# Đẩy notification thành sự kiện vận hành trong Spring Framework JMX

## 1. Mục tiêu

JMX notification là tín hiệu runtime do MBean phát ra. Trong Spring Framework JMX, các thành phần quản trị thường dùng notification để thông báo trạng thái worker, queue, cache hoặc kết nối downstream. Để sử dụng cho vận hành, cần biến những notification này thành **operational event** có cấu trúc, dễ lưu trữ, tìm kiếm, cảnh báo và kích hoạt runbook.

Chuỗi xử lý mục tiêu:

~~~text
Business event
   -> Spring MBean
   -> JMX notification
   -> NotificationListener
   -> normalizer / enricher
   -> bounded queue / durable pipeline
   -> operational event sink
   -> alerting / dashboard / automation
~~~

Ví dụ notification:

~~~text
type=com.example.orders.queue.threshold
source=com.example.orders:type=Queue,name=payments
message=Queue backlog above threshold
~~~

Sự kiện vận hành tương ứng:

~~~json
{
  "eventType": "queue.backlog.high",
  "service": "checkout",
  "environment": "production",
  "instance": "checkout-2",
  "resource": "payments",
  "severity": "warning",
  "occurredAt": "2026-11-11T09:00:00Z",
  "summary": "Queue backlog exceeded threshold",
  "attributes": {
    "pendingCount": "1400",
    "threshold": "1000"
  }
}
~~~

Giá trị JSON chỉ minh họa, không phải dữ liệu thực. Trong hệ thống thật phải lấy target identity, timestamp, severity và payload từ các nguồn đáng tin cậy.

## 2. Phân biệt notification, operational event và alert

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| JMX notification | Thông điệp runtime qua MBeanServer | com.example.queue.threshold |
| Operational event | Bản ghi sự kiện có schema ổn định và ngữ cảnh vận hành | queue.backlog.high |
| Alert | Đánh giá điều kiện cần chú ý hoặc xử lý | Backlog cao hơn ngưỡng trong 5 phút |
| Incident | Vấn đề vận hành cần điều phối xử lý | Checkout degraded |
| Automation action | Hành động do policy phê duyệt | Thu thập diagnostics |

Không phải mọi notification đều cần alert. Nếu mỗi biến động metric tạo một incident, hệ thống sẽ tạo alert fatigue và khó xác định sự cố thật.

## 3. Thiết kế trách nhiệm từng lớp

**Emitter MBean:** xác định state transition và phát notification với type rõ ràng.

**Listener:** nhận callback nhanh, validate loại event và đưa vào pipeline.

**Normalizer:** ánh xạ type, ObjectName, userData thành schema độc lập với Java JMX.

**Enricher:** bổ sung service, environment, target JVM, deployment version và correlation ID.

**Event sink:** gửi vào event log, broker, hệ thống cảnh báo hoặc API vận hành.

**Automation engine:** quyết định hành động sau các điều kiện bảo mật, idempotency và cooldown.

Không nên để emitter tự gửi HTTP tới nhiều hệ thống bên ngoài hoặc đặt toàn bộ retry logic trong handleNotification. Cách đó tạo coupling, khiến chậm mạng có thể ảnh hưởng đường phát event.

## 4. Spring NotificationPublisher ở phía nguồn

Một bean muốn phát notification qua Spring JMX có thể implement NotificationPublisherAware.

~~~java
package com.example.orders.management;

import java.util.concurrent.atomic.AtomicLong;
import javax.management.Notification;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.jmx.export.annotation.ManagedNotification;
import org.springframework.jmx.export.notification.NotificationPublisher;
import org.springframework.jmx.export.notification.NotificationPublisherAware;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.orders:type=Queue,name=payments",
    description = "Payment queue management"
)
@ManagedNotification(
    name = "com.example.orders.queue.threshold",
    description = "Queue backlog exceeded threshold"
)
public class PaymentQueueManagement
        implements NotificationPublisherAware {

    private final AtomicLong sequence = new AtomicLong();
    private volatile NotificationPublisher publisher;

    @Override
    public void setNotificationPublisher(NotificationPublisher value) {
        this.publisher = value;
    }

    public void onThresholdCrossed(int pendingCount) {
        NotificationPublisher current = publisher;
        if (current == null) {
            throw new IllegalStateException("JMX publisher unavailable");
        }

        Notification event = new Notification(
            "com.example.orders.queue.threshold",
            this,
            sequence.incrementAndGet(),
            System.currentTimeMillis(),
            "Queue backlog above threshold"
        );
        event.setUserData(pendingCount);
        current.sendNotification(event);
    }
}
~~~

Annotation ManagedNotification chỉ công bố metadata về loại sự kiện; nó không tự động phát event. Bean phải được exporter phù hợp quản lý, và ứng dụng cần gọi sendNotification.

Ví dụ giả định business layer chỉ gọi onThresholdCrossed khi có transition vượt ngưỡng. Nếu gọi mỗi lần queue depth tăng, notification storm có thể xảy ra. Cần hysteresis hoặc throttle theo chính sách.

## 5. Chuẩn hóa event schema

Một schema ổn định giúp downstream không phụ thuộc vào javax.management.Notification.

~~~java
import java.time.Instant;
import java.util.Map;

public record OperationalEvent(
    String eventType,
    String service,
    String environment,
    String instance,
    String objectName,
    String resource,
    String severity,
    Instant occurredAt,
    String summary,
    Map<String, String> attributes
) {}
~~~

Đoạn record yêu cầu Java hỗ trợ record; dự án Java 8/11 có thể dùng POJO bất biến thay thế.

Quy tắc schema:

1. Giữ tên eventType ổn định và có semantic rõ.
2. Chọn timestamp UTC; phân biệt occurredAt với receivedAt nếu cần.
3. Dùng service/environment/instance từ metadata triển khai đáng tin cậy.
4. Lưu canonical ObjectName để truy nguồn.
5. Giới hạn kích thước và kiểu dữ liệu attributes.
6. Không forward secret, token hoặc payload cá nhân nhạy cảm.
7. Có schema version khi xuất hiện thay đổi không tương thích.
8. Không giả định JMX sequenceNumber là event ID toàn cục.

Ví dụ tên event:

~~~text
worker.failed
worker.recovered
queue.backlog.high
queue.backlog.recovered
cache.refresh.completed
configuration.applied
~~~

## 6. Normalizer ánh xạ notification

~~~java
import java.time.Instant;
import java.util.Map;
import javax.management.Notification;
import javax.management.ObjectName;

public final class QueueEventNormalizer {
    private final String service;
    private final String environment;
    private final String instance;

    public QueueEventNormalizer(
            String service,
            String environment,
            String instance) {
        this.service = service;
        this.environment = environment;
        this.instance = instance;
    }

    public OperationalEvent normalize(
            Notification n, ObjectName source) {

        if (!"com.example.orders.queue.threshold".equals(n.getType())) {
            throw new IllegalArgumentException("Unsupported event type");
        }

        Object payload = n.getUserData();
        String count = payload instanceof Integer
            ? payload.toString() : "unknown";

        return new OperationalEvent(
            "queue.backlog.high",
            service,
            environment,
            instance,
            source.getCanonicalName(),
            source.getKeyProperty("name"),
            "warning",
            Instant.ofEpochMilli(n.getTimeStamp()),
            "Queue backlog above threshold",
            Map.of("pendingCount", count)
        );
    }
}
~~~

Normalizer phải kiểm tra whitelist type/source và loại dữ liệu userData. Với remote JMX, userData có thể không deserialize được nếu client thiếu class hoặc kiểu không tương thích.

Không nên ép notification.getSource() luôn là ObjectName. Source có thể là object hoặc thông tin khác tùy emitter/transport. Có thể truyền ObjectName đáng tin cậy qua handback lúc đăng ký listener.

## 7. Đăng ký NotificationListener

~~~java
import javax.management.NotificationListener;
import javax.management.ObjectName;

ObjectName queueName = new ObjectName(
    "com.example.orders:type=Queue,name=payments"
);

NotificationListener listener = (notification, handback) -> {
    ObjectName source = (ObjectName) handback;
    // Normalize and enqueue quickly.
};

connection.addNotificationListener(
    queueName, listener, null, queueName
);
~~~

Ở đây connection là MBeanServerConnection kết nối tới server đích. Vì chính code truyền queueName làm handback, cast ObjectName là hợp lệ cho registration này.

Khi listener nằm trong cùng Spring context và MBean do cùng exporter quản lý, có thể dùng NotificationListenerBean:

~~~java
import org.springframework.jmx.export.NotificationListenerBean;

NotificationListenerBean listenerBean =
    new NotificationListenerBean(listener);

listenerBean.setMappedObjectNames(
    "com.example.orders:type=Queue,name=payments"
);

exporter.setNotificationListeners(listenerBean);
~~~

Nếu MBean ở JVM khác hoặc do exporter khác quản lý, đăng ký qua MBeanServerConnection thường rõ ràng hơn. Không tự tạo thêm exporter gây trùng ObjectName chỉ để gắn listener.

## 8. Đặt giới hạn cho callback

Callback không nên thực hiện I/O chậm:

~~~java
public void handleNotification(Notification n, Object context) {
    externalIncidentApi.createIncident(n); // Không nên.
}
~~~

Nên tách thành:

~~~text
JMX callback
   -> validate + normalize
   -> bounded queue
   -> worker
   -> sink
~~~

Một listener có queue giới hạn:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import javax.management.Notification;
import javax.management.NotificationListener;
import javax.management.ObjectName;

public final class EventBridgeListener implements NotificationListener {
    private final BlockingQueue<OperationalEvent> queue =
        new ArrayBlockingQueue<>(1000);

    private final QueueEventNormalizer normalizer;

    public EventBridgeListener(QueueEventNormalizer normalizer) {
        this.normalizer = normalizer;
    }

    @Override
    public void handleNotification(
            Notification notification, Object handback) {

        if (!(handback instanceof ObjectName)) {
            return;
        }
        ObjectName source = (ObjectName) handback;

        try {
            OperationalEvent event =
                normalizer.normalize(notification, source);

            boolean accepted = queue.offer(event);
            if (!accepted) {
                // Increment drop counter; apply overload policy.
            }
        } catch (IllegalArgumentException invalid) {
            // Increment invalid/filtered counter.
        }
    }

    public OperationalEvent take() throws InterruptedException {
        return queue.take();
    }
}
~~~

Queue capacity 1000 chỉ là ví dụ. Cần xác định trường hợp full: drop, coalesce, dead-letter hoặc đưa qua đường bền vững khác. Đừng dùng unbounded queue vì consumer chậm có thể khiến JVM hết bộ nhớ.

## 9. Event sink và worker

Định nghĩa interface sink:

~~~java
public interface OperationalEventSink {
    void publish(OperationalEvent event) throws Exception;
}
~~~

Worker đơn giản:

~~~java
public final class EventBridgeWorker implements Runnable {
    private final EventBridgeListener listener;
    private final OperationalEventSink sink;

    public EventBridgeWorker(
            EventBridgeListener listener,
            OperationalEventSink sink) {
        this.listener = listener;
        this.sink = sink;
    }

    @Override
    public void run() {
        while (!Thread.currentThread().isInterrupted()) {
            try {
                OperationalEvent event = listener.take();
                sink.publish(event);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                break;
            } catch (Exception ex) {
                // Record failure, retry or dead-letter by policy.
            }
        }
    }
}
~~~

Đây là skeleton minh họa, không phải một pipeline bền vững. Nếu publish thất bại, event đã bị lấy khỏi queue có thể mất. Muốn at-least-once cần durable storage, retry với acknowledgment và xử lý poison messages.

## 10. Delivery guarantees: hiểu đúng giới hạn của JMX

JMX notification thường mang tính runtime:

- Client chưa đăng ký thì có thể bỏ lỡ notification.
- Remote connection mất thì các event trong thời gian mất kết nối không có cơ chế replay mặc định.
- MBean unregister/replace thì subscription cũ có thể không còn.
- Callback hoặc queue có thể quá tải.
- Retry từ event sink có thể tạo bản ghi trùng.

Phân biệt:

| Yêu cầu | Thiết kế |
| --- | --- |
| Best effort | JMX listener + bounded queue + logging |
| Cần giảm duplicate | Event ID/idempotency key + deduplication |
| At-least-once tới sink | Durable queue/store + retry và ack |
| Cần audit không mất | Ghi business event bền vững trước khi phát JMX |
| Cần replay sau outage | Broker/event store có retention |
| Chỉ cần trạng thái | Metric/attribute và periodic polling |

Không thể có exactly-once end-to-end chỉ bằng một NotificationListener. Nếu yêu cầu cực kỳ quan trọng, nên để business service ghi transactional outbox và JMX chỉ là một tín hiệu quan sát bổ sung.

## 11. Idempotency và deduplication

Một notification có sequenceNumber, nhưng sequence thường thuộc emitter, không duy nhất trên toàn cluster và có thể reset khi JVM restart.

Có thể xây dedupe key từ:

~~~text
targetInstance
+ canonicalObjectName
+ emitterGeneration
+ notificationSequenceNumber
+ notificationType
~~~

Điều kiện: generation được quản lý ổn định và source không tái sử dụng sequence trong cùng generation. Nếu producer cung cấp event ID duy nhất và bền vững, ưu tiên xác minh và sử dụng ID đó.

Những nguyên nhân duplicate:

- Cùng listener đăng ký nhiều lần.
- Hai bridge cùng subscribe một target.
- Event publisher retry sau timeout.
- MBean phát lại cùng trạng thái.
- Reconnect/re-subscribe thực hiện sai.

Dedupe nên dùng storage có TTL hoặc giới hạn dung lượng. Một HashSet vô hạn sẽ làm tăng memory.

## 12. Gắn target identity

ObjectName chỉ duy nhất trong phạm vi một MBeanServer. Các JVM khác nhau có thể cùng ObjectName:

~~~text
checkout-a: com.example.orders:type=Queue,name=payments
checkout-b: com.example.orders:type=Queue,name=payments
~~~

Vì vậy operational event phải mang thêm target identity:

~~~text
service=checkout
environment=production
cluster=payments-east
instance=checkout-a
objectName=com.example.orders:type=Queue,name=payments
~~~

Không suy ra environment hoặc instance bằng cách parse message tự do của notification. Dùng deployment metadata hoặc cấu hình collector đáng tin cậy.

## 13. Event severity và correlation

Ví dụ policy:

| Notification type | Event type | Severity ban đầu |
| --- | --- | --- |
| queue.threshold | queue.backlog.high | warning |
| queue.recovered | queue.backlog.recovered | info |
| worker.failed | worker.failed | critical hoặc warning theo service |
| worker.restarted | worker.restarted | info |
| cache.refreshed | cache.refresh.completed | info |
| configuration.applied | config.applied | audit/info |

Một event severity không nhất thiết tạo alert ngay. Alerting engine có thể áp threshold duration, business impact và lịch sử recovery.

Dùng correlation key:

~~~text
environment + service + resource + issueType
~~~

để nhóm cảnh báo high và recovery. Nếu thiếu correlation, mỗi notification có thể tạo một incident riêng và không được đóng khi dịch vụ phục hồi.

## 14. Automation và phòng tránh feedback loop

Một event vận hành có thể mở runbook hoặc kích hoạt auto-remediation. Nhưng không nên phản ứng mù:

~~~text
queue backlog high -> clearQueue()
~~~

Hành động có thể xóa dữ liệu chưa xử lý. Một quy trình phù hợp có thể thu thập diagnostics, mở cảnh báo hoặc đề xuất tăng capacity sau khi xác minh.

Nếu có tự động hóa, cần:

1. Preconditions và scope rõ.
2. Authorization và approval khi cần.
3. Idempotency key và operation ID.
4. Cooldown, rate limit và retry giới hạn.
5. Audit về trigger, action và kết quả.
6. Timeout, circuit breaker, khả năng rollback.
7. Phòng tránh event do automation phát ra kích hoạt lại chính nó.

Ví dụ feedback loop:

~~~text
worker unhealthy
  -> automation.restartWorker
  -> worker restarting notification
  -> automation.restartWorker again
~~~

Cần phân biệt event types, state transition và cooldown để không lặp.

## 15. Security khi chuyển notification thành event

Notification có thể chứa thông tin vận hành nhạy cảm. Nên:

- Không forward toàn bộ userData không được kiểm soát.
- Whitelist fields và notification types.
- Giới hạn kích thước message, attributes và batch.
- Không lưu password, token, customer payload hoặc private key.
- Giữ source identity đáng tin cậy.
- Bảo vệ JMX remote bằng authentication, TLS, network ACL.
- Bảo vệ sink/broker bằng credential chỉ có quyền publish cần thiết.
- Không trao quyền invoke operation nguy hiểm cho bridge chỉ cần subscribe.

JMX management permissions và event broker permissions là hai ranh giới quyền riêng biệt.

## 16. Lifecycle, reconnect và re-subscribe

Khi MBean được unregister hoặc replace, listener có thể mất subscription. Remote JMX connector có thể mất kết nối. Bridge cần quản lý:

~~~text
CONNECTING -> SUBSCRIBED -> DISCONNECTED
      ^                         |
      +------ RECONNECT --------+
~~~

Quy trình:

1. Kết nối tới đúng MBeanServer.
2. Xác nhận ObjectName đang registered.
3. Đăng ký listener, lưu registration state.
4. Theo dõi connection notifications.
5. Reconnect có exponential backoff với jitter.
6. Query registry lại sau reconnect.
7. Re-subscribe idempotently.
8. Cleanup listener và connector khi shutdown.

MBeanServerDelegate có thể phát notification khi MBean được đăng ký/hủy đăng ký. Tuy nhiên những notification này không bền vững; sau reconnect vẫn phải đồng bộ trạng thái registry.

## 17. Observability cho chính bridge

Nên đo từng giai đoạn:

~~~text
jmx_notification_received_total
jmx_notification_filtered_total
jmx_notification_invalid_total
jmx_notification_enqueued_total
jmx_notification_dropped_total
operational_event_publish_success_total
operational_event_publish_failure_total
operational_event_queue_depth
operational_event_oldest_age_seconds
jmx_connector_reconnect_total
jmx_subscription_recovered_total
~~~

Đây là các metric gợi ý do ứng dụng triển khai, không phải metric mặc định của Spring.

Nếu received tăng nhưng published không tăng, điều tra queue, worker và sink. Nếu source phát nhưng received không tăng, kiểm tra listener registration, ObjectName, filter và connector.

## 18. Tình huống lỗi phổ biến

| Triệu chứng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Không thấy event | MBean không phát hoặc listener chưa đăng ký | Kiểm tra producer và ObjectName |
| MBeanInfo có notification nhưng không có event | Metadata không tự emit | Kiểm tra sendNotification |
| Listener nhận nhưng broker không có | Queue đầy/publish thất bại | Metrics, retry/dead-letter |
| Sau deploy mất event | MBean thay thế hoặc context restart | Re-subscribe |
| Event trùng | Registration trùng hoặc publish retry | Dedupe và source generation |
| Alert quá nhiều | Phát event mỗi lần metric thay đổi | State transition/throttle |
| Incident không đóng | Recovery event thiếu hoặc correlation sai | Đồng bộ event types/correlation key |
| Sai instance | Chỉ dùng ObjectName | Thêm target identity |
| Callback làm chậm ứng dụng | I/O blocking | Bounded async queue |
| Memory tăng liên tục | Unbounded queue/map | Capacity và TTL |
| Tự động hóa lặp | Event/action loop | Cooldown và state machine |
| Lộ dữ liệu | Forward payload nguyên bản | Validate, redact và size limit |

## 19. Kiểm thử

Một integration test nên bao gồm:

1. Tạo MBeanServer riêng bằng MBeanServerFactory.newMBeanServer().
2. Đăng ký TestEmitter có hỗ trợ notification.
3. Tạo listener/normalizer/sink giả.
4. Đăng ký listener với ObjectName và filter phù hợp.
5. Gọi MBean operation phát notification.
6. Chờ event bằng latch hoặc cơ chế hữu hạn.
7. Assert eventType, resource, instance và payload.
8. Thử unknown type, invalid userData và queue đầy.
9. Thử thay MBean và re-subscribe.
10. Thử connection failure và sink publish failure.
11. Cleanup listener/MBean/worker.

Test sink giả:

~~~java
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

public final class RecordingEventSink implements OperationalEventSink {
    private final List<OperationalEvent> events =
        new CopyOnWriteArrayList<>();

    @Override
    public void publish(OperationalEvent event) {
        events.add(event);
    }

    public List<OperationalEvent> events() {
        return events;
    }
}
~~~

Một test chỉ xác nhận method handleNotification được gọi là chưa đủ. Nên kiểm tra event đã được normalize và publish theo schema mong đợi.

## 20. Khi nào dùng nguồn sự kiện khác?

| Nhu cầu | Lựa chọn |
| --- | --- |
| Tín hiệu quản trị best-effort | JMX notification bridge |
| Cần metric tổng hợp | Micrometer/Actuator metrics |
| Cần audit không mất | Durable event log/outbox |
| Cần replay sau outage | Message broker có retention |
| Cần tracking operation dài | Operation ID + trạng thái MBean |
| Cần workflow phê duyệt | Incident/runbook platform |
| Cần tương thích nhiều language | Schema độc lập với JMX |
| Cần thông tin hiện trạng | Getter JMX attribute/polling |

Dùng JMX notification đúng mục đích giúp giảm tải và tránh biến kênh quản trị runtime thành message broker không có khả năng lưu bền.

## 21. Checklist production

1. Notification types và schema đã định nghĩa rõ?
2. Producer phát theo state transition thay vì mọi metric change?
3. Source ObjectName và target JVM được xác thực?
4. Schema operational event có versioning?
5. Payload được whitelist và giới hạn kích thước?
6. Callback không block network I/O?
7. Buffer có capacity và overload policy?
8. Publish failure có cơ chế retry/dead-letter đúng yêu cầu?
9. Có event ID/dedupe phù hợp?
10. Alert correlation và recovery event đúng?
11. Auto-remediation có guardrails/cooldown/audit?
12. Remote JMX và sink đều có security?
13. Bridge có reconnect/re-subscribe?
14. Có metrics từng giai đoạn?
15. Có integration test, overload test và failure test?
16. Có tài liệu phân biệt best-effort và durable delivery?

## 22. Câu hỏi tự kiểm tra

**1. JMX notification có phải operational event hoàn chỉnh không?** Không. Cần chuẩn hóa type, source, severity, service, instance và payload.

**2. Có nên tạo incident cho mọi notification không?** Không. Cần alert policy và correlation.

**3. Vì sao callback không nên gọi API bên ngoài trực tiếp?** Vì network I/O có thể block và làm chậm emitter.

**4. Sequence number có là event ID toàn cục?** Không. Nó có thể lặp lại giữa emitter và sau restart.

**5. JMX notification có replay sau disconnect?** Không mặc định. Nếu cần, dùng nguồn sự kiện bền vững.

**6. Khi nào cần transactional outbox?** Khi sự kiện quan trọng phải không mất, có thể retry/replay.

**7. Vì sao cần target instance?** ObjectName chỉ duy nhất trong một MBeanServer, không phải toàn cluster.

**8. Automation an toàn cần gì?** Preconditions, authorization, idempotency, cooldown, retry giới hạn và audit.

## 23. Tổng kết

Chuyển JMX notification thành operational event là cách kết nối quản trị JVM với observability và automation.

Thiết kế tốt cần normalizer schema rõ, source identity đáng tin cậy, callback nhẹ, queue bounded, xử lý drop/retry, alert correlation, bảo mật, deduplication và reconnect. Với sự kiện bắt buộc lưu bền, business event store hoặc outbox phải là nguồn dữ liệu chính; JMX notification chỉ nên là tín hiệu bổ trợ.

**Đẩy notification thành sự kiện vận hành không đồng nghĩa đẩy nguyên dữ liệu JMX lên broker. Điều quan trọng là một hợp đồng sự kiện có ý nghĩa, có kiểm soát và phù hợp yêu cầu delivery.**

### Tài liệu tham khảo

- Spring Framework Reference — JMX notifications: https://docs.spring.io/spring-framework/reference/integration/jmx/notifications.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring API — NotificationPublisher: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/notification/NotificationPublisher.html
- Spring API — NotificationListenerBean: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/NotificationListenerBean.html
- Java SE API — Notification: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/Notification.html
