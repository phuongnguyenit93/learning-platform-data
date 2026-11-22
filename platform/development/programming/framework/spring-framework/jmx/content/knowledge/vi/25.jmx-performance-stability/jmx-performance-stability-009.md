# Xử lý lỗi listener để không làm hỏng nguồn phát trong Spring Framework JMX

## 1. Mục tiêu

JMX notification cho phép MBean gửi sự kiện quản trị đến một hoặc nhiều `NotificationListener`. Spring Framework tích hợp JMX qua `MBeanExporter`, `NotificationPublisherAware` và `NotificationPublisher`; tuy nhiên phía nhận thông báo thường là code ứng dụng hoặc JMX client được đăng ký trên `MBeanServer`.

Trong thực tế, listener có thể gặp lỗi parse dữ liệu, lỗi mạng, timeout, lỗi ghi log, lỗi truy cập database hoặc lỗi do thao tác nghiệp vụ bất ngờ. Nếu không được cô lập, hành vi của listener có thể làm giảm hiệu năng, cản trở thread gửi sự kiện, tạo vòng lặp lỗi hoặc khiến ứng dụng thiếu ổn định.

**Mục tiêu thiết kế:** một listener không đáng tin cậy hoặc hoạt động chậm không được phép làm hỏng luồng nghiệp vụ của nguồn phát; đồng thời hệ thống vẫn phải quan sát được lỗi, không che giấu hoàn toàn sự cố.

Những vấn đề cần hiểu:

- Ranh giới giữa MBean publisher, JMX broadcaster, MBeanServer và listener.
- Ảnh hưởng của exception hoặc blocking trong callback `handleNotification`.
- Vì sao `try/catch` ở listener không thay thế thiết kế bất đồng bộ.
- Cách xử lý notification bằng bounded queue, worker thread và chính sách overload.
- Cách quản lý registration/unregistration của listener, tránh memory leak.
- Phân biệt best-effort notification với hệ thống message delivery có cam kết.

## 2. Luồng phát notification trong Spring JMX

```text
Business service
    |
    | domain state change
    v
Spring-managed MBean
    |
    | NotificationPublisherAware
    v
NotificationPublisher.sendNotification(event)
    |
    v
JMX broadcaster / MBeanServer
    |
    +----> Listener A: xử lý nhanh
    |
    +----> Listener B: bị lỗi
    |
    +----> Listener C: xử lý chậm
    v
Continuity of publishing and business processing
```

JMX `NotificationListener` có callback:

```java
import javax.management.Notification;
import javax.management.NotificationListener;

public final class ExampleListener implements NotificationListener {
    @Override
    public void handleNotification(
            Notification notification, Object handback) {
        // Xử lý sự kiện.
    }
}
```

Callback này thường được gọi trên thread do JMX broadcaster hoặc hệ thống notification dispatch quản lý. **Đừng giả định mọi triển khai, local/remote connector và executor đều có cùng mô hình threading.** Có broadcaster thực hiện dispatch đồng bộ trên thread gửi; cũng có cấu hình dùng executor để chuyển việc gọi callback sang thread khác.

Do đó, để bảo vệ nguồn phát, phải thiết kế listener **nhanh, bounded, chịu lỗi** thay vì chỉ hy vọng framework sẽ nuốt ngoại lệ hoặc luôn chạy bất đồng bộ.

## 3. Điều gì có thể xảy ra khi listener lỗi?

| Lỗi listener | Tác động có thể có | Biện pháp |
| --- | --- | --- |
| `RuntimeException` khi parse payload | Callback thất bại; có thể ảnh hưởng dispatch tùy broadcaster | Bắt lỗi tại biên listener, ghi metric/log an toàn |
| Gọi database hoặc HTTP API lâu | Thread dispatch bị chiếm dụng, backlog hoặc tăng latency | Chỉ enqueue bounded, xử lý worker riêng |
| Log lỗi bằng payload nhạy cảm | Lộ secrets/PII trong log | Log type, safe event ID, error category |
| Gửi lại notification ngay trong listener | Recursion/event storm | Không phát lặp trực tiếp; giới hạn retry/debounce |
| Lỗi tạm thời nhưng retry vô hạn | Queue đầy, CPU hoặc network quá tải | Retry có giới hạn, backoff, DLQ khi thực sự cần |
| Listener bị đăng ký nhiều lần | Cùng event xử lý lặp, leak | Ownership rõ, register một lần và cleanup |
| Không unregister khi context đóng | Retained bean/classloader/threads | `removeNotificationListener` theo lifecycle |
| Payload quá lớn | Serialization, memory, GC pressure | Small schema và size limits |

**Không có bảo đảm chung rằng exception từ listener sẽ luôn được chuyển tới thread gọi `sendNotification`, hoặc luôn bị bỏ qua.** Điều đó phụ thuộc broadcaster/connector/executor cụ thể. Dù framework có bắt ngoại lệ, một listener chậm vẫn có thể gây tác động tới throughput hoặc memory.

## 4. Quy tắc quan trọng: exception boundary trong callback

Một listener đơn giản phải coi payload là dữ liệu bên ngoài ranh giới tin cậy của nó:

```java
import javax.management.Notification;
import javax.management.NotificationListener;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class SafeNotificationListener
        implements NotificationListener {

    private static final Logger log =
        LoggerFactory.getLogger(SafeNotificationListener.class);

    @Override
    public void handleNotification(
            Notification event, Object handback) {
        try {
            process(event);
        } catch (RuntimeException error) {
            String type = event == null ? "unknown" : event.getType();
            log.warn("Cannot process JMX event type={}", type, error);
        }
    }

    private void process(Notification event) {
        if (event == null) {
            throw new IllegalArgumentException("event missing");
        }
        // Logic nhận và xử lý event.
    }
}
```

Bắt `RuntimeException` tại biên callback giúp các lỗi phổ biến của logic xử lý không lan ngược ra JMX dispatch. Đây là **lớp phòng vệ đầu tiên**, không phải giải pháp đầy đủ cho listener gọi tác vụ chậm.

Không nên bắt `Throwable` một cách mù quáng rồi coi mọi lỗi là có thể bỏ qua. Các lỗi nghiêm trọng của JVM như `OutOfMemoryError` không phải loại lỗi có thể hồi phục an toàn bằng một dòng log.

Nếu callback xử lý một số lỗi checked exception từ I/O, nên bắt và chuyển thành kết quả thất bại trong logic nghiệp vụ thay vì để cơ chế `handleNotification` nhận ngoại lệ không xử lý.

## 5. Callback nên nhanh và có giới hạn

Anti-pattern:

```java
@Override
public void handleNotification(Notification event, Object handback) {
    externalApi.postEvent(event);        // Có thể timeout 30 giây.
    database.saveEvent(event);           // Có thể chậm hoặc lock.
    reportGenerator.generate(event);     // Có thể tốn CPU.
}
```

Nếu callback chạy đồng bộ hoặc pool notification có ít worker, ba thao tác này có thể làm nghẽn dispatch. Khi listener chậm hơn tốc độ phát, backlog tăng và gây áp lực lên memory.

Thay vì xử lý sâu trong callback, nên:

1. Xác minh event type và payload ở mức tối thiểu.
2. Chuyển thành DTO nhỏ không chứa references tới object graph lớn.
3. Đưa vào một hàng đợi **có giới hạn dung lượng**.
4. Kết thúc callback nhanh.
5. Cho worker riêng xử lý I/O, retry và metric.

Quan trọng: hàng đợi bounded cần chính sách khi đầy. Nếu không, chính việc cố bảo vệ nguồn phát có thể tạo memory leak hoặc blocking.

## 6. Ví dụ listener dùng bounded queue

Ví dụ minh họa một listener local xử lý event bên ngoài callback:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.atomic.AtomicLong;
import javax.management.Notification;
import javax.management.NotificationListener;

public final class QueueingNotificationListener
        implements NotificationListener {

    public record EventSummary(
        String type, long sequence, long timestamp, String message) {}

    private final BlockingQueue<EventSummary> queue =
        new ArrayBlockingQueue<>(1024);
    private final AtomicLong dropped = new AtomicLong();

    @Override
    public void handleNotification(
            Notification event, Object handback) {
        if (event == null) {
            dropped.incrementAndGet();
            return;
        }
        try {
            EventSummary summary = new EventSummary(
                event.getType(),
                event.getSequenceNumber(),
                event.getTimeStamp(),
                safeMessage(event.getMessage())
            );
            if (!queue.offer(summary)) {
                dropped.incrementAndGet();
            }
        } catch (RuntimeException ex) {
            dropped.incrementAndGet();
        }
    }

    private String safeMessage(String value) {
        if (value == null) return "";
        return value.length() <= 120 ? value : value.substring(0, 120);
    }

    public EventSummary take() throws InterruptedException {
        return queue.take();
    }

    public long droppedCount() {
        return dropped.get();
    }
}
```

Đây là một ví dụ **best-effort**. `offer` không chờ khi queue đầy, nên nguồn phát không bị block bởi việc enqueue. Tuy nhiên sự kiện có thể bị bỏ. Trong production, `safeMessage` chỉ giới hạn độ dài, **không tự redaction secrets**; tốt nhất publisher đã tạo payload sạch, và listener chỉ giữ những trường thực sự cần.

Worker riêng có thể đọc từ `take()` rồi gọi dịch vụ xử lý:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

ExecutorService worker = Executors.newSingleThreadExecutor();
worker.submit(() -> {
    while (!Thread.currentThread().isInterrupted()) {
        try {
            var event = listener.take();
            processor.process(event);
        } catch (InterruptedException stop) {
            Thread.currentThread().interrupt();
        } catch (RuntimeException processingError) {
            failureMetrics.increment();
            // Ghi log thông tin an toàn; không dump raw payload.
        }
    }
});
```

Ví dụ giả định có `listener`, `processor`, `failureMetrics` do ứng dụng quản lý. Thread worker phải được shutdown ở lifecycle phù hợp. Không tạo một thread cho **mỗi** notification; đó là anti-pattern dẫn đến cạn thread.

## 7. Chính sách khi queue đầy

Các chiến lược phổ biến:

| Chiến lược | Ý nghĩa | Rủi ro |
| --- | --- | --- |
| Drop newest | Bỏ event vừa nhận, giữ backlog cũ | Có thể mất sự kiện mới quan trọng |
| Drop oldest | Bỏ event cũ, ưu tiên thông tin mới | Có thể bỏ lịch sử cần điều tra |
| Coalesce | Gộp nhiều event cùng loại hoặc cùng resource | Mất độ chi tiết theo từng sự kiện |
| Bounded wait | Chờ một khoảng ngắn rồi bỏ/ghi metric | Vẫn có thể tăng latency của callback |
| Escalate | Cảnh báo tỷ lệ drop vượt ngưỡng | Phải tránh chính cảnh báo gây event storm |

Chính sách nên phù hợp ý nghĩa notification. Với trạng thái chỉ cần “có sự kiện mới, hãy đọc trạng thái hiện tại”, coalesce thường hợp lý. Với audit hoặc workflow cần bảo đảm từng event, **không nên dùng JMX notification làm nguồn dữ liệu duy nhất**; cần message broker hoặc audit store có durable delivery.

Mọi chính sách cần có metric như `notification_received_total`, `notification_processed_total`, `notification_dropped_total`, `notification_processing_failures_total`, `queue_depth` để biết khả năng chịu tải.

## 8. Không để listener làm thay đổi state của publisher theo vòng lặp

Nguy cơ khác là feedback loop:

```text
MBean phát notification queue.threshold
          |
          v
Listener nhận và gọi JMX operation
          |
          v
Operation thay đổi state và phát cùng notification
          |
          v
Listener lại gọi operation ...
```

Phải tách notification là **tín hiệu quan sát** với hành động điều khiển có điều kiện. Nếu listener muốn tự động xử lý, nên:

- Đọc state hiện tại trước khi hành động.
- Áp dụng idempotency và cooldown.
- Đánh dấu trạng thái đang xử lý hoặc dùng circuit breaker.
- Giới hạn số lần retry và số operation trong một cửa sổ thời gian.
- Không xử lý lại cùng sequence/resource khi chính nó vừa gây ra phản hồi.

Không gọi operation nguy hiểm ngay trong `handleNotification` mà không có kiểm soát truy cập và giới hạn tài nguyên.

## 9. Cô lập listener bằng adapter riêng

Một cách tổ chức code:

```text
JMX NotificationListener (biên nhận event)
      |
      v
Validator + sanitizer
      |
      v
Bounded queue
      |
      v
Worker / processor
      |
      +--> metrics/logging
      +--> retry policy
      +--> domain action nếu thực sự cần
```

Listener không nên giữ các database transactions lâu, lock domain hoặc state không thread-safe. Nó nên đơn giản để có thể được gọi đồng thời mà không corrupt state.

Với event payload được nhận từ remote JMX, không giả định đối tượng userData được tin cậy. Tránh deserialize hoặc cast các class application-specific không kiểm soát; ưu tiên primitive, String đã sanitize hoặc JMX Open Types.

## 10. Publisher cũng cần bảo vệ đường phát

Việc listener phải chịu lỗi không có nghĩa broadcaster/publisher có thể phát sự kiện vô hạn. Ở phía nguồn phát, nên xây đường gửi riêng và tránh đưa logic JMX vào transaction nghiệp vụ quan trọng.

```java
import javax.management.Notification;
import org.springframework.jmx.export.notification.NotificationPublisher;

public final class SafeEventPublisher {
    private final NotificationPublisher publisher;

    public SafeEventPublisher(NotificationPublisher publisher) {
        this.publisher = publisher;
    }

    public void trySend(Notification notification) {
        try {
            publisher.sendNotification(notification);
        } catch (RuntimeException publishingError) {
            // Log và metric lỗi gửi; không bao gồm raw notification payload.
            // Chính sách business có thể chọn không fail giao dịch chính.
        }
    }
}
```

Đây là minh họa về **failure boundary** ở application layer, không nên mặc định mọi lỗi JMX cần bị bỏ qua. Với một event bắt buộc cho business audit, phải có cơ chế delivery bền vững riêng thay vì nuốt lỗi.

Spring `NotificationPublisherAware` được sử dụng khi exporter cấp publisher cho bean:

```java
import org.springframework.jmx.export.notification.NotificationPublisher;
import org.springframework.jmx.export.notification.NotificationPublisherAware;

public class WorkerManagement implements NotificationPublisherAware {
    private volatile NotificationPublisher publisher;

    @Override
    public void setNotificationPublisher(NotificationPublisher publisher) {
        this.publisher = publisher;
    }

    public void onDegraded() {
        NotificationPublisher current = publisher;
        if (current == null) return;
        // Tạo Notification và chuyển qua safe publishing wrapper.
    }
}
```

Publisher có thể chưa được inject khi bean chưa export hoặc không còn hợp lệ sau khi unregister. Cần xử lý lifecycle và không dùng global static reference không được dọn dẹp.

## 11. Listener local và remote khác nhau như thế nào?

**Local listener** có thể được đăng ký trực tiếp qua `MBeanServer.addNotificationListener`. Tùy broadcaster, callback có thể chạy ngay trên thread dispatch hoặc theo executor. Một callback chậm có thể làm giảm throughput local và gián tiếp ảnh hưởng nguồn phát.

**Remote JMX client** thường nhận notification qua connector và có các thread/pool chuyển tiếp riêng. Lỗi, timeout hoặc mất mạng của client có thể tác động tới đường truyền/queue; không nên coi remote notification là cơ chế đảm bảo exactly-once.

Các đặc điểm quan trọng:

- Thứ tự callback/notifications không nhất thiết được bảo đảm tuyệt đối qua mọi listener và mọi kết nối.
- Client có thể đăng ký sau khi event đã phát, dẫn tới missed events.
- Server hoặc connector restart có thể làm mất subscription.
- Listener không được phép giữ reference ứng dụng sau khi context đã đóng.
- Retry ở phía client phải xét tính idempotent của action nếu notification dẫn tới JMX operation.

Đừng bắt lỗi bên listener rồi tuyên bố cả pipeline trở thành durable. Cần xác định reliability contract phù hợp.

## 12. Đăng ký listener và cleanup đúng lifecycle

Ví dụ local JMX:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.NotificationListener;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example.jobs:type=WorkerPool,name=Main"
);

NotificationListener listener = new SafeNotificationListener();
server.addNotificationListener(name, listener, null, null);

try {
    // Ứng dụng nhận notifications trong vòng đời hoạt động.
} finally {
    server.removeNotificationListener(name, listener);
}
```

Không nên tạo listener trong một method ngắn rồi lập tức thoát `finally` nếu thật sự muốn subscribe liên tục. Spring-managed listener có thể đăng ký lúc context startup và unregister trong `@PreDestroy` hoặc callback lifecycle tương ứng.

Trong shared JVM/container, không unregister hoặc replace MBean không thuộc quyền sở hữu chỉ để cleanup listener. Chỉ remove đúng listener mà component của mình đã đăng ký.

## 13. NotificationFilter giúp giảm event không liên quan

```java
import javax.management.NotificationFilterSupport;

NotificationFilterSupport filter = new NotificationFilterSupport();
filter.enableType("com.example.jobs.pool.degraded");
server.addNotificationListener(name, listener, filter, null);
```

Filter giúp giảm số callback không liên quan, nhưng không thay thế permission checks. Với nhiều loại event và nhiều MBean, nên quy định subscription theo nhu cầu vận hành; tránh listener wildcard xử lý mọi type, mọi source rồi ghi raw payload vào log.

Nếu nhận event từ nhiều MBean, nên phân biệt bằng ObjectName và type trong hệ thống consumer. Không dùng `Notification.getSource()` như một opaque Java object có thể cast thẳng sang implementation bean trong mọi local/remote trường hợp.

## 14. Retry có kiểm soát: backoff, idempotency, circuit breaker

Nếu worker xử lý event cần gọi dịch vụ bên ngoài, lỗi tạm thời là bình thường. Nhưng retry vô hạn gây quá tải. Một chính sách hợp lý có thể gồm:

1. Phân loại lỗi retryable và non-retryable.
2. Giới hạn số lần thử cho mỗi item.
3. Exponential backoff với jitter để tránh thundering herd.
4. Timeout rõ ràng khi gọi I/O.
5. Circuit breaker khi dependency đang lỗi diện rộng.
6. Ghi failure metric và gửi cảnh báo riêng khi cần.
7. Nếu việc mất event là không chấp nhận được, chuyển sang durable queue thay vì cố biến bộ nhớ JMX listener thành message broker.

Giả sử một event `queue.degraded` chỉ có ý nghĩa yêu cầu kiểm tra state; worker có thể bỏ qua event cũ sau khi trạng thái đã hồi phục. Một event audit mang tính pháp lý thì không phù hợp với cơ chế best-effort này.

## 15. Quan sát lỗi nhưng không tạo log storm

Không nên log full stack trace của cùng một lỗi hàng nghìn lần mỗi giây. Thay vào đó:

- Tăng counter theo error category.
- Log gộp/throttle theo cửa sổ thời gian.
- Ghi sampled stack traces khi cần chẩn đoán.
- Theo dõi queue depth, oldest event age, drop rate, processing latency.
- Cảnh báo trên tỷ lệ lỗi kéo dài, không phải mọi event đơn lẻ.
- Không log secret, token hoặc dữ liệu cá nhân trong message/userData.

Ví dụ metric logic:

```text
jmx_listener_events_received_total
jmx_listener_events_processed_total
jmx_listener_events_dropped_total
jmx_listener_errors_total{category="parse"}
jmx_listener_queue_depth
jmx_listener_processing_duration_seconds
```

Nếu dùng Micrometer trong Spring Boot, có thể công bố metrics qua Actuator hoặc registry phù hợp; tránh gắn sequence number, email, userId hay ObjectName động quá chi tiết làm metric tags để không tăng cardinality và lộ dữ liệu.

## 16. Kiểm tra khả năng chịu lỗi bằng các tình huống thực tế

Với một môi trường test, có thể kiểm chứng hành vi bằng các loại listener:

| Tình huống | Điều cần quan sát |
| --- | --- |
| Listener ném RuntimeException | Nguồn phát có tiếp tục hoạt động không; exception có được ghi nhận không |
| Listener ngủ lâu hơn thời gian phát event | Latency publisher, backlog, CPU, queue depth |
| Payload sai schema | Event bị loại hay đưa vào xử lý lỗi; không phá loop |
| Queue đầy | Có drop policy/metric, không block vô hạn |
| Nhiều listener cùng đăng ký | Một listener lỗi không khiến listener khác ngừng nhận ngoài dự kiến |
| Unregister/re-register target MBean | Listener có cleanup/resubscribe đúng không |
| Remote client mất kết nối | Server không tích lũy backlog vô hạn, client có reconnect policy |
| Lượng event tăng đột biến | Bounded resource, rate-limit hoặc coalescing có hiệu quả |

Việc test nên quan sát cả **luồng nghiệp vụ** và **notification delivery**. Có thể các notification bị mất trong tình huống lỗi nhưng business transaction vẫn phải hoạt động — đây là một trade-off hợp lý nếu notification chỉ phục vụ monitoring.

## 17. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Gọi sendNotification làm business thread chậm | Listener đồng bộ hoặc publisher path bị blocking | Tách event path, bounded queue và executor |
| Một listener lỗi khiến dispatch không ổn định | Callback ném ngoại lệ không kiểm soát | Catch ở listener boundary, đếm lỗi |
| OOM sau khi tăng notification rate | Queue/listener tasks không bounded | Giới hạn capacity, drop/coalesce policy |
| Mất event khi queue đầy | Best-effort design | Ghi metric, xem lại throughput và reliability contract |
| Listener lặp event mãi | Feedback loop gọi operation/phát event | Idempotency, debounce, cooldown |
| Notification được nhận nhiều lần | Đăng ký trùng listener hoặc connector reconnect duplicate | Quản lý registration, dedupe theo source/sequence khi cần |
| Không nhận event sau redeploy | Listener chưa resubscribe hoặc MBean ObjectName đổi | Lifecycle/reconnect logic và ổn định naming |
| Shutdown treo vì worker | Blocking I/O thiếu timeout, executor không shutdown | Timeout, interruption và graceful shutdown |
| Log chứa payload nhạy cảm | In notification/userData thô | Safe fields, redaction và sampling |

## 18. Nguyên tắc thiết kế kết luận

```text
Business event
    |
    v
Spring JMX publisher
    |
    v
JMX broadcaster
    |
    v
Thin NotificationListener
    |
    +-- validate/sanitize
    +-- bounded enqueue
    +-- catch RuntimeException
    |
    v
Background processor
    |
    +-- bounded retry + timeout
    +-- metrics, sampled logging
    +-- graceful shutdown
```

**Ghi nhớ:** xử lý lỗi listener để không làm hỏng nguồn phát là vấn đề **failure isolation và backpressure**, không chỉ là thêm `try/catch`. Giữ callback ngắn và an toàn, sử dụng bounded resources, tách I/O chậm ra worker, hạn chế retry, quản lý subscription lifecycle và theo dõi lỗi bằng metrics. JMX notification phù hợp làm tín hiệu quan sát best-effort; nếu hệ thống cần guaranteed delivery hoặc audit từng event, hãy dùng kênh messaging/audit chuyên dụng.
