# Kiểm tra thay đổi JDK hoặc framework ảnh hưởng JMX

## 1. Mục tiêu học tập

Khi nâng phiên bản JDK hoặc Spring Framework, code nghiệp vụ có thể vẫn biên dịch và chạy, nhưng bề mặt quản trị JMX có thể thay đổi theo những cách không dễ nhận ra: MBean không còn đăng ký, ObjectName khác, metadata của attribute/operation thay đổi, một Spring proxy không còn expose method như trước, remote connector không kết nối được hoặc công cụ giám sát gặp lỗi kiểu dữ liệu.

Bài học thuộc **Spring Framework JMX → Tiến hóa và tương thích**. Sau bài học, bạn có thể:

- Xác định những lớp hành vi JMX có thể bị ảnh hưởng khi nâng JDK, Spring hoặc thư viện liên quan.
- Tạo baseline rõ ràng cho ObjectName, `MBeanInfo`, attributes, operations và notifications.
- Kiểm thử `MBeanExporter`, annotation-driven export, naming strategy và Spring AOP sau nâng phiên bản.
- Kiểm tra platform MBeans, MXBeans, remote connector, serialization, authentication và network settings.
- Xây ma trận kiểm thử JDK/framework/client và quy trình canary, rollback.
- Phân biệt lỗi do API thay đổi thật với lỗi cấu hình, runtime classpath, module access và môi trường triển khai.

## 2. Vì sao JMX có thể bị ảnh hưởng dù code không đổi?

JMX có nhiều tầng:

```text
Management client: JConsole / JMC / agent / script
            |
            v
Remote connector (optional: RMI, TLS, auth)
            |
            v
MBeanServer / MBeanServerConnection
            |
            v
Spring MBeanExporter / annotation metadata
            |
            v
Managed bean / Spring AOP proxy / MXBean
            |
            v
Application services / JDK management internals
```

Một lần nâng cấp có thể thay đổi hành vi ở **bất kỳ tầng nào**:

1. JDK: các MXBean, module encapsulation, security configuration, TLS/cipher, RMI behavior hoặc GC implementation.
2. Spring: exporter lifecycle, metadata assembler, annotation scanning, naming strategy, AOP proxy và classpath.
3. Thư viện: MBean của cache, message broker, connection pool hoặc agent có thể đổi tên/metadata.
4. Deployment: hostname, container image, Java flags, Kubernetes port forwarding, firewall và certificate.
5. Client: Java version, JConsole/JMC, JMX connector provider hoặc classpath khác server.

Vì vậy, không chỉ chạy unit test của Java service; cần **kiểm thử hợp đồng JMX tại runtime** và luồng quản trị từ nơi client thực sự chạy.

## 3. Phân biệt ba loại tương thích

| Loại | Câu hỏi | Công cụ xác minh |
| --- | --- | --- |
| **Registration compatibility** | MBean vẫn có mặt dưới ObjectName cũ? | `isRegistered`, `queryNames` |
| **Management contract compatibility** | Attributes, operations, signatures, notifications còn như trước? | `getMBeanInfo`, invoke/read tests |
| **Transport/operational compatibility** | Client vẫn kết nối, xác thực, nhận dữ liệu và thao tác ổn định? | Remote connector integration test |

Ví dụ: sau nâng cấp, `isRegistered(name)` vẫn `true`, nhưng `getAttribute(name, "PendingCount")` ném lỗi vì attribute bị đổi tên. Registration test pass nhưng contract test fail.

Hoặc local JMX call pass, trong khi remote JMX thất bại vì `java.rmi.server.hostname` cấu hình sai trong container. Contract có thể đúng nhưng transport hỏng.

## 4. Lập danh mục hợp đồng JMX trước khi nâng cấp

Trước khi thay JDK/Spring, ghi nhận:

- JVM/JDK vendor, major version, runtime options và GC đang dùng.
- Spring Framework version, Spring Boot version nếu có, dependency quản trị liên quan.
- `MBeanServer` nào được sử dụng: platform hay custom.
- Những `ObjectName` ứng dụng công bố.
- Các attributes bắt buộc: name, type, read/write flags và ý nghĩa.
- Các operations quan trọng: name, parameter types, return type và side effects.
- Notification types, userData schema và event semantics.
- JMX remote endpoints, authentication, TLS và RMI ports.
- Client/agent đang sử dụng tên hoặc kiểu dữ liệu nào.
- Vòng đời context startup/shutdown và registration policy.

Một baseline có thể lưu ở dạng YAML:

```yaml
objectName: "com.example.orders:type=Queue,name=Payment"
attributes:
  PendingCount:
    type: "int"
    readable: true
    writable: false
  Paused:
    type: "boolean"
    readable: true
    writable: true
operations:
  - name: "retryFailed"
    signature: ["int"]
    returnType: "void"
notifications:
  - "com.example.orders.queue.overloaded"
```

Baseline phải lấy từ **hợp đồng đang được client dùng**, không chỉ tạo mới từ bản nâng cấp rồi so với chính nó.

## 5. Khác nhau giữa JDK management MBeans và MBeans ứng dụng

JDK cung cấp các platform management MXBeans, chẳng hạn:

```text
java.lang:type=Memory
java.lang:type=Threading
java.lang:type=Runtime
java.lang:type=ClassLoading
java.lang:type=OperatingSystem
```

Các MXBean chuẩn này phục vụ quan sát JVM. Tuy nhiên, những MBean phụ thuộc collector, implementation hoặc vendor có thể khác nhau giữa các JDK:

```text
java.lang:type=GarbageCollector,name=...
java.lang:type=MemoryPool,name=...
java.nio:type=BufferPool,name=...
```

Đừng giả định tên GC hoặc memory pool sẽ luôn giống giữa các thế hệ JDK. Ví dụ khi thay garbage collector, số lượng và tên `GarbageCollectorMXBean`/memory pools có thể khác, trong khi client vẫn cần quan sát cùng loại chỉ số.

Tốt hơn nên query theo pattern và đọc metadata:

```java
ObjectName gcPattern = new ObjectName(
    "java.lang:type=GarbageCollector,*"
);

for (ObjectName name :
        server.queryNames(gcPattern, null)) {
    System.out.println(name.getCanonicalName());
}
```

Client cần hiểu rằng từng collector không nhất thiết có tên bất biến. Việc một MBean implementation-specific không tồn tại trên JDK mới **không đồng nghĩa** API JMX tiêu chuẩn đã bị xóa.

## 6. Đọc JDK information từ JVM đích

Đối với local JVM:

```java
System.out.println(System.getProperty("java.version"));
System.out.println(System.getProperty("java.vendor"));
System.out.println(System.getProperty("java.vm.name"));
```

Còn từ `MBeanServerConnection` có thể đọc `java.lang:type=Runtime`:

```java
ObjectName runtimeName = new ObjectName(
    "java.lang:type=Runtime"
);

Object vmVersion = connection.getAttribute(
    runtimeName, "VmVersion"
);
Object specVersion = connection.getAttribute(
    runtimeName, "SpecVersion"
);

System.out.println(vmVersion);
System.out.println(specVersion);
```

Không dùng phiên bản Java của **client** để suy ra phiên bản Java của **server**. Với remote connector, `System.getProperty("java.version")` ở client chỉ mô tả chính client.

Khi điều tra tương thích, cần lưu rõ JDK client/server riêng biệt.

## 7. Kiểm tra Spring MBeanExporter sau nâng phiên bản

Spring có thể export MBean bằng `MBeanExporter`:

```java
import java.util.Map;
import javax.management.MBeanServer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class OrderJmxConfiguration {

    @Bean
    public MBeanExporter queueExporter(
            MBeanServer server,
            QueueAdminMBean queueAdmin) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(server);
        exporter.setBeans(Map.of(
            "com.example.orders:type=Queue,name=Payment",
            queueAdmin
        ));
        return exporter;
    }
}
```

Trong ví dụ, `QueueAdminMBean` là management interface ứng dụng; để đăng ký như Standard MBean, object implementation cần tuân convention tương ứng hoặc được bọc bằng cơ chế JMX phù hợp.

Sau nâng cấp, kiểm tra:

- Spring configuration class có được load không?
- Exporter có được tạo và khởi tạo đúng lifecycle?
- `MBeanServer` được inject có phải server dự kiến không?
- ObjectName mapping có còn giống trước không?
- `RegistrationPolicy` có bị thay đổi trong config không?
- Có exporter thứ hai cùng đăng ký MBean hoặc một exporter annotation-driven khác không?
- Shutdown có unregister đúng MBean do exporter quản lý không?

`MBeanExporter` đăng ký thành công không tự bảo đảm remote JMX connector được cấu hình đúng.

## 8. Kiểm tra @ManagedResource và annotation-driven export

Với cách annotation:

```java
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;

@ManagedResource(
    objectName = "com.example.orders:type=Queue,name=Payment"
)
public class OrderQueueAdmin {

    @ManagedAttribute
    public int getPendingCount() {
        return 12;
    }

    @ManagedOperation
    public void resetStatistics() {
        // ...
    }
}
```

Và cấu hình:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxAnnotationConfiguration {
}
```

Sau khi nâng Spring, cần test **runtime MBeanInfo**, không chỉ kiểm tra source annotation.

Ví dụ:

```java
ObjectName name = new ObjectName(
    "com.example.orders:type=Queue,name=Payment"
);

assertTrue(server.isRegistered(name));

MBeanInfo info = server.getMBeanInfo(name);
```

Kiểm tra những attribute/operation thực sự công bố trên server. Việc `@ManagedOperation` vẫn tồn tại trên class không chứng minh metadata assembler tìm được method đó trên một Spring proxy.

## 9. MBeanInfo là bằng chứng về contract thực tế

`MBeanServer.getMBeanInfo` cho phép kiểm tra:

```java
MBeanInfo info = server.getMBeanInfo(name);

for (var attr : info.getAttributes()) {
    System.out.printf(
        "%s %s readable=%s writable=%s%n",
        attr.getName(),
        attr.getType(),
        attr.isReadable(),
        attr.isWritable()
    );
}

for (var op : info.getOperations()) {
    System.out.println(op.getName());
    for (var param : op.getSignature()) {
        System.out.println("  " + param.getType());
    }
}

for (var notification : info.getNotifications()) {
    System.out.println(
        java.util.Arrays.toString(
            notification.getNotifTypes()
        )
    );
}
```

Khi so với baseline:

1. Dùng `ObjectName.equals()` hoặc canonical name; thứ tự key không phải khác danh tính.
2. So sánh attribute name/type/read-write flags.
3. So sánh operation name, ordered parameter types và return type.
4. So sánh notification types và contract của dữ liệu sự kiện.
5. Kiểm tra `OpenType` nếu dùng MXBean/OpenMBean.
6. Tránh coi thứ tự array/description/implementation class name là hợp đồng nếu không có client nào dựa vào chúng.

Một sự thay đổi trong `MBeanInfo.getClassName()` có thể do ModelMBean/proxy implementation đổi; cần xem nó có thực sự phá vỡ client hay không.

## 10. Viết contract test cho phiên bản mới

Giả sử management interface v1:

```java
public interface QueueAdminMBean {
    int getPendingCount();
    void resetStatistics();
}
```

Sau nâng cấp, muốn chắc chắn các thành phần đó vẫn tồn tại.

Ví dụ JUnit 5:

```java
import static org.junit.jupiter.api.Assertions.*;
import java.util.Arrays;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;

class QueueJmxCompatibilityTest {

    private final MBeanServer server; // khởi tạo trong test fixture

    QueueJmxCompatibilityTest(MBeanServer server) {
        this.server = server;
    }

    @Test
    void keepsPublishedContract() throws Exception {
        ObjectName name = new ObjectName(
            "com.example.orders:type=Queue,name=Payment"
        );

        assertTrue(server.isRegistered(name));

        MBeanInfo info = server.getMBeanInfo(name);

        assertTrue(
            Arrays.stream(info.getAttributes()).anyMatch(
                a -> a.getName().equals("PendingCount")
                  && a.getType().equals("int")
                  && a.isReadable()
            )
        );

        assertTrue(
            Arrays.stream(info.getOperations()).anyMatch(
                o -> o.getName().equals("resetStatistics")
                  && o.getSignature().length == 0
                  && o.getReturnType().equals("void")
            )
        );
    }
}
```

Đây là phần minh họa assertion; với JUnit 5 thực tế, test fixture cần cung cấp `MBeanServer` bằng `@BeforeEach`, Spring Test hoặc một factory phù hợp. Không dựa vào constructor injection trừ khi dự án đã cấu hình `ParameterResolver`.

Để test tự động, nên tạo một `MBeanServer` riêng và bật chính Spring exporter cần kiểm chứng.

## 11. Kiểm thử metadata giữa các phiên bản

Một pipeline có thể tạo hai artifacts:

```text
baseline-jmx-contract.json
current-jmx-contract.json
```

Quy trình:

```text
Build với phiên bản cũ
      |
      v
Start test context / MBeanServer
      |
      v
Export normalized MBeanInfo baseline
      |
      v
Build với phiên bản mới
      |
      v
Start test context / MBeanServer
      |
      v
Export normalized current contract
      |
      v
Compare backward compatibility
```

Một normalized record có thể chứa:

```json
{
  "objectName": "com.example.orders:name=Payment,type=Queue",
  "attributes": [
    {
      "name": "PendingCount",
      "type": "int",
      "readable": true,
      "writable": false
    }
  ],
  "operations": [
    {
      "name": "resetStatistics",
      "returnType": "void",
      "signature": []
    }
  ]
}
```

Không cần yêu cầu toàn bộ metadata bằng byte-for-byte. Bản mới có thể bổ sung attribute mà vẫn tương thích. Hãy so sánh những phần hợp đồng cũ **phải tiếp tục tồn tại** và thêm kiểm thử semantics riêng.

## 12. Kiểm tra Java module system và reflective access

Từ Java 9, hệ thống module (JPMS) có thể ảnh hưởng các thư viện sử dụng reflection hoặc truy cập class nội bộ. Khi nâng JDK, một số dependency/agent cũ có thể gặp:

```text
java.lang.reflect.InaccessibleObjectException
IllegalAccessException
ClassNotFoundException
NoClassDefFoundError
```

Nguyên nhân thường gặp:

- Thư viện cũ truy cập package nội bộ của JDK không còn mở.
- Một module ứng dụng chưa `exports` package chứa management interface.
- Runtime thiếu module cần thiết cho tool/connector.
- Classloader khác làm proxy/serializer không nhìn thấy type của MBean.
- JMX agent hoặc bytecode instrumentation không tương thích JDK mới.

Phân biệt `exports` và `opens`:

- `exports`: cho phép module khác truy cập public API của package.
- `opens`: cho phép reflection sâu trong điều kiện được chỉ định.

Đừng thêm hàng loạt `--add-opens` để che mọi lỗi. Hãy xác định thư viện/stack trace cần truy cập package nào, nâng dependency khi có thể và chỉ mở đúng phạm vi cần thiết.

## 13. JDK management agent và remote JMX settings

Remote JMX có thể được bật bằng JVM flags như:

```bash
-Dcom.sun.management.jmxremote
-Dcom.sun.management.jmxremote.port=9010
-Dcom.sun.management.jmxremote.rmi.port=9010
-Djava.rmi.server.hostname=127.0.0.1
```

Các tùy chọn cụ thể và hành vi có thể khác theo JDK distribution/version. Đừng sao chép flags từ một runtime cũ mà không thử lại sau nâng cấp.

Ở môi trường production:

- Bật authentication và authorization.
- Dùng TLS và chính sách certificate phù hợp.
- Giới hạn network access; không public JMX port trên Internet.
- Kiểm tra registry port, RMI server port và hostname được quảng bá.
- Không hardcode credentials trong source hoặc shell history nếu có cách quản lý secret phù hợp.
- Kiểm tra Docker/Kubernetes networking, NAT, DNS và port-forwarding.

Một port TCP mở không chứng minh remote JMX client đã gọi `getAttribute` thành công. Phải kiểm thử end-to-end tới đúng ObjectName.

## 14. JMX client và server có JDK khác nhau

Ví dụ:

```text
Client JDK 17 -> Server JDK 21
Client JDK 21 -> Server JDK 17
```

Về nguyên tắc, JMX Remote được thiết kế để cung cấp interoperability, nhưng trải nghiệm thực tế còn tùy:

- Connector protocol và provider.
- TLS cipher/certificate policies.
- Authentication setup.
- Classpath của client.
- Serialization của kiểu trả về.
- MXBean/OpenMBean types.
- Các features/attributes có chỉ xuất hiện trên JDK mới.

Một client JDK cũ không nên giả định hiểu mọi MXBean attribute mới của JDK server mới. Cũng không nên bắt buộc client dùng đúng JDK server nếu API/connector hiện tại hỗ trợ giao tiếp khác phiên bản.

Hãy kiểm chứng những cặp client/server **thực sự có trong vận hành**.

## 15. Serialization và MXBean/Open Data

Một management operation trả về object nội bộ:

```java
public InternalJobSnapshot getJobSnapshot();
```

có thể chạy local nhưng lỗi remote vì client JVM không có class hoặc serialization schema khác.

Để giảm rủi ro khi nâng JDK/Spring:

- Ưu tiên primitive, wrapper, `String`, `ObjectName` và các JMX Open Types.
- Với dữ liệu phức tạp, cân nhắc MXBean để biểu diễn qua `CompositeData`/`TabularData`.
- Tránh đưa domain entity nội bộ trực tiếp qua remote JMX.
- Giữ field names, type và units tương thích.
- Test việc deserialize thực tế từ client ngoài JVM.
- Tránh dùng Java serialized class phụ thuộc chi tiết implementation nếu client đa ngôn ngữ hoặc nhiều version.

Một `MBeanInfo` có metadata hợp lệ chưa chắc đảm bảo mọi client remote xử lý payload thành công.

## 16. Spring AOP proxy có thể đổi surface JMX

Khi thay Spring version hoặc bật các advisor mới, bean có thể được expose qua JDK dynamic proxy hoặc class-based proxy.

```text
Business target
    |
    v
Spring AOP proxy
    |
    v
MBeanExporter / JMX metadata assembler
```

Với JDK proxy, các method phải có trên interface mà proxy expose để caller gọi qua proxy theo cách thông thường. Với class-based proxy, nhiều method của class có thể được expose nhưng vẫn có giới hạn với `final`/`private`.

Nếu metadata source đọc annotation trên target nhưng exported object là proxy, một method có annotation vẫn có thể không invoke được nếu proxy interface không có method đó.

Giải pháp kiến trúc thường dễ kiểm soát:

```text
JMX Management Adapter (contract ổn định)
        |
        v
Business Service Interface / Spring AOP proxy
        |
        v
Target implementation
```

Adapter giữ `ObjectName`, attribute/operation contract độc lập với proxy mode của service. Nhưng vẫn cần integration test để chắc chắn đường gọi giữ transaction/security advice.

## 17. Notification compatibility

Nếu MBean phát notification:

```text
com.example.orders.queue.overloaded
```

client có thể dùng `NotificationFilterSupport` để chỉ nhận type đó.

Nếu bản nâng cấp đổi notification type, source hoặc userData schema, listener cũ có thể không hoạt động.

Kiểm tra:

- `MBeanInfo.getNotifications()` còn các types cũ không.
- `NotificationListener` còn nhận callback khi trigger sự kiện không.
- `sequenceNumber` và source semantics có thay đổi không.
- Remote connector có đưa notification qua kết nối thành công không.
- Nếu client reconnect sau downtime, nó có cách tự kiểm tra trạng thái thay vì giả định mọi notification được giao đủ không.

JMX notifications không phải hàng đợi bền vững/exactly-once; đừng dựa vào chúng như nguồn audit duy nhất sau nâng cấp.

## 18. Kiểm thử lifecycle và đăng ký trùng

Spring exporter thường đăng ký MBean khi context khởi tạo và cleanup khi context đóng. Sau nâng phiên bản, kiểm tra:

```text
Before context refresh: isRegistered = false
After context refresh:  isRegistered = true
After context close:    isRegistered = false
```

Nếu cùng JVM có nhiều Spring contexts hoặc exporters:

- MBean cũ chưa unregister có thể gây `InstanceAlreadyExistsException`.
- `RegistrationPolicy.IGNORE_EXISTING` có thể khiến context mới không xuất được MBean, trong khi client vẫn thấy object cũ.
- `REPLACE_EXISTING` có thể thay MBean thuộc component khác nếu ownership không rõ.
- Annotation exporter và manual exporter có thể đăng ký trùng cùng ObjectName.

Chọn naming convention và ownership rõ; tránh dùng UUID ngẫu nhiên chỉ để né lỗi trùng tên.

## 19. Ma trận nâng cấp cần kiểm chứng

| Trục | Ví dụ | Mục đích |
| --- | --- | --- |
| JDK runtime | JDK hiện tại, JDK mục tiêu | Phát hiện thay đổi platform MBeans và module access |
| Spring Framework | Bản hiện tại, bản mục tiêu | Exporter/annotation/proxy lifecycle |
| Spring Boot (nếu có) | Bản hiện tại, bản mục tiêu | Auto-configuration và JMX enablement |
| Management client | JConsole/JMC/agent hiện dùng | Kiểm tra UX, client classes |
| Network environment | Local, staging, container, remote | RMI hostname/ports/TLS |
| MBean type | Standard MBean, MXBean, ModelMBean | Metadata và serialization |
| Access mode | Local, remote read, remote invoke | Contract và transport |
| Lifecycle | Startup, redeploy, shutdown | Registration/unregister |
| Load | Polling bình thường, nhiều collectors | Latency và stability |

Không cần kiểm thử mọi tổ hợp không tồn tại trong thực tế; hãy ưu tiên các cặp JDK/Spring/client và deployment configurations đang hoặc sắp được vận hành.

## 20. Triển khai kiểm thử theo các mức

### Mức A: unit test không cần JMX remote

Kiểm tra:

- ObjectName được naming strategy tạo ra đúng.
- Java management interface ổn định.
- Logic nghiệp vụ được adapter quản trị gọi đúng.
- Parse/canonicalize names đúng.
- Các kiểu dữ liệu đơn giản không bị đổi ngoài ý muốn.

### Mức B: integration test Spring + MBeanServer thật

Dùng server riêng:

```java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;

MBeanServer server =
    MBeanServerFactory.newMBeanServer("test.management");
```

Khởi tạo Spring context chứa exporter, xác minh:

```java
assertTrue(server.isRegistered(expectedObjectName));
MBeanInfo info = server.getMBeanInfo(expectedObjectName);
```

Sau đó kiểm tra attributes, operations, notifications và lifecycle.

### Mức C: remote connector integration test

Khởi chạy JMX connector test đã được bảo vệ trong môi trường cô lập, dùng client ngoài JVM:

```java
try (JMXConnector connector =
         JMXConnectorFactory.connect(serviceUrl, env)) {

    MBeanServerConnection conn =
        connector.getMBeanServerConnection();

    assertTrue(conn.isRegistered(expectedObjectName));
    Object value = conn.getAttribute(
        expectedObjectName, "PendingCount"
    );
}
```

Kết quả cần bao gồm connection success, metadata, invocation và cleanup. Đừng dùng production connector không bảo vệ để làm lab.

### Mức D: canary/staging smoke test

Dùng target JDK/framework thật trong môi trường triển khai gần production. Xác minh dashboard, monitoring agent, JConsole/JMC và runbooks trước khi rollout rộng.

## 21. Quy trình upgrade đề xuất

```text
1. Inventory current JMX contracts / endpoints / clients
                  |
                  v
2. Save baseline ObjectName + MBeanInfo
                  |
                  v
3. Upgrade JDK / Spring in test environment
                  |
                  v
4. Run unit + Spring integration + remote tests
                  |
                  v
5. Compare metadata, behavior, notifications
                  |
                  v
6. Validate TLS, auth, ports, DNS, container networking
                  |
                  v
7. Deploy canary and observe metrics/logs
                  |
                  v
8. Rollout gradually with rollback plan
```

Trong quá trình nâng cấp, nếu phát hiện breaking change, cần xác định:

- Thay đổi có được chủ động thiết kế không?
- Client nào phụ thuộc hợp đồng cũ?
- Có thể giữ alias/old signature không?
- Có cần versioned ObjectName hay management adapter riêng không?
- Có thể rollback application/JDK image không?
- Cần cập nhật tài liệu vận hành và runbook gì?

Đừng biến một lỗi contract thành lỗi client bằng cách “sửa dashboard cho khớp” mà chưa xem ảnh hưởng tới các scripts/agents khác.

## 22. Phân biệt API behavior và môi trường triển khai

Một vấn đề chỉ xuất hiện sau nâng JDK chưa chắc do JMX API:

| Triệu chứng | Nguồn cần điều tra |
| --- | --- |
| `InstanceNotFoundException` | ObjectName, MBeanServer, exporter lifecycle |
| `InstanceAlreadyExistsException` | Duplicate exporter, registration policy, stale context |
| `NotCompliantMBeanException` | Standard MBean convention, assembler/proxy |
| `ReflectionException` khi invoke | Operation signature và method exposure |
| `InaccessibleObjectException` | Java module encapsulation, thư viện reflection |
| `NoClassDefFoundError` | Dependency/classpath/module changes |
| Remote connection refused | Port/firewall/connector not started |
| RMI lookup được nhưng call thất bại | RMI stub hostname/port, NAT/container |
| TLS handshake fail | Cipher/certificate/protocol policies |
| Deserialize fail | Type schema/classpath/client-server mismatch |
| GC metrics đổi | Collector hoặc implementation MBeans khác |
| MBean vẫn thấy nhưng số liệu “sai” | Semantics/units hoặc source của metrics thay đổi |

Hãy dùng log startup, classpath, JVM flags, `MBeanInfo`, network traces có kiểm soát và test độc lập để khoanh vùng.

## 23. Bài tập thực hành

1. Tạo một Spring MBean `com.example.orders:type=Queue,name=Payment` và lưu baseline ObjectName + `MBeanInfo`.
2. Chạy cùng test trên hai JDK versions mà dự án hỗ trợ; so sánh `java.lang` MXBeans và các MBeans ứng dụng.
3. Thay Spring proxy mode từ JDK sang class-based; kiểm tra metadata và operation invocation có khác không.
4. Đổi `int getPendingCount()` sang `long`, cho contract test phát hiện breaking change.
5. Chạy một remote client ngoài JVM khác version với server và kiểm tra getAttribute/invoke.
6. Cố tình dùng custom `MBeanServer` nhưng kết nối platform connector; phân tích vì sao MBean không hiển thị.
7. Kiểm tra `java.lang:type=GarbageCollector,*` trước và sau khi đổi GC; giải thích vì sao tên collector có thể khác.
8. Tạo test startup/close context liên tiếp để phát hiện MBean leak hoặc registration trùng.
9. Thiết kế canary checklist cho JDK/Spring upgrade trong ứng dụng có nhiều monitoring agents.
10. Viết migration plan cho một operation cũ bị đổi chữ ký trong bản Spring hoặc ứng dụng mới.

## 24. Câu hỏi tự kiểm tra

- Vì sao unit test service pass chưa chắc JMX contract còn tương thích?
- `MBeanInfo` cung cấp dữ liệu nào quan trọng khi so sánh hai phiên bản?
- Vì sao platform GC MBean names có thể khác sau nâng JDK?
- Local JMX test có đủ để xác minh remote connector/TLS không?
- Khi `@ManagedResource` còn nhưng MBean mất, nên kiểm tra gì?
- Vì sao JDK client version không phải JDK server version?
- `--add-opens` có nên được thêm hàng loạt khi có lỗi reflection không?
- Khi nào cần hỗ trợ client cũ trong rolling upgrade?
- Vì sao cần contract baseline độc lập với build đang kiểm tra?
- Quy trình rollback cần tính đến quản lý MBean và monitoring như thế nào?

**Ghi nhớ:** Nâng JDK hoặc Spring Framework có thể ảnh hưởng JMX ở cả registration, metadata, proxy, module access, serialization và remote connector. Muốn nâng cấp an toàn, hãy lập baseline từ phiên bản đang chạy, xác minh hợp đồng qua `MBeanInfo`, kiểm thử local/remote trên các cặp JDK-client/server thực tế và triển khai canary có rollback plan.