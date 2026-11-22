# executeInTransaction

Khi một nghiệp vụ cần gửi nhiều Kafka record như một đơn vị nguyên tử, ứng dụng không nên để record thứ nhất được ghi thành công trong khi record thứ hai thất bại và chỉ một phần dữ liệu xuất hiện trên topic. Kafka transaction cho phép producer ghi nhiều record vào một hoặc nhiều topic/partition rồi commit tất cả cùng nhau, hoặc abort để các record của transaction không được consumer đọc ở chế độ `read_committed`.

Spring Kafka cung cấp `KafkaTemplate.executeInTransaction()` để chạy một đoạn callback trong transaction do template quản lý. Cách này phù hợp khi một phương thức nghiệp vụ cần gửi một nhóm record Kafka trong cùng một ranh giới commit/rollback mà không muốn tự gọi `beginTransaction()`, `commitTransaction()` và `abortTransaction()` trên Kafka producer.

## 1. executeInTransaction làm gì?

`executeInTransaction()` nhận một `OperationsCallback` và thực thi callback trong một Kafka transaction. Callback nhận một `KafkaOperations` để gửi record. Nếu callback hoàn tất bình thường, template commit transaction; nếu callback ném exception, transaction được abort và exception được truyền ra caller.

```text
Gọi KafkaTemplate.executeInTransaction(callback)
                    |
                    v
             Bắt đầu transaction
                    |
                    v
        Chạy OperationsCallback
                    |
          +---------+---------+
          |                   |
      Thành công            Exception
          |                   |
          v                   v
    commitTransaction()  abortTransaction()
          |                   |
          v                   v
    Record được commit   Record bị abort
```

Điểm quan trọng là ranh giới transaction bao quanh callback. Các lệnh gửi cần thuộc cùng transaction phải được thực hiện qua `KafkaOperations` nhận từ callback hoặc qua `KafkaTemplate` tham gia đúng transaction hiện hành. Không tự tạo một producer Kafka khác rồi gửi ngoài transaction nếu muốn các record đó có tính nguyên tử cùng nhau.

## 2. Điều kiện để dùng executeInTransaction

`KafkaTemplate` phải dùng một `ProducerFactory` hỗ trợ transaction. Trong Spring Boot, cách phổ biến là cấu hình `spring.kafka.producer.transaction-id-prefix`. Spring Boot dùng prefix này để cấu hình producer factory có tính transaction và tự động cấu hình các thành phần Kafka transaction liên quan theo phiên bản Boot.

`KafkaTemplate.executeInTransaction()` có từ Spring Kafka 2.3. Nếu dự án dùng phiên bản cũ hơn, cần nâng cấp hoặc dùng transaction API tương ứng của phiên bản đó.

Ví dụ `application.yml`:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      transaction-id-prefix: ${HOSTNAME:orders-local}-orders-tx-
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
```

`transaction-id-prefix` được dùng để tạo `transactional.id` cho producer. Producer factory có thể thêm hậu tố để tạo ID riêng cho từng producer được quản lý. Prefix phải duy nhất giữa các instance ứng dụng đang hoạt động trong cùng cluster. Nếu hai instance dùng cùng transactional ID, broker có thể fence producer cũ khi instance còn lại khởi tạo producer với cùng ID.

Trong môi trường nhiều pod, nên lấy prefix từ định danh instance ổn định và duy nhất, ví dụ tên pod được inject vào biến `HOSTNAME` hoặc `POD_NAME`. Không dùng một prefix cố định giống nhau cho tất cả replica.

Nếu tự cấu hình producer factory, phải thiết lập transaction ID prefix trên `DefaultKafkaProducerFactory`:

```java
import java.util.HashMap;
import java.util.Map;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.common.serialization.StringSerializer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.DefaultKafkaProducerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.core.ProducerFactory;

@Configuration
class KafkaProducerConfiguration {

    @Bean
    ProducerFactory<String, String> producerFactory() {
        Map<String, Object> properties = new HashMap<>();
        properties.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
        properties.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG, StringSerializer.class);
        properties.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG, StringSerializer.class);

        var factory = new DefaultKafkaProducerFactory<String, String>(properties);
        factory.setTransactionIdPrefix("orders-local-tx-");
        return factory;
    }

    @Bean
    KafkaTemplate<String, String> kafkaTemplate(
            ProducerFactory<String, String> producerFactory) {
        return new KafkaTemplate<>(producerFactory);
    }
}
```

Ví dụ Java trên dành cho môi trường local. Production phải cấp prefix riêng cho từng instance. Nếu `ProducerFactory` không được cấu hình transaction, gọi `executeInTransaction()` sẽ thất bại vì template không có transactional producer để mở transaction.

## 3. Gửi nhiều record trong một transaction

Ví dụ một nghiệp vụ thanh toán cần phát ra sự kiện thanh toán thành công và sự kiện audit. Hai record phải cùng commit hoặc cùng abort:

```java
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

@Service
class PaymentEventPublisher {

    private final KafkaTemplate<String, String> kafkaTemplate;

    PaymentEventPublisher(KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public String publishPayment(String paymentId, String paymentJson, String auditJson) {
        return kafkaTemplate.executeInTransaction(operations -> {
            operations.send("payments.events", paymentId, paymentJson);
            operations.send("payments.audit", paymentId, auditJson);
            return "published:" + paymentId;
        });
    }
}
```

Trong callback:

- `operations.send()` gửi record bằng transactional producer gắn với transaction hiện tại.
- Có thể gửi tới nhiều topic và partition trong cùng Kafka cluster.
- Giá trị trả về của callback được trả lại cho caller sau khi transaction hoàn tất.
- Khi callback trả về bình thường, template commit transaction trước khi trả kết quả.

Nếu một trong các thao tác nghiệp vụ phát hiện dữ liệu không hợp lệ, hãy ném exception để transaction rollback:

```java
public String publishPayment(String paymentId, String paymentJson, String auditJson) {
    return kafkaTemplate.executeInTransaction(operations -> {
        operations.send("payments.events", paymentId, paymentJson);

        if (auditJson == null || auditJson.isBlank()) {
            throw new IllegalArgumentException("auditJson is required");
        }

        operations.send("payments.audit", paymentId, auditJson);
        return paymentId;
    });
}
```

Khi exception thoát khỏi callback, transaction bị abort. Record `payments.events` đã được gửi trước đó cũng thuộc transaction này nên không được hiển thị cho consumer `read_committed` như một record đã commit.

## 4. Dùng KafkaOperations được truyền vào callback

Tham số `operations` trong callback có kiểu `KafkaOperations<K, V>`. Nên sử dụng đối tượng này cho mọi lệnh gửi thuộc transaction:

```java
kafkaTemplate.executeInTransaction(operations -> {
    operations.send("orders.events", orderId, orderJson);
    operations.send("orders.audit", orderId, auditJson);
    return null;
});
```

Cách viết này thể hiện rõ những lệnh gửi nào thuộc ranh giới callback. Không gọi trực tiếp một `Producer` được tạo thủ công bên ngoài producer factory đang quản lý transaction; producer đó không tự động tham gia transaction của template.

Trong trường hợp cần tái sử dụng service gửi message, hãy thiết kế service nhận `KafkaOperations` hoặc bảo đảm `KafkaTemplate` được dùng tham gia đúng transaction context. Tránh âm thầm gửi một số record bằng một template/producer factory khác không có cùng transaction.

## 5. Điều gì xảy ra khi callback ném exception?

Nếu callback ném exception và exception thoát ra ngoài, `executeInTransaction()` abort transaction rồi truyền exception cho caller. Caller có thể bắt exception ở bên ngoài để trả lỗi nghiệp vụ hoặc thực hiện xử lý khác.

```java
try {
    kafkaTemplate.executeInTransaction(operations -> {
        operations.send("orders.events", orderId, orderJson);
        validateAudit(auditJson); // Có thể ném exception.
        operations.send("orders.audit", orderId, auditJson);
        return null;
    });
} catch (RuntimeException ex) {
    log.error("Không thể publish transaction cho orderId={}", orderId, ex);
    throw ex;
}
```

Không nên bắt exception bên trong callback rồi bỏ qua nếu muốn rollback:

```java
// Không phù hợp nếu lỗi phải làm transaction rollback.
kafkaTemplate.executeInTransaction(operations -> {
    operations.send("orders.events", orderId, orderJson);
    try {
        validateAudit(auditJson);
    } catch (IllegalArgumentException ex) {
        log.warn("Audit không hợp lệ", ex);
        // Callback vẫn trả về bình thường: transaction có thể được commit.
    }
    return null;
});
```

Nếu ứng dụng đã xử lý exception và callback vẫn trả về bình thường, template không biết nghiệp vụ đã thất bại; transaction có thể commit các record đã gửi. Hãy ném lại exception hoặc chủ động quyết định rằng phần dữ liệu đã gửi vẫn được phép commit.

## 6. Send future và thời điểm transaction commit

`KafkaTemplate.send()` trả về future vì gửi record là bất đồng bộ. Trong callback transaction, có thể gửi nhiều record mà không chờ từng future. Khi commit transaction, Kafka producer phải hoàn tất các request gửi đang chờ trước khi commit thành công; lỗi gửi có thể làm commit thất bại và khiến transaction bị abort.

Nếu cần kiểm tra kết quả gửi ngay tại vị trí gọi, có thể chờ future, nhưng việc chờ tuần tự từng record sẽ làm tăng latency và giảm khả năng gửi song song:

```java
import java.util.concurrent.CompletableFuture;
import org.springframework.kafka.support.SendResult;

String result = kafkaTemplate.executeInTransaction(operations -> {
    CompletableFuture<SendResult<String, String>> first =
            operations.send("orders.events", orderId, orderJson);
    CompletableFuture<SendResult<String, String>> second =
            operations.send("orders.audit", orderId, auditJson);

    // Chờ cả hai send acknowledgement; transaction vẫn commit sau khi callback trả về.
    CompletableFuture.allOf(first, second).join();
    return "sent";
});
```

Trong callback, hãy để lỗi gửi được truyền tới ranh giới transaction. Không nuốt lỗi trong callback hoặc callback của future rồi vẫn trả về bình thường nếu nghiệp vụ yêu cầu mọi record phải được ghi thành công. `CompletableFuture.allOf(...).join()` chờ các send acknowledgement và làm callback chậm hơn; đổi lại, lỗi của một future được ném ra trước khi callback trả về. Commit transaction vẫn là bước xác nhận cuối cùng cho toàn bộ nhóm record.

Với Spring Kafka 3.x, send API trả về `CompletableFuture`; các phiên bản cũ có thể trả về `ListenableFuture`. Cách quan sát kết quả bất đồng bộ cần phù hợp với phiên bản thư viện của ứng dụng.

## 7. Transaction và consumer read_committed

Kafka transaction bảo đảm tính nguyên tử đối với các record được gửi trong transaction, nhưng consumer cần chọn isolation level phù hợp để chỉ đọc dữ liệu đã commit.

```yaml
spring:
  kafka:
    consumer:
      properties:
        "[isolation.level]": read_committed
```

Với `read_committed`, consumer chỉ đọc record thuộc transaction đã commit và không trả về record từ transaction bị abort. Consumer dùng `read_uncommitted` có thể nhìn thấy record transactional trước khi transaction được quyết định, kể cả record sau đó bị abort.

`read_committed` có thể làm consumer chờ khi có transaction chưa hoàn tất ở đầu log của partition. Điều này liên quan tới Last Stable Offset (LSO), vì vậy transaction kéo dài bất thường có thể ảnh hưởng khả năng đọc và latency của consumer.

Nếu ứng dụng phát dữ liệu cho nhiều consumer downstream, hãy thống nhất isolation level theo yêu cầu nhất quán. Một consumer dùng `read_uncommitted` có thể quan sát dữ liệu mà consumer `read_committed` không bao giờ nhận được.

## 8. executeInTransaction khác gì @Transactional và KafkaTransactionManager?

Spring Kafka có nhiều cách quản lý transaction. Chọn cách phù hợp với ranh giới nghiệp vụ:

| Cách dùng | Ranh giới transaction | Trường hợp phù hợp |
|---|---|---|
| `KafkaTemplate.executeInTransaction()` | Callback được truyền vào template | Một phương thức cần gom một nhóm lệnh gửi Kafka trong transaction cục bộ |
| `KafkaTransactionManager` + `@Transactional` | Phương thức/service hoặc listener container theo Spring transaction | Muốn transaction được điều phối qua Spring transaction infrastructure |
| Transactional listener container | Quá trình xử lý record và gửi output Kafka, có thể phối hợp offset | Consume-transform-produce với Kafka transaction |

`executeInTransaction()` là API tiện lợi cho transaction gắn với callback. `KafkaTransactionManager` phù hợp khi muốn Spring quản lý transaction theo thread và annotation. Không nên lồng nhiều cơ chế transaction mà chưa hiểu rõ transaction nào sở hữu producer và transaction nào quyết định commit.

Khi một phương thức đã được quản lý bởi `KafkaTransactionManager`, thông thường chỉ cần gọi `KafkaTemplate.send()` bên trong phương thức để template tham gia transaction đang gắn với thread. Dùng `executeInTransaction()` cho một ranh giới callback riêng là một lựa chọn khác; không trộn hai cách trong cùng luồng nếu chưa xác định rõ semantics của phiên bản Spring Kafka và ranh giới commit mong muốn.

Ví dụ sử dụng `@Transactional` với Kafka transaction manager:

```java
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.stereotype.Service;

@Service
class TransactionalOrderPublisher {

    private final KafkaTemplate<String, String> kafkaTemplate;

    TransactionalOrderPublisher(KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @Transactional("kafkaTransactionManager")
    public void publish(String orderId, String payload) {
        kafkaTemplate.send("orders.events", orderId, payload);
        kafkaTemplate.send("orders.audit", orderId, "published:" + orderId);
    }
}
```

Ví dụ giả định ứng dụng đã khai báo bean `KafkaTransactionManager` có tên `kafkaTransactionManager`. Khi dùng Spring Boot, transaction manager có thể được auto-configure khi producer transaction prefix được thiết lập; hãy kiểm tra bean thực tế nếu ứng dụng có nhiều transaction manager.

## 9. executeInTransaction có tự commit consumer offset không?

Không nên đồng nhất transaction gửi record với transaction xử lý offset của consumer. `executeInTransaction()` gom các lệnh gửi Kafka trong callback. Nếu callback không có consumer offset được gửi vào transaction, transaction đó không tự động xác nhận offset mà một listener đã đọc.

Trong mô hình consume-transform-produce cần bảo đảm output record và offset input cùng commit trong Kafka, thường dùng transactional listener container với `KafkaTransactionManager`. Container điều phối offset của record đã xử lý để gửi vào cùng transaction với output.

```text
Input topic
    |
    v
Transactional listener container
    |
    +---- xử lý record
    |
    +---- gửi output record
    |
    +---- gửi consumer offset vào transaction
    |
    v
Commit Kafka transaction
    |
    +---- output record visible với read_committed
    +---- input offset được commit
```

Nếu chỉ gọi `executeInTransaction()` để gửi output rồi commit offset input bằng cơ chế độc lập, có thể xuất hiện khoảng trống giữa hai thao tác. Hãy chọn transactional listener container hoặc API gửi offset vào transaction theo đúng mô hình Kafka consume-process-produce.

## 10. Transaction không bao phủ database hoặc HTTP service

Kafka transaction chỉ điều phối các thao tác Kafka nằm trong transaction đó. Nó không tự động rollback database, REST API, email hoặc filesystem.

Ví dụ:

```text
Kafka transaction
    |
    +---- send orders.events
    +---- send orders.audit
    |
    +---- commit / abort

Database update và HTTP call không tự động thuộc transaction này.
```

Nếu callback cập nhật database rồi sau đó Kafka transaction abort, database không tự rollback trừ khi database transaction được phối hợp bằng một cơ chế riêng. Ngược lại, nếu Kafka commit thành công nhưng database update thất bại, hai hệ thống có thể lệch trạng thái.

Với nghiệp vụ cần phối hợp database và Kafka, cân nhắc transactional outbox, inbox/idempotency hoặc distributed transaction nếu toàn bộ hệ thống hỗ trợ và chấp nhận chi phí vận hành. Không dùng `executeInTransaction()` như một distributed transaction manager.

## 11. Timeout, fencing và các lỗi transaction

Kafka transaction có thêm các ràng buộc vận hành:

- `transaction.timeout.ms` giới hạn thời gian broker cho phép transaction mở. Giá trị này phải không vượt giới hạn `transaction.max.timeout.ms` trên broker.
- `transactional.id` giúp broker nhận diện producer qua lần khởi động và fencing producer cũ khi có producer mới dùng cùng ID.
- `transactionIdPrefix` phải duy nhất giữa các instance ứng dụng đồng thời.
- Transaction quá dài có thể giữ LSO, làm consumer `read_committed` chờ và tăng latency.
- Lỗi mạng hoặc timeout khi commit có thể khiến kết quả commit không rõ ràng với caller; cần thiết kế retry nghiệp vụ và idempotency phù hợp.

Không giữ transaction mở trong lúc thực hiện HTTP call lâu, chờ người dùng hoặc chạy công việc không liên quan. Hãy chuẩn bị dữ liệu trước khi mở transaction, sau đó thực hiện các thao tác Kafka cần tính nguyên tử trong callback ngắn.

## 12. Kiểm thử executeInTransaction

Kiểm thử transaction cần xác minh cả trường hợp commit và rollback, không chỉ kiểm tra phương thức trả về:

1. **Commit thành công:** gửi hai record vào hai topic trong callback; consumer `read_committed` nhận được cả hai.
2. **Rollback:** gửi record thứ nhất rồi ném exception trước record thứ hai; consumer `read_committed` không nhận record thuộc transaction bị abort.
3. **Send failure:** làm producer không thể gửi hoặc topic/ACL không hợp lệ; xác minh callback/commit báo lỗi và transaction không được coi là thành công.
4. **Transaction ID:** chạy nhiều instance với prefix riêng; xác minh không fencing lẫn nhau.
5. **Isolation level:** so sánh consumer `read_committed` và `read_uncommitted` khi có transaction bị abort.
6. **Transaction timeout:** kiểm tra callback không vượt timeout và hành vi khi broker chậm.
7. **Offset coordination:** nếu use case là consume-transform-produce, kiểm tra output và input offset cùng commit trong transactional listener container.

Test nên dùng Kafka broker thực hoặc embedded broker phù hợp với phiên bản thư viện. Chỉ mock `KafkaTemplate` không xác minh được commit marker, abort và isolation behavior của broker.

## 13. Những nhầm lẫn thường gặp

1. **Cho rằng chỉ cần gọi `executeInTransaction()` là producer tự có transaction.** `ProducerFactory` phải được cấu hình transaction bằng `transactionIdPrefix` hoặc cấu hình tương đương.
2. **Gửi một phần record qua producer khác.** Producer ngoài transaction không được commit/abort cùng callback.
3. **Bắt exception trong callback rồi trả về bình thường.** Transaction có thể commit dù nghiệp vụ đã gặp lỗi.
4. **Cho rằng send future hoàn tất đồng nghĩa transaction đã commit.** Gửi record và commit transaction là hai giai đoạn khác nhau.
5. **Cho rằng consumer mặc định chỉ đọc record đã commit.** Cần cấu hình `isolation.level=read_committed` để ẩn record transactional bị abort.
6. **Dùng cùng transaction ID prefix cho mọi pod.** Có thể gây producer fencing khi nhiều instance hoạt động.
7. **Cho rằng executeInTransaction tự commit offset consumer.** Muốn phối hợp input offset và output record phải dùng mô hình transactional consume-process-produce phù hợp.
8. **Cho rằng Kafka transaction bao gồm database hoặc HTTP.** Tài nguyên ngoài Kafka cần cơ chế phối hợp riêng.
9. **Giữ transaction mở quá lâu.** Có thể vượt transaction timeout, giữ LSO và làm downstream tăng latency.

`executeInTransaction()` giúp gom nhiều thao tác gửi Kafka thành một đơn vị commit/rollback rõ ràng. Hãy cấu hình producer factory có transaction ID prefix duy nhất, dùng `KafkaOperations` trong callback, để exception thoát ra khi cần rollback và đặt consumer downstream ở `read_committed`. Với luồng có consumer offset hoặc database, chọn cơ chế transaction tương ứng thay vì giả định một callback Kafka có thể bao phủ mọi tài nguyên.
