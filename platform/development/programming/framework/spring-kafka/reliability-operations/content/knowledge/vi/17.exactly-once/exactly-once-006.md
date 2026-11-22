# Offset và output cùng transaction

Trong Spring Kafka, một luồng xử lý phổ biến là đọc dữ liệu từ topic đầu vào, chuyển đổi hoặc kiểm tra nghiệp vụ, rồi publish kết quả sang topic đầu ra. Để consumer có thể tiếp tục từ đúng vị trí khi restart, ứng dụng còn phải **commit offset** của record đã xử lý. Nếu output và offset được commit bằng hai thao tác độc lập, một lần process crash ở giữa có thể khiến output bị lặp hoặc record đầu vào bị bỏ qua.

**Kafka transaction** cho phép đưa các output record và offset của consumer group vào **cùng một giao dịch Kafka**. Khi transaction commit, output và tiến độ tiêu thụ được xác nhận cùng nhau; khi abort, offset không được commit và output của transaction aborted sẽ không được trả về cho consumer có `isolation.level=read_committed`. Spring Kafka có thể điều phối điều này bằng `KafkaTransactionManager`, `KafkaTemplate` và transactional listener container.

Đây là cơ sở của **exactly-once semantics (EOS) cho luồng Kafka → xử lý → Kafka**. Nó không có nghĩa phương thức listener chỉ chạy một lần. Sau crash hoặc abort, cùng input có thể được xử lý lại; điều quan trọng là kết quả Kafka của các transaction aborted không được xem là output đã commit. Các side effect bên ngoài Kafka, chẳng hạn database và HTTP, vẫn cần idempotency hoặc kiến trúc riêng.

## 1. Hai kết quả của một record phải cùng được xác nhận

Giả sử consumer group `order-processor` đọc record từ `orders`, partition 0, offset 41. Listener tạo `OrderValidated` và gửi sang `validated-orders`.

Khi record offset 41 đã xử lý, committed offset tiếp theo thường là **42** — vị trí *kế tiếp cần đọc*, không phải vị trí cuối cùng đã xử lý. Có hai việc cần hoàn thành:

1. Publish output `OrderValidated` vào topic `validated-orders`.
2. Commit offset `orders-0 → 42` cho group `order-processor`.

```text
Kafka input: orders-0, offset=41
                |
                v
         Spring @KafkaListener
                |
                v
      Xử lý / tạo output record
                |
        +-------+-------+
        |               |
        v               v
 validated-orders   Offset group: 42
        |               |
        +-------+-------+
                |
                v
         Kafka transaction
        COMMIT hoặc ABORT
```

Mục tiêu là không xuất hiện trạng thái *output đã commit nhưng offset chưa commit*, hoặc *offset đã commit nhưng output tương ứng chưa commit*, do hai hành động được thực hiện như các commit riêng biệt.

## 2. Vấn đề khi gửi output và commit offset độc lập

Không dùng transaction, luồng `send()` trước rồi `commitSync()` có thể gặp:

```text
poll() input offset 41
        |
        v
publish output thành công
        |
        X process crash
        |
chưa kịp commit offset 42
```

Sau restart, consumer group vẫn có thể đọc lại offset 41, listener tạo output lần nữa. **Output bị lặp**. Producer idempotence giúp chống một số kiểu duplicate do producer retry, nhưng không tự ngăn ứng dụng publish cùng nghiệp vụ lần thứ hai sau khi consumer đọc lại input.

Nếu đổi thứ tự thành commit offset trước:

```text
poll() input offset 41
        |
        v
commit offset 42
        |
        X process crash
        |
chưa publish output
```

Group đã tiến qua record đầu vào nhưng output chưa tồn tại: nguy cơ **mất kết quả xử lý**. Vì vậy cách triển khai cần một ranh giới atomicity chung thay vì cố chọn thứ tự commit ít rủi ro hơn.

## 3. sendOffsetsToTransaction hoạt động thế nào?

Kafka producer có API `sendOffsetsToTransaction(...)` để thêm committed offset của một consumer group vào transaction của producer. Ở mức Kafka client, quy trình có thể được mô tả:

```text
producer.initTransactions()  // khởi tạo producer transactional

producer.beginTransaction()

producer.send(outputRecordA)
producer.send(outputRecordB)

producer.sendOffsetsToTransaction(
    offsetsToCommit,
    consumer.groupMetadata()
)

producer.commitTransaction()
```

`offsetsToCommit` là map từ `TopicPartition` đến `OffsetAndMetadata`. Ví dụ `orders-0 → 42` và `orders-1 → 16`. Tham số group metadata giúp Kafka liên hệ yêu cầu commit offset với đúng consumer group membership.

Trong **EOS V2**, Kafka sử dụng group metadata để tăng độ an toàn khi thay đổi thành viên hoặc partition assignment. Spring Kafka hiện đại dùng cơ chế này trong transactional listener container. Với ứng dụng thông thường, **không tự gọi `sendOffsetsToTransaction` bên trong `@KafkaListener`**: container thực hiện việc đưa offset vào transaction khi cấu hình Kafka transaction manager đúng.

Nếu transaction abort, các output record thuộc transaction không hiển thị cho consumer `read_committed` và các offset gửi trong transaction cũng không trở thành committed offset của group.

## 4. Container thực hiện những bước gì?

Với Kafka transaction manager được gắn vào listener container, luồng xử lý logic là:

```text
Consumer poll()
     |
     v
Listener container bắt đầu Kafka transaction
     |
     v
@KafkaListener xử lý input
     |
     v
KafkaTemplate.send(output) tham gia transaction
     |
     v
Listener kết thúc thành công
     |
     v
Container đưa offset đã xử lý vào transaction
     |
     v
Producer commitTransaction()
     |
     v
Output và committed offset cùng có hiệu lực
```

Nếu listener ném exception, transaction phải được abort theo cơ chế xử lý lỗi của container. Nếu commit transaction thất bại, container cũng cần xử lý ngoại lệ tương ứng; không được tự cho rằng offset đã tiến chỉ vì lệnh `send()` đã trả về.

Ranh giới transaction có thể khác giữa record listener và batch listener. **Không mặc định một lần `poll()` luôn bằng đúng một transaction** trong mọi chế độ; cần hiểu listener type, acknowledgment semantics và phiên bản Spring Kafka đang chạy.

## 5. Cấu hình Spring Boot

Ví dụ dùng String key/value, giúp tập trung vào Kafka transaction:

```yaml
spring:
  kafka:
    bootstrap-servers: kafka:9092
    producer:
      transaction-id-prefix: "order-tx-instance-a-"
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
      acks: all
      properties:
        "[enable.idempotence]": true
    consumer:
      group-id: order-processor
      enable-auto-commit: false
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      properties:
        "[isolation.level]": read_committed
```

| Cấu hình | Ý nghĩa |
|---|---|
| `transaction-id-prefix` | Cho producer factory tạo transactional producer có `transactional.id` từ prefix và suffix. |
| `acks=all` | Yêu cầu acknowledgment theo cấu hình replication; không thay thế tính atomic của transaction. |
| `enable.idempotence=true` | Bật idempotent producer, hữu ích cho transactional producer; không tự commit offset cùng output. |
| `enable-auto-commit=false` | Tránh Kafka consumer tự commit offset bên ngoài transaction do Spring container quản lý. |
| `isolation.level=read_committed` | Chỉ trả về các transactional record đã commit cho consumer. |

Trong ví dụ, `order-tx-instance-a-` chỉ đại diện **một instance**. Khi chạy nhiều pod, prefix phải khác nhau giữa các instance đang hoạt động đồng thời. Có thể lấy tên pod qua Kubernetes Downward API và truyền vào biến môi trường cấu hình.

Spring Boot có thể auto-configure `KafkaTransactionManager` khi producer transaction ID prefix được thiết lập. Khi ứng dụng tự tạo `ProducerFactory`, `KafkaTemplate` hoặc listener factory, hãy xác minh chúng tham gia đúng transaction manager; sự tồn tại của một bean transaction manager không tự bảo đảm mọi listener sử dụng nó.

## 6. Gắn KafkaTransactionManager với listener container

Ví dụ Java cấu hình listener container. Phương thức `setKafkaAwareTransactionManager(...)` phù hợp với Spring Kafka 3.2+; ở phiên bản trước, kiểm tra API `setTransactionManager(...)` tương ứng.

```java
@Configuration
public class KafkaOrderConfiguration {

    @Bean
    KafkaTransactionManager<String, String> kafkaTransactionManager(
            ProducerFactory<String, String> producerFactory) {
        return new KafkaTransactionManager<>(producerFactory);
    }

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, String>
            orderListenerFactory(
                    ConsumerFactory<String, String> consumerFactory,
                    KafkaTransactionManager<String, String> kafkaTransactionManager) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, String>();
        factory.setConsumerFactory(consumerFactory);

        factory.getContainerProperties()
                .setKafkaAwareTransactionManager(kafkaTransactionManager);

        return factory;
    }
}
```

Các import chính:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.core.ProducerFactory;
import org.springframework.kafka.transaction.KafkaTransactionManager;
```

Đoạn code giả định `ProducerFactory<String, String>` có cấu hình transaction ID prefix hợp lệ. Nếu Boot đã tạo transaction manager, không cần tạo thêm bean trùng chức năng; có thể inject manager sẵn có. Trong dự án có nhiều `KafkaTransactionManager` hoặc nhiều `ProducerFactory`, chọn rõ ràng bằng tên bean/`@Qualifier`.

**Yêu cầu quan trọng:** `KafkaTemplate` dùng trong listener phải sử dụng đúng transactional producer factory tương thích với transaction manager mà container dùng. Hai factory khác nhau không tự chia sẻ cùng một Kafka transaction.

## 7. Listener chỉ xử lý input và gửi output

Sau khi cấu hình container, listener có thể tập trung vào nghiệp vụ:

```java
@Component
public class OrderProcessor {

    private final KafkaTemplate<String, String> kafkaTemplate;

    public OrderProcessor(KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @KafkaListener(
        topics = "orders",
        groupId = "order-processor",
        containerFactory = "orderListenerFactory"
    )
    public void handle(ConsumerRecord<String, String> record) {
        String normalizedOrder = record.value().trim();

        kafkaTemplate.send(
                "validated-orders",
                record.key(),
                normalizedOrder);
    }
}
```

Các import liên quan:

```java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;
```

Listener **không tự gọi** `consumer.commitSync()`, `Acknowledgment.acknowledge()` hoặc `sendOffsetsToTransaction()` trong ví dụ này. Container gửi offset phù hợp vào Kafka transaction rồi commit sau khi listener xử lý thành công. Nếu xử lý nghiệp vụ thất bại, listener phải ném exception để container chọn rollback/retry.

Không gọi `KafkaTemplate.executeInTransaction(...)` một cách tùy tiện bên trong listener đã có transaction container: API này có thể tạo transaction Kafka mới, độc lập với transaction đang điều phối offset. Với read-process-write EOS, để output tham gia transaction hiện tại là mô hình dễ hiểu nhất.

## 8. Tính offset cần commit cho từng partition

Committed offset không phải cờ “record này đã xong”. Nó biểu thị vị trí kế tiếp consumer group sẽ đọc trên từng topic-partition.

Giả sử listener hoàn tất:

```text
orders-0: offset 40, 41, 42
orders-1: offset 15
```

Nếu tất cả record được bao phủ bởi một transaction và đủ điều kiện commit, map offset có thể có dạng:

```text
TopicPartition("orders", 0) -> OffsetAndMetadata(43)
TopicPartition("orders", 1) -> OffsetAndMetadata(16)
```

Không được commit vượt qua một record chưa hoàn tất chỉ vì một record phía sau đã xử lý xong. Spring Kafka quản lý tiến độ theo listener mode, acknowledgment mode và phạm vi transaction. Với batch listener, một lỗi giữa batch có thể làm phạm vi rollback và replay lớn hơn so với xử lý từng record riêng.

## 9. Các điểm crash và kết quả mong đợi

Xét input `orders-0@41` và output dự kiến vào `validated-orders`:

| Thời điểm sự cố | Output | Offset của group | Khi khởi động lại |
|---|---|---|---|
| Trước khi gửi output | Chưa có output committed. | Chưa commit 42. | Có thể xử lý lại input. |
| Sau `send()` nhưng trước transaction commit | Pending hoặc bị abort; không được xem là committed output. | Chưa commit 42. | Có thể xử lý lại input; `read_committed` bỏ qua aborted output. |
| Trong khi commit, client không nhận được phản hồi rõ ràng | Trạng thái Kafka transaction cần được xác định bởi coordinator; client có thể không biết chắc ngay. | Offset và output không phải hai commit rời. | Consumer khôi phục theo committed offset thực tế. |
| Broker đã commit transaction thành công | Output có hiệu lực cho `read_committed`. | Offset 42 đã commit. | Group thường tiếp tục ở offset 42. |

Một request `commitTransaction()` có thể thất bại hoặc mất kết nối đúng lúc chờ broker trả kết quả; **không được kết luận transaction đã abort chỉ vì client không nhận được acknowledgment**. Điều quan trọng là Kafka quản lý output và offset trong cùng transaction, nên chúng không tạo trạng thái “một bên commit, bên kia chưa commit” theo mô hình giao dịch đúng.

Nếu ứng dụng tự gửi lại output bằng một producer khác ngoài transaction để “chắc chắn” sau timeout, nó có thể tự đưa duplicate vào topic và phá vỡ bảo đảm.

## 10. read_committed là điều kiện nhìn thấy output

Kafka có thể ghi record vào log trước khi transaction được commit/abort. Consumer `read_uncommitted` có thể đọc record thuộc transaction chưa commit và cả transaction sau đó bị abort.

Consumer downstream muốn chỉ thấy output của giao dịch thành công cần:

```yaml
spring:
  kafka:
    consumer:
      properties:
        "[isolation.level]": read_committed
```

Với `read_committed`, Kafka consumer không trả các record của transaction aborted. Consumer cũng có thể tạm dừng tiến độ đọc tại **Last Stable Offset (LSO)** khi còn transaction đang mở; do đó một transaction dài có thể ảnh hưởng độ trễ xuất hiện của output downstream.

Hai trạng thái cần phân biệt:

- Producer future cho biết `send()` đã được broker xử lý theo ngữ cảnh request; **chưa đồng nghĩa cả transaction đã commit**.
- Consumer `read_committed` nhìn thấy output sau khi transaction đã được commit và kết quả đọc thỏa isolation level.

Nếu downstream dùng `read_uncommitted`, một phần bảo đảm EOS dựa trên transactional output không còn được tôn trọng trong cách downstream tiêu thụ.

## 11. EOS V2 và thay đổi consumer group

Spring Kafka hiện đại dùng **EOS V2**: offset được gửi vào transaction kèm consumer group metadata. Khi consumer bị rebalance và mất partition ownership, broker có thể từ chối thao tác transaction/offset không còn phù hợp với group generation hiện tại.

`transactional.id` lại giải quyết bài toán khác: producer epoch dùng để **fence** producer cũ khi có producer mới với cùng ID tiếp quản. Cần hiểu khác biệt:

| Khái niệm | Vai trò |
|---|---|
| Consumer `group.id` | Xác định nhóm chia sẻ partition và committed offset. |
| `Consumer.groupMetadata()` | Gắn offset transaction với trạng thái thành viên của consumer group. |
| Producer `transactional.id` | Định danh chuỗi phiên producer giao dịch; dùng cho fencing. |
| Producer epoch | Giúp broker vô hiệu phiên producer cũ khi một producer mới chiếm cùng ID. |
| Consumer `read_committed` | Lọc output chưa commit/đã abort theo Kafka transaction. |

Không dùng cùng một transactional ID cho tất cả replica trong consumer group. Khi rolling update có pod cũ và mới cùng chạy, prefix trùng nhau có thể gây `ProducerFencedException`. Hãy cấp prefix riêng cho từng instance đang hoạt động, và theo dõi fencing sau deployment.

## 12. Producer transaction cache và concurrency

`DefaultKafkaProducerFactory` tái sử dụng transactional producer sau khi transaction trước kết thúc. Nếu nhiều listener thread xử lý đồng thời, mỗi transaction đang hoạt động cần producer riêng; một producer không chạy hai transaction độc lập cùng lúc.

```text
Pod order-service-1
  listener-0 -> transaction A -> producer P0
  listener-1 -> transaction B -> producer P1
  listener-2 -> transaction C -> producer P2

Ba transaction đồng thời cần ba producer.
```

Với Spring Kafka 3.2+, `DefaultTransactionIdSuffixStrategy(maxCache)` có thể đặt giới hạn số suffix để cấp producer. Khi không còn suffix khả dụng, `NoProducerAvailableException` có thể xảy ra. Chọn kích thước cache theo concurrency và các transaction khác chạy trong **một JVM**, không nhân theo tổng replica toàn cluster cho từng pod.

Nếu producer cached lâu hơn tuổi phù hợp so với `transactional.id.expiration.ms` của broker, có thể gặp lỗi khi tái sử dụng. `DefaultKafkaProducerFactory.setMaxAge(...)` giúp factory thay producer quá tuổi. Cache giúp hiệu suất và vòng đời producer; **nó không tự kích hoạt EOS** nếu listener container không dùng Kafka transaction manager.

## 13. Timeout, poll interval và transaction dài

Transaction phải đủ ngắn để tránh timeout và ảnh hưởng consumer group:

| Thuộc tính | Ý nghĩa |
|---|---|
| Producer `transaction.timeout.ms` | Giới hạn thời gian giao dịch trên broker. |
| Broker `transaction.max.timeout.ms` | Giới hạn tối đa transaction timeout mà broker chấp nhận. |
| Consumer `max.poll.interval.ms` | Khoảng tối đa giữa các lần `poll()` theo chính sách consumer group. |
| Producer `request.timeout.ms` | Timeout của request riêng lẻ, không phải thời gian tối đa cả transaction. |

Nếu listener gọi database hoặc HTTP chậm, chờ retry đồng bộ quá lâu hoặc xử lý batch lớn, transaction có thể timeout và consumer có thể bị rebalance. Khi đó Kafka transaction abort và input được giao lại theo cơ chế recovery.

Đừng chỉ tăng timeout rất lớn. Transaction mở lâu có thể giữ output chưa commit và làm downstream `read_committed` phải chờ. Đo thời gian xử lý từng record/batch, giảm công việc blocking trong transaction và chọn timeout có dự phòng phù hợp.

## 14. Exception, abort và AfterRollbackProcessor

Với transactional listener, exception nên dẫn đến rollback/abort thay vì commit sai:

```text
poll input
    |
    v
Container beginTransaction()
    |
    v
Listener send(output) rồi ném exception
    |
    v
Kafka transaction abort
    |
    +--> output aborted không hiện cho read_committed
    |
    +--> offset của transaction không commit
    |
    v
AfterRollbackProcessor / container xử lý lại record
```

Spring Kafka cung cấp `AfterRollbackProcessor` cho logic xử lý sau rollback. Với listener transactional, cách retry/recover cần phù hợp transaction semantics; không nên chỉ copy một `DefaultErrorHandler` cho non-transactional listener rồi giả định kết quả tương đương.

**Không nuốt exception rồi return bình thường** nếu nghiệp vụ thực tế đã thất bại. Container có thể coi listener thành công và commit output/offset. Nếu đã phục hồi lỗi ở bên trong listener, phải xác định rõ record được coi là hoàn tất theo hợp đồng nào.

### Hết retry và đưa record sang DLT

Một poison record có thể liên tục gây abort. Có thể dùng xử lý sau rollback và recoverer để đưa record lỗi vào DLT; nếu muốn cả DLT publish và offset nguồn được xác nhận giao dịch, cần cấu hình recovery transaction thích hợp.

Các phiên bản Spring Kafka hỗ trợ `DefaultAfterRollbackProcessor` với khả năng thực hiện recovery trong transaction mới và commit recovered offset trong các điều kiện cấu hình cụ thể. Phải kiểm tra đúng API và kiểu listener đang sử dụng.

**Non-blocking retry qua `@RetryableTopic` không hỗ trợ kết hợp trực tiếp với container transactions trong các phiên bản Spring Kafka có giới hạn này.** Nếu EOS Kafka-to-Kafka là yêu cầu, chọn cơ chế retry/recovery tương thích thay vì bật đồng thời mọi annotation retry.

## 15. Exactly-once không tự bao gồm database hoặc HTTP

Kafka transaction chỉ atomic cho các thay đổi được Kafka transaction bao phủ:

```text
orders -> listener
            |
            +--> UPDATE PostgreSQL    (DB transaction riêng)
            |
            +--> KafkaTemplate.send   (Kafka transaction)
            |
            +--> offset commit        (Kafka transaction)
```

Nếu database commit thành công rồi Kafka transaction abort, input có thể được giao lại và DB update bị áp dụng lần nữa. Nếu Kafka transaction commit trước một thao tác database thất bại, offset/output đã được xác nhận trong Kafka nhưng DB chưa thay đổi.

Để bảo vệ side effect ngoài Kafka, cần thêm:

- **Idempotency** theo event ID, unique constraint hoặc upsert có kiểm soát.
- **Transactional outbox** để phối hợp thay đổi database với ý định publish Kafka.
- **Inbox/deduplication** để consumer nhận cùng event nhiều lần không tạo hiệu ứng trùng.
- **Idempotency key** khi gọi API bên ngoài, nếu hệ thống đối tác hỗ trợ.
- Quy trình đối soát khi hai hệ thống không có giao dịch phân tán nguyên tử.

Không diễn giải “exactly once” thành “listener chạy đúng một lần”. Một record có thể được listener chạy lại nhiều lần khi abort; output Kafka chỉ được công nhận từ transaction đã commit.

## 16. Quan sát transaction trong production

Các tín hiệu nên xem cùng nhau:

| Tín hiệu | Cách đọc |
|---|---|
| Transaction commit/abort rate | Abort tăng gợi ý listener failure, timeout hoặc hạ tầng giao dịch bất ổn. |
| Transaction duration | Giao dịch dài tăng độ trễ và rủi ro timeout. |
| `ProducerFencedException` / epoch errors | Kiểm tra prefix trùng, producer lifecycle và rebalance. |
| `NoProducerAvailableException` | Kiểm tra bounded producer cache và số transaction đồng thời. |
| Producer send failures | Phân biệt lỗi broker/network/serialization với lỗi nghiệp vụ. |
| Committed offset của group | Xác nhận tiến độ input thực sự đã commit. |
| Consumer lag và LSO | Đánh giá input backlog và output visibility qua `read_committed`. |
| AfterRollbackProcessor / DLT recovery | Phát hiện record đã chuyển sang nhánh xử lý lỗi thay vì tạo output bình thường. |

Tên metric cụ thể phụ thuộc Kafka client, Micrometer, Spring Kafka và instrumentation của ứng dụng; bảng trên liệt kê tín hiệu, không khẳng định mọi tên metric có sẵn.

Log có cấu trúc nên gồm `inputTopic`, `partition`, `offset`, group ID, instance ID, output topic, transaction result và exception type; không cần ghi toàn bộ payload nhạy cảm.

```text
event=kafka_read_process_write
input_topic=orders
input_partition=0
input_offset=41
output_topic=validated-orders
consumer_group=order-processor
transaction_result=ABORTED
exception_type=ValidationServiceUnavailableException
```

## 17. Kiểm thử crash và transaction abort

Muốn chứng minh EOS, cần integration test với Kafka broker hỗ trợ transactions; mock `KafkaTemplate` không thể chứng minh atomicity broker.

**Kịch bản thành công:** Publish một input, chờ output qua consumer `read_committed`, kiểm tra offset của group tiến qua input. Output và committed offset phải tương ứng với cùng transaction thành công.

**Kịch bản listener lỗi:** Listener gọi `send()` rồi ném exception. Xác nhận transaction abort, output đó không hiện trong consumer `read_committed`, offset chưa tiến vì transaction aborted và input có thể được retry.

**Kịch bản process crash trước commit:** Dừng instance sau khi gửi output nhưng trước `commitTransaction()`. Sau restart, record được xử lý lại; consumer `read_committed` chỉ thấy output của transaction đã commit.

**Kịch bản rebalance/fencing:** Cho chuyển ownership partition hoặc cấu hình trùng transaction ID trong môi trường test; xác nhận lỗi được ghi nhận, không tự commit offset ngoài transaction và record vẫn xử lý lại an toàn.

**Kịch bản database ngoài Kafka:** Cho DB commit rồi cố tình abort Kafka transaction; quan sát DB side effect vẫn tồn tại. Dùng kết quả để thiết kế idempotency/outbox.

Không chạy thử nghiệm phá hủy hoặc tự reset offset trên production; sử dụng topic và consumer group thử nghiệm riêng.

## 18. Runbook: output có log gửi nhưng offset không tiến

Giả sử sau rollout, service ghi “send successful”, nhưng consumer group `order-processor` không tiến offset.

1. **Kiểm tra cấu hình:** Listener có dùng đúng factory gắn `KafkaAwareTransactionManager` không? `KafkaTemplate` có dùng cùng transactional producer factory không?
2. **Kiểm tra kết quả giao dịch:** `send()` có thể thành công trước commit. Tìm lỗi `commitTransaction()`, abort, timeout và coordinator.
3. **Kiểm tra `transactional.id`:** Prefix có trùng giữa các pod đang hoạt động không? Có `ProducerFencedException` hoặc lỗi epoch sau rolling update không?
4. **Kiểm tra producer cache:** Số producer có đủ cho concurrency không? Có `NoProducerAvailableException` không?
5. **Kiểm tra consumer group:** Assignment, rebalance, committed offset, lag và `max.poll.interval.ms` có dấu hiệu bất thường không?
6. **Kiểm tra downstream:** Consumer đọc output có dùng `read_committed` không? Transaction còn mở làm LSO trì hoãn output không?
7. **Kiểm tra rollback/recovery:** Listener có ném exception? Record có bị xử lý lại, đưa sang DLT hoặc phục hồi bằng logic sau rollback không?
8. **Xác nhận sau sửa:** Input được xử lý, output xuất hiện theo transaction commit, offset tiến tương ứng và không tăng duplicate side effect ngoài Kafka.

Không tự reset offset hoặc gọi `seek` chỉ để làm lag giảm trước khi xác định transaction nào đã commit và record nào đã đi qua DLT.

## 19. Nguyên tắc vận hành

- Gộp output Kafka và offset input vào **một Kafka transaction** để đạt atomicity cho luồng Kafka-to-Kafka.
- Dùng `KafkaTransactionManager` trên listener container và `KafkaTemplate` cùng transactional producer factory.
- Đặt `enable.auto.commit=false`; không dùng `commitSync()` riêng cho offset đang được container gửi trong transaction.
- Không tự gọi `sendOffsetsToTransaction` trong transactional listener đã do container điều phối.
- Cấp `transactional.id` không trùng giữa các instance đang chạy đồng thời để tránh fencing.
- Downstream cần đọc output theo `read_committed` nếu muốn bỏ qua aborted messages.
- Không nuốt lỗi nghiệp vụ rồi return thành công khiến transaction có thể commit sai.
- Thiết kế retry/AfterRollbackProcessor/DLT tương thích với transaction, tránh kết hợp cơ chế retry không được hỗ trợ.
- Giới hạn transaction duration; theo dõi timeout, producer cache, group rebalance và offset cùng output.
- Dùng idempotency/outbox/inbox cho side effect database và API bên ngoài Kafka.
- Kiểm thử restart, crash trước commit, abort và rebalance trong môi trường cô lập.

**Offset và output cùng transaction** biến hai thao tác có thể bị tách rời — publish kết quả và lưu tiến độ đọc — thành một thay đổi atomic trong Kafka. Transaction commit cho phép output và offset cùng có hiệu lực; transaction abort khiến input có thể xử lý lại mà output aborted không được consumer `read_committed` xem là kết quả thành công. Độ tin cậy cuối cùng vẫn cần cấu hình transaction manager đúng, xử lý rollback/recovery rõ ràng và thiết kế an toàn cho các side effect ngoài Kafka.
