# Retry theo batch

## 1. Retry theo batch trong Spring Kafka

Kafka consumer có thể đọc nhiều record trong một lần gọi poll. Khi dùng **batch listener** trong Spring Kafka, phương thức listener nhận cả danh sách record để xử lý. Cách này phù hợp với bulk insert, gọi dịch vụ hỗ trợ nhiều phần tử hoặc tối ưu throughput.

Tuy nhiên, chỉ cần một record lỗi, ứng dụng phải quyết định cách thử lại: chạy lại **toàn batch**, hay tiếp tục từ **record lỗi và phần chưa xử lý**. Quyết định ảnh hưởng tới số lần xử lý lặp, consumer lag, thời gian commit offset và dữ liệu của hệ thống đích.

Ví dụ:

~~~text
Batch được giao:
   R0    R1    R2    R3    R4
   |     |     |     |     |
   OK    OK    X     ?     ?
               ^
           lỗi tại R2
~~~

Nếu R0 và R1 đã ghi database thành công rồi batch được chạy lại, hai record đó có thể bị xử lý lần nữa. Nếu cả batch được xử lý trong một database transaction và transaction rollback hoàn toàn khi lỗi, retry toàn batch có thể phù hợp.

Trong Spring Kafka, hai hướng quan trọng là:

- **Retry toàn batch:** listener ném một exception thông thường và handler không biết record cụ thể nào thất bại.
- **Retry từ record lỗi:** listener ném **BatchListenerFailedException** với vị trí record thất bại để **DefaultErrorHandler** có thông tin xử lý phần trước và phần sau lỗi.

Retry xử lý lỗi tạm thời. Nó không tự đảm bảo exactly-once cho side effect ở database, HTTP API hay các hệ thống ngoài Kafka.

## 2. Phân biệt poll batch, batch listener và producer batch

| Khái niệm | Ý nghĩa |
|---|---|
| Producer batch | Producer gom các record để gửi tới broker hiệu quả hơn |
| Consumer poll batch | Tập record KafkaConsumer trả về từ một lần poll; có thể trải trên nhiều partition |
| Batch listener | Phương thức Spring Kafka nhận danh sách record trong một lần gọi |
| Retry batch | Chính sách xử lý lại các record thuộc batch khi listener thất bại |

Ví dụ batch listener:

~~~java
@KafkaListener(
    topics = "orders.created",
    groupId = "order-fulfillment",
    containerFactory = "orderBatchContainerFactory"
)
public void handle(List<ConsumerRecord<String, OrderCreated>> records) {
    fulfillmentService.processBatch(records);
}
~~~

Số record được giao không cố định. **max.poll.records** là giới hạn tối đa cho một lần poll, không phải số record listener bắt buộc phải nhận. Một poll còn có thể lấy record từ nhiều partition mà consumer đang sở hữu.

~~~text
Index 0 -> partition 0, offset 40
Index 1 -> partition 0, offset 41
Index 2 -> partition 1, offset 98
Index 3 -> partition 1, offset 99
~~~

Index trong danh sách không phải Kafka offset. Một error handler cần biết partition và offset thực tế để quản lý commit và redelivery.

## 3. Vì sao lỗi một record có thể ảnh hưởng toàn batch?

Giả sử listener xử lý tuần tự năm record và record thứ ba thất bại. Phương thức chưa trả về bình thường, nên container không thể xem cả batch đã hoàn tất.

Khi listener chỉ ném **RuntimeException**, framework không biết record đầu, giữa hay cuối batch gây lỗi. Với **DefaultErrorHandler**, trường hợp này được xử lý bằng fallback batch retry: toàn bộ batch có thể được thử lại theo BackOff, sau đó chuyển sang recovery khi hết lượt.

~~~text
poll -> [A, B, C, D]
            |
            v
      processBatch()
            |
          lỗi
            |
            v
    DefaultErrorHandler
            |
       BackOff còn?
        /       \
      Có        Không
       |          |
       v          v
 retry batch   recovery theo
               chính sách
~~~

Hệ quả là một record lỗi có thể gây nhiều lần chạy lại cho các record đã thành công. Nếu mỗi record có side effect riêng, cần cơ chế idempotency để tránh tác động nghiệp vụ lặp.

### 3.1. Khi retry toàn batch phù hợp

Retry toàn batch thường phù hợp khi:

- Toàn bộ batch được xử lý trong một transaction DB và có khả năng rollback thật sự.
- Bulk API báo lỗi ở mức batch mà không xác định được phần tử lỗi.
- Side effect idempotent, gọi lại không làm thay đổi kết quả thêm lần nữa.
- Lỗi tạm thời của dependency có khả năng được khắc phục bằng một lần thử mới.
- Tính nhất quán nghiệp vụ yêu cầu xử lý toàn batch cùng một đơn vị.

Nếu listener đã commit thành công vài record trước khi thất bại, retry toàn batch vẫn có thể đúng về mặt at-least-once nhưng tạo thêm chi phí. Khi xác định được record lỗi, hãy cân nhắc báo failed index rõ ràng.

### 3.2. Bulk processing không có transaction

Ví dụ một batch 100 record được ghi vào một hệ thống ngoài Kafka. API trả lỗi sau khi ghi 70 record, nhưng không cho biết record nào đã hoàn tất. Nếu retry toàn bộ, 70 record có thể được gửi lại. Để an toàn, dependency phải có idempotency key hoặc nghiệp vụ cần một cơ chế đối soát trạng thái bền vững.

Chỉ ghi nhận “batch thất bại” trong log chưa đủ để quyết định offset nào có thể commit.

## 4. Xác định record lỗi bằng BatchListenerFailedException

**BatchListenerFailedException** là exception thuộc package **org.springframework.kafka.listener**. Listener có thể ném nó với index record lỗi trong danh sách đang xử lý.

~~~java
throw new BatchListenerFailedException(
    "Fulfillment event failed",
    originalException,
    failedIndex
);
~~~

**failedIndex** bắt đầu từ 0. Nếu record thứ ba lỗi, dùng index 2.

Ví dụ listener xử lý tuần tự:

~~~java
@Service
public class OrderBatchListener {

    private final FulfillmentService fulfillmentService;

    public OrderBatchListener(FulfillmentService fulfillmentService) {
        this.fulfillmentService = fulfillmentService;
    }

    @KafkaListener(
        topics = "orders.created",
        groupId = "order-fulfillment",
        containerFactory = "orderBatchContainerFactory"
    )
    public void consume(
            List<ConsumerRecord<String, OrderCreated>> records) {

        for (int index = 0; index < records.size(); index++) {
            var record = records.get(index);

            try {
                fulfillmentService.processIdempotently(record.value());
            }
            catch (RuntimeException ex) {
                throw new BatchListenerFailedException(
                    "Failed to handle order event",
                    ex,
                    index
                );
            }
        }
    }
}
~~~

Khi index 2 lỗi, handler biết index 0 và 1 nằm trước điểm thất bại. Nó có thể commit tiến độ tương ứng của phần đã xử lý, rồi redeliver record lỗi và phần còn lại theo cấu hình.

| Dữ liệu | Ví dụ | Có dùng làm failedIndex? |
|---|---|---|
| Vị trí trong List | records.get(2) | Có |
| Kafka offset | record.offset() = 120 | Không |
| Partition | record.partition() = 3 | Không |
| Event ID | order-102 | Không |

Không nhầm index với offset. Batch có thể chứa nhiều partition nên cũng không có offset chung cho toàn bộ danh sách.

### 4.1. Không giả định mọi record trước index đều đã commit

Nếu ứng dụng xử lý record song song, record index 4 có thể hoàn tất trước index 2. Trong trường hợp đó, vị trí index không mô tả chính xác trạng thái side effect của mỗi record.

**BatchListenerFailedException** phù hợp nhất khi listener biết chắc record nào đã hoàn tất trước khi lỗi được phát hiện. Nếu xử lý song song, phải đồng bộ kết quả và làm side effect idempotent trước khi chọn cơ chế redelivery.

## 5. Cấu hình batch listener trong Spring Boot

Có thể bật batch listener và để Spring Kafka quản lý offset như sau:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: order-fulfillment
      enable-auto-commit: false
      max-poll-records: 200
      auto-offset-reset: earliest
    listener:
      type: batch
      ack-mode: batch
      concurrency: 3
~~~

Ý nghĩa của cấu hình:

- **listener.type=batch:** endpoint dùng batch listener.
- **ack-mode=batch:** container quản lý commit theo tập record của poll trong luồng xử lý bình thường.
- **enable-auto-commit=false:** tránh Kafka client commit offset theo thời gian riêng trong khi listener chưa xử lý xong.
- **max-poll-records=200:** giới hạn số record được trả về mỗi poll.
- **concurrency=3:** listener container có thể tạo ba consumer con chạy song song trên những partition được gán.

Concurrency không làm hai consumer cùng group đọc song song một partition. Mỗi consumer con có poll batch và commit offset riêng.

Nếu ứng dụng dùng **ConcurrentKafkaListenerContainerFactory** tùy biến, phải đặt batch mode và error handler cho chính factory đó; không suy luận rằng mọi property của factory auto-configured đều được kế thừa.

## 6. DefaultErrorHandler kết hợp BackOff

**DefaultErrorHandler** có thể dùng **BackOff** để xác định số lần thử lại và thời gian chờ giữa các lần thử. Ví dụ có **DeadLetterPublishingRecoverer** để xử lý record sau khi retry hết:

~~~java
@Configuration
public class OrdersKafkaConfiguration {

    @Bean
    public DefaultErrorHandler ordersErrorHandler(
            KafkaTemplate<Object, Object> dltKafkaTemplate) {

        var recoverer =
            new DeadLetterPublishingRecoverer(dltKafkaTemplate);

        var backOff = new FixedBackOff(1_000L, 2L);

        return new DefaultErrorHandler(recoverer, backOff);
    }

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
            orderBatchContainerFactory(
                    ConsumerFactory<String, OrderCreated> consumerFactory,
                    DefaultErrorHandler ordersErrorHandler) {

        var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

        factory.setConsumerFactory(consumerFactory);
        factory.setBatchListener(true);
        factory.setCommonErrorHandler(ordersErrorHandler);

        return factory;
    }
}
~~~

Trong ví dụ **FixedBackOff(1_000L, 2L)**:

- Thời gian chờ giữa các lần retry khoảng 1 giây.
- Có tối đa hai lượt retry sau lần xử lý ban đầu theo semantics của FixedBackOff.
- Khi retry hết, recoverer được gọi theo nhánh xử lý lỗi của handler.

Đoạn mã giả định **ConsumerFactory**, KafkaTemplate và serializer/deserializer phù hợp đã tồn tại. Nếu DLT có dữ liệu thuộc nhiều kiểu, cần bảo đảm KafkaTemplate dùng serializer tương thích. Cũng cần có topic và quyền WRITE trên DLT.

### 6.1. Lựa chọn FixedBackOff và ExponentialBackOff

**FixedBackOff** giữ khoảng chờ cố định. Nó dễ dự đoán và phù hợp với các lỗi tạm thời có thời gian phục hồi ngắn.

Với dependency phục hồi chậm hơn, có thể dùng **ExponentialBackOff**:

~~~java
var backOff = new ExponentialBackOff();
backOff.setInitialInterval(500L);
backOff.setMultiplier(2.0);
backOff.setMaxInterval(8_000L);
backOff.setMaxElapsedTime(30_000L);

var handler = new DefaultErrorHandler(recoverer, backOff);
~~~

Giá trị cấu hình cần phù hợp với latency SLO, số lượng record và khả năng chịu tải của dependency. Chọn giới hạn retry rõ ràng; retry kéo dài sẽ giữ lỗi tồn tại, tăng lag và khiến batch phía sau bị chậm.

### 6.2. BackOff áp dụng khi có lỗi

Một batch thành công không phải chờ chỉ vì handler được cấu hình với FixedBackOff. Chỉ khi batch thất bại, handler mới áp dụng policy retry/recovery. Tổng thời gian thực tế còn gồm thời gian xử lý, network, downstream và thời gian gửi DLT.

## 7. Retry toàn batch so với retry từ failed index

Hai cơ chế khác nhau về phạm vi công việc phải lặp lại:

| Tiêu chí | Retry toàn batch | Retry từ failed index |
|---|---|---|
| Exception thường gặp | RuntimeException hoặc exception không xác định record lỗi | BatchListenerFailedException |
| Handler biết record lỗi? | Không | Có |
| Phần được thử lại | Có thể là toàn bộ batch | Phần lỗi và record còn lại theo handler |
| Tác động tới record đã xử lý | Có thể được gọi lại | Có thể giảm số record cần chạy lại |
| Phù hợp | Bulk transaction hoặc thao tác nguyên khối | Xử lý record tuần tự, xác định lỗi cụ thể |
| Đòi hỏi idempotency | Có | Vẫn có vì crash/rebalance |

Ví dụ:

~~~text
Poll batch:   A   B   C   D   E
              OK  OK  X   ?   ?

RuntimeException:
  handler có thể retry [A, B, C, D, E]

BatchListenerFailedException(index=2):
  handler có thể xử lý tiến độ [A, B]
  rồi redeliver [C, D, E]
~~~

Semantics cụ thể phụ thuộc Spring Kafka version, error handler, AckMode và cách record được giữ lại hoặc seek. Với listener có Kafka transaction, phải xem riêng cơ chế rollback.

## 8. Seek và redelivery không seek

Khi xử lý lỗi, consumer cần nhận lại các record chưa hoàn tất. Spring Kafka hỗ trợ các cách thực hiện khác nhau.

### 8.1. Seek về offset

Với cách xử lý seek, handler có thể đặt lại vị trí đọc của những partition có record chưa xử lý để KafkaConsumer đọc lại.

~~~text
Partition 0:
  offset 10 -> OK
  offset 11 -> OK
  offset 12 -> FAILED
  offset 13 -> chưa xử lý

Có thể commit tiến độ tới offset 12
và seek/redeliver từ offset 12
~~~

Kafka commit offset **tiếp theo cần đọc**. Nếu offset 11 đã hoàn tất thì vị trí commit tương ứng là 12.

### 8.2. Redelivery từ record giữ lại

Ở các phiên bản Spring Kafka hỗ trợ, đặt **seekAfterError=false** có thể khiến container giữ những record chưa xử lý để gửi lại sau một poll duy trì consumer, thay vì luôn seek KafkaConsumer.

~~~java
var handler = new DefaultErrorHandler(
    recoverer,
    new FixedBackOff(1_000L, 2L)
);
handler.setSeekAfterError(false);
~~~

Không seek không đồng nghĩa với record đã commit. Đây chỉ là cơ chế redelivery. Cần kiểm tra cấu hình effective và semantics của phiên bản Spring Kafka thực tế.

## 9. Retry và offset commit

Retry theo batch phải đồng bộ với commit offset. Consumer group lưu offset riêng theo từng partition.

Ví dụ poll nhận:

~~~text
index 0 -> P0 offset 10  : OK
index 1 -> P1 offset 50  : OK
index 2 -> P0 offset 11  : FAIL
index 3 -> P1 offset 51  : chưa xử lý
~~~

Record lỗi là P0 offset 11. Handler phải tính tiến độ của P0 và P1 riêng biệt, không thể commit theo một giá trị offset lấy từ index 2.

Nếu process crash sau khi ghi database nhưng trước commit Kafka, record chưa commit có thể được giao lại. Vì vậy, kể cả khi dùng failed index đúng, ứng dụng vẫn phải có idempotency cho những side effect quan trọng.

### 9.1. Tắt auto commit khi container quản lý retry

Nếu Kafka client tự commit định kỳ khi listener đang xử lý, offset có thể tiến lên trước khi side effect hoàn tất. Điều này có thể gây mất xử lý khi process bị dừng.

Khi dùng Spring Kafka listener container và DefaultErrorHandler, nên xác định **enable.auto.commit=false** và policy AckMode thích hợp. Không bật auto commit độc lập với cách container quản lý offset.

### 9.2. Không nuốt exception

Ví dụ không phù hợp:

~~~java
@KafkaListener(
    topics = "orders.created",
    containerFactory = "orderBatchContainerFactory"
)
public void consume(List<OrderCreated> orders) {
    try {
        fulfillmentService.processBatch(orders);
    }
    catch (Exception ex) {
        log.error("Batch failed", ex);
        // Trả về bình thường dù nghiệp vụ thất bại.
    }
}
~~~

Nếu listener bắt lỗi rồi trả về bình thường, container có thể xem batch thành công và commit offset. Để handler retry, hãy ném exception hoặc thực hiện một cơ chế recovery được xác định rõ.

## 10. Retry thủ công bằng nack(index, sleep)

Batch listener cũng có thể dùng **Acknowledgment.nack(index, sleep)** khi cấu hình AckMode manual phù hợp.

Ví dụ:

~~~java
@KafkaListener(
    topics = "orders.created",
    groupId = "order-fulfillment",
    containerFactory = "manualOrderBatchContainerFactory"
)
public void consume(
        List<ConsumerRecord<String, OrderCreated>> records,
        Acknowledgment ack) {

    for (int i = 0; i < records.size(); i++) {
        try {
            fulfillmentService.process(records.get(i).value());
        }
        catch (TemporaryDependencyException ex) {
            ack.nack(i, Duration.ofSeconds(2));
            return;
        }
    }
    ack.acknowledge();
}
~~~

Container factory cần chế độ manual ack:

~~~java
factory.setBatchListener(true);
factory.getContainerProperties()
    .setAckMode(ContainerProperties.AckMode.MANUAL);
~~~

Khi gọi **nack(index, sleep)** trong batch listener, container có thể commit tiến độ của record trước index, seek phần còn lại và tạm dừng trước khi tiếp tục. Lời gọi phải được thực hiện trên consumer thread và có giới hạn tương tác với **asyncAcks**. Hãy kiểm tra API của Spring Kafka version đang triển khai.

So sánh:

| Cơ chế | Ai điều khiển retry? | Backoff |
|---|---|---|
| BatchListenerFailedException + DefaultErrorHandler | Error handler | BackOff được cấu hình |
| Acknowledgment.nack(index, sleep) | Listener chủ động | Sleep do listener yêu cầu |

Không nên vừa ném exception vừa thực hiện nack cho cùng một lỗi mà không có quy tắc rõ ràng, vì có thể làm redelivery khó dự đoán.

## 11. Phân loại lỗi trước khi retry

Không phải lỗi nào cũng nên thử lại. Một record sai schema thường không tự trở thành hợp lệ sau vài giây. Một database timeout lại có thể phục hồi.

| Loại lỗi | Ví dụ | Hướng xử lý |
|---|---|---|
| Lỗi tạm thời | DB timeout, HTTP 503, connection reset | Retry giới hạn với backoff |
| Lỗi dữ liệu | Thiếu trường bắt buộc, enum không hợp lệ | Recovery/DLT, thường không retry lâu |
| Lỗi cấu hình | Thiếu quyền Kafka, topic sai | Sửa cấu hình hoặc ACL |
| Lỗi nghiệp vụ có thể phục hồi | Trạng thái phụ thuộc chưa được đồng bộ | Retry theo thời hạn nghiệp vụ |
| Lỗi vĩnh viễn | Dữ liệu vi phạm invariant không thể sửa | DLT hoặc xử lý thủ công |

Có thể cấu hình exception không retry cho DefaultErrorHandler:

~~~java
handler.addNotRetryableExceptions(InvalidOrderException.class);
~~~

Cần hiểu exception gốc, wrapper và cause mà handler nhìn thấy. Với BatchListenerFailedException, exception nghiệp vụ có thể nằm trong cause. Chính sách phân loại lỗi phải khớp với hệ thống thực tế.

### 11.1. Lỗi xảy ra trước listener

Một lỗi deserialization có thể xảy ra ngay trong Kafka consumer, trước khi listener nhận danh sách. Khi đó listener không thể ném failed index vì chưa có record đã deserialize.

Có thể dùng **ErrorHandlingDeserializer** và chính sách container/error handler phù hợp để xử lý loại lỗi này. Không nên giả định mọi lỗi đọc dữ liệu đều có thể bắt bằng try/catch trong batch listener.

## 12. DLT và recovery sau khi hết retry

**DeadLetterPublishingRecoverer** là lựa chọn phổ biến để chuyển record không thể xử lý sang dead-letter topic.

~~~java
var recoverer = new DeadLetterPublishingRecoverer(dltKafkaTemplate);

var handler = new DefaultErrorHandler(
    recoverer,
    new FixedBackOff(1_000L, 2L)
);
~~~

Nếu handler biết failed index, nó có thể hướng recovery vào record lỗi theo semantics được hỗ trợ. Nếu lỗi toàn batch không có failed index, fallback batch retry và recovery cần được hiểu riêng, bởi handler có thể xử lý cả batch chứ không biết đâu là poison record duy nhất.

Một DLT nên có:

- Topic và partition đủ cho destination resolver.
- Serializer phù hợp cho key/value của record cần publish.
- Quyền WRITE cho principal của DLT producer.
- Metadata nguồn: topic, partition, offset và exception.
- Metric backlog, ingress và cảnh báo.
- Quy trình điều tra, replay và kiểm soát duplicate khi replay.

Khi publish DLT thất bại, recovery không được coi thành công nếu không có bằng chứng record đã được lưu. Cần xem cách recoverer xử lý kết quả publish và cách handler phản ứng khi recoverer thất bại.

DLT không có nghĩa là nghiệp vụ đã hoàn tất. Nó là nơi cách ly dữ liệu cần xử lý thêm.

## 13. Retry batch và @RetryableTopic

Spring Kafka hỗ trợ non-blocking retry qua các retry topic và **@RetryableTopic** cho nhiều trường hợp record listener. Với batch listener, **non-blocking retries không được hỗ trợ trong cơ chế retry topic phổ biến của Spring Kafka**.

Vì vậy, không nên dựa vào việc chỉ gắn **@RetryableTopic** lên batch listener để có retry riêng theo từng record.

Nếu muốn delay dài mà không giữ poll thread trong quá trình retry, có thể:

- Chuyển sang record listener nếu cần cơ chế retry topic do Spring Kafka hỗ trợ.
- Tự thiết kế một pipeline retry riêng với topic và producer chuyên dụng.
- Định nghĩa rõ ordering, offset commit, lịch retry và idempotency.
- Cân nhắc DLT nếu record không thể xử lý.

Độ trễ hàng phút có thể không phù hợp với retry chặn consumer khi batch phía sau đang chờ.

## 14. Tránh duplicate bằng idempotent consumer

Retry theo batch thường đi cùng delivery semantics at-least-once. Kể cả khi error handler commit đúng phần đã hoàn tất, process có thể crash sau side effect và trước commit.

~~~text
Nhận batch
   |
   +-- R0 -> DB commit thành công
   +-- R1 -> DB commit thành công
   +-- R2 -> timeout
   |
   +-- JVM crash trước commit Kafka
   |
   v
Khởi động lại
   |
   v
R0, R1, R2 có thể được nhận lại
~~~

Để bảo vệ nghiệp vụ, dùng event ID ổn định và lưu trạng thái event đã xử lý trong cơ sở dữ liệu:

~~~sql
CREATE TABLE processed_event (
    event_id VARCHAR(128) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Một transaction DB nên ghi cả side effect và dấu vết đã xử lý. Unique constraint giúp hai lần xử lý cùng event không tạo kết quả trùng. Chỉ kiểm tra **existsById** trước khi insert không đủ nếu có race condition.

Nếu dependency là API bên ngoài, cần idempotency key hoặc cơ chế đối soát của dependency. Kafka offset và transaction Kafka không tự rollback được side effect ở HTTP service.

### 14.1. Retry cả batch và transaction DB

Khi toàn batch chạy trong một database transaction, failure có thể rollback tất cả thay đổi. Retry cả batch khi đó dễ lý giải hơn, nhưng batch lớn có thể giữ lock lâu và tăng contention.

Khi mỗi record có transaction riêng, một số record có thể commit thành công trước lỗi. Retry từ failed index có thể giảm công việc lặp, nhưng vẫn cần idempotency cho crash và rebalance.

## 15. Transactional listener và AfterRollbackProcessor

Với Kafka transaction, luồng xử lý lỗi có thể khác với DefaultErrorHandler non-transactional. Exception có thể khiến transaction abort và **AfterRollbackProcessor** quyết định cách record được redeliver/recover.

Ví dụ trong consume-transform-produce:

1. Consumer đọc record đầu vào.
2. Listener gửi output sang Kafka trong transaction.
3. Offset đầu vào được đưa vào transaction.
4. Khi transaction commit, output và offset được commit như một đơn vị Kafka.
5. Khi transaction abort, output chưa commit và offset trong transaction không được ghi nhận.

Điều này không bao gồm transaction DB hay HTTP call. Nếu trước khi Kafka transaction abort, listener đã ghi DB thành công, DB không tự rollback. Vì vậy, cần thiết kế outbox/inbox hoặc idempotent side effect.

Không lấy mô tả commit/seek của DefaultErrorHandler non-transactional áp dụng nguyên xi cho transactional batch listener. Hãy xác định đúng transaction manager, AfterRollbackProcessor và phiên bản Spring Kafka đang sử dụng.

## 16. Max poll interval, latency và consumer liveness

Retry và backoff có thể kéo dài thời gian giữa các lần poll. Nếu consumer không tiếp tục poll đúng cơ chế và vượt **max.poll.interval.ms**, nó có thể bị coi là không còn hoạt động trong consumer group.

Spring Kafka có các cơ chế poll, pause và retry nhằm giữ consumer hợp lệ trong nhiều tình huống. Tuy nhiên, một listener tự gọi sleep lâu hoặc blocking I/O không có timeout vẫn có thể gây mất group membership.

Cần xem tổng thời gian:

- Thời gian xử lý record hoặc bulk batch.
- Số lần retry.
- Tổng backoff.
- Timeout của downstream.
- Thời gian publish DLT và recovery.
- Thời gian GC hoặc chờ tài nguyên.

Giả sử batch có 200 record, mỗi record mất trung bình 20 ms nếu xử lý tuần tự:

~~~text
200 records x 20 ms = 4.000 ms = 4 giây
~~~

Nếu một record timeout 5 giây rồi retry ba lần với backoff 2 giây, thời gian batch tăng rõ rệt. Hãy đo p95/p99 thay vì chỉ trung bình.

Các lựa chọn giảm rủi ro:

- Giảm max.poll.records khi batch quá lớn.
- Đặt timeout rõ ràng cho DB/HTTP calls.
- Chọn số lần retry và backoff giới hạn.
- Theo dõi rebalance và consumer lag.
- Với delayed retry dài, cân nhắc pipeline bất đồng bộ riêng hoặc record listener có retry topic.

Không tăng max.poll.interval.ms vô hạn để che việc downstream đang bị treo.

## 17. Tác động tới throughput và ordering

Một record lỗi trong batch có thể trì hoãn xử lý những record phía sau. Nếu consumer quản lý nhiều partition, thời gian retry trong listener còn có thể làm tiến độ chung của consumer chậm lại.

~~~text
Consumer A: partition P0, P1
    |
    +-- batch chứa poison record ở P0
    |
    +-- retry/backoff
    |
    +-- record thuộc P1 có thể bị chậm theo
~~~

Kafka bảo đảm thứ tự trong từng partition, không có thứ tự toàn cục giữa các partition. Nếu nghiệp vụ cần thứ tự theo order ID, cần dùng key/partitioning phù hợp. Bỏ qua record lỗi hoặc chuyển DLT có thể giúp tiến độ tiếp tục, nhưng phải xác định tác động của việc thiếu record đó đối với thứ tự và trạng thái nghiệp vụ.

Tăng concurrency chỉ hữu ích khi có đủ partition, tài nguyên và downstream capacity. Nó không khiến nhiều consumer cùng group đọc song song một partition.

## 18. Quan sát và metric cho retry batch

Khi vận hành, nên đo cả lỗi riêng của record và lỗi toàn batch.

| Chỉ số | Câu hỏi cần trả lời |
|---|---|
| Batch size | Mỗi poll thường giao bao nhiêu record? |
| Batch duration p95/p99 | Batch có xử lý đủ nhanh? |
| Retry attempts | Có nhiều retry theo exception type? |
| Failed index | Lỗi thường xuất hiện đầu hay cuối batch? |
| Backoff accumulated time | Consumer chờ bao lâu vì lỗi? |
| Recovery success/failure | Recoverer/DLT publish có thành công? |
| DLT ingress | Có bao nhiêu record được cách ly? |
| Consumer lag per partition | Partition nào bị chặn? |
| Rebalance count | Retry có ảnh hưởng group membership? |
| Commit latency/failures | Offset có được ghi nhận đúng? |
| Event freshness | Thời gian hoàn tất nghiệp vụ có đáp ứng SLO? |

Log nên có topic, partition, offset, batch index, exception class và retry attempt:

~~~text
listener=order-batch
groupId=order-fulfillment
topic=orders.created
partition=2
offset=5130
batchIndex=18
exception=InventoryTimeoutException
retryAttempt=2
action=retry
~~~

Tránh dùng event ID, order ID hoặc offset làm label metric vì cardinality cao. Giữ các ID đó trong log/trace có kiểm soát.

Nếu retry tăng đồng thời lag tăng, có thể một record đang chặn tiến độ. Nếu DLT tăng đột biến, kiểm tra schema, validation và thay đổi deployment. Nếu rebalance tăng cùng batch duration, kiểm tra max.poll.interval.ms và các blocking call.

## 19. Ví dụ tổng hợp: Order Fulfillment

Order Fulfillment nhận event từ topic **orders.created**, xử lý mỗi record bằng một service có idempotency key và gửi record lỗi sang DLT khi hết retry.

Cấu hình Spring Boot:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: order-fulfillment
      enable-auto-commit: false
      max-poll-records: 100
    listener:
      type: batch
      ack-mode: batch
      concurrency: 3
~~~

Listener:

~~~java
@KafkaListener(
    topics = "orders.created",
    groupId = "order-fulfillment",
    containerFactory = "orderBatchContainerFactory"
)
public void handle(
        List<ConsumerRecord<String, OrderCreated>> records) {

    for (int i = 0; i < records.size(); i++) {
        try {
            fulfillmentService.processIdempotently(
                records.get(i).value()
            );
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

Error handler:

~~~java
@Bean
DefaultErrorHandler ordersErrorHandler(
        KafkaTemplate<Object, Object> dltKafkaTemplate) {

    var recoverer = new DeadLetterPublishingRecoverer(
        dltKafkaTemplate
    );

    var handler = new DefaultErrorHandler(
        recoverer,
        new FixedBackOff(1_000L, 2L)
    );

    handler.addNotRetryableExceptions(InvalidOrderException.class);
    return handler;
}
~~~

Giả sử batch có 80 record, record index 25 bị DB timeout. Listener ném **BatchListenerFailedException(index=25)**. Handler có thông tin xác định record lỗi và áp dụng retry policy. Nếu DB hồi phục, luồng có thể tiếp tục. Nếu hết lượt retry, handler gọi recoverer theo cấu hình.

Nếu lỗi là dữ liệu không hợp lệ vĩnh viễn, retry nhiều lần không hữu ích. Policy có thể phân loại lỗi để recovery sớm hơn. DLT cần có quy trình xử lý, vì event đưa vào DLT vẫn chưa hoàn tất nghiệp vụ gốc.

Nếu pod crash sau khi DB commit record index 20 nhưng trước Kafka offset commit, record đó có thể được giao lại. **processIdempotently** phải bảo đảm side effect không xảy ra lần hai.

## 20. Các sai lầm thường gặp

**Cho rằng DefaultErrorHandler luôn biết record nào lỗi.** Nếu listener chỉ ném RuntimeException chung, handler có thể phải retry cả batch.

**Truyền offset thay failed index.** Failed index là vị trí zero-based trong danh sách của listener.

**Retry cả batch dù side effect không idempotent.** Các record thành công trước lỗi có thể được xử lý lại.

**Bắt exception rồi chỉ ghi log.** Container có thể coi batch thành công và commit offset.

**Đặt retry vô hạn cho poison record.** Lỗi dữ liệu vĩnh viễn cần DLT hoặc xử lý thủ công, không nên làm consumer lag tăng mãi.

**Cho rằng recovery thành công khi DLT publish còn thất bại.** Cần xác nhận publisher và handler xử lý lỗi recovery đúng.

**Gắn @RetryableTopic lên batch listener rồi mong non-blocking retry tự hoạt động.** Cơ chế retry topic phổ biến không hỗ trợ batch listener.

**Bỏ qua max.poll.interval.ms.** Batch lớn, blocking call và retry dài làm tăng rủi ro rebalance.

**Cho rằng Kafka transaction rollback database.** Transaction Kafka chỉ bao gồm tài nguyên Kafka, side effect ngoài Kafka cần xử lý riêng.

**Tăng concurrency để chữa một hot partition.** Một partition vẫn chỉ được gán cho một consumer trong group.

## 21. Quy trình áp dụng

1. Xác nhận listener nhận batch và factory thực tế bật batch mode.
2. Xác định ranh giới transaction của side effect.
3. Chọn retry toàn batch hay retry từ failed index.
4. Nếu xác định được record lỗi, ném BatchListenerFailedException với index zero-based.
5. Thiết lập DefaultErrorHandler và BackOff có giới hạn.
6. Phân loại exception không retry và retry được.
7. Cấu hình DLT, serializer, topic, partition và ACL.
8. Dùng event ID và idempotency để chống xử lý lặp.
9. Chọn max.poll.records và timeout phù hợp SLO.
10. Đo retry attempts, lag, batch duration, DLT và rebalance.
11. Thử lỗi ở record đầu, giữa, cuối batch và thử restart trước commit.
12. Ghi rõ policy retry/recovery trong runbook.

## 22. Ghi nhớ

Retry theo batch cần xác định chính xác **phần nào thất bại** và **offset nào an toàn để commit**. Khi không có failed index, DefaultErrorHandler có thể retry toàn batch. Khi listener ném BatchListenerFailedException với index chính xác, handler có thể xử lý phần trước lỗi và redeliver phần chưa hoàn tất theo policy.

BackOff quyết định nhịp retry, recoverer xác định cách xử lý khi retry hết, còn idempotency bảo vệ side effect khi record bị giao lại. Hãy theo dõi độ trễ, consumer lag và DLT để bảo đảm retry giúp hệ thống phục hồi mà không làm sai kết quả nghiệp vụ.

