# Trace producer-consumer

Một application event thường đi qua nhiều thành phần trước khi hoàn tất: nghiệp vụ phát event, Spring Modulith ghi nhận publication, listener hoặc externalization adapter xử lý sau commit, producer gửi message tới broker, rồi consumer nhận và thực hiện nghiệp vụ tiếp theo. Khi một mắt xích chậm hoặc thất bại, log riêng lẻ của từng service thường không đủ để giải thích toàn bộ hành trình. **Distributed tracing** giúp nối các bước này thành một đường đi có thể quan sát, từ producer tới consumer và các dịch vụ downstream.

Để trace hoạt động xuyên suốt, hệ thống cần truyền trace context qua ranh giới bất đồng bộ, gắn định danh nghiệp vụ vào log, tạo span ở đúng điểm xử lý và đo các chỉ số vận hành bằng metrics. Trace ID, event ID và correlation ID có mục đích khác nhau; dùng đúng từng loại giúp điều tra sự cố mà không làm event contract phụ thuộc vào công cụ quan sát.

## 1. Hành trình của một event

Một event có thể đi qua các bước:

~~~text
HTTP request / command
        |
        v
Producer service
        |
        v
Business transaction commits
        |
        v
Spring Modulith publication
        |
        v
Externalization listener / adapter
        |
        v
Kafka producer
        |
        v
Kafka topic and partition
        |
        v
Consumer service
        |
        v
Database update / downstream call
~~~

Mỗi bước nên tạo span hoặc log có ngữ cảnh đủ để xác định nó thuộc event nào và quy trình nào. Khi có trace context, các span có thể được hiển thị thành một trace hoặc được nối bằng span links tùy semantics của messaging và cách instrumentation triển khai.

Một trace producer-consumer có thể gồm:

- Span xử lý request hoặc command ban đầu.
- Span transaction và phát application event.
- Span listener sau commit hoặc externalization.
- Span gửi message tới broker.
- Span nhận và xử lý message ở consumer.
- Span gọi database hoặc dịch vụ downstream.

Không phải mọi bước đều nhất thiết nằm trong một process hoặc một transaction. Trace cho thấy quan hệ thực thi và độ trễ giữa các bước; nó không tạo ra transaction phân tán và không bảo đảm message được giao đúng một lần.

## 2. Phân biệt trace ID, correlation ID và event ID

Ba định danh này thường xuất hiện cùng nhau nhưng trả lời các câu hỏi khác nhau:

| Định danh | Trả lời câu hỏi | Phạm vi |
|---|---|---|
| **traceId** | Các thao tác kỹ thuật này thuộc trace nào? | Một lần thực thi phân tán được tracing system theo dõi |
| **correlationId** | Những event và thao tác này thuộc quy trình nghiệp vụ nào? | Một workflow hoặc business process có thể kéo dài qua nhiều trace |
| **eventId** | Đây chính xác là sự kiện nghiệp vụ nào? | Một event ổn định qua publish, retry, redelivery và replay |
| **causationId** | Sự kiện hoặc hành động nào gây ra sự kiện hiện tại? | Quan hệ nhân quả giữa các event hoặc command |

Một workflow có thể kéo dài nhiều giờ hoặc nhiều ngày, vượt quá thời gian sống của một trace. Vì vậy, correlation ID có thể giữ nguyên qua nhiều trace khác nhau. Event ID phải giữ nguyên khi cùng một event được retry hoặc replay; không tạo event ID mới cho mỗi lần gửi lại.

Không dùng trace ID làm event ID. Trace ID có thể thay đổi khi replay, có thể không tồn tại nếu tracing bị tắt hoặc sampling loại bỏ trace. Ngược lại, event ID phải tồn tại độc lập với hệ thống observability để deduplicate và audit.

Một event envelope có thể chứa metadata nghiệp vụ:

~~~java
public record EventMetadata(
    UUID eventId,
    String correlationId,
    UUID causationId,
    Instant occurredAt,
    int schemaVersion
) {}
~~~

Có thể đưa metadata vào payload hoặc message headers tùy contract. Event ID, correlation ID và causation ID là dữ liệu phục vụ liên kết nghiệp vụ; trace context như traceparent và tracestate thường được truyền ở transport headers để tránh gắn contract domain với một chuẩn tracing cụ thể.

## 3. Trace context và W3C Trace Context

Trace context là thông tin giúp dịch vụ tiếp theo tiếp tục trace đang diễn ra. Chuẩn W3C Trace Context định nghĩa các header phổ biến:

- **traceparent** chứa version, trace ID, parent span ID và trace flags.
- **tracestate** mang thông tin vendor-specific bổ sung khi có.
- **baggage** mang các thuộc tính ngữ cảnh được cho phép truyền qua nhiều service.

Một traceparent có dạng minh họa:

~~~text
00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

Khi producer gửi message, trace context cần được inject vào message headers. Consumer extract context từ headers trước khi bắt đầu xử lý để span mới được nối với ngữ cảnh đã truyền.

Không nên tự tạo trace ID bằng UUID rồi đặt vào header traceparent. Traceparent có cấu trúc và semantics riêng; hãy dùng OpenTelemetry propagator hoặc instrumentation của framework để inject/extract đúng chuẩn.

Baggage chỉ nên chứa thuộc tính cần thiết, không chứa token, credential, dữ liệu cá nhân hoặc payload nghiệp vụ. Baggage được truyền qua nhiều service nên có thể mở rộng phạm vi lộ dữ liệu và kích thước message.

## 4. Bật tracing trong Spring Boot và Micrometer

Trong ứng dụng Spring Boot, observability thường được tích hợp qua Micrometer Observation và một tracing bridge như Micrometer Tracing với OpenTelemetry hoặc Brave. Các thành phần thường cần có:

- Observation API để tạo observation cho thao tác ứng dụng.
- Tracing bridge và exporter để tạo, kết thúc và xuất span.
- Context propagation để truyền ngữ cảnh qua executor và các ranh giới bất đồng bộ.
- Logging integration để đưa trace ID và span ID vào log correlation.
- Instrumentation cho HTTP client/server, database và messaging phù hợp với stack đang dùng.

Tên dependency và cấu hình cụ thể phụ thuộc phiên bản Spring Boot, Spring Modulith, Spring Kafka và tracing bridge. Hãy giữ một tracing implementation thống nhất trong service và kiểm tra dependency management của phiên bản đang triển khai. Không thêm nhiều bridge cùng lúc nếu không có lý do rõ ràng.

Ví dụ cấu hình minh họa cho sampling và endpoint exporter:

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.10
  otlp:
    tracing:
      endpoint: http://otel-collector:4318/v1/traces
~~~

Cấu hình trên chỉ minh họa cách chọn tỷ lệ sampling và endpoint OTLP; property có thể thay đổi theo phiên bản Spring Boot và exporter đang dùng. Trong production, endpoint nên được cấu hình theo môi trường và exporter cần xác thực/TLS phù hợp với hạ tầng.

Sampling 10% nghĩa là phần lớn trace có thể không được ghi lại. Các metric vẫn cần phản ánh toàn bộ lưu lượng; không suy ra tổng số event từ số trace được sample.

## 5. Tạo span ở producer

Producer nên có span cho thao tác phát event hoặc gửi message. Span cần mô tả thao tác, destination và kết quả, không ghi toàn bộ payload.

Với Spring Kafka, Micrometer Observation có thể được bật trên KafkaTemplate để tạo observation cho thao tác gửi. Tùy phiên bản, cấu hình có thể được thực hiện trên bean KafkaTemplate hoặc qua property của Spring Boot:

~~~java
@Bean
KafkaTemplate<String, Object> kafkaTemplate(
        ProducerFactory<String, Object> producerFactory) {

    KafkaTemplate<String, Object> template =
        new KafkaTemplate<>(producerFactory);

    template.setObservationEnabled(true);
    return template;
}
~~~

Đây là ví dụ API Spring Kafka ở các phiên bản hỗ trợ observation trên template. Hãy kiểm tra đúng phiên bản đang dùng và tránh cấu hình trùng nếu auto-configuration đã bật observation.

Nếu gửi message qua adapter riêng, có thể tạo observation quanh thao tác gửi. Observation cần bao phủ việc nhận kết quả gửi bất đồng bộ; kết thúc span ngay sau khi gọi send mà không theo dõi future có thể làm trace không phản ánh thời gian hoặc lỗi broker thực tế.

~~~java
Observation observation = Observation
    .createNotStarted("event.publish", observationRegistry)
    .lowCardinalityKeyValue("event.type", "StockReserved")
    .lowCardinalityKeyValue("messaging.destination", topic);

observation.observe(() -> publisher.publish(event));
~~~

Đoạn code trên là ví dụ về Observation API; nếu publisher trả về future, cần dùng cơ chế hỗ trợ async observation hoặc hoàn tất observation khi future kết thúc. Không giữ thread chỉ để chờ một future nếu API có thể xử lý callback hoặc completion phù hợp.

Các thuộc tính như event type và destination có cardinality thấp thường phù hợp làm span attributes. Event ID, order ID hoặc customer ID có cardinality cao; nên đặt chúng trong log hoặc span event khi cần điều tra, không dùng làm metric labels.

## 6. Truyền trace context qua Kafka headers

Kafka message là ranh giới bất đồng bộ. Trace context của producer cần được ghi vào headers để consumer có thể tiếp tục trace. Khi Spring Kafka instrumentation được cấu hình đúng, việc inject/extract thường được thực hiện tự động. Hãy ưu tiên instrumentation chuẩn để tránh tự triển khai propagation trùng lặp.

Nếu adapter cần inject thủ công bằng OpenTelemetry API, có thể dùng TextMapPropagator. Ví dụ rút gọn:

~~~java
private static final TextMapSetter<Headers> SETTER =
    (headers, key, value) ->
        headers.add(key, value.getBytes(StandardCharsets.UTF_8));

void publish(ProducerRecord<String, byte[]> record) {
    TextMapPropagator propagator = GlobalOpenTelemetry
        .getPropagators()
        .getTextMapPropagator();

    propagator.inject(Context.current(), record.headers(), SETTER);
    kafkaProducer.send(record);
}
~~~

Ví dụ giả định OpenTelemetry SDK và Kafka client đã được cấu hình. Chỉ dùng một cơ chế propagation cho mỗi đường gửi; nếu instrumentation tự inject headers, không inject lần nữa bằng code thủ công.

Ở consumer, extract context từ headers trước khi xử lý:

~~~java
private static final TextMapGetter<Headers> GETTER =
    new TextMapGetter<>() {
        @Override
        public Iterable<String> keys(Headers headers) {
            List<String> keys = new ArrayList<>();
            headers.forEach(header -> keys.add(header.key()));
            return keys;
        }

        @Override
        public String get(Headers headers, String key) {
            Header header = headers.lastHeader(key);
            return header == null
                ? null
                : new String(header.value(), StandardCharsets.UTF_8);
        }
    };

void consume(ConsumerRecord<String, byte[]> record) {
    TextMapPropagator propagator = GlobalOpenTelemetry
        .getPropagators()
        .getTextMapPropagator();

    Context extracted = propagator.extract(
        Context.current(),
        record.headers(),
        GETTER
    );

    try (Scope scope = extracted.makeCurrent()) {
        handler.process(record.value());
    }
}
~~~

Đây là ví dụ minh họa extraction thủ công. Nếu Spring Kafka hoặc agent instrumentation đã tạo consumer span và extract context, không tạo thêm một consumer span trùng. Cần kiểm tra trace thực tế trong backend để xác nhận parent hoặc span link được tạo đúng.

## 7. Truyền context qua listener bất đồng bộ của Spring Modulith

Trong Spring Modulith, listener có thể được xử lý sau commit và bất đồng bộ. Khi đó, request ban đầu đã kết thúc hoặc thread hiện tại đã thay đổi trước khi listener chạy.

Nếu executor không truyền context, span của listener có thể trở thành trace mới không liên kết với producer. Context propagation cần được cấu hình cho executor được dùng bởi listener. Với Spring Boot/Micrometer, context-propagation và TaskDecorator phù hợp có thể giúp truyền observation context qua task boundary; cách cấu hình tùy phiên bản và executor.

Một số nguyên tắc:

- Dùng executor có hỗ trợ context propagation cho listener bất đồng bộ.
- Không tự giữ ThreadLocal của request trong một khoảng thời gian dài.
- Nếu event được lưu rồi xử lý sau khi ứng dụng restart, ThreadLocal cũ không còn tồn tại; cần lưu correlation/event metadata bền vững và thiết lập trace context mới khi replay.
- Với replay, có thể tạo trace mới và liên kết với event ID, correlation ID và trace nguồn nếu metadata nguồn được lưu.
- Không giả định mọi publication được xử lý trong cùng trace với HTTP request ban đầu.

Ví dụ listener:

~~~java
@Component
class StockReservedListener {

    private final StockProjection projection;

    StockReservedListener(StockProjection projection) {
        this.projection = projection;
    }

    @ApplicationModuleListener
    void on(StockReserved event) {
        projection.apply(event);
    }
}
~~~

Listener nên tập trung vào xử lý nghiệp vụ. Tracing instrumentation của framework hoặc observation quanh service xử lý nên đảm nhiệm span. Tránh tự tạo span ở nhiều lớp cho cùng một thao tác khiến trace có quá nhiều span lặp.

## 8. Quan hệ parent và span links trong messaging

Trong request-response đồng bộ, span của service gọi thường là parent của span service được gọi. Với messaging, producer và consumer có thể cách nhau một khoảng thời gian dài, consumer có thể xử lý theo batch hoặc nhiều consumer có thể nhận cùng một event.

Vì vậy, quan hệ trace không phải lúc nào cũng nên biểu diễn bằng một cây parent-child đơn giản. Instrumentation có thể dùng parent context hoặc span links tùy semantics và phiên bản OpenTelemetry messaging conventions. Span link hữu ích khi một consumer xử lý nhiều message trong batch hoặc một tác vụ được kích hoạt bởi nhiều event.

Điều quan trọng là trace context gốc phải được giữ trong message headers và consumer phải tạo span mới với quan hệ phù hợp. Không tự ép mọi consumer thành child span trực tiếp nếu việc đó làm sai ý nghĩa của batch hoặc fan-out.

Với một event được nhiều consumer group xử lý độc lập, mỗi consumer có thể tạo một nhánh xử lý riêng. Khi xem trace, người vận hành cần phân biệt thời gian producer publish với thời gian mỗi consumer hoàn tất; một consumer chậm không có nghĩa producer gửi thất bại.

## 9. Structured logging và log correlation

Trace hữu ích hơn khi log chứa các định danh tương ứng. Một log có cấu trúc nên có các trường:

| Trường | Mục đích |
|---|---|
| service.name | Dịch vụ ghi log |
| trace_id | Liên kết log với trace |
| span_id | Xác định span tại thời điểm ghi log |
| event_id | Nhận diện event nghiệp vụ |
| correlation_id | Liên kết các bước trong workflow |
| causation_id | Xác định event hoặc command gây ra event hiện tại |
| messaging.destination | Topic hoặc destination |
| consumer.group | Consumer group đang xử lý |
| event.type | Loại event |
| attempt | Lần xử lý hoặc retry hiện tại |

Ví dụ log JSON:

~~~json
{
  "level": "INFO",
  "message": "Event consumed",
  "service.name": "order-service",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7",
  "event_id": "7f90c6e0-5e1f-4c8c-9a72-2df2c7d74e2a",
  "correlation_id": "checkout-20261125-001",
  "event.type": "StockReserved",
  "messaging.destination": "inventory.stock-reserved.v1"
}
~~~

Không ghi toàn bộ payload, token, credential hoặc dữ liệu cá nhân chỉ để thuận tiện tìm kiếm. Nếu cần điều tra payload, dùng event ID để truy cập kho dữ liệu được kiểm soát quyền và audit.

Trace ID trong MDC cần được làm sạch sau khi task kết thúc. Thread pool tái sử dụng thread; nếu context không được đóng đúng cách, log của request sau có thể mang trace ID của request trước. Dùng scope/context API với try/finally hoặc cơ chế tự đóng để tránh rò rỉ context giữa các task.

## 10. Metrics cho producer và consumer

Metrics cho biết xu hướng và mức độ ảnh hưởng trên toàn hệ thống; tracing giúp điều tra một lần thực thi cụ thể. Nên có metrics ở cả producer, broker và consumer:

| Metric | Ý nghĩa |
|---|---|
| event_publish_total | Số lần ứng dụng yêu cầu publish event |
| event_publish_duration | Thời gian gửi và nhận kết quả |
| event_publish_failure_total | Số lần gửi thất bại |
| event_consume_total | Số event consumer đã xử lý |
| event_consume_duration | Thời gian xử lý một event |
| event_consume_failure_total | Số lần xử lý thất bại |
| event_retry_total | Số lần retry |
| event_dead_letter_total | Số event chuyển sang dead-letter |
| event_publication_incomplete | Số publication chưa hoàn tất |
| kafka_consumer_lag | Khoảng cách giữa consumer và log mới nhất |

Tên metric là ví dụ; hãy theo convention của Micrometer và instrumentation đang sử dụng. Dùng tag có cardinality thấp như event type, destination, consumer group và outcome. Không dùng event ID, trace ID, order ID hoặc customer ID làm tag vì số lượng giá trị không giới hạn có thể làm tăng bộ nhớ và chi phí backend.

Không dùng trace sampling để thay thế metrics. Nếu chỉ trace 10% request, metric vẫn phải đếm đủ tổng số lần publish, consume và lỗi.

## 11. Theo dõi retry và lỗi xuyên suốt trace

Khi consumer xử lý lỗi, trace nên ghi nhận loại lỗi, attempt và policy action. Nếu retry xảy ra trong cùng process, có thể tạo span cho từng attempt hoặc span event thể hiện lần thử. Nếu retry được lên lịch rồi chạy ở thời điểm khác, mỗi lần thực thi có thể tạo trace mới nhưng vẫn giữ event ID và correlation ID để tìm lại toàn bộ lịch sử.

Ví dụ các thuộc tính hữu ích:

- event.type
- event.id khi cần tra cứu và không dùng làm metric label
- messaging.destination
- messaging.kafka.partition
- messaging.kafka.offset
- retry.attempt
- error.type
- error.category
- retry.next_attempt_at
- error.policy_action

Không đưa nội dung exception có thể chứa dữ liệu nhạy cảm vào span attribute. Có thể ghi exception event với loại lỗi và stack trace theo chính sách bảo mật/log retention của tổ chức.

Nếu Event Publication Registry giữ publication incomplete, dashboard nên liên kết được publication ID với event ID và trace/log tương ứng. Registry theo dõi trạng thái giao event; tracing ghi lại thời gian và quan hệ thực thi. Hai nguồn bổ sung nhau nhưng không thay thế nhau.

## 12. Sampling và chi phí quan sát

Tracing có thể tạo lượng dữ liệu lớn, đặc biệt khi event throughput cao. Sampling giúp kiểm soát chi phí nhưng cần được chọn theo mục tiêu:

- Head sampling quyết định ở đầu trace, đơn giản và tiết kiệm nhưng có thể bỏ qua trace chỉ trở nên quan trọng ở consumer.
- Tail sampling có thể giữ trace dựa trên kết quả cuối cùng như lỗi hoặc độ trễ cao, nhưng cần collector giữ dữ liệu đủ lâu và có tài nguyên phù hợp.
- Một số luồng quan trọng có thể được cấu hình sampling cao hơn theo service hoặc operation.

Khi producer và consumer ở nhiều service, propagation cần giữ sampling flags theo chuẩn. Không tự thay trace flags ở consumer nếu không có policy thống nhất, vì có thể làm trace bị đứt hoặc tăng dữ liệu ngoài dự kiến.

Dù sampling thấp, vẫn cần metrics và log có correlation để theo dõi tổng quan. Với event quan trọng, có thể tăng sampling theo loại operation hoặc dùng tail sampling để ưu tiên trace lỗi, nhưng cần kiểm soát cardinality và chi phí lưu trữ.

## 13. Kiểm thử trace producer-consumer

Kiểm thử cần xác nhận trace context đi qua đúng ranh giới, không chỉ xác nhận log có trace ID:

1. HTTP request phát application event và producer span được tạo.
2. Trace context được inject vào Kafka headers.
3. Consumer extract context và tạo span có quan hệ đúng với producer.
4. Event ID và correlation ID được giữ nguyên qua producer, broker và consumer.
5. Listener bất đồng bộ sau commit vẫn có context hoặc metadata liên kết theo thiết kế.
6. Retry tạo dấu vết attempt có thể tìm theo event ID.
7. Replay tạo trace mới nhưng giữ event ID/correlation ID để nối lịch sử nghiệp vụ.
8. Consumer batch hoặc fan-out dùng parent/span links phù hợp.
9. Log của producer và consumer chứa trace ID/span ID đúng với span hiện tại.
10. Metric đếm đầy đủ kể cả khi trace bị sampling.
11. Context được đóng sau task, không rò sang request tiếp theo.
12. Payload và baggage không chứa secret hoặc dữ liệu nhạy cảm.

Trong integration test, có thể dùng in-memory span exporter hoặc OpenTelemetry test tooling để kiểm tra span và parent/link. Với Kafka, dùng broker test phù hợp để xác nhận headers thực sự tồn tại trong record. Mock producer không đủ để chứng minh propagation qua serializer và broker.

## 14. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Chỉ ghi trace ID trong producer log | Consumer không thể nối trace | Inject trace context vào message headers |
| Dùng event ID làm trace ID | Trộn identity nghiệp vụ với identity thực thi | Giữ event ID và trace ID riêng |
| Async executor không truyền context | Listener tạo trace rời rạc | Cấu hình context propagation hoặc lưu metadata liên kết |
| Tạo span trùng ở nhiều lớp | Trace khó đọc và thời gian bị tính lặp | Chọn một instrumentation owner cho mỗi thao tác |
| Kết thúc span trước khi future gửi hoàn tất | Trace không thể hiện lỗi/latency broker | Hoàn tất observation khi async operation hoàn tất |
| Dùng trace ID làm metric tag | Cardinality tăng không giới hạn | Chỉ dùng ID trong trace/log |
| Nuốt exception rồi ghi log | Publication có thể bị coi là thành công | Truyền lỗi hoặc ghi trạng thái quarantine có chủ đích |
| Replay không giữ event ID | Khó deduplicate và điều tra | Giữ event identity ổn định qua replay |

## 15. Checklist triển khai

Trước khi đưa tracing producer-consumer vào production, xác nhận:

- Tracing bridge và exporter được cấu hình thống nhất trong các service.
- HTTP server/client, Spring Modulith listener và Kafka producer/consumer có instrumentation phù hợp.
- Trace context W3C được inject/extract qua Kafka headers.
- Executor xử lý listener bất đồng bộ có context propagation.
- Event ID, correlation ID và causation ID được định nghĩa với semantics rõ.
- Retry và replay giữ event ID; trace mới vẫn có liên kết nghiệp vụ.
- Span attributes dùng giá trị có cardinality phù hợp.
- Metrics không chứa trace ID hoặc event ID làm label.
- Log có trace ID, span ID, event ID và correlation ID khi cần.
- Sampling, retention, quyền truy cập và bảo vệ dữ liệu đã được thiết lập.
- Có kiểm thử trace xuyên producer, broker, consumer và downstream.

Trace producer-consumer giúp đội vận hành nhìn thấy một event đi qua các module và dịch vụ như thế nào, mất bao lâu và thất bại ở đâu. Khi truyền trace context đúng qua message headers, giữ riêng event/correlation identity, instrument các ranh giới bất đồng bộ và kết hợp trace với logs cùng metrics, ứng dụng Spring Modulith có thể điều tra sự cố xuyên suốt mà vẫn giữ event contract độc lập với nền tảng observability.

