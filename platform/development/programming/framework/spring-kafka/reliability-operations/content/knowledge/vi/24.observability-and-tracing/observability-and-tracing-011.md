# Không đưa payload nhạy cảm vào span

Trong **Spring Kafka Reliability Operations**, **Observation và tracing** giúp thấy một Kafka event đi từ producer, qua topic, vào listener, database và downstream service. Nhưng mỗi span cũng tạo một đường dữ liệu mới: ứng dụng gửi thông tin tới tracing exporter, collector, backend, dashboard và các công cụ hỗ trợ sự cố. Nếu span chứa **Kafka payload nhạy cảm**, dữ liệu nghiệp vụ có thể bị sao chép sang nơi không có cùng ACL, retention hoặc chính sách truy cập như Kafka và database.

Nguyên tắc trung tâm của bài này: **span mô tả hoạt động; span không phải bản sao của Kafka record**. Để điều tra throughput, retry, timeout hay deadlock, span thường chỉ cần topic, operation, thời gian xử lý, kết quả, loại lỗi và retry stage — không cần email, số điện thoại, địa chỉ, token, dữ liệu thanh toán hay raw JSON.

Bảo vệ phải áp dụng cho **tên span, attributes, events, exception details, baggage, Kafka key/value/headers và cả các spans HTTP/DB downstream**. Chỉ tránh gọi setAttribute với payload là chưa đủ nếu framework hoặc thư viện khác vẫn xuất exception message chứa dữ liệu.

## 1. Span chứa những thành phần gì?

| Thành phần | Ví dụ vận hành hữu ích | Rủi ro |
|---|---|---|
| Span name | kafka receive, order.process | Ghép email hoặc payload vào tên |
| Attributes | messaging.system=kafka | record.value, customer.email |
| Span events | retry_scheduled, validation_failed | Toàn bộ JSON trong event |
| Status | ERROR | Description chứa raw exception |
| Exception event | exception.type | Stack/message chứa token |
| Links | Kết nối trace context giữa spans | Link attributes chứa data khách hàng |
| Baggage | Opaque correlation reference đã duyệt | JWT, phone, account ID |
| Resource attributes | service.name, environment | Secret hoặc tenant identity |

Trace exporter thường gửi những trường này ra ngoài tiến trình. Các span events không phải log tạm thời sẽ biến mất: chúng có thể được backend lưu và index.

## 2. Vì sao Kafka payload cần chính sách riêng?

Kafka record có các phần: topic, partition, offset, timestamp, **key**, **value** và **headers**.

- **Value** có thể là JSON, Avro, Protobuf chứa PII, payment hoặc business secrets.
- **Key** có thể là email, số điện thoại hoặc account ID.
- **Headers** có thể có Authorization, cookie, baggage hoặc tenant/customer metadata.
- **Exception** khi deserialize có thể chứa raw bytes hoặc một phần payload.
- **DLT** có thể lưu lại record lỗi và thông tin nguyên nhân.
- **Logs** do interceptor tạo có thể in toàn bộ ConsumerRecord.

Ví dụ **không an toàn**:

~~~java
span.setAttribute("kafka.value", record.value().toString());
span.setAttribute("kafka.key", String.valueOf(record.key()));
span.setAttribute("kafka.headers", record.headers().toString());
~~~

DTO.toString() có thể được sinh tự động và in tất cả fields. Header values và record key không được mặc định xem là dữ liệu công khai.

**Không đưa trực tiếp record.key(), record.value(), raw headers hoặc raw exception message lên span.**

## 3. Dữ liệu rời ứng dụng bằng con đường nào?

~~~mermaid
flowchart LR
    A["Kafka producer"] --> B["Kafka topic"]
    B --> C["Spring Kafka listener"]
    C --> D["Business processing"]
    C --> E["Micrometer Observation"]
    D --> E
    E --> F["Tracing exporter"]
    F --> G["OTel collector"]
    G --> H["Trace backend"]
    H --> I["Dashboard / support"]
~~~

Kafka topic có thể được bảo vệ bằng ACL và retention ngắn. Nhưng trace backend có thể cho phép nhiều nhóm kỹ sư tra cứu, hoặc được vận hành bởi nhà cung cấp dịch vụ khác. Một attribute chứa payload làm **tăng số bản sao và số người có khả năng truy cập**.

Data minimization tại ứng dụng là lớp phòng thủ đầu tiên. Encryption, Collector redaction, RBAC và retention là những lớp tiếp theo, không thay thế chính sách không capture payload.

## 4. Phân loại trước khi thêm attribute

| Dữ liệu | Ví dụ | Chính sách |
|---|---|---|
| Messaging system | kafka | Cho phép |
| Operation | send, receive | Cho phép |
| Topic logical name | orders.events | Cho phép nếu naming policy phù hợp |
| Consumer group | order-service | Kiểm tra có chứa tenant ID không |
| Partition | 2 | Có thể cho phép |
| Offset | 104 | Cân nhắc nhu cầu, cardinality và privacy |
| Event type cố định | OrderCreated | Chỉ từ allowlist |
| Error category | timeout, schema_validation | Chỉ từ allowlist |
| Retry stage | original, retry, dlt | Cho phép |
| Customer details | Email, phone, address | Không ghi |
| Payment/health data | Card number, medical data | Không ghi |
| Message value | JSON/Avro/Protobuf payload | Không ghi |
| Raw message key | Email hoặc user ID | Mặc định không ghi |
| Raw Kafka headers | Authorization, JWT | Không copy |
| Exception message | Có thể chứa input | Chỉ dùng khi đã kiểm soát |

Ngay cả topic name có thể chứa customer identifier trong hệ thống dynamic topics. Metadata cũng cần review theo thực tế chứ không có ngoại lệ tự động.

## 5. Low cardinality không có nghĩa private

Micrometer Observation phân biệt **low-cardinality key values** dùng phù hợp với metrics và **high-cardinality key values** thường chỉ xuất qua tracing.

Nhưng đây là phân loại **số lượng giá trị**, không phải mức nhạy cảm:

- event.type=OrderCreated thường low cardinality và có thể được duyệt.
- customer.email là high cardinality và **không an toàn**, kể cả đặt qua highCardinalityKeyValue.
- Một enum nhạy cảm cũng có thể không được phép dù cardinality thấp.

Không xem high-cardinality là khu vực được phép lưu dữ liệu khách hàng. Về bản chất, giá trị đó có thể vẫn được xuất thành span attribute.

## 6. Spring Kafka và Micrometer Observation

Những thành phần liên quan:

- **KafkaTemplate** tạo observations cho producer khi được bật.
- **MessageListenerContainer** có thể tạo observations cho consumer/listener.
- **ObservationRegistry** quản lý các observations.
- **ObservationConvention** định nghĩa tên và key values.
- **Micrometer Tracing / OpenTelemetry bridge** có thể chuyển observations thành spans.
- **OTLP exporter/collector** gửi telemetry đến backend.

Ví dụ listener factory của phiên bản Spring Kafka hỗ trợ observation:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
observedListenerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties().setObservationEnabled(true);

    return factory;
}
~~~

Producer:

~~~java
@Bean
KafkaTemplate<String, OrderEvent> observedKafkaTemplate(
        ProducerFactory<String, OrderEvent> producerFactory) {

    var template = new KafkaTemplate<>(producerFactory);
    template.setObservationEnabled(true);
    return template;
}
~~~

Spring Boot có thể auto-configure KafkaTemplate hoặc listener factory. Không tạo bean trùng khi chưa biết project config. API observation và cách nối tracer/exporter phụ thuộc Spring Kafka/Boot version.

**Bật observation không cần thiết phải ghi record value.** Metadata và timing thường đủ chẩn đoán.

## 7. Vì sao phải kiểm tra custom instrumentation?

Instrumentations tiêu chuẩn có thể tránh copy payload, nhưng custom code thường làm lộ dữ liệu:

- Custom KafkaListenerObservationConvention hoặc KafkaTemplateObservationConvention.
- Business observation thêm event.toString().
- ProducerInterceptor/ConsumerInterceptor ghi ConsumerRecord.
- Exception recording chứa raw input.
- Database span chứa SQL literal values.
- HTTP span chứa raw URL/query.
- OpenTelemetry Java agent có configuration khác.
- Collector processor hoặc exporter bổ sung attributes.

Vì thế cần review **toàn bộ đường xuất spans**, không chỉ một listener. Một span Kafka an toàn chưa chứng minh toàn trace an toàn.

## 8. Allowlist attributes thay cho blacklist

Một schema observability có thể cho phép:

| Attribute | Giá trị ví dụ | Mục đích |
|---|---|---|
| messaging.system | kafka | Loại hệ thống |
| messaging.operation | send / receive | Loại thao tác |
| messaging.destination.name | orders.events | Topic |
| event.type | OrderCreated | Phân nhóm |
| processing.outcome | success / failed | Kết quả |
| retry.stage | original / retry / dlt | Recovery |
| error.kind | timeout / db_deadlock | Error classification |
| schema.version | 3 | Schema migration |
| component | order-projector | Nguồn xử lý |

Tên attributes là ví dụ gồm cả semantic conventions và application-defined tags; tên theo chuẩn OpenTelemetry có thể thay đổi theo phiên bản.

Không đưa vào:

~~~text
record.value
record.key
full.kafka.headers
customer.email
customer.phone
http.request.body
request.authorization
payment.card_number
exception.raw_input
db.bound_parameter
~~~

Mỗi attribute được duyệt nên có owner, mục đích, format, giới hạn độ dài/cardinality và test. Không thêm field chỉ vì nó có sẵn trên DTO.

## 9. Event type phải được chuẩn hóa

Một producer không tin cậy có thể gửi event.type chứa email hoặc secret. Không ghi giá trị đó trực tiếp.

~~~java
import java.util.Set;

public final class SafeTraceTags {

    private static final Set<String> TYPES =
        Set.of("OrderCreated", "OrderUpdated", "OrderCancelled");

    private SafeTraceTags() {
    }

    public static String eventType(String candidate) {
        if (candidate != null && TYPES.contains(candidate)) {
            return candidate;
        }
        return "other";
    }
}
~~~

Hàm chỉ trả về những enum đã duyệt. Cách tương tự dùng cho retry stage, processing outcome và error category.

Chỉ cắt chuỗi thành 100 ký tự không phải redaction: 100 ký tự có thể đã đủ để lộ một token.

## 10. Business observation an toàn

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
public class ObservedOrderProcessor {

    private final ObservationRegistry registry;
    private final OrderService service;

    public ObservedOrderProcessor(
            ObservationRegistry registry,
            OrderService service) {
        this.registry = registry;
        this.service = service;
    }

    public void process(OrderEvent event) {

        String type = SafeTraceTags.eventType(event.type());

        Observation.createNotStarted("orders.process", registry)
            .lowCardinalityKeyValue("event.type", type)
            .lowCardinalityKeyValue("component", "orders")
            .observe(() -> service.apply(event));
    }
}
~~~

OrderEvent và OrderService là domain classes minh họa. Code không thêm key/value/raw headers. Nếu listener đã có observation mặc định, chỉ tạo business child observation khi mang lại khả năng chẩn đoán rõ, tránh spans trùng không cần thiết.

Cần tiếp tục kiểm tra **exception recording**: handler/exporter có thể lưu exception message từ callback tùy instrumentation.

## 11. Ví dụ sai: POJO.toString() trên current span

~~~java
@KafkaListener(topics = "orders.events")
public void handle(OrderEvent event) {

    Observation current = Observation.currentObservation();

    if (current != null) {
        current.highCardinalityKeyValue(
            "record.value",
            event.toString()
        );
    }

    orderService.apply(event);
}
~~~

Đây là rủi ro vì toString có thể in địa chỉ, tên, số điện thoại hoặc token. highCardinalityKeyValue không phải công cụ masking.

Cách thay thế:

~~~java
@KafkaListener(topics = "orders.events")
public void handle(OrderEvent event) {

    Observation current = Observation.currentObservation();

    if (current != null) {
        current.lowCardinalityKeyValue(
            "event.type",
            SafeTraceTags.eventType(event.type())
        );
    }

    orderService.apply(event);
}
~~~

Ví dụ chỉ áp dụng khi observation context có mặt. Trong hệ thống lớn, một instrumentation policy tập trung thường dễ review hơn việc mỗi listener tự tạo attributes.

## 12. Span name phải ổn định

Tên span tốt:

~~~text
kafka receive
kafka send
order.process
inventory.reserve
payment.authorize
~~~

Tên span không tốt:

~~~text
process order customer@example.invalid
receive user-123456
handle token=TEST_SECRET
~~~

Không ghép raw customer ID, Kafka key, URL query string, payload hay exception message vào tên span. Backend thường index mạnh span names, làm rủi ro dữ liệu và cardinality tăng.

## 13. Span events cũng có thể lộ dữ liệu

Các event như validation_failed, retry_scheduled hay db_commit_completed hữu ích khi phân tích một trace. Nhưng không thêm raw value vào event:

~~~java
// Không an toàn:
span.addEvent("invalid_record=" + record.value());
~~~

Thay bằng một event cố định cùng các thông tin phân loại:

~~~text
event: validation_failed
error.kind: schema_validation
retry.stage: original
schema.version: 3
~~~

Span events không phải dữ liệu tạm thời chỉ ở trong JVM. Chúng có thể được exporter gửi và backend lưu.

## 14. Exception message là một nguồn leak

Một exception có thể chứa JSON input hoặc SQL parameter:

~~~text
Failed to deserialize:
{"email":"canary@example.invalid","token":"TEST_SECRET"}
~~~

Một tracing handler/SDK có thể record exception message, stacktrace hoặc status description. Vì vậy không chỉ kiểm tra custom attributes.

Khuyến nghị:

1. Dùng **exception class** và **error.kind** thay raw message.
2. Không tạo custom exception message bằng cách nối raw payload.
3. Không recordException với exception nhạy cảm mà chưa có policy sanitization.
4. Test các fields exporter tạo từ exception.
5. Kiểm tra cả logging pipeline.
6. Khi cần forensic, dùng DLT/quarantine có ACL và retention.

Ví dụ exception domain an toàn:

~~~java
public class InvalidOrderSchemaException
        extends RuntimeException {

    public InvalidOrderSchemaException() {
        super("INVALID_ORDER_SCHEMA");
    }
}
~~~

Không kết luận mọi exception đều an toàn chỉ vì message của một custom exception đã được chuẩn hóa. Exception từ thư viện có thể đưa raw values vào message.

## 15. Bảng error classification

| error.kind | Ý nghĩa |
|---|---|
| deserialization | Không decode được message |
| schema_validation | Không hợp lệ theo schema |
| dependency_timeout | API hoặc DB timeout |
| db_deadlock | Database deadlock |
| authorization | Không đủ quyền |
| transient_broker | Broker/network lỗi tạm |
| business_rejected | Domain rule từ chối |
| unknown | Chưa phân loại |

Chỉ ghi giá trị thuộc allowlist. Không gắn exception.getMessage() làm error.kind dù hiện tại nó có vẻ không chứa PII.

## 16. Không copy toàn bộ Kafka headers

Ví dụ không an toàn:

~~~java
for (Header header : record.headers()) {
    observation.highCardinalityKeyValue(
        "header." + header.key(),
        new String(header.value(), StandardCharsets.UTF_8)
    );
}
~~~

Headers có thể chứa Authorization, X-User, tenant identity, JWT hoặc baggage. Cả tên header cũng có thể được phía producer kiểm soát.

Cách phù hợp là:

- Không copy tất cả headers vào attributes.
- Trace propagation do framework quản lý.
- Chỉ dùng những headers thuộc allowlist cho xử lý nghiệp vụ.
- Không đưa raw customer/tenant identifiers vào tracing.
- Kiểm tra boundary khi Kafka nhận messages từ producer ngoài hệ thống.

## 17. Traceparent, tracestate và baggage

Kafka tracing có thể truyền context qua headers:

- **traceparent** cho trace/span identity.
- **tracestate** cho thông tin mở rộng theo chuẩn W3C.
- **baggage** cho các key/value có thể truyền xuyên services.

**Baggage không phải kho dữ liệu người dùng.** Không đưa email, số tài khoản, tên khách hàng, JWT hoặc payload vào baggage.

Baggage có thể được propagate từ Kafka sang HTTP, rồi sang nhiều services khác. Một số instrumentation có thể log hoặc ghi baggage. Dù tracing backend hiện tại không lưu baggage, dữ liệu vẫn có thể đã vượt ranh giới bảo mật.

Trace context dùng để liên kết spans, không phải xác thực danh tính hoặc cấp quyền.

## 18. Correlation ID an toàn

Khi cần tìm một workflow, sử dụng **opaque operation ID** đã được policy cho phép thay vì email hoặc customer ID.

Một thiết kế:

1. Tạo opaque ID ngẫu nhiên ở entry point.
2. Giữ mapping ID đến business entity trong database có ACL.
3. Chỉ đưa ID vào tracing nếu privacy owner cho phép.
4. Giới hạn retention và quyền truy ngược.
5. Không suy ra ID trực tiếp từ PII.
6. Không dùng trace ID làm authorization credential.

Ngay cả UUID vẫn có thể là định danh gián tiếp nếu nó liên kết được với profile khách hàng, nên không mặc định mọi opaque ID đều public.

## 19. Hash PII không tự làm dữ liệu an toàn

Hash email hoặc phone rồi thêm vào span vẫn có rủi ro:

- Không gian email/phone có thể bị đoán bằng dictionary attack.
- Hash ổn định cho phép nối nhiều traces theo cùng người.
- Dữ liệu đã hash có thể vẫn được xem là dữ liệu cá nhân theo policy.
- Nhiều systems dùng cùng hash có thể correlation ngoài dự kiến.

Nếu bắt buộc phải pseudonymize, cân nhắc HMAC với secret quản lý an toàn, key rotation, mục đích rõ ràng và security review. Nhưng tốt nhất là không đưa customer-level identifier lên span nếu không thật sự cần.

## 20. Sampling không phải cơ chế privacy

Ví dụ:

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.1
~~~

Sampling 10% làm giảm số traces được lưu, nhưng một trace được sample vẫn có thể chứa payload. Tail sampling còn có thể nhận và buffer spans ở collector trước khi quyết định giữ/bỏ.

Không dùng sampling thấp làm lý do ghi dữ liệu nhạy cảm. Thứ tự ưu tiên đúng là **không capture tại nguồn → redaction/allowlist → exporter protection → sampling theo nhu cầu vận hành**.

## 21. Collector redaction là lớp thứ hai

OpenTelemetry Collector có thể dùng processors hoặc policies để xóa attributes. Tuy nhiên:

- Dữ liệu đã rời ứng dụng trước khi tới collector.
- Collector có thể buffer/log.
- Config có thể không đồng nhất giữa environments.
- Raw data có thể nằm trong span events hoặc exception fields.
- Một exporter khác có thể không đi qua processor mong muốn.
- Attribute mới có thể không nằm trong denylist.

~~~mermaid
flowchart LR
    A["Kafka record"] --> B["Application allowlist"]
    B --> C["Observation / spans"]
    C --> D["Exporter"]
    D --> E["Collector redaction"]
    E --> F["Backend RBAC + retention"]
~~~

**Allowlist tại application là kiểm soát chính; Collector redaction là defense in depth.**

## 22. Producer spans cần được bảo vệ như consumer spans

Một producer có thể ghi payload khi gọi KafkaTemplate.send:

~~~java
// Không an toàn:
observation.highCardinalityKeyValue(
    "producer.payload",
    orderCreated.toString()
);
~~~

Thay bằng operation và metadata:

~~~text
messaging.system = kafka
messaging.operation = send
messaging.destination.name = orders.created
event.type = OrderCreated
~~~

Nếu producer dùng Kafka transaction, send future thành công chưa chắc Kafka transaction đã commit. Không gắn processing.outcome=committed chỉ vì send() được gọi. Tracing outcome phải phản ánh đúng lifecycle.

## 23. Deserialization failure và DLT

Với ErrorHandlingDeserializer hoặc đường deserialize failure tương tự, exception/header có thể mang raw bytes của record lỗi.

- Ghi error.kind=deserialization.
- Ghi topic/partition/offset nếu đã được duyệt.
- Không chuyển raw bytes/Base64 vào span.
- Không copy exception headers.
- Dùng DLT/quarantine được cấp ACL nếu cần giữ failed record.
- Đặt retention/masking riêng cho DLT và công cụ replay.

Base64 không phải mã hóa bảo mật.

Khi record đi qua retry/DLT, không tạo nhiều bản sao payload trên spans của main, retry và DLT listeners. Chỉ dùng retry stage, attempt category và error kind.

## 24. Kafka transactions và recovery

Một pipeline transactional có thể có spans cho consume, produce, commit/abort và AfterRollbackProcessor. Những spans này có giá trị khi điều tra lỗi exactly-once:

| Attribute | Ví dụ |
|---|---|
| transaction.outcome | committed / aborted / unknown |
| retry.stage | original / retry |
| processing.outcome | failure |
| error.kind | dependency_timeout |
| messaging.destination.name | orders.events |

Không gắn payload hoặc key để “nhìn cho rõ transaction nào bị abort”. Nếu cần, dùng trace ID và topic/partition/offset đã duyệt để tìm dữ liệu trong Kafka/DLT có kiểm soát.

Một transaction abort không tự cho phép ghi raw failed record lên telemetry.

## 25. HTTP và database spans cũng cần sạch

Một Kafka consumer thường gọi database hoặc REST API. Các spans downstream có thể làm lộ dữ liệu dù Kafka spans không có payload.

Không nên:

~~~java
String sql =
    "SELECT * FROM customers WHERE email='" + email + "'";

span.setAttribute("db.statement", sql);
~~~

Dùng parameterized SQL và không capture bound values. Nếu cần query text, dùng operation name hoặc normalized statement phù hợp.

HTTP tracing nên dùng route template:

~~~text
Safe:   GET /customers/{customerId}/orders
Unsafe: GET /customers/canary@example.invalid/orders?token=TEST_SECRET
~~~

Không ghi Authorization, cookies, request/response bodies hoặc raw query parameters vào span.

## 26. Multi-tenant metadata có thể nhạy cảm

Trong multi-tenant Kafka, topic hoặc group name có thể nhúng tenant identity:

~~~text
tenant-123.orders
orders-customer-name
~~~

Đừng mặc định topic.name, consumer.group hay tenant.tier luôn public. Có thể dùng logical classifications như workload=order-processing và topic.family=orders theo chính sách.

Nếu tracing backend cho phép nhiều tenants truy cập cùng một hệ thống, data minimization còn quan trọng hơn. Không để trace attributes tiết lộ thông tin tenant khác.

## 27. Chính sách tagging tập trung

Dùng helper hoặc custom ObservationConvention tập trung:

~~~java
import java.util.Map;
import java.util.Set;

public final class KafkaTraceTagPolicy {

    private static final Set<String> ALLOWED =
        Set.of("OrderCreated", "OrderUpdated", "OrderCancelled");

    private KafkaTraceTagPolicy() {
    }

    public static Map<String, String> safeTags(
            String type,
            boolean isRetry) {

        String safeType =
            type != null && ALLOWED.contains(type)
                ? type
                : "other";

        return Map.of(
            "event.type", safeType,
            "retry.stage", isRetry ? "retry" : "original"
        );
    }
}
~~~

Spring Kafka có KafkaListenerObservationConvention và KafkaTemplateObservationConvention ở những phiên bản hỗ trợ customization. Khi implement, chỉ trả KeyValues từ allowlist; không duyệt toàn bộ record.value() hoặc headers.

Một helper không thể chặn mọi instrumentation path: phải review Micrometer bridge, OpenTelemetry agent và backend config.

## 28. Test helper bằng JUnit

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import org.junit.jupiter.api.Test;

class SafeTraceTagsTest {

    @Test
    void untrustedValueMustNotAppear() {

        String input = "OrderCreated token=TEST_SECRET";
        String result = SafeTraceTags.eventType(input);

        assertThat(result).isEqualTo("other");
        assertThat(result).doesNotContain("TEST_SECRET");
    }

    @Test
    void knownTypeIsAllowed() {
        assertThat(
            SafeTraceTags.eventType("OrderCreated")
        ).isEqualTo("OrderCreated");
    }
}
~~~

Dùng dữ liệu test giả, không secret thật. Test helper là cần thiết nhưng chưa đủ vì exception handler hoặc agent có thể thêm attributes ở đường khác.

## 29. Integration test với exporter

Một test quan trọng phải kiểm tra **dữ liệu spans cuối cùng được export** bằng in-memory span exporter hoặc fake OTLP collector:

1. Tạo Kafka record với canary email, token và nested private field giả.
2. Cho Spring Kafka listener xử lý thành công.
3. Thu producer, consumer và business spans.
4. Kiểm tra names, attributes, events, exception fields, status descriptions.
5. Assert không chứa canary values hoặc raw JSON.
6. Assert vẫn có những attributes được phê duyệt.
7. Gây exception chứa canary string.
8. Test deserialization failures, retry topics và DLT.
9. Test key/headers chứa dữ liệu giả nhạy cảm.
10. Test HTTP/DB downstream spans.
11. Lặp lại khi nâng Micrometer, Spring Kafka hoặc OpenTelemetry agent.

Không chỉ kiểm tra ObservationRegistry trước khi export; tracing bridge/SDK có thể thêm dữ liệu sau đó.

## 30. Canary payload kiểm thử

~~~json
{
  "eventType": "OrderCreated",
  "eventId": "test-event-001",
  "customer": {
    "email": "canary-person@example.invalid",
    "address": "PRIVATE_CANARY_ADDRESS"
  },
  "credential": {
    "token": "TEST_SECRET_DO_NOT_EXPORT"
  }
}
~~~

Tất cả là dữ liệu giả. Exporter test tìm canary trong span attributes, events, status và exception details. Nếu cần, kiểm tra thêm những encoding transformations như Base64 hay URL encoding.

Canary scanning không thay thế allowlist: chính sách vẫn phải không thêm raw payload vào span từ đầu.

## 31. Điều tra sự cố mà không cần payload trên trace

Khi một record gây lỗi:

1. Dùng trace ID xác định service và listener.
2. Xem topic/partition/offset nếu policy cho phép.
3. Xem event.type, schema.version, retry.stage.
4. Xem error.kind và latency.
5. Kiểm tra consumer lag, transaction commit/abort và DLT.
6. Nếu cần raw payload, sử dụng công cụ Kafka/DLT/quarantine có ACL, audit và masking.
7. Đối chiếu business state trong database theo quyền được cấp.
8. Không copy payload vào span hay shared ticket/log để tiện truy vấn.

Tracing có nhiệm vụ **chỉ ra nơi cần điều tra**, không biến tracing backend thành kho dữ liệu nghiệp vụ.

## 32. Bảo vệ exporter và backend

Một hệ thống production cần:

- TLS và authentication cho exporter/collector.
- Network policy và endpoint được duyệt.
- RBAC cho trace backend.
- Tenant isolation.
- Retention giới hạn.
- Audit truy cập/export.
- Kiểm soát debug exporter và log ở collector.
- Kiểm tra việc đưa traces vào chat, ticket hoặc dashboard.
- Quy trình purge/delete khi phát hiện leak.
- Secret rotation nếu tokens bị lộ.

Ngay cả traces không chứa payload vẫn có thông tin vận hành/kiến trúc cần bảo vệ.

## 33. Runbook khi phát hiện sensitive data trong spans

1. Xác định field đang leak và loại dữ liệu.
2. Tìm instrumentation path: Kafka listener, producer, business observation, exception, baggage hoặc HTTP/DB.
3. Ngừng capture tại nguồn; cân nhắc giới hạn exporter theo incident policy.
4. Xác định collector và backends nhận dữ liệu.
5. Hạn chế quyền truy cập traces affected.
6. Tìm bản sao trong logs, dashboards, alerts, tickets hoặc screenshots.
7. Purge dữ liệu theo khả năng backend và quy trình bảo mật.
8. Rotate/revoke secret nếu token bị lộ.
9. Báo security/privacy owner theo mức độ sự cố.
10. Thêm regression test canary.
11. Deploy fix và kiểm tra spans mới.
12. Ghi audit và biện pháp ngăn tái diễn.

Chỉ ẩn attribute khỏi UI không xóa dữ liệu đã có trong backend hoặc exports khác.

## 34. Anti-patterns thường gặp

**Ghi DTO.toString() lên span.** Có thể chứa toàn bộ PII.

**Đưa record.key() vào highCardinalityKeyValue.** Key có thể là account/email.

**Copy Kafka headers thành attributes.** Headers có thể chứa secrets và baggage.

**Dùng span name có customer ID.** Vừa leak dữ liệu vừa tăng cardinality.

**Ghi exception.getMessage() không kiểm tra.** Nó có thể chứa raw payload/SQL/URL.

**Dùng sampling thấp như biện pháp privacy.** Sampled traces vẫn lộ.

**Chỉ dựa vào collector denylist.** Dữ liệu đã rời application, field mới có thể lọt.

**Hash email rồi coi là anonymous.** Hash có thể bị đoán và dùng để liên kết.

**Lưu payload lỗi vào DLT rồi lại copy lên span.** Làm tăng bản sao không kiểm soát.

**Chỉ kiểm tra Kafka span.** DB/HTTP spans trong cùng trace vẫn có thể leak.

**Coi tracing backend như secure business audit store.** Tracing có retention, quyền truy cập và mục đích khác.

## 35. Checklist trước production

**Policy**

- [ ] Key/value/headers và exception messages đã được phân loại.
- [ ] Không có payload trong span names, attributes, events.
- [ ] Không copy headers hoặc baggage không tin cậy.
- [ ] Event type/error.kind dùng allowlist.
- [ ] Không coi high cardinality là privacy-safe.
- [ ] Correlation IDs không trực tiếp chứa PII.

**Spring Kafka/Micrometer**

- [ ] Observation bật có chủ đích.
- [ ] Custom conventions được review.
- [ ] Business spans không gọi DTO.toString().
- [ ] Exception capture được kiểm tra.
- [ ] Retry/DLT/deserialization paths không leak.
- [ ] HTTP/DB spans tuân theo chính sách tương tự.

**Telemetry**

- [ ] Exporter/collector dùng TLS/authentication.
- [ ] Collector redaction là defense in depth.
- [ ] Backend có RBAC, audit và retention.
- [ ] Sampling không được dùng làm privacy control.
- [ ] Có incident playbook.

**Testing**

- [ ] Unit test allowlist.
- [ ] Integration test exporter output.
- [ ] Canary trong key/value/header/exception.
- [ ] Test success, error, retry và DLT.
- [ ] Regression test sau nâng dependencies/agent.

## 36. Kết luận

**Không đưa payload nhạy cảm vào span** là nguyên tắc thiết kế then chốt khi sử dụng Observation và distributed tracing trong Spring Kafka. Một trace hữu ích có thể mô tả topic, operation, event type đã duyệt, retry stage, error category và processing duration mà không cần chứa message value, customer identifier hay secret.

Hãy quản lý cả **Kafka key/value/headers, span attributes/events, exception information, baggage và downstream HTTP/DB spans**. Áp dụng allowlist tại nguồn; dùng collector redaction và backend RBAC làm lớp phòng thủ bổ sung; kiểm thử exported spans với canary data. Sampling giúp tối ưu telemetry cost, không phải kỹ thuật che payload.

Khi cần xem raw record để debug, dùng Kafka/DLT/quarantine và business audit tooling có cấp quyền thay vì đưa nó vào tracing. Như vậy hệ thống giữ được khả năng quan sát reliability trong production mà vẫn bảo vệ dữ liệu nhạy cảm.
