# ListenerContainerNoLongerIdleEvent

Trong **Spring Kafka**, **ListenerContainerNoLongerIdleEvent** là một **application event** được phát khi một **message listener container đã được nhận diện là idle** bắt đầu **nhận record trở lại**. Event này đánh dấu bước chuyển từ **không có records được nhận trong một khoảng thời gian** sang **có dữ liệu được chuyển đến consumer/container**, giúp hệ thống vận hành phân biệt “đầu vào tạm im lặng” với “luồng dữ liệu vừa hoạt động trở lại”.

Đây là tín hiệu quan sát **dòng records tại listener container**, không phải lời xác nhận rằng nghiệp vụ vừa xử lý thành công, cũng không tự khẳng định consumer group đã phục hồi hoàn toàn. Ví dụ, một record vừa được fetch có thể kích hoạt sự kiện no-longer-idle nhưng listener sau đó vẫn ném exception. Muốn kết luận pipeline khỏe trở lại, phải kết hợp event với listener success rate, consumer lag, downstream health và recovery metrics.

Để event này có ý nghĩa, ứng dụng cần **cấu hình phát hiện idle** cho listener container, phổ biến thông qua **ContainerProperties.setIdleEventInterval(...)**. Spring Kafka sẽ theo dõi khoảng thời gian container không nhận records và có thể phát **ListenerContainerIdleEvent**. Khi record đến sau trạng thái idle đã được ghi nhận, framework có thể phát **ListenerContainerNoLongerIdleEvent** tương ứng.

Bài học tập trung vào điều kiện phát event, cách lắng nghe an toàn, ý nghĩa của các thuộc tính, tác động của concurrency, pause/rebalance, cách đo thời gian idle và cách vận hành khi traffic quay lại.

## 1. Vì sao cần biết container “không còn idle”?

Một hệ thống event-driven có thể có các giai đoạn không có traffic hoàn toàn bình thường:

- Topic chỉ có dữ liệu trong giờ làm việc.
- Producer publish theo batch mỗi vài phút.
- Một partition nhận rất ít records vì key distribution.
- Một pipeline tạm yên sau khi xử lý hết backlog.
- Upstream dừng phát trong lúc bảo trì.
- Consumer tạm pause vì backpressure, rồi resume.

Khi dữ liệu bắt đầu đến lại, vận hành thường muốn biết:

1. Container nào vừa chuyển từ idle sang active?
2. Khoảng idle kéo dài bao lâu?
3. Các partitions nào thuộc phạm vi container đó?
4. Có records thực sự được xử lý thành công hay chỉ vừa đến?
5. Consumer lag có bắt đầu giảm không?
6. Sự kiện có xảy ra sau một pause/rebalance hoặc upstream outage không?
7. Có nên ngừng cảnh báo “no traffic” hay còn cần xác minh thêm?

**ListenerContainerNoLongerIdleEvent** trả lời phần quan trọng: **container đã nhận dữ liệu trở lại sau giai đoạn được nhận diện là idle**. Các câu hỏi về business success và health vẫn cần quan sát độc lập.

## 2. Idle và no-longer-idle trong vòng đời container

Giả sử container đang được assign partition và đã nhận record gần nhất ở thời điểm T0.

~~~text
T0          Container nhận một record
T0 + 5s     Không có record mới
T0 + 10s    Đạt idleEventInterval, framework phát idle event
T0 + 20s    Vẫn chưa có record; có thể tiếp tục phát idle events
T0 + 25s    Container nhận một record mới
T0 + 25s    Phát no-longer-idle event theo cơ chế của phiên bản
T0 + 25s+   Container tiếp tục nhận và xử lý dữ liệu
~~~

Các thời điểm chỉ minh họa. Idle detection và application event dispatch phụ thuộc nhịp poll, scheduler của container, thread processing, giá trị interval và phiên bản Spring Kafka; không nên coi event là một bộ hẹn giờ tuyệt đối chính xác ở mili giây.

~~~mermaid
stateDiagram-v2
    [*] --> RECEIVING
    RECEIVING --> IDLE: Không nhận records đủ idleEventInterval
    IDLE --> IDLE: Tiếp tục không có records
    IDLE --> RECEIVING: Record đến, phát NoLongerIdleEvent
    RECEIVING --> IDLE: Lại không nhận records đủ interval
~~~

Mỗi lần nhận record khi container đang hoạt động bình thường **không đồng nghĩa có một NoLongerIdleEvent**. Event có ý nghĩa vì **đã có trạng thái idle trước đó**.

## 3. So sánh với ListenerContainerIdleEvent

Hai events bổ sung cho nhau:

| Event | Khi nào xuất hiện | Điều nó cho biết |
|---|---|---|
| **ListenerContainerIdleEvent** | Container không nhận records trong khoảng idle được cấu hình | Container đang idle theo quy tắc phát hiện |
| **ListenerContainerNoLongerIdleEvent** | Container bắt đầu nhận record sau khi đã idle | Dòng records đã quay lại ở container |
| **ListenerContainerPartitionIdleEvent** | Một partition được nhận diện idle, ở phiên bản hỗ trợ | Idle ở cấp TopicPartition |
| **ListenerContainerPartitionNoLongerIdleEvent** | Một partition bắt đầu có record lại sau idle, ở phiên bản hỗ trợ | Chuyển trạng thái ở cấp partition |

Một container có nhiều partitions có thể nhận dữ liệu đều ở P0 nhưng không có dữ liệu ở P1. Trong trường hợp đó, **container-level event** có thể không thể hiện đúng tình trạng idle của riêng P1. Nếu cần giám sát partition-by-partition, chọn partition-specific events/metrics theo phiên bản thay vì suy từ một event chung.

Quan trọng: **ListenerContainerNoLongerIdleEvent không phải là event ghi nhận “listener method đã thành công”**. Nó có thể xuất hiện trước khi nghiệp vụ hoàn tất hoặc trước khi offset tương ứng được commit.

## 4. Điều kiện để event được phát

Trong cấu hình thông thường, cần bật cơ chế idle detection của listener container bằng một **idleEventInterval dương**.

Thứ tự điển hình:

1. Container được start và có khả năng poll/receive records.
2. Không có records được nhận trong khoảng idleEventInterval.
3. Container phát idle event và ghi nhận trạng thái idle.
4. Một record được nhận trở lại ở container.
5. Spring Kafka phát **ListenerContainerNoLongerIdleEvent**.

Nếu **idleEventInterval không được bật** hoặc quá lớn so với khoảng im lặng thực tế, ứng dụng có thể không thấy idle event và do đó cũng không có chuyển trạng thái no-longer-idle đáng quan sát.

Một khoảng trống 2 giây giữa các messages thường **không tạo event** nếu idleEventInterval bằng 30 giây.

Sự kiện này dựa trên **records được container nhận**, không phải việc producer đã gửi message ở phía upstream. Producer gửi thành công chưa chứng minh consumer đã fetch record; consumer có thể paused, không có assignment, đang rebalance, không đủ quyền hoặc đang đọc ở vị trí khác.

## 5. Cấu hình idleEventInterval

Ví dụ Spring Kafka listener factory:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;

@Configuration
public class KafkaListenerFactoryConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
    ordersListenerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

        factory.setConsumerFactory(consumerFactory);

        // Phát hiện container idle với ngưỡng minh họa 10 giây.
        factory.getContainerProperties()
                .setIdleEventInterval(10_000L);

        return factory;
    }
}
~~~

Listener sử dụng factory:

~~~java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {

    private final OrderService service;

    public OrderListener(OrderService service) {
        this.service = service;
    }

    @KafkaListener(
        id = "ordersListener",
        topics = "orders.events",
        groupId = "order-service",
        containerFactory = "ordersListenerFactory"
    )
    public void onOrder(OrderEvent event) {
        service.process(event);
    }
}
~~~

**10_000L là mili giây**, tương đương 10 giây. Đây là ngưỡng minh họa, không phải mức phù hợp cho mọi hệ thống.

Khi định nghĩa listener factory riêng, cần giữ các cấu hình khác mà ứng dụng yêu cầu, chẳng hạn message converter, concurrency, AckMode, error handler, transaction manager và customizers. Nếu listener không thực sự dùng factory đã bật idle detection, bạn có thể không nhận được events như mong đợi.

## 6. Lựa chọn idleEventInterval

Giá trị interval nên dựa trên **traffic pattern** và **mục tiêu giám sát**, không chỉ dựa vào con số tròn dễ nhớ.

| Loại workload | Khoảng trống dữ liệu bình thường | Cách chọn ngưỡng |
|---|---|---|
| Payment events liên tục | Rất ít khoảng trống dài | Có thể chọn ngưỡng tương đối ngắn để phát hiện upstream im lặng |
| Batch import mỗi 10 phút | Không có record giữa các batch | Ngưỡng 10 giây có thể tạo idle/no-longer-idle mỗi batch, điều này có thể là expected |
| Low-volume admin events | Vài giờ không có record | Ngưỡng ngắn dễ sinh nhiều telemetry ít giá trị |
| IoT burst traffic | Nhiều đợt burst và khoảng nghỉ | Chọn interval theo chu kỳ burst/SLA |
| Operational heartbeat topic | Có nhịp ổn định | Có thể lấy một vài lần chu kỳ kỳ vọng làm ngưỡng |

Nếu đặt interval quá thấp, hệ thống có thể tạo **nhiều cặp idle/no-longer-idle** do traffic tự nhiên dao động. Nếu đặt quá cao, không thể phản ánh nhanh một outage ngắn.

Để tránh cảnh báo nhiễu, phân biệt ngưỡng **phát event** với ngưỡng **gửi alert**. Ví dụ, nhận event sau 30 giây idle không nhất thiết phải gửi cảnh báo cấp cao; SLA upstream có thể là 5 phút.

## 7. Lắng nghe event với @EventListener

Spring cho phép lắng nghe application events bằng **@EventListener**.

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ListenerContainerNoLongerIdleEvent;
import org.springframework.stereotype.Component;

@Component
public class KafkaActivityEventLogger {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaActivityEventLogger.class);

    @EventListener
    public void onNoLongerIdle(
            ListenerContainerNoLongerIdleEvent event) {

        log.info(
            "Kafka listener no longer idle: listenerId={}, idleMs={}, partitions={}",
            event.getListenerId(),
            event.getIdleTime(),
            event.getTopicPartitions()
        );
    }
}
~~~

Ví dụ sử dụng các thuộc tính thường gặp của event như **listener ID**, **idle time** và **topic partitions**. Tên getters/API chính xác có thể khác theo Spring Kafka version; đối chiếu dependency hiện tại khi biên dịch.

Callback nên **ngắn và không blocking**. Logging và tăng metric thường phù hợp. Không gọi trực tiếp REST API, database transaction dài hoặc thực hiện một tác vụ hồi phục phức tạp trong synchronous event handler.

Mục tiêu của handler là **ghi nhận chuyển trạng thái hoạt động trở lại**, không biến nó thành bước xử lý nghiệp vụ bắt buộc trước khi listener tiếp tục.

## 8. Các thuộc tính cần hiểu

Tùy phiên bản Spring Kafka, event cung cấp những thông tin tương tự:

| Thuộc tính | Ý nghĩa vận hành |
|---|---|
| **listenerId** | Định danh container/listener phát event |
| **idleTime** | Khoảng thời gian idle mà event báo cáo, thường theo mili giây |
| **topicPartitions** | Những TopicPartition liên quan tới consumer/container phát event |
| **consumer** | Consumer liên quan, nếu API phiên bản cung cấp |
| **paused** | Thông tin trạng thái pause trong những phiên bản hỗ trợ |
| **source/container** | Nguồn phát event theo Spring application event model |

Một số lưu ý:

- **idleTime** không đồng nghĩa processing latency của record đầu tiên sau idle.
- **topicPartitions** là phạm vi assignment liên quan; không tự khẳng định record vừa nhận đến từ **mọi partition** trong danh sách đó.
- **listenerId** hữu ích để phân loại service/container; với concurrency, ID có thể có suffix child container.
- **consumer** chỉ nên được truy cập theo quy tắc thread safety của KafkaConsumer.
- **paused** hoặc state liên quan giúp giải thích rằng không có record vì pause, không nhất thiết vì upstream không hoạt động.

Không dựa vào event duy nhất để suy ra **key, value, offset hay business result** của record vừa đến. Những dữ liệu đó nên được ghi tại listener hoặc interceptor theo chính sách bảo mật.

## 9. Listener ID và concurrent containers

Một **ConcurrentMessageListenerContainer** có thể tạo nhiều child listener containers/consumers. Khi @KafkaListener có **concurrency = 3**, mỗi child consumer có assignment và nhịp nhận records riêng.

Ví dụ:

~~~java
@KafkaListener(
    id = "ordersListener",
    topics = "orders.events",
    groupId = "order-service",
    concurrency = "3"
)
public void onOrder(OrderEvent event) {
    service.process(event);
}
~~~

Ở những phiên bản Spring Kafka thường gặp, child container IDs có thể có dạng tương tự:

~~~text
ordersListener-0
ordersListener-1
ordersListener-2
~~~

Vì thế, handler chỉ lọc bằng phép bằng chính xác "ordersListener" có thể bỏ sót events của child containers, tùy nguồn event và phiên bản.

Một ví dụ filtering an toàn theo convention của ứng dụng:

~~~java
@EventListener
public void onNoLongerIdle(ListenerContainerNoLongerIdleEvent event) {
    String listenerId = event.getListenerId();

    if (listenerId == null
            || !listenerId.startsWith("ordersListener")) {
        return;
    }

    log.info(
        "orders listener resumed traffic: id={}, idleMs={}",
        listenerId,
        event.getIdleTime()
    );
}
~~~

Khi nhiều listener IDs có tiền tố giống nhau, cần kiểm tra cấu trúc ID để tránh bắt nhầm. Có thể giữ một tập IDs hoặc mapping được quản lý rõ thay vì phụ thuộc duy nhất vào startsWith.

**Một child container hết idle không có nghĩa mọi child container khác đều đã có dữ liệu.** Một consumer có thể được assign hot partition, consumer khác có thể ở partition ít traffic và vẫn idle.

## 10. Application event publication và luồng xử lý

Theo cấu hình Spring application events thông thường, một **ApplicationEventMulticaster đồng bộ** dispatch event listener trong thread đang publish event. Với các Kafka container events, đây có thể là **consumer thread**.

Nếu @EventListener chạy lâu, nó có thể làm consumer poll/dispatch chậm, tăng processing lag và thậm chí ảnh hưởng điều kiện **max.poll.interval.ms** khi cộng với listener processing quá lâu.

Không nên:

~~~java
@EventListener
public void onNoLongerIdle(
        ListenerContainerNoLongerIdleEvent event) {

    // Không nên: remote call blocking trong consumer event callback.
    remoteMonitoringApi.postActivityState(event.toString());
}
~~~

Nên:

- Ghi structured log ngắn.
- Tăng counter hoặc cập nhật timestamp gauge.
- Gửi tín hiệu nhỏ sang một queue nội bộ giới hạn nếu cần xử lý thêm.
- Dùng async event handling có kiểm soát nếu thật sự cần network I/O.
- Giữ lỗi telemetry không làm phá luồng consumer.

Lưu ý: nếu chuyển event handling sang thread khác bằng **@Async** hoặc async event multicaster, **không sử dụng KafkaConsumer từ event.getConsumer() trên thread đó**. KafkaConsumer có yêu cầu thread confinement, và việc gọi pause/seek/commit tùy ý từ thread khác có thể tạo lỗi hoặc race.

## 11. Cảnh báo về getConsumer()

Một số Kafka listener container events có thể mang tham chiếu **KafkaConsumer**. Tham chiếu này chỉ có ích trong bối cảnh thread phù hợp và không có nghĩa application được phép điều khiển consumer ở mọi nơi.

Điểm cần nhớ:

1. KafkaConsumer nói chung không thread-safe.
2. Spring Kafka container là owner của consumer loop.
3. Async @EventListener thường chạy ngoài consumer thread.
4. Gọi consumer.seek(), commitSync(), pause() hoặc resume() từ thread ngoài có thể không an toàn.
5. Việc nhận event no-longer-idle không phải lý do tự seek hoặc commit.
6. Nếu muốn điều khiển flow, ưu tiên API **MessageListenerContainer.pause()/resume()** hoặc **pausePartition()/resumePartition()** do container cung cấp.

Nếu cần tương tác với consumer tại đúng thread và API của framework cho phép, hãy làm trong callback được thiết kế cho điều đó với hiểu biết rõ lifecycle. Với bài toán observability, chỉ ghi nhận event attributes thường đã đủ.

## 12. Không đồng nhất “no longer idle” với “consumer healthy”

Event báo hiệu container **đã nhận được record trở lại**. Nó **không chứng minh**:

- Listener đã xử lý record không lỗi.
- Business side effect đã commit ở database.
- Kafka offset đã được commit.
- Consumer group lag đã giảm xuống 0.
- Mọi assigned partitions đều nhận data.
- Retry/DLT queue đã được drain.
- Downstream HTTP API hoặc database đã phục hồi.
- Tất cả application instances đều hoạt động bình thường.

Ví dụ:

~~~text
Container IDLE trong 60 giây
    |
    v
Record mới đến
    |
    v
ListenerContainerNoLongerIdleEvent
    |
    v
Listener ném IllegalArgumentException
    |
    v
DefaultErrorHandler -> DLT
~~~

No-longer-idle event đã xảy ra, nhưng nghiệp vụ vẫn thất bại. Nếu một dashboard lập tức đổi trạng thái toàn service sang “HEALTHY” chỉ dựa vào event này, nó có thể che một outage ở downstream.

Tốt hơn nên có hai trạng thái độc lập:

- **Input activity:** active hoặc idle.
- **Processing health:** success, erroring, paused, lagging hoặc unavailable.

## 13. Phân biệt idle container với consumer không poll

Đây là đối chiếu rất quan trọng trong **Spring Kafka Reliability Operations**.

| Tình huống | Poll loop | Records | Sự kiện/số liệu có ích |
|---|---|---|---|
| Topic rỗng, consumer khỏe | Poll đều | Không có | ListenerContainerIdleEvent |
| Topic nhận data lại | Poll đều | Có | ListenerContainerNoLongerIdleEvent |
| Listener/consumer thread bị block | Poll có thể gián đoạn | Không xử lý tiến | NonResponsiveConsumerEvent, poll metrics, thread dump |
| Consumer paused | Poll thường vẫn tiếp diễn | Không dispatch từ paused partitions | ConsumerPausedEvent, pause state, idle metrics |
| Consumer ngừng | Không tiếp tục poll sau stop | Không có | Lifecycle events |
| Không được assign partition | Poll/group activity có thể vẫn diễn ra | Không có từ assignment đó | Assignment/rebalance metrics |

**NonResponsiveConsumerEvent** phản ánh việc container nhận diện poll không tiến đúng hạn theo cơ chế giám sát của Spring Kafka; nó không đồng nghĩa với ListenerContainerIdleEvent.

Ví dụ topic không có record 10 phút nhưng consumer poll đều đặn: đó có thể chỉ là idle, không phải non-responsive. Ngược lại, một listener bị deadlock làm consumer không poll có thể chưa tạo no-longer-idle event dù upstream đang gửi nhiều records.

## 14. Pause/resume và NoLongerIdleEvent

Một container bị **pause** sẽ tạm ngừng nhận dữ liệu từ paused partitions, nhưng thường vẫn poll để duy trì group membership. Khi resume và nhận record, container có thể phát no-longer-idle nếu trước đó đã đạt trạng thái idle phù hợp với phiên bản/cấu hình.

Tuy nhiên, không nên tự động kết luận:

~~~text
ConsumerResumedEvent == ListenerContainerNoLongerIdleEvent
~~~

Hai events có ý nghĩa khác:

- **ConsumerResumedEvent:** việc resume consumer/partition đã được áp dụng.
- **ListenerContainerNoLongerIdleEvent:** dữ liệu lại được nhận sau một giai đoạn idle.

Resume có thể diễn ra khi topic vẫn rỗng, khi đó chưa có record và chưa thể kết luận container “no longer idle”. Ngược lại, một container có thể tự thoát idle vì producer gửi record mới mà không có pause/resume nào.

Nếu hệ thống có backpressure, hãy ghi đồng thời pause state, resume event, idle/no-longer-idle và actual processing throughput để thấy đúng quá trình phục hồi.

## 15. Idle event trong consumer có Kafka transaction

Với transactional Kafka processing, event vẫn chủ yếu là tín hiệu **nhận records**, không phải transaction commit.

Giả sử:

1. Container nhận một record sau thời gian idle.
2. NoLongerIdleEvent được publish.
3. Transactional listener bắt đầu xử lý.
4. Listener gửi output records qua KafkaTemplate.
5. Database hoặc Kafka transaction thất bại.
6. Transaction abort; input có thể được redeliver.

Event ở bước 2 không chứng minh transaction ở bước 5 thành công. Khi đánh giá xử lý đáng tin cậy, cần kết hợp với:

- Transaction commit/abort metrics.
- Listener processing duration.
- Offset commit/transactional offsets.
- AfterRollbackProcessor activity.
- DLT/recovery outcomes.

Nếu input consumer dùng **read_committed**, một upstream open transaction có thể làm records chưa được trả cho consumer dù producer đã gửi bytes lên Kafka. Container có thể trông idle cho tới khi transaction được commit và records trở nên đọc được theo isolation setting.

## 16. Container-level event và partition-level event

Một consumer có thể được assign nhiều partitions. Khi P0 có data liên tục còn P1 không có record trong vài giờ, container-level idle detection có thể không cho thấy vấn đề của P1.

Nếu Spring Kafka version hỗ trợ, có thể cấu hình/quan sát **partition idle** qua property và events tương ứng. Ví dụ một số phiên bản có **ContainerProperties.setIdlePartitionEventInterval(...)** để phát hiện partition riêng bị idle.

~~~java
factory.getContainerProperties()
        .setIdleEventInterval(30_000L);

// Nếu phiên bản hỗ trợ partition idle detection:
factory.getContainerProperties()
        .setIdlePartitionEventInterval(60_000L);
~~~

Đối với partition-specific event:

~~~java
import org.springframework.kafka.event
        .ListenerContainerPartitionNoLongerIdleEvent;

@EventListener
public void onPartitionNoLongerIdle(
        ListenerContainerPartitionNoLongerIdleEvent event) {

    log.info("Kafka partition is active again: {}", event);
}
~~~

Đoạn code thứ hai minh họa tên event/API trong các phiên bản hỗ trợ; cần đối chiếu chính xác package và khả năng cung cấp metadata của dependency.

Dùng partition-level observability khi mục tiêu là phát hiện **hot/cold partition**, mất cân đối key distribution hoặc một partition chưa được producer ghi đúng như thiết kế.

## 17. Structured logging cho chuyển trạng thái

Một event log nên đủ thông tin để người vận hành truy được listener nào hoạt động trở lại mà không làm tăng số lượng log vô hạn.

Ví dụ:

~~~text
event=kafka_listener_no_longer_idle
service=orders-service
listener_id=ordersListener-1
consumer_group=order-service
idle_duration_ms=45123
assigned_partition_count=2
container_state=RUNNING
timestamp=2026-11-15T10:15:30Z
~~~

Đây là format minh họa, không phải log mặc định của Spring Kafka. Consumer group, container state và service có thể cần được bổ sung bằng application configuration, vì không phải mọi trường đều có sẵn trực tiếp trong event ở mọi phiên bản.

Các trường nên cân nhắc:

- Service, environment và version.
- Listener ID hoặc child container ID.
- Khoảng idle được event báo cáo.
- Topic/partitions liên quan.
- Pause state nếu có.
- Thời điểm event.
- Nguyên nhân kỳ vọng, nếu hệ thống có ngữ cảnh bảo trì hoặc recovery.

Không log message payload, credentials hoặc dữ liệu nhạy cảm chỉ để ghi nhận state chuyển từ idle sang active.

## 18. Metric cho ListenerContainerNoLongerIdleEvent

Một số metric phù hợp:

| Metric | Ý nghĩa |
|---|---|
| **kafka.listener.no_longer_idle.events** | Counter số lần container thoát idle |
| **kafka.listener.idle.events** | Counter số lần container được nhận diện idle |
| **kafka.listener.reported_idle_duration** | Histogram/distribution của khoảng idle |
| **kafka.listener.last_activity_timestamp** | Thời điểm có dấu hiệu records quay lại |
| **kafka.listener.processing.success** | Counter xử lý nghiệp vụ thành công, đo riêng |
| **kafka.listener.processing.failure** | Counter lỗi nghiệp vụ, đo riêng |
| **kafka.consumer.lag** | Backlog của group/partition |
| **kafka.consumer.poll.rate** | Kiểm tra poll loop |
| **kafka.listener.paused** | Container có bị pause không |
| **kafka.listener.assignment.count** | Có partition assignment không |

Tên metrics là **convention gợi ý**, không phải tất cả được Spring Kafka tự tạo sẵn. Với Micrometer, có thể đăng ký custom counter/timer trong một event listener.

Không dùng offset, event ID, key hoặc full exception message làm metric tags. Chỉ dùng low-cardinality dimensions như service, listener ID chuẩn hóa, topic và environment.

Với concurrent containers, nếu listener ID gồm suffix số child, cardinality thường có giới hạn nhưng có thể thay đổi khi scale-out; xem xét aggregation theo logical listener ID ở dashboard.

## 19. Ví dụ kết hợp Micrometer

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ListenerContainerNoLongerIdleEvent;
import org.springframework.stereotype.Component;

import java.util.concurrent.TimeUnit;

@Component
public class KafkaIdleTransitionMetrics {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaIdleTransitionMetrics.class);

    private final MeterRegistry registry;

    public KafkaIdleTransitionMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    @EventListener
    public void onNoLongerIdle(
            ListenerContainerNoLongerIdleEvent event) {

        String listenerId = event.getListenerId();

        registry.counter(
                "kafka.listener.no.longer.idle.events",
                "listener", listenerId
        ).increment();

        registry.timer(
                "kafka.listener.reported.idle.duration",
                "listener", listenerId
        ).record(
                Math.max(0L, event.getIdleTime()),
                TimeUnit.MILLISECONDS
        );

        log.info(
            "Listener active again: id={}, idleMs={}",
            listenerId,
            event.getIdleTime()
        );
    }
}
~~~

Ví dụ giả định MeterRegistry đã được ứng dụng cung cấp qua Micrometer/Actuator và event getters của phiên bản tương thích. Để tránh cardinality quá cao, không đưa các trường định danh từng record vào tags. Nếu listener IDs được tạo động hoặc có số lượng rất lớn, chuẩn hóa logical listener ID trước khi dùng làm tag.

Metric này đo **số lần thoát idle** và **độ dài idle theo event**, không đo transaction commit success hoặc end-to-end business latency.

## 20. Đừng cảnh báo mỗi lần no-longer-idle

Một số hệ thống hoạt động theo nhịp: idle 30 giây, nhận burst data, idle tiếp. Khi đó việc NoLongerIdleEvent xuất hiện nhiều lần có thể bình thường.

Các cách alert hợp lý hơn:

- Idle kéo dài quá SLA đối với topic lẽ ra phải có traffic.
- Consumer lag tăng đồng thời với quá ít records xử lý.
- Listener vừa no-longer-idle nhưng processing failure rate tăng đột ngột.
- No-longer-idle events tạo **flapping** ngoài nhịp traffic dự kiến.
- Một partition vẫn idle trong khi những partitions khác nhận records đều và business contract đòi phân phối đồng đều.
- Sau upstream recovery, không có listener success dù đã có no-longer-idle event.
- Container không poll, thay vì chỉ không nhận records.

Nếu mục tiêu là chỉ thông báo “traffic quay lại”, có thể tạo informational event/log. Không cần mặc định gửi pager notification cho mỗi lần nhận records sau idle.

## 21. Idleness và throughput thấp

**Idle** không phải thuật ngữ đồng nghĩa với **throughput thấp**.

Ví dụ:

| Trường hợp | Có idle event? | Nhận xét |
|---|---|---|
| Không có record nào trong 60 giây, idle threshold 30 giây | Có thể có | Container không nhận dữ liệu đủ lâu |
| Mỗi 10 giây nhận một record, threshold 30 giây | Thường không | Throughput thấp nhưng chưa đạt idle interval |
| Consumer nhận records nhanh nhưng listener lỗi liên tục | Thường không | Không idle, nhưng pipeline không healthy |
| Consumer paused | Có thể trông idle theo cơ chế/phiên bản | Cần kiểm tra pause state |
| Consumer không có assignment | Không nhận records | Không suy ra upstream không gửi |
| read_committed đợi upstream transaction | Có thể không nhận record | Data có thể đã nằm trong broker nhưng chưa visible |

Vì vậy, một event no-longer-idle chỉ giúp xác định **dòng records đã quay lại sau khoảng im lặng đủ dài**, không mô tả trung bình records/sec trên một khoảng thời gian lớn.

## 22. Tương tác với retry và DLT

Trong hệ thống có **DefaultErrorHandler**, lần giao lại của record lỗi có thể ảnh hưởng quan sát về việc container “có nhận record” theo implementation và loại retry. Không nên tự suy ra một NoLongerIdleEvent luôn đại diện cho **một business event hoàn toàn mới**.

Trong hệ thống dùng **@RetryableTopic**, mỗi retry topic có thể có listener container riêng. Một listener trên retry topic có thể idle rồi no-longer-idle khi retry record đến, trong khi listener topic gốc vẫn active hoặc ngược lại.

Các điểm vận hành:

- Phân biệt logical listener ID và retry-stage listener IDs.
- Không cộng no-longer-idle ở tất cả retry containers rồi xem là số lượng business events mới.
- DLT listener có thể no-longer-idle khi record lỗi đến; điều đó **không phải recovery thành công**.
- Khi downstream outage, consumer lag và retry/DLT ingress có thể tăng ngay sau khi event báo input active.
- Cần metrics listener success, recovery success và publish failure riêng.

Nếu có event-based automation, đừng kích hoạt replay DLT chỉ vì DLT listener no-longer-idle; replay cần chính sách nghiệp vụ và idempotency.

## 23. Ảnh hưởng của rebalance và restart

Một container có thể mất/gain partition assignment trong consumer group rebalance. Khi assignment thay đổi, nguồn records và trạng thái idle detection có thể thay đổi theo.

Ví dụ:

1. Consumer C1 đang idle vì được assign ít traffic.
2. Consumer C2 rời group.
3. Rebalance chuyển một hot partition sang C1.
4. C1 nhận record.
5. C1 có thể chuyển từ idle sang active.

NoLongerIdleEvent trong tình huống này **không nhất thiết có nghĩa producer vừa khởi động lại**. Nó có thể đơn giản xuất phát từ **partition assignment mới**.

Sau restart, state idle trước đó ở container cũ không nhất thiết được giữ như một business state bền vững. Không thiết kế logic dùng NoLongerIdleEvent như một marker duy nhất xuyên process restarts.

Trong dashboard, kết hợp các mốc:

- Container started/stopped.
- Partitions assigned/revoked.
- Idle/no-longer-idle events.
- Pause/resume events.
- Consumer lag và records-consumed-rate.

Nhờ đó có thể phân biệt upstream traffic recovery với rebalance và thay đổi assignment.

## 24. Khi container đã idle nhưng không có NoLongerIdleEvent

Một số nguyên nhân:

| Triệu chứng | Giải thích có thể |
|---|---|
| Producer đã gửi nhưng không có event | Record chưa được container fetch/nhận |
| Container không còn running | Không còn consumer loop để nhận record |
| Consumer group đọc topic/partition khác | Record không thuộc assignment |
| Consumer paused | Chưa dispatch dữ liệu từ paused partitions |
| isolation.level=read_committed | Output transactional chưa committed nên chưa visible |
| Deserializer hoặc poll failure | Consumer chưa chuyển record thành luồng xử lý bình thường |
| Listener factory không bật idleEventInterval | Không có cơ chế idle detection cần thiết |
| Chưa từng phát idle event | Không có trạng thái idle trước đó để chuyển sang no-longer-idle |
| Event handler không được đăng ký | Sự kiện có thể được phát nhưng application không lắng nghe |
| Event listener filter sai ID | Concurrent child IDs khác với ID mong đợi |
| ApplicationEventMulticaster tùy biến | Dispatch/async/error behavior khác mặc định |

Không vội kết luận Spring Kafka “mất event”. Cần xác minh cấu hình, trạng thái container, assignment và điều kiện thực sự của no-longer-idle.

## 25. Khi event xuất hiện nhưng dữ liệu vẫn chưa xử lý thành công

Đây là một tình huống đặc biệt cần tách biệt.

~~~text
NoLongerIdleEvent at 12:00:00
Listener exception at 12:00:00.050
DefaultErrorHandler retry
DLT recovery at 12:00:04
Consumer group lag remains high
~~~

Event báo **đã có record đến sau idle**. Nó không bảo đảm:

- Record không bị lỗi deserialize hoặc conversion.
- Retry đã hoàn tất.
- DLT publish thành công.
- Business state đã được ghi database.
- Offset đã được commit.

Nếu muốn xác nhận luồng xử lý phục hồi, có thể dùng một state machine do ứng dụng quản lý:

~~~text
INPUT_IDLE
  |
  v
INPUT_ACTIVE_OBSERVED
  |
  +--> PROCESSING_HEALTHY   (sau khi thấy success metrics đạt điều kiện)
  |
  +--> PROCESSING_ERRORING  (khi failure rate cao)
~~~

Không chuyển thẳng từ INPUT_IDLE sang PROCESSING_HEALTHY chỉ dựa vào ListenerContainerNoLongerIdleEvent.

## 26. Ví dụ giám sát trạng thái ứng dụng

Một thành phần giám sát đơn giản có thể lưu timestamp gần nhất của lần container no-longer-idle để hiển thị status.

~~~java
import java.time.Instant;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ListenerContainerNoLongerIdleEvent;
import org.springframework.stereotype.Component;

@Component
public class ListenerActivitySnapshot {

    private final Map<String, Instant> lastReturnFromIdle =
            new ConcurrentHashMap<>();

    @EventListener
    public void onNoLongerIdle(
            ListenerContainerNoLongerIdleEvent event) {

        lastReturnFromIdle.put(
                event.getListenerId(),
                Instant.now()
        );
    }

    public Instant lastReturnFromIdle(String listenerId) {
        return lastReturnFromIdle.get(listenerId);
    }
}
~~~

Đây là **in-memory diagnostic state**. Nó mất khi restart và chỉ ghi nhận những lần **thoát idle**, không cập nhật theo mọi record mới. Không dùng nó làm nguồn sự thật cho business checkpoint hoặc SLA xuyên restart.

Nếu cần audit dài hạn, phát metric/log ra hệ thống observability hoặc ghi durable activity state có giới hạn, tránh thực hiện synchronous database write trong consumer event callback.

## 27. Kiểm thử bằng EmbeddedKafka hoặc Testcontainers

Để kiểm chứng điều kiện phát no-longer-idle, nên dùng broker trong integration test. Unit test tạo event object thủ công chỉ xác minh event listener, không chứng minh container phát event đúng lúc.

Kịch bản:

1. Tạo Kafka topic và consumer group riêng cho test.
2. Cấu hình listener factory có **idleEventInterval** ngắn nhưng đủ ổn định.
3. Khởi động container và đợi assigned partition.
4. Không publish records trong một khoảng lớn hơn ngưỡng idle.
5. Xác nhận **ListenerContainerIdleEvent** xuất hiện.
6. Publish một record hợp lệ vào topic test.
7. Chờ **ListenerContainerNoLongerIdleEvent**.
8. Xác nhận listener ID/partitions và thời gian idle hợp lý.
9. Xác nhận listener method thực sự nhận record.
10. Đợi một thời gian ngắn hơn idleEventInterval rồi publish record khác; không mặc định có thêm no-longer-idle event.
11. Đợi container idle lần nữa rồi publish record, xác nhận một vòng chuyển trạng thái mới.
12. Dọn context/group và topics nếu cần.

Dùng **polling assertion hoặc latch có timeout** thay vì Thread.sleep cố định làm điều kiện pass/fail. Không yêu cầu event phải xuất hiện chính xác ở mốc mili giây vì scheduling và poll timing có thể thay đổi.

## 28. Ví dụ recorder cho integration test

Một test support bean có thể thu thập tên event và listener IDs:

~~~java
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ListenerContainerIdleEvent;
import org.springframework.kafka.event.ListenerContainerNoLongerIdleEvent;
import org.springframework.stereotype.Component;

@Component
public class IdleTransitionRecorder {

    private final List<String> transitions =
            new CopyOnWriteArrayList<>();

    @EventListener
    public void onIdle(ListenerContainerIdleEvent event) {
        transitions.add("IDLE:" + event.getListenerId());
    }

    @EventListener
    public void onActive(
            ListenerContainerNoLongerIdleEvent event) {
        transitions.add("ACTIVE:" + event.getListenerId());
    }

    public List<String> transitions() {
        return List.copyOf(transitions);
    }

    public void clear() {
        transitions.clear();
    }
}
~~~

Trong integration test:

- Đợi recorder thấy IDLE của listener mục tiêu.
- Publish một Kafka record.
- Đợi ACTIVE của listener phù hợp.
- Kiểm tra listener processing counter hoặc latch độc lập.
- Không phụ thuộc thứ tự giữa các events của nhiều child containers nếu concurrency cao.
- Dùng test context riêng hoặc reset recorder giữa tests để tránh contamination.

Các records đầu tiên sau startup có thể tạo activity trước khi idle timer đạt ngưỡng; cần thiết kế timing test rõ ràng.

## 29. Kiểm thử concurrency và partition-specific idle

Với **concurrency=2** và topic có ít nhất hai partitions:

1. Đợi assignment ổn định cho từng child consumer.
2. Gửi liên tục records vào P0; không gửi P1.
3. Quan sát container-level idle events theo child assignment.
4. Đối chiếu child listener IDs trong event.
5. Nếu cần partition-level behavior, bật các partition idle events được Spring Kafka version hỗ trợ.
6. Gửi record vào P1 sau khoảng idle.
7. Xác nhận event phù hợp với partition nhận dữ liệu trở lại.
8. Kiểm tra một child/partition active không làm bạn suy luận toàn group đã active.

Nếu cả hai partitions được assign vào cùng một consumer, container-level event có thể không tách được P0 và P1. Test phải xác nhận assignment trước khi assert behavior của child containers.

Đây là lý do phân biệt container-level và partition-level no-longer-idle rất quan trọng.

## 30. Kiểm thử pause và resume

Một test khác:

1. Khởi động listener và đợi assignment.
2. Gọi container.pause() và chờ actual paused state.
3. Chờ idle detection theo cấu hình trong điều kiện phù hợp.
4. Publish record khi consumer đang paused.
5. Kiểm tra record chưa được listener nhận khi vẫn paused.
6. Gọi container.resume().
7. Chờ actual resumed state.
8. Xác nhận record được nhận.
9. Quan sát có no-longer-idle event hay không theo điều kiện trạng thái idle của phiên bản.
10. Kiểm tra consumer lag và offset ack/commit.

Quan trọng: **Không dùng sự xuất hiện của ConsumerResumedEvent để thay thế assertion cho ListenerContainerNoLongerIdleEvent**. Chúng là những sự kiện khác nghĩa.

Nếu test có records đã poll trước pause, chúng có thể còn in-flight; cần loại trừ khỏi assertion nhận record mới.

## 31. Runbook: không nhận được NoLongerIdleEvent

Khi upstream thông báo “đã gửi data lại” nhưng không thấy event:

1. Xác minh service, listener ID, container factory và group ID.
2. Kiểm tra **idleEventInterval** đã được bật trên đúng container.
3. Kiểm tra **ListenerContainerIdleEvent** có từng xuất hiện trước đó không.
4. Xác nhận listener container running và có assignment.
5. Kiểm tra topic/partition thực tế mà producer đã ghi.
6. Kiểm tra consumer paused state hoặc partition pause.
7. Kiểm tra isolation.level và upstream transactional commit nếu có.
8. Kiểm tra poll rate, NonResponsiveConsumerEvent và consumer thread health.
9. Kiểm tra deserialization, conversion, authorization và broker errors.
10. Kiểm tra filter listener ID, nhất là child IDs khi concurrency lớn.
11. Xác minh @EventListener bean được scan và application event multicaster configuration.
12. Gửi một record test hợp lệ qua đúng topic/partition theo quy trình an toàn.
13. Đối chiếu event, listener invocation và committed offsets.
14. Nếu event vẫn không xuất hiện, ghi lại Spring Kafka version và event APIs của version đó để điều tra.

Không sửa bằng cách ép một fake NoLongerIdleEvent rồi đánh dấu pipeline đã healthy; việc đó che lỗi cấu hình hoặc lỗi consumer thực sự.

## 32. Runbook: event xuất hiện nhưng pipeline vẫn lỗi

Khi NoLongerIdleEvent xuất hiện sau outage nhưng business metrics vẫn xấu:

1. Ghi lại thời điểm và listener ID của event.
2. Kiểm tra processing success/failure sau thời điểm đó.
3. Đối chiếu consumer group lag theo partition.
4. Kiểm tra error handler retries, DLT ingress và recovery failures.
5. Kiểm tra database/API latency và availability.
6. Xác định listener có nhận records nhưng fail trước commit không.
7. Kiểm tra transactional commit/abort nếu container transactional.
8. Kiểm tra side effects có idempotency khi record redelivery không.
9. Với retry topics, đối chiếu status của từng retry listener container.
10. Chỉ đổi trạng thái incident sang recovered khi business health tiêu chí được đáp ứng.

Event có thể là **dấu hiệu đầu tiên của traffic recovery**, nhưng không phải bằng chứng cuối cùng của service recovery.

## 33. Những hiểu nhầm thường gặp

**Mỗi record mới đều phát NoLongerIdleEvent.** Không đúng: event dành cho chuyển từ idle sang nhận dữ liệu trở lại.

**Có record producer gửi thì event chắc chắn xuất hiện.** Không đúng: consumer phải thực sự nhận record sau một trạng thái idle phù hợp.

**Không cấu hình idleEventInterval vẫn mong event.** Cần bật idle detection.

**NoLongerIdleEvent chứng minh nghiệp vụ xử lý thành công.** Event chỉ nói về input activity.

**NoLongerIdleEvent tương đương ConsumerResumedEvent.** Resume là điều khiển pause; no-longer-idle là dữ liệu đến sau idle.

**Idle container đồng nghĩa không poll.** Consumer vẫn có thể poll đều khi topic không có dữ liệu.

**Idle container đồng nghĩa consumer bị treo.** Cần đối chiếu với NonResponsiveConsumerEvent và poll metrics.

**Một child container active nghĩa cả group active.** Concurrent containers có assignment và hoạt động khác nhau.

**topicPartitions của event là toàn bộ partitions vừa nhận record.** Nó có thể chỉ mô tả assignment liên quan, không phải danh sách records gây event.

**Gọi consumer APIs từ async event handler luôn an toàn.** KafkaConsumer không thread-safe.

**NoLongerIdleEvent phải tạo pager alert.** Trong traffic bursty, event có thể là bình thường.

**Dùng event làm durable audit state.** Application events và bộ nhớ local không thay thế log/metric bền vững.

## 34. Checklist cho production

**Cấu hình**

- [ ] idleEventInterval được đặt trên đúng listener factory/container.
- [ ] Ngưỡng idle phản ánh traffic pattern và SLA.
- [ ] Có xử lý ListenerContainerIdleEvent và ListenerContainerNoLongerIdleEvent khi cần.
- [ ] Đã phân biệt container-level và partition-level events.
- [ ] Listener ID và child container IDs được lọc đúng.

**An toàn runtime**

- [ ] Event handlers nhẹ, không blocking consumer thread.
- [ ] Không gọi KafkaConsumer từ async thread.
- [ ] Không dùng NoLongerIdleEvent để commit/seek offsets.
- [ ] Không tự coi event là processing success.
- [ ] Có giải thích sự kiện trong trạng thái paused/rebalance.

**Observability**

- [ ] Có structured logs listenerId/idleTime/partitions.
- [ ] Có metric no-longer-idle count và idle duration.
- [ ] Có processing success/error metrics riêng.
- [ ] Dashboard đối chiếu consumer lag, poll rate và assignment.
- [ ] Alert được đặt theo SLA, tránh flapping khi burst traffic.

**Kiểm thử**

- [ ] Có integration test idle → nhận record → no-longer-idle.
- [ ] Có test không nhận event trên mọi record tiếp theo.
- [ ] Có test concurrency/child listener IDs.
- [ ] Có test pause/resume và input trở lại.
- [ ] Có test event xuất hiện nhưng listener processing thất bại.
- [ ] Có runbook khi event không xuất hiện đúng mong đợi.

## 35. Kết luận

**ListenerContainerNoLongerIdleEvent** là tín hiệu Spring Kafka application event cho biết **listener container đã nhận được record sau khi từng được nhận diện idle**. Nó bổ sung cho ListenerContainerIdleEvent, giúp ghi nhận giai đoạn luồng dữ liệu quay lại sau một khoảng im lặng.

Muốn sử dụng đúng, hãy bật **idleEventInterval**, lắng nghe event qua **@EventListener**, ghi lại listener ID và khoảng idle, hiểu trạng thái của concurrent child containers, và giữ callback nhẹ để không ảnh hưởng consumer thread. Đặc biệt, không đồng nhất event này với consumer resume, transaction commit hoặc xử lý nghiệp vụ thành công.

Trong vận hành Spring Kafka, NoLongerIdleEvent hữu ích như một **chỉ báo input activity**. Kết hợp nó với **processing success, consumer lag, poll metrics, DLT/retry, pause/rebalance và downstream health** để biết liệu hệ thống thật sự phục hồi sau khoảng idle hay chỉ vừa nhận thêm một record mới.
