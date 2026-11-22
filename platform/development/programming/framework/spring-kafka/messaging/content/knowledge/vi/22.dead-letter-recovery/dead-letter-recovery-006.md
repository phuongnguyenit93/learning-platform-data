# Dead-letter headers

Khi Spring Kafka chuyển một record lỗi sang dead-letter topic (DLT), record được gửi đi thường mang theo các header mô tả nguồn gốc và nguyên nhân thất bại. Những metadata này giúp đội vận hành biết record đến từ topic, partition, offset nào, consumer group nào xử lý và exception nào đã xảy ra. Consumer DLT có thể dùng chúng để phân loại lỗi, cảnh báo, lưu audit hoặc lên kế hoạch replay.

Trong module `SPRING_KAFKA_MESSAGING`, producer gửi event bằng `KafkaTemplate`, consumer xử lý bằng `@KafkaListener`, còn `DeadLetterPublishingRecoverer` đảm nhiệm việc publish record sau khi retry/recovery policy quyết định chuyển nó sang DLT. DLT headers là một phần của hợp đồng vận hành: cần hiểu giá trị, kiểu dữ liệu, khả năng lặp header và thông tin nhạy cảm có thể xuất hiện trong đó.

Ví dụ typed listener trong bài sử dụng event sau:

```java
import java.math.BigDecimal;

public record OrderCreatedEvent(
        String eventId,
        String orderId,
        BigDecimal total
) {}
```

## 1. Dead-letter headers dùng để làm gì?

Một record chuyển sang DLT thường giữ payload gốc và các header gốc, đồng thời được bổ sung metadata về record nguồn và exception. Nhờ đó, người xử lý DLT không cần suy đoán nguồn gốc chỉ từ tên topic.

Ví dụ record gốc:

```text
topic: orders.created
partition: 2
offset: 184
key: order-1001
value: OrderCreatedEvent(...)
```

Sau khi recovery chuyển record sang `orders.created.DLT`, record DLT có thể mang các header tương tự:

```text
kafka_dlt-original-topic          = orders.created
kafka_dlt-original-partition      = 2
kafka_dlt-original-offset         = 184
kafka_dlt-original-consumer-group = orders-projection
kafka_dlt-exception-fqcn          = com.acme.orders.InvalidOrderStateException
kafka_dlt-exception-message       = Order cannot be shipped before payment
```

Tên hiển thị trên wire tương ứng với các hằng số trong `KafkaHeaders`. Khi viết code Spring Kafka, ưu tiên dùng hằng số thay vì tự gõ chuỗi header để tránh sai tên.

## 2. Các header mô tả record gốc

Spring Kafka cung cấp các hằng số `KafkaHeaders.DLT_ORIGINAL_*` để đọc metadata của record ban đầu:

| Hằng số | Metadata | Ý nghĩa |
|---|---|---|
| `DLT_ORIGINAL_TOPIC` | Topic gốc | Topic nơi record được consume trước khi chuyển DLT |
| `DLT_ORIGINAL_PARTITION` | Partition gốc | Partition chứa record nguồn |
| `DLT_ORIGINAL_OFFSET` | Offset gốc | Offset của record trong partition nguồn |
| `DLT_ORIGINAL_TIMESTAMP` | Timestamp gốc | Timestamp của record nguồn |
| `DLT_ORIGINAL_TIMESTAMP_TYPE` | Loại timestamp | Cho biết timestamp thuộc loại do producer tạo hay broker append |
| `DLT_ORIGINAL_CONSUMER_GROUP` | Consumer group gốc | Group đã xử lý record trước khi recovery |

Ba trường topic, partition và offset thường được dùng cùng nhau để định vị record gốc. Offset chỉ có ý nghĩa trong một partition, vì vậy không dùng riêng offset làm định danh toàn cục.

`DLT_ORIGINAL_CONSUMER_GROUP` đặc biệt hữu ích khi nhiều service hoặc nhiều group cùng dùng một topic nhưng có chính sách xử lý khác nhau. Nó giúp xác định group nào đã chuyển record sang DLT.

## 3. Các header mô tả exception

Các header `KafkaHeaders.DLT_EXCEPTION_*` mô tả lỗi khiến record được chuyển sang DLT:

| Hằng số | Ý nghĩa |
|---|---|
| `DLT_EXCEPTION_FQCN` | Tên đầy đủ của class exception |
| `DLT_EXCEPTION_CAUSE_FQCN` | Tên class của nguyên nhân gốc nếu có |
| `DLT_EXCEPTION_MESSAGE` | Message của exception |
| `DLT_EXCEPTION_STACKTRACE` | Stack trace dưới dạng nội dung text |

Những header này hỗ trợ phân loại lỗi và điều tra sự cố. Ví dụ, có thể nhóm DLT record theo exception class để nhận ra lỗi dữ liệu, lỗi trạng thái nghiệp vụ hay dependency tạm thời.

Không nên dùng exception message làm mã lỗi ổn định. Message có thể thay đổi theo phiên bản code, chứa dữ liệu đầu vào hoặc khác nhau giữa các lần retry. Nếu cần phân loại lâu dài, hãy bổ sung error code có quy ước riêng trong payload hoặc custom header, đồng thời vẫn giữ exception metadata để điều tra.

## 4. Header riêng cho lỗi deserialize key/value

Một lỗi có thể xảy ra trước khi listener được gọi: consumer không deserialize được key hoặc value. Với `ErrorHandlingDeserializer`, Spring Kafka có thể đưa metadata riêng cho lỗi deserialize key/value vào record được chuyển sang DLT.

Các nhóm header thường dùng:

| Nhóm | Hằng số | Nội dung |
|---|---|---|
| Key deserialization | `DLT_KEY_EXCEPTION_FQCN` | Class exception khi deserialize key |
| Key deserialization | `DLT_KEY_EXCEPTION_MESSAGE` | Message của lỗi deserialize key |
| Key deserialization | `DLT_KEY_EXCEPTION_STACKTRACE` | Stack trace của lỗi deserialize key |
| Value deserialization | `DLT_VALUE_EXCEPTION_FQCN` | Class exception khi deserialize value |
| Value deserialization | `DLT_VALUE_EXCEPTION_MESSAGE` | Message của lỗi deserialize value |
| Value deserialization | `DLT_VALUE_EXCEPTION_STACKTRACE` | Stack trace của lỗi deserialize value |

Các header này khác với `DLT_EXCEPTION_*` của lỗi xảy ra trong quá trình xử lý listener. Với lỗi deserialize, listener có thể chưa nhận được object Java bình thường; DLT consumer có thể cần đọc payload dưới dạng `byte[]` để phân tích hoặc sửa dữ liệu.

Nếu DLT có thể chứa cả record đã deserialize và record giữ raw bytes do lỗi deserialize, producer template dùng để publish DLT phải hỗ trợ cả hai kiểu value. Ví dụ, có thể cấu hình serializer theo kiểu dữ liệu hoặc dùng nhiều template phù hợp. Không giả định một `JsonSerializer<OrderCreatedEvent>` luôn xử lý được mọi raw `byte[]`.

## 5. Cấu hình `DeadLetterPublishingRecoverer`

`DeadLetterPublishingRecoverer` tạo record gửi đến DLT và thêm metadata nguồn gốc/exception. Ví dụ định tuyến record sang topic có hậu tố `.DLT`, giữ nguyên partition index:

```java
import org.apache.kafka.common.TopicPartition;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;

@Configuration
public class DeadLetterConfiguration {

    @Bean
    public DeadLetterPublishingRecoverer deadLetterPublishingRecoverer(
            KafkaTemplate<Object, Object> dltKafkaTemplate) {

        return new DeadLetterPublishingRecoverer(
                dltKafkaTemplate,
                (record, exception) -> new TopicPartition(
                        record.topic() + ".DLT",
                        record.partition()
                )
        );
    }
}
```

Ví dụ dùng `KafkaTemplate<Object, Object>` để minh họa một template có thể được cấu hình với serializer hỗ trợ nhiều kiểu payload. Trong production, hãy cấu hình serializer thực tế một cách tường minh; đặc biệt phải hỗ trợ `byte[]` nếu DLT nhận record lỗi deserialize. Nếu DLT giữ nguyên partition index, topic DLT cần có đủ partition tương ứng với topic nguồn.

Có thể chọn DLT topic theo quy ước khác, ví dụ một topic chung `dead-letter-events`, nhưng khi nhiều topic nguồn cùng đổ vào một DLT, metadata `DLT_ORIGINAL_TOPIC` trở nên thiết yếu để định tuyến replay về đúng nguồn.

`DeadLetterPublishingRecoverer` có thể được gắn vào `DefaultErrorHandler` hoặc `DefaultAfterRollbackProcessor` tùy luồng xử lý lỗi. Phần header được tạo bởi recoverer; error handler/after-rollback processor quyết định khi nào gọi recoverer.

## 6. Đọc DLT headers bằng `@Header`

Nếu DLT listener chỉ cần một số metadata, có thể inject trực tiếp bằng `@Header`:

Ví dụ sau dành cho record chuyển DLT do lỗi xử lý sau khi payload đã deserialize thành `OrderCreatedEvent`. Nếu DLT cũng chứa record lỗi deserialize, dùng listener nhận `ConsumerRecord<?, ?>` hoặc `Message<?>` để xử lý payload linh hoạt.

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.stereotype.Component;

@Component
public class OrderDltListener {

    @KafkaListener(
            topics = "orders.created.DLT",
            groupId = "orders-dlt-inspector"
    )
    public void inspect(
            OrderCreatedEvent event,
            @Header(KafkaHeaders.DLT_ORIGINAL_TOPIC) String originalTopic,
            @Header(KafkaHeaders.DLT_ORIGINAL_PARTITION) Integer originalPartition,
            @Header(KafkaHeaders.DLT_ORIGINAL_OFFSET) Long originalOffset,
            @Header(name = KafkaHeaders.DLT_EXCEPTION_FQCN, required = false)
                    String exceptionType,
            @Header(name = KafkaHeaders.DLT_EXCEPTION_MESSAGE, required = false)
                    String exceptionMessage) {

        System.out.printf(
                "DLT event=%s original=%s-%d@%d exception=%s message=%s%n",
                event.eventId(),
                originalTopic,
                originalPartition,
                originalOffset,
                exceptionType,
                exceptionMessage
        );
    }
}
```

`required = false` phù hợp với header tùy chọn như exception message, vì một số loại lỗi hoặc cấu hình có thể không cung cấp mọi metadata. Với các header bắt buộc trong hợp đồng DLT của ứng dụng, có thể để required mặc định và để listener báo lỗi nếu metadata thiếu.

Kiểu đích trong `@Header` cần tương thích với cách header mapper chuyển dữ liệu. Với listener nhận `Message<?>`, các header được đọc từ `MessageHeaders`; nếu đọc trực tiếp `ConsumerRecord`, header Kafka là byte array và cần giải mã theo kiểu tương ứng.

## 7. Đọc trực tiếp từ `ConsumerRecord.headers()`

Khi cần giữ nguyên API Kafka cấp thấp, có thể đọc header từ `ConsumerRecord`:

```java
import java.nio.charset.StandardCharsets;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.header.Header;

public String readStringHeader(ConsumerRecord<?, ?> record, String name) {
    Header header = record.headers().lastHeader(name);
    if (header == null || header.value() == null) {
        return null;
    }
    return new String(header.value(), StandardCharsets.UTF_8);
}
```

Ví dụ sử dụng:

```java
String originalTopic = readStringHeader(
        record, KafkaHeaders.DLT_ORIGINAL_TOPIC);
String exceptionType = readStringHeader(
        record, KafkaHeaders.DLT_EXCEPTION_FQCN);
```

Đoạn code này chỉ giải mã các header dạng text. Header partition/offset có kiểu số; không nên đọc chúng bằng cách mặc định chuyển byte array thành UTF-8. Nếu cần đọc các giá trị số trực tiếp từ `ConsumerRecord`, hãy dùng quy ước encoding mà phiên bản Spring Kafka tạo ra hoặc nhận header qua `@Header` với kiểu đích phù hợp.

Kafka cho phép nhiều header cùng tên. `lastHeader(name)` lấy header cuối cùng; nếu cần kiểm tra toàn bộ lịch sử header, dùng `headers().headers(name)` và duyệt danh sách. Không giả định mọi record chỉ có đúng một giá trị cho một header.

## 8. Header gốc, header DLT và custom header

Record chuyển sang DLT có thể chứa ba nhóm thông tin:

1. **Header của event gốc:** ví dụ `event-type`, `correlation-id`, `traceparent` do producer thêm.
2. **Header nguồn DLT:** topic, partition, offset, timestamp và consumer group gốc.
3. **Header exception:** exception class, cause, message và stack trace.

Custom header nên dùng cho metadata có ích xuyên suốt vòng đời event như correlation ID hoặc business event ID. Tránh dùng header làm nơi lưu toàn bộ payload hoặc trạng thái nghiệp vụ lớn.

Khi record đi qua nhiều vòng retry/DLT/replay, header gốc có thể được giữ lại hoặc bổ sung thêm tùy cấu hình recoverer và phiên bản Spring Kafka. Nếu hệ thống cần phân biệt nguồn ban đầu với lần chuyển DLT gần nhất, hãy định nghĩa rõ header nào đại diện cho từng mốc và kiểm tra chính sách append/replace của recoverer đang dùng.

Đừng dựa vào vị trí header trong danh sách như một hợp đồng nghiệp vụ. Với header có thể lặp, chọn `lastHeader` hoặc duyệt toàn bộ dựa trên semantics mà ứng dụng đã thống nhất.

## 9. Replay record từ DLT và ý nghĩa metadata

DLT headers giúp tìm record gốc, nhưng không tự replay record. Quy trình replay cần xác định:

- Record có còn hợp lệ để xử lý sau khi sửa lỗi hay không.
- Consumer cần gửi lại vào topic gốc hay topic retry/replay riêng.
- Có giữ nguyên key để duy trì partition routing theo aggregate không.
- Có cần bổ sung `replay-at`, `replay-by` hoặc `replay-reason` để audit không.
- Consumer đích có hỗ trợ schema/type version của payload không.
- Event đã được xử lý một phần trước lỗi hay chưa; nếu có, handler phải idempotent.

Ví dụ, record gốc `orders.created-2@184` có thể được replay sau khi sửa dữ liệu hoặc sửa consumer. Khi publish lại, record mới sẽ có topic/partition/offset mới. `DLT_ORIGINAL_*` mô tả nguồn gốc được ghi trong quá trình dead-letter; metadata broker của lần publish mới mô tả vị trí mới. Hai loại vị trí này không giống nhau.

Giữ `eventId` ổn định qua replay để application layer có thể phát hiện duplicate. Nếu replay bằng producer, nên ghi thêm metadata audit mới thay vì ghi đè hoặc giả mạo offset của record gốc.

## 10. Bảo mật và giới hạn kích thước header

Exception message và stack trace có thể chứa thông tin nhạy cảm như SQL, tên bảng, payload fragment, URL nội bộ, token hoặc dữ liệu cá nhân. DLT thường có retention dài và được nhiều người vận hành truy cập; do đó cần kiểm soát quyền đọc DLT và log.

Một số nguyên tắc:

- Không đưa secret, access token hoặc credential vào custom headers.
- Xem stack trace và exception message là dữ liệu cần kiểm soát truy cập.
- Cân nhắc lọc hoặc rút gọn exception message trước khi lưu nếu có thể chứa dữ liệu nhạy cảm.
- Giữ header nhỏ; stack trace dài làm tăng kích thước record và có thể chạm giới hạn message/request của broker.
- Không log toàn bộ payload và headers một cách mặc định nếu record có dữ liệu nhạy cảm.
- Thiết lập ACL riêng cho topic DLT và giới hạn consumer group được phép đọc/replay.
- Có chính sách retention và xóa DLT theo yêu cầu dữ liệu của hệ thống.

Headers hỗ trợ chẩn đoán nhưng không thay thế log/metric có cấu trúc. Nên ghi các trường định danh như topic gốc, partition, offset, exception class và event ID; chỉ lưu stack trace đầy đủ ở nơi có kiểm soát phù hợp.

## 11. Quan sát và phân loại DLT

Consumer DLT hoặc công cụ vận hành có thể dùng header để xây dựng dashboard:

| Trường quan sát | Câu hỏi cần trả lời |
|---|---|
| `DLT_ORIGINAL_TOPIC` | Topic nào có tỷ lệ record lỗi cao? |
| `DLT_ORIGINAL_CONSUMER_GROUP` | Consumer group nào đang gặp vấn đề? |
| `DLT_EXCEPTION_FQCN` | Loại exception nào chiếm đa số? |
| `DLT_EXCEPTION_CAUSE_FQCN` | Nguyên nhân gốc có tập trung ở một dependency không? |
| `DLT_ORIGINAL_PARTITION` | Có partition nào tập trung lỗi bất thường? |
| `DLT_ORIGINAL_TIMESTAMP` | Record lỗi đã nằm trong hệ thống bao lâu? |

Metric nên đếm số record DLT theo topic nguồn, group, exception class và thời gian. Tránh dùng event ID hoặc exception message làm metric label vì cardinality có thể tăng không giới hạn. Các giá trị chi tiết nên nằm trong log có cấu trúc hoặc hệ thống lưu trữ DLT.

## 12. Kiểm thử dead-letter headers

Integration test nên xác minh header thực tế sau khi recoverer publish record:

- Tạo topic nguồn và DLT với partition count tương thích.
- Gửi một record có key và custom header như `correlation-id`.
- Làm listener ném exception để kích hoạt retry/recovery.
- Chờ record xuất hiện trong DLT.
- Đọc DLT bằng `ConsumerRecord` và kiểm tra `DLT_ORIGINAL_TOPIC`, partition, offset, timestamp và consumer group.
- Kiểm tra `DLT_EXCEPTION_FQCN`, message và cause theo loại exception.
- Gửi payload lỗi deserialize để xác minh key/value exception headers và raw bytes được giữ đúng.
- Forward/replay record nhiều lần để kiểm tra chính sách header trùng hoặc append/replace.
- Xác minh header nhạy cảm đã được lọc theo chính sách của ứng dụng.

Dùng Embedded Kafka hoặc Testcontainers để kiểm tra luồng thật. Với DLT consumer đọc bằng `@Header`, xác minh kiểu dữ liệu được mapper chuyển đổi; với `ConsumerRecord`, kiểm tra byte value và decode theo đúng quy ước.

## 13. Những lỗi thường gặp

- **Chỉ nhìn payload DLT mà bỏ qua metadata nguồn:** khó truy vết topic/partition/offset và group gây lỗi.
- **Dùng offset riêng lẻ để định vị record:** offset chỉ duy nhất trong partition; cần kết hợp topic và partition.
- **Nhầm exception header với deserialization exception header:** lỗi listener và lỗi deserialize có nhóm metadata khác nhau.
- **Giả định payload DLT luôn là POJO:** lỗi deserialize có thể khiến DLT chứa raw `byte[]`.
- **Dùng serializer không hỗ trợ raw bytes:** recoverer không thể publish DLT cho record deserialize lỗi.
- **Đọc numeric header như UTF-8:** partition/offset có kiểu số và cần mapping/encoding phù hợp.
- **Giả định header không thể trùng:** Kafka cho phép nhiều header cùng tên; cần quy định cách chọn giá trị.
- **Dựa vào exception message để phân loại lâu dài:** message không ổn định và có thể chứa dữ liệu nhạy cảm.
- **Không giới hạn quyền đọc DLT:** stack trace và payload có thể lộ thông tin nội bộ.
- **Replay nhưng không giữ event ID/idempotency:** có thể tạo side effect trùng.
- **Ghi đè metadata gốc khi replay:** làm mất khả năng phân biệt vị trí nguồn và vị trí mới.

## 14. Checklist sử dụng dead-letter headers

- [ ] DLT được cấu hình qua recoverer phù hợp với error handler/after-rollback processor.
- [ ] Đọc metadata gốc bằng `KafkaHeaders.DLT_ORIGINAL_*`.
- [ ] Đọc exception bằng `KafkaHeaders.DLT_EXCEPTION_*`.
- [ ] Có xử lý riêng cho key/value deserialization headers.
- [ ] DLT serializer hỗ trợ cả payload object và raw `byte[]` nếu cần.
- [ ] DLT topic có partition và retention phù hợp.
- [ ] Consumer biết cách đọc header qua `@Header`, `MessageHeaders` hoặc `ConsumerRecord`.
- [ ] Có quy tắc cho header trùng và nhiều vòng forwarding/replay.
- [ ] Replay giữ event ID và idempotency; không giả mạo offset gốc.
- [ ] Stack trace/message/custom headers không làm lộ secret hoặc dữ liệu nhạy cảm.
- [ ] ACL, retention, metric và quy trình xử lý DLT được xác định.
- [ ] Integration test xác minh header thực tế, bao gồm deserialize failure.

Dead-letter headers biến DLT từ một nơi chứa record lỗi thành nguồn metadata có thể truy vết và vận hành. Khi đọc đúng nhóm `DLT_ORIGINAL_*`, `DLT_EXCEPTION_*` và key/value deserialization headers, đồng thời kiểm soát kiểu payload, header trùng và dữ liệu nhạy cảm, đội phát triển có thể phân loại lỗi và replay có kiểm soát mà vẫn giữ được nguồn gốc của event.
