# Đăng ký một listener cho một MBean cụ thể trong Spring Framework JMX

## Mục tiêu bài học

Sau bài học này, bạn có thể:

- Hiểu mô hình **Notification broadcaster**, **Notification listener** và **MBeanServer** trong Java Management Extensions (JMX).
- Phân biệt đăng ký listener cho **một ObjectName cụ thể** với nghe notification từ nhiều MBeans.
- Sử dụng **Spring MBeanExporter** và **NotificationListenerBean** để gắn listener vào đúng MBean.
- Đăng ký listener trực tiếp qua **MBeanServer.addNotificationListener(...)**, dùng filter và handback khi cần.
- Hiểu vòng đời listener, cách hủy đăng ký, trách nhiệm cleanup và rủi ro của việc đăng ký trùng.
- Kiểm tra notification từ đúng nguồn, tránh nhầm ObjectName, sai MBeanServer hoặc kết nối tới JVM khác.
- Thiết kế callback ngắn gọn, có xử lý lỗi và bảo mật phù hợp.

## 1. Vì sao phải đăng ký listener theo một MBean?

Trong JMX, một MBean có thể phát **Notification** khi trạng thái quản trị thay đổi. Ví dụ:

- Cache được xóa.
- Queue vượt ngưỡng backlog.
- Scheduler chuyển trạng thái sang paused.
- Một tài nguyên báo sự kiện lỗi hoặc recovery.
- JVM hoặc thư viện phát sự kiện vận hành từ các MBeans có hỗ trợ.

Một Spring application có thể có nhiều MBeans. Nếu chỉ quan tâm queue chính, listener không nên nhận mọi sự kiện của mọi resource.

Ví dụ các ObjectNames:

\`\`\`text
learning.jmx:type=Queue,name=Primary
learning.jmx:type=Queue,name=Secondary
learning.jmx:type=Cache,name=Products
\`\`\`

Nếu mục tiêu là nghe notification của queue Primary, cần gắn listener tới đúng ObjectName:

\`\`\`text
learning.jmx:type=Queue,name=Primary
\`\`\`

Sơ đồ:

\`\`\`text
MBeanServer
  |
  +-- Queue Primary (NotificationBroadcaster)
  |       |
  |       +----> QueuePrimaryListener
  |
  +-- Queue Secondary
  |       |
  |       +----> listener khác (nếu có)
  |
  +-- Cache Products
\`\`\`

**Điểm cốt lõi:** Đăng ký listener cho một MBean là lựa chọn **đối tượng phát** theo ObjectName. Sau đó mới có thể dùng filter để chọn **loại notification** cần nhận từ đối tượng đó.

## 2. Các thành phần trong mô hình JMX notification

| Thành phần | Vai trò |
|---|---|
| MBean | Resource quản trị được đăng ký với ObjectName |
| NotificationBroadcaster | Giao diện broadcaster có thể đăng ký/xóa listener |
| NotificationBroadcasterSupport | Lớp tiện ích giúp phát notification |
| Notification | Object mang type, source, sequence number, timestamp, message |
| NotificationListener | Callback nhận Notification |
| NotificationFilter | Quy tắc chấp nhận/từ chối từng notification |
| Handback | Context riêng được truyền lại cho listener khi nhận sự kiện |
| MBeanServer | Điểm đăng ký MBeans và listener theo ObjectName |
| Spring NotificationListenerBean | Bean cấu hình một listener cùng tập MBeans cần lắng nghe |
| Spring MBeanExporter | Thành phần export MBeans và phối hợp listener theo cấu hình |

Có hai tầng cần phân biệt:

1. **Registration của MBean:** ObjectName phải tồn tại trong MBeanServer.
2. **Registration của listener:** Listener được gắn với MBean đó để nhận những notification do nó phát.

Một Spring bean có annotation JMX không mặc nhiên là broadcaster. MBean phải hỗ trợ notification và thực sự phát notification; nếu không, listener sẽ không có sự kiện để nhận.

## 3. ObjectName là địa chỉ định danh của MBean

Ví dụ:

\`\`\`java
ObjectName queueName = new ObjectName(
    "learning.jmx:type=Queue,name=Primary"
);
\`\`\`

ObjectName gồm domain và key properties. Nó không phải network URL; một client trong JVM khác vẫn cần JMX connector phù hợp để truy cập MBeanServer đích.

ObjectName là định danh **bên trong một MBeanServer**. Nếu cùng tên xuất hiện trong hai JVM, đó vẫn có thể là hai MBeans độc lập.

Khi cấu hình listener, cần biết:

- MBean nằm trong **MBeanServer nào**?
- ObjectName có chính xác không?
- MBean có hỗ trợ **NotificationBroadcaster/NotificationEmitter** không?
- Listener đăng ký **trước hay sau** thời điểm notification được phát?

Đăng ký listener sau khi sự kiện đã được gửi thường không giúp bạn nhận lại sự kiện đó; JMX Notification không mặc định là durable event log có replay.

## 4. Tạo một Standard MBean phát notification

Ví dụ dùng QueueMonitor với hai loại notification:

\`\`\`text
learning.queue.overloaded
learning.queue.recovered
\`\`\`

### 4.1. MBean interface

Tệp QueueMonitorMBean.java:

\`\`\`java
package example.jmx;

public interface QueueMonitorMBean {
    int getDepth();
    boolean isOverloaded();
    void updateDepth(int depth);
}
\`\`\`

### 4.2. Implementation phát notification

Tệp QueueMonitor.java:

\`\`\`java
package example.jmx;

import java.util.concurrent.atomic.AtomicLong;

import javax.management.MBeanNotificationInfo;
import javax.management.Notification;
import javax.management.NotificationBroadcasterSupport;

public class QueueMonitor extends NotificationBroadcasterSupport
        implements QueueMonitorMBean {

    public static final String TYPE_OVERLOADED =
            "learning.queue.overloaded";

    public static final String TYPE_RECOVERED =
            "learning.queue.recovered";

    private static final int THRESHOLD = 100;
    private final AtomicLong sequence = new AtomicLong();

    private int depth;
    private boolean overloaded;

    @Override
    public synchronized int getDepth() {
        return depth;
    }

    @Override
    public synchronized boolean isOverloaded() {
        return overloaded;
    }

    @Override
    public synchronized void updateDepth(int depth) {
        if (depth < 0) {
            throw new IllegalArgumentException("depth must be >= 0");
        }

        this.depth = depth;
        boolean next = depth > THRESHOLD;

        if (next == overloaded) {
            return;
        }

        overloaded = next;

        String type = overloaded
                ? TYPE_OVERLOADED
                : TYPE_RECOVERED;

        Notification notification = new Notification(
                type,
                this,
                sequence.incrementAndGet(),
                System.currentTimeMillis(),
                overloaded ? "Queue overloaded" : "Queue recovered"
        );

        notification.setUserData(depth);
        sendNotification(notification);
    }

    @Override
    public MBeanNotificationInfo[] getNotificationInfo() {
        return new MBeanNotificationInfo[] {
            new MBeanNotificationInfo(
                new String[] { TYPE_OVERLOADED, TYPE_RECOVERED },
                Notification.class.getName(),
                "Queue overload/recovery notifications"
            )
        };
    }
}
\`\`\`

Giải thích:

- QueueMonitor implements QueueMonitorMBean theo Standard MBean convention.
- NotificationBroadcasterSupport giúp quản lý listeners và phát notification.
- updateDepth chỉ phát notification khi trạng thái overload thay đổi.
- sequenceNumber tăng bằng AtomicLong.
- type mô tả tình huống overload hoặc recovery.
- userData chứa depth để listener dùng khi cần.

Ví dụ này minh họa notification; trong production, độ sâu queue thường được cập nhật từ thành phần xử lý thật. Không nên cung cấp operation thay đổi state chỉ để phục vụ monitoring nếu nó mở ra hành vi quản trị không cần thiết.

## 5. Đăng ký listener trực tiếp qua MBeanServer

Java JMX có phương thức:

\`\`\`java
server.addNotificationListener(
    objectName,
    listener,
    filter,
    handback
);
\`\`\`

Trong đó:

- objectName là tên MBean cần nghe.
- listener là callback xử lý notification.
- filter chọn những notification được chấp nhận.
- handback là object context được trả lại cho callback, không phải một event payload do broadcaster kiểm soát.

Ví dụ chỉ nghe queue Primary:

\`\`\`java
package example.jmx;

import java.lang.management.ManagementFactory;

import javax.management.MBeanServer;
import javax.management.NotificationListener;
import javax.management.ObjectName;

public class DirectListenerDemo {

    public static void main(String[] args) throws Exception {
        MBeanServer server =
                ManagementFactory.getPlatformMBeanServer();

        ObjectName primaryName = new ObjectName(
            "learning.jmx:type=Queue,name=Primary"
        );

        QueueMonitor primary = new QueueMonitor();
        server.registerMBean(primary, primaryName);

        NotificationListener listener = (notification, handback) -> {
            System.out.println(
                "type=" + notification.getType()
                + ", source=" + notification.getSource()
                + ", seq=" + notification.getSequenceNumber()
                + ", handback=" + handback
            );
        };

        server.addNotificationListener(
            primaryName,
            listener,
            null,
            "primary-queue-listener"
        );

        try {
            primary.updateDepth(120);
            primary.updateDepth(50);
        } finally {
            server.removeNotificationListener(primaryName, listener);
            server.unregisterMBean(primaryName);
        }
    }
}
\`\`\`

Điểm đáng chú ý:

- Listener đăng ký với **primaryName** chứ không đăng ký ở tên Queue Secondary.
- \`null\` filter cho phép nhận mọi notification mà broadcaster phát.
- Handback là chuỗi tĩnh do người đăng ký truyền; callback nhận lại nó ở tham số thứ hai.
- Dùng try/finally để hủy listener và MBean khi kết thúc.

### Vì sao phải unregister listener?

Nếu MBean hoặc MBeanServer tồn tại lâu, listener không được gỡ có thể tiếp tục nhận sự kiện, giữ tham chiếu tới các object khác và làm callback chạy sau thời điểm module không còn hoạt động.

Đặc biệt trong integration tests hoặc ứng dụng có nhiều ApplicationContext, việc không cleanup có thể gây listener trùng hoặc giữ reference không mong muốn.

## 6. Lọc notification type trên đúng MBean

Chọn MBean bằng ObjectName chưa đủ nếu broadcaster phát nhiều loại notification.

Ví dụ chỉ nhận overload:

\`\`\`java
import javax.management.NotificationFilterSupport;

NotificationFilterSupport filter =
        new NotificationFilterSupport();

filter.enableType(QueueMonitor.TYPE_OVERLOADED);

server.addNotificationListener(
    primaryName,
    listener,
    filter,
    null
);
\`\`\`

**Lưu ý:** NotificationFilterSupport dùng **prefix matching**. Nếu bật \`learning.queue\`, nó có thể nhận cả overload lẫn recovered vì cả hai có prefix giống nhau.

Nếu muốn so khớp đúng một type:

\`\`\`java
import javax.management.NotificationFilter;

NotificationFilter exactType =
    notification -> QueueMonitor.TYPE_OVERLOADED.equals(
        notification.getType()
    );
\`\`\`

Hai tầng lọc:

\`\`\`text
ObjectName
  -> chỉ nhận thông báo từ MBean được chọn

NotificationFilter
  -> chỉ nhận một số type từ broadcaster đó
\`\`\`

Không thay filter bằng cách kiểm tra message string; message thường dành cho người đọc, có thể thay đổi mà không đổi event type contract.

## 7. Cấu hình listener theo Spring Framework

Spring JMX hỗ trợ **NotificationListenerBean**, cho phép gắn một NotificationListener với một hoặc nhiều MBeans đã đăng ký.

Thông thường bạn có thể cấu hình:

- \`notificationListener\`: callback Java.
- \`mappedObjectNames\`: tập ObjectName của MBeans cần nghe.
- \`notificationFilter\`: filter nếu cần.
- \`handback\`: context do người đăng ký cung cấp.

Ví dụ cấu hình một Spring listener cho **một MBean cụ thể**:

\`\`\`java
package example.jmx;

import java.lang.management.ManagementFactory;
import java.util.Map;

import javax.management.MBeanServer;
import javax.management.NotificationListener;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.NotificationListenerBean;

@Configuration
public class QueueJmxConfiguration {

    @Bean
    public QueueMonitor queueMonitor() {
        return new QueueMonitor();
    }

    @Bean
    public NotificationListener queueNotificationListener() {
        return (notification, handback) -> {
            System.out.println(
                "Queue event: " + notification.getType()
            );
        };
    }

    @Bean
    public MBeanExporter mbeanExporter(
            QueueMonitor monitor,
            NotificationListener queueNotificationListener) {

        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(server);

        exporter.setBeans(Map.of(
            "learning.jmx:type=Queue,name=Primary",
            monitor
        ));

        NotificationListenerBean listenerBean =
            new NotificationListenerBean();

        listenerBean.setNotificationListener(
            queueNotificationListener
        );

        listenerBean.setMappedObjectNames(
            "learning.jmx:type=Queue,name=Primary"
        );

        exporter.setNotificationListeners(
            new NotificationListenerBean[] { listenerBean }
        );

        return exporter;
    }
}
\`\`\`

Ở đây:

1. Spring tạo QueueMonitor.
2. Spring tạo QueueNotificationListener.
3. MBeanExporter đăng ký QueueMonitor dưới ObjectName Primary.
4. Exporter thiết lập listener tới ObjectName đó.
5. Khi broadcaster phát notification, callback được gọi.

**Quan trọng:** mappedObjectNames xác định chính xác MBean cần nghe. Nếu bỏ mappedObjectNames theo cách exporter hiểu là áp dụng rộng, listener có thể được gắn với nhiều MBeans do exporter quản lý. Vì mục tiêu của bài là nghe một MBean cụ thể, hãy đặt mappedObjectNames rõ ràng.

Spring JMX có thể cấu hình NotificationListenerBean bằng các dạng ObjectName hoặc chuỗi ObjectName hợp lệ theo API setter tương ứng. Nếu triển khai một phiên bản Spring cụ thể, kiểm tra đúng chữ ký setter của phiên bản đó.

## 8. Lưu ý về bean name và ObjectName

Giả sử Spring bean có tên:

\`\`\`text
queueMonitor
\`\`\`

Nhưng MBeanExporter đăng ký dưới:

\`\`\`text
learning.jmx:type=Queue,name=Primary
\`\`\`

Khi cấu hình mappedObjectNames, bạn đang chọn **JMX ObjectName**, không phải chỉ một tên Spring bean tùy ý.

Nếu naming strategy biến bean name thành ObjectName theo quy tắc khác, bạn cần lấy **ObjectName thực tế** sau export để cấu hình listener đúng.

Một cách xác minh:

\`\`\`java
ObjectName name = new ObjectName(
    "learning.jmx:type=Queue,name=Primary"
);

System.out.println(server.isRegistered(name));
\`\`\`

Nếu false, cần xem exporter, server và naming strategy trước khi kết luận listener bị lỗi.

## 9. Cấu hình filter và handback trong Spring

Bạn có thể tạo một filter:

\`\`\`java
@Bean
public NotificationFilter queueOverloadFilter() {
    return notification ->
        QueueMonitor.TYPE_OVERLOADED.equals(
            notification.getType()
        );
}
\`\`\`

Và cấu hình listener bean:

\`\`\`java
NotificationListenerBean listenerBean =
    new NotificationListenerBean();

listenerBean.setNotificationListener(queueNotificationListener);
listenerBean.setMappedObjectNames(
    "learning.jmx:type=Queue,name=Primary"
);
listenerBean.setNotificationFilter(queueOverloadFilter);
listenerBean.setHandback("queue-primary");
\`\`\`

Khi callback nhận event:

\`\`\`java
NotificationListener listener = (notification, handback) -> {
    System.out.println("Type = " + notification.getType());
    System.out.println("Context = " + handback);
};
\`\`\`

### Handback dùng để làm gì?

Handback có ích khi một listener xử lý nhiều registrations và muốn biết context được gắn lúc đăng ký, ví dụ tenant hoặc một logical label.

Nhưng handback không thay thế nguồn event, ObjectName hoặc security identity. Trong môi trường remote, phải xem khả năng truyền object và semantics của connector. Không đưa secret vào handback hoặc dùng handback như cơ chế xác thực.

## 10. Lắng nghe một MBean khi ứng dụng có nhiều queues

Giả sử exporter đăng ký:

\`\`\`text
learning.jmx:type=Queue,name=Primary
learning.jmx:type=Queue,name=Secondary
\`\`\`

Bạn muốn listener chỉ nhận Primary:

\`\`\`java
listenerBean.setMappedObjectNames(
    "learning.jmx:type=Queue,name=Primary"
);
\`\`\`

Khi Primary phát notification, listener nhận. Khi Secondary phát, listener đó không được gắn vào Secondary nên không nhận thông báo từ nó qua registration này.

Nếu muốn nghe cả hai, hãy cấu hình danh sách ObjectNames rõ ràng, hoặc dùng những listener beans riêng khi chúng có trách nhiệm xử lý khác nhau.

**Không nên dùng ObjectName pattern như một cách đăng ký listener tự động cho mọi MBean tương lai** nếu API bạn đang dùng yêu cầu tên cụ thể. JMX queryNames có thể nhận ObjectName pattern để truy vấn, nhưng addNotificationListener yêu cầu MBean tồn tại theo tên được đăng ký.

Một hệ thống tự khám phá MBeans động cần cơ chế phát hiện và đăng ký listener khi MBean mới xuất hiện, kèm cleanup khi MBean bị unregister.

## 11. Vòng đời: startup, shutdown và đăng ký trùng

Listener cần được đăng ký khi:

1. MBean đã được đăng ký vào MBeanServer.
2. Listener đã được tạo và sẵn sàng xử lý.
3. Filter/handback được cấu hình.

Với MBeanExporter do Spring quản lý, cấu hình notification listeners có thể được exporter phối hợp với vòng đời export. Khi context đóng, exporter thực hiện cleanup cho các registrations nó quản lý.

### Vì sao không tự add listener thêm lần nữa?

Nếu bạn vừa cấu hình NotificationListenerBean trong exporter, vừa gọi:

\`\`\`java
server.addNotificationListener(name, sameListener, null, null);
\`\`\`

thì có thể tồn tại nhiều registrations cho cùng callback, dẫn đến sự kiện được xử lý lặp. Hãy chọn một cơ chế ownership rõ ràng.

### Với đăng ký thủ công

Nếu tự gọi addNotificationListener, cần tự gọi removeNotificationListener trong lifecycle callback tương ứng.

Ví dụ:

\`\`\`java
public void stop() throws Exception {
    server.removeNotificationListener(objectName, listener);
}
\`\`\`

Nên bắt riêng tình huống MBean đã bị unregister hoặc listener chưa đăng ký thay vì làm shutdown thất bại toàn bộ.

## 12. Thử nghiệm end-to-end với Spring

Một chương trình đơn giản tạo context rồi kích hoạt notification:

\`\`\`java
package example.jmx;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class SpringNotificationDemo {

    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(
                    QueueJmxConfiguration.class)) {

            QueueMonitor monitor =
                context.getBean(QueueMonitor.class);

            monitor.updateDepth(150);
            monitor.updateDepth(60);
        }
    }
}
\`\`\`

Nếu listener không có filter, callback dự kiến được gọi hai lần:

\`\`\`text
Queue event: learning.queue.overloaded
Queue event: learning.queue.recovered
\`\`\`

Nếu dùng filter chỉ overload, callback dự kiến được gọi một lần.

Khi thực hiện trong dự án, không nên dựa vào exact timestamp/source string vì các giá trị động có thể khác. Hãy tập trung vào event type, sequence, count và việc listener được gắn đúng ObjectName.

## 13. Integration test: đúng MBean, đúng notification

Một test có ý nghĩa nên tạo hai MBeans và một listener chỉ cho Primary.

Ví dụ JUnit 5 ở mức minh họa:

\`\`\`java
import static org.junit.jupiter.api.Assertions.*;

import java.lang.management.ManagementFactory;
import java.util.concurrent.atomic.AtomicInteger;

import javax.management.MBeanServer;
import javax.management.NotificationListener;
import javax.management.ObjectName;

import org.junit.jupiter.api.Test;

class SpecificMBeanListenerTest {

    @Test
    void listenerReceivesOnlyPrimaryQueueEvents() throws Exception {
        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        ObjectName primaryName = new ObjectName(
            "learning.jmx:type=Queue,name=Primary"
        );
        ObjectName secondaryName = new ObjectName(
            "learning.jmx:type=Queue,name=Secondary"
        );

        QueueMonitor primary = new QueueMonitor();
        QueueMonitor secondary = new QueueMonitor();

        server.registerMBean(primary, primaryName);
        server.registerMBean(secondary, secondaryName);

        AtomicInteger received = new AtomicInteger();

        NotificationListener listener =
            (notification, handback) -> received.incrementAndGet();

        server.addNotificationListener(
            primaryName,
            listener,
            null,
            null
        );

        try {
            primary.updateDepth(200);
            secondary.updateDepth(200);

            assertEquals(1, received.get());
        } finally {
            server.removeNotificationListener(primaryName, listener);
            server.unregisterMBean(primaryName);
            server.unregisterMBean(secondaryName);
        }
    }
}
\`\`\`

Đối với example broadcaster phát callback đồng bộ mặc định, assertion đếm sự kiện có thể trực tiếp sau sendNotification. Nếu ứng dụng dùng asynchronous executor, cần cơ chế await có timeout thay vì giả định notification đã được xử lý ngay khi operation trả về.

### Test trong Spring context

Với QueueJmxConfiguration, bạn có thể test:

1. Tạo AnnotationConfigApplicationContext.
2. Xác nhận \`server.isRegistered(primaryName)\`.
3. Kích hoạt notification qua QueueMonitor.
4. Dùng listener ghi sự kiện vào một collector test.
5. Xác nhận chỉ event từ Primary được nhận.
6. Đóng context và xác minh MBean/listener được cleanup.

Trong môi trường nhiều test chạy song song, nên dùng MBeanServer riêng hoặc ObjectNames được phân vùng để tránh xung đột với test khác.

## 14. MBeanServer nào là đúng?

Một JVM có thể có nhiều MBeanServers. Nếu MBeanExporter dùng server tùy biến:

\`\`\`java
exporter.setServer(customServer);
\`\`\`

thì listener phải được đăng ký trong **customServer**, không phải platform server khác.

Ví dụ:

\`\`\`java
MBeanServer platform =
    ManagementFactory.getPlatformMBeanServer();

MBeanServer custom =
    MBeanServerFactory.createMBeanServer("custom.jmx");
\`\`\`

Đăng ký MBean vào custom rồi gọi:

\`\`\`java
platform.addNotificationListener(name, listener, null, null);
\`\`\`

sẽ không có MBean dưới ObjectName đó ở platform server nếu không có một đăng ký riêng. Một lỗi như InstanceNotFoundException có thể chỉ ra bạn đang thao tác sai server.

Trong ứng dụng Spring, nên chọn đúng server cho cả exporter và listener registration, thay vì tạo server mới chỉ ở phía listener.

## 15. Remote JMX listener

Một client ở JVM khác dùng \`MBeanServerConnection\` từ JMXConnector:

\`\`\`java
MBeanServerConnection connection =
    connector.getMBeanServerConnection();

connection.addNotificationListener(
    objectName,
    listener,
    filter,
    handback
);
\`\`\`

Đường kết nối remote còn phụ thuộc JMX connector, quyền, TLS, network và lifecycle. Không nên mở JMX remote không xác thực để thử notification.

Đối với remote notification:

- Client phải kết nối đúng JVM và MBeanServer.
- Không giả định event được lưu bền vững hoặc replay khi reconnect.
- Khi mất kết nối, cần cơ chế phát hiện và tái đăng ký listener theo yêu cầu vận hành.
- Listener callback nên xử lý nhanh, tránh blocking quá lâu.
- Đừng đặt secret trong Notification message, userData hoặc handback.
- Nếu cần delivery guarantee, xem xét message broker/event stream chuyên dụng.

## 16. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Listener không nhận event | Đăng ký sai ObjectName | Xác nhận isRegistered và mappedObjectNames |
| InstanceNotFoundException | MBean chưa đăng ký hoặc sai MBeanServer | Kiểm tra lifecycle và server identity |
| MBean xuất hiện nhưng không phát notification | MBean không hỗ trợ broadcaster hoặc không gọi sendNotification | Kiểm tra implementation và getNotificationInfo |
| Listener nhận cả Queue Secondary | mappedObjectNames cấu hình quá rộng hoặc đăng ký hai nơi | Kiểm tra registrations |
| Listener không nhận recovered | Filter chỉ chấp nhận overload | Kiểm tra filter |
| Listener xử lý cùng event hai lần | Listener được add nhiều lần | Xác định owner và cleanup |
| Listener biến mất sau restart | MBean unregistered/recreated, registration cũ mất | Đăng ký lại khi lifecycle yêu cầu |
| Event type đúng nhưng source lạ | Notification source khác ObjectName suy đoán | Đọc getSource, xem broadcaster/connector |
| Handback luôn null | Đăng ký listener với handback null | Cung cấp context nếu cần |
| JConsole thấy MBean nhưng app không nhận event | JConsole và app đăng ký khác server/listener | Xác nhận MBeanServer và callback |
| Remote listener không nhận sau reconnect | Registration phụ thuộc kết nối/lifecycle | Thiết kế tái đăng ký và xử lý gap |
| Shutdown báo ListenerNotFoundException | Gỡ listener chưa được đăng ký hoặc gỡ trùng | Theo dõi registration state và cleanup phù hợp |

## 17. Checklist khi đăng ký một listener cụ thể

Trước khi đưa listener vào ứng dụng:

1. **MBean được export chưa?** Kiểm tra ObjectName tồn tại trong đúng MBeanServer.
2. **MBean có broadcaster không?** Kiểm tra NotificationBroadcaster/NotificationEmitter và metadata.
3. **Tên đúng chưa?** mappedObjectNames phải trùng ObjectName thực tế.
4. **Nguồn duy nhất chưa?** Có tránh nghe nhầm MBean khác cùng type không?
5. **Filter đúng chưa?** Chỉ định type cần nhận.
6. **Handback cần không?** Nếu cần, cung cấp context không nhạy cảm.
7. **Callback có nhẹ không?** Tránh tác vụ blocking dài hoặc tái nhập gây deadlock.
8. **Listener có thread-safe không?** Notification có thể đến từ nhiều threads.
9. **Đăng ký đúng lifecycle chưa?** Không bỏ lỡ sự kiện startup quan trọng do listener gắn muộn.
10. **Cleanup rõ ràng chưa?** Remove listener khi module/context dừng.
11. **Có registration trùng không?** Tránh cấu hình Spring và gọi thủ công đồng thời.
12. **Remote security có đảm bảo không?** Connector phải được bảo vệ.
13. **Có test ranh giới JMX chưa?** Kiểm tra event đến từ đúng MBean và đúng type.

## 18. Bài tập thực hành

### Bài tập 1 — Chọn một MBean

Cho ba ObjectNames:

\`\`\`text
learning.jmx:type=Queue,name=Primary
learning.jmx:type=Queue,name=Secondary
learning.jmx:type=Cache,name=Products
\`\`\`

Viết code addNotificationListener chỉ cho Queue Primary. Giải thích vì sao filter theo type overload không thay thế việc chọn đúng ObjectName.

### Bài tập 2 — Lọc overload

Tạo NotificationFilter chỉ nhận \`learning.queue.overloaded\`. Kích hoạt overload và recovery; xác nhận callback chỉ nhận overload.

### Bài tập 3 — Spring NotificationListenerBean

Cấu hình Spring MBeanExporter với listenerBean có mappedObjectNames là Queue Primary. Sau đó thêm Queue Secondary vào exporter nhưng không sửa mappedObjectNames. Kiểm tra listener không nhận event từ Secondary.

### Bài tập 4 — Kiểm thử cleanup

Đăng ký listener thủ công, kích hoạt event, gỡ listener, kích hoạt lại event. Xác nhận số callback không tăng sau remove. Dùng try/finally để cleanup MBean.

### Bài tập 5 — Debug sai server

Tạo hai MBeanServers A và B, đăng ký QueueMonitor vào A. Thử addNotificationListener trên B với cùng ObjectName, quan sát lỗi rồi sửa bằng việc dùng A. Giải thích sự khác nhau giữa ObjectName và MBeanServer identity.

## 19. Ghi nhớ cốt lõi

- **Chọn một MBean bằng ObjectName** là bước đầu tiên để giới hạn nguồn notification.
- Spring \`NotificationListenerBean\` có thể dùng \`mappedObjectNames\` để gắn listener tới một MBean cụ thể.
- \`NotificationFilter\` giới hạn loại event, không thay thế việc chọn đúng broadcaster.
- MBean phải được đăng ký và hỗ trợ notification; chỉ có Spring bean hay ObjectName không đủ.
- MBeanServer đích của listener phải là MBeanServer đang giữ MBean.
- Listener registration có vòng đời riêng và cần cleanup hoặc cơ chế exporter quản lý.
- Không giả định JMX Notification có durable delivery/replay; với remote connection phải xử lý reconnect và bảo mật.
- Kiểm thử cả metadata, source, type, lifecycle và việc không nhận event từ MBean khác.

## Tài liệu tham khảo

- Spring Framework Reference — JMX Notifications: https://docs.spring.io/spring-framework/reference/integration/jmx/notifications.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework API — NotificationListenerBean: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/NotificationListenerBean.html
- Spring Framework API — MBeanExporter: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Java SE 21 API — NotificationListener: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/NotificationListener.html
- Java SE 21 API — NotificationBroadcasterSupport: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/NotificationBroadcasterSupport.html
- Java SE 21 API — MBeanServer: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
