# InterfaceBasedMBeanInfoAssembler trong Spring Framework JMX

## 1. Vấn đề: không phải mọi phương thức của bean đều nên công bố

Trong một ứng dụng Spring, một service thường có nhiều phương thức: xử lý nghiệp vụ, kiểm tra trạng thái, truy cập repository, làm mới cache, cập nhật cấu hình, hoặc thao tác nội bộ phục vụ kiểm thử. Khi xuất service thành MBean, người vận hành chỉ nên nhìn thấy **những thuộc tính và thao tác được chọn cho mục đích quản trị**.

Ví dụ một service có:

```java
public class OrderService {
    public long getProcessedOrders() { /* ... */ }
    public boolean isHealthy() { /* ... */ }
    public void resetStatistics() { /* ... */ }

    public void deleteAllOrders() { /* ... */ }
    public void processPayment(String cardToken) { /* ... */ }
    public String getInternalSecret() { /* ... */ }
}
```

Nếu cơ chế export công bố quá rộng, một client JMX có thể gọi những method không có lý do hiện diện trên mặt phẳng quản trị. Vấn đề không chỉ là giao diện JConsole rối; việc export thừa có thể làm lộ dữ liệu, thay đổi trạng thái hoặc cung cấp một đường gọi bỏ qua API nghiệp vụ.

**`InterfaceBasedMBeanInfoAssembler`** trong Spring JMX cho phép dùng **management interface** làm nguồn xác định tập method được công bố. Spring xét những method có trong interface chỉ định để xây dựng `ModelMBeanInfo`; từ đó các accessor hợp lệ được nhận dạng thành attribute và các method còn lại có thể được xuất thành operation.

Điểm cốt lõi là **allowlist theo hợp đồng interface**: thêm method vào implementation không tự động có nghĩa nó được đưa ra JMX.

## 2. Vị trí của assembler trong kiến trúc export

Spring JMX gồm các thành phần có trách nhiệm khác nhau:

```text
                  Spring ApplicationContext
                            |
                 Bean nghiệp vụ/monitor
                            |
                     MBeanExporter
                     /     |      \
                    /      |       \
             assembler    naming   MBeanServer
                 |       strategy     |
                 v           |        v
     InterfaceBasedMBeanInfoAssembler
                 |
         management interface
                 |
       chọn attribute / operation
                 |
             ModelMBeanInfo
                 |
                 +---------> Spring ModelMBean
                                    |
                              đăng ký ObjectName
                                    |
                              JMX client
```

- **`MBeanExporter`** quản lý việc export bean, lựa chọn resource, vòng đời đăng ký và tương tác với `MBeanServer`.
- **`MBeanInfoAssembler`** xây dựng metadata quản trị: thuộc tính và thao tác nào được công bố.
- **`InterfaceBasedMBeanInfoAssembler`** là assembler dùng interface được cấu hình để chọn method.
- **`ObjectNamingStrategy`** xác định tên đăng ký MBean; nó không quyết định method nào được phép export.
- **`MBeanServer`** chứa MBean được đăng ký và phục vụ yêu cầu của client.
- **`MBeanInfo` / `ModelMBeanInfo`** mô tả giao diện quản trị mà client có thể khám phá.

Đây là cơ chế **Spring ModelMBean export**. Nó có liên hệ về ý tưởng với Standard MBean của JDK, nhưng không nên đồng nhất hai con đường cấu hình. Standard MBean mặc định dùng convention `SomethingMBean`; Spring assembler có thể chọn một interface được chỉ rõ mà không yêu cầu implementation tuân theo cùng quy ước tên.

## 3. Vì sao management interface là ranh giới tốt?

Một interface riêng có thể thể hiện chính xác những gì người vận hành cần:

```java
public interface OrderManagement {
    long getProcessedOrders();
    boolean isHealthy();
    void resetStatistics();
}
```

Implementation có thể có nhiều method khác:

```java
public class OrderService implements OrderManagement {
    @Override
    public long getProcessedOrders() { /* ... */ }

    @Override
    public boolean isHealthy() { /* ... */ }

    @Override
    public void resetStatistics() { /* ... */ }

    public void processOrder(Order order) { /* ... */ }

    public String getInternalSecret() { /* ... */ }
}
```

Khi assembler được cấu hình dùng `OrderManagement`, JMX metadata tập trung vào `getProcessedOrders()`, `isHealthy()` và `resetStatistics()`. Hai method `processOrder(...)` và `getInternalSecret()` không thuộc interface nên không được chọn.

Cách này có những lợi ích:

1. **Rõ phạm vi:** reviewer chỉ cần nhìn interface để biết khả năng quản trị dự kiến.
2. **Ổn định:** thay đổi implementation không nhất thiết thay đổi JMX API.
3. **Tách mục tiêu:** business service có thể chứa nhiều method mà không mở rộng bề mặt quản trị.
4. **Dễ kiểm kê:** tên method và return type trong interface tạo một hợp đồng được kiểm soát.
5. **Có thể thiết kế riêng:** interface quản trị khác interface nghiệp vụ, không cần chứa mọi operation kinh doanh.

Tuy vậy, interface chỉ là **ranh giới công bố method**, không thay thế xác thực, phân quyền hay validation. Nếu interface cố tình chứa `deleteAllOrders()`, assembler vẫn có thể công bố operation đó; trách nhiệm xem xét tính phù hợp vẫn nằm ở người thiết kế.

## 4. Cách nhận diện attribute và operation

Assembler không chỉ đưa toàn bộ tên method vào một danh sách. Với các accessor theo JavaBean convention, Spring JMX có thể mô tả attribute:

```java
public interface CacheManagement {
    long getHitCount();
    boolean isEnabled();
    int getMaxEntries();
    void setMaxEntries(int value);
    void clearCache();
}
```

Hợp đồng dự kiến:

| Method | Biểu diễn JMX | Khả năng |
|---|---|---|
| `getHitCount()` | Attribute `HitCount` | Read-only |
| `isEnabled()` | Attribute `Enabled` | Read-only |
| `getMaxEntries()` | Attribute `MaxEntries` | Read-write khi có setter tương ứng |
| `setMaxEntries(int)` | Setter của `MaxEntries` | Cho phép ghi |
| `clearCache()` | Operation `clearCache` | Gọi hành động |

Một attribute đọc–ghi cần getter/setter khớp tên và kiểu. Không nên trông chờ assembler suy đoán hai method mang tên khác nhau là cùng một property.

Dữ liệu trả về cũng là phần của hợp đồng. Nếu `getHitCount()` đổi từ `long` sang `String`, client JMX và các monitoring script đọc attribute có thể bị ảnh hưởng. Cần coi interface quản trị như một API có tính tương thích phiên bản.

## 5. Ví dụ hoàn chỉnh: chọn method qua InterfaceBasedMBeanInfoAssembler

Ví dụ dưới đây trình bày một Spring Framework application context độc lập. Ta có một service thực thi, một management interface và cấu hình `MBeanExporter` để chỉ xuất những method được chọn.

### 5.1. Management interface

```java
// JobManagement.java
public interface JobManagement {
    long getCompletedJobs();
    int getConcurrencyLimit();
    void setConcurrencyLimit(int limit);
    void resetStatistics();
}
```

Giao diện trên chỉ có bốn method; `CompletedJobs` là read-only, `ConcurrencyLimit` là read-write, còn `resetStatistics()` là operation.

### 5.2. Bean triển khai

```java
// JobService.java
import java.util.concurrent.atomic.AtomicLong;

public class JobService implements JobManagement {
    private final AtomicLong completedJobs = new AtomicLong();
    private volatile int concurrencyLimit = 4;

    public void recordCompletedJob() {
        completedJobs.incrementAndGet();
    }

    @Override
    public long getCompletedJobs() {
        return completedJobs.get();
    }

    @Override
    public int getConcurrencyLimit() {
        return concurrencyLimit;
    }

    @Override
    public void setConcurrencyLimit(int limit) {
        if (limit < 1 || limit > 32) {
            throw new IllegalArgumentException(
                "Concurrency limit must be between 1 and 32"
            );
        }
        concurrencyLimit = limit;
    }

    @Override
    public void resetStatistics() {
        completedJobs.set(0L);
    }

    // Method nội bộ, không thuộc management interface.
    public String getInternalCredential() {
        return "example-only-internal-value";
    }

    // Method nghiệp vụ, không xuất qua JMX.
    public void executeJob(String jobId) {
        recordCompletedJob();
    }
}
```

Chuỗi trong `getInternalCredential()` chỉ dùng để minh họa một method không được công bố; ứng dụng thật phải lưu secret bằng phương thức quản lý bí mật phù hợp, không hard-code credential trong source.

### 5.3. Cấu hình Spring exporter và assembler

```java
// JmxConfig.java
import java.util.Map;
import javax.management.MBeanServer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.assembler.InterfaceBasedMBeanInfoAssembler;
import org.springframework.jmx.support.MBeanServerFactoryBean;

@Configuration
public class JmxConfig {

    @Bean
    public JobService jobService() {
        return new JobService();
    }

    @Bean
    public MBeanServerFactoryBean mbeanServer() {
        MBeanServerFactoryBean factory = new MBeanServerFactoryBean();
        factory.setLocateExistingServerIfPossible(true);
        return factory;
    }

    @Bean
    public InterfaceBasedMBeanInfoAssembler interfaceAssembler() {
        InterfaceBasedMBeanInfoAssembler assembler =
            new InterfaceBasedMBeanInfoAssembler();
        assembler.setManagedInterfaces(JobManagement.class);
        return assembler;
    }

    @Bean
    public MBeanExporter mbeanExporter(
            JobService jobService,
            InterfaceBasedMBeanInfoAssembler assembler,
            MBeanServer mbeanServer) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(mbeanServer);
        exporter.setAssembler(assembler);
        exporter.setBeans(Map.of(
            "demo.jobs:type=JobService,name=main",
            jobService
        ));
        return exporter;
    }
}
```

Ở cấu hình trên:

- `setManagedInterfaces(JobManagement.class)` nói assembler chỉ lấy hợp đồng từ interface quản trị đã chọn.
- `setBeans(...)` chỉ rõ đối tượng và ObjectName để export.
- `setAssembler(...)` gắn chiến lược xây dựng metadata vào exporter.
- `MBeanServer` là registry để JConsole hoặc client truy vấn.
- `MBeanServerFactoryBean` giúp cấu hình MBeanServer trong Spring; có thể dùng platform server theo yêu cầu ứng dụng.

**Lưu ý cấu hình:** ứng dụng thật có thể đã có `MBeanServer` do Spring Boot hoặc hạ tầng cung cấp. Khi đó nên sử dụng server đó và tránh tạo nhiều registry gây khó tìm MBean. Ví dụ này minh họa mối quan hệ giữa các bean trong Spring; hãy chọn một chính sách MBeanServer nhất quán với môi trường.

### 5.4. Khởi chạy context và đọc metadata

```java
// Main.java
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {

    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(JmxConfig.class)) {

            MBeanServer server = context.getBean(MBeanServer.class);

            ObjectName name = new ObjectName(
                "demo.jobs:type=JobService,name=main"
            );

            MBeanInfo info = server.getMBeanInfo(name);

            for (MBeanAttributeInfo attribute : info.getAttributes()) {
                System.out.printf(
                    "Attribute %s: type=%s, read=%s, write=%s%n",
                    attribute.getName(),
                    attribute.getType(),
                    attribute.isReadable(),
                    attribute.isWritable()
                );
            }

            for (MBeanOperationInfo operation : info.getOperations()) {
                System.out.println("Operation " + operation.getName());
            }

            Thread.sleep(60_000L);
        }
    }
}
```

Mục tiêu khi đọc metadata là nhận ra `CompletedJobs`, `ConcurrencyLimit`, `resetStatistics` và không thấy `getInternalCredential` được công bố. Thứ tự liệt kê metadata không nên được dùng như hợp đồng.

Để JConsole kết nối local thuận tiện, MBean nên được đăng ký trong platform MBeanServer của JVM. Trong môi trường sử dụng server riêng, JConsole attach local có thể chỉ nhìn thấy platform server mặc định; cần xác định server mà exporter thực sự đăng ký.

## 6. Tại sao nên dùng management interface riêng?

Có hai chiến lược thiết kế khác nhau:

**A. Service implement trực tiếp management interface**

```java
public class QueueService implements QueueManagement {
    // Nghiệp vụ + các method quản trị
}
```

Ưu điểm là ít lớp, thuận tiện với service nhỏ. Nhược điểm là interface quản trị gắn vào class nghiệp vụ và có thể bị mở rộng do nhu cầu khác.

**B. Management facade chuyên biệt**

```java
public class QueueManagementFacade implements QueueManagement {
    private final QueueService service;

    public QueueManagementFacade(QueueService service) {
        this.service = service;
    }

    @Override
    public int getQueueDepth() {
        return service.currentQueueDepth();
    }

    @Override
    public void pause() {
        service.pauseProcessing();
    }
}
```

Facade có thể kiểm tra quyền ở tầng ứng dụng, validation, readiness và giới hạn tác động. Nó làm rõ rằng API JMX khác API nghiệp vụ.

```text
Business API ---> QueueService <--- ManagementFacade
                                        |
                                   QueueManagement
                                        |
                                     assembler
                                        |
                                    MBeanServer
```

Nếu ứng dụng có nhiều quy tắc quản trị, facade thường giúp giữ interface nhỏ và tránh export các method nghiệp vụ không cần thiết. Nhưng facade không tự bảo đảm quyền truy cập JMX; connector và môi trường vẫn cần bảo vệ.

## 7. ManagedInterfaces và quản lý nhiều interface

`InterfaceBasedMBeanInfoAssembler` có thể được cấu hình với tập interface quản trị dùng chung cho các bean phù hợp. Ví dụ:

```java
assembler.setManagedInterfaces(
    MonitoringManagement.class,
    MaintenanceManagement.class
);
```

Ý tưởng là các method trong những interface được chỉ định tạo tập khả năng quản trị mà assembler công bố, khi bean hỗ trợ các method tương ứng.

Cần bảo đảm mọi bean dùng chung assembler có hợp đồng phù hợp. Không nên dùng một danh sách interface toàn cục chứa các thao tác nhạy cảm, rồi gắn cùng assembler vào tất cả service chỉ vì tiện cấu hình.

Nếu các MBean cần contract khác nhau, nên cấu hình riêng cho từng bean hoặc dùng mapping interface theo bean phù hợp. Điều đó tránh việc một cấu hình “một cỡ cho tất cả” làm mở rộng giao diện quản trị.

## 8. InterfaceMappings: hợp đồng riêng cho từng bean

Khi export nhiều bean, bạn có thể cần ánh xạ **bean key → management interface** thay vì một danh sách interface chung. Spring hỗ trợ cấu hình `interfaceMappings` cho assembler.

Ví dụ ý tưởng:

```java
InterfaceBasedMBeanInfoAssembler assembler =
    new InterfaceBasedMBeanInfoAssembler();

java.util.Properties mappings = new java.util.Properties();
mappings.setProperty(
    "inventoryMonitor",
    "com.example.jmx.InventoryManagement"
);
mappings.setProperty(
    "paymentMonitor",
    "com.example.jmx.PaymentManagement"
);

assembler.setInterfaceMappings(mappings);
```

Các tên class trong ví dụ chỉ là minh họa; chúng phải trỏ tới interface có thật trên classpath. Key mapping phải khớp với cách exporter định danh bean được export theo cấu hình thực tế. Vì lookup key phụ thuộc cơ chế export, hãy thử với `MBeanInfo` để xác nhận đúng interface đã áp dụng.

Điểm chính: **một assembler có thể áp dụng contract khác nhau cho từng resource**, giúp quản lý một tập MBean đa dạng mà không đưa mọi method của tất cả interface ra ngoài.

## 9. So sánh các kiểu MBeanInfoAssembler

Spring JMX có nhiều assembler:

| Assembler | Cơ chế chọn method | Khi phù hợp |
|---|---|---|
| `SimpleReflectiveMBeanInfoAssembler` | Dựa trên các public method phù hợp | Demo nhỏ hoặc khi có kiểm soát chặt class export |
| `MethodNameBasedMBeanInfoAssembler` | Allowlist theo tên method | Tập method nhỏ, không muốn tạo interface |
| `InterfaceBasedMBeanInfoAssembler` | Dựa trên management interface | API quản trị cần hợp đồng rõ, có thể type-check |
| `MetadataMBeanInfoAssembler` | Dựa trên annotation metadata | Muốn `@ManagedAttribute`, `@ManagedOperation` và mô tả trên method |

Ví dụ, `MethodNameBasedMBeanInfoAssembler` chọn tên method trong cấu hình, còn `InterfaceBasedMBeanInfoAssembler` dùng interface Java để phản ánh cả chữ ký và kiểu. Metadata assembler thuận tiện khi đặt annotation trực tiếp trên các method được quản trị.

Chọn assembler dựa trên mức độ rõ ràng và cách tổ chức source. Không nên bật nhiều assembler với kỳ vọng chúng tự hợp nhất: `MBeanExporter` sử dụng assembler được cấu hình cho việc tạo metadata.

## 10. Phân biệt Standard MBean và Spring interface-based export

Trong Java JMX thuần, Standard MBean thường dùng interface theo convention:

```java
public interface CacheMonitorMBean {
    int getCacheSize();
}
public class CacheMonitor implements CacheMonitorMBean {
    public int getCacheSize() { return 42; }
}
```

Đăng ký đối tượng vào `MBeanServer` sẽ cho JMX introspect interface `CacheMonitorMBean`.

Trong Spring, một service có thể không muốn đặt tên interface theo convention đó. Khi dùng `InterfaceBasedMBeanInfoAssembler`, Spring chủ động chọn interface đã cấu hình rồi tạo metadata qua exporter.

Sự khác nhau:

```text
Standard MBean:
  Java class + SomethingMBean
     -> JMX standard introspection
     -> MBeanInfo

Spring ModelMBean:
  Spring bean + management interface
     -> InterfaceBasedMBeanInfoAssembler
     -> ModelMBeanInfo
     -> ModelMBean
```

Cả hai cho client thấy attribute/operation, nhưng quá trình chọn method và đăng ký không đồng nhất. Không nên suy luận rằng `setManagedInterfaces(...)` thay đổi cách JDK nhận diện MXBean hoặc Standard MBean ở mọi con đường đăng ký.

## 11. Proxy Spring và management interface

Một Spring bean có thể được AOP proxy vì transaction, caching, security hoặc scope. Nếu cấu hình export trực tiếp một proxy, tập interface có thể nhìn thấy khác implementation class.

Ví dụ:

```java
@Transactional
public class PaymentService implements PaymentManagement {
    // ...
}
```

Khi Spring tạo JDK dynamic proxy, proxy thường công bố những interface liên quan. Interface management cần được proxy hỗ trợ đúng cách nếu exporter dựa trên proxy. Với CGLIB proxy, nhiều method implementation có thể hiện diện nhưng assembler vẫn giới hạn contract theo interface.

Những vấn đề cần kiểm tra:

- Bean được export là proxy hay target?
- Proxy có implement interface quản trị được chọn không?
- Method quản trị có được định tuyến qua advice mong đợi không?
- Interface đã cấu hình có dùng đúng kiểu tham số/return type không?
- Có operation bị giới hạn bởi transaction hoặc authentication theo cách khác với dự kiến không?

Không giải quyết bằng cách chuyển sang reflective assembler để “thấy hết method”, vì điều đó có thể vô tình công bố nhiều khả năng ngoài ý muốn. Hãy kiểm tra proxy và hợp đồng export thực tế.

## 12. Dependency và thứ tự khởi tạo

Exporter được tạo trong vòng đời ApplicationContext. Nếu một MBean quản trị phụ thuộc database, cache hoặc một service khác, Spring cần resolve dependency khi tạo bean. Tuy nhiên, việc đăng ký MBean thành công không nhất thiết chứng minh service bên ngoài đã READY.

Một getter an toàn:

```java
@Override
public String getServiceState() {
    return lifecycleState.currentState().name();
}
```

thường thích hợp hơn getter gọi database hoặc remote endpoint dài để “kiểm tra ngay”. Interface quản trị có thể chứa cả `getServiceState()` và `resetStatistics()`, nhưng operation cần kiểm tra điều kiện sẵn sàng và có guard thích hợp.

Nếu một MBean không được đăng ký, cần kiểm tra exporter, ObjectName, interface mapping, initialization exception và xung đột tên. Đừng tự động kết luận đây là lỗi của assembler: assembler chỉ là một mắt xích trong pipeline export.

## 13. Bảo mật: interface là allowlist nhưng không phải authorization

Management interface cho phép **giảm surface** bằng cách chỉ công bố những method được chọn. Nó không quyết định người dùng nào được gọi chúng.

Cần tách:

1. **Exposure:** method nào xuất hiện trong `MBeanInfo`?
2. **Authentication:** client nào được kết nối JMX?
3. **Authorization:** client được đọc/gọi operation nào?
4. **Validation:** giá trị hoặc thao tác có hợp lệ không?
5. **Audit:** hệ thống ghi nhận hoạt động quản trị ra sao?

Ví dụ `setConcurrencyLimit(int)` có thể được công bố hợp lý, nhưng vẫn phải từ chối giá trị không hợp lệ. Nếu remote JMX được bật, cần bảo vệ connection, giới hạn mạng và quyền truy cập. Interface không phải bức tường bảo mật đối với người đã có các quyền thao tác tiến trình Java rộng hơn.

Không export password, token, raw configuration, user data hoặc operation nguy hiểm chỉ vì chúng nằm trong một interface Java. Hãy tách interface JMX riêng và đánh giá từng method.

## 14. Kiểm tra kết quả qua MBeanInfo

Sau khi application khởi động và exporter đăng ký MBean, metadata là bằng chứng thực tế về giao diện công khai.

```java
MBeanInfo info = connection.getMBeanInfo(objectName);

for (MBeanAttributeInfo attribute : info.getAttributes()) {
    System.out.printf(
        "ATTRIBUTE %s read=%s write=%s type=%s%n",
        attribute.getName(),
        attribute.isReadable(),
        attribute.isWritable(),
        attribute.getType()
    );
}

for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.println(
        "OPERATION " + operation.getName()
    );
}
```

Đoạn code cần import:

```java
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
```

`connection` là `MBeanServerConnection`, `objectName` là `ObjectName` đã đăng ký. Với Spring, hãy kiểm tra tên getter được chuyển thành attribute và operation nào còn xuất hiện.

Đặc biệt, kiểm tra **sự vắng mặt** của những method không thuộc management interface. Một test thực hành có thể so sánh tập method mong đợi và metadata, rồi fail nếu xuất hiện getter nhạy cảm.

### 14.1. Đọc attribute và gọi operation

```java
Object count = connection.getAttribute(
    objectName,
    "CompletedJobs"
);

connection.setAttribute(
    objectName,
    new javax.management.Attribute("ConcurrencyLimit", 8)
);

connection.invoke(
    objectName,
    "resetStatistics",
    new Object[0],
    new String[0]
);
```

Khi `ConcurrencyLimit` có getter và setter tương thích, client có thể đọc/ghi. `CompletedJobs` chỉ đọc; cố gọi `setAttribute` cho nó sẽ bị từ chối. `resetStatistics` là operation có tác dụng phụ, nên trong production cần quyền hạn và audit tương xứng.

## 15. Những lỗi thường gặp

### 15.1. Interface mapping không khớp bean

Bạn cấu hình interface mapping bằng key `inventoryMonitor`, nhưng exporter dùng key khác để định danh resource. Khi đó assembler có thể không tìm được interface dự kiến. Kiểm tra cách mapping key được giải quyết theo cấu hình exporter thực tế; không đoán từ tên Java class.

### 15.2. Bean không thực hiện interface mong đợi

Assembler chọn `OrderManagement` nhưng bean không cung cấp các method tương ứng hoặc proxy không lộ interface phù hợp. Export có thể thất bại hoặc không tạo metadata như mong muốn. Bảo đảm bean thực hiện contract một cách rõ ràng.

### 15.3. Getter không xuất hiện

Kiểm tra getter nằm trong management interface, chữ ký theo JavaBean convention và kiểu dữ liệu hỗ trợ bởi JMX/exporter. Method chỉ tồn tại ở implementation sẽ không được chọn nếu assembler dùng interface.

### 15.4. Xuất thừa operation

Một management interface vô tình kế thừa một interface nghiệp vụ có method không nên công bố. Khi assembler chọn interface mở rộng, các method kế thừa có thể đi vào hợp đồng quản trị. Giữ management interface nhỏ và tách khỏi contract nghiệp vụ nếu cần.

### 15.5. MBean xuất hiện nhưng không gọi được operation

Kiểm tra kiểu và chữ ký method, proxy, exception trong implementation, trạng thái service và quyền truy cập connector. MBeanInfo cho thấy hợp đồng, nhưng gọi operation vẫn chạy code thật với những điều kiện runtime riêng.

### 15.6. Đăng ký trùng ObjectName

Hai MBean cùng đăng ký tên `demo.jobs:type=JobService,name=main` có thể xung đột. Sửa naming/mapping hoặc registration policy một cách có chủ đích, tránh che lỗi bằng cách overwrite những MBean không thuộc sở hữu exporter.

### 15.7. Kích hoạt cả annotation exporter và manual exporter

Nếu `@EnableMBeanExport` hoặc auto-configuration đã tạo exporter, thêm một `MBeanExporter` thủ công có thể tạo hai cơ chế đăng ký. Quy hoạch rõ ownership và ObjectName của từng exporter.

### 15.8. Nhầm việc “không export” với “không thể truy cập bằng mọi đường”

Interface allowlist chỉ giới hạn bề mặt MBean cụ thể. Nếu cùng dữ liệu được lộ qua log, HTTP endpoint, debugger hoặc một MBean khác thì rủi ro vẫn tồn tại. Hãy nhìn toàn bộ hệ thống, không chỉ một assembler.

## 16. Bài tập thực hành

**Bài 1 — Tạo allowlist.** Tạo `CacheService` có năm method: `getHitCount()`, `getCacheSize()`, `clearCache()`, `getInternalToken()`, `loadUserDetails(String)`. Tạo `CacheManagement` chỉ chứa hai getter số liệu và `clearCache()`, cấu hình assembler và kiểm tra `MBeanInfo`.

**Bài 2 — Thử thay đổi implementation.** Thêm `getInternalDebugState()` vào class implementation nhưng không thêm vào management interface. Khởi động lại và xác nhận interface-based export không tự công bố method mới đó.

**Bài 3 — So sánh assembler.** Với cùng một bean, lần lượt cấu hình `MethodNameBasedMBeanInfoAssembler` và `InterfaceBasedMBeanInfoAssembler`. Ghi nhận khác biệt trong cách cấu hình, khả năng type-check và metadata thực tế.

**Bài 4 — Dùng interfaceMappings.** Export hai bean có contract quản trị khác nhau. Tạo mapping theo bean key, rồi kiểm tra từng MBean chỉ có attribute/operation của interface được chọn.

**Bài 5 — Xử lý proxy.** Dùng service có transaction advice và một management interface nhỏ. Kiểm tra kiểu proxy, giao diện mà proxy thực hiện và metadata export. Giải thích vì sao phương thức implementation ngoài interface không nên được công bố chỉ để thuận tiện debug.

**Bài 6 — Xác minh kiểu quyền attribute.** Tạo `getLimit()` + `setLimit(int)` trong management interface, đồng thời `getCount()` chỉ có getter. Đọc `MBeanAttributeInfo.isReadable()` và `isWritable()`, thử ghi giá trị hợp lệ và không hợp lệ.

## 17. Câu hỏi tự kiểm tra

1. `InterfaceBasedMBeanInfoAssembler` có trách nhiệm gì trong pipeline Spring JMX?
2. Nó khác `MBeanExporter` ở điểm nào?
3. Vì sao một management interface riêng giúp giới hạn bề mặt quản trị?
4. Một method chỉ xuất hiện trong implementation có tự được công bố không khi dùng interface-based assembler?
5. Getter/setter được diễn giải thành attribute như thế nào?
6. Khi nào dùng `interfaceMappings` thay cho `managedInterfaces` chung?
7. Vì sao quản trị qua interface không thay thế authentication/authorization?
8. Standard MBean của JDK và Spring ModelMBean export khác nhau ở nguồn chọn interface như thế nào?
9. Nếu MBean bị thiếu method hoặc có thừa method, bạn kiểm tra thành phần nào trước?
10. Vì sao cần đối chiếu `MBeanInfo` sau khi cấu hình exporter?

## 18. Ghi nhớ

**`InterfaceBasedMBeanInfoAssembler` dùng management interface để định nghĩa ranh giới phương thức được công bố qua Spring JMX.** Cấu hình interface phù hợp, gắn assembler vào `MBeanExporter` và xác nhận `MBeanInfo` thực tế giúp tạo API quản trị có chủ đích, giảm nguy cơ lộ method nội bộ khi implementation thay đổi.

Nên giữ management interface nhỏ, ổn định, dễ review; phân biệt rõ attribute và operation, lựa chọn một chiến lược export nhất quán và bảo vệ remote JMX. Interface là cơ chế **giới hạn những gì có thể gọi**, còn quyền ai được gọi, validation và audit vẫn cần được thiết kế độc lập.
