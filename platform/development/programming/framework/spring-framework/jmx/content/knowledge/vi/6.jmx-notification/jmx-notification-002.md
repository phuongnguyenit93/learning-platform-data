# NotificationBroadcaster và NotificationEmitter trong Spring Framework JMX

> **Chủ đề:** Spring Framework JMX  
> **Nhóm kiến thức:** Notification  
> **Bài học:** NotificationBroadcaster và NotificationEmitter

## 1. Mục tiêu

Sau bài học, bạn có thể:

- Phân biệt **JMX notification** với thuộc tính (attribute), thao tác (operation), application event của Spring và message broker.
- Hiểu các hợp đồng \`NotificationBroadcaster\`, \`NotificationEmitter\`, \`NotificationListener\` và \`NotificationFilter\`, cũng như vai trò của \`NotificationBroadcasterSupport\`.
- Biết cách viết MBean phát notification, công bố metadata notification và quản lý listener.
- Đăng ký, lọc, nhận và hủy đăng ký listener qua \`MBeanServer\`/\`MBeanServerConnection\`.
- Hiểu luồng notification từ Spring bean được export qua JMX đến công cụ quản trị, cùng các giới hạn vòng đời, đồng thời và kết nối từ xa.

## 2. Mô hình tư duy: JMX notification là tín hiệu do MBean phát

Trong JMX, MBean có thể công bố trạng thái qua **attribute**, cho phép client kích hoạt hành động qua **operation**, và chủ động phát **notification** khi một sự kiện quản trị xảy ra. Ví dụ, một pool vượt ngưỡng tải, một tác vụ hoàn tất, cache được làm mới hoặc một thuộc tính quản trị thay đổi.

\`\`\`text
                   ỨNG DỤNG / JVM
  +------------------------------------------------+
  | Spring bean / MBean                            |
  |   - quản lý trạng thái                         |
  |   - thực thi operation                         |
  |   - phát Notification khi sự kiện xảy ra       |
  |                       |                        |
  |                NotificationBroadcaster         |
  |                       |                        |
  |                  MBeanServer                   |
  +-----------------------|------------------------+
                          |
             listener đã đăng ký qua JMX
                          |
             +------------+--------------+
             |                           |
      Local JMX client           Remote JMX connector
             |                           |
             v                           v
      NotificationListener        NotificationListener
             |                           |
      log / cảnh báo / UI        quản trị / giám sát
\`\`\`

Notification **không đồng nghĩa** dữ liệu được lưu vào hàng đợi bền vững. Nó là cơ chế thông báo sự kiện cho những listener đang được đăng ký. Nếu client chưa đăng ký, bị ngắt kết nối hoặc không xử lý kịp, ứng dụng không nên mặc định rằng sẽ có lịch sử phát lại. Khi cần audit bền vững, phải dùng thêm hệ thống log, event store hoặc message broker phù hợp.

Trong Spring Framework JMX, bean có thể được xuất bản thông qua \`MBeanExporter\` hoặc \`@EnableMBeanExport\`. MBean đã export vẫn tuân theo hợp đồng JMX: listener tương tác qua \`MBeanServer\`, chứ không gọi thẳng \`ApplicationContext\` để nghe notification.

## 3. Các interface và lớp liên quan

| API | Vai trò | Phương thức nổi bật |
|---|---|---|
| \`NotificationBroadcaster\` | Hợp đồng của đối tượng có thể đăng ký/hủy listener và công bố loại notification. | \`addNotificationListener\`, \`removeNotificationListener\`, \`getNotificationInfo\` |
| \`NotificationEmitter\` | Mở rộng broadcaster, hỗ trợ hủy **một đăng ký cụ thể** theo listener/filter/handback. | \`removeNotificationListener(listener, filter, handback)\` |
| \`NotificationBroadcasterSupport\` | Lớp hỗ trợ triển khai broadcaster/emitter, giữ danh sách listener và cung cấp \`sendNotification\`. | \`sendNotification\`, \`getNotificationInfo\` |
| \`NotificationListener\` | Callback nhận notification. | \`handleNotification(Notification, Object)\` |
| \`NotificationFilter\` | Quyết định từng notification có được chuyển đến listener không. | \`isNotificationEnabled(Notification)\` |
| \`NotificationFilterSupport\` | Bộ lọc thuận tiện dựa trên tiền tố notification type. | \`enableType\`, \`disableType\`, \`disableAllTypes\` |
| \`Notification\` | Dữ liệu sự kiện JMX: type, source, sequence, timestamp, message, userData. | \`getType\`, \`getSource\`, \`getSequenceNumber\` |
| \`MBeanNotificationInfo\` | Metadata mô tả loại notification mà MBean có thể phát. | \`getNotifTypes\`, \`getDescription\` |

**Điểm phân biệt quan trọng:** \`NotificationBroadcaster\` chỉ có phương thức \`removeNotificationListener(NotificationListener)\` ở hợp đồng cơ bản. \`NotificationEmitter\` bổ sung overload nhận cả \`NotificationFilter\` và \`handback\`, nhờ đó có thể gỡ đúng một registration.

Mối quan hệ kế thừa:

\`\`\`text
NotificationBroadcaster
        |
        v
NotificationEmitter
        ^
        |
NotificationBroadcasterSupport

NotificationListener  <-- callback độc lập
NotificationFilter    <-- điều kiện chuyển tiếp
\`\`\`

Ở phía MBeanServer, client còn có các overload \`addNotificationListener\` và \`removeNotificationListener\`, nhận \`ObjectName\` của MBean phát, khác với việc gọi trực tiếp vào object broadcaster.

## 4. NotificationBroadcaster quy định những gì?

Giao diện JMX:

\`\`\`java
public interface NotificationBroadcaster {

    void addNotificationListener(
        NotificationListener listener,
        NotificationFilter filter,
        Object handback
    );

    void removeNotificationListener(
        NotificationListener listener
    ) throws ListenerNotFoundException;

    MBeanNotificationInfo[] getNotificationInfo();
}
\`\`\`

Ba trách nhiệm là:

1. **Thêm listener**: giữ một subscription gồm callback, filter có thể \`null\` và handback có thể \`null\`.
2. **Xóa listener**: gỡ các registration liên quan tới listener theo hợp đồng của broadcaster.
3. **Mô tả notification**: cung cấp metadata về những loại có thể phát.

Giao diện cơ bản không tự cung cấp một API \`sendNotification\` công khai. Đối tượng triển khai phải tự tổ chức việc phát notification. Với \`NotificationBroadcasterSupport\`, phần lớn cơ sở hạ tầng này đã được triển khai và ta gọi \`sendNotification(notification)\` khi có sự kiện.

### Vì sao có \`getNotificationInfo()\`?

Một công cụ như JConsole hoặc client dùng \`MBeanServer.getMBeanInfo(name)\` để đọc metadata. \`MBeanNotificationInfo\` cho biết các loại notification dự kiến, chẳng hạn:

\`\`\`text
Type: app.job.completed
Java class: javax.management.Notification
Description: A job has completed
\`\`\`

Metadata giúp client khám phá khả năng quan sát. Tuy nhiên, bản thân metadata không tự phát sự kiện. Implementation vẫn phải gọi cơ chế phát tương ứng. Một MBean báo có notification mà không bao giờ phát thì listener sẽ không nhận được gì.

## 5. NotificationEmitter bổ sung điều gì?

\`NotificationEmitter\` kế thừa \`NotificationBroadcaster\` và thêm:

\`\`\`java
void removeNotificationListener(
    NotificationListener listener,
    NotificationFilter filter,
    Object handback
) throws ListenerNotFoundException;
\`\`\`

Giả sử cùng một listener được đăng ký hai lần:

\`\`\`java
broadcaster.addNotificationListener(
    listener, filterA, "A"
);
broadcaster.addNotificationListener(
    listener, filterB, "B"
);
\`\`\`

Với \`NotificationBroadcaster.removeNotificationListener(listener)\`, nhiều implementation sẽ gỡ **toàn bộ** registration gắn với listener này. Với \`NotificationEmitter.removeNotificationListener(listener, filterA, "A")\`, ta có thể nhắm riêng registration A mà giữ registration B.

Cách hoạt động chi tiết tuân theo hợp đồng JMX về registration và so khớp listener/filter/handback. Vì thế hãy lưu giữ đúng các tham chiếu filter và handback dùng lúc đăng ký, tránh tạo một filter mới có cùng cấu hình nhưng không phải registration đã dùng.

## 6. NotificationBroadcasterSupport giúp đơn giản hóa implementation

Lớp \`javax.management.NotificationBroadcasterSupport\` cung cấp sẵn:

- Quản lý danh sách listener.
- Áp dụng filter trước khi gửi notification tới mỗi listener.
- Đưa handback đã đăng ký vào callback.
- \`sendNotification(Notification)\` để phát sự kiện.
- Các constructor cho phép cung cấp executor và metadata thông báo.

Có thể kế thừa lớp này rồi chỉ viết logic phát notification:

\`\`\`java
public class JobMonitor extends NotificationBroadcasterSupport
        implements JobMonitorMBean {
    // Business state + gọi sendNotification(...) khi có sự kiện.
}
\`\`\`

Lưu ý rằng \`NotificationBroadcasterSupport\` có thể dispatch callback bằng executor tùy constructor. Với cấu hình mặc định, nó thường thực hiện delivery đồng bộ trên thread phát; nếu cung cấp executor bất đồng bộ, thời điểm callback thay đổi. Với client kết nối từ xa qua JMX connector, hành vi callback còn phụ thuộc tầng truyền tải. Không nên thiết kế business logic giả định listener luôn chạy cùng thread hoặc nhất định nhận sự kiện trước khi lời gọi operation trả về.

## 7. Ví dụ đầy đủ: MBean phát notification khi hoàn thành job

Ví dụ độc lập dùng JMX chuẩn, có thể chạy trong JVM mà không cần Spring hoặc remote connector. Sau đó ta sẽ đưa MBean này vào Spring.

### 7.1. Định nghĩa Standard MBean interface

\`\`\`java
package example.jmx;

public interface JobMonitorMBean {
    long getCompletedJobs();

    String completeJob(String jobId);
}
\`\`\`

Theo quy tắc Standard MBean, class triển khai \`JobMonitorMBean\` có thể expose attribute \`CompletedJobs\` và operation \`completeJob(String)\`.

### 7.2. Viết broadcaster

\`\`\`java
package example.jmx;

import java.util.concurrent.atomic.AtomicLong;
import javax.management.MBeanNotificationInfo;
import javax.management.Notification;
import javax.management.NotificationBroadcasterSupport;

public class JobMonitor extends NotificationBroadcasterSupport
        implements JobMonitorMBean {

    public static final String JOB_COMPLETED =
        "app.job.completed";

    private final AtomicLong completedJobs =
        new AtomicLong();

    private final AtomicLong notificationSequence =
        new AtomicLong();

    @Override
    public long getCompletedJobs() {
        return completedJobs.get();
    }

    @Override
    public String completeJob(String jobId) {
        if (jobId == null || jobId.isBlank()) {
            throw new IllegalArgumentException(
                "jobId must not be blank"
            );
        }

        completedJobs.incrementAndGet();

        Notification event = new Notification(
            JOB_COMPLETED,
            this,
            notificationSequence.incrementAndGet(),
            System.currentTimeMillis(),
            "Completed job: " + jobId
        );
        event.setUserData(jobId);
        sendNotification(event);

        return "completed:" + jobId;
    }

    @Override
    public MBeanNotificationInfo[] getNotificationInfo() {
        return new MBeanNotificationInfo[] {
            new MBeanNotificationInfo(
                new String[] { JOB_COMPLETED },
                Notification.class.getName(),
                "Notification emitted when a job completes"
            )
        };
    }
}
\`\`\`

Trong ví dụ:

- \`completedJobs\` lưu số lần gọi thành công ở logic minh họa.
- \`notificationSequence\` cấp sequence number tăng dần cho các sự kiện do instance này phát.
- \`type\` là \`app.job.completed\`, tiện để filter.
- \`source\` được truyền là \`this\` trong implementation local; khi truy cập qua MBeanServer/remote client, nguồn có thể được biểu diễn hoặc thay đổi theo cơ chế JMX, vì vậy client nên dùng ObjectName đăng ký và metadata phù hợp thay vì ép \`source\` về class implementation.
- \`userData\` chứa mã job. Để remote client đọc \`userData\`, dữ liệu phải có dạng truyền qua JMX connector phù hợp. \`String\` là lựa chọn đơn giản.

Phương thức \`completeJob\` chỉ là ví dụ phát event. Trong ứng dụng thực, công việc xử lý job có thể hoàn thành ở một thread khác; hãy phát notification khi sự kiện **thực sự hoàn thành**, thay vì luôn phát ngay khi nhận yêu cầu.

### 7.3. Đăng ký với MBeanServer và gắn listener

\`\`\`java
package example.jmx;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.NotificationFilterSupport;
import javax.management.NotificationListener;
import javax.management.ObjectName;

public class JobMonitorDemo {

    public static void main(String[] args) throws Exception {
        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
            "learning.jmx:type=JobMonitor,name=main"
        );

        server.registerMBean(new JobMonitor(), name);

        NotificationListener listener =
            (notification, handback) -> {
                System.out.println(
                    "type=" + notification.getType()
                        + ", seq="
                        + notification.getSequenceNumber()
                        + ", message="
                        + notification.getMessage()
                        + ", handback=" + handback
                );
            };

        NotificationFilterSupport filter =
            new NotificationFilterSupport();

        filter.enableType(JobMonitor.JOB_COMPLETED);

        server.addNotificationListener(
            name,
            listener,
            filter,
            "job-monitor-context"
        );

        try {
            Object result = server.invoke(
                name,
                "completeJob",
                new Object[] { "job-42" },
                new String[] { "java.lang.String" }
            );
            System.out.println("Result: " + result);
        } finally {
            server.removeNotificationListener(
                name,
                listener,
                filter,
                "job-monitor-context"
            );
            server.unregisterMBean(name);
        }
    }
}
\`\`\`

Kết quả ví dụ khi dùng cơ chế dispatch đồng bộ:

\`\`\`text
type=app.job.completed, seq=1, message=Completed job: job-42, handback=job-monitor-context
Result: completed:job-42
\`\`\`

Thứ tự log không phải một cam kết chung khi thay executor hoặc dùng remote JMX. Trong ví dụ này, listener được đăng ký **qua MBeanServer** với ObjectName, không cần biết đối tượng \`JobMonitor\` server-side đang nằm ở đâu.

## 8. Luồng chi tiết từ operation đến listener

\`\`\`text
Client
  |
  | invoke("completeJob", ["job-42"], ["java.lang.String"])
  v
MBeanServer
  |
  v
JobMonitor.completeJob("job-42")
  |
  +--> completedJobs++
  |
  +--> new Notification(
  |       type="app.job.completed",
  |       sequence=1,
  |       source=this,
  |       message="Completed job: job-42"
  |     )
  |
  v
NotificationBroadcasterSupport.sendNotification(event)
  |
  +--> kiểm tra từng registration
  |       |
  |       +--> filter cho phép?
  |                |
  |          +-----+-----+
  |          |           |
  |         YES          NO
  |          |           |
  |          v           v
  |  handleNotification  bỏ qua
  |   (event, handback)
  v
Client quan sát notification
\`\`\`

Một listener có thể nhận nhiều notification, và nhiều listener có thể cùng nghe một MBean. Từng registration có thể sử dụng filter và handback khác nhau.

Notification mang tính **event**, còn \`getCompletedJobs()\` thể hiện **state**. Nếu listener bỏ lỡ vài sự kiện, việc đọc attribute vẫn có thể giúp lấy snapshot hiện tại, nhưng không tự khôi phục toàn bộ lịch sử event.

## 9. Lọc notification bằng NotificationFilter

\`NotificationFilter\` là functional interface với:

\`\`\`java
boolean isNotificationEnabled(Notification notification);
\`\`\`

Một filter tự viết:

\`\`\`java
import javax.management.Notification;
import javax.management.NotificationFilter;

NotificationFilter importantJobs =
    (Notification notification) -> {
        if (!"app.job.completed".equals(
                notification.getType())) {
            return false;
        }

        Object data = notification.getUserData();
        return data instanceof String jobId
            && jobId.startsWith("important-");
    };
\`\`\`

Khi đăng ký:

\`\`\`java
server.addNotificationListener(
    name,
    listener,
    importantJobs,
    "important-jobs"
);
\`\`\`

Một listener chỉ được gọi khi filter chấp nhận. Nếu filter là \`null\`, mọi notification do MBean phát đều có thể được chuyển đến listener theo contract.

### NotificationFilterSupport lọc theo tiền tố

\`\`\`java
NotificationFilterSupport filter =
    new NotificationFilterSupport();

filter.enableType("app.job.");
\`\`\`

Điểm cần nhớ: \`NotificationFilterSupport\` dùng **prefix matching**. Với prefix \`app.job.\`, nó có thể nhận \`app.job.completed\`, \`app.job.failed\` hoặc \`app.job.started\`, miễn MBean phát những type đó. Nếu muốn chỉ đúng một type, dùng filter so sánh \`equals\` hoặc chọn prefix đủ đặc hiệu dựa vào quy ước tên type.

Đây là khác biệt dễ bị bỏ qua khi filter một sự kiện nhạy cảm: \`enableType("app.job.completed")\` cũng có thể khớp một type dài hơn bắt đầu bằng chuỗi đó, chẳng hạn \`app.job.completed.detail\`.

## 10. Handback là gì?

\`handback\` là object context do bên đăng ký listener truyền vào; khi có notification, JMX chuyển chính context đó cho callback:

\`\`\`java
Object handback = "pool=main";

server.addNotificationListener(
    name,
    (notification, context) -> {
        System.out.println(context);
    },
    null,
    handback
);
\`\`\`

Handback hữu ích khi cùng một callback xử lý sự kiện từ nhiều nguồn nhưng cần biết subscription nào tạo callback, ví dụ \`node\`, \`region\` hoặc tên môi trường.

Không nhầm:

- \`notification.getUserData()\`: payload do **bên phát** notification đặt vào.
- \`handback\`: context do **bên nghe** cung cấp lúc đăng ký.
- \`notification.getSource()\`: nguồn sự kiện theo JMX.
- \`ObjectName\`: định danh MBean tại MBeanServer, thường nên được lưu riêng trong dữ liệu subscription phía client.

Với kết nối remote, đặc tính truyền tải của handback phụ thuộc cơ chế connector; nên ưu tiên context nhỏ, đơn giản và phù hợp serialization.

## 11. Hủy listener: hai kiểu remove có ý nghĩa khác nhau

JMX cung cấp các overload trên \`MBeanServer\`/\`MBeanServerConnection\`:

\`\`\`java
removeNotificationListener(
    ObjectName name,
    NotificationListener listener
);

removeNotificationListener(
    ObjectName name,
    NotificationListener listener,
    NotificationFilter filter,
    Object handback
);
\`\`\`

Đối với một listener có nhiều registration trên cùng MBean:

\`\`\`java
server.addNotificationListener(
    name, listener, filterA, "A"
);
server.addNotificationListener(
    name, listener, filterB, "B"
);
\`\`\`

Gọi:

\`\`\`java
server.removeNotificationListener(
    name, listener, filterA, "A"
);
\`\`\`

nhằm tháo registration A, giữ B. Trong khi đó:

\`\`\`java
server.removeNotificationListener(
    name, listener
);
\`\`\`

gỡ các đăng ký tương ứng với listener đó trên MBean.

Một số lỗi thường gặp:

- **\`ListenerNotFoundException\`**: không có registration phù hợp để tháo.
- **\`InstanceNotFoundException\`**: MBean theo ObjectName đã không còn tồn tại.
- **Race khi shutdown**: MBean có thể được unregister trước lúc cleanup listener.
- **Đăng ký trùng**: callback được gọi nhiều lần vì cùng listener được add nhiều lần. Hãy tổ chức subscription để add một lần hoặc lưu chính xác từng registration.

Nguyên tắc: mỗi \`addNotificationListener\` phải có chiến lược \`removeNotificationListener\` tương ứng và được thực hiện khi dừng component hoặc đóng connection.

## 12. MBeanServerDelegate: notification về chính registry

JMX có MBean hệ thống \`JMImplementation:type=MBeanServerDelegate\` (hằng \`MBeanServerDelegate.DELEGATE_NAME\`). Nó phát notification khi MBean được đăng ký hoặc gỡ khỏi MBeanServer.

\`\`\`java
import javax.management.MBeanServerDelegate;
import javax.management.MBeanServerNotification;
import javax.management.NotificationListener;

NotificationListener registryListener =
    (notification, handback) -> {
        if (notification instanceof MBeanServerNotification e) {
            System.out.println(
                "Registry event: " + e.getType()
                    + " " + e.getMBeanName()
            );
        }
    };

server.addNotificationListener(
    MBeanServerDelegate.DELEGATE_NAME,
    registryListener,
    null,
    null
);

try {
    // Theo dõi việc đăng ký hoặc hủy MBean.
} finally {
    server.removeNotificationListener(
        MBeanServerDelegate.DELEGATE_NAME,
        registryListener
    );
}
\`\`\`

Loại sự kiện thường gặp gồm \`JMX.mbean.registered\` và \`JMX.mbean.unregistered\`. Điều này hữu ích khi client muốn tự động tìm MBean mới để đăng ký listener riêng cho từng instance. Việc query hiện tại và lắng nghe thay đổi registry cần xử lý race, vì giữa hai bước có thể xuất hiện hoặc biến mất một MBean.

## 13. Notification trong Spring Framework

Có hai trường hợp cần phân biệt.

### Trường hợp A: Bean là MBean broadcaster theo JMX chuẩn

Nếu bean Spring implement Standard MBean và kế thừa \`NotificationBroadcasterSupport\`, Spring có thể export nó như một MBean có khả năng phát notification.

\`\`\`java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

import java.util.Map;

@Configuration
public class JobMonitorJmxConfig {

    @Bean
    public JobMonitor jobMonitor() {
        return new JobMonitor();
    }

    @Bean
    public MBeanExporter mbeanExporter(
            JobMonitor jobMonitor
    ) {
        MBeanExporter exporter = new MBeanExporter();

        exporter.setBeans(Map.of(
            "learning.jmx:type=JobMonitor,name=spring",
            jobMonitor
        ));

        return exporter;
    }
}
\`\`\`

Khi exporter đăng ký thành công, JMX client dùng ObjectName:

\`\`\`java
ObjectName name = new ObjectName(
    "learning.jmx:type=JobMonitor,name=spring"
);
\`\`\`

để gắn listener hoặc invoke operation. Cần bảo đảm client kết nối tới đúng MBeanServer mà exporter sử dụng. Không cấu hình trùng nhiều exporter đăng ký cùng ObjectName.

### Trường hợp B: Bean thường + Spring JMX metadata

Spring hỗ trợ \`@ManagedResource\`, \`@ManagedOperation\`, \`@ManagedAttribute\` để xuất bản một bean Java thông thường qua \`AnnotationMBeanExporter\` hoặc \`@EnableMBeanExport\`. Với notification, Spring có cơ chế chuyển tiếp notification từ bean biết phát sự kiện phù hợp qua JMX MBean.

Một tùy chọn là sử dụng \`NotificationPublisherAware\` để nhận \`NotificationPublisher\` do Spring cung cấp, rồi phát notification bằng \`sendNotification\` mà không cần tự quản lý listener.

Ví dụ:

\`\`\`java
package example.springjmx;

import java.util.concurrent.atomic.AtomicLong;
import javax.management.Notification;

import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.jmx.export.notification.NotificationPublisher;
import org.springframework.jmx.export.notification.NotificationPublisherAware;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "learning.jmx:type=JobMonitor,name=managed"
)
public class ManagedJobService
        implements NotificationPublisherAware {

    private final AtomicLong sequence = new AtomicLong();

    private NotificationPublisher publisher;

    @Override
    public void setNotificationPublisher(
            NotificationPublisher publisher
    ) {
        this.publisher = publisher;
    }

    @ManagedOperation(description = "Complete a managed job")
    public void complete(String jobId) {
        // Logic nghiệp vụ minh họa.
        Notification notification = new Notification(
            "app.job.completed",
            this,
            sequence.incrementAndGet(),
            System.currentTimeMillis(),
            "Completed: " + jobId
        );

        publisher.sendNotification(notification);
    }
}
\`\`\`

Cấu hình bật export:

\`\`\`java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxExportConfig {
}
\`\`\`

Spring sẽ cung cấp publisher trong ngữ cảnh export phù hợp. Cần gọi publisher **sau khi bean đã được export và callback thiết lập publisher được thực hiện**; nếu code tự gọi \`complete\` quá sớm trong lifecycle, tham chiếu publisher có thể chưa sẵn sàng. \`NotificationPublisherAware\` giúp bean tập trung vào việc tạo notification, trong khi adapter JMX lo chuyển tiếp tới listener.

Để công bố loại notification trong metadata JMX cho công cụ quản trị, có thể dùng \`@ManagedNotification\` trong \`@ManagedNotifications\` ở lớp được export, phù hợp với cơ chế annotation của Spring.

Ví dụ:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedNotification;
import org.springframework.jmx.export.annotation.ManagedNotifications;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "learning.jmx:type=JobMonitor,name=annotated"
)
@ManagedNotifications({
    @ManagedNotification(
        name = "app.job.completed",
        description = "A job completed",
        notificationTypes = { "app.job.completed" }
    )
})
public class AnnotatedJobMonitor {
    // Nội dung nghiệp vụ và NotificationPublisherAware tương tự.
}
\`\`\`

Trong các phiên bản Spring và cơ chế export tương ứng, hãy dùng annotation notification đúng hợp đồng metadata được thư viện hỗ trợ. \`@ManagedNotification\` mô tả type JMX, không tự phát notification. Phát sự kiện vẫn phải gọi publisher hoặc broadcaster.

## 14. Spring NotificationListenerBean: đăng ký listener bằng cấu hình

Spring còn có \`org.springframework.jmx.export.NotificationListenerBean\` để cấu hình listener với exporter.

\`\`\`java
import javax.management.NotificationListener;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.NotificationListenerBean;

NotificationListener loggingListener =
    (notification, context) -> {
        System.out.println(notification.getMessage());
    };

NotificationListenerBean binding =
    new NotificationListenerBean(loggingListener);

binding.setMappedObjectNames(
    "learning.jmx:type=JobMonitor,name=spring"
);

MBeanExporter exporter = new MBeanExporter();
exporter.setNotificationListeners(binding);
\`\`\`

Đây là mảnh cấu hình minh họa: trong ứng dụng thực, phải khai báo bean/exporter được quản lý hoàn chỉnh và đưa MBean cần theo dõi vào danh sách export tương ứng. \`mappedObjectNames\` xác định MBean mà listener gắn tới, không thay thế cơ chế tạo notification trong implementation.

Phân biệt hai phía:

\`\`\`text
Server-side:
  Spring bean
    -> JMX MBean + NotificationPublisher / broadcaster
    -> MBeanServer

Server-side Spring exporter listener:
  NotificationListenerBean
    -> exporter đăng ký listener cho MBean phù hợp

Client-side:
  MBeanServerConnection
    -> addNotificationListener(ObjectName,...)
    -> nhận callback qua JMX connector
\`\`\`

Các cấu hình trên có thể cùng tồn tại, nhưng nên tránh vô tình tạo listener trùng nhau và phải quản lý lifecycle rõ ràng.

## 15. NotificationPublisher so với NotificationBroadcasterSupport

| Góc nhìn | \`NotificationBroadcasterSupport\` | Spring \`NotificationPublisherAware\` |
|---|---|---|
| Cấp độ API | JMX chuẩn (\`javax.management\`) | Spring JMX |
| Đối tượng sử dụng | MBean triển khai trực tiếp broadcaster | Spring bean export theo cơ chế Spring |
| Phát notification | \`sendNotification(notification)\` | \`publisher.sendNotification(notification)\` |
| Quản lý listener | Lớp support quản lý listener | Spring/JMX adapter quản lý phía xuất bản |
| Metadata | Override \`getNotificationInfo()\` | Metadata từ Spring JMX assembler/annotation |
| Phù hợp | MBean cần tương thích JMX thuần | Bean Spring muốn giảm phụ thuộc vào cơ chế listener JMX |
| Lưu ý | Chọn executor/dispatch và cleanup listener | Chờ publisher được inject khi exporter sẵn sàng |

Hai cách đều đưa notification ra mô hình JMX. Chọn dựa trên việc lớp của bạn là một **MBean JMX trực tiếp** hay là **bean nghiệp vụ Spring được export**.

## 16. Phân biệt JMX notification với Spring ApplicationEvent

Spring có hệ thống \`ApplicationEventPublisher\` và \`@EventListener\`, phục vụ giao tiếp sự kiện trong application context. JMX notification phục vụ quan sát/quản trị qua MBeanServer.

| Tiêu chí | Spring ApplicationEvent | JMX Notification |
|---|---|---|
| Phạm vi chủ yếu | Nội bộ ứng dụng/Spring context | JMX MBeanServer và các client quản trị |
| Phát sự kiện | \`ApplicationEventPublisher.publishEvent(...)\` | \`sendNotification(...)\` hoặc Spring \`NotificationPublisher\` |
| Lắng nghe | \`@EventListener\`, \`ApplicationListener\` | \`NotificationListener\` |
| Định danh nguồn | Dựa trên event class/source trong Spring | MBean/ObjectName, notification type/source |
| Truy cập remote | Không mặc định | Có thể qua JMX connector khi cấu hình |
| Lưu trữ bền vững | Không mặc định | Không mặc định |

Có thể **bridge** từ Spring ApplicationEvent sang JMX Notification để expose một nhóm sự kiện vận hành cần thiết. Tuy nhiên không xuất bản dữ liệu nghiệp vụ nhạy cảm một cách mặc định, không dùng JMX notification làm bus sự kiện chính cho business workflow, và tránh biến mỗi Spring event thành một notification gây tải lớn.

## 17. Notification, AttributeChangeNotification và sequence number

JMX có subclass \`AttributeChangeNotification\` để mô tả một thay đổi attribute:

\`\`\`java
import javax.management.AttributeChangeNotification;

Notification change = new AttributeChangeNotification(
    this,
    sequence.incrementAndGet(),
    System.currentTimeMillis(),
    "ActiveCount changed",
    "ActiveCount",
    "int",
    5,
    8
);

sendNotification(change);
\`\`\`

Nó chứa:

- Tên thuộc tính \`ActiveCount\`.
- Kiểu thuộc tính \`int\`.
- Giá trị cũ \`5\`, giá trị mới \`8\`.
- Type \`jmx.attribute.change\`.

**Không phải mọi thay đổi field Java đều tự động tạo \`AttributeChangeNotification\`.** Implementation hoặc adapter phải phát thông báo. Một client có thể nhận event và đọc lại attribute để lấy trạng thái hiện tại.

Sequence number giúp nhận biết thứ tự của các sự kiện do một nguồn phát nếu implementation tăng số một cách nhất quán. Nó không tự cung cấp exactly-once delivery, global ordering giữa các MBean hoặc cơ chế tự phát lại các notification bị bỏ lỡ.

## 18. Bảo vệ callback và giảm rủi ro chặn thread

Listener thường chạy gần luồng xử lý notification, đặc biệt với broadcaster local dùng dispatcher đồng bộ. Nếu callback chậm, nó có thể kéo dài thời gian phát notification.

Một lựa chọn là đưa xử lý nặng sang executor riêng:

\`\`\`java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import javax.management.NotificationListener;

ExecutorService executor =
    Executors.newSingleThreadExecutor();

NotificationListener listener = (notification, handback) -> {
    executor.submit(() -> {
        // Xử lý ngoài đường phát sự kiện.
        System.out.println(notification.getMessage());
    });
};

// Sau khi tháo listener và không còn cần executor:
executor.shutdown();
\`\`\`

Đây chỉ là ý tưởng tách công việc. Trong production phải định nghĩa chính sách khi hàng đợi executor đầy, shutdown, lỗi callback và kiểm soát số lượng task. Với notification lưu lượng cao, nên đo throughput, latency và lượng sự kiện bị bỏ qua theo chính sách đã định, không vô hạn tạo task trong bộ nhớ.

Nếu dùng \`NotificationBroadcasterSupport\` với executor do bạn cấp, nên quản lý cả vòng đời executor đó, bảo đảm shutdown an toàn. Không giữ listener sống lâu hơn component cần nhận sự kiện.

## 19. Truy cập notification qua remote JMX

Client remote có thể đăng ký listener bằng \`MBeanServerConnection\`:

\`\`\`java
import javax.management.MBeanServerConnection;
import javax.management.NotificationListener;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

JMXServiceURL url = new JMXServiceURL(
    "service:jmx:rmi:///jndi/rmi://localhost:9999/jmxrmi"
);

try (JMXConnector connector =
         JMXConnectorFactory.connect(url)) {

    MBeanServerConnection connection =
        connector.getMBeanServerConnection();

    ObjectName name = new ObjectName(
        "learning.jmx:type=JobMonitor,name=spring"
    );

    NotificationListener listener =
        (notification, handback) ->
            System.out.println(notification.getMessage());

    connection.addNotificationListener(
        name,
        listener,
        null,
        null
    );

    try {
        // Giữ client hoạt động trong thời gian cần nhận event.
    } finally {
        connection.removeNotificationListener(
            name,
            listener
        );
    }
}
\`\`\`

Ví dụ giả định remote JMX connector đã được cấu hình đúng và có quyền truy cập. \`@EnableMBeanExport\` hoặc \`MBeanExporter\` **không tự mở cổng remote JMX**. Phải cấu hình connector/agent và bảo vệ kết nối bằng xác thực, phân quyền, TLS và giới hạn truy cập mạng thích hợp.

Khi mạng mất kết nối, notification có thể không đến. Client phải thiết kế reconnect, đăng ký listener lại và đồng bộ trạng thái qua attribute/polling hoặc nguồn dữ liệu bền vững nếu nghiệp vụ cần.

## 20. Những lỗi phổ biến

| Hiện tượng | Nguyên nhân có thể | Cách định vị |
|---|---|---|
| Không nhận notification | Chưa gọi \`sendNotification\`/\`publisher.sendNotification\`; sai ObjectName; filter từ chối | Kiểm tra đường phát, listener registration và type |
| Listener chỉ nhận sự kiện từ một instance | Listener gắn với ObjectName cụ thể | Đăng ký riêng cho từng MBean cần theo dõi |
| Nhận sự kiện lặp | Cùng listener được add nhiều lần | Kiểm tra số registration và lifecycle |
| Remove báo \`ListenerNotFoundException\` | Sai listener/filter/handback hoặc đã remove | Dùng đúng registration lúc add |
| Remove báo \`InstanceNotFoundException\` | MBean đã unregister | Kiểm tra lifecycle và xử lý cleanup an toàn |
| Metadata hiển thị nhưng không có sự kiện | \`getNotificationInfo\` chỉ mô tả, không phát | Kiểm tra điểm gọi send |
| Có event nhưng payload không đọc được từ remote | UserData không tương thích serialization/classpath remote | Ưu tiên type/payload JMX-friendly |
| Callback chậm làm app phản hồi kém | Dispatch đồng bộ hoặc queue quá tải | Tách xử lý, đặt giới hạn và theo dõi độ trễ |
| MBean mới không được theo dõi | Listener gắn vào danh sách MBean tại thời điểm truy vấn | Theo dõi \`MBeanServerDelegate\` và refresh subscription |
| Spring bean không có publisher | Chưa export đúng hoặc gọi quá sớm trong lifecycle | Kiểm tra exporter, metadata và thời điểm inject |

## 21. Kịch bản thực hành

**Bối cảnh:** một ứng dụng có hai MBean:

\`\`\`text
learning.jmx:type=JobMonitor,name=orders
learning.jmx:type=JobMonitor,name=payments
\`\`\`

Mỗi MBean phát hai type: \`app.job.completed\` và \`app.job.failed\`. Hệ thống giám sát chỉ muốn nhận các thông báo \`failed\` từ MBean \`orders\`.

Cách làm:

1. Tạo \`ObjectName\` chính xác cho \`orders\`.
2. Tạo \`NotificationListener\` để xử lý sự kiện.
3. Tạo \`NotificationFilter\` chỉ chấp nhận type đúng \`app.job.failed\`.
4. Gắn listener vào \`orders\` qua \`MBeanServerConnection\`.
5. Khi hoàn tất, remove đúng listener/filter/handback.

\`\`\`java
ObjectName orders = new ObjectName(
    "learning.jmx:type=JobMonitor,name=orders"
);

NotificationListener listener =
    (event, context) ->
        System.out.println("FAILED: " + event.getMessage());

NotificationFilter filter =
    event -> "app.job.failed".equals(event.getType());

connection.addNotificationListener(
    orders,
    listener,
    filter,
    "orders"
);

try {
    // Theo dõi notification.
} finally {
    connection.removeNotificationListener(
        orders,
        listener,
        filter,
        "orders"
    );
}
\`\`\`

Nếu MBean \`payments\` cũng phát \`app.job.failed\`, listener này vẫn không nhận, vì subscription gắn với ObjectName \`orders\`. Nếu \`orders\` unregister rồi đăng ký lại, client cần xem xét việc đăng ký listener lại.

## 22. Câu hỏi kiểm tra tư duy

1. Vì sao một MBean có \`getNotificationInfo()\` chưa chắc đã phát notification?
2. \`NotificationEmitter\` cung cấp thêm khả năng nào so với \`NotificationBroadcaster\`?
3. Khi nào \`NotificationBroadcasterSupport\` giúp giảm code tự viết?
4. \`NotificationFilterSupport.enableType("app.job.")\` có nhận \`app.job.failed\` không?
5. \`handback\` khác gì \`userData\` của một notification?
6. Nếu listener local xử lý mất 5 giây, vì sao có thể ảnh hưởng luồng gọi nghiệp vụ?
7. Một listener được gắn vào \`ObjectName\` của MBean cũ có tự chuyển sang MBean đăng ký lại cùng tên không?
8. Khi remote connector ngắt, JMX notification có tự phát lại sau reconnect không?
9. Trong Spring, \`NotificationPublisherAware\` hỗ trợ điều gì?
10. Vì sao nên kết hợp notification với đọc attribute hiện tại khi cần quan sát đáng tin cậy?

**Gợi ý:** metadata, registration, dispatch và lifecycle là các thành phần khác nhau. Cơ chế notification có thể báo sự kiện nhanh, nhưng không thay cho hợp đồng lưu trữ/phục hồi trạng thái.

## 23. Ghi nhớ cuối bài

\`\`\`text
NotificationBroadcaster
  = có khả năng quản lý listener và mô tả notification

NotificationEmitter
  = NotificationBroadcaster
    + remove riêng một registration
      (listener, filter, handback)

NotificationBroadcasterSupport
  = implementation tiện lợi
    + sendNotification(notification)

NotificationListener
  = callback nhận notification

NotificationFilter
  = điều kiện quyết định event có được chuyển đi

MBeanServer / MBeanServerConnection
  = nơi client gắn listener bằng ObjectName

Spring NotificationPublisherAware
  = bean được Spring hỗ trợ phát JMX notification
    qua publisher do exporter cung cấp
\`\`\`

**Quy tắc vận hành:** MBean phải **chủ động phát**, listener phải **đăng ký đúng**, filter phải **cho phép**, và vòng đời subscription phải được **dọn dẹp**. Hãy coi notification là tín hiệu quản trị theo thời điểm; trạng thái bền vững và lịch sử sự kiện cần những cơ chế riêng.