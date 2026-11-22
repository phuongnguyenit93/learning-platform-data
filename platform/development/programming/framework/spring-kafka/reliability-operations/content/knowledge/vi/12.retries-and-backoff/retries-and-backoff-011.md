# Retry theo từng record

Trong một consumer Spring Kafka, không phải record nào cũng được xử lý thành công ngay lần đầu. Database có thể mất kết nối vài giây, một HTTP API trả về 503, khóa nghiệp vụ có thể đang bị tranh chấp, hoặc dữ liệu trong record không hợp lệ. **Retry theo từng record** là cách xử lý có kiểm soát một record thất bại: thử lại khi lỗi có khả năng phục hồi, giới hạn số lần và thời gian thử, sau đó thực hiện recovery hoặc chuyển record sang Dead Letter Topic (DLT) nếu vẫn thất bại.

Trong chương **Retry và backoff** của Spring Kafka Reliability Operations, điều quan trọng không chỉ là viết một vòng lặp thử lại. Retry phải làm việc đúng với vòng lặp poll của Kafka consumer, offset commit, partition ordering, rebalance và khả năng xử lý trùng. Một retry policy sai có thể biến lỗi tạm thời thành consumer lag kéo dài hoặc retry storm, còn một recovery policy sai có thể làm record bị bỏ qua vĩnh viễn.

Bài này trình bày retry record listener bằng **DefaultErrorHandler**, cách định nghĩa backoff và phân loại exception, cách recover bằng DLT, sự khác biệt giữa blocking và non-blocking retry, cùng các tình huống vận hành cần kiểm chứng.

## 1. Thế nào là retry theo từng record?

Một record listener nhận từng ConsumerRecord hoặc payload trong mỗi lần gọi listener. Khi listener ném exception, Spring Kafka container chuyển lỗi tới error handler. Handler quyết định record nào phải được xử lý lại, chờ bao lâu, khi nào kết thúc retry và khi nào recovery.

Ví dụ listener:

~~~java
@Component
public class OrderListener {

    private final OrderService orderService;

    public OrderListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
        id = "order-processing",
        topics = "orders",
        groupId = "order-processing-prod"
    )
    public void onOrder(OrderCreated event) {
        orderService.process(event);
    }
}
~~~

Nếu orderService.process() ném exception, container không nên coi việc xử lý record đó là thành công. Nếu retry policy cho phép, listener được gọi lại với record thất bại. Khi retry hết hạn, recoverer sẽ xử lý theo chính sách đã cấu hình.

Một cách triển khai thường dùng:

~~~mermaid
flowchart TD
    P["Consumer poll records"] --> L["Record listener xử lý record A"]
    L --> Q{"Listener thành công?"}
    Q -->|Có| S["Tiếp tục record và commit theo AckMode"]
    Q -->|Không| E["DefaultErrorHandler nhận exception"]
    E --> C{"Exception được retry?"}
    C -->|Có| B["BackOff: chờ theo chính sách"]
    B --> R["Gọi listener lại với record A"]
    R --> Q
    C -->|Không| D["Recoverer xử lý record A"]
    E --> X{"Hết số lần retry?"}
    X -->|Có| D
    D --> Y{"Recovery thành công?"}
    Y -->|Có| N["Bỏ qua record lỗi theo policy rồi tiếp tục"]
    Y -->|Không| F["Giữ lỗi để xử lý lại; cảnh báo"]
~~~

Sơ đồ biểu diễn ý tưởng. Trong thực tế, handler phối hợp trạng thái retry, offset và những record còn lại của lần poll. Retry không đơn giản là gọi một method trong vòng lặp vô hạn.

### 1.1 Retry và redelivery khác nhau

Hai hiện tượng có thể khiến cùng một record được xử lý nhiều lần:

- **Retry trong error handler**: listener ném exception và Spring Kafka chủ động thử lại theo BackOff.
- **Redelivery từ Kafka**: record đã đọc nhưng offset chưa được commit; sau restart, rebalance hoặc seek, consumer có thể nhận lại record.

Cả hai đều có thể dẫn tới xử lý lặp. Vì vậy, ngay cả khi handler giới hạn retry chỉ một lần, ứng dụng vẫn phải chấp nhận record có thể quay lại sau khi process chết.

### 1.2 Tại sao retry ở cấp record?

Retry ở cấp record cho phép xác định chính xác record thất bại, điều chỉnh số lần thử, phân loại exception và chọn recovery độc lập với những record đã xử lý thành công.

Ví dụ poll trả về A, B, C, D; listener xử lý thành công A và B, thất bại ở C. Với record listener, container biết C là record lỗi và có thể retry C. Các record đứng sau vẫn phải được xử lý an toàn theo offset và thứ tự của từng partition. Cấu hình handler quyết định cách giữ hoặc tìm lại phần record còn lại.

Retry theo record đặc biệt phù hợp khi:

- Một record gây lỗi có thể xác định rõ.
- Mỗi record có side effect hoặc idempotency key riêng.
- Muốn phân loại transient error và poison record.
- Cần gửi đúng record thất bại tới DLT.
- Muốn hạn chế xử lý lại nhiều record đã thành công trong cùng một lần poll.

## 2. Bốn quyết định cần có trước khi bật retry

Một chính sách retry đầy đủ cần trả lời bốn câu hỏi:

1. **Retry lỗi nào?** Timeout kết nối và HTTP 503 thường có thể phục hồi; dữ liệu thiếu trường bắt buộc có thể không.
2. **Retry bao nhiêu lần và chờ bao lâu?** Cần giới hạn số lần thử và tính tổng thời gian ảnh hưởng tới consumer.
3. **Retry ở đâu?** Giữ consumer thread theo blocking retry hoặc chuyển record qua retry topic để xử lý sau.
4. **Sau khi hết retry thì làm gì?** Publish DLT, ghi trạng thái lỗi trong một hệ thống bền vững, dừng xử lý hoặc cảnh báo operator tùy yêu cầu nghiệp vụ.

Ví dụ chính sách cho một event tạo đơn hàng:

| Nhóm lỗi | Ví dụ | Cách xử lý |
|---|---|---|
| Tạm thời | Database connection timeout | Retry có giới hạn và backoff |
| Tạm thời nhưng cần chờ lâu | Downstream rate limit | Retry topic hoặc cơ chế trì hoãn phù hợp |
| Không tự phục hồi | Payload thiếu orderId | Không retry nhiều lần; DLT và cảnh báo |
| Cấu hình diện rộng | ACL Kafka sai, secret hết hạn | Khôi phục cấu hình; tránh retry dồn dập |
| Bất định | HTTP timeout sau khi downstream có thể đã nhận request | Retry với idempotency key và đối chiếu kết quả |

Không nên dựa vào tên exception để quyết định retry nếu chưa biết nguyên nhân thực tế. Cùng một TimeoutException có thể xảy ra khi request chưa đến server hoặc khi server đã xử lý xong nhưng phản hồi thất lạc.

## 3. DefaultErrorHandler cho record listener

Từ các phiên bản Spring Kafka hiện đại, **DefaultErrorHandler** là thành phần phổ biến để xử lý lỗi record listener. Nó thay cho nhiều error handler cũ và hỗ trợ BackOff, exception classification, recoverer và cách xử lý offset.

Ví dụ cấu hình cơ bản:

~~~java
@Configuration
public class KafkaRetryConfiguration {

    @Bean
    DefaultErrorHandler orderErrorHandler() {
        FixedBackOff backOff = new FixedBackOff(1_000L, 2L);
        return new DefaultErrorHandler(backOff);
    }
}
~~~

Ở đây **FixedBackOff(1_000L, 2L)** biểu thị delay 1.000 ms giữa các lần retry và tối đa hai lần retry sau lần xử lý ban đầu. Một record có thể được listener xử lý tối đa ba lần trong chuỗi thử tương ứng: một lần đầu và hai lần thử lại.

Không nên nhầm **maxAttempts** của các API khác với **maxRetries** trong FixedBackOff. Tên và cách đếm tùy API; khi cấu hình cần ghi rõ số lần gọi listener thực tế mà nghiệp vụ cho phép.

### 3.1 Gắn handler vào đúng listener container factory

Nếu dùng factory riêng:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
orderKafkaListenerContainerFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory,
        DefaultErrorHandler orderErrorHandler) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(orderErrorHandler);
    factory.setConcurrency(3);

    return factory;
}
~~~

Listener tham chiếu factory:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "order-processing-prod",
    containerFactory = "orderKafkaListenerContainerFactory"
)
public void onOrder(OrderCreated event) {
    orderService.process(event);
}
~~~

Nếu dự án có nhiều factory, một bean DefaultErrorHandler trong application context không chứng minh mọi listener đang dùng bean đó. Cần xác định annotation dùng factory nào, factory có đăng ký CommonErrorHandler nào và bean có bị auto-configuration hoặc customizer ghi đè không.

### 3.2 Handler xử lý những gì?

DefaultErrorHandler phối hợp với listener container để:

- Nhận exception của record đã thất bại.
- Giữ số lần thất bại theo record và chuỗi retry.
- Áp dụng BackOff trước khi listener được gọi lại.
- Seek consumer hoặc giữ lại record chưa xử lý để chuyển tới listener ở vòng phù hợp.
- Gọi recoverer sau khi các lần retry được sử dụng hết.
- Phối hợp offset commit với AckMode và trạng thái recovery.

Cần nhớ handler không sửa được side effect đã thực hiện trước exception. Nếu listener ghi database thành công rồi lỗi khi gọi HTTP, retry toàn bộ listener có thể ghi database lần nữa nếu code không idempotent.

## 4. Blocking retry: retry trên luồng xử lý consumer

Với blocking retry, record thất bại được xử lý lại trong luồng của consumer container, theo BackOff. Trong thời gian đó, khả năng xử lý record phía sau của cùng partition có thể bị chặn; các partition khác cùng consumer cũng có thể bị ảnh hưởng tùy cách container xử lý các record còn lại.

Ví dụ một partition:

~~~text
Partition orders-2
offset 200  A  -> thành công
offset 201  B  -> lỗi -> retry -> retry -> recovery
offset 202  C  -> chờ B được xử lý hoặc recover
offset 203  D  -> chờ
~~~

Đây là đánh đổi để giữ thứ tự xử lý: không cho record phía sau vượt record đang lỗi một cách tùy tiện.

### 4.1 Cách xử lý record còn lại sau exception

Khi listener ném exception giữa các record của một lần poll, handler cần bảo đảm record lỗi và những record chưa hoàn tất vẫn được xử lý. Trong các cấu hình Spring Kafka phổ biến:

- Handler có thể dùng consumer seek để lần poll tiếp theo đọc lại record lỗi và phần cần xử lý.
- Khi cấu hình **seekAfterError=false** ở phiên bản hỗ trợ, container có thể giữ lại các record chưa xử lý rồi chuyển chúng lại cho listener trong vòng tiếp theo, thay vì seek thực tế.
- Container có thể thực hiện một poll giữ cho consumer hoạt động trong lúc đang tạm pause hoặc chờ retry theo cơ chế framework.

Ví dụ tùy chọn:

~~~java
@Bean
DefaultErrorHandler orderErrorHandler() {
    DefaultErrorHandler handler =
        new DefaultErrorHandler(new FixedBackOff(1_000L, 2L));

    handler.setSeekAfterError(false);
    return handler;
}
~~~

Tùy chọn seekAfterError ảnh hưởng cơ chế delivery trong container. Nó không thay đổi yêu cầu idempotency hay đảm bảo rằng record chỉ được chạy đúng một lần.

### 4.2 Blocking retry ảnh hưởng độ trễ thế nào?

Giả sử consumer nhận một record lỗi với 4 lần retry, mỗi lần đợi 5 giây. Thời gian chờ riêng đã có thể lên tới khoảng 20 giây, chưa kể thời gian thực thi listener và thao tác recovery. Trong khoảng đó, các record khác có thể chưa được xử lý theo tốc độ bình thường.

Nếu một dependency hỏng diện rộng, nhiều consumer thread có thể cùng chờ backoff và retry, làm lag tăng nhanh. Cần đo tổng thời gian giữ partition và giới hạn retry theo SLA.

### 4.3 Poll interval và backoff dài

Kafka consumer có **max.poll.interval.ms** để giới hạn thời gian giữa các lần gọi poll. Nếu logic xử lý hoặc backoff chặn quá lâu mà container không poll đúng hạn, consumer có thể mất quyền giữ partition và xảy ra rebalance.

Không nên chỉ tăng max.poll.interval.ms lên một giá trị rất lớn để che lỗi downstream. Với delay dài, cân nhắc:

- Dùng cơ chế **ContainerPausingBackOffHandler** khi phiên bản Spring Kafka hỗ trợ và trường hợp phù hợp, để container pause và poll duy trì consumer membership.
- Dùng non-blocking retry topic.
- Giảm batch size hoặc thời gian xử lý mỗi record.
- Đặt timeout cho downstream.
- Theo dõi poll gap, rebalance, heartbeat và lag.

Cách backoff được thực thi phụ thuộc phiên bản và BackOffHandler đã cấu hình. Không suy luận rằng mọi BackOff tự động pause consumer an toàn trong nhiều phút.

## 5. FixedBackOff, ExponentialBackOff và jitter

**Backoff** là khoảng chờ giữa các lần retry. Nếu retry ngay lập tức khi dependency đang lỗi, ứng dụng có thể tạo một lượng request rất lớn mà không tăng khả năng phục hồi.

### 5.1 FixedBackOff

FixedBackOff dùng delay không đổi:

~~~java
new FixedBackOff(2_000L, 3L)
~~~

Policy trên thử lại tối đa ba lần sau lần đầu, chờ 2 giây giữa các lần thử. Đây là lựa chọn đơn giản cho lỗi tạm thời có thời gian hồi phục ngắn.

Đường thời gian minh họa:

~~~text
t=0s   xử lý lần 1 -> lỗi
t=2s   retry lần 1 -> lỗi
t=4s   retry lần 2 -> lỗi
t=6s   retry lần 3 -> lỗi
       hết retry -> recoverer
~~~

Các mốc chỉ minh họa thời gian chờ; thời gian thực thi listener có thể làm tổng thời gian lớn hơn.

### 5.2 ExponentialBackOff

ExponentialBackOff tăng delay sau các lần thất bại liên tiếp:

~~~java
ExponentialBackOff backOff =
    new ExponentialBackOff(1_000L, 2.0);

backOff.setMaxInterval(10_000L);
backOff.setMaxElapsedTime(60_000L);

DefaultErrorHandler handler = new DefaultErrorHandler(backOff);
~~~

Với initial interval 1 giây và multiplier 2, delay có thể tiến triển từ 1, 2, 4, 8 đến mức trần 10 giây. Giới hạn tổng thời gian cần được cấu hình phù hợp với API đang sử dụng.

Exponential backoff hữu ích khi service bên ngoài cần thời gian hồi phục, nhưng nó vẫn giữ record trong phạm vi retry nếu dùng blocking retry. Delay rất dài nên được xem xét cùng consumer poll và partition availability.

### 5.3 Jitter

Nếu hàng trăm consumer cùng gặp một lỗi và retry theo cùng nhịp cố định, chúng có thể đồng loạt gọi lại dependency vừa phục hồi. Đây là **retry storm**.

Jitter thêm độ lệch ngẫu nhiên có kiểm soát vào delay để giảm hiện tượng đồng bộ request. Việc hỗ trợ jitter phụ thuộc BackOff implementation hoặc cơ chế retry mà dự án lựa chọn. Khi tự triển khai, phải giữ delay trong giới hạn SLA và không tạo retry vô hạn.

### 5.4 Đừng nhân số lần retry không kiểm soát

Một listener có thể có nhiều lớp retry:

~~~text
Spring Kafka retry: 3 lần
HTTP client retry: 3 lần mỗi lời gọi
Database driver retry: 2 lần mỗi lời gọi
~~~

Nếu các lớp retry lồng nhau, số request thực tế tới downstream có thể lớn hơn nhiều so với cấu hình của một lớp. Cần xác định tầng nào chịu trách nhiệm retry, số lần tối đa, timeout tổng thể và circuit breaker/backpressure nếu phù hợp.

## 6. Phân loại exception retryable và non-retryable

Không phải lỗi nào cũng cải thiện khi thử lại. DefaultErrorHandler có cơ chế phân loại exception để skip backoff đối với lỗi không thể tự phục hồi.

Ví dụ:

~~~java
@Bean
DefaultErrorHandler orderErrorHandler(
        ConsumerRecordRecoverer recoverer) {

    DefaultErrorHandler handler =
        new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(1_000L, 3L)
        );

    handler.addNotRetryableExceptions(
        InvalidOrderPayloadException.class,
        UnsupportedEventVersionException.class
    );

    handler.addRetryableExceptions(
        TransientDataAccessException.class
    );

    return handler;
}
~~~

Các class nghiệp vụ trong ví dụ là class do ứng dụng định nghĩa. Danh sách mặc định lỗi được coi là fatal/non-retryable trong Spring Kafka có thể thay đổi theo phiên bản; cần hiểu chính sách hiện tại của framework.

| Loại lỗi | Nguyên nhân điển hình | Hành động thường phù hợp |
|---|---|---|
| TransientDataAccessException | Database bị gián đoạn ngắn | Retry có backoff |
| SocketTimeoutException | Network chậm hoặc phản hồi thất lạc | Retry có idempotency |
| HTTP 429 | Downstream giới hạn tải | Backoff theo Retry-After hoặc trì hoãn |
| Payload validation | Record thiếu trường bắt buộc | Non-retryable, recovery/DLT |
| ClassCastException do schema | Consumer và producer không tương thích | Sửa contract, tránh retry vô hạn |
| Authorization failure | Secret hoặc ACL sai | Sửa cấu hình, cảnh báo diện rộng |
| Business conflict vĩnh viễn | Trạng thái nghiệp vụ không hợp lệ | DLT hoặc ghi trạng thái từ chối |

### 6.1 Phân loại ở mức root cause

Một exception có thể bị bọc bởi ListenerExecutionFailedException hoặc framework exception khác. Khi phân loại, cần kiểm tra root cause và cơ chế classifier của handler phiên bản sử dụng.

Không nên đưa mọi RuntimeException vào nhóm non-retryable, vì nhiều lỗi hạ tầng cũng là runtime exception. Ngược lại, retry mọi exception có thể khiến poison message bị thử lại nhiều lần dù không có cơ hội thành công.

### 6.2 Reset backoff khi loại exception thay đổi

Trong một số phiên bản Spring Kafka, handler có tùy chọn reset trạng thái retry khi loại exception thay đổi. Điều này hữu ích khi cùng record lần lượt gặp các lỗi khác nhau, chẳng hạn lần đầu bị network timeout, lần sau gặp lỗi parsing.

Cần quyết định semantics theo nghiệp vụ và kiểm chứng trên phiên bản đang dùng. Dù reset hay giữ lại retry count, phải có giới hạn tổng thể và khả năng quan sát để tránh record bị giữ mãi.

## 7. Recovery khi hết retry

Retry phải có điểm kết thúc. Khi retry bị exhausted hoặc exception được phân loại non-retryable, **ConsumerRecordRecoverer** được gọi để xử lý record theo recovery policy.

Recovery có thể là:

- Publish record sang Dead Letter Topic.
- Lưu lỗi và thông tin record vào một kho bền vững.
- Ghi nhận một trạng thái từ chối có thể truy vết.
- Ném lỗi để container tiếp tục giữ record cần xử lý sau.

Không nên coi một recoverer chỉ log lỗi rồi return là an toàn cho mọi nghiệp vụ. Nếu recoverer return thành công, handler có thể coi record được xử lý và cho phép offset tiến triển theo policy. Với event bắt buộc, cách này có thể khiến mất cơ hội xử lý nghiệp vụ.

### 7.1 DeadLetterPublishingRecoverer

Ví dụ:

~~~java
@Bean
DefaultErrorHandler orderErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(
            kafkaTemplate,
            (record, exception) -> new TopicPartition(
                record.topic() + ".DLT",
                record.partition()
            )
        );

    DefaultErrorHandler handler =
        new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(1_000L, 2L)
        );

    handler.addNotRetryableExceptions(
        InvalidOrderPayloadException.class
    );

    return handler;
}
~~~

Khi record ở topic **orders**, partition 2 hết retry, recoverer theo routing trên gửi tới **orders.DLT**, partition 2.

Điều kiện cần:

- DLT đã được tạo với partition đích tồn tại. Nếu giữ partition nguồn, DLT cần ít nhất số partition tương ứng.
- Producer dùng để publish DLT có serializer tương thích với record được recover, kể cả trường hợp deserialization error.
- Principal có quyền ghi vào DLT.
- Có retention, replication, alert và quy trình replay.
- Publish DLT thất bại phải được phản ánh thành recovery failure; không được xem record là đã xử lý.

Nếu muốn DLT có số partition khác nguồn, cần thiết kế routing riêng; không gửi tới partition không tồn tại.

### 7.2 DLT là vùng cách ly

Record vào DLT không có nghĩa nghiệp vụ hoàn tất. Nó có nghĩa xử lý chính đã thất bại theo policy và record được đưa sang một luồng điều tra hoặc xử lý lại.

Cần lưu và truy vết:

- Topic, partition, offset gốc.
- Group id và listener id.
- Event id hoặc business key.
- Loại exception, thông báo lỗi phù hợp.
- Timestamp lần lỗi và số lần retry.
- Version schema hoặc content type khi liên quan.

Không log hoặc sao chép payload nhạy cảm thiếu kiểm soát. DLT là một phần của hệ thống dữ liệu, cần ACL, retention và quy trình xóa tương xứng.

### 7.3 Recovery failure

Nếu DLT bị lỗi hoặc recoverer ném exception, handler không nên âm thầm bỏ record. Cần giữ khả năng redelivery, phát cảnh báo, đồng thời kiểm tra các nguyên nhân như thiếu topic, ACL sai, serializer lỗi, không đủ ISR hoặc broker timeout.

Một tình huống cần chú ý là producer gửi DLT bất đồng bộ. Việc gọi send trả về future không tự bảo đảm broker đã ACK. Cần cấu hình hoặc kiểm tra outcome theo khả năng của DeadLetterPublishingRecoverer và phiên bản Spring Kafka để không đánh dấu recovered trước khi biết publish thực sự thành công.

## 8. Offset commit và retry record

Kafka consumer group lưu committed offset theo topic-partition. Offset biểu thị vị trí tiếp theo consumer sẽ đọc sau khi khởi động lại hoặc rebalance.

Nếu record xử lý thất bại mà offset của nó vẫn được commit như thành công, record có thể bị bỏ qua ở lần đọc sau. Nếu record xử lý thành công nhưng process chết trước commit, record có thể được đọc lại.

### 8.1 AckMode.RECORD

Với record listener và container-managed offset commit, AckMode.RECORD cho phép container commit offset sau khi từng record được listener xử lý thành công theo cơ chế container.

Ví dụ:

~~~yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
    listener:
      ack-mode: record
~~~

Khi listener ném exception, flow của error handler quyết định retry hoặc recovery. Cần hiểu trạng thái recoverer trước khi xem record là đã hoàn tất.

### 8.2 AckMode.BATCH và record listener

AckMode.BATCH cũng có thể được dùng với record listener. Trong một poll chứa nhiều record, container có thể commit sau khi xử lý toàn bộ batch poll thành công. Khi một record lỗi, các offset đã xử lý trước đó và offset chưa xử lý được quản lý qua error handler và commit policy.

Vì vậy, từ **record listener** không đồng nghĩa ứng dụng bắt buộc sử dụng AckMode.RECORD. Chọn ack mode theo yêu cầu throughput, độ trễ commit và mức độ chấp nhận redelivery.

### 8.3 Manual acknowledgment

Với manual ack, listener kiểm soát thời điểm xác nhận record. Hãy acknowledge chỉ sau khi business effect được bảo đảm hoàn tất theo mô hình nghiệp vụ.

Ví dụ ý tưởng:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "orders-service"
)
public void handle(
        ConsumerRecord<String, OrderCreated> record,
        Acknowledgment acknowledgment) {

    orderService.process(record.value());
    acknowledgment.acknowledge();
}
~~~

Ví dụ yêu cầu container được cấu hình AckMode phù hợp cho manual acknowledgment. Nếu process() ném exception thì không gọi acknowledge().

Không đặt acknowledge() trong finally hoặc gọi trước khi tác vụ async thực sự hoàn tất. Nếu kết hợp manual ack với recovery, cần xác định ai chịu trách nhiệm commit offset của record recovered.

### 8.4 commitRecovered

DefaultErrorHandler có cấu hình liên quan đến việc commit offset cho record đã recover, ví dụ **setCommitRecovered(true)** trong trường hợp AckMode.MANUAL_IMMEDIATE theo yêu cầu của API.

~~~java
DefaultErrorHandler handler =
    new DefaultErrorHandler(
        recoverer,
        new FixedBackOff(1_000L, 2L)
    );

handler.setCommitRecovered(true);
~~~

Chỉ bật tùy chọn này khi container ack mode và recovery policy đáp ứng điều kiện. Không thêm vào mọi factory một cách máy móc. Nếu commit khi DLT publish chưa thật sự thành công, record có thể bị bỏ qua mà không có bản sao ở DLT.

### 8.5 at-least-once và idempotency

Ngay cả khi xử lý retry và commit đúng, crash có thể xảy ra giữa business effect và offset commit:

~~~text
Listener xử lý order 1001
Database commit thành công
Process dừng trước offset commit
Consumer khởi động lại
Order 1001 được giao lại
~~~

Đây là một trường hợp at-least-once. Cần idempotency key, unique constraint, inbox/deduplication hoặc thiết kế side effect an toàn khi lặp.

Không thể dùng số lần retry để chứng minh một record chỉ tạo một side effect.

## 9. Blocking retry và non-blocking retry topic

Ngoài DefaultErrorHandler retry trên consumer, Spring Kafka hỗ trợ **non-blocking retry** qua retry topics, thường dùng @RetryableTopic trong các phiên bản phù hợp.

### 9.1 Blocking retry

~~~text
orders -> listener
         lỗi
         chờ backoff trên luồng xử lý
         thử lại record
         thành công hoặc recover
~~~

Đặc điểm:

- Dễ giữ thứ tự record theo partition trong lúc một record đang retry.
- Không cần retry topic bổ sung.
- Backoff ngắn phù hợp với lỗi tạm thời.
- Một record lỗi có thể giữ consumer/partition và làm lag tăng.

### 9.2 Non-blocking retry topic

~~~text
orders -> listener thất bại
              |
              v
         orders-retry-... -> retry listener
              |
          thất bại tiếp
              v
         orders-retry-... -> retry listener
              |
          exhausted
              v
         orders-DLT
~~~

Record được chuyển sang retry topic với cơ chế trì hoãn, giúp consumer topic chính tiếp tục xử lý. Điều này phù hợp khi lỗi cần chờ lâu hoặc throughput topic chính không thể bị chặn.

Tuy nhiên, record B có thể được xử lý trước record A đang retry ở topic khác, dù A và B có cùng key hoặc đến từ cùng partition nguồn. Vì vậy, non-blocking retry có thể thay đổi thứ tự xử lý nghiệp vụ.

### 9.3 Ví dụ @RetryableTopic

~~~java
@RetryableTopic(
    attempts = "4",
    backoff = @Backoff(
        delay = 1_000,
        multiplier = 2.0
    )
)
@KafkaListener(
    topics = "orders",
    groupId = "orders-service"
)
public void handle(OrderCreated event) {
    orderService.process(event);
}
~~~

Ví dụ diễn tả tối đa bốn lần thử theo semantics của annotation, bao gồm lần xử lý ban đầu, với backoff tăng dần. Hãy kiểm tra khả năng tạo topic, tên topic, DLT handler, retry-topic configuration và version thực tế trước khi triển khai.

Retry topic không phải cách mặc định cho mọi hệ thống. Nó tạo thêm topic, consumer group/endpoint, offset và giám sát. Nó có thể không phù hợp với yêu cầu strict ordering, một số mô hình transaction hoặc quy trình recovery hiện có.

### 9.4 Bảng lựa chọn

| Tiêu chí | Blocking retry | Non-blocking retry topic |
|---|---|---|
| Delay ngắn | Phù hợp | Có thể quá phức tạp |
| Delay vài phút hoặc lâu hơn | Cần cân nhắc poll/lifecycle | Thường phù hợp hơn |
| Giữ thứ tự theo partition | Dễ giữ hơn | Có thể thay đổi |
| Tốc độ topic chính khi record lỗi | Có thể bị chặn | Có thể tiếp tục |
| Hạ tầng bổ sung | Không cần retry topic | Cần retry topic và DLT |
| Vận hành | Theo dõi handler và consumer | Theo dõi cả topic chính và topic retry |
| Loại lỗi | Lỗi tạm thời phục hồi nhanh | Lỗi phục hồi chậm, cần trì hoãn |

Có thể phối hợp một số lần blocking retry ngắn trước khi chuyển sang retry topic nếu framework và policy hỗ trợ. Khi đó, phải tính tổng số lần thử ở tất cả các tầng.

## 10. Phân biệt record listener và batch listener

Retry record listener thuận lợi vì framework biết record vừa gây lỗi. Với batch listener, một lần gọi nhận nhiều record, nên exception thông thường có thể không cung cấp đủ thông tin để xác định record lỗi.

| Khía cạnh | Record listener | Batch listener |
|---|---|---|
| Input | Một record hoặc payload | Một danh sách/batch records |
| Record lỗi | Container biết record đang được xử lý | Có thể cần BatchListenerFailedException để biết vị trí |
| Retry mặc định khi không có vị trí lỗi | Retry record thất bại | Có thể retry toàn batch |
| Duplicate side effect | Có thể lặp record lỗi | Có thể lặp cả record đã thành công trong batch |
| Điều chỉnh | DefaultErrorHandler và BackOff | DefaultErrorHandler, fallback batch retry, partial failure |

Nếu handler batch được cấu hình để xác định failed index, logic retry và commit phần batch trước lỗi cần được hiểu riêng. Không dùng một ví dụ record listener để suy ra chính xác hành vi của batch listener.

## 11. Retry trong listener có Kafka transaction

Khi listener container được cấu hình chạy Kafka transaction, cách xử lý lỗi khác với container không transactional. Exception thường làm rollback transaction; cơ chế **AfterRollbackProcessor**, chẳng hạn DefaultAfterRollbackProcessor, được dùng để điều phối redelivery hoặc recovery sau rollback.

Không nên giả định DefaultErrorHandler là lớp duy nhất quyết định retry trong transactional listener.

Với luồng consume-transform-produce:

1. Consumer đọc input record.
2. Listener gửi output bằng KafkaTemplate transactional.
3. Exception xảy ra.
4. Kafka transaction bị rollback.
5. Output của transaction không hiển thị cho downstream read_committed.
6. Offset input trong transaction không commit, nên input có thể được xử lý lại.

Các side effect ngoài Kafka như ghi database, gửi email hoặc gọi API không tự bị rollback cùng Kafka transaction. Chúng vẫn cần idempotency hoặc cơ chế phối hợp phù hợp.

Khi dùng transactional container, kiểm tra transaction manager, listener container configuration, AfterRollbackProcessor, BackOff, recoverer và DLT trong đúng Spring Kafka version.

## 12. Deserialization error và record không tới listener

Có một trường hợp dễ bỏ sót: lỗi xảy ra **trước khi listener được gọi**, ví dụ payload không deserialize được. Nếu dùng Kafka deserializer thông thường và deserialization ném exception trong poll, listener không nhận được ConsumerRecord ở dạng mong muốn.

Spring Kafka có **ErrorHandlingDeserializer** để chuyển thông tin lỗi deserialization thành metadata phù hợp cho error handling.

Ví dụ cấu hình minh họa:

~~~yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.key.delegate.class: org.apache.kafka.common.serialization.StringDeserializer
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
~~~

Cấu hình trên chỉ minh họa wrapper và delegate, chưa bao gồm mapping type, trusted packages và contract event cụ thể của hệ thống.

Nếu deserialization error là do payload không hợp lệ cố định, retry nhiều lần sẽ không làm payload tự biến thành dữ liệu hợp lệ. Cần chuyển sang recovery/DLT phù hợp, lưu đủ metadata để điều tra và bảo đảm producer DLT có serializer tương thích với dữ liệu gốc.

Đừng nhầm lỗi trong method listener với lỗi poll/deserialization. Log exception class, topic, partition và offset nếu framework cung cấp metadata an toàn.

## 13. Retry và downstream side effect

Retry một record có thể gọi lại cùng business operation nhiều lần. Cần có cơ chế chống lặp ở ranh giới side effect.

### 13.1 Database idempotency

Ví dụ một event có eventId duy nhất:

~~~java
@Transactional
public void apply(OrderCreated event) {
    if (processedEvents.existsByEventId(event.eventId())) {
        return;
    }

    ordersRepository.insertIfAbsent(
        event.orderId(),
        event.customerId()
    );

    processedEvents.save(
        new ProcessedEvent(event.eventId())
    );
}
~~~

Đây là ví dụ ý tưởng. Trong triển khai thật, cần dùng unique constraint hoặc thao tác atomic để tránh hai consumer đồng thời cùng qua được bước exists rồi ghi trùng. Việc lưu processed event và business data nên nằm trong cùng transaction database nếu chúng cần bảo đảm nguyên tử.

### 13.2 HTTP idempotency key

Nếu listener gọi API thanh toán hoặc vận chuyển, timeout không chứng minh server chưa thực hiện request. Khi retry, gửi cùng idempotency key ổn định theo nghiệp vụ để downstream trả lại kết quả cũ hoặc bỏ qua thao tác trùng, nếu API có hỗ trợ.

~~~text
Record eventId: evt-1001
HTTP Idempotency-Key: evt-1001
Retry lần 1: evt-1001
Retry lần 2: evt-1001
~~~

Không tạo UUID mới trong mỗi lần retry; làm vậy sẽ khiến downstream coi mọi retry là một lệnh mới.

### 13.3 Transactional outbox và inbox

Với nghiệp vụ cần đồng bộ database và Kafka, **transactional outbox** giúp lưu ý định phát event cùng business transaction. Ở consumer, **inbox/deduplication** giúp nhận biết record đã được xử lý.

Kafka transaction có thể phối hợp Kafka output và input offset, nhưng không tự bao trùm side effect ở database hoặc HTTP service. Retry phải được thiết kế theo giới hạn đó.

## 14. Bài toán poison record và partition blocking

**Poison record** là record mà listener luôn thất bại với cùng điều kiện, ví dụ schema sai hoặc thiếu business key. Nếu retry vô hạn, consumer có thể không tiến triển qua record đó.

Ví dụ:

~~~text
orders-0 offset 700: record hợp lệ
orders-0 offset 701: poison record
orders-0 offset 702: record hợp lệ
orders-0 offset 703: record hợp lệ
~~~

Nếu record 701 bị retry liên tục bằng blocking retry, các record 702 và 703 trên cùng partition thường chưa được xử lý. Lag tăng dù chỉ một record là nguồn lỗi.

Giải pháp có kiểm soát:

1. Phân loại lỗi không thể phục hồi.
2. Chỉ retry trong giới hạn đủ ngắn hoặc bỏ retry khi đã biết là dữ liệu xấu.
3. Publish record vào DLT hoặc nơi lưu bền vững tương đương.
4. Sau recovery thành công, cho consumer tiếp tục xử lý record sau.
5. Điều tra, sửa dữ liệu và replay theo runbook.

Nếu nghiệp vụ yêu cầu strict ordering và record 702 không được xử lý trước khi 701 được sửa, chuyển 701 sang DLT rồi tiếp tục có thể vi phạm invariant. Khi đó cần thiết kế cách cô lập partition, tạm dừng xử lý hoặc workflow sửa dữ liệu thay vì tự động skip.

## 15. Quan sát retry theo từng record

Retry cần có metrics và logs ở cấp record, partition và consumer group. Consumer vẫn chạy không có nghĩa nghiệp vụ đang tiến triển.

| Tầng | Tín hiệu quan trọng |
|---|---|
| Listener | Processing duration, success/error rate, exception class |
| Error handler | Retry attempts, backoff elapsed, recovery attempts, recoverer failure |
| Consumer | Poll gap, rebalance, commit latency, assignment |
| Partition | Consumer lag, offset progression, age of oldest pending record |
| Downstream | Timeout, 429/503, connection pool saturation, queue depth |
| DLT | Số record được publish, publish error, age, replay status |
| Nghiệp vụ | Event id, duplicate detection, số side effect hoàn tất |

Một log hữu ích khi record thất bại:

~~~text
listenerId=order-processing
groupId=order-processing-prod
topic=orders
partition=2
offset=701
eventId=evt-1001
exception=TransientDataAccessException
attempt=2
action=retry
~~~

Không nhất thiết có sẵn mọi field trong framework. Có thể dùng Kafka headers, RecordInterceptor, retry listener hoặc instrumentation của ứng dụng tùy phiên bản.

### 15.1 RetryListener

DefaultErrorHandler có thể đăng ký RetryListener để quan sát các lần thất bại và recovery theo API của phiên bản Spring Kafka.

Ví dụ ý tưởng:

~~~java
handler.setRetryListeners(new RetryListener() {

    @Override
    public void failedDelivery(
            ConsumerRecord<?, ?> record,
            Exception ex,
            int deliveryAttempt) {

        log.warn(
            "Retry record topic={} partition={} offset={} attempt={}",
            record.topic(),
            record.partition(),
            record.offset(),
            deliveryAttempt,
            ex
        );
    }
});
~~~

Ví dụ thể hiện cơ chế quan sát, cần kiểm tra interface và chữ ký method phù hợp với phiên bản dự án. Tránh log full payload, đặc biệt với dữ liệu nhạy cảm.

### 15.2 Delivery attempt header

Một số cấu hình Spring Kafka có thể cung cấp header số lần delivery attempt cho listener. Khả năng có header và cách đếm phụ thuộc listener container, error handler và phiên bản.

Không nên dùng header này như idempotency key. Một record có thể được xử lý lại trong một consumer session mới với attempt counter khác.

### 15.3 Cảnh báo dựa trên tiến triển

Chỉ cảnh báo khi error rate cao là chưa đủ. Một partition có thể bị kẹt vì retry và không tạo lỗi mới trong mỗi giây. Nên thêm cảnh báo:

- Committed offset không tăng trong khi producer vẫn ghi.
- Lag hoặc tuổi record tăng qua SLA.
- Một event id bị retry nhiều lần.
- DLT publish failure.
- Consumer rebalance lặp lại.
- Downstream timeout tăng đồng thời ở nhiều listener.

Cần phân biệt lag do producer tăng tải với lag do consumer retry một record quá lâu.

## 16. Quy trình xử lý sự cố retry liên tục

Khi thấy một listener liên tục retry hoặc lag không giảm:

1. Xác định group id, listener id, topic, partition và offset đang lỗi.
2. Lấy event id và exception root cause; không cần log toàn bộ payload.
3. Kiểm tra lỗi là transient, dữ liệu xấu hay lỗi cấu hình diện rộng.
4. Kiểm tra retry policy hiệu lực: BackOff, maxRetries, classifier và recoverer.
5. Đối chiếu consumer poll, rebalance, lag, committed offset và assignment.
6. Kiểm tra dependency bị gọi: database pool, HTTP status, timeout, rate limit.
7. Kiểm tra idempotency và side effect nào đã commit trước exception.
8. Nếu retry exhausted, xác nhận DLT/recovery thực sự thành công.
9. Khi phục hồi, xác nhận record phía sau được xử lý và offset tiếp tục tăng.
10. Ghi nhận nguyên nhân và điều chỉnh retry policy hoặc runbook phù hợp.

Không nên reset offset ngay khi thấy poison record vì thao tác này có thể làm record bị bỏ qua hoặc nhiều record được replay. Cần snapshot offset và xác định hậu quả nghiệp vụ trước khi thay đổi vị trí đọc.

### 16.1 Khi dependency hỏng diện rộng

Nếu nhiều consumer cùng thất bại vì database không khả dụng, tăng retry count có thể khiến database chịu tải lớn hơn khi vừa phục hồi. Nên xem xét giảm concurrency, áp dụng backoff dài hơn có jitter, giới hạn connection pool hoặc tạm pause listener có kiểm soát.

Nếu lỗi là lỗi xác thực hoặc cấu hình, cần sửa nguyên nhân. Retry ngay trên từng record thường không giúp gì.

### 16.2 Khi chỉ một record lỗi

Nếu các record khác vẫn xử lý thành công và một event id luôn lỗi ở cùng vị trí, kiểm tra payload contract và nghiệp vụ. Có thể non-retryable rồi chuyển DLT nhanh hơn để giảm partition blocking, miễn policy cho phép record phía sau tiếp tục.

## 17. Kiểm thử retry theo từng record

Bài kiểm thử nên chạy trên môi trường tích hợp với Kafka broker và dữ liệu độc lập. Mỗi test phải biết event id, topic, partition và offset dự kiến.

### 17.1 Transient error

- Gửi một record hợp lệ.
- Làm downstream thất bại một hoặc hai lần đầu.
- Cấu hình FixedBackOff với số retry lớn hơn số lần lỗi.
- Xác nhận listener được gọi lại theo khoảng chờ phù hợp.
- Xác nhận side effect chỉ hoàn tất một lần theo idempotency policy.
- Xác nhận offset tiến triển sau thành công.

### 17.2 Non-retryable error

- Gửi một record thiếu trường bắt buộc.
- Ném exception đã phân loại non-retryable.
- Xác nhận handler đi tới recoverer theo policy.
- Xác nhận DLT nhận đúng record và metadata.
- Xác nhận record tiếp theo tiếp tục được xử lý nếu policy cho phép.

### 17.3 Retry exhausted

- Tạo dependency luôn thất bại.
- Cấu hình BackOff hữu hạn.
- Đếm số lần listener được gọi.
- Xác nhận recoverer được gọi khi hết retry.
- Kiểm tra offset và record tiếp theo.
- Kiểm tra không có retry vô hạn hoặc retry storm.

### 17.4 DLT publish failure

- Làm DLT tạm thời không khả dụng trong môi trường thử nghiệm.
- Đưa record đến trạng thái retry exhausted.
- Xác nhận recovery failure được ghi nhận.
- Đảm bảo record không bị âm thầm coi là thành công.
- Khôi phục DLT và xác nhận recovery có thể hoàn thành.

### 17.5 Crash giữa side effect và offset commit

- Cho listener ghi database thành công.
- Dừng process trước khi offset commit.
- Khởi động lại consumer.
- Xác nhận record có thể được giao lại.
- Xác nhận idempotency ngăn side effect trùng.

### 17.6 Ordering và retry topic

- Gửi các event cùng business key theo thứ tự.
- Cho event đầu thất bại và chuyển sang retry topic.
- Xác nhận khả năng event sau được xử lý trước event đầu.
- Đánh giá yêu cầu ordering của nghiệp vụ.
- Chọn blocking retry hoặc cơ chế điều phối phù hợp nếu strict ordering là bắt buộc.

## 18. Những hiểu nhầm cần tránh

**“Retry record bảo đảm exactly-once.”** Không. Retry và redelivery có thể gọi lại cùng nghiệp vụ; cần idempotency hoặc transaction phù hợp.

**“Hết retry thì Kafka tự đưa record vào DLT.”** Không tự động. Phải cấu hình recoverer hoặc retry-topic/DLT workflow phù hợp.

**“FixedBackOff với hai lần retry nghĩa là listener được gọi hai lần tổng cộng.”** Không. Với API FixedBackOff minh họa, có lần đầu cộng hai lần retry.

**“Retry luôn chỉ ảnh hưởng một record.”** Không hoàn toàn. Blocking retry có thể giữ tiến triển của partition và ảnh hưởng những record khác cùng consumer.

**“Có BackOff dài thì consumer sẽ không rebalance.”** Không chắc chắn. Cần xem BackOffHandler, poll lifecycle và max.poll.interval.ms.

**“Exception nào cũng nên retry.”** Không. Lỗi dữ liệu vĩnh viễn cần recovery thay vì retry nhiều lần.

**“Publish DLT là xử lý nghiệp vụ thành công.”** Không. DLT là vùng cách ly để điều tra hoặc replay.

**“Offset commit chứng minh database đã ghi.”** Không. Offset và side effect ngoài Kafka có ranh giới transaction riêng.

**“Tăng concurrency luôn giảm lag khi retry.”** Không. Concurrency bị giới hạn bởi partition count và năng lực downstream; tăng quá mức có thể tạo thêm timeout.

**“Non-blocking retry giữ thứ tự record theo partition.”** Không mặc định. Record ở retry topic có thể hoàn thành sau record mới hơn trên topic chính.

**“Retry trong DefaultErrorHandler giống retry trong transactional container.”** Không hoàn toàn. Transactional container thường dùng rollback và AfterRollbackProcessor.

## 19. Checklist thiết kế và vận hành

**Retry policy**

- [ ] Phân loại lỗi transient, permanent và lỗi cấu hình.
- [ ] Số lần retry và khoảng backoff có giới hạn.
- [ ] Có timeout tổng thể cho downstream và xử lý record.
- [ ] Backoff dài được đánh giá cùng poll interval và partition availability.
- [ ] Tránh nhiều tầng retry tạo request bùng nổ.

**Spring Kafka**

- [ ] Record listener dùng đúng container factory.
- [ ] DefaultErrorHandler được đăng ký trên factory thực tế.
- [ ] BackOff và exception classification phù hợp nghiệp vụ.
- [ ] AckMode, offset commit và recovered record semantics được hiểu rõ.
- [ ] Transactional listener dùng rollback/recovery đúng mô hình.

**Recovery và dữ liệu**

- [ ] Recoverer hoặc DLT được cấu hình cho exhausted/non-retryable record.
- [ ] DLT có partition, retention, replication và ACL phù hợp.
- [ ] Publish recovery failure được giám sát.
- [ ] Record metadata và event id được bảo toàn để điều tra.
- [ ] Side effect có idempotency key, unique constraint hoặc deduplication.

**Quan sát**

- [ ] Theo dõi retry attempts, recovery, listener error và processing latency.
- [ ] Theo dõi lag, offset progression, rebalance và poll interval.
- [ ] Có cảnh báo cho poison record và DLT publish failure.
- [ ] Có runbook replay DLT và đối chiếu duplicate.
- [ ] Đã thử transient failure, exhausted retry, crash và ordering trong môi trường phù hợp.

Retry theo từng record là cơ chế kiểm soát lỗi có khả năng phục hồi tại ranh giới consumer. Với DefaultErrorHandler, Spring Kafka có thể retry record lỗi theo BackOff, phân loại exception và gọi recoverer khi không thể tiếp tục. Độ tin cậy thực tế phụ thuộc vào thời điểm commit offset, thời gian giữ partition, khả năng publish DLT và idempotency của side effect. Một retry policy hữu ích phải giúp hệ thống phục hồi khi lỗi tạm thời biến mất và kết thúc có kiểm soát khi lỗi không thể tự phục hồi.

