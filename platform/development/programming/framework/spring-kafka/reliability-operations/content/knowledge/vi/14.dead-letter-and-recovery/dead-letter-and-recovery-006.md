# Dead-letter headers

Khi một record không thể được xử lý thành công và được chuyển sang **Dead Letter Topic (DLT)**, điều quan trọng không chỉ là giữ lại key/value. Hệ thống còn phải lưu được *record đến từ đâu, vì sao thất bại, thất bại trong lần thử nào và cần xử lý ra sao*. Trong Spring Kafka, các thông tin này thường được mang theo dưới dạng **Kafka headers** do `DeadLetterPublishingRecoverer` bổ sung khi publish record sang DLT.

Dead-letter headers là phần thiết yếu của vận hành reliability: nhờ đó người trực hệ thống có thể phân biệt lỗi dữ liệu với lỗi phụ thuộc, nối bản ghi DLT về topic/partition/offset nguồn, xác định nguyên nhân và replay có kiểm soát. Tuy nhiên, header chỉ là metadata; việc record nằm ở DLT không chứng minh nghiệp vụ đã hoàn tất.

## 1. Bối cảnh: từ lỗi listener đến DLT

Một consumer có thể thất bại vì payload không hợp lệ, thiếu schema, database timeout, vi phạm quy tắc nghiệp vụ hoặc exception trong code. Khi các lần retry được phép đã hết, cơ chế recovery có thể chuyển record sang topic chuyên biệt:

~~~text
orders [partition 2, offset 418]
            |
            v
    Order listener xử lý
            |
            +-- Thành công ------------> commit tiến độ
            |
            +-- Thất bại
                    |
                    v
             Error handler
                    |
             Retry + backoff
                    |
             Hết retry budget
                    |
                    v
        DeadLetterPublishingRecoverer
                    |
                    +-- Copy key/value phù hợp
                    +-- Bổ sung metadata nguồn
                    +-- Bổ sung metadata exception
                    +-- Có thể thêm custom headers
                    |
                    v
             orders.DLT
~~~

Trong các listener **không transactional**, `DefaultErrorHandler` thường phối hợp backoff, exception classification và recoverer. Với listener trong Kafka transaction, luồng rollback và recovery có thể dùng `DefaultAfterRollbackProcessor`. Cả hai có thể liên quan tới DLT, nhưng cấu hình và ranh giới commit khác nhau.

Những câu hỏi cần trả lời khi kiểm tra một DLT record:

- Nó đến từ topic, partition, offset và consumer group nào?
- Header nào cho biết exception, nguyên nhân gốc và stack trace?
- Key/value có phải dữ liệu gốc, hay đã thay đổi qua deserialization/conversion?
- Metadata nào phục vụ correlation, idempotency và replay?
- Đây là lỗi có thể retry lại hay cần sửa dữ liệu/triển khai?
- Có bao nhiêu lần record đã đi qua retry topic hoặc DLT?

Đó là lý do dead-letter headers không chỉ là chi tiết serialization mà là một phần của **hợp đồng phục hồi** giữa ứng dụng và hệ thống vận hành.

## 2. Header là gì trong Kafka?

Kafka record có các thành phần: topic, partition, offset (do broker gán), timestamp, key, value và một tập **headers**. Mỗi header là một cặp tên và giá trị `byte[]`.

Ví dụ khái niệm:

~~~text
Topic: orders.DLT
Partition: 2
Offset (trên DLT): 127
Key: order-901
Value: {"eventId":"evt-901","orderId":"order-901", ...}

Headers:
  event-id                     = evt-901
  kafka_dlt-original-topic     = orders
  kafka_dlt-original-partition = [binary integer: 2]
  kafka_dlt-original-offset    = [binary long: 418]
  kafka_dlt-exception-fqcn     = com.example.InvalidOrderException
  kafka_dlt-exception-message  = unsupported order state
~~~

Tên ở trên minh họa các header mà Spring Kafka đặt theo constants; không nên hardcode chuỗi prefix khi Java API có hằng số `KafkaHeaders` tương ứng. Các loại numeric thường được mã hóa dưới dạng byte theo quy ước framework, không phải chuỗi số đọc bằng UTF-8.

Kafka **cho phép nhiều header cùng key**. Do đó, khi record được forward qua nhiều bước, cần biết đang đọc header đầu tiên hay cuối cùng. `Headers.lastHeader(name)` trả về giá trị cuối cùng của tên đó; `Headers.headers(name)` dùng để duyệt các giá trị cùng tên.

## 3. Nhóm header truy vết record nguồn

`DeadLetterPublishingRecoverer` có thể bổ sung nhóm header nguồn qua các constant trong `KafkaHeaders`:

| Header constant | Thông tin lưu | Giá trị sử dụng |
|---|---|---|
| `KafkaHeaders.DLT_ORIGINAL_TOPIC` | Topic ban đầu | Xác định luồng gây lỗi |
| `KafkaHeaders.DLT_ORIGINAL_PARTITION` | Partition của record gốc | Truy vết thứ tự và vị trí |
| `KafkaHeaders.DLT_ORIGINAL_OFFSET` | Offset ở topic gốc | Đối chiếu record hoặc audit |
| `KafkaHeaders.DLT_ORIGINAL_TIMESTAMP` | Timestamp của record gốc | Điều tra thời gian phát sinh |
| `KafkaHeaders.DLT_ORIGINAL_TIMESTAMP_TYPE` | Kiểu timestamp nguồn | Phân biệt create time/log append time |
| `KafkaHeaders.DLT_ORIGINAL_CONSUMER_GROUP` | Consumer group nhận record trước khi recover | Xác định consumer chịu trách nhiệm |

Ví dụ, một record được đọc ở `orders-2@418` rồi ghi sang `orders.DLT-2@127`. Offset `127` trên topic DLT là **offset mới**, không thay thế offset nguồn `418`. Header `DLT_ORIGINAL_OFFSET` giúp liên kết hai vị trí này.

Khi có nhiều consumer group cùng đọc topic gốc, nhóm `DLT_ORIGINAL_CONSUMER_GROUP` giúp nhận diện **group nào** đã chuyển record sang DLT. Một record gốc có thể được các group xử lý với kết quả khác nhau; không nên kết luận tất cả consumer đều lỗi chỉ vì một DLT có chứa record đó.

Sự hiện diện của một số header phụ thuộc phiên bản Spring Kafka, cấu hình recoverer và luồng publish. Code vận hành nên xử lý trường hợp thiếu header, đặc biệt khi hệ thống phải đọc record DLT cũ được tạo trước khi nâng cấp framework.

## 4. Nhóm header mô tả exception

Nhóm thứ hai lưu thông tin về lỗi khiến record phải recovery.

| Header constant | Nội dung |
|---|---|
| `KafkaHeaders.DLT_EXCEPTION_FQCN` | Tên lớp exception đầy đủ |
| `KafkaHeaders.DLT_EXCEPTION_CAUSE_FQCN` | Loại cause nằm bên trong exception nếu có |
| `KafkaHeaders.DLT_EXCEPTION_MESSAGE` | Message của exception |
| `KafkaHeaders.DLT_EXCEPTION_STACKTRACE` | Stack trace để chẩn đoán |
| Các header dành cho **key deserialization failure** trong phiên bản hỗ trợ | Thông tin exception tương ứng với phần key |

Ví dụ:

~~~text
DLT_EXCEPTION_FQCN  = org.springframework.kafka.listener.ListenerExecutionFailedException
DLT_EXCEPTION_CAUSE_FQCN = com.example.orders.UnsupportedOrderVersionException
DLT_EXCEPTION_MESSAGE = Unsupported order version: 9
DLT_EXCEPTION_STACKTRACE = java.lang... (nhiều dòng)
~~~

Exception đầu ngoài có thể là wrapper do listener adapter tạo, trong khi cause bên trong mới là lỗi nghiệp vụ thực tế. Vì vậy, để phân loại nguyên nhân, nên đọc cả exception FQCN, cause và message; không chỉ dựa vào message bằng cách match substring.

Stack trace có giá trị khi điều tra lỗi bất thường nhưng có thể dài. Nó làm tăng kích thước record và có thể chứa đường dẫn source code, tên lớp, message nhạy cảm hoặc dữ liệu không nên được chia sẻ rộng rãi. Không coi tất cả nội dung stack trace là an toàn để công khai.

Cách biểu diễn và danh sách chính xác của exception headers có thể thay đổi theo phiên bản Spring Kafka. Khi viết code, sử dụng constant và API của phiên bản dự án, đồng thời không giả định mọi DLT record đều có đầy đủ tất cả header.

## 5. Đọc header đúng kiểu dữ liệu

Vì header value là `byte[]`, cách decode cần dựa theo loại dữ liệu. Chuỗi như topic và exception FQCN thường có thể đọc bằng UTF-8; partition và offset thường được mã hóa nhị phân.

Ví dụ tiện ích đọc metadata cơ bản:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import org.apache.kafka.common.header.Header;
import org.apache.kafka.common.header.Headers;
import org.springframework.kafka.support.KafkaHeaders;

public final class DltHeaderReader {

    private DltHeaderReader() {
    }

    public static String text(Headers headers, String name) {
        Header header = headers.lastHeader(name);
        return header == null || header.value() == null
                ? null
                : new String(header.value(), StandardCharsets.UTF_8);
    }

    public static Integer originalPartition(Headers headers) {
        Header header = headers.lastHeader(KafkaHeaders.DLT_ORIGINAL_PARTITION);
        if (header == null || header.value() == null
                || header.value().length != Integer.BYTES) {
            return null;
        }
        return ByteBuffer.wrap(header.value()).getInt();
    }

    public static Long originalOffset(Headers headers) {
        Header header = headers.lastHeader(KafkaHeaders.DLT_ORIGINAL_OFFSET);
        if (header == null || header.value() == null
                || header.value().length != Long.BYTES) {
            return null;
        }
        return ByteBuffer.wrap(header.value()).getLong();
    }
}
~~~

Một listener đọc record DLT:

~~~java
@KafkaListener(
    topics = "orders.DLT",
    groupId = "orders-dlt-operations"
)
public void inspectDlt(ConsumerRecord<String, byte[]> record) {
    Headers headers = record.headers();

    String originTopic = DltHeaderReader.text(
            headers, KafkaHeaders.DLT_ORIGINAL_TOPIC);
    Integer originPartition = DltHeaderReader.originalPartition(headers);
    Long originOffset = DltHeaderReader.originalOffset(headers);
    String errorType = DltHeaderReader.text(
            headers, KafkaHeaders.DLT_EXCEPTION_FQCN);

    log.warn(
        "DLT record received: origin={}-{}@{} dlt={}-{}@{} error={}",
        originTopic, originPartition, originOffset,
        record.topic(), record.partition(), record.offset(),
        errorType
    );

    dltCaseService.storeForReview(record);
}
~~~

Ví dụ chọn `byte[]` cho value để minh họa xử lý raw payload. Consumer factory của DLT phải dùng deserializer tương thích; nếu đang dùng JSON-to-object, tham số listener có thể là kiểu khác. Dữ liệu lưu qua `storeForReview` phải được ghi bền vững và có chính sách xác nhận offset rõ ràng.

**Không** decode `DLT_ORIGINAL_OFFSET` bằng `Long.parseLong(new String(bytes))` nếu dữ liệu được ghi theo dạng binary long. Sai cách decode có thể tạo offset vô nghĩa hoặc exception ở công cụ xử lý DLT.

## 6. Cấu hình DeadLetterPublishingRecoverer

Một cách phổ biến để tạo DLT headers là dùng `DeadLetterPublishingRecoverer` làm recoverer của `DefaultErrorHandler`.

~~~java
@Bean
DeadLetterPublishingRecoverer deadLetterRecoverer(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    return new DeadLetterPublishingRecoverer(
        kafkaTemplate,
        (record, exception) -> new TopicPartition(
            record.topic() + ".DLT",
            record.partition()
        )
    );
}

@Bean
DefaultErrorHandler orderErrorHandler(
        DeadLetterPublishingRecoverer recoverer) {

    var handler = new DefaultErrorHandler(
        recoverer,
        new FixedBackOff(1_000L, 3L)
    );

    handler.addNotRetryableExceptions(
        InvalidOrderPayloadException.class,
        UnsupportedOrderVersionException.class
    );

    return handler;
}
~~~

Recoverer có nhiệm vụ tạo producer record đích, chuyển key/value phù hợp, mang theo headers của record và bổ sung metadata phục vụ recovery. Đích mặc định thường là topic nguồn cộng hậu tố `.DLT` với partition tương ứng, nhưng destination resolver có thể thay đổi logic này như ví dụ trên.

Để dùng handler, gắn vào container factory:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
orderListenerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory,
        DefaultErrorHandler orderErrorHandler) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(orderErrorHandler);
    return factory;
}
~~~

Topic DLT phải tồn tại hoặc ứng dụng có cơ chế provision phù hợp. Nếu định tuyến giữ nguyên partition nguồn, topic DLT phải có ít nhất số partition tương ứng; nếu không, publish có thể thất bại. Có thể cấu hình destination resolver khác để Kafka producer tự chọn partition khi không cần giữ mapping 1:1.

## 7. Thêm custom headers phục vụ nghiệp vụ

Các header mặc định giải thích **nguồn gốc** và **exception** nhưng thường chưa đủ để vận hành xuyên nhiều hệ thống. Những header bổ sung hữu ích có thể gồm:

- `event-id`: định danh business event ổn định qua retry và replay.
- `correlation-id` hoặc `trace-id`: liên kết log giữa producer, consumer và dependency.
- `schema-version` hoặc `event-type`: giúp định tuyến người xử lý.
- `x-failure-category`: nhóm lỗi đã chuẩn hóa, chẳng hạn `TRANSIENT`, `VALIDATION`, `BUSINESS_RULE`.
- `x-recovery-policy`: mô tả quyết định `DLT`, `MANUAL_REVIEW` hoặc `DISCARD_APPROVED`.

Spring Kafka cung cấp cơ chế thêm headers cho recoverer, ví dụ `addHeadersFunction(...)` ở các phiên bản hỗ trợ:

~~~java
@Bean
DeadLetterPublishingRecoverer deadLetterRecoverer(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    var recoverer = new DeadLetterPublishingRecoverer(kafkaTemplate);

    recoverer.addHeadersFunction((record, exception) -> {
        var headers = new RecordHeaders();

        headers.add(
            "x-failure-category",
            failureCategory(exception).getBytes(StandardCharsets.UTF_8)
        );

        headers.add(
            "x-recovery-policy",
            "DLT".getBytes(StandardCharsets.UTF_8)
        );

        return headers;
    });

    return recoverer;
}

private static String failureCategory(Exception exception) {
    Throwable cause = exception;
    while (cause.getCause() != null) {
        cause = cause.getCause();
    }
    if (cause instanceof IllegalArgumentException) {
        return "VALIDATION";
    }
    return "UNKNOWN";
}
~~~

`failureCategory(...)` ở đây chỉ là ví dụ tối giản. Trong production nên xây classifier theo exception nghiệp vụ và ngữ cảnh; không nên mặc định mọi `IllegalArgumentException` đều là lỗi dữ liệu vĩnh viễn.

Tùy version, Spring Kafka có API để tùy biến thêm header functions, tạo exception headers hoặc kiểm soát headers đã tồn tại. Tránh cấu hình custom header trùng tên với `KafkaHeaders.DLT_*` nếu không có mục đích rõ ràng, vì dữ liệu nguồn do framework tạo có thể bị ghi đè hoặc xuất hiện nhiều bản.

## 8. Các header nào cần giữ nguyên?

Khi forward record sang topic retry hoặc DLT, các Kafka headers sẵn có thường được chuyển tiếp theo chính sách của framework và recoverer. Tuy nhiên, không phải mọi header đều nên được giữ mãi:

| Loại header | Nên làm gì? | Lý do |
|---|---|---|
| `event-id`, `correlation-id` | Giữ nếu cần truy vết và deduplicate | Hỗ trợ replay an toàn |
| `event-type`, `schema-version` | Giữ khi có giá trị nghiệp vụ | Phục hồi đúng kiểu record |
| `DLT_ORIGINAL_*` | Giữ nguồn gốc gốc theo chính sách | Truy ngược topic/partition/offset ban đầu |
| Exception FQCN/message | Giữ đủ để điều tra | Phân loại lỗi |
| Stack trace | Cân nhắc kích thước và độ nhạy cảm | Có thể rất lớn hoặc chứa thông tin không nên lan truyền |
| Authentication token/cookie | Không tự động truyền tiếp nếu không cần | Tránh rò rỉ credential |
| Headers chỉ dùng nội bộ một request | Xem xét loại bỏ | Không tạo contract không cần thiết |

Khi thiết kế producer event, hạn chế ngay từ đầu việc gửi bearer token, session cookie hoặc dữ liệu cá nhân trong header Kafka. DLT thường có retention dài hơn và nhiều người vận hành có quyền đọc hơn topic chính.

Bất kỳ hệ thống nào sử dụng DLT headers như một API phải định nghĩa rõ danh sách bắt buộc/tùy chọn, encoding và hành vi khi thiếu hoặc trùng header. Không coi `KafkaHeaders` là schema ổn định tuyệt đối qua mọi phiên bản khi chưa kiểm tra compatibility.

## 9. Header có thể lặp khi record qua nhiều tầng recovery

Một event có thể đi qua topic gốc, retry topic, DLT và được replay. Khi đó, một số header nguồn hoặc exception có thể xuất hiện nhiều lần hoặc được thay thế.

~~~text
orders                 -> orders-retry-1000
orders-retry-1000      -> orders-retry-2000
orders-retry-2000      -> orders.DLT
orders.DLT (replay)    -> orders
~~~

Nếu mỗi bước thêm `DLT_EXCEPTION_MESSAGE` mà không bỏ bản cũ, record có thể tăng kích thước và xuất hiện nhiều message thuộc các lần lỗi khác nhau. Nếu tất cả lần forward ghi lại original topic theo topic ngay trước đó, công cụ vận hành có nguy cơ hiểu nhầm retry topic là topic nguồn.

Spring Kafka có các cấu hình liên quan tới việc append original headers và strip previous exception headers trên recoverer trong những phiên bản phù hợp. Thay vì dựa vào một mặc định cố định, cần kiểm tra phiên bản Spring Kafka và quyết định:

1. Muốn lưu *nguồn đầu tiên* hay *chặng gần nhất*?
2. Muốn giữ *exception cuối cùng* hay *toàn bộ lịch sử exception*?
3. Có cần truy vết từng attempt qua log/trace riêng thay vì nhét tất cả vào Kafka headers?
4. Giới hạn kích thước record và yêu cầu bảo mật cho metadata lỗi là bao nhiêu?

Một nguyên tắc hữu ích: giữ `event-id` bền vững qua mọi lần retry/replay, đồng thời ghi lại lịch sử chuyển topic ở observability system. DLT header đủ để điều tra record hiện tại, nhưng không nhất thiết là nơi lưu toàn bộ audit trail có thể tăng không giới hạn.

## 10. Exception headers và ErrorHandlingDeserializer

Lỗi có thể xảy ra trước khi listener nhận được object Java, ví dụ JSON không parse được hoặc key/value deserializer bị lỗi. Nếu exception ném trực tiếp trong `poll()`, listener thông thường không nhận được object để tự xử lý.

`ErrorHandlingDeserializer` của Spring Kafka bọc delegate deserializer và chuyển thông tin lỗi qua header để container/error handler xử lý. Ví dụ:

~~~yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.value.default.type: com.example.events.OrderEvent
        spring.json.trusted.packages: com.example.events
~~~

Các exception headers của `ErrorHandlingDeserializer` và nhóm `KafkaHeaders.DLT_EXCEPTION_*` không hoàn toàn là cùng một tập header. Header của deserializer cung cấp thông tin cho error handler biết việc giải mã thất bại; recoverer sử dụng thông tin đó để tạo DLT record và header chẩn đoán thích hợp.

Khi lỗi value deserialization, payload được đưa sang DLT có thể là **byte[] gốc**, không phải object `OrderEvent`. Producer dùng cho DLT cần serializer có thể ghi dữ liệu kiểu thực tế. Nếu ứng dụng chỉ cấu hình `JsonSerializer<OrderEvent>`, publish raw bytes có thể thất bại hoặc cho dữ liệu không mong muốn. Có thể dùng serializer theo kiểu dữ liệu hoặc `DelegatingByTypeSerializer` trong các cấu hình thích hợp.

Ngoài ra, một số phiên bản cung cấp riêng header cho lỗi **key deserialization**. Nếu key bị lỗi, việc dùng key làm routing/idempotency có thể không còn tin cậy. Với DLT consumer, hãy xử lý tình huống key null, key raw bytes hoặc không thể xác định business ID, thay vì giả định key đã được parse thành chuỗi hợp lệ.

## 11. Kích thước header và giới hạn Kafka record

Stack trace có thể chiếm hàng chục KB. Nếu record mang theo nhiều headers cũ qua các lần retry, kích thước tăng dần. Hệ quả có thể gồm:

- Producer không gửi được record do vượt giới hạn request/record size.
- Broker từ chối do topic/broker message-size policy.
- Network bandwidth và storage cho retry/DLT tăng.
- Tool vận hành đọc DLT chậm và log chứa quá nhiều dữ liệu.
- Thông tin lỗi nhạy cảm bị nhân bản sang nhiều topic.

Cần xem tổng kích thước **key + value + headers + overhead**, không chỉ kích thước JSON payload. Các giới hạn thường liên quan tới producer `max.request.size` và broker/topic message size, nhưng kích thước thực tế phụ thuộc serialization và compression.

Một hướng thiết kế khi stack trace quá dài:

1. Giữ loại exception, message rút gọn an toàn và các header nguồn.
2. Ghi stack trace đầy đủ vào hệ thống log/tracing bảo mật có retention phù hợp.
3. Đưa trace/correlation ID vào custom header để liên kết hai hệ thống.
4. Tùy biến exception header creation bằng API của phiên bản đang dùng nếu cần giới hạn hoặc loại bỏ phần quá lớn.
5. Không làm mất các field bắt buộc cho replay như event ID và original topic/partition/offset.

Không nên tự động truncate toàn bộ header bytes bằng cách cắt giữa chuỗi UTF-8 hay giữa giá trị binary integer/long. Nếu phải giới hạn, cần encode lại đúng kiểu dữ liệu và giữ contract rõ ràng.

## 12. DLT header không thay thế offset và acknowledgment

Khi record từ `orders` được publish sang `orders.DLT`, bản ghi trên DLT có offset mới. Việc consumer gốc có tiến offset hay không phụ thuộc handler, ack mode, transaction và kết quả recovery.

Một số tình huống:

| Tình huống | Kết quả mong muốn |
|---|---|
| Publish DLT thành công; recovery được coi là hoàn tất | Consumer gốc có thể tiến offset theo chính sách |
| Publish DLT thất bại | Không được âm thầm coi record đã recover |
| Process crash sau publish DLT, trước commit offset nguồn | Record gốc có thể bị đọc lại, tạo bản sao trên DLT |
| DLT consumer xử lý lại nhưng crash trước commit offset DLT | DLT record có thể được giao lại |
| Replay từ DLT về topic nghiệp vụ | Hệ thống phải chống lặp side effect |

Dead-letter headers giúp phát hiện sự trùng lặp bằng event ID hoặc vị trí nguồn, nhưng không tự thực hiện deduplication. Nếu ứng dụng có side effect ngoài Kafka, hãy dùng idempotency key, inbox table có unique constraint hoặc workflow có trạng thái bền vững.

Ví dụ khóa điều tra có thể dùng:

~~~text
consumerGroup + originalTopic + originalPartition + originalOffset
~~~

Khóa này hữu ích để xác định cùng một Kafka delivery được recover nhiều lần. Nhưng với cùng business event được produce thành nhiều record khác nhau, cần `event-id` độc lập với offset để deduplicate theo semantics nghiệp vụ.

## 13. Thiết kế DLT consumer và quy trình review

DLT consumer nên tập trung vào **lưu trữ, cảnh báo, phân loại và hỗ trợ replay**, không nhất thiết tự động gửi lại record vào topic gốc ngay khi nhận.

Một luồng vận hành:

~~~mermaid
flowchart TD
    A["Record ở DLT"] --> B["Đọc dead-letter headers"]
    B --> C{"Metadata nguồn đầy đủ?"}
    C -->|Không| D["Quarantine + điều tra"]
    C -->|Có| E["Phân loại nguyên nhân"]
    E --> F{"Sự cố đã được khắc phục?"}
    F -->|Chưa| G["Giữ record / ticket / alert"]
    F -->|Có| H["Phê duyệt replay"]
    H --> I["Replay giữ event-id và trace"]
    I --> J["Theo dõi kết quả và deduplicate"]
~~~

Một case quản trị có thể lưu các field:

~~~json
{
  "eventId": "evt-901",
  "originalTopic": "orders",
  "originalPartition": 2,
  "originalOffset": 418,
  "dltTopic": "orders.DLT",
  "dltPartition": 2,
  "dltOffset": 127,
  "exceptionClass": "com.example.InvalidOrderException",
  "failureCategory": "VALIDATION",
  "status": "WAITING_FOR_REVIEW"
}
~~~

`dltOffset` khác `originalOffset`; lưu cả hai giúp truy vết hai log riêng. Với payload nhạy cảm, lưu payload dưới quyền truy cập hạn chế hoặc chỉ lưu reference/checksum, không phải log mọi chi tiết vào ticket công khai.

Nếu công cụ đọc DLT thấy thiếu header nguồn, không nên tự điền default như partition 0 hoặc offset 0 vì sẽ tạo sai bằng chứng. Đánh dấu metadata không đầy đủ và xử lý như trường hợp cần điều tra.

## 14. Replay và bảo toàn provenance

Replay cần trả lời: record được publish lại từ DLT về đâu, có cần giữ key, timestamp, event ID và những header nào, và có nguy cơ lặp nghiệp vụ không?

Các nguyên tắc:

- Giữ `event-id` và correlation ID để có thể deduplicate.
- Phân biệt topic đang replay với topic nguồn ban đầu.
- Tránh chuyển nguyên bộ exception stacktrace cũ về luồng nghiệp vụ nếu consumer không cần.
- Thêm metadata replay có tên riêng, ví dụ `x-replay-id`, `x-replayed-at`, `x-replay-operator` nếu chính sách bảo mật cho phép.
- Chỉ replay sau khi đã xử lý nguyên nhân hoặc có chiến lược chống vòng lặp.
- Không tự chỉnh offset/partition trong header để giả vờ record đến từ một nguồn khác.
- Kiểm tra serializer phù hợp, nhất là khi record DLT chứa raw bytes do lỗi deserialization.

Ví dụ hướng xử lý:

~~~text
DLT record:
  event-id = evt-901
  original-topic = orders
  exception = UnsupportedOrderVersionException

Sau khi nâng cấp consumer:
  publish lại event-id = evt-901 vào orders
  add x-replay-id = replay-2026-11-15-001
  lưu audit: originalTopic/partition/offset + replay ID
~~~

Khi publish lại vào Kafka, record sẽ có offset mới trên topic đích. Các header `DLT_ORIGINAL_*` có thể được giữ trong hệ thống audit, nhưng không nên dùng chúng thay thế metadata hiện hành do Kafka broker cấp.

## 15. Security và privacy của dead-letter headers

DLT không phải khu vực vô hại. Header exception có thể tiết lộ tên service, đường dẫn nội bộ, SQL error, endpoint URL, hoặc một phần thông tin từ payload xuất hiện trong exception message. DLT thường được giữ lâu để điều tra, vì vậy cần có chính sách riêng:

1. Hạn chế ACL đọc/ghi DLT cho ứng dụng và nhóm vận hành thực sự cần.
2. Quy định retention và khả năng xóa dữ liệu theo phân loại thông tin.
3. Không gắn credential, token hoặc secret vào Kafka header.
4. Sanitize exception message nếu exception có thể chứa dữ liệu người dùng.
5. Không copy toàn bộ stack trace vào alert, ticket hoặc dashboard truy cập rộng.
6. Giữ audit trail cho hoạt động replay, đặc biệt các luồng thanh toán hoặc đơn hàng.

Nếu muốn chia sẻ metadata lỗi với hệ thống giám sát, thường chỉ cần exception class, event type, retry count, original topic và correlation ID. Stack trace đầy đủ nên nằm trong logging backend có quyền truy cập phù hợp.

## 16. Observability dựa trên DLT headers

Nhờ các header nguồn và exception, hệ thống có thể tạo dashboard theo nhóm lỗi:

| Số liệu | Ý nghĩa |
|---|---|
| Số record DLT theo original topic | Luồng nào phát sinh lỗi |
| Số record DLT theo exception class | Nhóm lỗi đang tăng |
| Số record DLT theo consumer group | Consumer nào cần xử lý |
| Tỷ lệ thiếu original metadata | Có vấn đề tương thích/config header không |
| Tuổi record DLT chưa xử lý | Tồn đọng recovery |
| Tỷ lệ replay thành công/thất bại | Hiệu quả quy trình khắc phục |
| Số lần replay cùng event ID | Nguy cơ vòng lặp hoặc tác động trùng |
| Kích thước record/header DLT | Phát hiện bùng nổ stacktrace/metadata |

Hãy dùng exception class, topic, event type hoặc error category làm metric label có cardinality tương đối thấp. Không dùng event ID hoặc original offset làm metric label trên Prometheus/Micrometer vì mỗi event có thể tạo một series mới. Những định danh này phù hợp để đặt vào log/trace có thể tìm kiếm.

Một log gọn:

~~~text
DLT_RECEIVED origin=orders-2@418
  consumerGroup=order-projection
  error=UnsupportedOrderVersionException
  eventId=evt-901
  dlt=orders.DLT-2@127
  action=MANUAL_REVIEW
~~~

Log này đủ để điều tra ban đầu mà không cần in raw payload hay stack trace. Khi cần chi tiết, operator có thể tra cứu bằng event ID hoặc trace ID theo quyền truy cập.

## 17. Runbook khi dead-letter headers bất thường

### Thiếu original topic/partition/offset

- Xác định record có thực sự được publish bằng `DeadLetterPublishingRecoverer` hay do custom producer khác tạo.
- Kiểm tra phiên bản Spring Kafka và cấu hình tạo/giữ header.
- Xem record có bị replay hoặc forward qua công cụ trung gian đã loại bỏ headers hay không.
- Không đoán nguồn từ tên DLT nếu topology có custom routing; đánh dấu thiếu metadata và điều tra bằng audit/trace.

### Exception message có nhưng cause không rõ

- Đọc `DLT_EXCEPTION_FQCN`, cause FQCN nếu có, và stack trace theo quyền truy cập.
- Kiểm tra wrapper exception như `ListenerExecutionFailedException`.
- Dùng loại exception nghiệp vụ rõ ràng trong listener để classification ổn định hơn.

### Nhiều bản sao của cùng header

- Kiểm tra record đã qua nhiều chặng retry/recovery hoặc đã replay.
- Dùng `lastHeader` khi chỉ cần giá trị mới nhất; dùng `headers(name)` khi cần toàn bộ giá trị.
- Xác định chính sách append/strip của recoverer theo phiên bản đang dùng.
- Tránh tự cộng dồn stacktrace ở mỗi lần forward.

### DLT publish thất bại khi record chứa nhiều headers

- Kiểm tra tổng kích thước record và giới hạn producer/broker/topic.
- Kiểm tra serializer của raw bytes hoặc object.
- Cân nhắc rút gọn exception metadata theo cơ chế tùy biến được hỗ trợ.
- Đảm bảo handler không coi publish thất bại là recovery thành công.

### Replay lại gặp lỗi cũ

- So sánh exception class hiện tại với record DLT cũ.
- Xác định dependency hoặc schema đã được sửa thật sự chưa.
- Xác minh event ID giữ nguyên và quy trình chống duplicate hoạt động.
- Tạm dừng replay hàng loạt để tránh tạo vòng lặp DLT.

## 18. Checklist thiết kế dead-letter headers

- [ ] DLT record có đủ metadata nguồn: topic, partition, offset và consumer group khi khả dụng.
- [ ] Exception FQCN, cause và message có thể đọc được theo version/framework thực tế.
- [ ] Header numeric được decode đúng dạng nhị phân, không xử lý như chuỗi UTF-8.
- [ ] Custom headers dùng tên rõ ràng và không vô tình ghi đè constants `KafkaHeaders.DLT_*`.
- [ ] Event ID giữ nguyên qua retry, DLT và replay.
- [ ] Có chính sách cho header trùng và nhiều lần forward.
- [ ] Stacktrace/exception message không làm lộ secret hoặc vượt giới hạn record.
- [ ] Producer DLT serialize được payload gốc hoặc raw bytes khi deserialize lỗi.
- [ ] Recovery publish thất bại không bị coi là xử lý thành công.
- [ ] DLT consumer lưu case/audit trước khi xác nhận tiến độ theo chính sách.
- [ ] Replay được kiểm soát, có idempotency và giữ provenance.
- [ ] Dashboard/alerts theo dõi DLT volume, lỗi, tuổi record và trạng thái replay.

**Dead-letter headers biến DLT từ nơi chứa các record thất bại thành một nguồn dữ liệu có thể điều tra và phục hồi.** Trong Spring Kafka, hãy dựa trên `KafkaHeaders.DLT_*`, `DeadLetterPublishingRecoverer` và metadata nghiệp vụ ổn định để giữ nguyên nguồn gốc, diễn giải exception và quyết định replay an toàn. Đừng để header quá lớn hoặc thiếu chuẩn mã hóa khiến chính luồng recovery trở thành một nguồn lỗi mới.
