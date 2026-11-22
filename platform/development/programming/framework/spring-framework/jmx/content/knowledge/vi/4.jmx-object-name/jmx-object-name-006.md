# Định danh ổn định qua các lần khởi động trong JMX ObjectName

## Mục tiêu

Sau bài học, bạn có thể thiết kế `ObjectName` ổn định cho một tài nguyên được quản lý qua nhiều lần khởi động JVM; phân biệt danh tính logic với trạng thái của một phiên chạy; tránh dùng giá trị ngẫu nhiên, địa chỉ bộ nhớ và thứ tự khởi tạo trong tên MBean; đồng thời áp dụng quy ước đặt tên thống nhất khi xuất MBean bằng Spring Framework.

## 1. ObjectName là danh tính của MBean

Trong JMX, mỗi MBean được đăng ký trong một `MBeanServer` bằng một `javax.management.ObjectName`. Tên có cấu trúc:

```text
domain:key1=value1,key2=value2,...
```

Ví dụ:

```text
com.example.orders:type=Queue,name=PaymentQueue
com.example.orders:type=ConnectionPool,name=Primary
com.example.orders:type=Worker,group=Billing,name=Retry
```

Một `ObjectName` có hai phần: **domain** và tập các **key property**. Domain giúp phân vùng namespace; các key property xác định loại và danh tính cụ thể của MBean.

```java
import javax.management.ObjectName;

ObjectName name = new ObjectName(
    "com.example.orders:type=Queue,name=PaymentQueue"
);
System.out.println(name.getDomain());
System.out.println(name.getKeyProperty("type"));
System.out.println(name.getKeyProperty("name"));
System.out.println(name.getCanonicalName());
```

Một `ObjectName` phân biệt MBean **trong phạm vi của một MBeanServer**. Hai JVM có thể đăng ký cùng một chuỗi `ObjectName` độc lập. Khi truy cập từ xa, danh tính đầy đủ thường phải bao gồm cả endpoint/instance kết nối và tên JMX bên trong.

## 2. “Ổn định qua các lần khởi động” nghĩa là gì?

Giả sử ứng dụng vận hành một queue có danh tính logic `PaymentQueue`. JVM khởi động lần đầu lúc 09:00, sau đó được restart lúc 10:00. Nếu queue vẫn là cùng một tài nguyên quản trị, client nên tìm thấy:

```text
com.example.orders:type=Queue,name=PaymentQueue
```

ở cả hai phiên chạy.

**Ổn định** nghĩa là quy tắc tạo tên dựa trên các thuộc tính logic có chủ ý, tồn tại độc lập với vòng đời một đối tượng Java:

- Tên dịch vụ hoặc miền quản trị cố định.
- Loại tài nguyên: `Cache`, `Queue`, `ConnectionPool`, `Scheduler`.
- Tên logic của tài nguyên từ cấu hình được quản lý.
- Định danh tenant hoặc phân vùng bền vững khi đó thực sự là một phần hợp đồng.

Tên không cần trùng với một object Java sống xuyên restart: instance cũ đã kết thúc, instance mới được tạo lại. Điều cần giữ ổn định là **đường dẫn để hệ thống quản trị nhận diện cùng một vai trò/tài nguyên**.

Ví dụ không ổn định:

```text
com.example.orders:type=Queue,id=6d77b62c-5e...
com.example.orders:type=Queue,createdAt=20261111T090000
com.example.orders:type=Queue,identityHash=18273645
com.example.orders:type=Queue,thread=worker-17
```

UUID sinh mới, timestamp khởi động, `System.identityHashCode`, tên thread, PID, port ngẫu nhiên, thứ tự đăng ký hoặc index collection đều dễ đổi sau restart. Client phải liên tục khám phá lại tên, dashboard mất chuỗi lịch sử hoặc alert không còn tìm đúng đối tượng.

## 3. Danh tính logic và dữ liệu phiên chạy phải tách riêng

Một MBean có nhiều dữ liệu biến đổi theo thời gian, nhưng các biến đổi này **không nhất thiết thuộc ObjectName**.

| Thuộc tính | Có nên nằm trong ObjectName? | Ví dụ |
| --- | --- | --- |
| Loại tài nguyên | Có | `type=Queue` |
| Tên queue cấu hình ổn định | Có | `name=PaymentQueue` |
| Tên cụm/tenant ổn định khi cần phân biệt | Tùy yêu cầu | `tenant=Retail` |
| Thời điểm khởi động JVM | Thường không | Attribute `StartTimeMillis` |
| PID hiện tại | Thường không | Attribute `ProcessId` |
| Số request đang xử lý | Không | Attribute `ActiveRequests` |
| Trạng thái `RUNNING/STOPPED` | Không | Attribute `State` |
| ID phiên chạy UUID mới mỗi restart | Không | Attribute `RunId` |

Ví dụ:

```java
public interface QueueMonitorMBean {
    String getState();
    int getPendingCount();
    long getStartTimeMillis();
    String getRunId();
}
```

`ObjectName` vẫn là `com.example.orders:type=Queue,name=PaymentQueue`, còn các thuộc tính `RunId` và `StartTimeMillis` giúp người vận hành biết đây là phiên chạy mới.

Nếu công cụ cần phát hiện restart, hãy xem `RunId` hoặc `StartTimeMillis`, uptime, JMX connection lifecycle hay metric reset. Việc giữ `ObjectName` giống nhau **không** có nghĩa các counter hoặc notification sequence sẽ liên tục xuyên restart.

## 4. Tạo ObjectName bằng giá trị cấu hình ổn định

Một quy tắc tốt là gom logic tạo tên tại một nơi và truyền các thành phần danh tính từ cấu hình hoặc metadata nghiệp vụ đáng tin cậy.

```java
import javax.management.MalformedObjectNameException;
import javax.management.ObjectName;

public final class JmxNames {
    private JmxNames() {}

    public static ObjectName queue(String logicalName)
            throws MalformedObjectNameException {
        return new ObjectName(
            "com.example.orders",
            java.util.Hashtable.of() // chỉ là ký hiệu minh họa, xem triển khai dưới
        );
    }
}
```

Trong Java thực tế, `Hashtable` không có factory `of()`; nên triển khai rõ ràng như sau:

```java
import java.util.Hashtable;
import javax.management.MalformedObjectNameException;
import javax.management.ObjectName;

public final class JmxNames {
    private JmxNames() {}

    public static ObjectName queue(String logicalName)
            throws MalformedObjectNameException {
        if (logicalName == null || logicalName.isBlank()) {
            throw new IllegalArgumentException("logicalName is required");
        }

        Hashtable<String, String> properties = new Hashtable<>();
        properties.put("type", "Queue");
        properties.put("name", logicalName);
        return new ObjectName("com.example.orders", properties);
    }
}
```

Ví dụ:

```java
ObjectName objectName = JmxNames.queue("PaymentQueue");
```

Dùng constructor với `Hashtable<String,String>` để JMX xử lý quy tắc quote ký tự đặc biệt trong value theo API; khi xây chuỗi thủ công, dùng `ObjectName.quote(value)` với các value cần escape:

```java
String logicalName = "Billing,HighPriority";
ObjectName objectName = new ObjectName(
    "com.example.orders:type=Queue,name=" + ObjectName.quote(logicalName)
);
```

Đừng nối trực tiếp input không tin cậy vào mẫu tên JMX: dấu phẩy, dấu bằng, dấu hai chấm, dấu sao hoặc dấu hỏi có ý nghĩa đặc biệt trong cú pháp `ObjectName`. Đồng thời kiểm soát độ dài và tập ký tự của tên logic để tránh tạo số lượng MBean không giới hạn.

## 5. Một bản đăng ký MBean có vòng đời rõ ràng

Đây là ví dụ Standard MBean đơn giản:

```java
public interface QueueMonitorMBean {
    int getPendingCount();
    boolean isPaused();
    void setPaused(boolean paused);
}
```

```java
public final class QueueMonitor implements QueueMonitorMBean {
    private volatile boolean paused;

    @Override
    public int getPendingCount() {
        return 12;
    }

    @Override
    public boolean isPaused() {
        return paused;
    }

    @Override
    public void setPaused(boolean paused) {
        this.paused = paused;
    }
}
```

Đăng ký và hủy đăng ký:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public final class QueueJmxRegistration implements AutoCloseable {
    private final MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();
    private final ObjectName name;

    public QueueJmxRegistration(String logicalName) throws Exception {
        this.name = JmxNames.queue(logicalName);
        server.registerMBean(new QueueMonitor(), name);
    }

    public ObjectName getObjectName() {
        return name;
    }

    @Override
    public void close() throws Exception {
        if (server.isRegistered(name)) {
            server.unregisterMBean(name);
        }
    }
}
```

Sử dụng trong vòng đời ứng dụng:

```java
try (QueueJmxRegistration registration =
         new QueueJmxRegistration("PaymentQueue")) {
    System.out.println(registration.getObjectName());
    // Chạy ứng dụng/tài nguyên queue...
}
```

Sau restart, cấu hình `PaymentQueue` tạo lại cùng một `ObjectName`. Trong một JVM, hai MBean đăng ký đồng thời với cùng tên sẽ gây `InstanceAlreadyExistsException`: đó là dấu hiệu xung đột danh tính hoặc lỗi quản lý vòng đời cần xử lý, không nên giải quyết bằng cách tự động thêm UUID.

Trước khi đăng ký lại trong cùng JVM, cần xác định ai sở hữu MBean hiện có. Không tự ý `unregisterMBean` của component khác chỉ để giành lại tên.

## 6. Nhiều instance của cùng một ứng dụng

Một tình huống quan trọng: ba replica của dịch vụ cùng chạy queue `PaymentQueue`.

```text
Replica A -> com.example.orders:type=Queue,name=PaymentQueue
Replica B -> com.example.orders:type=Queue,name=PaymentQueue
Replica C -> com.example.orders:type=Queue,name=PaymentQueue
```

Điều này **không xung đột** nếu mỗi replica có `MBeanServer` riêng. Nhưng dashboard tập trung phải phân biệt các replica bằng định danh endpoint hoặc metadata deployment, ví dụ:

```text
(cluster=production, service=orders, instance=orders-0,
 ObjectName=com.example.orders:type=Queue,name=PaymentQueue)
```

Có hai chiến lược:

### A. ObjectName chỉ biểu diễn tài nguyên trong mỗi JVM

Giữ tên đơn giản, để monitoring/collector gắn nhãn endpoint hoặc service instance khi thu thập. Cách này thích hợp khi mỗi JVM có namespace riêng và nền tảng quan sát đã quản lý target identity.

### B. ObjectName mang thêm định danh instance bền vững

```text
com.example.orders:type=Queue,name=PaymentQueue,instance=orders-0
```

Chỉ phù hợp nếu `orders-0` thật sự là ID ổn định theo hợp đồng triển khai (chẳng hạn tên StatefulSet ordinal được giữ lại). Nếu chạy Deployment với pod name ngẫu nhiên sau mỗi lần triển khai, pod name không phải định danh bền vững. Nếu instance không có danh tính bền vững, hãy để tên local ổn định và để collector phân biệt các target theo nhãn phù hợp.

Không trộn “tên cùng vai trò logic” với “danh tính tiến trình” khi mục tiêu vận hành cần tổng hợp metric qua nhiều replica.

## 7. Canonical name và thứ tự key property

Hai chuỗi sau biểu diễn cùng một tập key property:

```text
com.example.orders:type=Queue,name=PaymentQueue
com.example.orders:name=PaymentQueue,type=Queue
```

Theo ngữ nghĩa `ObjectName`, thứ tự key property không làm đổi danh tính. Nếu cần một chuỗi chuẩn để lưu, so sánh hoặc ghi log, dùng `getCanonicalName()`, vì canonical form sắp xếp key property theo thứ tự xác định.

```java
ObjectName first = new ObjectName(
    "com.example.orders:type=Queue,name=PaymentQueue"
);
ObjectName second = new ObjectName(
    "com.example.orders:name=PaymentQueue,type=Queue"
);

System.out.println(first.equals(second)); // true
System.out.println(first.getCanonicalName());
```

Không tạo một hệ thống đặt tên dựa vào thứ tự properties của `HashMap` hoặc thứ tự string serialization; hãy dùng `ObjectName` như một kiểu giá trị.

**Điểm cần phân biệt:** canonicalization giúp ổn định biểu diễn của **cùng một danh tính**. Nó không thể làm tên có UUID/port/PID ngẫu nhiên trở thành danh tính bền vững.

## 8. Spring Framework JMX và chiến lược đặt tên ổn định

Trong Spring, `MBeanExporter` quản lý việc đăng ký bean vào JMX. Bạn có thể chỉ định `ObjectName` bằng annotation hoặc ánh xạ đăng ký rõ ràng:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.orders:type=Queue,name=PaymentQueue",
    description = "Payment queue monitor"
)
public class PaymentQueueMonitor {
    @ManagedAttribute
    public int getPendingCount() {
        return 12;
    }
}
```

Khi một service có nhiều queue, nên tránh hardcode cùng một `ObjectName` lên mọi bean. Dùng cấu hình hoặc cơ chế đặt tên thống nhất và ánh xạ mỗi tài nguyên sang một danh tính xác định.

Ví dụ đăng ký qua `MBeanExporter` với `beans` map:

```java
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class JmxConfiguration {
    @Bean
    public MBeanExporter queueMBeanExporter(PaymentQueueMonitor monitor) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setBeans(Map.of(
            "com.example.orders:type=Queue,name=PaymentQueue", monitor
        ));
        return exporter;
    }
}
```

Đây là cấu hình minh họa cho exporter rõ ràng; ứng dụng thực tế cần chọn một cơ chế đăng ký nhất quán, tránh đăng ký trùng cùng bean qua cả exporter tự động và exporter thủ công. Nếu dùng Spring Boot, cách bật JMX auto-configuration và exporter còn phụ thuộc phiên bản, cấu hình của ứng dụng.

Với các danh tính động, hãy tạo `ObjectName` bằng một `ObjectNamingStrategy` hoặc một factory trung tâm nhận stable ID từ cấu hình. Spring lifecycle giúp exporter đăng ký MBean khi context khởi tạo và hủy đăng ký khi đóng context bình thường; crash hoặc kill -9 có thể bỏ qua cleanup, nhưng MBeanServer của JVM đó cũng kết thúc theo tiến trình.

## 9. Tên ổn định giúp gì cho monitoring và automation?

Một script quản trị có thể truy vấn bằng chính xác `ObjectName`:

```java
ObjectName name = new ObjectName(
    "com.example.orders:type=Queue,name=PaymentQueue"
);
Integer pending = (Integer) connection.getAttribute(
    name, "PendingCount"
);
```

Nếu mỗi lần restart tên đổi thành `name=PaymentQueue-20261111T0900`, script có thể gặp `InstanceNotFoundException`. Phải tìm theo wildcard, tăng nguy cơ chọn nhầm MBean hoặc lấy nhầm giá trị từ phiên chạy không mong muốn.

Tên ổn định cải thiện:

- Cấu hình dashboard, panel và cảnh báo bám theo cùng một tài nguyên logic.
- Script điều hành và công cụ thu thập không cần cập nhật tên theo mỗi deploy.
- Phát hiện MBean mất/hiện lại qua restart mà vẫn giữ được mapping logic.
- So sánh attribute và operation qua các lần phát hành.
- Quy tắc truy cập và whitelist tên MBean dễ kiểm soát hơn.

Tuy nhiên, **ObjectName không phải khóa duy nhất toàn hệ thống qua mọi thời điểm**. Một MBean cùng tên trong phiên chạy mới không mang cùng trạng thái, counter hoặc event history của instance cũ. Đối với dữ liệu chuỗi thời gian, collector cần định nghĩa rõ các nhãn service, cluster, instance, môi trường và chiến lược xử lý counter reset.

## 10. Thay đổi danh tính là một migration

Giả sử quy ước cũ:

```text
com.example:type=Pool,name=Primary
```

Quy ước mới:

```text
com.example.db:type=ConnectionPool,name=Primary
```

Đây là thay đổi danh tính JMX. Đối với client truy vấn tên chính xác, nó có thể gây gián đoạn ngay cả khi class và attribute không đổi.

Một đợt migration nên:

1. Ghi rõ lý do đổi domain hoặc key property.
2. Liệt kê các dashboard, alert, script và chính sách truy cập phụ thuộc tên cũ.
3. Nếu cần và được hỗ trợ, xuất alias MBean trong giai đoạn chuyển tiếp (cùng logic được quản trị dưới hai tên riêng), cẩn trọng không đăng ký trùng `ObjectName`.
4. Cập nhật client và định tuyến metric theo tên mới.
5. Loại bỏ alias sau khi downstream đã chuyển đổi.

Không đổi `name` chỉ vì đổi class Java nội bộ hay thay framework implementation. Hợp đồng JMX là giao diện vận hành, nên tên logic có vòng đời độc lập với code refactor.

## 11. Cách kiểm tra tên qua restart

Có thể thử bằng một chương trình nhỏ sử dụng `ManagementFactory.getPlatformMBeanServer()`, đăng ký `QueueMonitor` theo `JmxNames.queue("PaymentQueue")`, rồi in canonical name. Chạy chương trình hai lần độc lập:

```text
Run 1: com.example.orders:name=PaymentQueue,type=Queue
Run 2: com.example.orders:name=PaymentQueue,type=Queue
```

Nếu cấu hình không thay đổi, hai canonical name phải giống nhau. Đồng thời thử hai queue khác nhau:

```text
com.example.orders:name=PaymentQueue,type=Queue
com.example.orders:name=RefundQueue,type=Queue
```

Hai tài nguyên cần hai tên phân biệt. Thử đăng ký trùng một tên trong cùng `MBeanServer`: phải thấy `InstanceAlreadyExistsException`, rồi sửa cơ chế ownership/đăng ký thay vì gắn suffix ngẫu nhiên.

Trong môi trường Spring, test integration có thể khởi tạo một `ApplicationContext` cho cấu hình JMX, đọc `MBeanServer.queryNames`, đóng context và khởi tạo context mới để so canonical names. Khi dùng một `MBeanServer` chung, test cần đảm bảo context đầu đã unregister xong trước khi mở context thứ hai để không nhầm xung đột lifecycle với sự bất ổn tên.

## 12. Các lỗi thiết kế thường gặp

**Dùng `Object.hashCode()` hoặc `identityHashCode()` làm key.** Các giá trị này không được thiết kế làm danh tính bền vững xuyên khởi động.

**Sinh UUID tại thời điểm đăng ký.** UUID mới mỗi lần có ích cho run ID, nhưng phá hợp đồng tìm kiếm theo tên chính xác. Nếu UUID thật sự là ID nghiệp vụ được lưu bền vững, nó có thể dùng làm tên, miễn có ý nghĩa vận hành và không chứa dữ liệu nhạy cảm.

**Dùng index thứ tự trong một danh sách.** `worker=0` không ổn định nếu danh sách bị sắp xếp lại hoặc instance được tạo/hủy động. Chỉ dùng ordinal khi nó là phần của danh tính được quản lý có bảo đảm.

**Đưa trạng thái động vào key property.** `status=ACTIVE` sẽ làm tên đổi khi tài nguyên chuyển trạng thái. Dùng attribute `State`.

**Đặt cùng một tên cho hai MBean trong cùng JVM.** Không thể đăng ký đồng thời; cần bổ sung khóa logic phân biệt hoặc thiết kế lại tài nguyên.

**Tin rằng tên giống nhau có nghĩa luôn cùng endpoint.** `ObjectName` chỉ định danh trong `MBeanServer`; remote client còn phải chọn đúng endpoint và xử lý reconnect.

**Dựa vào canonical string để hợp thức hóa tên ngẫu nhiên.** Canonicalization chỉ thống nhất thứ tự key property, không thay giá trị.

## 13. Bài tập thực hành

1. Thiết kế `ObjectName` cho `Cache` tên `ProductCatalog`, có thuộc tính `HitCount`, `Size`, `StartTimeMillis`. Chọn trường nào thuộc tên và trường nào thuộc attribute.
2. Một ứng dụng tạo MBean tên `service:type=Worker,pid=12345`. Mô tả tác hại sau restart và đề xuất tên logic thay thế.
3. So sánh hai chuỗi tên có thứ tự key khác nhau bằng `ObjectName.equals()` và `getCanonicalName()`.
4. Cho một hệ thống có 4 replica, mỗi replica có queue `PaymentQueue`. Thiết kế cách collector phân biệt target mà không dựa vào pod name thay đổi liên tục.
5. Viết một integration test khởi tạo hai Spring context lần lượt và xác nhận `ObjectName` của cùng một MBean cấu hình vẫn giống nhau.

## 14. Câu hỏi tự kiểm tra

- Vì sao không nên đưa PID, timestamp hoặc UUID sinh mới vào `ObjectName` của tài nguyên ổn định?
- `ObjectName` có bảo đảm duy nhất giữa nhiều JVM hay chỉ trong một `MBeanServer`?
- Hai `ObjectName` có key property giống nhau nhưng thứ tự khác nhau có bằng nhau không?
- Sự khác nhau giữa định danh tài nguyên, định danh phiên chạy và định danh endpoint là gì?
- Khi đổi domain từ `com.example` sang `com.example.db`, vì sao cần coi đó là migration?
- Spring `MBeanExporter` giúp gì cho lifecycle của MBean, và điều gì vẫn cần do ứng dụng quy định?

**Ghi nhớ:** Hãy đặt `ObjectName` bằng danh tính logic có kiểm soát và ổn định từ cấu hình. Giữ dữ liệu biến đổi theo mỗi phiên chạy dưới dạng attribute, dùng canonical name khi cần biểu diễn chuẩn và tách danh tính MBean khỏi danh tính kết nối/replica trong hệ thống phân tán.