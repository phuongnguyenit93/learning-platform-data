# Microservices và kiến trúc hướng sự kiện

**Nhóm kiến thức:** Quan hệ kiến trúc trong Software Design, System Architecture và Microservices.

Microservices và kiến trúc hướng sự kiện (Event-Driven Architecture – EDA) thường được sử dụng cùng nhau, nhưng chúng giải quyết hai chiều khác nhau của kiến trúc. **Microservices xác định cách chia hệ thống thành các đơn vị nghiệp vụ, dữ liệu và triển khai tương đối độc lập**; **EDA xác định cách các thành phần công bố và phản ứng với những sự kiện đã xảy ra**. Một hệ thống microservices có thể giao tiếp chủ yếu bằng HTTP/gRPC đồng bộ. Một ứng dụng đơn khối cũng có thể dùng domain event nội bộ. Kết hợp hai cách tiếp cận có thể giảm phụ thuộc thời gian giữa các dịch vụ, nhưng đồng thời đưa vào eventual consistency, duplicate delivery, ordering, retry, schema evolution và yêu cầu quan sát xuyên hệ thống.

Ví dụ trong thương mại điện tử, Checkout tạo đơn hàng rồi phát OrderCreated. Inventory giữ hàng, Payment xử lý thanh toán, Fulfillment chuẩn bị giao hàng và Notification gửi thông báo. Các consumer xử lý theo nhịp riêng; Checkout không phải gọi và chờ mọi dịch vụ phụ hoàn tất trong cùng một HTTP request. Tuy nhiên, event được publish không có nghĩa mọi bước nghiệp vụ đã hoàn tất. Một quy trình có thể vẫn đang PENDING, có thể thất bại ở bước sau và cần compensation.

Bài học này giải thích ranh giới giữa microservices và EDA, cách chọn sync/async, phân biệt command với event, domain event với integration event, queue với pub/sub, EDA với event sourcing, choreography với orchestration; sau đó trình bày transactional outbox, idempotency, ordering, saga, schema evolution, observability, security, kiểm thử và vận hành. Ví dụ dùng Java/Spring Boot và message broker.

## 1. Hai khái niệm, hai câu hỏi kiến trúc

**Microservices** tổ chức hệ thống thành các dịch vụ có capability nghiệp vụ, dữ liệu, contract và vòng đời triển khai tương đối độc lập. Một service nên có:
- Bounded context hoặc capability được xác định.
- Owner chịu trách nhiệm về code, dữ liệu và vận hành.
- API/event contract được công bố.
- Database/schema do service sở hữu.
- Pipeline, SLO, dashboard và runbook.
- Khả năng thay đổi mà không bắt buộc phát hành mọi service khác, khi contract vẫn tương thích.

**Event-Driven Architecture** tổ chức giao tiếp hoặc kích hoạt công việc quanh các event biểu diễn điều đã xảy ra. Producer phát sự kiện; một hoặc nhiều consumer đăng ký nhận và xử lý. Event có thể được chuyển qua queue, pub/sub, event bus hoặc distributed log.

| Câu hỏi | Microservices | EDA |
|---|---|---|
| Chia hệ thống theo gì? | Domain/capability và ownership | Không tự xác định ranh giới |
| Ai sở hữu dữ liệu? | Service owner | Event công bố thông tin qua ranh giới |
| Giao tiếp thế nào? | Sync hoặc async | Chủ yếu event/message |
| Deploy ra sao? | Theo contract của từng service | Producer/consumer cùng tồn tại nhiều schema version |
| Khi consumer chậm? | Sync call có thể chờ hoặc timeout | Broker có thể đệm, consumer xử lý sau |
| Consistency? | Tùy transaction boundary | Thường eventual giữa các consumer |
| Quan sát? | Theo service và dependency | Thêm publish, delivery, lag, retry, DLQ và workflow |

**Microservices không bắt buộc dùng EDA**, và EDA không bắt buộc phải có microservices. Một hệ thống có thể dùng domain event nội bộ trong modular monolith rồi chỉ công bố integration event khi thật sự cần giao tiếp xuyên ranh giới.

## 2. Kết hợp microservices và EDA

Luồng đồng bộ:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant O as Order
    participant I as Inventory
    participant P as Payment
    participant N as Notification
    C->>O: POST /orders
    O->>I: Reserve stock
    I-->>O: Reserved
    O->>P: Authorize payment
    P-->>O: Authorized
    O->>N: Send confirmation
    N-->>O: Accepted
    O-->>C: Order response
~~~

Nếu tất cả lời gọi nằm trên critical path, thời gian phản hồi và khả năng thành công phụ thuộc vào Inventory, Payment và Notification. Một dependency chậm có thể kéo dài request hoặc gây timeout dây chuyền.

Luồng bất đồng bộ:

~~~mermaid
flowchart LR
    C["Client"] --> O["Order Service"]
    O --> DB[("Orders DB + Outbox")]
    DB --> PUB["Outbox Publisher"]
    PUB --> B[("Event Broker")]
    B --> I["Inventory Consumer"]
    B --> P["Payment Consumer"]
    B --> N["Notification Consumer"]
    I --> IDB[("Inventory DB")]
    P --> PDB[("Payment DB")]
    N --> NDB[("Notification state")]
~~~

Order Service ghi đơn và outbox trong cùng transaction local. Publisher chuyển event tới broker. Consumer cập nhật domain của mình và có thể phát event kết quả.

Lợi ích:
- Producer không cần biết toàn bộ consumer.
- Consumer có thể scale và deploy riêng nếu contract tương thích.
- Broker đệm message khi consumer tạm dừng.
- Thêm consumer mới ít cần sửa producer.
- Tác vụ không cần phản hồi tức thời được tách khỏi request chính.
- Lỗi một consumer không nhất thiết làm request tạo đơn thất bại ngay.

Đánh đổi:
- Trạng thái nghiệp vụ chưa hoàn tất khi API trả về.
- Cần xử lý duplicate, retry, ordering và poison message.
- Debug cần nối trace qua nhiều service.
- Người dùng cần trạng thái trung gian và cách tra cứu.
- Broker, schema registry, retention và on-call làm tăng chi phí.
- Quy trình có thể thất bại sau khi request ban đầu đã được chấp nhận.

EDA giảm phụ thuộc đồng bộ nhưng làm tăng trách nhiệm quản lý trạng thái, deadline và bằng chứng xử lý.

## 3. Command và event khác nhau

**Command** là yêu cầu một thành phần thực hiện hành động: ReserveInventory, AuthorizePayment, CapturePayment.

**Event** là thông báo một việc đã xảy ra: InventoryReserved, PaymentAuthorized, PaymentCaptured.

| Đặc điểm | Command | Event |
|---|---|---|
| Ý nghĩa | Yêu cầu hành động | Sự kiện đã xảy ra |
| Cách đặt tên | Mệnh lệnh | Quá khứ/trạng thái đã xảy ra |
| Người nhận | Handler được xác định | Một hoặc nhiều subscriber |
| Kết quả | Có thể thành công hoặc thất bại | Có thể kích hoạt event khác |
| Quyền quyết định | Bên nhận quyết định có thực hiện | Producer chịu trách nhiệm về sự thật công bố |

Không gọi một command là event chỉ vì gửi nó qua Kafka. Transport không thay đổi semantics.

Ví dụ:
1. Order Service phát ReserveStock.
2. Inventory xử lý và phát InventoryReserved hoặc InventoryReservationRejected.
3. Order Process Manager phản ứng với kết quả để tiếp tục hoặc hủy quy trình.

OrderCreated phải có nghĩa đơn đã được tạo và commit theo contract của Order Service, không phải “hãy tạo đơn giúp tôi”. Event không nên công bố một hành động chưa xảy ra như thể nó đã thành công.

## 4. Domain event và integration event

**Domain event** biểu diễn điều có ý nghĩa bên trong bounded context: OrderPlaced, CreditLimitExceeded, ShipmentDispatched.

**Integration event** là thông tin được công bố qua ranh giới service để consumer khác phản ứng. Nó cần contract ổn định, schema/version và semantics rõ.

Domain event có thể chứa chi tiết nội bộ. Không nhất thiết đưa nguyên domain object ra broker. Service nên chuyển thành integration event phù hợp với nhu cầu consumer.

~~~text
Domain event nội bộ:
  OrderPlaced(orderId, customerId, internalPricingDecision,
              fraudSignals, domainMetadata)

Integration event:
  OrderCreated(eventId, orderId, customerReference,
               currency, totalAmount, occurredAt)
~~~

Không phát fraud score, PII hoặc cấu trúc database nội bộ nếu consumer không cần. Integration contract nên ổn định theo nhu cầu sử dụng, không phản chiếu mọi thay đổi entity.

## 5. Event notification và event-carried state transfer

**Event notification** chỉ thông báo có thay đổi; consumer gọi API producer nếu cần chi tiết.

~~~json
{
  "eventId": "evt-1001",
  "type": "CustomerAddressChanged",
  "customerId": "cus-42",
  "occurredAt": "2026-11-12T03:00:00Z"
}
~~~

Event nhỏ và ít sao chép dữ liệu, nhưng consumer lại phụ thuộc API availability và có thể tạo thêm lời gọi đồng bộ.

**Event-carried state transfer** mang phần dữ liệu cần thiết để consumer cập nhật projection mà không gọi lại producer.

~~~json
{
  "eventId": "evt-1002",
  "type": "ProductPriceChanged",
  "productId": "prd-77",
  "currency": "VND",
  "amountMinor": 125000,
  "version": 18,
  "occurredAt": "2026-11-12T03:05:00Z"
}
~~~

Consumer xử lý độc lập hơn, đổi lại payload lớn và dữ liệu được sao chép. Chọn dựa trên nhu cầu:
- Notification khi consumer chỉ cần biết có thay đổi.
- State transfer khi consumer cần dữ liệu ổn định để xử lý offline.
- Reference/token khi payload có dữ liệu nhạy cảm.
- Version/freshness contract khi consumer không thể dùng snapshot cũ.

## 6. Queue, pub/sub và distributed log

**Point-to-point queue:** một message thường được một worker trong nhóm xử lý thành công; nhiều worker cạnh tranh để tăng throughput. Ví dụ job gửi email.

**Publish/subscribe:** producer công bố event, nhiều subscription độc lập nhận thông điệp. Ví dụ OrderCreated cho Fulfillment và Analytics.

**Distributed append-only log:** event được ghi theo partition và consumer đọc theo offset; consumer group có thể replay trong giới hạn retention. Ví dụ Kafka.

| Mô hình | Phù hợp | Cần hiểu |
|---|---|---|
| Queue | Task được giao cho worker | Ack, visibility timeout, retry, DLQ |
| Pub/sub | Một event có nhiều subscriber | Subscription, delivery, retention |
| Log/stream | Replay và xử lý theo offset | Partition, ordering, offset |
| Event bus | Routing theo type/attribute | Binding, routing rule, retry |

Broker không có guarantee giống nhau. Queue managed, Kafka và pub/sub có semantics khác nhau. Thiết kế theo behavior thực tế của sản phẩm đang dùng; không giả định từ ngữ exactly-once hoặc FIFO có nghĩa giống nhau ở mọi lớp.

## 7. Chọn giao tiếp đồng bộ hay bất đồng bộ

Không nên chuyển mọi HTTP call thành event.

| Tình huống | Cách thường phù hợp | Lý do |
|---|---|---|
| Cần câu trả lời ngay | HTTP/gRPC sync | Request/response rõ |
| Đọc dữ liệu nhỏ cần nhất quán ngay | Sync API | Tránh broker không cần thiết |
| Tác vụ dài, không cần chờ | Async command/job | Giải phóng request thread |
| Một sự kiện có nhiều consumer | Pub/sub event | Producer ít biết consumer |
| Công việc nền có thể retry | Queue/stream | Buffer và retry |
| Dựng read model | Event-carried state/CDC | Consumer cập nhật projection |
| Quy trình nhiều domain | Saga/workflow | Theo dõi trạng thái và compensation |

Quy tắc thực tế: dùng sync cho quyết định cần câu trả lời ngay; dùng async cho công việc có thể tiếp tục sau, fan-out hoặc cần tách thời điểm xử lý.

Nếu Checkout cần biết Inventory giữ hàng trước khi xác nhận order, có thể gọi sync hoặc gửi command rồi trả trạng thái PENDING để workflow tiếp tục async. Lựa chọn phản ánh UX và business contract, không phải sở thích công nghệ.

## 8. EDA không đồng nghĩa event sourcing

**EDA** là các thành phần giao tiếp/kích hoạt xử lý qua event. Dữ liệu chính vẫn có thể nằm trong bảng trạng thái hiện tại.

**Event sourcing** lưu thay đổi domain dưới dạng chuỗi event bất biến; event store là nguồn sự thật của lịch sử. Trạng thái hiện tại được dựng từ event, đôi khi dùng snapshot để tăng tốc.

| Tiêu chí | EDA thông thường | Event sourcing |
|---|---|---|
| Event | Thông điệp tích hợp/notification | Nguồn sự thật của thay đổi |
| Current state | DB trạng thái hiện tại | Có thể dựng từ event |
| Replay | Tùy retention/semantics | Năng lực cốt lõi |
| Audit | Có thể cần bổ sung | Lịch sử event rõ |
| Độ phức tạp | Messaging và consistency | Thêm event store, replay, upcaster |
| Phù hợp | Decoupling và async workflow | Audit mạnh, lịch sử domain quan trọng |

Không cần event sourcing chỉ vì dùng Kafka. DB truyền thống + transactional outbox có thể đáp ứng EDA mà không biến event log thành nguồn dữ liệu chính.

## 9. Event boundary và event envelope

Event nên được phát bởi service sở hữu sự thật nghiệp vụ:
- Orders phát OrderCreated khi đơn được commit.
- Payments phát PaymentAuthorized khi provider xác nhận authorization theo contract.
- Inventory phát StockReserved khi reservation thành công.
- Fulfillment phát ShipmentDispatched khi shipment được bàn giao theo định nghĩa.

Không để service khác đọc bảng database rồi tự phát event thay owner.

Một event contract nên nêu:
- Event type và owner.
- Event ID duy nhất.
- Aggregate ID và version.
- Schema version.
- OccurredAt/publishedAt nếu cần.
- Correlation/causation ID.
- Payload và semantics.
- Partition key/ordering expectations.
- PII classification, retention và compatibility policy.

Ví dụ envelope:

~~~json
{
  "eventId": "evt-01JXYZ",
  "eventType": "OrderCreated",
  "schemaVersion": 2,
  "source": "orders-service",
  "subject": "orders/ord-123",
  "occurredAt": "2026-11-12T03:00:00Z",
  "publishedAt": "2026-11-12T03:00:01Z",
  "correlationId": "corr-789",
  "causationId": "cmd-456",
  "traceparent": "00-...",
  "data": {
    "orderId": "ord-123",
    "customerRef": "cus-42",
    "currency": "VND",
    "totalMinor": 125000
  }
}
~~~

Metadata hỗ trợ routing, idempotency, tracing và audit. Payload chứa dữ liệu nghiệp vụ cần thiết. Không đưa secret, token hoặc PII thô vào event nếu consumer không cần.

## 10. Transactional outbox: nối DB commit với publish

Một lỗi kinh điển:
1. Order Service ghi Orders DB thành công.
2. Process crash trước khi publish OrderCreated.
3. Đơn tồn tại nhưng consumer không nhận event.

Nếu publish trước rồi DB rollback, consumer có thể xử lý event cho record không tồn tại. Đây là vấn đề dual-write giữa database và broker.

**Transactional outbox** ghi trạng thái nghiệp vụ và event trong cùng transaction DB:

~~~mermaid
flowchart TD
    A["Create order"] --> T["One DB transaction"]
    T --> O[("Orders table")]
    T --> X[("Outbox table")]
    X --> P["Outbox publisher"]
    P --> B[("Broker")]
    B --> C["Consumers"]
~~~

Quy trình:
1. Bắt đầu transaction.
2. Ghi Order.
3. Ghi event vào Outbox.
4. Commit một lần.
5. Publisher đọc row chưa gửi và publish.
6. Đánh dấu published theo cơ chế an toàn.
7. Consumer xử lý idempotent.

Nếu crash sau publish nhưng trước khi đánh dấu, event có thể gửi lại. Outbox không tự bảo đảm exactly-once end-to-end; nó giảm khoảng hở giữa DB commit và ý định publish. Consumer vẫn cần idempotency.

### 10.1. Bảng outbox mẫu

~~~sql
CREATE TABLE outbox_events (
    event_id       UUID PRIMARY KEY,
    aggregate_type VARCHAR(100) NOT NULL,
    aggregate_id   VARCHAR(100) NOT NULL,
    event_type     VARCHAR(200) NOT NULL,
    schema_version INTEGER NOT NULL,
    payload        JSONB NOT NULL,
    occurred_at    TIMESTAMPTZ NOT NULL,
    published_at   TIMESTAMPTZ,
    attempts       INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX idx_outbox_unpublished
    ON outbox_events (occurred_at)
    WHERE published_at IS NULL;
~~~

Schema là ví dụ PostgreSQL. Production có thể dùng lease/claim, khóa hàng, CDC connector hoặc log-based publisher để tránh nhiều publisher xử lý cùng row. Cần retention, partitioning và cleanup theo audit policy.

Publisher nên có retry giới hạn, backoff, event ID ổn định, metrics backlog/oldest age và xử lý poison row để một event lỗi không chặn toàn bảng.

## 11. Java/Spring Boot: ghi domain và outbox trong transaction

~~~java
import java.time.Instant;
import java.util.UUID;

record CreateOrderCommand(
    String customerId,
    long totalMinor,
    String currency
) {}

record OrderCreated(
    UUID eventId,
    String orderId,
    String customerId,
    long totalMinor,
    String currency,
    Instant occurredAt
) {}

@Service
class OrderApplicationService {
    private final OrderRepository orders;
    private final OutboxRepository outbox;
    private final ObjectMapper objectMapper;

    OrderApplicationService(
        OrderRepository orders,
        OutboxRepository outbox,
        ObjectMapper objectMapper
    ) {
        this.orders = orders;
        this.outbox = outbox;
        this.objectMapper = objectMapper;
    }

    @Transactional
    public String create(CreateOrderCommand command) {
        Order order = Order.create(
            command.customerId(),
            command.totalMinor(),
            command.currency()
        );
        orders.save(order);

        var event = new OrderCreated(
            UUID.randomUUID(),
            order.id(),
            command.customerId(),
            command.totalMinor(),
            command.currency(),
            Instant.now()
        );

        outbox.save(OutboxRecord.from(
            event.eventId(),
            "OrderCreated",
            1,
            serialize(event)
        ));

        return order.id();
    }

    private String serialize(Object value) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (JsonProcessingException e) {
            throw new IllegalStateException("Cannot serialize event", e);
        }
    }
}
~~~

Ví dụ giả định repository dùng chung transaction manager và cùng database. Nếu outbox ở DB khác, transaction này không atomic. Timestamp nên tuân theo quy ước của hệ thống, không để client tùy ý quyết định thời điểm nghiệp vụ.

## 12. Consumer idempotency và Inbox

Broker có thể giao message nhiều lần:
- Consumer xử lý xong nhưng ACK thất bại.
- Process crash trước khi commit offset.
- Publisher timeout và gửi lại.
- Outbox publisher crash sau publish.
- Retry policy của broker giao lại message.

Consumer nên **idempotent**: cùng một event được xử lý nhiều lần không tạo thêm hiệu ứng nghiệp vụ.

Một bảng Inbox:

~~~sql
CREATE TABLE processed_messages (
    consumer_name VARCHAR(100) NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Trong cùng transaction local:
1. Insert event ID vào Inbox.
2. Nếu unique conflict, message đã xử lý; bỏ qua.
3. Nếu insert mới, áp dụng thay đổi domain.
4. Commit Inbox và state cùng transaction.
5. ACK/commit offset theo semantics broker.

Nếu đánh dấu processed và cập nhật domain ở hai transaction riêng, crash giữa hai bước có thể làm mất xử lý. Inbox và business update phải atomic trong cùng data store hoặc có giao thức recovery tương đương.

~~~java
@Service
class InventoryEventHandler {
    private final InboxRepository inbox;
    private final InventoryRepository inventory;

    InventoryEventHandler(
        InboxRepository inbox,
        InventoryRepository inventory
    ) {
        this.inbox = inbox;
        this.inventory = inventory;
    }

    @Transactional
    public void handle(InventoryReservationRequested event) {
        boolean firstDelivery = inbox.tryInsert(
            "inventory-reservation",
            event.eventId()
        );

        if (!firstDelivery) {
            return;
        }

        inventory.reserve(event.orderId(), event.items());
    }
}
~~~

Đây là ví dụ đơn giản. Reservation từ chối vì thiếu hàng là kết quả nghiệp vụ cần lưu và phát event, không phải exception để retry vô hạn. Nếu consumer gọi payment provider, Inbox local không thể atomic với provider; cần idempotency key, workflow state và reconciliation.

## 13. Delivery semantics

**At-most-once:** message có thể mất nhưng không được giao lại theo cơ chế đó. Chỉ phù hợp dữ liệu có thể bỏ qua.

**At-least-once:** message được giao một hoặc nhiều lần đến khi xác nhận theo policy. Phổ biến vì giảm nguy cơ mất message, nhưng consumer phải xử lý duplicate.

**Exactly-once:** phải chỉ rõ phạm vi. Broker có thể hỗ trợ transaction/idempotent producer trong phạm vi của nó, nhưng không tự bảo đảm DB, payment provider và email chỉ tạo side effect một lần.

Đối với business workflow, cần:
- Event ID ổn định.
- Idempotency key theo nghiệp vụ.
- Inbox/outbox.
- Transaction boundary rõ.
- Deduplication và reconciliation.
- Retry có giới hạn.
- Provider idempotency khi có hỗ trợ.

Không dựa vào nhãn exactly-once để bỏ kiểm soát ở các hệ thống bên ngoài broker.

## 14. Ordering, partition key và version

Giả sử một Order có:
- OrderCreated version 1.
- OrderConfirmed version 2.
- OrderCancelled version 3.

Nếu consumer nhận Cancelled trước Confirmed do retry hoặc partition khác nhau, state có thể sai.

Chiến lược:
- Partition theo aggregate ID để event cùng aggregate vào cùng partition.
- Gắn sequence/version tăng dần.
- Consumer kiểm tra expected version.
- Buffer event đến sớm nếu thiếu version trước.
- Deduplicate và reconciliation khi có gap.
- Không giả định thứ tự giữa các aggregate khác nhau.

Kafka bảo đảm thứ tự trong một partition, không phải toàn bộ topic/cluster. Một queue FIFO có semantics và giới hạn khác. Chọn broker/key theo thứ tự nghiệp vụ cần giữ.

Nếu projection chỉ cần trạng thái mới nhất, event cũ có thể bị bỏ qua theo version. Nhưng nếu event là business fact cần ghi sổ, bỏ event cũ có thể làm mất giao dịch hợp lệ. Phải phân biệt state replication với fact processing.

Không dùng wall-clock timestamp làm thứ tự duy nhất khi nhiều producer/region có clock skew. Aggregate version do owner phát hành thường đáng tin hơn.

## 15. Retry, backoff và dead-letter queue

Không phải lỗi nào cũng nên retry:
- Network timeout tạm thời có thể retry.
- Rate limit có thể retry sau thời gian chỉ định.
- Database unavailable có thể retry có giới hạn.
- Payload sai schema là lỗi permanent.
- Business rejection như insufficient stock không nên retry vô hạn.
- Authorization denied thường cần sửa cấu hình.

Policy nên:
1. Phân loại transient/permanent.
2. Retry với exponential backoff và jitter.
3. Đặt max attempts hoặc max delivery age.
4. Ghi attempt/error metadata.
5. Đưa poison message vào DLQ/quarantine.
6. Alert theo DLQ depth và oldest message age.
7. Inspect, sửa dữ liệu/code và replay có kiểm soát.

DLQ có thể chứa PII và giao dịch; cần encryption, retention và quyền truy cập. Không log toàn bộ payload nhạy cảm.

Retry ngay lập tức có thể tạo retry storm. Giới hạn concurrency, dùng backoff, circuit breaker và backpressure để bảo vệ dependency. Không retry vô hạn một lỗi validation permanent.

## 16. Saga: nhiều transaction local trong một workflow

Một giao dịch xuyên nhiều microservices thường không nằm trong một ACID transaction chung. **Saga** chia quy trình thành các transaction local; mỗi bước phát event/command và nếu thất bại thì thực hiện compensation theo nghiệp vụ.

Ví dụ:
1. Orders tạo Order PENDING.
2. Inventory reserve stock.
3. Payments authorize.
4. Orders confirm.
5. Fulfillment bắt đầu.

Nếu Payment bị từ chối, Orders yêu cầu Inventory release stock rồi đánh dấu OrderRejected.

~~~mermaid
sequenceDiagram
    participant O as Order
    participant I as Inventory
    participant P as Payment
    O->>I: ReserveInventory
    I-->>O: InventoryReserved
    O->>P: AuthorizePayment
    P-->>O: PaymentRejected
    O->>I: ReleaseInventory
    I-->>O: InventoryReleased
    O-->>O: OrderRejected
~~~

**Compensation không phải rollback thời gian.** Nếu đã capture tiền, có thể phải refund; nếu đã gửi hàng, cần quy trình trả hàng. Một số side effect không thể đảo ngược hoàn toàn.

Mỗi saga cần:
- Saga ID/correlation ID.
- Trạng thái và bước hiện tại.
- Timeout/deadline.
- Idempotency cho command/event.
- Compensation và retry policy.
- Owner khi compensation thất bại.
- Reconciliation cho trạng thái không xác định.

Nếu Payment provider timeout sau khi gửi authorize, không biết provider đã authorize chưa. Trước khi retry, cần query/reconcile bằng idempotency key; gửi lệnh mới có thể tạo authorization trùng.

## 17. Choreography và orchestration

**Choreography:** mỗi service phản ứng với event và phát event tiếp theo, không có coordinator trung tâm.

Ưu điểm: domain owner giữ hành động; phù hợp fan-out và luồng đơn giản. Đánh đổi: workflow nhiều nhánh khó nhìn, event chain khó debug và trạng thái tổng thể phân tán.

**Orchestration:** một saga orchestrator/process manager giữ trạng thái và gửi command tới participant.

Ưu điểm: luồng tổng thể, timeout và compensation rõ hơn. Đánh đổi: coordinator quan trọng cần HA, có thể biết quá nhiều logic domain và phải quản lý version workflow.

| Tiêu chí | Choreography | Orchestration |
|---|---|---|
| Điều phối | Phân tán qua event | Workflow owner |
| Phù hợp | Luồng đơn giản, fan-out | Nhiều bước/nhánh |
| Quan sát | Cần correlation/flow view | Workflow state tập trung |
| Rủi ro | Event chain rối | Coordinator thành điểm nghẽn |
| Test | Kiểm tra tương tác event | Test state machine |

Nếu chỉ fan-out một event cho ba consumer độc lập, choreography tự nhiên. Nếu có nhiều bước, compensation, timeout và can thiệp thủ công, orchestration thường rõ ràng hơn. Orchestrator nên gửi command qua contract, không truy cập trực tiếp database của participant.

## 18. Eventual consistency và trải nghiệm người dùng

Khi Order Service commit đơn và phát OrderCreated, Inventory/Payment xử lý sau. Trong một khoảng thời gian:
- Orders hiển thị PENDING.
- Inventory đang RESERVING.
- Payment chưa có transaction.
- Notification chưa gửi.

Đây là eventual consistency nếu hệ thống hội tụ về trạng thái hợp lệ sau khi event được xử lý.

Cần định nghĩa:
- Người dùng thấy trạng thái trung gian nào?
- Bao lâu là bình thường?
- SLO freshness là bao nhiêu?
- Quá deadline thì alert/escalation thế nào?
- Có retry/replay không?
- Nếu bước bị từ chối, trạng thái tổng thể là gì?

Eventual consistency không phải lý do để dữ liệu sai vô thời hạn. Phải có deadline, theo dõi lag, reconciliation và quy trình xử lý trạng thái không hội tụ.

Nếu API trả sau khi lưu Order PENDING, có thể dùng response:

~~~json
{
  "orderId": "ord-123",
  "status": "PENDING",
  "statusUrl": "/orders/ord-123",
  "acceptedAt": "2026-11-12T03:00:00Z"
}
~~~

Client poll status với backoff, nhận webhook, SSE/WebSocket hoặc push notification tùy use case. Contract phải nói rõ 202 Accepted là đã nhận yêu cầu, không đồng nghĩa thanh toán/đơn hàng hoàn tất.

## 19. Idempotency key cho request và side effect

Client có thể timeout sau khi server commit đơn rồi gửi lại POST. Nếu không có idempotency, có thể tạo hai đơn.

Server lưu:
- Idempotency key.
- Client/tenant scope.
- Hash payload.
- Kết quả/resource ID.
- Trạng thái xử lý.
- Expiry theo chính sách.

Cùng key và cùng payload thì trả kết quả trước đó. Cùng key nhưng payload khác thì báo conflict.

Phân biệt:
- Command ID chống xử lý lặp cùng yêu cầu.
- Event ID chống giao event lặp.
- Business idempotency key chống side effect nghiệp vụ trùng, ví dụ capture payment cho cùng order/attempt.

Key phải ổn định qua retry của cùng thao tác; không tạo UUID mới ở mỗi lần client gửi lại.

## 20. Schema evolution và versioning

Producer có thể deploy độc lập với consumer, vì vậy schema phải hỗ trợ nhiều version cùng tồn tại.

Nguyên tắc:
- Thêm field optional có default/semantics rõ thường dễ tương thích.
- Không đổi nghĩa field hiện tại mà giữ nguyên tên.
- Không tái sử dụng field number Protobuf đã xóa.
- Xử lý unknown enum/field theo serializer thực tế.
- Version event khi thay đổi semantic hoặc contract-breaking.
- Giữ fixture từ version lịch sử còn trong retention.
- Có deprecation policy và consumer inventory.

Schema validation pass không bảo đảm semantic compatibility. Đổi amount từ đơn vị tiền lớn sang minor unit có thể vẫn là integer nhưng khiến consumer tính sai.

Schema registry có thể kiểm tra backward, forward, full hoặc transitive theo cấu hình. Cần biết chính xác chế độ và serializer đang chạy. Không chỉ nhìn việc đăng ký schema thành công.

Các lựa chọn:
- Thêm field tương thích, giữ event type.
- Tạo event type mới khi semantics thay đổi đáng kể.
- Dùng adapter/upcaster khi replay event lịch sử.
- Dual-publish trong migration window chỉ khi có event identity và consumer policy chống side effect trùng.

## 21. Consumer group, scaling và backpressure

Trong Kafka, consumer group chia partition cho worker:
- Số consumer hoạt động trong group bị giới hạn bởi số partition.
- Tăng consumer quá số partition không tăng parallelism.
- Restart/rebalance có thể tạm dừng xử lý.
- Consumer chậm làm lag tăng.
- Key ordering trong partition cần được giữ nếu business phụ thuộc.

Theo dõi:
- Consumer lag theo partition.
- Oldest unprocessed event age.
- Processing latency.
- Rebalance frequency/duration.
- Error/retry/DLQ.
- Throughput.
- Offset commit và duplicate behavior.

Khi producer nhanh hơn consumer, backlog tăng. Broker đệm nhưng không tạo năng lực vô hạn. Có thể giới hạn producer rate, tăng concurrency trong capacity, batch, giới hạn in-flight, pause partition, tách priority và scale downstream.

Không tăng worker vô hạn: nhiều consumer có thể làm DB pool quá tải. Không drop event quan trọng chỉ để giảm lag; cần replay/reconciliation có audit.

## 22. Event time và processing time

Một event có nhiều mốc:
- Occurred time: lúc nghiệp vụ xảy ra.
- Published time: lúc đưa vào broker.
- Consumed time: lúc consumer nhận.
- Processed time: lúc consumer hoàn tất.
- Committed time: lúc state/offset được xác nhận.

Sự khác nhau giúp phân biệt producer delay, broker delay và consumer processing delay.

Với stream analytics, event có thể đến trễ hoặc sai thứ tự. Watermark biểu diễn mức thời gian event được xem là tương đối đầy đủ; nó không tự giải quyết event trễ. Chính sách late event phải nêu có cập nhật kết quả, lưu side output hay bỏ qua.

Không dùng timestamp client làm nguồn duy nhất cho ordering/audit nếu client có thể gửi sai đồng hồ.

## 23. Observability xuyên event flow

Một request HTTP có trace context; khi phát event, truyền context phù hợp để consumer nối luồng.

Metadata nên có:
- traceparent/tracing context.
- correlationId cho workflow.
- causationId cho event/command trực tiếp.
- eventId duy nhất.
- aggregateId/version.
- producer/consumer identity.
- schema version.

Dashboard cần theo dõi:
- Publish rate/error.
- Outbox backlog và oldest age.
- Broker availability/throughput.
- Consumer lag và processing duration.
- Retry attempts và DLQ depth.
- Duplicate/dedup count.
- End-to-end business completion time.
- Event age từ occurredAt đến processedAt.
- Saga/workflow PENDING quá deadline.

Broker khỏe nhưng consumer không commit offset hoặc business state không hội tụ vẫn là lỗi nghiệp vụ. Trace có sampling/retention; với giao dịch quan trọng vẫn cần business audit record bền vững gắn eventId/transaction ID.

## 24. Security và privacy

Broker là mặt phẳng giao tiếp chứa dữ liệu nhiều service tiêu thụ. Cần:
- Authentication cho producer/consumer.
- Authorization theo topic/queue/action.
- TLS/mTLS và encryption at rest.
- Key/secret lifecycle.
- Phân loại PII/secret trong payload.
- Data minimization.
- Retention/TTL theo mục đích.
- Audit truy cập và thay đổi ACL.
- Schema validation.
- Quyền truy cập DLQ/replay/export.

Consumer không cần địa chỉ đầy đủ có thể chỉ nhận customer reference. Nếu cần dữ liệu, gọi API có authorization hoặc nhận projection phù hợp.

Event đã publish có thể khó thu hồi vì nhiều consumer đã lưu bản sao. Xóa topic không xóa mọi bản sao downstream, backup hay data lake. Thiết kế payload tối thiểu và retention trước khi phát.

## 25. Failure modes thường gặp

| Failure mode | Biểu hiện | Kiểm soát |
|---|---|---|
| DB commit nhưng event mất | Consumer không biết record mới | Transactional outbox/CDC |
| Event gửi trùng | Duplicate side effect | Event ID, Inbox, idempotency |
| Event sai thứ tự | State regression | Partition key, version/sequence |
| Consumer chết | Lag/backlog tăng | Retry, restart, autoscaling, alert |
| Poison message | Một record lỗi lặp mãi | DLQ/quarantine, inspect/replay |
| Schema incompatibility | Consumer parse thất bại | Contract tests, schema policy |
| Retry storm | Dependency quá tải | Backoff, jitter, rate limit |
| Mất correlation | Không nối được workflow | Trace context, correlation/causation |
| Split-brain producer | Event conflict/duplicate | Single ownership, fencing |
| Event loop | A phát B, B phát lại A | Causal design, loop guard |
| Side effect timeout | Không biết đã thực hiện chưa | Provider idempotency, reconciliation |
| Broker outage | Publish/consume dừng | Outbox backlog, HA, recovery plan |

Thiết kế tốt giả định process có thể crash ở mọi thời điểm: trước publish, sau publish, trước DB commit, sau side effect và trước ACK. Mỗi điểm cần trạng thái phục hồi rõ.

## 26. CDC và event-driven integration

Change Data Capture đọc thay đổi từ transaction log của database và phát ra stream. Nó hữu ích khi tích hợp legacy khó sửa code, đồng bộ read model/search/data platform hoặc tránh dual-write trực tiếp.

Nhưng CDC thường phát database change, không tự mang business semantics. Một row update không tự chứng minh OrderConfirmed theo nghĩa nghiệp vụ.

Phân biệt:
- Business event: ý nghĩa domain do owner công bố.
- CDC record: thay đổi ở storage layer.
- Integration event: contract thiết kế cho consumer khác.

Có thể dùng CDC để vận chuyển outbox table, giữ business semantics và tận dụng transaction log. Không nên công bố toàn bộ bảng nội bộ làm contract lâu dài nếu schema không được thiết kế cho consumer.

## 27. Replay và rebuild read model

Replay hữu ích khi consumer có bug đã sửa, cần dựng lại projection, thêm consumer mới hoặc chuyển broker/data store.

Cần chuẩn bị:
- Retention đủ dài hoặc archive.
- Schema lịch sử đọc được.
- Upcaster/adapter.
- Idempotency/replay mode.
- Tốc độ replay không làm nghẽn production.
- Checkpoint và resume.
- Reconciliation sau replay.
- Tách side effect khỏi projection rebuild.

Replay không được gửi lại email/payment/shipment như event vừa xảy ra. Consumer cần phân biệt chế độ rebuild projection với chế độ side effect; có thể dùng consumer group/sink riêng hoặc replay adapter không có quyền external action.

## 28. Kiểm thử producer và consumer

Test strategy nên có nhiều tầng:

**Unit test**
- Domain event được tạo đúng khi state transition hợp lệ.
- Không phát event khi transaction nghiệp vụ thất bại.
- Payload có đúng semantics.

**Component test**
- Outbox row và domain record commit cùng transaction.
- Publisher claim/retry đúng.
- Inbox và business update atomic.
- DLQ/invalid payload được phân loại.

**Contract test**
- Producer schema tương thích với consumer versions.
- Consumer xử lý unknown optional field/enum.
- Semantic fixture đúng currency/status/version.

**Integration test**
- Broker/serializer/partition thực.
- Offset/ack/retry.
- Duplicate delivery và consumer restart.
- Publisher crash windows.

**End-to-end test**
- Critical journey xuyên service.
- Saga success và compensation.
- Workflow timeout/replay.
- Data reconciliation.

Không chỉ test happy path. Crash, retry và duplicate thường quyết định EDA có an toàn hay không. Với Java, Testcontainers có thể chạy PostgreSQL và broker thật cho integration tests; không cần khởi động hạ tầng đó cho mọi unit test.

## 29. Chọn choreography hay orchestration

Hỏi:
- Có bao nhiêu bước và nhánh?
- Compensation/timeout có phức tạp không?
- Cần audit trạng thái tổng thể ở một nơi không?
- Một team có ownership workflow không?
- Consumer có thể phản ứng độc lập không?
- Có nguy cơ event chain/vòng lặp khó hiểu không?
- Có cần can thiệp thủ công không?

Nếu chỉ fan-out một event cho ba consumer độc lập, choreography tự nhiên. Nếu có nhiều bước, compensation, timeout và trạng thái tổng thể, orchestration có thể rõ hơn.

Không dùng orchestrator để truy cập trực tiếp database của mọi service. Nó gửi command qua contract; mỗi domain vẫn sở hữu transaction và dữ liệu.

## 30. Khi nào không nên dùng EDA?

EDA có thể không phù hợp khi:
- Ứng dụng nhỏ, ít domain và transaction cần đơn giản.
- Người dùng cần kết quả cuối trong một request ngắn.
- Đội không có năng lực vận hành broker/consumer/replay.
- Luồng event không giảm coupling thực sự.
- Consumer luôn gọi ngược producer ngay sau khi nhận event.
- Dữ liệu nhạy cảm khó phân phối qua nhiều bản sao.
- Cần consistency mạnh xuyên nhiều bước và không có workflow/compensation phù hợp.
- Message volume thấp nhưng broker tạo thêm nhiều hạ tầng và công vận hành.

Có thể bắt đầu bằng modular monolith với domain event nội bộ, rồi chuyển một số event thành integration contract khi có nhu cầu. Không cần xây broker trước khi xác định luồng nghiệp vụ và semantics.

## 31. Case study: Checkout event-driven

**Bối cảnh:** Checkout gọi Inventory, Payment và Notification trong một request. Notification chậm khiến người dùng timeout dù order đã tạo.

Thiết kế:
1. Checkout tạo Order PENDING và outbox event trong một transaction.
2. API trả trạng thái cùng order ID.
3. Inventory consumer nhận ReserveInventory.
4. Inventory phát InventoryReserved hoặc InventoryRejected.
5. Saga điều phối Payment authorization.
6. Payment xác nhận thì Order chuyển CONFIRMED.
7. Notification consumer gửi thông báo độc lập.
8. Payment thất bại thì saga release inventory và đánh dấu rejected.
9. Dashboard theo dõi order completion time, queue age, payment uncertainty và DLQ.

Điều kiện thành công:
- Không mất event sau DB commit.
- Duplicate không tạo reservation/payment trùng.
- Order không PENDING vô hạn.
- Provider timeout được reconciliation.
- Người dùng thấy trạng thái chính xác.
- Notification lỗi không làm sai trạng thái đơn.
- Có runbook DLQ/replay/compensation.

EDA tách notification khỏi critical transaction nhưng không loại bỏ trách nhiệm quản lý workflow.

## 32. Case study: Notification consumer

Order Service phát OrderConfirmed. Notification Service nhận event và gửi email/push.

Cần giải quyết:
- Email gửi trùng: idempotency theo event/recipient/template.
- Provider timeout nhưng email đã gửi: reconcile nếu provider có delivery ID.
- Template thay đổi: tách template logic khỏi event contract.
- Consent thay đổi: kiểm tra policy hiện tại theo contract.
- Queue backlog: SLO freshness và alert.
- Replay lịch sử: không gửi lại email ngoài ý muốn.

Notification xử lý async được, nhưng business policy và consent vẫn quyết định có gửi hay không.

## 33. Case study: Analytics consumer và read model

OrderCreated/PaymentCaptured có thể cập nhật dashboard analytics:
- Consumer đọc event độc lập.
- Chuẩn hóa và aggregate.
- Lưu vào warehouse/read model.
- Chấp nhận eventual consistency vài phút nếu báo cáo cho phép.

Nếu Analytics lag, Checkout không nên bị block. Nhưng broker retention phải đủ, pipeline cần checkpoint, replay không nhân đôi doanh thu, late event cập nhật đúng business time và dashboard hiển thị freshness.

Đây là lợi ích fan-out: producer không phải gọi Analytics đồng bộ trong giao dịch.

## 34. Chuyển từ synchronous sang EDA từng bước

Không rewrite mọi luồng một lần:
1. Inventory synchronous calls và critical path.
2. Chọn tác vụ không cần kết quả tức thời.
3. Xác định event fact/command semantics.
4. Tạo contract và owner.
5. Thêm outbox cho producer.
6. Xây một consumer idempotent.
7. Thêm trạng thái workflow và API status.
8. Đo end-to-end latency, lag và business completion.
9. Chạy shadow/compare nếu phù hợp.
10. Bỏ call sync cũ sau khi có bằng chứng.
11. Diễn tập broker outage, duplicate, replay và DLQ.

Bắt đầu với Notification hoặc Analytics thường dễ hơn một bước tài chính khó đảo ngược. Chọn pilot có blast radius kiểm soát được.

## 35. Chi phí và vận hành

EDA thêm broker/managed messaging, network, serialization, schema registry, outbox/inbox, consumer compute, DLQ/replay, telemetry và on-call.

Nó có thể giảm coupling đồng bộ, tải critical path và cho phép consumer scale riêng. Nhưng nếu event volume thấp, consumer ít và mọi luồng cần response ngay, broker có thể là overhead.

Đo:
- Cost per event và per completed workflow.
- Broker storage/retention.
- Consumer idle capacity.
- End-to-end processing latency.
- Backlog age.
- Retry/DLQ rate.
- Operational toil và incident impact.

Không thêm Kafka chỉ vì microservices. Managed queue hoặc outbox + worker có thể đủ cho use case nhỏ.

## 36. Anti-patterns thường gặp

| Anti-pattern | Hậu quả | Cách khắc phục |
|---|---|---|
| Dùng event cho mọi giao tiếp | Khó debug, eventual consistency không cần thiết | Chọn sync/async theo nhu cầu |
| Phát event trước DB commit | Consumer thấy sự kiện không tồn tại | Transactional outbox |
| DB rồi publish trực tiếp không outbox | Có thể mất event khi crash | Outbox hoặc CDC |
| Consumer không idempotent | Duplicate side effect | Inbox/idempotency key |
| Dùng timestamp để bảo đảm thứ tự | Clock skew/event trễ | Aggregate version/sequence |
| Một topic cho mọi domain | Quyền và contract khó quản lý | Topic theo ownership |
| Event mang toàn bộ entity | Lộ dữ liệu/coupling schema | Payload tối thiểu |
| Consumer gọi ngược producer mọi lần | Async biến thành sync dependency | Read model/state transfer |
| Retry vô hạn | Poison message/retry storm | Backoff, max attempts, DLQ |
| Không theo dõi lag | Business workflow bị treo | Freshness/business SLO |
| Gọi event sourcing là EDA | Chọn sai độ phức tạp | Phân biệt nguồn sự thật và transport |
| Saga không có compensation | Workflow mắc kẹt | State machine/recovery |
| Replay có side effect | Email/payment/shipment trùng | Replay-safe consumer |
| Schema registry pass là đủ | Semantic mismatch | Contract tests |
| Choreography quá nhiều bước | Luồng khó hiểu | Orchestrator khi phù hợp |
| Không có owner cho event | Breaking change bất ngờ | Catalog và contract owner |

## 37. Bài tập thực hành

**Bài A — chọn sync hay async:** Checkout gọi Inventory, Payment, Notification và Analytics. Phân loại bước nào cần câu trả lời ngay, bước nào event-driven. Nêu ảnh hưởng UX và SLO.

**Bài B — command/event:** Với ReserveInventory, InventoryReserved, CapturePayment và PaymentCaptured, phân loại command/event và xác định producer/owner.

**Bài C — outbox crash:** DB commit thành công, publisher gửi event rồi crash trước khi đánh dấu published. Mô tả duplicate và cách consumer ngăn side effect trùng.

**Bài D — inbox atomicity:** Consumer insert processed_messages rồi crash trước update Inventory. Đề xuất transaction boundary để không mất xử lý.

**Bài E — ordering:** OrderCreated v1, OrderConfirmed v2, OrderCancelled v3 đến sai thứ tự. Thiết kế partition key, aggregate version và xử lý gap.

**Bài F — saga:** Payment authorize thành công nhưng response timeout; Inventory reservation hết hạn. Xây state machine, reconciliation và compensation tránh capture/refund sai.

**Bài G — schema evolution:** Producer thêm enum PaymentState mới; consumer cũ dùng strict deserializer. Đề xuất contract/versioning và rollout sequence.

**Bài H — event sourcing:** So sánh Orders dùng bảng trạng thái + outbox với event-sourced aggregate. Nêu yêu cầu audit/replay nào khiến event sourcing đáng giá.

**Bài I — consumer lag:** Kafka lag tăng liên tục, broker vẫn healthy. Thiết kế dashboard, alert, backpressure và scale mà không làm DB quá tải.

**Bài J — privacy:** Event chứa email/địa chỉ được phát tới 12 consumer và data lake. Xây data minimization, retention, deletion và audit policy.

**Bài K — replay:** Rebuild Order Read Model từ 30 ngày event. Thiết kế consumer group, checkpoint, rate limit và cách ngăn gửi lại email/payment.

**Bài L — choreography:** Quy trình có 8 event và 5 service. Vẽ dependency graph, chỉ ra điểm khó quan sát và khi nào chuyển sang orchestrator.

**Bài M — migration:** Chuyển Notification từ sync sang async. Viết lộ trình outbox, idempotency, consent, DLQ, SLO freshness và rollback.

**Bài N — failure drill:** Broker ngừng publish 10 phút rồi hoạt động lại. Định nghĩa outbox backlog, recovery capacity, retry và điều kiện hệ thống trở lại bình thường.

## 38. Checklist thiết kế EDA cho microservices

1. Ranh giới service và owner rõ theo bounded context.
2. Phân biệt command, domain event và integration event.
3. Định nghĩa semantics: event phát khi nào và chứng minh điều gì.
4. Chọn queue/pub-sub/log theo delivery và replay requirements.
5. Xác định sync/async dựa vào UX và business deadline.
6. Event envelope có ID, schema version, correlation và causation.
7. Dùng outbox/CDC để tránh mất event giữa DB commit và publish.
8. Consumer idempotent với Inbox hoặc cơ chế tương đương.
9. Xác định ordering theo aggregate/partition key và version.
10. Retry/backoff/DLQ có giới hạn và owner.
11. Saga/workflow có timeout, compensation và reconciliation.
12. Eventual consistency có SLO freshness và trạng thái người dùng.
13. Schema evolution có compatibility tests và deprecation policy.
14. Replay an toàn, không tái thực hiện external side effects.
15. Observability xuyên workflow với trace/correlation và business metrics.
16. Security/privacy: least privilege, data minimization, retention.
17. Capacity/backpressure bảo vệ broker và downstream.
18. Integration tests mô phỏng duplicate, crash, reorder và provider timeout.
19. Runbook cho lag, DLQ, outbox backlog và replay.
20. Đo TCO của broker, storage, telemetry và công vận hành.

## 39. Ghi nhớ

- **Microservices chia hệ thống theo ranh giới sở hữu và triển khai; EDA tổ chức giao tiếp qua sự kiện.** Hai cách tiếp cận bổ trợ nhau nhưng không đồng nghĩa.
- **Không phải mọi lời gọi nên chuyển thành event.** Sync phù hợp khi cần câu trả lời ngay; async phù hợp với công việc nền, fan-out và xử lý độc lập.
- **Command yêu cầu hành động; event thông báo điều đã xảy ra.** Semantics rõ giúp consumer không hiểu sai trạng thái nghiệp vụ.
- **Domain event và integration event khác mục đích.** Không công bố cấu trúc nội bộ hoặc dữ liệu nhạy cảm.
- **Transactional outbox** giảm rủi ro mất event sau DB commit; **Inbox/idempotency** xử lý duplicate delivery.
- **At-least-once phổ biến**, vì vậy consumer phải idempotent. Exactly-once phải giới hạn theo phạm vi thực tế.
- **Ordering chỉ được bảo đảm trong phạm vi broker định nghĩa**, thường theo partition/key; dùng aggregate version để kiểm tra thứ tự nghiệp vụ.
- **Saga** điều phối nhiều transaction local; compensation không phải rollback thời gian.
- **Eventual consistency cần deadline và reconciliation**, không phải trạng thái chờ vô hạn.
- **Event sourcing khác EDA**; không cần event store làm nguồn sự thật chỉ vì dùng broker.
- **Schema evolution và replay** là một phần của contract.
- **Observability phải theo business workflow**, không chỉ trạng thái broker.
- **Security/privacy cần thiết kế trước khi event lan sang nhiều consumer**.
- **EDA có cost floor và công vận hành**; dùng khi nó giải quyết nhu cầu thực.

Kết hợp microservices với kiến trúc hướng sự kiện có giá trị khi **mỗi service sở hữu rõ một capability, công bố những sự kiện có ý nghĩa nghiệp vụ, và consumer xử lý độc lập trong giới hạn nhất quán được công bố**. Thành công không nằm ở số topic hay broker, mà ở việc hệ thống chịu được chậm trễ, duplicate, lỗi và thay đổi phiên bản mà vẫn giữ đúng trạng thái nghiệp vụ và trải nghiệm người dùng.
