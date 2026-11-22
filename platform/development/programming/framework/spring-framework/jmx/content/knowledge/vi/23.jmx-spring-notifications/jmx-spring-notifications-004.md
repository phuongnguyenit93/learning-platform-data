# Wildcard listener cho các MBean exporter quản lý

> **Chủ đề:** Spring Framework JMX  
> **Nhóm kiến thức:** Notification trong Spring  
> **Bài học:** Wildcard listener cho các MBean exporter quản lý

## 1. Mục tiêu

Sau bài này, bạn có thể:

- Giải thích vai trò của JMX \`NotificationListener\` khi MBean được export bằng Spring.
- Hiểu ý nghĩa của **wildcard listener** trong \`MBeanExporter\`: một listener có thể được đăng ký cho **những MBean có khả năng phát notification mà exporter quản lý**, thay vì phải liệt kê từng ObjectName.
- Phân biệt wildcard của Spring exporter với **ObjectName query pattern** của JMX.
- Cấu hình \`NotificationListenerBean\` và \`MBeanExporter.setNotificationListeners(...)\` một cách có chủ đích.
- Phân biệt **đăng ký listener với MBean** và **lọc loại notification**.
- Nắm các giới hạn liên quan tới MBean ngoài exporter, listener đăng ký động, MBean bị thay thế và vòng đời exporter.
- Thiết kế listener không làm chậm luồng xử lý, tránh rò rỉ dữ liệu nhạy cảm và có cơ chế kiểm chứng rõ ràng.

## 2. Mô hình notification trong JMX

Trong JMX, một MBean có thể phát \`javax.management.Notification\` khi có sự kiện đáng quan sát, chẳng hạn tác vụ hoàn tất, hàng đợi vượt ngưỡng hoặc thay đổi trạng thái.

\`\`\`text
Spring bean / MBean
        |
        | sendNotification(...)
        v
JMX notification broadcaster
        |
        | listener đã đăng ký
        v
NotificationListener.handleNotification(...)
        |
        v
Log / metric / alert / xử lý quản trị
\`\`\`

Các thành phần:

| Thành phần | Vai trò |
|---|---|
| \`Notification\` | Đối tượng sự kiện, chứa type, source, sequence, timestamp, message, userData |
| \`NotificationBroadcaster\` | Hợp đồng cho phép đăng ký/hủy listener và cung cấp metadata notification |
| \`NotificationEmitter\` | Mở rộng broadcaster để hỗ trợ thao tác hủy registration cụ thể |
| \`NotificationListener\` | Callback nhận notification |
| \`NotificationFilter\` | Quyết định sự kiện có được chuyển tới một listener registration không |
| \`NotificationFilterSupport\` | Filter hỗ trợ matching các prefix của notification type |
| \`NotificationListenerBean\` | Cấu hình Spring bọc listener, filter và MBean mục tiêu |
| \`MBeanExporter\` | Đăng ký MBean và có thể đăng ký listener cho các MBean thuộc phạm vi quản lý |

Không phải mọi Spring bean hay MBean đều phát notification. Một listener được cấu hình thành công vẫn cần broadcaster có khả năng phát và sự kiện thực sự xảy ra.

## 3. Wildcard listener trong Spring nghĩa là gì?

Trong cấu hình Spring \`NotificationListenerBean\`, tập MBean mục tiêu có thể được chỉ định bằng ObjectName. Khi **không chỉ định tập mapped ObjectNames**, Spring exporter có thể coi listener này như một **wildcard listener** áp dụng cho các MBean phù hợp **mà exporter quản lý**.

Ý tưởng:

\`\`\`text
                     Spring MBeanExporter
                      /       |        \
                     v        v         v
                 MBean A   MBean B    MBean C
                   |         |          |
                   +---------+----------+
                             |
                      wildcard listener
                             |
                             v
                     handleNotification
\`\`\`

Điểm quan trọng:

- Wildcard này là **quy tắc ánh xạ listener của Spring exporter**, không phải cú pháp \`ObjectName("*:*")\`.
- Nó không tự động nghe mọi MBean trong toàn bộ JVM.
- Nó không bắt buộc nghe các MBean được thư viện khác hoặc application context khác đăng ký.
- Nó không đảm bảo các MBean không phát notification bỗng nhiên phát được.
- Nó không phải cơ chế subscription bền vững, lưu trữ hay replay event.

Theo cơ chế thông dụng của Spring, một \`NotificationListenerBean\` không có \`mappedObjectNames\` được xem là listener ánh xạ rộng trong phạm vi những MBean do exporter quản lý. Khi cần một bộ MBean cụ thể, hãy cấu hình danh sách ObjectName rõ ràng.

## 4. Wildcard mapping khác ObjectName pattern

JMX hỗ trợ \`ObjectName\` dạng pattern:

\`\`\`text
app.management:type=Worker,*
app.management:*
*:type=Queue,*
\`\`\`

Các pattern này dùng với API truy vấn:

\`\`\`java
Set<ObjectName> names = server.queryNames(
    new ObjectName("app.management:type=Worker,*"),
    null
);
\`\`\`

Trong khi đó, wildcard listener của Spring exporter là cách **không giới hạn listener tới một danh sách ObjectName cụ thể** trong cấu hình \`NotificationListenerBean\`.

Hai ý nghĩa:

| Cơ chế | Mục tiêu | Phạm vi |
|---|---|---|
| ObjectName pattern | Truy vấn hoặc chọn tên MBean theo quy tắc | Những tên matching trong server được truy vấn |
| Spring wildcard listener | Đăng ký listener trên những MBean exporter quản lý | Những MBean phù hợp trong phạm vi exporter |
| NotificationFilter | Chọn notification nào được chuyển tới listener | Các event sau khi listener đã được gắn |
| NotificationFilterSupport | Lọc theo prefix của \`Notification.getType()\` | Event type, không phải ObjectName |

Không nên dùng wildcard mapping như một thay thế cho kiểm soát security, ownership hoặc giới hạn event type.

## 5. Ví dụ một MBean phát notification

### 5.1. Spring bean với NotificationPublisherAware

Spring hỗ trợ \`NotificationPublisherAware\` để exporter cung cấp \`NotificationPublisher\` cho bean cần phát thông báo.

\`\`\`java
package example.jmx;

import java.util.concurrent.atomic.AtomicLong;
import javax.management.Notification;

import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.jmx.export.notification.NotificationPublisher;
import org.springframework.jmx.export.notification.NotificationPublisherAware;

@ManagedResource(
    objectName = "app.management:type=JobMonitor,name=main"
)
public class JobMonitor
        implements NotificationPublisherAware {

    private final AtomicLong sequence = new AtomicLong();

    private NotificationPublisher publisher;

    @Override
    public void setNotificationPublisher(
            NotificationPublisher publisher
    ) {
        this.publisher = publisher;
    }

    @ManagedOperation(description = "Complete a sample job")
    public void completeJob(String jobId) {
        Notification event = new Notification(
            "app.job.completed",
            this,
            sequence.incrementAndGet(),
            System.currentTimeMillis(),
            "Job completed: " + jobId
        );

        event.setUserData(jobId);
        publisher.sendNotification(event);
    }
}
\`\`\`

Ví dụ giả định bean đã được Spring tạo và exporter hoàn tất export trước khi gọi \`completeJob\`. Nếu gọi quá sớm, publisher có thể chưa được cấp cho bean. Trong code production, cần validate input và tránh đưa secret hoặc dữ liệu cá nhân vào \`message\`/\`userData\`.

### 5.2. Metadata notification

Để công cụ quản trị biết những loại event dự kiến, Spring cung cấp metadata annotation:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedNotification;
import org.springframework.jmx.export.annotation.ManagedNotifications;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "app.management:type=JobMonitor,name=main"
)
@ManagedNotifications({
    @ManagedNotification(
        name = "app.job.completed",
        description = "Job completion event",
        notificationTypes = { "app.job.completed" }
    )
})
public class JobMonitor {
    // Kết hợp nội dung implementation
    // và NotificationPublisherAware ở ví dụ trên.
}
\`\`\`

Khối code này minh họa metadata cần bổ sung trên **cùng class thực sự được export**; không tạo một class thứ hai có cùng ObjectName. Annotation metadata không tự phát event. Bean cần thực hiện \`publisher.sendNotification(...)\`.

## 6. Viết NotificationListener

\`\`\`java
package example.jmx;

import javax.management.Notification;
import javax.management.NotificationListener;

public class JobEventListener implements NotificationListener {

    @Override
    public void handleNotification(
            Notification notification,
            Object handback
    ) {
        System.out.printf(
            "type=%s source=%s seq=%d%n",
            notification.getType(),
            notification.getSource(),
            notification.getSequenceNumber()
        );
        System.out.println(
            "message=" + notification.getMessage()
        );
    }
}
\`\`\`

\`handback\` là đối tượng ngữ cảnh do phía đăng ký listener cung cấp, không phải \`Notification.userData\`.

\`\`\`text
Notification.userData
  -> payload do broadcaster phát

handback
  -> context của listener registration
\`\`\`

Một listener có thể được đăng ký với nhiều MBean; khi đó nên đọc \`notification.getSource()\` và \`notification.getType()\` để phân biệt sự kiện. Tuy nhiên source không nên bị ép kiểu thành implementation Spring bean vì client/adapter có thể biểu diễn nguồn bằng ObjectName hoặc object khác.

## 7. Cấu hình wildcard bằng NotificationListenerBean

Cách cấu hình trọng tâm:

\`\`\`java
import org.springframework.jmx.export.notification.NotificationListenerBean;

NotificationListenerBean listenerBean =
    new NotificationListenerBean();

listenerBean.setNotificationListener(
    new JobEventListener()
);

// Không gọi setMappedObjectNames(...):
// listener được cấu hình theo wildcard mapping
// trong phạm vi exporter quản lý.
\`\`\`

Sau đó đưa listener vào exporter:

\`\`\`java
MBeanExporter exporter = new MBeanExporter();

exporter.setNotificationListeners(listenerBean);
\`\`\`

Đây là các đoạn cấu hình minh họa. Exporter phải còn được cấp \`MBeanServer\`, bean mapping hoặc autodetection phù hợp và trải qua lifecycle của Spring trước khi listener thực sự được đăng ký.

Spring cũng hỗ trợ khai báo listener dưới dạng bean riêng để injection dependency, logging và cleanup được quản lý trong container.

## 8. Ví dụ Java configuration đầy đủ với exporter tường minh

Ví dụ dùng một \`MBeanExporter\` do ứng dụng kiểm soát:

\`\`\`java
package example.jmx;

import java.lang.management.ManagementFactory;
import java.util.Map;
import javax.management.MBeanServer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.notification.NotificationListenerBean;

@Configuration
public class JmxNotificationConfig {

    @Bean
    public MBeanServer managementServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public JobMonitor jobMonitor() {
        return new JobMonitor();
    }

    @Bean
    public JobEventListener jobEventListener() {
        return new JobEventListener();
    }

    @Bean
    public MBeanExporter managementExporter(
            MBeanServer managementServer,
            JobMonitor jobMonitor,
            JobEventListener jobEventListener
    ) {
        NotificationListenerBean listener =
            new NotificationListenerBean();
        listener.setNotificationListener(jobEventListener);

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(managementServer);
        exporter.setBeans(Map.of(
            "app.management:type=JobMonitor,name=main",
            jobMonitor
        ));
        exporter.setNotificationListeners(listener);

        return exporter;
    }
}
\`\`\`

Trong cùng một exporter, có thể thêm MBean khác có khả năng phát notification. Khi wildcard listener được áp dụng, listener có thể nhận những notification từ các broadcaster mà exporter đăng ký và quản lý.

**Cảnh báo cấu hình:** nếu ứng dụng đồng thời bật \`@EnableMBeanExport\` hoặc auto-configuration tạo exporter khác cho cùng bean, có thể phát sinh đăng ký trùng. Ví dụ dùng exporter tường minh để thể hiện rõ listener mapping; trong ứng dụng thực, hãy chọn cơ chế export thống nhất.

## 9. Listener chỉ nhận những event nào?

Giả sử exporter quản lý ba MBean:

\`\`\`text
app.management:type=JobMonitor,name=main
app.management:type=QueueMonitor,name=orders
app.management:type=CacheMonitor,name=primary
\`\`\`

Trong đó:

- JobMonitor phát \`app.job.completed\`.
- QueueMonitor phát \`app.queue.threshold\`.
- CacheMonitor chỉ có attribute, không phát notification.

Wildcard listener có thể nhận event từ JobMonitor và QueueMonitor khi các MBean này hỗ trợ broadcaster và listener được gắn thành công.

CacheMonitor không tự tạo notification chỉ vì wildcard listener tồn tại.

Nếu một MBean khác:

\`\`\`text
third.party:type=LibraryMonitor
\`\`\`

do thành phần khác đăng ký trực tiếp vào cùng MBeanServer, wildcard mapping của exporter không mặc nhiên bao phủ nó.

Do đó, “wildcard” mô tả phạm vi MBean exporter **chủ động quản lý**, không phải quyền truy cập vô hạn vào toàn bộ JMX registry.

## 10. Lọc event type bằng NotificationFilter

Không phải mọi event thuộc exporter đều cần đưa tới cùng một consumer. Có thể thêm filter để giới hạn loại thông báo.

\`\`\`java
import javax.management.NotificationFilter;

NotificationFilter completedOnly =
    event -> "app.job.completed".equals(event.getType());

NotificationListenerBean listener =
    new NotificationListenerBean();

listener.setNotificationListener(
    new JobEventListener()
);
listener.setNotificationFilter(completedOnly);
\`\`\`

Bộ lọc này quyết định callback nào được nhận, nhưng **không thay đổi MBean mục tiêu**. Nếu listener vẫn là wildcard, nó được gắn trên các broadcaster trong phạm vi exporter rồi lọc event type tương ứng.

### NotificationFilterSupport

\`\`\`java
import javax.management.NotificationFilterSupport;

NotificationFilterSupport filter =
    new NotificationFilterSupport();

filter.enableType("app.job.");
\`\`\`

\`NotificationFilterSupport\` thường thực hiện prefix matching: cấu hình \`app.job.\` cho phép các type như \`app.job.completed\` và \`app.job.failed\`. Nếu muốn **đúng một type**, dùng \`equals\` hoặc filter tự viết.

## 11. Chỉ định MBean cụ thể khi không muốn wildcard

Một listener chỉ nên nghe một số broadcaster được chọn nếu nghiệp vụ cần scope hẹp.

Ví dụ dùng \`NotificationListenerBean.setMappedObjectNames\`:

\`\`\`java
NotificationListenerBean listener =
    new NotificationListenerBean();

listener.setNotificationListener(
    new JobEventListener()
);

listener.setMappedObjectNames(
    "app.management:type=JobMonitor,name=main",
    "app.management:type=JobMonitor,name=batch"
);
\`\`\`

Khi đã chỉ định ObjectName, exporter ánh xạ listener theo danh sách mục tiêu được cấu hình thay vì wildcard cho mọi MBean do nó quản lý.

Cần dùng ObjectName thực tế mà exporter đăng ký. Nếu bean được đổi tên, naming strategy thay đổi hoặc nhiều instance có key properties khác nhau, listener có thể không được gắn nơi mong đợi.

Nếu tập MBean rất lớn nhưng chỉ có một loại event liên quan, có thể phối hợp **mapped names** và **notification filter** để giảm phạm vi và giảm xử lý không cần thiết.

## 12. Một listener cho nhiều MBean: nhận diện nguồn

Khi wildcard listener nhận nhiều loại event, code callback nên phân loại rõ:

\`\`\`java
@Override
public void handleNotification(
        Notification notification,
        Object handback
) {
    String type = notification.getType();

    switch (type) {
        case "app.job.completed":
            onJobCompleted(notification);
            break;
        case "app.queue.threshold":
            onQueueThreshold(notification);
            break;
        default:
            // Bỏ qua hoặc ghi nhận theo policy.
    }
}
\`\`\`

Các phương thức \`onJobCompleted\` và \`onQueueThreshold\` là helper của ứng dụng minh họa.

Nên kết hợp \`type\`, \`source\` và mã tương quan nếu cần truy vết. \`sequenceNumber\` thường là counter theo broadcaster, không phải thứ tự toàn cục cho tất cả MBean.

Cẩn thận với việc log \`userData\`: nó có thể chứa object domain, thông tin khách hàng hoặc token nếu producer thiết kế không phù hợp.

## 13. Lifecycle listener và exporter

Spring exporter có trách nhiệm đăng ký MBean và những listener được cấu hình với exporter đó theo lifecycle phù hợp.

\`\`\`text
ApplicationContext startup
          |
          v
MBeanExporter initialization
          |
          +--> Register MBean A
          +--> Register MBean B
          |
          +--> Register listener với MBean phù hợp
          |
          v
MBeanServer active
          |
          v
ApplicationContext shutdown
          |
          +--> Cleanup listener registrations
          +--> Unregister MBeans thuộc phạm vi quản lý
\`\`\`

Thứ tự nội bộ cụ thể phụ thuộc phiên bản Spring và exporter implementation. Không dùng sơ đồ như bảo đảm toàn bộ listener được gắn trước mọi event startup.

Nếu một bean phát notification trong constructor hoặc quá sớm ở \`@PostConstruct\`, listener có thể chưa được đăng ký và mất event. Với sự kiện bắt buộc phải nhận, hãy thiết kế lifecycle rõ hoặc một cơ chế event bền vững riêng.

## 14. MBean được đăng ký động sau startup

Một câu hỏi quan trọng: nếu exporter quản lý MBean mới phát sinh sau khi wildcard listener đã cấu hình, listener có tự gắn không?

Hành vi phụ thuộc vào cơ chế registration động và API exporter đang sử dụng. Spring có thể quản lý listener registrations cho MBean mà chính nó đăng ký, nhưng không nên giả định wildcard listener sẽ tự theo dõi mọi MBean được thêm bởi **mã bên ngoài** hoặc mọi trường hợp dynamic registration.

Trong hệ thống có MBean động:

1. Xác định MBean được tạo và đăng ký qua đường nào.
2. Xác định exporter có quản lý registration đó không.
3. Kiểm tra listener đã được gắn sau khi MBean xuất hiện chưa.
4. Test bằng cách phát một notification có type và timestamp biết trước.
5. Cân nhắc tự quản lý subscription khi registry thay đổi nếu cần độ bao phủ cao.

Nếu listener phải theo dõi MBean do bên ngoài đăng ký, có thể dùng JMX API trực tiếp với \`MBeanServerConnection.addNotificationListener\`, kết hợp theo dõi registry qua \`MBeanServerDelegate\`.

## 15. Theo dõi thay đổi registry bằng MBeanServerDelegate

JMX có một MBean delegate phát các notification liên quan đến MBean được đăng ký/hủy đăng ký.

\`\`\`java
import javax.management.MBeanServerDelegate;
import javax.management.MBeanServerNotification;
import javax.management.NotificationListener;

NotificationListener registryListener =
    (notification, handback) -> {
        if (notification instanceof MBeanServerNotification event) {
            System.out.println(
                event.getType() + " " + event.getMBeanName()
            );
        }
    };

server.addNotificationListener(
    MBeanServerDelegate.DELEGATE_NAME,
    registryListener,
    null,
    null
);
\`\`\`

Client có thể quan sát \`JMX.mbean.registered\` và \`JMX.mbean.unregistered\` để quyết định có phải gắn listener cho MBean mới không.

Nếu thêm cơ chế này, phải xử lý race giữa query registry, đăng ký listener và MBean thay đổi. Đừng quên \`removeNotificationListener\` cho delegate khi dừng.

## 16. Unregister/re-register và RegistrationPolicy

Giả sử exporter thay thế một MBean dưới cùng ObjectName bằng \`RegistrationPolicy.REPLACE_EXISTING\`:

\`\`\`text
ObjectName X
   -> Old broadcaster
   -> unregister
   -> New broadcaster
   -> register
\`\`\`

Listener gắn với broadcaster cũ không tự động chuyển sang broadcaster mới chỉ vì ObjectName giữ nguyên.

Với dynamic replacement, cần kiểm chứng exporter có tái gắn listener theo lifecycle hay không. Trong tình huống client tự quản lý subscription, cần đăng ký lại đúng thời điểm.

Không coi \`REPLACE_EXISTING\` là cơ chế chuyển toàn bộ notification state hoặc listener registrations.

## 17. Tránh xử lý nặng trong handleNotification

\`NotificationListener.handleNotification\` là callback do hệ thống gửi notification gọi. Tùy broadcaster/connector và cấu hình, dispatch có thể đồng bộ hoặc bất đồng bộ.

Không nên:

\`\`\`java
@Override
public void handleNotification(
        Notification notification,
        Object handback
) {
    callRemoteServiceWithNoTimeout();
    performHeavyDatabaseAggregation();
}
\`\`\`

Thay bằng xử lý nhanh:

\`\`\`java
@Override
public void handleNotification(
        Notification notification,
        Object handback
) {
    if (!"app.job.completed".equals(notification.getType())) {
        return;
    }

    eventExecutor.execute(
        () -> processEvent(notification)
    );
}
\`\`\`

\`eventExecutor\` và \`processEvent\` là thành phần do ứng dụng cung cấp. Khi đưa vào executor, cần xác định queue capacity, rejection policy, shutdown và cách xử lý exception. Tránh tạo queue vô hạn hoặc nuốt lỗi âm thầm.

Một listener wildcard có thể nhận số lượng event lớn; nếu mọi event đều bị xử lý nặng, tác động hiệu năng có thể lan rộng trên toàn bộ các MBean broadcaster của exporter.

## 18. Kiểm tra wildcard listener bằng kịch bản lặp lại

Một kịch bản kiểm tra tốt:

1. Tạo hai MBean broadcaster trong cùng exporter.
2. Cấu hình \`NotificationListenerBean\` không có mapped ObjectNames.
3. Bật filter nhận type \`app.job.\` nếu chỉ muốn một nhóm sự kiện.
4. Hoàn tất Spring context initialization.
5. Gọi operation phát notification trên MBean A.
6. Gọi operation phát notification trên MBean B.
7. Quan sát callback và thống kê source/type.
8. Thử MBean C không thuộc exporter, nếu có quyền và môi trường test riêng.
9. Xác nhận listener không tự nhận notification từ C nếu nó không được đăng ký cho C.
10. Đóng context và kiểm tra cleanup theo lifecycle đã thiết kế.

Kết quả phải được xác nhận bằng callback thực tế, không chỉ từ việc Spring bean listener tồn tại trong ApplicationContext.

## 19. Kiểm tra bằng MBeanServerConnection

Một công cụ kiểm thử độc lập có thể đăng ký listener trực tiếp với MBean:

\`\`\`java
import javax.management.MBeanServerConnection;
import javax.management.NotificationListener;
import javax.management.ObjectName;

ObjectName name = new ObjectName(
    "app.management:type=JobMonitor,name=main"
);

NotificationListener listener =
    (notification, handback) -> {
        System.out.println(notification.getType());
    };

connection.addNotificationListener(
    name,
    listener,
    null,
    null
);

try {
    connection.invoke(
        name,
        "completeJob",
        new Object[] { "job-001" },
        new String[] { "java.lang.String" }
    );
} finally {
    connection.removeNotificationListener(
        name,
        listener
    );
}
\`\`\`

\`connection\` cần trỏ đúng MBeanServer exporter đã sử dụng. Đối với remote connection, có thể phải chờ notification bằng \`CountDownLatch\` có timeout trước khi hủy listener, tránh bỏ lỡ callback trên đường truyền.

Điều này giúp xác minh producer có phát event không, nhưng **không thay thế** phép kiểm tra Spring wildcard mapping. Để xác minh wildcard, phải quan sát chính listener cấu hình trong exporter nhận event từ các broadcaster khác nhau.

## 20. Khi nào chọn wildcard và khi nào chọn mapping tường minh?

| Bối cảnh | Lựa chọn gợi ý | Lý do |
|---|---|---|
| Một exporter chuyên quản lý nhóm MBean cùng mục đích, cùng chuẩn event | Wildcard listener + filter | Cấu hình gọn, dễ bao phủ các broadcaster của exporter |
| Nhiều MBean không liên quan và volume event lớn | Mapped ObjectNames | Hạn chế callback/chi phí xử lý |
| MBean của nhiều ứng dụng/thư viện chia sẻ một server | Mapping rõ ràng hoặc JMX API riêng | Wildcard exporter không bao phủ toàn registry |
| Listener cần audit event đặc thù | Mapping hẹp + filter chính xác | Dễ xác minh ownership và data policy |
| MBean đăng ký động qua nhiều cơ chế | Chủ động theo dõi registry và subscription | Giảm giả định về phạm vi exporter |
| Chỉ cần health/metrics tổng hợp | Có thể không cần notification listener | Polling metrics/Actuator có thể phù hợp hơn |

Wildcard là công cụ tiện lợi **trong phạm vi quản lý của exporter**. Nó không nên thay thế việc thiết kế event contract và giới hạn thông tin nhạy cảm.

## 21. Rủi ro khi wildcard listener nhận quá nhiều event

- **Nhiễu thông tin:** nhiều broadcaster phát các type không liên quan.
- **Hiệu năng:** callback có thể chiếm tài nguyên ở luồng dispatch.
- **Trùng xử lý:** listener được đăng ký nhiều lần hoặc nhiều exporter cùng xử lý MBean.
- **Bảo mật dữ liệu:** log \`userData\` từ MBean không được kiểm soát.
- **Khó audit:** không rõ event đến từ MBean nào nếu không log source phù hợp.
- **Lifecycle:** listener có thể bỏ lỡ event khi startup/restart hoặc MBean replacement.
- **Khả năng mở rộng:** số lượng MBean/notification tăng theo deployment.

Nên có filter, log cấu trúc, giới hạn xử lý và test integration với nhiều MBean. Không coi số event nhận được bằng số sự kiện nghiệp vụ xảy ra trong mọi hoàn cảnh; notification không mặc định có durable delivery.

## 22. Phân biệt NotificationListenerBean với NotificationPublisherAware

Hai API có vai trò đối diện:

\`\`\`text
NotificationPublisherAware
    -> Bean phát notification

NotificationListenerBean
    -> Cấu hình phía nhận notification
\`\`\`

\`NotificationPublisherAware\` cho phép Spring cấp \`NotificationPublisher\` vào bean export. Bean tự tạo \`Notification\` và gọi \`sendNotification\`.

\`NotificationListenerBean\` mô tả một listener, optional filter và danh sách MBean mục tiêu. Exporter dùng cấu hình này để đăng ký listener tương ứng.

Một class có cả publisher và listener không bị cấm, nhưng nên phân biệt trách nhiệm để tránh vòng lặp sự kiện hoặc xử lý khó kiểm soát.

## 23. Câu hỏi tự kiểm tra

1. Wildcard listener của Spring exporter có đồng nghĩa với nghe tất cả MBean trong JVM không?
2. Vì sao \`NotificationListenerBean\` không chỉ định mapped ObjectNames có thể trở thành wildcard listener?
3. NotificationFilter chọn MBean hay chọn loại notification?
4. \`NotificationFilterSupport.enableType("app.job.")\` có matching prefix không?
5. Có cần MBean hỗ trợ broadcaster để listener nhận notification không?
6. Vì sao không nên xử lý network I/O nặng trực tiếp trong callback?
7. Listener có tự nhận event đã xảy ra trước khi nó được đăng ký không?
8. Một MBean do thư viện khác đăng ký có mặc nhiên thuộc phạm vi wildcard của exporter không?
9. Khi MBean bị unregister/re-register cùng tên, listener cũ có chắc tiếp tục nhận event không?
10. Muốn xác minh wildcard hoạt động, vì sao cần kiểm tra chính Spring listener thay vì chỉ dùng một listener JMX độc lập?

## 24. Ghi nhớ

\`\`\`text
MBeanExporter
   |
   +-- quản lý MBean A (broadcaster)
   +-- quản lý MBean B (broadcaster)
   +-- quản lý MBean C (không phát event)
   |
   +-- NotificationListenerBean
          |
          +-- mappedObjectNames không chỉ định
          |       -> wildcard trong phạm vi exporter
          |
          +-- NotificationFilter (nếu có)
                  -> lọc event type
\`\`\`

**Kết luận:** wildcard listener trong Spring JMX là cách cấu hình một \`NotificationListenerBean\` nghe các broadcaster thuộc phạm vi \`MBeanExporter\` quản lý, thay vì kê từng ObjectName. Nó **không** là subscription toàn JVM, **không** thay thế filter và **không** bảo đảm nhận event trước lúc đăng ký hoặc sau khi MBean được thay thế. Hãy kiểm tra đúng phạm vi exporter, metadata, subscription lifecycle và luồng xử lý callback.