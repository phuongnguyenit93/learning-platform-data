# KafkaTemplate local transaction

## 1. Local transaction của KafkaTemplate là gì?

Trong một số nghiệp vụ, một thao tác cần phát nhiều record Kafka và các record đó phải được ghi nhận cùng nhau. Ví dụ, khi đơn hàng được tạo, dịch vụ có thể phát `OrderCreatedEvent` vào topic `orders` và đồng thời phát `OrderAuditEvent` vào topic `order-audit`.

Nếu gửi từng record bằng các lời gọi `KafkaTemplate.send()` độc lập, record thứ nhất có thể được ghi thành công trong khi record thứ hai thất bại. Consumer khi đó nhìn thấy một phần kết quả, dù nghiệp vụ mong muốn cả hai record cùng xuất hiện hoặc cùng không xuất hiện.

Kafka hỗ trợ producer transaction để nhóm nhiều lần gửi thành một đơn vị nguyên tử trong phạm vi Kafka cluster. Spring Kafka cung cấp `KafkaTemplate.executeInTransaction()` để mở một transaction cục bộ, thực hiện các thao tác gửi trong callback rồi commit khi callback kết thúc bình thường.

Nếu callback ném exception, transaction được abort. Consumer dùng `isolation.level=read_committed` chỉ nhìn thấy các record thuộc transaction đã commit.

Local transaction của `KafkaTemplate` phù hợp khi một đoạn code cần tự quản lý ranh giới transaction gửi Kafka mà không cần đặt toàn bộ phương thức trong một Spring transaction do transaction manager điều phối.

## 2. Luồng thực thi transaction

`executeInTransaction()` nhận một callback làm việc với `KafkaOperations`. Trong callback, ứng dụng có thể gửi nhiều record, kể cả đến các topic hoặc partition khác nhau trong cùng Kafka cluster.

~~~mermaid
flowchart TD
    A["Gọi executeInTransaction()"] --> B["Tạo / lấy transactional producer"]
    B --> C["beginTransaction()"]
    C --> D["Chạy callback"]
    D --> E{"Callback kết thúc bình thường?"}
    E -->|Có| F["commitTransaction()"]
    E -->|Có exception| G["abortTransaction()"]
    F --> H["Record được read_committed consumer nhìn thấy"]
    G --> I["Record thuộc transaction bị loại khỏi read_committed view"]
~~~

Một transaction producer thường gồm các bước:

1. Spring lấy một transactional producer từ `ProducerFactory`.
2. Producer bắt đầu transaction.
3. Các lệnh `send()` trong callback được gửi bằng producer gắn với transaction hiện tại.
4. Khi callback trả về bình thường, Spring commit transaction.
5. Nếu callback thất bại, Spring abort transaction rồi truyền lỗi ra caller.

Lệnh `executeInTransaction()` chỉ trả về kết quả callback sau khi quá trình commit hoàn tất. Nếu commit thất bại, caller nhận exception thay vì kết quả thành công.

Transaction Kafka cung cấp tính nguyên tử cho các record được gửi trong cùng transaction. Nó không tự động bao gồm thao tác database, HTTP request, ghi file hoặc side effect ở hệ thống khác.

## 3. Bật transactional producer trong Spring Boot

`KafkaTemplate.executeInTransaction()` cần một `ProducerFactory` hỗ trợ transaction. Với Spring Boot, cách phổ biến là cấu hình `spring.kafka.producer.transaction-id-prefix`.

Ví dụ:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      transaction-id-prefix: order-service-${INSTANCE_ID:local}-tx-
      acks: all
      properties:
        transaction.timeout.ms: 60000
~~~

Spring Boot dùng prefix này để cấu hình transactional producer factory và tạo transactional ID riêng cho các producer được tạo từ factory.

**Prefix phải duy nhất giữa các instance đang chạy đồng thời.** Trong môi trường nhiều replica, hãy cung cấp `INSTANCE_ID` khác nhau cho từng instance, chẳng hạn pod UID hoặc một định danh instance ổn định. Nếu hai instance đồng thời dùng cùng prefix, transactional ID có thể xung đột và producer này fencing producer kia.

Giá trị `local` trong ví dụ chỉ phù hợp khi chạy một instance đơn lẻ trên máy phát triển. Không dùng cùng giá trị mặc định này cho nhiều replica production.

Một số điểm cần nhớ:

- Không tự đặt một `transactional.id` cố định dùng chung cho mọi producer instance.
- Để Spring Kafka quản lý phần suffix của transactional ID thông qua `transaction-id-prefix`.
- Không tắt idempotence của transactional producer.
- Chọn `transaction.timeout.ms` phù hợp với thời gian tối đa của transaction; broker có giới hạn `transaction.max.timeout.ms`.
- Giữ transaction ngắn. Không thực hiện gọi API chậm hoặc chờ người dùng trong khi transaction đang mở.

Với cấu hình trên, Spring Boot có thể auto-configure `ProducerFactory` và `KafkaTemplate` mang tính transactional. Ứng dụng có thể inject template và gọi `executeInTransaction()`.

## 4. Cấu hình ProducerFactory thủ công

Nếu không dùng auto-configuration của Spring Boot, cần cấu hình transactional ID prefix trên `DefaultKafkaProducerFactory`.

~~~java
import java.util.HashMap;
import java.util.Map;

import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.common.serialization.StringSerializer;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.kafka.core.DefaultKafkaProducerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.core.ProducerFactory;
import org.springframework.kafka.support.serializer.JsonSerializer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class KafkaProducerConfiguration {

    @Bean
    ProducerFactory<String, Object> producerFactory(
            @Value("${app.kafka.transaction-id-prefix}")
            String transactionIdPrefix) {

        Map<String, Object> producerProperties = new HashMap<>();
        producerProperties.put(
            ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
            "localhost:9092"
        );
        producerProperties.put(
            ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
            StringSerializer.class
        );
        producerProperties.put(
            ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
            JsonSerializer.class
        );
        producerProperties.put(ProducerConfig.ACKS_CONFIG, "all");

        var factory =
            new DefaultKafkaProducerFactory<String, Object>(
                producerProperties
            );

        factory.setTransactionIdPrefix(transactionIdPrefix);
        return factory;
    }

    @Bean
    KafkaTemplate<String, Object> kafkaTemplate(
            ProducerFactory<String, Object> producerFactory) {
        return new KafkaTemplate<>(producerFactory);
    }
}
~~~

Ví dụ khai báo property mà bean nhận:

~~~yaml
app:
  kafka:
    transaction-id-prefix: order-service-${INSTANCE_ID:local}-tx-
~~~

`producerProperties` trong ví dụ được tạo với bootstrap server và serializer minh họa; thay `localhost:9092` bằng cấu hình cluster của môi trường. `transactionIdPrefix` phải được lấy từ cấu hình riêng cho từng instance, không hard-code cùng một giá trị cho mọi replica.

Ví dụ trên tập trung vào điểm bật transaction. Trong ứng dụng thật, hãy dùng một cấu hình properties có kiểu rõ ràng và khai báo serializer tương thích với kiểu key/value. Không tạo hai `ProducerFactory` khác nhau rồi kỳ vọng record gửi từ cả hai factory tự động thuộc cùng một transaction.

## 5. Gửi nhiều record trong một local transaction

Ví dụ dịch vụ phát hai sự kiện khi tạo đơn hàng:

~~~java
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;

@Component
public class OrderEventPublisher {

    private final KafkaTemplate<String, Object> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, Object> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public String publish(OrderCreatedEvent orderEvent,
                          OrderAuditEvent auditEvent) {

        return kafkaTemplate.executeInTransaction(operations -> {
            operations.send(
                "orders",
                orderEvent.orderId(),
                orderEvent
            ).join();

            operations.send(
                "order-audit",
                auditEvent.orderId(),
                auditEvent
            ).join();

            return "published";
        });
    }
}
~~~

Trong callback:

- `operations` là `KafkaOperations` gắn với transaction hiện tại.
- Hai lệnh `send()` sử dụng cùng transactional producer.
- `join()` chờ kết quả gửi để lỗi gửi được phát hiện ngay trong callback.
- Callback chỉ trả về `"published"` sau khi cả hai thao tác gửi hoàn tất; `executeInTransaction()` tiếp tục commit transaction trước khi trả kết quả cho caller.

`join()` làm luồng gọi chờ kết quả gửi. Với luồng throughput cao, cần cân nhắc cách phối hợp future và transaction; dù không gọi `join()`, commit transaction vẫn phải hoàn tất các lần gửi còn đang chờ trước khi transaction được commit. Không được coi việc `send()` trả về future là bằng chứng record đã commit.

Nếu một lần gửi thất bại hoặc callback ném exception, transaction bị abort. Không bắt rồi nuốt exception bên trong callback, vì callback kết thúc bình thường sẽ khiến Spring commit các record đã gửi trước đó.

## 6. Điều gì xảy ra khi callback ném exception?

Có thể chủ động ném exception khi một điều kiện nghiệp vụ không đạt:

~~~java
public void publishIfValid(
        OrderCreatedEvent orderEvent,
        OrderAuditEvent auditEvent) {

    kafkaTemplate.executeInTransaction(operations -> {
        operations.send(
            "orders",
            orderEvent.orderId(),
            orderEvent
        ).join();

        if (!auditEvent.isAllowed()) {
            throw new IllegalStateException(
                "Không được phép phát audit event"
            );
        }

        operations.send(
            "order-audit",
            auditEvent.orderId(),
            auditEvent
        ).join();

        return null;
    });
}
~~~

Trong ví dụ này, record đã gửi vào `orders` vẫn thuộc transaction đang mở. Khi callback ném `IllegalStateException`, Spring abort transaction. Consumer ở chế độ `read_committed` sẽ không nhận record đó như một record đã commit.

Một consumer dùng `read_uncommitted` có thể đọc record thuộc transaction chưa commit hoặc đã abort. Vì vậy, nếu yêu cầu nghiệp vụ là chỉ đọc dữ liệu đã commit, cấu hình isolation level phía consumer là bắt buộc.

Đừng viết như sau:

~~~java
kafkaTemplate.executeInTransaction(operations -> {
    try {
        operations.send("orders", orderId, event).join();
        operations.send("order-audit", orderId, audit).join();
    } catch (RuntimeException ex) {
        log.error("Gửi event thất bại", ex);
        // Callback kết thúc bình thường: transaction có thể được commit.
    }
    return null;
});
~~~

Nếu đã quyết định giao dịch thất bại, hãy để exception truyền ra ngoài callback hoặc ném lại một exception runtime. Chỉ log rồi tiếp tục có thể biến lỗi gửi thành transaction commit ngoài ý muốn.

## 7. Consumer phải dùng read_committed

Kafka consumer có thuộc tính `isolation.level`:

| Giá trị | Hành vi |
|---|---|
| `read_uncommitted` | Có thể đọc record từ transaction chưa commit hoặc đã abort; đây là mặc định phổ biến của Kafka consumer |
| `read_committed` | Chỉ trả về record thuộc transaction đã commit và bỏ qua record thuộc transaction đã abort |

Cấu hình Spring Boot:

~~~yaml
spring:
  kafka:
    consumer:
      properties:
        isolation.level: read_committed
~~~

Với `read_committed`, consumer chỉ đọc đến last stable offset của partition. Nếu có transaction đang mở ở partition, record phía sau transaction đó có thể chưa được trả về cho đến khi transaction kết thúc. Đây là hành vi cần hiểu khi quan sát consumer lag hoặc độ trễ đọc.

Cấu hình `read_committed` không làm consumer tự xử lý transaction. Nó chỉ quyết định consumer được phép nhìn thấy những record nào.

Nếu một topic có cả producer transactional và non-transactional, consumer `read_committed` vẫn đọc được record non-transactional đã ghi bình thường; nó lọc theo trạng thái transaction của record.

## 8. Local transaction khác KafkaTransactionManager như thế nào?

Spring Kafka cung cấp nhiều cách quản lý transaction. Cần chọn theo nơi muốn đặt ranh giới transaction:

| Cơ chế | Cách sử dụng | Phù hợp |
|---|---|---|
| `KafkaTemplate.executeInTransaction()` | Mở và kết thúc một local transaction ngay trong callback | Một đoạn code cần gửi nhiều record Kafka theo kiểu all-or-nothing |
| `KafkaTransactionManager` | Tích hợp Kafka transaction với Spring transaction infrastructure | Muốn Spring quản lý transaction Kafka qua transaction manager |
| Transactional listener container | Container bắt đầu transaction cho việc xử lý record; gửi Kafka trong transaction và phối hợp offset theo cấu hình | Consume-transform-produce trong Kafka |
| Database transaction + Outbox | Ghi dữ liệu nghiệp vụ và outbox row trong cùng transaction database; publisher phát outbox sau | Cần phối hợp thay đổi database với việc phát Kafka một cách tin cậy |

`executeInTransaction()` là API cục bộ, tường minh: đoạn code gọi nó quyết định transaction bắt đầu và kết thúc ở đâu. Nó không tự làm cho transaction database hiện có trở thành một transaction phân tán cùng Kafka.

Nếu mục tiêu là xử lý một record đầu vào, phát record đầu ra và commit offset theo cùng Kafka transaction, hãy tìm hiểu transactional listener container và cấu hình `KafkaTransactionManager` phù hợp. Nếu mục tiêu là cập nhật database rồi phát sự kiện, Transactional Outbox thường là lựa chọn dễ vận hành hơn.

## 9. Local transaction không bao gồm database hoặc HTTP

Giả sử callback gửi event Kafka và cập nhật database:

~~~java
kafkaTemplate.executeInTransaction(operations -> {
    operations.send("orders", orderId, event).join();

    orderRepository.markPublished(orderId);

    return null;
});
~~~

Đoạn code này không tạo một transaction nguyên tử giữa Kafka và database. Nếu database commit thành công nhưng Kafka transaction abort, hoặc Kafka commit thành công nhưng database transaction rollback, hai hệ thống có thể ở trạng thái không nhất quán.

Không đặt lệnh ghi database vào callback với giả định `executeInTransaction()` sẽ rollback database. Tương tự, HTTP request, gửi email hoặc ghi file không được Kafka transaction tự động hoàn tác.

Nếu cần ghi database và phát Kafka như một nghiệp vụ bền vững:

1. Trong một database transaction, cập nhật dữ liệu nghiệp vụ và thêm một bản ghi outbox.
2. Một publisher đọc outbox và gửi sự kiện vào Kafka.
3. Publisher đánh dấu outbox đã phát theo cơ chế retry/đối soát.
4. Consumer xử lý idempotent để chịu được việc event được phát lại.

Outbox giải quyết khoảng trống giữa database commit và Kafka publish bằng một bản ghi bền vững trong cùng database transaction. Nó không biến database và Kafka thành một distributed transaction duy nhất.

## 10. Transactional ID, fencing và transaction timeout

Kafka dùng `transactional.id` để nhận diện producer transaction qua các lần tạo producer. Spring Kafka tạo ID dựa trên `transaction-id-prefix` cùng suffix do producer factory quản lý.

Nếu hai producer instance đang hoạt động dùng cùng transactional ID, broker có thể fence producer cũ. Fencing ngăn một producer cũ tiếp tục ghi transaction sau khi quyền sở hữu ID đã chuyển sang producer khác.

Cần chú ý:

- Mỗi application instance đồng thời phải có prefix riêng.
- Trong một instance, producer factory quản lý suffix cho các producer được tạo.
- Prefix nên gắn với định danh instance có chủ đích, không dùng chung tùy tiện giữa replica.
- Khi một instance được thay thế, dùng định danh phù hợp để producer mới có thể fence producer cũ khi cần.
- Transaction phải kết thúc trong giới hạn `transaction.timeout.ms`.
- Broker đặt giới hạn tối đa qua `transaction.max.timeout.ms`.

Không tăng timeout quá lớn chỉ để che callback chạy chậm. Transaction mở lâu có thể giữ last stable offset ở phía consumer và làm tăng độ trễ đọc. Hãy giảm thời gian xử lý trong transaction, tránh chờ dịch vụ bên ngoài và chia nhỏ công việc nếu phù hợp.

## 11. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách khắc phục |
|---|---|---|
| `executeInTransaction()` báo factory không transactional | Chưa cấu hình transaction ID prefix | Cấu hình `transaction-id-prefix` trên Boot hoặc `setTransactionIdPrefix()` |
| Producer bị fencing | Hai instance dùng trùng transactional ID/prefix | Cấp prefix riêng cho mỗi instance đang chạy |
| Consumer nhìn thấy record đã abort | Consumer đang dùng `read_uncommitted` | Chuyển sang `read_committed` nếu chỉ muốn đọc transaction đã commit |
| Transaction timeout | Callback chạy lâu hoặc chờ API bên ngoài | Rút ngắn transaction và điều chỉnh timeout theo broker |
| Một số record xuất hiện, record khác không | Các lần gửi không nằm trong cùng transaction hoặc gửi qua producer factory khác | Dùng cùng template/transaction context trong callback |
| Callback báo lỗi nhưng transaction vẫn commit | Exception bị bắt và nuốt bên trong callback | Ném lại exception để transaction bị abort |
| Nghĩ database đã rollback cùng Kafka | Nhầm local Kafka transaction với distributed transaction | Dùng Outbox hoặc cơ chế phối hợp phù hợp |
| Producer send future chưa hoàn tất | Chưa chờ kết quả hoặc commit chưa hoàn tất | Quan sát future và kết quả của `executeInTransaction()` |

Khi gặp lỗi, kiểm tra transaction ID prefix, producer factory thực tế, transaction timeout, broker logs, send future và isolation level của consumer. Không kết luận transaction thành công chỉ dựa vào việc callback đã chạy hết; cần chờ `executeInTransaction()` trả về thành công.

## 12. Kiểm thử local transaction

Nên kiểm thử cả hai nhánh: commit thành công và abort khi callback thất bại.

**Kiểm thử commit:** gọi `executeInTransaction()` để gửi hai record vào hai topic. Dùng consumer có `isolation.level=read_committed` đọc cả hai topic và xác minh mỗi record xuất hiện đúng một lần.

~~~java
kafkaTemplate.executeInTransaction(operations -> {
    operations.send("orders", "ORD-1", orderEvent).join();
    operations.send("order-audit", "ORD-1", auditEvent).join();
    return null;
});
~~~

**Kiểm thử abort:** gửi record thứ nhất rồi ném exception trước khi callback hoàn tất:

~~~java
assertThatThrownBy(() ->
    kafkaTemplate.executeInTransaction(operations -> {
        operations.send("orders", "ORD-2", orderEvent).join();
        throw new IllegalStateException("force rollback");
    })
).isInstanceOf(RuntimeException.class);
~~~

Sau đó, consumer `read_committed` không được nhận record thuộc transaction đã abort. Để test không bị ảnh hưởng bởi dữ liệu cũ, dùng topic hoặc group ID riêng cho test, và poll với timeout hữu hạn.

Các điểm cần xác minh:

- Producer factory thực sự có transactional ID prefix.
- Hai lần gửi trong callback thuộc cùng transaction.
- Callback kết thúc bình thường thì consumer `read_committed` thấy đủ record.
- Callback ném exception thì consumer `read_committed` không thấy record của transaction bị abort.
- Lỗi commit hoặc publish được truyền về caller.
- Hai instance không dùng trùng prefix.
- Consumer `read_uncommitted` có hành vi quan sát khác, nếu test cần minh họa isolation.

Có thể dùng Embedded Kafka hoặc Testcontainers để kiểm thử với broker thật. Không chỉ mock `KafkaTemplate`, vì mock không chứng minh được broker transaction marker, commit/abort hoặc isolation level hoạt động đúng.

## 13. Checklist triển khai KafkaTemplate local transaction

- [ ] Cấu hình transactional producer bằng `transaction-id-prefix`.
- [ ] Cấp prefix duy nhất cho từng application instance chạy đồng thời.
- [ ] Dùng cùng transactional `KafkaTemplate` cho các record trong callback.
- [ ] Gửi mọi record cần atomicity bên trong `executeInTransaction()`.
- [ ] Để exception truyền ra ngoài callback khi transaction phải abort.
- [ ] Chờ `executeInTransaction()` hoàn tất trước khi báo nghiệp vụ thành công.
- [ ] Cấu hình consumer `isolation.level=read_committed` khi cần chỉ đọc record đã commit.
- [ ] Chọn `transaction.timeout.ms` phù hợp và giữ callback ngắn.
- [ ] Không giả định Kafka transaction bao gồm database, HTTP hoặc file.
- [ ] Dùng Outbox khi cần phối hợp database commit với Kafka publish.
- [ ] Kiểm thử cả commit và abort qua broker thật.
- [ ] Theo dõi fencing, transaction timeout, producer error và consumer lag.

`KafkaTemplate.executeInTransaction()` cung cấp một cách rõ ràng để gửi nhiều record Kafka theo một transaction cục bộ. Khi producer factory có transactional ID prefix riêng cho từng instance, consumer đọc bằng `read_committed` và callback xử lý lỗi đúng cách, ứng dụng có thể bảo đảm các record trong transaction được nhìn thấy cùng nhau hoặc không được nhìn thấy. Ranh giới đó chỉ thuộc Kafka; các side effect ở database và hệ thống ngoài cần cơ chế phối hợp riêng.
