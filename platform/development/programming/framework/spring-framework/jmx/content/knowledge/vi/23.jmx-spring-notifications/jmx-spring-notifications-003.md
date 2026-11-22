# Đăng ký listener cho nhiều MBean trong Spring Framework JMX

## 1. Bối cảnh và mục tiêu

JMX (Java Management Extensions) không chỉ cho phép đọc **attribute** và gọi **operation** trên MBean, mà còn hỗ trợ mô hình **notification**: một MBean có thể phát sự kiện để các client hoặc thành phần khác biết trạng thái vừa thay đổi.

Trong Spring Framework JMX, một ứng dụng thường có nhiều MBean phát thông báo:

- MBean quản lý cache phát notification khi dữ liệu được làm mới.
- MBean quản lý worker phát notification khi worker được pause/resume.
- MBean quản lý hàng đợi phát notification khi số job chờ vượt ngưỡng.
- MBean quan sát kết nối phát notification khi một downstream service bị mất kết nối hoặc khôi phục.

Nếu mỗi sự kiện phải được xử lý theo một quy tắc thống nhất, ta cần **đăng ký listener cho nhiều MBean**. Spring hỗ trợ cấu hình listener qua `MBeanExporter` và các thành phần liên quan, bên cạnh API notification tiêu chuẩn của JMX.

Sau bài học, bạn có thể:

1. Hiểu `NotificationEmitter`, `NotificationListener`, `NotificationFilter` và `ObjectName`.
2. Phân biệt listener đăng ký trực tiếp trên MBeanServer và listener do Spring exporter quản lý.
3. Cấu hình một listener nhận sự kiện từ nhiều MBean một cách có kiểm soát.
4. Giới hạn notification bằng filter và xử lý dữ liệu sự kiện an toàn.
5. Xử lý việc đăng ký, hủy đăng ký và thay thế MBean trong lifecycle ứng dụng.
6. Kiểm thử nhiều nguồn phát mà không làm lẫn metadata, listener hoặc operation.

## 2. Các khái niệm cốt lõi của JMX notification

JMX sử dụng những thành phần chính:

| Thành phần | Vai trò |
| --- | --- |
| `Notification` | Đối tượng biểu diễn sự kiện: type, source, sequence number, timestamp, message, userData. |
| `NotificationBroadcaster` | Interface biểu thị một MBean có thể phát notification. |
| `NotificationEmitter` | Mở rộng broadcaster, hỗ trợ quản lý listener/filter/handback. |
| `NotificationListener` | Thành phần nhận thông báo qua `handleNotification`. |
| `NotificationFilter` | Quyết định notification nào được chuyển tới listener. |
| `ObjectName` | Định danh MBean đã đăng ký trong MBeanServer. |
| `MBeanServer` | Cho phép `addNotificationListener`/`removeNotificationListener` với MBean đã đăng ký. |

Luồng đơn giản:

~~~text
MBean A --notification--+
                        |
MBean B --notification--+--> NotificationListener
                        |
MBean C --notification--+
~~~

Trong JMX, một listener có thể được đăng ký trên nhiều MBean. Mỗi registration vẫn là một quan hệ riêng giữa listener và emitter; không có khái niệm “một subscription tự động bao phủ mọi MBean” nếu chưa thực hiện đầy đủ việc đăng ký.

### Notification không phải message queue bền vững

Notification thường mang tính runtime. Nếu listener chưa đăng ký, ứng dụng mất kết nối hoặc MBean bị thay, client có thể không nhận được những notification đã phát. JMX không mặc nhiên hỗ trợ lưu bền, replay hay exactly-once delivery.

Nếu yêu cầu không được mất sự kiện, hãy dùng hệ thống event/message phù hợp ở tầng ứng dụng thay vì coi JMX notification là cơ chế tích hợp nghiệp vụ đáng tin cậy.

## 3. Ví dụ hai MBean phát notification

Ta xây hai emitter độc lập để minh họa: `CacheMonitor` và `QueueMonitor`. Chúng dùng `NotificationBroadcasterSupport`, một lớp JMX tiêu chuẩn giúp quản lý listener và phát notification.

### 3.1. Interface quản trị

~~~java
package com.example.management;

public interface CacheMonitorMBean {
    long getRefreshCount();
    void refresh();
}
~~~

~~~java
package com.example.management;

public interface QueueMonitorMBean {
    int getPendingCount();
    void signalThreshold();
}
~~~

### 3.2. CacheMonitor phát sự kiện

~~~java
package com.example.management;

import java.util.concurrent.atomic.AtomicLong;
import javax.management.Notification;
import javax.management.NotificationBroadcasterSupport;

public class CacheMonitor extends NotificationBroadcasterSupport
        implements CacheMonitorMBean {

    private final AtomicLong sequence = new AtomicLong();
    private final AtomicLong refreshCount = new AtomicLong();

    @Override
    public long getRefreshCount() {
        return refreshCount.get();
    }

    @Override
    public void refresh() {
        long count = refreshCount.incrementAndGet();

        Notification notification = new Notification(
            "com.example.cache.refreshed",
            this,
            sequence.incrementAndGet(),
            System.currentTimeMillis(),
            "Cache refreshed, count=" + count
        );

        sendNotification(notification);
    }
}
~~~

### 3.3. QueueMonitor phát sự kiện

~~~java
package com.example.management;

import java.util.concurrent.atomic.AtomicLong;
import javax.management.Notification;
import javax.management.NotificationBroadcasterSupport;

public class QueueMonitor extends NotificationBroadcasterSupport
        implements QueueMonitorMBean {

    private final AtomicLong sequence = new AtomicLong();
    private volatile int pendingCount = 10;

    @Override
    public int getPendingCount() {
        return pendingCount;
    }

    @Override
    public void signalThreshold() {
        Notification notification = new Notification(
            "com.example.queue.threshold",
            this,
            sequence.incrementAndGet(),
            System.currentTimeMillis(),
            "Pending queue size=" + pendingCount
        );

        sendNotification(notification);
    }
}
~~~

Mỗi MBean có sequence counter riêng. **Sequence number không phải mã định danh toàn cục** giữa nhiều emitter. Khi tổng hợp notification từ nhiều MBean, không nên giả định sequence của chúng tăng liên tục trên toàn hệ thống.

Hai ví dụ sử dụng một thao tác đồng bộ để chủ động phát notification. Trong hệ thống thật, notification có thể được phát từ logic quản lý cache hoặc queue khi điều kiện xảy ra.

## 4. Đăng ký MBean trong MBeanServer

~~~java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

ObjectName cacheName = new ObjectName(
    "com.example:type=CacheMonitor,name=products"
);
ObjectName queueName = new ObjectName(
    "com.example:type=QueueMonitor,name=payments"
);

server.registerMBean(new CacheMonitor(), cacheName);
server.registerMBean(new QueueMonitor(), queueName);
~~~

MBeanServer yêu cầu các ObjectName là duy nhất trong một server. Với hai nguồn phát khác nhau, dùng hai ObjectName khác nhau và nhất quán để listener có thể theo dõi đúng tài nguyên.

Đoạn code minh họa chạy trong cùng JVM. Nếu tạo một JVM độc lập để thực thi đoạn này, nó không tự đăng ký MBean vào JVM của một ứng dụng Spring khác.

## 5. Cách đăng ký một listener cho nhiều MBean bằng JMX API

Đầu tiên tạo listener:

~~~java
import javax.management.Notification;
import javax.management.NotificationListener;

NotificationListener listener = (Notification notification,
                                 Object handback) -> {
    System.out.println(
        "type=" + notification.getType()
        + ", source=" + notification.getSource()
        + ", sequence=" + notification.getSequenceNumber()
        + ", message=" + notification.getMessage()
        + ", handback=" + handback
    );
};
~~~

Sau đó gọi `addNotificationListener` riêng cho từng ObjectName:

~~~java
server.addNotificationListener(
    cacheName,
    listener,
    null,
    "cache"
);

server.addNotificationListener(
    queueName,
    listener,
    null,
    "queue"
);
~~~

Cùng một listener được dùng lại, nhưng có **hai registration độc lập**. Tham số `handback` là context do caller cung cấp khi đăng ký; trong ví dụ này nó giúp phân biệt nguồn.

Khi MBean phát sự kiện, listener được gọi với notification và handback tương ứng. Có thể dùng handback là một object chứa ObjectName, logical resource ID hoặc metadata của subscription.

### Hủy đăng ký chính xác

Khi không còn cần nhận thông báo:

~~~java
server.removeNotificationListener(
    cacheName,
    listener
);

server.removeNotificationListener(
    queueName,
    listener
);
~~~

Một ứng dụng phải quản lý lifecycle của mọi registration đã tạo. Nếu bỏ quên hủy listener, có thể tạo memory leak hoặc tiếp tục xử lý sự kiện không còn phù hợp.

**Lưu ý:** API JMX có overload `removeNotificationListener` với filter và handback. Khi đã tạo nhiều registration cho cùng listener trên một emitter, việc dùng overload phù hợp rất quan trọng để tránh xóa nhầm subscription hoặc không tìm thấy registration tương ứng.

## 6. Dùng NotificationFilter để chỉ nhận sự kiện cần thiết

Khi một listener dùng chung cho nhiều MBean, filter giúp tránh xử lý mọi event không liên quan.

Ví dụ:

~~~java
import javax.management.Notification;
import javax.management.NotificationFilter;

NotificationFilter filter = new NotificationFilter() {
    private static final long serialVersionUID = 1L;

    @Override
    public boolean isNotificationEnabled(Notification notification) {
        String type = notification.getType();

        return "com.example.cache.refreshed".equals(type)
            || "com.example.queue.threshold".equals(type);
    }
};
~~~

Đăng ký:

~~~java
server.addNotificationListener(
    cacheName,
    listener,
    filter,
    cacheName
);

server.addNotificationListener(
    queueName,
    listener,
    filter,
    queueName
);
~~~

Một listener có thể được đăng ký với **filter khác nhau cho từng emitter**. Nếu cache phát nhiều loại notification nhưng subscriber chỉ cần `cache.refreshed`, hãy dùng filter riêng.

### Filter theo loại notification

Một cách khác là `NotificationFilterSupport`:

~~~java
import javax.management.NotificationFilterSupport;

NotificationFilterSupport cacheFilter =
    new NotificationFilterSupport();
cacheFilter.enableType("com.example.cache.refreshed");

NotificationFilterSupport queueFilter =
    new NotificationFilterSupport();
queueFilter.enableType("com.example.queue.threshold");
~~~

Rồi dùng:

~~~java
server.addNotificationListener(
    cacheName, listener, cacheFilter, cacheName
);

server.addNotificationListener(
    queueName, listener, queueFilter, queueName
);
~~~

**Cảnh báo:** `NotificationFilterSupport.enableType` dựa trên quy tắc khớp prefix của notification type. Nếu cần khớp chính xác một loại, hãy viết filter với `equals` như ví dụ trước.

## 7. Cơ chế listener trong Spring MBeanExporter

Spring Framework JMX cung cấp cách cấu hình listener tại exporter thông qua `NotificationListenerBean`.

Lợi ích:

- Listener được Spring quản lý như một bean.
- Có thể khai báo listener dùng chung.
- Có thể chọn những MBean do exporter quản lý cần nhận sự kiện.
- Registration/unregistration có thể được gắn với lifecycle của exporter.
- Không cần tự viết toàn bộ code `addNotificationListener` cho các MBean thuộc phạm vi exporter.

Khái niệm cấu hình:

~~~text
MBeanExporter
    |
    +-- Beans to export:
    |     CacheMonitor
    |     QueueMonitor
    |
    +-- NotificationListeners:
          SharedEventListener
                |
                +-- CacheMonitor ObjectName
                +-- QueueMonitor ObjectName
~~~

**Quan trọng:** cơ chế `NotificationListenerBean` trong exporter áp dụng cho những MBean mà exporter quản lý theo cấu hình của nó. Không nên giả định khai báo một listener trong exporter sẽ tự động đăng ký với mọi MBean có sẵn trong platform MBeanServer, kể cả JVM MBeans và MBeans do exporter khác quản lý.

## 8. Tạo listener Spring có thể nhận nhiều nguồn

Một listener đơn giản:

~~~java
package com.example.management;

import javax.management.Notification;
import javax.management.NotificationListener;

public class SharedManagementListener
        implements NotificationListener {

    @Override
    public void handleNotification(
            Notification notification,
            Object handback
    ) {
        System.out.printf(
            "type=%s, source=%s, message=%s%n",
            notification.getType(),
            notification.getSource(),
            notification.getMessage()
        );
    }
}
~~~

Trong production, tránh log trực tiếp toàn bộ `notification.getUserData()` nếu dữ liệu có thể chứa secret hoặc thông tin nhạy cảm. Listener cũng nên xử lý nhanh, tránh blocking network/database kéo dài trong callback.

## 9. Cấu hình NotificationListenerBean cho nhiều MBean

Một ví dụ Java configuration:

~~~java
package com.example.management;

import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.NotificationListenerBean;

@Configuration
public class MultiMBeanNotificationConfiguration {

    @Bean
    CacheMonitor cacheMonitor() {
        return new CacheMonitor();
    }

    @Bean
    QueueMonitor queueMonitor() {
        return new QueueMonitor();
    }

    @Bean
    SharedManagementListener sharedManagementListener() {
        return new SharedManagementListener();
    }

    @Bean
    NotificationListenerBean notificationListenerBean(
            SharedManagementListener listener
    ) {
        NotificationListenerBean bean =
            new NotificationListenerBean(listener);

        bean.setMappedObjectNames(
            "com.example:type=CacheMonitor,name=products",
            "com.example:type=QueueMonitor,name=payments"
        );
        return bean;
    }

    @Bean
    MBeanExporter managementExporter(
            CacheMonitor cacheMonitor,
            QueueMonitor queueMonitor,
            NotificationListenerBean listenerBean
    ) {
        MBeanExporter exporter = new MBeanExporter();

        exporter.setBeans(Map.of(
            "com.example:type=CacheMonitor,name=products",
            cacheMonitor,
            "com.example:type=QueueMonitor,name=payments",
            queueMonitor
        ));

        exporter.setNotificationListeners(listenerBean);

        return exporter;
    }
}
~~~

Trong cấu hình này:

1. Spring tạo hai bean MBean source.
2. Exporter đăng ký hai nguồn phát với ObjectName riêng.
3. `NotificationListenerBean` nhận listener implementation.
4. `setMappedObjectNames` giới hạn nguồn nhận notification.
5. `setNotificationListeners` cung cấp cấu hình listener cho exporter.
6. Cùng một listener có thể nhận sự kiện từ cả cache và queue.

**Lưu ý quan trọng về phiên bản API:** tên overload, kiểu của `mappedObjectNames` và cách khai báo `NotificationListenerBean` có thể khác theo Spring version; khi copy cần đối chiếu Javadoc của phiên bản đang dùng. Nếu `setMappedObjectNames` yêu cầu `ObjectName` thay vì String trong version của bạn, hãy tạo bằng `new ObjectName(...)` hoặc dùng biến thể setter đúng kiểu.

Khi một MBean đã được Spring Boot/JMX exporter khác quản lý, không nên cấu hình thêm exporter chỉ để nhận notification nếu điều đó tạo đăng ký trùng tên. Trong trường hợp ấy, xem xét đăng ký trực tiếp trên `MBeanServer` hoặc điều chỉnh ownership.

## 10. Ví dụ XML configuration

Trong các ứng dụng Spring XML, có thể khai báo listener và mapping tương tự:

~~~xml
<bean id="sharedManagementListener"
      class="com.example.management.SharedManagementListener"/>

<bean id="notificationListener"
      class="org.springframework.jmx.export.NotificationListenerBean">
    <constructor-arg ref="sharedManagementListener"/>
    <property name="mappedObjectNames">
        <list>
            <value>com.example:type=CacheMonitor,name=products</value>
            <value>com.example:type=QueueMonitor,name=payments</value>
        </list>
    </property>
</bean>

<bean id="mbeanExporter"
      class="org.springframework.jmx.export.MBeanExporter">
    <property name="beans">
        <map>
            <entry key="com.example:type=CacheMonitor,name=products"
                   value-ref="cacheMonitor"/>
            <entry key="com.example:type=QueueMonitor,name=payments"
                   value-ref="queueMonitor"/>
        </map>
    </property>
    <property name="notificationListeners">
        <list>
            <ref bean="notificationListener"/>
        </list>
    </property>
</bean>
~~~

Các bean `cacheMonitor` và `queueMonitor` phải được định nghĩa ở nơi khác trong context. Cấu hình minh họa quan hệ giữa nguồn phát, listener và exporter; cần kiểm tra schema cùng Spring version thực tế trước khi sử dụng.

## 11. Mapped ObjectNames: đăng ký đúng nguồn

Một lỗi dễ gặp là listener được cấu hình nhưng mapping ObjectName không khớp MBean đã export.

Ví dụ:

~~~text
Exported:
  com.example:type=CacheMonitor,name=products

Configured listener:
  com.example:type=CacheMonitor,name=product
~~~

Chỉ khác một ký tự `products`/`product` nhưng đó là hai ObjectName khác nhau. Listener có thể không được gắn vào nguồn dự kiến.

Cách xác minh:

~~~java
ObjectName name = new ObjectName(
    "com.example:type=CacheMonitor,name=products"
);

if (!server.isRegistered(name)) {
    throw new IllegalStateException(
        "Expected MBean is not registered"
    );
}
~~~

Dùng `ObjectName.equals` hoặc canonical names khi so tên; thứ tự key property không quyết định danh tính.

### Khi có nhiều instance cùng loại

~~~text
com.example:type=QueueMonitor,name=payments
com.example:type=QueueMonitor,name=shipping
com.example:type=QueueMonitor,name=notifications
~~~

Có thể gắn listener vào cả ba bằng mapping cụ thể. Đối với nguồn được tạo động, cần thiết kế cơ chế khám phá và đăng ký lifecycle; không mặc định một pattern wildcard trong cấu hình listener luôn được Spring coi như “subscribe mọi MBean hiện tại và tương lai”.

## 12. Có thể đăng ký listener với MBean do JVM/framework tạo không?

Có thể, nếu MBean đó là một notification broadcaster và client có quyền đăng ký.

Ví dụ nhiều MBean do JVM cung cấp có thể hỗ trợ notification cụ thể như một số Memory/GC MXBeans; nhưng không phải mọi MBean thuộc `java.lang` đều phát notification.

Trong code, dùng `MBeanServerConnection.addNotificationListener` với ObjectName đã xác định và có quyền:

~~~java
connection.addNotificationListener(
    targetName,
    listener,
    filter,
    targetName
);
~~~

Điều kiện:

- `targetName` được đăng ký trong MBeanServer.
- Target hỗ trợ notification broadcasting.
- Caller được phép đăng ký listener.
- Kênh kết nối và kiểu listener phù hợp với cơ chế local/remote.

**Đừng nhầm** listener do Spring exporter quản lý với một subscription trên MBeanServer bất kỳ. Nếu target không thuộc exporter đang dùng, đăng ký qua `MBeanServerConnection` thường rõ ràng hơn.

## 13. Listener cho nhiều MBean trên JMX remote connector

Với remote JMX, client có thể dùng `MBeanServerConnection`:

~~~java
import javax.management.MBeanServerConnection;
import javax.management.Notification;
import javax.management.NotificationListener;
import javax.management.ObjectName;

NotificationListener listener = (notification, handback) -> {
    System.out.println(notification.getType());
};

ObjectName cacheName = new ObjectName(
    "com.example:type=CacheMonitor,name=products"
);

ObjectName queueName = new ObjectName(
    "com.example:type=QueueMonitor,name=payments"
);

connection.addNotificationListener(
    cacheName, listener, null, cacheName
);

connection.addNotificationListener(
    queueName, listener, null, queueName
);
~~~

`connection` là `MBeanServerConnection` lấy từ `JMXConnector`. Nếu kết nối remote bị đóng hoặc mất, subscription có thể không còn hiệu lực; client cần thiết kế reconnect và re-subscribe.

### Vì sao cần lưu mapping subscription?

Một client quản trị nhiều MBean nên giữ danh sách:

~~~text
[ObjectName, NotificationListener, NotificationFilter, handback]
~~~

Danh sách này dùng để:

1. Tự đăng ký lại sau reconnect.
2. Hủy đúng registration khi shutdown.
3. Ghi log source của sự kiện theo ObjectName.
4. Xử lý MBean thay thế hoặc không còn tồn tại.
5. Tránh đăng ký lặp nhiều lần ngoài ý muốn.

Không nên chỉ giữ `Notification.getSource()` rồi giả định giá trị đó luôn là ObjectName. Source do emitter tạo; tùy server/connector, client có thể thấy source được chuyển đổi, nhưng cần dùng handback và mapping subscription khi cần định danh đáng tin cậy.

## 14. Đăng ký nhiều MBean bằng vòng lặp

Khi có danh sách ObjectName cố định, có thể dùng:

~~~java
import java.util.List;
import javax.management.MBeanServerConnection;
import javax.management.NotificationListener;
import javax.management.ObjectName;

public final class MultiMBeanSubscriber {
    private final MBeanServerConnection connection;
    private final NotificationListener listener;

    public MultiMBeanSubscriber(
            MBeanServerConnection connection,
            NotificationListener listener
    ) {
        this.connection = connection;
        this.listener = listener;
    }

    public void subscribe(List<ObjectName> names)
            throws Exception {
        for (ObjectName name : names) {
            connection.addNotificationListener(
                name,
                listener,
                null,
                name
            );
        }
    }

    public void unsubscribe(List<ObjectName> names)
            throws Exception {
        for (ObjectName name : names) {
            connection.removeNotificationListener(name, listener);
        }
    }
}
~~~

Mẫu này đơn giản nhưng cần xem xét lỗi giữa chừng: nếu đăng ký thành công MBean đầu rồi MBean thứ hai thất bại, listener vẫn có thể đang đăng ký trên MBean đầu.

Với hệ thống thật nên ghi lại từng subscription thành công, và khi một bước thất bại hãy cleanup các registration đã tạo hoặc báo trạng thái partial registration rõ ràng. Không nên coi một vòng lặp nhiều registration là một transaction nguyên tử.

## 15. Partial registration và cleanup khi lỗi

Một cách triển khai an toàn hơn:

~~~java
import java.util.ArrayList;
import java.util.List;
import javax.management.MBeanServerConnection;
import javax.management.NotificationListener;
import javax.management.ObjectName;

public final class SafeMultiSubscriber {
    private final MBeanServerConnection connection;
    private final NotificationListener listener;

    public SafeMultiSubscriber(
            MBeanServerConnection connection,
            NotificationListener listener
    ) {
        this.connection = connection;
        this.listener = listener;
    }

    public List<ObjectName> subscribeAll(List<ObjectName> names)
            throws Exception {

        List<ObjectName> registered = new ArrayList<>();

        try {
            for (ObjectName name : names) {
                connection.addNotificationListener(
                    name, listener, null, name
                );
                registered.add(name);
            }
            return registered;
        } catch (Exception error) {
            for (ObjectName name : registered) {
                try {
                    connection.removeNotificationListener(name, listener);
                } catch (Exception cleanupError) {
                    error.addSuppressed(cleanupError);
                }
            }
            throw error;
        }
    }
}
~~~

Mẫu này cố gắng cleanup khi có lỗi. Trong remote JMX, vẫn có thể tồn tại tình huống kết quả đăng ký không chắc chắn nếu kết nối bị ngắt sau khi server xử lý; muốn độ tin cậy cao cần giữ lifecycle và đối chiếu lại subscriptions khi reconnect.

## 16. MBean động: đăng ký listener cho nguồn xuất hiện sau

Các MBean có thể được đăng ký và hủy đăng ký theo lifecycle Spring hoặc theo resource động.

Nếu muốn listener nhận sự kiện từ MBean được thêm sau khi subscriber khởi động, phải thiết kế một cơ chế theo dõi registry thay vì chỉ query một lần.

JMX có MBean delegate:

~~~text
JMImplementation:type=MBeanServerDelegate
~~~

MBean này phát `MBeanServerNotification` khi MBean được đăng ký hoặc hủy đăng ký.

Một mô hình:

~~~text
Client
  |
  +-- Subscribe to MBeanServerDelegate
  |
  +-- Query existing MBeans
  |
  +-- Subscribe to matching emitters
  |
  +-- On registration:
  |     +-- Check ObjectName
  |     +-- Subscribe new emitter
  |
  +-- On unregistration:
        +-- Remove subscription tracking
~~~

Khi dùng delegate và query, cần phòng tránh race condition giữa hai bước. Ví dụ đăng ký delegate trước, sau đó query existing names và dùng một set idempotent subscriptions để tránh thêm listener trùng khi một MBean vừa xuất hiện đồng thời với query.

### Ví dụ đăng ký delegate listener

~~~java
import javax.management.MBeanServerNotification;
import javax.management.NotificationListener;
import javax.management.ObjectName;

ObjectName delegate = new ObjectName(
    "JMImplementation:type=MBeanServerDelegate"
);

NotificationListener registryListener = (notification, handback) -> {
    if (notification instanceof MBeanServerNotification event) {
        System.out.println(
            "Registry event: " + notification.getType()
            + " -> " + event.getMBeanName()
        );
    }
};

connection.addNotificationListener(
    delegate,
    registryListener,
    null,
    null
);
~~~

Ví dụ sử dụng pattern matching cho `instanceof` của Java hiện đại; với phiên bản Java cũ cần cast truyền thống.

**Giới hạn:** delegate event không phải lịch sử sự kiện bền vững. Client mất kết nối có thể bỏ lỡ registration event; sau reconnect cần query lại registry và đồng bộ subscriptions.

## 17. Phân biệt một listener chung với nhiều listener riêng

### Một listener chung

~~~text
Cache A --+
Cache B --+--> SharedListener
Queue C --+
~~~

Ưu điểm:

- Thống nhất logging và xử lý notification.
- Dễ tổng hợp metric sự kiện và policy.
- Ít lớp listener.
- Có thể dùng filter/handback để phân biệt nguồn.

Nhược điểm:

- Logic dễ phình to khi nhiều type khác nhau.
- Một listener xử lý chậm có thể làm ảnh hưởng các nguồn phát.
- Cần routing và kiểm soát concurrency cẩn thận.

### Listener riêng

~~~text
Cache A --> CacheListener
Cache B --> CacheListener
Queue C --> QueueListener
~~~

Ưu điểm:

- Trách nhiệm riêng, dễ test theo loại event.
- Dễ giới hạn dependency và quyền xử lý.
- Ít nhầm lẫn giữa các schema notification khác nhau.

Nhược điểm:

- Thêm cấu hình/registration.
- Có thể lặp logic audit, logging hoặc error handling.

Một phương án kết hợp là một listener chung chỉ làm nhiệm vụ **routing nhanh** tới những handler riêng theo notification type và resource identity.

## 18. Thiết kế handler không làm chậm emitter

Một notification listener có thể được gọi trên thread của emitter hoặc một executor tùy implementation. Không nên giả định listener luôn chạy trong background thread tách biệt.

Tránh:

~~~java
@Override
public void handleNotification(
        Notification notification, Object handback
) {
    externalApi.callSlowly(notification);
    database.runLongTransaction(notification);
}
~~~

Nếu emitter dispatch đồng bộ, handler này có thể làm chậm operation quản trị hoặc luồng nghiệp vụ phát event.

Cách hợp lý hơn:

1. Validate dữ liệu notification nhanh.
2. Chuyển event cần xử lý vào executor hoặc bounded queue.
3. Xử lý logic chậm ở worker riêng.
4. Giới hạn số lượng event đang chờ.
5. Định nghĩa chiến lược khi queue đầy: drop, coalesce, backpressure hoặc chuyển sang hệ thống event khác.
6. Tránh tạo vô hạn thread hoặc queue theo số notification.

### Ví dụ listener đưa sự kiện vào executor

~~~java
import java.util.concurrent.ExecutorService;
import javax.management.Notification;
import javax.management.NotificationListener;

public class AsyncNotificationListener
        implements NotificationListener {

    private final ExecutorService executor;

    public AsyncNotificationListener(ExecutorService executor) {
        this.executor = executor;
    }

    @Override
    public void handleNotification(
            Notification notification,
            Object handback
    ) {
        executor.execute(() -> process(notification, handback));
    }

    private void process(Notification notification, Object handback) {
        System.out.println(notification.getType());
    }
}
~~~

Mẫu này chỉ minh họa dispatch bất đồng bộ. Production cần xử lý `RejectedExecutionException`, shutdown lifecycle, queue capacity và dữ liệu `userData` có thể không an toàn nếu chia sẻ object mutable giữa nhiều thread.

## 19. Dữ liệu notification và ý nghĩa của source

Một notification thường có:

~~~text
type
source
sequenceNumber
timeStamp
message
userData
~~~

Khi listener nhận từ nhiều nguồn, đừng chỉ dùng `sequenceNumber` để xác định thứ tự toàn cục. Các emitter có thể có sequence counter riêng, clock khác nhau hoặc notification được xử lý không đồng bộ.

Gợi ý key để log:

~~~text
target JVM / ObjectName / notification type / sequence number / timestamp
~~~

Nếu listener dùng `handback` để mang ObjectName thì kết quả dễ phân tích hơn:

~~~java
ObjectName sourceName = (ObjectName) handback;
System.out.println(
    "MBean=" + sourceName.getCanonicalName()
    + ", type=" + notification.getType()
);
~~~

Chỉ cast như trên khi chính code registration bảo đảm handback là `ObjectName`. Nếu Spring exporter gắn handback theo cấu hình khác, cần xem hợp đồng callback thực tế.

## 20. Notification metadata và @ManagedNotification

Trong Spring JMX, `@ManagedNotification` mô tả các loại notification mà MBean có thể phát. Ví dụ:

~~~java
import org.springframework.jmx.export.annotation.ManagedNotification;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example:type=Cache,name=products"
)
@ManagedNotification(
    name = "com.example.cache.refreshed",
    description = "Emitted after a cache refresh"
)
public class CacheManagement {
    // Implementation.
}
~~~

**Metadata khác runtime event.** Chỉ khai báo `@ManagedNotification` không làm sự kiện tự phát. Bean phải thực sự phát notification qua cơ chế JMX/Spring phù hợp.

Với Spring, có thể dùng hỗ trợ notification publishing của framework thay vì tự implement `NotificationBroadcasterSupport` trong mọi trường hợp. Khi dùng annotation và publisher, cần thống nhất `notification type` trong metadata với loại sự kiện thực tế.

Nếu muốn kiểm chứng MBean hỗ trợ loại sự kiện nào:

~~~java
import javax.management.MBeanInfo;
import javax.management.MBeanNotificationInfo;

MBeanInfo info = connection.getMBeanInfo(targetName);

for (MBeanNotificationInfo notificationInfo :
        info.getNotifications()) {
    for (String type : notificationInfo.getNotifTypes()) {
        System.out.println(type);
    }
}
~~~

MBeanInfo cho biết capability được công bố; không chứng minh listener đã đăng ký hoặc event chắc chắn được phát.

## 21. Lỗi thường gặp khi đăng ký nhiều MBean

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Listener chỉ nhận từ MBean đầu tiên | Chỉ đăng ký một ObjectName | Đăng ký riêng từng nguồn |
| `InstanceNotFoundException` | ObjectName chưa được đăng ký hoặc vừa bị xóa | Query registry và kiểm tra lifecycle |
| `RuntimeOperationsException` hoặc lỗi khác | Tham số registration sai | Kiểm tra listener/filter/handback |
| Không thấy notification | MBean không hỗ trợ phát event hoặc chưa phát | Metadata, emitter implementation và test |
| MappedObjectNames không khớp | Tên khác một key/value | So canonical ObjectName |
| Listener nhận quá nhiều event | Filter quá rộng | Dùng filter theo type hoặc source |
| Một event được xử lý nhiều lần | Cùng listener đăng ký nhiều lần hoặc có nhiều subscription | Theo dõi registration và cleanup |
| Listener ngừng nhận sau replace | Target MBean bị unregister/register lại | Re-subscribe và theo dõi delegate |
| Client remote ngừng nhận | Connector disconnect | Reconnect và re-subscribe |
| Trùng event khi nhiều replica | Collector gộp nguồn sai | Gắn target JVM/instance identity |
| Memory leak khi shutdown | Không remove listener | Quản lý lifecycle và cleanup |
| App chậm sau khi bật listener | Handler blocking | Async dispatch có giới hạn |

## 22. Integration test cho nhiều nguồn

Một integration test nên kiểm tra đủ cả hai MBean:

1. Tạo MBeanServer cô lập.
2. Đăng ký `CacheMonitor` và `QueueMonitor`.
3. Đăng ký cùng listener trên cả hai ObjectName.
4. Gọi `refresh()` và `signalThreshold()`.
5. Chờ nhận đủ hai loại notification theo cơ chế test phù hợp.
6. Kiểm tra ObjectName/handback để phân biệt nguồn.
7. Kiểm tra filter chặn notification ngoài scope.
8. Remove listener của một MBean, xác nhận MBean còn lại vẫn phát tới listener.
9. Đóng server/context và xác nhận cleanup.

### Ví dụ test cơ bản với CountDownLatch

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import javax.management.NotificationListener;
import javax.management.ObjectName;

CountDownLatch latch = new CountDownLatch(2);

NotificationListener listener = (notification, handback) -> {
    latch.countDown();
};

server.addNotificationListener(cacheName, listener, null, cacheName);
server.addNotificationListener(queueName, listener, null, queueName);

server.invoke(cacheName, "refresh", new Object[0], new String[0]);
server.invoke(queueName, "signalThreshold",
              new Object[0], new String[0]);

if (!latch.await(5, TimeUnit.SECONDS)) {
    throw new AssertionError("Expected two notifications");
}
~~~

`server`, `cacheName` và `queueName` là những biến phải được tạo trước trong fixture. Đoạn code minh họa việc đợi hai callback, nhưng test production nên lưu loại notification để xác nhận **mỗi nguồn phát đúng một loại mong đợi**, không chỉ tổng số hai event.

## 23. Kiểm tra listener trong JConsole

JConsole hỗ trợ quan sát notification trên một số MBean. Khi thử nghiệm:

1. Khởi chạy ứng dụng và kết nối tới đúng JVM.
2. Mở tab **MBeans**.
3. Chọn nguồn `CacheMonitor`.
4. Tìm phần notification (nếu công cụ hỗ trợ).
5. Subscribe và gọi operation `refresh()`.
6. Xác nhận event hiển thị.
7. Lặp lại với `QueueMonitor`.
8. So sánh notification type, source và sequence.
9. Kiểm tra trong ứng dụng Spring rằng listener chung nhận event của cả hai nguồn.

JConsole subscription riêng của công cụ không phải bằng chứng Spring exporter đã đăng ký listener của ứng dụng. Muốn xác nhận Spring listener, cần log test hoặc assertion trực tiếp từ listener bean.

## 24. Bảo mật và quyền truy cập notification

Notification cũng có thể mang dữ liệu nhạy cảm. Một `Notification` có trường `userData` mà emitter có thể dùng để gắn thông tin chi tiết.

Không nên công bố:

- Password hoặc token.
- Dữ liệu cá nhân.
- Connection string chứa credentials.
- Chi tiết nội bộ gây lộ kiến trúc nhạy cảm.
- Toàn bộ stack trace hoặc payload nghiệp vụ nếu không cần.

Với remote JMX, connector cần authentication, TLS và authorization. Quyền đăng ký listener có thể phụ thuộc policy của connector/server. Một listener đọc notification không nên được cấp quyền `readwrite` chỉ vì ứng dụng có các operation khác.

Ngoài ra, nếu listener chuyển event tới Slack, email hoặc hệ thống khác, đó là một đường dữ liệu ra ngoài cần được kiểm soát riêng.

## 25. Những trường hợp đặc biệt

### Nhiều ApplicationContext

Một JVM có thể chứa parent/child contexts hoặc nhiều context độc lập cùng dùng platform MBeanServer. Listener trong một exporter không mặc nhiên bao phủ MBean của exporter/context khác. Xác định rõ owner và scope của từng exporter.

### MBean bị replace

Nếu dùng `RegistrationPolicy.REPLACE_EXISTING`, cùng ObjectName có thể trỏ tới một MBean mới. Subscription cũ không nhất thiết được chuyển giao. Client cần xử lý registry change và đăng ký lại.

### MBean bị unregister khi context đóng

Các registration gắn với MBean cũ có thể không còn. Listener client cần xóa tracking và có thể subscribe khi nguồn xuất hiện trở lại.

### Multi-replica

Cùng ObjectName trên hai JVM không phải cùng emitter. Client remote chỉ nhận notification của target JVM mà connection đang kết nối. Nếu muốn tổng hợp toàn cluster, cần nhiều connection/subscription và nhãn target riêng.

### Notification quá nhiều

Nếu MBean phát hàng nghìn notification/giây, JMX có thể không phải transport phù hợp cho event streaming. Sử dụng metric aggregation hoặc hệ thống message broker khi cần throughput, buffering và replay.

## 26. Checklist triển khai

Trước khi chạy hệ thống có một listener theo dõi nhiều MBean:

1. Các MBean nguồn đã được đăng ký đúng ObjectName?
2. Tất cả nguồn thực sự hỗ trợ NotificationBroadcaster/Emitter?
3. Spring exporter có quản lý đúng những MBean đang được mapping?
4. Listener bean có được tạo đúng context?
5. MappedObjectNames có đầy đủ và chính xác?
6. Có filter phù hợp cho từng loại notification?
7. Handler có nhanh và không gây blocking đáng kể?
8. Có giới hạn queue hoặc executor cho xử lý bất đồng bộ?
9. Có cleanup khi shutdown hoặc đổi context?
10. Có xử lý re-subscribe sau reconnect/replace?
11. Có dùng handback/target identity để phân biệt nguồn?
12. Có unit/integration test cho ít nhất hai emitter?
13. Có kiểm soát dữ liệu nhạy cảm trong userData/log?
14. Có xác định notification delivery không phải bảo đảm bền vững?
15. Có chính sách cho MBean mới được tạo động?

## 27. Câu hỏi tự kiểm tra

**1. Một NotificationListener có thể nhận từ nhiều MBean không?**

Có. Cần đăng ký listener riêng với từng MBean hoặc sử dụng Spring exporter mapping phù hợp.

**2. Đăng ký listener cho một ObjectName pattern có tự theo dõi mọi MBean sinh sau không?**

Không nên giả định. Nếu cần theo dõi MBean động, thiết kế registry listener và đồng bộ subscription riêng.

**3. Vì sao cần handback?**

Nó giúp truyền context của registration, chẳng hạn ObjectName nguồn hoặc resource ID, để listener phân biệt notification khi dùng chung.

**4. Dùng `@ManagedNotification` có tự phát event không?**

Không. Annotation chỉ khai báo metadata; implementation phải thực sự emit notification.

**5. MBeanProxyFactoryBean có phải công cụ chính để nhận notification không?**

Không. Nó giúp tạo typed proxy để gọi attributes/operations; nhận notification sử dụng listener và cơ chế registration của JMX hoặc Spring exporter.

**6. Vì sao notification có thể mất sau reconnect?**

Subscription thường gắn với connection/registration runtime và không có cơ chế replay bền vững tự động.

**7. Notification sequenceNumber có là số thứ tự toàn cục giữa nhiều MBean không?**

Không. Mỗi emitter có thể phát sequence riêng. Cần thêm ObjectName/target identity khi đối chiếu.

**8. Có thể dùng một listener cho MBean do JVM và custom MBean không?**

Có nếu các emitter hỗ trợ notification và client có quyền. Với nguồn không thuộc Spring exporter hiện tại, đăng ký trực tiếp qua MBeanServerConnection thường rõ hơn.

## 28. Tổng kết

Đăng ký listener cho nhiều MBean trong Spring JMX là một bài toán phối hợp **nhiều nguồn phát → một hoặc nhiều handler**.

- JMX API cho phép dùng cùng `NotificationListener` và gọi `addNotificationListener` cho từng ObjectName.
- Spring `MBeanExporter` cùng `NotificationListenerBean` giúp cấu hình listener cho các MBean nằm trong phạm vi exporter.
- `NotificationFilter` giúp chọn event cần thiết, `handback` giúp mang thông tin nguồn.
- Với MBean động, cần quan sát registry và quản lý re-subscribe.
- Với remote JMX, phải xử lý reconnect, quyền truy cập và khả năng mất notification.
- Handler cần nhanh, có kiểm soát concurrency và không làm lộ dữ liệu nhạy cảm.

**Một listener chung không xóa bỏ lifecycle của từng subscription.** Thiết kế tốt cần xác định chính xác ObjectName của mỗi emitter, loại notification cần nhận và cách cleanup khi nguồn hoặc connection thay đổi.

### Tài liệu tham khảo

- Spring Framework Reference — JMX Notifications: https://docs.spring.io/spring-framework/reference/integration/jmx/notifications.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework API — `NotificationListenerBean`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/NotificationListenerBean.html
- Java SE API — `NotificationListener`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/NotificationListener.html
- Java SE API — `MBeanServerConnection`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html
- Java SE API — `MBeanServerNotification`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerNotification.html
