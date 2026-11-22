# Trace context của consumer

Trong hệ thống Spring Kafka, một sự kiện có thể bắt đầu từ HTTP request, được producer gửi lên Kafka, đi qua nhiều consumer, retry topic hoặc dead-letter topic (DLT) trước khi tạo kết quả cuối cùng. Khi mỗi service chỉ ghi log riêng, đội vận hành rất khó trả lời: **record này bắt nguồn từ đâu, đã qua những service nào và lỗi/chậm ở bước nào?**

**Trace context của consumer** là metadata truy vết được truyền theo Kafka record để consumer có thể tiếp nhận ngữ cảnh từ producer và liên hệ thao tác xử lý với luồng công việc upstream. Spring Kafka 3.x hỗ trợ tích hợp **Micrometer Observation**; khi kết hợp Micrometer Tracing, propagator và tracing exporter phù hợp, listener có thể tạo các span có khả năng liên hệ với trace phía producer.

Trong vận hành cần phân biệt: **propagation** truyền context qua Kafka headers; **observation/span** mô tả hoạt động trong JVM; **export** chuyển span sang tracing backend. Có trace header không đồng nghĩa trace đã xuất hiện trong Jaeger/Tempo. Ngược lại, một span không có parent không tự chứng minh record bị lỗi; có thể record không mang context upstream.

## 1. Trace context giải quyết vấn đề gì?

Giả sử nghiệp vụ đặt hàng:

~~~text
HTTP POST /orders
       |
       v
order-api
       |
       +--> Kafka: orders.created
                     |
                     v
                order-validator
                     |
                     +--> Kafka: orders.validated
                                    |
                                    v
                                billing-service
                                    |
                                    +--> HTTP payment API
~~~

Một tracing pipeline đúng giúp người vận hành tìm quan hệ giữa HTTP request ban đầu, producer send, listener xử lý, database và các HTTP calls tiếp theo. Thông tin cần trả lời gồm:

- Producer nào tạo record và trong bối cảnh request nào?
- Consumer group và listener nào nhận record?
- Listener mất bao lâu và đoạn nào chiếm thời gian?
- Record lỗi ở lần xử lý thứ mấy, có đi retry topic hoặc DLT không?
- Event có được giao lại do rebalance, restart hay replay thủ công không?
- Consumer bị chậm vì xử lý nghiệp vụ hay vì lag đã tích tụ trước khi nhận record?

**Trace ID không phải event ID.** Trace ID dùng để liên hệ các hoạt động quan sát; cùng một event có thể được replay trong một trace mới. Event ID cần ổn định giữa các lần giao để hỗ trợ idempotency và audit.

## 2. Trace, span, context và propagation

| Thuật ngữ | Ý nghĩa |
|---|---|
| Trace | Tập hợp span mô tả một chuỗi công việc xuyên service. |
| Trace ID | Định danh chung của trace. |
| Span | Một thao tác quan sát, ví dụ HTTP request, producer send hoặc consumer processing. |
| Span ID | Định danh riêng của span. |
| Parent/span link | Quan hệ giữa các span, tùy instrumentation và messaging semantic conventions. |
| Trace context | Dữ liệu cho downstream biết thông tin upstream cần để tiếp tục hoặc liên kết trace. |
| Propagator | Thành phần inject/extract context qua HTTP/Kafka headers. |
| Baggage | Metadata đi kèm context khi được cấu hình; cần kiểm soát quyền và kích thước. |

Ví dụ:

~~~text
Trace T
  HTTP request                         span A
      |
      +-- Kafka producer send          span B
              |
              +-- Kafka listener       span C
                      |
                      +-- DB operation  span D
                      +-- HTTP call     span E
~~~

Sơ đồ là minh họa. OpenTelemetry messaging conventions có thể thể hiện quan hệ parent-child hoặc **span links**, nhất là ở luồng bất đồng bộ hoặc batch. Khi kiểm thử, không nên giả định mọi consumer span luôn là child trực tiếp của producer span; phải xét phiên bản instrumentation và semantic conventions được chọn.

## 3. Kafka headers là nơi truyền trace context

Một Kafka `ConsumerRecord` có topic, partition, offset, key, value và **headers**. Kafka broker lưu header như dữ liệu metadata; broker không tự sinh trace ID hoặc đọc trace header để quyết định offset.

Ví dụ record mang W3C Trace Context:

~~~text
topic       = orders.created
partition   = 2
offset      = 1875
key         = order-4821
value       = {...}
headers:
  traceparent = 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
  tracestate  = ...
  event-id    = order-4821-created
~~~

Header `traceparent` có cấu trúc:

~~~text
version-trace-id-parent-id-flags
00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

Phần trace ID dài 32 ký tự hex, parent/span ID dài 16 ký tự hex; flags thể hiện thông tin như quyết định sampling. Đây là định dạng W3C, **không phải định dạng duy nhất**: B3 propagation dùng các header khác.

Producer và consumer cần thống nhất propagator. Một consumer chỉ tìm `traceparent` có thể kết luận nhầm “mất tracing” trong khi producer đang dùng B3; cách đúng là kiểm tra cấu hình propagation của cả hai đầu.

## 4. Luồng inject ở producer và extract ở consumer

~~~text
HTTP request
    |
    v
Current context trong order-api
    |
    v
KafkaTemplate.send()
    |
    +-- Producer observation/span
    +-- Propagator inject context vào record.headers()
    |
    v
Kafka broker lưu record và headers
    |
    v
Consumer poll()
    |
    +-- Propagator extract từ headers
    +-- Listener observation/span
    +-- Current scope được kích hoạt phù hợp
    |
    v
@KafkaListener
    |
    +-- DB / HTTP / producer downstream
    |
    v
Observation kết thúc -> span exporter
~~~

Điều quan trọng: **ThreadLocal của producer không thể tự đi qua broker tới JVM consumer**. Metadata phải được serialize vào header hoặc một cơ chế truyền context tương đương.

Nếu producer không instrument, consumer vẫn cần xử lý nghiệp vụ bình thường. Tùy cấu hình, nó có thể bắt đầu một root trace mới. Không dùng “thiếu traceparent” như lý do mặc định để bỏ qua Kafka record.

## 5. Bật Spring Kafka Observation ở listener

Với Spring Kafka 3.x, có thể bật observation trên `ContainerProperties`:

~~~java
@Configuration
public class KafkaObservationConfig {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, String>
            observedKafkaListenerFactory(
                    ConsumerFactory<String, String> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, String>();

        factory.setConsumerFactory(consumerFactory);
        factory.getContainerProperties().setObservationEnabled(true);

        return factory;
    }
}
~~~

Các import:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
~~~

Dùng đúng factory trên listener:

~~~java
@Component
public class OrderConsumer {

    @KafkaListener(
        id = "observed-orders",
        topics = "orders.created",
        groupId = "order-validator",
        containerFactory = "observedKafkaListenerFactory"
    )
    public void consume(ConsumerRecord<String, String> record) {
        orderService.validate(record.value());
    }
}
~~~

Bật `setObservationEnabled(true)` cho phép hạ tầng Spring Kafka tạo observation trong listener; muốn có distributed tracing còn phải cấu hình **ObservationRegistry, tracing bridge và propagator** phù hợp.

Nếu Spring Boot đã auto-configure listener factory mặc định, không nên tạo một factory thứ hai rồi quên chỉ định `containerFactory` cho listener. Trong dự án có nhiều factory, phải biết **listener nào dùng factory nào**.

## 6. Bật observation trên KafkaTemplate producer

Ở phía producer:

~~~java
@Bean
KafkaTemplate<String, String> observedKafkaTemplate(
        ProducerFactory<String, String> producerFactory) {

    KafkaTemplate<String, String> template =
            new KafkaTemplate<>(producerFactory);

    template.setObservationEnabled(true);
    return template;
}
~~~

Khi `KafkaTemplate` dùng observation/tracing bridge đúng, producer instrumentation có thể tạo span và inject context sang Kafka record headers.

~~~java
kafkaTemplate.send(
        "orders.created",
        "order-4821",
        "{\"orderId\":\"order-4821\"}");
~~~

**Consumer observation không tự bổ sung headers cho producer ở service khác.** Nếu upstream producer dùng raw `KafkaProducer`, Kafka Connect hoặc một client ngoài Java, phải xem instrumentation của chính producer đó. Một auto-instrumentation agent có thể xử lý Kafka client theo cơ chế riêng; tránh bật hai lớp producer instrumentation trùng nhau mà không hiểu quan hệ các span.

## 7. Micrometer Tracing và tracing backend

Một pipeline Spring Boot hoàn chỉnh thường cần:

1. Actuator/Micrometer Observation infrastructure.
2. Một tracing bridge như Micrometer Tracing bridge sang OpenTelemetry hoặc Brave.
3. Propagator tương thích upstream (W3C Trace Context, B3 hoặc chính sách tổ chức).
4. Span exporter/agent đưa dữ liệu sang collector/backend.
5. Observation được bật trên template và listener container thực sự đang chạy.

Ví dụ sampling cho các phiên bản Spring Boot hỗ trợ:

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.10
~~~

`0.10` là tỷ lệ lấy mẫu mục tiêu 10% theo chính sách sampler; parent sampling và exporter có thể khiến kết quả thực tế khác. Cấu hình Java `setObservationEnabled(true)` không tự cài bridge/exporter. Dự án cần dependency phù hợp với Spring Boot và phiên bản tracing backend đang dùng.

~~~text
Spring Kafka
   |
   +--> ObservationRegistry
   |      |
   |      v
   |   Micrometer Tracing bridge
   |      |
   |      +--> Propagator (inject/extract)
   |      +--> Span scope
   |
   v
Exporter / Agent
   |
   v
OTel Collector -> Jaeger / Tempo / khác
~~~

Một record có header `traceparent` nhưng backend trống có thể do **sampling, exporter, Collector ingestion, retention** hoặc listener chưa tạo span. Phải kiểm tra từng tầng.

## 8. Đọc trace ID hiện tại trong listener

Khi tracing bridge hoạt động, có thể inject Micrometer `Tracer` để đọc span đang active:

~~~java
@Component
public class TracedOrderConsumer {

    private static final Logger log =
            LoggerFactory.getLogger(TracedOrderConsumer.class);

    private final Tracer tracer;

    public TracedOrderConsumer(Tracer tracer) {
        this.tracer = tracer;
    }

    @KafkaListener(
        topics = "orders.created",
        groupId = "order-validator",
        containerFactory = "observedKafkaListenerFactory"
    )
    public void consume(ConsumerRecord<String, String> record) {
        Span current = tracer.currentSpan();

        String traceId = current == null
                ? "missing"
                : current.context().traceId();

        log.info(
            "Kafka record received: traceId={}, topic={}, partition={}, offset={}",
            traceId,
            record.topic(),
            record.partition(),
            record.offset());

        orderService.validate(record.value());
    }
}
~~~

Import chính:

~~~java
import io.micrometer.tracing.Span;
import io.micrometer.tracing.Tracer;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;
~~~

Ví dụ cần bean `Tracer` thực tế. Nếu `currentSpan()` là `null`, kiểm tra observation của listener, bridge, scope và việc listener có đang chạy trong thread/đường xử lý đã được instrument hay không.

Không dùng trace ID làm **idempotency key**. Một event được replay có thể có trace mới; deduplication cần event ID ổn định.

## 9. Đọc raw trace headers để chẩn đoán

Khi cần xác minh dữ liệu thực tế đi qua Kafka, có thể đọc header bytes:

~~~java
import java.nio.charset.StandardCharsets;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.header.Header;

void inspectHeader(ConsumerRecord<String, String> record) {
    Header h = record.headers().lastHeader("traceparent");

    if (h == null) {
        log.info("W3C traceparent absent: topic={}, partition={}, offset={}",
                record.topic(), record.partition(), record.offset());
        return;
    }

    String raw = new String(h.value(), StandardCharsets.UTF_8);
    log.debug("W3C traceparent present: {}", raw);
}
~~~

Đây là kỹ thuật **quan sát**, không phải propagator hoàn chỉnh. Cần nhớ:

- Header `traceparent` vắng mặt có thể là bình thường nếu upstream dùng B3.
- Kafka `Headers` có thể có nhiều header cùng tên.
- Không phải mọi giá trị UTF-8 nhìn giống traceparent đều hợp lệ; propagator cần validate.
- Kafka Connect, custom producer, recoverer hoặc gateway có thể thay/copy headers.
- Tránh ghi raw trace headers hoặc toàn bộ payload vào log production nếu không cần thiết.

Không tự tạo traceparent mới bằng cách ghép ngẫu nhiên chuỗi khi tracing library đã quản lý injection.

## 10. Trace context và MDC logging

Một tracing bridge có thể đưa `traceId`, `spanId` vào MDC để log cùng consumer invocation được liên hệ với span trong backend.

~~~text
timestamp=2026-11-15T12:00:00Z
service=order-validator
traceId=4bf92f3577b34da6a3ce929d0e0e4736
spanId=9124ab77cc881234
topic=orders.created
partition=2
offset=1875
eventId=order-4821-created
message="validation started"
~~~

Dữ liệu là ví dụ log ứng dụng tự thiết kế, không phải format mặc định của Spring Kafka.

Ba loại ID nên tồn tại cạnh nhau:

| ID/metadata | Dùng để |
|---|---|
| `traceId` | Tìm các span/log thuộc cùng trace. |
| `topic-partition-offset` | Tìm một lần xuất hiện của record trong Kafka. |
| `eventId` | Theo dõi cùng event nghiệp vụ qua retry, DLT và replay. |
| `causationId` | Liên kết event mới với event đã tạo ra nó theo policy nghiệp vụ. |

Nếu log không hiện trace ID mà backend vẫn có spans, kiểm tra cấu hình **MDC/logging pattern**, không chỉ Kafka headers. Nếu trace ID có trong log nhưng backend không có span, kiểm tra sampling/exporter. Hai đường quan sát có thể được cấu hình độc lập.

## 11. Propagation qua thread và async callback

Trace scope thường gắn với execution context hiện hành. Khi consumer chuyển công việc sang thread khác, không mặc định context sẽ tự đi theo.

~~~text
Kafka consumer thread
    |
    +-- current trace A
    |
    +-- executor.submit(task)
                  |
                  v
           Worker thread
           current trace có thể trống
~~~

Ví dụ:

~~~java
@KafkaListener(
    topics = "orders.created",
    containerFactory = "observedKafkaListenerFactory"
)
public void consume(String payload) {
    executorService.submit(() -> {
        // Không mặc định thread này có cùng tracing scope
        // với consumer thread.
        paymentService.process(payload);
    });
}
~~~

Sử dụng **Micrometer Context Propagation**, `TaskDecorator`, executor wrapper hoặc cơ chế context của Reactor phù hợp với framework và version đang dùng. Không sao chép thread-local bằng static variable; các listener thread đồng thời có thể xử lý những trace khác nhau và gây context leakage.

**Đừng nhầm context propagation với acknowledgment.** Nếu listener submit async task rồi return trước khi task hoàn tất, offset có thể được commit sớm theo container ack mode. Việc trace được nối đúng không đảm bảo side effect nghiệp vụ hoặc Kafka delivery semantics đúng.

## 12. Consumer gửi output sang topic khác

Khi consumer xử lý input rồi publish output, có hai ranh giới tracing liên tiếp: nhận input và gửi output.

~~~java
@Component
public class OrderValidator {

    private final KafkaTemplate<String, String> kafkaTemplate;

    public OrderValidator(
            KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @KafkaListener(
        topics = "orders.created",
        containerFactory = "observedKafkaListenerFactory"
    )
    public void handle(ConsumerRecord<String, String> record) {
        String normalized = normalize(record.value());
        kafkaTemplate.send("orders.validated", record.key(), normalized);
    }
}
~~~

Nếu listener observation và template observation hoạt động trong cùng scope, producer instrumentation có thể sử dụng current context và inject headers cho downstream. Nhưng nếu template được tạo từ một factory khác không instrument, hoặc code dùng KafkaProducer trực tiếp, propagation có thể bị đứt.

Nếu ứng dụng copy **toàn bộ Kafka headers** từ input sang output, cần cẩn trọng: raw `traceparent` cũ có thể được giữ nguyên ngoài ý muốn, gây nhiều header trùng hoặc quan hệ span không đúng. Ưu tiên để propagator chịu trách nhiệm injection; metadata nghiệp vụ như `eventId`/`causationId` nên ở header riêng.

## 13. Batch listener và nhiều upstream trace

Một batch có thể chứa record từ nhiều producer với context khác nhau:

~~~text
poll():
   record A -> trace A
   record B -> trace B
   record C -> trace C

@KafkaListener(List<ConsumerRecord<...>> batch)
~~~

Không thể mặc định có **một parent trace** phù hợp cho toàn batch. Hỗ trợ tracing/batch observation và cách tạo span links phụ thuộc Spring Kafka version và instrumentation cụ thể.

Nếu cần truy vết từng record trong batch:

- Xác nhận bản Spring Kafka hỗ trợ observation cho batch listener đến mức nào.
- Giữ `eventId` và `topic-partition-offset` cho từng record.
- Nếu tự tạo span per record, extract context bằng propagator chuẩn, không lấy context record đầu tiên gán cho toàn batch.
- Cân bằng số lượng spans với throughput và sampling.
- Kiểm tra partial batch failure và offset semantics riêng; tracing không sửa được acknowledgment.

Không dùng trace ID của một record trong batch làm idempotency key chung.

## 14. Retry, DLT và trace context

Một record lỗi có thể retry ngay trong consumer (blocking retry), được publish sang retry topic (non-blocking retry), hoặc đưa vào DLT.

~~~text
orders.created
      |
      v
consumer attempt 1 -- lỗi -->
      |
      v
orders-retry-1000
      |
      v
consumer attempt 2 -- lỗi -->
      |
      v
orders.DLT
~~~

Cần phân biệt:

| Trường hợp | Tác động tới tracing |
|---|---|
| Blocking retry trong cùng container | Có thể xử lý lại record với cùng upstream headers; cách observation/span cho mỗi attempt phụ thuộc framework. |
| Non-blocking retry | Record được republish sang topic khác, có thể tạo producer span và headers mới. |
| DLT publishing | Recoverer gửi record lỗi sang destination, có thể copy/update headers. |
| Replay thủ công | Có thể tạo trace mới dù event ID nghiệp vụ giữ nguyên. |

Với `DeadLetterPublishingRecoverer` và `@RetryableTopic`, context downstream phụ thuộc producer template, tracing instrumentation, cách copy headers và phiên bản Spring Kafka. **Không mặc định mọi retry hoặc DLT phải giữ cùng trace ID**, cũng không giả định mọi bước forwarding đều có observation mới nếu chưa kiểm tra cấu hình.

Khi điều tra record lỗi, nên lưu:

- Event ID nghiệp vụ ổn định.
- Original topic/partition/offset và current topic/partition/offset.
- Attempt/recovery metadata.
- Exception class, message an toàn và trạng thái publish DLT.
- Trace ID hiện hành; nếu cần, original trace ID hoặc causation ID trong trường **riêng**.

Không biến `traceparent` thành một nơi ghi “lịch sử tất cả trace cũ”; hãy để propagator quản lý format, còn provenance/audit thuộc event metadata.

## 15. Replay sau nhiều ngày không cần nối nguyên trace cũ

Ví dụ:

~~~text
Ngày 1:
  HTTP -> event E -> consumer fail -> DLT
  trace ID = T1

Ngày 3:
  Operator replay event E -> consumer success
  trace ID = T2 (có thể)
  event ID = E (giữ nguyên)
~~~

Tạo trace mới cho một workflow replay sau nhiều ngày có thể hợp lý hơn cố kéo dài trace cũ: backend có retention, sampler và semantics riêng. Cách liên kết lâu dài nên là **eventId, causationId, replayId** và audit log, không phụ thuộc trace ID cũ vẫn tồn tại trong tracing backend.

Replay phải có idempotency và quyền vận hành phù hợp; tracing không ngăn được charge payment lần hai.

## 16. Span success không đồng nghĩa committed offset

Một luồng xử lý logic:

~~~text
poll record
    |
    v
listener observation bắt đầu
    |
    v
@KafkaListener xử lý
    |
    v
listener return / observation kết thúc
    |
    v
container commit offset theo ack mode hoặc transaction
~~~

Thời điểm chính xác giữa observation, acknowledgment, error handler và transaction commit phụ thuộc listener mode, container và Spring Kafka version.

**Không coi span thành công là bằng chứng offset đã commit.** App có thể crash sau listener return nhưng trước commit, khiến record được giao lại. Tương tự, span lỗi có thể dẫn đến retry hoặc recover sang DLT và container vẫn tiếp tục theo error policy.

Muốn đánh giá delivery reliability cần ghép trace với:

- Consumer group committed offset và lag.
- Listener exception, `DefaultErrorHandler`/after-rollback policy.
- Kafka transaction commit/abort nếu có.
- DLT ingress/recovery failures.
- Business idempotency và side effect.

Trace context phục vụ quan sát, không cung cấp exactly-once hoặc khả năng rollback database.

## 17. Sampling và vì sao header có mà backend không có span

Hệ thống throughput cao thường lấy mẫu traces để giảm overhead:

~~~text
Record có traceparent
        |
        v
Consumer extract context
        |
        v
Sampling policy
    /            \
sampled        not sampled
   |                |
export span      không nhất thiết có span ở backend
~~~

Các nguyên nhân có thể khiến thiếu span:

- Upstream trace không được sample theo parent policy.
- Consumer sử dụng sampling probability thấp.
- Collector hoặc exporter lọc/drop span khi quá tải.
- Span chưa flush trước khi pod shutdown.
- Tracing backend đã hết retention dữ liệu.
- Propagator không tương thích hoặc listener observation không bật.

Không nâng sampling lên 100% trên mọi Kafka consumer production mà chưa đánh giá CPU, network, exporter queue và chi phí lưu trữ. Nếu cần điều tra incident, có thể tăng sampling có thời hạn hoặc dùng tail-sampling có kiểm soát, tùy hệ thống.

## 18. Baggage, privacy và trust boundary

Kafka headers có thể tồn tại lâu theo retention, bị copy sang retry topic/DLT và đọc được bởi các consumer group được cấp quyền. **Không đưa thông tin nhạy cảm vào tracing context** chỉ vì nó tiện truy cập.

Tránh đưa nguyên văn:

- Access token, API key, cookie hoặc mật khẩu.
- Email, số điện thoại, thẻ thanh toán và thông tin cá nhân không cần thiết.
- Payload nghiệp vụ lớn và stack trace chứa dữ liệu đầu vào.
- Giá trị tenant/user ID có cardinality lớn dưới dạng metric tag.
- Baggage không có allowlist và không có giới hạn kích thước.

**Trace context không phải cơ chế xác thực.** Producer không đáng tin có thể tự gửi traceparent giả; consumer không được lấy trace ID hoặc baggage làm căn cứ phân quyền tenant hoặc xác định người dùng đã đăng nhập.

Nếu cần gắn tenant vào tracing, áp dụng allowlist/anonymization, chính sách retention và khả năng truy cập phù hợp. Dữ liệu dùng cho authorization phải đến từ cơ chế xác thực được tin cậy.

## 19. Ma trận lỗi trace context

| Triệu chứng | Khả năng gây ra | Cách điều tra |
|---|---|---|
| Producer span có, consumer bắt đầu trace mới | Header không inject, bị xóa hoặc propagator khác nhau. | Kiểm tra raw Kafka headers và W3C/B3 config. |
| Record có traceparent, `currentSpan()` null | Listener observation chưa bật, tracing bridge thiếu hoặc scope thất lạc. | Kiểm tra factory, Tracer bean và context. |
| Log không có trace ID nhưng backend có span | MDC/logging pattern chưa cấu hình. | Kiểm tra log correlation và thread scope. |
| Có trace ID trong log nhưng backend không thấy span | Sampling/exporter/Collector/retention. | Xem sampling và tracing pipeline. |
| Trace bị đứt sau `@Async` hoặc executor | Context không đi theo thread mới. | Thêm context propagation/task decorator phù hợp. |
| Retry/DLT xuất hiện trace mới | Forwarder inject mới, copy headers khác hoặc replay là workflow mới. | Xem recoverer, template observation và event ID. |
| Một batch bị gán trace của record đầu tiên | Không xử lý nhiều upstream context đúng cách. | Kiểm tra batch semantics/span links. |
| Tracing làm tăng CPU hoặc latency | Sampling cao, attributes lớn, exporter nghẽn. | Xem span rate, queue/drop, CPU và exporter. |

Không tự “sửa” traceparent bằng string replace nếu chưa hiểu propagation specification; quan hệ trace sai có thể gây khó điều tra hơn cả việc thiếu trace.

## 20. Runbook: consumer mất liên kết trace

Giả sử order-api có HTTP trace và producer span nhưng trace không hiển thị bước order-validator.

**Bước 1 — Xác minh dữ liệu.** Record có thực sự vào topic/partition không? Consumer group có đọc record chưa? Dùng event ID, offset và log để định vị, không dựa duy nhất vào tracing backend.

**Bước 2 — Kiểm tra producer.** Producer có dùng observed `KafkaTemplate`, auto-instrumented KafkaProducer hay một đường publish khác? Có inject headers không?

**Bước 3 — Kiểm tra propagator.** Hai bên dùng W3C, B3 hay định dạng khác? Header có hợp lệ và không bị bridge/proxy/connector xóa không?

**Bước 4 — Kiểm tra listener container.** `setObservationEnabled(true)` đã được áp dụng cho **factory thực tế** chưa? Có nhiều listener factory hoặc custom container nào không?

**Bước 5 — Kiểm tra current context.** Trong listener, `Tracer.currentSpan()` có tồn tại không? Nếu có, quan hệ với upstream có đúng theo instrumentation conventions không?

**Bước 6 — Kiểm tra sampling và export.** Span có được tạo nhưng không export vì sampling, collector lỗi, quota hay retention không?

**Bước 7 — Kiểm tra async boundary.** Listener có submit task sang executor, Reactor hoặc callback làm mất scope không?

**Bước 8 — Kiểm tra retry/DLT.** Record có bị forward sang topic khác, khiến header/trace thay đổi không? Có event ID ổn định để nối lịch sử không?

**Bước 9 — Xác nhận bằng record mới.** Publish test event có ID riêng; kiểm tra Kafka headers, listener log, span backend và downstream hop cùng lúc.

**Bước 10 — Ghi postmortem.** Lưu phiên bản Spring Kafka/Boot, tracer bridge, propagator, sampling và cấu hình exporter liên quan để lần sau có thể đối chiếu.

Không kích hoạt replay quy mô lớn chỉ để tìm trace; replay có thể tạo side effect và phải theo quy trình dữ liệu riêng.

## 21. Trace latency và consumer lag không giống nhau

Ví dụ:

~~~text
Producer span:
  10:00:00.000 -> 10:00:00.035

Kafka record nằm trong topic

Consumer span:
  10:00:03.200 -> 10:00:03.280
~~~

Khoảng giữa producer và consumer có thể đến từ backlog, pause, retry topic delay, scheduling hoặc broker/network. **Không gọi toàn bộ khoảng này là broker latency**.

Để chẩn đoán đúng cần ghép:

- Producer send completion và transaction commit.
- Record timestamp, producer timestamp và thời điểm consumer nhận.
- Consumer lag, assignment, pause/resume, poll rate.
- Listener processing duration và dependency spans.
- Retry/DLT, thời gian chờ backoff và business processing delay.

Nếu tính message age từ timestamps, hãy kiểm tra topic dùng `CreateTime` hay `LogAppendTime` và clock skew giữa các host. Không coi độ lệch đồng hồ là một “Kafka queue time” chính xác.

## 22. Kiểm thử tích hợp propagation

Một kịch bản kiểm thử nên dùng Kafka broker thực (Testcontainers hoặc embedded Kafka) cùng tracing test exporter/handler:

1. Tạo topic và consumer group riêng cho test.
2. Cấu hình producer và listener với observation/tracing bridge và propagator tương thích.
3. Mở upstream observation/span trong test, publish record với event ID duy nhất.
4. Chờ listener nhận record bằng điều kiện có timeout.
5. Kiểm tra record chứa headers propagation phù hợp định dạng đã chọn.
6. Kiểm tra consumer có observation/span và quan hệ tracing phù hợp instrumentation contract.
7. Cho consumer publish sang một output topic, quan sát downstream context.
8. Thử record **không có trace header** để đảm bảo nghiệp vụ vẫn chạy bình thường.
9. Thử async boundary, retry topic hoặc DLT nếu hệ thống có dùng.
10. Kiểm tra exporter/test collector nhận spans khi sampling được bật, rồi cleanup tài nguyên test.

Tránh assert cứng tên span hoặc kiểu quan hệ parent-child khi nâng version có thể đổi semantic conventions. Ưu tiên kiểm tra khả năng propagate, xử lý record và kết quả trace theo contract của phiên bản đang chạy.

## 23. Checklist vận hành

- [ ] Producer và consumer có propagator tương thích, ví dụ W3C Trace Context.
- [ ] `KafkaTemplate` và listener factory thật đã bật Micrometer Observation khi dùng Spring Kafka instrumentation.
- [ ] ObservationRegistry, tracing bridge, exporter và tracing backend được cấu hình đầy đủ.
- [ ] Có cách kiểm tra raw headers trên một record thử nghiệm.
- [ ] Log có traceId/spanId và topic-partition-offset phù hợp, không ghi payload nhạy cảm.
- [ ] Không dùng trace ID để thay thế event ID, idempotency key hoặc authentication.
- [ ] Có context propagation cho executor, `@Async`, Reactor và callback nếu cần.
- [ ] Với batch listener, xác định tracing behavior thực tế của phiên bản.
- [ ] Với retry/DLT, biết header được copy/thay như thế nào và giữ event ID ổn định.
- [ ] Phân biệt tracing span success với acknowledgment/commit offset.
- [ ] Có sampling, cardinality và baggage privacy policy.
- [ ] Dashboard ghép tracing với lag, producer latency, retry/DLT và transaction metrics.
- [ ] Có runbook tách lỗi propagator, context scope, sampling và exporter.
- [ ] Có integration test end-to-end ít nhất qua producer, broker và consumer.

## 24. Kết luận

**Trace context của consumer** kết nối khả năng quan sát giữa các service bất đồng bộ trên Kafka. Producer inject context qua record headers, consumer extract context và tạo observation/span phù hợp; các thao tác downstream tiếp tục hoặc liên hệ trace qua tracing instrumentation. Spring Kafka và Micrometer Observation hỗ trợ tích hợp thuận tiện, nhưng hệ thống chỉ hoạt động end-to-end khi propagator, bridge, sampling và exporter được cấu hình nhất quán.

Tracing là **công cụ điều tra**, không phải bảo đảm delivery hay nhất quán nghiệp vụ. Hãy giữ event ID, offset, retry metadata và idempotency riêng; kiểm soát dữ liệu nhạy cảm trong headers; và duy trì propagation qua async thread hoặc retry/DLT. Khi làm đúng, trace giúp tìm nhanh nguyên nhân lỗi mà không che khuất trạng thái thực tế của Kafka record và consumer group.
