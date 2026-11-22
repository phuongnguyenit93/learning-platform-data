# Thiết kế log có cấu trúc và mã tương quan sự kiện

Trong module **KAFKA**, người học xây dựng hệ thống event streaming với Apache Kafka, hiểu topic, partition, offset, producer, consumer group, replication và KRaft; triển khai luồng sự kiện Java/Spring Kafka, xử lý retry, ordering và giao dịch; tích hợp Kafka Connect/Streams rồi giám sát, tối ưu và phục hồi cụm. Bài học này hướng dẫn thiết kế log có cấu trúc và mã tương quan để theo dõi một sự kiện qua producer, Kafka broker, consumer, retry, dead-letter topic (DLT) và các hệ thống downstream.

Trong một hệ thống event streaming, producer và consumer thường chạy ở process, host hoặc service khác nhau. Một dòng log chỉ có message text như “publish success” hoặc “processing failed” không đủ để nối các hoạt động lại với nhau. Cần một schema log thống nhất, định danh sự kiện ổn định và quy ước truyền context qua Kafka record headers. Khi thiết kế đúng, người vận hành có thể lần theo event ID, correlation ID, trace ID và vị trí record để xác định sự kiện bắt đầu ở đâu, đã đi qua service nào và lỗi tại bước nào.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vì sao log text tự do khó tìm kiếm và tương quan trong hệ thống phân tán.
- Thiết kế JSON log schema có field ổn định và có version.
- Phân biệt eventId, correlationId, traceId, spanId, requestId và Kafka record key.
- Chọn nơi tạo correlation ID và cách truyền nó qua event flow.
- Dùng Kafka headers để mang correlation ID và trace context.
- Ghi log producer cùng topic, partition, offset từ RecordMetadata.
- Ghi log consumer cùng topic, partition, offset, group và event ID.
- Dùng MDC trong Java/Spring để tự động gắn context vào log.
- Xử lý MDC đúng với listener thread, async callback, executor và batch listener.
- Tương quan log qua retry, retry topic và DLT mà không làm mất metadata gốc.
- Bảo vệ log khỏi PII, secret, header injection và payload quá lớn.
- Kết hợp structured log, metrics và distributed tracing.
- Thiết kế truy vấn, dashboard, alert và kiểm thử correlation end-to-end.

## 2. Vì sao cần log có cấu trúc?

Log text truyền thống thường ghi thông tin thành một câu:

~~~text
2026-11-20 10:15:31 INFO OrderService Published order ORD-1001
2026-11-20 10:15:32 INFO PaymentConsumer Received order ORD-1001
2026-11-20 10:15:33 ERROR InventoryConsumer Failed to reserve stock
~~~

Người đọc có thể hiểu nội dung, nhưng hệ thống log khó trả lời nhất quán các câu hỏi:

- Các dòng log thuộc cùng một luồng nghiệp vụ có mã chung không?
- Record được publish vào topic, partition và offset nào?
- Consumer nào đã xử lý record?
- Đây là lần xử lý đầu hay retry lần thứ ba?
- Lỗi có xảy ra trước hay sau khi gọi database?
- Sự kiện được đưa sang DLT từ record gốc nào?
- Có thể lọc toàn bộ hoạt động theo một event ID mà không tìm theo nội dung message không?

Structured logging ghi log thành các field có kiểu và tên ổn định, thường ở dạng JSON:

~~~json
{
  "@timestamp": "2026-11-20T10:15:31.125Z",
  "severity": "INFO",
  "service.name": "orders-api",
  "service.version": "1.8.2",
  "event.name": "kafka.producer.send",
  "event.id": "evt-7f81a9",
  "correlation.id": "corr-order-1001",
  "trace.id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span.id": "00f067aa0ba902b7",
  "kafka.topic": "orders",
  "kafka.partition": 2,
  "kafka.offset": 18420,
  "outcome": "success"
}
~~~

Hệ thống log có thể lọc theo field, nhóm theo service, đếm lỗi theo event type hoặc nối các log cùng correlation ID. Việc tìm kiếm không phụ thuộc vào cách viết một câu message.

### 2.1. Log có cấu trúc không đồng nghĩa log đầy đủ mọi dữ liệu

Structured logging chuẩn hóa cách ghi nhận sự kiện vận hành. Nó không có nghĩa mọi request hoặc mọi Kafka record đều phải in toàn bộ payload.

Nên log metadata đủ để chẩn đoán:

- Loại hoạt động.
- Service và phiên bản.
- Event ID/correlation ID.
- Kafka topic, partition, offset khi đã biết.
- Thời gian, kết quả và thời lượng.
- Error type và thông tin lỗi đã được làm sạch.

Payload nghiệp vụ, thông tin định danh cá nhân, token và credential cần chính sách riêng. Trong nhiều hệ thống, log chỉ chứa một số business identifier đã được phân loại hoặc pseudonymize.

## 3. Phân biệt các mã định danh

Các ID có mục đích khác nhau. Dùng một ID thay cho tất cả sẽ làm mất ngữ nghĩa hoặc gây khó khăn khi điều tra.

| ID | Phạm vi | Mục đích | Ví dụ |
|---|---|---|---|
| eventId | Một event logic | Nhận diện duy nhất sự kiện, giữ ổn định qua retry/replay | evt-7f81a9 |
| correlationId | Một luồng nghiệp vụ | Nối nhiều event/request cùng một business operation | corr-order-1001 |
| traceId | Một distributed trace | Nối các span trong một trace | 4bf92f... |
| spanId | Một operation trong trace | Nhận diện một bước xử lý cụ thể | 00f067aa0ba902b7 |
| requestId | Một request tới service/API | Tìm log trong phạm vi request đó | req-82a1 |
| Kafka key | Định tuyến record | Chọn partition và hỗ trợ ordering theo key | order-1001 |
| topic/partition/offset | Vị trí record trong log | Định vị record Kafka đã được append | orders/2/18420 |

### 3.1. eventId

eventId nhận diện một event cụ thể. Nếu event được retry hoặc publish lại, nên giữ nguyên eventId để downstream có thể nhận ra cùng một sự kiện logic.

Ví dụ:

~~~text
OrderCreated event:
  eventId = evt-7f81a9

Retry lần 1:
  eventId = evt-7f81a9

Retry lần 2:
  eventId = evt-7f81a9
~~~

eventId hỗ trợ idempotency, deduplication và điều tra duplicate. Không dùng Kafka offset làm eventId vì offset chỉ có ý nghĩa trong một partition của một topic và có thể thay đổi khi record được republish.

### 3.2. correlationId

correlationId nối các hoạt động thuộc cùng một nghiệp vụ, kể cả khi nghiệp vụ tạo ra nhiều event hoặc đi qua nhiều service.

Ví dụ một yêu cầu checkout có thể tạo:

~~~text
CheckoutRequested
  -> OrderCreated
  -> PaymentRequested
  -> PaymentAuthorized
  -> InventoryReserved
  -> OrderConfirmed
~~~

Các event có eventId riêng nhưng có thể dùng chung correlationId để truy vấn toàn bộ hành trình checkout.

Nếu request đầu vào đã có correlation ID từ một gateway đáng tin cậy, service có thể tiếp tục dùng sau khi validate. Nếu không có, service đầu tiên trong hệ thống tạo ID mới. Không tin vô điều kiện một header do client Internet gửi lên: cần kiểm tra độ dài, ký tự, định dạng và tránh cho phép giá trị tùy ý làm nhiễu log.

### 3.3. traceId và spanId

traceId thuộc distributed tracing, thường theo chuẩn W3C Trace Context. Mỗi operation được biểu diễn bằng một span có spanId riêng.

- traceId nối các span trong cùng trace.
- spanId nhận diện một span.
- parent span hoặc span link thể hiện quan hệ giữa các bước.
- trace context có thể được truyền qua Kafka headers.

Một trace có thể kết thúc trong khi correlationId của nghiệp vụ tiếp tục tồn tại qua retry nhiều phút hoặc nhiều giờ. Vì vậy, correlationId và traceId không nên bị đồng nhất.

Với retry bất đồng bộ hoặc event được xử lý sau một khoảng thời gian dài, có thể tạo trace/span mới và dùng span link để nối với context ban đầu theo chính sách tracing của hệ thống. Correlation ID vẫn giữ nguyên để tra cứu nghiệp vụ.

### 3.4. Kafka key không phải correlation ID

Kafka key thường dùng để quyết định partition. Các record cùng key thường được route về cùng partition, giúp giữ thứ tự append trong partition đó.

Không chọn correlationId làm key một cách mặc định. Một correlationId có thể gom nhiều loại event và tạo hot partition nếu một nghiệp vụ phát ra quá nhiều record. Chọn key theo yêu cầu ordering, phân bố tải và semantics của dữ liệu.

## 4. Thiết kế JSON log schema

Một schema log thống nhất giúp service khác nhau ghi được dữ liệu tương thích.

Ví dụ schema đề xuất:

| Field | Kiểu | Ý nghĩa |
|---|---|---|
| @timestamp | string UTC ISO-8601 | Thời điểm log được tạo |
| severity | string | DEBUG, INFO, WARN, ERROR |
| service.name | string | Tên service |
| service.version | string | Phiên bản ứng dụng |
| deployment.environment | string | local, dev, staging, production |
| logger | string | Logger/class phát log |
| thread.name | string | Thread xử lý |
| event.name | string | Tên sự kiện vận hành |
| event.id | string | ID event nghiệp vụ |
| correlation.id | string | ID nối luồng nghiệp vụ |
| trace.id | string | Distributed trace ID |
| span.id | string | Span hiện tại |
| request.id | string | Request ID nếu có |
| kafka.topic | string | Topic |
| kafka.partition | integer | Partition |
| kafka.offset | integer | Offset |
| kafka.consumer.group | string | Consumer group |
| kafka.client.id | string | Kafka client ID |
| kafka.key_hash | string | Hash key nếu cần đối chiếu mà không lộ key |
| operation.duration_ms | number | Thời gian xử lý |
| outcome | string | success, failure, skipped, retried |
| error.type | string | Loại exception |
| error.message | string | Message đã được làm sạch |
| retry.attempt | integer | Lần thử hiện tại |
| code | string | Mã lỗi hoặc kết quả nghiệp vụ |

Tên field là quy ước của ứng dụng; có thể ánh xạ sang OpenTelemetry Logs hoặc schema của nền tảng log đang dùng. Chọn một naming convention thống nhất, tránh service này dùng correlationId, service khác dùng correlation_id và service thứ ba dùng requestCorrelation.

### 4.1. Version schema log

Nếu cần thay đổi schema, hãy có field version hoặc quản lý schema theo hợp đồng tập trung.

Ví dụ:

~~~json
{
  "log.schema.version": 1,
  "@timestamp": "2026-11-20T10:15:31.125Z",
  "severity": "INFO",
  "service.name": "orders-api",
  "event.name": "order.created",
  "event.id": "evt-7f81a9",
  "correlation.id": "corr-order-1001"
}
~~~

Không đổi ý nghĩa một field đã tồn tại mà không có kế hoạch migration. Ví dụ correlation.id phải luôn là business correlation ID; không lúc thì ghi trace ID, lúc thì ghi request ID.

### 4.2. Field bắt buộc và field tùy chọn

Không phải mọi log đều có Kafka metadata. Log trước khi producer gửi record chưa có offset; log ở HTTP entry point có thể chưa có eventId.

Có thể phân loại:

- Field nền tảng: timestamp, severity, service.name, event.name.
- Field correlation: event.id, correlation.id, trace.id, span.id, request.id.
- Field Kafka: topic, partition, offset, group, client.id.
- Field kết quả: outcome, duration, error.
- Field retry: retry.attempt, original topic/partition/offset.

Field chưa biết nên được bỏ qua hoặc để null theo schema policy; không gán giá trị giả như offset 0 để lấp chỗ trống.

## 5. Tạo và truyền correlation ID

Có hai cách phổ biến để tạo correlation ID:

1. Tạo tại API gateway hoặc entry service khi bắt đầu business flow.
2. Tạo tại service đầu tiên nếu request chưa có ID đáng tin cậy.

ID có thể dùng UUID ngẫu nhiên hoặc định dạng opaque khác. Không nhúng email, số điện thoại, access token hoặc dữ liệu cá nhân vào correlation ID.

### 5.1. Quy tắc truyền

- Giữ correlationId ổn định qua các event thuộc cùng business flow.
- Tạo eventId mới cho mỗi event logic mới.
- Không tạo correlationId mới mỗi khi retry cùng một event.
- Truyền trace context theo chuẩn tracing riêng.
- Kiểm tra header trùng lặp và quy định cách chọn giá trị.
- Giới hạn độ dài header và ký tự hợp lệ.
- Không dùng correlationId làm cơ chế xác thực hoặc phân quyền.

### 5.2. Kafka record headers

Kafka record hỗ trợ headers dưới dạng danh sách cặp key/value bytes. Ứng dụng có thể mang correlation ID và trace context qua headers mà không phải sửa business payload.

Ví dụ header convention:

| Header | Nội dung |
|---|---|
| x-correlation-id | Business correlation ID |
| x-event-id | Event ID |
| traceparent | W3C trace context |
| tracestate | W3C vendor trace state nếu có |
| x-request-id | Request ID từ API nếu cần |
| x-schema-version | Version event contract nếu ứng dụng dùng quy ước này |

Tên header là convention của hệ thống. Trước khi tạo convention mới cho traceparent hoặc tracestate, hãy kiểm tra instrumentation đang dùng để tránh ghi đè hoặc tạo duplicate header.

### 5.3. Producer thêm header

Ví dụ Java Kafka Producer:

~~~java
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.header.Headers;

import java.nio.charset.StandardCharsets;

public class OrderEventPublisher {

    public ProducerRecord<String, String> createRecord(
            String topic,
            String key,
            String payload,
            String eventId,
            String correlationId) {

        ProducerRecord<String, String> record =
            new ProducerRecord<>(topic, key, payload);

        Headers headers = record.headers();

        headers.add(
            "x-event-id",
            eventId.getBytes(StandardCharsets.UTF_8)
        );

        headers.add(
            "x-correlation-id",
            correlationId.getBytes(StandardCharsets.UTF_8)
        );

        return record;
    }
}
~~~

Nếu dùng OpenTelemetry instrumentation, để instrumentation inject traceparent/tracestate theo cơ chế tương thích. Không tự tạo traceparent ngẫu nhiên vì format này chứa trace ID, parent span ID và trace flags theo chuẩn W3C.

## 6. Đọc correlation ID ở consumer

Consumer nhận Kafka record cùng headers. Cần xử lý trường hợp header thiếu, null, trùng hoặc có giá trị không hợp lệ.

Ví dụ helper đọc header:

~~~java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.header.Header;

import java.nio.charset.StandardCharsets;

public final class KafkaHeaderReader {

    private KafkaHeaderReader() {
    }

    public static String readLast(
            ConsumerRecord<?, ?> record,
            String name) {

        Header header = record.headers().lastHeader(name);

        if (header == null || header.value() == null) {
            return null;
        }

        return new String(
            header.value(),
            StandardCharsets.UTF_8
        );
    }
}
~~~

Kafka headers có thể chứa nhiều header cùng tên. Ví dụ trên chọn header cuối cùng. Hệ thống cần thống nhất duplicate-header policy: từ chối record, lấy giá trị đầu/cuối hoặc ghi nhận lỗi. Không để mỗi consumer tự chọn cách khác nhau.

### 6.1. Fallback khi header thiếu

Nếu correlation ID thiếu:

- Tạo ID mới tại boundary nếu đây là luồng mới.
- Nếu consumer đang xử lý event đã tồn tại, có thể dùng eventId làm khóa điều tra cục bộ nhưng cần đánh dấu rằng correlation ID gốc bị thiếu.
- Ghi metric thiếu header.
- Không dùng chuỗi rỗng hoặc giá trị chung như unknown cho mọi event trong truy vấn vì sẽ gom tất cả record thành một luồng giả.

Nếu eventId cũng thiếu, ghi nhận lỗi contract và áp dụng policy validation/retry/DLT phù hợp.

## 7. Log producer: từ send đến broker acknowledgement

Producer có thể log hai giai đoạn:

1. Bắt đầu gửi record.
2. Nhận kết quả send thành công hoặc thất bại.

Trước khi broker xác nhận, producer chưa biết offset cuối cùng. Khi send thành công, callback nhận RecordMetadata chứa topic, partition, offset và timestamp.

### 7.1. Producer callback

Ví dụ với Java Producer API:

~~~java
import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.clients.producer.RecordMetadata;

public class ProducerLoggingExample {

    public void send(
            KafkaProducer<String, String> producer,
            ProducerRecord<String, String> record,
            String eventId,
            String correlationId) {

        producer.send(record, (RecordMetadata metadata, Exception error) -> {
            if (error != null) {
                // Log eventId/correlationId cùng error type.
                // Không log toàn bộ payload hoặc secret.
                logFailure(eventId, correlationId, error);
                return;
            }

            logSuccess(
                eventId,
                correlationId,
                metadata.topic(),
                metadata.partition(),
                metadata.offset(),
                metadata.timestamp()
            );
        });
    }

    private void logFailure(
            String eventId,
            String correlationId,
            Exception error) {
        // Thay bằng structured logger của ứng dụng.
    }

    private void logSuccess(
            String eventId,
            String correlationId,
            String topic,
            int partition,
            long offset,
            long timestamp) {
        // Thay bằng structured logger của ứng dụng.
    }
}
~~~

Ví dụ chỉ minh họa vị trí ghi log; các hàm logSuccess/logFailure cần triển khai bằng logger JSON của dự án.

### 7.2. Không log hai lần cùng một ý nghĩa

Một producer có thể log “send started”, callback log “send completed” và framework cũng log retry. Đặt event.name khác nhau để phân biệt:

- kafka.producer.send.started
- kafka.producer.send.acknowledged
- kafka.producer.send.failed

Không dùng một message chung “sent” cho cả lúc bắt đầu và lúc đã nhận acknowledgement.

### 7.3. Đo thời gian gửi

Đo duration từ lúc gọi send đến lúc callback hoàn tất. Nếu producer retry nội bộ, thời gian này có thể gồm nhiều lần gửi. Ghi rõ đây là application-observed send duration, không phải thời gian broker xử lý riêng lẻ.

## 8. Log consumer: nhận, xử lý và hoàn tất

Consumer cần ghi lại vị trí record và kết quả nghiệp vụ. Một log “received” không có nghĩa xử lý đã hoàn tất hoặc offset đã commit.

Các mốc nên phân biệt:

- Record được poll.
- Bắt đầu xử lý.
- Business operation hoàn tất.
- Offset được commit hoặc transaction hoàn tất.
- Record được retry, recover hoặc chuyển DLT.

### 8.1. ConsumerRecord metadata

Record metadata gồm:

- topic.
- partition.
- offset.
- timestamp.
- key.
- headers.

Consumer group và client.id là thuộc tính consumer/application, không nằm trực tiếp trong ConsumerRecord. Đưa chúng vào log từ context cấu hình hoặc instrumentation.

### 8.2. Spring Kafka listener

Ví dụ listener nhận ConsumerRecord:

~~~java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderConsumer {

    @KafkaListener(
        topics = "orders",
        groupId = "order-projection"
    )
    public void consume(ConsumerRecord<String, String> record) {
        String eventId =
            KafkaHeaderReader.readLast(record, "x-event-id");

        String correlationId =
            KafkaHeaderReader.readLast(record, "x-correlation-id");

        logReceived(
            eventId,
            correlationId,
            record.topic(),
            record.partition(),
            record.offset()
        );

        processOrder(record.value());

        logProcessed(
            eventId,
            correlationId,
            record.topic(),
            record.partition(),
            record.offset()
        );
    }

    private void processOrder(String payload) {
        // Validate và xử lý nghiệp vụ.
    }

    private void logReceived(
            String eventId,
            String correlationId,
            String topic,
            int partition,
            long offset) {
        // Ghi JSON log với metadata.
    }

    private void logProcessed(
            String eventId,
            String correlationId,
            String topic,
            int partition,
            long offset) {
        // Ghi JSON log sau khi business processing thành công.
    }
}
~~~

Nếu processOrder ném exception, log processed không được ghi. Error handler của Spring Kafka có thể retry hoặc chuyển record sang DLT; log retry/recovery cần giữ eventId, correlationId và vị trí record gốc.

### 8.3. Received không phải committed

Consumer có thể đã poll và xử lý record nhưng chưa commit offset. Nếu process crash trước commit, record có thể được đọc lại. Vì vậy:

- received: consumer đã nhận record.
- processed: business handler đã hoàn tất theo logic ứng dụng.
- committed: offset đã được commit theo consumer semantics.

Không dùng một log “success” chung cho cả ba mốc. Nếu cần xác minh exactly-once hoặc transaction, phải kết hợp log với transaction/commit behavior và trạng thái downstream.

## 9. Dùng MDC để tự động gắn context vào log

MDC (Mapped Diagnostic Context) của SLF4J/Logback lưu các field theo thread để logger có thể tự thêm chúng vào mỗi log event.

Ví dụ:

~~~java
import org.slf4j.MDC;

public void processWithMdc(
        String eventId,
        String correlationId,
        Runnable action) {

    String previousEventId = MDC.get("event.id");
    String previousCorrelationId = MDC.get("correlation.id");

    try {
        MDC.remove("event.id");
        MDC.remove("correlation.id");

        if (eventId != null) {
            MDC.put("event.id", eventId);
        }

        if (correlationId != null) {
            MDC.put("correlation.id", correlationId);
        }

        action.run();

    } finally {
        if (previousEventId == null) {
            MDC.remove("event.id");
        } else {
            MDC.put("event.id", previousEventId);
        }

        if (previousCorrelationId == null) {
            MDC.remove("correlation.id");
        } else {
            MDC.put("correlation.id", previousCorrelationId);
        }
    }
}
~~~

Dùng finally để xóa context. Kafka listener thread thường được tái sử dụng cho nhiều record; nếu không xóa MDC, record sau có thể bị gắn ID của record trước.

### 9.1. MDC là thread-local

MDC không tự động truyền sang thread khác trong mọi executor hoặc callback. Khi xử lý bất đồng bộ:

1. Capture MDC context trước khi submit task.
2. Chuyển context sang thread thực thi.
3. Khôi phục context cũ sau khi task hoàn tất.
4. Xóa hoặc restore trong finally.

Không dùng MDC như một kho context toàn cục. Với reactive pipeline hoặc virtual thread, kiểm tra cơ chế context propagation của framework và phiên bản đang dùng.

### 9.2. Filter/interceptor cho Spring Kafka

Có thể đặt MDC tại một lớp boundary chung như RecordInterceptor hoặc listener wrapper để không lặp code trong mọi listener. Khi chọn cơ chế này, cần kiểm tra:

- Listener record và batch listener.
- Exception trước/sau listener invocation.
- Retry và DLT listener.
- Async listener hoặc handoff sang executor.
- Context được cleanup khi listener ném exception.

Không giữ MDC qua nhiều record trong batch bằng cách chỉ set một lần nếu mỗi record có eventId/correlationId khác nhau. Batch logging có thể ghi batch ID và số lượng, sau đó log riêng những record lỗi theo policy.

## 10. Cấu hình JSON logging trong Java/Spring

Một cách phổ biến là dùng Logback encoder để phát log JSON. Tên dependency và cấu hình chi tiết phụ thuộc phiên bản Spring Boot/Logback/encoder; cần chọn version tương thích với dependency tree của dự án.

Ví dụ cấu hình Logback:

~~~xml
<configuration>
    <appender name="JSON_CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder class="net.logstash.logback.encoder.LogstashEncoder">
            <includeMdcKeyName>event.id</includeMdcKeyName>
            <includeMdcKeyName>correlation.id</includeMdcKeyName>
            <includeMdcKeyName>trace.id</includeMdcKeyName>
            <includeMdcKeyName>span.id</includeMdcKeyName>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="JSON_CONSOLE"/>
    </root>
</configuration>
~~~

Cấu hình trên minh họa cách đưa MDC vào JSON. Nếu dùng OpenTelemetry Logback appender hoặc Spring Boot structured logging tích hợp, hãy chọn một pipeline chính và tránh xuất hai bản log trùng nhau.

### 10.1. Ví dụ dependency

Với Gradle, thêm encoder tương thích với Logback đang dùng:

~~~groovy
dependencies {
    implementation("net.logstash.logback:logstash-logback-encoder:<compatible-version>")
}
~~~

Không dùng placeholder version trong build production. Pin version đã được kiểm tra với Spring Boot và Logback của dự án.

### 10.2. Log level và volume

- ERROR: thao tác thất bại cần xử lý hoặc điều tra.
- WARN: dữ liệu bất thường, retry, fallback hoặc tình huống có thể phục hồi.
- INFO: mốc nghiệp vụ/vận hành quan trọng, không phải mọi record ở throughput cao.
- DEBUG: chi tiết chẩn đoán trong môi trường hoặc thời gian giới hạn.
- TRACE: chỉ bật có kiểm soát khi thực sự cần.

Không ghi một INFO log cho mọi record nếu topic có hàng triệu record mỗi phút. Dùng metric cho số lượng/throughput, sampling cho log chi tiết và chỉ log từng event khi có nhu cầu điều tra.

## 11. Truyền trace context qua Kafka

Correlation ID phục vụ truy vấn business flow. Trace context phục vụ distributed tracing. Khi dùng OpenTelemetry hoặc tracing framework, producer thường inject trace context vào Kafka headers và consumer extract để tạo quan hệ span.

Với W3C Trace Context, các header phổ biến là:

- traceparent.
- tracestate.

Baggage có thể truyền thêm metadata nhưng cần giới hạn field, kích thước và dữ liệu được phép chia sẻ. Không đưa PII hoặc secret vào baggage.

### 11.1. Producer và consumer span

Một luồng minh họa:

~~~mermaid
flowchart LR
    A[HTTP request span] --> B[Producer send span]
    B --> K[(Kafka topic)]
    K --> C[Consumer process span]
    C --> D[Database span]
    C --> E[Downstream publish span]
~~~

Instrumentation có thể tạo producer/consumer span tự động. Nếu tự tạo span thủ công, phải theo đúng semantic convention của phiên bản OpenTelemetry đang dùng để tránh span trùng hoặc sai quan hệ parent/link.

### 11.2. Fan-out và fan-in

Một event có thể kích hoạt nhiều consumer độc lập. Mỗi nhánh có span riêng nhưng vẫn có thể chia sẻ correlation ID. Khi nhiều nhánh hội tụ, trace có thể dùng span links thay vì ép mọi nhánh thành một chuỗi parent-child giả tạo.

Correlation ID vẫn giúp truy vấn toàn bộ nghiệp vụ dù các nhánh chạy song song hoặc trace bị sampling.

### 11.3. Trace sampling và log correlation

Một trace có thể không được export do sampling hoặc exporter lỗi. Log có traceId vẫn hữu ích để tìm kiếm, nhưng không bảo đảm backend có đủ span tương ứng.

Không phụ thuộc duy nhất vào trace backend. Giữ eventId/correlationId trong structured log và Kafka headers để có đường truy vết khác.

## 12. Retry, retry topic và DLT

Retry làm một event có nhiều lần xử lý. Nếu mỗi lần retry tạo eventId hoặc correlationId mới, việc nối các lần thử trở nên khó khăn và downstream có thể hiểu nhầm đó là event mới.

Quy ước khuyến nghị:

- Giữ nguyên eventId cho cùng event logic.
- Giữ nguyên correlationId cho cùng business flow.
- Ghi retry.attempt riêng.
- Ghi original topic, partition, offset.
- Ghi tên retry topic hoặc DLT hiện tại.
- Ghi error.type và exception class đã làm sạch.
- Trace context có thể tiếp tục hoặc tạo trace mới với link theo retry policy.

### 12.1. Log retry

Ví dụ JSON:

~~~json
{
  "@timestamp": "2026-11-20T10:18:00.100Z",
  "severity": "WARN",
  "service.name": "inventory-consumer",
  "event.name": "kafka.consumer.retry",
  "event.id": "evt-7f81a9",
  "correlation.id": "corr-order-1001",
  "kafka.topic": "orders",
  "kafka.partition": 2,
  "kafka.offset": 18420,
  "retry.attempt": 2,
  "outcome": "retry_scheduled",
  "error.type": "InventoryUnavailableException"
}
~~~

Không log toàn bộ stack trace cho mọi retry ở mức ERROR nếu hệ thống có retry liên tục; có thể tạo lượng log rất lớn. Ghi WARN có sampling/rate limit và ghi ERROR khi exhausted hoặc chuyển DLT.

### 12.2. DLT cần giữ metadata gốc

Khi record được publish sang DLT, topic/partition/offset mới là vị trí của bản DLT. Muốn tìm record gốc, cần giữ metadata nguồn trong header hoặc envelope.

Các field nên có:

- original.topic.
- original.partition.
- original.offset.
- original.timestamp.
- event.id.
- correlation.id.
- retry.attempt.
- error.type.
- error.message đã redact.
- failed.at hoặc thời điểm đưa vào DLT.

Framework có thể tự thêm một số header exception/original record. Hãy kiểm tra cấu hình DeadLetterPublishingRecoverer hoặc cơ chế DLT tương ứng; tránh tự thêm header trùng hoặc vô tình chuyển secret sang DLT.

### 12.3. Log DLT và thao tác replay

Khi operator replay DLT:

- Giữ eventId để idempotency.
- Giữ correlationId để nối business flow.
- Ghi replay.request.id và actor.
- Ghi source DLT topic/partition/offset.
- Ghi target topic và kết quả publish.
- Không sửa event payload âm thầm.
- Nếu phải sửa payload, ghi rõ transformation/version và tạo audit event.

Replay là một thao tác vận hành có side effect, nên có audit riêng thay vì chỉ log như một consumer bình thường.

## 13. Tương quan end-to-end

Một hành trình event có thể được theo dõi bằng nhiều lớp ID và metadata.

~~~mermaid
sequenceDiagram
    participant API as Orders API
    participant K as Kafka
    participant P as Payment Consumer
    participant I as Inventory Consumer
    participant D as DLT

    API->>API: Create eventId and correlationId
    API->>K: Publish OrderCreated + headers
    K-->>API: topic/partition/offset ACK
    K->>P: Deliver record
    P->>P: Log received and process
    P->>K: Publish PaymentRequested
    K->>I: Deliver record
    I->>I: Process, retry on failure
    I->>D: Publish after retries exhausted
    Note over API,D: eventId and correlationId connect the business flow
~~~

Ví dụ truy vấn:

1. Tìm correlation.id = corr-order-1001.
2. Xem các event.id theo thứ tự thời gian.
3. Lọc theo service.name để xác định service gây lỗi.
4. Dùng trace.id để mở distributed trace nếu có.
5. Dùng kafka.topic + partition + offset để định vị record.
6. Kiểm tra retry.attempt và DLT metadata nếu event thất bại.
7. Đối chiếu request ID hoặc business order ID nếu được phép.

Không sắp xếp toàn bộ log chỉ theo Kafka offset vì offset chỉ so sánh được trong cùng partition. Với nhiều partition/service, dùng timestamp, trace/span relationship và event sequence nghiệp vụ.

## 14. Bảo vệ log và correlation metadata

Log và Kafka headers đều có thể chứa dữ liệu do client hoặc producer bên ngoài gửi. Không coi header là trusted input.

### 14.1. Tránh log dữ liệu nhạy cảm

Không ghi:

- Password, SASL JAAS config.
- OAuth access/refresh token.
- Private key hoặc certificate secret.
- Authorization header hoặc cookie.
- Toàn bộ payload chứa PII nếu không có nhu cầu và cơ sở phù hợp.
- Thông tin thanh toán hoặc dữ liệu định danh vượt quá mức cần thiết.

Nếu cần đối chiếu customer ID, cân nhắc HMAC hoặc tokenization với key được bảo vệ thay vì hash thường có thể dò ngược bằng dictionary.

### 14.2. Chống log injection

Header có thể chứa ký tự xuống dòng, tab hoặc chuỗi rất dài. Trước khi ghi log:

- Giới hạn độ dài.
- Kiểm tra encoding.
- Loại bỏ hoặc escape ký tự điều khiển.
- Dùng JSON encoder đúng chuẩn thay vì nối chuỗi thủ công.
- Không cho phép header ghi đè các field hệ thống như service.name hoặc severity.
- Ghi nhận header duplicate theo policy.

Không dùng giá trị correlation ID không kiểm tra làm tên logger, metric label hoặc tên file.

### 14.3. Giới hạn cardinality

eventId, correlationId và traceId có độ đa dạng rất cao. Chúng phù hợp để tìm log/trace nhưng thường không phù hợp làm metric label vì tạo cardinality lớn và làm tăng chi phí backend.

Metric nên dùng label có tập giá trị giới hạn như service, topic, outcome, error.type đã chuẩn hóa. ID cụ thể để trong log hoặc trace.

### 14.4. Quyền truy cập và retention

Log có thể chứa dữ liệu nhạy cảm ngay cả khi payload không được ghi trực tiếp. Cần:

- RBAC cho log search và export.
- Retention theo mục đích và chính sách dữ liệu.
- Encryption in transit và at rest.
- Audit thao tác tìm kiếm/export khi dữ liệu nhạy cảm.
- Redaction ở application trước khi gửi.
- Kiểm soát quyền truy cập DLT và retry topic.

## 15. Logging trong Kafka Streams

Kafka Streams xử lý record qua topology, có thể đổi key, aggregate, join và tạo internal topic. Nên giữ event/correlation context qua các bước biến đổi khi còn ý nghĩa.

Gợi ý:

- Log ở boundary input khi nhận event.
- Log ở boundary output khi publish kết quả.
- Dùng eventId/correlationId trong payload hoặc headers theo event contract.
- Giữ trace context theo instrumentation hoặc processor policy.
- Không log từng bước map/filter stateless ở INFO.
- Với aggregate, log key/aggregate window và kết quả theo sampling.
- Với lỗi record, ghi topic/partition/offset và exception class.
- Với repartition, dùng topology description và metrics để quan sát; không cần log từng internal record.

Một aggregate có thể đại diện cho nhiều event đầu vào. Nếu cần truy vết từng event đóng góp, hãy thiết kế event lineage hoặc audit riêng; không thể suy ra đầy đủ eventId nguồn chỉ từ giá trị aggregate cuối.

## 16. Logging trong Kafka Connect

Kafka Connect worker và connector có log riêng. Khi điều tra một record đi qua source/sink connector, nên nối:

- Connector name.
- Task ID.
- Worker ID.
- Source system hoặc sink destination.
- Kafka topic/partition/offset nếu có.
- Event ID/correlation ID trong record/header nếu connector bảo toàn.
- Error class, retry state và DLQ metadata nếu cấu hình hỗ trợ.

Không phải connector/plugin nào cũng bảo toàn mọi header hoặc metadata giống nhau. Hãy kiểm tra converter, SMT, connector behavior và DLQ configuration thực tế.

REST API thao tác connector cần audit actor, action, connector name, before/after config đã redact và request ID. Worker log chỉ là một nguồn bằng chứng; nên nối với audit gateway hoặc management plane.

## 17. Chọn log level, sampling và metric

Structured log không thay thế metric. Mỗi loại tín hiệu trả lời một nhóm câu hỏi:

| Tín hiệu | Câu hỏi phù hợp |
|---|---|
| Log | Event cụ thể nào thất bại và metadata nào liên quan? |
| Metric | Tỷ lệ lỗi, throughput, latency và backlog thay đổi ra sao? |
| Trace | Một request/event đi qua những service/span nào và mất bao lâu? |
| Audit | Ai đã thực hiện thao tác quản trị hoặc truy cập nhạy cảm? |

### 17.1. Khi nào ghi từng record?

Ghi log mỗi record có thể hữu ích trong lab hoặc lưu lượng thấp. Với throughput cao, chi phí CPU, network, storage và index có thể rất lớn.

Có thể chọn:

- INFO cho mốc business quan trọng.
- WARN cho retry hoặc dữ liệu bất thường.
- ERROR cho xử lý thất bại cuối cùng.
- DEBUG có thời hạn để điều tra.
- Sampling cho log chi tiết theo tỷ lệ.
- Metric cho throughput, retry count và error rate.

Nếu sample log, không được dùng mẫu đó làm bằng chứng đầy đủ rằng mọi record đã được xử lý. Với yêu cầu audit, cần một cơ chế ghi nhận riêng có durability và retention phù hợp.

### 17.2. Metric nên có

- kafka_producer_send_total theo outcome.
- kafka_producer_send_duration_ms histogram.
- kafka_consumer_process_total theo outcome.
- kafka_consumer_process_duration_ms histogram.
- kafka_consumer_retry_total theo error class đã chuẩn hóa.
- kafka_consumer_dlt_total theo topic/error category.
- kafka_correlation_header_missing_total.
- kafka_event_duplicate_total nếu có deduplication.
- kafka_event_processing_lag_ms.
- kafka_log_dropped_total nếu logging pipeline có thể drop event.

Không đưa eventId/correlationId vào label. Dùng topic, service, outcome và error category có giới hạn cardinality.

## 18. Truy vấn log và dashboard

Một dashboard vận hành nên có:

1. Producer send success/failure theo service và topic.
2. Consumer process success/failure theo group.
3. Retry và DLT count theo error type.
4. Processing duration p50/p95/p99.
5. Event-time lag hoặc end-to-end age theo định nghĩa thống nhất.
6. Số record thiếu eventId/correlationId.
7. Top service phát sinh lỗi.
8. Log ingestion delay và dropped log events.
9. Trace link hoặc correlation search link từ log record.

Ví dụ truy vấn dạng giả lập theo cú pháp của hệ thống log:

~~~text
correlation.id = "corr-order-1001"
AND deployment.environment = "production"
~~~

Tìm event thất bại:

~~~text
event.name = "kafka.consumer.process"
AND outcome = "failure"
AND kafka.topic = "orders"
~~~

Tìm retry vượt ngưỡng:

~~~text
event.name = "kafka.consumer.retry"
AND retry.attempt >= 3
~~~

Cú pháp truy vấn thực tế phụ thuộc Elasticsearch, OpenSearch, Loki, Splunk hoặc nền tảng đang dùng. Điều quan trọng là field name và type phải nhất quán giữa các service.

## 19. Kiểm thử correlation end-to-end

Không chỉ unit test helper đọc header. Cần kiểm thử toàn bộ đường đi của một event.

### 19.1. Unit test

Kiểm tra:

- Header có giá trị hợp lệ.
- Header thiếu.
- Header value null.
- Header trùng tên.
- Encoding không hợp lệ.
- Giá trị quá dài.
- Ký tự điều khiển.
- MDC được cleanup sau success và exception.

### 19.2. Integration test

Một bài test có thể:

1. Tạo event với eventId và correlationId xác định.
2. Publish qua KafkaTemplate.
3. Consumer đọc record và log metadata.
4. Consumer phát event downstream.
5. Cố ý gây lỗi để kích hoạt retry.
6. Chuyển record sang DLT.
7. Kiểm tra eventId/correlationId được giữ.
8. Kiểm tra original topic/partition/offset có thể truy vết.
9. Kiểm tra log không chứa payload/secret nhạy cảm.
10. Kiểm tra metric retry/DLT tăng đúng.

Với Testcontainers hoặc Kafka broker test, xác minh metadata thật từ RecordMetadata và ConsumerRecord. Unit test đơn lẻ không kiểm tra được toàn bộ serialization, header propagation và listener lifecycle.

### 19.3. Kiểm thử async context

Tạo một test dùng executor để xác nhận MDC không bị mất hoặc rò từ task trước sang task sau. Sau mỗi task, kiểm tra thread không còn eventId/correlationId cũ.

Với reactive pipeline, kiểm tra context propagation theo thư viện và instrumentation đang dùng; MDC thread-local truyền thống không tự đại diện cho reactive context.

## 20. Troubleshooting

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Không tìm được log producer và consumer cùng event | Header không được inject hoặc consumer không đọc | Kiểm tra ProducerRecord headers và ConsumerRecord |
| correlationId thay đổi ở retry | Retry code tạo ID mới | Giữ correlationId và eventId gốc |
| eventId bị trùng giữa event mới | ID được tạo từ orderId hoặc key | Sinh eventId riêng cho từng event logic |
| Nhiều event bị gom vào một correlation | Dùng giá trị mặc định unknown hoặc ID rỗng | Tạo ID tại boundary và validate header |
| MDC của record trước xuất hiện ở record sau | Không cleanup MDC trong finally | Luôn restore/remove context |
| MDC mất trong callback async | Thread-local không được truyền sang executor | Capture và restore context |
| Log producer không có offset | Ghi trước callback acknowledgement | Ghi metadata sau send completion |
| Log consumer báo success nhưng record bị đọc lại | Nhầm processed với committed | Tách log processing và offset commit |
| DLT không tìm được record gốc | Không lưu original topic/partition/offset | Bảo toàn metadata gốc trong header |
| Log JSON parse lỗi | Payload log hoặc message chưa được encode đúng | Dùng JSON encoder và kiểm tra schema |
| Log volume tăng đột biến | INFO mỗi record hoặc retry log lặp | Sampling, rate limit và metric |
| Trace không nối qua Kafka | Instrumentation không inject/extract context | Kiểm tra trace headers và agent/framework |
| Trace không tồn tại nhưng correlation vẫn có | Sampling hoặc exporter không ghi trace | Tìm bằng correlation/event ID và log |
| Header chứa dữ liệu nhạy cảm | Producer đưa token/PII vào headers | Redact, allowlist và sửa event contract |
| Tìm kiếm chậm | Field không được index hoặc schema không thống nhất | Chuẩn hóa field mapping và retention |

## 21. Checklist production

Trước khi đưa structured logging và correlation vào production, hãy xác nhận:

1. Có JSON log schema chung cho các service không?
2. Có field version và naming convention ổn định không?
3. eventId có duy nhất cho từng event logic không?
4. correlationId có ổn định qua retry và downstream event không?
5. traceId/spanId có tuân theo tracing framework không?
6. Kafka key có được chọn theo ordering/partitioning thay vì tùy tiện dùng correlationId không?
7. Header convention có được tài liệu hóa không?
8. Có policy cho header thiếu, duplicate, null và quá dài không?
9. Producer log có RecordMetadata sau acknowledgement không?
10. Consumer log có topic, partition, offset và group không?
11. Received, processed và committed có được phân biệt không?
12. MDC có cleanup trong finally không?
13. Async callback/executor có context propagation không?
14. Retry/DLT có giữ eventId, correlationId và original location không?
15. Log có redact PII, token, password và private key không?
16. Có chống log injection và giới hạn kích thước field không?
17. ID có bị dùng làm metric label gây cardinality cao không?
18. Có sampling/rate limit cho log throughput cao không?
19. Log pipeline có retention, RBAC và encryption không?
20. Có integration test nối producer, consumer, retry và DLT không?

## 22. Bài tập thực hành

### Bài 1: Thiết kế log schema

1. Chọn một luồng OrderCreated.
2. Định nghĩa field nền tảng, business và Kafka metadata.
3. Tạo JSON log cho producer send started và acknowledged.
4. Tạo JSON log cho consumer received và processed.
5. Thêm schema version.
6. Giải thích vì sao không ghi toàn bộ payload.

### Bài 2: Truyền correlation ID qua Kafka headers

1. Tạo correlationId tại REST entry point.
2. Tạo eventId mới cho OrderCreated.
3. Thêm x-correlation-id và x-event-id vào ProducerRecord.
4. Consumer đọc headers.
5. Publish PaymentRequested và giữ correlationId.
6. Kiểm tra eventId của event downstream là ID mới.

### Bài 3: Dùng MDC trong Spring Kafka

1. Tạo helper set/remove MDC.
2. Gọi helper trong listener.
3. Cấu hình JSON encoder.
4. Gây exception trong listener.
5. Xác nhận MDC được cleanup.
6. Xử lý hai record liên tiếp trên cùng listener thread và kiểm tra không rò context.

### Bài 4: Tương quan retry và DLT

1. Cấu hình retry cho consumer.
2. Tạo event lỗi có eventId/correlationId.
3. Ghi retry.attempt.
4. Cho event hết retry và đi vào DLT.
5. Kiểm tra original topic/partition/offset.
6. Replay event và giữ eventId/correlationId.
7. Ghi actor và replay.request.id.

### Bài 5: Nối trace và log

1. Bật OpenTelemetry instrumentation phù hợp.
2. Gửi trace context qua Kafka headers.
3. Consumer extract context.
4. Tạo log có traceId/spanId/correlationId.
5. Tìm log theo correlationId.
6. Mở trace theo traceId.
7. Thử sampling và giải thích vì sao log vẫn có thể tìm thấy khi trace không được export.

### Bài 6: Kiểm tra an toàn log

1. Gửi header có chuỗi dài và ký tự xuống dòng.
2. Gửi payload có token giả lập.
3. Kiểm tra log output.
4. Bổ sung length limit, escaping và redaction.
5. Xác nhận metric labels không chứa eventId/correlationId.
6. Kiểm tra quyền truy cập và retention của log backend.

## 23. Câu hỏi tự kiểm tra

1. Vì sao structured logging dễ truy vấn hơn log text tự do?
2. eventId và correlationId khác nhau như thế nào?
3. traceId và spanId dùng để làm gì?
4. Vì sao Kafka offset không phải eventId?
5. Kafka key có vai trò gì và vì sao không mặc định dùng correlationId làm key?
6. Khi nào nên tạo correlationId?
7. Vì sao không tin vô điều kiện correlation header từ client?
8. Kafka record headers có thể mang những loại metadata nào?
9. Vì sao producer chỉ biết offset sau acknowledgement?
10. ConsumerRecord cung cấp metadata gì cho log?
11. Received, processed và committed khác nhau thế nào?
12. MDC là gì và vì sao phải cleanup trong finally?
13. Vì sao MDC có thể mất trong async callback?
14. Retry nên giữ eventId và correlationId như thế nào?
15. Vì sao DLT cần original topic/partition/offset?
16. Trace context khác business correlation như thế nào?
17. Vì sao không dùng eventId làm metric label?
18. Những field nào không nên ghi vào log?
19. Kafka Streams aggregate có thể giữ lineage event như thế nào?
20. Cần kiểm thử gì để xác nhận correlation end-to-end?

## Kết luận

Structured logging cung cấp schema field ổn định để truy vấn và phân tích hoạt động của các service. eventId nhận diện một event logic, correlationId nối một business flow, traceId/spanId nối distributed trace, còn topic/partition/offset định vị record trong Kafka log. Các ID này bổ sung cho nhau và không nên dùng thay thế nhau.

Kafka headers là kênh phù hợp để truyền correlation ID và trace context giữa producer và consumer. Producer nên ghi RecordMetadata sau acknowledgement; consumer nên ghi vị trí record cùng event ID, correlation ID và kết quả xử lý. Với Spring Kafka, MDC giúp tự động gắn context vào log nhưng phải cleanup và truyền context đúng qua async boundary.

Retry và DLT cần giữ eventId, correlationId cùng metadata nguồn để điều tra và replay. Log phải được bảo vệ khỏi secret, PII, header injection và cardinality không cần thiết. Kết hợp structured logs, metrics, distributed traces và audit giúp vận hành có thể lần theo event từ lúc phát sinh đến khi hoàn tất hoặc thất bại.

## Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| Structured logging | Ghi log theo field có cấu trúc, thường ở dạng JSON. |
| Log schema | Hợp đồng field, kiểu dữ liệu và naming convention của log. |
| eventId | ID duy nhất nhận diện một event logic. |
| correlationId | ID nối nhiều request/event thuộc cùng một business flow. |
| traceId | ID nối các span thuộc một distributed trace. |
| spanId | ID của một operation trong distributed trace. |
| requestId | ID của một request API hoặc operation đầu vào. |
| Kafka key | Key dùng cho partitioning và semantics xử lý theo key. |
| RecordMetadata | Metadata producer nhận sau khi Kafka xác nhận gửi record. |
| ConsumerRecord | Record consumer đọc, kèm topic, partition, offset, timestamp và headers. |
| Kafka headers | Danh sách metadata key/value bytes gắn với record. |
| MDC | Mapped Diagnostic Context, lưu field theo thread để logger đưa vào log event. |
| traceparent | Header W3C mang trace ID, parent span ID và trace flags. |
| tracestate | Header W3C mang vendor-specific trace context. |
| Retry | Cơ chế thử xử lý lại event khi gặp lỗi có thể phục hồi. |
| DLT | Dead-letter topic lưu record không xử lý thành công sau policy retry/recovery. |
| Original record metadata | Topic, partition, offset và timestamp của record nguồn trước khi chuyển retry/DLT. |
| Cardinality | Số lượng giá trị khác nhau của một field/label; cao quá mức làm tăng chi phí metrics backend. |
| Sampling | Chọn một phần log/trace để ghi hoặc export nhằm kiểm soát chi phí. |
| Redaction | Loại bỏ hoặc che dữ liệu nhạy cảm trước khi ghi log. |

