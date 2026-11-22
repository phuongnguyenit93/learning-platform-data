# Theo dõi thời gian paused

Trong Spring Kafka, **pause** là cách tạm ngừng giao thêm record cho listener mà không nhất thiết đóng consumer hoặc rời consumer group. Ứng dụng có thể pause toàn bộ listener container, pause một partition, hoặc để một cơ chế backpressure yêu cầu tạm dừng khi database, HTTP service hay hàng đợi nội bộ đang quá tải.

Vấn đề vận hành không dừng ở câu hỏi **consumer có đang paused không?** Một partition có thể được pause có chủ đích trong vài giây để downstream phục hồi, nhưng nếu giữ paused hàng chục phút thì dữ liệu sẽ tiếp tục tích tụ. Vì vậy, cần đo **thời gian pause đã kéo dài bao lâu**, **tổng thời gian pause trong một khoảng quan sát**, **lý do pause**, **thời gian từ yêu cầu đến khi thực sự pause/resume**, và **tác động lên consumer lag, tuổi record cũng như SLO nghiệp vụ**.

Bài học này trình bày cách theo dõi trạng thái và thời gian paused trong chương **Pause và backpressure** của module **Spring Kafka Reliability Operations**. Trọng tâm là listener lifecycle của Spring Kafka, phân biệt requested và effective state, đo duration bằng đồng hồ phù hợp, xử lý rebalance, thiết kế metrics/alert và lập runbook khi pause kéo dài ngoài dự kiến.

## 1. Pause không phải stop và cũng không phải xử lý xong record

Một consumer Kafka có thể thuộc các trạng thái vận hành:

~~~text
RUNNING: poll và xử lý records
      |
      | container.pause() / pausePartition()
      v
PAUSE REQUESTED
      |
      | consumer thread áp dụng pause tại thời điểm phù hợp
      v
PAUSED: vẫn có thể poll để duy trì membership
      |
      | container.resume() / resumePartition()
      v
RESUME REQUESTED
      |
      | consumer thread áp dụng resume
      v
RUNNING: tiếp tục nhận và xử lý records
~~~

Sơ đồ thể hiện chuyển trạng thái khái niệm. Việc pause/resume được áp dụng tại một điểm an toàn trong vòng poll của consumer; gọi API yêu cầu pause không có nghĩa tất cả child consumers lập tức ở trạng thái paused ngay trong cùng lời gọi.

So sánh:

| Hành động | Mục tiêu | Consumer group | Record chưa hoàn tất |
|---|---|---|---|
| Pause container | Tạm ngừng nhận/giao thêm dữ liệu theo semantics container | Thường giữ membership nhờ tiếp tục poll | Vẫn cần hoàn tất/ack theo policy |
| Pause partition | Chặn dữ liệu một partition được chỉ định | Consumer vẫn sở hữu partitions đang được assign | Không được commit bỏ qua record |
| Resume | Tiếp tục xử lý sau pause | Giữ membership nếu không có rebalance khác | Dữ liệu tồn lại được xử lý |
| Stop container | Kết thúc listener lifecycle | Có thể rời group hoặc thay đổi assignment theo protocol | Xử lý/replay theo stop policy |
| Process crash | Mất khả năng xử lý đột ngột | Coordinator có thể phân công lại | Record chưa commit có thể redeliver |

**Pause không phải acknowledge.** Một record được pause không đồng nghĩa với record đó đã được xử lý hoặc offset đã commit. Khi consumer resume, nó cần tiếp tục xử lý từ vị trí thích hợp theo container, acknowledgement và committed offsets.

## 2. Vì sao phải đo thời gian paused?

Không có duration metric, dashboard có thể hiển thị một đèn trạng thái paused mà đội vận hành không biết:

- Pause vừa xảy ra cách đây 200 mili giây hay đã kéo dài 2 giờ.
- Pause do backpressure tự động hay do operator bật thủ công.
- Một partition bị paused trong khi các partition khác vẫn chạy bình thường.
- Lệnh resume đã gửi nhưng consumer thread chưa áp dụng.
- Consumer đã rebalance hoặc dừng nhưng telemetry vẫn báo paused.
- Lag tăng vì pause có chủ đích hay vì listener chậm, lỗi deserialization hoặc transaction bị treo.
- Pause có giảm tải dependency như mong muốn không.

Ví dụ một consumer của topic orders.events pause vì connection pool database đã cạn. Pause trong 10 giây có thể cho database phục hồi. Nhưng nếu circuit breaker đã đóng sau 10 giây mà listener vẫn paused thêm 30 phút, hệ thống bỏ lỡ thời gian xử lý, SLO nghiệp vụ bị vi phạm và backlog tăng dù CPU của consumer thấp.

Đo duration giúp phát hiện **pause bị quên**, tạo ngưỡng escalation và phân tích tỷ lệ thời gian consumer không xử lý dữ liệu.

## 3. Có nhiều loại thời gian pause cần theo dõi

Một thiết kế metrics nên tách ít nhất năm đại lượng:

| Đại lượng | Ý nghĩa | Câu hỏi |
|---|---|---|
| Requested pause age | Thời gian từ khi ứng dụng yêu cầu pause | Lệnh pause đã được chờ bao lâu? |
| Effective pause age | Thời gian từ khi container/partition thực sự paused | Nó đã ngừng xử lý bao lâu? |
| Resume application latency | Từ yêu cầu resume đến khi trạng thái paused được gỡ | Vì sao đã resume mà chưa chạy? |
| Completed pause duration | Độ dài một khoảng pause đã kết thúc | Mỗi lần pause kéo dài bao lâu? |
| Cumulative paused time | Tổng thời gian ở trạng thái paused trong một cửa sổ | Consumer mất bao nhiêu thời gian vì backpressure? |

Đừng chỉ ghi một timestamp **pauseRequestedAt** rồi gọi mọi kết quả là pause duration. Một request có thể được ghi nhận trước khi consumer thread áp dụng pause, đặc biệt khi listener đang xử lý một poll lớn hoặc bị kẹt ở dependency.

### 3.1. Ví dụ timeline

~~~text
t=00.0s  Listener đang xử lý batch
t=00.2s  Service gọi container.pause()
t=04.0s  Consumer thực sự paused sau khi xử lý xong
t=14.0s  Service gọi container.resume()
t=15.0s  Consumer áp dụng resume

Requested-to-effective pause latency = 3.8s
Effective paused duration           = 11.0s
Requested pause interval            = 13.8s
Resume application latency          = 1.0s
~~~

Nếu dashboard đo từ t=00.2s đến t=15s, nó báo 14,8 giây, không phải 11 giây consumer thật sự paused. Hai số đều hữu ích, nhưng dùng cho mục đích khác nhau.

## 4. API pause/resume trong Spring Kafka

Spring Kafka cung cấp API pause/resume trên listener container. Với listener được khai báo bằng @KafkaListener, có thể lấy container qua **KafkaListenerEndpointRegistry** theo listener ID.

Ví dụ:

~~~java
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.stereotype.Component;

@Component
public class OrdersListenerControl {

    private final KafkaListenerEndpointRegistry registry;

    public OrdersListenerControl(KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void pauseOrders() {
        MessageListenerContainer container =
            registry.getListenerContainer("orders-listener");

        if (container != null && container.isRunning()) {
            container.pause();
        }
    }

    public void resumeOrders() {
        MessageListenerContainer container =
            registry.getListenerContainer("orders-listener");

        if (container != null && container.isRunning()) {
            container.resume();
        }
    }
}
~~~

Listener tương ứng:

~~~java
@KafkaListener(
    id = "orders-listener",
    topics = "orders.events",
    groupId = "orders-worker"
)
public void consume(OrderEvent event) {
    orderService.process(event);
}
~~~

Tùy cấu hình Spring Boot và container factory, registry có thể được tự tạo bởi Kafka listener infrastructure. Trong ứng dụng có nhiều factories hoặc nhiều listener IDs, cần chắc rằng code đang điều khiển **đúng** container.

**Không gọi KafkaConsumer.pause() trực tiếp từ thread bất kỳ.** KafkaConsumer không có bảo đảm thread-safe chung cho các thao tác đó. Sử dụng API container để yêu cầu pause/resume và cho consumer thread áp dụng ở thời điểm phù hợp.

## 5. Requested state khác effective state

Spring Kafka expose các trạng thái kiểu:

- **isPauseRequested():** ứng dụng đã yêu cầu pause cho container.
- **isConsumerPaused():** trạng thái pause đã được áp dụng theo semantics của container.
- **isPartitionPauseRequested(partition):** một partition đã được yêu cầu pause.
- **isPartitionPaused(partition):** partition đang được container ghi nhận là paused.

Tên method và hành vi tổng hợp trên ConcurrentMessageListenerContainer phụ thuộc phiên bản. Khi container chứa nhiều child consumers, một boolean tổng hợp không đủ để mô tả đầy đủ từng partition.

Ví dụ kiểm tra:

~~~java
MessageListenerContainer container =
    registry.getListenerContainer("orders-listener");

if (container != null) {
    boolean requested = container.isPauseRequested();
    boolean effective = container.isConsumerPaused();

    log.info(
        "orders listener pause requested={}, effective={}",
        requested,
        effective
    );
}
~~~

Nếu requested=true nhưng effective=false, consumer có thể đang hoàn tất công việc đã fetch hoặc chưa đi đến điểm áp dụng pause. Nếu requested=false nhưng effective=true, có thể resume vừa được yêu cầu nhưng chưa áp dụng hoặc container vẫn có partition paused do một cơ chế khác.

Không lấy một snapshot đơn lẻ để kết luận lỗi. Cần theo dõi trạng thái qua thời gian và phân biệt global pause với partition-specific pause.

## 6. Theo dõi pause từng partition

Khi một topic có nhiều partitions, backpressure có thể chỉ xảy ra tại một partition. Nếu metric chỉ có listener-level paused=true/false, dashboard có thể bỏ sót vấn đề:

~~~text
orders.events:
  partition 0 -> RUNNING, lag 10
  partition 1 -> PAUSED,  lag 25.000
  partition 2 -> RUNNING, lag 20
  partition 3 -> RUNNING, lag 5
~~~

Với partition pause, ví dụ:

~~~java
import org.apache.kafka.common.TopicPartition;

TopicPartition target =
    new TopicPartition("orders.events", 1);

MessageListenerContainer container =
    registry.getListenerContainer("orders-listener");

if (container != null) {
    container.pausePartition(target);
    // Trạng thái thực tế áp dụng ở consumer thread.
}
~~~

Theo dõi partition:

~~~java
boolean requested =
    container.isPartitionPauseRequested(target);

boolean effective =
    container.isPartitionPaused(target);
~~~

Các method trên cần được xác nhận theo Spring Kafka version. Đặc biệt, nếu partition chưa được assign cho container hiện tại, một trạng thái request trong memory không nên được diễn giải là Kafka broker đã pause partition đó.

Một metric tốt có thể bao gồm topic, partition, listener ID và instance identity. Với cluster có hàng chục nghìn partitions, cần cân nhắc cardinality trước khi đưa tất cả vào labels của hệ thống metrics.

## 7. Events khi pause hoặc resume được áp dụng

Spring Kafka có các container application events liên quan đến pause/resume, ví dụ:

- **ConsumerPausedEvent**: thông báo consumer/container pause đã có hiệu lực theo logic framework.
- **ConsumerResumedEvent**: consumer/container tiếp tục theo logic framework.
- **ConsumerPartitionPausedEvent**: một partition được pause.
- **ConsumerPartitionResumedEvent**: một partition được resume.

Các event này giúp instrumentation đo thời gian sát với **effective state** hơn so với lúc code gọi pause(). Tên event, payload, container reference và timing có thể khác theo Spring Kafka version; cần kiểm tra Javadoc của phiên bản đang chạy.

Ví dụ kiến trúc theo sự kiện:

~~~text
PauseService gọi pause()
       |
       +--> record requestedAt và reason
       |
       v
Consumer thread áp dụng pause
       |
       v
Spring Kafka phát paused event
       |
       +--> tracker bắt đầu effective timer
       |
       +--> Gauge paused=1, currentPausedSeconds tăng
       |
       v
PauseService gọi resume()
       |
       +--> record resumeRequestedAt
       |
       v
Consumer thread áp dụng resume
       |
       v
Spring Kafka phát resumed event
       |
       +--> tracker stop timer và record duration
       |
       +--> Gauge paused=0, currentPausedSeconds=0
~~~

Nếu event listener chạy bất đồng bộ, thời gian callback nhận event có thể trễ hơn thời gian chuyển trạng thái thật. Khi cần độ chính xác cao, instrument ngay tại boundary event phát sinh hoặc chấp nhận sai số của dispatcher/sampling và ghi rõ mức độ chính xác.

Không thực hiện HTTP/database query hoặc logic dài trong application event handler chạy trên consumer thread. Handler nên cập nhật số liệu trong memory nhanh, sau đó để metrics exporter đọc bất đồng bộ.

## 8. Đo duration bằng monotonic clock

Một lỗi phổ biến là dùng:

~~~java
long started = System.currentTimeMillis();
long duration = System.currentTimeMillis() - started;
~~~

Đồng hồ wall-clock có thể bị chỉnh bởi NTP hoặc đồng bộ thời gian hệ điều hành; khoảng chênh lệch đôi khi không phản ánh chính xác elapsed time. Để đo **duration bên trong cùng một JVM**, nên dùng **System.nanoTime()**.

Nguyên tắc:

- **System.nanoTime():** đo thời gian tương đối, thích hợp cho elapsed duration.
- **Instant.now() / Clock:** lưu thời điểm UTC để điều tra log, dashboard và incident timeline.
- **Persisted startedAt:** nếu cần biết một pause kéo dài qua restart, lưu timestamp ở hệ thống bền vững và đối chiếu trạng thái thực tế; không thể mang System.nanoTime từ JVM này sang JVM khác.

Ví dụ:

~~~java
long startedNanos = System.nanoTime();

// Sau khi thực sự resume:
long durationNanos = System.nanoTime() - startedNanos;
long durationMillis =
    TimeUnit.NANOSECONDS.toMillis(durationNanos);
~~~

Không lưu giá trị System.nanoTime() vào database rồi dùng lại sau restart. Điểm gốc của nanoTime không có ý nghĩa thời gian UTC và không được thiết kế để so sánh giữa processes.

## 9. Tracker đơn giản cho một trạng thái pause

Để theo dõi một listener container ở mức tổng thể, có thể lưu thời điểm effective paused bắt đầu và cộng thời gian khi trạng thái trở về running.

Ví dụ Java:

~~~java
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.LongAdder;

public final class PauseDurationStats {

    // Giá trị 0 nghĩa là hiện không có khoảng pause đang mở.
    private final AtomicLong startedNanos = new AtomicLong(0L);
    private final LongAdder completedNanos = new LongAdder();
    private final LongAdder completedIntervals = new LongAdder();

    public void observe(boolean actuallyPaused) {
        if (actuallyPaused) {
            startedNanos.compareAndSet(0L, System.nanoTime());
            return;
        }

        long start = startedNanos.getAndSet(0L);
        if (start != 0L) {
            long elapsed = Math.max(0L, System.nanoTime() - start);
            completedNanos.add(elapsed);
            completedIntervals.increment();
        }
    }

    public boolean isActive() {
        return startedNanos.get() != 0L;
    }

    public double currentPausedSeconds() {
        long start = startedNanos.get();
        return start == 0L
            ? 0.0
            : Math.max(0L, System.nanoTime() - start) / 1e9;
    }

    public double totalPausedSeconds() {
        return completedNanos.sum() / 1e9 + currentPausedSeconds();
    }

    public long completedPauseCount() {
        return completedIntervals.sum();
    }
}
~~~

Ví dụ này có mục đích minh họa nguyên tắc đo thời gian. Nó lưu thống kê **trong memory của một JVM** và không tự tổng hợp nhiều instances. Việc observe() cần được gọi trên mỗi thay đổi effective state hoặc theo lịch sampling nhất quán. Khi listener stop/rebalance, cần đóng interval theo một **lý do lifecycle** riêng, không tự diễn giải stop như “resume thành công”.

Nếu cùng một object nhận observe từ nhiều threads hoặc nhiều child consumers, phải xác định rõ semantics: một tracker cho từng consumer/partition hoặc một phép tổng hợp có đồng bộ. Không dùng một boolean để cộng duration của nhiều partitions nếu cần **partition-seconds** chính xác.

## 10. Lấy mẫu trạng thái theo lịch

Nếu không cần độ chính xác từng mili giây, một scheduled monitor có thể kiểm tra container mỗi giây:

~~~java
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class OrdersPauseSampler {

    private final KafkaListenerEndpointRegistry registry;
    private final PauseDurationStats stats = new PauseDurationStats();

    public OrdersPauseSampler(KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    @Scheduled(fixedDelay = 1_000L)
    public void sample() {
        MessageListenerContainer container =
            registry.getListenerContainer("orders-listener");

        if (container == null || !container.isRunning()) {
            // Ghi nhận trạng thái stop riêng, không đánh đồng với resume.
            return;
        }

        stats.observe(container.isConsumerPaused());
    }

    public double activePausedSeconds() {
        return stats.currentPausedSeconds();
    }
}
~~~

Ứng dụng cần bật scheduling infrastructure, ví dụ **@EnableScheduling**, nếu chưa được cấu hình. Scheduled sampler phù hợp với trạng thái container-level, nhưng có giới hạn:

- Pause dưới 1 giây có thể không được ghi nhận.
- Requested-to-effective latency không được đo nếu chỉ gọi isConsumerPaused().
- Khi có nhiều child consumers, một trạng thái tổng hợp có thể che khuất partial pause.
- Sau restart, in-memory duration bắt đầu lại.
- Nếu container stop trong lúc paused, interval cần đóng với reason STOPPED để không tăng vô hạn.

Với dashboard cần dữ liệu chính xác theo partition và phân biệt reason, dùng event-driven tracker kết hợp periodic reconciliation sẽ phù hợp hơn.

## 11. Gắn Micrometer metrics

Spring Boot thường tích hợp **Micrometer** để xuất metrics tới Prometheus hoặc hệ thống giám sát khác. Với pause duration nên có hai loại chính:

**Gauge cho trạng thái đang diễn ra:**

- paused.active: 0 hoặc 1.
- paused.current.seconds: số giây của interval đang mở, liên tục tăng khi paused.
- pause.requested.current.seconds: thời gian từ request chưa được áp dụng nếu cần.

**Timer/Histogram cho interval đã kết thúc:**

- paused.duration: phân phối thời lượng các lần pause đã hoàn tất.
- pause.to.effective.latency: thời gian từ request đến actual pause.
- resume.to.effective.latency: thời gian từ request resume đến actual resume.

Ví dụ cách đăng ký gauges:

~~~java
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;

public void registerPauseMetrics(
        MeterRegistry registry,
        PauseDurationStats stats) {

    Gauge.builder(
        "app.kafka.pause.current.seconds",
        stats,
        PauseDurationStats::currentPausedSeconds
    )
    .tag("listener_id", "orders-listener")
    .register(registry);

    Gauge.builder(
        "app.kafka.pause.active",
        stats,
        state -> state.isActive() ? 1.0 : 0.0
    )
    .tag("listener_id", "orders-listener")
    .register(registry);

    Gauge.builder(
        "app.kafka.pause.total.seconds",
        stats,
        PauseDurationStats::totalPausedSeconds
    )
    .tag("listener_id", "orders-listener")
    .register(registry);
}
~~~

Các tên metric là **đề xuất custom**, không phải built-in metric bảo đảm có sẵn trong mọi phiên bản Spring Kafka. Micrometer/Prometheus có thể đổi tên dấu chấm thành dấu gạch dưới và chuẩn hóa suffix theo convention của exporter.

Đừng chỉ dùng Timer để cảnh báo pause kéo dài: một interval rất dài chưa kết thúc sẽ **chưa được ghi vào histogram completed durations**. Phải có gauge **current paused age** để thấy ngay một pause vẫn đang diễn ra.

### 11.1. Đo lần pause đã hoàn tất

Ví dụ khi transition paused → resumed:

~~~java
Timer completedPauseTimer = Timer.builder(
    "app.kafka.pause.duration"
)
    .tag("listener_id", "orders-listener")
    .register(meterRegistry);

// elapsedNanos được đo từ monotonic clock.
completedPauseTimer.record(
    elapsedNanos,
    TimeUnit.NANOSECONDS
);
~~~

Timer có thể cung cấp count, total time, max và histogram/percentiles nếu được cấu hình. Mỗi lần record duration chỉ thực hiện khi một effective pause interval thực sự kết thúc.

## 12. Quy ước một khoảng pause

Để tránh double count, một pause interval nên có state machine rõ ràng:

~~~text
ACTIVE
  |
  | effective pause transition
  v
PAUSED(startNano, reason, assignmentEpoch)
  |
  +-- duplicate paused event --> giữ interval hiện tại
  |
  +-- effective resume --> close interval(reason=RESUMED)
  |
  +-- partition revoked --> close interval(reason=REVOKED)
  |
  +-- container stopped --> close interval(reason=STOPPED)
  |
  +-- application shutdown --> close interval(reason=SHUTDOWN)
~~~

Các sự kiện repeated/no-op pause không nên reset start time. Nếu caller gọi pause() mỗi giây trong khi consumer đã paused, duration phải tiếp tục tăng từ lần transition đầu tiên, không khởi động lại.

Tương tự, repeated resume không nên tạo nhiều completed intervals. Dùng transition detection, atomic state hoặc lock phù hợp.

Một completed interval có thể ghi các field:

~~~text
listenerId       = orders-listener
topic            = orders.events
partition        = 3
startedAtUtc     = 2026-11-15T14:00:00Z
endedAtUtc       = 2026-11-15T14:02:15Z
durationSeconds  = 135
reason           = DOWNSTREAM_OVERLOAD
endReason        = RESUMED
instanceId       = orders-pod-7
assignmentEpoch  = ...
~~~

UTC timestamps có ích cho audit/incident; duration trong cùng JVM vẫn nên được tính bằng monotonic clock.

## 13. Tổng thời gian pause: listener-seconds hay partition-seconds?

Một chỉ số **total paused time** dễ bị hiểu sai khi có nhiều partitions.

Giả sử consumer sở hữu 3 partitions:

- Partition 0 paused 10 giây.
- Partition 1 paused cùng khoảng 10 giây.
- Partition 2 vẫn chạy.

Khi đó:

- **Container elapsed pause window:** có thể bằng 10 giây nếu định nghĩa “ít nhất một partition đang pause”.
- **Partition-seconds:** 10 + 10 = 20 partition-giây.
- **Tỷ lệ partitions paused:** 2/3 trong khoảng đó.
- **Full container paused:** false nếu partition 2 vẫn active.

Không cộng thời gian của các partitions rồi gọi đó là “ứng dụng đã dừng 20 giây”. Tổng partition-seconds đo khối lượng tài nguyên partition bị pause, không phải wall-clock pause duration.

Một dashboard tốt nên hiển thị:

| Metric | Định nghĩa |
|---|---|
| app.kafka.pause.partitions | Số partitions thực sự paused tại thời điểm đo |
| app.kafka.pause.partition.seconds.total | Tổng duration cộng qua từng partition |
| app.kafka.pause.any.seconds.current | Thời gian từ khi có ít nhất một partition paused, nếu định nghĩa vậy |
| app.kafka.pause.container.active | Toàn bộ container ở trạng thái paused hay không |
| app.kafka.pause.max.partition.age.seconds | Tuổi pause dài nhất trong các partitions đang paused |

Những metric tên trên là ví dụ về mô hình đo, không phải thuộc tính có sẵn của Spring Kafka.

## 14. Phải ghi nhận lý do pause

Kafka không tự biết **lý do nghiệp vụ** khiến một ứng dụng pause. Nếu cần vận hành, code điều khiển pause nên đính kèm reason có số lượng giá trị giới hạn.

Ví dụ enum:

~~~java
public enum PauseReason {
    DOWNSTREAM_OVERLOAD,
    IN_MEMORY_QUEUE_HIGH,
    CIRCUIT_OPEN,
    RATE_LIMIT,
    MANUAL_MAINTENANCE,
    CONFIG_ROLLOUT,
    UNKNOWN
}
~~~

Khi yêu cầu pause:

~~~text
requestPause(
    listener="orders-listener",
    reason="DOWNSTREAM_OVERLOAD",
    correlationId="incident-417"
)
~~~

Tracker lưu:

- requestedAt.
- requestedBy hoặc automation source.
- reason đã chuẩn hóa.
- context/incident ID trong log hoặc trace.
- expectedResumeCondition.
- expectedDeadline hoặc reviewAt nếu là manual pause.

Không dùng exception message, URL, customer ID hoặc event ID làm metric label reason: cardinality có thể tăng vô hạn. Reason label nên là enum bounded; correlation ID chỉ nên nằm trong log/trace.

### 14.1. Một container có nhiều lý do pause

Giả sử circuit breaker yêu cầu pause, trong lúc operator cũng bật maintenance pause. Nếu circuit breaker phục hồi rồi gọi resume() ngay, maintenance pause có thể bị hủy ngoài ý muốn.

Một pause coordinator có thể lưu **tập active reasons**:

~~~text
activeReasons = { CIRCUIT_OPEN, MANUAL_MAINTENANCE }

Circuit phục hồi:
activeReasons = { MANUAL_MAINTENANCE }
=> vẫn paused

Operator kết thúc maintenance:
activeReasons = {}
=> mới yêu cầu resume
~~~

Đây là ứng dụng-specific policy, không phải Kafka container tự reference-count mọi nguyên nhân. Nếu có nhiều nguồn pause/resume, hãy tập trung quyền điều khiển tại một coordinator thay vì để mỗi component tự gọi resume độc lập.

## 15. Pause vì backpressure: hai watermark và hysteresis

Backpressure thường xuất hiện khi downstream xử lý chậm hơn tốc độ record đến. Ví dụ listener đẩy work vào executor queue; khi queue gần đầy, service cần tạm ngừng nhận thêm.

Một policy minh họa:

~~~text
Queue capacity = 10.000 tasks

Queue usage >= 8.000 (80%)
    -> request pause

Queue usage <= 3.000 (30%)
    -> request resume
~~~

Vì ngưỡng pause và resume khác nhau, đây là **hysteresis**. Nó tránh oscillation khi queue dao động quanh một ngưỡng duy nhất:

~~~text
Không có hysteresis:
79% RUN -> 81% PAUSE -> 79% RESUME -> 81% PAUSE ...

Có hysteresis:
80% PAUSE -> 65% still PAUSED -> 30% RESUME
~~~

Theo dõi pause duration để đánh giá tính hiệu quả của policy:

- Nếu pause quá ngắn và lặp rất nhiều, watermark có thể quá sát nhau.
- Nếu pause thường kéo dài hàng chục phút, downstream capacity có thể không đủ.
- Nếu queue đã giảm dưới low watermark nhưng paused age vẫn tăng, resume coordination có thể bị lỗi.
- Nếu resume tạo spike tải lớn, cần ramp-up/concurrency limit thay vì bật toàn bộ ngay.

Không tự động resume chỉ vì pause đã quá thời hạn nếu dependency vẫn đang lỗi. Thời gian là điều kiện **cảnh báo/escalation**, không nhất thiết là điều kiện cưỡng bức tiếp tục.

## 16. Theo dõi thời gian từ pause request đến actual pause

Một độ trễ bị bỏ quên là **pause application latency**.

Ví dụ:

~~~text
Queue vừa đạt 90% lúc 10:00:00
PauseService gọi pause() lúc 10:00:00.050
Listener đang xử lý batch 500 records
Consumer áp dụng pause lúc 10:00:17
~~~

Ở đây queue có thể tiếp tục tăng trong 17 giây sau khi đã request pause. Nếu autoscaling/backpressure chỉ nhìn requested=true, hệ thống có thể tưởng mình đã chặn ingress trong khi thực tế consumer vẫn xử lý records đã fetch.

Nên đo:

~~~text
pause_apply_latency =
  effective_pause_at - pause_requested_at
~~~

Khi latency vượt ngưỡng:

- Xem max.poll.records.
- Xem thời gian xử lý từng record hoặc batch.
- Xem listener có bị blocking ở HTTP/database không.
- Xem pauseImmediate support của Spring Kafka version nếu cần dừng sau record hiện tại.
- Xem CPU starvation/GC pause.
- Xem container có thực sự đang chạy không.

Một lệnh request bị lỗi hoặc container stop trước khi áp dụng không nên bị ghi nhận thành một completed effective pause interval.

## 17. Theo dõi thời gian từ resume request đến actual resume

Tương tự, khi dependency phục hồi:

~~~text
10:05:00  Database healthy
10:05:01  PauseCoordinator gọi resume()
10:05:02  Spring Kafka container áp dụng resume
10:05:04  Listener nhận record mới
~~~

Ở đây:

- Resume application latency: khoảng 1 giây.
- Time-to-first-record sau resume: khoảng 2 giây.
- End-to-end recovery latency: từ database healthy đến record được xử lý thành công.

Nếu resume đã applied mà vẫn không có record, chưa chắc đó là lỗi pause. Topic có thể đang rỗng, partition chưa được assign, consumer lag thực sự bằng 0, listener error handler đang retry hoặc downstream vẫn không sẵn sàng.

Hãy dùng nhiều tín hiệu: resumed event, assigned partitions, lag, records-consumed-rate, listener success count, error rate.

## 18. Rebalance làm pause duration khó đo hơn

Trong Kafka consumer group, partition có thể được thu hồi khỏi một instance và giao cho instance khác. Khi đó, **pause state của một consumer instance** không tương đương với **tình trạng nghiệp vụ của partition xuyên các instances**.

Ví dụ:

~~~text
t=00s  Pod A sở hữu partition 2, paused do queue cao
t=20s  Rebalance xảy ra
t=21s  Partition 2 bị revoke khỏi Pod A
t=25s  Pod B được assign partition 2
t=26s  Pod B có thể bắt đầu xử lý nếu không có policy pause
~~~

Nếu monitor của Pod A cứ giữ interval paused đến khi có resumed event, paused age có thể tăng vô hạn dù Pod A không còn sở hữu partition 2.

Cần có lifecycle-aware tracker:

- Khi partition bị revoked/lost, kết thúc interval pause của assignment cũ với endReason=REVOKED hoặc LOST.
- Khi partition được assign ở consumer mới, mở assignment epoch mới.
- Nếu business policy vẫn muốn pause partition đó, reconcile desired pause state sau assignment.
- Không giả định một local in-memory pause request tự động được chuyển sang Pod khác.
- Không cộng duration của assignment cũ và mới như một khoảng liên tục nếu cần báo cáo thời gian thực tế theo instance.

Với nhu cầu giám sát end-to-end “partition bị ngừng xử lý do policy bao lâu xuyên các owners”, cần lưu desired state và các timestamps ở nơi dùng chung, rồi tổng hợp theo partition/assignment epochs.

## 19. ConsumerRebalanceListener giúp kết thúc interval

Spring Kafka hỗ trợ các callback liên quan tới assign/revoke/lost partitions. Ví dụ tên callback thường gặp qua ConsumerAwareRebalanceListener:

- onPartitionsAssigned.
- onPartitionsRevokedBeforeCommit.
- onPartitionsRevokedAfterCommit.
- onPartitionsLost.

Theo dõi pause nên:

1. Lưu partition assignment hiện tại.
2. Ghi endReason khi partition mất ownership.
3. Xóa gauge stale hoặc đưa active=0 cho assignment đã mất.
4. Khi assign lại, kiểm tra desired pause policy và trạng thái thực tế.
5. Dùng metric riêng cho rebalance duration.

Không cố commit offset hoặc gọi resume như owner cũ sau **onPartitionsLost**. Consumer có thể đã mất quyền xử lý partition.

Event callback không nên thực hiện thao tác chậm với database/HTTP. Nếu cần reconcile desired state từ nơi lưu dùng chung, nên tổ chức một workflow riêng có giới hạn thời gian và xử lý an toàn khi ownership thay đổi.

## 20. ConcurrentMessageListenerContainer: tránh metric gộp sai

Khi @KafkaListener có concurrency lớn hơn 1, Spring Kafka có thể tạo nhiều child consumer containers:

~~~text
orders-listener (concurrency=3)
      |
      +-- child-0 owns partitions [0, 3]
      |
      +-- child-1 owns partitions [1, 4]
      |
      +-- child-2 owns partitions [2, 5]
~~~

Nếu parent container được pause, từng child áp dụng pause theo poll lifecycle. Có thể có khoảng thời gian child-0 đã paused nhưng child-1 vẫn đang xử lý record.

Do đó:

- Parent requested flag phản ánh mong muốn của controller.
- Child effective flags/events phản ánh chuyển trạng thái thực tế từng consumer.
- Partition-level events giúp định vị cụ thể partition nào paused.
- Một boolean parent có thể biểu thị trạng thái tổng hợp, không thay cho metric chi tiết.

Dashboard có thể dùng:

- Số child consumers đã pause / tổng child consumers.
- Số assigned partitions paused / tổng assigned partitions.
- Effective pause age lớn nhất trong các partitions.
- Pause apply latency lớn nhất giữa các children.

Để tránh metrics explosion, có thể lưu chi tiết per-partition trong logs hoặc event store, còn Prometheus chỉ xuất aggregate theo listener/topic/instance khi số partitions rất lớn.

## 21. Kết hợp pause duration với consumer lag

Pause duration một mình chưa cho biết mức độ ảnh hưởng đến dữ liệu. Cần nhìn cùng:

- Committed offset của consumer group.
- Log end offset của từng partition.
- Consumer lag.
- Record arrival rate.
- Oldest unprocessed record age.
- Throughput và processing latency sau resume.

Ví dụ:

~~~text
Partition 2 paused trong 5 phút
Producer ghi thêm 100 records/giây

Backlog tăng lý thuyết:
5 × 60 × 100 = 30.000 records
~~~

Đây chỉ là ước lượng khi partition không được xử lý trong suốt khoảng đó và producer rate không đổi. Lag thực tế còn phụ thuộc committed offset, batches đã fetch, prior backlog, reassignment và ghi nhận tiến độ.

Nếu pause kéo dài nhưng topic không có dữ liệu mới, lag có thể không tăng. Tuy nhiên, **pause policy vẫn có thể cần cảnh báo** khi đáng lẽ đã resume, vì record mới tiếp theo sẽ bị trì hoãn.

Ngược lại, lag tăng không chứng minh consumer đang paused: nó có thể đang xử lý chậm, rebalance, lỗi commit, poison record hoặc read_committed bị LSO giữ lại.

## 22. Retention và backlog khi pause lâu

Kafka lưu record theo retention policy của topic, không theo trạng thái paused của consumer group.

Nếu topic có retention chỉ vài giờ nhưng consumer bị paused lâu hơn, các records chưa được xử lý có thể bị xóa khỏi log theo retention trước khi consumer resume. Khi đó có thể xảy ra offset out-of-range và mất cơ hội replay theo committed offset ban đầu.

Ví dụ:

~~~text
Topic retention: 24 giờ
Consumer paused: 30 giờ
Producer liên tục ghi record
      |
      v
Record cũ được Kafka xóa theo retention
      |
      v
Consumer resume từ committed offset quá cũ
      |
      v
OffsetOutOfRange hoặc reset policy được áp dụng
~~~

Thời gian retention thực tế phụ thuộc segment cleanup, topic configuration và broker behavior; đây là rủi ro tổng quát, không phải một mốc xóa chính xác tại giây thứ 24 giờ.

Do đó, ngưỡng cảnh báo paused age phải xét:

- Topic retention.
- Oldest unprocessed record age.
- SLO xử lý end-to-end.
- Khả năng catch up sau resume.
- Khối lượng record đến trong outage.

Không mặc định rằng giữ group membership nhờ pause đồng nghĩa mọi record sẽ được lưu vô hạn.

## 23. Pause và polling: tránh hiểu nhầm max.poll.interval.ms

Spring Kafka có cơ chế pause container giúp consumer tiếp tục poll ở các chu kỳ phù hợp để giữ consumer group membership khi không giao records cho listener. Điều này khác với việc đặt Thread.sleep rất dài ngay trong listener hoặc chặn consumer poll thread.

Trong nhiều tình huống:

~~~text
Container paused
    |
    +-- KafkaConsumer vẫn poll theo lifecycle
    |
    +-- Kafka group heartbeat/membership vẫn được duy trì
    |
    +-- Listener không được giao record từ partitions paused
~~~

Nhưng **pause không miễn trừ mọi ràng buộc consumer group**. Nếu consumer thread bị chặn trong HTTP call, GC pause, synchronous event handler hoặc một vòng retry không phù hợp, nó vẫn có thể không poll đúng hạn và vi phạm max.poll.interval.ms.

Khi thấy consumer paused và rebalance tăng:

- Xác định container còn poll không.
- Xem listener có in-flight task chưa hoàn thành không.
- Xem pause được yêu cầu trong lúc xử lý batch lớn không.
- Kiểm tra exception/backoff handler.
- Đo pause application latency và poll loop responsiveness.

Không dùng KafkaConsumer.pause() rồi sleep vô hạn trong consumer thread như một cách thay thế container pause API.

## 24. Pause do retry backoff khác manual pause

Spring Kafka có thể dùng các cơ chế backoff gây pause container tạm thời, ví dụ khi phải chờ retry một record mà không muốn giữ poll thread bị chặn quá lâu. Một số cấu hình dùng **ContainerPausingBackOffHandler** hoặc cơ chế tương ứng.

Không phải mọi khoảng chờ retry đều được ghi nhận giống hệt pause do application gọi container.pause(). Khi xây metrics:

- Xác định cơ chế nào tạo pause.
- Kiểm tra các event effective paused/resumed có được phát trong đường đó không.
- Đặt reason riêng như RETRY_BACKOFF thay vì DOWNSTREAM_OVERLOAD.
- Không cộng nhầm elapsed retry backoff thành thời gian pause do operator thủ công.
- Đo thêm retry attempts, retry success và retry duration.

Nếu hệ thống dùng @RetryableTopic, record có thể được chuyển sang retry topic thay vì giữ container chính paused. Topic chính tiếp tục xử lý, còn độ trễ nằm ở retry queue. Không dùng paused duration của consumer chính để đo thời gian record chờ retry topic; cần metric riêng về retry record age và retry topic lag.

## 25. Cumulative paused ratio và availability

Ngoài current paused age, có thể tính **tỷ lệ thời gian paused** trong một cửa sổ:

~~~text
paused_ratio =
    paused_seconds_in_window / window_seconds
~~~

Ví dụ trong 1 giờ, một listener instance có tổng 12 phút ở trạng thái paused:

~~~text
paused_ratio = 12 / 60 = 20%
~~~

Nếu một container có nhiều partitions, định nghĩa ratio phải rõ:

- **Container fully-paused ratio:** thời gian toàn bộ container paused / tổng thời gian.
- **Any-partition-paused ratio:** thời gian ít nhất một partition paused / tổng thời gian.
- **Partition-weighted paused ratio:** partition-seconds / tổng assigned partition-seconds.

Ba số có thể rất khác nhau. Không dùng một tên “pause percentage” mà không ghi rõ mẫu số và aggregation.

Tỷ lệ paused cao có thể là hợp lệ trong maintenance có kiểm soát, nhưng đối với consumer real-time nó thường cảnh báo downstream capacity hoặc policy pause/resume chưa được cân chỉnh.

## 26. Latency sau resume và backlog catch-up

Sau một khoảng pause, cần theo dõi **thời gian từ resume đến khi backlog trở về mức chấp nhận được**. Resume không có nghĩa mọi record đang chờ đã được xử lý.

Một timeline ví dụ:

~~~text
00:00  Consumer pause
05:00  Consumer resume
05:05  Listener xử lý record đầu tiên sau resume
09:00  Consumer lag về dưới 100
~~~

Đại lượng:

- Effective paused duration: 5 phút.
- Time-to-first-success sau resume: 5 giây.
- Backlog catch-up time: 4 phút.
- Total data delay: bao gồm thời gian paused và thời gian chờ trong backlog.

Đặt dashboard gồm **pause age**, **lag**, **processing rate**, **oldest record age** và **estimated drain time** nếu có đủ tốc độ đo đáng tin cậy.

Ước lượng drain time:

~~~text
drain_seconds ≈ backlog_records /
                max(processing_rate - incoming_rate, epsilon)
~~~

Nếu processing rate không cao hơn incoming rate, backlog có thể không giảm; đừng hiển thị ETA chính xác giả khi mẫu số không dương.

## 27. Tự động resume nên phụ thuộc điều kiện thực tế

Một policy backpressure an toàn không nên chỉ chạy cron sau 30 giây để gọi resume() bất kể downstream đã phục hồi hay chưa.

Ví dụ state machine:

~~~text
RUNNING
   |
   | queue >= highWatermark hoặc circuit open
   v
PAUSE_REQUESTED
   |
   | pause applied
   v
PAUSED
   |
   | queue <= lowWatermark
   | AND downstream healthy
   | AND minPauseDuration đã đủ nếu có
   v
RESUME_REQUESTED
   |
   | resume applied
   v
RUNNING
~~~

Một **maximum pause duration** có thể là ngưỡng alert/escalation:

- Sau 60 giây: warning.
- Sau 5 phút: critical hoặc page on-call.
- Sau 15 phút: chuyển sang manual intervention/shed load tùy SLO.

Các mốc chỉ là ví dụ. Ngưỡng thật cần dựa vào business SLO, topic retention, tốc độ ingress và downstream recovery characteristic.

Không cưỡng bức resume khi circuit vẫn open chỉ để metric current paused seconds về 0. Điều đó có thể tạo retry storm hoặc làm dependency outage nặng hơn.

## 28. Tránh pause/resume flapping

Nếu một consumer pause và resume quá thường xuyên:

~~~text
Pause 0.2s
Resume 0.1s
Pause 0.3s
Resume 0.1s
...
~~~

Histogram completed duration sẽ cho nhiều interval rất ngắn. Điều này có thể chỉ ra:

- High/low watermark quá gần nhau.
- Queue size dao động.
- Health check phản ứng quá nhanh với một lỗi đơn lẻ.
- Nhiều components điều khiển cùng một container mà không có coordinator.
- Container sampling khiến requested/effective state không đồng bộ.

Biện pháp:

- Hysteresis với hai ngưỡng.
- Minimum pause duration có giới hạn.
- Consecutive-success threshold trước resume.
- Exponential recovery/backoff phù hợp.
- Điều phối active reasons thay vì nhiều callers gọi resume.
- Theo dõi pause_transition_count và completed pause duration p50/p95.

Không nên làm minimum pause quá dài đến mức vi phạm SLO trong trường hợp downstream phục hồi sớm.

## 29. Metric cardinality và ownership

Một dashboard muốn gắn labels:

~~~text
listener_id
consumer_group
topic
partition
pod
reason
exception_class
event_id
customer_id
~~~

Nhưng event_id và customer_id có cardinality rất cao; nếu đưa trực tiếp vào Micrometer/Prometheus, chi phí lưu trữ/đánh chỉ mục có thể tăng không kiểm soát.

Khuyến nghị:

- Metrics tổng hợp theo listener, topic, group, reason và instance.
- Per-partition metric chỉ khi số partition và retention metrics cho phép.
- Exception class có thể giới hạn theo taxonomy.
- Event ID, correlation ID, command ID đặt trong logs/traces.
- Tắt hoặc expire per-partition meters khi assignment bị revoke nếu instrumentation tạo meter động.
- Có ownership rõ ai được quyền resume manual pause.

Nếu hệ thống cần truy vết lâu dài một partition paused xuyên nhiều pods, lưu pause events có UTC timestamps vào kho bền vững; không ép mọi raw event thành metric timeseries.

## 30. Ví dụ dashboard cho một listener

Một dashboard “Kafka Pause & Backpressure” có thể sắp xếp theo các khối:

**Trạng thái tức thời**

- Listener running / pause requested / effective paused.
- Number of paused child consumers.
- Paused partitions / assigned partitions.
- Pause reason và owner.
- Current pause age, current resume-request latency.

**Tải và hậu quả**

- Consumer lag theo partition.
- Oldest unprocessed record age.
- Producer ingress rate.
- Listener processing throughput.
- Downstream queue depth và connection pool usage.

**Chất lượng điều khiển**

- Pause transitions per minute.
- Completed pause duration p50/p95/p99.
- Pause requested-to-effective latency.
- Resume requested-to-effective latency.
- Pause ratio trong 1 giờ/24 giờ.
- Thời gian backlog catch up sau resume.

**Sức khỏe và vòng đời**

- Consumer assignment/rebalance.
- Container stop/start events.
- Retry/backoff/DLT activity.
- Pod restarts, OOMKill hoặc forced termination.

Đừng tạo dashboard chỉ có gauge paused.active. Nó không giải thích **vì sao** paused, **bao lâu**, và **đến khi nào** cần can thiệp.

## 31. Cảnh báo theo thời gian và mức độ ảnh hưởng

Các loại alert nên có điều kiện rõ ràng:

| Alert | Điều kiện gợi ý | Mục tiêu |
|---|---|---|
| LongEffectivePause | Effective pause age vượt SLO | Phát hiện container/partition bị giữ |
| ResumeStuck | Resume requested nhưng effective paused vẫn true quá lâu | Phát hiện resume không áp dụng |
| PauseRequestStuck | Pause requested nhưng effective state chưa thay đổi quá lâu | Phát hiện listener/poll bị chặn |
| HighPausedPartitionRatio | Tỷ lệ partition paused vượt ngưỡng | Phát hiện giảm năng lực tiêu thụ |
| PauseLagCritical | Paused đồng thời lag và oldest age vượt SLO | Cảnh báo ảnh hưởng dữ liệu |
| PauseFlapping | Nhiều transitions với durations ngắn | Phát hiện policy dao động |
| PausedNearRetention | Oldest record age gần Kafka retention | Bảo vệ cơ hội replay |
| PausedAfterRecovery | Downstream healthy nhưng consumer chưa resume | Phát hiện stale pause state |

Ví dụ Prometheus query **chỉ mang tính minh họa**, với tên metrics do ứng dụng tự export:

~~~promql
max by (listener_id) (
  app_kafka_pause_current_seconds
) > 300
~~~

Một alert tốt nên gắn mô tả:

- Listener/group/topic/instance đang bị ảnh hưởng.
- Paused age và oldest record age.
- Lý do pause, ai/automation đã yêu cầu.
- Link dashboard, log/trace.
- Runbook xử lý.

Đừng trang on-call khi pause theo maintenance plan đã được phê duyệt và vẫn nằm trong thời gian dự kiến; nên dùng suppression/window hoặc alert policy khác, nhưng vẫn đo duration để phát hiện quá hạn.

## 32. Quan sát qua Kafka CLI

Kafka CLI không trực tiếp biết trạng thái **Spring Kafka paused** của một listener container. Tuy nhiên, nó giúp thấy tác động lên consumer group lag và offset.

Ví dụ:

~~~bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server broker1:9092 \
  --describe \
  --group orders-worker
~~~

Kết quả có thể hiển thị:

~~~text
TOPIC          PARTITION CURRENT-OFFSET LOG-END-OFFSET LAG
orders.events  0         1200           1210           10
orders.events  1         500            1250           750
orders.events  2         1180           1181           1
~~~

Nếu partition 1 đã paused, lag 750 có thể phù hợp với việc nó ngừng tiến triển. Nhưng output này **không chứng minh** Spring Kafka đã pause partition 1; cần kết hợp container state, application event/log và metrics.

Lưu ý:

- CURRENT-OFFSET thường là committed next offset của consumer group.
- LOG-END-OFFSET là vị trí cuối log theo cách CLI/broker báo.
- LAG là chênh lệch offset, không phải elapsed time.
- Với read_committed, LSO có thể làm phạm vi dữ liệu đọc được khác LEO.

Để biết paused age, CLI không thay được metrics của ứng dụng hoặc một hệ thống audit pause events.

## 33. Runbook: paused quá lâu nhưng downstream đã khỏe

### Bước 1: Xác nhận requested hay effective

Đọc isPauseRequested(), isConsumerPaused() và các partition-specific flags. Kiểm tra listener ID chính xác, container có running không, assignments hiện tại là gì.

### Bước 2: Xác định lý do và owner

Tìm pauseRequestedAt, reason, caller, incident ID và resume condition. Có manual maintenance reason còn active không? Có circuit open, queue high hoặc rate limit không?

### Bước 3: Kiểm tra bộ điều khiển resume

- Health check đã thật sự báo healthy chưa?
- Low watermark đã đạt chưa?
- Có scheduler/consumer của PauseCoordinator bị lỗi không?
- Một lý do pause khác vẫn active không?
- Có mismatch giữa requested=false và effective=true không?

### Bước 4: Kiểm tra lifecycle và assignment

- Listener có bị stopped không?
- Partition có được revoke/reassign trong thời gian đó không?
- Metric có thuộc pod cũ không?
- Có static membership hoặc rebalances đang diễn ra không?

### Bước 5: Resume có kiểm soát

Chỉ resume khi dependency và năng lực downstream chấp nhận tải. Nếu backlog lớn, có thể ramp concurrency hoặc xử lý từng partition, quan sát queue/latency, tránh thundering herd.

### Bước 6: Xác minh phục hồi

Effective paused age phải kết thúc, completed duration được ghi nhận, records-consumed-rate và processing success tăng, lag/oldest age giảm. Đừng coi resume API return là hoàn tất sự cố nếu consumer vẫn chưa xử lý record mới.

## 34. Runbook: pause request lâu mới có hiệu lực

Triệu chứng: requested=true đã lâu, nhưng effective=false và ingress tiếp tục.

Kiểm tra:

1. Container có đang xử lý một poll batch lớn không?
2. Listener có bị block ở database/HTTP hoặc lock không?
3. max.poll.records, batch listener và concurrency là bao nhiêu?
4. Có GC pause hoặc CPU starvation không?
5. Có cài container pauseImmediate behavior phù hợp trong phiên bản đang chạy không?
6. Consumer thread có đang ở retry/backoff không?
7. Container thực sự running và listener ID đúng không?

Khắc phục ưu tiên giảm công việc không thể preempt trong một poll, đặt timeout dependency và dùng đúng container API. Không gọi trực tiếp KafkaConsumer.pause từ thread quản trị để cưỡng ép chuyển trạng thái, vì KafkaConsumer không thread-safe theo cách đó.

## 35. Runbook: paused và consumer lag tăng nhanh

### Bước 1: Xác định phạm vi

- Bao nhiêu partitions đang paused?
- Lag và oldest record age lớn nhất ở đâu?
- Topic ingress rate hiện tại là bao nhiêu?
- Pause là manual hay backpressure tự động?

### Bước 2: Kiểm tra downstream

- Database connection pool/lock và query latency.
- HTTP service error rate, rate limit, circuit breaker.
- Executor queue depth và worker throughput.
- CPU/memory/throttling của pods.

### Bước 3: Ước lượng khả năng bắt kịp

~~~text
Net drain rate = Processing rate - Incoming rate

Nếu net drain rate <= 0:
  Backlog không thể giảm ổn định

Nếu net drain rate > 0:
  ETA ≈ Backlog / Net drain rate
~~~

Ước lượng cần dùng cửa sổ đủ dài để tránh biến động tức thời, nhất là ngay sau resume.

### Bước 4: Bảo vệ dữ liệu

- So sánh oldest record age với topic retention.
- Không commit offsets của records chưa xử lý.
- Đánh giá có cần bổ sung capacity hoặc giảm ingress.
- Theo dõi DLT/retry nếu consumer vừa resume nhưng record lỗi liên tục.

### Bước 5: Khôi phục và theo dõi

Resume từng bước khi downstream khỏe. Quan sát lag, records-consumed-rate, queue depth, error rate và pause flapping. Nếu lag không giảm sau resume, vấn đề có thể không còn ở pause mà ở throughput hoặc poison record.

## 36. Kiểm thử đo pause duration

Một implementation đo pause nên có tests cho storage/timing semantics của tracker và integration behavior của listener container.

### 36.1. Pause một lần rồi resume

- Gửi pause.
- Chờ actual paused state.
- Để paused trong một khoảng xác định.
- Gửi resume.
- Xác nhận completed duration gần khoảng pause thực, trong tolerance của test clock/scheduling.

### 36.2. Repeated pause không reset timer

- Gọi pause nhiều lần khi đã paused.
- Xác nhận chỉ có một active interval.
- Duration tiếp tục tăng từ transition đầu tiên.
- Completed count tăng đúng một lần khi resume.

### 36.3. Pause requested nhưng chưa effective

- Cho listener đang xử lý record chậm.
- Gọi pause.
- Xác nhận requested=true trước effective=true.
- Đo application latency riêng, không gộp vào effective duration.

### 36.4. Pause/resume rất ngắn

- Tạo một interval ngắn hơn sampling period.
- Xác nhận event-driven instrumentation bắt được nếu yêu cầu độ chính xác.
- Với scheduled sampler, chấp nhận khả năng bỏ sót hoặc tăng sampling frequency phù hợp.

### 36.5. Partition revoke khi paused

- Pause partition.
- Gây rebalance trong test cluster.
- Xác nhận interval cũ được close với endReason=REVOKED/LOST.
- Không còn gauge stale ở owner cũ.
- Desired state được reconcile ở owner mới nếu policy yêu cầu.

### 36.6. Container stop trong lúc paused

- Pause container.
- Stop listener.
- Không tính toàn bộ thời gian container stopped như một pause interval active.
- Đo shutdown separately.
- Start lại, xác nhận tracker không giữ state không còn hợp lệ.

### 36.7. Concurrent consumers và partition pause

- Tạo concurrency lớn hơn 1.
- Pause một partition.
- Xác nhận metrics toàn container không báo mọi partition đều paused.
- Per-partition duration được ghi độc lập.

### 36.8. Backpressure recovery

- Dùng test queue với high/low watermarks.
- Gây pause ở high watermark.
- Hạ queue qua low watermark và xác nhận resume.
- Kiểm tra không flapping, thời gian tới first-success và backlog drain.

## 37. Các sai lầm thiết kế thường gặp

| Sai lầm | Hậu quả | Điều chỉnh |
|---|---|---|
| Đo từ lúc gọi pause() và gọi đó là effective duration | Bao gồm cả thời gian chờ áp dụng | Tách requestedAt và effectivePausedAt |
| Chỉ có paused.active boolean | Không biết pause kéo dài bao lâu | Thêm currentPausedSeconds và completed duration |
| Chỉ dùng Timer cho completed intervals | Pause treo vẫn chưa được đếm | Thêm gauge current pause age |
| Dùng System.currentTimeMillis cho mọi duration | Clock adjustments có thể làm số đo sai | Dùng nanoTime cho elapsed, UTC cho audit |
| Không close interval khi revoke/stop | Gauge tăng vô hạn, stale alerts | Close theo lifecycle reason |
| Lặp pause() rồi reset start timestamp | Luôn thấy paused age nhỏ giả tạo | Chỉ ghi start khi state transition |
| Gộp 3 paused partitions thành 30 giây wall-clock cho 10 giây thực | Hiểu sai ý nghĩa tổng thời gian | Phân biệt partition-seconds và elapsed wall time |
| Một gauge parent che partition paused | Không phát hiện hot/stuck partition | Per-partition hoặc paused partition count |
| Dùng lag để suy đoán paused | Lag có nhiều nguyên nhân | Kết hợp Spring container flags/events |
| Manual resume ghi đè maintenance reason | Resume ngoài ý muốn | Reference-count/set active reasons |
| Auto-resume chỉ vì quá deadline | Downstream còn lỗi, retry storm | Deadline để alert, resume dựa trên health |
| Metric tag là eventId/customerId | Cardinality bùng nổ | Bounded labels, ID ở log/trace |
| Không tính retention | Paused lâu có thể làm record hết hạn | Alert oldest age gần retention |
| Chỉ nhìn thời gian pause, không nhìn catch-up | Đánh giá sai recovery | Theo dõi backlog drain sau resume |
| Không kiểm thử rebalance trong khi paused | Stale state hoặc partition mới xử lý sai policy | Test revoke/assign và reconciliation |

## 38. Checklist production

Trước khi đưa cơ chế theo dõi pause duration vào production:

1. Có định nghĩa rõ **pause requested** và **pause effective** không?
2. Metrics có tách listener-level, child-consumer và partition-level khi cần không?
3. Tracker có dùng monotonic clock cho elapsed durations và UTC timestamp cho incident không?
4. Repeated pause/resume có được deduplicate thành state transitions không?
5. Current paused age có được export ngay cả khi interval chưa kết thúc không?
6. Completed duration có Timer/histogram với labels có kiểm soát không?
7. Requested-to-effective pause và resume latency có được theo dõi không?
8. Mọi pause có reason/owner hoặc nguồn yêu cầu rõ ràng không?
9. Nhiều nguồn pause có coordinator tránh resume quá sớm không?
10. Partition revoke/lost, container stop và shutdown có đóng telemetry interval đúng lý do không?
11. Sau rebalance, desired pause state có được reconcile ở owner mới khi cần không?
12. Có dashboard kết hợp paused age, lag, oldest record age và downstream health không?
13. Ngưỡng long pause có xét SLO, Kafka retention và ingress rate không?
14. Auto-resume có kiểm tra low watermark và dependency health, tránh retry storm không?
15. Metric labels có tránh event/customer ID cardinality cao không?
16. Có đo pause ratio theo định nghĩa container hay partition-seconds rõ ràng không?
17. Có theo dõi time-to-first-success và catch-up time sau resume không?
18. Đã test requested-vs-effective, repeated commands, rebalance, stop, concurrency và forced shutdown chưa?
19. Có runbook cho paused quá lâu, resume không áp dụng và lag tăng không?
20. Đội vận hành có biết khi nào pause là an toàn và khi nào cần chuyển sang stop/rebalance hoặc thay đổi capacity không?

**Kết luận:** Theo dõi thời gian paused trong Spring Kafka cần nhiều hơn một boolean trạng thái. Hãy đo từ lúc **effective pause** tới khi **effective resume**, đồng thời tách thời gian chờ áp dụng request, thống kê completed intervals, phân biệt pause theo partition và lý do vận hành. Khi kết hợp duration với consumer lag, tuổi record, retention, downstream health và rebalance lifecycle, hệ thống sẽ phát hiện được cả hai tình huống nguy hiểm: **pause có chủ đích nhưng bị quên** và **resume đã yêu cầu nhưng consumer chưa thực sự tiếp tục**. Một pipeline đáng tin cậy phải đo được thời gian tạm dừng, lý do tạm dừng và khả năng bắt kịp dữ liệu sau khi phục hồi.
