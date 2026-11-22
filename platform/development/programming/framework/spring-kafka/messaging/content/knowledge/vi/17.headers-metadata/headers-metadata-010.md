# Quy ước header dùng chung giữa dịch vụ

## 1. Vì sao cần quy ước header?

Kafka record có key, value, timestamp và headers. Payload thường chứa dữ liệu nghiệp vụ; header mang metadata đi kèm record để các dịch vụ phối hợp mà không phải nhồi mọi thông tin vận chuyển vào payload.

Ví dụ, một dịch vụ phát sự kiện đơn hàng có thể gửi payload `OrderCreatedEvent`, đồng thời gắn `event-id`, `event-type`, `correlation-id` và `traceparent`. Dịch vụ nhận dùng metadata này để nhận diện sự kiện, ghi log, nối chuỗi xử lý và tiếp tục distributed tracing.

Nếu mỗi dịch vụ tự đặt tên và cách mã hóa header, hệ thống dễ gặp các vấn đề:

- Dịch vụ A gửi `eventId`, dịch vụ B lại tìm `event-id`, khiến metadata bị xem như không tồn tại.
- Một bên ghi timestamp theo epoch milliseconds, bên kia lại đọc như chuỗi ISO-8601.
- Header có cùng tên nhưng ý nghĩa khác nhau giữa các topic.
- Một dịch vụ vô tình chuyển tiếp header nội bộ hoặc dữ liệu nhạy cảm sang dịch vụ khác.
- Khi đổi phiên bản, producer và consumer không biết header nào bắt buộc hoặc có thể bỏ qua.

Quy ước dùng chung giúp producer và consumer độc lập về ngôn ngữ, framework nhưng vẫn hiểu metadata theo cùng một hợp đồng.

## 2. Header Kafka khác payload và key như thế nào?

Ba thành phần thường bị nhầm lẫn:

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| Key | Định tuyến record đến partition và hỗ trợ xử lý theo thực thể | `orderId` |
| Value/payload | Dữ liệu nghiệp vụ của sự kiện | `OrderCreatedEvent` |
| Headers | Metadata mô tả, truy vết và diễn giải record | `event-id`, `content-type`, `correlation-id` |

Không dùng header để thay thế dữ liệu nghiệp vụ mà consumer cần để ra quyết định. Nếu `orderId` là dữ liệu bắt buộc để xử lý đơn hàng, nó phải có trong payload hoặc key theo hợp đồng; không nên chỉ giấu trong header.

Header cũng không thay thế Kafka key. Kafka không dùng `correlation-id` hay `event-id` trong header để chọn partition mặc định. Nếu cần các sự kiện của cùng đơn hàng vào cùng partition, hãy đặt `orderId` làm record key.

Kafka headers là một danh sách các cặp tên và giá trị byte. Một record có thể chứa nhiều header trùng tên. Thứ tự header được giữ trong record; vì vậy consumer cần biết một header là đơn trị hay đa trị và cách chọn giá trị nếu xuất hiện nhiều lần.

Trong Spring Messaging, `Message<?>` biểu diễn headers dưới dạng map nên một tên header chỉ có một giá trị trong map đó. Nếu cần giữ nguyên header Kafka trùng tên hoặc kiểm soát chính xác byte trên wire, hãy làm việc trực tiếp với `ProducerRecord` và `ConsumerRecord`.

## 3. Bộ quy ước header đề xuất

Không có một bộ tên header tùy chỉnh duy nhất bắt buộc cho mọi hệ thống Kafka. Các dịch vụ trong cùng nền tảng nên thống nhất một contract rõ ràng. Bảng sau là một bộ quy ước thực tế có thể áp dụng cho luồng event:

| Header | Bắt buộc? | Định dạng giá trị | Ý nghĩa |
|---|---|---|---|
| `event-id` | Có | UUID hoặc ID duy nhất dạng chuỗi UTF-8 | Nhận diện một sự kiện xuyên suốt retry và xử lý trùng |
| `event-type` | Có | Tên ổn định như `order.created` | Loại sự kiện nghiệp vụ |
| `content-type` | Có | MIME type, ví dụ `application/json` | Định dạng payload |
| `schema-version` | Có | Số phiên bản dạng chuỗi, ví dụ `1` | Phiên bản schema của payload |
| `source` | Có | Tên logic của dịch vụ phát, ví dụ `order-service` | Nguồn tạo sự kiện |
| `occurred-at` | Có nếu nghiệp vụ cần event time | ISO-8601/RFC 3339 UTC | Thời điểm sự kiện xảy ra theo nghiệp vụ |
| `correlation-id` | Theo luồng nghiệp vụ | Chuỗi UTF-8 | Liên kết nhiều bước trong cùng một workflow |
| `causation-id` | Khi sự kiện phát sinh từ sự kiện khác | `event-id` của sự kiện trước | Chỉ ra nguyên nhân trực tiếp |
| `traceparent` | Khi có distributed tracing | W3C Trace Context | Mang trace context qua ranh giới dịch vụ |
| `tracestate` | Tùy tracing vendor | W3C Trace Context | Trạng thái bổ sung của tracing |
| `tenant-id` | Chỉ hệ thống multi-tenant | ID tenant theo contract | Xác định tenant nếu cần định tuyến/ngữ cảnh |

Các tên trong bảng là quy ước của hệ thống, ngoại trừ các tên thuộc chuẩn tracing như `traceparent` và `tracestate`. Nếu tổ chức đã dùng CloudEvents hoặc một event envelope chuẩn, hãy tuân thủ naming và binding của chuẩn đó thay vì tạo một bộ header song song.

### Ý nghĩa cần thống nhất

- `event-id` là định danh của lần phát sự kiện nghiệp vụ. Khi retry cùng một sự kiện, giữ nguyên ID này. Khi tạo một sự kiện mới, cấp ID mới.
- `event-type` mô tả ý nghĩa nghiệp vụ, không nên chứa tên class Java có thể đổi package.
- `schema-version` mô tả cấu trúc payload. Tăng phiên bản khi thay đổi contract theo quy tắc tương thích đã thống nhất.
- `source` nên là tên dịch vụ logic ổn định, không phải pod ID hoặc hostname thay đổi theo lần triển khai.
- `occurred-at` là thời điểm nghiệp vụ xảy ra, khác với Kafka record timestamp có thể phản ánh thời điểm record được tạo hoặc broker ghi nhận.
- `correlation-id` có thể được giữ xuyên suốt một workflow. Nó không nhất thiết giống `trace-id`.
- `causation-id` chỉ ra sự kiện trực tiếp dẫn tới sự kiện hiện tại; nó khác correlation ID bao quát cả chuỗi.
- `traceparent` phải được tạo và tiếp tục bằng tracing propagator tương thích W3C, không tự ghép chuỗi trace bằng tay.

## 4. Quy tắc đặt tên và mã hóa giá trị

Nên thống nhất các quy tắc sau cho header tùy chỉnh:

1. Dùng chữ thường ASCII và dấu gạch nối `kebab-case`, ví dụ `event-id`, `schema-version`.
2. Tên header phân biệt chữ hoa/chữ thường ở tầng Kafka; producer và consumer phải dùng đúng cùng một cách viết.
3. Tránh dấu cách, ký tự có dấu và tên mơ hồ như `id`, `type`, `time`, `version`.
4. Không dùng tiền tố dành riêng cho framework hoặc metadata nội bộ như `spring_`, `__` nếu chưa hiểu rõ cơ chế của framework.
5. Quy định header đơn trị hay đa trị. Phần lớn metadata event nên là đơn trị.
6. Chuỗi được mã hóa UTF-8; không dựa vào charset mặc định của máy chạy.
7. Giá trị số nên có format rõ ràng. Với version, dùng số nguyên dạng chuỗi; với timestamp, dùng ISO-8601 UTC.
8. Giá trị nhị phân phải có contract riêng về encoding và version; không đưa object Java tùy ý vào header.

Kafka lưu giá trị header dưới dạng `byte[]`. Vì vậy, khi ghi chuỗi, hãy dùng `StandardCharsets.UTF_8`; khi đọc, dùng cùng encoding. Không chuyển header byte sang String bằng charset mặc định.

Ví dụ helper để tạo giá trị header văn bản:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public final class EventHeaderValues {

    private EventHeaderValues() {
    }

    public static byte[] utf8(String value) {
        if (value == null) {
            throw new IllegalArgumentException("Header value không được null");
        }
        return value.getBytes(StandardCharsets.UTF_8);
    }

    public static String asUtf8(byte[] value) {
        if (value == null) {
            throw new IllegalArgumentException("Header value không được null");
        }
        try {
            return StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(value))
                .toString();
        } catch (CharacterCodingException ex) {
            throw new IllegalArgumentException(
                "Header không phải UTF-8 hợp lệ", ex
            );
        }
    }
}
~~~

## 5. Gắn header khi gửi bằng Spring Kafka

Với contract liên dịch vụ cần byte rõ ràng, có thể tạo `ProducerRecord` và thêm header trực tiếp. Ví dụ dưới đây dùng `OrderCreatedEvent` làm payload; cấu hình serializer value phải tương thích với kiểu event, chẳng hạn JSON serializer:

~~~java
import java.util.concurrent.CompletableFuture;

import org.apache.kafka.clients.producer.ProducerRecord;
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
            OrderCreatedEvent event,
            String correlationId,
            String traceparent) {

        ProducerRecord<String, OrderCreatedEvent> record =
            new ProducerRecord<>("orders", event.orderId(), event);

        record.headers()
            .add("event-id", EventHeaderValues.utf8(event.eventId()))
            .add("event-type", EventHeaderValues.utf8("order.created"))
            .add("content-type", EventHeaderValues.utf8("application/json"))
            .add("schema-version", EventHeaderValues.utf8("1"))
            .add("source", EventHeaderValues.utf8("order-service"))
            .add("occurred-at", EventHeaderValues.utf8(
                event.occurredAt().toString()
            ));

        if (correlationId != null) {
            record.headers().add(
                "correlation-id",
                EventHeaderValues.utf8(correlationId)
            );
        }

        if (traceparent != null) {
            record.headers().add(
                "traceparent",
                EventHeaderValues.utf8(traceparent)
            );
        }

        return kafkaTemplate.send(record);
    }
}
~~~

Ví dụ giả định `OrderCreatedEvent` có các phương thức `eventId()`, `orderId()` và `occurredAt()`. Trong ứng dụng thực tế, `traceparent` nên được lấy từ tracing library/propagator đang dùng. Không tạo trace context bằng chuỗi tùy ý.

Có thể tạo một helper hoặc component dùng chung để tránh mỗi publisher tự viết tên header. Tuy nhiên, helper chỉ nên chuẩn hóa tên và encoding; ý nghĩa, tính bắt buộc và thời điểm tạo giá trị vẫn thuộc contract của từng loại event.

## 6. Đọc và kiểm tra header ở consumer

Khi cần kiểm tra chính xác Kafka headers, nhận `ConsumerRecord<K, V>`. `Headers.lastHeader(name)` trả về header cuối cùng có tên đó; nếu contract yêu cầu header đơn trị, nên phát hiện và từ chối trường hợp bị lặp thay vì âm thầm chọn một giá trị.

~~~java
import java.util.Iterator;

import org.apache.kafka.common.header.Header;
import org.apache.kafka.common.header.Headers;

public final class RequiredEventHeaders {

    private RequiredEventHeaders() {
    }

    public static String requiredSingleUtf8(
            Headers headers,
            String name) {

        Iterator<Header> values = headers.headers(name).iterator();

        if (!values.hasNext()) {
            throw new IllegalArgumentException(
                "Thiếu Kafka header bắt buộc: " + name
            );
        }

        Header header = values.next();

        if (values.hasNext()) {
            throw new IllegalArgumentException(
                "Kafka header không được lặp: " + name
            );
        }

        if (header.value() == null) {
            throw new IllegalArgumentException(
                "Kafka header không được null: " + name
            );
        }

        return EventHeaderValues.asUtf8(header.value());
    }
}
~~~

Sử dụng trong listener:

~~~java
import org.apache.kafka.clients.consumer.ConsumerRecord;

import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderEventListener {

    @KafkaListener(
        topics = "orders",
        groupId = "order-projection"
    )
    public void handle(
            ConsumerRecord<String, OrderCreatedEvent> record) {

        String eventId = RequiredEventHeaders.requiredSingleUtf8(
            record.headers(), "event-id"
        );

        String eventType = RequiredEventHeaders.requiredSingleUtf8(
            record.headers(), "event-type"
        );

        if (!"order.created".equals(eventType)) {
            throw new IllegalArgumentException(
                "Event type không được hỗ trợ: " + eventType
            );
        }

        if (!eventId.equals(record.value().eventId())) {
            throw new IllegalArgumentException(
                "event-id trong header không khớp payload"
            );
        }

        orderProjectionService.apply(record.value());
    }
}
~~~

Kiểm tra header trước khi gọi nghiệp vụ giúp lỗi contract được phát hiện tại ranh giới tích hợp. Với header tùy chọn, chỉ đọc khi tồn tại và quy định rõ hành vi khi thiếu. Không biến header thiếu thành chuỗi `"null"` hoặc giá trị mặc định có thể che giấu lỗi producer.

Nếu chỉ dùng annotation `@KafkaListener`, có thể bind metadata bằng `@Header`:

~~~java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;

@KafkaListener(topics = "orders", groupId = "order-projection")
public void handle(
        @Payload OrderCreatedEvent event,
        @Header("event-id") byte[] eventIdHeader,
        @Header(name = "correlation-id", required = false) byte[] correlationIdHeader) {

    String eventId = EventHeaderValues.asUtf8(eventIdHeader);
    String correlationId = correlationIdHeader == null
        ? null
        : EventHeaderValues.asUtf8(correlationIdHeader);

    orderProjectionService.apply(event, eventId, correlationId);
}
~~~

Cách bind qua `@Header` tiện cho listener đơn giản, nhưng việc chuyển đổi kiểu header phụ thuộc `RecordMessageConverter` và header mapper đang cấu hình. Nếu contract yêu cầu kiểm soát byte UTF-8, phát hiện header trùng tên hoặc kiểm tra cardinality, hãy nhận `ConsumerRecord` và kiểm tra trực tiếp.

## 7. Dùng Spring Message và KafkaHeaders

Spring Kafka cho phép tạo `Message<?>` với payload và headers. `KafkaHeaders` cung cấp các tên header dành riêng cho thông tin điều khiển record, ví dụ topic và key. Header nghiệp vụ như `event-id` hoặc `correlation-id` vẫn cần được định nghĩa trong contract ứng dụng.

Ví dụ:

~~~java
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<OrderCreatedEvent> message = MessageBuilder
    .withPayload(event)
    .setHeader(KafkaHeaders.TOPIC, "orders")
    .setHeader(KafkaHeaders.MESSAGE_KEY, event.orderId())
    .setHeader("event-id", event.eventId())
    .setHeader("event-type", "order.created")
    .setHeader("schema-version", "1")
    .setHeader("correlation-id", correlationId)
    .build();

kafkaTemplate.send(message);
~~~

Khi dùng `KafkaTemplate.send(Message<?>)`, `RecordMessageConverter` và header mapper của template tham gia chuyển Spring Message thành Kafka record. Ở phía consumer, converter/header mapper có thể ánh xạ Kafka headers thành Spring Message headers.

Cần kiểm tra cấu hình serializer và converter tương ứng. Nếu muốn các header chuỗi được ghi thành byte UTF-8 chính xác cho nhiều ngôn ngữ, hãy xác minh byte thực tế trong integration test hoặc dùng `ProducerRecord.headers().add(...)` như ví dụ trước. Không giả định mọi header Spring đều được chuyển thành byte theo cùng một cách trong mọi cấu hình mapper.

`KafkaHeaders.TOPIC`, `KafkaHeaders.MESSAGE_KEY` là metadata điều khiển record. Các header như `event-id`, `event-type`, `schema-version` là metadata hợp đồng sự kiện. Không đặt tên tùy chỉnh trùng với header nội bộ của Spring Kafka.

## 8. Header cho tracing và tương quan request

Ba loại ID thường bị dùng lẫn:

| Giá trị | Phạm vi | Dùng để |
|---|---|---|
| `event-id` | Một sự kiện | Khử trùng lặp và đối chiếu lần phát |
| `correlation-id` | Một workflow hoặc chuỗi nghiệp vụ | Tìm tất cả bước liên quan trong log |
| `traceparent` | Một distributed trace | Nối span giữa các dịch vụ theo W3C Trace Context |

Một workflow có thể phát nhiều event ID nhưng giữ cùng correlation ID. Mỗi lần xử lý qua một dịch vụ có thể tạo span mới trong cùng trace context. `causation-id` giúp xác định sự kiện trực tiếp dẫn tới sự kiện hiện tại.

Khi nhận một event rồi phát event tiếp theo:

- Cấp `event-id` mới cho event mới.
- Đặt `causation-id` bằng `event-id` của event đầu vào nếu quan hệ nhân quả trực tiếp.
- Giữ `correlation-id` nếu event mới thuộc cùng workflow.
- Dùng tracing propagator để inject `traceparent` và `tracestate` của span hiện tại.
- Không sao chép mù mọi header từ record đầu vào sang record mới.

Nếu ứng dụng dùng Micrometer Tracing, OpenTelemetry hoặc thư viện tracing khác, hãy dùng Kafka instrumentation/propagator tương ứng để inject và extract trace context. Việc tự copy `traceparent` cũ có thể làm trace không phản ánh đúng span mới hoặc làm sai quan hệ parent-child.

## 9. Header có thể lặp và chính sách cardinality

Kafka cho phép nhiều header cùng tên. Ví dụ một record có thể mang nhiều giá trị `tag`:

~~~java
record.headers()
    .add("tag", EventHeaderValues.utf8("priority"))
    .add("tag", EventHeaderValues.utf8("billing"));
~~~

Điều này hữu ích nếu contract định nghĩa header đa trị. Tuy nhiên, các header nhận diện event thường nên là đơn trị:

| Nhóm | Cardinality khuyến nghị | Chính sách |
|---|---|---|
| `event-id`, `event-type`, `schema-version`, `content-type` | Chính xác một | Thiếu hoặc lặp đều là lỗi contract |
| `correlation-id`, `causation-id`, `source` | Tối đa một | Có thể bắt buộc hoặc tùy loại event |
| `traceparent` | Tối đa một | Theo W3C Trace Context |
| `tracestate` | Tối đa một | Nội dung theo chuẩn tracing |
| `tag` hoặc nhãn mở rộng | Có thể nhiều | Đọc toàn bộ giá trị theo thứ tự nếu contract cho phép |

Khi header đơn trị bị lặp, chọn `lastHeader` mà không kiểm tra có thể khiến producer lỗi hoặc thành phần trung gian ghi đè metadata mà consumer không nhận ra. Với header đa trị, consumer phải đọc toàn bộ danh sách bằng `headers(name)` và giữ đúng thứ tự theo contract.

## 10. Versioning và thay đổi contract header

Header là một phần của contract liên dịch vụ. Thay đổi tên, format hoặc ý nghĩa có thể làm consumer cũ không xử lý đúng record.

Nên áp dụng quy tắc rollout theo hướng tương thích:

1. Thêm header mới dưới dạng optional trước.
2. Triển khai consumer có thể đọc cả định dạng cũ và mới.
3. Sau khi consumer mới đã sẵn sàng, producer bắt đầu gửi header mới.
4. Theo dõi tỷ lệ consumer đọc thành công và log cảnh báo khi header cũ còn xuất hiện.
5. Chỉ bỏ header cũ sau khi mọi consumer cần nó đã được nâng cấp.

Không đổi ý nghĩa của một header hiện có trong cùng một tên. Nếu format thay đổi không tương thích, dùng schema version hoặc tên header/version contract mới theo quy định. `schema-version` của payload không nhất thiết là version của toàn bộ header contract; hãy ghi rõ phạm vi từng version.

Consumer nên bỏ qua header tùy chọn mà nó chưa biết, miễn là header đó không ảnh hưởng đến việc giải mã hoặc bảo mật. Header bắt buộc chưa biết hoặc không hợp lệ phải được xử lý theo chính sách lỗi rõ ràng, ví dụ retry có giới hạn rồi chuyển dead-letter để điều tra.

## 11. Bảo mật và giới hạn kích thước

Header được lưu cùng Kafka record và có thể được đọc bởi consumer có quyền đọc topic. Không xem header là kênh bí mật hoặc vùng metadata chỉ dành cho một dịch vụ.

Không đưa các nội dung sau vào header:

- Access token, refresh token, API key, mật khẩu hoặc secret.
- Dữ liệu cá nhân nhạy cảm không cần thiết cho consumer.
- Toàn bộ JSON payload hoặc nội dung file.
- Stack trace, exception message hoặc dữ liệu nội bộ có thể làm lộ cấu trúc hệ thống.
- Thông tin xác thực người dùng chỉ để truyền tiếp giữa các dịch vụ.

Chỉ truyền metadata tối thiểu cần cho routing, tracing, contract và xử lý nghiệp vụ. Dùng TLS, ACL topic và cơ chế quản lý secret phù hợp; ACL Kafka thường kiểm soát quyền trên topic, không phải quyền riêng cho từng header.

Header cũng làm tăng kích thước record. Giữ số lượng header và độ dài giá trị ở mức nhỏ, tránh nhồi baggage lớn hoặc chuỗi JSON dài. Nếu metadata lớn, hãy đặt nó trong payload hoặc lưu ở hệ thống phù hợp rồi truyền tham chiếu. Giới hạn tổng record vẫn chịu ảnh hưởng bởi cấu hình kích thước message/batch của producer, broker và consumer.

Khi chuyển tiếp event, dùng allowlist các header được phép truyền. Không copy toàn bộ header một cách vô điều kiện vì có thể làm rò rỉ thông tin nội bộ, token hoặc context không còn đúng sau khi qua dịch vụ khác.

## 12. Kiểm thử contract header giữa dịch vụ

Nên kiểm thử contract ở cả producer và consumer, không chỉ kiểm tra listener nhận được payload.

**Producer test** cần xác minh:

- Header bắt buộc đều có mặt.
- Tên header đúng chính tả và đúng chữ thường.
- Giá trị chuỗi được encode UTF-8.
- `event-id`, `event-type`, `schema-version` và `content-type` đúng contract.
- Header tùy chọn chỉ xuất hiện khi có giá trị hợp lệ.
- Không có header nhạy cảm hoặc header nội bộ bị phát ra.

**Consumer test** cần xác minh:

- Thiếu header bắt buộc bị phát hiện.
- Header đơn trị bị lặp bị từ chối.
- Header tùy chọn thiếu được xử lý đúng.
- Giá trị sai encoding hoặc sai format bị xử lý theo chính sách.
- Consumer bỏ qua header tùy chọn chưa biết nếu contract cho phép.
- Consumer tương thích với producer ở phiên bản trước trong giai đoạn rollout.

Ví dụ unit test kiểm tra helper đọc header đơn trị:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.apache.kafka.common.header.internals.RecordHeaders;
import org.junit.jupiter.api.Test;

class RequiredEventHeadersTest {

    @Test
    void readsSingleUtf8Header() {
        var headers = new RecordHeaders();
        headers.add(
            "event-id",
            EventHeaderValues.utf8("evt-1001")
        );

        assertThat(
            RequiredEventHeaders.requiredSingleUtf8(headers, "event-id")
        ).isEqualTo("evt-1001");
    }

    @Test
    void rejectsDuplicateSingletonHeader() {
        var headers = new RecordHeaders();
        headers.add("event-id", EventHeaderValues.utf8("evt-1"));
        headers.add("event-id", EventHeaderValues.utf8("evt-2"));

        assertThatThrownBy(
            () -> RequiredEventHeaders.requiredSingleUtf8(headers, "event-id")
        ).isInstanceOf(IllegalArgumentException.class);
    }
}
~~~

Integration test nên dùng Embedded Kafka hoặc Testcontainers để xác minh header qua broker vẫn giữ đúng tên, số lần xuất hiện và byte value. Đặc biệt, nếu dùng `Message<?>` cùng `DefaultKafkaHeaderMapper`, hãy kiểm tra record thực tế để bảo đảm cách encode header đúng contract của các dịch vụ không dùng Spring.

## 13. Checklist quy ước header dùng chung

- [ ] Có tài liệu contract tập trung cho tên, ý nghĩa và định dạng từng header.
- [ ] Tên header tùy chỉnh dùng lowercase ASCII và `kebab-case`.
- [ ] Quy định header bắt buộc, tùy chọn và cardinality.
- [ ] Chuỗi được encode/decode bằng UTF-8.
- [ ] `event-id`, `event-type`, `content-type`, `schema-version` có ý nghĩa thống nhất.
- [ ] Phân biệt `event-id`, `correlation-id`, `causation-id` và `traceparent`.
- [ ] Không dùng header thay cho Kafka key hoặc dữ liệu nghiệp vụ thiết yếu.
- [ ] Dùng tracing propagator để inject/extract trace context.
- [ ] Có quy trình thêm, deprecate và bỏ header tương thích ngược.
- [ ] Không đưa secret hoặc payload lớn vào header.
- [ ] Chỉ chuyển tiếp header theo allowlist.
- [ ] Kiểm thử header thực tế qua broker và giữa các phiên bản producer/consumer.

Quy ước header dùng chung giúp các dịch vụ hiểu metadata theo cùng một cách, từ định danh sự kiện đến tracing và versioning. Hãy xem header là một phần của contract liên dịch vụ: đặt tên ổn định, mã hóa rõ ràng, quy định cardinality và thay đổi theo lộ trình tương thích để hệ thống Spring Kafka dễ tích hợp và vận hành.
