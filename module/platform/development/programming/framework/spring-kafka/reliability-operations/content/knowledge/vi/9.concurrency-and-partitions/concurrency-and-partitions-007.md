# Batch listener và record listener trong Spring Kafka

Spring Kafka hỗ trợ hai cách nhận dữ liệu trong listener: **record listener** xử lý từng record trong mỗi lần gọi method, còn **batch listener** nhận một tập record do một lần poll trả về và xử lý trong một lần gọi. Cả hai dùng cùng Kafka consumer và listener container, nhưng khác nhau về hình dạng dữ liệu đầu vào, cách tổ chức xử lý, xử lý lỗi và thời điểm commit offset.

Record listener thường dễ kiểm soát từng sự kiện, retry và thứ tự nghiệp vụ. Batch listener có thể giảm overhead gọi method và phù hợp với thao tác theo lô, nhưng đòi hỏi thiết kế rõ ràng hơn khi chỉ một record trong batch bị lỗi. Lựa chọn đúng phụ thuộc vào throughput, yêu cầu thứ tự, độ trễ, cách xử lý lỗi và khả năng idempotent của nghiệp vụ.

## 1. Record và batch được tạo ra từ đâu?

Kafka consumer đọc dữ liệu bằng poll. Một lần poll có thể trả về nhiều record từ một hoặc nhiều partition được gán cho consumer đó.

~~~text
Kafka topic
  partition 0: A1, A2, A3, A4
  partition 1: B1, B2, B3
                  |
                  v
            KafkaConsumer.poll()
                  |
                  v
             Poll result
             A1, A2, B1, A3, B2, A4, B3
                  |
          +-------+-------+
          |               |
          v               v
     Record listener   Batch listener
          |               |
     gọi method nhiều   gọi method một lần
     lần, mỗi lần một   với tập record
     record             của poll
~~~

Với record listener, container lấy từng record trong poll result và gọi listener cho từng record. Với batch listener, container chuyển tập record của poll cho listener trong một lần gọi.

Một poll không nhất thiết trả về đủ số record tối đa. Kết quả phụ thuộc lượng dữ liệu sẵn có, partition assignment, fetch settings và giới hạn max.poll.records. Một consumer cũng có thể nhận dữ liệu từ nhiều partition cùng lúc.

## 2. Record listener là gì?

Record listener nhận một record trong mỗi lần gọi method. Ứng dụng có thể nhận trực tiếp payload đã deserialize hoặc nhận ConsumerRecord để truy cập metadata Kafka.

Ví dụ nhận payload:

~~~java
@Component
public class OrderRecordListener {

    private final OrderService orderService;

    public OrderRecordListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
            topics = "orders",
            groupId = "order-service"
    )
    public void onOrder(OrderCreated event) {
        orderService.process(event);
    }
}
~~~

Container gọi method cho từng record. Nếu một poll trả về 50 record, listener có thể được gọi tối đa 50 lần cho các record đó, tùy số record thực tế và việc xử lý lỗi.

Nếu cần key, partition, offset, timestamp hoặc header, nhận ConsumerRecord:

~~~java
@KafkaListener(
        topics = "orders",
        groupId = "order-service"
)
public void onOrder(ConsumerRecord<String, OrderCreated> record) {
    log.info(
            "Received order: topic={}, partition={}, offset={}, key={}",
            record.topic(),
            record.partition(),
            record.offset(),
            record.key()
    );

    orderService.process(record.value());
}
~~~

Record listener phù hợp khi:

- Mỗi sự kiện có quy tắc nghiệp vụ riêng.
- Cần retry và recovery theo từng record.
- Cần xử lý lỗi dữ liệu độc lập.
- Muốn đơn giản hóa idempotency theo event ID.
- Cần kiểm soát thời gian xử lý của từng sự kiện.
- Thứ tự trong partition là yêu cầu quan trọng và xử lý tuần tự là lựa chọn phù hợp.

Record listener không có nghĩa một consumer chỉ đọc một record mỗi poll. Consumer vẫn có thể poll nhiều record; container chỉ gọi method riêng cho từng record.

## 3. Batch listener là gì?

Batch listener nhận nhiều record trong một lần gọi method. Với Spring Kafka, factory phải được cấu hình batch mode, sau đó method có thể nhận List payload hoặc List ConsumerRecord.

Ví dụ nhận danh sách payload:

~~~java
@Component
public class OrderBatchListener {

    private final OrderService orderService;

    public OrderBatchListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
            topics = "orders",
            groupId = "order-service",
            containerFactory = "batchKafkaListenerContainerFactory"
    )
    public void onOrders(List<OrderCreated> events) {
        orderService.processBatch(events);
    }
}
~~~

Ví dụ nhận metadata đầy đủ cho từng record:

~~~java
@KafkaListener(
        topics = "orders",
        groupId = "order-service",
        containerFactory = "batchKafkaListenerContainerFactory"
)
public void onOrders(
        List<ConsumerRecord<String, OrderCreated>> records) {

    for (ConsumerRecord<String, OrderCreated> record : records) {
        log.info(
                "topic={}, partition={}, offset={}",
                record.topic(),
                record.partition(),
                record.offset()
        );

        orderService.process(record.value());
    }
}
~~~

Một lần gọi batch listener tương ứng với tập record nhận từ một lần poll của consumer. Tập đó có thể chứa record từ nhiều partition. Thứ tự được bảo đảm trong từng partition theo thứ tự offset; không nên giả định có một thứ tự nghiệp vụ toàn cục giữa các partition.

Batch listener hữu ích khi:

- Có thể xử lý nhiều record bằng một thao tác bulk.
- Có thể gom các lần ghi database thành batch.
- Cần giảm chi phí gọi method hoặc chi phí khởi tạo transaction cho từng record.
- Nghiệp vụ chấp nhận xử lý theo lô và có chiến lược lỗi phù hợp.
- Cần tăng throughput bằng cách tận dụng batch API của hệ thống đích.

Batch listener không tự động làm toàn bộ xử lý nhanh hơn. Nếu xử lý từng record vẫn tuần tự và tốn cùng thời gian, lợi ích có thể nhỏ. Nếu batch quá lớn, thời gian xử lý một lần poll có thể dài và làm tăng nguy cơ vượt max.poll.interval.ms.

## 4. Cấu hình record listener và batch listener

### Cấu hình record listener

Record là kiểu listener mặc định trong nhiều cấu hình Spring Boot. Có thể khai báo rõ:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: order-service
      enable-auto-commit: false
      max-poll-records: 500
    listener:
      type: single
      ack-mode: record
      concurrency: 3
~~~

Với record listener, container gọi method một lần cho mỗi record. AckMode RECORD yêu cầu commit sau khi listener xử lý thành công từng record.

### Cấu hình batch listener bằng Spring Boot

Để dùng batch listener với auto-configured factory:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: order-service
      enable-auto-commit: false
      max-poll-records: 500
    listener:
      type: batch
      ack-mode: batch
      concurrency: 3
~~~

Trong Spring Boot, listener type có thể được cấu hình là single hoặc batch tùy phiên bản. Kiểm tra metadata/configuration properties của phiên bản Boot đang dùng nếu tên hoặc kiểu property thay đổi.

AckMode BATCH là lựa chọn tự nhiên khi muốn commit sau khi toàn bộ poll batch đã được xử lý. Với batch listener, method cần hoàn tất thành công trước khi container coi batch là đã xử lý xong theo luồng bình thường.

### Tạo factory riêng bằng Java

Nếu ứng dụng cần cả hai kiểu listener trong cùng một context, tạo hai factory riêng sẽ giúp ý định rõ ràng:

~~~java
@Configuration
public class KafkaListenerConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
    recordKafkaListenerContainerFactory(
            ConsumerFactory<String, OrderCreated> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<
                        String, OrderCreated>();

        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);
        factory.setBatchListener(false);
        factory.getContainerProperties().setAckMode(
                ContainerProperties.AckMode.RECORD
        );

        return factory;
    }

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
    batchKafkaListenerContainerFactory(
            ConsumerFactory<String, OrderCreated> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<
                        String, OrderCreated>();

        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);
        factory.setBatchListener(true);
        factory.getContainerProperties().setAckMode(
                ContainerProperties.AckMode.BATCH
        );

        return factory;
    }
}
~~~

Chọn factory tương ứng tại endpoint:

~~~java
@KafkaListener(
        id = "orderRecordListener",
        topics = "orders",
        groupId = "order-records",
        containerFactory = "recordKafkaListenerContainerFactory"
)
public void onOrder(OrderCreated event) {
    orderService.process(event);
}

@KafkaListener(
        id = "orderBatchListener",
        topics = "orders",
        groupId = "order-batches",
        containerFactory = "batchKafkaListenerContainerFactory"
)
public void onOrders(List<OrderCreated> events) {
    orderService.processBatch(events);
}
~~~

Ví dụ dùng hai group ID khác nhau để minh họa hai consumer group độc lập. Trong hệ thống thực tế, không nên để hai listener group cùng đọc một topic nếu cả hai cùng thực hiện side effect giống nhau mà không có mục đích nghiệp vụ rõ ràng. Nếu chúng thuộc hai cách triển khai thay thế nhau, hãy chỉ kích hoạt một group trong production hoặc dùng topic/test environment riêng.

## 5. So sánh record listener và batch listener

| Tiêu chí | Record listener | Batch listener |
|---|---|---|
| Tham số method | Một payload hoặc ConsumerRecord | List payload, List ConsumerRecord hoặc kiểu batch được hỗ trợ |
| Số lần gọi method | Một lần cho mỗi record | Một lần cho mỗi poll batch |
| Xử lý nghiệp vụ | Theo từng sự kiện | Theo tập sự kiện |
| Xử lý lỗi | Dễ xác định record lỗi | Cần xác định record lỗi trong batch hoặc retry cả batch |
| Retry | Thường dễ retry từng record | Có thể retry một phần hoặc cả batch tùy error handler |
| Commit offset | Có thể dùng RECORD hoặc các mode khác | Thường dùng BATCH; semantics phụ thuộc ack mode |
| Throughput | Tốt cho xử lý từng record | Có thể cao hơn nếu hệ thống đích hỗ trợ bulk |
| Độ trễ | Record có thể được xử lý ngay khi poll trả về | Có thể phải chờ xử lý toàn batch |
| Thứ tự | Dễ giữ thứ tự xử lý tuần tự trong partition | Cần giữ thứ tự trong batch khi nghiệp vụ yêu cầu |
| Bộ nhớ | Thường giữ ít dữ liệu ở tầng listener | Có thể giữ cả batch trong quá trình xử lý |

Không có lựa chọn nào luôn tốt hơn. Hãy đo throughput, processing latency, commit overhead, consumer lag và chi phí retry trong workload thực tế.

## 6. Acknowledgement và commit offset

Listener type quyết định hình dạng callback; AckMode quyết định thời điểm commit offset. Hai khái niệm liên quan nhưng không thay thế nhau.

Một số mode thường gặp:

| AckMode | Hành vi |
|---|---|
| RECORD | Commit sau khi từng record listener xử lý thành công |
| BATCH | Commit sau khi tất cả record từ một poll đã được xử lý |
| TIME | Commit khi đạt khoảng thời gian ackTime |
| COUNT | Commit khi đạt số record ackCount |
| COUNT_TIME | Commit khi đạt ackCount hoặc ackTime |
| MANUAL | Listener gọi acknowledge; container xử lý commit theo batch semantics |
| MANUAL_IMMEDIATE | Acknowledge trên consumer thread có thể kích hoạt commit ngay |

Với record listener, RECORD có thể giảm số record bị replay sau crash, đổi lại tăng số lần commit. BATCH có thể giảm commit overhead, nhưng nếu consumer dừng trước khi batch hoàn tất hoặc commit thành công, các record chưa commit có thể được giao lại.

Với batch listener, BATCH thường dễ hiểu nhất: method xử lý toàn bộ tập record rồi container commit offset sau khi callback thành công. Nếu method thất bại, error handler quyết định cách retry và recovery.

Không commit offset trước khi side effect cần bảo vệ hoàn tất. Nếu listener cập nhật database rồi process dừng trước commit, record có thể được giao lại. Vì vậy, cả record listener và batch listener đều cần idempotency nếu xử lý lại có thể tạo hiệu ứng trùng.

## 7. Xử lý lỗi trong record listener

Với record listener, exception thường gắn trực tiếp với record mà listener đang xử lý. CommonErrorHandler như DefaultErrorHandler có thể retry record theo backoff rồi recover hoặc gửi DLT khi hết retry.

~~~java
@KafkaListener(topics = "orders", groupId = "order-service")
public void onOrder(OrderCreated event) {
    orderService.process(event);
}
~~~

Nếu process ném exception, container chuyển lỗi tới error handler. Ví dụ cấu hình:

~~~java
@Bean
DefaultErrorHandler orderErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    var recoverer =
            new DeadLetterPublishingRecoverer(kafkaTemplate);

    var backOff = new FixedBackOff(1000L, 2L);

    return new DefaultErrorHandler(recoverer, backOff);
}
~~~

Với FixedBackOff(1000L, 2L), error handler chờ một giây giữa các lần retry và cho phép hai lần retry sau lần gọi đầu. Nếu vẫn thất bại, recoverer có thể gửi record sang DLT. Cần cấu hình handler vào listener container factory thực tế.

Record listener giúp việc xác định event lỗi và ghi log metadata đơn giản hơn. Tuy nhiên, nếu record đã cập nhật database trước khi exception xảy ra ở bước sau, lần retry vẫn có thể lặp side effect. Dùng transaction database và event ID để bảo vệ nghiệp vụ.

## 8. Xử lý lỗi trong batch listener

Batch listener có một điểm khác biệt quan trọng: một lần gọi method xử lý nhiều record. Nếu method ném exception, container cần biết record nào gây lỗi để quyết định retry phần nào.

Nếu listener có thể xác định index của record lỗi, hãy ném BatchListenerFailedException:

~~~java
@KafkaListener(
        topics = "orders",
        groupId = "order-batch",
        containerFactory = "batchKafkaListenerContainerFactory"
)
public void onOrders(
        List<ConsumerRecord<String, OrderCreated>> records) {

    for (int index = 0; index < records.size(); index++) {
        ConsumerRecord<String, OrderCreated> record =
                records.get(index);

        try {
            orderService.process(record.value());
        }
        catch (RuntimeException ex) {
            throw new BatchListenerFailedException(
                    "Order batch processing failed",
                    ex,
                    index
            );
        }
    }
}
~~~

Index trong exception chỉ vị trí record trong danh sách batch hiện tại. DefaultErrorHandler có thể dùng thông tin đó để xử lý phần record trước vị trí lỗi và seek/retry phần còn lại theo chính sách của nó.

Nếu listener chỉ ném một exception chung mà không xác định record lỗi, error handler có thể phải retry toàn batch. Khi đó, các record đã xử lý thành công trước lỗi cũng có thể được chạy lại. Đây là lý do batch operation cần idempotent hoặc có cách ghi nhận tiến độ từng record.

Các lưu ý khi xử lý lỗi batch:

- Không bắt exception rồi bỏ qua nếu muốn error handler retry.
- Nếu xác định được record lỗi, cung cấp index hoặc record tương ứng bằng BatchListenerFailedException.
- Giữ event ID và metadata để log, điều tra và phát lại.
- Đảm bảo các thao tác bulk có thể rollback hoặc chịu được việc chạy lại.
- Kiểm tra recovery/DLT cho batch listener theo phiên bản Spring Kafka.
- Không giả định toàn bộ batch đã commit chỉ vì một phần record xử lý thành công.

## 9. Xử lý batch bằng bulk operation

Batch listener phát huy lợi thế khi hệ thống đích hỗ trợ thao tác bulk. Ví dụ, thay vì ghi database từng order một, có thể gom thành một lần batch insert/update.

~~~java
@Service
public class OrderBatchService {

    private final OrderRepository orderRepository;

    public OrderBatchService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional
    public void processBatch(List<OrderCreated> events) {
        List<OrderEntity> entities = events.stream()
                .map(this::toEntity)
                .toList();

        orderRepository.saveAll(entities);
    }

    private OrderEntity toEntity(OrderCreated event) {
        return new OrderEntity(
                event.orderId(),
                event.customerId(),
                event.amount()
        );
    }
}
~~~

Transaction database có thể giúp cả batch commit hoặc rollback cùng nhau nếu repository và database dùng chung transaction. Điều này không tự động tạo transaction phân tán với Kafka offset. Nếu database commit thành công nhưng offset chưa commit, batch có thể được giao lại.

Một số lựa chọn thiết kế:

- Dùng unique constraint trên event ID để ngăn insert trùng.
- Dùng upsert nếu cập nhật lặp lại có cùng kết quả.
- Lưu inbox/processed event cùng transaction với dữ liệu nghiệp vụ.
- Chia batch thành các nhóm nhỏ nếu một batch quá lớn.
- Đặt giới hạn số record và tổng thời gian xử lý batch.

Không phải mọi bulk API đều nguyên tử. Hãy xác nhận transaction semantics của database hoặc dịch vụ đích.

## 10. Batch size và các cấu hình poll

Batch listener nhận các record do poll trả về. Các cấu hình consumer ảnh hưởng kích thước batch và thời gian xử lý.

~~~yaml
spring:
  kafka:
    consumer:
      max-poll-records: 300
      properties:
        "[max.poll.interval.ms]": 300000
        "[fetch.min.bytes]": 1
        "[fetch.max.wait.ms]": 500
    listener:
      type: batch
      ack-mode: batch
      concurrency: 3
~~~

Ý nghĩa:

- max.poll.records giới hạn số record tối đa trả về trong một lần poll.
- max.poll.interval.ms giới hạn thời gian giữa các lần poll tiếp theo của consumer.
- fetch.min.bytes là lượng dữ liệu tối thiểu broker cố gắng trả về khi có thể.
- fetch.max.wait.ms giới hạn thời gian broker chờ để tích lũy đủ fetch.min.bytes.
- concurrency tạo nhiều child consumer để xử lý partition song song.

max.poll.records không phải số record luôn có trong batch. Nếu chỉ có 20 record sẵn sàng, poll có thể trả 20 record dù giới hạn là 300.

Nếu xử lý batch mất quá nhiều thời gian, consumer có thể vượt max.poll.interval.ms và bị xem là không còn hoạt động đúng. Khi đó group có thể rebalance và partition được giao cho consumer khác. Cần đo thời gian xử lý batch ở p95/p99, điều chỉnh max.poll.records, concurrency và năng lực hệ thống đích.

Tăng max.poll.records có thể tăng throughput khi bulk operation hiệu quả, nhưng cũng làm tăng bộ nhớ cần thiết, thời gian xử lý một batch và số record có thể bị replay.

## 11. Concurrency và partition assignment

Spring Kafka dùng ConcurrentMessageListenerContainer để quản lý nhiều child consumer khi concurrency lớn hơn một. Mỗi child có một Kafka consumer riêng và chỉ xử lý các partition được group coordinator gán cho nó.

~~~text
Topic orders: 6 partitions
        |
        v
Consumer group: order-service
        |
        +--> Consumer 1: P0, P1
        |
        +--> Consumer 2: P2, P3
        |
        +--> Consumer 3: P4, P5
~~~

Sơ đồ chỉ minh họa một cách phân bổ có thể xảy ra. Assignment thực tế phụ thuộc partition assignor và số consumer đang hoạt động.

Nguyên tắc:

- Một partition trong cùng consumer group chỉ được gán cho một consumer tại một thời điểm.
- Tăng concurrency vượt số partition không tạo thêm mức xử lý song song hữu ích cho topic đó.
- Record trong cùng partition có thứ tự offset; xử lý tuần tự trong listener giúp giữ thứ tự nghiệp vụ.
- Các partition khác nhau có thể được xử lý đồng thời.
- Batch listener có thể nhận record từ nhiều partition trong cùng poll; không giả định thứ tự toàn cục giữa chúng.
- Khi rebalance, partition có thể chuyển sang child consumer khác và record chưa commit có thể được giao lại.

Nếu cần bảo toàn thứ tự theo order ID, hãy dùng order ID làm Kafka key để các record của cùng order đi vào cùng partition. Nếu batch listener xử lý song song nội bộ, hãy bảo đảm các record có quan hệ thứ tự không bị hoàn tất theo thứ tự ngược.

## 12. Khi nào chọn record listener?

Chọn record listener khi:

**Mỗi record là một đơn vị nghiệp vụ độc lập.** Một event lỗi không nên làm các event khác trong poll phải retry cùng.

**Cần retry theo từng record.** DefaultErrorHandler có thể retry và recover record lỗi mà không phải viết logic xác định index trong batch.

**Cần kiểm soát latency.** Record có thể được xử lý ngay khi container lấy nó ra khỏi poll result, không cần đợi ứng dụng xử lý cả danh sách.

**Nghiệp vụ cần thứ tự rõ ràng.** Listener tuần tự xử lý từng record trong partition dễ thiết kế hơn, mặc dù vẫn cần cân nhắc concurrency và các lời gọi bất đồng bộ do ứng dụng tự tạo.

**Từng record có thể có kích thước hoặc thời gian xử lý rất khác nhau.** Xử lý riêng giúp tránh một record nặng kéo dài toàn batch.

Đổi lại, record listener có thể chịu overhead gọi method và transaction lặp lại nếu mỗi record cần thao tác riêng.

## 13. Khi nào chọn batch listener?

Chọn batch listener khi:

**Hệ thống đích hỗ trợ bulk.** Ví dụ database batch insert, bulk indexing, bulk API hoặc phép tính tổng hợp trên tập record.

**Chi phí mỗi lần gọi lớn.** Gom record có thể giảm số lần mở transaction, gọi API hoặc chuẩn bị statement.

**Throughput quan trọng hơn latency từng record.** Batch có thể chờ đủ dữ liệu trước khi xử lý, nhưng thường tận dụng tài nguyên tốt hơn trong workload phù hợp.

**Có thể xác định record lỗi.** Listener có thể dùng BatchListenerFailedException để thông báo index lỗi và error handler xử lý phần còn lại.

**Nghiệp vụ chấp nhận xử lý theo lô.** Các record trong batch có thể được xử lý chung mà không cần phản hồi độc lập ngay lập tức.

Tránh batch listener nếu một record lỗi thường xuyên khiến toàn batch phải retry, batch processing khó rollback hoặc thứ tự nghiệp vụ giữa các record không được xác định.

## 14. Batch listener, transaction và exactly-once semantics

Nếu listener container dùng Kafka transaction manager, container có thể gộp việc ghi output Kafka và commit offset input trong một Kafka transaction. Với batch listener, đơn vị callback là batch; khi exception làm transaction abort, các output Kafka thuộc transaction đó không được consumer dùng read_committed quan sát như dữ liệu đã commit.

Tuy nhiên, transaction Kafka không tự bao gồm database hoặc HTTP service bên ngoài. Nếu batch đã cập nhật database rồi transaction Kafka abort, lần giao lại batch có thể cập nhật database lần nữa.

Đối với database:

- Dùng transaction database cho thao tác bulk nếu muốn cả batch commit/rollback cùng nhau.
- Dùng inbox/event ID để nhận diện record đã xử lý.
- Cân nhắc transactional outbox khi cần phát event sau khi cập nhật database.
- Không gọi side effect ngoài transaction rồi giả định Kafka rollback sẽ hoàn tác side effect đó.

Exactly-once trong Kafka cần cấu hình producer/consumer transaction đúng cách. Nó không tự động bảo đảm exactly-once end-to-end cho batch listener khi có hệ thống ngoài Kafka.

## 15. Các lỗi thường gặp

**Cấu hình batch factory nhưng method vẫn nhận một payload đơn**

Factory ở batch mode mong đợi listener signature tương thích với batch. Hãy dùng List payload, List ConsumerRecord hoặc kiểu batch được Spring Kafka hỗ trợ. Nếu muốn nhận từng payload, dùng record factory.

**Method nhận List nhưng factory vẫn ở record mode**

Chỉ đổi method signature không đủ để cấu hình container batch. Cần bật batch listener qua Boot property hoặc factory.setBatchListener(true).

**Batch quá lớn**

Batch lớn có thể tăng bộ nhớ, thời gian xử lý và rủi ro vượt max.poll.interval.ms. Giảm max.poll.records hoặc chia nhỏ công việc.

**Một lỗi làm retry toàn batch**

Nếu không xác định record lỗi, handler có thể phải retry cả batch. Dùng BatchListenerFailedException khi biết vị trí lỗi và thiết kế xử lý idempotent.

**Xử lý song song phá thứ tự**

Nếu batch được chia cho nhiều thread, record cùng partition có thể hoàn tất sai thứ tự. Chỉ parallelize khi nghiệp vụ độc lập hoặc có cơ chế sequence/serialization theo key.

**Cho rằng BATCH đồng nghĩa xử lý đúng một lần**

BATCH chỉ quyết định thời điểm commit offset. Nếu process dừng sau side effect nhưng trước commit, record có thể được giao lại.

**Tăng concurrency nhưng topic ít partition**

Consumer bổ sung có thể không nhận partition. Tăng concurrency không thay thế việc thiết kế partition phù hợp.

**Nuốt exception trong listener**

Nếu method bắt exception rồi trả về bình thường, container có thể coi callback thành công. Hãy ném lại lỗi nếu muốn error handler retry hoặc recover.

## 16. Theo dõi hiệu năng và vận hành

Khi so sánh hai kiểu listener, hãy đo cùng một workload và cùng điều kiện.

| Metric | Ý nghĩa |
|---|---|
| records-consumed-rate | Số record được xử lý mỗi giây |
| listener execution time | Thời gian thực thi method listener |
| batch size | Số record trung bình và lớn nhất mỗi callback |
| consumer lag | Khoảng cách giữa offset mới nhất và offset đã commit |
| commit rate | Tần suất commit offset |
| commit latency | Thời gian commit hoàn tất |
| rebalance rate | Tần suất group phân phối lại partition |
| retry count | Số lần record/batch được thử lại |
| DLT rate | Số record được recovery sang DLT |
| heap/buffer usage | Tài nguyên bộ nhớ khi giữ batch |

Tên metric thực tế phụ thuộc Kafka client, Spring Kafka, Micrometer và exporter. Kiểm tra các metric được ứng dụng xuất thay vì giả định mọi phiên bản đều có cùng tên.

Một phép so sánh hữu ích nên ghi nhận:

- Throughput tổng và throughput trên từng partition.
- p50, p95, p99 listener latency.
- Thời gian từ record được publish tới khi nghiệp vụ hoàn tất.
- Số lần commit và commit latency.
- Số record bị replay sau restart.
- Tỷ lệ lỗi và thời gian phục hồi.
- CPU, heap và tải database/service đích.

Batch có thể tăng throughput nhưng cũng tăng latency của record đầu tiên trong batch nếu phải chờ thêm dữ liệu. Hãy đo cả throughput và end-to-end latency trước khi chọn.

## 17. Checklist lựa chọn và cấu hình

Trước khi đưa listener vào production, hãy xác định:

- Mỗi callback nhận một record hay một poll batch?
- Factory thực tế có được cấu hình đúng record/batch mode không?
- Method signature có tương thích với listener type không?
- max.poll.records có phù hợp với kích thước batch và thời gian xử lý không?
- Concurrency có phù hợp với số partition và năng lực hệ thống đích không?
- AckMode có phù hợp với yêu cầu commit offset không?
- Exception có được truyền tới error handler khi cần retry không?
- Batch listener có xác định được index record lỗi không?
- DLT và recovery có xử lý được record/batch không?
- Side effect database/API có idempotent khi redelivery không?
- Việc parallelize batch có phá thứ tự trong partition không?
- max.poll.interval.ms có đủ cho p99 batch processing time không?
- Consumer lag, batch size, listener latency, commit và retry metrics có được theo dõi không?
- Đã thử crash, rebalance và lỗi giữa batch để kiểm tra replay chưa?

Record listener phù hợp với xử lý từng sự kiện, retry độc lập và yêu cầu latency rõ ràng. Batch listener phù hợp khi ứng dụng có thể tận dụng bulk processing và chấp nhận xử lý theo lô. Cả hai vẫn dựa trên Kafka consumer poll, offset commit và listener container; hãy chọn theo ranh giới nghiệp vụ, chiến lược lỗi và số liệu vận hành của hệ thống.
