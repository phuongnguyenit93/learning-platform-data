# Bridge giữa hai broker

**Chương:** Design patterns  
**Bài học:** Bridge giữa hai broker  
**Module:** Spring Integration Adapters (`SPRING_INTEGRATION_ADAPTERS`)  
**Ngữ cảnh:** Kết nối các hệ thống ngoài bằng inbound/outbound adapter, gateway, poller và `MessageChannel`; tập trung vào cầu nối JMS, AMQP/RabbitMQ và Kafka, đồng thời liên hệ với HTTP, File/SFTP và JDBC khi xây dựng hoặc vận hành một integration flow.

> **Ý chính:** Bridge chuyển thông điệp từ **broker nguồn** sang **broker đích**, nhưng không đồng nghĩa với "nối hai queue" bằng một dòng cấu hình. Hai broker có **định dạng, cơ chế xác nhận, transaction, ordering, routing, retry và vòng đời kết nối khác nhau**. Một bridge tin cậy phải có **hợp đồng message**, **ranh giới trách nhiệm rõ ràng**, **khả năng phục hồi khi crash** và **bằng chứng message đã được bàn giao**.

## 1. Bài toán: vì sao phải bridge hai broker?

Một hệ thống lâu năm dùng **JMS** để phát sự kiện tạo đơn hàng. Hệ thống mới nhận sự kiện qua **RabbitMQ**, còn nền tảng analytics xử lý bằng **Kafka**. Trong giai đoạn chuyển đổi, doanh nghiệp không thể thay mọi producer và consumer cùng lúc.

Một **broker-to-broker bridge** là thành phần tiêu thụ message từ bên A, chuyển đổi hợp đồng nếu cần, rồi phát message tương ứng sang bên B.

~~~mermaid
flowchart LR
    OLD["Legacy Order Service"] --> JMS["JMS broker / orders.queue"]
    JMS --> SI["Spring Integration Bridge"]
    SI --> AMQP["RabbitMQ / orders.exchange"]
    AMQP --> NEW["Fulfillment Service"]
    SI -.-> STORE["Outbox / Failure Store"]
    STORE -.-> SI
    SI --> OBS["Metrics / Tracing / Audit"]
~~~

Những mục tiêu điển hình:

- **Migration:** Chuyển dần consumer từ một broker sang broker khác.
- **Interoperability:** Kết nối hệ thống JMS với RabbitMQ hoặc Kafka mà không sửa tất cả producer.
- **Event distribution:** Phát cùng một event nghiệp vụ sang hệ thống analytics hoặc ứng dụng khác.
- **Boundary isolation:** Tách hai miền mạng, tenant, tổ chức hoặc chính sách bảo mật.
- **Protocol adaptation:** Đổi metadata, routing key, partition key, schema và payload.
- **Operational decoupling:** Hệ thống nguồn không phải chờ hệ thống đích triển khai cùng tốc độ.

Bridge **không** được dùng như một cách tự động khắc phục mọi bất đồng về dữ liệu. Nếu nguồn phát lệnh `CREATE_ORDER` còn đích chỉ hiểu event `ORDER_CREATED`, cần quyết định rõ **lệnh đang được chuyển tiếp** hay **một sự kiện đã xảy ra**. Sai ý nghĩa message là lỗi hợp đồng nghiệp vụ, không phải lỗi broker.

### 1.1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **Messaging Bridge**, `BridgeHandler`, `MessageChannel`, inbound adapter, outbound adapter và gateway.
2. Thiết kế bridge JMS ↔ AMQP hoặc Kafka ↔ JMS/Kafka ↔ RabbitMQ với sơ đồ ranh giới chính xác.
3. Định nghĩa hợp đồng payload, message key, headers, correlation, schema version và quy tắc chuyển đổi.
4. Giải thích chính xác **acknowledgment**, **publish confirmation**, **transaction**, **redelivery** và **delivery guarantee**.
5. Chỉ ra những crash windows gây message loss hoặc duplicate và biết khi nào cần **inbox/outbox**.
6. Thiết kế retry, error channel, dead-letter queue/topic, idempotency và replay có kiểm soát.
7. Kiểm thử với broker thật, đo throughput/lag và xây runbook vận hành.

## 2. Bridge pattern là gì, và không phải gì?

Trong **Enterprise Integration Patterns (EIP)**, bridge kết nối các hệ thống messaging có thể có công nghệ và quy ước khác nhau. Spring Integration triển khai các mẫu EIP thông qua `Message`, `MessageChannel`, adapters, gateways, transformers, routers, filters và error flows.

Nhưng từ "bridge" được dùng ở **ba cấp khác nhau**:

| Khái niệm | Vai trò | Ví dụ |
| --- | --- | --- |
| **Channel bridge / BridgeHandler** | Chuyển Spring Message giữa các channel **bên trong** một ứng dụng | `inputChannel -> bridge -> outputChannel` |
| **Broker-to-broker bridge** | Tiêu thụ từ broker A và phát tới broker B | JMS queue → RabbitMQ exchange |
| **Broker-native federation/connector** | Cơ chế broker/connector quản lý replication hoặc integration | Kafka Connect, RabbitMQ federation/shovel theo nhu cầu |

`BridgeHandler` trong Spring Integration **không tự mở connection tới hai broker**. Broker bridge thường cần **inbound adapter/gateway** ở một đầu, `MessageChannel` và xử lý contract ở giữa, **outbound adapter/gateway** ở đầu kia.

### 2.1. Adapter hay gateway?

| Thành phần | Trường hợp phù hợp |
| --- | --- |
| **Inbound channel adapter** | Nhận message/event one-way từ nguồn, phát vào `MessageChannel` |
| **Message-driven inbound adapter** | Nguồn broker đẩy message tới listener thay vì application poll định kỳ |
| **Outbound channel adapter** | Gửi message one-way tới broker đích |
| **Gateway** | Request-reply: gửi yêu cầu và chờ phản hồi theo hợp đồng |
| **MessageChannel** | Truyền message nội bộ; có thể đồng bộ hoặc bất đồng bộ tùy loại |
| **Transformer** | Đổi payload/headers giữa hợp đồng nguồn và hợp đồng đích |
| **Router** | Chọn destination, topic, exchange hoặc tenant |
| **Filter** | Chặn thông điệp không hợp lệ hoặc không thuộc phạm vi |

Không nên thay một **event bridge một chiều** bằng request-reply gateway chỉ vì muốn "chờ broker báo thành công": publish confirmation không phải **business reply** từ consumer. Ngược lại, nếu source là yêu cầu RPC cần response, thiết kế bridge phải xử lý **reply channel, correlation và timeout** chứ không chỉ forward rồi kết thúc.

### 2.2. Chuyển tải khác chuyển ngữ nghĩa

**Pass-through bridge:** Giữ nguyên payload theo định dạng ổn định, chỉ chuyển protocol và headers cần thiết.  
**Transforming bridge:** Chuẩn hóa schema, lọc PII, đổi routing key, phiên bản contract hoặc enrich metadata.

Một bridge chủ động có thể từ chối message không hợp lệ và đưa vào **quarantine**, thay vì cố đoán dữ liệu còn thiếu.

## 3. Kiến trúc tổng thể của một bridge

~~~mermaid
flowchart TD
    SA["Source broker A"] --> IA["Inbound adapter / listener"]
    IA --> CH["MessageChannel"]
    CH --> VAL["Validate + normalize contract"]
    VAL --> ID["Idempotency / inbox nếu cần"]
    ID --> MAP["Transform / route / enrich"]
    MAP --> OA["Outbound adapter / publisher"]
    OA --> TA["Target broker B"]
    OA --> CONF{"Publish confirm / transaction result"}
    CONF -->|Success theo contract| ACK["Source ACK hoặc commit theo chính sách"]
    CONF -->|Failure / timeout| ERR["Retry, recover, reconcile"]
    ERR --> DLQ["Durable failure store / DLQ / quarantine"]
    DLQ --> REPLAY["Replay có kiểm soát"]
    REPLAY --> MAP
    VAL -->|Invalid| DLQ
~~~

Sơ đồ trên là **mô hình trách nhiệm logic**, không hàm ý rằng mọi adapter tự giữ source message mở đến publish confirm. Với bridge bền vững theo kiến trúc **outbox**, nguồn có thể được ACK sau khi message đã được lưu an toàn ở inbox/outbox; việc phát sang broker B diễn ra sau đó bởi worker khác.

### 3.1. Phân định các ranh giới

Bridge cắt qua ít nhất ba miền:

1. **Source domain:** Broker A, consumer group/queue, offset hoặc session, authentication và quyền đọc.
2. **Application domain:** Spring Message, channels, mapping, retry, state store, lifecycle và observability.
3. **Target domain:** Broker B, producer session, routing, key/partition, publish confirm và quyền ghi.

Khi mất kết nối, các miền có thể **thất bại độc lập**. JMS transaction của source không mặc nhiên bao trùm RabbitMQ publish hoặc Kafka producer transaction.

### 3.2. Một bridge tốt phải có owner rõ

Quy định:

- Ai sở hữu schema và phiên bản event?
- Ai vận hành bridge, broker A và broker B?
- Ai quyết định retention, DLQ, replay và tỷ lệ xử lý?
- Khi một nguồn đã ACK nhưng đích chưa nhận, nơi nào **chịu trách nhiệm bền vững**?
- Ai có quyền đổi routing key, trust, ACL hoặc cấu hình consumer group?
- Ai xử lý sự cố duplicate, mất thứ tự và event không hợp lệ?

Thiếu owner biến bridge thành một thành phần "đứng giữa" mà không ai biết message cuối cùng đang ở đâu.

## 4. So sánh JMS, AMQP/RabbitMQ và Kafka

| Khía cạnh | JMS / broker tương thích | AMQP / RabbitMQ | Apache Kafka |
| --- | --- | --- | --- |
| Mô hình phổ biến | Queue và topic theo JMS API/provider | Exchange định tuyến tới queue; consumer đọc queue | Topic chia partitions, consumer groups đọc offsets |
| Identity message | `JMSMessageID`, `JMSCorrelationID` và properties | AMQP properties/headers, messageId/correlationId | Topic/partition/offset, record key và headers |
| Xác nhận tiêu thụ | JMS session transaction hoặc acknowledgment mode | Consumer ACK/NACK/reject, requeue theo config | Offset commit/ack theo consumer/container |
| Xác nhận publish | JMS send/session commit theo provider/config | Publisher confirms/returns khi cấu hình phù hợp | Producer send acknowledgment/future theo `acks` và settings |
| Thứ tự | Tùy queue, session, consumer concurrency/provider | Tùy queue và consumer topology, requeue/redelivery | Thứ tự record trong **một partition** |
| Tính bền | Durable queue/topic/message tùy config | Durable exchange/queue và persistent message phù hợp | Retention, replication, producer durability configs |
| Dead-letter | Provider DLQ/redelivery policy | DLX, dead-letter routing, TTL/policy | DLT theo ứng dụng/framework hoặc connector |
| Replay | Thường qua DLQ/source logic | Re-publish từ DLQ/store theo policy | Consumer seek/reset offset hoặc republish, cần nghiệp vụ kiểm soát |
| Transaction | JMS transacted session, tùy provider | Channel transaction và broker semantics | Producer transaction/idempotent producer theo phạm vi Kafka |

**Lưu ý:** Bảng mô tả mô hình tổng quát, **không khẳng định mặc định** của mọi broker hoặc bản Spring. JMS là một API và contract; behavior thực còn phụ thuộc ActiveMQ Artemis, IBM MQ hoặc provider khác.

### 4.1. Kafka không phải hàng đợi JMS theo nghĩa một-một

Trong Kafka, một record có thể được **nhiều consumer groups** đọc độc lập. Offset lưu vị trí của group; việc đọc/commit offset không xóa record khỏi topic. Một bridge Kafka → JMS muốn tránh publish trùng phải quản lý **source record key, consumer group, offset commit và idempotency ở broker đích**.

### 4.2. RabbitMQ exchange không phải queue

Outbound adapter thường publish tới **exchange và routing key**. Exchange có thể định tuyến tới nhiều queue hoặc không queue nào. **Producer call không lỗi không có nghĩa đã có consumer nhận message**. Cần kiểm tra exchange/queue bindings, mandatory returns, publisher confirms và topology.

### 4.3. JMS topic subscription có vòng đời riêng

Khi bridge dùng JMS topic thay vì queue, cần xác định client ID, durable subscription, shared subscription và provider semantics; restart/đổi subscription ID có thể làm **đọc lại hoặc bỏ lỡ** message tùy cấu hình. Đừng áp mô hình queue trực tiếp cho topic subscriber.

## 5. Hợp đồng message đi xuyên hai broker

Spring Integration message có **payload và headers**, còn broker nguồn/đích có metadata riêng. Bridge phải xây **canonical message contract** để không làm mất thông tin cần cho business và operations.

### 5.1. Envelope minh họa

~~~json
{
  "eventId": "evt-T42-971-1",
  "eventType": "ORDER_CREATED",
  "schemaVersion": 2,
  "producer": "legacy-order-service",
  "occurredAt": "2026-11-23T08:00:00Z",
  "tenantId": "T42",
  "aggregateId": "ORD-971",
  "correlationId": "trace-84021",
  "causationId": "cmd-T42-971",
  "payload": {
    "orderId": "ORD-971",
    "status": "CREATED"
  }
}
~~~

Đây là **định dạng ứng dụng minh họa**, không phải payload mà Spring Integration tự sinh. Dữ liệu nghiệp vụ thực phải tuân thủ phân loại nhạy cảm và schema compatibility.

### 5.2. Các trường nên giữ và tác dụng

| Trường | Ý nghĩa | Quy tắc chuyển tiếp |
| --- | --- | --- |
| `eventId` hoặc `operationId` | Định danh ổn định của event/operation | **Không đổi ở mỗi redelivery/replay** |
| `eventType` | Mô tả nghiệp vụ | Không tùy tiện biến command thành fact event |
| `schemaVersion` | Contract để parse | Validate trước khi publish |
| `tenantId` | Phạm vi dữ liệu | Bảo vệ cross-tenant, không dùng vô điều kiện từ header |
| `aggregateId` | Cơ sở ordering/partition | Giữ ổn định qua migration |
| `correlationId` | Nối các bước xử lý | Preserve hoặc map rõ giữa broker headers |
| `causationId` | Nguyên nhân tạo event | Preserve phục vụ trace nghiệp vụ |
| `occurredAt` | Thời điểm event gốc | Không thay bằng thời gian bridge nhận |
| `receivedAt`/`bridgedAt` | Quan sát độ trễ | Do bridge thêm dưới tên khác |
| `sourceRecordRef` | JMS ID, Rabbit delivery info, Kafka offset | Audit; **không** dùng làm ID nghiệp vụ nếu republish |
| `traceparent` | Distributed trace nếu hệ thống hỗ trợ | Kiểm soát header propagation và trust |

Nếu có payload chứa PII, bridge không nên tạo bản sao vô hạn trong log, DLQ hoặc tracing. Dùng reference và cơ chế mã hóa/phân quyền phù hợp.

### 5.3. Header mapping không phải copy-all

JMS, AMQP và Kafka có các loại header và quy tắc serializer khác nhau. Không phải header nào cũng chuyển nguyên trạng. Ví dụ:

- `JMSCorrelationID` cần được ánh xạ sang header/event field mà consumer RabbitMQ/Kafka hiểu.
- JMS `JMSReplyTo` là **Destination** trong source domain; không tự có địa chỉ hợp lệ ở target broker.
- RabbitMQ `deliveryTag` là thông tin delivery thuộc channel nguồn, không phải ID có thể dùng ở broker đích.
- Kafka `offset` thuộc partition nguồn, **không được copy** thành offset ghi mới do Kafka đích tự quyết định.
- Spring Integration `MessageHeaders.ID` và `TIMESTAMP` được framework quản lý, không nên dùng thay business `eventId`.
- Header chứa đối tượng Java không phù hợp broker serializer/consumer khác.

**Đề xuất:** Allowlist các metadata cần thiết, xác định kiểu dữ liệu rõ ràng (string, integer, bytes...) và dùng field riêng cho reference transport gốc.

## 6. MessageChannel: ranh giới thread và transaction

Spring Integration bridge không nên chọn `MessageChannel` chỉ vì tên nghe phù hợp. Loại channel quyết định **thời điểm inbound handler trả về** và **exception có lan ngược** hay không.

| Channel | Đặc điểm | Tác động đến bridge |
| --- | --- | --- |
| `DirectChannel` | Dispatch thường đồng bộ cùng thread | Outbound error có thể lan tới source listener |
| `ExecutorChannel` | Dispatch qua executor/thread khác | Source có thể trả về trước target publish; cần durable handoff |
| `QueueChannel` in-memory | Giữ message trong hàng đợi nội bộ | Không tự bảo đảm bền qua restart |
| Persistent queue-backed channel | Có backing MessageStore theo cấu hình | Cần xét store durability, poller và ack source |
| `PublishSubscribeChannel` | Fan-out tới nhiều subscribers | Một source message có thể sinh nhiều side effects độc lập |
| `FluxMessageChannel`/reactive | Ranh giới reactive/backpressure theo cơ chế | Lỗi và lifecycle khác flow đồng bộ; cần test riêng |

### 6.1. Tại sao `DirectChannel` thường dễ lý luận hơn?

~~~text
JMS listener thread
    -> DirectChannel
    -> Transform
    -> Rabbit publisher
    -> return/throw
    -> JMS listener quyết định ACK/rollback theo config
~~~

Với `DirectChannel`, lỗi publish đồng bộ có cơ hội lan về listener. Tuy nhiên **publish method return không mặc nhiên bằng durable broker acceptance**; ví dụ RabbitMQ cần publisher confirm/return semantics đúng.

### 6.2. Tại sao một `ExecutorChannel` có thể tạo nguy cơ mất message?

~~~text
JMS listener -> ExecutorChannel.send() returns quickly
JMS listener ACKs
Worker thread later tries Rabbit publish -> fails
No durable handoff -> message can be lost
~~~

Nếu bridge cần async decoupling, nên dùng **persistent handoff** (inbox/outbox hoặc message store được quản trị) thay vì chỉ tách thread trong bộ nhớ.

### 6.3. Fan-out có thêm failure states

Một message phải chuyển tới **RabbitMQ và Kafka**. Rabbit publish thành công nhưng Kafka publish thất bại. Một cờ `forwarded=true` chung sẽ không mô tả đúng trạng thái từng destination.

Mỗi destination cần:

- Subscription/routing contract riêng.
- Delivery state riêng (`PENDING`, `SENT`, `FAILED`).
- Retry và idempotency key phù hợp.
- Theo dõi backlog/lag độc lập.

## 7. Một bridge đơn giản JMS → RabbitMQ

Mục tiêu ví dụ: đọc từ JMS queue `legacy.orders` rồi publish một-way sang RabbitMQ exchange `orders.bridge` với routing key `orders.in`.

### 7.1. Sơ đồ

~~~mermaid
flowchart LR
    JQ["JMS queue: legacy.orders"] --> JIA["Jms message-driven inbound adapter"]
    JIA --> MC["Spring MessageChannel"]
    MC --> AO["Amqp outbound adapter"]
    AO --> EX["Rabbit exchange: orders.bridge"]
    EX --> RQ["Rabbit queue: orders.in"]
    RQ --> C["Consumer mới"]
~~~

### 7.2. Spring Integration Java DSL minh họa

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.amqp.core.AmqpTemplate;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.amqp.dsl.Amqp;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jms.dsl.Jms;

@Configuration
class SimpleJmsToRabbitBridgeConfig {

    @Bean
    IntegrationFlow jmsToRabbitBridge(
            ConnectionFactory sourceJmsConnectionFactory,
            AmqpTemplate targetRabbitTemplate) {

        return IntegrationFlow
                .from(Jms.messageDrivenChannelAdapter(sourceJmsConnectionFactory)
                        .destination("legacy.orders"))
                .handle(Amqp.outboundAdapter(targetRabbitTemplate)
                        .exchangeName("orders.bridge")
                        .routingKey("orders.in"))
                .get();
    }
}
~~~

**Đây là một minh họa wiring**, không phải cấu hình production hoàn chỉnh. Cần đối chiếu API/overloads với **Spring Integration BOM** của dự án, khai báo `ConnectionFactory`, AMQP template, topology queue/exchange/binding, converters và listener container settings.

### 7.3. Cấu hình còn thiếu nếu muốn reliability

Ví dụ trên **không tự**:

1. Tạo durable Rabbit exchange/queue/binding.
2. Cấu hình publisher confirm/return và chờ xác nhận phù hợp.
3. Bao transaction nguồn JMS và publish Rabbit vào một giao dịch phân tán.
4. Đảm bảo bên đích không nhận duplicate sau crash.
5. Chuyển JMS header tùy ý thành AMQP header hợp lệ.
6. Quyết định retry, DLQ hoặc quarantine khi lỗi.
7. Bảo vệ authentication, TLS, ACL, payload serialization.
8. Tự dừng intake khi RabbitMQ outage kéo dài.

Không đánh dấu **delivered-to-target** chỉ vì flow Java DSL gọi xong và chưa ném exception.

## 8. Transforming bridge: chuẩn hóa schema trước publish

Một schema canonical giúp tách định dạng source khỏi destination.

~~~text
JMS bytes/TextMessage
   -> message converter
   -> validate schema/source attributes
   -> canonical EventEnvelope
   -> serialize target JSON/Avro/Protobuf
   -> outbound AMQP/Kafka
~~~

### 8.1. Ví dụ Java model

~~~java
import java.time.Instant;
import java.util.Map;

public record BridgeEvent(
        String eventId,
        String eventType,
        int schemaVersion,
        String tenantId,
        String aggregateId,
        String correlationId,
        Instant occurredAt,
        Map<String, Object> payload) {}
~~~

**Mẫu mapping nghiệp vụ minh họa:**

~~~java
BridgeEvent normalize(SourceOrderCreated source) {
    if (source.eventId() == null || source.eventId().isBlank()) {
        throw new InvalidSourceContractException("Missing stable eventId");
    }
    return new BridgeEvent(
            source.eventId(),
            "ORDER_CREATED",
            2,
            source.tenantId(),
            source.orderId(),
            source.correlationId(),
            source.occurredAt(),
            Map.of("orderId", source.orderId(), "status", "CREATED")
    );
}
~~~

`SourceOrderCreated` và `InvalidSourceContractException` là **kiểu do ứng dụng định nghĩa**, không phải API Spring. Mapping phải xử lý `null`, schema evolution, timezone, precision số, encoding, validation và dữ liệu nhạy cảm.

### 8.2. Nguyên tắc schema evolution

- **Consumer compatibility:** Thêm field optional có mặc định và quy tắc nâng version.
- **Breaking change:** Có version/new topic/route hoặc migration plan.
- **Unknown fields:** Quy định consumer bỏ qua hay reject.
- **Serialization:** Không dùng Java native serialization chỉ vì cả hai đầu viết Java.
- **Schema registry:** Nếu dùng Avro/Protobuf, xác định registry, subject naming và quyền truy cập.
- **Poison message:** Invalid schema phải vào quarantine/DLQ có owner, không retry network vô hạn.

### 8.3. Loại bỏ metadata không nên lan truyền

Không forward:

- Authentication headers hoặc credential nội bộ của broker nguồn.
- `replyTo`/temporary destination mà target broker không thể dùng.
- Object header chỉ có nghĩa trong JVM.
- Debug stack trace hoặc payload thô nhạy cảm.
- Source delivery tag/consumer session object.

Thay bằng business correlation, provenance và schema metadata đã được chuẩn hóa.

## 9. Delivery guarantees: lời hứa nào là hợp lý?

Ba mức thường được dùng:

| Mức | Ý nghĩa nghiệp vụ | Đánh đổi |
| --- | --- | --- |
| **At-most-once** | Có thể mất message, nhưng hạn chế gửi lại | Thường tránh duplicate bằng cách chấp nhận loss |
| **At-least-once** | Có thể gửi lại khi chưa chắc thành công | Cần idempotent consumer |
| **Exactly-once effect** | Một thao tác nghiệp vụ có một hiệu ứng cuối cùng | Cần phạm vi bảo đảm rõ, unique key/transaction hoặc contract end-to-end |

**Quan trọng:** Không tuyên bố "JMS → RabbitMQ/Kafka exactly-once" chỉ vì mỗi broker hỗ trợ transaction hoặc acknowledgments. Khi đi qua **hai broker khác loại**, thường không có một commit nguyên tử được cả hai mặc nhiên chia sẻ.

### 9.1. Source ACK và target publish confirm

Bridge cần biết hai thông tin khác nhau:

- **Source ACK/commit:** Broker A có còn trách nhiệm phát lại message hay không?
- **Target publish confirm/commit:** Broker B đã nhận message theo guarantee mà producer cấu hình hay chưa?

Nếu source ACK **trước** khi target được bàn giao bền: có nguy cơ mất message. Nếu target nhận bền **trước** source ACK: crash có thể gây redelivery và **duplicate** ở target.

### 9.2. Confirmation không đồng nghĩa consumer business success

Rabbit publisher confirm hoặc Kafka producer acknowledgment chỉ nói broker/partition leader (và replicas theo policy) đã xử lý publish theo contract. Nó **không** chứng minh một consumer đã cập nhật database hoặc gửi email thành công.

Nếu business cần response cuối, phải thiết kế **reply/event/correlation hoặc workflow orchestration riêng**, không tráo nghĩa publisher confirmation thành business completion.

## 10. Bảng crash windows quan trọng

| Thời điểm crash | Tình trạng có thể xảy ra | Hành động cần thiết |
| --- | --- | --- |
| Trước khi consume | Source còn message | Đọc lại bình thường |
| Sau consume nhưng trước persist/target publish | Chưa có bản sao ở target | Không ACK source trước handoff an toàn |
| Sau target publish, trước nhận confirm | Target **có thể** đã nhận | Đánh dấu `OUTCOME_UNKNOWN`, dùng idempotency/reconciliation |
| Sau confirm target, trước ACK source | Source redeliver → target có duplicate | Giữ event ID để dedupe |
| Sau ACK source, trước ghi audit/outbox state | Không chắc trạng thái bridge | Thiết kế durable state/correlation hoặc reconcile |
| Sau persist outbox, trước ACK source | Source có thể redeliver, outbox đã có | Unique inbox key/upsert, ACK sau xác minh |
| Sau target confirm, trước mark outbox `SENT` | Outbox worker có thể publish lại | Idempotent destination/consumer |
| Trong lúc chuyển vào DLQ | Failure record có thể chưa được lưu | Không fake-success, giữ source hoặc dùng store dự phòng |

### 10.1. "Publish method returned" là điều kiện yếu

`RabbitTemplate.convertAndSend(...)` hoặc `KafkaTemplate.send(...)` trả về theo semantics riêng. Với Kafka, `send` thường **bất đồng bộ**, cần quan sát completion/future; với RabbitMQ, publisher confirm có thể xử lý riêng và route đến exchange không bảo đảm đến queue nếu bindings sai.

Test bridge phải dùng **broker integration tests**, theo dõi confirm/returns và kiểm tra record có mặt ở target, thay vì chỉ dùng mock verify `send` đã được gọi.

## 11. Thiết kế A: bridge trực tiếp

~~~text
Source broker -> Spring Integration handler -> Target broker
     |                                        |
     +----------- ACK/rollback policy <-------+
~~~

**Ưu điểm:** Ít thành phần, latency thấp, dễ hiểu cho throughput vừa phải.  
**Nhược điểm:** Giữ source consumer/thread trong lúc kết nối target; khó có atomic cross-broker commit; khi target outage dễ tăng unacked/redelivery/backlog.

Điều kiện nên có:

1. Consumer source có transaction/ack behavior được kiểm chứng.
2. Target publish có confirmation và timeout phù hợp.
3. Khi target publish chưa đạt guarantee, source **không ACK** hoặc lưu failure **bền vững trước ACK**.
4. Target consumer idempotent, vì duplicate vẫn có thể xảy ra.
5. Retry hữu hạn, backoff, DLQ/quarantine rõ.
6. Không đặt async in-memory channel làm ranh giới "handoff an toàn".

### 11.1. Khi nào bridge trực tiếp đủ dùng?

Khi throughput vừa phải, downtime chấp nhận được, broker source có khả năng buffer/redelivery an toàn, message không quá nhạy cảm và **duplicate được xử lý theo contract**. Không nên lựa chọn chỉ vì mã DSL ngắn.

### 11.2. Nếu target broker mất kết nối

Một phản ứng an toàn thường là **backpressure hoặc để source giữ message**, thay vì consume/ACK toàn bộ rồi lưu trong queue in-memory. Tùy SLA, có thể chuyển sang durable buffer hoặc outbox để source không bị chặn lâu.

## 12. Thiết kế B: inbox/outbox làm durable handoff

Một bridge cần chịu được việc hai broker không khả dụng cùng lúc có thể lưu **bản sao message và trạng thái giao nhận** ở một hệ thống trung gian bền vững.

~~~mermaid
flowchart TD
    A["Broker A"] --> CON["Inbound consumer"]
    CON --> TX["DB transaction"]
    TX --> I["Inbox: unique source/business ID"]
    TX --> O["Outbox: PENDING target delivery"]
    O --> WORK["Outbox publisher / poller"]
    WORK --> B["Broker B"]
    B --> CONF["Broker confirmation"]
    CONF --> MARK["Mark outbox SENT"]
    I -.-> ACK["ACK source after durable handoff"]
    ACK --> A
    MARK --> AUD["Metrics, audit, reconciliation"]
    WORK -->|Failure| WAIT["Backoff / retry / DLQ alert"]
    WAIT --> WORK
~~~

**Quan trọng:** Tranh chấp commit giữa source broker và DB vẫn tồn tại nếu không dùng distributed transaction. Kiểu triển khai thường **commit DB trước rồi mới ACK source**, chấp nhận redelivery và dùng **unique inbox key** để không ghi outbox trùng. Điều này tránh mất message trong các cửa sổ phổ biến, nhưng vẫn cần test transaction/ack cụ thể.

### 12.1. Trạng thái tối thiểu

~~~text
Inbound:
    NEW -> DURABLY_ACCEPTED -> SOURCE_ACKED

Outbound:
    PENDING -> IN_FLIGHT -> SENT
                     \-> RETRY_PENDING
                     \-> OUTCOME_UNKNOWN
                     \-> QUARANTINED
~~~

Không được đánh dấu `SENT` chỉ vì worker bắt đầu gọi producer hoặc nhận được `send` future chưa hoàn thành.

### 12.2. Inbox và outbox giải quyết những gì?

- **Inbox:** Dedupe source redelivery bằng ID ổn định, tránh tạo hai outbox rows.
- **Outbox:** Giữ trách nhiệm phát target sau khi source ACK, sống qua restart.
- **Publisher worker:** Có backoff, rate limit, trạng thái và retry riêng.
- **Correlation:** Nối source message → outbox row → target record.

Inbox/outbox **không tự tạo exactly-once effect ở target**. Nếu target đã nhận nhưng chưa kịp cập nhật outbox state, worker có thể gửi lại; target consumer vẫn cần idempotency.

### 12.3. Một schema SQL minh họa

~~~sql
-- Ví dụ mô hình chung, không phải schema chuẩn của Spring Integration.
CREATE TABLE bridge_inbox (
    source_system      VARCHAR(120) NOT NULL,
    source_event_id    VARCHAR(220) NOT NULL,
    payload_hash       VARCHAR(128) NOT NULL,
    received_at        TIMESTAMP NOT NULL,
    PRIMARY KEY (source_system, source_event_id)
);

CREATE TABLE bridge_outbox (
    outbox_id          VARCHAR(120) PRIMARY KEY,
    source_system      VARCHAR(120) NOT NULL,
    source_event_id    VARCHAR(220) NOT NULL,
    target_system      VARCHAR(120) NOT NULL,
    destination        VARCHAR(220) NOT NULL,
    status             VARCHAR(40) NOT NULL,
    attempts           INT NOT NULL,
    last_error_code    VARCHAR(120),
    payload_reference  VARCHAR(400) NOT NULL,
    created_at         TIMESTAMP NOT NULL,
    updated_at         TIMESTAMP NOT NULL,
    UNIQUE (source_system, source_event_id, target_system)
);
~~~

Với một event cần phát tới nhiều destinations, unique key phải bao gồm **destination/consumer contract** nếu một target system có nhiều route khác nhau. Ví dụ này cần bổ sung index/locking/leases, isolation level và cleanup phù hợp database thực tế.

### 12.4. Source ACK khi nào?

~~~text
1. Receive message từ broker A.
2. Validate identity/contract và operation key.
3. Trong một DB transaction:
       insert inbox row nếu chưa tồn tại;
       insert các outbox rows tương ứng nếu là event mới.
4. Commit DB thành công.
5. Cho phép source ACK theo cấu hình container/listener.
6. Outbox worker publish sang broker B rồi chờ xác nhận.
7. Chỉ mark SENT khi có outcome được kiểm chứng theo policy.
~~~

Nếu app crash sau bước 4 nhưng trước bước 5, broker A redeliver; unique inbox bảo vệ khỏi tạo thêm outbox row. Nếu app crash sau target publish nhưng trước bước 7, outbox worker có thể gửi lại; target consumer phải dùng cùng event ID để dedupe.

## 13. Khi nào dùng Spring Integration, khi nào dùng broker-native connector?

Không phải mọi bài toán giữa hai broker đều cần một ứng dụng Java tùy chỉnh.

| Lựa chọn | Điểm mạnh | Hạn chế |
| --- | --- | --- |
| **Spring Integration adapters** | Kiểm soát transform, route, filter, retry, hợp đồng và business validation; kết nối nhiều hệ thống | Ứng dụng sở hữu state, scale, monitoring và failure handling |
| **Kafka Connect + connector phù hợp** | Tích hợp nguồn/đích theo connector framework, quản trị offset/task | Capability và semantics tùy connector; transform phức tạp có thể không phù hợp |
| **RabbitMQ federation/shovel** | Bridge/forward message theo khả năng broker, ít custom code | Không thay business transformation, schema governance hoặc arbitrary cross-broker atomicity |
| **JMS provider bridge / network connector** | Có thể phù hợp hệ sinh thái cùng vendor | Phụ thuộc provider, semantics cụ thể và lock-in |
| **CDC/outbox pipeline** | Chuyển event từ trạng thái đã commit của database | Cần thiết kế schema, ordering, idempotent consumption và operations |

Nếu chỉ cần chuyển byte-identical events giữa các broker hỗ trợ connector tốt, công cụ broker-native có thể đơn giản hơn. Nếu cần **kiểm tra contract, làm sạch dữ liệu, route theo tenant, điều phối lỗi và tích hợp HTTP/SFTP/JDBC**, Spring Integration phù hợp để biểu diễn flow qua `MessageChannel` và endpoints.

### 13.1. Tiêu chí lựa chọn

1. Có cần thay đổi **business schema** hoặc routing phức tạp không?
2. Broker A/B có connector được hỗ trợ và vận hành ổn định không?
3. Ai chịu trách nhiệm source offset, producer confirm và DLQ?
4. Có cần thêm DB inbox/outbox hoặc reconciliation không?
5. Tải và latency budget là bao nhiêu?
6. Có yêu cầu multi-tenant, dữ liệu nhạy cảm hoặc chính sách mã hóa không?
7. Đội vận hành có khả năng theo dõi connector-native hay custom integration service tốt hơn?

Không so sánh chỉ bằng số dòng code. Một connector ít code nhưng thiếu khả năng trace hoặc kiểm soát thất bại có thể đắt hơn về vận hành.

## 14. ACK/transaction của source và producer confirmation của target

### 14.1. JMS source

Với JMS message-driven inbound adapter, việc redelivery phụ thuộc **listener container** và JMS session: transactional session, client acknowledgment, auto acknowledgment, error propagation và provider redelivery settings.

Trong nhiều ứng dụng, **container transaction** là công cụ để exception làm rollback source delivery. Nhưng cần test:

- Handler exception có lan tới listener container không?
- Error/recovery callback có **nuốt exception**, làm listener kết thúc bình thường không?
- Container thực sự dùng transacted session hay auto-ack?
- Message còn ở source/được redeliver khi target publish failure không?
- Connection loss giữa source ACK và target confirm ảnh hưởng thế nào?

Một bridge không thể tuyên bố JMS source sẽ redeliver khi lỗi nếu chưa kiểm tra **container configuration và provider behavior**.

### 14.2. RabbitMQ source và target

**Source side:** Consumer ACK/NACK/reject/requeue quyết định RabbitMQ có tiếp tục giao hàng hoặc đưa vào DLX theo topology.  
**Target side:** Publisher confirm giúp biết broker đã nhận publish theo mode được cấu hình; **publisher return** giúp phát hiện một số trường hợp message **unroutable** khi `mandatory` và return callback phù hợp được cấu hình.

| Sự kiện | Cần kiểm chứng |
| --- | --- |
| `basic.ack` nguồn | Source queue có còn delivery không? |
| `basic.nack`/reject không requeue | DLX có route tới DLQ như dự kiến không? |
| Target producer return | Exchange không route được, bridge có coi là lỗi không? |
| Target publisher confirm | ACK/NACK của publish có được quan sát theo contract không? |
| Target queue durable | Message có còn qua broker restart theo persistence configuration không? |

**Publisher confirm ACK không chứng minh đã có consumer nghiệp vụ xử lý**, và nếu không kiểm tra unroutable returns, có thể bỏ qua một lỗi routing quan trọng.

### 14.3. Kafka source và target

**Source side:** Kafka consumer duy trì offset theo group; bridge cần quyết định offset commit sau khi target/durable store đạt trạng thái nào.  
**Target side:** Producer `KafkaTemplate.send(...)` cung cấp completion result/failure; `acks`, retries, idempotent producer và replication settings ảnh hưởng guarantee.

~~~text
Kafka source record (topic=orders, partition=2, offset=105)
    -> bridge
    -> target broker publish
    -> target confirmation / durable outbox
    -> source offset commit theo policy
~~~

**Offset 105 ở source không phải offset ở target.** Nếu target cũng là Kafka, producer có thể chọn partition theo key và assign offset mới. Preserve `eventId` và `aggregateId` để dedupe/ordering theo hợp đồng.

### 14.4. Không có XA mặc định giữa các broker

Một ứng dụng có thể dùng transaction manager cho JMS hoặc local database, và Kafka có transactional producer. Nhưng **chỉ bật hai transaction managers** không tự tạo **một giao dịch nguyên tử xuyên JMS + RabbitMQ + Kafka**.

Các phương án:

- Chấp nhận **at-least-once**, idempotent target và source rollback/redelivery.
- Dùng **inbox/outbox** làm durable handoff.
- Trong hệ sinh thái/driver cụ thể có hỗ trợ distributed transaction, đánh giá XA/JTA theo đúng sản phẩm, chi phí và failure modes; không mặc định mọi broker hỗ trợ chung.

Trong đa số bài toán tích hợp dịch vụ hiện đại, việc định nghĩa **business idempotency và reconciliation** là cần thiết dù source/target có transactional features.

## 15. Ví dụ bridge Kafka → RabbitMQ: ranh giới offset

Giả sử Kafka chứa topic `billing.events` và RabbitMQ là nơi các dịch vụ cũ nhận thông báo.

~~~text
Kafka inbound adapter (consumer group bridge-v1)
   -> parse/validate canonical event
   -> transform payload + AMQP headers
   -> Rabbit outbound publisher
   -> confirm result
   -> Kafka offset commit theo cấu hình an toàn
~~~

### 15.1. Giả mã broker-neutral

~~~text
onKafkaRecord(record):
    event = validateAndNormalize(record)
    key = event.stableEventId

    if directBridgeMode:
        targetResult = publishToRabbitWithConfirmation(event)
        if targetResult.confirmedAndRouted:
            commitSourceOffsetWhenSafe(record)
        else:
            propagateFailureToContainer(record)

    if durableHandoffMode:
        durableStore.insertInboxAndOutboxAtomicallyIfNew(key, event)
        commitSourceOffsetWhenSafe(record)
        // Outbox worker publish sau, độc lập source consumer.
~~~

Giả mã nhấn mạnh **thứ tự trách nhiệm**, không phải API Kafka/Rabbit của Spring. Một producer confirm có thể đến qua callback bất đồng bộ; nếu direct bridge đợi kết quả, phải tính timeout và backpressure. Nếu dùng outbox, source offset chỉ được commit **sau khi durable handoff** được xác nhận.

### 15.2. DLT của Kafka khác DLQ của RabbitMQ

Khi source Kafka record không parse được, có thể chuyển tới **Kafka DLT/quarantine** theo container error handling phù hợp. Khi publish RabbitMQ thất bại, có thể retry hoặc lưu vào **bridge failure store**, thay vì cố đẩy message trả về source topic với idempotency key mới.

Nếu một message đã được accept và lưu outbox bền, sau đó publisher RabbitMQ gặp lỗi, việc retry nên thuộc **outbox worker**, không phải làm consumer Kafka reprocess toàn bộ payload không cần thiết.

### 15.3. Kafka consumer group của bridge

Group ID phải được quản trị cẩn thận:

- Đổi group ID khi deploy có thể làm bridge đọc lại lịch sử theo `auto.offset.reset`.
- Tăng partitions thay đổi phân bổ record; ordering chỉ trong một partition.
- Rebalance hoặc restart tạo nguy cơ redelivery nếu offset chưa commit.
- Nhiều pods trong cùng group chia partitions; không nhất thiết tăng throughput nếu partitions ít.
- Dedupe cần ổn định qua những lần deploy, không dựa trên Spring Message ID mới.

## 16. Ordering, partitions và routing keys

**Thứ tự** là một trong những điểm dễ mất khi chuyển broker. Source JMS queue có một consumer tuần tự không đảm bảo target RabbitMQ nhiều consumers giữ cùng thứ tự xử lý. Kafka giữ thứ tự **theo partition**, không phải toàn topic.

### 16.1. Ordering theo aggregate

Với sự kiện đơn hàng:

~~~text
Event E1: order ORD-971 CREATED
Event E2: order ORD-971 PAID
Event E3: order ORD-971 SHIPPED
~~~

Nếu bridge xử lý song song rồi publish E3 trước E2, target consumer có thể thấy sự kiện sai thứ tự. Cần xác định:

1. Ordering cần **toàn cục**, **theo tenant** hay **theo aggregate**?
2. Source có bảo đảm ordering không?
3. Bridge có dùng `ExecutorChannel`/concurrency khiến đảo thứ tự không?
4. Target Kafka key/partitioning có giữ cùng aggregate trên cùng partition không?
5. Target RabbitMQ consumers có xử lý tuần tự theo aggregate không?
6. Retry một message có chặn các message sau hay cho phép đi trước?

### 16.2. Dùng key ổn định cho Kafka

Với Kafka target, `aggregateId` thường là một lựa chọn hợp lý làm **record key** khi cần ordering per aggregate. Nhưng:

- Key trống có thể phân bổ không theo aggregate.
- Thay serializer hoặc partitioner làm cùng aggregate chuyển partition qua migration có thể ảnh hưởng ordering.
- Thay số partitions có thể thay mapping key → partition.
- Nhiều producers cùng gửi một aggregate không tự có thứ tự nghiệp vụ nếu không phối hợp.

Không khẳng định "có Kafka key thì chắc chắn end-to-end đúng thứ tự" mà chưa kiểm tra producer, partitioning và consumption.

### 16.3. Sequence number khi cần phát hiện gap

Event contract có thể thêm `aggregateVersion` hoặc `sequenceNumber`. Consumer target kiểm tra:

~~~text
lastAppliedVersion(ORD-971) = 4
received version 5 -> apply
received version 5 again -> duplicate, skip
received version 7 -> gap, wait/quarantine/reconcile
received version 3 -> stale, skip theo business policy
~~~

Đây là business state, không nên suy từ target Kafka offset hoặc RabbitMQ delivery tag. Nếu version 7 đến trước version 6, bỏ version 6 chỉ vì "last seen = 7" có thể làm mất tác vụ hợp lệ.

## 17. Idempotent Receiver ở target và duplicate suppression ở bridge

Bridge có thể bị buộc phát lại cùng message khi target confirm không rõ. Vì vậy **idempotency** nên được thiết kế ở cả nơi nhận và nơi phát:

| Lớp | Có thể làm gì? | Giới hạn |
| --- | --- | --- |
| Source record ID | Phát hiện cùng delivery/record | Republish cùng event có ID khác |
| Bridge inbox | Ngăn tạo hai outbox rows cho cùng event | Không kiểm soát mọi side effect target |
| Bridge outbox | Retry bền với cùng event key | Publish lại vẫn có thể đến target |
| Target broker dedupe | Broker-specific nếu có hỗ trợ | Không mặc nhiên chống duplicate business |
| Target consumer inbox | Đảm bảo mỗi operation được áp đúng theo key | Cần transaction/unique constraint với business effect |
| Downstream HTTP API | Dùng idempotency key theo API contract | Cần xử lý response mất/outcome unknown |

### 17.1. Chọn key nào?

~~~text
Không nên dùng:
    bridge-delivery-UUID sinh mới mỗi attempt

Nên dùng:
    sourceSystem + stableEventId + destinationContract

Ví dụ:
    legacy-jms:evt-T42-971-1:rabbit-orders-v2
~~~

`destinationContract` giúp phân biệt việc phát tới những consumer hoặc target hợp lệ khác nhau. Nếu cùng event gửi tới hai target, mỗi target cần trạng thái giao nhận độc lập.

### 17.2. Cùng key nhưng payload khác?

Nếu inbox đã chứa `evt-T42-971-1` nhưng payload được gửi lần sau có amount/status khác, không nên im lặng coi là duplicate. Lưu **payload fingerprint** để phát hiện **key collision hoặc upstream contract violation**; chuyển vào điều tra/conflict queue.

### 17.3. MetadataStoreSelector có đủ không?

Spring Integration có `MetadataStoreSelector` và `IdempotentReceiverInterceptor` giúp phát hiện key đã gặp. Tuy nhiên **đánh dấu seen trước khi business commit** có thể làm mất message sau crash. Với bridge có yêu cầu bền vững, nên cân nhắc **transactional inbox/outbox** hoặc một chiến lược phối hợp marker với trạng thái nghiệp vụ thật.

## 18. Retry policy: transient, permanent và outcome unknown

| Lỗi | Ví dụ | Chính sách thường phù hợp |
| --- | --- | --- |
| **Transient target unavailable** | Rabbit connection reset, Kafka leader failover | Retry hữu hạn, backoff/jitter và circuit breaker |
| **Backpressure/overload** | Broker flow control, quota/throttling | Giảm concurrency/rate, tăng buffer bền |
| **Permanent schema invalid** | Unknown required field, incompatible version | Quarantine/DLQ, không retry vô hạn |
| **Unauthorized publish** | ACL/credentials/TLS sai | Dừng/alert, sửa cấu hình; retry có kiểm soát |
| **Unroutable Rabbit message** | Sai binding/routing key | Kiểm tra publisher return/topology, không coi success |
| **Oversized payload** | Vượt broker message size policy | Reject/chuyển payload reference theo contract |
| **Publish confirm timeout** | Không rõ broker đã nhận hay chưa | `OUTCOME_UNKNOWN`, retry bằng cùng event ID |
| **Source transaction failure** | JMS session commit lỗi hoặc Kafka offset commit thất bại | Chấp nhận redelivery, dùng inbox/idempotency |
| **Business conflict** | Same event ID nhưng khác payload | Điều tra contract, không auto sửa event |

### 18.1. Bounded retry và backoff

Một bridge nên giới hạn số attempts theo **mỗi failure domain**. Nếu Rabbit publisher retry 3 lần, Spring Integration handler advice retry 3 lần và source broker redeliver 5 lần, số publish attempts có thể tới **45** trong kịch bản tất cả vòng đều chạy đủ, chưa kể SDK auto retry.

Đừng đặt ba lớp retry độc lập rồi chỉ nhìn `maxAttempts` của một lớp.

### 18.2. Khi cần dead-letter?

- **Permanent invalid:** Đưa vào quarantine nhanh, giữ reference/schema version.
- **Transient exhausted:** Ghi durable failure record hoặc để source còn trách nhiệm redelivery theo runbook.
- **Outcome unknown:** Cần reconciliation trước khi replay mù.
- **No owner:** Escalation; không được để DLQ tăng mãi không ai xử lý.

### 18.3. Circuit breaker và pause intake

Khi broker target unavailable lâu, source consumers có thể bị giữ trong retry loop. Kết hợp:

- Giới hạn concurrency và inflight messages.
- Rate limiter/backoff với jitter khi phù hợp.
- Pause/resume container theo runbook.
- Handoff vào outbox bền nếu muốn source tiếp tục tiêu thụ.
- Cảnh báo backlog source và outbox theo độ tuổi, không chỉ theo số lượng.

## 19. ErrorMessage, errorChannel và dead-letter trong Spring Integration

**`ErrorMessage`** của Spring Messaging có payload `Throwable`. Spring Integration có global `errorChannel` và hỗ trợ header `errorChannel` trong các đường xử lý lỗi phù hợp.

Tuy nhiên:

- Một `DirectChannel` handler ném exception đồng bộ có thể **truyền lỗi ngược caller**, không nhất thiết publish global ErrorMessage.
- Poller hoặc async endpoint có thể dùng `MessagePublishingErrorHandler` để publish ErrorMessage.
- `RequestHandlerRetryAdvice` có thể dùng `RecoveryCallback` khi retry exhausted.
- `ErrorMessageSendingRecoverer` gửi ErrorMessage tới channel được chỉ định; bản thân nó **không tự publish vào broker DLQ**.

### 19.1. Error route đề xuất

~~~mermaid
flowchart TD
    H["Broker bridge outbound handler"] --> F{"Publish failed?"}
    F -->|Không| OK["Delivery state success theo confirmation contract"]
    F -->|Có| R["Bounded retry"]
    R --> EX{"Exhausted / permanent?"}
    EX -->|Không| H
    EX -->|Có| ERR["RecoveryCallback / ErrorMessage"]
    ERR --> CLASS["Classify failure"]
    CLASS -->|Invalid schema| Q["Quarantine"]
    CLASS -->|Transient exhausted| DL["Durable DLQ/failure store"]
    CLASS -->|Unknown result| REC["Reconciliation queue"]
    Q --> AUD["Audit + owner"]
    DL --> AUD
    REC --> AUD
~~~

### 19.2. Recovery handler cũng có thể lỗi

Nếu publish tới DLQ hoặc lưu failure DB lỗi, không được `catch Exception` rồi chỉ log nếu điều đó khiến source ACK trước khi có bản sao an toàn.

Thiết kế phải có **điểm dừng**:

~~~text
Target publish failed
  -> recovery store persist failed
  -> propagate error / keep source responsibility / pause intake
  -> alert, không tự coi message đã recovered
~~~

Đặc biệt với outbox, **failure store có thể chính là outbox**: message vẫn ở trạng thái `PENDING/RETRY_PENDING` và được thử lại sau, thay vì cần copy sang broker DLQ ngay.

### 19.3. Source DLQ và target DLQ không thay thế nhau

| Nơi lỗi | Điểm lưu thích hợp |
| --- | --- |
| Source payload không parse được | Source-side quarantine/DLQ hoặc durable failure store |
| Target publish thất bại lâu | Bridge outbox/recovery store hoặc source redelivery |
| Target consumer xử lý thất bại | Target-side DLQ/DLT theo chính sách consumer |
| Unknown publish confirmation | Reconciliation/bridge state; dùng same event ID |

Một event có thể **đã đến target broker** nhưng target consumer vẫn chuyển nó vào target DLQ do business error. Đây là hai loại failure khác nhau, cần event ID để nối audit.

## 20. Thiết kế dead-letter envelope và replay

### 20.1. Failure record

~~~json
{
  "failureId": "bridge-fail-20261123-012",
  "bridgeId": "legacy-jms-to-rabbit-v2",
  "source": {
    "broker": "jms",
    "destination": "legacy.orders",
    "sourceRecordRef": "JMS-message-reference"
  },
  "target": {
    "broker": "rabbitmq",
    "exchange": "orders.bridge",
    "routingKey": "orders.in"
  },
  "eventId": "evt-T42-971-1",
  "schemaVersion": 2,
  "correlationId": "trace-84021",
  "attemptsObserved": 3,
  "errorCategory": "TARGET_PUBLISH_TIMEOUT",
  "outcome": "UNKNOWN_REQUIRES_RECONCILIATION",
  "payloadReference": "encrypted-blob-ref:bridge/evt-T42-971-1",
  "owner": "integration-platform",
  "createdAt": "2026-11-23T08:05:00Z",
  "nextAction": "verify-target-before-republish"
}
~~~

Đây là **schema nghiệp vụ minh họa**, không phải dữ liệu `ErrorMessage` tự tạo sẵn. Lưu `attemptsObserved` từ counter hoặc retry context đáng tin; một lỗi non-retryable có thể được chuyển vào recovery sau lần thử đầu.

### 20.2. Replay an toàn

Trước replay:

1. Xác minh nguyên nhân lỗi đã được khắc phục.
2. Truy vấn target broker/downstream hoặc durable reconciliation state khi kết quả publish chưa rõ.
3. Giữ **eventId/business operation ID gốc**; thêm `replayId` riêng.
4. Không chuyển event cũ sang schema mới khi chưa có quy tắc migration.
5. Giới hạn số replay và tốc độ.
6. Ghi owner, approval nếu tác động production hoặc dữ liệu nhạy cảm.
7. Kiểm tra target consumer không sinh side effect trùng.
8. Đánh dấu resolved chỉ khi có bằng chứng theo contract.

~~~text
Original eventId: evt-T42-971-1
Source delivery: JMS-msg-204
First bridge attempt: attempt-001
Dead-letter record: bridge-fail-012
Replay attempt: replay-022

Idempotency key gửi sang target vẫn là: evt-T42-971-1
~~~

### 20.3. Chống vòng lặp hai chiều

Nếu có cả bridge **A → B** và **B → A**, một message mới phát ở A có thể quay lại A, rồi tiếp tục lặp vô hạn.

Hợp đồng nên có:

- `originSystem`/provenance đáng tin, không lấy tùy tiện từ bên không tin cậy.
- `bridgeRouteId`, `hopCount` và giới hạn hop.
- Quy tắc bỏ qua event được bridge này tạo ra nếu không có tác vụ mới.
- Deduplication theo stable event ID + route.
- Không tự động gộp hai bridge thành một đường full-duplex nếu chưa có điều kiện ngăn loop.

## 21. Backpressure, throughput và capacity planning

Nếu source có 10.000 messages/giây nhưng target chỉ nhận ổn định 2.000, bridge phải quản lý backlog. Thêm threads không giải quyết được việc target chậm và có thể làm tệ hơn vì retry storm.

### 21.1. Chọn chiến lược

| Cơ chế | Khi phù hợp | Lưu ý |
| --- | --- | --- |
| Giảm consumer concurrency | Target broker bị quá tải | Kiểm tra source lag và SLA |
| Bounded inflight messages | Hạn chế memory và số publish đang chờ confirm | Có timeout và signal rõ |
| Bounded retry/backoff | Lỗi transient | Không nhân retry quá nhiều lớp |
| Durable outbox buffer | Target downtime nhưng source muốn tiếp tục consume | Theo dõi disk/DB size, retention, cleanup |
| Pause source listeners | Target outage kéo dài, không có buffer an toàn | Nguồn cần đủ retention/queue capacity |
| Batch/compression | Giảm overhead với payload phù hợp | Kiểm soát message size, ordering và error granularity |
| Partition-aware processing | Giữ ordering theo aggregate và scale-out | Không thay partitioner tùy tiện |

### 21.2. Tính backlog gần đúng

~~~text
Input rate  = 10.000 events/giây
Output rate =  2.000 events/giây
Growth      =  8.000 events/giây

Sau 5 phút:
    8.000 x 300 = 2.400.000 events tồn đọng
~~~

Đây là **tính toán minh họa**, chưa tính kích thước payload, overhead indexing, retries và replication. Nếu trung bình payload 4 KiB, chỉ dữ liệu thô đã là khoảng 9,2 GiB, chưa gồm metadata và replicas; cần capacity plan thực tế.

### 21.3. Không dùng QueueChannel in-memory làm buffer vô hạn

Queue in-memory có thể cạn RAM và mất message khi process dừng. Nếu dùng một channel có backing store bền vững, vẫn cần xác minh **atomic handoff và transaction/source ACK**, không tự coi "persistent queue" là exactly-once.

## 22. Bảo mật và ranh giới trust

Bridge đứng giữa hai broker thường nối hai security domains, nên bản thân nó là **điểm nhạy cảm**.

### 22.1. Nguyên tắc bảo mật

- **Least privilege:** Identity đọc chỉ queue/topic nguồn, ghi chỉ destination đích; không dùng admin broker chung.
- **TLS và credential rotation:** Mã hóa kết nối, validate server identity, không hardcode password trong YAML/repository.
- **Segregation:** Tách dev/staging/production, tenant, vùng dữ liệu và tài khoản kỹ thuật.
- **Payload validation:** Không tin mọi header/payload từ source, kể cả `tenantId` hoặc `routingKey`.
- **Header allowlist:** Không chuyển tiếp token, credentials, broker-internal metadata hoặc debug headers.
- **PII minimization:** Chỉ chuyển dữ liệu cần cho consumer, mã hóa payload reference ở DLQ/outbox.
- **ACL:** Người vận hành bridge không mặc nhiên được đọc mọi DLQ hoặc đổi schema.
- **Audit:** Ghi thay đổi topology, destination routing, role, TLS và connection config.
- **Supply chain:** Nếu transform dùng thư viện/serializer ngoài, kiểm soát dependencies và dữ liệu đầu vào.

### 22.2. Chống cross-tenant routing

~~~text
Không an toàn:
    routingKey = rawMessage.header("tenantDestination")

An toàn hơn:
    tenant = authenticateOrValidateTenant(sourceContext, payload)
    routingKey = approvedRoutingTable.lookup(tenant, eventType)
    verifyACL(destination, tenant)
~~~

Đây là pseudocode thể hiện bảo vệ ranh giới; chức năng `approvedRoutingTable` và `verifyACL` do ứng dụng/quy trình quản trị cung cấp.

### 22.3. Tránh log raw payload

Trong error flow, một `ErrorMessage` có thể mang failed/original message chứa payload nhạy cảm. Không ghi toàn bộ `Throwable` và `Message.toString()` vào logs nếu chưa redact. Lưu **event ID, correlation ID, exception category, destination và payload reference** lành mạnh thường đủ cho điều tra ban đầu.

## 23. Vòng đời kết nối và shutdown

Bridge có **hai bộ kết nối**: consumer nguồn và publisher đích. Việc khởi động/khôi phục/shutdown phải tính riêng từng phía.

### 23.1. Startup

1. Kiểm tra connection source và target, certificate/credential, network/TLS.
2. Khởi tạo topology cần thiết hoặc xác minh queue/exchange/topic có tồn tại.
3. Khởi động health/metrics và failure store/outbox.
4. Nếu direct bridge yêu cầu target sẵn sàng, xác nhận target publisher có thể hoạt động trước khi mở source intake.
5. Khởi động listener/poller và giới hạn concurrency ban đầu nếu cần.

**Lưu ý:** Đừng xem `connection opened` là bằng chứng có đủ ACL để consume/publish tới destination thật; cần kiểm chứng permission hoặc kiểm thử được phép.

### 23.2. Shutdown có kiểm soát

~~~text
Stop accepting new source deliveries
  -> drain/stop inflight handlers theo deadline
  -> confirm/persist pending target publishes
  -> source ACK hoặc để redelivery theo policy
  -> checkpoint/flush durable state
  -> close producer/consumer connections
~~~

Nếu deadline shutdown hết trước khi publisher confirm, message phải **ở nguồn hoặc durable buffer** theo thiết kế. Không đánh dấu delivery `SENT` trước confirm chỉ để tắt ứng dụng nhanh.

### 23.3. Connection flapping

Khi target reconnect liên tục, có thể xảy ra:

- Multiple inflight publishes chưa rõ outcome.
- Source backlog và redeliver tăng.
- Producer reconnect/backoff lặp.
- Consumer rebalance (Kafka) hoặc listener restart.
- Session/channel leak và memory pressure.

Test reconnect và xác minh **không thất thoát resource**, không tiếp tục sử dụng stale connections và không ghi nhầm duplicate do retries.

## 24. Observability: nhìn thấy message đang ở đâu

Nếu bridge hoạt động giữa các hệ thống không có giao dịch chung, **observability là điều kiện để đối soát**, không chỉ để tối ưu hiệu năng.

### 24.1. Bốn trạng thái phải phân biệt

~~~text
RECEIVED:        Broker source đã giao message cho bridge.
DURABLE_ACCEPTED: Bridge đã ghi trách nhiệm bền vững (ví dụ inbox/outbox).
TARGET_PUBLISHED: Broker target đã confirm theo guarantee được chọn.
BUSINESS_APPLIED: Consumer đích đã hoàn tất tác vụ nghiệp vụ.
~~~

Bridge thường chỉ trực tiếp chứng minh ba trạng thái đầu; `BUSINESS_APPLIED` phải đến từ **consumer acknowledgment nghiệp vụ, event phản hồi hoặc reconciliation** phù hợp. Không tự đánh dấu business success từ publisher confirm.

### 24.2. Metrics gợi ý

| Metric | Ý nghĩa |
| --- | --- |
| `bridge_source_received_total` | Tổng message nguồn đã nhận |
| `bridge_inbox_deduplicated_total` | Redelivery được inbox nhận diện |
| `bridge_outbox_pending` | Số outbound records chưa hoàn tất |
| `bridge_outbox_oldest_age_seconds` | Tuổi message chờ target lâu nhất |
| `bridge_publish_attempt_total` | Số lần gọi producer, kể cả retry |
| `bridge_publish_confirm_total` | Confirm thành công theo target |
| `bridge_publish_return_total` | Rabbit unroutable returns nếu được cấu hình |
| `bridge_publish_unknown_total` | Publish outcome chưa rõ |
| `bridge_retry_exhausted_total` | Hết lượt retry theo policy |
| `bridge_dead_letter_total` | Failure được lưu/publish vào DLQ |
| `bridge_replay_total` | Replay attempts, thành công/thất bại |
| `bridge_source_lag` | JMS queue depth/Rabbit depth/Kafka lag theo nguồn |
| `bridge_target_lag` | Độ trễ giữa source và target confirmation |
| `bridge_duplicate_detected_total` | Event ID lặp qua source/replay |
| `bridge_contract_rejected_total` | Reject vì schema/version/tenant |
| `bridge_connection_recovery_total` | Số lần reconnect theo broker |

Đây là **metric names do ứng dụng đề xuất**, không phải Spring Integration tự tạo toàn bộ. Metric labels nên chứa `flow`, `sourceBroker`, `targetBroker`, `errorCategory`, `environment` với cardinality kiểm soát được; không dùng mỗi `eventId` làm label.

### 24.3. Structured log

~~~json
{
  "event": "bridge.target.publish.unknown",
  "bridgeId": "jms-orders-to-rabbit-v2",
  "sourceBroker": "jms",
  "targetBroker": "rabbitmq",
  "sourceDestination": "legacy.orders",
  "targetDestination": "orders.bridge/orders.in",
  "eventId": "evt-T42-971-1",
  "correlationId": "trace-84021",
  "outboxId": "outbox-0042",
  "outcome": "UNKNOWN_REQUIRES_RECONCILIATION",
  "attemptsObserved": 2,
  "occurredAt": "2026-11-23T08:10:00Z"
}
~~~

Không ghi raw JMS properties chứa credential, AMQP Authorization, Kafka SASL secret, file nội dung nhạy cảm hoặc Spring Message payload thô vào log.

### 24.4. Tracing xuyên broker

Trace có thể gắn:

~~~text
Source consume span
  -> contract normalize span
  -> durable handoff span
  -> target publish span
  -> target consumer span (nếu có propagation)
~~~

Một trace context có thể không còn tồn tại xuyên thời gian retention dài hoặc replay. Vì vậy **eventId/correlationId bền** vẫn cần thiết, không thay bằng trace/span ID được tạo mới cho mỗi attempt.

## 25. Kiểm thử bridge theo tầng

Một test suite tốt tách các mức để biết **đã kiểm tra chính xác bảo đảm nào**.

| Tầng | Điều kiểm tra | Công cụ phù hợp |
| --- | --- | --- |
| **Unit** | Canonical event mapping, routing, key, validation | JUnit 5, Mockito, AssertJ |
| **Spring Integration component** | Adapter → channel → transformer → handler/error route | Spring Integration Test, mock handler/source, `QueueChannel` |
| **Broker integration** | JMS transaction, Rabbit confirm/return, Kafka offset/DLT | Testcontainers/embedded broker theo nhu cầu |
| **Durability integration** | Inbox/outbox DB commit, uniqueness, outbox retry | Disposable database, transaction tests |
| **Failure injection** | Crash sau publish, trước ACK/mark SENT, target outage | Staging/containers với network fault/restart |
| **End-to-end** | Message đến target và target consumer áp business đúng | Test environment mô phỏng hai domains |

### 25.1. Test không được chứng minh quá phạm vi

Ví dụ unit test:

~~~java
verify(rabbitTemplate).convertAndSend(
        eq("orders.bridge"),
        eq("orders.in"),
        any());
~~~

Test này chỉ chứng minh **method được gọi**, không chứng minh broker nhận message, exchange route tới queue, confirm ACK, consumer nhận, hay source JMS đã commit đúng.

### 25.2. Broker integration assertions

Đối với JMS → RabbitMQ:

1. Gửi message fixture vào JMS queue test.
2. Khởi động inbound message-driven adapter trong context có topology RabbitMQ test.
3. Chờ message xuất hiện ở Rabbit target queue với bounded timeout.
4. Assert payload/schema, eventId, correlationId, routing và headers được phép.
5. Cho Rabbit target không route được hoặc publish thất bại: verify error/recovery behavior.
6. Verify source JMS redelivery/ACK hoặc handoff outbox theo config thật.
7. Restart bridge trước ACK, xác nhận không mất event và xử lý duplicate theo contract.

Đối với Kafka → JMS:

1. Produce Kafka record có key/partition/offset xác định.
2. Bridge nhận qua consumer group test.
3. Gửi tới JMS queue test và xác minh có message.
4. Tắt JMS broker khi publish, verify source offset không được commit trước durable handoff.
5. Khởi động lại, verify redelivery không tạo business side effect trùng.

### 25.3. Failure injection matrix

| Điểm lỗi | Mục tiêu assertion |
| --- | --- |
| Source connection mất trước receive | Không báo nhận event giả |
| Source nhận xong, target down | Message còn ở source hoặc durable buffer |
| Target publish success, confirm response mất | `UNKNOWN`, retry với cùng event ID |
| Confirm success, source ACK fail | Redelivery; target consumer idempotent |
| DB inbox commit xong, source ACK fail | Unique inbox không tạo outbox trùng |
| Outbox publish success, mark SENT fail | Worker retry không tạo business duplicate |
| Schema invalid | Quarantine nhanh, không retry kết nối vô hạn |
| Rabbit exchange unroutable | Publisher return được xử lý thành failure |
| Kafka DLT publish failure | Không mark record `RECOVERED` giả |
| Target queue full/quota exceeded | Backpressure, source retention an toàn |
| App shutdown với inflight message | Không ACK trước handoff hoặc confirm |
| Two concurrent bridge instances | Unique key/locking/correct per-partition handling |
| Source event republished với ID transport khác | Business dedupe hoạt động |
| Replay sau target outage | Event ID giữ nguyên; đúng owner/audit |
| Đổi routing config sai | Alert và quarantine, không gửi cross-tenant |

### 25.4. Test lỗi giữa hai transaction

Một case đặc biệt quan trọng:

~~~text
1. Outbox worker publishes evt-T42-971-1 to Rabbit.
2. Rabbit broker ACKs publisher confirm.
3. Bridge process crashes before marking outbox row SENT.
4. Bridge restarts; worker publishes same event again.

Expected:
    Rabbit may receive two deliveries.
    Both carry the same stable eventId.
    Target consumer applies business effect once.
    Outbox eventually reaches reconciled SENT state.
~~~

Nếu test chỉ assert "Rabbit nhận đúng một message" rồi đỏ khi nhận hai, nó có thể đang yêu cầu một đảm bảo **không thuộc kiến trúc at-least-once**. Nên assert **business outcome idempotent**, đồng thời đo duplicates để cải thiện.

## 26. Ví dụ thực hành: từ JMS sang RabbitMQ qua outbox

Giả sử hệ thống **Learning Orders** muốn gửi event từ JMS queue `legacy.orders` sang RabbitMQ exchange `learning.events`. Team chọn outbox để tách vòng đời hai broker.

### 26.1. Định nghĩa contract

~~~yaml
# Contract minh họa, không phải cấu hình Spring Integration tự sinh.
bridgeId: legacy-jms-to-rabbit-v2
source:
  protocol: jms
  destination: legacy.orders
target:
  protocol: amqp
  exchange: learning.events
  routingKey: order.created.v2
message:
  eventIdField: eventId
  aggregateIdField: orderId
  schemaVersion: 2
  payloadFormat: json
delivery:
  expectedGuarantee: at-least-once
  durableHandoff: jdbc-inbox-outbox
  confirmRequired: true
  targetConsumerIdempotency: required
errorHandling:
  invalidContract: quarantine
  transientPublishFailure: retry-with-backoff
  unknownConfirm: reconcile-and-retry-same-event-id
security:
  headerAllowlist:
    - eventId
    - correlationId
    - schemaVersion
~~~

### 26.2. Giai đoạn 1 — nhận vào inbox/outbox

~~~text
JMS inbound receives message M.

validate/M -> canonical event E.
sourceKey = (sourceSystem, E.eventId).
payloadHash = fingerprint(E).

DB transaction:
    if sourceKey absent:
        insert inbox(sourceKey, payloadHash).
        insert outbox(E, targetRoute, status=PENDING).
    else:
        verify payloadHash matches; do not insert duplicate.
commit DB.

Only after durable commit:
    allow JMS session/container to complete according to
    configured transaction and acknowledgment semantics.
~~~

**Giới hạn:** Đây là **giả mã nghiệp vụ**, không phải giao dịch XA. Nếu DB đã commit nhưng JMS session không commit, JMS redelivery được xử lý qua unique key. Nếu JMS ACK trước khi DB commit, có nguy cơ mất event; vì thế cần integration test listener/container thật.

### 26.3. Giai đoạn 2 — phát ra RabbitMQ

~~~text
Outbox worker claims a PENDING row with lease/version.
Build target payload + allowlisted AMQP headers.
Publish to learning.events with order.created.v2.
Wait for configured broker publish confirm.
Check mandatory return/unroutable policy.

If broker confirms and routing requirements pass:
    mark row SENT (with confirm metadata).
If confirmed NACK or known failure:
    mark RETRY_PENDING and schedule backoff.
If confirmation is lost/unknown:
    mark OUTCOME_UNKNOWN and retry/reconcile
    using the original eventId.
~~~

Một **Rabbit publish return** và một **publisher confirm** là các tín hiệu riêng; xử lý callback/lifecycle cần đúng theo cấu hình RabbitTemplate và Spring AMQP version. Không dùng `Thread.sleep` như cách xác nhận publish thành công.

### 26.4. Giai đoạn 3 — target consumer

Rabbit consumer nhận event với `eventId=evt-T42-971-1`, kiểm tra unique business key trong inbox của nó, rồi commit business effect cùng trạng thái `COMPLETED` nếu có thể.

Khi bridge phát lại cùng event, consumer có thể ACK duplicate đã `COMPLETED` mà không tạo thêm đơn hàng; nếu trạng thái `PROCESSING/UNKNOWN`, phải có cơ chế chờ/đối soát thay vì bỏ message vô điều kiện.

### 26.5. Trạng thái đi qua

~~~mermaid
stateDiagram-v2
    [*] --> Received
    Received --> DurableAccepted: Inbox/outbox DB commit
    DurableAccepted --> PendingPublish: Source ACK allowed
    PendingPublish --> InFlight: Worker claim
    InFlight --> Sent: Publish confirmed/routed
    InFlight --> RetryPending: Known failure
    InFlight --> Unknown: Confirm result unknown
    RetryPending --> InFlight: Retry bounded
    Unknown --> InFlight: Reconcile / resend with same eventId
    InFlight --> Quarantined: Permanent contract violation
    Sent --> [*]
    Quarantined --> [*]
~~~

State machine là minh họa; trong hệ thống thật `Unknown` có thể cần manual intervention và status `SENT` không đồng nghĩa target business `COMPLETED`.

## 27. Migration plan khi thay broker trong production

Thay broker là thay **contract, traffic ownership và failure modes**. Nên triển khai theo giai đoạn với rollback rõ.

### 27.1. Giai đoạn 0 — inventory

- Liệt kê producers, consumers, queue/topic, consumer groups/subscriptions.
- Ghi schema, message size, compression, partitioning, priority, TTL, retention.
- Xác định requirement về ordering, dedupe, DLQ, business latency.
- Đo baseline source rate, lag, retry và payload distribution.
- Ghi owner nghiệp vụ và điều kiện cắt chuyển.

### 27.2. Giai đoạn 1 — shadow bridge

Đưa message sang target để **quan sát**, chưa kích hoạt side effects từ consumer mới nếu chưa có quy trình an toàn. Đối chiếu:

- Số event theo stable event IDs.
- Schema và fingerprint.
- Timing/lag.
- Routing/ordering và missing records.
- Unknown/invalid contract.

Nếu shadow consumer cũng gọi external API tạo đơn, đây **không** còn là shadow an toàn. Cần tắt side effect hoặc dùng môi trường thử phù hợp.

### 27.3. Giai đoạn 2 — dual-read hoặc cutover có kiểm soát

Một số chiến lược:

- **Strangler migration:** Chuyển từng nhóm consumer sang target.
- **Canary:** Chuyển một tenant/partition/route nhỏ trước.
- **Dual-write/dual-publish:** Chỉ nếu đã kiểm soát duplicate, ordering và reconciliation.
- **Replay/backfill:** Đồng bộ lịch sử theo event ID mà không tạo business effect trùng.

**Dual-write** đặc biệt cần cẩn trọng: source application publish hai broker có thể thành công ở A nhưng thất bại ở B, tạo split-brain event history. Dùng outbox/CDC/bridge có durable state giúp dễ đối soát hơn.

### 27.4. Giai đoạn 3 — chuyển ownership

Xác định thời điểm:

1. Producer mới ghi broker nào là authoritative?
2. Consumer cũ ngừng xử lý side effects khi nào?
3. Bridge có tiếp tục chuyển event hai chiều hay chỉ một chiều?
4. Event đến muộn và nguồn cũ còn backlog được xử lý thế nào?
5. Hệ thống nào giữ replay/retention sau cutover?

Đừng tắt bridge chỉ vì dashboard "queue depth = 0" tại một thời điểm; còn inflight messages, retries, outbox pending, delay queue hoặc DLT.

### 27.5. Rollback

Rollback plan cần có:

- Điều kiện tự động/dưới quyền approver để dừng cutover.
- Cách pause consumer mới không mất events.
- Cách đưa consumers cũ hoạt động lại mà không replay side effects đã hoàn tất.
- Bản đồ event IDs/offsets và kết quả đã commit.
- Kế hoạch xử lý schema changes mới không tương thích hệ cũ.
- Audit ghi ai quyết định và trạng thái cuối.

## 28. Runbook khi broker đích không khả dụng

### 28.1. Triệu chứng

RabbitMQ target trả publisher NACK/connection timeout; outbox pending tăng. JMS source vẫn hoạt động và các ứng dụng vẫn tạo đơn hàng.

### 28.2. Chẩn đoán

1. Kiểm tra target broker network/TLS/ACL, exchange/queue bindings, quota và health.
2. Kiểm tra lỗi client producer, confirm/return, reconnect và retry budget.
3. Xác định bridge đang ở chế độ **direct** hay **durable handoff**.
4. Kiểm tra source queue depth/lag, inflight/ACK và redelivery.
5. Kiểm tra outbox age, DB disk/CPU, pool connections và lease contention.
6. Xác định event nào `PENDING`, `RETRY_PENDING`, `UNKNOWN`, `SENT`.
7. Kiểm tra failed schema/routing khác với lỗi hạ tầng, không gộp mọi thứ thành "Rabbit down".

### 28.3. Ứng phó

- Hạn chế source consumers hoặc pause intake nếu buffer sắp đầy.
- Không xóa backlog hoặc ACK để làm đẹp dashboard.
- Giới hạn retry và tăng backoff để tránh đánh sập broker khi vừa hồi phục.
- Với unknown confirms, retry bằng cùng event ID và giám sát duplicate.
- Xử lý auth/ACL hoặc misrouting bằng change control, không retry vô hạn.
- Ưu tiên những event có SLA quan trọng theo policy; tránh đảo thứ tự của cùng aggregate ngoài dự định.
- Không flush inbox/outbox để "giải phóng dung lượng" khi chưa có kế hoạch recovery.

### 28.4. Sau khi phục hồi

1. Chạy canary publish, kiểm tra confirm và routing thật.
2. Tăng dần concurrency/rate theo sức chịu tải target.
3. Theo dõi source lag và outbox oldest age cùng nhau.
4. Đối soát source event IDs với target records.
5. Xử lý DLQ/quarantine và unknown outcomes.
6. Chỉ đóng incident khi backlog đã được giải quyết hoặc còn các ngoại lệ có owner/deadline.
7. Ghi lại root cause, retry config, session lifecycle và test phòng tránh tái diễn.

## 29. Những anti-pattern thường gặp

| Anti-pattern | Hậu quả | Biện pháp |
| --- | --- | --- |
| Coi `BridgeHandler` là broker connector | Không tạo nguồn/đích thực | Cấu hình inbound/outbound adapters riêng |
| Dùng `ExecutorChannel` in-memory rồi ACK source ngay | Crash làm mất message | Durable handoff hoặc giữ trách nhiệm ở source |
| Publish target xong không quan sát confirm | Không biết broker đã nhận/routed | Publisher confirm/return và kiểm chứng |
| Dùng source JMS transaction như transaction cho Rabbit/Kafka | Ảo tưởng atomic cross-broker | Inbox/outbox + idempotency hoặc giải pháp giao dịch được chứng minh |
| Tạo event ID mới mỗi lần retry | Target không dedupe được | Stable event ID và replay ID riêng |
| Copy toàn bộ JMS/AMQP/Kafka headers | Incompatible types, leak credential, sai routing | Canonical envelope + allowlist |
| Bỏ `replyTo`/correlation khi cần request-reply | Caller chờ vô hạn hoặc sai response | Thiết kế gateway reply contract |
| Nhầm Rabbit exchange với queue | Publish thành công nhưng unroutable | Bindings + mandatory returns + tests |
| Coi Kafka offset là business event ID | Republish/bridge sang topic khác mất idempotency | Business event ID ổn định |
| Nhiều retries không có budget | Retry storm, latency cao | Bounded attempts/backoff/concurrency |
| Retry schema invalid mãi | Poison messages làm nghẽn queue | Permanent error → quarantine |
| Coi DLQ là đã xử lý nghiệp vụ | Failure tồn đọng vô hạn | Owner, SLA, reconciliation và replay |
| Nuốt lỗi khi archive failure | Source ACK trong lúc không có bản sao bền | Fail-safe và kiểm thử store outage |
| Xóa outbox pending sau source ACK | Mất trách nhiệm delivery | Retention, recovery, audit có kiểm chứng |
| Dùng một cờ `forwarded=true` cho nhiều targets | Một target fail bị che | Per-target outbox status |
| Không phân tích ordering | CREATED/PAID/SHIPPED tới sai thứ tự | Per-aggregate ordering + sequence/gap logic |
| Hai bridge hai chiều không chặn loop | Message đi vô hạn A↔B | Provenance/hop limit/route dedupe |
| Shadow traffic có side effects thật | Tạo đơn hàng/giao dịch trùng | Shadow consumers không thực thi business effect |
| Tắt bridge khi queue depth tạm bằng 0 | Còn inflight, DLQ hoặc outbox pending | Cutover readiness và reconciliation |
| Copy raw payload vào log và DLQ | Rò rỉ PII/credential | Redaction, encryption, scoped access |

## 30. Bài tập tự kiểm tra

### Bài 1 — JMS ACK trước Rabbit publish

**Tình huống:** JMS listener nhận event, đưa message vào `ExecutorChannel`, trả về; target Rabbit publisher ở thread khác lỗi. JMS source đã ACK.

**Đáp án:** Nếu không có durable handoff, message có thể mất. Cần source commit/ACK sau khi có broker confirmation hoặc sau khi lưu bền inbox/outbox; kiểm tra semantics của container.

### Bài 2 — RabbitMQ confirm ACK nhưng queue rỗng

**Tình huống:** Rabbit producer nhận publisher confirm ACK nhưng consumer queue không có message.

**Đáp án:** Có thể publish tới exchange không route được theo topology. Cần kiểm tra `mandatory` returns, exchange/binding/routing key và phân biệt broker confirm với consumer delivery.

### Bài 3 — Kafka offset được copy sang target

**Tình huống:** Kafka source offset 120 được gắn vào event đích và dùng làm key chống trùng sau khi republish.

**Đáp án:** Offset là identity của record tại một partition/source topic, không phải business event ID ổn định xuyên republish. Dùng stable `eventId`; offset chỉ làm provenance.

### Bài 4 — Outbox SENT bị ghi trễ

**Tình huống:** Publisher xác nhận target nhận event nhưng process crash trước khi update outbox row `SENT`.

**Đáp án:** Sau restart, outbox worker có thể gửi lại. Target consumer cần idempotency theo stable event ID. Không thể suy ra exactly-once từ hai commit độc lập.

### Bài 5 — Source là lệnh, target là event

**Tình huống:** Source gửi `CREATE_ORDER` command, bridge tự đổi tên thành `ORDER_CREATED` rồi publish trước khi nghiệp vụ tạo đơn thành công.

**Đáp án:** Sai ngữ nghĩa. Fact event chỉ nên phát khi kết quả tương ứng đã xảy ra/được xác nhận. Bridge không được biến một command thành successful fact chỉ bằng rename.

### Bài 6 — Ordering theo đơn hàng

**Tình huống:** Kafka target ghi events với key ngẫu nhiên; consumer có thể nhận `SHIPPED` trước `PAID` của cùng đơn.

**Đáp án:** Nếu nghiệp vụ yêu cầu thứ tự per aggregate, cần key/partition strategy và consumer concurrency phù hợp; có thể thêm aggregateVersion và gap detection.

### Bài 7 — Target downtime kéo dài

**Tình huống:** Source 10.000 events/s, target 2.000 events/s. Bridge đẩy hết vào QueueChannel in-memory không giới hạn.

**Đáp án:** Backlog tăng 8.000 events/s, dễ hết RAM và mất message khi restart. Cần pause/backpressure hoặc durable outbox có capacity plan.

### Bài 8 — Hai bridge A → B và B → A

**Tình huống:** Một event liên tục quay lại hệ thống nguồn sau khi được bridge qua bên kia.

**Đáp án:** Cần provenance, route identity, hop limit và dedupe; không bật full-duplex khi chưa có chính sách chống loop.

### Bài 9 — Failure store down

**Tình huống:** Target publish thất bại, error handler không lưu được DLQ nhưng vẫn trả thành công để source ACK.

**Đáp án:** Nguy cơ silent loss. Phải giữ trách nhiệm source hoặc durable buffer khác, propagate failure và alert theo thiết kế.

### Bài 10 — Migration dual-read

**Tình huống:** Consumer cũ và mới đều gọi API tạo thanh toán khi cùng event được shadow sang broker mới.

**Đáp án:** Shadow traffic không được tạo business side effect thứ hai. Cần test consumer đọc/validate không commit nghiệp vụ hoặc business idempotency/cutover ownership rõ.

## 31. Checklist xây dựng broker-to-broker bridge

1. **Chọn pattern:** Bridge trong ứng dụng, connector-native hay CDC/outbox phù hợp nhu cầu thật.
2. **Scope rõ:** Source/destination broker, queue/topic, subscription/group, environments và owner.
3. **Direction rõ:** A→B hay hai chiều; nếu hai chiều phải chống loop.
4. **Contract rõ:** Command/event, schema version, payload, event ID và encoding.
5. **Canonical headers:** Allowlist, correlation, causation, provenance, tenant mapping.
6. **Không lộ metadata nội bộ:** Không chuyển credential, delivery tag, session object, replyTo không hợp lệ.
7. **Source semantics:** JMS transaction, AMQP ACK/NACK, Kafka offset commit được test thực.
8. **Target semantics:** Producer confirms/futures, unroutable returns và durability được kiểm chứng.
9. **Không ảo tưởng XA:** Có thiết kế rõ crash windows và guarantee đạt được.
10. **Handoff bền:** Nếu ACK source trước target publish, đã có inbox/outbox hoặc store có semantics phù hợp.
11. **Idempotency:** Stable event ID xuyên retry/redelivery/replay, target consumer chống side effect trùng.
12. **Ordering:** Scope per-aggregate/partition, concurrency và xử lý gap/out-of-order.
13. **Retry budget:** Phân biệt transient/permanent/unknown, bounded backoff và rate limit.
14. **DLQ/quarantine:** Bản ghi bền, owner, retention và đường replay được phép.
15. **Error flow fail-safe:** Recovery store down không được biến thành ACK sai.
16. **Outbox state:** PENDING, IN_FLIGHT, RETRY_PENDING, UNKNOWN, SENT được quản lý.
17. **Backpressure:** Có concurrency limit và chính sách target outage.
18. **Connection lifecycle:** Startup, reconnect, shutdown, drain và credential rotation.
19. **Security:** TLS, least privilege, tenant routing, encryption, log redaction.
20. **Test source/target thật:** Broker publishes, ACK/offset, Rabbit routing, Kafka DLT và JMS rollback.
21. **Failure injection:** Crash sau DB commit/trước ACK, sau target confirm/trước SENT.
22. **Migration plan:** Shadow/canary/cutover/rollback và event reconciliation.
23. **Observability:** Source lag, outbox oldest age, unknown outcome, DLQ và confirm latency.
24. **Runbook:** Ai dừng intake, ai replay, ai phê duyệt và khi nào đóng incident.

## 32. Tài liệu tham khảo

Tham khảo tài liệu chính thức và **đối chiếu theo phiên bản đang dùng** khi triển khai:

1. **Spring Integration Reference — JMS Support**  
   https://docs.spring.io/spring-integration/reference/jms.html
2. **Spring Integration Reference — AMQP Support**  
   https://docs.spring.io/spring-integration/reference/amqp.html
3. **Spring Integration Reference — Kafka Support**  
   https://docs.spring.io/spring-integration/reference/kafka.html
4. **Spring Integration Reference — Message Channels**  
   https://docs.spring.io/spring-integration/reference/channel.html
5. **Spring Integration Reference — Error Handling**  
   https://docs.spring.io/spring-integration/reference/error-handling.html
6. **Spring Integration Reference — Idempotent Receiver**  
   https://docs.spring.io/spring-integration/reference/handler-advice/idempotent-receiver.html
7. **Spring AMQP Reference — RabbitMQ messaging and template confirms**  
   https://docs.spring.io/spring-amqp/reference/amqp/template.html
8. **Spring Kafka Reference — Kafka template, listener and error handling**  
   https://docs.spring.io/spring-kafka/reference/

Tên classes, method overloads, transaction/publisher-confirm options và cấu hình container trong ví dụ có thể khác giữa các phiên bản **Spring Integration, Spring AMQP, Spring Kafka và Spring Boot**. Ví dụ trong bài là học liệu để phát triển tiếp và kiểm chứng trên BOM của dự án; **chưa chạy build hoặc integration tests với broker trong phạm vi bước soạn nội dung**.

## 33. Tổng kết

**Bridge giữa hai broker** trong Spring Integration là việc kết hợp **inbound adapter/gateway, MessageChannel, validation/transform/routing và outbound adapter** để chuyển message có kiểm soát giữa những hệ messaging khác nhau. `BridgeHandler` có ích cho việc nối channel nội bộ, nhưng **không thay thế** việc cấu hình endpoint và giao thức của JMS, RabbitMQ hay Kafka.

Điểm khó nhất không phải phép chuyển `Message<?>` từ channel này sang channel khác mà là **đảm bảo trách nhiệm giao nhận** khi hai broker có transaction/ack/confirmation khác nhau. Source ACK trước durable handoff gây nguy cơ mất message; target confirm trước source ACK gây nguy cơ duplicate. Một bridge tin cậy phải xác định delivery guarantee thực tế, bảo toàn stable event ID, duy trì idempotency ở đích, có retry/DLQ/replay và biết xử lý `OUTCOME_UNKNOWN`.

Với luồng quan trọng, **inbox/outbox** giúp tách vòng đời source và target, nhưng vẫn cần downstream idempotency cùng kiểm thử crash windows. **Ordering, header mapping, schema version, backpressure, bảo mật, connection lifecycle và observability** phải được thiết kế đồng thời. Khi có bằng chứng source message đã được bàn giao bền, target publish đã được xác minh theo contract và mọi ngoại lệ có owner/runbook, bridge mới thực sự hỗ trợ migration và tích hợp giữa hai broker **mà không đánh đổi tính đúng đắn của nghiệp vụ**.


