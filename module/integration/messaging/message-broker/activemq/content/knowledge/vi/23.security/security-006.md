# Cô lập mạng cho cổng giao thức, console, JMX và Jolokia

> **Chương:** Bảo mật  
> **Phạm vi:** Apache ActiveMQ Classic và Apache ActiveMQ Artemis. Bài tập trung vào **ranh giới mạng** của bốn bề mặt: protocol listeners, web console, Java Management Extensions (**JMX**) và Jolokia HTTP API. Ví dụ gồm XML cho broker, Docker Compose, Kubernetes NetworkPolicy, kiểm tra truy cập và runbook vận hành. Các mục authentication, authorization và TLS được đề cập đúng mức để chứng minh **cô lập mạng không thể thay thế kiểm soát danh tính và quyền**.

Một broker có thể chấp nhận JMS message chỉ trên mạng ứng dụng, đồng thời để lộ trang quản trị hoặc endpoint JMX/Jolokia ra Internet. Lỗi cấu hình này không được khắc phục bằng việc chỉ thêm username/password cho producer: kẻ tấn công có thể dò chức năng quản trị, đọc metadata nhạy cảm, thay đổi hàng đợi hoặc gây gián đoạn xử lý nếu còn lỗ hổng ở tầng console/management.

Mục tiêu của bài không phải “đóng tất cả các cổng”, mà là **cấp đúng đường kết nối cho đúng chủ thể**: application chỉ được đến protocol endpoint cần thiết; SRE/automation được đến management plane qua một kênh kiểm soát; client ngoài không được thấy console, JMX và Jolokia. Tất cả ví dụ dùng **địa chỉ, cổng và domain giả lập dành cho lab**, phải điều chỉnh theo topology thật.

## 1. Lập danh mục bề mặt mạng trước khi đặt firewall

Các cổng dưới đây là **giá trị thường gặp hoặc giá trị ví dụ**, **không phải cấu hình bắt buộc** của mọi bản Classic/Artemis. Cổng nào thực sự mở phụ thuộc listener, bootstrap, JVM flags, plugin và deployment.

| Bề mặt | Giao thức/endpoint thường gặp | Mục đích | Chủ thể được phép kết nối |
|---|---|---|---|
| **JMS/Message protocol** | Core/OpenWire qua TCP, ví dụ **61616** | Producer, consumer, broker client | Chỉ application workload / integration gateway được duyệt |
| **AMQP 1.0** | TCP/TLS, thường **5672** khi cấu hình riêng | Ứng dụng AMQP | Chỉ client AMQP đã được cấp quyền |
| **STOMP/MQTT** | STOMP **61613**, MQTT **1883** khi được bật | Client theo protocol tương ứng | Chỉ nguồn cần dùng; tắt nếu không có |
| **WebSocket messaging** | WS/WSS listener hoặc reverse proxy | Client web/protocol được cho phép | Chỉ gateway/browser domain theo thiết kế, TLS/WSS |
| **Web console** | HTTP(S), thường **8161** | Hawtio/Artemis Console hoặc Classic web console | SRE/operator qua VPN, bastion, port-forward |
| **Jolokia** | HTTP(S) endpoint trong web console hoặc agent riêng | REST bridge tới JMX/MBean | Chỉ hệ quản trị/monitoring đã cấp quyền |
| **JMX remote** | RMI registry và RMI connector ports do JVM cấu hình, ví dụ **1099** | MBean monitoring, thao tác quản trị | Chỉ management host hoặc local attach |

**Jolokia không phải mặc nhiên là “một port JMS khác”.** Trong nhiều cài đặt, Jolokia chạy **bên trong web container phục vụ console**, do đó chia sẻ listener HTTP(S) (ví dụ 8161) nhưng có **URL path và chính sách quyền** riêng. Nếu chạy một Jolokia JVM agent độc lập, nó có thể mở **cổng riêng**: phải đưa cả cổng đó vào asset inventory.

**JMX từ xa cũng không đồng nghĩa TCP 1099 duy nhất.** Với JMX/RMI, RMI registry là một endpoint; stub có thể chỉ tới **RMI server port khác**, có khi là cổng động. Chỉ mở 1099 mà không xác định RMI port có thể khiến đăng nhập registry thành công nhưng kết nối JMX thất bại.

### 1.1. Bốn miền tin cậy nên tách biệt

~~~mermaid
flowchart LR
    EXT["Internet / mạng không tin cậy"]
    APP["Application workloads<br/>producer / consumer"]
    OPS["Operator / SRE<br/>VPN + bastion"]
    MON["Monitoring service<br/>least privilege"]
    P["Broker protocol listener<br/>61616 private"]
    WEB["Console + Jolokia<br/>8161 management only"]
    JMX["Remote JMX/RMI<br/>nếu thật sự bật"]
    EXT -. "DENY" .-> P
    EXT -. "DENY" .-> WEB
    EXT -. "DENY" .-> JMX
    APP -->|"ALLOW protocol"| P
    OPS -->|"ALLOW via protected path"| WEB
    OPS -->|"ALLOW only if needed"| JMX
    MON -->|"Scoped management access"| WEB
~~~

Đây là **logical trust zones**, không nhất thiết phải triển khai thành bốn VLAN. Có thể hiện thực bằng security groups, firewall, Kubernetes NetworkPolicy, service mesh authorization hoặc route qua bastion. Điều bắt buộc là **đường đi thực tế phải tuân theo ma trận cho phép**, kể cả từ một container/pod hoặc host khác trong cùng private network.

### 1.2. Nguyên tắc least exposure

1. **Đóng theo mặc định**, chỉ cho phép nguồn, đích, cổng và giao thức cần thiết.
2. **Tắt các protocol listener không sử dụng**; không mở đủ AMQP, MQTT, STOMP, WebSocket chỉ vì bản phân phối có sẵn.
3. **Bind vào địa chỉ phù hợp** thay vì tất cả interfaces khi có thể; kiểm chứng IP thực của máy/pod.
4. **Console, Jolokia, JMX không đi cùng quyền truy cập ứng dụng**: workload được gửi JMS chưa chắc được phép quản trị.
5. **TLS/mTLS và ACL vẫn bắt buộc** khi cần: private subnet không tự xác thực chủ thể.
6. **Tách quyền đọc và quyền thay đổi** cho monitoring, operations, support.
7. **Kiểm thử từ cả vị trí được phép và vị trí bị cấm**; nhìn một dòng config “localhost” chưa đủ chứng minh không bị proxy/port publish ra ngoài.
8. **Quan sát kết nối và thay đổi** bằng audit log, firewall logs, management access logs và configuration inventory.

## 2. Thiết kế ma trận truy cập trước khi sửa broker

Một ma trận mẫu cho môi trường production:

| Nguồn | Đích | Transport/port | Chính sách |
|---|---|---|---|
| **orders-service** | Artemis Orders | Core/TLS **61617** (ví dụ) | **ALLOW** qua private network; auth + TLS |
| **billing-worker** | Artemis Billing | Core/TLS **61617** (ví dụ) | **ALLOW** theo đúng SG/namespace |
| **orders-service** | Broker console **8161** | HTTP(S) admin | **DENY** |
| **billing-worker** | JMX **1099** | RMI management | **DENY** |
| **Internet** | Bất kỳ broker protocol/console/JMX | Mọi cổng | **DENY** |
| **SRE bastion/VPN** | Console **8161** | HTTPS hoặc tunnel an toàn | **ALLOW** có identity/RBAC |
| **Monitoring agent đã duyệt** | Jolokia/management endpoint | HTTPS riêng | **ALLOW** read-only/scoped |
| **SRE qua local attach** | Local broker JVM | Không cần remote JMX TCP | **PREFER** nếu phù hợp |

**Các port 61617/8161/1099 chỉ là số ví dụ.** Nếu hệ thống dùng 61616 cho Core + TLS, hoặc nhiều giao thức đi qua cùng Netty acceptor, thay giá trị trong ma trận dựa trên **cấu hình thực** và account inventory.

### 2.1. Vì sao chỉ “private IP” chưa đủ?

Một broker nghe trên **10.40.10.12:61616** không tự ngăn mọi host khác cùng VPC/VNet truy cập. Nếu security group mở cho cả **10.0.0.0/8**, một service bị xâm nhập ở subnet không liên quan có thể thử kết nối broker. Vùng private cần chia theo **workload identity, subnet, namespace và source security group**, không phải chỉ “không có public IP”.

Một broker chạy ở Kubernetes sau **Service type ClusterIP** cũng không được coi là an toàn tuyệt đối: mọi pod có tuyến truy cập trong cluster có thể thử kết nối, trừ khi **NetworkPolicy/CNI/authorization** thực sự giới hạn.

## 3. Cô lập cổng giao thức của ActiveMQ Classic

Classic thường cấu hình network listeners trong **conf/activemq.xml**, mục **transportConnectors**. Mỗi connector mở một transport/protocol endpoint; danh sách thực tế khác nhau tùy broker instance và phiên bản.

Ví dụ chỉ cho OpenWire từ network ứng dụng qua một interface riêng:

~~~xml
<!-- Fragment bên trong <broker> của Classic activemq.xml -->
<transportConnectors>
    <transportConnector
        name="openwire-private"
        uri="tcp://10.40.10.12:61616"/>
</transportConnectors>
~~~

Trong ví dụ, **10.40.10.12 phải là IP đang được gán cho host**. Bind một IP không tồn tại sẽ làm listener lỗi. Nếu host có management interface và application interface riêng, hãy bind OpenWire vào **application interface**, sau đó kết hợp firewall/security group chỉ cho workload được duyệt.

**Một listener bind 10.40.10.12 không tự được mã hóa.** TCP trong ví dụ là plaintext. Khi có đường mạng không hoàn toàn tin cậy hoặc cần chính sách bảo vệ traffic, dùng **TLS connector** được cấu hình đúng keystore/truststore, hostname verification và role/credential. Mô hình Classic thường dùng transport SSL tương ứng như **ssl://...**; không chỉ đổi URI mà bỏ phần thiết lập TLS.

### 3.1. Không bật protocol chỉ vì bản cài có ví dụ

Các connector khác có thể xuất hiện trong bản mẫu Classic:

~~~xml
<!-- Chỉ minh họa sự tồn tại của các connector riêng;
     KHÔNG thêm các dòng này nếu không có client tương ứng. -->
<transportConnector name="stomp" uri="stomp://10.40.10.12:61613"/>
<transportConnector name="mqtt" uri="mqtt://10.40.10.12:1883"/>
~~~

Mỗi cổng mở thêm là một bề mặt kiểm tra authentication, parser và resource limits. Nếu ứng dụng chỉ dùng OpenWire, **không cần STOMP/MQTT/WebSocket**. Nếu cần nhiều protocol, cấp network policy theo **client nguồn cụ thể**, không mở wildcard toàn bộ workload.

### 3.2. Broker protocol ports và web console không cùng cấu hình

Sửa **transportConnectors** trong activemq.xml **không tự đóng Jetty web console**. Tương tự, tắt web console **không tự dừng JMS listener**. Đây là hai mặt phẳng khác nhau, cần quản trị riêng.

Một triển khai Classic có thể dùng **Jetty** với cấu hình host/port trong **conf/jetty.xml** và các thành phần liên quan. Không chỉ tìm chuỗi **61616** rồi kết luận broker không còn port quản trị.

## 4. Cô lập Netty acceptors của ActiveMQ Artemis

Artemis khai báo protocol endpoints bằng **acceptors** trong **broker.xml**. Cùng một Netty acceptor có thể được cấu hình cho **một hoặc nhiều giao thức**; nếu cho phép nhiều protocol trên cùng cổng, firewall **không thể phân biệt** các protocol dựa vào số port đó.

Ví dụ chỉ mở **Core protocol** trên private IP:

~~~xml
<!-- Fragment trong phần <acceptors> của Artemis broker.xml -->
<acceptors>
    <acceptor name="app-core">tcp://10.40.10.22:61616?protocols=CORE</acceptor>
</acceptors>
~~~

**Ghi chú triển khai:**

- **10.40.10.22** phải tồn tại trong network namespace của broker.
- **protocols=CORE** giới hạn protocol được acceptor xử lý theo cấu hình Artemis tương ứng.
- Nếu thực sự có AMQP clients, cân nhắc một **acceptor riêng** cho AMQP trên private port khác và ACL riêng theo nguồn; không mặc định dùng nhiều protocol trên cổng 61616.
- Nếu cần TLS, cấu hình **sslEnabled**, certificate/truststore và client policy theo version Artemis; không coi private TCP là encrypted.
- Định dạng acceptor parameters và hỗ trợ protocol phụ thuộc broker/client version; kiểm tra server log sau khi restart/reload.

### 4.1. Vì sao tách acceptor giúp phân vùng quyền?

So sánh hai thiết kế:

~~~text
Thiết kế 1:
  0.0.0.0:61616 → CORE + AMQP + STOMP + MQTT + OPENWIRE
  → cùng một allowlist network phải đủ cho tất cả protocol

Thiết kế 2:
  private-a:61616 → CORE, chỉ Java worker
  private-b:5672  → AMQP, chỉ gateway AMQP
  không cấu hình MQTT/STOMP nếu không có nhu cầu
~~~

Thiết kế 2 giúp firewall/security group gắn quyền theo **port và nhóm client**, nhưng **không thay thế** role authorization trên queue/address. Nếu một client được vào CORE listener nhưng tài khoản chỉ được phép consume một queue, broker vẫn phải kiểm tra quyền đó.

### 4.2. Địa chỉ 0.0.0.0 trong container có luôn sai?

Không. Trong Docker/Kubernetes, broker đôi khi cần bind **0.0.0.0 bên trong container/pod** để Service hoặc port mapping nhận được kết nối. Nguy hiểm xảy ra khi cùng lúc:

- Publish host port ra **0.0.0.0 trên mọi interface của node**;
- Tạo LoadBalancer/NodePort/Ingress công khai;
- Không có security group/NetworkPolicy;
- Console/Jolokia cũng bind mọi interface.

Hãy phân biệt **bind address trong container** với **địa chỉ được publish ở host/cloud edge**. Kiểm tra cả hai lớp thay vì áp mẹo “bind 127.0.0.1 cho mọi thứ” làm mất khả năng kết nối hợp lệ từ pod khác.

## 5. Web console: tách đường quản trị khỏi đường JMS

Web console cung cấp chức năng quan sát và đôi khi thay đổi trạng thái broker: xem queue, message, connections, producers/consumers, thao tác quản trị qua MBean hoặc APIs. Do đó console cần **management zone**, không nên mở cùng allowlist với application producers.

### 5.1. ActiveMQ Classic: kiểm tra Jetty web endpoint

Classic thường có Jetty console ở port **8161** và cấu hình trong file liên quan **jetty.xml**. Ở một số bản phân phối, bean **WebConsolePort** xác định host và port:

~~~xml
<!-- Fragment minh họa trong conf/jetty.xml của Classic;
     kiểm tra cấu trúc thực tế theo phiên bản đang chạy. -->
<bean id="jettyPort"
      class="org.apache.activemq.web.WebConsolePort"
      init-method="start">
    <property name="host" value="127.0.0.1"/>
    <property name="port" value="8161"/>
</bean>
~~~

Nếu Classic instance của bạn sử dụng Jetty config khác, phải sửa **connector thực sự đang dùng**, không tạo bean thứ hai trùng tên. Sau thay đổi, kiểm tra socket đang listen và thử từ host ngoài.

**Bind 127.0.0.1** phù hợp khi người vận hành truy cập qua **SSH port-forward/bastion** hoặc local access. Nếu console cần phục vụ trong private operations subnet, có thể bind management interface riêng và dùng HTTPS + firewall + identity controls; **không cần public IP**.

### 5.2. ActiveMQ Artemis: console thường thuộc web bootstrap

Artemis instance thường có file **etc/bootstrap.xml** khai báo web server/console. Ví dụ cấu trúc minh họa:

~~~xml
<!-- Fragment bootstrap.xml; khi triển khai thực phải giữ nguyên
     các <app .../> và phần còn lại do instance tạo ra. -->
<web bind="http://127.0.0.1:8161" path="web">
    <!-- Giữ các app console/branding/plugins của instance hiện tại -->
</web>
~~~

Mấu chốt là thuộc tính **bind** của **web endpoint**, **không phải acceptor CORE ở broker.xml**. Không thay toàn bộ bootstrap.xml bằng fragment này: console của phiên bản hiện tại có thể yêu cầu các app/branding/plugin đã khai báo trước đó.

Với yêu cầu quản trị từ xa, nên dùng **TLS trên management network, reverse proxy được harden hoặc tunnel được kiểm soát**. Nếu để HTTP trên loopback và dùng SSH tunnel, lưu lượng trên đường từ operator tới host được bảo vệ bởi SSH; đừng mở HTTP loopback qua reverse proxy công khai.

### 5.3. Console authentication không đủ để bỏ firewall

Ngay cả khi trang login yêu cầu username/password:

- Pre-auth endpoints vẫn tiếp nhận traffic, chịu ảnh hưởng DoS và những lỗi thuộc web stack.
- Session cookies, CSRF, route misconfiguration và plugin còn là bề mặt rủi ro.
- Một lần lộ credential operator không nên tự cho phép truy cập từ mọi địa chỉ trên Internet.
- Quyền **admin**, **browse/read** và **monitoring** cần tách theo khả năng broker và phiên bản.
- Access logs phải ghi ai truy cập, từ đâu, làm gì; tránh lưu password/token.

**Không đặt console/Jolokia vào cùng public Ingress dùng cho ứng dụng web** chỉ vì reverse proxy đã có sẵn TLS.

## 6. JMX: mặc định ưu tiên local, remote phải quản trị cả RMI

JMX cung cấp quyền đọc và đôi khi thao tác quản trị thông qua MBeans. Một số operations có thể ảnh hưởng trực tiếp đến queue và broker; vì vậy **JMX không phải monitoring endpoint vô hại**.

### 6.1. Local JMX khác remote JMX

**Local attach/JMX:** công cụ chạy trên cùng host/namespace với JVM, dùng cơ chế local JVM attach khi được cho phép. Không cần công khai một JMX/RMI endpoint ra mạng ứng dụng.

**Remote JMX:** JVM mở remote management agent. Khi đó phải quan tâm đồng thời:

- Port cho **RMI registry/JMX connector**.
- Port của **RMI server endpoint** mà client được hướng tới.
- **Hostname/IP nhúng trong RMI stub**, phải resolvable và routable từ management client.
- TLS, authentication, quyền MBean, firewall, certificate và credential storage.

Nếu không có nhu cầu remote JMX thực tế, **không bật remote JMX**. Có thể dùng management API hoặc metrics exporter đã được phân quyền qua một kênh khác, tránh mở thêm RMI.

### 6.2. Vì sao “đã mở port 1099 mà JConsole vẫn lỗi”?

~~~mermaid
sequenceDiagram
    participant J as JConsole / JMX client
    participant R as RMI registry
    participant S as RMI server endpoint
    J->>R: Kết nối registry port 1099
    R-->>J: Trả về RMI stub: hostname + server port
    J->>S: Kết nối theo stub
    Note over J,S: Nếu server port động/chặn hoặc hostname sai → fail
~~~

**Chỉ allow 1099 trong firewall chưa đủ** nếu server port là cổng khác hoặc hostname trong stub không thể đến được. Một cấu hình remote JMX được thiết kế bài bản thường **pin RMI port**, ràng buộc đường quản trị, bật authentication và TLS.

Ví dụ các **JVM system properties** cần phối hợp khi có remote JMX được duyệt:

~~~properties
# Đây là mẫu xác định bề mặt cấu hình, KHÔNG phải
# một bộ JVM flags có thể dùng nguyên xi.
-Dcom.sun.management.jmxremote
-Dcom.sun.management.jmxremote.port=1099
-Dcom.sun.management.jmxremote.rmi.port=1099
-Dcom.sun.management.jmxremote.authenticate=true
-Dcom.sun.management.jmxremote.ssl=true
-Dcom.sun.management.jmxremote.password.file=/etc/mq/jmxremote.password
-Dcom.sun.management.jmxremote.access.file=/etc/mq/jmxremote.access
-Djavax.net.ssl.keyStore=/etc/mq/jmx-server.p12
-Djavax.net.ssl.keyStoreType=PKCS12
-Djava.rmi.server.hostname=10.40.20.10
~~~

**Bắt buộc hoàn thiện trước khi bật:** file password/access có owner và permission chặt, keystore đúng certificate/private key và cơ chế cấp mật khẩu keystore an toàn, CA trust ở client, RMI hostname đúng management interface, firewall chỉ cho phép nguồn SRE. Không đưa mật khẩu vào tài liệu, process command line, source control hoặc URL.

Nếu dùng **cùng port cho registry và RMI server**, phải kiểm thử chính xác trên JDK/JVM đang triển khai. Nếu có hai port, mở **cả hai** nhưng **chỉ từ management subnet**. Firewall không thay TLS/authentication.

### 6.3. Nguy cơ mở JMX remote trên mọi interface

**java.rmi.server.hostname** là địa chỉ mà RMI stub công bố, **không mặc nhiên giới hạn socket server bind vào interface đó**. Kiểm tra listener thực tế bằng công cụ OS, chính sách firewall và test từ nguồn bị cấm. Một kết nối có thể bị từ chối ở tầng identity nhưng port vẫn mở tới một mạng không mong muốn.

Đối với broker container/pod, nếu cần remote JMX, còn phải tính **pod IP/host IP, NAT, Kubernetes Service và routing của RMI stub**. Vì độ phức tạp này, với môi trường Kubernetes thường nên cân nhắc **agent metrics/exporter được giới hạn quyền** hoặc management tunnel thay vì mở remote JMX rộng.

### 6.4. JMX và broker authorization là hai lớp khác nhau

Một tài khoản JMS có quyền gửi message lên queue không nhất thiết được quyền gọi **MBean administrative operations**. Phải kiểm tra **JMX/Jolokia authorization** và cơ chế quản trị của broker. Với Artemis, management có thể còn được truy cập qua **management messages/addresses** trên broker protocol khi user được cấp quyền tương ứng: **đóng web/JMX không thay thế phân quyền management API trên cổng JMS**.

## 7. Jolokia: REST management thường dùng chung cổng web

Jolokia expose một phần tính năng JMX qua HTTP(S), thường ở một đường dẫn thuộc web console/Hawtio. Nó có thể cho phép client đọc attributes và thực hiện operations tùy security policy, phiên bản và quyền của ứng dụng.

**Hai câu không được đánh đồng:**

- “Đã đóng remote JMX/RMI” **không có nghĩa Jolokia đã bị đóng**.
- “Jolokia nằm dưới /console hoặc /api” **không có nghĩa endpoint chỉ cho phép đọc**.

### 7.1. Tìm đúng endpoint triển khai

| Sản phẩm/kiểu triển khai | Nơi Jolokia thường xuất hiện | Cần xác minh |
|---|---|---|
| **Classic web console/Jetty** | HTTP(S) endpoint dưới web app, thường có dạng **/api/jolokia/** | URL path/context thực của version, auth và Jetty bind |
| **Artemis Console/Hawtio** | Jolokia endpoint cùng web server với console, path tùy bản phát hành | Đường dẫn cụ thể, app deployment, realm/RBAC |
| **Jolokia agent độc lập** | Có thể mở một listener HTTP(S) riêng | Port, bind, policy, auth/TLS và owner |

**Không hardcode URL Jolokia từ một bài hướng dẫn cũ** rồi mở port để “làm cho request hoạt động”. Trước hết đọc cấu hình web ứng dụng hiện tại và kiểm tra listener/route **trong môi trường được phép**.

### 7.2. Cô lập ở hai lớp: network và API permissions

**Lớp mạng:** chỉ cho phép SRE/monitoring có thẩm quyền đến web endpoint. Nếu console và Jolokia cùng port, **firewall L4 không thể mở Jolokia cho monitoring mà đóng console theo path**. Muốn tách quyền theo HTTP path có thể dùng reverse proxy/gateway có authentication, authorization và allowlist chính xác; rủi ro cấu hình proxy phải được kiểm thử.

**Lớp ứng dụng:** bật và kiểm chứng:

- Authentication/role-based authorization của console/Jolokia theo phiên bản.
- Policy/restrictor cho các MBeans, operations, attributes được phép.
- Read-only monitoring identity; operator/admin identity riêng.
- Hạn chế CORS/Origin; không dùng **allow-origin \*** một cách vô điều kiện.
- CSRF/session protection khi có UI browser, cùng cookie/security headers phù hợp.
- HTTP request size/rate limits và access logs; không dump credentials hoặc message payload nhạy cảm vào log.

**Dữ liệu quan sát được qua MBean có thể nhạy cảm**: tên destination, địa chỉ broker, connection metadata và một số nội dung message. Đừng xem “chỉ read attribute” là không cần authorization.

### 7.3. Kiểm thử chức năng Jolokia có kiểm soát

Trên management host đã được cho phép:

~~~bash
# Ví dụ probe đường dẫn Classic đã được kiểm chứng trong deployment.
# Chỉ xem HTTP status/headers, không gửi operation thay đổi trạng thái.
curl --silent --show-error --include \
  --max-time 3 "https://mq-admin.example.internal/api/jolokia/"

# Với Artemis, dùng URL path thực từ cấu hình console hiện hành.
# Nếu ở loopback qua SSH port-forward, truy cập 127.0.0.1 local.
~~~

Tùy policy, một request **không có credentials** nên nhận **401/403**, redirect tới login hoặc bị chặn ở reverse proxy; **không được coi response 200 chứa dữ liệu quản trị là tiêu chí thành công**. Muốn chứng minh role monitoring thực sự read-only, dùng tài khoản test có quyền hẹp và thử một operation đã được chuẩn bị **không phá dữ liệu** trong sandbox, không chạy queue purge/move trên production.

**Quan trọng:** URL **mq-admin.example.internal** là tên giả lập, không phải đích cần gọi thật. Không copy probe để truy vấn hạ tầng không thuộc quyền sở hữu.

## 8. Docker/Compose: bind host khác bind container

Một lỗi phổ biến: broker trong container nghe **0.0.0.0:61616**, Docker lại publish **61616:61616** trên mọi host interfaces; hoặc publish luôn **8161:8161** cho console.

### 8.1. Port mapping an toàn cho lab local

~~~yaml
services:
  artemis:
    image: "your-approved-artemis-image:version"
    # Các biến môi trường/volumes phụ thuộc image được tổ chức dùng.
    ports:
      - "127.0.0.1:61616:61616"
      - "127.0.0.1:8161:8161"
    networks:
      - messaging-private

networks:
  messaging-private:
    driver: bridge
~~~

**Chỉ là ví dụ mapping**, không phải Compose đầy đủ để khởi chạy một image bất kỳ. Nó công bố hai cổng trên **loopback của host**, thay vì mọi interface. Để port mapping hoạt động, service bên trong container phải bind vào interface có thể đi tới được từ Docker bridge, thường **0.0.0.0 trong container**. Nếu broker chỉ bind **127.0.0.1 bên trong container**, việc publish từ host có thể không kết nối được.

**Không vì vậy kết luận console đã được bảo vệ hoàn toàn.** Các container cùng network vẫn có thể kết nối tới port nội bộ; mạng bridge và Docker host access phải được kiểm soát. Loopback host mapping cũng không ngăn mọi tiến trình **trên chính host** truy cập, và các chế độ host networking có semantics khác.

### 8.2. Khi triển khai nhiều container cùng một network

Nếu một container Java service cần Artemis, trong Compose có thể dùng service name **artemis:61616** trên private network mà **không publish 61616 ra host**. Với console, ưu tiên không publish hoặc chỉ publish host loopback khi có nhu cầu vận hành. Không thêm **privileged**, **network_mode: host** hoặc port mapping wildcard để chữa một lỗi DNS/connection chưa được phân tích.

## 9. Kubernetes: Service nội bộ và NetworkPolicy allowlist

**Service type ClusterIP** chỉ nghĩa là không tạo LoadBalancer/NodePort công khai theo mặc định. Nó không tự ngăn pod khác trong cluster gọi broker Service/pod IP. **NetworkPolicy** là lớp lọc pod traffic, chỉ có tác dụng khi **CNI/network implementation hỗ trợ và thực thi**.

### 9.1. Chỉ công bố cổng protocol qua ClusterIP

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: artemis-orders
  namespace: messaging
spec:
  type: ClusterIP
  selector:
    app: artemis-orders
  ports:
    - name: core
      protocol: TCP
      port: 61616
      targetPort: 61616
~~~

Service này **không expose web console/JMX** qua port của Service. Tuy nhiên pod có thể vẫn listen trên các port khác; phải có NetworkPolicy/host firewall và kiểm tra trực tiếp pod network. Việc không liệt kê 8161 trong Service **không đủ** để khẳng định 8161 không thể được truy cập bằng pod IP.

### 9.2. Chính sách chỉ cho phép Orders worker vào Core port

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: orders-broker-ingress
  namespace: messaging
spec:
  podSelector:
    matchLabels:
      app: artemis-orders
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: app-workloads
          podSelector:
            matchLabels:
              app: orders-worker
      ports:
        - protocol: TCP
          port: 61616
~~~

**Giải thích semantics:**

- Policy chọn **pod app=artemis-orders** trong namespace **messaging**.
- Chỉ traffic đến **TCP 61616** từ pod **app=orders-worker** trong namespace **app-workloads** được policy này cho phép.
- **namespaceSelector và podSelector trong cùng một phần tử from** có quan hệ **AND**: cả namespace lẫn pod labels phải khớp.
- Các ingress khác tới broker pod bị từ chối **nếu không có policy khác cho phép**. NetworkPolicies có semantics **cộng gộp allow rules**; một policy khác có thể mở thêm 8161, vì vậy phải kiểm tra **toàn bộ effective policies**.
- Policy trên chỉ giới hạn **Ingress** của broker pod. Nó **không tự quản lý egress** từ broker hoặc từ app pods; nếu cần cô lập chiều đi, viết egress policies tương ứng.
- Kubernetes NetworkPolicy không phải authentication/authorization của JMS; username/permissions broker vẫn phải được cấu hình.

Nếu dùng namespace labels tự đặt thay vì nhãn chuẩn **kubernetes.io/metadata.name**, cần kiểm tra namespace thực sự mang label đó. Cũng cần kiểm tra CNI có thực thi NetworkPolicy, tránh deploy YAML thành công nhưng traffic vẫn không bị chặn.

### 9.3. Console/Jolokia trong Kubernetes nên truy cập thế nào?

Ưu tiên một đường quản trị được kiểm soát bởi **RBAC, Kubernetes API audit, VPN/bastion hoặc private ingress**. Ví dụ với quyền port-forward được cấp:

~~~bash
# Chạy trên máy quản trị có kubectl và quyền RBAC phù hợp.
kubectl -n messaging port-forward pod/artemis-orders-0 8161:8161
~~~

Sau đó operator mở **http://127.0.0.1:8161/** hoặc path console phù hợp từ máy local, trong điều kiện broker web server ở pod có listener phục vụ port đó. **Port-forward qua Kubernetes API không thay thế authentication của console.** Quyền **pods/portforward** có thể tạo đường vào quản trị ngay cả khi không expose Service, vì thế cần được giới hạn và audit.

Trong nhiều môi trường, **pod name không cố định** hoặc pod chưa phải ready; thay tên trong ví dụ bằng pod thực tế. Không bật Ingress công khai chỉ vì việc port-forward chưa được cấp quyền.

## 10. Cách xác minh mạng không chỉ dựa vào file cấu hình

Sau khi thay đổi binding, firewall hoặc NetworkPolicy, luôn kiểm chứng từ **ba vị trí**: trên broker, từ application được phép, và từ host/pod không được phép.

### 10.1. Đọc socket listeners trên broker host (Linux)

~~~bash
# Trên host/namespace của broker, xem listeners đang hoạt động.
ss -lntp

# Quan sát riêng các port ví dụ khi cần:
ss -lntp | grep -E '61616|61617|8161|1099'
~~~

Đọc cả **local address** của từng listener:

~~~text
127.0.0.1:8161     → chỉ loopback của network namespace đó
10.40.10.22:61616  → interface private đã chọn
0.0.0.0:61616      → mọi IPv4 interfaces của namespace đó
[::]:8161          → IPv6 wildcard (semantics dual-stack tùy OS)
~~~

Cần kiểm tra **IPv4 và IPv6**. Đóng listener IPv4 nhưng để cùng dịch vụ nghe **[::]** có thể vẫn tạo đường truy cập ngoài ý muốn. Trên Windows, có thể dùng **Get-NetTCPConnection** hoặc công cụ tương đương; cùng một nguyên tắc đọc local address + owning process.

### 10.2. Kiểm thử kết nối từ nguồn được phép

Trên một application pod đã được allowlist:

~~~bash
# Dùng TCP probe đơn giản; không chứng minh JMS auth.
nc -vz -w 3 artemis-orders.messaging.svc.cluster.local 61616
~~~

Sau probe TCP, phải dùng **Java/JMS client thực** với đúng TLS/auth và thực hiện một **send/receive vào queue test**, có timeout và không tạo side effect nghiệp vụ. TCP “open” không chứng minh Core/OpenWire/AMQP authentication, authorization hoặc TLS handshake thành công.

### 10.3. Kiểm thử từ nguồn không được phép

Từ một pod không mang label **orders-worker**, hoặc từ ops host không được phép:

~~~bash
nc -vz -w 3 artemis-orders.messaging.svc.cluster.local 61616
nc -vz -w 3 artemis-orders.messaging.svc.cluster.local 8161
~~~

**Kỳ vọng:** kết nối bị chặn/refused/timeout theo cách policy và network stack áp dụng. Nếu TCP 8161 mở, điều tra **NetworkPolicy khác, pod IP direct path, hostNetwork, Service/Ingress/LB, sidecar, IPv6 và firewall**. Một response **401 Unauthorized** chứng minh authentication hoạt động nhưng **không** chứng minh network isolation: port web vẫn đến được từ nguồn đáng lẽ bị cấm.

**Không sử dụng các probe này trên hệ thống không thuộc quyền quản trị.** Với production, phối hợp thời điểm và phạm vi test vì firewall logs/IDS có thể ghi lại.

### 10.4. Kiểm thử từ management zone

Trên SRE bastion được phép, kiểm tra console/Jolokia qua đúng TLS/tunnel và identity; thử **read-only operation** có hạn mức. Với remote JMX nếu thật sự bật, xác nhận:

- Registry port mở đúng source.
- RMI server port được pin và reachable từ management zone.
- Hostname trong stub resolvable.
- TLS và authentication hoạt động với credential hợp lệ.
- Một nguồn không được phép **không** mở được registry/RMI ports.
- Tài khoản chỉ monitoring không có quyền thay đổi/xóa message.

Không dùng thao tác purge/remove queue làm bài test authorization production.

## 11. Những đường vòng thường bị bỏ sót

### 11.1. Web console bị đóng nhưng Jolokia vẫn truy cập được

Có thể tồn tại một Jolokia agent riêng hoặc reverse proxy route khác. Phải kiểm tra **mọi listener HTTP** của JVM/web container, không chỉ giao diện HTML. Ngược lại, chỉ chặn đường dẫn **/console** mà vẫn cho **/api/jolokia** có thể giữ nguyên khả năng gọi MBean từ xa.

### 11.2. Đã đóng remote JMX nhưng Core management còn được cấp quyền rộng

Artemis có khả năng management qua các kênh broker được ủy quyền. Nếu tài khoản producer có role quá rộng, nó có thể tiếp cận management functions dù không có cổng JMX riêng. Network segmentation không thể thay thế **broker security settings và management authorization**.

### 11.3. Chỉ hạn chế public IP, quên lateral movement nội bộ

Một workload container bị xâm nhập có thể tìm tới broker trên private network nếu allowlist quá rộng. Dùng **workload identity và least-privilege destinations**; giám sát nguồn kết nối bất thường, lượng connection tăng và các truy vấn management không mong đợi.

### 11.4. Reverse proxy/WebSocket mở thêm đường không có trong inventory

WebSocket messaging qua proxy WSS là **protocol endpoint**, không phải console. Phải quản lý domain/origin, TLS, authentication, rate limits và protocol Upgrade; không tự đưa console/Jolokia vào cùng proxy location chỉ để “tiện cấu hình”.

### 11.5. Mở JMX registry nhưng quên RMI stub

Triệu chứng: client kết nối port 1099 được nhưng JConsole timeout. Cần kiểm tra **rmi.port, hostname, NAT/TLS và firewall cho server endpoint**; không tắt authentication hoặc SSL để chữa lỗi routing.

### 11.6. Cấu hình broker bind localhost nhưng host port vẫn công khai ở lớp khác

Các tình huống điển hình: một reverse proxy mở endpoint ra Internet; một service mesh gateway route tới web port; một kube port-forward được cấp RBAC rộng; hoặc container bind wildcard bên trong và Docker publish host wildcard. Bài kiểm tra phải theo **đường từ nguồn đến đích**, không chỉ theo một file broker.xml.

## 12. Runbook thay đổi port và cấp quyền kết nối

Một thay đổi mạng có thể làm mất producer/consumer hoặc làm lộ admin plane. Quy trình khuyến nghị:

1. **Inventory hiện trạng:** broker identity, version, listener addresses, protocols, container ports, host ports, Services/Ingress/LB, JMX flags, console/Jolokia paths, security groups.
2. **Phân loại nguồn cần truy cập:** producer/consumer, connector giữa brokers, metrics agent, SRE và automation. Mỗi nguồn có owner và business justification.
3. **Lập allowlist cụ thể:** source identity/subnet, destination IP/service, port, TLS mode, authentication và ngày hết hạn quyền tạm.
4. **Thay đổi cấu hình broker:** chỉ bật listener/protocol cần thiết; tách management web/JMX khỏi application network.
5. **Thay đổi security groups/firewall/NetworkPolicy:** deny các cổng admin từ app/public và allow đúng protocol từ đúng workload.
6. **Kiểm tra TLS, credential và authorization**: một TCP connection thành công không tương đương truy cập hợp lệ.
7. **Canary:** kiểm tra một producer/consumer test, một SRE operator và một nguồn bị cấm; đọc audit/firewall logs.
8. **Quan sát rollout:** connection errors, auth failures, TLS failures, queue lag, reconnect storms, DLQ và health theo broker.
9. **Rollback có kế hoạch:** khôi phục quyền ứng dụng thiết yếu mà **không mở public 8161/JMX** để chữa sự cố nhanh.
10. **Ghi nhận trạng thái cuối:** listener inventory, policy effective, kết quả positive/negative tests, owner và lịch review quyền.

### 12.1. Bảng nghiệm thu

| Test | Nguồn | Đích | Kỳ vọng |
|---|---|---|---|
| **T1** | Orders app đúng identity | Orders Core port | TCP + TLS/JMS auth + queue operation thành công |
| **T2** | App không thuộc allowlist | Orders Core port | **Network DENY** |
| **T3** | Orders app | Console/Jolokia | **Network DENY** |
| **T4** | Internet/vùng khách | Console/JMX/Jolokia | **Network DENY** |
| **T5** | SRE từ bastion/VPN | Console qua tunnel/HTTPS | Auth và quyền operator hợp lệ |
| **T6** | Monitoring principal | Jolokia/MBean read-only | Đọc metric được cấp quyền, mutate bị từ chối |
| **T7** | Host không được phép | RMI registry + server port | **Network DENY** |
| **T8** | Broker sau restart | Socket/Ingress/NetPolicy inventory | Không có listener/route bất ngờ |
| **T9** | App khi mất đường JMS tạm thời | Broker protocol | Timeout/retry hữu hạn, không làm nghẽn vô hạn |
| **T10** | Operator qua K8s API | Port-forward có RBAC | Chỉ người có quyền mới tạo đường quản trị |

Một bài test chỉ ghi **HTTP 401 từ Internet** đối với console **không đạt T4**: nguồn từ Internet vẫn chạm tới web stack. Nguyên tắc quản trị là **chặn ở lớp mạng trước**, rồi dùng auth/TLS làm lớp bảo vệ tiếp theo.

## 13. Bài tập áp dụng

### Lab A — Phân biệt bốn bề mặt trên cùng broker

Chuẩn bị Classic hoặc Artemis sandbox. Liệt kê mọi port nghe bằng công cụ OS, đối chiếu transport connector/acceptor, web bootstrap/Jetty, JVM JMX flags và Jolokia deployment. Gắn nhãn mỗi port **DATA**, **WEB MANAGEMENT**, **JMX**, **OTHER**.

**Đạt:** không nhầm 8161 với JMS connector, không bỏ sót RMI server endpoint và không coi Jolokia luôn có port riêng.

### Lab B — Chặn console từ application subnet

Cho JMS client kết nối thành công đến Core/OpenWire nhưng chặn **8161** từ cùng source. Đọc network firewall logs và thử từ SRE management zone theo đường được duyệt.

**Đạt:** messaging vẫn hoạt động; client application không chạm được console/Jolokia dù biết URL.

### Lab C — Classic transport binding

Trong lab nhiều network interface, chỉnh Classic transportConnector để chỉ nghe private app interface và kiểm chứng bằng **ss -lntp**, positive JMS client test và negative probe từ interface khác. Không quên Jetty console là listener riêng.

**Đạt:** dịch vụ chỉ nhận ở interface dự kiến; console không tự bị mở theo transportConnector.

### Lab D — Artemis Core acceptor và protocol whitelist

Thiết lập Artemis Core-only acceptor trong broker.xml, cấu hình Java JMS Core client và kiểm tra. Với client AMQP test không được cho phép trên endpoint này, xác nhận broker không xử lý protocol ấy như một connection hợp lệ. Không coi TCP probe là bằng chứng protocol được cho phép.

**Đạt:** protocol whitelist được xác minh bằng ứng dụng client thực, không chỉ nhìn port.

### Lab E — Kubernetes default-deny đối với broker pod

Áp dụng NetworkPolicy ở mục 9 trên namespace sandbox với CNI thực thi policy. Thử từ pod label **orders-worker** và pod không được allowlist. Sau đó kiểm tra một policy khác có vô tình cho phép **8161** hay không.

**Đạt:** đúng nguồn được phép vào TCP 61616; source khác bị chặn; có evidence về effective policies.

### Lab F — JMX qua RMI và hostname sai

Trong lab cô lập, cấu hình remote JMX có TLS/auth và các port được chọn. Cố tình đặt **java.rmi.server.hostname** không reachable, quan sát client qua registry nhưng lỗi ở stub connection. Sửa hostname và pin RMI port; giữ firewall giới hạn management source.

**Đạt:** giải thích được hai chặng JMX/RMI và không tắt bảo mật chỉ để kết nối thành công.

### Lab G — Jolokia read-only identity

Trên console sandbox đã xác nhận URL, tạo principal read-only với policy MBean thích hợp; kiểm thử đọc một attribute vô hại, và kiểm thử operation thay đổi được từ chối mà không chạm dữ liệu thật. Kiểm tra unauthorized client từ application subnet bị chặn ở network layer.

**Đạt:** có hai lớp bảo vệ độc lập: **network allowlist** và **read-only authorization**.

## 14. Checklist rà soát bảo mật

- [ ] Đã lập danh sách toàn bộ **protocol listeners, web console, Jolokia agents và remote JMX/RMI ports** thực tế.
- [ ] Chỉ mở những protocol thực sự có client; tránh acceptor/connector multi-protocol quá rộng.
- [ ] Không có console/Jolokia/remote JMX public trên Internet.
- [ ] Application sources chỉ tới **messaging port** cần dùng, không có quyền network đến management plane.
- [ ] Web console của Classic được kiểm tra trong **Jetty config**, không nhầm với activemq.xml transportConnector.
- [ ] Web console của Artemis được kiểm tra trong **bootstrap.xml**, không nhầm với broker.xml Netty acceptor.
- [ ] Khi có remote JMX, đã xác định cả **registry port, RMI server port, stub hostname, TLS và authentication**.
- [ ] Jolokia được phát hiện cả khi dùng chung console HTTP listener hoặc chạy agent riêng; path/policy đã được xác minh.
- [ ] Không dựa vào HTTP 401 như bằng chứng network isolation, không dùng CORS wildcard.
- [ ] Broker JMS/management roles được phân quyền riêng; private IP không thay authentication và authorization.
- [ ] Nếu dùng Docker, đã kiểm tra **container bind address** khác với **host published interface**.
- [ ] Nếu dùng Kubernetes, Service là ClusterIP và NetworkPolicy thực sự do CNI thực thi; xét các policy allow được cộng gộp.
- [ ] Đã kiểm tra IPv4/IPv6, reverse proxy, hostNetwork, NodePort/LoadBalancer và port-forward RBAC.
- [ ] Secret, truststore, keystore và management access logs được bảo vệ; không log credentials.
- [ ] Có positive test từ workload được phép, negative test từ nguồn bị cấm và management test từ bastion.
- [ ] Có owner, audit trail, lịch review allowlist và phương án rollback không mở bề mặt admin ra public.

**Kết luận:** Bảo mật ActiveMQ Classic và Artemis không dừng ở một username cho JMS. **Cổng giao thức** phải được phép từ đúng ứng dụng, **console và Jolokia** thuộc miền web management riêng, còn **remote JMX** nếu bật phải quản trị cả registry, RMI endpoint và identity. Hãy kết hợp **listener binding, firewall/security group, Kubernetes NetworkPolicy, TLS và broker authorization**, rồi kiểm chứng đường truy cập thật từ **nguồn được phép và nguồn bị cấm**. Đó là cách giảm nguy cơ lộ management plane mà vẫn giữ producer/consumer vận hành đáng tin cậy.
