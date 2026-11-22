# monitorInterval

Trong Spring Kafka, việc một consumer **không nhận được record** và việc nó **không còn poll bình thường** là hai trạng thái rất khác nhau. Topic có thể hoàn toàn không có dữ liệu nhưng consumer vẫn khỏe mạnh, liên tục gọi KafkaConsumer.poll() để duy trì group membership. Ngược lại, listener hoặc Kafka client có thể bị kẹt khiến vòng poll ngừng tiến triển dù topic đang có dữ liệu cần xử lý.

**monitorInterval** là thuộc tính của Spring Kafka listener container dùng để quy định **chu kỳ kiểm tra consumer có đang phản hồi hay không**. Nó phối hợp với pollTimeout và noPollThreshold để phát hiện một consumer lâu không thực hiện được nhịp poll bình thường, rồi phát **NonResponsiveConsumerEvent** cho ứng dụng quan sát.

Bài này thuộc chủ đề **Idle và non-responsive**. Trọng tâm không chỉ là đặt một con số monitorInterval, mà là hiểu bộ ba cấu hình, phân biệt idle với consumer bị kẹt, kiểm soát cảnh báo giả, tìm nguyên nhân và xử lý an toàn mà không làm mất offset hoặc tạo vòng lặp rebalance.

## 1. Hai trạng thái: idle và non-responsive

Hãy xét hai consumer cùng đăng ký topic orders.events.

**Consumer A: topic không có message mới**

    Consumer A:
      poll() -> empty
      poll() -> empty
      poll() -> empty
      ...
      poll() vẫn được gọi đều đặn

Consumer A có thể **idle**, nhưng vẫn đang hoạt động bình thường. Nó duy trì heartbeat và group membership, sẵn sàng nhận dữ liệu mới.

**Consumer B: vòng poll ngừng tiến triển**

    Consumer B:
      poll() -> records
      xử lý / thao tác khác
      thread bị block quá lâu
      ...
      chưa quay lại poll()

Hoặc một trường hợp khác:

    Consumer B:
      gọi poll()
      poll() không trả về trong khoảng thời gian dự kiến
      ...
      không có tiến triển

Consumer B có thể bị xem là **non-responsive** theo chính sách giám sát. Tình trạng này cần điều tra vì nó có thể dẫn tới consumer lag, mất assignment hoặc lỗi commit offset.

Điểm khác biệt:

| Tín hiệu | Idle | Non-responsive |
|---|---|---|
| Có record mới từ broker? | Có thể không | Có thể có hoặc không |
| Vòng poll còn tiến triển? | Thường có | Không tiến triển đủ thường xuyên |
| Ý nghĩa chính | Không có dữ liệu để xử lý | Có dấu hiệu consumer bị chậm/kẹt |
| Spring Kafka event liên quan | ListenerContainerIdleEvent | NonResponsiveConsumerEvent |
| Cấu hình trọng tâm | idleEventInterval | monitorInterval, noPollThreshold, pollTimeout |
| Hướng xử lý | Thường theo dõi thông tin | Điều tra thread, broker, dependency và poll interval |

Không nên dùng NonResponsiveConsumerEvent để báo topic vắng dữ liệu; cũng không nên coi idle event là bằng chứng consumer đang treo.

## 2. monitorInterval thực sự điều khiển điều gì?

Spring Kafka tạo một tác vụ giám sát định kỳ cho listener container. **monitorInterval** quy định khoảng thời gian giữa các lượt kiểm tra trạng thái phản hồi của consumer.

Nói đơn giản:

    Consumer thread:
      poll() -> listener -> poll() -> listener -> ...

    Monitor task:
      check ----- check ----- check ----- check
         khoảng cách = monitorInterval

Nếu thời gian kể từ nhịp poll gần nhất vượt ngưỡng do cấu hình noPollThreshold và pollTimeout quyết định, container có thể publish NonResponsiveConsumerEvent.

Có ba đại lượng cần phân biệt:

- **pollTimeout:** thời gian chờ tối đa mà một lệnh KafkaConsumer.poll() được yêu cầu chờ, tính bằng milliseconds trong ContainerProperties.
- **noPollThreshold:** hệ số nhân dùng để xác định khoảng thời gian không thấy nhịp poll được chấp nhận.
- **monitorInterval:** chu kỳ monitor kiểm tra, thường được cấu hình theo **giây**, không phải milliseconds.

Công thức ngưỡng thường được Spring Kafka mô tả:

    NonResponsiveThreshold = pollTimeout * noPollThreshold

Và điều kiện phát hiện có thể hiểu gần đúng:

    timeSinceLastPoll > NonResponsiveThreshold
      -> monitor task xem consumer là non-responsive
      -> publish NonResponsiveConsumerEvent

Đừng nhầm monitorInterval với số giây “chờ tối đa trước khi phát event”. Nó chỉ là **nhịp lấy mẫu**; ngưỡng đánh giá được tính bằng hai thuộc tính còn lại.

## 3. Giá trị mặc định và đơn vị

Ở nhiều phiên bản Spring Kafka, các giá trị mặc định thường gặp là:

| Thuộc tính | Giá trị thường gặp | Đơn vị | Vai trò |
|---|---:|---|---|
| pollTimeout | 5.000 | ms | Khoảng chờ poll |
| noPollThreshold | 3,0 | hệ số | Nhân với pollTimeout để tạo ngưỡng |
| monitorInterval | 30 | giây | Chu kỳ tác vụ kiểm tra |
| idleEventInterval | Không phát idle event nếu chưa bật | ms | Ngưỡng vắng record |

Với các giá trị này:

    pollTimeout = 5.000 ms = 5 giây
    noPollThreshold = 3,0

    Threshold = 5 * 3 = 15 giây

    monitorInterval = 30 giây

Consumer vượt 15 giây chưa chắc nhận event ngay đúng giây thứ 15, vì monitor chỉ kiểm tra theo chu kỳ 30 giây và còn phụ thuộc scheduling trong JVM.

**Lưu ý phiên bản:** Spring Kafka đã thay đổi một số API, mặc định và cách xử lý listener container theo thời gian. Khi tích hợp, hãy kiểm tra Javadoc của ContainerProperties cho dependency thực tế. Ví dụ trong bài dùng các API phổ biến của Spring Kafka 3.x; không giả định mọi thuộc tính đều tồn tại hoặc cùng mặc định trong bản cũ.

## 4. Ước lượng thời điểm phát hiện sự cố

Giả sử:

    pollTimeout = 5 giây
    noPollThreshold = 3,0
    NonResponsiveThreshold = 15 giây
    monitorInterval = 10 giây

Monitor lấy mẫu tại các mốc 10, 20, 30 giây sau khi bắt đầu một chuỗi đo minh họa.

Nếu consumer ngừng tiến triển ngay từ giây 0:

    T=0s:   Consumer ngừng poll
    T=10s:  Monitor check; 10s chưa vượt ngưỡng 15s
    T=20s:  Monitor check; 20s > 15s, phát hiện
    T=30s:  Monitor có thể tiếp tục thấy trạng thái xấu

Thời gian phát hiện ở ví dụ khoảng 20 giây, không phải 10 giây và cũng không phải đúng 15 giây.

Về nguyên tắc, trong điều kiện scheduler vận hành bình thường, độ trễ bổ sung do lấy mẫu có thể xấp xỉ tới một monitorInterval sau khi vượt ngưỡng. Tuy nhiên GC pause, thiếu CPU, thread scheduling và quá trình lifecycle của container có thể làm thời điểm thực tế trễ hơn. Đừng coi đây là một thời hạn cứng bảo đảm sẽ phát event trong mọi hoàn cảnh.

Nếu mục tiêu là phát hiện trong vài giây, cần cân bằng monitorInterval, pollTimeout, noPollThreshold và nguy cơ cảnh báo giả. Giảm monitorInterval mà không điều chỉnh các tham số khác không làm ngưỡng non-responsive tự giảm.

## 5. monitorInterval không phải max.poll.interval.ms

Hai tên gần giống nhau nhưng thuộc hai tầng cơ chế:

| Cấu hình | Hệ thống | Điều khiển |
|---|---|---|
| monitorInterval | Spring Kafka container | Chu kỳ kiểm tra non-responsive |
| pollTimeout | Kafka consumer thông qua container | Thời gian poll chờ record |
| noPollThreshold | Spring Kafka container | Ngưỡng dựa trên pollTimeout |
| max.poll.interval.ms | Kafka Consumer group protocol | Khoảng thời gian cho phép giữa các lượt poll theo điều kiện group membership |

Nếu consumer xử lý một poll quá lâu và vượt max.poll.interval.ms, Kafka client có thể bị coi là không còn poll đủ thường xuyên, dẫn tới rebalance hoặc mất assignment. Đây là **hệ quả ở mức group membership**.

NonResponsiveConsumerEvent là **cảnh báo ứng dụng** do container phát hiện nhịp poll bất thường. Nó không thay đổi giới hạn max.poll.interval.ms của broker/client và không tự giữ partition khỏi bị rebalance.

Ví dụ:

    monitorInterval = 10 giây
    threshold = 30 giây
    max.poll.interval.ms = 300.000 ms (5 phút)

Container có thể phát cảnh báo non-responsive khi chưa tới ngưỡng 5 phút. Điều này giúp phát hiện sớm trước khi consumer thực sự mất assignment, nhưng không bảo đảm nguyên nhân luôn là deadlock.

Ngược lại, nếu monitorInterval/threshold đặt quá lớn, Kafka client có thể đã xảy ra rebalance trước khi monitor cung cấp tín hiệu hữu ích.

## 6. monitorInterval không thay thế idleEventInterval

idleEventInterval dùng để phát ListenerContainerIdleEvent khi container không nhận record trong khoảng thời gian cấu hình, trong khi vòng poll vẫn có thể hoàn toàn bình thường.

Ví dụ:

~~~java
ContainerProperties props = factory.getContainerProperties();

// Đơn vị milliseconds: 60 giây không nhận record.
props.setIdleEventInterval(60_000L);

// Đơn vị seconds: monitor kiểm tra mỗi 10 giây.
props.setMonitorInterval(10);
~~~

Hai thuộc tính giải quyết hai câu hỏi khác nhau:

- idleEventInterval: “Đã bao lâu consumer không nhận record?”
- monitorInterval: “Bao lâu kiểm tra một lần xem vòng poll có đang phản hồi?”

Có thể phát ListenerContainerIdleEvent sau một phút không có dữ liệu và **không** phát NonResponsiveConsumerEvent, bởi consumer vẫn đang poll thành công.

Nếu consumer non-responsive, không thể suy ra chắc chắn idle event cũng sẽ phát tại thời điểm đó; việc phát event phụ thuộc poll loop và cơ chế container.

## 7. Cấu hình bộ ba tham số trong Spring Kafka

Với một ConcurrentKafkaListenerContainerFactory, có thể cấu hình như sau:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.ContainerProperties;

@Configuration
public class OrdersConsumerConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
    ordersListenerFactory(
            ConsumerFactory<String, OrderCreated> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<
                        String, OrderCreated>();

        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);

        ContainerProperties props = factory.getContainerProperties();

        // pollTimeout: milliseconds.
        props.setPollTimeout(5_000L);

        // Ngưỡng non-responsive: 3 * 5s = 15s.
        props.setNoPollThreshold(3.0f);

        // Monitor thức dậy mỗi 10s (đơn vị seconds).
        props.setMonitorInterval(10);

        // Event idle độc lập với event non-responsive.
        props.setIdleEventInterval(60_000L);

        return factory;
    }
}
~~~

Listener sử dụng factory này:

~~~java
@KafkaListener(
    id = "ordersListener",
    topics = "orders.created",
    groupId = "order-processor",
    containerFactory = "ordersListenerFactory"
)
public void consume(OrderCreated event) {
    orderService.process(event);
}
~~~

OrderCreated và orderService là thành phần ứng dụng minh họa. Ví dụ cần Spring Kafka dependency, Bean configuration và imports phù hợp với dự án.

Cấu hình trên chỉ thay đổi container được tạo bởi ordersListenerFactory. Nếu hệ thống có nhiều listener factories, những listener dùng factory khác không tự nhận các giá trị này.

**Không nhầm setMonitorInterval(10) thành 10 milliseconds.** Tùy chọn này thường nhận số giây; ngược lại setPollTimeout(5_000L) nhận milliseconds.

## 8. Cấu hình với Spring Boot và cấu hình Java

Spring Boot có nhiều thuộc tính cho Kafka consumer và listener, nhưng không nên giả định mọi setter của ContainerProperties đều có một đường dẫn spring.kafka.listener.* tương ứng trong mọi phiên bản Boot.

Một cấu hình YAML nền tảng:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: order-processor
      enable-auto-commit: false
      properties:
        max.poll.records: 100
        max.poll.interval.ms: 300000
    listener:
      concurrency: 3
      ack-mode: record
~~~

Những thuộc tính monitorInterval/noPollThreshold thường nên được cấu hình trực tiếp qua Java ContainerProperties, hoặc qua một customizer/factory được ứng dụng quản lý nếu phiên bản hỗ trợ.

Có thể tạo bean dùng factory mặc định của Spring Boot nếu đã xác nhận customizer đúng contract. Điều quan trọng nhất là **listener container thực sự sử dụng factory có cấu hình**; chỉ khai báo một bean mà listener không dùng sẽ không ảnh hưởng monitor.

Ở môi trường nhiều instance, mọi pod có thể dùng cùng policy để dễ so sánh metric, nhưng yêu cầu SLO và poll processing time có thể khác giữa consumer groups. Không nhất thiết đặt một threshold toàn ứng dụng cho tất cả workload.

## 9. NonResponsiveConsumerEvent là gì?

Spring Kafka có application event **NonResponsiveConsumerEvent** dành cho những tình huống consumer bị giám sát phát hiện không phản hồi theo ngưỡng.

Một observer có thể xử lý sự kiện bằng Spring @EventListener:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.NonResponsiveConsumerEvent;
import org.springframework.stereotype.Component;

@Component
public class KafkaPollMonitorListener {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaPollMonitorListener.class);

    @EventListener
    public void onNonResponsive(NonResponsiveConsumerEvent event) {

        log.warn(
            "Non-responsive Kafka consumer: listenerId={}, " +
            "timeSinceLastPollMs={}, source={}",
            event.getListenerId(),
            event.getTimeSinceLastPoll(),
            event.getSource()
        );
    }
}
~~~

Các thông tin quan trọng:

- getTimeSinceLastPoll() cung cấp khoảng thời gian đo được từ nhịp poll gần nhất theo event, thường thể hiện bằng milliseconds.
- getListenerId() hỗ trợ phân biệt listener có liên quan.
- getSource() là nguồn application event; không được tùy tiện xem đó là đối tượng KafkaConsumer có thể sử dụng từ thread khác.

Đây là observer để ghi nhận sự kiện, không phải đoạn code tự khởi động lại consumer. Sự kiện giúp đặt cảnh báo đúng ngữ cảnh nhưng chưa chứng minh consumer thực sự bị deadlock.

## 10. Application event handler nên làm gì?

Trong callback, ưu tiên các thao tác ngắn:

1. Ghi structured log với listenerId, instanceId, thời gian từ lần poll gần nhất.
2. Tăng metric counter.
3. Đọc thông tin trạng thái container theo API an toàn.
4. Gửi tín hiệu nhẹ tới một supervisor hoặc monitoring queue.
5. Kết hợp các thông tin khác để quyết định có cần thao tác khôi phục hay không.

Ví dụ:

~~~java
@Component
public class NonResponsiveConsumerMetrics {

    private final MeterRegistry metrics;

    public NonResponsiveConsumerMetrics(MeterRegistry metrics) {
        this.metrics = metrics;
    }

    @EventListener
    public void record(NonResponsiveConsumerEvent event) {

        metrics.counter(
            "kafka.consumer.nonresponsive",
            "listener", event.getListenerId()
        ).increment();
    }
}
~~~

Khi dùng label listenerId, đảm bảo giá trị có cardinality được kiểm soát; nếu listener ID có suffix thay đổi theo child consumer hoặc pod, cần dự kiến số lượng series. Không dùng eventId, partition offset hay full exception làm metric label.

Application event handler nên tránh gọi API mạng blocking dài, giữ khóa lâu hoặc chạy một tiến trình sửa lỗi phức tạp. Tác vụ giám sát phải nhanh và không làm bản thân monitoring trở thành nguồn bế tắc mới.

## 11. Event handler chạy trên thread nào?

Non-responsive monitoring được thực hiện từ một tác vụ giám sát của container, không nên giả định callback luôn nằm trên consumer poll thread. Cấu hình ApplicationEventMulticaster của Spring có thể dispatch listener đồng bộ hoặc bất đồng bộ tùy ứng dụng.

Hệ quả:

- Không dùng đối tượng KafkaConsumer từ event listener trên một thread không sở hữu consumer.
- Không gọi poll(), seek(), commitSync() hoặc pause() trực tiếp trên raw consumer từ một monitoring callback bất đồng bộ.
- KafkaConsumer nói chung không thread-safe; phải tuân theo contract của Kafka client.
- Không dùng ThreadLocal state của consumer để suy luận trong monitor thread.
- Nếu cần stop/restart, thao tác qua Spring Kafka container API và lifecycle supervisor phù hợp.

KafkaConsumer.wakeup() là một ngoại lệ có contract thread-safe trong Kafka client, nhưng không nên dùng nó như cách khôi phục mù mọi NonResponsiveConsumerEvent. Spring Kafka container quản lý poll và lifecycle; tự can thiệp raw consumer có thể làm phát sinh các lỗi bổ sung.

## 12. Cách kiểm tra trạng thái container theo listener ID

Spring Kafka cung cấp KafkaListenerEndpointRegistry để truy xuất container của @KafkaListener.

~~~java
@Service
public class ListenerContainerHealth {

    private final KafkaListenerEndpointRegistry registry;

    public ListenerContainerHealth(
            KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public boolean isRunning(String listenerId) {
        MessageListenerContainer container =
                registry.getListenerContainer(listenerId);

        return container != null && container.isRunning();
    }
}
~~~

Một container có isRunning() = true vẫn có thể đang bị kẹt hoặc không nhận dữ liệu. Vì vậy cần kết hợp:

- Last poll time hoặc sự kiện NonResponsiveConsumerEvent.
- Committed offset progression.
- Consumer lag và oldest record age.
- Số partition đang được assign.
- Processing duration và dependency latency.
- Container pause state.
- Kafka consumer group membership.

Không đánh giá container healthy chỉ bởi isRunning() và cũng không kết luận dead chỉ bởi một lần NonResponsiveConsumerEvent.

## 13. Không tự động stop/restart ngay trong @EventListener

Một cách xử lý dễ nghĩ tới:

~~~java
@EventListener
public void onNonResponsive(NonResponsiveConsumerEvent event) {
    // Phản ví dụ: tránh gọi stop đồng bộ ở đây.
    registry.getListenerContainer("ordersListener").stop();
}
~~~

Đây **không phải** cơ chế khôi phục production được khuyến nghị. Một số rủi ro:

- Nếu dừng đồng bộ, caller có thể chờ consumer thread đang bị kẹt.
- Monitor event có thể lặp theo chu kỳ, tạo nhiều yêu cầu stop/restart.
- Tín hiệu có thể là do listener xử lý chậm nhưng vẫn hợp lệ.
- Một lỗi dependency vẫn còn tồn tại sẽ gây restart loop.
- Restart consumer group gây rebalance, có thể tăng lag và duplicate.
- Parent ConcurrentMessageListenerContainer có nhiều child consumers; dừng cả parent có thể ảnh hưởng những partition đang hoạt động tốt.

Thay vào đó, event handler nên chuyển một tín hiệu nhẹ tới supervisor riêng. Supervisor kiểm tra trạng thái thực tế, có timeout/cooldown, chỉ xử lý container phù hợp và phối hợp với orchestrator khi cần.

Nếu cần stop container từ đường xử lý event, không block ngay trên thread monitor; triển khai thông qua executor/scheduler được quản lý với giới hạn queue và chính sách lifecycle. Kiểm tra behavior API stop() của Spring Kafka version đang dùng.

## 14. Một supervisor có cooldown và chính sách rõ ràng

Mô hình phù hợp:

    NonResponsiveConsumerEvent
             |
             v
    Lightweight observer
             |
             v
    Bounded signal queue
             |
             v
    Recovery supervisor
             |
             +--> kiểm tra listener container state
             |
             +--> kiểm tra số lần liên tiếp + thời gian gần nhất
             |
             +--> xem lag / processing / dependency
             |
             +--> quyết định alert hoặc restart
             |
             v
    Recovery action có backoff

Ví dụ policy:

| Điều kiện | Hành động |
|---|---|
| Một event đơn lẻ, listener vẫn xử lý | Log/metric, không restart vội |
| Hai hoặc nhiều chu kỳ monitor đều non-responsive | Kiểm tra thread dump và dependency |
| Dependency đang outage nhưng consumer còn poll | Rate limit/pause theo thiết kế, không restart mù |
| Consumer thread kẹt thực sự, không tiến triển | Escalate; controlled restart nếu hợp đồng cho phép |
| Có transaction đang xử lý | Đánh giá abort/fencing và độ an toàn side effect |
| Repeated restart trong cửa sổ ngắn | Ngừng tự động restart, nâng cảnh báo |
| Pod/JVM không phản hồi | External liveness/monitoring xử lý |

Một supervisor nên tránh có cả hai cơ chế cùng cố restart: ví dụ local scheduler và Kubernetes liveness probe. Nếu cả hai tác động đồng thời, hệ thống có thể liên tục tái cân bằng consumer group.

## 15. Vì sao NonResponsiveConsumerEvent có thể là cảnh báo giả?

Không phải mọi khoảng cách dài giữa các lần poll đều là deadlock.

Các nguyên nhân có thể gây tăng thời gian:

- Listener chạy nghiệp vụ lâu nhưng vẫn hoàn tất.
- Lệnh gọi database/HTTP bị chậm.
- max.poll.records quá lớn nên một poll chứa nhiều record.
- Thread pool nghẽn hoặc bị chờ lock.
- JVM GC pause dài.
- CPU throttling trong container.
- Host bị thiếu tài nguyên.
- Đang shutdown/rebalance hoặc chờ lifecycle operation.
- Poll timeout và noPollThreshold cấu hình quá thấp so với workload.
- Có chính sách delay giữa poll hoặc backpressure được cấu hình.

Tùy cách container tính thời gian poll gần nhất, một listener xử lý lâu hoặc một thread đang block ở bước khác cũng có thể tạo tín hiệu “chưa poll lại đủ sớm”. Event không khẳng định chính xác vị trí stack đang bị treo.

Khi nhận event, hãy kiểm tra thread dump để phân biệt:

    Thread đang chờ KafkaConsumer.poll()
        -> điều tra client/network/coordinator

    Thread đang chờ database socket read
        -> điều tra DB timeout/connection pool

    Thread đang chờ lock trong code
        -> điều tra deadlock/contention

    Thread đang xử lý hàng trăm record đồng bộ
        -> xem max.poll.records và processing time

Đừng chỉ tăng noPollThreshold mãi để loại bỏ event. Nếu nguyên nhân là service dependency không có timeout, việc tăng ngưỡng chỉ làm mất khả năng phát hiện sự cố.

## 16. monitorInterval và pollTimeout: chọn cho đúng ngữ cảnh

Ví dụ ba cấu hình minh họa:

| Workload | pollTimeout | noPollThreshold | Ngưỡng | monitorInterval |
|---|---:|---:|---:|---:|
| Listener nhẹ, mong poll thường xuyên | 2.000 ms | 3,0 | 6 giây | 5 giây |
| Workload trung bình | 5.000 ms | 3,0 | 15 giây | 10 giây |
| Workload có poll chờ dài | 10.000 ms | 3,0 | 30 giây | 10–15 giây |

Các giá trị là **ví dụ để suy luận**, không phải mẫu bắt buộc. Chọn theo phân bố thời gian xử lý thực tế, Kafka client behavior, CPU scheduling và mức độ nghiêm trọng khi consumer ngừng tiến triển.

Một số nguyên tắc:

1. pollTimeout phản ánh mục đích fetch/poll, không nên bị đổi tùy tiện chỉ để tác động monitor.
2. noPollThreshold đặt tỷ lệ dung sai so với pollTimeout.
3. monitorInterval nên đủ nhỏ để phát hiện trong thời gian vận hành mong muốn, nhưng không cần kiểm tra quá dày.
4. SLO phát hiện lỗi cần tính thêm độ trễ scheduler và xử lý cảnh báo.
5. Với workload nhiều record trên mỗi poll, cần xem max.poll.records và thời gian xử lý cả poll.

Nếu pollTimeout được tăng gấp đôi và noPollThreshold không đổi, ngưỡng non-responsive cũng tăng gấp đôi. MonitorInterval không tự đổi theo.

## 17. Giá trị quá nhỏ có tác động gì?

Giả sử:

    pollTimeout = 5.000 ms
    noPollThreshold = 1,1
    monitorInterval = 1 giây

Ngưỡng chỉ 5,5 giây. Một poll bình thường gần sát timeout, kết hợp một ít overhead Java scheduling, GC hoặc listener preparation, có thể dễ chạm ngưỡng, làm tăng cảnh báo không hữu ích.

Hệ quả:

- Counter non-responsive tăng dù hệ thống còn xử lý được.
- Alert fatigue làm đội vận hành bỏ qua sự cố thật.
- Supervisor restart quá nhạy có thể gây rebalance storm.
- Consumer re-delivery làm side effect phải xử lý lại.
- Chi phí logging/metric và điều tra tăng.

Ngưỡng nên có **headroom** hợp lý so với pollTimeout, thời gian xử lý và dao động scheduler. Cần dữ liệu đo thực tế trước khi giảm quá mạnh.

## 18. Giá trị quá lớn có tác động gì?

Ngược lại:

    pollTimeout = 5.000 ms
    noPollThreshold = 30
    monitorInterval = 120 giây

Ngưỡng = 150 giây. Monitor chỉ kiểm tra hai phút một lần; việc phát hiện có thể rất muộn so với SLO.

Hệ quả:

- Consumer lag tăng đáng kể trước khi có cảnh báo.
- Lỗi offset hoặc group membership có thể đã xảy ra.
- Dependency outage kéo dài mà không có tín hiệu chuyên biệt.
- Nhóm vận hành khó phân biệt chậm tạm thời với treo lâu.
- Container running state có thể vẫn hiển thị true trong khi không xử lý.

Nếu muốn giữ thời gian polling dài vì workload đặc thù, phải bổ sung các metric khác như processing duration, per-partition lag và oldest record age. Không dùng một ngưỡng monitor quá lớn rồi coi hệ thống đã được giám sát đầy đủ.

## 19. Ảnh hưởng của max.poll.records

max.poll.records quy định số record tối đa KafkaConsumer.poll() trả về trong một lần. Với record listener, container có thể xử lý một chuỗi nhiều record trước khi quay lại poll.

Giả sử:

    max.poll.records = 500
    Mỗi record xử lý ~100 ms
    Một poll có thể chứa 500 record

    Thời gian nghiệp vụ ~50 giây

Nếu hệ thống chỉ kiểm tra nhịp poll ở ngưỡng 15 giây, một chuỗi xử lý hợp lệ nhưng dài có thể tạo cảnh báo non-responsive.

Hướng xử lý:

- Giảm max.poll.records xuống mức phù hợp processing throughput.
- Giảm thời gian xử lý từng record.
- Đặt timeout cho dependency.
- Cân nhắc concurrency thêm nếu số partition và dependency capacity cho phép.
- Tách long-running jobs khỏi consumer path bằng hợp đồng bền vững.
- Điều chỉnh ngưỡng monitor sau khi đã đo thời gian xử lý thực tế.

Chỉ tăng max.poll.interval.ms không nhất thiết giải quyết tín hiệu NonResponsiveConsumerEvent, vì đó là hai cơ chế độc lập.

## 20. Poll lâu và consumer group rebalance

Khi một consumer không poll đủ thường xuyên, nó có thể bị loại hoặc thay đổi trạng thái group membership theo cơ chế Kafka. Group coordinator có thể chuyển các partition sang consumer khác.

Sơ đồ:

    Consumer A sở hữu partition P0
            |
            v
    A xử lý quá lâu, chưa poll tiếp
            |
            +--> Spring monitor có thể phát warning
            |
            v
    max.poll.interval.ms bị vượt
            |
            v
    Group membership thay đổi
            |
            v
    Partition P0 có thể chuyển sang Consumer B
            |
            v
    B đọc từ committed offset an toàn

Nếu A đã thực hiện side effect database nhưng chưa commit source offset, B có thể xử lý lại cùng event. Vì vậy bảo vệ độ tin cậy cần:

- Idempotency key/eventId ổn định.
- Giới hạn thời gian dependency.
- Không commit offset trước khi xử lý bền vững.
- Quản lý assignment/revocation/lost ownership.
- Fencing task cũ khi có async work.
- Theo dõi consumer group generation và rebalance.

monitorInterval **không ngăn** rebalance; nó giúp phát hiện một tín hiệu đi trước hoặc đi cùng sự cố để vận hành can thiệp.

## 21. Pause/resume có tạo NonResponsiveConsumerEvent không?

Khi sử dụng Spring Kafka container.pause(), container thường duy trì nhịp poll phù hợp để giữ group membership trong khi các partition được pause. Vì vậy, **pause theo cơ chế container** không đồng nghĩa vòng poll đã bị treo.

Ví dụ:

~~~java
MessageListenerContainer container =
        registry.getListenerContainer("ordersListener");

if (container != null) {
    container.pause();
}
~~~

Nếu container vẫn thực hiện poll cần thiết, nó có thể không phát NonResponsiveConsumerEvent chỉ vì đang paused. Tuy vậy, các record in-flight, chế độ pauseImmediate và behavior của phiên bản container có thể ảnh hưởng nhịp xử lý.

Cần phân biệt:

| Sự kiện | Dấu hiệu chính |
|---|---|
| Container được yêu cầu pause | Có pause request |
| Container đã pause consumer | ConsumerPausedEvent hoặc trạng thái tương ứng |
| Container idle | Không nhận record trong khoảng cấu hình |
| Consumer non-responsive | Không đạt nhịp poll theo monitor threshold |
| Container stopped | Lifecycle đã dừng, không còn poll |

Không dùng monitorInterval như cách triển khai backpressure. Muốn giảm tốc tiêu thụ, sử dụng rate limiter, concurrency limit hoặc pause/resume đúng API.

## 22. idleBetweenPolls và mối quan hệ với monitor

ContainerProperties.idleBetweenPolls có thể thêm thời gian nghỉ giữa các lượt poll để hạ nhịp xử lý.

Ví dụ:

~~~java
ContainerProperties props = factory.getContainerProperties();

props.setIdleBetweenPolls(1_000L);
props.setPollTimeout(5_000L);
props.setNoPollThreshold(3.0f);
props.setMonitorInterval(10);
~~~

Khi ứng dụng chủ động tạo khoảng nghỉ giữa poll, thời gian quan sát giữa các nhịp có thể tăng. Một chính sách monitor quá nhạy có thể coi lịch poll được làm chậm có chủ đích là không phản hồi.

Không dùng idleBetweenPolls thay cho quota request/giây chính xác; một poll có thể mang nhiều record. Nếu đã dùng rate limiter blocking trong listener, hãy cộng thời gian chờ permit vào ngân sách xử lý trước khi đặt monitor threshold.

Đo thời gian thực tế từ poll đến poll trên workload hiện tại, thay vì chỉ cộng tham số theo lý thuyết rồi khẳng định chắc chắn event sẽ hoặc không xuất hiện.

## 23. NonResponsiveConsumerEvent và ConsumerStoppedEvent

Hai event thường được quan sát cùng hệ thống nhưng không đồng nghĩa.

**NonResponsiveConsumerEvent**: monitor nhận thấy consumer lâu không tiến triển poll theo ngưỡng. Consumer vẫn có thể đang running ở mức lifecycle và chưa bị dừng.

**ConsumerStoppedEvent**: consumer thực sự kết thúc lifecycle; event có thể chứa Reason như NORMAL, ERROR, AUTH, FENCED hoặc NO_OFFSET tùy phiên bản.

Sơ đồ:

    Consumer không poll kịp
        |
        v
    NonResponsiveConsumerEvent
        |
        +--> Có thể tự hồi phục
        |
        +--> Có thể tiếp tục kẹt
                |
                v
        Container có thể bị stop/restart
                |
                v
        ConsumerStoppedEvent

Không phải mọi NonResponsiveConsumerEvent đều dẫn tới ConsumerStoppedEvent, và không phải mọi ConsumerStoppedEvent đều có NonResponsiveConsumerEvent trước đó. Ví dụ shutdown bình thường có thể tạo ConsumerStoppedEvent(NORMAL) mà không có cảnh báo poll.

Trong alerting, non-responsive có thể là mức warning cần xác minh; stopped bất thường thường có hậu quả về capacity và tiến độ tiêu thụ cần điều tra riêng.

## 24. NonResponsiveConsumerEvent và ListenerContainerIdleEvent

Giả sử topic orders.created không có dữ liệu suốt một giờ:

    Consumer vẫn poll:
       00:00 poll empty
       00:05 poll empty
       00:10 poll empty
       ...
       60:00 poll empty

Nếu idleEventInterval được cấu hình, Spring Kafka có thể phát ListenerContainerIdleEvent theo chu kỳ phù hợp. Nhưng đây là **trạng thái vắng dữ liệu**, không phải deadlock.

Trường hợp khác:

    Topic có dữ liệu mới
       |
       v
    Consumer bị chặn lâu trong client hoặc listener
       |
       v
    Không poll lại đủ sớm
       |
       v
    NonResponsiveConsumerEvent

Dù hai event cùng tồn tại, cách khắc phục khác nhau:

- Idle kéo dài: kiểm tra producer traffic, topic selection, filter, pause, assignment.
- Non-responsive: kiểm tra thread dump, poll interval, dependency và lifecycle.

Nếu dùng cả hai event trong dashboard, nên biểu diễn chúng như các metric riêng, không cộng chung thành “Kafka listener errors”.

## 25. Giám sát theo từng child consumer khi concurrency lớn

Với concurrency=4, một parent ConcurrentMessageListenerContainer có thể quản lý bốn child Kafka consumers:

    Parent ordersListener
       |
       +-- Consumer 0 -> P0, P1
       +-- Consumer 1 -> P2, P3
       +-- Consumer 2 -> P4, P5
       +-- Consumer 3 -> P6, P7

Nếu chỉ Consumer 2 gặp deadlock, các consumer khác vẫn có thể poll và xử lý bình thường.

Điểm cần chú ý:

- NonResponsiveConsumerEvent có thể gắn với child container/consumer cụ thể.
- Không kết luận toàn consumer group đã treo từ một event.
- Một parent listener ID có thể có nhiều child IDs theo convention của Spring Kafka.
- Theo dõi lag theo partition để biết workload bị ảnh hưởng.
- Nếu lựa chọn restart parent container, nó sẽ ảnh hưởng toàn bộ child consumers.
- Quyết định dừng một child phải dùng API/lifecycle được framework hỗ trợ, không thao tác raw KafkaConsumer từ monitor thread.

Trong metric, nên dùng tập nhãn ổn định như application, group, listener hoặc child index được quản lý; không dùng offset hay eventId làm label.

## 26. Thiết kế monitoring với log có cấu trúc

Một log hữu ích khi phát sinh NonResponsiveConsumerEvent:

    event_type=NonResponsiveConsumerEvent
    application=order-service
    instance=order-service-pod-2
    listener_id=ordersListener-2
    time_since_last_poll_ms=22000
    monitor_interval_sec=10
    poll_timeout_ms=5000
    no_poll_threshold=3.0
    consumer_lag=12000
    action=investigate

Không phải mọi trường đều có trực tiếp trên event. Các giá trị cấu hình và lag cần lấy từ chính sách ứng dụng hoặc nguồn metric khác; đừng ngụy tạo chúng chỉ vì log cần phong phú.

Đừng log raw KafkaConsumer, credential hoặc toàn bộ record payload. Nếu thread dump được thu thập tự động, nó có thể chứa dữ liệu nhạy cảm từ stack/local context; cần retention và phân quyền phù hợp.

Bổ sung correlation giữa event timestamp, container/client ID, consumer group và pod instance để tìm đúng log trước thời điểm sự cố.

## 27. Metrics cần kết hợp

Những metric được khuyến nghị:

| Metric | Mục tiêu |
|---|---|
| kafka_consumer_nonresponsive_total | Số lần monitor phát hiện non-responsive |
| kafka_consumer_time_since_last_poll_ms | Khoảng cách poll khi có event hoặc đo định kỳ |
| kafka_consumer_poll_duration | Thời gian Kafka consumer poll |
| kafka_listener_processing_duration | Thời gian listener xử lý record/batch |
| kafka_consumer_records_consumed_rate | Tốc độ tiêu thụ record |
| kafka_consumer_lag | Số record chưa commit/tiêu thụ theo cách đo tương ứng |
| kafka_consumer_oldest_record_age | Độ tuổi backlog |
| kafka_consumer_rebalance_total | Số lần consumer group rebalance |
| kafka_consumer_commit_failures_total | Lỗi commit offset |
| kafka_consumer_paused | Consumer/partition đang pause hay không |
| jvm_gc_pause | Thời gian stop-the-world GC |
| process_cpu_throttling | Tình trạng CPU bị throttle trong container |
| downstream_latency / timeout | Khả năng chậm do dependency |

Tên metric trong bảng là tên **gợi ý về ý nghĩa**, không phải cam kết tất cả metric đã được Spring Kafka hoặc Micrometer xuất trực tiếp với đúng tên đó. Tên thực tế phụ thuộc Kafka client metrics, Micrometer binder, Prometheus naming và hệ thống quan sát đang dùng.

Cần nhìn trend theo thời gian. Một NonResponsiveConsumerEvent ngắn không gây lag có thể chưa nghiêm trọng; nhiều event liên tiếp cùng lag tăng và processing duration tăng là tín hiệu đáng chú ý hơn.

## 28. SLO và ngưỡng cảnh báo nên chọn thế nào?

Một SLO có thể yêu cầu:

- 99,9% record được xử lý trong 60 giây.
- Consumer không bị kẹt quá 30 giây mà không có cảnh báo.
- Không có partition mất owner quá thời gian cho phép.
- Tỷ lệ retry/error không vượt ngân sách.

Để đáp ứng mục tiêu phát hiện kẹt trong khoảng 30 giây, có thể chọn:

    pollTimeout = 5 giây
    noPollThreshold = 3.0
    threshold = 15 giây
    monitorInterval = 5 hoặc 10 giây

Theo mô hình lấy mẫu thông thường, event có thể xuất hiện sau khi vượt ngưỡng tại một trong những lượt kiểm tra tiếp theo. Nhưng đây không phải cam kết thời gian thực nếu JVM tạm dừng hoặc scheduler không chạy.

Một cảnh báo production nên có ít nhất hai điều kiện:

1. Consumer non-responsive theo monitor.
2. Có bằng chứng tiến độ xử lý suy giảm như lag/oldest age hoặc nhiều lượt monitor liên tiếp bất thường.

Nếu một hệ thống bắt buộc phát hiện hard hang ngay cả khi JVM không phát event, cần **monitor bên ngoài process**; local monitor cũng sẽ ngừng chạy khi JVM chết hoặc node không được cấp CPU.

## 29. Phân biệt việc poll bị kẹt với listener bị kẹt

Cách điều tra:

**Bước 1: xem thread dump.**

Tìm các thread có tên liên quan Kafka listener container hoặc consumer. Xem stack đứng ở:

- KafkaConsumer.poll hoặc network client.
- JDBC driver/connection pool.
- HTTP client socket read.
- Object monitor/LockSupport/CompletableFuture.get.
- Deserialization hoặc business logic.
- Kafka transaction commit/abort.
- ApplicationEvent listener có blocking operation.

**Bước 2: đối chiếu thời gian.**

Nếu listener processing duration p99 tăng trước NonResponsiveConsumerEvent, khả năng dependency/business code là nguồn gây chậm. Nếu listener gần như không chạy mà poll không tiến triển, xem broker/network/client.

**Bước 3: kiểm tra tình trạng nhóm.**

Consumer đã mất assignment chưa? Có rebalance không? Committed offset có tiến không? Pod có GC/CPU throttle không?

**Bước 4: quyết định hành động phù hợp.**

Không restart Kafka chỉ vì thread dump cho thấy một socket read đang chờ trong giới hạn timeout hợp lệ. Ngược lại, nếu task block vô hạn và SLO đang bị ảnh hưởng, cần kiểm soát timeout và thay đổi code.

## 30. Non-responsive không đồng nghĩa timeout Kafka network

Một exception liên quan Kafka request timeout có thể khiến poll hoặc giao tiếp với broker thất bại, nhưng NonResponsiveConsumerEvent có thể xuất hiện **không có Kafka exception nào**.

Ví dụ:

    Listener gọi HTTP client với timeout vô hạn
    HTTP server không phản hồi
    Consumer thread chờ lâu
    Không trở lại poll đúng nhịp
    Monitor báo non-responsive

Broker Kafka vẫn có thể khỏe, không có network issue giữa consumer và broker.

Ngược lại, broker outage có thể làm poll liên tục trả lỗi/retry nhưng container vẫn còn tiến triển theo cách khiến monitor không phát hiện giống một thread bị kẹt.

Vì thế, không dùng event để khẳng định “broker down”. Kết hợp client metrics, broker health, network và stack trace.

## 31. Đặt request timeout và concurrency limit

Để giảm non-responsive do business processing, cần hạn chế việc một record giữ consumer thread quá lâu:

- HTTP client có connect timeout, read/response timeout và overall deadline.
- JDBC pool có connection acquisition timeout, query timeout.
- Thread pool bounded với queue limit.
- Không chờ vô hạn trên Future.get(), CountDownLatch hoặc distributed lock.
- Circuit breaker cho dependency mất khả năng đáp ứng.
- Rate limiter/concurrency limit để không gây overload upstream.
- Retry có backoff và tổng deadline rõ ràng.

Ví dụ nguyên tắc:

    ProcessingDeadlinePerRecord = 2 giây
    max.poll.records = 100
    Worst-case sequential processing ~= 200 giây

Nếu poll interval group là 300 giây, thời gian xử lý tệ nhất này có thể còn sát ngưỡng sau khi cộng retry, commit và scheduling. Nếu cần độ trễ thấp hơn, giảm max.poll.records hoặc tối ưu thời gian mỗi record.

Các deadline phải thực tế; timeout quá ngắn có thể gây thất bại giả rồi tạo retry storm, còn timeout quá dài làm consumer khó phục hồi.

## 32. Tác động tới offset và độ tin cậy

NonResponsiveConsumerEvent không tự thay đổi consumer offset. Nhưng nếu ứng dụng quyết định restart hoặc consumer mất assignment, các record đã poll mà chưa commit có thể được giao lại.

Ví dụ:

    Group committed offset = 100
    Consumer poll offsets 100...109
    Xử lý thành công tới 103 nhưng chưa commit
    Consumer thread kẹt ở 104
    Monitor phát event
    Container dừng / group rebalance
    Consumer mới đọc lại từ committed offset 100

Khi đó các record 100–103 có thể được xử lý lần nữa. Đây là lý do cần:

- Idempotency theo eventId hoặc business unique key.
- Không commit offset sớm khi side effect còn đang thực hiện.
- Theo dõi group assignment và committed offset thật.
- Kiểm soát manual acknowledgment và async task.
- Với transactional Kafka read-process-write, giữ output và offset cùng transaction.
- Đảm bảo DLT/recovery không đánh dấu record là thành công khi publish thất bại.

Một supervisor restart consumer không thể thay thế idempotency. Consumer có thể chết mà không phát event, và Kafka vẫn cần có đường xử lý lại.

## 33. Consumer đang pause có cần alert riêng không?

Nếu operator chủ động pause container vì downstream rate limit, consumer lag có thể tăng, nhưng điều đó không tự là consumer non-responsive.

Nên có ba nhóm trạng thái:

1. **Running và đang xử lý:** consumer poll và listener có throughput.
2. **Running nhưng paused/idle:** consumer còn khỏe, công việc ít hoặc cố ý tạm dừng.
3. **Running nhưng non-responsive:** nhịp poll không đáp ứng ngưỡng.
4. **Stopped:** container đã kết thúc lifecycle.

Các trạng thái này không phải enum duy nhất của Spring Kafka; đây là cách phân loại vận hành để thiết kế dashboard.

Alert paused lâu có thể dựa trên SLO backlog/freshness, không nhất thiết dựa vào NonResponsiveConsumerEvent. Nếu đang pause nhưng JVM vẫn poll bình thường, event non-responsive không phải công cụ thích hợp để cảnh báo backlog.

## 34. Kiểm thử cấu hình monitorInterval

Một bài kiểm thử cần xác nhận rằng monitorInterval và noPollThreshold được áp dụng cho **factory thực sự dùng bởi listener**.

Các bước:

1. Tạo broker test tương thích (Embedded Kafka hoặc Testcontainers).
2. Tạo listener container với pollTimeout, noPollThreshold và monitorInterval được cấu hình rõ.
3. Đăng ký @EventListener nhận NonResponsiveConsumerEvent.
4. Chạy consumer bình thường, xác nhận nhịp poll không bị báo lỗi liên tục.
5. Mô phỏng tình huống consumer thread không trở lại poll đủ lâu.
6. Chờ event với timeout test lớn hơn threshold và một số chu kỳ monitor.
7. Xác nhận event chứa listenerId và timeSinceLastPoll phù hợp.
8. Giải phóng blocking condition, xác nhận consumer có thể hồi phục theo lifecycle.
9. Kiểm tra offset/duplicate sau restart hoặc rebalance nếu test có làm dừng container.

Không nên assert event xuất hiện đúng tại một millisecond xác định. Thời điểm phát phụ thuộc scheduler, machine load và môi trường test.

### 34.1. Test observer bằng ApplicationEventPublisher

Phần observer có thể test tách biệt với broker: publish một event giả hoặc gọi adapter/service nhận metadata đã chuẩn hóa rồi xác nhận metric/log được ghi.

Tuy nhiên, test này **không chứng minh** container monitor phát event đúng ngưỡng. Phần đó cần test tích hợp với listener container và broker hoặc một cơ chế test hạ tầng phù hợp.

### 34.2. Test khi topic không có record

Tạo một topic rỗng; consumer poll trả về empty đều đặn. Nếu đã bật idleEventInterval, có thể nhận idle event. Không được viết test đòi hỏi NonResponsiveConsumerEvent chỉ vì không có record.

### 34.3. Test listener block

Dùng một CountDownLatch trong business listener để giữ thread sau khi record đã poll:

~~~java
@Component
public class BlockingOrderListener {

    private final CountDownLatch release = new CountDownLatch(1);

    @KafkaListener(
        topics = "orders.monitor-test",
        groupId = "monitor-test-group",
        containerFactory = "testListenerFactory"
    )
    public void consume(String value) throws InterruptedException {
        release.await();
    }

    public void allowCompletion() {
        release.countDown();
    }
}
~~~

Test phải có finally block giải phóng latch và dừng container để tránh treo suite. Vì cách framework xác định last poll và mức độ block có thể khác phiên bản, cần xác nhận chính xác event được tạo trong môi trường test thay vì suy luận chỉ từ latch.

### 34.4. Test concurrency

Chạy nhiều child consumers và làm chỉ một listener thread bị block. Xác nhận monitoring nhận diện đúng child/source trong giới hạn của event API, các child khác vẫn có thể xử lý record và metric không bị hiểu thành toàn group chết.

## 35. Thử nghiệm với thread dump và fault injection

Một kịch bản điều tra chủ động:

1. Gửi record khiến listener gọi HTTP stub có độ trễ lớn.
2. Đặt request timeout dài hơn threshold monitor để thấy tín hiệu.
3. Thu thread dump ở thời điểm event.
4. Đối chiếu thread stack với log listener.
5. Kiểm tra downstream latency và request concurrency.
6. Sau đó giảm request timeout hợp lý.
7. Xác nhận số event non-responsive giảm và consumer không còn phải restart thường xuyên.

Kịch bản khác mô phỏng CPU throttling hoặc GC pause. Nếu JVM bị stop-the-world quá lâu, monitor task cũng có thể bị trì hoãn, nên sự kiện có thể đến muộn. Điều này chứng minh cần monitor JVM và Kubernetes/host ngoài Kafka.

Không tạo deadlock production chỉ để xác nhận monitor. Các fault injection phải chạy trong môi trường test hoặc staging với giới hạn và phương án thu hồi.

## 36. Runbook khi thấy NonResponsiveConsumerEvent

Một quy trình vận hành:

1. **Xác định phạm vi:** listenerId, groupId, instance/pod, thời điểm event, timeSinceLastPoll.
2. **Xác nhận lặp lại:** một lần hay nhiều chu kỳ monitor liên tiếp?
3. **Kiểm tra lifecycle:** container running, paused, stopping hay restart?
4. **Kiểm tra lag và freshness:** backlog tăng không, partition nào bị ảnh hưởng?
5. **Thu thread dump:** consumer thread đang ở poll, listener, lock, DB hay HTTP?
6. **Kiểm tra dependency:** latency, timeout, 429/503, pool saturation.
7. **Kiểm tra JVM/node:** GC pause, CPU throttling, OOM, scheduler delays.
8. **Kiểm tra group:** rebalance, lost partition, max.poll.interval.ms, committed offset.
9. **Phân loại nguyên nhân:** deadlock, xử lý quá lâu, dependency outage hay threshold quá nhạy.
10. **Chọn recovery:** timeout, giảm max.poll.records, pause/rate limit hoặc restart có kiểm soát.
11. **Kiểm soát duplicate:** idempotency và transaction khi record redelivery.
12. **Theo dõi sau sửa:** event count, processing latency, lag, commit rate.
13. **Cập nhật threshold và runbook:** chỉ thay cấu hình khi đã đo được nguyên nhân.

Đừng xử lý mọi event bằng cách increase monitorInterval. Đây chỉ là kéo dài chu kỳ kiểm tra và có thể làm sự cố được phát hiện muộn hơn mà không sửa nguyên nhân.

## 37. Những hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế |
|---|---|
| monitorInterval là thời gian tối đa Kafka poll được block | Nó là chu kỳ monitor kiểm tra |
| setMonitorInterval(10) nghĩa là 10 ms | Với API Spring Kafka phổ biến, giá trị là giây |
| NonResponsiveConsumerEvent nghĩa là topic không có record | Idle và non-responsive là hai trạng thái khác nhau |
| Đã nhận event nghĩa là consumer chắc chắn deadlock | Có thể do listener lâu, GC, CPU hoặc config |
| Giảm monitorInterval sẽ làm ngưỡng no-poll nhỏ lại | Ngưỡng dựa trên pollTimeout * noPollThreshold |
| noPollThreshold là số lần poll thất bại | Đây là hệ số ngưỡng thời gian |
| monitorInterval bảo vệ group khỏi rebalance | max.poll.interval.ms và group protocol độc lập |
| isRunning() là đủ để biết consumer khỏe | Consumer có thể running nhưng không poll tiến triển |
| Idle event là cảnh báo consumer không phản hồi | Idle event nói về thiếu record |
| Gọi stop() đồng bộ ngay trong callback luôn an toàn | Có nguy cơ block monitor, restart loop |
| KafkaConsumer dùng từ mọi thread đều an toàn | KafkaConsumer không thread-safe |
| Restart sau non-responsive bảo đảm không duplicate | Record chưa commit có thể redelivery |
| Pause container đồng nghĩa consumer đã dừng poll | Container thường vẫn duy trì poll để giữ membership |
| Monitor có thể phát event ngay cả khi JVM chết | Local monitor cũng dừng theo process |

## 38. Nguyên tắc thiết kế production

- Dùng monitorInterval để điều chỉnh **chu kỳ quan sát**, không coi nó là timeout Kafka client.
- Đặt noPollThreshold cùng pollTimeout để tạo ngưỡng phát hiện non-responsive.
- Giữ đơn vị đo rõ ràng: pollTimeout milliseconds, monitorInterval seconds.
- Phân biệt ListenerContainerIdleEvent và NonResponsiveConsumerEvent.
- Theo dõi cả poll duration, processing duration, lag, rebalance và downstream latency.
- Không dựa trên một event đơn lẻ để auto-restart toàn group.
- Dùng supervisor có backoff/cooldown, tránh chạy stop đồng bộ lâu trong event callback.
- Không thao tác trực tiếp raw KafkaConsumer từ thread monitor hoặc event listener bất đồng bộ.
- Không coi isRunning=true là bằng chứng consumer đang xử lý tiến triển.
- Đảm bảo timeout và bounded concurrency cho dependency.
- Dùng max.poll.records phù hợp với thời gian xử lý một poll và max.poll.interval.ms.
- Với pause/backpressure, dùng API pause/resume thay vì cố mô phỏng bằng monitor.
- Bảo vệ side effect idempotent khi restart/rebalance làm record redelivery.
- Giám sát từ bên ngoài JVM để phát hiện crash hoặc GC/thread starvation làm local monitor không chạy.
- Kiểm thử cả healthy idle topic, blocked listener, async monitoring, concurrency và restart.

## 39. Kết luận

**monitorInterval quyết định Spring Kafka kiểm tra consumer có phản hồi theo chu kỳ bao lâu một lần**. Kết hợp pollTimeout và noPollThreshold, nó hỗ trợ phát hiện dấu hiệu vòng poll không tiến triển, thường thông qua NonResponsiveConsumerEvent. Giá trị nhỏ làm phát hiện nhanh hơn nhưng có thể tăng cảnh báo giả; giá trị lớn làm chẩn đoán chậm hơn. Không có một con số đúng cho mọi listener.

Một hệ thống đáng tin cậy phải xem monitorInterval là **cảm biến**, không phải bộ điều khiển duy nhất. Muốn xử lý consumer chậm hoặc bị kẹt, cần xác định nguyên nhân ở listener, Kafka client, dependency, JVM hoặc group lifecycle; sau đó áp dụng timeout, backpressure, retry/recovery và idempotency phù hợp. Khi đó sự kiện non-responsive giúp phát hiện sớm mà không trở thành nguyên nhân của vòng lặp restart và mất ổn định consumer group.
