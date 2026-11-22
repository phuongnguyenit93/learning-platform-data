# MBeanProxyFactoryBean với server connection từ xa

## 1. Bối cảnh và mục tiêu

JMX (Java Management Extensions) không chỉ dành cho công cụ chạy cùng JVM. Một ứng dụng Spring có thể cần đọc trạng thái của một Java service ở máy khác, gọi operation quản trị hoặc kết nối đến một MBeanServer được công bố qua remote connector. Nếu code ứng dụng thao tác trực tiếp với `MBeanServerConnection`, mỗi lần đọc thuộc tính phải gọi `getAttribute`, mỗi operation phải truyền tên và chữ ký vào `invoke`, và client phải xử lý các kiểu dữ liệu JMX. Spring Framework cung cấp `MBeanProxyFactoryBean` để làm cho client có thể gọi **một Java interface kiểu mạnh**, trong khi lời gọi thực tế vẫn được chuyển tới MBean thông qua remote JMX connector.

Ví dụ:

```java
// Thay vì:
Object value = connection.getAttribute(
    new ObjectName("demo.service:type=Worker,name=primary"),
    "ActiveJobs"
);

// Ta muốn:
int active = workerManagement.getActiveJobs();
```

Ở trường hợp thứ hai, `workerManagement` là JMX proxy, không phải instance target local. Phương thức trên proxy kích hoạt truy vấn tới MBeanServer bên kia kết nối.

Bài học tập trung vào:

- Vai trò của `JMXServiceURL`, `JMXConnector`, `MBeanServerConnection` và `ObjectName`.
- Cách `MBeanProxyFactoryBean` tạo proxy cho management interface.
- Cấu hình kết nối remote qua Spring và phân biệt `MBeanServerConnectionFactoryBean` với proxy.
- Lifecycle của connector và lỗi khi target MBean chưa đăng ký hoặc connection bị mất.
- An toàn kết nối, xác thực, dữ liệu, timeout, retries và operation có tác dụng phụ.
- Ví dụ client/server đơn giản và cách xác minh kết quả bằng metadata.

## 2. Sơ đồ đường đi của một lời gọi

```text
JVM client / Spring ApplicationContext
    |
    | workerManagement.getActiveJobs()
    v
MBeanProxyFactoryBean -> typed management proxy
    |
    v
MBeanClientInterceptor
    |
    | JMX request qua MBeanServerConnection
    v
JMXConnector (client)
    |
    | remote transport: thường là RMI/JMX
    v
JMXConnectorServer (server JVM)
    |
    v
MBeanServer
    |
    | ObjectName: demo.service:type=Worker,name=primary
    v
Registered MBean (target JVM)
    |
    v
Business service / runtime state
```

Các vai trò cần tách rõ:

| Thành phần | Bên nào? | Công dụng |
|---|---|---|
| `MBeanExporter` | Server Spring (nếu dùng Spring) | Đưa bean vào MBeanServer |
| `JMXConnectorServer` | Server JVM | Công bố MBeanServer qua giao thức remote |
| `JMXServiceURL` | Client | Định vị connector endpoint |
| `JMXConnector` | Client | Quản lý kết nối tới JMX server |
| `MBeanServerConnection` | Client | Giao diện thao tác với MBeanServer |
| `MBeanProxyFactoryBean` | Client Spring | Tạo proxy typed để gọi MBean |
| `ObjectName` | Cả hai | Xác định MBean trên server |
| Management interface | Client và server theo hợp đồng | Chữ ký getter/setter/operation |

Proxy **không tạo remote connector server**, không tự export target MBean và không làm cho một endpoint chưa có JMX connector trở nên truy cập được. Đó là ba trách nhiệm độc lập.

## 3. MBeanServerConnection: hợp đồng chung cho local và remote

`javax.management.MBeanServerConnection` định nghĩa các thao tác như:

```java
Object value = connection.getAttribute(name, "ActiveJobs");

connection.setAttribute(
    name, new Attribute("WarningThreshold", 50)
);

connection.invoke(
    name,
    "pause",
    new Object[0],
    new String[0]
);
```

Với kết nối **local**:

```java
MBeanServerConnection connection =
    ManagementFactory.getPlatformMBeanServer();
```

Với kết nối **remote**, client thường lấy giao diện đó từ một `JMXConnector`:

```java
JMXServiceURL url = new JMXServiceURL(serviceUrl);
JMXConnector connector = JMXConnectorFactory.connect(url, environment);
MBeanServerConnection connection = connector.getMBeanServerConnection();
```

Mặc dù caller sử dụng cùng interface, remote có thêm những yếu tố không có ở local call: mạng, xác thực, giới hạn firewall, phiên làm việc, sự cố kết nối, latency, serialization và khả năng operation đã được thực hiện dù client không nhận response.

**Remote JMX là giao diện quản trị có đặc quyền.** Không mở connector ra Internet công khai; không vô hiệu hóa authentication hoặc TLS chỉ để chạy ví dụ nhanh. Những cấu hình thực tế về cổng, RMI host và SSL phụ thuộc topology triển khai và phải được xác định cùng đội vận hành.

## 4. Management interface làm hợp đồng phía client

Giả sử server đã đăng ký một Standard MBean tại:

```text
demo.service:type=Worker,name=primary
```

Interface quản trị:

```java
// WorkerManagementMBean.java
public interface WorkerManagementMBean {
    int getActiveJobs();
    int getWarningThreshold();
    void setWarningThreshold(int threshold);
    void pause();
    void resume();
}
```

Theo JMX convention:

- `ActiveJobs`: attribute chỉ đọc.
- `WarningThreshold`: attribute đọc–ghi.
- `pause()`, `resume()`: operations.

Server có thể triển khai:

```java
public class WorkerManagement
        implements WorkerManagementMBean {
    private volatile int activeJobs = 3;
    private volatile int warningThreshold = 100;
    private volatile boolean paused;

    @Override
    public int getActiveJobs() {
        return activeJobs;
    }

    @Override
    public int getWarningThreshold() {
        return warningThreshold;
    }

    @Override
    public void setWarningThreshold(int threshold) {
        if (threshold < 1 || threshold > 1000) {
            throw new IllegalArgumentException("threshold: 1..1000");
        }
        warningThreshold = threshold;
    }

    @Override
    public void pause() {
        paused = true;
    }

    @Override
    public void resume() {
        paused = false;
    }

    public boolean isPausedInternally() {
        return paused;
    }
}
```

Vì class tên `WorkerManagement` implement `WorkerManagementMBean`, nó tuân theo quy ước Standard MBean. Method `isPausedInternally()` không thuộc management interface nên không được công bố qua Standard MBean đó.

Tại client, ta cần interface tương thích về tên, chữ ký và kiểu. Client có thể sử dụng cùng artifact Java chứa management interface, hoặc duy trì một bản hợp đồng tương thích. **Không nhất thiết cần implementation class của server**, nhưng client phải hiểu những kiểu dữ liệu xuất hiện trong interface.

Nếu server sử dụng Spring ModelMBean tạo từ annotation/assembler, hãy kiểm tra `MBeanInfo` thực tế để bảo đảm thuộc tính và operation trên interface proxy ánh xạ đúng. Tên interface phía client không tự tạo API mới trên server.

## 5. Tạo proxy từ JDK trước khi dùng Spring

JDK có công cụ trực tiếp:

```java
WorkerManagementMBean proxy = JMX.newMBeanProxy(
    connection,
    objectName,
    WorkerManagementMBean.class
);

int current = proxy.getActiveJobs();
proxy.setWarningThreshold(75);
proxy.pause();
```

Ở đây:

- `connection` là `MBeanServerConnection` remote.
- `objectName` là `ObjectName` của MBean đã đăng ký.
- `WorkerManagementMBean.class` là interface mà proxy triển khai.

JDK proxy giúp xóa những chuỗi hard-coded tên thuộc tính khỏi caller, nhưng vòng đời connector, wiring Spring và exception handling vẫn là trách nhiệm của ứng dụng.

Nếu target là MXBean, hãy xem xét `JMX.newMXBeanProxy(...)`, vì MXBean có OpenType mapping. Không giả định `JMX.newMBeanProxy` sẽ tự xử lý mọi kiểu DTO như proxy MXBean.

## 6. MBeanProxyFactoryBean cung cấp gì?

`org.springframework.jmx.access.MBeanProxyFactoryBean` là một Spring `FactoryBean` tạo đối tượng proxy triển khai interface được chỉ định. Proxy sử dụng cơ chế `MBeanClientInterceptor` để chuyển lời gọi Java thành JMX request.

Một bean consumer có thể sử dụng:

```java
public final class OperationsDashboard {
    private final WorkerManagementMBean worker;

    public OperationsDashboard(WorkerManagementMBean worker) {
        this.worker = worker;
    }

    public int activeJobs() {
        return worker.getActiveJobs();
    }

    public void changeWarningThreshold(int value) {
        worker.setWarningThreshold(value);
    }
}
```

Consumer không cần biết `ObjectName` hoặc gọi `MBeanServerConnection` trực tiếp. Những chi tiết này được cấu hình ở proxy factory.

Nhưng cần nhớ rằng method trên proxy có thể thực hiện **network I/O**, ngay cả khi cú pháp trông như method Java bình thường:

```java
worker.getActiveJobs(); // Remote round-trip có thể chậm hoặc lỗi.
```

Không gọi proxy trong path xử lý hot loop với tần suất cao mà không cân nhắc latency và availability.

## 7. Cách cấu hình Spring: hai hướng

Có hai cách tổ chức hợp lý.

### Hướng A — MBeanProxyFactoryBean quản lý việc kết nối

Spring `MBeanProxyFactoryBean` có khả năng cấu hình địa chỉ remote thông qua thuộc tính service URL do nó kế thừa từ lớp kết nối JMX của Spring. Ví dụ:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.access.MBeanProxyFactoryBean;

@Configuration
public class RemoteJmxProxyConfiguration {

    @Bean
    public MBeanProxyFactoryBean workerManagementProxy() {
        MBeanProxyFactoryBean proxy = new MBeanProxyFactoryBean();

        proxy.setServiceUrl(
            "service:jmx:rmi:///jndi/rmi://jmx.example.internal:9999/jmxrmi"
        );
        proxy.setObjectName(
            "demo.service:type=Worker,name=primary"
        );
        proxy.setProxyInterface(WorkerManagementMBean.class);

        // Cấu hình authentication/TLS theo connector và hạ tầng.
        return proxy;
    }
}
```

URL trên **chỉ là ví dụ cấu trúc**, không phải endpoint có thể kết nối. Không dùng nó trong production khi chưa triển khai connector server, DNS, firewall và bảo mật tương ứng.

Cách này phù hợp khi một proxy trực tiếp quản lý kết nối tới một endpoint. Với nhu cầu quản lý nhiều proxy, tái sử dụng connection hoặc kiểm soát riêng vòng đời connector, hãy cân nhắc hướng B.

### Hướng B — cấu hình MBeanServerConnectionFactoryBean rồi gắn vào proxy

Spring cung cấp `org.springframework.jmx.support.MBeanServerConnectionFactoryBean` để xây dựng `MBeanServerConnection` từ service URL.

```java
import javax.management.MBeanServerConnection;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.access.MBeanProxyFactoryBean;
import org.springframework.jmx.support.MBeanServerConnectionFactoryBean;

@Configuration
public class SharedRemoteConnectionConfiguration {

    @Bean
    public MBeanServerConnectionFactoryBean remoteJmxConnection() {
        MBeanServerConnectionFactoryBean factory =
            new MBeanServerConnectionFactoryBean();

        factory.setServiceUrl(
            "service:jmx:rmi:///jndi/rmi://jmx.example.internal:9999/jmxrmi"
        );

        // Bổ sung environment map và các thiết lập connector
        // theo hệ thống bảo mật đã triển khai.
        return factory;
    }

    @Bean
    public MBeanProxyFactoryBean workerManagementProxy(
            MBeanServerConnection remoteConnection) {
        MBeanProxyFactoryBean proxy = new MBeanProxyFactoryBean();
        proxy.setServer(remoteConnection);
        proxy.setObjectName(
            "demo.service:type=Worker,name=primary"
        );
        proxy.setProxyInterface(WorkerManagementMBean.class);
        return proxy;
    }
}
```

Ở đây `setServer(remoteConnection)` yêu cầu proxy dùng một `MBeanServerConnection` đã được cung cấp. Cần đảm bảo Spring resolve đúng FactoryBean product và không đồng thời thiết lập hai chiến lược kết nối mâu thuẫn trên cùng proxy.

**Quy tắc quan trọng:** lựa chọn A hoặc B theo ownership connector. Không mặc định mỗi `MBeanProxyFactoryBean` sẽ có chung connection nếu mỗi proxy tự cấu hình service URL riêng; và không tạo nhiều connection không cần thiết nếu một connection được quản lý tập trung đã đáp ứng yêu cầu.

## 8. Cấu hình credentials và connector environment

Trong Java JMX, `JMXConnectorFactory.connect` nhận một environment map. Với một số connector sử dụng xác thực username/password, key phổ biến là `JMXConnector.CREDENTIALS`, nhận một `String[]` gồm hai phần tử.

Ví dụ minh họa ở client Java SE:

```java
Map<String, Object> env = new HashMap<>();
env.put(
    JMXConnector.CREDENTIALS,
    new String[]{username, password}
);

JMXConnector connector = JMXConnectorFactory.connect(
    serviceUrl,
    env
);
```

Với Spring, có thể truyền environment map theo API cấu hình connector tương ứng:

```java
Map<String, Object> environment = new HashMap<>();
environment.put(
    JMXConnector.CREDENTIALS,
    new String[]{username, password}
);

// factory.setEnvironmentMap(environment);
```

Ví dụ trên mô tả hình dạng cấu hình; tên setter khả dụng, khả năng tái kết nối và hành vi runtime cần đối chiếu với phiên bản Spring đang dùng.

**Không hard-code credentials thật trong source.** Lấy chúng từ secret manager hoặc configuration được bảo vệ. Tránh ghi raw credential vào log, exception message, MBean attribute hoặc debug dump.

Cũng không nên hiểu rằng chỉ truyền username/password sẽ tự bật TLS. Authentication và bảo vệ đường truyền là các cấu hình độc lập của connector/server và hạ tầng; cần kiểm tra cả hai phía.

## 9. Vòng đời kết nối: Spring bean và network session

Remote proxy có ít nhất ba trạng thái cần quan tâm:

1. **Spring bean/proxy đã được tạo.**
2. **Connector đã thiết lập được session tới remote JMX server.**
3. **Target MBean đã đăng ký và xử lý được operation.**

Các trạng thái không tương đương. Ví dụ server còn đang STARTING, connector có thể hoạt động nhưng ObjectName chưa có. Ngược lại, MBean đã đăng ký nhưng connector có thể đứt vì network.

```text
Spring startup
    -> tạo proxy factory
    -> tạo connector (có thể eager hoặc lazy)
    -> proxy sẵn sàng để caller sử dụng
    -> remote target MBean có/không tồn tại
    -> caller gọi operation/attribute
```

Các phương thức và option của Spring có thể thay đổi **khi nào kết nối/metadata được kiểm tra**, nhưng không loại bỏ khả năng lỗi runtime. Một application startup thành công không có nghĩa remote MBean sẽ luôn reachable.

Khi ứng dụng shutdown, factory/connector do Spring quản lý cần đóng session phù hợp. Không tự tạo `JMXConnector` ngoài container rồi bỏ quên `close()`; điều đó có thể giữ tài nguyên, thread hoặc kết nối không cần thiết.

## 10. Ví dụ server có remote connector an toàn: khái niệm và cấu hình

Để client proxy từ xa làm việc, target JVM phải có:

1. `MBeanServer`.
2. MBean đã đăng ký đúng `ObjectName`.
3. `JMXConnectorServer` đang lắng nghe tại địa chỉ truy cập được.
4. Cơ chế xác thực/bảo vệ đường truyền và network policy phù hợp.

Ví dụ đoạn code đăng ký target MBean (chưa mở remote port):

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "demo.service:type=Worker,name=primary"
);

server.registerMBean(new WorkerManagement(), name);
```

Đoạn này chỉ đăng ký local MBean. Nó **không** tự tạo `JMXConnectorServer` cho remote access.

Nếu triển khai remote JMX qua RMI, cần phối hợp cấu hình `com.sun.management.jmxremote.port`, `com.sun.management.jmxremote.rmi.port`, `java.rmi.server.hostname`, SSL và authentication theo môi trường JDK/hạ tầng. Các giá trị và số cổng không nên copy vô điều kiện vì RMI có thể cần nhiều endpoint và bị ảnh hưởng bởi NAT, container port mapping, firewall.

Ví dụ URL phổ biến:

```text
service:jmx:rmi:///jndi/rmi://host.example.internal:9999/jmxrmi
```

**Không bật remote JMX bằng cách thêm `authenticate=false` và `ssl=false` trên máy dùng chung.** Nếu đang học trong môi trường cá nhân, ưu tiên dùng MBeanServer local hoặc môi trường test cô lập được bảo vệ.

## 11. Trực tiếp dùng JMXConnector trong Java SE

Để hiểu rõ luồng kết nối trước khi dùng Spring proxy, đây là mẫu client Java SE:

```java
import java.util.HashMap;
import java.util.Map;
import javax.management.JMX;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

public final class RemoteClient {
    public static void main(String[] args) throws Exception {
        JMXServiceURL url = new JMXServiceURL(
            "service:jmx:rmi:///jndi/rmi://host.example.internal:9999/jmxrmi"
        );

        Map<String, Object> environment = new HashMap<>();
        // Điền cơ chế xác thực và trust configuration phù hợp.
        // Không nhúng mật khẩu trực tiếp vào source code.

        try (JMXConnector connector =
                JMXConnectorFactory.connect(url, environment)) {

            MBeanServerConnection connection =
                connector.getMBeanServerConnection();

            ObjectName name = new ObjectName(
                "demo.service:type=Worker,name=primary"
            );

            WorkerManagementMBean proxy = JMX.newMBeanProxy(
                connection,
                name,
                WorkerManagementMBean.class
            );

            System.out.println("Active jobs: " + proxy.getActiveJobs());
        }
    }
}
```

Chạy được khi remote server thật tồn tại, có quyền truy cập và cùng hợp đồng management interface. Đây là skeleton tích hợp, không phải mock server tự khởi chạy.

Điểm quan trọng: `try-with-resources` đảm bảo connector được đóng sau khi hoàn tất. Nếu client là Spring application dài hạn, giao nhiệm vụ sở hữu session cho một bean/factory được quản lý lifecycle.

## 12. Spring consumer chỉ nhìn thấy management interface

Khi `MBeanProxyFactoryBean` được cấu hình như trên, một bean client có thể inject interface:

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;

@Service
public class RemoteOperationsDashboard {
    private final WorkerManagementMBean worker;

    public RemoteOperationsDashboard(
            @Qualifier("workerManagementProxy")
            WorkerManagementMBean worker) {
        this.worker = worker;
    }

    public WorkerSnapshot readSnapshot() {
        return new WorkerSnapshot(
            worker.getActiveJobs(),
            worker.getWarningThreshold()
        );
    }

    public record WorkerSnapshot(
        int activeJobs,
        int warningThreshold
    ) {}
}
```

Code này có vẻ là hai getter Java đơn giản, nhưng thực tế là **hai lời gọi JMX remote**. Hai giá trị có thể được chụp ở hai thời điểm khác nhau; không được suy ra chúng tạo một snapshot nguyên tử của server.

Nếu cần nhiều chỉ số nhất quán, hãy thiết kế một attribute snapshot tổng hợp phù hợp với JMX type mapping hoặc một operation trả kết quả thống nhất. Nếu cần throughput cao, thu thập có chu kỳ, caching và giới hạn tần suất, tránh gọi remote JMX liên tục cho từng request nghiệp vụ.

### Khi client và server dùng interface khác phiên bản

Phần lớn lỗi proxy chỉ xuất hiện **khi gọi**, không phải lúc compile. Nếu client có `getActiveJobs()` nhưng server đã đổi tên attribute hoặc kiểu trả về, proxy có thể thất bại. Nên xem management interface như API có versioning và kiểm tra khả năng tương thích bằng `MBeanInfo`.

## 13. Metadata: đừng đoán contract từ code client

Trước khi coi proxy hoạt động, có thể đọc metadata qua raw connection:

```java
MBeanInfo info = connection.getMBeanInfo(objectName);

for (MBeanAttributeInfo attr : info.getAttributes()) {
    System.out.printf(
        "%s type=%s readable=%s writable=%s%n",
        attr.getName(),
        attr.getType(),
        attr.isReadable(),
        attr.isWritable()
    );
}

for (MBeanOperationInfo op : info.getOperations()) {
    System.out.println("operation=" + op.getName());
}
```

Imports:

```java
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
```

Metadata có ích để xác nhận:

- `ActiveJobs` tồn tại và có thể đọc.
- `WarningThreshold` có read/write đúng ý định.
- `pause` và `resume` là operations.
- ObjectName có trỏ đúng loại MBean hay không.
- Một deployment đã thay contract mà client chưa cập nhật hay không.

Không tự động dump **giá trị** của mọi attribute để “debug metadata”, vì có thể làm lộ dữ liệu nhạy cảm.

## 14. Lỗi thường gặp và cách phân biệt

Remote proxy có nhiều lớp lỗi khác nhau:

| Tình huống | Biểu hiện điển hình | Hướng kiểm tra |
|---|---|---|
| URL sai hoặc connector chưa lắng nghe | Lỗi kết nối / `IOException` | Host, port, connector server |
| RMI registry tới được nhưng stub endpoint không tới được | Timeout/kết nối thất bại | RMI hostname, port mapping, NAT/firewall |
| Authentication thất bại | `SecurityException` hoặc lỗi xác thực | Identity, permissions, auth config |
| TLS/truststore không khớp | Handshake/trust failure | Trust material, TLS configuration |
| ObjectName chưa đăng ký | `InstanceNotFoundException` hoặc Spring wrapper | Query server, lifecycle |
| Interface proxy khác MBeanInfo | Attribute/operation invocation error | Metadata, method signature |
| Setter từ chối dữ liệu | Validation exception được JMX/Spring bọc | Domain rule, input |
| Kết nối đứt sau startup | Lỗi I/O khi gọi tiếp | Reconnect strategy, monitoring |
| MBean bị replace khi client đang chạy | Metadata hoặc call thay đổi | Version/registration policy |

**Không gộp mọi lỗi thành “remote service is down”.** Một endpoint reachable nhưng thiếu permission cần giải quyết khác với ObjectName sai, TLS trust lỗi hoặc server chưa start.

### 14.1. Vì sao RMI đôi khi kết nối được cổng đầu nhưng vẫn lỗi?

JMX RMI có thể sử dụng một registry endpoint và một remote object endpoint. Nếu firewall cho phép registry nhưng hostname/port trong stub không truy cập được từ client, kết nối vẫn thất bại. Trong container hoặc NAT, cần cấu hình rõ RMI hostname và port phù hợp, không chỉ “mở cổng 9999” rồi kết luận đường đi đã đủ.

### 14.2. Proxy có thể ném exception nào?

Tùy Spring/JMX layer, một lỗi có thể hiện dưới dạng exception JMX, `IOException`, `MBeanException`, `ReflectionException`, `InvalidAttributeValueException`, `AttributeNotFoundException` hoặc exception Spring JMX access chuyển đổi/bọc. Client cần phân loại theo cause và ý nghĩa, không phụ thuộc tuyệt đối một loại exception cho mọi triển khai.

## 15. Timeout, retry và idempotency

Với remote JMX, latency và sự cố mạng là chuyện bình thường. Cần phân biệt:

**Getter đọc trạng thái:** có thể được phép retry trong một số trường hợp nếu logic chỉ đọc, nhưng retry phải có giới hạn và không tạo bão request khi server đang quá tải.

**Setter hoặc operation thay đổi trạng thái:** retry mù có thể gây tác dụng phụ lặp lại. Ví dụ `rotateKey()`, `restartWorker()`, `clearCache()` hoặc `incrementCounter()` không nhất thiết idempotent.

Giả sử:

```text
Client gửi pause()
Server thực hiện pause()
Response bị mất trên mạng
Client nhận timeout
```

Timeout **không chứng minh** operation chưa được thực hiện. Nếu client tự retry, nó có thể gọi hai lần. Đối với operation quan trọng, hãy thiết kế:

- Trạng thái có thể đọc lại, ví dụ `getLifecycleState()`.
- Request ID hoặc idempotency key nếu hợp đồng có hỗ trợ.
- Audit log phía server.
- Retry với giới hạn và exponential backoff khi phù hợp.
- Hành vi rõ khi timeout: kiểm tra kết quả trước khi gửi lệnh lần nữa.
- Không thực thi operation có tác dụng phụ trong getter chỉ để “xác nhận”.

`MBeanProxyFactoryBean` không tự làm mọi operation trở nên exactly-once.

## 16. Chọn cơ chế reconnect phù hợp

Một kết nối remote có thể mất sau khi Spring context đã start. Tùy phiên bản Spring, `MBeanClientInterceptor` hỗ trợ các tùy chọn như refresh connection on failure, nhưng không nên giả định chúng xử lý mọi tình huống network.

Cần xác định rõ:

1. Ai sở hữu `JMXConnector` hoặc connection factory?
2. Khi connection hỏng, component nào đóng connector cũ?
3. Component nào tạo session mới?
4. Proxy có giữ connection cũ hay có cách refresh?
5. Nếu server restart và đăng ký lại MBean, proxy có thể tiếp tục gọi sau reconnect không?
6. Lúc server chưa sẵn sàng, client sẽ fail fast, trả trạng thái degraded hay giữ retry trong nền?

Nếu dùng một `MBeanServerConnectionFactoryBean` chia sẻ nhiều proxy, một lỗi connection có thể ảnh hưởng tất cả. Ngược lại, tạo connector riêng cho mỗi proxy có thể gây dư session và làm việc quản lý credentials khó hơn. Chọn dựa trên số MBean, độ ổn định endpoint và policy vận hành.

## 17. Tích hợp vào Spring Boot và Spring Framework

Trong Spring Framework thuần, exporter phía server có thể được cấu hình qua:

```java
@Configuration
@EnableMBeanExport
public class ServerJmxConfiguration {
}
```

Bean `@ManagedResource` có thể được xuất ra JMX nếu hạ tầng annotation export đã cấu hình phù hợp. Trong Spring Boot, việc export JMX còn phụ thuộc auto-configuration và `spring.jmx.enabled` ở phiên bản tương ứng.

Nhưng **Spring JMX export không đồng nghĩa remote connector đã được mở**. `spring.jmx.enabled` có thể cho phép export MBean vào local MBeanServer mà không thiết lập remote RMI service URL. Nếu client Spring khác cần truy cập, server vẫn phải được cấu hình remote JMX một cách có bảo mật.

Ở phía client, `MBeanProxyFactoryBean` chỉ cần management interface, ObjectName và connection. Nó không yêu cầu server cũng phải chạy Spring; server có thể là bất kỳ JVM cung cấp MBean hợp lệ qua connector tương thích.

## 18. Lưu ý security cho remote JMX proxy

Remote JMX có thể cho phép đọc dữ liệu runtime và gọi những operation có tác dụng phụ. Một endpoint quản trị không được bảo vệ có thể nguy hiểm hơn một endpoint metrics read-only.

Các nguyên tắc cần áp dụng:

1. **Giới hạn mạng:** chỉ cho phép máy/segment quản trị được truy cập; tránh public Internet.
2. **Xác thực:** dùng cơ chế authentication được hỗ trợ và quản lý secret an toàn.
3. **Mã hóa:** thiết lập TLS hoặc kênh bảo vệ phù hợp từ client tới server.
4. **Phân quyền:** identity monitoring thường chỉ cần đọc; operation thay đổi trạng thái cần hạn chế chặt hơn.
5. **Không xuất secret:** MBean getter không trả password, token, private key hoặc raw configuration.
6. **Audit:** ghi nhận thao tác quản trị quan trọng ở server.
7. **Không log credentials:** kiểm tra logging của client, connector, proxy và exception handling.
8. **Bảo vệ key material:** truststore, keystore và credential provider có quyền file phù hợp.
9. **Tránh remote operation ngoài ý muốn:** không mở rộng management interface chỉ vì “debug nhanh”.
10. **Cân nhắc mạng và RMI topology:** registry/stub endpoint phải được bảo vệ nhất quán.

Đừng dùng `authenticate=false` hoặc `ssl=false` như đáp án mặc định cho lab trong môi trường dùng chung. Nếu chưa có một remote endpoint được bảo vệ, có thể học mapping/proxy với MBeanServer local trước, sau đó triển khai kết nối remote trong môi trường test có kiểm soát.

## 19. Trường hợp client dùng MXBean

Một MXBean có type mapping sang Open Types. Raw connection có thể trả `CompositeData` hoặc `TabularData`, trong khi typed MXBean proxy của JDK có thể ánh xạ về kiểu Java thích hợp khi hợp đồng hỗ trợ.

```java
StatusMXBean proxy = JMX.newMXBeanProxy(
    connection,
    objectName,
    StatusMXBean.class
);
```

Trong ví dụ này `StatusMXBean` phải được định nghĩa và target đăng ký đúng là MXBean. Không lấy một `CompositeData` bất kỳ rồi ép trực tiếp thành DTO Java.

Khi sử dụng `MBeanProxyFactoryBean` cho MXBean, phải đối chiếu Spring version và khả năng MXBean mapping tương ứng. Nếu cần dựa chắc vào MXBean semantics của JDK, `JMX.newMXBeanProxy` là lựa chọn rõ ràng.

## 20. Một mẫu thiết kế thực tế: monitoring facade

Thay vì cho nhiều service nghiệp vụ gọi remote proxy liên tục, nên tạo một component gom dữ liệu:

```text
Remote Worker MBean
         |
Spring JMX proxy
         |
RemoteWorkerMonitor
         |
cached status / bounded polling
         |
dashboard / health endpoint / alert pipeline
```

Một mẫu Java đơn giản:

```java
@Service
public class RemoteWorkerMonitor {
    private final WorkerManagementMBean proxy;

    public RemoteWorkerMonitor(
            @Qualifier("workerManagementProxy")
            WorkerManagementMBean proxy) {
        this.proxy = proxy;
    }

    public WorkerStatus sample() {
        return new WorkerStatus(
            proxy.getActiveJobs(),
            proxy.getWarningThreshold(),
            System.currentTimeMillis()
        );
    }

    public record WorkerStatus(
        int activeJobs,
        int threshold,
        long sampledAt
    ) {}
}
```

Trong production, `sample()` nên được gọi theo chu kỳ có giới hạn hoặc sau thao tác người dùng, không tùy tiện ở mỗi request. Cần lưu trạng thái `UNKNOWN` hoặc `STALE` khi không lấy được dữ liệu, thay vì tự coi lỗi kết nối là số 0.

Ngoài ra, hai getter JMX có thể phản ánh hai thời điểm khác nhau. Nếu cần snapshot nguyên tử, thiết kế attribute tổng hợp hoặc operation riêng trên server.

## 21. Bài tập thực hành

### Bài 1 — Raw connection và proxy

Dùng một JMX endpoint test có authentication. Kết nối qua `JMXConnector`, đọc `ActiveJobs` bằng `getAttribute`, rồi đọc bằng `JMX.newMBeanProxy`. So sánh kết quả và log thời gian thực hiện.

### Bài 2 — Cấu hình MBeanProxyFactoryBean

Tạo Spring context có `MBeanProxyFactoryBean` với `serviceUrl`, `objectName`, `proxyInterface`. Inject proxy vào một bean consumer và đọc `getActiveJobs()`.

### Bài 3 — Connection factory chia sẻ

Định nghĩa một `MBeanServerConnectionFactoryBean` dùng chung cho hai proxy tương ứng hai MBean khác nhau trên cùng server. So sánh với cách mỗi proxy tự quản lý kết nối và mô tả ownership/lifecycle cần thiết.

### Bài 4 — MBean chưa đăng ký

Giữ connector vẫn hoạt động nhưng đổi ObjectName thành một tên không tồn tại. Gọi proxy, quan sát exception. Kiểm tra `queryNames` và `getMBeanInfo` để nhận diện lỗi.

### Bài 5 — Mạng lỗi giữa operation

Trong môi trường test, giả lập response timeout khi gọi một operation thay đổi trạng thái. Giải thích vì sao không được tự động retry nếu operation không idempotent. Thiết kế readback state hoặc idempotency key.

### Bài 6 — Cấu hình bảo mật

Lập bảng các thành phần cần bảo vệ: service URL, authentication credentials, truststore, firewall, audit log và management interface. Mô tả biện pháp giảm nguy cơ dữ liệu và operation nhạy cảm.

### Bài 7 — MXBean mapping

Tạo MXBean trả một composite status, đọc raw `CompositeData` và dùng `JMX.newMXBeanProxy` để quan sát mapping typed. So sánh với Standard MBean proxy.

## 22. Câu hỏi tự kiểm tra

1. `MBeanProxyFactoryBean` tạo ra thành phần gì?
2. Vì sao proxy không tự đăng ký target MBean?
3. `MBeanServerConnection` local và remote giống nhau ở giao diện nào, khác nhau ở rủi ro gì?
4. `ObjectName` có vai trò gì đối với lời gọi qua proxy?
5. Khi dùng shared connection, thành phần nào chịu trách nhiệm đóng connector?
6. Vì sao một lời gọi Java getter trên proxy có thể gây network I/O?
7. Sự khác nhau giữa lỗi `InstanceNotFoundException` và lỗi connection refused là gì?
8. Timeout sau `pause()` có chứng minh server chưa thực hiện operation không?
9. `spring.jmx.enabled` có tự mở remote connector được bảo vệ không?
10. Những biện pháp nào cần có trước khi triển khai remote JMX trên môi trường dùng chung?

## 23. Ghi nhớ

**`MBeanProxyFactoryBean` là cơ chế client-side của Spring Framework để gọi một JMX MBean thông qua Java management interface.** Với remote connector, lời gọi trên proxy đi qua `MBeanServerConnection`, transport và `MBeanServer` trên JVM đích; vì vậy phải xử lý network latency, lifecycle, authentication, TLS, API compatibility và lỗi giữa chừng.

Hãy phân biệt rõ **export target**, **mở connector server**, **tạo connector client** và **tạo proxy**. Dùng ObjectName ổn định, kiểm tra `MBeanInfo`, quản lý kết nối tập trung khi phù hợp và tuyệt đối không coi một operation remote bị timeout là chắc chắn chưa chạy.
