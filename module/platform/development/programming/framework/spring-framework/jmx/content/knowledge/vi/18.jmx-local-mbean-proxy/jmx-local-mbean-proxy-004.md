# MBeanServerConnection local và lời gọi qua proxy trong Spring Framework JMX

## 1. Bài toán: cùng JVM vẫn cần một giao diện quản trị rõ ràng

Khi một đối tượng Java đã được đăng ký thành MBean trong JMX, bên gọi không bắt buộc phải giữ tham chiếu trực tiếp tới object gốc. Thay vào đó, nó có thể làm việc thông qua `MBeanServerConnection` và `ObjectName`. Điều này áp dụng cả khi caller và MBean **nằm trong cùng một JVM**.

Giả sử một Spring application có `QueueManager` đang xử lý hàng đợi. Một thành phần khác muốn đọc số tác vụ chờ hoặc yêu cầu tạm dừng consumer. Có ít nhất ba cách:

1. Inject `QueueManager` và gọi method Java trực tiếp.
2. Tìm MBean trong `MBeanServer` và dùng `getAttribute`/`setAttribute`/`invoke`.
3. Tạo **JMX proxy** triển khai management interface rồi gọi method Java trên proxy, để proxy chuyển lời gọi thành JMX operation/attribute access.

Cách thứ ba thường là trọng tâm của **proxy MBean local** trong Spring Framework. Nó giúp code phía caller có kiểu rõ ràng, giảm lặp các chuỗi tên attribute/operation, trong khi vẫn đi qua hợp đồng quản trị đã đăng ký.

```text
   Spring caller bean
         |
         | orderMonitor.getProcessedCount()
         v
   JMX management proxy
         |
         | getAttribute(ObjectName, "ProcessedCount")
         v
   MBeanServerConnection (local)
         |
         v
   MBeanServer
         |
         | định tuyến theo ObjectName
         v
   Registered MBean / ModelMBean
         |
         v
   Application object
```

**Điểm quan trọng:** “local” mô tả đường kết nối tới MBeanServer cùng JVM, không có nghĩa proxy gọi thẳng method của target. Bề mặt JMX, metadata, quy tắc kiểu và lỗi quản trị vẫn có ý nghĩa.

## 2. MBeanServerConnection là gì?

`javax.management.MBeanServerConnection` là giao diện truy cập quản trị cho một MBeanServer. Nó định nghĩa các thao tác phổ biến:

| Phương thức | Vai trò |
|---|---|
| `getAttribute(ObjectName, String)` | Đọc một attribute |
| `setAttribute(ObjectName, Attribute)` | Ghi một attribute |
| `getAttributes(...)` / `setAttributes(...)` | Đọc/ghi một tập attribute |
| `invoke(ObjectName, String, Object[], String[])` | Gọi operation |
| `getMBeanInfo(ObjectName)` | Đọc metadata thuộc tính, operation, notification |
| `queryNames(...)` | Tìm ObjectName đã đăng ký |
| `isRegistered(ObjectName)` | Kiểm tra MBean còn tồn tại |
| `addNotificationListener(...)` | Đăng ký nhận notification |
| `removeNotificationListener(...)` | Gỡ registration listener |

`javax.management.MBeanServer` **kế thừa `MBeanServerConnection`**, đồng thời có thêm những khả năng registry cục bộ như đăng ký MBean trực tiếp. Vì vậy có thể gán:

```java
MBeanServer server = ManagementFactory.getPlatformMBeanServer();
MBeanServerConnection connection = server;
```

Đây là một `MBeanServerConnection` local hoàn toàn hợp lệ. Không cần `JMXConnector`, host, port hay RMI nếu ứng dụng chỉ dùng cùng một `MBeanServer` trong JVM.

Với kết nối remote, `JMXConnector.getMBeanServerConnection()` trả một đối tượng cùng giao diện; các call lúc đó có thể phải qua network và có thêm vấn đề về serialization, authentication, latency, timeout.

Tư duy hữu ích là:

```text
MBeanServerConnection = hợp đồng client
MBeanServer           = server/registry trong JVM
JMXConnector          = cầu nối khi cần truy cập từ xa
ObjectName            = địa chỉ logic của MBean trong registry
```

## 3. ObjectName định danh MBean, không phải Java bean name

Mỗi MBean trong một `MBeanServer` được xác định bằng `javax.management.ObjectName`:

```text
demo.queue:type=QueueMonitor,name=orders
```

Trong đó:

- `demo.queue` là domain.
- `type=QueueMonitor` và `name=orders` là key properties.
- Toàn bộ ObjectName mới là định danh đầy đủ để client gọi `getAttribute` hoặc `invoke`.

ObjectName khác với tên Spring bean:

```text
Spring bean name : queueMonitor
JMX ObjectName   : demo.queue:type=QueueMonitor,name=orders
Java class       : com.example.QueueMonitor
```

Chúng có thể được liên hệ qua cấu hình exporter, nhưng **không tự đồng nhất**.

Khi target MBean chưa được đăng ký, proxy vẫn có thể được tạo trong một số cấu hình, nhưng lời gọi thực tế sẽ thất bại vì `ObjectName` không có trong registry. Ngược lại, một ObjectName hợp lệ không chứng minh management interface ở phía proxy khớp với metadata thật.

## 4. Ví dụ Java SE: Standard MBean trước khi dùng Spring

Ta bắt đầu với một Standard MBean đơn giản, không có Spring, để nhìn rõ quy trình.

### 4.1. Management interface

File `QueueMonitorMBean.java`:

```java
public interface QueueMonitorMBean {
    long getProcessedCount();
    int getWarningThreshold();
    void setWarningThreshold(int threshold);
    void resetStatistics();
}
```

Ý nghĩa:

- `ProcessedCount` là read-only attribute.
- `WarningThreshold` là read-write attribute.
- `resetStatistics()` là JMX operation.

### 4.2. Target implementation

File `QueueMonitor.java`:

```java
import java.util.concurrent.atomic.AtomicLong;

public class QueueMonitor implements QueueMonitorMBean {
    private final AtomicLong processedCount = new AtomicLong();
    private volatile int warningThreshold = 100;

    public void recordProcessed() {
        processedCount.incrementAndGet();
    }

    @Override
    public long getProcessedCount() {
        return processedCount.get();
    }

    @Override
    public int getWarningThreshold() {
        return warningThreshold;
    }

    @Override
    public void setWarningThreshold(int threshold) {
        if (threshold < 1 || threshold > 1000) {
            throw new IllegalArgumentException(
                "threshold must be between 1 and 1000"
            );
        }
        warningThreshold = threshold;
    }

    @Override
    public void resetStatistics() {
        processedCount.set(0L);
    }
}
```

Class triển khai interface đúng convention Standard MBean; `recordProcessed()` không nằm trong management interface nên không phải JMX operation của Standard MBean này.

### 4.3. Đăng ký vào platform MBeanServer

File `Main.java`:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;

public class Main {
    public static void main(String[] args) throws Exception {
        QueueMonitor monitor = new QueueMonitor();
        monitor.recordProcessed();
        monitor.recordProcessed();

        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();
        ObjectName name = new ObjectName(
            "demo.queue:type=QueueMonitor,name=orders"
        );
        server.registerMBean(monitor, name);

        MBeanServerConnection connection = server;

        System.out.println(
            "Raw count = " +
            connection.getAttribute(name, "ProcessedCount")
        );

        // Các phần tiếp theo có thể đặt tại đây.
    }
}
```

Dù target và caller trong cùng method `main`, lệnh `connection.getAttribute` vẫn đi qua JMX API, ObjectName và metadata MBean. Nó không phải `monitor.getProcessedCount()` thông thường.

## 5. Đường gọi thủ công: getAttribute, setAttribute và invoke

Khi sử dụng `MBeanServerConnection` trực tiếp, client phải biết tên attribute/operation và chữ ký tham số.

```java
long count = (Long) connection.getAttribute(
    name, "ProcessedCount"
);

connection.setAttribute(
    name,
    new javax.management.Attribute(
        "WarningThreshold",
        150
    )
);

Object current = connection.getAttribute(
    name, "WarningThreshold"
);

connection.invoke(
    name,
    "resetStatistics",
    new Object[0],
    new String[0]
);
```

Với operation có tham số, `invoke` cần hai mảng song song:

```java
connection.invoke(
    name,
    "setProcessingMode",
    new Object[]{"PAUSED"},
    new String[]{String.class.getName()}
);
```

Ví dụ `setProcessingMode` chỉ mang tính minh họa: nó phải được export như operation tương ứng thì lệnh mới chạy. Với setter của attribute, thường dùng `setAttribute`, không gọi `invoke("setWarningThreshold", ...)` rồi mặc định chúng tương đương về contract.

**Nhược điểm của cách thủ công:** client chứa các chuỗi như `"ProcessedCount"` và `"WarningThreshold"`, phải cast return type, tự cung cấp signature và tự chuyển đổi dữ liệu khi cần.

Những nhược điểm này là động cơ quan trọng để sử dụng proxy.

## 6. Java JMX proxy: typed API phía client

JDK cung cấp:

```java
javax.management.JMX.newMBeanProxy(
    connection,
    name,
    QueueMonitorMBean.class
);
```

Ví dụ đầy đủ:

```java
QueueMonitorMBean proxy =
    javax.management.JMX.newMBeanProxy(
        connection,
        name,
        QueueMonitorMBean.class
    );

long count = proxy.getProcessedCount();
proxy.setWarningThreshold(180);
int threshold = proxy.getWarningThreshold();
proxy.resetStatistics();
```

Code caller trông giống lời gọi Java bình thường, nhưng đối tượng `proxy` là đại diện cho MBean. Các call trên được dịch ra JMX attribute access và operation invocation.

So sánh:

```text
Raw API:
  connection.getAttribute(name, "ProcessedCount")

Typed proxy:
  proxy.getProcessedCount()
```

**Proxy không phải target object.** Một thay đổi thực hiện qua proxy ảnh hưởng target MBean trong MBeanServer; caller không nhất thiết có tham chiếu trực tiếp tới implementation.

### 6.1. Standard MBean proxy và MXBean proxy

JDK phân biệt proxy dành cho Standard MBean và MXBean:

```java
QueueMonitorMBean standard =
    JMX.newMBeanProxy(connection, name, QueueMonitorMBean.class);
```

Với MXBean:

```java
MemoryMXBean memory =
    JMX.newMXBeanProxy(
        connection,
        new ObjectName("java.lang:type=Memory"),
        MemoryMXBean.class
    );
```

Các import tương ứng gồm `javax.management.JMX` và `java.lang.management.MemoryMXBean`. MXBean có cơ chế ánh xạ giữa kiểu Java của interface và OpenData; không nên dùng `newMBeanProxy` thay cho `newMXBeanProxy` rồi kỳ vọng các DTO custom được chuyển đổi theo cùng quy tắc.

## 7. Spring JMX proxy: MBeanProxyFactoryBean

Spring Framework cung cấp `org.springframework.jmx.access.MBeanProxyFactoryBean`, một `FactoryBean` có thể tạo proxy đến MBean được nhận diện bởi ObjectName và management interface.

Ví dụ:

```java
import javax.management.MBeanServer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.access.MBeanProxyFactoryBean;

@Configuration
public class ProxyConfiguration {

    @Bean
    public MBeanProxyFactoryBean queueMonitorProxy(
            MBeanServer mbeanServer) {

        MBeanProxyFactoryBean factory =
            new MBeanProxyFactoryBean();

        factory.setServer(mbeanServer);
        factory.setObjectName(
            "demo.queue:type=QueueMonitor,name=orders"
        );
        factory.setProxyInterface(QueueMonitorMBean.class);

        return factory;
    }
}
```

Một bean phụ thuộc có thể inject interface:

```java
import org.springframework.stereotype.Service;

@Service
public class QueueDashboard {
    private final QueueMonitorMBean monitor;

    public QueueDashboard(QueueMonitorMBean monitor) {
        this.monitor = monitor;
    }

    public String summary() {
        return "Processed=" + monitor.getProcessedCount()
            + ", threshold=" + monitor.getWarningThreshold();
    }
}
```

Với cấu hình proxy factory phù hợp, Spring cung cấp một đối tượng triển khai `QueueMonitorMBean` để inject vào dashboard; cuộc gọi đến nó đi qua JMX.

**Lưu ý về wiring:** nếu trong context cũng có target `QueueMonitor` implement `QueueMonitorMBean`, injection chỉ bằng type có thể mơ hồ. Sử dụng `@Qualifier` hoặc tên bean riêng để chọn proxy thay vì target.

### 7.1. MBeanProxyFactoryBean không phải MBeanExporter

Hai thành phần giải quyết hai phía ngược nhau:

| Thành phần | Trách nhiệm | Luồng |
|---|---|---|
| `MBeanExporter` | Đăng ký Spring bean thành MBean | Spring bean → JMX registry |
| `MBeanProxyFactoryBean` | Tạo client proxy cho MBean đã đăng ký | Spring caller → JMX registry |
| `MBeanServer` | Chứa các registration | Registry/server |
| `MBeanServerConnection` | Hợp đồng thao tác JMX | Client API |

Tạo proxy không tự đăng ký target. Ngược lại, export MBean không tự tạo một client proxy có thể inject vào mọi bean.

Trong nhiều ứng dụng Spring, hai thành phần có thể cùng xuất hiện, nhưng cần quản lý thời điểm tạo bean và ObjectName để tránh proxy gọi trước khi target được đăng ký.

## 8. MBeanClientInterceptor: cơ chế phía sau proxy

Spring có `MBeanClientInterceptor` trong package `org.springframework.jmx.access`. Nó chuyển lời gọi trên proxy thành những thao tác với JMX MBeanServerConnection.

Bạn thường không cần tự gọi interceptor. `MBeanProxyFactoryBean` cung cấp lớp FactoryBean thuận tiện để tạo proxy có management interface. Nhưng hiểu interceptor giúp giải thích những hành vi như:

- Lời gọi getter được chuyển thành `getAttribute`.
- Lời gọi setter được chuyển thành `setAttribute`.
- Method quản trị còn lại được xử lý như operation.
- Có các exception liên quan MBeanServer, ObjectName hoặc metadata trong quá trình gọi.
- Nếu cần kết nối remote, interceptor/proxy cần cấu hình connector thích hợp.

Một proxy JMX là **adapter của hợp đồng quản trị**, không phải bean AOP đại diện đầy đủ cho tất cả method implementation.

### 8.1. Kiểu proxy cần phù hợp

Management interface chỉ nên chứa các phương thức JMX được công bố:

```java
public interface QueueManagement {
    long getProcessedCount();
    void resetStatistics();
}
```

Nếu target MBean thực tế không có operation `resetStatistics`, proxy interface vẫn có thể biên dịch nhưng lời gọi sẽ thất bại khi JMX xử lý. Do đó phải giữ interface phía client đồng bộ với `MBeanInfo` của target.

Khi server đang dùng Standard MBean theo interface khác hoặc Spring ModelMBean do assembler tạo, cần bảo đảm tên attribute và operation khớp. Một interface có cùng tên phương thức không bảo đảm tất cả kiểu tham số, return type hoặc semantics tương thích.

## 9. Local proxy khác gọi trực tiếp object như thế nào?

Giả sử Spring đã tạo một target `QueueMonitor` và đăng ký nó thành MBean.

### Direct Java call

```java
QueueMonitor monitor = context.getBean(QueueMonitor.class);
long count = monitor.getProcessedCount();
```

- Caller cần tham chiếu tới target bean.
- Phương thức được gọi theo ngữ nghĩa Java thông thường, có thể qua Spring proxy/AOP nếu bean đã được bọc.
- Không cần ObjectName hoặc MBeanServer.
- Hợp đồng có thể gồm method implementation không xuất JMX.
- Lỗi và kiểu dữ liệu tuân theo call Java trực tiếp.

### Local JMX call

```java
MBeanServerConnection connection = server;
long count = (Long) connection.getAttribute(
    objectName, "ProcessedCount"
);
```

- Caller cần ObjectName và MBeanServerConnection.
- JMX thực thi quy tắc access attribute/operation.
- Chỉ phần interface được export mới truy cập được qua JMX.
- Có thể gặp exception của JMX.
- Dễ thay caller bằng một JMX client khác mà giữ nguyên hợp đồng JMX.

### Local JMX proxy call

```java
QueueMonitorMBean proxy =
    JMX.newMBeanProxy(
        connection,
        objectName,
        QueueMonitorMBean.class
    );
long count = proxy.getProcessedCount();
```

- Caller có API Java kiểu mạnh.
- Bên dưới vẫn dựa vào JMX.
- Không phải target object, dù hai bên cùng JVM.
- Các ràng buộc metadata, signature và lifecycle của MBean vẫn có hiệu lực.

**Kết luận:** local JMX proxy không được tạo chủ yếu để “gọi method Java nhanh hơn”; nó được dùng khi muốn caller làm việc thông qua **hợp đồng quản trị JMX** và tránh phụ thuộc trực tiếp vào implementation.

## 10. Chi phí và đặc tính runtime của local JMX

Vì cùng JVM, local MBeanServerConnection tránh chi phí network connector. Nhưng call vẫn có thể cần:

- Tra ObjectName trong registry.
- Kiểm tra attribute/operation theo metadata.
- Chuyển đổi kiểu và xử lý reflection hoặc ModelMBean.
- Áp dụng logic của MBean implementation.
- Phân phối exception theo hợp đồng JMX.

Không nên coi local proxy là một cách thay thế tối ưu cho các lời gọi nghiệp vụ tần suất rất cao. Nếu xử lý mỗi event cần gọi `incrementCounter()`, thường nên gọi service trực tiếp rồi export số đếm qua JMX cho giám sát, thay vì mỗi event đi qua JMX proxy.

Dùng JMX local hợp lý khi:

- Có một management API ổn định và muốn reuse giữa local/remote clients.
- Module quan sát không cần phụ thuộc vào target implementation.
- Cần test/chẩn đoán đúng bề mặt JMX thực sự.
- Muốn sử dụng ObjectName để định vị một component quản trị theo convention.

Dùng dependency injection trực tiếp hợp lý khi:

- Caller là thành phần nghiệp vụ cốt lõi cần hiệu năng và type safety đầy đủ.
- Target đã có một service interface Java thông thường.
- Không cần semantics JMX hoặc khả năng quan sát bởi client quản trị.

## 11. Thứ tự khởi tạo: proxy có thể đến trước MBean

Một tình huống thường gặp:

```text
Spring context refresh
   |
   +--> tạo MBeanProxyFactoryBean
   |
   +--> tạo MBeanExporter
   |
   +--> đăng ký MBean target
   |
   +--> caller gọi method trên proxy
```

Nếu proxy được sử dụng **trước khi target MBean xuất hiện**, lời gọi có thể gặp `InstanceNotFoundException` hoặc lỗi Spring JMX access tương ứng. Tùy cấu hình, bước khởi tạo proxy cũng có thể kiểm tra kết nối hoặc metadata của MBean trước lời gọi đầu tiên.

Một số cách tổ chức:

1. Tạo target và đăng ký MBean trước khi bắt đầu gọi qua proxy.
2. Dùng dependency/lifecycle rõ ràng khi hai bean nằm cùng Spring context.
3. Nếu target là module khác, đưa trạng thái sẵn sàng vào thiết kế; không gọi operation ngay trong constructor của caller.
4. Đọc `isRegistered(ObjectName)` khi cần chẩn đoán, nhưng đừng xem đây là bảo đảm rằng MBean sẽ còn tồn tại đến lúc gọi.
5. Xử lý lỗi runtime vì target có thể bị unregister hoặc thay thế sau khi proxy đã tạo.

Cần phân biệt **lúc proxy tồn tại** với **lúc target có thể xử lý lời gọi**. Một proxy không tự giữ MBean sống mãi.

## 12. getMBeanInfo giúp phát hiện hợp đồng thật

Trước khi tạo hoặc sử dụng proxy, có thể đọc metadata:

```java
MBeanInfo info = connection.getMBeanInfo(objectName);

for (MBeanAttributeInfo attribute : info.getAttributes()) {
    System.out.printf(
        "%s: type=%s, read=%s, write=%s%n",
        attribute.getName(),
        attribute.getType(),
        attribute.isReadable(),
        attribute.isWritable()
    );
}

for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.println(
        "operation=" + operation.getName()
    );
}
```

Cần import các type từ `javax.management`. Metadata cho biết:

- `ProcessedCount` có thực sự được export không.
- `WarningThreshold` có writable không.
- `resetStatistics` có phải operation và chữ ký của nó là gì.
- Target hiện tại đang dùng một interface/assembler khác với interface proxy dự kiến không.

**Proxy không thể tạo thêm khả năng cho target.** Nếu operation không nằm trong `MBeanInfo`, gọi một method cùng tên trên interface proxy không làm nó xuất hiện.

## 13. Notification qua MBeanServerConnection

Ngoài attribute và operation, JMX còn hỗ trợ notification. Với client local:

```java
NotificationListener listener = (notification, handback) -> {
    System.out.println(
        "type=" + notification.getType()
        + ", handback=" + handback
    );
};

connection.addNotificationListener(
    objectName,
    listener,
    null,
    "local-observer"
);
```

Đoạn code chỉ hợp lệ khi target MBean có khả năng phát notification. `null` filter nghĩa là không lọc loại notification theo registration này; `"local-observer"` là handback do caller chọn.

Gỡ registration:

```java
connection.removeNotificationListener(
    objectName,
    listener
);
```

Nếu ứng dụng cần nhiều registration cho cùng listener, có thể dùng overload nhận listener/filter/handback để gỡ chính xác. Không để listener local sống lâu hơn lifecycle của component sở hữu nó.

Spring MBean proxy dành cho method quản trị không tự biến notification thành callback Java của một interface nghiệp vụ; muốn nhận notification, phải đăng ký listener qua JMX API hoặc cơ chế hỗ trợ của Spring.

## 14. Exception trên proxy: không giống mọi lời gọi Java bình thường

Khi gọi trực tiếp:

```java
target.setWarningThreshold(-1);
```

implementation có thể ném `IllegalArgumentException`. Khi gọi qua JMX:

```java
proxy.setWarningThreshold(-1);
```

exception có thể đi qua JMX reflection/ModelMBean và lớp proxy, nên caller có thể quan sát exception đã được bọc hoặc dịch thành exception truy cập JMX. Không nên viết code phụ thuộc vào việc loại exception luôn giống hệt direct call.

Các trường hợp thường gặp:

| Nguyên nhân | Biểu hiện |
|---|---|
| ObjectName không tồn tại | `InstanceNotFoundException` hoặc exception proxy liên quan |
| Attribute không có/không đọc được | `AttributeNotFoundException` hoặc exception proxy tương ứng |
| Value không hợp lệ | Exception validation của target được JMX/Spring chuyển tiếp hoặc bọc |
| Method không export | Lỗi invoke/metadata |
| MBean bị thay hoặc unregister | Lời gọi trước thành công, lời gọi sau thất bại |
| Remote connector đứt | Lỗi kết nối/IO ngoài các lỗi MBean thông thường |

Không dùng proxy để che mọi lỗi thành “MBean unavailable”. Client cần phân biệt cấu hình sai, dữ liệu đầu vào sai, trạng thái đang STOPPING và kết nối bị lỗi.

## 15. Spring local proxy với FactoryBean: wiring minh họa

Một cấu hình tập trung có thể tạo target, exporter và proxy trong cùng context:

```java
import java.lang.management.ManagementFactory;
import java.util.Map;
import javax.management.MBeanServer;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.access.MBeanProxyFactoryBean;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class CompleteJmxConfiguration {

    @Bean
    public MBeanServer mBeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public QueueMonitor queueMonitorTarget() {
        return new QueueMonitor();
    }

    @Bean
    public MBeanExporter queueExporter(
            MBeanServer mBeanServer,
            QueueMonitor queueMonitorTarget) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(mBeanServer);
        exporter.setBeans(Map.of(
            "demo.queue:type=QueueMonitor,name=orders",
            queueMonitorTarget
        ));
        return exporter;
    }

    @Bean
    public MBeanProxyFactoryBean queueMonitorJmxProxy(
            MBeanServer mBeanServer) {
        MBeanProxyFactoryBean factory =
            new MBeanProxyFactoryBean();
        factory.setServer(mBeanServer);
        factory.setObjectName(
            "demo.queue:type=QueueMonitor,name=orders"
        );
        factory.setProxyInterface(QueueMonitorMBean.class);
        return factory;
    }
}
```

Một consumer có thể inject proxy bằng qualifier:

```java
@Service
public class MonitoringClient {
    private final QueueMonitorMBean proxy;

    public MonitoringClient(
            @Qualifier("queueMonitorJmxProxy")
            QueueMonitorMBean proxy) {
        this.proxy = proxy;
    }

    public long processed() {
        return proxy.getProcessedCount();
    }
}
```

Vì target cũng implements `QueueMonitorMBean`, qualifier tránh nhầm injection. Trong dự án thật, hãy chọn lifecycle rõ ràng để exporter đăng ký target trước khi client cần gọi; ví dụ test bằng cách tạo context rồi gọi proxy **sau khi context refresh xong** và đọc `MBeanInfo` trước.

Không cấu hình nhiều exporter cùng đăng ký một ObjectName nếu không có chủ đích. Các bean trong `@Configuration` mẫu là một cách tổ chức lab; ứng dụng lớn có thể dùng auto-exporter, `@ManagedResource` và naming strategy khác.

## 16. MBeanServerFactoryBean và lựa chọn server local

Spring cung cấp `MBeanServerFactoryBean` để tìm hoặc tạo `MBeanServer` theo cấu hình. Với local proxy, điều tối quan trọng là **exporter và proxy phải trỏ tới cùng một server**.

```text
Exporter -> Server A -> MBean "demo:type=Queue"
Proxy    -> Server B -> không tìm thấy "demo:type=Queue"
```

Dù Server A và B cùng ở một JVM, chúng là registry khác nhau. Một ObjectName được đăng ký vào A không tự xuất hiện ở B. Đây là nguyên nhân phổ biến khi proxy báo MBean không tồn tại trong khi log cho thấy exporter đã đăng ký thành công.

Với Spring/JVM platform monitoring, thường thuận tiện chọn `ManagementFactory.getPlatformMBeanServer()` làm server chung. Nhưng trong test hoặc ứng dụng cần cô lập MBean, có thể dùng server riêng. Hãy chọn nhất quán và xác nhận instance thật, không chỉ xác nhận cùng kiểu `MBeanServer`.

## 17. Kiểu dữ liệu: Standard MBean và MXBean

Với Standard MBean, các method trên proxy thường dùng cùng management interface với target. Nếu interface chứa DTO tùy biến, local proxy có thể làm việc khi hai bên có type tương thích và JMX xử lý phù hợp; nhưng khi chuyển sang remote, class availability và serialization có thể trở thành vấn đề.

MXBean chủ động ánh xạ các kiểu Java phù hợp sang Open Types. Ví dụ một MXBean trả một DTO composite có thể xuất `CompositeData` qua raw API, còn typed MXBean proxy ánh xạ về kiểu Java nếu mapping chiều ngược hợp lệ.

So sánh:

```java
// MXBean raw API có thể trả CompositeData:
Object raw = connection.getAttribute(name, "Status");

// Typed MXBean proxy:
StatusMXBean p = JMX.newMXBeanProxy(
    connection,
    name,
    StatusMXBean.class
);
StatusDto value = p.getStatus();
```

`StatusMXBean` và `StatusDto` ở đây là tên minh họa; cần định nghĩa interface và DTO có quy tắc MXBean mapping phù hợp khi chạy. Không lấy `CompositeData` rồi ép trực tiếp sang `StatusDto`.

Khi dùng Spring `MBeanProxyFactoryBean` với MXBean, cần xem khả năng MXBean mode và quy tắc type mapping của phiên bản Spring đang dùng. Nếu cần proxy chuẩn MXBean, `JMX.newMXBeanProxy` của JDK là một lựa chọn trực tiếp và rõ nghĩa.

## 18. Bảo mật: local không có nghĩa là không cần kiểm soát

Cùng JVM làm việc qua JMX thường không cần remote network transport, nhưng vẫn có những điểm cần lưu ý:

- MBean interface có thể chứa method có tác dụng phụ như `resetCounters()`, `clearCache()`, `pauseConsumer()`.
- Một component nội bộ có tham chiếu MBeanServer có thể gọi các operation JMX theo khả năng môi trường cho phép.
- Nếu cùng MBeanServer sau này được mở remote, bề mặt quản trị cũng có thể được client từ xa nhìn thấy.
- Getter được export có thể làm lộ cấu hình, credential hoặc dữ liệu người dùng.
- Proxy local không tự thêm authentication/authorization cho từng method.
- Lỗi hoặc độ trễ của getter vẫn có thể ảnh hưởng thread gọi.

Vì vậy quản trị MBean như API có đặc quyền: giới hạn số method công bố, validation giá trị, kiểm soát quyền truy cập, log audit operation quan trọng và bảo vệ kết nối remote khi có.

Không dùng JMX proxy làm đường tắt để bỏ qua security boundary của API nghiệp vụ. Nếu một operation thay đổi dữ liệu quan trọng, security policy phải được áp dụng ở các lớp thích hợp chứ không chỉ dựa vào việc caller “nằm cùng JVM”.

## 19. Khi nào không nên dùng proxy?

Proxy JMX tạo thêm một tầng trừu tượng, không phải luôn là lựa chọn tốt.

**Không nên dùng chỉ để gọi logic nội bộ liên tục.** Ví dụ một worker gọi `recordProcessed()` hàng nghìn lần/giây thông qua MBean proxy, thay vì gọi service Java trực tiếp, có thể tăng overhead mà không tạo giá trị quản trị.

**Không nên dùng để thay thế messaging giữa service.** JMX được thiết kế cho management/monitoring, không phải bus sự kiện nghiệp vụ bền vững.

**Không nên dùng để che lifecycle phức tạp.** Proxy không làm target tự xuất hiện, không tự khởi động database và không bảo đảm target READY.

**Không nên dùng khi type contract không ổn định.** Nếu MBeanInfo thường xuyên thay đổi trong lúc triển khai, client proxy có thể thất bại khi gọi; cần versioning/naming strategy và đồng bộ hợp đồng.

Dùng proxy khi có một management interface nhỏ, ổn định và muốn code client làm việc theo hợp đồng đó thay vì phụ thuộc implementation class.

## 20. Thực hành kiểm tra proxy local

### Bài 1 — Raw API và typed proxy

Đăng ký `QueueMonitor` vào platform MBeanServer. Đọc `ProcessedCount` bằng `getAttribute` và bằng `JMX.newMBeanProxy`. So sánh hai giá trị. Sau đó gọi `resetStatistics()` qua proxy rồi đọc lại raw attribute.

### Bài 2 — Thay đổi threshold

Gọi `setWarningThreshold(200)` qua proxy và đọc lại `WarningThreshold` bằng `getAttribute`. Sau đó thử giá trị không hợp lệ và quan sát exception.

### Bài 3 — Sai ObjectName

Tạo proxy với `ObjectName` chưa có MBean, gọi getter và ghi nhận lỗi. Sau đó đăng ký đúng MBean rồi thử lại. Mục tiêu là phân biệt tạo proxy với target registration.

### Bài 4 — Hai MBeanServer local

Tạo MBeanServer A và B riêng trong JVM test. Đăng ký MBean vào A nhưng tạo proxy trỏ B. Giải thích vì sao call thất bại dù hai server cùng local. Sau đó trỏ proxy về A.

### Bài 5 — Spring wiring

Tạo `MBeanExporter` và `MBeanProxyFactoryBean` trong Spring context. Inject proxy vào bean `MonitoringClient` và gọi getter sau khi context refresh xong. Dùng qualifier để phân biệt proxy và target.

### Bài 6 — Cập nhật interface

Thêm một operation mới vào management interface ở phía caller nhưng chưa cập nhật MBean target. Xem MBeanInfo và thử gọi. Giải thích vì sao việc proxy có method ở compile time không tạo khả năng ở runtime.

### Bài 7 — Notification

Tạo một MBean có `NotificationBroadcasterSupport`, đăng ký listener qua `MBeanServerConnection`, phát notification và gỡ listener. So sánh subscription notification với các lời gọi method trên proxy.

## 21. Câu hỏi tự kiểm tra

1. `MBeanServer` và `MBeanServerConnection` khác nhau như thế nào?
2. Vì sao có thể dùng `MBeanServer` làm `MBeanServerConnection` local?
3. `ObjectName` có vai trò gì đối với proxy?
4. `JMX.newMBeanProxy` làm gì, và nó có tự đăng ký MBean không?
5. Khác biệt giữa direct Java call và local JMX proxy call là gì?
6. `MBeanProxyFactoryBean` và `MBeanExporter` giải quyết hai hướng nào?
7. Vì sao injection theo interface có thể mơ hồ khi target và proxy cùng implement interface?
8. Điều gì xảy ra nếu exporter và proxy dùng hai MBeanServer local khác nhau?
9. Vì sao proxy có thể gọi getter thất bại dù đối tượng proxy đã được tạo?
10. Khi nào nên dùng `JMX.newMXBeanProxy` thay vì `newMBeanProxy`?

## 22. Ghi nhớ cốt lõi

**`MBeanServerConnection` là giao diện JMX của client; một `MBeanServer` cùng JVM có thể được sử dụng trực tiếp như connection local.** Raw API dùng `getAttribute`, `setAttribute`, `invoke` và `ObjectName`; typed proxy giúp caller gọi method trên một management interface trong khi lời gọi vẫn đi qua JMX.

Trong Spring, `MBeanExporter` đưa bean vào MBeanServer, còn `MBeanProxyFactoryBean` tạo proxy để gọi MBean đã được đăng ký. Hãy giữ exporter và proxy trỏ cùng registry, đồng bộ management interface với MBeanInfo, bảo đảm lifecycle hợp lý và chỉ dùng JMX proxy cho mục đích quản trị/quan sát tương xứng.
