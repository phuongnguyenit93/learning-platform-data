# Bật batchListener trên container factory

Spring Kafka mặc định thường cấu hình listener theo kiểu nhận từng record. Khi bật batch listener, một lần gọi poll() của Kafka consumer có thể được chuyển thành một lần gọi listener với nhiều record. Cách này giảm overhead gọi method và phù hợp khi ứng dụng có thể xử lý một nhóm sự kiện cùng lúc, ví dụ ghi nhiều dòng database, gọi bulk API hoặc tổng hợp dữ liệu.

Trong Spring Kafka, batch mode được bật ở listener container factory. Factory tạo container và consumer cho các endpoint @KafkaListener sử dụng nó. Khi factory được cấu hình batch, listener method phải có chữ ký tương thích với dữ liệu theo lô, chẳng hạn List<OrderEvent> hoặc List<ConsumerRecord<...>>.

Batch listener không tự động làm nghiệp vụ nhanh hơn. Ứng dụng vẫn phải chọn kích thước poll phù hợp, xử lý lỗi trong batch, quản lý offset và bảo đảm record được xử lý đúng thứ tự trong từng partition. Một batch lớn có thể tăng throughput nhưng cũng tăng bộ nhớ, thời gian xử lý một lần poll và phạm vi record bị giao lại khi lỗi.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích batch listener nhận dữ liệu theo từng lần poll như thế nào.
- Bật batch mode bằng setBatchListener(true) trên ConcurrentKafkaListenerContainerFactory.
- Cấu hình batch listener bằng Spring Boot properties.
- Viết @KafkaListener nhận List payload, List<ConsumerRecord> hoặc ConsumerRecords.
- Chọn giữa record listener và batch listener theo đặc điểm nghiệp vụ.
- Điều chỉnh max.poll.records, fetch settings, concurrency và max.poll.interval.ms.
- Hiểu AckMode.BATCH, MANUAL và cách commit offset sau khi xử lý batch.
- Xử lý lỗi toàn batch và lỗi tại một record cụ thể.
- Giữ ordering theo partition khi batch chứa record từ nhiều partition.
- Kiểm thử batch conversion, partial failure, rebalance và throughput.

## 1. Batch listener hoạt động như thế nào?

Kafka consumer gọi poll() để lấy record từ các partition đang được assign. Kết quả của một lần poll là một tập ConsumerRecord, có thể chứa record từ nhiều partition. Khi listener container chạy ở batch mode, Spring Kafka chuyển tập record đó thành đầu vào của một lần gọi listener.

Luồng xử lý:

~~~text
Kafka topic
  Partition 0: P0-R1, P0-R2, P0-R3
  Partition 1: P1-R1, P1-R2
  Partition 2: P2-R1
          |
          v
KafkaConsumer.poll()
          |
          v
ConsumerRecords (một poll)
          |
          v
Batch listener container
          |
          v
@KafkaListener(List<Record> batch)
          |
          v
Xử lý batch / ghi bulk / commit offset
~~~

Ví dụ topic orders có ba partition. Một poll có thể trả về ba record từ partition 0, hai record từ partition 1 và một record từ partition 2. Listener nhận sáu record trong một lần gọi, nếu chúng nằm trong kết quả poll đó.

Batch không nhất thiết có đúng số lượng record mà ứng dụng mong muốn. Poll có thể trả về ít record hơn giới hạn cấu hình nếu dữ liệu chưa có sẵn, fetch chưa đủ điều kiện hoặc các giới hạn fetch/poll khác đang áp dụng.

### Batch listener khác producer batching

Hai cơ chế này thường bị nhầm:

| Cơ chế | Phía hoạt động | Mục đích |
|---|---|---|
| Producer batching | Producer | Gom record trước khi gửi broker, giảm số request |
| Consumer batch listener | Consumer/Spring listener container | Đưa nhiều record của một poll vào một lần gọi listener |
| Database batch write | Ứng dụng và database | Gộp nhiều thao tác ghi để giảm round trip |

Producer có thể gom record thành batch ngay cả khi consumer xử lý từng record. Consumer có thể nhận batch dù producer không có cấu hình batching đặc biệt. Đây là ba tầng tối ưu riêng biệt.

## 2. Bật batchListener bằng container factory

Cách phổ biến nhất là tạo một ConcurrentKafkaListenerContainerFactory riêng và gọi setBatchListener(true).

Ví dụ:

~~~java
@Configuration
public class KafkaListenerConfiguration {

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
            batchKafkaListenerContainerFactory(
                    ConsumerFactory<String, OrderEvent> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

        factory.setConsumerFactory(consumerFactory);

        // Bật batch listener cho các endpoint sử dụng factory này.
        factory.setBatchListener(true);

        // Tạo ba consumer con trong cùng listener container.
        factory.setConcurrency(3);

        // Commit offset của batch sau khi listener xử lý thành công.
        factory.getContainerProperties().setAckMode(
                ContainerProperties.AckMode.BATCH
        );

        return factory;
    }
}
~~~

Các điểm quan trọng:

- setConsumerFactory() cung cấp cấu hình bootstrap server, deserializer và consumer properties.
- setBatchListener(true) yêu cầu container gọi listener theo batch.
- setConcurrency(3) tạo tối đa ba consumer con cho endpoint.
- AckMode.BATCH commit tiến độ của các record trong poll sau khi listener xử lý thành công.

AckMode.BATCH là lựa chọn thông dụng cho batch listener. AckMode.RECORD không phù hợp với batch listener vì listener xử lý cả tập record trong một lần gọi, không trả kết quả thành công riêng cho từng lần gọi method.

### Gắn factory vào @KafkaListener

Listener cần tham chiếu đúng tên factory:

~~~java
@Component
public class OrderBatchListener {

    @KafkaListener(
        id = "orders-batch-listener",
        topics = "orders",
        groupId = "order-batch-service",
        containerFactory = "batchKafkaListenerContainerFactory"
    )
    public void onOrders(List<OrderEvent> events) {
        orderService.processBatch(events);
    }
}
~~~

Nếu không khai báo containerFactory, Spring Kafka dùng factory mặc định có tên kafkaListenerContainerFactory. Vì vậy, chỉ tạo một factory batch không có nghĩa mọi listener tự động dùng nó; endpoint phải tham chiếu đúng factory hoặc ứng dụng phải cấu hình factory mặc định ở chế độ batch.

Một ứng dụng có thể có cả record listener và batch listener. Nên tạo hai factory riêng để mỗi endpoint có chữ ký và hành vi phù hợp.

## 3. Bật batch mode bằng Spring Boot configuration

Nếu dùng factory tự động cấu hình của Spring Boot, có thể chọn loại listener bằng property:

~~~yaml
spring:
  kafka:
    listener:
      type: batch
      ack-mode: batch
      concurrency: 3
    consumer:
      max-poll-records: 200
~~~

Ý nghĩa:

- listener.type=batch: cấu hình listener container factory tự động của Boot ở batch mode.
- listener.ack-mode=batch: commit offset theo batch sau khi listener xử lý thành công.
- listener.concurrency=3: tạo ba consumer con cho listener container.
- consumer.max-poll-records=200: giới hạn tối đa số record consumer trả về trong một lần poll.

Đây là cấu hình cho factory tự động của Spring Boot. Nếu ứng dụng tự tạo factory mới mà không dùng Boot configurer, các property trên có thể không được áp dụng tự động cho factory đó. Trong trường hợp custom factory, hãy cấu hình trực tiếp bằng setBatchListener(true), setConcurrency() và ContainerProperties.

### Chỉ bật batch cho listener cần batch

Nếu ứng dụng có cả listener nhận từng record và listener nhận batch, không nên đổi factory mặc định sang batch rồi để các method cũ giữ chữ ký một record.

Ví dụ cấu trúc:

~~~text
recordKafkaListenerContainerFactory
    -> @KafkaListener nhận OrderEvent

batchKafkaListenerContainerFactory
    -> @KafkaListener nhận List<OrderEvent>
~~~

Mỗi listener chỉ định containerFactory phù hợp. Điều này giúp tránh lỗi adapter do chữ ký method không tương thích với loại listener container.

## 4. Các kiểu tham số được hỗ trợ cho batch listener

Batch listener có thể nhận payload đã chuyển đổi hoặc record Kafka gốc. Chọn kiểu tham số dựa trên nhu cầu metadata.

### Nhận List payload

Nếu chỉ cần dữ liệu nghiệp vụ, nhận List<OrderEvent> là cách đơn giản:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "order-batch-service",
    containerFactory = "batchKafkaListenerContainerFactory"
)
public void onOrders(List<OrderEvent> events) {
    orderService.processBatch(events);
}
~~~

Container chuyển đổi value của từng record thành OrderEvent trước khi gọi listener. Cách này phù hợp khi không cần offset, partition hoặc native headers cho từng record.

### Nhận List<ConsumerRecord>

Nếu cần metadata từng record, nhận ConsumerRecord:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "order-audit-service",
    containerFactory = "batchKafkaListenerContainerFactory"
)
public void onOrders(
        List<ConsumerRecord<String, OrderEvent>> records) {

    for (ConsumerRecord<String, OrderEvent> record : records) {
        log.info(
            "topic={}, partition={}, offset={}, key={}",
            record.topic(),
            record.partition(),
            record.offset(),
            record.key()
        );

        orderService.process(record.value());
    }
}
~~~

Mỗi phần tử giữ topic, partition, offset, key, timestamp, headers và value đã deserialize. Đây là lựa chọn hữu ích cho audit, xử lý theo partition hoặc batch cần quản lý offset chi tiết.

### Nhận ConsumerRecords

Batch listener cũng có thể nhận ConsumerRecords trực tiếp:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "order-raw-batch-service",
    containerFactory = "batchKafkaListenerContainerFactory"
)
public void onOrders(
        ConsumerRecords<String, OrderEvent> records) {

    for (TopicPartition partition : records.partitions()) {
        List<ConsumerRecord<String, OrderEvent>> partitionRecords =
                records.records(partition);

        orderService.processPartitionBatch(partition, partitionRecords);
    }
}
~~~

ConsumerRecords giúp truy cập record theo từng TopicPartition. Cách này phù hợp khi logic cần nhóm theo partition và giữ metadata gốc.

### Nhận Spring Message theo batch

Nếu muốn dùng Spring Message headers, có thể cấu hình BatchMessagingMessageConverter và nhận danh sách Message hoặc payload list tùy kiểu converter và method signature.

~~~java
@Bean
public BatchMessagingMessageConverter batchMessageConverter() {
    return new BatchMessagingMessageConverter();
}
~~~

Gắn converter vào factory:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, String>
        jsonBatchListenerFactory(
                ConsumerFactory<String, String> consumerFactory,
                BatchMessagingMessageConverter batchMessageConverter) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, String>();

    factory.setConsumerFactory(consumerFactory);
    factory.setBatchListener(true);
    factory.setBatchMessageConverter(batchMessageConverter);

    return factory;
}
~~~

Khi cần metadata theo từng record, kiểm tra các header batch mà converter cung cấp, ví dụ KafkaHeaders.BATCH_CONVERTED_HEADERS. Không giả định một header đơn của Spring Message đại diện chính xác cho toàn bộ metadata của mọi record trong batch.

Với các use case cần native headers, header trùng tên hoặc offset chính xác từng record, List<ConsumerRecord<...>> thường dễ kiểm soát hơn.

## 5. Xử lý header trong batch listener

Trong record listener, các header như received topic, partition, key và offset thường là một giá trị. Trong batch listener, các header tương ứng có thể là danh sách giá trị theo thứ tự record.

Ví dụ:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "order-batch-service",
    containerFactory = "batchKafkaListenerContainerFactory"
)
public void onOrders(
        @Payload List<OrderEvent> events,
        @Header(KafkaHeaders.RECEIVED_KEY) List<String> keys,
        @Header(KafkaHeaders.RECEIVED_PARTITION) List<Integer> partitions,
        @Header(KafkaHeaders.OFFSET) List<Long> offsets) {

    for (int i = 0; i < events.size(); i++) {
        orderService.process(
                events.get(i),
                keys.get(i),
                partitions.get(i),
                offsets.get(i)
        );
    }
}
~~~

Các danh sách metadata phải được ghép theo đúng vị trí với danh sách payload do converter tạo. Nếu cần kiểm soát chắc chắn hơn, nhận List<ConsumerRecord> để tránh tự đồng bộ nhiều list song song.

Header có thể null nếu record không có key hoặc producer không gửi custom header. Với các header tùy chọn, hãy dùng kiểu nullable hoặc kiểm tra giá trị trước khi xử lý.

## 6. Điều chỉnh kích thước batch bằng max.poll.records

max.poll.records là giới hạn số record tối đa mà Kafka consumer trả về trong một lần poll. Nó là tham số quan trọng khi bật batch listener.

Ví dụ:

~~~yaml
spring:
  kafka:
    consumer:
      max-poll-records: 200
~~~

Nếu có đủ dữ liệu và các giới hạn fetch cho phép, một lần poll có thể trả về tối đa 200 record. Consumer không cam kết luôn trả về đúng 200 record.

Các yếu tố ảnh hưởng batch thực tế:

- Số record đang có sẵn trên các partition được assign.
- max.poll.records.
- fetch.min.bytes và fetch.max.wait.ms.
- fetch.max.bytes và max.partition.fetch.bytes.
- Kích thước trung bình của record.
- Tốc độ producer và trạng thái broker.

### Fetch properties và max.poll.records khác nhau

| Property | Vai trò |
|---|---|
| max.poll.records | Giới hạn số record trả về cho ứng dụng trong một poll |
| fetch.min.bytes | Lượng dữ liệu tối thiểu consumer muốn broker gom trước khi trả fetch, nếu có thể |
| fetch.max.wait.ms | Thời gian broker chờ để đạt fetch.min.bytes trước khi trả response |
| fetch.max.bytes | Giới hạn tổng dữ liệu fetch response mà consumer mong muốn nhận |
| max.partition.fetch.bytes | Giới hạn dữ liệu fetch cho mỗi partition trong một response |

fetch properties tác động đến lượng byte và thời điểm broker trả dữ liệu. max.poll.records giới hạn số record mà poll trả về cho ứng dụng. Không dùng chúng thay thế cho nhau.

Ví dụ cấu hình bắt đầu:

~~~yaml
spring:
  kafka:
    consumer:
      max-poll-records: 200
      properties:
        "[fetch.min.bytes]": 16384
        "[fetch.max.wait.ms]": 100
        "[max.partition.fetch.bytes]": 1048576
~~~

Các giá trị cần được điều chỉnh theo kích thước message, throughput, latency và bộ nhớ. Nếu record lớn, một batch nhỏ về số lượng vẫn có thể chiếm nhiều bộ nhớ.

## 7. Concurrency và số partition

Concurrency tạo nhiều consumer con trong một listener container. Mỗi consumer được Kafka group assignor gán một hoặc nhiều partition.

Ví dụ topic orders có sáu partition và concurrency bằng ba:

~~~text
orders:
P0  P1  P2  P3  P4  P5

Consumer 1: P0, P1
Consumer 2: P2, P3
Consumer 3: P4, P5
~~~

Mỗi consumer poll và gọi listener riêng. Do đó, trong cùng một ứng dụng có thể có ba batch listener invocation đồng thời, mỗi invocation xử lý batch của consumer tương ứng.

Nguyên tắc:

- Số consumer con có thể hoạt động hữu ích với một topic không vượt quá số partition của topic đó.
- Nếu concurrency lớn hơn partition count, một số consumer không có partition.
- Nếu concurrency nhỏ hơn partition count, một consumer có thể đọc nhiều partition.
- Tổng số consumer member của group cần tính cả số replica ứng dụng nhân concurrency của mỗi replica.
- Concurrency không tạo thêm partition và không bảo đảm throughput tăng tuyến tính.

Nếu batch listener xử lý database bulk write, concurrency nên được chọn theo connection pool và năng lực database. Tạo nhiều consumer hơn khả năng downstream chỉ làm tăng hàng đợi, lock contention và thời gian xử lý.

## 8. Batch listener và ordering

Một batch có thể chứa record từ nhiều partition. Kafka chỉ bảo đảm thứ tự offset trong từng partition; không có thứ tự toàn cục giữa các partition.

Ví dụ:

~~~text
Batch từ một poll:

Partition 0: offset 10, 11, 12
Partition 1: offset 20, 21
Partition 2: offset 30

Không có thứ tự toàn cục:
P0-10 < P0-11 < P0-12
P1-20 < P1-21
P2-30 độc lập với hai partition kia
~~~

Nếu listener nhận List<OrderEvent>, không nên suy ra thứ tự giữa hai sự kiện ở hai partition từ vị trí trong list. Nếu nghiệp vụ yêu cầu xử lý theo partition, hãy nhóm record theo TopicPartition và xử lý từng nhóm theo offset.

Ví dụ:

~~~java
public void processPartitionBatch(
        TopicPartition partition,
        List<ConsumerRecord<String, OrderEvent>> records) {

    records.stream()
            .sorted(Comparator.comparingLong(ConsumerRecord::offset))
            .forEach(record ->
                    orderService.process(record.value()));
}
~~~

Trong cùng một poll, ConsumerRecords đã giữ các record theo partition; ví dụ sort thể hiện rõ yêu cầu xử lý theo offset. Nếu xử lý nhiều partition song song, mỗi partition cần một luồng xử lý tuần tự riêng.

Không gửi từng record trong batch sang executor nhiều thread nếu side effect của cùng partition phải giữ thứ tự. Batch listener giảm overhead invocation nhưng không tự bảo đảm thứ tự hoàn tất của công việc bất đồng bộ do ứng dụng tạo ra.

## 9. AckMode và commit offset cho batch listener

Với batch listener, listener xử lý cả tập record từ một poll. AckMode cần phản ánh ranh giới xác nhận của batch.

| AckMode | Ý nghĩa với batch listener |
|---|---|
| BATCH | Commit offset sau khi listener xử lý thành công toàn bộ batch |
| MANUAL | Listener gọi acknowledge(); container quản lý commit theo ranh giới batch/poll |
| MANUAL_IMMEDIATE | Cố gắng commit ngay khi acknowledge trên consumer thread |
| RECORD | Không phù hợp với batch listener |

Ví dụ cấu hình BATCH:

~~~java
factory.getContainerProperties().setAckMode(
        ContainerProperties.AckMode.BATCH
);
~~~

Với BATCH, nếu listener trả về bình thường, container có thể commit tiến độ của các record đã trả về trong poll. Nếu listener ném exception, error handler quyết định retry/recover và commit theo chính sách tương ứng.

Không bật Kafka auto commit cùng lúc với logic manual acknowledgement nếu không có lý do rõ ràng. Spring Kafka listener container thường quản lý commit và mặc định tắt auto commit trong cấu hình do container tạo.

### Manual acknowledgement cho batch

Có thể nhận Acknowledgment:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "order-batch-service",
    containerFactory = "manualBatchFactory"
)
public void onOrders(
        List<OrderEvent> events,
        Acknowledgment acknowledgment) {

    orderService.processBatch(events);

    // Xác nhận batch sau khi mọi record đã xử lý thành công.
    acknowledgment.acknowledge();
}
~~~

Factory dùng MANUAL:

~~~java
factory.setBatchListener(true);
factory.getContainerProperties().setAckMode(
        ContainerProperties.AckMode.MANUAL
);
~~~

Chỉ gọi acknowledge() sau khi toàn bộ công việc cần thiết hoàn tất. Nếu một phần batch đã ghi database nhưng phần còn lại lỗi, cả batch có thể được giao lại. Handler cần idempotent để không tạo side effect trùng.

## 10. Xử lý lỗi toàn batch

Nếu batch listener ném exception thông thường, container không biết chắc record nào trong batch đã xử lý thành công. Error handler có thể retry toàn batch theo cấu hình.

Ví dụ:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "order-batch-service",
    containerFactory = "batchKafkaListenerContainerFactory"
)
public void onOrders(List<OrderEvent> events) {
    orderService.processBatch(events);
}
~~~

Nếu processBatch() cập nhật thành công 80 record rồi lỗi ở record thứ 81, lần retry có thể chạy lại cả batch. Vì vậy:

- Các thao tác cần idempotent theo eventId.
- Database có thể dùng unique constraint hoặc inbox table.
- Không commit offset trước khi chính sách lỗi/recover đã hoàn tất.
- Theo dõi số lần retry và batch bị giao lại.

Một lỗi batch không nhất thiết đồng nghĩa mọi record đều chưa được xử lý. Có thể đã có side effect ở một phần batch trước khi exception xảy ra.

## 11. Xác định record lỗi bằng BatchListenerFailedException

Nếu listener biết index của record lỗi trong batch, có thể ném BatchListenerFailedException để báo cho DefaultErrorHandler biết vị trí lỗi. Error handler có thể xử lý các record trước đó như đã hoàn tất, retry/recover record lỗi và tiếp tục theo chiến lược được cấu hình.

Ví dụ:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "order-batch-service",
    containerFactory = "batchKafkaListenerContainerFactory"
)
public void onOrders(List<ConsumerRecord<String, OrderEvent>> records) {
    for (int i = 0; i < records.size(); i++) {
        ConsumerRecord<String, OrderEvent> record = records.get(i);

        try {
            orderService.processIdempotently(record.value());
        } catch (Exception ex) {
            throw new BatchListenerFailedException(
                    "Cannot process record at batch index " + i,
                    ex,
                    i
            );
        }
    }
}
~~~

Cấu hình error handler với retry backoff:

~~~java
@Bean
public DefaultErrorHandler batchErrorHandler() {
    return new DefaultErrorHandler(
            new FixedBackOff(1000L, 2L)
    );
}
~~~

Gắn vào factory:

~~~java
// Inject DefaultErrorHandler bean vào phương thức tạo factory.
factory.setCommonErrorHandler(batchErrorHandler);
~~~

Ví dụ trên minh họa retry có giới hạn. Khi hết retry, hành vi recover phụ thuộc recoverer được cấu hình. Trong production, hãy định nghĩa rõ record lỗi sẽ được gửi DLT, ghi vào kho lỗi hay dừng xử lý để can thiệp. Đừng mặc định rằng retry exhaustion tự động gửi record sang DLT nếu chưa cấu hình recoverer phù hợp.

Constructor và hành vi chi tiết của BatchListenerFailedException/DefaultErrorHandler cần đối chiếu phiên bản Spring Kafka. Cơ chế này đặc biệt hữu ích khi muốn xử lý partial batch mà không retry toàn bộ record đã hoàn tất.

## 12. Batch listener và dead-letter topic

Có thể kết hợp DefaultErrorHandler với DeadLetterPublishingRecoverer để chuyển record lỗi sau khi hết retry. Ví dụ cấu hình khái quát:

~~~java
@Bean
public DefaultErrorHandler batchDltErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(kafkaTemplate);

    return new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(1000L, 2L)
    );
}
~~~

Gắn vào factory:

~~~java
factory.setCommonErrorHandler(batchDltErrorHandler);
~~~

Với batch listener, nếu exception chỉ rõ index record lỗi bằng BatchListenerFailedException, error handler có thể recover record đó và tiếp tục với phần còn lại theo chính sách. Nếu không xác định được record lỗi, cả batch có thể bị retry.

Với resolver mặc định, record thường được gửi đến topic có hậu tố .DLT và giữ số partition nguồn. Vì vậy, topic DLT cần có đủ partition tương ứng; nếu muốn route sang topic hoặc partition khác, cấu hình destination resolver tường minh. DLT cũng cần serializer phù hợp với key/value và headers. Khi recoverer publish DLT, cần bảo đảm việc publish thành công trước khi offset của record gốc được xác nhận theo chính sách error handler. Hãy kiểm thử lỗi DLT publish và cách xử lý khi broker DLT không khả dụng.

Đưa record vào DLT là một quyết định nghiệp vụ: record đã được cách ly để xử lý sau, không có nghĩa business operation thành công. Cần giám sát DLT và quy trình replay.

## 13. max.poll.interval.ms và thời gian xử lý batch

Consumer cần tiếp tục gọi poll() trong giới hạn max.poll.interval.ms. Nếu listener xử lý batch quá lâu, consumer có thể vượt khoảng thời gian này, bị xem là không còn tiến triển và rời group, dẫn đến rebalance.

Ví dụ:

~~~text
max.poll.interval.ms = 300000 (5 phút)
Batch có 200 record
Thời gian xử lý trung bình = 2 giây/record
Tổng thời gian tuần tự ước tính = 400 giây

Kết quả:
  Xử lý batch vượt 5 phút
  Consumer có thể rời group
  Rebalance và record có thể được giao lại
~~~

Đây là phép tính minh họa; thời gian thực tế phụ thuộc phân bố latency, batch operation và xử lý song song. Nếu một batch có thời gian xử lý quá dài, cân nhắc:

- Giảm max.poll.records để giảm lượng công việc mỗi poll.
- Tối ưu bulk operation để giảm thời gian xử lý từng batch.
- Tăng max.poll.interval.ms nếu thời gian xử lý dài là yêu cầu có chủ đích.
- Dùng concurrency giữa các partition.
- Chia batch nghiệp vụ thành các chunk nhỏ nhưng chỉ commit khi offset an toàn.
- Không offload tùy tiện sang executor nếu chưa quản lý acknowledgement và ordering.

Tăng max.poll.interval.ms không làm hệ thống nhanh hơn; nó chỉ tăng thời gian consumer được phép xử lý giữa các lần poll. Hãy theo dõi rebalance, lag và thời gian listener thực tế.

## 14. Bộ nhớ và backpressure

Batch lớn có thể chiếm nhiều heap vì consumer giữ nhiều record, payload đã deserialize và các cấu trúc tạm thời khi xử lý. Nếu payload lớn hoặc listener tạo thêm bản sao object, mức sử dụng bộ nhớ tăng đáng kể.

Cần cân nhắc:

- max.poll.records.
- Kích thước trung bình và phân bố kích thước message.
- Số partition được assign cho mỗi consumer.
- Concurrency và số batch có thể xử lý đồng thời.
- Dữ liệu tạm khi chuyển đổi JSON hoặc gom batch database.
- Connection pool và giới hạn đồng thời của downstream.

Một ước lượng đơn giản:

~~~text
Memory cho batch
  ~= số record trong batch
     x kích thước object trung bình sau deserialize
     x hệ số overhead của object/collection
~~~

Đây chỉ là ước lượng định hướng; heap thực tế còn phụ thuộc JVM object layout, serializer, payload, header và bản sao dữ liệu.

Nếu batch lớn làm heap tăng hoặc GC pause kéo dài, giảm max.poll.records, giới hạn concurrency hoặc xử lý theo chunk. Đừng gom toàn bộ record vào một danh sách dài hạn trong service.

## 15. Batch listener và database bulk operation

Một lợi ích thực tế của batch listener là gom nhiều record để ghi database theo lô.

Ví dụ:

~~~java
@Service
public class OrderBatchService {

    private final OrderRepository repository;

    public void processBatch(List<OrderEvent> events) {
        List<OrderEntity> entities = events.stream()
                .map(this::toEntity)
                .toList();

        repository.saveAll(entities);
    }

    private OrderEntity toEntity(OrderEvent event) {
        return new OrderEntity(
                event.orderId(),
                event.status(),
                event.version()
        );
    }
}
~~~

Bulk operation có thể giảm round trip và tăng throughput. Tuy nhiên, saveAll() không phải lúc nào cũng tạo một câu SQL bulk duy nhất; hành vi phụ thuộc JPA provider, JDBC batching, mapping và transaction.

Để đạt hiệu quả database batch thực sự, cần cân nhắc:

- JDBC batch size.
- Transaction boundary.
- Flush/clear persistence context khi batch lớn.
- Unique constraint cho eventId.
- Xử lý duplicate khi Kafka giao lại batch.
- Partial failure và rollback toàn transaction.

Nếu toàn bộ batch được ghi trong một database transaction và transaction rollback, không có record nào trong transaction được commit. Nếu xử lý từng record với transaction riêng, một phần batch có thể đã thành công trước khi record sau lỗi. Hai cách có ranh giới retry khác nhau.

### Ví dụ transaction theo batch

~~~java
@Transactional
public void processBatch(List<OrderEvent> events) {
    for (OrderEvent event : events) {
        processIdempotently(event);
    }
}
~~~

Khi exception thoát khỏi phương thức và transaction rollback, các cập nhật trong transaction đó được rollback theo cấu hình transaction manager. Kafka offset chỉ được commit sau khi listener hoàn tất theo AckMode đã chọn; database và Kafka offset vẫn là hai hệ thống riêng nếu không dùng cơ chế phối hợp phù hợp.

## 16. Batch conversion và kiểu payload

Nếu consumer deserializer đã tạo object, batch listener có thể nhận List<OrderEvent>. Nếu deserializer trả về String, converter cần chuyển từng payload thành kiểu mong muốn.

Các lựa chọn thường gặp:

| Deserializer | Listener | Cách chuyển đổi |
|---|---|---|
| JsonDeserializer<OrderEvent> | List<OrderEvent> | Deserializer tạo object; batch converter đóng gói danh sách |
| StringDeserializer | List<OrderEvent> | Cần JSON message converter phù hợp cho từng record |
| StringDeserializer | List<String> | Nhận raw JSON String và parse trong service |
| ByteArrayDeserializer | List<byte[]> | Ứng dụng tự xử lý byte hoặc dùng converter tương ứng |
| Deserializer bất kỳ | List<ConsumerRecord<K,V>> | Giữ record metadata và value đã deserialize |

Khi dùng StringJsonMessageConverter hoặc converter tùy chỉnh, hãy cấu hình batch converter phù hợp. BatchMessagingMessageConverter có thể delegate việc chuyển từng record cho RecordMessageConverter.

Ví dụ:

~~~java
@Bean
public BatchMessagingMessageConverter batchJsonConverter() {
    return new BatchMessagingMessageConverter(
            new StringJsonMessageConverter()
    );
}
~~~

Gắn vào factory bằng setBatchMessageConverter(). Kiểm tra constructor/API theo version Spring Kafka đang dùng; nếu converter không cần JSON conversion, BatchMessagingMessageConverter mặc định có thể đủ.

Không cấu hình JsonDeserializer và StringJsonMessageConverter cùng chuyển đổi một payload path. Chọn một điểm chịu trách nhiệm parse JSON để tránh chuyển đổi hai lần hoặc lỗi kiểu dữ liệu.

## 17. Trộn record listener và batch listener trong một ứng dụng

Một service có thể cần một listener nhận từng record và listener khác nhận batch. Tạo hai factory riêng:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        recordListenerFactory(
                ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setBatchListener(false);
    factory.setConcurrency(2);

    return factory;
}

@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        batchListenerFactory(
                ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setBatchListener(true);
    factory.setConcurrency(3);

    return factory;
}
~~~

Hai listener chọn factory:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "order-notification",
    containerFactory = "recordListenerFactory"
)
public void notifyOne(OrderEvent event) {
    notificationService.send(event);
}

@KafkaListener(
    topics = "orders",
    groupId = "order-analytics",
    containerFactory = "batchListenerFactory"
)
public void aggregate(List<OrderEvent> events) {
    analyticsService.aggregate(events);
}
~~~

Hai listener trên dùng group ID khác nhau nên mỗi group đọc độc lập toàn bộ topic. Nếu cùng group ID và cùng subscribe topic, hai endpoint sẽ chia partition với nhau; hãy chọn group ID theo mục tiêu xử lý.

Nếu dùng Spring Boot global property listener.type=batch, factory mặc định có thể được cấu hình batch. Factory record riêng cần được cấu hình rõ setBatchListener(false) hoặc được tạo theo cấu hình phù hợp.

## 18. Kiểm thử batch listener

Kiểm thử nên xác nhận listener thực sự nhận nhiều record trong một lần gọi và commit/retry đúng.

Các kịch bản hữu ích:

- Tạo topic nhiều partition, gửi một nhóm record và xác nhận batch listener nhận List.
- Kiểm tra batch có thể chứa record từ nhiều partition.
- Kiểm tra List<ConsumerRecord> giữ topic, partition, offset, key và headers.
- Kiểm tra max.poll.records giới hạn số record tối đa một poll.
- Gửi ít record hơn max.poll.records và xác nhận listener không chờ đủ batch size cố định.
- Kiểm tra concurrency tạo nhiều consumer con và assignment đúng theo partition.
- Làm một record trong batch lỗi; xác nhận cả batch retry hoặc chỉ record lỗi retry theo BatchListenerFailedException.
- Xác nhận DLT publish thành công trước khi offset được recover/commit theo cấu hình.
- Làm database transaction rollback và xác nhận batch có thể được giao lại.
- Giả lập batch xử lý lâu vượt max.poll.interval.ms và quan sát rebalance.
- Kiểm tra record cùng partition vẫn được xử lý theo offset.
- Kiểm tra listener record và batch dùng factory riêng, không bị nhầm chữ ký.
- Đo throughput, latency, heap và GC khi thay đổi max.poll.records.

Để kiểm tra một lần gọi listener có nhiều record, nên gửi đủ dữ liệu và dùng latch/condition đồng bộ với timeout. Không dùng sleep ngắn rồi kết luận batch listener chỉ nhận một record; broker có thể trả poll trước khi các record tiếp theo đến.

## 19. Các lỗi thường gặp

**Quên gọi setBatchListener(true).** Listener method nhận List nhưng factory vẫn chạy record mode. Cấu hình factory đúng hoặc dùng Boot listener.type=batch.

**Dùng chữ ký một record với batch factory.** Container truyền batch nhưng method không tương thích. Dùng factory record riêng hoặc đổi method signature.

**Nghĩ max.poll.records là batch size cố định.** Đây là giới hạn tối đa, không phải số record luôn được trả về. Batch có thể nhỏ hơn.

**Nhầm producer batch.size với consumer max.poll.records.** Producer batching và consumer poll batch là hai cơ chế khác nhau.

**Đặt concurrency cao hơn partition count.** Consumer dư không nhận partition và không tăng throughput.

**Xử lý cả batch trong thời gian quá dài.** Có thể vượt max.poll.interval.ms và gây rebalance. Giảm batch, tối ưu xử lý hoặc điều chỉnh interval.

**Commit offset khi mới xử lý một phần batch.** Có thể bỏ qua record chưa thành công. Chỉ commit batch khi hoàn tất hoặc dùng error handling/partial batch strategy có kiểm soát.

**Không idempotent khi batch được retry.** Các record đã ghi database trước lỗi có thể được xử lý lại. Dùng eventId và unique constraint/inbox.

**Giả định batch có thứ tự toàn cục.** Batch có thể chứa nhiều partition; chỉ có thứ tự trong từng partition.

**Không cấu hình error handler cho partial failure.** Error handler không biết record nào lỗi và có thể retry toàn batch. Dùng BatchListenerFailedException khi biết index và cấu hình recoverer phù hợp.

**Dùng converter sai với deserializer.** StringJsonMessageConverter cần dữ liệu dạng String/byte phù hợp; không ghép tùy tiện với JsonDeserializer đã tạo object.

## 20. Checklist bật batchListener

- [ ] Đã xác định use case có thể xử lý nhiều record cùng lúc.
- [ ] Factory gọi setBatchListener(true).
- [ ] @KafkaListener tham chiếu đúng containerFactory.
- [ ] Method signature phù hợp: List payload, List<ConsumerRecord> hoặc ConsumerRecords.
- [ ] AckMode phù hợp với batch; không dùng RECORD cho batch listener.
- [ ] max.poll.records phù hợp kích thước payload và thời gian xử lý.
- [ ] max.poll.interval.ms đủ cho thời gian xử lý batch.
- [ ] Concurrency phù hợp partition count và năng lực downstream.
- [ ] Batch chứa nhiều partition được xử lý theo từng partition khi cần ordering.
- [ ] Listener có idempotency để chịu được batch retry.
- [ ] Có error handler cho lỗi toàn batch và partial failure.
- [ ] DLT/recoverer được cấu hình rõ nếu cần cách ly record lỗi.
- [ ] Batch converter tương thích với deserializer và payload type.
- [ ] Heap, GC, consumer lag và listener duration được theo dõi.
- [ ] Integration test bao gồm batch nhiều partition, retry, DLT, rebalance và shutdown.

## Kết luận

Bật batch listener trên container factory bằng setBatchListener(true) để Spring Kafka chuyển các record của một lần poll thành một lần gọi @KafkaListener. Có thể nhận List payload để xử lý nghiệp vụ đơn giản hoặc List<ConsumerRecord> khi cần metadata từng record. Hãy cấu hình max.poll.records, concurrency, AckMode và max.poll.interval.ms theo năng lực xử lý thực tế. Batch giúp giảm overhead và hỗ trợ bulk operation, nhưng mở rộng phạm vi lỗi, tăng bộ nhớ và đòi hỏi xử lý partial failure cẩn thận. Luôn giữ idempotency, ordering theo từng partition và kiểm thử commit/retry trước khi đưa batch listener vào production.

