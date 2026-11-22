# Record listener và batch listener

Spring Kafka hỗ trợ hai cách chính để một listener nhận dữ liệu từ Kafka: record listener xử lý từng record trong mỗi lần gọi phương thức, còn batch listener xử lý một nhóm record được trả về từ một lần poll. Cả hai đều chạy trên listener container và dùng cùng nền tảng consumer, nhưng khác nhau ở cách giao dữ liệu cho code nghiệp vụ, cách xác nhận offset và cách xử lý lỗi.

Record listener phù hợp khi mỗi event cần được xử lý độc lập, dễ retry và cần kiểm soát lỗi theo từng record. Batch listener phù hợp khi có thể xử lý nhiều event cùng lúc, ví dụ ghi database theo lô, bulk API hoặc tính toán trên một tập dữ liệu. Batch có thể giảm overhead mỗi record và tăng throughput, nhưng làm tăng độ phức tạp về memory, latency, acknowledgement và xử lý record lỗi.

Bài học thuộc chương **Batch và throughput** của module **SPRING_KAFKA_MESSAGING**. Module tập trung xây dựng ứng dụng gửi nhận sự kiện bằng Spring Kafka, `KafkaTemplate` và `@KafkaListener`, hiểu topic, partition, offset và consumer group; đồng thời học serialization, retry, dead-letter, transaction, xử lý đồng thời và kiểm thử để vận hành luồng messaging tin cậy.

## 1. Record listener và batch listener khác nhau thế nào?

Record listener nhận một record cho mỗi lần gọi phương thức listener. Consumer vẫn có thể lấy nhiều record trong một lần poll, nhưng listener container lần lượt chuyển từng record cho phương thức.

Batch listener nhận một tập record trong một lần gọi. Tập này thường tương ứng với các record mà Kafka consumer trả về từ một lần `poll()`. Kích thước batch thay đổi theo lưu lượng, partition assignment, giới hạn fetch và `max.poll.records`.

| Tiêu chí | Record listener | Batch listener |
| --- | --- | --- |
| Dữ liệu đầu vào | Một record | Một danh sách/tập record |
| Số lần gọi listener | Một lần cho mỗi record | Một lần cho một batch |
| Xử lý lỗi | Dễ xác định record lỗi | Cần xác định record lỗi trong batch hoặc retry cả batch |
| Acknowledgement | Có thể xác nhận theo record hoặc batch tùy AckMode | Thường xác nhận sau khi xử lý batch |
| Throughput | Phù hợp xử lý từng event | Có thể cao hơn khi xử lý theo lô |
| Latency | Có thể xử lý ngay từng record | Có thể cần chờ đủ dữ liệu hoặc batch được poll |
| Memory | Thường thấp hơn mỗi lần gọi | Có thể cao hơn do giữ nhiều record cùng lúc |
| Use case | Gửi email, cập nhật một aggregate, gọi nghiệp vụ theo event | Bulk insert, batch update, bulk API, xử lý dữ liệu theo tập |

Cả hai chế độ đều đọc dữ liệu theo partition và offset. Batch listener không tạo thứ tự toàn topic; các record từ nhiều partition có thể cùng nằm trong một batch nhưng chỉ có thứ tự được bảo đảm bên trong từng partition.

~~~mermaid
flowchart TD
    A[Kafka consumer poll] --> B[Records từ các partition được gán]
    B --> C{Listener mode}
    C -->|Record| D[Container gọi listener cho từng record]
    C -->|Batch| E[Container chuyển cả batch trong một lần gọi]
    D --> F[Xử lý và acknowledgement]
    E --> F
    F --> G[Commit offset theo AckMode]
~~~

## 2. Record listener với @KafkaListener

Record listener là chế độ mặc định của listener container. Phương thức có thể nhận payload đã được deserialize:

~~~java
@Component
public class OrderEventListener {

    @KafkaListener(
        id = "orderRecordListener",
        topics = "order-events",
        groupId = "order-service",
        containerFactory = "recordListenerFactory"
    )
    public void onOrderEvent(OrderEvent event) {
        orderService.handle(event);
    }
}
~~~

Spring Kafka lấy record từ consumer, chuyển value thành OrderEvent thông qua deserializer/converter đã cấu hình rồi gọi phương thức listener.

Nếu cần metadata như topic, partition, offset, key hoặc timestamp, nhận trực tiếp `ConsumerRecord`:

~~~java
@KafkaListener(
    id = "orderRecordListener",
    topics = "order-events",
    groupId = "order-service",
    containerFactory = "recordListenerFactory"
)
public void onOrderEvent(
        ConsumerRecord<String, OrderEvent> record) {

    log.info(
        "topic={} partition={} offset={} key={}",
        record.topic(),
        record.partition(),
        record.offset(),
        record.key()
    );

    orderService.handle(record.value());
}
~~~

Cách nhận ConsumerRecord hữu ích khi cần audit, tracing hoặc xử lý phụ thuộc metadata. Nếu chỉ cần payload, nhận OrderEvent giúp chữ ký listener gọn hơn.

### 2.1. Cấu hình record listener container factory

Có thể khai báo factory riêng cho record listener:

~~~java
@Configuration
public class KafkaListenerConfiguration {

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
            recordListenerFactory(
                ConsumerFactory<String, OrderEvent> consumerFactory) {

        var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

        factory.setConsumerFactory(consumerFactory);
        factory.setBatchListener(false);
        return factory;
    }
}
~~~

`setBatchListener(false)` làm rõ factory này dùng record listener. Đây cũng là hành vi mặc định trong cấu hình thông thường, nhưng khai báo tường minh giúp phân biệt với factory dành cho batch.

Có thể dùng một factory mặc định cho nhiều listener record nếu chúng có cùng ConsumerFactory, converter và chính sách container. Khi một nhóm listener cần AckMode hoặc concurrency khác, có thể tạo factory riêng.

## 3. Batch listener với @KafkaListener

Để listener nhận cả batch, cấu hình container factory với `setBatchListener(true)`:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        batchListenerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setBatchListener(true);
    factory.getContainerProperties()
        .setAckMode(ContainerProperties.AckMode.BATCH);

    return factory;
}
~~~

Listener dùng factory này có thể nhận danh sách ConsumerRecord:

~~~java
@Component
public class OrderBatchListener {

    @KafkaListener(
        id = "orderBatchListener",
        topics = "order-events",
        groupId = "order-batch-service",
        containerFactory = "batchListenerFactory"
    )
    public void onOrders(
            List<ConsumerRecord<String, OrderEvent>> records) {

        orderService.handleBatch(records);
    }
}
~~~

Một lần gọi listener nhận tập record mà consumer poll trả về. Batch có thể chứa record từ nhiều partition được gán cho consumer đó. Nó không nhất thiết chứa đủ `max.poll.records`; nếu topic ít dữ liệu hoặc fetch chưa đủ, batch có thể nhỏ hơn.

Nên dùng `List<ConsumerRecord<K,V>>` khi cần truy cập metadata của từng record. Nếu chỉ cần payload, có thể dùng `List<OrderEvent>` khi message converter được cấu hình để chuyển batch phù hợp.

## 4. Batch listener nhận payload hay ConsumerRecord?

Có hai kiểu chữ ký thường dùng:

**Nhận ConsumerRecord:**

~~~java
@KafkaListener(
    topics = "order-events",
    groupId = "order-batch-service",
    containerFactory = "batchListenerFactory"
)
public void onOrders(
        List<ConsumerRecord<String, OrderEvent>> records) {

    for (ConsumerRecord<String, OrderEvent> record : records) {
        orderService.validate(record.value());
    }

    orderService.persistBatch(records);
}
~~~

Ưu điểm là mỗi phần tử có đầy đủ topic, partition, offset, key, timestamp và headers. Đây là lựa chọn dễ kiểm soát khi xử lý lỗi theo record hoặc cần quan sát.

**Nhận payload đã chuyển đổi:**

~~~java
@KafkaListener(
    topics = "order-events",
    groupId = "order-batch-service",
    containerFactory = "batchListenerFactory"
)
public void onOrders(List<OrderEvent> events) {
    orderService.persistEvents(events);
}
~~~

Kiểu này cần batch message conversion phù hợp. Spring Kafka có `BatchMessagingMessageConverter` để chuyển một batch ConsumerRecord thành Spring Message có payload là danh sách. Converter có thể phối hợp với record converter để deserialize/convert từng phần tử.

Nếu cần metadata song song với payload, có thể nhận `List<Message<?>>` hoặc cấu hình converter/header phù hợp. Hãy chọn chữ ký mà ứng dụng thực sự cần; không nên chuyển mọi record thành Message object nếu chỉ xử lý payload.

## 5. Cấu hình BatchMessagingMessageConverter

Khi batch listener nhận payload list và cần chuyển metadata/header, có thể cấu hình batch converter:

~~~java
@Bean
public BatchMessageConverter batchMessageConverter() {
    return new BatchMessagingMessageConverter();
}
~~~

Gắn converter vào factory:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        batchListenerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory,
            BatchMessageConverter batchMessageConverter) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setBatchListener(true);
    factory.setBatchMessageConverter(batchMessageConverter);
    return factory;
}
~~~

`BatchMessagingMessageConverter` có thể dùng record converter bên trong để chuyển từng record. Nếu ứng dụng đã có converter JSON hoặc custom converter, cấu hình converter đó theo API phiên bản Spring Kafka đang dùng.

Nếu listener nhận `List<ConsumerRecord<K,V>>`, có thể không cần chuyển từng record thành Spring Message. Dùng ConsumerRecord giúp giữ metadata Kafka nguyên bản và giảm một lớp chuyển đổi.

## 6. Batch được tạo ra từ poll như thế nào?

Kafka consumer gọi `poll()` để lấy record từ các partition đang được gán. Một lần poll có thể trả về nhiều record từ một hoặc nhiều partition. Batch listener nhận tập record này trong một lần gọi.

Một số yếu tố ảnh hưởng kích thước batch:

| Cấu hình/yếu tố | Ảnh hưởng |
| --- | --- |
| `max.poll.records` | Giới hạn số record tối đa trả về trong một lần poll. |
| `fetch.max.bytes` | Giới hạn tổng dữ liệu fetch trong một request theo cấu hình client. |
| `max.partition.fetch.bytes` | Giới hạn dữ liệu fetch cho mỗi partition trong một request. |
| Số partition được assign | Nhiều partition có thể đóng góp record vào cùng poll. |
| Lưu lượng producer | Ít dữ liệu mới thì batch thường nhỏ. |
| Thời gian poll và network | Ảnh hưởng thời điểm và lượng dữ liệu nhận được. |

`max.poll.records` giới hạn số record trả về cho ứng dụng trong một lần poll; nó không phải kích thước byte của batch và không thay thế các fetch size setting. Kafka client có thể fetch dữ liệu trước vào buffer rồi trả record cho ứng dụng theo giới hạn poll.

Ví dụ cấu hình:

~~~yaml
spring:
  kafka:
    consumer:
      max-poll-records: 200
      properties:
        max.poll.interval.ms: 300000
        fetch.max.bytes: 52428800
        max.partition.fetch.bytes: 1048576
~~~

Các con số chỉ là giá trị minh họa. Hãy đo kích thước payload, throughput, số partition và thời gian xử lý để chọn giới hạn phù hợp. Tăng batch size không tự động làm throughput tăng nếu bottleneck nằm ở database, network hoặc logic nghiệp vụ.

## 7. Batch có thể chứa record từ nhiều partition

Một consumer có thể được gán nhiều partition. Vì vậy, một poll batch có thể chứa record từ nhiều partition thuộc cùng topic hoặc nhiều topic nếu subscription cho phép.

Ví dụ minh họa:

~~~text
Consumer A được gán:
  order-events-0
  order-events-1
  payment-events-0

Một lần poll:
  order-events-0: offsets 10, 11
  order-events-1: offsets 20, 21, 22
  payment-events-0: offsets 5, 6
  --------------------------------
  Tổng cộng: 7 records trong batch
~~~

Thứ tự record trong từng partition vẫn được giữ theo offset. Không có thứ tự nghiệp vụ tổng thể giữa record của partition 0 và partition 1. Nếu batch listener xử lý tất cả record trong một vòng lặp, không nên giả định record từ partition nào sẽ luôn xuất hiện trước record của partition khác.

Nếu cần xử lý tuần tự theo key, hãy dùng key để các event cùng thực thể vào một partition và tránh dispatch bất đồng bộ làm đảo thứ tự.

## 8. Acknowledgement và commit offset với record listener

Container quản lý commit offset dựa trên `AckMode`. Với record listener, các chế độ thường gặp:

| AckMode | Hành vi khái quát |
| --- | --- |
| `RECORD` | Commit sau khi listener xử lý xong từng record. |
| `BATCH` | Commit sau khi tất cả record từ poll hiện tại được xử lý. |
| `TIME` | Commit theo thời gian khi có record đã xử lý. |
| `COUNT` | Commit khi đạt số record đã xử lý. |
| `COUNT_TIME` | Kết hợp ngưỡng số record và thời gian. |
| `MANUAL` | Listener gọi acknowledge; commit theo quy trình batch của container. |
| `MANUAL_IMMEDIATE` | Commit ngay khi acknowledge được gọi trên consumer thread; hành vi khác nếu gọi từ thread khác. |

Các chế độ trên áp dụng khi auto commit của Kafka consumer được tắt để Spring container quản lý acknowledgement. Spring Kafka thường khuyến nghị container quản lý commit thay vì bật auto commit trong các ứng dụng listener.

Với record listener, `AckMode.RECORD` phù hợp khi muốn tiến độ commit sát từng record. `BATCH` có thể giảm số lần commit nhưng nếu consumer dừng giữa batch, record đã xử lý sau committed offset có thể được đọc lại.

Không nên coi commit offset là bằng chứng mọi tác vụ ngoài Kafka đã hoàn tất bền vững. Nếu listener cập nhật database rồi commit offset, cần thiết kế transaction/outbox/idempotency phù hợp để xử lý crash ở giữa hai thao tác.

## 9. Acknowledgement và commit offset với batch listener

Batch listener nhận một tập record như một đơn vị gọi listener. `AckMode.RECORD` không phù hợp với batch listener vì container không gọi listener riêng cho từng record; hãy dùng BATCH hoặc các chế độ manual theo semantics của phiên bản Spring Kafka.

Với `AckMode.BATCH`, container commit sau khi listener xử lý thành công batch. Đây là lựa chọn phổ biến khi toàn bộ batch được xem như một đơn vị xử lý.

Ví dụ dùng acknowledgment thủ công:

~~~java
@KafkaListener(
    topics = "order-events",
    groupId = "order-batch-service",
    containerFactory = "batchListenerFactory"
)
public void onOrders(
        List<ConsumerRecord<String, OrderEvent>> records,
        Acknowledgment acknowledgment) {

    orderService.persistBatch(records);
    acknowledgment.acknowledge();
}
~~~

Chỉ acknowledge sau khi xử lý nghiệp vụ đã hoàn tất theo contract. Nếu acknowledge trước khi database commit, ứng dụng có thể mất cơ hội xử lý lại record khi gặp sự cố.

### 9.1. Partial batch acknowledgment

Từ Spring Kafka 3.0.10, batch listener có thể xác nhận một phần batch bằng `Acknowledgment.acknowledge(index)` trong các điều kiện hỗ trợ. Cơ chế này yêu cầu `AckMode.MANUAL_IMMEDIATE` và listener phải gọi trên consumer thread. Index xác định record cuối cùng đã xử lý thành công trong batch.

Ví dụ minh họa:

~~~java
@KafkaListener(
    topics = "order-events",
    groupId = "order-batch-service",
    containerFactory = "manualBatchFactory"
)
public void onOrders(
        List<ConsumerRecord<String, OrderEvent>> records,
        Acknowledgment acknowledgment) {

    for (int index = 0; index < records.size(); index++) {
        process(records.get(index));
        acknowledgment.acknowledge(index);
    }
}
~~~

Ví dụ trên chỉ minh họa API; cấu hình factory phải đặt AckMode.MANUAL_IMMEDIATE và tuân thủ điều kiện của phiên bản. Partial acknowledgement có quy tắc index tăng dần và không được gọi tùy tiện từ thread khác. Hãy đọc Javadoc phiên bản đang dùng trước khi áp dụng vì đây là API có yêu cầu chặt.

Nếu không cần xác nhận một phần, xử lý toàn batch rồi gọi acknowledge một lần sẽ đơn giản và ít lỗi hơn.

## 10. Xử lý lỗi trong record listener

Với record listener, lỗi xảy ra trong một lần gọi thường gắn với record cụ thể. Spring Kafka error handler có thể retry record, áp dụng backoff hoặc chuyển record sang dead-letter topic.

Ví dụ cấu hình DefaultErrorHandler với DeadLetterPublishingRecoverer:

~~~java
@Bean
public DefaultErrorHandler kafkaErrorHandler(
        DeadLetterPublishingRecoverer recoverer) {

    return new DefaultErrorHandler(
        recoverer,
        new FixedBackOff(1000L, 2L)
    );
}
~~~

Cấu hình này minh họa retry với khoảng chờ một giây và số lần retry hữu hạn trước khi recoverer xử lý record theo cấu hình. Cần cấu hình DLT destination, producer template và exception classification phù hợp.

Với record listener, error handler có thể seek/redeliver record lỗi hoặc chuyển record sang DLT. Record tiếp theo trong cùng partition thường không được xử lý vượt qua record lỗi khi blocking retry đang giữ tiến độ partition.

Lỗi tạm thời như database timeout có thể retry. Lỗi dữ liệu không hợp lệ thường không tự hết; nên phân loại và chuyển DLT sau số lần thử hợp lý.

## 11. Xử lý lỗi trong batch listener

Batch listener có một khác biệt quan trọng: nếu phương thức ném exception thông thường, container không nhất thiết biết chính xác phần tử nào trong batch thất bại. Tùy error handler và phiên bản, toàn bộ batch có thể được retry hoặc xử lý lại.

Nếu listener xác định được record lỗi, có thể ném `BatchListenerFailedException` với index hoặc ConsumerRecord lỗi. `DefaultErrorHandler` có thể dùng thông tin đó để xử lý các record trước vị trí lỗi như đã thành công và retry/recover record lỗi cùng phần còn lại theo chính sách.

Ví dụ:

~~~java
@KafkaListener(
    topics = "order-events",
    groupId = "order-batch-service",
    containerFactory = "batchListenerFactory"
)
public void onOrders(
        List<ConsumerRecord<String, OrderEvent>> records) {

    for (int index = 0; index < records.size(); index++) {
        ConsumerRecord<String, OrderEvent> record = records.get(index);

        try {
            orderService.handle(record.value());
        }
        catch (Exception exception) {
            throw new BatchListenerFailedException(
                "Không xử lý được order event",
                exception,
                index
            );
        }
    }
}
~~~

Chữ ký constructor và cách error handler xử lý cần đối chiếu phiên bản Spring Kafka. Mục đích của exception là chỉ ra vị trí record lỗi trong batch để container có thể áp dụng tiến độ và retry chính xác hơn.

Nếu batch listener chỉ ném exception chung mà không xác định record lỗi, có thể phải xử lý lại cả batch. Vì vậy, các thao tác nghiệp vụ trong batch nên idempotent hoặc có cơ chế nhận diện event đã xử lý để tránh tác dụng phụ trùng lặp.

### 11.1. Batch retry và DLT

Khi retry hết số lần cho phép, recoverer có thể gửi record lỗi sang DLT. Với batch listener, cần hiểu record nào được recover và record nào được redeliver sau đó. Khi xác định đúng failed index, error handler có thể commit phần trước lỗi và xử lý phần còn lại theo chính sách. Nếu không xác định được vị trí, batch có thể được xem như một đơn vị thất bại.

Không nên mặc định mọi batch luôn được chuyển nguyên vẹn sang một DLT record. Cách recover phụ thuộc exception, batch error handling strategy và cấu hình recoverer. Nếu cần DLT riêng cho từng event, hãy thiết kế và kiểm thử rõ cách tách record.

## 12. Ordering khi xử lý batch

Batch listener không làm mất thứ tự offset trong từng partition, nhưng ứng dụng phải cẩn thận khi xử lý batch có nhiều partition.

Một poll batch có thể chứa:

- Nhiều record liên tiếp từ partition 0.
- Nhiều record liên tiếp từ partition 1.
- Record từ nhiều topic nếu subscription bao gồm nhiều topic.

Kafka không bảo đảm thứ tự giữa các partition. Nếu listener xử lý batch bằng parallel stream hoặc executor, thứ tự hoàn tất còn có thể khác thứ tự mà listener nhận được.

Ví dụ không nên dùng khi cần ordering:

~~~java
records.parallelStream()
    .forEach(record -> orderService.handle(record.value()));
~~~

Cách này có thể chạy các record cùng partition đồng thời và hoàn tất không theo offset. Nếu cần tuần tự theo partition/key, xử lý tuần tự hoặc chia batch theo partition rồi xử lý mỗi partition tuần tự.

Batch processing nên tận dụng bulk operation nhưng không làm mất các ràng buộc thứ tự nghiệp vụ.

## 13. Concurrency và số partition

Concurrency của listener container tạo nhiều consumer trong cùng group. Với batch listener, mỗi consumer poll batch riêng từ các partition được assign.

Nếu topic có sáu partition và factory concurrency là ba, group có thể có ba consumer, mỗi consumer nhận một số partition. Mỗi consumer xử lý batch từ partition được gán cho nó.

Concurrency hữu ích không vượt số partition được gán cho group. Nếu có hai partition nhưng concurrency là tám, chỉ tối đa hai consumer có partition để đọc tại một thời điểm.

Tăng concurrency và tăng batch size là hai cách mở rộng khác nhau:

- Concurrency tăng số consumer có thể xử lý partition song song.
- Batch size tăng số record xử lý trong một lần gọi trên mỗi consumer.

Cả hai đều có thể tăng throughput nhưng cũng tăng tài nguyên và áp lực lên dependency. Hãy đo database connection pool, heap, CPU, network và listener latency trước khi tăng.

## 14. Tối ưu throughput với batch listener

Batch listener có thể tăng throughput khi chi phí cố định cho mỗi lần gọi lớn. Ví dụ thay vì insert từng record, ứng dụng gom nhiều event và dùng JDBC batch hoặc bulk API.

Một số kỹ thuật:

- Dùng bulk insert/update thay vì từng câu lệnh riêng.
- Tối ưu batch size theo payload và giới hạn database.
- Giảm chuyển đổi object không cần thiết.
- Dùng serializer/deserializer phù hợp và tránh payload quá lớn.
- Theo dõi thời gian xử lý batch và số record mỗi batch.
- Giới hạn concurrency để không làm quá tải downstream.
- Chọn commit cadence phù hợp với khả năng replay.

Ví dụ xử lý batch:

~~~java
public void persistBatch(List<ConsumerRecord<String, OrderEvent>> records) {
    List<OrderEvent> events = records.stream()
        .map(ConsumerRecord::value)
        .toList();

    orderRepository.saveAll(events);
}
~~~

Ví dụ dùng `Stream.toList()` yêu cầu Java 16 trở lên. Nếu dự án dùng Java 8/11, có thể dùng `Collectors.toList()`. Ngoài ra, `saveAll` không bảo đảm mọi repository triển khai bulk insert thực sự; cần kiểm tra SQL và transaction thực tế.

Batch size tối ưu phụ thuộc dữ liệu. Batch quá nhỏ không tận dụng được bulk operation; batch quá lớn làm tăng memory, thời gian xử lý và nguy cơ vượt poll interval.

## 15. max.poll.interval.ms và thời gian xử lý batch

Consumer phải tiếp tục gọi poll trong giới hạn `max.poll.interval.ms`. Nếu xử lý một batch quá lâu trước lần poll tiếp theo, consumer có thể bị xem là không tiến triển và rời group, dẫn tới rebalance.

Ví dụ:

- max.poll.records = 500.
- Một record mất trung bình 100 ms.
- Xử lý tuần tự 500 record mất khoảng 50 giây, chưa tính database/network overhead.
- Nếu max.poll.interval.ms là 30 giây, consumer có nguy cơ vượt giới hạn.

Đây chỉ là phép ước lượng; thời gian thực tế phụ thuộc phân phối latency, batch, retry và runtime. Cần đo p95/p99 processing time chứ không chỉ average.

Hướng xử lý:

- Giảm max.poll.records nếu batch quá lớn.
- Tối ưu bulk operation và listener.
- Điều chỉnh max.poll.interval.ms phù hợp nếu tác vụ cần lâu, đồng thời đánh giá ảnh hưởng membership.
- Chia công việc thành các bước có thể hoàn tất trong giới hạn poll.
- Tránh retry/backoff dài ngay trong luồng listener mà không tính vào poll interval.

Tăng max.poll.interval.ms không làm xử lý nhanh hơn; nó chỉ tăng thời gian consumer được phép giữa các lần poll trước khi bị xem là không tiến triển.

## 16. Khi nào chọn record listener, khi nào chọn batch listener?

| Yêu cầu | Lựa chọn gợi ý | Lý do |
| --- | --- | --- |
| Xử lý từng event độc lập | Record listener | Dễ hiểu, retry và quan sát theo record. |
| Gọi nghiệp vụ cần latency thấp | Record listener | Không cần gom nhiều record mới xử lý. |
| Bulk insert/update | Batch listener | Tận dụng batch API của database. |
| Xử lý dữ liệu theo cửa sổ/lô | Batch listener | Một lần gọi có thể xử lý tập record. |
| Poison record cần cô lập rõ | Record listener hoặc batch có failed-index handling | Dễ xác định và recover record lỗi. |
| Nhiều event nhỏ, throughput cao | Có thể dùng batch listener | Giảm overhead mỗi lần gọi nếu downstream hỗ trợ bulk. |
| Cần metadata Kafka chi tiết | Cả hai | Record listener nhận ConsumerRecord; batch nhận List<ConsumerRecord>. |

Không nên chọn batch chỉ vì muốn tăng throughput. Nếu downstream không hỗ trợ bulk hoặc xử lý batch làm tăng latency và memory, record listener có thể phù hợp hơn.

Một ứng dụng có thể dùng nhiều container factory: record factory cho luồng nghiệp vụ cần xử lý từng event và batch factory cho luồng analytics/import. Tách factory giúp chính sách ack, concurrency và converter rõ ràng.

## 17. Kiểm thử record listener và batch listener

Integration test với Embedded Kafka hoặc Testcontainers giúp xác nhận container factory, listener signature, conversion, offset và error handling hoạt động như dự kiến.

### 17.1. Kiểm thử record listener

- Gửi nhiều record vào topic.
- Xác nhận listener được gọi theo từng record.
- Kiểm tra payload và metadata.
- Kiểm tra exception/retry theo record.
- Kiểm tra offset commit theo AckMode.

### 17.2. Kiểm thử batch listener

- Cấu hình factory với `setBatchListener(true)`.
- Gửi nhiều record trước khi poll.
- Xác nhận listener nhận list có nhiều phần tử khi điều kiện poll cho phép.
- Kiểm tra record từ nhiều partition và thứ tự trong từng partition.
- Kiểm tra batch nhỏ hơn max.poll.records.
- Kiểm tra failed index, retry và DLT.
- Kiểm tra acknowledgment và commit khi batch thành công/thất bại.

Không nên khẳng định một số lượng record cố định sẽ luôn nằm trong một batch. Poll có thể trả ít hơn giới hạn do thời điểm dữ liệu đến, partition assignment, fetch và các giới hạn byte.

Test nên dùng latch hoặc Awaitility với timeout hữu hạn. Để xác nhận một batch cụ thể, kiểm soát producer gửi trước khi poll và cấu hình consumer test phù hợp; tránh sleep cố định vì kết quả phụ thuộc scheduler và broker.

### 17.3. Kiểm thử hiệu năng

Benchmark record và batch listener trên cùng dữ liệu, partition count, consumer count và dependency. Đo:

- Records per second.
- Batch size trung bình và phân vị.
- Listener processing latency p50/p95/p99.
- Consumer lag.
- CPU, heap, GC và network.
- Database throughput và connection usage.
- Retry/error/DLT rate.

So sánh end-to-end throughput và latency. Một batch listener có throughput cao hơn nhưng p99 latency quá lớn có thể không đáp ứng SLA.

## 18. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Listener nhận từng record dù muốn batch | Factory chưa bật batch listener hoặc listener dùng nhầm factory | Kiểm tra setBatchListener(true) và containerFactory |
| Batch listener không convert được payload list | Chữ ký method/converter không phù hợp | Kiểm tra BatchMessageConverter và generic type |
| Batch luôn nhỏ hơn max.poll.records | Poll không đảm bảo trả đủ giới hạn | Kiểm tra producer rate, partition, fetch và thời điểm poll |
| Batch xử lý quá lâu rồi rebalance | Vượt max.poll.interval.ms | Đo processing time, giảm batch hoặc điều chỉnh interval |
| Retry làm xử lý lại nhiều record | Batch exception không xác định failed index | Dùng BatchListenerFailedException khi xác định được record lỗi |
| Commit offset trước khi xử lý xong | Acknowledge/commit gọi quá sớm | Chỉ xác nhận sau khi tác vụ bền vững hoàn tất |
| Record trong cùng partition hoàn tất sai thứ tự | Dùng parallel stream/executor | Xử lý tuần tự hoặc phân luồng theo partition/key |
| Tăng batch size nhưng throughput không tăng | Bottleneck nằm ở downstream hoặc network | Đo từng tầng, thử bulk API và kiểm tra dependency |
| DLT chứa dữ liệu không như mong đợi | Batch recovery semantics chưa được kiểm thử | Kiểm tra failed index, recoverer và handler |
| Consumer thường xuyên rebalance | Xử lý batch lâu, restart hoặc poll interval | Kiểm tra max.poll.interval.ms và lifecycle container |

## 19. Checklist chọn và vận hành listener mode

Trước khi đưa listener vào production, hãy xác nhận:

1. Chế độ record hay batch phù hợp với yêu cầu latency và throughput.
2. Listener đang dùng đúng container factory.
3. Batch listener đã bật `setBatchListener(true)`.
4. Chữ ký method phù hợp với payload, ConsumerRecord hoặc Message converter.
5. `max.poll.records` và fetch size được chọn theo payload/partition.
6. AckMode phù hợp với record hoặc batch semantics.
7. Acknowledge chỉ sau khi tác vụ nghiệp vụ hoàn tất bền vững.
8. Batch error handling xác định được failed record khi cần partial recovery.
9. Retry/DLT không làm mất hoặc xử lý sai thứ tự nghiệp vụ.
10. Processing time không vượt `max.poll.interval.ms`.
11. Concurrency không vượt quá nhu cầu và năng lực downstream.
12. Có integration test và benchmark đo throughput, latency, lag, retry và DLT.

Record listener và batch listener cùng dùng Kafka consumer nhưng tạo hai mô hình xử lý khác nhau. Record listener đơn giản khi cần xử lý từng event và cô lập lỗi; batch listener tận dụng bulk operation để tăng throughput khi downstream hỗ trợ. Lựa chọn đúng cần cân bằng latency, memory, commit semantics, retry, ordering và giới hạn thời gian poll để consumer group hoạt động ổn định.

