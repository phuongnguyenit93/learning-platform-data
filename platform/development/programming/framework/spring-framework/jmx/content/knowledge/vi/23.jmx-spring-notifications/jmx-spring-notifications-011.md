# Kiểm thử notification và chống xử lý trùng trong Spring JMX

## 1. Mục tiêu và vấn đề

Trong Spring Framework JMX, một MBean có thể phát \`javax.management.Notification\` để thông báo trạng thái công việc, cảnh báo, thay đổi cấu hình hoặc sự kiện quản trị. Spring hỗ trợ \`NotificationPublisherAware\` và \`NotificationPublisher\` để managed bean gửi notification khi được export.

Tuy nhiên, **một notification được gửi không đồng nghĩa với việc mọi listener đều nhận và xử lý đúng một lần**. Listener có thể đăng ký trùng, client reconnect, producer phát lại cùng sự kiện hoặc consumer downstream retry. Ngoài ra, listener có thể bỏ lỡ notification khi chưa đăng ký, mất kết nối hoặc JVM restart. Do đó, cần kiểm thử ở nhiều tầng và xây dựng xử lý **idempotent** cho những tác động nghiệp vụ không được phép lặp.

Sau bài này, bạn có thể:

- Viết managed bean phát notification bằng Spring.
- Kiểm thử publisher bằng fake và kiểm thử listener thông qua \`MBeanServer\`.
- Kiểm tra type, sequence, source, payload và notification filter.
- Nhận diện những nguyên nhân làm một sự kiện bị xử lý trùng.
- Áp dụng event ID, database unique constraint và transaction để hạn chế side effect lặp.
- Phân biệt \`at-most-once\`, \`at-least-once\` và \`exactly-once\` trong phạm vi phù hợp.
- Kiểm thử concurrent delivery, reconnect, restart và phục hồi bằng snapshot.

## 2. Luồng notification và những điểm có thể lỗi

\`\`\`text
Spring bean
    |
    | NotificationPublisher.sendNotification()
    v
MBeanServer / notification broadcaster
    |
    +------ local NotificationListener
    |
    +------ remote JMX connector ------ remote listener
                                           |
                                           v
                                    Handler / queue
                                           |
                                      Dedup gate
                                           |
                                     Business effect
\`\`\`

Một hệ thống có các mốc riêng:

| Mốc | Điều có thể khẳng định | Điều chưa được bảo đảm |
|---|---|---|
| Producer tạo \`Notification\` | Có một object notification | Không chắc đã gửi |
| Producer gọi \`sendNotification()\` | Đã yêu cầu phát qua publisher | Không chắc mọi client đều nhận |
| Listener callback được gọi | Một callback đã quan sát notification | Không chắc xử lý nghiệp vụ thành công |
| Handler ghi event ID | Có ghi nhận lần xử lý | Không chắc side effect đã commit cùng transaction |
| Business effect commit | Tác động nghiệp vụ đã được ghi bền trong phạm vi transaction | Không chứng minh không có effect tương tự ở hệ thống khác |

Không coi JMX notification như durable event log. JMX không mặc định cung cấp persistence, replay lịch sử đầy đủ, consumer offset hoặc acknowledgment nghiệp vụ end-to-end.

## 3. Các trường dữ liệu của Notification

\`\`\`java
import javax.management.Notification;

Notification event = new Notification(
    "com.example.jobs.completed",
    this,
    101L,
    System.currentTimeMillis(),
    "Job completed"
);
event.setUserData("job-123");
\`\`\`

Các trường thường dùng:

- \`type\`: ví dụ \`com.example.jobs.completed\`.
- \`source\`: đối tượng hoặc thông tin nguồn phát.
- \`sequenceNumber\`: số thứ tự do producer gán.
- \`timeStamp\`: thời điểm producer gán.
- \`message\`: mô tả.
- \`userData\`: payload bổ sung.

**Không dùng riêng \`sequenceNumber\` làm định danh sự kiện toàn cục** nếu chưa có hợp đồng rõ. Hai MBeans khác nhau có thể cùng dùng sequence 101; counter có thể reset sau restart; các loại notification có thể chia sẻ hoặc sử dụng các dãy khác nhau.

Một deduplication key ổn định nên dựa trên \`eventId\` do nghiệp vụ cấp, hoặc \`source + instanceEpoch + sequence\` nếu producer bảo đảm tính duy nhất của bộ ba đó.

## 4. Managed bean phát notification qua Spring

\`\`\`java
package com.example.jmx;

import java.util.concurrent.atomic.AtomicLong;
import javax.management.Notification;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedNotification;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.jmx.export.notification.NotificationPublisher;
import org.springframework.jmx.export.notification.NotificationPublisherAware;

@ManagedResource(
    objectName = "com.example.jobs:type=Monitor,name=Import",
    description = "Import job monitoring"
)
@ManagedNotification(
    name = "com.example.jobs.completed",
    description = "Import completed event",
    notificationTypes = {"com.example.jobs.completed"}
)
public class ImportMonitor implements NotificationPublisherAware {

    private final AtomicLong sequence = new AtomicLong();
    private volatile NotificationPublisher publisher;
    private volatile String lastCompletedJob = "";

    @Override
    public void setNotificationPublisher(
            NotificationPublisher publisher) {
        this.publisher = publisher;
    }

    @ManagedAttribute(description = "Last completed job ID")
    public String getLastCompletedJob() {
        return lastCompletedJob;
    }

    @ManagedOperation(description = "Publish completion event")
    public void complete(String jobId) {
        if (jobId == null || jobId.isBlank()) {
            throw new IllegalArgumentException("jobId is blank");
        }

        NotificationPublisher current = publisher;
        if (current == null) {
            throw new IllegalStateException("Publisher unavailable");
        }

        lastCompletedJob = jobId;
        Notification notification = new Notification(
            "com.example.jobs.completed",
            this,
            sequence.incrementAndGet(),
            System.currentTimeMillis(),
            "Completed " + jobId
        );
        notification.setUserData(jobId);
        current.sendNotification(notification);
    }
}
\`\`\`

Giải thích:

1. \`@ManagedResource\` xác định ObjectName.
2. \`@ManagedNotification\` mô tả notification metadata cho JMX clients.
3. \`NotificationPublisherAware\` nhận publisher từ Spring JMX export infrastructure.
4. \`complete()\` gọi \`sendNotification()\` thực tế.
5. \`AtomicLong\` cấp sequence nguyên tử trong một instance, nhưng không tự bảo đảm thứ tự callback khi có nhiều thread.
6. \`getLastCompletedJob()\` là snapshot tối giản có thể đọc lại sau khi listener bỏ lỡ notification.

Annotation \`@ManagedNotification\` **không tự phát notification**. Bản thân source phải gọi publisher.

### Khởi tạo exporter

Một cách cấu hình Spring Framework:

\`\`\`java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfiguration {
    @Bean
    public ImportMonitor importMonitor() {
        return new ImportMonitor();
    }
}
\`\`\`

Trong Spring Boot, kiểm tra cấu hình JMX auto-configuration, chẳng hạn \`spring.jmx.enabled\` theo phiên bản Boot. Không tạo exporter thứ hai trùng cùng ObjectName khi hạ tầng hiện hành đã thực hiện export.

## 5. Ba cấp kiểm thử chính

| Cấp | Kiểm thử điều gì? | Không thể suy ra |
|---|---|---|
| **Unit test publisher** | Method tạo/gửi notification đúng | Có listener nhận qua MBeanServer |
| **Local JMX integration test** | MBean được đăng ký, listener nhận, filter hoạt động | Remote transport/reconnect chắc chắn đúng |
| **Business idempotency test** | Duplicate event không lặp side effect theo hợp đồng | JMX không bao giờ mất notification |
| **Remote JMX integration test** | Listener nhận qua connector, phục hồi kết nối | Có durable replay sau offline |
| **Restart/concurrency test** | Dedupe vẫn có hiệu lực trong điều kiện lỗi mục tiêu | Tự có exactly-once toàn hệ thống |

Nên kiểm tra **business effect**, không chỉ đếm số callback.

## 6. Unit test với CapturingPublisher

Dùng fake publisher trong JUnit:

\`\`\`java
import java.util.ArrayList;
import java.util.List;
import javax.management.Notification;
import org.springframework.jmx.export.notification.NotificationPublisher;

final class CapturingPublisher implements NotificationPublisher {
    final List<Notification> events = new ArrayList<>();

    @Override
    public void sendNotification(Notification notification) {
        events.add(notification);
    }
}
\`\`\`

Test:

\`\`\`java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class ImportMonitorTest {
    @Test
    void publishesCorrectCompletion() {
        ImportMonitor monitor = new ImportMonitor();
        CapturingPublisher publisher = new CapturingPublisher();
        monitor.setNotificationPublisher(publisher);

        monitor.complete("job-123");

        assertEquals(1, publisher.events.size());
        Notification event = publisher.events.get(0);
        assertEquals("com.example.jobs.completed", event.getType());
        assertEquals(1L, event.getSequenceNumber());
        assertEquals("job-123", event.getUserData());
        assertEquals("job-123", monitor.getLastCompletedJob());
    }

    @Test
    void rejectsBlankJobId() {
        ImportMonitor monitor = new ImportMonitor();
        monitor.setNotificationPublisher(new CapturingPublisher());

        assertThrows(
            IllegalArgumentException.class,
            () -> monitor.complete(" ")
        );
    }
}
\`\`\`

Fake trên không thread-safe; chỉ dùng cho unit test tuần tự. Với kiểm thử phát đồng thời, dùng \`ConcurrentLinkedQueue\` hoặc cơ chế đồng bộ hóa thích hợp.

Đây là test **producer logic**: nó không chứng minh Spring đã export MBean hay JMX listener nhận được notification.

## 7. Kiểm thử listener qua MBeanServer

Trong integration test, dùng \`MBeanServer\` mà Spring exporter đã chọn.

\`\`\`java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import javax.management.MBeanServer;
import javax.management.Notification;
import javax.management.NotificationListener;
import javax.management.ObjectName;

MBeanServer server = /* MBeanServer của Spring test context */ null;

ObjectName name = new ObjectName(
    "com.example.jobs:type=Monitor,name=Import"
);

if (!server.isRegistered(name)) {
    throw new AssertionError("Missing MBean: " + name);
}

CountDownLatch latch = new CountDownLatch(1);
AtomicReference<Notification> received = new AtomicReference<>();

NotificationListener listener = (event, handback) -> {
    received.set(event);
    latch.countDown();
};

server.addNotificationListener(name, listener, null, null);

try {
    server.invoke(
        name,
        "complete",
        new Object[]{"job-123"},
        new String[]{String.class.getName()}
    );

    if (!latch.await(5, TimeUnit.SECONDS)) {
        throw new AssertionError("Notification was not received");
    }

    Notification actual = received.get();
    if (!"com.example.jobs.completed".equals(actual.getType())) {
        throw new AssertionError("Unexpected type");
    }
    if (!"job-123".equals(actual.getUserData())) {
        throw new AssertionError("Unexpected payload");
    }
} finally {
    server.removeNotificationListener(name, listener);
}
\`\`\`

\`server\` là placeholder: test hoàn chỉnh phải lấy MBeanServer thật từ Spring context hoặc \`ManagementFactory.getPlatformMBeanServer()\` **chỉ khi exporter sử dụng đúng platform server**.

Để giảm flaky tests:

- Đăng ký listener **trước khi** kích hoạt event.
- Dùng \`CountDownLatch\` hoặc \`BlockingQueue\`, không cố định \`Thread.sleep()\`.
- Chờ với timeout phù hợp.
- Gỡ listener trong \`finally\`.
- Khởi tạo/đóng context có ownership rõ ràng.
- Tránh trùng ObjectName giữa các tests chạy song song cùng JVM.
- Nếu callback chạy đồng thời, dùng thread-safe storage thay vì \`ArrayList\`.

## 8. Kiểm tra notification metadata

\`\`\`java
var info = server.getMBeanInfo(name);

for (var notificationInfo : info.getNotifications()) {
    System.out.println(notificationInfo.getName());
    System.out.println(
        java.util.Arrays.toString(notificationInfo.getNotifTypes())
    );
}
\`\`\`

Cần phân biệt:

- \`MBeanInfo.getNotifications()\` mô tả **loại notification được công bố**.
- \`NotificationPublisher.sendNotification()\` là hành động **phát**.
- \`NotificationListener.handleNotification()\` là nơi **nhận callback**.
- Business handler quyết định liệu notification có dẫn đến **side effect** không.

Một notification được khai báo trong metadata có thể chưa từng được phát. Một listener nhận callback có thể lỗi trước khi xử lý nghiệp vụ.

## 9. Test filter: nhận đúng loại notification

Ví dụ dùng filter chính xác:

\`\`\`java
import javax.management.NotificationFilter;

NotificationFilter onlyCompleted = notification ->
    "com.example.jobs.completed".equals(notification.getType());

server.addNotificationListener(
    name,
    listener,
    onlyCompleted,
    null
);
\`\`\`

Ngoài ra có \`NotificationFilterSupport\`:

\`\`\`java
import javax.management.NotificationFilterSupport;

NotificationFilterSupport filter = new NotificationFilterSupport();
filter.enableType("com.example.jobs.");
\`\`\`

\`NotificationFilterSupport\` hỗ trợ so khớp **prefix type**, nên \`enableType("com.example.jobs.")\` có thể chấp nhận nhiều loại \`started\`, \`completed\`, \`failed\`. Không mặc định đây là phép equality chính xác.

Bộ test nên phát ít nhất ba types rồi xác minh:

| Type | Exact completed filter |
|---|---|
| \`com.example.jobs.started\` | Bị loại |
| \`com.example.jobs.completed\` | Được nhận |
| \`com.example.jobs.failed\` | Bị loại |

Nếu listener chỉ nhận completed, khoảng trống sequence của source **không chứng minh notification bị mất**; có thể các loại khác đã bị filter chủ động loại.

## 10. Thứ tự và concurrent publication

Ví dụ:

\`\`\`text
Thread A: sequence=100 --pause--> send(N100)
Thread B: sequence=101 ---------> send(N101)
Listener: N101 trước N100
\`\`\`

\`AtomicLong.incrementAndGet()\` bảo đảm cấp số không trùng trong instance, nhưng không tuần tự hóa toàn bộ thao tác tạo và phát. Nếu thứ tự là hợp đồng bắt buộc, producer phải có điểm tuần tự hóa phù hợp, ví dụ một executor đơn luồng hoặc phần phát được đồng bộ hóa.

Tương tự, listener có thể chuyển notification vào thread pool, dẫn đến thời gian **hoàn tất side effect** khác thứ tự callback.

Kiểm thử concurrency nên kiểm tra:
- Event IDs có duy nhất không.
- Tập các event nhận được trong phạm vi test có đúng không.
- Có sequence đảo thứ tự không nếu contract yêu cầu.
- Có duplicate effect khi nhiều handler workers cùng xử lý một event không.
- Có lỗi dữ liệu do shared mutable state không.

Không lấy một bài test local pass làm bằng chứng về ordering hoặc delivery guarantee trên remote network khi mất kết nối.

## 11. Vì sao một event bị xử lý trùng?

### 11.1. Đăng ký listener lặp

\`\`\`java
server.addNotificationListener(name, listener, null, null);
server.addNotificationListener(name, listener, null, null);
\`\`\`

Các lần đăng ký có thể tương ứng nhiều registration entries; không nên giả định MBeanServer tự gộp mọi listener giống object. Khi cleanup, cần dùng overload phù hợp và quản lý \`listener\`, \`filter\`, \`handback\`.

### 11.2. Reconnect tạo nhiều consumer đang hoạt động

Client mất connection rồi tạo connection mới nhưng không vô hiệu hóa session cũ. Nếu cùng một logical consumer có nhiều active listener, một event có thể đến nhiều lần ở tầng ứng dụng.

Giải pháp:
- Theo dõi connection generation.
- Đăng ký listener một lần cho mỗi connection hợp lệ.
- Gỡ hoặc đóng connection cũ.
- Vô hiệu hóa callback từ session đã hết hạn.
- Refresh snapshot sau khi reconnect.

### 11.3. Producer gửi lặp

Business workflow có thể gọi gửi notification hai lần do retry hoặc do event handler được kích hoạt lặp. Một notification ID ổn định giúp consumer nhận biết cùng một logical event.

### 11.4. Downstream retry

Listener chuyển sự kiện sang database, email hoặc queue. Nếu worker downstream retry, side effect có thể lặp dù JMX callback chỉ chạy một lần.

### 11.5. Hai listeners cùng đảm nhiệm một nhiệm vụ

Hai consumer instances cùng subscribe và cùng ghi dữ liệu vào bảng nghiệp vụ. Nếu không phân chia ownership hoặc dedupe chung, cả hai có thể áp dụng cùng một logical event.

**Bài học:** Deduplication phải được thiết kế ở ranh giới của **business side effect**, không chỉ tại tầng JMX callback.

## 12. Idempotency là gì?

Một thao tác idempotent có thể áp dụng lại cùng yêu cầu mà không làm thay đổi kết quả mong muốn sau lần thành công đầu.

Ví dụ:
- \`setJobStatus("job-123","COMPLETED")\` theo semantics gán trạng thái có thể idempotent.
- \`upsert\` bản ghi với khóa cố định có thể idempotent.
- \`incrementCompletedCount()\` không idempotent.
- \`sendEmail()\` không idempotent mặc định.
- \`chargeAccount(amount)\` không idempotent nếu không có idempotency key.

\`\`\`text
E-123 delivered
    |
    +--> handler A --> increment count
    |
    +--> handler B --> increment count

Result: count tăng 2 lần
\`\`\`

Khi handler có deduplication key:

\`\`\`text
E-123 delivered
    |
    +--> gate accepts E-123 --> apply effect
    |
    +--> gate sees E-123 --> skip duplicate
\`\`\`

Phải xác định **một event** là gì, đặc biệt khi cùng \`jobId\` có thể có nhiều lần bắt đầu/kết thúc ở các lần chạy khác nhau. Không dùng \`jobId\` làm event ID nếu cùng job có thể sinh nhiều events hợp lệ.

## 13. Payload có eventId

Định nghĩa payload:

\`\`\`java
import java.io.Serializable;

public record JobEvent(
    String eventId,
    String jobId,
    String status,
    long occurredAtEpochMillis
) implements Serializable {
    private static final long serialVersionUID = 1L;
}
\`\`\`

Tạo notification:

\`\`\`java
JobEvent payload = new JobEvent(
    "evt-123",
    "job-123",
    "COMPLETED",
    System.currentTimeMillis()
);

Notification event = new Notification(
    "com.example.jobs.completed",
    this,
    sequence.incrementAndGet()
);
event.setUserData(payload);
publisher.sendNotification(event);
\`\`\`

Một \`eventId\` tốt:
- Được cấp một lần cho logical event.
- Không thay đổi khi retry publication.
- Không trùng với event khác trong phạm vi đã định.
- Có thể lưu và truy vết qua hệ thống.
- Không chứa secret/personal data không cần thiết.

Nếu remote client không có Java class \`JobEvent\`, Java serialization có thể thất bại. Khi cần client độc lập với classpath, dùng String event ID hoặc OpenType như \`CompositeData\`.

## 14. Deduplication trong bộ nhớ

Ví dụ listener có gate thread-safe:

\`\`\`java
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import javax.management.Notification;
import javax.management.NotificationListener;

public class InMemoryDedupListener implements NotificationListener {

    private final Set<String> seenIds =
        ConcurrentHashMap.newKeySet();

    @Override
    public void handleNotification(
            Notification notification,
            Object handback) {

        if (!(notification.getUserData() instanceof JobEvent event)) {
            return;
        }

        if (!seenIds.add(event.eventId())) {
            return;
        }

        applyEffect(event);
    }

    private void applyEffect(JobEvent event) {
        System.out.println("Event: " + event.eventId());
    }
}
\`\`\`

\`seenIds.add()\` là thao tác nguyên tử đối với key trong một instance. Nhưng **đây không phải durable exactly-once**:

1. Set tăng kích thước không giới hạn nếu không có TTL/eviction.
2. Restart xóa trạng thái seen.
3. Nhiều JVM không chia sẻ seen set.
4. Nếu handler fail sau \`seenIds.add()\`, retry bị bỏ qua dù effect chưa thành công.
5. Một event ID lặp với payload mâu thuẫn có thể bị bỏ qua mà không được báo lỗi.

Dùng cách này cho UI refresh, xử lý không quan trọng hoặc một phiên sống ngắn có thể hợp lý. Với dữ liệu nghiệp vụ, cần giải pháp bền vững.

## 15. Chống xử lý trùng bằng database unique constraint

Tạo bảng:

\`\`\`sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(150) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
\`\`\`

Luồng transaction:

\`\`\`text
BEGIN
    INSERT processed_events(
        consumer_name, event_id, processed_at
    )
    VALUES ('jobs-consumer', 'evt-123', CURRENT_TIMESTAMP);

    UPDATE job_statistics
    SET completed_count = completed_count + 1
    WHERE statistic_id = 'global';
COMMIT
\`\`\`

Nếu \`INSERT\` gặp duplicate primary key, logic consumer bỏ qua side effect hoặc trả trạng thái “already processed” theo hợp đồng.

Điều quan trọng là dedup insert và business update phải nằm trong **cùng một transaction** khi cả hai là dữ liệu của cùng database. Nếu dedup key được commit trước rồi business update thất bại, retry sau có thể bị loại sai.

### Ví dụ Spring service

\`\`\`java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class JobEventConsumer {
    private final ProcessedEventRepository processed;
    private final JobStatisticsRepository statistics;

    public JobEventConsumer(
            ProcessedEventRepository processed,
            JobStatisticsRepository statistics) {
        this.processed = processed;
        this.statistics = statistics;
    }

    @Transactional
    public void process(JobEvent event) {
        boolean inserted = processed.tryInsertUnique(
            "jobs-consumer", event.eventId()
        );

        if (!inserted) {
            return;
        }

        statistics.incrementCompletedCount();
    }
}
\`\`\`

\`tryInsertUnique\` là pseudocode của repository: implementation thực tế cần dùng unique constraint/atomic insert và xử lý duplicate conflict phù hợp với transaction manager và database. Không dùng “SELECT exists rồi INSERT” đơn thuần, vì hai threads có thể cùng thấy chưa tồn tại.

### Tác động ngoài database

Với email, HTTP API, payment hoặc file write, database transaction không tự bảo đảm side effect bên ngoài thực hiện đúng một lần. Có thể cần downstream idempotency key, outbox, trạng thái xử lý và workflow retry rõ ràng.

## 16. Vì sao không nên dedupe chỉ bằng sequence?

Giả sử:

\`\`\`text
MBean instance A: seq=100
JVM restart
MBean instance B: seq=100
\`\`\`

Hai notifications có cùng sequence nhưng là events khác nhau.

Một key tốt hơn:

\`\`\`text
sourceObjectName + sourceEpoch + sequenceNumber
\`\`\`

Nhưng chỉ phù hợp nếu:
- Producer cam kết mỗi sequence tương ứng duy nhất một event trong epoch.
- Epoch được thay đổi sau restart.
- Client xác định đúng source.
- Không bỏ qua sự khác biệt giữa các event types khi producer định nghĩa sequence riêng.

Trong nghiệp vụ, event ID ổn định do source logic cấp thường đáng tin cậy hơn.

## 17. Kiểm thử chống trùng theo hành vi nghiệp vụ

Bộ test tối thiểu:

1. **Event mới:** E-1 xử lý một lần → side effect tăng một.
2. **Event lặp:** E-1 xử lý hai lần → side effect vẫn tăng một.
3. **Event khác:** E-2 xử lý → tăng thêm một.
4. **Concurrent duplicates:** 20 threads xử lý E-3 → side effect chỉ tăng một.
5. **Restart:** sau restart, E-3 vẫn không làm lặp effect nếu contract cần durable dedup.
6. **Failure before commit:** transaction rollback → retry có thể xử lý lại thành công.
7. **Conflicting payload:** cùng event ID nhưng nội dung khác → báo conflict theo policy thay vì âm thầm ghi dữ liệu sai.

Ví dụ JUnit:

\`\`\`java
@Test
void duplicateEventDoesNotDoubleCount() {
    JobEvent event = new JobEvent(
        "evt-123", "job-123", "COMPLETED", 1000L
    );

    consumer.process(event);
    consumer.process(event);

    assertEquals(
        1,
        statistics.countCompletedEffects("job-123")
    );
}
\`\`\`

Đây là assertion ở tầng business effect, không chỉ kiểm tra số lần \`handleNotification()\` được gọi.

## 18. Kiểm thử concurrent duplicates

Một ví dụ khung:

\`\`\`java
ExecutorService executor =
    Executors.newFixedThreadPool(8);

CountDownLatch start = new CountDownLatch(1);
List<Future<?>> futures = new ArrayList<>();

for (int i = 0; i < 20; i++) {
    futures.add(executor.submit(() -> {
        start.await();
        consumer.process(event);
        return null;
    }));
}

start.countDown();

try {
    for (Future<?> future : futures) {
        future.get();
    }
} finally {
    executor.shutdown();
}

assertEquals(1, repository.countEffects(event.eventId()));
\`\`\`

Trong code thật, bổ sung imports, test database và transaction configuration phù hợp. Concurrency test cần dùng database với unique constraint thực tế, vì mock repository không chứng minh được các race conditions trong storage.

Nếu nhiều threads cùng làm \`SELECT exists\`, cả hai có thể thấy false rồi xử lý. Unique key và atomic insert là điểm bảo vệ cuối cùng.

## 19. Kiểm thử listener registration lifecycle

Listener nên được đăng ký một lần trên connection/session hiện tại và gỡ khi không còn cần thiết.

\`\`\`java
server.addNotificationListener(
    name, listener, filter, handback
);
\`\`\`

Cleanup:

\`\`\`java
server.removeNotificationListener(
    name, listener, filter, handback
);
\`\`\`

Phân biệt các registration có cùng listener nhưng filter/handback khác nhau. Khi dùng Spring JMX listener registry hoặc cơ chế registration tự viết, cần thống nhất ai sở hữu listener lifecycle.

Test nên xác minh:
- Không có callback sau khi listener được remove đúng cách.
- Không tạo registration trùng khi component reinitialize.
- Không có hai connection generations cùng tạo side effects.
- Shutdown context dọn tài nguyên phù hợp.
- Reconnect đăng ký lại listener mà không giữ references lỗi thời.

## 20. Remote reconnect và snapshot

Một kịch bản:

\`\`\`text
Client connected
    |
    v
Receives E-10
    |
    v
Network outage
    |
    +--- Server emits E-11, E-12
    |
    v
Client reconnects
    |
    v
Re-register listener
    |
    v
Read current MBean state
\`\`\`

Không được giả định E-11/E-12 sẽ được replay đầy đủ sau reconnect. Remote connector có thể có buffer và chính sách fetch riêng, nhưng JMX notification không phải durable business history.

Một dashboard nên xử lý notification như **tín hiệu thay đổi**:

\`\`\`text
Notification received
         |
         v
Refresh current attributes
         |
         v
Replace UI snapshot
\`\`\`

Nếu notification bị trùng, refresh thêm một lần không làm sai trạng thái. Nếu thiếu notification, client có thể refresh định kỳ hoặc khi reconnect để đồng bộ.

Nếu cần biết từng lần chuyển trạng thái đã bị bỏ lỡ, snapshot không đủ; cần event log riêng.

## 21. Các mức bảo đảm cần hiểu đúng

| Mong muốn | JMX notification cơ bản có tự bảo đảm? | Giải pháp khi bắt buộc |
|---|---|---|
| Listener đăng ký có thể nhận notification | Có, theo cơ chế broadcaster và connector đang hoạt động | Test registration/filter |
| Notification cũ được replay khi listener đăng ký muộn | Không | Durable event log |
| Mọi event tồn tại qua JVM restart | Không | Persistent outbox/broker |
| Callback chỉ gọi đúng một lần bất chấp lỗi | Không thể mặc định | Thiết kế consumer chịu duplicate |
| Business effect áp dụng một lần | Không | Idempotency key + transaction |
| Phát hiện sequence gap | Có thể nếu source contract rõ | Source+epoch+sequence |
| Khôi phục state sau reconnect | Có nếu MBean cung cấp snapshot | Read attributes/version |
| Audit toàn bộ lịch sử | Không | Database/event store |

Không đánh đồng:
- **at-most-once attempt:** có thể bỏ sót nhưng không lặp attempt theo policy.
- **at-least-once attempt:** retry cho đến khi đạt tiêu chí, có thể lặp.
- **exactly-once effect:** side effect có ràng buộc để không nhân đôi tác động.

Một hệ thống có at-least-once delivery từ broker vẫn thường cần idempotent consumer để tiến gần exactly-once business effects.

## 22. Khi nào dùng queue hoặc event store?

JMX notification phù hợp cho:
- Tín hiệu refresh dashboard.
- Cảnh báo vận hành tức thời.
- Quan sát trạng thái runtime.
- Tool quản trị kết nối tại thời điểm phát.

Không nên dùng JMX notification làm kênh duy nhất cho:
- Thanh toán hoặc thay đổi số dư.
- Audit log phải đầy đủ.
- Workflow không được mất event khi JVM crash.
- Hàng đợi công việc có retry bền vững.
- Tích hợp nhiều services cần consumer offset/replay.

Kiến trúc kết hợp:

\`\`\`text
Business transaction
       |
       v
Database + outbox
       |
       v
Durable event processing
       |
       +----> Idempotent business consumers
       |
       +----> State/metrics
                   |
                   v
               JMX MBean
                   |
                   v
            JMX notification
                   |
                   v
              Dashboard
\`\`\`

Trong thiết kế này, notification là tầng quan sát; event business quan trọng có nguồn lưu bền riêng.

## 23. Những sai lầm thường gặp

**1. “JMX đảm bảo listener không bao giờ nhận trùng.”**  
Không có bảo đảm nghiệp vụ như vậy; ứng dụng có thể tạo nhiều registrations hoặc downstream retry.

**2. “Sequence number là event ID duy nhất.”**  
Không đúng nếu nguồn có reset, nhiều MBeans hoặc chính sách sequence không rõ.

**3. “ConcurrentHashMap dedup là exactly-once.”**  
Không đúng: không bền qua restart và có thể đánh dấu đã xử lý trước khi effect thành công.

**4. “Đã nhận callback nghĩa là transaction nghiệp vụ đã commit.”**  
Không đúng: callback và business transaction là hai giai đoạn khác.

**5. “@ManagedNotification tự phát event.”**  
Không. Nó mô tả metadata, còn publisher/broadcaster phải gửi notification.

**6. “Filter làm mất sequence nên connector bị lỗi.”**  
Không nhất thiết. Filter có thể cố ý loại các notification types khác.

**7. “Reconnect tự nhận lại mọi notification mất.”**  
Không nên giả định. Cần resubscribe và refresh snapshot hoặc dùng event store.

**8. “Chỉ kiểm tra callback count là đủ.”**  
Không. Business side effects cần được kiểm tra riêng.

**9. “Dùng DTO nội bộ trong userData luôn tương thích remote.”**  
Không. Client có thể không có class hoặc bị từ chối deserialize.

**10. “Dùng một listener callback để chạy transaction rất dài là vô hại.”**  
Không. Nó có thể block notification dispatch; dùng cơ chế worker/queue phù hợp và quản lý backpressure.

## 24. Bài tập thực hành

### Bài A — Unit test producer

1. Tạo \`ImportMonitor\`.
2. Tiêm fake publisher.
3. Gọi \`complete("job-1")\`.
4. Kiểm tra type, sequence, userData và trạng thái.
5. Gọi thêm lần nữa với job khác và quan sát sequence.

### Bài B — Integration test MBeanServer

1. Bật Spring annotation JMX export.
2. Đăng ký notification listener.
3. Gọi \`complete\` bằng \`MBeanServer.invoke()\`.
4. Chờ notification bằng latch.
5. Kiểm tra payload và metadata.
6. Gỡ listener trong finally.

### Bài C — Duplicate event

1. Tạo một \`JobEvent\` có event ID cố định.
2. Gọi handler hai lần.
3. Assert side effect chỉ xuất hiện một lần.
4. Gọi một event ID khác và assert side effect được áp dụng thêm.

### Bài D — Concurrency

1. Dùng 20 threads xử lý cùng event ID.
2. Dùng database unique constraint và transaction.
3. Assert side effect chỉ áp dụng một lần.
4. Đổi sang check-then-insert không atomic để quan sát race.

### Bài E — Restart

1. Xử lý và commit event E-1.
2. Tạo consumer instance mới hoặc restart application.
3. Gửi E-1 lần nữa.
4. Xác minh dedup bền vững vẫn ngăn effect lặp.
5. So sánh với in-memory seen set.

### Bài F — Reconnect

1. Kết nối JMX remote ở môi trường test.
2. Đăng ký listener.
3. Mất kết nối trong lúc server phát notification.
4. Reconnect và đăng ký lại.
5. Refresh MBean snapshot.
6. Xác minh không có side effect trùng khi event được nhận lại theo đường ứng dụng.

## 25. Câu hỏi tự kiểm tra

**Câu 1.** \`@ManagedNotification\` có tự phát notification không?  
**Trả lời:** Không. Cần \`NotificationPublisher.sendNotification()\` hoặc broadcaster gửi thực tế.

**Câu 2.** \`sequenceNumber\` có phải unique event ID xuyên mọi JVM không?  
**Trả lời:** Không. Nó do producer gán và có thể reset hoặc trùng.

**Câu 3.** Vì sao in-memory dedup có thể làm mất xử lý?  
**Trả lời:** Nếu đánh dấu seen trước side effect rồi handler fail, retry sẽ bị bỏ qua.

**Câu 4.** Vì sao cần database unique constraint khi nhiều threads xử lý cùng ID?  
**Trả lời:** Để bảo đảm atomic uniqueness thay vì rơi vào race check-then-insert.

**Câu 5.** Khi reconnect JMX client, phải làm gì?  
**Trả lời:** Đăng ký lại listener trên connection mới, quản lý session cũ và refresh trạng thái.

**Câu 6.** Kiểm thử tốt nhất chống side effect trùng là gì?  
**Trả lời:** Assert kết quả nghiệp vụ cuối cùng, cả khi event gửi nhiều lần hoặc đồng thời, không chỉ assert callback count.

**Câu 7.** Notification có thay thế durable event store khi yêu cầu audit đầy đủ không?  
**Trả lời:** Không. JMX notification không mặc định lưu bền hoặc replay toàn bộ lịch sử.

## 26. Ghi nhớ

- Kiểm thử notification cần tách producer, local MBeanServer, remote connector và business effect.
- JMX notification là cơ chế báo hiệu, **không phải durable event log**.
- Duplicate có thể do đăng ký listener, producer gửi lại, reconnect hoặc downstream retry.
- \`sequenceNumber\` hữu ích để chẩn đoán nhưng không mặc định là khóa dedup bền vững.
- Dùng **event ID ổn định** cho logical event; giữ source/epoch khi dùng sequence.
- In-memory dedup chỉ phù hợp khi chấp nhận giới hạn restart, concurrency phạm vi JVM và failure handling.
- Side effect trên database cần unique constraint và transaction chung với dedup record.
- Dashboard thường nên dùng notification để kích hoạt đọc snapshot thay vì phụ thuộc vào việc nhận đủ từng event.
- Với yêu cầu không mất event, hãy chọn outbox, event log hoặc broker có lưu bền và idempotent consumer.

### Tài liệu tham khảo

- Spring Framework Reference — JMX Notifications: https://docs.spring.io/spring-framework/reference/integration/jmx/notifications.html
- Spring Framework Javadoc — \`NotificationPublisherAware\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/notification/NotificationPublisherAware.html
- Spring Framework Javadoc — \`NotificationPublisher\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/notification/NotificationPublisher.html
- Java SE 21 API — \`Notification\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/Notification.html
- Java SE 21 API — \`NotificationListener\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/NotificationListener.html
- Java SE 21 API — \`MBeanServer\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
