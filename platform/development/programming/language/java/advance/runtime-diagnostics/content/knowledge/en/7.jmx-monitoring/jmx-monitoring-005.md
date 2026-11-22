# 7.5 — Kết nối từ xa qua JMX connector, RMI registry và cấu hình cổng

## 1. Mục tiêu và vấn đề cốt lõi

Khi một Java 17 application chạy ở máy chủ khác, JConsole, JDK Mission Control hoặc chương trình Java trên máy quản trị có thể đọc **platform MXBeans** và MBeans ứng dụng qua **JMX Remote API**. Với ready-to-use management agent của HotSpot, JMX thường sử dụng **RMI connector**.

Vấn đề gây lỗi phổ biến: một phiên JMX/RMI có **hai chặng TCP**. Client trước hết tìm RMI connector trong **RMI registry**, sau đó dùng **remote stub** được trả về để liên hệ cổng thực của connector. Nếu chỉ mở cổng registry, bước tra cứu có thể thành công nhưng mọi lệnh JMX tiếp theo vẫn timeout.

Sau bài này, bạn có thể:

1. Giải thích vai trò của MBeanServer, JMX connector server, RMI registry, RMIServer stub và client.
2. Phân biệt `jmxremote.port`, `jmxremote.rmi.port`, bind interface và hostname được quảng bá.
3. Đọc `JMXServiceURL` và xác định cổng nào là registry, cổng nào là connector.
4. Chạy demo **hai Java process** qua RMI/JMX, đọc custom MXBean cùng platform RuntimeMXBean.
5. Chẩn đoán DNS, firewall, NAT/container, SSL, authentication và authorization.
6. Giữ nguyên tắc bảo mật khi mở remote management endpoint.

> **Cảnh báo:** JMX remote là bề mặt **quản trị JVM**, không chỉ là metrics endpoint. Demo `authenticate=false` và `ssl=false` dưới đây **chỉ được chạy trên máy thử nghiệm cô lập và bind 127.0.0.1**. Không copy cấu hình này lên server có port truy cập được từ mạng không tin cậy.

## 2. Luồng kết nối qua RMI registry và JMX connector

```text
JMX client / JConsole / JMC
        |
        | (1) RMI lookup tên "jmxrmi" ở HOST:9010
        v
RMI registry của management agent
        |
        | trả về RMIServer remote stub
        v
Client lấy advertised HOST:PORT từ stub
        |
        | (2) RMI call tới HOST:9011 (ví dụ)
        v
JMX RMI connector server trong JVM đích
        |
        | chuyển yêu cầu MBeanServerConnection
        v
Platform MBeanServer
        +-- java.lang:type=Runtime
        +-- java.lang:type=Memory
        +-- demo:type=Status
```

| Thành phần | Vai trò | Không phải |
| --- | --- | --- |
| **Platform MBeanServer** | Quản lý MBeans, attributes, operations theo `ObjectName` | RMI registry trên TCP |
| **JMX connector server** | Đưa giao diện quản lý qua network transport RMI | Web/REST server |
| **RMI registry** | Lookup binding `jmxrmi` thành stub | Nơi xử lý `getAttribute` của MBean |
| **RMIServer stub** | Remote reference tới connector object, có endpoint để liên hệ | Bằng chứng đã xác thực |
| **JMXConnector client** | Tạo session, lấy `MBeanServerConnection`, gọi API rồi đóng tài nguyên | Chính JVM được giám sát |

**Chặng 1:** Client liên hệ `HOST:9010` và yêu cầu tên `jmxrmi`. Ready-to-use management agent tạo registry riêng và đăng ký binding đó.

**Chặng 2:** RMI registry trả về stub. Client lấy địa chỉ và port được ghi trong remote reference để gọi connector. Connector tạo phiên `RMIConnection` và phục vụ thao tác `MBeanServerConnection`.

Tên gọi “private read-only RMI registry” chỉ nói về quyền sửa registry bindings, **không** cho biết client được phép đọc/ghi những MBeans nào. Quyền JMX được kiểm soát bởi authentication và authorization của management agent.

## 3. Bản đồ cổng và địa chỉ

| Property/khái niệm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `-Dcom.sun.management.jmxremote.port=9010` | 9010 | Bật remote agent và RMI registry cho remote JMX |
| `-Dcom.sun.management.jmxremote.rmi.port=9011` | 9011 | Cố định cổng RMI connector để firewall biết trước |
| `-Djava.rmi.server.hostname=HOST` | `jvm-node.internal.example` | Host/IP **được ghi vào RMI stub** để client gọi chặng hai |
| `-Dcom.sun.management.jmxremote.host=IP` | `127.0.0.1` trong demo | Interface remote JMX agent bind trên HotSpot |
| `com.sun.management.jmxremote.local.port` | Không dùng trong demo | Một cổng khác dành cho local management connector |
| Registry binding | `jmxrmi` | Tên được lookup trong registry |

Port `9010` và `9011` là **số minh họa**, phải chọn các cổng còn trống. Với firewall thông thường, cần xem cả hai luồng, chứ không chỉ port `9010`.

Nếu bỏ `jmxremote.rmi.port`, RMI connector có thể được export qua một **cổng động**. Registry tra cứu thành công nhưng cổng connector không được firewall cho phép là tình huống rất phổ biến.

**Advertised host khác bind address:**

- `java.rmi.server.hostname` kiểm soát địa chỉ trong stub, **không tự mở socket mới**.
- `com.sun.management.jmxremote.host` chỉ định interface remote agent lắng nghe trên HotSpot.
- Host trong JMXServiceURL là nơi **registry lookup** diễn ra.
- Cả host/port registry và host/port từ stub đều phải **route được từ phía client**.

Một stub ghi `127.0.0.1:9011` hoạt động cho client trên cùng máy với JVM; client ở laptop khác sẽ thử kết nối về **laptop**, không phải máy chủ.

## 4. Đọc JMXServiceURL chính xác

Với ready-to-use management agent, URL chuẩn là:

```text
service:jmx:rmi:///jndi/rmi://HOST:REGISTRY_PORT/jmxrmi
```

Ví dụ trong bài thực hành:

```text
service:jmx:rmi:///jndi/rmi://127.0.0.1:9010/jmxrmi
```

Giải thích:

- `service:jmx:`: JMX connector address.
- `rmi:` đầu: connector protocol là RMI.
- `/jndi/rmi://...`: dùng JNDI lookup từ một RMI registry.
- `127.0.0.1:9010`: **registry endpoint**, không nhất thiết là port dùng cho RMI calls.
- `/jmxrmi`: binding name mà ready-to-use agent đăng ký.

**Vì sao không ghi `9011` trong URL?** Với dạng URL trên, client nhận endpoint thực từ stub. Nếu tự tạo custom JMX connector, có thể dùng dạng `service:jmx:rmi://HOST:CONNECTOR_PORT/jndi/rmi://HOST:REGISTRY_PORT/jmxrmi`; không suy ra mọi kiểu connector đều cần một format URL giống nhau.

### 4.1. Có cần chạy `rmiregistry` thủ công?

**Không** đối với management agent có sẵn. Khi JVM khởi động với `-Dcom.sun.management.jmxremote.port=9010`, agent tạo registry/binding cần thiết. Mở `rmiregistry` khác trên cùng port có thể làm JVM không khởi động do `Address already in use`. Chỉ trong custom connector architecture mới cần tự quản lý registry theo thiết kế của ứng dụng.

### 4.2. Khác nhau giữa JMX local và remote

Local JMX qua Attach API thường khám phá JVM theo PID, dùng local connector/IPC và quyền hệ điều hành. JMX remote qua RMI sử dụng registry URL, remote stub, giao diện mạng và security settings. `jcmd` trên laptop không tự attach vào PID của server từ xa. Bài này tập trung **remote connector**, không phải cách bật local management agent.

## 5. Thực hành Java 17: kết nối RMI/JMX với hai port riêng

Để vừa kiểm chứng protocol vừa tránh mở cổng quản trị ra mạng, demo cố định **loopback 127.0.0.1**. Hai chương trình chạy trong **hai process Java khác nhau**: target export MXBean, client đọc nó qua RMI registry và connector.

**Cấu hình bỏ authentication/TLS là không an toàn** ngoài máy học tập cô lập. Không dùng trên public IP, production server hoặc môi trường nhiều người không tin cậy.

### 5.1. Tạo file RemoteJmxTarget.java

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class RemoteJmxTarget {
    public interface StatusMXBean {
        String getMessage();
    }

    public static class Status implements StatusMXBean {
        @Override
        public String getMessage() {
            return "hello-over-jmx";
        }
    }

    public static void main(String[] args) throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();
        server.registerMBean(new Status(), new ObjectName("demo:type=Status"));
        System.out.println("TARGET_READY");
        Thread.sleep(60_000);
    }
}
```

Class `Status` implements `StatusMXBean`, cung cấp thuộc tính `Message`. `registerMBean` đăng ký nó dưới ObjectName `demo:type=Status` trên **platform MBeanServer** của JVM đích. `Thread.sleep(60_000)` giữ chương trình sống đủ lâu cho terminal thứ hai kết nối.

Remote agent có thể khởi tạo các thread riêng; sau khi `main` hết sleep không nên giả định JVM chắc chắn thoát ngay. Khi kết thúc bài, chủ động dừng **đúng process demo** bằng Ctrl+C hoặc công cụ OS được phép.

### 5.2. Tạo file RemoteJmxClient.java

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

public class RemoteJmxClient {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException("registry port required");
        }

        String urlText =
            "service:jmx:rmi:///jndi/rmi://127.0.0.1:" + args[0] + "/jmxrmi";
        JMXServiceURL url = new JMXServiceURL(urlText);

        try (JMXConnector connector = JMXConnectorFactory.connect(url)) {
            MBeanServerConnection remote = connector.getMBeanServerConnection();

            String message = (String) remote.getAttribute(
                new ObjectName("demo:type=Status"), "Message");
            long uptime = (Long) remote.getAttribute(
                new ObjectName(ManagementFactory.RUNTIME_MXBEAN_NAME), "Uptime");

            System.out.println("message=" + message);
            System.out.println("uptimeNonNegative=" + (uptime >= 0));
        }
    }
}
```

Client không biết lớp Java cụ thể của `Status`; nó chỉ dùng MBean `ObjectName` và attribute. `RuntimeMXBean.Uptime` là giá trị động; chương trình in kiểm tra boolean để có stdout ổn định. `try-with-resources` đóng `JMXConnector` kể cả khi lỗi.

### 5.3. Biên dịch

Đặt hai file trong cùng thư mục và dùng JDK 17+:

```bash
javac --release 17 RemoteJmxTarget.java RemoteJmxClient.java
```

JMX API nằm trong các module chuẩn Java management, không cần thư viện bên ngoài. Mã hai file này đã được biên dịch và kết nối thử thành công trên OpenJDK.

### 5.4. Khởi động target trong terminal thứ nhất

Trên bash (Linux/macOS/Git Bash), dùng **hai port còn trống**:

```bash
java \
  -Dcom.sun.management.jmxremote.port=9010 \
  -Dcom.sun.management.jmxremote.rmi.port=9011 \
  -Dcom.sun.management.jmxremote.host=127.0.0.1 \
  -Djava.rmi.server.hostname=127.0.0.1 \
  -Dcom.sun.management.jmxremote.authenticate=false \
  -Dcom.sun.management.jmxremote.ssl=false \
  RemoteJmxTarget
```

Trên Windows PowerShell, nhập các options **trên một dòng**:

```powershell
java -Dcom.sun.management.jmxremote.port=9010 -Dcom.sun.management.jmxremote.rmi.port=9011 -Dcom.sun.management.jmxremote.host=127.0.0.1 -Djava.rmi.server.hostname=127.0.0.1 -Dcom.sun.management.jmxremote.authenticate=false -Dcom.sun.management.jmxremote.ssl=false RemoteJmxTarget
```

**Stdout cố định khi target khởi động thành công:**

```text
TARGET_READY
```

Nếu port bị chiếm, file cấu hình sai hoặc agent không bind được, JVM có thể báo lỗi trước dòng này; cần xem stderr, không coi process đã sẵn sàng.

### 5.5. Kết nối từ terminal thứ hai

Khi target đã in `TARGET_READY` và còn chạy:

```bash
java RemoteJmxClient 9010
```

**Stdout chính xác của demo:**

```text
message=hello-over-jmx
uptimeNonNegative=true
```

Đã kiểm chứng hai kết quả trên bằng JVM mục tiêu và client thử nghiệm dùng **registry port khác RMI connector port**. Cổng thực tế trong kiểm thử có thể khác `9010` và `9011`; các output của Java code không phụ thuộc số port cụ thể.

`message=hello-over-jmx` chứng minh một `getAttribute` đã đi tới **MBeanServer của JVM đích** và trả dữ liệu. Việc hai process ở cùng máy để thử nghiệm **không đồng nghĩa** client đang dùng Attach API: đường truyền vẫn là JMX remote connector qua RMI.

### 5.6. Kiểm tra và dọn dẹp

Trên Linux:

```bash
ss -ltn
```

Trên Windows:

```powershell
Test-NetConnection 127.0.0.1 -Port 9010
Test-NetConnection 127.0.0.1 -Port 9011
```

Đây chỉ là TCP listener/reachability checks; không chứng minh SSL, authentication hoặc lời gọi MBean đã thành công. Dừng target sau thử nghiệm; không để JMX không xác thực chạy lâu trên máy dùng chung.

## 6. Từ JMXConnector đến MBeanServerConnection

Trong client, `JMXConnectorFactory.connect(url)` tạo connector; `getMBeanServerConnection()` cung cấp các thao tác JMX từ xa:

| API | Vai trò | Lưu ý |
| --- | --- | --- |
| `queryNames(...)` | Tìm MBeans theo ObjectName pattern | Danh sách có thể đổi theo runtime |
| `getMBeanInfo(...)` | Xem metadata attributes/operations | Không chứng minh caller có quyền gọi tất cả |
| `getAttribute(...)` | Đọc một attribute | Có thể lỗi vì ObjectName/attribute/quyền |
| `getAttributes(...)` | Đọc nhiều attributes | Không bảo đảm snapshot nguyên tử |
| `addNotificationListener(...)` | Theo dõi notifications | Cần unsubscribe/reconnect |
| `invoke(...)` | Gọi MBean operation | **Có thể thay đổi trạng thái JVM/ứng dụng** |

Role `readonly` phù hợp cho monitoring. Không cấp `readwrite` chỉ để một dashboard đọc JVM memory hay thread metrics.

### 6.1. Cấu hình credentials phía client

Nếu agent bật authentication, JMX client truyền credentials qua environment:

```java
// Snippet minh họa, không phải chương trình độc lập.
String user = System.getenv("JMX_USER");
String password = System.getenv("JMX_PASSWORD");

java.util.Map<String, ?> env = java.util.Map.of(
    JMXConnector.CREDENTIALS, new String[] { user, password });

try (JMXConnector connector = JMXConnectorFactory.connect(url, env)) {
    // Đọc MBeans mà role được cho phép.
}
```

Không hard-code password hay đưa credentials vào URL. `JMX_USER`/`JMX_PASSWORD` là tên biến ví dụ, không phải property do JDK bắt buộc. Với TLS/mutual TLS hoặc `registry.ssl=true`, client còn cần truststore, certificates và socket-factory settings thích hợp; một map credentials **không tự hoàn thiện TLS**.

## 7. Firewall, DNS, NAT và container

Hai câu hỏi phải tách riêng:

1. **Client tìm được registry không?** Kết nối tới `HOST:9010` và lookup `jmxrmi`.
2. **Client đi đến connector trong stub không?** Kết nối tới advertised `HOST:9011`, thực hiện handshake và MBean call.

Ví dụ lỗi khi host trong stub sai:

```text
client -> jvm-node:9010         SUCCESS: registry lookup
registry -> stub 127.0.0.1:9011 SUCCESS
client -> 127.0.0.1:9011       FAILED: trỏ về client, không phải jvm-node
```

Ví dụ lỗi khi connector port động bị firewall chặn:

```text
client -> jvm-node:9010         SUCCESS
registry -> stub jvm-node:random-port
client -> random-port           TIMEOUT
```

**Không chữa bằng cách đổi URL từ `9010` sang `9011`**: port trong đoạn `/jndi/rmi://...` vẫn dùng cho registry lookup.

Trong Docker/Kubernetes, JVM có thể quảng bá podIP/containerIP mà client bên ngoài không route được. Port-forward chỉ registry port có thể bỏ sót cổng connector. Một load balancer chuyển registry lookup đến JVM A và connector call đến JVM B cũng có thể làm session hỏng. Cần giữ cùng một JVM instance cho cả hai chặng và đảm bảo cả advertised host lẫn port đều reach được từ client.

`java.rmi.server.hostname` phải phù hợp với routing thực, nhưng nó không tạo listener mới. `com.sun.management.jmxremote.host` tác động bind interface; thay đổi nó cũng không tự sửa sai endpoint trong stub. Khi dùng tunnel/bastion, phải thiết kế cả hai chặng và bảo mật; không tắt TLS/auth để vượt qua NAT.

## 8. Bảo mật JMX remote trong production

Tài liệu Oracle Java 17 khuyến nghị authentication, authorization và TLS/SSL khi mở remote management. Các cờ `jmxremote.authenticate` và `jmxremote.ssl` thường bật mặc định khi remote agent được cấu hình, trong khi `jmxremote.registry.ssl` **mặc định false**.

| Lớp | Cấu hình/biện pháp | Mục đích |
| --- | --- | --- |
| Network | VPN, firewall, Security Group, NetworkPolicy | Hạn chế host có thể kết nối |
| Authentication | Password/JAAS/client certificates | Xác nhận danh tính |
| Authorization | Access file/role `readonly` hoặc `readwrite` | Giới hạn MBean operations |
| TLS connector | `jmxremote.ssl=true` | Bảo vệ RMI connector |
| TLS registry | `jmxremote.registry.ssl=true` | Bảo vệ đường lookup stub |
| Mutual TLS | `jmxremote.ssl.need.client.auth=true` | Xác thực client certificate |
| Secrets | Keystore, truststore, rotation, file permissions | Tránh lộ credential/certificates |

**TLS của connector không tự bảo vệ registry.** Registry không TLS có thể bị tấn công giả mạo trong một số mô hình đe dọa, khiến client lấy stub không đáng tin và gửi credentials sai nơi. Khi cần bảo mật mạnh, bật registry TLS và mutual TLS theo tài liệu JDK, kiểm tra client tương thích cấu hình.

Password file của ready-to-use agent lưu password dạng **clear text**; phải có quyền truy cập file chặt và tài liệu Oracle khuyến nghị cơ chế bảo mật mạnh hơn cho production. Không để secrets trong command line/log/repo; dùng chính sách secret management của tổ chức.

**Không chạy production với:**

```text
-Dcom.sun.management.jmxremote.authenticate=false
-Dcom.sun.management.jmxremote.ssl=false
```

Trên endpoint truy cập được từ mạng, cấu hình này có thể cho client lạ đọc/điều khiển ứng dụng qua MBean operations. Kể cả role chỉ đọc cũng có thể lộ nội dung cấu hình, thread/heap/system properties. Mọi truy cập JMX cần giới hạn và kiểm toán.

Agent có thể khiến JVM **khởi động thất bại** nếu port đã bị chiếm hoặc password/access file không hợp lệ, permission sai. Khi bật JMX trong deployment, phải xác minh startup logs, readiness và listener, không chỉ việc có đủ flags trong cấu hình.

## 9. Chẩn đoán theo từng chặng, không đoán cổng

| Triệu chứng | Nguyên nhân khả dĩ | Hướng kiểm tra |
| --- | --- | --- |
| JVM exit trước khi READY | Port conflict, password/access file lỗi, quyền file | stderr/log startup và listener |
| Connection refused tại registry | Sai IP/registry port, chưa bật agent, bind interface khác | `jmxremote.port`, process, route |
| Registry port open nhưng JMX timeout | Connector port động/bị chặn, stub advertised host sai | `jmxremote.rmi.port`, `java.rmi.server.hostname` |
| `NameNotFoundException: jmxrmi` | Registry không có đúng binding hoặc nhầm process | URL `/jmxrmi`, JVM identity |
| `UnknownHostException` | DNS tên registry hoặc stub không hợp lệ | Resolve **từ máy client** |
| RMI cố nối `127.0.0.1` từ laptop | Stub chứa loopback của server | Đặt advertised host phù hợp mạng |
| SSL handshake failure | Certificate/hostname/truststore/mTLS không khớp | Kiểm tra cert chain và TLS registry/connector |
| `SecurityException` | Credentials hoặc access role sai | Authentication/authorization, không log secret |
| Connect được nhưng `getAttribute` lỗi | Sai ObjectName/attribute, bean biến mất hoặc thiếu quyền | `queryNames`, `getMBeanInfo`, role |
| Chập chờn sau deploy | Pod restart, LB đổi JVM instance | Đối chiếu registry–stub–process identity |
| Chỉ lỗi qua port-forward | Stub trả container/pod IP không route | Xử lý cả hai chặng, không chỉ registry |

**Quy trình xử lý:** (1) xác nhận đúng JVM, (2) xác nhận agent đã start, (3) xác định registry port và connector port, (4) kiểm tra DNS/route/firewall từ client, (5) kiểm tra stub advertised endpoint, (6) kiểm tra TLS/auth, (7) thực hiện một `getAttribute` không phá hủy, (8) đóng connector và ghi timestamp/lỗi.

Các lệnh `ss`/`Test-NetConnection` chỉ là TCP tests, không xác nhận JMX handshake. Khi một thao tác JMX thành công rồi thao tác khác thất bại, cần kiểm tra quyền/contract MBean hoặc JVM đang pause, không mặc định mọi lỗi đều do firewall.

## 10. Sai lầm thường gặp

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “JMX remote chỉ có một port.” | Registry và connector có thể dùng hai port. |
| “Port trong URL là port thực hiện mọi JMX call.” | Đó là registry port; stub có thể quảng bá port khác. |
| “`java.rmi.server.hostname` sẽ bind socket.” | Nó ảnh hưởng advertised host trong RMI reference. |
| “Mở registry port nghĩa là endpoint hoạt động.” | Chặng hai và MBean operation vẫn có thể lỗi. |
| “Chỉ forward 9010 qua Kubernetes là xong.” | Cần đường đi phù hợp cho connector 9011 và stub. |
| “Phải chạy `rmiregistry` riêng.” | Ready-to-use agent tạo registry/binding riêng. |
| “Registry read-only nghĩa là JMX role read-only.” | Hai lớp quyền hoàn toàn khác nhau. |
| “SSL connector bảo vệ luôn registry.” | `registry.ssl` là setting riêng. |
| “Bỏ authentication chỉ ảnh hưởng metrics.” | JMX cho phép management operations. |
| “`service:jmx:...` là HTTP URL.” | Đây là JMX/RMI service URL. |
| “Attach API và remote connector giống nhau.” | Khác protocol, discovery, security và phạm vi. |
| “Client không cần đóng connector.” | Cần `close()` để giải phóng tài nguyên. |

## 11. Khi nào cần custom JMXConnectorServer?

Demo dùng management agent có sẵn; **không cần** gọi `LocateRegistry.createRegistry(...)` hay `JMXConnectorServerFactory` trong ứng dụng. Nếu có yêu cầu kiến trúc đặc biệt, có thể tạo custom connector bằng API:

```java
// Snippet minh họa khái niệm, không phải chương trình hoàn chỉnh.
javax.management.remote.JMXConnectorServer connector =
    javax.management.remote.JMXConnectorServerFactory.newJMXConnectorServer(
        serviceURL, environment, ManagementFactory.getPlatformMBeanServer());
connector.start();
```

Custom connector phải tự xử lý registry, exported ports, SSL socket factories, authentication, lifecycle và cleanup. Không sử dụng chỉ vì hiểu nhầm `jmxremote.rmi.port`; với JDK 17, property này đã hỗ trợ cố định connector port cho ready-to-use agent. Dùng giải pháp custom chỉ khi yêu cầu security/network thật sự đòi hỏi và đã được kiểm thử.

## 12. Tình huống thực tế

**A. JConsole dùng được trên server, hỏng từ laptop.** Kiểm tra RMI stub có chứa `127.0.0.1` hoặc hostname nội bộ không reach được từ laptop. Cấu hình advertised host, bind interface và security tương ứng; đổi mỗi URL registry không sửa stub sai.

**B. Sau khi đặt firewall, registry vẫn open nhưng JMX timeout.** Kết nối chặng đầu hoạt động; connector có thể đang dùng port động. Xem `jmxremote.rmi.port` và hai luồng TCP; không mở nhiều port ngẫu nhiên.

**C. Pod Kubernetes được port-forward nhưng client lỗi.** Registry qua tunnel hoạt động nhưng stub quảng bá podIP:connectorPort. Phải thiết kế cả hai chặng hoặc chạy client trong network quản trị có routing phù hợp.

**D. Đã bật SSL nhưng còn rủi ro giả mạo registry.** `jmxremote.ssl` và `jmxremote.registry.ssl` độc lập. Xem TLS của registry, chứng chỉ client/trust và quyền role trước khi kết luận cấu hình đủ an toàn.

**E. Dashboard chỉ cần đọc heap/thread.** Ưu tiên monitoring role chỉ đọc và mạng quản trị hạn chế. Đừng mở JMX unauthenticated hoặc cấp readwrite chỉ để lấy số liệu.

## 13. Checklist triển khai

- [ ] Xác nhận JVM/host/container/PID/start time, không nhắm nhầm replica.
- [ ] Đặt `jmxremote.port` cho registry và `jmxremote.rmi.port` cho connector nếu có firewall.
- [ ] Phân biệt bind interface với hostname/port được quảng bá qua stub.
- [ ] Hiểu `service:jmx:rmi:///jndi/rmi://HOST:REGISTRY_PORT/jmxrmi`.
- [ ] Kiểm tra cả hai chặng; không chỉ mở một TCP port.
- [ ] Không chạy `rmiregistry` trùng cổng management agent.
- [ ] Bảo vệ JMX bằng authentication, authorization, TLS và network isolation.
- [ ] Xem TLS registry và mutual TLS khi thiết kế security production.
- [ ] Không sao chép các cờ tắt bảo mật từ demo.
- [ ] Với NAT/container/LB, bảo đảm registry và stub chỉ đúng **một JVM instance**.
- [ ] Thử một JMX attribute read không phá hủy rồi đóng connector.
- [ ] Log lỗi/timestamp/endpoint cần thiết, không ghi passwords, tokens hay private keys.

## 14. Tài liệu Java SE 17 chính thức

- [Oracle — Monitoring and Management Using JMX Technology](https://docs.oracle.com/en/java/javase/17/management/monitoring-and-management-using-jmx-technology.html): ready-to-use JMX agent, remote ports, registry `jmxrmi`, TLS/auth.
- [Oracle — javax.management.remote](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/javax/management/remote/package-summary.html): JMXServiceURL, JMXConnector, MBeanServerConnection.
- [Oracle — javax.management.remote.rmi](https://docs.oracle.com/en/java/javase/17/docs/api/java.management.rmi/javax/management/remote/rmi/package-summary.html): RMI connector, stubs, JNDI lookup.
- [Oracle — JMXConnectorFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/javax/management/remote/JMXConnectorFactory.html): API tạo JMX client.
- [Oracle — RMI system properties](https://docs.oracle.com/en/java/javase/17/docs/specs/rmi/properties.html): `java.rmi.server.hostname`.
- [Oracle — JMX Security](https://docs.oracle.com/en/java/javase/17/jmx/security.html): authentication, authorization, SSL/TLS.

**Ghi nhớ:** một remote JMX/RMI connection thực hiện **registry lookup → nhận stub → gọi connector → truy vấn MBeanServer**. Registry port, connector port, bind interface và advertised hostname phải nhất quán với routing. TCP mở chưa bảo đảm JMX hoạt động, và một kết nối không có authentication/TLS là rủi ro quản trị nghiêm trọng.