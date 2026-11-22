# Notification không đến listener trong Spring Framework JMX

## 1. Vấn đề và mục tiêu

Trong Java Management Extensions (**JMX**), một MBean có thể phát **notification** để thông báo các sự kiện quản trị như cache được làm mới, worker thất bại, hàng đợi vượt ngưỡng hay kết nối được phục hồi. Spring Framework JMX hỗ trợ cơ chế này qua **NotificationPublisher**, **NotificationPublisherAware**, **@ManagedNotification**, **NotificationListenerBean** và **MBeanExporter**.

Một lỗi thường gặp là MBean hoạt động bình thường, JConsole vẫn đọc được attributes hoặc gọi được operations, nhưng **listener không nhận được notification**. Đây không nhất thiết là lỗi của JMX transport. Notification có thể chưa từng được phát, listener có thể chưa được đăng ký, bộ lọc có thể loại sự kiện, MBean có thể bị thay thế hoặc kết nối remote đã mất.

Mục tiêu của bài học là điều tra theo chuỗi:

~~~text
Business event
    |
    v
MBean tạo Notification
    |
    v
NotificationPublisher / NotificationBroadcaster
    |
    v
MBeanServer + ObjectName
    |
    v
Listener registration + filter
    |
    v
Local/remote dispatch
    |
    v
handleNotification(...)
~~~

**Nguyên tắc chẩn đoán:** xác định sự kiện bị mất ở bước nào thay vì sửa ngẫu nhiên nhiều lớp. Việc nhìn thấy `@ManagedNotification` hoặc `MBeanInfo.getNotifications()` không chứng minh một notification thực tế đã được phát.

## 2. Các thành phần phải được phân biệt

| Thành phần | Trách nhiệm | Sai sót thường gặp |
| --- | --- | --- |
| `@ManagedNotification` | Khai báo metadata loại sự kiện mà MBean hỗ trợ | Có annotation nhưng không có code phát |
| `NotificationPublisherAware` | Nhận publisher do Spring exporter gắn | Bean không được exporter quản lý |
| `NotificationPublisher` | Phát notification từ bean Spring | Publisher chưa sẵn sàng hoặc không được gọi |
| `NotificationBroadcasterSupport` | Phát notification theo API JMX thuần | Listener đăng ký vào MBean khác |
| `NotificationListener` | Nhận callback `handleNotification` | Không đăng ký hoặc xử lý lỗi |
| `NotificationFilter` | Quyết định event có được chuyển đến hay không | Sai notification type hoặc filter quá chặt |
| `NotificationListenerBean` | Định nghĩa listener/filter/target cho Spring exporter | `mappedObjectNames` không khớp |
| `MBeanServerConnection` | Đăng ký listener ở local/remote | Sai target, mất kết nối, thiếu quyền |
| `ObjectName` | Định danh MBean trong server | Sai domain/key/value |
| `MBeanServerDelegate` | Thông báo khi MBean đăng ký/hủy đăng ký | Không theo dõi khi MBean bị replace |

**Metadata, registration và delivery là ba trạng thái khác nhau.** Một MBean có metadata đúng nhưng listener chưa được đăng ký thì không có callback. Một listener đã được đăng ký cũng không thể nhận notification chưa được emitter phát.

## 3. Phân loại triệu chứng trước khi sửa

Cùng một câu “không nhận event” có thể che giấu nhiều tình huống.

### Tình huống A: Chưa từng nhận được

- Sai ObjectName.
- MBean không hỗ trợ notification.
- Publisher không được inject.
- Listener chưa gắn vào target.
- NotificationFilter loại tất cả.
- Business event chưa xảy ra.

### Tình huống B: Đã nhận rồi đột nhiên ngừng

- MBean bị unregister hoặc replace.
- Spring context restart nhưng client không re-subscribe.
- JMX remote connection bị ngắt.
- Executor xử lý listener bị shutdown.
- Handler ném exception hoặc queue xử lý bị đầy.
- Policy throttle/rate limit ngăn event.

### Tình huống C: Chỉ mất một số event

- Filter theo type sai.
- Listener bị backlog.
- Event bị suppress/coalesce ở source.
- Hai MBean phát các loại notification khác nhau.
- Async dispatch tạo điều kiện mất dữ liệu khi shutdown.
- Remote JMX không có cơ chế replay toàn bộ event đã phát trong lúc mất kết nối.

Từ phân loại này, chọn kiểm tra tối thiểu có khả năng xác định vị trí lỗi.

## 4. Bước 1: xác nhận đúng MBeanServer và ObjectName

Một listener không thể nhận từ MBean nằm trong JVM hoặc MBeanServer khác.

Ví dụ MBean mong đợi:

~~~text
com.example.orders:type=Queue,name=payments
~~~

Kiểm tra:

~~~java
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;

public static void ensureRegistered(
        MBeanServerConnection connection
) throws Exception {
    ObjectName name = new ObjectName(
        "com.example.orders:type=Queue,name=payments"
    );

    if (!connection.isRegistered(name)) {
        throw new IllegalStateException(
            "MBean not registered: " + name
        );
    }
}
~~~

Khi `isRegistered(name)` là `false`, hãy kiểm tra:

1. Spring bean đã được tạo trong ApplicationContext chưa?
2. `MBeanExporter` hoặc `AnnotationMBeanExporter` có hoạt động không?
3. ObjectName do exporter tạo có khác dự kiến không?
4. MBean có bị unregister hoặc thay bằng một MBean khác không?
5. Đoạn code đang dùng đúng MBeanServer chưa?

Có thể query theo domain:

~~~java
ObjectName pattern = new ObjectName("com.example.orders:*");

for (ObjectName objectName : connection.queryNames(pattern, null)) {
    System.out.println(objectName.getCanonicalName());
}
~~~

Dùng `getCanonicalName()` hoặc `ObjectName.equals` để tránh nhầm vì thứ tự key property.

### Lưu ý local và remote

`ManagementFactory.getPlatformMBeanServer()` trả MBeanServer **của JVM đang gọi**. Chạy một chương trình kiểm tra ở JVM khác rồi gọi phương thức đó không tự kết nối đến ứng dụng Spring đang chạy. Để truy cập JVM khác, dùng `JMXConnector` và `MBeanServerConnection` của endpoint đích.

## 5. Bước 2: xác nhận MBean có metadata notification

JMX cung cấp `MBeanInfo` để đọc danh sách loại notification được MBean công bố:

~~~java
import javax.management.MBeanInfo;
import javax.management.MBeanNotificationInfo;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;

public static void printNotificationMetadata(
        MBeanServerConnection connection,
        ObjectName name
) throws Exception {
    MBeanInfo info = connection.getMBeanInfo(name);

    for (MBeanNotificationInfo item : info.getNotifications()) {
        System.out.println("Description: " + item.getDescription());

        for (String type : item.getNotifTypes()) {
            System.out.println("Type: " + type);
        }
    }
}
~~~

Ví dụ mong đợi:

~~~text
com.example.orders.queue.threshold
com.example.orders.queue.recovered
~~~

Nếu danh sách rỗng hoặc thiếu type:

- Bean có khai báo `@ManagedNotification` hay `getNotificationInfo()` phù hợp chưa?
- Exporter có dùng annotation metadata hoặc assembler tương ứng không?
- Target hiện tại là đúng MBean chưa?
- Có dùng Standard MBean wrapper hoặc proxy khác metadata dự kiến không?
- Có quên cung cấp `NotificationBroadcaster` hoặc publisher tương ứng không?

**Quan trọng:** `getNotifications()` mô tả loại sự kiện được công bố; nó không đếm các event đã phát. Một MBean có metadata đúng vẫn có thể không bao giờ gọi `sendNotification`.

Ngược lại, với một số MBean có thể phát sự kiện nhưng khai báo metadata thiếu/chưa chuẩn, kiểm tra registry và việc đăng ký listener vẫn cần thiết. Không dùng metadata đơn lẻ làm kết luận cuối cùng.

## 6. Bước 3: xác nhận code thực sự phát notification

### 6.1. Ví dụ với Spring NotificationPublisherAware

~~~java
package com.example.orders.management;

import java.util.concurrent.atomic.AtomicLong;
import javax.management.Notification;

import org.springframework.jmx.export.annotation.ManagedNotification;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.jmx.export.notification.NotificationPublisher;
import org.springframework.jmx.export.notification.NotificationPublisherAware;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.orders:type=Queue,name=payments",
    description = "Payment queue management"
)
@ManagedNotification(
    name = "com.example.orders.queue.threshold",
    description = "Payment queue crossed threshold"
)
public class PaymentQueueManagement
        implements NotificationPublisherAware {

    private final AtomicLong sequence = new AtomicLong();
    private volatile NotificationPublisher publisher;

    @Override
    public void setNotificationPublisher(NotificationPublisher publisher) {
        this.publisher = publisher;
    }

    public void onQueueThreshold(long pending) {
        NotificationPublisher current = publisher;

        if (current == null) {
            throw new IllegalStateException(
                "JMX NotificationPublisher not initialized"
            );
        }

        Notification notification = new Notification(
            "com.example.orders.queue.threshold",
            this,
            sequence.incrementAndGet(),
            System.currentTimeMillis(),
            "Queue pending=" + pending
        );

        current.sendNotification(notification);
    }
}
~~~

Đoạn ví dụ cho phép tách hai vấn đề:

- `onQueueThreshold` có được gọi thực sự không?
- `NotificationPublisher` có được Spring gắn vào bean đã export không?

Nếu `publisher == null`, đừng chỉ ép gọi `sendNotification` trên một đối tượng mới; hãy kiểm tra cách exporter nhận bean, lifecycle và whether Spring đang quản lý instance được gọi.

### Những lý do publisher không được inject

- Class có `@ManagedResource` nhưng không được export.
- Business code tự tạo object bằng `new` thay vì gọi Spring-managed bean được export.
- Bean ở context khác exporter.
- Exporter không dùng cơ chế annotation/publisher mà class giả định.
- Code phát event trước khi exporter hoàn thành đăng ký.
- Có nhiều instance cùng class, publisher chỉ gắn vào một instance.

**Tách class khỏi instance:** việc một class được annotate không nói rằng mọi instance của class đó đều là MBean. Cần xác nhận business event đang gọi đúng instance được Spring exporter công bố.

## 7. Bước 4: kiểm tra listener registration

Theo API JMX, listener chỉ nhận event sau khi được đăng ký:

~~~java
import javax.management.NotificationListener;
import javax.management.ObjectName;

NotificationListener listener = (notification, handback) -> {
    System.out.println(
        "Received type=" + notification.getType()
        + ", source=" + notification.getSource()
    );
};

ObjectName name = new ObjectName(
    "com.example.orders:type=Queue,name=payments"
);

connection.addNotificationListener(
    name,
    listener,
    null,
    name
);
~~~

`connection` là `MBeanServerConnection` đúng server đích.

Nếu lời gọi đăng ký ném exception, phải kiểm tra exception chứ không bỏ qua:

- `InstanceNotFoundException`: target không tồn tại khi đăng ký.
- Lỗi unsupported notification hoặc runtime exception: target/cấu hình không hỗ trợ hoặc lời gọi không hợp lệ.
- `SecurityException` hoặc lỗi connector: client không có quyền.
- `IOException`: kết nối remote có vấn đề.

Lời gọi `addNotificationListener` trả về bình thường không chứng minh event sẽ xảy ra; nó chỉ thiết lập registration theo cơ chế server/connection.

### Đăng ký sai thời điểm

Nếu listener được đăng ký trước khi MBean xuất hiện, registration có thể thất bại. Với ứng dụng khởi động theo nhiều bước, cần đăng ký sau khi exporter đã tạo MBean hoặc có cơ chế chờ MBean hiện diện.

Không dùng một `Thread.sleep` cố định rồi kết luận mọi môi trường sẽ ổn; tốt hơn là kiểm tra `isRegistered`, đồng bộ startup hoặc theo dõi registration notification của MBeanServerDelegate.

## 8. Bước 5: kiểm tra mapping của NotificationListenerBean

Spring Framework có `NotificationListenerBean` để cấu hình listener do `MBeanExporter` quản lý.

Ví dụ:

~~~java
import org.springframework.jmx.export.NotificationListenerBean;

NotificationListenerBean registration =
    new NotificationListenerBean(listener);

registration.setMappedObjectNames(
    "com.example.orders:type=Queue,name=payments"
);
~~~

Sau đó exporter nhận cấu hình:

~~~java
exporter.setNotificationListeners(registration);
~~~

`exporter` là `MBeanExporter` đang quản lý MBean đích. Ví dụ minh họa quan hệ API; cần khai báo exporter/bean trong Spring configuration và đối chiếu overload theo Spring version.

### Khi mapping không khớp

Giả sử exporter đăng ký:

~~~text
com.example.orders:type=Queue,name=payment
~~~

nhưng `NotificationListenerBean` được cấu hình:

~~~text
com.example.orders:type=Queue,name=payments
~~~

Đây là hai ObjectName khác nhau. Listener sẽ không nhận từ nguồn dự kiến.

Nếu exporter dùng `ObjectNamingStrategy`, hãy xem **ObjectName thực tế** qua `queryNames`, đừng chỉ dựa trên bean name hoặc class name.

### Phạm vi của exporter

Listener do `MBeanExporter` cấu hình thường áp dụng cho MBean trong phạm vi exporter quản lý. Nó không tự động là subscription cho mọi MBean thuộc JVM, thư viện hoặc exporter khác. Nếu target do một exporter khác hoặc JDK quản lý, việc đăng ký trực tiếp qua `MBeanServerConnection` có thể thích hợp hơn.

## 9. Bước 6: kiểm tra NotificationFilter

Một listener có thể đã đăng ký nhưng `NotificationFilter` loại tất cả sự kiện.

Ví dụ:

~~~java
import javax.management.NotificationFilter;

NotificationFilter filter = notification ->
    "com.example.orders.queue.threshold".equals(
        notification.getType()
    );
~~~

Nếu emitter phát:

~~~text
com.example.orders.queue.warning
~~~

thì filter sẽ trả `false` và listener không nhận event.

### Cách tách vấn đề

Trong môi trường test:

1. Đăng ký listener với `filter=null`.
2. Phát một event thử nghiệm vô hại.
3. Nếu listener nhận, đối chiếu `notification.getType()`.
4. Khôi phục filter và test lại.
5. Với nhiều loại event, xác minh từng loại riêng.

Đừng nới filter hoặc bỏ hẳn cơ chế bảo vệ trên production khi chưa hiểu nội dung notification có thể chứa dữ liệu nhạy cảm hay không.

### NotificationFilterSupport dùng prefix

`NotificationFilterSupport.enableType("com.example.orders.queue")` cho phép các type có prefix phù hợp. Nếu cần khớp chính xác, dùng `equals`. Một prefix quá rộng có thể nhận event không mong muốn; một prefix quá hẹp có thể bỏ mất type hợp lệ.

## 10. Bước 7: kiểm tra listener có nhận nhưng handler xử lý lỗi

Có trường hợp callback đã được gọi, nhưng logic xử lý sau đó ném lỗi hoặc bỏ event:

~~~java
@Override
public void handleNotification(
        Notification notification,
        Object handback
) {
    downstreamService.send(notification); // Có thể lỗi.
}
~~~

Nếu callback throw exception, cách emitter/connector xử lý lỗi phụ thuộc implementation. Không nên mặc định lỗi được tự retry hoặc sẽ xuất hiện trong log mong muốn.

Một phương pháp debug an toàn:

~~~java
@Override
public void handleNotification(
        Notification notification,
        Object handback
) {
    receivedCounter.incrementAndGet();

    try {
        process(notification, handback);
    } catch (RuntimeException ex) {
        failureCounter.incrementAndGet();
        logger.warn(
            "Failed to process JMX notification type={}",
            notification.getType(),
            ex
        );
    }
}
~~~

`receivedCounter`, `failureCounter`, `process` và `logger` là dependency minh họa. Không nên log toàn bộ `userData` nếu có thể chứa secret hoặc dữ liệu nhạy cảm.

### Async listener và hàng đợi đầy

Nếu listener đưa event vào `BlockingQueue`, một `offer` trả `false` sẽ làm mất event dù callback đã chạy. Hãy đo rõ:

~~~text
notification_received_total
notification_enqueued_total
notification_dropped_total
notification_processed_total
notification_handler_failed_total
~~~

Đây là tên metric ứng dụng gợi ý, không phải JMX metric tự động có sẵn.

Nếu `received_total` tăng nhưng `processed_total` không tăng, vấn đề nằm sau callback, không phải emitter hay registration.

## 11. Bước 8: kiểm tra rate limiter, throttle và coalescing

Một số ứng dụng cố ý giảm tần suất notification để bảo vệ hiệu năng:

~~~text
Business events:       1000
Notification emitted:    20
Notification suppressed: 980
~~~

Khi đó listener không nhận 980 event là hành vi do policy, không nhất thiết lỗi. Cần kiểm tra:

- Event nào được phép drop?
- Bộ giới hạn áp dụng theo MBean, type hay toàn JVM?
- Có trạng thái warning/recovered không?
- Có dùng debounce khiến event bị hoãn vô thời hạn dưới tải liên tục không?
- Có dùng coalescing và phát summary event không?
- Có metric suppressed counter không?

Không nên sửa listener để nhận event mà producer không phát. Cần xác minh chính sách publish tại nguồn.

Đặc biệt, một policy chỉ phát khi vượt ngưỡng sẽ không phát lại với mỗi lần queue depth tăng khi hệ thống vẫn nằm trên ngưỡng. Đó là một thiết kế hợp lệ nếu được tài liệu hóa.

## 12. Bước 9: MBean bị unregister hoặc replace

Khi Spring `ApplicationContext` đóng, exporter có thể unregister MBean. Khi context khác đăng ký lại cùng ObjectName, đó là **MBean mới** dù tên giống hệt.

Ví dụ:

~~~text
T0: MBean A đăng ký dưới ObjectName X
T1: Listener đăng ký với X
T2: Exporter unregister A
T3: Exporter đăng ký MBean B dưới X
T4: Listener không còn nhận notification
~~~

Subscription trên emitter A không mặc nhiên chuyển sang emitter B.

Nếu dùng `RegistrationPolicy.REPLACE_EXISTING`, rủi ro này cũng xuất hiện khi thay MBean đang được sử dụng.

### Quan sát MBeanServerDelegate

JMX có MBean delegate:

~~~text
JMImplementation:type=MBeanServerDelegate
~~~

Có thể lắng nghe `MBeanServerNotification.REGISTRATION_NOTIFICATION` và `UNREGISTRATION_NOTIFICATION`.

~~~java
import javax.management.MBeanServerNotification;
import javax.management.NotificationListener;
import javax.management.ObjectName;

ObjectName delegate = new ObjectName(
    "JMImplementation:type=MBeanServerDelegate"
);

NotificationListener observer = (notification, handback) -> {
    if (notification instanceof MBeanServerNotification event) {
        System.out.println(
            notification.getType() + " " + event.getMBeanName()
        );
    }
};

connection.addNotificationListener(
    delegate,
    observer,
    null,
    null
);
~~~

Ví dụ dùng pattern matching `instanceof` của Java hiện đại. Với Java đời cũ, sử dụng `instanceof` và cast truyền thống.

Khi nhận notification đăng ký lại của ObjectName X, client có thể xác nhận `isRegistered(X)`, kiểm tra metadata và **re-subscribe**. Cần làm thao tác idempotent để tránh đăng ký listener trùng nhiều lần.

**Giới hạn:** registry notification không phải event store. Nếu client mất kết nối, có thể bỏ lỡ sự kiện đăng ký; sau reconnect cần query lại registry.

## 13. Bước 10: mất kết nối JMX remote

Một client remote thường lấy `MBeanServerConnection` từ `JMXConnector`. Khi kết nối bị ngắt:

- Subscription cũ có thể mất.
- Client không nhận notification phát trong thời gian disconnect.
- Callback có thể ngừng tới mà ứng dụng không biết ngay.
- Server và client có thể có trạng thái subscription khác nhau sau reconnect.

Cần phân biệt:

~~~text
MBean vẫn phát event
      |
      v
JMX connector disconnected
      |
      x
Remote listener không nhận
~~~

Với remote JMX, nên theo dõi connection notification của connector và có cơ chế kết nối lại:

~~~java
import javax.management.remote.JMXConnectionNotification;
import javax.management.NotificationListener;

NotificationListener connectionObserver =
    (notification, handback) -> {
        String type = notification.getType();
        if (JMXConnectionNotification.CLOSED.equals(type)
                || JMXConnectionNotification.FAILED.equals(type)) {
            System.out.println("JMX connection interrupted");
        }
    };

connector.addConnectionNotificationListener(
    connectionObserver, null, null
);
~~~

`connector` là một `JMXConnector` đã được tạo/kết nối trước đó. Sau khi reconnect thành công, cần tạo connection phù hợp và đăng ký lại listeners.

Không tự động retry các operation quản trị có side effect chỉ vì kết nối mất; cần xác định kết quả operation trước khi thử lại. Việc re-subscribe listener là một vấn đề riêng với retry operation.

## 14. Chẩn đoán local trước rồi mới remote

Khi remote listener không nhận, nên kiểm tra trong JVM đích:

1. Có một emitter MBean đúng ObjectName không?
2. Local listener có nhận notification không?
3. MBean phát notification thực sự không?
4. Filter local có cho qua type tương ứng không?

Nếu local listener nhận nhưng remote không nhận, tập trung vào:

- JMXConnector đang trỏ đúng JVM?
- TLS/authentication/authorization.
- Listener registration qua remote connection.
- Connection drop, timeout hoặc reconnect.
- Notification serialization/userData type.
- Remote connector backlog hoặc giới hạn delivery.
- Client-side handler và queue.

Nếu cả local lẫn remote đều không nhận, xem publisher, emitter, registration hoặc filter trước.

### Không nhầm JMX remote với HTTP management

Một Spring Boot Actuator endpoint truy cập được qua HTTP không chứng minh JMX remote connector hoạt động. HTTP và JMX là hai đường quản trị khác nhau.

## 15. Kiểm thử tối thiểu bằng NotificationBroadcasterSupport

Để loại bỏ các yếu tố Spring và remote, có thể tạo Standard MBean phát notification với Java thuần.

Interface:

~~~java
package com.example.testjmx;

public interface TestEmitterMBean {
    void emit();
}
~~~

Implementation:

~~~java
package com.example.testjmx;

import java.util.concurrent.atomic.AtomicLong;
import javax.management.Notification;
import javax.management.NotificationBroadcasterSupport;

public class TestEmitter extends NotificationBroadcasterSupport
        implements TestEmitterMBean {

    private final AtomicLong sequence = new AtomicLong();

    @Override
    public void emit() {
        sendNotification(new Notification(
            "com.example.test.event",
            this,
            sequence.incrementAndGet(),
            System.currentTimeMillis(),
            "Synthetic notification"
        ));
    }
}
~~~

Test registration:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.NotificationListener;
import javax.management.ObjectName;

MBeanServer server = MBeanServerFactory.newMBeanServer();

ObjectName name = new ObjectName(
    "com.example.test:type=Emitter,name=primary"
);

server.registerMBean(new TestEmitter(), name);

CountDownLatch latch = new CountDownLatch(1);

NotificationListener listener = (notification, handback) -> {
    if ("com.example.test.event".equals(notification.getType())) {
        latch.countDown();
    }
};

server.addNotificationListener(name, listener, null, null);

try {
    server.invoke(name, "emit", new Object[0], new String[0]);

    if (!latch.await(3, TimeUnit.SECONDS)) {
        throw new AssertionError("Notification not received");
    }
} finally {
    server.removeNotificationListener(name, listener);
    server.unregisterMBean(name);
}
~~~

Khi test trên thành công, JMX notification cơ bản hoạt động. Nếu test thật vẫn lỗi, sự khác biệt nằm ở cách Spring export, ObjectName, filter, lifecycle hoặc connector.

Trong dự án, có thể đặt đoạn test vào phương thức JUnit; đây là ví dụ statement-level để minh họa cơ chế, không phải một file Java độc lập hoàn chỉnh.

## 16. Kiểm thử Spring NotificationPublisher

Một integration test nên tạo Spring context cô lập với:

- Một bean `@ManagedResource` và `@ManagedNotification`.
- Bean implement `NotificationPublisherAware`.
- `AnnotationMBeanExporter` hoặc exporter có metadata phù hợp.
- Một `NotificationListenerBean` mapping đúng ObjectName.
- MBeanServer test riêng.
- `CountDownLatch` hoặc collector thread-safe.

Luồng test:

~~~text
Create test MBeanServer
      |
Create Spring context/exporter
      |
Assert ObjectName registered
      |
Assert notification metadata
      |
Register listener
      |
Call method causing NotificationPublisher.sendNotification()
      |
Await callback with timeout
      |
Assert type/source/handback
      |
Close context and cleanup
~~~

Điểm cần xác nhận là **cùng một bean instance** được business code gọi và được exporter quản lý.

### Ví dụ listener collector trong test

~~~java
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CountDownLatch;
import javax.management.Notification;
import javax.management.NotificationListener;

public class RecordingListener implements NotificationListener {

    private final List<Notification> received =
        new CopyOnWriteArrayList<>();

    private final CountDownLatch latch = new CountDownLatch(1);

    @Override
    public void handleNotification(
            Notification notification,
            Object handback
    ) {
        received.add(notification);
        latch.countDown();
    }

    public boolean awaitNotification(long timeoutSeconds)
            throws InterruptedException {
        return latch.await(
            timeoutSeconds,
            java.util.concurrent.TimeUnit.SECONDS
        );
    }

    public List<Notification> getReceived() {
        return received;
    }
}
~~~

Đừng dùng `Thread.sleep(100)` rồi kiểm tra ngay; timeout có giới hạn và latch giúp test ít bị flaky hơn.

## 17. Khi Spring listener mapping không đúng

Một cấu hình `NotificationListenerBean` có thể giới hạn các MBean được lắng nghe:

~~~java
NotificationListenerBean bean =
    new NotificationListenerBean(recordingListener);

bean.setMappedObjectNames(
    "com.example.orders:type=Queue,name=payments"
);
~~~

Nếu ObjectName thực tế của exporter là:

~~~text
com.example.orders:type=Queue,application=checkout,name=payments
~~~

thì mapping có thể không khớp.

Tương tự, nếu listener được gắn vào một `MBeanExporter` khác với exporter quản lý nguồn phát, listener có thể không nhận theo cơ chế mapping dự kiến.

### Gợi ý chẩn đoán

Đừng chỉ nhìn thấy `NotificationListenerBean` tồn tại trong ApplicationContext rồi kết luận listener đã đăng ký. Cần:

1. Xác nhận exporter sử dụng bean listener đó.
2. Xác nhận exporter thực sự quản lý target.
3. Xác nhận ObjectName được đăng ký trùng mapping.
4. Xác nhận notification type được phát và không bị filter loại.
5. Dùng một event tổng hợp vô hại để kiểm chứng callback.

## 18. Notification type, source và sequence number

Một `Notification` thường có:

~~~text
type
source
sequenceNumber
timestamp
message
userData
~~~

Những trường này giúp chẩn đoán:

- `type`: có khớp filter không?
- `source`: emitter gắn định danh gì? Có thể là object hoặc ObjectName tùy cách xuất/transport.
- `sequenceNumber`: có tăng theo emitter không?
- `timestamp`: event có xảy ra trước khi listener đăng ký không?
- `message`: có mô tả đúng trạng thái không?
- `userData`: có chứa payload cần dùng và có serializable với remote không?

**Không coi sequence number là số thứ tự toàn cục** giữa nhiều MBean. Với nhiều JVM, cần target identity và ObjectName để phân biệt.

Nếu filter dựa vào `notification.getSource().equals(objectName)`, có thể bị lỗi nếu source là một object khác ObjectName. Sử dụng `handback` hoặc mapping registration khi cần xác định nguồn chắc chắn.

## 19. Những lỗi thường gặp và hướng xử lý

| Triệu chứng | Nguyên nhân nghi vấn | Kiểm tra |
| --- | --- | --- |
| MBean có nhưng listener không nhận | Không gọi sendNotification | Log/counter tại producer |
| Metadata có `@ManagedNotification` nhưng không có callback | Annotation chỉ khai báo loại sự kiện | Test phát event thực |
| Publisher null | Bean instance không được exporter gắn publisher | Spring bean và exporter lifecycle |
| `InstanceNotFoundException` khi subscribe | Sai ObjectName hoặc chưa register | `isRegistered`, `queryNames` |
| Listener chỉ nhận vài loại event | Filter khác type thực tế | In type, thử filter=null trong test |
| Listener được tạo nhưng không callback | Chưa gắn vào exporter/MBeanServer | Registration path |
| Local hoạt động, remote không | JMX connector/connection | TLS, quyền, reconnect, serialization |
| Sau restart không còn nhận | Subscription mất | Re-subscribe và query registry |
| Sau REPLACE_EXISTING không còn nhận | MBean mới thay emitter cũ | Delegate event, re-subscribe |
| Callback được gọi nhưng downstream không xử lý | Handler exception hoặc queue đầy | Metrics nhận/xử lý/drop |
| Chỉ mất event dưới tải | Throttling, coalescing hoặc backpressure | Suppressed counter và queue depth |
| Event được gửi trước khi subscribe | Listener chưa tồn tại lúc emit | Điều chỉnh startup/order |
| Người vận hành thấy JConsole event nhưng code không nhận | JConsole listener khác listener Spring | Kiểm tra mapping trong app |
| Một lần emit mà nhận nhiều lần | Listener đăng ký trùng | Kiểm kê subscription và cleanup |
| Notification payload lỗi ở remote | Kiểu userData không tương thích | Serialization/open types |

## 20. Checklist chẩn đoán từng bước

Có thể thực hiện quy trình sau cho một sự cố cụ thể:

1. **Target đúng chưa?** Xác nhận JVM, MBeanServer và canonical ObjectName.
2. **MBean tồn tại chưa?** `isRegistered` trả true.
3. **MBean có thể phát không?** Đọc `MBeanInfo.getNotifications`.
4. **Event business có xảy ra?** Log/counter tại source.
5. **Code có phát không?** Theo dõi invocation của publisher/broadcaster.
6. **Publisher đã inject?** Không null và đúng bean instance.
7. **Listener đã đăng ký?** Kiểm tra `addNotificationListener` hoặc Spring exporter mapping.
8. **Filter có đúng?** So type string chính xác.
9. **Callback có chạy?** Counter ngay đầu `handleNotification`.
10. **Handler có drop event?** Queue đầy, exception, executor ngừng.
11. **MBean có bị replace?** Theo dõi unregister/register.
12. **Remote connection có còn?** Kiểm tra connection notification và reconnect.
13. **Có rate limit?** Xem số event bị suppress.
14. **Test local tối thiểu có chạy?** Phân biệt lỗi JMX core và Spring/transport.
15. **Có cleanup/re-subscribe?** Kiểm tra lifecycle context và listener.
16. **Có dữ liệu nhạy cảm?** Không log raw userData/credential khi debug.

Đây là quy trình đi từ đầu nguồn đến cuối pipeline, giúp tránh xử lý sai nguyên nhân.

## 21. Cách giảm khả năng tái diễn lỗi

### 21.1. Dùng naming contract ổn định

Không xây ObjectName từ tên proxy class hoặc random ID khi không cần. Giữ domain và key properties ổn định để listener mapping không bị lệch giữa release.

### 21.2. Có health và counters cho notification pipeline

Ví dụ:

~~~text
jmx_notification_created_total
jmx_notification_sent_total
jmx_notification_received_total
jmx_notification_processed_total
jmx_notification_dropped_total
jmx_listener_reconnect_total
~~~

Các metric này do ứng dụng tự triển khai, không phải mặc định của Spring. Nếu created tăng nhưng sent không tăng, tìm lỗi producer. Nếu sent tăng nhưng received không tăng, xem registration/filter/connector. Nếu received tăng nhưng processed không tăng, xem handler.

### 21.3. Giới hạn tải và log hợp lý

Đừng format payload lớn rồi phát hàng nghìn notification mỗi giây. Với thay đổi trạng thái lặp, dùng edge-triggered notification hoặc coalescing.

### 21.4. Dùng idempotent re-subscribe

Khi connector reconnect hoặc MBean được đăng ký lại, client nên đối chiếu subscriptions hiện tại trước khi add mới. Tránh nhân đôi event do đăng ký lặp.

### 21.5. Không phụ thuộc vào delivery bền vững

JMX notification không mặc nhiên hỗ trợ replay những event mất khi client chưa kết nối. Nếu event phải không mất, dùng event store/message broker/audit log và JMX chỉ báo trạng thái.

## 22. Bài tập thực hành

**Mục tiêu:** tái tạo và sửa ba sự cố “notification không đến listener”.

### Tình huống A: mapping sai

1. Tạo emitter MBean có ObjectName `com.example.test:type=Queue,name=payments`.
2. Đăng ký listener bằng ObjectName `com.example.test:type=Queue,name=payment`.
3. Quan sát registration thất bại hoặc listener không nhận.
4. Sửa ObjectName đúng.
5. Phát event `com.example.test.queue.warning`.
6. Xác nhận callback chạy.

### Tình huống B: filter sai

1. Emitter phát `com.example.test.queue.warning`.
2. Listener filter chỉ chấp nhận `com.example.test.queue.recovered`.
3. Xác nhận callback không chạy.
4. Đổi filter hoặc tạm dùng `null` trong test.
5. Xác nhận callback chạy.
6. Khôi phục filter đúng theo policy.

### Tình huống C: MBean bị replace

1. Đăng ký MBean A dưới ObjectName X.
2. Add listener, xác nhận nhận event.
3. Unregister A, register MBean B cùng X.
4. Phát event trên B, quan sát subscription cũ không tự được chuyển.
5. Re-subscribe listener lên X.
6. Phát lại event test, xác nhận callback chạy.
7. Hủy registration khi kết thúc.

Các bài tập này nên chạy trên MBeanServer test cô lập, không can thiệp MBean của ứng dụng production.

## 23. Câu hỏi tự kiểm tra

**1. Có `@ManagedNotification` nghĩa là notification chắc chắn được gửi?**

Không. Annotation mô tả metadata. Code phải thực sự gọi publisher/broadcaster để phát.

**2. Vì sao đọc attribute được nhưng listener không nhận?**

Vì đường đọc attribute và đường phát notification khác nhau; MBean tồn tại chưa đủ để listener được đăng ký hoặc event được phát.

**3. `NotificationListenerBean` được tạo trong Spring có bảo đảm đang subscribe không?**

Không. Nó còn phải được exporter phù hợp sử dụng và mapping ObjectName đúng.

**4. Lúc nào cần kiểm tra `filter=null`?**

Khi test muốn tách lỗi filter khỏi lỗi registration hoặc emitter, trong môi trường kiểm soát với sự kiện vô hại.

**5. Vì sao listener mất event sau MBean replace?**

Subscription gắn với emitter đã unregister, không tự chuyển sang MBean mới cùng ObjectName.

**6. Vì sao remote listener ngừng sau reconnect?**

Connection/subscription runtime có thể đã mất; client phải khôi phục connection và re-subscribe.

**7. Cần gì để xác định event bị mất ở đâu?**

Counter/log tại producer, publisher, callback và handler, cùng thông tin ObjectName/filter/connection.

**8. Notification có bảo đảm không mất event khi mạng bị ngắt?**

Không. Với yêu cầu bền vững, dùng hệ thống sự kiện hoặc audit khác.

## 24. Tổng kết

Khi **notification không đến listener** trong Spring Framework JMX, không nên chỉ kiểm tra một annotation hoặc một class listener. Hãy truy vết toàn bộ đường đi:

~~~text
Event xảy ra
    -> publisher phát
    -> MBean có mặt trong registry
    -> listener đăng ký đúng ObjectName
    -> filter cho phép event
    -> connector chuyển event
    -> handler xử lý thành công
~~~

Các nhóm nguyên nhân nổi bật gồm:

- MBean hoặc publisher chưa được cấu hình/khởi tạo đúng.
- Notification chưa thực sự được phát.
- Listener không đăng ký đúng target.
- Filter hoặc mapping sai.
- MBean bị unregister/replace.
- Remote connection gián đoạn.
- Handler lỗi hoặc drop event do quá tải.

Một hệ thống bền vững cần có naming ổn định, lifecycle rõ, re-subscribe khi cần, metrics cho pipeline và nhận thức đúng rằng JMX notification không phải cơ chế event delivery bền vững.

### Tài liệu tham khảo

- Spring Framework Reference — JMX Notifications: https://docs.spring.io/spring-framework/reference/integration/jmx/notifications.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework API — NotificationPublisher: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/notification/NotificationPublisher.html
- Spring Framework API — NotificationListenerBean: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/NotificationListenerBean.html
- Java SE API — MBeanServerConnection: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html
- Java SE API — MBeanServerNotification: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerNotification.html
