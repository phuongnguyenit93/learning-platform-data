# notificationListeners và NotificationListenerBean trong Spring JMX

## 1. Mục tiêu

JMX Notification là cơ chế để một MBean **chủ động phát sự kiện quản trị** khi trạng thái thay đổi, thay vì buộc client liên tục polling attribute. Spring Framework hỗ trợ đăng ký listener JMX thông qua `MBeanExporter`, đặc biệt là property `notificationListeners` và lớp `NotificationListenerBean`.

Bài này tập trung vào cách dùng `NotificationListenerBean` để liên kết một `NotificationListener` với những MBean cụ thể, thiết lập `NotificationFilter`, `handback`, tổ chức lifecycle đăng ký/gỡ đăng ký và kiểm thử trên một `MBeanServer` thực.

Sau khi học, bạn cần phân biệt được:

- **MBean phát notification**: đối tượng triển khai cơ chế `NotificationBroadcaster` hoặc `NotificationEmitter`.
- **NotificationListener**: callback nhận `Notification` đã phát.
- **NotificationListenerBean**: cấu hình Spring bao bọc listener cùng filter, handback và danh sách MBean cần lắng nghe.
- **MBeanExporter.notificationListeners**: danh sách các listener registration mà exporter quản lý trong quá trình đăng ký những MBean.
- **ObjectName mapped**: đích đăng ký listener, không phải tên Java bean dùng để gọi phương thức nghiệp vụ.

## 2. Notification đi từ đâu đến đâu?

Một luồng cơ bản:

```text
Spring ApplicationContext
  |
  +-- Managed bean / NotificationPublisherAware
  |         |
  |         v
  |    MBean được export
  |         |
  |         v
  |    MBeanServer
  |         |
  |    Notification từ MBean
  |         |
  |         v
  +-- MBeanExporter.notificationListeners
            |
            v
      NotificationListenerBean
         |       |        |
      listener  filter  handback
         |
         v
    handleNotification(...)
```

Trong một trường hợp Spring annotation-driven, bean có thể dùng `NotificationPublisherAware` để nhận `NotificationPublisher` rồi phát sự kiện. Một cách khác là một MBean chuẩn trực tiếp sử dụng `NotificationBroadcasterSupport` của JMX API.

Điểm quan trọng: `NotificationListenerBean` **không tự biến bean bất kỳ thành notification source**. Nó chỉ đăng ký listener với những MBean có khả năng phát notification. Nếu MBean không là `NotificationBroadcaster`, việc đăng ký listener có thể thất bại theo cơ chế JMX.

## 3. Các thành phần JMX cốt lõi

### 3.1. Notification

`javax.management.Notification` mang metadata sự kiện:

- `type`: chuỗi phân loại sự kiện, ví dụ `com.example.jobs.worker.paused`.
- `source`: nguồn phát.
- `sequenceNumber`: số thứ tự do emitter quản lý.
- `timeStamp`: thời gian phát.
- `message`: mô tả ngắn.
- `userData`: dữ liệu bổ sung nếu có.

Ví dụ:

```java
import javax.management.Notification;

Notification notification = new Notification(
    "com.example.jobs.worker.paused",
    this,
    17L,
    System.currentTimeMillis(),
    "Worker paused by administrator"
);
```

Không đưa password, token, dữ liệu khách hàng hay object graph nhạy cảm vào `message` hoặc `userData`. Notification có thể đi qua remote JMX connector nếu hệ thống cho phép client từ xa đăng ký listener.

### 3.2. NotificationListener

Listener là callback của JMX:

```java
import javax.management.Notification;
import javax.management.NotificationListener;

public final class WorkerEventListener
        implements NotificationListener {

    @Override
    public void handleNotification(
            Notification notification,
            Object handback) {

        System.out.println(
            "type=" + notification.getType() +
            ", sequence=" + notification.getSequenceNumber() +
            ", handback=" + handback
        );
    }
}
```

Callback nên thực thi nhanh, không giữ lock nghiệp vụ lâu và không ném exception làm ảnh hưởng đường dispatch của emitter. Nếu cần xử lý sự kiện tốn thời gian, đưa công việc sang executor có giới hạn queue và chính sách backpressure rõ ràng.

### 3.3. NotificationFilter

`NotificationFilter` quyết định notification nào đi tới listener:

```java
import javax.management.Notification;
import javax.management.NotificationFilter;

NotificationFilter pausedOnly =
    (Notification n) ->
        "com.example.jobs.worker.paused".equals(n.getType());
```

Filter phù hợp khi cùng một MBean có nhiều notification types nhưng một listener chỉ cần một tập con. Filter khác với việc chọn ObjectName: **ObjectName chọn emitter**, filter chọn **loại event từ emitter ấy**.

## 4. NotificationBroadcasterSupport: một nguồn sự kiện mẫu

Tạo Standard MBean phát sự kiện:

```java
package com.example.jobs.jmx;

public interface WorkerControlMBean {
    boolean isPaused();
    void pause();
    void resume();
}
```

Implementation:

```java
package com.example.jobs.jmx;

import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;
import javax.management.MBeanNotificationInfo;
import javax.management.Notification;
import javax.management.NotificationBroadcasterSupport;

public final class WorkerControl
        extends NotificationBroadcasterSupport
        implements WorkerControlMBean {

    private final AtomicBoolean paused = new AtomicBoolean();
    private final AtomicLong sequence = new AtomicLong();

    @Override
    public boolean isPaused() {
        return paused.get();
    }

    @Override
    public void pause() {
        if (paused.compareAndSet(false, true)) {
            publish("com.example.jobs.worker.paused",
                    "Worker is paused");
        }
    }

    @Override
    public void resume() {
        if (paused.compareAndSet(true, false)) {
            publish("com.example.jobs.worker.resumed",
                    "Worker is resumed");
        }
    }

    private void publish(String type, String message) {
        Notification event = new Notification(
            type,
            this,
            sequence.incrementAndGet(),
            System.currentTimeMillis(),
            message
        );
        sendNotification(event);
    }

    @Override
    public MBeanNotificationInfo[] getNotificationInfo() {
        return new MBeanNotificationInfo[] {
            new MBeanNotificationInfo(
                new String[] {
                    "com.example.jobs.worker.paused",
                    "com.example.jobs.worker.resumed"
                },
                Notification.class.getName(),
                "Worker lifecycle state changes"
            )
        };
    }
}
```

`NotificationBroadcasterSupport` thực hiện phần đăng ký listener và gửi notification; `WorkerControlMBean` định nghĩa thuộc tính/operation Standard MBean.

Trong môi trường có nhiều thread gọi `pause`/`resume`, sequence counter có tính duy nhất và tăng nhờ `AtomicLong`. Nhưng nếu có notification phát từ nguồn khác, cần bảo đảm quy ước sequence nhất quán theo emitter.

## 5. Spring MBeanExporter và notificationListeners

`MBeanExporter` cung cấp property để đăng ký các `NotificationListenerBean`:

```java
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.NotificationListenerBean;

MBeanExporter exporter = new MBeanExporter();

NotificationListenerBean registration =
    new NotificationListenerBean();

registration.setNotificationListener(
    new WorkerEventListener()
);

exporter.setNotificationListeners(registration);
```

Đây là cấu hình rút gọn nhằm minh họa API; exporter còn cần lựa chọn MBean và server phù hợp. Nếu không chỉ định MBean nào cần lắng nghe, behavior và phạm vi matching phải được xem theo API Spring đang dùng. Trong ứng dụng có nhiều MBean, **nên cấu hình danh sách ObjectName một cách tường minh** để tránh vô tình nhận event từ nguồn không liên quan.

`notificationListeners` là cấu hình của exporter: đừng nhầm nó với `NotificationListener` làm callback, và cũng đừng coi nó là một registry notification độc lập với JMX.

## 6. Cấu hình listener cho ObjectName cụ thể

Ví dụ Spring Java config đầy đủ theo một Standard MBean:

```java
package com.example.jobs.config;

import com.example.jobs.jmx.WorkerControl;
import com.example.jobs.jmx.WorkerEventListener;
import java.lang.management.ManagementFactory;
import java.util.Map;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.NotificationListenerBean;

@Configuration
public class WorkerJmxConfig {

    @Bean
    public MBeanServer mbeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public WorkerControl workerControl() {
        return new WorkerControl();
    }

    @Bean
    public WorkerEventListener workerEventListener() {
        return new WorkerEventListener();
    }

    @Bean
    public MBeanExporter workerExporter(
            MBeanServer server,
            WorkerControl control,
            WorkerEventListener listener) throws Exception {

        ObjectName name = new ObjectName(
            "com.example.jobs:type=Worker,name=Primary"
        );

        NotificationListenerBean registration =
            new NotificationListenerBean();

        registration.setNotificationListener(listener);
        registration.setMappedObjectNames(name);

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(server);
        exporter.setBeans(Map.of(name.toString(), control));
        exporter.setNotificationListeners(registration);
        return exporter;
    }
}
```

Mẫu này biểu diễn ý định: exporter đăng ký MBean dưới một ObjectName cụ thể và đăng ký listener cho đúng ObjectName đó.

Lưu ý Spring có các overload/mapping cho `setMappedObjectNames` và có thể hỗ trợ tên dạng `ObjectName` hoặc `String` tùy phiên bản. Khi dùng đúng Spring Framework version của dự án, cần đối chiếu API thực tế; ví dụ dùng `ObjectName` làm tên đích để tránh parse chuỗi tùy tiện.

Nếu Spring Boot đã tạo một exporter qua auto-configuration, không nên thêm một exporter khác cùng export `WorkerControl` mà không kiểm tra ownership và collision. Một context có hai exporter ghi cùng `ObjectName` vào platform server có thể gặp `InstanceAlreadyExistsException`.

## 7. ObjectName mapping hoạt động thế nào?

`NotificationListenerBean` có danh sách **mapped object names**, chỉ những MBean tương ứng mới được exporter gắn listener. Ví dụ:

```java
ObjectName primary = new ObjectName(
    "com.example.jobs:type=Worker,name=Primary"
);

ObjectName secondary = new ObjectName(
    "com.example.jobs:type=Worker,name=Secondary"
);

registration.setMappedObjectNames(primary, secondary);
```

Khi exporter xử lý các MBean thuộc phạm vi export, listener được đăng ký cho những tên khớp. Một listener có thể nhận notification từ nhiều MBean; callback nên đọc `notification.getSource()` hoặc nhận diện nguồn bằng metadata thích hợp để phân biệt.

Nếu cần loại sự kiện chỉ từ Primary, không nên chỉ lọc theo `type` vì Secondary có thể phát cùng type. Hãy giới hạn bằng ObjectName và dùng filter theo type nếu cần.

Với tên ObjectName động, cần validate canonical name và không dùng wildcard tùy ý khi chưa chắc cơ chế mapping hỗ trợ pattern matching như mong muốn. Dấu `*` hoặc `?` trong JMX có thể tạo ObjectName pattern, không còn là identity đơn lẻ.

## 8. NotificationFilter và handback trong NotificationListenerBean

Một registration có thể cung cấp filter và handback:

```java
import javax.management.NotificationFilter;
import org.springframework.jmx.export.NotificationListenerBean;

NotificationFilter filter = event ->
    "com.example.jobs.worker.paused".equals(event.getType());

NotificationListenerBean registration =
    new NotificationListenerBean();

registration.setNotificationListener(listener);
registration.setNotificationFilter(filter);
registration.setHandback("operations-audit");
registration.setMappedObjectNames(
    new ObjectName("com.example.jobs:type=Worker,name=Primary")
);
```

Ở callback:

```java
@Override
public void handleNotification(
        Notification notification, Object handback) {

    if ("operations-audit".equals(handback)) {
        // Xử lý nhánh audit.
    }
}
```

**Handback** là object do bên đăng ký listener cung cấp và được trả lại khi notification tới. Nó không phải dữ liệu userData do emitter đặt trong Notification.

Điều này đặc biệt hữu ích khi cùng một listener được đăng ký trên nhiều nguồn:

```text
Emitter A --listener/filter/handback="cluster-a"--> callback
Emitter B --listener/filter/handback="cluster-b"--> callback
```

Không đưa một object lớn giữ reference tới toàn bộ `ApplicationContext` làm handback nếu không thật cần, vì registration có thể giữ reference ấy trong thời gian tồn tại và làm phức tạp cleanup.

## 9. MappedObjectNames và autodetection

Nếu exporter dùng autodetection để tìm MBean, cần hiểu phạm vi listener:

- Exporter có thể tìm các bean ứng dụng đủ điều kiện đăng ký.
- Naming strategy quyết định ObjectName cuối cùng.
- NotificationListenerBean được gắn theo những tên mapped object names.
- Nếu tên thực tế không giống tên mong đợi, listener có thể không được gắn dù MBean đã xuất thành công.

Ví dụ annotation-driven:

```java
@ManagedResource(
    objectName = "com.example.jobs:type=Worker,name=Primary"
)
public class WorkerManagementAdapter {
    // ...
}
```

Nếu naming strategy hoặc cấu hình nhiều context thêm key `instance`, ObjectName cuối cùng có thể khác; listener mapping theo một tên tĩnh sẽ không còn khớp.

Để chẩn đoán, in `server.queryNames(...)` rồi đối chiếu canonical ObjectName với danh sách được cấu hình cho listener. Không giả định Spring bean ID tự động là ObjectName.

## 10. NotificationPublisherAware trong Spring

Spring cũng hỗ trợ một con đường phát notification dành cho bean quản trị: implement `NotificationPublisherAware` để nhận publisher khi bean được export phù hợp.

Ví dụ:

```java
import java.util.concurrent.atomic.AtomicLong;
import javax.management.Notification;
import org.springframework.jmx.export.notification.NotificationPublisher;
import org.springframework.jmx.export.notification.NotificationPublisherAware;

public final class JobNotificationSource
        implements NotificationPublisherAware {

    private final AtomicLong sequence = new AtomicLong();
    private NotificationPublisher publisher;

    @Override
    public void setNotificationPublisher(
            NotificationPublisher publisher) {
        this.publisher = publisher;
    }

    public void reportJobCompleted(String jobId) {
        Notification event = new Notification(
            "com.example.jobs.completed",
            this,
            sequence.incrementAndGet(),
            System.currentTimeMillis(),
            "Job completed"
        );
        publisher.sendNotification(event);
    }
}
```

Đoạn ví dụ giả định lifecycle exporter đã inject `NotificationPublisher` trước khi `reportJobCompleted` được gọi. Trong hệ thống thật cần guard việc publisher chưa sẵn sàng, nhất là khi bean được dùng trước đăng ký JMX hoặc khi context đang shutdown.

`NotificationPublisherAware` là **phía emitter**; `NotificationListenerBean` là **phía subscriber**. Hai abstraction bổ sung cho nhau chứ không thay thế nhau.

## 11. MBeanInfo và notification metadata

Một MBean có thể phát notification nhưng client cần biết những loại event được công bố. Có thể kiểm tra metadata:

```java
MBeanInfo info = server.getMBeanInfo(
    new ObjectName("com.example.jobs:type=Worker,name=Primary")
);

for (var notification : info.getNotifications()) {
    System.out.println(notification.getName());

    for (String type : notification.getNotifTypes()) {
        System.out.println("  " + type);
    }
}
```

Nếu notification metadata trống, điều đó có thể phản ánh cấu hình emitter không công bố type, dù mã ứng dụng có logic phát ở nơi khác. Cần kiểm tra loại MBean, `getNotificationInfo()` hoặc metadata Spring mà exporter đang sử dụng.

Không dùng `MBeanInfo.getOperations()` để suy ra notification types: operation và notification là hai phần độc lập của MBean contract.

## 12. Gỡ listener đúng lifecycle

Khi đăng ký listener qua `MBeanExporter.notificationListeners`, exporter có thể quản lý việc gỡ registration mà nó sở hữu theo vòng đời Spring context. Đây là lợi ích quan trọng so với đăng ký thủ công mà quên cleanup.

Với đăng ký trực tiếp:

```java
server.addNotificationListener(
    name, listener, filter, handback
);
```

cần gỡ theo identity tương ứng:

```java
server.removeNotificationListener(
    name, listener, filter, handback
);
```

`removeNotificationListener` có nhiều overload; overload ba thành phần listener/filter/handback chỉ gỡ registration khớp chính xác. Nếu cùng listener được đăng ký nhiều lần với filter hoặc handback khác nhau, chọn overload phù hợp để không xóa nhầm registration khác.

Khi app redeploy mà listener cũ vẫn được giữ trong MBeanServer hoặc broadcaster, nó có thể giữ reference tới classloader của deployment trước. Vì vậy cleanup là yêu cầu vận hành, không phải tùy chọn làm đẹp code.

## 13. Test trực tiếp bằng MBeanServer

Một test dùng server riêng và Standard MBean:

```java
import static org.junit.jupiter.api.Assertions.*;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.Notification;
import javax.management.NotificationListener;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;

class JmxNotificationTest {

    @Test
    void listenerReceivesPauseNotification() throws Exception {
        MBeanServer server =
            MBeanServerFactory.createMBeanServer("listener-test");

        ObjectName name = new ObjectName(
            "com.example.jobs:type=Worker,name=Primary"
        );

        WorkerControl emitter = new WorkerControl();
        BlockingQueue<Notification> events =
            new LinkedBlockingQueue<>();

        NotificationListener listener =
            (event, handback) -> events.add(event);

        try {
            server.registerMBean(emitter, name);
            server.addNotificationListener(
                name, listener, null, "unit-test"
            );

            server.invoke(
                name, "pause", new Object[0], new String[0]
            );

            Notification received =
                events.poll(2, TimeUnit.SECONDS);

            assertNotNull(received);
            assertEquals(
                "com.example.jobs.worker.paused",
                received.getType()
            );
        } finally {
            try {
                server.removeNotificationListener(name, listener);
            } catch (Exception ignored) {
                // Có thể chưa được đăng ký hoặc MBean đã bị gỡ.
            }

            if (server.isRegistered(name)) {
                server.unregisterMBean(name);
            }

            MBeanServerFactory.releaseMBeanServer(server);
        }
    }
}
```

Test trên xác minh cơ chế notification của JMX. Nó **chưa kiểm tra Spring NotificationListenerBean wiring**, vì listener được thêm trực tiếp lên server. Một integration test Spring phải tạo context chứa exporter, listener bean và MBean, rồi kích hoạt sự kiện để chứng minh wiring thực tế đúng.

Dùng `BlockingQueue` và timeout thay vì `Thread.sleep` cố định để tránh test bị nhiễu bởi scheduling. Nếu callback xử lý bất đồng bộ, thời gian chờ cần phù hợp với hệ thống test nhưng không che lỗi cấu hình.

## 14. Integration test cấu hình NotificationListenerBean

Với Spring context, nên kiểm tra:

1. Context khởi động và MBean được đăng ký với ObjectName dự kiến.
2. `NotificationListenerBean` được exporter nhận.
3. Kích hoạt một operation tạo notification.
4. Listener nhận đúng type và handback.
5. Kích hoạt một event không qua filter; listener không nhận event đó.
6. Nếu có nhiều MBean, event từ ObjectName ngoài mapped list không được nhận.
7. Đóng context; exporter dọn registration do nó sở hữu.
8. Tạo context mới hoặc redeploy; không có callback trùng từ listener cũ.

Ví dụ kiểm tra filter bằng queue:

```java
BlockingQueue<Notification> events =
    new LinkedBlockingQueue<>();

NotificationFilter pausedOnly =
    e -> "com.example.jobs.worker.paused".equals(e.getType());

NotificationListener listener =
    (e, handback) -> events.add(e);
```

Sau khi gọi `resume`, queue không nên nhận notification loại `resumed`; sau `pause`, phải nhận loại `paused`. Tránh test chỉ assert số lượng event mà không kiểm tra type/sequence/source, vì có thể nhận event từ MBean khác.

## 15. Những lỗi phổ biến

| Triệu chứng | Khả năng cao | Cách điều tra |
| --- | --- | --- |
| MBean có nhưng listener không nhận | Mapped ObjectName sai hoặc emitter không phát | `isRegistered`, `queryNames`, log emitter |
| Startup lỗi khi gắn listener | MBean không hỗ trợ notification | Kiểm tra `NotificationBroadcaster` hoặc adapter |
| Nhận cả notification không mong đợi | Filter chưa cấu hình hoặc filter quá rộng | Kiểm tra `NotificationFilter` |
| Listener nhận trùng sau redeploy | Registration cũ chưa được gỡ | Kiểm tra exporter/context lifecycle |
| Handback là `null` | Registration không set handback | Kiểm tra `setHandback` |
| Sai nguồn khi nhiều MBean | MappedObjectNames quá rộng | Giới hạn ObjectName |
| Nhận event nhưng client remote không nhận | Remote connector/listener registration khác | Kiểm tra connection, reconnect |
| MBeanInfo không liệt kê loại event | Emitter không công bố notification metadata | `getNotificationInfo`, `getMBeanInfo` |
| Listener làm ứng dụng chậm | Callback nặng hoặc blocking | Chuyển xử lý sang executor có giới hạn |

Một notification listener không nên được dùng thay cho message broker bảo đảm giao hàng. JMX Notification không cung cấp đầy đủ các ngữ nghĩa bền vững, replay và delivery guarantee của hệ thống messaging chuyên dụng.

## 16. Những nguyên tắc bảo mật và hiệu năng

Một notification gửi qua JMX có thể được client từ xa quan sát nếu connector cho phép. Vì vậy:

- Không đưa dữ liệu nhạy cảm vào `Notification.message` và `userData`.
- Định nghĩa type có namespace rõ ràng: `com.example.jobs.worker.paused`.
- Giữ notification payload nhỏ, không serialize domain object lớn.
- Sử dụng sequence number và timestamp nhất quán.
- Filter ở nơi phù hợp; filter phía listener không thay thế authorization phía server.
- Không gọi database hoặc remote service đồng bộ trong listener nếu có thể tránh.
- Giới hạn queue khi fan-out/bất đồng bộ để tránh memory growth.
- Thiết kế idempotency nếu listener kích hoạt xử lý có side effect.
- Bảo vệ remote JMX connector bằng authentication, TLS và network isolation.

Nếu notification có tần suất rất cao, dùng metrics hoặc event streaming chuyên dụng có thể phù hợp hơn gửi mọi thay đổi nhỏ qua JMX.

## 17. So sánh listener đăng ký bằng Spring và đăng ký thủ công

| Tiêu chí | `NotificationListenerBean` qua exporter | `MBeanServer.addNotificationListener` |
| --- | --- | --- |
| Vị trí cấu hình | Spring `ApplicationContext` | Java code chủ động |
| Chọn MBean | Mapped ObjectNames | ObjectName truyền vào lời gọi |
| Filter | `setNotificationFilter` | Tham số filter |
| Handback | `setHandback` | Tham số handback |
| Lifecycle | Có thể được exporter quản lý | Caller phải dọn registration |
| Kiểm thử | Spring integration context | JMX unit/integration test |
| Mục đích | Cấu hình listener declarative | Đăng ký động theo logic runtime |

Không nhất thiết phải dùng Spring listener bean cho mọi trường hợp. Khi listener phải đăng ký/huỷ theo phiên làm việc động, API trực tiếp có thể rõ hơn. Khi một listener cố định thuộc cấu hình quản trị ứng dụng, `NotificationListenerBean` giúp gắn ownership vào context.

## 18. Quy trình triển khai

1. Xác định MBean nào phát notification và những event types dự kiến.
2. Công bố notification metadata trên emitter, kiểm tra `MBeanInfo` khi cần.
3. Đăng ký MBean bằng exporter trên một `MBeanServer` đã xác định.
4. Tạo `NotificationListener` có xử lý nhanh và an toàn.
5. Tạo `NotificationListenerBean`, set listener, filter, handback và mapped ObjectNames.
6. Gắn registration vào `MBeanExporter.notificationListeners`.
7. Khởi động context và xác minh ObjectName thực tế.
8. Kích hoạt event trong môi trường test, kiểm tra type/source/sequence/handback.
9. Đóng context, xác nhận không còn callback trùng hoặc registration tồn dư.
10. Kiểm thử reconnect/redeploy nếu có JMX remote client hoặc context nhiều vòng đời.

## 19. Ghi nhớ

**`NotificationListenerBean` là mô hình cấu hình listener JMX phía Spring; `MBeanExporter.notificationListeners` gắn các registration đó vào quá trình export MBean.** Một registration gồm listener callback, filter, handback và tập ObjectName cần quan sát. Nó không tự tạo nguồn notification, không tự thay thế security, và không bảo đảm event delivery bền vững. Muốn hệ thống đáng tin cậy, hãy dùng đúng ObjectName, test phát/nhận notification trên `MBeanServer` thật và gỡ listener đúng lifecycle của Spring context.
