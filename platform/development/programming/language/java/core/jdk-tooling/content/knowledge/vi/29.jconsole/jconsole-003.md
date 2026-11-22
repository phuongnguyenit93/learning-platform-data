# Kết nối remote JVM bằng `jconsole`

`jconsole` là công cụ giao diện đồ họa trong JDK để giám sát và quản lý Java Virtual Machine (JVM) thông qua Java Management Extensions (JMX). Khi kết nối remote, JConsole chạy trên máy quản trị và đọc dữ liệu từ một JMX management agent đang chạy trên máy ứng dụng.

Lệnh kết nối cơ bản:

~~~text
jconsole app-server.example.internal:9010
~~~

Ở phía JVM đích, cần bật remote management agent bằng các system property:

~~~text
-Dcom.sun.management.jmxremote.port=9010
-Dcom.sun.management.jmxremote.rmi.port=9011
~~~

Hai cổng này phục vụ hai phần của kết nối RMI. Client kết nối registry ở cổng `9010`, nhận RMI stub rồi kết nối tiếp tới RMI connector ở cổng `9011`. Cần cấu hình firewall và hostname cho cả hai đường kết nối.

Remote JMX có thể đọc thông tin runtime và gọi các operation quản lý thông qua MBeans. Vì vậy, kết nối cần authentication, authorization và TLS. JDK bật password authentication và SSL/TLS cho remote management theo mặc định; với production, Oracle khuyến nghị xác thực client bằng certificate và phân quyền user bằng password hoặc login module.

Toolchain được kiểm tra cho bài này là Zulu/OpenJDK 24.0.2. Ví dụ thực hành dùng Java 17+ và một JMX endpoint chỉ bind vào loopback.

## 1. JConsole, JMX và remote management

JMX là cơ chế chuẩn của Java để công bố thông tin và thao tác quản lý thông qua các MBean (Managed Bean). JVM tích hợp sẵn platform MXBeans cho các thành phần như:

- Runtime: phiên bản VM, uptime và arguments.
- Memory: heap, non-heap và memory pools.
- Garbage Collector: số lần collection và thời gian GC.
- Threading: thread count, thread state, stack trace và deadlock detection.
- Class Loading: số class được load/unload.
- Operating System: thông tin process và hệ điều hành tùy runtime.

Ứng dụng có thể đăng ký custom MBean để công bố metrics hoặc thao tác quản trị riêng.

Luồng kết nối remote:

~~~text
JConsole on operator workstation
             |
             | JMX over RMI
             v
      RMI Registry on target
             |
             | returns connector stub
             v
      RMI Connector on target
             |
             v
      MBeanServer in target JVM
             |
       +-----+------+
       |            |
       v            v
  Platform MBeans  Application MBeans
~~~

JConsole là JMX client. Nó không tự bật remote management trên một JVM ở máy khác. JVM đích phải có remote JMX agent đang lắng nghe, hoặc được cấu hình để khởi động agent qua một quy trình quản trị phù hợp.

## 2. Phân biệt kết nối local và remote

### Local connection

Khi chạy:

~~~text
jconsole
~~~

JConsole liệt kê các Java process cục bộ mà user hiện tại có quyền attach. Chọn một process rồi Connect.

Có thể chỉ định PID:

~~~text
jconsole 18240
~~~

Kết nối local sử dụng Attach API và quyền của hệ điều hành. JConsole và JVM thường phải chạy dưới cùng user. Với Java hiện đại, local monitoring có thể được bật động khi JConsole attach; không nhất thiết phải truyền `-Dcom.sun.management.jmxremote.port` từ lúc khởi chạy.

### Remote connection

Kết nối remote cần:

1. JVM đích bật remote JMX agent.
2. Client biết hostname và registry port.
3. Registry port và RMI connector port truy cập được qua mạng.
4. RMI stub quảng bá hostname/IP mà client có thể kết nối.
5. Client có credentials và trust material theo cấu hình bảo mật.

Remote connection không phụ thuộc PID của process trên máy client. PID ở máy đích không được nhập thay cho hostname và JMX port.

## 3. Cú pháp `jconsole`

Cú pháp của JDK 24:

~~~text
jconsole [-interval=n] [-notile] [-pluginpath path] [-version] [connection] [-Jinput_arguments]
~~~

`connection` có thể là:

| Dạng | Ý nghĩa |
|---|---|
| `pid` | PID của JVM cục bộ, cần quyền attach phù hợp |
| `host:port` | Hostname và cổng `com.sun.management.jmxremote.port` trên máy đích |
| `jmxURL` | Địa chỉ JMX service URL đầy đủ |

Các tùy chọn thường dùng:

- `-interval=n`: khoảng thời gian cập nhật biểu đồ, tính bằng giây; mặc định là 4 giây.
- `-notile`: không tự xếp cửa sổ khi kết nối nhiều JVM.
- `-pluginpath`: đường dẫn plugin JConsole.
- `-version`: in phiên bản chương trình.
- `-help` hoặc `--help`: hiển thị trợ giúp.
- `-J...`: truyền JVM option cho chính process JConsole, ví dụ truststore hoặc keystore phía client.

Ví dụ kết nối remote với chu kỳ cập nhật 10 giây:

~~~text
jconsole -interval=10 app-server.example.internal:9010
~~~

Nếu không truyền host và port, JConsole mở cửa sổ kết nối để nhập thông tin remote process hoặc JMX service URL.

## 4. Cấu hình remote JMX agent trên JVM đích

Remote management agent được bật khi JVM khởi chạy bằng `com.sun.management.jmxremote.port`.

Ví dụ cấu hình cổng:

~~~text
-Dcom.sun.management.jmxremote.port=9010
-Dcom.sun.management.jmxremote.rmi.port=9011
~~~

Vai trò:

- `com.sun.management.jmxremote.port`: cổng RMI Registry mà JConsole truy cập đầu tiên. Registry công bố connector dưới tên `jmxrmi`.
- `com.sun.management.jmxremote.rmi.port`: cổng cố định cho RMI connector server.
- `com.sun.management.jmxremote.host`: interface IP trên máy đích mà JMX RMI agent bind vào.
- `java.rmi.server.hostname`: hostname/IP được ghi vào RMI stub để client sử dụng khi kết nối tiếp.
- `com.sun.management.jmxremote.local.port`: cổng local JMX connector nếu muốn cố định riêng.

Nếu không cố định `com.sun.management.jmxremote.rmi.port`, RMI có thể dùng cổng động. Khi đó firewall chỉ mở registry port nhưng không mở được connector port; client có thể tìm thấy registry rồi vẫn timeout.

`jmxremote.host` và `java.rmi.server.hostname` có vai trò khác nhau: một thuộc tính chọn interface bind trên server, thuộc tính còn lại quyết định địa chỉ được quảng bá trong stub. Với máy có nhiều NIC, NAT hoặc subnet quản trị riêng, cần cấu hình cả hai theo đường mạng mà client thực sự sử dụng.

## 5. Chuẩn bị firewall và network

Ví dụ cấu hình:

~~~text
JMX registry:       TCP 9010
RMI connector:      TCP 9011
Server bind address: 10.20.30.40
Advertised host:    jmx-app-01.example.internal
Client command:     jconsole jmx-app-01.example.internal:9010
~~~

Để kết nối thành công:

1. Hostname phân giải đến đúng interface quản trị của máy đích.
2. TCP registry port `9010` được phép từ máy quản trị.
3. TCP connector port `9011` được phép từ máy quản trị.
4. RMI stub quảng bá hostname/IP mà client phân giải và truy cập được.
5. Firewall, NAT, security group và network policy không chặn một trong hai kết nối.
6. Cả hai port chưa bị process khác chiếm.

Không chỉ mở cổng registry rồi cho rằng JMX đã sẵn sàng. RMI client phải kết nối tới endpoint được trả về trong stub. Nếu stub chứa địa chỉ private hoặc loopback không truy cập được từ client, kết nối vẫn thất bại.

Trong production, chỉ cho phép subnet quản trị hoặc máy jump host được truy cập JMX. Không public JMX port ra Internet.

## 6. Bật remote JMX bằng startup options

Ví dụ lệnh khởi chạy với hai cổng cố định và interface quản trị:

~~~text
java -Dcom.sun.management.jmxremote.port=9010 -Dcom.sun.management.jmxremote.rmi.port=9011 -Dcom.sun.management.jmxremote.host=10.20.30.40 -Djava.rmi.server.hostname=jmx-app-01.example.internal -jar application.jar
~~~

Đây là phần cấu hình network. Trước khi đưa vào production, phải bổ sung authentication, authorization và TLS theo chính sách bảo mật. Không dùng ví dụ này một mình làm cấu hình phát hành nếu chưa thiết lập bảo mật remote JMX.

Các system property cũng có thể được đặt trong file `management.properties`, sau đó truyền đường dẫn file bằng:

~~~text
-Dcom.sun.management.config.file=/etc/myapp/management.properties
~~~

Property truyền trực tiếp trên command line sẽ ghi đè giá trị tương ứng trong file cấu hình.

## 7. Authentication và access control

Remote JMX agent dùng password authentication theo mặc định. Có hai file chính:

- `jmxremote.password`: ánh xạ role/user sang password.
- `jmxremote.access`: quy định quyền của mỗi role.

Ví dụ nội dung password file:

~~~text
# Thay các giá trị mẫu bằng mật khẩu riêng, đủ mạnh.
monitorRole <monitor-password>
controlRole <control-password>
~~~

Ví dụ access file:

~~~text
# Chỉ đọc metrics và MBean attributes.
monitorRole readonly

# Có quyền ghi attributes và gọi operations.
controlRole readwrite
~~~

`readonly` cho phép đọc MBean attributes và nhận notifications. `readwrite` có thể ghi thuộc tính, gọi operation và theo cấu hình có thể tạo hoặc xóa MBean. Chỉ cấp `readwrite` cho người vận hành thật sự cần thao tác quản trị.

Chỉ định file riêng khi khởi chạy:

~~~text
-Dcom.sun.management.jmxremote.authenticate=true
-Dcom.sun.management.jmxremote.password.file=/etc/myapp/jmxremote.password
-Dcom.sun.management.jmxremote.access.file=/etc/myapp/jmxremote.access
~~~

File password của cơ chế mặc định chứa password dạng clear text. Trên Linux/macOS, giới hạn quyền:

~~~sh
chmod 600 /etc/myapp/jmxremote.password
~~~

Trên Windows, dùng NTFS ACL để chỉ tài khoản chạy JVM được đọc file. Nếu file có quyền đọc rộng hơn, JMX agent có thể từ chối khởi động. Không dùng tài khoản đăng nhập cá nhân thường ngày làm role JMX; tạo credential chuyên dụng và phân quyền riêng.

Không đặt `com.sun.management.jmxremote.authenticate=false` trong production. Khi tắt authentication, các user có thể truy cập endpoint sẽ được cấp quyền quản lý đầy đủ; password/access files bị bỏ qua.

## 8. TLS và bảo vệ RMI Registry

Khi bật remote JMX, SSL/TLS được bật theo mặc định, nhưng JVM cần cấu hình certificate phù hợp. Phía server cần keystore chứa private key và certificate của server. Phía client cần truststore tin certificate của server.

Các system property thường dùng:

| Property | Vai trò |
|---|---|
| `javax.net.ssl.keyStore` | Đường dẫn keystore của JVM |
| `javax.net.ssl.keyStoreType` | Loại keystore, ví dụ `PKCS12` |
| `javax.net.ssl.keyStorePassword` | Password mở keystore |
| `javax.net.ssl.trustStore` | Đường dẫn truststore |
| `javax.net.ssl.trustStoreType` | Loại truststore |
| `javax.net.ssl.trustStorePassword` | Password mở truststore |
| `com.sun.management.jmxremote.ssl` | Bật/tắt TLS trên connector; mặc định `true` |
| `com.sun.management.jmxremote.ssl.need.client.auth` | Yêu cầu client certificate khi TLS bật |
| `com.sun.management.jmxremote.registry.ssl` | Bảo vệ RMI Registry bằng TLS |

Một mẫu cấu hình production có thể đặt trong `management.properties`:

~~~properties
com.sun.management.jmxremote.port=9010
com.sun.management.jmxremote.rmi.port=9011
com.sun.management.jmxremote.host=10.20.30.40
com.sun.management.jmxremote.authenticate=true
com.sun.management.jmxremote.password.file=/etc/myapp/jmxremote.password
com.sun.management.jmxremote.access.file=/etc/myapp/jmxremote.access
com.sun.management.jmxremote.ssl=true
com.sun.management.jmxremote.registry.ssl=true
com.sun.management.jmxremote.ssl.need.client.auth=true
~~~

Khởi chạy JVM với file quản lý và keystore/truststore đã được cấp phát:

~~~text
java -Dcom.sun.management.config.file=/etc/myapp/management.properties -Djava.rmi.server.hostname=jmx-app-01.example.internal -Djavax.net.ssl.keyStore=/etc/myapp/jmx-server.p12 -Djavax.net.ssl.keyStoreType=PKCS12 -Djavax.net.ssl.trustStore=/etc/myapp/jmx-truststore.p12 -Djavax.net.ssl.trustStoreType=PKCS12 -jar application.jar
~~~

Password keystore/truststore phải được cấp qua cơ chế bảo vệ secret của môi trường triển khai. Không ghi password thật vào source control, file cấu hình có quyền đọc rộng hoặc command history.

Khi dùng mutual TLS, cấu hình hai chiều phải bao gồm:

- Server keystore chứa server certificate và private key.
- Server truststore tin client certificate hoặc CA phát hành client certificate.
- Client keystore chứa client certificate và private key.
- Client truststore tin server certificate hoặc CA phát hành server certificate.

Có thể dùng `keytool` để tạo key pair, xuất public certificate và import vào truststore. Trong production, ưu tiên certificate do CA nội bộ hoặc CA được tổ chức chấp nhận cấp; quản lý private key và password bằng secret management.

Một lưu ý bảo mật quan trọng: Oracle ghi nhận rủi ro giả mạo RMI Registry khi connector stub được lấy từ registry không bảo vệ. Chỉ bật TLS trên connector là chưa đủ để loại bỏ tình huống này. Với production, bật `com.sun.management.jmxremote.registry.ssl=true` và client certificate authentication, đồng thời dùng password/login authentication để phân quyền user.

## 9. Kết nối từ JConsole

Sau khi remote JMX agent đã chạy, trên máy quản trị:

~~~text
jconsole jmx-app-01.example.internal:9010
~~~

Hoặc mở JConsole không có tham số, chọn Remote Process rồi nhập:

- Host name: `jmx-app-01.example.internal`
- Port: `9010`
- User name: role được cấp trong password file
- Password: password tương ứng với role

Nếu dùng JMX service URL, địa chỉ mặc định của JMX RMI agent có dạng:

~~~text
service:jmx:rmi:///jndi/rmi://jmx-app-01.example.internal:9010/jmxrmi
~~~

Nhập URL trong lựa chọn Remote Process của JConsole. URL chứa registry port, không phải RMI connector port.

Nếu server certificate không nằm trong truststore mặc định của JConsole, có thể truyền truststore cho JVM chạy JConsole bằng `-J`:

~~~text
jconsole -J-Djavax.net.ssl.trustStore=/etc/jmx/client-truststore.p12 -J-Djavax.net.ssl.trustStoreType=PKCS12 jmx-app-01.example.internal:9010
~~~

Nếu dùng mutual TLS, cấu hình thêm client keystore cho JConsole:

~~~text
jconsole -J-Djavax.net.ssl.keyStore=/etc/jmx/jconsole-client.p12 -J-Djavax.net.ssl.keyStoreType=PKCS12 -J-Djavax.net.ssl.trustStore=/etc/jmx/jconsole-truststore.p12 -J-Djavax.net.ssl.trustStoreType=PKCS12 jmx-app-01.example.internal:9010
~~~

Không ghi password keystore thật trực tiếp vào script hoặc command line được lưu lại; process arguments có thể bị người dùng cùng máy đọc. Dùng cơ chế quản lý secret và certificate phù hợp với môi trường.

## 10. Các tab chính trong JConsole

Sau khi kết nối, JConsole cung cấp sáu tab chính:

| Tab | Nội dung và cách sử dụng |
|---|---|
| Overview | Tổng quan CPU, memory, thread count và class loading trên một màn hình |
| Memory | Heap, non-heap, memory pool, used/committed/max và thời gian GC |
| Threads | Danh sách thread, trạng thái, stack trace và deadlock detection |
| Classes | Số class đang load, tổng số đã load và số đã unload |
| VM | Uptime, process CPU time, VM arguments, class path và thông tin runtime |
| MBeans | Platform MXBeans và custom MBeans, gồm attributes, operations và notifications |

### 10.1. Overview

Dùng Overview để quan sát nhanh CPU usage, memory usage, thread count và số class đã load. Khi một chỉ số tăng bất thường, chuyển sang tab chuyên biệt để tìm nguyên nhân.

### 10.2. Memory

Tab Memory hiển thị heap và non-heap theo thời gian, memory pool và thông tin GC. Những số liệu thường gặp:

- Used: dung lượng đang được sử dụng.
- Committed: dung lượng VM đã cam kết có thể sử dụng.
- Max: giới hạn tối đa nếu VM xác định được.
- GC time: tổng thời gian và số lần collection.

Các memory pool phụ thuộc collector và JDK. Không giả định tên pool của G1, ZGC và Parallel GC giống nhau.

Nút `Perform GC` yêu cầu JVM chạy garbage collection. Đây là thao tác quản lý có thể gây pause hoặc tăng CPU; không bấm lặp lại để xử lý memory leak hoặc dùng nó như phép đo duy nhất về sức khỏe heap.

### 10.3. Threads

Tab Threads hiển thị số thread đang sống, peak thread count, danh sách thread, state và stack trace. Chọn thread để xem call stack tại thời điểm cập nhật.

Nút `Detect Deadlock` kiểm tra deadlock giữa object monitor và ownable synchronizer như `ReentrantLock`. Nếu phát hiện, JConsole hiển thị tab kết quả deadlock cạnh tab Threads.

Khi điều tra thread pool, lock contention hoặc request bị treo, kết hợp thông tin này với thread dump từ `jcmd <PID> Thread.print -l`.

### 10.4. Classes

Tab Classes theo dõi số class được load, hiện còn được load và đã unload. Nếu số class hiện tại tăng liên tục trong thời gian dài, cần kiểm tra classloader, dynamic proxy, plugin hoặc cơ chế hot reload của ứng dụng.

### 10.5. VM

Tab VM hiển thị thông tin như uptime, process CPU time, JIT compile time, thread counts, memory summary, VM arguments và class path. Dùng tab này để xác nhận JConsole đang kết nối đúng instance và đúng cấu hình triển khai.

### 10.6. MBeans

Tab MBeans hiển thị cây MBean theo ObjectName. Chọn một MBean để xem:

- Attributes: giá trị thuộc tính và khả năng đọc/ghi.
- Operations: các phương thức quản trị có thể gọi.
- Notifications: sự kiện MBean có thể phát ra.
- Metadata: mô tả MBean và descriptor.

Các platform MXBean như `java.lang:type=Memory`, `java.lang:type=Threading` và `java.lang:type=Runtime` cung cấp nhiều thông tin sâu hơn các biểu đồ tổng quan. Ứng dụng cũng có thể đăng ký custom MBean cho business metrics hoặc thao tác vận hành.

Một attribute có quyền ghi hoặc một operation có thể thay đổi trạng thái JVM/ứng dụng. Chỉ thao tác khi đã hiểu tác động và được cấp role phù hợp.

## 11. Lưu dữ liệu biểu đồ

JConsole cho phép lưu dữ liệu biểu đồ thành CSV:

1. Mở tab có biểu đồ cần lưu.
2. Nhấp chuột phải vào biểu đồ.
3. Chọn `Save data as...`.
4. Chọn đường dẫn và tên file CSV.

CSV có timestamp và các cột metric, có thể mở bằng spreadsheet hoặc dùng để so sánh với log/metrics khác.

Khi so sánh nhiều khoảng thời gian, ghi lại JDK version, thời điểm, workload và update interval. Biểu đồ là dữ liệu lấy mẫu; nó không thay thế GC log, JFR hoặc metrics có độ phân giải cao.

## 12. Bật remote management cho JVM đang chạy bằng `jcmd`

Nếu JVM đã chạy nhưng chưa bật remote JMX agent, có thể kiểm tra khả năng attach và khởi động agent động bằng `jcmd`:

~~~text
jcmd <PID> ManagementAgent.status
~~~

Khởi động remote agent với cấu hình được hỗ trợ:

~~~text
jcmd <PID> ManagementAgent.start jmxremote.host=10.20.30.40 jmxremote.port=9010 jmxremote.rmi.port=9011 jmxremote.authenticate=true jmxremote.ssl=true
~~~

Có thể truyền thêm các option được JVM hỗ trợ, ví dụ password/access file, registry SSL, client authentication hoặc management config file. Xem chính xác các option của target JVM:

~~~text
jcmd <PID> help ManagementAgent.start
~~~

Dừng remote agent:

~~~text
jcmd <PID> ManagementAgent.stop
~~~

Lệnh này cần chạy trên cùng máy và dưới user/group có quyền attach vào JVM. Nếu attach bị tắt hoặc process chạy trong container namespace khác, thao tác có thể thất bại.

Khởi động agent động không thay thế việc chuẩn bị certificate, truststore, password file, access file và firewall. Với production, nên chuẩn hóa cấu hình trong deployment/startup config để có thể audit, tái lập và khôi phục sau restart.

## 13. Ví dụ Java 17+: kiểm tra remote JMX trên loopback

Lab này chạy registry và connector chỉ trên `127.0.0.1`. Cấu hình tắt authentication và TLS chỉ nhằm đơn giản hóa bài thử cục bộ; không dùng các option này cho remote host hoặc production.

Tạo file `RemoteJmxTarget.java`:

~~~java
public final class RemoteJmxTarget {
    private RemoteJmxTarget() {
    }

    public static void main(String[] args) throws InterruptedException {
        System.out.println("REMOTE_JMX_READY");
        Thread.sleep(300_000);
    }
}
~~~

Tạo file `JmxProbe.java` để kiểm tra JMX service URL:

~~~java
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

public final class JmxProbe {
    private JmxProbe() {
    }

    public static void main(String[] args) throws Exception {
        JMXServiceURL url = new JMXServiceURL(
                "service:jmx:rmi:///jndi/rmi://127.0.0.1:19099/jmxrmi");

        try (JMXConnector connector = JMXConnectorFactory.connect(url)) {
            MBeanServerConnection server =
                    connector.getMBeanServerConnection();

            ObjectName runtime =
                    new ObjectName("java.lang:type=Runtime");

            server.getAttribute(runtime, "VmName");
            System.out.println("JMX_CONNECT_OK");
        }
    }
}
~~~

Biên dịch:

~~~text
javac --release 17 RemoteJmxTarget.java JmxProbe.java
~~~

Chạy server trong terminal thứ nhất:

~~~text
java -Dcom.sun.management.jmxremote.port=19099 -Dcom.sun.management.jmxremote.rmi.port=19100 -Dcom.sun.management.jmxremote.host=127.0.0.1 -Djava.rmi.server.hostname=127.0.0.1 -Dcom.sun.management.jmxremote.authenticate=false -Dcom.sun.management.jmxremote.ssl=false -cp . RemoteJmxTarget
~~~

Stdout:

~~~text
REMOTE_JMX_READY
~~~

Trong terminal thứ hai, mở JConsole:

~~~text
jconsole 127.0.0.1:19099
~~~

JConsole kết nối tới registry port `19099`. Trong cửa sổ remote connection, host là `127.0.0.1`, port là `19099`.

Có thể kiểm tra endpoint bằng JMX client:

~~~text
java JmxProbe
~~~

Stdout:

~~~text
JMX_CONNECT_OK
~~~

Hai cổng `19099` và `19100` phải còn trống. Nếu máy đã dùng cổng này, chọn hai cổng khác và cập nhật cả server command, JMX URL và JConsole host/port. Khi kết thúc, dừng JVM thử nghiệm bằng `Ctrl+C`.

Lab đã được chạy với Zulu/OpenJDK 24.0.2: server in `REMOTE_JMX_READY`, client in `JMX_CONNECT_OK`, và hai listener chỉ bind vào `127.0.0.1`.

## 14. Troubleshooting kết nối remote

### `Connection refused`

**Nguyên nhân:** remote agent chưa bật, JVM đã dừng, port sai hoặc firewall từ chối kết nối.

**Cách xử lý:** kiểm tra startup options, process và listener trên registry port; xác nhận port đang dùng không bị process khác chiếm.

### Kết nối registry thành công nhưng sau đó timeout

**Nguyên nhân:** RMI connector port không truy cập được hoặc stub quảng bá hostname/IP không thể định tuyến từ client.

**Cách xử lý:** cố định `com.sun.management.jmxremote.rmi.port`, mở cả hai TCP port và đặt `java.rmi.server.hostname` thành địa chỉ client truy cập được.

### `Unknown host` hoặc kết nối tới sai địa chỉ

**Nguyên nhân:** DNS không phân giải được hostname trong RMI stub hoặc hostname trỏ tới interface nội bộ.

**Cách xử lý:** kiểm tra DNS từ máy chạy JConsole, `jmxremote.host` và `java.rmi.server.hostname`. Không chỉ kiểm tra hostname trong lệnh JConsole; stub cũng phải quảng bá địa chỉ đúng.

### `SSLHandshakeException`

**Nguyên nhân:** client không tin certificate server, certificate hết hạn, hostname không khớp, client certificate thiếu hoặc truststore sai.

**Cách xử lý:** kiểm tra keystore/truststore ở cả hai phía, certificate chain, SAN/hostname, thời hạn certificate và trạng thái mutual TLS.

### `Authentication failed`

**Nguyên nhân:** username không tồn tại trong password file, password không khớp, role không có trong access file hoặc file không đúng định dạng.

**Cách xử lý:** kiểm tra cả hai file, role name và quyền truy cập file. Dùng credential JMX chuyên dụng; không dùng password cá nhân.

### JMX agent không khởi động

**Nguyên nhân:** port bị chiếm, password/access file sai định dạng hoặc password file có quyền đọc quá rộng.

**Cách xử lý:** xem stderr/log của JVM, kiểm tra listener và quyền file. Sửa cấu hình rồi khởi động lại theo quy trình triển khai.

### JConsole không thấy local JVM

**Nguyên nhân:** JConsole và JVM chạy dưới user khác, Attach API bị giới hạn hoặc process nằm trong container/PID namespace khác.

**Cách xử lý:** chạy JConsole dưới user phù hợp, xác nhận PID trong đúng môi trường và kiểm tra attach mechanism.

### JConsole kết nối được nhưng một số thao tác bị từ chối

**Nguyên nhân:** role hiện tại là `readonly` hoặc MBean không cho phép thao tác tương ứng.

**Cách xử lý:** xem access file và MBean operation. Chỉ cấp `readwrite` nếu cần và có phê duyệt vận hành.

### Biểu đồ không cập nhật hoặc dữ liệu có vẻ trễ

**Nguyên nhân:** update interval dài, JVM đang quá tải, network latency hoặc JMX polling bị chậm.

**Cách xử lý:** kiểm tra interval, giảm số biểu đồ đang theo dõi, đối chiếu với GC log/JFR và tránh polling quá dày.

## 15. Tác động hiệu năng và giới hạn vận hành

JConsole liên tục lấy mẫu các MBean để cập nhật biểu đồ. Chi phí phụ thuộc số thread, số MBean, tần suất cập nhật và tình trạng JVM.

Một số nguyên tắc:

- Chạy JConsole trên máy quản trị để giảm tải UI trên máy ứng dụng.
- Giữ update interval phù hợp; mặc định là 4 giây, có thể tăng lên 10 giây khi chỉ cần quan sát tổng quan.
- Tránh mở nhiều phiên JConsole cùng polling một JVM với tần suất cao.
- Hạn chế gọi operation nặng từ MBeans khi hệ thống đang quá tải.
- Không dùng nút `Perform GC` như biện pháp xử lý memory leak.
- Lưu CSV có chọn lọc và bảo vệ dữ liệu vận hành.
- Dùng GC log, JFR và monitoring metrics cho quan sát dài hạn; JConsole phù hợp cho kiểm tra tương tác và điều tra tại thời điểm cụ thể.

JMX cho phép quản lý JVM, nên tài khoản `readwrite` có thể ảnh hưởng tới ứng dụng. Tách role monitoring và control, chỉ mở quyền control cho người được giao nhiệm vụ.

## 16. Quy trình kết nối remote JVM trong production

1. Xác định đúng service, host, JDK version và interface quản trị.
2. Chọn registry port và RMI connector port cố định, chưa được sử dụng.
3. Cấu hình `jmxremote.host` và `java.rmi.server.hostname`.
4. Chuẩn bị server keystore, server truststore và client certificate nếu dùng mutual TLS.
5. Cấu hình `jmxremote.password` hoặc JAAS/LDAP authentication.
6. Cấu hình access file với role `readonly` và role `readwrite` riêng.
7. Bật TLS, bảo vệ RMI Registry bằng `jmxremote.registry.ssl=true` và client certificate authentication.
8. Giới hạn firewall chỉ cho management subnet hoặc jump host.
9. Khởi động JVM với remote management options và kiểm tra log agent.
10. Kết nối bằng JConsole với host/registry port, xác nhận đúng JVM trong tab VM.
11. Dùng role readonly để theo dõi trước; chỉ dùng role control khi cần thao tác.
12. Lưu lại thời điểm, người vận hành, host, port, JDK version và mục đích phiên kết nối.
13. Thu hồi credential/certificate không còn sử dụng và đóng các port quản trị khi không còn cần.

## 17. Checklist trước khi kết nối

- [ ] Đã xác nhận đúng host và JVM đích.
- [ ] Đã bật remote JMX agent.
- [ ] Đã cố định registry port và RMI connector port.
- [ ] Đã cấu hình bind interface và advertised hostname.
- [ ] Cả hai cổng TCP đều truy cập được từ máy JConsole.
- [ ] Authentication được bật và password/access files hợp lệ.
- [ ] Password file chỉ tài khoản chạy JVM được đọc.
- [ ] TLS certificate, keystore và truststore đúng ở cả hai phía.
- [ ] Đã bảo vệ RMI Registry và bật client certificate auth theo policy production.
- [ ] Role monitoring chỉ có `readonly`.
- [ ] Role `readwrite` được giới hạn cho người vận hành cần thiết.
- [ ] JConsole đang kết nối đúng JMX endpoint.
- [ ] Đã xem Overview, Memory, Threads, Classes, VM và MBeans theo mục tiêu điều tra.
- [ ] Không gọi operation có tác động cao nếu chưa đánh giá.
- [ ] Thread dump, CSV và thông tin MBean được lưu ở nơi có kiểm soát truy cập.
- [ ] Có kế hoạch đóng phiên, thu hồi quyền và quản lý certificate/credential.

## 18. Tài liệu tham khảo

- Oracle JDK 24 — Monitoring and Management Using JMX Technology: https://docs.oracle.com/en/java/javase/24/management/monitoring-and-management-using-jmx-technology.html
- Oracle JDK 24 — Using JConsole: https://docs.oracle.com/en/java/javase/24/management/using-jconsole.html
- Oracle JDK 24 — The `jconsole` Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jconsole.html
- Oracle JDK 24 — The `jcmd` Command, phần `ManagementAgent.start`: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html
- Java SE 24 — `JMXServiceURL` API: https://docs.oracle.com/en/java/javase/24/docs/api/java.management/javax/management/remote/JMXServiceURL.html

Kết nối remote JVM bằng JConsole dựa trên JMX/RMI: bật management agent, cấu hình registry và connector port, đặt đúng địa chỉ bind/advertised host, rồi kết nối bằng `host:port` hoặc JMX service URL. Vì JMX cung cấp cả khả năng đọc lẫn thao tác quản trị, production cần TLS, client authentication, phân quyền read-only/read-write và firewall giới hạn theo mạng quản trị.