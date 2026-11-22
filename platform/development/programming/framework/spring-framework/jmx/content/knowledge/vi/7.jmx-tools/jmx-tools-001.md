# JConsole kết nối tới MBeanServer local và remote

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích JConsole là công cụ JMX trong JDK, truy cập các MBean qua MBeanServer để quan sát và thao tác quản trị.
- Kết nối JConsole đến ứng dụng Java **cùng máy** (local process) hoặc **khác máy** (remote JMX connection).
- Phân biệt platform MBeanServer với đầu cuối JMX connector, và nhận biết đường truyền JMX/RMI.
- Bật cấu hình remote JMX cần thiết, hiểu các tham số cổng, hostname, xác thực và TLS.
- Tự chẩn đoán các sự cố kết nối thường gặp: không thấy process, sai PID, thiếu quyền attach, firewall, NAT, hostname RMI, port động, TLS và credential.
- Khai thác giao diện MBeans của JConsole để đọc attribute, xem operation, quan sát notification và kiểm tra giới hạn an toàn khi thao tác.
- Áp dụng quy trình kết nối an toàn trong môi trường ứng dụng Spring Framework, JVM service, container và máy chủ.

## 2. JConsole là gì?

**JConsole** là công cụ đồ họa đi kèm một số bản phân phối JDK, được xây dựng trên Java Management Extensions (JMX). Nó giúp người vận hành quan sát JVM và các MBean đã đăng ký, thường qua các tab:

- **Overview:** tóm tắt CPU, bộ nhớ, số luồng và lớp.
- **Memory:** heap/non-heap, các memory pool, GC và đồ thị sử dụng bộ nhớ.
- **Threads:** tổng số luồng, trạng thái và thông tin luồng được JVM công bố.
- **Classes:** số class đã tải và đã unload.
- **VM Summary:** thông tin runtime, JVM, đường chạy, hệ điều hành và các thuộc tính quản trị.
- **MBeans:** cây ObjectName, attributes, operations và notifications được công bố qua JMX.

JConsole **không phải** bộ lưu trữ metrics lâu dài hoặc hệ thống phân tích phân tán. Nó chủ yếu phù hợp cho thao tác quan sát/chẩn đoán trực tiếp tại một thời điểm. Những công cụ giám sát dài hạn như Prometheus/Grafana có thể thu số liệu qua cơ chế exporter riêng nếu ứng dụng cần lịch sử và cảnh báo.

Một MBean có thể được đăng ký trong platform MBeanServer của JVM:

\`\`\`java
MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName name = new ObjectName(
    "com.example:type=Cache,name=Products"
);
server.registerMBean(cacheMonitor, name);
\`\`\`

JConsole thông qua JMX connection sẽ nhìn thấy MBean này nếu connector trỏ đúng MBeanServer và quyền truy cập cho phép.

## 3. Kiến trúc kết nối

\`\`\`text
                      JVM ứng dụng
+--------------------------------------------------------+
| Business services / Spring beans                       |
|           |                                            |
|       MBeans / MXBeans                                 |
|           | đăng ký                                    |
|           v                                            |
| Platform MBeanServer                                   |
|   java.lang:type=Memory                                |
|   java.lang:type=Threading                             |
|   com.example:type=Cache,name=Products                 |
|           ^                                            |
|           | MBeanServerConnection API                  |
|           |                                            |
|    JMX agent / JMXConnectorServer (khi bật remote)     |
+-----------|--------------------------------------------+
            ^
            | JMX/RMI, qua mạng khi dùng remote
            |
        JConsole
        - Local Process
        - Remote Process
\`\`\`

**Platform MBeanServer** quản lý MBean trong tiến trình Java. **JMXConnectorServer** cung cấp cách client kết nối từ bên ngoài tiến trình, khi được cấu hình. Với remote JMX kiểu RMI thông dụng, kết nối còn phụ thuộc hostname được công bố bởi RMI stub và các cổng liên quan.

Đối với **local**, JConsole trên cùng host thường có khả năng phát hiện JVM phù hợp và sử dụng cơ chế local management/attach. Với **remote**, client cần một endpoint được cấu hình và có thể truy cập qua mạng, có thể kèm xác thực và TLS.

Điểm cần nhớ: gọi \`ManagementFactory.getPlatformMBeanServer()\` trong code **không tự động mở cổng remote JMX**. Một local process có thể có JMX MBeans nhưng không có kết nối từ xa.

## 4. Điều kiện tiên quyết

Trước khi thao tác, kiểm tra:

1. **JDK/JConsole:** có JDK cài đặt công cụ \`jconsole\`. Một số runtime image tối giản không bao gồm công cụ đồ họa.
2. **Java process:** ứng dụng đang chạy trong JVM có JMX management API; với platform MBeanServer của JDK thông thường, các MBean hệ thống thường sẵn có.
3. **Quyền local:** tài khoản đang chạy JConsole có thể nhìn thấy/attach vào tiến trình, tùy hệ điều hành, quyền người dùng và cấu hình JVM.
4. **Remote connector:** JVM đích đã bật JMX remote; endpoint và các cổng cần thiết được mở đúng phạm vi mạng.
5. **Bảo mật:** có credential, truststore/certificate hoặc đường hầm kết nối nếu chính sách yêu cầu.
6. **Spring:** nếu muốn thấy MBean ứng dụng, bean phải được xuất qua Spring JMX exporter hoặc đăng ký với MBeanServer, ngoài các MBean mặc định của JVM.

Lệnh kiểm tra trong terminal có JDK:

\`\`\`bash
java -version
jconsole
\`\`\`

Trên Windows có thể chạy \`jconsole.exe\` từ thư mục \`bin\` của JDK. Nếu lệnh không nhận diện, xác minh đường dẫn cài đặt JDK hoặc gọi trực tiếp file executable thích hợp.

Không cần tự thêm JConsole vào dependency Maven/Gradle của ứng dụng: nó là công cụ ngoài JVM, dùng để kết nối và quan sát.

## 5. Kết nối local: JConsole và ứng dụng chạy cùng máy

### 5.1. Các bước thực hiện

1. Khởi động ứng dụng Java/Spring Boot trong một JVM local.
2. Mở terminal và chạy \`jconsole\`, hoặc mở \`jconsole.exe\` từ thư mục \`bin\` của JDK.
3. Trong cửa sổ **New Connection**, chọn **Local Process**.
4. Chọn tiến trình Java theo PID và mô tả lệnh chạy. Nếu có nhiều JVM, đối chiếu PID để tránh chọn nhầm.
5. Nhấn **Connect**. Với những JVM phiên bản và cấu hình có hỗ trợ local management agent, công cụ có thể bật/sử dụng agent này để truy cập.
6. Sau khi kết nối, mở tab **MBeans** và khám phá các domain như \`java.lang\`, \`com.sun.management\` hoặc domain ứng dụng đã xuất.

Có thể xem PID từ \`jps -l\` nếu bộ JDK có tiện ích \`jps\`:

\`\`\`bash
jps -l
\`\`\`

Trên Windows, PID còn có thể tìm trong Task Manager; trên Linux/macOS dùng các công cụ quản lý tiến trình tương ứng. Chỉ cần biết PID đúng và quyền truy cập phù hợp; không cần bật remote JMX chỉ để kết nối trên cùng máy trong trường hợp local attach có thể hoạt động.

### 5.2. Chọn đúng process

Nếu máy đang chạy nhiều Java process, tên \`org.springframework.boot.loader.launch.JarLauncher\`, \`Application\` hay \`GradleDaemon\` có thể trông giống nhau. Hãy kiểm tra PID, đường dẫn ứng dụng, command line hoặc quy trình khởi động. Đừng chọn JVM chỉ dựa vào thứ tự hiện trong danh sách.

JConsole local cũng có thể không phát hiện một tiến trình khi tài khoản khác, JVM bị hạn chế attach, process chạy trong container namespace khác hoặc agent bị vô hiệu hóa. Khi đó cần chẩn đoán chính sách quyền/namespace hoặc chuyển sang phương án kết nối được cấu hình có chủ đích.

### 5.3. Local connection không đồng nghĩa quản trị an toàn tuyệt đối

Tài khoản cùng máy có thể có quyền truy cập nhạy cảm. Nếu MBean xuất operation như \`clearCache\`, \`resetStatistics\`, \`pauseConsumer\`, người dùng JConsole có quyền có thể thực thi thao tác và ảnh hưởng hệ thống. Việc kết nối local chỉ khác về đường truy cập; nó không tự làm cho mọi operation vô hại.

## 6. Ví dụ ứng dụng có MBean để quan sát trong JConsole

Một Standard MBean phù hợp với ví dụ đơn giản:

\`\`\`java
package example.jmx;

public interface TaskMonitorMBean {
    long getCompletedCount();
    boolean isPaused();
    void resume();
}
\`\`\`

\`\`\`java
package example.jmx;

public final class TaskMonitor implements TaskMonitorMBean {
    private volatile long completedCount = 42L;
    private volatile boolean paused;

    @Override
    public long getCompletedCount() {
        return completedCount;
    }

    @Override
    public boolean isPaused() {
        return paused;
    }

    @Override
    public void resume() {
        paused = false;
    }
}
\`\`\`

Đăng ký rồi giữ ứng dụng chạy để có đủ thời gian quan sát:

\`\`\`java
package example.jmx;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public final class JmxDemoApplication {
    public static void main(String[] args) throws Exception {
        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
            "com.example:type=TaskMonitor,name=Primary"
        );
        server.registerMBean(new TaskMonitor(), name);

        System.out.println("MBean registered: " + name);
        System.out.println("Press Enter to stop.");

        try {
            System.in.read();
        } finally {
            server.unregisterMBean(name);
        }
    }
}
\`\`\`

Khi kết nối JConsole tới JVM này, vào **MBeans → com.example → TaskMonitor → Primary** (cách hiển thị cây có thể khác tùy phiên bản). Bạn sẽ thấy:

- \`CompletedCount\` có giá trị ban đầu \`42\`, đọc được.
- \`Paused\` có giá trị ban đầu \`false\`, đọc được.
- \`resume\` xuất hiện trong phần Operations.

Nếu command line hoặc môi trường làm \`System.in.read()\` kết thúc sớm vì không có stdin, hãy thay bằng vòng đời ứng dụng lâu chạy của riêng bạn; mục đích là giữ JVM đủ lâu để JConsole attach.

### 6.1. Đăng ký MBean và công bố Spring bean là hai việc khác nhau

Một Spring bean thông thường không tự động xuất hiện trong JMX MBean tree. Với Spring Framework, có thể dùng \`MBeanExporter\`, \`@ManagedResource\`, \`@ManagedAttribute\` và \`@ManagedOperation\` theo một cấu hình exporter phù hợp.

Spring JMX exporter sẽ đăng ký đối tượng quản trị vào một MBeanServer, thường là platform MBeanServer. JConsole chỉ hiển thị những MBean thực sự được đăng ký trên server mà nó đang truy cập.

## 7. Kết nối remote: hai phần cấu hình cần hiểu

Remote JMX thường dựa trên **JMX management agent** của JVM và transport RMI. Cần phân biệt:

- **JMX management port:** nơi client bắt đầu liên hệ RMI registry/connector endpoint.
- **RMI server port:** cổng transport thực sự mà remote endpoint trả về cho client để tiếp tục kết nối.

Nếu RMI server port để chọn động, client có thể truy cập registry port nhưng không kết nối được tới cổng được công bố sau đó, đặc biệt qua firewall, NAT và container. Vì thế nhiều triển khai đặt cố định cả hai cổng phù hợp.

Các JVM và cơ chế JMX connector khác có thể dùng cấu hình khác; ví dụ dưới đây áp dụng cho built-in remote JMX agent kiểu RMI thường gặp trên HotSpot/OpenJDK.

## 8. Cấu hình remote JMX trong môi trường lab

### 8.1. Lệnh minh họa

Chỉ dùng cấu hình **không xác thực và không TLS** trong môi trường lab cô lập, không có truy cập từ mạng không tin cậy. Ví dụ:

\`\`\`bash
java \
  -Dcom.sun.management.jmxremote \
  -Dcom.sun.management.jmxremote.port=9010 \
  -Dcom.sun.management.jmxremote.rmi.port=9010 \
  -Dcom.sun.management.jmxremote.authenticate=false \
  -Dcom.sun.management.jmxremote.ssl=false \
  -Djava.rmi.server.hostname=127.0.0.1 \
  -cp out example.jmx.JmxDemoApplication
\`\`\`

Giải thích:

| Cấu hình | Ý nghĩa |
| --- | --- |
| \`com.sun.management.jmxremote\` | Bật quản lý JMX agent theo cơ chế JVM hỗ trợ. |
| \`com.sun.management.jmxremote.port=9010\` | Đặt cổng remote JMX management/registry. |
| \`com.sun.management.jmxremote.rmi.port=9010\` | Cố định cổng RMI connector server, tránh random port cần mở thêm. |
| \`com.sun.management.jmxremote.authenticate=false\` | Tắt xác thực; **chỉ phù hợp môi trường lab cô lập**. |
| \`com.sun.management.jmxremote.ssl=false\` | Tắt mã hóa TLS; **không dùng cho kết nối qua mạng không tin cậy**. |
| \`java.rmi.server.hostname=127.0.0.1\` | Đặt địa chỉ được RMI stub quảng bá, phù hợp với kết nối local loopback. |

Với \`127.0.0.1\`, ví dụ hướng tới JConsole chạy trên **cùng host**, hoặc phía client qua **SSH tunnel** có chuyển tiếp localhost phù hợp. Để kết nối trực tiếp từ host khác, hostname được RMI quảng bá phải là địa chỉ/tên có thể truy cập **từ phía client** theo thiết kế mạng, đồng thời có lớp bảo mật và quyền truy cập cần thiết.

Việc đặt \`port\` và \`rmi.port\` bằng nhau là cấu hình thông dụng; trong các môi trường, phiên bản JVM khác nhau cần kiểm tra cách các endpoint được bind. JVM cũng có thể mở thêm cổng local management riêng phục vụ attach cục bộ.

### 8.2. Windows PowerShell

Trong PowerShell, dấu \`\\\` không phải ký tự nối dòng như Bash. Ví dụ viết một dòng:

\`\`\`powershell
java -Dcom.sun.management.jmxremote -Dcom.sun.management.jmxremote.port=9010 -Dcom.sun.management.jmxremote.rmi.port=9010 -Dcom.sun.management.jmxremote.authenticate=false -Dcom.sun.management.jmxremote.ssl=false -Djava.rmi.server.hostname=127.0.0.1 -cp out example.jmx.JmxDemoApplication
\`\`\`

Trong PowerShell 5.1, nếu cần xuống dòng, dùng backtick theo cú pháp shell và lưu ý không có khoảng trắng sau backtick. Các option JVM phải nằm **trước** tên main class hoặc \`-jar\`.

### 8.3. Với Spring Boot JAR

\`\`\`bash
java \
  -Dcom.sun.management.jmxremote \
  -Dcom.sun.management.jmxremote.port=9010 \
  -Dcom.sun.management.jmxremote.rmi.port=9010 \
  -Dcom.sun.management.jmxremote.authenticate=false \
  -Dcom.sun.management.jmxremote.ssl=false \
  -Djava.rmi.server.hostname=127.0.0.1 \
  -jar app.jar
\`\`\`

Ví dụ cho lab trên loopback, không dùng nguyên cấu hình này để mở cổng production. Lưu ý sự khác nhau giữa **bật remote JMX agent của JVM** và **bật export JMX của Spring Boot**: remote agent quyết định đường kết nối, còn Spring/JMX exporter quyết định MBean ứng dụng nào được đăng ký.

## 9. Thực hiện kết nối Remote Process trong JConsole

Các bước trên giao diện:

1. Chạy JVM đích với JMX remote agent và xác nhận process đang hoạt động.
2. Mở JConsole từ máy client.
3. Ở cửa sổ **New Connection**, chọn **Remote Process**.
4. Nhập địa chỉ \`host:port\` mà JVM công bố, ví dụ \`127.0.0.1:9010\` cho bài lab.
5. Nếu endpoint yêu cầu credential, nhập username/password được cấp trong các ô tương ứng (hoặc quy trình xác thực của môi trường).
6. Nhấn **Connect**. Nếu có cảnh báo về kết nối không mã hóa, chỉ tiếp tục khi đây là lab cô lập đã được xác nhận an toàn; với môi trường thực tế, cần dùng đường kết nối bảo vệ.
7. Khi kết nối thành công, quan sát tab **MBeans**, kiểm tra đúng domain/ứng dụng.

Một service URL JMX/RMI điển hình:

\`\`\`text
service:jmx:rmi:///jndi/rmi://127.0.0.1:9010/jmxrmi
\`\`\`

Cấu trúc URL cụ thể phụ thuộc connector. Dùng URI được cấu hình/được cấp bởi hạ tầng thay vì tự đoán khi có custom connector.

### 9.1. Phân biệt lỗi endpoint và lỗi quyền

- **Connection refused:** thường không có tiến trình nghe trên địa chỉ/cổng, hoặc network/firewall từ chối.
- **Connection timed out:** đường mạng hoặc firewall chặn, hostname không tới được, hoặc cổng thứ hai của RMI không mở.
- **Authentication failed / SecurityException:** credential, chính sách xác thực hoặc authorization sai.
- **SSL/TLS handshake error:** SSL mode, truststore, certificate, protocol hoặc hostname verification có vấn đề.
- **Có kết nối nhưng thiếu MBean ứng dụng:** exporter không đăng ký, sai MBeanServer, ObjectName khác hoặc ứng dụng chưa khởi tạo thành phần.

Đọc lỗi theo đúng giai đoạn thất bại sẽ giúp tránh sửa nhầm ứng dụng khi sự cố thực tế nằm ở RMI hoặc mạng.

## 10. RMI, hostname, NAT và container

### 10.1. Vì sao port 9010 mở mà JConsole vẫn không kết nối?

Một JMX/RMI client có thể kết nối ban đầu tới RMI registry trên \`host:9010\`, nhận một RMI stub chứa địa chỉ/cổng của connector, rồi mở kết nối tiếp theo tới địa chỉ/cổng đó. Nếu stub công bố địa chỉ private như \`127.0.0.1\` của **server** cho client chạy trên máy khác, client sẽ thử tới localhost **của chính client** và thất bại.

Ví dụ:

\`\`\`text
Client 10.0.0.50                Server 10.0.0.20
      |                               |
      | TCP 9010 -> registry          |
      +------------------------------>|
      |                               |
      | RMI stub: 127.0.0.1:random    |
      |<------------------------------+
      |
      +--> 127.0.0.1:random (client localhost)
           Kết nối sai đích -> thất bại
\`\`\`

Khi dùng remote trực tiếp, \`java.rmi.server.hostname\` phải chứa địa chỉ mà client có thể định tuyến tới, đồng thời cổng RMI server cần cố định/mở đúng phạm vi. Nếu dùng tunnel, loopback được công bố phải tương thích thiết kế tunnel đó.

### 10.2. Trong Docker hoặc Kubernetes

Cần cân nhắc:

- JVM trong container có namespace mạng riêng.
- Cổng JVM lắng nghe bên trong container khác với cổng được map/expose ở host.
- \`java.rmi.server.hostname\` phải là địa chỉ client có thể đi tới sau cơ chế routing/NAT/tunnel.
- Việc map chỉ cổng registry không giải quyết được nếu RMI stub trả về một địa chỉ hoặc cổng không truy cập được.
- Trong Kubernetes, \`kubectl port-forward\` chỉ chuyển tiếp những port đã chỉ rõ; endpoint được RMI công bố cần phù hợp với kết nối đó.
- Container runtime, chính sách NetworkPolicy và ingress không tự hiểu hoặc sửa RMI stub.

Cách đơn giản để lab là cố định JMX port và RMI port bằng cùng một port, dùng một đường tunnel đã được kiểm soát, rồi kiểm tra cách client đi tới endpoint được stub công bố. Đối với production, quy trình network/security của tổ chức quyết định cấu hình thực tế.

## 11. Kết nối remote an toàn

JMX có thể cho phép xem dữ liệu, điều chỉnh thuộc tính và gọi operation thay đổi trạng thái ứng dụng. Đừng xem endpoint JMX như một HTTP health endpoint chỉ đọc.

### 11.1. Xác thực

Agent JMX/RMI chuẩn của HotSpot/OpenJDK có thể dùng password/access files. Các tùy chọn điển hình:

\`\`\`text
-Dcom.sun.management.jmxremote.authenticate=true
-Dcom.sun.management.jmxremote.password.file=/secure/path/jmxremote.password
-Dcom.sun.management.jmxremote.access.file=/secure/path/jmxremote.access
\`\`\`

Các file cần được bảo vệ bằng quyền filesystem phù hợp; agent có thể từ chối file password có quyền quá rộng. Cú pháp và quyền chi tiết phụ thuộc JVM/OS; tham khảo tài liệu JDK sử dụng trong môi trường thực tế.

Ví dụ access file minh họa:

\`\`\`text
monitorRole readonly
controlRole readwrite
\`\`\`

Ví dụ password file:

\`\`\`text
monitorRole <password-set-securely>
controlRole <another-password-set-securely>
\`\`\`

Đây là nội dung mẫu, không dùng mật khẩu literal trong tài liệu như credential thật. Những file này cần đặt ngoài source repository và đường dẫn được quản lý an toàn. Các quyền \`readonly\`/\`readwrite\` ở agent chỉ là một phần của chiến lược bảo mật; operation nào được công bố và lớp authorization bổ sung vẫn cần xem xét.

### 11.2. TLS và giới hạn mạng

Trong môi trường thực tế, nên:

- Dùng TLS/SSL được cấu hình và kiểm tra certificate/truststore phù hợp.
- Chỉ cho phép kết nối từ jump host, VPN, tunnel hoặc vùng mạng vận hành.
- Không mở cổng JMX rộng ra internet.
- Giữ credential trong secret manager hoặc cơ chế quản lý bí mật tương đương.
- Phân quyền theo nhu cầu đọc/điều khiển; tránh dùng tài khoản readwrite cho tác vụ monitoring.
- Có audit/log phù hợp cho operation quản trị nguy hiểm.
- Không xuất dữ liệu nhạy cảm qua getter/notification/ObjectName.

**Chú ý:** một số thiết lập SSL của JMX/RMI có thể yêu cầu cấu hình SSL riêng cho registry và connector. Nếu JConsole không bắt tay TLS, cần kiểm tra mode và tài liệu phiên bản JDK thay vì tắt bảo mật để “cho chạy”.

### 11.3. SSH tunnel như một cách giảm bề mặt mở cổng

Một thiết kế thực tế là chỉ nghe trên loopback hoặc mạng riêng, sau đó tạo đường hầm SSH từ máy vận hành tới máy chủ. Ví dụ khái niệm:

\`\`\`bash
ssh -L 9010:127.0.0.1:9010 operator@server.example
\`\`\`

Sau khi tunnel hoạt động, JConsole thử kết nối \`127.0.0.1:9010\`. Điều này đòi RMI stub quảng bá địa chỉ/cổng tương thích với tunnel, chẳng hạn port 9010/loopback. Đừng mặc định một tunnel cho registry port sẽ giải quyết được cấu hình RMI có port động hoặc hostname khác.

SSH tunnel không loại bỏ nhu cầu kiểm soát ai được phép SSH và ai được phép gọi JMX operation.

## 12. Dùng JConsole để đọc MBeans và thao tác

### 12.1. Attributes

Trong tab **MBeans**, chọn một ObjectName, mở mục **Attributes**. Công cụ hiển thị các attribute mà metadata cho phép đọc. Một số attribute writable có thể có giao diện cho phép sửa giá trị.

Ví dụ Standard MBean:

\`\`\`java
public interface CacheAdminMBean {
    long getEntryCount();
    boolean isEnabled();
    void setEnabled(boolean enabled);
}
\`\`\`

Đối với MBean này, JConsole có thể hiển thị \`EntryCount\` read-only và \`Enabled\` read/write. Thay đổi \`Enabled\` có tác dụng thật trên MBean, không chỉ trong giao diện.

### 12.2. Operations

Phần **Operations** liệt kê operation được công bố. Với thao tác có side effect như \`clearCache\` hoặc \`requestPause\`, việc bấm nút tương đương yêu cầu server thực hiện operation.

Nên đọc mô tả, xác nhận môi trường đúng và kiểm tra trạng thái trước/sau thao tác. Nếu client timeout sau khi invoke, không mặc định operation chưa chạy; server có thể đã bắt đầu xử lý.

### 12.3. Notifications

Một số MBean hỗ trợ JMX notifications. JConsole có thể cung cấp giao diện subscription ở phần Notifications tùy MBean và phiên bản công cụ. Nếu MBean không phát notification, tab đó không tự sinh ra sự kiện.

Để MBean phát sự kiện, nó cần cơ chế như \`NotificationBroadcaster\`/ \`NotificationEmitter\`, và client cần subscribe qua MBeanServerConnection hoặc UI phù hợp.

### 12.4. MBeanInfo và ObjectName

JConsole hiển thị cây dựa trên \`ObjectName\` như:

\`\`\`text
com.example:type=Cache,name=Products
java.lang:type=Memory
java.lang:type=Threading
\`\`\`

Nếu không tìm thấy MBean, kiểm tra domain, type, name, và xem nó có thực sự được đăng ký trong đúng MBeanServer. Một lỗi nhỏ trong ObjectName làm bạn nhìn sai nhánh cây.

## 13. Tích hợp Spring Framework và Spring Boot

### 13.1. Spring-managed MBeans

Trong Spring Framework, \`MBeanExporter\` có thể đăng ký các bean vào JMX. Ví dụ một bean quản trị:

\`\`\`java
package example.springjmx;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example:type=Worker,name=Import",
    description = "Import worker status"
)
public class ImportWorkerAdmin {

    @ManagedAttribute
    public long getProcessedCount() {
        return 42L;
    }

    @ManagedAttribute
    public boolean isHealthy() {
        return true;
    }
}
\`\`\`

Để metadata annotation có hiệu lực cần exporter/assembler cấu hình tương ứng. Có thể cấu hình Spring JMX theo tài liệu Spring hoặc dùng auto-configuration có điều kiện của Spring Boot. Chỉ có \`@Component\` và \`@ManagedResource\` không đủ để đảm bảo MBean được đăng ký trong mọi ứng dụng.

### 13.2. Cấu hình Spring Boot JMX

Tùy phiên bản Spring Boot, thuộc tính phổ biến:

\`\`\`properties
spring.jmx.enabled=true
\`\`\`

Thuộc tính này hỗ trợ auto-configure JMX export của Spring Boot khi điều kiện phù hợp. Nó không trực tiếp mở remote JMX port của JVM. Để JConsole từ máy khác truy cập, vẫn cần một connector/JMX remote agent hoặc cơ chế tương đương, kèm bảo mật.

Nếu dùng Spring Boot Actuator, các endpoint quản trị có thể được công bố theo cơ chế JMX và cấu hình exposure riêng. Không giả định cấu hình HTTP exposure áp dụng nguyên xi cho JMX; mỗi kênh cần xem xét riêng.

### 13.3. Những trường hợp không thấy MBean ứng dụng

Có thể do:

1. Bean chưa được exporter đăng ký.
2. JMX auto-configuration của Spring Boot không bật hoặc điều kiện thiếu.
3. Annotation JMX có mặt nhưng assembler không đọc metadata tương ứng.
4. ObjectName được tạo khác tên mong đợi.
5. ApplicationContext chưa hoàn tất khởi tạo hoặc MBean đã unregister.
6. JConsole kết nối nhầm JVM/PID.
7. Client kết nối một MBeanServer khác server chứa MBean.
8. Exporter báo trùng tên hoặc lỗi đăng ký MBean.

Cách xác minh trực tiếp trong code ứng dụng:

\`\`\`java
MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example:type=Worker,name=Import"
);

System.out.println(server.isRegistered(name));
\`\`\`

Nếu \`false\`, hãy kiểm tra quá trình xuất MBean thay vì xử lý firewall.

## 14. Bảng xử lý lỗi kết nối

| Triệu chứng | Nguyên nhân khả dĩ | Bước chẩn đoán |
| --- | --- | --- |
| Local Process không liệt kê ứng dụng | Sai user, attach disabled, khác namespace, JVM đã dừng | Xác nhận PID, tài khoản, quyền và trạng thái process |
| Chọn process nhưng kết nối bị từ chối | Agent không hoạt động, quyền attach, JVM không tương thích | Kiểm tra log và hỗ trợ local attach của JDK |
| Remote \`Connection refused\` | Port chưa nghe, sai host/port | Kiểm tra cấu hình JVM và listener |
| Remote timeout | Firewall, NAT, RMI secondary port không tới được | Kiểm tra cả registry port lẫn endpoint trong RMI stub |
| Kết nối registry thành công rồi thất bại | Stub quảng bá hostname/cổng sai | Kiểm tra \`java.rmi.server.hostname\`, \`jmxremote.rmi.port\` và mapping mạng |
| Authentication failed | Tài khoản/mật khẩu sai, access file lỗi | Kiểm tra cấu hình credentials và quyền filesystem |
| SSL handshake failed | Certificate, truststore, TLS mode khác nhau | Đối chiếu cấu hình SSL client/server |
| Kết nối được, không thấy MBean ứng dụng | Exporter không chạy, sai MBeanServer/ObjectName | Kiểm tra \`isRegistered\`, \`queryNames\` và exporter |
| MBeans xuất hiện nhưng operation không chạy | Thiếu quyền, signature sai, lỗi MBean | Kiểm tra metadata, exception và server logs |
| JConsole bị chậm/đơ | Getter tốn CPU, nhiều MBean, network chậm | Kiểm tra chi phí getter/polling, giới hạn dữ liệu |

Không nên vô hiệu hóa TLS hoặc xác thực để “sửa” lỗi production khi chưa hiểu nguyên nhân. Một lỗi configuration thường có thể khắc phục bằng đúng hostname, certificate hoặc quyền.

## 15. Quy trình chẩn đoán theo thứ tự

Để tránh kiểm tra lan man, đi theo chuỗi:

\`\`\`text
(1) JVM có đang chạy?
        |
        v
(2) Có MBeanServer và MBean cần quan sát?
        |
        v
(3) Local: JConsole có thấy đúng PID?
    Remote: registry endpoint có mở?
        |
        v
(4) Remote: RMI stub quảng bá host/port nào?
        |
        v
(5) Network/firewall/tunnel tới endpoint tiếp theo?
        |
        v
(6) Authentication/TLS/authorization hợp lệ?
        |
        v
(7) JConsole kết nối và khám phá MBeans?
        |
        v
(8) Xác minh giá trị và thao tác được cho phép.
\`\`\`

Nếu local attach không thành công, không nhất thiết phải cấu hình remote ngay; có thể kiểm tra JDK tool, PID, user và quyền hệ điều hành trước. Nếu remote registry thành công nhưng RMI stub sai, mở thêm firewall tùy tiện có thể không giải quyết được.

## 16. Minh họa chương trình JMX client thay cho GUI

Ngoài JConsole, Java code có thể kết nối tới cùng endpoint remote qua JMX API chuẩn:

\`\`\`java
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

JMXServiceURL url = new JMXServiceURL(
    "service:jmx:rmi:///jndi/rmi://127.0.0.1:9010/jmxrmi"
);

try (JMXConnector connector =
         JMXConnectorFactory.connect(url)) {

    MBeanServerConnection connection =
        connector.getMBeanServerConnection();

    ObjectName memory = new ObjectName(
        "java.lang:type=Memory"
    );

    Object heap = connection.getAttribute(
        memory,
        "HeapMemoryUsage"
    );

    System.out.println(heap);
}
\`\`\`

Trong thực tế, nếu remote JMX yêu cầu xác thực, truyền environment map chứa credentials phù hợp cho \`connect\`; nếu dùng TLS, cấu hình truststore/client đúng chính sách. Đoạn ví dụ dành cho endpoint lab không xác thực.

Phần API này cũng là nền tảng để tạo công cụ kiểm tra tự động, nhưng một collector nên ưu tiên getter nhẹ, giới hạn concurrency và polling rate.

### 16.1. Vì sao client không cần object ứng dụng?

\`MBeanServerConnection\` cung cấp \`getAttribute\`, \`invoke\`, \`queryNames\` và \`getMBeanInfo\`. Client chỉ cần biết \`ObjectName\`, tên thuộc tính/operation và loại giá trị JMX. Với MXBean/Open MBean, giá trị phức tạp có thể là \`CompositeData\` hoặc \`TabularData\` thay vì class ứng dụng riêng.

## 17. Những nhầm lẫn thường gặp

**“JConsole chỉ kết nối local.”** Không. Nó có lựa chọn Remote Process, nhưng remote JVM phải có connector và cấu hình mạng/bảo mật phù hợp.

**“Spring JMX enabled tự mở port remote.”** Không. Spring exporter đăng ký MBean; remote JMX port thuộc lớp JVM connector/agent riêng.

**“Chỉ cần mở một port bất kỳ cho RMI.”** Không hẳn. Registry port và endpoint được RMI stub công bố phải đều kết nối được. Cố định port thường đơn giản hóa firewall/NAT.

**“RMI hostname 127.0.0.1 luôn đúng.”** Chỉ đúng khi đường kết nối từ client thực sự dẫn tới loopback tương ứng, như local hoặc tunnel được cấu hình đồng bộ.

**“Có thể an toàn khi tắt authentication vì port khó đoán.”** Không. Port không phải cơ chế xác thực.

**“MBeans chỉ là read-only metrics.”** Không. MBean có thể có writable attributes và operations thay đổi trạng thái.

**“Không thấy MBean tức là JConsole lỗi.”** Thường cần kiểm tra exporter, ObjectName, đúng JVM và MBeanServer trước.

## 18. Bài tập thực hành

### Bài tập 1 — Local connection

Khởi chạy \`JmxDemoApplication\`, dùng \`jps -l\` tìm PID, mở \`jconsole\` và chọn đúng process. Ghi nhận domain \`java.lang\` và \`com.example\`, giá trị \`CompletedCount\`.

**Kết quả mong đợi:** thấy \`CompletedCount=42\` và operation \`resume\`.

### Bài tập 2 — Remote loopback lab

Chạy ứng dụng với JMX management agent trên \`127.0.0.1:9010\`, cấu hình \`port\` và \`rmi.port\` như ví dụ. Trong JConsole chọn Remote Process và nhập \`127.0.0.1:9010\`.

**Kết quả mong đợi:** kết nối thành công trên cùng host, truy cập được \`java.lang:type=Memory\` và MBean demo.

### Bài tập 3 — RMI hostname không tương thích

Trong một môi trường thử nghiệm cô lập, cấu hình hostname được quảng bá khác với địa chỉ có thể truy cập từ client, giữ registry port hoạt động, quan sát lỗi. Sau đó sửa \`java.rmi.server.hostname\` và cổng RMI để tương thích với topology.

**Kết quả mong đợi:** nhận biết sự khác nhau giữa kết nối registry và kết nối connector RMI.

### Bài tập 4 — Bảo vệ quyền

Dùng agent JMX cấu hình xác thực và access files trên môi trường lab, tạo role chỉ đọc và role có quyền quản trị. Thử đọc thuộc tính và gọi operation. Quan sát sự khác nhau giữa quyền của client và khả năng MBean công bố.

**Kết quả mong đợi:** hiểu vì sao phải phân quyền ngay cả khi operation hiện trên UI.

### Bài tập 5 — Spring

Tạo một \`@ManagedResource\` trong Spring, cấu hình exporter phù hợp, khởi chạy app. Kết nối JConsole local, tìm ObjectName đã đặt, xác nhận giá trị. Nếu không thấy, kiểm tra \`isRegistered\` và cấu hình exporter.

**Kết quả mong đợi:** phân biệt việc xuất MBean với việc kết nối JMX tới JVM.

## 19. Câu hỏi ôn tập

**1. JConsole lấy thông tin quản trị từ đâu?** Qua JMX API và MBeanServer, trực tiếp ở kết nối local phù hợp hoặc thông qua connector cho remote.

**2. Platform MBeanServer có tự mở remote port không?** Không. Cần agent/connector được cấu hình riêng.

**3. Khi nào dùng Local Process?** Khi JConsole và JVM chạy trên cùng host và quyền/cơ chế attach cho phép.

**4. Tại sao remote JMX có thể thất bại dù đã mở registry port?** Vì RMI stub có thể chỉ tới hostname hoặc cổng tiếp theo không truy cập được.

**5. \`java.rmi.server.hostname\` dùng để làm gì?** Chỉ định hostname được RMI export/quảng bá để client kết nối tới endpoint.

**6. Có nên tắt authentication/SSL trong production?** Không; chỉ dùng cấu hình không bảo vệ trong lab cô lập có chủ đích.

**7. Muốn thấy Spring bean trên JConsole cần gì?** Bean phải được xuất thành MBean bằng exporter hoặc cơ chế đăng ký phù hợp, và JConsole kết nối đúng MBeanServer/JVM.

**8. Vì sao phải thận trọng khi nhấn operation?** Vì operation có thể thay đổi trạng thái ứng dụng ngay trên server.

## 20. Tổng kết

JConsole là công cụ trực quan để quan sát JVM và quản trị MBean qua JMX. **Kết nối local** thường dựa trên việc phát hiện và attach vào JVM cùng máy; **kết nối remote** cần JMX connector có endpoint, hostname, cổng và bảo mật được cấu hình rõ ràng. Với JMX/RMI, phải xem xét cả registry port lẫn địa chỉ/cổng mà RMI stub công bố, đặc biệt qua firewall, NAT và container.

Trong ứng dụng Spring Framework, JConsole chỉ nhìn thấy những MBean đã được đăng ký bằng exporter hoặc cơ chế JMX tương ứng. Khi làm việc trên hệ thống thực tế, ưu tiên dữ liệu quản trị tối thiểu, quyền đọc phù hợp, kết nối được bảo vệ và xác minh thao tác trước khi thay đổi trạng thái.

## Tài liệu tham khảo

- JDK 21 — \`jconsole\` manual: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jconsole.html
- Oracle JMX Technology — Monitoring and Management: https://docs.oracle.com/javase/8/docs/technotes/guides/management/agent.html
- Java SE 21 — \`JMXConnector\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/remote/JMXConnector.html
- Java SE 21 — \`JMXServiceURL\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/remote/JMXServiceURL.html
- Java SE 21 — \`ManagementFactory\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ManagementFactory.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html