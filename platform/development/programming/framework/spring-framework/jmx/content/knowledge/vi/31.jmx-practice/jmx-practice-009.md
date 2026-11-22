# Spring Framework JMX — Thực hành kết nối remote qua JSR-160 trong môi trường thử nghiệm

## 1. Mục tiêu và phạm vi lab

JSR-160 (Java Management Extensions Remote API) bổ sung cách client JMX kết nối tới một MBeanServer qua connector, điển hình là RMI. Spring Framework sử dụng API này thông qua MBeanServerConnectionFactoryBean và các abstraction JMX. Mục tiêu là khởi động một JVM có MBean, mở JMX RMI connector trong môi trường thử nghiệm cô lập, kết nối từ một JVM khác, đọc attribute, gọi một operation an toàn và kiểm tra lỗi khi endpoint không sẵn sàng.

**Giới hạn quan trọng:** Lab chỉ sử dụng loopback 127.0.0.1 và thông tin không nhạy cảm. Các ví dụ không bật authentication hoặc TLS chỉ phù hợp trên máy phát triển cô lập để hiểu API. Không dùng nguyên cấu hình đó cho server production, máy dùng chung, container có port công khai hoặc mạng có người khác truy cập.

```text
JVM A — JMX server (loopback only)
  TrainingCounter MBean
           |
       MBeanServer
           |
     JMXConnectorServer
           | JSR-160 / RMI
           |
JVM B — JMX client
  JMXConnectorFactory.connect
           |
  MBeanServerConnection
           |
  getAttribute / invoke / getMBeanInfo

Spring client variant:
  MBeanServerConnectionFactoryBean -> MBeanServerConnection
```

## 2. Kiến thức nền

| Thành phần | Trách nhiệm |
|---|---|
| `MBeanServer` | Registry chứa MBeans trong JVM đích |
| `ObjectName` | Định danh một MBean trong MBeanServer |
| `JMXServiceURL` | Địa chỉ endpoint connector JSR-160 |
| `JMXConnectorServer` | Phía server cung cấp giao thức remote |
| `JMXConnectorServerFactory` | Tạo connector server từ URL, environment và MBeanServer |
| `JMXConnector` | Phiên client giữ kết nối và tài nguyên transport |
| `JMXConnectorFactory` | Tạo kết nối remote |
| `MBeanServerConnection` | API client truy vấn attribute, metadata và operation |
| `MBeanServerConnectionFactoryBean` | Spring FactoryBean cung cấp connection để inject vào bean Spring |

JSR-160 là chuẩn API remote JMX, không đồng nghĩa một cấu hình network duy nhất. Bài dùng RMI và JNDI/RMI registry vì đây là cách triển khai phổ biến với Java/JMX. Một `MBeanServer` tồn tại không tự động mở cổng remote; phải khởi động connector server riêng.

## 3. Chuẩn bị

Yêu cầu:

- Một JDK có module `java.management` và hỗ trợ JMX RMI; ví dụ JDK 17+.
- Maven hoặc công cụ biên dịch Java đang dùng trong dự án.
- Hai chương trình Java chạy trên cùng máy để tránh lộ connector thử nghiệm ra ngoài.
- Spring Framework `spring-context` nếu muốn làm thêm phần Spring client.
- Cổng loopback chưa bị chiếm, ví dụ 11099 và 11100. Nếu cổng này đã sử dụng, đổi đồng bộ trong mã server và client.

Không cần mở Internet hoặc cấu hình remote JVM agent qua `com.sun.management.jmxremote` cho cách tạo connector bằng Java API trong bài. Chúng là hai con đường thiết lập connector khác nhau; tránh bật cả hai trên cùng cổng.

## 4. Tạo Standard MBean thử nghiệm

Đầu tiên tạo interface `TrainingCounterMBean`, lưu file đúng tên:

```java
package com.example.jsr160;

public interface TrainingCounterMBean {
    int getCount();
    void reset();
}
```

Tạo implementation:

```java
package com.example.jsr160;

import java.util.concurrent.atomic.AtomicInteger;

public class TrainingCounter implements TrainingCounterMBean {
    private final AtomicInteger count = new AtomicInteger(7);

    @Override
    public int getCount() {
        return count.get();
    }

    @Override
    public void reset() {
        count.set(0);
    }
}
```

Trong JMX Standard MBean convention, interface có tên `<ClassName>MBean` định nghĩa contract. Vì vậy `TrainingCounter` triển khai `TrainingCounterMBean`. Attribute `Count` là read-only, còn `reset()` là operation. Chỉ gọi reset trong lab, không dùng một operation có side effects trên dịch vụ thật để kiểm tra connection.

## 5. Tạo JSR-160 RMI connector server bằng Java

Để JMX RMI hoạt động, ví dụ dưới đây dùng RMI registry bind ở loopback và RMI server endpoint với port cố định. Đặt `java.rmi.server.hostname=127.0.0.1` trước khi export RMI objects để tránh stub quảng bá địa chỉ mạng khác.

```java
package com.example.jsr160;

import java.lang.management.ManagementFactory;
import java.rmi.registry.LocateRegistry;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import javax.management.remote.JMXConnectorServer;
import javax.management.remote.JMXConnectorServerFactory;
import javax.management.remote.JMXServiceURL;

public final class TrainingJmxServer {
    public static void main(String[] args) throws Exception {
        System.setProperty("java.rmi.server.hostname", "127.0.0.1");

        int registryPort = 11099;
        int rmiServerPort = 11100;
        LocateRegistry.createRegistry(registryPort);

        MBeanServer server = ManagementFactory.getPlatformMBeanServer();
        ObjectName name = new ObjectName(
            "com.example.training:type=Counter,name=primary"
        );

        if (!server.isRegistered(name)) {
            server.registerMBean(new TrainingCounter(), name);
        }

        JMXServiceURL url = new JMXServiceURL(
            "service:jmx:rmi://127.0.0.1:" + rmiServerPort
              + "/jndi/rmi://127.0.0.1:" + registryPort
              + "/jmxrmi"
        );

        JMXConnectorServer connector =
            JMXConnectorServerFactory.newJMXConnectorServer(
                url, null, server
            );

        connector.start();
        System.out.println("JMX URL: " + url);
        System.out.println("PID: " + ProcessHandle.current().pid());
        System.out.println("Press Enter to stop...");

        try {
            System.in.read();
        } finally {
            connector.stop();
            if (server.isRegistered(name)) {
                server.unregisterMBean(name);
            }
        }
    }
}
```

### Cách hoạt động

1. Registry dùng cổng 11099 để client tra cứu RMI stub.
2. JMX RMI server dùng cổng 11100 làm endpoint export trong URL.
3. Connector được gắn với platform MBeanServer đã chứa `TrainingCounter`.
4. `connector.start()` mở connector và bind stub vào registry dưới `jmxrmi`.
5. Client phải truy cập được **cả những endpoint mà stub trả về**, không chỉ cổng registry.
6. Khi người dùng nhấn Enter, chương trình đóng connector và unregister MBean của lab.

**Lưu ý về an toàn lab:** `java.rmi.server.hostname` ảnh hưởng địa chỉ được quảng bá trong RMI stub, nhưng không phải một firewall/security boundary bảo đảm socket chỉ bind loopback trong mọi cấu hình JDK. Nếu phải bảo đảm loopback-only, dùng RMI socket factories bind loopback hoặc sandbox/firewall chặn inbound connections; không tin rằng hostname property tự cô lập server. Ở môi trường production luôn cần authentication, authorization, encryption và network controls.

## 6. Tạo client Java thuần kết nối remote

```java
package com.example.jsr160;

import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

public final class TrainingJmxClient {
    public static void main(String[] args) throws Exception {
        JMXServiceURL url = new JMXServiceURL(
            "service:jmx:rmi://127.0.0.1:11100"
              + "/jndi/rmi://127.0.0.1:11099/jmxrmi"
        );

        try (JMXConnector connector =
                 JMXConnectorFactory.connect(url)) {

            MBeanServerConnection connection =
                connector.getMBeanServerConnection();

            ObjectName name = new ObjectName(
                "com.example.training:type=Counter,name=primary"
            );

            System.out.println("Registered: "
                + connection.isRegistered(name));

            Object value = connection.getAttribute(name, "Count");
            System.out.println("Count before: " + value);

            connection.invoke(
                name, "reset", new Object[0], new String[0]
            );

            System.out.println("Count after: "
                + connection.getAttribute(name, "Count"));
        }
    }
}
```

Với server lab, client dự kiến in `Count before: 7` và `Count after: 0` nếu chưa có actor khác can thiệp. Phép thử remote thực hiện các thao tác qua `MBeanServerConnection`, không tham chiếu trực tiếp tới object Java của JVM A.

Trong lab, chạy `TrainingJmxServer` ở terminal thứ nhất, rồi chạy `TrainingJmxClient` ở terminal thứ hai. Không tắt JVM server trước khi client hoàn tất.

## 7. Khám phá MBeanInfo qua remote connection

Đọc metadata để xác nhận đúng server và contract:

```java
ObjectName name = new ObjectName(
    "com.example.training:type=Counter,name=primary"
);

var info = connection.getMBeanInfo(name);
System.out.println(info.getClassName());

for (var attribute : info.getAttributes()) {
    System.out.printf(
        "%s type=%s read=%s write=%s%n",
        attribute.getName(),
        attribute.getType(),
        attribute.isReadable(),
        attribute.isWritable()
    );
}

for (var operation : info.getOperations()) {
    System.out.println(operation.getName());
}
```

Ở đây, `Count` phải được hiển thị là readable, không writable, và `reset` là một operation không tham số. `MBeanInfo` cũng hữu ích khi các công cụ quản trị gặp lỗi `AttributeNotFoundException` hoặc không gọi được operation do sai signature.

## 8. Kết nối bằng Spring MBeanServerConnectionFactoryBean

Spring Framework cho phép khai báo remote connection như một Spring bean. Ví dụ Java configuration:

```java
package com.example.jsr160;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.support.MBeanServerConnectionFactoryBean;

@Configuration
public class TrainingJmxClientConfig {
    @Bean
    public MBeanServerConnectionFactoryBean remoteMBeanConnection()
            throws Exception {
        MBeanServerConnectionFactoryBean factory =
            new MBeanServerConnectionFactoryBean();

        factory.setServiceUrl(
            "service:jmx:rmi://127.0.0.1:11100"
              + "/jndi/rmi://127.0.0.1:11099/jmxrmi"
        );
        return factory;
    }
}
```

Với FactoryBean, Spring inject **sản phẩm** là `MBeanServerConnection` vào service, thay vì bắt mọi service tự tạo và đóng một `JMXConnector`:

```java
package com.example.jsr160;

import javax.management.MBeanServerConnection;
import javax.management.ObjectName;

public class RemoteTrainingReader {
    private final MBeanServerConnection connection;

    public RemoteTrainingReader(MBeanServerConnection connection) {
        this.connection = connection;
    }

    public int getCount() throws Exception {
        ObjectName name = new ObjectName(
            "com.example.training:type=Counter,name=primary"
        );
        return (Integer) connection.getAttribute(name, "Count");
    }
}
```

Bean wiring:

```java
@Bean
RemoteTrainingReader remoteTrainingReader(
        @Qualifier("remoteMBeanConnection")
        MBeanServerConnection connection) {
    return new RemoteTrainingReader(connection);
}
```

Ứng dụng cần import `org.springframework.beans.factory.annotation.Qualifier`. FactoryBean tiện cho dependency injection, nhưng không đồng nghĩa Spring tự reconnect sau mọi lần mất mạng. Nếu client được khởi động trước server lab, context có thể lỗi ở bước tạo connection tùy cấu hình và thời điểm khởi tạo.

## 9. Xử lý credentials trong client

Trong production, JMX connector phải có authentication và authorization. Với một connector hỗ trợ JMX credentials, client có thể truyền environment:

```java
import java.util.HashMap;
import java.util.Map;
import javax.management.remote.JMXConnector;

Map<String, Object> env = new HashMap<>();
env.put(
    JMXConnector.CREDENTIALS,
    new String[] { username, password }
);

factory.setEnvironment(env);
```

Lab dùng RMI connector không xác thực không đại diện cho cấu hình production; **không coi việc truyền credentials ở client là đã bảo mật server**. Server phải thực thi authenticator/authorization, transport phải được bảo vệ và credentials phải đến từ secret manager. Không commit password vào Git hoặc in `env` ra log.

## 10. Dùng JConsole kết nối remote

Để thử giao diện quản trị:

1. Chạy JVM server lab.
2. Mở `jconsole` từ JDK.
3. Chọn **Remote Process** (hoặc trường kết nối tương ứng).
4. Nhập JMX service URL mà server in ra.
5. Kết nối, mở tab **MBeans**.
6. Tìm domain `com.example.training` và ObjectName `type=Counter,name=primary`.
7. Đọc attribute `Count` và gọi operation `reset()` trong môi trường thử nghiệm.

JConsole phiên bản khác nhau có thể có cách nhập JMX URL hơi khác. Nếu kết nối bằng JConsole không thành công nhưng Java client hoạt động, hãy kiểm tra URL, RMI connector support, JDK, endpoint và trạng thái JVM server.

## 11. Lỗi thường gặp khi kết nối JSR-160

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra |
|---|---|---|
| `Connection refused` tại registry | Registry không chạy, sai port, server chưa start | Kiểm tra JVM server và cổng 11099 |
| Registry kết nối nhưng RMI call lỗi | Stub trả hostname/port không truy cập | Kiểm tra `java.rmi.server.hostname`, port 11100 |
| `UnknownHostException` | Tên host trong URL hoặc RMI stub không resolve | Dùng loopback trong lab, kiểm tra DNS |
| `IOException` khi connect | Endpoint chưa sẵn sàng hoặc transport hỏng | Kiểm tra connector.start(), network, cause chain |
| `SecurityException` | Authentication/authorization policy từ chối | Kiểm tra config server và credentials |
| `InstanceNotFoundException` | ObjectName không được đăng ký trong server đích | `queryNames`, `isRegistered` |
| `AttributeNotFoundException` | Gọi sai attribute, ví dụ `count` thay vì `Count` | Đọc `MBeanInfo.getAttributes()` |
| `ReflectionException` | Sai tên operation hoặc signature | Đọc `MBeanInfo.getOperations()` |
| Client kết nối được nhưng không thấy MBean | Connector gắn sai MBeanServer hoặc nhầm ObjectName | So registry và server reference |
| Client chạy sau khi server dừng | Connector/session đã đóng | Restart server rồi tạo connection mới |

**Không gán mọi lỗi kết nối thành lỗi xác thực.** DNS/TCP/RMI có thể hỏng trước khi JVM đích kiểm tra username/password. Một `SecurityException` cũng cần được phân loại theo thời điểm connect hay invoke.

## 12. Kiểm thử mất kết nối

Thực hiện chuỗi thử nghiệm:

1. Khởi động server và kết nối client thành công.
2. Đọc `Count` và xác nhận giá trị hợp lệ.
3. Dừng server bằng Enter.
4. Gọi lại client; kiểm tra nhận lỗi transport rõ ràng thay vì kết luận MBean không tồn tại.
5. Khởi động lại server.
6. Tạo kết nối mới và kiểm tra `Count` theo state mới.

Đừng cho rằng reference `MBeanServerConnection` cũ tự trở lại trạng thái khỏe sau khi JVM đích restart. Một application giám sát thực tế phải có health check, backoff khi reconnect và lifecycle connector rõ ràng.

## 13. Lỗi RMI với Docker, NAT và Kubernetes

Trong network phức tạp, việc chỉ mở registry port không đủ: RMI stub có thể chứa một địa chỉ server khác và một port thứ hai. Nếu advertised hostname là địa chỉ nội bộ container mà client ngoài container không thể route tới, registry lookup vẫn có thể thành công nhưng JMX invocation sẽ fail.

Trong production cần thiết kế:

- Hostname có thể truy cập từ client.
- Registry port và RMI server port cụ thể.
- SSL/TLS với certificate và truststore phù hợp.
- Firewall/network policies giới hạn nguồn kết nối.
- Authentication và authorization.
- Monitoring kết nối, authentication failures, timeout và reconnect.

Không bê nguyên lab loopback/unauthenticated connector sang production; không mở ngẫu nhiên các cổng RMI ra Internet để khắc phục lỗi.

## 14. So sánh local và remote access

| Tiêu chí | Local MBeanServer | Remote JSR-160 connection |
|---|---|---|
| Cách lấy | `ManagementFactory.getPlatformMBeanServer()` | `JMXConnectorFactory.connect(...)` |
| Ranh giới | Cùng JVM | Qua network/transport |
| Độ trễ | Gọi nội bộ Java | Phụ thuộc RMI/network |
| Authentication | Theo quyền trong JVM | Phải cấu hình connector authentication |
| Lỗi thường gặp | MBean registration/contract | Thêm DNS, TLS, network, timeout |
| Cleanup | Owner của MBean registration | Connector lifecycle và listener subscriptions |

Mỗi JVM có MBeanServer riêng. Một client JVM gọi `ManagementFactory.getPlatformMBeanServer()` chỉ truy cập **server của chính client**, không truy cập server của JVM A. Muốn xem MBean ở JVM A cần remote connection hoặc công cụ kết nối vào JVM đó.

## 15. Bài tập mở rộng

### Bài 1 — Đọc thuộc tính

Không gọi reset. Dùng `MBeanServerConnection` đọc `Count`, in kiểu Java của kết quả và ObjectName hiện tại.

### Bài 2 — Metadata

Đọc `MBeanInfo` để xác định `Count` có writable không, `reset` có bao nhiêu tham số, và thử truy vấn một ObjectName pattern.

### Bài 3 — URL không hợp lệ

Đổi client registry port thành một cổng không có server. Quan sát exception và phân loại transport failure; không gọi là sai mật khẩu.

### Bài 4 — Operation có tham số

Thêm `setCount(int value)` vào Standard MBean. Client gọi với params `new Object[]{5}` và signature `new String[]{"int"}`. Vì primitive method signature là `int`, không dùng `"java.lang.Integer"` trong signature.

### Bài 5 — Spring injection

Dùng `MBeanServerConnectionFactoryBean` inject connection vào `RemoteTrainingReader`, đọc `Count` và so kết quả với client Java thuần.

### Bài 6 — Auth test

Bổ sung một JMXAuthenticator đơn giản trong **môi trường test cô lập** và dùng credential fixture. Kiểm tra login hợp lệ/thất bại, nhưng không thử brute-force và không log password.

## 16. Checklist hoàn thành lab

- JVM server đăng ký `TrainingCounter` vào MBeanServer.
- Connector server được khởi động và in JMX URL.
- Client kết nối bằng JSR-160 và tạo MBeanServerConnection.
- ObjectName được tìm thấy qua `isRegistered`.
- `Count` được đọc và `reset()` được gọi đúng trong môi trường lab.
- `MBeanInfo` mô tả đúng attribute/operation.
- Spring client inject connection bằng FactoryBean.
- Endpoint và port được kiểm tra khi mất kết nối.
- Connector và MBean registration được cleanup khi dừng.
- Không mở connector test ra mạng công cộng hoặc production.

## 17. Tổng kết

JSR-160 cho phép JMX client ở JVM khác quản trị MBeans thông qua connector. Bài thực hành tạo Standard MBean, đăng ký với MBeanServer, mở RMI connector, kết nối bằng JMXConnectorFactory và đọc/gọi thông qua MBeanServerConnection. Spring Framework có thể đơn giản hóa phía client bằng MBeanServerConnectionFactoryBean. Thành công của lab phụ thuộc vào ObjectName đúng, URL JMX RMI đầy đủ, registry/stub endpoints có thể truy cập và vòng đời connector rõ ràng. Môi trường production còn cần authentication, authorization, bảo vệ transport và network isolation nghiêm ngặt.