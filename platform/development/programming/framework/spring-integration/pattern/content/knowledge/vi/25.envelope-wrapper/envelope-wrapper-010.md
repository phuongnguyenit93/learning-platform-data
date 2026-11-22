# Envelope khi message qua nhiều hệ thống

Một message đi qua HTTP API, Kafka, RabbitMQ, JMS, gateway hoặc các service khác nhau không chỉ mang **dữ liệu nghiệp vụ**. Bên nhận thường còn cần biết *ai tạo sự kiện, sự kiện thuộc loại gì, phiên bản schema nào, lúc nào xảy ra, liên quan tới nghiệp vụ nào, dữ liệu được mã hóa ra sao và phải truy vết thế nào*. Khi các thông tin đó nằm trong những header đặc thù của từng transport, một bước chuyển từ HTTP sang broker có thể làm chúng biến mất hoặc bị hiểu sai.

**Envelope Wrapper** là Enterprise Integration Pattern đóng gói **payload nghiệp vụ** vào một **vỏ thông điệp (envelope)** có cấu trúc rõ, mang những metadata được phép trao đổi qua ranh giới hệ thống. Hệ thống nhận xác minh envelope, giải mã payload và chuyển nó thành message nội bộ để xử lý. Khi message đi qua nhiều hệ thống, cần phân biệt **danh tính sự kiện gốc** với **thông tin của từng lần chuyển tiếp**, đồng thời tránh sao chép headers chứa token hoặc đối tượng nội bộ sang hệ thống khác.

Bài **Envelope khi message qua nhiều hệ thống** thuộc chương **Envelope wrapper**, module **SPRING_INTEGRATION_PATTERN**. Module học triển khai Enterprise Integration Patterns với Spring Integration để tạo các luồng thông điệp ít phụ thuộc và dễ mở rộng; thực hành Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation, đồng thời kiểm thử và theo dõi những nhánh xử lý.

**Nguyên tắc xuyên suốt:** *Dữ liệu nghiệp vụ giữ ý nghĩa nghiệp vụ; envelope mang hợp đồng tích hợp qua boundary; transport headers chỉ có hiệu lực trong phạm vi transport của chúng*. Không mặc định rằng JSON envelope, Spring `MessageHeaders`, HTTP headers và Kafka record headers là cùng một lớp.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích Envelope Wrapper và phân biệt nó với Transformer, Header Enricher, Normalizer và wire framing.
2. Thiết kế envelope mang event ID, type, source, version, occurrence time, correlation/causation và payload.
3. Phân biệt business payload, integration envelope, Spring Message headers và transport metadata.
4. Quyết định metadata nào ổn định **end-to-end**, metadata nào chỉ dành cho **một hop**.
5. Giữ nguyên logical event identity khi chuyển HTTP → broker → consumer nhưng cho phép delivery/message instance ID thay đổi.
6. Phân biệt `eventId`, `messageId`, `correlationId`, `causationId`, `traceId`, `tenantId` và `schemaVersion`.
7. Gắn và xác thực payload schema/version/content type mà không suy đoán tùy ý.
8. Viết Java 17 record cho domain event/envelope và wrapper/unwrapper bằng Jackson.
9. Tạo Spring Integration Java DSL flow wrap → outbound channel và inbound → unwrap → business channel.
10. Kiểm thử round trip, metadata propagation, content mismatch, unsupported version và header leakage.
11. Thiết kế adapter qua HTTP, Kafka/JMS/AMQP với quy tắc chuyển metadata có chủ đích.
12. Xử lý retry, DLQ, idempotency, replay, expiry, signatures và data privacy.
13. Bảo toàn business correlation cho Aggregator/Resequencer qua các hop.
14. Quan sát từng hop mà không tạo metric labels cardinality cao hoặc log secrets.
15. Lập một hợp đồng envelope có thể nâng cấp khi nhiều hệ thống sử dụng các phiên bản khác nhau.

## 2. Bài toán: một sự kiện đi qua ba hệ thống

Giả sử Order Service phát sự kiện `OrderCreated`, Integration Gateway chuyển nó vào broker, Fulfillment Service nhận và lưu một task xử lý đơn.

~~~mermaid
flowchart LR
    O["Order Service"] -->|"HTTP / JSON"| G["Integration Gateway"]
    G -->|"Kafka / AMQP"| B[("Message Broker")]
    B -->|"Broker delivery"| F["Fulfillment Service"]
    F --> H["Order Handler"]
~~~

Nếu Order Service chỉ gửi:

~~~json
{
  "orderId": "ORDER-101",
  "totalMinorUnits": 250000,
  "currency": "VND"
}
~~~

Fulfillment Service còn thiếu nhiều thông tin:

- Đây là sự kiện **OrderCreated** hay một snapshot cập nhật?
- Ai là nguồn phát để xác minh hợp đồng?
- Cùng sự kiện đã được broker gửi lại chưa?
- Event thuộc tenant nào?
- Schema của payload là version nào?
- Mốc thời gian là lúc nghiệp vụ xảy ra hay lúc gateway nhận?
- Muốn correlate với PaymentCaptured/InventoryReserved thì dùng ID nào?
- Khi lỗi, có thể đưa vào quarantine rồi replay bằng cách nào?

Một envelope có hợp đồng rõ giúp các bên dùng chung ngữ nghĩa:

~~~json
{
  "envelopeVersion": "1",
  "eventId": "evt-order-1001",
  "source": "order-service",
  "type": "order.created",
  "schemaVersion": "1",
  "occurredAt": "2026-11-21T02:00:00Z",
  "tenantId": "tenant-a",
  "correlationId": "tenant-a/ORDER-101",
  "causationId": "cmd-place-order-1001",
  "contentType": "application/json",
  "data": {
    "eventId": "evt-order-1001",
    "tenantId": "tenant-a",
    "orderId": "ORDER-101",
    "totalMinorUnits": 250000,
    "currency": "VND",
    "occurredAt": "2026-11-21T02:00:00Z"
  }
}
~~~

Đây là **định dạng envelope tự thiết kế cho bài học**, không phải tuyên bố mọi trường trên thuộc một tiêu chuẩn bắt buộc. Trong production, các bên cần thống nhất tên trường, JSON Schema/AsyncAPI/OpenAPI hoặc một chuẩn event envelope đã chọn, chẳng hạn CloudEvents nếu phù hợp.

### 2.1. Cái gì nằm trong `data`?

`data` chứa **ý nghĩa nghiệp vụ của OrderCreated**, ví dụ order ID, amount và currency. Một consumer có thể xử lý business event mà không biết nó được gửi qua HTTP hay Kafka.

### 2.2. Cái gì nằm trong envelope?

Vỏ chứa metadata cần trao đổi **giữa hệ thống**: event ID, source, type, version, thời điểm gốc và những liên kết correlation/causation có hợp đồng. Chúng không nên phụ thuộc vào tên header riêng của một broker.

### 2.3. Cái gì nên ở transport headers?

HTTP `Authorization`, Kafka partition/offset, JMS delivery mode, RabbitMQ delivery tag hoặc Spring `replyChannel` phục vụ transport/runtime hiện tại. Không mặc định chúng là phần của JSON envelope cần gửi đến mọi hệ thống sau.

## 3. Bốn lớp không được nhập nhằng

~~~mermaid
flowchart TB
    T["Transport frame / record
    HTTP / Kafka / JMS / AMQP"]
    E["Integration Envelope
    id / type / source / versions / metadata"]
    D["Business Data
    orderId / amount / currency"]
    S["Spring Message
    payload + MessageHeaders nội bộ"]
    T --> E
    E --> D
    T -.-> S
    E -.-> S
~~~

Sơ đồ là cách nhìn **khái niệm**: khi Java chạy, `Message<ExternalEnvelope>` có payload là envelope; khi gửi wire, một serializer chuyển nó thành bytes và một adapter đặt bytes trong transport record.

| Lớp | Ví dụ | Nhiệm vụ | Vòng đời |
|---|---|---|---|
| Business payload | `OrderCreated` | Ý nghĩa domain event | Độc lập transport |
| Integration envelope | `eventId,type,source,data` | Contract liên hệ giữa các hệ thống | Có thể đi qua nhiều hop |
| Spring `MessageHeaders` | `id,timestamp,replyChannel,errorChannel` | Điều phối flow trong Spring Integration | Theo message/flow instance |
| Transport metadata | HTTP method/header; Kafka offset; JMS delivery count | Delivery, routing, authentication/ACK | Thường chỉ trong một transport/hop |

### 3.1. Một Spring Message đã có headers, vậy envelope có cần không?

Trong một JVM, Spring `Message<T>` đủ truyền payload và metadata nội bộ. Nhưng khi chuyển ra JSON HTTP hoặc binary broker record, các header tùy ý có thể:

- Không được serializer chuyển đi.
- Có tên hoặc kiểu không tương thích ở hệ thống nhận.
- Chứa `replyChannel` là đối tượng Java không serialize phù hợp.
- Bị adapter khác bỏ hoặc ghi đè.
- Trở thành thông tin bảo mật không nên gửi qua trust boundary.

Envelope là **hợp đồng dữ liệu qua boundary**, không thay thế toàn bộ Spring headers. Cần chọn cái nào thuộc **business/integration contract**, cái nào **hop-local**.

### 3.2. Envelope khác message encoding/frame

HTTP/TCP/Kafka đều có cách đóng frame hoặc record riêng. Envelope Wrapper là **pattern về nội dung và metadata trao đổi**, không đồng nghĩa định dạng TCP packet hay TLS record. Một envelope có thể được serialize bằng JSON, Avro hoặc Protobuf; lựa chọn encoding là một quyết định contract khác.

## 4. Envelope Wrapper khác những EIP liên quan

| Pattern / endpoint | Câu hỏi chính | Khác biệt với Envelope Wrapper |
|---|---|---|
| **Envelope Wrapper** | Cần bọc payload thế nào để hệ thống ngoài hiểu? | Tạo vỏ chứa metadata + payload |
| **Transformer** | Đổi payload/message từ representation A sang B? | Có thể được dùng để thực hiện wrap/unwrap |
| **Header Enricher** | Bổ sung metadata vào Spring headers? | Không nhất thiết tạo wire envelope |
| **Normalizer** | Nhiều source formats về một canonical payload? | Có thể chạy trước/sau unwrap tùy boundary |
| **Content-based Router** | Message cần tới route nào? | Có thể đọc `type` của envelope để route |
| **Filter** | Message có được đi tiếp không? | Có thể reject invalid/unauthorized envelope |
| **Claim Check** | Làm payload nhẹ bằng token thay vì dữ liệu lớn? | Không giống thêm một vỏ metadata |
| **Wire Tap** | Sao chép message để audit/tracing? | Không có nhiệm vụ wrap |
| **Idempotent Receiver** | Tránh side effect lặp sau redelivery? | Có thể dùng `eventId` do envelope mang |
| **Aggregator** | Message thuộc group nào và khi nào đủ? | Có thể dùng business correlation từ envelope |

Trong Spring Integration, Envelope Wrapper thường triển khai bằng `Transformer`, `@Transformer`, Java DSL `.transform(...)` hoặc adapter serialization. Pattern không đòi một class tên `EnvelopeWrapper` có sẵn trong Spring Integration.

## 5. Một message qua nhiều hop: "giữ" gì, "đổi" gì?

~~~text
Hop 1: Order Service -> Integration Gateway
Hop 2: Integration Gateway -> Kafka topic
Hop 3: Kafka Consumer -> Fulfillment Service
~~~

| Thông tin | Hop 1 | Hop 2 | Hop 3 | Quy tắc |
|---|---|---|---|---|
| `eventId` | evt-1001 | evt-1001 | evt-1001 | **Giữ** nếu vẫn forward cùng logical event |
| `source` | order-service | order-service | order-service | **Giữ** origin; gateway không mạo danh publisher gốc |
| `type` | order.created | order.created | order.created | Giữ nếu không tạo event mới |
| `occurredAt` | 02:00 | 02:00 | 02:00 | Giữ thời điểm nghiệp vụ gốc |
| `tenantId` | tenant-a | tenant-a | tenant-a | Giữ nhưng phải xác minh trust scope |
| `correlationId` | order workflow key | same | same | Giữ theo domain contract |
| `causationId` | cmd-1001 | cmd-1001 | cmd-1001 | Giữ nếu chỉ forward |
| `schemaVersion` | 1 | 1 | 1 | Giữ khi `data` không đổi schema |
| Spring `MessageHeaders.ID` | UUID-A | UUID-B | UUID-C | Có thể **đổi** theo từng Message instance |
| HTTP request ID | req-http-1 | Không tương đương | — | Hop-local |
| Kafka offset | — | offset-178 | offset-178 khi nhận record | Transport-local; không là event ID |
| Delivery attempt | 1 | 1 | 2 khi retry | Thay đổi qua redelivery |
| `receivedAt` | gateway receive time | broker receive time | consumer receive time | Hop-local; không ghi đè `occurredAt` |

### 5.1. Forward nguyên event khác tạo event mới

**Forward/re-publish cùng logical event:** giữ `eventId`, `source`, `type`, `occurredAt`, đồng thời có thể ghi hop receipt riêng ngoài logical envelope.

**Derived event:** nếu Fulfillment nhận `OrderCreated` rồi thực sự tạo `ShipmentRequested`, đây là **event khác**:

~~~text
Input event:
  id=evt-order-1001
  type=order.created

Derived event:
  id=evt-shipment-2001   (ID mới)
  type=shipment.requested
  causationId=evt-order-1001
  correlationId=tenant-a/ORDER-101
~~~

Không dùng cùng ID cho hai sự kiện khác loại chỉ vì một sự kiện sinh ra sự kiện kia. `causationId` giữ quan hệ nguyên nhân, `correlationId` giữ workflow, trong khi `eventId` mới nhận diện sự kiện phát sinh.

### 5.2. Có thể re-envelope khi đổi schema không?

Nếu intermediary thực sự **thay đổi dữ liệu có ý nghĩa hoặc contract sự kiện**, phải có policy rõ: sự kiện gốc được biến đổi representation nhưng **business event identity** có giữ hay không phụ thuộc hợp đồng giữa các bên. Một adapter thuần đổi định dạng mà không đổi semantics thường giữ logical event ID và ghi metadata transformation. Nếu tạo **business event mới**, phải cấp ID mới và liên kết causation.

## 6. Event ID, correlation, causation và trace

Các ID thường bị trộn lẫn:

| Trường | Nhận diện | Có nên thay qua hop? |
|---|---|---|
| `eventId` | Một logical event | Không khi forward cùng event |
| `correlationId` | Nhóm sự kiện cùng workflow | Không nếu workflow không đổi |
| `causationId` | Sự kiện/lệnh trực tiếp dẫn tới event hiện tại | Không khi forward; cập nhật khi phát event mới |
| `traceId` | Một distributed trace | Theo tracing context/propagation |
| `spanId` | Một span cụ thể | Thường thay khi tạo span mới |
| `MessageHeaders.ID` | Spring Message instance | Có thể thay |
| Kafka offset | Vị trí record trong partition | Thay theo nơi publish |
| HTTP request ID | Một request/attempt | Có thể thay |
| `schemaVersion` | Format/schema của `data` | Thay khi thay payload schema theo contract |
| `envelopeVersion` | Schema của chính envelope | Thay khi nâng cấp envelope format |

**Event ID không phải Spring Message ID.** Hai lần broker redelivery có thể dựng hai `Message<?>` khác nhau, nhưng vẫn cùng logical `eventId`.

### 6.1. Correlation phải nhận diện đúng nhóm nghiệp vụ

Nếu bạn cần Aggregator gom OrderCreated, PaymentCaptured, InventoryReserved cho một đơn, group key có thể là `(tenantId,orderId)`. Không dùng email, trạng thái, timestamp hoặc event ID riêng của từng part làm group key.

`correlationId` trong envelope phải có hợp đồng: nó là ID workflow, request hay business group? Chỉ tên field không chứng minh đúng ngữ nghĩa.

### 6.2. Trace context không thay business correlation

W3C `traceparent` hoặc OpenTelemetry tracing có thể được truyền qua HTTP và broker headers theo instrumentation. Một trace có thể bị chia ở async processing; một business workflow có thể kéo dài qua nhiều traces. Không dùng traceId làm orderId hoặc idempotency key.

### 6.3. Causation không phải thời gian gửi

`causationId` trả lời *event/lệnh nào dẫn tới event này?* Nó không chứa timestamp và không được suy ra từ thứ tự arrival của broker. Khi forward không tạo business event mới, không tùy tiện đổi causationId thành ID của gateway request.

## 7. Schema version của envelope và payload khác nhau

Hai contract có thể nâng cấp độc lập:

~~~json
{
  "envelopeVersion": "1",
  "type": "order.created",
  "schemaVersion": "2",
  "data": {
    "orderId": "ORDER-101",
    "amountMinorUnits": 250000
  }
}
~~~

- `envelopeVersion="1"`: quy tắc fields và semantics của lớp vỏ.
- `schemaVersion="2"`: quy tắc fields/semantics của `data` cho event type tương ứng.
- HTTP API version: có thể khác cả hai.
- Application release `4.8.1`: không bắt buộc tương ứng với schema version.

### 7.1. Version phải đi cùng event type

Schema v1 của `order.created` không đồng nghĩa schema v1 của `payment.captured`. Bộ định danh schema hợp lý thường gồm `(source/eventType, schemaVersion)` hoặc schema registry ID đã được xác thực.

### 7.2. Không lấy version để sắp thứ tự nghiệp vụ

Một OrderCreated v2 và PaymentCaptured v1 vẫn có thể thuộc cùng order. Không dùng `schemaVersion` làm `sequenceNumber`, business revision hay correlation key.

### 7.3. Re-wrap khi thay `data`

Nếu Gateway chuyển payload v1 sang canonical v2, nó phải cập nhật `schemaVersion` cho **payload mới** và lưu provenance ở trường/header riêng nếu cần. Giữ `schemaVersion=1` bên cạnh `data` đã thành v2 làm consumer chọn decoder sai.

Không tự nâng `envelopeVersion` nếu chỉ thay schema của `data`. Đó là hai trục evolution khác nhau.

## 8. Payload, metadata và header mapping contract

Một envelope qua nhiều hệ thống nên có bảng contract thay vì sao chép mọi header:

| Thông tin | Nơi ưu tiên | Có gửi qua boundary? | Ghi chú |
|---|---|---|---|
| Order ID, amount, currency | `data` | Có | Business contract |
| Event ID, event type, source | Envelope | Có | Logical identity |
| Original occurredAt | Envelope | Có | Không ghi đè bởi receive time |
| Schema/envelope versions | Envelope | Có | Decoder/compatibility |
| Business correlation/causation | Envelope | Khi cần | Không dùng traceId thay |
| Trace context | Transport headers / tracing metadata | Theo policy | W3C/OpenTelemetry context, có trust controls |
| Tenant ID | Envelope hoặc authenticated routing context | Có điều kiện | Luôn xác thực |
| Authentication bearer token | Hop-local secure header | **Không copy tùy tiện** | Nhạy cảm, có thể phải cấp credential mới |
| Spring `replyChannel` | Spring Message headers | Không qua wire tùy ý | Không phải HTTP callback URL |
| Spring `errorChannel` | Spring runtime | Không qua wire tùy ý | Chỉ hữu dụng trong context phù hợp |
| Kafka topic/partition/offset | Transport | Hop-local | Không là business ID |
| Retry attempt/delivery tag | Transport | Hop-local | Có thể reset ở hop mới |
| Compression/encoding | Wire metadata | Có nếu contract yêu cầu | Phải kiểm tra giới hạn/kích thước |

### 8.1. Không copy toàn bộ Spring headers vào JSON envelope

Một anti-pattern là serialize `message.getHeaders()` vào một map trong envelope. Nó có thể chứa:

- `replyChannel`/`errorChannel` là object runtime không portable.
- `Authorization`/session metadata.
- Broker-specific headers chứa offset, partition, delivery tag.
- Old `contentType` không đúng với payload đã biến đổi.
- Các internal tracking IDs hoặc thông tin nhạy cảm.

**Dùng allowlist** cho các metadata cần đi qua boundary; còn headers cần chuyển qua transport phải được adapter mapping và trust policy rõ ràng.

## 9. Khi nào không cần envelope tự thiết kế?

Không phải mọi hệ thống cần thêm một lớp JSON custom.

- Một API đã có **hợp đồng response/request** với trace và identity rõ có thể không cần wrap thêm.
- Một broker có event envelope theo **CloudEvents** hoặc schema registry có thể dùng chuẩn đó thay vì tự phát minh.
- Trong một Spring Integration flow nội bộ, `Message<T>` + headers có thể đủ.
- Khi payload là file lớn, thêm một vỏ JSON chứa toàn bộ bytes có thể làm tăng memory; cân nhắc file metadata, attachment, object storage hoặc Claim Check theo contract.
- Khi message đã có envelope chuẩn, **đừng bọc lồng nhiều lớp** chỉ vì đi qua thêm một gateway.

Câu hỏi thiết kế là: *bên nhận cần hiểu metadata nào, qua trust boundary nào, với hợp đồng tương thích ra sao?* Nếu có một chuẩn đã đáp ứng, ưu tiên tái sử dụng hơn là tạo custom envelope mới.

### 9.1. CloudEvents là một lựa chọn, không phải đồng nghĩa với demo

CloudEvents 1.0 định nghĩa các thuộc tính cốt lõi như `specversion`, `id`, `source`, `type` và dữ liệu sự kiện; cũng có các thuộc tính tùy chọn như `subject`, `time`, `datacontenttype`, `dataschema`. Nó định nghĩa các cách binding/serialization tương ứng. JSON demo `envelopeVersion/eventId/schemaVersion` trong bài **không phải** JSON CloudEvents chuẩn; nếu dùng CloudEvents, phải tuân đúng tên trường, kiểu, source/id uniqueness và structured/binary binding của đặc tả, không chỉ đổi vài tên property.

### 9.2. Envelope không tự giải quyết reliability

Wrap thành JSON hợp lệ **không** mang lại:

- Exactly-once business side effects.
- Broker ACK đúng thời điểm.
- Authenticity nếu chưa có security.
- Schema compatibility giữa producers/consumers.
- Correlation đúng nếu key được chọn sai.
- Transaction across multiple services.

Nó chỉ tạo một **khung hợp đồng** để các cơ chế khác hoạt động nhất quán.

## 10. Hợp đồng kiểm thử trước khi viết Java

Trước khi triển khai, chốt mẫu hợp đồng:

| Mục | Ví dụ |
|---|---|
| Event type | `order.created` |
| Envelope version | `"1"` |
| Payload schema version | `"1"` |
| Source | `order-service` |
| Event ID | `evt-order-1001`, ổn định qua retry |
| Tenant | `tenant-a`, được xác thực ở ingress |
| Correlation | `tenant-a/ORDER-101` theo business contract |
| Causation | `cmd-place-order-1001` (có thể null nếu không có) |
| Occurrence time | ISO-8601 `Instant` UTC |
| Content type | `application/json` trong ví dụ |
| Payload | `OrderCreated` |
| Unknown envelope version | Reject/quarantine, không đoán |
| Unknown payload version | Explicit unsupported schema handling |
| Unknown event type | Route/quarantine, không cast thành OrderCreated |
| Duplicate event ID | Idempotent Receiver ở phía xử lý |
| Security | Verify authenticated source/tenant và giới hạn kích thước |
| Trace | Propagate theo instrumentation/trust policy |
| Replay | Giữ event identity, kiểm tra retention của dedup ledger |

Bảng này là **contract ví dụ của ứng dụng**. Những hệ thống thực tế phải định nghĩa owner, thời hạn hỗ trợ version, schema examples và chính sách xử lý dữ liệu nhạy cảm.
## 11. Java 17: mô hình payload và envelope

Ta xây dựng một ví dụ độc lập cho `order.created` dùng Java 17 và Jackson. Mỗi kiểu `public` dưới đây cần lưu trong **một source file Java riêng cùng tên** khi đưa vào project.

### 11.1. Payload nghiệp vụ không biết về broker

~~~java
public record OrderCreated(
        String eventId,
        String tenantId,
        String orderId,
        long totalMinorUnits,
        String currency,
        String occurredAt
) {}
~~~

`OrderCreated` chỉ mô tả một business event. Không có Kafka partition/offset, HTTP authorization hay địa chỉ Spring channel trong record này.

Trong bài, số tiền luôn ở **minor units**; một `long` là lựa chọn minh họa cho integer amount khi có hợp đồng currency rõ. Không tự nhân amount với 100 cho mọi loại tiền hoặc dùng `double` để chuyển đổi tiền tệ.

### 11.2. Envelope có cấu trúc rõ

~~~java
import com.fasterxml.jackson.databind.JsonNode;

public record ExternalEventEnvelope(
        String envelopeVersion,
        String eventId,
        String source,
        String type,
        String schemaVersion,
        String occurredAt,
        String tenantId,
        String correlationId,
        String causationId,
        String contentType,
        JsonNode data
) {}
~~~

Lưu ý:

- `data` là `JsonNode`, tương ứng một JSON subtree. Có thể dùng `byte[]` hoặc một typed union trong định dạng khác.
- `occurredAt` dạng ISO-8601 string; validator sẽ parse với `Instant.parse`, tránh giờ local không timezone.
- `causationId` có thể null nếu không có sự kiện/lệnh nguyên nhân được biết.
- `envelopeVersion` là version **vỏ**; `schemaVersion` là version của **`data` theo event type**.
- `source` chỉ nhận diện origin được khai báo; cần đối chiếu với nguồn **đã xác thực**, không tin client tùy ý.
- `correlationId` trong ví dụ được cấp theo một contract `tenantId/orderId` có grammar hạn chế; không suy ra rằng mọi hệ thống có cùng định dạng.

### 11.3. Exceptions có reason code

~~~java
public final class EnvelopeContractException
        extends RuntimeException {

    private final String code;

    public EnvelopeContractException(String code) {
        super(code);
        this.code = code;
    }

    public EnvelopeContractException(
            String code,
            Throwable cause) {
        super(code, cause);
        this.code = code;
    }

    public String code() {
        return code;
    }
}
~~~

Sử dụng stable codes như `ENVELOPE_VERSION_UNSUPPORTED` hoặc `EVENT_ID_MISMATCH` để phân loại lỗi, không đưa toàn bộ raw payload hoặc thông tin cá nhân vào exception message.

## 12. Wrapper/unwrapper: ranh giới tích hợp hai chiều

Ta triển khai một class `OrderEnvelopeCodec` nhận Spring `Message<?>` và trả **Message mới** có payload thay đổi. Việc tạo message mới là có chủ đích để **không copy mọi header** từ boundary bên ngoài.

### 12.1. Core implementation

~~~java
import java.time.Instant;
import java.time.format.DateTimeParseException;
import java.util.regex.Pattern;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public final class OrderEnvelopeCodec {

    private static final String ENVELOPE_VERSION = "1";
    private static final String SCHEMA_VERSION = "1";
    private static final String EVENT_TYPE = "order.created";
    private static final String EVENT_SOURCE = "order-service";
    private static final String CONTENT_TYPE = "application/json";

    // Grammar cố ý hạn chế để phép ghép bằng '/' không nhập nhằng.
    private static final Pattern IDENTIFIER =
            Pattern.compile("[A-Za-z0-9._-]+");

    private final ObjectMapper mapper;

    public OrderEnvelopeCodec(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    public Message<ExternalEventEnvelope> wrap(
            Message<?> original) {

        if (!(original.getPayload() instanceof OrderCreated event)) {
            throw new EnvelopeContractException(
                    "OUTBOUND_PAYLOAD_TYPE_INVALID");
        }

        validateOrder(event);

        String causationId =
                optionalStringHeader(original, "causationId");

        ExternalEventEnvelope envelope =
                new ExternalEventEnvelope(
                        ENVELOPE_VERSION,
                        event.eventId(),
                        EVENT_SOURCE,
                        EVENT_TYPE,
                        SCHEMA_VERSION,
                        event.occurredAt(),
                        event.tenantId(),
                        businessCorrelationId(
                                event.tenantId(), event.orderId()),
                        causationId,
                        CONTENT_TYPE,
                        mapper.valueToTree(event));

        MessageBuilder<ExternalEventEnvelope> builder =
                MessageBuilder.withPayload(envelope)
                        .setHeader("eventId", event.eventId());

        copyIfPresent(original, builder, "traceparent");

        return builder.build();
    }

    public Message<OrderCreated> unwrap(
            Message<?> incoming) {

        if (!(incoming.getPayload()
                instanceof ExternalEventEnvelope envelope)) {
            throw new EnvelopeContractException(
                    "INBOUND_ENVELOPE_TYPE_INVALID");
        }

        validateEnvelope(envelope);

        final OrderCreated event;
        try {
            event = mapper.treeToValue(
                    envelope.data(), OrderCreated.class);
        }
        catch (JsonProcessingException e) {
            throw new EnvelopeContractException(
                    "PAYLOAD_DECODE_FAILED", e);
        }

        validateOrder(event);

        if (!envelope.eventId().equals(event.eventId())) {
            throw new EnvelopeContractException(
                    "EVENT_ID_MISMATCH");
        }
        if (!envelope.tenantId().equals(event.tenantId())) {
            throw new EnvelopeContractException(
                    "TENANT_ID_MISMATCH");
        }
        if (!envelope.occurredAt().equals(event.occurredAt())) {
            throw new EnvelopeContractException(
                    "OCCURRED_AT_MISMATCH");
        }

        String expectedCorrelation =
                businessCorrelationId(
                        event.tenantId(), event.orderId());

        if (!expectedCorrelation.equals(
                envelope.correlationId())) {
            throw new EnvelopeContractException(
                    "CORRELATION_ID_MISMATCH");
        }

        MessageBuilder<OrderCreated> builder =
                MessageBuilder.withPayload(event)
                        .setHeader("eventId", envelope.eventId())
                        .setHeader(
                                "businessCorrelationId",
                                envelope.correlationId())
                        .setHeader(
                                "sourceSchemaVersion",
                                envelope.schemaVersion())
                        .setHeader(
                                "sourceSystem",
                                envelope.source());

        copyIfPresent(incoming, builder, "traceparent");

        return builder.build();
    }

    private static void validateEnvelope(
            ExternalEventEnvelope e) {

        requireEqual(
                ENVELOPE_VERSION, e.envelopeVersion(),
                "ENVELOPE_VERSION_UNSUPPORTED");
        requireEqual(
                EVENT_TYPE, e.type(),
                "EVENT_TYPE_UNSUPPORTED");
        requireEqual(
                EVENT_SOURCE, e.source(),
                "EVENT_SOURCE_UNTRUSTED");
        requireEqual(
                SCHEMA_VERSION, e.schemaVersion(),
                "PAYLOAD_SCHEMA_UNSUPPORTED");
        requireEqual(
                CONTENT_TYPE, e.contentType(),
                "CONTENT_TYPE_UNSUPPORTED");

        requireId(e.eventId(), "EVENT_ID_INVALID");
        requireId(e.tenantId(), "TENANT_ID_INVALID");
        requireNonBlank(
                e.correlationId(), "CORRELATION_ID_REQUIRED");
        validateInstant(e.occurredAt());

        if (e.data() == null
                || !e.data().isObject()) {
            throw new EnvelopeContractException(
                    "DATA_OBJECT_REQUIRED");
        }

        if (e.causationId() != null) {
            requireId(
                    e.causationId(), "CAUSATION_ID_INVALID");
        }
    }

    private static void validateOrder(OrderCreated e) {
        requireId(e.eventId(), "EVENT_ID_INVALID");
        requireId(e.tenantId(), "TENANT_ID_INVALID");
        requireId(e.orderId(), "ORDER_ID_INVALID");

        if (e.totalMinorUnits() <= 0) {
            throw new EnvelopeContractException(
                    "AMOUNT_NOT_POSITIVE");
        }

        if (e.currency() == null
                || !e.currency().matches("[A-Z]{3}")) {
            throw new EnvelopeContractException(
                    "CURRENCY_FORMAT_INVALID");
        }

        validateInstant(e.occurredAt());
    }

    private static String businessCorrelationId(
            String tenantId,
            String orderId) {

        requireId(tenantId, "TENANT_ID_INVALID");
        requireId(orderId, "ORDER_ID_INVALID");
        return tenantId + "/" + orderId;
    }

    private static void validateInstant(String value) {
        requireNonBlank(value, "OCCURRED_AT_REQUIRED");
        try {
            Instant.parse(value);
        }
        catch (DateTimeParseException ex) {
            throw new EnvelopeContractException(
                    "OCCURRED_AT_INVALID", ex);
        }
    }

    private static void requireId(
            String value, String code) {

        if (value == null
                || !IDENTIFIER.matcher(value).matches()) {
            throw new EnvelopeContractException(code);
        }
    }

    private static void requireNonBlank(
            String value, String code) {

        if (value == null || value.isBlank()) {
            throw new EnvelopeContractException(code);
        }
    }

    private static void requireEqual(
            String expected,
            String actual,
            String code) {

        if (!expected.equals(actual)) {
            throw new EnvelopeContractException(code);
        }
    }

    private static String optionalStringHeader(
            Message<?> message,
            String name) {

        Object raw = message.getHeaders().get(name);
        if (raw == null) {
            return null;
        }
        if (!(raw instanceof String text)) {
            throw new EnvelopeContractException(
                    "HEADER_TYPE_INVALID");
        }
        return text;
    }

    private static void copyIfPresent(
            Message<?> original,
            MessageBuilder<?> builder,
            String name) {

        Object value = original.getHeaders().get(name);
        if (value != null) {
            builder.setHeader(name, value);
        }
    }
}
~~~

**Đây là ví dụ áp dụng cho một event type/source/version duy nhất**, không phải parser đa schema tự động. Những event khác cần model/mapper/dispatch phù hợp. Jackson hỗ trợ Java records ở các phiên bản hiện đại (và project phải có dependencies tương ứng); các kiểu `public` cần source file riêng.

### 12.2. Điểm khác giữa wrap và unwrap

- `wrap` xác định event type/source/schema theo **adapter có thẩm quyền phát sự kiện**, không lấy `source` từ một header người dùng tùy ý.
- `unwrap` **kiểm tra envelope trước** rồi giải mã `data` thành `OrderCreated`.
- `unwrap` so sánh eventId/tenantId/occurredAt giữa vỏ và data, chặn việc khai hai danh tính khác nhau.
- `correlationId` trong ví dụ được đối chiếu với `tenantId/orderId` vì contract nói nó là business group này.
- Cả hai tạo Spring Message **mới**; chỉ truyền header `traceparent` được chọn sau khi adapter xác nhận tin cậy. Các headers `Authorization`, `replyChannel` và `errorChannel` không được đưa qua bộ codec.
- `schemaVersion` được validate trước khi deserialize đúng schema; nếu có v2, dùng Normalizer hoặc version-specific codec khác, không cast v2 thành v1.
- `source` khớp string **không tự xác thực nguồn**: consumer phải kiểm tra TLS identity, token claims, signature hoặc cơ chế tương ứng ở ingress.
- `currency` dạng ba chữ hoa chỉ là syntactic check; phải validate currency allowlist/scale theo nghiệp vụ thật.

### 12.3. Vì sao không cần copy `occurredAt` vào Spring headers?

Business event đã có `occurredAt`, envelope cũng có giá trị gốc và decoder so khớp. Nếu handler muốn dùng, lấy từ typed payload. Copy thêm một bản vào mọi internal header không có lợi nếu tạo khả năng không đồng nhất. Một số flow cần header timestamp để route, nhưng đó phải là mapping có contract và test riêng.

### 12.4. Tại sao validate `data.isObject()`?

Nếu payload event dự kiến là một JSON object, nhận array, string hoặc scalar là contract violation. Không để Jackson cố ép kiểu rồi âm thầm sinh record rỗng/defaults. Với những event type thật sự có array payload, schema phải nêu rõ và dùng validator tương ứng.

### 12.5. Trường hợp tenant có dấu phân cách

Demo cố ý giới hạn `tenantId`/`orderId` bằng regex không chứa dấu `/`. Nếu domain có identifiers tùy ý, phép nối `tenantId + "/" + orderId` có thể collision. Khi đó dùng một **structured business key** (record/object) hoặc key codec có length-prefix/escaping chuẩn, chứ không bỏ validation rồi ghép chuỗi một cách ngây thơ.

## 13. Java DSL: hai integration flows wrap/unwrap

Ta tách outbound và inbound thành hai pipeline. Trong demo, các channel `QueueChannel` đóng vai trò **điểm quan sát/test**; production sẽ thay bằng outbound HTTP/Kafka/AMQP adapter và inbound consumer tương ứng.

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;

@Configuration
@EnableIntegration
public class EnvelopeFlowConfiguration {

    @Bean
    public ObjectMapper envelopeObjectMapper() {
        return new ObjectMapper();
    }

    @Bean
    public OrderEnvelopeCodec orderEnvelopeCodec(
            ObjectMapper envelopeObjectMapper) {
        return new OrderEnvelopeCodec(envelopeObjectMapper);
    }

    @Bean(name = "orders.internal.out")
    public MessageChannel outboundInput() {
        return new DirectChannel();
    }

    @Bean(name = "orders.wire.out")
    public PollableChannel wireOutput() {
        return new QueueChannel();
    }

    @Bean(name = "orders.wire.in")
    public MessageChannel wireInput() {
        return new DirectChannel();
    }

    @Bean(name = "orders.internal.in")
    public PollableChannel inboundOutput() {
        return new QueueChannel();
    }

    @Bean
    public IntegrationFlow envelopeOutboundFlow(
            OrderEnvelopeCodec codec) {

        return IntegrationFlow
                .from("orders.internal.out")
                .transform(codec, "wrap")
                .channel("orders.wire.out")
                .get();
    }

    @Bean
    public IntegrationFlow envelopeInboundFlow(
            OrderEnvelopeCodec codec) {

        return IntegrationFlow
                .from("orders.wire.in")
                .transform(codec, "unwrap")
                .channel("orders.internal.in")
                .get();
    }
}
~~~

Đọc theo dòng chảy:

~~~text
Order Service nội bộ
  Message<OrderCreated>
     -> .transform(codec,"wrap")
  Message<ExternalEventEnvelope>
     -> orders.wire.out (test fixture)
     -> Serialize JSON và gửi transport (production)

Inbound transport
  JSON bytes -> Decode ExternalEventEnvelope (adapter)
     -> orders.wire.in
     -> .transform(codec,"unwrap")
  Message<OrderCreated>
     -> orders.internal.in (test fixture)
     -> Fulfillment handler (production)
~~~

**Chú ý lớp còn thiếu có chủ đích:** code trên chưa serialize envelope thành byte[] trên outbound hoặc deserialize byte[] trên inbound. Hai việc đó thuộc **transport adapter/serializer**. Không nên gọi demo này là tích hợp Kafka hoàn chỉnh; nó minh họa Spring Integration routing/transform boundaries và cho phép kiểm thử payload, headers, metadata.

### 13.1. Nếu cần chuyển qua HTTP

Một Spring Integration HTTP outbound adapter có thể gửi JSON bytes được tạo từ envelope, kèm `Content-Type: application/json` và authentication cho hop hiện tại. HTTP inbound cần xác thực, giới hạn kích thước, parse JSON, validate rồi chuyển typed envelope vào flow. HTTP `Authorization` không được copy nguyên vào `data` hoặc onward broker header.

### 13.2. Nếu cần chuyển qua Kafka hoặc RabbitMQ

Outbound adapter sử dụng serializer cho `ExternalEventEnvelope`/JSON bytes. Kafka topic/partition/offset hoặc AMQP delivery tag là **transport metadata**. Inbound adapter giải mã và chuyển vào wrapper validation; một broker record có thể được nhận nhiều lần, vì vậy `eventId` trong envelope cần ổn định để Idempotent Receiver hoạt động.

### 13.3. Nếu cần request-reply qua Gateway

Một Gateway có thể có `replyChannel`/`errorChannel` nội bộ để khớp response. Không thể mặc nhiên serialize `replyChannel` Java object và gửi qua broker khác rồi kỳ vọng nó tồn tại ở JVM kia. Với cross-system request-reply, phải định nghĩa **reply destination, request/correlation ID, timeout, error outcome và security** như một protocol riêng (có thể dùng envelope). Nếu producer chỉ phát event async, không cần carry replyChannel.

## 14. Unit test wrapper/unwrapper và JSON round trip

Đoạn test dưới đây kiểm tra codec mà **không cần Spring context**. Nó chứng minh event identity/correlation được giữ qua serialize/deserialize envelope và original business payload có thể khôi phục.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class OrderEnvelopeCodecTest {

    private final ObjectMapper mapper = new ObjectMapper();
    private final OrderEnvelopeCodec codec =
            new OrderEnvelopeCodec(mapper);

    private OrderCreated sample() {
        return new OrderCreated(
                "evt-order-1001",
                "tenant-a",
                "ORDER-101",
                250000,
                "VND",
                "2026-11-21T02:00:00Z");
    }

    @Test
    void wrapAndUnwrapPreserveLogicalEvent() throws Exception {
        OrderCreated event = sample();

        Message<OrderCreated> internal =
                MessageBuilder.withPayload(event)
                        .setHeader(
                                "causationId",
                                "cmd-place-order-1001")
                        .setHeader(
                                "traceparent",
                                "00-11111111111111111111111111111111"
                                + "-2222222222222222-01")
                        .build();

        Message<ExternalEventEnvelope> wrapped =
                codec.wrap(internal);

        String wireJson = mapper.writeValueAsString(
                wrapped.getPayload());

        ExternalEventEnvelope received =
                mapper.readValue(
                        wireJson, ExternalEventEnvelope.class);

        Message<OrderCreated> unwrapped =
                codec.unwrap(
                        MessageBuilder.withPayload(received)
                                .build());

        assertEquals(
                event, unwrapped.getPayload());

        assertEquals(
                "evt-order-1001",
                received.eventId());
        assertEquals(
                "tenant-a/ORDER-101",
                received.correlationId());
        assertEquals(
                "order-service",
                received.source());
        assertEquals(
                "order.created",
                received.type());
        assertEquals(
                "1",
                received.schemaVersion());
        assertEquals(
                "1",
                received.envelopeVersion());
        assertEquals(
                "cmd-place-order-1001",
                received.causationId());

        assertEquals(
                "evt-order-1001",
                unwrapped.getHeaders().get("eventId"));
        assertEquals(
                "tenant-a/ORDER-101",
                unwrapped.getHeaders()
                        .get("businessCorrelationId"));
    }

    @Test
    void wrapperDoesNotCopySecretInternalHeaders() {
        Message<OrderCreated> input =
                MessageBuilder.withPayload(sample())
                        .setHeader("Authorization", "Bearer SECRET")
                        .setHeader("internalDebug", "do-not-export")
                        .build();

        Message<ExternalEventEnvelope> result =
                codec.wrap(input);

        assertNull(
                result.getHeaders().get("Authorization"));
        assertNull(
                result.getHeaders().get("internalDebug"));

        String envelopeJson =
                result.getPayload().data().toString();
        assertFalse(envelopeJson.contains("SECRET"));
    }

    @Test
    void envelopeEventIdMustEqualPayloadEventId() {
        ExternalEventEnvelope good =
                codec.wrap(
                        MessageBuilder.withPayload(sample())
                                .build())
                        .getPayload();

        ExternalEventEnvelope forged =
                new ExternalEventEnvelope(
                        good.envelopeVersion(),
                        "evt-fake",
                        good.source(),
                        good.type(),
                        good.schemaVersion(),
                        good.occurredAt(),
                        good.tenantId(),
                        good.correlationId(),
                        good.causationId(),
                        good.contentType(),
                        good.data());

        EnvelopeContractException error =
                assertThrows(
                        EnvelopeContractException.class,
                        () -> codec.unwrap(
                                MessageBuilder.withPayload(forged)
                                        .build()));

        assertEquals("EVENT_ID_MISMATCH", error.code());
    }

    @Test
    void unknownEnvelopeVersionIsRejected() {
        ExternalEventEnvelope good =
                codec.wrap(
                        MessageBuilder.withPayload(sample())
                                .build())
                        .getPayload();

        ExternalEventEnvelope unsupported =
                new ExternalEventEnvelope(
                        "99",
                        good.eventId(),
                        good.source(),
                        good.type(),
                        good.schemaVersion(),
                        good.occurredAt(),
                        good.tenantId(),
                        good.correlationId(),
                        good.causationId(),
                        good.contentType(),
                        good.data());

        EnvelopeContractException error =
                assertThrows(
                        EnvelopeContractException.class,
                        () -> codec.unwrap(
                                MessageBuilder
                                        .withPayload(unsupported)
                                        .build()));

        assertEquals(
                "ENVELOPE_VERSION_UNSUPPORTED",
                error.code());
    }
}
~~~

### 14.1. Test JSON chứ không chỉ test object equality

Hai DTO Java có thể so sánh bằng nhau nhưng serializer làm mất trường hoặc đặt tên sai. Test `writeValueAsString` + `readValue` đưa cả envelope qua representation JSON, giúp phát hiện các lỗi serialization contract cơ bản.

Với sản phẩm thực, nên thêm **contract tests dùng chính sample JSON của các producer**, kiểm tra naming strategy, unknown fields, numeric range, version policy và serializer configuration thật.

### 14.2. `traceparent` thuộc transport/tracing boundary

Trong test round-trip JSON trên, `traceparent` nằm trong Spring header của `wrapped` nhưng **không nằm trong JSON envelope**. Sau khi serialize chỉ payload rồi reconstruct một Message mới, traceparent **không tự tồn tại**. Đó là hành vi có chủ đích: production adapter/instrumentation phải chuyển W3C tracing context bằng HTTP/Kafka headers hoặc một policy envelope explicit. Không nói việc giữ `traceparent` ở local Message đồng nghĩa trace đã được propagate cross-system.

### 14.3. Test security ở đúng điểm

Test wrapper không copy `Authorization` là cần nhưng **chưa đủ**: outbound adapter vẫn có thể copy headers theo một mapper khác. Cần thêm transport adapter tests xác nhận credential của hop trước không xuất hiện ở broker/remote logs, và authentication của hop mới được cấu hình độc lập.

## 15. Integration test qua Spring Integration channels

Test này kiểm tra wiring của Java DSL, không giả lập HTTP/Kafka. Dùng `PollableChannel` ở hai đầu output.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = EnvelopeFlowConfiguration.class)
class EnvelopeFlowIntegrationTest {

    @Autowired
    @Qualifier("orders.internal.out")
    MessageChannel outboundInput;

    @Autowired
    @Qualifier("orders.wire.out")
    PollableChannel outboundWire;

    @Autowired
    @Qualifier("orders.wire.in")
    MessageChannel inboundWire;

    @Autowired
    @Qualifier("orders.internal.in")
    PollableChannel inboundOutput;

    @Test
    void oneLogicalEventFlowsThroughBothBoundaries() {
        OrderCreated businessEvent = new OrderCreated(
                "evt-order-2001",
                "tenant-a",
                "ORDER-201",
                75000,
                "VND",
                "2026-11-21T02:05:00Z");

        assertTrue(outboundInput.send(
                MessageBuilder.withPayload(businessEvent)
                        .setHeader(
                                "causationId",
                                "cmd-order-2001")
                        .build()));

        Message<?> wrapped =
                outboundWire.receive(1000);

        assertNotNull(wrapped);
        assertInstanceOf(
                ExternalEventEnvelope.class,
                wrapped.getPayload());

        ExternalEventEnvelope envelope =
                (ExternalEventEnvelope) wrapped.getPayload();

        assertEquals(
                "evt-order-2001", envelope.eventId());
        assertEquals(
                "tenant-a/ORDER-201",
                envelope.correlationId());

        assertTrue(inboundWire.send(
                MessageBuilder.withPayload(envelope)
                        .build()));

        Message<?> unwrapped =
                inboundOutput.receive(1000);

        assertNotNull(unwrapped);
        assertEquals(
                businessEvent, unwrapped.getPayload());
        assertEquals(
                "evt-order-2001",
                unwrapped.getHeaders().get("eventId"));
        assertEquals(
                "tenant-a/ORDER-201",
                unwrapped.getHeaders()
                        .get("businessCorrelationId"));

        assertNull(outboundWire.receive(0));
        assertNull(inboundOutput.receive(0));
    }
}
~~~

### 15.1. Các giới hạn rõ ràng

- Hai flows đang chạy trong cùng ApplicationContext; chưa kiểm thử JSON serialization ở wire adapter (unit test có JSON round trip riêng).
- QueueChannel không bảo đảm broker durability/ACK.
- Không có authentication thật; `source`/`tenantId` cần được xác minh ở adapter ingress.
- Không có Idempotent Receiver; redelivery có thể đưa cùng `eventId` qua flow hai lần.
- Không có error routing; một invalid envelope trong `DirectChannel` thường làm sender nhận exception, có thể được Spring bọc.
- `MessageHeaders.ID` của output không bắt buộc giống input. Business `eventId` phải giống.
- Nếu test suites chia sẻ cached ApplicationContext, cần drain QueueChannels/cô lập context để tránh test contamination.

### 15.2. Nên bổ sung integration test cho các trường hợp nào?

| Trường hợp | Kỳ vọng |
|---|---|
| Inbound envelope version `"99"` | Reject, không tới business channel |
| Inbound payload schema version `"99"` | Reject/unsupported path |
| Event type `payment.captured` trên Order codec | Reject, không cast |
| Envelope eventId khác data eventId | Reject với reason |
| Envelope tenantId khác data tenantId | Reject |
| Correlation key không khớp order | Reject |
| Data thiếu orderId | Reject |
| Amount âm/zero ngoài contract | Reject |
| ISO timestamp sai | Reject |
| Source không được cho phép | Reject nhưng không xem string-check là authentication |
| Transport header chứa token | Không leak qua boundary |
| Broker delivery duplicate | Downstream dedup theo stable eventId |
| Inbound serialized JSON > limit | Reject trước Jackson parse |
| JSON có nesting quá sâu | Parser constraint/reject |
| Schema registry/remote API outage | Bounded retry nếu transient |

### 15.3. Integration test cho invalid header có thể dùng cause chain

Một `DirectChannel` có thể bọc `EnvelopeContractException` trong `MessageHandlingException`/`MessagingException`. Khi test, duyệt `Throwable.getCause()` để assert reason code thay vì phụ thuộc vào một wrapper cụ thể trong version framework.
## 16. HTTP → broker → consumer: hợp đồng chuyển từng hop

Envelope qua nhiều hệ thống cần **adapter mapping** rõ ràng. Một JSON string đi qua HTTP có thể được chuyển vào Kafka như một value dạng byte array, kèm một số headers tracing/transport riêng.

~~~mermaid
sequenceDiagram
    participant O as Order Service
    participant G as Integration Gateway
    participant K as Kafka/AMQP
    participant C as Fulfillment Consumer

    O->>G: HTTP JSON Envelope + Authorization + traceparent
    G->>G: Authn/Authz + validate envelope/data
    G->>G: Preserve eventId/source/type/occurredAt
    G->>K: JSON bytes + trusted transport headers
    K-->>C: Delivery (có thể redelivery)
    C->>C: Decode + verify envelope
    C->>C: Idempotent Receiver theo eventId/source/tenant
    C->>C: Business handler
~~~

### 16.1. Hop 1: HTTP inbound

Nên làm tại boundary:

1. Xác thực token/mTLS hoặc cơ chế nguồn tương ứng.
2. Áp dụng request size/timeouts, content type và parser constraints.
3. Giải mã envelope theo `envelopeVersion` mà consumer hỗ trợ.
4. Kiểm tra `source`/`tenantId` so với danh tính thực của caller.
5. Đối chiếu các trường lặp giữa vỏ và data.
6. Từ chối event type hoặc payload schema chưa hỗ trợ, với reason code.
7. Chỉ sau đó chuyển vào internal normalized flow.

Một HTTP header `X-Event-Id` nếu do client tự khai phải được đối chiếu với envelope, hoặc không sử dụng như nguồn dữ liệu danh tính. **Không tạo hai nguồn sự thật** mà không có quy tắc nhất quán.

### 16.2. Hop 2: gửi vào Kafka/AMQP

Một mapper hợp đồng có thể đặt:

~~~text
Broker record value:
  UTF-8 JSON bytes của ExternalEventEnvelope

Broker record key:
  partitionKey = trusted tenantId/orderId, nếu cần ordering

Broker headers:
  traceparent = tracing propagation theo policy
  contentType = application/json
  messageType = order.created, nếu adapter yêu cầu

Broker-provided metadata:
  topic, partition, offset, delivery attempt
~~~

**Partition key** không mặc nhiên là eventId. Nếu muốn những events của cùng order cùng partition để giữ thứ tự per-order, có thể dùng một business key ổn định được canonicalize; nếu muốn cân bằng tải kiểu khác, cần contract khác. Đừng dùng secret hoặc PII làm partition key tùy tiện.

### 16.3. Hop 3: broker consumer

Inbound adapter:

- Đọc value bytes và decode envelope.
- Đọc trace context từ broker headers theo instrumentation.
- Không tin source/tenant chỉ vì chúng có mặt trong JSON; cần trust model/broker ACL và validation.
- Dùng stable event key để dedup trước side effects.
- Chỉ ACK/commit offset theo policy sau khi xử lý đủ bền vững.
- Route non-retryable invalid contract tới quarantine/DLQ.
- Bounded retry với lỗi transient như DB/network unavailable.

### 16.4. Một hop chuyển mã nhưng không tạo business event mới

Nếu Gateway chỉ chuyển JSON sang Avro hoặc đổi từ HTTP sang Kafka mà **không đổi logical event**, các trường eventId/source/type/occurredAt không nên bị thay chỉ vì transport khác. Có thể ghi thêm metadata hop như `gatewayReceivedAt` trong log/trace hoặc một transport header riêng; không ghi đè business occurrence time.

## 17. Re-envelope hay lồng nhiều envelope?

Một gateway đôi khi cần gói một event vào **envelope cho hệ thống đích** khác:

~~~text
Original business event
  -> Envelope A (external partner)
  -> Gateway
  -> Envelope B (internal broker contract)
~~~

Có hai cách thiết kế:

1. **Unwrap A → validate/normalize → wrap B**: phù hợp khi hai contracts khác nhau và gateway được ủy quyền chuyển đổi.
2. **Forward A như opaque payload bên trong B**: phù hợp với store-and-forward hoặc tunneling, nhưng làm người nhận phải hiểu **hai lớp**.

Không nên mặc định cách thứ hai tốt hơn chỉ vì ít decode. Nếu vỏ B bao toàn bộ vỏ A, bên nhận phải biết đường dẫn tới eventId, contentType/schemaVersion của **hai lớp**, biết lúc nào validate chữ ký A và có chính sách giới hạn kích thước/nesting.

### 17.1. Original metadata và forwarding metadata

Một message forwarded qua gateway có thể cần cả:

~~~text
originSource = order-service
originEventId = evt-order-1001

forwarder = integration-gateway
forwardedAt = 2026-11-21T02:00:05Z
forwardingAttemptId = attempt-3
~~~

Trong đó origin identity là **end-to-end**; `forwardingAttemptId` chỉ là thông tin một lần publish, có thể thay khi retry. Nếu contract envelope không có trường forwarder, đặt nó trong audit/tracing hoặc transport metadata theo policy thay vì tự thêm field có thể làm consumer strict reject.

### 17.2. Đổi `source` khi nào?

Nếu gateway chỉ chuyển tiếp cùng logical event, `source` gốc nên được giữ. Nếu gateway tạo một **business event mới** sau khi xử lý có ý nghĩa (chẳng hạn `order.accepted.by.gateway`), nó có thể là source của event mới, với event ID mới và causation liên kết event gốc. Không đổi `source` để mạo danh một producer khác.

### 17.3. Không lồng envelope vô hạn

Nếu mỗi trong mười microservices tự bao thêm một vỏ, size và độ khó debug tăng, thậm chí tạo nested payload không giới hạn. Cần mô hình thống nhất cho metadata end-to-end và hop-local, có giới hạn nesting/depth và hợp đồng unwrap cụ thể.

## 18. Content-type, encoding, compression và bảo vệ parser

Một envelope JSON có thể chứa `data` dạng object, nhưng các hệ thống khác có thể truyền bytes được nén, binary payload hoặc base64.

### 18.1. Content type thuộc lớp nào?

- HTTP `Content-Type`: media type của **HTTP request body**.
- Envelope `contentType` trong demo: media type của **`data`**.
- Kafka record serialization: encoding của **record value bytes**.
- Spring `MessageHeaders.CONTENT_TYPE`: metadata nội bộ có thể được converter dùng.

Chúng có thể giống nhau trong một thiết kế JSON đơn giản, nhưng không luôn tương đương. Ví dụ HTTP body chứa **CloudEvents structured JSON** mà CloudEvents `datacontenttype` mô tả payload binary khác.

### 18.2. Không tin `contentType` mà không kiểm tra bytes

Nếu header nói JSON nhưng body là binary không hợp lệ, decoder phải reject, không tự thử vô hạn mọi codec. Nếu type/version không tương thích, dùng error reason thay vì tự áp parser khác một cách âm thầm.

### 18.3. Giới hạn kích thước và độ sâu

Trước khi parse dữ liệu từ nguồn ngoài:

- Giới hạn request/record size theo contract.
- Giới hạn JSON nesting depth, số trường, độ dài chuỗi.
- Giới hạn decompress ratio để tránh zip bombs.
- Kiểm tra timeout và bộ nhớ parser.
- Không log toàn bộ raw body khi lỗi parse.

Envelope wrapper **không phải** cơ chế bảo vệ trước payload không tin cậy nếu không có các giới hạn này.

## 19. Identity và Idempotent Receiver xuyên transport

Broker có thể redeliver event sau khi business handler commit nhưng trước khi ACK. Nếu consumer dùng `MessageHeaders.ID` hoặc delivery tag làm idempotency key, retry có thể được xem như event mới.

~~~text
First broker delivery:
  messageId = UUID-A
  eventId   = evt-order-1001
  source    = order-service

Redelivery:
  messageId = UUID-B
  eventId   = evt-order-1001
  source    = order-service
~~~

Idempotency key nên ổn định, ví dụ:

~~~text
(tenantId, source, eventId, eventType)
~~~

Hoặc `(source,eventId)` khi domain/chuẩn event đảm bảo uniqueness trong namespace đó. Phải so fingerprint nếu cùng key nhưng payload khác, thay vì âm thầm bỏ qua event mâu thuẫn.

### 19.1. Tại sao không dùng orderId làm idempotency key cho mọi event?

Một order có thể có nhiều **business events khác nhau** (created, paid, shipped, cancelled). Nếu dedup chỉ theo `orderId`, event paid có thể bị chặn vì order created đã được xử lý. Idempotency key phải nhận diện đúng **tác vụ/sự kiện cần thực hiện tối đa một lần**, không phải chỉ nhận diện đối tượng nghiệp vụ.

### 19.2. Không tạo event ID mới trong unwrap

Một anti-pattern:

~~~java
// Sai: redelivery tạo idempotency key mới.
String newEventId = java.util.UUID.randomUUID().toString();
~~~

Nếu một intermediary tạo event mới thật sự, hãy ghi causation. Nếu chỉ deserialize/forward event, giữ logical event ID gốc.

### 19.3. Exactly-once không tự đến từ envelope

Một envelope có eventId giúp dedup, nhưng **không bảo đảm side effect exactly-once**. Nếu marker được commit trước business action, crash có thể làm mất tác vụ; nếu side effect commit trước marker, retry có thể làm trùng. Khi marker và business mutation cùng DB, dùng unique constraint và transaction chung; khi remote side effect, dùng idempotency API/reconciliation hoặc inbox/outbox phù hợp.

## 20. Correlation, Aggregator và Resequencer qua các hệ thống

Giả sử ba hệ thống phát ba event:

~~~text
Order Service:     OrderCreated(orderId=ORDER-101)
Payment Service:   PaymentCaptured(orderId=ORDER-101)
Inventory Service: InventoryReserved(orderId=ORDER-101)
~~~

Mỗi event có `eventId` và `source` riêng. Chúng có thể dùng envelope versions khác nhau hoặc transport headers khác nhau, nhưng phải mang **một business identity chung** nếu muốn Aggregator hội tụ.

~~~mermaid
flowchart LR
    O["Envelope OrderCreated"] --> UO["Unwrap/Normalize"]
    P["Envelope PaymentCaptured"] --> UP["Unwrap/Normalize"]
    I["Envelope InventoryReserved"] --> UI["Unwrap/Normalize"]
    UO --> A[("Aggregator by BusinessKey")]
    UP --> A
    UI --> A
    A --> OUT["OrderReady"]
~~~

### 20.1. Correlation metadata phải có hợp đồng

Không mặc định mọi `correlationId` đều là order ID. Một Payment Service có thể gửi `correlationId` bằng request ID của giao dịch ngân hàng. Trước khi Aggregator, cần canonical business key `(tenantId,orderId)` và đối chiếu mapping giữa external order references.

### 20.2. Sequence metadata có thể là hop-local

`sequenceNumber` và `sequenceSize` được Splitter/Resequencer sử dụng để sắp thứ tự parts. Nếu qua broker, chỉ chuyển chúng trong envelope/headers nếu **contract của batch/sequence yêu cầu**. Không lấy `schemaVersion` hoặc `eventId` thay sequence number.

### 20.3. Version khác không tách group

OrderCreated schema v1 và PaymentCaptured schema v2 cho cùng ORDER-101 vẫn có thể thuộc một group. Không dùng `(orderId,schemaVersion)` làm group key trừ khi nghiệp vụ thực sự phân biệt hai workflow runs độc lập theo một run ID đã thống nhất.

### 20.4. Filter/Normalizer trước Aggregator

Nếu Filter bỏ một message cần thiết nhưng Aggregator vẫn đợi `sequenceSize=3`, group có thể kẹt; nếu Normalizer làm mất correlation headers, các part có thể rơi vào nhóm khác. Cần test toàn pipeline, không chỉ test từng endpoint.

## 21. Security: authentication, integrity và chữ ký qua từng hop

Envelope có thể chứa `source="order-service"` và `tenantId="tenant-a"`, nhưng một client không tin cậy có thể **tự viết hai chuỗi đó**.

### 21.1. Identity khai báo không phải identity đã xác thực

Cần đối chiếu:

- Caller identity từ mTLS/JWT/broker ACL.
- Source mà caller được phép đại diện.
- Tenant/subject trong envelope so với principal/claims.
- Event type/schema mà source được phép phát.
- Quyền truy cập resource bên trong `data`.

Không dùng việc JSON hợp lệ để suy ra message được phép thực hiện side effect.

### 21.2. Chữ ký trên raw wire representation

Nếu cần xác thực **tính toàn vẹn** của message, có thể dùng digital signature/HMAC theo protocol. Nhưng chữ ký chỉ hợp lệ cho **đúng canonical representation hoặc bytes đã được ký**:

~~~text
Signer ký JSON bytes A.
Gateway parse -> reserialize thành JSON bytes B.
Bytes B khác A (field order/whitespace/encoding).
Chữ ký trên A không nhất thiết còn đúng với B.
~~~

Nếu gateway phải thay đổi representation, nó cần **verify chữ ký cũ trước**, sau đó ký representation mới bằng identity/key được ủy quyền nếu contract yêu cầu; không copy chữ ký cũ và coi như đã xác thực bytes mới.

### 21.3. TLS bảo vệ hop, không tự chứng thực event end-to-end

TLS/mTLS bảo vệ kết nối giữa hai endpoints trong một hop, nhưng gateway có thể đọc/biến đổi dữ liệu. Nếu yêu cầu nguồn gốc end-to-end, cần threat model và cơ chế ký/audit phù hợp. Không mặc định trace headers hoặc event ID là bằng chứng cryptographic integrity.

### 21.4. Không truyền bearer token qua nhiều hệ thống

HTTP Authorization từ Order Service đến Gateway thường **không phải** credential phù hợp cho Kafka Consumer hoặc Fulfillment Service. Dùng identity/authorization riêng ở từng hop, scoped tokens hoặc mTLS. Không đặt bearer token trong envelope/data hoặc logs.

### 21.5. PII và tenant isolation

Không dùng email, số điện thoại hay địa chỉ khách làm `eventId` hoặc correlation key chỉ để tiện debug. Nếu cần đưa thông tin cá nhân trong `data`, có classification, encryption/access control, retention và data minimization. Trong shared broker, việc tenantId được khai báo trong envelope không thay ACL/authorization.

## 22. Lỗi, retry, DLQ và replay

Envelope validation có thể thất bại ở nhiều tầng:

| Lỗi | Ví dụ | Loại | Cách xử lý gợi ý |
|---|---|---|---|
| Invalid JSON bytes | Payload không parse được | Deterministic contract | Quarantine/non-retryable |
| Unsupported envelope version | `"99"` | Contract/rollout | Explicit unsupported path |
| Unsupported event type | `payment.captured` vào Order codec | Contract/routing | Router/quarantine |
| Unsupported payload schema | Schema v3 chưa có converter | Contract/rollout | Quarantine cho tới khi có adapter |
| Header/body mismatch | Event ID ở vỏ khác trong data | Integrity failure | Reject, audit |
| Tenant/source mismatch | Source khai không phù hợp principal | Security failure | Deny/audit |
| Timestamp invalid | Không phải ISO-8601 Instant | Contract | Reject |
| Data too large | Vượt ingress cap | Security/contract | Reject trước parse |
| Schema registry unavailable | Không thể resolve schema ID | Transient infra | Bounded retry |
| Broker temporarily unavailable | Publish timeout | Transient/unknown | Retry với event ID ổn định |
| Remote business API timeout | Không rõ đã commit chưa | Unknown outcome | Reconcile/idempotent remote |
| Duplicate delivery | Cùng event ID qua broker | Expected transport | Idempotent no-op/return result |

### 22.1. Discard channel không phải DLQ tự động

Trong Spring Integration, `discardChannel` thường nhận message bị Filter từ chối; `errorChannel` thường nhận `ErrorMessage` từ error handling; broker DLQ có policy riêng. Không đồng nhất ba cơ chế.

Một envelope chưa hỗ trợ có thể đi vào **quarantine** có reason `UNSUPPORTED_ENVELOPE_VERSION` và metadata an toàn, rồi được reprocess sau khi nâng cấp consumer.

### 22.2. Lỗi deterministic không nên retry vô hạn

Một event có `eventId` ở vỏ khác `data.eventId` sẽ fail y nguyên sau mỗi redelivery. Retry lặp làm tăng lag nhưng không sửa dữ liệu. Đặt non-retryable outcome rõ, giữ thông tin điều tra, không làm mất dữ liệu khi hợp đồng không cho phép.

### 22.3. Retry khi kết quả publish không rõ

Gateway gửi tới broker bị timeout: có thể broker **đã lưu record** nhưng response/ACK về gateway bị mất. Nếu gateway retry cùng logical event, có thể tạo **hai broker records**. Hệ thống nhận cần idempotency bằng `eventId` ổn định; không cấp event ID mới cho mỗi retry.

### 22.4. Reprocessing sau nhiều ngày

Quarantine/DLQ có thể chứa envelope version cũ. Khi triển khai adapter v2, đừng xóa support v1 trước khi hết replay/retention window. Nếu muốn migrate archived payloads, phải có documented migration và preserve event identity theo contract.

## 23. Nâng cấp envelope khi nhiều hệ thống deploy lệch thời điểm

Không phải lúc nào tất cả producers/gateways/consumers đều deploy đồng thời. Cần định nghĩa **support matrix** cho envelopeVersion và payload schemaVersion.

| Envelope version | Payload version | Producer | Gateway | Consumer | Kết quả |
|---|---|---|---|---|---|
| 1 | 1 | Legacy | Support | Support | Chấp nhận |
| 1 | 2 | New producer | Support | Có normalizer v2 | Chấp nhận sau normalize |
| 2 | 2 | New producer | Chưa hỗ trợ vỏ 2 | Có thể hỗ trợ payload | **Gateway reject** |
| 1 | 99 | Unexpected | Support vỏ 1 | Unsupported data | Quarantine |
| 99 | 1 | Unexpected | Unsupported vỏ | Không giải mã an toàn | Reject/quarantine |

### 23.1. Expand consumer trước khi producer phát version mới

Một quy trình:

~~~text
1. Consumer/Gateway hỗ trợ envelopeVersion 1 và 2.
2. Contract tests cho cả hai.
3. Producer bật version 2 canary.
4. Theo dõi unsupported/mismatch/latency.
5. Ngừng phát version 1.
6. Đợi backlog, DLQ, archive/replay window.
7. Retire decoder/transformer v1 theo runbook.
~~~

Nếu chỉ đổi payload schema v1→v2, không nhất thiết đổi envelopeVersion. Nếu đổi semantics/required fields của chính vỏ, phải có envelope version migration rõ.

### 23.2. Backward-compatible change vẫn cần test

Thêm một field tùy chọn vào envelope có thể được reader tolerant chấp nhận, nhưng strict JSON reader có thể từ chối unknown fields. Đổi tên `eventId`, thay kiểu timestamp hoặc bỏ field bắt buộc có thể breaking. Không suy "thêm field = chắc chắn compatible" mà không biết decoder/version policy.

### 23.3. Canonical contract nội bộ là một trục thứ ba

Một gateway có thể nhận nhiều envelope versions, nhiều payload schema versions nhưng đưa tất cả về **một canonical business DTO nội bộ**. Canonical schema có thể lại nâng cấp độc lập; khi đó các downstream handlers cần compatibility/migration test riêng.

## 24. Tracing và logging đa hop

Một trace hữu ích có thể mô tả:

~~~text
traceId=trace-1001
  span A: Order Service tạo event
  span B: HTTP send Gateway
  span C: Gateway validate + broker publish
  span D: Consumer receive
  span E: Fulfillment business action
~~~

Các span IDs thường thay đổi theo bước. Business eventId vẫn là `evt-order-1001`, giúp liên kết retries/replays khi một trace bị kết thúc và một trace mới bắt đầu.

### 24.1. Một log chuẩn cho từng hop

~~~text
service=integration-gateway
flow=order-event-forward
eventType=order.created
source=order-service
eventId=evt-order-1001
envelopeVersion=1
schemaVersion=1
outcome=FORWARDED
transport=kafka
attempt=2
traceId=trace-1001
~~~

Cần kiểm soát access và retention cho eventId/tenant, có thể dùng hash/redaction. Không để message payload và authentication tokens xuất hiện trong public logs.

### 24.2. Metric labels không chứa raw IDs

| Metric | Mục đích | Labels nên dùng |
|---|---|---|
| `envelope_received_total` | Lưu lượng nhận | source, eventType, version |
| `envelope_validated_total` | Hợp đồng hợp lệ | eventType, result |
| `envelope_rejected_total` | Lỗi validation/security | reasonCode, source |
| `envelope_forwarded_total` | Thông điệp đã forward | transport, eventType |
| `envelope_unwrapped_total` | Số event giải bọc | eventType |
| `envelope_round_trip_latency_seconds` | Độ trễ qua các hop | flow, transport |
| `envelope_duplicate_delivery_total` | Số redeliveries | consumer, eventType |
| `envelope_unknown_version_total` | Version chưa hỗ trợ | envelopeVersion |
| `envelope_quarantine_total` | Cách ly | reason |
| `envelope_payload_bytes` | Kích thước | eventType, bucket |

**Không** dùng eventId, orderId, customerId, traceId hoặc full correlationId làm metric labels cardinality cao. Chúng thích hợp hơn cho logs/traces có quyền và quy tắc retention.

### 24.3. Những dấu hiệu hỏng hợp đồng

- Tỷ lệ `EVENT_ID_MISMATCH` tăng sau khi deploy gateway.
- Fulfillment nhận envelope nhưng `source` khác peer identity.
- Broker redelivery tạo event ID mới.
- `occurredAt` bị thay bằng gateway receive time.
- Consumer không đọc được version mới.
- Tracing mất ở HTTP→Kafka adapter.
- DLQ tăng với `CONTENT_TYPE_UNSUPPORTED`.
- Cross-tenant mismatches xuất hiện sau thay đổi tenant routing.

## 25. Hiệu năng, kích thước và backpressure

Envelope có overhead: lặp metadata trong mỗi record, JSON object nesting, serialization/deserialization và đôi khi payload bị nhân đôi trong body/header.

### 25.1. Ước lượng overhead

Một payload `OrderCreated` nhỏ có thể chỉ vài trăm bytes; envelope metadata thêm source, event type, versions, IDs và timestamp. Tỷ lệ overhead **phụ thuộc kích thước payload**, không thể mặc định "rất nhỏ". Với millions events per second, thêm hàng trăm bytes mỗi event có thể ảnh hưởng broker bandwidth và storage.

### 25.2. Không bọc payload lớn vào JSON không kiểm soát

Với image/file/document lớn:

- Có thể dùng object storage + signed reference/Claim Check.
- Envelope chứa object ID, checksum, contentType và authorization scope.
- Dữ liệu tải từ object storage phải được kiểm tra quyền và integrity.
- Quản lý TTL của reference khác TTL của event.
- Không coi signed URL là thông tin có thể log hoặc forward tự do.

### 25.3. Backpressure tại gateway

Nếu broker chậm, gateway không nên nhận HTTP request và **ACK thành công nghiệp vụ** khi event chưa được persist đủ theo contract. Có thể dùng transactional outbox/buffer bền vững, retry và backpressure. Một envelope hợp lệ không chứng minh broker đã lưu.

### 25.4. Tránh n+1 metadata lookups

Không gọi schema registry, tenant service hoặc ID mapping API cho từng event nếu có caching/contract cho phép. Nhưng cache cần invalidation/version policy, timeout và bounded retries; dữ liệu auth không được cache vô thời hạn thiếu kiểm soát.

### 25.5. Schema evolution và memory

Deserializer tạo toàn bộ `JsonNode` cho dữ liệu lớn có thể tốn RAM. Khi cần streaming, dùng parser streaming/size bounds hoặc codec nhị phân phù hợp. Không để unknown-version messages tích tụ vô hạn trong in-memory queues.

## 26. Anti-pattern thường gặp

| Anti-pattern | Hậu quả | Giải pháp |
|---|---|---|
| Đưa toàn bộ Spring headers vào envelope | Lộ token, objects không portable | Header allowlist |
| Dùng broker offset làm eventId | ID thay khi republish | Stable logical event ID |
| Tạo UUID mới mỗi lần forward/retry | Dedup thất bại | Giữ eventId khi forward |
| Gateway đổi `source` của event gốc | Mất provenance | Giữ origin, log forwarder riêng |
| Ghi đè occurredAt bằng receivedAt | Sai thời gian nghiệp vụ | Tách original/hop timestamps |
| Dùng traceId làm business correlation | Split/merge group sai | Stable business key |
| Dùng eventId làm group key Aggregator nhiều event | Mỗi part ở group riêng | Correlate theo order/workflow |
| Dùng orderId đơn lẻ làm idempotency key cho nhiều event | Chặn event hợp lệ | Scope theo event/operation |
| Dùng schemaVersion thay business revision | Sai thứ tự/state | Tách version kinds |
| Giữ schemaVersion cũ sau đổi payload | Consumer decode sai | Cập nhật payload version |
| Unknown envelope version mặc định v1 | Silent corruption | Reject/quarantine |
| `source` string được coi là authenticated | Spoofing | Xác thực peer/tenant |
| Copy chữ ký cũ sau reserialize | Invalid integrity | Verify rồi re-sign |
| Tin TLS hop = end-to-end signature | Gateway có thể biến đổi bytes | Threat model end-to-end |
| Copy Authorization qua broker | Credential leakage | Authentication từng hop |
| Drop invalid message không audit | Mất event khó truy | Quarantine reason |
| Retry poison event vô hạn | Consumer lag cao | Non-retryable classification |
| ACK trước khi persist | Có thể mất event | Commit/ACK policy |
| Nghĩ envelope là exactly-once | Side effect lặp | Idempotent consumer/outbox |
| Lồng envelope nhiều lớp không giới hạn | Size/nesting/complexity | Contract rõ; giới hạn depth |
| Log full payload khi parser fail | PII leak | Redaction/restricted logs |
| Chỉ test object, không test wire JSON | Serializer lệch contract | Round-trip/contract tests |
| Dùng metric label là eventId | Cardinality nổ | Labels bounded by type/reason |

## 27. Bài tập thực hành

**Bài 1 — Thiết kế hợp đồng.** Từ event `OrderCreated` thuần, xác định payload fields, envelope metadata và transport-only metadata khi gửi HTTP→Kafka.

**Bài 2 — Wrap/unwrap.** Implement `OrderEnvelopeCodec`; assert round-trip giữ eventId/tenantId/orderId/amount.

**Bài 3 — JSON serialization.** Dùng Jackson serialize envelope ra JSON và parse ngược; so sánh với fixture JSON được producer cung cấp.

**Bài 4 — Header leakage.** Gắn Authorization, replyChannel và debug header trên Spring Message; xác minh outbound wire không chứa chúng.

**Bài 5 — Event ID mismatch.** Thay eventId trong envelope khác data eventId; expect `EVENT_ID_MISMATCH`.

**Bài 6 — Correlation mismatch.** Đổi correlationId thành tenant-b/ORDER-101; expect reject.

**Bài 7 — Unknown version.** Gửi envelopeVersion `"99"` và payload schemaVersion `"99"`; test cả hai loại lỗi khác nhau.

**Bài 8 — Derived event.** Từ OrderCreated phát ShipmentRequested: cấp event ID mới, causationId là event ID cũ, correlationId vẫn theo order.

**Bài 9 — Redelivery.** Gửi cùng JSON envelope qua hai Spring Message instances khác nhau; kết hợp Idempotent Receiver để chặn side effect trùng.

**Bài 10 — Replay sau migration.** Lưu envelope v1 trong DLQ, upgrade producer v2; kiểm tra consumer mới có thể đọc v1 hoặc quarantine theo migration policy.

**Bài 11 — Kafka key.** Chọn partition key để giữ ordering per-order, không dùng eventId nếu các event cùng order cần về một partition.

**Bài 12 — Gateway reply.** Thiết kế request envelope có request ID, reply destination/correlation contract và timeout; không serialize `replyChannel` object.

**Bài 13 — Chữ ký.** Ký một JSON byte sequence rồi đổi whitespace; giải thích vì sao phải canonicalize/verify/re-sign theo protocol.

**Bài 14 — Authentication.** Client tenant-a khai tenant-b trong envelope; test adapter reject trước business handler.

**Bài 15 — File lớn.** Đổi payload 20 MB thành Claim Check/object storage reference với checksum/authorization/TTL; thiết kế failure recovery.

**Bài 16 — Tracing.** Propagate `traceparent` qua HTTP→Kafka adapter thật; assert trace continuation không làm thay eventId.

**Bài 17 — Observability.** Tạo metrics nhận/validate/forward/reject theo event type/version; không dùng eventId làm label.

**Bài 18 — Batch/aggregation.** Gửi OrderCreated, PaymentCaptured, InventoryReserved envelopes từ ba nguồn; normalize và group theo trusted tenantId/orderId.

### Ma trận test tối thiểu

| Đầu vào | Kết quả kỳ vọng |
|---|---|
| Envelope v1 hợp lệ | Unwrap ra đúng OrderCreated |
| Wrap rồi JSON round-trip | Payload giữ nguyên |
| Same logical event, redelivery | Event ID giữ nguyên |
| Different Spring Message IDs | Không tạo business event ID khác |
| Envelope eventId khác data | Reject |
| Envelope tenant khác data | Reject |
| CorrelationId sai | Reject |
| Unknown envelopeVersion | Unsupported contract error |
| Unknown schemaVersion | Unsupported payload schema |
| Wrong event type/source | Reject/routing riêng |
| Missing orderId | Validation reject |
| Amount không hợp lệ | Reject, không tự sửa |
| Timestamp sai ISO-8601 | Reject |
| Authorization trong headers | Không xuất ra wire |
| Tenant không đúng authenticated identity | Security reject |
| JSON quá lớn/nested | Ingress reject trước parse |
| HTTP→broker adapter | Không mất event identity/trace theo contract |
| Broker redelivery | Idempotent side effect |
| Archived envelope v1 | Có replay/migration policy |
| Registry/backend outage | Bounded retry, không drop im lặng |

### Câu hỏi tự kiểm tra

1. Envelope Wrapper thêm gì so với payload nghiệp vụ?
2. Vì sao Spring `MessageHeaders` không thay được mọi cross-system envelope?
3. Metadata nào nên giữ end-to-end khi chỉ forward?
4. Khi nào cần tạo event ID mới?
5. CausationId khác correlationId ở điểm nào?
6. TraceId có phải business correlation key không?
7. Source/schema/envelope version khác nhau thế nào?
8. Broker offset có thể làm eventId không?
9. HTTP Authorization có nên nằm trong JSON envelope không?
10. Vì sao phải đối chiếu eventId giữa vỏ và data?
11. Vì sao source string không đủ để xác thực publisher?
12. Schema version cũ nhưng data mới gây lỗi gì?
13. Khi nào cần Normalizer sau unwrap?
14. Một envelope chuẩn có bảo đảm exactly-once không?
15. Vì sao JSON reserialize có thể làm chữ ký không hợp lệ?
16. Discard/error channel khác DLQ như thế nào?
17. Gateway replyChannel có thể gửi như một Java object qua broker không?
18. Cần làm gì với unknown envelopeVersion?
19. Vì sao phải giữ adapter v1 sau khi producer chuyển sang v2?
20. Cần test nào để bắt rò rỉ header?
21. Khi nào nên dùng CloudEvents thay custom envelope?
22. Vì sao không nên lồng nhiều envelopes vô hạn?
23. Khi nào dùng Claim Check thay vì nhét file vào envelope?
24. Envelope metadata nào có nguy cơ cardinality cao?
25. Cách bảo toàn correlation cho Aggregator khi các producer dùng transport khác nhau?

## 28. Checklist triển khai Envelope Wrapper đa hệ thống

- [ ] Có contract rõ cho business `data` và integration envelope.
- [ ] Không nhầm Spring headers với wire envelope/transport headers.
- [ ] Event type, source, eventId và versions có schema/owner.
- [ ] Event ID giữ ổn định khi forward/retry cùng logical event.
- [ ] Event mới có ID mới và causation link khi phù hợp.
- [ ] CorrelationId có business semantics được công bố.
- [ ] OccurredAt không bị ghi đè bởi receive/publish time.
- [ ] SchemaVersion mô tả payload hiện tại; envelopeVersion mô tả lớp vỏ.
- [ ] Missing/unknown versions có explicit reject/quarantine policy.
- [ ] Inbound validate eventId/tenant/source/type/version/contentType.
- [ ] Các field trùng trong envelope/data được đối chiếu.
- [ ] Headers cross-boundary dùng allowlist.
- [ ] Không forward Authorization, internal channel objects, secret tokens.
- [ ] Trace context được instrumentation/adapter propagate đúng.
- [ ] Tenant/source được xác thực và authorized tại ingress.
- [ ] Chữ ký được verify trên representation đã ký; re-sign sau transform nếu cần.
- [ ] JSON parser có size/depth/time limits và schema validation.
- [ ] Không tự convert units hoặc bịa defaults nghiệp vụ.
- [ ] Broker publish/ACK có durability policy.
- [ ] Idempotent Receiver dùng stable key và fingerprint đúng.
- [ ] Retry transient errors có backoff/max attempts, deterministic errors không loop.
- [ ] Quarantine/DLQ có reason code, retention và replay plan.
- [ ] Gateway request-reply có response/correlation protocol rõ.
- [ ] Aggregator dùng business identity, không dùng schemaVersion/eventId.
- [ ] Wire JSON/serializer contract tests chạy với producer fixtures.
- [ ] Unit tests wrapper/unwrap, mismatch và unknown version.
- [ ] Integration tests Spring channels và broker/HTTP adapter thật khi cần.
- [ ] Canary/expand-migrate-contract tính đến archived v1 events.
- [ ] Metrics theo type/version/outcome; không dùng raw IDs làm labels.
- [ ] Có giới hạn payload size, backpressure và strategy cho file lớn.
- [ ] Có runbook cho replay, rollback, key rotation và schema migration.

## 29. Tổng kết

**Envelope khi message qua nhiều hệ thống** là cách đưa **business payload** và **integration metadata** vào một hợp đồng có thể hiểu xuyên HTTP, broker và nhiều runtime. Vỏ giúp bên nhận biết sự kiện thuộc loại gì, ai khai báo là nguồn phát, event ID nào phải giữ ổn định, schema/version nào cần decode, thời điểm nghiệp vụ gốc là khi nào và message có liên hệ với workflow nào. Tuy vậy, nó **không thay thế** authentication, schema validation, idempotency, retry/ACK hoặc transaction.

Trong Spring Integration, Envelope Wrapper có thể được triển khai bằng **Transformer wrap/unwrap** trên `Message<?>` và được ghép với Router, Header Enricher, Normalizer, Filter, Gateway, Aggregator và error channel. Khi đi qua nhiều hop, cần phân biệt **logical event ID** với **message/delivery IDs**, **correlation/causation** với **trace**, **payload schema version** với **envelope version** và **metadata end-to-end** với **hop-local headers**.

Một thiết kế tốt dùng **header allowlist, version support matrix, explicit unsupported paths, canonical identity, authenticated source/tenant, bounded parsing và dedup**. Kiểm thử phải bao gồm round trip trên wire representation, Spring integration channels và các tình huống thực tế như redelivery, missing fields, wrong tenant, legacy replay và chữ ký sau reserialization. Khi những ranh giới được định nghĩa rõ, luồng **SPRING_INTEGRATION_PATTERN** trở nên dễ mở rộng giữa các hệ thống mà không làm mất danh tính, ý nghĩa hay khả năng truy vết của message.

### Tài liệu tham khảo

- Enterprise Integration Patterns — Envelope Wrapper: https://www.enterpriseintegrationpatterns.com/patterns/messaging/EnvelopeWrapper.html
- Enterprise Integration Patterns — Message Translator: https://www.enterpriseintegrationpatterns.com/patterns/messaging/MessageTranslator.html
- Enterprise Integration Patterns — Correlation Identifier: https://www.enterpriseintegrationpatterns.com/patterns/messaging/CorrelationIdentifier.html
- Enterprise Integration Patterns — Idempotent Receiver: https://www.enterpriseintegrationpatterns.com/patterns/messaging/IdempotentReceiver.html
- CloudEvents Specification 1.0: https://github.com/cloudevents/spec/blob/v1.0.2/cloudevents/spec.md
- W3C Trace Context: https://www.w3.org/TR/trace-context/
- Spring Integration Reference — Message: https://docs.spring.io/spring-integration/reference/message.html
- Spring Integration Reference — Message Transformation: https://docs.spring.io/spring-integration/reference/transformer.html
- Spring Integration Reference — Message Routing: https://docs.spring.io/spring-integration/reference/router.html
- Spring Integration Reference — Java DSL: https://docs.spring.io/spring-integration/reference/dsl.html
- Spring Integration Reference — HTTP Support: https://docs.spring.io/spring-integration/reference/http.html
- Spring Integration Reference — Error Handling: https://docs.spring.io/spring-integration/reference/error-handling.html
- Spring Integration Reference — Aggregator: https://docs.spring.io/spring-integration/reference/aggregator.html
- Spring Integration Reference — Claim Check: https://docs.spring.io/spring-integration/reference/claim-check.html
- Jackson Databind README: https://github.com/FasterXML/jackson-databind
- JUnit 5 User Guide: https://junit.org/junit5/docs/current/user-guide/




