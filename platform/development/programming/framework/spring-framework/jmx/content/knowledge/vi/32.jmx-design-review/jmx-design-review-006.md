# Kiểm tra hành vi local, remote, proxy và lỗi mạng trong Spring Framework JMX

## 1. Mục tiêu đánh giá

Một ứng dụng Spring có thể công bố các bean quản trị qua MBeanExporter, cho phép gọi trên MBeanServer trong cùng JVM, qua MBeanProxyFactoryBean hoặc từ JVM khác qua JMX RMI connector. Các con đường này chia sẻ giao diện JMX nhưng không có cùng tính chất lỗi. Nếu chỉ kiểm thử một getter Java trên target bean, ta chưa biết hợp đồng MBean có đúng, Spring proxy có ánh xạ chính xác hay remote connector có đi qua firewall/TLS đúng không.

Bài này xây dựng ma trận đánh giá bốn nhóm:

1. **Local JMX:** registration, ObjectName, MBeanInfo, attribute/operation và lifecycle.
2. **Spring JMX proxy:** proxyInterface, mapping getter/setter/operation, AOP và lỗi chuyển tiếp.
3. **Remote JMX:** RMI Registry, connector, MBeanServerConnection, authentication/TLS và serialization.
4. **Lỗi mạng:** timeout, connection drop, reconnect, stale stub và invoke không rõ kết quả.

Kết quả mong muốn không đơn thuần là “connect được”; hệ thống cần thất bại theo cách có thể phân loại, không thực thi lặp operation nguy hiểm và biết phục hồi khi connector thay đổi.

## 2. Đường đi request và điểm lỗi

~~~text
Application caller
  |
  +--> Local MBeanServer -----------+
  |                                 |
  +--> MBeanProxyFactoryBean        |
  |       |                         |
  |       v                         |
  |  MBeanServerConnection          |
  |       |                         |
  |       +--> Local server --------+
  |       |
  |       +--> JMXConnector / RMI
  |                  |
  |            JMXConnectorServer
  |                  |
  +------------------+
                     |
                     v
                 MBeanServer
                     |
                     v
                  MBean
                     |
                     v
             Business target/AOP
~~~

Một request remote có thể lỗi trước khi tới MBean, khi tra cứu RMI Registry, ở bước TLS/auth, trong JMX method dispatch hoặc trong target method. Không nên coi mọi IOException là lỗi Spring exporter hoặc mọi ReflectionException là lỗi mạng.

## 3. Contract quản trị mẫu

Standard MBean:

~~~java
public interface WorkerControlMBean {
    int getQueueDepth();
    boolean isPaused();
    void pause();
    void resume();
}
~~~

~~~java
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public final class WorkerControl implements WorkerControlMBean {
    private final AtomicBoolean paused = new AtomicBoolean();
    private final AtomicInteger queueDepth = new AtomicInteger(5);

    public int getQueueDepth() {
        return queueDepth.get();
    }

    public boolean isPaused() {
        return paused.get();
    }

    public void pause() {
        paused.set(true);
    }

    public void resume() {
        paused.set(false);
    }
}
~~~

MBeanServer đăng ký với ObjectName:

~~~java
ObjectName name = new ObjectName(
    "com.example.jobs:type=Worker,name=Test"
);

server.registerMBean(new WorkerControl(), name);
~~~

Contract kỳ vọng:

| Thành phần | JMX metadata |
| --- | --- |
| QueueDepth | Readable attribute kiểu int |
| Paused | Readable attribute kiểu boolean |
| pause | Operation không tham số |
| resume | Operation không tham số |
| ObjectName | com.example.jobs:type=Worker,name=Test |

Trong test production-like, nên tách những operation có side effect khỏi read-only probes. Test không được dùng để dừng worker production.

## 4. Ma trận đánh giá

| Kiểm thử | Local | Spring proxy | Remote | Fault injection |
| --- | --- | --- | --- | --- |
| Đăng ký ObjectName | Có | Có | Có | MBean unregister |
| getAttribute | Có | Getter proxy | Có | Timeout/disconnect |
| invoke | Có | Operation proxy | Có | Uncertain outcome |
| MBeanInfo | Có | Gián tiếp | Có | Metadata lookup fail |
| Getter/setter mapping | Có | Bắt buộc | Có | Sai signature |
| AOP proxy server-side | Theo cấu hình | Có | Có | Target failure |
| RMI Registry và stub | Không | Chỉ nếu remote | Có | Registry/port lỗi |
| Authentication/TLS | Không | Theo connection | Có | Credential/cert lỗi |
| Reconnect | Không | Khi remote | Có | Connector restart |
| Notification | Có | Có thể | Có | Listener mất kết nối |
| Performance | Getter/dispatch | Proxy overhead | Network overhead | Retry burst |

Mỗi hàng cần một test hoặc phép kiểm tra định vị tầng. Không xem một integration test connect thành công là bao phủ đầy đủ các tình huống còn lại.

## 5. Kiểm thử local bằng MBeanServer riêng

~~~java
import static org.junit.jupiter.api.Assertions.*;
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;

class LocalJmxTest {
    @Test
    void registrationMetadataAndInvocationWork() throws Exception {
        MBeanServer server =
            MBeanServerFactory.createMBeanServer("jmx-test");

        ObjectName name = new ObjectName(
            "com.example.jobs:type=Worker,name=Test"
        );

        try {
            server.registerMBean(new WorkerControl(), name);

            assertTrue(server.isRegistered(name));
            assertEquals(5, server.getAttribute(name, "QueueDepth"));
            assertEquals(false, server.getAttribute(name, "Paused"));

            server.invoke(
                name, "pause", new Object[0], new String[0]
            );
            assertEquals(true, server.getAttribute(name, "Paused"));
        } finally {
            if (server.isRegistered(name)) {
                server.unregisterMBean(name);
            }
            MBeanServerFactory.releaseMBeanServer(server);
        }
    }
}
~~~

Test dùng MBeanServer cô lập giúp tránh trùng ObjectName với MBean ở JVM test runner. Nó chứng minh Standard MBean contract; nếu sản phẩm dùng Spring MBeanExporter, cần thêm test khởi tạo Spring context và exporter trên đúng MBeanServer.

Luôn dọn registration mà test sở hữu. Không unregister MBean JVM nền tảng hoặc của test khác.

## 6. Đọc MBeanInfo thay vì đoán từ Java method

~~~java
var info = server.getMBeanInfo(name);

for (var a : info.getAttributes()) {
    System.out.printf(
        "%s %s readable=%s writable=%s%n",
        a.getName(),
        a.getType(),
        a.isReadable(),
        a.isWritable()
    );
}

for (var op : info.getOperations()) {
    System.out.printf(
        "operation=%s return=%s%n",
        op.getName(),
        op.getReturnType()
    );

    for (var p : op.getSignature()) {
        System.out.println("  param=" + p.getType());
    }
}
~~~

Getter getQueueDepth() có thể được công bố dưới dạng attribute QueueDepth chứ không nằm trong operation list. Với operation overload, phải so sánh tên và kiểu tham số. Nếu Spring dùng metadata assembler, annotation và AOP proxy ở server, MBeanInfo là contract thực tế client nhìn thấy.

Không suy luận rằng method không xuất hiện trong MBeanInfo là do mạng. Trước hết so sánh contract local rồi mới test remote.

## 7. Kiểm thử Spring MBeanProxyFactoryBean

~~~java
import org.springframework.jmx.access.MBeanProxyFactoryBean;

MBeanProxyFactoryBean factory = new MBeanProxyFactoryBean();
factory.setServer(server);
factory.setObjectName(name);
factory.setProxyInterface(WorkerManagementClient.class);
factory.afterPropertiesSet();

WorkerManagementClient client =
    (WorkerManagementClient) factory.getObject();

if (client == null) {
    throw new IllegalStateException("Proxy not created");
}

int queued = client.getQueueDepth();
client.pause();
boolean after = client.isPaused();
~~~

Interface client:

~~~java
public interface WorkerManagementClient {
    int getQueueDepth();
    boolean isPaused();
    void pause();
    void resume();
}
~~~

Các kiểm thử quan trọng:
- Proxy thực sự implement đúng interface client.
- Getter Java map sang JMX attribute, không phải operation cùng tên.
- Operation có tên và signature khớp với MBeanInfo.
- Kiểu trả về tương thích với interface client.
- MBean chưa đăng ký hoặc đã unregister có failure mode rõ.
- Exception được chuyển/bọc không che mất nguyên nhân thật.
- Không thêm method vào proxyInterface nếu MBean không export method đó.

Spring proxy tạo thành công không bảo đảm mọi method sẽ invoke thành công; integration test cần gọi những method thuộc contract.

## 8. AOP proxy phía server khác JMX proxy phía client

Một Spring service có thể được bọc bởi JDK/CGLIB proxy vì transaction, caching hoặc security. Còn MBeanProxyFactoryBean tạo một proxy **client** để gửi lời gọi vào MBeanServer.

~~~text
Client -> JMX client proxy -> MBeanServer
                                   |
                                   v
                             JMX adapter
                                   |
                                   v
                             AOP-proxied service
~~~

Nếu server export trực tiếp một JDK proxy, method quản trị chỉ tồn tại trên target class nhưng không nằm trên interface proxy có thể gặp vấn đề khi exporter lựa chọn metadata hoặc gọi method.

Có thể kiểm tra:

~~~java
import org.springframework.aop.support.AopUtils;

Object bean = context.getBean("workerService");

System.out.println("runtime=" + bean.getClass());
System.out.println("aop=" + AopUtils.isAopProxy(bean));
System.out.println("target=" + AopUtils.getTargetClass(bean));
~~~

Dùng MBeanInfo của registered object để đối chiếu. Tách một management adapter nhỏ thường làm contract ổn định hơn so với export toàn bộ service chịu nhiều advice.

## 9. Remote JMX: client và connector

Remote client sử dụng JMXServiceURL:

~~~java
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

JMXServiceURL url = new JMXServiceURL(
    "service:jmx:rmi:///jndi/rmi://127.0.0.1:9010/jmxrmi"
);

try (JMXConnector connector =
        JMXConnectorFactory.connect(url)) {

    var remote = connector.getMBeanServerConnection();

    if (!remote.isRegistered(name)) {
        throw new IllegalStateException("Missing MBean");
    }

    System.out.println(
        remote.getAttribute(name, "QueueDepth")
    );
}
~~~

Ví dụ giả định đã có JMXConnectorServer và RMI Registry phù hợp. Server phải gắn vào cùng MBeanServer mà exporter đăng ký MBean.

Cấu hình remote production cần authentication, TLS, network isolation và secret handling. Không đặt connector không xác thực ra Internet; không tắt auth/TLS chỉ để test đơn giản.

## 10. Hai cổng RMI và vấn đề NAT

Một endpoint RMI thường có hai bước:

~~~text
Client -> RMI Registry on host:9010
       -> lookup jmxrmi
       -> receives RMI stub
       -> connects to advertised host:9011
       -> calls JMX operations
~~~

Registry port kết nối thành công chưa bảo đảm client có thể truy cập RMI endpoint. Với Docker/Kubernetes, stub có thể quảng bá IP nội bộ không tới được từ client ngoài cluster.

Kiểm thử:
- Registry host/port đúng.
- Binding lookup đúng tên.
- Advertised hostname có thể resolve và route từ client.
- RMI endpoint port được mở/forward phù hợp.
- TLS/auth ở các kênh cần thiết.
- Connector có lifecycle owner rõ ràng.

Các thuộc tính JVM agent như com.sun.management.jmxremote.rmi.port không tự điều khiển mọi connector tùy chỉnh do Spring hoặc thư viện tạo; xác minh implementation thực tế.

## 11. Lỗi mạng cần kiểm thử

| Kịch bản | Kết quả cần quan sát | Nhóm nguyên nhân |
| --- | --- | --- |
| Registry không chạy | Connection refused/unreachable | Bootstrap |
| Registry có nhưng binding thiếu | Naming/lookup error | RMI JNDI |
| Stub quảng bá host sai | Timeout sau lookup | Network/NAT |
| RMI endpoint port bị chặn | Kết nối không hoàn tất | Firewall |
| Credentials sai | Authentication failure | Security |
| TLS truststore sai | Handshake failure | Security |
| MBean chưa đăng ký | InstanceNotFound | JMX registration |
| Proxy method không khớp | Attribute/operation missing | Contract |
| Mất kết nối khi getAttribute | Read failed | Transport |
| Mất kết nối khi invoke | Outcome có thể không rõ | Transport + business |
| Connector restart | Old connection stale | Lifecycle |
| Listener mất sau reconnect | Không nhận notification | Registration |

Fault injection chỉ nên thực hiện trong test environment cô lập hoặc môi trường đã được phê duyệt. Không chặn cổng remote JMX của production một cách tùy tiện.

## 12. Uncertain outcome khi invoke

Xem chuỗi sự kiện:

~~~text
Client sends restartWorker()
Server receives restartWorker()
Server executes operation
Network drops before response
Client sees IOException
~~~

Client không thể tự kết luận operation chưa chạy. Với lệnh có side effect, retry mù có thể thực hiện lặp thao tác nguy hiểm.

Một contract tốt cần:
- Desired-state operation như setPaused(true) thay vì togglePaused().
- Request ID ổn định cho lệnh dài hoặc không idempotent.
- Status attribute/operation để kiểm tra hậu quả.
- Deduplication ở server theo key nếu cần.
- Retry bounded theo loại lỗi, backoff và jitter.
- Version/epoch để stale controller không ghi đè quyết định mới.

Đừng nhầm network delivery với exactly-once business effect. Remote JMX không tự bảo đảm exactly-once cho custom operation.

## 13. Kiểm thử reconnection

Một kịch bản đầy đủ:

1. Start MBeanServer và register MBean.
2. Start connector A và mở client connection.
3. Query MBeanInfo, đọc attribute thành công.
4. Stop connector A.
5. Quan sát đường gọi bằng connection cũ.
6. Start connector B với cấu hình intended endpoint.
7. Tạo JMXConnector mới ở client.
8. Query lại ObjectName và MBeanInfo.
9. Thực hiện read-only probe và thao tác thử đã được phép.
10. Cleanup connectors, listeners và MBean registration.

Không giả định stop connector sẽ tự đóng RMI Registry dùng chung. Khi context redeploy, phải kiểm tra exporter unregister đúng MBean thuộc ownership của context.

Nếu ObjectName thay đổi do unique-name hoặc tên instance mới, client phải discover lại thay vì hard-code identity cũ.

## 14. Notifications qua remote connector

Client có thể đăng ký listener:

~~~java
NotificationListener listener =
    (notification, handback) ->
        System.out.println(notification.getType());

remote.addNotificationListener(
    name, listener, null, null
);
~~~

Sau reconnect, không nên mặc định listener registration cũ vẫn hoạt động. Tùy connector và client lifecycle, cần đăng ký lại listener rồi kiểm tra không bị callback trùng.

Test notification cần xác minh type, source, filter, handback và cleanup. Notification JMX không phải event log bền vững có guaranteed replay; nếu cần exactly-once event processing, dùng cơ chế messaging phù hợp.

## 15. Security testing cho remote path

Một ma trận bảo mật:
- Client không có credential không vào được khi auth bật.
- Credential sai bị từ chối.
- Principal hợp lệ đọc được MBean thuộc quyền.
- Operation có side effect bị kiểm soát ở server/connector.
- TLS certificate hợp lệ được chấp nhận.
- Certificate không hợp lệ bị từ chối theo policy.
- Không log secret trong service URL, exception hoặc metrics.
- Credential rotation/revocation được kiểm chứng.
- Session hiện có sau revoke được đánh giá theo threat model.

Spring Security HTTP và JMX RMI không phải cùng một kênh; rule cho /actuator/** không tự bảo vệ connector remote JMX.

## 16. So sánh metadata local và remote

~~~java
var localInfo = localServer.getMBeanInfo(name);
var remoteInfo = remoteConnection.getMBeanInfo(name);
~~~

So sánh contract cần thiết:
- Attribute names/types/readable/writable flags.
- Operation names/signatures/return types.
- Notification types.
- Descriptions nếu là một phần của API dành cho vận hành.

Không so sánh thô toàn bộ toString() nếu thứ tự metadata hay descriptor khác nhau nhưng contract tương thích. Nếu metadata remote không giống local, kiểm tra đúng JVM, đúng server và đúng ObjectName trước khi kết luận connector biến đổi dữ liệu.

## 17. Kiểm tra hiệu năng và tải

Các lớp performance khác nhau:
- Local getter/operation cost.
- Spring proxy dispatch overhead.
- RMI serialization, TLS và network RTT.
- Concurrent client polling.
- MBean discovery và getMBeanInfo frequency.
- Notification rate/queue pressure.
- CPU/GC/lock contention của target.
- Reconnect/retry burst khi connector lỗi.

Benchmark phải giữ workload gần production và đo cả service throughput/p95/p99, không chỉ JMX call time. Một getter chạy DB query có thể làm service chậm dưới polling load dù test local rất nhanh.

## 18. Kiểm soát flaky test

Để test ổn định:
- Dùng MBeanServer riêng hoặc ObjectName duy nhất cho fixture.
- Không hard-code cổng đang được suite parallel test chia sẻ.
- Sử dụng timeout bounded và condition-based wait thay Thread.sleep cố định.
- Dọn client connector, server connector, registry và listener đúng owner.
- Không gọi operation nguy hiểm trên production.
- Không bắt toàn bộ exception rồi bỏ qua.
- Phân biệt lỗi transport, auth, metadata và business.
- Ghi lỗi theo giai đoạn: connect, lookup, authentication, getMBeanInfo, attribute và invoke.
- Nếu inject network fault, rollback chính xác network policy sau test.

## 19. Checklist đánh giá thiết kế

- [ ] Local MBeanServer đăng ký đúng ObjectName.
- [ ] MBeanInfo chứa đúng attribute/operation/signature.
- [ ] Local getAttribute/invoke hoạt động.
- [ ] MBeanProxyFactoryBean trả đúng proxyInterface.
- [ ] AOP proxy server-side không làm mất management API.
- [ ] Remote connector gắn đúng server.
- [ ] RMI Registry và endpoint host/port truy cập được.
- [ ] TLS/auth/authorization được kiểm thử.
- [ ] Network failure được phân loại và không retry vô hạn.
- [ ] Invoke timeout xử lý uncertain outcome/idempotency.
- [ ] Reconnect/redeploy không giữ stale connections.
- [ ] Notifications có policy re-registration.
- [ ] Metadata local/remote tương đương theo contract.
- [ ] Có test concurrency/performance dưới workload thực tế.
- [ ] Cleanup mọi tài nguyên thuộc fixture.

## 20. Ghi nhớ

**Đánh giá Spring JMX cần vượt qua local, proxy, remote và fault injection có kiểm soát.** Local kiểm chứng MBean contract; proxy kiểm chứng ánh xạ typed Java calls; remote kiểm chứng kết nối, RMI/TLS và security; lỗi mạng kiểm chứng timeout/reconnect và cách bảo vệ operation có side effect. Dùng cùng ObjectName/MBeanServer dự kiến, phân loại lỗi đúng tầng và kiểm thử lifecycle để tránh những lỗi chỉ lộ ra khi vận hành thực tế.
