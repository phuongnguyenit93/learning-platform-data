# Bảo mật JMX khi kết nối bằng JConsole

JMX (Java Management Extensions) cung cấp giao diện để theo dõi và quản lý một JVM thông qua các MBean. JConsole dùng JMX để hiển thị heap, GC, thread, class loading, VM flags và các MBean của ứng dụng. Khi bật remote JMX, một client có thể đọc thông tin runtime và, nếu được cấp quyền, thay đổi thuộc tính hoặc gọi operation của MBean. Vì vậy, cổng JMX phải được bảo vệ như một giao diện quản trị có quyền cao.

Bảo mật JMX cần giải quyết bốn việc riêng: xác thực client, giới hạn quyền của client, mã hóa kết nối và bảo vệ điểm đăng ký RMI. Chỉ bật SSL hoặc chỉ đặt mật khẩu không tự động giải quyết cả bốn việc.

## 1. Mô hình bảo mật JMX

Một kết nối remote JMX đi qua các lớp sau:

1. **Network boundary:** firewall hoặc security group quyết định máy nào được phép kết nối tới các cổng JMX.
2. **TLS:** mã hóa dữ liệu trên đường truyền và xác minh danh tính máy chủ; mutual TLS còn xác minh chứng thư của client.
3. **Authentication:** xác định người dùng hoặc danh tính client, ví dụ password, certificate hoặc JAAS/LDAP.
4. **Authorization:** quyết định danh tính đó được đọc MBean, sửa thuộc tính hay gọi operation nào.

Các lớp này bổ sung cho nhau. TLS không tự quyết định một người dùng được phép gọi operation nào. Password authentication cũng không mã hóa dữ liệu nếu SSL bị tắt. Một firewall chỉ giới hạn nguồn kết nối; nó không thay thế authentication và authorization.

### 1.1. Authentication và authorization khác nhau

| Khái niệm | Câu hỏi | Ví dụ |
|---|---|---|
| Authentication | Client là ai? | Username/password, chứng thư client, LDAP |
| Authorization | Client được làm gì? | readonly hoặc readwrite trong access file |
| TLS server authentication | Client có đang kết nối đúng server không? | Client kiểm tra certificate của JMX server |
| TLS client authentication | Client có chứng thư được server tin cậy không? | Server yêu cầu certificate của client |

JMX có thể sử dụng nhiều cơ chế authentication. Với agent mặc định, password/access file là cách đơn giản để học và thử nghiệm. Trong môi trường doanh nghiệp, có thể tích hợp JAAS hoặc LDAP để dùng hệ thống danh tính sẵn có.

## 2. Local JMX và remote JMX

### 2.1. Kết nối local bằng JConsole

Trên Java SE hiện đại, JConsole có thể attach vào JVM cục bộ thông qua Attach API mà không cần bật thuộc tính com.sun.management.jmxremote từ lúc khởi chạy.

Chạy:

~~~bash
jconsole
~~~

JConsole liệt kê các JVM cục bộ mà tài khoản hiện tại có thể attach. Có thể chọn PID cụ thể:

~~~bash
jconsole 12345
~~~

JConsole và JVM đích phải chạy dưới cùng user vì kết nối local dựa trên quyền file của hệ điều hành. Với local connector, password/access file của remote JMX không được kiểm tra; ranh giới bảo mật chính là quyền của tài khoản OS được phép attach.

Local JConsole hữu ích khi phát triển và điều tra trực tiếp. Trong production, hãy cân nhắc tải do JConsole tạo ra và dùng remote monitoring từ máy quản trị riêng để tách công cụ khỏi JVM đang giám sát.

### 2.2. Remote JMX

Để kết nối từ máy khác, phải bật remote management khi khởi chạy JVM bằng thuộc tính:

~~~text
-Dcom.sun.management.jmxremote.port=<registry-port>
~~~

Ví dụ:

~~~bash
-Dcom.sun.management.jmxremote.port=9010
~~~

Remote JMX dùng RMI. Cổng jmxremote.port mở RMI registry để client tìm connector có tên jmxrmi. Cổng mà RMI connector thực sự bind có thể được cố định bằng:

~~~bash
-Dcom.sun.management.jmxremote.rmi.port=9011
~~~

Nên chỉ định cả hai cổng để cấu hình firewall rõ ràng. Nếu không cố định cổng RMI connector, nó có thể dùng một cổng động, khiến việc mở firewall và xử lý sự cố khó hơn.

Remote JMX không phải cổng HTTP của ứng dụng. Đây là cổng quản trị JVM; người có quyền readwrite có thể thay đổi MBean attribute và gọi MBean operation.

## 3. Các thuộc tính bảo mật quan trọng

Các thuộc tính sau áp dụng cho ready-to-use JMX agent của HotSpot:

| System property | Giá trị mặc định | Ý nghĩa |
|---|---|---|
| com.sun.management.jmxremote.port | Không có | Bật remote RMI connector và chỉ định cổng registry |
| com.sun.management.jmxremote.rmi.port | Không có | Cố định cổng RMI connector |
| com.sun.management.jmxremote.authenticate | true | Bật authentication bằng password/access file hoặc login module |
| com.sun.management.jmxremote.ssl | true | Bật TLS cho remote connector |
| com.sun.management.jmxremote.registry.ssl | false | Bảo vệ RMI registry bằng TLS |
| com.sun.management.jmxremote.ssl.need.client.auth | false | Yêu cầu client certificate khi TLS được bật |
| com.sun.management.jmxremote.password.file | JAVA_HOME/conf/management/jmxremote.password | Đường dẫn password file |
| com.sun.management.jmxremote.access.file | JAVA_HOME/conf/management/jmxremote.access | Đường dẫn access file |
| com.sun.management.jmxremote.login.config | File-based login | Chọn entry JAAS để xác thực |
| java.rmi.server.hostname | Địa chỉ host mặc định | Địa chỉ IP/DNS được ghi vào RMI stub gửi cho client |

Với remote JMX, password authentication và SSL được bật mặc định. Tuy nhiên, registry.ssl và client certificate authentication mặc định tắt. Muốn có cấu hình mạnh hơn cho production, hãy bật bảo vệ RMI registry và mutual TLS, đồng thời sử dụng cơ chế authentication phù hợp với tổ chức.

### 3.1. Đừng tắt security trên remote agent

Hai thuộc tính sau tắt cả password authentication và TLS:

~~~bash
-Dcom.sun.management.jmxremote.authenticate=false
-Dcom.sun.management.jmxremote.ssl=false
~~~

Khi đó, bất kỳ client từ xa nào kết nối được tới host và port đều có thể giám sát và quản lý JVM. Rủi ro vượt xa việc đọc số liệu: client có thể gọi operation của MBean, thay đổi trạng thái ứng dụng và trong một số cấu hình có thể nạp MBean để thực thi mã tùy ý.

Cấu hình này chỉ có thể chấp nhận trong môi trường thử nghiệm cô lập, không có đường truy cập từ mạng không tin cậy. Không dùng nó trong production.

## 4. Password file và access file

JMX agent mặc định dùng hai file trong:

~~~text
JAVA_HOME/conf/management/
~~~

JDK cung cấp mẫu jmxremote.password.template. Sao chép mẫu thành jmxremote.password, sau đó thêm các role và password riêng.

### 4.1. Password file

Ví dụ nội dung cho một môi trường lab:

~~~properties
monitorRole monitor-demo-only
controlRole control-demo-only
~~~

Tên role là phần đứng trước, password là phần sau. Password file lưu password dạng clear text. Không dùng mật khẩu tài khoản cá nhân hoặc mật khẩu đăng nhập hệ thống ở đây. Tạo credential riêng cho JMX và thay các giá trị demo bằng secret ngẫu nhiên trong môi trường thực.

Có thể đặt password file riêng cho từng instance:

~~~bash
-Dcom.sun.management.jmxremote.password.file=/etc/myapp/jmxremote.password
~~~

Trên Linux/macOS, chỉ owner được đọc và ghi:

~~~bash
chown appuser:appuser /etc/myapp/jmxremote.password
chmod 600 /etc/myapp/jmxremote.password
~~~

Trên Windows, bỏ quyền kế thừa và chỉ cấp quyền cho tài khoản chạy JVM, ví dụ:

~~~powershell
icacls C:\secure\jmxremote.password /inheritance:r /grant:r "DOMAIN\jmxsvc:(F)"
~~~

Đường dẫn và account trong ví dụ cần thay theo máy thực tế. JMX agent kiểm tra quyền của password file và có thể từ chối khởi động nếu người dùng khác cũng đọc được file. Đây là một kiểm tra bảo mật bắt buộc vì file chứa password dạng clear text.

### 4.2. Access file

Access file ánh xạ role sang mức quyền. Ví dụ:

~~~properties
monitorRole readonly
controlRole readwrite
~~~

Một role phải có mặt trong cả password file và access file mới đăng nhập được.

- readonly: đọc MBean attribute và đăng ký nhận notification; không được thực hiện hành động làm thay đổi môi trường của ứng dụng.
- readwrite: đọc/ghi attribute và gọi operation của MBean. Chỉ cấp cho client thực sự được phép quản lý ứng dụng.
- create và unregister là các quyền bổ sung có thể cấp cho role readwrite; chúng cho phép tạo hoặc xóa MBean. Chỉ cấp khi có nhu cầu cụ thể và đã xác minh class MBean được phép tạo.

Nếu role không có entry trong access file thì role đó không có quyền. Mỗi role chỉ nên có một entry để tránh nhầm lẫn khi có nhiều dòng trùng tên.

Có thể chỉ định access file riêng:

~~~bash
-Dcom.sun.management.jmxremote.access.file=/etc/myapp/jmxremote.access
~~~

Nếu password hoặc access file rỗng/không tồn tại trong khi authentication đang bật, client không có quyền truy cập hợp lệ. Agent cũng có thể thoát khi file sai định dạng hoặc không đọc được.

### 4.3. Phân quyền theo công việc

Một cấu hình thực tế nên có role đọc số liệu và role quản trị riêng:

| Vai trò | Quyền | Công việc phù hợp |
|---|---|---|
| monitorRole | readonly | Dashboard, kiểm tra heap, GC, thread và MBean |
| controlRole | readwrite | Quản trị viên cần gọi operation hoặc sửa thuộc tính MBean |

Không cấp readwrite cho mọi người chỉ vì họ cần xem biểu đồ. Một thao tác trong MBeans tab có thể thay đổi trạng thái ứng dụng, kích hoạt GC hoặc gọi operation do ứng dụng tự định nghĩa.

## 5. TLS, keystore và truststore

TLS bảo vệ tính bí mật và toàn vẹn của dữ liệu JMX trên đường truyền. Nó cũng giúp client xác minh server certificate.

- **Keystore:** lưu private key và certificate của chính máy.
- **Truststore:** lưu certificate/CA mà máy chấp nhận tin cậy.
- **Server certificate:** giúp JConsole xác minh đúng JMX server.
- **Client certificate:** giúp JMX server xác minh danh tính máy client khi bật mutual TLS.

### 5.1. Server-authenticated TLS

Tạo key pair và certificate cho JMX server bằng keytool, hoặc dùng certificate do CA của tổ chức cấp. Export certificate/CA chain và import vào truststore trên máy chạy JConsole.

Ví dụ tạo truststore cho client:

~~~bash
keytool -importcert -alias jmx-server \
  -file jmx-server.cer \
  -storetype PKCS12 \
  -keystore jmx-client-trust.p12
~~~

Khi chạy JMX server, chỉ định keystore:

~~~bash
-Djavax.net.ssl.keyStore=/etc/myapp/jmx-server.p12
-Djavax.net.ssl.keyStorePassword=secret-from-secure-launch-config
~~~

Trên JConsole, chỉ định truststore:

~~~bash
jconsole \
  -J-Djavax.net.ssl.trustStore=/secure/jmx-client-trust.p12 \
  -J-Djavax.net.ssl.trustStorePassword=secret-from-secure-launch-config
~~~

Sau đó kết nối tới host:port và nhập role/password trong hộp thoại Remote Process.

Certificate production nên được cấp bởi CA phù hợp với tổ chức, có SAN khớp hostname client sử dụng, có thời hạn và quy trình gia hạn/thu hồi rõ ràng. Certificate tự ký phù hợp cho lab; phải phân phối và xác minh fingerprint qua một kênh đáng tin trước khi import.

### 5.2. Mutual TLS: xác thực cả client

Khi bật:

~~~bash
-Dcom.sun.management.jmxremote.ssl.need.client.auth=true
~~~

JMX server yêu cầu client cung cấp certificate. Server truststore phải tin cậy certificate hoặc CA cấp certificate client. Phía JConsole cần keystore có private key/client certificate và truststore tin cậy server.

Với mutual TLS:

- Server keystore chứa private key và certificate của server.
- Server truststore chứa CA/certificate được phép cấp danh tính client.
- Client keystore chứa private key và certificate của client.
- Client truststore chứa CA/certificate dùng để xác minh server.

Oracle khuyến nghị dùng SSL client certificates để xác thực host client và authentication theo user để quản lý quyền người dùng. Nếu dùng JAAS/LDAP, có thể map danh tính đã xác thực sang role như monitorRole.

### 5.3. Bảo vệ cả RMI registry

Một chi tiết dễ bị bỏ qua là RMI registry. Theo tài liệu Oracle, khi client lấy connector stub từ một RMI registry không được bảo vệ, có nguy cơ client bị đánh lừa bởi registry giả và để lộ password, kể cả khi kết nối connector đã bật SSL.

Bảo vệ registry bằng:

~~~bash
-Dcom.sun.management.jmxremote.registry.ssl=true
-Dcom.sun.management.jmxremote.ssl.need.client.auth=true
~~~

Khi registry.ssl=true, Oracle yêu cầu bật client certificate authentication để có đầy đủ bảo vệ cho registry. Hãy kiểm thử cả JConsole và client JMX thực tế sau khi bật các thuộc tính này; cấu hình RMI registry và connector phải thống nhất với certificate/truststore của hai phía.

## 6. Cố định cổng và giới hạn mạng

RMI remote JMX thường dùng hai cổng:

- Registry port: com.sun.management.jmxremote.port.
- Connector port: com.sun.management.jmxremote.rmi.port.

Ví dụ:

~~~bash
-Dcom.sun.management.jmxremote.port=9010
-Dcom.sun.management.jmxremote.rmi.port=9011
~~~

Mở firewall chỉ cho hai cổng này từ máy quản trị hoặc subnet monitoring được phê duyệt. Không mở JMX trực tiếp ra Internet và không dùng chung cổng JMX giữa các instance.

RMI stub chứa địa chỉ host mà server công bố. Nếu server có nhiều NIC, chạy sau NAT hoặc dùng hostname nội bộ, cấu hình:

~~~bash
-Djava.rmi.server.hostname=jmx.example.internal
~~~

Giá trị này là địa chỉ được quảng bá trong stub, không phải quy tắc firewall và không tự giới hạn interface lắng nghe. Nếu registry kết nối được nhưng connector không kết nối được, hãy kiểm tra địa chỉ stub, cổng RMI cố định và firewall cho cả hai cổng.

## 7. Kết nối JConsole tới JMX đã bảo vệ

### 7.1. Kết nối remote

Cú pháp:

~~~bash
jconsole hostName:portNum
~~~

Ví dụ:

~~~bash
jconsole jmx.example.internal:9010
~~~

Trong hộp thoại Remote Process, nhập:

- Host: hostname/IP của server.
- Port: giá trị com.sun.management.jmxremote.port.
- Username/password: role được khai báo trong password file hoặc hệ thống authentication đang dùng.

### 7.2. Kết nối remote qua TLS

Khởi chạy JConsole với truststore của client:

~~~bash
jconsole \
  -J-Djavax.net.ssl.trustStore=/secure/jmx-client-trust.p12 \
  -J-Djavax.net.ssl.trustStorePassword=secret-from-secure-launch-config \
  jmx.example.internal:9010
~~~

Nếu server yêu cầu mutual TLS, bổ sung keystore client:

~~~bash
-J-Djavax.net.ssl.keyStore=/secure/jmx-client.p12
-J-Djavax.net.ssl.keyStorePassword=secret-from-secure-launch-config
~~~

JConsole dùng -J để truyền system property cho JVM chạy JConsole. Khi mở hộp thoại kết nối, nhập role/password theo cấu hình agent.

### 7.3. Đọc và quản lý MBeans

Sau khi kết nối thành công, JConsole hiển thị các tab Overview, Memory, Threads, Classes, VM và MBeans. Với role readonly, người vận hành có thể xem metrics và nhận notification. Các thao tác ghi hoặc gọi operation sẽ bị từ chối. Với role readwrite, JConsole có thể thực hiện những thao tác mà MBean cho phép.

Hãy thử kết nối bằng monitorRole trước để xác minh quyền đọc. Chỉ dùng controlRole khi cần thực hiện thay đổi đã được phê duyệt.

## 8. Ví dụ thực hành Java 17+: kiểm tra authentication và role

Ví dụ này tạo một MBean có thuộc tính Value. Client monitorRole có thể đọc thuộc tính nhưng không thể sửa. Client controlRole có thể đọc và cập nhật thuộc tính.

Tạo bốn file sau trong cùng thư mục.

ProbeMBean.java:

~~~java
public interface ProbeMBean {
    String getValue();
    void setValue(String value);
}
~~~

Probe.java:

~~~java
public final class Probe implements ProbeMBean {
    private volatile String value = "initial";

    public String getValue() {
        return value;
    }

    public void setValue(String value) {
        this.value = value;
    }
}
~~~

JmxTarget.java:

~~~java
import java.lang.management.ManagementFactory;
import java.util.concurrent.CountDownLatch;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public final class JmxTarget {
    public static void main(String[] args) throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();
        server.registerMBean(
            new Probe(),
            new ObjectName("demo:type=Probe")
        );

        System.out.println("JMX_TARGET_READY");
        new CountDownLatch(1).await();
    }
}
~~~

JmxClient.java:

~~~java
import java.util.HashMap;
import java.util.Map;
import javax.management.Attribute;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

public final class JmxClient {
    private static boolean hasSecurityCause(Throwable error) {
        for (Throwable cause = error; cause != null; cause = cause.getCause()) {
            if (cause instanceof SecurityException) {
                return true;
            }
        }
        return false;
    }

    public static void main(String[] args) throws Exception {
        String user = System.getenv("JMX_USER");
        String password = System.getenv("JMX_PASSWORD");

        if (user == null || password == null) {
            throw new IllegalStateException("Set JMX_USER and JMX_PASSWORD");
        }

        Map<String, Object> environment = new HashMap<>();
        environment.put(
            JMXConnector.CREDENTIALS,
            new String[] { user, password }
        );

        JMXServiceURL url = new JMXServiceURL(
            "service:jmx:rmi:///jndi/rmi://127.0.0.1:7111/jmxrmi"
        );

        try (JMXConnector connector =
                 JMXConnectorFactory.connect(url, environment)) {
            MBeanServerConnection connection =
                connector.getMBeanServerConnection();
            ObjectName name = new ObjectName("demo:type=Probe");

            System.out.println(
                "READ_VALUE=" + connection.getAttribute(name, "Value")
            );

            if ("monitor".equals(args[0])) {
                try {
                    connection.setAttribute(
                        name,
                        new Attribute("Value", "monitor-updated")
                    );
                    throw new IllegalStateException(
                        "Read-only role unexpectedly wrote"
                    );
                } catch (Exception error) {
                    if (!hasSecurityCause(error)) {
                        throw error;
                    }
                    System.out.println("WRITE_DENIED=SecurityException");
                }
            } else {
                connection.setAttribute(
                    name,
                    new Attribute("Value", "control-updated")
                );
                System.out.println(
                    "WRITE_ALLOWED=" + connection.getAttribute(name, "Value")
                );
            }
        }
    }
}
~~~

Biên dịch:

~~~bash
javac --release 17 -d out ProbeMBean.java Probe.java JmxTarget.java JmxClient.java
~~~

Tạo file jmxremote.password cho môi trường lab:

~~~properties
monitorRole monitorPass
controlRole controlPass
~~~

Tạo file jmxremote.access:

~~~properties
monitorRole readonly
controlRole readwrite
~~~

Chỉ dùng các password ví dụ trong máy thử nghiệm. Đặt ACL của password file chỉ cho tài khoản khởi chạy JVM đọc/ghi. Trên Linux/macOS:

~~~bash
chmod 600 jmxremote.password
~~~

Chạy JMX target trong môi trường lab với TLS server authentication và password/access file:

~~~bash
java \
  -Dcom.sun.management.jmxremote.port=7111 \
  -Dcom.sun.management.jmxremote.rmi.port=7112 \
  -Dcom.sun.management.jmxremote.authenticate=true \
  -Dcom.sun.management.jmxremote.password.file=/secure/jmxremote.password \
  -Dcom.sun.management.jmxremote.access.file=/secure/jmxremote.access \
  -Dcom.sun.management.jmxremote.ssl=true \
  -Djavax.net.ssl.keyStore=/secure/jmx-server.p12 \
  -Djavax.net.ssl.keyStorePassword=changeit \
  -Djava.rmi.server.hostname=127.0.0.1 \
  -cp out JmxTarget
~~~

Stdout chính xác:

~~~text
JMX_TARGET_READY
~~~

Đây là cấu hình lab để kiểm tra authentication và role trên máy thử nghiệm. RMI registry SSL và mutual TLS chưa được bật trong fixture này; cấu hình production phải bổ sung các thuộc tính bảo vệ registry/client certificate ở phần trước, đồng thời giới hạn firewall cho cả hai cổng.

Trong terminal thứ hai, cấu hình truststore chứa certificate/CA của server. Với shell Bash, ví dụ:

~~~bash
export JMX_USER=monitorRole
export JMX_PASSWORD=monitorPass
java \
  -Djavax.net.ssl.trustStore=/secure/jmx-client-trust.p12 \
  -Djavax.net.ssl.trustStorePassword=changeit \
  -cp out JmxClient monitor
~~~

Output:

~~~text
READ_VALUE=initial
WRITE_DENIED=SecurityException
~~~

Thử role quản trị:

~~~bash
export JMX_USER=controlRole
export JMX_PASSWORD=controlPass
java \
  -Djavax.net.ssl.trustStore=/secure/jmx-client-trust.p12 \
  -Djavax.net.ssl.trustStorePassword=changeit \
  -cp out JmxClient control
~~~

Output:

~~~text
READ_VALUE=initial
WRITE_ALLOWED=control-updated
~~~

Thử password sai sẽ làm kết nối thất bại với lỗi Authentication failed! Invalid username or password.

Ví dụ dùng biến môi trường để tránh đặt password trong command argument. Biến môi trường chỉ là cách truyền credential cho lab; production nên dùng secret manager, login provider hoặc prompt an toàn, giới hạn quyền process và không ghi secret vào source code, shell history hay log.

## 9. JAAS/LDAP cho môi trường doanh nghiệp

Khi cần quản lý danh tính tập trung, JMX agent có thể dùng JAAS login module thay cho file password mặc định. Oracle cung cấp com.sun.security.auth.module.LdapLoginModule để xác thực với LDAP.

Các thuộc tính liên quan:

~~~bash
-Dcom.sun.management.jmxremote.login.config=CompanyJmx
-Djava.security.auth.login.config=/etc/myapp/jmx-jaas.config
~~~

Entry JAAS định nghĩa login module, LDAP provider/filter và authzIdentity để ánh xạ người dùng đã xác thực sang role JMX. Ví dụ, một nhóm vận hành có thể được ánh xạ vào monitorRole, trong khi nhóm quản trị được ánh xạ vào role có quyền cao hơn.

Khi dùng JAAS/LDAP, vẫn cần TLS để bảo vệ credentials và traffic, access policy để giới hạn quyền MBean, cùng network control cho các cổng RMI. LDAP authentication không tự thay thế TLS hoặc firewall.

## 10. Lỗi thường gặp và cách xử lý

| Lỗi/tình huống | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Authentication failed! Invalid username or password | Username/password không khớp password file hoặc login provider | Kiểm tra role, password, file path và credential của JConsole |
| Access denied khi sửa attribute | Client đăng nhập bằng role readonly | Dùng role readwrite chỉ khi được phép thay đổi |
| JMX agent thoát lúc startup | Password file có quyền đọc quá rộng, file sai định dạng hoặc thiếu file | Kiểm tra owner-only ACL, file path và định dạng |
| Address already in use | Registry hoặc connector port đã được process khác sử dụng | Chọn hai port chưa dùng và cập nhật firewall |
| Connection refused / timeout | Sai host/port, firewall chặn hoặc agent chưa bật | Xác nhận registry port, RMI port và trạng thái agent |
| Registry kết nối được nhưng connector thất bại | RMI stub quảng bá hostname/IP không truy cập được hoặc RMI port bị chặn | Kiểm tra java.rmi.server.hostname và jmxremote.rmi.port |
| SSLHandshakeException | Client không tin server certificate, certificate hết hạn hoặc client cert không được tin | Kiểm tra chain, SAN, truststore, keystore và thời hạn certificate |
| Client certificate bị từ chối | Server bật mutual TLS nhưng truststore không tin certificate/CA của client | Import đúng CA/client certificate vào server truststore |
| JConsole không thấy local JVM | Khác user, Attach API bị tắt hoặc JVM không attach được | Chạy JConsole bằng cùng user và kiểm tra chính sách/runtime |
| Remote JMX không hoạt động qua NAT/multihomed host | RMI stub quảng bá địa chỉ không thể truy cập từ client | Đặt java.rmi.server.hostname thành hostname/IP client có thể truy cập |
| Chạy được local nhưng remote thất bại | Remote agent chưa bật hoặc firewall chưa cho cả hai cổng | Cấu hình jmxremote.port, jmxremote.rmi.port và network rule |

## 11. Quy trình triển khai JMX an toàn

1. Xác định máy quản trị và nhóm người dùng cần truy cập.
2. Chọn hai cổng RMI cố định; chỉ cho phép subnet quản trị kết nối.
3. Cấp server certificate từ CA được tin cậy và cấu hình keystore/truststore.
4. Bật SSL và xác thực client certificate; bảo vệ RMI registry bằng registry.ssl=true.
5. Chọn authentication provider: JAAS/LDAP hoặc cơ chế được tổ chức quản lý.
6. Tạo role đọc và role quản trị riêng; cấp readonly mặc định cho monitoring.
7. Bảo vệ password/access/config files bằng ACL phù hợp; không để secret trong source code hoặc log.
8. Cấu hình java.rmi.server.hostname thành địa chỉ mà client thực sự truy cập được.
9. Kiểm tra JConsole bằng role readonly; xác minh thao tác ghi bị từ chối.
10. Kiểm tra role quản trị trong một phiên có kiểm soát và xác minh operation được phép.
11. Kiểm tra certificate expiry, rotation, access review và log vận hành định kỳ.
12. Khi kết thúc sự cố, disconnect JConsole và thu hồi quyền tạm thời nếu có.

## 12. Checklist trước khi mở remote JMX

- [ ] Remote authentication đang bật.
- [ ] TLS đang bật và client xác minh được server certificate.
- [ ] RMI registry được bảo vệ bằng TLS.
- [ ] Mutual TLS được bật nếu dùng client certificate.
- [ ] Authentication dùng password/JAAS/LDAP theo chính sách.
- [ ] readonly và readwrite được tách biệt.
- [ ] Password file chỉ owner được đọc/ghi nếu vẫn sử dụng file-based login.
- [ ] Không dùng password tài khoản cá nhân trong password file.
- [ ] Registry port và RMI connector port được cố định.
- [ ] Firewall chỉ cho phép máy quản trị cần thiết.
- [ ] RMI stub quảng bá hostname/IP mà client truy cập được.
- [ ] Không tắt đồng thời authentication và SSL.
- [ ] Đã thử quyền đọc và quyền ghi bằng hai role khác nhau.
- [ ] Có quy trình rotate certificate, password và review quyền.

## 13. Ghi nhớ

JConsole là client quản trị JMX; quyền của nó đến từ JMX agent và MBean server mà nó kết nối. Local connection dựa trên cùng user OS và Attach API. Remote connection cần cổng RMI, TLS, authentication và authorization rõ ràng.

Dùng readonly cho monitoring, chỉ cấp readwrite cho người vận hành cần thay đổi ứng dụng. Với remote production, bảo vệ cả connector lẫn RMI registry, dùng mutual TLS và login provider phù hợp, cố định hai cổng RMI và giới hạn firewall. Không tắt authentication/SSL trên một JMX endpoint có thể truy cập từ mạng.

Tài liệu tham khảo:

- [Monitoring and Management Using JMX Technology — Java SE 21](https://docs.oracle.com/en/java/javase/21/management/monitoring-and-management-using-jmx-technology.html)
- [Using JConsole — Java SE 21](https://docs.oracle.com/en/java/javase/21/management/using-jconsole.html)
- [Java SE 21 Monitoring and Management Guide (PDF)](https://docs.oracle.com/en/java/javase/21/management/java-se-monitoring-and-management-guide.pdf)
- [The keytool Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/keytool.html)