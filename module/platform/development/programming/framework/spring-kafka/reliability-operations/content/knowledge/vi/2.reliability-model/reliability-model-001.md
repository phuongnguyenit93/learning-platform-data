# At most once, at least once và exactly once

Trong Kafka, ba thuật ngữ **at most once**, **at least once** và **exactly once** mô tả số lần một bản ghi hoặc một hiệu ứng xử lý có thể được ghi nhận khi hệ thống gặp lỗi, retry, khởi động lại hoặc rebalance consumer. Chúng là các *delivery/processing semantics* (ngữ nghĩa giao nhận và xử lý), không phải ba mức chất lượng có thể bật bằng một thuộc tính duy nhất.

Với Spring Kafka, cần xác định rõ guarantee ở từng chặng: producer gửi record, broker lưu record, consumer đọc record, ứng dụng thực hiện nghiệp vụ và consumer commit offset. Một pipeline chỉ đạt guarantee đầu cuối khi các chặng liên quan phối hợp đúng.

## 1. Đặt guarantee vào đúng phạm vi

Một luồng xử lý Kafka thường có dạng:

~~~text
Ứng dụng nguồn
    |
    | KafkaTemplate.send(...)
    v
Kafka topic / partition
    |
    | poll() và gọi @KafkaListener
    v
Ứng dụng consumer
    |
    +---- cập nhật database
    |
    +---- gọi dịch vụ ngoài
    |
    +---- gửi record sang topic khác
    |
    v
Commit consumer offset
~~~

Có ba câu hỏi riêng biệt:

1. **Producer có thể ghi thiếu hoặc ghi trùng không?** Điều này phụ thuộc vào xác nhận của broker, retry và idempotent producer.
2. **Consumer có thể bỏ qua hoặc xử lý lại record không?** Điều này phụ thuộc vào thời điểm commit offset so với thời điểm xử lý.
3. **Hiệu ứng nghiệp vụ có thể xảy ra nhiều lần không?** Điều này phụ thuộc vào nơi lưu hiệu ứng và cách ứng dụng xử lý trùng.

Offset là vị trí consumer group đã xử lý trong một partition. Nếu offset đã được commit, consumer khởi động lại thường tiếp tục từ vị trí kế tiếp. Nếu xử lý đã hoàn tất nhưng offset chưa được commit, record có thể được đọc và xử lý lại. Đây là nguồn phổ biến của duplicate trong mô hình at least once.

| Guarantee | Số lần xử lý/hiệu ứng được quan sát | Rủi ro chính |
|---|---:|---|
| At most once | 0 hoặc 1 | Có thể mất record hoặc bỏ qua nghiệp vụ |
| At least once | 1 hoặc nhiều hơn | Có thể xử lý trùng |
| Exactly once | Chính xác 1 trong phạm vi được bảo vệ | Chỉ đúng trong phạm vi transaction và các hệ thống tham gia |

Không nên suy ra rằng producer dùng acks=all thì toàn bộ ứng dụng đã exactly once. Producer acknowledgement chỉ nói về việc broker xác nhận ghi record; nó không tự động kết hợp việc cập nhật database hay commit offset của consumer.

## 2. At most once — xử lý tối đa một lần

At most once có nghĩa là mỗi record được xử lý **không quá một lần**. Record có thể được xử lý một lần hoặc không được xử lý lần nào. Hệ thống ưu tiên tránh duplicate, chấp nhận khả năng mất dữ liệu khi có lỗi.

### Cách hoạt động

Consumer commit offset trước khi xử lý nghiệp vụ. Nếu ứng dụng dừng ngay sau commit, Kafka cho rằng record đã được xử lý và sẽ không gửi lại record đó cho consumer group. Nghiệp vụ vì vậy có thể chưa từng chạy.

~~~text
1. Consumer nhận record 42
2. Consumer commit offset kế tiếp (43)
3. Ứng dụng bắt đầu xử lý record 42
4. Process bị dừng đột ngột
5. Consumer khởi động lại từ offset 43
6. Record 42 không được xử lý lại
~~~

Một cách khác có thể dẫn đến hành vi tương tự là bật auto commit và để việc commit offset diễn ra trước khi listener hoàn tất công việc. Khi đó, một lần dừng hoặc lỗi ở thời điểm không thuận lợi có thể làm record bị bỏ qua.

### Cấu hình Spring Kafka

Nếu chủ động chọn auto commit, cấu hình có thể như sau:

~~~yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: true
      auto-commit-interval: 1s
~~~

Với Spring Kafka, hãy kiểm tra cấu hình container và phiên bản Spring Kafka đang chạy: listener container thường quản lý commit offset và mặc định tắt auto commit nếu ứng dụng không bật rõ ràng. Khi chọn at most once, cần hiểu chính xác ai đang commit và commit ở thời điểm nào.

Có thể biểu diễn rõ ý định commit trước nghiệp vụ bằng manual acknowledgement:

~~~yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
    listener:
      ack-mode: manual_immediate
~~~

~~~java
@KafkaListener(topics = "telemetry", groupId = "telemetry-fast")
public void consume(
        ConsumerRecord<String, String> record,
        Acknowledgment acknowledgment) {

    // Commit offset trước khi chạy nghiệp vụ.
    acknowledgment.acknowledge();

    process(record.value());
}
~~~

Với MANUAL_IMMEDIATE, acknowledgement được gọi trên consumer thread sẽ yêu cầu commit ngay. Cần cấu hình và kiểm tra commit mode phù hợp nếu ứng dụng thay đổi cách thực thi listener.

### Ưu điểm và giới hạn

At most once phù hợp khi một số mẫu tin có thể bỏ qua mà không gây hậu quả đáng kể, ví dụ telemetry tần suất cao, số liệu đo tức thời hoặc cập nhật trạng thái có thể được thay thế bởi mẫu mới hơn. Nó có thể giảm chi phí xử lý lại và tránh thực hiện một hành động lặp.

Không nên dùng cách này cho thanh toán, tạo đơn hàng, trừ tồn kho, ghi nhận giao dịch hoặc bất kỳ nghiệp vụ nào cần bảo đảm mỗi sự kiện đều được xử lý. Một record bị bỏ qua có thể tạo ra dữ liệu nghiệp vụ sai mà không có lần retry tự động để khôi phục.

## 3. At least once — xử lý ít nhất một lần

At least once bảo đảm hệ thống tiếp tục thử xử lý cho đến khi có một lần xử lý thành công được xác nhận. Một record có thể được xử lý một lần hoặc nhiều lần. Đây là lựa chọn phổ biến cho consumer Kafka vì ưu tiên không bỏ mất sự kiện.

### Cách hoạt động

Consumer chỉ commit offset sau khi listener xử lý thành công. Nếu xử lý thất bại, offset chưa được commit và record có thể được gửi lại. Tuy nhiên, có một khoảng thời gian quan trọng: nghiệp vụ đã hoàn tất nhưng commit offset chưa thành công.

~~~text
1. Consumer nhận record 42
2. Listener xử lý record 42 thành công
3. Database đã cập nhật
4. Process dừng trước khi offset 43 được commit
5. Consumer khởi động lại từ offset 42
6. Listener xử lý record 42 lần nữa
~~~

Kafka không thể tự biết database đã thực hiện nghiệp vụ ở bước 3. Vì vậy, lần xử lý thứ hai có thể tạo ra duplicate nếu ứng dụng không có cơ chế chống trùng.

### Cấu hình Spring Kafka

Với listener xử lý từng record, có thể dùng RECORD acknowledgement mode:

~~~yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
    listener:
      ack-mode: record
~~~

~~~java
@KafkaListener(topics = "orders", groupId = "billing")
public void onOrder(OrderCreated event) {
    billingService.apply(event);
    // Khi listener trả về thành công, container commit offset của record.
}
~~~

Nếu listener ném exception, container có thể chuyển record qua cơ chế retry và error handler đã cấu hình. Offset chỉ được commit theo chính sách xử lý lỗi và phục hồi của container. Cần thiết kế rõ số lần retry, backoff, dead-letter topic (DLT) và điều kiện được xem là đã phục hồi.

### Làm nghiệp vụ idempotent

At least once thường được kết hợp với **idempotency**. Một thao tác idempotent có thể được thực hiện nhiều lần với cùng một event nhưng kết quả nghiệp vụ cuối cùng tương đương với thực hiện một lần.

Mỗi event nên có một định danh ổn định, chẳng hạn eventId. Consumer ghi nhận định danh này cùng với cập nhật nghiệp vụ trong **cùng một transaction database**:

~~~java
@Transactional
public void apply(OrderCreated event) {
    boolean firstDelivery = processedEventRepository
            .insertIfAbsent(event.eventId());

    if (!firstDelivery) {
        // Event đã được áp dụng trước đó; lần giao lại không tạo hiệu ứng mới.
        return;
    }

    billingRepository.createInvoice(event.orderId(), event.amount());
}
~~~

insertIfAbsent ở đây đại diện cho thao tác insert có ràng buộc unique trên event_id; cách triển khai cụ thể phụ thuộc database. Việc ghi nhận event và cập nhật hóa đơn phải cùng commit hoặc cùng rollback. Nếu hai thao tác nằm trong hai transaction độc lập, ứng dụng vẫn có thể tạo ra trạng thái không nhất quán.

Một số cách chống trùng khác:

- Dùng eventId làm idempotency key khi gọi API bên ngoài, nếu API hỗ trợ.
- Dùng khóa nghiệp vụ duy nhất, ví dụ orderId + operationType, để ngăn tạo cùng một hiệu ứng hai lần.
- Dùng upsert hoặc phép cập nhật đặt giá trị cuối cùng thay vì cộng dồn, nếu ý nghĩa nghiệp vụ cho phép.
- Lưu trạng thái xử lý và kết quả trong cùng transaction với dữ liệu nghiệp vụ.

Chỉ kiểm tra một biến trong bộ nhớ hoặc cache tạm thời không đủ để chống trùng qua lần restart, rebalance hoặc triển khai nhiều instance.

### Producer và at least once

Ở phía producer, ứng dụng cần xử lý kết quả gửi và lỗi gửi. Cấu hình acks=all, retry phù hợp và idempotent producer giúp tăng độ tin cậy khi ghi vào Kafka. Tuy nhiên, ứng dụng vẫn cần quan sát kết quả gửi và xử lý trường hợp gửi thất bại hoặc hết thời gian chờ.

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        enable.idempotence: true
        max.in.flight.requests.per.connection: 5
~~~

acks=all yêu cầu broker xác nhận theo toàn bộ replica hiện có trong ISR (in-sync replicas). Kết hợp với min.insync.replicas phù hợp ở broker/topic để tránh chấp nhận ghi khi số replica đồng bộ thấp hơn mức mong muốn.

Idempotent producer ngăn các bản ghi trùng phát sinh từ retry của cùng producer session theo cơ chế sequence của Kafka. Nó không tự nhận diện hai lần gọi send() độc lập của ứng dụng là cùng một sự kiện nghiệp vụ.

## 4. Exactly once — hiệu ứng đúng một lần trong phạm vi xác định

Exactly once có nghĩa là một record tạo ra đúng một hiệu ứng được quan sát trong phạm vi mà cơ chế bảo đảm bao phủ. Với Kafka, cơ chế transaction có thể kết hợp việc ghi các record đầu ra với việc commit offset đầu vào trong một transaction Kafka.

Điểm quan trọng là **exactly once trong Kafka không đồng nghĩa exactly once trên mọi hệ thống bên ngoài Kafka**. Nếu listener cập nhật database, gọi HTTP hoặc gửi lệnh sang một hệ thống khác, Kafka transaction không tự động rollback các tác động đó.

### Kafka transaction bảo vệ điều gì?

Giả sử consumer đọc từ topic orders, xử lý và ghi kết quả sang orders-enriched. Kafka transaction có thể gộp hai thao tác sau:

1. Ghi các record đầu ra vào topic đích.
2. Commit offset của các record đầu vào đã xử lý.

~~~text
Bắt đầu Kafka transaction
    |
    +--> Đọc record từ orders
    |
    +--> Xử lý record
    |
    +--> Ghi record vào orders-enriched
    |
    +--> Đưa offset đầu vào vào transaction
    |
    +--> Commit transaction
             |
             +-- Thành công: output và offset cùng được commit
             |
             +-- Thất bại: transaction bị abort
                         output không hiển thị với read_committed
                         offset đầu vào chưa được commit
~~~

Nếu ứng dụng dừng trước khi transaction commit, record đầu vào sẽ được đọc lại. Record đầu ra của transaction bị abort không được consumer dùng read_committed nhìn thấy. Vì vậy, lần xử lý lại có thể tạo một output hợp lệ mà không làm lộ output của lần transaction thất bại.

### Cấu hình producer và consumer

Producer cần transactional ID prefix. Mỗi instance ứng dụng phải có prefix duy nhất để tránh các producer instance vô tình fencing lẫn nhau. Spring Boot có thể cấu hình như sau:

~~~yaml
spring:
  kafka:
    producer:
      transaction-id-prefix: orders-instance-01-
      acks: all
      properties:
        enable.idempotence: true
    consumer:
      enable-auto-commit: false
      properties:
        isolation.level: read_committed
~~~

Trong ví dụ, orders-instance-01- là giá trị minh họa. Khi chạy nhiều replica, hãy tạo prefix duy nhất cho từng instance theo cách triển khai của hệ thống. Spring Kafka dùng prefix này để tạo transactional producer. Không chia sẻ cùng một prefix giữa các instance độc lập.

Consumer đọc dữ liệu transactional nên dùng isolation.level=read_committed. Nếu dùng read_uncommitted, consumer có thể đọc cả record thuộc transaction chưa commit hoặc đã abort, khiến ứng dụng quan sát dữ liệu chưa được xác nhận.

### Gắn Kafka transaction vào listener container

Spring Kafka cung cấp KafkaTransactionManager. Listener container cần dùng transaction manager này để transaction bao trùm việc xử lý record. KafkaTemplate dùng cùng ProducerFactory sẽ tham gia transaction đang hoạt động trên listener thread.

~~~java
@Configuration
public class KafkaTransactionConfiguration {

    @Bean
    KafkaTransactionManager<String, String> kafkaTransactionManager(
            ProducerFactory<String, String> producerFactory) {
        return new KafkaTransactionManager<>(producerFactory);
    }

    @Bean(name = "kafkaListenerContainerFactory")
    ConcurrentKafkaListenerContainerFactory<String, String> kafkaListenerContainerFactory(
            ConsumerFactory<String, String> consumerFactory,
            KafkaTransactionManager<String, String> transactionManager) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, String>();

        factory.setConsumerFactory(consumerFactory);
        factory.getContainerProperties()
                .setKafkaAwareTransactionManager(transactionManager);

        return factory;
    }
}
~~~

Listener có thể gửi kết quả sang topic khác:

~~~java
@Component
public class OrderEnrichmentListener {

    private final KafkaTemplate<String, String> kafkaTemplate;

    public OrderEnrichmentListener(
            KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @KafkaListener(topics = "orders", groupId = "order-enrichment")
    public void onOrder(String orderPayload) {
        String enriched = enrich(orderPayload);
        kafkaTemplate.send("orders-enriched", enriched);
    }

    private String enrich(String payload) {
        return payload + "|enriched";
    }
}
~~~

Khi listener container được cấu hình với Kafka transaction manager, container bắt đầu transaction trước khi gọi listener. Lệnh gửi qua KafkaTemplate tham gia transaction đó. Khi listener hoàn tất thành công, container đưa offset đầu vào vào transaction và commit. Nếu listener ném exception, transaction bị abort; error handler và chính sách retry quyết định lần xử lý tiếp theo.

Ví dụ trên minh họa luồng consume-transform-produce. Trong ứng dụng thực tế, hãy giữ cùng producer factory cho transaction manager và KafkaTemplate, cấu hình serializer/deserializer phù hợp với kiểu dữ liệu, và kiểm tra listener container đang sử dụng đúng factory có transaction manager.

### Exactly once với Kafka Streams

Nếu ứng dụng dùng Kafka Streams thay vì tự viết listener, có thể cấu hình processing guarantee:

~~~properties
processing.guarantee=exactly_once_v2
~~~

Kafka Streams quản lý transaction cho việc đọc, xử lý và ghi kết quả theo mô hình của Streams. Cần cấu hình application ID ổn định, broker hỗ trợ tính năng tương ứng và các topic nội bộ được tạo/cấu hình phù hợp. Đây là cơ chế riêng của Kafka Streams; không thay thế việc cấu hình transaction cho một Spring Kafka listener thông thường.

## 5. Giới hạn khi nghiệp vụ có database hoặc dịch vụ bên ngoài

Một Kafka transaction có thể nguyên tử hóa các thao tác Kafka nằm trong transaction. Nó không thể tự động bao gồm một transaction của PostgreSQL/MySQL, một lệnh HTTP đến payment gateway hoặc một thao tác trên hệ thống bên ngoài.

Ví dụ:

~~~text
Consumer nhận OrderCreated
    |
    +--> Ghi invoice vào database: COMMIT thành công
    |
    +--> Gửi Kafka output
    |
    +--> Kafka transaction ABORT
~~~

Database đã lưu invoice, nhưng transaction Kafka thất bại. Kafka giao lại event và consumer có thể tạo invoice lần nữa. Gắn @Transactional vào method không tự làm cho database transaction và Kafka transaction trở thành một transaction phân tán nguyên tử. Hai transaction manager khác nhau vẫn có thể commit/rollback ở các thời điểm khác nhau.

Có hai mẫu thiết kế thường dùng:

### Inbox hoặc bảng processed events

Consumer lưu eventId vào bảng có unique constraint trong cùng database transaction với thay đổi nghiệp vụ. Khi Kafka giao lại event, insert trùng bị nhận diện và consumer bỏ qua hiệu ứng đã thực hiện. Đây là cách phổ biến để có at least once delivery nhưng vẫn giữ một hiệu ứng nghiệp vụ trong database.

### Transactional outbox

Nếu một transaction database vừa cập nhật dữ liệu vừa cần phát event, ứng dụng ghi dữ liệu nghiệp vụ và một dòng outbox trong cùng database transaction. Một tiến trình relay hoặc CDC đọc outbox rồi gửi event sang Kafka. Nếu relay gửi lại do chưa ghi nhận được kết quả, consumer tiếp nhận vẫn nên idempotent.

~~~text
Database transaction
    |
    +--> Update business tables
    |
    +--> Insert outbox event
    |
    +--> Commit
             |
             v
      Outbox relay / CDC
             |
             v
           Kafka
~~~

Outbox giải quyết khoảng trống giữa cập nhật database và phát event. Nó không khiến mọi consumer bên ngoài tự nhiên exactly once; phía nhận vẫn cần xử lý duplicate an toàn.

## 6. So sánh theo tình huống lỗi

| Tình huống | At most once | At least once | Kafka exactly once (consume-transform-produce) |
|---|---|---|---|
| Process dừng trước khi xử lý | Có thể record đã bị commit và mất | Offset chưa commit nên có thể đọc lại | Transaction abort; input có thể đọc lại |
| Process dừng sau xử lý, trước commit offset | Nếu offset đã commit trước đó thì không chạy lại | Có thể xử lý lại và tạo duplicate | Output và offset cùng transaction nên không lộ output đã abort |
| Broker tạm thời không sẵn sàng | Có thể bỏ qua tùy cách commit | Retry và xử lý lỗi gửi/nhận | Transaction có thể abort hoặc retry theo cấu hình |
| Database đã commit nhưng Kafka offset chưa commit | Có thể mất record nếu commit offset sớm | Có thể cập nhật database lần nữa | Kafka transaction không rollback database |
| Producer retry cùng một send | Có thể mất nếu không retry | Có thể phát sinh duplicate nếu không có idempotence | Idempotent producer và transaction bảo vệ ghi Kafka trong phạm vi tương ứng |

Bảng này mô tả hành vi tổng quát. Kết quả cụ thể còn phụ thuộc vào retry policy, error handler, acknowledgement mode, commit mode, transaction timeout, loại listener và hệ thống lưu hiệu ứng nghiệp vụ.

## 7. Chọn mô hình nào?

| Nhu cầu | Hướng lựa chọn | Điều cần triển khai |
|---|---|---|
| Dữ liệu đo có thể bỏ qua, ưu tiên không lặp | At most once | Commit trước xử lý; chấp nhận khả năng mất |
| Sự kiện nghiệp vụ phải được xử lý, retry được | At least once | Commit sau xử lý; idempotency ở consumer |
| Đọc Kafka, biến đổi và ghi sang Kafka khác | Kafka exactly once | Transactional producer, transaction-enabled listener container, offset trong transaction, consumer đầu ra dùng read_committed |
| Đọc Kafka rồi cập nhật database | At least once + idempotent database operation | Event ID, unique constraint, transaction database |
| Cập nhật database rồi phát event | Transactional outbox | Ghi outbox cùng transaction database, relay/CDC, consumer idempotent |
| Xử lý topology Kafka Streams | Kafka Streams exactly once | processing.guarantee=exactly_once_v2 và cấu hình Streams phù hợp |

Trong nhiều hệ thống nghiệp vụ, lựa chọn thực tế là at least once cộng với idempotent processing. Cách này dễ quan sát và phục hồi, đồng thời giữ được độ tin cậy khi consumer restart hoặc rebalance. Exactly once qua Kafka transaction đặc biệt hữu ích khi đầu vào và đầu ra đều nằm trong Kafka. Với database hoặc API bên ngoài, hãy thiết kế idempotency hoặc outbox/inbox theo ranh giới transaction thực tế.

## 8. Các cấu hình và hành vi cần kiểm tra

**Consumer offset**

- Tắt auto commit khi muốn listener container kiểm soát thời điểm commit.
- Chọn RECORD cho listener xử lý từng record khi cần commit sau mỗi record; chọn batch mode khi listener xử lý theo batch và hiểu rõ phạm vi commit.
- Với manual acknowledgement, xác định rõ MANUAL hay MANUAL_IMMEDIATE, thread gọi acknowledgement và cách container thực hiện commit.
- Không commit offset trước khi nghiệp vụ hoàn tất nếu yêu cầu là at least once.
- Kiểm tra hành vi khi rebalance, shutdown và listener xử lý lâu.

**Producer và broker**

- Chọn acks=all và min.insync.replicas theo yêu cầu durability.
- Bật idempotent producer để bảo vệ retry ở producer.
- Thiết lập retry, delivery.timeout.ms và xử lý lỗi gửi rõ ràng; không xem việc gọi send() là bằng chứng record đã được broker xác nhận.
- Theo dõi ISR, under-replicated partitions và lỗi producer.

**Transaction**

- Mỗi ứng dụng instance cần transactional ID prefix duy nhất.
- Consumer đọc dữ liệu transactional cần read_committed nếu không muốn thấy record chưa commit hoặc đã abort.
- Giữ transaction đủ ngắn; xử lý lâu có thể vượt transaction timeout.
- Xử lý ProducerFencedException và các lỗi transaction theo vòng đời instance, không retry vô hạn một producer đã bị fencing.
- Xác nhận KafkaTemplate và listener container dùng producer factory/transaction manager tương thích.
- Kiểm tra transaction abort, commit timeout và consumer lag trong vận hành.

**Retry và dead-letter topic**

- Retry có thể khiến cùng event được xử lý nhiều lần; nghiệp vụ phải chịu được điều đó.
- DLT giúp giữ record không xử lý được để điều tra hoặc phục hồi. Chuyển record sang DLT và commit offset cần được cấu hình theo chính sách rõ ràng.
- Nếu cần giữ thứ tự trong partition, cân nhắc tác động của retry topic, non-blocking retry và việc đưa record sang DLT.
- Không coi việc đưa record vào DLT là nghiệp vụ đã thành công; cần có quy trình theo dõi và phát lại.

## 9. Những nhầm lẫn thường gặp

1. **Idempotent producer đồng nghĩa exactly once end-to-end.** Không đúng. Nó bảo vệ retry của producer; không chống hai lần gửi độc lập và không bảo vệ cập nhật database.
2. **acks=all đồng nghĩa consumer không bao giờ xử lý trùng.** Không đúng. Producer acknowledgement không quyết định thời điểm consumer commit offset.
3. **Commit offset sau listener đồng nghĩa không có duplicate.** Không đúng. Process có thể dừng sau khi nghiệp vụ hoàn tất nhưng trước khi commit offset.
4. **Kafka transaction bao gồm database vì listener có @Transactional.** Không đúng. Cần xem transaction manager nào quản lý từng thao tác; Kafka transaction không tự rollback một transaction database độc lập.
5. **Bật read_committed là đủ để có exactly once.** Không đúng. Nó chỉ quyết định consumer đọc dữ liệu transactional nào; producer và listener vẫn phải tham gia transaction đúng cách.
6. **Retry càng nhiều thì guarantee càng mạnh.** Retry tăng cơ hội thành công nhưng cũng tăng khả năng xử lý lặp. Cần kết hợp retry với idempotency, giới hạn retry và quy trình phục hồi.

## 10. Checklist thiết kế

Trước khi chọn guarantee cho một luồng Spring Kafka, hãy trả lời các câu hỏi sau:

- Nếu một record không được xử lý, tác động nghiệp vụ là gì?
- Nếu cùng record được xử lý hai lần, có thể tạo ra khoản trừ tiền, hóa đơn hoặc thông báo trùng không?
- Offset được commit trước hay sau khi listener hoàn tất?
- Listener dùng record, batch hay manual acknowledgement?
- Producer có kiểm tra kết quả gửi, retry và idempotence không?
- Dữ liệu đầu ra có nằm trong cùng Kafka transaction với offset đầu vào không?
- Consumer đọc dữ liệu transactional có đặt read_committed không?
- Database/API bên ngoài có idempotency key, inbox hoặc outbox không?
- Retry, DLT, rebalance và shutdown có hành vi đã được xác định không?
- Metrics và log có đủ để phát hiện duplicate, record bị bỏ qua, transaction abort và consumer lag không?

Một thiết kế đáng tin cậy cần nêu rõ guarantee theo từng ranh giới, thời điểm commit, phạm vi transaction và cách xử lý duplicate. Khi các điều kiện đó được xác định, nhóm phát triển có thể chọn at most once cho dữ liệu cho phép mất, at least once cho sự kiện cần phục hồi, hoặc Kafka exactly once cho luồng consume-transform-produce nằm trọn trong Kafka.
