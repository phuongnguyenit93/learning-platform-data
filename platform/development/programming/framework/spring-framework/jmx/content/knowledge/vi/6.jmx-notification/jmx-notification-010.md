# Kiểm thử JMX notification bằng listener quan sát được

## 1. Mục tiêu

Trong JMX, MBean có thể phát **notification** để báo một sự kiện quản trị: tác vụ hoàn tất, ngưỡng sử dụng vượt giới hạn, cấu hình đã được nạp lại hoặc trạng thái worker thay đổi. Khác với việc đọc attribute (pull), notification là tín hiệu được **đẩy tới các listener đã đăng ký**.

Kiểm thử notification chỉ bằng log hoặc chờ một công cụ giao diện như JConsole thường khó tự động hóa. Một thiết kế tốt dùng **listener quan sát được**: test đăng ký \`NotificationListener\`, lưu lại thông báo nhận được trong một collection có kiểm soát, kích hoạt sự kiện, rồi khẳng định nội dung và số lượng notification. Điều này kiểm tra hành vi thực sự mà client JMX có thể thấy.

Mục tiêu cụ thể:

- Xác minh notification được phát khi đúng sự kiện xảy ra.
- Xác minh \`type\`, \`source\`, \`sequenceNumber\`, \`timeStamp\`, \`message\` và \`userData\` theo hợp đồng.
- Xác minh listener chỉ nhận những loại thông báo mà nó đăng ký và bộ lọc cho phép.
- Không phụ thuộc \`Thread.sleep()\` hoặc thứ tự bất định của môi trường.
- Đăng ký và gỡ listener đúng vòng đời để test độc lập, không rò tài nguyên.
- Phân biệt kiểm thử logic phát notification trực tiếp với kiểm thử đường đi qua \`MBeanServer\` và Spring.

## 2. Luồng notification trong JMX

\`\`\`text
Application event / state change
              |
       NotificationBroadcaster
        (MBean implementation)
              |
         sendNotification
              |
          MBeanServer
              |
    NotificationListener
              |
   Recorded notification queue
              |
       Assertion in test
\`\`\`

JMX chuẩn cung cấp:

- \`javax.management.Notification\`: đối tượng thông báo chứa metadata.
- \`javax.management.NotificationListener\`: callback \`handleNotification(Notification, Object)\`.
- \`javax.management.NotificationFilter\`: quyết định notification nào được chuyển đến listener.
- \`javax.management.NotificationBroadcasterSupport\`: base class tiện dụng để gửi notification và quản lý listener.
- \`javax.management.MBeanServer.addNotificationListener(...)\` và \`removeNotificationListener(...)\`: API phía client của một MBean đã đăng ký.

Khi phát notification qua một MBean, interface quản trị của MBean có thể công bố các loại notification mà nó hỗ trợ qua \`MBeanNotificationInfo\`. Đây là metadata cho công cụ quản trị, không tự phát notification.

## 3. MBean mẫu phát notification

Ví dụ một worker có thao tác chuyển trạng thái và phát notification sau khi trạng thái thay đổi. Chúng ta xây dựng **Standard MBean** với interface chỉ mô tả hành vi quản trị.

\`\`\`java
package com.example.jmx;

public interface WorkerControlMBean {
    boolean isPaused();
    void pause();
    void resume();
}
\`\`\`

Lớp triển khai kế thừa \`NotificationBroadcasterSupport\` và dùng \`AtomicLong\` để tạo số thứ tự:

\`\`\`java
package com.example.jmx;

import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;
import javax.management.MBeanNotificationInfo;
import javax.management.Notification;
import javax.management.NotificationBroadcasterSupport;

public final class WorkerControl
        extends NotificationBroadcasterSupport
        implements WorkerControlMBean {

    public static final String PAUSED = "com.example.worker.paused";
    public static final String RESUMED = "com.example.worker.resumed";

    private final AtomicBoolean paused = new AtomicBoolean(false);
    private final AtomicLong sequence = new AtomicLong();

    @Override
    public boolean isPaused() {
        return paused.get();
    }

    @Override
    public void pause() {
        if (paused.compareAndSet(false, true)) {
            publish(PAUSED, "Worker paused");
        }
    }

    @Override
    public void resume() {
        if (paused.compareAndSet(true, false)) {
            publish(RESUMED, "Worker resumed");
        }
    }

    private void publish(String type, String message) {
        Notification notification = new Notification(
            type,
            this,
            sequence.incrementAndGet(),
            System.currentTimeMillis(),
            message
        );
        notification.setUserData("operations");
        sendNotification(notification);
    }

    @Override
    public MBeanNotificationInfo[] getNotificationInfo() {
        String[] types = { PAUSED, RESUMED };
        return new MBeanNotificationInfo[] {
            new MBeanNotificationInfo(
                types,
                Notification.class.getName(),
                "Worker state changed"
            )
        };
    }
}
\`\`\`

Một lời gọi \`pause()\` khi worker đã pause không phát thêm notification, vì trạng thái không thay đổi. Đây là một **hợp đồng hữu ích để test**: notification chỉ xuất hiện khi chuyển trạng thái thực sự.

Trong production, cần phân biệt “đã nhận yêu cầu pause” với “worker đã ngừng lấy công việc mới”. Nếu thao tác bất đồng bộ, notification nên gắn với sự kiện hoàn tất của ứng dụng, không giả định \`pause()\` đồng bộ đã dừng toàn bộ worker.

## 4. Listener quan sát được đơn giản

Một \`NotificationListener\` có thể ghi nhận mọi notification vào \`CopyOnWriteArrayList\` khi số lượng sự kiện nhỏ:

\`\`\`java
package com.example.jmx;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import javax.management.Notification;
import javax.management.NotificationListener;

public final class RecordingListener implements NotificationListener {
    private final CopyOnWriteArrayList<Notification> recorded =
        new CopyOnWriteArrayList<>();

    @Override
    public void handleNotification(
            Notification notification,
            Object handback) {
        recorded.add(notification);
    }

    public List<Notification> snapshot() {
        return List.copyOf(recorded);
    }

    public void clear() {
        recorded.clear();
    }
}
\`\`\`

Ưu điểm: callback viết đơn giản, test có thể lấy immutable snapshot để assert, và việc ghi nhận an toàn trước callback từ thread khác. Nhược điểm: \`CopyOnWriteArrayList\` sao chép dữ liệu ở mỗi lần ghi, không phù hợp khi luồng notification rất lớn. Với test tải lớn, dùng \`BlockingQueue\` hoặc một cấu trúc đồng thời khác.

**Không assert trực tiếp vào \`System.out\`/log**. Log là dấu vết phụ, có thể phụ thuộc cấu hình và định dạng; chính notification object mới là hợp đồng mà người tiêu thụ JMX nhìn thấy.

## 5. Unit test: quan sát trực tiếp broadcaster

Test này đăng ký listener ngay lên \`WorkerControl\` mà không cần Spring hay \`MBeanServer\`:

\`\`\`java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import javax.management.Notification;

class WorkerControlUnitTest {
    @Test
    void sendsOneNotificationForEachRealTransition() {
        WorkerControl worker = new WorkerControl();
        RecordingListener listener = new RecordingListener();

        worker.addNotificationListener(listener, null, null);
        try {
            worker.pause();
            worker.pause();  // không thay đổi trạng thái
            worker.resume();

            var notifications = listener.snapshot();
            assertEquals(2, notifications.size());

            Notification first = notifications.get(0);
            Notification second = notifications.get(1);

            assertEquals(WorkerControl.PAUSED, first.getType());
            assertEquals(WorkerControl.RESUMED, second.getType());
            assertEquals("Worker paused", first.getMessage());
            assertEquals("Worker resumed", second.getMessage());
            assertEquals(1, first.getSequenceNumber());
            assertEquals(2, second.getSequenceNumber());
            assertTrue(second.getTimeStamp() >= first.getTimeStamp());
            assertEquals("operations", first.getUserData());
        } finally {
            try {
                worker.removeNotificationListener(listener);
            } catch (javax.management.ListenerNotFoundException ignored) {
                // Listener đã được gỡ ở nơi khác.
            }
        }
    }
}
\`\`\`

Với \`NotificationBroadcasterSupport\` dùng executor mặc định, callback thường được thực thi trực tiếp trong lời gọi \`sendNotification\`; vì vậy ví dụ unit test trên có thể assert ngay sau \`pause()\` và \`resume()\`. Nếu dùng executor bất đồng bộ hoặc đường đi remote, test phải chờ trên một tín hiệu đồng bộ có timeout, không giả định callback đã chạy trước khi lời gọi điều khiển trả về.

## 6. Integration test: đăng ký listener thông qua MBeanServer

Unit test broadcaster là chưa đủ để khẳng định client JMX nhận được notification khi MBean được đăng ký. Kiểm thử tích hợp cần dùng chính API của \`MBeanServer\`:

\`\`\`java
import static org.junit.jupiter.api.Assertions.*;
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.Notification;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;

class WorkerControlMBeanTest {
    @Test
    void notificationIsVisibleThroughMBeanServer() throws Exception {
        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
            "com.example.test:type=Worker,name=NotificationTest"
        );

        WorkerControl worker = new WorkerControl();
        RecordingListener listener = new RecordingListener();

        server.registerMBean(worker, name);
        try {
            server.addNotificationListener(name, listener, null, null);
            try {
                server.invoke(name, "pause", new Object[0], new String[0]);

                var received = listener.snapshot();
                assertEquals(1, received.size());
                Notification event = received.get(0);

                assertEquals(WorkerControl.PAUSED, event.getType());
                assertEquals("Worker paused", event.getMessage());
                assertEquals(1, event.getSequenceNumber());
                assertTrue(event.getTimeStamp() > 0);
            } finally {
                server.removeNotificationListener(name, listener);
            }
        } finally {
            server.unregisterMBean(name);
        }
    }
}
\`\`\`

Trong bộ test chạy song song, hãy sử dụng \`ObjectName\` duy nhất theo từng ca test, ví dụ thêm UUID vào property \`name\` sau khi quote; tránh va chạm với MBean của test khác trên platform server.

Đăng ký listener bằng \`server.addNotificationListener(name, ...)\` kiểm tra được đường đi qua server, metadata của MBean và cách client thực tế dùng JMX. Nếu MBean không hỗ trợ notification, server sẽ báo lỗi phù hợp thay vì silently bỏ qua.

## 7. Kiểm thử bất đồng bộ với BlockingQueue và timeout

Trong môi trường bất đồng bộ, callback có thể xảy ra sau thời điểm lời gọi kết thúc. Dùng \`BlockingQueue\` để test chờ một notification trong thời gian hữu hạn:

\`\`\`java
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;
import javax.management.Notification;
import javax.management.NotificationListener;

public final class QueueingNotificationListener
        implements NotificationListener {

    private final BlockingQueue<Notification> events =
        new LinkedBlockingQueue<>();

    @Override
    public void handleNotification(
            Notification notification,
            Object handback) {
        events.add(notification);
    }

    public Notification awaitNext(long timeout, TimeUnit unit)
            throws InterruptedException {
        return events.poll(timeout, unit);
    }
}
\`\`\`

Test:

\`\`\`java
@Test
void asynchronouslyDeliveredNotificationCanBeObserved()
        throws Exception {
    WorkerControl worker = new WorkerControl();
    QueueingNotificationListener listener =
        new QueueingNotificationListener();

    worker.addNotificationListener(listener, null, null);
    try {
        worker.pause();

        Notification event = listener.awaitNext(2, TimeUnit.SECONDS);
        assertNotNull(event, "Expected paused notification");
        assertEquals(WorkerControl.PAUSED, event.getType());
    } finally {
        worker.removeNotificationListener(listener);
    }
}
\`\`\`

Ở ví dụ này callback mặc định có thể đồng bộ, nhưng listener loại queue vẫn dùng được khi đổi sang executor bất đồng bộ. Giá trị timeout là giới hạn tránh treo test, không phải yêu cầu ngủ đủ số giây. Với test hệ thống, chọn timeout dựa trên môi trường CI và đặc điểm của luồng phát sự kiện.

**Không thay chờ có điều kiện bằng \`Thread.sleep(1000)\`** rồi hy vọng notification đã tới; sleep gây test chậm và đôi khi vẫn thất bại khi máy tải cao.

## 8. Kiểm tra NotificationFilter và handback

Listener có thể đăng ký một \`NotificationFilter\` để chỉ nhận một số type. \`handback\` là object được chuyển nguyên vẹn tới callback để client nhận biết ngữ cảnh đăng ký.

\`\`\`java
import javax.management.NotificationFilterSupport;
import javax.management.NotificationListener;

NotificationFilterSupport onlyPaused =
    new NotificationFilterSupport();
onlyPaused.enableType(WorkerControl.PAUSED);

RecordingListener pausedListener = new RecordingListener();

worker.addNotificationListener(
    pausedListener,
    onlyPaused,
    "expected-context"
);
\`\`\`

Nếu muốn assert cả handback, tạo listener ghi nhận một cấu trúc gồm cả hai:

\`\`\`java
record ReceivedNotification(
    javax.management.Notification notification,
    Object handback
) {}

class CapturingListener implements javax.management.NotificationListener {
    final java.util.concurrent.BlockingQueue<ReceivedNotification> queue =
        new java.util.concurrent.LinkedBlockingQueue<>();

    @Override
    public void handleNotification(
            javax.management.Notification event,
            Object handback) {
        queue.add(new ReceivedNotification(event, handback));
    }
}
\`\`\`

Kiểm thử:

\`\`\`java
CapturingListener capturing = new CapturingListener();
worker.addNotificationListener(
    capturing, onlyPaused, "monitor-A"
);

try {
    worker.pause();
    worker.resume();

    var actual = capturing.queue.poll(
        2, java.util.concurrent.TimeUnit.SECONDS
    );

    assertNotNull(actual);
    assertEquals(WorkerControl.PAUSED, actual.notification().getType());
    assertEquals("monitor-A", actual.handback());
    assertNull(capturing.queue.poll());
} finally {
    worker.removeNotificationListener(capturing);
}
\`\`\`

Khi dùng \`NotificationFilterSupport.enableType("com.example.worker")\`, hãy nhớ filter này so sánh prefix của type; với một loại cụ thể, tên type phải được thiết kế sao cho prefix không vô tình nhận các type không mong muốn. Nếu cần đối sánh chính xác, dùng \`NotificationFilter\` tự viết:

\`\`\`java
javax.management.NotificationFilter exactPaused =
    n -> WorkerControl.PAUSED.equals(n.getType());
\`\`\`

## 9. Xác minh metadata về loại notification

Ngoài dữ liệu nhận được, MBean nên khai báo loại notification trong \`MBeanNotificationInfo\` để client có thể introspect:

\`\`\`java
import javax.management.MBeanInfo;
import javax.management.MBeanNotificationInfo;

MBeanInfo info = server.getMBeanInfo(name);
MBeanNotificationInfo[] declared = info.getNotifications();

boolean pausedDeclared = java.util.Arrays.stream(declared)
    .flatMap(x -> java.util.Arrays.stream(x.getNotifTypes()))
    .anyMatch(WorkerControl.PAUSED::equals);

org.junit.jupiter.api.Assertions.assertTrue(pausedDeclared);
\`\`\`

Kiểm tra metadata **không thay thế** việc kích hoạt sự kiện và assert listener. Metadata có thể đúng trong khi mã không bao giờ gọi \`sendNotification\`; ngược lại, notification có thể được phát nhưng metadata thiếu hoặc sai. Hai kiểm tra xác nhận hai khía cạnh khác nhau của hợp đồng.

## 10. Đặt sequence number và timestamp có ý nghĩa

\`Notification.sequenceNumber\` giúp client quan sát thứ tự phát sự kiện của một broadcaster. Một \`AtomicLong\` là cách thường dùng để cấp số tăng dần trong một instance:

\`\`\`java
long next = sequence.incrementAndGet();
Notification event = new Notification(
    TYPE, source, next, System.currentTimeMillis(), message
);
\`\`\`

Khi test, nên khẳng định số thứ tự **tăng** theo thứ tự phát, thay vì cố định \`1,2,3\` nếu broadcaster được dùng chung giữa nhiều test hoặc có sự kiện nền. Với instance mới và đường đi hoàn toàn kiểm soát, \`1,2\` là hợp lý.

\`timestamp\` nên dương và nằm trong khoảng hợp lý. Tránh assert bằng tuyệt đối \`System.currentTimeMillis()\` vì thời gian thay đổi giữa lúc phát và lúc test kiểm tra; dùng \`before <= timestamp <= after\` với biên phù hợp khi cần.

\`source\` trong notification phải phản ánh nguồn mà client nhận diện. Trong integration test, đường đi \`MBeanServer\` có thể chuẩn hóa \`source\` theo \`ObjectName\` tùy cơ chế broadcaster/MBean server; hãy định nghĩa kỳ vọng theo hợp đồng client thực sự sử dụng thay vì kiểm tra đồng nhất object Java một cách máy móc.

## 11. Spring Framework và notification

Trong Spring JMX, bean được export qua \`MBeanExporter\`. Spring hỗ trợ gửi JMX notification từ bean được quản lý thông qua các cơ chế như \`NotificationPublisherAware\`, để code không phải trực tiếp nắm \`MBeanServer\`. Ví dụ:

\`\`\`java
import javax.management.Notification;
import org.springframework.jmx.export.notification.NotificationPublisher;
import org.springframework.jmx.export.notification.NotificationPublisherAware;

public class JobMonitor implements NotificationPublisherAware {
    private volatile NotificationPublisher publisher;

    @Override
    public void setNotificationPublisher(
            NotificationPublisher publisher) {
        this.publisher = publisher;
    }

    public void jobFinished(String jobId) {
        NotificationPublisher current = publisher;
        if (current == null) {
            throw new IllegalStateException(
                "JMX notification publisher not initialized"
            );
        }

        Notification n = new Notification(
            "com.example.job.finished",
            this,
            System.nanoTime(),
            "Job finished"
        );
        n.setUserData(jobId);
        current.sendNotification(n);
    }
}
\`\`\`

Đây là hình thức thích hợp khi Spring quản lý và export bean. Cần cung cấp metadata notification thích hợp để các công cụ JMX introspect được types, đồng thời bảo đảm test context đã khởi tạo exporter/publisher trước khi kích hoạt \`jobFinished\`. Việc chọn số sequence bằng \`System.nanoTime()\` ở ví dụ trên chỉ minh họa nguồn tăng theo thời gian, không đảm bảo sequence liên tiếp giữa các sự kiện; production nên dùng counter \`AtomicLong\` của broadcaster.

**Giữ domain độc lập JMX:** Trong hệ thống có layering, domain phát event ứng dụng như \`JobFinished\`; một adapter/infrastructure component nhận event và gọi \`NotificationPublisher\`. Như vậy domain không phụ thuộc \`NotificationPublisherAware\` hay \`javax.management.Notification\`.

## 12. Ví dụ unit test adapter Spring với publisher giả

Khi muốn kiểm tra adapter tạo notification đúng payload, có thể inject publisher bằng \`setNotificationPublisher\` như một dependency giả:

\`\`\`java
import static org.junit.jupiter.api.Assertions.*;
import java.util.ArrayList;
import java.util.List;
import javax.management.Notification;
import org.junit.jupiter.api.Test;

class JobMonitorTest {
    @Test
    void publishesFinishedEventWithJobId() {
        JobMonitor monitor = new JobMonitor();
        List<Notification> recorded = new ArrayList<>();

        monitor.setNotificationPublisher(recorded::add);
        monitor.jobFinished("job-42");

        assertEquals(1, recorded.size());
        Notification actual = recorded.get(0);
        assertEquals("com.example.job.finished", actual.getType());
        assertEquals("job-42", actual.getUserData());
    }
}
\`\`\`

Test này xác minh chính xác object mà adapter gửi tới publisher, không cần cấu hình JMX network. Tuy nhiên nó **không xác minh** exporter đã đăng ký notification cho client JMX, nên integration test với \`MBeanServer.addNotificationListener\` vẫn có giá trị ở mức tích hợp.

## 13. Test khi không được gửi notification

Ngoài các đường thành công, test các điều kiện âm:

- Không chuyển trạng thái thì không phát thông báo trùng lặp.
- Sự kiện không hợp lệ bị chặn trước khi publish.
- Filter bỏ notification không khớp type.
- Listener đã remove không nhận thêm thông báo.
- Lệnh bất đồng bộ bị từ chối vì worker đang bận thì không phát tín hiệu “hoàn tất” giả.
- Nếu một listener ném ngoại lệ, thiết kế phải có hành vi rõ ràng với listener khác và luồng xử lý ứng dụng.

Ví dụ unregister listener:

\`\`\`java
WorkerControl worker = new WorkerControl();
RecordingListener listener = new RecordingListener();

worker.addNotificationListener(listener, null, null);
worker.pause();
int countBefore = listener.snapshot().size();

worker.removeNotificationListener(listener);
worker.resume();

org.junit.jupiter.api.Assertions.assertEquals(
    countBefore, listener.snapshot().size()
);
\`\`\`

Với phân phối bất đồng bộ, cần xử lý khả năng một notification đã được xếp hàng trước thời điểm remove nhưng callback hoàn thành sau đó. Test nên xác định ranh giới thời gian và cơ chế executor để không diễn giải nhầm race condition là lỗi nghiệp vụ.

## 14. Những nguyên nhân phổ biến khiến test notification thất bại

| Hiện tượng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| Không có notification | Listener gắn vào nhầm MBean hoặc chưa đăng ký | Kiểm tra \`ObjectName\`, \`isRegistered\` và thời điểm attach |
| Test lúc pass lúc fail | Callback bất đồng bộ, dùng sleep | Dùng queue/latch có timeout |
| Nhận nhiều notification hơn dự kiến | Listener cũ chưa remove; transition trùng | Cleanup trong \`finally\`, xác định semantics của chuyển trạng thái |
| Listener nhận type ngoài ý muốn | Filter rộng hoặc không có filter | Dùng exact filter khi cần |
| Nội dung khác sau khi nhận qua server | Source/value được adapter chuẩn hóa hoặc client serialization | Assert hợp đồng của kênh đang test |
| Test xung đột khi chạy song song | Cùng \`ObjectName\` trên platform server | Sinh tên riêng, unregister sau test |
| Thời gian test kéo dài | Chờ vô hạn hoặc timeout quá lớn | Dùng \`poll(timeout)\` và ghi rõ điều kiện |
| Không dọn tài nguyên | MBean, listener hoặc connector còn tồn tại | Dùng \`try/finally\`, đóng context và connector |

## 15. Checklist thiết kế test notification

Một phép thử có thể quan sát đáng tin cậy thường đi theo chuỗi:

1. Tạo MBean/broadcaster mới hoặc context test riêng.
2. Đăng ký MBean dưới \`ObjectName\` xác định.
3. Gắn \`NotificationListener\` có bộ đệm ghi nhận.
4. Kích hoạt một sự kiện với dữ liệu đầu vào đã kiểm soát.
5. Chờ notification nếu callback bất đồng bộ, luôn có timeout.
6. Assert số lượng, type, message, source, sequence, timestamp, userData và filter/handback theo yêu cầu.
7. Gỡ listener, unregister MBean, đóng context/connector trong \`finally\`.

Hãy tránh test phụ thuộc log, UI và khoảng ngủ tùy ý. Nếu yêu cầu chỉ là “client JMX nhận được thông báo đúng”, listener quan sát được là công cụ kiểm tra trực tiếp nhất.

## 16. Ghi nhớ

**Notification test là kiểm tra điều mà một JMX client thực sự nhận được.** Một listener ghi nhận dữ liệu cho phép biến callback thành các assertion ổn định; unit test kiểm tra cách broadcaster tạo notification, còn integration test qua \`MBeanServer\` kiểm tra đường đi xuất MBean. Với môi trường bất đồng bộ, dùng queue và timeout có giới hạn, luôn dọn listener/MBean, và giữ logic nghiệp vụ độc lập hạ tầng JMX.
