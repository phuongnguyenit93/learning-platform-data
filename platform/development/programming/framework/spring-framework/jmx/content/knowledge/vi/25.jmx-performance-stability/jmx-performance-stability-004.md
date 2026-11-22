# Giới hạn tần suất phát notification trong Spring Framework JMX

## 1. Vì sao phải giới hạn notification?

Java Management Extensions (**JMX**) hỗ trợ cơ chế **notification** để MBean phát tín hiệu khi trạng thái của ứng dụng thay đổi. Trong Spring Framework JMX, một bean có thể được xuất thành MBean bằng `MBeanExporter`, khai báo metadata notification bằng `@ManagedNotification` và phát sự kiện thông qua `NotificationPublisher` hoặc các API tiêu chuẩn JMX.

Cơ chế này phù hợp cho những sự kiện quản trị như:

- Một worker chuyển từ `RUNNING` sang `PAUSED`.
- Một hàng đợi vượt ngưỡng cảnh báo.
- Một cache hoàn tất refresh.
- Một kết nối đến hệ thống ngoài bị gián đoạn.
- Một tác vụ bảo trì bắt đầu, thất bại hoặc hoàn thành.

Tuy nhiên, **phát notification cho mọi thay đổi nhỏ** có thể khiến MBean, connector và listener chịu tải lớn. Ví dụ một queue xử lý 50.000 công việc mỗi giây mà mỗi lần thêm job đều phát notification có thể tạo 50.000 sự kiện mỗi giây — thường vượt nhu cầu của hệ thống quản trị.

Giới hạn tần suất phát là một phần của thiết kế **hiệu năng và ổn định**, không chỉ là tối ưu phụ. Mục tiêu là giảm sự kiện dư thừa nhưng vẫn giữ khả năng nhận biết những thay đổi quan trọng.

## 2. Kiến trúc notification và nơi có thể xuất hiện quá tải

~~~text
Business service / resource
       |
       +-- state transition / threshold
       |
       v
MBean / Spring NotificationPublisher
       |
       +-- event filtering
       +-- throttling / coalescing
       |
       v
MBeanServer / NotificationBroadcaster
       |
       +-- local listener A
       +-- remote listener B
       +-- audit/monitoring listener C
       |
       v
Alerting / logging / dashboard
~~~

Có nhiều nguồn chi phí:

| Thành phần | Tác động khi tần suất cao |
| --- | --- |
| Business thread phát event | Tạo object, format message, giữ lock, gọi publisher |
| Notification broadcaster | Duyệt listener, thực thi filter, dispatch |
| Listener | CPU, blocking, ghi log, gọi mạng |
| Remote JMX connector | Serialization, network, buffering, thread/connection |
| Observability backend | Ingestion, storage, alert fan-out |
| Operator | Alert fatigue, khó phân biệt sự kiện quan trọng |

Không nên giả định mọi notifier đều dispatch bất đồng bộ. Cơ chế phát có thể dùng executor riêng hoặc chạy callback theo cơ chế implementation. Với listener đồng bộ, một handler chậm có thể làm chậm đường phát sự kiện.

**Nguyên tắc:** kiểm soát tần suất càng gần nguồn phát càng tốt, đồng thời thiết kế listener và connector có khả năng chịu tải.

## 3. Phân biệt rate limiting, throttling, debounce, coalescing và sampling

Những khái niệm này không hoàn toàn giống nhau.

### 3.1. Rate limiting

Giới hạn tối đa số notification được phát trong một khoảng thời gian.

Ví dụ:

~~~text
Tối đa 10 notification/giây cho mỗi MBean.
~~~

Có thể dùng token bucket, fixed window hoặc sliding window.

### 3.2. Throttling

Cho phép phát tối đa một sự kiện sau một khoảng tối thiểu.

~~~text
Chỉ phát một queue-depth warning mỗi 5 giây.
~~~

Mọi event nằm giữa các lần được phép phát có thể bị bỏ hoặc được tổng hợp.

### 3.3. Debounce

Chờ một khoảng yên lặng trước khi phát. Nếu trạng thái tiếp tục thay đổi, thời điểm phát được dời lại.

~~~text
Configuration changes liên tục
   -> chỉ phát sau 500 ms không còn thay đổi
~~~

Debounce hữu ích cho burst cấu hình, nhưng có thể trì hoãn mãi nếu sự kiện liên tục không ngừng.

### 3.4. Coalescing

Gộp nhiều sự kiện thành một bản tóm tắt.

~~~text
100 queue-depth changes
   -> một notification: "100 changes, latest depth=1320"
~~~

Coalescing có thể bảo toàn thông tin tổng hợp thay vì chỉ drop event.

### 3.5. Sampling

Lấy một phần sự kiện, ví dụ 1 trong mỗi 100 lần hoặc theo xác suất. Sampling phù hợp với dữ liệu tần suất cao dùng phân tích xu hướng, nhưng không phù hợp cho sự kiện hiếm/critical bắt buộc phải ghi nhận.

| Kỹ thuật | Mục tiêu | Đánh đổi |
| --- | --- | --- |
| Throttle | Tránh quá nhiều event trong thời gian ngắn | Bỏ qua thay đổi trung gian |
| Token bucket | Cho phép burst có kiểm soát | Cần quản lý token và đồng hồ |
| Debounce | Đợi trạng thái ổn định | Tăng độ trễ, có thể hoãn liên tục |
| Coalescing | Gộp biến động thành tóm tắt | Mất chi tiết từng event |
| Sampling | Giảm volume thống kê | Không bảo đảm giữ sự kiện cụ thể |
| Bounded queue | Bảo vệ bộ nhớ và listener | Cần chính sách khi đầy |

## 4. Xác định event nào được phép giảm tần suất

Không phải mọi notification đều giống nhau. Phân loại trước khi chọn thuật toán:

**Nhóm thông tin thường xuyên:**

- Cache hit/miss riêng lẻ.
- Queue depth thay đổi liên tục.
- Progress update mỗi phần trăm nhỏ.
- Số thread active tăng giảm theo request.

Thường nên **dùng metric/attribute** và polling hoặc aggregation, thay vì phát notification cho từng thay đổi.

**Nhóm state transition:**

- `HEALTHY -> DEGRADED`.
- `RUNNING -> FAILED`.
- `CONNECTED -> DISCONNECTED`.
- `PAUSED -> RUNNING`.

Nên phát khi thực sự chuyển trạng thái, không phát lại trong mỗi vòng kiểm tra.

**Nhóm critical:**

- Tác vụ sao lưu thất bại.
- Hết tài nguyên hoặc rủi ro mất dữ liệu.
- Hành động quản trị không được phép.
- Một operation nguy hiểm hoàn tất hoặc lỗi.

Với sự kiện quan trọng cần delivery đáng tin cậy, chỉ giới hạn JMX notification là chưa đủ. Nếu phải bảo đảm không mất sự kiện, cần hệ thống sự kiện bền vững, audit log hoặc cơ chế xác nhận riêng.

## 5. Thiết kế một policy đơn giản trước khi code

Giả sử ứng dụng có notification type:

~~~text
com.example.queue.depth.warning
com.example.queue.depth.recovered
com.example.queue.worker.failed
com.example.queue.worker.restarted
~~~

Policy ví dụ:

| Loại sự kiện | Chiến lược |
| --- | --- |
| Queue depth vượt warning threshold | Phát khi vượt ngưỡng; nhắc lại sau 60 giây nếu vẫn cao |
| Queue depth phục hồi | Phát một lần khi trở về vùng bình thường |
| Worker failed | Phát khi có transition sang FAILED |
| Worker restarted | Phát khi transition sang RUNNING |
| Queue depth thông thường | Metric/attribute, không phát notification |

Lợi ích của **transition-based publishing** là giảm tải ngay từ logic nghiệp vụ mà không cần thêm bộ lọc phức tạp.

Ví dụ khi threshold là 1000:

~~~text
depth  900 -> 1100 : WARNING
depth 1100 -> 1200 : không phát warning mới
depth 1200 ->  800 : RECOVERED
depth  800 -> 1300 : WARNING mới
~~~

Cần định nghĩa rõ liệu “warning nhắc lại sau 60 giây” là notification mới hay summary update. Cùng loại event có thể dùng sequence mới và ghi rõ số lần suppressed để không khiến người nhận hiểu sai.

## 6. MBean Spring phát notification bằng NotificationPublisher

Trong Spring JMX, bean có thể implement `NotificationPublisherAware` để nhận một `NotificationPublisher` và phát notification.

~~~java
package com.example.management;

import java.util.concurrent.atomic.AtomicLong;
import javax.management.Notification;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedNotification;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.jmx.export.notification.NotificationPublisher;
import org.springframework.jmx.export.notification.NotificationPublisherAware;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example:type=Queue,name=payments",
    description = "Payment queue management"
)
@ManagedNotification(
    name = "com.example.queue.depth.warning",
    description = "Queue depth crossed the warning threshold"
)
public class QueueManagement implements NotificationPublisherAware {

    private final AtomicLong sequence = new AtomicLong();
    private volatile int pendingCount;
    private volatile NotificationPublisher publisher;

    @Override
    public void setNotificationPublisher(NotificationPublisher publisher) {
        this.publisher = publisher;
    }

    @ManagedAttribute
    public int getPendingCount() {
        return pendingCount;
    }

    public void onDepthChanged(int depth) {
        pendingCount = depth;

        if (depth > 1000 && publisher != null) {
            Notification event = new Notification(
                "com.example.queue.depth.warning",
                this,
                sequence.incrementAndGet(),
                System.currentTimeMillis(),
                "Queue depth exceeded threshold"
            );

            publisher.sendNotification(event);
        }
    }
}
~~~

Đây là **ví dụ cơ bản chưa giới hạn tần suất**. Khi queue tiếp tục tăng từ 1001 lên 1002, 1003, 1004…, logic sẽ phát liên tục. Cần thêm state transition hoặc limiter để tránh notification storm.

Lưu ý: `@ManagedNotification` khai báo metadata về loại notification, **không tự phát event và không giới hạn tần suất**. Cần exporter phù hợp, ví dụ `AnnotationMBeanExporter`, để Spring nhận diện metadata và gắn `NotificationPublisher`.

## 7. Cách 1: chỉ phát khi trạng thái thay đổi

Một kỹ thuật rất hiệu quả là **edge-triggered notification**.

~~~java
import java.util.concurrent.atomic.AtomicBoolean;

public class QueueThresholdGate {
    private final int warningThreshold;
    private final AtomicBoolean overThreshold = new AtomicBoolean();

    public QueueThresholdGate(int warningThreshold) {
        this.warningThreshold = warningThreshold;
    }

    public boolean shouldEmitWarning(int depth) {
        if (depth <= warningThreshold) {
            overThreshold.set(false);
            return false;
        }

        return overThreshold.compareAndSet(false, true);
    }
}
~~~

Ví dụ:

~~~java
QueueThresholdGate gate = new QueueThresholdGate(1000);

if (gate.shouldEmitWarning(depth)) {
    emitWarning(depth);
}
~~~

Trong một chuỗi thay đổi liên tục ở phía trên ngưỡng, chỉ lần đầu phát warning. Khi depth về ngưỡng hoặc thấp hơn, gate được reset và có thể phát warning mới trong lần vượt ngưỡng tiếp theo.

### Vấn đề khi nhiều thread cập nhật đồng thời

Ví dụ `AtomicBoolean` chỉ chứng minh một thread chuyển trạng thái `false -> true` thành công. Nếu các thread cùng nhận snapshot depth khác thời điểm, một event “đã phục hồi” được xử lý trễ có thể reset cờ sau event vượt ngưỡng mới.

Với hệ thống nhận nhiều update đồng thời, nên tính trạng thái từ một nguồn dữ liệu có thứ tự hoặc dùng synchronization/state machine bảo vệ cả thao tác cập nhật depth và quyết định phát event.

Nếu threshold có hysteresis, dùng ngưỡng “bắt đầu warning” và “phục hồi” khác nhau để tránh rung lắc quanh một điểm.

## 8. Hysteresis giảm notification khi metric dao động quanh ngưỡng

Giả sử warning threshold là 1000. Khi queue depth dao động 999 ↔ 1001, một gate đơn giản có thể liên tục phát warning/recovered.

Giải pháp: hysteresis.

~~~text
Enter WARNING: depth >= 1000
Return NORMAL: depth <= 800
~~~

Với state machine:

~~~java
public enum QueueHealth {
    NORMAL,
    WARNING
}
~~~

~~~java
public synchronized QueueHealth updateHealth(int depth) {
    if (health == QueueHealth.NORMAL && depth >= 1000) {
        health = QueueHealth.WARNING;
        sendWarning(depth);
    } else if (health == QueueHealth.WARNING && depth <= 800) {
        health = QueueHealth.NORMAL;
        sendRecovered(depth);
    }
    return health;
}
~~~

`health`, `sendWarning` và `sendRecovered` là thành viên/phương thức cần được định nghĩa trong bean thật. Mẫu minh họa state transition. Không nên thực hiện blocking I/O trong synchronized region nếu callback phát notification có thể chậm; tính transition trong lock, sau đó dispatch bằng cơ chế phù hợp.

Hysteresis đặc biệt hữu ích với CPU usage, queue backlog, memory pressure và kết nối không ổn định.

## 9. Cách 2: throttle theo khoảng thời gian

Nếu một event có thể được lặp lại nhưng không cần phát liên tục, dùng khoảng tối thiểu giữa hai lần emit.

Ví dụ phát tối đa một warning mỗi 5 giây trong một JVM:

~~~java
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;

public final class NotificationThrottler {
    private final long intervalNanos;
    private final AtomicLong nextAllowedNanos = new AtomicLong(0L);

    public NotificationThrottler(long duration, TimeUnit unit) {
        if (duration <= 0) {
            throw new IllegalArgumentException("duration must be positive");
        }
        this.intervalNanos = unit.toNanos(duration);
    }

    public boolean tryAcquire(long nowNanos) {
        while (true) {
            long next = nextAllowedNanos.get();

            if (nowNanos < next) {
                return false;
            }

            long updated = nowNanos + intervalNanos;

            if (nextAllowedNanos.compareAndSet(next, updated)) {
                return true;
            }
        }
    }
}
~~~

Sử dụng:

~~~java
NotificationThrottler throttler =
    new NotificationThrottler(5, TimeUnit.SECONDS);

if (throttler.tryAcquire(System.nanoTime())) {
    publishQueueWarning();
}
~~~

**Giới hạn của mẫu đơn giản:**

- Dùng `System.nanoTime()` cho elapsed time, không dùng `currentTimeMillis()` để đo khoảng cách chịu ảnh hưởng đồng hồ hệ thống.
- Giả định thời gian chạy chưa dài đến mức arithmetic overflow của mốc thời gian gây ảnh hưởng so sánh; production nên dùng elapsed comparison và trạng thái khởi tạo rõ ràng nếu cần độ bền cao.
- Bộ limiter này chỉ bảo vệ **một instance**. Nhiều replica JVM có limiter riêng.
- Không tự phát bản tổng hợp các event bị suppress.
- Không phân biệt notification type; nhiều loại dùng chung một instance sẽ tranh cùng quota.

Với nghiệp vụ cần phân biệt nhóm event, quản lý limiter theo key như `ObjectName + notificationType`.

## 10. Cách 3: token bucket cho phép burst có kiểm soát

Throttle chỉ cho phép một event mỗi khoảng, nhưng đôi khi cần cho phép burst ngắn khi có nhiều state transition thực sự quan trọng.

Một **token bucket** có các tham số:

~~~text
capacity = 10 notifications
refillRate = 5 tokens/second
~~~

Mỗi lần emit cần một token. Khi bucket hết, event bị suppress hoặc tổng hợp. Sau một khoảng yên lặng, tokens được refill nhưng không vượt capacity.

Thuật toán khái niệm:

~~~text
onEvent:
  now = monotonicClock()
  elapsed = now - lastRefill
  tokens = min(capacity, tokens + elapsed * refillRate)
  lastRefill = now

  if tokens >= 1:
      tokens -= 1
      emit()
  else:
      countSuppressed()
~~~

### Điểm cần lưu ý

- Đồng bộ toàn bộ cập nhật token/refill khi nhiều thread dùng cùng bucket.
- Không dùng wall-clock làm nguồn đo thời gian trôi nếu có thể tránh.
- Áp dụng capacity và refill rate theo mức độ quan trọng của event.
- Tránh một loại event “ồn” chiếm hết quota của loại critical.
- Nếu có nhiều JVM, token bucket local không bảo đảm rate toàn cluster.

**Token bucket phù hợp để giới hạn traffic, không bảo đảm quan trọng nhất luôn được giữ** nếu mọi event đều dùng chung quota. Có thể phân loại priority và dùng budget riêng.

## 11. Cách 4: coalescing và notification tổng hợp

Thay vì drop hoàn toàn những event bị giới hạn, có thể ghi nhận số bị suppress và phát thông tin tóm tắt trong lần sau.

Ví dụ:

~~~text
12:00:00 WARNING depth=1200
12:00:01..12:00:29 487 events suppressed
12:00:30 SUMMARY depth=1380 suppressed=487
~~~

Một class đếm suppression:

~~~java
import java.util.concurrent.atomic.AtomicLong;

public final class SuppressedEventCounter {
    private final AtomicLong suppressed = new AtomicLong();

    public void onSuppressed() {
        suppressed.incrementAndGet();
    }

    public long drainSuppressedCount() {
        return suppressed.getAndSet(0L);
    }
}
~~~

Khi limiter cho phép phát:

~~~java
long dropped = counter.drainSuppressedCount();

Notification event = new Notification(
    "com.example.queue.depth.warning.summary",
    this,
    sequence.incrementAndGet(),
    System.currentTimeMillis(),
    "Queue warning; suppressed=" + dropped
);

publisher.sendNotification(event);
~~~

Mẫu đơn giản này có một race có thể xảy ra: một event bị suppress ngay sau khi drain sẽ được tính vào đợt kế tiếp. Điều đó chấp nhận được nếu semantics của summary được định nghĩa theo “đợt đã ghi nhận đến lúc drain”, nhưng không nên mô tả summary như một snapshot nguyên tử của mọi thread nếu không có synchronization phù hợp.

Ngoài số lượng, summary có thể chứa:

- Giá trị gần nhất.
- Max/min trong cửa sổ.
- Khoảng thời gian tổng hợp.
- Số lần thay đổi trạng thái.
- Mã định danh nguồn phát.

Không nên đưa toàn bộ payload gốc vào `userData` của summary vì có thể làm notification quá lớn.

## 12. Cách 5: debounce các thay đổi cấu hình

Giả sử người vận hành thay nhiều setting trong vòng một giây. Nếu mỗi setter đều phát notification “configuration updated”, client có thể nhận hàng chục thông báo.

Debounce có thể đợi 500 ms sau lần thay đổi cuối:

~~~text
setMaxWorkers()
setTimeout()
setBatchSize()
      |
      +-- debounce 500 ms
               |
               v
    configurationChanged (once)
~~~

Tuy nhiên, một luồng thay đổi không ngừng có thể khiến debounce không phát bao giờ. Khi cần khả năng quan sát có thời hạn, dùng **debounce có max-wait** hoặc gộp theo cửa sổ cố định.

Khi triển khai bằng `ScheduledExecutorService`, cần hủy lịch cũ, xử lý race giữa cancel và task đã chạy, quản lý shutdown và không tạo một thread cho mỗi event. Nên dùng scheduler có ownership rõ trong Spring context.

## 13. Cách 6: giới hạn tại listener và bounded queue

Ngay cả khi producer đã rate-limit, listener vẫn cần tự bảo vệ vì:

- Có nhiều emitter cùng phát.
- Listener kết nối tới nhiều JVM.
- Có producer không tuân thủ policy.
- Consumer downstream bị chậm hoặc tạm ngưng.

Một thiết kế:

~~~text
JMX callback
    |
    v
validate/filter quickly
    |
    v
bounded queue
    |
    v
worker pool
    |
    v
logging / alert service
~~~

Với Java:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import javax.management.Notification;
import javax.management.NotificationListener;

public class QueueingListener implements NotificationListener {
    private final BlockingQueue<Notification> queue =
        new ArrayBlockingQueue<>(1000);

    @Override
    public void handleNotification(
            Notification notification, Object handback
    ) {
        boolean accepted = queue.offer(notification);

        if (!accepted) {
            // Increment a dropped-event metric.
        }
    }

    public Notification take() throws InterruptedException {
        return queue.take();
    }
}
~~~

Mẫu chỉ xây một queue được giới hạn bộ nhớ; ứng dụng phải tạo worker đọc từ queue, quyết định xử lý drop, shutdown và metrics. Nếu cần phân biệt nguồn, nên lưu cả handback/ObjectName cùng notification thay vì chỉ lưu Notification.

**Không dùng hàng đợi vô hạn** để “không mất notification” khi consumer có thể chậm vô thời hạn; điều đó có thể dẫn đến OutOfMemoryError.

## 14. Spring configuration: tách policy khỏi publisher

Một thiết kế có thể chia thành:

~~~text
QueueService
   |
   +-- thay đổi trạng thái
   |
   v
QueueNotificationPolicy
   |
   +-- transition guard
   +-- throttle/coalescing
   |
   v
NotificationPublisher
   |
   v
JMX listeners
~~~

Ưu điểm:

- Dễ unit test thuật toán rate limit mà không cần khởi động MBeanServer.
- Business service không phải biết các chi tiết `Notification`.
- Có thể thay policy theo loại event.
- Có thể dùng metrics để theo dõi suppression.
- Giữ `NotificationPublisher` chỉ tập trung vào phát event hợp lệ.

Spring `@ManagedNotification` là metadata của MBean. Nó **không có một tham số rate-limit chung** tự hạn chế mọi thông báo. Giới hạn thường được thiết kế tại producer, bộ phát/scheduler hoặc listener.

## 15. Ví dụ service quản lý notification policy

Một giao diện đơn giản:

~~~java
public interface ManagementEventPolicy {
    boolean shouldPublish(
        String resourceName,
        String notificationType,
        long nowNanos
    );
}
~~~

Từ đó có thể triển khai policy theo key:

~~~text
com.example:type=Queue,name=payments
    + com.example.queue.depth.warning
       -> 1 notification/5 seconds

com.example:type=Queue,name=shipping
    + com.example.queue.depth.warning
       -> 1 notification/30 seconds

com.example:type=Worker,name=primary
    + com.example.worker.failed
       -> publish every state transition
~~~

Không nên dùng một limiter toàn cục cho mọi sự kiện khi mức độ quan trọng khác nhau. Một nguồn phát ồn có thể chiếm quota khiến sự kiện quan trọng không còn được gửi.

### Quản lý số key

Nếu policy tạo một limiter riêng cho mọi ID, nhưng resource ID sinh động không giới hạn, map limiter có thể tăng vô hạn. Dùng tập resource đã đăng ký ổn định, cache có eviction hoặc một chiến lược key bounded phù hợp.

## 16. Đảm bảo thời gian và tính đồng thời

Rate limit phụ thuộc thời gian và concurrency:

- **Thời gian:** dùng monotonic clock cho duration.
- **Đồng thời:** các thread không được cùng tiêu thụ một token/cửa sổ như thể chỉ có một event.
- **Sequence:** JMX notification sequence number nên tăng cho mỗi event được phát theo hợp đồng emitter.
- **Publication:** nếu vừa phát vừa cập nhật trạng thái, xác định thứ tự quan sát của client.
- **Clock skew:** timestamp giữa các JVM không đủ để xây thứ tự toàn cục.
- **Restart:** limiter local bị reset khi process khởi động lại.

Một cách test hợp lý là inject `Clock` hoặc `LongSupplier` cho thời gian thay vì hard-code `System.nanoTime()` ở mọi nơi, giúp test deterministic.

### Có cần đồng bộ distributed không?

Nếu yêu cầu là “không quá 100 notification/giây cho toàn cluster”, limiter riêng ở mỗi JVM chưa đủ. Có thể cần aggregator hoặc rate limiter dùng state chia sẻ. Nhưng với monitoring notification thông thường, thường phù hợp hơn là giới hạn theo MBean/JVM và để hệ thống monitoring tổng hợp.

Tránh thêm distributed coordination phức tạp nếu yêu cầu chỉ là không làm nghẽn MBeanServer của một JVM.

## 17. Observability cho bộ giới hạn

Một rate limiter không được giám sát có thể che mất tình trạng nghiêm trọng. Nên có các metric:

| Metric | Ý nghĩa |
| --- | --- |
| `notification_emitted_total` | Tổng số notification thực sự phát |
| `notification_suppressed_total` | Tổng số bị chặn vì policy |
| `notification_coalesced_total` | Tổng số sự kiện được gộp |
| `notification_delivery_errors_total` | Lỗi ở tầng dispatch/client nếu đo được |
| `notification_queue_depth` | Số event đợi xử lý tại listener |
| `notification_oldest_age_seconds` | Độ trễ của event lâu nhất trong queue |
| `notification_publish_duration` | Thời gian dùng để publish/dispatch |
| `notification_listener_failures_total` | Số lỗi handler |

Các tên trên là **ví dụ metric ứng dụng**, không phải metric JMX tự động được Spring cung cấp.

Bổ sung attributes quản trị:

~~~java
@ManagedAttribute
public long getSuppressedNotificationCount() {
    return suppressedCounter.get();
}

@ManagedAttribute
public long getEmittedNotificationCount() {
    return emittedCounter.get();
}
~~~

Điều này giúp người vận hành thấy limiter đang hoạt động, tránh hiểu nhầm “không có notification” là “hệ thống ổn”.

## 18. Không nhầm rate limiting với yêu cầu bảo toàn event

Nếu notification là tín hiệu trạng thái, việc coalescing có thể chấp nhận:

~~~text
10.000 queue depth updates
    -> current depth + high-water mark
~~~

Nhưng nếu mỗi event là một yêu cầu pháp lý/kiểm toán, không được mất thì “drop dưới tải” là sai kiến trúc. JMX notification không phải message broker bền vững với replay, ack và exactly-once guarantee.

Trong trường hợp ấy, có thể:

1. Ghi event vào transactional outbox hoặc log bền vững.
2. Đẩy qua message broker phù hợp.
3. Dùng JMX chỉ để báo trạng thái hoặc số lượng event đang tồn.
4. Phát notification JMX tổng hợp như tín hiệu phụ.
5. Thiết kế retry, deduplication và audit theo yêu cầu nghiệp vụ.

Rate limiting bảo vệ hiệu năng, nhưng không thay thế cơ chế bảo đảm event delivery.

## 19. Rủi ro với notification từ xa

Remote JMX có thể dùng RMI connector. Khi notification được gửi qua mạng:

- Serialization tốn CPU và bandwidth.
- Client không xử lý kịp có thể dẫn đến backlog/notification loss tùy connector.
- Kết nối bị gián đoạn có thể khiến client bỏ lỡ sự kiện.
- Listener có thể nhận event trễ hoặc không đúng thứ tự quan sát tại source.
- Dữ liệu trong `userData` có thể cần kiểu Serializable/open types phù hợp.
- Mọi endpoint JMX remote cần authentication, TLS và authorization.

Không nên dựa vào JMX notification như kênh truyền mọi event tần suất cao qua nhiều JVM. Với hệ thống phân tán, có thể dùng metric telemetry hoặc event streaming chuyên biệt thay thế.

### Throttle trước khi đi qua connector

Nếu một notification bị chặn ngay tại source, nó không đi qua broadcaster hoặc remote connector. Điều này thường tiết kiệm chi phí hơn so với gửi tất cả rồi để remote client drop.

Tuy vậy, cần cân nhắc có client nào bắt buộc nhận đầy đủ event không. Nếu có, không được áp dụng một policy drop toàn cục mà làm mất quyền quan sát của client ấy; thay vào đó dùng kênh riêng.

## 20. Kiểm thử rate limiter

Một bộ test nên bao gồm:

1. Event đầu tiên có được phát không?
2. Những event sát nhau trong cùng cửa sổ bị suppress đúng không?
3. Event sau khi hết khoảng được phát đúng không?
4. Hai thread cùng gọi có vượt quota không?
5. Clock giả lập không làm test phụ thuộc `sleep`.
6. Thay đổi notification type có dùng quota độc lập không?
7. Sau restart, policy local reset có đúng hợp đồng không?
8. Coalescing có ghi nhận số event đã suppressed không?
9. Queue đầy được xử lý theo policy đã định nghĩa không?
10. Không có memory leak từ map limiter theo resource ID.
11. Sự kiện critical có bị chặn do sự kiện informational chiếm budget không?
12. Các transition WARNING/RECOVERED không bị bỏ nhầm.

### Unit test throttle dùng fake time

~~~java
import java.util.concurrent.TimeUnit;

NotificationThrottler throttler =
    new NotificationThrottler(5, TimeUnit.SECONDS);

long t0 = TimeUnit.SECONDS.toNanos(100);

assert throttler.tryAcquire(t0);
assert !throttler.tryAcquire(t0 + TimeUnit.SECONDS.toNanos(1));
assert !throttler.tryAcquire(t0 + TimeUnit.SECONDS.toNanos(4));
assert throttler.tryAcquire(t0 + TimeUnit.SECONDS.toNanos(5));
~~~

Bài test sử dụng thời gian truyền vào để kiểm tra logic, không phải ngủ 5 giây.

### Integration test với MBeanServer

Kiểm thử integration có thể:

- Khởi tạo MBeanServer cô lập.
- Đăng ký một MBean phát notification.
- Đăng ký `NotificationListener` đếm sự kiện.
- Gọi method kích hoạt event nhiều lần.
- Kiểm tra số event nhận trong từng cửa sổ.
- Gọi sau khi thời gian giả tiến lên.
- Hủy đăng ký listener/MBean và giải phóng resource.

Nếu dùng executor bất đồng bộ, test cần `CountDownLatch` hoặc đồng bộ trạng thái để chờ kết quả; không dùng assertion ngay lập tức một cách dễ bị flaky.

## 21. Những lỗi phổ biến

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Notification storm | Phát event cho từng thay đổi metric | Chuyển sang state transition/metric |
| Alert lặp liên tục quanh ngưỡng | Thiếu hysteresis | Dùng enter/exit thresholds khác nhau |
| Event quan trọng bị mất | Dùng chung limiter với event ồn | Tách priority/budget |
| Listener làm chậm application thread | Handler blocking | Bounded async dispatch |
| Memory tăng không giới hạn | Queue hoặc map limiter không bounded | Giới hạn capacity và eviction |
| Metric suppressed luôn bằng 0 | Chưa đếm event bị drop | Bổ sung counter |
| Notification không được nhận | Listener không đăng ký hoặc MBean không emit | Kiểm tra registration và metadata |
| Remote client bỏ lỡ sự kiện | Mất kết nối, connector backlog | Reconnect/re-subscribe, telemetry khác nếu cần |
| Cùng event phát nhiều lần | Nhiều emitter/registration hoặc thiếu dedup | Kiểm tra ObjectName và subscription |
| Giới hạn local nhưng cluster vẫn ồn | Mỗi replica có limiter riêng | Tổng hợp hoặc giới hạn tại collector |
| CPU tăng khi format message | Format payload trước khi rate limit | Gate trước rồi mới tạo Notification |
| Giới hạn không ổn khi đồng thời | Cập nhật limiter không atomic | CAS/lock/state machine |

## 22. Checklist khi triển khai production

1. Có cần notification hay metric/attribute đã đủ?
2. Event nào quan trọng, event nào có thể drop/coalesce?
3. Rate-limit theo MBean, notification type hay toàn JVM?
4. Có cần ngưỡng khác nhau để enter/exit cảnh báo?
5. Có giới hạn tối đa số event trong một giây không?
6. Có cần burst ngắn hay chỉ một event mỗi khoảng?
7. Có cơ chế báo số event đã suppressed?
8. Payload có đủ nhỏ và không chứa secret?
9. Handler có giới hạn thời gian xử lý và queue capacity?
10. Có cleanup executor/listener khi Spring context đóng?
11. Có cần re-subscribe khi MBean hoặc connector bị thay?
12. Với nhiều JVM, target identity có được lưu trong monitoring?
13. Với remote connector, TLS/authentication/authorization có đầy đủ?
14. Có test concurrency và time boundary?
15. Có plan khi monitoring cần thông tin chi tiết hơn summary?
16. Có event critical nào không được phép bị suppress?
17. Có audit/log bền vững cho những sự kiện bắt buộc lưu?
18. Có tài liệu mô tả mức trễ và khả năng mất event?

## 23. Câu hỏi tự kiểm tra

**1. Spring `@ManagedNotification` có giới hạn tốc độ phát không?** Không. Annotation chỉ khai báo metadata notification; code phát hoặc lớp policy phải thực hiện giới hạn.

**2. Khi nào throttle tốt hơn debounce?** Khi cần bảo đảm event có thể phát theo chu kỳ tối thiểu trong khi nguồn liên tục thay đổi; debounce phù hợp chờ giai đoạn yên lặng.

**3. Vì sao nên kiểm tra state transition thay vì phát theo mọi lần đo metric?** Vì nhiều lần đo không tạo thay đổi trạng thái mới; phát theo transition giảm đáng kể event dư thừa.

**4. `System.currentTimeMillis()` có nên dùng để đo interval rate limit không?** Không nên, vì wall clock có thể bị điều chỉnh. Dùng monotonic time như `System.nanoTime()` cho duration.

**5. Một `AtomicBoolean` có tự giải quyết mọi race condition khi cập nhật queue health không?** Không. Cần bảo đảm state update có ordering/atomicity phù hợp, đặc biệt khi update đến từ nhiều thread và snapshot khác thời điểm.

**6. Token bucket local có giới hạn được tổng notification của cả cluster không?** Không. Mỗi JVM có quota riêng; giới hạn toàn cluster cần coordination hoặc aggregation phù hợp.

**7. Có nên dùng queue vô hạn để không drop notification?** Không. Khi consumer chậm, queue có thể tăng đến hết bộ nhớ. Cần bounded queue và chính sách quá tải.

**8. JMX notification có phù hợp làm kênh audit bền vững không?** Không nên xem nó là bảo đảm lưu bền/replay. Dùng event log hoặc message broker khi yêu cầu không mất sự kiện.

## 24. Tổng kết

Giới hạn tần suất notification là một thành phần quan trọng của hiệu năng và độ ổn định khi dùng Spring Framework JMX.

Hướng tiếp cận ưu tiên:

- **Không phát event cho từng thay đổi metric thông thường** nếu có thể dùng attribute/metric.
- **Phát theo state transition** và dùng hysteresis để tránh rung lắc quanh ngưỡng.
- Dùng throttle/token bucket cho sự kiện có tần suất cao nhưng vẫn cần cập nhật định kỳ.
- Dùng coalescing/summary để người vận hành biết có bao nhiêu sự kiện đã bị giảm.
- Dùng bounded queue, handler nhanh và metrics để bảo vệ downstream.
- Đánh giá riêng sự kiện critical và sự kiện bắt buộc lưu bền.
- Với remote JMX, giảm volume càng gần source càng tốt để tránh tốn transport.

**Mục tiêu không phải xóa tối đa sự kiện, mà là giữ tín hiệu quản trị quan trọng với chi phí có thể kiểm soát và hành vi rõ ràng dưới tải.**

### Tài liệu tham khảo

- Spring Framework Reference — JMX Notifications: https://docs.spring.io/spring-framework/reference/integration/jmx/notifications.html
- Spring Framework API — `NotificationPublisher`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/notification/NotificationPublisher.html
- Spring Framework API — `NotificationPublisherAware`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/notification/NotificationPublisherAware.html
- Java SE API — `Notification`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/Notification.html
- Java SE API — `NotificationBroadcasterSupport`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/NotificationBroadcasterSupport.html
