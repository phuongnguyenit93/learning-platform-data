# Kiểm thử proxy local qua MBeanServerConnection trong Spring Framework JMX

## 1. Mục tiêu và tình huống

Spring Framework cung cấp cơ chế JMX proxy để code Java thao tác với MBean qua một giao diện quen thuộc. Thay vì tự gọi `getAttribute`, `setAttribute` và `invoke` ở mọi nơi, một bean client có thể gọi `monitor.getActiveJobs()` hoặc `monitor.resetCounters()`. Ở phía sau, `MBeanProxyFactoryBean` sử dụng `MBeanClientInterceptor` và `MBeanServerConnection` để chuyển lời gọi thành thao tác JMX.

Tuy nhiên, test chỉ gọi trực tiếp Java target rồi assert giá trị là **chưa đủ**. Nó không chứng minh MBean đã đăng ký, proxy trỏ đúng server và ObjectName, tên attribute/operation đúng, hay Spring client interceptor thực sự chuyển lời gọi qua JMX.

Bài học này hướng dẫn xây dựng integration test có phạm vi rõ:

- Tạo MBeanServer cô lập hoặc sử dụng server được inject tường minh.
- Đăng ký một Standard MBean hoặc Spring-managed bean qua `MBeanExporter`.
- Cấu hình local proxy bằng `MBeanProxyFactoryBean`.
- Dùng `MBeanServerConnection` kiểm tra registration và metadata.
- So sánh lời gọi qua Java proxy với `getAttribute`, `setAttribute`, `invoke` qua JMX.
- Kiểm tra read-only attribute, operation signature, missing ObjectName, lỗi thực thi.
- Đảm bảo test cleanup để không gây collision khi chạy lặp hoặc song song.

## 2. Đường đi cần kiểm thử

```text
Spring test / client
       |
       v
WorkerControl proxy (Java interface)
       |
       v
MBeanProxyFactoryBean
       |
       v
MBeanClientInterceptor
       |
       v
MBeanServerConnection
       |
       v
MBeanServer
       |
       v
Registered WorkerControl MBean
       |
       v
WorkerControl target
```

Để khẳng định local proxy thật sự hoạt động, test nên quan sát kết quả tại **JMX boundary**, không chỉ tại target.

### 2.1. Ba cấp độ test

| Loại test | Ví dụ | Chứng minh điều gì? |
|---|---|---|
| Unit test target | `target.getActiveJobs()` | Business logic Java |
| Integration test MBean | `server.getAttribute(name, "ActiveJobs")` | MBean registered, metadata/dispatch hợp lệ |
| Integration test proxy | `proxy.getActiveJobs()` và so với server | Spring client proxy gọi đúng MBean qua JMX |

Unit test vẫn cần thiết, nhưng nó không thay được kiểm thử thứ ba.

## 3. MBeanServerConnection là gì?

`javax.management.MBeanServerConnection` là interface chung để một client thao tác với MBeanServer. `MBeanServer` triển khai interface này, nên có thể dùng cùng API với local server:

```java
MBeanServer server = MBeanServerFactory.newMBeanServer();
MBeanServerConnection connection = server;
```

Các method chính:

```java
boolean isRegistered(ObjectName name);
Object getAttribute(ObjectName name, String attribute);
AttributeList getAttributes(ObjectName name, String[] names);
void setAttribute(ObjectName name, Attribute attribute);
Object invoke(ObjectName name, String operation, Object[] args,
              String[] signature);
MBeanInfo getMBeanInfo(ObjectName name);
Set<ObjectName> queryNames(ObjectName pattern, QueryExp query);
```

Khi dùng local server, không cần `JMXConnector`, cổng mạng, TLS hay RMI. Tuy nhiên lookup, metadata, signature và exception rules vẫn là JMX rules.

**Phân biệt:** một `MBeanServerConnection` local không tự kiểm thử remote authentication, TLS, firewall hoặc connector lifecycle. Muốn kiểm tra những yếu tố đó cần integration test riêng cho remote JMX.

## 4. Vì sao nên dùng một MBeanServer riêng trong test?

Platform server lấy từ `ManagementFactory.getPlatformMBeanServer()` là tài nguyên chung của JVM. Nếu nhiều test contexts cùng export `training.spring:type=Worker,name=Primary`, dễ gặp `InstanceAlreadyExistsException`.

Một fixture riêng:

```java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;

MBeanServer isolated =
    MBeanServerFactory.newMBeanServer("test.jmx");
```

Ưu điểm:

1. Không đụng tên với MBean production-like hoặc test khác trên platform server.
2. Có thể kiểm tra registry sạch theo từng test.
3. Test đóng context và xác minh registration bị unregister.
4. Có thể tạo nhiều fixture độc lập nếu test chạy song song.
5. Không cần bật remote JMX.

`newMBeanServer` tạo server không đăng ký với `MBeanServerFactory` giống một số đường tạo server khác. Dù vậy vẫn cần đóng Spring context và dọn resource do test tạo.

Không giả định JConsole sẽ tự phát hiện server riêng này; JConsole attach local thông thường dùng platform management interface.

## 5. Contract Java cho proxy và MBean

Ta chọn Standard MBean để tách bài toán proxy khỏi annotation metadata và làm rõ hợp đồng.

File `WorkerControlMBean.java`:

```java
package example.jmx;

public interface WorkerControlMBean {
    int getActiveJobs();
    boolean isEnabled();
    void setEnabled(boolean enabled);
    void resetCounters();
}
```

File `WorkerControl.java`:

```java
package example.jmx;

import java.util.concurrent.atomic.AtomicInteger;

public class WorkerControl implements WorkerControlMBean {
    private final AtomicInteger activeJobs = new AtomicInteger();
    private volatile boolean enabled = true;

    @Override
    public int getActiveJobs() {
        return activeJobs.get();
    }

    @Override
    public boolean isEnabled() {
        return enabled;
    }

    @Override
    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    @Override
    public void resetCounters() {
        activeJobs.set(0);
    }

    public void startedOneJob() {
        if (enabled) {
            activeJobs.incrementAndGet();
        }
    }
}
```

Các mapping JMX mong đợi:

| Interface method | JMX representation |
|---|---|
| `getActiveJobs()` | Attribute `ActiveJobs`, readable, không writable |
| `isEnabled()` | Attribute `Enabled`, readable |
| `setEnabled(boolean)` | Attribute `Enabled`, writable |
| `resetCounters()` | Operation `resetCounters`, không tham số |

Đây là hợp đồng Standard MBean; JMX server quyết định metadata theo interface `WorkerControlMBean`. Trong hệ thống dùng Spring `@ManagedResource` và `@ManagedAttribute`, kết quả tương đương cần được xác minh qua assembler.

## 6. Cấu hình Spring exporter và local proxy

File `JmxTestConfiguration.java`:

```java
package example.jmx;

import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.ObjectName;
import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.access.MBeanProxyFactoryBean;

@Configuration(proxyBeanMethods = false)
public class JmxTestConfiguration {

    public static final String NAME =
        "training.spring:type=Worker,name=Primary";

    @Bean
    public MBeanServer testMBeanServer() {
        return MBeanServerFactory.newMBeanServer("test.jmx");
    }

    @Bean
    public WorkerControl workerControl() {
        return new WorkerControl();
    }

    @Bean
    public MBeanExporter workerExporter(
            MBeanServer testMBeanServer,
            WorkerControl workerControl) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(testMBeanServer);
        exporter.setBeans(Map.of(NAME, workerControl));
        return exporter;
    }

    @Bean
    public MBeanProxyFactoryBean workerProxy(
            MBeanServer testMBeanServer) throws Exception {

        MBeanProxyFactoryBean factory =
            new MBeanProxyFactoryBean();
        factory.setServer(testMBeanServer);
        factory.setObjectName(new ObjectName(NAME));
        factory.setProxyInterface(WorkerControlMBean.class);
        return factory;
    }
}
```

Hai thành phần mấu chốt:

- Exporter được inject **chính server fixture**.
- Proxy cũng được inject **chính server fixture**, cùng ObjectName.

Nếu exporter dùng platform server còn proxy dùng test server, client sẽ gặp `InstanceNotFoundException` dù target object hoàn toàn bình thường.

### 6.1. Bẫy injection ambiguity

`workerControl` implement `WorkerControlMBean`; sản phẩm của `MBeanProxyFactoryBean` cũng implement interface ấy. Nếu inject `WorkerControlMBean` theo type mà không qualifier, Spring có thể gặp nhiều candidates.

Trong test, lấy bằng **bean name**:

```java
WorkerControlMBean proxy =
    context.getBean("workerProxy", WorkerControlMBean.class);
```

Điều này tránh vô tình nhận target rồi tưởng proxy đã hoạt động.

## 7. Kiểm thử đầu tiên: registration và metadata

File `LocalMBeanProxyIntegrationTest.java`:

```java
package example.jmx;

import java.util.Arrays;
import javax.management.*;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation
    .AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.*;

class LocalMBeanProxyIntegrationTest {

    @Test
    void mbeanHasExpectedMetadata() throws Exception {
        try (var context =
                new AnnotationConfigApplicationContext(
                    JmxTestConfiguration.class)) {

            MBeanServerConnection connection =
                context.getBean(MBeanServer.class);

            ObjectName name = new ObjectName(
                JmxTestConfiguration.NAME);

            assertTrue(connection.isRegistered(name));

            MBeanInfo info = connection.getMBeanInfo(name);

            MBeanAttributeInfo jobs =
                Arrays.stream(info.getAttributes())
                    .filter(a -> a.getName().equals("ActiveJobs"))
                    .findFirst()
                    .orElseThrow();

            assertTrue(jobs.isReadable());
            assertFalse(jobs.isWritable());
            assertEquals("int", jobs.getType());

            MBeanAttributeInfo enabled =
                Arrays.stream(info.getAttributes())
                    .filter(a -> a.getName().equals("Enabled"))
                    .findFirst()
                    .orElseThrow();

            assertTrue(enabled.isReadable());
            assertTrue(enabled.isWritable());

            assertTrue(Arrays.stream(info.getOperations())
                .anyMatch(op -> op.getName()
                    .equals("resetCounters")));
        }
    }
}
```

Test chứng minh một MBean có mặt trong server và metadata khớp hợp đồng. Tuy nhiên nó chưa gọi Spring proxy; cần bước tiếp theo.

## 8. Kiểm thử getter qua proxy và getAttribute

```java
@Test
void getterProxyReadsJmxAttribute() throws Exception {
    try (var context =
            new AnnotationConfigApplicationContext(
                JmxTestConfiguration.class)) {

        WorkerControl target =
            context.getBean(WorkerControl.class);

        WorkerControlMBean proxy =
            context.getBean(
                "workerProxy",
                WorkerControlMBean.class);

        MBeanServerConnection connection =
            context.getBean(MBeanServer.class);

        ObjectName name = new ObjectName(
            JmxTestConfiguration.NAME);

        assertNotSame(target, proxy);

        assertEquals(0, proxy.getActiveJobs());
        assertEquals(0, connection.getAttribute(
            name, "ActiveJobs"));

        target.startedOneJob();

        assertEquals(1, proxy.getActiveJobs());
        assertEquals(
            connection.getAttribute(name, "ActiveJobs"),
            proxy.getActiveJobs());
    }
}
```

Test này xác nhận getter Java qua proxy trả giá trị JMX và phản ánh state của MBean.

**Lưu ý quan trọng:** `assertNotSame(target, proxy)` chứng minh hai tham chiếu khác nhau nhưng chưa đủ để xác nhận đường JMX. Khi kết hợp với `getAttribute` và thử failure khi unregister (trong fixture riêng), bằng chứng mạnh hơn.

### 8.1. Vì sao không chỉ dùng `assertEquals(target.getActiveJobs(), proxy.getActiveJobs())`?

Nếu vô tình inject target thay proxy, kết quả vẫn giống. Cần lấy proxy bằng tên, assert khác instance và kiểm tra JMX registration/metadata.

## 9. Kiểm thử setter qua proxy và setAttribute

Nếu management interface expose `setEnabled(boolean)`, Spring client proxy phải chuyển lời gọi thành JMX attribute write.

```java
@Test
void setterProxyWritesJmxAttribute() throws Exception {
    try (var context =
            new AnnotationConfigApplicationContext(
                JmxTestConfiguration.class)) {

        WorkerControlMBean proxy =
            context.getBean(
                "workerProxy",
                WorkerControlMBean.class);

        MBeanServerConnection connection =
            context.getBean(MBeanServer.class);

        ObjectName name = new ObjectName(
            JmxTestConfiguration.NAME);

        assertTrue(proxy.isEnabled());

        proxy.setEnabled(false);

        assertEquals(false,
            connection.getAttribute(name, "Enabled"));

        assertFalse(proxy.isEnabled());

        connection.setAttribute(
            name, new Attribute("Enabled", true));

        assertTrue(proxy.isEnabled());
    }
}
```

Điều này xác minh luồng hai chiều: proxy `setEnabled` cập nhật attribute, còn một `setAttribute` từ JMX API được proxy đọc lại.

Không thêm setter vào một attribute chỉ đọc của hệ thống thật chỉ để test đường write. Ví dụ dùng riêng thuộc tính `Enabled` đã được thiết kế writable.

## 10. Kiểm thử operation qua proxy và invoke

```java
@Test
void operationProxyInvokesMBean() throws Exception {
    try (var context =
            new AnnotationConfigApplicationContext(
                JmxTestConfiguration.class)) {

        WorkerControl target =
            context.getBean(WorkerControl.class);

        WorkerControlMBean proxy =
            context.getBean(
                "workerProxy",
                WorkerControlMBean.class);

        MBeanServerConnection connection =
            context.getBean(MBeanServer.class);

        ObjectName name = new ObjectName(
            JmxTestConfiguration.NAME);

        target.startedOneJob();
        assertEquals(1, proxy.getActiveJobs());

        proxy.resetCounters();

        assertEquals(0,
            connection.getAttribute(name, "ActiveJobs"));

        target.startedOneJob();

        connection.invoke(
            name, "resetCounters",
            new Object[0], new String[0]);

        assertEquals(0, proxy.getActiveJobs());
    }
}
```

Lời gọi `proxy.resetCounters()` là Java method trên interface nhưng tác dụng phải được quan sát qua MBeanServer. Lời gọi `connection.invoke` kiểm tra contract của operation trực tiếp.

### 10.1. Signature của operation có tham số

Nếu interface có:

```java
void setLimit(int limit);
```

theo JavaBeans, `setLimit` có thể được xem là setter của attribute `Limit`, không nhất thiết là operation. Nếu muốn minh họa operation rõ ràng, dùng:

```java
void resetForQueue(String queue);
```

Lời gọi JMX:

```java
connection.invoke(
    name,
    "resetForQueue",
    new Object[]{"orders"},
    new String[]{String.class.getName()});
```

Không truyền tên type `"String"` hay `"Integer"` tùy tiện; signature phải khớp `MBeanOperationInfo` thực tế.

## 11. Kiểm thử read-only và lỗi ghi attribute

`ActiveJobs` không có setter trong `WorkerControlMBean`, nên metadata dự kiến `writable=false`.

```java
@Test
void activeJobsIsReadOnly() throws Exception {
    try (var context =
            new AnnotationConfigApplicationContext(
                JmxTestConfiguration.class)) {

        MBeanServerConnection connection =
            context.getBean(MBeanServer.class);

        ObjectName name = new ObjectName(
            JmxTestConfiguration.NAME);

        assertThrows(
            AttributeNotFoundException.class,
            () -> connection.setAttribute(
                name, new Attribute("ActiveJobs", 99)));
    }
}
```

Một implementation JMX có thể thể hiện lỗi ghi read-only theo contract thích hợp; để giảm phụ thuộc vào thông điệp exception, assert metadata `isWritable=false` cũng rất quan trọng.

Client interface thiếu setter **không đủ** kết luận server-side attribute chỉ đọc: một client khác có thể dùng `setAttribute`. Vì vậy cần bảo vệ trên MBean metadata.

## 12. Kiểm thử ObjectName sai hoặc MBean đã unregister

MBean proxy phụ thuộc registration thực tế. Trong test fixture cô lập, có thể chứng minh proxy thất bại khi object biến mất khỏi server.

```java
@Test
void proxyFailsAfterMBeanUnregistration() throws Exception {
    try (var context =
            new AnnotationConfigApplicationContext(
                JmxTestConfiguration.class)) {

        MBeanServer server =
            context.getBean(MBeanServer.class);

        WorkerControlMBean proxy =
            context.getBean(
                "workerProxy",
                WorkerControlMBean.class);

        ObjectName name = new ObjectName(
            JmxTestConfiguration.NAME);

        assertTrue(server.isRegistered(name));

        server.unregisterMBean(name);

        assertFalse(server.isRegistered(name));

        assertThrows(RuntimeException.class,
            proxy::getActiveJobs);
    }
}
```

Đây là cách kiểm thử negative path trong **server riêng của test**, không áp dụng với platform server dùng chung. Exception qua Spring proxy có thể được wrap thành runtime exception cụ thể; production test nên chốt loại exception theo phiên bản Spring của dự án và xem root cause thay vì chỉ tin vào một type tổng quát.

**Lưu ý cleanup:** exporter có thể cố unregister lại khi context đóng, nhưng implementation thường quản lý những registrations đã tạo. Một test thay đổi trực tiếp registry phải chấp nhận/kiểm tra cách exporter cleanup hoạt động trong phiên bản đang dùng. Nếu không muốn tác động đến lifecycle của exporter, tạo một proxy hướng tới ObjectName không tồn tại ngay từ đầu.

## 13. Kiểm thử proxy không trỏ nhầm server

Một lỗi wiring tinh vi:

```text
MBeanExporter --> Server A
MBeanProxyFactoryBean --> Server B
```

Cả hai server đều hợp lệ và cùng JVM, nhưng proxy không thấy MBean.

Test:

```java
MBeanServer serverA =
    MBeanServerFactory.newMBeanServer("A");

MBeanServer serverB =
    MBeanServerFactory.newMBeanServer("B");
```

Đăng ký MBean vào A nhưng cấu hình proxy dùng B. Lời gọi qua proxy sẽ thất bại vì ObjectName chưa đăng ký trong B.

Nếu cần xác minh server identity trong cấu hình Spring, inject cùng bean `MBeanServer` vào exporter và proxy; trong integration test có thể assert tham chiếu cùng server trước khi gọi getter.

**Không suy luận cùng default domain nghĩa là cùng server.** Hai MBeanServers có thể có cùng domain nhưng registry hoàn toàn khác.

## 14. Test với AnnotationMBeanExporter và @ManagedAttribute

Standard MBean là điểm khởi đầu dễ kiểm chứng. Trong ứng dụng Spring Framework thực tế, bean có thể dùng annotations:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "training.spring:type=Queue,name=Orders")
public class QueueMonitor {

    private volatile int pending;

    @ManagedAttribute
    public int getPending() {
        return pending;
    }

    @ManagedOperation
    public void resetPending() {
        pending = 0;
    }
}
```

Spring có thể export bean qua `@EnableMBeanExport` hoặc một `AnnotationMBeanExporter`/assembler tương thích. Interface client:

```java
public interface QueueMonitorManagement {
    int getPending();
    void resetPending();
}
```

Một `MBeanProxyFactoryBean` có `setProxyInterface(QueueMonitorManagement.class)` và ObjectName tương ứng sẽ hoạt động **nếu** metadata thực tế công bố `Pending` attribute và `resetPending` operation đúng.

Cần kiểm tra:

- Annotation exporter đã được bật ở context chứa bean chưa?
- ObjectName được chọn từ metadata hay strategy khác?
- Có exporter khác trùng registration không?
- Các methods có nằm trên proxy/target interface được assembler nhìn thấy không?
- Proxy dùng cùng MBeanServer không?

Không chỉ dựa trên annotation hiện diện trong source code.

## 15. Test với Spring AOP hoặc @Transactional

Khi bean được bọc bởi Spring AOP proxy, class thực tế mà exporter nhìn thấy có thể khác target class. Nếu dùng JDK dynamic proxy, các method quản trị không nằm trong interface được proxy expose có thể khó phát hiện theo cấu hình nhất định.

Ma trận test có ích:

| Cấu hình | Điều cần xác nhận |
|---|---|
| Không có AOP | MBean registration và proxy hoạt động |
| JDK dynamic proxy | Management interface vẫn được expose |
| Class-based proxy | Metadata không thay đổi ngoài ý định |
| Transaction advice | Operation đi qua advice đúng thiết kế |
| Custom MBeanInfoAssembler | Attributes/operations khớp contract |
| Multiple contexts | Exporter và client proxy dùng đúng server |

Nếu thêm `@Transactional` khiến proxy JMX không hoạt động, đừng bỏ transaction chỉ để test pass. Nên xác minh target/proxy type, annotation metadata và lựa chọn management facade riêng khi cần.

## 16. Fixture lifecycle: tránh test nhiễu lẫn nhau

Các quy tắc thực tế:

1. Tạo context và MBeanServer trong mỗi test hoặc mỗi fixture cô lập.
2. Đóng context bằng try-with-resources.
3. Không đăng ký MBean dưới ObjectName trùng trên platform server khi chạy song song.
4. Không dùng `RegistrationPolicy.IGNORE_EXISTING` để che collision giữa tests.
5. Không giả định mọi thread/executor được JMX listener tạo đều tự shutdown.
6. Dùng `@AfterEach` để cleanup nếu test tạo resource ngoài Spring lifecycle.
7. Tách remote connector tests khỏi local proxy tests.
8. Không thay đổi MBeanServer do ứng dụng khác đang sử dụng.

Ví dụ một lần test:

```java
try (var context =
        new AnnotationConfigApplicationContext(
            JmxTestConfiguration.class)) {
    // assertions...
}
// Spring context close triggers exporter lifecycle cleanup.
```

Việc `context.close()` gọi cleanup của exporter thường unregister MBeans do exporter đăng ký. Nếu test trực tiếp unregister hoặc replace MBean, cần kiểm tra chính sách và implementation cụ thể.

## 17. Đồng bộ và độ trễ của local proxy

Local proxy không đi qua mạng, nhưng vẫn có:

- Chi phí dispatch JMX.
- Reflection/adapter hoặc Spring interceptor.
- Validation tên và signature.
- AOP proxy/interceptor của managed bean nếu có.
- Locks và thời gian xử lý getter/operation.

Không dùng local proxy như cách truy cập metric cho từng request ở throughput cực cao nếu một Java method trực tiếp/metrics library phù hợp hơn. Với monitoring, management proxy giúp tách hợp đồng quản trị nhưng có chi phí cần đo.

### 17.1. Test latency tương đối

```java
long started = System.nanoTime();
int active = proxy.getActiveJobs();
long elapsed = System.nanoTime() - started;

System.out.println(
    "Active=" + active + ", elapsed ns=" + elapsed);
```

Đây chỉ là đo thăm dò, không phải benchmark chuẩn. Cần warm-up, nhiều iterations, thống kê và kiểm soát environment để so sánh hiệu năng. Test correctness không nên assert thời gian quá chặt trên CI.

## 18. Troubleshooting theo loại lỗi

| Triệu chứng | Nguyên nhân thường gặp | Bằng chứng |
|---|---|---|
| Proxy bean tạo được nhưng getter lỗi | MBean chưa đăng ký hoặc sai ObjectName | `isRegistered` |
| Getter báo không có attribute | Tên JavaBeans/assembler khác | `MBeanInfo.getAttributes()` |
| Setter không hoạt động | Attribute read-only | `isWritable()` |
| Operation không có | Sai metadata/signature | `MBeanInfo.getOperations()` |
| Proxy trả giá trị cũ | Target/caching/concurrency | So target và JMX read |
| Test chạy riêng pass, chạy suite fail | Shared platform MBeanServer hoặc collision | Server identity, names |
| Spring DI ambiguity | Target và proxy cùng interface | Inject theo bean name/qualifier |
| Sau context close vẫn còn MBean | Lifecycle cleanup hoặc registration thủ công | `isRegistered` sau close |
| Bật AOP rồi thiếu MBean | Proxy method visibility/assembler | AopUtils và MBeanInfo |
| Remote test thất bại nhưng local pass | Connector, auth, TLS, RMI | Kiểm tra remote layer riêng |

### 18.1. Trình tự chẩn đoán

```text
1. context.getBean("workerProxy") có trả proxy đúng không?
2. Exporter đã đăng ký ObjectName vào server nào?
3. connection.isRegistered(name) có true không?
4. MBeanInfo có attribute/operation dự kiến không?
5. proxy getter/setter/operation có chạy không?
6. Có exception wrapper/cause gì?
7. Test cleanup có xóa registration không?
```

Không tăng quyền, bật remote JMX hoặc đổi policy collision trước khi nắm được nguyên nhân.

## 19. Bài tập thực hành

### Bài tập A — Getter và attribute metadata

Tạo `WorkerControl` với getter `ActiveJobs`. Dùng `MBeanProxyFactoryBean` gọi `getActiveJobs()`, so với `getAttribute`. Assert `isReadable=true` và `isWritable=false`.

### Bài tập B — Setter và writable attribute

Thêm `isEnabled()`/`setEnabled(boolean)`. Đổi giá trị qua proxy, đọc lại qua JMX API, rồi set qua API và đọc bằng proxy. Kiểm tra metadata.

### Bài tập C — Operation

Thêm `resetCounters()`, gọi qua proxy và `connection.invoke`. Kiểm tra state sau mỗi đường.

### Bài tập D — Wrong ObjectName

Tạo một proxy với ObjectName khác tên exporter đã đăng ký. Gọi getter, ghi exception và cause. Thử `queryNames` để tìm ObjectName thực tế.

### Bài tập E — Server isolation

Tạo hai MBeanServers trong cùng JVM. Đăng ký vào A, proxy dùng B. Chứng minh lỗi. Sau đó inject cùng reference A cho exporter và proxy.

### Bài tập F — Multiple contexts

Đặt exporter trong root context và proxy trong child context. Đảm bảo cả hai dùng cùng server và tên. Đóng root rồi xem proxy còn kết nối tới MBean hay không.

### Bài tập G — AOP regression

Dùng một bean được export qua Spring JMX metadata. Bật AOP proxy và chạy lại contract tests. Nếu metadata biến mất, xác định proxy interface/assembler hoặc tách management facade.

## 20. Câu hỏi tự kiểm tra

1. `MBeanServerConnection` và `MBeanProxyFactoryBean` khác nhau ở vai trò nào?
2. Vì sao unit test gọi trực tiếp target chưa chứng minh proxy hoạt động?
3. Test nào chứng minh getter ánh xạ tới attribute?
4. Tại sao cần kiểm tra `MBeanInfo` trước khi tin vào proxy?
5. Vì sao có thể DI ambiguity khi target và proxy cùng implement management interface?
6. MBeanServer riêng có lợi gì trong integration test?
7. Khi proxy gọi `setEnabled`, server phải expose attribute như thế nào?
8. `resetCounters` được gọi bằng API JMX nào?
9. Nếu ObjectName đã unregister, getter proxy sẽ gặp vấn đề gì?
10. Local proxy test có kiểm tra được TLS/RMI không?
11. Vì sao context.close() quan trọng với test isolation?
12. Khi bật AOP, những phần nào của management contract có thể đổi?

## 21. Tài liệu tham khảo

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework API — `MBeanProxyFactoryBean`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/access/MBeanProxyFactoryBean.html
- Spring Framework API — `MBeanClientInterceptor`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/access/MBeanClientInterceptor.html
- Spring Framework API — `MBeanExporter`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Java SE 21 API — `MBeanServerConnection`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html
- Java SE 21 API — `MBeanInfo`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanInfo.html

**Ghi nhớ:** test proxy local đáng tin cậy phải đi qua đúng JMX boundary: exporter đăng ký MBean vào MBeanServer, proxy dùng cùng server/ObjectName, `MBeanServerConnection` chứng minh metadata và operation mapping, rồi Spring proxy được gọi như Java interface. Dùng server fixture cô lập và đóng context để giữ tests độc lập, lặp lại được và an toàn.
