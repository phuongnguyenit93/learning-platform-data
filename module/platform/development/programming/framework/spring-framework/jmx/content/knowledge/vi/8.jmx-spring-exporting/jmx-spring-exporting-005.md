# Spring bean không cần phụ thuộc trực tiếp vào API JMX

## 1. Vấn đề và mục tiêu

Trong ứng dụng Spring, các đối tượng nghiệp vụ thường được xây dựng để giải quyết bài toán của hệ thống: xử lý đơn hàng, quản lý cache, thực thi tác vụ hoặc thống kê giao dịch. JMX (**Java Management Extensions**) cung cấp cách quan sát và quản trị những đối tượng đó thông qua MBeanServer.

Điểm mạnh của **Spring Framework JMX Exporting** là Spring bean có thể giữ nguyên trách nhiệm nghiệp vụ, **không phải triển khai các giao diện của `javax.management`** và cũng không cần tự đăng ký vào MBeanServer. Spring có thể xuất bean thành MBean bằng `MBeanExporter`, chiến lược đặt tên và thành phần xây metadata.

Ví dụ, một class sau chỉ chứa logic nghiệp vụ:

```java
public class CacheStatistics {
    private final java.util.concurrent.atomic.AtomicLong hits =
            new java.util.concurrent.atomic.AtomicLong();

    public long getHitCount() {
        return hits.get();
    }

    public void recordHit() {
        hits.incrementAndGet();
    }

    public void reset() {
        hits.set(0);
    }
}
```

Class này không import `javax.management.*`, không implement `DynamicMBean`, `NotificationBroadcaster` hoặc `CacheStatisticsMBean`. Nó có thể được dùng trong ứng dụng Spring như một bean thông thường.

Nếu ứng dụng cần quan sát `HitCount` hoặc gọi `reset()` qua JMX, Spring có thể kết nối bean đó với lớp quản trị. Khi làm đúng, business class không cần biết JMX có tồn tại.

Bài học tập trung vào ba câu hỏi:

1. Spring tách **business bean** khỏi **JMX infrastructure** bằng cách nào?
2. Có những cách export nào và chúng khác nhau ở đâu?
3. Làm thế nào để kiểm soát những method thực sự được công bố, định danh MBean và vòng đời đăng ký?

## 2. Phân biệt Spring bean, MBean và MBeanServer

Một **Spring bean** là đối tượng được Spring container tạo, cấu hình hoặc quản lý. Bean không mặc nhiên là MBean.

Một **MBean** là đối tượng quản trị đáp ứng hợp đồng JMX, công bố các attribute, operation và có thể có notification.

**MBeanServer** là thành phần JMX dùng để đăng ký, tìm và điều phối các MBean. Mỗi MBean được định danh bởi `ObjectName`, ví dụ:

```text
com.example.shop:type=CacheStatistics,name=product
```

Khi Spring export bean, kiến trúc có thể hình dung:

```text
Spring ApplicationContext
    |
    +-- CacheStatistics (plain Java object)
    |       |
    |       +-- getHitCount()
    |       +-- recordHit()
    |       +-- reset()
    |
    +-- MBeanExporter
            |
            +-- ObjectNamingStrategy
            +-- MBeanInfoAssembler (khi cần)
            +-- MBeanServer
                    |
                    +-- ObjectName
                            |
                            +-- JConsole / JMX client
```

Không phải mọi public method của bean đều nên được export. **Business API** và **management API** là hai hợp đồng cần được chọn rõ ràng. Xuất bean ra JMX không biến mọi hành vi Java của bean thành một giao diện quản trị an toàn.

## 3. MBeanExporter: thành phần trung tâm

`org.springframework.jmx.export.MBeanExporter` chịu trách nhiệm đăng ký những bean được chọn vào một `MBeanServer`.

Những trách nhiệm chính:

- Chọn các bean sẽ được xuất.
- Ánh xạ bean với `ObjectName`.
- Sử dụng `ObjectNamingStrategy` khi cần đặt tên theo quy ước.
- Sử dụng `MBeanInfoAssembler` hoặc cơ chế thích hợp để xây metadata cho bean không trực tiếp tuân theo một interface MBean chuẩn.
- Đăng ký và hủy đăng ký MBean theo lifecycle của exporter.
- Áp dụng chính sách xử lý khi tên MBean đã tồn tại.
- Phối hợp với các cơ chế notification của Spring JMX khi được cấu hình.

Khi dùng **explicit export**, ứng dụng chỉ rõ bean và ObjectName, chẳng hạn:

```text
Bean productCacheStatistics
    -> com.example.shop:type=CacheStatistics,name=product

Bean customerCacheStatistics
    -> com.example.shop:type=CacheStatistics,name=customer
```

Điều này tạo ranh giới rõ giữa tên bean nội bộ của Spring và tên MBean bên ngoài.

### MBeanExporter không làm thay logic nghiệp vụ

Exporter không tự tính số cache hit, không xử lý HTTP request và không quyết định giá trị nào có ý nghĩa vận hành. Resource bên dưới vẫn có trách nhiệm duy trì trạng thái và tính đúng đắn của các method.

Ví dụ `getHitCount()` trả số lượt hit do bean ghi nhận; nếu bean không cập nhật số liệu đúng, JMX sẽ đọc giá trị sai như mọi caller khác.

## 4. Cách 1: xuất POJO bằng interface và cấu hình Spring

Một phương pháp là tách hợp đồng quản trị thành một **interface Java chuyên biệt**. Bean không phải import API JMX, dù có thể tuân theo quy ước đặt tên Standard MBean.

```java
package com.example.shop;

public interface ProductCacheMonitorMBean {
    long getHitCount();
    void resetStatistics();
}
```

```java
package com.example.shop;

import java.util.concurrent.atomic.AtomicLong;

public class ProductCacheMonitor
        implements ProductCacheMonitorMBean {

    private final AtomicLong hitCount = new AtomicLong();

    public void recordHit() {
        hitCount.incrementAndGet();
    }

    @Override
    public long getHitCount() {
        return hitCount.get();
    }

    @Override
    public void resetStatistics() {
        hitCount.set(0);
    }
}
```

Ở ví dụ này, interface `ProductCacheMonitorMBean` là một hợp đồng Java; code không import `javax.management`. Bean vẫn có sự gắn kết với **quy ước tên JMX** qua hậu tố `MBean`.

Nếu mục tiêu là class nghiệp vụ **hoàn toàn không cần biết hợp đồng quản trị**, có thể dùng một adapter quản trị riêng:

```java
public class ProductCacheService {
    private final java.util.concurrent.atomic.AtomicLong hits =
            new java.util.concurrent.atomic.AtomicLong();

    public long hits() {
        return hits.get();
    }

    public void recordHit() {
        hits.incrementAndGet();
    }

    public void resetCounters() {
        hits.set(0);
    }
}
```

```java
public interface ProductCacheAdminMBean {
    long getHitCount();
    void resetStatistics();
}
```

```java
public class ProductCacheAdmin implements ProductCacheAdminMBean {
    private final ProductCacheService service;

    public ProductCacheAdmin(ProductCacheService service) {
        this.service = service;
    }

    @Override
    public long getHitCount() {
        return service.hits();
    }

    @Override
    public void resetStatistics() {
        service.resetCounters();
    }
}
```

Với thiết kế này, `ProductCacheService` là business class thuần Java; `ProductCacheAdmin` sở hữu management API. Adapter có thể được đăng ký qua JMX thuần hoặc Spring exporter.

**Lợi ích:** thay đổi cách export JMX mà không sửa hợp đồng nghiệp vụ. Đây là lựa chọn tốt với ứng dụng cần quản lý dependency rất chặt hoặc có nhiều đường quan sát cùng một service.

## 5. Cách 2: xuất plain Spring bean bằng metadata của Spring

Spring JMX hỗ trợ cấu hình một **MBeanInfoAssembler** để mô tả interface quản trị của một bean. Nhờ đó, bean có thể không implement `*MBean` và không import API JMX.

Giả sử có POJO:

```java
package com.example.shop;

import java.util.concurrent.atomic.AtomicInteger;

public class QueueStatistics {
    private final AtomicInteger pending = new AtomicInteger();

    public int getPendingCount() {
        return pending.get();
    }

    public void onJobEnqueued() {
        pending.incrementAndGet();
    }

    public void reset() {
        pending.set(0);
    }

    public void internalMaintenance() {
        // Not intended as a JMX management operation.
    }
}
```

Ta muốn xuất **chỉ** `PendingCount` và `reset()`, không xuất `internalMaintenance()`.

Một lựa chọn là dùng `MethodNameBasedMBeanInfoAssembler` để cấu hình method được công bố:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.assembler.MethodNameBasedMBeanInfoAssembler;

import java.util.Map;

@Configuration
public class QueueJmxConfiguration {

    @Bean
    QueueStatistics queueStatistics() {
        return new QueueStatistics();
    }

    @Bean
    MethodNameBasedMBeanInfoAssembler queueMBeanInfoAssembler() {
        MethodNameBasedMBeanInfoAssembler assembler =
                new MethodNameBasedMBeanInfoAssembler();

        assembler.setManagedMethods(
                "getPendingCount",
                "reset"
        );
        return assembler;
    }

    @Bean
    MBeanExporter queueMBeanExporter(
            QueueStatistics queueStatistics,
            MethodNameBasedMBeanInfoAssembler assembler
    ) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setBeans(Map.of(
                "com.example.shop:type=QueueStatistics,name=orders",
                queueStatistics
        ));
        exporter.setAssembler(assembler);
        return exporter;
    }
}
```

**Giải thích:**

1. `QueueStatistics` là bean thuần, không biết JMX.
2. `MethodNameBasedMBeanInfoAssembler` chọn danh sách method được đưa vào metadata của MBean.
3. `MBeanExporter` ánh xạ bean tới một ObjectName và đăng ký với MBeanServer.
4. JConsole hoặc client JMX đọc MBean qua ObjectName và metadata được exporter tạo.

Các assembler theo tên method hoặc interface là công cụ hữu ích để bảo vệ business class khỏi phụ thuộc framework. Với ứng dụng thực tế, cần đối chiếu method được công bố, chữ ký và kiểu trả về qua `MBeanInfo`; lựa chọn assembler có thể ảnh hưởng cách method được nhận diện là attribute hay operation.

### Vì sao metadata assembler quan trọng?

Không có một cơ chế xuất phù hợp, Java object thông thường không tự trở thành MBean hợp lệ. Assembler là một phần giúp Spring xây **Dynamic/Model MBean metadata** và kết nối các attribute/operation được công bố với bean thật.

Đây là giải pháp gần nhất với yêu cầu: **“Spring bean không cần phụ thuộc trực tiếp vào API JMX.”** Phần quản trị được khai báo ở configuration và infrastructure, không nhúng vào lớp nghiệp vụ.

## 6. Cách 3: annotation của Spring giúp đơn giản hóa nhưng vẫn tạo phụ thuộc annotation

Spring cung cấp:

- `@ManagedResource`: mô tả bean được quản trị.
- `@ManagedAttribute`: công bố thuộc tính.
- `@ManagedOperation`: công bố thao tác.
- `@ManagedOperationParameter`: mô tả tham số.
- `@ManagedNotification`: khai báo thông tin notification.
- `@ManagedMetric`: công bố metadata metric.

Ví dụ:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.shop:type=QueueStatistics,name=orders",
    description = "Order queue statistics"
)
public class QueueStatistics {
    private volatile int pendingCount;

    @ManagedAttribute
    public int getPendingCount() {
        return pendingCount;
    }

    @ManagedOperation
    public void reset() {
        pendingCount = 0;
    }
}
```

Class này **không import JMX API của JDK**, nhưng có import **annotation JMX integration của Spring**. Vì vậy cần phân biệt hai mức độc lập:

| Mức độc lập | Ý nghĩa | Lựa chọn phù hợp |
| --- | --- | --- |
| Không phụ thuộc trực tiếp `javax.management` | Bean không cần implement `DynamicMBean` hoặc dùng `MBeanServer` | Annotation Spring, assembler hoặc adapter |
| Không phụ thuộc bất kỳ JMX-specific API/annotation nào | Business bean không cần biết nó được quản trị bằng JMX | External metadata assembler hoặc adapter |

Annotation rất tiện khi bean thuộc riêng một ứng dụng Spring và không cần độc lập tuyệt đối. Nếu class nằm ở domain module dùng chung cho nhiều runtime, cách khai báo metadata bên ngoài bean thường có ranh giới kiến trúc rõ hơn.

**Lưu ý:** annotation không tự đăng ký MBean. Phải có `AnnotationMBeanExporter` hoặc cơ chế Spring JMX tương đương được cấu hình.

## 7. So sánh các lựa chọn trong Spring

| Giải pháp | Business bean biết JMX? | Management metadata ở đâu? | Điểm mạnh | Trade-off |
| --- | --- | --- | --- | --- |
| Standard MBean interface trên bean | Biết quy ước interface MBean, dù không import `javax.management` | Java interface | Hợp đồng type-safe, dùng với JMX thuần | Bean liên kết với management API |
| Adapter implement MBean interface | Không | Adapter và interface | Tách biệt rõ nghiệp vụ/quản trị | Thêm lớp adapter |
| Plain bean + MethodNameBasedMBeanInfoAssembler | Không | Spring config | Không sửa mã nghiệp vụ, chọn method tập trung | Phải giữ tên method/config đồng bộ |
| Plain bean + InterfaceBasedMBeanInfoAssembler | Có thể không | Interface và Spring config | Chọn giao diện công bố bằng interface | Cần thiết kế interface và cấu hình chính xác |
| Bean + `@Managed*` annotation | Biết Spring JMX annotation | Class/method | Dễ đọc, metadata gần method | Dependency vào Spring JMX annotation |
| Export MXBean có hợp đồng JMX riêng | Tùy class/adapter | MXBean interface | Tương thích remote nhờ open-type mapping | Hợp đồng quản trị phải tuân theo quy tắc MXBean |

Có thể phối hợp các cách. Ví dụ business service thuần Java, adapter quản trị implement MXBean, và Spring chỉ đảm nhận lifecycle đăng ký.

## 8. InterfaceBasedMBeanInfoAssembler: công bố qua interface mà class không implement MBean

Một lựa chọn khác trong Spring là `InterfaceBasedMBeanInfoAssembler`.

Giả sử business interface:

```java
public interface QueueMonitoring {
    int getPendingCount();
    long getCompletedCount();
}
```

```java
public class OrderQueue implements QueueMonitoring {
    private volatile int pending;
    private volatile long completed;

    @Override
    public int getPendingCount() {
        return pending;
    }

    @Override
    public long getCompletedCount() {
        return completed;
    }

    public void deleteQueueData() {
        // Internal operation, should not be exposed.
    }
}
```

Spring có thể sử dụng interface để quyết định method nào được xuất:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.jmx.export.assembler.InterfaceBasedMBeanInfoAssembler;

@Bean
InterfaceBasedMBeanInfoAssembler queueAssembler() {
    InterfaceBasedMBeanInfoAssembler assembler =
            new InterfaceBasedMBeanInfoAssembler();
    assembler.setManagedInterfaces(QueueMonitoring.class);
    return assembler;
}
```

Khi `MBeanExporter` sử dụng assembler này, các method khai báo trong `QueueMonitoring` là tập method được xem xét công bố, còn `deleteQueueData()` nằm ngoài hợp đồng.

`QueueMonitoring` không bắt buộc mang hậu tố `MBean`, vì đây là một Java interface được Spring dùng làm nguồn metadata chứ không nhất thiết là Standard MBean interface theo quy ước JMX.

**Chú ý:** Việc chọn interface của assembler chỉ quyết định tập method được xét công bố; attribute và operation vẫn được xây theo quy tắc metadata của Spring. Với interface generic hoặc inheritance phức tạp, hãy kiểm tra `getMBeanInfo` của MBean đã đăng ký.

## 9. Một kiến trúc rõ trách nhiệm

Một hệ thống có thể chia thành:

```text
domain/
  OrderService.java
  OrderQueue.java

application/
  OrderJobProcessor.java

management/
  OrderQueueManagement.java
  JmxExportConfiguration.java
```

Trong đó:

```text
Domain/Application
    |
    +-- logic nghiệp vụ
    +-- dữ liệu và trạng thái runtime
    +-- không biết có JMX hay không

Management adapter/configuration
    |
    +-- xác định attributes/operations
    +-- chọn bean và ObjectName
    +-- cấu hình metadata, notification, registration
    +-- được phép phụ thuộc Spring JMX/JMX API

Monitoring client
    |
    +-- kết nối MBeanServer
    +-- đọc dữ liệu qua ObjectName
```

Lợi ích:

1. Business code không cần thay đổi khi bỏ JMX hoặc thay cách export.
2. Có thể thêm Micrometer, OpenTelemetry, REST management endpoint hoặc logging mà không nhúng mọi hạ tầng vào domain.
3. Dễ kiểm thử domain độc lập với MBeanServer.
4. Dễ kiểm soát method nguy hiểm bằng một API quản trị giới hạn.
5. Dễ chuyển bean giữa Spring applications mà không mang theo annotation JMX.

Vẫn cần cân nhắc quy mô: với một ứng dụng nhỏ có hai metric, thêm nhiều adapter/assembler có thể làm tăng độ phức tạp không cần thiết. Chọn mức tách biệt theo yêu cầu thật.

## 10. ObjectName: vẫn cần thiết dù bean thuần Java

Bean có độc lập với API JMX đến đâu thì MBean được export vẫn phải có ObjectName duy nhất trong MBeanServer.

Ví dụ:

```text
com.example.shop:type=CacheStatistics,application=storefront,name=products
com.example.shop:type=CacheStatistics,application=storefront,name=customers
com.example.shop:type=QueueStatistics,application=storefront,name=orders
```

Spring hỗ trợ `ObjectNamingStrategy`, chẳng hạn naming theo metadata hoặc bean key.

Những điều nên xác định:

- **Domain** thể hiện namespace của ứng dụng/hệ thống.
- **Type** biểu thị loại tài nguyên quản trị.
- **Application/context** giúp phân biệt các ứng dụng hoặc context cùng chia sẻ MBeanServer khi cần.
- **Name** phân biệt bean/resource cụ thể.
- **Lifecycle** bảo đảm exporter hủy đăng ký đúng MBean khi context đóng.

Nếu nhiều exporter đăng ký cùng ObjectName, có thể phát sinh `InstanceAlreadyExistsException`. `MBeanExporter` hỗ trợ chính sách registration như fail, ignore hoặc replace; lựa chọn mặc định an toàn thường là phát hiện xung đột và sửa cách đặt tên, tránh vô tình ghi đè MBean của thành phần khác.

**Không lấy tên class proxy runtime làm định danh lâu dài** nếu ứng dụng dùng AOP, vì tên proxy có thể thay đổi theo cấu hình.

## 11. Bean lifecycle và MBean lifecycle không hoàn toàn giống nhau

Spring quản lý lifecycle của bean và context. JMX quản lý lifecycle đăng ký của MBean trong MBeanServer.

Một bean có thể tồn tại trong context nhưng chưa export vì:

- Không được đưa vào danh sách bean export.
- Exporter chưa khởi tạo hoặc chưa đăng ký thành công.
- Bean không tương thích với assembler hoặc interface đã chọn.
- ObjectName không hợp lệ hoặc đã tồn tại.
- Exporter dùng MBeanServer khác với server mà client kết nối.

Ngược lại, nếu đăng ký MBean thủ công mà không hủy đăng ký, MBean có thể tồn tại trong server lâu hơn lifecycle mong đợi của thành phần.

Khi dùng `MBeanExporter`, nên để chính exporter quản lý việc đăng ký và hủy đăng ký; tránh có một logic thủ công khác cùng quản lý một tên nếu không có ownership rõ ràng.

### Khởi động và shutdown

```text
ApplicationContext khởi tạo
    -> tạo business bean
    -> tạo MBeanExporter
    -> exporter đăng ký MBean
    -> JMX client có thể truy vấn

ApplicationContext đóng
    -> exporter hủy đăng ký các MBean thuộc quyền quản lý
    -> business bean hoàn tất lifecycle
```

Thứ tự chi tiết phụ thuộc lifecycle framework và cấu hình; sơ đồ mô tả trách nhiệm, không phải mọi callback thực tế.

## 12. Phân tách quản trị với nghiệp vụ không đồng nghĩa tự động an toàn

Ví dụ POJO có method:

```java
public void deleteAllOrders() {
    // Destructive business operation.
}
```

Nếu assembler được cấu hình quá rộng, method này có thể bị công bố dưới dạng JMX operation. Do đó:

- Chọn tập method quản trị rõ ràng, thay vì export tất cả public method của business bean.
- Không để lộ credential, token, dữ liệu cá nhân hoặc cấu hình nhạy cảm qua attribute.
- Thiết kế getter quản trị nhanh, không gây side effect.
- Kiểm soát quyền kết nối JMX remote; sử dụng authentication, TLS và giới hạn mạng phù hợp.
- Xác định operation nào chỉ đọc, operation nào thay đổi trạng thái, cần audit/authorization nào.

**Tách dependency giúp kiến trúc rõ ràng; bảo mật còn phụ thuộc vào hợp đồng export và cấu hình runtime.**

## 13. Kiểm thử việc export mà không sửa business class

Có thể kiểm thử hai lớp trách nhiệm riêng.

### 13.1. Test business logic

Test `QueueStatistics` như Java object thông thường:

```java
QueueStatistics statistics = new QueueStatistics();

statistics.onJobEnqueued();
assert statistics.getPendingCount() == 1;

statistics.reset();
assert statistics.getPendingCount() == 0;
```

Kiểm thử này không cần `MBeanServer` hoặc Spring context.

### 13.2. Test hợp đồng JMX

Trong integration test có exporter và MBeanServer, kiểm tra:

1. MBean được đăng ký đúng ObjectName.
2. Các attribute cần thiết có thể đọc.
3. Chỉ operation được phép được công bố.
4. Method nội bộ không vô tình xuất ra.
5. Khi context đóng, exporter dọn dẹp các MBean thuộc quyền quản lý.

Ví dụ phác thảo truy vấn:

```java
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

ObjectName name = new ObjectName(
    "com.example.shop:type=QueueStatistics,name=orders"
);

if (!server.isRegistered(name)) {
    throw new AssertionError("Expected MBean is not registered");
}

MBeanInfo info = server.getMBeanInfo(name);

for (var operation : info.getOperations()) {
    if ("internalMaintenance".equals(operation.getName())) {
        throw new AssertionError(
            "Internal method must not be exported"
        );
    }
}
```

`server` ở đây là MBeanServer được cấu hình cho integration test; cần tạo hoặc inject đúng đối tượng, không giả định biến đã có sẵn. Những test như vậy xác nhận ranh giới hạ tầng, thay vì buộc domain test khởi tạo JMX.

## 14. Những hiểu lầm thường gặp

### “Spring bean tự động là MBean”

Không. Bean phải được exporter lựa chọn và đăng ký vào MBeanServer theo cấu hình phù hợp.

### “Không implement `javax.management.*` thì không thể export”

Không. Spring có thể xây metadata và xuất POJO bằng assembler hoặc adapter thích hợp.

### “Dùng `@ManagedResource` nghĩa là business class hoàn toàn không phụ thuộc JMX”

Không hoàn toàn. Class vẫn có dependency vào integration annotation của Spring. Chỉ khi metadata được đặt ở cấu hình hoặc adapter bên ngoài mới đạt độc lập hoàn toàn về khai báo quản trị.

### “Có MBeanExporter thì mọi public method được xuất đều an toàn”

Không. Cần giới hạn tập method, hiểu nghiệp vụ và kiểm soát security. Phương pháp exporter không tự bảo đảm quyền gọi hoặc rủi ro side effect.

### “Spring bean name và JMX ObjectName là một”

Không. Bean name là định danh trong ApplicationContext; ObjectName định danh MBean trong MBeanServer. Naming strategy có thể dùng bean key để tạo ObjectName, nhưng đây là một lựa chọn cấu hình.

### “Tách JMX ra ngoài business class khiến không thể cập nhật metric”

Không. Business class vẫn giữ trạng thái và API Java; adapter hoặc exporter chỉ đọc/call các method đã có. Quan hệ dependency có thể đi từ management layer tới domain layer.

### “Một MBeanServer cho mỗi Spring context”

Không phải mặc định. Nhiều context có thể cùng sử dụng platform MBeanServer và cần tránh ObjectName trùng.

## 15. Hướng dẫn chọn cơ chế export

| Yêu cầu thực tế | Hướng triển khai phù hợp |
| --- | --- |
| Bean có API đơn giản và chỉ dùng trong Spring | Annotation `@Managed*` có thể đủ |
| Không muốn business class import Spring JMX | External assembler hoặc adapter |
| Không muốn class phụ thuộc bất kỳ quy ước JMX nào | External metadata assembler, không dùng MBean interface trên domain class |
| Cần hợp đồng Java quản trị ổn định giữa nhiều module | Interface-based MBean hoặc MXBean adapter |
| Muốn expose một tập method được kiểm soát | InterfaceBased hoặc MethodNameBased assembler, hoặc adapter riêng |
| Cần công cụ generic đọc dữ liệu phức tạp từ xa | Cân nhắc MXBean/Open Types |
| Có nhiều bean cùng loại | ObjectNamingStrategy và ObjectName ổn định, duy nhất |
| Có nhiều application context | Ownership và lifecycle registration rõ ràng |
| Có thao tác có khả năng thay đổi trạng thái | Adapter quản trị chuyên biệt và quyền truy cập phù hợp |

## 16. Bài tập tự thực hành

**Mục tiêu:** tạo một bean `QueueStatistics` chỉ chứa logic Java, sau đó export hai khả năng quản trị mà không sửa mã nguồn của bean.

Các bước:

1. Tạo `QueueStatistics` với `getPendingCount()`, `onJobEnqueued()`, `reset()`, `internalMaintenance()`.
2. Đăng ký bean trong Spring `ApplicationContext`.
3. Tạo `MBeanExporter` và `MethodNameBasedMBeanInfoAssembler` chỉ chọn `getPendingCount` và `reset`.
4. Dùng ObjectName `com.example.shop:type=QueueStatistics,name=orders`.
5. Chạy ứng dụng và mở JConsole kết nối tới JVM.
6. Kiểm tra `PendingCount` và operation `reset()` có mặt.
7. Đảm bảo `internalMaintenance()` không xuất hiện.
8. Thay đổi trạng thái queue bằng một caller Java thông thường, sau đó quan sát lại attribute trong JConsole.
9. Đóng Spring context, xác nhận MBean đã được hủy đăng ký đúng.

### Câu hỏi tự kiểm tra

**1. Vì sao plain Spring bean có thể xuất ra JMX dù không implement `DynamicMBean`?**

Vì Spring exporter có thể sử dụng assembler và infrastructure JMX để biểu diễn bean dưới dạng MBean.

**2. `@ManagedResource` có hoàn toàn loại bỏ dependency quản trị khỏi source code không?**

Không. Nó loại bỏ nhu cầu implement JMX interface trực tiếp nhưng vẫn đưa annotation của Spring JMX vào class.

**3. Vai trò của `MBeanInfoAssembler` là gì?**

Xác định các attributes/operations và metadata của bean sẽ được công bố qua JMX.

**4. Có nên export mọi public method của service không?**

Không. Nên chọn rõ những method cần quản trị, đặc biệt khi service có operation thay đổi dữ liệu hoặc trạng thái.

**5. `ObjectName` có gắn với tên Java class không?**

Không bắt buộc. ObjectName được tạo bởi cấu hình hoặc naming strategy; nên dùng định danh nghiệp vụ ổn định.

**6. Tách adapter ra có lợi gì?**

Giữ domain code độc lập với JMX, giới hạn API quản trị và dễ bổ sung các kênh quản trị khác.

## 17. Tổng kết

**Spring bean không cần phụ thuộc trực tiếp vào API JMX để được export thành MBean.** Spring `MBeanExporter`, `MBeanInfoAssembler` và `ObjectNamingStrategy` tạo lớp kết nối giữa bean nghiệp vụ và MBeanServer.

Nếu chỉ muốn tránh `javax.management`, annotation Spring hoặc MBean interface theo quy ước có thể đáp ứng. Nếu muốn **business bean hoàn toàn không biết đến JMX**, hãy ưu tiên đặt metadata trong cấu hình Spring hoặc tạo adapter quản trị riêng.

Thiết kế bền vững cần giữ rõ ba ranh giới: **business logic thuộc về bean**, **management API thuộc về interface/metadata/adapter**, và **registration/lifecycle thuộc về infrastructure JMX của Spring**.

### Tài liệu tham khảo

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework API — `MBeanExporter`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Spring Framework API — `MBeanInfoAssembler`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/assembler/MBeanInfoAssembler.html
- Java SE Management API: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/module-summary.html
