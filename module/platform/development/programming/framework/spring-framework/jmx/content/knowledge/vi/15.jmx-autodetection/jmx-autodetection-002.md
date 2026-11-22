# Autodetect resource dựa trên assembler trong Spring Framework JMX

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích **autodetection** của `MBeanExporter` và cơ chế lựa chọn bean thông qua **`AutodetectCapableMBeanInfoAssembler`**.
- Phân biệt chế độ phát hiện MBean theo interface/JMX compliance với chế độ phát hiện resource dựa trên metadata assembler.
- Hiểu cách `MetadataMBeanInfoAssembler`, `AnnotationJmxAttributeSource` và `@ManagedResource` phối hợp để quyết định một Spring bean có được export không.
- Cấu hình exporter chủ động và tránh việc vô tình công bố quá nhiều MBean.
- Kiểm tra kết quả bằng `MBeanServer.queryNames()` và `MBeanServer.getMBeanInfo()`.
- Nhận diện giới hạn liên quan Spring AOP proxies, bean name, `ObjectName`, exporter trùng lặp và lifecycle.
- Thiết kế cơ chế discovery phù hợp cho ứng dụng Spring có nhiều bean nhưng chỉ một phần cần được quản trị qua JMX.

## 2. Bài toán: Spring có nhiều bean, export bean nào?

Một ứng dụng Spring có thể có hàng trăm bean: controller, service, repository, scheduler, cache adapter, configuration và các bean hạ tầng. Không phải bean nào cũng nên xuất hiện trong JConsole.

Ví dụ:

```text
ApplicationContext
├── orderController
├── orderService
├── orderRepository
├── paymentClient
├── inventoryClient
├── queueManagement      (@ManagedResource)
├── cacheManagement      (@ManagedResource)
└── internalScheduler
```

Khi muốn quản lý queue và cache qua JMX, bạn có hai hướng chính:

1. **Export tường minh:** chỉ định chính xác bean và `ObjectName` trong `MBeanExporter.setBeans(...)`.
2. **Autodetection:** yêu cầu exporter tự tìm các bean đáp ứng điều kiện nhất định.

Với autodetection dựa trên **assembler**, quyết định “bean có được xem là managed resource không?” được giao cho một assembler có khả năng xét điều kiện include. Đây là cách phù hợp với annotation-driven JMX: chỉ những bean có metadata quản trị thích hợp mới được chọn.

Ý chính:

> Assembler không chỉ mô tả attribute và operation. Khi triển khai `AutodetectCapableMBeanInfoAssembler`, nó còn có thể tham gia **quyết định bean nào được autodetect để export**.

Vì vậy “autodetect resource dựa trên assembler” không có nghĩa “quét mọi class có bất kỳ annotation nào” hay “export mọi bean Java public”.

## 3. Các thành phần cần phân biệt

| Thành phần | Chức năng |
|---|---|
| `MBeanExporter` | Tích hợp Spring beans với `MBeanServer`, chọn bean và thực hiện registration |
| `MBeanInfoAssembler` | Tạo metadata JMX cho attributes, operations, descriptions... |
| `AutodetectCapableMBeanInfoAssembler` | Mở rộng assembler với khả năng quyết định một bean có nên được autodetect |
| `MetadataMBeanInfoAssembler` | Assembler đọc management metadata từ một `JmxAttributeSource` |
| `AnnotationJmxAttributeSource` | Nguồn metadata từ các annotation JMX như `@ManagedResource` |
| `@ManagedResource` | Đánh dấu một bean/class là tài nguyên quản trị và cung cấp metadata resource |
| `@ManagedAttribute` | Đánh dấu getter/setter cần công bố dưới dạng JMX attribute |
| `@ManagedOperation` | Đánh dấu operation được phép gọi qua JMX |
| `ObjectNamingStrategy` | Xác định `ObjectName` của bean được export |
| `MBeanServer` | Registry và runtime API của JMX |

Một luồng xử lý khái niệm:

```text
Spring ApplicationContext
          |
          v
     MBeanExporter
          |
          +-- autodetectMode = ASSEMBLER
          |
          v
 AutodetectCapableMBeanInfoAssembler
          |
          +-- includeBean(beanClass, beanName)?
          |       |
          |       +-- false --> bỏ qua bean
          |       |
          |       +-- true
          |             |
          |             v
          |       tạo MBeanInfo
          |             |
          |             v
          +------ ObjectNamingStrategy
                        |
                        v
                 MBeanServer
                        |
                        v
                  JMX client
```

Sơ đồ là mô hình logic để hiểu nhiệm vụ từng component. Thời điểm gọi, cách phát hiện target class của proxy, chính sách naming và registration phụ thuộc phiên bản/cấu hình Spring cụ thể.

## 4. Autodetect assembler khác autodetect MBean thế nào?

`MBeanExporter` hỗ trợ các chế độ autodetection có thể được cấu hình bằng tên hằng.

| Chế độ | Ý nghĩa chung |
|---|---|
| `AUTODETECT_NONE` | Không tự phát hiện bean ngoài các đăng ký tường minh |
| `AUTODETECT_MBEAN` | Tìm các bean đã phù hợp với cơ chế MBean JMX, chẳng hạn Standard/Dynamic MBean |
| `AUTODETECT_ASSEMBLER` | Để một assembler có khả năng autodetect quyết định bean nào nên được export |
| `AUTODETECT_ALL` | Kết hợp các đường autodetection được hỗ trợ |

Trong API Spring, chế độ có thể được đặt bằng `setAutodetectModeName("AUTODETECT_ASSEMBLER")` hoặc API số tương ứng tùy phiên bản.

Điểm cần nhớ: `AUTODETECT_ASSEMBLER` **không** đồng nghĩa với “lấy mọi Spring bean và biến thành MBean”. Nó yêu cầu một **assembler có khả năng autodetect** và điều kiện include tương ứng.

### So sánh ngắn

Cho:

```java
public class HealthMonitor implements HealthMonitorMBean { ... }
```

và:

```java
@ManagedResource(objectName =
        "com.example.shop:type=QueueMonitor,name=primary")
public class QueueManagement { ... }
```

Nếu chọn `AUTODETECT_MBEAN`, exporter tìm bean đáp ứng tiêu chí MBean theo cơ chế JMX. Với `AUTODETECT_ASSEMBLER` và `MetadataMBeanInfoAssembler` + annotation source, `QueueManagement` được xét theo `@ManagedResource`.

Không nên dự đoán tất cả output của chế độ `ALL` mà không xem assembler và naming strategy thực tế; chế độ này có phạm vi rộng hơn và có thể tạo registration ngoài dự tính.

## 5. Contract: AutodetectCapableMBeanInfoAssembler

Một assembler thông thường có nhiệm vụ tạo `MBeanInfo`. Assembler được dùng để autodetect cần thêm khả năng quyết định bean có được chọn không.

API khái niệm trong Spring:

```java
public interface AutodetectCapableMBeanInfoAssembler
        extends MBeanInfoAssembler {

    boolean includeBean(Class<?> beanClass, String beanName);
}
```

Ý nghĩa:

- `beanClass`: class mà exporter đưa ra để assembler đánh giá.
- `beanName`: tên Spring bean tương ứng.
- Giá trị `true`: bean thỏa chính sách include và có thể được export.
- Giá trị `false`: bean không được chọn qua đường autodetection của assembler.

Đây là interface mô tả **cơ chế lựa chọn**, không phải API tùy tiện để gọi JMX operations.

Với `MetadataMBeanInfoAssembler`, lựa chọn thường dựa vào khả năng lấy `ManagedResource` metadata từ `JmxAttributeSource`. Khi kết hợp `AnnotationJmxAttributeSource`, `@ManagedResource` trở thành dấu hiệu quan trọng cho một managed resource.

**Không nhầm:** Annotation `@ManagedAttribute` trên một getter chưa chắc đủ để class được autodetect là managed resource; annotation class-level `@ManagedResource` mới là thông tin đánh dấu resource trong luồng metadata-based discovery phổ biến.

## 6. MetadataMBeanInfoAssembler và AnnotationJmxAttributeSource

Giả sử:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.shop.orders:type=QueueMonitor,name=outbox",
    description = "Order outbox queue")
public class QueueManagement {

    private int pendingCount;

    @ManagedAttribute(description = "Current pending jobs")
    public int getPendingCount() {
        return pendingCount;
    }

    @ManagedOperation(description = "Reset local statistics")
    public void resetStatistics() {
        pendingCount = 0;
    }
}
```

Phân vai:

1. **`@ManagedResource`** giúp nhận diện class này là tài nguyên cần đưa ra JMX.
2. **`@ManagedAttribute`** mô tả getter trở thành attribute `PendingCount`.
3. **`@ManagedOperation`** mô tả operation `resetStatistics`.
4. **`AnnotationJmxAttributeSource`** đọc thông tin annotation.
5. **`MetadataMBeanInfoAssembler`** diễn giải thành metadata và có thể quyết định include.
6. **`MBeanExporter`** đăng ký bean theo ObjectName sau khi discovery/naming.
7. **`MBeanServer`** cung cấp runtime API để công cụ bên ngoài truy cập.

Annotation là metadata của code; nó không phải một lệnh tự đăng ký MBean. Exporter phải thực sự được cấu hình và chạy trong Spring context.

## 7. Ví dụ cấu hình Spring rõ ràng

Với Spring Framework thuần, có thể cấu hình exporter cùng assembler và naming strategy phù hợp.

Ví dụ dưới minh họa ý tưởng trong Java configuration:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.naming.MetadataNamingStrategy;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;

@Configuration
public class JmxExportConfig {

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
        MetadataNamingStrategy strategy =
                new MetadataNamingStrategy();
        strategy.setAttributeSource(source);
        return strategy;
    }

    @Bean
    MBeanExporter mBeanExporter(
            MetadataMBeanInfoAssembler assembler,
            MetadataNamingStrategy namingStrategy) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setAssembler(assembler);
        exporter.setNamingStrategy(namingStrategy);
        exporter.setAutodetectModeName("AUTODETECT_ASSEMBLER");
        return exporter;
    }
}
```

Ở cấu hình này, assembler và naming strategy cùng dựa trên **một annotation attribute source**. Điều đó giúp giảm rủi ro assembler chọn bean theo nguồn metadata A nhưng naming strategy lại đặt tên theo nguồn B.

### Các điều kiện để ví dụ có tác dụng

- `QueueManagement` phải được đăng ký là Spring bean, bằng `@Component` hoặc khai báo `@Bean`.
- `@ManagedResource` phải được metadata source nhận diện.
- MBeanServer mà exporter dùng phải tồn tại và được cấu hình đúng; Spring có thể tìm hoặc tạo server theo môi trường.
- Không nên đồng thời cấu hình một exporter khác quét cùng resource và đăng ký cùng ObjectName.
- API constructor/setter và lifecycle cụ thể cần đối chiếu với version Spring được sử dụng.

Ví dụ minh họa **một đường cấu hình**; nhiều dự án có cấu hình đơn giản hơn thông qua XML namespace, annotation exporter hoặc Spring Boot auto-configuration. Không cần copy toàn bộ nếu framework đã quản lý exporter.

## 8. Khai báo bean được autodetect

Ví dụ bean quản trị:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;
import java.util.concurrent.atomic.AtomicInteger;

@Component
@ManagedResource(
    objectName = "com.example.shop.orders:type=Queue,name=outbox",
    description = "Local order queue management")
public class OrderQueueManagement {

    private final AtomicInteger pendingCount = new AtomicInteger();

    public void onQueued() {
        pendingCount.incrementAndGet();
    }

    public void onProcessed() {
        pendingCount.decrementAndGet();
    }

    @ManagedAttribute
    public int getPendingCount() {
        return pendingCount.get();
    }
}
```

Trong cùng ứng dụng, các bean sau không có `@ManagedResource`:

```java
@Component
public class OrderRepositoryAdapter {
    // API nội bộ.
}

@Component
public class PaymentClient {
    // API nội bộ.
}
```

Khi assembler thực hiện discovery dựa trên annotation resource, hai bean thông thường không được chọn chỉ vì chúng là `@Component`. Điều này tránh công bố toàn bộ API của service và repository.

**Nguyên tắc bảo mật:** `@ManagedResource` chỉ đánh dấu tài nguyên có thể export; nó không thay thế xác thực, TLS, phân quyền hoặc chính sách network exposure của JMX connector.

## 9. Quy trình đánh giá bean khi application khởi động

Cách tư duy khi xem cấu hình startup:

```text
Bean "orderQueueManagement"
    |
    +-- Có phải bean trong ApplicationContext? ---- không -> không được quét
    |
    +-- Exporter có autodetection? -------------- không -> chỉ dùng đăng ký tường minh
    |
    +-- AUTODETECT_ASSEMBLER được bật? ---------- không -> áp dụng chế độ khác
    |
    +-- Assembler implement autodetect? -------- không -> không đủ điều kiện cho đường này
    |
    +-- includeBean(...) trả true? ------------- không -> bỏ qua
    |
    +-- Có ObjectName hợp lệ? ------------------- không -> lỗi naming/registration
    |
    +-- ObjectName chưa bị chiếm? -------------- không -> conflict
    |
    +-- MBeanServer.registerMBean thành công? --- có -> client có thể truy vấn
```

Sơ đồ này phân biệt **discovery**, **metadata assembly**, **naming** và **registration**.

Nếu bean không xuất hiện, đừng ngay lập tức cho rằng `@ManagedAttribute` bị lỗi. Có thể bean không được quét, bị assembler loại, ObjectName không hợp lệ hoặc exporter gặp conflict.

## 10. Phân biệt autodetection với export tường minh

Autodetection và `setBeans` có mục đích khác nhau.

### Export tường minh

```java
import java.util.Map;
import org.springframework.jmx.export.MBeanExporter;

MBeanExporter exporter = new MBeanExporter();
exporter.setBeans(Map.of(
    "com.example.shop.orders:type=Queue,name=outbox",
    orderQueueManagementBean
));
```

Cách này yêu cầu code/cấu hình **đưa bean vào danh sách export**. Nó phù hợp khi số MBean nhỏ hoặc cần allowlist chính xác.

### Autodetection dựa trên assembler

```java
exporter.setAssembler(metadataAssembler);
exporter.setAutodetectModeName("AUTODETECT_ASSEMBLER");
```

Exporter tự tìm beans mà assembler cho phép. Không cần liệt kê ObjectName → bean thủ công cho từng resource, nhưng vẫn cần đặt naming strategy và quản lý sự nhất quán của annotation.

**Không giả định:** `setBeans` là bộ lọc bổ sung cho tất cả autodetected beans. Với một exporter có cả hai cấu hình, danh sách bean tường minh và tập autodetect có thể là các đường export khác nhau. Nếu muốn chỉ export tập nhỏ, đừng bật autodetect rộng rồi nghĩ `setBeans` sẽ giới hạn mọi thứ.

### Khi nào chọn cách nào?

| Bối cảnh | Hướng thường hợp lý |
|---|---|
| Chỉ 2–3 management beans | Export tường minh dễ kiểm soát |
| Nhiều module có annotation JMX nhất quán | Autodetect bằng assembler |
| Bảo mật yêu cầu allowlist chặt | Export tường minh hoặc autodetect với policy đã kiểm thử |
| Thư viện mang MBeans sẵn | Cân nhắc autodetect MBean hoặc đăng ký tường minh |
| Ứng dụng có nhiều `@ManagedResource` do thư viện cung cấp | Rà soát phạm vi autodetect trước khi bật |
| Cần ObjectName động theo deployment | Naming strategy/factory có chủ đích |

## 11. Một assembler autodetect tùy chỉnh hoạt động ra sao?

Một ứng dụng có thể muốn chỉ xuất các bean quản trị thuộc một package hoặc convention cụ thể. Nếu tự xây assembler, bạn cần bảo đảm cả **chức năng tạo metadata** lẫn **quy tắc include**.

Ý tưởng đơn giản:

```java
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;

public class RestrictedManagementAssembler
        extends MetadataMBeanInfoAssembler {

    @Override
    public boolean includeBean(Class<?> beanClass, String beanName) {
        return beanName.endsWith("Management")
                && super.includeBean(beanClass, beanName);
    }
}
```

Điểm chính:

- Điều kiện `super.includeBean` giữ nguyên kiểm tra managed-resource metadata.
- Kiểm tra hậu tố bean name chỉ là một policy bổ sung theo convention.
- Bean không được export nếu thiếu cả tên phù hợp hoặc annotation resource.

**Hạn chế của ví dụ:** Bean name thường do developer, `@Bean` method hoặc component scanner quyết định, không tự bắt buộc kết thúc `Management`. Policy dựa vào tên có thể bỏ sót resource hợp lệ. Với hệ thống thật, nên dùng một convention được kiểm thử và tránh phụ thuộc tên class runtime của AOP proxy.

Một policy dựa vào package cũng cần xử lý target class đúng nếu bean bị proxy. Không tự suy ra `beanClass.getPackageName()` luôn trỏ tới package của target implementation.

## 12. Metadata assembler không phải bộ lọc quyền truy cập

`includeBean` quyết định bean được chọn để **export** hay không. Nó không quyết định client nào có thể đọc hoặc gọi operations sau khi export.

Ví dụ:

```java
@ManagedResource(
    objectName = "com.example.shop:type=JobController,name=primary")
public class JobManagement {

    @ManagedOperation
    public void restartWorkers() {
        // Có thể gây ảnh hưởng vận hành.
    }
}
```

Nếu resource này được autodetect, operation có thể được công bố cho các JMX clients có quyền tương ứng. `@ManagedOperation` không tự kích hoạt một mô hình phân quyền nghiệp vụ theo role.

Do đó:

1. Không annotate các operation nhạy cảm chỉ để tiện debug.
2. Hạn chế JMX remote exposure.
3. Cấu hình authentication/TLS/authorization phù hợp với cách triển khai.
4. Có audit/rate limit khi operation có tác động đáng kể.
5. Xem annotation JMX như một phần của public management API.

Autodetection chỉ là **cơ chế selection**. Nó không làm MBean an toàn hơn hay kém hơn về mặc định; mức độ rủi ro phụ thuộc những gì được export và cách truy cập được bảo vệ.

## 13. Tại sao chỉ có @ManagedAttribute chưa đủ?

Một lớp có:

```java
@Component
public class InternalStatistics {

    @ManagedAttribute
    public int getWorkerCount() {
        return 5;
    }
}
```

Nhưng không có `@ManagedResource` trên class.

Với metadata-based autodetection điển hình, assembler phải xác định **class được phép trở thành managed resource**. Nếu tiêu chí include dựa trên `ManagedResource`, class này sẽ không được chọn, dù getter có annotation.

Cách rõ ràng:

```java
@Component
@ManagedResource(
    objectName = "com.example.shop:type=WorkerStats,name=primary")
public class WorkerStatisticsManagement {

    @ManagedAttribute
    public int getWorkerCount() {
        return 5;
    }
}
```

Đây là cách diễn đạt rõ “đối tượng này là MBean” và “getter này là attribute”. Trong dự án có custom attribute source/assembler, quy tắc include có thể khác; hãy kiểm tra implementation thực tế.

## 14. Annotation và management interface khác nhau thế nào trong autodetect?

Một Standard MBean có management interface:

```java
public interface CacheMonitorMBean {
    int getEntryCount();
}
```

```java
public class CacheMonitor implements CacheMonitorMBean {
    @Override
    public int getEntryCount() {
        return 10;
    }
}
```

Nó có thể được phát hiện theo chế độ **autodetect MBean**.

Một annotation-driven resource:

```java
@ManagedResource(objectName =
    "com.example.shop.catalog:type=Cache,name=products")
public class CacheManagement {

    @ManagedAttribute
    public int getEntryCount() {
        return 10;
    }
}
```

có thể được phát hiện theo **assembler**.

Hai contract khác nhau:

- Standard MBean: interface `CacheMonitorMBean` xác định surface JMX.
- Annotation-driven: các `@Managed...` và assembler xác định surface JMX.

Không nên cho rằng cấu hình assembler sẽ tự tìm mọi `*MBean` interface, hoặc chế độ MBean discovery sẽ diễn giải tất cả `@Managed...` theo cùng một cách.

Nếu chọn `AUTODETECT_ALL`, phải hiểu rõ hai cơ chế và kiểm tra runtime metadata, tránh dựa vào suy đoán “được union” để thiết kế API quản trị.

## 15. Tương tác với Spring AOP proxy

Spring có thể tạo JDK dynamic proxy hoặc CGLIB proxy cho beans dùng `@Transactional`, `@Cacheable`, security, retry hoặc custom advice.

Giả sử:

```java
@ManagedResource(objectName =
    "com.example.shop.orders:type=OrderMonitor,name=main")
public class OrderMonitor {
    @ManagedAttribute
    public int getPendingCount() { return 5; }
}
```

nhưng bean runtime lại là proxy.

Các câu hỏi cần xác định:

1. Assembler đánh giá **proxy class** hay **target class** khi gọi include?
2. Attribute source có tìm được `@ManagedResource` trên target không?
3. JDK proxy có expose method được annotate không?
4. Nếu MBean đăng ký thành công, client có thực sự đọc được attribute không?

Lưu ý:

- JDK proxy thường chỉ expose methods của interfaces mà nó triển khai.
- CGLIB proxy kế thừa class nhưng có giới hạn với `final` và method visibility.
- Spring có utility như `AopUtils.isAopProxy` và `AopUtils.getTargetClass` để hỗ trợ điều tra.
- Không nên unwrap target rồi export trực tiếp nếu điều đó bỏ qua transaction/security advice.

Một giải pháp kiến trúc rõ ràng là **management adapter** ít bị AOP tác động, gọi nghiệp vụ qua injected service proxy.

```java
@Component
@ManagedResource(objectName =
    "com.example.shop.orders:type=OrderMonitor,name=main")
public class OrderManagement {

    private final OrderService service;

    public OrderManagement(OrderService service) {
        this.service = service;
    }

    @ManagedAttribute
    public int getPendingCount() {
        return service.pendingCount();
    }
}
```

Adapter chỉ có responsibility quản trị; target business service không cần annotation JMX. Tuy nhiên adapter cũng có thể bị pointcut AOP rộng tác động, nên vẫn cần kiểm tra cấu hình runtime.

## 16. Đặt ObjectName bằng metadata naming strategy

Khi annotation-driven discovery dùng `@ManagedResource(objectName="...")`, naming strategy nên đọc cùng nguồn metadata.

Ví dụ:

```text
Managed resource:
  bean name = queueManagement
  class = OrderQueueManagement

Annotation:
  @ManagedResource(
      objectName = "com.example.shop.orders:type=Queue,name=outbox"
  )

MBeanServer:
  com.example.shop.orders:type=Queue,name=outbox
```

Không nhầm:

- **Spring bean name**: key trong ApplicationContext.
- **Java class name**: class implementation hoặc proxy.
- **JMX ObjectName**: định danh quản lý trong MBeanServer.

Nếu naming strategy sinh ObjectName từ bean name nhưng annotation lại chứa ObjectName khác, việc điều tra sẽ khó khăn. Có thể dùng naming strategy khác theo chủ đích; chỉ cần đảm bảo một convention rõ ràng, có owner và được test.

**Không cần** nhét environment hay pod ID vào domain/ObjectName nếu monitoring đã dùng metadata kết nối/instance để phân biệt JVM. ObjectName chỉ cần duy nhất trong cùng một MBeanServer.

## 17. Kiểm tra danh sách MBean được autodetect

Đừng chỉ dựa vào message “exporter initialized”. Hãy truy vấn MBeanServer thật:

```java
import java.lang.management.ManagementFactory;
import java.util.Set;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class DiscoveredMBeansDemo {

    public static void main(String[] args) throws Exception {
        MBeanServer server =
                ManagementFactory.getPlatformMBeanServer();

        ObjectName pattern = new ObjectName(
                "com.example.shop.*:*");

        Set<ObjectName> names =
                server.queryNames(pattern, null);

        names.stream()
                .map(ObjectName::getCanonicalName)
                .sorted()
                .forEach(System.out::println);
    }
}
```

Đoạn code trên giả định exporter đăng ký vào platform MBeanServer; nếu có server custom, phải dùng đúng server của exporter.

Pattern `com.example.shop.*:*` tìm domain bắt đầu với `com.example.shop.`. Nó **không** bao gồm domain chính xác `com.example.shop`; nếu hệ thống dùng cả hai kiểu, cần query riêng hoặc chuẩn hóa naming.

Đọc metadata một MBean:

```java
import javax.management.MBeanInfo;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanOperationInfo;

ObjectName name = new ObjectName(
    "com.example.shop.orders:type=Queue,name=outbox");

MBeanInfo info = server.getMBeanInfo(name);

for (MBeanAttributeInfo attribute : info.getAttributes()) {
    System.out.println("Attribute: " + attribute.getName());
}
for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.println("Operation: " + operation.getName());
}
```

Cần xác minh cả:

- Bean mong muốn có xuất hiện.
- Bean nội bộ không mong muốn **không** xuất hiện.
- Attribute/operation được công bố đúng.
- ObjectName đúng convention.
- Không có exporter trùng, lỗi registration hoặc bean lifecycle bất thường.

## 18. Integration test cho autodetection

Với một Spring integration test, có thể khởi động context chứa:

- Một `@ManagedResource` bean được phép export.
- Một `@Component` không có annotation resource.
- Một exporter `AUTODETECT_ASSEMBLER` và assembler phù hợp.
- Một MBeanServer dành riêng cho test để tránh ảnh hưởng JMX toàn tiến trình.

Các điều kiện cần assert:

```text
Expected:
  com.example.shop.orders:type=Queue,name=outbox
  isRegistered = true

Not expected:
  com.example.shop.internal:type=Repository,name=main
  isRegistered = false
```

Nếu muốn tự kiểm chứng chương trình:

```java
import javax.management.MBeanServer;
import javax.management.ObjectName;

public final class JmxAssertions {

    public static void assertRegistered(
            MBeanServer server, String name) throws Exception {
        if (!server.isRegistered(new ObjectName(name))) {
            throw new AssertionError("Missing MBean: " + name);
        }
    }

    public static void assertNotRegistered(
            MBeanServer server, String name) throws Exception {
        if (server.isRegistered(new ObjectName(name))) {
            throw new AssertionError("Unexpected MBean: " + name);
        }
    }
}
```

Trong dự án thực tế, tích hợp JUnit 5/Spring Test và lấy MBeanServer trực tiếp từ test context. Một test chỉ kiểm tra được bean được export là chưa đủ; cần test **không công bố nhầm** service nội bộ.

## 19. Vòng đời, đăng ký trùng và các exporter khác

Một số lỗi thường gặp khi bật autodetection:

### 19.1. Đăng ký trùng ObjectName

```text
Annotation exporter -------+
                           +--> same ObjectName
Manual MBeanExporter ------+
```

Nếu hai exporter cùng đăng ký một ObjectName vào cùng MBeanServer, có thể nhận `InstanceAlreadyExistsException`. Các registration policies của Spring có thể xử lý trường hợp đã tồn tại theo những cách khác nhau, nhưng không nên dùng chúng để che một thiết kế export owner không rõ ràng.

**Khuyến nghị:** Mỗi MBean có một chủ sở hữu registration. Nếu có auto-configuration khác, hiểu xem nó đã tạo exporter hay chưa trước khi thêm exporter thủ công.

### 19.2. Bean không được đăng ký trong ApplicationContext

`@ManagedResource` trên một object tạo bằng `new` nằm ngoài Spring context không làm exporter tự tìm object ấy. Đối tượng phải được cung cấp cho exporter hoặc là Spring bean được quét trong phạm vi autodetection.

### 19.3. Bean xuất hiện trước khi sẵn sàng

Autodetection/registration thường diễn ra trong lifecycle khởi tạo exporter và context. Nếu management getter truy cập component chưa sẵn sàng, có thể gây lỗi runtime. Hãy thiết kế attribute thể hiện trạng thái initialization, tránh để JMX getter block hoặc khởi động tài nguyên nặng.

### 19.4. Autodetection trên bean infrastructure

Không nên cố xuất tự động mọi bean. Các thành phần như `DataSource`, repository, serializer, security manager và client wrapper có thể có nhiều method public nhưng không phải public management contract. Dùng annotation resource hoặc mapping tường minh theo chính sách để thu hẹp phạm vi.

## 20. Lưu ý về Spring Boot và auto-configuration

Spring Boot cung cấp nhiều tiện ích quản trị, ví dụ Actuator endpoints và khả năng expose quản trị qua JMX theo cấu hình. Cần phân biệt:

- Spring Framework JMX exporter cho các bean custom mang `@ManagedResource`.
- Spring Boot Actuator endpoints có thể được expose qua JMX tùy cấu hình.
- JVM platform MBeans như `java.lang:type=Memory` là MBeans chuẩn của JVM.
- Micrometer metrics và Actuator metric endpoints là một cơ chế đo lường và exposure liên quan nhưng không đồng nghĩa với assembler autodetection.

Khi ứng dụng dùng Boot, **không tự tạo thêm AnnotationMBeanExporter** chỉ vì thấy annotation mà chưa biết Boot đã thiết lập cơ chế export nào. Cần kiểm tra effective configuration và MBeanServer thực tế.

Một thay đổi configuration hoặc dependency có thể kích hoạt exporter khác, tạo xung đột ObjectName. Integration test khởi động đúng Spring profile giúp phát hiện khác biệt giữa local/staging/production.

## 21. Những hiểu lầm thường gặp

| Hiểu lầm | Giải thích |
|---|---|
| “Autodetect assembler export mọi bean.” | Chỉ các bean thỏa tiêu chí của assembler có khả năng autodetect |
| “Có `@ManagedAttribute` là class tự được phát hiện.” | Với metadata assembler phổ biến, resource-level `@ManagedResource` mới là dấu hiệu chính |
| “Assembler chỉ tạo tên method, không chọn bean.” | `AutodetectCapableMBeanInfoAssembler` có thể quyết định include |
| “Bean name chính là ObjectName.” | Hai namespace khác nhau, naming strategy quyết định JMX identity |
| “Autodetection là bảo mật.” | Nó chỉ chọn resource; authorization/TLS phải cấu hình riêng |
| “MBean có attribute nên chắc export đúng.” | Cần kiểm tra cả ObjectName, operations, descriptions và phạm vi |
| “Dùng `AUTODETECT_ALL` luôn tiện hơn.” | Phạm vi rộng hơn có thể công bố ngoài dự tính |
| “Có thể bật nhiều exporter cùng lúc mà không cần kiểm tra.” | Có thể trùng ObjectName và behavior phụ thuộc registration policy |
| “`@ManagedResource` tự chạy trên class không phải bean.” | Exporter chỉ biết các object trong scope của nó |
| “Proxy luôn giữ nguyên annotation như class gốc.” | Metadata lookup và method exposure phụ thuộc proxy/assembler |

## 22. Bài tập thực hành

### Bài tập 1 — Dự đoán bean được chọn

Cho ba Spring beans:

```java
@Component
@ManagedResource(objectName =
    "com.example.shop:type=Cache,name=products")
class ProductCacheManagement {
    @ManagedAttribute
    public int getEntryCount() { return 10; }
}

@Component
class InternalRepository {
    public int countRows() { return 100; }
}

@Component
class WorkerState {
    @ManagedAttribute
    public int getActiveCount() { return 3; }
}
```

Với `AUTODETECT_ASSEMBLER` sử dụng `MetadataMBeanInfoAssembler` và `AnnotationJmxAttributeSource`, hãy dự đoán bean nào được chọn và lý giải vai trò `@ManagedResource`.

**Đáp án định hướng:** `ProductCacheManagement` có resource metadata. `InternalRepository` không có annotation JMX. `WorkerState` chỉ có method-level annotation nhưng không có resource annotation, nên không thỏa điều kiện include phổ biến theo managed resource metadata.

### Bài tập 2 — Thực hiện test không export nhầm

Khởi tạo Spring test context với một management bean và một service nội bộ. Viết assertions:

- Management ObjectName được đăng ký.
- Internal ObjectName không xuất hiện.
- MBeanInfo chỉ có những operations thực sự được annotate.

Điều tra lỗi test bằng cách kiểm tra mode, assembler và attribute source trước khi đổi component scanning.

### Bài tập 3 — Phân biệt hai mode

Tạo một Standard MBean có interface `SampleMonitorMBean` và một annotation-based MBean `@ManagedResource`.

Chạy hai Spring contexts tách biệt:

- Context A dùng `AUTODETECT_MBEAN`.
- Context B dùng `AUTODETECT_ASSEMBLER` kèm metadata assembler.

So sánh ObjectNames và MBeanInfo. Không đăng ký hai contexts vào cùng server với cùng ObjectName nếu không kiểm soát xung đột.

### Bài tập 4 — Bổ sung policy theo bean name

Xây assembler custom chỉ nhận bean có hậu tố `Management` và đồng thời có managed-resource metadata. Test một bean hợp lệ và một bean bị loại. Thảo luận nhược điểm khi bean name thay đổi do refactor hoặc `@Bean` method naming.

### Bài tập 5 — Lỗi proxy và annotation

Gắn `@Transactional` lên một service có JMX annotations, khiến nó có thể được proxy. Dùng `AopUtils` để xem type runtime và target class. Sau đó kiểm tra MBeanInfo. Nếu metadata bị thiếu hoặc invocation lỗi, tạo management adapter tách biệt thay vì cố unwrap target một cách tùy tiện.

## 23. Câu hỏi tự kiểm tra

**1. `AUTODETECT_ASSEMBLER` được dùng để làm gì?**

Để exporter xét các Spring beans theo tiêu chí của assembler có khả năng autodetect, thay vì chỉ tự nhận diện Standard/Dynamic MBeans.

**2. `MetadataMBeanInfoAssembler` làm việc với annotation như thế nào?**

Nó dùng `JmxAttributeSource` (chẳng hạn `AnnotationJmxAttributeSource`) để đọc managed-resource/method metadata rồi tạo MBeanInfo, đồng thời hỗ trợ tiêu chí include tương ứng.

**3. Chỉ gắn `@ManagedAttribute` trên một getter đã đủ để bean được autodetect chưa?**

Không nên coi là đủ. Với annotation metadata discovery thường dùng, cần resource metadata như `@ManagedResource` ở class.

**4. `setBeans` có phải là danh sách giới hạn bắt buộc của autodetection không?**

Không. Đăng ký tường minh và autodetection có thể là hai đường lựa chọn; phải xem cấu hình exporter thực tế.

**5. Vì sao phải kiểm tra cả bean không được export?**

Vì việc vô tình công bố các service nội bộ hoặc operations nhạy cảm có thể tạo rủi ro và làm khó quản lý API vận hành.

**6. Nếu exporter tìm được bean nhưng ObjectName sai, đã gọi là autodetection đúng hoàn toàn chưa?**

Chưa. Discovery chỉ là một bước; naming và registration cũng phải phù hợp với management contract.

**7. Có nên bật `AUTODETECT_ALL` mà không quan sát phạm vi bean không?**

Không nên. Cần hiểu những MBeans và resources nào có thể bị chọn, rồi kiểm tra kết quả runtime.

## 24. Ghi nhớ

- **Assembler-based autodetection** là khả năng của `MBeanExporter` để chọn Spring beans dựa trên `AutodetectCapableMBeanInfoAssembler.includeBean(...)`.
- Với annotation-driven JMX, `MetadataMBeanInfoAssembler` và `AnnotationJmxAttributeSource` là bộ đôi thường dùng để đọc `@ManagedResource` và các `@Managed...` methods.
- `@ManagedResource` thể hiện resource intent; `@ManagedAttribute`/`@ManagedOperation` thể hiện surface API của MBean.
- `AUTODETECT_ASSEMBLER` khác `AUTODETECT_MBEAN`; `AUTODETECT_ALL` có thể kết hợp phạm vi và cần kiểm chứng.
- Autodetection không tự là allowlist bảo mật hay đảm bảo đúng ObjectName. Cần một export owner và naming strategy thống nhất.
- Spring AOP proxies, cấu hình auto-export và vòng đời bean có thể ảnh hưởng discovery/invocation.
- Kiểm tra `MBeanServer` và `MBeanInfo` thực tế, cả các resources mong muốn và những beans không được phép xuất hiện.
- Khi cần kiểm soát phạm vi chặt hoặc MBean ít, export tường minh vẫn là lựa chọn hợp lý.

## 25. Tài liệu tham khảo

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework Javadoc — `MBeanExporter`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Spring Framework Javadoc — `AutodetectCapableMBeanInfoAssembler`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/assembler/AutodetectCapableMBeanInfoAssembler.html
- Spring Framework Javadoc — `MetadataMBeanInfoAssembler`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/assembler/MetadataMBeanInfoAssembler.html
- Spring Framework Javadoc — `AnnotationJmxAttributeSource`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/AnnotationJmxAttributeSource.html
- Java SE 21 — `MBeanServer`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
