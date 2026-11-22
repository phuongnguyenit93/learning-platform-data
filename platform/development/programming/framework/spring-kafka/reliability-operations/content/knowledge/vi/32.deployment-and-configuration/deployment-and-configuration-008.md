# Cấu hình DLT trong Spring Kafka

## 1. DLT là gì và vì sao cần cấu hình khi triển khai?

Trong **Spring Kafka Reliability Operations**, **DLT (Dead Letter Topic)** là một Kafka topic dùng để giữ những record mà consumer chưa thể xử lý thành công theo chính sách lỗi của ứng dụng. DLT giúp tách một record có vấn đề khỏi luồng xử lý chính, bảo toàn thông tin phục vụ điều tra và tạo điểm xuất phát cho quy trình sửa lỗi, replay hoặc bù trừ.

Ví dụ ứng dụng nhận sự kiện tạo đơn hàng:

~~~text
orders.events
     |
     v
OrderCreatedListener
     |
     +--> Xử lý thành công --> Ghi DB --> Hoàn tất record
     |
     +--> Lỗi tạm thời --> Retry theo chính sách
                                   |
                          Retry vẫn thất bại
                                   |
                                   v
                           orders.events.DLT
                                   |
                         Điều tra / sửa / replay
~~~

Nếu consumer cứ retry mãi một record hỏng, partition có thể bị chặn và consumer lag tăng. Nếu chỉ catch exception rồi bỏ qua record, dữ liệu có thể bị mất mà không có bằng chứng. DLT là một cách **cách ly và lưu lại record lỗi**, nhưng **không tự sửa dữ liệu hoặc bảo đảm end-to-end exactly-once**.

Mục tiêu bài này là cấu hình DLT đủ rõ để triển khai và vận hành:

- Phân biệt retry, recovery và dead-letter publishing.
- Chuẩn bị Kafka topic, partition, replication, retention và quyền truy cập.
- Dùng **DefaultErrorHandler** kết hợp **DeadLetterPublishingRecoverer** cho record listener.
- Kiểm soát lỗi khi chính việc gửi DLT thất bại.
- Xử lý các lỗi JSON, validation, database timeout và deserialization.
- Phân biệt blocking retry với **@RetryableTopic**.
- Theo dõi DLT, điều tra, replay an toàn và không tạo vòng lặp vô hạn.
- Kiểm thử cấu hình bằng Embedded Kafka hoặc Kafka Testcontainers.

Các ví dụ chính dùng **Java 17, Spring Boot 3.x và Spring Kafka 3.x**. Trong dự án có phiên bản khác, cần đối chiếu API và các thuộc tính được hỗ trợ theo dependency thực tế.

## 2. Những khái niệm cần phân biệt

| Khái niệm | Ý nghĩa | Liên hệ với DLT |
| --- | --- | --- |
| **Consumer record** | Một bản ghi ở topic/partition/offset cụ thể | Bản ghi gốc được retry hoặc chuyển DLT |
| **Retry** | Thử xử lý lại sau lỗi | Có thể thử nhiều lần trước khi recover |
| **Backoff** | Khoảng nghỉ giữa các lần retry | Giảm tải khi lỗi tạm thời |
| **Recoverer** | Thành phần được gọi khi lỗi không được giải quyết bằng retry | Có thể publish tới DLT |
| **DLT** | Topic giữ record không xử lý thành công | Phục vụ audit, triage và replay |
| **Poison record** | Record có lỗi dữ liệu hoặc luôn làm consumer fail | Không nên retry vô hạn |
| **Offset commit** | Lưu vị trí xử lý của consumer group | Quyết định record gốc có được giao lại không |
| **Redrive/replay** | Đưa record từ DLT trở lại một pipeline xử lý | Phải kiểm soát duplicate và idempotency |
| **Consumer lag** | Độ trễ tiến độ consumption | Có thể tăng khi retry chặn partition |

Một Kafka record được chuyển sang DLT không có nghĩa **đã được xử lý thành công về nghiệp vụ**. Nó chỉ cho biết record đã đi qua một nhánh recovery đã được cấu hình.

Với message ảnh hưởng số dư, đơn hàng, thanh toán hoặc dữ liệu khách hàng, cần một quy trình giải quyết record DLT đến cùng: chủ sở hữu, deadline, kết quả xử lý và trạng thái nghiệp vụ.

## 3. Chọn chiến lược lỗi trước khi cấu hình

Không phải exception nào cũng nên retry giống nhau.

| Nhóm lỗi | Ví dụ | Chiến lược thường phù hợp |
| --- | --- | --- |
| **Lỗi tạm thời** | Database timeout, service HTTP 503, lock timeout | Retry có giới hạn và backoff |
| **Lỗi dữ liệu không hợp lệ** | JSON sai schema, amount âm, thiếu trường bắt buộc | DLT/quarantine sớm; không retry vô ích |
| **Lỗi nghiệp vụ cần can thiệp** | Mã sản phẩm chưa được cấu hình, tài khoản bị chặn | DLT hoặc workflow chờ bổ sung dữ liệu |
| **Lỗi hạ tầng kéo dài** | Database down, Kafka DLT broker không sẵn sàng | Cân nhắc dừng/pause consumer, cảnh báo và không bỏ record |
| **Lỗi cấu hình/bug triển khai** | ClassCastException, mapping lỗi toàn bộ batch | Dừng/rollback deployment có thể tốt hơn đẩy hàng triệu record vào DLT |
| **Payload conflict/idempotency** | Cùng eventId nhưng giá trị khác | Cách ly, cảnh báo và không tự áp dụng lại |

DLT không phải lựa chọn duy nhất. Với dữ liệu bắt buộc giữ đúng thứ tự, việc chuyển một record lỗi sang DLT rồi xử lý tiếp record sau có thể vi phạm hợp đồng nghiệp vụ. Khi đó cần chọn chiến lược **pause partition, chặn tiến độ, hoặc quản lý trạng thái workflow** thay vì coi DLT như cách “bỏ qua cho nhanh”.

## 4. Kiến trúc đề xuất cho một consumer

Giả sử hệ thống có:

- Topic nguồn: **orders.events**.
- Consumer group nghiệp vụ: **order-processor-v1**.
- Topic lỗi: **orders.events.DLT**.
- Dịch vụ xử lý đơn hàng ghi xuống PostgreSQL.
- Một quy trình quan sát DLT riêng, không tự replay mọi record ngay khi nhận.

~~~text
                       Kafka broker
                    topic orders.events
                            |
                            v
                  Spring Kafka listener
                            |
                     business service
                            |
                +-----------+------------+
                |                        |
            SUCCESS                  EXCEPTION
                |                        |
      DB transaction commit       DefaultErrorHandler
                |                        |
      Container tiến hành ack       +-----+------+
      / commit theo chính sách      |            |
                                Retry OK    Retry hết lượt
                                    |            |
                                    v            v
                                Hoàn tất    DeadLetterPublishing
                                                Recoverer
                                                    |
                                             publish và kiểm tra
                                                    |
                                                    v
                                           orders.events.DLT
                                                    |
                                            Triage / alert /
                                          sửa nguyên nhân / replay
~~~

**Database commit và Kafka consumer offset commit thường không nằm trong cùng transaction nguyên tử.** Record có thể được giao lại sau khi database đã commit nhưng offset chưa được commit. Vì vậy consumer vẫn cần **idempotency theo business event ID**; DLT không giải quyết được riêng vấn đề duplicate.

## 5. Chuẩn bị topic DLT trước khi chạy ứng dụng

Một chiến lược đặt tên dễ quan sát là:

~~~text
Source topic: orders.events
DLT topic:    orders.events.DLT
~~~

Tên này là **quy ước của ứng dụng**. Spring Kafka có thể dùng quy ước mặc định khác trong một số cấu hình; nếu muốn đích **.DLT**, hãy cấu hình resolver tường minh.

Các thuộc tính cần quyết định:

| Thành phần | Ví dụ triển khai | Lý do |
| --- | --- | --- |
| **Partitions** | DLT có ít nhất số partition nguồn nếu giữ nguyên partition index | Tránh publish lỗi vì partition không tồn tại |
| **Replication factor** | 3 trên cluster có ít nhất 3 broker | Chịu lỗi broker theo chính sách cụm |
| **Retention** | Theo SLA điều tra/replay và quy định dữ liệu | Tránh record biến mất trước khi xử lý |
| **Cleanup policy** | Thường delete theo thời gian | DLT thường cần giữ lịch sử lỗi |
| **ACLs** | App được write DLT, đội vận hành có quyền read thích hợp | Kiểm soát dữ liệu nhạy cảm |
| **Message size** | Đủ cho payload + headers lỗi | Tránh không publish được record lớn |
| **Monitoring** | Alert trên record DLT và độ tuổi lỗi | Không để DLT thành nơi tồn đọng vô hình |

Ví dụ nếu nguồn **orders.events** có ba partition, resolver giữ partition gốc thì DLT cũng phải có partition 0, 1 và 2. **DLT ít partition hơn nguồn sẽ gây lỗi** với những record thuộc partition không tồn tại tại đích.

### Ví dụ tạo topic qua Kafka CLI

Ở cluster production có đủ broker:

~~~bash
kafka-topics.sh \
  --bootstrap-server kafka-01.example.internal:9092 \
  --create \
  --topic orders.events.DLT \
  --partitions 3 \
  --replication-factor 3
~~~

Đây là ví dụ shell với bootstrap server minh họa. Nếu cluster local chỉ có một broker, replication factor 3 không hợp lệ; môi trường test có thể dùng factor 1. Nên tạo và cập nhật topic/ACL bằng Terraform, Helm, Strimzi, Kafka admin pipeline hoặc quy trình hạ tầng tương ứng, thay vì tạo thủ công không có version control.

Kiểm tra:

~~~bash
kafka-topics.sh \
  --bootstrap-server kafka-01.example.internal:9092 \
  --describe \
  --topic orders.events.DLT
~~~

Đối với dữ liệu quan trọng, cần kiểm tra thêm **min.insync.replicas**, producer acknowledgements, dung lượng retention và chính sách backup/giữ chứng cứ theo yêu cầu tổ chức.

### Tạo topic bằng Spring KafkaAdmin

Trong môi trường cho phép ứng dụng quản lý topic, có thể khai báo:

~~~java
import org.apache.kafka.clients.admin.NewTopic;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.TopicBuilder;

@Configuration
public class TopicConfiguration {

    @Bean
    NewTopic ordersDltTopic() {
        return TopicBuilder.name("orders.events.DLT")
                .partitions(3)
                .replicas(3)
                .build();
    }
}
~~~

Khi triển khai trên broker đơn để test, cần override cấu hình replication factor/bean theo môi trường. Trong production, nhiều tổ chức **không cấp quyền CREATE topic** cho ứng dụng; lúc đó hạ tầng sẽ tạo sẵn topic và Spring Kafka chỉ sử dụng.

## 6. Cấu hình consumer và producer trong Spring Boot

Ví dụ ứng dụng đọc giá trị Kafka dưới dạng **String**, còn Jackson parse JSON **bên trong listener**. Cách này làm rõ việc một chuỗi JSON không hợp lệ có thể đi qua listener error handler dưới dạng exception của code ứng dụng.

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka-01.example.internal:9092
    consumer:
      group-id: order-processor-v1
      enable-auto-commit: false
      auto-offset-reset: earliest
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
    producer:
      acks: all
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
      properties:
        enable.idempotence: true
    listener:
      ack-mode: record
~~~

Giải thích:

- **enable-auto-commit=false:** để listener container quản lý offset theo cơ chế đã cấu hình, tránh auto commit độc lập với xử lý ứng dụng.
- **ack-mode: record:** với record listener, container xử lý commit offset tương ứng sau khi listener đã xử lý thành công hoặc error handler đã hoàn tất recovery theo contract.
- **StringDeserializer:** payload JSON lỗi cú pháp vẫn tới listener dưới dạng chuỗi, nơi Jackson có thể ném exception.
- **acks=all:** yêu cầu producer nhận xác nhận từ các replica in-sync theo cấu hình broker.
- **enable.idempotence=true:** giúp producer giảm một số duplicate ở log Kafka do retry trong phạm vi cơ chế producer idempotence; **không thay thế idempotency nghiệp vụ**.

**auto-offset-reset=earliest** chỉ tác động khi consumer group chưa có offset hợp lệ (và một số trường hợp offset ngoài phạm vi). Nó không phải cơ chế retry hoặc DLT; chọn earliest/latest theo chính sách triển khai.

Mã ví dụ dùng cùng một KafkaTemplate để publish DLT với key/value dạng **String**, do đó serializer trên producer phải phù hợp. Nếu consumer nhận đối tượng JSON hoặc raw bytes trong trường hợp deserialization failure, phần serializer cần cấu hình khác (xem phần 11).

## 7. DeadLetterPublishingRecoverer và DefaultErrorHandler

Hai thành phần chính trong chiến lược **blocking retry** của Spring Kafka:

- **DefaultErrorHandler:** nhận lỗi phát sinh từ listener, quyết định retry và gọi recoverer khi hết lượt hoặc khi exception không cần retry.
- **DeadLetterPublishingRecoverer:** gửi record lỗi tới topic đích bằng một Kafka producer.

Ví dụ Spring Kafka 3.x:

~~~java
import org.apache.kafka.common.TopicPartition;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

@Configuration
public class KafkaErrorHandlingConfiguration {

    @Bean
    DefaultErrorHandler errorHandler(
            KafkaTemplate<Object, Object> kafkaTemplate) {

        DeadLetterPublishingRecoverer recoverer =
                new DeadLetterPublishingRecoverer(
                        kafkaTemplate,
                        (record, exception) ->
                                new TopicPartition(
                                        record.topic() + ".DLT",
                                        record.partition()));

        // Không coi một send bất đồng bộ thất bại là recovery thành công.
        recoverer.setFailIfSendResultIsError(true);

        // Sau lần thử đầu, retry thêm tối đa 2 lần
        // với khoảng nghỉ 1.500 ms.
        DefaultErrorHandler handler =
                new DefaultErrorHandler(
                        recoverer,
                        new FixedBackOff(1_500L, 2L));

        handler.addNotRetryableExceptions(
                InvalidOrderPayloadException.class);

        return handler;
    }
}
~~~

Một exception domain cho payload không hợp lệ:

~~~java
public class InvalidOrderPayloadException
        extends RuntimeException {

    public InvalidOrderPayloadException(
            String message, Throwable cause) {
        super(message, cause);
    }

    public InvalidOrderPayloadException(String message) {
        super(message);
    }
}
~~~

**Cấu hình trên dùng String key/value như ví dụ YAML.** Với các ứng dụng có bean KafkaTemplate generic/type khác, hãy tạo hoặc inject KafkaOperations/KafkaTemplate có serializer phù hợp, thay vì chỉ ép generic type để che lỗi.

### Diễn giải số lần thử

**FixedBackOff(1_500L, 2L)** biểu diễn **hai lần retry sau lần xử lý ban đầu**. Nếu cả ba attempt đều thất bại và recoverer gửi DLT thành công, error handler có thể coi record đó đã được recovery theo cơ chế container. Nếu exception thuộc nhóm non-retryable, handler có thể đi thẳng tới recoverer theo classifier.

Trong ví dụ, class **InvalidOrderPayloadException** đại diện lỗi dữ liệu không thể sửa bằng chờ thêm vài giây. Một **database timeout** có thể được retry; tuy nhiên nếu database down kéo dài, đẩy hàng nghìn record vào DLT có thể không phù hợp. Cần policy dừng/pause consumer, circuit breaker hoặc backoff phù hợp cho sự cố diện rộng.

### Vì sao đặt partition DLT bằng partition gốc?

Resolver dùng:

~~~java
new TopicPartition(
        record.topic() + ".DLT",
        record.partition())
~~~

Điều này giữ một quan hệ dễ truy vết giữa partition nguồn và partition DLT. Nó chỉ hoạt động nếu DLT có partition index tương ứng. Khi muốn Kafka tự quyết định partition theo key, có thể thiết kế resolver trả partition âm phù hợp API thay vì cố truy cập partition không tồn tại; nhưng phải xác minh tác động tới ordering và partition affinity của quy trình replay.

Đừng mặc định rằng DLT luôn giữ tuyệt đối thứ tự của source topic, đặc biệt khi có retry, những record lỗi khác nhau được gửi vào DLT ở những thời điểm khác nhau hoặc nhiều consumer cùng hoạt động.

## 8. Listener mẫu và các loại exception

Một listener nhận giá trị String rồi parse:

~~~java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderEventListener {

    private final ObjectMapper mapper;
    private final OrderService orderService;

    public OrderEventListener(
            ObjectMapper mapper, OrderService orderService) {
        this.mapper = mapper;
        this.orderService = orderService;
    }

    @KafkaListener(
            topics = "orders.events",
            groupId = "order-processor-v1")
    public void onMessage(ConsumerRecord<String, String> record) {
        OrderEvent event;

        try {
            event = mapper.readValue(
                    record.value(), OrderEvent.class);
        } catch (JsonProcessingException ex) {
            throw new InvalidOrderPayloadException(
                    "Invalid order event JSON", ex);
        }

        if (event.eventId() == null
                || event.eventId().isBlank()
                || event.orderId() == null
                || event.orderId().isBlank()) {
            throw new InvalidOrderPayloadException(
                    "Missing required order event fields");
        }

        orderService.apply(event);
    }
}
~~~

Model:

~~~java
import java.math.BigDecimal;

public record OrderEvent(
        String eventId,
        String orderId,
        BigDecimal amount) {
}
~~~

**OrderService** là thành phần domain phải triển khai. Ví dụ này giả định OrderService ghi database với transaction và idempotency thích hợp; DLT không tự bảo đảm điều đó.

Hành vi minh họa:

1. JSON hợp lệ và domain xử lý thành công: listener trả về bình thường.
2. JSON sai cú pháp: ném **InvalidOrderPayloadException**, thuộc non-retryable, đi tới DLT theo handler.
3. JSON hợp lệ nhưng thiếu trường định danh: đi tới DLT với lỗi validation.
4. Database timeout từ OrderService: DefaultErrorHandler retry theo backoff, sau đó gọi recoverer nếu vẫn không xử lý được.

**Không bắt mọi RuntimeException rồi return bình thường** trong listener, vì container có thể coi record đã xử lý thành công và commit tiến độ mà không có DLT/audit.

## 9. Khi DLT publish thành công, offset gốc sẽ ra sao?

Đây là quyết định quan trọng về **khả năng mất record**.

~~~text
Source offset 120:
    Listener attempt 1 -> fail
    Listener retry 1   -> fail
    Listener retry 2   -> fail
    Recoverer publish  -> DLT success
    Handler returns    -> record được coi đã recover
    Container          -> tiếp tục theo ack/commit policy
~~~

Với record listener và chế độ **AckMode.RECORD**, container thường commit tiến độ khi handler đã xử lý lỗi và trả về theo cơ chế Spring Kafka. **DefaultErrorHandler** có thuộc tính **ackAfterHandle** liên quan việc container commit offset đã recover; cần hiểu cài đặt này trước khi đổi sang manual ack hoặc dùng transaction.

Nếu recoverer publish thất bại hoặc ném exception, record **không được coi đã recovery thành công** và error handler/container có thể thử lại theo cơ chế lỗi. Trong ví dụ dùng **setFailIfSendResultIsError(true)** để tránh coi một send lỗi của producer là thành công.

Tuy nhiên, **DLT publish và offset commit vẫn có cửa sổ lỗi**. Có thể đã gửi DLT thành công nhưng process crash trước khi offset gốc được commit; sau restart, record được xử lý lại và có thể có **hai bản copy trong DLT**. Vì vậy:

- DLT consumer/replay tool cũng cần có business idempotency.
- Không dùng “DLT count bằng 1” làm bảo đảm tuyệt đối cho một logical event.
- Nếu cần giao dịch Kafka có bảo đảm mạnh hơn trong một pipeline Kafka-to-Kafka, phải xem xét transactional listener container, producer và kiểu error handling tương ứng; không suy ra mọi side effect JDBC là nguyên tử với Kafka.
- Khi chuyển sang **MANUAL** hoặc **MANUAL_IMMEDIATE** ack mode, cần kiểm chứng lại semantics offset; không sao chép mặc định của RECORD sang manual ack mà không test.

**Không ack offset sớm chỉ để tránh duplicate.** Nếu ack trước khi DLT được ghi bền vững, quá trình lỗi có thể khiến record gốc bị bỏ qua mà không còn một bản lỗi có thể truy xuất.

## 10. DLT record chứa những gì?

Với **DeadLetterPublishingRecoverer**, record được gửi tới DLT thường giữ **key/value** ban đầu phù hợp với serializer và bổ sung headers cung cấp thông tin về record gốc và lỗi.

Ví dụ một bản mô tả:

~~~text
Destination topic : orders.events.DLT
Destination part. : 1
Value            : {"eventId":"evt-9","orderId":null,"amount":125.00}

Headers (minh họa):
  original topic     : orders.events
  original partition : 1
  original offset    : 120
  exception class    : InvalidOrderPayloadException
  exception message  : Missing required order event fields
  stack trace        : tùy cấu hình/phiên bản
~~~

Spring Kafka cung cấp các Kafka header constants liên quan DLT trong lớp **KafkaHeaders**. Kiểu và nội dung cụ thể của headers có thể khác theo phiên bản và cách cấu hình recoverer, nên khi viết công cụ đọc DLT cần kiểm tra thực tế trên phiên bản thư viện đang chạy.

Những lưu ý:

- **DLT offset mới** không phải offset gốc. Ghi nhận original topic/partition/offset để điều tra.
- Header exception có thể rất lớn, đặc biệt stack trace, làm tăng record size và băng thông.
- Message exception không được chứa password, token, raw PII hoặc dữ liệu không nên đưa vào Kafka.
- Có thể có nhiều headers cùng key hoặc các header được bổ sung sau nhiều lần re-drive; cần hiểu cách recoverer cập nhật/giữ header.
- Key/value của DLT có thể không parse được theo schema hiện tại; dashboard và tool xử lý DLT không nên mặc định deserialize thành DTO như record hợp lệ.

DLT chỉ giữ record cho tới khi retention/cleanup policy xóa nó. Không coi DLT là hệ thống lưu trữ vĩnh viễn nếu chưa thiết kế retention và backup/audit phù hợp.

## 11. Lỗi deserialization xảy ra trước khi listener chạy

Một vấn đề khác với ví dụ String payload là consumer dùng **JsonDeserializer** trực tiếp. Nếu record không decode được, exception có thể xảy ra **trong Kafka poll/deserialization**, trước khi **@KafkaListener** được gọi.

Khi đó một try/catch trong listener không thể bắt lỗi vì listener chưa nhận event.

Cách thường dùng với Spring Kafka là **ErrorHandlingDeserializer**, bọc một deserializer delegate và cung cấp thông tin lỗi để container error handling có thể xử lý.

Ví dụ cấu hình cho một DTO cụ thể:

~~~yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.value.default.type: com.example.kafka.OrderEvent
        spring.json.trusted.packages: com.example.kafka
~~~

Trong cấu hình này, **com.example.kafka.OrderEvent** chỉ là tên class minh họa; phải thay bằng package/class thực. Không dùng trusted packages là ký tự đại diện toàn bộ nếu không có lý do và biện pháp kiểm soát phù hợp.

### Serializer cho record lỗi từ ErrorHandlingDeserializer

Một record bị **JsonDeserializer** từ chối có thể được recoverer gửi tới DLT với **raw byte[] ban đầu**, trong khi record hợp lệ có thể là một **OrderEvent** object. Nếu DLT KafkaTemplate chỉ dùng **JsonSerializer** hoặc **StringSerializer** cho tất cả value, nó có thể không gửi đúng cả hai dạng.

Một hướng cấu hình producer cho DLT là dùng serializer theo loại payload:

~~~java
Map<Class<?>, Serializer<?>> serializers = Map.of(
        byte[].class, new ByteArraySerializer(),
        OrderEvent.class, new JsonSerializer<OrderEvent>());

Serializer<Object> valueSerializer =
        new DelegatingByTypeSerializer(serializers, true);
~~~

Đoạn này minh họa cơ chế; khi triển khai cần khai báo các import Spring Kafka/Apache Kafka, thiết lập ProducerFactory và KafkaTemplate tương ứng với key serializer cũng như kiểu value thực tế. Phải test cả **event hợp lệ nhưng xử lý thất bại** và **raw bytes không deserialize được**. Đừng áp dụng nguyên serializer của ví dụ **StringDeserializer + StringSerializer** cho mọi pipeline JSON mà không xét hình dạng payload.

### Phân biệt hai đường xử lý

| Tình huống | Điểm lỗi | Điều cần kiểm tra |
| --- | --- | --- |
| StringDeserializer, Jackson parse trong listener | Listener | DefaultErrorHandler nhận exception từ listener |
| JsonDeserializer delegate bị lỗi | Trước listener | ErrorHandlingDeserializer mang thông tin lỗi để handler recover |
| Schema registry/Avro decode lỗi | Trước listener | ErrorHandlingDeserializer + producer DLT hỗ trợ raw bytes |
| DTO hợp lệ nhưng business validation lỗi | Listener/service | Handler classify, retry hoặc DLT |
| Business DB timeout | Service trong listener | Retry/backoff, transaction rollback, idempotency |

## 12. Chọn blocking retry hay non-blocking retry topics?

Có hai mẫu triển khai phổ biến.

### 12.1. Blocking retry với DefaultErrorHandler

Record lỗi được thử lại trong luồng xử lý của listener container theo chính sách error handler. Với một partition, điều này có thể trì hoãn các record phía sau.

~~~text
orders.events partition-0
  offset 10: lỗi -> retry -> retry -> DLT
  offset 11: chờ phía sau
~~~

Ưu điểm:

- Cấu hình trực tiếp với **DefaultErrorHandler** và recoverer.
- Dễ áp dụng retry ngắn cho lỗi tạm thời.
- Không cần tạo nhiều topic retry.

Hạn chế:

- Retry chặn tiến độ partition trong thời gian xử lý.
- Với sự cố kéo dài, nhiều record có thể bị ảnh hưởng.
- Không phù hợp nếu cần trì hoãn retry hàng phút/giờ trong cùng listener thread.

### 12.2. Non-blocking retry với @RetryableTopic

Spring Kafka có cơ chế dùng các **retry topics** để chuyển record thất bại sang topic retry và xử lý sau theo chiến lược backoff, cuối cùng mới tới DLT.

~~~text
orders.events
    |
  failure
    v
orders.events-retry-...  (delay)
    |
  failure
    v
orders.events-retry-...  (delay)
    |
  still failure
    v
orders.events.DLT
~~~

Ví dụ ý tưởng cấu hình, sử dụng **một chiến lược thay thế** cho luồng listener tương ứng:

~~~java
@RetryableTopic(
        attempts = "4",
        backoff = @Backoff(delay = 1_000, multiplier = 2.0),
        dltTopicSuffix = ".DLT",
        autoCreateTopics = "false")
@KafkaListener(
        topics = "orders.events",
        groupId = "order-processor-v1")
public void onMessage(String payload) {
    orderService.handle(payload);
}
~~~

Cần import **org.springframework.kafka.annotation.RetryableTopic**, **org.springframework.retry.annotation.Backoff**, **KafkaListener** và các class ứng dụng. Đây là minh họa cơ chế non-blocking retry: số lần gửi, tên retry topics, cấu trúc backoff và cách xử lý DLT phụ thuộc cấu hình chính xác. Nếu đặt **autoCreateTopics=false**, pipeline triển khai phải provision đầy đủ **retry topics và DLT topic** theo tên/partition/replication được framework tính ra.

Không áp dụng đồng thời một DefaultErrorHandler tự publish thẳng **.DLT** cho cùng listener trong khi cũng dùng **@RetryableTopic**, nếu chưa phân tích rõ đường đi; có thể làm bỏ qua retry topics hoặc tạo nhiều nhánh recovery chồng nhau.

Ưu điểm:

- Không giữ listener ở source topic chờ lâu cho một record.
- Phù hợp retry có độ trễ dài và cần hạn chế chặn partition.

Hạn chế:

- Cần nhiều topic và consumer group; tăng độ phức tạp deployment/monitoring.
- Record có thể được xử lý **không còn đúng thứ tự ban đầu**.
- Thiết kế không phù hợp cho những luồng bắt buộc giữ strict ordering trên cùng entity.
- Cần kiểm thử timeout, retention, DLT handler, topology và idempotency tương ứng.

**Quy tắc chọn:** retry ngắn và ordering quan trọng có thể dùng blocking strategy; retry dài và throughput ưu tiên có thể cân nhắc retry topics. Đừng lựa chọn dựa trên tên annotation mà không xem yêu cầu nghiệp vụ.

## 13. DLT handler: nhận để điều tra, không tự động xử lý lại vô hạn

Một DLT có thể được tiêu thụ bởi:

- Công cụ quản trị chỉ đọc và hiển thị thông tin.
- Dịch vụ audit lưu metadata của lỗi.
- Quy trình sửa dữ liệu và re-drive có phê duyệt.
- Consumer thực thi compensation nếu hợp đồng nghiệp vụ yêu cầu.

Không nên tạo listener đọc **orders.events.DLT** rồi ngay lập tức publish mọi message trở lại **orders.events**, vì record poison có thể lặp vô hạn.

Một service audit tối giản:

~~~java
@Component
public class OrderDltAuditListener {

    private final DltAuditService auditService;

    public OrderDltAuditListener(DltAuditService auditService) {
        this.auditService = auditService;
    }

    @KafkaListener(
            topics = "orders.events.DLT",
            groupId = "order-dlt-audit-v1")
    public void onDlt(ConsumerRecord<String, String> record) {
        auditService.recordFailure(
                record.topic(),
                record.partition(),
                record.offset(),
                record.key(),
                record.value(),
                record.headers());
    }
}
~~~

**DltAuditService** trong ví dụ là thành phần tự triển khai. Nó cần kiểm soát thông tin nhạy cảm, chỉ lưu dữ liệu cần thiết và có idempotency nếu bản DLT được redeliver.

Nếu dùng **@RetryableTopic**, cũng có thể có **@DltHandler** trong mô hình annotation của Spring Kafka. Cần chọn một đường audit/handler phù hợp thay vì cấu hình hai consumer độc lập cùng thực hiện side effect không kiểm soát.

Đừng đánh dấu business event **COMPLETED** chỉ vì DLT audit đã nhận record. Business status và DLT processing status là hai khái niệm khác nhau.

## 14. Quy trình re-drive/replay từ DLT

Khi vấn đề được khắc phục, một record có thể được đưa trở lại pipeline. Nhưng replay cần có thiết kế **idempotent**.

~~~text
orders.events.DLT
       |
       v
Triage: xác định nguyên nhân
       |
       +--> Dữ liệu thật sự không hợp lệ: quarantine / đóng ticket
       |
       +--> Thiếu cấu hình: sửa reference data
       |
       +--> Lỗi phần mềm: triển khai phiên bản sửa
       |
       v
Kiểm tra điều kiện replay
       |
       v
Publish lại với eventId gốc + thông tin audit
       |
       v
orders.events (hoặc topic replay riêng)
       |
       v
Consumer idempotent
       |
       v
Reconciliation + đóng ticket
~~~

Các nguyên tắc:

1. **Giữ eventId/operationId gốc** cho cùng logical business event. Tạo eventId mới sẽ làm mất cơ chế deduplication.
2. **Không dùng offset DLT làm identity nghiệp vụ**, vì đó là offset mới của bản lỗi.
3. Có thể gắn **replayAttempt**, **original topic/partition/offset** và correlation ID làm header phục vụ truy vết.
4. Giới hạn số lần replay; tránh vòng lặp source → DLT → source → DLT vô hạn.
5. Có quyền truy cập và phê duyệt phù hợp, đặc biệt cho event tài chính.
6. Khi cần đảm bảo thứ tự, replay theo aggregate/business key có kiểm soát; không chỉ bắn toàn bộ DLT song song.
7. **Kiểm tra outcome tại hệ thống đích** và cập nhật trạng thái ticket; việc Kafka producer gửi lại thành công chưa đồng nghĩa business xử lý thành công.
8. Nếu code hoặc schema thay đổi, xác định có giữ nguyên payload hay thực hiện một quá trình migration có kiểm soát.

### Replay và duplicate delivery

Kafka có thể gửi một record tới DLT hơn một lần do cửa sổ lỗi giữa send DLT và offset commit của source. Re-drive tool có thể nhìn thấy nhiều bản mang cùng eventId.

Một service nghiệp vụ an toàn thường có **unique constraint trên operationId/eventId** và ghi side effect + marker trong cùng transaction. Điều này cho phép replay mà không nhân đôi tác động nghiệp vụ.

DLT **lưu dấu lỗi**, còn idempotency **bảo vệ việc áp dụng tác động**. Cần cả hai trong nhiều hệ thống quan trọng.

## 15. Quyền truy cập và bảo vệ dữ liệu trên DLT

DLT thường chứa dữ liệu lỗi chưa được làm sạch. Header exception hoặc payload có thể tiết lộ:

- Định danh khách hàng, số tài khoản, địa chỉ hoặc số điện thoại.
- Đường dẫn hệ thống nội bộ, class name, stack trace.
- JSON lỗi chưa đi qua cơ chế redaction.
- Token hoặc nội dung nhạy cảm nếu exception message được tạo cẩu thả.

Các yêu cầu bảo mật:

- Consumer nghiệp vụ chỉ cần **WRITE** topic DLT nếu không đọc.
- DLT audit/replay service được cấp quyền **READ** phù hợp, tách khỏi consumer production nếu cần.
- Chỉ nhân sự được ủy quyền xem payload gốc; dashboard phổ thông nên hiển thị error category, count, timestamp và correlation ID.
- Kafka broker kết nối qua TLS và authentication/ACL phù hợp.
- Retention gắn với chính sách dữ liệu và nhu cầu điều tra, không giữ vĩnh viễn vì tiện lợi.
- Exception message/stack trace cần giới hạn dữ liệu nhạy cảm và có thể cần redaction.
- Không dùng topic DLT làm kho lưu trữ tài liệu nghiệp vụ duy nhất.

Nếu DLT record vượt giới hạn message size do payload/header quá lớn, producer sẽ không publish thành công. Đừng giải quyết bằng cách nâng giới hạn vô hạn; cân nhắc rút gọn exception headers hoặc chuyển nội dung chi tiết sang audit store an toàn có correlation ID.

## 16. Retention và khả năng xử lý tồn đọng

Giả sử tổ chức cho phép điều tra/replay record DLT trong tối đa 14 ngày. Một retention chỉ 3 ngày sẽ làm record biến mất trước khi đội vận hành xử lý.

Ngược lại, retention quá dài có thể tăng chi phí lưu trữ và rủi ro dữ liệu. Cần thỏa thuận:

| Yếu tố | Câu hỏi |
| --- | --- |
| **Triage SLA** | Bao lâu phải nhận biết và phân loại lỗi? |
| **Replay window** | Tối đa bao lâu sau lỗi mới được re-drive? |
| **Source retention** | Source topic còn record gốc không? |
| **DLT retention** | DLT phải lưu đủ lâu để xử lý theo SLA? |
| **Compliance** | Payload có dữ liệu nhạy cảm cần hạn chế thời gian lưu? |
| **Marker retention** | Dedupe marker còn tồn tại khi replay muộn? |
| **Backup/archive** | Có cần xuất báo cáo audit bền vững ngoài Kafka? |

Một rủi ro phổ biến: **DLT giữ record 30 ngày, nhưng bảng idempotency marker chỉ giữ 7 ngày**. Khi replay event đã từng áp dụng vào ngày 20, marker có thể đã bị xóa, tạo side effect lặp. Hai chính sách retention phải được thiết kế cùng nhau.

## 17. Quan sát DLT bằng metrics và alert

Bật DLT nhưng không quan sát chẳng khác nào chuyển lỗi từ log này sang một nơi không ai kiểm tra.

Các tín hiệu nên theo dõi:

| Chỉ số | Công dụng |
| --- | --- |
| **DLT published total** | Số record được recoverer gửi tới DLT |
| **DLT publish failures total** | Phát hiện không thể lưu record lỗi |
| **DLT backlog/lag** | Số record đang chờ audit/triage trong group tương ứng |
| **Oldest unresolved DLT age** | Phát hiện ticket tồn đọng vượt SLA |
| **Consumer retry attempts** | Phát hiện lỗi tạm thời lặp lại |
| **Consumer lag nguồn** | Xem retry có đang chặn partition |
| **Processing error categories** | Phân biệt validation/DB timeout/bug |
| **Replay success/failure** | Theo dõi khắc phục thực tế |
| **Partition skew** | Một partition có quá nhiều poison records |
| **Broker/topic disk usage** | Ngăn retention làm đầy storage |

Cần xác định metric đo ở đâu: publish callback, recoverer, DLT audit consumer hay tracker ticket. Một record có thể được publish DLT nhiều lần hoặc bị re-drive, nên **số DLT messages không luôn bằng số logical incidents duy nhất**.

Không gắn eventId, orderId, UUID hoặc stack trace làm Prometheus metric labels dài hạn. Chúng phù hợp với structured log/audit có kiểm soát; metrics nên dùng tags ít biến động như topic, group, error category, outcome.

### Cảnh báo gợi ý

- DLT bắt đầu nhận record khác 0 trong một khoảng mà bình thường không có.
- Lượng DLT tăng đột biến sau deployment.
- Recoverer publish DLT thất bại liên tiếp.
- Consumer lag nguồn tăng cùng tỷ lệ retry.
- Record DLT lâu nhất chưa được xử lý vượt SLA.
- Re-drive liên tục quay lại DLT cho cùng eventId.
- DLT topic sắp vượt quota/dung lượng broker.

Alert không nên tự replay toàn bộ DLT. Replay không được kiểm soát có thể gây duplicate, tải lớn hoặc ghi sai dữ liệu khi bug chưa được sửa.

## 18. Kiểm thử DLT bằng Embedded Kafka

Bộ test triển khai cần xác nhận ít nhất:

1. Topic nguồn và DLT có partition tương thích.
2. Một record hợp lệ không đi vào DLT.
3. Một JSON sai cú pháp được DLT nhận, còn listener không áp dụng nghiệp vụ.
4. Một lỗi tạm thời được retry theo số lần kỳ vọng, rồi DLT nếu vẫn thất bại.
5. Khi DLT không publish được, handler không âm thầm coi record đã recover thành công.
6. Key/value và thông tin nguồn (topic, partition, offset, lỗi) còn đủ để điều tra.
7. Replay cùng eventId không lặp side effect.
8. Consumer DLT/audit không tạo vòng lặp vô hạn.

Ví dụ dùng **@EmbeddedKafka** với một partition để minh họa đường đi của record lỗi. Ở môi trường test, topic/bean KafkaAdmin cần dùng replication factor 1 thay vì cấu hình production replicas(3).

~~~java
import java.time.Duration;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.core.DefaultKafkaConsumerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.test.EmbeddedKafkaBroker;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.kafka.test.utils.KafkaTestUtils;

import static org.assertj.core.api.Assertions.assertThat;

@EmbeddedKafka(
        partitions = 1,
        topics = {"orders.events", "orders.events.DLT"},
        bootstrapServersProperty = "spring.kafka.bootstrap-servers")
@SpringBootTest(properties = {
        "spring.kafka.consumer.enable-auto-commit=false",
        "spring.kafka.consumer.auto-offset-reset=earliest",
        "spring.kafka.consumer.key-deserializer=org.apache.kafka.common.serialization.StringDeserializer",
        "spring.kafka.consumer.value-deserializer=org.apache.kafka.common.serialization.StringDeserializer",
        "spring.kafka.producer.key-serializer=org.apache.kafka.common.serialization.StringSerializer",
        "spring.kafka.producer.value-serializer=org.apache.kafka.common.serialization.StringSerializer",
        "spring.kafka.listener.ack-mode=record"
})
class OrderDltIntegrationTest {

    @Autowired
    EmbeddedKafkaBroker broker;

    @Autowired
    KafkaTemplate<Object, Object> kafkaTemplate;

    @Test
    void invalidJsonIsSentToDlt() throws Exception {
        String payload = "{\"eventId\":";

        Map<String, Object> props = KafkaTestUtils.consumerProps(
                "dlt-observer-" + UUID.randomUUID(),
                "false",
                broker);

        props.put(
                "auto.offset.reset",
                "earliest");

        try (Consumer<String, String> dltConsumer =
                     new DefaultKafkaConsumerFactory<>(
                             props,
                             new StringDeserializer(),
                             new StringDeserializer())
                             .createConsumer()) {

            broker.consumeFromAnEmbeddedTopic(
                    dltConsumer,
                    "orders.events.DLT");

            kafkaTemplate.send(
                    "orders.events",
                    "order-123",
                    payload).get(10, TimeUnit.SECONDS);

            var dltRecord = KafkaTestUtils.getSingleRecord(
                    dltConsumer,
                    "orders.events.DLT",
                    Duration.ofSeconds(30));

            assertThat(dltRecord.value()).isEqualTo(payload);
            assertThat(dltRecord.key()).isEqualTo("order-123");
            assertThat(dltRecord.topic())
                    .isEqualTo("orders.events.DLT");
        }
    }
}
~~~

Ví dụ là **integration test skeleton**:

- Ứng dụng test phải khởi tạo **OrderEventListener** và **DefaultErrorHandler** của phần trước.
- Cấu hình KafkaTemplate cần đúng serializer String.
- Bean tạo topic cho production phải được override/tắt trong test để tránh xung đột replication factor hoặc partitions.
- Nếu có **OrderDltAuditListener** đang hoạt động, nó dùng một consumer group khác; test observer vẫn có thể đọc DLT vì các group độc lập.
- Nên cô lập broker/topic hoặc fixture giữa các test để tránh **getSingleRecord** lấy cả record của test khác.
- Phải xác minh service nghiệp vụ **chưa được gọi**, chẳng hạn bằng mock/spy hoặc kiểm tra database không có side effect.
- Test thực tế cần dependencies **spring-kafka-test**, JUnit 5, Spring Boot Test và các thành phần listener/service của dự án.

**Không dùng Thread.sleep cố định rồi assert DLT có record.** Kafka xử lý bất đồng bộ; một test nên chờ bằng polling có timeout, Awaitility hoặc KafkaTestUtils. Bài test cũng cần chứng minh không có side effect nghiệp vụ của event lỗi, chứ không chỉ DLT có dữ liệu.

## 19. Test retry hết lượt rồi mới vào DLT

Cấu hình minh họa **FixedBackOff(1_500L, 2L)** kỳ vọng một record lỗi retryable sẽ được gọi lần đầu và hai lần retry.

Một kịch bản test:

~~~text
Test event: eventId=evt-test-1

Attempt 1 -> OrderService ném TransientDbException
Attempt 2 -> vẫn TransientDbException
Attempt 3 -> vẫn TransientDbException
             |
             v
       Recoverer publish DLT
~~~

Cách dựng test:

1. Dùng một eventId duy nhất cho test.
2. Thiết lập OrderService test double/fault injection luôn ném lỗi retryable cho event đó.
3. Gắn một counter theo eventId để biết số lần service được gọi.
4. Publish record qua KafkaTemplate.
5. Chờ DLT observer nhận record.
6. Assert counter bằng số attempt dự kiến theo cấu hình handler.
7. Assert DLT giữ key/value và metadata nguồn; không có dữ liệu nghiệp vụ đã commit.
8. Dọn state fixture theo phạm vi eventId, không TRUNCATE bảng chung khi listener khác đang chạy.

Không phụ thuộc timing chính xác “phải mất đúng 3 giây” trên CI. Backoff thực tế chịu ảnh hưởng scheduler, consumer poll và broker. Test nên dựa vào **số lần xử lý, trạng thái DLT và timeout hợp lý**.

### Test thành công sau một retry

Cấu hình fault injection ném lỗi **chỉ ở attempt đầu**, sau đó xử lý thành công. Khi test xác nhận listener đã xử lý xong và offset/side effect phù hợp, kết quả là:

- Có retry.
- Không có record DLT cho event đó.
- Tác động nghiệp vụ được commit đúng một lần.

Đừng dùng câu khẳng định “DLT không có record ngay lúc này” trước khi consumer xử lý xong; bài test có thể pass giả do record vẫn chưa được xử lý. Cần đợi một dấu hiệu hoàn tất đáng tin rồi mới kiểm tra absence trong một cửa sổ thích hợp.

## 20. Test lỗi publish sang DLT

Nếu topic DLT không tồn tại, ACL không cho phép WRITE, broker mất kết nối hoặc serializer không xử lý được value, chính recoverer có thể thất bại.

Một failure test cần đảm bảo:

- Không báo **recovered** khi DLT publish chưa được xác nhận theo policy.
- Không commit offset gốc một cách sai lệch chỉ vì đã vào recovery path.
- Có log/metric/alert cho lỗi DLT publishing.
- Có thể retry/recover sau khi hạ tầng được sửa mà không mất record.
- Một sự cố DLT rộng không tạo vòng retry vô hạn làm cạn tài nguyên.

Có thể mô phỏng bằng một **KafkaTemplate hoặc ProducerFactory test** luôn trả lỗi publish, hoặc chặn quyền WRITE trong Kafka container có bật ACL. Khi dùng mô phỏng, phải xác minh chính sách **setFailIfSendResultIsError(true)** và đường lỗi của container; nếu muốn chứng minh broker behavior, cần bài integration test với Kafka thật.

**Đừng cố tạo một tình huống mất record trong production để kiểm tra.** Dùng broker test hoặc fault injection có kiểm soát.

## 21. Kiểm thử replay từ DLT an toàn

Ví dụ event **evt-123** từng được service áp dụng thành công vào database nhưng do crash sau DB commit, trước Kafka offset commit, nó bị giao lại và có thể đi qua recovery path.

Khi replay:

~~~text
First processing:
  eventId=evt-123
  inserted marker -> business update -> DB commit

DLT replay:
  eventId=evt-123
  marker đã tồn tại
  không áp dụng business update lần hai
~~~

Với dịch vụ có marker idempotency trong cùng DB transaction như business update, test nên assert:

- **eventId/operationId gốc** được giữ.
- Bản replay được listener tiếp nhận và xử lý/recover theo policy.
- Bảng business chỉ có một tác động nghiệp vụ.
- Marker dedupe tồn tại đúng một bản.
- Báo cáo DLT/replay được cập nhật với outcome phù hợp.

DLT không bảo đảm tính đúng đắn của tác động tài chính khi service không idempotent. Vì vậy replay test cần **assert dữ liệu cuối**, không chỉ assert KafkaTemplate.send trả thành công.

## 22. Checklist trước khi triển khai DLT lên production

- [ ] Đã xác định **source topic**, DLT name, partition mapping và consumer group.
- [ ] Topic DLT được provision với partition/replication phù hợp.
- [ ] Producer có serializer hỗ trợ đúng kiểu payload được recoverer gửi.
- [ ] Consumer có **enable-auto-commit=false** và ack mode được chọn có chủ đích.
- [ ] Retry/backoff hữu hạn cho lỗi tạm thời; lỗi dữ liệu không hợp lệ được phân loại.
- [ ] DefaultErrorHandler và DeadLetterPublishingRecoverer được gắn đúng listener/container.
- [ ] Recoverer báo lỗi khi publish DLT không thành công.
- [ ] Hiểu offset commit sau recovery và các cửa sổ có thể gây duplicate DLT.
- [ ] Đã phân biệt lỗi trong listener với lỗi deserialization trước listener.
- [ ] Nếu dùng ErrorHandlingDeserializer, DLT producer hỗ trợ raw bytes khi cần.
- [ ] Nếu dùng @RetryableTopic, retry topics/DLT đã được provision và tránh recovery chồng nhau.
- [ ] Đã đánh giá ordering khi skip lỗi hoặc dùng retry topics.
- [ ] Có ACL, TLS, retention, hạn chế payload/header nhạy cảm trên DLT.
- [ ] Có metric/alert, đội chịu trách nhiệm triage và SLA giải quyết.
- [ ] Có runbook replay với eventId gốc, idempotency và giới hạn lần thử.
- [ ] Test invalid JSON, retryable error, lỗi publish DLT, replay và duplicate.
- [ ] Đã kiểm chứng business side effect chính xác, không chỉ Kafka records tồn tại.

## 23. Runbook xử lý một record DLT

Khi có cảnh báo về **orders.events.DLT**, một luồng vận hành an toàn:

~~~text
1. Nhận alert:
   DLT topic, consumer group, thời điểm, error category.
                 |
                 v
2. Mở audit tool được phân quyền:
   original topic/partition/offset, eventId, exception.
                 |
                 v
3. Xác định phạm vi ảnh hưởng:
   Một record hay toàn bộ batch? Có sai lệch business DB không?
                 |
                 v
4. Phân loại nguyên nhân:
   Data invalid / reference missing / DB outage / app bug.
                 |
           +-----+------+
           |            |
       Sửa được      Không thể sửa
           |            |
           v            v
     Kiểm tra điều   Quarantine +
     kiện re-drive   ticket nghiệp vụ
           |
           v
5. Replay giữ original business event ID,
   giới hạn số lần và tốc độ gửi.
           |
           v
6. Xác minh kết quả nghiệp vụ, idempotency,
   Kafka/DLT status và reconciliation.
           |
           v
7. Đóng ticket, giữ lịch sử audit.
~~~

Nếu một lỗi deployment khiến hầu hết messages vào DLT, nên cân nhắc **ngừng consumer hoặc rollback phiên bản**, xử lý nguyên nhân trước khi mở lại. DLT giúp giữ lại bằng chứng, nhưng không phải dung lượng vô hạn cho một bug đang tạo lỗi hàng loạt.

## 24. Kết luận

**Cấu hình DLT** trong Spring Kafka không kết thúc ở việc tạo thêm một topic và gắn **DefaultErrorHandler**. Một thiết kế đầy đủ phải xem record nào được retry, lỗi nào được chuyển DLT, producer dùng serializer gì, partition DLT có tồn tại không, việc publish thất bại được xử lý ra sao, offset được commit lúc nào và ai chịu trách nhiệm điều tra record tồn đọng.

Với consumer đọc String JSON, cấu hình **DefaultErrorHandler + DeadLetterPublishingRecoverer + DLT topic được provision trước** là một điểm khởi đầu rõ ràng. Với lỗi xảy ra ngay ở deserializer, cần **ErrorHandlingDeserializer** và serializer DLT phù hợp với raw bytes. Khi cần retry dài, **@RetryableTopic** là một chiến lược khác có thêm retry topics và trade-off về ordering.

Cuối cùng, DLT **giữ record lỗi để phục hồi**, còn **idempotency, audit, monitoring và replay có kiểm soát** quyết định hệ thống có thực sự tin cậy sau failure hay không.

