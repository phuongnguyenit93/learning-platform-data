# Mapped ObjectNames, NotificationFilter và handback trong Spring JMX

## 1. Bối cảnh: một listener không nhất thiết phải nhận mọi MBean

Java Management Extensions (JMX) hỗ trợ cơ chế phát sự kiện quản trị gọi là **Notification**. Một MBean có thể phát thông báo khi trạng thái thay đổi, ngưỡng bị vượt, cấu hình được chỉnh sửa hoặc một tác vụ quan trọng hoàn tất. Spring Framework cung cấp các lớp hỗ trợ đăng ký listener để application code không cần tự lặp lại mọi bước gọi `MBeanServer.addNotificationListener(...)`.

Khi ứng dụng có nhiều MBean, ba câu hỏi xuất hiện:

1. **Nghe từ đâu?** Listener cần đăng ký với MBean nào? Đây là vai trò của các **mapped ObjectNames**.
2. **Nhận loại notification nào?** Listener có cần nhận tất cả, hay chỉ một số type? Đây là vai trò của **`NotificationFilter`**.
3. **Khi callback chạy, cần biết đây là subscription nào?** Đây là vai trò của **`handback`**.

Cả ba thành phần tạo ra một subscription JMX có ý nghĩa rõ ràng:

```text
Spring ApplicationContext
        |
        +--> MBeanExporter ----------------------+
        |                                        |
        |                              MBeanServer
        |                                        |
        +--> NotificationListenerBean             |
               |                                 |
               +-- mapped ObjectNames -----------+--> QueueMonitor
               |                                 +--> CacheMonitor
               +-- NotificationFilter
               +-- handback
               |
               v
         NotificationListener.handleNotification(notification, handback)
```

Điểm quan trọng: **ObjectName chọn nguồn**, **filter chọn sự kiện**, **handback cung cấp ngữ cảnh callback**. Không thành phần nào trong số đó tự làm một bean phát notification; nguồn phát phải thực hiện hợp đồng JMX notification và gọi cơ chế phát.

## 2. Phân biệt notification với attribute và operation

Một MBean thường cung cấp ba kiểu tương tác:

| Khả năng | Hướng tương tác | Ví dụ |
|---|---|---|
| Attribute | Client đọc hoặc ghi trạng thái | `QueueDepth`, `WarningThreshold` |
| Operation | Client yêu cầu thực thi hành động | `pause()`, `resetCounters()` |
| Notification | Nguồn chủ động phát sự kiện tới listener | `demo.queue.threshold.exceeded` |

Đọc attribute `QueueDepth` là thao tác pull: client phải hỏi. Notification là push từ góc nhìn broadcaster: khi sự kiện xảy ra, JMX phân phối cho những registration đang hợp lệ.

Notification không nhất thiết lưu bền vững, replay sau mất kết nối hoặc giao nhận đúng một lần. Nếu cần lịch sử sự kiện và retry nghiêm ngặt, sử dụng logging/event store hoặc hệ thống messaging phù hợp. Đối với JMX, nên coi notification là tín hiệu vận hành tại thời điểm phát.

## 3. Notification gồm những trường gì?

`javax.management.Notification` chứa dữ liệu chung:

```java
Notification event = new Notification(
    "demo.queue.threshold.exceeded",
    this,
    sequence.incrementAndGet(),
    System.currentTimeMillis(),
    "Queue depth exceeded the threshold"
);
event.setUserData(95);
```

Các trường cần phân biệt:

| Trường | Ý nghĩa |
|---|---|
| `type` | Chuỗi loại sự kiện do broadcaster định nghĩa |
| `source` | Nguồn của notification |
| `sequenceNumber` | Số thứ tự do broadcaster cấp |
| `timeStamp` | Thời điểm phát/khởi tạo event |
| `message` | Mô tả dễ đọc |
| `userData` | Payload bổ sung của notification |
| `handback` | **Không nằm trong notification**; đến từ subscription |

`handback` là tham số thứ hai được JMX truyền vào `NotificationListener.handleNotification`, không phải một field do broadcaster đặt trên event. Một notification có thể tới nhiều registration với **cùng userData** nhưng **handback khác nhau**.

`sequenceNumber` không là sequence toàn cục cho mọi MBean. Mỗi nguồn có thể có bộ đếm riêng, và counter có thể reset sau restart. Không dùng sequence đơn lẻ làm bằng chứng giao nhận đầy đủ trên nhiều JVM.

## 4. ObjectName và mapped ObjectNames

`javax.management.ObjectName` định danh một MBean bên trong một `MBeanServer`.

Ví dụ:

```text
demo.queue:type=QueueMonitor,name=orders
demo.queue:type=QueueMonitor,name=payments
demo.cache:type=CacheMonitor,name=product
```

Một `NotificationListenerBean` của Spring có thể được cấu hình **mapped ObjectNames** để chỉ đăng ký với một tập nguồn cụ thể. Mục đích của mapping là tránh nhận notification từ các MBean ngoài phạm vi của listener.

Ví dụ định hướng:

```text
listener: alertListener

mappedObjectNames:
  - demo.queue:type=QueueMonitor,name=orders
  - demo.queue:type=QueueMonitor,name=payments

filter:
  chỉ nhận demo.queue.critical

handback:
  "oncall-queue"
```

Khi exporter đăng ký listener với những MBean tương ứng, notification từ `demo.cache:type=CacheMonitor,name=product` sẽ không tự đến listener này chỉ vì cùng JVM.

**Mapped ObjectNames chọn broadcaster, không đặt lại tên notification type.** Một MBean có thể phát nhiều type và nhiều MBean có thể phát cùng một type. Do đó khi phân tích sự kiện, thường cần cả nguồn lẫn type.

## 5. NotificationListenerBean trong Spring Framework

Spring hỗ trợ `org.springframework.jmx.export.notification.NotificationListenerBean` để gom ba yếu tố của một registration:

- `NotificationListener` delegate thực thi callback.
- `NotificationFilter` tùy chọn cho việc lọc notification.
- `handback` tùy chọn chứa ngữ cảnh registration.
- Danh sách `mappedObjectNames` xác định các MBean nguồn liên quan.

Ví dụ cấu hình Java:

```java
import javax.management.NotificationListener;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.notification.NotificationListenerBean;

@Configuration
public class JmxListenerConfiguration {

    @Bean
    public NotificationListenerBean queueListenerBean(
            NotificationListener queueListener) {

        NotificationListenerBean registration =
            new NotificationListenerBean();

        registration.setNotificationListener(queueListener);
        registration.setMappedObjectNames(
            "demo.queue:type=QueueMonitor,name=orders",
            "demo.queue:type=QueueMonitor,name=payments"
        );

        registration.setHandback("queue-dashboard");
        return registration;
    }
}
```

Đây là **bean mô tả đăng ký**, chưa đủ nếu không có thành phần exporter/registrar thực sự áp dụng nó. Để Spring quản lý subscription qua `MBeanExporter`, cần đưa `NotificationListenerBean` vào danh sách listener của exporter hoặc sử dụng cấu hình Spring JMX tương ứng.

Tùy phiên bản Spring, chữ ký setter chấp nhận ObjectName được biểu diễn dưới dạng `String`, `ObjectName` hoặc `Object...` có thể được chuyển đổi qua Spring; hãy dùng một API cụ thể phù hợp với dependency thực tế. Trong cấu hình Java thường có thể tạo `ObjectName` rõ ràng để giảm nhầm lẫn với cú pháp.

### 5.1. Nguyên tắc lifecycle

Listener registration gắn với vòng đời exporter. Khi exporter được khởi tạo và đăng ký thành công, Spring có thể thiết lập subscriptions; khi exporter đóng, các registration do nó quản lý cần được gỡ theo lifecycle.

**Một `NotificationListenerBean` không có nghĩa subscription đã tồn tại.** Nếu quên liên kết nó với exporter, các phương thức callback có thể không bao giờ được gọi. Khi debug, kiểm tra exporter, MBeanServer, ObjectName và thời điểm registration thay vì chỉ kiểm tra `@Bean` đã tạo.

## 6. Tạo nguồn phát: NotificationBroadcasterSupport

Hãy xây dựng một Standard MBean phát sự kiện khi queue vượt ngưỡng.

### 6.1. Management interface

```java
// QueueMonitorMBean.java
public interface QueueMonitorMBean {
    int getDepth();
    int getWarningThreshold();
    void setWarningThreshold(int value);
    void updateDepth(int value);
}
```

`Depth` là read-only, `WarningThreshold` là read-write, `updateDepth` là operation phục vụ thí nghiệm.

### 6.2. Implementation phát notification

```java
// QueueMonitor.java
import java.util.concurrent.atomic.AtomicLong;
import javax.management.MBeanNotificationInfo;
import javax.management.Notification;
import javax.management.NotificationBroadcasterSupport;

public class QueueMonitor extends NotificationBroadcasterSupport
        implements QueueMonitorMBean {

    public static final String WARNING = "demo.queue.warning";
    public static final String CRITICAL = "demo.queue.critical";

    private final AtomicLong sequence = new AtomicLong();
    private volatile int depth;
    private volatile int warningThreshold = 70;

    @Override
    public int getDepth() {
        return depth;
    }

    @Override
    public int getWarningThreshold() {
        return warningThreshold;
    }

    @Override
    public void setWarningThreshold(int value) {
        if (value < 1 || value > 100) {
            throw new IllegalArgumentException(
                "WarningThreshold must be between 1 and 100"
            );
        }
        warningThreshold = value;
    }

    @Override
    public void updateDepth(int value) {
        if (value < 0) {
            throw new IllegalArgumentException("Depth must be >= 0");
        }

        depth = value;
        if (value >= warningThreshold) {
            String type = value >= 90 ? CRITICAL : WARNING;
            Notification event = new Notification(
                type,
                this,
                sequence.incrementAndGet(),
                System.currentTimeMillis(),
                "Depth changed to " + value
            );
            event.setUserData(value);
            sendNotification(event);
        }
    }

    @Override
    public MBeanNotificationInfo[] getNotificationInfo() {
        return new MBeanNotificationInfo[] {
            new MBeanNotificationInfo(
                new String[] { WARNING, CRITICAL },
                Notification.class.getName(),
                "Queue threshold events"
            )
        };
    }
}
```

`NotificationBroadcasterSupport` thực hiện cơ chế phát, đăng ký và gỡ listener. `getNotificationInfo()` công bố metadata; **metadata không tự phát sự kiện**. Phải gọi `sendNotification(event)` trong logic cần thiết.

Trong ví dụ, mỗi lần cập nhật depth trên ngưỡng đều phát event. Hệ thống thật có thể muốn chỉ phát khi **đi qua ngưỡng** hoặc chuyển trạng thái, có debounce/rate limit để tránh spam.

### 6.3. Vì sao Standard MBean vẫn phát notification?

`QueueMonitor` implement `QueueMonitorMBean` để định nghĩa attribute và operation, đồng thời kế thừa `NotificationBroadcasterSupport` để phát notification. Hai cơ chế này bổ sung cho nhau.

Đối tượng được đăng ký đúng tên:

```text
demo.queue:type=QueueMonitor,name=orders
```

JMX client có thể đọc `Depth`, gọi `updateDepth` và nhận event qua listener registration khi MBean được đăng ký phù hợp.

## 7. NotificationFilter: lọc theo type

`javax.management.NotificationFilter` khai báo:

```java
boolean isNotificationEnabled(Notification notification);
```

Filter trả `true` khi notification được phép chuyển đến listener trong registration; trả `false` thì notification bị loại khỏi registration đó.

Ví dụ chỉ nhận critical:

```java
import javax.management.NotificationFilter;

NotificationFilter criticalOnly = notification ->
    notification != null &&
    QueueMonitor.CRITICAL.equals(notification.getType());
```

Bộ lọc có thể kết hợp các điều kiện: type, source, nội dung `userData` hoặc sequence khi có ý nghĩa. Tuy nhiên, filter nên xử lý nhanh, không thực hiện network call hoặc truy vấn database dài.

Nếu filter là `null`, registration không yêu cầu lọc và có thể nhận mọi notification mà broadcaster phân phối cho subscription đó.

### 7.1. NotificationFilterSupport

JMX cung cấp `NotificationFilterSupport` hỗ trợ lọc **theo tiền tố type**:

```java
import javax.management.NotificationFilterSupport;

NotificationFilterSupport filter = new NotificationFilterSupport();
filter.enableType("demo.queue.");
```

Filter chấp nhận những type bắt đầu bằng `demo.queue.`, ví dụ:

```text
demo.queue.warning
demo.queue.critical
demo.queue.recovered
```

Đừng dùng:

```java
filter.enableType("demo.queue.*");
```

với ý nghĩ `*` là wildcard. `NotificationFilterSupport` kiểm tra tiền tố literal, không phải biểu thức chính quy. Nếu muốn **đúng duy nhất** `demo.queue.critical`, dùng một `NotificationFilter` so sánh chuỗi chính xác.

### 7.2. Filter theo userData

```java
NotificationFilter largeDepthOnly = event -> {
    if (!QueueMonitor.WARNING.equals(event.getType())) {
        return false;
    }
    return event.getUserData() instanceof Integer depth &&
        depth >= 80;
};
```

Code trên yêu cầu payload `userData` có kiểu `Integer` như hợp đồng của broadcaster. Với remote JMX, payload còn phải tương thích với cơ chế serialization và quyền truy cập class ở phía client. Không coi `userData` bất kỳ là dữ liệu đã được xác thực hoặc luôn có đúng kiểu.

## 8. Handback: ngữ cảnh do subscriber cung cấp

Giao diện `NotificationListener`:

```java
void handleNotification(
    Notification notification,
    Object handback
);
```

`handback` là đối tượng **bên đăng ký đặt vào registration**, sau đó JMX truyền lại cho listener khi callback chạy. Nó không phải payload của broadcaster.

Ví dụ:

```java
NotificationListener listener = (notification, handback) -> {
    System.out.printf(
        "channel=%s type=%s source=%s payload=%s%n",
        handback,
        notification.getType(),
        notification.getSource(),
        notification.getUserData()
    );
};
```

Khi registration có handback `"oncall"`, callback nhận chuỗi đó. Một listener khác có thể đăng ký với handback `"audit"` mà vẫn nhận cùng notification.

### 8.1. So sánh userData và handback

| Đặc điểm | `notification.getUserData()` | `handback` |
|---|---|---|
| Nguồn cung cấp | Broadcaster | Subscriber |
| Gắn với | Event cụ thể | Registration cụ thể |
| Có thể khác giữa hai listener cùng nhận event? | Thường giữ nguyên trên cùng event | Có |
| Mục đích chính | Chi tiết sự kiện | Ngữ cảnh xử lý/routing |
| Thay thế xác thực? | Không | Không |

Handback có thể là `null` và có thể là một đối tượng context bất biến. Không dùng handback để truyền mật khẩu, token hoặc tài nguyên nặng. Với listener local, giữ một context record nhỏ là cách thiết kế dễ hiểu.

```java
public record SubscriptionContext(
    String channel,
    String component
) {}
```

Trong remote connector, cách quản lý/cất giữ handback thuộc phía client/connector. Không mặc định rằng handback là dữ liệu được gửi tới server.

## 9. Mapped ObjectNames và nhiều registration

Một Spring `NotificationListenerBean` có thể được dùng cho nhiều ObjectName. Điều đó tạo các subscription ứng với nhiều broadcaster, với cùng listener/filter/handback theo cấu hình.

Ví dụ:

```text
QueueMonitor orders
  ObjectName = demo.queue:type=QueueMonitor,name=orders

QueueMonitor payments
  ObjectName = demo.queue:type=QueueMonitor,name=payments

NotificationListenerBean:
  mappedObjectNames = [orders, payments]
  filter = criticalOnly
  handback = "oncall"
```

Kết quả kỳ vọng:

- Notification WARNING từ orders: không đến listener nếu filter criticalOnly.
- Notification CRITICAL từ orders: callback nhận `handback="oncall"`.
- Notification CRITICAL từ payments: callback cũng nhận `handback="oncall"`.
- Notification CRITICAL từ một MBean khác không nằm trong mapped names: listener này không nhận từ mapping đó.

Vì handback giống nhau cho hai nguồn, callback cần đọc thêm `notification.getSource()` hoặc dùng ObjectName/ngữ cảnh phù hợp để xác định phát sinh từ orders hay payments.

Nếu cần handback khác nhau theo nguồn, có thể tạo **hai `NotificationListenerBean` registrations** sử dụng cùng listener delegate nhưng `mappedObjectNames` và handback riêng:

```text
Registration A:
  mappedObjectNames = [orders]
  handback = "orders-channel"

Registration B:
  mappedObjectNames = [payments]
  handback = "payments-channel"
```

Đây là trường hợp điển hình cho cấu hình nhiều registration thay vì cố nhét bảng ánh xạ tùy biến vào một handback duy nhất.

## 10. Ghép với MBeanExporter trong Spring

Spring `MBeanExporter` có thể quản lý việc export các bean và đăng ký notification listeners. Ví dụ cấu hình Java minh họa với các type rõ ràng:

```java
import java.lang.management.ManagementFactory;
import java.util.Map;
import javax.management.MBeanServer;
import javax.management.NotificationFilter;
import javax.management.NotificationListener;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.notification.NotificationListenerBean;

@Configuration
public class CompleteJmxConfiguration {

    @Bean
    public MBeanServer mbeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public QueueMonitor ordersQueueMonitor() {
        return new QueueMonitor();
    }

    @Bean
    public QueueMonitor paymentsQueueMonitor() {
        return new QueueMonitor();
    }

    @Bean
    public NotificationListener queueNotificationListener() {
        return (event, handback) ->
            System.out.printf(
                "[%s] type=%s source=%s depth=%s%n",
                handback,
                event.getType(),
                event.getSource(),
                event.getUserData()
            );
    }

    @Bean
    public NotificationFilter criticalFilter() {
        return event ->
            QueueMonitor.CRITICAL.equals(event.getType());
    }

    @Bean
    public NotificationListenerBean ordersCriticalRegistration(
            NotificationListener queueNotificationListener,
            NotificationFilter criticalFilter) {

        NotificationListenerBean listener =
            new NotificationListenerBean();

        listener.setNotificationListener(queueNotificationListener);
        listener.setMappedObjectNames(
            "demo.queue:type=QueueMonitor,name=orders"
        );
        listener.setNotificationFilter(criticalFilter);
        listener.setHandback("orders-oncall");
        return listener;
    }

    @Bean
    public NotificationListenerBean paymentsCriticalRegistration(
            NotificationListener queueNotificationListener,
            NotificationFilter criticalFilter) {

        NotificationListenerBean listener =
            new NotificationListenerBean();

        listener.setNotificationListener(queueNotificationListener);
        listener.setMappedObjectNames(
            "demo.queue:type=QueueMonitor,name=payments"
        );
        listener.setNotificationFilter(criticalFilter);
        listener.setHandback("payments-oncall");
        return listener;
    }

    @Bean
    public MBeanExporter mbeanExporter(
            MBeanServer mbeanServer,
            QueueMonitor ordersQueueMonitor,
            QueueMonitor paymentsQueueMonitor,
            NotificationListenerBean ordersCriticalRegistration,
            NotificationListenerBean paymentsCriticalRegistration) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(mbeanServer);
        exporter.setBeans(Map.of(
            "demo.queue:type=QueueMonitor,name=orders",
            ordersQueueMonitor,
            "demo.queue:type=QueueMonitor,name=payments",
            paymentsQueueMonitor
        ));
        exporter.setNotificationListeners(
            ordersCriticalRegistration,
            paymentsCriticalRegistration
        );
        return exporter;
    }
}
```

Cấu hình tạo một exporter, hai Standard MBean và hai registration mô tả listener, filter, handback. Mỗi registration chỉ theo dõi đúng một ObjectName để handback xác định nguồn ngữ cảnh.

**Chú ý khi chuyển thành dự án thật:** mọi interface/classes phải tồn tại trên classpath Spring Framework tương ứng; nếu dependency injection theo type bị mơ hồ vì nhiều bean cùng loại `QueueMonitor`, hãy dùng `@Qualifier` hoặc injection qua tên, như ví dụ đã phân biệt tên tham số. Nếu có nhiều `NotificationListenerBean` hoặc `NotificationFilter`, nên dùng qualifier rõ ràng thay vì dựa duy nhất vào tên biến.

Không bật thêm một exporter tự động khác cho cùng hai ObjectName nếu không thiết kế registration policy/ownership; điều đó có thể gây trùng MBean.

## 11. Gọi thử MBean sau khi Spring context refresh

Tạo lớp chạy lab:

```java
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Application {
    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(
                    CompleteJmxConfiguration.class
                )) {

            MBeanServer server = context.getBean(MBeanServer.class);

            ObjectName orders = new ObjectName(
                "demo.queue:type=QueueMonitor,name=orders"
            );
            ObjectName payments = new ObjectName(
                "demo.queue:type=QueueMonitor,name=payments"
            );

            System.out.println(
                "orders registered=" + server.isRegistered(orders)
            );
            System.out.println(
                "payments registered=" + server.isRegistered(payments)
            );

            QueueMonitor orderTarget =
                context.getBean("ordersQueueMonitor", QueueMonitor.class);
            QueueMonitor paymentTarget =
                context.getBean("paymentsQueueMonitor", QueueMonitor.class);

            orderTarget.updateDepth(50);
            orderTarget.updateDepth(75);
            orderTarget.updateDepth(95);
            paymentTarget.updateDepth(92);

            Thread.sleep(1_000L);
        }
    }
}
```

Kết quả logic mong muốn:

```text
orders registered=true
payments registered=true
[orders-oncall] type=demo.queue.critical ... depth=95
[payments-oncall] type=demo.queue.critical ... depth=92
```

Notification WARNING (depth=75) không đến những registration chỉ nhận CRITICAL. Nếu thêm một registration không filter cho orders, WARNING có thể đến registration đó.

**Không dựa vào thứ tự dòng callback như hợp đồng:** `NotificationBroadcasterSupport` có thể dispatch theo executor được cấu hình, connector và thời điểm nhận; nếu cần ordering rõ ràng, thiết kế riêng.

## 12. Phân biệt Spring NotificationListenerBean với JMX NotificationListener thuần

Trong Java JMX thuần, bạn đăng ký:

```java
server.addNotificationListener(
    objectName,
    listener,
    filter,
    handback
);
```

Spring thêm lớp cấu hình:

```java
NotificationListenerBean registration =
    new NotificationListenerBean();

registration.setNotificationListener(listener);
registration.setNotificationFilter(filter);
registration.setHandback(handback);
registration.setMappedObjectNames(objectName);

exporter.setNotificationListeners(registration);
```

Về nguyên tắc, cả hai cuối cùng cần tạo registration trên MBeanServer. Spring giúp ràng buộc registration vào cấu hình bean và vòng đời exporter.

Nhưng Spring không thay đổi ý nghĩa của filter/handback trong hợp đồng JMX. Nếu filter trả `false`, notification không được chuyển đến registration đó. Nếu handback là `null`, callback nhận null. Nếu MBean không broadcaster, registration không tự tạo khả năng phát.

## 13. Điều gì xảy ra khi không cấu hình mappedObjectNames?

`NotificationListenerBean` hỗ trợ mapping để liên kết với những MBean cụ thể. Khi không đặt mapped ObjectNames, hành vi có thể phụ thuộc vào cách `MBeanExporter` xử lý listener configuration và version Spring, bao gồm trường hợp listener được gắn với các MBean do exporter quản lý.

Vì vậy, để tạo bài học có kết quả dự đoán được, **hãy chỉ định ObjectName tường minh** cho các MBean cần theo dõi. Tránh dựa vào giả định listener sẽ tự subscribe mọi MBean trong toàn platform server.

Nếu mục tiêu là nghe một nhóm MBean theo domain/pattern, cần kiểm tra liệu version/configuration hỗ trợ pattern expansion như mong muốn hay không; một ObjectName pattern không tự có nghĩa registration sẽ tự cập nhật khi MBean mới xuất hiện sau đó.

Một danh sách explicit thường an toàn và dễ kiểm kê hơn.

## 14. Phân biệt mapping với filter theo source

Giả sử hai notification có cùng `type`:

```text
demo.queue.critical từ orders
demo.queue.critical từ payments
```

Có thể:

- Dùng mapped ObjectNames chỉ chứa orders, filter chỉ `critical`.
- Dùng mapped ObjectNames chứa cả hai, filter phân nhánh thêm theo source.
- Dùng hai registration với handback khác nhau.

Chiến lược đầu tiên đơn giản khi chỉ có một nguồn cần nghe. Chiến lược thứ ba thuận tiện khi cùng logic xử lý nhưng cần routing khác nhau.

**Filter theo source không hoàn toàn thay thế mapped ObjectNames.** Nếu listener đăng ký với quá nhiều broadcaster rồi loại phần lớn event sau đó, cấu hình vẫn có thêm registration không cần thiết. Chọn đúng nguồn trước, lọc event sau.

Tương tự, mapped ObjectNames không thay thế `NotificationFilter`: một MBean có thể phát WARNING/CRITICAL/RECOVERED và listener có thể chỉ cần CRITICAL.

## 15. Một listener được đăng ký nhiều lần và nguy cơ xử lý trùng

Một listener instance có thể được đăng ký nhiều lần với cùng MBean, ví dụ:

```text
Registration A:
  ObjectName = orders
  Filter = demo.queue.
  Handback = dashboard

Registration B:
  ObjectName = orders
  Filter = demo.queue.critical
  Handback = pager
```

Khi orders phát CRITICAL, event có thể khớp cả hai. Callback có thể chạy **hai lần** với cùng notification nhưng handback khác:

```text
handleNotification(event #42, "dashboard")
handleNotification(event #42, "pager")
```

Đây không nhất thiết là broadcaster phát trùng; đó có thể là hai subscription hợp lệ.

Nếu downstream cần bảo đảm không xử lý cùng một sự kiện hai lần, cần thiết kế idempotency hoặc một event ID ứng dụng. Chỉ dùng sequenceNumber đơn lẻ không đủ trong hệ thống nhiều nguồn hoặc sau restart.

## 16. Lọc notification an toàn, nhanh và dễ đoán

Một filter thường chạy trong quá trình dispatch notification. Nó nên:

- Kiểm tra loại và payload được định nghĩa rõ.
- Trả `boolean` nhanh.
- Không gọi database/remote service.
- Không thay đổi trạng thái nghiệp vụ.
- Không log payload nhạy cảm.
- Chịu được notification null hoặc userData không mong đợi khi cần.

Ví dụ filter có validation kiểu:

```java
NotificationFilter criticalWithDepth = event -> {
    if (event == null || !QueueMonitor.CRITICAL.equals(
            event.getType())) {
        return false;
    }

    Object data = event.getUserData();
    return data instanceof Integer depth && depth >= 90;
};
```

Listener callback cũng nên ngắn và chuyển tác vụ nặng sang queue/executor có kiểm soát. Không mặc định mọi callback luôn chạy trên một thread riêng; broadcaster hoặc connector quyết định cách dispatch.

Với production, nếu event rate cao, cần giới hạn, aggregation hoặc deduplication trước khi gửi cảnh báo. Nếu không, một MBean tạo rất nhiều notification có thể làm listener và logging pipeline quá tải.

## 17. Lifecycle: startup, unregister và shutdown

Một subscription hoạt động phụ thuộc nhiều mốc:

```text
Spring context starts
    |
    +--> QueueMonitor beans được tạo
    +--> MBeanExporter đăng ký ObjectNames
    +--> exporter thiết lập NotificationListenerBeans
    |
    +--> nguồn phát notification
    |        |
    |        +--> filter
    |                |
    |                +--> listener callback(handback)
    |
Spring context closes
    |
    +--> exporter gỡ registrations do mình quản lý
    +--> MBean registration được cleanup theo lifecycle
```

Có những tình huống cần xử lý:

1. Source MBean chưa được đăng ký khi listener cố subscribe.
2. ObjectName sai, khác domain hoặc property.
3. Exporter trỏ vào MBeanServer khác với nơi source được đăng ký.
4. Hai context cùng dùng ObjectName và registration policy tạo kết quả khác dự kiến.
5. Source unregister/re-register khiến subscription cũ không còn ý nghĩa.
6. Context đóng nhưng callback đã được dispatch vẫn còn đang chạy.
7. Notification phát quá sớm, trước khi listener được gắn.
8. Spring bean listener tồn tại nhưng chưa được cấu hình vào exporter.

Không giả định JMX lưu backlog để gửi lại những notification phát trước khi subscription thành công. Nếu một event quan trọng cần được truy xuất sau startup, cung cấp trạng thái hiện tại bằng attribute hoặc event store riêng.

## 18. Kiểm tra metadata và registration từ MBeanServer

Để xác nhận source có khả năng phát notification:

```java
import javax.management.MBeanInfo;
import javax.management.MBeanNotificationInfo;

MBeanInfo info = server.getMBeanInfo(orders);

for (MBeanNotificationInfo notificationInfo :
        info.getNotifications()) {
    System.out.println(
        "Notification class=" + notificationInfo.getName()
    );
    for (String type : notificationInfo.getNotifTypes()) {
        System.out.println("  type=" + type);
    }
}
```

`MBeanInfo.getNotifications()` cho biết metadata nguồn công bố. Nhưng metadata không bảo đảm notification sẽ được phát trong thời gian quan sát; điều đó phụ thuộc sự kiện thực tế và logic `sendNotification`.

Kiểm tra source tồn tại:

```java
System.out.println(server.isRegistered(orders));
```

Sau đó tạo event thử trong môi trường lab bằng operation `updateDepth`. Nếu callback không chạy, kiểm tra từng khâu theo thứ tự:

```text
MBean đã đăng ký?
  -> Có phát notification?
  -> Listener registration đã được exporter tạo?
  -> Mapped ObjectName khớp?
  -> Filter trả true?
  -> Callback có exception?
```

Không sửa bừa nhiều cấu hình cùng lúc khi chưa biết event bị chặn ở bước nào.

## 19. Spring XML configuration (khi dự án cũ dùng XML)

Trong ứng dụng Spring truyền thống sử dụng XML, các thông số tương tự có thể được đưa qua bean property:

```xml
<bean id="notificationListener"
      class="com.example.jmx.LoggingNotificationListener"/>

<bean id="criticalFilter"
      class="javax.management.NotificationFilterSupport">
    <property name="enabledTypes">
        <!-- Chỉ minh họa cấu trúc; trong thực tế dùng
             phương thức hỗ trợ enableType hoặc filter custom. -->
    </property>
</bean>
```

Với `NotificationListenerBean`, các property quan trọng là `notificationListener`, `notificationFilter`, `handback` và `mappedObjectNames`. Với `MBeanExporter`, property `notificationListeners` liên kết các registration.

Nếu cần XML hoàn chỉnh, nên dựa vào schema, phiên bản Spring và cách cấu hình đúng `NotificationFilterSupport` (vì `enableType` là method thay đổi state, không phải một JavaBeans setter `enabledTypes`). Trong dự án mới, cấu hình Java `@Bean` thường rõ ràng hơn cho việc tạo filter và mapping.

## 20. Spring Boot integration

Spring Boot có khả năng auto-configuration cho JMX export tùy `spring.jmx.enabled` và các điều kiện khác. Nhưng **bật JMX export không tự động làm mọi notification listener bean được đăng ký theo ý muốn**. Cần bảo đảm registration được liên kết với exporter thực sự hoạt động trong context.

Nếu đã có một exporter do Boot/Spring tạo, tạo exporter mới thủ công có thể làm cùng bean được export hai lần hoặc gây trùng ObjectName. Với hệ thống Boot, nên kiểm kê exporter beans trước, xác định ownership và chọn một chiến lược nhất quán.

Phân biệt:

- Spring `ApplicationEvent`: sự kiện trong application context.
- Spring JMX `NotificationListenerBean`: cấu hình JMX listener registration.
- JMX `Notification`: đối tượng sự kiện do MBean phát.
- Spring Boot Actuator: tập endpoint quản trị/giám sát, không đồng nghĩa mọi endpoint phát JMX notifications.

Nếu muốn chuyển notification thành ApplicationEvent, cần một adapter explicit; JMX không tự động đưa các notification vào Spring event bus.

## 21. An toàn dữ liệu và quyền quản trị

JMX notification có thể bị thu thập bởi local hoặc remote clients. Không gửi secret, token, request body hoặc dữ liệu cá nhân vào `notification.getMessage()` hay `notification.getUserData()` chỉ vì chúng tiện để debug.

Handback có thể chứa object từ client, nhưng không nên dùng làm kênh giữ credential nhạy cảm hoặc thay thế authorization. Nếu listener dùng handback để routing cảnh báo, validate context type và giữ nó bất biến khi có thể.

Remote JMX cần:

- Authentication và phân quyền phù hợp.
- TLS hoặc kênh bảo vệ đáng tin cậy.
- Giới hạn mạng quản trị.
- Không mở RMI/JMX port công khai.
- Audit operation có tác dụng phụ.
- Xử lý reconnect, event loss và subscription lifecycle.
- Không tự suy ra notification là message queue bền vững.

Với một sự kiện quan trọng như sự cố thanh toán, nên phát notification chứa trạng thái tổng hợp và correlation ID không nhạy cảm; chi tiết nghiệp vụ cần lưu trong hệ thống thích hợp.

## 22. Lỗi thường gặp

### 22.1. Bean listener có trong Spring nhưng không nhận event

Bạn tạo `NotificationListenerBean` nhưng quên gắn vào `MBeanExporter`. Sửa cấu hình liên kết và kiểm tra exporter đã khởi tạo.

### 22.2. Mapping sai ObjectName

Nguồn đăng ký `demo.queue:type=QueueMonitor,name=orders`, nhưng mapped name viết `demo.queues:type=QueueMonitor,name=orders`. Chỉ cần khác domain hoặc key property là listener không theo dõi đúng nguồn. Dùng `MBeanServer.queryNames` để xác nhận tên thật.

### 22.3. FilterSupport dùng regex sai

`enableType("demo.queue.*")` không là wildcard. Dùng `enableType("demo.queue.")` để nhận theo tiền tố hoặc custom filter so khớp chính xác.

### 22.4. Nhầm handback với userData

`userData` đến từ broadcaster trong từng event; `handback` đến từ subscriber ở thời điểm đăng ký. Nếu cần biết event có queueDepth bao nhiêu, đọc payload; nếu cần biết subscription thuộc channel nào, đọc handback.

### 22.5. Cùng listener callback hai lần

Có thể do hai registration chồng nhau, không nhất thiết do broadcaster phát trùng. Liệt kê nguồn/filter/handback từng subscription để xác định.

### 22.6. Đã đăng ký listener nhưng MBean không phát

MBean cần thực sự là notification broadcaster và gọi `sendNotification`. Override metadata `getNotificationInfo` chưa đủ.

### 22.7. Event phát trước lúc listener đăng ký

JMX không bảo đảm replay thông báo cũ. Nếu client cần biết trạng thái đang là CRITICAL, hãy đọc attribute sau khi đăng ký hoặc có cơ chế đồng bộ state.

### 22.8. Callback ném exception làm mất hành vi mong đợi

Bảo vệ listener, logging có kiểm soát và chuyển việc nặng sang nơi xử lý riêng. Không giả định exception của listener sẽ được retry.

### 22.9. Exporter không cùng MBeanServer với source

Trong một JVM có thể có nhiều MBeanServer. Nếu source đăng ký ở A nhưng listener registration thực hiện trên B, tên giống nhau cũng không giúp subscription hoạt động.

## 23. Thực hành theo kịch bản

**Bài 1 — Chỉ nhận critical từ orders.** Đăng ký listener với `mappedObjectNames` chỉ chứa orders, filter chỉ nhận `demo.queue.critical`, handback `"orders-oncall"`. Phát WARNING và CRITICAL để so sánh.

**Bài 2 — Hai source, một listener.** Map orders và payments tới cùng listener, dùng chung filter critical. Quan sát `notification.getSource()` để phân biệt nguồn, vì handback giống nhau.

**Bài 3 — Hai handback khác nhau.** Tạo hai `NotificationListenerBean` riêng cho orders/payments cùng delegate; gán `"orders-channel"` và `"payments-channel"`. Chứng minh callback nhận handback theo registration.

**Bài 4 — FilterSupport prefix.** Dùng `enableType("demo.queue.")` và phát các type `demo.queue.warning`, `demo.queue.critical`, `demo.cache.evicted`. Ghi nhận loại được nhận và giải thích prefix matching.

**Bài 5 — Trùng registration.** Tạo hai registration cùng map orders nhưng filter chồng nhau. Phát CRITICAL và giải thích vì sao callback hai lần có thể hợp lệ.

**Bài 6 — Lỗi lifecycle.** Phát event trước khi Spring exporter hoàn thành registration; sau đó phát lại. Giải thích vì sao event đầu không được replay tự động.

**Bài 7 — Metadata.** Dùng `MBeanServer.getMBeanInfo` để liệt kê notification types của `QueueMonitor`; đối chiếu với filter của client.

**Bài 8 — Đóng context.** Dùng `try-with-resources` cho `AnnotationConfigApplicationContext`, phát event trước và sau cleanup trong một lab có quản lý nguồn phù hợp. Quan sát rằng listener registration có lifecycle và không nên tiếp tục nhận event khi exporter đã đóng.

## 24. Câu hỏi tự kiểm tra

1. `mappedObjectNames` của `NotificationListenerBean` quyết định điều gì?
2. `NotificationFilter` khác mapping nguồn như thế nào?
3. `NotificationFilterSupport.enableType` hoạt động theo tiền tố hay regex?
4. `handback` do broadcaster hay subscriber cung cấp?
5. `handback` và `userData` có thể khác nhau ra sao?
6. Một listener được đăng ký hai lần với cùng source có thể nhận cùng notification hai lần không?
7. Vì sao `NotificationListenerBean` tồn tại trong context nhưng không chắc callback chạy?
8. Nếu MBean không dùng `sendNotification`, metadata notification có đủ làm listener nhận event không?
9. Vì sao phải kiểm tra ObjectName thực tế thay vì suy đoán từ Spring bean name?
10. JMX notification có replay sau disconnect hoặc sau khi listener đăng ký muộn không?
11. Khi nào nên tạo hai registration riêng để có hai handback?
12. Những rủi ro nào phát sinh nếu notification payload chứa secret?

## 25. Ghi nhớ

Trong Spring Framework JMX, **`NotificationListenerBean` gom một listener, filter, handback và tập mapped ObjectNames để exporter đăng ký subscription có chủ đích**. ObjectName quyết định nguồn phát cần nghe; filter quyết định notification nào đi tới callback; handback mang ngữ cảnh do bên đăng ký định nghĩa.

Để cấu hình hoạt động, MBean phải có khả năng phát notification, exporter phải tạo registration trên đúng MBeanServer và ObjectName phải khớp. Hãy giữ filter nhanh, callback an toàn, loại bỏ payload nhạy cảm, quản lý lifecycle và xác minh bằng sự kiện thử cũng như `MBeanInfo`. Khi cần giao nhận bền vững, không dùng JMX notification thay cho event broker.
