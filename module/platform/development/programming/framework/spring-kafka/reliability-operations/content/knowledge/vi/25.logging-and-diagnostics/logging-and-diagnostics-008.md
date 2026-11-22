# Log DLT destination

Khi một record không thể được xử lý sau số lần retry đã định, Spring Kafka có thể chuyển record đó sang **Dead Letter Topic (DLT)** thông qua `DeadLetterPublishingRecoverer`. Trong production, chỉ biết “đã gửi vào DLT” là chưa đủ để điều tra. Đội vận hành cần biết **record nguồn đến từ topic/partition/offset nào, recoverer đã chọn topic/partition đích nào, vì sao record bị chuyển, và việc publish có thực sự được broker xác nhận hay không**.

**Log DLT destination** là cách ghi nhận đích recovery một cách có cấu trúc, có thể đối chiếu với metadata được gắn vào record DLT. Trong Spring Kafka, đích được xác định bởi destination resolver của `DeadLetterPublishingRecoverer`; ứng dụng có thể log quyết định đó, cấu hình recoverer chờ kết quả gửi và ghi nhận success/failure theo đúng ý nghĩa.

Một nguyên tắc cần giữ rõ: **log rằng recoverer đã chọn destination không đồng nghĩa record đã được publish thành công**. Muốn xác nhận send, phải quan sát kết quả gửi Kafka hoặc cấu hình recoverer báo lỗi khi send thất bại. Bài này trình bày cách log cả hai giai đoạn, cách dùng DLT headers để đối chiếu, và cách tránh làm log/metrics trở thành nguồn rò rỉ dữ liệu hoặc cardinality explosion.

## 1. DLT destination được quyết định ở đâu?

Luồng recovery thông thường trong Spring Kafka:

```text
Kafka topic orders
       |
       v
@KafkaListener
       |
       +--> xử lý thành công --> commit theo container
       |
       +--> exception
                |
                v
          DefaultErrorHandler
                |
          retry/backoff policy
                |
          hết retry hoặc lỗi non-retryable
                |
                v
       DeadLetterPublishingRecoverer
                |
        destination resolver
                |
                v
       KafkaTemplate.send(DLT topic, partition, record)
```

`DeadLetterPublishingRecoverer` thực hiện vai trò `ConsumerRecordRecoverer`: nhận `ConsumerRecord` gốc cùng exception, xác định `TopicPartition` đích, tạo record để publish và gửi qua `KafkaTemplate`/`KafkaOperations` được cấu hình.

Với constructor mặc định dùng một template, quy ước destination phổ biến là **`<originalTopic>.DLT` và cùng partition index với record nguồn**. Ví dụ `orders` partition 2 được chuyển tới `orders.DLT` partition 2. Khi cần quy tắc khác, có thể truyền `BiFunction<ConsumerRecord<?, ?>, Exception, TopicPartition>` làm destination resolver.

Đích log phải được lấy từ **quyết định resolver**, không tự ghép chuỗi `record.topic() + ".DLT"` ở một nơi khác rồi giả định đó luôn là destination thật. Ứng dụng có thể định tuyến theo loại exception, tenant class, topic nguồn hoặc chính sách vận hành; resolver là nơi thể hiện quyết định đó.

## 2. Phân biệt source record và DLT record

Một record khi đang được xử lý trên topic nguồn có các tọa độ:

```text
Source record:
  topic     = orders
  partition = 2
  offset    = 18420
```

Sau khi recover, record mới được ghi vào DLT:

```text
Published DLT record:
  topic     = orders.DLT
  partition = 2
  offset    = 930

Original source metadata (headers):
  original topic     = orders
  original partition = 2
  original offset    = 18420
```

Offset `930` là offset mới trong partition của DLT; `18420` là offset của record gốc trên topic nguồn. Hai tọa độ không thể dùng thay thế cho nhau. Khi một consumer đọc DLT, `ConsumerRecord.topic()` trả về `orders.DLT`; metadata nguồn phải được lấy từ các header gốc mà recoverer đính kèm.

Log tốt cần ghi **cả hai phía**:

- Source: topic, partition, offset, timestamp và listener/group nếu ứng dụng biết chắc.
- Destination: topic và partition do resolver chọn.
- Recovery reason: exception class hoặc error category được chuẩn hóa.
- Outcome: destination selected, send acknowledged hoặc send failed.

Không cần ghi raw payload để biết record được chuyển đi đâu. Payload có thể chứa thông tin cá nhân, token, bí mật hoặc dữ liệu không đáng tin cậy; provenance và tọa độ Kafka thường đủ để tìm record trong môi trường được cấp quyền.

## 3. Dùng destination resolver để xác định và log đích

Constructor nhận `KafkaOperations` và một destination resolver cho phép ứng dụng quyết định topic/partition. Ví dụ sau log destination đã chọn:

```java
import java.util.function.BiFunction;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.TopicPartition;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;

public class DltRecovererConfiguration {

    private static final Logger log = LoggerFactory.getLogger(
            DltRecovererConfiguration.class);

    public static DeadLetterPublishingRecoverer create(
            KafkaTemplate<Object, Object> dltTemplate) {

        BiFunction<ConsumerRecord<?, ?>, Exception, TopicPartition> resolver =
                (record, exception) -> {
                    TopicPartition destination = new TopicPartition(
                            record.topic() + ".DLT",
                            record.partition());

                    log.warn(
                            "DLT destination selected: sourceTopic={}, "
                                    + "sourcePartition={}, sourceOffset={}, "
                                    + "destinationTopic={}, destinationPartition={}, "
                                    + "exceptionType={}",
                            record.topic(),
                            record.partition(),
                            record.offset(),
                            destination.topic(),
                            destination.partition(),
                            exception.getClass().getName());

                    return destination;
                };

        return new DeadLetterPublishingRecoverer(dltTemplate, resolver);
    }
}
```

Log ở resolver thể hiện **destination đã được chọn**, tức là quyết định định tuyến trước khi send. Nó không xác nhận broker đã nhận record. Nếu publish thất bại sau đó, log destination vẫn đúng về mặt routing nhưng không được diễn giải thành “DLT record đã tồn tại”.

Resolver nên là hàm thuần, xác định và nhanh: cùng một record/exception trong cùng điều kiện phải trả về cùng destination. Không gọi database hoặc HTTP service đồng bộ từ resolver chỉ để tra cứu tên topic; điều đó kéo dài recovery trên consumer thread và có thể làm poll chậm. Nếu routing phụ thuộc cấu hình động, nên đọc từ cấu hình/cache đã được kiểm soát.

## 4. Xác nhận publish thành công bằng `setFailIfSendResultIsError`

`KafkaTemplate.send()` thường trả về một future vì send diễn ra bất đồng bộ. Nếu ứng dụng chỉ log destination rồi tiếp tục, send có thể thất bại sau đó do topic không tồn tại, ACL, serialization, broker unavailable hoặc timeout.

`DeadLetterPublishingRecoverer` cung cấp `setFailIfSendResultIsError(true)` để recoverer chờ kết quả send và báo lỗi khi send thất bại, trong các phiên bản Spring Kafka hỗ trợ API này. Khi bật, ứng dụng có thể bọc recoverer để ghi log sau khi `accept()` trả về bình thường:

```java
DeadLetterPublishingRecoverer delegate =
        new DeadLetterPublishingRecoverer(dltTemplate, resolver);

delegate.setFailIfSendResultIsError(true);

ConsumerRecordRecoverer loggingRecoverer = (record, exception) -> {
    TopicPartition destination = resolver.apply(record, exception);

    log.warn(
            "Publishing failed record to DLT: sourceTopic={}, "
                    + "sourcePartition={}, sourceOffset={}, "
                    + "destinationTopic={}, destinationPartition={}, "
                    + "exceptionType={}",
            record.topic(), record.partition(), record.offset(),
            destination.topic(), destination.partition(),
            exception.getClass().getName());

    // Với failIfSendResultIsError=true, lỗi send được báo lại
    // thay vì xem recovery là hoàn tất.
    delegate.accept(record, exception);

    log.info(
            "DLT publish acknowledged: sourceTopic={}, sourcePartition={}, "
                    + "sourceOffset={}, destinationTopic={}, destinationPartition={}",
            record.topic(), record.partition(), record.offset(),
            destination.topic(), destination.partition());
};
```

`ConsumerRecordRecoverer` thuộc package `org.springframework.kafka.listener`; `resolver` cần được định nghĩa một lần và chia sẻ cho delegate cùng wrapper. Resolver trong ví dụ được gọi một lần để log và một lần nữa bên trong delegate, nên nó phải **không có side effect**. Nếu cần tránh tính lại, có thể triển khai một abstraction ứng dụng giữ kết quả routing theo lời gọi, nhưng không dùng cache global theo offset mà không có cleanup.

`setFailIfSendResultIsError(true)` có ý nghĩa quan trọng: nếu recoverer ném exception do send thất bại, error handler có thể coi recovery chưa hoàn tất và không tiến offset nguồn như một record đã được recover thành công. Hành vi commit/retry cuối cùng vẫn phụ thuộc `DefaultErrorHandler`, ack mode, transaction manager và phiên bản Spring Kafka; cần cấu hình và kiểm thử đúng luồng đang chạy.

Nếu không bật chờ send result, dòng log sau `delegate.accept()` chỉ xác nhận phương thức recoverer đã trả về, **không phải bằng chứng broker đã acknowledge**. Không viết log `DLT publish succeeded` trong trường hợp đó.

## 5. Gắn recoverer vào `DefaultErrorHandler`

Một cấu hình hoàn chỉnh ở mức container factory có thể dùng recoverer đã bọc log:

```java
@Bean
DefaultErrorHandler ordersErrorHandler(
        KafkaTemplate<Object, Object> dltTemplate) {

    BiFunction<ConsumerRecord<?, ?>, Exception, TopicPartition> resolver =
            (record, exception) -> new TopicPartition(
                    record.topic() + ".DLT",
                    record.partition());

    DeadLetterPublishingRecoverer delegate =
            new DeadLetterPublishingRecoverer(dltTemplate, resolver);
    delegate.setFailIfSendResultIsError(true);

    ConsumerRecordRecoverer loggingRecoverer = (record, exception) -> {
        TopicPartition destination = resolver.apply(record, exception);
        log.warn(
                "DLT recovery selected: source={}-{}@{}, destination={}-{}, cause={}",
                record.topic(), record.partition(), record.offset(),
                destination.topic(), destination.partition(),
                exception.getClass().getSimpleName());

        delegate.accept(record, exception);

        log.info(
                "DLT recovery send acknowledged: source={}-{}@{}, destination={}-{}",
                record.topic(), record.partition(), record.offset(),
                destination.topic(), destination.partition());
    };

    return new DefaultErrorHandler(
            loggingRecoverer,
            new FixedBackOff(1_000L, 2L));
}
```

Đoạn code dùng `log` là logger SLF4J do ứng dụng khai báo trong class cấu hình. Ví dụ minh họa hai lần retry sau lần xử lý đầu tiên; `FixedBackOff(1_000L, 2L)` không phải quy tắc bắt buộc cho mọi lỗi. Ứng dụng nên phân loại lỗi retryable/non-retryable theo nguyên nhân: payload sai vĩnh viễn có thể chuyển DLT ngay, còn lỗi dependency tạm thời cần backoff hữu hạn.

Gắn handler vào đúng listener container factory:

```java
@Bean("ordersKafkaListenerContainerFactory")
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
ordersKafkaListenerContainerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory,
        DefaultErrorHandler ordersErrorHandler) {

    ConcurrentKafkaListenerContainerFactory<String, OrderEvent> factory =
            new ConcurrentKafkaListenerContainerFactory<>();
    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(ordersErrorHandler);
    return factory;
}
```

Listener cần tham chiếu factory này bằng `containerFactory`. Nếu handler được cấu hình trong một factory không được listener sử dụng, log DLT destination sẽ không xuất hiện theo dự định.

## 6. Routing nhiều DLT theo loại lỗi

Một số hệ thống tách DLT theo nguyên nhân để đội phụ trách có thể điều tra đúng luồng: lỗi schema vào `orders-invalid-format.DLT`, lỗi business contract vào `orders-business-error.DLT`, lỗi không phân loại vào `orders.DLT`.

```java
BiFunction<ConsumerRecord<?, ?>, Exception, TopicPartition> resolver =
        (record, exception) -> {
            String suffix;

            if (exception instanceof InvalidPayloadException) {
                suffix = ".invalid-format.DLT";
            }
            else if (exception instanceof UnsupportedOrderStateException) {
                suffix = ".business-error.DLT";
            }
            else {
                suffix = ".DLT";
            }

            return new TopicPartition(
                    record.topic() + suffix,
                    record.partition());
        };
```

Các exception trong ví dụ là class ứng dụng tự định nghĩa. Trong thực tế, cần phân loại root cause thay vì chỉ so sánh exception ngoài cùng; một `ListenerExecutionFailedException` có thể bọc exception gốc. Cũng cần quyết định có giữ cùng partition index hay dùng partition resolver khác.

Khi có nhiều đích, log nên có `destination_reason` hoặc `error_category` từ một enum nhỏ như `INVALID_FORMAT`, `BUSINESS_REJECTED`, `UNCLASSIFIED`. Không ghi toàn bộ exception message làm label hoặc routing key; message có thể thay đổi theo record, chứa PII hoặc làm topic name không hợp lệ.

## 7. Partition đích phải tồn tại

Nếu resolver giữ nguyên partition index nguồn, DLT cần có đủ partition tương ứng. Ví dụ source topic có 12 partition nhưng `orders.DLT` chỉ có 6 partition; record từ `orders-9` không thể được gửi tới `orders.DLT-9` nếu partition 9 chưa tồn tại.

| Source topic | Source partition | DLT partitions | Kết quả khi giữ partition index |
|---|---:|---:|---|
| `orders` | 0 | 12 | Hợp lệ nếu DLT có partition 0 |
| `orders` | 5 | 12 | Hợp lệ nếu DLT có partition 5 |
| `orders` | 9 | 6 | Không hợp lệ: DLT không có partition 9 |

Có thể xử lý theo một trong các cách:

- Tạo DLT có số partition bằng hoặc lớn hơn source khi dùng cùng partition index.
- Dùng resolver ánh xạ về một partition hợp lệ, chấp nhận thay đổi ordering/parallelism.
- Dùng topic DLT riêng với topology được thiết kế theo nhu cầu triage thay vì giả định một-to-một.

Không log một partition đích tự suy diễn là hợp lệ nếu chưa kiểm tra topology. `DeadLetterPublishingRecoverer` có cơ chế kiểm tra partition theo phiên bản/cấu hình; nếu destination không hợp lệ, recovery có thể thất bại. Việc tạo topic và cấp ACL cần được quản lý trước khi consumer bắt đầu gửi DLT, không chờ tới lúc có poison record mới phát hiện thiếu topic.

## 8. Log destination và log send outcome là hai sự kiện khác nhau

Để tránh hiểu sai, nên phân biệt ba trạng thái trong log:

| Trạng thái | Ý nghĩa | Ví dụ log |
|---|---|---|
| `destination_selected` | Resolver đã chọn topic/partition | `DLT destination selected ...` |
| `send_acknowledged` | Recoverer chờ send và nhận kết quả thành công | `DLT publish acknowledged ...` |
| `send_failed` | Send lỗi/timeout/serialization/ACL; recovery chưa hoàn tất | `DLT publish failed ...` |

Ví dụ một chuỗi sự kiện có thể như sau:

```text
WARN  dlt.destination_selected source=orders-2@18420
      destination=orders.DLT-2 cause=InvalidPayloadException

INFO  dlt.send_acknowledged source=orders-2@18420
      destination=orders.DLT-2
```

Nếu send thất bại, chỉ có log `destination_selected` rồi sau đó có exception từ recoverer. Đừng tạo một dòng success ở `finally`; `finally` chạy cả khi delegate ném exception. Có thể dùng `catch` để ghi `send_failed` rồi ném lại exception cho error handler:

```java
try {
    delegate.accept(record, exception);
    log.info("DLT send acknowledged: source={}-{}@{}, destination={}-{}",
            record.topic(), record.partition(), record.offset(),
            destination.topic(), destination.partition());
}
catch (RuntimeException sendFailure) {
    log.error("DLT send failed: source={}-{}@{}, destination={}-{}, failureType={}",
            record.topic(), record.partition(), record.offset(),
            destination.topic(), destination.partition(),
            sendFailure.getClass().getName());
    throw sendFailure;
}
```

Đoạn wrapper chỉ có ý nghĩa xác nhận send khi delegate được cấu hình chờ kết quả và báo lỗi tương ứng. Nếu không, nó chỉ xác nhận recoverer đã nhận yêu cầu gửi. Log failure nên tránh lặp toàn bộ stack trace ở nhiều tầng nếu framework đã ghi exception; chọn một nơi chịu trách nhiệm log chi tiết và các nơi khác ghi structured context.

## 9. DLT headers dùng để đối chiếu log

`DeadLetterPublishingRecoverer` bổ sung metadata vào headers của record được publish, trong đó có các header gốc quan trọng như:

- `KafkaHeaders.DLT_ORIGINAL_TOPIC`
- `KafkaHeaders.DLT_ORIGINAL_PARTITION`
- `KafkaHeaders.DLT_ORIGINAL_OFFSET`

Các header này cho phép consumer DLT biết record được chuyển từ đâu. Spring Kafka còn hỗ trợ exception metadata như exception class/message/stack trace theo phiên bản và cấu hình, nhưng không nên mặc định mọi header đều được giữ nguyên qua nhiều lần recovery/replay.

Ví dụ consumer DLT có thể đọc provenance:

```java
@KafkaListener(topics = "orders.DLT", groupId = "orders-dlt-triage")
public void inspect(
        ConsumerRecord<String, byte[]> record,
        @Header(KafkaHeaders.DLT_ORIGINAL_TOPIC) String originalTopic,
        @Header(KafkaHeaders.DLT_ORIGINAL_PARTITION) Integer originalPartition,
        @Header(KafkaHeaders.DLT_ORIGINAL_OFFSET) Long originalOffset) {

    log.warn(
            "DLT record received: dltTopic={}, dltPartition={}, dltOffset={}, "
                    + "sourceTopic={}, sourcePartition={}, sourceOffset={}",
            record.topic(), record.partition(), record.offset(),
            originalTopic, originalPartition, originalOffset);
}
```

Đoạn ví dụ dùng value `byte[]` để minh họa consumer triage có thể đọc raw payload; kiểu key/value thực tế phụ thuộc serializer DLT. Các hằng header và kiểu chuyển đổi cần đối chiếu với phiên bản Spring Kafka. Nếu header không tồn tại hoặc được publish qua một hệ thống khác, method argument binding có thể thất bại; production code nên có cách xử lý thiếu metadata hoặc đọc header một cách phòng thủ.

Đừng chỉ dựa vào DLT record offset để tìm record nguồn. Hãy lưu original topic/partition/offset trong log và headers; chúng là khóa điều tra rõ ràng hơn.

## 10. Structured logging: trường nào nên có?

Một log DLT hữu ích có thể chứa:

| Trường | Ví dụ | Mục đích |
|---|---|---|
| `event` | `dlt.send_acknowledged` | Phân loại sự kiện log |
| `source_topic` | `orders` | Topic gốc |
| `source_partition` | `2` | Partition gốc |
| `source_offset` | `18420` | Offset gốc |
| `destination_topic` | `orders.DLT` | DLT đã chọn |
| `destination_partition` | `2` | Partition đích |
| `exception_type` | `InvalidPayloadException` | Lý do kỹ thuật ở mức class |
| `error_category` | `INVALID_FORMAT` | Nhóm lỗi ổn định để lọc |
| `consumer_group` | `order-service` | Nhóm consumer liên quan, nếu có từ context |
| `listener_id` | `ordersListener` | Listener xử lý record, nếu có từ context |
| `correlation_id` | giá trị đã chuẩn hóa/được phép | Liên kết log nghiệp vụ nếu cần |

Không phải mọi trường đều có sẵn trong `ConsumerRecord` hoặc exception. Listener ID/group có thể cần đưa vào context ở tầng container hoặc wrapper; đừng lấy một giá trị giả rồi ghi như dữ liệu chắc chắn.

Ví dụ log SLF4J dạng key-value có thể tích hợp với JSON encoder:

```java
log.warn(
        "DLT destination selected source_topic={} source_partition={} "
                + "source_offset={} destination_topic={} destination_partition={} "
                + "error_category={} exception_type={}",
        record.topic(),
        record.partition(),
        record.offset(),
        destination.topic(),
        destination.partition(),
        errorCategory,
        exception.getClass().getSimpleName());
```

Định dạng cuối cùng phụ thuộc logging backend/encoder. Nếu dùng MDC, nhớ dọn MDC ở đúng thread để không rò rỉ context sang record kế tiếp. `eventId` có thể hữu ích trong log nếu đã được phép ghi, nhưng không nên biến nó thành metric label.

## 11. Những dữ liệu không nên ghi vào log DLT

Một record lỗi có thể chứa dữ liệu không tin cậy hoặc nhạy cảm. Tránh log:

- Toàn bộ key/value hoặc payload JSON/Avro/Protobuf.
- Authorization header, access token, cookie, password hoặc secret.
- Exception message chưa được kiểm soát nếu nó có thể chứa một phần payload/PII.
- Toàn bộ stack trace cho từng lần retry nếu cùng một lỗi lặp lại hàng nghìn lần.
- Header tùy ý do producer gửi mà chưa giới hạn kích thước/encoding.

Log injection cũng là rủi ro: giá trị header chứa newline hoặc ký tự điều khiển có thể làm giả nhiều dòng log. Với field lấy từ record/header, dùng encoder có escaping, chuẩn hóa độ dài và giới hạn ký tự. Nếu cần xem payload, truy cập DLT bằng công cụ được phân quyền và audit, không đưa payload vào log tập trung mặc định.

Một quy tắc thực tế là **log tọa độ và phân loại lỗi; giữ payload trong Kafka DLT**. Nhờ vậy người vận hành có thể tìm record mà không sao chép dữ liệu nhạy cảm sang hệ thống log có retention hoặc quyền truy cập khác.

## 12. Log mỗi lần retry hay chỉ log lần recover cuối?

Không phải mọi exception đều lập tức đưa record vào DLT. `DefaultErrorHandler` có thể thực hiện nhiều lần retry trước khi gọi recoverer. Nếu mỗi lần retry đều log như “DLT publish”, dashboard sẽ đếm sai.

```text
Delivery #1 -> exception -> retry
Delivery #2 -> exception -> retry
Delivery #3 -> exception -> recoverer
                          |
                          v
                    destination selected
                          |
                          v
                    DLT send acknowledged
```

Nên phân biệt log ở các tầng:

- `record_processing_failed`: listener attempt thất bại.
- `record_retry_scheduled` hoặc log retry của error handler: sẽ thử lại.
- `dlt.destination_selected`: đã tới bước recovery và resolver chọn đích.
- `dlt.send_acknowledged`: DLT send đã được xác nhận theo cấu hình chờ kết quả.
- `dlt.send_failed`: send thất bại, recovery chưa hoàn tất.

Một record có thể có nhiều lần `record_processing_failed` nhưng chỉ một lần gửi DLT thành công. Khi retry recovery sau send failure, destination log có thể xuất hiện lại. Điều đó không nhất thiết là duplicate DLT; cần đối chiếu kết quả send, offset nguồn và event ID.

## 13. Destination log không thay thế metrics

Log chi tiết từng record là hữu ích cho điều tra, nhưng dashboard và alert cần metrics có cardinality thấp. Một hệ thống nên có counters và timers riêng:

| Metric | Dùng để trả lời |
|---|---|
| DLT recovery attempts | Bao nhiêu lần recoverer được gọi? |
| DLT sends acknowledged | Bao nhiêu record đã được broker xác nhận? |
| DLT send failures | Bao nhiêu lần publish DLT thất bại? |
| DLT rate theo source topic/error category | Topic/loại lỗi nào tạo nhiều DLT nhất? |
| DLT backlog / oldest record age | Bao nhiêu record còn chờ triage/replay? |
| Recovery latency | Mất bao lâu từ lúc record lỗi đến khi DLT send hoàn tất? |

Tags nên giới hạn ở `source_topic`, `error_category`, `service`, `environment` hoặc một tập destination topic hữu hạn. Không dùng `source_offset`, `event_id`, `order_id`, raw exception message hay payload làm metric tags.

Một counter `dlt.send.acknowledged` có thể tăng sau khi recoverer xác nhận send; `dlt.send.failed` tăng khi send thất bại. Không tăng counter success chỉ vì resolver đã trả `TopicPartition`.

## 14. Retry, DLT và Kafka transaction

Trong cấu hình producer non-transactional, DLT record được gửi như một Kafka record bình thường; `read_committed` consumer vẫn có thể đọc record non-transactional đó. Nếu recoverer dùng transactional `KafkaTemplate`, việc gửi DLT có thể thuộc Kafka transaction. Khi đó downstream `read_committed` chỉ nhìn thấy DLT record sau khi transaction commit.

Trong một số luồng recovery, Spring Kafka có thể phối hợp publish DLT và commit offset nguồn trong cùng Kafka transaction bằng cấu hình transactional recovery thích hợp. Đây là thiết kế khác với việc chỉ gọi `DeadLetterPublishingRecoverer` trên producer không transactional.

Log cần phân biệt:

- Resolver chọn destination.
- Producer gửi DLT.
- Kafka transaction commit/abort nếu transactional.
- Offset nguồn được commit theo container/error handler.

Một log `send_acknowledged` của producer trong transaction chưa nhất thiết có nghĩa DLT record đã **visible** cho `read_committed` consumer; transaction có thể vẫn đang mở hoặc cuối cùng abort. Với transactional recovery, chỉ log “recovery committed” sau khi có bằng chứng transaction hoàn tất, hoặc dựa vào instrumentation của transaction manager. Đừng suy ra transaction outcome từ một send future đơn lẻ.

## 15. Xử lý khi log cho biết destination đã chọn nhưng DLT không có record

Một số nguyên nhân thường gặp:

1. Log chỉ ghi `destination_selected`; producer send chưa hoàn tất hoặc thất bại sau đó.
2. `setFailIfSendResultIsError(true)` chưa được bật nên recoverer không chờ kết quả send theo cách ứng dụng mong muốn.
3. Topic đích không tồn tại hoặc broker không cho phép auto-create.
4. ACL thiếu quyền ghi topic/partition đích.
5. DLT serializer không hỗ trợ runtime type thực tế của key/value, đặc biệt raw `byte[]` từ deserialization failure.
6. Partition index trong resolver vượt số partition của DLT.
7. Transactional send được thực hiện nhưng transaction abort hoặc chưa commit.
8. Consumer triage đọc DLT bằng group/offset khác hoặc `read_committed` chưa thấy record transactional.
9. Record đã được ghi nhưng retention, compaction hoặc thao tác quản trị khiến nó không còn ở vị trí mong đợi.

Quy trình điều tra nên đối chiếu source coordinates, destination coordinates, producer error/ack, transaction outcome, committed offset nguồn và DLT consumer offsets. Không chỉ tìm theo `eventId` trong log nếu log đã không ghi event ID hoặc giá trị đó không duy nhất.

## 16. Log DLT publish failure mà vẫn giữ lỗi cho error handler

Khi send thất bại, wrapper nên ghi context rồi **ném lại exception** để error handler biết recovery chưa thành công:

```java
ConsumerRecordRecoverer loggingRecoverer = (record, exception) -> {
    TopicPartition destination = resolver.apply(record, exception);

    try {
        delegate.accept(record, exception);
        log.info("DLT send acknowledged source={}-{}@{} destination={}-{}",
                record.topic(), record.partition(), record.offset(),
                destination.topic(), destination.partition());
    }
    catch (RuntimeException failure) {
        log.error("DLT send failed source={}-{}@{} destination={}-{} type={}",
                record.topic(), record.partition(), record.offset(),
                destination.topic(), destination.partition(),
                failure.getClass().getName());
        throw failure;
    }
};
```

Ví dụ giả định `delegate` đã được cấu hình `setFailIfSendResultIsError(true)`. Nếu không chờ kết quả, đoạn `try` chỉ bắt được lỗi xảy ra đồng bộ khi gọi recoverer, không chắc bắt được lỗi send bất đồng bộ. Cũng không nên catch `Throwable` rồi nuốt tất cả lỗi JVM; chỉ bắt loại exception phù hợp với contract của phiên bản.

Khi recoverer ném lỗi, record nguồn cần tiếp tục theo chính sách error handler/transaction của container. Kiểm thử cụ thể để xác nhận offset không được commit như thể recovery thành công. Không đặt `acknowledge()` trong `finally` để tránh consumer bị mắc kẹt.

## 17. Destination routing theo môi trường và ownership

Tên DLT có thể khác theo môi trường, domain hoặc chính sách bảo mật. Thay vì hardcode nhiều hậu tố rải rác, định nghĩa routing ở một nơi:

```java
public interface DltDestinationPolicy {
    TopicPartition destinationFor(
            ConsumerRecord<?, ?> record,
            Exception exception);
}
```

Implementation có thể đọc một cấu hình đã validate:

```java
@Component
public class OrdersDltDestinationPolicy implements DltDestinationPolicy {

    @Override
    public TopicPartition destinationFor(
            ConsumerRecord<?, ?> record,
            Exception exception) {

        String topic = record.topic() + ".DLT";
        return new TopicPartition(topic, record.partition());
    }
}
```

Resolver chuyển kết quả thành log và destination:

```java
BiFunction<ConsumerRecord<?, ?>, Exception, TopicPartition> resolver =
        policy::destinationFor;
```

Trong thực tế, policy cần được kiểm tra trước khi chạy: topic phải nằm trong allowlist, partition hợp lệ, tên không vượt quy tắc broker và mỗi DLT có owner/retention/ACL. Không cho phép exception message hoặc header tùy ý quyết định tên topic trực tiếp, vì điều đó có thể tạo destination không kiểm soát hoặc mở đường ghi dữ liệu sai nơi.

Nếu dùng DLT chung nhiều service, log cần có source topic và owner để tránh đội vận hành xử lý nhầm record. Một DLT dùng chung cũng phải có schema/serializer strategy rõ ràng cho nhiều loại payload.

## 18. Log khi đọc DLT và khi replay

Khi một record đã ở DLT, consumer triage nên log cả tọa độ hiện tại và tọa độ nguồn:

```text
event=dlt.record_inspected
dlt_topic=orders.DLT
dlt_partition=2
dlt_offset=930
source_topic=orders
source_partition=2
source_offset=18420
error_category=INVALID_FORMAT
```

Khi replay, ghi thêm `replay_id`, `replay_attempt` và destination topic mới theo quy trình được phê duyệt. Giữ original metadata để có thể truy vết chuỗi:

```text
orders-2@18420
       |
       v
orders.DLT-2@930
       |
       v
orders-2@19001  (record mới do replay publish)
```

Offset `19001` là vị trí mới; replay không thể ghi lại vào offset cũ `18420`. Nếu consumer xử lý lại event, cần idempotency hoặc state versioning. DLT destination log không được dùng thay thế business audit và không nên xóa provenance gốc khi replay.

Không log `traceId` hoặc `replayId` như metric tag. Chúng phù hợp trong structured logs/traces có retention và quyền truy cập phù hợp; stable business event ID là chìa khóa deduplication, trace ID chỉ hỗ trợ telemetry.

## 19. Các lỗi logging và cấu hình thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Log báo DLT destination nhưng topic không có record | Chỉ log resolver, send chưa ack hoặc send thất bại | Bật fail-on-send-error và log outcome riêng |
| DLT record có nhưng source coordinates không rõ | Header provenance bị xóa hoặc consumer triage không đọc header | Kiểm tra recoverer header policy và `KafkaHeaders.DLT_ORIGINAL_*` |
| Log ghi sai destination | Log tự ghép `.DLT` trong khi resolver định tuyến khác | Log từ chính resolver được cấu hình |
| Cùng record có nhiều log destination | Retry/recovery được gọi nhiều lần hoặc resolver được gọi ở wrapper và delegate | Phân biệt attempt và outcome; resolver thuần, dùng event name rõ |
| Log thành công dù send future thất bại | Không chờ/kiểm tra send result | Dùng `setFailIfSendResultIsError(true)` ở version hỗ trợ |
| Recovery failure nhưng offset vẫn tiến | Cấu hình ack/handler/transaction không đúng hoặc exception bị nuốt | Ném lại recovery exception và kiểm thử committed offset |
| DLT partition không tồn tại | DLT ít partition hơn source nhưng resolver giữ index | Tạo đủ partition hoặc đổi resolver |
| Log có PII/payload | Log toàn record hoặc exception message | Chỉ log provenance và error category; redact dữ liệu |
| Dashboard có hàng triệu series | Dùng offset/event ID/exception message làm metric tags | Chuyển chi tiết sang logs/traces; giữ metrics tags cardinality thấp |
| Consumer DLT không thấy transactional record | DLT transaction chưa commit hoặc consumer isolation khác | Kiểm tra transaction outcome và `read_committed` visibility |

## 20. Kiểm thử log destination và publish outcome

Kiểm thử nên xác minh **routing**, **record thực tế** và **log outcome** thay vì chỉ kiểm tra một chuỗi log tồn tại.

Các trường hợp quan trọng:

1. **Default destination:** record từ `orders-2` được định tuyến tới `orders.DLT-2` theo policy đã chọn.
2. **Custom destination:** exception category khác nhau tạo topic đích đúng allowlist.
3. **Resolver log:** source topic/partition/offset và destination topic/partition được ghi đúng.
4. **Send success:** với fail-on-send-error bật, recoverer trả về bình thường sau kết quả send thành công; log outcome được ghi là acknowledged.
5. **Topic không tồn tại:** send thất bại, log failure có tọa độ đích và recovery exception được ném lại.
6. **Partition không hợp lệ:** xác nhận lỗi destination được phát hiện và offset nguồn không bị coi là recover thành công.
7. **Serializer mismatch:** kiểm tra raw `byte[]` và object thường nếu DLT nhận cả hai loại.
8. **Header provenance:** DLT record giữ original topic/partition/offset và consumer triage đọc được.
9. **Retry:** log retry attempt không bị nhầm với DLT send success; chỉ recoverer tạo log destination cuối.
10. **Transactional recovery:** phân biệt producer send result với transaction commit/abort và visibility của `read_committed` consumer.
11. **PII/log injection:** payload/header bất thường không xuất hiện thô trong log.
12. **Metric cardinality:** event ID, offset và raw exception không được tạo thành tags.

Trong integration test, dùng Kafka broker thử nghiệm hoặc Testcontainers để xác minh record đích thật sự tồn tại. Nếu chỉ mock `KafkaTemplate`, test có thể chứng minh resolver được gọi nhưng không chứng minh serializer, broker, ACL, partition hay send acknowledgment hoạt động.

## 21. Runbook khi cần tìm record đã được chuyển DLT

Khi đội vận hành cần tìm một record cụ thể hoặc xác nhận một lần recovery, thực hiện theo trình tự:

1. **Tìm log theo source coordinates:** source topic, partition, offset; bổ sung event ID/correlation ID nếu có và được phép ghi.
2. **Xác định trạng thái log:** `destination_selected`, `send_acknowledged` hay `send_failed`.
3. **Lấy destination:** topic và partition từ log resolver; không tự suy luận theo hậu tố nếu routing có custom policy.
4. **Kiểm tra producer/send:** lỗi serializer, ACL, topic/partition, timeout và kết quả transaction nếu có.
5. **Đọc DLT bằng quyền phù hợp:** xác nhận record thực tế, DLT offset và original metadata headers.
6. **Đối chiếu source offset:** xác nhận recovery đã hoàn tất và consumer group đã tiến offset theo policy.
7. **Nếu cần replay:** ghi replay ID, giữ provenance, giới hạn record, rate và idempotency; không replay toàn bộ DLT chỉ vì một record không tìm thấy trong log.
8. **Nếu send thất bại:** khôi phục topic/ACL/serializer/broker rồi để error handler/recovery retry theo chính sách.
9. **Đối soát:** so số recovery attempts, send acknowledgments, DLT records và records đã được triage.
10. **Lưu bằng chứng:** log IDs, source/destination coordinates, error category và người xử lý theo audit policy.

Không reset offset nguồn để “đưa record vào DLT” nếu chưa biết recovery đã publish hay chưa. Reset lùi có thể khiến record được xử lý và chuyển DLT lặp lại; reset tiến có thể bỏ qua record mà chưa có bản sao bền vững trong DLT.

## 22. Nguyên tắc production

1. Lấy DLT destination từ **destination resolver thực tế** của `DeadLetterPublishingRecoverer`, không log một tên topic tự suy diễn ở nơi khác.
2. Phân biệt `destination_selected` với `send_acknowledged` và `send_failed`.
3. Bật `setFailIfSendResultIsError(true)` khi cần recoverer chờ send result và báo lỗi; xác nhận API/semantics theo Spring Kafka version.
4. Nếu send thất bại, ghi log có context rồi ném lại exception để recovery không bị coi là thành công.
5. Ghi source topic/partition/offset cùng destination topic/partition; DLT offset là offset mới trên topic khác.
6. Dùng `KafkaHeaders.DLT_ORIGINAL_TOPIC`, `DLT_ORIGINAL_PARTITION`, `DLT_ORIGINAL_OFFSET` để đối chiếu provenance.
7. Bảo đảm topic và partition đích tồn tại, serializer hỗ trợ runtime key/value và ACL cho phép publish.
8. Log error class/category và tọa độ; tránh payload, token, PII, exception message chưa kiểm soát và header tùy ý.
9. Metrics chỉ dùng tags cardinality thấp; log chi tiết theo record không được biến thành metric series theo offset/event ID.
10. Phân biệt retry attempt, DLT publish, Kafka transaction commit và consumer offset commit.
11. Khi replay, giữ provenance, stable business event ID và idempotency; không dùng trace ID làm khóa deduplication.
12. Kiểm thử cả routing, send failure, transactional visibility, offset recovery và log sanitization trước rollout.

**Kết luận:** log DLT destination phải cho biết record nguồn được định tuyến tới đâu và liệu việc publish đã được xác nhận hay chưa. `DeadLetterPublishingRecoverer` cung cấp điểm mở rộng tự nhiên qua destination resolver; kết hợp resolver log với send-result handling, DLT provenance headers và structured logging sẽ tạo dấu vết đủ để điều tra. Khi log được tách khỏi metrics, payload nhạy cảm được giữ ngoài log và recovery failure không bị nuốt, đội vận hành có thể tìm đúng record, xác minh DLT và replay có kiểm soát mà không làm sai lệch offset hoặc che giấu lỗi publish.
