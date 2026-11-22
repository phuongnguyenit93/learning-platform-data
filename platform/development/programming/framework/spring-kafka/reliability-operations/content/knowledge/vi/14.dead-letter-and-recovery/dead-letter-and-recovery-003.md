# Destination resolver

Trong Spring Kafka, **destination resolver** là cơ chế quyết định **topic và partition đích** khi một record không thể xử lý thành công và cần được chuyển sang **dead-letter topic (DLT)** hoặc một topic recovery khác. Với **DeadLetterPublishingRecoverer**, ứng dụng có thể cung cấp một hàm nhận **ConsumerRecord** gốc và **Exception** liên quan, sau đó trả về **TopicPartition** đích. Hàm này cho phép định tuyến linh hoạt theo topic nguồn, loại lỗi hoặc các quy tắc nghiệp vụ đã được kiểm soát.

Đây là một điểm mở rộng quan trọng trong mô hình **Dead letter và recovery** của Spring Kafka. Resolver chỉ **chọn đích**. Nó không tự quyết định số lần retry, không tự publish record, không commit offset và không biến một record lỗi thành xử lý nghiệp vụ thành công. Những trách nhiệm đó được phối hợp bởi **DefaultErrorHandler**, recoverer, **KafkaTemplate**, listener container và chính sách acknowledgement/transaction đang dùng.

## 1. Từ listener failure đến destination resolver

Một luồng xử lý thông thường:

1. Consumer đọc record từ topic nguồn.
2. Listener xử lý nghiệp vụ.
3. Nếu listener ném exception, container chuyển lỗi cho error handler.
4. Error handler áp dụng retry và BackOff theo cấu hình.
5. Nếu lỗi không retryable hoặc đã hết retry, error handler gọi **DeadLetterPublishingRecoverer**.
6. Recoverer hỏi destination resolver record cần được gửi tới topic/partition nào.
7. Recoverer tạo producer record, đính kèm các header recovery thích hợp và dùng KafkaTemplate publish tới đích.
8. Sau khi recovery được xem là hoàn tất, container xử lý tiến độ offset theo AckMode và policy hiện hành.

~~~mermaid
flowchart TD
    A["Kafka source topic"] --> B["Consumer và @KafkaListener"]
    B --> C{"Xử lý thành công?"}
    C -->|Có| D["Ack/commit theo container"]
    C -->|Không| E["DefaultErrorHandler"]
    E --> F{"Còn retry và lỗi retryable?"}
    F -->|Có| G["BackOff rồi giao lại record"]
    G --> B
    F -->|Không| H["DeadLetterPublishingRecoverer"]
    H --> I["Destination resolver"]
    I --> J["Chọn TopicPartition đích"]
    J --> K["KafkaTemplate gửi record recovery"]
    K --> L{"Publish/recovery thành công?"}
    L -->|Có| M["Container xử lý offset theo policy"]
    L -->|Không| N["Recovery failure: tiếp tục xử lý lỗi"]
~~~

Điểm cần phân biệt: **destination resolver không xử lý dữ liệu lỗi**. Nó quyết định nơi đưa dữ liệu đến. Việc gửi thành công và xử lý record ở DLT là hai hoạt động khác nhau.

## 2. API cốt lõi của destination resolver

Một constructor thường dùng của **DeadLetterPublishingRecoverer** nhận KafkaTemplate và một **BiFunction**:

~~~java
DeadLetterPublishingRecoverer(
    KafkaTemplate<?, ?> template,
    BiFunction<ConsumerRecord<?, ?>, Exception, TopicPartition>
        destinationResolver
)
~~~

Ý tưởng của hàm:

~~~java
(record, exception) -> {
    String destinationTopic = ...;
    int destinationPartition = ...;

    return new TopicPartition(
        destinationTopic,
        destinationPartition
    );
}
~~~

Ba loại dữ liệu quan trọng:

| Thành phần | Vai trò |
|---|---|
| **ConsumerRecord<?, ?> record** | Cung cấp topic nguồn, partition, offset, key, value, headers và timestamp |
| **Exception exception** | Mô tả lỗi khiến record phải được recover; có thể là wrapper chứa nguyên nhân gốc |
| **TopicPartition** | Chỉ rõ tên topic đích và partition đích, hoặc yêu cầu để producer chọn partition |

Tên **TopicPartition** đôi khi làm người mới hiểu nhầm là đối tượng mô tả partition nguồn. Trong trường hợp này, object trả về phải mô tả **đích cần publish**, không phải vị trí mà consumer đang đọc.

Destination resolver chạy trong đường xử lý recovery, sau các lần thử do error handler quản lý. Hàm này nên thực thi nhanh, thuần quyết định định tuyến và không tạo side effect nghiệp vụ.

## 3. Hành vi mặc định của DeadLetterPublishingRecoverer

Khi không cung cấp destination resolver tùy chỉnh, DeadLetterPublishingRecoverer thông thường định tuyến record tới một topic có tên bằng **topic nguồn + ".DLT"**, cùng số partition với record nguồn.

Ví dụ:

| Record nguồn | Đích mặc định |
|---|---|
| orders.events, partition 0, offset 102 | orders.events.DLT, partition 0 |
| orders.events, partition 2, offset 533 | orders.events.DLT, partition 2 |
| payments.events, partition 1, offset 89 | payments.events.DLT, partition 1 |

Cấu hình tối giản:

~~~java
@Bean
DeadLetterPublishingRecoverer deadLetterRecoverer(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    return new DeadLetterPublishingRecoverer(kafkaTemplate);
}
~~~

Với mapping cùng partition như trên, topic DLT phải tồn tại và phải có đủ số partition để chứa index lớn nhất được gửi tới. Nếu topic nguồn có sáu partition nhưng DLT chỉ có ba, record từ partition 3, 4 hoặc 5 có thể không được gửi thành công đến partition tương ứng.

Khi đặt tên khác, chia DLT theo loại lỗi hoặc muốn Kafka producer tự chọn partition đích, hãy cung cấp resolver tùy chỉnh.

## 4. Ví dụ đầy đủ: cấu hình custom destination resolver

Giả sử hệ thống muốn tách lỗi dữ liệu không hợp lệ ra một topic DLT chuyên xử lý, còn các lỗi xử lý đã hết retry được đưa vào DLT chung.

~~~java
import java.util.function.BiFunction;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.TopicPartition;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;

@Configuration
public class DeadLetterRoutingConfiguration {

    @Bean
    DeadLetterPublishingRecoverer deadLetterRecoverer(
            KafkaTemplate<Object, Object> kafkaTemplate) {

        BiFunction<ConsumerRecord<?, ?>, Exception, TopicPartition>
                destinationResolver = (record, exception) -> {

            String topic;

            if (causedBy(
                    exception,
                    IllegalArgumentException.class)) {
                topic = "orders.events.validation.DLT";
            } else {
                topic = "orders.events.processing.DLT";
            }

            // Chỉ định partition cùng index với partition nguồn.
            return new TopicPartition(
                    topic,
                    record.partition()
            );
        };

        return new DeadLetterPublishingRecoverer(
                kafkaTemplate,
                destinationResolver
        );
    }

    private static boolean causedBy(
            Throwable failure,
            Class<? extends Throwable> type) {

        for (Throwable current = failure;
             current != null;
             current = current.getCause()) {

            if (type.isInstance(current)) {
                return true;
            }
        }
        return false;
    }
}
~~~

Ví dụ giả định listener đang xử lý topic orders.events; nếu factory được dùng cho nhiều topic, hard-code tên DLT như vậy có thể không phù hợp. Một resolver tái sử dụng nên dựa trên record.topic() hoặc một bảng mapping rõ ràng theo source topic.

Từ code trên:

- **IllegalArgumentException** trong cause chain sẽ được định tuyến tới topic validation DLT.
- Những lỗi khác sau khi hết retry được định tuyến tới processing DLT.
- Partition đích giữ số index như partition nguồn.
- Producer cần quyền WRITE vào cả hai topic.
- Hai DLT phải có đủ partition để tiếp nhận index từ topic nguồn.

Ví dụ dùng IllegalArgumentException để minh họa phân loại. Trong ứng dụng thật nên dùng exception nghiệp vụ có ý nghĩa rõ ràng như InvalidOrderPayloadException, không mặc định mọi IllegalArgumentException đều là dữ liệu lỗi vĩnh viễn.

## 5. Gắn recoverer vào DefaultErrorHandler

Destination resolver chỉ được sử dụng khi DeadLetterPublishingRecoverer được gọi. Với listener container không dùng Kafka transaction, có thể gắn recoverer vào **DefaultErrorHandler**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

@Configuration
public class KafkaListenerConfiguration {

    @Bean
    DefaultErrorHandler orderErrorHandler(
            DeadLetterPublishingRecoverer deadLetterRecoverer) {

        var handler = new DefaultErrorHandler(
                deadLetterRecoverer,
                new FixedBackOff(1_000L, 2L)
        );

        handler.addNotRetryableExceptions(
                InvalidOrderPayloadException.class
        );

        return handler;
    }

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
    ordersListenerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory,
            DefaultErrorHandler orderErrorHandler) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

        factory.setConsumerFactory(consumerFactory);
        factory.setCommonErrorHandler(orderErrorHandler);

        return factory;
    }
}
~~~

Listener sử dụng factory:

~~~java
@KafkaListener(
    id = "orderEventsListener",
    topics = "orders.events",
    groupId = "order-processor",
    containerFactory = "ordersListenerFactory"
)
public void handle(OrderEvent event) {
    orderProcessingService.process(event);
}
~~~

Trong ví dụ, FixedBackOff(1_000L, 2L) đặt khoảng nghỉ một giây và tối đa hai lần retry sau lần xử lý đầu, nếu lỗi được xem là retryable. Với lỗi InvalidOrderPayloadException được khai báo không retryable, error handler có thể tiến tới recovery sớm hơn.

**Destination resolver không quyết định lỗi nào retryable.** Việc định tuyến theo exception sau khi hết retry và việc phân loại exception trước retry là hai quyết định liên quan nhưng tách biệt. Cần phối hợp chính sách để tránh cho lỗi dữ liệu vĩnh viễn chạy qua nhiều retry không cần thiết.

Các class nghiệp vụ OrderEvent và InvalidOrderPayloadException là ví dụ; cần được định nghĩa trong ứng dụng.

## 6. Thiết kế quy tắc định tuyến

Resolver có thể dựa trên nhiều thông tin, nhưng quy tắc phải dự đoán được và dễ kiểm chứng.

| Tín hiệu | Quy tắc minh họa | Lưu ý |
|---|---|---|
| Topic nguồn | orders.events → orders.events.DLT | Dễ tái sử dụng cho nhiều source topic |
| Loại exception | Validation error → validation.DLT | Cần đọc cause chain, tránh phân loại theo message text |
| Header đã được xác thực | Route theo miền nghiệp vụ được cho phép | Không dùng header tùy ý làm tên topic |
| Tenant đã được ánh xạ | Tenant A → DLT A | Dùng allowlist, giới hạn số topic và partition |
| Consumer group | Mỗi consumer workflow có DLT riêng | Group ID phải được lấy đáng tin cậy |
| Partition nguồn | Giữ nguyên partition index ở DLT | DLT cần đủ partition |
| Chính sách vận hành | Lỗi bảo mật → security DLT | Không tạo topic tùy tiện khi gặp exception lạ |

Ưu tiên routing policy rõ ràng, hữu hạn và được version-control. Không nên tạo tên topic bằng cách nối trực tiếp exception message, tenant ID tùy ý hoặc giá trị payload chưa qua kiểm tra. Những thông tin đó có thể chứa ký tự không hợp lệ, gây topic explosion hoặc đưa dữ liệu nhạy cảm vào tên tài nguyên.

### Ví dụ mapping theo topic nguồn

~~~java
BiFunction<ConsumerRecord<?, ?>, Exception, TopicPartition> resolver =
        (record, exception) -> {

    String sourceTopic = record.topic();

    String targetTopic = switch (sourceTopic) {
        case "orders.events"   -> "orders.events.DLT";
        case "payments.events" -> "payments.events.DLT";
        default                -> "shared-recovery.DLT";
    };

    return new TopicPartition(
            targetTopic,
            record.partition()
    );
};
~~~

Với shared-recovery.DLT, topic này phải có đủ partition cho mọi nguồn nếu giữ nguyên partition index. Nếu không có yêu cầu giữ partition, có thể để producer chọn partition.

## 7. Partition đích: giữ nguyên hay để Kafka chọn?

Phần thứ hai của TopicPartition trả về quyết định cách đặt partition cho producer record ở đích.

### 7.1 Giữ nguyên index partition

~~~java
return new TopicPartition(
        record.topic() + ".DLT",
        record.partition()
);
~~~

Ưu điểm:

- Có thể định vị record lỗi theo partition index tương ứng với topic gốc.
- Dễ triển khai mapping mặc định.
- Có thể giúp phân tích sự cố theo source partition.

Điều kiện bắt buộc: topic đích cần có partition với index được chỉ định. Topic DLT không tự mở rộng partition chỉ vì resolver trả về một index lớn.

Giữ cùng partition index không có nghĩa record ở DLT có cùng offset với record nguồn. Offset DLT do Kafka gán khi record được append vào log đích.

### 7.2 Để producer tự chọn partition

Nếu resolver trả về **partition âm**, DeadLetterPublishingRecoverer có thể tạo producer record mà không gán partition đích tường minh, để Kafka producer chọn partition theo partitioner, key và cấu hình producer.

~~~java
return new TopicPartition(
        "shared-recovery.DLT",
        -1
);
~~~

Phương án này hữu ích khi nhiều topic nguồn có số partition khác nhau nhưng đều đẩy vào một shared DLT. Lúc đó không cần bảo đảm shared DLT có mọi index của các topic nguồn.

Tuy nhiên:

- Partition đích có thể khác partition nguồn.
- Không thể dựa vào partition đích để suy ra partition nguồn.
- Cần dùng DLT headers hoặc metadata nghiệp vụ để truy vết.
- Nếu key không ổn định hoặc producer partitioning thay đổi, record có thể vào partition khác.

Hãy xác nhận cách xử lý partition âm theo phiên bản Spring Kafka đang chạy và kiểm thử record được publish thành công. Không dùng giá trị âm như một partition Kafka hợp lệ; nó là tín hiệu để recoverer **không chỉ định** partition trên producer record.

### 7.3 So sánh nhanh

| Chính sách | Khi phù hợp | Đánh đổi |
|---|---|---|
| Giữ partition gốc | DLT per topic, số partition tương thích | Phải provision đủ partition |
| Producer chọn partition | DLT dùng chung, nhiều source topic | Không giữ mapping partition bằng index |
| Custom partition mapping | Phân luồng theo nghiệp vụ/tenant | Cần vận hành và kiểm thử phức tạp hơn |

## 8. Exception wrapper và cause chain

Lỗi được ném ra trong listener thường được Spring Kafka bọc trong exception khác, ví dụ ListenerExecutionFailedException. Nếu chỉ kiểm tra exception.getClass() ở lớp ngoài, resolver có thể định tuyến mọi lỗi vào nhánh fallback.

Nên kiểm tra cause chain hoặc dịch lỗi sang một exception nghiệp vụ có chủ đích tại service boundary.

Ví dụ hàm hỗ trợ:

~~~java
static boolean containsCause(
        Throwable failure,
        Class<? extends Throwable> expected) {

    java.util.Set<Throwable> visited =
            java.util.Collections.newSetFromMap(
                    new java.util.IdentityHashMap<>()
            );

    for (Throwable cursor = failure;
         cursor != null && visited.add(cursor);
         cursor = cursor.getCause()) {

        if (expected.isInstance(cursor)) {
            return true;
        }
    }

    return false;
}
~~~

Dùng bộ visited giúp tránh lặp vô hạn nếu một cause chain bất thường có chu trình. Phân loại qua cause chain vẫn cần cẩn trọng vì lỗi tổng quát như IllegalArgumentException có thể xuất hiện sâu trong lỗi serialization hoặc mapping và không nhất thiết có cùng ý nghĩa nghiệp vụ.

Không parse text của exception.getMessage() làm nguồn duy nhất để chọn DLT. Nội dung message có thể thay đổi theo version, locale, driver hoặc chứa dữ liệu nhạy cảm.

## 9. Ánh xạ theo tenant và vùng nghiệp vụ

Một số hệ thống đa tenant muốn các record recovery của từng nhóm khách hàng được xử lý bởi đội riêng hoặc có retention khác nhau. Có thể chọn DLT theo tenant nhưng phải có allowlist.

Ví dụ:

~~~java
private static final Map<String, String> TENANT_DLT_TOPICS =
        Map.of(
            "tenant-a", "orders.tenant-a.DLT",
            "tenant-b", "orders.tenant-b.DLT"
        );

static TopicPartition resolveByTenant(
        ConsumerRecord<?, ?> record) {

    var header = record.headers().lastHeader("tenant-id");

    String tenant = header == null
            ? ""
            : new String(
                    header.value(),
                    StandardCharsets.UTF_8
            );

    String topic = TENANT_DLT_TOPICS.getOrDefault(
            tenant,
            "orders.quarantine.DLT"
    );

    return new TopicPartition(topic, -1);
}
~~~

Ví dụ minh họa kỹ thuật đọc header, không phải cơ chế xác thực tenant. Trước khi định tuyến theo tenant, hệ thống phải bảo đảm header đó được producer đáng tin cậy tạo ra hoặc được xác thực ở ranh giới vào.

Không ghép trực tiếp giá trị từ header vào tên topic, chẳng hạn tạo hàng nghìn topic theo ID không được giới hạn. Đưa tenant lạ vào quarantine DLT và phát metric cảnh báo sẽ an toàn hơn so với tự tạo topic mới.

Nếu nhiều tenant chia sẻ DLT, lưu đủ metadata nguồn và kiểm soát quyền đọc để tránh lộ dữ liệu giữa tenant.

## 10. DLT headers và khả năng truy vết

DeadLetterPublishingRecoverer thường bổ sung metadata mô tả record gốc và lỗi dẫn tới recovery vào headers của record ở DLT. Những trường có thể bao gồm:

- Topic gốc.
- Partition gốc.
- Offset gốc.
- Timestamp gốc và kiểu timestamp.
- Consumer group gốc khi có thông tin.
- Exception class.
- Exception cause, message và thông tin stack trace phù hợp.

Tên constant cụ thể được Spring Kafka cung cấp qua **KafkaHeaders** và có thể thay đổi giữa phiên bản. Khi code đọc headers, hãy dùng constant/API của dependency thực tế thay vì hard-code những tên header suy đoán.

Ví dụ DLT record:

~~~text
DLT destination topic: orders.events.validation.DLT
DLT partition: 2
DLT offset: 9801

Original topic: orders.events
Original partition: 2
Original offset: 445
Exception: InvalidOrderPayloadException
Event ID: evt-2f84
~~~

DLT offset là offset mới ở topic đích. Nó không thay thế original offset. Để replay/điều tra, kết hợp metadata DLT và event ID nghiệp vụ.

Nếu exception message hoặc stack trace chứa PII/secret, cần kiểm soát retention, ACL và cách export log. Không cho phép ai có quyền đọc DLT cũng mặc nhiên nhận toàn bộ dữ liệu nhạy cảm ngoài phạm vi cần thiết.

## 11. Resolver có nên tạo topic hay gọi dịch vụ bên ngoài?

Không nên.

Resolver được gọi trong đường xử lý lỗi của consumer. Nếu nó phải gọi database, hệ thống cấu hình remote hoặc API đồng bộ, chính quá trình recovery có thể treo, timeout hoặc thất bại khi dependency đang gặp sự cố.

Các nguyên tắc thực tế:

- Routing map nên được chuẩn bị sẵn từ cấu hình đã kiểm soát.
- Quy tắc có thể đọc metadata record và cause chain ngay trong bộ nhớ.
- Không tạo topic trong callback.
- Không gọi HTTP API để xin tên DLT cho mỗi record.
- Không thay đổi database nghiệp vụ trong resolver.
- Không xóa, sửa payload hoặc đánh dấu record đã xử lý bên trong resolver.
- Không tạo side effect chỉ để đo metric; log/metric nên được ghi ở điểm phù hợp với recovery outcome.

Nếu cần chính sách định tuyến thường xuyên thay đổi, có thể nạp cấu hình từ nguồn tin cậy trước khi chạy, validate, rồi cập nhật snapshot bất biến theo quy trình vận hành. Không phụ thuộc một request runtime tới config service cho mỗi lần lỗi.

## 12. Retry policy và destination routing là hai tầng khác nhau

Một số lỗi không nên retry, một số cần retry trước khi DLT. Quyết định này thuộc error handler, không phải resolver.

~~~text
Listener exception
    |
    v
Error handler: retryable?
    |
    +-- Có và còn attempts --> retry/backoff
    |
    +-- Không hoặc exhausted
             |
             v
     DeadLetterPublishingRecoverer
             |
             v
     Destination resolver --> DLT topic/partition
~~~

Ví dụ:

| Exception | Retry policy | Destination sau recovery |
|---|---|---|
| InvalidOrderPayloadException | Không retry | validation DLT |
| DatabaseDeadlockException | Retry giới hạn | processing DLT nếu hết retry |
| DownstreamTimeoutException | Retry với backoff | dependency DLT nếu hết retry |
| AuthorizationException | Điều tra cấu hình | security/operations DLT theo chính sách |
| SerializationException | Có thể cần recovery đặc biệt | quarantine DLT với serializer phù hợp |

Không nên chuyển một lỗi network tạm thời thẳng tới DLT chỉ vì resolver nhìn thấy một exception liên quan. Resolver chỉ chạy khi error handler đã quyết định cần recovery. DLT routing phải tương thích với cách error handler phân loại lỗi.

## 13. DLT producer và serializer

DeadLetterPublishingRecoverer dùng KafkaTemplate để gửi record sang destination đã chọn. Producer cần serialization phù hợp với key/value đang được recover.

Điển hình, nếu listener nhận String key và JSON payload, recoverer có thể dùng KafkaTemplate tương thích với các serializer đó:

~~~yaml
spring:
  kafka:
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      acks: all
      properties:
        enable.idempotence: true
~~~

Đây là một ví dụ producer configuration; ứng dụng còn cần bootstrap servers, security và producer factory.

Trong trường hợp **deserialization failure**, listener có thể không nhận được object Java hợp lệ. Khi dùng ErrorHandlingDeserializer, recoverer có thể cần publish giá trị dạng byte array gốc. Khi đó JsonSerializer đơn thuần có thể không phù hợp.

Spring Kafka hỗ trợ cấu hình recoverer với nhiều KafkaTemplate hoặc mapping serializer theo kiểu dữ liệu trong một số phiên bản. Hãy chọn KafkaOperations/producer serializer phù hợp với cả object đã deserialize và raw bytes khi hệ thống cần DLT cho lỗi deserialize.

Nếu producer không serialize được record, destination resolver vẫn có thể chọn đúng topic nhưng publish vẫn thất bại. Vì thế cần theo dõi riêng **routing decision** và **recovery publish outcome**.

## 14. Security và quyền trên destination

Một resolver có thể định tuyến vào nhiều topic. Producer phải có quyền WRITE với **tất cả** những destination mà policy cho phép.

Ví dụ:

- orders.events.validation.DLT.
- orders.events.processing.DLT.
- orders.quarantine.DLT.

Các quyền cần xem xét:

| Thành phần | Quyền cần thiết |
|---|---|
| Consumer của topic nguồn | READ trên source topic và quyền consumer group |
| Producer gửi DLT | WRITE trên DLT topics |
| Consumer xử lý DLT | READ trên DLT và quyền consumer group |
| Admin/provisioning | CREATE/ALTER nếu được giao quản lý topic |
| Transactional producer, nếu có | Quyền transactional ID và cluster theo cấu hình |

Nếu thiếu ACL WRITE, Kafka có thể trả về TopicAuthorizationException. Lúc đó không nên sửa resolver để route tới một topic khác rộng quyền hơn chỉ để che lỗi. Cần cấp quyền tối thiểu trên destination hợp lệ theo quy trình quản trị.

Không đặt topic DLT dựa trên dữ liệu chưa kiểm chứng vì điều đó cũng có thể khiến ứng dụng vô tình gửi record nhạy cảm vào topic mà principal khác có quyền đọc.

## 15. Đảm bảo topic đích có đủ partition

Đây là lỗi vận hành phổ biến nhất khi tùy chỉnh destination resolver.

Giả sử topic nguồn có partition 0 tới 7, nhưng topic DLT chỉ có partition 0 tới 3. Resolver sau sẽ lỗi với record thuộc partition 4, 5, 6 hoặc 7:

~~~java
return new TopicPartition(
        "shared-recovery.DLT",
        record.partition()
);
~~~

Một trong hai hướng:

1. Tạo topic DLT với số partition tương thích và kiểm tra khi tăng partition nguồn.
2. Trả về partition âm để Kafka producer chọn partition đích nếu hệ thống chấp nhận không giữ mapping partition.

Không dùng phép modulo tùy ý để chuyển partition nếu chưa đánh giá key ordering, khả năng truy vết và việc phân phối dữ liệu. Nếu cần custom partition mapping, hãy ghi rõ policy và test từng nguồn partition.

Khi nguồn topic tăng số partition, phải đánh giá mọi DLT destination giữ index. Tăng partition nguồn không đồng nghĩa DLT tự có thêm partition.

## 16. Recovery thành công và offset commit

Một hiểu nhầm phổ biến là: destination resolver đã trả về TopicPartition thì record lỗi đã được xử lý xong. Thực tế có nhiều bước:

1. Resolver tính destination.
2. Recoverer tạo ProducerRecord và gửi.
3. Producer có thể thành công hoặc thất bại.
4. Error handler quyết định recovery thành công hay không.
5. Container xử lý offset theo acknowledgement/recovery configuration.

**Không commit offset sớm chỉ vì resolver chọn được topic.**

Với DefaultErrorHandler và container không dùng Kafka transaction, các tùy chọn như AckMode và việc handler báo đã recover ảnh hưởng cách container tiến offset. Với một số cấu hình manual acknowledgement, thuộc tính như **commitRecovered** và cách xử lý ack được áp dụng theo điều kiện riêng. Không suy ra mọi mode đều commit ngay khi recoverer return.

Nếu sử dụng Kafka transactions, cần xem AfterRollbackProcessor và cơ chế gửi offset vào transaction. Recovery với transaction có semantics khác với listener container thông thường.

### Kiểm soát publish failure

DeadLetterPublishingRecoverer có các tùy chọn trong những phiên bản Spring Kafka hiện đại để chờ/kết luận kết quả gửi, ví dụ **setFailIfSendResultIsError(true)**. Khi cần không đánh dấu recovery thành công nếu Kafka send thất bại, hãy kiểm tra và cấu hình cơ chế quan sát send result phù hợp.

Ví dụ API ở các phiên bản hỗ trợ:

~~~java
DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(
                kafkaTemplate,
                resolver
        );

recoverer.setFailIfSendResultIsError(true);
~~~

Cách chờ và timeout send result có thể được cấu hình thêm theo phiên bản. Hãy xem semantics thật của KafkaTemplate và recoverer: nếu gửi là bất đồng bộ mà ứng dụng xem như đã recover trước khi biết kết quả, có nguy cơ mất dấu record trong các failure windows.

## 17. Khi chính recoverer thất bại

Recovery failure có thể xảy ra dù listener exception đã được phân loại đúng. Ví dụ:

- Destination topic chưa tồn tại.
- Partition được chỉ định không hợp lệ.
- KafkaTemplate không có serializer tương thích.
- Producer không có ACL WRITE.
- Broker không phản hồi hoặc quota bị vượt.
- Hàm resolver ném exception do dữ liệu/header bất thường.
- Topic đã đổi tên nhưng application config chưa đồng bộ.
- DLT publish lỗi do producer transaction/fencing.

Khi recoverer lỗi, error handler có thể giữ record để xử lý lại theo recovery failure policy. Tùy cấu hình, retry state hoặc backoff có thể được reset và record được giao lại. Cần kiểm tra version và option như **resetStateOnRecoveryFailure** khi thiết kế runbook.

Không bắt exception của recoverer rồi nuốt trong một wrapper để container tưởng record đã phục hồi. Việc này có thể khiến offset tiến lên trong khi record chưa được lưu tại bất kỳ destination bền vững nào.

## 18. Ghi log và metric cho routing

Để vận hành một resolver tùy chỉnh, đội vận hành cần thấy **vì sao record được đưa tới một destination cụ thể**.

Ví dụ log có cấu trúc:

~~~text
event=dlt_routing
service=order-processor
listener_id=orderEventsListener
source_topic=orders.events
source_partition=2
source_offset=445
exception_class=InvalidOrderPayloadException
destination_topic=orders.events.validation.DLT
destination_partition=2
event_id=evt-2f84
~~~

Đây là ví dụ format, không phải log tự động của framework.

Các metric:

| Metric | Ý nghĩa |
|---|---|
| Recovery attempts | Số lần hệ thống thử publish record recovery |
| Recovery success/failure | Kết quả publisher/recoverer |
| DLT ingress rate | Tốc độ record tới từng DLT |
| DLT backlog/lag | Số record chưa được DLT consumer xử lý |
| DLT oldest record age | Thời gian record lỗi cũ nhất còn tồn |
| Router fallback count | Số record rơi vào nhánh fallback |
| Unknown topic/tenant count | Phát hiện nguồn không nằm trong policy |
| Serialization errors | Phát hiện không publish được record recovery |
| Partition routing errors | Đích thiếu partition hoặc mapping sai |

Metric tags nên có cardinality thấp như source topic, destination topic, nhóm exception và environment. Không dùng event ID, offset, customer ID hoặc exception message làm tag vì có thể tạo số series quá lớn.

Ghi event ID/offset trong log hoặc tracing nếu chính sách bảo mật cho phép. Không log đầy đủ payload, token, password hoặc stack trace chứa dữ liệu nhạy cảm ra hệ thống không được kiểm soát.

## 19. DLT consumer và quy trình phục hồi

Destination resolver quyết định nơi record lỗi đến. Nhưng hệ thống còn phải quyết định ai xử lý ở nơi đó.

Một recovery workflow thực tế gồm:

1. Record vào DLT topic với metadata nguồn và exception.
2. DLT consumer hoặc hệ thống vận hành ghi nhận record.
3. Đội phụ trách phân tích lỗi là data, configuration hay dependency.
4. Sửa nguyên nhân gốc.
5. Kiểm tra side effect đã xảy ra hay chưa.
6. Replay có kiểm soát với event ID ổn định.
7. Xác nhận listener nguồn xử lý thành công hoặc trạng thái đã được giải quyết.
8. Theo dõi backlog và tránh DLT loop.

Không nên cấu hình DLT consumer đọc record rồi tự động gửi ngay về topic nguồn vô hạn. Nếu lỗi gốc chưa được sửa, hệ thống có thể tạo vòng lặp: topic nguồn → DLT → topic nguồn → DLT, làm tăng tải và nhân bản sự kiện.

Nếu mỗi loại lỗi có DLT riêng, phải có owner, retention và hướng xử lý rõ cho từng DLT. Việc chia nhỏ quá nhiều DLT có thể làm vận hành phức tạp hơn mà không tăng khả năng phục hồi.

## 20. Destination resolver với @RetryableTopic: không phải cùng khái niệm

Spring Kafka cũng có cơ chế **non-blocking retry** dùng **@RetryableTopic**. Hạ tầng này quản lý topology gồm topic nguồn, retry topics và DLT thông qua các thành phần retry-topic configuration và destination resolution của chính nó.

Cần phân biệt:

| Cơ chế | Tác dụng |
|---|---|
| **DeadLetterPublishingRecoverer destination resolver** | Chọn TopicPartition khi một recoverer cần publish record lỗi |
| **@RetryableTopic retry destination logic** | Chọn stage/topic tiếp theo theo attempt, delay, exception classification và DLT policy |
| **DefaultErrorHandler** | Xử lý blocking retry, BackOff và gọi recoverer khi cần |
| **@DltHandler** | Xử lý record đã đến DLT trong retry-topic topology |

Không mặc định một custom BiFunction trên DeadLetterPublishingRecoverer của listener chính sẽ điều khiển toàn bộ topology do @RetryableTopic tạo ra. Hai đường cấu hình có thể khác nhau theo framework version và listener factory.

Nếu ứng dụng sử dụng @RetryableTopic, cần kiểm tra cơ chế tạo retry/DLT topics, suffix, attempts, backoff và custom destination configuration của retry-topic infrastructure. Không dùng API của standard recoverer để thay thế logic retry-stage mà framework đang quản lý.

## 21. Batch listener và exception metadata

Với batch listener, một lời gọi có thể xử lý nhiều ConsumerRecord. Khi lỗi xảy ra, error handler có thể xử lý batch theo cách khác với record listener.

Nếu batch listener cung cấp thông tin record lỗi qua **BatchListenerFailedException**, error handler có thể xác định record cần recover. Nếu lỗi không gắn rõ với record cụ thể, recovery có thể áp dụng rộng hơn tùy API và policy.

Destination resolver của DeadLetterPublishingRecoverer vẫn nhận một ConsumerRecord cụ thể khi recoverer xử lý record đó. Nhưng không nên suy luận từ đó rằng mọi lỗi batch tự động xác định đúng record thất bại.

Cần kiểm thử:

- Listener ném exception trước khi xử lý record nào.
- Listener xử lý thành công một phần batch rồi lỗi.
- Error handler biết index của record lỗi hay không.
- Record nào được gửi vào DLT.
- Offset nào được commit hoặc seek lại.
- Side effect của record đã xử lý có idempotent không.

Khi bài toán yêu cầu recovery chi tiết theo record, record listener thường đơn giản hơn về ownership của failure. Batch listener cần thiết kế offset và retry semantics riêng.

## 22. Kafka transaction và database transaction

Destination resolver không tạo tính nguyên tử giữa database và Kafka. Nếu listener cập nhật database rồi phát sự kiện khác, việc đưa record lỗi vào DLT không tự động rollback hoặc commit database.

Với transactional listener container, error path có thể đi qua **AfterRollbackProcessor** thay vì DefaultErrorHandler thông thường. Cần cấu hình recoverer ở đúng thành phần sau rollback và hiểu cách offset được gửi vào transaction.

Các nguyên tắc:

- Không nuốt exception trong listener khi cần rollback.
- Cho database transaction kết thúc/rollback trước khi xử lý lại record.
- Nếu recovery publish thành công nhưng source offset chưa commit, có thể xảy ra redelivery.
- Dùng event ID và inbox/idempotency để chống side effect trùng.
- Dùng outbox nếu cần phối hợp database update với event publish.
- Không tuyên bố exactly-once cho external API hoặc database chỉ vì dùng Kafka transactions.

Destination resolver vẫn chỉ chọn topic và partition. Semantics của transaction thuộc các thành phần khác.

## 23. Kiểm thử destination resolver

Có thể kiểm thử hàm routing độc lập với Kafka broker để xác nhận input record và exception tạo ra TopicPartition mong muốn. Sau đó cần integration test để kiểm tra KafkaTemplate, topic partition count, ACL và send result.

### Unit test mapping

Ví dụ helper:

~~~java
static TopicPartition resolve(
        ConsumerRecord<?, ?> record,
        Exception failure) {

    if (containsCause(
            failure,
            InvalidOrderPayloadException.class)) {
        return new TopicPartition(
                "orders.validation.DLT",
                record.partition()
        );
    }

    return new TopicPartition(
            "orders.processing.DLT",
            record.partition()
    );
}
~~~

Với test, tạo ConsumerRecord giả của orders.events partition 3 offset 27, truyền exception validation và xác minh trả về orders.validation.DLT partition 3. Với exception khác, xác minh processing DLT.

Một số tình huống cần bao phủ:

| Test case | Kết quả mong đợi |
|---|---|
| Lỗi validation trực tiếp | Route tới validation DLT |
| Lỗi validation bị wrapper | Vẫn route đúng theo cause chain |
| Lỗi transient hết retry | Route tới processing DLT |
| Topic nguồn chưa cấu hình | Route tới quarantine/fallback hữu hạn |
| Tenant header không hợp lệ | Không tạo tên topic tùy ý |
| Source partition lớn hơn DLT partitions | Publish failure được phát hiện hoặc dùng mapping khác |
| Partition = -1 ở đích | Producer tự chọn partition |
| DLT topic chưa tồn tại | Recovery failure có log/metric |
| Kafka producer thiếu ACL WRITE | TopicAuthorizationException được quan sát |
| Serialization failure | Không xem recovery đã thành công |
| Publish timeout | Không đánh dấu đã recover khi chưa có kết quả theo policy |

### Integration test với Kafka

Dùng EmbeddedKafka hoặc Testcontainers phù hợp với phiên bản ứng dụng. Quy trình minh họa:

1. Tạo topic nguồn và các DLT topics.
2. Cấu hình listener luôn ném InvalidOrderPayloadException cho một event test.
3. Cấu hình DefaultErrorHandler với recoverer custom resolver.
4. Gửi record vào partition đã biết.
5. Chờ tới khi error handler gọi recoverer.
6. Đọc đúng DLT mong đợi bằng consumer test độc lập.
7. Xác minh key/value, topic đích, partition và headers nguồn.
8. Xác nhận record không xuất hiện ở nhánh DLT khác.
9. Tạo thử một lỗi DLT publish và quan sát error handler recovery failure.
10. Xác minh offset/replay behavior theo AckMode đang dùng.

Không chỉ mock BiFunction rồi kết luận recovery thành công. Unit test chứng minh routing rule; integration test chứng minh end-to-end publication và phục hồi.

## 24. Runbook khi record đi sai DLT

Khi phát hiện record lỗi nằm ở DLT không đúng:

1. Xác định listener ID, consumer group, source topic/partition/offset và event ID.
2. Thu thập exception gốc và toàn bộ cause chain.
3. Kiểm tra DefaultErrorHandler đã hết retry hay coi exception là non-retryable.
4. Xác nhận bean DeadLetterPublishingRecoverer mà listener container thực sự dùng.
5. Đọc chính sách resolver hiện hành: source topic, exception, tenant mapping và fallback.
6. Xác nhận TopicPartition trả về và DLT topic thực tế.
7. Kiểm tra DLT partition count, topic existence và producer WRITE ACL.
8. Đối chiếu serialization, KafkaTemplate và publish result.
9. Kiểm tra headers chứa original topic/partition/offset.
10. Nếu dùng @RetryableTopic, xác định đây là retry-topic topology hay standard recoverer.
11. Sửa routing policy hoặc topology theo quy trình change management.
12. Xác định cách xử lý record đã nằm ở DLT cũ; không tự động xóa dữ liệu.
13. Replay có kiểm soát, theo dõi duplicate và side effect.
14. Cập nhật test để ngăn routing regression.

Nếu record hoàn toàn không xuất hiện ở DLT, ưu tiên điều tra recoverer publish failure và offset commit state thay vì kết luận resolver đã chọn sai đích.

## 25. Các lỗi triển khai thường gặp

**Nhầm destination resolver với retry classifier.** Resolver chọn đích khi cần recovery; error handler mới quyết định retry hay không.

**Không kiểm tra cause chain.** Spring Kafka có thể bọc exception gốc, khiến resolver route mọi lỗi vào fallback.

**Giữ partition gốc nhưng DLT ít partition hơn.** Kafka producer không thể publish tới partition index không tồn tại.

**Ghép tên topic trực tiếp từ header hoặc exception message.** Có thể tạo topic explosion, sai tên tài nguyên hoặc lộ thông tin nhạy cảm.

**Chỉ kiểm tra hàm resolver return đúng.** Publish vẫn có thể lỗi vì ACL, serializer, partition hoặc broker timeout.

**Coi DLT publishing là nghiệp vụ thành công.** Nó chỉ là recovery path; domain processing chưa chắc hoàn tất.

**Không xác minh send result.** Nếu publish fail nhưng handler vẫn xem recovered, record có nguy cơ mất dấu sau offset commit.

**Thiếu idempotency.** Publish DLT và commit offset nguồn có các failure windows; record có thể bị giao lại hoặc gửi DLT trùng.

**Dùng chung DLT nhưng không lưu original metadata.** Đội vận hành khó xác định nguồn và replay chính xác.

**Gọi network/database đồng bộ trong resolver.** Khi dependency lỗi, đường recovery cũng bị chặn.

**Quá nhiều destination không có owner.** Routing càng phân mảnh càng cần retention, ACL, dashboard và runbook riêng.

**Đổi routing policy không xử lý backlog cũ.** Record nằm ở DLT trước đó vẫn cần được tiêu thụ và phục hồi.

## 26. Checklist vận hành

**Chính sách định tuyến**

- [ ] Đã định nghĩa topic/partition đích cho từng nhóm lỗi cần tách.
- [ ] Resolver có fallback rõ ràng cho exception hoặc topic không biết trước.
- [ ] Cause chain được phân tích theo quy tắc ổn định.
- [ ] Header và tenant được kiểm chứng trước khi tham gia routing.
- [ ] Không tạo tên topic tùy ý từ dữ liệu không tin cậy.

**Kafka infrastructure**

- [ ] Mọi destination topic tồn tại và có retention phù hợp.
- [ ] Topic DLT có đủ partition nếu giữ original partition.
- [ ] Producer có WRITE trên tất cả DLT hợp lệ.
- [ ] KafkaTemplate/serializer xử lý được key/value cần recover.
- [ ] Có giám sát publish failure và partition routing failure.

**Recovery semantics**

- [ ] DefaultErrorHandler hoặc AfterRollbackProcessor dùng đúng recoverer.
- [ ] Retry policy tách biệt với routing policy.
- [ ] Offset/ack policy chỉ xem recovered khi recovery đáp ứng điều kiện đã thiết kế.
- [ ] Có idempotency và quy trình DLT replay.
- [ ] Recovery failure không bị nuốt rồi đánh dấu thành công.

**Quan sát và kiểm thử**

- [ ] Log có source và destination topic/partition, offset và event ID.
- [ ] Metric tags có cardinality thấp.
- [ ] Có unit test mapping theo exception/topic/tenant.
- [ ] Có integration test DLT publication và producer failure.
- [ ] Có runbook khi DLT backlog, routing sai hoặc producer thiếu ACL.

## 27. Nguyên tắc thiết kế

**Destination resolver** cho DeadLetterPublishingRecoverer là một hàm định tuyến từ **ConsumerRecord + Exception** sang **TopicPartition đích**. Sức mạnh của nó nằm ở khả năng đưa từng nhóm lỗi đến nơi recovery có owner và chính sách rõ ràng. Mặc định, có thể giữ DLT cùng partition với topic nguồn; với shared DLT có thể để producer chọn partition nếu cấu hình phù hợp.

Hãy giữ resolver đơn giản, quyết định hữu hạn và không có side effect; provision topic/ACL/serializer đầy đủ; xác nhận kết quả DLT publishing; và tách rõ retry classification, routing, offset commit cùng nghiệp vụ replay. Khi có log, metric, test và runbook cho cả đường thành công lẫn recovery failure, destination resolver trở thành một thành phần đáng tin cậy của vận hành Spring Kafka thay vì điểm dễ làm mất dấu record lỗi.
