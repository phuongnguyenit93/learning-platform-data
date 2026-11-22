# Kiểm tra notification trong công cụ JMX

> **Chủ đề:** Spring Framework JMX  
> **Nhóm kiến thức:** Công cụ JMX  
> **Bài học:** Kiểm tra notification trong công cụ JMX

## 1. Mục tiêu

Sau bài này, bạn có thể:

- Xác định một MBean có công bố khả năng phát **JMX notification** hay không.
- Kết nối đúng JVM bằng JConsole hoặc công cụ JMX phù hợp và tìm chính xác **ObjectName** của MBean.
- Đăng ký nhận notification trong công cụ, tạo sự kiện thử, đọc \`type\`, \`source\`, \`sequenceNumber\`, \`timeStamp\`, \`message\` và \`userData\` khi công cụ hiển thị.
- Phân biệt tình trạng **không có notification metadata**, **không có listener**, **filter chặn**, **không phát sự kiện**, **sai JVM/MBeanServer** và **remote connection mất ổn định**.
- Dùng \`MBeanServerConnection\` làm công cụ kiểm chứng độc lập khi cần kiểm soát filter, subscription và nội dung event.
- Hiểu cách Spring export bean và phát notification, đồng thời xử lý vòng đời listener đúng cách.

## 2. Notification là gì trong thao tác giám sát?

JMX (Java Management Extensions) cho phép ứng dụng expose dữ liệu quản trị qua MBean. Ba cơ chế thường gặp:

| Cơ chế | Mục đích | Cách client sử dụng |
|---|---|---|
| **Attribute** | Đọc hoặc thay đổi trạng thái hiện tại. | Tab Attributes hoặc \`getAttribute\`/\`setAttribute\`. |
| **Operation** | Yêu cầu MBean thực hiện một hành động. | Tab Operations hoặc \`invoke\`. |
| **Notification** | MBean chủ động gửi thông báo về một sự kiện. | Tab Notifications hoặc \`addNotificationListener\`. |

Ví dụ: một MBean quản lý hàng đợi có attribute \`QueueDepth\`, operation \`resetQueue()\`, và notification \`app.queue.threshold.exceeded\` khi độ dài hàng đợi vượt ngưỡng.

Notification có **tính thời điểm**. Nếu chỉ mở giao diện sau khi sự kiện đã xảy ra, bạn thường không thấy event cũ. Thông thường, công cụ phải **đăng ký listener trước**, sau đó sự kiện mới được tạo và phát.

\`\`\`text
Ứng dụng Spring/JVM
      |
      v
MBean phát Notification
      |
      v
MBeanServer (đúng JVM và ObjectName)
      |
      +---- Local JMX attach ----> JConsole
      |
      +---- JMX Connector -------> Remote JMX Client
                                       |
                                       v
                              Listener đã đăng ký
                                       |
                                       v
                          Hiển thị type / message / time
\`\`\`

Đăng ký notification trên MBean không biến JMX thành message queue bền vững. JMX notification không mặc định có replay, durable subscription, exactly-once delivery hay bảo đảm giữ đầy đủ lịch sử khi client ngắt kết nối.

## 3. Chuẩn bị một kịch bản thử có thể lặp lại

Một bài kiểm tra notification đáng tin cậy nên có đủ các yếu tố:

1. **Đúng MBean:** có \`ObjectName\` rõ ràng, ví dụ \`learning.jmx:type=TaskMonitor,name=main\`.
2. **Loại notification biết trước:** ví dụ \`app.task.completed\`.
3. **Trigger có kiểm soát:** một operation \`completeTask(String taskId)\` hoặc hành động ứng dụng có thể chủ động kích hoạt.
4. **Listener đăng ký trước trigger:** để tránh bỏ lỡ event do công cụ bắt đầu nghe quá muộn.
5. **Dữ liệu đối chiếu:** có event type, thời gian, sequence number, message, và một mã tương quan như task ID.
6. **Cleanup:** hủy listener khi kết thúc, đóng kết nối và xóa MBean thử nghiệm nếu chính bạn đã đăng ký nó.

Nếu ứng dụng có event thật nhưng không có hành động dễ lặp, hãy chuẩn bị môi trường thử nghiệm có dữ liệu phù hợp. Tránh kích hoạt operation mang tính phá hủy như xóa cache sản xuất, đóng kết nối hoặc reset trạng thái chỉ để kiểm chứng UI.

## 4. Tạo MBean minh họa phát notification

Ví dụ thuần JMX sau cho phép quan sát bằng JConsole mà không cần cấu hình remote connector.

### 4.1. Standard MBean interface

\`\`\`java
package example.jmx;

public interface TaskMonitorMBean {
    long getCompletedCount();

    String completeTask(String taskId);
}
\`\`\`

Tên interface theo quy tắc Standard MBean: class \`TaskMonitor\` implement \`TaskMonitorMBean\`. \`getCompletedCount()\` trở thành attribute quản trị, còn \`completeTask(String)\` được công bố là operation.

### 4.2. Implementation phát notification

\`\`\`java
package example.jmx;

import java.util.concurrent.atomic.AtomicLong;
import javax.management.MBeanNotificationInfo;
import javax.management.Notification;
import javax.management.NotificationBroadcasterSupport;

public class TaskMonitor extends NotificationBroadcasterSupport
        implements TaskMonitorMBean {

    public static final String TASK_COMPLETED =
        "app.task.completed";

    private final AtomicLong completedCount =
        new AtomicLong();

    private final AtomicLong sequence =
        new AtomicLong();

    @Override
    public long getCompletedCount() {
        return completedCount.get();
    }

    @Override
    public String completeTask(String taskId) {
        if (taskId == null || taskId.isBlank()) {
            throw new IllegalArgumentException(
                "taskId must not be blank"
            );
        }

        long total = completedCount.incrementAndGet();

        Notification event = new Notification(
            TASK_COMPLETED,
            this,
            sequence.incrementAndGet(),
            System.currentTimeMillis(),
            "Task completed: " + taskId
        );
        event.setUserData(taskId);

        sendNotification(event);

        return "completed=" + total;
    }

    @Override
    public MBeanNotificationInfo[] getNotificationInfo() {
        return new MBeanNotificationInfo[] {
            new MBeanNotificationInfo(
                new String[] { TASK_COMPLETED },
                Notification.class.getName(),
                "A task was completed"
            )
        };
    }
}
\`\`\`

Ở đây:

- \`sendNotification(event)\` thực sự phát notification. Chỉ khai báo \`getNotificationInfo()\` chưa tạo event.
- \`type\` là \`app.task.completed\`, dùng để phân loại sự kiện.
- \`source\` được đặt là \`this\` trong implementation; khi đi qua MBeanServer hoặc remote connector, biểu diễn nguồn có thể khác. Không ép kiểu \`source\` về implementation cụ thể ở client.
- \`sequenceNumber\` tăng theo từng instance của \`TaskMonitor\`. Nó không phải thứ tự toàn cục của mọi MBean.
- \`timeStamp\` là thời gian phát do implementation cung cấp, không nhất thiết trùng thời điểm công cụ nhận.
- \`userData\` chứa \`taskId\` để đối chiếu event khi test.
- \`CompletedCount\` cho phép đọc trạng thái tổng hợp sau khi có event, nhưng một attribute không thay thế lịch sử notification.

### 4.3. Đăng ký MBean và giữ JVM đang chạy

\`\`\`java
package example.jmx;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class TaskMonitorApplication {

    public static void main(String[] args) throws Exception {
        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
            "learning.jmx:type=TaskMonitor,name=main"
        );

        server.registerMBean(new TaskMonitor(), name);

        System.out.println("MBean registered: " + name);
        System.out.println(
            "PID: " + ProcessHandle.current().pid()
        );
        System.out.println(
            "Open JConsole and invoke completeTask(...)"
        );

        // Giữ JVM để JConsole có thời gian kết nối.
        System.in.read();

        server.unregisterMBean(name);
    }
}
\`\`\`

Khởi chạy \`TaskMonitorApplication\` trong JVM có thể được JConsole attach. Chương trình chờ nhập từ stdin rồi thoát; không nhấn Enter trước khi hoàn thành các bước kiểm tra.

Ví dụ này dùng **platform MBeanServer** và đăng ký tên rõ ràng. Khi chạy lại nhiều lần trong cùng JVM, nếu tên đã tồn tại, \`registerMBean\` có thể báo \`InstanceAlreadyExistsException\`; đừng âm thầm unregister MBean không do bài kiểm tra sở hữu.

## 5. Kết nối JConsole tới đúng JVM

JConsole là công cụ GUI JMX đi kèm nhiều bản phân phối JDK. Cách mở phổ biến là chạy \`jconsole\` từ thư mục \`bin\` của JDK.

Trình tự:

1. Khởi chạy ứng dụng thử nghiệm, ghi lại PID mà chương trình in ra.
2. Mở terminal cài đúng JDK và chạy \`jconsole\`.
3. Chọn **Local Process** có PID tương ứng. Nếu ứng dụng chạy trong IDE, vẫn phải chọn đúng tiến trình JVM của ứng dụng, tránh chọn IDE hoặc Gradle daemon.
4. Đồng ý kết nối nếu JConsole hỏi xác nhận.
5. Mở tab **MBeans** và tìm domain \`learning.jmx\`.
6. Chọn MBean với key properties \`type=TaskMonitor,name=main\`.

Một JVM có thể có nhiều MBean hệ thống trong \`java.lang\`, \`com.sun.management\` hoặc domain khác. Đừng nhầm những MBean JVM mặc định với MBean của ứng dụng.

**Lưu ý:** tùy hệ điều hành, JDK, quyền người dùng và thiết lập attach, JConsole có thể không kết nối được vào local process. Với container, WSL, Docker hoặc môi trường nhiều user, JConsole trên host có thể không nhìn thấy tiến trình JVM như một local process. Trường hợp đó cần cấu hình JMX connector phù hợp; chỉ bật Spring JMX export không tự mở kết nối từ xa.

## 6. Tìm tab Notifications trong JConsole

Sau khi chọn MBean, JConsole thường hiển thị các phần như Attributes, Operations, Notifications và Info tùy metadata và loại MBean.

Trong phần **Notifications**:

- Kiểm tra danh sách loại notification mà MBean công bố.
- Chọn hành động **Subscribe** hoặc thao tác tương đương để JConsole đăng ký listener.
- Sau khi subscribe, mới tạo trigger cho notification.
- Quan sát số notification nhận được, chọn event để xem chi tiết và thời gian xuất hiện.
- Dùng **Unsubscribe** khi không cần nghe nữa.

Tên nút và bố cục có thể khác theo phiên bản JDK/JConsole. Cần nhận ra ý nghĩa thao tác là **đăng ký/hủy đăng ký listener với MBean**, chứ không phụ thuộc tuyệt đối vào vị trí một nút trong UI.

Nếu không thấy Notifications, hãy xem tab Info hoặc metadata MBean. MBean không công bố notification hoặc không triển khai chức năng phát sự kiện phù hợp có thể không cung cấp bề mặt nghe trong công cụ.

Một nguyên tắc: **Subscribe thành công không có nghĩa đã có event**. Subscription chỉ xác lập người nghe; cần có \`sendNotification\` sau đó để xuất hiện dữ liệu.

## 7. Thử event trực tiếp qua Operations

Với \`TaskMonitor\`, JConsole có thể hiển thị operation:

\`\`\`text
completeTask(java.lang.String)
\`\`\`

Sau khi đã subscribe:

1. Chuyển sang phần **Operations**.
2. Chọn \`completeTask\`, nhập một mã thử như \`job-001\`.
3. Gọi operation.
4. Trở về **Notifications** để xem event mới.
5. Đối chiếu message với \`job-001\`, type \`app.task.completed\`, sequence number và timestamp.
6. Trong **Attributes**, đọc lại \`CompletedCount\` để xác nhận giá trị đã tăng.

Kỳ vọng sau một lần gọi thành công:

\`\`\`text
Type:          app.task.completed
Message:       Task completed: job-001
UserData:      job-001
Sequence:      1
Timestamp:     thời điểm thực thi
CompletedCount: 1
\`\`\`

Con số và thời điểm phụ thuộc vào lịch sử của instance. Nếu đã gọi nhiều lần, sequence và \`CompletedCount\` sẽ lớn hơn. Nếu đã unregister rồi tạo instance mới, các counter có thể bắt đầu lại từ đầu. JConsole có thể hiển thị \`userData\` hoặc source theo định dạng riêng, nên nên kiểm chứng dựa trên type/message/sequence mà công cụ thực sự cung cấp.

Với operation có tham số, công cụ cần chuyển kiểu từ UI sang kiểu Java phù hợp. Nếu UI không hỗ trợ nhập kiểu dữ liệu của operation, có thể dùng Java client qua \`MBeanServerConnection.invoke\` để tạo sự kiện thay vì cố thao tác trong GUI.

## 8. Cách đọc các trường của một notification

| Trường | Ý nghĩa | Ví dụ | Điều cần tránh |
|---|---|---|---|
| \`type\` | Mã phân loại sự kiện. | \`app.task.completed\` | Không mặc định tất cả MBean dùng cùng quy ước type. |
| \`source\` | Nguồn phát theo biểu diễn JMX. | MBean/ObjectName hoặc nguồn khác | Không ép kiểu thành Spring bean khi remote. |
| \`sequenceNumber\` | Số thứ tự do nguồn phát gán. | \`8\` | Không giả định thứ tự toàn cục. |
| \`timeStamp\` | Thời gian do event lưu. | Epoch milliseconds | Không đồng nhất với thời gian UI nhận. |
| \`message\` | Mô tả dễ đọc. | \`Task completed: job-001\` | Không dùng message làm định danh machine-readable duy nhất. |
| \`userData\` | Payload bổ sung do nguồn phát cung cấp. | \`job-001\` | Remote client có thể không giải mã được object tùy ý. |

Để phân tích có hệ thống, nên kết hợp **ObjectName + notification type + sequenceNumber + timestamp + mã tương quan**. Nếu ứng dụng có nhiều instance, sequence number \`1\` từ hai instance là hai sự kiện khác nhau.

Các event type thường là chuỗi tên phân cấp bằng dấu chấm. Ví dụ:

\`\`\`text
app.task.started
app.task.completed
app.task.failed
\`\`\`

Đó là quy ước ứng dụng; JMX không buộc mọi event phải dùng ba tên này.

## 9. Kiểm tra metadata: MBean có công bố notification không?

JConsole hiển thị thông tin dựa trên metadata từ JMX. Có thể kiểm tra trực tiếp bằng API:

\`\`\`java
import javax.management.MBeanInfo;
import javax.management.MBeanNotificationInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanInfo info = server.getMBeanInfo(name);

for (MBeanNotificationInfo n : info.getNotifications()) {
    System.out.println(n.getDescription());

    for (String type : n.getNotifTypes()) {
        System.out.println("  type=" + type);
    }
}
\`\`\`

Nếu \`info.getNotifications()\` rỗng, công cụ khó biết các loại notification dự kiến. Tuy nhiên có metadata cũng không chứng minh event thực sự được phát.

Cần phân biệt bốn bước:

\`\`\`text
1. MBean được đăng ký
2. MBean công bố notification metadata
3. Client đăng ký listener
4. MBean chủ động phát notification
\`\`\`

Mỗi bước có thể thành công hoặc thất bại độc lập. Nếu GUI không hiển thị event, không kết luận ngay “JMX hỏng”; phải tìm mắt xích nào chưa xảy ra.

## 10. Kiểm chứng độc lập bằng NotificationListener

Khi JConsole không hiển thị đủ chi tiết, một client JMX bằng code giúp quan sát rõ những notification nhận được.

Ví dụ dùng \`MBeanServerConnection\` và \`ObjectName\` đúng:

\`\`\`java
import javax.management.MBeanServerConnection;
import javax.management.Notification;
import javax.management.NotificationListener;
import javax.management.ObjectName;

ObjectName name = new ObjectName(
    "learning.jmx:type=TaskMonitor,name=main"
);

NotificationListener listener =
    (Notification event, Object context) -> {
        System.out.printf(
            "type=%s source=%s seq=%d time=%d%n",
            event.getType(),
            event.getSource(),
            event.getSequenceNumber(),
            event.getTimeStamp()
        );
        System.out.println(
            "message=" + event.getMessage()
        );
        System.out.println(
            "userData=" + event.getUserData()
        );
        System.out.println(
            "handback=" + context
        );
    };

connection.addNotificationListener(
    name,
    listener,
    null,
    "diagnostic-session"
);

try {
    connection.invoke(
        name,
        "completeTask",
        new Object[] { "job-002" },
        new String[] { "java.lang.String" }
    );

    // Dành đủ thời gian cho callback nếu kết nối là remote.
} finally {
    connection.removeNotificationListener(
        name,
        listener
    );
}
\`\`\`

\`connection\` phải là một \`MBeanServerConnection\` trỏ tới server đã đăng ký MBean. Ví dụ trên là **đoạn code trong ngữ cảnh có connection**, không phải một lớp Java tự chạy độc lập. Khi kiểm chứng remote, có thể dùng \`JMXConnectorFactory.connect\` để nhận connection và đóng connector khi xong.

Nếu client remote nhận event không đồng bộ, tháo listener ngay sau \`invoke\` có thể làm bỏ lỡ callback đang trên đường truyền. Đối với một phép thử xác định, dùng \`CountDownLatch\` để chờ event với timeout có giới hạn.

## 11. Kiểm thử có timeout bằng CountDownLatch

Ví dụ dưới đây giúp phân biệt tình huống sự kiện đến thực sự và việc suy đoán dựa vào console log.

\`\`\`java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import javax.management.MBeanServerConnection;
import javax.management.Notification;
import javax.management.NotificationListener;
import javax.management.ObjectName;

public static Notification awaitTaskCompleted(
        MBeanServerConnection connection,
        ObjectName name,
        String taskId
) throws Exception {

    CountDownLatch latch = new CountDownLatch(1);
    AtomicReference<Notification> captured =
        new AtomicReference<>();

    NotificationListener listener = (event, context) -> {
        if (!"app.task.completed".equals(event.getType())) {
            return;
        }

        if (!taskId.equals(event.getUserData())) {
            return;
        }

        captured.set(event);
        latch.countDown();
    };

    connection.addNotificationListener(
        name,
        listener,
        null,
        taskId
    );

    try {
        connection.invoke(
            name,
            "completeTask",
            new Object[] { taskId },
            new String[] { "java.lang.String" }
        );

        boolean arrived = latch.await(
            5,
            TimeUnit.SECONDS
        );

        if (!arrived) {
            throw new IllegalStateException(
                "No matching notification within timeout"
            );
        }

        return captured.get();
    } finally {
        connection.removeNotificationListener(
            name,
            listener
        );
    }
}
\`\`\`

**Cách đọc kết quả:** thành công nghĩa là listener đã nhận notification có type và \`userData\` khớp task ID. Timeout chỉ nói rằng **không quan sát được event trong khoảng chờ**; có thể do event không phát, filter không khớp, listener đã đăng ký sai, network chậm hoặc connector mất kết nối. Không kết luận một nguyên nhân cụ thể chỉ từ timeout.

Với test dùng local MBeanServer, kết quả thường nhanh và ổn định. Với remote JMX, cần cân nhắc latency và độ ổn định thực tế khi chọn timeout.

## 12. Filter trong công cụ và kiểm chứng bằng API

Một số công cụ cho phép lọc hiển thị hoặc chọn loại notification. Bộ lọc của công cụ có thể khác bộ lọc JMX được đăng ký ở phía server. Khi cần kiểm soát chính xác loại sự kiện, dùng \`NotificationFilter\`:

\`\`\`java
import javax.management.NotificationFilter;

NotificationFilter onlyCompleted =
    event -> "app.task.completed".equals(
        event.getType()
    );

connection.addNotificationListener(
    name,
    listener,
    onlyCompleted,
    null
);
\`\`\`

Có thể dùng \`NotificationFilterSupport\`:

\`\`\`java
import javax.management.NotificationFilterSupport;

NotificationFilterSupport filter =
    new NotificationFilterSupport();

filter.enableType("app.task.");
\`\`\`

Nhưng \`NotificationFilterSupport\` thực hiện **prefix matching**: \`app.task.\` có thể cho phép \`app.task.completed\` và \`app.task.failed\`. Nếu cần đúng một chuỗi type, filter so sánh \`equals\` phù hợp hơn.

Để hủy đúng registration dùng filter, gọi:

\`\`\`java
connection.removeNotificationListener(
    name,
    listener,
    onlyCompleted,
    null
);
\`\`\`

Giữ lại cùng đối tượng listener, filter và handback đã dùng khi add. Overload chỉ nhận \`name, listener\` có thể xóa mọi registration của listener đó trên MBean.

## 13. Kiểm tra notification khi Spring export bean

Spring Framework có thể đăng ký bean dưới dạng MBean bằng \`MBeanExporter\` hoặc \`@EnableMBeanExport\`. Với bean thông thường, Spring hỗ trợ \`NotificationPublisherAware\` để nhận publisher rồi phát JMX notification.

### 13.1. Spring bean phát notification

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
    objectName = "learning.jmx:type=TaskMonitor,name=spring"
)
public class ManagedTaskService
        implements NotificationPublisherAware {

    private final AtomicLong sequence =
        new AtomicLong();

    private NotificationPublisher publisher;

    @Override
    public void setNotificationPublisher(
            NotificationPublisher publisher
    ) {
        this.publisher = publisher;
    }

    @ManagedOperation(description = "Complete a task")
    public void completeTask(String taskId) {
        Notification event = new Notification(
            "app.task.completed",
            this,
            sequence.incrementAndGet(),
            System.currentTimeMillis(),
            "Task completed: " + taskId
        );
        event.setUserData(taskId);

        publisher.sendNotification(event);
    }
}
\`\`\`

Cấu hình export:

\`\`\`java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfiguration {
}
\`\`\`

Đảm bảo application context tạo được bean và cơ chế export hoàn tất trước khi gọi \`completeTask\`. Nếu gọi quá sớm khi publisher chưa được cung cấp, mã có thể lỗi vì publisher chưa được khởi tạo.

### 13.2. Công bố loại notification cho công cụ

Với Spring, metadata notification có thể cấu hình bằng \`@ManagedNotification\` trong \`@ManagedNotifications\` trên lớp được export:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedNotification;
import org.springframework.jmx.export.annotation.ManagedNotifications;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "learning.jmx:type=TaskMonitor,name=spring"
)
@ManagedNotifications({
    @ManagedNotification(
        name = "app.task.completed",
        description = "A task has completed",
        notificationTypes = { "app.task.completed" }
    )
})
public class AnnotatedTaskMonitor {
    // Kết hợp với cơ chế phát notification phù hợp.
}
\`\`\`

Metadata giúp công cụ quản trị nhận diện event type. Annotation tự nó không phát event; cần có \`publisher.sendNotification\` hoặc cơ chế broadcaster thực tế.

Nếu sử dụng code này, hãy gắn metadata vào đúng lớp Spring bean thực sự được export và triển khai phần phát tương ứng. Không đăng ký thêm class minh họa khác với cùng ObjectName.

### 13.3. Kết nối đúng server

\`@EnableMBeanExport\` chỉ bật xuất bản bean sang JMX. Nó không tự mở remote connector. Nếu Spring exporter đăng ký trên platform MBeanServer, local JConsole attach cùng JVM thường quan sát được MBean. Nếu ứng dụng dùng một MBeanServer riêng, JConsole attach vào platform server có thể không thấy MBean dù exporter đăng ký thành công.

Khi nhiều ứng dụng JVM chạy cùng host, hãy đối chiếu PID, domain và ObjectName thay vì chỉ nhìn thấy tên process gần giống.

## 14. Kiểm tra thông báo bằng JConsole: quy trình có thể ghi biên bản

Một phiên kiểm tra có thể ghi lại các thông tin sau:

| Mục kiểm chứng | Bằng chứng cần thu |
|---|---|
| JVM đích | PID, tên main class hoặc startup command. |
| MBean đích | ObjectName canonical và domain. |
| Notification metadata | Danh sách type và description trong MBeanInfo. |
| Subscription | Thời điểm/nút Subscribe đã thực hiện. |
| Trigger | Operation hoặc hành động ứng dụng và input đã dùng. |
| Kết quả event | Type, message, sequence, timestamp, userData nếu có. |
| Trạng thái sau trigger | Attribute liên quan, ví dụ CompletedCount. |
| Cleanup | Đã unsubscribe và đóng connector. |

Ví dụ biên bản:

\`\`\`text
JVM:             PID 18422
MBean:           learning.jmx:type=TaskMonitor,name=main
Notification:    app.task.completed
Subscribed at:   10:15:00
Trigger:         completeTask("job-001")
Observed at:     10:15:04
Event sequence:  1
Event message:   Task completed: job-001
Attribute:       CompletedCount = 1
Cleanup:         unsubscribed
\`\`\`

Đây là dữ liệu minh họa, không phải kết quả của một hệ thống thật. Trong môi trường thực tế, cần ghi giá trị công cụ hiển thị, không tự suy đoán từ code.

Nếu cần bằng chứng cho kiểm thử hồi quy, kết hợp screenshot JConsole với log client và assertion từ \`CountDownLatch\` sẽ giúp phân biệt kiểm tra thủ công với kiểm tra tự động. Không đưa dữ liệu nhạy cảm hoặc credentials vào ảnh/log được chia sẻ.

## 15. Chẩn đoán khi Notifications không hiện

### Tình huống A: MBean không xuất hiện

**Dấu hiệu:** không tìm thấy domain hoặc ObjectName.

Nguyên nhân thường gặp:

- Kết nối nhầm JVM/PID.
- Spring chưa bật export hoặc bean chưa được export.
- ObjectName khác tên dự kiến.
- MBeanServer đang dùng khác platform server mà JConsole attach.
- MBean đã bị unregister.
- Lỗi đăng ký như \`InstanceAlreadyExistsException\` hoặc malformed ObjectName.

Cách kiểm chứng bằng API:

\`\`\`java
boolean registered =
    connection.isRegistered(name);

System.out.println("registered=" + registered);
\`\`\`

Khi MBean không tồn tại, chưa cần kiểm tra filter hoặc notification payload; hãy giải quyết registry/connection trước.

### Tình huống B: MBean có nhưng không có metadata notification

**Dấu hiệu:** Attributes/Operations có thể xuất hiện nhưng Notifications không hiển thị hoặc không có loại sự kiện.

Kiểm tra \`MBeanInfo.getNotifications()\`. Đối với Standard MBean, implementation cần hỗ trợ broadcaster và công bố \`MBeanNotificationInfo[]\`. Đối với Spring bean export, cần cấu hình notification metadata phù hợp.

Không đánh đồng “chưa có metadata” với “chắc chắn không có đường phát”: phần phát và phần mô tả là hai trách nhiệm riêng, nhưng công cụ GUI thường phụ thuộc metadata để thể hiện tính năng.

### Tình huống C: Đã Subscribe nhưng không nhận event

Kiểm tra theo thứ tự:

1. Đã subscribe **trước khi** tạo event chưa?
2. Có invoke đúng operation hoặc kích hoạt đúng luồng nghiệp vụ không?
3. Implementation có thực sự gọi \`sendNotification\` hoặc \`publisher.sendNotification\` không?
4. Listener gắn đúng ObjectName chưa?
5. Notification type có bị filter loại bỏ không?
6. MBean có bị unregister/re-register sau khi subscribe không?
7. Connection có bị ngắt, client có bị pause hoặc chưa xử lý callback không?

Nếu cần, dùng một listener Java đơn giản không filter để loại trừ lỗi do UI/filter.

### Tình huống D: Số event không như mong đợi

Có thể do:

- Trigger được gọi nhiều lần.
- Listener đã đăng ký trùng.
- Một hành động phát nhiều loại notification.
- Filter prefix chấp nhận nhiều type hơn tưởng tượng.
- Dispatch bất đồng bộ khiến event xuất hiện trễ.
- Client bỏ lỡ event vì unsubscribe hoặc ngắt kết nối.
- Nhiều instance phát notification với sequence number riêng.

Không lấy số lượng event ở GUI làm kết luận duy nhất về số lần nghiệp vụ đã chạy. Đọc thêm attribute/counter hoặc log nghiệp vụ tương ứng.

### Tình huống E: Event tới nhưng dữ liệu khó đọc

Với remote JMX, \`userData\` là object Java và có thể cần serialization/class thích hợp ở client. Khi phát notification phục vụ công cụ tổng quát, nên ưu tiên primitive wrapper, \`String\` hoặc các kiểu chuẩn JMX phù hợp. Tránh gửi nguyên object domain phức tạp hoặc chứa dữ liệu nhạy cảm.

## 16. Notification trong JConsole so với VisualVM và client khác

**JConsole** thường phù hợp để kiểm tra nhanh local JVM và các MBean đã expose metadata. Công cụ cho phép duyệt MBean, xem attribute/operation và đăng ký notification khi hỗ trợ.

**VisualVM** tập trung vào quan sát JVM; khả năng duyệt MBean và xem notification phụ thuộc plugin/chức năng được cài và phiên bản ứng dụng. Nếu không có giao diện notification trong VisualVM hiện tại, điều đó không chứng minh MBean không phát sự kiện. Có thể dùng JConsole hoặc client JMX bằng code để xác minh.

**Client JMX bằng code** phù hợp khi cần kiểm thử tự động, filter chính xác, đối chiếu correlation ID, timeout và kiểm soát remote connection. API \`MBeanServerConnection\` là lớp giao tiếp chung; giao diện công cụ khác nhau nhưng cùng dựa trên các thao tác JMX tương ứng.

Một phép thử hiệu quả có thể dùng JConsole để quan sát trực quan và một test Java để xác nhận event được giao tới listener với dữ liệu đúng.

## 17. Local và remote JMX: khác nhau ở kết nối

Local attach:

\`\`\`text
JConsole -> JVM process -> platform MBeanServer
\`\`\`

Remote:

\`\`\`text
JConsole / client
      |
      v
JMXConnector
      |
      v
MBeanServerConnection
      |
      v
MBeanServer
\`\`\`

Với remote, bạn cần:

- Connector đã được cấu hình và có endpoint reachable.
- Hostname/port/JNDI/RMI phù hợp với hạ tầng mạng.
- Authentication và authorization thích hợp.
- TLS hoặc cơ chế bảo mật vận chuyển phù hợp.
- Firewall và network policy cho phép kết nối.

Remote JMX dùng RMI có thể cần quan tâm cổng registry và cổng endpoint được quảng bá, đặc biệt khi đi qua NAT/container. Một kết nối thành công để đọc attribute không có nghĩa mọi notification chắc chắn được chuyển ổn định trong suốt phiên làm việc.

**Không mở JMX remote công khai lên Internet** chỉ để thử notification. Những MBean operation có thể thay đổi trạng thái hệ thống, và notification có thể mang thông tin nội bộ.

## 18. Listener lifecycle và sự kiện từ MBean thay đổi động

Nếu công cụ hoặc client đã subscribe rồi MBean bị unregister, subscription với MBean cũ không tự động chuyển sang implementation mới. Dù MBean mới đăng ký lại **cùng ObjectName**, listener có thể phải đăng ký lại.

Có thể theo dõi thay đổi registry qua MBean hệ thống \`MBeanServerDelegate\`:

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

connection.addNotificationListener(
    MBeanServerDelegate.DELEGATE_NAME,
    registryListener,
    null,
    null
);
\`\`\`

Khi có \`JMX.mbean.registered\` hoặc \`JMX.mbean.unregistered\`, client có thể cập nhật danh sách MBean cần theo dõi. Với ứng dụng có đăng ký MBean động, đây là một cách xây dựng cơ chế subscribe lại, nhưng vẫn phải xử lý race giữa query/subscribe và trạng thái connection.

Đừng quên tháo listener Delegate khi đóng client.

## 19. Các câu hỏi tự kiểm tra

1. Một MBean xuất hiện trong JConsole nhưng không có tab Notifications: bạn kiểm tra metadata nào đầu tiên?
2. Vì sao phải nhấn Subscribe trước khi gọi \`completeTask\`?
3. \`getNotificationInfo()\` có tự động phát notification không?
4. \`getSequenceNumber()\` có chứng minh không mất event trên mọi MBean không?
5. \`getTimeStamp()\` khác gì thời gian JConsole nhận event?
6. Khi \`NotificationFilterSupport.enableType("app.task.")\` được bật, \`app.task.failed\` có thể được nhận không?
7. Nếu client remote mất kết nối rồi reconnect, listener có cần đăng ký lại không?
8. Khi Spring bean implement \`NotificationPublisherAware\`, publisher được dùng để làm gì?
9. Nếu đã nhận notification nhưng \`CompletedCount\` không đổi, bạn sẽ kiểm tra logic nào?
10. Tại sao notification không nên thay thế log/audit trail bền vững?

Một lời giải thích đầy đủ cần kết nối bốn mắt xích: **MBean đã đăng ký, metadata công bố, listener đã subscribe, và code thực sự phát event**.

## 20. Ghi nhớ

\`\`\`text
[1] Kết nối đúng JVM / MBeanServer
       |
[2] Tìm đúng ObjectName
       |
[3] Kiểm tra notification metadata
       |
[4] Subscribe listener
       |
[5] Kích hoạt một sự kiện biết trước
       |
[6] Quan sát type, source, sequence, time, message, userData
       |
[7] Đọc attribute/log liên quan để đối chiếu
       |
[8] Unsubscribe và đóng connection
\`\`\`

**Mấu chốt của kiểm tra notification trong công cụ JMX:** công cụ chỉ hiển thị những notification nó có cơ hội nhận được. Hãy luôn xác nhận đường phát **và** đường nghe, kích hoạt sự kiện sau khi subscribe, kiểm tra đúng server/ObjectName, và dùng listener Java có timeout khi cần bằng chứng rõ ràng hơn giao diện đồ họa.