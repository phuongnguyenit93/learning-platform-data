# pollTimeout

Trong Spring Kafka, một Kafka listener không chủ động nhận record bằng cách được broker “gọi ngược” mỗi khi có dữ liệu. Thay vào đó, Kafka consumer thực hiện vòng lặp **`poll()`**: yêu cầu/nhận dữ liệu từ broker, tham gia cơ chế consumer group, xử lý những sự kiện nội bộ rồi giao các record nhận được cho listener container. Khi không có record sẵn sàng, `poll()` có thể phải chờ.

**`pollTimeout`** là thuộc tính quan trọng của Spring Kafka listener container, xác định **khoảng thời gian tối đa mà một lần gọi `KafkaConsumer.poll(Duration)` có thể chờ trong điều kiện thông thường**. Nó ảnh hưởng tới nhịp vòng poll, cách container quan sát trạng thái idle, mức độ thường xuyên kiểm tra các điều kiện lifecycle và việc chẩn đoán consumer không phản hồi.

Trong chương **Idle và non-responsive**, cần hiểu `pollTimeout` cùng các cơ chế `idleEventInterval`, `idlePartitionEventInterval`, `NonResponsiveConsumerEvent`, `noPollThreshold` và `monitorInterval`. Quan trọng nhất: **pollTimeout không phải timeout xử lý một record, không phải deadline transaction và không phải `max.poll.interval.ms`**.

## 1. Vòng poll của Kafka consumer

Một listener container trong Spring Kafka về mặt khái niệm thực hiện:

~~~text
Spring Kafka listener container
          |
          v
       poll(timeout)
          |
          +---- Có record sẵn sàng -> trả về ConsumerRecords
          |
          +---- Không có record -> chờ tối đa theo timeout
          |
          v
   Container giao record cho listener
          |
          v
   Error handling / acknowledgment / transaction
          |
          v
       poll(timeout) tiếp theo
~~~

Khi có record trả về, container xử lý chúng theo kiểu record listener hoặc batch listener, ack mode, error handler và transaction configuration. Khi không có record, `poll()` thường trả về một tập record rỗng lúc hết timeout; container có thể tiếp tục vòng lặp để thực hiện các kiểm tra lifecycle.

Ví dụ Kafka consumer API thuần:

~~~java
ConsumerRecords<String, String> records =
        consumer.poll(Duration.ofMillis(3_000));
~~~

Đối số `Duration` là **khoảng chờ tối đa cho một lời gọi poll**, không phải chu kỳ bắt buộc “cứ đúng ba giây mới nhận dữ liệu”. Nếu dữ liệu được fetch sẵn sàng, `poll()` có thể trả về sớm; nếu consumer đang cần tham gia group hoặc xử lý callback, thời gian thực tế còn phụ thuộc Kafka client và scheduler.

Spring Kafka dùng consumer API này phía trong listener container. Với ứng dụng dùng `@KafkaListener`, thông thường **không tự gọi `consumer.poll()`** trong listener; container chịu trách nhiệm polling.

## 2. Định nghĩa pollTimeout của Spring Kafka

Spring Kafka cung cấp `ContainerProperties.setPollTimeout(long)` để cấu hình thời gian chờ cho mỗi vòng `poll()`.

Ví dụ:

~~~java
factory.getContainerProperties().setPollTimeout(3_000L);
~~~

Giá trị được biểu diễn bằng **millisecond**: `3_000L` tương đương ba giây. Ở nhiều phiên bản Spring Kafka, giá trị mặc định của `pollTimeout` là **5.000 ms**; luôn kiểm tra API và các giá trị mặc định của phiên bản ứng dụng đang triển khai.

Tác động chính:

- **Timeout ngắn**: consumer quay lại từ những poll rỗng thường xuyên hơn, container có cơ hội kiểm tra idle/lifecycle thường xuyên hơn, nhưng có thể tăng overhead.
- **Timeout dài**: khi topic không có dữ liệu, consumer có thể chờ lâu hơn trong một lời gọi poll, giảm số lần poll rỗng; độ chi tiết thời gian của một số phép kiểm tra sau poll có thể giảm.
- **Khi record có sẵn**: `poll()` có thể trả về trước timeout; đặt `pollTimeout=5s` không mặc nhiên thêm năm giây độ trễ cho từng message.
- **Khi listener xử lý record lâu**: thời gian xử lý nằm ngoài ý nghĩa giới hạn chờ của `pollTimeout`.

Không nên coi `pollTimeout` là biện pháp trực tiếp để tăng throughput. Trong nhiều ứng dụng, giới hạn throughput nằm ở số partition, logic nghiệp vụ, kích thước batch, serializer, database hoặc HTTP dependency.

## 3. Cấu hình pollTimeout trên listener container factory

Một cấu hình Spring Kafka đầy đủ ở mức cơ bản:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;

@Configuration
public class OrderKafkaListenerConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
            orderListenerFactory(
                    ConsumerFactory<String, OrderEvent> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);

        // Consumer poll() có thể chờ tối đa 2 giây khi chưa có dữ liệu.
        factory.getContainerProperties().setPollTimeout(2_000L);

        return factory;
    }
}
~~~

Listener sử dụng factory:

~~~java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderEventListener {

    private final OrderService orderService;

    public OrderEventListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
            id = "orders-processor",
            groupId = "orders-service",
            topics = "orders.events",
            containerFactory = "orderListenerFactory")
    public void onOrder(OrderEvent event) {
        orderService.process(event);
    }
}
~~~

`OrderEvent` và `OrderService` là kiểu nghiệp vụ minh họa. Để chạy ứng dụng thật, còn cần cấu hình Kafka bootstrap servers, key/value deserializer, topic và các dependency cần thiết.

Điểm quan trọng:

1. `pollTimeout` thuộc **container properties**, không phải Kafka broker property.
2. `factory.setConcurrency(3)` ảnh hưởng số consumer child containers; `pollTimeout` áp dụng cho vòng poll của những consumer được container tạo.
3. Nếu một ứng dụng có nhiều container factory, hãy cấu hình đúng factory mà `@KafkaListener` đang dùng.
4. Nếu tự cấu hình listener containers ngoài `@KafkaListener`, cần đặt property trên chính `ContainerProperties` của những container đó.
5. Đừng sửa nhầm `spring.kafka.consumer.properties.max.poll.interval.ms` rồi nghĩ là đã thay đổi `pollTimeout`; đó là hai giới hạn khác nhau.

### 3.1. Spring Boot property

Các dòng Spring Boot hỗ trợ cấu hình `spring.kafka.listener.poll-timeout` có thể ánh xạ thời lượng vào container mặc định, ví dụ:

~~~yaml
spring:
  kafka:
    listener:
      poll-timeout: 2s
~~~

Với ứng dụng tự tạo `ConcurrentKafkaListenerContainerFactory`, hãy kiểm tra cấu hình Boot có được áp dụng lên factory đó hay không. Nếu factory không được cấu hình bởi `ConcurrentKafkaListenerContainerFactoryConfigurer` hoặc cơ chế tương đương, một YAML property có thể không tự động ghi đè các properties của custom factory.

Dùng cách đặt trực tiếp trên container factory khi cần kiểm soát rõ ràng; kiểm tra property binding của phiên bản Spring Boot trước khi kết luận runtime dùng giá trị mong đợi.

## 4. pollTimeout không có nghĩa “chờ đủ thời gian mới nhận record”

Ví dụ `pollTimeout = 5_000 ms`:

~~~text
T0     Consumer gọi poll(5s)
T0+20ms Broker/consumer đã có record khả dụng
T0+25ms poll trả về và container bắt đầu xử lý
~~~

Trong kịch bản này, record không bị giữ lại cho đủ năm giây. `pollTimeout` là giới hạn chờ của lời gọi poll, không phải batch timer bắt buộc.

Ngược lại, nếu topic rỗng:

~~~text
T0     poll(5s)
T0+5s  poll có thể trả về rỗng
T0+5s  container kiểm tra trạng thái, rồi gọi poll tiếp
~~~

Thời gian thực tế chịu ảnh hưởng bởi Kafka client, trạng thái consumer group, scheduler và các request đang diễn ra. Vì vậy một hệ thống không có dữ liệu có thể thấy poll rỗng lặp lại, nhưng không nên suy ra những lần poll bắt đầu đúng tại mốc 0, 5, 10, 15 giây.

## 5. Ảnh hưởng tới idleEventInterval

Spring Kafka có `idleEventInterval` để phát `ListenerContainerIdleEvent` khi container không nhận record trong khoảng thời gian cấu hình. Khi đánh giá thời điểm phát event, cần xét cả `pollTimeout` vì container thường kiểm tra điều kiện idle trong vòng xử lý polling.

Ví dụ:

~~~java
factory.getContainerProperties().setPollTimeout(1_000L);
factory.getContainerProperties().setIdleEventInterval(10_000L);
~~~

Sơ đồ minh họa khi không có record:

~~~text
poll ~1s -> rỗng -> poll ~1s -> rỗng -> ...
                           |
                    sau khi idle đủ lâu
                           |
                           v
               ListenerContainerIdleEvent
~~~

Với một poll timeout rất dài, điều kiện idle có thể chỉ được xem xét khi container có cơ hội thực thi nhánh kiểm tra tương ứng. Điều đó có thể khiến event xuất hiện **trễ hơn ngưỡng idle được cấu hình**.

### 5.1. Chọn pollTimeout so với idleEventInterval

Giả sử ứng dụng muốn nhận tín hiệu idle sau khoảng 15 giây. Một cấu hình dễ quan sát hơn có thể là:

~~~java
factory.getContainerProperties().setPollTimeout(2_000L);
factory.getContainerProperties().setIdleEventInterval(15_000L);
~~~

Không nên đặt `pollTimeout` lớn hơn nhiều so với `idleEventInterval` rồi mong sự kiện luôn được phát đúng thời điểm 15 giây. Các event không phải timer real-time; độ trễ còn phụ thuộc scheduling và vòng poll.

Tuy nhiên, cũng không cần giảm `pollTimeout` xuống vài millisecond chỉ để có timestamp event cực kỳ sát ngưỡng. Làm vậy có thể tạo quá nhiều vòng poll rỗng và overhead giám sát.

### 5.2. Idle không đồng nghĩa consumer không phản hồi

Một container **idle** vẫn có thể thực hiện `poll()` bình thường và nhận tập record rỗng. Đây là trạng thái thường gặp với topic ít traffic.

Một container **non-responsive** có thể bị kẹt trong một lần poll hoặc không trở lại vòng poll theo kỳ vọng. Hai tình huống cần metric và hành động khác nhau:

| Tình huống | Poll có tiếp tục? | Có record? | Cách hiểu |
|---|---|---|---|
| Topic rỗng, consumer bình thường | Có | Không | Idle bình thường. |
| Một partition không có dữ liệu | Có | Các partition khác có thể có | Partition idle, không nhất thiết container idle. |
| Listener xử lý quá lâu giữa các poll | Không đều | Có thể có backlog | Nguy cơ vi phạm `max.poll.interval.ms`. |
| Consumer bị kẹt trong poll/request | Không trả về đúng thời gian kỳ vọng | Không xác định | Cần điều tra non-responsive. |
| Container đã stop | Không | Không | Lifecycle stopped; không phải idle running. |

## 6. pollTimeout và NonResponsiveConsumerEvent

Spring Kafka cung cấp `NonResponsiveConsumerEvent` để giúp phát hiện consumer không thực hiện/hoàn tất polling như kỳ vọng theo cơ chế monitor của container. Cấu hình liên quan gồm:

- **`pollTimeout`**: thời gian chờ của một lần poll.
- **`noPollThreshold`**: hệ số nhân dùng cùng poll timeout để xác định ngưỡng kiểm tra không poll.
- **`monitorInterval`**: chu kỳ monitor kiểm tra trạng thái consumer; đơn vị cấu hình của property này cần theo API phiên bản.
- **`NonResponsiveConsumerEvent`**: application event thông báo dấu hiệu consumer không phản hồi theo ngưỡng monitor.

Ví dụ:

~~~java
factory.getContainerProperties().setPollTimeout(2_000L);
factory.getContainerProperties().setNoPollThreshold(3.0f);
factory.getContainerProperties().setMonitorInterval(5);
~~~

Về mặt ý tưởng:

~~~text
pollTimeout         = 2 giây
noPollThreshold     = 3.0
ngưỡng theo tích    = khoảng 6 giây
monitorInterval     = kiểm tra mỗi 5 giây
~~~

Ngưỡng khoảng sáu giây **không** có nghĩa event luôn được phát đúng tại giây thứ sáu. Monitor chạy theo chu kỳ của nó; event có thể được phát ở một lần kiểm tra sau khi vượt ngưỡng. Ngoài ra, container có thể vẫn chưa trở về vòng poll vì xử lý record quá lâu, không chỉ vì Kafka network bị treo.

`monitorInterval` ở `ContainerProperties` thường được cấu hình bằng giây, trong khi `pollTimeout` dùng millisecond. Đây là một lỗi đơn vị rất dễ gặp khi người vận hành chuyển giá trị cấu hình giữa API Java và YAML.

### 6.1. Vì sao cần cân chỉnh ba tham số?

Một cấu hình gây nhiễu:

~~~text
pollTimeout = 10 giây
noPollThreshold = 1.1
monitorInterval = 1 giây
~~~

Khi một lời gọi poll bình thường mất gần 10 giây, ngưỡng không poll theo tích chỉ khoảng 11 giây. Chênh lệch quá nhỏ có thể tạo cảnh báo khi chỉ có scheduling jitter hoặc đường xử lý callback hợp lệ.

Một cấu hình khác:

~~~text
pollTimeout = 1 giây
noPollThreshold = 20
monitorInterval = 60 giây
~~~

Ngưỡng khoảng 20 giây nhưng monitor chỉ kiểm tra mỗi 60 giây. Sự cố có thể không được báo kịp thời, dù ngưỡng nội bộ thấp hơn nhiều.

Nên chọn `monitorInterval` đủ nhỏ để phát hiện lỗi theo SLO vận hành, nhưng không quá ngắn để tự tạo overhead. Ngưỡng `noPollThreshold × pollTimeout` cần đủ rộng để phân biệt poll bình thường với consumer thực sự chậm/kẹt theo hành vi tải hiện tại.

### 6.2. Nhận NonResponsiveConsumerEvent

Ví dụ:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.NonResponsiveConsumerEvent;
import org.springframework.stereotype.Component;

@Component
public class KafkaNonResponsiveObserver {

    @EventListener
    public void onNonResponsive(NonResponsiveConsumerEvent event) {
        log.warn("Kafka consumer non-responsive: source={}, container={}",
                event.getSource(),
                event.getContainer());
    }
}
~~~

`log` là logger của class. Khi nhận event, không nên lập tức reset offsets hoặc kết luận broker chắc chắn lỗi. Cần xem thread dump, listener processing time, Kafka client logs, rebalance, pause state và các timeouts khác.

## 7. pollTimeout và idlePartitionEventInterval

`idlePartitionEventInterval` theo dõi **từng topic-partition** không nhận record trong khoảng thời gian cấu hình. `pollTimeout` vẫn là thời gian chờ của vòng poll nền tảng.

Ví dụ:

~~~java
factory.getContainerProperties().setPollTimeout(1_500L);
factory.getContainerProperties().setIdlePartitionEventInterval(30_000L);
~~~

Sơ đồ:

~~~text
Topic orders.events
  p0: record liên tục -----+
  p1: im lặng 30 giây ----+----> listener container vẫn polling
  p2: record liên tục -----+
                                 |
                                 v
                     PartitionIdleEvent cho p1
~~~

Khi những partition khác có record, `poll()` có thể trả về sớm. Khi toàn bộ topic rỗng, poll có thể chờ gần hết timeout. Vì vậy việc phát partition idle event có thể bị ảnh hưởng bởi nhịp container xử lý poll, nhưng không phải đơn giản “mỗi pollTimeout phát một idle event”.

Nếu một partition bị **pause**, container có thể không nhận record từ partition đó dù producer vẫn ghi. Trước khi kết luận upstream im lặng, kiểm tra pause state và consumer lag.

## 8. pollTimeout khi container bị pause

Spring Kafka cho phép pause toàn container hoặc từng partition để điều tiết tải. Pause không nhất thiết đồng nghĩa ngừng hoàn toàn polling; consumer thường vẫn phải duy trì một số hoạt động cần thiết cho consumer group.

Một số phiên bản Spring Kafka hỗ trợ property **`pollTimeoutWhilePaused`** để dùng một thời gian chờ poll riêng khi container ở trạng thái paused. Vì vậy:

- `pollTimeout` điều khiển vòng poll thông thường.
- `pollTimeoutWhilePaused`, nếu phiên bản hỗ trợ và được áp dụng trong trạng thái pause, điều chỉnh vòng poll khi container paused.
- `pause()` không đồng nghĩa `stop()`.
- Chỉ thay đổi `pollTimeout` chưa chắc thay đổi toàn bộ nhịp polling trong trạng thái paused.

Ví dụ cấu hình trên container properties khi API phiên bản hỗ trợ:

~~~java
factory.getContainerProperties().setPollTimeout(5_000L);
factory.getContainerProperties().setPollTimeoutWhilePaused(200L);
~~~

Thời gian chờ khi paused có thể ngắn hơn để container phản ứng nhanh với lệnh resume và kiểm tra lifecycle. Nhưng không vì vậy mà consumer phải liên tục nhận record từ partition đã pause.

Khi xử lý backpressure, cần xem cả `pauseImmediate`, `idleBetweenPolls`, container state và hành vi retry trong phiên bản Spring Kafka. Những tham số này phục vụ các mục tiêu khác nhau; không điều chỉnh tất cả cùng lúc mà không đo tác động.

## 9. pollTimeout và idleBetweenPolls

Spring Kafka có thể cấu hình khoảng nghỉ **giữa các lần poll** bằng `idleBetweenPolls` trong những phiên bản hỗ trợ. Thuộc tính này khác `pollTimeout`:

~~~text
poll(timeout):
    có thể chờ dữ liệu trong chính lời gọi poll

idleBetweenPolls:
    khoảng nghỉ chủ động giữa các vòng poll, theo chính sách container
~~~

Ví dụ:

~~~java
factory.getContainerProperties().setPollTimeout(1_000L);
factory.getContainerProperties().setIdleBetweenPolls(200L);
~~~

Với topic rỗng, thời gian giữa hai vòng lặp có thể gồm **thời gian poll thực tế + khoảng nghỉ giữa poll + overhead xử lý**. Không thể lấy `1_000ms` làm tổng thời gian chính xác giữa các lần bắt đầu poll.

Khoảng nghỉ giữa poll có thể giúp điều tiết nhịp lấy dữ liệu, nhưng phải tính tới giới hạn `max.poll.interval.ms`. Nếu listener xử lý một batch lâu rồi còn chủ động nghỉ dài, consumer có thể chậm gọi poll tiếp theo và bị Kafka group coordinator xem không tiến triển đúng yêu cầu.

## 10. pollTimeout không phải max.poll.interval.ms

Đây là hai khái niệm dễ nhầm nhất:

| Thuộc tính | Thuộc về | Mục đích |
|---|---|---|
| `pollTimeout` | Spring Kafka listener container | Timeout tối đa cho **một lời gọi** `poll(Duration)`. |
| `max.poll.interval.ms` | Kafka consumer client | Giới hạn khoảng thời gian giữa các lần `poll()`, dùng để phát hiện application không poll đủ thường xuyên. |
| `session.timeout.ms` | Kafka consumer group | Liên quan việc broker đánh giá liveness/session của member qua heartbeat. |
| `heartbeat.interval.ms` | Kafka consumer (tùy group protocol) | Nhịp heartbeat theo cơ chế consumer group. |
| `request.timeout.ms` | Kafka client | Giới hạn chờ phản hồi request mạng của client. |
| `fetch.max.wait.ms` | Kafka consumer/broker fetch | Giới hạn chờ phía broker trước khi trả fetch khi chưa đủ lượng dữ liệu, theo cấu hình fetch. |

Ví dụ:

~~~yaml
spring:
  kafka:
    listener:
      poll-timeout: 2s
    consumer:
      properties:
        max.poll.interval.ms: 300000
~~~

Điều này **không** có nghĩa mỗi record được xử lý tối đa 2 giây. Nó có nghĩa container thường poll với timeout hai giây; khoảng cách giữa các lần poll theo giới hạn consumer group là 300 giây trong ví dụ.

Một batch listener xử lý 350 giây có thể vi phạm `max.poll.interval.ms` ngay cả khi `pollTimeout` chỉ 500 millisecond. Vấn đề nằm ở **listener không quay lại poll đủ sớm**, không phải thời gian chờ trong một poll rỗng.

### 10.1. Ví dụ vi phạm max.poll.interval.ms

~~~text
T0: consumer.poll(2s) trả về 500 records
T0+1s: listener bắt đầu xử lý batch
T0+320s: listener mới hoàn tất
T0+320s: consumer chuẩn bị poll lần tiếp theo
~~~

Nếu `max.poll.interval.ms = 300_000`, consumer có thể mất quyền group membership hoặc gặp các hậu quả liên quan generation/assignment theo phiên bản và consumer group protocol, dù `pollTimeout` chưa từng dài hơn hai giây.

Biện pháp phù hợp có thể gồm tối ưu batch, giảm `max.poll.records`, giới hạn thời gian gọi dependency hoặc thiết kế async processing phù hợp. Chỉ giảm `pollTimeout` không sửa được một listener đang xử lý batch quá lâu.

## 11. pollTimeout và graceful shutdown

Khi ứng dụng nhận lệnh dừng, Spring Kafka container phải phối hợp với consumer thread để ngừng vòng polling và đóng KafkaConsumer.

~~~text
SIGTERM / ApplicationContext shutdown
                 |
                 v
container.stop() / Spring lifecycle stop
                 |
                 v
đánh thức/điều phối vòng poll, xử lý shutdown
                 |
                 v
consumer close và ContainerStoppedEvent
~~~

Một `pollTimeout` dài có thể ảnh hưởng tới thời điểm container thường xuyên rời khỏi poll khi không có dữ liệu. Tuy nhiên, KafkaConsumer có cơ chế **`wakeup()`** để phá vỡ việc chờ poll trong nhiều đường shutdown; vì vậy **không được mặc định độ trễ stop luôn bằng toàn bộ pollTimeout**.

Thời gian stop thực tế phụ thuộc:

- Listener đang xử lý record/batch hay đang chờ trong `poll()`.
- Dependency timeout của HTTP/database.
- Offset commit và Kafka transaction commit/abort.
- Error handler, retry và backoff.
- `shutdownTimeout` của container.
- Spring lifecycle shutdown phase timeout.
- Kubernetes termination grace period.

Nếu một listener đang chờ HTTP response 60 giây mà dependency không có timeout hợp lý, giảm `pollTimeout` từ 5 giây xuống 500ms có thể không cải thiện thời gian shutdown: consumer đang ở **business processing**, không phải đang chờ poll.

### 11.1. Phối hợp với Spring Boot và Kubernetes

Ví dụ:

~~~yaml
spring:
  lifecycle:
    timeout-per-shutdown-phase: 45s

server:
  shutdown: graceful
~~~

Nếu chạy trên Kubernetes, `terminationGracePeriodSeconds` phải bao quát ngân sách dừng phù hợp, có dự phòng cho cleanup và đóng kết nối.

~~~yaml
spec:
  terminationGracePeriodSeconds: 60
~~~

Nếu container bị `SIGKILL` trước khi stop hoàn tất, các application lifecycle events không được bảo đảm phát ra, offset chưa commit có thể được xử lý lại. Vì vậy cần idempotency, không chỉ điều chỉnh poll timeout.

## 12. pollTimeout, throughput và CPU/network overhead

Một lựa chọn `pollTimeout` quá ngắn có thể khiến consumer thường xuyên thực hiện poll rỗng khi topic rất ít traffic. Overhead có thể bao gồm các lần quay vòng nội bộ, kiểm tra trạng thái và scheduling, dù Kafka client/broker vẫn áp dụng các tối ưu fetch riêng.

Một timeout dài hơn có thể giảm vòng polling rỗng, nhưng có thể làm các mốc kiểm tra idle/lifecycle ở application trở nên thô hơn khi ứng dụng không nhận dữ liệu.

| Cấu hình | Lợi ích có thể có | Rủi ro cần cân nhắc |
|---|---|---|
| 100–500 ms | Phản hồi nhanh cho một số vòng kiểm tra sau poll | Nhiều vòng poll rỗng hơn với topic ít dữ liệu. |
| 1–5 giây | Cân bằng đơn giản cho nhiều workload | Idle event timing phụ thuộc nhịp poll. |
| Vài chục giây | Ít vòng poll rỗng khi topic rất thưa | Monitor/idle detection có thể kém nhạy, cần đánh giá timeout khác. |
| Tùy biến khi paused | Tách hành vi pause và running | Phải xác minh `pollTimeoutWhilePaused` và container state. |

Các khoảng trong bảng chỉ là **ví dụ để phân tích trade-off**, không phải benchmark hay khuyến nghị universal. Hãy đo trên workload thật thay vì chọn giá trị theo cảm tính.

Đặc biệt, khi topic có nhiều record, `poll()` có thể trả về nhanh ở cả timeout ngắn và dài. Throughput lúc này thường chịu ảnh hưởng lớn hơn từ `max.poll.records`, xử lý message và số consumer/partition.

## 13. pollTimeout và max.poll.records

`max.poll.records` là Kafka consumer property giới hạn số record được trả về trong một lần `poll()`. Nó **không** quyết định thời gian chờ poll, nhưng ảnh hưởng lượng công việc container phải xử lý trước lần poll tiếp theo.

Ví dụ:

~~~yaml
spring:
  kafka:
    listener:
      poll-timeout: 2s
    consumer:
      properties:
        max.poll.records: 200
        max.poll.interval.ms: 300000
~~~

Nếu mỗi record mất trung bình 500ms và container xử lý tuần tự 200 records, tổng thời gian nghiệp vụ có thể xấp xỉ 100 giây, chưa tính overhead; đây là mức có ý nghĩa hơn đối với `max.poll.interval.ms` so với `pollTimeout=2s`.

Khi điều tra consumer không poll đủ thường xuyên, cần xem:

1. Số record mỗi poll và số partition được assign.
2. Kiểu listener record/batch.
3. Thời gian xử lý trung bình và percentile cao.
4. Retry/backoff có giữ consumer thread không.
5. Timeout của API/database gọi trong listener.
6. `max.poll.interval.ms` và các đường pause/resume.

Không tăng `max.poll.interval.ms` vô hạn để che giấu một listener bị kẹt. Cần xử lý root cause và giới hạn thời gian xử lý.

## 14. Event monitoring với @EventListener

Có thể quan sát idle và non-responsive events để phân biệt “không có dữ liệu” với “consumer bị kẹt”.

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ListenerContainerIdleEvent;
import org.springframework.kafka.event.NonResponsiveConsumerEvent;
import org.springframework.stereotype.Component;

@Component
public class ConsumerPollingObserver {

    private static final Logger log =
            LoggerFactory.getLogger(ConsumerPollingObserver.class);

    @EventListener
    public void onIdle(ListenerContainerIdleEvent event) {
        log.info("Kafka listener idle: source={}", event.getSource());
    }

    @EventListener
    public void onNonResponsive(NonResponsiveConsumerEvent event) {
        log.warn("Kafka consumer non-responsive: source={}",
                event.getSource());
    }
}
~~~

Các event này là **Spring application events trong JVM**; không có Kafka topic hoặc offset độc lập. Các sự kiện có thể được publish bởi consumer/container thread và được xử lý đồng bộ theo multicaster mặc định. Vì vậy handler nên ngắn, không gọi HTTP/database lâu và không thao tác trực tiếp `KafkaConsumer` từ thread không phù hợp.

Chỉ có `ListenerContainerIdleEvent` chưa đủ chứng minh cluster khỏe mạnh; chỉ có `NonResponsiveConsumerEvent` cũng chưa đủ kết luận Kafka broker chết. Kết hợp logs và metrics để phân loại.

## 15. Quan sát bằng metrics và log

Một dashboard cho chương Idle và non-responsive nên có:

| Tín hiệu | Câu hỏi cần trả lời |
|---|---|
| Consumer poll rate / poll latency | Consumer có poll thường xuyên và poll mất bao lâu? |
| Time since last poll | Consumer đã không trở lại vòng poll trong bao lâu? |
| `NonResponsiveConsumerEvent` count | Có bao nhiêu tín hiệu monitor cho consumer bị kẹt? |
| `ListenerContainerIdleEvent` count | Container không nhận record trong khoảng nào? |
| Partition idle events | Partition nào không nhận record dù container vẫn có traffic? |
| Consumer lag per partition | Có backlog chưa commit không? |
| Listener processing latency | Business processing có làm chậm poll không? |
| Rebalance count/duration | Consumer đang mất group membership liên tục không? |
| Container running / paused state | Consumer đang chạy, pause hay stop? |
| Broker request latency / failures | Network/broker có gặp sự cố không? |

Một structured log minh họa:

~~~text
service=orders-worker
listener_id=orders-processor
group_id=orders-service
poll_timeout_ms=2000
no_poll_threshold=3.0
monitor_interval_seconds=5
event_type=NonResponsiveConsumerEvent
instance_id=orders-worker-2
~~~

Các trường này là metadata do ứng dụng/monitoring thêm vào; không phải tất cả đều là properties mặc định của event. Hạn chế dùng event ID, offset hoặc record key làm metric labels vì cardinality có thể tăng rất lớn.

### 15.1. Điều tra một cảnh báo non-responsive

Khi nhận NonResponsiveConsumerEvent:

1. Kiểm tra **container có đang running/paused/stopping** không.
2. Xem metric thời gian từ lần poll trước và thời gian xử lý listener.
3. Lấy thread dump nếu consumer thread có dấu hiệu bị chặn.
4. Kiểm tra Kafka client network logs, broker health và authentication.
5. Đối chiếu `pollTimeout × noPollThreshold` và `monitorInterval` đang áp dụng thực tế.
6. Xem `max.poll.interval.ms` và dấu hiệu group rebalance.
7. Kiểm tra retry/backoff, blocking API/database và lock contention.
8. Chỉ thay đổi timeout sau khi biết consumer bị kẹt ở **poll**, **listener processing** hay **shutdown**.

Nếu consumer vẫn poll rỗng bình thường và topic không có record, đây là **idle**, không phải non-responsive. Nếu consumer bị chặn trong HTTP call, giảm pollTimeout sẽ không giải quyết vấn đề.

## 16. Những tình huống pollTimeout thường bị cấu hình sai

### 16.1. Cấu hình quá thấp chỉ để giảm message latency

`pollTimeout=100ms` không bảo đảm mọi record có độ trễ dưới 100ms, vì độ trễ còn gồm producer batching, broker fetch, partition assignment, consumer scheduling, business processing và commit.

Nếu có yêu cầu latency nghiêm ngặt, đo end-to-end timestamp/lag và xử lý bottleneck thật.

### 16.2. Cấu hình quá cao rồi bỏ qua idle monitoring

Một poll timeout hàng chục giây có thể làm các vòng kiểm tra idle event bị thưa. Nếu cần phát hiện “nguồn không gửi record trong 10 giây”, poll timeout nên được chọn phù hợp độ chi tiết quan sát.

### 16.3. Đặt noPollThreshold thấp hơn hành vi poll bình thường

Ngưỡng monitor quá sát thời gian poll hợp lệ có thể gây cảnh báo non-responsive không cần thiết. Cần tính theo thời gian thực tế và scheduling jitter.

### 16.4. Dùng monitorInterval quá dài

Monitor chỉ chạy định kỳ. Nếu `monitorInterval` lớn hơn nhiều so với ngưỡng non-responsive, sự cố có thể được phát hiện muộn hơn mong muốn.

### 16.5. Nhầm pollTimeout với max.poll.interval.ms

Một listener xử lý batch 10 phút không được “cứu” chỉ bằng cách giảm `pollTimeout` xuống 100ms. Phải giảm thời gian giữ consumer giữa các lần poll hoặc điều chỉnh thiết kế processing.

### 16.6. Tin rằng pollTimeout bằng shutdownTimeout

`pollTimeout` quyết định cách poll chờ dữ liệu; `shutdownTimeout` quyết định ngân sách container chờ stop. KafkaConsumer wakeup và các công việc in-flight làm mối quan hệ giữa chúng không đơn giản.

### 16.7. Chỉ sửa YAML nhưng listener dùng custom factory khác

Nếu ứng dụng có nhiều `@KafkaListener(containerFactory="...")`, cấu hình Boot listener properties có thể không áp dụng cho từng factory tùy chỉnh. Cần xác nhận giá trị container properties thực tế.

## 17. Kiểm thử pollTimeout bằng Kafka broker thật

Nên sử dụng Embedded Kafka hoặc Kafka Testcontainers để kiểm tra hành vi listener container và các application events. Mock một lời gọi listener Java không đủ để chứng minh KafkaConsumer poll behavior.

Một bộ test có thể bao gồm:

1. **Topic rỗng:** cấu hình pollTimeout ngắn; xác nhận consumer container tiếp tục running và có thể phát idle event khi đạt ngưỡng.
2. **Record đến khi consumer đang poll:** gửi record sau khi start; xác nhận listener nhận record mà không phải chờ đúng hết pollTimeout.
3. **Idle event timing:** cấu hình `idleEventInterval` lớn hơn pollTimeout vài lần; chờ event bằng latch/queue có timeout hữu hạn.
4. **Partition idle:** cho một partition không có record trong khi partition khác có; xác nhận partition idle event nếu tính năng được bật.
5. **Consumer non-responsive:** dùng failpoint/proxy/test harness gây tình trạng poll không tiến triển, xem monitor event và khôi phục.
6. **Listener xử lý lâu:** tạo delay nghiệp vụ có kiểm soát; chứng minh pollTimeout ngắn không thay đổi giới hạn processing.
7. **Pause/resume:** xác nhận hành vi dùng pollTimeoutWhilePaused nếu được cấu hình và hỗ trợ.
8. **Shutdown:** gọi container.stop() khi topic rỗng hoặc listener đang xử lý; đo stop callback và thời gian shutdown.
9. **Concurrency:** chạy nhiều consumer child containers; xác nhận metric/event được gán đúng consumer/container.
10. **Restart/rebalance:** kiểm tra timeout và lifecycle khi một consumer mất rồi nhận lại partition.

### 17.1. Ví dụ test nhận ListenerContainerIdleEvent

Probe trong Spring context:

~~~java
import java.time.Duration;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ListenerContainerIdleEvent;
import org.springframework.stereotype.Component;

@Component
public class IdleEventProbe {

    private final BlockingQueue<ListenerContainerIdleEvent> queue =
            new LinkedBlockingQueue<>();

    @EventListener
    public void onIdle(ListenerContainerIdleEvent event) {
        queue.offer(event);
    }

    public ListenerContainerIdleEvent await(Duration timeout)
            throws InterruptedException {
        return queue.poll(timeout.toMillis(), TimeUnit.MILLISECONDS);
    }
}
~~~

Test với container factory đã bật `idleEventInterval`:

~~~java
@Test
void emptyTopicEventuallyProducesIdleEvent() throws Exception {
    MessageListenerContainer container =
            registry.getListenerContainer("orders-processor");

    assertThat(container).isNotNull();

    if (!container.isRunning()) {
        container.start();
    }

    ListenerContainerIdleEvent event =
            idleProbe.await(Duration.ofSeconds(30));

    assertThat(event).isNotNull();
}
~~~

`registry` là bean `KafkaListenerEndpointRegistry` được inject vào test, `idleProbe` là probe ở trên. Topic rỗng và consumer group phải được cách ly để listener không bị record của test khác làm mất điều kiện idle.

Nếu test context có nhiều listeners, lọc event theo listener/container ID để không lấy nhầm event của listener khác. Không dùng `Thread.sleep()` cố định thay cho chờ điều kiện có timeout.

### 17.2. Kiểm tra pollTimeout không áp đặt độ trễ record

Một kịch bản kiểm thử:

~~~text
1. Start container có pollTimeout=5s
2. Chờ consumer đã được assign partition
3. Gửi record mới tại T0
4. Dùng latch ghi nhận lúc listener xử lý record
5. Tính thời gian T_listener - T0
~~~

Giá trị latency có thể thay đổi theo máy chạy test, broker và scheduler. Test không nên assert một SLA không thực tế như “chắc chắn dưới 1ms”. Mục tiêu là chứng minh consumer có thể nhận record **trước khi hết toàn bộ pollTimeout** trong điều kiện phù hợp.

### 17.3. Kiểm thử non-responsive cần fault injection riêng

Một unit test chỉ gọi trực tiếp method `onNonResponsive()` không chứng minh container monitor đã phát hiện consumer kẹt. Để kiểm tra event thật, cần tạo điều kiện khiến consumer không poll/không trở về vòng poll theo threshold, rồi chờ event.

Có thể sử dụng test-specific blocking listener hoặc proxy/network fault, nhưng phải phân biệt rõ mình đang mô phỏng **listener blocking** hay **consumer poll blocking**. Đo thời gian và state thực tế để tránh test false positive.

Đừng dùng những fault injections kéo dài hoặc không có cleanup trên CI shared environment. Luôn đặt timeout và giải phóng latch, consumer, topic, process khi test hoàn tất.

## 18. Cách chọn pollTimeout theo mục tiêu

| Mục tiêu vận hành | Hướng cấu hình |
|---|---|
| Topic có record liên tục, cần throughput ổn định | Giữ giá trị hợp lý, tối ưu listener/batch/concurrency trước khi giảm pollTimeout. |
| Topic rất ít dữ liệu | Tránh timeout quá ngắn nếu tạo nhiều vòng poll rỗng không cần thiết. |
| Muốn phát hiện container idle trong vài giây | Chọn pollTimeout tương xứng với idleEventInterval và khả năng scheduler. |
| Cần cảnh báo non-responsive nhanh | Cân chỉnh pollTimeout, noPollThreshold, monitorInterval như một bộ. |
| Container có thể pause để backpressure | Kiểm tra pollTimeoutWhilePaused và cơ chế pause/resume. |
| Listener xử lý record lâu | Tập trung processing time, max.poll.interval.ms, max.poll.records và dependency timeouts. |
| Shutdown chậm | Đo giai đoạn đang chờ poll hay đang xử lý, kiểm tra wakeup và shutdownTimeout. |
| Nhiều listeners/factories trong ứng dụng | Xác nhận property áp dụng cho factory/container thực tế. |

Không có một giá trị `pollTimeout` tốt nhất cho tất cả hệ thống. Nên bắt đầu bằng cấu hình vừa phải, đo thời gian poll thực tế, idle-event delivery, error rate và hiệu quả shutdown, sau đó điều chỉnh có kiểm soát.

## 19. Checklist production

Trước khi thay đổi `pollTimeout` trong một hệ thống Spring Kafka đang chạy, hãy trả lời:

- Listener có bao nhiêu consumer threads và mỗi consumer giữ bao nhiêu partition?
- Consumer chủ yếu đang chờ dữ liệu hay bị giới hạn bởi processing?
- `pollTimeout` được cấu hình ở factory nào, có bị custom factory ghi đè không?
- Phiên bản Spring Kafka/Boot có default và unit nào cho những properties liên quan?
- `idleEventInterval` và `idlePartitionEventInterval` có bật không?
- `noPollThreshold × pollTimeout` tạo ngưỡng non-responsive bao lâu?
- `monitorInterval` có đủ thường xuyên so với ngưỡng đó không?
- Consumer có sử dụng `pollTimeoutWhilePaused` hoặc `idleBetweenPolls` không?
- `max.poll.interval.ms` có đủ lớn với batch/record processing time không?
- Có metric poll latency, processing latency, lag và rebalance không?
- Shutdown được kiểm thử khi topic rỗng và khi listener đang xử lý chưa?
- Alert idle có được phân biệt với partition pause, upstream outage và non-responsive không?
- Test có dùng broker thật và chờ điều kiện quan sát được thay vì timing cứng không?

**`pollTimeout`** là nút điều chỉnh **thời gian chờ của một vòng Kafka consumer poll**, không phải giới hạn xử lý nghiệp vụ. Trong chương **Idle và non-responsive**, giá trị của nó nằm ở sự phối hợp với idle-event intervals, consumer non-responsive monitor và vòng đời listener container. Hiểu đúng ranh giới của `pollTimeout` giúp ứng dụng quan sát chính xác hơn, tránh cảnh báo giả và tránh điều chỉnh sai một timeout khi nguyên nhân thật nằm ở listener processing, consumer group hoặc dependency bên ngoài Kafka.
