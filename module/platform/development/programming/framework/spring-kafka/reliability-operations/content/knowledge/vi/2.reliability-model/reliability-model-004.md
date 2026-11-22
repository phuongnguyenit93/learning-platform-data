# Read, process và write trong một luồng

Trong một ứng dụng Spring Kafka, một luồng xử lý phổ biến là đọc một record từ topic đầu vào, thực hiện nghiệp vụ rồi ghi kết quả sang topic đầu ra. Ví dụ, dịch vụ nhận `OrderCreated` từ `orders.in`, kiểm tra và bổ sung dữ liệu đơn hàng, sau đó phát `OrderEnriched` vào `orders.enriched` để các dịch vụ phía sau tiếp tục xử lý.

Luồng này có ba bước rõ ràng:

1. **Read** — consumer nhận record và giải mã key, value cùng metadata.
2. **Process** — ứng dụng kiểm tra dữ liệu và chạy nghiệp vụ để tạo kết quả.
3. **Write** — producer gửi kết quả sang topic đích.

Điểm quyết định độ tin cậy là thứ tự giữa việc ghi kết quả và việc xác nhận offset đầu vào. Nếu ứng dụng xác nhận offset quá sớm, record có thể bị mất khi ghi đầu ra thất bại. Nếu ghi đầu ra thành công nhưng offset chưa được xác nhận, record có thể được đọc lại và tạo ra kết quả trùng. Spring Kafka cung cấp transaction để gộp việc ghi record đầu ra và xác nhận offset đầu vào vào cùng một Kafka transaction.

## 1. Nhìn toàn bộ vòng đời của một record

```text
orders.in
   |
   v
Kafka consumer / @KafkaListener
   |
   v
Deserialize -> Validate -> Process
                         |
                         v
                  KafkaTemplate.send()
                         |
                         v
                   orders.enriched

Listener thành công  -> commit transaction (output + input offset)
Listener thất bại    -> rollback; record đầu vào có thể được đọc lại
```

Với listener chạy trong transaction do container quản lý, container bắt đầu transaction trước khi gọi listener. `KafkaTemplate` dùng producer đang tham gia transaction đó. Khi listener kết thúc thành công, container đưa offset đã xử lý vào transaction và commit. Khi listener ném exception, transaction bị rollback; cả record đầu ra lẫn offset đầu vào đều không được commit.

Điều này tạo ra **exactly-once processing trong phạm vi Kafka consume-transform-produce**: một lần xử lý được commit sẽ làm cho output và offset cùng có hiệu lực. Nó không có nghĩa mọi dòng code nghiệp vụ chỉ chạy đúng một lần, và cũng không bao phủ các hệ thống bên ngoài Kafka như database, HTTP API hoặc hệ thống thanh toán.

## 2. Read: nhận record và hiểu metadata

`@KafkaListener` là điểm vào thông dụng của một luồng xử lý Spring Kafka. Listener có thể nhận riêng payload hoặc nhận toàn bộ `ConsumerRecord`. Khi cần xử lý đáng tin cậy, `ConsumerRecord` hữu ích vì nó cung cấp:

- `key()` — khóa định tuyến record, thường được dùng lại khi phát kết quả.
- `value()` — payload sau khi deserializer chuyển đổi.
- `topic()`, `partition()` và `offset()` — vị trí record đầu vào, rất hữu ích khi log và điều tra sự cố.
- `headers()` — metadata như correlation ID, trace context hoặc loại sự kiện.

Ví dụ, listener nhận một đơn hàng:

```java
@Component
public class OrderEnrichmentListener {

    private final OrderProcessor processor;
    private final KafkaTemplate<String, Object> kafkaTemplate;
    private final String outputTopic;

    public OrderEnrichmentListener(
            OrderProcessor processor,
            KafkaTemplate<String, Object> kafkaTemplate,
            @Value("${app.topics.orders-out}") String outputTopic) {
        this.processor = processor;
        this.kafkaTemplate = kafkaTemplate;
        this.outputTopic = outputTopic;
    }

    @KafkaListener(
            topics = "${app.topics.orders-in}",
            groupId = "${spring.kafka.consumer.group-id}")
    public void onOrder(ConsumerRecord<String, Order> record) {
        EnrichedOrder result = processor.enrich(record.value());
        kafkaTemplate.send(outputTopic, record.key(), result);
    }
}
```

`Order`, `EnrichedOrder` và `OrderProcessor` là kiểu dữ liệu và thành phần nghiệp vụ của ứng dụng. Ví dụ giả định producer đã được cấu hình serializer phù hợp với `EnrichedOrder` và listener container đã được cấu hình transaction như phần tiếp theo.

### Deserialize và validate

Deserializer chịu trách nhiệm chuyển byte trong Kafka thành kiểu Java. Cần thống nhất serializer ở producer và deserializer ở consumer, đồng thời kiểm soát schema khi cấu trúc sự kiện thay đổi. Một record không thể deserialize có thể lỗi trước khi phương thức listener được gọi; vì vậy hãy cấu hình cơ chế xử lý lỗi deserialization, chẳng hạn `ErrorHandlingDeserializer`, nếu ứng dụng cần chuyển record lỗi sang dead-letter topic (DLT).

Validate dữ liệu đầu vào trước khi chạy nghiệp vụ. Phân biệt lỗi dữ liệu vĩnh viễn, như thiếu mã đơn hàng, với lỗi tạm thời, như dịch vụ tra cứu khách hàng đang gián đoạn. Hai loại lỗi này cần chính sách xử lý khác nhau: record không hợp lệ thường cần được cách ly hoặc đưa vào DLT, còn lỗi tạm thời có thể được retry.

## 3. Process: xử lý nghiệp vụ có thể retry

Nên đặt nghiệp vụ trong một service riêng thay vì viết toàn bộ logic trong listener. Listener chịu trách nhiệm điều phối luồng; `OrderProcessor` chịu trách nhiệm tạo kết quả nghiệp vụ. Cách tổ chức này giúp kiểm thử logic độc lập và làm rõ thời điểm một exception cần quay lại container.

```java
@Service
public class OrderProcessor {

    public EnrichedOrder enrich(Order order) {
        if (order == null || order.getOrderId() == null) {
            throw new InvalidOrderException("orderId is required");
        }

        // Thực hiện quy tắc nghiệp vụ và tạo kết quả mới.
        return new EnrichedOrder(
                order.getOrderId(),
                order.getCustomerId(),
                calculatePriority(order));
    }

    private String calculatePriority(Order order) {
        return order.getTotal().signum() > 0 ? "NORMAL" : "REVIEW";
    }
}
```

Trong thực tế, processor có thể gọi service nội bộ, tra cứu dữ liệu hoặc áp dụng quy tắc nghiệp vụ. Hãy chú ý các tác dụng phụ. Kafka transaction không thể tự rollback một lệnh ghi database hay một HTTP request đã hoàn tất. Nếu processor cập nhật database rồi sau đó Kafka transaction rollback, dữ liệu database vẫn có thể đã thay đổi.

Với tác dụng phụ bên ngoài Kafka, hãy chọn một chiến lược rõ ràng:

- Thiết kế thao tác **idempotent** bằng một event ID hoặc business key ổn định để lần gọi lặp không tạo thêm hiệu ứng.
- Dùng **transactional outbox** khi cần ghi database và phát sự kiện một cách nhất quán: ghi thay đổi nghiệp vụ và outbox row trong cùng database transaction, sau đó một publisher riêng chuyển outbox row sang Kafka.
- Dùng saga hoặc quy trình bù trừ khi nghiệp vụ trải qua nhiều hệ thống và không thể có một transaction phân tán chung.

Không bắt exception rồi tiếp tục như thể xử lý thành công. Nếu listener nuốt exception, container có thể xem lần xử lý là thành công và commit offset. Khi muốn retry hoặc rollback, hãy để exception phù hợp truyền ra khỏi listener.

## 4. Write: phát kết quả bằng KafkaTemplate

`KafkaTemplate` là abstraction chính của Spring Kafka để gửi record. Dạng gọi thường dùng là:

```java
kafkaTemplate.send(topic, key, value);
```

Key có ý nghĩa quan trọng. Kafka dùng key để chọn partition theo partitioner; các record có cùng key thường đi vào cùng partition và giữ thứ tự trong partition đó. Nếu luồng xử lý cần giữ thứ tự theo `orderId`, hãy dùng `orderId` làm key nhất quán ở cả đầu vào và đầu ra khi mô hình dữ liệu cho phép.

Trong Spring Kafka 3.x, `send()` trả về `CompletableFuture<SendResult<K, V>>`. Việc gửi thường diễn ra bất đồng bộ. Khi listener đang ở trong Kafka transaction do container quản lý, producer transaction sẽ được flush và commit ở cuối lần xử lý; lỗi gửi khiến transaction không thể commit sẽ làm lần xử lý thất bại. Nếu ứng dụng cần đọc metadata của kết quả gửi, có thể gắn callback hoặc chờ future có timeout, nhưng không nên chặn luồng listener nếu không có lý do cụ thể.

Kết quả gửi có thể cung cấp metadata như topic, partition và offset đầu ra. Những thông tin này hữu ích cho log và tracing, nhưng không thay thế việc xác nhận transaction đã commit.

## 5. Gộp output và input offset bằng Kafka transaction

Đây là cách phù hợp khi một listener đọc từ Kafka, biến đổi record rồi ghi kết quả trở lại Kafka và cần bảo đảm hai thao tác được commit cùng nhau.

### 5.1 Cấu hình producer transaction

Với Spring Boot, bật transaction bằng transaction ID prefix:

```yaml
spring:
  kafka:
    producer:
      transaction-id-prefix: ${INSTANCE_ID:local}-
      acks: all
    consumer:
      group-id: order-enricher
      properties:
        isolation.level: read_committed

app:
  topics:
    orders-in: orders.in
    orders-out: orders.enriched
```

`transaction-id-prefix` khiến producer factory có khả năng tạo transactional producer. Prefix phải duy nhất giữa các instance ứng dụng đang chạy để tránh các instance dùng trùng transaction ID và fencing lẫn nhau. Khi chạy nhiều replica, cấp `INSTANCE_ID` riêng cho từng replica; không dùng chung giá trị `local` cho nhiều instance đồng thời.

`acks: all` yêu cầu broker xác nhận theo cấu hình replica trong ISR. Để độ bền thực tế phù hợp với yêu cầu, cần cấu hình thêm replication factor và `min.insync.replicas` ở broker/topic. Transaction bảo đảm tính nguyên tử của các thao tác Kafka; nó không thay thế cấu hình durability của cluster.

### 5.2 Gắn KafkaTransactionManager vào listener container

Listener container phải dùng `KafkaTransactionManager` được tạo từ **cùng `ProducerFactory` mà `KafkaTemplate` sử dụng**. Có thể cấu hình factory theo mẫu sau (các generic type cần khớp với producer factory và serializer của ứng dụng):

```java
@Bean
KafkaTransactionManager<String, Object> kafkaTransactionManager(
        ProducerFactory<String, Object> producerFactory) {
    return new KafkaTransactionManager<>(producerFactory);
}

@Bean
ConcurrentKafkaListenerContainerFactory<String, Order>
orderListenerContainerFactory(
        ConsumerFactory<String, Order> consumerFactory,
        KafkaTransactionManager<String, Object> kafkaTransactionManager) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, Order>();
    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties()
            .setKafkaAwareTransactionManager(kafkaTransactionManager);
    return factory;
}
```

Nếu dùng tên factory tùy chỉnh, trỏ listener tới factory đó bằng thuộc tính `containerFactory` của `@KafkaListener`. Nếu ứng dụng dùng auto-configuration của Spring Boot, hãy kiểm tra bean transaction manager và producer factory được tạo ra, rồi gắn transaction manager vào đúng listener container. Tránh tạo một `ProducerFactory` riêng cho `KafkaTemplate` và một factory khác cho transaction manager, vì hai producer đó không tự tham gia cùng một transaction.

### 5.3 Điều gì xảy ra khi listener chạy?

Với cấu hình trên, trình tự thành công là:

1. Container bắt đầu Kafka transaction.
2. Consumer nhận record đầu vào và gọi listener.
3. Listener chạy nghiệp vụ và gọi `KafkaTemplate.send()`.
4. Producer ghi record đầu ra trong transaction đang mở.
5. Listener trả về thành công.
6. Container đưa offset của record đã xử lý vào transaction.
7. Transaction commit; record đầu ra và offset đầu vào cùng có hiệu lực.

Nếu bước xử lý hoặc gửi đầu ra phát sinh lỗi làm listener thất bại, transaction rollback. Offset chưa được commit nên record đầu vào sẽ được tiêu thụ lại theo chính sách retry của container. Record đầu ra thuộc transaction bị rollback sẽ không được consumer có `read_committed` nhìn thấy.

Consumer đọc dữ liệu transactional nên dùng `isolation.level=read_committed`. Nếu consumer downstream dùng `read_uncommitted`, nó có thể nhìn thấy record thuộc transaction chưa commit hoặc đã bị abort. Mỗi consumer group có thể có cấu hình isolation riêng; hãy kiểm tra cả consumer của topic đầu vào lẫn các consumer đọc output transactional.

## 6. Nếu không dùng transaction: hiểu rõ at-least-once

Một luồng không transactional vẫn có thể đáng tin cậy nếu gửi đầu ra thành công trước khi listener hoàn tất và offset được commit. Tuy nhiên, có một khoảng thời gian giữa hai thao tác:

```text
Gửi output thành công ---- ứng dụng dừng ---- commit input offset
         |                                      |
         +---- output đã tồn tại                +---- offset chưa commit
```

Khi ứng dụng khởi động lại, input record có thể được đọc lại và output bị tạo trùng. Đây là hành vi **at-least-once**: ưu tiên không mất record, nhưng cho phép xử lý lặp.

Với record listener không transactional, có thể chờ xác nhận từ broker trước khi listener trả về:

```java
@KafkaListener(
        topics = "${app.topics.orders-in}",
        containerFactory = "nonTransactionalRecordListenerFactory")
public void onOrder(ConsumerRecord<String, Order> record) throws Exception {
    EnrichedOrder result = processor.enrich(record.value());

    kafkaTemplate.send(outputTopic, record.key(), result)
            .get(10, TimeUnit.SECONDS);
}
```

Ví dụ này chỉ minh họa luồng non-transactional: nếu gửi thất bại hoặc timeout, exception được truyền ra để container không coi record là đã xử lý thành công. Cần chọn timeout phù hợp và xử lý `InterruptedException` đúng cách trong mã production. Khi gửi thành công nhưng commit offset thất bại, output vẫn có thể bị phát lại. Hãy làm cho downstream idempotent hoặc khử trùng lặp bằng event ID ổn định.

Không gọi `send().get()` một cách máy móc trong mọi listener. Chờ future làm tăng thời gian giữ consumer thread và giảm throughput. Trong luồng transactional do container quản lý, transaction commit đã flush producer; chỉ chờ future riêng khi cần lấy kết quả gửi hoặc muốn xử lý lỗi gửi ngay tại vị trí đó.

## 7. Offset và AckMode ảnh hưởng thế nào?

AckMode quy định thời điểm container xác nhận offset sau khi listener xử lý thành công. Với record listener, các lựa chọn thường gặp là:

| AckMode | Thời điểm xác nhận | Hệ quả vận hành |
|---|---|---|
| `RECORD` | Sau mỗi record listener xử lý thành công | Dễ suy luận theo từng record; phù hợp khi muốn ranh giới commit rõ ràng. |
| `BATCH` | Sau khi tất cả record trong một lần poll được xử lý thành công | Giảm số lần commit; nếu batch thất bại, có thể phải xử lý lại nhiều record hơn. |
| `MANUAL` | Khi listener gọi `acknowledge()`; container xử lý commit theo batch semantics | Ứng dụng tự quyết định thời điểm ack và phải quản lý cẩn thận. |
| `MANUAL_IMMEDIATE` | Commit ngay khi `acknowledge()` được gọi trên consumer thread | Kiểm soát sát hơn nhưng dễ tạo logic khó theo dõi nếu ack sai thời điểm. |

Với container transaction, offset được gửi vào Kafka transaction khi container hoàn tất xử lý theo semantics của listener/container. Hãy để container quản lý offset trong mô hình consume-transform-produce thông thường; chỉ dùng manual acknowledgment khi có yêu cầu cụ thể và đã hiểu cách nó tương tác với transaction.

Không bật auto commit của Kafka consumer cho luồng cần điều phối offset cùng output. Hãy để Spring Kafka container quản lý commit. Nếu batch listener được sử dụng, hãy xác định rõ retry và xử lý một phần batch; semantics khác với listener nhận từng record.

## 8. Retry, rollback và Dead Letter Topic

Không phải lỗi nào cũng cần xử lý giống nhau. Một chiến lược thường dùng là:

| Loại lỗi | Ví dụ | Cách xử lý thường phù hợp |
|---|---|---|
| Tạm thời | Broker hoặc dịch vụ phụ thuộc gián đoạn ngắn | Retry có giới hạn với backoff. |
| Dữ liệu không hợp lệ | Thiếu trường bắt buộc, schema không tương thích | Đưa vào DLT hoặc luồng cách ly để điều tra. |
| Lỗi nghiệp vụ không thể phục hồi | Đơn hàng ở trạng thái không cho phép chuyển bước | Ghi nhận lý do và xử lý theo chính sách nghiệp vụ; tránh retry vô hạn. |
| Lỗi hạ tầng kéo dài | Database hoặc dịch vụ phụ thuộc ngừng hoạt động | Dừng/giảm tốc tiêu thụ theo chính sách, theo dõi lag và khôi phục dependency. |

Trong luồng transactional, exception làm transaction rollback. Spring Kafka có `DefaultAfterRollbackProcessor` để điều phối việc seek và retry sau rollback; có thể cấu hình giới hạn lần thử và dead-letter publishing. Khi chuyển record sang DLT, việc publish DLT cũng phải được bảo đảm: nếu publish DLT thất bại, không được âm thầm xác nhận offset gốc như thể đã xử lý xong. Cấu hình xử lý lỗi cần phù hợp với chế độ transaction của container.

Một DLT hữu ích nên giữ lại thông tin nguồn như topic, partition, offset, key, timestamp và exception. Thêm correlation ID hoặc event ID để có thể truy vết record từ đầu vào đến output hoặc DLT. Quy trình replay DLT cần kiểm tra schema và tính idempotent trước khi phát lại, vì replay có thể chạy lại nghiệp vụ.

Retry có backoff giúp tránh tạo tải dồn dập lên dependency đang lỗi. Tuy nhiên, retry kéo dài có thể giữ partition và làm tăng consumer lag. Đặt giới hạn số lần thử, thời gian chờ và chính sách sau khi hết retry dựa trên mức độ quan trọng của luồng. Non-blocking retry bằng retry topic là một mô hình khác với blocking retry/rollback; hãy đánh giá riêng semantics transaction và thứ tự record trước khi kết hợp chúng.

## 9. Giữ thứ tự và tránh xử lý trùng

Kafka chỉ bảo đảm thứ tự trong một partition. Nếu hai sự kiện của cùng một đơn hàng phải được xử lý theo thứ tự, hãy dùng cùng key để chúng được định tuyến vào cùng partition. Tăng số partition hoặc thay đổi partitioner có thể ảnh hưởng cách key được phân bố, vì vậy cần xem xét khi thay đổi topology của topic.

Producer idempotence giúp loại bỏ một số bản ghi trùng do retry ở tầng producer trong một phiên producer. Nó không tự ngăn ứng dụng phát lại cùng một nghiệp vụ sau khi consumer đọc lại input record. Để chống trùng ở cấp nghiệp vụ:

- Mỗi event nên có `eventId` ổn định qua các lần retry.
- Downstream có thể lưu event ID đã xử lý với unique constraint hoặc kho deduplication.
- Các thao tác cập nhật nên có điều kiện hoặc dùng version để tránh áp dụng một sự kiện cũ nhiều lần.
- Khi retry hoặc replay DLT, giữ nguyên event ID gốc; không tạo ID mới cho cùng một sự kiện logic.

Exactly-once trong Kafka giúp đồng bộ output và offset của một Kafka transaction. Idempotency vẫn cần thiết cho database, API, gửi thông báo, thanh toán và mọi tác dụng phụ ngoài transaction đó.

## 10. Các điểm vận hành cần theo dõi

Một luồng read-process-write có thể đúng về logic nhưng vẫn không ổn định khi tải tăng hoặc dependency gặp sự cố. Theo dõi ít nhất các tín hiệu sau:

- **Consumer lag** theo group và partition để biết tốc độ xử lý có theo kịp tốc độ ghi hay không.
- **Thời gian xử lý listener** và thời gian gửi output để phát hiện processor hoặc broker chậm.
- **Số record đọc/ghi**, số lần retry, số rollback và số record vào DLT.
- **Lỗi serialization/deserialization** và lỗi gửi theo topic/partition.
- **Transaction commit/abort** và lỗi producer fencing để phát hiện transaction ID prefix bị dùng trùng.

Log nên có topic, partition, offset, key hoặc event ID và correlation ID. Không ghi toàn bộ payload nhạy cảm vào log. Dùng trace context trong Kafka headers nếu hệ thống có distributed tracing.

Concurrency của listener container nên phù hợp với số partition mà consumer group có thể xử lý song song. Thêm thread vượt quá số partition không làm tăng throughput của group. Nếu xử lý một record mất quá lâu, kiểm tra `max.poll.interval.ms`, `max.poll.records` và thời gian xử lý thực tế để tránh consumer bị xem là không còn hoạt động. Với xử lý dài, cân nhắc giảm số record mỗi poll, tối ưu nghiệp vụ hoặc tách công việc nặng sang một luồng khác có thiết kế xác nhận rõ ràng.

Transaction không nên kéo dài quá mức. Thời gian transaction cần tương thích với transaction timeout, thời gian poll và độ trễ của các dependency. Một transaction giữ quá lâu làm tăng khả năng timeout và làm các consumer `read_committed` phải chờ transaction hoàn tất trước khi đọc tiếp phần dữ liệu liên quan.

## 11. Kiểm thử luồng thành công và các điểm lỗi

Kiểm thử nên bao phủ toàn bộ đường đi từ input đến output và offset, thay vì chỉ kiểm tra processor trả về đúng object. Có thể dùng Embedded Kafka hoặc Kafka Testcontainers để kiểm tra hành vi với broker thật ở phạm vi tích hợp.

Các kịch bản hữu ích gồm:

1. Gửi một record hợp lệ vào input topic; xác nhận output có đúng key và payload.
2. Làm processor ném exception; xác nhận output không được commit và input được retry theo cấu hình.
3. Làm broker từ chối hoặc không thể xác nhận output; xác nhận listener không hoàn tất thành công và offset không bị commit sớm.
4. Dừng ứng dụng ở thời điểm output đã gửi nhưng trước khi offset được commit trong luồng non-transactional; xác nhận hệ thống chấp nhận khả năng output trùng và downstream xử lý idempotent.
5. Với transaction, xác nhận consumer `read_committed` không nhìn thấy output thuộc transaction đã abort.
6. Gửi record không deserialize được hoặc dữ liệu không hợp lệ; xác nhận record được xử lý theo chính sách DLT/cách ly.
7. Replay một event đã xử lý; xác nhận cơ chế idempotency ngăn tác dụng phụ bị lặp.

Kiểm thử tích hợp cần chờ điều kiện rõ ràng như output xuất hiện hoặc offset đạt vị trí mong đợi, thay vì dùng sleep cố định. Dọn topic, consumer group và container sau mỗi bài test để tránh trạng thái cũ ảnh hưởng kết quả.

## 12. Những lỗi thiết kế thường gặp

- **Commit offset trước khi gửi output:** nếu gửi thất bại, input đã được xác nhận và kết quả có thể mất.
- **Gửi output rồi nuốt exception:** container có thể commit offset dù nghiệp vụ hoặc thao tác gửi chưa thành công.
- **Dùng producer factory khác nhau:** `KafkaTemplate` không tham gia transaction do listener container quản lý.
- **Cho rằng Kafka transaction bao phủ database hoặc HTTP:** tác dụng phụ bên ngoài vẫn có thể tồn tại sau rollback.
- **Đọc output transactional bằng `read_uncommitted`:** consumer có thể quan sát record thuộc transaction bị abort.
- **Dùng transaction ID prefix chung cho nhiều instance:** có thể gây producer fencing và lỗi transaction.
- **Retry vô hạn không backoff:** làm tăng tải lên dependency đang lỗi và giữ consumer lag ở mức cao.
- **Dựa vào producer idempotence để chống mọi duplicate:** producer idempotence không thay thế event ID và deduplication ở cấp nghiệp vụ.

## 13. Cách chọn mô hình cho một luồng

| Nhu cầu | Mô hình nên cân nhắc |
|---|---|
| Đọc Kafka, xử lý, ghi Kafka và cần output cùng offset có hiệu lực nguyên tử | Container-managed Kafka transaction với `KafkaTransactionManager` và cùng `ProducerFactory`. |
| Chấp nhận at-least-once, có thể xử lý duplicate ở downstream | Gửi output thành công trước khi listener hoàn tất, sau đó để container commit offset; dùng idempotency. |
| Cập nhật database và phát sự kiện Kafka cần nhất quán | Transactional outbox; không dựa vào Kafka transaction đơn lẻ để commit cả hai hệ thống. |
| Lỗi tạm thời cần thử lại | Blocking retry với backoff hoặc một retry-topic design được cân nhắc riêng về thứ tự và transaction. |
| Record không thể xử lý | Dead Letter Topic có metadata nguồn, giám sát và quy trình replay. |

Khi thiết kế, hãy trả lời rõ ba câu hỏi: **khi nào offset được xác nhận, điều gì xảy ra nếu gửi output thất bại, và tác dụng phụ nào nằm ngoài Kafka transaction?** Câu trả lời cho ba câu hỏi này quyết định liệu luồng đang cung cấp at-least-once hay exactly-once trong phạm vi Kafka, cách retry hoạt động và nơi cần idempotency.
