# Kết hợp MBeanExporter với bean configuration hiện có trong Spring Framework

## 1. Mục tiêu học tập

Sau bài học này, bạn có thể:

- Giải thích cách **`MBeanExporter`** đưa các Spring beans đã tồn tại trong `ApplicationContext` ra JMX mà không cần tạo lại business objects.
- Phân biệt **bean definition**, **management interface**, **ObjectName**, **MBeanServer**, **exporter** và **Spring bean lifecycle**.
- Tích hợp exporter vào cấu hình Java `@Configuration`, `@Bean`, component scanning, XML và Spring Boot khi phù hợp.
- Chọn giữa `setBeans(...)` (đăng ký tường minh) và annotation-based autodetection.
- Tránh tạo nhiều MBeanExporter cùng export một bean hoặc đăng ký hai MBeans cùng ObjectName.
- Biết cách cấu hình `MBeanServer`, naming strategy, metadata assembler và registration policy mà vẫn bảo toàn các Spring beans đang dùng.
- Xử lý AOP proxy và lựa chọn một management adapter nhỏ để tránh công bố toàn bộ business service.
- Xác minh kỹ thuật bằng `MBeanServer.isRegistered`, `getAttribute`, `getMBeanInfo` và integration tests.

## 2. Bài toán: ứng dụng đã có beans, nay cần JMX

Một ứng dụng Spring thường đã có hệ thống bean configuration hoàn chỉnh:

```text
ApplicationContext
├── orderService
├── orderRepository
├── paymentClient
├── cacheService
├── taskExecutor
└── orderStatistics
```

Giả sử nhóm vận hành muốn xem `PendingOrders` và `ProcessedOrders` qua JConsole, đồng thời cho phép reset một counter chỉ phục vụ giám sát. Không nên tạo **service thứ hai** chỉ để đăng ký JMX.

Thay vào đó:

```text
                 ApplicationContext
                        |
        +---------------+----------------+
        |                                |
        v                                v
    orderService                   orderStatistics
        |                                |
        +----------------+---------------+
                         |
                         v
                OrderManagement
                         |
                         v
                   MBeanExporter
                         |
                         v
                     MBeanServer
                         |
                         v
             JConsole / JMX client
```

Spring bean `OrderManagement` là adapter để công bố một management contract nhỏ. `MBeanExporter` đăng ký adapter này dưới ObjectName. Business service/repository vẫn dùng cấu hình, dependency injection, transaction và lifecycle đã có.

**Ý tưởng chính:** Tích hợp JMX là một **lớp quản trị bổ sung** trên các beans hiện hữu, không phải một ứng dụng Spring thứ hai hoặc một vòng đời riêng không được kiểm soát.

## 3. Những khái niệm phải tách biệt

| Khái niệm | Nhiệm vụ | Ví dụ |
|---|---|---|
| **Spring bean** | Object do IoC container tạo, inject, quản lý lifecycle | `orderStatistics` |
| **Bean name** | Định danh trong `ApplicationContext` | `orderManagement` |
| **Management interface** | Contract cho JMX attributes/operations | `OrderMonitorMBean` |
| **ObjectName** | Định danh JMX trong `MBeanServer` | `com.example.shop.orders:type=Monitor,name=primary` |
| **MBeanExporter** | Lấy bean và đăng ký vào JMX | `setBeans(...)` |
| **MBeanServer** | Runtime registry và access API | `ManagementFactory.getPlatformMBeanServer()` |
| **JMX client** | Đọc attributes, gọi operations, nhận notifications | JConsole |

Một Spring bean name **không tự động bằng** ObjectName. Có thể dùng bean name để chọn bean export, nhưng định danh JMX phải được tạo theo naming strategy hoặc khai báo tường minh.

```text
Spring:
  bean name = orderManagement

JMX:
  ObjectName = com.example.shop.orders:type=Monitor,name=primary
```

Hai định danh phục vụ hai hệ khác nhau. ObjectName chỉ cần duy nhất trong một MBeanServer; hai JVM độc lập có thể có cùng ObjectName.

## 4. Cách tiếp cận: export bean hiện có hay tạo management adapter?

Có hai cách triển khai phổ biến.

### 4.1. Export trực tiếp một bean hiện có

Nếu bean có management interface rõ và phù hợp, có thể export trực tiếp:

```java
public interface QueueMonitorMBean {
    int getPendingCount();
    void resetStatistics();
}

public class QueueMonitor implements QueueMonitorMBean {
    private int pendingCount;

    @Override
    public int getPendingCount() {
        return pendingCount;
    }

    @Override
    public void resetStatistics() {
        pendingCount = 0;
    }
}
```

Khi đây là một Spring bean, exporter có thể đăng ký nó qua ObjectName.

Ưu điểm: ít wrapper, đơn giản nếu bean chỉ mang trách nhiệm quản trị.

Nhược điểm: nếu bean là một business service lớn, có nhiều AOP advice hoặc public methods, JMX contract có thể bị gắn chặt với implementation nghiệp vụ.

### 4.2. Tạo management adapter dựa trên beans có sẵn

```java
public interface OrderStatisticsService {
    long pendingOrders();
    long processedOrders();
}
```

```java
import org.springframework.stereotype.Component;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;

@Component
@ManagedResource(
    objectName = "com.example.shop.orders:type=Monitor,name=primary",
    description = "Order processing statistics")
public class OrderManagement {

    private final OrderStatisticsService statistics;

    public OrderManagement(OrderStatisticsService statistics) {
        this.statistics = statistics;
    }

    @ManagedAttribute(description = "Current pending orders")
    public long getPendingOrders() {
        return statistics.pendingOrders();
    }

    @ManagedAttribute(description = "Total processed orders")
    public long getProcessedOrders() {
        return statistics.processedOrders();
    }
}
```

Adapter cho phép giữ một **management surface có chủ đích**, không phơi bày repository hoặc service methods khác qua JMX.

**Cảnh báo:** Annotation chỉ khai báo metadata; vẫn cần exporter có hỗ trợ annotation và bean phải nằm trong ApplicationContext.

## 5. Kết hợp MBeanExporter với Java @Configuration

Giả sử dự án đã có một bean `QueueMonitor` hợp chuẩn Standard MBean:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class CoreConfiguration {

    @Bean
    QueueMonitor queueMonitor() {
        return new QueueMonitor();
    }
}
```

Thêm cấu hình exporter riêng, **không tạo lại `QueueMonitor`**:

```java
import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.support.RegistrationPolicy;

@Configuration
public class JmxConfiguration {

    @Bean
    MBeanExporter queueExporter(QueueMonitor queueMonitor) {
        MBeanExporter exporter = new MBeanExporter();

        exporter.setBeans(Map.of(
            "com.example.shop.orders:type=QueueMonitor,name=primary",
            queueMonitor));

        exporter.setRegistrationPolicy(
            RegistrationPolicy.FAIL_ON_EXISTING);

        return exporter;
    }
}
```

Luồng này:

1. Spring tạo `queueMonitor` một lần theo scope mặc định singleton.
2. Dependency injection truyền chính bean đó vào factory method `queueExporter`.
3. `MBeanExporter` dùng bean này để đăng ký JMX.
4. Các component khác vẫn có thể inject `QueueMonitor`.
5. MBeanServer và JMX clients tương tác với MBean đã được đăng ký.

Đừng viết `new QueueMonitor()` một lần trong `@Bean` và một lần nữa trong `setBeans`, vì bạn sẽ quản lý hai object khác nhau với hai state khác nhau.

## 6. Giữ lifecycle của Spring bean

Spring IoC container thường quản lý:

- Constructor injection và `@PostConstruct`.
- `InitializingBean` hoặc custom init methods.
- AOP post-processors.
- Bean scopes.
- `@PreDestroy`, `DisposableBean` hoặc destroy methods.

Exporter không nên trở thành lý do để bypass các cơ chế đó.

Ví dụ cần tránh:

```java
@Bean
MBeanExporter exporter() {
    MBeanExporter exporter = new MBeanExporter();
    exporter.setBeans(Map.of(
        "com.example.shop:type=QueueMonitor,name=main",
        new QueueMonitor()));
    return exporter;
}
```

Ở đây `QueueMonitor` được tạo bằng `new` trong cấu hình exporter, thay vì được inject như một Spring bean quản lý độc lập. Trong nhiều trường hợp sẽ mất các lợi ích cấu hình và lifecycle mong muốn.

Cách phù hợp:

```java
@Bean
MBeanExporter exporter(QueueMonitor monitor) {
    MBeanExporter exporter = new MBeanExporter();
    exporter.setBeans(Map.of(
        "com.example.shop:type=QueueMonitor,name=main",
        monitor));
    return exporter;
}
```

**Chú ý:** Nếu bean scope là prototype hoặc request-scoped, export một object cụ thể có thể không phản ánh kỳ vọng của scope. Với JMX, thường nên có một management adapter singleton giữ reference tới service/proxy phù hợp, hoặc được thiết kế rõ để đại diện cho toàn component.

## 7. MBeanServer: dùng đúng server đã cấu hình

Một ứng dụng có thể có MBeanServer được Spring tìm thấy hoặc cấu hình riêng. `MBeanExporter` có thể sử dụng MBeanServer được inject.

Ví dụ:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class MBeanServerConfiguration {

    @Bean
    MBeanServer mBeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }
}
```

Exporter:

```java
@Bean
MBeanExporter exporter(
        MBeanServer mBeanServer,
        QueueMonitor monitor) {

    MBeanExporter exporter = new MBeanExporter();
    exporter.setServer(mBeanServer);
    exporter.setBeans(Map.of(
        "com.example.shop.orders:type=QueueMonitor,name=primary",
        monitor));
    return exporter;
}
```

Việc dùng platform MBeanServer phù hợp khi muốn MBeans của ứng dụng xuất hiện cùng JVM platform MBeans như `java.lang:type=Memory`. Nhưng không nên tạo thêm server tùy ý nếu JConsole hoặc các exporter khác đang kết nối đến một server khác.

Khi xác minh, dùng **cùng MBeanServer instance** mà exporter sử dụng.

## 8. Config theo interface và proxy: điểm dễ gây lỗi

Trong nhiều ứng dụng, business service có `@Transactional`, `@Cacheable` hoặc security advice, nên object inject thực tế có thể là Spring AOP proxy.

Giả sử:

```java
public interface OrderService {
    long pendingOrders();
}
```

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DefaultOrderService implements OrderService {

    @Override
    @Transactional(readOnly = true)
    public long pendingOrders() {
        return 12;
    }
}
```

Nếu Spring dùng JDK dynamic proxy, object inject qua `OrderService` không nhất thiết có kiểu `DefaultOrderService`.

**Khuyến nghị:** Management adapter nhận interface nghiệp vụ:

```java
@Component
@ManagedResource(
    objectName = "com.example.shop.orders:type=OrderMonitor,name=main")
public class OrderManagement {

    private final OrderService orderService;

    public OrderManagement(OrderService orderService) {
        this.orderService = orderService;
    }

    @ManagedAttribute
    public long getPendingOrders() {
        return orderService.pendingOrders();
    }
}
```

Nhờ đó JMX adapter gọi qua Spring proxy của service, giữ behavior của transaction/security/cache khi cần.

Tuy nhiên, một getter JMX có thể được poll liên tục. Nếu `orderService.pendingOrders()` chạy SQL mỗi lần, nó có thể gây tải DB. Nên ưu tiên snapshot/counter rẻ hoặc thiết kế refresh có kiểm soát.

## 9. Annotated beans và assembler: chọn đúng cơ chế export

Nếu management bean được annotate:

```java
@Component
@ManagedResource(
    objectName = "com.example.shop.catalog:type=Cache,name=products")
public class ProductCacheManagement {

    @ManagedAttribute
    public int getEntryCount() {
        return 42;
    }
}
```

thì bạn cần một exporter/assembler hiểu `@ManagedResource` và `@ManagedAttribute`.

Các thành phần phổ biến:

- `AnnotationJmxAttributeSource`: đọc metadata annotation.
- `MetadataMBeanInfoAssembler`: tạo MBeanInfo từ metadata.
- `MetadataNamingStrategy`: đọc tên từ managed resource metadata.
- `MBeanExporter`: thực hiện export.
- `AnnotationMBeanExporter`: tiện ích phù hợp với annotation-driven export.

**Quan trọng:** Đừng chỉ thêm annotation vào một bean rồi tự tạo `MBeanExporter` dùng mặc định mà kết luận chắc chắn các annotations được xử lý theo ý muốn. Hãy kiểm tra cách exporter được cấu hình trong phiên bản Spring đang sử dụng.

### Cấu hình explicit metadata pipeline

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.naming.MetadataNamingStrategy;

@Configuration
public class AnnotationJmxConfig {

    @Bean
    AnnotationJmxAttributeSource jmxAttributeSource() {
        return new AnnotationJmxAttributeSource();
    }

    @Bean
    MetadataMBeanInfoAssembler jmxAssembler(
            AnnotationJmxAttributeSource source) {
        MetadataMBeanInfoAssembler assembler =
                new MetadataMBeanInfoAssembler();
        assembler.setAttributeSource(source);
        return assembler;
    }

    @Bean
    MetadataNamingStrategy jmxNamingStrategy(
            AnnotationJmxAttributeSource source) {
        MetadataNamingStrategy naming =
                new MetadataNamingStrategy();
        naming.setAttributeSource(source);
        return naming;
    }

    @Bean
    MBeanExporter annotationExporter(
            MetadataMBeanInfoAssembler assembler,
            MetadataNamingStrategy naming) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setAssembler(assembler);
        exporter.setNamingStrategy(naming);
        exporter.setAutodetectModeName("AUTODETECT_ASSEMBLER");
        return exporter;
    }
}
```

Cấu hình trên minh họa cách nối pipeline để chọn các managed resources. Cần kiểm tra API cụ thể theo Spring version; nếu ứng dụng đã có exporter annotation-driven, **không tạo exporter thứ hai** chỉ vì nhìn thấy ví dụ này.

## 10. Export tường minh và autodetection: tránh trùng nhau

Hai con đường thường được dùng:

### Cách A: explicit mapping

```java
exporter.setBeans(Map.of(
    "com.example.shop.orders:type=Queue,name=outbox",
    orderManagement));
```

Phù hợp khi số resource ít, cần allowlist rõ và naming do config quyết định.

### Cách B: autodetection

```java
exporter.setAssembler(metadataAssembler);
exporter.setAutodetectModeName("AUTODETECT_ASSEMBLER");
```

Phù hợp khi các modules có annotation JMX nhất quán và muốn exporter tự nhận diện.

Nếu vừa có explicit mapping vừa bật autodetection, phải hiểu liệu cùng bean có bị chọn hai lần hay ObjectName có bị tạo trùng trong phiên bản/cấu hình đó hay không. Tránh dùng hai đường đăng ký song song cho cùng MBean.

**Nguyên tắc ownership:** Mỗi `ObjectName` nên có **một registration owner** và một nguồn metadata quản trị chính.

## 11. Không nhầm MBeanExporter với MBeanProxyFactoryBean

Trong Spring JMX có hai chiều:

```text
SERVER SIDE:
Spring bean -> MBeanExporter -> MBeanServer

CLIENT SIDE:
Spring bean proxy -> MBeanProxyFactoryBean -> MBeanServerConnection
```

`MBeanExporter` **công bố** bean.

`MBeanProxyFactoryBean` **tạo client proxy** để gọi một MBean đã đăng ký.

Nếu cùng ứng dụng cần gọi MBean local bằng Java interface, có thể dùng client proxy, nhưng không cần tạo client proxy chỉ để export một bean. Hai công cụ khác nhiệm vụ.

Một số ứng dụng có service Java trực tiếp đã được inject, nên không cần đi qua JMX proxy để gọi nghiệp vụ nội bộ. Dùng JMX proxy khi bạn muốn thao tác với một **management contract** qua MBeanServer và ObjectName, không thay thế dependency injection bình thường.

## 12. Registration policy: đừng che xung đột cấu hình

Khi hai exporters hoặc hai resources cùng đăng ký ObjectName, có thể gặp `InstanceAlreadyExistsException`. Spring hỗ trợ `RegistrationPolicy` để kiểm soát xung đột.

| Policy | Khi ObjectName đã tồn tại | Rủi ro/ưu điểm |
|---|---|---|
| `FAIL_ON_EXISTING` | Báo conflict | Dễ phát hiện cấu hình sai |
| `IGNORE_EXISTING` | Giữ MBean hiện có, không thay | Bean mới có thể không được export như dự kiến |
| `REPLACE_EXISTING` | Thay MBean đã có | Có thể gây gián đoạn và mất contract cũ |

Trong cấu hình tích hợp ban đầu, **`FAIL_ON_EXISTING`** thường là lựa chọn an toàn về tính dự đoán vì giúp phát hiện việc duplicate export.

Không chuyển sang `IGNORE_EXISTING` chỉ để làm app khởi động được; có thể JConsole vẫn đọc MBean của exporter khác. Không chọn `REPLACE_EXISTING` chỉ để “thắng” xung đột, vì có thể thay MBean của thư viện/container mà ứng dụng không sở hữu.

## 13. Spring Boot: kiểm tra auto-configuration trước khi thêm exporter

Trong Spring Boot, có những phần tích hợp JMX/Actuator tùy cấu hình và dependency:

- JVM platform MBeans luôn có thể được truy cập qua platform MBeanServer.
- Custom `@ManagedResource` beans cần cơ chế export phù hợp.
- Spring Boot Actuator endpoints có thể expose qua JMX theo management configuration.
- Các thư viện có thể tự đăng ký MBeans, chẳng hạn một connection pool.

Vì vậy, trước khi tự tạo `MBeanExporter`, hãy xác nhận:

1. Ứng dụng đã có exporter từ auto-configuration chưa?
2. `spring.jmx.enabled` hoặc các thuộc tính JMX tương đương có được bật theo Spring Boot version đang dùng không?
3. Có bean tên `mbeanExporter` hoặc exporter tùy chỉnh nào không?
4. Có Actuator JMX exposure sử dụng cùng MBeanServer không?
5. Domain/ObjectName custom có thể trùng với Spring/Actuator hoặc thư viện không?

Cấu hình minh họa:

```yaml
spring:
  jmx:
    enabled: true

management:
  endpoints:
    jmx:
      exposure:
        include: health,info
```

Cấu hình cụ thể phụ thuộc Spring Boot version và dependency. Không coi ví dụ YAML này là yêu cầu bắt buộc cho mọi ứng dụng Spring Framework thuần.

Khi Boot đã cung cấp một exporter hợp lệ, nên tận dụng cấu hình đó hoặc cấu hình lại owner hiện có, thay vì tạo thêm exporter cùng phạm vi.

## 14. Tổ chức configuration theo module

Trong ứng dụng nhiều module, có thể tách:

```text
com.example.shop
  ├── orders
  │   ├── OrdersConfiguration.java
  │   └── OrderManagement.java
  ├── catalog
  │   ├── CatalogConfiguration.java
  │   └── CacheManagement.java
  └── jmx
      └── JmxConfiguration.java
```

Cách tổ chức:

- Business configurations tạo services/repositories như trước.
- Management adapters inject các service đó.
- Một JMX configuration ở cấp ứng dụng xác định exporter, naming, policy và MBeanServer.
- Nếu module cần khai báo bean JMX riêng, nó cung cấp adapter/metadata, không tự động tạo exporter thứ hai nếu app đã có exporter chung.

Ví dụ:

```java
@Configuration
public class OrderModuleConfiguration {
    @Bean
    OrderStatistics orderStatistics() {
        return new OrderStatistics();
    }
}

@Configuration
public class MonitoringConfiguration {
    @Bean
    OrderManagement orderManagement(OrderStatistics statistics) {
        return new OrderManagement(statistics);
    }
}
```

Ví dụ này giả định `OrderManagement` có constructor nhận `OrderStatistics` phù hợp. Nếu đã có `@Component` trên `OrderManagement` và component scanning, không khai báo thêm `@Bean` cho cùng nhiệm vụ một cách vô tình.

Quy tắc thực hành: **mỗi bean một nguồn tạo chính** (component scanning hoặc `@Bean` tường minh, trừ khi chủ đích có nhiều instances); **mỗi ObjectName một exporter owner**.

## 15. Điều gì xảy ra với singleton, prototype và scoped proxy?

### Singleton

Spring singleton là scope mặc định và thường phù hợp nhất cho MBean quản trị. Exporter đăng ký instance được quản lý trong ApplicationContext.

### Prototype

Một prototype bean được tạo theo mỗi yêu cầu lấy bean. Nếu exporter nhận một prototype instance cụ thể, JMX client chỉ tương tác với instance được đăng ký, không đại diện cho mọi prototype objects khác. Điều này có thể làm số liệu quan sát sai kỳ vọng.

### Request/session scope

Một request-scoped bean không phải lựa chọn tự nhiên cho MBean sống suốt JVM. Nếu dùng scoped proxy, lời gọi JMX từ thread không có request context có thể thất bại.

### Management adapter singleton

Thường an toàn hơn để quản trị tổng thể: adapter singleton đọc counters/snapshots ở các services hoặc metrics registry. Nhưng vẫn cần định nghĩa rõ dữ liệu thuộc instance nào, đặc biệt khi hệ thống có nhiều replicas.

## 16. Giới hạn của @ManagedAttribute getter

Một MBean được export thành công không có nghĩa các getters đều an toàn khi polling.

Ví dụ cần xem xét:

```java
@ManagedAttribute
public long getPendingOrders() {
    return repository.countPendingOrders();
}
```

JConsole hoặc exporter có thể gọi attribute nhiều lần, tạo SQL queries lặp lại. Nếu DB đang nghẽn, chính monitoring gây thêm tải.

Cách ít rủi ro:

```java
@ManagedAttribute
public long getPendingOrders() {
    return statistics.getPendingSnapshot();
}
```

Những giá trị được refresh trong background nên có timestamp/freshness metadata, giúp người vận hành biết khi nào dữ liệu đã cũ.

Đối với operations thay đổi trạng thái như `clearCache`, `pauseConsumers`, `resetStatistics`, phải cân nhắc authorization, audit và side effects. `@ManagedOperation` không mặc nhiên áp dụng security role nghiệp vụ.

## 17. Xác minh ObjectName được đăng ký

Sau khi context khởi động, có thể kiểm tra MBean qua MBeanServer:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
        ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
        "com.example.shop.orders:type=QueueMonitor,name=primary");

boolean exists = server.isRegistered(name);
System.out.println("Registered: " + exists);
```

Nếu exporter dùng một MBeanServer khác, phải dùng đúng instance đó. Việc client tìm ObjectName trên một server khác sẽ cho kết quả `false` dù registration ở server chính đã thành công.

Đọc attribute:

```java
if (server.isRegistered(name)) {
    Object pending =
            server.getAttribute(name, "PendingCount");
    System.out.println("Pending: " + pending);
}
```

Đây là kiểm tra end-to-end của JMX getter, không chỉ xác nhận Spring bean tồn tại.

## 18. Kiểm tra contract qua MBeanInfo

Cách tin cậy để xem điều client nhận được:

```java
import javax.management.MBeanInfo;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanOperationInfo;

MBeanInfo info = server.getMBeanInfo(name);

for (MBeanAttributeInfo attr : info.getAttributes()) {
    System.out.printf("ATTRIBUTE %s type=%s readable=%s%n",
            attr.getName(), attr.getType(), attr.isReadable());
}

for (MBeanOperationInfo op : info.getOperations()) {
    System.out.println("OPERATION " + op.getName());
}
```

Kiểm tra:

- `PendingCount` có đúng tên và kiểu dữ liệu?
- Read-only/writeable semantics có đúng?
- Những operation nội bộ có vô tình bị expose?
- ObjectName có theo naming convention?
- Attributes từ annotation có được assembler xử lý?
- Có registration conflict hoặc duplicate owner không?

MBeanInfo là **contract mà client JMX quan sát**, vì vậy có giá trị hơn việc chỉ nhìn annotation trên class.

## 19. Một integration test tối thiểu

Khi ứng dụng có Spring Test/JUnit 5, có thể khởi động context chỉ gồm core bean và exporter.

Ví dụ test định hướng:

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

import javax.management.MBeanServer;
import javax.management.ObjectName;

class JmxExportIntegrationTest {

    private final MBeanServer mbeanServer;
    // Trong test thực tế inject MBeanServer và Spring context.

    JmxExportIntegrationTest(MBeanServer mbeanServer) {
        this.mbeanServer = mbeanServer;
    }

    @Test
    void exportsExpectedQueueMonitor() throws Exception {
        ObjectName name = new ObjectName(
                "com.example.shop.orders:type=QueueMonitor,name=primary");

        assertTrue(mbeanServer.isRegistered(name));

        Object pending = mbeanServer.getAttribute(name, "PendingCount");
        assertNotNull(pending);
    }
}
```

Đây là **mẫu ý tưởng**. Với JUnit 5 và Spring Test, cần thực hiện constructor injection đúng cơ chế test context (ví dụ `@SpringJUnitConfig` và cấu hình autowiring) hoặc dùng field injection rõ ràng. Đoạn minh họa không phải một class test standalone tự chạy nếu chưa có test configuration.

Nên dùng một MBeanServer test riêng để không ảnh hưởng các tests khác trong cùng JVM. Cleanup registration khi đóng context để tránh xung đột giữa các test suites.

### Những assertion nên có

1. MBean mong muốn có mặt.
2. MBean không mong muốn không bị export.
3. Attribute có đúng type/value.
4. Operation surface đúng và không vô tình expose internal methods.
5. Exporter không đăng ký trùng.
6. Context shutdown loại bỏ registration thuộc owner này.
7. AOP proxy được xử lý đúng nếu service có transaction/caching.

## 20. Các vấn đề lifecycle khi shutdown và restart context

`MBeanExporter` có thể quản lý unregister những MBeans mà nó đăng ký khi context dừng. Nếu nhiều contexts/exporters cùng dùng MBeanServer và ObjectName, lifecycle trở nên khó đoán:

```text
Context A register -> MBean X
Context B register -> conflict/ignore/replace
Context A close    -> ai sở hữu registration hiện tại?
```

Vì thế:

- Không dùng registration policy để che ownership không rõ.
- Dùng một exporter owner cho từng ObjectName.
- Test đóng/mở context.
- Không manually unregister MBean do component khác quản lý.
- Nếu có một container tạo MBeans hệ thống, tôn trọng lifecycle của container.
- Trong hot reload/devtools, kiểm tra các registration tồn dư và cách context cleanup.

Nếu cần thay implementation mà giữ ObjectName, hãy thiết kế một management facade ổn định hoặc migration có kiểm soát thay vì mặc định dùng `REPLACE_EXISTING`.

## 21. Khi kết hợp exporter với cấu hình XML có sẵn

Spring Framework vẫn hỗ trợ XML bean definitions ở những hệ thống cũ. Khái niệm tương tự Java configuration: giữ bean definitions hiện có và thêm exporter tham chiếu đến beans bằng tên.

Ví dụ:

```xml
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
         http://www.springframework.org/schema/beans
         https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="queueMonitor" class="com.example.shop.QueueMonitor"/>

    <bean id="exporter"
          class="org.springframework.jmx.export.MBeanExporter">
        <property name="beans">
            <map>
                <entry key="com.example.shop.orders:type=QueueMonitor,name=primary"
                       value-ref="queueMonitor"/>
            </map>
        </property>
    </bean>
</beans>
```

Trong XML, `value-ref="queueMonitor"` là tham chiếu tới Spring bean đã khai báo, không tạo object mới.

Nếu dự án đã dùng namespace `context:mbean-export` hoặc cấu hình annotation exporter tương tự, cần hiểu scope hiện tại trước khi khai báo thêm `MBeanExporter` thủ công, tránh hai registration owners.

## 22. Lựa chọn giữa Java configuration và XML

| Tiêu chí | Java `@Configuration` | XML bean definitions |
|---|---|---|
| Kiểu khai báo | Type-safe Java methods và annotations | XML elements, bean references |
| Tái sử dụng beans | Constructor/parameter injection | `ref`/`value-ref` |
| Đặt ObjectName | Map key, naming strategy, annotation | Map key, bean properties, namespace |
| Test | Spring context với config classes | Spring context với XML resources |
| Rủi ro | Tạo bean mới trong exporter hoặc trùng `@Component` | Sai bean id, thêm exporter trùng |
| Khả năng dùng chung | Có thể cùng tồn tại trong một context | Có thể import/compose với Java config |

Chọn theo kiến trúc hiện tại của dự án; không nhất thiết chuyển toàn bộ XML sang Java chỉ để thêm JMX. Quan trọng hơn là **tạo bean một lần và có export owner duy nhất**.

## 23. Những sai lầm thường gặp

| Vấn đề | Nguyên nhân | Cách xử lý |
|---|---|---|
| MBean đọc state khác ứng dụng | Exporter tự `new` object khác bean đang dùng | Inject Spring-managed instance |
| `InstanceAlreadyExistsException` | Hai exporters/beans dùng cùng ObjectName | Một owner, sửa naming hoặc configuration |
| Annotation không xuất hiện | Exporter thiếu annotation assembler/source | Cấu hình đúng metadata pipeline |
| `NotCompliantMBeanException` | Bean/proxy không thỏa MBean contract | Dùng Standard MBean, MXBean hoặc adapter phù hợp |
| Getter query DB mỗi lần | Attribute đọc trực tiếp repository | Dùng counter/snapshot nhẹ |
| MBean không thấy trong JConsole | Sai MBeanServer hoặc chưa export | Kiểm tra server, ObjectName, startup logs |
| ObjectName sai | Bean name bị nhầm với ObjectName | Naming strategy hoặc mapping tường minh |
| Actuator và custom exporter xung đột | Auto-configuration cộng exporter thủ công | Điều chỉnh một registration owner |
| Scope không phù hợp | Prototype/request bean bị export | Dùng singleton adapter |
| Test bị ảnh hưởng lẫn nhau | Các contexts dùng chung platform MBeanServer | Test server riêng và cleanup |

## 24. Một quy trình tích hợp có kiểm soát

### Bước 1: Xác định nhu cầu quản trị

Liệt kê attributes/operations người vận hành thật sự cần. Không export toàn bộ services/repositories.

### Bước 2: Chọn đối tượng quản trị

- Nếu bean hiện có là Standard/MXBean hợp lệ và API nhỏ: export trực tiếp.
- Nếu business bean phức tạp/AOP nhiều: tạo management adapter singleton.

### Bước 3: Chọn metadata source

- Standard MBean interface.
- MXBean interface.
- Annotation-driven `@Managed...` và assembler.

Không dựa vào việc nhiều nguồn sẽ tự hợp nhất nhất quán.

### Bước 4: Chọn exporter và naming

Một exporter owner và ObjectName theo convention:

```text
com.example.shop.orders:type=OrderMonitor,name=primary
```

### Bước 5: Liên kết beans hiện hữu

Dùng constructor injection hoặc `value-ref`, không tạo object nghiệp vụ mới trong exporter.

### Bước 6: Cấu hình registration policy

Ưu tiên phát hiện conflict trong môi trường test/staging; chỉ dùng ignore/replace khi có lý do và quản lý lifecycle rõ.

### Bước 7: Xác minh runtime

Đọc `MBeanServer`, `MBeanInfo`, attributes và operation visibility. Test cả trường hợp không export nhầm.

### Bước 8: Kiểm tra an toàn

Giới hạn JMX remote access, kiểm soát operation có side effects, tránh secrets trong ObjectName/attributes và đảm bảo getters có chi phí thấp.

### Bước 9: Kiểm tra shutdown/restart

Đảm bảo exporter cleanup registrations thuộc owner, không xóa MBeans của bên khác.

## 25. Bài tập thực hành

### Bài tập 1 — Không tạo bean thứ hai

Một dự án có:

```java
@Bean
QueueMonitor queueMonitor() {
    return new QueueMonitor();
}
```

Hãy viết `@Bean MBeanExporter` nhận `QueueMonitor` làm parameter và export dưới ObjectName `com.example.shop:type=QueueMonitor,name=main`. Giải thích vì sao `new QueueMonitor()` bên trong exporter là sai đối với trạng thái được chia sẻ.

### Bài tập 2 — Chọn adapter hay export trực tiếp

Service `OrderServiceImpl` có `@Transactional`, nhiều public methods và truy cập database. Cần expose `PendingOrders` cùng `LastProcessingErrorCode`.

Hãy thiết kế `OrderManagement` singleton có hai getters nhỏ, đọc snapshot/counter đã được duy trì bởi service. Giải thích vì sao không export toàn bộ `OrderServiceImpl`.

### Bài tập 3 — Đọc metadata

Đăng ký `QueueMonitor`, sau đó dùng `MBeanServer.getMBeanInfo` in tất cả attributes/operations. Xác nhận `PendingCount` được expose như read-only và internal API không xuất hiện.

### Bài tập 4 — Annotation-aware configuration

Một `@Component` có `@ManagedResource` và `@ManagedAttribute`, nhưng JConsole không thấy MBean. Kiểm tra các giả thuyết theo thứ tự: bean có nằm trong context không; exporter có chạy không; assembler có hiểu annotation không; naming strategy có chọn ObjectName đúng không; MBeanServer có đúng không.

### Bài tập 5 — Test trùng exporter

Cố tình khai báo hai exporters cho cùng `ObjectName` trong test context. Với `FAIL_ON_EXISTING`, quan sát conflict. Sau đó sửa kiến trúc thành một exporter owner, không dùng `IGNORE_EXISTING` để che lỗi.

### Bài tập 6 — Chuyển cấu hình XML

Cho một XML đã khai báo bean `queueMonitor`. Thêm `MBeanExporter` dùng `value-ref` tới bean hiện có. Đọc attribute bằng JConsole hoặc Java client, xác minh dữ liệu là từ đúng instance.

## 26. Câu hỏi tự kiểm tra

**1. Vì sao không nên tạo lại một service bằng `new` trong cấu hình MBeanExporter?**

Vì sẽ có object khác với bean đang được nghiệp vụ sử dụng, dẫn đến state và lifecycle không nhất quán.

**2. Một bean có `@ManagedResource` có tự xuất hiện trong JConsole không?**

Không. Nó phải được Spring quản lý và export qua cơ chế có hỗ trợ annotation với MBeanServer phù hợp.

**3. `MBeanExporter` và `MBeanProxyFactoryBean` làm cùng việc không?**

Không. Exporter đăng ký MBean; proxy factory tạo client proxy để gọi MBean đã đăng ký.

**4. Spring bean name có phải ObjectName không?**

Không. ObjectName là định danh JMX và cần được quyết định qua mapping/naming strategy/metadata.

**5. Khi nào nên tạo management adapter?**

Khi business service có nhiều API nội bộ, nhiều AOP advice hoặc cần contract JMX tối thiểu, ổn định.

**6. Tại sao không dùng `IGNORE_EXISTING` mặc định để né lỗi duplicate?**

Vì có thể bỏ qua bean mới, để lại MBean cũ không đúng contract và che lỗi ownership.

**7. Có cần dùng đúng MBeanServer khi verify không?**

Có. Đọc server khác có thể báo MBean không tồn tại dù exporter đăng ký thành công trên server mục tiêu.

## 27. Ghi nhớ

- Kết hợp exporter với Spring configuration là **tái sử dụng beans hiện có**, không tạo implementation thứ hai chỉ để đăng ký JMX.
- MBeanExporter lấy Spring bean và đưa management contract ra MBeanServer dưới ObjectName.
- Chọn một con đường metadata rõ: Standard MBean, MXBean hoặc annotation-driven assembler.
- Spring bean name và JMX ObjectName là hai định danh khác nhau; giữ naming convention ổn định.
- Mỗi ObjectName nên có một registration owner; tránh explicit export và autodetection chồng nhau.
- Management adapter singleton giúp giới hạn API quản trị và duy trì service AOP/lifecycle.
- Với Spring Boot, kiểm tra auto-configuration trước khi thêm exporter thủ công.
- Xác minh bằng `MBeanInfo`, `getAttribute`, và tests thực sự qua MBeanServer; đừng chỉ kiểm tra annotation trong source.
- Cân nhắc security, chi phí getter, scope, shutdown và tương thích với công cụ giám sát.

## 28. Tài liệu tham khảo

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework Javadoc — `MBeanExporter`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Spring Framework Javadoc — `AnnotationMBeanExporter`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/AnnotationMBeanExporter.html
- Spring Framework Reference — Exporting MBeans: https://docs.spring.io/spring-framework/reference/integration/jmx/exporting.html
- Java SE 21 — `MBeanServer`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
