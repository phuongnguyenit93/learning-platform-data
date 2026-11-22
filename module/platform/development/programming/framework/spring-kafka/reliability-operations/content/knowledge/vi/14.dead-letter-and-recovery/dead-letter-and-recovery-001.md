# Dead Letter Topic và mục đích

## 1. Dead Letter Topic là gì?

Trong Kafka, consumer đọc record từ topic và thực hiện logic nghiệp vụ. Nếu record làm listener thất bại, hệ thống có thể retry. Tuy nhiên, không phải lỗi nào cũng được khắc phục bằng cách thử lại: payload có thể không hợp lệ, schema không tương thích, dữ liệu vi phạm quy tắc nghiệp vụ hoặc dependency gặp sự cố kéo dài.

**Dead Letter Topic (DLT)** là một topic Kafka dùng để lưu những record không xử lý được trong luồng chính sau khi áp dụng chính sách retry hoặc phân loại lỗi. Khái niệm này đôi khi được gọi là **Dead Letter Queue (DLQ)**; trong Kafka, nơi lưu trữ vẫn là topic.

Ví dụ một consumer đọc **orders.created**. Record hợp lệ được ghi vào database; record lỗi nhiều lần được gửi sang **orders.created.DLT** để đội vận hành điều tra và replay khi an toàn.

~~~text
Order producer
      |
      v
orders.created
      |
      v
Spring Kafka @KafkaListener
      |
      +--> Xử lý thành công --> DB / downstream
      |
      +--> Exception
                |
                v
        DefaultErrorHandler
                |
                v
           Retry + BackOff
                |
          +-----+-----+
          |           |
       Thành công   Hết retry
          |           |
          v           v
        Tiếp tục   DeadLetterPublishingRecoverer
                      |
                      v
                orders.created.DLT
                      |
                      v
               Điều tra / replay
~~~

DLT **không đồng nghĩa với xử lý thành công**. Nó biểu thị record đã được cô lập theo chính sách, không còn được xử lý bình thường ở lượt đó. Nghiệp vụ gốc có thể vẫn đang chờ hoàn tất.

## 2. Vì sao hệ thống cần DLT?

### 2.1. Tránh một poison record chặn tiến độ

**Poison record** là record tiếp tục gây lỗi qua nhiều lần xử lý, chẳng hạn một event thiếu trường bắt buộc. Nếu consumer retry vô hạn, các record sau có thể không được xử lý kịp thời và consumer lag tăng.

DLT cho phép tách record này khỏi luồng chính, sau đó consumer tiếp tục với các record khác khi chính sách nghiệp vụ cho phép. Điều này cải thiện khả năng phục hồi nhưng có đánh đổi: event lỗi chưa được áp dụng vào trạng thái nghiệp vụ.

### 2.2. Giữ dữ liệu và nguyên nhân lỗi để điều tra

Nếu chỉ bỏ qua exception hoặc ghi log ngắn, người vận hành có thể không khôi phục được event gốc sau khi log bị xoay vòng. DLT có thể lưu key, value, headers và metadata lỗi để truy tìm nguyên nhân:

- Topic, partition và offset của bản ghi nguồn.
- Thời điểm event được tạo và được xử lý.
- Exception class, message và ngữ cảnh xử lý.
- Event ID hoặc correlation ID đã được phép lưu.
- Thông tin consumer group hoặc dịch vụ đang xử lý.

Metadata cụ thể phụ thuộc phiên bản Spring Kafka và cấu hình publisher; không nên giả định mọi header đều luôn có mặt.

### 2.3. Tách thời gian xử lý trực tuyến khỏi thời gian khắc phục

Một pipeline có thể yêu cầu độ trễ vài trăm milliseconds, trong khi sửa bug dữ liệu mất hàng giờ. DLT cho phép cô lập record bị lỗi để đội vận hành giải quyết ngoài luồng trực tiếp.

Ví dụ, một hệ thống thông báo có thể tiếp tục gửi các notification hợp lệ, còn notification có template sai được điều tra riêng.

### 2.4. Hỗ trợ replay có kiểm soát

Sau khi sửa dữ liệu, schema, consumer code hoặc dependency, record DLT có thể được replay. Replay cần quyết định đích phát, tốc độ, thứ tự và cách chống duplicate. DLT chỉ lưu dữ liệu để phục hồi; nó không tự thực hiện replay an toàn.

## 3. DLT khác retry topic như thế nào?

| Tiêu chí | Retry topic | Dead Letter Topic |
|---|---|---|
| Vai trò | Chờ xử lý lại sau một khoảng thời gian | Cô lập record không hoàn tất theo policy |
| Khả năng hồi phục | Thường kỳ vọng lỗi có thể hết | Đã hết retry hoặc lỗi được xem là terminal |
| Xử lý tiếp | Consumer retry xử lý | Điều tra, sửa, replay hoặc can thiệp thủ công |
| Tuổi dữ liệu | Theo lịch retry | Theo retention và quy trình vận hành |
| Nguy cơ | Retry storm, chậm, đảo thứ tự | Backlog bị bỏ quên, lỗi replay, dữ liệu nhạy cảm |

Với Spring Kafka, **DefaultErrorHandler** có thể thực hiện retry ở listener container rồi gọi recoverer khi hết retry. **@RetryableTopic** trong các trường hợp được hỗ trợ dùng retry topic cho non-blocking retries và có thể đưa record sang DLT.

Hai cơ chế không bắt buộc xuất hiện cùng nhau. Một consumer có thể có DLT mà không có retry topic. Không nên gọi mọi topic lỗi là DLT nếu chúng thực chất là trạm trung gian của retry workflow.

## 4. Khi nào chuyển record vào DLT?

Các trường hợp điển hình:

| Nhóm lỗi | Ví dụ | Hướng xử lý |
|---|---|---|
| Dữ liệu không hợp lệ | Thiếu field bắt buộc, giá trị enum sai | Có thể không retry dài; recovery/DLT |
| Lỗi schema | Consumer không giải mã đúng phiên bản payload | Kiểm tra compatibility; cô lập hoặc dừng luồng |
| Dependency tạm thời | DB timeout, HTTP 503 | Retry có giới hạn; DLT khi hết lượt |
| Bug consumer | NullPointerException sau deployment | Cảnh báo và rollback/fix; DLT nếu phù hợp |
| Lỗi nghiệp vụ terminal | Event vi phạm invariant không thể sửa tự động | DLT hoặc quy trình xử lý đặc biệt |
| Lỗi hạ tầng diện rộng | Cluster hoặc downstream ngừng hoạt động | Cân nhắc pause/stop để không tạo DLT ồ ạt |

**Không phải mọi lỗi đều nên vào DLT ngay.** Với lỗi tạm thời, retry ngắn có thể giải quyết mà không cần can thiệp. Với lỗi diện rộng ảnh hưởng mọi event, đưa tất cả record sang DLT có thể chỉ di chuyển backlog sang topic khác mà không làm hệ thống khỏe hơn.

Với thanh toán, kế toán, ledger hoặc workflow cần thứ tự nghiêm ngặt, bỏ qua một record có thể làm dữ liệu nghiệp vụ không nhất quán. Khi đó cần cân nhắc dừng partition/listener hoặc yêu cầu phê duyệt thay vì tự động đi tiếp.

## 5. Các thành phần Spring Kafka liên quan

| Thành phần | Trách nhiệm |
|---|---|
| **@KafkaListener** | Xử lý record và ném exception khi thất bại |
| **ConcurrentKafkaListenerContainerFactory** | Tạo listener container và gắn error handler |
| **DefaultErrorHandler** | Phối hợp retry, backoff, seek/redelivery và recovery |
| **FixedBackOff / ExponentialBackOff** | Quy định thời gian chờ, giới hạn retry |
| **DeadLetterPublishingRecoverer** | Tạo record đầu ra và publish sang DLT |
| **KafkaTemplate** | Gửi bản ghi sang Kafka |
| **DLT topic** | Lưu record lỗi và metadata |
| **DLT operator / consumer** | Điều tra, khắc phục và điều phối replay |

Một listener nên để error handler chịu trách nhiệm recovery, trừ khi ứng dụng chủ động thiết kế quy trình khác. Nếu listener chỉ bắt exception rồi ghi log và kết thúc bình thường, container có thể coi record đã được xử lý và commit offset; DLT publisher sẽ không được gọi.

## 6. Cấu hình Spring Boot và DefaultErrorHandler

Ví dụ sử dụng record listener, Spring Kafka quản lý offset:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: order-fulfillment
      enable-auto-commit: false
      auto-offset-reset: earliest
    listener:
      ack-mode: batch
      concurrency: 3
~~~

**ack-mode=batch** quyết định ranh giới commit thông thường sau poll, không buộc listener nhận danh sách. Retry và recovery được điều phối bởi error handler.

Ví dụ cấu hình recoverer với BackOff cố định:

~~~java
@Configuration
public class OrderKafkaConfiguration {

    @Bean
    DefaultErrorHandler orderErrorHandler(
            KafkaTemplate<Object, Object> dltTemplate) {

        var recoverer = new DeadLetterPublishingRecoverer(dltTemplate);
        var backOff = new FixedBackOff(1_000L, 2L);

        return new DefaultErrorHandler(recoverer, backOff);
    }

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
            orderListenerContainerFactory(
                    ConsumerFactory<String, OrderCreated> consumerFactory,
                    DefaultErrorHandler orderErrorHandler) {

        var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

        factory.setConsumerFactory(consumerFactory);
        factory.setCommonErrorHandler(orderErrorHandler);

        return factory;
    }
}
~~~

**FixedBackOff(1_000L, 2L)** yêu cầu thời gian chờ khoảng một giây giữa các lần retry và tối đa hai lượt retry sau lần đầu, theo semantics của FixedBackOff.

Các bean **ConsumerFactory**, KafkaTemplate, serializer/deserializer và security cần được cấu hình tương ứng. Nếu ứng dụng đã dùng Spring Boot auto-configuration, không nhất thiết phải tạo factory riêng; cần đảm bảo handler được gắn vào factory thực sự tạo listener.

Listener ví dụ:

~~~java
@Service
public class OrderListener {

    private final FulfillmentService fulfillmentService;

    public OrderListener(FulfillmentService fulfillmentService) {
        this.fulfillmentService = fulfillmentService;
    }

    @KafkaListener(
        topics = "orders.created",
        groupId = "order-fulfillment",
        containerFactory = "orderListenerContainerFactory"
    )
    public void consume(OrderCreated event) {
        fulfillmentService.processIdempotently(event);
    }
}
~~~

Khi **processIdempotently** ném exception, container đưa lỗi cho DefaultErrorHandler. Khi hết retry theo policy, recoverer có thể publish record sang DLT.

### 6.1. Phân loại exception

Không nên retry một payload sai dữ liệu nhiều lần chỉ để đạt ngưỡng retry. Có thể đặt exception không retry:

~~~java
var handler = new DefaultErrorHandler(
    recoverer,
    new FixedBackOff(1_000L, 3L)
);

handler.addNotRetryableExceptions(InvalidOrderException.class);
~~~

Chỉ phân loại là non-retryable khi lỗi thật sự không thể hồi phục bằng cách thử lại. Exception nghiệp vụ đôi khi bọc cause là timeout tạm thời; cần kiểm tra cấu trúc exception mà handler nhận được.

## 7. Tên topic và partition của DLT

Với destination resolver mặc định, **DeadLetterPublishingRecoverer** thường gửi record từ source topic sang topic có hậu tố **.DLT**, và giữ partition nguồn.

Ví dụ:

~~~text
Record nguồn:
  topic     = orders.created
  partition = 2
  offset    = 1452

Topic đích:
  topic     = orders.created.DLT
  partition = 2
~~~

Đây là hành vi của recoverer, không phải một tính năng tự động của broker. Kafka không tự chuyển record chỉ vì tồn tại topic tên **.DLT**.

Nếu recoverer cố publish vào partition 7 của DLT, topic DLT cần có ít nhất tám partition. Vì vậy, với mapping mặc định, số partition DLT thường cần tối thiểu bằng source topic.

### 7.1. Đổi đích bằng destination resolver

Có thể dùng một topic DLT cố định, để producer lựa chọn partition đích:

~~~java
@Bean
DeadLetterPublishingRecoverer dltRecoverer(
        KafkaTemplate<Object, Object> dltTemplate) {

    return new DeadLetterPublishingRecoverer(
        dltTemplate,
        (record, exception) ->
            new TopicPartition("fulfillment.failures.DLT", -1)
    );
}
~~~

Partition âm trong **TopicPartition** báo recoverer không yêu cầu partition đích cố định. Khi đó không được suy luận rằng partition DLT phản ánh partition gốc. Cần giữ metadata nguồn trong headers để hỗ trợ replay.

DLT riêng theo source topic thường dễ quản lý ACL, schema, retention và thống kê. DLT chung cho nhiều topic có thể phù hợp với hệ thống vận hành tập trung, nhưng cần xử lý nhiều kiểu payload và phân quyền dữ liệu.

## 8. Tạo topic DLT

DLT là một Kafka topic bình thường, có replication factor, retention, cleanup policy và ACL.

Ví dụ provision bằng Spring Kafka khi ứng dụng có KafkaAdmin/quyền phù hợp:

~~~java
@Bean
NewTopic ordersCreatedDlt() {
    return TopicBuilder
        .name("orders.created.DLT")
        .partitions(6)
        .replicas(3)
        .config(TopicConfig.RETENTION_MS_CONFIG, "604800000")
        .build();
}
~~~

Ví dụ này đặt sáu partition, replication factor ba và retention bảy ngày. Đây là giá trị minh họa, không phải mặc định chung. Topic nguồn phải có số partition tương thích nếu dùng mapping cùng partition.

Trong production, tạo topic thường thuộc IaC hoặc pipeline quản trị riêng, thay vì cấp quyền CREATE rộng cho application runtime.

### 8.1. Retention và durability

DLT retention phải đủ để phát hiện, điều tra và replay record trước khi Kafka xóa dữ liệu theo chính sách. Nếu quá ngắn, record có thể biến mất trước khi được xử lý. Nếu quá dài, storage và phạm vi lưu dữ liệu nhạy cảm tăng.

Hãy chọn retention dựa trên thời gian phản hồi incident, yêu cầu audit, khối lượng dữ liệu lỗi và chính sách dữ liệu. DLT không mặc nhiên là kho lưu trữ audit vô thời hạn.

Vì record DLT có thể là bản sao cần thiết cho recovery, hãy chọn replication factor, min.insync.replicas và producer acks phù hợp với độ quan trọng của dữ liệu.

## 9. Metadata trong record DLT

DeadLetterPublishingRecoverer có thể giữ key/value gốc, headers của record nguồn và thêm các header mô tả exception.

Thông tin thường hữu ích:

- Source topic, partition, offset và timestamp.
- Exception class và message.
- Thông tin exception stack trace theo cấu hình.
- Correlation ID hoặc event ID nếu đã có trong nguồn.
- Consumer group hoặc các trường nguồn khác khi phiên bản hỗ trợ.

Ví dụ logic:

~~~text
DLT topic = orders.created.DLT
Key       = order-102
Value     = OrderCreated{eventId=evt-102,...}

Source topic     = orders.created
Source partition = 2
Source offset    = 1452
Error class      = InvalidOrderException
Error message    = missing shippingAddress
~~~

Các tên trường mô tả ở đây không phải tên hằng số header bắt buộc. Khi viết Java code để đọc headers, dùng các hằng số **KafkaHeaders** hoặc API phù hợp của Spring Kafka version thực tế.

Không dùng exception message làm protocol ổn định cho retry/replay vì text lỗi có thể thay đổi qua phiên bản. Nếu cần tự động phân loại, dùng mã lỗi nghiệp vụ được version rõ ràng.

### 9.1. Bảo mật headers

Exception và payload có thể chứa email, địa chỉ, dữ liệu cá nhân hoặc secret vô tình bị log. DLT phải được kiểm soát quyền READ/WRITE, retention và masking giống như topic gốc hoặc nghiêm ngặt hơn.

## 10. Lỗi deserialization và serializer DLT

Có hai nhóm lỗi cần phân biệt:

1. Listener đã nhận object Java hợp lệ rồi xử lý thất bại.
2. Kafka consumer không deserialize được record, vì vậy listener chưa được gọi.

Trong trường hợp thứ hai, listener không thể ném lỗi nghiệp vụ cho payload nó chưa nhìn thấy. **ErrorHandlingDeserializer** thường được dùng để Spring Kafka đưa thông tin lỗi deserialization tới error handling.

Ví dụ:

~~~yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        "[spring.deserializer.key.delegate.class]": org.apache.kafka.common.serialization.StringDeserializer
        "[spring.deserializer.value.delegate.class]": org.springframework.kafka.support.serializer.JsonDeserializer
~~~

Khi lỗi deserialize, recoverer có thể cần publish nguyên bytes gốc vào DLT. KafkaTemplate dùng cho DLT phải có serializer xử lý đúng key/value thực tế. Một **JsonSerializer** chỉ dành cho object nghiệp vụ không nhất thiết phù hợp với dữ liệu bytes lỗi.

Có thể cần **DelegatingByTypeSerializer** hoặc nhiều KafkaTemplate cho các kiểu key/value khác nhau. Hãy xác nhận kiểu dữ liệu thật recoverer nhận khi lỗi trước listener.

## 11. Recovery và commit offset

Một record chuyển sang DLT được xem là đã **recovered** theo handler policy, không có nghĩa nghiệp vụ gốc đã hoàn tất.

Sau khi recovery thành công, container có thể tiến offset để tiếp tục xử lý các record sau. Hành vi cụ thể phụ thuộc:

- AckMode và trạng thái commit của listener container.
- Cấu hình **ackAfterHandle** của error handler.
- Tùy chọn **commitRecovered** trong điều kiện được hỗ trợ, thường liên quan MANUAL_IMMEDIATE.
- Recovery publisher có xác nhận thành công hoặc ném exception không.
- Container transactional hay non-transactional.

Không nên nói mọi ứng dụng Spring Kafka luôn commit offset ngay sau DLT publish; phải kiểm tra effective configuration.

### 11.1. DLT publish thất bại là lỗi reliability

Ví dụ producer DLT bị thiếu quyền WRITE. Nếu recoverer gửi không thành công mà ứng dụng vẫn commit offset nguồn, record có nguy cơ không còn được xử lý lại trong luồng chính và cũng không tồn tại trên DLT.

Vì vậy:

1. Xác nhận DLT topic tồn tại.
2. Xác nhận principal có quyền WRITE.
3. Cấu hình serializer phù hợp.
4. Quan sát kết quả publish và lỗi recoverer.
5. Không che exception recovery hoặc giả định publish đã thành công.

### 11.2. Kafka transaction không rollback DB

Kafka transaction có thể phối hợp output Kafka và offset input ở những luồng được hỗ trợ. Nó không tự tạo transaction phân tán với database hoặc HTTP service.

Nếu consumer đã ghi DB nhưng crash trước khi commit offset, record có thể được giao lại. DLT không khắc phục side effect đã tồn tại bên ngoài Kafka.

## 12. DLT đối với batch listener

Với batch listener, một record lỗi có thể khiến toàn bộ batch thất bại. Nếu listener biết chính xác vị trí record lỗi, có thể ném **BatchListenerFailedException** cùng zero-based index để DefaultErrorHandler xử lý phần trước và sau lỗi theo policy.

~~~java
@KafkaListener(
    topics = "orders.created",
    groupId = "order-fulfillment",
    containerFactory = "orderBatchContainerFactory"
)
public void consume(
        List<ConsumerRecord<String, OrderCreated>> records) {

    for (int i = 0; i < records.size(); i++) {
        try {
            fulfillmentService.process(records.get(i).value());
        }
        catch (RuntimeException ex) {
            throw new BatchListenerFailedException(
                "Order processing failed",
                ex,
                i
            );
        }
    }
}
~~~

Nếu chỉ ném exception thường và không biết phần tử lỗi, fallback batch retry có thể thử lại toàn batch. Một số record đã có side effect có thể bị gọi lại, vì vậy idempotency vẫn cần thiết.

**Non-blocking retries qua @RetryableTopic** không hỗ trợ batch listener trong các phiên bản Spring Kafka phổ biến có cơ chế retry topic này; nếu cần retry topic riêng từng record, cân nhắc record listener hoặc thiết kế khác.

## 13. Replay từ DLT

Replay không đơn giản là đọc mọi record DLT và gửi lại topic nguồn. Nó là một thao tác nghiệp vụ cần kiểm soát.

Quy trình khuyến nghị:

1. Xác định nguyên nhân record vào DLT.
2. Xác nhận bug, schema, payload hoặc downstream đã được khắc phục.
3. Kiểm tra event còn phù hợp với business state hiện tại không.
4. Kiểm tra khả năng đã tạo side effect một phần.
5. Chọn replay đích: topic nguồn, recovery topic hoặc service xử lý riêng.
6. Đặt giới hạn tốc độ replay và xử lý ordering.
7. Ghi nhận attempt, actor, thời điểm và kết quả replay.
8. Dùng idempotency key ổn định để chống tác động lặp.
9. Theo dõi lỗi và không tạo vòng lặp replay tự động vô hạn.

### 13.1. Replay về topic nguồn

Nếu phát lại vào topic nguồn, record được append với offset mới. Event cũ có thể xuất hiện **sau event mới**, làm thay đổi trình tự xử lý nghiệp vụ, dù các record trong partition vẫn giữ thứ tự log.

Ngoài ra, mọi consumer group khác đọc topic này đều có thể nhận event được replay. Vì vậy, cần đánh giá phạm vi tác động của replay, đặc biệt với thanh toán, thông báo hoặc workflow đa dịch vụ.

### 13.2. Recovery consumer riêng

Một consumer DLT chuyên dụng có thể kiểm tra trạng thái nghiệp vụ rồi áp dụng logic khắc phục. Cách này giảm việc phát lại event vào mọi consumer downstream của topic nguồn, nhưng vẫn phải quản lý offset, retry, quyền truy cập và side effect idempotent.

### 13.3. Tránh replay loop

~~~text
DLT -> replay -> topic nguồn -> lỗi -> DLT -> replay ...
~~~

Nếu không giới hạn số attempt hoặc không có bước sửa nguyên nhân, vòng lặp có thể diễn ra liên tục. Cần trạng thái terminal, lịch sử replay, cảnh báo và quy trình can thiệp thủ công.

## 14. Idempotency khi retry và replay

Một event được gửi tới DLT chưa chắc đã hoàn toàn chưa tác động lên hệ thống đích. Consumer có thể thành công ở bước ghi database nhưng thất bại khi gọi API tiếp theo hoặc crash trước commit offset.

~~~text
Consume OrderCreated
       |
       v
DB commit thành công
       |
       v
Crash trước Kafka offset commit
       |
       v
Record được đọc lại / replay
       |
       v
Nguy cơ tạo fulfillment lần hai
~~~

Một cách bảo vệ là dùng event ID ổn định và bảng inbox:

~~~sql
CREATE TABLE processed_event (
    event_id VARCHAR(128) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Side effect và ghi event ID nên nằm trong cùng DB transaction. Unique constraint giúp chống race condition nếu hai attempt xử lý cùng event. Chỉ kiểm tra **existsById** trước insert không đủ để bảo vệ khi thực thi đồng thời.

Với external API, dùng idempotency key do dependency cung cấp hoặc cơ chế đối soát kết quả. Kafka transaction không thể rollback một HTTP request đã được hệ thống bên ngoài chấp nhận.

## 15. DLT và thứ tự nghiệp vụ

Kafka đảm bảo thứ tự trong từng partition, nhưng khi một record bị chuyển sang DLT, consumer chính có thể tiếp tục xử lý record sau đó tùy policy.

~~~text
orders.created - partition 1

offset 100: OrderCreated(order-1) --> lỗi, vào DLT
offset 101: OrderPaid(order-1)    --> xử lý tiếp
~~~

Nếu OrderPaid phụ thuộc vào việc OrderCreated đã được áp dụng, thứ tự log được giữ nhưng thứ tự hoàn tất nghiệp vụ không còn đúng.

Trước khi áp dụng DLT cần xác định:

- Event sau có được xử lý nếu event trước thất bại không?
- Có cần pause partition hoặc stop listener khi gặp lỗi nghiêm trọng không?
- Các event cùng entity có dùng partition key ổn định không?
- Replay event cũ ảnh hưởng thế nào tới state hiện tại?
- Có cần ghi trạng thái “pending manual recovery” trong DB không?

DLT giúp cô lập lỗi nhưng không tự bảo toàn dependency nghiệp vụ giữa các event.

## 16. Quan sát và cảnh báo

Một DLT không có owner, metric và quy trình xử lý sẽ chỉ là nơi tích tụ record lỗi.

| Chỉ số | Câu hỏi vận hành |
|---|---|
| DLT ingress rate | Có bao nhiêu record mới vào DLT? |
| Recovery publish failures | Có record nào gửi DLT thất bại? |
| Oldest unresolved age | Record chưa xử lý lâu nhất bao nhiêu tuổi? |
| Exception distribution | Lỗi nào chiếm ưu thế? |
| Retry-to-DLT ratio | Bao nhiêu retry kết thúc bằng recovery? |
| Replay attempts/success | Replay đã được thử và hoàn tất ra sao? |
| Consumer lag theo partition | Luồng chính có bị nghẽn không? |
| DLT storage/retention | Có nguy cơ hết disk hoặc hết thời gian giữ dữ liệu? |

**Số record còn trong DLT không bằng số record chưa được xử lý.** Record đã replay thành công vẫn tồn tại trong Kafka tới khi retention xóa. Nếu cần unresolved backlog chính xác, hãy lưu trạng thái xử lý riêng theo event ID hoặc nguồn topic/partition/offset.

Một log DLT có thể chứa:

~~~text
service=order-fulfillment
eventId=evt-102
sourceTopic=orders.created
sourcePartition=2
sourceOffset=1452
dltTopic=orders.created.DLT
exceptionClass=InvalidOrderException
recovery=published
~~~

Tránh dùng event ID, offset hay order ID làm label metrics có cardinality cao. Chúng phù hợp hơn với log/trace có kiểm soát dữ liệu nhạy cảm.

### 16.1. Khi DLT tăng đột biến

Nếu số record vào DLT tăng mạnh sau deployment, kiểm tra phiên bản consumer, schema và downstream trước khi kết luận dữ liệu nguồn hỏng. Với lỗi diện rộng, cân nhắc rollback hoặc pause consumer để không đẩy toàn bộ lưu lượng vào DLT.

Nếu recoverer publish DLT lỗi, cảnh báo mức cao vì đây là thất bại ở lớp bảo vệ cuối của consumer.

## 17. Quyền truy cập và bảo mật

DLT là topic Kafka có ACL riêng:

| Thành phần | Quyền cần kiểm tra |
|---|---|
| Source consumer | READ topic gốc, READ consumer group |
| DLT producer/recoverer | WRITE trên DLT |
| DLT consumer/operator | READ DLT và READ group tương ứng |
| Replay producer | WRITE topic đích |
| Topic provisioning | CREATE hoặc quyền quản trị theo quy trình |

Một ứng dụng có thể dùng KafkaTemplate riêng cho DLT, với credential khác producer nghiệp vụ. Khi có **TopicAuthorizationException**, cần xác định principal thật sự được recoverer sử dụng.

Payload DLT và exception message có thể chứa dữ liệu cá nhân hoặc stack trace. Chỉ cấp quyền tối thiểu, quản lý retention và audit thao tác replay.

## 18. Ví dụ tổng hợp: Order Fulfillment

Giả sử Order Service phát **OrderCreated** vào **orders.created**. Consumer Fulfillment Service ghi yêu cầu giao hàng vào DB, có khả năng idempotent theo event ID.

Chính sách:

- Timeout DB: retry hai lần, cách nhau một giây.
- InvalidOrderException: không retry lâu, chuyển sang recovery.
- Hết retry: gửi sang **orders.created.DLT**.
- Operator phân loại lỗi, sửa nguyên nhân và replay có kiểm soát.

Listener:

~~~java
@KafkaListener(
    topics = "orders.created",
    groupId = "order-fulfillment",
    containerFactory = "orderListenerContainerFactory"
)
public void handle(OrderCreated event) {
    fulfillmentService.processIdempotently(event);
}
~~~

Error handler:

~~~java
@Bean
DefaultErrorHandler orderErrorHandler(
        KafkaTemplate<Object, Object> dltTemplate) {

    var recoverer = new DeadLetterPublishingRecoverer(dltTemplate);
    var handler = new DefaultErrorHandler(
        recoverer,
        new FixedBackOff(1_000L, 2L)
    );
    handler.addNotRetryableExceptions(InvalidOrderException.class);
    return handler;
}
~~~

Khi một record có địa chỉ giao hàng không hợp lệ, record có thể được publish sang DLT sớm theo policy. Khi database downtime kéo dài, record hợp lệ có thể vào DLT sau các lần retry thất bại.

Nếu nhiều event đổ vào DLT cùng lúc, cần điều tra outage thay vì cho replay chạy liên tục. Nếu event đã ghi fulfillment trước khi crash, replay phải nhận ra event ID đã xử lý để tránh tạo hai yêu cầu giao hàng.

## 19. Các sai lầm thường gặp

**Cho rằng DLT được Kafka tạo tự động.** Kafka không tự chuyển record; ứng dụng cần recoverer hoặc publisher và topic đã được provision phù hợp.

**Cho rằng vào DLT nghĩa là xử lý thành công.** DLT chỉ cô lập record lỗi; nghiệp vụ còn có thể chưa hoàn tất.

**Quên partition count.** Default recoverer thường giữ partition nguồn; DLT thiếu partition có thể làm publish thất bại.

**Quên serializer cho lỗi deserialization.** DLT producer có thể phải gửi bytes gốc thay vì object nghiệp vụ.

**Nuốt exception trong listener.** Container có thể commit offset mà không biết lỗi để gửi DLT.

**Không kiểm tra DLT publish error.** Recovery thất bại có thể làm record bị kẹt hoặc mất nếu policy commit sai.

**Coi tổng record trong topic là unresolved backlog.** Record đã xử lý vẫn được giữ tới khi retention xóa.

**Replay vô điều kiện.** Có thể tạo duplicate, đảo thứ tự nghiệp vụ hoặc vòng lặp DLT.

**Cho rằng transaction Kafka rollback được database.** Side effect ngoài Kafka cần idempotency/outbox/inbox riêng.

**Không phân công owner xử lý.** DLT không có người theo dõi không tạo ra khả năng phục hồi thực tế.

## 20. Quy trình triển khai và vận hành

1. Phân loại lỗi retryable, terminal và lỗi cần dừng luồng.
2. Cấu hình DefaultErrorHandler, BackOff và DeadLetterPublishingRecoverer.
3. Xác định tên DLT, partition mapping, retention và replication.
4. Kiểm tra KafkaTemplate và serializer thực sự dùng để publish DLT.
5. Cấp đúng ACL WRITE trên DLT cho principal của recoverer.
6. Xác định chính sách offset commit sau recovery thành công/thất bại.
7. Giữ metadata nguồn và exception cần thiết, tránh lộ secret.
8. Thiết kế idempotency cho side effect của retry và replay.
9. Đặt cảnh báo DLT ingress spike, recovery failures và unresolved age.
10. Có owner, runbook, phê duyệt replay và giới hạn tốc độ replay.
11. Thử lỗi validation, dependency timeout, lỗi publish DLT và crash trước commit.
12. Đánh giá business ordering khi record lỗi bị tách khỏi luồng chính.

## 21. Ghi nhớ

**Dead Letter Topic** là nơi cô lập record mà consumer không thể hoàn tất theo retry/recovery policy. Trong Spring Kafka, **DefaultErrorHandler** phối hợp **BackOff** và **DeadLetterPublishingRecoverer** để publish record sang DLT.

DLT giúp tránh poison record làm tắc nghẽn luồng trong các trường hợp có thể tiếp tục, giữ thông tin điều tra và hỗ trợ replay có kiểm soát. Nó không tự bảo đảm exactly-once, không tự giữ thứ tự nghiệp vụ, không xác nhận side effect đã hoàn tất và không thay thế idempotency.

Một thiết kế DLT đáng tin cậy phải có **retention phù hợp, ACL, quan sát, alert, owner, runbook và quy trình replay an toàn**.
