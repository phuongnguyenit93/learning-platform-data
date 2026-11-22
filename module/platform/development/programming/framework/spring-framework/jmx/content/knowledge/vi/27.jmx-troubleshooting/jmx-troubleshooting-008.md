# JConsole không kết nối được tới remote server — Chẩn đoán Spring Framework JMX

## 1. Bối cảnh và mục tiêu

JConsole là công cụ quản trị và quan sát Java qua Java Management Extensions (JMX). Nó có thể kết nối JVM cục bộ hoặc **remote JMX server** để xem MBean, heap, thread, CPU và các chỉ số quản trị khác. Trong ứng dụng Spring Framework, bean có thể được export bằng `MBeanExporter` vào một `MBeanServer`; nhưng **MBean đã đăng ký thành công không đồng nghĩa JConsole có thể kết nối từ xa**.

Khi JConsole báo không kết nối được, nguyên nhân có thể nằm ở từng lớp riêng: JMX agent chưa chạy, sai địa chỉ service URL, tường lửa, hostname RMI, cổng kết nối bổ sung, xác thực, TLS, chính sách mạng, hoặc connector đang trỏ tới một `MBeanServer` khác. Bài này hướng dẫn xử lý có hệ thống, thay vì thử mở cổng hoặc tắt bảo mật ngẫu nhiên.

Mục tiêu:

- Hiểu đường đi từ JConsole tới `MBeanServerConnection` và MBean.
- Phân biệt vấn đề **kết nối remote** với vấn đề **MBean không xuất hiện**.
- Biết cấu hình JMX Remote cơ bản của JVM và cơ chế hai bước của RMI.
- Xác minh host, port, firewall, DNS, NAT, container networking và credentials.
- Đọc đúng thông báo lỗi như `ConnectException`, `UnknownHostException`, `SSLHandshakeException`, lỗi authentication hoặc timeout.
- Cấu hình truy cập an toàn: giới hạn mạng, xác thực và TLS, không expose quản trị JMX ra Internet công khai.
- Đặt quy trình kiểm tra có khả năng tái hiện và ghi nhận evidence để đội vận hành phối hợp.

## 2. Mô hình kết nối JConsole từ xa

```text
Máy quản trị                         JVM ứng dụng
+------------------+                +----------------------------+
| JConsole         |                | JMX Remote agent /        |
| JMXConnector     | --network-->   | JMXConnectorServer         |
|                  | <----------    |          |                 |
+------------------+                |   MBeanServerConnection    |
                                    |          |                 |
                                    |      MBeanServer           |
                                    |      /        \            |
                                    | JVM MXBeans  Spring MBeans |
                                    +----------------------------+
```

JConsole phải tạo được kết nối tới connector. Sau đó, connector cung cấp một `MBeanServerConnection` để đọc `MBeanInfo`, attribute và operation.

Có hai bài toán khác nhau:

1. **Không tạo được kết nối:** JConsole không đến được connector hoặc không hoàn tất handshake/authentication.
2. **Kết nối được nhưng thiếu MBean:** connector có thể trỏ server khác, exporter chưa chạy, tên MBean sai hoặc bean chưa được export.

Không giải quyết vấn đề thứ hai bằng cách mở thêm port nếu JConsole đã kết nối thành công. Ngược lại, sửa annotation `@ManagedResource` không giải quyết được lỗi TCP connection refused.

## 3. JMX Remote và Spring MBeanExporter là hai tầng độc lập

Spring JMX thường có các thành phần:

```java
MBeanExporter exporter = new MBeanExporter();
exporter.setServer(mbeanServer);
exporter.setBeans(
    Map.of("com.example.ops:type=JobMonitor,name=Main", monitor)
);
```

Exporter đưa bean vào **một MBeanServer**. Cơ chế remote cần một connector/management agent cho phép JConsole từ JVM khác truy cập đến server đó. Nếu remote agent của JVM dùng platform MBeanServer mà exporter đăng ký vào private server, JConsole có thể **kết nối được** nhưng không thấy MBean của Spring.

Hai điều cần xác minh:

- `exporter.setServer(...)` cuối cùng nhận instance MBeanServer nào?
- Remote JMX connector được gắn tới MBeanServer nào?

Một `MBeanServerFactoryBean` tạo server mới cũng **không tự mở remote port**. Ngay cả khi bean tồn tại dưới ObjectName hợp lệ, client remote vẫn cần endpoint phù hợp.

## 4. Thứ tự xử lý sự cố tổng quát

Nên đi từ thấp lên cao:

1. **Xác định đích thực:** đúng hostname/IP, môi trường, JVM/process và cổng.
2. **Kiểm tra JMX agent/connector:** server có thật sự lắng nghe không?
3. **Kiểm tra TCP và đường mạng:** DNS, route, firewall, security group, NetworkPolicy, VPN, NAT.
4. **Kiểm tra RMI handshake:** có port thứ hai không và stub quảng bá hostname nào?
5. **Kiểm tra authentication/TLS:** credential, truststore, certificate, protocol.
6. **Kiểm tra server-side logs:** lỗi startup agent, bind port, security hoặc handshake.
7. **Sau khi kết nối thành công:** kiểm tra MBeanServer, ObjectName và exporter của Spring.

Nguyên tắc: **mỗi lần đổi đúng một giả thuyết** và ghi lại kết quả. Không tắt TLS/authentication hay mở rộng firewall như bước đầu mặc định.

## 5. Xác định JMX Remote agent đã bật chưa

Một JVM có thể bật JMX management agent bằng các Java system properties. Ví dụ dưới đây minh họa cách buộc RMI registry port và RMI server port ở một giá trị cố định, nhưng các thuộc tính bảo mật cụ thể phải được cấu hình an toàn theo môi trường:

```text
-Dcom.sun.management.jmxremote
-Dcom.sun.management.jmxremote.port=9010
-Dcom.sun.management.jmxremote.rmi.port=9010
-Djava.rmi.server.hostname=jmx.internal.example
```

Ý nghĩa:

- `com.sun.management.jmxremote.port`: cổng quản trị JMX Remote registry.
- `com.sun.management.jmxremote.rmi.port`: cổng RMI server; đặt cố định để tường lửa dễ cho phép.
- `java.rmi.server.hostname`: hostname/IP được RMI đưa vào địa chỉ mà client sử dụng khi gọi tiếp.
- `com.sun.management.jmxremote`: bật phần hỗ trợ management agent theo JDK/cấu hình tương ứng.

**Không dùng cấu hình vô hiệu hóa xác thực hoặc SSL cho môi trường production.** Ví dụ cấu hình trên là các thuộc tính định tuyến, chưa đủ mô tả một triển khai remote JMX an toàn.

Các JDK, cách chạy và policy môi trường có thể khác nhau. Hãy xác minh agent thực sự khởi chạy và các system properties áp dụng cho **đúng JVM**. Nếu JVM đã chạy, chỉ thêm tùy chọn vào terminal mới không thay đổi process cũ.

### 5.1. Các lỗi khởi động agent

Nếu agent không mở cổng, xem log JVM khi startup:

- Port đã bị process khác chiếm.
- Host bind không hợp lệ.
- File password/access không tồn tại hoặc sai quyền.
- Lỗi cấu hình TLS/truststore/keystore.
- JVM chạy với option không được phiên bản JDK hỗ trợ.
- Cấu hình launcher/container không chuyển `JAVA_TOOL_OPTIONS` hoặc JVM arguments như dự định.

Trước khi kết luận do firewall, cần xác nhận process Java thực sự đang lắng nghe ở cổng dự kiến.

## 6. Hai bước RMI: cổng registry và cổng thực tế

Một nguyên nhân điển hình: kiểm tra thấy cổng JMX registry mở, nhưng JConsole vẫn bị treo hoặc timeout.

Với kết nối JMX RMI, client thường:

1. Kết nối tới RMI registry.
2. Lấy một stub mô tả endpoint thực tế.
3. Kết nối tiếp tới hostname/port được stub cung cấp.
4. Hoàn tất lời gọi remote tới `MBeanServerConnection`.

```text
JConsole
  |
  | (1) TCP -> jmx.internal.example:9010
  v
RMI registry
  |
  | (2) trả stub
  v
jmx.internal.example:9010 (hoặc host/port khác trong stub)
  ^
  | (3) Client mở kết nối tới endpoint trong stub
  +----------------------------------------
```

Nếu `com.sun.management.jmxremote.rmi.port` không cố định trong một cấu hình dùng RMI, cổng RMI server có thể được chọn động và firewall chỉ mở registry port sẽ chưa đủ. Nếu stub chứa hostname nội bộ không phân giải được từ phía client, kết nối cũng thất bại.

**Kiểm tra port registry mở không chứng minh toàn bộ đường RMI hoạt động.**

### 6.1. Kiểm tra với cổng cố định

Trong môi trường hỗ trợ và đã được đội vận hành phê duyệt, có thể đặt:

```text
-Dcom.sun.management.jmxremote.port=9010
-Dcom.sun.management.jmxremote.rmi.port=9010
```

Khi thực sự sử dụng chung cổng theo cấu hình agent/JDK, cần xác nhận bằng lệnh kiểm tra kết nối và logs; không mặc định mọi container/JDK sẽ có cùng cách binding.

Nếu dùng hai cổng riêng, ví dụ 9010 (registry) và 9011 (RMI), cả hai phải có đường mạng thích hợp theo topology và client sử dụng đúng URL.

## 7. Hostname trong RMI stub: bẫy DNS, NAT, container

Giả sử client kết nối tới:

```text
jmx-public.internal:9010
```

nhưng JVM lại quảng bá:

```text
127.0.0.1:54321
```

hoặc:

```text
java-pod-7f4abc:9011
```

Client lấy được stub từ registry nhưng không thể gọi tiếp nếu địa chỉ đó không reachable từ máy của nó.

`java.rmi.server.hostname` ảnh hưởng hostname được quảng bá. Giá trị phải có ý nghĩa **theo góc nhìn của client**, không chỉ theo góc nhìn của container hoặc JVM.

Các trường hợp:

| Môi trường | Rủi ro điển hình |
| --- | --- |
| Máy chủ truyền thống | Hostname trong stub không được DNS phân giải ngoài máy chủ |
| Docker | Stub quảng bá container IP/hostname, client ở máy ngoài không đến được |
| Kubernetes | Stub quảng bá pod IP không thể truy cập từ máy operator |
| NAT/VPN | Endpoint trong stub chứa địa chỉ trước NAT hoặc địa chỉ ngoài route |
| SSH tunnel | Stub quảng bá host/port không trùng endpoint được tunnel |
| Load balancer | Kết nối hai bước có thể đi vào instance khác hoặc không hỗ trợ cách chuyển tiếp phù hợp |

Trong container, việc map host port tới container port không tự sửa hostname trong stub. Cần thiết kế hostname/port mapping phù hợp và kiểm tra từ vị trí mạng thực tế của JConsole.

### 7.1. SSH tunnel

SSH tunnel có thể giảm nhu cầu mở JMX trực tiếp trên mạng rộng, nhưng RMI vẫn có thể trả stub trỏ sang hostname/port không nằm trong tunnel. Một cấu hình tunnel phải đưa **mọi endpoint cần thiết** qua tuyến truy cập hợp lệ.

Không nên hiểu “tunnel thành công tới 9010” là bảo đảm tất cả lời gọi RMI đều đi qua tunnel. Nếu có port RMI riêng hoặc hostname quảng bá khác, client có thể tiếp tục thất bại.

## 8. Kiểm tra DNS và kết nối TCP

Kiểm tra từ **máy chạy JConsole**, không chỉ từ server:

Trên Linux/macOS:

```bash
getent hosts jmx.internal.example
nc -vz jmx.internal.example 9010
```

Lưu ý `getent` thường có trên Linux; macOS có thể dùng `dig`, `nslookup` hoặc công cụ tương đương.

Trên Windows PowerShell:

```powershell
Resolve-DnsName jmx.internal.example
Test-NetConnection jmx.internal.example -Port 9010
```

Nếu không resolve tên, khắc phục DNS hoặc dùng hostname chính xác theo network policy. Nếu TCP không kết nối được, kiểm tra route, VPN, firewall, security group và port listening.

Nhưng nếu TCP **thành công**, đó mới là phép kiểm tra transport của **một cổng**. Nó không xác nhận JMX authentication, TLS hoặc bước RMI thứ hai.

### 8.1. Kiểm tra server đang nghe cổng

Trên máy Linux chạy JVM:

```bash
ss -lntp | grep 9010
```

Hoặc kiểm tra process/container logs và cấu hình triển khai nếu lệnh hệ thống bị hạn chế. Trong Kubernetes, cần xác nhận cả service/pod port và NetworkPolicy; đừng chỉ dựa vào `ss` bên trong container khi user không có quyền xem.

Một cổng `LISTEN` có thể thuộc process khác. Khi cần, đối chiếu PID để xác nhận đó chính là JVM được quản trị.

## 9. JConsole kết nối bằng host:port hay JMXServiceURL?

JConsole thường hỗ trợ kết nối tới remote process bằng host:port và có cách cung cấp JMX service URL tùy giao diện/phiên bản. Với JMX RMI, một dạng URL thường gặp là:

```text
service:jmx:rmi:///jndi/rmi://jmx.internal.example:9010/jmxrmi
```

Trong đó:

- `service:jmx:rmi:` xác định dạng JMX connector.
- Phần `/jndi/rmi://.../jmxrmi` chỉ nơi tra cứu connector stub qua registry.
- Host/port trong lookup phải khớp cơ chế publish và network mapping thực tế.

Nếu ứng dụng tạo `JMXConnectorServer` thủ công, service URL có thể khác. Không giả định mọi remote JMX endpoint đều dùng đường dẫn `/jmxrmi` hoặc cùng một port.

Đối với client Java, có thể kiểm tra connector theo URL:

```java
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

JMXServiceURL url = new JMXServiceURL(
    "service:jmx:rmi:///jndi/rmi://jmx.internal.example:9010/jmxrmi"
);

try (JMXConnector connector =
         JMXConnectorFactory.connect(url)) {

    System.out.println(
        "Connected MBean count: " +
        connector.getMBeanServerConnection().getMBeanCount()
    );
}
```

Ví dụ trên **chỉ thích hợp với endpoint cho phép kết nối theo chính sách và thông tin xác thực đã cấu hình**. Nếu cần authentication, phải truyền environment map với credentials hoặc callback phù hợp; không nhúng mật khẩu vào URL hoặc source code.

## 10. Authentication: sai tài khoản hoặc cấu hình quyền

Nhiều triển khai JMX Remote yêu cầu credentials. Khi nhập sai, JConsole có thể thông báo lỗi kết nối hoặc lỗi xác thực.

Nguyên nhân:

- Sai username/password.
- File password/access không đúng đường dẫn hoặc quyền.
- JVM không đọc được file bảo mật.
- Cấu hình agent yêu cầu auth nhưng client không cung cấp.
- Proxy hoặc connector riêng dùng cơ chế authentication khác.
- Tài khoản có quyền kết nối nhưng không được phép truy cập một số operation/attribute.

Phân biệt:

1. **Không kết nối được TCP**: chưa tới bước xác thực.
2. **Kết nối được tới agent nhưng bị từ chối authentication**: cần kiểm tra danh tính và cấu hình bảo mật.
3. **Đã kết nối nhưng thao tác bị từ chối**: thường là vấn đề authorization ở cấp hành động.

Khi chia sẻ logs, không đưa password, token hoặc nội dung file credential vào ticket. Chỉ ghi loại lỗi, endpoint, thời điểm và phiên bản cấu hình phù hợp.

### 10.1. Không khắc phục bằng cách tắt authentication

Việc đặt thuộc tính tắt authentication để thử nhanh trên máy phát triển không nên trở thành cấu hình production hoặc hướng dẫn mặc định. JMX có thể cho phép gọi operation thay đổi cấu hình, xóa cache hoặc dừng xử lý; đây không phải cổng “chỉ đọc metrics” theo mặc định.

Nếu cần chẩn đoán, ưu tiên một môi trường cô lập, chính sách truy cập tạm thời có giám sát hoặc dùng local debugging do đội vận hành quản lý.

## 11. TLS/SSL handshake

Một remote agent có thể yêu cầu SSL/TLS trong khi client kết nối theo kỳ vọng khác. Một số triệu chứng:

- `javax.net.ssl.SSLHandshakeException`.
- Certificate không được trust.
- Hostname trong certificate không khớp endpoint.
- Client/server không có bộ giao thức hoặc cipher suite tương thích.
- Client authentication được yêu cầu nhưng client không cung cấp certificate.
- Keystore/truststore sai hoặc chưa được JVM quản trị tải.

Các bước kiểm tra:

1. Xác nhận endpoint đang dùng TLS hay không.
2. Kiểm tra chính sách certificate chain và truststore của JConsole/JVM client.
3. Kiểm tra hostname mà client sử dụng với SAN/certificate.
4. Đối chiếu JDK version và TLS protocol hỗ trợ.
5. Xem log handshake có kiểm soát mà không làm lộ secret.
6. Chỉ thay đổi cấu hình theo quy trình bảo mật của hệ thống.

Với RMI/JMX Remote, TLS có thể áp dụng cho những kênh liên quan theo cấu hình connector. Đừng mặc định rằng thử nghiệm kết nối TCP đơn thuần đã chứng minh handshake hoàn chỉnh.

## 12. Firewall, cloud và Kubernetes networking

Một server chạy trong datacenter, cloud hoặc Kubernetes có thể có nhiều lớp lọc:

```text
Client workstation
       |
       v
VPN / corporate network
       |
       v
Cloud security group / firewall
       |
       v
Kubernetes Service / NetworkPolicy
       |
       v
Pod/host listening port
       |
       v
JVM JMX connector
```

Mỗi lớp có thể từ chối một trong các kết nối cần cho RMI. Khi mở kết nối, ưu tiên phạm vi IP nguồn hẹp và endpoint quản trị nội bộ.

Trong Kubernetes, JMX thường phù hợp hơn với một đường truy cập bảo vệ riêng như port-forward hoặc tunnel được phê duyệt, kết hợp cấu hình stub hostname/port phù hợp. Nếu service được load balance qua nhiều pod, cần đảm bảo client tiếp tục kết nối tới cùng backend trong các bước RMI cần thiết; load balancer thông thường không tự giải quyết identity/stub của connector.

Không nên mở một NodePort hoặc public LoadBalancer chỉ để JConsole hoạt động. Những operation JMX được export có thể có side effect rất lớn.

## 13. Thông báo lỗi và cách suy luận

| Triệu chứng | Khả năng nguyên nhân | Kiểm tra ưu tiên |
| --- | --- | --- |
| Connection refused | Không có listener hoặc firewall chủ động từ chối | PID/port/agent startup và kết nối TCP |
| Connection timed out | Route, firewall drop, RMI stub unreachable | Traceroute, port cả hai bước, host quảng bá |
| UnknownHostException | DNS hoặc hostname trong stub không phân giải được | `Resolve-DnsName`, `java.rmi.server.hostname` |
| SSLHandshakeException | Certificate, truststore, protocol hoặc mTLS | TLS config và logs có chọn lọc |
| Authentication failed | Credential hoặc access file | Agent auth config và thông tin đăng nhập |
| RemoteException | RMI invocation/transport, đôi khi endpoint thứ hai | Root cause trong exception |
| JConsole đã kết nối, không thấy Spring MBean | Exporter dùng server khác hoặc chưa export | MBeanServer và `isRegistered` |
| Chỉ lỗi khi kết nối ngoài Docker/K8s | NAT/stub hostname/container IP | Endpoint mà stub quảng bá |
| Lúc được lúc không | DNS/LB, scaling, port đổi, session tới backend khác | Topology và tính ổn định endpoint |

Một lỗi `IOException` chung chưa đủ để kết luận nguyên nhân. Cần xem nested exception, thời điểm, URL thực tế và server logs.

## 14. Phân biệt lỗi JConsole không kết nối với MBean không xuất hiện

Sau khi connector đã mở được:

```java
var connection = connector.getMBeanServerConnection();

System.out.println(connection.getMBeanCount());
System.out.println(connection.getDefaultDomain());
```

Kiểm tra ObjectName:

```java
import javax.management.ObjectName;

ObjectName name = new ObjectName(
    "com.example.monitoring:type=QueueMonitor,name=Primary"
);

System.out.println(connection.isRegistered(name));
```

Nếu `false`, đừng quay lại sửa tường lửa ngay vì client đã có connection. Kiểm tra:

- Spring context có bean và `MBeanExporter` hay không.
- Annotation `@ManagedResource` hoặc naming strategy có tạo đúng ObjectName không.
- MBean đã được đăng ký vào platform server hay private server.
- Registration policy có bỏ qua hoặc thay thế đăng ký không.
- MBean đã unregister khi context đóng chưa.
- Client có đang nối JVM hoặc process khác với dự kiến không.

Một tiến trình JVM có thể chứa nhiều `MBeanServer`. Dù cùng tên ObjectName, hai server là hai registry khác nhau.

## 15. Quy trình chẩn đoán có kiểm soát

### Bước 1 — Thu thập thông tin đích

Ghi nhận hostname, cổng, environment, JVM PID/container/pod, JDK version và kiểu connector. Xác nhận đội vận hành cho phép kết nối từ vị trí mạng của bạn.

### Bước 2 — Xác nhận agent chạy

Kiểm tra JVM arguments/agent startup logs và listener port trên đúng process. Một cổng đang mở không nhất thiết là JMX.

### Bước 3 — Thử TCP

Từ máy JConsole, kiểm tra DNS và TCP đến cổng registry. Nếu fail, tập trung vào network và listener.

### Bước 4 — Xác nhận RMI endpoint

Nếu registry TCP thành công nhưng JConsole fail, kiểm tra RMI server port và hostname được quảng bá. Kiểm tra Docker/Kubernetes/NAT/tunnel mapping.

### Bước 5 — Xác nhận security

Đối chiếu authentication, TLS và access policy; đọc nested exception trên client/server. Không tắt security để “thử cho nhanh” trên production.

### Bước 6 — Kết nối bằng client tối giản

Nếu có quyền, sử dụng một đoạn Java `JMXConnectorFactory.connect` cùng URL và security environment để cô lập vấn đề JConsole UI. Chỉ chạy từ mạng được phép.

### Bước 7 — Kiểm tra MBean

Sau khi thành công, gọi `getMBeanCount`, `getDefaultDomain`, `isRegistered` và `getMBeanInfo`. Nếu Spring MBean không hiện, điều tra cấu hình exporter.

### Bước 8 — Ghi nhận kết quả

Lưu endpoint đã che thông tin nhạy cảm, cấu hình JVM liên quan, loại exception, port check và kết luận của từng bước. Đây là dữ liệu để điều tra tiếp, không phải yêu cầu mở rộng quyền truy cập mặc định.

## 16. Ví dụ tình huống thực tế

### 16.1. Máy chủ vật lý/VM: TCP thành công nhưng JConsole treo

- Registry port 9010 mở.
- RMI stub trỏ tới hostname chỉ phân giải trên server hoặc một port động.
- Client không thể kết nối bước hai.

Hướng giải quyết: xác định RMI port và hostname quảng bá, cấu hình endpoint reachable theo network policy, bảo vệ kết nối bằng security phù hợp.

### 16.2. Docker: JConsole nối vào host port nhưng báo timeout

- Container có port mapping 9010.
- RMI trả về container hostname hoặc IP nội bộ.
- Máy ngoài Docker không truy cập địa chỉ đó.

Hướng giải quyết: thiết kế mapping cả endpoint RMI, cấu hình hostname quảng bá theo vị trí mạng của client; không chỉ chỉnh một biến Spring.

### 16.3. Kubernetes: port-forward hoạt động không ổn định

- Client tới được registry qua port-forward.
- Stub chứa pod IP hoặc RMI port không nằm trong tunnel.
- Kết nối tiếp fail.

Hướng giải quyết: dùng cấu hình port và hostname phù hợp với tunnel, kiểm tra port-forward đường đi cho cả endpoint, hạn chế quyền và bảo vệ transport.

### 16.4. JConsole kết nối thành công nhưng không thấy MBean Spring

- Spring exporter đăng ký vào server do `MBeanServerFactoryBean` tạo.
- JVM management agent dùng platform server.
- JConsole đọc được JVM MXBeans nhưng không thấy private-server MBean.

Hướng giải quyết: dùng cùng server theo kiến trúc hoặc cung cấp connector riêng trỏ vào private server; không coi đây là lỗi firewall.

### 16.5. Chỉ một số tài khoản JConsole kết nối được

- Network và connector đều hoạt động.
- Một account không qua authentication hoặc thiếu quyền theo policy.

Hướng giải quyết: kiểm tra cấu hình credentials/access, logs và yêu cầu quyền tối thiểu. Tránh cấp toàn quyền chỉ để chứng minh lỗi đã hết.

## 17. JMXServiceURL và kết nối có authentication

Một mẫu Java dùng credentials từ nguồn an toàn (không hard-code trong code):

```java
import java.util.HashMap;
import java.util.Map;

import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

JMXServiceURL url = new JMXServiceURL(
    "service:jmx:rmi:///jndi/rmi://jmx.internal.example:9010/jmxrmi"
);

Map<String, Object> environment = new HashMap<>();
environment.put(
    JMXConnector.CREDENTIALS,
    new String[] { usernameFromSecureSource, passwordFromSecureSource }
);

try (JMXConnector connector =
         JMXConnectorFactory.connect(url, environment)) {

    var server = connector.getMBeanServerConnection();
    System.out.println("MBean count = " + server.getMBeanCount());
}
```

`usernameFromSecureSource` và `passwordFromSecureSource` là biến giả định đã lấy từ cơ chế secrets thích hợp. Trong ứng dụng thật phải tránh vô tình ghi credentials vào exception, heap dump hoặc log; phương thức xác thực cũng có thể khác nếu connector dùng JAAS, mTLS hoặc cơ chế riêng.

Đoạn code này chỉ giúp tách lỗi UI JConsole khỏi lỗi connector. Nếu cả Java client lẫn JConsole cùng fail, nhiều khả năng vấn đề nằm ở endpoint, network hoặc security chứ không phải giao diện JConsole.

## 18. Lỗi cấu hình bảo mật và lựa chọn khắc phục

Một số cách “làm cho chạy được” có rủi ro:

- Tắt authentication lâu dài.
- Tắt TLS trên kênh quản trị nằm ngoài mạng tin cậy.
- Mở cổng JMX cho toàn bộ Internet.
- Đặt password trong startup arguments dễ bị nhìn thấy.
- Dùng một tài khoản đặc quyền chung không có accountability.
- Tạo endpoint quản trị công khai không rate limit hoặc audit.
- Bật operation nguy hiểm để thử kết nối.

Thay vào đó:

1. Xác nhận nhu cầu remote JConsole thực sự cần thiết.
2. Dùng network path hạn chế, ví dụ VPN hoặc tunnel được phê duyệt.
3. Bật authentication và TLS theo chính sách bảo mật.
4. Chỉ expose MBean/operation cần thiết.
5. Đảm bảo có quyền truy cập tối thiểu và log audit.
6. Giữ cấu hình nhất quán giữa triển khai, tài liệu và automation.
7. Sau chẩn đoán, thu hồi quyền hoặc cấu hình truy cập tạm thời không còn cần thiết.

**JMX là bề mặt quản trị**, và nhiều MBean có operation thay đổi cấu hình/cache/luồng xử lý. Do đó một lỗi connection không biện minh cho việc hạ mức bảo mật.

## 19. Bài tập thực hành cô lập

Thiết lập một JVM thử nghiệm trong mạng lab được phép, không dùng production:

1. Tạo Spring bean `@ManagedResource` với `@ManagedAttribute` đọc một trạng thái đơn giản.
2. Đăng ký vào platform MBeanServer bằng Spring `MBeanExporter`.
3. Cấu hình JMX Remote với port và RMI port cố định, authentication/TLS theo môi trường lab.
4. Từ máy client, kiểm tra DNS và registry TCP.
5. Kết nối JConsole bằng endpoint chính xác.
6. Đọc JVM MXBeans và MBean Spring.
7. Thay hostname quảng bá sang giá trị không reachable trong môi trường lab, quan sát kiểu lỗi.
8. Khôi phục cấu hình đúng, kết nối lại và xác nhận.
9. Thử tình huống credentials không hợp lệ để phân biệt security failure với network failure.
10. Đổi exporter sang MBeanServer riêng và giải thích vì sao Spring MBean có thể không xuất hiện khi JConsole vẫn nối platform server.

Trong lab, khi gây lỗi có chủ đích, không mở mạng quản trị rộng ra ngoài. Dọn connector và cấu hình tạm thời khi bài thực hành kết thúc.

## 20. Câu hỏi tự kiểm tra

**1. Có MBean trong Spring là JConsole remote tự kết nối được không?** Không; cần connector và mạng/security hoạt động.

**2. Vì sao kiểm tra registry TCP thành công mà JConsole vẫn timeout?** Vì RMI có thể yêu cầu bước kết nối tiếp tới hostname/port được stub quảng bá.

**3. `java.rmi.server.hostname` ảnh hưởng gì?** Hostname được quảng bá cho client trong RMI stub.

**4. Tại sao Docker/Kubernetes thường gây rắc rối cho JMX RMI?** Vì NAT/container IP/pod DNS và mapping port có thể không trùng địa chỉ mà client từ ngoài nhìn thấy.

**5. `MBeanServerFactoryBean` có tự bật remote port không?** Không, nó cung cấp MBeanServer chứ không tự tạo endpoint mạng.

**6. Kết nối JConsole thành công nhưng thiếu Spring MBean cần kiểm tra gì?** Exporter dùng MBeanServer nào, ObjectName nào và MBean có đăng ký không.

**7. Lỗi SSLHandshakeException nên xử lý ở đâu?** Kiểm tra TLS/certificate/truststore/protocol của client và server.

**8. Có nên tắt authentication để giải quyết lỗi remote không?** Không nên ở production; cần chẩn đoán credential/policy đúng cách.

**9. Timeout có chứng minh operation JMX chưa chạy không?** Không; phải kiểm tra trạng thái thực tế trước khi retry.

**10. Khi client không resolve hostname trong RMI stub, thay annotation Spring có giúp không?** Không. Đây là lỗi địa chỉ và kết nối transport.

## 21. Ghi nhớ

- **Spring MBeanExporter không đồng nghĩa JMX Remote connector**.
- **Kết nối thất bại** và **kết nối được nhưng thiếu MBean** là hai nhóm sự cố khác nhau.
- Với JMX RMI, phải kiểm tra **registry + RMI endpoint**, không chỉ một TCP port.
- **Hostname trong RMI stub** phải reachable từ máy JConsole.
- **Docker/NAT/Kubernetes/tunnel** có thể làm endpoint quảng bá sai đường đi.
- **Authentication/TLS** là thành phần thiết yếu của truy cập JMX từ xa, không phải tùy chọn nên tắt khi gặp lỗi.
- **MBeanServer đúng** là điều kiện để nhìn thấy bean Spring sau khi kết nối.
- Quy trình hiệu quả là kiểm tra lần lượt **process → listener → DNS/TCP → RMI stub → security → MBeanInfo**.
- Dùng log và kết quả kiểm tra để xác định giả thuyết, tránh sửa nhiều cấu hình cùng lúc.
- Bảo vệ JMX như một **control plane đặc quyền**, bởi operation có thể thay đổi hành vi ứng dụng.

Khi JConsole không kết nối được tới remote server, hãy xử lý theo từng lớp từ network tới JMX connector, rồi mới xét Spring exporter. Việc tách bạch transport, security và MBean registry giúp tìm nguyên nhân nhanh hơn và tránh những thay đổi cấu hình có thể làm lộ bề mặt quản trị của hệ thống.