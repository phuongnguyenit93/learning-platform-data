# Phân biệt envelope với payload nghiệp vụ

## 1. Vấn đề: cùng một đơn hàng, nhiều lớp thông tin

Trong một hệ thống tích hợp, dịch vụ đặt hàng gửi sự kiện `OrderPlaced` sang các nhánh kiểm kho, gửi thông báo và lưu audit. Dữ liệu nghiệp vụ nói về **đơn hàng nào, số tiền bao nhiêu, những mặt hàng nào**; còn hệ thống truyền thông điệp phải biết **sự kiện đến từ đâu, theo schema nào, gửi khi nào, thuộc tenant nào, dùng ID nào để truy vết hoặc phát lại**.

Nếu nhét mọi thông tin này vào một DTO `OrderPlaced`, DTO nghiệp vụ sẽ phụ thuộc vào broker, trace, routing và cơ chế retry. Ngược lại, nếu chỉ gửi payload mà không kèm ngữ cảnh, consumer khó xác thực nguồn, chọn schema, chống trùng hoặc tìm lại các lần giao thất bại.

**Envelope Wrapper** là một Enterprise Integration Pattern dùng **một lớp vỏ (envelope)** chứa dữ liệu nghiệp vụ (**payload**) cùng metadata phục vụ giao tiếp giữa các hệ thống. Tách hai lớp giúp payload mô tả điều đã xảy ra hoặc điều cần làm, còn envelope mô tả **cách thông điệp được nhận diện, diễn giải, bảo vệ và vận chuyển**.

~~~mermaid
flowchart LR
    P["Order service: OrderPlaced"] --> W["Envelope Wrapper"]
    W --> E["Envelope metadata + business payload"]
    E --> B["Broker / HTTP / JMS"]
    B --> U["Unwrap + validate"]
    U --> D["OrderPlaced domain payload"]
    U --> H["Trusted routing / trace metadata"]
    D --> X["Inventory / Notification / Audit"]
    H --> X
~~~

Bài học thuộc chương **Envelope wrapper** trong module `SPRING_INTEGRATION_PATTERN`. Mục tiêu module là học triển khai Enterprise Integration Patterns với Spring Integration để tạo luồng thông điệp ít phụ thuộc, dễ mở rộng; thực hành Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, correlation và kiểm thử/quan sát các nhánh xử lý.

### Sau bài này, bạn sẽ làm được gì?

1. Nêu ranh giới chính xác giữa **business payload**, **application envelope**, **Spring `Message<?>`** và **transport envelope/headers**.
2. Chọn metadata cần có cho event identity, schema version, nguồn, tenant, correlation, causation và tracing.
3. Tránh nhét thông tin hạ tầng vào domain object hoặc coi metadata do caller cấp là đáng tin.
4. Viết Java record cho domain payload và envelope, triển khai wrap/unwrap qua Spring Integration Java DSL.
5. Kiểm soát header mapping khi đổi transport, tạo message mới, split/aggregate hoặc retry.
6. Thiết kế schema evolution, idempotency, security, audit, DLQ/quarantine và replay theo đúng ranh giới.
7. Kiểm thử payload không bị biến dạng và metadata quan trọng không bị mất, nhân đôi hoặc bị dùng sai.

## 2. Định nghĩa chính xác bốn lớp

### 2.1. Business payload: dữ liệu mang ý nghĩa nghiệp vụ

Ví dụ:

~~~json
{
  "orderId": "ORD-1001",
  "customerId": "C-17",
  "amountVnd": 850000,
  "items": [
    {"sku": "SKU-A", "quantity": 2}
  ]
}
~~~

Payload cho biết nội dung của một đơn hàng. Nó **không cần biết** message được gửi qua Kafka topic nào, HTTP request header nào hoặc tracing span hiện tại là gì.

Một payload cũng có thể chứa các định danh **thuộc nghiệp vụ** như `orderId`, `paymentId`, `businessVersion`; không phải cứ có chữ “ID” là metadata envelope. Quy tắc là **trường đó còn có ý nghĩa khi không có hệ thống messaging hay không?** Nếu vẫn cần cho nghiệp vụ, nhiều khả năng nó thuộc payload/domain contract.

### 2.2. Application envelope: cấu trúc bao quanh payload

Ví dụ một hợp đồng giao tiếp:

~~~json
{
  "messageId": "MSG-1001",
  "eventType": "order.placed",
  "schemaVersion": 1,
  "source": "order-service",
  "tenantId": "TENANT-A",
  "occurredAt": "2026-11-21T02:30:00Z",
  "correlationId": "CHECKOUT-88",
  "causationId": "CMD-449",
  "payload": {
    "orderId": "ORD-1001",
    "customerId": "C-17",
    "amountVnd": 850000,
    "items": [
      {"sku": "SKU-A", "quantity": 2}
    ]
  }
}
~~~

Những metadata này có thể dùng để chọn schema, kiểm tra độ tương thích, gắn correlation, chống duplicate và điều tra sự cố. Nhưng **không có nghĩa mọi envelope phải có đúng tất cả trường trên**. Hợp đồng cần được thiết kế theo loại tích hợp; field nào không có mục đích rõ ràng có thể làm tăng chi phí hoặc rò rỉ dữ liệu.

### 2.3. Spring Integration message: `Message<T>` gồm payload và headers

Spring Messaging mô hình hóa:

~~~text
Message<T>
  payload: T
  headers: MessageHeaders
~~~

Trong JVM, một Spring `Message<OrderPlaced>` có thể dùng payload domain ở phần `getPayload()` và headers làm metadata kỹ thuật: `MessageHeaders.ID`, `TIMESTAMP` và các header do ứng dụng đặt.

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<String> message = MessageBuilder
        .withPayload("ORD-1001")
        .setHeader("eventType", "order.placed")
        .setHeader("schemaVersion", 1)
        .build();

String payload = message.getPayload(); // ORD-1001
Object type = message.getHeaders().get("eventType");
~~~

**Không đồng nhất `MessageHeaders` với application envelope trên wire.** Headers trong JVM có thể mang objects nội bộ như `replyChannel`/`errorChannel`. Khi đi qua broker hoặc HTTP, adapter/header mapper có thể chuyển đổi, bỏ hoặc sinh lại headers; Spring `MessageHeaders.ID` cũng có thể đổi khi xây dựng message mới. Một record JSON envelope và một Spring `Message<?>` là **hai mô hình ở hai lớp**, dù có những trường tương ứng.

### 2.4. Transport envelope: định dạng/metadata của broker hoặc HTTP

Một Kafka record có topic, partition, offset, key, headers và value. Một HTTP request có method, path, headers và body. JMS có các header/properties và body theo chuẩn của nó.

~~~text
Kafka record
  topic = orders.events
  partition = 2
  offset = 721
  key = ORD-1001
  headers = {content-type, traceparent, ...}
  value = serialized application envelope
~~~

**Offset không phải domain order version** và **HTTP request ID không mặc nhiên là business event ID**. Transport có thể giao lại hoặc republish cùng một logical event dưới tọa độ record mới.

### 2.5. Bảng so sánh nhanh

| Đối tượng | Chứa gì | Chủ sở hữu contract | Khi nào có thể đổi? |
|---|---|---|---|
| **Domain payload** | Order, payment, customer, item data. | Business/domain team. | Khi nghiệp vụ hoặc domain schema thay đổi. |
| **Application envelope** | Message/event identity, source, type, schema, correlation, payload. | Hợp đồng tích hợp giữa producer và consumer. | Khi chuẩn event/transport contract thay đổi. |
| **Spring `Message<?>`** | Một payload object + `MessageHeaders` trong luồng Spring. | Framework và integration flow. | Khi Transformer/adapter xây message mới hoặc enrich headers. |
| **Transport record/envelope** | Topic/partition/offset, wire headers, request metadata. | Broker/protocol/adapter. | Mỗi lần publish/delivery/retry theo transport. |

### 2.6. Một sơ đồ phân lớp

~~~mermaid
flowchart TB
    subgraph Transport["Transport layer: Kafka / HTTP / JMS"]
      R["Record / Request headers, offsets, routing"]
      subgraph Application["Application envelope (serialized)"]
        M["messageId, type, version, source, correlation"]
        subgraph Domain["Business payload"]
          O["orderId, amountVnd, items"]
        end
      end
    end
~~~

Sơ đồ là một **cách đóng gói có thể chọn**, không phải bắt buộc trong mọi flow. Một hệ thống có thể truyền envelope metadata bằng Kafka headers và chỉ serialise payload vào value. Dù vậy, vẫn phải có contract rõ để consumer tái tạo đúng message identity/schema sau khi đi qua transport.

## 3. Quy tắc phân loại một trường dữ liệu

Đặt lần lượt các câu hỏi:

1. **Trường này có tồn tại nếu không dùng broker/HTTP/message framework không?** Ví dụ `orderId` và `amountVnd`: có, nên thuộc domain.
2. **Nó mô tả một business fact hay cách phân phối/diễn giải message?** `eventType`, `schemaVersion` có thể thuộc envelope.
3. **Nó là định danh của operation hay chỉ của một lần giao?** `paymentOperationId` là business identity; `deliveryAttempt` không phải.
4. **Ai được quyền cấp/đổi?** `tenantId` có thể là business attribute nhưng **trusted tenant scope** tại integration boundary phải được lấy từ principal/adapter, không chỉ tin payload.
5. **Consumer nào thật sự cần?** Không thêm metadata nhạy cảm vào mọi envelope chỉ vì một nhánh có thể dùng.

| Trường | Vị trí đề xuất | Lý do |
|---|---|---|
| `orderId` | Payload | Một business entity ID. |
| `amountVnd` | Payload | Giá trị nghiệp vụ. |
| `customerId` | Payload hoặc reference được bảo vệ | Dữ liệu nghiệp vụ, có yêu cầu privacy. |
| `eventType` | Envelope | Hợp đồng loại message/dispatch/schema. |
| `schemaVersion` | Envelope | Giúp consumer chọn decoder/upcaster. |
| `messageId/eventId` | Envelope, đôi khi cả domain event record | Stable logical-event identity; cần thống nhất nguồn sự thật. |
| `sourceSystem` | Envelope/trusted ingress metadata | Audit, compatibility và provenance. |
| `correlationId` | Envelope/Spring header | Ghép request/flows có liên quan. |
| `causationId` | Envelope | Liên kết nguyên nhân: message nào tạo ra message này. |
| `traceparent` | Wire header/envelope theo contract | Distributed tracing, không phải business idempotency. |
| `deliveryAttempt` | Transport/runtime diagnostics | Có thể tăng khi retry, không thuộc business payload. |
| `topic/partition/offset` | Transport metadata | Tọa độ Kafka, không phải domain field. |
| `businessVersion` | Payload hoặc domain event metadata | Thứ tự thay đổi business aggregate, khác schemaVersion. |
| `replyChannel` Spring object | Nội bộ Spring message | Không phải wire-portable destination. |

**Trường hợp biên:** `tenantId` và `eventId` có thể xuất hiện ở cả payload và envelope do contract cũ hoặc lý do portability. Khi đó định nghĩa **nguồn sự thật và đối chiếu equality**, không âm thầm ưu tiên giá trị thuận tiện nhất. Mâu thuẫn giữa tenant trong payload và principal phải dẫn tới xác minh hoặc reject theo policy.

## 4. Java: mô hình domain payload độc lập với message transport

### 4.1. Tạo DTO nghiệp vụ bất biến

~~~java
import java.math.BigDecimal;
import java.util.List;
import java.util.Objects;

record OrderLine(String sku, int quantity) {
    OrderLine {
        if (sku == null || sku.isBlank() || quantity <= 0) {
            throw new IllegalArgumentException("INVALID_ORDER_LINE");
        }
    }
}

record OrderPlaced(
        String orderId,
        String customerId,
        BigDecimal amountVnd,
        List<OrderLine> items) {

    OrderPlaced {
        if (orderId == null || orderId.isBlank()
                || customerId == null || customerId.isBlank()
                || amountVnd == null || amountVnd.signum() <= 0) {
            throw new IllegalArgumentException("INVALID_ORDER");
        }
        Objects.requireNonNull(items, "items");
        items = List.copyOf(items);
        if (items.isEmpty()) {
            throw new IllegalArgumentException("EMPTY_ORDER");
        }
    }
}
~~~

**Quan sát:** `OrderPlaced` không import `Message`, `KafkaHeaders`, Spring Integration, HTTP hay tracing. DTO này có thể được kiểm thử như Java thuần và sử dụng từ những luồng khác mà không gắn chặt với transport.

Trong ví dụ, validation trong constructor chỉ đảm bảo các invariant cơ bản của DTO. Nếu cần chấp nhận dữ liệu sai để quarantine, hãy decode vào **ingress DTO chưa được tin cậy**, validate và chỉ tạo `OrderPlaced` đã được xác nhận sau đó. Không bắt mọi lỗi constructor rồi coi là “không có message”.

### 4.2. Application envelope generic

~~~java
import java.time.Instant;
import java.util.Objects;

record EventEnvelope<T>(
        String messageId,
        String eventType,
        int schemaVersion,
        String source,
        String tenantId,
        Instant occurredAt,
        String correlationId,
        String causationId,
        T payload) {

    EventEnvelope {
        if (blank(messageId)
                || blank(eventType)
                || blank(source)
                || blank(tenantId)
                || schemaVersion < 1) {
            throw new IllegalArgumentException(
                    "INVALID_ENVELOPE_METADATA");
        }
        Objects.requireNonNull(occurredAt, "occurredAt");
        Objects.requireNonNull(payload, "payload");
    }

    private static boolean blank(String value) {
        return value == null || value.isBlank();
    }
}
~~~

`EventEnvelope<T>` biểu diễn **hợp đồng giữa hai service**: envelope có identity/type/version/provenance, còn `payload` là dữ liệu nghiệp vụ. Generic giúp nêu khái niệm trong Java, nhưng **không đảm bảo runtime JSON deserializer tự biết `T`**. Khi nhận JSON, cần chọn type bằng event type/schema rồi map payload theo contract an toàn.

### 4.3. Tạo một envelope không làm thay đổi payload

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

OrderPlaced order = new OrderPlaced(
        "ORD-1001",
        "C-17",
        new BigDecimal("850000"),
        List.of(new OrderLine("SKU-A", 2)));

EventEnvelope<OrderPlaced> envelope = new EventEnvelope<>(
        "EVT-1001",
        "order.placed",
        1,
        "order-service",
        "TENANT-A",
        Instant.parse("2026-11-21T02:30:00Z"),
        "CHECKOUT-88",
        "CMD-449",
        order);

// envelope.payload().equals(order) == true
// envelope.schemaVersion() == 1
~~~

Trong production, `messageId` nên được cấp **một lần ở source of truth/outbox** và giữ nguyên khi **republish cùng logical event**. Nếu sinh UUID mới ở mỗi consumer attempt, dedupe không biết đây là cùng sự kiện. Không dùng một `messageId` cho hai event khác nhau chỉ vì có cùng `orderId`.

## 5. Envelope không nên trở thành một “god object”

Một wrapper lớn có thể chứa quá nhiều thông tin không liên quan:

~~~text
Envelope:
  payload
  58 debug flags
  raw security token
  database connection details
  client password
  internal Java MessageChannel object
  every upstream HTTP header
~~~

Đây không còn là lớp vỏ tích hợp hữu ích mà là một kênh **phát tán dữ liệu không kiểm soát**. Một envelope tốt:

- Chứa **metadata cần thiết và được version hóa**.
- Có giới hạn kích thước, schema và allowed fields.
- Không sao chép credentials/token/PII khi consumer không cần.
- Không chứa **internal JVM object** không wire-portable.
- Có một nguồn sự thật cho identity và tenant.
- Để payload giữ ngữ nghĩa domain.
- Phân biệt **immutable logical event metadata** với **delivery diagnostics có thể đổi**.

### 5.1. Metadata bất biến và metadata theo lần giao

| Nhóm | Ví dụ | Có nên giữ khi broker redeliver? |
|---|---|---|
| Logical event identity | `messageId/eventId`, `eventType`, `source`, `occurredAt` | Có, nếu cùng logical event. |
| Schema contract | `schemaVersion`, encoding/content type contract | Có, trừ khi có bước chuyển đổi version được ghi dấu. |
| Business correlation | `correlationId`, `causationId` | Thường có, theo workflow contract. |
| Trusted tenant scope | `tenantId` đối chiếu principal | Cần giữ/bind nhất quán, không dựa vào dữ liệu tự xưng. |
| Delivery attempt | `deliveryAttempt`, `lastReceivedAt` | Có thể tăng/thay đổi. |
| Broker placement | topic, partition, offset | Có thể thay khi republish. |
| Tracing runtime | `spanId`, sampling flags | Có thể khác qua consumer attempts; liên kết trace khi cần. |
| Processing state | retry count, last error, lock owner | Thường thuộc vận hành/store, không phải bất biến của event. |

**Không ghi đè `occurredAt` bằng “thời điểm nhận”** khi redelivery. Nếu cần quan sát độ trễ, dùng thêm `receivedAt` hoặc log riêng; hai timestamp trả lời hai câu hỏi khác nhau.

### 5.2. Phân biệt schema version và business version

~~~text
schemaVersion = 2
  -> cách mã hóa event: trường nào có mặt, tên gì, type gì

orderVersion = 15
  -> trạng thái/thứ tự thay đổi của business order ORD-1001
~~~

Một sự kiện theo schema v2 **không mặc nhiên là lần thay đổi thứ hai** của order. Nếu Resequencer cần sắp các events của một order, phải dùng một **business sequence/version** có contract, không dùng `schemaVersion`.

## 6. Wire envelope và contract JSON

### 6.1. JSON là một biểu diễn, không phải toàn bộ ý nghĩa envelope

Với Spring Integration, envelope có thể đi trên wire theo nhiều cách:

**Cách A — body chứa application envelope:**

~~~json
{
  "messageId": "EVT-1001",
  "eventType": "order.placed",
  "schemaVersion": 1,
  "source": "order-service",
  "tenantId": "TENANT-A",
  "occurredAt": "2026-11-21T02:30:00Z",
  "payload": {
    "orderId": "ORD-1001",
    "customerId": "C-17",
    "amountVnd": 850000,
    "items": [{"sku": "SKU-A", "quantity": 2}]
  }
}
~~~

**Cách B — metadata trong broker headers và payload trong record value:**

~~~text
Kafka headers:
  event-id       = EVT-1001
  event-type     = order.placed
  schema-version = 1
  source         = order-service

Kafka value:
  {"orderId":"ORD-1001", ...}
~~~

Hai cách đều có thể phù hợp. Nhưng nếu chuyển từ Kafka sang HTTP mà chỉ copy `value`, cách B sẽ **mất metadata**. Cần một **adapter mapping contract** để xây lại application envelope hoặc forward các headers bắt buộc.

### 6.2. Chọn schema và payload type bằng allowlist

Không deserialize object dựa trên tên class bất kỳ do caller gửi, ví dụ:

~~~json
{"javaClass": "com.some.reflective.Class", "payload": {}}
~~~

Chọn từ registry/allowlist:

| `eventType` | `schemaVersion` | Target DTO |
|---|---:|---|
| `order.placed` | 1 | `OrderPlacedV1` hoặc `OrderPlaced` tương thích. |
| `order.cancelled` | 1 | `OrderCancelledV1`. |
| `payment.confirmed` | 2 | `PaymentConfirmedV2`. |

Nếu type/version không hỗ trợ, trả lỗi có cấu trúc và route sang **unsupported-schema quarantine**/DLQ theo policy. Không bỏ qua phiên bản rồi ép JSON về một DTO bất kỳ, vì có thể mất field hoặc đổi nghĩa số tiền.

### 6.3. Raw và typed payload không có cùng cơ hội được validate

~~~text
Raw bytes
  -> Content-type/size/security checks
  -> Parse wire envelope metadata
  -> Validate eventType + schemaVersion
  -> Deserialize typed payload
  -> Validate domain invariants
  -> Build Spring Message<T>
~~~

Một JSON bị cắt có thể lỗi **trước** khi tạo được `EventEnvelope<T>`. Một schema không nhận diện có thể lỗi **trước** khi map payload. Một business amount âm có thể decode được nhưng không đạt domain validation. Các đường lỗi này cần **reason code và recovery riêng**, không gộp thành một boolean “invalid”.

### 6.4. Không tin `source` và `tenantId` chỉ vì nằm trong envelope

Client có thể gửi:

~~~json
{"source":"trusted-service","tenantId":"TENANT-A","payload":{}}
~~~

Đây mới là **lời khai của message**, không phải xác thực nguồn. Inbound adapter phải xác thực chữ ký/mTLS/broker ACL/principal theo kiến trúc, rồi đối chiếu envelope metadata. Nếu không khớp, **reject hoặc quarantine ở trust boundary**, không forward dữ liệu sang tenant được khai trong JSON.

## 7. Wrap và unwrap: hai thao tác có trách nhiệm khác nhau

### 7.1. Wrap là tạo một thông điệp có ngữ cảnh

~~~text
Business event OrderPlaced
    + source-of-truth eventId
    + producer identity
    + schema version / occurredAt
    + authorized tenant scope
      -> EventEnvelope<OrderPlaced>
~~~

**Không sinh lại event ID ở mỗi attempt publish.** Với transactional outbox, original event và envelope metadata nên được chốt trước khi đưa vào hàng phát; outbox relay có thể gửi lại **cùng logical event** với cùng `messageId`.

Ví dụ Java:

~~~java
import java.time.Instant;
import java.util.Objects;

record OrderDispatch(
        String sourceEventId,
        String sourceSystem,
        String tenantId,
        Instant occurredAt,
        String correlationId,
        String causationId,
        OrderPlaced order) {}

final class OrderEnvelopeWriter {

    EventEnvelope<OrderPlaced> wrap(OrderDispatch request) {
        Objects.requireNonNull(request, "request");
        // sourceEventId phải đến từ event store/outbox có thẩm quyền.
        return new EventEnvelope<>(
                request.sourceEventId(),
                "order.placed",
                1,
                request.sourceSystem(),
                request.tenantId(),
                request.occurredAt(),
                request.correlationId(),
                request.causationId(),
                request.order());
    }
}
~~~

Một số hệ thống sẽ ký/mã hóa message sau khi serialize envelope; số khác ký raw canonical representation rồi chuyển đi. **Đừng tự nói object Java đã được bảo mật chỉ vì nó được bọc trong envelope**. Xác thực, mã hóa và integrity nằm ở ranh giới transport/storage và hợp đồng bảo mật.

### 7.2. Unwrap là kiểm tra rồi chuyển về payload phù hợp

~~~text
Receive envelope
  -> validate authenticated source / tenant
  -> validate eventType + schemaVersion
  -> choose safe payload decoder
  -> domain validation
  -> build Spring Message<OrderPlaced> + selected headers
  -> business flow
~~~

Không chỉ làm `envelope.payload()` rồi bỏ mọi metadata. Consumer cần giữ **các trường phục vụ idempotency, correlation, audit và tracing** ở nơi phù hợp. Đồng thời không copy mọi input header không rõ nguồn sang internal message.

### 7.3. Trusted ingress context là đầu vào riêng

Để minh họa trust boundary:

~~~java
record TrustedOrderIngress(
        EventEnvelope<OrderPlaced> envelope,
        String authenticatedTenant,
        String authenticatedSource) {
    TrustedOrderIngress {
        if (envelope == null
                || authenticatedTenant == null
                || authenticatedSource == null) {
            throw new IllegalArgumentException(
                    "MISSING_TRUSTED_INGRESS_CONTEXT");
        }
    }
}
~~~

`authenticatedTenant` và `authenticatedSource` **không** phải field người gửi tùy ý chèn vào JSON. Trong demo, test tạo trực tiếp context đã xác thực để tập trung vào mapping. Production phải lấy chúng từ broker ACL, mTLS, signed identity hoặc server-side security context và không được cấp cho caller quyền tự đặt.

### 7.4. Header names thuộc một internal contract

~~~java
final class EnvelopeHeaders {
    static final String EVENT_ID = "businessEventId";
    static final String EVENT_TYPE = "eventType";
    static final String SCHEMA_VERSION = "schemaVersion";
    static final String SOURCE = "trustedSource";
    static final String TENANT = "trustedTenant";
    static final String CORRELATION = "businessCorrelationId";
    static final String CAUSATION = "causationId";
    static final String OCCURRED_AT = "occurredAt";

    private EnvelopeHeaders() {}
}
~~~

Đặt tên `businessEventId` thay vì `id` tránh nhầm với `MessageHeaders.ID` của Spring. Trong một dự án có nhiều loại message, nên chuẩn hóa prefix/namespace/allowed header types và kiểm tra với header mapper của các adapter thực tế.

### 7.5. Converter giữ business payload và chọn lọc metadata

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

final class OrderEnvelopeReader {

    Message<OrderPlaced> unwrap(TrustedOrderIngress ingress) {
        EventEnvelope<OrderPlaced> envelope = ingress.envelope();

        if (!envelope.tenantId().equals(
                    ingress.authenticatedTenant())) {
            throw new SecurityException(
                    "ENVELOPE_TENANT_MISMATCH");
        }
        if (!envelope.source().equals(
                    ingress.authenticatedSource())) {
            throw new SecurityException(
                    "ENVELOPE_SOURCE_MISMATCH");
        }
        if (!"order.placed".equals(envelope.eventType())
                || envelope.schemaVersion() != 1) {
            throw new IllegalArgumentException(
                    "UNSUPPORTED_ENVELOPE_CONTRACT");
        }

        // Payload đã được decode + domain-validated ở ví dụ typed.
        MessageBuilder<OrderPlaced> builder =
                MessageBuilder.withPayload(envelope.payload())
                        .setHeader(
                                EnvelopeHeaders.EVENT_ID,
                                envelope.messageId())
                        .setHeader(
                                EnvelopeHeaders.EVENT_TYPE,
                                envelope.eventType())
                        .setHeader(
                                EnvelopeHeaders.SCHEMA_VERSION,
                                envelope.schemaVersion())
                        .setHeader(
                                EnvelopeHeaders.SOURCE,
                                ingress.authenticatedSource())
                        .setHeader(
                                EnvelopeHeaders.TENANT,
                                ingress.authenticatedTenant())
                        .setHeader(
                                EnvelopeHeaders.OCCURRED_AT,
                                envelope.occurredAt());

        if (envelope.correlationId() != null) {
            builder.setHeader(
                    EnvelopeHeaders.CORRELATION,
                    envelope.correlationId());
        }
        if (envelope.causationId() != null) {
            builder.setHeader(
                    EnvelopeHeaders.CAUSATION,
                    envelope.causationId());
        }

        return builder.build();
    }
}
~~~

**Những điểm cần nhìn kỹ:**

1. `getPayload()` của message mới là `OrderPlaced`, **không phải envelope**. Domain handler được giảm phụ thuộc vào wire format.
2. `businessEventId` giữ **logical event ID** từ nguồn. `MessageHeaders.ID` vẫn do framework tạo cho message hiện tại, có thể là một giá trị khác.
3. `trustedTenant` và `trustedSource` lấy từ ngữ cảnh được xác thực sau khi so với envelope, không mù quáng copy `tenantId/source` chưa tin.
4. `correlationId` và `causationId` được giữ nếu có. Không tự đồng nhất chúng với trace ID.
5. Chỉ copy **allowlisted metadata**, không copy `replyChannel`, `errorChannel`, credentials, user-supplied HTTP headers hoặc arbitrary Java types.

**Giới hạn:** Ở ví dụ `EventEnvelope<OrderPlaced>` đã typed nên payload được coi là object đã decode. Trong production, bước deserialize/schema validation có thể lỗi **trước** khi có kiểu này; cần đường error/quarantine ở inbound adapter, như phần sau mô tả.

### 7.6. Đừng nhầm “unwrap payload” với “xóa lịch sử event”

Sau khi unwrap, message trong JVM có thể chỉ chứa `OrderPlaced` và selected headers. Điều đó không có nghĩa được xóa original raw envelope ở source/outbox/audit nếu retention/replay cần nó. Payload phục vụ xử lý hiện tại, còn **provenance** và khả năng replay cần được bảo vệ theo chính sách riêng.

## 8. Java DSL: đưa envelope vào domain handler

### 8.1. Cấu trúc flow

~~~mermaid
flowchart LR
    INPUT["orders.envelope.input"] --> TR["Envelope Reader / Transformer"]
    TR --> MSG["Message<OrderPlaced> + selected headers"]
    MSG --> CH["orders.domain"]
    CH --> H["Order handler"]
    TR -->|Bad type/version/tenant| ERR["Error classification / quarantine"]
~~~

Demo này dùng `DirectChannel`, một transformer và handler ghi nhận kết quả. Không có Kafka/JMS hoặc persistent store để giữ bài tập tập trung vào boundary giữa envelope và business payload.

### 8.2. Consumer probe cho kiểm thử

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CopyOnWriteArrayList;

record ObservedOrder(
        OrderPlaced payload,
        Map<String, Object> headers) {}

final class OrderReceivedProbe {
    private final List<ObservedOrder> received =
            new CopyOnWriteArrayList<>();

    void record(
            OrderPlaced payload,
            Map<String, Object> headers) {
        received.add(new ObservedOrder(
                payload,
                Map.copyOf(headers)));
    }

    List<ObservedOrder> snapshot() {
        return List.copyOf(received);
    }
}
~~~

`OrderReceivedProbe` là fixture in-memory, không phải domain store. `Map.copyOf(headers)` phù hợp khi các header values không null theo contract. Nếu dữ liệu có mutable objects, một shallow copy không tự đảm bảo deep immutability; avoid storing arbitrary mutable header values.

### 8.3. Cấu hình Spring Integration 6.x minh họa

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
class EnvelopeBoundaryConfiguration {

    @Bean(name = "orders.envelope.input")
    MessageChannel envelopeInput() {
        return new DirectChannel();
    }

    @Bean(name = "orders.domain")
    MessageChannel domainOrders() {
        return new DirectChannel();
    }

    @Bean
    OrderEnvelopeReader envelopeReader() {
        return new OrderEnvelopeReader();
    }

    @Bean
    OrderReceivedProbe orderReceivedProbe() {
        return new OrderReceivedProbe();
    }

    @Bean
    IntegrationFlow unwrapEnvelopeFlow(OrderEnvelopeReader reader) {
        return IntegrationFlow.from("orders.envelope.input")
                .transform(
                        TrustedOrderIngress.class,
                        reader::unwrap)
                .channel("orders.domain")
                .get();
    }

    @Bean
    IntegrationFlow consumeDomainOrders(OrderReceivedProbe probe) {
        return IntegrationFlow.from("orders.domain")
                .handle(
                        OrderPlaced.class,
                        (payload, headers) -> {
                            probe.record(payload, headers);
                            return null; // Terminal demo handler.
                        })
                .get();
    }
}
~~~

**Lưu ý về type:** transformer của Spring Integration có thể tạo một `Message<?>` làm kết quả biến đổi. Trong flow này `reader.unwrap(...)` trả `Message<OrderPlaced>`, gồm payload và các internal headers được chọn; handler kế tiếp nhận `OrderPlaced` làm payload. Nếu dùng mapper/transformer khác hoặc Java DSL version khác, hãy kiểm chứng cách framework **merge/propagate headers** trong integration test, đừng chỉ kiểm tra object trả về từ hàm Java thuần.

**Lưu ý về scope:** bước STEP 4 chỉ soạn bài. Code mang tính minh họa Spring Integration 6.x; chưa có build hoặc Content QA theo phiên bản dependency của dự án.

### 8.4. Vì sao không dùng `envelope.toString()` làm wire payload?

`toString()` của Java record không phải JSON contract ổn định, không bảo đảm escaping, compatibility hay security. Với wire transport, dùng serializer có schema/configuration rõ, kiểm tra field allowlist, canonicalization khi cần ký, size limit và converter version.

### 8.5. Domain handler nên nhận cái gì?

Hai lựa chọn thường gặp:

~~~java
void handle(OrderPlaced payload) {
    // Logic nghiệp vụ chỉ cần order.
}
~~~

hoặc:

~~~java
void handle(OrderPlaced payload, String businessEventId) {
    // Business operation cần stable event identity để dedupe.
}
~~~

Không nhất thiết buộc domain handler nhận cả `EventEnvelope<OrderPlaced>`. Nếu handler cần idempotency, truyền **identity có chủ đích** ở một application service boundary thay vì để mọi domain object hiểu Kafka header hoặc Spring messaging API.

## 9. JUnit 5: envelope và payload phải tách biệt

### 9.1. Fixture có dữ liệu xác định

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

final class EnvelopeTestData {

    static OrderPlaced order() {
        return new OrderPlaced(
                "ORD-1001",
                "C-17",
                new BigDecimal("850000"),
                List.of(new OrderLine("SKU-A", 2)));
    }

    static EventEnvelope<OrderPlaced> envelope() {
        return new EventEnvelope<>(
                "EVT-1001",
                "order.placed",
                1,
                "order-service",
                "TENANT-A",
                Instant.parse("2026-11-21T02:30:00Z"),
                "CHECKOUT-88",
                "CMD-449",
                order());
    }

    static TrustedOrderIngress trustedIngress() {
        return new TrustedOrderIngress(
                envelope(), "TENANT-A", "order-service");
    }
}
~~~

### 9.2. Wrap không làm đổi payload gốc

~~~java
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotSame;

class OrderEnvelopeWriterTest {

    @Test
    void wrappingAddsContextButKeepsBusinessFields() {
        OrderPlaced original = EnvelopeTestData.order();
        EventEnvelope<OrderPlaced> wrapped =
                new OrderEnvelopeWriter().wrap(
                        new OrderDispatch(
                                "EVT-1001",
                                "order-service",
                                "TENANT-A",
                                EnvelopeTestData.envelope().occurredAt(),
                                "CHECKOUT-88",
                                "CMD-449",
                                original));

        assertEquals(original, wrapped.payload());
        assertEquals("order.placed", wrapped.eventType());
        assertEquals(1, wrapped.schemaVersion());
        assertEquals("TENANT-A", wrapped.tenantId());
        assertNotSame(original, wrapped);
    }
}
~~~

Điều cần test là **payload field và object contract giữ nguyên**, không phải `OrderPlaced` và `EventEnvelope` phải có cùng Java type. `assertNotSame` ở ví dụ chỉ nhấn mạnh đây là hai đối tượng thuộc hai lớp khác nhau.

### 9.3. Unwrap trả domain payload và giữ selected metadata

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

class OrderEnvelopeReaderTest {

    @Test
    void unwrappingBuildsMessageWithBusinessPayload() {
        Message<OrderPlaced> message =
                new OrderEnvelopeReader().unwrap(
                        EnvelopeTestData.trustedIngress());

        assertEquals(
                EnvelopeTestData.order(),
                message.getPayload());
        assertEquals(
                "EVT-1001",
                message.getHeaders().get(
                        EnvelopeHeaders.EVENT_ID));
        assertEquals(
                "TENANT-A",
                message.getHeaders().get(
                        EnvelopeHeaders.TENANT));
        assertEquals(
                "CHECKOUT-88",
                message.getHeaders().get(
                        EnvelopeHeaders.CORRELATION));
        assertEquals(
                "CMD-449",
                message.getHeaders().get(
                        EnvelopeHeaders.CAUSATION));
        assertNotNull(
                message.getHeaders().get(MessageHeaders.ID));
    }
}
~~~

Test này **không** khẳng định `MessageHeaders.ID` bằng `EVT-1001`. Trái lại, nó kiểm tra **logical event identity** ở header ứng dụng `businessEventId`, còn framework có ID riêng cho message hiện tại.

### 9.4. Tenant mismatch phải bị chặn trước business handling

~~~java
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertThrows;

class EnvelopeTenantSecurityTest {

    @Test
    void claimedTenantCannotOverrideAuthenticatedTenant() {
        TrustedOrderIngress forged = new TrustedOrderIngress(
                EnvelopeTestData.envelope(),
                "TENANT-B",
                "order-service");

        assertThrows(SecurityException.class, () ->
                new OrderEnvelopeReader().unwrap(forged));
    }
}
~~~

Ví dụ này kiểm tra **so khớp string trong converter**. Production phải bảo đảm `authenticatedTenant` thật sự do security layer cung cấp. Nếu test truyền `authenticatedTenant` từ một field tự khai trong cùng envelope, test chỉ chứng minh hai chuỗi trùng nhau, không chứng minh authorization.

### 9.5. Sai event type hoặc schema version phải reject

~~~java
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertThrows;

class EnvelopeContractTest {

    @Test
    void unknownVersionDoesNotSilentlyUseV1Decoder() {
        EventEnvelope<OrderPlaced> valid =
                EnvelopeTestData.envelope();
        EventEnvelope<OrderPlaced> version2 = new EventEnvelope<>(
                valid.messageId(),
                valid.eventType(),
                2,
                valid.source(),
                valid.tenantId(),
                valid.occurredAt(),
                valid.correlationId(),
                valid.causationId(),
                valid.payload());

        TrustedOrderIngress incoming = new TrustedOrderIngress(
                version2, "TENANT-A", "order-service");

        assertThrows(IllegalArgumentException.class, () ->
                new OrderEnvelopeReader().unwrap(incoming));
    }
}
~~~

Trong ứng dụng thật, việc version 2 có được hỗ trợ hay không phải do **schema registry/decoder policy** quyết định. Demo chỉ cho phép V1 để cho thấy **không được tự âm thầm bỏ qua version**.

### 9.6. Mã nguồn không nên sinh message ID mới để chống trùng

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;

import static org.junit.jupiter.api.Assertions.assertEquals;

class SameBusinessEventTwoMessageInstancesTest {

    @Test
    void rebuiltSpringMessageStillHasSameLogicalEventIdentity() {
        OrderEnvelopeReader reader = new OrderEnvelopeReader();
        TrustedOrderIngress incoming =
                EnvelopeTestData.trustedIngress();

        Message<OrderPlaced> first = reader.unwrap(incoming);
        Message<OrderPlaced> retry = reader.unwrap(incoming);

        assertEquals(
                first.getHeaders().get(
                        EnvelopeHeaders.EVENT_ID),
                retry.getHeaders().get(
                        EnvelopeHeaders.EVENT_ID));
        assertEquals(
                first.getPayload(),
                retry.getPayload());

        // Framework MessageHeaders.ID có thể được cấp mới.
        // Không dùng nó làm business idempotency key.
    }
}
~~~

## 10. Integration test: message đi qua Java DSL đúng hợp đồng

### 10.1. Test end-to-end trong một Spring context

~~~java
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringJUnitConfig(EnvelopeBoundaryConfiguration.class)
@DirtiesContext(classMode =
        DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class EnvelopeBoundaryIntegrationTest {

    @Autowired
    @Qualifier("orders.envelope.input")
    MessageChannel input;

    @Autowired
    OrderReceivedProbe probe;

    @Test
    void domainHandlerSeesOrderNotApplicationEnvelope() {
        boolean dispatched = input.send(
                MessageBuilder.withPayload(
                        EnvelopeTestData.trustedIngress())
                        .build());

        assertTrue(dispatched);

        List<ObservedOrder> seen = probe.snapshot();
        assertEquals(1, seen.size());
        assertEquals(
                EnvelopeTestData.order(),
                seen.get(0).payload());
        assertEquals(
                "EVT-1001",
                seen.get(0).headers().get(
                        EnvelopeHeaders.EVENT_ID));
        assertEquals(
                "TENANT-A",
                seen.get(0).headers().get(
                        EnvelopeHeaders.TENANT));
        assertEquals(
                "CHECKOUT-88",
                seen.get(0).headers().get(
                        EnvelopeHeaders.CORRELATION));
    }
}
~~~

**Điều test chứng minh:** qua Transformer và channel, handler nhận `OrderPlaced` làm payload và selected metadata ở headers.

**Điều test chưa chứng minh:** JSON codec, Kafka/JMS header mapper, persistence, broker redelivery, authorization của principal thật hoặc transaction. Đó là các test tại boundary riêng.

### 10.2. Không cho mạo danh nguồn đi vào domain flow

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringJUnitConfig(EnvelopeBoundaryConfiguration.class)
class EnvelopeSourceMismatchIntegrationTest {

    @Autowired
    @Qualifier("orders.envelope.input")
    MessageChannel input;

    @Autowired
    OrderReceivedProbe probe;

    @Test
    void forgedSourceDoesNotReachDomainHandler() {
        TrustedOrderIngress incoming = new TrustedOrderIngress(
                EnvelopeTestData.envelope(),
                "TENANT-A",
                "other-service");

        // Messaging layer có thể bọc SecurityException trong
        // MessageHandlingException; chỉ assert broad error ở đây.
        assertThrows(RuntimeException.class, () ->
                input.send(
                        MessageBuilder.withPayload(
                                incoming).build()));
        assertEquals(0, probe.snapshot().size());
    }
}
~~~

Nếu muốn test chính xác **reason code và error route**, cần inspect cause chain và áp dụng error policy của adapter cụ thể. Đừng viết test chỉ mong một exception mà bỏ qua câu hỏi **failed event sẽ được giữ ở đâu**.

### 10.3. Khi xử lý async thì không assert tức thì

Với `DirectChannel`, handler trong demo được gọi đồng bộ theo semantics của channel. Với `ExecutorChannel`, `QueueChannel`, poller hoặc broker:

- `send(...)` có thể chỉ xác nhận dispatch/enqueue, chưa có business completion.
- Dùng `CountDownLatch`/`BlockingQueue.poll(timeout)` hoặc kỹ thuật await có deadline.
- Có cleanup executor/latch và không dựa vào `Thread.sleep` như bằng chứng processed.
- Test cả late retry, process restart và delivery metadata mapping nếu yêu cầu production phụ thuộc chúng.

## 11. Header mapping khi đi qua các adapter

### 11.1. Header trong Spring không tự xuất hiện trên wire

Trong Spring Integration, header `businessEventId` có thể tồn tại ở một `Message<OrderPlaced>`. Khi một outbound adapter đưa message sang Kafka, JMS hoặc HTTP, **header mapper/serializer** quyết định header nào được chuyển, tên và kiểu dữ liệu ra sao. Inbound adapter nhận lại có thể tái tạo Spring message với **ID khác**.

~~~mermaid
flowchart LR
    A["Spring Message: payload + headers"] --> M1["Outbound Header Mapper"]
    M1 --> W["Broker record"]
    W --> M2["Inbound Header Mapper"]
    M2 --> B["New Spring Message: payload + mapped headers"]
~~~

Không được giả định tất cả headers tự tồn tại xuyên mọi transport, nhất là custom headers, Java objects hoặc non-serializable types.

### 11.2. Bảng mapping cần kiểm soát

| Internal header / metadata | Wire representation gợi ý | Hành động khi nhận |
|---|---|---|
| `businessEventId` | `event-id` string/bytes theo contract | Validate định dạng và identity; dùng để dedupe. |
| `eventType` | `event-type` | Kiểm tra allowlist/type registry. |
| `schemaVersion` | `schema-version` | Chọn decoder version. |
| `trustedSource` | Sender identity do adapter xác thực, đối chiếu source claim | Không tin một string tự khai là đã xác thực. |
| `trustedTenant` | Authenticated tenant scope, tùy transport | Bind từ principal và validate. |
| `businessCorrelationId` | `correlation-id` | Propagate theo workflow contract. |
| `causationId` | `causation-id` | Dựng causal graph/audit. |
| `occurredAt` | ISO-8601/epoch theo schema | Parse timezone/precision nhất quán. |
| Spring `MessageHeaders.ID` | Không cần copy bằng tên ID nghiệp vụ | Framework có thể tạo mới. |
| `replyChannel`/`errorChannel` object | Không serialize object JVM | Dùng wire reply destination/routing được xác thực. |

Nếu hệ thống chọn **body JSON envelope** thay vì wire headers, có thể giữ các field logic trong body và chỉ đưa những metadata thực sự cần transport vào headers. Quan trọng là **một contract rõ ràng, nhất quán và có test round-trip**.

### 11.3. Một anti-pattern dễ gặp

~~~text
Sender:
  message.headers["businessEventId"] = EVT-101
  message.payload = OrderPlaced

Outbound broker adapter:
  chuyển payload thành JSON
  không map businessEventId

Receiver:
  có OrderPlaced nhưng không có event ID
  tự sinh UUID tại mỗi lần nhận

Consequence:
  broker redeliver -> UUID mới -> dedupe thất bại
~~~

Chẩn đoán không nên bắt đầu bằng “thêm retry cho receiver”, mà phải kiểm tra **metadata đã rơi ở adapter boundary nào**.

### 11.4. Content type và serialization là hai thứ khác nhau

`content-type=application/json` chỉ cho biết kiểu biểu diễn, không đủ để xác định business schema. Cần biết:

- `eventType` nào?
- `schemaVersion` nào?
- JSON field representation của `BigDecimal`, thời gian và enum ra sao?
- Unknown fields bị bỏ, reject hay được ghi nhận?
- Size/depth limits và validation rules thế nào?
- Payload có mã hóa/ký không, ký phần nào?

Không dùng `Content-Type` như thông tin thay thế `eventType`/`schemaVersion`.

### 11.5. Test round-trip tại adapter thật

Một integration test nên thực hiện:

~~~text
Given:
  EventEnvelope<OrderPlaced> messageId=EVT-101,
  schemaVersion=1, tenant=TENANT-A, correlation=CHECKOUT-9

When:
  outbound adapter serialize + publish
  inbound adapter deserialize + rebuild Spring Message

Then:
  OrderPlaced business values unchanged
  businessEventId remains EVT-101
  type/version present and validated
  trusted tenant is derived and matched
  correlation preserved
  no internal Java MessageChannel serialized
~~~

**Không bắt buộc** Spring `MessageHeaders.ID` phải giữ nguyên qua adapter. Nếu contract yêu cầu event identity ổn định, kiểm tra `businessEventId` hoặc wire envelope `messageId`.

## 12. Correlation, causation, tracing và idempotency không đồng nghĩa nhau

### 12.1. Một business workflow có nhiều events

~~~text
Checkout CHECKOUT-88
  |
  +-- CMD-449: PlaceOrder
      |
      +-- EVT-1001: OrderPlaced
          |
          +-- EVT-1002: InventoryReserved
          |
          +-- EVT-1003: NotificationRequested
~~~

Ở mô hình này:

- **Correlation ID** `CHECKOUT-88` nhóm các message trong một workflow.
- **Causation ID** của `EVT-1001` có thể là `CMD-449`; của `EVT-1002` có thể là `EVT-1001`.
- **Logical event ID** phân biệt từng event.
- **Trace ID** liên kết các spans/logs trong một lần chạy hệ thống phân tán.
- **Business operation ID** định danh thao tác side effect cần chống trùng, ví dụ `RESERVE-STOCK:ORD-1001`.

### 12.2. Không dùng correlation làm idempotency key duy nhất

Giả sử mọi event có `correlationId=CHECKOUT-88`. Nếu Notification và Inventory dùng correlation ID làm dedupe key, nhánh thứ hai có thể bị đánh dấu duplicate của nhánh thứ nhất.

Một số scope phù hợp:

~~~text
Inventory consumer: (TENANT-A, INVENTORY_RESERVE, RESERVE-ORD-1001)
Notification consumer: (TENANT-A, NOTIFY_ORDER_PLACED, EVT-1001)
Audit consumer: (TENANT-A, AUDIT, EVT-1001)
~~~

Đây là các key minh họa. Không có một chuỗi key mặc định đúng cho mọi nghiệp vụ; chọn khóa từ **logical operation/event identity** trong ranh giới consumer.

### 12.3. Message ID có thể khác nhau qua các lần delivery

~~~text
Logical event envelope:
  messageId = EVT-1001

First Spring Message:
  headers.id = UUID-A

Broker redelivery / reconstructed Spring Message:
  headers.id = UUID-B

Business effect:
  should be applied only once for EVT-1001
~~~

Đừng nhầm **Spring message identity** với **logical event identity**. Với duplicate delivery, endpoint có thể xử lý hai Spring messages mà vẫn chỉ áp dụng một business operation.

### 12.4. Causation ID không thay event ID

Hai events phát sinh từ cùng một parent có thể có:

~~~text
InventoryReserved.eventId = EVT-1002
InventoryReserved.causationId = EVT-1001

NotificationRequested.eventId = EVT-1003
NotificationRequested.causationId = EVT-1001
~~~

Nếu dedupe bằng causation ID, event thứ hai có thể bị loại nhầm. Causation dùng để hỏi “**điều gì dẫn đến sự kiện này?**”, không phải “**đây có phải chính cùng sự kiện không?**”.

### 12.5. Trace context là telemetry, không phải quyền

`traceparent` hoặc `traceId` có thể được chuyển qua nhiều services, nhưng:

- Không dùng nó làm authentication token.
- Không gắn customer PII vào baggage/tracing tùy tiện.
- Sampling có thể làm thiếu spans; không coi trace là durable audit.
- Retry có thể tạo child spans hoặc traces mới; cần business event/operation IDs để nối lịch sử chính xác.

## 13. Envelope Wrapper với Router và Filter

### 13.1. Router nên dựa trên trường nào?

Một Router có thể chọn channel theo:

~~~text
Envelope.eventType = "order.placed"
  -> orderEventsChannel

Envelope.eventType = "payment.confirmed"
  -> paymentEventsChannel
~~~

Nhưng `eventType` phải được **validate theo schema/allowlist và trusted source**. Nếu caller có thể sửa nó, một message không hợp lệ có thể bị route vào handler khác.

Sau unwrap, có hai cách:

1. **Route trước unwrap** theo validated type/version của wire envelope, rồi chọn typed decoder.
2. **Unwrap/normalize trước** theo schema registry, sau đó route theo typed payload hoặc selected header.

Đừng route vào business handler chỉ vì tên eventType giống khi body chưa decode/validate được.

### 13.2. Routing dựa vào payload cũng có thể hợp lệ

Ví dụ tất cả message đều là `OrderPlaced`, nhưng đơn quốc tế và nội địa đi nhánh khác nhau. Đây là business routing có thể dựa trên **validated payload field** như `shippingCountry` nếu domain có field đó. Không cần nhân đôi mọi business attribute vào envelope.

### 13.3. Filter không nên im lặng loại envelope lỗi

Nếu thiếu `schemaVersion` hoặc `tenantId` không khớp, đây là lỗi contract/security, cần error/quarantine hoặc reject theo policy. Chỉ gọi `filter(false)` mà không có discard route có thể làm message biến mất.

~~~mermaid
flowchart TD
    E["Incoming Envelope"] --> V{"Type/version/security validation"}
    V -->|Valid| U["Unwrap"]
    U --> F{"Business Filter"}
    F -->|Accepted| B["Business"]
    F -->|Rejected| Q1["Business quarantine/rejection"]
    V -->|Unsupported/malformed| Q2["Schema/security error path"]
~~~

Không nhầm **invalid envelope metadata** với **business payload bị từ chối**. Ví dụ sai schema version là lỗi compatibility; amount âm là business validation. Cách khắc phục, ownership và retry khác nhau.

### 13.4. Envelope có thể bị mất khi Filter/Transformer chỉ trả payload

Ví dụ:

~~~java
// Về mặt Java, đây là thao tác unwrap đơn giản:
OrderPlaced order = envelope.payload();
~~~

Nếu đoạn này nằm giữa flow và không tạo headers mới hoặc giữ metadata ở application context, downstream có thể không còn `eventId`/`correlationId`. Điều đó có thể làm Idempotent Receiver và tracing không còn đủ thông tin. Cần integration test kiểm tra metadata tại **điểm tiêu thụ thực tế**, không chỉ ở đầu vào.

### 13.5. Header enrichment không được trở thành data laundering

Thêm một header `trustedTenant` từ `envelope.tenantId` rồi chuyển tiếp **không tự biến tenant thành trusted**. Header enrich chỉ chuyển vị trí dữ liệu; security phải được xác minh từ principal/adapter. Đặt tên header “trusted” chỉ sau khi đã đối chiếu/ủy quyền xong.

## 14. Splitter, Aggregator và Resequencer: không dùng nhầm envelope ID

### 14.1. Splitter sinh nhiều child messages từ một parent payload

Một `OrderPlaced` có hai dòng hàng. Splitter có thể sinh:

~~~text
Parent envelope:
  messageId=EVT-1001
  payload=OrderPlaced(items=[SKU-A, SKU-B])

Child messages:
  childEventId=EVT-1001/LINE-1, payload=OrderLine(SKU-A)
  childEventId=EVT-1001/LINE-2, payload=OrderLine(SKU-B)
~~~

Đây là **hai child operations/messages riêng biệt**, mặc dù chúng cùng phát sinh từ parent `EVT-1001`. Nếu cả hai được đặt nguyên `messageId=EVT-1001` rồi dùng global dedupe key, child thứ hai có thể bị coi là duplicate của child thứ nhất.

Một cách xác định danh tính minh họa:

~~~java
record OrderLineWork(
        String orderId,
        int lineNumber,
        OrderLine line) {}

record SplitChild(
        String childEventId,
        String parentEventId,
        String batchCorrelationId,
        int sequenceNumber,
        int sequenceSize,
        OrderLineWork payload) {}
~~~

Các IDs/sequence phải được định nghĩa có khả năng **tái tạo ổn định qua retry/replay**, chẳng hạn lưu child IDs tại producer/outbox hoặc xây từ identity đã canonicalize trong contract. Không dùng UUID mới mỗi lần Splitter chạy lại nếu downstream cần dedupe child operation.

### 14.2. Không sao chép “cùng ID” khi fan-out

Có hai ngữ nghĩa khác nhau:

| Tình huống | Message identity hợp lý | Idempotency scope |
|---|---|---|
| **Publish–Subscribe** giao **cùng event** `EVT-1001` tới Audit và Notification. | Cùng logical event ID, nhiều consumers. | `consumerId + EVT-1001`. |
| **Splitter** tạo **hai child operations** từ một parent. | Mỗi child có identity riêng, cùng parent/causation. | `batchId + childId` hoặc operation ID riêng. |

Nhầm hai mô hình dẫn tới dedupe sai. Không có quy tắc “mọi message mới phải có ID mới” hoặc “mọi nhánh phải giữ một ID” áp dụng cho tất cả; phải hiểu **đó là bản sao của cùng event hay một logical event/command mới**.

### 14.3. Correlation, sequence và business event identity

~~~text
batchCorrelation = BATCH-1001-RUN-7
childEventId     = EVT-1001-LINE-2
sequenceNumber   = 2
sequenceSize     = 3
~~~

`batchCorrelation` dùng gom child messages. `sequenceNumber` dùng phục hồi vị trí. `childEventId` dùng nhận diện duplicate child. Chúng không thay thế nhau.

Nếu một child bị Filter loại vì invalid, Aggregator có thể chờ mãi khi vẫn mong `sequenceSize=3`. Cần placeholder/failure outcome, chính sách partial release hoặc quarantine cả batch theo business contract, không âm thầm tăng/giảm size riêng trên một child.

### 14.4. Aggregator không nên nhét toàn envelope vào business result một cách mù quáng

Giả sử ba child replies có:

~~~text
Reply A: envelope(meta A, payload=ReservationResult)
Reply B: envelope(meta B, payload=ReservationResult)
Reply C: envelope(meta C, payload=ReservationResult)
~~~

Aggregator cần biết phải tạo **business aggregate result** thế nào, ví dụ `OrderReservationSummary`, rồi khi phát một **new logical result event** thì cấp event ID/version/correlation phù hợp. Không chỉ nối ba envelope JSON vào một mảng và gọi đó là business DTO nếu downstream không có contract này.

### 14.5. Resequencer dùng sequence nghiệp vụ, không dùng schema version

~~~text
Order ORD-1001:
  Event A: businessSequence=1, schemaVersion=2
  Event B: businessSequence=2, schemaVersion=2
  Event C: businessSequence=3, schemaVersion=3
~~~

Nếu cần phát A→B→C, Resequencer phải dùng business sequence và correlation/group identity đúng, không dùng `schemaVersion=2,2,3` để xác định thứ tự. Envelope chỉ là nơi có thể **chở metadata**, không định nghĩa semantics của chúng.

### 14.6. Sắp đúng thứ tự gửi chưa chắc commit đúng thứ tự

Sau Resequencer, một `ExecutorChannel` hoặc broker có nhiều consumer có thể xử lý song song. Kết quả commit có thể đảo dù thứ tự release đúng. Nếu business invariant yêu cầu commit theo phiên bản, cần serialization/partitioning per key, optimistic version guard, idempotency và transaction ở nơi tạo side effect.

## 15. Scatter–Gather, Publish–Subscribe và Recipient List

### 15.1. Fan-out không đồng nghĩa nhân đôi nghiệp vụ

~~~mermaid
flowchart TD
    E["Envelope EVT-1001: OrderPlaced"] --> PUB["Publish–Subscribe"]
    PUB --> A["Audit consumer"]
    PUB --> N["Notification consumer"]
    PUB --> I["Inventory consumer"]
    A --> KA["Inbox key: audit/EVT-1001"]
    N --> KN["Inbox key: notify/EVT-1001"]
    I --> KI["Inbox key: inventory/EVT-1001"]
~~~

Cùng một original envelope có thể đến ba recipients. Mỗi recipient cần xử lý sự kiện một lần **theo trách nhiệm của mình**. Không dùng một global `processed_messages[eventId]` để chặn tất cả recipients sau khi Audit xử lý đầu tiên.

### 15.2. Scatter yêu cầu kết quả của các tác vụ khác nhau

Một request `PriceQuoteRequested` có thể tạo:

~~~text
REQUEST-9
  -> Supplier A quote
  -> Supplier B quote
  -> Supplier C quote
~~~

Parent envelope `correlationId=REQUEST-9` giúp Gatherer nhóm replies, nhưng từng recipient cần ID/attempt tracking riêng để phân biệt **hai replies của Supplier A** với **một reply của Supplier B**.

Đây là nơi metadata như `recipientId`, `parentRequestId`, `attemptId` và deadline có thể xuất hiện ở envelope hoặc process store. Không tự coi `replyChannel` object trong JVM là một địa chỉ wire ổn định khi supplier trả lời từ một dịch vụ khác.

### 15.3. Lỗi một nhánh không nên làm sai final outcome

Nếu Fraud branch nhận invalid schema, trong khi Inventory và Pricing đều thành công, Gatherer không được báo `APPROVED` nếu Fraud là điều kiện bắt buộc. Thiết kế **branch outcome** với trạng thái `SUCCESS/INVALID/ERROR/TIMEOUT` và correlation riêng; không đưa một envelope bị lỗi vào payload aggregate rồi ngầm coi đó là success.

## 16. Gateway và request–reply

### 16.1. Envelope mô tả request, nhưng reply là một message mới

~~~text
Request:
  messageId=CMD-101
  eventType=inventory.reserve.requested
  correlationId=CHECKOUT-88

Reply:
  messageId=EVT-202
  eventType=inventory.reservation.completed
  correlationId=CHECKOUT-88
  causationId=CMD-101
~~~

Đây là hai logical messages; **không nhất thiết dùng cùng messageId**. Correlation/causation cho phép ghép reply về request nguồn mà vẫn giữ identity của từng message.

### 16.2. Spring `replyChannel` là internal return path

Trong một synchronous Gateway nội bộ, `replyChannel` có thể được Spring Integration sử dụng để trả kết quả. Đây là **header kỹ thuật chứa một channel object hoặc return address nội bộ**, không phải thứ mặc định chuyển qua Kafka/HTTP.

Nếu request được gửi sang service ngoài:

- Dùng reply destination được định nghĩa ở transport (reply topic/queue/callback URL được bảo vệ), nếu cần.
- Giữ stable `requestId`/`correlationId` để nối asynchronous reply.
- Không deserialize arbitrary replyChannel object từ untrusted JSON.
- Giới hạn timeout, validate quyền và filter late replies.

### 16.3. Caller timeout không có nghĩa operation chưa thực hiện

~~~text
T0 Gateway gửi request
T1 Worker nhận, xử lý thành công
T2 Reply bị mất ở transport
T3 Gateway timeout
T4 Caller retry cùng operation
~~~

Retry cần giữ **business operation ID**, tra ledger/receipt và không tạo side effect mới nếu operation cũ đã commit. Một envelope mới được tạo ra chỉ để **giao lại** cùng operation không được tự biến thành operation mới bằng ID sinh ngẫu nhiên.

### 16.4. Discard hoặc quarantine phải có response contract

Nếu incoming envelope không hợp lệ và Filter discard nó, Gateway đang đợi reply có thể hết timeout. Với API đồng bộ, nên có response rõ:

~~~json
{
  "requestId": "CMD-101",
  "status": "REJECTED",
  "reasonCode": "UNSUPPORTED_SCHEMA_VERSION",
  "quarantineReference": "Q-202"
}
~~~

**Không mặc định discardChannel trả reply**. Thiết kế error/response flow rõ; tránh trả raw input hoặc secret trong error message. Với asynchronous event ingestion, có thể chỉ ack khi quarantine được lưu bền theo contract.

## 17. Claim Check: envelope không thay thế một kho payload

### 17.1. Envelope Wrapper và Claim Check giải quyết bài toán khác nhau

| Pattern | Mục đích | Dữ liệu tiếp tục di chuyển |
|---|---|---|
| **Envelope Wrapper** | Thêm metadata/giao thức quanh payload. | Envelope chứa hoặc tham chiếu tới payload theo hợp đồng. |
| **Claim Check** | Cất payload/message gốc vào store, gửi token nhỏ. | Claim ID/reference, cần restore khi dùng. |

Một envelope có thể chứa `payloadRef` thay vì toàn bộ payload:

~~~json
{
  "messageId": "EVT-1001",
  "eventType": "order.placed",
  "schemaVersion": 1,
  "payloadRef": "CLAIM-555"
}
~~~

Nhưng **payload reference không tự làm payload gốc trở thành sẵn có**. Consumer phải được cấp quyền và có store/retention để restore. Nếu token hết hạn trước khi retry, envelope metadata vẫn có thể đọc được nhưng business payload đã mất.

### 17.2. Không dùng claim ID thay business event ID

Nếu cùng event được replay bằng claim mới:

~~~text
Original logical event: EVT-1001
Attempt 1 claim: CLAIM-555
Attempt 2 claim: CLAIM-777
~~~

Hai claims có thể chỉ là hai cách truy xuất cùng event; dedupe business side effect theo `EVT-1001`/operation ID thích hợp, không theo claim token vừa tạo.

### 17.3. Metadata cũng có vòng đời

Envelope có thể lưu lâu hơn claim hoặc ngược lại. Cần định nghĩa retention và cleanup của:

- Raw envelope/event log.
- Payload object/Claim Check store.
- Inbox idempotency record.
- Audit/receipt.
- Transport DLQ và replay references.

Nếu xóa payload do yêu cầu bảo mật, một envelope/tombstone còn lại không tự phục hồi được dữ liệu. Không “replay” bằng cách đoán nội dung thiếu.

## 18. Retry, error channel, DLQ và quarantine

### 18.1. Envelope lỗi không phải lúc nào cũng là business payload lỗi

| Tình huống | Lớp lỗi | Hướng xử lý |
|---|---|---|
| JSON/Avro/Protobuf không decode được | Wire serialization/converter | Adapter error handling, raw reference + DLQ/quarantine. |
| Thiếu `eventType` hoặc không hỗ trợ `schemaVersion` | Application envelope contract | Quarantine/unsupported-schema workflow. |
| Envelope `tenantId` mâu thuẫn authenticated principal | Security/provenance | Reject, security audit; không retry tự động. |
| Envelope hợp lệ nhưng `amountVnd` âm | Domain validation | Business-invalid quarantine/rejection. |
| Message trùng `eventId` đã COMPLETED | Delivery/idempotency | Trả previous outcome/ack duplicate theo contract. |
| External database timeout | Infrastructure | Retry/backoff/possibly DLQ; không gắn nhãn payload invalid. |
| Business order không đủ tồn kho | Business outcome | Rejected outcome/compensation; không nhất thiết “bad message”. |
| Replay có claim đã hết hạn | Payload retrieval/lifecycle | Reconcile/authorized reissue, không tự dựng payload. |

**Điểm mấu chốt:** Validate envelope đúng không chứng minh business processing thành công. Và một failure downstream không làm original envelope trở thành malformed.

### 18.2. Error path có thể xảy ra trước Spring Integration flow

~~~mermaid
flowchart TD
    B["Broker / HTTP raw bytes"] --> DE{"Decode envelope?"}
    DE -->|Không| RAW["Adapter error/DLQ"]
    DE -->|Có| SE{"Schema + provenance valid?"}
    SE -->|Không| Q["Envelope quarantine/rejection"]
    SE -->|Có| UN["Unwrap typed business payload"]
    UN --> VA{"Domain validation"}
    VA -->|Invalid| BUSQ["Business-invalid quarantine"]
    VA -->|Valid| H["Business handler"]
    H -->|Technical failure| ER["Retry/error channel/recovery"]
~~~

`errorChannel` trong Spring Integration được sử dụng theo execution context và cấu hình endpoint/adapter. Không phải mọi lỗi deserialization của Kafka/JMS hoặc HTTP binding đều tự tới **global errorChannel**; các lỗi đó có thể xuất hiện trước khi `Message<?>` được tạo.

### 18.3. Những trường nên giữ ở error record

~~~text
event=ENVELOPE_REJECTED
  transportRef=orders.events/partition-2/offset-721
  authenticatedSource=order-service
  trustedTenant=TENANT-A
  eventRef=EVT-1001 (nếu đọc được)
  eventType=order.placed (nếu đọc được)
  declaredSchemaVersion=7
  errorCode=UNSUPPORTED_SCHEMA_VERSION
  rawPayloadReference=protected-ref
  decoderVersion=v3
  receivedAt=...
~~~

Đây là một **schema audit/error do ứng dụng đề xuất**, không phải log framework tự cung cấp. Không log toàn bộ raw body có customer data hoặc token. Đối với payload không decode được, eventId trong body có thể **không đáng tin hoặc không có**, nên giữ transport reference ổn định/nguồn xác thực để điều tra.

### 18.4. Retry cần giữ logical identity

~~~text
Attempt #1:
  envelope.messageId = EVT-1001
  broker deliveryAttempt = 1

Attempt #2:
  envelope.messageId = EVT-1001
  broker deliveryAttempt = 2
~~~

Nếu là **redelivery của cùng event**, `messageId` nên giữ nguyên. Một message tạo ra do **business correction** thật sự có thể cần event ID mới và `causationId` trỏ về original; phải phân biệt correction với transport retry.

### 18.5. Đừng tự suy “at-least-once” bằng cách thêm retry count vào payload

`retryCount` là metadata của attempt/recovery, không phải business fact của `OrderPlaced`. Đưa nó vào domain DTO có thể làm consumer tính một event mới khi số attempt đổi và dễ làm thay đổi fingerprint. Dùng delivery metadata hoặc durable operation state; giữ `OrderPlaced` bất biến khi retry cùng logical event.

### 18.6. Durable outbox tránh dangling envelopes

Nếu producer lưu order state vào DB rồi publish envelope tới broker, crash ở giữa có thể tạo **order committed nhưng event chưa phát**, hoặc duplicate publish khi không nhận ack. Một giải pháp là:

~~~mermaid
flowchart LR
    CMD["Place Order"] --> TX["DB transaction"]
    TX --> ORDER[("Orders")]
    TX --> OUTBOX[("Outbox event + envelope metadata")]
    OUTBOX --> RELAY["Publisher/retry"]
    RELAY --> B[("Broker")]
    B --> INBOX["Idempotent consumer"]
~~~

Outbox record nên giữ **logical event ID, type, schema version, source, payload/version reference** ổn định; relay có thể gửi lại cùng envelope. Consumer vẫn cần idempotency vì **publish lặp là khả năng có thật**, không phải lỗi có thể loại bỏ tuyệt đối bằng outbox.

## 19. Bảo mật và tính toàn vẹn của envelope

### 19.1. Wrapper không phải security boundary tự nhiên

Nếu trong JSON có:

~~~json
{
  "tenantId": "TENANT-A",
  "source": "payment-service",
  "payload": {"orderId": "ORD-9"}
}
~~~

thì đó là dữ liệu do caller gửi. Không có bằng chứng `source` hoặc `tenantId` đúng cho đến khi adapter xác thực và gắn quyền. **Envelope có thể bị sửa, giả mạo hoặc phát lại** nếu không có transport/authentication/integrity control phù hợp.

### 19.2. Bảo vệ nguồn và phạm vi

1. Xác thực producer qua mTLS, broker ACL, service identity hoặc cơ chế được phê duyệt.
2. Bind `tenantId` với principal/route đã xác thực; không dùng tenant tự khai để truy cập dữ liệu tenant khác.
3. Kiểm tra `eventType`, `schemaVersion` và nguồn được phép phát type đó.
4. Giới hạn kích thước body, depth, số items, header count và header lengths.
5. Dùng encryption in transit/at rest theo dữ liệu, không tin base64 là encryption.
6. Không cho arbitrary Java class/type discriminator từ wire điều khiển deserializer.
7. Nếu dùng chữ ký/MAC, xác định **canonical bytes** được ký và version; không xác minh một representation rồi parse representation khác có thể bị đánh tráo.
8. Với replay, kiểm tra revoke/retention/permission **tại thời điểm replay**, không chỉ tại lần nhận đầu.

### 19.3. Header injection và override

Một inbound HTTP request có thể gửi header tùy ý tên `trustedTenant` hoặc `errorChannel`. Nếu ứng dụng blind-copy vào Spring headers rồi downstream tin nó:

- Caller có thể mạo danh tenant.
- Chèn route selector/header để đi sai channel.
- Làm lộ hoặc can thiệp reply/error route.
- Đẩy các loại dữ liệu không được phép vào store/log.

Giải pháp: **allowlist + normalize + validate + use trusted context for privileged headers**. Không sao chép `replyChannel`/`errorChannel` từ wire mà không có protocol và security contract chặt chẽ.

### 19.4. Bảo mật metadata cũng quan trọng như payload

Metadata có thể làm lộ business:

~~~text
source = hospital-service
eventType = cancer-treatment.updated
customerId = ...
correlationId = patient-...
~~~

Dù body được mã hóa, metadata không phù hợp vẫn có thể làm lộ thông tin. Với dữ liệu nhạy cảm, tránh ID chứa email, số định danh hoặc tên bệnh; dùng opaque IDs và giảm số trường cần lộ. **Không đưa eventId/tenantId/customerId làm metric labels có cardinality cao hoặc PII**.

### 19.5. Không log toàn envelope mặc định

Một log production tốt hơn:

~~~text
event=ENVELOPE_ACCEPTED
  eventType=order.placed
  schemaVersion=1
  eventRefHash=...
  source=order-service
  outcome=ACCEPTED
~~~

Nếu cần xem original raw payload, dùng secure audit/object store với quyền, retention và checksum, không in nguyên vào log text hay exception. Stack traces của deserializer cũng có thể chứa body fragments; phải cấu hình redaction.

## 20. Schema evolution: envelope version khác payload business version

### 20.1. Một event type có nhiều schema revisions

Ví dụ `order.placed` phiên bản 1:

~~~json
{
  "eventType": "order.placed",
  "schemaVersion": 1,
  "payload": {
    "orderId": "ORD-101",
    "amountVnd": 100000
  }
}
~~~

Phiên bản 2 có thể thêm `currency`:

~~~json
{
  "eventType": "order.placed",
  "schemaVersion": 2,
  "payload": {
    "orderId": "ORD-101",
    "amount": 100000,
    "currency": "VND"
  }
}
~~~

Đây là ví dụ **schema change**. Không được đọc V2 vào V1 rồi bỏ qua field `currency` mà không xác nhận semantics; một số loại thay đổi cần migration/upcaster hoặc từ chối nếu decoder chưa hỗ trợ.

### 20.2. Upcaster phải là phép chuyển có chủ đích

Một mô hình:

~~~text
Wire V1 -> decode OrderPlacedV1 -> upcast to canonical OrderPlaced
Wire V2 -> decode OrderPlacedV2 -> upcast to canonical OrderPlaced
                                  |
                                  v
                           Domain handler
~~~

Upcaster có thể thêm default theo **quy tắc được phê duyệt**, không tự bịa thông tin còn thiếu. Ví dụ nếu tất cả V1 chắc chắn dùng VND theo hợp đồng lịch sử, mới có cơ sở upcast `currency=VND`. Nếu không biết currency, phải reject/quarantine/require enrichment thay vì đoán.

### 20.3. Không “đổi lại” identity sau upcast

Upcasting **representation của cùng event** không nên tự sinh event ID mới và khiến Idempotent Receiver xem event cũ là chưa xử lý.

~~~text
Original:
  eventId=EVT-55, schemaVersion=1

Upcast view:
  eventId=EVT-55, canonicalPayloadVersion=2
~~~

Nếu producer phát ra **một business correction event mới** thì đó là tình huống khác: cần event ID mới, causation/reference tới original và operation semantics rõ.

### 20.4. Reader/writer compatibility

| Tình huống | Phải kiểm tra |
|---|---|
| Consumer mới đọc event cũ | Decoder V1 còn được hỗ trợ? Upcaster đúng business semantics? |
| Consumer cũ nhận event mới | Có forward/backward compatibility hay phải reject? |
| Enum thêm giá trị mới | Unknown enum được xử lý rõ, không tự map thành success. |
| Field đổi tên/type | Migration có validation; không silent drop. |
| Money scale/currency thay đổi | Không làm sai đơn vị hoặc precision. |
| Thời gian đổi precision/timezone | Chuyển đổi nhất quán và giữ occurredAt. |
| Event type mới | Router/registry có allowlist, không route bừa. |
| Persisted message sau deploy | Serialization cũ còn đọc được qua store/replay horizon. |

### 20.5. Event metadata cũng cần version contract

Không chỉ payload schema; cách đặt `eventType`, `tenantId`, `correlationId` hoặc `messageId` có thể đổi giữa các phiên bản chuẩn envelope. Nếu có thay đổi lớn, cân nhắc **envelopeFormatVersion** riêng với **event payload schemaVersion**, kèm migration plan. Đừng bắt một trường version duy nhất đồng thời đại diện cho ba ý nghĩa độc lập.

## 21. Observability: biết message mất lớp thông tin ở đâu

### 21.1. Các mốc nên ghi nhận

~~~text
event=TRANSPORT_RECORD_RECEIVED
  transportRef=orders.events/2/721
  sourceAuthenticated=true

event=ENVELOPE_DECODED
  businessEventRef=EVT-1001
  eventType=order.placed
  schemaVersion=1

event=ENVELOPE_VALIDATED
  businessEventRef=EVT-1001
  tenantMatch=true
  typeSupported=true

event=BUSINESS_PAYLOAD_UNWRAPPED
  businessEventRef=EVT-1001
  payloadType=OrderPlaced

event=BUSINESS_HANDLER_COMPLETED
  businessEventRef=EVT-1001
  operationRef=RESERVE-ORD-1001

event=BROKER_ACKNOWLEDGED
  transportRef=orders.events/2/721
~~~

Đây là **schema log gợi ý**, không phải một tập log tự động được Spring Integration cung cấp trong mọi cấu hình. Các sự kiện cũng không nhất thiết có quan hệ một-một: một broker record có thể chứa batch nhiều events, hoặc cùng event được giao nhiều lần.

### 21.2. Đừng gộp các mốc “thành công”

| Mốc | Điều xác nhận | Điều chưa xác nhận |
|---|---|---|
| Transport accepted | Broker/adapter nhận record theo contract. | Consumer đã xử lý. |
| Envelope decoded | Parse wire metadata/payload biểu diễn thành công. | Source/tenant đã authorized. |
| Envelope validated | Type/version/provenance qua policy. | Business payload hợp lệ. |
| Payload unwrapped | Có typed domain payload cho downstream. | Payment/inventory side effect đã commit. |
| Handler returned | Một callback xử lý xong theo execution model. | External transaction luôn bền nếu không có chứng cứ. |
| Inbox COMPLETED | Có authoritative operation receipt theo ledger. | Mọi external system atomic nếu nằm ngoài ranh giới ledger. |
| Broker acked | Transport ghi nhận acknowledgment. | Không còn replay/DLQ/manual republish. |

Một dashboard ghi “processed” ngay sau khi parse envelope có thể báo sai nghiêm trọng. Cần định nghĩa rõ **processed = decoded? validated? handled? committed?**.

### 21.3. Metrics gợi ý

| Metric | Mục đích |
|---|---|
| `envelope_received_total{source}` | Số lần envelope được nhận. |
| `envelope_decoded_total{type,version}` | Decode thành công. |
| `envelope_decode_failed_total{reason}` | Decode lỗi trước business flow. |
| `envelope_contract_rejected_total{reason}` | Type/version/format không hợp lệ. |
| `envelope_source_mismatch_total` | Claimed source khác authenticated source. |
| `envelope_tenant_mismatch_total` | Sai tenant boundary. |
| `envelope_unwrapped_total{type}` | Payload typed chuyển thành công. |
| `envelope_header_mapping_failed_total{adapter}` | Metadata mất/không map được qua adapter. |
| `envelope_schema_upcast_total{from,to}` | Có migration version. |
| `envelope_duplicate_delivery_total` | Số logical events được giao lại theo identity. |
| `envelope_quarantined_total{reason}` | Số envelope bị cách ly theo policy. |
| `envelope_size_bytes` | Phân phối kích thước envelope. |
| `envelope_processing_latency_seconds` | Độ trễ từ ingress tới bước xác định. |

Đây là **tên gợi ý**, không khẳng định framework tự tạo chúng. Tránh gắn `messageId`, `orderId`, `customerId`, `traceId` hoặc email làm metric labels có cardinality cao. Dùng log/tracing/audit có quyền cho từng event cụ thể.

### 21.4. Message History không thay thế durable audit

Spring Integration Message History (nếu được bật) có thể chỉ ra message đã đi qua các component nào. Nhưng nó không tự:

- Lưu nguyên wire envelope khi adapter decode thất bại.
- Chứng minh raw payload signature/authorization hợp lệ.
- Giữ durable mapping giữa business eventId và operation receipt.
- Ghi transaction/ack của broker/DB.
- Lưu metadata bị drop qua adapter nếu header mapping sai.

Cần kết hợp **broker coordinates, envelope event ID, secure payload reference, message history, trace context và business receipt**.

## 22. Chẩn đoán khi consumer có payload nhưng mất metadata

Giả sử Inventory Handler nhận đúng `OrderPlaced` nhưng không thấy `businessEventId` và `correlationId`.

1. **Kiểm tra producer:** eventId/correlation có được cấp và lưu ổn định trong outbox hay không?
2. **Kiểm tra serialized envelope:** metadata nằm trong body hay headers? Có đúng field names/types không?
3. **Kiểm tra outbound adapter:** header mapper có allowlist các trường cần thiết không? Có drop unknown headers?
4. **Kiểm tra broker:** record value và wire headers thực sự chứa gì? Có record ID khác do republish?
5. **Kiểm tra inbound adapter:** trường nào được deserialize, trường nào được gán vào Spring headers?
6. **Kiểm tra trust:** producer/source/tenant đã authenticated chưa? Một header bị loại có phải do policy bảo mật?
7. **Kiểm tra Transformer:** có trả payload đơn thuần mà không giữ selected metadata hay không?
8. **Kiểm tra Router/Filter:** có route mặc định làm message sang sai handler? Metadata có bị đổi giữa các nhánh?
9. **Kiểm tra Splitter:** child IDs và correlation/sequence đã được tạo đúng chưa?
10. **Kiểm tra Gateway:** reply có sử dụng internal channel object sau transport hop không?
11. **Kiểm tra retry:** cùng logical event có bị cấp ID mới ở consumer attempt không?
12. **Kiểm tra audit/tracing:** có đối chiếu eventRef, transportRef, trace và business receipt để tìm đúng điểm mất?
13. **Thêm regression test:** thực hiện wire round-trip và assert selected headers sau inbound adapter thay vì chỉ trước outbound.

### 22.1. Một vài triệu chứng quen thuộc

| Triệu chứng | Khả năng đầu tiên nên kiểm tra |
|---|---|
| Message ID đổi qua Kafka | Có thể bình thường; phân biệt Spring ID với logical event ID. |
| Duplicate effect sau redelivery | `businessEventId`/operation key mất hoặc không có durable dedupe. |
| Consumer đọc sai DTO | `eventType`/`schemaVersion` không được map hoặc decoder dùng default sai. |
| Tenant mismatch tăng sau deploy | Header mapping, principal scope, claimed metadata thay đổi. |
| Correlation ở Aggregator biến mất | Transformer/Splitter/header mapper mất correlation headers. |
| Kafka value đúng nhưng header không có | Outbound mapper chưa serialize custom header. |
| Gateway timeout dù handler chạy | Reply routing/return address không wire-portable. |
| Resequencer phát sai thứ tự | Đang dùng schemaVersion hoặc event arrival order thay business sequence. |
| Replay một event có schema cũ bị lỗi | Decoder/upcaster cũ bị xóa sớm so với retention. |
| Quarantine không có eventId | Raw parse thất bại; cần transport reference và secure raw copy. |

### 22.2. Trình tự debug có hệ thống

~~~text
Producer business event
  -> Application envelope
  -> Serialized bytes + wire headers
  -> Inbound adapter / header mapper
  -> Spring Message<?> received
  -> Envelope unwrap/validation
  -> Domain handler + operation receipt
~~~

Tìm **điểm đầu tiên metadata bị mất hoặc đổi nghĩa**. Đừng sửa bằng cách copy tất cả HTTP/broker headers vào domain handler: cách đó có thể đưa untrusted values vào business flow và tạo rủi ro bảo mật.

## 23. Ma trận kiểm thử: envelope khác business payload

| ID | Đầu vào/kịch bản | Expected outcome | Điều không được xảy ra |
|---|---|---|---|
| EW-01 | Wrap `OrderPlaced` hợp lệ | Envelope chứa đúng payload và metadata. | Payload đổi giá trị. |
| EW-02 | Unwrap typed envelope hợp lệ | `Message<OrderPlaced>` với selected headers. | Domain handler nhận raw JSON envelope. |
| EW-03 | Envelope có ID sự kiện ổn định | `businessEventId` đúng nguồn. | Gán nhầm Spring MessageHeaders.ID. |
| EW-04 | Hai Spring messages của cùng logical event | Cùng business event ID, payload tương đương. | Xem là hai operations mới vì UUID khác. |
| EW-05 | Hai events khác nhau cùng `orderId` | Hai event IDs riêng. | Dedupe bằng orderId đơn thuần. |
| EW-06 | Envelope thiếu `messageId` | Reject/validation failure. | Sinh UUID mới ở mỗi retry mà không audit. |
| EW-07 | Envelope thiếu `eventType` | Reject contract invalid. | Route vào handler mặc định. |
| EW-08 | Unsupported `schemaVersion` | Quarantine/unsupported-schema handling. | Parse tùy tiện thành V1. |
| EW-09 | Claimed tenant khác authenticated tenant | Security rejection. | Truy cập dữ liệu tenant khác. |
| EW-10 | Claimed source khác authenticated producer | Security rejection/audit. | Chấp nhận source giả. |
| EW-11 | Envelope chứa raw HTTP credential | Redact/drop theo policy. | Forward secret tới subscribers. |
| EW-12 | Body JSON envelope qua Kafka | Header/body mapping giữ required metadata. | Consumer chỉ copy payload làm mất type/version. |
| EW-13 | Metadata ở Kafka headers, value chỉ payload | Inbound adapter tái tạo identity/schema. | Mất eventId mà không phát hiện. |
| EW-14 | Spring custom header không map qua outbound | Test bắt thiếu header. | Silent metadata loss. |
| EW-15 | Wire header không serialize được | Error/validation theo adapter policy. | Serialize arbitrary Java objects. |
| EW-16 | Wire gửi `replyChannel` object | Reject/ignore; dùng transport reply destination. | Deserialization Java channel trái quyền. |
| EW-17 | Malformed JSON trước typed decoder | Adapter error route/raw quarantine. | Khẳng định typed Filter đã xử lý. |
| EW-18 | Payload amount âm dù envelope hợp lệ | Business validation rejection. | Coi envelope valid là business success. |
| EW-19 | External DB timeout sau unwrap | Technical retry/recovery. | Gắn nhãn malformed envelope. |
| EW-20 | Broker ack bị mất sau business commit | Same event identity, idempotent result. | Business side effect lặp. |
| EW-21 | Outbox relay publish event hai lần | Cùng logical eventId. | Tạo business event mới ở relay. |
| EW-22 | Republish cùng event ở offset khác | Dedupe bằng event ID/operation ID. | Dedupe chỉ theo offset. |
| EW-23 | Một event fan-out cho Audit và Notification | Mỗi consumer xử lý một lần. | Global dedupe chặn nhánh thứ hai. |
| EW-24 | Splitter tạo ba child messages | Unique child IDs, stable parent/sequence metadata. | Ba child có một key operation gây drop. |
| EW-25 | Filter loại một child | Aggregator có failure outcome/timeout policy. | Chờ mãi không quan sát. |
| EW-26 | Aggregator nhận duplicate reply | Dedupe theo recipient/child identity. | Duplicate thay missing child. |
| EW-27 | Scatter–Gather có late reply | Correlation + attempt/version guard. | Ghép reply vào request mới. |
| EW-28 | Resequencer có `schemaVersion=2` cho cả nhóm | Ordering theo business sequence. | Sắp thứ tự theo schemaVersion. |
| EW-29 | Gateway request timeout | Stable operationId, reconcile outcome. | Tạo charge mới vì request ID mới. |
| EW-30 | Claim Check reissue claim | Cùng business event identity nếu cùng logical event. | Dedupe theo claimId mới. |
| EW-31 | `occurredAt` từ producer, `receivedAt` khác | Hai thời điểm giữ đúng nghĩa. | Ghi đè occurredAt bằng thời điểm nhận. |
| EW-32 | Retry attempt 2 | deliveryAttempt có thể tăng, logical eventId không đổi. | Đổi payload/domain event mỗi lần giao. |
| EW-33 | Có `traceparent` từ nguồn ngoài | Trace context được validate/propagate theo policy. | Coi trace ID là quyền hoặc operation ID. |
| EW-34 | Correlation và causation khác nhau | Hai field giữ đúng semantics. | Dedupe bằng causation của siblings. |
| EW-35 | V1 event đọc bằng V2 consumer | Upcast theo business contract hoặc reject rõ. | Đoán dữ liệu thiếu không có bằng chứng. |
| EW-36 | V2 có currency mới | Validate/convert theo schema. | Silent drop currency. |
| EW-37 | Object store còn raw envelope sau deploy | Schema cũ vẫn decode/replay được theo retention. | Làm mất khả năng replay. |
| EW-38 | Wire body quá lớn | Size/depth bounds, error route. | OOM/tràn log. |
| EW-39 | Payload chứa PII, metadata logging | Redacted structured logs. | Log nguyên customer details/token. |
| EW-40 | Tenant header do caller giả mạo | Trusted context validation. | Đặt tên “trusted” là coi đã xác thực. |
| EW-41 | `MessageHeaders.ID` đổi qua Transformer | BusinessEventId vẫn đủ cho idempotency. | Dùng ID runtime làm nguồn sự thật. |
| EW-42 | Unknown `eventType` | Quarantine/controlled rejection. | Deserialize arbitrary class do caller chỉ định. |
| EW-43 | Schema registry/downstream unavailable | Technical error/retry policy. | Coi payload sai chắc chắn. |
| EW-44 | No reply cho discarded request | Gateway response/error contract rõ. | Caller đợi đến timeout không lý do. |
| EW-45 | Transport message accepted, business effect fail | Metrics tách received/handled/committed. | Báo COMPLETED tại ingress. |
| EW-46 | Producer source đổi sau deploy | Authenticated source allowlist cập nhật có audit. | Chấp nhận vì claimed source giống cũ. |
| EW-47 | Đổi header mapper giữa hai services | Round-trip test bắt field mất/đổi kiểu. | Tin test serialize thuần trong JVM. |
| EW-48 | Message bản gốc đã được correction | New event/attempt lineage và operation policy. | Đè eventId cũ để giả dữ liệu không đổi. |

### 23.1. Kiểm thử ở đúng tầng

| Cấp | Nội dung cần test | Điều chưa chứng minh |
|---|---|---|
| **Java unit** | Wrap/unwrap, DTO invariants, type/version/tenant validation. | Broker header mapping hoặc dữ liệu bền. |
| **Spring Integration test** | Transformer, channel, handler, selected headers. | JSON codec/Kafka behavior nếu không có adapter thật. |
| **Serializer/contract test** | JSON fields, schema registry, version compatibility. | Delivery/ack của broker. |
| **Adapter integration test** | Inbound/outbound header mapping, content type, raw parse errors. | Domain side effect commit nếu chỉ mock. |
| **Persistence test** | Outbox/inbox, idempotency, transaction, replay compatibility. | Remote payment nếu nằm ngoài transaction. |
| **System/chaos test** | Restart, duplicate, late reply, concurrency, DLQ replay. | Mọi điều kiện production có thể xảy ra. |
| **Security test** | Auth source/tenant, header injection, payload size, PII redaction. | Những trust boundaries chưa được kiểm tra. |

### 23.2. Một golden round-trip fixture

Cho một sự kiện được ký hiệu `EVT-1001`, lưu một fixture có:

~~~text
messageId: EVT-1001
eventType: order.placed
schemaVersion: 1
source: order-service
tenantId: TENANT-A
correlationId: CHECKOUT-88
causationId: CMD-449
payload.orderId: ORD-1001
payload.amountVnd: 850000
payload.items[0].sku: SKU-A
~~~

Test nên đưa fixture qua **serialize → transport adapter mapping → deserialize → unwrap → handler observation**. Assert toàn bộ trường có ý nghĩa vẫn đúng; kiểm tra cả các field **cố ý không forward** như credentials/replyChannel object.

## 24. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| “Envelope chính là domain payload.” | Domain DTO chứa trace/broker-specific fields. | Tách domain event và application envelope. |
| “Spring MessageHeaders giống hoàn toàn wire envelope.” | Lỗi khi chuyển transport hoặc deserialize. | Xây mapping contract và round-trip test. |
| “Mọi ID đều là `messageId`.” | Nhầm operation, trace, correlation và delivery. | Định nghĩa identity theo từng mục đích. |
| “`MessageHeaders.ID` phải giữ nguyên qua Kafka.” | Test sai hoặc dedupe không ổn định. | Giữ logical event ID riêng. |
| “`schemaVersion` chính là thứ tự event.” | Resequencer sai thứ tự. | Dùng business sequence/order version. |
| “`correlationId` đủ để dedupe mọi child.” | Splitter/gatherer bỏ các child hợp lệ. | Child operation ID và consumer scope. |
| “Wrap là mã hóa/bảo mật.” | Tin dữ liệu giả mạo, lộ secret. | AuthN/AuthZ, integrity và encryption riêng. |
| “Có `tenantId` trong JSON là trusted.” | Cross-tenant access. | Bind từ authenticated principal. |
| “Header có tên `trustedSource` nghĩa là đã xác thực.” | Data laundering qua header enrichment. | Validate trước khi tạo trusted metadata. |
| “Chỉ forward payload là đủ.” | Mất event ID, schema, correlation khi đổi adapter. | Mapping selected metadata có chủ đích. |
| “Forward mọi headers cho chắc.” | Rò rỉ secrets, route injection và objects JVM. | Allowlist và sanitize. |
| “Deserializer tự biết mọi event class.” | Injection/type confusion/bug schema. | Type/version allowlist. |
| “Unknown schema cứ thử deserialize V1.” | Mất field, sai đơn vị tiền. | Reject/upcast có contract. |
| “`occurredAt` = `receivedAt`.” | Sai latency, replay chronology. | Giữ hai thời điểm riêng. |
| “Retry nên cấp event ID mới mỗi lần.” | Dedupe mất tác dụng. | Stable logical event ID cho redelivery. |
| “Đã unwrap thì đã xử lý thành công.” | Báo success trước business commit. | Theo dõi state/receipt của side effect. |
| “Bọc một payload ở ngoài là có Claim Check.” | Không có store/token/retrieval semantics. | Phân biệt Envelope Wrapper với Claim Check. |
| “Gateway replyChannel object gửi qua wire được.” | Reply mất hoặc deserialization không an toàn. | Dùng wire reply destination/protocol. |
| “Message History là audit của business receipt.” | Không chứng minh commit/idempotency. | Durable inbox/outbox/receipt kết hợp tracing. |
| “Log toàn envelope dễ debug nhất.” | PII/secret leak và storage bùng nổ. | Redact, protected payload reference. |
| “Fan-out cùng event ID chỉ cho một consumer chạy.” | Mất Audit/Notification/Inventory. | Consumer-scoped idempotency. |
| “Replay correction giữ nguyên mọi metadata.” | Không biết dữ liệu đã đổi hoặc ai sửa. | New revision/causation/attempt lineage. |
| “Một unit test writer/reader chứng minh adapter luôn đúng.” | Headers rơi qua network. | Adapter/contract/system tests. |

## 25. Bài tập thực hành

1. **Phân lớp thông tin:** từ một JSON chứa `orderId`, `eventId`, `traceId`, `amountVnd`, `schemaVersion` và `deliveryAttempt`, giải thích trường nào thuộc payload, envelope hoặc transport và vì sao.
2. **Domain DTO:** viết `OrderPlaced` không import Spring/Kafka/HTTP, kiểm tra các invariants cơ bản và tính bất biến của `items`.
3. **Generic envelope:** triển khai `EventEnvelope<T>` với message ID, type, version, source, tenant, occurredAt, correlation, causation và payload.
4. **Wrap:** tạo `OrderEnvelopeWriter` nhận `OrderDispatch` từ nguồn tin cậy và trả envelope, không sinh ID mới ở mỗi attempt.
5. **Unwrap:** chuyển `EventEnvelope<OrderPlaced>` thành Spring `Message<OrderPlaced>` và giữ selected headers.
6. **Logical vs framework ID:** unwrap cùng event hai lần; assert `businessEventId` giống nhau mà không dựa vào `MessageHeaders.ID`.
7. **Schema validation:** đổi version 1 thành version 99; converter phải reject có lý do thay vì silently decode V1.
8. **Tenant binding:** envelope khai TENANT-A nhưng trusted context là TENANT-B; xác minh không gọi domain handler.
9. **Source binding:** claimed source và authenticated source không khớp; kiểm tra failure và audit.
10. **Header allowlist:** thử đưa arbitrary header `replyChannel`, `secret`, `debugPayload` vào wire; chỉ những field được phép mới có mặt sau mapping.
11. **Java DSL flow:** dùng `EnvelopeBoundaryConfiguration` để gửi một `TrustedOrderIngress` và quan sát `OrderReceivedProbe`.
12. **Raw codec:** thêm JSON parser/serializer phù hợp dependency, test decode envelope metadata trước khi map typed payload.
13. **Round-trip qua adapter:** gửi envelope qua Kafka/JMS/HTTP test setup thực, kiểm tra custom headers và payload không mất sau inbound.
14. **Malformed wire:** đưa JSON sai cấu trúc, xác minh adapter error route hoạt động ngay cả khi typed Transformer không được gọi.
15. **Domain invalid:** gửi envelope hợp lệ nhưng amount âm trong raw ingress DTO; bảo đảm đó là business validation error, không phải unsupported schema.
16. **EventId stability:** mô phỏng outbox publish cùng logical event hai lần với transport coordinates khác; Idempotent Receiver vẫn nhận ra duplicate.
17. **Consumer scopes:** gửi cùng `OrderPlaced` tới Audit và Notification; cả hai được xử lý một lần theo consumer-scoped key.
18. **Splitter:** chia OrderPlaced thành các OrderLineWork với child IDs khác nhau, parent/correlation/sequence giữ đúng và ổn định qua replay.
19. **Aggregator:** thử cùng một child reply hai lần và thiếu child còn lại; group không được release như thể đủ.
20. **Resequencer:** tạo ba events có business sequence 1,2,3 nhưng schemaVersion khác nhau; sắp theo business sequence, không theo schema version.
21. **Gateway:** tạo request/reply envelopes có event IDs riêng, cùng correlation và reply causation trỏ request ID; test caller timeout và late reply.
22. **Claim Check:** đổi payload trong envelope thành protected claim reference; test expired claim và business idempotency khi reissue.
23. **Upcasting:** tạo OrderPlacedV1/V2, chỉ default currency khi lịch sử business contract chứng minh, giữ event ID gốc qua upcast.
24. **Security:** thử source/tenant spoofing qua HTTP headers và envelope body; bắt mismatch trước business routing, không leak receipt.
25. **Observability:** tạo logs `ENVELOPE_DECODED`, `ENVELOPE_VALIDATED`, `BUSINESS_HANDLER_COMPLETED` với redacted IDs và metrics tách từng mốc.
26. **Replay runbook:** mô tả đường đi từ DLQ/secure raw store tới schema upcaster, validation, idempotency ledger và business handler có audit.
27. **Compatibility matrix:** xác minh consumer mới đọc được envelope V1 và V2 hoặc trả unsupported rõ khi không tương thích.
28. **Partial transport failure:** mô phỏng publish thành công nhưng producer không nhận ack; replay phải giữ event ID, consumer không nhân đôi side effect.
29. **Header loss regression:** tắt mapping `businessEventId` ở outbound adapter trong test và xác minh test round-trip thất bại có ý nghĩa.
30. **Data retention:** khi payload cần xóa sau hạn, vẫn giữ metadata tối thiểu có quyền và tombstone nếu policy cần chống late duplicate.

### 25.1. Tiêu chí một bài thực hành đạt yêu cầu

- Domain payload **không phụ thuộc** tên headers/broker/service adapter.
- Envelope có **logical event identity** và schema contract rõ.
- Unwrap **validate source/tenant/type/version** trước khi chuyển vào business flow.
- Spring `MessageHeaders.ID` và envelope `messageId` **không bị đánh đồng**.
- Selected headers sống qua adapter round-trip; untrusted headers bị loại.
- Retry giữ event/operation identity và có idempotency ở đúng side-effect boundary.
- Splitter, Aggregator, Router, Gateway, Claim Check, Resequencer dùng correlation/sequence đúng ngữ nghĩa.
- Unsupported schema, malformed raw data, domain invalid và technical failure có error path khác nhau.
- Metadata/PII được bảo vệ, logs/metrics không tiết lộ dữ liệu không cần thiết.
- Test có kiểm tra **nơi metadata có thể mất thật** — đặc biệt outbound/inbound adapter.

## 26. Câu hỏi tự kiểm tra

**Câu 1: Envelope Wrapper là gì?**

Là pattern bọc business payload bằng metadata của hợp đồng giao tiếp, giúp truyền identity, type/version, provenance, correlation và ngữ cảnh xử lý mà không biến domain DTO thành object của transport.

**Câu 2: Có phải payload là tất cả dữ liệu bên trong JSON không?**

Không. JSON body có thể chứa cả application envelope và payload. Payload là phần dữ liệu mang ý nghĩa nghiệp vụ; metadata envelope là phần mô tả message/hợp đồng truyền.

**Câu 3: Spring `Message<?>` có giống một JSON envelope không?**

Không nhất thiết. Spring Message là object trong JVM gồm payload và headers; JSON envelope là wire/application representation. Cần mapping rõ khi chuyển đổi.

**Câu 4: Nếu message ID của Spring đổi sau Transformer thì event có đổi không?**

Không mặc định. Một logical event có thể được thể hiện bằng nhiều Spring messages; business event ID có thể giữ nguyên giữa chúng.

**Câu 5: `orderId` và `eventId` khác gì?**

`orderId` là business entity ID; `eventId` là identity của một logical event. Một order có thể có nhiều events.

**Câu 6: `schemaVersion` có dùng để Resequencer sắp thứ tự không?**

Không. Nó mô tả format/contract phiên bản, không phải thứ tự thay đổi business. Cần business sequence/version riêng.

**Câu 7: Vì sao không dùng `correlationId` làm idempotency key cho mọi message?**

Vì nhiều child events/operations có thể cùng correlation group. Dedupe thường phải gắn logical event hoặc business operation và consumer scope.

**Câu 8: `causationId` và `correlationId` khác nhau ra sao?**

Causation nối message với nguyên nhân trực tiếp; correlation nhóm messages của cùng workflow/request. Hai events siblings có thể cùng causation nhưng IDs riêng.

**Câu 9: Envelope có `tenantId=TENANT-A` thì tenant đã được xác thực chưa?**

Chưa. Phải kiểm tra principal/adapter identity và bind/đối chiếu với claimed metadata.

**Câu 10: Sao không forward tất cả Spring headers qua Kafka để tránh mất thông tin?**

Vì nhiều headers là internal JVM objects, secrets hoặc dữ liệu không tin cậy; một số không serialize được. Chỉ map selected fields theo hợp đồng đã validate.

**Câu 11: Nếu `schemaVersion` không được hỗ trợ thì sao?**

Reject hoặc đưa vào unsupported-schema quarantine/error path theo policy; không tùy tiện deserialize thành schema mặc định rồi bỏ field.

**Câu 12: Một message malformed JSON có đi qua typed Filter không?**

Không nếu adapter/decoder đã lỗi trước khi tạo typed message. Cần adapter-specific error handling.

**Câu 13: Fan-out cùng event tới Audit và Notification có phải duplicate không?**

Không theo consumer scope. Đây là cùng event cần hai side effects độc lập; mỗi consumer chỉ nên xử lý nó một lần.

**Câu 14: Splitter tạo ba child messages thì có nên giữ cùng một child event ID?**

Không nếu chúng là ba logical child operations khác nhau. Giữ parent/causation/correlation phù hợp, nhưng cần child identities riêng và ổn định.

**Câu 15: Một Gateway reply có phải dùng chung eventId với request?**

Không mặc định. Reply là một logical message riêng, có thể có ID mới, giữ correlation và causation/request ID để nối với request nguồn.

**Câu 16: Envelope chứa `payloadRef` có đồng nghĩa Claim Check hoạt động không?**

Chưa. Cần store, quyền, cơ chế lấy lại payload, TTL và recovery policy. Reference không tự mang dữ liệu original.

**Câu 17: Nếu broker republish cùng event ở offset khác, có nên coi là event mới không?**

Không chỉ vì offset đổi. Xác định logical identity từ eventId/operationId và provenance; offset là transport coordinate.

**Câu 18: Upcasting V1 thành V2 có cần đổi eventId không?**

Không nếu chỉ thay cách biểu diễn của cùng logical event. Business correction mới là một sự kiện khác và cần lineage rõ.

**Câu 19: Có thể kết luận business đã hoàn tất khi envelope được decode thành công không?**

Không. Decode/validate/unwrap là các mốc đầu vào, không phải bằng chứng external side effect đã commit.

**Câu 20: Nên debug mất metadata theo thứ tự nào?**

Kiểm tra producer/outbox → serialized envelope/wire headers → outbound mapper → broker record → inbound mapper → Spring message → Transformer/Router → domain handler, tìm điểm đầu tiên metadata mất hoặc bị đổi nghĩa.

## 27. Kết luận

**Envelope và payload nghiệp vụ là hai lớp khác nhau.** Payload trả lời **“điều gì xảy ra hoặc cần được thực hiện trong nghiệp vụ?”**; envelope trả lời **“thông điệp này là gì, thuộc hợp đồng nào, đến từ đâu, có identity/correlation/schema như thế nào?”**. Spring `Message<?>` là một mô hình runtime gồm payload và headers, còn transport record có metadata riêng của Kafka/JMS/HTTP. Chúng liên quan với nhau nhưng **không tự tương đương**.

Trong Spring Integration, một bước **wrap/unwrap** tốt không chỉ bỏ hoặc thêm một lớp JSON. Nó cần kiểm tra source/tenant theo trusted context, chọn type/version có allowlist, chuyển thành typed domain payload, giữ selected metadata ở đúng chỗ và không phát tán internal headers hoặc dữ liệu nhạy cảm. Đặc biệt, **logical event ID khác Spring MessageHeaders.ID; business sequence khác schemaVersion; correlation khác causation; claim reference khác operation ID**.

Khi kết hợp Envelope Wrapper với Router, Filter, Transformer, Splitter, Aggregator, Scatter–Gather, Resequencer, Claim Check, Gateway, retry và error channel trong `SPRING_INTEGRATION_PATTERN`, hãy kiểm thử **mỗi ranh giới**: Java object, Spring Message, serializer, adapter/transport, business handler, persistence và replay. Một thiết kế đạt yêu cầu phải trả lời rõ ba câu: **“Payload nào mang ý nghĩa nghiệp vụ?”, “Metadata nào cần đi cùng nó qua mọi hop?”, và “Ai được phép tin, chuyển đổi hoặc sử dụng metadata đó?”**
