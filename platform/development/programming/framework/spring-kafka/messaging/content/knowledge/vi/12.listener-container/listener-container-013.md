# ContainerProperties.EOSMode và các lựa chọn hiện đại

Khi một Kafka listener đọc record, xử lý dữ liệu rồi gửi kết quả sang topic khác, ứng dụng cần bảo đảm rằng kết quả và offset đầu vào được ghi nhận nhất quán. Nếu output đã được ghi nhưng offset chưa commit, record đầu vào có thể được đọc lại và tạo output trùng. Nếu offset đã commit nhưng output chưa được ghi, kết quả có thể bị mất. Kafka transaction kết hợp với Spring Kafka listener container giải quyết khoảng trống này bằng cách đưa output và offset của input vào cùng một transaction.

`ContainerProperties.EOSMode` xác định cơ chế Exactly Once Semantics (EOS) mà listener container sử dụng khi chạy với transaction. Ở các phiên bản Spring Kafka hiện đại, lựa chọn được hỗ trợ là `V2`. Để dùng EOS, chỉ đặt `EOSMode` là chưa đủ: producer factory phải hỗ trợ transaction, listener container phải được gắn `KafkaAwareTransactionManager`, và broker phải đáp ứng yêu cầu tương thích.

## 1. EOS giải quyết vấn đề gì trong consumer?

Giả sử service `order-projection` đọc sự kiện từ topic `orders.in`, tính trạng thái đơn hàng rồi gửi kết quả đến `orders.out`.

Nếu không dùng transaction, hai thao tác sau độc lập:

1. Gửi kết quả vào `orders.out`.
2. Commit offset của record đã đọc từ `orders.in`.

Có thể xảy ra hai cửa sổ lỗi:

- Output đã được ghi nhưng ứng dụng dừng trước khi commit offset. Record đầu vào được đọc lại và output có thể được ghi lần nữa.
- Offset đã commit nhưng ứng dụng dừng trước khi output được ghi thành công. Consumer sẽ không đọc lại record đó theo offset đã commit và kết quả có thể bị thiếu.

Với Kafka transaction, Spring Kafka có thể ghi output và offset đầu vào trong cùng transaction. Broker chỉ công bố transaction khi toàn bộ thao tác commit thành công.

```text
orders.in
    |
    v
Consumer đọc record
    |
    v
Listener xử lý nghiệp vụ
    |
    +---- KafkaTemplate gửi kết quả ----> orders.out
    |
    +---- Offset đầu vào ----------------> Kafka transaction
                                              |
                                              v
                                        COMMIT hoặc ABORT
```

Nếu listener hoàn tất thành công, container gửi offset vào transaction bằng `sendOffsetsToTransaction()` rồi commit transaction. Nếu listener ném exception, transaction bị rollback và consumer được reposition để record có thể được đọc lại. Các consumer downstream dùng `isolation.level=read_committed` chỉ nhìn thấy output thuộc transaction đã commit.

## 2. `ContainerProperties.EOSMode` là gì?

`ContainerProperties` chứa các thiết lập điều khiển listener container, trong đó `eosMode` chọn cơ chế fencing được sử dụng cho Exactly Once Semantics. Enum này được bổ sung từ Spring Kafka 2.5.

Hai cách triển khai từng được sử dụng là V1 và V2:

| Mode | Cơ chế | Yêu cầu và tình trạng |
| --- | --- | --- |
| `V1` | Fencing dựa trên `transactional.id`; Spring Kafka cũ dùng producer riêng theo group/topic/partition cho listener record để ngăn consumer cũ tiếp tục ghi | Dành cho broker cũ từ 0.11 đến trước 2.5; đã bị loại khỏi lựa chọn của Spring Kafka 3.0 trở lên |
| `V2` | Fetch-offset-request fencing; consumer metadata được gửi cùng offset vào transaction để broker xác định producer còn hợp lệ hay đã bị fence | Yêu cầu Kafka broker 2.5 trở lên; là mode duy nhất được Spring Kafka 3.0+ hỗ trợ |

V2 giảm nhu cầu tạo producer riêng cho từng tổ hợp consumer group/topic/partition. Broker dùng metadata consumer đi kèm offset transaction để kiểm tra fencing. Cơ chế này được mô tả trong KIP-447.

Trong một số phiên bản Spring Kafka 2.x cũ, enum còn có các tên `ALPHA` và `BETA` như alias lịch sử của `V1` và `V2`; chúng đã deprecated. Khi đọc code cũ, cần đối chiếu đúng phiên bản thư viện. Với Spring Kafka 3.x và 4.x, không chọn `V1`, `ALPHA` hoặc `BETA`; chỉ dùng `V2`.

## 3. Mode mặc định và cách cấu hình hiện đại

`EOSMode.V2` là giá trị mặc định của `ContainerProperties` trong các dòng Spring Kafka hiện đại. Do đó, với Spring Kafka 3.x/4.x, thông thường không cần đặt lại `eosMode` bằng code.

Nếu muốn thể hiện rõ cấu hình trong một listener container tự tạo:

```java
import org.springframework.kafka.listener.ContainerProperties;

factory.getContainerProperties()
        .setEosMode(ContainerProperties.EOSMode.V2);
```

Lệnh trên chỉ chọn cơ chế EOS V2. Nó không tự tạo transaction, không bật transaction cho producer và không gắn transaction manager vào container. Các thành phần đó phải được cấu hình riêng.

Không nên cố đặt `spring.kafka.listener.eos-mode=V1` trong cấu hình ứng dụng hiện đại. `EOSMode` là thiết lập của `ContainerProperties`; Boot không cung cấp lựa chọn V1 để khôi phục cơ chế cũ trong Spring Kafka 3.0+.

## 4. Bật transaction cho producer factory

Spring Kafka bật transaction khi `DefaultKafkaProducerFactory` được cấu hình `transactionIdPrefix`. Factory sẽ quản lý cache các transactional producer; `transactional.id` của mỗi producer được tạo từ prefix cộng với hậu tố do factory cấp.

Với Spring Boot, cách cấu hình ngắn nhất là khai báo `spring.kafka.producer.transaction-id-prefix`:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      transaction-id-prefix: ${INSTANCE_ID:local}-orders-tx-
    consumer:
      group-id: order-projection
      properties:
        "[isolation.level]": read_committed
```

Khi property transaction ID prefix được đặt, Spring Boot tự cấu hình `KafkaTransactionManager` và gắn nó vào listener container được auto-configure. Với môi trường chạy nhiều instance, `INSTANCE_ID` phải duy nhất cho từng instance, ví dụ pod name hoặc instance identifier do nền tảng triển khai cấp. Không dùng cùng prefix trên các instance đồng thời vì chúng có thể tranh chấp `transactional.id` và fence producer của nhau.

Giá trị `local` chỉ phù hợp khi chạy một instance local. Khi chạy nhiều replica, hãy cấp prefix riêng cho từng replica.

## 5. Gắn KafkaTransactionManager vào listener container

Nếu không dùng Spring Boot auto-configuration hoặc tự tạo listener container factory, cần gắn `KafkaAwareTransactionManager` vào `ContainerProperties`.

Ví dụ với producer factory đã được cấu hình transaction ID prefix:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.core.ProducerFactory;
import org.springframework.kafka.transaction.KafkaTransactionManager;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.listener.ContainerProperties;

@Configuration
public class KafkaTransactionConfiguration {

    @Bean
    public KafkaTransactionManager<String, String> kafkaTransactionManager(
            ProducerFactory<String, String> producerFactory) {
        return new KafkaTransactionManager<>(producerFactory);
    }

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, String>
            kafkaListenerContainerFactory(
                    ConsumerFactory<String, String> consumerFactory,
                    KafkaTransactionManager<String, String> transactionManager) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, String>();
        factory.setConsumerFactory(consumerFactory);
        factory.getContainerProperties()
                .setKafkaAwareTransactionManager(transactionManager);
        factory.getContainerProperties()
                .setEosMode(ContainerProperties.EOSMode.V2);
        return factory;
    }
}
```

Đoạn code giả định `ProducerFactory` đã được cấu hình `transactionIdPrefix` và `ConsumerFactory` đã có bootstrap server, deserializer cùng các thuộc tính bảo mật cần thiết. `KafkaTemplate` dùng để gửi output phải sử dụng cùng producer factory với transaction manager để các lệnh gửi tham gia đúng transaction.

Trong Spring Kafka 3.2 trở lên, dùng `setKafkaAwareTransactionManager(...)`. API `setTransactionManager(PlatformTransactionManager)` cũ đã deprecated từ 3.2 và được thay thế bằng API chuyên biệt này.

## 6. Luồng read-process-write với EOS V2

Ví dụ listener đọc một sự kiện đơn hàng, chuyển đổi payload và gửi kết quả sang topic khác:

```java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;

@Component
public class OrderProjectionListener {

    private final KafkaTemplate<String, String> kafkaTemplate;

    public OrderProjectionListener(
            KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @KafkaListener(
            topics = "orders.in",
            groupId = "order-projection")
    public void process(ConsumerRecord<String, String> record) {
        String projection = transform(record.value());

        kafkaTemplate.send(
                "orders.out",
                record.key(),
                projection);
    }

    private String transform(String event) {
        return "projection:" + event;
    }
}
```

Khi listener container đã được gắn `KafkaTransactionManager`, container bắt đầu Kafka transaction trước khi gọi `process`. Lệnh `KafkaTemplate.send` tham gia transaction đang hoạt động. Khi listener hoàn tất, container gửi offset đầu vào vào cùng transaction rồi commit.

Nếu `transform` hoặc lệnh gửi phát sinh exception và exception được truyền ra khỏi listener, container rollback transaction. Record đầu vào có thể được đọc lại và listener có thể chạy lần nữa. Vì vậy, EOS không có nghĩa phương thức Java chỉ được gọi đúng một lần; nó bảo đảm kết quả Kafka của chuỗi read-process-write được commit theo transaction, tránh để output của lần thử đã rollback trở thành dữ liệu được consumer `read_committed` nhìn thấy.

Không bắt exception rồi bỏ qua nếu nghiệp vụ cần rollback. Nếu listener bắt exception và kết thúc bình thường, container có thể xem lần xử lý là thành công và commit transaction.

## 7. Vai trò của isolation.level=read_committed

Kafka consumer có hai mức isolation phổ biến:

| Giá trị | Hành vi |
| --- | --- |
| `read_uncommitted` | Có thể đọc record thuộc transaction đang mở hoặc transaction cuối cùng bị abort |
| `read_committed` | Chỉ trả record thuộc transaction đã commit; bỏ qua dữ liệu thuộc transaction chưa hoàn tất hoặc đã abort |

Để downstream không nhìn thấy output của transaction đã rollback, consumer đọc topic output cần dùng `isolation.level=read_committed`. Trong Spring Boot:

```yaml
spring:
  kafka:
    consumer:
      properties:
        "[isolation.level]": read_committed
```

Nếu consumer downstream vẫn dùng `read_uncommitted`, nó có thể nhìn thấy record thuộc transaction đã abort và ứng dụng sẽ không quan sát được lợi ích đầy đủ của transaction. Cần thống nhất isolation level cho các consumer tham gia luồng xử lý transactional.

## 8. EOS bảo đảm điều gì và không bảo đảm điều gì?

Phạm vi của EOS trong Spring Kafka là chuỗi `read → process → write` khi input offset và output record được tham gia cùng Kafka transaction.

| Tình huống | EOS V2 xử lý thế nào |
| --- | --- |
| Listener gửi output rồi hoàn tất | Output và offset input được commit cùng transaction |
| Listener ném exception trước commit | Transaction abort; output chưa commit không hiển thị với consumer `read_committed`; input có thể được đọc lại |
| Consumer cũ tiếp tục ghi sau khi partition đã chuyển sang consumer mới | Broker fencing ngăn producer cũ tiếp tục hoàn tất transaction không hợp lệ |
| Listener cập nhật database rồi gửi Kafka | Kafka transaction không tự bao trùm database transaction |
| Listener gọi HTTP hoặc gửi email | Tác động bên ngoài Kafka không được Kafka transaction rollback |

Đọc và xử lý vẫn có thể được thực hiện lại sau rollback hoặc lỗi. Vì vậy, cần phân biệt “sequence có kết quả Kafka được commit exactly once” với “code nghiệp vụ chỉ chạy một lần”.

EOS cũng không tự tạo transaction phân tán nguyên tử giữa Kafka và relational database, HTTP service, email provider hoặc hệ thống lưu trữ khác. Nếu listener cập nhật database rồi gửi Kafka, lỗi giữa hai thao tác vẫn có thể tạo trạng thái lệch. Có thể dùng transactional outbox/inbox, idempotency key hoặc quy trình bù trừ để xử lý ranh giới đó.

## 9. Producer idempotence khác với EOS

Kafka producer idempotence giúp tránh ghi trùng record do producer retry trong các điều kiện được hỗ trợ. Nó không tự kết hợp offset consumer với output record.

| Cơ chế | Phạm vi |
| --- | --- |
| Idempotent producer | Chống duplicate do retry ở phía producer |
| Kafka transaction | Nhóm nhiều thao tác ghi Kafka và/hoặc offset vào một transaction |
| Listener container EOS V2 | Kết hợp xử lý record, gửi output và commit offset input trong transaction |
| Idempotent business handler | Chịu được việc listener được gọi lại hoặc nhận duplicate từ nguồn khác |
| Outbox/inbox | Giải quyết tính nhất quán giữa database và messaging ở ranh giới ứng dụng |

Chỉ bật producer idempotence không đủ để tuyên bố một consumer read-process-write có EOS. Cần transaction do listener container quản lý và offset được gửi vào cùng transaction với output.

## 10. Record listener và batch listener

Với record listener, container có thể thực hiện một transaction cho từng record. Khi listener thành công, output và offset của record được commit cùng nhau.

Với batch listener, container xử lý một tập record nhận được từ một poll. Nếu batch listener phát sinh exception, mặc định cả batch có thể được đọc lại sau rollback vì framework không thể luôn xác định chính xác record nào trong batch gây lỗi. Điều này cần được tính đến khi chọn kích thước batch và thiết kế thao tác nghiệp vụ.

Có thể dùng `AfterRollbackProcessor` để xử lý sau rollback, retry record hoặc phục hồi record lỗi theo chính sách. Với batch listener, hãy xác định rõ phạm vi batch, chiến lược recovery và khả năng xử lý lặp trước khi đưa vào production.

## 11. Retry và dead-letter khi dùng container transaction

Khi listener chạy trong container transaction, lỗi sẽ khiến transaction rollback. Spring Kafka có thể dùng `AfterRollbackProcessor` để seek, retry và cuối cùng recover record lỗi, chẳng hạn chuyển đến dead-letter topic.

Một điểm cần lưu ý là **non-blocking retry topics** (ví dụ `@RetryableTopic`) không thể kết hợp với container transactions. Với cơ chế non-blocking retry, khi listener ném exception, transaction của container được commit và record được gửi sang retry topic theo cơ chế riêng; điều đó không tương đương rollback toàn bộ read-process-write transaction.

Nếu yêu cầu là giữ tính nguyên tử của output và offset, hãy thiết kế retry theo transaction/rollback phù hợp, thường là blocking retry và `AfterRollbackProcessor`. Nếu ưu tiên không giữ partition chờ retry và chấp nhận mô hình retry topic riêng, cần đánh giá lại yêu cầu EOS của luồng đó.

## 12. Transaction ID prefix và fencing khi chạy nhiều instance

Mỗi transactional producer có một `transactional.id`. Với EOS V2, không còn cần transactional ID cố định cho từng group/topic/partition, nhưng prefix vẫn phải duy nhất giữa các application instance đang chạy đồng thời.

Ví dụ:

```text
Instance A: orders-projection-pod-a-orders-tx-0
Instance B: orders-projection-pod-b-orders-tx-0
```

Nếu hai instance dùng cùng prefix, chúng có thể tạo cùng transactional ID. Khi một producer khởi tạo transaction với ID đã được instance khác sử dụng, producer trước có thể bị fence và nhận `ProducerFencedException`.

Một số lưu ý vận hành:

- Tạo prefix từ application name cộng với instance ID duy nhất.
- Không dùng giá trị cố định giống nhau cho mọi pod/replica.
- Khi scale deployment, bảo đảm mỗi instance nhận giá trị riêng.
- Theo dõi `ProducerFencedException`, transaction timeout và lỗi coordinator.
- Nếu transactional producer có thể idle lâu hơn `transactional.id.expiration.ms` của broker, xem xét cấu hình `maxAge` của producer factory thấp hơn thời hạn broker để factory làm mới producer trước khi bị fence do hết hạn.

## 13. Cấu hình broker và yêu cầu triển khai

EOS V2 yêu cầu Kafka broker từ phiên bản 2.5 trở lên. Ngoài tương thích version, cluster phải vận hành transaction coordinator và topic nội bộ `__transaction_state` đúng cấu hình.

Trong production, cần kiểm tra các thiết lập như replication factor và min ISR của transaction state log, thời gian transaction, dung lượng broker và khả năng phục hồi coordinator. Với cluster một broker dùng để học tập, các giá trị replication factor có thể phải đặt bằng một; cấu hình đó không cung cấp độ bền và khả năng chịu lỗi tương đương cluster nhiều broker.

Producer transaction cũng cần có quyền phù hợp để ghi topic đích và sử dụng transactional ID. Nếu cluster bật ACL, kiểm tra quyền `Write`, `Describe` và các quyền transactional ID theo cơ chế bảo mật của nền tảng.

## 14. Khi nào nên dùng EOS V2 và khi nào chọn cách khác?

EOS có chi phí vận hành và độ trễ transaction. Không phải mọi listener đều cần transactional read-process-write.

| Nhu cầu | Lựa chọn phù hợp |
| --- | --- |
| Đọc Kafka, biến đổi và ghi sang Kafka; cần output và offset nguyên tử | Container transaction với EOS V2 |
| Chỉ đọc và cập nhật một projection có thể xử lý lặp | Listener thông thường, commit theo AckMode và business idempotency |
| Gửi event từ database sau khi commit dữ liệu | Transactional outbox và publisher riêng |
| Cần retry không chặn partition bằng retry topics | Non-blocking retry; không dùng cùng container transaction cho luồng đó |
| Chỉ cần chống duplicate do producer retry | Producer idempotence; không cần container EOS nếu không có consume-process-write |
| Gọi API ngoài hoặc gửi email trong listener | Idempotency key, outbox hoặc cơ chế bù trừ; Kafka EOS không rollback tác động ngoài Kafka |

Hãy chọn EOS khi giá trị của việc commit output và offset cùng nhau lớn hơn chi phí transaction. Với consumer chỉ cập nhật trạng thái có thể idempotent, mô hình at-least-once đơn giản có thể dễ vận hành hơn.

## 15. Phân biệt container transaction và producer transaction

Spring Kafka có nhiều cách tạo Kafka transaction. Chúng có mục đích liên quan nhưng không thay thế cho nhau:

| Cách bắt đầu transaction | Phạm vi chính | Có tự đưa offset input vào transaction không? |
| --- | --- | --- |
| Listener container dùng `KafkaAwareTransactionManager` | Read-process-write trong listener | Có; container gửi offset vào transaction trước khi commit |
| `@Transactional` với `KafkaTransactionManager` | Một nhóm thao tác gửi Kafka từ service | Không tự động; đây là producer-initiated transaction |
| `TransactionTemplate` với `KafkaTransactionManager` | Điều khiển transaction producer bằng code | Không tự động |
| `KafkaTemplate.executeInTransaction(...)` | Một nhóm thao tác gửi Kafka trong transaction cục bộ | Không; callback chỉ nhóm các thao tác producer |
| Listener không có transaction manager | Xử lý record và commit offset theo AckMode | Không; dùng semantics commit thông thường của container |

Ví dụ `KafkaTemplate.executeInTransaction`:

```java
kafkaTemplate.executeInTransaction(operations -> {
    operations.send("orders.audit", orderId, auditEvent);
    operations.send("orders.projection", orderId, projectionEvent);
    return true;
});
```

Nếu callback kết thúc bình thường, transaction được commit; nếu exception thoát khỏi callback, transaction bị rollback. Đây là transaction cho các lệnh gửi trong callback. Nó không đưa offset của một listener đang xử lý vào transaction đó.

Nếu một Kafka transaction đã được mở bởi `KafkaTransactionManager` hoặc transaction synchronization, `executeInTransaction` tạo một transaction lồng mới thay vì tham gia transaction đang có. Vì vậy, trong listener container đang chạy EOS, hãy gọi trực tiếp `KafkaTemplate.send(...)` để thao tác gửi tham gia transaction của container; không bọc các lệnh đó bằng `executeInTransaction` nếu mục tiêu là cùng transaction với offset đầu vào.

## 16. Checklist kiểm tra EOS V2

Trước khi đưa listener transactional vào môi trường chạy thật, kiểm tra:

- [ ] Spring Kafka phiên bản 3.0 trở lên chỉ dùng `EOSMode.V2`.
- [ ] Kafka broker từ phiên bản 2.5 trở lên.
- [ ] Producer factory có `transactionIdPrefix` và hỗ trợ transaction.
- [ ] `transactionIdPrefix` duy nhất cho từng application instance.
- [ ] Listener container được gắn `KafkaAwareTransactionManager`.
- [ ] `KafkaTemplate` dùng cùng producer factory với transaction manager.
- [ ] Consumer downstream đọc transactional output bằng `isolation.level=read_committed`.
- [ ] Listener ném exception khi nghiệp vụ cần rollback; không nuốt lỗi ngoài ý muốn.
- [ ] Retry và DLT được thiết kế phù hợp với container transaction.
- [ ] Không ghép `@RetryableTopic` non-blocking retry với container transactions.
- [ ] Database và external side effect có outbox/inbox hoặc idempotency riêng.
- [ ] Kiểm thử cả commit thành công, rollback, redelivery và fencing.

## 17. Kiểm thử hành vi commit và rollback

Kiểm thử tích hợp cần xác minh kết quả mà consumer `read_committed` nhìn thấy, thay vì chỉ kiểm tra listener có được gọi. Một kịch bản nên gồm:

1. Gửi record vào topic input.
2. Listener đọc record, gửi output trong transaction và hoàn tất thành công.
3. Xác nhận consumer `read_committed` nhận được output và offset input đã tiến lên.
4. Gửi một record khác khiến listener ném exception sau khi gọi `KafkaTemplate.send`.
5. Xác nhận output thuộc transaction rollback không xuất hiện với consumer `read_committed`.
6. Xác nhận record input có thể được retry/redeliver theo cấu hình after-rollback processor.

Ngoài ra, kiểm thử nhiều instance với prefix khác nhau, dừng/restart consumer trong lúc xử lý và quan sát log fencing. Test cần chờ transaction và consumer assignment hoàn tất bằng điều kiện/timeout rõ ràng; tránh chỉ dùng `Thread.sleep` cố định rồi kết luận.

## 18. Kết luận

`ContainerProperties.EOSMode` điều khiển cơ chế Exactly Once Semantics của listener container. V1 là cơ chế fencing cũ dựa trên transactional ID; V2 dùng fetch-offset-request fencing và yêu cầu broker Kafka 2.5 trở lên. Spring Kafka 3.0 và các phiên bản hiện đại chỉ hỗ trợ V2, đồng thời đặt V2 làm mặc định.

Để có EOS thực sự, cần cấu hình transactional producer factory, transaction ID prefix duy nhất cho từng instance và `KafkaAwareTransactionManager` trên listener container. Container sẽ đưa output do `KafkaTemplate` gửi cùng offset input vào một Kafka transaction. Phạm vi bảo đảm là kết quả Kafka của chuỗi read-process-write; listener vẫn có thể chạy lại và database hoặc external side effect cần cơ chế nhất quán riêng.

## Tài liệu tham khảo

- [Spring Kafka — Exactly Once Semantics](https://docs.spring.io/spring-kafka/reference/kafka/exactly-once.html)
- [Spring Kafka — Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html)
- [Spring Kafka — Listener Container Properties](https://docs.spring.io/spring-kafka/reference/kafka/container-props.html)
- [Apache Kafka KIP-447 — Producer scalability for exactly once semantics](https://cwiki.apache.org/confluence/display/KAFKA/KIP-447%3A+Producer+scalability+for+exactly+once+semantics)
