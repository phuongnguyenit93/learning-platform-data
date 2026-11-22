# Notification dồn dập và áp lực lên listener trong Spring Framework JMX

## 1. Vấn đề thực tế và mục tiêu

JMX Notification là cơ chế phát tín hiệu quản trị khi trạng thái một MBean thay đổi. Ví dụ, một MBean trong ứng dụng Spring có thể phát notification khi kết nối bị lỗi, hàng đợi vượt ngưỡng, job hoàn tất hoặc cache được reset. Ở tải thấp, notification listener thường hoạt động nhẹ nhàng. Nhưng khi lỗi xảy ra liên tiếp hoặc hệ thống có hàng nghìn sự kiện mỗi giây, **notification dồn dập** có thể trở thành nguồn gây chậm chính ứng dụng đang cần giám sát.

Các biểu hiện điển hình:

- Method phát notification trở nên chậm vì listener xử lý đồng bộ.
- Số phần việc chờ trong executor tăng liên tục.
- Callback xử lý chậm hơn tốc độ phát, dẫn đến backlog và tăng memory.
- Lỗi quá tải làm notification bị từ chối, bỏ qua hoặc xử lý muộn.
- Khi remote JMX mất kết nối, client không thể giả định mọi notification đều được nhận lại.
- Một notification quan trọng bị chìm giữa hàng nghìn thông báo lặp.
- Metrics, logs, alerts cùng tạo thêm tải vào thời điểm hệ thống gặp sự cố.

Bài học này hướng dẫn nhận diện và kiểm soát áp lực notification theo tư duy hiệu năng: tính tốc độ, giới hạn tài nguyên, phân loại sự kiện, giảm nhiễu, thiết kế listener không block và xác minh bằng kiểm thử.

Sau bài học, bạn có thể phân biệt đồng bộ/bất đồng bộ, đo độ trễ callback, ước lượng backlog, cấu hình bounded executor, chọn chính sách quá tải và thiết kế cơ chế khôi phục trạng thái sau khi mất thông báo.

## 2. Mô hình notification pipeline

```text
                   Application / MBean
                     event producer
                           |
                   create Notification
                           |
                    sendNotification()
                           |
                +----------+----------+
                |                     |
         Synchronous path       Asynchronous path
                |                     |
          listener callback      Executor / task queue
                |                     |
          xử lý trực tiếp         listener callback
                |                     |
                +----------+----------+
                           |
                    logs / metrics /
                    dashboard / actions
```

Với Spring JMX, nguồn phát có thể sử dụng `NotificationPublisherAware` và `NotificationPublisher`; listener có thể được đăng ký qua `NotificationListenerBean` hoặc trực tiếp qua JMX API. Spring hỗ trợ wiring, nhưng **việc dùng Spring bean không tự tạo backpressure hay giới hạn callback concurrency**.

Một kiến trúc notification ổn định cần quyết định rõ nơi nào có queue, ai sở hữu executor, giới hạn backlog là bao nhiêu, sự kiện nào có thể mất, và xử lý thế nào khi vượt giới hạn.

## 3. Notification không phải message queue bền vững

Một sai lầm thường gặp là xem `NotificationBroadcasterSupport` hoặc remote JMX notification như hệ thống event streaming có đảm bảo lưu trữ.

JMX notification có các đặc điểm cần nhớ:

1. Dùng để truyền thông tin quản trị, không mặc định có persistence.
2. Không có durable subscriber offset như message broker.
3. Không cung cấp exactly-once processing cho listener.
4. Không mặc định có retry bền vững khi listener/connector gặp sự cố.
5. Không đảm bảo remote clients nhận mọi notification sau disconnect.
6. Thứ tự xử lý hoàn tất phụ thuộc dispatcher và executor.
7. Có thể query lại trạng thái hiện tại qua MBean attributes sau khi client reconnect.

Nếu notification là nguồn dữ liệu bắt buộc để cập nhật số dư, đơn hàng hoặc audit không được mất, hãy dùng cơ chế messaging/event log đáp ứng yêu cầu. JMX notification nên được xem là **tín hiệu quan sát**, còn trạng thái quản trị authoritative nằm ở MBean attributes, database hoặc service phù hợp.

## 4. Định lượng áp lực bằng tốc độ phát và xử lý

Giả sử nguồn phát `λ` notification/giây và listener xử lý `μ` notification/giây.

Khi chỉ có một worker:

```text
λ = 500 notifications/s
μ = 200 notifications/s

Backlog tăng xấp xỉ:
  500 - 200 = 300 notifications/s
```

Sau 10 giây quá tải liên tục, queue có thể tích lũy khoảng 3.000 phần việc (nếu không giới hạn, không drop và tốc độ giữ nguyên).

Với `c` workers tương đương có throughput mỗi worker là `μ`, công suất gần đúng là `c × μ`; khi `λ >= c × μ` trong thời gian dài, hàng chờ có xu hướng tăng. Đây là mô hình sơ bộ vì xử lý thực tế có phân phối thời gian, lock contention, GC và những lớp queue khác nhau.

| Ký hiệu | Ý nghĩa |
|---|---|
| `λ` | Tốc độ notification đến |
| `μ` | Throughput xử lý mỗi worker |
| `c` | Số workers xử lý |
| `Q` | Số task đang chờ |
| `W` | Thời gian một task đợi và xử lý |
| `L` | Số task trung bình đang ở hệ thống |

Trong điều kiện hệ thống ổn định, Little's Law `L = λ × W` giúp liên hệ mức concurrency, thông lượng và latency. Không áp dụng công thức như bảo đảm khi queue liên tục quá tải và trạng thái chưa ổn định.

### 4.1. Tính dung lượng queue có mục đích

Nếu producer có thể bùng lên 800 notifications/s trong 5 giây, còn 4 workers xử lý tổng cộng 600 notifications/s, backlog tăng gần `(800 - 600) × 5 = 1.000` notifications. Queue 100 entries sẽ đầy nhanh; queue 100.000 entries có thể che lỗi lâu nhưng dùng nhiều RAM.

Queue nên được chọn dựa trên:

- Burst size và thời gian burst có thể chấp nhận.
- Kích thước trung bình và cực đại của task/payload.
- Time budget trước khi notification trở nên lỗi thời.
- Khả năng tăng/giảm throughput thực tế.
- Policy khi queue đầy: drop, reject, coalesce, block hoặc chuyển sang hệ thống bền vững.

**Không dùng unbounded queue như biện pháp xử lý overload mặc định.**

## 5. Synchronous listener: bottleneck ngay trên thread phát

JDK `NotificationBroadcasterSupport` mặc định có thể dispatch tới listener trên đường gọi `sendNotification` nếu không cấu hình executor.

```java
import javax.management.Notification;
import javax.management.NotificationBroadcasterSupport;
import javax.management.NotificationListener;
import java.util.concurrent.atomic.AtomicLong;

public class WorkerEmitter extends NotificationBroadcasterSupport {
    private final AtomicLong sequence = new AtomicLong();

    public void event(String type) {
        sendNotification(new Notification(
            type, this, sequence.incrementAndGet(),
            System.currentTimeMillis(), "worker event"));
    }
}
```

Listener cố tình chậm:

```java
NotificationListener slowListener = (notification, handback) -> {
    try {
        Thread.sleep(100); // Chỉ mô phỏng trong lab.
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
    }
};
```

Khi callback chạy đồng bộ, một notification có thể mất ít nhất khoảng 100 ms cho listener này. Nguồn phát 100 events/s trên một thread sẽ nhanh chóng bị giới hạn bởi listener, chưa kể các listener khác.

### 5.1. Những hệ quả thường bị bỏ qua

- Notification phát từ JMX operation làm lời gọi `invoke` kéo dài.
- Notification phát trong `synchronized` block làm lock bị giữ lâu.
- Listener gọi lại cùng MBean có thể tạo reentrancy hoặc vòng chờ.
- Một listener gọi HTTP/database có thể làm chậm luồng nghiệp vụ.
- Tăng notification frequency có thể làm tăng log noise và GC pressure.

Một callback đồng bộ phù hợp khi xử lý rất nhẹ, ví dụ tăng counter hoặc ghi một state đơn giản. Nếu phải làm I/O hoặc xử lý dữ liệu nhiều, hãy dùng hàng chờ giới hạn.

## 6. Bất đồng bộ bằng Executor: có lợi nhưng không miễn phí

`NotificationBroadcasterSupport` có constructor nhận `Executor`. Một ví dụ:

```java
import javax.management.Notification;
import javax.management.NotificationBroadcasterSupport;
import java.util.concurrent.Executor;

public final class AsyncStatusEmitter
        extends NotificationBroadcasterSupport {

    public AsyncStatusEmitter(Executor executor) {
        super(executor);
    }

    public void changed(long sequence) {
        sendNotification(new Notification(
            "training.status.changed",
            this,
            sequence,
            System.currentTimeMillis()));
    }
}
```

Khi executor chấp nhận task, thread phát notification có thể tiếp tục mà không đợi callback hoàn tất. Tuy nhiên, nếu tốc độ phát cao hơn throughput xử lý, queue tích lũy và hệ thống vẫn quá tải.

### 6.1. Executor nhiều threads không bảo đảm thứ tự hoàn tất

```text
Notification #1 -> worker A (500 ms)
Notification #2 -> worker B (10 ms)

Kết quả:
  #2 hoàn tất trước #1
```

Nếu listener chỉ cập nhật counters độc lập, điều này có thể chấp nhận. Nếu state machine phụ thuộc sequence, cần thiết kế ordering theo resource hoặc kiểm tra version trước khi áp dụng event.

### 6.2. Một thread tuần tự hay pool nhiều threads?

| Phương án | Ưu điểm | Hạn chế |
|---|---|---|
| Dispatch đồng bộ | Đơn giản, ít queue | Block thread phát |
| Single-thread executor | Dễ giữ thứ tự submit | Throughput giới hạn |
| Fixed pool | Xử lý song song | Cần thread-safety, ordering |
| Bounded pool/queue | Giới hạn memory/concurrency | Cần overflow policy |
| Durable queue bên ngoài | Hỗ trợ persistence/retry | Hệ thống phức tạp hơn |

Không tăng threads vô hạn để chạy theo spike. Nếu callback chủ yếu đợi network, số workers có thể cao hơn CPU cores nhưng vẫn cần giới hạn connections và deadlines.

## 7. ThreadPoolExecutor có bounded queue

Ví dụ Spring `@Bean` sở hữu executor:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class NotificationExecutorConfig {

    @Bean(destroyMethod = "shutdown")
    public ThreadPoolExecutor jmxNotificationExecutor() {
        return new ThreadPoolExecutor(
            2,
            2,
            0,
            TimeUnit.MILLISECONDS,
            new ArrayBlockingQueue<>(256),
            runnable -> {
                Thread t = new Thread(runnable, "jmx-notification");
                t.setDaemon(false);
                return t;
            },
            new ThreadPoolExecutor.AbortPolicy());
    }
}
```

Với 2 workers và queue tối đa 256 tasks, executor không giữ vô hạn notification tasks. Khi queue đã đầy và workers bận, `AbortPolicy` ném `RejectedExecutionException`.

Cần **xác định rõ nơi xử lý rejection**. Một broadcaster gửi notification có thể gọi `executor.execute` trong quá trình dispatch; cách exception được xử lý có thể phụ thuộc implementation và vị trí dispatch. Không giả định mọi rejection đều được ghi log hoặc tự retry.

### 7.1. Policy khi queue đầy

- **Reject/alert:** loại bỏ việc tiếp nhận thêm task và ghi metric, phù hợp cho event có thể bỏ.
- **Drop newest:** giữ backlog cũ nhưng bỏ event vừa tới; có thể làm chậm việc nhận thông tin mới.
- **Drop oldest:** ưu tiên cập nhật mới, có ích cho snapshot state nhưng làm mất các chuyển trạng thái cũ.
- **Coalesce:** gộp nhiều event cùng resource/thông tin thành một tín hiệu.
- **CallerRunsPolicy:** caller trực tiếp chạy task khi bão hòa, tạo backpressure nhưng có thể khiến đường phát notification bị chặn.
- **Persist to durable queue:** phù hợp khi event không được phép mất; khi đó nên cân nhắc message broker thay JMX notification làm kênh dữ liệu chính.

Không chọn policy chỉ theo throughput benchmark; phải căn cứ **semantics của notification**.

## 8. Phân loại notification theo tầm quan trọng

Không phải mọi notification đều cần xử lý như nhau:

| Loại notification | Giá trị vận hành | Gợi ý |
|---|---|---|
| CPU/queue vượt ngưỡng liên tục | Thường là state có thể query | Debounce, coalesce |
| Worker chuyển RUNNING → PAUSED | Transition đáng chú ý | Giữ sequence/last state |
| Một task hoàn thành | Có thể rất nhiều | Tổng hợp thành counters |
| Lỗi critical lần đầu | Rất quan trọng | Alert + audit riêng |
| Lỗi lặp cùng nguyên nhân | Ít giá trị sau mẫu đầu | Rate-limit, group theo fingerprint |
| Heartbeat quá thường xuyên | Tín hiệu định kỳ | Sampling hoặc bỏ nếu attributes đủ |
| Dữ liệu nghiệp vụ không được mất | Nghiệp vụ quan trọng | Durable messaging, không JMX-only |

Một lỗi phổ biến là phát notification cho **mỗi request** hoặc **mỗi message**. JMX không phải high-volume event stream. Thường tốt hơn expose `RequestCount`, `ErrorRate`, `QueueDepth` làm MBean attributes/metrics, và chỉ phát notification khi trạng thái đáng chú ý thay đổi.

## 9. Debounce, throttle, sampling và coalescing

### 9.1. Debounce

Chỉ phát notification sau khi trạng thái duy trì đủ lâu, ví dụ queue depth vượt 1.000 trong 15 giây. Tránh bắn liên tục khi metric dao động quanh ngưỡng.

### 9.2. Throttle hoặc rate-limit

Cho phép tối đa N notifications mỗi khoảng thời gian, ví dụ 1 notification/10 giây cho cùng một resource và loại cảnh báo.

### 9.3. Sampling

Chỉ lấy mẫu một phần của nhóm event tần suất cao. Cách này chỉ phù hợp với telemetry có thể mất, không dùng cho trạng thái critical cần ghi nhận đầy đủ.

### 9.4. Coalescing

Nhiều notifications `queue.changed` trong một khoảng ngắn có thể gộp thành `queue.state.changed`; listener khi nhận đọc giá trị `QueueDepth` mới nhất từ MBean.

```text
10.000 queue.change events
            |
            v
      Coalescing window
            |
            v
      1 signal "changed"
            |
            v
Listener queries QueueDepth attribute
```

Điều này chuyển từ mô hình “mỗi thay đổi là một payload” sang mô hình “notification báo rằng cần refresh state”.

### 9.5. Cẩn thận với trạng thái chuyển tiếp

Nếu một sự kiện mang ý nghĩa transition không thể bỏ qua, chẳng hạn đổi trạng thái từ `RUNNING` sang `FAILED` rồi `RECOVERING`, việc gộp hết thành trạng thái hiện tại có thể làm mất lịch sử. Hãy phân tách **state snapshot** và **audit event**; dùng event log phù hợp cho loại thứ hai.

## 10. Ví dụ: giảm notification trùng theo khoảng thời gian

Một emitter có thể throttle tín hiệu “queue too deep”:

```java
import javax.management.Notification;
import javax.management.NotificationBroadcasterSupport;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;

public final class ThrottledQueueEmitter
        extends NotificationBroadcasterSupport {

    private final AtomicLong sequence = new AtomicLong();
    private final AtomicLong nextAllowed = new AtomicLong();
    private final long intervalNanos = TimeUnit.SECONDS.toNanos(10);

    public void reportHighQueue(int depth) {
        long now = System.nanoTime();

        while (true) {
            long allowed = nextAllowed.get();
            if (now - allowed < 0) {
                return;
            }
            if (nextAllowed.compareAndSet(
                    allowed, now + intervalNanos)) {
                break;
            }
        }

        Notification n = new Notification(
            "training.queue.high",
            this,
            sequence.incrementAndGet(),
            System.currentTimeMillis(),
            "Queue depth above threshold");
        n.setUserData(depth);
        sendNotification(n);
    }
}
```

Ví dụ mô phỏng một nguyên tắc throttle bằng monotonic clock. Trong hệ thống thực, cần kiểm tra edge cases liên quan initialization, clock wrap và chính sách “leading/trailing event”, và bảo đảm không chứa dữ liệu nhạy cảm trong payload. Với nhiều resource IDs, nên có throttle state riêng cho từng resource thay vì một biến dùng chung.

Điều cần chú ý: throttle giảm **số notification phát ra**, không chỉ làm listener xử lý nhanh hơn.

## 11. Listener nhẹ và xử lý nặng tách rời

Giả sử một listener cần gửi cảnh báo tới dịch vụ khác. Nếu gọi HTTP trực tiếp trong callback đồng bộ, lúc dịch vụ cảnh báo bị chậm, hệ thống bị ảnh hưởng ngược.

Mô hình tốt hơn:

```text
JMX callback
   |
   +--> validate type
   +--> snapshot minimal fields
   +--> enqueue bounded task
   +--> return quickly
               |
               v
          Worker executor
               |
               +--> outbound API with timeout
               +--> retry if safe
               +--> metrics/logs
```

Ví dụ:

```java
import javax.management.Notification;
import javax.management.NotificationListener;
import java.util.concurrent.Executor;

public final class AlertListener implements NotificationListener {
    private final Executor executor;
    private final AlertSender sender;

    public AlertListener(Executor executor, AlertSender sender) {
        this.executor = executor;
        this.sender = sender;
    }

    @Override
    public void handleNotification(Notification notification,
                                   Object handback) {
        String type = notification.getType();
        long sequence = notification.getSequenceNumber();
        String message = notification.getMessage();

        executor.execute(() ->
            sender.send(type, sequence, message));
    }

    public interface AlertSender {
        void send(String type, long sequence, String message);
    }
}
```

Một implementation production phải xử lý `RejectedExecutionException`, giữ payload an toàn, tránh retry vô hạn, định nghĩa shutdown và log lỗi worker. Nếu notification là optional telemetry, có thể drop kèm counter. Nếu bắt buộc không mất, dùng persistent queue và cơ chế nghiệp vụ phù hợp.

## 12. Thread safety và memory visibility

Notification có thể được phát từ nhiều threads, listener cũng có thể chạy song song. Những điểm quan trọng:

- Bộ đếm sequence nên atomic nếu nhiều producers.
- State dùng chung cần `volatile`, locks hoặc concurrent structures thích hợp.
- Payload không nên chứa mutable object dùng chung chưa đồng bộ.
- Listener không được giả định callbacks luôn trên cùng thread.
- Khi dùng multi-thread executor, callback #2 có thể kết thúc trước callback #1.
- Nếu listener gọi lại MBean synchronously, cần tránh lock inversion và deadlocks.

Một anti-pattern:

```java
private final java.util.HashMap<String, Integer> counts =
    new java.util.HashMap<>();

public void handleNotification(Notification n, Object handback) {
    counts.merge(n.getType(), 1, Integer::sum);
}
```

Nếu callbacks song song, `HashMap` không thread-safe. Một phương án:

```java
private final java.util.concurrent.ConcurrentHashMap<
    String, java.util.concurrent.atomic.LongAdder> counts =
        new java.util.concurrent.ConcurrentHashMap<>();

public void handleNotification(Notification n, Object handback) {
    counts.computeIfAbsent(
        n.getType(),
        ignored -> new java.util.concurrent.atomic.LongAdder()
    ).increment();
}
```

Đối với state phức tạp hơn bộ đếm, cần kiểm soát atomicity của nhiều fields hoặc dùng immutable snapshot.

## 13. Listener exception và lỗi không được quan sát

Một callback có thể thất bại vì:

- Payload không hợp lệ.
- Resource đã bị unregister.
- Rejection từ executor.
- Database/network dependency lỗi.
- Race condition do concurrent updates.
- Queue đầy hoặc callback timeout.

Với callback chạy trên executor, exception có thể chỉ xuất hiện trong executor thread. Nếu code không ghi log/metrics, caller của `sendNotification` có thể không nhận biết.

Một pattern:

```java
@Override
public void handleNotification(Notification n, Object handback) {
    try {
        process(n);
    } catch (RuntimeException e) {
        failedNotifications.increment();
        logger.error("JMX listener failed type={}", n.getType(), e);
    }
}
```

`logger` và `failedNotifications` là dependencies minh họa. Tùy loại lỗi và yêu cầu delivery, chỉ log không đủ; có thể cần dead-letter queue hoặc pipeline bền vững riêng. Không ghi toàn bộ `userData` khi có thể chứa thông tin nhạy cảm.

## 14. Remote JMX tăng thêm lớp queue và lỗi mạng

Remote notification listener không nhất thiết chạy trên thread business của server. Connector có cơ chế fetch/forward/dispatch của chính nó, phụ thuộc JMX implementation và protocol.

```text
Server JVM
  emitter
     |
     v
  MBeanServer
     |
  JMX connector server
     |
  network / fetch
     |
Client JVM
  JMX connector client
     |
  listener callback
```

Các yếu tố cần xem xét:

1. Notification forwarding buffer/connector có giới hạn.
2. Kết nối mất có thể làm client bỏ lỡ notifications.
3. Client chậm có thể làm backlog tăng hoặc dẫn đến dropped events.
4. Reconnect không tự khôi phục mọi thông báo đã mất.
5. Thời điểm callback tới client không phải thời điểm notification được tạo.
6. Nhiều listeners và nhiều clients làm tăng fan-out.

**Giải pháp cốt lõi:** notification báo thay đổi, còn client query lại **state hiện tại** sau reconnect hoặc khi nghi có gap. Nếu cần lịch sử đầy đủ, lưu event ở hệ thống bền vững.

## 15. Metrics cần theo dõi

Không thể điều khiển áp lực notification nếu không đo được nó. Các metrics hữu ích:

| Metric | Ý nghĩa | Khi tăng bất thường |
|---|---|---|
| notifications_emitted_total | Số notification đã phát | Producer quá ồn |
| notifications_received_total | Số callback nhận | Fan-out hoặc nhận bất thường |
| notifications_dropped_total | Số event bị drop/reject | Overload policy đang kích hoạt |
| listener_processing_seconds | Thời gian xử lý callback | Callback hoặc dependency chậm |
| listener_queue_depth | Số task chờ | Throughput không theo kịp |
| listener_executor_active | Số workers bận | Saturation |
| listener_errors_total | Exception trong callback | Payload/logic/dependency lỗi |
| reconnect_total | Remote connector kết nối lại | Network không ổn định |
| notification_lag_seconds | Thời gian từ timestamp event tới xử lý | Event quá cũ |
| notification_gap_total | Số gap có thể phát hiện qua sequence | Có thể mất event |

Một số metric chỉ khả thi nếu bạn instrumentation đúng tầng. Không mặc định JMX cung cấp tất cả tên metric này. Các metric này có thể được triển khai bằng Micrometer, custom counters hoặc health monitoring tùy kiến trúc.

### 15.1. Tránh metric labels có cardinality cao

Không đặt `notificationId`, UUID, raw message hoặc user ID vào label. Dùng type, module và outcome ở cardinality kiểm soát được. Một system monitoring bị tăng series không giới hạn có thể tự trở thành nguồn quá tải.

### 15.2. Latency end-to-end

Nếu notification có timestamp, listener có thể tính lag:

```java
long ageMs =
    System.currentTimeMillis() - notification.getTimeStamp();
```

Với remote JVMs, clock skew có thể làm số đo âm hoặc sai lệch. Dùng timestamps có đồng bộ thời gian và không coi phép trừ trên hai clocks khác nhau là latency chính xác tuyệt đối. Đo callback duration trong cùng JVM bằng `System.nanoTime()`.

## 16. Spring NotificationPublisher và cấu hình producer

Spring-managed bean có thể phát notification qua `NotificationPublisherAware`:

```java
import javax.management.Notification;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.jmx.export.notification.NotificationPublisher;
import org.springframework.jmx.export.notification.NotificationPublisherAware;

@ManagedResource(
    objectName = "training.spring:type=Queue,name=Orders")
public class QueueManagement implements NotificationPublisherAware {

    private NotificationPublisher publisher;
    private final AtomicLong sequence = new AtomicLong();

    @Override
    public void setNotificationPublisher(NotificationPublisher publisher) {
        this.publisher = publisher;
    }

    @ManagedOperation
    public void signalHighQueue() {
        Notification notification = new Notification(
            "training.queue.high",
            this,
            sequence.incrementAndGet(),
            System.currentTimeMillis(),
            "Orders queue above threshold");
        publisher.sendNotification(notification);
    }
}
```

Đây là ví dụ cho việc một bean gửi notification; production không nên tạo notification mới mỗi khi có request vượt ngưỡng mà không có rate limiting. Để notification metadata xuất hiện trong JMX, cấu hình `@ManagedNotification` hoặc metadata assembler thích hợp có thể cần thiết tùy cách exporter sử dụng Spring annotations.

Spring `NotificationListenerBean` giúp đăng ký listener, filter và mapping MBeans. Nhưng việc đăng ký không thay thế thiết kế threading/queue ở application-level.

## 17. Giảm fan-out không cần thiết

Một notification có thể tới nhiều listener, mỗi listener lại tạo tasks mới:

```text
1 emitter event
    |
    +-- log listener
    +-- metrics listener
    +-- alert listener
    +-- audit listener
    |
    v
4 callbacks / event
```

Với 1.000 events/s, tổng callback rate có thể 4.000/s trước khi tính remote clients. Nếu mỗi listener lại phát notification khác, hệ thống có thể tạo vòng event.

Cách cải thiện:

- Chỉ đăng ký listeners thực sự cần.
- Dùng `NotificationFilter` theo type.
- Hạn chế phát lặp cùng trạng thái.
- Gộp metrics aggregation thay vì event-by-event.
- Không tạo notification mới từ mỗi callback mà thiếu guard chống vòng lặp.
- Theo dõi số subscribers, latency và queue của từng listener quan trọng.

Một filter chỉ loại bỏ event trước callback; nó không nhất thiết giảm chi phí **tạo và gửi notification** ở producer nếu broadcaster đã phải xử lý trước đó. Nếu lượng event quá lớn, giảm tại nguồn mang lại lợi ích hơn.

## 18. Thiết kế chính sách overload theo loại tín hiệu

Một hệ thống có thể đặt policy cho từng nhóm:

```text
State change / queue depth:
    coalesce + query current attribute

Recoverable warning:
    throttle + aggregate count

Critical failure transition:
    emit immediately + durable audit elsewhere

Bulk per-item completion:
    counters/metrics instead of notifications

Remote client reconnect:
    resubscribe + resync state
```

Không nên dùng cùng một queue và cùng drop policy cho mọi loại event. Một notification quan trọng về node bị dừng có thể cần đường riêng, tránh bị nghẽn bởi hàng nghìn log-level changes hoặc heartbeat.

### 18.1. Reserve capacity có ý nghĩa gì?

Khi cần ưu tiên critical notifications, có thể tách executor/queue theo mức độ quan trọng hoặc đặt priority queue với policy rõ. Tuy nhiên priority queue không giải quyết tự động vấn đề bounded memory và starvation; cần giới hạn tổng dung lượng và đo được số event bị chậm/mất.

## 19. Vòng đời listener và shutdown dưới tải cao

Một executor đang có 10.000 tasks pending khi Spring context đóng có thể kéo dài shutdown hoặc làm mất công việc nếu dừng đột ngột.

Nên xác định:

1. Khi shutdown, có ngừng phát notifications mới không?
2. Listener registration được hủy ở thời điểm nào?
3. Executor dừng nhận task bằng `shutdown()` hay `shutdownNow()`?
4. Chờ tasks hoàn tất tối đa bao lâu?
5. Những event còn chờ có được drop có kiểm soát không?
6. Có cần flush logs/metrics hoặc status store không?
7. Khi restart, client sẽ resync trạng thái bằng cách nào?

Một mẫu:

```java
executor.shutdown();

if (!executor.awaitTermination(10, TimeUnit.SECONDS)) {
    java.util.List<Runnable> abandoned =
        executor.shutdownNow();
    System.err.println(
        "Discarded pending tasks: " + abandoned.size());
}
```

Đây là minh họa, không phải chiến lược bảo đảm không mất event. `shutdownNow()` không bảo đảm task đang chạy ngừng ngay. Đối với processing quan trọng, cần durable handoff trước khi shutdown.

## 20. Kiểm thử burst và áp lực listener

### 20.1. Kịch bản kiểm thử

Tạo môi trường lab có producer phát 10.000 notifications trong một khoảng ngắn. So sánh ba cấu hình:

1. Synchronous listener chậm.
2. Unbounded async queue.
3. Bounded async queue với metrics drop/rejection.

Đo thời gian producer hoàn tất, queue peak, memory sử dụng, số event xử lý, số event bị drop và callback latency.

Không chỉ đo throughput thành công; cần ghi cả **tác động đến ứng dụng nguồn**.

### 20.2. JUnit với controlled executor

Có thể kiểm tra queue/backpressure bằng `ThreadPoolExecutor`:

```java
import org.junit.jupiter.api.Test;
import java.util.concurrent.*;
import static org.junit.jupiter.api.Assertions.*;

class ListenerBackpressureTest {

    @Test
    void boundedQueueRejectsWhenSaturated() throws Exception {
        CountDownLatch release = new CountDownLatch(1);
        ThreadPoolExecutor executor = new ThreadPoolExecutor(
            1, 1, 0, TimeUnit.MILLISECONDS,
            new ArrayBlockingQueue<>(1),
            new ThreadPoolExecutor.AbortPolicy());

        try {
            executor.execute(() -> {
                try {
                    release.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
            });

            // Một worker đang chạy, một task vào queue.
            executor.execute(() -> {});

            assertThrows(RejectedExecutionException.class,
                () -> executor.execute(() -> {}));
        } finally {
            release.countDown();
            executor.shutdownNow();
        }
    }
}
```

Test này chứng minh behavior queue/rejection của executor, không tự chứng minh toàn bộ broadcaster sẽ báo lỗi ra sao. Để kiểm thử JMX end-to-end, đăng ký listener với emitter và đo số callback, timing và error policy thực tế.

### 20.3. Test listener luôn được cleanup

Trong Spring integration test, tạo context với broadcaster và listener, phát một loạt notifications, đóng context, sau đó xác minh listener registration/executor lifecycle không giữ references làm memory leak. Đừng dùng `Thread.sleep` làm điều kiện thành công; dùng latches/counters hoặc trạng thái test fixture có deadline rõ ràng.

## 21. Chẩn đoán sự cố production

| Triệu chứng | Nguyên nhân có thể | Bằng chứng nên lấy |
|---|---|---|
| `sendNotification` chậm | Callback sync hoặc CallerRunsPolicy | Thread dumps, callback duration |
| CPU tăng khi cảnh báo dồn dập | Callback, serialization, logs | Profiler, metrics, sampling |
| Heap tăng liên tục | Unbounded queue/retained payload | Heap histogram, queue depth |
| Listener nhận notification rất muộn | Backlog hoặc remote forwarding delay | Event timestamp và processing lag |
| Một số sự kiện không tới | Drop/reject, filter, disconnect | Emitted/received/dropped counters |
| Client thấy events sai thứ tự | Multi-thread dispatch | Sequence vs completion times |
| Alert lặp vô hạn | Producer thiếu throttle hoặc feedback loop | Event type trace/fingerprint |
| Restart gây mất notification | Non-durable delivery và shutdown | Recovery/resync design |
| Listener lỗi không ai biết | Exception trong worker thiếu logs | Error counters/executor hooks |
| Cảnh báo quá nhiều gây mất tín hiệu quan trọng | Cùng queue và cùng priority | Per-type rates, queue saturation |

Thứ tự điều tra nên bắt đầu từ **tốc độ event phát**, sau đó kiểm tra dispatch mode, queue, processing latency và remote clients. Không tăng số threads trước khi xác định callback đang dùng CPU, đợi I/O hay bị lock contention.

## 22. Checklist vận hành

- [ ] Phân biệt notification cần lịch sử với notification chỉ báo trạng thái.
- [ ] Giảm notification ngay ở producer bằng throttle/coalescing nếu phù hợp.
- [ ] Không phát notification trên mỗi request khi chỉ cần counters.
- [ ] Listener đồng bộ phải ngắn, tránh blocking network I/O.
- [ ] Executor bất đồng bộ có bounded queue và rejection policy rõ.
- [ ] Có giới hạn callback concurrency.
- [ ] Có metrics emitted/received/dropped/lag/error.
- [ ] Có test burst và saturation.
- [ ] Có chính sách ordering cho events cần thứ tự.
- [ ] Có chiến lược resync sau remote reconnect.
- [ ] Có lifecycle cleanup khi context đóng.
- [ ] Không dùng JMX notification làm durable event transport nghiệp vụ.

## 23. Bài tập thực hành

### Bài tập A — So sánh synchronous và async

Tạo `NotificationBroadcasterSupport` và listener có callback ngủ 50 ms trong lab. Phát 200 notifications, đo thời gian producer. Chuyển sang executor và so sánh thời gian phát, độ trễ xử lý và số tasks chờ.

### Bài tập B — Burst 10.000 notification

Tạo producer phát 10.000 notifications với ba listener. Đo CPU, heap, callback count và total processing time. Xác định listener nào là bottleneck.

### Bài tập C — Queue bounded

Dùng executor 2 workers và queue 100 entries. Chặn workers bằng latch, gửi thêm notifications và xác minh overload policy. Ghi counter cho rejected/drop tasks.

### Bài tập D — Coalescing theo resource

Thay 1.000 notifications `queue.depth.changed` bằng một notification mỗi cửa sổ thời gian cho mỗi queue ID. Listener đọc attribute `QueueDepth` sau khi nhận tín hiệu. Đánh giá trade-off nếu trạng thái chuyển đổi nhiều lần trong cửa sổ.

### Bài tập E — Remote reconnect

Chạy JMX client khác JVM, đăng ký listener, ngắt kết nối rồi reconnect. So sánh notification count với state hiện tại. Viết bước resync bằng `MBeanServerConnection.getAttribute`.

### Bài tập F — Backpressure và shutdown

Mô phỏng queue còn nhiều tasks khi đóng Spring ApplicationContext. Thiết kế thời gian chờ shutdown, metrics cho abandoned tasks, và giải thích điều kiện cần durable queue thay JMX.

## 24. Câu hỏi tự kiểm tra

1. Vì sao notification dồn dập có thể làm chậm thread phát?
2. Khi nào backlog tăng theo `λ - μ`?
3. Async dispatch có tự giải quyết overload không?
4. Unbounded queue gây rủi ro gì?
5. `CallerRunsPolicy` đưa backpressure vào thread nào?
6. Vì sao event sequence không đồng nghĩa callback completion order?
7. Khi nào nên dùng throttling hoặc coalescing?
8. Tại sao một counter thường tốt hơn notification cho mỗi request?
9. Remote JMX có đảm bảo replay notification sau reconnect không?
10. Metrics nào cho biết listener đang quá tải?
11. Vì sao lỗi trong executor worker có thể khó quan sát?
12. Khi nào cần message broker thay JMX notification?

## 25. Tài liệu tham khảo

- Spring Framework Reference — JMX Notifications: https://docs.spring.io/spring-framework/reference/integration/jmx/notifications.html
- Spring Framework API — NotificationPublisher: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/notification/NotificationPublisher.html
- Spring Framework API — NotificationListenerBean: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/notification/NotificationListenerBean.html
- Java SE 21 — NotificationBroadcasterSupport: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/NotificationBroadcasterSupport.html
- Java SE 21 — ThreadPoolExecutor: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html
- Java SE 21 — MBeanServerConnection: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html

**Ghi nhớ:** JMX notification là tín hiệu quản trị, không phải durable event stream. Khi sự kiện dồn dập, hãy đo tỷ lệ phát và xử lý, giảm nhiễu ở nguồn, giới hạn queue và concurrency, định nghĩa overload policy, instrument drop/lag/error và thiết kế resync cho remote listeners. Mục tiêu là giữ ứng dụng ổn định ngay cả khi hệ thống cảnh báo hoạt động dưới tải cao.
