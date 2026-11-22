# Kiểm thử notification listener và filter trong Spring Framework JMX

## Mục tiêu

Trong Java Management Extensions (JMX), một MBean có thể phát **notification** để báo rằng trạng thái runtime đã thay đổi, tác vụ hoàn tất hoặc xảy ra sự kiện vận hành. Client đăng ký \`NotificationListener\` để nhận notification, và có thể cung cấp \`NotificationFilter\` để chỉ nhận một phần các sự kiện. Spring Framework hỗ trợ JMX export cùng các cấu hình listener giúp tích hợp notification vào ứng dụng.

Khi viết test, không thể chỉ kiểm tra một phương thức \`sendNotification()\` đã được gọi. Cần kiểm tra đầy đủ hợp đồng: **nguồn phát, loại notification, thứ tự, sequence number, userData, filter, handback, thời điểm đăng ký/hủy đăng ký và behavior khi listener ném exception**. Nếu nhận sự kiện từ xa hoặc có luồng bất đồng bộ, còn phải kiểm soát timeout, mất kết nối và sự kiện đến trễ.

Bài học giúp bạn:

- Phân biệt \`NotificationBroadcaster\`, \`NotificationEmitter\`, \`NotificationListener\` và \`NotificationFilter\`.
- Viết MBean test phát notification có type và sequence number rõ ràng.
- Dùng \`MBeanServer.addNotificationListener\` và \`removeNotificationListener\` trong JUnit.
- Kiểm tra notification được nhận và sự kiện bị filter loại trừ.
- Kiểm tra chính xác \`handback\`, \`source\`, \`message\`, \`userData\` và sequence number.
- Tránh test flakiness bằng \`CountDownLatch\`, timeout giới hạn và cleanup trong \`finally\`.
- Kiểm thử listener Spring qua \`NotificationListenerBean\`/exporter khi tích hợp với ApplicationContext.
- Phân tích giới hạn của local và remote notifications, thread ordering, duplicate callbacks và vòng đời context.
- Thiết kế negative tests cho filter, unregister và isolation giữa các test.

## 1. Kiến trúc notification của JMX

Các thành phần chính:

\`\`\`text
Business event / runtime state
             |
             v
          MBean
             |
             v
NotificationBroadcaster / NotificationEmitter
             |
             v
         MBeanServer
             |
             +── Listener A + Filter A + Handback A
             |
             +── Listener B + Filter B + Handback B
             |
             +── Listener C (không filter)
\`\`\`

- \`Notification\` là một sự kiện có type, source, sequence number, timestamp, message và userData tùy dùng.
- \`NotificationListener\` định nghĩa \`handleNotification(Notification, Object)\`.
- \`NotificationFilter\` quyết định notification nào được chuyển cho một registration cụ thể.
- \`NotificationBroadcaster\` cho phép add/remove listener.
- \`NotificationEmitter\` bổ sung dạng remove listener chính xác theo listener/filter/handback.
- \`NotificationBroadcasterSupport\` là lớp tiện ích thường dùng khi viết MBean phát notification.
- \`MBeanServerConnection\` cho phép đăng ký listener local hoặc remote tùy connector.

Một notification có thể được phát nhưng không được một listener nhận vì:
1. Listener chưa được đăng ký.
2. Filter trả \`false\`.
3. Listener đã bị remove.
4. MBean không phát notification theo đường đang được test.
5. Client kết nối tới MBeanServer/ObjectName khác.
6. Remote connector bị lỗi hoặc subscription không còn.
7. Test kết thúc quá sớm, trước khi callback chạy.

Vì vậy test nên xác minh cả **đường truyền và điều kiện lọc**, chứ không chỉ số lần method emit được gọi.

## 2. Định nghĩa hợp đồng notification trước khi test

Giả sử MBean quản lý một worker và phát các loại sau:

| Type | Ý nghĩa | Payload dự kiến |
|---|---|---|
| \`com.example.worker.started\` | Worker bắt đầu | Mã worker |
| \`com.example.worker.paused\` | Worker tạm dừng hiệu lực | Lý do pause |
| \`com.example.worker.failed\` | Worker lỗi | Mã lỗi đã redact |
| \`com.example.worker.completed\` | Một batch hoàn tất | Batch ID |

Hợp đồng test cần xác định:

- Type là chuỗi ổn định.
- Source là nguồn được công bố theo JMX.
- Sequence number tăng theo chính sách của emitter.
- Timestamp được gán hợp lệ, nhưng không assert bằng một thời điểm tuyệt đối dễ lỗi.
- Message không chứa secret.
- userData có schema ổn định và kích thước có giới hạn.
- Có hoặc không bảo đảm thứ tự giữa nhiều producer threads.
- Có cơ chế nào lọc event type hay severity.
- Listener có cần nhận handback nào khi callback chạy.

Với remote JMX, payload phải phù hợp với serializer/classloading của connector. Một custom Java object trong userData có thể khiến client cần class tương ứng; cân nhắc \`CompositeData\` hoặc kiểu dữ liệu đơn giản nếu cần tương tác rộng.

## 3. MBean test có khả năng phát notification

Một MBean JMX tiêu chuẩn có thể implement \`NotificationEmitter\` hoặc kế thừa \`NotificationBroadcasterSupport\`. Ví dụ:

\`\`\`java
package com.example.jmx;

public interface WorkerEventsMBean {
    void start();
    void pause();
    void fail(String code);
    long getEventCount();
}
\`\`\`

\`\`\`java
package com.example.jmx;

import java.util.concurrent.atomic.AtomicLong;
import javax.management.Notification;
import javax.management.NotificationBroadcasterSupport;
import javax.management.MBeanNotificationInfo;

public class WorkerEvents extends NotificationBroadcasterSupport
        implements WorkerEventsMBean {

    private final AtomicLong sequence = new AtomicLong();

    @Override
    public void start() {
        publish("com.example.worker.started", "Worker started", "worker-A");
    }

    @Override
    public void pause() {
        publish("com.example.worker.paused", "Worker paused", "maintenance");
    }

    @Override
    public void fail(String code) {
        publish("com.example.worker.failed", "Worker failed", code);
    }

    @Override
    public long getEventCount() {
        return sequence.get();
    }

    private void publish(String type, String message, String data) {
        long n = sequence.incrementAndGet();
        Notification event = new Notification(
            type, this, n, System.currentTimeMillis(), message);
        event.setUserData(data);
        sendNotification(event);
    }

    @Override
    public MBeanNotificationInfo[] getNotificationInfo() {
        String[] types = {
            "com.example.worker.started",
            "com.example.worker.paused",
            "com.example.worker.failed"
        };

        return new MBeanNotificationInfo[] {
            new MBeanNotificationInfo(
                types,
                Notification.class.getName(),
                "Lifecycle events for worker operations")
        };
    }
}
\`\`\`

Trong JMX MBeanServer, \`source\` trên notification có thể được điều chỉnh/biểu diễn dưới \`ObjectName\` theo cơ chế phát qua server/connector. Khi test local class trực tiếp, source có thể là \`this\`. Vì vậy test nên phân biệt contract source ở cấp emitter và source quan sát được bởi listener qua MBeanServer.

Đối với Spring \`@ManagedResource\` và \`@ManagedNotification\`, exporter/assembler xử lý metadata về notification. Nếu viết MBean chuẩn như trên, không cần annotation Spring chỉ để thử filter.

## 4. Đăng ký MBean trong test có cleanup an toàn

Có thể sử dụng một MBeanServer riêng cho mỗi test để tránh collision với platform server của ứng dụng:

\`\`\`java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.ObjectName;

MBeanServer server = MBeanServerFactory.newMBeanServer();
ObjectName name = new ObjectName(
    "com.example.test:type=WorkerEvents,name=Local");

WorkerEvents bean = new WorkerEvents();
server.registerMBean(bean, name);
\`\`\`

\`newMBeanServer()\` tạo server không được đăng ký trong factory list như \`createMBeanServer()\`, phù hợp cho fixture cô lập đơn giản. Khi dùng platform server, tránh ObjectName cố định gây xung đột test chạy song song và chỉ unregister MBean do fixture sở hữu.

Ví dụ lifecycle:

\`\`\`java
boolean owned = false;

try {
    server.registerMBean(bean, name);
    owned = true;

    // Add listeners, emit and assert notifications.
} finally {
    if (owned && server.isRegistered(name)) {
        server.unregisterMBean(name);
    }
}
\`\`\`

Trong test thực tế, listener cũng phải được remove trong finally trước khi unregister. Điều này tránh callback đến một fixture đã kết thúc và làm nhiễu test tiếp theo.

## 5. Test listener nhận notification theo type

JUnit 5 có thể dùng \`CountDownLatch\` để chờ callback mà không \`Thread.sleep\` tùy tiện:

\`\`\`java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import javax.management.*;

import org.junit.jupiter.api.Test;

class WorkerNotificationTest {

    @Test
    void receivesStartedNotification() throws Exception {
        MBeanServer server = MBeanServerFactory.newMBeanServer();
        ObjectName name = new ObjectName(
            "com.example.test:type=WorkerEvents,name=Local");
        WorkerEvents bean = new WorkerEvents();
        server.registerMBean(bean, name);

        CountDownLatch latch = new CountDownLatch(1);
        AtomicReference<Notification> received =
            new AtomicReference<>();

        NotificationListener listener = (n, handback) -> {
            received.set(n);
            latch.countDown();
        };

        try {
            server.addNotificationListener(name, listener, null, null);

            server.invoke(name, "start", new Object[0], new String[0]);

            assertTrue(latch.await(3, TimeUnit.SECONDS));
            Notification n = received.get();
            assertNotNull(n);
            assertEquals("com.example.worker.started", n.getType());
            assertEquals("worker-A", n.getUserData());
            assertTrue(n.getSequenceNumber() > 0);
        } finally {
            try {
                server.removeNotificationListener(name, listener);
            } finally {
                if (server.isRegistered(name)) {
                    server.unregisterMBean(name);
                }
            }
        }
    }
}
\`\`\`

Nếu emitter và listener được dispatch trên cùng thread, latch đã được countDown trước khi \`invoke\` trả về. Nếu dispatch bất đồng bộ, \`await\` xử lý độ trễ có giới hạn. Timeout ba giây là ví dụ; trong CI thực tế nên đặt ngưỡng phù hợp nhưng không cho phép chờ vô hạn.

Không nên assert \`n.getTimeStamp() == System.currentTimeMillis()\` vì thời gian thực luôn thay đổi. Có thể assert timestamp nằm trong khoảng chấp nhận được của test, có độ lệch để tránh flakiness.

## 6. NotificationFilter và ý nghĩa của việc lọc

Một filter nhận \`Notification\` và trả boolean:

\`\`\`java
import javax.management.Notification;
import javax.management.NotificationFilter;

NotificationFilter failuresOnly =
    n -> n != null &&
         "com.example.worker.failed".equals(n.getType());
\`\`\`

Khi đăng ký listener:

\`\`\`java
server.addNotificationListener(
    name, listener, failuresOnly, "failure-subscription");
\`\`\`

Với filter này, notification \`started\` hoặc \`paused\` không được chuyển cho registration trên. \`failed\` được chuyển cho listener cùng handback \`"failure-subscription"\`.

### 6.1 NotificationFilterSupport

JMX cung cấp \`NotificationFilterSupport\` để bật các type-prefix:

\`\`\`java
import javax.management.NotificationFilterSupport;

NotificationFilterSupport filter =
    new NotificationFilterSupport();

filter.enableType("com.example.worker.failed");
\`\`\`

Quan trọng: \`NotificationFilterSupport.enableType(String)\` kiểm tra tiền tố type, không chỉ so khớp toàn bộ chuỗi. Nếu bật \`"com.example.worker"\`, các type bắt đầu bằng tiền tố đó có thể đều qua filter. Muốn exact match, dùng \`NotificationFilter\` tùy biến với \`equals\` hoặc kiểm tra cấu trúc chuỗi rõ ràng.

## 7. Test positive filter và negative filter

Test filter tốt phải chứng minh cả sự kiện được phép qua và sự kiện bị loại:

\`\`\`java
@Test
void filterOnlyAcceptsFailures() throws Exception {
    MBeanServer server = MBeanServerFactory.newMBeanServer();
    ObjectName name = new ObjectName(
        "com.example.test:type=WorkerEvents,name=Filter");
    WorkerEvents bean = new WorkerEvents();
    server.registerMBean(bean, name);

    java.util.List<Notification> received =
        new java.util.concurrent.CopyOnWriteArrayList<>();
    CountDownLatch failureReceived = new CountDownLatch(1);

    NotificationListener listener = (n, hb) -> {
        received.add(n);
        failureReceived.countDown();
    };

    NotificationFilter filter =
        n -> "com.example.worker.failed".equals(n.getType());

    try {
        server.addNotificationListener(name, listener, filter, null);

        server.invoke(name, "start", new Object[0], new String[0]);
        server.invoke(name, "pause", new Object[0], new String[0]);
        server.invoke(
            name,
            "fail",
            new Object[]{"E_TIMEOUT"},
            new String[]{String.class.getName()});

        assertTrue(failureReceived.await(3, TimeUnit.SECONDS));
        assertEquals(1, received.size());
        assertEquals("com.example.worker.failed",
                     received.get(0).getType());
    } finally {
        try {
            server.removeNotificationListener(name, listener);
        } finally {
            server.unregisterMBean(name);
        }
    }
}
\`\`\`

Test này phù hợp với emitter đồng bộ và một chuỗi phát đơn giản. Với dispatch bất đồng bộ hoặc concurrent producer, assertion \`received.size() == 1\` ngay sau latch của event đích có thể gặp callback đến trễ từ nguồn khác nếu implementation không xác lập thứ tự. Trong test async, nên thiết kế điểm đồng bộ hoặc đợi pipeline xử lý xong trước khi assert phủ định.

**Không dùng \`Thread.sleep(500)\` như bằng chứng tuyệt đối rằng không có sự kiện.** Nếu test cần khẳng định một event bị chặn, hãy kiểm tra filter trực tiếp và dùng cơ chế completion/barrier của emitter hoặc executor test.

## 8. Kiểm tra filter độc lập bằng unit test

NotificationFilter là thành phần có thể test riêng mà không cần MBeanServer:

\`\`\`java
@Test
void exactMatchFilterRejectsOtherTypes() {
    NotificationFilter filter =
        n -> "com.example.worker.failed".equals(n.getType());

    Notification failure =
        new Notification("com.example.worker.failed", "source", 1L);
    Notification started =
        new Notification("com.example.worker.started", "source", 2L);

    assertTrue(filter.isNotificationEnabled(failure));
    assertFalse(filter.isNotificationEnabled(started));
}
\`\`\`

Unit test lọc giúp bắt lỗi logic \`startsWith\`, null handling hoặc severity comparisons. Tuy nhiên nó chưa chứng minh MBeanServer đăng ký đúng filter; vẫn cần integration test listener để xác minh đường truyền.

### 8.1 Filter dùng userData hoặc severity

Nếu filter dựa trên \`userData\`, kiểm tra type và null:

\`\`\`java
NotificationFilter criticalOnly = n -> {
    if (n == null) {
        return false;
    }
    Object data = n.getUserData();
    if (!(data instanceof EventDetails details)) {
        return false;
    }
    return details.severity() >= 4;
};
\`\`\`

\`EventDetails\` là kiểu minh họa của ứng dụng. Với remote JMX, custom DTO phải có chiến lược serialization/classloading phù hợp; nếu không, nên dùng payload đơn giản hoặc \`CompositeData\` để tăng khả năng tương tác.

## 9. Handback: kiểm tra tham số đi kèm registration

JMX listener có signature:

\`\`\`java
void handleNotification(Notification notification, Object handback)
\`\`\`

\`handback\` là object gắn với **registration của listener**, không phải \`notification.getUserData()\`.

Ví dụ:

\`\`\`java
Object handback = "subscription-42";

NotificationListener listener = (n, hb) -> {
    assertEquals("subscription-42", hb);
};

server.addNotificationListener(name, listener, null, handback);
\`\`\`

Nếu cùng listener được đăng ký nhiều lần với filter/handback khác nhau, nó có thể nhận nhiều callback cho cùng notification theo những registration phù hợp. Vì vậy một test đếm callback cần biết có bao nhiêu registration thực sự được cài đặt.

Không nhầm handback với payload được emitter phát. Emitter cung cấp \`Notification.userData\`; bên đăng ký listener quyết định handback.

## 10. Unregister listener: kiểm thử không nhận event sau cleanup

Một test lifecycle cần chứng minh listener được gỡ đúng và không nhận notification tiếp theo.

\`\`\`java
server.addNotificationListener(name, listener, null, null);
server.invoke(name, "start", new Object[0], new String[0]);

server.removeNotificationListener(name, listener);

server.invoke(name, "pause", new Object[0], new String[0]);
\`\`\`

Với emitter đồng bộ, sau \`removeNotificationListener\` và một phát sự kiện mới, có thể assert không có callback mới. Với emitter async, có thể có callback đã được enqueue trước khi remove nhưng thực thi muộn. Vì vậy test phải phân biệt:

- Notification phát **trước** khi remove nhưng callback đến **sau**.
- Notification phát **sau** remove.
- Listener được đăng ký nhiều lần với filter/handback khác nhau.
- Client remote đã mất kết nối và subscription không còn.

Một chiến lược test deterministic là dùng executor đồng bộ trong fixture, hoặc một \`CountDownLatch\`/barrier cho queue event trước khi tiến hành remove. Nếu mục tiêu là chặn event sau remove, hãy phát một event có sequence riêng sau khi chắc chắn remove đã xong.

### 10.1 Remove overload cần đúng registration

\`NotificationEmitter\` hỗ trợ remove với listener/filter/handback cụ thể:

\`\`\`java
removeNotificationListener(listener, filter, handback);
\`\`\`

Với \`MBeanServer.removeNotificationListener\` cũng có các overload tương ứng. Khi cùng listener được đăng ký nhiều lần, dùng đúng overload và object identity/registration details để tránh remove nhầm hoặc bỏ sót.

## 11. Test notification metadata trên MBeanInfo

Một MBean có thể khai báo types phát qua \`MBeanNotificationInfo\`. Kiểm tra metadata:

\`\`\`java
MBeanInfo info = server.getMBeanInfo(name);

MBeanNotificationInfo[] notificationInfos =
    info.getNotifications();

boolean supportsFailed = java.util.Arrays.stream(notificationInfos)
    .flatMap(i -> java.util.Arrays.stream(i.getNotifTypes()))
    .anyMatch(type -> type.equals("com.example.worker.failed"));

assertTrue(supportsFailed);
\`\`\`

Đây là kiểm tra metadata được công bố, không chứng minh event đã được phát. Một test đầy đủ nên kết hợp metadata test với callback test. Nếu metadata khai báo type nhưng emitter không bao giờ gửi, test thực thi mới phát hiện.

Ngược lại, nếu emitter phát một type không được ghi trong metadata, client vẫn có thể thấy event ở một số cơ chế nhưng monitoring contract trở nên khó hiểu. Hãy giữ metadata đồng bộ với sự kiện thực tế.

## 12. Kiểm thử thứ tự, sequence number và timestamp

Mỗi \`Notification\` có sequence number do emitter định nghĩa. Trong mẫu dùng \`AtomicLong.incrementAndGet()\`, sequence tăng theo thứ tự cấp số:

\`\`\`java
assertTrue(second.getSequenceNumber() >
           first.getSequenceNumber());
\`\`\`

Nhưng khi có nhiều producer threads, thứ tự gọi \`sendNotification\` có thể khác thứ tự cấp sequence number. Khi dùng executor bất đồng bộ, thứ tự callback có thể khác thứ tự emission nếu executor không bảo đảm FIFO hoặc có nhiều worker.

Cần định nghĩa contract:
- Sequence tăng đơn điệu theo một emitter, hay theo từng type?
- Có thể có gap khi filter loại event không?
- Client có cần sắp xếp/khử trùng lặp không?
- Một notification có được retry hay gửi lại sau reconnect không?
- Timestamp là thời điểm phát, tạo notification hay thời điểm sự kiện nghiệp vụ xảy ra?

Với filter chỉ nhận \`failed\`, sequence number có thể nhảy từ 10 đến 13 vì các event khác bị lọc. **Không assert sequence liên tiếp** ở listener đã được filter nếu emitter phát các type khác xen kẽ.

## 13. Concurrency: test nhiều notification cùng lúc

Một emitter có thể phát trên nhiều luồng:

\`\`\`java
ExecutorService pool = Executors.newFixedThreadPool(4);

try {
    for (int i = 0; i < 20; i++) {
        pool.submit(bean::start);
    }
} finally {
    pool.shutdown();
    assertTrue(pool.awaitTermination(5, TimeUnit.SECONDS));
}
\`\`\`

Nếu test dùng \`ArrayList\` thường trong listener được gọi từ nhiều thread, có thể xảy ra race. Dùng \`CopyOnWriteArrayList\`, \`ConcurrentLinkedQueue\` hoặc đồng bộ rõ ràng. Có thể dùng latch đếm 20 callback, sau đó assert số lượng, type và tập sequence không trùng.

Tuy nhiên nếu listener dispatch bất đồng bộ bằng executor riêng, chỉ chờ pool phát sự kiện kết thúc chưa chắc callback đã xong. Cần một latch trên listener hoặc barrier của dispatcher. Không giả định mọi \`NotificationBroadcasterSupport\` luôn phát callback trên cùng thread: constructor có thể nhận executor, và implementer khác có behavior khác.

## 14. Test callback lỗi và isolation

Listener có thể ném runtime exception:

\`\`\`java
NotificationListener failing = (n, hb) -> {
    throw new IllegalStateException("simulated listener failure");
};
\`\`\`

Khi kiểm thử, cần hiểu semantics của broadcaster/dispatcher đang sử dụng. Không mặc định một listener lỗi sẽ khiến mọi listener khác mất notification hoặc khiến method phát exception; behavior cụ thể phụ thuộc implementation và executor.

Một test có thể:
- Đăng ký failing listener và healthy listener.
- Phát notification.
- Xem healthy listener có được gọi theo contract kỳ vọng không.
- Kiểm tra lỗi được ghi log/rate-limited thay vì làm crash domain processing.
- Bảo đảm cleanup cả hai listener.

Đây là test resilience quan trọng nếu notification được dùng cho monitoring, nhưng đừng dựa vào notification như một message queue có durability và acknowledgment. JMX notifications thường không cung cấp durable delivery hay exactly-once semantics.

## 15. Spring Framework: exporter và listener bean

Spring hỗ trợ cấu hình listener trong hệ sinh thái JMX, ví dụ \`NotificationListenerBean\` kết hợp với \`MBeanExporter\`. Một mô hình cấu hình có thể tổ chức như sau:

\`\`\`text
Spring ApplicationContext
  ├── WorkerEvents (MBean)
  ├── MBeanExporter
  │    └── export WorkerEvents → ObjectName
  └── NotificationListenerBean
       ├── listener
       ├── notificationFilter
       ├── handback
       └── mappedObjectNames
\`\`\`

Khi exporter quản lý cả registration và listener, cần đảm bảo listener được add sau khi MBean có thể nhận notification và được remove khi context đóng. Trong integration test, xác minh bằng cách tạo context với fixture nhỏ và quan sát callback thay vì chỉ assert bean tồn tại.

Ví dụ Java configuration theo ý tưởng:

\`\`\`java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.NotificationListenerBean;

@Configuration
public class NotificationJmxConfiguration {

    @Bean
    public WorkerEvents workerEvents() {
        return new WorkerEvents();
    }

    @Bean
    public NotificationListenerBean workerListenerBean(
            NotificationListener listener) {
        NotificationListenerBean bean =
            new NotificationListenerBean();
        bean.setNotificationListener(listener);
        bean.setMappedObjectNames(
            "com.example.test:type=WorkerEvents,name=Spring");
        return bean;
    }

    @Bean
    public MBeanExporter exporter(
            WorkerEvents workerEvents,
            NotificationListenerBean workerListenerBean) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setBeans(java.util.Map.of(
            "com.example.test:type=WorkerEvents,name=Spring",
            workerEvents));
        exporter.setNotificationListeners(workerListenerBean);
        return exporter;
    }
}
\`\`\`

Đoạn ví dụ cần imports và bean \`NotificationListener\` cụ thể, cũng như MBeanServer được chọn trong fixture. API setter/constructor phải được đối chiếu với phiên bản Spring đang dùng. \`NotificationListenerBean\` có thể hỗ trợ mapping/handback/filter tương ứng; test nên chứng minh listener đã được gắn vào đúng ObjectName thay vì chỉ tin cấu hình.

### 15.1 Chọn đúng server trong test

Nếu exporter dùng platform MBeanServer, test phải truy vấn platform server. Nếu exporter dùng server riêng, inject server đó và tránh \`ManagementFactory.getPlatformMBeanServer()\` trong assertion. Một listener được cấu hình đúng nhưng gắn vào MBeanServer khác vẫn không nhận event như mong muốn.

## 16. Test Spring annotation notification metadata

Spring JMX có \`@ManagedNotification\` và \`@ManagedNotifications\` để mô tả notification types trong metadata của MBean được annotation-driven export.

Ví dụ định hướng:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedNotification;
import org.springframework.jmx.export.annotation.ManagedNotifications;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.ops:type=WorkerEvents,name=Import")
@ManagedNotifications({
    @ManagedNotification(
        name = "com.example.worker.completed",
        description = "Worker completed a batch",
        notificationTypes = {
            "com.example.worker.completed"
        })
})
public class AnnotatedWorkerEvents {
    // Emitter/notification publisher implementation.
}
\`\`\`

Tùy Spring Framework version, thuộc tính và vị trí annotation cần theo API tương ứng. Metadata annotation **không tự phát notification**: class cần sử dụng cơ chế publisher/emitter hợp lệ. Test phải tách:
1. Annotation metadata được export thành \`MBeanNotificationInfo\`.
2. Actual notification được phát bởi source.
3. Listener/filter thực sự nhận hoặc loại event.

Không dùng annotation như thay thế cho emitter behavior.

## 17. Remote JMX notification: khác local test ở đâu?

Với remote connector, callback đến client qua connector transport và có thêm lỗi mạng. Các điểm khác:

| Vấn đề | Local MBeanServer | Remote connector |
|---|---|---|
| Latency | Thường thấp | Network và transport delay |
| Serialization | Ít ràng buộc hơn | Payload cần tương thích classloading |
| Disconnection | Không có network failure | Có thể mất subscription/connection |
| Ordering | Theo emitter/dispatcher | Còn phụ thuộc transport và buffering |
| Timeout | Chủ yếu thread scheduling | Network, reconnect và client polling |
| Cleanup | Remove listener trực tiếp | Remove có thể thất bại nếu mất kết nối |
| Security | Boundary trong JVM | Authentication, TLS, authorization |

Không nên viết một test chỉ chạy local rồi tuyên bố remote notifications an toàn, ổn định và không mất event. Với remote JMX, cần integration test qua \`JMXConnectorServer\` được khởi động trong fixture riêng, security credentials/trust khi áp dụng, và có cleanup connector/registry.

### 17.1 Lost connection không đồng nghĩa event được replay

JMX notifications không phải message queue có lưu bền vững mặc định. Nếu client mất kết nối, có thể không nhận được event phát trong khoảng mất kết nối. Khi cần trạng thái đáng tin cậy, client nên kết hợp notification với **đọc lại current state** hoặc metrics và idempotent reconciliation sau reconnect.

Notification thích hợp cho tín hiệu và cập nhật gần thời gian thực, không nên là nguồn chứng thực duy nhất cho workflow nghiệp vụ không được phép mất dữ liệu.

## 18. Test callback được remove khi context đóng

Một lỗi lâu dài là listener vẫn còn tham chiếu đến Spring bean đã bị destroy hoặc test fixture đã kết thúc:

\`\`\`text
Context A:
  listener A registered
  context.close()
  listener A remains
     |
     v
Old bean retained / callback to destroyed component
\`\`\`

Integration test nên:
1. Start Spring context và đăng ký MBean/listener.
2. Phát event, assert listener nhận.
3. Close context.
4. Phát event từ nguồn còn sống nếu fixture cho phép.
5. Xác minh listener của context A không được gọi nữa, đồng thời MBean của context khác không bị gỡ nhầm.

Với một MBean cũng bị unregister khi context đóng, muốn kiểm chứng listener cleanup riêng có thể dùng emitter thuộc fixture/shared owner sống lâu hơn. Không cố invoke MBean đã unregister và diễn giải \`InstanceNotFoundException\` thành “listener được remove đúng”.

## 19. Test negative filter có cơ chế đồng bộ rõ

Một negative test thất bại kiểu flakiness:

\`\`\`java
emit("started");
Thread.sleep(100);
assertEquals(0, calls.get());
\`\`\`

Nó có thể PASS dù event đang nằm trong queue, rồi callback đến sau assertion. Thay vào đó, có thể:

- Test \`NotificationFilter.isNotificationEnabled\` trực tiếp.
- Dùng executor đồng bộ trong fixture để callback hoàn tất trước khi \`emit\` trả về.
- Sử dụng barrier/ack của dispatcher test.
- Phát một sentinel event được filter chấp nhận sau event bị từ chối, rồi chờ sentinel; chỉ kết luận ordering khi dispatcher bảo đảm FIFO.
- Đối với remote async, dùng deadline đủ rõ và state reconciliation, không khẳng định vắng mặt tuyệt đối dựa trên sleep.

Ví dụ fixture \`NotificationBroadcasterSupport\` không truyền executor bất đồng bộ có behavior dispatch trực tiếp theo implementation. Khi test được thiết kế chỉ dùng một thread và không có producer khác, có thể assert ngay sau lời gọi phát event. Với executor tự tạo, test phải kiểm soát chính executor.

## 20. Đo lường và chống listener leak

Những tín hiệu nên theo dõi trong test/staging:

- Số listener registrations theo MBean.
- Số callback nhận được cho mỗi type.
- Tỉ lệ notification bị filter loại.
- Thời gian từ emit đến receive.
- Tần suất duplicate callback.
- Callback exception count.
- Số notification không được consumer xử lý kịp.
- Số kết nối remote đang mở.
- Số listener còn lại sau shutdown/redeploy.

Không phải mọi MBean có sẵn API trực tiếp để đếm listener. Có thể thêm instrumentation trong emitter/registration wrapper của ứng dụng hoặc test bằng hệ quả callback. Tránh công bố số liệu chỉ để test nếu làm tăng bề mặt quản trị không cần thiết.

## 21. Quy trình test tổng hợp

### Trước test

1. Chọn ObjectName riêng và MBeanServer test cô lập.
2. Xác định contract type/source/payload/sequence.
3. Tạo emitter có behavior deterministic.
4. Định nghĩa filter và handback.
5. Chuẩn bị latch hoặc controlled executor.
6. Xác định ai sở hữu MBean và listener registration.

### Trong test

1. Register MBean.
2. Add listener/filter.
3. Emit event được phép và event bị loại.
4. Await callback có timeout.
5. Assert type, payload, handback và metadata.
6. Kiểm tra negative case bằng cơ chế đồng bộ thích hợp.
7. Nếu test concurrency, dùng thread-safe collection và assert số sự kiện nhận.

### Sau test

1. Remove listener chính xác theo registration.
2. Unregister MBean nếu fixture sở hữu.
3. Shutdown executor/connector do fixture tạo.
4. Xác minh không có event đến callback của fixture đã đóng.
5. Không xóa MBean của test khác chỉ vì ObjectName nằm cùng domain.

## 22. Lỗi thường gặp

**“Filter enableType là so khớp exact.”** Không. \`NotificationFilterSupport\` so khớp theo prefix. Dùng filter custom nếu cần exact type.

**“Listener không nhận có nghĩa emitter không phát.”** Chưa chắc; có thể filter loại, chưa đăng ký, sai server hoặc callback đến trễ.

**“Sleep vài trăm ms đủ để chứng minh không có callback.”** Không chắc với async/remote dispatch.

**“Handback là userData.”** Không. Handback thuộc registration; userData thuộc notification event.

**“Sequence number luôn liên tiếp tại một filtered listener.”** Không. Event bị lọc vẫn có sequence và khiến số nhận được có gap.

**“MBeanInfo có type nghĩa là notification đã phát.”** Không. Metadata mô tả khả năng; test callback chứng minh hành vi.

**“Remove listener xong không bao giờ có callback đến trễ.”** Không được bảo đảm trong mọi async dispatcher; callback đã queue trước đó có thể vẫn chạy.

**“Spring annotation tự gửi notification.”** Không. Metadata và emitter behavior là hai việc khác nhau.

**“Remote notification được replay sau reconnect.”** Không mặc định; nên reconcile state sau reconnect.

## 23. Bài tập vận dụng

**Bài 1 — Positive/negative filter.** Tạo listener chỉ nhận \`com.example.worker.failed\`; emit started, paused, failed. Assert đúng một failure event đến listener. Viết thêm unit test filter.

**Bài 2 — Handback.** Đăng ký cùng một listener hai lần với handback khác nhau và filter khác nhau. Nêu khi nào callback có thể chạy hai lần và cách remove từng registration.

**Bài 3 — Sequence.** Emitter phát sequence 1:started, 2:failed, 3:paused, 4:failed. Filter chỉ nhận failed. Có nên assert sequence [1,2] ở listener? Không; cần nhận [2,4] theo sequence emitter.

**Bài 4 — Async race.** Một negative test dùng \`Thread.sleep(50)\`. Hãy thiết kế lại bằng controlled executor hoặc barrier, giải thích tại sao fixed sleep gây flakiness.

**Bài 5 — Spring context lifecycle.** Listener được đăng ký qua exporter rồi context đóng. Thiết kế test chứng minh listener không bị leak mà không unregister MBean thuộc context khác.

**Bài 6 — Remote reconnect.** Client mất kết nối khi worker phát paused event. Vì sao không nên coi notification là durable record? Hãy đề xuất cách đọc effective state sau reconnect.

## Tổng kết

Kiểm thử notification listener và filter trong Spring Framework JMX cần xác minh **contract sự kiện** và **cơ chế phân phối**: listener registration, notification types, filter acceptance/rejection, handback, metadata, payload, sequence và lifecycle. Dùng \`CountDownLatch\`, controlled executor và test server riêng để tránh phụ thuộc vào timing ngẫu nhiên. Phân biệt rõ unit test filter với integration test qua MBeanServer; với remote connector, kiểm tra thêm transport, serialization, reconnect và security. Cuối cùng, luôn dọn listener/MBean đúng ownership để test độc lập, không tạo callback leak hoặc xung đột trong Spring ApplicationContext.
