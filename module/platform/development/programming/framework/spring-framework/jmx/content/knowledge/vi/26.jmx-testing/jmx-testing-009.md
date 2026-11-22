# Kiểm thử connector remote trong môi trường cô lập — Spring Framework JMX

## Mục tiêu học tập

Bài này thuộc nhóm **Kiểm thử** của **Spring Framework JMX**, tập trung vào việc kiểm thử một kết nối JMX từ xa giữa JVM client và JVM server mà không phụ thuộc hạ tầng production, không mở cổng quản trị ra mạng công cộng và không ảnh hưởng registry của các test khác.

Sau khi hoàn thành, bạn có thể:

- Phân biệt \`MBeanServer\`, \`JMXConnectorServer\`, \`JMXConnector\`, \`MBeanServerConnection\` và \`JMXServiceURL\`.
- Xây dựng môi trường kiểm thử chỉ cho phép kết nối loopback, dùng port động, có teardown đầy đủ.
- Chạy server và client ở cùng JVM để kiểm tra giao thức JMX remote hoặc ở hai JVM để tăng mức cách ly.
- Kiểm thử đường đi end-to-end: đăng ký MBean → khởi động connector → kết nối client → đọc attribute → invoke operation → ngắt kết nối.
- Hiểu khác biệt giữa kiểm thử connector transport và kiểm thử cấu hình remote JMX management agent của JVM.
- Kiểm soát xác thực, SSL/TLS, timeout và secret cho môi trường phù hợp.
- Chẩn đoán các lỗi RMI registry, advertised host, port, registration, lifecycle và callback.
- Tạo test tái lập được trên CI mà không dựa vào IP cứng hoặc server đang chạy sẵn.

## 1. Remote JMX connector là gì?

JMX cung cấp một mô hình client/server:

\`\`\`text
JVM client                              JVM server
-----------                             -------------------
JMXConnectorFactory.connect             JMXConnectorServer
        |                                       |
        v                                       v
JMXConnector                             MBeanServer
        |                                       |
        v                                       +-- ObjectName -> MBean
MBeanServerConnection                           |
        |                                       |
        +------ getAttribute/invoke ------------+
\`\`\`

Trong Spring Framework JMX, \`MBeanExporter\` thường đưa Spring beans vào một \`MBeanServer\`. Tuy nhiên **MBeanExporter không tự động mở remote endpoint**. Để một JVM bên ngoài truy cập registry, cần một connector thích hợp, ví dụ connector RMI theo JSR 160.

Các thành phần có trách nhiệm riêng:

| Thành phần | Trách nhiệm |
| --- | --- |
| \`MBeanServer\` | Chứa các MBean đã đăng ký và thực thi JMX operations |
| \`MBeanExporter\` | Export Spring beans vào server, quản lý registration theo lifecycle |
| \`JMXConnectorServer\` | Cung cấp endpoint remote JMX cho client |
| \`JMXServiceURL\` | Mô tả địa chỉ/protocol mà client sử dụng |
| \`JMXConnector\` | Quản lý kết nối ở phía client |
| \`MBeanServerConnection\` | API client gọi \`getAttribute\`, \`invoke\`, \`queryNames\`… |
| \`RMI Registry\` | Trong một cấu hình JMX/RMI phổ biến, lưu tên \`jmxrmi\` để client tra cứu stub |

Một local API test gọi \`server.getAttribute(...)\` **không kiểm tra remote connector**. Muốn xác nhận transport, cần tạo \`JMXConnector\` từ \`JMXServiceURL\`, nhận \`MBeanServerConnection\` rồi thực hiện lời gọi qua connection đó.

## 2. Vì sao phải cô lập môi trường kiểm thử?

Remote JMX có khả năng đọc thông tin JVM và gọi các operation quản trị, nhiều operation có thể thay đổi trạng thái ứng dụng. Một test bất cẩn có thể:

- Bind connector trên mọi network interface thay vì chỉ loopback.
- Dùng port cố định đang được service khác chiếm.
- Kết nối nhầm endpoint thật do URL lấy từ environment.
- Tác động lên platform \`MBeanServer\` của JVM test và làm nhiễm trạng thái suite.
- Để lại RMI registry hoặc socket đang mở sau test.
- Cấu hình không xác thực trong một môi trường mà máy khác truy cập được.
- Chạy các JMX operations có side effect lên shared service.

**Nguyên tắc cô lập:** test tự tạo server, tự tạo endpoint chỉ dùng trong fixture, chỉ đăng ký MBean thử nghiệm, chỉ kết nối tới địa chỉ do fixture sinh ra, rồi đóng toàn bộ tài nguyên trong \`finally\` hoặc teardown hook.

Ưu tiên loopback \`127.0.0.1\` và port động, không sử dụng địa chỉ production hoặc DNS của một hệ thống khác. Khi cần test multi-host/TLS thực tế, dùng môi trường kiểm thử có network policy tách biệt và credentials riêng.

## 3. Các mức kiểm thử nên phân biệt

| Mức | Client/server | Kiểm chứng | Giới hạn |
| --- | --- | --- | --- |
| Unit test MBean | Cùng object Java | Business behavior và metadata tự dựng | Không kiểm tra JMX registry/transport |
| Integration test local JMX | \`MBeanServer\` trong cùng JVM | Registration, attributes, operations | Không kiểm tra connector |
| Remote connector integration test | \`JMXConnector\` + \`MBeanServerConnection\` | Protocol, serialization, lookup, remote invocation | Nếu cùng JVM chưa bao phủ process isolation |
| Two-JVM integration test | Client và server khác JVM | Network stack, lifecycle/process boundary, JVM properties | Cần orchestration/teardown chặt chẽ |
| Security/production-like test | TLS, authentication, firewall/container networking | Security configuration và route thực tế | Nặng, phụ thuộc environment |

Bài học bắt đầu bằng test remote connector RMI trên loopback. Sau đó mở rộng sang test client/server ở hai process. Cách này tạo sự cân bằng giữa tốc độ test và độ tin cậy.

## 4. Chuẩn bị Standard MBean đơn giản

Dùng một MBean không phụ thuộc database, network hay hệ thống ngoài.

**RemoteProbeMBean.java**

\`\`\`java
package com.example.jmx;

public interface RemoteProbeMBean {
    String getStatus();
    long getInvocationCount();
    String ping(String message);
}
\`\`\`

**RemoteProbe.java**

\`\`\`java
package com.example.jmx;

import java.util.concurrent.atomic.AtomicLong;

public final class RemoteProbe implements RemoteProbeMBean {
    private final AtomicLong invocations = new AtomicLong();

    @Override
    public String getStatus() {
        return "READY";
    }

    @Override
    public long getInvocationCount() {
        return invocations.get();
    }

    @Override
    public String ping(String message) {
        invocations.incrementAndGet();
        return "PONG:" + message;
    }
}
\`\`\`

Đây là Standard MBean: implementation \`RemoteProbe\` implement interface tên \`RemoteProbeMBean\`, theo convention của JMX. Khi đăng ký, các attributes \`Status\`, \`InvocationCount\` và operation \`ping(java.lang.String)\` có thể được gọi qua \`MBeanServer\`.

Trong test transport, \`ping\` là operation có side effect nhỏ và kiểm soát được: chỉ tăng một counter trong bộ nhớ. Không dùng method xóa dữ liệu, khởi động job ngoài hệ thống hoặc gọi API production.

## 5. Fixture tối thiểu: dùng JMXConnectorServer với URL RMI dạng trực tiếp

RMI connector có nhiều dạng service URL. Một dạng được dùng để khởi tạo connector và lấy địa chỉ kết nối là:

\`\`\`java
new JMXServiceURL("service:jmx:rmi://127.0.0.1:0");
\`\`\`

Tuy nhiên, cách server chọn/bind socket và địa chỉ client được quảng bá còn phụ thuộc RMI provider và \`java.rmi.server.hostname\`. Đối với test yêu cầu bảo đảm không mở interface ngoài loopback, cần cấu hình \`RMIServerSocketFactory\` chỉ bind loopback hoặc dùng một RMI registry do test quản lý với socket factories phù hợp. **Chỉ viết host loopback trong URL không phải là chứng minh đủ rằng tất cả RMI sockets đã bind loopback.**

Fixture Java dưới đây minh họa một connector không sử dụng RMI registry bên ngoài:

\`\`\`java
package com.example.jmx;

import java.net.InetAddress;
import java.net.ServerSocket;
import java.rmi.server.RMIClientSocketFactory;
import java.rmi.server.RMIServerSocketFactory;
import java.util.HashMap;
import java.util.Map;

import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.remote.JMXConnectorServer;
import javax.management.remote.JMXConnectorServerFactory;
import javax.management.remote.JMXServiceURL;
import javax.management.remote.rmi.RMIConnectorServer;

public final class IsolatedJmxServer implements AutoCloseable {

    private final MBeanServer mBeanServer;
    private final JMXConnectorServer connector;
    private final JMXServiceURL address;

    public IsolatedJmxServer() throws Exception {
        this.mBeanServer =
                MBeanServerFactory.createMBeanServer("test.remote");

        RMIServerSocketFactory serverFactory = (port) ->
                new ServerSocket(
                        port, 0,
                        InetAddress.getByName("127.0.0.1"));

        RMIClientSocketFactory clientFactory = null;

        Map<String, Object> env = new HashMap<>();
        env.put(RMIConnectorServer.RMI_SERVER_SOCKET_FACTORY_ATTRIBUTE,
                serverFactory);
        if (clientFactory != null) {
            env.put(RMIConnectorServer.RMI_CLIENT_SOCKET_FACTORY_ATTRIBUTE,
                    clientFactory);
        }

        JMXServiceURL requested =
                new JMXServiceURL("service:jmx:rmi://127.0.0.1:0");

        connector = JMXConnectorServerFactory.newJMXConnectorServer(
                requested, env, mBeanServer);
        connector.start();
        address = connector.getAddress();
    }

    public MBeanServer server() {
        return mBeanServer;
    }

    public JMXServiceURL address() {
        return address;
    }

    @Override
    public void close() throws Exception {
        try {
            connector.stop();
        } finally {
            MBeanServerFactory.releaseMBeanServer(mBeanServer);
        }
    }
}
\`\`\`

Đây là skeleton minh họa cách tạo server và connector tách biệt. Khi triển khai, cần lưu ý **socket factories qua RMI có thể cần serializable implementation** để hoạt động đúng khi stub được truyền cho client, và cách JDK/provider xử lý \`RMI_SERVER_SOCKET_FACTORY_ATTRIBUTE\` cần được xác minh trong môi trường test. Lambda capture và custom socket factory không nên được coi là portable setup cho mọi JDK. Một factory dạng class \`Serializable\` và cấu hình hostname rõ thường phù hợp hơn cho test hai JVM.

Đối với một test CI thật, cách dễ kiểm soát là một cấu hình chuẩn đã được xác minh trên JDK mục tiêu, với registry/connector ports cố định trong phạm vi fixture nhưng được cấp động bởi orchestration, không lấy bằng “find free port, đóng socket, rồi bind lại” nếu cần tránh race.

## 6. Một biến thể dễ chạy: RMI registry trên port test

URL JMX/RMI thường thấy:

\`\`\`text
service:jmx:rmi:///jndi/rmi://127.0.0.1:PORT/jmxrmi
\`\`\`

Trong mô hình này:

1. Test tạo RMI registry tại loopback và port đã chọn.
2. Test tạo \`MBeanServer\` riêng.
3. Test tạo \`JMXConnectorServer\` với URL JNDI lookup qua registry.
4. Server đăng ký stub dưới tên \`jmxrmi\`.
5. Client dùng cùng URL để lấy stub và kết nối.

Với RMI, đôi khi có **hai cổng**: registry port và cổng của exported remote object. Nếu chỉ giới hạn registry port, RMI server có thể mở thêm cổng ngẫu nhiên. Trong CI có firewall/container network, điều này gây lỗi “lookup thành công nhưng invoke thất bại”.

Do đó test cần thiết kế rõ network boundary, bind host và port của exported object, hoặc dùng connector URL trực tiếp từ server để loại bỏ registry trong test transport tối thiểu.

Trong môi trường Docker hoặc Kubernetes, địa chỉ mà RMI stub quảng bá phải truy cập được từ client. \`127.0.0.1\` trong container server **không phải** loopback của container client. Với test hai container khác nhau, phải dùng network được cô lập và hostname phù hợp trong mạng test.

## 7. Đăng ký MBean và thực thi remote client test

Với \`IsolatedJmxServer\`, test có thể đăng ký MBean trực tiếp trên server riêng, sau đó kết nối qua connector:

\`\`\`java
package com.example.jmx;

import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.MBeanServerConnection;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class RemoteConnectorIntegrationTest {

    @Test
    void remoteClientReadsAttributeAndInvokesOperation()
            throws Exception {

        try (IsolatedJmxServer fixture =
                new IsolatedJmxServer()) {

            ObjectName name = new ObjectName(
                    "test.remote:type=RemoteProbe,name=primary");

            fixture.server().registerMBean(
                    new RemoteProbe(), name);

            try (JMXConnector client =
                    JMXConnectorFactory.connect(
                            fixture.address())) {

                MBeanServerConnection connection =
                        client.getMBeanServerConnection();

                assertTrue(connection.isRegistered(name));
                assertEquals("READY",
                        connection.getAttribute(name, "Status"));

                Object result = connection.invoke(
                        name,
                        "ping",
                        new Object[]{"hello"},
                        new String[]{"java.lang.String"});

                assertEquals("PONG:hello", result);
                assertEquals(1L,
                        connection.getAttribute(
                                name, "InvocationCount"));
            }
        }
    }
}
\`\`\`

**Điểm kiểm tra quan trọng:** tất cả thao tác \`isRegistered\`, \`getAttribute\` và \`invoke\` của client được gọi qua \`MBeanServerConnection\`, không gọi trực tiếp \`fixture.server()\` (ngoại trừ khâu setup). Như vậy test thực sự đi qua transport remote JMX.

Để test ổn định, fixture phải trả về service URL kết nối được với cấu hình connector cụ thể. Trong trường hợp trực tiếp dạng \`service:jmx:rmi://...\`, URL trả từ \`getAddress()\` có thể chứa stub encoded; dùng nó thay vì tự suy đoán port/URL sau khi \`start()\`.

## 8. Gắn MBeanExporter của Spring vào test remote connector

Nếu mục tiêu là test toàn đường **Spring bean → MBeanExporter → MBeanServer → JMXConnectorServer → remote client**, thay \`registerMBean\` thủ công bằng \`MBeanExporter\` được Spring quản lý.

**SpringJmxTestConfiguration.java**

\`\`\`java
package com.example.jmx;

import java.util.Map;
import javax.management.MBeanServer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class SpringJmxTestConfiguration {

    @Bean
    public RemoteProbe remoteProbe() {
        return new RemoteProbe();
    }

    @Bean
    public MBeanExporter testExporter(
            RemoteProbe remoteProbe,
            MBeanServer testMBeanServer) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(testMBeanServer);
        exporter.setBeans(Map.of(
                "test.remote:type=RemoteProbe,name=primary",
                remoteProbe));
        return exporter;
    }
}
\`\`\`

Test cần đưa \`testMBeanServer\` do fixture tạo vào context trước khi refresh, ví dụ:

\`\`\`java
try (IsolatedJmxServer fixture = new IsolatedJmxServer()) {
    var context = new AnnotationConfigApplicationContext();
    context.registerBean(
            "testMBeanServer",
            MBeanServer.class,
            fixture::server);
    context.register(SpringJmxTestConfiguration.class);
    context.refresh();

    try {
        // Kết nối client qua fixture.address(), thực hiện assertions.
    } finally {
        context.close();
    }
}
\`\`\`

Với thiết kế này:

- \`MBeanExporter\` chỉ đăng ký vào \`testMBeanServer\` do test cung cấp.
- \`JMXConnectorServer\` cũng gắn với cùng server.
- Không có lý do làm thay đổi platform MBean server của JUnit process.
- Khi context đóng, exporter unregister MBean của nó.
- Khi fixture đóng, connector dừng và server được release.

Các component thứ tự teardown cần phù hợp: **đóng client → đóng Spring context/exporter → stop connector → release MBeanServer**.

## 9. Assertion về lifecycle và cleanup

Một test tốt không chỉ kiểm tra kết nối thành công mà còn xác minh các tài nguyên được dọn:

\`\`\`text
Before:
  server created
  connector started
  MBean registered
  client connected

During:
  remote read/invoke returns expected result

After:
  client.close()
  ApplicationContext.close() -> exporter unregister
  connector.stop()
  MBeanServerFactory.releaseMBeanServer()
\`\`\`

Có thể giữ reference đến server để kiểm tra MBean đã bị unregister sau \`context.close()\` trước khi fixture release server:

\`\`\`java
ObjectName name = new ObjectName(
        "test.remote:type=RemoteProbe,name=primary");

assertTrue(fixture.server().isRegistered(name));

context.close();

assertFalse(fixture.server().isRegistered(name));
\`\`\`

Không dùng \`Thread.sleep\` để “chờ cleanup” nếu API đóng đồng bộ và có thể assert trực tiếp. Trong các trường hợp connector start/stop bất đồng bộ hoặc retry connection, dùng polling có deadline hữu hạn và fail message rõ.

Test không nên cố kết nối lại sau khi connector đã stop chỉ để chứng minh cổng đóng nếu thao tác đó có thể chạm tới service khác vừa sử dụng lại port. Có thể kiểm tra trạng thái connector hoặc setup/teardown APIs theo hợp đồng rồi dùng test tiếp theo để phát hiện leak.

## 10. Dùng hai JVM để tăng mức cách ly

Test cùng JVM kiểm tra JMX remote connector layer nhưng vẫn có những hạn chế:

- Java static state có thể vô tình chia sẻ.
- Classloader và hệ thống property dùng chung.
- Client cùng tiến trình nên không tái hiện toàn bộ firewall/network behavior.
- Một test có thể tìm trực tiếp server nếu viết sai.

Khi cần chắc chắn về process boundary, hãy chạy server ở JVM con:

\`\`\`text
JUnit JVM (parent)
     |
     +-- khởi động ProcessBuilder
     |      |
     |      +-- Child JVM
     |              +-- isolated MBeanServer
     |              +-- JMXConnectorServer
     |              +-- RemoteProbe MBean
     |              +-- in READY + service URL
     |
     +-- JMXConnectorFactory.connect(service URL)
     +-- remote assertions
     +-- yêu cầu child shutdown
     +-- timeout chờ exit
     +-- destroyForcibly nếu cần
\`\`\`

Với \`ProcessBuilder\`, không truyền password hoặc secret qua command-line arguments nếu có cách an toàn hơn, vì process list/logging có thể hiển thị chúng. Test nên capture stdout/stderr để chẩn đoán, nhưng giới hạn output và tránh ghi secret.

Một quy trình ổn định:

1. Start child JVM với classpath/test fixture xác định.
2. Child bind connector vào loopback và chọn cổng phù hợp.
3. Child in một readiness record có định dạng máy đọc được, ví dụ \`READY|serviceUrl\`.
4. Parent đọc readiness với timeout hữu hạn.
5. Parent kết nối, thực hiện assertions.
6. Parent gửi tín hiệu shutdown qua stdin hoặc một channel test riêng.
7. Parent đợi process exit với deadline; nếu quá hạn, hủy process.
8. Cleanup file/temp directories và artifacts của test.

Quan trọng: \`ProcessBuilder\` không tự áp timeout cho startup. Nếu chờ vô hạn ở \`readLine()\`, test có thể treo cả CI. Dùng asynchronous stream reader hoặc một cơ chế deadline rõ.

## 11. Cấu hình xác thực: test khác production

Một remote JMX connector không xác thực trên loopback có thể phù hợp cho **bài test fixture ngắn**, nhưng không phù hợp để mặc định dùng trên network rộng.

Trong production hoặc test security riêng, cần cân nhắc:

- Authentication bằng credentials hoặc cơ chế phù hợp provider.
- Authorization/role restrictions để hạn chế các operations quản trị.
- TLS/SSL để bảo vệ transport.
- Giới hạn interface bind và network ingress.
- Thời hạn credentials và rotation.
- Audit các administrative invocations có side effect.

Với RMI connector, authentication có thể được cấu hình qua environment/server provider, chẳng hạn \`jmx.remote.authenticator\`, nhưng behavior và yêu cầu triển khai phải theo JDK/provider cụ thể. Khi test authentication, dùng user/password giả của môi trường cô lập, không nhúng credentials thật vào source code hoặc CI logs.

Nếu dùng Java management agent qua JVM flags như \`com.sun.management.jmxremote.*\`, đó là đường cấu hình khác với việc tự tạo \`JMXConnectorServer\` trong code. Các flags và port settings có thể khác theo JDK version. Không trộn hai cách mà không xác định endpoint nào được test.

## 12. Test âm tính về authentication và authorization

Một suite security có thể bao gồm:

| Trường hợp | Kỳ vọng |
| --- | --- |
| Credentials hợp lệ | Kết nối và đọc \`Status\` thành công |
| Credentials sai | Connection/authentication bị từ chối |
| Không cung cấp credentials khi server yêu cầu | Kết nối thất bại |
| User chỉ có quyền đọc | Đọc attribute thành công, invoke bị từ chối nếu operation không được phép |
| TLS client thiếu trust material phù hợp | Handshake thất bại |
| Endpoint bind loopback | Máy ngoài host không thể truy cập trực tiếp |

Những assertion này chỉ có ý nghĩa khi fixture thực sự bật cơ chế security tương ứng. Không thể test “không có credentials sẽ bị từ chối” trên connector mà bản thân test cấu hình không yêu cầu authentication.

Với TLS và role-based access, nên tạo fixture riêng, có certificates/keystores test được quản lý an toàn, không sử dụng material production. Tránh log password, private key hoặc full authentication environment.

## 13. Kiểm tra timeout và kết nối lỗi

Remote call có thể bị chậm hoặc mất kết nối. Các trường hợp test cần bao phủ:

1. Server chưa khởi động: client connect thất bại có kiểm soát.
2. Server đang khởi động: readiness timeout hữu hạn.
3. Server dừng giữa request: client báo exception và cleanup.
4. Client đóng connector: thao tác tiếp theo trên connection không được giả định còn hợp lệ.
5. RMI registry còn nhưng remote object port không truy cập được: lookup có thể thành công, invocation thất bại.
6. Network hoặc serialization lỗi: nhận exception tương ứng.
7. Operation server-side chạy lâu: client không được retry mù nếu không biết kết quả.

**Timeout transport không đồng nghĩa timeout thực thi operation.** Ngay cả khi client ngừng chờ, server-side operation có thể tiếp tục. Với các operation có side effect, thiết kế request ID, idempotency key hoặc trạng thái có thể tra cứu để tránh gọi lặp không an toàn.

Không có một property timeout portable duy nhất cho mọi \`JMXConnector\` implementation. Một số RMI transport settings là provider/JDK-specific. Test nên xác định rõ provider và version thay vì dựa vào một key không được bảo đảm.

## 14. Chuẩn hóa service URL và advertised hostname

JMX over RMI thường gây khó khăn ở hai tầng:

**Tầng 1 — registry lookup.** Client kết nối tới \`rmi://host:port/jmxrmi\` để nhận stub.

**Tầng 2 — remote object invocation.** Stub có thể chỉ tới một host/port khác. Nếu địa chỉ này là hostname không phân giải được hoặc interface không thể truy cập, lookup thành công nhưng thao tác trên MBean thất bại.

Ví dụ một container chỉ khai báo:

\`\`\`text
JMX URL:
  service:jmx:rmi:///jndi/rmi://test-jmx:9010/jmxrmi
\`\`\`

nhưng RMI stub quảng bá \`127.0.0.1\` hoặc hostname của container server. Client trong container khác có thể không gọi được remote object.

Trong test two-JVM trên cùng host, loopback và advertised host \`127.0.0.1\` thường phù hợp. Với hai container trên mạng test, dùng hostname/IP mà client container truy cập được và cấu hình mạng cô lập; không gán \`127.0.0.1\` theo cách khiến client trỏ về chính nó.

Mỗi test nên log **không chứa secret** về service URL, hostname quảng bá, registry port, connector port và JVM identity để dễ chẩn đoán.

## 15. Những lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| \`ConnectException: Connection refused\` | Server chưa start, sai port hoặc socket không mở | Kiểm tra readiness và bind |
| \`NameNotFoundException: jmxrmi\` | Registry chưa bind tên phù hợp | Kiểm tra URL JNDI và lifecycle |
| Lookup thành công nhưng invoke lỗi | Stub quảng bá host/port không truy cập được | Kiểm tra RMI remote object endpoint |
| \`InstanceNotFoundException\` | Sai \`ObjectName\`, exporter chưa đăng ký MBean | Kiểm tra registry trên đúng server |
| \`NotCompliantMBeanException\` | Class/interface không tuân JMX Standard MBean | Kiểm tra \`RemoteProbeMBean\` |
| \`SecurityException\` | Credentials/quyền không hợp lệ | Kiểm tra fixture auth và role |
| SSL handshake lỗi | Truststore/keystore hoặc protocol không khớp | Dùng certificates test và cấu hình đồng bộ |
| Test pass local, fail CI | Port xung đột, firewall hoặc hostname | Dùng port test cô lập và readiness timeout |
| Test fail khi chạy song song | Các fixtures dùng cùng port hoặc \`ObjectName\` trên server chung | Mỗi fixture có server riêng và endpoint riêng |
| JVM test không thoát | RMI thread, connector, registry hoặc executor chưa cleanup | Đóng client/connector và quản lý registry lifecycle |
| Client thấy dữ liệu sai | Kết nối nhầm JVM hoặc MBean cũ | Kiểm tra URL, PID, identity attribute |
| Operation không trả kết quả | Method server-side bị chặn | Thiết kế deadline/timeout nghiệp vụ, không retry mù |

Một lỗi nên được chẩn đoán theo thứ tự: **endpoint → connection → registry → ObjectName → metadata → method invocation**, thay vì lập tức chỉnh annotation Spring.

## 16. Test serialization và kiểu tham số

Remote JMX cần truyền dữ liệu qua connector. Các kiểu primitive, wrapper, \`String\` và những kiểu JMX chuẩn thường thuận tiện hơn một POJO tùy biến có phụ thuộc classpath.

Một test operation:

\`\`\`java
Object result = connection.invoke(
        name,
        "ping",
        new Object[]{"hello"},
        new String[]{"java.lang.String"});
\`\`\`

Signature phải khớp kiểu tham số khai báo trong MBean management interface. Với \`ping(String)\`, dùng \`"java.lang.String"\`.

Nếu MBean trả về object tùy biến trong Standard MBean, client remote có thể cần class đó ở classpath và đối tượng phải đáp ứng yêu cầu serialization của transport. Với MXBean, Java có quy tắc ánh xạ Open Types như \`CompositeData\`, \`TabularData\`; vì vậy thiết kế remote management interface thường ưu tiên MXBean-compatible types hoặc các kiểu đơn giản.

Không giả định một \`Map\` hoặc DTO bất kỳ luôn đi qua JMX/RMI thành công. Test nên bao gồm cả dữ liệu thực tế mà client bên ngoài sẽ dùng.

## 17. Kiểm tra remote notification

Ngoài read/invoke, JMX có notification listeners:

\`\`\`java
connection.addNotificationListener(
        name,
        listener,
        filter,
        handback);
\`\`\`

Nếu MBean implement \`NotificationBroadcaster\`, client remote có thể đăng ký listener và nhận callback. Đây là kiểm thử end-to-end sâu hơn, vì nó cần đường notification từ server tới client và state quản lý subscriptions.

Test cần:

1. Đăng ký listener.
2. Kích hoạt một notification thử nghiệm.
3. Chờ callback bằng \`CountDownLatch\` với deadline hữu hạn.
4. Assert notification type/sequence/userData phù hợp.
5. Gỡ listener bằng \`removeNotificationListener\`.
6. Đóng connector.
7. Kích hoạt lại event nếu broadcaster còn sống và xác minh listener đã được tháo theo hợp đồng test.

Không dùng \`Thread.sleep\` làm bằng chứng callback chắc chắn đã đến hoặc không đến. Khi kiểm tra **không còn nhận notification**, sử dụng cơ chế synchronization và khoảng chờ hợp lý, đồng thời tránh test âm tính dựa hoàn toàn vào timing nếu có thể kiểm tra registry/listener lifecycle trực tiếp.

## 18. Cấu hình Spring cho remote connector có lifecycle rõ ràng

Nếu Spring context sở hữu connector, có thể khai báo \`@Bean\` với init/destroy lifecycle:

\`\`\`java
@Configuration
public class RemoteConnectorConfiguration {

    @Bean(destroyMethod = "stop")
    public JMXConnectorServer remoteConnectorServer(
            MBeanServer mBeanServer) throws Exception {

        Map<String, Object> env = /* test-only environment */ Map.of();
        JMXServiceURL url = new JMXServiceURL(
                "service:jmx:rmi://127.0.0.1:0");

        JMXConnectorServer connector =
                JMXConnectorServerFactory.newJMXConnectorServer(
                        url, env, mBeanServer);

        connector.start();
        return connector;
    }
}
\`\`\`

Đây là ví dụ cấu hình khái niệm; khi dùng thật cần một môi trường RMI loopback đã được kiểm chứng như ở fixture. Vì connector được start trong factory method, nếu \`start()\` ném exception thì bean chưa được trả về để Spring gọi destroy; nên đảm bảo cleanup ngay trong catch/finally của factory method nếu đã tạo tài nguyên một phần.

Một thiết kế khác là dùng \`SmartLifecycle\` cho connector và chỉ start khi các dependencies/exporter sẵn sàng. Khi dừng context, cần stop connector trước khi release \`MBeanServer\`, và không để remote invocation mới đi vào MBean đã bị unregister.

Mục tiêu của test là kiểm chứng một vòng đời **đóng được một cách xác định**, không để lại socket/threads ngoài kiểm soát.

## 19. CI pipeline và tính tái lập

Để test remote connector chạy ổn định trên CI:

- Không hardcode port dùng chung cho mọi build.
- Không phụ thuộc server JMX ngoài fixture.
- Không mặc định CI runner có cùng DNS/firewall như máy developer.
- Đặt timeout hữu hạn cho startup, kết nối, lời gọi và shutdown.
- Tách test có network khỏi các unit tests thuần khi cần.
- Ghi log đủ để tái hiện lỗi nhưng không lộ secrets.
- Dọn process/socket/connector dù assertion thất bại.
- Hạn chế chạy song song những test phải dùng shared JVM properties hoặc RMI registry toàn cục.
- Không dùng \`Thread.sleep\` vô hạn hay polling không deadline.
- Nếu test yêu cầu TLS/authorization, đưa certificates/credentials riêng của môi trường test vào pipeline bảo mật.

Một cách tổ chức hợp lý là dùng tag \`@Tag("integration-jmx-remote")\` trong JUnit Jupiter để có thể chạy test remote riêng:

\`\`\`java
@Tag("integration-jmx-remote")
@Test
void remoteConnectorIsReachable() throws Exception {
    // Fixture tạo server và connector trong test.
}
\`\`\`

Đừng biến remote integration test thành bài kiểm tra tình trạng production endpoint. Môi trường cô lập cần tự quản lý input và output để kết quả có thể lặp lại.

## 20. Checklist trước khi coi remote connector test thành công

| Nhóm | Câu hỏi xác minh |
| --- | --- |
| Server identity | Client có kết nối đúng JVM/test fixture? |
| Isolation | MBeanServer không chia sẻ với các test khác? |
| Network | Bind loopback/isolated network, không expose ra public? |
| Port | Port được cấp và quản lý trong scope test? |
| RMI | Registry và remote object advertised host/port có khớp? |
| Connector | \`JMXConnectorServer.start()\` thành công? |
| Registration | MBean đã có đúng \`ObjectName\` trước client connect? |
| Remote read | \`getAttribute\` qua connection cho đúng giá trị? |
| Remote invoke | \`invoke\` thực thi đúng method và trả kết quả? |
| Metadata | \`getMBeanInfo\` trả đúng contract? |
| Security | Authentication/TLS test thực sự bật nếu kiểm tra? |
| Timeout | Mọi blocking step có deadline hữu hạn? |
| Cleanup | Client, Spring context, connector, registry, server và child process đều được dọn? |
| CI | Test không phụ thuộc port, IP, server hoặc credentials production? |

## 21. Bài tập thực hành

**Bài 1 — Remote loopback:** tạo \`MBeanServer\` riêng, đăng ký \`RemoteProbe\`, start \`JMXConnectorServer\`, kết nối bằng \`JMXConnectorFactory\`. Đọc \`Status\` và gọi \`ping\`.

**Bài 2 — Spring exporter:** đưa \`RemoteProbe\` vào \`ApplicationContext\` và dùng \`MBeanExporter\` thay cho đăng ký thủ công. Sau khi đóng context, xác nhận MBean không còn trong server trước khi stop connector.

**Bài 3 — Hai JVM:** chạy server fixture trong child process, client từ JUnit JVM; truyền service URL qua readiness output. Thêm startup timeout và cleanup child process.

**Bài 4 — Sai ObjectName:** kết nối remote thành công nhưng gọi \`getAttribute\` trên tên MBean không tồn tại. Giải thích khác biệt giữa lỗi transport và \`InstanceNotFoundException\`.

**Bài 5 — RMI hostname:** tạo môi trường hai container test cô lập và quan sát tác động khi stub quảng bá \`127.0.0.1\` thay vì hostname mà client container truy cập được. Không mở endpoint ra mạng công cộng.

**Bài 6 — Xác thực:** bật một JMX authenticator trong fixture riêng, thử credentials hợp lệ/không hợp lệ. Xác nhận test không log passwords và dùng TLS khi kiểm tra remote network không được tin cậy.

**Bài 7 — Notification:** đăng ký remote \`NotificationListener\`, phát một event, chờ bằng \`CountDownLatch\`, sau đó remove và đóng connector.

**Bài 8 — Resource cleanup:** cho một assertion thất bại có chủ đích, đảm bảo \`finally\` vẫn stop connector và release server. Chạy test lại để kiểm tra không còn port/registry của lần trước cản trở.

## Kết luận

Kiểm thử **remote connector trong môi trường cô lập** là kiểm chứng đường đi thực sự qua \`JMXConnector\` và \`MBeanServerConnection\`, không chỉ kiểm tra \`MBeanServer\` nội bộ. Với Spring Framework JMX, cần bảo đảm \`MBeanExporter\` và \`JMXConnectorServer\` cùng sử dụng đúng server, \`ObjectName\` nhất quán, endpoint loopback/network test được cách ly, authentication/TLS không bị suy diễn, và teardown đầy đủ. Khi test có readiness, timeout, assertion về attributes/operations, quản lý ports/hostname của RMI và cleanup rõ ràng, bạn sẽ phát hiện các lỗi remote JMX trước khi chúng gây sự cố trong môi trường vận hành.
