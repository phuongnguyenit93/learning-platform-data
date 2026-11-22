# Chọn một nguồn metadata duy nhất để tránh khó đoán trong Spring JMX

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích **management metadata** trong JMX gồm những gì và vì sao phải xác định rõ một nguồn quy định contract cho mỗi MBean.
- Phân biệt Standard MBean interface, MXBean interface, annotation `@ManagedResource`/`@ManagedAttribute`/`@ManagedOperation`, metadata assembler và cấu hình `MBeanExporter`.
- Nhận diện các trường hợp cùng một bean bị nhiều cơ chế export, naming strategy hoặc assembler diễn giải khác nhau.
- Thiết kế một **nguồn chân lý duy nhất (single source of truth)** cho attributes, operations, descriptions và ObjectName của mỗi MBean.
- Chọn phương pháp kiểm chứng qua `MBeanServer.getMBeanInfo()` thay vì chỉ dựa vào code annotations hoặc interface.
- Lập quy tắc phối hợp giữa service nghiệp vụ, management adapter, Spring AOP proxy, collector và công cụ vận hành.

## 2. Vấn đề: một MBean nhưng nhiều nơi khai báo metadata

Trong Java Management Extensions (JMX), **MBean management interface** xác định người vận hành có thể quan sát hoặc điều khiển điều gì. Với Standard MBean, interface theo quy ước tên `ClassNameMBean`; với MXBean, interface được nhận diện là MXBean; với Spring, metadata có thể được khai báo bằng annotation và ánh xạ qua assembler.

Khi một dự án có nhiều cơ chế cùng xuất hiện, ví dụ:

```text
OrderMonitorMBean.java       --> khai báo getPendingCount(), reset()
OrderMonitor.java            --> @ManagedAttribute, @ManagedOperation
Spring configuration        --> MBeanExporter + naming strategy
Another auto-configuration  --> tự scan/export @ManagedResource
```

các developer có thể tưởng rằng mọi khai báo sẽ được “gộp” vào cùng một MBean. Thực tế, **JMX metadata được tạo theo cơ chế export đang được sử dụng**; không có quy tắc tổng quát rằng các nguồn metadata độc lập sẽ được hợp nhất với ưu tiên luôn giống nhau.

Kết quả có thể là:

- Attributes/operations hiện ra khác với dự kiến.
- Một attribute có description ở annotation nhưng JConsole hiển thị description khác.
- MBean có tên khác naming convention.
- Cùng một ObjectName bị hai exporter đăng ký dẫn đến xung đột.
- AOP proxy làm annotation lookup nhận ra class/interface không như mong muốn.
- Một lần refactor làm đổi metadata dù Java business API không thay đổi.

**Nguyên tắc trung tâm:** Mỗi MBean nên có **một contract quản trị được chỉ định rõ**, và một đường export chủ đạo chịu trách nhiệm biến contract đó thành `MBeanInfo` trong `MBeanServer`.

## 3. JMX management metadata gồm những gì?

Một `MBeanInfo` thường mô tả:

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| **Attributes** | Thuộc tính đọc/ghi, kiểu dữ liệu, description | `PendingCount` (int, read-only) |
| **Operations** | Thao tác quản trị và tham số | `resetStatistics()` |
| **Constructors** | Metadata constructor khi áp dụng | Constructor descriptions |
| **Notifications** | Các loại notification MBean có thể phát | `queue.threshold.exceeded` |
| **Description** | Mô tả MBean hoặc thành phần | `Order queue monitor` |
| **Descriptors** | Metadata mở rộng theo JMX model | Units, display conventions tùy assembler |

**ObjectName** là định danh dùng để đăng ký và truy vấn MBean; nó không đơn thuần là một field nằm trong `MBeanInfo`. Trong cấu hình Spring, ObjectName có thể đến từ `@ManagedResource.objectName`, tên được đặt tường minh hoặc naming strategy.

Do đó khi nói “một nguồn metadata”, cần làm rõ hai mặt:

1. **Management contract:** attributes/operations/notifications/descriptions được khai báo từ đâu?
2. **Registration contract:** ObjectName và vòng đời export được quyết định ở đâu?

Có thể có một naming convention dùng chung, nhưng không nên để các exporter cạnh tranh chọn ObjectName cho cùng một instance.

## 4. Những nguồn metadata phổ biến trong Java/Spring JMX

### 4.1. Standard MBean interface

Ví dụ:

```java
public interface OrderMonitorMBean {
    int getPendingCount();
    void resetStatistics();
}

public class OrderMonitor implements OrderMonitorMBean {
    @Override
    public int getPendingCount() {
        return 17;
    }

    @Override
    public void resetStatistics() {
        // Reset counters only.
    }
}
```

Với convention Standard MBean, **interface `OrderMonitorMBean`** là contract được JMX introspection diễn giải thành attributes và operations.

Những public methods khác của `OrderMonitor` nhưng không nằm trong interface không tự trở thành JMX operations.

Ưu điểm:

- Contract tường minh, dễ đọc và kiểm thử.
- Java compiler giúp đảm bảo implementation thỏa interface.
- Không cần gắn annotation riêng lên từng method nếu chỉ cần metadata cơ bản.

Đánh đổi:

- Description hoặc metadata phong phú có thể cần cơ chế bổ sung.
- Cần tuân thủ quy ước tên hoặc dùng `StandardMBean` wrapper phù hợp.
- Dùng interface JMX thuần không tự quyết định object name, quyền kết nối hay lifecycle.

### 4.2. MXBean interface

MXBean cũng lấy contract từ interface nhưng có quy tắc ánh xạ dữ liệu Java sang **open types** dùng trong JMX interoperability. Ví dụ:

```java
public interface QueueMetricsMXBean {
    int getPendingCount();
    String getQueueName();
}
```

Khi chọn MXBean, contract quản trị nên nằm trong interface MXBean đã định nghĩa. Không nên đồng thời thêm một lớp metadata annotation khác mà người đọc tưởng là nguồn bắt buộc được diễn giải.

MXBean phù hợp khi muốn công bố cấu trúc dữ liệu có khả năng trao đổi giữa process/client mà không cần phân phối toàn bộ class tùy chỉnh của server. Không phải mọi kiểu Java đều có mapping trực tiếp; cần hiểu quy tắc open type của MXBean.

### 4.3. Annotation-driven Spring JMX

Spring cung cấp:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.shop.orders:type=OrderMonitor,name=primary",
    description = "Order monitoring endpoint")
public class OrderManagement {

    @ManagedAttribute(description = "Pending orders in this JVM")
    public int getPendingCount() {
        return 17;
    }

    @ManagedOperation(description = "Reset monitoring counters")
    public void resetStatistics() {
        // ...
    }
}
```

Ở đây, nhóm annotation là **nguồn metadata quản trị**. Để hoạt động, bean cần được exporter/assembler phù hợp xử lý. Chỉ gắn annotation lên Java class không đảm bảo MBean xuất hiện trên MBeanServer.

Lợi ích:

- Dễ bổ sung description và thông tin method.
- Có thể dùng một management adapter riêng cho JMX mà không cần interface `*MBean`.
- Hợp với ứng dụng Spring đang sử dụng component scanning/export.

Đánh đổi:

- Metadata discovery phụ thuộc exporter/assembler và cách proxy được xử lý.
- Cần giữ annotation tập trung ở lớp quản trị, không rải trên nhiều layer.
- Đổi cấu hình export có thể làm metadata khác đi.

### 4.4. Dynamic MBean hoặc ModelMBean

`DynamicMBean` cho phép component tự cung cấp `getMBeanInfo()` và xử lý attribute/operation. `ModelMBean` có các descriptor và cấu hình metadata chi tiết.

Đây là những mô hình quản trị có khả năng tùy biến sâu, phù hợp một số trường hợp framework/plugin. Nhưng khi đã chọn dynamic metadata, **không nên đồng thời coi Standard MBean naming convention và Spring annotations là hai contract cạnh tranh** mà không có thiết kế hợp nhất rõ ràng.

## 5. Vì sao “gộp tất cả” tạo hành vi khó đoán?

Giả sử:

```java
public interface PaymentMonitorMBean {
    int getPendingCount();
}
```

Implementation lại có annotations:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.shop.payments:type=Monitor,name=main")
public class PaymentMonitor implements PaymentMonitorMBean {

    @Override
    @ManagedAttribute(description = "Payments waiting")
    public int getPendingCount() {
        return 12;
    }

    @ManagedOperation(description = "Reconcile payment states")
    public void reconcilePayments() {
        // ...
    }
}
```

Một developer có thể mong cả `PendingCount` từ interface lẫn `reconcilePayments()` từ annotation đều được công bố.

Tuy nhiên:

- Nếu bean được JMX introspect như **Standard MBean**, contract chính là `PaymentMonitorMBean`; `reconcilePayments()` không nằm trong interface đó.
- Nếu Spring dùng **annotation-based metadata assembler**, attributes/operations được chọn theo annotation của cơ chế này; `reconcilePayments()` có thể xuất hiện.
- Nếu có **hai exporter** cùng cố register ObjectName, một registration có thể thất bại với `InstanceAlreadyExistsException`.
- Nếu bean bị JDK dynamic proxy, method `reconcilePayments()` không có trong interface có thể không được proxy expose, tạo thêm vấn đề metadata/invocation.

Đây là những hệ quả phụ thuộc **export path thực tế**, không có một thứ tự ưu tiên “interface luôn thắng annotation” cho tất cả cấu hình Spring.

Mục tiêu không phải cấm interface + annotation cùng tồn tại trong source code, mà là **không để hai nguồn được hiểu là hợp đồng công khai đồng thời khi chưa xác định rõ cơ chế chọn metadata**.

## 6. Quy tắc single source of truth cho một MBean

Có thể định nghĩa chính sách ở cấp dự án:

> Mỗi ObjectName có đúng một owner quản trị và một cơ chế định nghĩa attributes/operations được công nhận. Mọi thông tin còn lại là implementation detail hoặc tài liệu phụ trợ, không phải contract thứ hai.

Quy tắc cụ thể:

1. **Chọn contract style:** Standard MBean, MXBean, annotation-driven hoặc DynamicMBean.
2. **Chọn export owner:** một MBeanExporter hoặc cơ chế đăng ký JMX được chỉ định.
3. **Chọn naming strategy:** ObjectName tường minh hoặc một factory/naming strategy chuẩn.
4. **Không export cùng một bean hai lần** dưới cùng ObjectName bằng các cơ chế khác nhau.
5. **Không rải annotation quản trị** trên nhiều service/interface rồi kỳ vọng Spring tự gộp chúng theo ý muốn.
6. **Kiểm chứng metadata thực tế** qua MBeanInfo sau khi app khởi động.
7. **Đổi metadata như đổi API contract:** đánh giá tác động lên JConsole, exporter, dashboard và automation.

Chính sách này không yêu cầu mọi MBean trên toàn công ty cùng một style. Một hệ thống có thể dùng Standard MBean cho thư viện và annotation Spring cho các adapter nội bộ, miễn mỗi MBean có một nguồn contract rõ ràng.

## 7. Cách A — Lấy interface làm nguồn chính

Nếu muốn management interface là hợp đồng duy nhất, thiết kế:

```text
OrderMonitorMBean.java   <-- contract quản trị
         |
         v
OrderMonitor.java        <-- implementation
         |
         v
MBeanServer              <-- đăng ký theo ObjectName
```

Ví dụ runnable không cần Spring:

**`OrderMonitorMBean.java`**

```java
public interface OrderMonitorMBean {
    int getPendingCount();
    void resetStatistics();
}
```

**`OrderMonitor.java`**

```java
public class OrderMonitor implements OrderMonitorMBean {
    private int pendingCount = 5;

    @Override
    public int getPendingCount() {
        return pendingCount;
    }

    @Override
    public void resetStatistics() {
        pendingCount = 0;
    }

    public void importOrders() {
        // API nội bộ, không nằm trong management interface.
    }
}
```

**`StandardMBeanDemo.java`**

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class StandardMBeanDemo {
    public static void main(String[] args) throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();
        ObjectName name = new ObjectName(
                "com.example.shop.orders:type=OrderMonitor,name=main");

        server.registerMBean(new OrderMonitor(), name);
        try {
            System.out.println(
                    server.getAttribute(name, "PendingCount"));
            server.invoke(name, "resetStatistics",
                    new Object[0], new String[0]);
        } finally {
            server.unregisterMBean(name);
        }
    }
}
```

Trong cách này:

- Interface là một nguồn chân lý cho surface API.
- Class cài đặt không khai báo thêm `@ManagedAttribute` để “mở rộng” contract.
- ObjectName được quyết định tại chỗ registration hoặc factory chuyên biệt.
- JMX client dùng attribute `PendingCount` và operation `resetStatistics`, không nhìn thấy `importOrders`.

Nếu cần description phong phú, có thể chọn cơ chế metadata khác có chủ đích, nhưng phải **công bố rõ chỗ nào quyết định API** và kiểm tra kết quả.

## 8. Cách B — Dùng annotation-driven management adapter

Trong ứng dụng Spring, một adapter quản trị riêng là mô hình dễ duy trì:

```text
OrderProcessingService (business interface)
              ^
              |
DefaultOrderProcessingService (business logic + AOP)
              ^
              | được gọi qua proxy
              |
OrderManagement (JMX annotations)
              |
              v
Annotation-aware exporter -> MBeanServer
```

Ví dụ:

```java
public interface OrderProcessingService {
    int pendingCount();
}
```

```java
import org.springframework.stereotype.Service;

@Service
public class DefaultOrderProcessingService
        implements OrderProcessingService {

    @Override
    public int pendingCount() {
        return 5;
    }
}
```

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.shop.orders:type=OrderMonitor,name=main",
    description = "Read-only order monitoring")
public class OrderManagement {

    private final OrderProcessingService service;

    public OrderManagement(OrderProcessingService service) {
        this.service = service;
    }

    @ManagedAttribute(description = "Pending orders in local instance")
    public int getPendingCount() {
        return service.pendingCount();
    }
}
```

Trong cách này:

- Mọi `@Managed...` dành cho MBean này nằm tại `OrderManagement`.
- Business service không cần mang annotation JMX.
- Spring exporter cần được bật và có annotation-aware assembler phù hợp.
- Không tạo `OrderManagementMBean` chỉ để định nghĩa thêm một contract khác nếu đã quyết định lấy annotation làm nguồn chân lý.
- Nếu service được Spring AOP proxy, management adapter gọi qua interface service để giữ advice và boundary rõ ràng.

**Lưu ý:** Adapter vẫn có thể bị AOP proxy bởi pointcut rộng. Khi đó cần xác minh target-class resolution, method accessibility và metadata thực tế. Single source of truth giải quyết sự mơ hồ hợp đồng, không tự giải quyết mọi vấn đề proxy.

## 9. Cách C — MXBean cho dữ liệu quản trị có kiểu rõ ràng

Nếu hệ thống muốn client bên ngoài JVM có khả năng đọc dữ liệu phức tạp qua open types, có thể chọn MXBean:

```java
public interface QueueStatusMXBean {
    int getPendingCount();
    String getState();
}
```

Với MXBean:

- Interface MXBean là contract.
- Kiểu dữ liệu phải có mapping theo quy tắc MXBean.
- Dùng `ObjectName` ổn định và đăng ký theo cơ chế thích hợp.
- Không xây thêm một lớp annotation contract cạnh tranh trừ khi có lý do và cấu hình rõ.

Khác biệt Standard MBean và MXBean không phải “một bên có metadata, một bên không”; cả hai đều có metadata. MXBean có quy tắc ánh xạ kiểu dữ liệu sang Open MBean types để tăng khả năng tương tác.

## 10. Một export owner: tránh đăng ký MBean hai lần

Ngay cả khi metadata contract duy nhất, vẫn có thể bị lỗi nếu hai exporter cùng đăng ký.

Ví dụ kiến trúc cần tránh:

```text
Spring @ManagedResource scanning ------+
                                       |
Manual MBeanExporter ------------------+--> same ObjectName
                                       |
Manual server.registerMBean -----------+
```

Hai lời gọi register cùng ObjectName trong một MBeanServer không thể cùng thành công nếu name đã được chiếm. JMX có thể báo `InstanceAlreadyExistsException`, hoặc Spring có chính sách xử lý registration tùy cấu hình.

Đừng coi policy “ignoreExisting” (nếu có trong exporter) là giải pháp chuẩn thay cho việc xác định owner, vì lúc ấy metadata **thực sự được đăng ký** phụ thuộc thứ tự khởi tạo. Cách ổn định hơn:

- Ghi rõ component nào chịu trách nhiệm export mỗi ObjectName.
- Chỉ dùng một đường registration cho cùng MBean.
- Kiểm tra các auto-configuration hoặc annotation scanning có trùng với mapping thủ công không.
- Gắn unregister với lifecycle phù hợp.
- Nếu cần đổi implementation, cập nhật owner hiện tại thay vì thêm exporter thứ hai.

Tính duy nhất áp dụng trong **cùng MBeanServer**; nhiều JVM có thể có cùng ObjectName mà không xung đột.

## 11. Naming metadata: ObjectName cũng cần một chủ sở hữu

Một MBean có thể được đặt tên từ:

- `@ManagedResource(objectName="...")`.
- `MBeanExporter.setBeans` mapping.
- `ObjectNamingStrategy` hoặc factory tự xây dựng.
- `ObjectName` được truyền vào `MBeanServer.registerMBean`.
- Convention riêng của framework.

Không nên để nhiều nơi tự quyết định những tên khác nhau cho cùng một MBean.

Ví dụ:

```java
@ManagedResource(
    objectName = "com.example.shop.orders:type=Queue,name=outbox")
public class QueueManagement { /* ... */ }
```

nhưng mapping exporter lại dùng:

```text
com.example.shop.orders:type=OrderQueue,name=primary
```

Nếu cả hai được coi là naming contract, người vận hành không biết phải tìm cái nào. Tùy cơ chế export, một tên có thể được chọn hoặc một exporter khác có thể đăng ký thêm MBean.

**Chính sách đề xuất:** Chọn một trong hai:

1. **ObjectName ngay trên `@ManagedResource`:** thích hợp tên cố định và adapter chuyên dụng.
2. **ObjectName tại naming factory/export configuration:** thích hợp khi cần biến môi trường, tenant hoặc instance; tránh hardcode thông tin deployment trong class.

Không sử dụng cả hai như những yêu cầu ngang hàng. Nếu phải có metadata và mapping cùng lúc, hãy nêu rõ mapping nào là authoritative và viết kiểm thử xác nhận ObjectName đăng ký thật.

## 12. Metadata từ interface và annotation có thể khác nhau như thế nào?

Xét:

```java
public interface WorkerMonitorMBean {
    int getActiveThreads();
    void stop();
}
```

Implementation:

```java
@ManagedResource(
    objectName = "com.example.shop:type=WorkerMonitor,name=main")
public class WorkerMonitor implements WorkerMonitorMBean {

    @Override
    @ManagedAttribute(description = "Currently active threads")
    public int getActiveThreads() {
        return 4;
    }

    @Override
    public void stop() {
        // ...
    }

    @ManagedOperation(description = "Reset counters")
    public void resetCounters() {
        // ...
    }
}
```

Kết quả kỳ vọng khác nhau theo contract:

| Method | Standard MBean interface | Annotation-driven assembler |
|---|---|---|
| `getActiveThreads()` | Attribute `ActiveThreads` | Attribute nếu annotation được nhận diện |
| `stop()` | Operation `stop` | Không tự được annotate trong ví dụ |
| `resetCounters()` | Không thuộc interface | Operation nếu annotation được nhận diện |

Vì vậy một công cụ client có thể thấy `stop` nhưng không thấy `resetCounters`, hoặc ngược lại, tùy export path. Đây là minh họa về sự khác biệt contract; kết quả runtime cụ thể phải được xác nhận trên MBean đã đăng ký.

**Không xây bài kiểm thử bằng cách chỉ đếm annotation trong source** nếu hệ thống đã chọn interface làm contract. Và không dùng interface method list làm chuẩn nếu annotation assembler được chỉ định là nguồn metadata.

## 13. Proxy AOP làm nhiều nguồn metadata nguy hiểm hơn

Spring AOP có thể tạo JDK dynamic proxy hoặc class-based proxy. Một class `OrderMonitor` có annotation JMX nhưng bean runtime là proxy, có thể khiến:

- Annotation class-level được tìm trên target hoặc proxy tùy mechanism.
- Interface JDK proxy chỉ expose các method interface.
- Method annotated nhưng không nằm trong proxy interface không được gọi như kỳ vọng.
- CGLIB có ràng buộc với `final` class/method.
- Naming strategy nhìn vào runtime type khác với type được khai báo.

Khi vừa có interface `*MBean` vừa có annotation `@Managed...`, người điều tra còn phải xác định metadata discovery ưu tiên cái nào. Một contract duy nhất làm giảm đáng kể số giả thuyết cần kiểm tra.

Ví dụ kiểm tra proxy:

```java
import org.springframework.aop.support.AopUtils;

Object bean = applicationContext.getBean("orderManagement");

System.out.println(AopUtils.isAopProxy(bean));
System.out.println(AopUtils.isJdkDynamicProxy(bean));
System.out.println(AopUtils.getTargetClass(bean));
```

Đây là code debug minh họa trong context đã có `applicationContext`. Không nên tự unwrap target và export trực tiếp nếu điều đó bỏ qua security/transaction/caching advice.

## 14. Kiểm chứng nguồn chân lý bằng MBeanInfo

Dù chọn interface hay annotation, **MBeanServer là nguồn dữ liệu cuối cùng của JMX client**. Sau khi export, đọc metadata thật:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class MBeanContractInspection {
    public static void printContract() throws Exception {
        MBeanServer server =
                ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
                "com.example.shop.orders:type=OrderMonitor,name=main");

        if (!server.isRegistered(name)) {
            throw new IllegalStateException(
                    "Expected MBean is not registered");
        }

        MBeanInfo info = server.getMBeanInfo(name);

        System.out.println("MBean: " + name);
        System.out.println("Description: " + info.getDescription());

        for (MBeanAttributeInfo attribute : info.getAttributes()) {
            System.out.printf("ATTRIBUTE %s type=%s read=%s write=%s%n",
                    attribute.getName(),
                    attribute.getType(),
                    attribute.isReadable(),
                    attribute.isWritable());
        }

        for (MBeanOperationInfo operation : info.getOperations()) {
            System.out.printf("OPERATION %s%n",
                    operation.getName());
        }
    }
}
```

Đoạn code giả định MBean đã được export vào **platform MBeanServer**; nếu Spring cấu hình custom server phải dùng đúng instance.

Kiểm tra `MBeanInfo` giúp xác định:

- Attribute `PendingCount` có tồn tại và read-only như contract không.
- Operation nào thật sự công bố.
- Description/parameter metadata có được assembler tạo không.
- Có sự khác biệt giữa source code và client-visible contract hay không.

Để kiểm chứng ổn định giữa các lần build, có thể viết integration test kiểm tra tập attributes/operations cần có và tập operations không được công bố (đặc biệt method nhạy cảm).

## 15. Test hợp đồng JMX không dựa vào nội bộ implementation

Với một Standard MBean, test có thể:

1. Tạo `MBeanServer` riêng cho test bằng `MBeanServerFactory.createMBeanServer()`.
2. Register MBean với ObjectName test.
3. Đọc `MBeanInfo`.
4. So sánh danh sách attributes/operations với contract.
5. Unregister trong `finally`.

Ví dụ:

```java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.ObjectName;
import java.util.Arrays;
import java.util.Set;
import java.util.stream.Collectors;

public class ContractTestExample {
    public static void verify() throws Exception {
        MBeanServer server = MBeanServerFactory.createMBeanServer();
        ObjectName name = new ObjectName(
                "com.example.test:type=OrderMonitor");

        server.registerMBean(new OrderMonitor(), name);
        try {
            var info = server.getMBeanInfo(name);

            Set<String> attributes = Arrays.stream(info.getAttributes())
                    .map(x -> x.getName())
                    .collect(Collectors.toSet());

            Set<String> operations = Arrays.stream(info.getOperations())
                    .map(x -> x.getName())
                    .collect(Collectors.toSet());

            if (!attributes.contains("PendingCount")) {
                throw new AssertionError("Missing PendingCount");
            }
            if (!operations.contains("resetStatistics")) {
                throw new AssertionError("Missing resetStatistics");
            }
            if (operations.contains("importOrders")) {
                throw new AssertionError("Internal API leaked to JMX");
            }
        } finally {
            server.unregisterMBean(name);
        }
    }
}
```

Đây là ví dụ kiểu “assert bằng Java” để trình bày logic; trong dự án thực tế nên dùng JUnit/AssertJ hoặc framework test tương ứng. Không coi test JMX thuần này thay thế cho Spring integration test nếu contract thực sự được tạo bởi annotation assembler.

Với annotation-driven export, test nên khởi động Spring context có đúng exporter/assembler/beans, rồi đọc `MBeanInfo` từ MBeanServer mà exporter dùng.

## 16. Chọn phương án nào cho dự án?

| Tình huống | Nguồn metadata thường thích hợp | Lưu ý |
|---|---|---|
| Java không dùng Spring | Standard MBean interface | Dễ hiểu và ít dependency |
| Cần interoperable open types | MXBean interface | Xác thực mapping kiểu phức tạp |
| Spring app, muốn descriptions bằng annotation | Management adapter + `@Managed...` | Cấu hình exporter annotation-aware |
| Thư viện có Standard MBean sẵn | Giữ interface thư viện | Đừng bọc lại bằng nhiều annotation không cần thiết |
| Domain/ObjectName cần cấu hình deployment | Naming factory hoặc exporter mapping | Một owner đặt tên duy nhất |
| Bean nghiệp vụ có nhiều AOP advice | Adapter riêng công bố ít API quản trị | Không bỏ qua proxy của service |
| Cần metadata thay đổi runtime | DynamicMBean / ModelMBean | Kiểm soát metadata/invocation nhất quán |

Không có quy định rằng toàn hệ thống bắt buộc một style. **Granularity đúng là mỗi MBean/management contract**: chọn một kiểu chịu trách nhiệm chính, rồi giữ consistent trong module.

## 17. Quy trình migration khi đã có metadata hỗn hợp

Nếu code cũ có interface `*MBean`, annotations, exporter mappings và auto-configurations chồng nhau, hãy chuyển đổi có kiểm soát:

### Bước 1: Chụp trạng thái thực tế

Đọc ObjectName đã đăng ký và `MBeanInfo` từ môi trường chạy hiện tại. Ghi nhận consumers đang dùng attributes và operations nào. Không suy đoán từ source.

### Bước 2: Chọn contract mục tiêu

Quyết định Standard/MXBean interface hay annotations cho từng MBean. Xác định những operation nào được phép công bố và tên attribute chuẩn.

### Bước 3: Chọn registration owner và naming owner

Xác định một exporter hoặc đăng ký thủ công cho mỗi ObjectName. Lập danh sách cấu hình có thể export trùng.

### Bước 4: Chỉnh sửa code theo contract

Nếu chọn interface, bỏ annotations JMX chỉ làm nhiễu hoặc không còn được sử dụng. Nếu chọn annotation, gom chúng về management adapter; không dùng interface `*MBean` như API công khai thứ hai một cách mơ hồ.

### Bước 5: Kiểm tra qua integration test

Chạy ứng dụng có AOP như production; đọc `MBeanInfo` và xác thực các field quan trọng. Kiểm tra cả absence của operations nội bộ.

### Bước 6: Chuyển đổi dashboard/client

Nếu ObjectName hoặc attribute names đổi, cập nhật JMX exporters, dashboards, alert rules, JConsole scripts và tài liệu vận hành. Nếu cần duy trì backward compatibility, lập kế hoạch explicit, không dựa vào thứ tự registration tình cờ.

## 18. Dấu hiệu hệ thống có nhiều nguồn metadata cạnh tranh

Các triệu chứng đáng điều tra:

- Một service có cả `SomethingMBean`, `@ManagedResource`, `@ManagedOperation` và hai `MBeanExporter`.
- MBean xuất hiện hai lần dưới các ObjectName hơi khác nhau.
- Một environment hiển thị operation nhưng environment khác không, dù Java code giống nhau.
- Metadata description thay đổi sau khi thêm AOP annotation.
- JConsole chỉ thấy Standard MBean interface methods, không thấy annotated methods.
- Sau khi bật Spring Boot JMX hoặc Actuator integration, registration conflict xuất hiện.
- Có nhiều naming strategy khác nhau chạy cho cùng bean.
- Cấu hình exporter dùng policy xử lý existing MBeans để che conflict thay vì giải quyết owner.

Mỗi triệu chứng cần quan sát **trạng thái runtime và cấu hình export**. Không nên kết luận chỉ từ tên bean hoặc số annotation.

## 19. Những lỗi thường gặp

| Vấn đề | Nguyên nhân | Cách phòng ngừa |
|---|---|---|
| `InstanceAlreadyExistsException` | Hai registration cùng ObjectName | Một export owner/registration path |
| Thiếu `@ManagedOperation` trên JConsole | Exporter dùng interface contract thay vì annotations hoặc proxy không expose method | Kiểm tra MBeanInfo và đúng source |
| Operation nội bộ xuất hiện ngoài ý muốn | Export surface quá rộng | Contract tối thiểu, test absence |
| MBean có description không như mong đợi | Assembler lấy nguồn metadata khác | Một metadata source và test descriptions |
| ObjectName thay đổi giữa deployments | Naming strategy thiếu ổn định | Naming factory/contract rõ ràng |
| AOP proxy gây khác biệt | Metadata reader hoặc method exposure bị proxy ảnh hưởng | Adapter và integration test đúng proxy mode |
| “ignoreExisting” làm hành vi không đoán được | Cơ chế nào register trước quyết định metadata | Không dùng policy để che exporter trùng |
| Trộn MXBean và Standard MBean không chủ đích | Hai contract khác mapping kiểu và naming | Chọn một style theo yêu cầu interoperability |
| Refactor interface làm hỏng dashboard | Attributes/operations là public management contract | Version/migration và kiểm thử JMX |
| Annotation chỉ tồn tại ở class nhưng exporter chưa bật | Không có export path phù hợp | Kiểm tra context/assembler và MBeanServer |

## 20. Bài tập thực hành

### Bài tập 1 — Nhận diện hai nguồn contract

Cho:

```java
public interface CacheMonitorMBean {
    int getEntryCount();
}

@ManagedResource(objectName =
    "com.example.shop.catalog:type=CacheMonitor,name=main")
public class CacheMonitor implements CacheMonitorMBean {
    @ManagedAttribute
    public int getEntryCount() { return 10; }

    @ManagedOperation
    public void flush() { /* ... */ }
}
```

Hãy dự đoán metadata khi export theo Standard MBean convention và khi export qua annotation assembler, rồi dùng MBeanInfo để so sánh trong hai bài test riêng. Không đăng ký cả hai vào cùng ObjectName cùng lúc.

### Bài tập 2 — Chọn chủ sở hữu ObjectName

Một bean có `@ManagedResource(objectName="...name=old")` nhưng config cũng mapping nó sang `"...name=new"`. Hãy chọn một cơ chế là authoritative và sửa phần còn lại để không còn hai cách đặt tên cạnh tranh.

### Bài tập 3 — Kiểm tra sau refactor

Bạn đổi `QueueMonitorMBean.getPendingCount()` thành `getQueuedCount()`. Những client hoặc dashboard nào có thể bị ảnh hưởng? Hãy viết integration test bảo đảm tên attribute `PendingCount` còn tồn tại nếu vẫn cần backward compatibility.

### Bài tập 4 — Tách management adapter

Một service có cả `@Transactional`, `@Cacheable` và `@ManagedOperation`. Hãy tạo một `ServiceManagement` bean chuyên cho JMX, chỉ công bố `getHealthStatus()` và `resetMonitoringCounters()`, rồi gọi service qua dependency được Spring inject.

### Bài tập 5 — Kiểm thử absence của operation

Một class cài đặt có public method `deleteCustomerData()`. Hãy thiết kế một management contract không công bố method đó và kiểm tra `MBeanInfo.getOperations()` không có tên method nguy hiểm này. Không cần tạo logic xóa dữ liệu thật.

## 21. Câu hỏi tự kiểm tra

**1. Một class có cả interface `*MBean` và `@ManagedOperation` thì cả hai chắc chắn được gộp vào MBeanInfo không?**

Không. Kết quả phụ thuộc export path/assembler và khả năng method được expose.

**2. Vì sao một ObjectName nên có một registration owner?**

Để tránh trùng đăng ký và tình trạng metadata phụ thuộc thứ tự exporter khởi tạo.

**3. Nguồn chân lý cuối cùng đối với JMX client ở runtime là gì?**

MBean đã được đăng ký và `MBeanInfo` của nó; source code là contract mục tiêu, còn metadata runtime là điều client nhìn thấy.

**4. Chọn annotation-driven export có bắt buộc bỏ mọi Java interface nghiệp vụ không?**

Không. Interface nghiệp vụ vẫn hữu ích; chỉ cần tránh coi nó như một management contract thứ hai nếu không được thiết kế như vậy.

**5. Có thể dùng Standard MBean và MXBean trong cùng một ứng dụng không?**

Có. Quy tắc “một nguồn” áp dụng cho từng MBean; các MBean khác nhau có thể dùng cơ chế khác nhau.

**6. “ignoreExisting” có phải cách chuẩn để tránh conflict metadata không?**

Không nên coi đó là giải pháp kiến trúc. Nó có thể che việc đăng ký trùng và tạo hành vi phụ thuộc thứ tự.

**7. Vì sao cần test MBeanInfo sau khi bật AOP?**

Proxy có thể thay đổi runtime class và method exposure; metadata thực tế có thể khác dự đoán từ source.

## 22. Ghi nhớ

- Management metadata là **hợp đồng vận hành**: attributes, operations, descriptions, notifications và các thông tin liên quan.
- Một MBean nên có **một nguồn contract chính**: Standard MBean interface, MXBean interface, Spring annotations hoặc DynamicMBean metadata.
- Một MBean cũng cần **một export owner** và một naming policy để tránh registration conflict hoặc ObjectName khác nhau.
- Interface và annotation có thể cùng tồn tại trong source, nhưng không mặc định được hợp nhất; cơ chế export quyết định điều client nhìn thấy.
- AOP proxy làm việc suy đoán từ implementation khó hơn; dùng adapter và kiểm chứng metadata runtime.
- JMX client nhìn vào `MBeanInfo`, không nhìn vào source code. Test contract nên dựa trên metadata thực tế.
- Giữ management surface nhỏ, ổn định và có kiểm soát bảo mật; tránh công bố những operation nghiệp vụ nhạy cảm.
- Nếu thay đổi contract hoặc ObjectName, hãy xem đó là migration ảnh hưởng dashboard, exporter và công cụ vận hành.

## 23. Tài liệu tham khảo

- Java SE 21 — `MBeanInfo`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanInfo.html
- Java SE 21 — `MBeanServer`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
- Java SE 21 — `StandardMBean`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/StandardMBean.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework Reference — Controlling MBean Registration Behavior: https://docs.spring.io/spring-framework/reference/integration/jmx/exporting.html
- Spring Framework Reference — AOP Proxying: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
