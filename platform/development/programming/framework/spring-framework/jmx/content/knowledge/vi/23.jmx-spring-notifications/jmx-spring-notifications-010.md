# Tháo listener khi context dừng trong Spring Framework JMX

## Mục tiêu học tập

Trong JMX, một \`NotificationListener\` được đăng ký để nhận các sự kiện do MBean phát ra. Nếu ứng dụng Spring tạo hoặc gắn listener trong quá trình khởi tạo nhưng không tháo listener khi \`ApplicationContext\` dừng, các đăng ký còn lại có thể giữ tham chiếu tới bean cũ, gây nhận sự kiện lặp, khó khởi động lại context và làm phức tạp quá trình shutdown.

Sau bài này, bạn có thể:

- Phân biệt vòng đời \`NotificationListener\`, \`NotificationBroadcaster\`, \`MBeanServer\` và \`ApplicationContext\`.
- Đăng ký và tháo listener bằng \`addNotificationListener\`/\`removeNotificationListener\`.
- Dùng \`@PreDestroy\`, \`DisposableBean\`, \`@Bean(destroyMethod=...)\` hoặc \`SmartLifecycle\` khi listener do ứng dụng quản lý.
- Hiểu vai trò của Spring \`NotificationListenerBean\` và \`MBeanExporter\` khi đăng ký listener theo cấu hình.
- Thiết kế thứ tự shutdown để tháo listener trước khi các dependency hoặc \`MBeanServer\` cần dùng bị giải phóng.
- Kiểm tra thực nghiệm việc listener không còn nhận notification sau khi context đóng.

## 1. Vì sao phải tháo listener?

JMX có cơ chế notification: một MBean có thể phát \`javax.management.Notification\` khi trạng thái thay đổi, ngưỡng bị vượt, job hoàn thành hoặc sự kiện quản trị xảy ra.

Một listener được cài đặt bằng interface:

\`\`\`java
public interface NotificationListener {
    void handleNotification(
            Notification notification,
            Object handback);
}
\`\`\`

Trong trường hợp dùng \`MBeanServer\`, đăng ký thường có dạng:

\`\`\`java
server.addNotificationListener(
        objectName, listener, filter, handback);
\`\`\`

Đăng ký này tồn tại trong phạm vi MBean server/MBean broadcaster và có thể giữ reference đến listener. **Spring không tự biết để tháo mọi listener mà business code đăng ký thủ công.** Nếu context bị đóng nhưng server vẫn còn sống, registration có thể giữ listener cùng các dependency trước đó, khiến object không được thu gom rác như dự kiến hoặc xử lý sự kiện sau khi thành phần ứng dụng đã dừng.

Ví dụ vòng đời gây vấn đề:

\`\`\`text
JVM / platform MBeanServer: vẫn đang chạy
    |
    +-- MBean phát notification
    |
    +-- Listener thuộc Spring ApplicationContext A
             |
             +-- Service hoặc executor của context A
    |
ApplicationContext A đóng
    |
    +-- Listener không được remove
    |
Context B tạo listener mới
    |
    +-- Có thể có hai listener còn đăng ký
    +-- Notification đến cả listener A và B
\`\`\`

Trong một số thiết lập, MBean được unregister cùng exporter và việc unregister có thể làm mất đường notification gắn với registration đó. Nhưng **không nên dựa vào tác động gián tiếp này** nếu listener được đăng ký tới một MBean thuộc server chung, platform MBean hoặc component có vòng đời dài hơn context.

## 2. Các API JMX liên quan

JDK cung cấp các overload quan trọng:

\`\`\`java
MBeanServer.addNotificationListener(
        ObjectName name,
        NotificationListener listener,
        NotificationFilter filter,
        Object handback);

MBeanServer.removeNotificationListener(
        ObjectName name,
        NotificationListener listener);

MBeanServer.removeNotificationListener(
        ObjectName name,
        NotificationListener listener,
        NotificationFilter filter,
        Object handback);
\`\`\`

**\`name\`** chỉ \`ObjectName\` của broadcaster được đăng ký. **\`listener\`** là đối tượng nhận notification. **\`filter\`** có thể lọc notification theo type hoặc điều kiện. **\`handback\`** là object được trả lại cho listener khi notification được xử lý.

Hai cách remove có ngữ nghĩa khác nhau:

- Overload hai tham số \`removeNotificationListener(name, listener)\` gỡ những registration của listener đó trên broadcaster tương ứng.
- Overload bốn tham số \`removeNotificationListener(name, listener, filter, handback)\` gỡ registration khớp chính xác tổ hợp listener/filter/handback.

Nếu cùng một listener được thêm nhiều lần với các filter hoặc handback khác nhau, cần lựa chọn cách remove phù hợp mục tiêu. Để một component quản lý đúng subscription của nó, nên lưu cả filter/handback đã dùng hoặc bảo đảm listener chỉ có một registration trên broadcaster.

Các lỗi có thể gặp gồm \`InstanceNotFoundException\` nếu \`ObjectName\` không tồn tại, và \`ListenerNotFoundException\` nếu listener hoặc bộ tham số không khớp registration.

## 3. Phân biệt ba nhóm registration

Một ứng dụng Spring JMX có thể đăng ký listener theo các cách:

| Kiểu đăng ký | Ai thực hiện | Ai nên cleanup |
| --- | --- | --- |
| \`MBeanServer.addNotificationListener\` gọi trong business/config code | Thành phần tự viết | Chính component đó hoặc bean lifecycle quản lý |
| \`NotificationListenerBean\` cung cấp cho \`MBeanExporter\` | Spring JMX exporter | Exporter quản lý registrations do nó tạo theo lifecycle |
| Remote \`MBeanServerConnection.addNotificationListener\` | JMX client ở JVM khác | Client/connector owner cần đóng, tháo hoặc tái kết nối theo hợp đồng |

Bài học này tập trung vào các listener **trong ứng dụng Spring**. Đối với listener do exporter quản lý, nên tận dụng lifecycle của exporter. Đối với listener đăng ký thủ công, phải có cách tháo thủ công và test shutdown.

Không nhầm \`ApplicationListener<ContextClosedEvent>\` của Spring Event với \`javax.management.NotificationListener\` của JMX. Chúng là hai hệ thống sự kiện độc lập, dù có thể cùng được dùng trong ứng dụng.

## 4. Ví dụ MBean phát notification

Tạo một MBean broadcaster dùng \`NotificationBroadcasterSupport\`.

**TaskEventsMBean.java**

\`\`\`java
package com.example.jmx;

public interface TaskEventsMBean {
    long getSequence();
    void emitTaskCompleted(String taskId);
}
\`\`\`

**TaskEvents.java**

\`\`\`java
package com.example.jmx;

import java.util.concurrent.atomic.AtomicLong;

import javax.management.MBeanNotificationInfo;
import javax.management.Notification;
import javax.management.NotificationBroadcasterSupport;

public class TaskEvents extends NotificationBroadcasterSupport
        implements TaskEventsMBean {

    public static final String TYPE = "com.example.task.completed";
    private final AtomicLong sequence = new AtomicLong();

    @Override
    public long getSequence() {
        return sequence.get();
    }

    @Override
    public void emitTaskCompleted(String taskId) {
        long next = sequence.incrementAndGet();
        Notification notification = new Notification(
                TYPE, this, next,
                System.currentTimeMillis(),
                "Task completed: " + taskId);
        notification.setUserData(taskId);
        sendNotification(notification);
    }

    @Override
    public MBeanNotificationInfo[] getNotificationInfo() {
        String[] types = {TYPE};
        return new MBeanNotificationInfo[] {
                new MBeanNotificationInfo(
                        types,
                        Notification.class.getName(),
                        "Task completion notifications")
        };
    }
}
\`\`\`

\`TaskEvents\` là Standard MBean vì implement \`TaskEventsMBean\`, đồng thời kế thừa \`NotificationBroadcasterSupport\` để phát notification.

Ví dụ chỉ dùng chuỗi \`taskId\` đơn giản. Trong production, tránh đưa bí mật hoặc dữ liệu cá nhân nhạy cảm vào \`userData\`, message hoặc handback vì hệ thống quản trị và logging có thể ghi nhận chúng.

## 5. Listener ghi nhận notification

**TaskCompletionListener.java**

\`\`\`java
package com.example.jmx;

import java.util.concurrent.atomic.AtomicInteger;
import javax.management.Notification;
import javax.management.NotificationListener;

public class TaskCompletionListener implements NotificationListener {
    private final AtomicInteger received = new AtomicInteger();

    @Override
    public void handleNotification(
            Notification notification,
            Object handback) {

        if (TaskEvents.TYPE.equals(notification.getType())) {
            received.incrementAndGet();
            System.out.println("Received: "
                    + notification.getMessage());
        }
    }

    public int getReceivedCount() {
        return received.get();
    }
}
\`\`\`

Class này chỉ ghi nhận sự kiện để dễ kiểm tra. Trong ứng dụng thật, listener có thể đẩy metric, cập nhật cache hoặc thực thi logic phụ trợ. Khi shutdown, những dependency mà listener dùng (executor, repository, queue...) có thể đã ngừng hoạt động; càng cần tháo listener đúng thời điểm.

\`NotificationListener\` không tự có callback \`close()\` hoặc \`destroy()\`. Bản thân interface không biết ai đăng ký nó, trên \`ObjectName\` nào hoặc với filter/handback gì.

## 6. Cách 1 — Đăng ký thủ công và tháo bằng @PreDestroy

Một Spring bean lifecycle có thể quản lý cả subscription.

**TaskNotificationSubscription.java**

\`\`\`java
package com.example.jmx;

import javax.annotation.processing.Generated;
import javax.management.MBeanServer;
import javax.management.NotificationFilter;
import javax.management.NotificationListener;
import javax.management.ObjectName;

import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;

public class TaskNotificationSubscription {

    private final MBeanServer server;
    private final ObjectName target;
    private final NotificationListener listener;
    private final NotificationFilter filter;
    private final Object handback;
    private boolean registered;

    public TaskNotificationSubscription(
            MBeanServer server,
            ObjectName target,
            NotificationListener listener) {
        this.server = server;
        this.target = target;
        this.listener = listener;
        this.filter = null;
        this.handback = null;
    }

    @PostConstruct
    public synchronized void start() throws Exception {
        if (!registered) {
            server.addNotificationListener(
                    target, listener, filter, handback);
            registered = true;
        }
    }

    @PreDestroy
    public synchronized void stop() throws Exception {
        if (registered) {
            try {
                server.removeNotificationListener(
                        target, listener, filter, handback);
            } finally {
                registered = false;
            }
        }
    }
}
\`\`\`

Trong Spring Framework 6+, ví dụ sử dụng \`jakarta.annotation\` tương ứng với Jakarta EE annotations. Nếu dự án dùng Spring Framework cũ, package và dependencies có thể khác.

**Lưu ý:** import \`javax.annotation.processing.Generated\` không cần thiết cho subscription; đó là annotation dành cho generated source, không liên quan lifecycle. Trong mã triển khai, chỉ cần các imports JMX và \`jakarta.annotation\` đã dùng. Đoạn ví dụ trình bày lớp lifecycle để hiểu quan hệ \`PostConstruct\`/\`PreDestroy\`.

Có một vấn đề thực tế cần giải quyết: \`@PostConstruct\` chạy khi bean subscription khởi tạo, nhưng exporter có thể **chưa đăng ký MBean** vào server tại thời điểm đó. Nếu listener subscription phụ thuộc vào MBean do \`MBeanExporter\` tạo, cần thiết kế thứ tự khởi tạo rõ ràng, hoặc sử dụng cách tiếp cận do exporter quản lý ở mục sau. Dùng \`@DependsOn\` phù hợp, hoặc đăng ký listener sau khi context refresh hoàn tất.

## 7. Cách 2 — Dùng NotificationListenerBean với MBeanExporter

Spring Framework có \`org.springframework.jmx.export.NotificationListenerBean\` để mô tả listener được cấu hình với \`MBeanExporter\`.

Ví dụ Java configuration:

\`\`\`java
package com.example.jmx;

import java.lang.management.ManagementFactory;
import java.util.Map;
import javax.management.MBeanServer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.NotificationListenerBean;

@Configuration
public class ExporterManagedNotificationConfiguration {

    @Bean
    public MBeanServer platformMBeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public TaskEvents taskEvents() {
        return new TaskEvents();
    }

    @Bean
    public TaskCompletionListener completionListener() {
        return new TaskCompletionListener();
    }

    @Bean
    public MBeanExporter taskExporter(
            MBeanServer platformMBeanServer,
            TaskEvents taskEvents,
            TaskCompletionListener completionListener) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(platformMBeanServer);
        exporter.setBeans(Map.of(
                "com.example.task:type=TaskEvents,name=primary",
                taskEvents));

        NotificationListenerBean listenerBean =
                new NotificationListenerBean(completionListener);
        listenerBean.setMappedObjectName(
                "com.example.task:type=TaskEvents,name=primary");
        exporter.setNotificationListeners(listenerBean);
        return exporter;
    }
}
\`\`\`

Khi \`MBeanExporter\` vừa export MBean vừa quản lý notification listener, nó có thể tổ chức đăng ký và hủy đăng ký trong lifecycle của chính exporter. Đây thường là lựa chọn đơn giản hơn so với việc tạo một \`@PostConstruct\` subscription riêng cho MBean mà exporter đồng thời sở hữu.

\`NotificationListenerBean\` cho phép cấu hình filter, handback và \`mappedObjectNames\` phù hợp để giới hạn MBean nguồn. Khi ứng dụng dùng nhiều MBeans, cần xác định listener nào nhận notification từ tên nào, không giả định sẽ tự chỉ nhận đúng một MBean.

Trong Spring version cụ thể, API setter/constructor phải được đối chiếu với version dependency của ứng dụng, đặc biệt khi dùng các property mapping hoặc notification filters khác.

## 8. Cách 3 — Dùng SmartLifecycle khi cần thứ tự start/stop

Với những listener phụ thuộc vào executor hoặc cần start sau khi exporter đăng ký, \`SmartLifecycle\` là lựa chọn có thể kiểm soát pha lifecycle.

**ManagedNotificationSubscriber.java**

\`\`\`java
package com.example.jmx;

import javax.management.MBeanServer;
import javax.management.NotificationListener;
import javax.management.ObjectName;

import org.springframework.context.SmartLifecycle;

public class ManagedNotificationSubscriber implements SmartLifecycle {

    private final MBeanServer server;
    private final ObjectName name;
    private final NotificationListener listener;

    private volatile boolean running;

    public ManagedNotificationSubscriber(
            MBeanServer server,
            ObjectName name,
            NotificationListener listener) {
        this.server = server;
        this.name = name;
        this.listener = listener;
    }

    @Override
    public synchronized void start() {
        if (running) {
            return;
        }

        try {
            server.addNotificationListener(
                    name, listener, null, null);
            running = true;
        } catch (Exception e) {
            throw new IllegalStateException(
                    "Cannot register JMX listener", e);
        }
    }

    @Override
    public synchronized void stop() {
        if (!running) {
            return;
        }

        try {
            server.removeNotificationListener(
                    name, listener);
        } catch (Exception e) {
            throw new IllegalStateException(
                    "Cannot unregister JMX listener", e);
        } finally {
            running = false;
        }
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public int getPhase() {
        return 100;
    }
}
\`\`\`

Spring \`SmartLifecycle\` có cơ chế start/stop theo pha. Khi start, phase thấp hơn thường được khởi động trước; khi stop, phase cao hơn được dừng trước. Tuy nhiên, **exporter không nhất thiết là \`SmartLifecycle\`**. Vì vậy, phase không tự bảo đảm exporter đã hoàn tất đăng ký; cần biết exporter khởi tạo trong quá trình context refresh và dùng dependency phù hợp.

Ví dụ \`stop()\` ném runtime exception khi removal lỗi. Trong hệ thống thực, có thể cần ghi log và tiếp tục dọn các thành phần khác; không nên để một listener không thể tháo khiến toàn bộ shutdown treo hoặc bỏ qua cleanup quan trọng.

Nếu cần thực sự theo dõi kết quả shutdown bất đồng bộ, sử dụng overload \`stop(Runnable callback)\` và gọi callback sau khi việc stop hoàn tất; mặc định \`SmartLifecycle\` có hành vi hỗ trợ nhưng với tác vụ async bạn nên hiện thực rõ.

## 9. Một cấu hình đơn giản có @DependsOn

Nếu listener subscription được tạo với \`@PostConstruct\`, nó cần thấy broadcaster MBean đã đăng ký trước khi gọi \`addNotificationListener\`.

\`\`\`java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.DependsOn;

@Configuration
public class ManualListenerConfig {

    @Bean
    @DependsOn("taskExporter")
    public TaskNotificationSubscription subscription(
            MBeanServer platformMBeanServer,
            TaskCompletionListener completionListener)
            throws Exception {

        return new TaskNotificationSubscription(
                platformMBeanServer,
                new ObjectName(
                    "com.example.task:type=TaskEvents,name=primary"),
                completionListener);
    }
}
\`\`\`

Giả định \`taskExporter\`, \`platformMBeanServer\` và \`completionListener\` đã được khai báo trong context. Với \`@DependsOn("taskExporter")\`, Spring khởi tạo exporter trước bean subscription, và khi destroy theo dependency, subscription có cơ hội được dọn trước exporter/server owner.

Cần tránh đồng thời dùng \`NotificationListenerBean\` trong exporter **và** một manual subscription cho cùng listener/MBean mà không có chủ đích. Điều đó có thể tạo hai registrations và khiến listener nhận cùng notification nhiều lần.

## 10. ContextClosedEvent có phù hợp để remove không?

Một cách khác là lắng nghe \`ContextClosedEvent\`:

\`\`\`java
import org.springframework.context.ApplicationListener;
import org.springframework.context.event.ContextClosedEvent;

public class ShutdownListener
        implements ApplicationListener<ContextClosedEvent> {

    @Override
    public void onApplicationEvent(ContextClosedEvent event) {
        // Tháo đăng ký JMX nếu component này sở hữu subscription.
    }
}
\`\`\`

Tuy nhiên, \`ContextClosedEvent\` là một **Spring application event**; nó không tương đương \`NotificationListener\` của JMX. Nếu vừa có \`@PreDestroy\` vừa lắng nghe \`ContextClosedEvent\` để remove cùng registration, cần thiết kế idempotency để tránh removal lặp.

Thường nên chọn một owner và một lifecycle hook chính. \`@PreDestroy\` hoặc \`SmartLifecycle\` phù hợp cho một bean đóng gói subscription. \`ContextClosedEvent\` có thể cần khi muốn phản ứng sớm với việc context bắt đầu đóng, nhưng không nên lạm dụng nếu chỉ để gỡ một listener.

## 11. Kiểm tra listener đã được tháo thực sự

Một kiểm thử hiệu quả không chỉ gọi \`context.close()\` rồi giả định cleanup đúng. Cần bảo đảm một broadcaster còn hoạt động có thể phát notification sau khi context đóng nhưng listener cũ không nhận nữa.

Ví dụ thiết kế fixture:

\`\`\`text
Test-owned MBeanServer
    |
    +-- TaskEvents MBean được đăng ký bởi test owner
    |
Spring context A
    |
    +-- TaskCompletionListener
    +-- Subscription đăng ký vào TaskEvents MBean
    |
1. emit -> listener count = 1
2. close context A
3. emit -> listener count vẫn = 1
4. tạo context B / listener B
5. emit -> listener B nhận một lần, A không nhận
6. close context B và unregister TaskEvents
\`\`\`

Điểm then chốt là **broadcaster phải tồn tại lâu hơn context đang thử**. Nếu context sở hữu và unregister broadcaster khi đóng, bạn không thể phát thêm notification để chứng minh listener đã được tháo, vì MBean nguồn cũng đã biến mất.

Để test độc lập, dùng một \`MBeanServer\` riêng tạo bằng \`MBeanServerFactory.createMBeanServer\` và cleanup bằng \`releaseMBeanServer\` sau khi kết thúc.

## 12. Ví dụ test với listener được quản lý thủ công

Đoạn JUnit sau minh họa logic kiểm tra removal. Test tạo server và broadcaster ngoài context, còn subscriber được khởi tạo và đóng bằng Spring.

\`\`\`java
package com.example.jmx;

import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.ObjectName;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.*;

class NotificationShutdownTest {

    @Test
    void listenerStopsReceivingAfterContextCloses() throws Exception {
        MBeanServer server =
                MBeanServerFactory.createMBeanServer("isolated-test");
        ObjectName name = new ObjectName(
                "com.example.task:type=TaskEvents,name=primary");

        TaskEvents broadcaster = new TaskEvents();
        server.registerMBean(broadcaster, name);

        TaskCompletionListener listener = new TaskCompletionListener();

        try {
            var context = new AnnotationConfigApplicationContext();
            context.registerBean(
                    "testMBeanServer",
                    MBeanServer.class,
                    () -> server);
            context.registerBean(
                    "completionListener",
                    TaskCompletionListener.class,
                    () -> listener);
            context.registerBean(
                    TaskNotificationSubscription.class,
                    () -> new TaskNotificationSubscription(
                            server, name, listener));
            context.refresh();

            try {
                broadcaster.emitTaskCompleted("task-1");
                assertEquals(1, listener.getReceivedCount());
            } finally {
                context.close();
            }

            broadcaster.emitTaskCompleted("task-2");
            assertEquals(1, listener.getReceivedCount(),
                    "Listener must be removed after context close");
        } finally {
            if (server.isRegistered(name)) {
                server.unregisterMBean(name);
            }
            MBeanServerFactory.releaseMBeanServer(server);
        }
    }
}
\`\`\`

Ví dụ yêu cầu Spring xử lý \`@PostConstruct\` và \`@PreDestroy\` (có dependency \`jakarta.annotation-api\` phù hợp). Để test tránh dependency đó, có thể khai báo bean với \`initMethod\` và \`destroyMethod\` hoặc dùng \`DisposableBean\`.

Lưu ý rằng \`NotificationBroadcasterSupport\` mặc định có thể dispatch notification đồng bộ nếu không cung cấp executor; nếu cấu hình asynchronous executor, assertion cần chờ bằng cơ chế đồng bộ rõ ràng, không dùng \`Thread.sleep\` tùy tiện để suy luận kết quả.

## 13. Kiểm thử với NotificationListenerBean của MBeanExporter

Khi dùng exporter-managed listener, fixture nên có:

- MBean \`TaskEvents\` do exporter đăng ký.
- \`TaskCompletionListener\` được cấu hình qua \`NotificationListenerBean\`.
- \`MBeanExporter\` có \`notificationListeners\` tương ứng.
- \`ApplicationContext\` đóng để kích hoạt cleanup exporter.

Test cần xác nhận listener được gắn khi context chạy và không còn registration sau khi exporter bị destroy. Vì broadcaster có thể bị unregister cùng lúc, có thể xây dựng fixture có broadcaster lâu sống hơn context, nhưng việc exporter có quản lý listener gắn với một MBean bên ngoài mapping của nó còn phụ thuộc cấu hình mapping/listener hỗ trợ của Spring. Đọc đúng API và dùng integration test để xác minh.

Nếu chỉ kiểm tra listener count khi context đang chạy, test chưa chứng minh removal. Cần kiểm tra sau close hoặc bằng một phép thử tạo lại context để phát hiện duplicate registrations.

## 14. Khi listener đăng ký nhiều lần

JMX cho phép cùng listener object được thêm vào một broadcaster nhiều lần, kể cả với filter/handback khác nhau. Mỗi registration có thể tạo một lượt callback.

Ví dụ:

\`\`\`java
server.addNotificationListener(name, listener, filterA, "A");
server.addNotificationListener(name, listener, filterB, "B");
\`\`\`

Khi chỉ gọi:

\`\`\`java
server.removeNotificationListener(name, listener, filterA, "A");
\`\`\`

registration với filter B và handback B có thể vẫn tồn tại. Nếu muốn tháo tất cả registration của listener đó tại tên MBean, dùng overload hai tham số:

\`\`\`java
server.removeNotificationListener(name, listener);
\`\`\`

Tuy nhiên, thao tác gỡ tất cả cần có ownership phù hợp. Nếu một listener object được chia sẻ giữa nhiều module, module này không nên tự gỡ đăng ký thuộc module khác. Cách an toàn thường là mỗi subscription owner có listener/filter/handback riêng và tháo đúng phần mình tạo.

## 15. Thứ tự shutdown: listener, exporter, server

Một thiết kế nên phân định rõ:

\`\`\`text
ApplicationContext
    |
    +-- MBeanServer (có thể thuộc JVM hoặc do Spring factory tạo)
    +-- MBeanExporter (đăng ký MBeans)
    +-- NotificationSubscription (gắn listener)
    |
    v
Shutdown
    1. Ngăn tạo subscription mới
    2. Tháo listener thuộc context
    3. Dừng executor xử lý notification theo thứ tự phù hợp
    4. Unregister MBeans do exporter quản lý
    5. Release custom MBeanServer nếu context sở hữu
\`\`\`

Nếu listener callback dùng executor, đôi khi cần ngừng nhận notification **trước** khi shutdown executor. Nếu executor đã ngừng nhưng listener còn đăng ký, callback vẫn có thể cố submit task vào executor và nhận \`RejectedExecutionException\`.

Khi \`TaskNotificationSubscription\` inject hoặc \`@DependsOn\` exporter/server, Spring biết quan hệ phụ thuộc và có thể thực hiện destroy theo thứ tự ngược dependency. Đối với server được mượn từ JVM, context không nên release server đó.

## 16. Xử lý lỗi cleanup

Trong shutdown, \`removeNotificationListener\` có thể thất bại nếu:

- MBean đã bị unregister bởi exporter hoặc thành phần khác.
- Listener chưa từng đăng ký thành công.
- Registration đã được remove bởi path khác.
- Tên server hoặc \`ObjectName\` không còn khớp.
- Remote connection đã ngắt (đối với client JMX từ xa).

Một implementation có thể bắt lỗi và ghi log theo mức độ phù hợp:

\`\`\`java
public synchronized void stopSafely() {
    if (!registered) {
        return;
    }

    try {
        server.removeNotificationListener(
                target, listener, filter, handback);
    } catch (javax.management.InstanceNotFoundException
            | javax.management.ListenerNotFoundException ex) {
        // MBean/listener có thể đã được dọn bởi owner khác.
        // Ghi log nếu cần; xác minh lifecycle thực tế.
    } finally {
        registered = false;
    }
}
\`\`\`

Ví dụ này minh họa cleanup có chủ đích, không phải khuyến nghị bỏ qua mọi lỗi. Đặc biệt, nếu remove thất bại vì connection hoặc quyền, listener có thể vẫn còn trong registry; không nên ghi nhận trạng thái “đã tháo thành công” nếu không có bằng chứng.

Với một subscription lưu trạng thái \`registered\`, việc set \`false\` trong \`finally\` là một quyết định lifecycle: tránh gỡ lặp, nhưng có thể che một registration còn tồn tại nếu remove thực sự thất bại. Trong production, nên phân biệt **remove success**, **đã mất registration** và **remove chưa xác minh** bằng logs hoặc trạng thái rõ ràng.

## 17. Listener sử dụng remote MBeanServerConnection

Khi listener được cài trên một MBean ở JVM khác, code có thể nhận \`MBeanServerConnection\` từ \`JMXConnector\`:

\`\`\`java
MBeanServerConnection connection =
        connector.getMBeanServerConnection();

connection.addNotificationListener(
        objectName, listener, null, null);
\`\`\`

Khi dừng:

\`\`\`java
connection.removeNotificationListener(
        objectName, listener);
connector.close();
\`\`\`

Nếu listener còn đăng ký khi connector đóng hoặc server ngắt, trạng thái có thể phụ thuộc protocol/session. Không nên dựa vào việc disconnect để giả định mọi subscription đã được cleanup theo logic ứng dụng; tháo listener trong khi connection còn hợp lệ và đóng connector trong \`finally\` khi cần.

Remote notification listeners còn có vấn đề latency, reconnection và duplicate delivery. Khi re-register sau reconnect, cần bảo đảm không vô tình tạo nhiều registrations ở cùng server.

## 18. Khác biệt với Spring ApplicationListener

Hai khái niệm cùng chữ “listener” nhưng không tương đương:

| Khái niệm | Hệ thống | Đăng ký | Cleanup |
| --- | --- | --- | --- |
| \`NotificationListener\` | Java JMX | \`MBeanServer.addNotificationListener\` | \`removeNotificationListener\` hoặc exporter lifecycle |
| \`ApplicationListener<ContextClosedEvent>\` | Spring Events | Spring \`ApplicationEventMulticaster\` | Theo lifecycle Spring event registration |
| \`@EventListener\` | Spring Events | Container tìm listener method | Container quản lý đăng ký theo context |
| \`NotificationListenerBean\` | Spring JMX export | Gắn vào \`MBeanExporter\` | Exporter quản lý khi dùng đúng cấu hình |

Một \`@EventListener\` không tự đăng ký JMX notification listener. Tương tự, một JMX \`NotificationListener\` không tự nhận Spring application events nếu không có bridge rõ ràng.

## 19. Các lỗi phổ biến

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Listener nhận notification hai lần sau restart context | Subscription cũ chưa tháo | Remove ở lifecycle hook, kiểm tra owner |
| Context đóng nhưng bean vẫn bị giữ trong heap | MBean server còn reference đến listener | Dùng heap analysis và kiểm tra registrations |
| \`ListenerNotFoundException\` khi stop | Gỡ sai listener/filter/handback hoặc đã gỡ trước | Lưu chính xác thông số đăng ký, cleanup idempotent |
| \`InstanceNotFoundException\` khi stop | MBean đã bị unregister | Thiết kế destroy order hoặc xử lý trường hợp đã mất |
| Startup lỗi khi add listener | Exporter chưa đăng ký broadcaster | Dùng exporter-managed listener hoặc lifecycle dependency |
| Callback chạy khi executor đã shutdown | Listener tháo quá muộn | Dừng nguồn callback trước executor |
| JConsole không thấy notification | Kết nối sai JVM/MBean hoặc broadcaster không khai báo notification metadata | Kiểm tra đúng server, \`MBeanInfo\` và notification types |
| Test pass riêng nhưng fail khi chạy suite | Test cùng dùng platform server/registration | Dùng MBean server và tên riêng cho fixture |
| Listener không nhận sự kiện | Filter loại bỏ, sai \`ObjectName\`, broadcaster không phát | Kiểm tra filter, handback, MBean nguồn |
| Spring bean bị destroy nhưng vẫn nhận callback | Registration sống lâu hơn context | Kiểm tra \`@PreDestroy\`, \`SmartLifecycle\` và thứ tự dọn |

## 20. Thiết kế subscription có ownership rõ ràng

Một pattern có thể tái sử dụng là tạo bean chịu trách nhiệm toàn bộ vòng đời subscription:

\`\`\`text
JmxSubscription
  - MBeanServerConnection server
  - ObjectName target
  - NotificationListener listener
  - NotificationFilter filter
  - Object handback
  - registrationState
  + start()
  + stop()
\`\`\`

Pattern này có các lợi ích:

1. Không rải rác \`addNotificationListener\` ở nhiều service methods.
2. Chỉ một owner biết registration được tạo và phải tháo thế nào.
3. Có thể kiểm tra trạng thái và tránh duplicate registration.
4. Dễ đặt quan hệ dependency với exporter/server.
5. Dễ test khi context đóng.
6. Dễ mở rộng logic retry/reconnect có kiểm soát cho remote JMX.

Khi business service không cần biết JMX, để subscription thành một adapter ở tầng monitoring/management thay vì trộn lifecycle code vào service nghiệp vụ.

## 21. Bài tập thực hành

**Bài 1 — Listener một lần:** tạo \`TaskEvents\`, \`TaskCompletionListener\` và subscription. Phát notification trước khi đóng context, assert count tăng; đóng context và phát lại từ broadcaster bên ngoài, assert count không tăng.

**Bài 2 — Duplicate registrations:** đăng ký cùng listener hai lần với hai handback khác nhau. Quan sát callback count; thử remove chỉ một registration rồi remove toàn bộ. Giải thích khác nhau giữa hai overload remove.

**Bài 3 — Lifecycle order:** tạo exporter-managed broadcaster và subscription \`@PostConstruct\` độc lập. Quan sát tình huống add quá sớm, sau đó dùng \`@DependsOn\` hoặc chuyển sang \`NotificationListenerBean\` và kiểm tra kết quả.

**Bài 4 — SmartLifecycle:** tạo subscriber có phase 100, một executor-managed bean có phase thấp hơn, kiểm tra quá trình stop. Giải thích vì sao subscriber nên ngừng nhận notification trước executor.

**Bài 5 — Test restart:** khởi tạo context A rồi đóng; khởi tạo context B dùng cùng external broadcaster. Phát notification và xác minh listener A không nhận, listener B nhận đúng một lần.

**Bài 6 — Remote JMX:** thiết kế client dùng \`JMXConnector\` và \`MBeanServerConnection\`. Mô tả chiến lược tháo listener trước \`connector.close()\`, và xử lý trường hợp connection mất trong lúc shutdown.

## Kết luận

**Tháo listener khi \`ApplicationContext\` dừng** là trách nhiệm quan trọng của ứng dụng Spring sử dụng JMX notification. Listener có thể được gắn qua \`MBeanServer.addNotificationListener\` hoặc cấu hình cùng \`MBeanExporter\` bằng \`NotificationListenerBean\`. Nếu subscription do ứng dụng tự tạo, hãy đóng gói nó thành bean có lifecycle rõ ràng và gọi \`removeNotificationListener\` trước khi các dependency hoặc server owner bị dọn. Chỉ kiểm tra context đóng là chưa đủ; một bài test tốt chứng minh listener **không còn nhận notification** từ broadcaster vẫn sống sau khi context dừng.
