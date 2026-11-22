# Giảm surface area bằng cách chỉ export MBean cần thiết trong Spring Framework JMX

## 1. Tại sao phạm vi export là một quyết định bảo mật?

JMX (Java Management Extensions) giúp giám sát và điều khiển ứng dụng Java đang chạy. Khi sử dụng Spring Framework, các bean có thể được xuất ra `MBeanServer` thông qua `MBeanExporter`, `AnnotationMBeanExporter`, `@ManagedResource` hoặc một cơ chế cấu hình tương đương. Công cụ như JConsole và các JMX collector sau đó có thể khám phá ObjectName, đọc attribute và gọi operation.

Điều thuận tiện cho vận hành cũng tạo ra một **bề mặt quản trị có đặc quyền**: càng nhiều MBean, attribute và operation được công bố, càng nhiều khả năng nội bộ được mở cho client có quyền truy cập JMX. Đây là **management attack surface**, khác với HTTP API nhưng cũng phải được thiết kế, kiểm kê và bảo vệ.

Ví dụ, một service có các method:

```java
public class PaymentService {
    public long getProcessedPayments() { /* ... */ }
    public String getStatus() { /* ... */ }
    public String getApiToken() { /* ... */ }
    public void clearPendingPayments() { /* ... */ }
    public void retryFailedPayment(String id) { /* ... */ }
}
```

Người vận hành có thể chỉ cần `ProcessedPayments` và `Status`. Nếu vô tình export thêm `ApiToken`, `clearPendingPayments` và `retryFailedPayment`, JMX đã mở rộng khả năng đọc dữ liệu nhạy cảm và thay đổi trạng thái nghiệp vụ.

**Nguyên tắc chính:** chỉ export MBean thực sự cần cho mục đích quản trị, và bên trong mỗi MBean chỉ công bố đúng attribute/operation đã được phê duyệt.

Bài này giải thích cách giảm surface area ở ba cấp: **số MBean**, **số khả năng của từng MBean** và **số client có thể truy cập**.

## 2. Ba lớp của JMX surface area

```text
                JVM / Spring Application
                         |
           +-------------+-------------+
           |                           |
   Spring business beans         Platform MXBeans
           |                           |
     MBeanExporter                     |
           |                           |
           +---------- MBeanServer ----+
                           |
                     JMX connector
                           |
                JConsole / monitoring
```

Các tầng cần kiểm soát:

| Lớp | Ví dụ | Câu hỏi thiết kế |
|---|---|---|
| **Resource exposure** | `OrderMonitor`, `CacheAdmin`, `PaymentConfig` | Bean nào thực sự cần thành MBean? |
| **Method/data exposure** | `getQueueDepth()`, `resetCounters()`, `getPassword()` | Chỉ số và operation nào nên được công bố? |
| **Connection exposure** | Local attach, remote JMX RMI, monitoring agent | Client nào được phép kết nối, đọc hoặc điều khiển? |

Giảm số MBean không thay thế xác thực connector. Ngược lại, có authentication không có nghĩa nên export mọi bean. Một thiết kế tốt dùng **defense in depth**: giảm dữ liệu và khả năng được công bố trước, rồi giới hạn client và đường truyền sau.

Ngoài MBean do ứng dụng tạo, JVM còn có platform MXBeans về memory, threads, class loading, runtime và garbage collection. Vì thế ngay cả khi không export custom MBean, một JMX connector vẫn có thể cung cấp thông tin chẩn đoán đáng kể. “Chỉ export MBean cần thiết” là biện pháp quan trọng nhưng **không làm toàn bộ JMX interface biến mất**.

## 3. Phân loại MBean trước khi quyết định export

Không nên xuất mọi bean chỉ vì chúng tồn tại trong `ApplicationContext`. Hãy chia thành nhóm:

### 3.1. Nhóm quan sát vận hành

Các MBean chỉ công bố trạng thái và số đo tổng hợp:

```text
QueueMonitor
  QueueDepth
  ProcessedTotal
  ConsumerState

CacheMonitor
  HitCount
  MissCount
  EstimatedEntryCount
```

Đây thường là nhóm nên ưu tiên nếu có mục tiêu giám sát rõ ràng. Getter cần nhanh, tránh truy cập dữ liệu người dùng thô hoặc thực hiện tác vụ dài.

### 3.2. Nhóm điều khiển hạn chế

Các MBean có operation hoặc writable attribute:

```text
QueueControl
  pause()
  resume()

CacheAdmin
  clearCache()
```

Những thao tác này có thể hợp lý nhưng phải được xem như API quản trị có tác dụng phụ. Cần validation, quyền hạn, audit, giới hạn concurrency và trạng thái lifecycle. Một `clearCache()` nhầm có thể làm tăng tải database hoặc mất hiệu năng ngay lập tức.

### 3.3. Nhóm dữ liệu không nên xuất

Thông thường không export:

- Credential, password, API token, private key, refresh token.
- Session, cookie, authorization header, request body.
- Thông tin cá nhân và dữ liệu nghiệp vụ của từng khách hàng.
- Toàn bộ `Environment`, system properties hoặc configuration object.
- Stack trace, raw exception message có thể chứa thông tin nội bộ.
- Repository/service nội bộ với nhiều method thao tác dữ liệu.

Nếu cần chẩn đoán credential, export trạng thái `CONFIGURED` hoặc `VALIDATION_FAILED` thay vì giá trị secret. Nếu cần quan sát người dùng, export tổng số request hoặc tỷ lệ lỗi thay vì dữ liệu định danh.

## 4. Explicit export: danh sách MBean được phép

Khi cần kiểm soát chặt, một chiến lược dễ kiểm tra là **chỉ định rõ những bean được export** bằng `MBeanExporter.setBeans(...)`.

Ví dụ Spring Framework:

```java
import java.lang.management.ManagementFactory;
import java.util.Map;
import javax.management.MBeanServer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class ControlledJmxConfiguration {

    @Bean
    public MBeanServer mbeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public QueueMonitor queueMonitor() {
        return new QueueMonitor();
    }

    @Bean
    public PaymentService paymentService() {
        return new PaymentService();
    }

    @Bean
    public MBeanExporter mbeanExporter(
            MBeanServer mbeanServer,
            QueueMonitor queueMonitor) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(mbeanServer);

        exporter.setBeans(Map.of(
            "company.ops:type=QueueMonitor,name=primary",
            queueMonitor
        ));
        return exporter;
    }
}
```

Giả sử `QueueMonitor` là JMX-compliant MBean hoặc được cấu hình assembler phù hợp. Chỉ `queueMonitor` nằm trong mapping; `paymentService` vẫn là Spring bean phục vụ nghiệp vụ nhưng **không được exporter này chỉ định để đăng ký**.

Cần phân biệt rõ: một bean không nằm trong mapping này vẫn có thể bị exporter khác trong cùng JVM xuất ra nếu ứng dụng bật thêm autodetection hoặc annotation export. Vì vậy explicit allowlist phải đi kèm **kiểm kê tất cả exporter** và cách chúng chọn bean.

### 4.1. Vì sao explicit mapping phù hợp với hệ thống nhạy cảm?

Một reviewer có thể nhìn thấy ngay:

```text
ObjectName                               Spring bean
company.ops:type=QueueMonitor,name=primary -> queueMonitor
company.ops:type=CacheMonitor,name=main    -> cacheMonitor
```

Khi team thêm service mới, service đó không tự động nằm trong danh sách chỉ vì có tên class hoặc annotation phù hợp. Điều này làm **sự mở rộng bề mặt JMX trở thành thay đổi cấu hình có chủ đích**.

Đổi lại, explicit mapping tốn công hơn khi có nhiều MBean. Nếu quy mô lớn, có thể chuẩn hóa một module cấu hình JMX tập trung và yêu cầu review mỗi khi có mapping mới.

## 5. Hạn chế autodetection

`MBeanExporter` có khả năng autodetection. Khi bật, Spring có thể tìm những bean đáp ứng tiêu chí JMX hoặc metadata assembler trong application context.

Ví dụ:

```java
MBeanExporter exporter = new MBeanExporter();
exporter.setAutodetect(true);
```

Autodetection thuận tiện cho demo, ứng dụng nhỏ hoặc môi trường đã có một tập MBean được kiểm soát. Nhưng trong codebase lớn, những thay đổi không nhằm mở rộng API quản trị vẫn có thể làm xuất hiện MBean mới:

- Một class bắt đầu implement interface theo convention Standard MBean.
- Một component được thêm `@ManagedResource`.
- Một auto-configuration mới tạo thêm exporter.
- Một module được import vào application context khác.
- Proxy/lifecycle thay đổi đối tượng mà exporter nhìn thấy.

**Autodetection không đồng nghĩa export tất cả Spring bean**, nhưng vẫn cần giới hạn phạm vi và kiểm kê những bean thật sự đủ điều kiện. Nếu yêu cầu bảo mật là chỉ cho phép một tập ObjectName được phê duyệt, explicit export thường dễ chứng minh hơn.

Khi muốn dùng autodetect, cần một quy trình kiểm tra MBeanInfo và ObjectName sau mỗi deployment để phát hiện thay đổi ngoài dự kiến.

## 6. Annotation-based export cũng cần allowlist

Spring cho phép:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(objectName = "company.ops:type=Status")
public class OperationalStatus {

    @ManagedAttribute
    public String getState() {
        return "READY";
    }
}
```

Với annotation exporter được cấu hình phù hợp, `OperationalStatus` trở thành ứng viên MBean. Đây là kiểu allowlist ở cấp class/bean: chỉ những class có annotation quản trị được chọn theo chiến lược tương ứng.

Nhưng nếu team thêm annotation `@ManagedResource` vào một class nghiệp vụ rất lớn, cần bảo đảm chỉ các method an toàn được chọn qua `@ManagedAttribute`/`@ManagedOperation`. Không export dữ liệu nhạy cảm hoặc operation nguy hiểm chỉ vì người viết muốn tiện debug.

**Hai cấp allowlist cần có:**

1. Bean nào được phép trở thành MBean?
2. Trong MBean đó, method/attribute nào được phép công bố?

Annotation giúp lựa chọn có chủ đích, nhưng không thay thế review về thông tin và hành vi được tiết lộ.

## 7. Management interface để giới hạn method

Một Standard MBean của JDK sử dụng management interface theo convention:

```java
public interface QueueMonitorMBean {
    int getQueueDepth();
    long getProcessedCount();
}
```

Implementation:

```java
import java.util.concurrent.atomic.AtomicLong;

public class QueueMonitor implements QueueMonitorMBean {
    private final AtomicLong processed = new AtomicLong();

    @Override
    public int getQueueDepth() {
        return 5;
    }

    @Override
    public long getProcessedCount() {
        return processed.get();
    }

    public String getInternalToken() {
        return "do-not-export-real-secret";
    }

    public void deleteAllPendingJobs() {
        // Method nghiệp vụ không dành cho JMX.
    }
}
```

Nếu đối tượng được đăng ký là Standard MBean, JMX chỉ công bố hợp đồng từ `QueueMonitorMBean`, không tự export `getInternalToken()` hay `deleteAllPendingJobs()`.

Với Spring ModelMBean, `InterfaceBasedMBeanInfoAssembler` cũng có thể dùng một management interface làm nguồn chọn method. Đây là kỹ thuật giảm surface area rõ ràng hơn so với một assembler phản chiếu rộng toàn bộ public methods.

### 7.1. Không dùng interface nghiệp vụ làm interface quản trị

Một interface:

```java
public interface PaymentService {
    Receipt charge(CardData data);
    void refund(String transactionId);
    void deleteDraft(String id);
}
```

không nên được đưa trực tiếp thành JMX management contract chỉ vì tiện tái sử dụng. Những operation này có ý nghĩa nghiệp vụ mạnh và kiểu dữ liệu phức tạp, có thể không phù hợp với JMX. Hãy tạo một interface quản trị riêng:

```java
public interface PaymentMonitoring {
    long getCompletedPayments();
    String getServiceState();
}
```

Một facade mỏng có thể triển khai interface này và lấy trạng thái từ service. Phân tách giúp giới hạn method được công bố và giảm rủi ro lộ dữ liệu hoặc thao tác ngoài mục đích.

## 8. Cẩn thận với reflective assembler

Spring có `MBeanInfoAssembler` với những chiến lược chọn method khác nhau. Một assembler phản chiếu toàn bộ public API có thể công bố nhiều method hơn chủ đích.

So sánh khái niệm:

| Chiến lược | Mức kiểm soát | Rủi ro |
|---|---|---|
| Reflective assembler chọn rộng | Thấp nếu class có nhiều method | Export thừa getter/operation |
| `MethodNameBasedMBeanInfoAssembler` | Allowlist theo tên method | Cần cập nhật cấu hình khi API đổi |
| `InterfaceBasedMBeanInfoAssembler` | Allowlist theo interface | Hợp đồng rõ, dễ review |
| `MetadataMBeanInfoAssembler` | Chọn bằng metadata/annotation | Cần kiểm tra annotation không gắn nhầm |
| Standard MBean interface | Hợp đồng JMX chuẩn | Cần quản lý interface riêng |

Không nên cố “sửa” lỗi một method không xuất hiện bằng cách chuyển sang reflective exporter rộng hơn, vì có thể đồng thời phơi bày method nhạy cảm.

Một dự án có thể dùng nhiều cơ chế export khác nhau; hãy chọn một cách rõ ràng cho mỗi tập bean và kiểm tra metadata thực tế.

## 9. Tách read-only monitoring khỏi write operations

Một cách giảm surface area là tách **monitoring** và **management**.

```text
QueueMonitoringMBean
  QueueDepth (read-only)
  ProcessedTotal (read-only)
  State (read-only)

QueueAdministrationMBean
  pause()
  resume()
  clearCache()
```

Không phải hệ thống nào cũng cần hai MBean riêng, nhưng nếu quyền đọc metrics được cấp rộng hơn quyền thay đổi runtime, việc tách interface và ObjectName có thể giúp định nghĩa chính sách rõ ràng.

Tuy vậy, tách thành hai MBean **không tự tạo phân quyền**. Nếu cùng connector cho phép mọi client gọi tất cả operation, người dùng vẫn có thể điều khiển MBean quản trị. Cần cấu hình authorization phù hợp ở JMX access layer hoặc dùng một cơ chế quản trị riêng có kiểm soát tốt hơn.

### 9.1. Writable attribute cũng là bề mặt điều khiển

```java
void setWarningThreshold(int value);
```

dù chỉ là setter của attribute, vẫn là một thao tác thay đổi trạng thái. Hãy áp dụng:

- Validation phạm vi giá trị.
- Kiểm soát quyền ghi.
- Audit khi có ý nghĩa vận hành.
- Kiểm tra trạng thái lifecycle, ví dụ không cho sửa khi STOPPING.
- Không dùng setter JMX để truyền hoặc cập nhật secret không được bảo vệ.

Read-only attribute giúp giới hạn khả năng điều khiển nhưng vẫn phải đánh giá **dữ liệu bị đọc ra**.

## 10. Không export secret, configuration dump hay dữ liệu người dùng

Một getter như:

```java
@ManagedAttribute
public String getApiKey() {
    return settings.getApiKey();
}
```

có thể tiết lộ credential qua JMX, ngay cả khi field gốc là `private`, getter là read-only và application không có HTTP endpoint tương ứng.

Những anti-pattern khác:

```java
@ManagedAttribute
public String getFullConfiguration() {
    return config.toString();
}

@ManagedAttribute
public java.util.Map<String, String> getEnvironment() {
    return System.getenv();
}

@ManagedAttribute
public String getLastRequestBody() {
    return lastRequest.getBody();
}
```

Nếu cần thông tin vận hành, xuất trạng thái tổng hợp:

```java
@ManagedAttribute
public boolean isCredentialConfigured() {
    return credentialHealth.isConfigured();
}

@ManagedAttribute
public String getLastErrorCategory() {
    return failureState.getCategory().name();
}

@ManagedAttribute
public long getFailedRequestsTotal() {
    return counters.getFailedRequests();
}
```

Ngay cả một error message cũng có thể chứa endpoint, username hoặc payload nhạy cảm. Không xuất raw exception và không giả định `toString()` sẽ luôn che secret.

**Data minimization ngay ở MBean** là lớp bảo vệ mạnh: dữ liệu không được export thì JMX client không thể đọc qua chính attribute đó, dù client có quyền kết nối rộng.

## 11. Kiểm soát ObjectName và naming strategy

ObjectName định danh MBean trong `MBeanServer`:

```text
company.orders:type=QueueMonitor,name=primary
company.cache:type=CacheStatus,name=product
```

Một naming convention nhất quán hỗ trợ kiểm kê allowlist:

```text
Cho phép:
  company.orders:type=QueueMonitor,name=primary
  company.cache:type=CacheStatus,name=product

Không dự kiến:
  company.payment:type=SecretConfig
  company.internal:type=DebugEverything
```

Cần hiểu rằng domain/key properties của ObjectName cũng là metadata được JMX client khám phá. Không đặt token, user ID nhạy cảm, mật khẩu hoặc endpoint có credential vào ObjectName.

Tập ObjectName hiệu lực có thể đổi do `ObjectNamingStrategy`, `@ManagedResource(objectName=...)`, explicit mappings hoặc các module khác. Vì vậy, một policy quản trị tốt cần kiểm tra **registry thật** thay vì suy luận chỉ từ tên bean trong source.

## 12. Kiểm kê MBean đang được đăng ký

Có thể truy vấn `MBeanServer` bằng Java:

```java
import java.lang.management.ManagementFactory;
import java.util.Set;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

Set<ObjectName> names = server.queryNames(
    new ObjectName("company.*:*"),
    null
);

names.stream()
    .map(ObjectName::toString)
    .sorted()
    .forEach(System.out::println);
```

Ví dụ này quan sát platform server trong JVM đang chạy. Nếu exporter dùng một MBeanServer riêng, phải truy vấn đúng server đó.

Mục tiêu của inventory:

1. Ghi lại ObjectName thực tế sau startup.
2. So sánh với danh sách MBean được phê duyệt.
3. Đánh dấu ObjectName mới hoặc không dự kiến.
4. Kiểm tra MBeanInfo của các MBean thuộc phạm vi ứng dụng.
5. Điều tra nguyên nhân từ exporter, annotation, autodetection, dependency hoặc module mới.

Không tự động unregister một ObjectName lạ chỉ vì nó không thuộc danh sách custom MBean của bạn; có thể đó là platform MXBean hoặc MBean của thư viện cần thiết. Inventory giúp phát hiện sai lệch trước khi quyết định sửa cấu hình.

## 13. Kiểm tra MBeanInfo để biết attribute và operation thật

```java
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;

MBeanInfo info = server.getMBeanInfo(name);

for (MBeanAttributeInfo attr : info.getAttributes()) {
    System.out.printf(
        "ATTR %s type=%s readable=%s writable=%s%n",
        attr.getName(),
        attr.getType(),
        attr.isReadable(),
        attr.isWritable()
    );
}

for (MBeanOperationInfo op : info.getOperations()) {
    System.out.println("OP " + op.getName());
}
```

`MBeanInfo` cho biết bề mặt thực tế mà client nhìn thấy. Đây là bằng chứng tốt hơn việc nhìn source, vì một MBean có thể được tạo qua ModelMBean, proxy, annotation exporter hoặc Standard MBean interface với metadata khác nhau.

**Không tự động gọi mọi getter/operation để kiểm kê.** Đọc metadata thường đủ cho bước đầu; một getter có thể trả secret hoặc kích hoạt truy vấn nặng, còn operation có thể gây tác dụng phụ. Nếu cần kiểm thử giá trị, chọn một số attribute an toàn trong môi trường phù hợp.

### 13.1. Kiểm thử allowlist

Trong integration test, định nghĩa tập tên MBean mà ứng dụng sở hữu:

```java
Set<String> expected = Set.of(
    "company.orders:type=QueueMonitor,name=primary",
    "company.cache:type=CacheStatus,name=product"
);
```

Lấy tập ObjectName thực tế trong domain thuộc ứng dụng, chuẩn hóa bằng `getCanonicalName()` nếu cần so sánh không phụ thuộc thứ tự key, rồi xác nhận không có tên ngoài danh sách.

Ví dụ ý tưởng:

```java
Set<String> actual = server.queryNames(
    new ObjectName("company.*:*"), null
).stream()
 .map(ObjectName::getCanonicalName)
 .collect(java.util.stream.Collectors.toSet());
```

Cần lưu ý rằng `ObjectName` canonicalization ảnh hưởng cách so sánh chuỗi. Hãy chuẩn hóa cả expected và actual theo cùng cách khi chạy test thật.

Trong production có thể có MBean mới hợp lệ do runtime platform/library; chỉ áp dụng allowlist nghiêm ngặt cho domain thuộc sở hữu ứng dụng, không cho toàn bộ `java.lang`, `com.sun.management` hoặc các domain do bên khác quản lý.

## 14. Kiểm tra exporter thực sự tồn tại trong ApplicationContext

Một ứng dụng có thể có nhiều `MBeanExporter`:

```java
Map<String, MBeanExporter> exporters =
    context.getBeansOfType(MBeanExporter.class);

exporters.forEach((name, exporter) ->
    System.out.println(
        name + " -> " + exporter.getClass().getName()
    )
);
```

Nếu Spring Boot tự cấu hình exporter và dự án khai báo thêm exporter thủ công, hai bên có thể cùng chọn một MBean. Cần xác định:

- Exporter nào có annotation autodetection.
- Exporter nào dùng explicit `setBeans`.
- Có nhiều context cùng sử dụng một platform server không.
- Có ObjectName trùng và registration policy đang làm gì.
- Có module hoặc thư viện tự đăng ký MBean bên ngoài Spring exporter không.

Để giảm surface area thật sự, phải xét **tất cả nguồn đăng ký**, không chỉ một `@Configuration` đang mở trong IDE.

## 15. Registration policy không phải bộ lọc bảo mật

Spring có các chính sách xử lý ObjectName trùng:

```java
exporter.setRegistrationPolicy(
    RegistrationPolicy.FAIL_ON_EXISTING
);
```

Các lựa chọn thường gặp:

| Policy | Khi ObjectName đã tồn tại |
|---|---|
| `FAIL_ON_EXISTING` | Báo lỗi collision |
| `IGNORE_EXISTING` | Bỏ qua registration mới, giữ MBean đang có |
| `REPLACE_EXISTING` | Thay registration cũ theo cơ chế exporter |

Không dùng `IGNORE_EXISTING` để “giảm số MBean” nếu mục tiêu thực sự là quyết định bean nào được export. Policy xử lý **tên trùng**, không quyết định những bean nào là an toàn để công bố.

`REPLACE_EXISTING` cũng không phải cách sửa cấu hình trùng tên mà không xem ownership. Thay MBean của module khác có thể khiến dashboard quan sát sai đối tượng.

Hãy giải quyết nguồn gốc: explicit mapping, naming convention, phân chia ownership và chỉ một exporter chịu trách nhiệm cho mỗi tập ObjectName.

## 16. Spring Boot Actuator và surface area JMX

Trong Spring Boot, JMX export có thể bị ảnh hưởng bởi:

```properties
spring.jmx.enabled=true
management.endpoints.jmx.exposure.include=health,info
```

Đây là một ví dụ giới hạn **Actuator endpoint exposure qua JMX**, không đồng nghĩa chỉ còn hai MBean trong JVM. Platform MXBeans và các MBean khác vẫn có thể tồn tại.

Phân biệt:

- Spring `@ManagedResource` → custom MBean thông qua annotation export phù hợp.
- Standard MBean → MBean có management interface theo JMX.
- Actuator `@Endpoint` → endpoint có thể được export thành MBean qua Actuator JMX exporter.
- Platform MXBean → do JVM cung cấp, tồn tại độc lập với custom Spring MBean.

Nếu muốn giảm surface area, kiểm soát **từng nguồn export**. Tắt một Actuator endpoint không tự gỡ các custom MBean khác. Ngược lại, bỏ `@ManagedResource` khỏi một bean không làm platform MXBean biến mất.

### 16.1. Không dùng wildcard exposure không kiểm soát

```properties
management.endpoints.jmx.exposure.include=*
```

có thể hữu ích trong môi trường test cô lập nhưng không nên là mặc định production. Endpoint mới trong một lần nâng cấp Boot/dependency có thể xuất hiện thêm nếu được enable và thuộc exposure wildcard. Ưu tiên liệt kê endpoint cụ thể.

Nếu ứng dụng sử dụng HTTP Actuator, `management.endpoints.web.exposure.include` là cấu hình **khác**; hai danh sách không tự đồng nhất.

## 17. Local JMX và remote connector

Giảm MBean export chỉ kiểm soát một phần khả năng quản trị. Khi bật remote JMX, một client ở nơi khác có thể truy vấn MBeanServer được connector công bố.

Các biện pháp cần thiết:

1. Không mở JMX port ra Internet công khai.
2. Giới hạn nguồn truy cập ở firewall/network policy.
3. Dùng authentication và phân quyền phù hợp.
4. Bảo vệ đường truyền bằng TLS hoặc kênh mã hóa được thiết kế rõ.
5. Hạn chế quyền ghi/call operation của tài khoản monitoring.
6. Quản lý credential, truststore, keystore an toàn.
7. Audit các thao tác quản trị nhạy cảm.
8. Kiểm tra topology RMI, hostname và port nếu dùng JMX RMI.

Nếu một connector cho phép client đọc toàn bộ MBeanServer, chỉ loại bỏ vài custom bean không chứng minh hệ thống đã an toàn. Platform MXBeans và MBean của thư viện cũng có thể chứa thông tin cần được bảo vệ.

**Local JMX cũng không phải “không có rủi ro”.** Người dùng có quyền attach hoặc thao tác với JVM local có thể xem dữ liệu chẩn đoán; hãy tuân theo phân quyền hệ điều hành và giảm dữ liệu công bố.

## 18. Theo dõi thay đổi surface area trong CI/CD

Một quy trình hữu ích:

```text
Code change
    |
    +--> Build/test Spring context
    |
    +--> Query MBeanServer
    |
    +--> Collect ObjectNames + MBeanInfo
    |
    +--> Compare approved inventory
    |
    +--> Review additions/removals
    |
    +--> Deploy with monitoring
```

Khi thêm một `@ManagedResource`, management interface hoặc thay đổi annotation, tập attribute/operation có thể thay đổi dù HTTP contract không đổi. Vì vậy cần coi JMX API là một surface có versioning và review.

Các kiểm tra có thể tự động:

- Không xuất hiện ObjectName ngoài allowlist trong domain ứng dụng.
- Không có readable attribute chứa tên đáng ngờ như `Password`, `Secret`, `Token`, `Authorization`.
- MBean thuộc nhóm monitoring không có writable attribute hoặc operation không cho phép.
- Metadata về type/return/parameter không bị thay đổi ngoài dự kiến.
- Không xuất hiện exporter mới do auto-configuration/dependency mà chưa được xem xét.

Kiểm tra tên không đủ chứng minh an toàn: một attribute `Details` cũng có thể chứa secret. Cần review source và data flow để biết giá trị thật được tính từ đâu.

## 19. Một mẫu thiết kế: facade quan sát mỏng

Để tránh export cả service nghiệp vụ, tạo facade quản trị:

```text
PaymentService
   |
   +--> thực hiện payment, refund, gọi gateway
   |
   +--> cập nhật OperationalState
                   |
                   v
             PaymentMonitor
                   |
             @ManagedResource
                   |
             MBeanServer
```

Ví dụ:

```java
import java.util.concurrent.atomic.AtomicLong;

public class PaymentOperationalState {
    private final AtomicLong successful = new AtomicLong();
    private final AtomicLong failed = new AtomicLong();

    public void success() {
        successful.incrementAndGet();
    }

    public void failure() {
        failed.incrementAndGet();
    }

    public long successfulCount() {
        return successful.get();
    }

    public long failedCount() {
        return failed.get();
    }
}
```

Facade:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "company.payment:type=PaymentMonitor"
)
public class PaymentMonitor {
    private final PaymentOperationalState state;

    public PaymentMonitor(PaymentOperationalState state) {
        this.state = state;
    }

    @ManagedAttribute
    public long getSuccessfulPayments() {
        return state.successfulCount();
    }

    @ManagedAttribute
    public long getFailedPayments() {
        return state.failedCount();
    }
}
```

`PaymentMonitor` không biết token hoặc customer record. Nó chỉ trả số liệu tổng hợp. Khi cấu hình exporter rõ ràng, bề mặt JMX này nhỏ hơn nhiều so với export `PaymentService` trực tiếp.

## 20. Quy trình đánh giá một MBean trước khi export

Với mỗi MBean dự kiến, trả lời:

1. **Mục tiêu:** cần giám sát hoặc điều khiển vấn đề gì?
2. **Người dùng:** client nào sẽ truy cập và với quyền gì?
3. **Dữ liệu:** attribute trả thông tin gì, có nhạy cảm không?
4. **Hành vi:** operation/setter có tác dụng phụ nào?
5. **Tần suất:** nếu JConsole/collector gọi getter liên tục có gây tải không?
6. **Lifecycle:** MBean có hoạt động khi STARTING/STOPPING không?
7. **Naming:** ObjectName có duy nhất và ổn định không?
8. **Authorization:** có phân quyền đọc/ghi thích hợp không?
9. **Audit:** có cần ghi lại thao tác quản trị không?
10. **Thay thế:** có thể dùng metric/health endpoint an toàn hơn thay vì JMX operation không?

Nếu không xác định được mục đích vận hành của một attribute/operation, đừng export chỉ vì framework hỗ trợ. Càng ít capability không cần thiết, càng dễ kiểm tra và vận hành.

## 21. Những lỗi thường gặp

### 21.1. Export service trực tiếp và lộ nhiều public method

Dùng assembler phản chiếu rộng có thể đưa nhiều method không intended ra ngoài. Tạo management interface/metadata allowlist hoặc facade riêng.

### 21.2. Bật autodetect trên một codebase lớn mà không inventory

MBean mới có thể xuất hiện khi module hoặc annotation thay đổi. Ghi nhận và review ObjectName/MBeanInfo trong CI và sau deploy.

### 21.3. Coi read-only attribute là không nhạy cảm

Read-only vẫn cho phép đọc. Secret không được xuất qua getter, kể cả khi không có setter.

### 21.4. Dùng wildcard Actuator JMX exposure

Có thể mở rộng endpoint quản trị ngoài ý định khi thêm dependency hoặc nâng cấp. Liệt kê endpoint theo nhu cầu.

### 21.5. Có nhiều exporter nhưng chỉ kiểm tra một exporter

Một exporter khác có thể đăng ký cùng MBean hoặc thêm MBean khác. Kiểm kê toàn bộ ApplicationContext liên quan và MBeanServer thực tế.

### 21.6. Dùng IGNORE_EXISTING để che lỗi naming

`IGNORE_EXISTING` có thể giữ MBean của module cũ, khiến monitoring đọc nhầm nguồn. Sửa ObjectName và ownership thay vì chỉ đổi policy.

### 21.7. Không nghĩ tới notification và operation

Ngay cả khi attribute an toàn, operation có thể thay đổi state; notification userData có thể lộ payload. Kiểm tra đầy đủ `MBeanInfo`, không chỉ getter.

### 21.8. Getter chạy network/database query nặng

Monitoring collector có thể đọc theo chu kỳ cao và gây tải. Export một trạng thái đã được tính sẵn hoặc cache có kiểm soát, với timestamp/staleness phù hợp.

## 22. Bài tập thực hành

**Bài 1 — Explicit allowlist.** Tạo ba Spring bean `QueueMonitor`, `CacheMonitor`, `PaymentService`; cấu hình `MBeanExporter.setBeans` chỉ với hai monitor. Khởi động context và xác nhận `PaymentService` không có ObjectName do exporter này tạo.

**Bài 2 — Method-level allowlist.** Tạo một bean có `getQueueDepth()`, `getApiToken()`, `clearCache()`. Dùng management interface chỉ chứa `getQueueDepth()` và kiểm tra `MBeanInfo`.

**Bài 3 — Annotation review.** Tạo `@ManagedResource` với hai `@ManagedAttribute` an toàn. Thêm một method public mới nhưng không annotate; xác nhận interface quản trị không mở rộng ngoài ý muốn.

**Bài 4 — Actuator exposure.** Trong Spring Boot, cấu hình `management.endpoints.jmx.exposure.include=health,info`, quan sát các MBean Actuator. So sánh khi thêm một endpoint trong môi trường test và ghi lại thay đổi.

**Bài 5 — Inventory.** Viết test lấy `queryNames("company.*:*")`, so sánh với allowlist ObjectName và in metadata attribute/operation nhưng không đọc giá trị.

**Bài 6 — Tách monitoring/admin.** Thiết kế hai interface, một chỉ đọc và một có `pause()`/`resume()`. Giải thích cách phân quyền connector hoặc giải pháp quản trị bên ngoài phải bổ sung để có ranh giới quyền thật.

**Bài 7 — Secret leak.** Viết một MBean không an toàn trả `config.toString()`, xác định đường rò rỉ, rồi sửa thành chỉ báo `CredentialConfigured` và `ServiceState`.

**Bài 8 — Runtime review.** Sau khi bật một dependency mới có MBean tự đăng ký, ghi nhận ObjectName mới và đánh giá liệu nó thuộc ownership ứng dụng, thư viện hay JVM.

## 23. Câu hỏi tự kiểm tra

1. Vì sao số lượng MBean ảnh hưởng management attack surface?
2. Explicit `setBeans(...)` khác autodetection ở điểm nào?
3. Tại sao dùng management interface riêng giúp giảm method exposure?
4. Đặt `@ManagedResource` lên class nghiệp vụ lớn có rủi ro gì?
5. Read-only attribute có thể làm lộ dữ liệu không?
6. Vì sao không nên export `System.getenv()` hoặc toàn bộ config object?
7. Tại sao `RegistrationPolicy` không phải một bộ lọc bảo mật?
8. Platform MXBeans có bị xóa khi bạn ngừng export custom Spring MBean không?
9. Vì sao cần kiểm tra `MBeanInfo` chứ không chỉ xem annotation trong source?
10. Khi nào nên tách MBean monitoring với MBean administration?
11. JMX remote cần những lớp bảo vệ nào ngoài việc giảm số MBean?
12. CI/CD có thể phát hiện JMX surface expansion theo cách nào?

## 24. Ghi nhớ

**Giảm JMX surface area bắt đầu từ quyết định không export những khả năng không cần thiết.** Hãy ưu tiên explicit mapping hoặc annotation/management interface allowlist, chỉ đưa ra trạng thái và số liệu vận hành, tránh secret và operation nguy hiểm, rồi kiểm tra ObjectName/MBeanInfo thực tế.

Kết hợp giới hạn resource/method với bảo vệ connector, network, quyền, audit và kiểm kê sau mỗi deploy. Một bề mặt quản trị nhỏ, có ownership rõ và được kiểm chứng trong runtime sẽ dễ bảo vệ hơn một MBeanServer chứa mọi service chỉ vì export tiện lợi.
