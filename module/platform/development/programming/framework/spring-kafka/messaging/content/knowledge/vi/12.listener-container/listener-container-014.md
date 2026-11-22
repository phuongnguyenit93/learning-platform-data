# Theo dõi trạng thái container

Trong Spring Kafka, `@KafkaListener` không trực tiếp gọi `KafkaConsumer.poll()` trong phương thức nghiệp vụ. Listener container quản lý Kafka consumer, vòng lặp poll, phân phối record, commit offset và vòng đời của consumer. Khi vận hành ứng dụng, cần theo dõi container để biết listener đang chạy, đã dừng, đang được yêu cầu pause hay đã pause thực sự, đồng thời phát hiện tình trạng không nhận record hoặc consumer không phản hồi.

Spring Kafka cung cấp `KafkaListenerEndpointRegistry`, các API trên `MessageListenerContainer`, application events và metrics của Kafka client để quan sát trạng thái. Kết hợp các nguồn này giúp phân biệt một container đang chạy bình thường nhưng topic không có dữ liệu với một consumer bị kẹt, mất assignment hoặc gặp vấn đề kết nối.

## 1. Listener container quản lý những gì?

Khi ứng dụng khai báo `@KafkaListener`, Spring tạo listener endpoint và đăng ký container quản lý endpoint đó. Container sử dụng `ConsumerFactory` để tạo Kafka consumer, gọi `poll()`, chuyển record tới listener và xử lý acknowledgement/commit theo cấu hình.

Với listener concurrency bằng một, thường có một `KafkaMessageListenerContainer`. Khi concurrency lớn hơn một, Spring tạo `ConcurrentMessageListenerContainer` làm container cha và nhiều container con, mỗi container con quản lý một Kafka consumer riêng.

```text
KafkaListenerEndpointRegistry
          |
          +---- orders-listener
          |          |
          |          +---- ConcurrentMessageListenerContainer
          |                    |
          |                    +---- KafkaMessageListenerContainer (consumer 0)
          |                    +---- KafkaMessageListenerContainer (consumer 1)
          |                    +---- KafkaMessageListenerContainer (consumer 2)
          |
          +---- payments-listener
                     |
                     +---- KafkaMessageListenerContainer
```

Sơ đồ trên minh họa một ứng dụng có listener orders concurrency bằng ba và listener payments concurrency bằng một. Mỗi consumer con có vòng đời và assignment riêng, trong khi container cha đại diện cho listener endpoint có concurrency.

## 2. Truy vấn container qua KafkaListenerEndpointRegistry

`KafkaListenerEndpointRegistry` quản lý các container được tạo từ listener endpoint, thường là các endpoint khai báo bằng `@KafkaListener`. Có thể inject registry để lấy danh sách ID, lấy container theo ID hoặc duyệt các container đã đăng ký.

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.stereotype.Service;

@Service
class KafkaContainerStatusService {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaContainerStatusService.class);

    private final KafkaListenerEndpointRegistry registry;

    KafkaContainerStatusService(KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void logContainerStates() {
        for (String listenerId : registry.getListenerContainerIds()) {
            MessageListenerContainer container =
                    registry.getListenerContainer(listenerId);

            if (container == null) {
                continue;
            }

            log.info(
                    "listenerId={}, running={}, pauseRequested={}, paused={}",
                    listenerId,
                    container.isRunning(),
                    container.isPauseRequested(),
                    container.isContainerPaused()
            );
        }
    }
}
```

Các phương thức quan trọng:

| API | Ý nghĩa |
|---|---|
| `getListenerContainerIds()` | Lấy các ID listener đã đăng ký trong registry |
| `getListenerContainer(id)` | Lấy container theo listener ID |
| `getListenerContainers()` | Lấy các container được registry quản lý |
| `isRunning()` | Cho biết container đang ở trạng thái chạy theo lifecycle |
| `isPauseRequested()` | Cho biết đã có yêu cầu pause |
| `isContainerPaused()` | Cho biết container đã thực sự pause |

Registry quản lý các endpoint được đăng ký với nó. Một `MessageListenerContainer` được ứng dụng tự khai báo như bean riêng không nhất thiết xuất hiện trong registry; khi đó cần theo dõi bean đó trực tiếp.

## 3. Phân biệt running, pause requested và paused

Không nên gộp mọi trạng thái thành một cờ `running`. Container có thể đang chạy nhưng đã nhận yêu cầu pause và đang chờ tới điểm an toàn trong vòng poll để pause consumer.

| Trạng thái quan sát | Diễn giải | Hướng xử lý |
|---|---|---|
| `isRunning() == false` | Container chưa chạy hoặc đã dừng | Kiểm tra lifecycle, startup lỗi hoặc yêu cầu stop |
| `isRunning() == true`, `isPauseRequested() == false` | Container đang hoạt động và chưa có yêu cầu pause | Theo dõi assignment, poll và lưu lượng record |
| `isPauseRequested() == true`, `isContainerPaused() == false` | Pause đã được yêu cầu nhưng consumer chưa hoàn tất pause | Chờ sự kiện pause hoặc kiểm tra listener đang xử lý |
| `isContainerPaused() == true` | Container đã pause | Xác định ai yêu cầu pause và khi nào resume |

Ví dụ, gọi `pause()` không có nghĩa consumer lập tức ngừng mọi hoạt động. Container phối hợp việc pause với vòng poll; consumer vẫn cần duy trì hoạt động quản lý group theo cơ chế của Kafka. Vì vậy, `isPauseRequested()` và `isContainerPaused()` trả lời hai câu hỏi khác nhau.

Để tiếp tục nhận record, có thể gọi `resume()` trên container. Khi quản trị qua registry, hãy kiểm tra container tồn tại và trạng thái trước khi gửi lệnh:

```java
public void pauseOrders() {
    MessageListenerContainer container =
            registry.getListenerContainer("orders-listener");

    if (container != null && container.isRunning()
            && !container.isPauseRequested()) {
        container.pause();
    }
}

public void resumeOrders() {
    MessageListenerContainer container =
            registry.getListenerContainer("orders-listener");

    if (container != null && container.isRunning()
            && container.isPauseRequested()) {
        container.resume();
    }
}
```

Pause thường dùng khi cần kiểm soát tải hoặc tạm ngừng xử lý trong thời gian ngắn. Stop kết thúc container và đóng consumer; đây là thao tác lifecycle khác với pause.

## 4. Theo dõi container cha và container con

Khi dùng `concurrency`, registry trả về container đại diện cho listener endpoint. Nếu cần quan sát chi tiết từng consumer con, có thể kiểm tra kiểu `ConcurrentMessageListenerContainer` và duyệt danh sách child container.

```java
import org.springframework.kafka.listener.ConcurrentMessageListenerContainer;
import org.springframework.kafka.listener.MessageListenerContainer;

public void logChildContainerStates() {
    MessageListenerContainer container =
            registry.getListenerContainer("orders-listener");

    if (container instanceof ConcurrentMessageListenerContainer<?, ?> concurrent) {
        int index = 0;
        for (MessageListenerContainer child : concurrent.getContainers()) {
            log.info(
                    "listenerId=orders-listener, childIndex={}, running={}, paused={}",
                    index++,
                    child.isRunning(),
                    child.isContainerPaused()
            );
        }
    }
}
```

Container cha có thể đang chạy trong khi một child consumer gặp vấn đề hoặc chưa được gán partition. Theo dõi từng child giúp phát hiện tình trạng không đồng đều giữa các consumer, nhất là khi concurrency cao. Hậu tố client ID và consumer metrics có thể hỗ trợ ghép thông tin child với số liệu Kafka client.

Không suy luận rằng child có index `0` luôn đọc partition `0`. Partition assignment do Kafka assignor quyết định và có thể thay đổi sau rebalance.

## 5. Theo dõi trạng thái bằng application events

Spring Kafka phát các application event trong những thời điểm quan trọng của listener container và consumer. Ứng dụng có thể lắng nghe các event để ghi log, cập nhật dashboard hoặc gửi cảnh báo.

Một số event thường hữu ích:

| Event | Thông tin quan sát |
|---|---|
| `ListenerContainerIdleEvent` | Container không nhận record trong khoảng idle đã cấu hình |
| `ListenerContainerNoLongerIdleEvent` | Container nhận record trở lại sau giai đoạn idle |
| `NonResponsiveConsumerEvent` | Consumer không hoàn tất `poll()` trong khoảng theo dõi |
| `ConsumerPausedEvent` / `ConsumerResumedEvent` | Consumer con đã pause hoặc resume |
| `ContainerPausedEvent` / `ContainerResumedEvent` | Container đã hoàn tất pause hoặc resume |
| `ConsumerStartedEvent` / `ConsumerStoppedEvent` | Vòng đời consumer con bắt đầu hoặc kết thúc |
| `ContainerStoppedEvent` | Listener container đã dừng |

Danh sách event và một số phương thức có thể khác theo phiên bản Spring Kafka. Hãy đối chiếu API của phiên bản dự án khi cần đọc thêm thuộc tính của event.

### Cấu hình idle event

Có thể cấu hình `idleEventInterval` trên `ContainerProperties` để container phát `ListenerContainerIdleEvent` khi không nhận record trong khoảng thời gian đã đặt.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;

@Configuration
class KafkaListenerEventConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, String>
            eventAwareKafkaListenerContainerFactory(
                    ConsumerFactory<String, String> consumerFactory) {

        var factory = new ConcurrentKafkaListenerContainerFactory<String, String>();
        factory.setConsumerFactory(consumerFactory);
        factory.getContainerProperties().setIdleEventInterval(60_000L);
        return factory;
    }
}
```

Listener dùng factory này bằng thuộc tính `containerFactory`:

```java
@KafkaListener(
        id = "orders-listener",
        topics = "orders.events",
        groupId = "order-projection",
        containerFactory = "eventAwareKafkaListenerContainerFactory"
)
public void consume(String payload) {
    process(payload);
}
```

### Nhận idle và non-responsive events

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ListenerContainerIdleEvent;
import org.springframework.kafka.event.NonResponsiveConsumerEvent;
import org.springframework.stereotype.Component;

@Component
class KafkaContainerEventObserver {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaContainerEventObserver.class);

    @EventListener
    public void onIdle(ListenerContainerIdleEvent event) {
        log.info(
                "Kafka listener idle: listenerId={}, idleTime={}, partitions={}",
                event.getListenerId(),
                event.getIdleTime(),
                event.getTopicPartitions()
        );
    }

    @EventListener
    public void onNonResponsive(NonResponsiveConsumerEvent event) {
        log.warn(
                "Kafka consumer not responsive: listenerId={}, timeSinceLastPoll={}, partitions={}",
                event.getListenerId(),
                event.getTimeSinceLastPoll(),
                event.getTopicPartitions()
        );
    }
}
```

Idle event không tự động có nghĩa consumer lỗi. Topic có thể không phát sinh dữ liệu, consumer group có thể chưa được gán partition hoặc producer đang ngừng gửi. Ngược lại, `NonResponsiveConsumerEvent` là tín hiệu cần điều tra vì poll có thể đang bị treo hoặc consumer thread bị chặn.

Các event thường được phát từ luồng container/consumer. Listener event nên thực hiện nhanh, tránh gọi dịch vụ bên ngoài hoặc xử lý blocking kéo dài. Nếu chuyển event sang executor bất đồng bộ, không sử dụng đối tượng `Consumer` gắn trong event từ một thread khác vì Kafka consumer không thread-safe.

## 6. Theo dõi lifecycle start, stop, pause và resume

Ngoài idle và non-responsive, có thể lắng nghe event vòng đời để ghi lại thời điểm container hoặc consumer thay đổi trạng thái. Ví dụ, `ContainerStoppedEvent` cho biết container đã dừng; `ConsumerPausedEvent` và `ConsumerResumedEvent` cho biết trạng thái pause của consumer con.

Nên ghi các trường nhận diện sau trong log lifecycle:

- Listener ID để biết endpoint nào thay đổi trạng thái.
- Client ID hoặc thông tin consumer con nếu cần phân biệt concurrency.
- Topic và partition khi event cung cấp thông tin assignment.
- Thời điểm event và nguyên nhân stop nếu API event của phiên bản đang dùng cung cấp.

Không nên chỉ ghi một thông báo chung như “Kafka stopped”. Khi có nhiều listener, log cần xác định được container nào dừng và trạng thái trước đó là gì.

## 7. Metrics giúp biết container có đang tiến triển

Trạng thái `isRunning()` chỉ cho biết container đang chạy theo lifecycle. Nó không chứng minh consumer đang nhận record, đang có assignment hay đang xử lý thành công. Để đánh giá tiến triển, cần kết hợp metrics của Kafka consumer, consumer group lag và metrics nghiệp vụ.

Các chỉ số Kafka client thường hữu ích gồm:

| Chỉ số | Ý nghĩa vận hành |
|---|---|
| `records-consumed-rate` | Tốc độ record consumer đọc được |
| `records-lag-max` | Độ trễ lớn nhất giữa vị trí consumer và log end offset trên các partition được theo dõi |
| `fetch-rate` | Tần suất fetch request |
| `fetch-latency-avg` | Độ trễ fetch trung bình |
| `bytes-consumed-rate` | Tốc độ dữ liệu consumer đọc |
| `commit-latency-avg` | Độ trễ commit offset trung bình |
| `poll-idle-ratio-avg` | Tỷ lệ thời gian consumer không bận xử lý record giữa các lần poll, theo định nghĩa metric của Kafka client |

Tên metric, phạm vi và khả năng xuất phụ thuộc phiên bản Kafka client, số liệu có sẵn và hệ thống metrics đang dùng. `records-lag-max` cũng cần được đọc cùng trạng thái assignment; khi consumer chưa có partition, không thể kết luận lag bằng không có nghĩa là luồng đã khỏe.

Có thể lấy metrics từ `MessageListenerContainer.metrics()` ở các phiên bản Spring Kafka hỗ trợ API này:

```java
import org.apache.kafka.common.Metric;
import org.apache.kafka.common.MetricName;
import java.util.Map;

public void inspectKafkaMetrics() {
    MessageListenerContainer container =
            registry.getListenerContainer("orders-listener");

    if (container == null) {
        return;
    }

    Map<MetricName, ? extends Metric> metrics = container.metrics();
    metrics.forEach((name, metric) -> {
        log.debug(
                "Kafka metric: name={}, group={}, value={}",
                name.name(),
                name.group(),
                metric.metricValue()
        );
    });
}
```

Với concurrent container, metrics có thể tổng hợp từ consumer con và metric name có thể chứa tag `client-id`. Không nên đưa toàn bộ metric vào log ở mỗi lần poll; hãy xuất chúng qua hệ thống monitoring với chu kỳ phù hợp và chọn những metric phục vụ cảnh báo.

## 8. Kết hợp trạng thái container với consumer group lag

Một dashboard vận hành tốt nên kết hợp ít nhất ba lớp thông tin:

1. **Lifecycle:** container có chạy không, có pause không, có event stop hoặc non-responsive không.
2. **Kafka progress:** consumer có assignment không, tốc độ đọc thế nào, lag tăng hay giảm, commit có thành công không.
3. **Business processing:** listener xử lý thành công bao nhiêu sự kiện, thời gian xử lý, số lỗi, retry và dead-letter.

Ví dụ cách diễn giải:

| Trạng thái container | Record rate / lag | Cách điều tra |
|---|---|---|
| Running, không pause | Record rate bằng 0, lag bằng 0 | Có thể topic không có dữ liệu mới; kiểm tra producer và lưu lượng đầu vào |
| Running, không pause | Record rate bằng 0, lag tăng | Kiểm tra assignment, poll, kết nối broker, listener bị block và non-responsive event |
| Running, paused | Lag tăng | Xác định yêu cầu pause, thời gian pause và điều kiện resume |
| Stopped | Lag tăng | Kiểm tra lifecycle, startup failure, shutdown hoặc lỗi cấu hình |
| Running | Record rate cao nhưng xử lý lỗi tăng | Kiểm tra deserialization, handler, retry, dependency và dead-letter |

Không dùng riêng consumer lag để kết luận ứng dụng khỏe hay lỗi. Lag bằng không trong lúc topic không có record mới là bình thường; lag tăng cũng có thể do producer đẩy dữ liệu nhanh hơn khả năng xử lý dù consumer vẫn hoạt động đúng.

## 9. Quy trình chẩn đoán khi container bất thường

Khi dashboard cho thấy listener không xử lý record như dự kiến, hãy kiểm tra theo trình tự:

1. Dùng registry tìm đúng listener ID và xác nhận container có tồn tại.
2. Kiểm tra `isRunning()`, `isPauseRequested()` và `isContainerPaused()`.
3. Kiểm tra event start/stop, idle, non-responsive, pause/resume gần thời điểm xảy ra sự cố.
4. Kiểm tra assignment và consumer group membership để biết consumer có partition hay không.
5. Đối chiếu record rate, lag, fetch latency, poll và commit metrics.
6. Kiểm tra log listener, exception, retry, dead-letter và thời gian xử lý dependency.
7. Nếu container đã dừng, tìm nguyên nhân startup/shutdown hoặc lỗi khiến context dừng; chỉ start lại sau khi hiểu trạng thái và điều kiện vận hành.

Tránh tự động gọi `start()` mỗi khi `isRunning()` trả về false mà không kiểm tra nguyên nhân. Container có thể đã được chủ động stop để bảo trì hoặc ứng dụng đang shutdown. Tự khởi động lại trong những trường hợp đó có thể làm sai ý định vận hành.

## 10. Những nhầm lẫn thường gặp

1. **Cho rằng `isRunning() == true` nghĩa là consumer đang đọc record.** Container có thể chạy nhưng không có dữ liệu, chưa được gán partition hoặc đang gặp vấn đề poll.
2. **Coi pause requested là paused hoàn tất.** `isPauseRequested()` và `isContainerPaused()` phản ánh hai thời điểm khác nhau trong quá trình pause.
3. **Coi idle event là lỗi.** Idle chỉ cho biết container không nhận record trong khoảng thời gian đã cấu hình; cần đối chiếu lưu lượng đầu vào và assignment.
4. **Coi container cha là một consumer duy nhất khi concurrency lớn hơn một.** Concurrent container quản lý nhiều child consumer; nên quan sát child khi cần chẩn đoán chi tiết.
5. **Dùng event listener để làm công việc blocking.** Event được phát trong ngữ cảnh container; xử lý chậm có thể ảnh hưởng luồng consumer.
6. **Chỉ xem consumer lag.** Lag phải được đọc cùng record rate, assignment, lifecycle và lỗi nghiệp vụ.
7. **Tự động restart mọi container stopped.** Container có thể được dừng có chủ đích hoặc context đang đóng; cần xác định nguyên nhân trước khi start.

Theo dõi trạng thái container hiệu quả cần kết hợp API lifecycle, application events, metrics Kafka client và consumer group lag. Trong Spring Kafka, registry giúp tìm đúng listener, container API cho biết trạng thái chạy/pause, còn event và metrics cho biết consumer có thực sự tiến triển hay đang gặp vấn đề. Nhờ đó, đội vận hành có thể phân biệt thiếu dữ liệu đầu vào, pause có chủ đích và sự cố consumer để xử lý đúng nguyên nhân.
