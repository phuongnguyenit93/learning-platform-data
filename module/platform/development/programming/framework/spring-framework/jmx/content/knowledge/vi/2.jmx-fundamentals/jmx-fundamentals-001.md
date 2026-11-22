# Java Management Extensions (JMX) gồm những thành phần nào?

## 1. JMX là gì và giải quyết vấn đề nào?

**Java Management Extensions (JMX)** là tập hợp đặc tả và API của Java dùng để **quản lý, giám sát và điều khiển tài nguyên tại thời gian chạy**. Tài nguyên (managed resource) có thể là một đối tượng Java, thread pool, bộ nhớ JVM, bộ đệm, thành phần ứng dụng hoặc một dịch vụ. JMX cho phép các công cụ quản trị đọc trạng thái, thay đổi một số thuộc tính được phép, gọi thao tác và nhận thông báo sự kiện mà không phải thiết kế một giao diện quản trị riêng cho từng thành phần.

Một mô hình JMX điển hình có ba lớp:

```text
Công cụ quản trị (JConsole, VisualVM, ứng dụng giám sát)
                  |
         Connector / Protocol
                  |
        MBeanServer (agent layer)
                  |
       MBeans (instrumentation layer)
                  |
     Đối tượng / tài nguyên được quản lý
```

Trong thực tế, các lớp có thể chạy trong cùng JVM hoặc kết nối từ xa. JMX không mặc định biến mọi đối tượng Java thành đối tượng quản lý; ứng dụng hoặc thư viện cần xuất các thành phần phù hợp dưới dạng MBean.

## 2. Lớp instrumentation: tài nguyên được biểu diễn bằng MBean

**MBean (Managed Bean)** là đối tượng Java tuân theo quy ước hoặc giao diện JMX để công bố các khả năng quản trị. Mỗi MBean có thể công bố:

- **Attribute:** trạng thái có thể đọc, có thể ghi hoặc cả hai, chẳng hạn `ActiveCount` hoặc `Enabled`.
- **Operation:** hành động được gọi bởi trình quản trị, chẳng hạn `clearCache()` hoặc `resetStatistics()`.
- **Notification:** sự kiện bất đồng bộ, chẳng hạn cảnh báo ngưỡng hoặc thay đổi trạng thái.
- **Metadata:** mô tả tên, kiểu dữ liệu, tham số và quyền đọc/ghi/gọi mà client có thể khám phá thông qua `MBeanInfo`.

Các kiểu MBean quan trọng:

| Kiểu | Cách định nghĩa giao diện quản trị | Khi nào hữu ích |
| --- | --- | --- |
| **Standard MBean** | Interface có tên `<ClassName>MBean`, cùng các phương thức công khai đúng quy ước | API quản trị ổn định, dễ hiểu, kiểm tra kiểu khi biên dịch |
| **MXBean** | Interface kết thúc bằng `MXBean` hoặc đánh dấu `@MXBean`; ánh xạ kiểu dữ liệu sang các kiểu mở của JMX | Cần dữ liệu tương tác giữa JVM/client và công cụ quản trị |
| **Dynamic MBean** | Implement `DynamicMBean`; tự cung cấp `MBeanInfo`, đọc/ghi attribute và gọi operation bằng tên | Cấu trúc thuộc tính/phương thức được xác định động |
| **Model MBean** | MBean cấu hình theo metadata, thường dùng `RequiredModelMBean` | Muốn mô tả/quản trị các tài nguyên có cấu hình linh hoạt |

**Standard MBean** và **MXBean** là lựa chọn thường gặp khi bắt đầu. **Dynamic MBean** đem lại khả năng tùy biến nhưng đòi hỏi viết nhiều mã xử lý metadata. MXBean hữu ích cho khả năng tương thích qua kết nối quản trị vì JMX quy định ánh xạ về các *open types*, thay vì yêu cầu client phải có mọi lớp Java của ứng dụng.

### Ví dụ: một Standard MBean

```java
public interface CacheMetricsMBean {
    int getEntryCount();   // Read-only attribute: EntryCount
    boolean isEnabled();   // Read-only attribute: Enabled
    void clear();          // Operation: clear()
}
```

```java
public class CacheMetrics implements CacheMetricsMBean {
    private volatile boolean enabled = true;
    private final java.util.concurrent.atomic.AtomicInteger entryCount =
            new java.util.concurrent.atomic.AtomicInteger();

    @Override
    public int getEntryCount() {
        return entryCount.get();
    }

    @Override
    public boolean isEnabled() {
        return enabled;
    }

    @Override
    public void clear() {
        entryCount.set(0);
    }
}
```

Trong ví dụ này, `getEntryCount()` được JMX biểu diễn thành attribute `EntryCount`; `isEnabled()` thành attribute `Enabled`; và `clear()` là operation. Đây là giao diện quản trị; logic vận hành thực tế phải được thiết kế phù hợp với tài nguyên thật (ví dụ xóa cache có đồng bộ với bộ nhớ cache thực, chứ không chỉ đặt lại bộ đếm).

## 3. Lớp agent: MBeanServer và ObjectName

**MBeanServer** là registry và điểm truy cập trung tâm của các MBean trong một JVM. Nó đăng ký/hủy đăng ký MBean, tìm MBean theo tên, truy vấn thuộc tính, gọi operation và điều phối notification. Client quản trị không nhất thiết giữ tham chiếu trực tiếp tới đối tượng Java; client làm việc thông qua MBeanServer.

JVM cung cấp **platform MBeanServer**, thường được lấy bằng:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class JmxRegistrationExample {
    public static void main(String[] args) throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();
        ObjectName name = new ObjectName(
                "com.example.cache:type=CacheMetrics,name=primary"
        );

        CacheMetrics bean = new CacheMetrics();
        if (!server.isRegistered(name)) {
            server.registerMBean(bean, name);
        }

        System.out.println("Registered: " + name);
    }
}
```

**ObjectName** là tên định danh MBean, có dạng `domain:key=value[,key=value...]`. Trong ví dụ, `com.example.cache` là domain; `type=CacheMetrics,name=primary` là các key property. Một ObjectName phải phân biệt được MBean trong MBeanServer; đăng ký hai MBean cùng tên sẽ gây lỗi `InstanceAlreadyExistsException` trừ khi xử lý theo thiết kế.

Có thể dùng `MBeanServerFactory.createMBeanServer()` để tạo server khác, nhưng **platform MBeanServer** là lựa chọn thường gặp để các công cụ JVM khám phá và đọc các MXBean hệ thống bên cạnh MBean của ứng dụng.

### Các MBean có sẵn của JVM

Nền tảng Java xuất nhiều MXBean trong các nhóm như:

- **MemoryMXBean** và **MemoryPoolMXBean:** bộ nhớ heap/non-heap, memory pool, ngưỡng sử dụng.
- **ThreadMXBean:** số thread, trạng thái thread, deadlock và một số chỉ số CPU/thời gian tùy khả năng JVM.
- **GarbageCollectorMXBean:** thông tin bộ thu gom rác và chỉ số collection.
- **ClassLoadingMXBean:** số lớp đã nạp/gỡ.
- **RuntimeMXBean:** tên, uptime và các thông tin runtime.
- **OperatingSystemMXBean:** thông tin hệ điều hành theo hợp đồng chuẩn; một số JVM có phần mở rộng riêng.

Các MXBean nền tảng có thể dùng qua `ManagementFactory` hoặc truy cập gián tiếp qua MBeanServer. Không nên giả định mọi JVM đều cung cấp mọi chỉ số nâng cao; ứng dụng nên kiểm tra khả năng được hỗ trợ.

## 4. Lớp distributed services: kết nối quản trị và công cụ client

**JMX connector** cho phép một ứng dụng quản trị truy cập MBeanServer, kể cả khi client chạy ở tiến trình khác. Một số khái niệm liên quan:

- **JMXConnectorServer:** cung cấp đầu cuối cho các client từ xa.
- **JMXConnector / MBeanServerConnection:** phía client tạo kết nối, truy vấn MBean và gọi các phương thức quản trị.
- **JMX Remote API:** API kết nối từ xa; Java SE thường cung cấp JMX qua **RMI**. Khả năng hỗ trợ giao thức khác phụ thuộc môi trường hoặc connector triển khai bổ sung.
- **Management client:** ví dụ JConsole, các tính năng JMX trong VisualVM hoặc phần mềm giám sát tương thích.

Ví dụ truy xuất thuộc tính bằng giao diện `MBeanServerConnection` (ở đây kết nối nội bộ thông qua platform server):

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;

public class ReadJmxAttribute {
    public static void main(String[] args) throws Exception {
        MBeanServerConnection connection =
                ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
                "java.lang:type=Memory"
        );
        Object heapUsage = connection.getAttribute(
                name, "HeapMemoryUsage"
        );

        System.out.println(heapUsage);
    }
}
```

`HeapMemoryUsage` của Memory MXBean được trình bày dưới dạng dữ liệu quản lý phù hợp qua API JMX. Việc kết nối từ xa thay đổi cách nhận `MBeanServerConnection`, nhưng các thao tác khám phá MBean, đọc attribute hay gọi operation tuân theo cùng mô hình.

## 5. Notification: cơ chế nhận sự kiện

Ngoài polling attribute theo chu kỳ, JMX hỗ trợ thông báo sự kiện:

- Một MBean có thể là **NotificationBroadcaster**, thường dựa vào `NotificationBroadcasterSupport`.
- MBean phát một **Notification** có loại sự kiện, sequence number, timestamp và nội dung mô tả.
- Client đăng ký **NotificationListener** và tùy chọn **NotificationFilter**; listener được thông báo khi có sự kiện phù hợp.
- **MBeanServerDelegate** còn cung cấp notification khi MBean được đăng ký hoặc hủy đăng ký.

Ví dụ emitter đơn giản:

```java
import javax.management.Notification;
import javax.management.NotificationBroadcasterSupport;
import java.util.concurrent.atomic.AtomicLong;

public class ThresholdEmitter extends NotificationBroadcasterSupport {
    private final AtomicLong sequence = new AtomicLong();

    public void thresholdExceeded(int value) {
        sendNotification(new Notification(
                "com.example.threshold.exceeded",
                this,
                sequence.incrementAndGet(),
                System.currentTimeMillis(),
                "Threshold exceeded, current value=" + value
        ));
    }
}
```

Lớp ví dụ cho thấy cách phát notification; để công cụ JMX thấy nó, cần xuất một MBean tương ứng và đăng ký vào MBeanServer. Notification phù hợp cho sự kiện ngưỡng hoặc biến cố hiếm; polling vẫn hữu ích cho các số liệu liên tục. Vì các notification là thông báo runtime, không nên xem chúng là hàng đợi sự kiện bền vững hoặc cơ chế giao dịch.

## 6. Metadata, kiểu dữ liệu và bảo mật cũng là thành phần quan trọng

JMX có hệ thống metadata để client khám phá các khả năng của MBean mà không cần biết trước mã nguồn. Ví dụ:

- `MBeanInfo`: mô tả toàn bộ MBean.
- `MBeanAttributeInfo`, `MBeanOperationInfo`: mô tả attribute và operation.
- `MBeanNotificationInfo`: mô tả các loại notification.
- **Open MBean types** như `CompositeData`, `TabularData`: cách biểu diễn cấu trúc dữ liệu để các client có thể đọc được mà không phụ thuộc lớp Java cụ thể.

Vì JMX có thể cung cấp quyền **đọc dữ liệu vận hành, thay đổi cấu hình và thực thi thao tác**, kết nối JMX từ xa cần được quản lý nghiêm ngặt. Tùy môi trường, cần cấu hình authentication, TLS, network restrictions và phân quyền phù hợp. Không bật một cổng JMX quản trị công khai mà không có bảo vệ. Với RMI, cần chú ý endpoint/port và cấu hình mạng, vì quá trình kết nối có thể sử dụng thêm endpoint khác ngoài địa chỉ ban đầu.

## 7. JMX trong Spring Framework

Spring Framework hỗ trợ đưa các bean ứng dụng thành MBean và tích hợp cơ chế JMX trong namespace `org.springframework.jmx`:

- **`MBeanExporter`**: xuất các Spring bean được chọn vào MBeanServer.
- **`@ManagedResource`, `@ManagedAttribute`, `@ManagedOperation`**: annotation mô tả tài nguyên, thuộc tính và thao tác quản trị; thường đi cùng `AnnotationMBeanExporter` hoặc cấu hình tương ứng.
- **`MBeanServerFactoryBean`**: tạo hoặc tìm MBeanServer theo cấu hình.
- **`MBeanProxyFactoryBean`**: client proxy giúp gọi MBean qua giao diện Java.
- **`NotificationPublisher`** và listener tích hợp: xuất và xử lý notification trong mô hình Spring.

Ví dụ Spring Java configuration:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.annotation.AnnotationMBeanExporter;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(objectName = "com.example:type=CacheAdmin")
class CacheAdmin {
    private int entries;

    @ManagedAttribute
    public int getEntries() {
        return entries;
    }

    @ManagedOperation
    public void reset() {
        entries = 0;
    }
}

@Configuration
class JmxConfig {
    @Bean
    CacheAdmin cacheAdmin() {
        return new CacheAdmin();
    }

    @Bean
    static AnnotationMBeanExporter annotationMBeanExporter() {
        return new AnnotationMBeanExporter();
    }
}
```

Với cấu hình này, exporter có thể đăng ký bean `CacheAdmin` làm MBean có tên `com.example:type=CacheAdmin`, từ đó client JMX có thể đọc attribute `Entries` và gọi operation `reset`. Đoạn mã nhằm minh họa các vai trò thành phần; ứng dụng thực tế nên có chiến lược tránh trùng ObjectName và thiết kế truy cập đa luồng phù hợp với các method quản trị.

Spring Boot còn có các thiết lập để bật/tắt việc xuất bean qua JMX hoặc tổ chức endpoint quản trị, tùy phiên bản và dependency. **Khái niệm JMX nền tảng vẫn là MBean, MBeanServer và client/connector**; phần Spring là lớp hỗ trợ khai báo và đăng ký.

## 8. Luồng xử lý tổng thể

Giả sử một dịch vụ có cache và cần theo dõi số phần tử:

1. Lập trình viên định nghĩa một MBean biểu diễn cache, công bố `EntryCount` và `clear()`.
2. Ứng dụng hoặc Spring exporter đăng ký MBean với ObjectName `com.example.cache:type=CacheMetrics,name=primary` vào MBeanServer.
3. Client quản trị kết nối đến MBeanServer tại chỗ hoặc qua connector từ xa.
4. Client tìm ObjectName, đọc `EntryCount` hay gọi `clear()`; MBeanServer chuyển tiếp thao tác đến MBean.
5. Nếu có phát notification, client đã đăng ký listener có thể nhận sự kiện khi ngưỡng bị vượt.

```text
[Java resource]
      |
      v
[MBean: attributes / operations / notifications]
      |
      | đăng ký bằng ObjectName
      v
[MBeanServer] <-- MBeanInfo / registry / dispatcher
      ^
      | JMX connection hoặc in-process
      |
[JConsole / VisualVM / Monitoring client]
```

## 9. Những điểm dễ nhầm

**MBean có phải JavaBean thông thường không?** Không. Standard MBean áp dụng quy ước interface JMX cụ thể; việc một đối tượng có getter/setter JavaBean không tự động làm nó trở thành MBean.

**JMX có phải công cụ giám sát duy nhất không?** Không. JMX là một API/kiến trúc quản trị Java. Các công cụ quan sát hiện đại còn có metrics, logs, traces và hệ thống thu thập tập trung. JMX có thể là nguồn dữ liệu cho các hệ thống đó.

**MBeanServer có phải server HTTP không?** Không. Đây là đối tượng Java giữ registry và phục vụ thao tác quản trị. Kết nối từ xa cần connector/protocol tương ứng.

**Attribute có luôn sửa được không?** Không. Phụ thuộc giao diện MBean và metadata; một số chỉ đọc, một số có thể ghi. Operation cũng chỉ tồn tại khi MBean công bố.

**JMX có tự an toàn khi bật remote không?** Không. Cần kiểm soát truy cập, bảo mật kênh và phạm vi mạng trước khi sử dụng.

## 10. Tổng kết

Có thể nhớ các thành phần JMX theo ba lớp chính:

| Lớp | Thành phần | Trách nhiệm |
| --- | --- | --- |
| Instrumentation | Managed resource, MBean, attributes, operations, notifications, metadata | Công bố trạng thái và hành động quản trị |
| Agent | MBeanServer, ObjectName, platform MXBeans | Đăng ký, định danh, khám phá và điều phối MBean |
| Distributed services | JMX connector, `MBeanServerConnection`, client quản trị | Truy cập MBeanServer tại chỗ hoặc từ xa |

Trong **Spring Framework**, `MBeanExporter`, các annotation JMX và những factory/proxy hỗ trợ làm việc với kiến trúc trên thuận tiện hơn. Khi phân tích một hệ thống JMX, hãy lần theo câu hỏi: *Tài nguyên nào được xuất? MBean công bố gì? ObjectName nào định danh nó? MBeanServer nào lưu nó? Client truy cập bằng đường nào và với quyền gì?*

### Tài liệu tham khảo

- Oracle Java SE — Java Management Extensions (JMX) Technology: https://docs.oracle.com/javase/tutorial/jmx/
- Java SE API — `javax.management` và `java.lang.management`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/module-summary.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
