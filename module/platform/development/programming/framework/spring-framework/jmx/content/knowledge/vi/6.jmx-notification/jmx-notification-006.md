# Spring Framework JMX Notification: Đăng ký listener và hủy đăng ký listener

## 1. Mục tiêu và bức tranh tổng thể

JMX không chỉ cho phép đọc/ghi thuộc tính hay gọi operation lên MBean. Một MBean còn có thể **phát Notification** khi xảy ra sự kiện quản trị, chẳng hạn thay đổi trạng thái worker, vượt ngưỡng queue, kết thúc một đợt xử lý hoặc tái cấu hình tài nguyên. Thành phần quan tâm có thể **đăng ký listener** để nhận sự kiện, sau đó **hủy đăng ký** khi không còn cần theo dõi.

Ba vai trò chính:

- **Nguồn phát (notification broadcaster / emitter)**: MBean phát ra \`javax.management.Notification\`.
- **Listener**: đối tượng triển khai \`javax.management.NotificationListener\`, xử lý notification qua \`handleNotification(Notification, Object)\`.
- **MBeanServer**: điểm trung gian đăng ký và hủy đăng ký listener theo \`ObjectName\`. Với listener được quản lý qua server, có thể dùng một \`ObjectName\` khác để chỉ MBean nhận notification.

Luồng cơ bản:

\`\`\`text
                              register
JMX client / Spring bean  ------------------------+
    NotificationListener                          |
             |                                     v
             |                            MBeanServer
             |                                   |
             | addNotificationListener(          | ObjectName của broadcaster
             |     name, listener, filter, handback)
             |                                   |
             +<----------- Notification ----------+
             |
             +--> handleNotification(notification, handback)
             |
             +-- removeNotificationListener(...) --> Hủy subscription
\`\`\`

**Đăng ký** là tạo quan hệ nhận notification. **Hủy đăng ký** là kết thúc quan hệ đó. Không nên nhầm việc listener Java vẫn tồn tại trong bộ nhớ với việc listener vẫn đang đăng ký nhận notification: một đối tượng có thể còn sống nhưng không còn nhận sự kiện, hoặc một listener không được tham chiếu trực tiếp bởi business code vẫn đang được MBeanServer/broadcaster giữ qua subscription.

## 2. API nền tảng của Java JMX

Những loại cơ bản trong \`javax.management\`:

| API | Vai trò |
|---|---|
| \`Notification\` | Dữ liệu sự kiện, gồm type, source, sequence number, timestamp, message và optional user data |
| \`NotificationListener\` | Callback nhận notification với \`handleNotification\` |
| \`NotificationFilter\` | Quyết định notification nào được chuyển tới listener |
| \`NotificationFilterSupport\` | Filter tiện ích theo notification type |
| \`NotificationBroadcaster\` | Hợp đồng phát sự kiện và quản lý listener |
| \`NotificationEmitter\` | Mở rộng broadcaster và hỗ trợ remove theo bộ ba listener/filter/handback |
| \`NotificationBroadcasterSupport\` | Lớp tiện ích phát notification và quản lý đăng ký |
| \`MBeanServerConnection\` | API đăng ký/hủy đăng ký listener từ phía client hoặc qua MBeanServer |

Interface listener:

\`\`\`java
import javax.management.Notification;
import javax.management.NotificationListener;

NotificationListener listener = new NotificationListener() {
    @Override
    public void handleNotification(
            Notification notification,
            Object handback) {
        System.out.println(
            "type=" + notification.getType()
                + ", seq=" + notification.getSequenceNumber()
                + ", message=" + notification.getMessage()
                + ", handback=" + handback
        );
    }
};
\`\`\`

Tham số \`handback\` là đối tượng do **bên đăng ký** truyền vào. Nó giúp listener phân biệt ngữ cảnh các subscription. \`handback\` không phải payload chính của sự kiện; payload nằm trong đối tượng \`Notification\` và có thể chứa \`userData\`.

## 3. Tạo một broadcaster MBean đơn giản

MBean phát notification cần công bố khả năng phát notification. Ví dụ một bộ điều khiển worker có thể phát thông báo khi chuyển từ RUNNING sang PAUSED.

Định nghĩa giao diện quản trị:

\`\`\`java
package com.example.jmx;

public interface WorkerControlMBean {
    boolean isActive();
    void pause();
    void resume();
}
\`\`\`

Triển khai broadcaster với \`NotificationBroadcasterSupport\`:

\`\`\`java
package com.example.jmx;

import java.util.concurrent.atomic.AtomicLong;
import javax.management.MBeanNotificationInfo;
import javax.management.Notification;
import javax.management.NotificationBroadcasterSupport;

public class WorkerControl
        extends NotificationBroadcasterSupport
        implements WorkerControlMBean {

    public static final String PAUSED = "com.example.worker.paused";
    public static final String RESUMED = "com.example.worker.resumed";

    private final AtomicLong sequence = new AtomicLong();
    private volatile boolean active = true;

    @Override
    public boolean isActive() {
        return active;
    }

    @Override
    public synchronized void pause() {
        if (!active) {
            return;
        }
        active = false;
        sendNotification(new Notification(
            PAUSED,
            this,
            sequence.incrementAndGet(),
            System.currentTimeMillis(),
            "Worker paused"
        ));
    }

    @Override
    public synchronized void resume() {
        if (active) {
            return;
        }
        active = true;
        sendNotification(new Notification(
            RESUMED,
            this,
            sequence.incrementAndGet(),
            System.currentTimeMillis(),
            "Worker resumed"
        ));
    }

    @Override
    public MBeanNotificationInfo[] getNotificationInfo() {
        return new MBeanNotificationInfo[] {
            new MBeanNotificationInfo(
                new String[] { PAUSED, RESUMED },
                Notification.class.getName(),
                "Worker lifecycle notifications"
            )
        };
    }
}
\`\`\`

Ở ví dụ này, \`getNotificationInfo()\` khai báo những loại notification MBean có thể phát; client sử dụng metadata để khám phá. \`sendNotification\` thực sự phát event cho các listener đã đăng ký.

**Lưu ý về đồng thời:** ví dụ gửi notification khi đang giữ lock \`synchronized\`. Với business operation thực, có thể thiết kế thu thập thay đổi state bên trong lock rồi phát notification sau khi ra khỏi vùng đồng bộ để giảm nguy cơ callback hoặc executor gây tương tác phức tạp. Thiết kế phải nhất quán giữa thứ tự state change và event.

Đăng ký MBean vào platform MBeanServer:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName name = new ObjectName(
    "com.example.app:type=WorkerControl,name=main"
);

server.registerMBean(new WorkerControl(), name);
\`\`\`

Đoạn code giả định ObjectName chưa được đăng ký. Trong ứng dụng Spring, thường để \`MBeanExporter\` đăng ký MBean thay vì gọi \`registerMBean\` thủ công cho cùng một bean.

## 4. Đăng ký NotificationListener với MBeanServer

Cách thông dụng nhất là dùng overload:

\`\`\`java
void addNotificationListener(
    ObjectName name,
    NotificationListener listener,
    NotificationFilter filter,
    Object handback
)
\`\`\`

Ví dụ đầy đủ:

\`\`\`java
import javax.management.MBeanServer;
import javax.management.Notification;
import javax.management.NotificationListener;
import javax.management.NotificationFilterSupport;
import javax.management.ObjectName;

ObjectName target = new ObjectName(
    "com.example.app:type=WorkerControl,name=main"
);

NotificationListener listener = (Notification n, Object context) -> {
    System.out.printf(
        "event=%s, sequence=%d, context=%s%n",
        n.getType(),
        n.getSequenceNumber(),
        context
    );
};

NotificationFilterSupport filter = new NotificationFilterSupport();
filter.enableType("com.example.worker.paused");
filter.enableType("com.example.worker.resumed");

String handback = "monitoring-subscription-1";

server.addNotificationListener(
    target,
    listener,
    filter,
    handback
);
\`\`\`

Ý nghĩa từng đối số:

1. \`target\`: **ObjectName của MBean phát notification**, không phải tên của listener.
2. \`listener\`: callback object thực tế nhận event.
3. \`filter\`: có thể \`null\` để nhận tất cả loại notification mà broadcaster chuyển tới; khi dùng filter, event chỉ đến callback nếu \`isNotificationEnabled\` trả \`true\`.
4. \`handback\`: tùy chọn \`null\` hoặc bất kỳ context object phù hợp trong JVM; MBeanServer chuyển giá trị này cho listener khi gọi callback.

\`NotificationFilterSupport.enableType\` kiểm tra các type bắt đầu bằng chuỗi đã bật, nên có thể match cả type con có cùng prefix. Khi cần so khớp **chính xác một type**, tự triển khai filter với \`notification.getType().equals(...)\` hoặc kiểm tra rõ quy ước namespace type. Không nên coi filter prefix là cơ chế phân quyền.

Để thử:

\`\`\`java
server.invoke(
    target,
    "pause",
    new Object[0],
    new String[0]
);

server.invoke(
    target,
    "resume",
    new Object[0],
    new String[0]
);
\`\`\`

Sau lời gọi, listener sẽ nhận các notification phù hợp theo cơ chế dispatch của broadcaster. Với broadcaster triển khai bất đồng bộ, callback có thể chạy muộn; không nên dựa vào thứ tự callback như một transaction đồng bộ với operation nếu không có hợp đồng cụ thể.

## 5. Hủy đăng ký listener đúng cách

JMX hỗ trợ hai kiểu hủy listener object qua \`MBeanServerConnection\`:

\`\`\`java
removeNotificationListener(ObjectName name, NotificationListener listener)

removeNotificationListener(
    ObjectName name,
    NotificationListener listener,
    NotificationFilter filter,
    Object handback
)
\`\`\`

### 5.1. Hủy toàn bộ đăng ký của listener với một MBean

\`\`\`java
server.removeNotificationListener(target, listener);
\`\`\`

Overload hai tham số loại bỏ các đăng ký của \`listener\` trên broadcaster \`target\` (theo hợp đồng API). Cùng listener có thể đăng ký với các MBean khác, nên việc hủy trên \`target\` không đồng nghĩa hủy mọi subscription trên mọi MBean.

### 5.2. Hủy chính xác một subscription

Nếu cùng \`listener\` được đăng ký nhiều lần với filter/handback khác nhau, overload bốn tham số cho phép loại đúng một tổ hợp đăng ký:

\`\`\`java
server.removeNotificationListener(
    target,
    listener,
    filter,
    handback
);
\`\`\`

Cần truyền lại đúng các đối tượng filter/handback đã dùng khi đăng ký. Với JMX local, việc đối chiếu thường dựa trên identity của listener, filter và handback theo hợp đồng quản lý listener; **đừng tạo filter object mới giống nội dung rồi giả định nó là subscription cũ**.

Ví dụ dễ sai:

\`\`\`java
NotificationFilterSupport first = new NotificationFilterSupport();
first.enableType("com.example.worker.paused");

server.addNotificationListener(target, listener, first, "ctx");

// Một đối tượng filter khác:
NotificationFilterSupport second = new NotificationFilterSupport();
second.enableType("com.example.worker.paused");

// Không nên giả định second xác định chính xác registration với first.
server.removeNotificationListener(target, listener, second, "ctx");
\`\`\`

Nên lưu nguyên \`listener\`, \`filter\` và \`handback\` trong một đối tượng quản lý subscription để hủy chính xác.

### 5.3. Hủy listener khi object bị mất đăng ký

Nếu \`target\` đã bị unregister khỏi MBeanServer, lời gọi hủy có thể phát sinh \`InstanceNotFoundException\`. Nếu broadcaster không tìm thấy registration tương ứng, JMX thường ném \`ListenerNotFoundException\`. Một shutdown handler có thể lựa chọn ghi nhận trường hợp subscription đã biến mất, nhưng không nên che mọi exception vì có thể bỏ sót lỗi cấu hình hoặc nhầm tên.

## 6. Quản lý lifecycle bằng AutoCloseable

Để tránh quên remove, bọc subscription trong một đối tượng có \`close()\`. Khi setup thành công, \`close()\` thực hiện remove chính xác một lần.

\`\`\`java
import javax.management.MBeanServerConnection;
import javax.management.NotificationFilter;
import javax.management.NotificationListener;
import javax.management.ObjectName;
import java.io.IOException;
import java.util.concurrent.atomic.AtomicBoolean;

public final class JmxSubscription implements AutoCloseable {
    private final MBeanServerConnection connection;
    private final ObjectName broadcaster;
    private final NotificationListener listener;
    private final NotificationFilter filter;
    private final Object handback;
    private final AtomicBoolean closed = new AtomicBoolean();

    public JmxSubscription(
            MBeanServerConnection connection,
            ObjectName broadcaster,
            NotificationListener listener,
            NotificationFilter filter,
            Object handback) throws Exception {

        this.connection = connection;
        this.broadcaster = broadcaster;
        this.listener = listener;
        this.filter = filter;
        this.handback = handback;

        connection.addNotificationListener(
            broadcaster,
            listener,
            filter,
            handback
        );
    }

    @Override
    public void close() throws Exception {
        if (!closed.compareAndSet(false, true)) {
            return;
        }
        connection.removeNotificationListener(
            broadcaster,
            listener,
            filter,
            handback
        );
    }
}
\`\`\`

Cách dùng:

\`\`\`java
try (JmxSubscription subscription = new JmxSubscription(
        server,
        target,
        listener,
        filter,
        handback)) {

    server.invoke(target, "pause", new Object[0], new String[0]);
    server.invoke(target, "resume", new Object[0], new String[0]);

} // close() hủy đăng ký listener
\`\`\`

Ví dụ này nhấn mạnh **ownership và cleanup**. Với ứng dụng thực tế cần cân nhắc ngoại lệ khi remove, retry hoặc xác nhận trạng thái close trước khi đánh dấu đã hủy. Trong phiên bản trên, \`closed\` chuyển sang \`true\` trước khi \`removeNotificationListener\` hoàn thành; nếu remove thất bại thì object không tự retry. Chọn chính sách này chỉ khi shutdown mang tính best effort, hoặc bổ sung cơ chế quản lý lỗi phù hợp.

Đối với listener chạy lâu dài suốt vòng đời Spring context, có thể giữ subscription như field của một bean và hủy trong callback destroy, thay vì giới hạn trong \`try-with-resources\` ngắn.

## 7. Spring Framework: đăng ký listener thông qua MBeanExporter

Spring JMX có \`MBeanExporter\` để export các bean và hỗ trợ đăng ký notification listener theo cấu hình exporter. Tùy cách wiring, Spring có thể quản lý vòng đời đăng ký/hủy listener khi context đóng.

Các interface và class liên quan:

- \`org.springframework.jmx.export.MBeanExporter\`
- \`org.springframework.jmx.export.notification.NotificationListenerBean\`
- \`org.springframework.jmx.export.notification.NotificationPublisher\`
- \`org.springframework.jmx.export.notification.NotificationPublisherAware\`

### 7.1. Listener thông thường trong Spring

\`\`\`java
package com.example.jmx;

import javax.management.Notification;
import javax.management.NotificationListener;

public class AuditNotificationListener implements NotificationListener {
    @Override
    public void handleNotification(
            Notification notification,
            Object handback) {

        System.out.printf(
            "[JMX AUDIT] type=%s, source=%s, msg=%s%n",
            notification.getType(),
            notification.getSource(),
            notification.getMessage()
        );
    }
}
\`\`\`

Có thể khai báo \`NotificationListenerBean\` để mô tả listener, MBean mà nó quan tâm và filter/context. Mẫu cấu hình:

\`\`\`java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.notification.NotificationListenerBean;

@Configuration
public class JmxListenerConfiguration {
    @Bean
    public AuditNotificationListener auditNotificationListener() {
        return new AuditNotificationListener();
    }

    @Bean
    public NotificationListenerBean auditListenerBean(
            AuditNotificationListener auditNotificationListener) {

        NotificationListenerBean definition = new NotificationListenerBean();
        definition.setNotificationListener(auditNotificationListener);
        definition.setMappedObjectName(
            "com.example.app:type=WorkerControl,name=main"
        );
        return definition;
    }

    @Bean
    public MBeanExporter mbeanExporter(
            WorkerControl workerControl,
            NotificationListenerBean auditListenerBean) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setBeans(java.util.Map.of(
            "com.example.app:type=WorkerControl,name=main",
            workerControl
        ));
        exporter.setNotificationListeners(auditListenerBean);
        return exporter;
    }
}
\`\`\`

Mẫu này minh họa cách gắn listener với exporter. Cần chú ý không cấu hình thêm exporter khác tự động export cùng bean, nhất là khi sử dụng Spring Boot auto-configuration hoặc \`@EnableMBeanExport\`. Kiểu của MBean được export phải thực sự hỗ trợ NotificationBroadcaster/Emitter.

Trong Spring, \`NotificationListenerBean\` có thể map listener tới một hay nhiều \`ObjectName\`; khi không chỉ rõ map, scope đăng ký phụ thuộc cấu hình exporter. Nên khai báo rõ MBean đích để tránh nhận notification không mong muốn.

### 7.2. NotificationPublisherAware dành cho bean do Spring export

Với Spring-managed MBean, có thể dùng \`NotificationPublisherAware\` để nhận \`NotificationPublisher\` do exporter cấp:

\`\`\`java
import java.util.concurrent.atomic.AtomicLong;
import javax.management.Notification;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.jmx.export.notification.NotificationPublisher;
import org.springframework.jmx.export.notification.NotificationPublisherAware;

@ManagedResource(
    objectName = "com.example.app:type=WorkerControl,name=main"
)
public class SpringWorkerControl implements NotificationPublisherAware {
    private final AtomicLong sequence = new AtomicLong();
    private NotificationPublisher publisher;

    @Override
    public void setNotificationPublisher(NotificationPublisher publisher) {
        this.publisher = publisher;
    }

    @ManagedOperation
    public void pause() {
        // Cập nhật trạng thái nghiệp vụ ở đây...
        publisher.sendNotification(new Notification(
            "com.example.worker.paused",
            this,
            sequence.incrementAndGet(),
            "Worker paused"
        ));
    }
}
\`\`\`

Ví dụ dành cho cơ chế Spring JMX annotation export. \`NotificationPublisherAware\` là phía **phát**, khác với \`NotificationListener\` phía **nhận**. Để client biết các notification types một cách chính xác, MBean cần có metadata notification phù hợp với cơ chế export/assembler đang sử dụng.

Khi bean không được exporter quản lý hoặc publisher chưa được inject, gọi \`publisher.sendNotification\` có thể lỗi; Spring lifecycle và cấu hình exporter phải được thiết lập đúng.

## 8. Spring lifecycle: tạo subscription và hủy khi context đóng

Nếu ứng dụng Spring chủ động đăng ký listener bằng API JMX, có thể quản lý vòng đời bằng \`@PostConstruct\` và \`@PreDestroy\`, hoặc dùng \`SmartLifecycle\`, \`DisposableBean\` tùy yêu cầu.

Ví dụ Spring bean đăng ký khi khởi tạo và hủy khi đóng context:

\`\`\`java
package com.example.jmx;

import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.Notification;
import javax.management.NotificationFilterSupport;
import javax.management.NotificationListener;
import javax.management.ObjectName;
import org.springframework.stereotype.Component;

@Component
public class WorkerNotificationSubscriber {

    private final MBeanServer server =
        ManagementFactory.getPlatformMBeanServer();

    private final ObjectName target;
    private final NotificationListener listener;
    private final NotificationFilterSupport filter;

    public WorkerNotificationSubscriber() throws Exception {
        target = new ObjectName(
            "com.example.app:type=WorkerControl,name=main"
        );

        listener = (Notification event, Object handback) ->
            System.out.println("Received: " + event.getType());

        filter = new NotificationFilterSupport();
        filter.enableType("com.example.worker.");
    }

    @PostConstruct
    public void start() throws Exception {
        server.addNotificationListener(
            target,
            listener,
            filter,
            null
        );
    }

    @PreDestroy
    public void stop() throws Exception {
        server.removeNotificationListener(
            target,
            listener,
            filter,
            null
        );
    }
}
\`\`\`

Đoạn code có ý nghĩa minh họa trong ứng dụng dùng Jakarta annotations. Trong Spring Framework 6, \`jakarta.annotation\` là namespace thường dùng. Dependency Jakarta annotation API cần có trong classpath nếu không được runtime cung cấp.

**Điểm cần lưu ý về thứ tự khởi tạo:** \`@PostConstruct\` của subscriber có thể chạy trước khi MBean đích được export. Nếu vậy, \`InstanceNotFoundException\` sẽ xảy ra. Với ứng dụng thật, nên tạo dependency rõ ràng để exporter hoàn thành việc đăng ký trước, dùng lifecycle phase thích hợp, hoặc đăng ký sau sự kiện context sẵn sàng; không dùng vòng retry vô hạn mà không theo dõi shutdown.

Nếu \`@PreDestroy\` được gọi sau khi exporter đã unregister MBean, remove có thể lỗi. Có thể để cùng một component quản lý cả exporter và subscription, hoặc chọn \`SmartLifecycle\` với thứ tự start/stop được kiểm soát.

### Khi nào để Spring đăng ký hộ?

Nếu subscriber nằm cùng Spring context với \`MBeanExporter\` và lifecycle có thể quản lý đồng nhất, \`NotificationListenerBean\` thường giảm code thủ công. Nếu subscriber là client ngoài ứng dụng hoặc kết nối đến remote JMX, quản lý trực tiếp qua \`MBeanServerConnection\`/\`JMXConnector\` thường rõ ràng hơn.

## 9. Đăng ký listener từ JMX remote client

Khi Java client kết nối JVM khác, thường sử dụng \`JMXConnectorFactory\`:

\`\`\`java
import javax.management.MBeanServerConnection;
import javax.management.NotificationListener;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

JMXServiceURL serviceUrl = new JMXServiceURL(
    "service:jmx:rmi:///jndi/rmi://localhost:9999/jmxrmi"
);

try (JMXConnector connector =
        JMXConnectorFactory.connect(serviceUrl)) {

    MBeanServerConnection connection =
        connector.getMBeanServerConnection();

    ObjectName target = new ObjectName(
        "com.example.app:type=WorkerControl,name=main"
    );

    NotificationListener listener = (event, context) ->
        System.out.println("Remote event: " + event.getType());

    connection.addNotificationListener(
        target,
        listener,
        null,
        null
    );

    try {
        // Client đang hoạt động và có thể nhận notification.
        // Không đóng connector trước khi kết thúc subscription.
    } finally {
        connection.removeNotificationListener(target, listener);
    }
}
\`\`\`

Đây là ví dụ hình thức kết nối; endpoint chỉ hoạt động khi remote JMX đã được cấu hình tương ứng. Trong môi trường thực, phải cấu hình authentication, authorization, TLS/transport security và giới hạn network theo hạ tầng. Không bật remote JMX cổng công khai khi chưa bảo vệ quyền truy cập.

**Đặc điểm remote delivery:**

- Notification có thể được chuyển qua transport của JMX connector; mất kết nối có thể làm client bỏ lỡ notification.
- Không nên mặc định notification được lưu bền vững, retry tự động vô hạn hoặc cung cấp exactly-once delivery.
- \`Notification\` và \`userData\` cần phù hợp với serialization/transport nếu chuyển qua remote connector.
- Listener chỉ nhận những notification phát sau khi subscription thực sự được thiết lập; không có cơ chế replay lịch sử mặc định.
- Cần quản lý reconnect và resubscribe khi kết nối bị ngắt nếu ứng dụng cần tiếp tục theo dõi lâu dài.

Nếu subscription đã mất sau disconnect, client nên xác định connection mới đã sẵn sàng rồi đăng ký lại. Tránh tạo nhiều subscription giống nhau trên cùng connection vì sẽ dẫn tới callback trùng.

## 10. Trường hợp listener là MBean được đăng ký

Ngoài nhận một object \`NotificationListener\`, \`MBeanServerConnection\` còn có overload đăng ký listener qua \`ObjectName\`:

\`\`\`java
addNotificationListener(
    ObjectName broadcasterName,
    ObjectName listenerName,
    NotificationFilter filter,
    Object handback
)
\`\`\`

Ở dạng này, listener phải là một MBean được MBeanServer định danh bằng \`listenerName\` và đáp ứng hợp đồng nhận notification thích hợp. Mục tiêu là server trung gian quản lý quan hệ giữa hai MBean.

Ví dụ cú pháp:

\`\`\`java
ObjectName broadcaster = new ObjectName(
    "com.example.app:type=WorkerControl,name=main"
);

ObjectName listenerMBean = new ObjectName(
    "com.example.app:type=AuditListener,name=worker-events"
);

server.addNotificationListener(
    broadcaster,
    listenerMBean,
    null,
    "operations"
);
\`\`\`

Cần đăng ký MBean listener hợp lệ trước khi thực hiện lời gọi. Không phải chỉ đặt tên cho một object Java thông thường là đủ. Hủy subscription:

\`\`\`java
server.removeNotificationListener(
    broadcaster,
    listenerMBean
);
\`\`\`

hoặc phiên bản có filter và handback. Khi lỗi \`InstanceNotFoundException\`, hãy phân biệt broadcaster chưa đăng ký và listener ObjectName không tồn tại; kiểm tra cả hai qua \`isRegistered\`.

## 11. Filter và handback khi listener được tái sử dụng

Một listener có thể nhận event từ nhiều nguồn hoặc nhiều loại event. Ví dụ cùng một callback được đăng ký hai lần với những bộ lọc khác nhau:

\`\`\`java
NotificationListener listener = (n, context) ->
    System.out.println(context + ": " + n.getType());

NotificationFilterSupport pauseFilter =
    new NotificationFilterSupport();
pauseFilter.enableType("com.example.worker.paused");

NotificationFilterSupport resumeFilter =
    new NotificationFilterSupport();
resumeFilter.enableType("com.example.worker.resumed");

Object pauseContext = new Object();
Object resumeContext = new Object();

server.addNotificationListener(
    target, listener, pauseFilter, pauseContext
);
server.addNotificationListener(
    target, listener, resumeFilter, resumeContext
);
\`\`\`

Khi muốn dừng nhận event pause nhưng vẫn nhận resume:

\`\`\`java
server.removeNotificationListener(
    target, listener, pauseFilter, pauseContext
);
\`\`\`

Khi muốn dừng toàn bộ subscription của listener trên target:

\`\`\`java
server.removeNotificationListener(target, listener);
\`\`\`

Nếu client tạo nhiều registration trùng nhau, một notification có thể dẫn đến nhiều lần callback. Sự trùng lặp đôi khi do logic setup chạy lại mà chưa remove, không phải broadcaster phát event nhiều lần.

**Handback nên là context nhẹ và không nhạy cảm.** Với remote JMX, cân nhắc object truyền qua connector và những yêu cầu serializable. Không đưa secret hoặc object giữ nhiều tài nguyên vào handback chỉ để đánh dấu một subscription.

## 12. Lỗi thường gặp khi đăng ký và hủy

| Tình huống | Biểu hiện thường gặp | Cách chẩn đoán |
|---|---|---|
| Sai ObjectName broadcaster | \`InstanceNotFoundException\` | Kiểm tra \`isRegistered\` và \`queryNames\` |
| MBean không hỗ trợ notification | \`RuntimeOperationsException\` hoặc lỗi khác theo adapter | Kiểm tra MBean có broadcaster/emitter và \`MBeanNotificationInfo\` |
| Listener đã bị remove | \`ListenerNotFoundException\` khi remove lần nữa | Quản lý trạng thái subscription và một owner cleanup |
| Dùng filter/handback khác khi remove | \`ListenerNotFoundException\` | Giữ lại đúng object đã đăng ký |
| Đăng ký hai lần ngoài ý muốn | Event đến callback hai lần | Theo dõi số lần add/remove và subscription identity |
| Filter không match | Listener không nhận notification | Kiểm tra \`getType()\` và quy tắc match của filter |
| Operation không phát event | Listener không nhận notification | Xác nhận broadcaster có gọi \`sendNotification\` |
| MBean bị unregister | Remove thất bại hoặc không còn nhận event | Quản lý lifecycle và thứ tự shutdown |
| Remote connection bị ngắt | Mất notification, callback dừng đến | Kiểm tra connector, reconnect và resubscribe |
| Callback ném runtime exception | Log/lỗi dispatch hoặc ảnh hưởng thread gọi tùy executor | Bắt lỗi trong listener và cô lập xử lý |

Không suy luận loại exception duy nhất cho mọi loại MBeanServer, Spring adapter và JMX connector. Đọc \`cause\`, stack trace, tên broadcaster và metadata của MBean để xác định lỗi thực tế.

## 13. Concurrency và độ tin cậy của callback

\`NotificationListener.handleNotification\` là callback; cách và thời điểm nó chạy phụ thuộc broadcaster/connector và executor.

- **Đừng làm việc chặn lâu trong callback.** Nếu listener cần ghi database, gọi mạng hoặc tính toán nặng, đẩy dữ liệu tối thiểu sang executor/queue có giới hạn rồi xử lý ngoài callback.
- **Đừng giả định callback luôn chạy trong thread gọi operation.** \`NotificationBroadcasterSupport\` có thể dùng executor để dispatch; connector remote cũng có luồng chuyển event riêng.
- **Đừng giả định event liên tiếp đồng nghĩa một transaction.** MBean có thể gửi notification trong khi state thay đổi hoặc listener đọc state mới hơn.
- **Cần xác định semantics khi hủy.** \`removeNotificationListener\` ngừng đăng ký, nhưng callback đã được lên lịch trước đó có thể vẫn đang chạy; muốn shutdown hoàn toàn cần ngừng worker queue và chờ tác vụ xử lý nếu hợp đồng ứng dụng yêu cầu.
- **Làm callback đủ bền vững.** Xử lý lỗi cục bộ, ghi metric số event thành công/thất bại, và không để một event xấu làm tắt toàn bộ listener.

Ví dụ handler nhẹ:

\`\`\`java
NotificationListener listener = (notification, handback) -> {
    try {
        String type = notification.getType();
        long sequence = notification.getSequenceNumber();

        // Xử lý nhanh hoặc enqueue vào hàng đợi có giới hạn.
        System.out.println(type + " #" + sequence);
    } catch (RuntimeException ex) {
        // Log có context, không làm lộ dữ liệu nhạy cảm.
        System.err.println("JMX notification handler failed: " + ex);
    }
};
\`\`\`

Trong hệ thống cần phát hiện mất sự kiện, có thể quan sát sequence number cùng source và restart epoch. **Sequence number không phải bảo đảm globally unique hay exactly-once**; nhiều nguồn khác nhau có thể dùng sequence độc lập, và restart có thể đặt lại bộ đếm. Nếu yêu cầu lịch sử sự kiện bền vững, nên dùng message broker/event log thay vì chỉ dựa vào JMX Notifications.

## 14. Quy trình thực hành có thể tái hiện

Giả sử đã đăng ký \`WorkerControl\` MBean và có \`MBeanServer server\`, \`ObjectName target\`.

### Bước 1: Xác minh broadcaster tồn tại

\`\`\`java
if (!server.isRegistered(target)) {
    throw new IllegalStateException("MBean not registered: " + target);
}

for (var info : server.getMBeanInfo(target).getNotifications()) {
    System.out.println(
        "notification class=" + info.getName()
    );
    for (String type : info.getNotifTypes()) {
        System.out.println("  type=" + type);
    }
}
\`\`\`

### Bước 2: Tạo listener và filter

\`\`\`java
NotificationListener listener = (n, ctx) ->
    System.out.println("RECEIVED " + n.getType());

NotificationFilterSupport filter = new NotificationFilterSupport();
filter.enableType("com.example.worker.paused");
\`\`\`

### Bước 3: Đăng ký

\`\`\`java
server.addNotificationListener(target, listener, filter, null);
\`\`\`

### Bước 4: Gọi operation để phát sự kiện

\`\`\`java
server.invoke(target, "pause", new Object[0], new String[0]);
\`\`\`

Quan sát listener nhận event pause.

### Bước 5: Hủy đăng ký

\`\`\`java
server.removeNotificationListener(target, listener, filter, null);
\`\`\`

### Bước 6: Gọi lại và kiểm tra không còn subscription

\`\`\`java
server.invoke(target, "resume", new Object[0], new String[0]);
server.invoke(target, "pause", new Object[0], new String[0]);
\`\`\`

Sau khi remove, listener không còn được lên lịch nhận các event mới do subscription đó. Nếu có callback đang được dispatch từ trước hoặc client remote có độ trễ, vẫn có thể nhìn thấy callback muộn. Đây là hành vi cần tính đến khi kiểm tra shutdown trong hệ thống bất đồng bộ.

## 15. Câu hỏi tự kiểm tra

**1. Vì sao cần giữ reference tới NotificationListener?**

Để remove đúng instance listener đã đăng ký và tránh mất khả năng cleanup. Nếu mỗi lần gọi đều tạo lambda mới, không được giả định lambda mới là cùng registration với lambda cũ.

**2. Nếu listener được add hai lần với hai filter khác nhau, gọi remove hai tham số có tác dụng gì?**

Nó hủy các registration của listener đó đối với broadcaster tương ứng. Nếu chỉ muốn loại một subscription, dùng overload bốn tham số với đúng filter và handback.

**3. Filter có thay thế authorization không?**

Không. Filter chỉ là cơ chế chọn event chuyển cho listener. Authorization phải do JMX connector/server và chính sách hệ thống kiểm soát.

**4. Vì sao một client không nhận được notification dù MBean đã đăng ký?**

Có thể MBean không phát event, filter không match, ObjectName sai, listener chưa đăng ký thành công, connection bị ngắt, hoặc event đã xảy ra trước khi subscription được thiết lập.

**5. Có thể dùng JMX Notifications làm message queue bền vững không?**

Không có bảo đảm lưu bền vững, replay hay exactly-once mặc định. Nó phù hợp cho tín hiệu quản trị runtime; yêu cầu delivery nghiêm ngặt nên dùng nền tảng messaging phù hợp.

**6. Khi Spring context dừng, điểm nào cần kiểm tra?**

Xác định exporter và subscriber thuộc lifecycle nào, thứ tự hủy đăng ký, và xử lý trường hợp broadcaster đã biến mất; tránh để subscription tồn tại sau khi service không còn cần theo dõi.

## 16. Ghi nhớ

Đăng ký JMX Notification listener bằng \`MBeanServer.addNotificationListener\` tạo quan hệ **broadcaster → listener**, kèm filter và handback tùy chọn. Hủy bằng \`removeNotificationListener\`, ưu tiên giữ nguyên reference để loại đúng subscription. Với Spring Framework, có thể dùng \`NotificationListenerBean\` kết hợp \`MBeanExporter\` để Spring quản lý đăng ký, hoặc sử dụng trực tiếp JMX API trong Spring lifecycle khi cần kiểm soát đặc biệt.

Điểm quan trọng nhất khi xây hệ thống nhiều component là coi listener như một tài nguyên có **owner, lifecycle và cleanup**. Xác định khi nào đăng ký, khi nào kết thúc, xử lý reconnect, callback chậm và lỗi remove. Từ đó notification thực sự giúp quan sát runtime mà không làm phát sinh subscription trùng hoặc tài nguyên bị giữ ngoài ý muốn.