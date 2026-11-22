# notificationListenerMappings của MBeanExporter trong Spring JMX

## 1. Mục tiêu học tập

Khi sử dụng Spring Framework JMX, **MBean** có thể không chỉ công bố attribute và operation mà còn phát ra **JMX Notification** khi xảy ra một sự kiện quản trị. Ví dụ: queue chuyển sang quá tải, worker bị tạm dừng, một bộ nhớ đệm được làm mới, hoặc một tác vụ nền kết thúc.

`MBeanExporter` hỗ trợ thuộc tính cấu hình **`notificationListenerMappings`** để gắn các `javax.management.NotificationListener` vào những MBean phù hợp ngay trong quá trình export.

Sau bài này, bạn sẽ hiểu:

- Cấu trúc và ý nghĩa của `notificationListenerMappings`.
- Cách khai báo `NotificationListener` và ánh xạ tới MBean được export.
- Sự khác nhau giữa **MBean phát notification**, **listener nhận notification**, **ObjectName** và **listener mapping key**.
- Cách cấu hình bằng Spring Java `@Configuration` và XML.
- Cách quản lý vòng đời đăng ký/hủy listener, xử lý filter, handback và tránh trùng listener.
- Cách kiểm thử notification bằng `MBeanServer` thật và chẩn đoán sự cố trong ứng dụng Spring.

## 2. Bức tranh tổng quan: notification không phải attribute hay operation

Trong JMX có ba kiểu tương tác quản trị phổ biến:

| Thành phần | Cách sử dụng | Ví dụ |
| --- | --- | --- |
| **Attribute** | Client chủ động đọc/ghi trạng thái | `PendingJobs`, `Paused` |
| **Operation** | Client chủ động gọi hành động | `resetStatistics()` |
| **Notification** | MBean phát thông báo khi có sự kiện | `queue.overloaded`, `worker.paused` |

Một MBean phát notification thường triển khai `NotificationEmitter` hoặc `NotificationBroadcaster`. Các class trợ giúp như `NotificationBroadcasterSupport` cho phép quản lý danh sách listener và gửi sự kiện.

Một listener triển khai:

```java
import javax.management.Notification;
import javax.management.NotificationListener;

public class LoggingNotificationListener
        implements NotificationListener {

    @Override
    public void handleNotification(
            Notification notification, Object handback) {

        System.out.println(
            "type=" + notification.getType()
            + ", source=" + notification.getSource()
            + ", message=" + notification.getMessage()
        );
    }
}
```

Để listener nhận được notification, phải **đăng ký listener với đúng MBean** đang phát sự kiện. `notificationListenerMappings` là cơ chế cấu hình việc gắn listener đó khi dùng `MBeanExporter`.

## 3. notificationListenerMappings là gì?

`MBeanExporter` có thể nhận map liên kết **khóa định danh MBean** tới **listener**.

Mô hình:

```text
MBeanExporter
  |
  +-- beans:
  |     com.example.jobs:type=Queue,name=Billing
  |        -> billingQueueMonitor
  |
  +-- notificationListenerMappings:
        com.example.jobs:type=Queue,name=Billing
           -> QueueNotificationListener

                       |
                       v
                MBeanServer
                       |
             registered MBean
                       |
                JMX Notification
                       |
                       v
              QueueNotificationListener
```

Khóa mapping có thể là `ObjectName` hoặc một bean key thích hợp theo cơ chế `MBeanExporter` đang dùng. Khi muốn cấu hình dễ đọc và tránh mơ hồ, sử dụng tên JMX đầy đủ của MBean được export.

Đừng hiểu tên thuộc tính này là danh sách các loại notification. Nó là **ánh xạ nơi listener được đăng ký**. Muốn lọc notification theo `type`, cần kết hợp `NotificationFilter`, hoặc kiểm tra `notification.getType()` trong `handleNotification`.

Cũng không nên nhầm `notificationListenerMappings` với `notificationListeners`. Spring còn có cơ chế `NotificationListenerBean` để khai báo listener và các tùy chọn như mappedObjectNames, notificationFilter, handback một cách chi tiết.

## 4. Tạo MBean có khả năng phát notification

Để hiểu hoạt động của mapping, trước tiên cần một MBean thực sự phát notification. Ví dụ MBean quản trị queue:

```java
package com.example.jobs.jmx;

public interface QueueMonitorMBean {
    int getPendingCount();
    void updatePendingCount(int value);
}
```

Implementation:

```java
package com.example.jobs.jmx;

import java.util.concurrent.atomic.AtomicLong;
import javax.management.MBeanNotificationInfo;
import javax.management.Notification;
import javax.management.NotificationBroadcasterSupport;

public final class QueueMonitor
        extends NotificationBroadcasterSupport
        implements QueueMonitorMBean {

    private static final String OVERLOADED =
            "com.example.jobs.queue.overloaded";

    private final AtomicLong sequence = new AtomicLong();
    private volatile int pendingCount;

    @Override
    public int getPendingCount() {
        return pendingCount;
    }

    @Override
    public void updatePendingCount(int value) {
        if (value < 0) {
            throw new IllegalArgumentException("value must be >= 0");
        }

        pendingCount = value;

        if (value >= 100) {
            Notification notification = new Notification(
                OVERLOADED,
                this,
                sequence.incrementAndGet(),
                System.currentTimeMillis(),
                "Queue backlog reached " + value
            );

            notification.setUserData(value);
            sendNotification(notification);
        }
    }

    @Override
    public MBeanNotificationInfo[] getNotificationInfo() {
        return new MBeanNotificationInfo[] {
            new MBeanNotificationInfo(
                new String[] { OVERLOADED },
                Notification.class.getName(),
                "Queue backlog threshold events"
            )
        };
    }
}
```

Trong ví dụ:

- `QueueMonitorMBean` là Standard MBean interface.
- `QueueMonitor` kế thừa `NotificationBroadcasterSupport`, cung cấp cơ chế phát notification và quản lý listener.
- `getNotificationInfo()` công bố metadata các notification có thể phát.
- `updatePendingCount(100)` hoặc lớn hơn sẽ gửi một notification với `type` là `com.example.jobs.queue.overloaded`.
- `sequenceNumber` tăng dần, giúp client quan sát thứ tự phát sự kiện theo emitter.

Ví dụ dùng ngưỡng đơn giản để dễ hiểu. Trong hệ thống thật, nên tránh gửi vô hạn notification cho mỗi lần cập nhật khi backlog vẫn lớn: cân nhắc chỉ gửi lúc **chuyển trạng thái** qua ngưỡng, debounce hoặc rate-limit.

## 5. Tạo NotificationListener dùng trong Spring

Listener xử lý sự kiện:

```java
package com.example.jobs.jmx;

import java.util.concurrent.atomic.AtomicInteger;
import javax.management.Notification;
import javax.management.NotificationListener;

public final class QueueNotificationListener
        implements NotificationListener {

    private final AtomicInteger overloadedEvents =
            new AtomicInteger();

    @Override
    public void handleNotification(
            Notification notification, Object handback) {

        if ("com.example.jobs.queue.overloaded".equals(
                notification.getType())) {
            overloadedEvents.incrementAndGet();

            System.out.println(
                "[JMX] " + notification.getMessage()
            );
        }
    }

    public int getOverloadedEvents() {
        return overloadedEvents.get();
    }
}
```

Listener trong ví dụ lưu counter nhằm phục vụ kiểm thử. Trong production, listener có thể chuyển tín hiệu sang logging/metrics/event bus hoặc hệ thống điều phối sự cố.

**Lưu ý về xử lý:** callback notification có thể chạy trên thread do emitter/dispatcher quản lý. Không thực hiện I/O chậm, xử lý kéo dài hoặc gọi operation phản hồi tạo vòng lặp không kiểm soát ngay trong callback nếu chưa thiết kế concurrency phù hợp.

## 6. Cấu hình notificationListenerMappings bằng Java

Một ví dụ cấu hình tập trung với Spring:

```java
package com.example.jobs.config;

import com.example.jobs.jmx.QueueMonitor;
import com.example.jobs.jmx.QueueNotificationListener;
import java.lang.management.ManagementFactory;
import java.util.Map;
import javax.management.MBeanServer;
import javax.management.NotificationListener;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class QueueJmxConfiguration {

    private static final String QUEUE_NAME =
        "com.example.jobs:type=Queue,name=Billing";

    @Bean
    public QueueMonitor billingQueueMonitor() {
        return new QueueMonitor();
    }

    @Bean
    public QueueNotificationListener queueNotificationListener() {
        return new QueueNotificationListener();
    }

    @Bean
    public MBeanServer queueMBeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public MBeanExporter queueMBeanExporter(
            QueueMonitor billingQueueMonitor,
            QueueNotificationListener queueNotificationListener,
            MBeanServer queueMBeanServer) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(queueMBeanServer);

        exporter.setBeans(Map.of(
            QUEUE_NAME,
            billingQueueMonitor
        ));

        Map<String, NotificationListener> mappings = Map.of(
            QUEUE_NAME,
            queueNotificationListener
        );

        exporter.setNotificationListenerMappings(mappings);
        return exporter;
    }
}
```

Ý nghĩa từng phần:

1. `setBeans` đăng ký đối tượng quản trị dưới `ObjectName` đã chọn.
2. `setNotificationListenerMappings` hướng dẫn exporter gắn listener với MBean được chỉ định.
3. `setServer` đảm bảo exporter đăng ký/đính listener trong cùng `MBeanServer` dự kiến.
4. Client hoặc code nghiệp vụ khiến `QueueMonitor` phát notification.
5. `QueueNotificationListener.handleNotification` nhận callback theo cơ chế JMX.

Trên các phiên bản Spring, chữ ký API cho mapping có thể chấp nhận kiểu map đối tượng rộng hơn; ví dụ dùng `Map<String, NotificationListener>` theo kiểu tương thích với `setNotificationListenerMappings` cho trình bày. Khi áp dụng, hãy để IDE xác định đúng kiểu generic theo Spring Framework version của dự án.

Cần lưu ý: `notificationListenerMappings` không tự tạo notification và không khiến class bình thường trở thành broadcaster. Target phải hỗ trợ phát notification.

## 7. Cấu hình XML

Với một ứng dụng Spring Framework khai báo bean trong XML:

```xml
<bean id="queueMonitor"
      class="com.example.jobs.jmx.QueueMonitor"/>

<bean id="queueNotificationListener"
      class="com.example.jobs.jmx.QueueNotificationListener"/>

<bean id="jmxExporter"
      class="org.springframework.jmx.export.MBeanExporter">

    <property name="beans">
        <map>
            <entry
                key="com.example.jobs:type=Queue,name=Billing"
                value-ref="queueMonitor"/>
        </map>
    </property>

    <property name="notificationListenerMappings">
        <map>
            <entry
                key="com.example.jobs:type=Queue,name=Billing"
                value-ref="queueNotificationListener"/>
        </map>
    </property>
</bean>
```

`value-ref` trong map listener trỏ tới bean triển khai `NotificationListener`, không phải chính MBean phát notification.

Nếu dùng nhiều listener cho một MBean hoặc cần filter/handback, cấu hình nâng cao bằng `NotificationListenerBean` thường rõ ràng hơn, thay vì cố nhồi nhiều listener vào một key của map.

## 8. Phân biệt map listener với NotificationListenerBean

Spring hỗ trợ `org.springframework.jmx.export.NotificationListenerBean`, cho phép mô tả registration với nhiều thuộc tính hơn:

- `notificationListener`: object triển khai `NotificationListener`.
- `mappedObjectNames`: MBean nhận listener, theo tên/định danh phù hợp.
- `notificationFilter`: chỉ nhận notification thỏa điều kiện.
- `handback`: object được chuyển kèm khi callback.

Ví dụ Java:

```java
import javax.management.NotificationFilterSupport;
import org.springframework.jmx.export.NotificationListenerBean;

NotificationFilterSupport filter =
        new NotificationFilterSupport();

filter.enableType("com.example.jobs.queue.overloaded");

NotificationListenerBean listenerBean =
        new NotificationListenerBean(queueNotificationListener);

listenerBean.setMappedObjectNames(
    "com.example.jobs:type=Queue,name=Billing"
);

listenerBean.setNotificationFilter(filter);
listenerBean.setHandback("billing-queue");

exporter.setNotificationListeners(listenerBean);
```

Ở đây, `NotificationListenerBean` hỗ trợ một cấu hình đầy đủ, trong khi `notificationListenerMappings` là dạng đơn giản hóa để map listener theo key.

**Chọn cách nào?**

- Một listener cho một MBean, không cần filter/handback: mapping đơn giản dễ dùng.
- Cần một listener nghe nhiều MBean hoặc cấu hình filter: `NotificationListenerBean` phù hợp hơn.
- Cần nhiều listener trên cùng MBean với cấu hình riêng: sử dụng nhiều `NotificationListenerBean`.

Không bật cả hai cấu hình cho cùng listener/MBean một cách vô tình, vì có thể làm callback được nhận nhiều lần.

## 9. Khóa mapping: ObjectName, bean key và phạm vi

Trong một số cách cấu hình, key dùng để map listener có thể là tên JMX đầy đủ hoặc bean key được exporter dùng để đăng ký MBean. Điều này phụ thuộc cách exporter xử lý các entry và naming strategy.

Ví dụ rõ ràng:

```text
com.example.jobs:type=Queue,name=Billing
```

Nếu sử dụng một key nội bộ:

```text
billingQueueMonitor
```

thì cần đảm bảo exporter ánh xạ key đó tới đúng `ObjectName`, và mapping listener sử dụng đúng quy tắc do Spring hỗ trợ ở phiên bản đang chạy.

**Không mặc định rằng tên Spring bean và ObjectName trùng nhau.** Nếu exporter có naming strategy biến `billingQueueMonitor` thành một ObjectName khác, test cần xác nhận listener thực sự được đăng ký tới MBean mong đợi.

Mỗi MBean trên cùng server có ObjectName duy nhất. Một key mapping sai có thể dẫn tới listener không nhận notification hoặc lỗi đăng ký khi exporter khởi tạo.

## 10. Vòng đời registration và cleanup

`MBeanExporter` gắn listener khi export và quản lý việc hủy các listener registration do nó thiết lập trong quá trình đóng exporter/context phù hợp.

Luồng:

```text
Spring ApplicationContext startup
  |
  +-- Tạo QueueMonitor
  +-- Tạo QueueNotificationListener
  +-- Tạo MBeanExporter
       |
       +-- Đăng ký QueueMonitor vào MBeanServer
       +-- Đăng ký listener với ObjectName đã map
       |
       v
JMX notification flow hoạt động

Spring ApplicationContext shutdown
  |
  +-- Hủy registration listener thuộc exporter
  +-- Hủy đăng ký MBean do exporter sở hữu
```

Việc cleanup đặc biệt quan trọng nếu Spring context được refresh/redeploy trong cùng JVM. Listener cũ còn tồn tại có thể:

- Nhận cùng event nhiều lần.
- Giữ tham chiếu tới bean/classloader đã hết vòng đời.
- Ghi log hoặc metric sai sau redeploy.
- Gây memory leak.
- Tạo lỗi khi callback truy cập service đã bị đóng.

Không tự động `unregisterMBean` một ObjectName không thuộc sở hữu của context chỉ để “dọn cho sạch”. Cần hiểu ownership của exporter và MBeanServer.

## 11. Kiểm thử notification trực tiếp bằng MBeanServer

Trước khi đưa Spring vào, có thể kiểm chứng JMX notification thuần Java:

```java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.atomic.AtomicInteger;
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.NotificationListener;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;

class JmxNotificationTest {

    @Test
    void listenerReceivesQueueNotification() throws Exception {
        MBeanServer server =
            MBeanServerFactory.createMBeanServer("test.management");

        ObjectName name = new ObjectName(
            "com.example.jobs:type=Queue,name=Billing"
        );

        QueueMonitor monitor = new QueueMonitor();
        AtomicInteger received = new AtomicInteger();

        NotificationListener listener = (notification, handback) -> {
            if ("com.example.jobs.queue.overloaded".equals(
                    notification.getType())) {
                received.incrementAndGet();
            }
        };

        try {
            server.registerMBean(monitor, name);
            server.addNotificationListener(
                name, listener, null, null
            );

            // Gây sự kiện đúng bằng operation quản trị.
            server.invoke(
                name,
                "updatePendingCount",
                new Object[] { 120 },
                new String[] { "int" }
            );

            assertEquals(1, received.get());
        } finally {
            if (server.isRegistered(name)) {
                try {
                    server.removeNotificationListener(name, listener);
                } catch (javax.management.ListenerNotFoundException ignored) {
                    // Listener chưa được đăng ký thành công.
                }
                server.unregisterMBean(name);
            }
            MBeanServerFactory.releaseMBeanServer(server);
        }
    }
}
```

Ví dụ sử dụng một `NotificationBroadcasterSupport` có dispatch đồng bộ mặc định để minh họa. Nếu broadcaster dùng executor bất đồng bộ, test cần cơ chế chờ có giới hạn (ví dụ latch) thay vì giả định callback đã chạy ngay sau invocation.

Điều test xác minh:

- MBean đã đăng ký.
- Listener được gắn vào đúng ObjectName.
- Operation khiến emitter phát notification.
- Callback được nhận với `type` mong đợi.
- Registration được dọn trong `finally`.

## 12. Kiểm thử thông qua Spring MBeanExporter

Một integration test cho Spring nên khởi tạo ApplicationContext chứa:

- `QueueMonitor`.
- `QueueNotificationListener`.
- `MBeanServer` riêng cho test.
- `MBeanExporter` cấu hình `beans` và `notificationListenerMappings`.

Khi context đã refresh, dùng server test để invoke operation rồi xác minh listener counter.

Ví dụ cấu hình test:

```java
import java.util.Map;
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class NotificationJmxTestConfig {

    @Bean
    public MBeanServer testMBeanServer() {
        return MBeanServerFactory.newMBeanServer("test.management");
    }

    @Bean
    public QueueMonitor queueMonitor() {
        return new QueueMonitor();
    }

    @Bean
    public QueueNotificationListener queueNotificationListener() {
        return new QueueNotificationListener();
    }

    @Bean
    public MBeanExporter mbeanExporter(
            MBeanServer testMBeanServer,
            QueueMonitor queueMonitor,
            QueueNotificationListener queueNotificationListener) {

        String name =
            "com.example.jobs:type=Queue,name=Billing";

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(testMBeanServer);
        exporter.setBeans(Map.of(name, queueMonitor));
        exporter.setNotificationListenerMappings(
            Map.of(name, queueNotificationListener)
        );
        return exporter;
    }
}
```

Integration test:

```java
import static org.junit.jupiter.api.Assertions.*;

import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

class SpringNotificationMappingTest {

    @Test
    void receivesNotificationsFromMappedMBean() throws Exception {
        try (var context =
                 new AnnotationConfigApplicationContext(
                     NotificationJmxTestConfig.class)) {

            MBeanServer server = context.getBean(MBeanServer.class);
            QueueNotificationListener listener =
                context.getBean(QueueNotificationListener.class);

            ObjectName name = new ObjectName(
                "com.example.jobs:type=Queue,name=Billing"
            );

            assertTrue(server.isRegistered(name));

            server.invoke(
                name,
                "updatePendingCount",
                new Object[] { 120 },
                new String[] { "int" }
            );

            assertEquals(1, listener.getOverloadedEvents());
        }
    }
}
```

Với server test `newMBeanServer`, không cần release qua `MBeanServerFactory.releaseMBeanServer`. Đóng `ApplicationContext` để Spring cleanup exporter và listeners.

Nếu test có hai exporters hoặc listener cùng được cấu hình trong `notificationListeners` và `notificationListenerMappings`, callback có thể bị gọi hai lần. Hãy xác minh cấu hình chỉ gắn listener một lần.

## 13. Lọc notification theo type

Một MBean có thể phát nhiều notification types:

```text
com.example.jobs.queue.overloaded
com.example.jobs.queue.recovered
com.example.jobs.queue.paused
```

Nếu listener chỉ quan tâm quá tải:

```java
import javax.management.NotificationFilterSupport;

NotificationFilterSupport filter = new NotificationFilterSupport();
filter.enableType("com.example.jobs.queue.overloaded");
```

Sau đó dùng `NotificationListenerBean.setNotificationFilter(filter)` hoặc `MBeanServer.addNotificationListener(name, listener, filter, handback)` khi đăng ký trực tiếp.

Không nên giả định mapping key chứa tên notification type. Mapping key thường xác định **MBean phát notification**; filter mới xác định **notification nào được nhận**.

Khi nhiều type quan trọng, có thể có nhiều listener/handlers chuyên trách hoặc một listener phân nhánh theo `notification.getType()`. Cần tránh callback xử lý quá nặng.

## 14. Handback là gì?

JMX cho phép truyền một object `handback` khi đăng ký listener:

```java
server.addNotificationListener(
    objectName,
    listener,
    filter,
    "billing-queue"
);
```

Khi callback chạy:

```java
@Override
public void handleNotification(
        Notification notification, Object handback) {

    System.out.println("Source label: " + handback);
}
```

`handback` là context do **bên đăng ký listener** cung cấp. Nó khác `notification.getSource()` (nguồn sự kiện) và `notification.getUserData()` (dữ liệu kèm sự kiện).

Nếu cần cấu hình handback qua Spring, `NotificationListenerBean` thuận tiện hơn mapping đơn giản. Không đưa password, token hoặc dữ liệu nhạy cảm vào handback một cách tùy tiện.

## 15. Phân biệt notification nội bộ và remote JMX

`notificationListenerMappings` được sử dụng khi **Spring exporter đăng ký listener trên MBeanServer mà nó quản lý**.

Nó không tự thiết lập remote JMX client, không mở socket và không chuyển listener Java trực tiếp sang một JVM khác bằng cách map bean nội bộ.

Nếu client ở JVM khác muốn nhận notification:

1. Client kết nối tới remote `MBeanServerConnection` qua `JMXConnector`.
2. Client gọi `addNotificationListener` trên connection từ xa cho ObjectName của MBean.
3. JMX connector vận chuyển notification về client theo giao thức và quyền được cấu hình.
4. Client quản lý reconnect, listener cleanup và các lỗi mạng.

Đừng nhầm local exporter listener với remote monitoring subscription. Cùng ObjectName có thể tồn tại trên nhiều JVM, nên phải gắn listener vào đúng connection/server.

## 16. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| MBean xuất hiện nhưng listener không nhận event | Bean không phát notification; mapping key không khớp; listener không đăng ký | Kiểm tra broadcaster, `sendNotification`, ObjectName và config |
| Lỗi khi exporter đăng ký listener | MBean không hỗ trợ notification hoặc key sai | Xác minh `NotificationBroadcaster`/`NotificationEmitter`, metadata và server |
| Listener nhận event hai lần | Đăng ký trùng qua mappings, listener beans hoặc custom code | Chọn một cơ chế registration/owner |
| Listener nhận quá nhiều event | Không có filter hoặc broadcaster gửi mỗi lần poll | Dùng `NotificationFilter`, điều chỉnh phát sự kiện |
| `ListenerNotFoundException` khi cleanup | Listener đã được gỡ hoặc tuple listener/filter/handback không phù hợp | Quản lý registration theo cùng owner và lifecycle |
| Không nhận event sau redeploy | Listener cũ/bean cũ còn tham chiếu, exporter mới chưa đăng ký | Kiểm tra teardown và startup logs |
| Event đến nhưng làm chậm hệ thống | Callback thực hiện I/O chậm, logic nặng | Đẩy xử lý qua queue/executor phù hợp |
| Remote client không nhận event | Đang nối sai server hoặc connector bị lỗi | Kiểm tra endpoint, ObjectName và connection lifecycle |
| Notification type không thấy trong MBeanInfo | Broadcaster không công bố metadata đúng | Kiểm tra `getNotificationInfo()` |
| Method gọi thành công nhưng không phát event | Đường code không gọi `sendNotification` | Kiểm tra điều kiện trigger và implementation |

Nếu `MBeanInfo.getNotifications()` không chứa type mong đợi, đó là dấu hiệu cần kiểm tra emitter metadata. Tuy nhiên, metadata chỉ là mô tả, không đảm bảo logic thực tế sẽ phát sự kiện trong mọi lần gọi.

## 17. Checklist triển khai an toàn

- Xác định MBean nào thực sự phát notification.
- Giữ ObjectName ổn định, có domain/type/name rõ ràng.
- Chỉ gắn listener vào những MBean cần nghe.
- Cấu hình filter khi chỉ quan tâm một số notification types.
- Không tạo registration trùng giữa `notificationListenerMappings` và `notificationListeners`.
- Giữ callback nhanh và không gây vòng lặp notification.
- Dùng sequence number phù hợp và mô tả event types ổn định.
- Không đặt bí mật hoặc dữ liệu cá nhân vào message/userData.
- Xác minh cleanup khi Spring context đóng.
- Kiểm tra bằng `MBeanServer` thật trong integration test.
- Nếu nghe notification từ xa, kiểm tra connector/TLS/authentication và reconnect riêng.
- Không coi listener như cơ chế đảm bảo giao hàng bền vững; nếu cần exactly-once/durable delivery, dùng message broker hoặc event system phù hợp hơn.

## 18. Bài tập thực hành

1. Tạo Standard MBean `QueueMonitor` kế thừa `NotificationBroadcasterSupport`, phát type `queue.overloaded` khi `PendingCount >= 100`.
2. Tạo `QueueNotificationListener` tăng counter khi nhận type đó.
3. Cấu hình Spring `MBeanExporter.setNotificationListenerMappings` để nghe MBean `com.example.jobs:type=Queue,name=Billing`.
4. Gọi `updatePendingCount(120)` qua `MBeanServer.invoke` và xác minh listener nhận event.
5. Thay mapping đơn giản bằng `NotificationListenerBean` có `NotificationFilterSupport`, chỉ nhận `queue.overloaded`.
6. Cấu hình hai notification types và so sánh kết quả có/không có filter.
7. Cố tình đăng ký cùng listener hai lần và quan sát số callback; sửa bằng một owner duy nhất.
8. Viết integration test đóng `ApplicationContext`, đảm bảo không còn callback từ registration đã dọn.
9. Thử cấu hình listener trên một MBean không phát notification để xem Spring/JMX phản hồi và xử lý lỗi.

## 19. Câu hỏi tự kiểm tra

- `notificationListenerMappings` dùng để chọn MBean phát event hay để chọn notification type?
- `NotificationListener` khác `NotificationBroadcaster` như thế nào?
- Vì sao `MBeanExporter` không thể tự phát notification cho bean không hỗ trợ broadcaster?
- Khi nào nên dùng `NotificationListenerBean` thay cho map đơn giản?
- `NotificationFilter` và `handback` phục vụ mục đích gì?
- Vì sao một listener có thể nhận cùng event hai lần?
- Dùng cùng ObjectName trên JVM khác có làm listener local nhận notification từ xa không?
- Cleanup listener quan trọng thế nào trong ứng dụng redeploy nhiều lần?

**Ghi nhớ:** `notificationListenerMappings` là cấu hình của `MBeanExporter` dùng để **gắn listener vào MBean** khi Spring đăng ký JMX resources. MBean phải thực sự hỗ trợ phát notification; mapping không tự tạo sự kiện. Với các yêu cầu filter, handback và nhiều listener, cân nhắc `NotificationListenerBean`. Luôn kiểm tra ObjectName, server, lifecycle và hành vi callback qua `MBeanServer` thật.