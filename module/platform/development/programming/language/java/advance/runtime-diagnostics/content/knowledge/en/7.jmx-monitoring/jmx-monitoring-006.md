# 7.6 Xác thực, TLS và phân quyền đọc hoặc điều khiển trên kênh quản lý

**JMX (Java Management Extensions)** hỗ trợ đọc và quản lý trạng thái của JVM cùng ứng dụng thông qua **MBeans**. Ta có thể xem heap, GC, class loading, thread count, health và các metric nghiệp vụ; nhưng cũng có thể gặp những MBean cho phép sửa cấu hình hoặc gọi operation làm thay đổi runtime. Một cổng JMX Remote mở sai chính sách có thể biến giao diện chẩn đoán thành kênh điều khiển nhạy cảm.

Muốn bảo vệ **kênh quản lý JMX**, phải phân biệt ba câu hỏi độc lập:

- **Authentication — Ai đang kết nối?** Ví dụ danh tính username/password, JAAS hoặc chứng chỉ TLS client.
- **TLS — Kết nối có bảo mật và client có xác minh đúng máy chủ không?** Bao gồm encryption, certificate chain, hostname và đôi khi mutual TLS (mTLS).
- **Authorization — Sau khi được xác thực, người đó được làm gì?** Ví dụ **readonly** cho người giám sát, **readwrite** cho người được phép thao tác điều khiển.

Bài này tập trung vào **JDK 21/HotSpot ready-to-use management agent** dùng JMX Remote với **RMI connector**. Các thuộc tính **com.sun.management.jmxremote.*** là đặc trưng của cấu hình JDK/HotSpot, không phải cam kết mọi JVM Java SE 21 đều triển khai cùng cơ chế. Ví dụ mạng, file và PID dùng để học, không phải thông tin của hệ thống production.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **MBeanServer**, **JMX connector**, **RMI registry**, local Attach API và remote management.
2. Giải thích sự khác biệt **TLS server authentication**, **mTLS client authentication**, tài khoản JMX và quyền MBean.
3. Thiết kế một file **jmxremote.access** cho monitor readonly và operator readwrite theo nguyên tắc **least privilege**.
4. Nắm cơ chế **jmxremote.password**, yêu cầu quyền file và lý do không dùng file password plaintext tùy tiện trong production.
5. Hiểu hệ quả của **authenticate=false**, **ssl=false** và việc registry có thể chưa được TLS-protected.
6. Biết cách đặt **jmxremote.port**, **jmxremote.rmi.port**, **java.rmi.server.hostname** và các giới hạn RMI trong Docker/Kubernetes.
7. Kiểm tra thật việc đọc **getAttribute** được phép còn ghi **setAttribute** hoặc **invoke** bị chặn với role readonly.
8. Chuẩn bị keystore/truststore và kiểm chứng certificate mà không nhúng secret vào source code/arguments.
9. Phân biệt lỗi network, TLS handshake, authentication và authorization khi điều tra kết nối JMX.
10. Đặt giới hạn cho cả remote JMX, local attach, Kubernetes RBAC và các phiên truy cập đã tồn tại.

## 2. Bức tranh các lớp bảo mật

~~~text
Operator / JConsole / monitoring service
          |
          |  (A) Network controls: firewall, VPN, allowlist, tunnel
          v
RMI registry / JMX connector
          |
          |  (B) TLS: mã hóa, tin server, có yêu cầu client cert?
          |  (C) Authentication: principal nào đã đăng nhập?
          v
Authorization / MBeanServerForwarder
          |
          |  (D) readonly hay readwrite? operation nào?
          v
Platform MBeans và Application MBeans
~~~

| Lớp | Kiểm soát | Không tự thay thế |
| --- | --- | --- |
| **Mạng** | Nguồn client có thể tới cổng registry/connector. | Không xác nhận danh tính user hay operation được gọi. |
| **TLS** | Bảo mật đường truyền và xác thực peer theo certificate. | Không tự cấp/giới hạn quyền MBean. |
| **Authentication** | Xác nhận user hoặc client identity. | Không tự đảm bảo user chỉ được đọc. |
| **Authorization** | Chặn/cho các hoạt động getAttribute, setAttribute, invoke. | Không mã hóa dữ liệu hoặc mở/đóng cổng mạng. |
| **Audit** | Biết ai truy cập, thay đổi gì, khi nào. | Không tự ngăn kết nối trái phép. |

**Kết nối được không đồng nghĩa tin cậy. Có TLS không đồng nghĩa readonly. Có username/password không đồng nghĩa dữ liệu được mã hóa.** Ba sự nhầm lẫn này dẫn tới nhiều sự cố quản trị từ xa.

## 3. Phân biệt local JMX và remote JMX

Trên HotSpot JDK 21, **local JMX/Attach API** có thể cho phép công cụ như JConsole gắn vào JVM ở cùng host theo điều kiện **OS user và file permissions**. Tài liệu JDK mô tả private local connector và nêu rằng **password/access files của remote agent không được kiểm tra cho các yêu cầu đi qua local connector**.

Do đó:

- File **jmxremote.access** có dòng **monitorRole readonly** không chứng minh mọi tiến trình chạy cùng OS user trên máy có thể **chỉ đọc**.
- Người có quyền exec vào cùng container, đọc secret, attach hoặc chạy code trong cùng process có thể có một đường điều khiển **khác** với remote connector.
- Lệnh **jcmd PID ...** dựa trên diagnostic/attach mechanism, không phải một đăng nhập JMX Remote bằng monitorRole.
- Phải quản lý cả **OS permissions, PID/namespace, quyền exec/attach, container isolation** lẫn remote JMX authentication.

Đối với **remote management**, cần cấu hình JMX agent/connector nghe ở cổng phù hợp. Trên ready-to-use agent, **com.sun.management.jmxremote.port** bật RMI remote endpoint. Các cổng này chịu kiểm soát authentication, TLS và access file đã cấu hình; không nên coi chúng có cùng đặc tính với local connector.

### 3.1. Một ví dụ về kiểm thử nhầm đường

Bạn chạy JConsole trên cùng node bằng account của Java process và thấy có thể sửa attribute của MBean. Bạn lại có **monitorRole readonly** trong access file nên cho rằng policy bị bỏ qua.

Có thể bạn chỉ đang kết nối **local Attach**. Hãy thử bằng **remote JMX service URL thực sự**, sử dụng monitorRole và đúng TLS/certificate. Nếu thử local để chứng minh remote authorization, kết luận sẽ sai. Ngược lại, khi local attach rộng quá mức, phải sửa **quyền ở lớp OS/deployment**, không chỉ sửa file role remote.

## 4. Authentication bằng password file

### 4.1. Hai file khác chức năng

Agent dùng hai file riêng:

- **jmxremote.password**: principal/role tương ứng với một password, hoặc thay bằng cơ chế đăng nhập được hỗ trợ.
- **jmxremote.access**: principal/role tương ứng với **readonly** hoặc **readwrite**, có thể có điều khoản bổ sung.

Một identity muốn dùng file-based login phải được khai báo hợp lệ ở cả hai. Những tên **monitorRole** và **controlRole** trong tài liệu chỉ là các ví dụ phổ biến, không phải tài khoản mặc định đã có mật khẩu.

Đường dẫn cấu hình minh họa:

~~~properties
com.sun.management.jmxremote.authenticate=true
com.sun.management.jmxremote.password.file=/run/secrets/jmxremote.password
com.sun.management.jmxremote.access.file=/etc/jmx/jmxremote.access
~~~

Các dòng là **phần của cấu hình**, chưa phải toàn bộ cấu hình remote agent. Mặc định những file này thường nằm trong **$JAVA_HOME/conf/management** với bản JDK phù hợp; dùng đường dẫn riêng để quản lý theo từng ứng dụng và chính sách secret.

### 4.2. Password file có ràng buộc bảo mật

Theo tài liệu JDK 21, file-based JMX password thường được lưu theo dạng Java properties với **giá trị password clear text** và được xem là cách tiếp cận thích hợp hơn cho phát triển/kiểm soát hẹp. Production nên kết hợp chứng chỉ client và/hoặc JAAS/login module theo chính sách danh tính được duyệt.

Trên Linux/macOS, password file cần có permission chỉ owner đọc/ghi, điển hình **0600**. JDK kiểm tra permission để hạn chế secret bị đọc bởi user khác; nếu file có quyền quá rộng, agent có thể từ chối startup.

~~~bash
# Chỉ xem metadata, không in mật khẩu
ls -l /run/secrets/jmxremote.password
stat /run/secrets/jmxremote.password
~~~

**Không dùng cat/echo để đưa secret thật vào terminal chia sẻ hoặc CI log.** Hạn chế quyền trên cả folder, secret volume và quyền root/exec của container. File phải thực sự tồn tại trong **filesystem/mount namespace của JVM** và JVM user có quyền đọc. Có file tên đúng trên host chưa chắc container JVM nhìn thấy nó.

### 4.3. authenticate=false là thay đổi quyền nguy hiểm

Tùy chọn sau **không phải cấu hình production được khuyến nghị**:

~~~properties
com.sun.management.jmxremote.authenticate=false
~~~

Với ready-to-use JMX agent, nó **vô hiệu hóa việc dùng password/access files**. Những client được phép kết nối có thể có toàn quyền theo mô hình agent, ngay cả khi file access còn chứa **monitorRole readonly**. **Mạng nội bộ không khắc phục lỗ hổng phân quyền này**.

Cấu hình kết hợp **authenticate=false** và **ssl=false** đặc biệt nguy hiểm: không còn password-based authentication/role enforcement lẫn encryption trên connector. Không dùng nó như cách khắc phục tạm khi JConsole không kết nối được.

Nếu thiết kế dựa trên mTLS client certificates mà không sử dụng password, cần một **kiến trúc authentication/authorization đã xác minh**. Không tự suy ra việc nhận chứng chỉ client đồng nghĩa principal chỉ có quyền readonly.

### 4.4. JAAS, LDAP và cách xác thực thay thế

Với ready-to-use agent, cơ chế **JAAS** có thể được chọn qua property **com.sun.management.jmxremote.login.config** cùng cấu hình login phù hợp. JMX API cũng có **JMXAuthenticator** cho connector tùy biến.

~~~properties
com.sun.management.jmxremote.login.config=EnterpriseJmxLogin
~~~

**EnterpriseJmxLogin** là tên login entry minh họa; sẽ chỉ hoạt động khi được khai báo và được JVM nạp theo JAAS config thật. Identity trả về sau xác thực phải được **gắn đúng role/policy**. Một LDAP login thành công không tự cấp quyền readwrite; người vận hành vẫn phải kiểm tra access mapping, auditing và session lifecycle.

## 5. Authorization: readonly và readwrite

Ví dụ file **jmxremote.access**:

~~~properties
monitorRole readonly
controlRole readwrite
~~~

| Quyền | Ví dụ | Khuyến nghị |
| --- | --- | --- |
| **readonly** | Đọc MBean attributes, xem metadata, nhận notifications. | Tài khoản monitoring/dashboard cần đọc dữ liệu. |
| **readwrite** | Đọc/sửa writable attributes, gọi MBean operations. | Chỉ cho người điều khiển tin cậy, có quy trình chấp thuận. |
| **create/unregister** (tùy policy) | Tạo hoặc hủy đăng ký MBean. | Chỉ cấp khi có nhu cầu rõ, giới hạn class và quyền. |

**readonly** giới hạn thao tác làm thay đổi trạng thái qua **remote connector được access controller bảo vệ**. Tuy nhiên một getter do ứng dụng tự viết vẫn có thể **chậm, tạo side effect hoặc lộ dữ liệu nhạy cảm** nếu implementation không an toàn. “Read-only” không có nghĩa “ai cũng nên đọc”.

**readwrite** có thể cho phép thay đổi hệ thống rộng hơn mong đợi. Nó không phải quyền chỉ sửa một attribute cụ thể. Nếu doanh nghiệp cần **team A chỉ chỉnh feature flag X** và **team B chỉ xem MBean Y**, các quyền readonly/readwrite đơn giản là chưa đủ chi tiết.

### 5.1. Access file không phải fine-grained RBAC theo method

Java JMX hỗ trợ cấu hình bảo mật phức tạp hơn, chẳng hạn **MBeanServerForwarder** hoặc application-level security. Chúng có thể chặn từng ObjectName/operation/identity nếu được triển khai đúng.

File ready-to-use access thường có role mức **coarse-grained**. Đừng tự cho rằng nó hiểu wildcard operation trong domain ứng dụng mà không có bằng chứng. Cần thiết kế một **management gateway** hoặc controller có policy chi tiết khi thao tác điều khiển quá nhạy cảm.

### 5.2. Lưu ý create và unregister

JDK 21 cho phép entry **readwrite** kèm các mệnh đề **create** và/hoặc **unregister**. Điều này cho phép những hành động còn mạnh hơn đọc/ghi thuộc tính. File access mẫu đi kèm JDK có thể cấp role control những quyền bổ sung. **Phải đọc file thực tế JVM đang dùng**.

Không cấp **create** cho mọi class tùy ý. MBean creation có thể mở rộng bề mặt thực thi code của process; chỉ những class tin cậy và các use case đã duyệt mới nên được cấp. Với mục tiêu quan sát, **monitorRole readonly** gần như luôn phù hợp hơn.

## 6. TLS: mã hóa và xác minh peer

Khi **com.sun.management.jmxremote.ssl=true**, JMX connector sử dụng SSL/TLS theo cấu hình agent. Tài liệu JDK 21 nói SSL được bật mặc định cho remote management nhưng **vẫn phải provision certificate/keystore/truststore đúng**. Nếu chưa thiết lập trust chain, bật ssl=true không làm kết nối tự thành công.

**TLS một chiều**:

1. Server có private key/certificate trong **keystore**.
2. Client có trust anchors trong **truststore** và xác minh đúng server.
3. Client phải xác minh certificate chain, hostname/SAN, expiry và thuật toán được tin.
4. Luồng qua connector được mã hóa theo TLS session.

**Mutual TLS (mTLS)**:

1. Server chứng minh danh tính với client.
2. Client cũng đưa certificate; server xác minh với client truststore.
3. Danh tính chứng chỉ là một lớp authentication; quyền thao tác MBean vẫn cần authorization.

Ví dụ những property JSSE có liên quan:

~~~properties
javax.net.ssl.keyStore=/run/secrets/jmx-server.p12
javax.net.ssl.keyStoreType=PKCS12
javax.net.ssl.trustStore=/run/secrets/jmx-client-trust.p12
javax.net.ssl.trustStoreType=PKCS12
~~~

Đây là **sơ đồ vị trí file**, không đủ để khởi chạy: cần keystore/truststore thực sự, certificate chain, password/secret injection, SAN đúng với địa chỉ kết nối và chính sách certificate lifecycle. Không gửi private key lên kho git hoặc để store passwords trong script chia sẻ.

### 6.1. Các tham số JDK 21 cần nhớ

| Property | Ý nghĩa |
| --- | --- |
| **com.sun.management.jmxremote.ssl=true** | Bật TLS của remote connector. |
| **com.sun.management.jmxremote.ssl.need.client.auth=true** | Yêu cầu xác thực client certificate khi connector TLS. |
| **com.sun.management.jmxremote.registry.ssl=true** | Bật TLS cho **RMI registry**, là thành phần riêng. |
| **com.sun.management.jmxremote.ssl.enabled.protocols** | Chọn các TLS protocol versions được phép. |
| **com.sun.management.jmxremote.ssl.enabled.cipher.suites** | Chọn cipher suites được phép. |
| **javax.net.ssl.keyStore** | Key/cert phù hợp của peer. |
| **javax.net.ssl.trustStore** | Trust anchors để kiểm tra certificate của peer. |

Không copy bộ TLS ciphers/protocols từ cấu hình JDK cũ vào production. Phải theo Java 21 vendor, các thuật toán đã bị vô hiệu hóa trong **java.security**, PKI và client thực tế. Không tắt certificate validation hoặc bỏ qua hostname checking để “sửa” SSLHandshakeException.

## 7. RMI registry và connector: hai ranh giới riêng

RMI-based JMX remote client thường đi qua hai giai đoạn:

~~~text
JMX client
    |
    +--- RMI registry: jmxremote.port
    |           |
    |           +-- Tra tên jmxrmi, nhận connector stub
    |
    +--- RMI connector: jmxremote.rmi.port
                |
                +-- TLS -> authentication -> JMX operations
~~~

JDK 21 HotSpot có property **com.sun.management.jmxremote.registry.ssl**. **Mặc định là false**, ngay cả khi connector SSL được bật. Điều này quan trọng vì registry không được bảo vệ đầy đủ có thể tạo điều kiện cho rủi ro trả về **connector stub giả mạo** trong một số trường hợp; tài liệu Oracle đã cảnh báo về khả năng lộ password khi client tin registry không an toàn.

Để bảo vệ registry bằng TLS:

~~~properties
com.sun.management.jmxremote.registry.ssl=true
com.sun.management.jmxremote.ssl.need.client.auth=true
com.sun.management.jmxremote.ssl=true
~~~

Tài liệu khuyến nghị nếu bật **registry.ssl=true** thì để có bảo mật đầy đủ, phải bật xác thực **TLS client certificate**. Client cần hỗ trợ **SSL-protected registry lookup** chứ không chỉ TLS ở connector; nếu không, connection vẫn có thể thất bại dù username/password đúng.

**Đừng coi SSL ở connector là SSL ở mọi mắt xích RMI**. Registry, connector, trust/certificates, authentication và access policy là các thành phần cần đánh giá riêng.

### 7.1. Hai cổng và hostname được quảng bá

Ví dụ loopback cho một lab có JVM và client ở cùng môi trường host:

~~~properties
com.sun.management.jmxremote.port=7091
com.sun.management.jmxremote.rmi.port=7092
com.sun.management.jmxremote.host=127.0.0.1
java.rmi.server.hostname=127.0.0.1
~~~

- **7091** là registry port.
- **7092** là connector port được cấu hình cố định.
- **com.sun.management.jmxremote.host** ảnh hưởng địa chỉ agent bind theo khả năng JDK.
- **java.rmi.server.hostname** quyết định hostname/IP được đưa vào RMI stub để client theo tới connector.

**127.0.0.1 ở trên chỉ dùng cho tình huống loopback phù hợp**. Nếu client ở máy khác, stub trỏ loopback thường khiến client kết nối đến chính máy của nó. Trong container, loopback của JVM không phải loopback của Docker host hoặc laptop. Không mở toàn bộ interface ra Internet để đối phó với sai cấu hình stub; chọn DNS/certificate SAN, network topology và port được kiểm soát đúng cách.

### 7.2. Service URL cho RMI JMX

Client dùng URL thông dụng:

~~~text
service:jmx:rmi:///jndi/rmi://hostName:portNum/jmxrmi
~~~

**portNum** ở URL là cổng registry. Sau lookup, stub có thể quảng bá connector endpoint khác. Nếu client connect tới registry thành công nhưng sau đó **Connection refused** hoặc timeout, hãy kiểm tra hostname/connector port/firewall/TLS — không lập tức reset mật khẩu.

JMX RMI **không phải HTTP**. Một HTTPS Ingress thông thường không tự proxy đúng giao thức RMI hoặc quá trình chuyển từ registry đến connector. Nếu qua VPN/tunnel/bastion, cần cả port và địa chỉ stub phù hợp.

## 8. Sơ đồ khung cấu hình an toàn để rà soát

Đoạn dưới là **các property cần có trong một thiết kế bảo mật**, không phải file production-ready để chạy nguyên xi. Nó **cố ý thiếu credentials, certificates và password values**; đội vận hành phải provision các thành phần đó qua secret manager/PKI và cấu hình đúng cách JVM sẽ nạp chúng.

~~~properties
# RMI trên loopback trong lab
com.sun.management.jmxremote.port=7091
com.sun.management.jmxremote.rmi.port=7092
com.sun.management.jmxremote.host=127.0.0.1
java.rmi.server.hostname=127.0.0.1

# Identity + quyền
com.sun.management.jmxremote.authenticate=true
com.sun.management.jmxremote.password.file=/run/secrets/jmxremote.password
com.sun.management.jmxremote.access.file=/etc/jmx/jmxremote.access

# TLS cho connector và registry, xác thực client cert
com.sun.management.jmxremote.ssl=true
com.sun.management.jmxremote.registry.ssl=true
com.sun.management.jmxremote.ssl.need.client.auth=true
~~~

Các **com.sun.management.jmxremote** properties có thể được dùng với **-Dkey=value** lúc JVM startup hoặc cấu hình management file theo tài liệu JDK. Các JSSE properties như **javax.net.ssl.keyStore** và **trustStore** cũng cần đặt bằng cơ chế JVM/triển khai phù hợp; không mặc định file properties tự chọn ở một đường dẫn bất kỳ sẽ được JVM nạp.

Tài khoản **monitorRole** và **controlRole** trong file **jmxremote.access** phải có cơ chế xác thực tương ứng. File password cần permission hợp lệ; cert keystore/truststore phải có chuỗi tin cậy và key password đúng. Nếu sai, JVM có thể không startup được khi bật management agent.

### 8.1. Vì sao không đưa mật khẩu vào dòng lệnh ví dụ?

Ví dụ **không khuyến nghị**:

~~~text
-Djavax.net.ssl.keyStorePassword=secret-displayed-in-process-list
~~~

Đó là mô tả điều **cần tránh**, không phải một mật khẩu hay lệnh chạy. Arguments có thể bị thu thập bởi process listing, runtime metadata, deployment manifests, crash diagnostics và CI logs. Dùng cơ chế quản lý secret được phê duyệt, quyền file chặt, rotate và không ghi thông tin bí mật trong bài học/code.

## 9. Java 21 runnable: MBean an toàn để thử read và write

Để thử authorization mà không tác động JVM production, tạo **MBean thử nghiệm** trong tiến trình Java riêng. Nó công bố attribute **Limit** đọc/ghi và operation **Reset**. Bản thân Java class không kiểm tra remote role; vai trò được thực thi bởi access controller của **remote JMX connector**.

**Tệp JmxRoleLab.java:**

~~~java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import javax.management.StandardMBean;

public final class JmxRoleLab {
    public interface DemoControlMBean {
        int getLimit();
        void setLimit(int newLimit);
        void reset();
    }

    public static final class DemoControl
            implements DemoControlMBean {
        private int limit = 10;

        @Override
        public synchronized int getLimit() {
            return limit;
        }

        @Override
        public synchronized void setLimit(int newLimit) {
            if (newLimit < 1 || newLimit > 100) {
                throw new IllegalArgumentException(
                        "Limit must be 1..100");
            }
            limit = newLimit;
        }

        @Override
        public synchronized void reset() {
            limit = 10;
        }
    }

    public static void main(String[] args)
            throws Exception {
        MBeanServer server =
                ManagementFactory.getPlatformMBeanServer();
        ObjectName name = new ObjectName(
                "training.jmx:type=DemoControl");

        server.registerMBean(
                new StandardMBean(
                        new DemoControl(),
                        DemoControlMBean.class),
                name);

        System.out.println("MBean=" + name);
        System.out.println("InitialLimit="
                + server.getAttribute(name, "Limit"));
        System.out.println("Window=120 seconds");

        Thread.sleep(120_000L);
        System.out.println("FinalLimit="
                + server.getAttribute(name, "Limit"));
    }
}
~~~

Biên dịch và chạy với JDK 21:

~~~bash
javac --release 21 JmxRoleLab.java
java JmxRoleLab
~~~

**Ba dòng stdout đầu luôn như sau nếu chương trình khởi tạo thành công:**

~~~text
MBean=training.jmx:type=DemoControl
InitialLimit=10
Window=120 seconds
~~~

Sau khoảng 120 giây, chương trình in **FinalLimit=...**. Nếu chưa có client điều khiển, giá trị là **10**. Nếu client readwrite đổi **Limit**, giá trị cuối có thể khác.

**Lệnh java JmxRoleLab thuần túy chỉ đăng ký MBean trong platform MBeanServer; nó không tự mở remote JMX.** Muốn thử remote role, phải khởi động JVM lab bằng các -D properties của remote agent đã được provision TLS/cert/secret đúng, hoặc dùng một connector thử nghiệm an toàn có kiểm soát.

### 9.1. Bài kiểm thử quyền đúng nghĩa

Dùng **remote JMX client đã cấu hình TLS/mTLS** kết nối vào đúng JVM lab, không dùng JConsole local tab:

- **monitorRole readonly**: đọc attribute **Limit** được, nhưng gọi **setAttribute** để đổi Limit hoặc **invoke Reset** phải bị từ chối.
- **controlRole readwrite**: được đọc, ghi Limit, gọi Reset nếu policy đang dùng cho phép và MBean đã công bố đúng attribute/operation.
- **Sai password**: connection phải thất bại ở authentication.
- **Client cert không được tin** khi bật mTLS: phải bị từ chối ở TLS handshake.
- **Client từ mạng không cho phép**: phải không tới được registry/connector port.

**Không thử thao tác ghi lên một platform MBean của production** như thay logging, reset hệ thống hay buộc GC chỉ để chứng minh role. MBean lab có side effect nhỏ và được thiết kế cho việc này.

**Giới hạn quan trọng:** gọi **MBeanServer.setAttribute** trực tiếp trong cùng JVM không đi qua remote password/access file; nếu local code sửa được Limit thì không chứng minh remote role đang sai. Muốn thử role, phải thực hiện từ **remote connector** mà policy thực sự bảo vệ.

## 10. Java 21 runnable: client đọc MBean qua remote JMX

Ví dụ bên dưới chỉ **đọc attribute Limit**, không gọi operation thay đổi trạng thái. Password được nhập từ **console**, không truyền như CLI argument. Chương trình **biên dịch trên JDK 21**, nhưng kết nối thành công phụ thuộc remote agent, TLS certificates, RMI registry socket factory và credentials được triển khai đúng.

**Tệp JmxReadProbe.java:**

~~~java
import java.io.Console;
import java.util.Arrays;
import java.util.HashMap;
import java.util.Map;

import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

public final class JmxReadProbe {
    public static void main(String[] args)
            throws Exception {
        if (args.length != 3) {
            System.out.println(
                    "Usage: java JmxReadProbe host port role");
            return;
        }

        Console console = System.console();
        if (console == null) {
            throw new IllegalStateException(
                    "A console is required to enter the password");
        }

        char[] secret = console.readPassword(
                "JMX password for %s: ", args[2]);
        if (secret == null) {
            throw new IllegalStateException(
                    "Password input cancelled");
        }

        String[] credentials =
                {args[2], new String(secret)};
        Arrays.fill(secret, '\0');

        int port = Integer.parseInt(args[1]);
        JMXServiceURL url = new JMXServiceURL(
                "service:jmx:rmi:///jndi/rmi://"
                        + args[0] + ":" + port + "/jmxrmi");

        Map<String, Object> env = new HashMap<>();
        env.put(JMXConnector.CREDENTIALS, credentials);

        try (JMXConnector connector =
                JMXConnectorFactory.connect(url, env)) {
            MBeanServerConnection server =
                    connector.getMBeanServerConnection();
            ObjectName bean = new ObjectName(
                    "training.jmx:type=DemoControl");
            Object current = server.getAttribute(
                    bean, "Limit");
            System.out.println("Limit=" + current);
        } finally {
            Arrays.fill(credentials, null);
        }
    }
}
~~~

Biên dịch và chạy **nếu agent và client đã được cấu hình tương thích**:

~~~bash
javac --release 21 JmxReadProbe.java
java JmxReadProbe localhost 7091 monitorRole
~~~

Khi lab MBean vẫn hoạt động, password/role đúng, TLS và RMI lookup thành công, Limit chưa thay đổi, client in:

~~~text
JMX password for monitorRole:
Limit=10
~~~

Dòng đầu là **password prompt**; ký tự người nhập không được echo. Nếu MBean đã được operator sửa thì giá trị Limit khác. Nếu TLS handshake/registry lookup/authorization fail, Java sẽ báo exception thay vì có stdout thành công cố định.

**Giới hạn minh bạch của client mẫu:** khi server bật **com.sun.management.jmxremote.registry.ssl=true**, một client RMI/JNDI có thể cần thêm **SSL socket factory** cho thao tác lookup registry. Code trên **không tự cấu hình SSL-protected registry hay mTLS keystore/truststore**. Người vận hành phải dùng công cụ JMX/JConsole và cấu hình client hỗ trợ TLS registry, certificate/trust đúng; không bỏ registry.ssl chỉ để làm ví dụ này kết nối được. Cần kiểm tra compatibility của library/client theo JDK thực tế.

**Giới hạn bảo vệ password:** code xóa bản char[] ban đầu, nhưng API **JMXConnector.CREDENTIALS** dùng **String[]**, và String chứa password không thể xóa bytes ngay như char[]. Vì vậy ứng dụng quản trị production vẫn cần xử lý secret lifecycle và bảo vệ process memory; không log credentials.

## 11. Kiểm tra TLS certificate và identity

Keystore/truststore không chỉ là hai đường dẫn có đuôi **.p12**. Cần kiểm tra:

- **Server certificate** được client tin cậy và certificate **SAN** phù hợp với DNS/IP dùng để kết nối.
- **Client certificate** được server tin khi yêu cầu mTLS; scope và policy của CA/client identity được quản lý.
- Certificate chưa hết hạn, chưa bị thu hồi theo chính sách và dùng thuật toán hợp lệ với JDK 21.
- Protocol/cipher suites được hai đầu hỗ trợ; không “fix” bằng cách tắt validation.
- Private keys không nằm trong Docker image, git, screenshot hay log.
- Mật khẩu của keystore/truststore được cấp qua secret workflow, không hardcode lên startup command cho tất cả người dùng đọc.

Với JDK **keytool**, người vận hành có thể kiểm tra certificate/alias trong một keystore khi có quyền và công cụ:

~~~bash
keytool -list -v -keystore /run/secrets/jmx-server.p12
~~~

Lệnh có thể yêu cầu mật khẩu; kết quả sẽ hiển thị certificate metadata. **Không chia sẻ output chứa thông tin nhạy cảm hoặc nội dung private key**, không tự chạy trên môi trường không có quyền.

**Hostname verification:** nếu dùng **localhost** cho tunnel nhưng server certificate cấp cho **jmx.internal.example**, cần thiết kế endpoint/address và cách xác minh danh tính phù hợp. Đừng tắt hostname checking để tránh xử lý bất đồng giữa advertised RMI host và certificate SAN.

## 12. Docker và Kubernetes: port, PID, secret và network policy

### 12.1. Docker

Trong Docker Linux, JVM có thể mang **PID container** khác **PID trên host**. Dù jcmd cần PID đúng cho local attach, remote JMX thường dùng **host/port/JMX service URL**. Hai mô hình có namespace/permission riêng; không suy ra JMX role tự hạn chế các lệnh chạy trong container.

Cần thiết kế:

1. **RMI registry + connector ports** được publish có chủ đích, không mở tất cả.
2. **Listener bind** của JVM và **java.rmi.server.hostname** phải tương thích đường route thực tế từ client.
3. Docker **bind mount/volume** phải đưa keystore/truststore/access/password files vào đúng đường dẫn JVM.
4. Secret file owner/mode phù hợp **effective UID/GID** của Java, không chỉ quyền shell root.
5. Network/tunnel giới hạn nguồn, chứng chỉ khớp hostname và logging không để lộ secret.

**Docker Desktop** đặt Linux containers trong Linux VM; RMI stub không thể tùy tiện quảng bá một host chỉ có nghĩa trong VM và mong máy ngoài truy cập được. Đừng giải quyết bằng cách bỏ TLS hoặc vô hiệu hóa authentication.

### 12.2. Kubernetes

Trong Kubernetes, remote JMX không nên bị expose như một internet-facing **LoadBalancer/Ingress** phổ thông. Một mô hình kiểm soát hợp lý:

- Restrict với **NetworkPolicy** chỉ từ monitoring/bastion theo nhu cầu.
- Dùng **Secret** và volume mount để cấp cert/keystore/password với quyền thích hợp; kiểm tra Pod Security, service account và RBAC đọc secrets.
- Định nghĩa cả registry và connector port; chú ý **Pod IP, Service DNS, RMI hostname trong stub** và certificate SAN.
- **kubectl port-forward** có thể là một đường truy cập được quản trị nhưng không tự cung cấp TLS/auth hoặc hỗ trợ tất cả RMI stub/second port.
- Với nhiệm vụ chỉ quan sát CPU/heap, cân nhắc **metrics exporter chỉ đọc**, thay vì đưa raw JMX control endpoint cho mọi dashboard.
- Giới hạn người có quyền **kubectl exec** hoặc vào node vì họ có thể có đường local attach hoặc đọc file secret.

**Kubernetes RBAC** kiểm soát Kubernetes API, không tự phân biệt getAttribute/setAttribute của remote JMX. **jmxremote.access** kiểm soát remote JMX roles, không tự ràng buộc những người có khả năng exec cùng OS user trong Pod. Hai hệ quyền không thay nhau.

### 12.3. Nếu chỉ có port-forward một cổng mà vẫn lỗi

RMI có thể làm client lookup registry thành công rồi cố nối tiếp đến hostname và connector port đã được stub trả về. Nếu chỉ forward **7091** mà connector là **7092** hoặc stub quảng bá Pod IP không route được từ laptop, connection sẽ fail. Kiểm tra **cả hai cổng**, stub hostname, DNS, firewall và chứng chỉ; không mặc định lỗi thuộc password.

## 13. Phân biệt các loại lỗi khi remote JMX không hoạt động

| Dấu hiệu | Khả năng nguyên nhân | Kiểm tra đúng |
| --- | --- | --- |
| **Connection refused** đến registry | Agent chưa listen, sai bind, sai port, firewall. | JVM startup config, listening sockets, network. |
| Registry reachable nhưng connector timeout | RMI stub hostname/connector port sai, NAT/network policy. | java.rmi.server.hostname, jmxremote.rmi.port, route. |
| **SSLHandshakeException** | CA không tin, cert sai SAN/expired, cipher/protocol, thiếu client cert. | Server/client truststores, TLS properties, PKI. |
| **Authentication failed** | Mật khẩu, identity, JAAS, password file, role entry. | File permission, principal mapping, login logs (không log secret). |
| Đọc được nhưng **setAttribute** bị từ chối | readonly role hoặc attribute không writable. | MBeanInfo và thử remote trên lab MBean. |
| **invoke** bị từ chối với monitorRole | Authorization chặn đúng hành vi có side effect. | Kiểm tra client đi qua remote connector. |
| JConsole local chạy còn remote fail | Local Attach bypass remote file checks; remote TLS/auth khác. | Kiểm tra đúng kết nối, port và identity. |
| TLS connector có nhưng registry SSL chưa bật | Registry là mắt xích riêng, mặc định không TLS. | registry.ssl, client cert và policy. |
| Khai báo role nhưng vẫn có quyền rộng | authenticate=false, custom connector bỏ forwarder, local path. | Endpoint thực, effective properties, chính sách. |
| Java process không startup khi bật agent | Password/access file sai quyền/nội dung, bind failure, cert issue. | Startup stderr/config, owner/mode, port conflicts. |
| JMX hoạt động trước deploy, sau restart mất | JVM mới, secret/mount/port/hostname khác. | Full Java version, Pod UID, config và certificate rotation. |

**Đừng “sửa” lỗi kết nối bằng cách tự động tắt authentication/TLS.** Ghi nhận giai đoạn đầu tiên thất bại, kiểm tra từng lớp theo thứ tự: route → TLS → identity → role → operation.

## 14. Kênh quản lý phải có vòng đời secret và session

Một cấu hình hoạt động hôm nay có thể không còn bảo mật sau khi operator đổi nhóm, chứng chỉ hết hạn hoặc workload deploy sang môi trường khác. Cần có:

- **Tách tài khoản monitoring và control**, rotate password/certificate định kỳ, revoke khi không cần.
- **Quản trị file permissions** và không để secret trong image, git, process arguments, crash files, CI logs.
- **Theo dõi certificate expiry/trust chain** và phiên bản JDK/cipher suites trước khi thay.
- **Xác minh cơ chế reload** của agent; không mặc định sửa file secret trên disk làm mọi phiên/JVM cập nhật ngay.
- **Kiểm soát established sessions:** một session đã xác thực có thể còn hoạt động sau khi policy/secret thay đổi; cần kiểm chứng cách ngắt, timeout hoặc restart connector.
- **Audit actions** của operator, đặc biệt những operation thay đổi cấu hình hay gây pause.
- **Kế hoạch đóng endpoint** khi một kênh debug tạm thời hết nhu cầu, thay vì để cổng readwrite tồn tại mãi.

Một dashboard readonly có thể vẫn xem thông tin nhạy cảm. Cần **data minimization** trong MBeans; không công bố private key, password hoặc nhạy cảm dưới dạng getter chỉ vì “monitor chỉ đọc”.

## 15. Runbook kiểm tra phân quyền từ ngoài vào trong

**Bước 1 — Nhận diện target.** Xác định JDK full version, VM vendor, host/node, Pod/container UID, process start time và connector URL. Tránh nhầm local connector với remote connector.

**Bước 2 — Chụp cấu hình.** Đọc effective startup flags/management properties, kiểm tra remote port, rmi port, host binding, auth=true, TLS, registry.ssl, access roles; **không in nội dung password/cert private key**.

**Bước 3 — Kiểm tra mạng.** Chứng minh client không được phép **không route** được tới cả registry và connector. DNS/stub hostname phải tới được từ đúng vị trí client.

**Bước 4 — Kiểm tra TLS.** Với CA không tin hoặc client cert không hợp lệ, kết nối phải thất bại. Xác minh hostname SAN, certificate chain, expiry, mutual TLS/registry SSL nếu có.

**Bước 5 — Kiểm tra authentication.** Sai password/unknown principal không được mở session. Đừng lưu password trong test logs.

**Bước 6 — Kiểm tra readonly.** Trên **training.jmx:type=DemoControl** của lab, monitorRole đọc **Limit** được; **set Limit** và **invoke Reset** phải bị từ chối.

**Bước 7 — Kiểm tra readwrite.** controlRole trên lab được sửa **Limit** và gọi Reset theo policy được thiết kế; điều này chỉ nên làm ở môi trường thử nghiệm.

**Bước 8 — Phân biệt local.** OS user khác bị giới hạn attach như thiết kế; không dùng thử nghiệm local để suy ra remote RBAC.

**Bước 9 — Cleanup.** Đóng session, tắt cổng debug nếu tạm thời, rotate/revoke credential thử nghiệm, lưu biên bản mà không ghi secret.

| Test | Kết quả mong đợi |
| --- | --- |
| Client từ mạng không được phép | Không đến được endpoint. |
| Server certificate không được client tin | TLS handshake/identity verification thất bại. |
| Thiếu client certificate khi mTLS bắt buộc | TLS authentication thất bại. |
| Sai user/password | JMX authentication thất bại. |
| monitorRole đọc Limit | Thành công khi kết nối hợp lệ. |
| monitorRole set Limit | Bị từ chối do readonly. |
| monitorRole invoke Reset | Bị từ chối do readonly. |
| controlRole set Limit trên lab | Được phép nếu MBean và policy cho phép. |
| Local attach bằng user không được phép | Bị kiểm soát theo OS/Attach policy. |

## 16. Những lỗi cần tránh

1. **“Có TLS rồi thì không cần authorization.”** TLS không phân quyền get/set/invoke.
2. **“Có password là traffic đã được mã hóa.”** Authentication và encryption khác nhau.
3. **“authenticate=false chỉ bỏ login, vẫn readonly từ access file.”** Với ready-to-use agent, file role bị bỏ qua.
4. **“readwrite chỉ được sửa một MBean business.”** Coarse-grained role có phạm vi rộng hơn.
5. **“readonly không có dữ liệu nhạy cảm.”** MBean getter có thể lộ cấu hình và metadata.
6. **“Local JConsole là test cho remote access file.”** Local Attach là một đường khác.
7. **“ssl=true nghĩa là registry.ssl=true.”** Registry là endpoint riêng, mặc định chưa TLS-protected.
8. **“Chỉ cần mở cổng jmxremote.port.”** Connector port và hostname trong stub còn phải route.
9. **“127.0.0.1 luôn phù hợp remote JMX.”** Loopback phụ thuộc client/host/container.
10. **“Đặt password trong -D argument để tiện vận hành.”** Secret có thể lộ qua nhiều hệ thống.
11. **“Docker private network là đủ.”** Workload khác/credentials bị lộ vẫn là nguy cơ.
12. **“Kubernetes Secret tạo ra JMX RBAC.”** Secret chỉ cấp file/giá trị, không cấp policy MBean.
13. **“Port-forward đồng nghĩa có TLS.”** Tunnel/reachability không thay mTLS/auth/JMX access.
14. **“Phải có Security Manager cũ mới bảo vệ JMX.”** Không dùng Security Manager đã deprecated làm lớp bảo vệ duy nhất; dùng cơ chế connector/authorization đang hỗ trợ.
15. **“Sửa access file xong sẽ ngắt mọi session cũ.”** Cần kiểm chứng lifecycle và revoke đúng cơ chế.
16. **“Read-only user có thể gọi operation không thay đổi trạng thái.”** Access policy readonly có thể từ chối invoke, dù operation trông vô hại.
17. **“Mọi client cần quyền readwrite để xem thread dump.”** Xác định phương pháp đọc, quyền chính xác; không cấp rộng theo thói quen.
18. **“Password TLS handshakes fail thì cứ tắt SSL.”** Kiểm tra truststore, SAN, cipher, registry socket factory, route.
19. **“Kết nối được registry là chắc chắn tới JVM.”** RMI stub có thể trỏ connector host/port khác.
20. **“JMX TLS cũng tự bảo vệ jcmd trong container.”** Local attach/OS permissions là ranh giới khác.

## 17. Tự kiểm tra

**Câu 1.** Server có TLS hợp lệ; monitoring client đăng nhập bằng **monitorRole readonly**. Có được gọi **Reset** của lab không?

**Đáp án:** Không qua remote connector chịu policy readonly. TLS chỉ bảo vệ đường truyền/peer, không tự cấp quyền operation.

**Câu 2.** File access có monitorRole readonly, nhưng JVM chạy **authenticate=false**. Policy còn hiệu lực không?

**Đáp án:** Không thể dựa vào đó. Ready-to-use agent bỏ qua password/access files khi authentication bị tắt.

**Câu 3.** Connector SSL bật, registry SSL để mặc định. Rủi ro gì?

**Đáp án:** RMI registry vẫn là endpoint không TLS theo mặc định JDK 21; cần bảo vệ bằng **registry.ssl** và thiết kế client cert/auth theo tài liệu.

**Câu 4.** Vì sao remote monitor bị chặn ghi nhưng JConsole local cùng user ghi được?

**Đáp án:** Local connector sử dụng OS/Attach permission, không áp dụng password/access file của remote agent.

**Câu 5.** Registry port 7091 reachable nhưng connector 7092 timeout. Có chắc password sai?

**Đáp án:** Không. Kiểm tra stub hostname, connector port, firewall, DNS, TLS handshake và certificate.

**Câu 6.** Port JMX chỉ được expose trong Kubernetes cluster. Đủ bảo mật chưa?

**Đáp án:** Chưa. Cần network restrictions, TLS, authentication, JMX authorization, secret management và Kubernetes RBAC.

**Câu 7.** Vì sao metrics collector không nên dùng controlRole readwrite?

**Đáp án:** Nó thường chỉ cần read attributes; readwrite có thể thực thi management operations không liên quan, tạo rủi ro quá quyền.

**Câu 8.** Chứng chỉ client đã bị revoke nhưng established JMX session còn mở. Có thể không?

**Đáp án:** Có. Cần xác minh hành vi connector, TLS sessions và cơ chế đóng kết nối/restart/rotation thay vì giả định revoke ảnh hưởng tức thời.

**Câu 9.** Kế hoạch test readwrite dùng platform MemoryMXBean gọi GC trên production. Có nên?

**Đáp án:** Không; đó là side effect có tác động. Dùng MBean thử nghiệm với thay đổi nhỏ và rollback rõ ràng.

**Câu 10.** MBean readonly công bố system properties có chứa secret. Có an toàn không?

**Đáp án:** Không. Readonly có thể làm lộ thông tin; phải hạn chế dữ liệu trong MBean, redact và hạn chế người đọc.

## 18. Checklist áp dụng cho JDK 21 production

- [ ] Xác định chính xác JDK vendor/VM và loại JMX connector.
- [ ] Phân biệt local Attach và remote JMX; khóa quyền OS/Pod truy cập local.
- [ ] Registry/connector chỉ reachable từ approved network, không public.
- [ ] **jmxremote.port** và **jmxremote.rmi.port** được cấu hình đúng, stub hostname route được.
- [ ] **authenticate=true** và identity store/JAAS được bảo vệ.
- [ ] Monitoring dùng **readonly**, operator readwrite chỉ theo approval.
- [ ] Rà soát **create/unregister** và các operation nhạy cảm.
- [ ] TLS được bật; client xác minh certificate chain, hostname, expiry, protocol.
- [ ] Nếu dùng mTLS, server kiểm tra client cert; nếu registry.ssl=true, client hỗ trợ TLS registry lookup.
- [ ] Secret/password/access/keystore/truststore có owner/mode và vòng đời đúng.
- [ ] Đã thử positive/negative cases: sai password/cert, readonly get và set/invoke.
- [ ] Đã kiểm tra Docker/Kubernetes networking, Secret mount, RBAC, port-forward.
- [ ] Có audit, credential rotation, session revocation và kế hoạch đóng cổng.
- [ ] Không mở raw remote JMX chỉ để đọc metrics nếu có exporter/gateway readonly phù hợp.

## Tài liệu tham khảo

- [JDK 21 — Monitoring and Management Using JMX Technology](https://docs.oracle.com/en/java/javase/21/management/monitoring-and-management-using-jmx-technology.html): ready-to-use JMX agent, file auth, TLS/registry SSL, remote properties.
- [Java SE 21 JMX Guide — Security](https://docs.oracle.com/en/java/javase/21/jmx/security.html): JMXAuthenticator, MBeanServerForwarder, simple và fine-grained security.
- [Java SE 21 — JMXConnectorFactory](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/remote/JMXConnectorFactory.html): tạo client connector.
- [Java SE 21 — JMXConnector](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/remote/JMXConnector.html): credentials và lifecycle.
- [Java SE 21 — JMXServiceURL](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/remote/JMXServiceURL.html): JMX service URL.
- [Java SE 21 — StandardMBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/StandardMBean.html): MBean thử nghiệm.
- [Java SE 21 — MBeanServerConnection](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html): getAttribute, setAttribute, invoke.
- [Java SE 21 — JSSE Reference Guide](https://docs.oracle.com/en/java/javase/21/security/java-secure-socket-extension-jsse-reference-guide.html): TLS/keystore/truststore.
- [Java SE 21 — keytool](https://docs.oracle.com/en/java/javase/21/docs/specs/man/keytool.html): chứng chỉ và kho khóa.
- [OpenJDK JEP 411 — Security Manager deprecation](https://openjdk.org/jeps/411): giới hạn của mô hình Security Manager cũ.

**Nguyên tắc cốt lõi:** với JMX, **chỉ đọc không có nghĩa công khai**, **TLS không có nghĩa được phép điều khiển**, và **có authentication không bảo đảm file role được thực thi qua mọi connector**. Hãy xác minh cùng lúc **mạng, TLS, danh tính, quyền, local attach và vòng đời secret/session** trên đúng JVM.
