# Kiểm tra phiên bản, firewall và port cần mở cho Spring Framework JMX Remote Connector

> **Chủ đề:** Spring Framework JMX  
> **Nhóm kiến thức:** Remote connector  
> **Bài học:** Kiểm tra phiên bản, firewall và port cần mở

## 1. Mục tiêu bài học

Khi triển khai JMX từ xa, lỗi thường không nằm ở annotation hoặc MBean mà ở **phiên bản JDK/JMX client**, **cách connector quảng bá địa chỉ**, **các cổng RMI** hoặc **quy tắc firewall/NAT**. Sau bài học này, bạn có thể:

- Phân biệt Spring JMX export và JMX remote connector.
- Kiểm tra phiên bản Java phía server và client, cấu hình JMX agent, kiểu connector đang dùng.
- Hiểu vì sao với RMI/JNDI, mở một cổng registry đôi khi **chưa đủ**.
- Cấu hình cổng JMX registry và cổng RMI server theo chính sách mạng rõ ràng.
- Phân biệt \`java.rmi.server.hostname\`, \`com.sun.management.jmxremote.port\` và \`com.sun.management.jmxremote.rmi.port\`.
- Kiểm tra kết nối theo từng bước: JVM đang nghe cổng nào, DNS, TCP, firewall, RMI stub, xác thực, TLS, MBeanServer và ObjectName.
- Thiết lập một cấu hình thử nghiệm có kiểm soát và tránh biến cổng JMX thành bề mặt quản trị công khai nguy hiểm.

## 2. Tách hai câu hỏi: có MBean hay có kết nối từ xa?

Ứng dụng Spring có thể export MBean:

\`\`\`java
@Configuration
@EnableMBeanExport
public class JmxConfig {
}
\`\`\`

Bean được công bố:

\`\`\`java
@Component
@ManagedResource(
    objectName = "app.management:type=Queue,name=orders"
)
public class QueueMonitor {

    @ManagedAttribute
    public int getDepth() {
        return 12;
    }
}
\`\`\`

Nhưng **\`@EnableMBeanExport\` không mở cổng mạng**. Nó kích hoạt hạ tầng đưa bean vào MBeanServer. Remote connector là lớp khác:

\`\`\`text
Spring bean / @ManagedResource
              |
              v
       Spring MBeanExporter
              |
              v
          MBeanServer
              ^
              |
       JMXConnectorServer
              ^
              |  TCP / RMI / TLS / authentication
              |
          JMX client
     JConsole / VisualVM /
     Java MBeanServerConnection
\`\`\`

Nếu JConsole local thấy MBean nhưng client từ máy khác không kết nối được, trước hết xác định **connector, địa chỉ và mạng**. Nếu remote client kết nối được nhưng không thấy MBean, mới cần kiểm tra **MBeanServer mà connector và exporter đang dùng**.

## 3. Những phiên bản cần kiểm tra

“Phiên bản JMX” không phải một con số độc lập đủ mô tả mọi khả năng kết nối. Thực tế cần quan sát cả các thành phần sau:

| Thành phần | Ví dụ kiểm tra | Vì sao liên quan |
|---|---|---|
| JDK/JRE server | \`java -version\` | Agent, RMI, TLS, cipher và tùy chọn JVM phụ thuộc JDK |
| JDK của client | \`java -version\`, JConsole đang dùng JDK nào | Client có thể gặp khác biệt về TLS/protocol |
| Spring Framework | Dependency đang chạy | Ảnh hưởng cơ chế export, không tự quyết định RMI ports |
| Spring Boot (nếu có) | Dependency và cấu hình JMX | Có thể bật/tắt export hoặc thay domain |
| JMX connector | RMI/JNDI, connector tự tạo, JMXMP nếu cài thêm | Quyết định endpoint và mô hình giao thức |
| OS/container | Linux/Windows/Docker/Kubernetes | Quyết định lệnh kiểm tra listening port, NAT và service routing |
| Firewall/network | Host firewall, security group, network policy | Có thể chặn kết nối dù JVM đã bind cổng |
| Security settings | Authentication, SSL/TLS và access rules | Kết nối TCP thành công chưa chắc vào được JMX |

Trên server:

\`\`\`bash
java -version
\`\`\`

Để biết JVM đang chạy thực tế dùng JDK nào, có thể dùng công cụ JDK tương ứng:

\`\`\`bash
jcmd <PID> VM.version
jcmd <PID> VM.command_line
jcmd <PID> VM.system_properties
\`\`\`

\`jcmd\` cần quyền phù hợp và công cụ attach phải có thể truy cập tiến trình. Không đưa toàn bộ \`VM.system_properties\` vào log chia sẻ, bởi system properties có thể chứa secret hoặc token.

Với Java process chạy trong container, cần chạy công cụ trong môi trường có thể nhìn thấy PID và JVM tương ứng. Phiên bản Java trên máy host **không nhất thiết** là phiên bản JVM đang chạy trong container.

### Vì sao tương thích phiên bản ảnh hưởng remote JMX?

JMX RMI dựa vào Java RMI và có thể chịu ảnh hưởng của:

- Phiên bản JDK và implementation connector.
- Cơ chế authentication, authorization.
- TLS protocol/cipher mặc định ở hai đầu.
- Java serialization và classpath cho payload tùy biến.
- Các chính sách bảo mật và thuật toán bị vô hiệu hóa trên JDK mới.
- Hostname hoặc RMI endpoint được server gửi cho client.

Không suy đoán rằng một phiên bản Spring Framework nhất định bắt buộc có một cổng JMX cố định. Spring export là logic trong JVM; thông số cổng do JMX agent/connector và hạ tầng mạng quyết định.

## 4. Hai endpoint quan trọng trong JMX RMI

Với remote JMX dùng RMI/JNDI thông dụng, có ít nhất hai vai trò:

1. **RMI registry/JNDI lookup**: nơi client lấy stub/địa chỉ connector.
2. **RMI connector endpoint**: nơi client thực sự tiếp tục giao tiếp với JMX server.

\`\`\`text
                       Máy client
                           |
             1) Lookup tới registry port
                           |
                           v
                  HOST:REGISTRY_PORT
                         RMI registry
                           |
                  nhận RMI stub / endpoint
                           |
             2) Connect tới RMI server port
                           |
                           v
                HOST:RMI_SERVER_PORT
                           |
                           v
                JMXConnectorServer
                           |
                           v
                       MBeanServer
\`\`\`

Một kết nối ban đầu thành công đến registry **không đảm bảo** toàn bộ phiên JMX hoạt động. Client còn phải kết nối đến host/port được RMI stub quảng bá.

Ví dụ URI:

\`\`\`text
service:jmx:rmi:///jndi/rmi://jmx.example.internal:9010/jmxrmi
\`\`\`

Trong URL này, \`9010\` là cổng phục vụ **registry lookup**. Endpoint tiếp theo có thể sử dụng cổng RMI riêng. Chỉ nhìn URL chưa đủ để khẳng định client sẽ sử dụng đúng một TCP connection hoặc một cổng duy nhất.

## 5. Các system properties thông dụng

Với built-in JMX management agent trên HotSpot/OpenJDK, các thuộc tính thường dùng gồm:

| Thuộc tính | Chức năng |
|---|---|
| \`com.sun.management.jmxremote\` | Bật khả năng quản trị JMX của JVM theo cơ chế agent phù hợp |
| \`com.sun.management.jmxremote.port\` | Cổng remote JMX registry/lookup của built-in agent |
| \`com.sun.management.jmxremote.rmi.port\` | Cổng RMI connector endpoint được cố định, nếu agent/JDK hỗ trợ |
| \`java.rmi.server.hostname\` | Hostname/IP được RMI quảng bá cho client |
| \`com.sun.management.jmxremote.authenticate\` | Bật/tắt xác thực theo built-in agent |
| \`com.sun.management.jmxremote.ssl\` | Bật/tắt SSL/TLS theo built-in agent |
| \`com.sun.management.jmxremote.access.file\` | Đường dẫn access-control file nếu dùng cơ chế file |
| \`com.sun.management.jmxremote.password.file\` | Đường dẫn password file nếu dùng cơ chế file |
| \`com.sun.management.jmxremote.local.only\` | Một tùy chọn liên quan giới hạn local access trên các JDK hỗ trợ; kiểm tra semantics theo JDK thực tế |

Tính khả dụng và semantics phải được kiểm tra với **JDK vendor/version thực tế**. Các system properties này thuộc cơ chế built-in agent, không phải một phần annotation \`@ManagedResource\` của Spring.

### Cấu hình minh họa cho môi trường nội bộ

\`\`\`bash
java \
  -Dcom.sun.management.jmxremote \
  -Dcom.sun.management.jmxremote.port=9010 \
  -Dcom.sun.management.jmxremote.rmi.port=9011 \
  -Djava.rmi.server.hostname=jmx.example.internal \
  -Dcom.sun.management.jmxremote.authenticate=true \
  -Dcom.sun.management.jmxremote.ssl=true \
  -jar application.jar
\`\`\`

Đây là mẫu minh họa: trước khi chạy thực tế, cần chuẩn bị file authentication/authorization, keystore/truststore hoặc SSL setup tương ứng với agent/JDK và mạng. Đừng cho rằng chỉ cần thêm hai cờ \`authenticate=true\` và \`ssl=true\` là đã hoàn thành cấu hình an toàn.

Cổng \`9010\` và \`9011\` chỉ là ví dụ; chọn cổng theo hạ tầng của bạn.

## 6. Vì sao phải kiểm tra hai cổng?

Không cố định \`rmi.port\` có thể khiến connector endpoint dùng một cổng động. Trong môi trường firewall, client có thể:

- Kết nối được TCP đến \`9010\`.
- Tra được registry.
- Nhận stub trỏ đến một cổng mà firewall không cho qua.
- Treo hoặc báo timeout khi thiết lập JMX connection.

Do đó, thiết kế firewall nên dựa trên **danh sách cổng thực tế của connector**, không chỉ trên cổng xuất hiện trong URL.

Ví dụ:

\`\`\`text
Client subnet            Server
10.10.20.0/24            10.10.30.15

  TCP 9010  -----------> RMI registry
  TCP 9011  -----------> RMI endpoint
\`\`\`

Nếu hai vai trò được cấu hình dùng chung cổng trên một implementation phù hợp, cần xác nhận hành vi cụ thể. Đừng mặc định có thể dùng cùng cổng ở mọi cấu hình JMX agent hoặc connector tự viết.

## 7. java.rmi.server.hostname giải quyết vấn đề gì?

RMI stub có thể chứa hostname/IP mà client phải kết nối đến. Trong môi trường nhiều network interface, container, NAT hoặc DNS nội bộ, host được quảng bá có thể không truy cập được từ phía client.

Ví dụ server có:

\`\`\`text
Hostname nội bộ container: app-pod-7
IP trong container: 172.18.0.4
Địa chỉ client truy cập: jmx.example.internal
\`\`\`

Client mở URL tới \`jmx.example.internal:9010\` nhưng stub lại hướng nó đến \`172.18.0.4:9011\`. Nếu client ngoài container không route được \`172.18.0.4\`, kết nối tiếp theo thất bại.

Dùng:

\`\`\`text
-Djava.rmi.server.hostname=jmx.example.internal
\`\`\`

để cấu hình địa chỉ mà RMI quảng bá theo hạ tầng phù hợp.

**Lưu ý:** đây là địa chỉ **được quảng bá**, không đồng nghĩa JVM sẽ bind mọi network interface theo đúng ý muốn. Kiểm soát bind/listen interface còn phụ thuộc implementation agent/socket factory và cấu hình hệ điều hành. Cần kiểm tra listening sockets thực tế.

## 8. Firewall cần mở những gì?

Một chính sách thực tế nên bắt đầu từ câu hỏi: “Client nào được phép quản trị JVM nào?”

Ví dụ bảng yêu cầu firewall:

| Luồng | Nguồn | Đích | Giao thức | Mục đích |
|---|---|---|---|---|
| JMX lookup | Bastion/monitoring subnet được duyệt | JVM server | TCP 9010 | RMI registry |
| JMX endpoint | Cùng tập client được duyệt | JVM server | TCP 9011 | RMI connector |
| DNS | Client hoặc hạ tầng DNS | DNS resolver | Theo chính sách DNS | Phân giải hostname |
| TLS/identity backend | Connector nếu dùng hệ thống xác thực ngoài | Hệ thống tương ứng | Theo thiết kế | Hỗ trợ xác thực |

Chỉ mở inbound từ các địa chỉ quản trị được phê duyệt. Đừng mở \`0.0.0.0/0\` trên firewall/security group chỉ để JConsole kết nối được.

Phân biệt ba lớp thường bị nhầm:

- **Host firewall**: Windows Firewall, nftables/iptables, firewalld...
- **Cloud firewall/security group**: quy tắc trước VM hoặc load balancer.
- **Container/Kubernetes network policy**: kiểm soát traffic giữa pods/nodes/namespaces.

Một lớp cho phép không đảm bảo toàn đường đi cho phép. Cần kiểm tra các lớp có liên quan đến topology thực tế.

## 9. Kiểm tra port JVM đang LISTEN

Trên Linux, có thể dùng:

\`\`\`bash
ss -ltnp
\`\`\`

Hoặc lọc theo port đã chọn:

\`\`\`bash
ss -ltnp | grep -E ':(9010|9011)\b'
\`\`\`

Trên Windows PowerShell:

\`\`\`powershell
Get-NetTCPConnection -State Listen |
    Where-Object { $_.LocalPort -in 9010, 9011 } |
    Select-Object LocalAddress, LocalPort, OwningProcess
\`\`\`

Các cổng nghe phải thuộc đúng JVM/PID hoặc quy trình proxy/forwarding được thiết kế. Khi dịch vụ chạy trong container, việc port LISTEN bên trong container chưa chứng minh port đã được publish hoặc route từ ngoài.

Nếu không có process LISTEN:

1. Kiểm tra JVM đã nhận đúng system properties hay chưa.
2. Kiểm tra startup log có lỗi JMX agent không.
3. Kiểm tra cổng có bị process khác chiếm không.
4. Kiểm tra việc agent/connector thực sự được khởi tạo.
5. Kiểm tra bind address hoặc giới hạn local-only.

Không bắt đầu bằng việc mở firewall nếu chính JVM chưa nghe trên endpoint được mong đợi.

## 10. Kiểm tra TCP từ phía client

Từ máy có JConsole hoặc monitoring agent, kiểm tra từng cổng.

Linux/macOS:

\`\`\`bash
nc -vz jmx.example.internal 9010
nc -vz jmx.example.internal 9011
\`\`\`

Windows PowerShell:

\`\`\`powershell
Test-NetConnection jmx.example.internal -Port 9010
Test-NetConnection jmx.example.internal -Port 9011
\`\`\`

Nếu công cụ không có \`nc\`, dùng công cụ TCP phù hợp với OS. Kết quả kết nối TCP chỉ chứng minh một socket được mở hoặc reachable; **không xác nhận JMX handshake, SSL, authentication và MBean lookup**.

Diễn giải:

| Kết quả | Khả năng | Bước tiếp theo |
|---|---|---|
| Connection refused | Không có listener hoặc bị reject | Kiểm tra process/listen/host |
| Timeout | Firewall, network path, routing hoặc đích không trả lời | Kiểm tra rule và route |
| Port 9010 OK, 9011 fail | RMI endpoint bị chặn/không bind/sai host | Kiểm tra rmi.port và stub |
| Cả hai TCP OK, JMX fail | TLS, authentication, URL, RMI hostname hoặc protocol | Kiểm tra JMX handshake |
| JMX connect OK, MBean missing | Sai MBeanServer/ObjectName/exporter | Kiểm tra registry |

TCP test không bảo đảm endpoint thực sự là dịch vụ JMX. Một process khác có thể chiếm cổng; phải kết hợp kết quả với PID trên server.

## 11. Kết nối bằng JConsole

Khởi chạy JConsole bằng một JDK tương thích:

\`\`\`bash
jconsole
\`\`\`

Chọn remote process và sử dụng endpoint hoặc service URL theo cách JConsole/JDK hỗ trợ.

Ví dụ service URL:

\`\`\`text
service:jmx:rmi:///jndi/rmi://jmx.example.internal:9010/jmxrmi
\`\`\`

Quy trình:

1. Xác nhận hostname phía client resolve đúng địa chỉ mong muốn.
2. Kiểm tra registry và RMI endpoint reachable.
3. Chuẩn bị thông tin xác thực và trust configuration nếu TLS được bật.
4. Kết nối JConsole.
5. Mở tab **MBeans** và tìm domain/ObjectName ứng dụng.
6. Đọc attribute hoặc thử operation **chỉ đọc/không phá hủy**.
7. Nếu kết nối được nhưng không có MBean, kiểm tra MBeanServer của connector và exporter.

Tùy JDK, JConsole có thể cần JVM options để sử dụng truststore hoặc cơ chế xác thực đặc thù. Tránh đưa mật khẩu vào dòng lệnh hoặc file log không được bảo vệ.

## 12. Kiểm tra bằng Java client thay vì chỉ GUI

Một ví dụ client JMX:

\`\`\`java
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

public class JmxClientProbe {
    public static void main(String[] args) throws Exception {
        JMXServiceURL url = new JMXServiceURL(
            "service:jmx:rmi:///jndi/rmi://" +
            "jmx.example.internal:9010/jmxrmi"
        );

        try (JMXConnector connector =
                 JMXConnectorFactory.connect(url)) {

            MBeanServerConnection connection =
                connector.getMBeanServerConnection();

            ObjectName name = new ObjectName(
                "app.management:type=Queue,name=orders"
            );

            System.out.println(
                "registered=" + connection.isRegistered(name)
            );

            if (connection.isRegistered(name)) {
                System.out.println(
                    "MBeanClass=" +
                        connection.getMBeanInfo(name).getClassName()
                );
            }
        }
    }
}
\`\`\`

Ví dụ trên chưa cung cấp credentials hoặc SSL environment. Với connector yêu cầu xác thực, truyền cấu hình phù hợp trong environment map hoặc cấu hình client theo tài liệu JMX của JDK hiện tại; không tắt xác thực để làm ví dụ hoạt động trên production.

Khả năng gọi \`isRegistered\` thành công cho thấy connection đi qua JMX và truy vấn registry được. Nhưng ObjectName không tồn tại vẫn có thể do exporter chưa đăng ký hoặc sử dụng một MBeanServer khác.

## 13. Kiểm tra hostname, DNS và địa chỉ được quảng bá

Trên client, kiểm tra:

\`\`\`bash
nslookup jmx.example.internal
\`\`\`

hoặc dùng lệnh DNS phù hợp:

\`\`\`bash
getent hosts jmx.example.internal
\`\`\`

So sánh kết quả với địa chỉ mà firewall/service route cho phép. Nhưng RMI có hai bước, nên còn cần biết stub quảng bá host/port nào.

Một số dấu hiệu điển hình:

- Client báo lỗi kết nối đến hostname không phải hostname ban đầu.
- Stack trace chứa IP private của container.
- Registry lookup thành công nhưng JMX handshake timeout.
- Client trong cùng server kết nối được, client từ mạng khác không được.

Tập trung kiểm tra \`java.rmi.server.hostname\`, rmi.port, port forwarding và topology mạng. Không “sửa” bằng cách mở cả một dải cổng rộng không rõ phạm vi.

## 14. Docker và port publishing

Với Docker, cần nghĩ đến hai bộ cổng: cổng trong container và cổng ở host.

\`\`\`text
JConsole trên host/network
        |
        | host:9010 / host:9011
        v
Docker port publish
        |
        | container:9010 / container:9011
        v
JVM built-in JMX RMI agent
\`\`\`

Ví dụ một đoạn cấu hình Docker Compose minh họa:

\`\`\`yaml
services:
  application:
    image: example/java-app
    ports:
      - "9010:9010"
      - "9011:9011"
    environment:
      JAVA_TOOL_OPTIONS: >-
        -Dcom.sun.management.jmxremote
        -Dcom.sun.management.jmxremote.port=9010
        -Dcom.sun.management.jmxremote.rmi.port=9011
        -Djava.rmi.server.hostname=jmx.example.internal
        -Dcom.sun.management.jmxremote.authenticate=true
        -Dcom.sun.management.jmxremote.ssl=true
\`\`\`

Đây là minh họa **topology**, chưa phải cấu hình production hoàn chỉnh: cần file authentication, TLS/key material, giới hạn interface được publish, Docker network và firewall. Nếu hostname trong stub không truy cập được từ client thì vẫn lỗi dù hai cổng đã publish.

Đối với chạy thử trên máy đơn, có thể sử dụng port forwarding/tunnel để giới hạn phạm vi truy cập. Phải bảo đảm địa chỉ quảng bá từ RMI tương thích với đường tunnel; không phải mọi cấu hình NAT port mapping tùy ý đều hoạt động với Java RMI.

## 15. Kubernetes: Service, pod và NetworkPolicy

Trong Kubernetes, lỗi JMX RMI thường liên quan đến endpoint được quảng bá và cơ chế chuyển tiếp đến pod:

- Container trong pod nghe cổng JMX.
- \`Service\` expose cổng registry và RMI.
- \`NetworkPolicy\` cho phép traffic từ namespace/client được duyệt.
- RMI stub phải quảng bá địa chỉ mà client thực sự truy cập được.
- Một service load-balanced trước nhiều pod có thể định tuyến lookup và endpoint đến **hai pod khác nhau**, gây lỗi.

Với management endpoint kiểu RMI, thường cần kết nối tới **một instance cụ thể** thay vì phân phối ngẫu nhiên giữa nhiều replica. Một hướng là dùng port-forward vào pod hoặc endpoint per-pod được quản lý phù hợp, kết hợp authentication và security.

Không giả định một Kubernetes Service chung với load balancing sẽ luôn phù hợp cho phiên RMI có state.

Ví dụ lệnh chẩn đoán:

\`\`\`bash
kubectl get pods -n application
kubectl get svc -n application
kubectl describe svc jmx-service -n application
kubectl get networkpolicy -n application
\`\`\`

Các tên resource và namespace ở đây chỉ là ví dụ. Không thay đổi production NetworkPolicy hoặc mở service ra public chỉ để truy cập JConsole.

## 16. Firewall và security group: ít quyền nhất

JMX remote là **kênh quản trị JVM**. Nó có thể cho phép client đọc attribute, gọi operation và thay đổi trạng thái runtime tùy quyền.

Nên:

1. Chỉ expose trong private network hoặc qua đường quản trị đã kiểm soát.
2. Giới hạn source IP/subnet đến các monitoring host hoặc bastion.
3. Bật authentication/authorization phù hợp.
4. Dùng TLS khi dữ liệu qua mạng không được bảo vệ.
5. Không dùng \`authenticate=false\` và \`ssl=false\` trên một cổng public.
6. Quản lý credential trong secret manager hoặc file có quyền hạn thích hợp.
7. Giới hạn các MBean/operations có tác dụng phụ, không export API nhạy cảm.
8. Quan sát truy cập bất thường và có thủ tục thu hồi quyền.

Các công cụ giám sát thường chỉ cần quyền **read**, không nhất thiết cần quyền gọi operation thay đổi trạng thái. Thiết kế permission tương ứng thay vì cho mọi client quyền readwrite.

## 17. Phiên bản JDK và thay đổi cấu hình bảo mật

Trên các JDK khác nhau, có thể có thay đổi về:

- Bộ TLS protocol/cipher được bật mặc định.
- Cơ chế đọc password/access file và yêu cầu permission.
- Thuộc tính cấu hình management agent.
- Cách local attach và remote management được khởi tạo.
- Chính sách serialization/filter hoặc hạn chế giao thức cũ.
- Default behavior liên quan local-only và socket binding.

Do đó, khi nâng JDK:

\`\`\`text
Trước nâng cấp:
  server JDK version
  client JDK version
  JMX agent flags
  hostname + registry port + RMI port
  TLS/auth settings
  firewall rules

Sau nâng cấp:
  kiểm tra lại tất cả các yếu tố trên
  + xác nhận JConsole/monitoring agent kết nối thực tế
\`\`\`

Không chỉ kiểm tra \`java -version\` trên host; hãy kiểm tra binary/JVM runtime của đúng process. Nếu lỗi mới xuất hiện sau nâng cấp, đối chiếu thay đổi JDK, truststore, security properties và log handshake trước khi thay firewall.

## 18. Chẩn đoán theo triệu chứng

| Triệu chứng | Nguyên nhân khả dĩ | Hướng kiểm tra |
|---|---|---|
| Không có cổng LISTEN | Agent không bật, cấu hình sai, startup fail | VM flags, process, log |
| TCP connection refused | Không có listener hoặc bị reject | PID, bind address, cổng |
| TCP timeout | Firewall, routing, network policy | Source/destination, subnet, rules |
| Registry port OK, endpoint port fail | Chưa cố định RMI port, endpoint bị chặn | \`jmxremote.rmi.port\`, \`ss\`, firewall |
| Kết nối đến IP lạ | RMI stub quảng bá hostname sai | \`java.rmi.server.hostname\`, DNS/NAT |
| \`SSLHandshakeException\` | TLS version/cipher/truststore không tương thích | JDK, cert, client trust |
| Authentication failure | Sai credential hoặc access control | Credential source, file permissions |
| JMX session OK nhưng MBean thiếu | Exporter/connector dùng server khác hoặc ObjectName sai | \`getMBeanInfo\`, \`queryNames\` |
| Query được MBean nhưng invoke lỗi | Signature, permission, exception implementation | Metadata và cause |
| Kết nối chập chờn trong k8s | Load balancing giữa các pod, endpoint không ổn định | Per-pod endpoint và service routing |

## 19. Quy trình kiểm tra từng lớp

Một quy trình xử lý sự cố có thể chạy theo thứ tự:

\`\`\`text
[1] Đúng JVM và JDK version?
        |
        v
[2] JMX agent / connector đã bật?
        |
        v
[3] Registry và RMI endpoint ports xác định?
        |
        v
[4] Đúng bind/listen address và PID?
        |
        v
[5] DNS + route + firewall cho cả hai cổng?
        |
        v
[6] RMI stub quảng bá hostname/port reachable?
        |
        v
[7] TLS + authentication thành công?
        |
        v
[8] JMXConnector kết nối được?
        |
        v
[9] Đúng MBeanServer và ObjectName?
        |
        v
[10] Đọc metadata/attribute và kiểm tra operation an toàn
\`\`\`

Phân tầng giúp tránh “sửa nhầm” vấn đề. Không chỉnh Spring annotation khi thực ra TCP bị chặn, và không mở firewall rộng hơn khi vấn đề là client thiếu TLS truststore.

## 20. Checklist trước khi vận hành

- [ ] Đã xác định đúng JVM/PID và phiên bản JDK server.
- [ ] Client JConsole/agent dùng JDK và TLS settings tương thích.
- [ ] Đã phân biệt Spring export với JMX remote connector.
- [ ] Có ObjectName của MBean cần quan sát.
- [ ] Đã xác định registry port và endpoint port thực tế.
- [ ] Nếu cần firewall cố định, đã cấu hình \`jmxremote.rmi.port\` phù hợp.
- [ ] \`java.rmi.server.hostname\` trỏ đến địa chỉ client có thể kết nối.
- [ ] Host, cloud và container network policy chỉ cho phép nguồn được duyệt.
- [ ] DNS/route/NAT đã được đối chiếu với địa chỉ trong RMI stub.
- [ ] TLS/authentication/authorization đã được cấu hình và thử thật.
- [ ] Có cách kiểm tra TCP trên từng cổng từ máy client.
- [ ] Đã thử kết nối JMX thực, không chỉ thử socket.
- [ ] Connector và exporter sử dụng cùng MBeanServer dự kiến.
- [ ] Có log vận hành thích hợp nhưng không để lộ password/secret.
- [ ] Không expose remote JMX ra Internet công khai.

## 21. Bài tập thực hành

### Tình huống A: Cổng registry mở nhưng JConsole timeout

JVM:

\`\`\`text
-Dcom.sun.management.jmxremote.port=9010
\`\`\`

Không có cờ cố định RMI endpoint port.

**Câu hỏi:** Vì sao kiểm tra \`nc -vz host 9010\` thành công nhưng JConsole vẫn timeout?

**Gợi ý:** client có thể nhận RMI stub chứa endpoint khác dùng cổng động không đi qua firewall. Cần xác định và cố định cổng endpoint nếu hạ tầng yêu cầu, rồi kiểm tra đường mạng tương ứng.

### Tình huống B: Docker publish đủ hai cổng nhưng vẫn lỗi

Cấu hình:

\`\`\`text
registry port: 9010
RMI port: 9011
stub hostname: 172.18.0.4
client location: outside Docker host
\`\`\`

**Câu hỏi:** Điều gì cần sửa?

**Gợi ý:** hostname được quảng bá phải reachable từ client; private container IP có thể không route được từ bên ngoài. Kiểm tra \`java.rmi.server.hostname\`, publish mappings và giới hạn bảo mật.

### Tình huống C: TCP đều OK nhưng bị từ chối

JConsole báo authentication failure sau khi mở kết nối.

**Câu hỏi:** Mở thêm firewall port có giải quyết không?

**Gợi ý:** Không. Lỗi đã tới lớp xác thực; cần kiểm tra credentials và access policy thay vì mở thêm cổng.

### Tình huống D: JMX kết nối thành công nhưng không thấy MBean

Spring exporter đăng ký bean vào một custom MBeanServer, còn connector expose platform MBeanServer.

**Câu hỏi:** Nên làm gì?

**Gợi ý:** dùng cùng MBeanServer cho exporter và connector hoặc kết nối tới server đã được exporter sử dụng; kiểm chứng bằng \`isRegistered\` và \`getMBeanInfo\` trên đúng instance.

## 22. Câu hỏi tự kiểm tra

1. \`@EnableMBeanExport\` có tự bật remote JMX port không?
2. Vì sao JMX RMI có thể cần hai cổng TCP?
3. \`com.sun.management.jmxremote.port\` và \`com.sun.management.jmxremote.rmi.port\` đảm nhiệm vai trò gì?
4. \`java.rmi.server.hostname\` liên quan tới bind hay endpoint quảng bá?
5. Vì sao TCP port reachable chưa chứng minh JMX login thành công?
6. Khi nâng JDK, những yếu tố TLS nào có thể thay đổi?
7. Vì sao JMX RMI qua Kubernetes Service load-balanced có thể lỗi?
8. Nếu JConsole có thể kết nối nhưng không thấy một MBean, bước kiểm tra đúng tiếp theo là gì?
9. Vì sao không nên mở JMX remote cho mọi IP để phục vụ debug?
10. Khi xảy ra timeout, quy trình nào giúp phân biệt firewall, endpoint và authentication?

## 23. Ghi nhớ

\`\`\`text
Remote JMX = exporter + MBeanServer + connector + network + security

RMI/JNDI thường gồm:
  registry lookup port
  + RMI connector endpoint port

Cần kiểm tra:
  JDK version
  + agent flags
  + bind/listen ports
  + advertised hostname
  + DNS/route/firewall
  + TLS/authentication
  + MBeanServer/ObjectName
\`\`\`

**Nguyên tắc trọng tâm:** mở đúng cổng chỉ là một phần của JMX remote. Hãy kiểm tra đủ **hai bước RMI**, địa chỉ được quảng bá, khả năng kết nối mạng và yêu cầu bảo mật, rồi mới xác minh MBean trên registry thực tế. Không dùng việc tắt bảo mật hoặc mở rộng firewall làm giải pháp mặc định.