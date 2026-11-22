# Phân loại lỗi producer và consumer

## 1. Vì sao phải phân loại lỗi theo nơi phát sinh?

Trong một luồng Spring Kafka, producer và consumer thực hiện hai công việc khác nhau. Producer chuyển dữ liệu thành Kafka record và gửi record đến broker. Consumer đọc record, chuyển đổi dữ liệu rồi gọi nghiệp vụ trong listener. Vì vậy, lỗi ở hai phía có nguyên nhân, khả năng retry và cách phục hồi khác nhau.

Ví dụ với luồng tạo đơn hàng:

- `order-service` gửi `OrderCreatedEvent` vào topic `orders`.
- Kafka broker lưu record và trả kết quả gửi cho producer.
- `order-projection` đọc record rồi cập nhật dữ liệu phục vụ truy vấn.
- `fraud-monitor` đọc cùng sự kiện trong consumer group riêng để đánh giá rủi ro.

Nếu `order-service` không gửi được record, listener của `order-projection` chưa có record để xử lý. `DefaultErrorHandler` của consumer không thể khắc phục lỗi gửi ở producer. Ngược lại, nếu record đã nằm trong Kafka nhưng `order-projection` không ghi được database, producer không nên gửi lại chỉ vì một consumer gặp lỗi.

Nguyên tắc đầu tiên là xác định lỗi xảy ra ở giai đoạn nào:

~~~mermaid
flowchart TD
    A["Ứng dụng producer"] --> B["Serialize key/value"]
    B --> C["Gửi record"]
    C --> D["Kafka broker"]
    D --> E["Consumer poll"]
    E --> F["Deserialize / convert"]
    F --> G["Listener và nghiệp vụ"]
    G --> H["Commit offset"]

    B --> P1["Producer serialization/config error"]
    C --> P2["Producer send / broker / network error"]
    E --> C1["Consumer fetch / group error"]
    F --> C2["Deserialization / conversion error"]
    G --> C3["Listener / business error"]
    H --> C4["Commit / offset error"]
~~~

Phân loại sai thường dẫn đến retry vô ích, gửi trùng sự kiện hoặc bỏ sót dữ liệu.

## 2. Bản đồ các nhóm lỗi

| Giai đoạn | Nhóm lỗi | Ví dụ | Nơi xử lý chính |
|---|---|---|---|
| Producer trước khi gửi | Dữ liệu hoặc cấu hình | Value sai kiểu, serializer lỗi, topic không hợp lệ | Publisher, serializer, cấu hình producer |
| Producer khi gửi | Lỗi tạm thời | Mất kết nối, leader đổi, broker tạm thời không sẵn sàng | Kafka producer retry và publisher quan sát kết quả |
| Producer khi gửi | Lỗi không thể retry | Không có quyền ghi, record vượt giới hạn, cấu hình sai | Sửa cấu hình/dữ liệu hoặc xử lý vận hành |
| Producer chờ kết quả | Timeout chưa rõ kết quả | Broker có thể đã ghi nhưng xác nhận không về kịp | Publisher, idempotency và đối soát |
| Consumer đọc dữ liệu | Lỗi hạ tầng/group | Broker mất kết nối, rebalance, commit thất bại | Kafka client và listener container |
| Consumer chuyển đổi | Lỗi deserialize/convert | Byte sai định dạng, JSON không hợp lệ, schema không tương thích | Deserializer, converter, error handler |
| Consumer chạy listener | Lỗi nghiệp vụ | Database tạm ngừng, gọi API lỗi, vi phạm quy tắc dữ liệu | Listener, retry, recoverer, DLT |
| Consumer xác nhận | Lỗi commit offset | Commit thất bại, consumer không còn quyền sở hữu partition | Listener container và consumer group |

Bảng phân loại theo giai đoạn phát sinh. Khi xử lý sự cố, cần đọc exception gốc và ngữ cảnh record thay vì chỉ dựa vào tên lớp exception ở lớp ngoài cùng.

## 3. Lỗi phía producer

Producer có thể thất bại trước khi record rời khỏi ứng dụng, trong quá trình gửi hoặc khi chờ broker xác nhận.

### Lỗi dữ liệu và serialization

Các lỗi thường gặp:

- Publisher truyền object không tương thích với serializer đã cấu hình.
- Serializer không thể chuyển object thành byte.
- Dữ liệu đầu vào thiếu trường bắt buộc hoặc có giá trị không hợp lệ.
- Kích thước record vượt giới hạn producer, broker hoặc topic.
- Tên topic, partition hoặc cấu hình bảo mật không hợp lệ.

Ví dụ producer được cấu hình `StringSerializer` nhưng publisher gửi một object `OrderCreatedEvent` trực tiếp. Lỗi kiểu dữ liệu này không tự hết sau vài giây. Retry cùng một object với cùng cấu hình sẽ tiếp tục thất bại.

Cách xử lý là kiểm tra kiểu generic của `KafkaTemplate<K, V>`, serializer, payload, kích thước record, topic và ACL. Ghi nhận lỗi cùng event ID để có thể sửa và phát lại có kiểm soát. Không dùng retry để che lỗi lập trình hoặc cấu hình cố định.

### Lỗi tạm thời khi gửi

Một số lỗi có thể tự phục hồi:

- Broker tạm thời mất kết nối.
- Partition leader đang được bầu lại.
- Request bị gián đoạn do mạng.
- Broker tạm thời thiếu tài nguyên hoặc chưa đáp ứng được request.
- Replica chưa đáp ứng điều kiện xác nhận theo cấu hình `acks`.

Kafka producer có cơ chế retry nội bộ. Những thuộc tính quan trọng:

| Thuộc tính | Vai trò |
|---|---|
| `retries` | Số lần producer thử gửi lại một số lỗi có thể retry |
| `retry.backoff.ms` | Khoảng chờ cơ bản giữa các lần retry |
| `delivery.timeout.ms` | Tổng thời gian tối đa producer cố gắng hoàn tất việc gửi, gồm chờ và retry |
| `request.timeout.ms` | Thời gian chờ phản hồi cho một request |
| `acks` | Mức xác nhận broker cần trả về cho request gửi |
| `enable.idempotence` | Hạn chế duplicate do retry nội bộ producer trong phạm vi bảo đảm của Kafka |

Ví dụ cấu hình Spring Boot:

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        enable.idempotence: true
        delivery.timeout.ms: 120000
        request.timeout.ms: 30000
        retry.backoff.ms: 1000
~~~

Các giá trị trên chỉ minh họa. Chọn timeout theo latency, SLA, cấu hình broker và thời gian publisher có thể chờ. Khi bật idempotence, Kafka producer áp dụng các ràng buộc tương thích giữa `acks`, `retries` và `max.in.flight.requests.per.connection`; kiểm tra cấu hình hiệu lực của phiên bản Kafka client đang dùng.

Thông thường nên để producer xử lý retry cho lỗi mạng/broker tạm thời. Không tạo một vòng retry ứng dụng bao quanh mọi lần `KafkaTemplate.send()` mà không hiểu producer đã retry những gì.

## 4. Timeout phía producer có thể có kết quả chưa rõ

Một tình huống khó xử lý là publisher gửi record nhưng không nhận được xác nhận trước timeout.

Có hai khả năng:

1. Broker chưa ghi record. Việc gửi lại có thể cần thiết.
2. Broker đã ghi record nhưng phản hồi bị mất hoặc đến sau khi producer hết thời gian chờ. Việc gửi lại ở tầng ứng dụng có thể tạo một record thứ hai.

Vì vậy, timeout không phải lúc nào cũng có nghĩa record chắc chắn chưa được ghi. Hãy coi đây là kết quả chưa rõ cho đến khi có cơ chế đối soát.

`enable.idempotence=true` bảo vệ retry nội bộ của một producer session theo cơ chế idempotent producer. Nó không tự khử trùng lặp mọi lần ứng dụng gọi `send()` lại sau timeout, restart hoặc tạo một producer request mới cho cùng sự kiện nghiệp vụ.

Để xử lý an toàn:

- Gán `eventId` ổn định cho sự kiện trước lần gửi đầu tiên.
- Khi retry cùng một sự kiện nghiệp vụ, giữ nguyên `eventId` này.
- Consumer dùng `eventId` để khử trùng lặp khi áp dụng side effect.
- Với sự kiện phát sinh từ transaction database, cân nhắc Transactional Outbox để lưu ý định phát event cùng transaction nghiệp vụ.
- Ghi log topic, key, event ID, exception và kết quả future; tránh log payload nhạy cảm.

## 5. Quan sát kết quả gửi bằng KafkaTemplate

Trong Spring Kafka 3.x, `KafkaTemplate.send()` trả về `CompletableFuture<SendResult<K, V>>`. Publisher cần quan sát cả lỗi xảy ra ngay trong lời gọi và lỗi hoàn tất bất đồng bộ.

~~~java
import java.util.concurrent.CompletableFuture;

import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Component;

@Component
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderCreatedEvent>> publish(
            OrderCreatedEvent event) {

        try {
            return kafkaTemplate.send(
                "orders",
                event.orderId(),
                event
            );
        } catch (RuntimeException ex) {
            // Lỗi đồng bộ: ví dụ cấu hình hoặc serialization.
            log.error(
                "Không thể khởi tạo lần gửi eventId={}",
                event.eventId(),
                ex
            );
            throw ex;
        }
    }
}
~~~

Quan sát kết quả bất đồng bộ:

~~~java
publisher.publish(event)
    .whenComplete((result, error) -> {
        if (error != null) {
            log.error(
                "Gửi event thất bại eventId={}",
                event.eventId(),
                error
            );
            return;
        }

        var metadata = result.getRecordMetadata();
        log.info(
            "Gửi event thành công eventId={} topic={} partition={} offset={}",
            event.eventId(),
            metadata.topic(),
            metadata.partition(),
            metadata.offset()
        );
    });
~~~

Khi future hoàn tất thành công, producer đã nhận xác nhận theo `acks` đã cấu hình. Điều này không có nghĩa mọi consumer đã xử lý record.

Không nuốt exception trong callback rồi coi lần gửi là thành công. Nếu publisher phải duy trì trạng thái gửi, hãy ghi kết quả thành công/thất bại vào cơ chế lưu trữ hoặc outbox phù hợp để có thể retry và đối soát sau khi tiến trình khởi động lại.

## 6. Lỗi phía consumer

Consumer có thể lỗi ở nhiều giai đoạn sau khi record đã tồn tại trong Kafka.

### Lỗi fetch, kết nối và consumer group

Ví dụ:

- Consumer tạm thời không kết nối được broker.
- Partition leader thay đổi.
- Consumer bị rebalance khi thành viên group tham gia/rời đi.
- Xử lý một poll quá lâu, vượt `max.poll.interval.ms`.
- Commit offset thất bại do consumer không còn quyền sở hữu partition hoặc group đang rebalance.

Đây chủ yếu là lỗi client, kết nối và điều phối group. Kafka consumer và listener container có cơ chế quản lý poll, heartbeat, assignment và commit. Không nên bắt mọi exception hạ tầng rồi đưa record vào DLT như thể payload bị lỗi.

Khi điều tra, kiểm tra consumer lag, partition assignment, rebalance, thời gian listener, `max.poll.interval.ms`, trạng thái broker và log consumer.

### Lỗi deserialization

Lỗi xảy ra khi Kafka client không thể chuyển byte thành kiểu key/value mà consumer yêu cầu. Ví dụ:

- Producer gửi JSON nhưng consumer dùng `IntegerDeserializer`.
- Byte bị hỏng hoặc payload không đúng định dạng.
- Consumer dùng sai schema hoặc cấu hình type mapping.
- Record tombstone có value `null` nhưng ứng dụng giả định luôn có payload.

Lỗi deserialize có thể xảy ra ngay trong `poll()`, trước khi listener được gọi. Vì vậy, nếu muốn Spring Kafka error handler xử lý loại lỗi này, thường cần bọc delegate bằng `ErrorHandlingDeserializer`.

Ví dụ consumer dùng `JsonDeserializer` làm delegate:

~~~yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.value.default.type: com.example.events.OrderCreatedEvent
        spring.json.trusted.packages: com.example.events
~~~

`ErrorHandlingDeserializer` giữ thông tin lỗi deserialize để Spring Kafka chuyển lỗi tới cơ chế xử lý phù hợp của container. Cần cấu hình delegate, type mapping và trusted packages theo đúng contract. Không mở trusted packages rộng cho dữ liệu từ nguồn không đáng tin chỉ để làm hết lỗi.

Nếu consumer dùng `StringDeserializer` cùng `StringJsonMessageConverter`, lỗi parse JSON xảy ra ở message conversion, sau khi Kafka client đã tạo được String. Hãy phân biệt lỗi deserialize ở client với lỗi chuyển JSON thành object ở listener adapter.

### Lỗi message conversion và validation

Một số record deserialize thành công nhưng vẫn không thể chuyển thành tham số listener:

- JSON hợp lệ về cú pháp nhưng không ánh xạ được vào kiểu Java.
- Thiếu header/type metadata cần thiết.
- Kiểu trường không tương thích với event class.
- Validation phát hiện dữ liệu thiếu hoặc sai quy tắc.

Lỗi conversion thường xảy ra trong đường gọi listener adapter. Lỗi validation có thể phát sinh từ listener hoặc service nghiệp vụ. Cần ghi nhận loại lỗi và event ID để xác định record có thể được sửa, cần chuyển DLT hay cần thay đổi contract.

### Lỗi nghiệp vụ trong listener

Ví dụ:

- Database tạm thời không kết nối được.
- API downstream trả về lỗi 503.
- Một dịch vụ phụ thuộc đang bị giới hạn tốc độ.
- Dữ liệu hợp lệ nhưng trạng thái nghiệp vụ chưa cho phép xử lý tại thời điểm hiện tại.
- Record không thể xử lý vì thiếu dữ liệu hoặc vi phạm quy tắc vĩnh viễn.

Không phải mọi lỗi listener đều có cùng chính sách retry. Database tạm ngừng có thể retry sau backoff; payload sai schema có thể không bao giờ thành công nếu không thay đổi dữ liệu hoặc code. Cần phân loại lỗi tạm thời và lỗi không thể phục hồi bằng retry.

## 7. Phân loại lỗi consumer theo khả năng phục hồi

| Loại lỗi | Ví dụ | Retry? | Hành động sau khi hết retry |
|---|---|---|---|
| Lỗi tạm thời của hạ tầng | Database timeout, HTTP 503 | Có, với backoff và giới hạn | DLT hoặc quy trình phục hồi/đợi dependency |
| Lỗi giới hạn tốc độ | HTTP 429 | Có, tôn trọng Retry-After nếu có | DLT hoặc retry topic có trì hoãn |
| Lỗi payload không hợp lệ | JSON sai, thiếu trường bắt buộc | Thường không retry mù | DLT để điều tra |
| Lỗi contract/schema | Version không hỗ trợ | Chỉ retry sau khi có code/schema phù hợp | DLT hoặc tạm dừng theo chính sách |
| Lỗi xác thực/phân quyền | Credentials sai, ACL thiếu | Không retry liên tục | Sửa secret/ACL rồi phục hồi |
| Lỗi lập trình | NullPointerException, bug mapping | Không retry vô hạn | DLT/tạm dừng, sửa code và replay |
| Lỗi commit/rebalance | Commit thất bại khi group đổi assignment | Để container/client quản lý; đánh giá giao lại | Theo dõi rebalance và offset |

Bảng chỉ là hướng dẫn. Một exception có thể đại diện cho nhiều nguyên nhân; ví dụ `DataAccessException` có thể là lỗi kết nối tạm thời hoặc vi phạm constraint vĩnh viễn. Nên phân loại dựa trên nguyên nhân gốc và loại thao tác, không chỉ dựa trên một lớp exception chung.

## 8. Retry và Dead Letter ở phía consumer

Với record listener, Spring Kafka có thể dùng `DefaultErrorHandler` để retry record bị lỗi theo backoff. Khi retry hết giới hạn, recoverer có thể chuyển record sang dead-letter topic (DLT).

Bean error handler phải được gắn vào container factory đang được listener sử dụng. Ví dụ factory:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.DefaultErrorHandler;

@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreatedEvent>
        orderKafkaListenerContainerFactory(
                ConsumerFactory<String, OrderCreatedEvent> consumerFactory,
                DefaultErrorHandler kafkaErrorHandler) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderCreatedEvent>();
    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(kafkaErrorHandler);
    return factory;
}
~~~

Listener cần chỉ định `containerFactory = "orderKafkaListenerContainerFactory"`, hoặc cấu hình error handler trên factory mặc định mà listener đang dùng. Hãy bảo đảm factory và DLT template dùng serializer phù hợp với kiểu key/value thực tế.

~~~java
import org.apache.kafka.common.TopicPartition;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.util.backoff.FixedBackOff;

@Configuration
public class KafkaConsumerErrorConfiguration {

    @Bean
    DefaultErrorHandler kafkaErrorHandler(
            KafkaTemplate<Object, Object> dltKafkaTemplate) {

        var recoverer = new DeadLetterPublishingRecoverer(
            dltKafkaTemplate,
            (record, exception) ->
                new TopicPartition(
                    record.topic() + ".DLT",
                    record.partition()
                )
        );

        var handler = new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(1000L, 2L)
        );

        // Các lỗi dữ liệu không có ích khi retry được đánh dấu non-retryable.
        handler.addNotRetryableExceptions(
            IllegalArgumentException.class
        );

        return handler;
    }
}
~~~

`FixedBackOff(1000L, 2L)` nghĩa là chờ một giây giữa các lần retry, tối đa hai lần retry bổ sung sau lần xử lý ban đầu. `IllegalArgumentException` trong ví dụ được coi là lỗi không retry; chỉ dùng phân loại này nếu ứng dụng bảo đảm exception đó thực sự biểu thị dữ liệu không thể xử lý.

Để recoverer chuyển record về cùng số partition, topic DLT phải có đủ partition tương ứng và được tạo/cấu hình trước. Nếu không thể bảo đảm mapping partition, hãy chọn partition đích theo chiến lược phù hợp thay vì giả định DLT luôn có sẵn partition tương ứng.

Producer dùng để publish DLT phải serialize được cả record lỗi. Đặc biệt, lỗi deserialize có thể khiến value gốc vẫn là byte array trong khi record bình thường là object Java. Khi một DLT template phải nhận nhiều kiểu value, cần cấu hình serializer tương thích, ví dụ serializer phân loại theo kiểu; không mặc định `KafkaTemplate<Object, Object>` tự giải quyết mọi kiểu dữ liệu.

Với lỗi deserialize, hãy xác minh DLT thực sự giữ được raw key/value và exception metadata. Nếu DLT publish thất bại, error handler không nên âm thầm xem record đã phục hồi. Cấu hình và kiểm thử hành vi commit/recovery theo phiên bản Spring Kafka đang dùng.

## 9. Vì sao producer retry và consumer retry không thay thế nhau?

| Tiêu chí | Producer retry | Consumer retry |
|---|---|---|
| Mục tiêu | Ghi record vào Kafka thành công theo chính sách producer | Xử lý record đã đọc thành công |
| Nơi thực hiện | Kafka producer client | Spring Kafka listener container/error handler hoặc retry topic |
| Lỗi điển hình | Network, leader unavailable, broker tạm thời lỗi | Database lỗi, API downstream lỗi, listener exception |
| Đơn vị retry | Một lần gửi record | Một lần xử lý record hoặc batch |
| Kết quả cuối | Send future thành công hoặc thất bại | Listener thành công, record được recover/DLT hoặc tiếp tục lỗi |
| Không giải quyết | Lỗi nghiệp vụ phía consumer | Record chưa được producer ghi vào Kafka |

Ví dụ producer gửi `OrderCreatedEvent` thành công, sau đó consumer không cập nhật được database. Producer không cần gửi lại event chỉ vì database của consumer đang lỗi. Consumer error handler phải retry việc xử lý record đó.

Ngược lại, nếu producer không thể gửi record do lỗi serialization, consumer không thể retry vì record chưa được ghi vào topic.

Nếu publisher nhận timeout với kết quả chưa rõ và quyết định gửi lại, có thể tạo duplicate. Consumer vẫn cần idempotency bằng `eventId` ngay cả khi producer bật idempotence.

## 10. Log và metadata cần có khi điều tra lỗi

Log lỗi Kafka cần đủ ngữ cảnh để tìm lại record và xác định component chịu trách nhiệm.

| Trường | Ý nghĩa |
|---|---|
| `event-id` | Định danh sự kiện nghiệp vụ |
| `topic` | Topic liên quan |
| `partition` | Partition của record |
| `offset` | Vị trí record |
| `key` | Key nếu không nhạy cảm |
| `consumer-group` | Group đang xử lý |
| `exception-class` | Loại exception |
| `root-cause` | Nguyên nhân gốc đã được rút gọn an toàn |
| `attempt` | Số lần retry hoặc lần xử lý |
| `correlation-id` / `traceparent` | Liên kết log và distributed trace |

Không ghi toàn bộ payload, token, dữ liệu cá nhân hoặc nội dung tài liệu nhị phân vào log. Với producer chưa có Kafka offset vì send thất bại, ghi event ID, topic đích, key, trạng thái future và exception. Không bịa offset khi broker chưa xác nhận.

Dùng metrics để theo dõi:

- Số lần send thành công/thất bại ở producer.
- Tỷ lệ timeout, retry và record bị từ chối.
- Consumer lag theo group và partition.
- Số listener exception theo loại.
- Số lần retry và số record chuyển DLT.
- Tốc độ phát sinh và xử lý DLT.
- Độ trễ từ lúc event được tạo đến lúc từng consumer hoàn tất.

## 11. Kiểm thử phân loại lỗi

Kiểm thử nên xác nhận lỗi được xử lý ở đúng phía và đúng chính sách, thay vì chỉ kiểm tra exception được ném ra.

| Kịch bản | Điều cần xác minh |
|---|---|
| Producer truyền sai kiểu cho serializer | Send thất bại, listener consumer không bị gọi |
| Broker tạm thời không sẵn sàng | Producer retry theo cấu hình và future phản ánh kết quả cuối |
| Producer timeout sau khi gửi | Ứng dụng nhận biết kết quả chưa rõ và không tự động tạo event ID mới |
| Consumer deserialize thất bại | Listener không nhận object sai; error handling giữ được thông tin lỗi |
| Listener gặp database timeout | Retry theo backoff hữu hạn |
| Listener gặp payload sai định dạng | Không retry vô hạn; record được recover theo chính sách |
| DLT publish thất bại | Recovery không bị ghi nhận thành công ngoài ý muốn |
| Consumer xử lý xong nhưng dừng trước commit | Record có thể được giao lại và side effect phải idempotent |

Có thể dùng Embedded Kafka hoặc Testcontainers để kiểm thử đường đi qua broker. Dùng topic và group ID riêng cho từng test, chờ bằng Awaitility hoặc polling có timeout thay vì `Thread.sleep()` cố định.

Với producer, kiểm tra `CompletableFuture` và metadata trả về. Với consumer, kiểm tra số lần listener được gọi, committed offset, DLT record và tác động database. Không kết luận producer thành công chỉ vì `KafkaTemplate.send()` đã trả về future; cần chờ future hoàn tất trong test.

## 12. Quy trình điều tra sự cố thực tế

Khi hệ thống báo lỗi Kafka, có thể đi theo trình tự:

1. **Xác định record đã được producer gửi chưa.** Kiểm tra send future, producer logs, topic và event ID.
2. **Nếu producer thất bại, phân biệt lỗi cố định và lỗi tạm thời.** Kiểm tra serializer, ACL, topic, kích thước record, broker/network và timeout.
3. **Nếu record đã có trong topic, kiểm tra consumer group.** Xem assignment, lag, poll, rebalance và committed offset.
4. **Xác định lỗi xảy ra trước hay trong listener.** Kiểm tra deserializer, converter, argument binding và stack trace.
5. **Phân loại lỗi listener.** Xác định lỗi dependency tạm thời, dữ liệu không hợp lệ hay lỗi code.
6. **Kiểm tra retry/recovery.** Xác minh backoff, số lần thử, DLT và việc publish DLT có thành công.
7. **Đối soát tác động nghiệp vụ.** Kiểm tra event ID, database và khả năng xử lý trùng trước khi replay.
8. **Theo dõi sau phục hồi.** Xác nhận lag giảm, DLT được xử lý và producer/consumer hoạt động bình thường.

Đừng xóa hoặc reset offset chỉ để làm hết cảnh báo lag khi chưa xác định record nào chưa được xử lý. Reset offset có thể bỏ qua dữ liệu hoặc làm xử lý lại một lượng lớn record.

## 13. Checklist phân loại lỗi producer và consumer

- [ ] Xác định lỗi xảy ra trước send, trong send, khi poll, khi deserialize, trong listener hay khi commit.
- [ ] Phân biệt lỗi cấu hình/dữ liệu cố định với lỗi hạ tầng tạm thời.
- [ ] Để Kafka producer xử lý retry nội bộ cho lỗi gửi có thể retry.
- [ ] Quan sát `CompletableFuture` của `KafkaTemplate.send()`.
- [ ] Xem timeout producer là kết quả có thể chưa rõ, không mặc định record chưa được ghi.
- [ ] Giữ `eventId` ổn định khi retry cùng một sự kiện.
- [ ] Dùng `ErrorHandlingDeserializer` khi cần đưa lỗi deserialize vào cơ chế xử lý Spring Kafka.
- [ ] Cấu hình `DefaultErrorHandler`, backoff và recoverer theo loại lỗi listener.
- [ ] Đảm bảo DLT có partition và serializer phù hợp với record lỗi.
- [ ] Không dùng producer retry để giải quyết lỗi nghiệp vụ consumer hoặc ngược lại.
- [ ] Thiết kế consumer idempotent để chịu được record được giao lại.
- [ ] Theo dõi event ID, topic, partition, offset, group, retry và DLT.

Phân loại đúng lỗi producer và consumer giúp chọn đúng nơi retry và phục hồi. Producer chịu trách nhiệm đưa record vào Kafka và báo kết quả gửi; consumer chịu trách nhiệm đọc, chuyển đổi, xử lý nghiệp vụ và xác nhận offset. Khi tách rõ hai trách nhiệm này, kết hợp timeout có nhận thức, retry hữu hạn, DLT và idempotency, luồng Spring Kafka sẽ dễ điều tra và phục hồi hơn.
