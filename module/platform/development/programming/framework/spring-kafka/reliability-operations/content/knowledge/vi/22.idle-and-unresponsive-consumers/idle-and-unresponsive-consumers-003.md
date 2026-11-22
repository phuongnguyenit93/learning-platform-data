# idleBeforeDataMultiplier

Trong Spring Kafka, một listener container có thể được khởi động thành công nhưng chưa nhận được record nào. Đây có thể là tình huống hoàn toàn bình thường: topic mới được tạo, producer chưa bắt đầu phát sự kiện, hệ thống đang triển khai lần đầu hoặc một phân vùng hiện chưa có dữ liệu. Nếu lập tức phát cảnh báo “consumer idle” theo cùng ngưỡng sử dụng cho hệ thống đã hoạt động ổn định, đội vận hành dễ nhận nhiều cảnh báo không cần thiết.

Thuộc tính **`idleBeforeDataMultiplier`** của Spring Kafka giúp giải quyết đúng tình huống đó. Nó là **hệ số nhân áp dụng cho `idleEventInterval` trong giai đoạn trước khi listener container nhận được dữ liệu đầu tiên**. Sau khi đã nhận được dữ liệu, cơ chế phát idle event sử dụng ngưỡng idle thông thường. Đây là một chi tiết nhỏ nhưng rất quan trọng khi theo dõi Kafka consumer trong quá trình startup, scale-out và triển khai topic mới.

Bài học này đi sâu vào bản chất của thuộc tính, cách cấu hình, quan hệ với `ListenerContainerIdleEvent`, cách phân biệt consumer idle và consumer không phản hồi, tác động của concurrency và pause, cách viết cảnh báo và cách kiểm thử để hạn chế false positive mà không bỏ sót sự cố thật.

## 1. Tại sao có idleBeforeDataMultiplier?

Giả sử một service xử lý đơn hàng có cấu hình phát idle event sau **10 giây không nhận record**. Trong môi trường production đã hoạt động, việc không có dữ liệu trong 10 giây có thể đáng quan tâm nếu hệ thống thường xuyên nhận hàng trăm events mỗi giây.

Nhưng khi khởi động một consumer mới, những điều sau có thể xảy ra trước khi message đầu tiên đến:

- Producer đang triển khai hoặc chưa phát sự kiện.
- Topic không có dữ liệu tồn đọng.
- Consumer group vừa được tạo và bắt đầu từ vị trí cuối log.
- Kafka consumer đang hoàn tất subscription và partition assignment.
- Business flow chỉ phát event khi có người dùng thực hiện thao tác.
- Một instance scale-out được assign những partition chưa có traffic.

Trong những trường hợp đó, coi khoảng thời gian không có message **ngay từ thời điểm khởi động** là lỗi tương tự như tình huống “đang chạy đều rồi bất ngờ im lặng” là chưa hợp lý.

`idleBeforeDataMultiplier` cho phép tạo **khoảng chờ ban đầu dài hơn** mà không phải nới lỏng ngưỡng idle của toàn bộ vòng đời consumer.

~~~text
Startup consumer
       |
       | Chưa từng nhận record
       | Ngưỡng idle ban đầu:
       | idleEventInterval × idleBeforeDataMultiplier
       v
Record đầu tiên được nhận
       |
       | Từ đây sử dụng
       | idleEventInterval thông thường
       v
Consumer tiếp tục xử lý
~~~

**Điểm quan trọng:** Hệ số này không làm consumer chờ trước khi poll và không trì hoãn record đầu tiên. Nó điều chỉnh **thời điểm xuất hiện idle event**, tức tín hiệu quan sát khi chưa nhận dữ liệu.

## 2. Quan hệ giữa idleEventInterval và idleBeforeDataMultiplier

Hai thuộc tính có nhiệm vụ khác nhau.

| Thuộc tính | Vai trò | Ví dụ |
|---|---|---|
| `idleEventInterval` | Khoảng thời gian không nhận record dùng để phát idle event | 10.000 ms |
| `idleBeforeDataMultiplier` | Hệ số nhân ngưỡng idle trong giai đoạn chưa từng nhận record | 3.0 |
| `idlePartitionEventInterval` | Tùy phiên bản, phát hiện idle theo từng partition | Ngưỡng riêng cho partition, không đồng nhất với idle toàn container |

Một cách hiểu thực tế:

~~~text
Ngưỡng trước khi nhận data đầu tiên
  ≈ idleEventInterval × idleBeforeDataMultiplier

Ngưỡng sau khi đã nhận data
  ≈ idleEventInterval
~~~

Dấu “≈” nhắc rằng idle event là tín hiệu dựa trên hoạt động của consumer/container và chu kỳ poll, không phải bộ hẹn giờ thời gian thực cam kết phát chính xác đến từng mili giây.

### 2.1. Ví dụ số liệu

Giả sử:

- `idleEventInterval = 10_000L`, tương ứng 10 giây.
- `idleBeforeDataMultiplier = 3.0`.

Khi container mới chạy nhưng **chưa từng nhận record**, ngưỡng trước khi phát idle event tương ứng khoảng 30 giây. Sau khi một record đã đến, những khoảng không nhận record được đánh giá theo ngưỡng thông thường là 10 giây.

| Giai đoạn | Đã từng nhận record? | Ngưỡng idle tương ứng |
|---|---|---|
| Sau khởi động, topic chưa có message | Chưa | Khoảng 30 giây |
| Consumer đã nhận record đầu tiên | Có | Reset theo hoạt động nhận dữ liệu |
| Sau đó topic im lặng | Có | Khoảng 10 giây |
| Một đợt idle khác về sau | Có | Khoảng 10 giây |

Đây không phải cơ chế nhân mọi khoảng idle lên ba lần; hệ số chỉ có ý nghĩa ở giai đoạn **before data**.

### 2.2. Timeline

~~~text
Thời gian:       0s     10s     20s     30s     40s     50s
                |-------|-------|-------|-------|-------|

Consumer start  ^
Record đầu tiên chưa đến
Ngưỡng trước data = 30s
                                       |
                                       v
                             Idle event có thể xuất hiện

Sau đó record đến ở khoảng 42s
                                                  ^
                                                  |
                                        Từ đây idle interval = 10s
~~~

Nếu record đầu tiên đến trước ngưỡng ban đầu, tình huống idle trước data có thể không phát sinh; việc theo dõi idle về sau dùng ngưỡng thông thường.

### 2.3. Multiplier có thể nhỏ hơn 1 không?

Mục đích sử dụng chủ đạo là **giãn thời gian trước idle event đầu tiên**, thường chọn hệ số lớn hơn 1. Không nên tùy ý đặt 0, số âm hoặc những giá trị cực đoan. Khả năng validation, phạm vi giá trị hợp lệ và giá trị mặc định cần được đối chiếu với phiên bản Spring Kafka đang chạy.

Một số phiên bản Spring Kafka có giá trị mặc định của hệ số này là **5.0**. Tuy nhiên, khi thiết kế alert nghiêm ngặt, hãy xem default trong `ContainerProperties` của đúng dependency thay vì mặc nhiên áp một con số từ tài liệu phiên bản khác.

## 3. Phải bật idleEventInterval trước

`idleBeforeDataMultiplier` **không tự bật cơ chế phát idle event**. Nó chỉ điều chỉnh ngưỡng khi tính năng idle event đã được cấu hình.

Trong Spring Kafka, `idleEventInterval` thường là một khoảng thời gian không được bật theo mặc định; muốn nhận `ListenerContainerIdleEvent` cần cấu hình ngưỡng phù hợp.

Ví dụ:

~~~java
factory.getContainerProperties()
        .setIdleEventInterval(10_000L);

factory.getContainerProperties()
        .setIdleBeforeDataMultiplier(3.0);
~~~

Nếu chỉ cấu hình:

~~~java
factory.getContainerProperties()
        .setIdleBeforeDataMultiplier(3.0);
~~~

nhưng không cấu hình cơ chế idle event, ứng dụng không nên kỳ vọng tự xuất hiện các event idle chỉ vì multiplier đã có giá trị.

### 3.1. Tác động đến consumer

`idleBeforeDataMultiplier` không trực tiếp thay đổi:

- Kafka topic subscription.
- Partition assignment.
- Poll timeout.
- Group heartbeat.
- Offset commit.
- Retry/backoff của `DefaultErrorHandler`.
- Cách `@KafkaListener` chuyển đổi payload.
- Kích thước batch hoặc số record mỗi lần poll.

Nó thuộc **container observability/lifecycle event timing**, không phải cơ chế rate limiting hoặc cấu hình broker.

## 4. Cấu hình Java trên ConcurrentKafkaListenerContainerFactory

Giả sử ứng dụng nhận sự kiện đơn hàng qua `orders.events` và cần cảnh báo khi một consumer đang chạy bỗng không có dữ liệu.

~~~java
@Configuration
public class OrdersKafkaConfig {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
    ordersListenerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<
                        String, OrderEvent>();

        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);

        factory.getContainerProperties()
                .setIdleEventInterval(10_000L);

        factory.getContainerProperties()
                .setIdleBeforeDataMultiplier(3.0);

        return factory;
    }
}
~~~

Listener:

~~~java
@Component
public class OrdersListener {

    private final OrderService orderService;

    public OrdersListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
            id = "ordersListener",
            topics = "orders.events",
            groupId = "orders-processing",
            containerFactory = "ordersListenerFactory")
    public void consume(OrderEvent event) {
        orderService.processIdempotently(event);
    }
}
~~~

Ví dụ giả định `OrderEvent`, `OrderService` và `ConsumerFactory` được khai báo phù hợp trong ứng dụng. API cụ thể của `ContainerProperties` cần tương thích với phiên bản Spring Kafka.

### 4.1. Listener factory phải là factory thực sự được sử dụng

Một ứng dụng có thể có nhiều `ConcurrentKafkaListenerContainerFactory`. Nếu bạn bật multiplier trên factory A nhưng `@KafkaListener` lại trỏ tới factory B, thay đổi sẽ không ảnh hưởng listener mong muốn.

Khi điều tra không thấy idle event hoặc event đến quá sớm, hãy xác nhận:

1. ID listener.
2. Giá trị `containerFactory` trong annotation.
3. `ContainerProperties` của container đang chạy.
4. Cấu hình `idleEventInterval` và multiplier thực tế.
5. Startup lifecycle của container.

Không kết luận tính năng lỗi chỉ từ việc một bean configuration đã được tạo.

### 4.2. Cấu hình khi tạo container trực tiếp

Nếu không dùng `@KafkaListener` mà tạo Kafka listener container bằng Java:

~~~java
ContainerProperties properties =
        new ContainerProperties("orders.events");

properties.setGroupId("orders-processing");
properties.setIdleEventInterval(10_000L);
properties.setIdleBeforeDataMultiplier(3.0);

var container =
        new KafkaMessageListenerContainer<>(
                consumerFactory, properties);
~~~

Đoạn code chỉ minh họa nơi đặt thuộc tính; cần gắn listener, cấu hình handler và start container đúng lifecycle trước khi dùng trong hệ thống thực.

## 5. Nghe ListenerContainerIdleEvent

Sau khi cấu hình `idleEventInterval`, Spring Kafka có thể publish `ListenerContainerIdleEvent` khi listener không nhận record trong khoảng thời gian phù hợp.

Ví dụ application event listener:

~~~java
@Component
public class KafkaIdleEvents {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaIdleEvents.class);

    @EventListener
    public void onIdle(ListenerContainerIdleEvent event) {
        log.info(
                "Kafka listener idle: listener={}, idleTimeMs={}, " +
                "partitions={}",
                event.getListenerId(),
                event.getIdleTime(),
                event.getTopicPartitions());
    }
}
~~~

`getIdleTime()` giúp quan sát khoảng thời gian container đánh giá là idle khi event phát ra. `getListenerId()` và `getTopicPartitions()` cung cấp ngữ cảnh container/partition theo API của phiên bản tương ứng.

**Không đọc event.getIdleTime() như số mili giây chính xác kể từ JVM startup** trong mọi trường hợp. Nó diễn đạt idle duration theo cách container theo dõi việc nhận record; các yếu tố poll, rebalance, pause và thời điểm nhận record ảnh hưởng kết quả.

### 5.1. Idle event không có nghĩa consumer chết

Một Kafka consumer có thể liên tục gọi `poll()`, giữ group membership, nhận metadata và heartbeats hợp lệ trong khi **không có bất kỳ record nào để xử lý**. Trong trường hợp đó, listener vẫn idle mà consumer hoàn toàn khỏe.

Vì vậy:

- Idle event là một **tín hiệu thiếu dữ liệu**.
- Consumer không responsive là một **vấn đề liveness/poll**.
- Container stop là một **lifecycle state**.
- Broker unavailable là một **vấn đề kết nối/hạ tầng**.

Chúng có thể liên quan nhưng không đồng nhất.

### 5.2. Không biến mỗi idle event thành một page

Nếu topic bản chất thưa dữ liệu, container có thể phát nhiều idle events bình thường. Một callback gửi email/pager cho từng event dễ gây alert fatigue.

Hãy dùng event để cập nhật metric hoặc trạng thái, sau đó đưa ra alert theo chính sách: độ trễ dự kiến của dữ liệu, upstream activity, consumer lag, partition assignment và tính quan trọng nghiệp vụ.

## 6. ListenerContainerNoLongerIdleEvent

Khi một container từng được xác định idle rồi nhận lại record, Spring Kafka có thể publish `ListenerContainerNoLongerIdleEvent`. Event này hữu ích để đóng một incident “không có dữ liệu” hoặc đo khoảng thời gian pipeline không nhận record.

~~~java
@Component
public class KafkaIdleLifecycleEvents {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaIdleLifecycleEvents.class);

    @EventListener
    public void onIdle(ListenerContainerIdleEvent event) {
        log.warn(
                "Idle: listener={}, idleMs={}",
                event.getListenerId(),
                event.getIdleTime());
    }

    @EventListener
    public void onNoLongerIdle(
            ListenerContainerNoLongerIdleEvent event) {
        log.info(
                "Data resumed after idle: listener={}",
                event.getListenerId());
    }
}
~~~

Tùy phiên bản và cách container publish events, những trường metadata cụ thể có thể khác nhau. Ví dụ dùng những phương thức phổ biến của event API; cần bổ sung imports tương ứng trong mã nguồn thật.

### 6.1. Cách dùng cho incident lifecycle

~~~text
Container nhận dữ liệu đều
          |
          v
Không nhận record đủ ngưỡng
          |
          v
ListenerContainerIdleEvent
          |
          v
Incident mở ở mức warning
          |
          v
Record mới được nhận
          |
          v
ListenerContainerNoLongerIdleEvent
          |
          v
Incident được đánh giá kết thúc
~~~

Nếu trước đó container chưa từng phát idle event, không nên giả định luôn có “no longer idle” event cho record đầu tiên. Logic theo dõi incident cần xử lý trường hợp chưa có incident mở.

## 7. Phân biệt ba giai đoạn quan trọng

Để hiểu multiplier, hãy chia vòng đời của consumer thành những pha:

### 7.1. Pha A — container vừa khởi động, chưa từng nhận record

Đây là pha mà `idleBeforeDataMultiplier` hướng tới. Ngưỡng idle được giãn so với `idleEventInterval` để giảm false positive lúc startup.

### 7.2. Pha B — container nhận record đầu tiên

Khi record xuất hiện, consumer chuyển khỏi tình huống “before data” và có lịch sử nhận dữ liệu. Các quyết định idle sau đó dùng khoảng bình thường của `idleEventInterval`.

### 7.3. Pha C — đã chạy có dữ liệu nhưng về sau im lặng

Đây là tình huống vận hành khác pha A. Nếu hệ thống có traffic đều nhưng bất ngờ không nhận record, phát hiện sớm bằng idle interval thông thường có giá trị chẩn đoán cao.

| Giai đoạn | Hệ số có ý nghĩa? | Tín hiệu vận hành |
|---|---|---|
| Mới start, chưa có record | Có | Có thể là startup bình thường hoặc thiếu upstream |
| Đã nhận data đầu tiên | Chuyển về ngưỡng idle thông thường | Xác nhận dữ liệu đã bắt đầu chảy |
| Im lặng sau một thời gian chạy | Không phải lý do giãn startup nữa | Kiểm tra producer/upstream, lag, assignment và errors |

Nếu bạn đặt multiplier rất lớn, có thể làm chậm phát hiện sự cố **ngay từ khi service triển khai**, nhưng không nên kỳ vọng nó tiếp tục trì hoãn mọi cảnh báo sau khi hệ thống đã nhận record.

## 8. idleBeforeDataMultiplier khác idleBetweenPolls

Hai tên gần nhau nhưng ngữ nghĩa khác biệt:

| Thuộc tính | Tác động |
|---|---|
| `idleBeforeDataMultiplier` | Hệ số nhân cho idle event threshold trước dữ liệu đầu tiên |
| `idleEventInterval` | Khoảng không nhận record để publish idle event |
| `idleBetweenPolls` | Cho container nghỉ một khoảng giữa các lần poll theo cấu hình, ảnh hưởng nhịp poll |
| `pollTimeout` | Thời gian một lời gọi poll có thể chờ |

`idleBeforeDataMultiplier` không làm `KafkaConsumer.poll()` chờ lâu gấp N lần và không phải cơ chế giảm tốc độ đọc. Nếu cần backpressure, hãy đánh giá pause/resume, concurrency, bounded queue hoặc rate limiting tùy bài toán.

### 8.1. Ví dụ nhầm lẫn

Nếu mục tiêu là “đọc Kafka ít hơn để không quá tải database”, đặt:

~~~java
properties.setIdleBeforeDataMultiplier(100.0);
~~~

sẽ **không** giải quyết vấn đề throughput. Nó chỉ làm thay đổi việc quan sát khoảng idle trước khi có data, trong khi lúc topic có record, consumer vẫn xử lý theo cấu hình hiện hành.

Nếu mục tiêu là “đừng báo idle trong phút đầu deployment”, multiplier có thể phù hợp.

## 9. idleBeforeDataMultiplier và NonResponsiveConsumerEvent

Spring Kafka còn cung cấp `NonResponsiveConsumerEvent` cho các tình huống consumer **không hoàn tất poll hoặc không poll theo ngưỡng giám sát**.

Hai sự kiện:

| Đặc điểm | `ListenerContainerIdleEvent` | `NonResponsiveConsumerEvent` |
|---|---|---|
| Câu hỏi | Có record được nhận gần đây không? | Consumer có đang poll/đáp ứng tiến độ poll không? |
| Consumer có thể khỏe? | Có, topic trống vẫn idle | Cần điều tra vì poll có thể đang bị block |
| Liên quan `idleBeforeDataMultiplier`? | Có, trước dữ liệu đầu tiên | Không phải mục đích của multiplier |
| Điểm điều tra | Producer, subscription, assignment, traffic | Thread dump, poll blocking, deadlock, network/lifecycle |
| Có record cụ thể gây lỗi? | Không nhất thiết | Không nhất thiết |

Một topic hoàn toàn trống có thể làm listener idle dù KafkaConsumer vẫn poll đều. Ngược lại, consumer bị kẹt trong một lời gọi poll hoặc một phần xử lý không quay lại poll có thể cần điều tra non-responsive ngay cả khi vừa nhận record.

### 9.1. Không dùng multiplier để chữa non-responsive

Nếu application đang bị poll stuck, tăng `idleBeforeDataMultiplier` có thể làm idle alerts xuất hiện muộn hơn, nhưng **không giải quyết nguyên nhân consumer không poll**.

Phải kiểm tra non-responsive monitor, listener processing duration, `max.poll.interval.ms`, CPU/GC và thread dump.

## 10. Idle và dữ liệu đến ở topic như thế nào?

Một listener có thể không nhận record vì nhiều lý do:

1. Producer thực sự chưa phát dữ liệu.
2. Consumer group đang ở cuối log và chưa có record mới.
3. Listener subscribe sai topic hoặc pattern.
4. Topic có record nhưng chúng thuộc partition chưa được assign cho consumer đó.
5. Consumer container đang paused.
6. Consumer group membership đang thay đổi.
7. Deserializer/converter gặp lỗi trước khi listener nhận object.
8. Consumer có lỗi authorization/network.
9. Một record đang được retry làm chậm các record tiếp theo.

`idleBeforeDataMultiplier` không phân loại nguyên nhân. Nó chỉ điều chỉnh ngưỡng phát event theo trạng thái “chưa từng nhận data”. Khi cần xác định lỗi, phải kết hợp logs, assignments, consumer lag, producer throughput và error events.

### 10.1. Topic có traffic không có nghĩa mọi listener instance đều nhận record

Trong consumer group, partition được phân phối cho các consumers. Nếu tổng consumer nhiều hơn partitions, một số consumer có thể không nhận assignment hoặc không có data trên partition được assign.

Do đó, “một pod chưa nhận message trong 30 giây” không nhất thiết là bất thường ngay cả khi topic toàn cục có traffic.

## 11. Concurrent container và phạm vi của multiplier

Với `ConcurrentMessageListenerContainer`, một listener ID có thể tạo nhiều consumer con theo `concurrency`.

~~~text
@KafkaListener(id="ordersListener")
                 |
                 v
ConcurrentMessageListenerContainer
      |              |              |
      v              v              v
  consumer-0      consumer-1      consumer-2
  partition 0     partition 1     partition 2
      |              |              |
  Có dữ liệu       Chưa có        Có dữ liệu
~~~

Khi quan sát idle events:

- Một consumer con có thể chưa nhận record nào dù các consumer con khác đã nhận.
- Thời điểm start/assignment của mỗi consumer con có thể khác nhau.
- Không mặc định một event của một child tương đương toàn bộ group/topic không hoạt động.
- Cần quan sát listener/container ID và partitions đi kèm event.

### 11.1. Cách tránh báo động sai khi concurrency lớn

Ví dụ topic có 6 partitions, mỗi pod có concurrency 3, tổng có 2 pods. Nếu chỉ một partition thưa dữ liệu, consumer quản lý partition đó có thể idle lâu.

Một alert toàn dịch vụ “pipeline down” chỉ dựa vào idle event từ một consumer sẽ không chính xác. Thay vào đó:

1. Xác định partition assignment.
2. So sánh input traffic theo partition.
3. Kiểm tra partition-specific lag.
4. Phân biệt consumer không nhận record do topic trống hay do bị pause/stuck.
5. Chỉ tăng mức độ nghiêm trọng nếu ảnh hưởng đến SLO nghiệp vụ.

### 11.2. Một multiplier không thay thế ngưỡng theo partition

Nếu mục tiêu là phát hiện “partition 2 không nhận record trong khi partition 1 vẫn hoạt động”, hãy xem cơ chế idle theo partition (`idlePartitionEventInterval` và các event tương ứng trong phiên bản hỗ trợ).

`idleBeforeDataMultiplier` điều chỉnh **ngưỡng ban đầu của idle event container**, không tự cung cấp phân tích traffic bất thường trên từng partition.

## 12. Khi nào nên đặt multiplier lớn?

Một multiplier lớn có thể hữu ích khi:

- Topic mới, producer triển khai sau consumer.
- Môi trường test/staging có ít traffic.
- Pipeline chỉ chạy khi có event theo lịch không liên tục.
- Startup nhiều service theo thứ tự, cần grace period.
- Consumer group scale-out và một số partition chưa phát data.
- Trong đợt deploy, cần tránh page vì “không nhận record trong vài giây đầu”.

Nhưng multiplier quá lớn cũng có nhược điểm:

- Phát hiện một consumer sai subscription từ đầu sẽ muộn hơn.
- Một producer đáng lẽ phải phát event ngay sau start nhưng bị lỗi có thể không bị cảnh báo sớm.
- Đội vận hành có thể hiểu lầm thời gian im lặng kéo dài là bình thường.
- Khi thời gian chờ ban đầu vượt SLO, tín hiệu từ event có thể đến quá muộn.

Hãy chọn multiplier theo **thời gian khởi động thực tế, nhịp dữ liệu kỳ vọng và SLO**, không dựa vào một giá trị cao chỉ để giảm số lượng cảnh báo.

## 13. Công thức chọn multiplier theo ngân sách thời gian

Giả sử:

- Sau startup, bạn chấp nhận tới 90 giây chưa có record đầu tiên.
- Sau khi pipeline đã hoạt động, muốn phát hiện khoảng im lặng khoảng 15 giây.

Có thể chọn:

~~~text
idleEventInterval = 15 giây
idleBeforeDataMultiplier = 90 / 15 = 6.0

Ngưỡng ban đầu ≈ 90 giây
Ngưỡng thông thường ≈ 15 giây
~~~

Một số ví dụ minh họa:

| Idle interval | Multiplier | Ngưỡng trước data tương ứng |
|---|---:|---:|
| 5 giây | 2.0 | 10 giây |
| 10 giây | 3.0 | 30 giây |
| 15 giây | 6.0 | 90 giây |
| 60 giây | 2.0 | 120 giây |

Những giá trị này chỉ minh họa phép nhân, không phải ngưỡng được khuyến nghị chung. Thời điểm event thực tế có thể muộn hơn do poll/lifecycle.

### 13.1. Chọn theo loại topic

| Kiểu workload | Cách suy nghĩ về threshold |
|---|---|
| Event streaming liên tục | Idle thông thường ngắn; startup grace vừa đủ |
| Job định kỳ mỗi 5 phút | Idle event không nên mặc định coi im lặng 30 giây là incident |
| Topic giao dịch chỉ phát theo hành vi người dùng | Có thể chấp nhận thời gian idle dài, dùng upstream business SLO bổ sung |
| DLT/quarantine | Idle thường là trạng thái mong muốn; không page vì thiếu dữ liệu |
| Topic dùng trong integration tests | Grace period giúp tránh test báo idle trước khi producer setup xong |

Đối với DLT, “không có record mới” thường là dấu hiệu tốt, nên chính sách alert có thể tập trung vào việc **có** record vào DLT thay vì việc idle.

## 14. Khởi động service không đồng nghĩa bắt đầu nhận data

Một listener container có thể ở lifecycle `running` nhưng:

- Chưa hoàn tất partition assignment.
- Chưa có traffic mới.
- Được assign những partition trống.
- Bị pause theo chính sách.
- Đang bị lỗi consumer runtime.

Vì vậy, “sau startup chưa thấy record” không phải bằng chứng `@KafkaListener` lỗi.

Khi debug:

1. Kiểm tra container có start và running không.
2. Kiểm tra consumer group subscription và assignment.
3. Kiểm tra Kafka topic và input producer.
4. Kiểm tra committed offsets và end offsets.
5. Kiểm tra partition-level traffic.
6. Kiểm tra consumer có paused hay không.
7. Kiểm tra exception trước listener như deserialization/authorization.

Multiplier chỉ giúp điều chỉnh **khi nào** bạn nhận một thông báo idle, không trả lời **vì sao** dữ liệu chưa tới.

## 15. Ảnh hưởng của consumer pause

Spring Kafka hỗ trợ `container.pause()` và `container.resume()` để ngừng nhận thêm record khi downstream quá tải. Khi container paused, consumer có thể vẫn poll để giữ group membership, nhưng không giao thêm record mới cho listener.

Nếu listener không nhận record trong thời gian pause, tín hiệu idle có thể xuất hiện tùy cách tính và trạng thái của container ở phiên bản đang dùng. Một số event API cung cấp thông tin `isPaused()` để biết trạng thái pause liên quan.

### 15.1. Đừng page vì planned pause

Một runbook hợp lý:

- Nếu container đang pause theo lịch bảo trì, ghi nhận idle là trạng thái dự kiến.
- Nếu container pause do queue quá tải, alert theo **backpressure duration**, queue depth hoặc downstream failure, không chỉ idle duration.
- Nếu container không paused nhưng topic có input traffic và consumer không nhận record, điều tra sâu hơn.

`idleBeforeDataMultiplier` không phải tính năng “bỏ qua idle khi paused”. Muốn tránh alert sai, phải kết hợp container pause state và pause reason từ hệ thống quản trị.

### 15.2. Resume không reset dữ liệu nghiệp vụ

`resume()` không tự commit offset, không seek về đầu topic và không bắt record cũ biến mất. Sau resume, listener tiếp tục delivery theo trạng thái consumer/offset và error handler.

Không dùng idle event làm trigger tự động resume mọi container; nếu chúng được pause do downstream đang yếu, tự resume có thể tạo retry storm.

## 16. Batch listener và record listener

Spring Kafka hỗ trợ record listener và batch listener. Trong cả hai trường hợp, idle event nói đến **khoảng không nhận dữ liệu**, không phải “tổng số object nghiệp vụ đã xử lý thành công”.

### 16.1. Record listener

~~~java
@KafkaListener(
        id = "ordersRecordListener",
        topics = "orders.events")
public void consume(OrderEvent event) {
    orderService.process(event);
}
~~~

Với record listener, một poll có thể mang nhiều records và adapter gọi method nhiều lần. Idle event không nhất thiết có quan hệ 1:1 với từng lần method invocation.

### 16.2. Batch listener

~~~java
@KafkaListener(
        id = "ordersBatchListener",
        topics = "orders.events",
        containerFactory = "ordersBatchFactory")
public void consumeBatch(List<OrderEvent> events) {
    orderService.processBatch(events);
}
~~~

Với batch listener, một lần gọi method có thể chứa nhiều records. Không suy ra “một method call” tương đương “một record” khi quan sát idle. Nếu batch processing rất chậm, consumer có thể gặp các vấn đề poll interval dù vừa nhận được dữ liệu trước đó.

### 16.3. Lỗi processing khác thiếu data

Một listener nhận record nhưng ném exception liên tục không đồng nghĩa container idle theo ngữ nghĩa “không nhận record”. Cần metrics exception, retries, DLT và consumer lag song song với idle events.

## 17. Consumer không phản hồi không thể sửa bằng multiplier

Một consumer không poll được trong thời gian dài có thể bị:

- Listener code block vô hạn.
- Thread deadlock.
- Database query treo không timeout.
- HTTP client chờ lâu.
- CPU/GC pressure.
- Lỗi network hoặc Kafka client.
- Error handler/backoff cấu hình không phù hợp.

Trong trường hợp này:

1. Kiểm tra `NonResponsiveConsumerEvent` hoặc các tín hiệu poll monitoring.
2. Lấy thread dump.
3. Xác định thread consumer đang làm gì.
4. Kiểm tra `max.poll.interval.ms` và group rebalances.
5. Kiểm tra I/O timeouts và circuit breaker.
6. Phục hồi dependency hoặc sửa code.

Tăng `idleBeforeDataMultiplier` chỉ thay đổi thời điểm cảnh báo idle trước record đầu tiên; không làm consumer tự poll hoặc thoát deadlock.

## 18. Application events có thể chạy trên thread của container

Spring application events thường được phát đồng bộ nếu không cấu hình asynchronous multicaster. Do đó, một `@EventListener` nhận idle event có thể chạy trên thread mà container sử dụng trong quá trình publish event.

Event listener nên:

- Ghi log ngắn.
- Cập nhật counter/gauge nhẹ.
- Lưu trạng thái thread-safe.
- Đẩy notification sang pipeline bất đồng bộ có kiểm soát.

Không nên:

- Sleep nhiều giây.
- Gọi database hoặc HTTP không timeout.
- Gọi trực tiếp `KafkaConsumer.seek(...)` hoặc `pause(...)` từ event callback mà không tuân thủ consumer thread ownership.
- Trigger restart/stop container liên tục.
- Ghi toàn bộ payload hoặc Kafka headers nhạy cảm.

### 18.1. Ví dụ callback nhẹ

~~~java
@Component
public class OrdersIdleMonitor {

    private final AtomicLong lastIdleEventMs =
            new AtomicLong(-1L);

    @EventListener
    public void onIdle(ListenerContainerIdleEvent event) {
        if (!event.getListenerId().contains("ordersListener")) {
            return;
        }

        lastIdleEventMs.set(System.currentTimeMillis());
    }

    public long lastIdleEventMs() {
        return lastIdleEventMs.get();
    }
}
~~~

Đây là ví dụ về ý tưởng giám sát local state, không phải health check hoàn chỉnh. Tùy cách đặt listener ID và concurrency, `getListenerId()` có thể có suffix hoặc cách đặt tên cụ thể, nên tránh dựa vào so khớp chuỗi mơ hồ để xác định ownership trong production.

## 19. Alerting: idle event là một tín hiệu, không phải kết luận

Một chính sách cảnh báo nên kết hợp ít nhất:

1. Topic có kỳ vọng về traffic hay không.
2. Upstream producer có đang phát record không.
3. Consumer group có assignment phù hợp không.
4. Consumer lag và tuổi record chưa xử lý.
5. Container có running/paused không.
6. Consumer có poll và heartbeat bình thường không.
7. Đây là giai đoạn startup hay steady state.
8. Có maintenance window hoặc intentional throttle không.

Ví dụ:

| Tình huống | Idle event | Alert phù hợp |
|---|---|---|
| Topic mới và producer chưa chạy theo lịch | Có thể có | Thông báo mức thấp hoặc không alert |
| Topic giao dịch đang có traffic cao, consumer không nhận record | Có thể có | Điều tra ngay, nhất là nếu lag tăng |
| Consumer đang paused vì bảo trì | Có thể có | Theo dõi maintenance duration |
| Consumer chưa có partition assignment | Có thể có | Điều tra group/assignment trước khi báo data loss |
| DLT không có message | Có thể có | Thường là bình thường |
| Consumer không poll | Không nhất thiết cần idle event | Alert qua non-responsive/poll metrics |

### 19.1. Tránh đếm lặp nhiều idle events

Nếu một container tiếp tục idle, nó có thể tiếp tục phát các idle events theo cấu hình. Một incident management system không nên tạo một ticket mới cho mọi event.

Hãy dùng identity ổn định, ví dụ application + listener/container ID + instance, và có:

- Trạng thái open/closed của incident.
- Thời điểm idle bắt đầu.
- Mức độ nghiêm trọng theo SLO.
- Cooldown hoặc deduplication window.
- Cơ chế đóng incident khi data trở lại.

## 20. Metrics để quan sát idleBeforeDataMultiplier

Không phải mọi metric dưới đây đều được Spring Kafka xuất ra mặc định; nhiều chỉ số cần instrumentation riêng.

| Metric | Công dụng |
|---|---|
| Idle event count/rate | Phát hiện số lần listener rơi vào idle |
| Time to first record | Đo khoảng từ lúc container sẵn sàng đến record đầu tiên |
| Idle duration distribution | Hiểu thời gian im lặng bình thường của workload |
| Consumer records consumed rate | Xác nhận có record đang được nhận |
| Consumer lag by partition | Xem backlog tăng hay giảm |
| Last successful processing timestamp | Đo tiến độ nghiệp vụ |
| Producer send rate | Có input upstream hay không |
| Container running/paused state | Xác định lifecycle |
| Poll duration/non-responsive count | Phát hiện consumer bị kẹt |
| Partition assignment count | Phân biệt thiếu traffic và thiếu assignment |

### 20.1. Time to first record và idle duration không giống nhau

`idleBeforeDataMultiplier` tác động đến **ngưỡng phát idle event khi chưa có record**. Nhưng việc một consumer nhận record đầu tiên sau 50 giây là một phép đo riêng. Để hiểu startup, cần instrument first-record timestamp hoặc event tương ứng; không suy ra chính xác thời điểm record đầu tiên chỉ bằng số idle events.

### 20.2. Metric tags

Tag nên hữu hạn:

- Application/service.
- Environment.
- Listener ID.
- Topic (theo tập được kiểm soát).
- Instance nếu số lượng bounded.

Tránh dùng Kafka offset, event ID, record key, exception message hoặc raw partition assignment list dài làm metric tags gây cardinality cao. Chi tiết từng record nên đưa vào structured logs/traces có kiểm soát.

## 21. Ví dụ ghi nhận idle qua Micrometer

~~~java
@Component
public class KafkaIdleMetrics {

    private final Counter idleEvents;
    private final Counter noLongerIdleEvents;

    public KafkaIdleMetrics(MeterRegistry meterRegistry) {
        idleEvents = Counter.builder(
                "app.kafka.listener.idle.events")
                .description("Listener idle application events")
                .register(meterRegistry);

        noLongerIdleEvents = Counter.builder(
                "app.kafka.listener.no_longer_idle.events")
                .description("Listener resumed receiving records")
                .register(meterRegistry);
    }

    @EventListener
    public void onIdle(ListenerContainerIdleEvent event) {
        idleEvents.increment();
    }

    @EventListener
    public void onDataBack(
            ListenerContainerNoLongerIdleEvent event) {
        noLongerIdleEvents.increment();
    }
}
~~~

Đây là ví dụ instrumentation. `MeterRegistry` và `Counter` thuộc Micrometer; dự án cần dependency và imports tương ứng. Nếu có nhiều listeners, nên chọn một tập tag ổn định để phân nhóm, thay vì phát sinh meter mới cho từng message.

### 21.1. Cân nhắc cardinality với concurrent containers

Trong hệ thống có nhiều pods và consumer children, số metric series có thể tăng nếu tag gồm client ID động, pod UID và partition list. Hãy đặt taxonomy ổn định và chỉ thêm độ chi tiết khi cần cho debug.

## 22. Kiểm thử multiplier bằng integration test

Mục tiêu kiểm thử là chứng minh **ngưỡng ban đầu** dài hơn ngưỡng thông thường khi chưa có data, và sau khi data đến, idle event dùng ngưỡng bình thường.

Có thể dùng embedded Kafka broker hoặc Testcontainers. Bởi vì event publishing gắn với poll cycle, hãy dùng test timeout có độ dư thay vì assert chính xác từng mili giây.

### 22.1. Kịch bản chưa có record

1. Tạo topic test không có record tồn đọng cho group mới.
2. Cấu hình `idleEventInterval = 1_000L`.
3. Cấu hình `idleBeforeDataMultiplier = 3.0`.
4. Khởi động listener container.
5. Thu thập `ListenerContainerIdleEvent` bằng một event collector thread-safe.
6. Xác nhận không kỳ vọng event ở ngưỡng thông thường 1 giây đầu theo policy đã cấu hình.
7. Xác nhận idle event xuất hiện sau khoảng chờ đầu phù hợp, có dung sai polling/scheduling.

Đừng dùng giá trị thời gian quá nhỏ so với startup và `pollTimeout`, vì test dễ flaky.

### 22.2. Kịch bản record đầu tiên đến sớm

1. Start container với topic mới.
2. Gửi record trước khi vượt ngưỡng đầu.
3. Xác nhận listener nhận record.
4. Ngừng producer.
5. Quan sát idle event sau khoảng `idleEventInterval` thông thường.
6. Không chờ lại multiplier × interval như thể container chưa từng nhận data.

### 22.3. Kịch bản sau lần idle đầu

1. Để container không có record đủ lâu để idle event phát ra.
2. Gửi record.
3. Quan sát `ListenerContainerNoLongerIdleEvent` nếu được hỗ trợ và phù hợp lifecycle.
4. Ngừng gửi records.
5. Xác nhận cơ chế idle tiếp tục hoạt động với ngưỡng sau data.

### 22.4. Kịch bản concurrency

1. Tạo topic nhiều partitions.
2. Chạy listener với concurrency > 1.
3. Gửi data vào một partition nhưng không gửi vào partition khác.
4. Thu event cùng metadata listener ID/partitions.
5. Xác nhận dashboard không gộp sai idle của một child thành downtime toàn group.

### 22.5. Kịch bản paused container

1. Start container và xác nhận đã nhận data.
2. Pause container.
3. Quan sát event/state trong phiên bản Spring Kafka đang chạy.
4. Xác nhận alerts loại trừ intentional pause.
5. Resume và gửi record tiếp.
6. Xác nhận không mất record và offset xử lý đúng.

### 22.6. Kịch bản consumer non-responsive

Để chứng minh khác biệt, tạo một tình huống listener/poll bị chặn có kiểm soát trong integration test và quan sát monitor non-responsive. Không nên dùng idle event làm tín hiệu duy nhất để kết luận poll health.

## 23. Ví dụ event collector cho kiểm thử

Một collector tối giản:

~~~java
@Component
public class IdleEventCollector {

    private final BlockingQueue<ListenerContainerIdleEvent> events =
            new LinkedBlockingQueue<>();

    @EventListener
    public void onIdle(ListenerContainerIdleEvent event) {
        events.offer(event);
    }

    public ListenerContainerIdleEvent awaitIdle(
            long timeout, TimeUnit unit)
            throws InterruptedException {
        return events.poll(timeout, unit);
    }
}
~~~

Đây là hỗ trợ test đơn giản; trong bộ integration test thực tế cần:

- Cách lọc event theo listener/container test.
- Reset collector giữa các test.
- Giới hạn queue nếu test chạy lâu.
- Dùng cùng application context hoặc injected collector phù hợp.
- Tránh test phụ thuộc thứ tự event của nhiều consumers.

Khi kiểm tra thời gian, có thể ghi timestamp nhận event và đối chiếu tương đối với thời điểm container start. Không assert bằng một khoảng thời gian quá hẹp, vì thread scheduling và Kafka poll không phải đồng hồ thời gian thực.

## 24. Runbook: idle event đến quá sớm sau startup

1. Xác nhận listener ID và container factory đang chạy.
2. Đọc `idleEventInterval` thực tế.
3. Đọc `idleBeforeDataMultiplier` thực tế.
4. Kiểm tra listener đã từng nhận record trước thời điểm event chưa.
5. Kiểm tra có record tồn đọng được consume ngay sau start không.
6. Kiểm tra container được restart nhưng không khởi tạo consumer mới theo kỳ vọng hay không.
7. Kiểm tra thời gian start, first record và event timestamps.
8. Kiểm tra Spring Kafka version và default values.
9. Đối chiếu với poll timeout và concurrency.

Nếu listener đã nhận dù chỉ một record, giai đoạn “before data” có thể đã kết thúc; lúc đó việc phát idle event theo khoảng bình thường không phải lỗi của multiplier.

### 24.1. Đừng chỉ sửa bằng cách tăng multiplier

Nếu event quá sớm vì producer thực sự đang down, tăng multiplier chỉ che sự cố. Nếu startup grace thực sự không đủ, tăng multiplier có thể đúng. Phải phân biệt hai nguyên nhân bằng producer metrics và time-to-first-record.

## 25. Runbook: không thấy idle event dù topic trống

1. Xác nhận `idleEventInterval` đã được bật.
2. Xác nhận container đã start và đang running.
3. Xác nhận đúng listener factory.
4. Kiểm tra khoảng chờ ban đầu: interval × multiplier có thể lớn hơn dự tính.
5. Kiểm tra event listener bean có được Spring scan/đăng ký không.
6. Kiểm tra event filtering logic có loại bỏ event vì listener ID không khớp không.
7. Kiểm tra container đang pause, stop hoặc bị kẹt poll không.
8. Kiểm tra logs và application event multicaster.
9. Kiểm tra poll interval/timeout trước khi cho rằng event bị mất.

Nếu ngưỡng ban đầu là 5 phút, không thấy idle event sau 30 giây là behavior dự kiến. Nếu consumer không poll được, điều tra non-responsive thay vì chỉ chờ idle event.

## 26. Runbook: đã nhận data nhưng idle vẫn dùng ngưỡng dài

1. Xác nhận record thực sự đã được **consumer/container nhận**, không chỉ producer publish.
2. Kiểm tra record có đi tới group/partition của listener đang xét không.
3. Kiểm tra event đang phát từ child consumer khác chưa từng nhận record không.
4. Kiểm tra listener ID và instance trong event metadata.
5. Kiểm tra lần restart/rebalance gần nhất.
6. Kiểm tra có nhiều listener factories với multiplier khác nhau.
7. Kiểm tra event timestamps và poll scheduling.
8. Kiểm tra Spring Kafka version và semantics của property.

Đặc biệt với concurrent consumers, một child nhận data không nhất thiết có nghĩa mọi child khác đều đã nhận data. Không suy ra toàn container/group có cùng lịch sử message nếu implementation đang theo dõi từng consumer.

## 27. Runbook: idle alert nhưng consumer lag bằng 0

1. Kiểm tra producer có đang phát record không.
2. Kiểm tra topic thực sự có data mới trong thời gian alert.
3. Kiểm tra consumer group committed offsets và end offsets.
4. Kiểm tra assignment của instance phát event.
5. Xác nhận workload có bản chất thưa data không.
6. Kiểm tra planned maintenance hoặc intentional pause.
7. Nếu không có input và lag bằng 0, giảm mức độ alert theo business expectation.
8. Nếu upstream buộc phải phát định kỳ, cảnh báo upstream SLO thay vì quy ngay consumer lỗi.

Consumer idle khi không có record cần đọc có thể là trạng thái hoàn toàn tốt.

## 28. Runbook: idle alert và consumer lag tăng

1. Xác nhận lag tăng trên partition nào.
2. Kiểm tra consumer container có running không.
3. Kiểm tra partition assignment và group rebalance.
4. Kiểm tra consumer paused hoặc backpressure state.
5. Kiểm tra deserialization failures hoặc error handler đang xử lý poison pill.
6. Kiểm tra consumer poll responsiveness và thread dump.
7. Kiểm tra Kafka network/authentication/authorization errors.
8. Kiểm tra producer rate và consumer records consumed rate.
9. Sửa root cause, sau đó theo dõi lag và oldest record age giảm.

Nếu lag tăng trong khi không có record được nhận, đây có thể là sự cố nghiêm trọng; multiplier chỉ điều chỉnh tín hiệu khởi đầu, không phải giải pháp phục hồi.

## 29. Runbook: NonResponsiveConsumerEvent đồng thời với idle

1. Đừng kết luận cả hai sự kiện cùng một nghĩa.
2. Xác định consumer thread có gọi poll đều không.
3. Xem thread dump và GC pause.
4. Kiểm tra listener processing time và downstream timeouts.
5. Đối chiếu monitor interval, poll timeout và `max.poll.interval.ms`.
6. Kiểm tra group rebalances.
7. Ưu tiên xử lý sự cố poll responsiveness nếu consumer bị kẹt.
8. Sau phục hồi, tiếp tục đánh giá idle theo data traffic kỳ vọng.

Một consumer im lặng vì không có data là chuyện khác với consumer không thể tiến hành poll.

## 30. Những sai lầm thường gặp

**Nghĩ multiplier làm Kafka poll chậm lại.** Property chỉ điều chỉnh ngưỡng idle event trước data đầu tiên.

**Chỉ đặt multiplier, quên idleEventInterval.** Multiplier không tự bật event.

**Áp hệ số cho mọi khoảng idle.** Sau khi nhận data, cơ chế dùng ngưỡng idle thông thường.

**Cho rằng idle event là lỗi broker.** Topic trống hoặc consumer ở cuối log vẫn có thể idle hoàn toàn bình thường.

**Cho rằng không có idle event nghĩa consumer khỏe.** Consumer có thể stop, non-responsive hoặc event feature chưa bật.

**Bật alert cho mọi event ở DLT.** DLT im lặng thường là bình thường.

**Gộp idle của một consumer child thành downtime toàn consumer group.** Cần nhìn assignment và concurrency.

**Bỏ qua pause state.** Intentional pause có thể tạo khoảng không nhận data dài.

**Tăng multiplier thật lớn để hết alert.** Có thể che lỗi từ startup và làm chậm phát hiện.

**Dùng idle event làm trigger restart container vô điều kiện.** Restart có thể gây rebalance và không giải quyết upstream thiếu data.

**Xử lý HTTP/database nặng ngay trong @EventListener.** Có thể block event dispatch và ảnh hưởng container.

**Không kiểm thử bằng môi trường có poll scheduling thực.** Đọc cấu hình không chứng minh ngưỡng vận hành đúng.

## 31. Checklist triển khai

### Cấu hình

- [ ] Đã xác định workload có traffic liên tục hay thưa dữ liệu.
- [ ] `idleEventInterval` được bật khi thực sự cần idle events.
- [ ] `idleBeforeDataMultiplier` được chọn theo startup grace và SLO.
- [ ] Đã kiểm tra default và API trên đúng phiên bản Spring Kafka.
- [ ] Đã cấu hình trên đúng listener factory/container.
- [ ] Đã tách rõ `idleBetweenPolls`, `pollTimeout` và idle thresholds.

### Application events

- [ ] Có listener cho `ListenerContainerIdleEvent`.
- [ ] Có xử lý `ListenerContainerNoLongerIdleEvent` nếu cần đóng incident.
- [ ] Event callbacks nhẹ và không can thiệp KafkaConsumer sai thread.
- [ ] Có listener/instance/partition context để tránh gộp nhầm.
- [ ] Không tạo một alert mới cho mỗi idle event lặp lại.

### Observability

- [ ] Có consumer lag, input producer rate và records consumed rate.
- [ ] Có signal consumer running/paused/assignment.
- [ ] Có monitor non-responsive độc lập với idle events.
- [ ] Có metric time-to-first-record khi startup quan trọng.
- [ ] Alert phân biệt startup, steady state và maintenance.
- [ ] Tags có cardinality thấp, không đưa event IDs vào metrics.

### Kiểm thử

- [ ] Topic trống trước data đầu tiên chờ theo threshold đã nhân hệ số.
- [ ] Record đầu tiên đến sớm thì ngưỡng idle thông thường có hiệu lực sau đó.
- [ ] Listener idle lâu có event theo chính sách.
- [ ] Khi data trở lại, event no-longer-idle hoạt động nếu phù hợp.
- [ ] Concurrent consumers/partitions không bị đánh giá nhầm.
- [ ] Pause/rebalance/restart được thử nếu ảnh hưởng hệ thống.
- [ ] Test timing có dung sai cho poll và scheduler, tránh flaky assertions.

## Kết luận

`idleBeforeDataMultiplier` là hệ số nhân của `idleEventInterval` trong giai đoạn **Spring Kafka listener container chưa nhận được dữ liệu đầu tiên**. Nó giúp hệ thống tránh phát idle event quá sớm khi mới startup hoặc khi topic còn trống, trong khi vẫn duy trì ngưỡng phát hiện im lặng thông thường sau khi consumer đã có dữ liệu. Thuộc tính này không làm thay đổi tốc độ poll, offset commit, retry hay khả năng kết nối broker.

Để vận hành đúng, hãy bật `idleEventInterval` trên container thực sự được sử dụng, chọn multiplier dựa trên startup grace và SLO, sau đó quan sát `ListenerContainerIdleEvent` cùng event dữ liệu trở lại. Luôn phân biệt **idle vì không có record** với **consumer non-responsive vì không poll**, đồng thời kết hợp partition assignment, lag, producer rate, pause state và lifecycle. Một cấu hình multiplier hợp lý sẽ giảm cảnh báo sai nhưng không thay thế monitoring toàn diện cho độ tin cậy của Spring Kafka consumer.
