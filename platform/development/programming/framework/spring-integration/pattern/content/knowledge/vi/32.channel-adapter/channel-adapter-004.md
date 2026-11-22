# Adapter chuyển đổi payload và header

## 1. Vấn đề: cùng một sự kiện nhưng mỗi hệ thống biểu diễn khác nhau

Trong module **SPRING_INTEGRATION_PATTERN**, chúng ta học cách triển khai **Enterprise Integration Patterns (EIP)** với **Spring Integration** để xây dựng các luồng thông điệp ít phụ thuộc, dễ mở rộng và có thể quan sát. Khi Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation phối hợp, một vấn đề thường xuất hiện ở ngay ranh giới hệ thống: **định dạng thông điệp của thế giới bên ngoài không giống Spring Message và không giống đối tượng nghiệp vụ của ứng dụng**.

Ví dụ, đối tác gửi một sự kiện đặt hàng qua HTTP hoặc JMS:

~~~json
{
  "schemaVersion": 1,
  "eventId": "evt-order-901",
  "orderId": "ORD-901",
  "sku": "SKU-RED",
  "quantity": 2,
  "workflowEpoch": 3
}
~~~

Đối tác có thể kèm:

~~~text
HTTP header: X-Event-Id: evt-order-901
HTTP header: X-Tenant-Id: tenant-admin
HTTP header: Content-Type: application/json

JMS property: event_id = evt-order-901
JMS property: partner_schema_version = 1
JMS header: JMSMessageID = ID:...
~~~

Trong Spring Integration, handler nội bộ có thể cần một **Message<OrderCommand>** với các headers thống nhất:

~~~text
Message.payload:
  OrderCommand(orderId=ORD-901, sku=SKU-RED, quantity=2, epoch=3)

Message.headers:
  trustedTenantId = tenant-a
  businessEventId = evt-order-901
  producerId = partner-a
  businessCorrelationKey = order:tenant-a:ORD-901:epoch-3
~~~

Một **Channel Adapter** là cầu nối đưa dữ liệu **vào** hoặc **ra khỏi** hệ thống messaging. Phần khó không chỉ là đọc từ HTTP/JMS/file hay ghi ra broker; nó còn là **chuyển đổi payload, map headers, xác minh ngữ cảnh, quản lý lỗi và bảo toàn identity qua transport boundary**.

### Mục tiêu bài học

Sau bài này, bạn có thể:

1. Phân biệt **Channel Adapter**, **Messaging Gateway**, **Message Translator/Transformer**, **MessageConverter** và **HeaderMapper**.
2. Vẽ đường đi của payload/headers qua inbound và outbound adapters.
3. Thiết kế hợp đồng **wire DTO → typed domain payload → wire DTO**, có version và validation.
4. Chuyển headers từ transport thành Spring MessageHeaders theo **allowlist**, không biến client claims thành dữ liệu đáng tin.
5. Hiểu sự khác biệt giữa business identity và headers kỹ thuật của HTTP/JMS/AMQP/Spring Integration.
6. Tạo ví dụ Java 17 + Spring Integration với inbound/outbound boundary minh họa và kiểm thử thực tế qua Spring channels.
7. Xử lý sai schema, header thiếu/sai kiểu, duplicate, reply/error/timeout và retry an toàn.
8. Biết cách kiểm thử và quan sát một adapter khi nó làm mất payload hoặc correlation metadata.

## 2. Channel Adapter đóng vai trò nào trong Enterprise Integration Patterns?

**Channel Adapter** kết nối một ứng dụng, nguồn dữ liệu hoặc giao thức với **Message Channel**. Một inbound adapter lấy dữ liệu từ bên ngoài rồi **phát Message vào channel**; một outbound adapter **nhận Message từ channel** rồi gửi nội dung ra hệ thống ngoài.

~~~mermaid
flowchart LR
    X["External system / file / broker"] --> I["Inbound Channel Adapter"]
    I --> C["Spring MessageChannel"]
    C --> R["Router / Transformer / Service Activator"]
    R --> O["Outbound Channel Adapter"]
    O --> Y["External system / file / broker"]
~~~

| Thành phần | Trách nhiệm chính | Không tự bảo đảm |
| --- | --- | --- |
| **Inbound Channel Adapter** | Nhận/poll dữ liệu ngoài, tạo Spring Message | Payload đã đúng nghiệp vụ, tenant được phép |
| **Outbound Channel Adapter** | Nhận Spring Message và gửi ra hệ thống ngoài | Remote đã hoàn tất nghiệp vụ hoặc phản hồi |
| **MessageConverter** | Đổi bytes/text/object theo wire format | Authorization hoặc correlation đúng |
| **HeaderMapper** | Ánh xạ selected transport properties và Spring headers | Header đến từ nguồn đáng tin |
| **Transformer/Translator** | Đổi biểu diễn nội bộ hoặc chuẩn hóa payload/header | Transaction xuyên nhiều services |
| **Messaging Gateway** | Cung cấp lời gọi request/reply có return value | Exactly-once remote effects |
| **Filter/Router** | Cho qua/bỏ hoặc chọn nhánh dựa trên Message | Dữ liệu đầu vào tự đáng tin |

Một outbound Channel Adapter thường mang nghĩa **gửi một chiều**; nếu caller cần response gắn với request, hãy xem **outbound Gateway/request-reply adapter**, không coi một lần send thành công là business completion.

### 2.1. Inbound và outbound là hai chiều ngược nhau

~~~text
Inbound:
  transport bytes + native metadata
      -> deserialize payload
      -> validate source and schema
      -> map/construct Spring headers
      -> Spring Message<T>

Outbound:
  Spring Message<T>
      -> validate outgoing contract
      -> serialize permitted wire payload
      -> map selected Spring headers to native metadata
      -> send bytes/properties
~~~

Hai chiều có thể **không đối xứng**: một inbound adapter nhận nhiều native headers nhưng chỉ chọn hai header vào internal Message; outbound adapter có thể phát một bộ headers khác theo hợp đồng đối tác. Không mặc định một header nhận được sẽ được gửi ngược trở lại.

### 2.2. Adapter khác Transformer như thế nào?

Một Transformer có thể đổi **OrderWireV1 → OrderCommand** ngay trong Spring Integration, nhưng adapter còn xử lý **giao thức và vòng đời nhận/gửi**: connection, polling, ack, converter, native properties, error handling, backpressure. Trong một flow thực tế, bạn thường dùng **adapter + transformer** chứ không đặt mọi logic trong một endpoint lớn.

### 2.3. Adapter khác Gateway ở đâu?

~~~text
Adapter:
  external event -> channel
  channel -> external destination

Gateway:
  request -> channel/transport -> correlated reply
  caller chờ hoặc nhận một result
~~~

Đối với HTTP inbound request cần trả HTTP response đồng bộ, **inbound HTTP Gateway** có thể phù hợp hơn một inbound Channel Adapter một chiều. Đối với đọc file, event stream hoặc ghi audit vào broker, adapters là lựa chọn tự nhiên.

## 3. Phân biệt ba tầng định dạng

Nhiều lỗi production xảy ra vì nhóm phát triển dùng chung từ “header” cho ba loại thông tin:

~~~mermaid
flowchart TD
    W["Wire message: bytes + native headers"] --> A["Adapter / Converter / HeaderMapper"]
    A --> M["Spring Message: typed payload + MessageHeaders"]
    M --> D["Domain service: DTO + trusted business context"]
~~~

| Tầng | Payload | Header/context |
| --- | --- | --- |
| **Wire** | JSON/XML/text/byte array/file | HTTP headers, JMS properties, AMQP properties, file metadata |
| **Spring Messaging** | Java object hoặc bytes trong Message | Immutable MessageHeaders, id/timestamp, replyChannel/errorChannel, custom headers |
| **Domain** | OrderCommand, OrderAccepted, Money... | VerifiedTenant, businessEventId, workflow identity trong typed context |

**Spring MessageHeaders không đồng nhất với HTTP headers.** HTTP `X-Event-Id` chỉ trở thành Spring `businessEventId` nếu adapter/mapper tạo mapping đó. Sau khi đi qua broker khác, nó có thể bị đổi tên, sai kiểu hoặc mất nếu không có wire contract.

### 3.1. Một ví dụ sai tên

~~~text
Wire HTTP:
  X-Event-Id = evt-order-901

Spring Message:
  x_event_id = evt-order-901

Downstream:
  @Header("businessEventId") String eventId
~~~

Handler có thể thiếu header bắt buộc vì ba tên **không tương đương**. Cần thống nhất mapping ở boundary, không để mỗi business handler đoán các tên khác nhau của từng đối tác.

### 3.2. Payload conversion và header conversion là hai bài toán

- **Payload conversion:** JSON bytes thành OrderWireV1 rồi thành OrderCommand; chuyển encoding, schema version, enum, các field nghiệp vụ.
- **Header conversion:** native property `event_id` hoặc HTTP `X-Event-Id` thành một Spring header ổn định; đối chiếu với eventId trong payload khi cần.
- **Context binding:** gắn `trustedTenantId` từ authentication/authorization, không lấy giá trị tự khai từ HTTP.

Không gộp ba bước thành một `copyHeaders(raw)` rồi coi là chuyển đổi đã hoàn tất.

## 4. Inbound adapter: luồng xử lý đáng tin cậy

Một inbound adapter cần thực hiện công việc theo thứ tự:

1. Nhận từ nguồn được cấu hình (poll file, đọc broker, nhận HTTP callback, ...).
2. Giới hạn kích thước thông điệp, xác minh encoding/content type và schema.
3. Authenticate producer qua credential, mTLS, chữ ký hoặc broker ACL.
4. Deserialize payload và validate field/enum/units.
5. Authorize producer đối với tenant/entity/workflow được nêu.
6. Kiểm tra eventId và correlation với hợp đồng đã công bố.
7. Tạo **trusted Spring Message** với headers được allowlist.
8. Gửi vào internal channel để Router, Filter, Transformer và Service Activator xử lý.
9. Ack/commit theo semantics của inbound adapter và transaction/recovery policy.

Không phải mọi transport thực hiện từng bước trong cùng một lớp; điều quan trọng là **không để untrusted metadata trở thành trusted application header trước khi các bước xác minh được thực hiện**.

### 4.1. Tránh nhầm ACK với kết quả nghiệp vụ

Với broker, ACK có thể nghĩa là consumer đã nhận/xử lý đến một ranh giới cụ thể. Với HTTP, response 200/202 có thể là phản hồi của adapter. Không suy ra downstream đã hoàn thành ghi sổ, gọi provider hay phát event nếu contract chưa quy định.

### 4.2. Phân biệt receive timestamp và event time

HTTP/JMS broker timestamp, MessageHeaders.TIMESTAMP và field `occurredAt` của business event có thể khác nhau. Khi đo trễ, cần giữ rõ timestamp nào do producer tạo, timestamp nào do ingress xác minh/ghi nhận, và timestamp nào do Spring Message khởi tạo.

### 4.3. Inbound có thể là poller

Ví dụ đọc file hoặc queue, `poller` quyết định tần suất lấy dữ liệu, maxMessagesPerPoll và error handling. Khi consumer không kịp xử lý, cần bounded capacity/backpressure; không chỉ tăng polling interval để che một queue backlog không được theo dõi.

## 5. Outbound adapter: chỉ xuất những gì wire contract cho phép

Chiều outbound không phải “serialize nguyên Message object”. Một outbound adapter cần:

1. Xác định target transport/destination từ cấu hình tin cậy hoặc business routing allowlist.
2. Chọn đúng schema version cho receiver.
3. Chuyển typed payload thành wire DTO và bytes.
4. Tạo native headers/properties từ **allowlisted metadata**.
5. Loại live Spring runtime headers như `replyChannel`, `errorChannel` và internal channel references.
6. Gửi và ghi nhận kết quả transport send theo semantics của adapter.
7. Xử lý retry, DLQ/outbox/recovery nếu send thất bại hoặc outcome không chắc chắn.

### 5.1. Nguy cơ serialize nhầm control headers

Một Spring Message có thể chứa `replyChannel` là một **MessageChannel object** do Gateway tạo. Header đó không phải JSON/broker property portable và có thể làm lộ topology. Tương tự, errorChannel/routingSlip không phải các giá trị để external producer tự quyết định.

### 5.2. Vì sao không echo toàn bộ headers?

Một inbound request có thể có Authorization, cookie, broker delivery tag, partner request ID, source IP và runtime metadata. Outbound reply/event chỉ nên gửi **những trường được contract cho phép**. Việc giữ internal message context phục vụ tracing không đồng nghĩa gửi toàn bộ context ra đối tác.

### 5.3. Một chiều không có reply business

Khi outbound adapter gửi một event sang broker, sender có thể nhận broker confirmation nhưng không nhận `OrderAccepted` từ consumer nghiệp vụ. Nếu cần business reply, thiết kế một **outbound Gateway** hoặc một completion event/status API với correlation và timeout rõ ràng.

## 6. Contract mẫu cho chuyển đổi một sự kiện đặt hàng

Chúng ta sẽ xây một **in-memory adapter harness** để có thể kiểm thử mapping mà không cần triển khai HTTP server/broker. Harness mô phỏng hai ranh giới:

- **Inbound:** một khung dữ liệu đã nhận từ transport gồm JSON, native headers và verified producer context.
- **Outbound:** một sự kiện đã xử lý được serialize thành JSON cùng một tập native headers có allowlist.

Đây là **harness mô phỏng trách nhiệm adapter**, không phải code kết nối HTTP/JMS/AMQP production. Khi tích hợp thật, phần receive/send được thay bằng adapter tương ứng, còn business DTO, mapper, validation và tests có thể tái sử dụng.

### 6.1. Wire request v1

~~~json
{
  "schemaVersion": 1,
  "eventId": "evt-order-901",
  "orderId": "ORD-901",
  "sku": "SKU-RED",
  "quantity": 2,
  "workflowEpoch": 3
}
~~~

Hai native headers minh họa:

~~~text
x-event-id: evt-order-901
content-type: application/json
~~~

Chúng chỉ là **metadata do nguồn cung cấp**. Nếu raw eventId vừa có trong body vừa có trong header, mapper cần kiểm tra hai giá trị nhất quán, sau đó bind identity này với nguồn/tenant được xác thực và chính sách chống replay.

### 6.2. Internal message contract

~~~text
Message.payload = OrderCommand(
    orderId="ORD-901",
    sku="SKU-RED",
    quantity=2,
    workflowEpoch=3
)

Message.headers:
    trustedTenantId="tenant-a"
    producerId="partner-a"
    businessEventId="evt-order-901"
    businessCorrelationKey="order:tenant-a:ORD-901:epoch-3"
~~~

**trustedTenantId** phải đến từ authenticated producer + authorization registry. Không dùng client-provided x-tenant-id để dựng trustedTenantId.

### 6.3. Wire output v1

~~~json
{
  "schemaVersion": 1,
  "eventId": "evt-order-901",
  "orderId": "ORD-901",
  "outcome": "ACCEPTED"
}
~~~

Headers khi gửi ra ngoài:

~~~text
content-type: application/json
x-event-id: evt-order-901
x-schema-version: 1
~~~

**ACCEPTED** trong harness có nghĩa là ghi nhận bởi processor in-memory, **không phải bảo đảm một order đã commit bền hoặc đã giao hàng**. Trong production phải định nghĩa chính xác tại thời điểm ACK/ACCEPTED được phát thì dữ liệu đã được persist đến đâu.

## 7. Typed wire DTO và domain payload

Sử dụng Java 17 record với validation giúp phát hiện schema lỗi sớm.

~~~java
import java.util.Objects;

record OrderWireV1(
        int schemaVersion,
        String eventId,
        String orderId,
        String sku,
        int quantity,
        int workflowEpoch) {

    OrderWireV1 {
        if (schemaVersion != 1) {
            throw new IllegalArgumentException(
                    "UNSUPPORTED_SCHEMA_VERSION");
        }
        if (eventId == null
                || !eventId.matches("[A-Za-z0-9_-]{1,96}")) {
            throw new IllegalArgumentException("INVALID_EVENT_ID");
        }
        if (orderId == null
                || !orderId.matches("[A-Za-z0-9_-]{1,64}")) {
            throw new IllegalArgumentException("INVALID_ORDER_ID");
        }
        if (sku == null
                || !sku.matches("[A-Za-z0-9_-]{1,64}")) {
            throw new IllegalArgumentException("INVALID_SKU");
        }
        if (quantity < 1 || quantity > 1000) {
            throw new IllegalArgumentException("INVALID_QUANTITY");
        }
        if (workflowEpoch < 1) {
            throw new IllegalArgumentException("INVALID_WORKFLOW_EPOCH");
        }
    }
}

record OrderCommand(
        String orderId,
        String sku,
        int quantity,
        int workflowEpoch) {

    OrderCommand {
        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(sku, "sku");
        if (quantity < 1 || workflowEpoch < 1) {
            throw new IllegalArgumentException("INVALID_ORDER_COMMAND");
        }
    }
}

record OrderAccepted(
        String tenantId,
        String producerId,
        String eventId,
        String orderId,
        String outcome) {
}

record OrderAckWireV1(
        int schemaVersion,
        String eventId,
        String orderId,
        String outcome) {
}
~~~

**OrderWireV1** là schema ở ranh giới transport. **OrderCommand** là payload nội bộ. **OrderAccepted** đại diện kết quả của processor mô phỏng. **OrderAckWireV1** là DTO output được phép gửi ra ngoài; nó cố ý **không chứa tenantId, principal hoặc framework replyChannel**.

### 7.1. Tại sao không serialize OrderAccepted trực tiếp?

Một domain object có thể thay đổi theo yêu cầu nội bộ, ví dụ thêm internalRiskScore, auditOwner hoặc tenant authorization data. Nếu outbound adapter serialize toàn bộ record đó, trường nội bộ có thể rò ra external contract. Wire DTO giúp **chọn có chủ đích** trường nào receiver được phép biết.

### 7.2. Đừng mặc định ObjectMapper tự là security boundary

ObjectMapper chuyển JSON thành Java object; nó **không xác thực producer hoặc tenant ownership**. Khi dữ liệu chưa đáng tin, cần giới hạn kích thước, độ sâu, unknown fields, allowed enum values và không bật arbitrary polymorphic deserialization dựa vào class name do client cung cấp.

### 7.3. Wire schema có thể không cùng type với domain schema

Một đối tác có thể gửi timestamp dưới dạng ISO-8601 String, trong khi domain dùng Instant. Một price có thể ở minor units (long) hoặc decimal string với Currency. Converter phải xác định **đơn vị, timezone, precision và null semantics** chứ không chỉ rename fields.

## 8. Verified producer context và inbound frame

Một adapter cần phân biệt **metadata wire tự khai** với **identity được tạo từ authentication**.

~~~java
import java.util.Map;
import java.util.Objects;

record VerifiedProducer(
        String tenantId,
        String producerId) {

    VerifiedProducer {
        if (tenantId == null
                || !tenantId.matches("[a-z0-9_-]{1,48}")) {
            throw new IllegalArgumentException("INVALID_TENANT_ID");
        }
        if (producerId == null
                || !producerId.matches("[a-z0-9_-]{1,48}")) {
            throw new IllegalArgumentException("INVALID_PRODUCER_ID");
        }
    }
}

record TransportFrame(
        String jsonBody,
        Map<String, String> nativeHeaders,
        VerifiedProducer producer) {

    TransportFrame {
        Objects.requireNonNull(jsonBody, "jsonBody");
        nativeHeaders = Map.copyOf(nativeHeaders);
        Objects.requireNonNull(producer, "producer");
    }
}

interface OrderSourceAuthorization {
    void assertMayPublish(
            VerifiedProducer producer,
            OrderWireV1 event);
}
~~~

**VerifiedProducer chỉ là một Java record mô tả kết quả xác thực**, không phải một authentication mechanism. Trong code production, transport adapter/ingress phải thực sự kiểm tra mTLS/JWT/broker ACL/chữ ký rồi ràng buộc tenant và producerId với một registry có quyền.

### 8.1. Không cho client tự dựng VerifiedProducer

Sai:

~~~java
// Không dùng làm production ingress.
VerifiedProducer untrusted = new VerifiedProducer(
        httpRequest.getHeader("X-Tenant-Id"),
        httpRequest.getHeader("X-Producer-Id"));
~~~

Đúng về thứ tự trách nhiệm:

~~~text
HTTP/JMS/AMQP credentials
    -> authenticate producer
    -> authorize producer for tenant + order
    -> VerifiedProducer
    -> TransportFrame
    -> inbound mapper
~~~

### 8.2. Frame chứa raw native headers nhưng internal Message thì không

TransportFrame trong harness mang Map nativeHeaders để kiểm thử. Nhưng **chỉ mapper được đọc Map này**. Các internal business handlers không được nhận toàn bộ nativeHeaders hay biết tên x-tenant-id, JMSCorrelationID, broker delivery tag và HTTP cookie.

### 8.3. Quy tắc idempotency trong ví dụ

Một eventId có thể chỉ duy nhất trong namespace của producer. Vì vậy dedup scope của harness sẽ là **tenantId + producerId + eventId**. Cùng key nhưng payload khác là conflict. Trong production, cần contract cụ thể để xác định eventId là globally unique hay chỉ source-scoped.

## 9. Inbound mapper: JSON + headers thành trusted Spring Message

Đây là nơi tách ba bước **decode**, **verify**, và **build internal Message**.

~~~java
import java.nio.charset.StandardCharsets;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

final class OrderInboundMapper {
    private static final int MAX_WIRE_BYTES = 64 * 1024;

    private final ObjectMapper objectMapper;
    private final OrderSourceAuthorization authorization;

    OrderInboundMapper(
            ObjectMapper objectMapper,
            OrderSourceAuthorization authorization) {
        this.objectMapper = objectMapper;
        this.authorization = authorization;
    }

    Message<OrderCommand> toTrustedMessage(TransportFrame frame) {
        int bytes = frame.jsonBody()
                .getBytes(StandardCharsets.UTF_8).length;
        if (bytes == 0 || bytes > MAX_WIRE_BYTES) {
            throw new IllegalArgumentException(
                    "WIRE_PAYLOAD_SIZE_INVALID");
        }

        OrderWireV1 wire;
        try {
            wire = objectMapper.readValue(
                    frame.jsonBody(), OrderWireV1.class);
        } catch (JsonProcessingException ex) {
            throw new IllegalArgumentException(
                    "INVALID_ORDER_WIRE_JSON", ex);
        }

        String declaredEventId = frame.nativeHeaders()
                .get("x-event-id");
        if (declaredEventId != null
                && !declaredEventId.equals(wire.eventId())) {
            throw new SecurityException(
                    "EVENT_ID_HEADER_PAYLOAD_MISMATCH");
        }

        // Bắt buộc bind producer/tenant trước business processing.
        authorization.assertMayPublish(frame.producer(), wire);

        OrderCommand command = new OrderCommand(
                wire.orderId(),
                wire.sku(),
                wire.quantity(),
                wire.workflowEpoch());

        String correlation = "order:"
                + frame.producer().tenantId() + ":"
                + wire.orderId() + ":epoch-"
                + wire.workflowEpoch();

        return MessageBuilder.withPayload(command)
                .setHeader("trustedTenantId",
                        frame.producer().tenantId())
                .setHeader("producerId",
                        frame.producer().producerId())
                .setHeader("businessEventId", wire.eventId())
                .setHeader("businessCorrelationKey",
                        correlation)
                .build();
    }
}
~~~

**Điểm quyết định:** không có `copyHeaders(frame.nativeHeaders())`. Một transport sender có thể cố đặt `replyChannel` hoặc `trustedTenantId` trong Map. Internal Spring Message chỉ được tạo bằng headers mà ứng dụng sở hữu.

### 9.1. Event ID trong body và header

Ví dụ chấp nhận vắng `x-event-id` nếu `eventId` đã có trong body, nhưng khi header hiện diện thì bắt buộc khớp. Một hợp đồng khác có thể yêu cầu `x-event-id` luôn có; khi đó thay validation tương ứng. Không lựa chọn tùy tiện một trong hai giá trị khi xảy ra mismatch.

### 9.2. Vì sao không dùng request IP làm tenant?

Source IP hoặc broker connection name có thể hữu ích cho audit, nhưng không đủ để định danh người có quyền với order. Producer phải được chứng thực và authorize theo registry/business policy.

### 9.3. Khi JSON không hợp lệ

Jackson có thể ném lỗi parse hoặc mapping; record constructor có thể ném IllegalArgumentException từ schema validation. Adapter phải phân loại lỗi input (invalid/unprocessable) so với lỗi hệ thống (DB/network) để quyết định reject/quarantine hay retry.

### 9.4. Khi header x-event-id bị đổi trên đường truyền

Nếu một HTTP reverse proxy, broker bridge hoặc header mapper đổi tên thành X-Event-ID hay event_id, Map lookup chính xác `"x-event-id"` có thể không thấy. Tại **mỗi adapter**, normalize case/name theo giao thức và công bố mapping; không ngầm giả định cùng tên hoạt động qua mọi transport.

## 10. Xử lý nội bộ: Service Activator nhận domain payload và trusted headers

Sau inbound mapping, business handler không phải biết transport là HTTP, JMS, AMQP hay file. Nó nhận typed OrderCommand và identity đã được xác minh.

### 10.1. Processor demo có idempotency trong memory

~~~java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

final class DemoOrderProcessor {
    private record Recorded(
            OrderCommand original,
            String businessCorrelationKey,
            OrderAccepted accepted) {
    }

    private final ConcurrentMap<String, Recorded> ledger =
            new ConcurrentHashMap<>();

    OrderAccepted process(
            OrderCommand command,
            String tenantId,
            String producerId,
            String eventId,
            String businessKey) {

        String expected = "order:" + tenantId
                + ":" + command.orderId()
                + ":epoch-" + command.workflowEpoch();
        if (!expected.equals(businessKey)) {
            throw new SecurityException(
                    "BUSINESS_CORRELATION_MISMATCH");
        }

        String dedupKey =
                tenantId + ":" + producerId + ":" + eventId;

        Recorded stored = ledger.compute(dedupKey, (key, existing) -> {
            if (existing != null) {
                if (!existing.original().equals(command)
                        || !existing.businessCorrelationKey()
                                .equals(businessKey)) {
                    throw new IllegalStateException(
                            "EVENT_ID_CONFLICT");
                }
                return existing;
            }

            return new Recorded(
                    command,
                    businessKey,
                    new OrderAccepted(
                            tenantId,
                            producerId,
                            eventId,
                            command.orderId(),
                            "ACCEPTED"));
        });
        return stored.accepted();
    }

    int uniqueEventCount() {
        return ledger.size();
    }
}
~~~

Trong ví dụ, ConcurrentHashMap đảm bảo cập nhật một key tuần tự trong cùng JVM. **Đây không phải ledger production**: không bền qua restart, không phối hợp nhiều instances và không chứng minh external side effect exactly once. Nếu handler ghi database, gọi carrier hoặc charge payment, cần transaction/idempotency key/recovery riêng.

### 10.2. Service Activator nhận method arguments

~~~java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;

final class OrderProcessingActivator {
    private final DemoOrderProcessor processor;

    OrderProcessingActivator(DemoOrderProcessor processor) {
        this.processor = processor;
    }

    @ServiceActivator(
            inputChannel = "trustedCommands",
            outputChannel = "orderResults")
    public OrderAccepted accept(
            @Payload OrderCommand command,
            @Header("trustedTenantId") String tenantId,
            @Header("producerId") String producerId,
            @Header("businessEventId") String eventId,
            @Header("businessCorrelationKey") String businessKey) {

        return processor.process(
                command, tenantId, producerId, eventId, businessKey);
    }
}
~~~

Đây là điểm gặp nhau của **Channel Adapter** và **Service Activator**: inbound adapter làm sạch, chuẩn hóa payload/headers; handler xử lý nghiệp vụ qua typed arguments. Không để business method tự đọc HTTP `X-Tenant-Id` hoặc broker delivery tags.

### 10.3. Vì sao processor kiểm tra lại business key?

Một Transformer hoặc custom handler ở giữa có thể vô tình sửa businessCorrelationKey. Một handler có side effect nên kiểm tra các bất biến quan trọng trước khi commit, đồng thời tin tenantId chỉ sau khi ingress đã authorize. Kiểm tra hai chuỗi khớp nhau **không thay thế** authentication của producer.

## 11. Outbound mapper: domain result thành wire payload và selected headers

Với outbound, chúng ta muốn **giữ business event ID** cho đối tác nhưng không xuất internal tenant context, implementation details hoặc MessageChannel object.

### 11.1. OutboundPacket chứa hợp đồng transport

~~~java
import java.util.Map;
import java.util.Objects;

record OutboundPacket(
        String jsonBody,
        Map<String, String> nativeHeaders) {

    OutboundPacket {
        Objects.requireNonNull(jsonBody, "jsonBody");
        nativeHeaders = Map.copyOf(nativeHeaders);
    }
}
~~~

Map.copyOf đảm bảo không có thay đổi tùy ý lên tập native headers sau khi packet được tạo. Nếu payload là byte[], cần defensive copy ở cả constructor và accessor; Java record chứa byte[] không tự immutable sâu.

### 11.2. Encoder tạo wire ACK v1

~~~java
import java.util.Map;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

final class OrderOutboundMapper {
    private final ObjectMapper objectMapper;

    OrderOutboundMapper(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    Message<OutboundPacket> toWire(Message<OrderAccepted> input) {
        OrderAccepted accepted = input.getPayload();

        // Nếu handler đã nhận headers, chúng phải còn nhất quán
        // ở hop này. Nếu thiếu, fail để phát hiện regression.
        Object eventHeader =
                input.getHeaders().get("businessEventId");
        Object tenantHeader =
                input.getHeaders().get("trustedTenantId");
        if (!accepted.eventId().equals(eventHeader)
                || !accepted.tenantId().equals(tenantHeader)) {
            throw new SecurityException(
                    "OUTBOUND_METADATA_MISMATCH");
        }

        OrderAckWireV1 wire = new OrderAckWireV1(
                1,
                accepted.eventId(),
                accepted.orderId(),
                accepted.outcome());

        String json;
        try {
            json = objectMapper.writeValueAsString(wire);
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException(
                    "ACK_SERIALIZATION_FAILED", ex);
        }

        OutboundPacket packet = new OutboundPacket(
                json,
                Map.of(
                        "content-type", "application/json",
                        "x-event-id", accepted.eventId(),
                        "x-schema-version", "1"));

        // Tạo một Message mới cho transport output.
        // Native headers được đóng trong packet allowlist.
        return MessageBuilder.withPayload(packet).build();
    }
}
~~~

**Chỗ cần kiểm thử:** các header của Message<OrderAccepted> phải được giữ xuyên Service Activator. Khi handler trả payload thuần, Spring Integration thường hỗ trợ propagation headers; nếu handler trả Message mới hoặc có HeaderFilter, behavior có thể khác. Integration test sẽ xác minh thay vì dựa vào giả định.

### 11.3. Tại sao không dùng copyHeaders(input.getHeaders())?

~~~java
// Phản ví dụ nếu sẽ serialize toàn bộ Message ra transport.
return MessageBuilder.withPayload(packet)
        .copyHeaders(input.getHeaders())
        .build();
~~~

Các header input có thể chứa technical correlationId/sequenceNumber, replyChannel/errorChannel, trace context, tenantId và security-sensitive data. Nếu outbound sink chuyển tiếp toàn bộ, có nguy cơ leak hoặc điều khiển đường gửi. OutboundPacket chỉ chứa **native headers công bố trong contract v1**.

### 11.4. Đừng tin internal Message chỉ vì nó ở trong JVM

Nếu một component bên trong nhận trực tiếp untrusted Spring Message rồi gắn vào `trustedCommands`, việc có header `trustedTenantId` chưa chắc đáng tin. Ownership của channel, producer, interceptor và ingress phải được giới hạn. Ngay cả khi outbound mapper kiểm tra metadata nhất quán, nó chưa thể thay authorization.

## 12. Wiring Spring Integration: adapter harness qua các channels

Để kiểm thử đường đi, chúng ta tạo bốn DirectChannels và các annotated endpoints:

~~~mermaid
flowchart LR
    A["TransportFrame input"] --> R["transportFrames"]
    R --> I["@Transformer: inbound mapper"]
    I --> C["trustedCommands"]
    C --> S["@ServiceActivator: process"]
    S --> O["orderResults"]
    O --> E["@Transformer: outbound mapper"]
    E --> P["transportPackets"]
    P --> K["@ServiceActivator: collecting sink"]
~~~

### 12.1. Inbound Transformer

~~~java
import org.springframework.integration.annotation.Transformer;
import org.springframework.messaging.Message;

final class OrderInboundTransformer {
    private final OrderInboundMapper mapper;

    OrderInboundTransformer(OrderInboundMapper mapper) {
        this.mapper = mapper;
    }

    @Transformer(
            inputChannel = "transportFrames",
            outputChannel = "trustedCommands")
    public Message<OrderCommand> normalize(TransportFrame frame) {
        return mapper.toTrustedMessage(frame);
    }
}
~~~

Trong harness, **transportFrames** được cấp Message từ bộ test đóng vai trò inbound adapter. Trong production, adapter HTTP/JMS/AMQP/file thực tế sẽ nhận từ nguồn bên ngoài rồi gọi/đưa dữ liệu vào phần mapping tương đương. Không coi việc dùng @Transformer ở đây là đã tạo một network adapter.

### 12.2. Outbound Transformer

~~~java
import org.springframework.integration.annotation.Transformer;
import org.springframework.messaging.Message;

final class OrderOutboundTransformer {
    private final OrderOutboundMapper mapper;

    OrderOutboundTransformer(OrderOutboundMapper mapper) {
        this.mapper = mapper;
    }

    @Transformer(
            inputChannel = "orderResults",
            outputChannel = "transportPackets")
    public Message<OutboundPacket> encode(
            Message<OrderAccepted> resultMessage) {
        return mapper.toWire(resultMessage);
    }
}
~~~

### 12.3. Outbound sink mô phỏng Channel Adapter

~~~java
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import org.springframework.integration.annotation.ServiceActivator;

final class CollectingOutboundAdapter {
    private final CopyOnWriteArrayList<OutboundPacket> sent =
            new CopyOnWriteArrayList<>();

    @ServiceActivator(inputChannel = "transportPackets")
    public void send(OutboundPacket packet) {
        sent.add(packet);
    }

    List<OutboundPacket> packets() {
        return List.copyOf(sent);
    }

    void clear() {
        sent.clear();
    }
}
~~~

Đây là **test sink in-memory**, không phải JMS/AMQP sender. Trong triển khai thật, adapter outbound sẽ serialize gửi packet với đúng content type/native headers; cần xử lý send failure/confirm/outbox tương ứng.

### 12.4. Configuration

~~~java
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
class OrderAdapterHarnessConfig {

    @Bean
    MessageChannel transportFrames() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel trustedCommands() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel orderResults() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel transportPackets() {
        return new DirectChannel();
    }

    @Bean
    ObjectMapper orderObjectMapper() {
        return new ObjectMapper().configure(
                DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, true);
    }

    @Bean
    OrderSourceAuthorization demoOrderAuthorization() {
        // Chỉ để minh họa/test! Đây KHÔNG PHẢI xác thực thật.
        return (producer, event) -> {
            if (!"partner-a".equals(producer.producerId())) {
                throw new SecurityException("PRODUCER_NOT_ALLOWED");
            }
        };
    }

    @Bean
    OrderInboundMapper orderInboundMapper(
            ObjectMapper mapper,
            OrderSourceAuthorization authorization) {
        return new OrderInboundMapper(mapper, authorization);
    }

    @Bean
    OrderOutboundMapper orderOutboundMapper(ObjectMapper mapper) {
        return new OrderOutboundMapper(mapper);
    }

    @Bean
    DemoOrderProcessor demoOrderProcessor() {
        return new DemoOrderProcessor();
    }

    @Bean
    OrderInboundTransformer orderInboundTransformer(
            OrderInboundMapper mapper) {
        return new OrderInboundTransformer(mapper);
    }

    @Bean
    OrderProcessingActivator orderProcessingActivator(
            DemoOrderProcessor processor) {
        return new OrderProcessingActivator(processor);
    }

    @Bean
    OrderOutboundTransformer orderOutboundTransformer(
            OrderOutboundMapper mapper) {
        return new OrderOutboundTransformer(mapper);
    }

    @Bean
    CollectingOutboundAdapter collectingOutboundAdapter() {
        return new CollectingOutboundAdapter();
    }
}
~~~

Trong code sản xuất, các bean adapter thực sẽ thay hai đầu test harness; không dùng demoOrderAuthorization làm security policy. Jackson 2 (như snippets) phù hợp nhiều project Spring Integration 6.x; hãy điều chỉnh dependency/import theo phiên bản framework đang dùng nếu project đã chuyển Jackson APIs.

### 12.5. Gửi một frame thử

~~~java
String json = """
        {
          "schemaVersion": 1,
          "eventId": "evt-order-901",
          "orderId": "ORD-901",
          "sku": "SKU-RED",
          "quantity": 2,
          "workflowEpoch": 3
        }
        """;

TransportFrame frame = new TransportFrame(
        json,
        Map.of(
                "x-event-id", "evt-order-901",
                "x-tenant-id", "tenant-admin"),
        new VerifiedProducer("tenant-a", "partner-a"));

// Trong test/ứng dụng có Spring context:
transportFrames.send(
        org.springframework.messaging.support.MessageBuilder
                .withPayload(frame)
                .build());
~~~

**Kỳ vọng:** outbound packet chứa eventId evt-order-901 và JSON ACK, không chứa `x-tenant-id` từ raw header, không phát `trustedTenantId` ra wire. Đây là phép thử điều quan trọng nhất: **đúng business identity nhưng không copy dữ liệu ngoài chưa xác minh**.

## 13. Unit test inbound: payload và headers đúng, nguồn giả không được cấp quyền

Unit test tách mapper khỏi framework endpoint để kiểm chứng phần đổi payload/header và trust boundary.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.Map;

import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;

class OrderInboundMapperTest {
    private OrderInboundMapper mapper;

    @BeforeEach
    void prepare() {
        ObjectMapper jackson = new ObjectMapper().configure(
                DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, true);
        OrderSourceAuthorization auth = (producer, wire) -> {
            if (!"partner-a".equals(producer.producerId())) {
                throw new SecurityException("PRODUCER_NOT_ALLOWED");
            }
        };
        mapper = new OrderInboundMapper(jackson, auth);
    }

    private String json(String eventId, int quantity) {
        return """
                {
                  "schemaVersion": 1,
                  "eventId": "%s",
                  "orderId": "ORD-901",
                  "sku": "SKU-RED",
                  "quantity": %d,
                  "workflowEpoch": 3
                }
                """.formatted(eventId, quantity);
    }

    private TransportFrame frame(
            String eventId,
            Map<String, String> wireHeaders) {
        return new TransportFrame(
                json(eventId, 2),
                wireHeaders,
                new VerifiedProducer("tenant-a", "partner-a"));
    }

    @Test
    void mapsPayloadIntoTypedOrderCommand() {
        Message<OrderCommand> output =
                mapper.toTrustedMessage(frame(
                        "evt-order-901",
                        Map.of("x-event-id", "evt-order-901")));

        OrderCommand command = output.getPayload();
        assertEquals("ORD-901", command.orderId());
        assertEquals("SKU-RED", command.sku());
        assertEquals(2, command.quantity());
        assertEquals(3, command.workflowEpoch());
    }

    @Test
    void createsTrustedHeadersWithoutCopyingExternalHeaders() {
        Message<OrderCommand> output =
                mapper.toTrustedMessage(frame(
                        "evt-order-902",
                        Map.of(
                                "x-event-id", "evt-order-902",
                                "x-tenant-id", "tenant-admin",
                                "replyChannel", "maliciousChannel")));

        assertEquals("tenant-a",
                output.getHeaders().get("trustedTenantId"));
        assertEquals("partner-a",
                output.getHeaders().get("producerId"));
        assertEquals("evt-order-902",
                output.getHeaders().get("businessEventId"));
        assertEquals(
                "order:tenant-a:ORD-901:epoch-3",
                output.getHeaders().get("businessCorrelationKey"));

        assertNull(output.getHeaders().get("x-tenant-id"));
        assertNull(output.getHeaders().get("replyChannel"));
    }

    @Test
    void rejectsHeaderAndPayloadEventIdMismatch() {
        TransportFrame frame = frame(
                "evt-order-903",
                Map.of("x-event-id", "evt-other"));

        assertThrows(SecurityException.class,
                () -> mapper.toTrustedMessage(frame));
    }

    @Test
    void rejectsUnauthorizedProducer() {
        TransportFrame frame = new TransportFrame(
                json("evt-order-904", 1),
                Map.of(),
                new VerifiedProducer("tenant-a", "unknown-producer"));

        assertThrows(SecurityException.class,
                () -> mapper.toTrustedMessage(frame));
    }

    @Test
    void rejectsMalformedJson() {
        TransportFrame frame = new TransportFrame(
                "{not-valid-json",
                Map.of(),
                new VerifiedProducer("tenant-a", "partner-a"));

        assertThrows(IllegalArgumentException.class,
                () -> mapper.toTrustedMessage(frame));
    }

    @Test
    void rejectsInvalidQuantity() {
        TransportFrame frame = new TransportFrame(
                json("evt-order-905", 0),
                Map.of(),
                new VerifiedProducer("tenant-a", "partner-a"));

        assertThrows(IllegalArgumentException.class,
                () -> mapper.toTrustedMessage(frame));
    }

    @Test
    void rejectsUnknownFieldsUnderStrictContract() {
        String unknownField = """
                {
                  "schemaVersion": 1,
                  "eventId": "evt-order-906",
                  "orderId": "ORD-901",
                  "sku": "SKU-RED",
                  "quantity": 2,
                  "workflowEpoch": 3,
                  "unexpectedControlChannel": "admin"
                }
                """;

        TransportFrame frame = new TransportFrame(
                unknownField, Map.of(),
                new VerifiedProducer("tenant-a", "partner-a"));

        assertThrows(IllegalArgumentException.class,
                () -> mapper.toTrustedMessage(frame));
    }
}
~~~

**Điều test được:** mapper tạo typed payload; custom headers đáng tin được sinh từ verified context; raw x-tenant-id/replyChannel không được copy; mismatched eventId, unauthorized producer, malformed JSON và validation error bị chặn.

**Điều chưa được test:** HTTP/JMS adapter thật có normalize header name/content type ra đúng như TransportFrame hay không; mTLS/JWT/ACL thực sự cấp VerifiedProducer ra sao; broker ACK/retry và database side effect.

### 13.1. Strict unknown fields là một policy, không phải chuẩn chung

Ví dụ dùng **FAIL_ON_UNKNOWN_PROPERTIES=true** để phát hiện dữ liệu không đúng hợp đồng v1. Một hệ thống cần forward/backward compatibility có thể cho phép unknown optional fields, nhưng phải quyết định rõ dựa trên schema/version. Đừng ngẫu nhiên bỏ field ảnh hưởng authorization, currency hoặc semantics.

### 13.2. Data type conversion là một phần contract

Một producer gửi quantity dưới dạng String **"2"** và producer khác gửi JSON number **2**. Nếu ObjectMapper được cấu hình coercion, chúng có thể cùng thành int; nhưng có thể làm dữ liệu sai bị chấp nhận. Khi chọn strict schema, tắt coercions không mong muốn và thêm tests cho number, String, null, overflow/negative.

## 14. Unit test outbound: chọn đúng wire fields và không làm lộ headers

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.Map;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class OrderOutboundMapperTest {

    private final ObjectMapper jackson = new ObjectMapper();
    private final OrderOutboundMapper mapper =
            new OrderOutboundMapper(jackson);

    private Message<OrderAccepted> acceptedMessage() {
        return MessageBuilder.withPayload(
                new OrderAccepted(
                        "tenant-a",
                        "partner-a",
                        "evt-order-901",
                        "ORD-901",
                        "ACCEPTED"))
                .setHeader("trustedTenantId", "tenant-a")
                .setHeader("businessEventId", "evt-order-901")
                .setHeader(
                        "businessCorrelationKey",
                        "order:tenant-a:ORD-901:epoch-3")
                .setHeader("internalRiskScore", 99)
                .build();
    }

    @Test
    void producesVersionedJsonAndSelectedNativeHeaders()
            throws Exception {
        Message<OutboundPacket> output =
                mapper.toWire(acceptedMessage());

        OutboundPacket packet = output.getPayload();
        JsonNode root = jackson.readTree(packet.jsonBody());

        assertEquals(1, root.path("schemaVersion").asInt());
        assertEquals("evt-order-901",
                root.path("eventId").asText());
        assertEquals("ORD-901",
                root.path("orderId").asText());
        assertEquals("ACCEPTED",
                root.path("outcome").asText());
        assertTrue(root.path("tenantId").isMissingNode());
        assertTrue(root.path("internalRiskScore").isMissingNode());

        assertEquals(
                Map.of(
                        "content-type", "application/json",
                        "x-event-id", "evt-order-901",
                        "x-schema-version", "1"),
                packet.nativeHeaders());
        assertFalse(
                packet.nativeHeaders()
                        .containsKey("trustedTenantId"));
        assertFalse(
                packet.nativeHeaders()
                        .containsKey("businessCorrelationKey"));
    }

    @Test
    void rejectsHeaderPayloadIdentityMismatch() {
        Message<OrderAccepted> forged =
                MessageBuilder.withPayload(
                        new OrderAccepted(
                                "tenant-a",
                                "partner-a",
                                "evt-order-901",
                                "ORD-901",
                                "ACCEPTED"))
                .setHeader("trustedTenantId", "tenant-b")
                .setHeader("businessEventId", "evt-order-901")
                .build();

        assertThrows(SecurityException.class,
                () -> mapper.toWire(forged));
    }
}
~~~

Test kiểm tra **bề mặt công khai của OutboundPacket** chứ không chỉ kiểm tra một MessageHeaders nội bộ. Đây là khác biệt quan trọng: có thể internal Message vẫn giữ context cho observability, nhưng outbound transport contract chỉ được chứa selected fields.

### 14.1. Header duplication gây rủi ro gì?

Khi eventId ở cả body và x-event-id, transport receiver phải kiểm tra nhất quán hoặc quy định nguồn nào có authority. Không để người gửi thay đổi một trong hai rồi downstream chọn ngẫu nhiên dẫn tới dedup sai.

### 14.2. Copy-on-write và immutability

Wire packet dạng String JSON + Map.copyOf là đủ minh họa. Với byte arrays, streaming buffers hoặc file handles, cần ownership/defensive copies và không chia sẻ mutable state vô kiểm soát giữa PublishSubscribeChannel subscribers.

## 15. Spring integration test: đi xuyên inbound mapper → outbound sink

Integration test này khởi động **OrderAdapterHarnessConfig**, gửi một TransportFrame mô phỏng inbound adapter, rồi kiểm tra packet mà outbound sink đã nhận.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.Map;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(OrderAdapterHarnessConfig.class)
class OrderAdapterHarnessIntegrationTest {

    @Autowired
    @Qualifier("transportFrames")
    MessageChannel input;

    @Autowired
    CollectingOutboundAdapter output;

    @Autowired
    DemoOrderProcessor processor;

    @Autowired
    ObjectMapper jackson;

    @BeforeEach
    void resetOutput() {
        output.clear();
    }

    private TransportFrame frame(
            String eventId,
            String tenantId,
            int quantity) {
        String json = """
                {
                  "schemaVersion": 1,
                  "eventId": "%s",
                  "orderId": "ORD-901",
                  "sku": "SKU-RED",
                  "quantity": %d,
                  "workflowEpoch": 3
                }
                """.formatted(eventId, quantity);

        return new TransportFrame(
                json,
                Map.of(
                        "x-event-id", eventId,
                        "x-tenant-id", "tenant-admin"),
                new VerifiedProducer(tenantId, "partner-a"));
    }

    private void send(TransportFrame frame) {
        assertTrue(input.send(
                MessageBuilder.withPayload(frame).build()));
    }

    @Test
    void validInputBecomesOutboundAckWithSelectedHeaders()
            throws Exception {

        send(frame("evt-flow-901", "tenant-a", 2));

        assertEquals(1, output.packets().size());
        OutboundPacket packet = output.packets().get(0);

        JsonNode root = jackson.readTree(packet.jsonBody());
        assertEquals("evt-flow-901",
                root.path("eventId").asText());
        assertEquals("ORD-901",
                root.path("orderId").asText());
        assertEquals("ACCEPTED",
                root.path("outcome").asText());
        assertEquals("evt-flow-901",
                packet.nativeHeaders().get("x-event-id"));
        assertNull(
                packet.nativeHeaders().get("x-tenant-id"));
        assertNull(
                packet.nativeHeaders().get("replyChannel"));
    }

    @Test
    void duplicateEventReplaysAckWithoutCreatingSecondRecord() {
        int before = processor.uniqueEventCount();
        TransportFrame event =
                frame("evt-flow-duplicate", "tenant-a", 2);

        send(event);
        send(event);

        assertEquals(before + 1, processor.uniqueEventCount());
        assertEquals(2, output.packets().size());
        assertEquals(
                output.packets().get(0).jsonBody(),
                output.packets().get(1).jsonBody());
    }

    @Test
    void conflictingPayloadUnderSameEventIdFails() {
        send(frame("evt-flow-conflict", "tenant-a", 2));

        assertThrows(RuntimeException.class,
                () -> send(
                        frame("evt-flow-conflict", "tenant-a", 3)));

        assertEquals(1, output.packets().size());
    }

    @Test
    void sameEventIdDifferentTenantsDoNotCollide() {
        int before = processor.uniqueEventCount();

        send(frame("evt-flow-tenant", "tenant-a", 2));
        send(frame("evt-flow-tenant", "tenant-b", 2));

        assertEquals(before + 2, processor.uniqueEventCount());
        assertEquals(2, output.packets().size());
    }

    @Test
    void badEventHeaderIsRejectedBeforeSink() {
        TransportFrame bad = new TransportFrame(
                """
                {
                  "schemaVersion": 1,
                  "eventId": "evt-flow-bad",
                  "orderId": "ORD-901",
                  "sku": "SKU-RED",
                  "quantity": 2,
                  "workflowEpoch": 3
                }
                """,
                Map.of("x-event-id", "evt-different"),
                new VerifiedProducer("tenant-a", "partner-a"));

        assertThrows(RuntimeException.class, () -> send(bad));
        assertTrue(output.packets().isEmpty());
    }
}
~~~

### 15.1. Điều test đã chứng minh

- Spring Integration đăng ký các annotated Transformer và Service Activator endpoints.
- Message đi qua chuỗi channels đồng bộ như đã thiết kế.
- Payload chuyển JSON → typed OrderCommand → OrderAccepted → ACK JSON.
- Business identity giữ đúng và native output headers được allowlist.
- Same-event replay trong cùng JVM không tạo record mới trong demo processor.
- Same event ID ở hai tenants không bị gộp khi ledger dùng namespace phù hợp.
- Mismatched event header hoặc event conflict không tạo output success mới.

### 15.2. Điều test chưa chứng minh

- HTTP/JMS/AMQP/TCP header mapper cụ thể hoạt động đúng qua network.
- Authentication/authorization thực tế với external producer.
- Event được ack/requeue đúng khi broker redelivery.
- Transactional inbox/outbox chống lỗi sau process restart.
- Exactly-once external side effects hoặc distributed commits.
- Behavior khi DirectChannel được thay bằng ExecutorChannel/QueueChannel.

**Đây là test contract của mapping trong Spring runtime, không phải end-to-end network adapter test.**

## 16. HTTP adapter: body và headers là hai kênh dữ liệu khác nhau

Với HTTP, request có **method, URI, status, content type, body và headers**. Adapter có thể tạo Spring Message từ request và có thể chọn body làm payload; native HTTP headers không tự trở thành tất cả custom headers của ứng dụng.

~~~text
POST /external/orders/events
Content-Type: application/json
X-Event-Id: evt-order-901
X-Tenant-Id: tenant-admin

{"schemaVersion":1,"eventId":"evt-order-901", ...}
~~~

Một inbound boundary an toàn:

~~~mermaid
flowchart TD
    H["HTTP request"] --> A["Authentication + content-type/size limits"]
    A --> P["Parse JSON + schema validation"]
    P --> V["Authorize tenant/order + event identity"]
    V --> M["Create trusted Spring Message"]
    M --> C["Internal channel"]
~~~

### 16.1. HTTP inbound channel adapter và HTTP inbound gateway

- **Inbound Channel Adapter:** phù hợp một chiều, ví dụ nhận notification/event rồi phát vào channel; HTTP response thường chỉ xác nhận mức transport/acceptance theo cấu hình.
- **Inbound Gateway:** phù hợp HTTP request cần một Spring Message reply ánh xạ trở lại HTTP response.

Nếu endpoint `POST /quote` phải trả giá đồng bộ, **Gateway** thường đúng semantics hơn adapter một chiều. Nếu endpoint chỉ nhận event và một workflow xử lý sau, **adapter + durable ingestion/accepted policy** có thể hợp lý.

### 16.2. HeaderMapper cần chính sách allowlist

Ví dụ mapping được công bố:

| HTTP source | Inbound handling | Spring internal header |
| --- | --- | --- |
| `Content-Type` | Validate JSON media type | Chỉ dùng cho converter/content-type |
| `X-Event-Id` | Validate và đối chiếu body.eventId | `businessEventId` |
| `X-Tenant-Id` | Dùng làm claimed tenant để đối chiếu nếu cần | **Không** tự chuyển thành trustedTenantId |
| `X-Trace-Ref` | Validate length/charset | `externalTraceRef` tùy hợp đồng |
| `Authorization` | Authentication filter sử dụng | Không echo tới domain/outbound |
| `X-Reply-Channel` | Không cho client điều khiển MessageChannel | Bỏ/reject |

Trong Spring Integration HTTP, `HeaderMapper` và `HttpMessageConverter` giải quyết các mối quan tâm khác nhau. Converter chuyển body/Java object, còn HeaderMapper chuyển các selected HTTP headers. Security filter/controller/verification layer mới quyết định trust.

### 16.3. Content-Type không đồng nghĩa payload thực hợp lệ

`Content-Type: application/json` không chứng minh body là JSON đúng schema. Kiểm tra encoding, body size và thực sự parse. Nếu dùng một API đòi JSON v1, unknown `schemaVersion=99` phải đi vào unsupported version path chứ không mặc định parse như v1.

### 16.4. HTTP status contract

Một event ingestion API có thể công bố:

- 202 Accepted: command/event đã được nhận vào boundary có thể xử lý tiếp theo contract.
- 400 Bad Request: malformed JSON/missing required fields.
- 401/403: authentication hoặc authorization fail.
- 409 Conflict: eventId/operationId reused với payload khác.
- 415 Unsupported Media Type: Content-Type không hỗ trợ.
- 422 Unprocessable Content: schema hợp cú pháp nhưng vi phạm business field policy.
- 429/503: rate limit hoặc tạm thời không phục vụ.

Đây là **gợi ý contract**, không phải mapping status mặc định của Spring Integration. Nếu một adapter trả 202 trước khi persist command, phải mô tả rõ khả năng mất sự kiện khi process crash.

## 17. JMS adapter: Java Message headers khác JMS headers/properties

JMS có **JMSMessageID, JMSCorrelationID, JMSReplyTo, JMSType** và application properties. Spring Integration JMS adapters chuyển JMS Message thành Spring Message theo converter/header mapper và ngược lại.

~~~text
JMS TextMessage:
  body = {"schemaVersion":1,...}
  JMSMessageID = ID:...
  JMSCorrelationID = some-protocol-token
  property event_id = evt-order-901

JMS inbound adapter
  -> MessageConverter / HeaderMapper
  -> Spring Message<OrderWireV1 / String / byte[]>
  -> Trusted normalization
  -> Message<OrderCommand>
~~~

### 17.1. Hai hướng mapping khác nhau

| JMS concept | Spring concept | Lưu ý |
| --- | --- | --- |
| JMS TextMessage body | Payload String hoặc converted DTO | Phụ thuộc converter |
| JMS BytesMessage body | Payload byte[] hoặc DTO | Giới hạn size, encoding/schema |
| JMSMessageID | Native JMS transport identity | Không thay businessEventId |
| JMSCorrelationID | Protocol correlation | Không tự làm workflow correlation |
| JMSReplyTo | Destination của JMS request/reply | Không phải Spring temporary MessageChannel |
| Custom JMS property event_id | Custom Spring header nếu mapped | Cần contract tên/kiểu |
| JMS redelivery flag | Delivery metadata | Chỉ dấu hiệu retry, không bảo đảm dedup |

### 17.2. HeaderMapper không phải content converter

Trong các phiên bản Spring Integration dùng JMS, có các lớp hỗ trợ JMS header mapping như **DefaultJmsHeaderMapper** và converters cho JMS payload. Cấu hình mapper xác định properties/headers nào đi vào Spring Message. Cấu hình converter xác định body JSON/TextMessage/BytesMessage đi vào payload Java nào.

Nếu broker property `event_id` đã đi vào Spring headers nhưng payload vẫn là một String JSON, bước mapping **chưa hoàn tất**: cần parse thành OrderWireV1, validate schema, rồi tạo OrderCommand.

### 17.3. JMS properties có hạn chế type

JMS properties có các kiểu dữ liệu được giao thức hỗ trợ; không giả định một arbitrary Java object như MessageChannel, DomainEnvelope hay RequestContext có thể được copy làm property. Chỉ gửi values theo wire contract portable, chẳng hạn String/boolean/number khi hợp lệ.

### 17.4. Ack và transaction

JMS inbound adapter có semantics ack/session transaction/poller tùy cấu hình. Nếu handler đã làm external side effect nhưng session rollback vì reply/send lỗi, message có thể bị giao lại. Do đó businessEventId/operationId cần ổn định và downstream effect phải idempotent.

### 17.5. Không dùng JMSCorrelationID để chống trùng nghiệp vụ

Một yêu cầu có thể được thử lại với **JMSCorrelationID khác** cho request/reply attempt mới nhưng vẫn có cùng businessEventId. Nếu dedup theo protocol correlation token, effect có thể chạy hai lần. Chọn scope từ business identity đã được xác minh.

## 18. AMQP adapter: properties, headers và broker confirms

AMQP (ví dụ RabbitMQ) thường có **contentType, correlationId, replyTo, deliveryMode, routingKey, application headers** cùng payload bytes. Cơ chế message converter và header mapper chịu trách nhiệm đổi sang Spring Message.

~~~text
AMQP:
  body = UTF-8 JSON bytes
  contentType = application/json
  headers.event_id = evt-order-901
  correlationId = request-attempt-123
  replyTo = reply-queue-for-attempt

Inbound mapping:
  converter -> OrderWireV1
  header policy -> permitted metadata
  verifier -> trusted producer/tenant
  transformer -> OrderCommand
~~~

### 18.1. Một publisher confirm không phải OrderAccepted

Broker confirm có thể xác nhận broker đã nhận message. Nó **không chứng minh** consumer Service Activator đã ghi dữ liệu hoặc trả business result. Nếu caller cần biết kết quả, dùng request/reply Gateway hoặc asynchronous completion contract.

### 18.2. Correlation IDs theo scope

`correlationId` AMQP có thể do outbound gateway sử dụng để nối reply về request attempt. Nó không nhất thiết bằng `businessCorrelationKey` của order. Nếu một message bị gửi lại sau timeout với attempt token mới, business identity vẫn cần giữ nguyên.

### 18.3. Retry và DLQ

Khi consumer fail, tùy listener/container policy message có thể được requeue, retry hoặc gửi DLQ. **Malformed schema/unauthorized message** không nên bị retry vô hạn như lỗi network tạm thời. Cần dead-letter/quarantine có reason code và policy xử lý lại, đồng thời tránh replay tạo effect trùng.

### 18.4. Header type portable

Không gửi arbitrary Java class instances trong AMQP application headers. Dùng dữ liệu portable và có schema; nếu cần nested business metadata, cân nhắc wire envelope JSON/Avro/Protobuf thay vì hy vọng HeaderMapper serialize tùy ý.

## 19. File/SFTP adapter: payload có thể là File, không phải JSON String

File inbound adapters thường phát message chứa **java.io.File** hoặc nội dung file tùy nguồn và cấu hình. Một Service Activator expecting `OrderCommand` không tự nhận đúng DTO khi payload là File.

~~~mermaid
flowchart LR
    D["Incoming directory"] --> F["File inbound adapter"]
    F --> M["Message<File>"]
    M --> P["Read bounded bytes + UTF-8 decode"]
    P --> J["Validate JSON schema / origin"]
    J --> T["OrderCommand + trusted metadata"]
    T --> S["Service Activator"]
~~~

### 19.1. File name là metadata, không phải quyền

Một file có tên `tenant-admin_orders.json` không chứng minh nó thuộc tenant-admin. Với SFTP, cần ràng buộc remote account/directory/transport identity với tenant được phép; không chỉ parse tenant từ filename.

### 19.2. File payload lớn và streaming

Không gọi `Files.readString(file)` vô điều kiện với file dung lượng nhiều GB. Kiểm tra kích thước, quyền đọc, symbolic links/path traversal và streaming parser nếu cần. Với file-based polling, dùng filters/locks/rename policies tránh đọc file đang được ghi dở hoặc xử lý lặp không kiểm soát.

### 19.3. Outbound filename phải an toàn

Không để untrusted `orderId="../../secrets"` trở thành path ghi file. Dùng sanitized basename, target directory cố định, collision policy và atomic write/rename khi có yêu cầu durability.

### 19.4. Một file có thể chứa nhiều events

Nếu mỗi file có một batch orders, cần Splitter tách records, tạo **child logical IDs** ổn định và correlation/group semantics cho batch. Không dùng `sequenceNumber` một mình làm idempotency key; cần parent batch ID + child ID hoặc composite key có scope.

## 20. TCP và các transport không có header metadata giàu

TCP là luồng bytes, không tự có message boundary theo business schema. Spring Integration TCP adapters/gateways cần framing/serializer/deserializer xác định từng frame. Nếu payload mang eventId/tenantRef, cần deserialize theo **versioned envelope** và xác minh nguồn/tenant sau khi nhận.

~~~text
TCP bytes
   -> framing (length-prefixed / delimiter / custom)
   -> versioned wire envelope
   -> validate message length and schema
   -> bind authenticated connection identity
   -> Spring Message<DomainCommand>
~~~

Không mặc định một TCP connection ID là business correlation key. Nhiều requests có thể đi trên cùng connection, và một logical operation có thể thử lại trên connection mới.

## 21. Bảng so sánh kỹ thuật mapping giữa các adapters

| Nguồn | Payload ban đầu thường gặp | Header native thường gặp | Conversion cần chủ ý |
| --- | --- | --- | --- |
| HTTP | String/byte[]/DTO theo converter | Headers, URI, method, content type | JSON schema + trusted principal |
| JMS | TextMessage/BytesMessage/converted object | JMSMessageID, JMSCorrelationID, properties | JMS MessageConverter + HeaderMapper |
| AMQP | byte[]/converted DTO | contentType, routing key, replyTo, application headers | AMQP converter/header mapping |
| File | File hoặc content | File name/path, timestamp, filter metadata | Bounded file read + decoder |
| SFTP | Local file representing downloaded content | Remote path/source account | Authenticated source binding + path safety |
| TCP | byte[]/String frame | Connection metadata | Framing + versioned envelope |
| In-process | Typed Java object | Spring MessageHeaders | Normalize header contracts between flows |

**Phần bất biến:** đầu vào của business service nên được chuẩn hóa thành một contract **domain payload + trusted context**, độc lập với adapter nguồn. Thay adapter không nên buộc Router/Service Activator biết tên native headers của từng giao thức.

## 22. Header propagation qua Router, Transformer, Splitter và Gateway

Khi adapter đã tạo Spring Message có trusted headers, thông điệp có thể đi qua nhiều endpoints. Cần phân biệt **metadata nghiệp vụ cần bảo toàn** với **metadata kỹ thuật thay đổi theo topology**.

~~~mermaid
flowchart TD
    I["Inbound Adapter"] --> N["Normalize payload + trusted headers"]
    N --> R{"Router by business type"}
    R --> T["Transformer"]
    T --> S["Service Activator"]
    S --> O["Outbound Adapter"]
    R --> P["Splitter / Aggregator flow"]
    P --> O
~~~

### 22.1. Khi Transformer trả payload thuần

Một Spring Integration Transformer thường hỗ trợ propagation của inbound headers khi nó trả payload mới. Chẳng hạn message vào có payload **OrderWireV1**, transformer tạo **OrderCommand**, và framework tạo output Message giữ metadata theo quy tắc của endpoint.

Tuy nhiên, **không phải mọi chuyển đổi giữ tất cả headers**: một HeaderFilter, một gateway/adapter boundary hoặc một custom handler trả Message mới có thể làm mất field. Contract tests nên xác minh businessEventId, trustedTenantId và correlationKey ở các hop quan trọng.

### 22.2. Khi một handler tạo Message mới

~~~java
// Ví dụ tái tạo Message với selected headers:
Message<OrderCommand> next = MessageBuilder
        .withPayload(command)
        .setHeader("trustedTenantId", verifiedTenant)
        .setHeader("businessEventId", stableEventId)
        .setHeader("businessCorrelationKey", businessKey)
        .build();
~~~

Không chỉ nhìn thấy payload đúng mà kết luận contract đã nguyên vẹn. Nếu một Service Activator downstream cần `@Header("businessEventId")`, thiếu header có thể khiến method argument resolution thất bại trước khi business method chạy.

### 22.3. HeaderFilter được dùng khi nào?

HeaderFilter có thể loại những metadata không nên truyền vào nhánh tiếp theo, ví dụ external trace claims, raw transport tags hoặc control headers không cần thiết. Nhưng nếu cấu hình filter quá rộng, bạn có thể xóa **businessCorrelationKey** khiến Aggregator hoặc handler ghép sai workflow.

### 22.4. Splitter và sequence headers

Splitter có thể gắn **correlationId**, **sequenceNumber**, **sequenceSize** cho từng child. Các giá trị này có thể phục vụ **technical group** riêng, không nhất thiết trùng businessCorrelationKey của order. Nếu một parent message sinh nhiều logical child events, mỗi child có thể cần child event ID riêng và parentEventId/causationId.

Không dùng cùng eventId cho tất cả child effects nếu chúng phải dedup độc lập, và không dùng sequenceNumber một mình để phân biệt events trên các batches khác nhau.

### 22.5. Gateway và temporary replyChannel

Một Messaging Gateway chờ reply có thể dùng **temporary replyChannel** trong runtime. Khi request đi qua outbound HTTP/JMS/AMQP Gateway, transport có reply/correlation protocol riêng. Không serialize một live MessageChannel object như wire header; nếu callback đến sau khi Gateway timeout, phải correlate bằng **persistent business identity**.

### 22.6. Trace propagation khác business ID

Trace headers giúp nối spans và logs; có thể có conventions như W3C trace context. Nhưng traceId không tự chứng minh tenant, không thay eventId cho idempotency và có thể thay đổi theo retry hoặc sampling policy. Cần giữ business identity ngay cả khi tracing bị tắt.

## 23. Hợp đồng header: tên, kiểu, ownership và scope

Một bảng contract rất hữu ích khi nhiều adapters cùng phục vụ một IntegrationFlow:

| Field | Kiểu nội bộ | Ai sở hữu? | Có được gửi ra wire? | Khi retry? |
| --- | --- | --- | --- | --- |
| **trustedTenantId** | String | Verified ingress/auth | Chỉ nếu partner contract cho phép, theo authority | Giữ tenant đúng |
| **producerId** | String | Authenticated source registry | Có thể không cần | Giữ cùng source scope |
| **businessEventId** | String | Source identity đã bind/validated | Thường cần | Cùng logical event thì giữ |
| **businessCorrelationKey** | String | Workflow service | Nếu wire contract cần | Cùng workflow thì giữ |
| **externalTraceRef** | String | External caller, đã sanitize | Chỉ khi phù hợp | Không làm authority |
| **replyChannel** | MessageChannel/runtime | Spring Gateway | **Không** | Attempt-specific |
| **errorChannel** | Channel/runtime | Spring integration | **Không** | Theo endpoint |
| **correlationId** | Object/String tùy topology | Splitter/Aggregator/transport | Theo protocol riêng nếu cần | Scope-specific |
| **sequenceNumber** | Integer | Splitter | Chỉ nếu wire contract cần | Child-specific |
| **JMSMessageID** | String/JMS native | JMS broker | Native transport field | Có thể đổi |
| **AMQP deliveryTag** | Number/native | Broker/consumer delivery | Không làm business ID | Thay theo delivery |
| **Content-Type** | Media type | Wire contract/adapter | Có | Theo encoding |

### 23.1. Đừng dùng Spring MessageHeaders.ID làm business eventId

Nếu một message được tạo lại khi chuyển adapter, **Spring MessageHeaders.ID có thể đổi**. BusinessEventId của cùng logical event phải ổn định để dedup. Dùng source event ID/operation registry và scope đúng tenant/producer, không dùng UUID mới mỗi khi Transformer tạo Message.

### 23.2. Không ép business key vào technical correlation scope

Một order workflow có thể có nhiều Splitter/Aggregator groups và remote Gateway invocations. Nếu buộc mọi CORRELATION_ID bằng businessCorrelationKey, nested Aggregator có thể trộn các child groups thuộc các giai đoạn khác nhau. Giữ business key riêng hoặc thiết kế correlationStrategy cho đúng nhóm.

### 23.3. Dynamic native header Map cần giới hạn

Ngoài tên/kiểu, giới hạn:

- Header count tối đa.
- Key name allowlist, charset/length, case normalization.
- Giá trị String/number/boolean portable theo transport.
- Không cho duplicate keys trái contract.
- Không dùng untrusted destination/routing key trực tiếp.
- Không truyền dữ liệu bảo mật sang message headers nếu receiver không cần.

HeaderMapper chuyển biểu diễn; **source authentication và authorization phải diễn ra trước khi tin semantic của các field**.

## 24. Schema evolution: adapter là ranh giới tương thích

Với nhiều producers, wire v1/v2 có thể cùng tồn tại trong broker hoặc filesystem sau khi ứng dụng deploy phiên bản mới.

### 24.1. Không sửa nghĩa field âm thầm

Ví dụ wire v1:

~~~json
{"quantity": 2, "quantityUnit": "pieces"}
~~~

Và wire v2 thay semantics:

~~~json
{"quantity": 2, "quantityUnit": "boxes"}
~~~

Nếu handler v1 chỉ đọc số 2 mà không đọc unit, một adapter mới có thể khiến hệ thống xuất kho sai gấp nhiều lần. Thay đổi semantics không tương thích ngay cả khi JSON field name và kiểu dữ liệu không đổi.

### 24.2. Versioned parser/upcaster

~~~mermaid
flowchart LR
    V1["WireOrderV1"] --> P1["Parse v1"]
    V2["WireOrderV2"] --> P2["Parse v2"]
    P1 --> C["Canonical OrderCommand"]
    P2 --> C
    C --> B["Business flow"]
~~~

Mỗi converter phải biết:

- Schema versions được hỗ trợ.
- Required/optional fields.
- Defaults có nghĩa nghiệp vụ hợp lệ.
- Enum migration hoặc unsupported values.
- Unit/currency/timezone.
- Validation của producer/client identity.
- Cách tạo canonical businessEventId và correlationKey.

### 24.3. Upcaster không được bịa identity

Nếu event v1 thiếu operationId nhưng v2 yêu cầu, không tự tạo UUID mỗi khi replay. Cần xem v1 có stable source ID đủ để derive operationId không; nếu không, đặt event vào migration/quarantine workflow để xử lý có kiểm soát.

### 24.4. Outbound projection theo receiver contract

Receiver A còn dùng ACK v1, receiver B đã dùng ACK v2. Adapter có thể chọn serializer theo **configured receiver capability** hoặc negotiated version, không lấy version chỉ từ một untrusted header. Nếu receiver không hiểu phiên bản mới, trả failure rõ thay vì gửi payload mới nhưng dán `x-schema-version: 1`.

### 24.5. Replay và DLQ phải version-aware

Một message nằm trong DLQ hai tuần có thể dùng schema v1 khi ứng dụng đã ở v2. Recovery worker phải có parser/upcaster v1 hoặc migration plan. Không giả định mọi message đang chờ đều theo version mới nhất chỉ vì code đã deploy.

### 24.6. Strict và tolerant parsing

- **Strict:** reject unknown fields để bắt schema drift sớm; phù hợp boundary kiểm soát chặt.
- **Tolerant có kiểm soát:** bỏ qua unknown optional fields nếu contract cho phép, nhưng không được bỏ fields có ý nghĩa an ninh/nghiệp vụ.

Việc bật/tắt Jackson FAIL_ON_UNKNOWN_PROPERTIES nên được thiết kế và test theo version policy, không theo sở thích nhất thời.

## 25. Retry, acknowledgments và side effects ở adapter boundary

Khi một outbound adapter gửi event, có ít nhất ba mức “thành công” khác nhau:

~~~text
1. Producer created and validated the Spring Message.
2. Adapter / broker accepted the transport message.
3. Remote business consumer committed its effect.
~~~

Không được suy ra mức 3 từ mức 1 hoặc 2. Với một outbound adapter một chiều, mức business completion có thể được báo qua sự kiện khác, status API hoặc audit workflow.

### 25.1. Inbound ACK timing

Một inbound broker adapter có thể ack:

- Sau khi lấy Message từ broker.
- Sau khi flow xử lý đồng bộ thành công.
- Trong transaction bao gồm một phần xử lý.
- Theo manual acknowledgment do application kiểm soát.

Cấu hình thực tế khác nhau giữa JMS, AMQP, Kafka và phiên bản framework. Nếu ack trước khi persist operation, process crash có thể làm mất event. Nếu ack sau side effect nhưng trước ack broker, crash có thể dẫn tới redelivery và duplicate effect.

### 25.2. Outbound send timeout

Nếu outbound adapter báo timeout sau khi gửi, có thể:

- Remote/broker chưa nhận packet.
- Broker đã nhận nhưng confirm mất.
- Consumer đã nhận/commit nhưng reply mất.

Nếu packet đại diện cho một **command có side effect**, không tạo operationId mới rồi gửi lại vô điều kiện. Tra status hoặc retry bằng stable key theo contract.

### 25.3. Dedup key phải phù hợp scope

~~~text
tenantId      = tenant-a
producerId    = partner-a
businessEventId = evt-order-901

Idempotency key:
  tenant-a | partner-a | evt-order-901
~~~

Nếu cùng producer dùng lại eventId với payload khác, đó là **ID_CONFLICT**. Nếu hai producers khác nhau đều dùng `evt-order-901`, có thể là hai events riêng nếu contract xác nhận ID chỉ duy nhất trong producer scope.

### 25.4. In-memory dedup không bền qua restart

DemoOrderProcessor trong ví dụ chỉ giữ ConcurrentHashMap. Khi process restart, dữ liệu mất. Nếu cần bền, triển khai ledger có unique index và transaction:

~~~sql
CREATE TABLE order_event_inbox (
    tenant_id VARCHAR(48) NOT NULL,
    producer_id VARCHAR(48) NOT NULL,
    event_id VARCHAR(96) NOT NULL,
    order_id VARCHAR(64) NOT NULL,
    workflow_epoch INTEGER NOT NULL,
    payload_digest VARCHAR(128) NOT NULL,
    processing_state VARCHAR(32) NOT NULL,
    result_reference VARCHAR(160),
    received_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, producer_id, event_id)
);

CREATE INDEX order_event_inbox_state_idx
    ON order_event_inbox (processing_state);
~~~

Một row có state RECEIVED không chứng minh business effect đã commit. Cần state machine/worker lease/recovery và, khi dispatch sang hệ thống khác, transactional outbox hoặc cách đồng bộ hóa thích hợp.

### 25.5. Khoảng hở crash

~~~text
1. Adapter receives event.
2. Application writes inbox state=RECEIVED.
3. Application acknowledges broker.
4. Process crashes before business handler runs.
5. Broker will not redeliver; event remains RECEIVED.
~~~

Recovery worker cần tìm các events còn RECEIVED/DISPATCH_PENDING và tiếp tục xử lý. Nếu chỉ bỏ duplicate vì row đã tồn tại, message có thể bị “mất” vĩnh viễn dù inbox có record.

### 25.6. Outbox cho outbound publishing

Nếu ứng dụng vừa ghi order vào DB vừa muốn publish OrderAccepted, có thể dùng **transactional outbox**:

~~~text
DB transaction:
  UPDATE order state
  INSERT outbox event with stable eventId
COMMIT

Outbox publisher:
  read pending records
  adapter send to broker
  mark as delivered according to policy
~~~

Outbox publisher có thể phát cùng event hơn một lần sau crash/confirm loss; consumers vẫn cần idempotency. Outbox giảm khoảng hở giữa DB commit và event publication, **không tự tạo exactly-once delivery trên toàn hệ thống**.

### 25.7. Retry decision table

| Failure | Có retry không? | Lý do |
| --- | --- | --- |
| Malformed JSON, schemaVersion lạ | Không retry nguyên payload vô hạn | Permanent contract issue |
| Header/payload eventId mismatch | Không dispatch business event | Identity violation |
| Producer chưa được cấp quyền | Không retry như transient IO | Security failure |
| External API timeout | Có thể retry bounded | Stable operationId/reconcile |
| Database tạm thời không sẵn sàng | Có thể | Backoff + durable recovery |
| Same event replay | Có thể trả receipt cũ/skip effect | Idempotency |
| Same key, different payload | Không coi là duplicate bình thường | Conflict/quarantine |
| Broker confirm lost | Retry có kiểm soát | Có thể packet đã được nhận |
| Outbound header converter lỗi type | Fix converter/schema | Không retry vô hạn |
| Receiver reports unsupported version | Rollback/upcast/upgrade | Compatibility |

## 26. Error flow: schema error khác handler error và broker error

Một adapter pipeline có nhiều điểm có thể lỗi:

~~~mermaid
flowchart TD
    A["Inbound transport"] --> V{"Decode / validate"}
    V -->|"Malformed / unsupported"| Q["Reject / quarantine"]
    V -->|"Valid"| B{"Authenticate / authorize"}
    B -->|"Denied"| S["Security rejection"]
    B -->|"Verified"| C{"Internal processing"}
    C -->|"Business reject"| R["Typed business outcome"]
    C -->|"Transient failure"| T["Retry / recover"]
    C -->|"Success"| O{"Outbound convert / send"}
    O -->|"Converter failure"| F["Contract failure"]
    O -->|"Send failed / unknown"| U["Outbox retry / reconcile"]
    O -->|"Transport accepted"| D["Transport delivery status"]
~~~

### 26.1. DirectChannel trong harness

Tất cả channels ví dụ là DirectChannel. Một exception ở OrderInboundMapper/processor/outbound mapper thường propagate ngược về `input.send(...)`. Vì vậy negative integration tests có thể assert RuntimeException và chắc rằng sink không nhận packet success.

**Không suy ra** behavior này cho QueueChannel, ExecutorChannel, poller, AMQP listener hoặc JMS session; thread, errorChannel, acknowledgment và transaction semantics khác nhau.

### 26.2. ErrorMessage không có payload nghiệp vụ

Trong flow bất đồng bộ, error handler có thể nhận **ErrorMessage** với payload là Throwable, có thể tham chiếu failedMessage. Không cast `errorMessage.getPayload()` thành OrderCommand. Cần trích context có kiểm soát từ failedMessage hoặc persisted inbox để biết eventId, tenant và source.

### 26.3. Không mọi lỗi đi vào default route của Router

Nếu Router nhận payload type chưa hỗ trợ, có thể route sang default/reject channel. Nếu Transformer ném InvalidWireJson exception, đó là **error flow**, không tự chuyển thành default Router route. Cấu hình error routing riêng.

### 26.4. Có cần một error reply hay không?

- Với HTTP inbound Gateway, có thể map lỗi validation/auth thành HTTP response có schema.
- Với một inbound Channel Adapter một chiều, có thể reject/ack/DLQ và ghi audit theo contract.
- Với outbound adapter, không nên giả một business success reply khi send thất bại.
- Với request/reply remote Gateway, technical error có thể được chuyển thành structured fault hoặc exception tùy contract; timeout không tự là business rejection.

### 26.5. Quarantine có thời hạn và quyền truy cập

Một error record có thể gồm:

~~~json
{
  "eventRef": "evt-order-901",
  "sourceType": "HTTP_PARTNER",
  "stage": "INBOUND_VALIDATION",
  "reasonCode": "EVENT_ID_HEADER_PAYLOAD_MISMATCH",
  "schemaVersion": 1,
  "outcome": "QUARANTINED"
}
~~~

Raw payload chứa PII/secret phải được mã hóa hoặc tách storage bảo vệ, có retention/access audit. Không log toàn bộ body hay Authorization header trong message lỗi chỉ để dễ debug.

### 26.6. Error taxonomy

| Lớp lỗi | Ví dụ | Hành vi |
| --- | --- | --- |
| **Decode** | Invalid JSON, invalid UTF-8 | Reject/quarantine |
| **Schema** | Unknown version/enum | Unsupported contract |
| **Header mapping** | Missing/wrong type/duplicate header | Normalize/reject |
| **Trust** | Tenant spoofing, source unauthorized | Security reject |
| **Business** | Order không hợp policy | Typed reject nếu contract định nghĩa |
| **Processing** | DB deadlock/outage | Retry bounded + recovery |
| **Outbound conversion** | Không encode được wire v1 | Fail, alert, không gửi payload sai |
| **Transport send** | Network reset/confirm unknown | Outbox retry/reconcile |
| **Reply correlation** | Wrong requestId/late reply | Reject/park theo workflow |

## 27. Security tại ranh giới adapter

Adapter là một **trust boundary**. Những câu hỏi phải trả lời trước khi gắn trusted headers:

1. Producer là ai? Bằng chứng authentication từ đâu?
2. Producer có quyền tạo event cho tenant/order đó không?
3. Payload có vượt size/rate limits, hoặc chứa enum/type không hỗ trợ không?
4. Có header nào đang cố điều khiển route/reply/error channel không?
5. EventId đã bị dùng với payload khác chưa?
6. Có khả năng JSON/XML parser bị lạm dụng (entity expansion, polymorphic types, excessive nesting) không?
7. Outbound reply/event có làm lộ internal metadata hoặc thông tin tenant khác không?

### 27.1. Header injection

Một external sender có thể gửi native properties giống tên Spring internal headers:

~~~text
trustedTenantId = tenant-admin
replyChannel = adminInternalChannel
errorChannel = suppressErrors
routingSlip = secretRoute
~~~

Không pass-through những tên này vào Spring Message trong một trusted flow. Ingress tự tạo trusted metadata và framework control headers từ cấu hình nội bộ.

### 27.2. Header spoofing không chỉ là casing

HTTP có tính case-insensitive ở header names; JMS/broker application property names có quy tắc khác. Khi normalize case, phải xử lý **duplicate/colliding header names**: ví dụ cả `X-Event-Id` và `x-event-id` xuất hiện với hai giá trị khác nhau. Không tùy ý chọn cái đầu hoặc cuối; reject theo policy.

### 27.3. Dynamic destination injection

Không lấy native header `destination=admin.internal.queue` làm tên MessageChannel/broker destination trực tiếp. Dùng **business route key từ allowlist** và mapping tĩnh/trusted registry, authorize producer với operation được phép.

### 27.4. Replay protection

Một signed request có thể bị gửi lại. Signature verification chưa đủ để chống replay nếu eventId/timestamp/nonce không có policy. Cần idempotency/expiry window và application state để bảo vệ effects.

### 27.5. Đừng dùng traceId làm quyền

Trace ID chỉ giúp observability. Nó có thể do external caller tự khai, bị thay đổi hoặc được chia sẻ trong logs. Không dùng traceId làm tenant identity, authorization proof hoặc stable idempotency key.

### 27.6. Dữ liệu cá nhân ở outbound

Nếu domain payload chứa địa chỉ khách hàng, số điện thoại hoặc payment metadata, outbound projection cần **data minimization** theo receiver quyền được biết. Serialization trực tiếp một domain object thường làm contract mở rộng ngoài ý muốn.

## 28. Observability: theo dõi payload và header conversion theo từng hop

Khi cùng một businessEventId đi qua nhiều adapters, tổng số messages vào/ra không đủ để xác định lỗi schema hay header loss. Nên đo riêng từng giai đoạn.

### 28.1. Metrics gợi ý

| Metric | Ý nghĩa | Labels phù hợp |
| --- | --- | --- |
| **adapter_inbound_received_total** | Native messages đến boundary | adapterType, sourceType |
| **adapter_inbound_payload_decode_failed_total** | Lỗi JSON/bytes/schema | adapterType, reason |
| **adapter_inbound_header_mapping_failed_total** | Header thiếu/sai kiểu/mâu thuẫn | adapterType, headerName allowlist |
| **adapter_inbound_auth_failed_total** | Producer/tenant chưa được phép | sourceType, reason |
| **adapter_normalized_total** | Messages có trusted internal contract | operation, schemaVersion |
| **adapter_outbound_encoded_total** | Thành công tạo wire DTO | receiverType, schemaVersion |
| **adapter_outbound_send_failed_total** | Transport send lỗi | receiverType, reasonClass |
| **adapter_outbound_confirmed_total** | Broker/transport xác nhận theo contract | receiverType |
| **adapter_retries_total** | Retry attempts | direction, reasonClass |
| **adapter_duplicate_skipped_total** | Logical duplicate bị phát hiện | operation |
| **adapter_id_conflict_total** | Same identity, different payload | operation |
| **adapter_quarantined_total** | Event cần điều tra | reasonCode |
| **adapter_inbound_lag_seconds** | Trễ từ event time tới ingress | sourceType |
| **adapter_processing_duration_seconds** | Latency từ ingress tới outbound | operation |
| **adapter_queue_backlog** | Work chưa xử lý | channel/queue identifier hữu hạn |

Không dùng eventId, tenantId, orderId, requestId hoặc traceId làm **metric labels tùy ý**: cardinality cao và có nguy cơ rò rỉ thông tin. Dùng structured logs và tracing với access control để tra một event.

### 28.2. Log ví dụ khi normalize thành công

~~~json
{
  "component": "orderInboundMapper",
  "stage": "TRUSTED_NORMALIZATION",
  "sourceType": "HTTP_PARTNER",
  "schemaVersion": 1,
  "eventRef": "evt-order-901",
  "payloadType": "OrderCommand",
  "result": "ACCEPTED"
}
~~~

### 28.3. Log khi header mâu thuẫn

~~~json
{
  "component": "orderInboundMapper",
  "stage": "HEADER_CONSISTENCY",
  "reasonCode": "EVENT_ID_HEADER_PAYLOAD_MISMATCH",
  "sourceType": "JMS_PARTNER",
  "result": "REJECTED"
}
~~~

### 28.4. Log khi gửi outbound

~~~json
{
  "component": "orderOutboundAdapter",
  "stage": "TRANSPORT_SEND",
  "schemaVersion": 1,
  "eventRef": "evt-order-901",
  "targetType": "AMQP",
  "result": "BROKER_ACCEPTED"
}
~~~

Đây là **log do ứng dụng định nghĩa**, không phải format mà Spring Integration tự sinh. Giá trị `BROKER_ACCEPTED` phải có định nghĩa theo protocol; nó không đồng nghĩa business handler của receiver đã hoàn thành.

### 28.5. Các cảnh báo hữu ích

- Tỷ lệ **header mapping mismatch** tăng sau deploy API gateway/proxy.
- Unknown schemaVersion tăng sau khi partner nâng version.
- Inbound accepted tăng nhưng outbound encoded đứng yên.
- Outbound send retries tăng mà broker confirm không tăng.
- File adapter lag tăng hoặc một file được xử lý nhiều lần.
- Duplicate skipped tăng bất thường, có thể do source redelivery hoặc retry storm.
- DLQ/quarantine tồn đọng quá lâu mà không có owner.
- Business effects trùng sau chuyển từ DirectChannel sang async broker.
- Số temporary Gateway replies hết hạn tăng khi network latency cao.

## 29. Runbook: event đúng payload nhưng mất header qua adapter

**Tình huống:** business handler báo thiếu `trustedTenantId` hoặc `businessEventId`, trong khi JSON body hợp lệ và external producer khẳng định đã gửi header.

### Bước 1 — Kiểm tra nguồn và security context

Xác định transport, endpoint, producer và tenant **từ authentication evidence**. Không bắt đầu bằng cách “vá” giá trị `trustedTenantId` bằng HTTP header của client để xử lý tiếp.

### Bước 2 — Kiểm tra raw wire contract có chọn lọc

~~~text
Expected:
  body.schemaVersion = 1
  body.eventId = evt-order-901
  HTTP X-Event-Id / JMS property event_id = evt-order-901

Actual:
  contentType?
  body version?
  header value type?
  duplicate header names?
~~~

Chỉ log metadata an toàn; không dump Authorization/cookie/customer address. Đối với binary broker payload, lưu hash và content type/schema version để điều tra.

### Bước 3 — Kiểm tra MessageConverter

Message payload sau adapter là **String**, **byte[]**, **File**, **OrderWireV1** hay **OrderCommand**? Nếu Service Activator expecting OrderCommand nhưng nhận String JSON, lỗi nằm ở bước conversion, không nhất thiết ở header mapping.

### Bước 4 — Kiểm tra HeaderMapper

Một native header tên **event_id** có được ánh xạ thành **businessEventId** không? Nếu HTTP `X-Event-Id` được normalize lower-case, code có đang lookup tên chính xác như hợp đồng không? Có converter/mapper nào bỏ field hoặc chuyển String thành byte[]/List không?

### Bước 5 — Kiểm tra trusted boundary

Sau khi authenticate/authorize, factory/mapper có gắn **trustedTenantId** từ VerifiedProducer không? Nếu có raw x-tenant-id khác tenant được xác minh, policy là reject hay ignore/audit? Không coi raw claim là nguồn thay thế.

### Bước 6 — Kiểm tra Spring Message sau normalization

Ở ranh giới:

~~~text
payload class = OrderCommand
headers.trustedTenantId = tenant-a
headers.producerId = partner-a
headers.businessEventId = evt-order-901
headers.businessCorrelationKey = order:tenant-a:ORD-901:epoch-3
~~~

Nếu đã đúng, lỗi xảy ra ở hop tiếp theo. Nếu chưa đúng, sửa inbound mapper/authorization/context binding.

### Bước 7 — Kiểm tra Transformer/Router/HeaderFilter

Một Transformer trả Message mới mà không copy selected headers có thể làm mất eventId. Một HeaderFilter có thể được cấu hình quá rộng. Nếu Splitter/Aggregator tạo technical correlationId riêng, đừng vội ghi đè business key chỉ để hai giá trị giống nhau.

### Bước 8 — Kiểm tra outbound projection

Khi gửi ra đối tác, packet nên có đúng wire body + native headers theo contract, không có nội bộ `replyChannel`/`trustedTenantId`. Nếu receiver cần eventId mà outbound chưa gửi, sửa **wire contract/projection** thay vì serialize toàn bộ Spring Message.

### Bước 9 — Kiểm tra retry/ack

Nếu broker đã ack nhưng side effect chưa commit, cần tra inbox/recovery state. Nếu send confirm bị mất, dùng stable business ID và idempotency để retry an toàn. Không tạo UUID mới mỗi lần send attempt.

### Bước 10 — Xác minh sau sửa

Chạy các tests:

1. Inbound mapper từ JSON/native headers đến typed payload.
2. Trusted tenant được lấy từ authenticated context.
3. Header mismatch bị reject.
4. Outbound JSON/headers chỉ chứa allowed fields.
5. Same logical retry không tạo thêm effect.
6. Same ID different payload phát ID_CONFLICT.
7. Real adapter round-trip qua HTTP/JMS/AMQP/file path.
8. Error paths và DLQ/recovery theo topology thực.

## 30. Ma trận kiểm thử toàn bộ contract adapter

| Nhóm | Tình huống | Assertion |
| --- | --- | --- |
| **Inbound payload** | JSON v1 hợp lệ | OrderCommand đúng type/fields |
| **Inbound payload** | Schema v99 | Reject/quarantine |
| **Inbound payload** | Quantity 0 hoặc overflow | Validation fail |
| **Inbound payload** | Unknown enum hoặc wrong type | Contract failure |
| **Encoding** | Invalid UTF-8/large body | Reject sớm |
| **Inbound header** | x-event-id khớp body | businessEventId đúng |
| **Inbound header** | x-event-id khác body | Reject mismatch |
| **Inbound header** | HTTP duplicate case variants | Reject/normalize theo policy |
| **Trust** | Client khai tenant-admin, auth tenant-a | trustedTenantId vẫn từ auth; conflict policy |
| **Trust** | Producer unauthorized | Không dispatch |
| **Spring metadata** | HeaderFilter làm mất businessEventId | Regression test fail |
| **Transformer** | Trả Message mới không giữ selected headers | Test phát hiện |
| **Outbound payload** | OrderAccepted hợp lệ | ACK JSON v1 đúng fields |
| **Outbound header** | Selected native headers | Content-Type, x-event-id, schema-version đúng |
| **Outbound security** | Input có replyChannel/secret | Không xuất qua packet |
| **Protocol** | HTTP header name/case | Real mapper contract test |
| **Protocol** | JMS TextMessage/property | JMS converter+mapper test |
| **Protocol** | AMQP contentType/routing | AMQP converter+header test |
| **Protocol** | TCP frame bị cắt | Parser không ghép sai message |
| **File** | File chưa ghi xong | Polling/filter không xử lý partial |
| **Retry** | Same eventId, same payload | Skip effect hoặc replay receipt |
| **Conflict** | Same ID, different payload | ID_CONFLICT |
| **Multi-tenant** | Same orderId/eventId ở khác tenant | Namespace không trộn |
| **Ack** | Commit success, broker ack lost | Idempotent redelivery |
| **Crash** | Inbox RECEIVED, process restart | Recovery xử lý pending |
| **Timeout** | Outbound confirm unknown | Reconcile/bounded retry |
| **Error** | Invalid schema không tự retry vô hạn | Quarantine |
| **Error** | DB down tạm thời | Retry bounded, state retained |
| **Observability** | Mapping fail trước handler | Error metric/log tại boundary |

### 30.1. Unit test không thay adapter integration test

Một `ObjectMapper.readValue(...)` test có thể chứng minh JSON schema/DTO. Nhưng nó **không kiểm tra** HTTP HeaderMapper/JMS converter/AMQP delivery tags, ACL, ack hoặc retry của listener container.

### 30.2. Integration test trong JVM không thay network test

OrderAdapterHarnessIntegrationTest chạy DirectChannel và in-memory sink, nên hữu ích để bắt lỗi propagation giữa endpoints. Nhưng không có transport thật và process restart. Khi chọn adapter production, phải thêm tests ở đúng boundary giao thức.

### 30.3. Test nhiều producers và nhiều versions

Chạy song song schema v1/v2, producer A/B, tenant A/B, cùng orderId trong hai namespaces; assert business identity không trộn. Nếu inbound là async, không yêu cầu arrival order giống send order trừ khi transport/partition/order contract có bảo đảm.

## 31. Thực hành nâng cao: tự viết một inbound polling adapter

Để phân biệt **Channel Adapter** với một test tự gửi DirectChannel, có thể tạo một inbound adapter custom đọc từ nguồn có giao diện polling. Spring Integration hỗ trợ **@InboundChannelAdapter** trên method cung cấp messages.

### 31.1. Nguồn polling in-memory

~~~java
import java.util.Objects;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;

import org.springframework.integration.annotation.InboundChannelAdapter;
import org.springframework.integration.annotation.Poller;

final class DemoPollingFrameSource {
    private final BlockingQueue<TransportFrame> frames =
            new ArrayBlockingQueue<>(100);

    boolean offer(TransportFrame frame) {
        return frames.offer(Objects.requireNonNull(frame));
    }

    @InboundChannelAdapter(
            channel = "transportFrames",
            poller = @Poller(
                    fixedDelay = "1000",
                    maxMessagesPerPoll = "10"))
    public TransportFrame poll() {
        // null nghĩa là hiện chưa có dữ liệu để phát.
        return frames.poll();
    }
}
~~~

Đăng ký bean `DemoPollingFrameSource` vào một **Spring context thử nghiệm riêng** và giữ lại bốn channels cùng mapper/handler của OrderAdapterHarnessConfig. Poller gọi `poll()`, adapter endpoint tạo Spring Message có payload TransportFrame và gửi vào `transportFrames`. Lần này, test không cần tự gọi `input.send`.

**Lưu ý:** đây là một nguồn in-memory, không bền và không có broker ack. Poller fixedDelay chỉ mô phỏng cách inbound Channel Adapter kéo dữ liệu từ nguồn; một JMS listener hoặc HTTP inbound adapter thật có semantics khác.

### 31.2. Test polling mà không phụ thuộc Thread.sleep vô hạn

Một test có thể:

1. Tạo Spring context với DemoPollingFrameSource.
2. Gọi `source.offer(frame)`.
3. Chờ có giới hạn bằng polling assertion/awaitility hoặc CountDownLatch ở sink.
4. Assert OutboundPacket body/headers.
5. Assert source queue không bị xử lý lặp ngoài ý muốn.
6. Close test context để dừng poller.

Không tạo vòng `while(true)` hoặc `Thread.sleep` vô hạn khiến test treo CI. Với poller interval thực, sử dụng timeout đủ ổn định và test fixture có khả năng reset.

### 31.3. Thêm error channel cho poller

Nếu `OrderInboundMapper` ném exception trong thread poller, lỗi có thể đi qua ErrorMessage và error channel theo cấu hình. Cần thiết kế:

- Chỗ ghi errorCode/failed eventRef an toàn.
- Quy tắc retry/quarantine tùy lỗi schema hay transient.
- Bảo đảm frame không mất sau khi bị poll khỏi in-memory queue.
- Khi sử dụng broker/file thực, chọn ack/rename/transaction strategy theo connector.

**Một BlockingQueue in-memory không cung cấp durable recovery**. Nếu worker crash ngay sau `frames.poll()` nhưng trước khi persist, frame mất. Đừng dùng mẫu này thay một hệ thống queue bền khi dữ liệu quan trọng.

## 32. Bài thực hành: thay adapter nhưng giữ nguyên business flow

**Mục tiêu:** người học thay hai đầu ingress/egress mà **không sửa OrderProcessingActivator hoặc DemoOrderProcessor**.

### 32.1. Ba nguồn đầu vào

**Nguồn A — HTTP:** nhận JSON có X-Event-Id và credential đã xác minh.

**Nguồn B — JMS:** nhận TextMessage cùng property event_id, JMSMessageID và broker-authenticated producer.

**Nguồn C — File/SFTP:** nhận file UTF-8 JSON từ một directory/account đã gắn tenant theo registry.

Cả ba phải chuẩn hóa thành:

~~~text
Message<OrderCommand>
  payload.orderId, sku, quantity, workflowEpoch
  headers.trustedTenantId
  headers.producerId
  headers.businessEventId
  headers.businessCorrelationKey
~~~

### 32.2. Hai đích đầu ra

**Đích 1 — AMQP:** phát ACK JSON v1 cùng selected headers.

**Đích 2 — File:** ghi ACK vào một thư mục cố định bằng basename an toàn `eventId + ".ack.json"`; cần collision/atomic-write policy để retry không overwrite nhầm.

Không gửi nguyên MessageHeaders tới bên nhận. Nếu một destination yêu cầu `businessCorrelationKey`, hãy thêm trường đó vào **wire contract versioned** sau khi đánh giá receiver có quyền biết, không mở toàn bộ header Map.

### 32.3. Công việc cụ thể

1. Công bố schema OrderWireV1 và OrderAckWireV1.
2. Tạo danh sách native headers được nhận/gửi cho từng transport.
3. Cấu hình authentication cho HTTP/JMS/SFTP; bind VerifiedProducer từ nguồn xác minh.
4. Áp dụng payload size/encoding/schema validation.
5. Viết mapper từ wire DTO sang OrderCommand.
6. Sinh trustedTenantId và correlationKey từ verified context.
7. Kiểm tra x-event-id/event_id với body.eventId nếu hợp đồng yêu cầu.
8. Dùng cùng OrderProcessingActivator cho cả ba nguồn.
9. Áp dụng dedup theo tenant+producer+eventId trong durable inbox.
10. Chuyển OrderAccepted sang wire ACK theo receiver schema.
11. Không xuất replyChannel/errorChannel, Authorization hoặc internal risk fields.
12. Thử schema v2 có thêm `lineItems` và triển khai upcaster v1→canonical.
13. Mô phỏng invalid JSON, unauthorized tenant và duplicate header case.
14. Mô phỏng broker redelivery sau commit nhưng trước ACK.
15. Mô phỏng outbound confirm lost và restart outbox publisher.
16. Thêm tracing/metrics tại từng boundary.
17. Thêm runbook cho header mismatch và schema drift.
18. Kiểm tra các test end-to-end có transport thật.

### 32.4. Acceptance criteria

| Tình huống | Mong đợi |
| --- | --- |
| HTTP order hợp lệ | Đúng OrderCommand và tenant đã verify |
| JMS same event qua retry | Không xử lý business effect lần hai |
| SFTP file chứa eventId sai scope | Reject/quarantine |
| HTTP x-tenant-id giả mạo | Không trở thành trustedTenantId |
| Inbound body v99 | Unsupported version, không đoán schema |
| Quantity String nếu schema đòi number | Fail hoặc convert theo policy công bố |
| Transformer trả Message mới thiếu eventId | Integration contract test bắt lỗi |
| Outbound AMQP ACK | Đúng JSON v1 và native headers |
| Outbound File ACK | Tên file an toàn, không traversal |
| Two tenants same orderId | Không trộn identity/ledger |
| Same key different payload | ID_CONFLICT |
| Broker confirm lost | Outbox retry với stable eventId |
| Queue backlog tăng | Alert/backpressure |
| Callback/reply từ producer giả | Reject theo auth |
| DLQ replay sau version upgrade | Parser/upcaster nhận đúng schema |

### 32.5. Tiêu chí kiến trúc

Một business handler chỉ biết **OrderCommand + trusted business context**, không biết:

- HTTP X-Event-Id hay JMS event_id được dùng ở nguồn.
- Payload ban đầu là File, String JSON hay BytesMessage.
- HeaderMapper cụ thể là của JMS, HTTP hay AMQP.
- Outbound ACK đi AMQP hay File.
- Spring MessageHeaders.ID hoặc JMSMessageID của từng attempt.

Nếu phải sửa business handler mỗi lần đổi transport hoặc source header name, Channel Adapter boundary chưa thực hiện tốt nhiệm vụ chuẩn hóa.

## 33. Câu hỏi tự kiểm tra

1. Channel Adapter inbound và outbound khác nhau về chiều dữ liệu như thế nào?
2. Khi nào cần outbound Gateway thay vì outbound Channel Adapter một chiều?
3. Spring MessageHeaders có giống HTTP headers không?
4. MessageConverter và HeaderMapper giải quyết hai vấn đề khác nhau như thế nào?
5. Transformer khác Channel Adapter ở trách nhiệm nào?
6. Vì sao JSON parse thành OrderWireV1 chưa đủ để gắn trustedTenantId?
7. Một client tự khai X-Tenant-Id có được phép trở thành trustedTenantId không?
8. Nếu body.eventId khác x-event-id, nên lấy cái nào?
9. Vì sao producerId và tenantId có thể cần nằm trong idempotency namespace?
10. MessageHeaders.ID có ổn định khi retry/redelivery không?
11. Tại sao không copyHeaders(rawExternalHeaders) vào trusted Message?
12. HeaderReplyChannel có phải dữ liệu wire portable không?
13. Nếu handler trả payload thuần, Spring Integration thường xử lý inbound headers thế nào?
14. Nếu handler trả Message hoàn chỉnh, phải kiểm thử header propagation ra sao?
15. Khi Splitter tạo sequenceNumber, có thể dùng nó một mình làm dedup key không?
16. BusinessCorrelationKey khác JMSCorrelationID và AMQP correlationId ở đâu?
17. Vì sao broker ACK không chứng minh business effect đã commit?
18. Một HTTP 202 Accepted cần cam kết gì về durability?
19. ObjectMapper strict parsing có ưu và nhược điểm nào với schema evolution?
20. Một field v2 có nghĩa khác v1 nhưng giữ type/name có breaking change không?
21. Wire DTO khác domain DTO ở trách nhiệm gì?
22. Vì sao không gửi internalRiskScore ra external ACK?
23. OutboundPacket native headers nên được chọn theo allowlist như thế nào?
24. Nếu AMQP publish confirm mất, có thể kết luận message chưa đến broker không?
25. Khi inbound file adapter đọc file 2 GB, cách an toàn hơn Files.readString là gì?
26. Một filename có thể là căn cứ authorization không?
27. Technical correlation của TCP connection có luôn bằng business eventId không?
28. ErrorMessage.getPayload() thường là gì khi handler lỗi?
29. Router default route có tự bắt exception từ JSON converter không?
30. Vì sao malformed JSON không nên retry vô hạn như lỗi DB tạm thời?
31. Inbox row RECEIVED có chứng minh side effect completed không?
32. Transactional outbox giảm khoảng hở nào giữa DB và broker?
33. Schema v1 trong DLQ phải xử lý ra sao sau khi consumer nâng lên v2?
34. Unit test inbound mapper chứng minh gì mà Spring context test không tự suy ra?
35. Spring context DirectChannel test có chứng minh broker ack/transaction thật không?
36. Metric nào giúp phân biệt payload decoder fail với outbound send fail?
37. Một raw native header tên routingSlip có nên được giữ cho nội bộ không?
38. Vì sao traceId không thể là authorization proof hoặc idempotency key?
39. Khi nào nên chuyển từ header sang versioned wire envelope?
40. Tiêu chí nào chứng minh adapter đã giúp domain service độc lập transport?

## 34. Checklist trước khi triển khai Channel Adapter

### 34.1. Inbound conversion

- Đã xác định inbound adapter là push/listener hay poller, và channel đích có owner rõ.
- Đã công bố wire payload schema, version, required fields và enum/range.
- Đã giới hạn message body size, encoding, parser depth và JSON/XML deserialization policy.
- Đã xác định class payload ở mỗi hop: byte[], String, File, wire DTO hay domain DTO.
- MessageConverter được cấu hình đúng wire format và có test serialize/deserialize.
- Raw native headers được normalize tên/kiểu theo giao thức.
- Có allowlist inbound headers; duplicate/colliding names được xử lý rõ.
- EventId ở body/native header có consistency rule, không chọn tùy tiện khi mismatch.
- Authentication producer được xử lý trước khi tạo trusted context.
- Tenant/order ownership và quyền publish được verify bởi registry/policy.
- Không dùng raw X-Tenant-Id hoặc source filename như proof tenant.
- Trusted Spring Message được tạo với typed domain payload và selected headers.
- Có schema versioning/upcaster/reject policy cho unknown versions.
- Lỗi malformed/untrusted input bị reject/quarantine trước business side effect.

### 34.2. Outbound conversion

- Có wire reply/event DTO riêng, không serialize nguyên domain model.
- Chọn đúng receiver contract version và destination được phép.
- HeaderMapper chỉ gửi native properties được allowlist.
- Không xuất replyChannel, errorChannel, routingSlip, Authorization token hoặc internal fields.
- Content-Type/encoding/schemaVersion nhất quán với bytes thực gửi.
- EventId trong wire body/header đồng nhất theo contract.
- Có policy cho send failure, unknown confirm, DLQ/retry và outbox.
- Đã phân biệt transport accepted với business completed.
- Nếu cần business reply, có Gateway hoặc completion event/status API tương ứng.

### 34.3. Spring Integration topology

- Các MessageChannels có tên/owner rõ, không vô tình gắn hai competing consumers vào một DirectChannel.
- Transformer chỉ thực hiện conversion thích hợp, không âm thầm thay business identity.
- Các endpoint đã kiểm tra propagation của tenantId/eventId/correlation qua Router/Transformer.
- HeaderFilter không loại những metadata nghiệp vụ còn cần cho downstream.
- Splitter/Aggregator có technical group scope và release policy riêng.
- Gateway replyChannel giữ đúng request/reply lifecycle; không serialize live channels ra remote.
- ExecutorChannel/QueueChannel/poller có bounded capacity và error handling phù hợp.
- ErrorMessage, errorChannel và durable DLQ/quarantine được phân biệt rõ.

### 34.4. Reliability, transaction và retry

- BusinessEventId giữ ổn định cho cùng logical event sau redelivery.
- Dedup key có scope tenant/producer/operation đúng contract.
- Same-key/different-payload được xem là conflict.
- Nếu có side effect, sử dụng durable inbox/idempotency ledger.
- Có recovery khi crash giữa receive, persist, dispatch và commit.
- Outbound event có outbox hoặc cơ chế tránh mất giữa DB commit và broker publication.
- Retry bounded, có backoff và phân loại permanent/transient failures.
- Unknown transport outcome được reconcile thay vì tạo operation ID mới.
- File/stream adapters có atomic read/write hoặc rename/lock policy thích hợp.
- Replay DLQ có kiểm soát về schema version và duplicate effect.

### 34.5. Security, privacy và observability

- Nguồn producer, tenant và destination được xác thực/authorize.
- Không cho external headers điều khiển arbitrary internal channel, routingSlip hoặc errorChannel.
- Không dùng untrusted traceRef làm authorization/idempotency.
- Lọc/separate PII, tokens và internal context khỏi outbound payload.
- Log theo stage/reasonCode, không dump toàn bộ headers/body nhạy cảm.
- Metric labels có cardinality hữu hạn và bảo vệ dữ liệu.
- Có dashboard inbound failures, header mismatch, outbound failures, backlog và retry.
- Có runbook cho schema drift, header loss và unknown ACK.

### 34.6. Tests và deploy

- Unit tests cho wire DTO, mapper, header allowlist, identity và encoding.
- Unit tests cho outbound projection không leak fields.
- Spring context test thật đi qua các channels/endpoints.
- Negative tests cho header mismatch, producer giả, unknown schema và wrong types.
- Tests cho duplicate, ID_CONFLICT, multi-tenant namespace và timeout.
- Adapter integration tests với HTTP/JMS/AMQP/TCP/File thật nếu sử dụng.
- Thử process restart/recovery với durable inbox/outbox.
- Version compatibility tests cho v1/v2 và DLQ replay.
- Đã kiểm tra converter/header mapper theo đúng phiên bản Spring Integration đang triển khai.

## 35. Kết luận

**Adapter chuyển đổi payload và header** là việc thiết kế **một ranh giới rõ ràng** giữa protocol bên ngoài và hệ thống Spring Integration, không chỉ là parse JSON hoặc copy một Map headers.

~~~text
External system:
  Native payload + native transport headers
      |
      v
Inbound Channel Adapter:
  Authenticate source
  Decode/validate versioned wire payload
  Normalize/verify selected native metadata
  Build trusted Spring Message
      |
      v
Message<OrderCommand>:
  typed payload
  trustedTenantId / producerId
  businessEventId / businessCorrelationKey
      |
      v
Router / Transformer / Service Activator
      |
      v
Message<OrderAccepted>
      |
      v
Outbound Channel Adapter:
  Check identity and output contract
  Project to wire DTO
  Serialize payload + allowlisted native headers
  Send with retry/ack/recovery policy
      |
      v
External system
~~~

Một thiết kế tốt đảm bảo **business handlers chỉ thấy typed payload và verified context**, không phụ thuộc HTTP X-Event-Id, JMS properties, AMQP delivery tags hay tên file đầu vào. Đồng thời outbound adapter chỉ xuất dữ liệu đối tác được phép nhận, tránh làm lộ Spring MessageHeaders hoặc control channels.

Trong hệ thống có Router, Filter, Transformer, Splitter, Aggregator, Messaging Gateway, retry, error channel và correlation, hãy kiểm thử **cả payload lẫn headers ở từng boundary**. Thêm versioning, idempotency, authorization và observability để việc thay một adapter không làm hỏng business identity hoặc lặp lại side effect khi timeout/redelivery.

## Tài liệu tham khảo

- [Enterprise Integration Patterns — Channel Adapter](https://www.enterpriseintegrationpatterns.com/patterns/messaging/ChannelAdapter.html): bridge giữa ứng dụng/giao thức và messaging channel.
- [Enterprise Integration Patterns — Message Translator](https://www.enterpriseintegrationpatterns.com/patterns/messaging/MessageTranslator.html): chuyển biểu diễn message giữa các hệ thống.
- [Enterprise Integration Patterns — Messaging Gateway](https://www.enterpriseintegrationpatterns.com/patterns/messaging/MessagingGateway.html): request/reply phía application và khác biệt với adapter một chiều.
- [Spring Integration Reference](https://docs.spring.io/spring-integration/reference/): tổng quan adapters, gateways, messaging, converters và error handling.
- [Spring Integration Reference — Message](https://docs.spring.io/spring-integration/reference/message.html): Spring Message và MessageHeaders.
- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html): DirectChannel, QueueChannel, ExecutorChannel, dispatch/polling semantics.
- [Spring Integration Reference — Transformer](https://docs.spring.io/spring-integration/reference/transformer.html): payload transformation và header propagation.
- [Spring Integration Reference — Service Activator](https://docs.spring.io/spring-integration/reference/service-activator.html): mapping từ Message sang Java method arguments.
- [Spring Integration Reference — HTTP](https://docs.spring.io/spring-integration/reference/http.html): HTTP inbound/outbound adapters, gateways, converters và headers.
- [Spring Integration Reference — JMS](https://docs.spring.io/spring-integration/reference/jms.html): JMS adapters/gateways, header mapping và acknowledgments.
- [Spring Integration Reference — AMQP](https://docs.spring.io/spring-integration/reference/amqp.html): AMQP adapters/gateways, properties, converter và reply behavior.
- [Spring Integration Reference — File](https://docs.spring.io/spring-integration/reference/file.html): file adapters, filters và outbound file handling.
- [Spring Integration Reference — SFTP](https://docs.spring.io/spring-integration/reference/sftp.html): remote file adapters và source metadata.
- [Spring Integration Reference — TCP](https://docs.spring.io/spring-integration/reference/ip.html): TCP/IP adapters, connection metadata và serialization.
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): ErrorMessage, errorChannel và đồng bộ/bất đồng bộ.
- [Spring Integration Reference — Idempotent Receiver](https://docs.spring.io/spring-integration/reference/handler-advice/idempotent-receiver.html): duplicate detection và idempotency advice.
- [Spring Framework — Testing](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework.html): Spring TestContext Framework cho integration tests.
