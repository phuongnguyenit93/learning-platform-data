# Retry với manual acknowledgment

Spring Kafka cho phép listener tự xác nhận một record đã xử lý thành công bằng tham số `Acknowledgment`. Cách này gọi là **manual acknowledgment**. Thay vì để container tự commit offset ngay theo chế độ `RECORD` hoặc `BATCH`, listener chủ động gọi `acknowledge()` sau khi hoàn tất công việc.

Manual acknowledgment hữu ích khi thời điểm xác nhận phụ thuộc vào kết quả xử lý nghiệp vụ, chẳng hạn chỉ commit sau khi lưu dữ liệu thành công hoặc sau khi hoàn tất một bước kiểm tra. Khi listener ném exception trước khi acknowledge, `CommonErrorHandler` có thể retry record theo chính sách đã cấu hình. Tuy nhiên, manual ack không tự tạo exactly-once: nếu nghiệp vụ đã hoàn tất nhưng ứng dụng dừng trước khi offset được commit, record vẫn có thể được giao lại.

## 1. Manual acknowledgment là gì?

Kafka consumer đọc record và duy trì offset theo từng partition. Khi offset được commit, consumer group lưu vị trí tiếp theo cần đọc. Với manual acknowledgment, listener báo cho Spring Kafka biết record hoặc batch đã xử lý xong bằng cách gọi `Acknowledgment.acknowledge()`.

Luồng cơ bản:

```text
Kafka poll
    |
    v
@KafkaListener nhận record
    |
    v
Thực hiện nghiệp vụ
    |
    +---- Thất bại --------------------> Ném exception
    |                                      |
    |                                      v
    |                                CommonErrorHandler
    |                                      |
    |                                Retry / Recovery
    |
    +---- Thành công -----------------> acknowledge()
                                           |
                                           v
                                     Commit offset
```

Điểm quan trọng là listener chỉ acknowledge sau khi các thao tác cần thiết của lần xử lý đã hoàn tất. Nếu xác nhận trước khi lưu dữ liệu hoặc trước khi gọi dịch vụ downstream, ứng dụng có thể bỏ qua record sau khi gặp sự cố.

## 2. Hai chế độ manual: MANUAL và MANUAL_IMMEDIATE

Spring Kafka cung cấp hai `AckMode` dành cho manual acknowledgment:

| AckMode | Hành vi của `acknowledge()` |
| --- | --- |
| `MANUAL` | Ack được đưa vào hàng đợi; offset được commit sau khi tất cả record từ lần poll trước đã được xử lý |
| `MANUAL_IMMEDIATE` | Nếu gọi trên consumer thread, container commit ngay; nếu gọi từ thread khác, ack được đưa vào hàng đợi và xử lý theo chu kỳ container |

`MANUAL` phù hợp khi muốn listener tự quyết định record nào đã xử lý thành công nhưng vẫn để container gom các acknowledgement trong poll. `MANUAL_IMMEDIATE` phù hợp khi cần commit ngay sau lời gọi acknowledge trên consumer thread.

Không nên hiểu `MANUAL_IMMEDIATE` là cam kết commit đồng bộ trong mọi trường hợp. Hành vi phụ thuộc thread gọi, cấu hình commit của container và kết quả broker. Nếu gọi acknowledgement từ thread khác, container không thể thực hiện commit ngay trên consumer thread đang quản lý consumer.

## 3. Bật manual acknowledgment trong Spring Boot

Đặt `enable-auto-commit=false` và chọn `ack-mode`:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: order-service
      enable-auto-commit: false
      auto-offset-reset: earliest
    listener:
      ack-mode: manual
```

Trong Spring Kafka, auto commit thường được đặt thành `false` khi framework tạo consumer nếu ứng dụng không khai báo thuộc tính này. Khai báo rõ giúp thể hiện rằng container và listener quản lý offset. Không bật auto commit đồng thời với thiết kế manual ack vì client có thể commit offset theo chu kỳ độc lập với thời điểm listener xác nhận.

Có thể dùng `manual_immediate` nếu muốn hành vi commit ngay trên consumer thread:

```yaml
spring:
  kafka:
    listener:
      ack-mode: manual_immediate
```

Tên property Boot là `spring.kafka.listener.ack-mode`; giá trị được bind tới `ContainerProperties.AckMode`. Nếu tự tạo listener container factory, cấu hình trực tiếp:

```java
factory.getContainerProperties()
        .setAckMode(ContainerProperties.AckMode.MANUAL);
```

## 4. Gọi Acknowledgment trong @KafkaListener

Spring Kafka có thể truyền một đối tượng `Acknowledgment` vào tham số listener:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.Acknowledgment;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {

    private final OrderService orderService;

    public OrderListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
            topics = "orders.created",
            groupId = "order-service")
    public void onMessage(
            OrderCreatedEvent event,
            Acknowledgment acknowledgment) {

        orderService.process(event);

        // Chỉ xác nhận sau khi nghiệp vụ hoàn tất.
        acknowledgment.acknowledge();
    }
}
```

Với `AckMode.MANUAL`, listener gọi `acknowledge()` sau khi `orderService.process` hoàn tất. Nếu service ném exception, dòng acknowledge không chạy và exception được truyền tới container để error handler xử lý.

Nếu listener bắt exception rồi chỉ ghi log và kết thúc bình thường, container không biết thao tác nghiệp vụ đã thất bại. Listener cần ném lại exception hoặc gọi một quy trình recovery có chủ đích; không nên nuốt lỗi rồi acknowledge.

## 5. Thời điểm acknowledge quyết định rủi ro mất hoặc trùng record

Hãy xem xét các điểm dừng có thể xảy ra:

| Thời điểm ứng dụng dừng | Kết quả với manual ack |
| --- | --- |
| Trước khi xử lý nghiệp vụ | Chưa ack; record có thể được giao lại |
| Trong khi xử lý và nghiệp vụ chưa hoàn tất | Chưa ack; record có thể được giao lại |
| Nghiệp vụ đã hoàn tất, nhưng trước `acknowledge()` | Record có thể được giao lại; nghiệp vụ có thể chạy lần nữa |
| Sau khi gọi ack nhưng commit chưa thành công | Record có thể được giao lại |
| Sau khi offset commit thành công | Group tiếp tục từ offset kế tiếp |

Vì vậy, manual ack thường tạo semantics at-least-once khi chỉ acknowledge sau khi xử lý thành công. Điều này giảm nguy cơ bỏ sót record nhưng vẫn có thể tạo duplicate nếu sự cố xảy ra giữa business completion và offset commit.

Nếu acknowledge trước khi xử lý, ứng dụng chuyển sang rủi ro at-most-once: sau khi offset commit, lỗi nghiệp vụ có thể làm record không được đọc lại. Chỉ làm vậy khi chấp nhận mất tác vụ.

## 6. Retry khi listener chưa acknowledge

Manual acknowledgment kết hợp với `DefaultErrorHandler` để retry record khi listener ném exception. Ví dụ cấu hình hai lần retry, mỗi lần cách nhau một giây:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

@Bean
public DefaultErrorHandler orderErrorHandler() {
    return new DefaultErrorHandler(
            new FixedBackOff(1_000L, 2L));
}
```

Gắn handler vào listener container factory:

```java
factory.setCommonErrorHandler(orderErrorHandler);
factory.getContainerProperties()
        .setAckMode(ContainerProperties.AckMode.MANUAL);
```

Khi listener thất bại trước acknowledge, error handler thực hiện retry theo backoff. Nếu lần retry thành công và listener acknowledge, container tiếp tục tiến offset. Nếu hết retry, handler có thể gọi recoverer để chuyển record sang DLT.

Với `DefaultErrorHandler`, sau khi recover thành công, mặc định `ackAfterHandle` cho phép container commit offset sau khi handler trả về bình thường. Cần hiểu rõ điều này khi dùng manual ack: recovery thành công cũng là một kết quả được chấp nhận để group tiến lên. Nếu muốn kiểm soát việc commit record đã recover, hãy xem xét `ackAfterHandle`, `commitRecovered` và AckMode tương ứng theo tài liệu phiên bản Spring Kafka đang dùng.

## 7. Chuyển record lỗi sang Dead Letter Topic

Khi record không thể xử lý sau số lần retry đã định, có thể dùng `DeadLetterPublishingRecoverer` để chuyển record sang DLT:

```java
import org.apache.kafka.common.TopicPartition;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

@Bean
public DefaultErrorHandler orderErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    var recoverer = new DeadLetterPublishingRecoverer(
            kafkaTemplate,
            (record, exception) -> new TopicPartition(
                    record.topic() + ".DLT",
                    record.partition()));

    return new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(1_000L, 2L));
}
```

Ví dụ chuyển `orders.created` sang `orders.created.DLT`, giữ partition index. Topic DLT phải tồn tại hoặc được quản trị để tạo phù hợp. Nếu giữ partition gốc, DLT phải có đủ partition tương ứng.

Nếu DLT publish thất bại, recoverer có thể ném exception để record gốc không bị xem là đã phục hồi thành công. Cần giám sát cả lỗi publish DLT và bảo đảm producer DLT có serializer tương thích với payload bình thường cũng như raw bytes từ lỗi deserialize.

DLT là nơi lưu record cần điều tra hoặc phát lại; việc chuyển record vào DLT không có nghĩa lỗi nghiệp vụ đã được sửa. Cần có quy trình xem xét, sửa dữ liệu và replay rõ ràng.

## 8. MANUAL và MANUAL_IMMEDIATE trong record listener

Ví dụ dùng `MANUAL`:

```java
@KafkaListener(topics = "payments.authorized", groupId = "payment-ledger")
public void onPayment(
        PaymentAuthorized event,
        Acknowledgment acknowledgment) {

    ledgerService.record(event);
    acknowledgment.acknowledge();
}
```

Ack được ghi nhận và container commit theo chu kỳ của manual mode sau khi các record thuộc poll đã được xử lý. Nếu poll trả nhiều record, không nên giả định mỗi lần gọi `acknowledge()` lập tức ghi offset riêng ngay lập tức.

Ví dụ dùng `MANUAL_IMMEDIATE`:

```java
@KafkaListener(topics = "payments.authorized", groupId = "payment-ledger")
public void onPayment(
        PaymentAuthorized event,
        Acknowledgment acknowledgment) {

    ledgerService.record(event);
    acknowledgment.acknowledge(); // Gọi trên consumer thread.
}
```

Với `MANUAL_IMMEDIATE`, lời gọi trên consumer thread yêu cầu container commit ngay. Vì vậy, chỉ gọi sau khi tất cả bước cần thiết đã hoàn tất. Không gọi acknowledge ở đầu listener rồi mới thực hiện database update hoặc gọi API.

Không nên trộn lẫn các lời gọi ack từ consumer thread và thread khác trong cùng một listener theo cách khiến thứ tự commit khó dự đoán. Chọn một mô hình xử lý và xác nhận nhất quán.

## 9. Manual acknowledgment với xử lý bất đồng bộ

Một số ứng dụng muốn listener giao công việc cho executor rồi acknowledge khi tác vụ nền hoàn tất. Nếu làm vậy, listener có thể trả về trước khi nghiệp vụ thực sự xong; container phải được cấu hình để quản lý các acknowledgement đến không theo thứ tự.

Spring Kafka hỗ trợ `asyncAcks` từ phiên bản 2.8. Khi bật, container cho phép acknowledge các record của một poll theo thứ tự bất kỳ. Container theo dõi những offset còn thiếu và tạm dừng consumer cho đến khi tất cả acknowledgement của poll được nhận. Sau đó việc commit mới có thể tiến qua khoảng trống.

Ví dụ cấu hình:

```java
factory.getContainerProperties()
        .setAckMode(ContainerProperties.AckMode.MANUAL);
factory.getContainerProperties()
        .setAsyncAcks(true);
```

Mô hình này cần được dùng cẩn thận:

- Consumer có thể bị pause trong lúc chờ acknowledgement còn thiếu.
- Một tác vụ nền thất bại hoặc không bao giờ hoàn tất có thể chặn tiến độ commit của poll đó.
- Khi ứng dụng dừng trước khi đủ ack, các record chưa commit có thể được giao lại, kể cả công việc nền trước đó đã tạo side effect.
- Không giữ `Acknowledgment` vô thời hạn hoặc sử dụng sau khi container đã dừng/rebalance.
- Phải xử lý exception trong executor và có cơ chế báo lỗi/retry rõ ràng; không để future thất bại mà offset bị treo không giám sát.

`asyncAcks` không biến Kafka consumer thành một consumer thread-safe và cũng không tự bảo đảm thứ tự hoàn tất nghiệp vụ. Nó chỉ giúp container quản lý acknowledgement đến không theo thứ tự của các record thuộc poll.

## 10. Manual acknowledgment với batch listener

Với batch listener, một lần gọi nhận nhiều record. Listener thường acknowledge sau khi toàn bộ batch đã xử lý thành công:

```java
import java.util.List;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.Acknowledgment;

@KafkaListener(
        topics = "orders.created",
        groupId = "order-batch-service",
        containerFactory = "batchKafkaListenerContainerFactory")
public void onMessages(
        List<ConsumerRecord<String, OrderCreatedEvent>> records,
        Acknowledgment acknowledgment) {

    for (ConsumerRecord<String, OrderCreatedEvent> record : records) {
        orderService.process(record.value());
    }

    acknowledgment.acknowledge();
}
```

Factory cần được cấu hình batch mode bằng `setBatchListener(true)` và `AckMode.MANUAL`. Nếu bất kỳ record nào ném exception trước khi acknowledge, batch chưa được xác nhận thành công và error handler sẽ xử lý lỗi theo chính sách.

Với batch listener, cần cân nhắc tác động khi một phần batch đã cập nhật database nhưng record sau đó thất bại. Khi batch được retry, phần đã hoàn tất có thể chạy lại. Hãy dùng idempotency hoặc transaction database cho thao tác batch.

## 11. Manual acknowledgment không thay thế idempotency

Giả sử listener cập nhật database thành công rồi ứng dụng dừng trước khi gọi `acknowledge()`. Kafka sẽ giao lại record. Nếu listener cập nhật database lần nữa mà không có kiểm soát, số liệu hoặc trạng thái nghiệp vụ có thể bị nhân đôi.

Một cách phổ biến là lưu `eventId` vào bảng inbox cùng transaction với cập nhật nghiệp vụ:

```sql
CREATE TABLE processed_event (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
```

```java
@Transactional
public void processOnce(OrderCreatedEvent event) {
    if (!processedEventRepository.insertIfAbsent(event.eventId())) {
        return; // Event đã được xử lý trước đó.
    }

    orderRepository.createProjection(event);
}
```

`insertIfAbsent` cần dựa trên unique constraint hoặc thao tác insert nguyên tử. Ghi dấu event và cập nhật nghiệp vụ phải nằm trong cùng database transaction. Sau khi service commit thành công, listener mới acknowledge Kafka offset.

Nếu ứng dụng dừng giữa database commit và Kafka offset commit, lần giao lại tiếp theo sẽ gặp `eventId` đã tồn tại và không tạo thêm tác động nghiệp vụ.

## 12. Quan hệ với transaction và exactly-once

Manual ack chỉ kiểm soát thời điểm xác nhận offset. Nó không tự đưa database transaction và Kafka offset vào cùng một transaction phân tán.

Nếu listener chỉ cập nhật database rồi acknowledge, vẫn có cửa sổ lỗi giữa hai hệ thống. Kafka transaction có thể kết hợp output Kafka và input offset trong cùng transaction, nhưng không tự bao trùm database hoặc HTTP side effect.

Vì vậy:

- Dùng manual ack để điều khiển thời điểm commit offset theo kết quả xử lý.
- Dùng idempotency/inbox để chống lặp khi record được giao lại.
- Dùng outbox/inbox hoặc cơ chế phối hợp phù hợp khi cần nhất quán giữa database và Kafka.
- Dùng container transaction/EOS V2 khi cần atomic read-process-write giữa các topic Kafka.

Không gọi manual ack là exactly-once. Listener vẫn có thể được gọi lại sau crash, rollback hoặc commit thất bại.

## 13. Các lưu ý về commit và error handler

Manual acknowledgment tương tác với các thiết lập khác của listener container:

| Thiết lập | Điều cần kiểm tra |
| --- | --- |
| `enable.auto.commit` | Để `false` để container quản lý offset |
| `AckMode.MANUAL` | Ack được xếp hàng và commit sau khi các record của poll được xử lý |
| `AckMode.MANUAL_IMMEDIATE` | Commit ngay khi ack trên consumer thread |
| `DefaultErrorHandler` | Xử lý retry khi listener ném exception trước ack |
| `ackAfterHandle` | Mặc định cho phép commit sau khi error handler phục hồi thành công |
| `commitRecovered` | Tùy chọn commit offset record được recover; cần tuân thủ yêu cầu AckMode của phiên bản |
| `asyncAcks` | Cho phép ack không theo thứ tự nhưng có thể pause consumer chờ gap |
| Kafka transaction | Exception thoát listener làm transaction rollback; cần thiết kế recovery theo transaction |

Với `DefaultErrorHandler`, `setCommitRecovered(true)` là tùy chọn nâng cao để commit offset của record đã recover và yêu cầu `MANUAL_IMMEDIATE` theo hợp đồng API. Không bật tùy chọn này theo thói quen; trước tiên xác định `ackAfterHandle` và AckMode hiện tại đã đáp ứng yêu cầu chưa.

Nếu listener chạy trong container transaction, exception cần được truyền ra để transaction rollback. Cơ chế retry sau rollback thường do `DefaultAfterRollbackProcessor` quản lý; không áp dụng máy móc cấu hình `DefaultErrorHandler` của listener non-transactional vào transactional listener.

## 14. Kiểm thử manual acknowledgment và retry

Kiểm thử nên chứng minh offset chỉ tiến sau khi acknowledge và record có thể được giao lại khi listener thất bại.

Một integration test có thể thực hiện:

1. Tạo topic input và cấu hình listener `AckMode.MANUAL`.
2. Gửi một event có `eventId` cố định.
3. Cho service thất bại ở lần đầu; listener không gọi acknowledge.
4. Xác nhận error handler retry và listener được gọi lại.
5. Cho service thành công ở lần sau rồi gọi acknowledge.
6. Xác nhận group commit offset và không tiếp tục nhận lại record.
7. Tạo tình huống service đã commit database nhưng ứng dụng dừng trước ack; xác nhận record được giao lại nhưng idempotency ngăn tác động lặp.

Các trường hợp nên kiểm thử thêm:

- So sánh `MANUAL` và `MANUAL_IMMEDIATE`.
- Listener ném exception trước ack.
- Listener vô tình ack trước business completion.
- Hết retry và record được recover sang DLT.
- `asyncAcks` nhận acknowledgement theo thứ tự khác với poll.
- Batch listener xử lý một phần batch rồi thất bại.
- Rebalance hoặc shutdown khi tác vụ async chưa acknowledge.

Dùng Embedded Kafka hoặc broker kiểm thử, `CountDownLatch`, `BlockingQueue` hay Awaitility để chờ listener và offset với timeout. Không dựa vào một `Thread.sleep` ngắn để kết luận commit đã hoàn tất.

## 15. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Record được đọc lại dù listener đã chạy | Listener chưa ack hoặc commit chưa thành công | Kiểm tra vị trí gọi ack và commit log |
| Record bị mất sau khi listener lỗi | Ack được gọi trước khi nghiệp vụ hoàn tất | Chỉ ack sau khi business operation thành công |
| Listener không retry | Exception bị bắt và không truyền ra ngoài | Ném lại exception hoặc cấu hình recovery rõ ràng |
| Commit không xảy ra ngay | Dùng `MANUAL` và chờ container xử lý hết poll | Hiểu khác biệt với `MANUAL_IMMEDIATE` |
| Ack từ thread nền không có hiệu lực như mong đợi | Chưa bật `asyncAcks` hoặc ack đến sau khi container đã đổi trạng thái | Cấu hình async ack có chủ đích và quản lý vòng đời task |
| Offset bị kẹt | Có record trong poll chưa được acknowledge | Theo dõi ack gap, timeout và lỗi tác vụ nền |
| Duplicate database update | DB commit thành công nhưng Kafka offset chưa commit | Dùng event ID, unique constraint và inbox pattern |
| Record vào DLT nhưng offset vẫn lặp | Recovery/commit policy không phù hợp | Kiểm tra `ackAfterHandle`, `commitRecovered` và AckMode |
| Auto commit làm offset tiến ngoài dự kiến | `enable.auto.commit=true` | Tắt auto commit và để container quản lý |

## 16. Kết luận

Manual acknowledgment cho phép listener chủ động xác nhận record sau khi nghiệp vụ hoàn tất. `AckMode.MANUAL` xếp acknowledgement vào hàng đợi và commit sau khi các record của poll được xử lý; `MANUAL_IMMEDIATE` commit ngay khi ack được gọi trên consumer thread. Khi listener ném exception trước ack, `CommonErrorHandler` có thể retry hoặc recover record.

Hãy acknowledge ở cuối luồng xử lý thành công, cấu hình `enable.auto.commit=false`, hiểu tương tác giữa AckMode và error handler, đồng thời làm cho nghiệp vụ idempotent để chịu được redelivery. Với xử lý bất đồng bộ, chỉ bật `asyncAcks` khi đã quản lý được ack gap, pause và vòng đời tác vụ. Manual ack giúp kiểm soát offset; độ tin cậy cuối cùng vẫn phụ thuộc retry, recovery, idempotency và ranh giới transaction của hệ thống.

## Tài liệu tham khảo

- [Spring for Apache Kafka — Message Listener Containers: Committing Offsets](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html)
- [Spring for Apache Kafka — Acknowledgment API](https://docs.spring.io/spring-kafka/api/org/springframework/kafka/support/Acknowledgment.html)
- [Spring for Apache Kafka — Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html)
- [Spring for Apache Kafka — Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html)
