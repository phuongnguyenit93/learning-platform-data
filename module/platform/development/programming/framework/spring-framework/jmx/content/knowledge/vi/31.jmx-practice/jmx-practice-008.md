# Tạo proxy local để đọc và gọi MBean trong Spring Framework JMX

## Mục tiêu thực hành

Sau bài thực hành này, bạn có thể:

- Hiểu **local JMX proxy** giúp Java code gọi MBean qua một Java interface thay vì tự viết \`MBeanServer.getAttribute(...)\` và \`invoke(...)\` cho từng lời gọi.
- Phân biệt **MBean được export vào MBeanServer** và **proxy được tạo ở phía client** để gọi MBean đó.
- Sử dụng Spring Framework \`MBeanProxyFactoryBean\` với \`ObjectName\`, \`MBeanServer\` và management interface rõ ràng.
- Đọc một JMX attribute bằng một Java getter, gọi JMX operation bằng Java method và hiểu cách mapping từ method sang JMX.
- Cấu hình bằng Java \`@Configuration\` và sử dụng proxy như một Spring bean qua dependency injection.
- Kiểm chứng kết quả bằng JUnit 5, so sánh với \`MBeanServer\` API và xử lý \`InstanceNotFoundException\`, sai ObjectName, sai interface hoặc server không đúng.
- Biết phạm vi local proxy và khi nào cần một JMX client từ xa sử dụng \`MBeanServerConnection\`.

## 1. Bài toán

Giả sử ứng dụng có MBean quản lý một queue, với các khả năng:

- Đọc số lượng công việc đang chờ: \`PendingJobs\`.
- Kiểm tra queue có tạm dừng không: \`Paused\`.
- Gọi operation \`pauseProcessing()\`.
- Gọi operation \`resumeProcessing()\`.

Cách gọi JMX API trực tiếp:

\`\`\`java
ObjectName name = new ObjectName(
    "learning.jmx:type=Queue,name=Primary"
);

long pending = (Long) server.getAttribute(
    name,
    "PendingJobs"
);

server.invoke(
    name,
    "pauseProcessing",
    new Object[0],
    new String[0]
);
\`\`\`

Điểm bất tiện là client phải lặp lại ObjectName, tên attribute và operation, kiểu dữ liệu và signatures. Khi có nhiều operations, code trở nên dài và dễ sai tên.

Một local proxy cho phép viết:

\`\`\`java
long pending = queueJmxClient.getPendingJobs();
queueJmxClient.pauseProcessing();
\`\`\`

Proxy chuyển lời gọi interface thành tương tác với MBeanServer.

### Sơ đồ

\`\`\`text
Business/JMX consumer trong cùng JVM
            |
            | Java interface call
            v
     Local MBean proxy
            |
            | getAttribute / invoke
            v
        MBeanServer
            |
            | ObjectName
            v
       QueueMonitor MBean
\`\`\`

**Quan trọng:** Proxy không phải bản sao trạng thái MBean. Nó là một adapter cho những lời gọi đi tới resource đang được đăng ký trên MBeanServer.

## 2. Hai hướng tương tác JMX

Có hai hướng hoạt động độc lập:

**Hướng export:** Spring bean → MBeanExporter → MBeanServer.

**Hướng client:** Java interface → MBeanProxyFactoryBean → MBeanServer → MBean.

Cùng một ứng dụng có thể dùng cả hai hướng:

\`\`\`text
Spring ApplicationContext
    |
    +-- QueueMonitor bean
    |       |
    |       v
    |   MBeanExporter
    |       |
    |       v
    |   MBeanServer
    |       ^
    |       |
    |   MBean proxy
    |       ^
    |       |
    +-- QueuePollingService
\`\`\`

Vì là **local proxy**, MBean proxy trong bài được cấu hình với một \`MBeanServer\` khả dụng bên trong cùng JVM. Việc tạo proxy không tự mở remote JMX endpoint.

## 3. Phụ thuộc và môi trường

Ví dụ dùng:

- Java 17+.
- Spring Framework 6.x hoặc phiên bản tương thích với dự án.
- Module \`spring-context\` có các thành phần Spring JMX và cấu hình bean.
- JUnit Jupiter nếu viết integration tests.
- Java module \`java.management\` chứa JMX API.

Ví dụ Maven cho Spring Context, quản lý version thông qua BOM hoặc dependency management của dự án:

\`\`\`xml
<dependency>
    <groupId>org.springframework</groupId>
    <artifactId>spring-context</artifactId>
</dependency>

<dependency>
    <groupId>org.junit.jupiter</groupId>
    <artifactId>junit-jupiter</artifactId>
    <scope>test</scope>
</dependency>
\`\`\`

Nếu dự án không dùng BOM, cần khai báo version phù hợp ở dependency management. Không nên trộn phiên bản Spring modules tùy ý.

## 4. Định nghĩa MBean quản lý queue

Ta tạo Standard MBean để ví dụ tập trung vào proxy.

### 4.1. Management interface phía MBean

\`\`\`java
package example.jmx;

public interface QueueMonitorMBean {

    long getPendingJobs();

    boolean isPaused();

    void pauseProcessing();

    void resumeProcessing();
}
\`\`\`

Tên \`QueueMonitorMBean\` theo Standard MBean convention vì class implementation sẽ có tên \`QueueMonitor\`.

### 4.2. MBean implementation

\`\`\`java
package example.jmx;

import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;

public class QueueMonitor implements QueueMonitorMBean {

    private final AtomicLong pendingJobs = new AtomicLong(5);
    private final AtomicBoolean paused = new AtomicBoolean();

    @Override
    public long getPendingJobs() {
        return pendingJobs.get();
    }

    @Override
    public boolean isPaused() {
        return paused.get();
    }

    @Override
    public void pauseProcessing() {
        paused.set(true);
    }

    @Override
    public void resumeProcessing() {
        paused.set(false);
    }
}
\`\`\`

Đây là Standard MBean: management interface quy định công bố attribute và operation.

Tương ứng:

| Java method | JMX contract |
|---|---|
| \`getPendingJobs()\` | Attribute \`PendingJobs\`, type \`long\`, readable |
| \`isPaused()\` | Attribute \`Paused\`, type \`boolean\`, readable |
| \`pauseProcessing()\` | Operation \`pauseProcessing\` |
| \`resumeProcessing()\` | Operation \`resumeProcessing\` |

Không dùng bean class runtime name hoặc proxy name để tạo ObjectName; ta sẽ chỉ định một tên quản trị cố định.

## 5. Management interface phía client

Local proxy cần một interface mà phía client muốn gọi.

\`\`\`java
package example.jmx;

public interface QueueJmxClient {

    long getPendingJobs();

    boolean isPaused();

    void pauseProcessing();

    void resumeProcessing();
}
\`\`\`

Interface này có cùng management method signatures với MBean contract.

Vì sao có thể tách \`QueueJmxClient\` khỏi \`QueueMonitorMBean\`?

- Tránh để consumer phụ thuộc vào implementation của server.
- Cho phép giữ một interface client có chủ đích.
- Giúp minh họa proxy là adapter độc lập, không phải instance của \`QueueMonitor\`.

Trong ví dụ đơn giản, client cũng có thể dùng chính \`QueueMonitorMBean\` làm proxy interface. Chọn cách nào tùy mức độ tách biệt cần thiết, miễn các method được proxy ánh xạ chính xác tới JMX attributes và operations.

## 6. Tạo MBeanServer local trong Spring

Để integration test tránh xung đột với platform MBeanServer chung của JVM, ta dùng server riêng:

\`\`\`java
package example.jmx;

import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class JmxServerConfiguration {

    @Bean
    public MBeanServer lessonMBeanServer() {
        return MBeanServerFactory.createMBeanServer(
            "learning.local"
        );
    }
}
\`\`\`

\`MBeanServerFactory.createMBeanServer(...)\` tạo một registry JMX riêng. Cần bảo đảm exporter và proxy đều được inject **đúng instance server này**.

Nếu bạn dùng platform server, thay bằng:

\`\`\`java
@Bean
public MBeanServer lessonMBeanServer() {
    return ManagementFactory.getPlatformMBeanServer();
}
\`\`\`

Với server tạo qua factory, cần có chính sách giải phóng sau khi application/test không còn sử dụng; không release platform MBeanServer hay server dùng chung không thuộc quyền của bạn.

## 7. Export QueueMonitor thành MBean

Ta cấu hình \`MBeanExporter\` và ObjectName tường minh:

\`\`\`java
package example.jmx;

import java.util.Map;
import javax.management.MBeanServer;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class QueueExportConfiguration {

    public static final String QUEUE_OBJECT_NAME =
        "learning.jmx:type=Queue,name=Primary";

    @Bean
    public QueueMonitor queueMonitor() {
        return new QueueMonitor();
    }

    @Bean
    public MBeanExporter queueMBeanExporter(
            @Qualifier("lessonMBeanServer") MBeanServer server,
            QueueMonitor queueMonitor) {

        MBeanExporter exporter = new MBeanExporter();

        exporter.setServer(server);

        exporter.setBeans(Map.of(
            QUEUE_OBJECT_NAME,
            queueMonitor
        ));

        return exporter;
    }
}
\`\`\`

Tác dụng:

1. Tạo \`QueueMonitor\`.
2. Tạo exporter Spring-managed.
3. Chọn custom MBeanServer.
4. Đăng ký MBean dưới ObjectName cố định.
5. Quản lý unexport khi exporter đóng.

Nếu có nhiều MBeanServer beans, dùng \`@Qualifier\` để đảm bảo không inject nhầm server.

**Lưu ý:** Đừng bật một exporter khác cũng đăng ký QueueMonitor cùng ObjectName vào cùng server nếu không có ownership rõ.

## 8. Tạo proxy local bằng MBeanProxyFactoryBean

Spring Framework cung cấp \`org.springframework.jmx.access.MBeanProxyFactoryBean\` để tạo proxy implement một management interface và định tuyến lời gọi tới MBean.

Ví dụ:

\`\`\`java
package example.jmx;

import javax.management.MBeanServer;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.access.MBeanProxyFactoryBean;

@Configuration
public class QueueProxyConfiguration {

    @Bean(name = "queueJmxClient")
    public MBeanProxyFactoryBean queueJmxClientFactory(
            @Qualifier("lessonMBeanServer") MBeanServer server) {

        MBeanProxyFactoryBean factory =
                new MBeanProxyFactoryBean();

        factory.setServer(server);

        factory.setObjectName(
            QueueExportConfiguration.QUEUE_OBJECT_NAME
        );

        factory.setProxyInterface(QueueJmxClient.class);

        return factory;
    }
}
\`\`\`

Ở đây \`MBeanProxyFactoryBean\` là **FactoryBean**. Khi bean tên \`queueJmxClient\` được inject dưới kiểu \`QueueJmxClient\`, Spring cung cấp proxy object do factory tạo.

Các thành phần quan trọng:

| Property | Giá trị | Mục đích |
|---|---|---|
| \`server\` | MBeanServer local | Nơi chứa MBean được gọi |
| \`objectName\` | \`learning.jmx:type=Queue,name=Primary\` | MBean đích |
| \`proxyInterface\` | \`QueueJmxClient.class\` | Contract mà proxy triển khai |

Không nhầm \`setServer\` với hostname/port. Bài local proxy dùng trực tiếp một MBeanServer Java, không phải URL remote.

## 9. Spring configuration tổng hợp

Có thể gom các cấu hình trong một context:

\`\`\`java
package example.jmx;

import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;

@Configuration
@Import({
    JmxServerConfiguration.class,
    QueueExportConfiguration.class,
    QueueProxyConfiguration.class
})
public class LocalJmxApplicationConfiguration {
}
\`\`\`

Application:

\`\`\`java
package example.jmx;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class LocalJmxProxyDemo {

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(
                    LocalJmxApplicationConfiguration.class)) {

            QueueJmxClient client =
                context.getBean(QueueJmxClient.class);

            long pending = client.getPendingJobs();

            System.out.println(
                "Pending jobs = " + pending
            );

            System.out.println(
                "Initially paused = " + client.isPaused()
            );

            client.pauseProcessing();

            System.out.println(
                "After pause = " + client.isPaused()
            );

            client.resumeProcessing();

            System.out.println(
                "After resume = " + client.isPaused()
            );
        }
    }
}
\`\`\`

Kết quả kỳ vọng:

\`\`\`text
Pending jobs = 5
Initially paused = false
After pause = true
After resume = false
\`\`\`

Đây là lời gọi Java qua proxy đi đến JMX MBean, không phải lời gọi trực tiếp tới QueueMonitor. Proxy sẽ dùng MBeanServer và ObjectName đã cấu hình để ánh xạ methods.

## 10. Đối chiếu proxy với MBeanServer API

Để hiểu rõ cơ chế, hãy so sánh:

**Cách JMX API trực tiếp:**

\`\`\`java
MBeanServer server =
    context.getBean("lessonMBeanServer", MBeanServer.class);

ObjectName name = new ObjectName(
    "learning.jmx:type=Queue,name=Primary"
);

long pending =
    (Long) server.getAttribute(name, "PendingJobs");

server.invoke(
    name,
    "pauseProcessing",
    new Object[0],
    new String[0]
);
\`\`\`

**Cách proxy:**

\`\`\`java
QueueJmxClient proxy =
    context.getBean(QueueJmxClient.class);

long pending = proxy.getPendingJobs();
proxy.pauseProcessing();
\`\`\`

Proxy giúp code client dễ đọc và tránh lặp tên chuỗi. Nhưng JMX operations vẫn phải tồn tại và đúng signature trong MBeanServer.

Proxy không tự sửa một ObjectName sai hoặc một MBean chưa đăng ký.

## 11. Vì sao proxy interface phải khớp management contract?

Giả sử client khai báo:

\`\`\`java
public interface QueueJmxClient {
    int getPendingJobs();
}
\`\`\`

Trong khi MBean công bố \`PendingJobs\` type \`long\`.

Dù tên attribute giống nhau, Java return type có thể không tương thích với giá trị mà JMX trả về, và proxy invocation có thể lỗi.

Tương tự:

\`\`\`java
void pauseProcessing(boolean force);
\`\`\`

không tương đương JMX operation \`pauseProcessing()\` không có tham số.

Những yếu tố cần khớp:

1. Tên attribute/operation.
2. Java return type.
3. Parameter types và order.
4. Primitive vs wrapper semantics.
5. Read-only/writable behavior.
6. Contract và các exceptions mà client có thể nhận.

Không dùng một interface được đoán từ source code khi MBean thực tế đã được export với schema khác. Hãy xem \`MBeanInfo\` trước khi quyết định proxy interface.

## 12. Kiểm chứng metadata với MBeanInfo

Sử dụng \`MBeanServer.getMBeanInfo\`:

\`\`\`java
MBeanServer server =
    context.getBean("lessonMBeanServer", MBeanServer.class);

ObjectName name = new ObjectName(
    QueueExportConfiguration.QUEUE_OBJECT_NAME
);

MBeanInfo info = server.getMBeanInfo(name);

for (MBeanAttributeInfo attribute : info.getAttributes()) {
    System.out.printf(
        "Attribute: %s, type=%s%n",
        attribute.getName(),
        attribute.getType()
    );
}

for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.printf(
        "Operation: %s%n",
        operation.getName()
    );
}
\`\`\`

Kỳ vọng:

\`\`\`text
Attribute: PendingJobs, type=long
Attribute: Paused, type=boolean
Operation: pauseProcessing
Operation: resumeProcessing
\`\`\`

Thứ tự các dòng metadata không nhất thiết cố định; test nên so theo tên/signature, không so theo vị trí trong mảng.

## 13. Integration test JUnit 5

Một bài test kiểm tra toàn bộ đường local proxy:

\`\`\`java
package example.jmx;

import static org.junit.jupiter.api.Assertions.*;

import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

class LocalJmxProxyTest {

    @Test
    void readsAttributesAndInvokesOperations() throws Exception {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(
                    LocalJmxApplicationConfiguration.class)) {

            QueueJmxClient client =
                context.getBean(QueueJmxClient.class);

            MBeanServer server =
                context.getBean(
                    "lessonMBeanServer",
                    MBeanServer.class
                );

            ObjectName name = new ObjectName(
                "learning.jmx:type=Queue,name=Primary"
            );

            assertTrue(server.isRegistered(name));
            assertEquals(5L, client.getPendingJobs());
            assertFalse(client.isPaused());

            client.pauseProcessing();
            assertTrue(client.isPaused());
            assertEquals(
                true,
                server.getAttribute(name, "Paused")
            );

            client.resumeProcessing();
            assertFalse(client.isPaused());
            assertEquals(
                false,
                server.getAttribute(name, "Paused")
            );
        }
    }
}
\`\`\`

Test kiểm tra:

- Context tạo được MBean và proxy.
- MBean đăng ký dưới đúng ObjectName.
- Proxy đọc attribute thành công.
- Proxy gọi operation thay đổi state.
- JMX API trực tiếp và proxy nhìn cùng một state.

Với các thao tác có tác dụng phụ, chỉ test trên test fixture hoặc môi trường kiểm soát.

## 14. Test phân biệt đúng MBeanServer

Nếu có hai MBeanServers:

\`\`\`java
MBeanServer first =
    MBeanServerFactory.createMBeanServer("first");

MBeanServer second =
    MBeanServerFactory.createMBeanServer("second");
\`\`\`

Và MBean chỉ được đăng ký vào \`first\`, thì một proxy cấu hình với \`second\` không thể truy cập MBean bằng cùng ObjectName nếu không có registration riêng.

Sai lầm thường gặp:

\`\`\`java
proxyFactory.setServer(
    ManagementFactory.getPlatformMBeanServer()
);
\`\`\`

khi exporter dùng custom MBeanServer khác.

Khi gặp lỗi, đối chiếu:

\`\`\`java
first.isRegistered(name);
second.isRegistered(name);
\`\`\`

ObjectName chỉ có ý nghĩa trong registry đang được client sử dụng. Đừng đổi ObjectName ngẫu nhiên trước khi xác định server identity.

## 15. Vòng đời: proxy phụ thuộc registration

Một proxy local có thể tồn tại dưới dạng Spring bean, nhưng lời gọi sẽ thất bại nếu MBean target bị unregister.

Ví dụ:

\`\`\`text
Context start
   -> MBeanExporter registers MBean
   -> MBean proxy created
   -> proxy methods work
Context shutdown
   -> MBeanExporter unregisters MBean
   -> proxy can no longer access it
\`\`\`

Không nên giữ proxy trong static singleton bên ngoài lifecycle của ApplicationContext nếu MBean target có thể bị unregister/recreated.

Nếu dùng MBeanServer tạo qua factory, ứng dụng/test cần có chính sách release khi không còn consumer. Việc exporter unregister MBean không tự đồng nghĩa MBeanServer bị hủy.

### Vấn đề startup order

Nếu proxy được kiểm tra quá sớm trước khi exporter đăng ký MBean, context initialization có thể gặp lỗi tùy cấu hình và hành vi kiểm tra của proxy factory.

Một cách tổ chức dễ dự đoán là tạo exporter/managed resource trước, sau đó sử dụng proxy khi context đã refresh thành công. Khi quản lý nhiều contexts, cần thiết kế thứ tự khởi tạo hoặc dependency giữa các thành phần.

## 16. Những lỗi thường gặp

| Lỗi | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| \`InstanceNotFoundException\` | ObjectName không có trong server được chọn | \`isRegistered\`, server identity |
| Proxy bean không inject được | Sai bean name, interface hoặc FactoryBean wiring | \`getBean(QueueJmxClient.class)\`, configuration |
| \`AttributeNotFoundException\` | Getter client không khớp JMX attribute | \`getMBeanInfo\` |
| \`ReflectionException\` hoặc operation mismatch | Method name/signature khác | Metadata operation signatures |
| \`ClassCastException\` | Getter Java return type không khớp JMX value | \`MBeanAttributeInfo.getType()\` |
| Startup lỗi duplicate ObjectName | Có hai exporters cùng đăng ký một tên | Ownership và RegistrationPolicy |
| Proxy đọc giá trị cũ | Client đang gọi MBean khác/server khác hoặc state caching ở target | ObjectName, server và resource identity |
| Gọi operation nhưng state không thay đổi | Proxy gọi nhầm target hoặc logic method không cập nhật | \`getAttribute\`, business logic |
| MBean đã unregister | Context đóng hoặc exporter lifecycle thay đổi | Kiểm tra registration sau close |
| Remote client không truy cập được | Local proxy không tự tạo remote connector | Dùng JMXConnector và security thích hợp |
| Method có @Transactional không được áp dụng | JMX invocation bypass Spring proxy hoặc self-invocation | Kiểm tra management facade/service call path |

## 17. Proxy local và Spring AOP proxy không phải cùng một khái niệm

Có hai loại proxy thường được nhắc trong dự án Spring:

**Spring AOP proxy:**

\`\`\`text
Caller -> AOP proxy -> advice -> target service
\`\`\`

Được dùng cho transactions, security, logging, caching và các cross-cutting concerns.

**JMX local proxy:**

\`\`\`text
Caller -> MBean proxy -> MBeanServer -> MBean
\`\`\`

Được dùng để biến lời gọi Java interface thành JMX attribute/operation access.

Cả hai có thể tồn tại đồng thời. Một MBean facade có thể gọi Spring service proxy bên trong. Đừng giả định AOP proxy tự động là JMX proxy hoặc ngược lại.

Nếu method-level security áp dụng ở service, hãy bảo đảm đường gọi qua JMX cuối cùng đi qua service proxy đúng, không đăng ký target thô gây bypass advice.

## 18. Local proxy khác remote JMX client

Local proxy trong bài dùng một \`MBeanServer\` cùng JVM:

\`\`\`java
factory.setServer(localMBeanServer);
\`\`\`

Remote JMX client cần connector:

\`\`\`java
JMXServiceURL url = new JMXServiceURL(
    "service:jmx:rmi:///jndi/rmi://example-host:9010/jmxrmi"
);

JMXConnector connector =
    JMXConnectorFactory.connect(url, environment);

MBeanServerConnection connection =
    connector.getMBeanServerConnection();
\`\`\`

Không dùng ví dụ này như một cấu hình remote không bảo vệ. Trong production, connector cần authentication, TLS, network isolation và least privilege.

Nếu muốn Spring client proxy qua remote connection, có thể dùng các thành phần Spring JMX connector/client tương ứng như \`MBeanClientInterceptor\` với \`MBeanServerConnection\` tùy phiên bản và yêu cầu. Bài này tập trung vào local proxy bằng \`MBeanProxyFactoryBean\`.

## 19. Khi nào nên dùng proxy local?

Proxy local phù hợp khi:

- Java component trong cùng JVM muốn tiêu thụ MBean contract.
- Muốn thử nghiệm contract của MBean qua Java interface.
- Muốn tránh lặp các chuỗi \`ObjectName\`, attribute name và operation signature.
- Muốn giữ consumer code không phụ thuộc trực tiếp vào implementation class của MBean.
- Dự án đã sử dụng Spring application context và quản lý proxy như bean.

Cân nhắc dùng MBeanServer API trực tiếp khi:

- Cần khám phá MBeans động bằng \`queryNames\`.
- Cần inspect \`MBeanInfo\` và thao tác metadata chi tiết.
- Không có interface ổn định.
- Cần xử lý nhiều MBeans với ObjectNames thay đổi liên tục.

Nếu logic chỉ cần gọi một service trong cùng JVM, **không nhất thiết dùng JMX proxy**. Dependency injection trực tiếp đơn giản và ít overhead hơn; proxy hữu ích khi muốn client tương tác qua chính management boundary hoặc cần compatibility với contract JMX.

## 20. Hiệu năng và độ ổn định

Mỗi proxy call vẫn đi qua JMX infrastructure. Getter có thể thực hiện code nặng, giữ lock hoặc đọc dữ liệu từ database.

Các nguyên tắc:

- Chỉ đọc attributes cần thiết.
- Không poll quá thường xuyên.
- Tránh getter có I/O hoặc tính toán đắt.
- Không gọi operations có tác dụng phụ từ background task không giới hạn.
- Dùng timeout/backoff thích hợp khi đi qua remote connector.
- Không giả định local proxy là access trực tiếp vào Java field.
- Kiểm thử state và lifecycle khi target có thể được unregister.

JMX proxy cải thiện interface của client, không tự biến operation nặng thành nhẹ.

## 21. Bài tập thực hành

### Bài 1 — Đọc attribute

Tạo \`QueueJmxClient\` với \`getPendingJobs()\`. Export QueueMonitor và dùng proxy đọc giá trị 5. So sánh với \`MBeanServer.getAttribute\`.

### Bài 2 — Gọi operation

Thêm \`pauseProcessing()\` và \`resumeProcessing()\`. Dùng proxy gọi từng operation rồi đọc \`isPaused()\` để chứng minh state thay đổi.

### Bài 3 — Thử sai interface

Đổi \`getPendingJobs()\` trong client interface từ \`long\` thành \`int\`. Chạy integration test, ghi nhận lỗi hoặc hành vi type mismatch. Dùng \`MBeanInfo\` giải thích.

### Bài 4 — Thử sai server

Tạo hai MBeanServers, export QueueMonitor vào server A nhưng tạo proxy dùng server B. Xác định vì sao proxy không truy cập được MBean.

### Bài 5 — Test lifecycle

Tạo context, gọi proxy thành công, đóng context, kiểm tra MBean không còn đăng ký. Giải thích vì sao không nên giữ proxy sau khi MBean target bị unregister.

## 22. Checklist trước khi dùng MBeanProxyFactoryBean

1. MBean đã được đăng ký vào MBeanServer chưa?
2. ObjectName trên proxy có khớp chính xác không?
3. Proxy và exporter có dùng cùng MBeanServer không?
4. Proxy interface có khớp tên methods không?
5. Return types và parameter signatures có khớp không?
6. Attribute getter có readable không?
7. Operation có được expose và cho phép gọi không?
8. Có duplicate exporters hoặc ObjectName collision không?
9. Có test \`MBeanInfo\` và \`getAttribute\` trực tiếp không?
10. Có test proxy invocation và state thực tế không?
11. Có lifecycle cleanup cho exporter/server không?
12. Proxy có được dùng trong scope mà MBean còn tồn tại không?
13. Nếu phải dùng remote, có cấu hình connector/auth/TLS riêng không?

## 23. Ghi nhớ cốt lõi

- **MBeanProxyFactoryBean** tạo một Java interface proxy để gọi JMX MBean bằng các method quen thuộc.
- Proxy không phải MBean mới và không tự tạo remote endpoint.
- Client interface là contract, phải khớp JMX attribute/operation names và types.
- \`server\` và \`objectName\` chỉ định chính xác nơi và đối tượng proxy gọi.
- Local JMX proxy khác Spring AOP proxy; mỗi loại giải quyết một nhiệm vụ.
- Dùng \`MBeanInfo\` và integration test để xác nhận contract, không suy đoán từ Java code.
- Cần quản lý lifecycle; một proxy không thể tiếp tục gọi target sau khi MBean đã unregistered.

## Tài liệu tham khảo

- Spring Framework JMX Reference: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework API — MBeanProxyFactoryBean: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/access/MBeanProxyFactoryBean.html
- Spring Framework API — MBeanClientInterceptor: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/access/MBeanClientInterceptor.html
- Spring Framework API — MBeanExporter: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Java SE 21 API — MBeanServer: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
- Java SE 21 API — MBeanServerConnection: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html
