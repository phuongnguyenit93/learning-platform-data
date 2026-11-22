# Ranh giới giữa sự kiện thay đổi dữ liệu và sự kiện nghiệp vụ

CDC (Change Data Capture) ghi nhận những thay đổi xảy ra trong database, chẳng hạn một row được insert, update hoặc delete. Business event mô tả một sự thật có ý nghĩa trong miền nghiệp vụ, chẳng hạn đơn hàng đã được thanh toán hoặc yêu cầu giao hàng đã được xác nhận.

Hai loại dữ liệu này có thể cùng được truyền qua Kafka và có thể cùng được thu thập bằng Debezium, nhưng chúng không có cùng ý nghĩa. Một thay đổi row không tự động trở thành một business event. Nếu consumer cần hiểu ý định nghiệp vụ, hợp đồng tích hợp và vòng đời sự kiện, ứng dụng nên tạo domain event một cách tường minh. Transactional outbox giúp lưu domain event cùng transaction với thay đổi dữ liệu rồi dùng CDC để chuyển event đó sang Kafka.

Bài này làm rõ ranh giới giữa CDC change record và business event, cách chọn mô hình phù hợp, vai trò của outbox và các yêu cầu về schema, ordering, duplicate, replay.

## 1. CDC change record và business event khác nhau ở đâu?

CDC trả lời câu hỏi: **database đã thay đổi dữ liệu nào?**

Business event trả lời câu hỏi: **điều gì đã xảy ra trong nghiệp vụ và hệ thống khác cần biết điều gì?**

Ví dụ một đơn hàng được thanh toán. Database có thể thực hiện nhiều thay đổi:

- Cập nhật `orders.status` từ `PENDING` sang `PAID`.
- Ghi một row vào `payments`.
- Cập nhật `accounts.balance`.
- Ghi một row vào bảng audit.
- Cập nhật `updated_at`.

CDC có thể phát ra một hoặc nhiều change record tương ứng với các thay đổi row. Các record mô tả trạng thái dữ liệu và metadata nguồn.

Business event có thể chỉ là một sự kiện có ý nghĩa rõ ràng:

~~~json
{
  "eventId": "evt-901",
  "eventType": "OrderPaid",
  "aggregateId": "order-123",
  "occurredAt": "2026-11-20T10:15:30Z",
  "data": {
    "orderId": "order-123",
    "paymentId": "payment-456",
    "amount": 1250000,
    "currency": "VND"
  }
}
~~~

Event `OrderPaid` cho consumer biết một sự thật nghiệp vụ đã xảy ra. Consumer không cần biết ứng dụng đã cập nhật bao nhiêu bảng để tạo ra sự thật đó.

| Tiêu chí | CDC change record | Business event |
|---|---|---|
| Ý nghĩa | Thay đổi row hoặc dữ liệu nguồn | Sự thật/điều đã xảy ra trong nghiệp vụ |
| Nguồn tạo | Database log hoặc cơ chế CDC | Domain/application logic |
| Nội dung | Before/after, operation, source metadata | Event type, aggregate, business payload |
| Phụ thuộc schema DB | Thường cao | Nên độc lập với schema lưu trữ |
| Mục tiêu | Replication, data integration, cache, analytics | Giao tiếp giữa domain/service |
| Thay đổi cấu trúc | Có thể xuất hiện khi migration bảng | Được quản lý như contract của event |
| Ngữ nghĩa | Không nhất thiết thể hiện ý định nghiệp vụ | Có ý nghĩa nghiệp vụ được định nghĩa rõ |

CDC có thể vận chuyển business event nếu ứng dụng ghi event vào outbox table và Debezium capture table đó. Trong trường hợp này, CDC là cơ chế vận chuyển; bản ghi được phát ra vẫn mang ngữ nghĩa business event do ứng dụng định nghĩa.

## 2. CDC ghi nhận điều gì?

Với log-based CDC, connector đọc transaction log hoặc change log của database để phát hiện thay đổi. Debezium là một nền tảng phổ biến cho cách tiếp cận này.

Một change event thường chứa:

- Operation: create, update, delete hoặc snapshot/read.
- Before: trạng thái row trước thay đổi nếu connector/database cung cấp.
- After: trạng thái row sau thay đổi.
- Source metadata: database, schema, table, log position, transaction hoặc timestamp tùy connector.
- Metadata thời điểm ghi nhận thay đổi.

Ví dụ envelope Debezium dạng rút gọn cho một update:

~~~json
{
  "before": {
    "id": 123,
    "status": "PENDING"
  },
  "after": {
    "id": 123,
    "status": "PAID"
  },
  "source": {
    "db": "commerce",
    "table": "orders",
    "lsn": 987654
  },
  "op": "u",
  "ts_ms": 1795169730000
}
~~~

Tên field và cấu trúc envelope cụ thể phụ thuộc connector, database, phiên bản Debezium và cấu hình converter. Với Debezium, các operation code phổ biến gồm:

| Operation | Ý nghĩa |
|---|---|
| `c` | Row được tạo |
| `u` | Row được cập nhật |
| `d` | Row bị xóa |
| `r` | Row được đọc trong snapshot |

CDC có thể phát record `r` khi snapshot đọc dữ liệu hiện có. Đây không phải bằng chứng rằng nghiệp vụ vừa tạo lại entity tại thời điểm snapshot. Nếu consumer xem mọi record snapshot là `EntityCreated`, nó có thể gửi email hoặc kích hoạt side effect sai.

### 2.1. CDC không đồng nghĩa event sourcing

CDC phản ánh thay đổi của database hiện tại. Nó không tự động là một event store chứa đầy đủ các sự kiện nghiệp vụ bất biến.

Ví dụ bảng `orders` chỉ lưu trạng thái mới nhất. Một update từ `PENDING` sang `PAID` có thể được capture, nhưng database không nhất thiết lưu đầy đủ các quyết định trước đó như:

- Ai đã chấp thuận thanh toán?
- Vì sao đơn hàng chuyển trạng thái?
- Quy tắc nghiệp vụ nào đã được áp dụng?
- Lệnh nghiệp vụ ban đầu là gì?
- Có bước kiểm tra hoặc bù trừ nào đã xảy ra?

Nếu bảng bị ghi đè nhiều lần, CDC log có thể ghi lại các thay đổi trong thời gian log còn được giữ, nhưng retention và snapshot policy không biến nó thành event store nghiệp vụ dài hạn.

Event sourcing là mô hình lưu các event làm nguồn sự thật của trạng thái. CDC có thể được dùng để chuyển event store hoặc database sang hệ thống khác, nhưng hai khái niệm không thay thế nhau.

## 3. Vì sao không nên biến mọi row update thành business event?

Một thay đổi database có thể là chi tiết triển khai nội bộ:

- Cập nhật `updated_at` hoặc `last_seen_at`.
- Tăng bộ đếm retry.
- Cập nhật trạng thái kỹ thuật của một workflow.
- Ghi audit row nội bộ.
- Chuyển dữ liệu giữa hai bảng do refactor.
- Cập nhật cache hoặc cột denormalized.

Nếu phát từng thay đổi đó như event nghiệp vụ, consumer bên ngoài sẽ phụ thuộc vào cấu trúc database và phải hiểu các chi tiết không thuộc contract của họ.

Ví dụ consumer nhận:

~~~json
{
  "table": "orders",
  "op": "u",
  "before": {"status": "PENDING"},
  "after": {"status": "PAID", "updated_at": "2026-11-20T10:15:30Z"}
}
~~~

Consumer phải tự suy luận rằng thay đổi status có nghĩa là `OrderPaid`. Nó còn phải phân biệt update kỹ thuật, correction, snapshot và các thay đổi không liên quan.

Thay vào đó, producer nghiệp vụ phát:

~~~json
{
  "eventId": "evt-901",
  "eventType": "OrderPaid",
  "aggregateId": "order-123",
  "data": {
    "paymentId": "payment-456",
    "amount": 1250000,
    "currency": "VND"
  }
}
~~~

Contract này thể hiện ý nghĩa rõ ràng và không buộc consumer biết bảng nào đã được cập nhật.

## 4. Business event được tạo ở đâu?

Business event nên được tạo tại ranh giới nơi ứng dụng hiểu quyết định nghiệp vụ. Thường đó là domain/application service xử lý command.

Ví dụ command `PayOrder` có thể:

1. Kiểm tra đơn hàng đang ở trạng thái cho phép thanh toán.
2. Xác nhận kết quả payment.
3. Chuyển trạng thái đơn hàng thành PAID.
4. Tạo event `OrderPaid`.
5. Lưu thay đổi và event trong cùng database transaction.

Không nên suy ra `OrderPaid` chỉ từ một row update nếu ứng dụng không thể phân biệt update đó đến từ luồng nghiệp vụ nào.

### 4.1. Domain event và integration event

Hai thuật ngữ này gần nhau nhưng có phạm vi khác nhau:

- **Domain event:** sự kiện nội bộ trong domain, phản ánh điều có ý nghĩa trong mô hình nghiệp vụ.
- **Integration event:** hợp đồng được công bố ra ngoài để service hoặc hệ thống khác tiêu thụ.

Một domain event có thể được chuyển đổi thành integration event. Không nhất thiết mọi domain event nội bộ đều phải phát ra Kafka.

| Domain event | Integration event có thể công bố |
|---|---|
| `PaymentMethodValidated` | Không nhất thiết công bố |
| `OrderPaid` | `OrderPaid` |
| `InventoryReservationAdjusted` | `InventoryReserved` |
| `InternalRiskScoreCalculated` | Có thể chỉ công bố kết quả được phép chia sẻ |

Integration event cần được thiết kế ổn định, có schema/version và chỉ chứa dữ liệu mà consumer được phép nhận.

## 5. Dual-write problem khi cập nhật database và gửi Kafka

Một service thường cần cập nhật database rồi phát business event. Nếu hai thao tác được thực hiện độc lập:

~~~mermaid
flowchart TD
    A["Xử lý command"] --> B["Commit database"]
    B --> C["Publish event Kafka"]
    C --> D{"Publish thành công?"}
    D -->|Có| E["Hoàn tất"]
    D -->|Không| F["Database đã đổi<br/>nhưng event chưa phát"]
~~~

Có hai failure window:

**Database commit trước, Kafka publish thất bại:** dữ liệu nghiệp vụ đã thay đổi nhưng consumer không nhận được event.

**Kafka publish trước, database rollback:** consumer đã nhận event về một thay đổi chưa được commit trong database.

Gọi hai thao tác trong cùng phương thức `@Transactional` của Spring không tự động tạo một transaction nguyên tử giữa database và Kafka, trừ khi dùng một cơ chế phối hợp transaction cụ thể với các giới hạn và thứ tự commit được hiểu rõ. Với nhiều hệ thống, cách đơn giản và bền vững là transactional outbox.

## 6. Transactional outbox tạo ranh giới giữa database và event

Outbox pattern lưu business event vào một bảng riêng trong cùng database transaction với thay đổi nghiệp vụ.

Luồng:

1. Service xử lý command.
2. Cập nhật bảng nghiệp vụ.
3. Insert integration event vào bảng outbox.
4. Commit một database transaction.
5. CDC connector đọc outbox table từ transaction log.
6. Debezium Event Router chuyển row outbox thành Kafka record.
7. Consumer nhận business event.

~~~mermaid
flowchart TD
    A["Command: PayOrder"] --> B["BEGIN DB transaction"]
    B --> C["Update orders"]
    B --> D["Insert OrderPaid into outbox"]
    C --> E["COMMIT DB"]
    D --> E
    E --> F["Database transaction log"]
    F --> G["Debezium CDC"]
    G --> H["Outbox Event Router"]
    H --> I["Kafka topic: order events"]
    I --> J["Downstream consumers"]
~~~

Nếu transaction rollback, cả thay đổi bảng nghiệp vụ và outbox row đều rollback. Nếu transaction commit, cả hai cùng tồn tại để CDC đọc.

Outbox giải quyết dual-write giữa database và Kafka bằng cách đưa việc tạo event vào cùng transaction database. Nó không bảo đảm publish đúng một lần tuyệt đối: connector có thể phát lại record sau restart hoặc khi offset được khôi phục. Consumer vẫn cần idempotency.

## 7. Thiết kế outbox table

Một bảng outbox thường có các trường:

| Trường | Mục đích |
|---|---|
| `id` | Event ID duy nhất, ổn định |
| `aggregatetype` | Loại aggregate, ví dụ Order |
| `aggregateid` | ID aggregate, thường dùng làm Kafka key |
| `type` | Tên integration event, ví dụ OrderPaid |
| `payload` | Nội dung event |
| `timestamp` | Thời điểm tạo event |
| `headers` (tùy chọn) | Metadata bổ sung như correlation ID |

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE outbox_event (
    id            UUID PRIMARY KEY,
    aggregatetype VARCHAR(100) NOT NULL,
    aggregateid   VARCHAR(200) NOT NULL,
    type          VARCHAR(200) NOT NULL,
    payload       JSONB NOT NULL,
    timestamp     TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_outbox_event_timestamp
    ON outbox_event (timestamp);
~~~

`aggregateid` nên giữ ổn định và được dùng làm key nếu cần các event của cùng aggregate đi vào cùng Kafka partition. `id` là event identity, không nên thay đổi khi event được publish lại.

Có thể thêm `headers` hoặc các cột correlation/trace tùy contract và cách cấu hình Event Router. Tránh lưu secret hoặc dữ liệu cá nhân không cần thiết trong outbox vì dữ liệu có thể được giữ trong log và Kafka lâu hơn vòng đời row.

### 7.1. Insert outbox cùng transaction nghiệp vụ

Ví dụ service Java với Spring:

~~~java
@Service
public class OrderApplicationService {

    private final OrderRepository orderRepository;
    private final OutboxRepository outboxRepository;

    public OrderApplicationService(
            OrderRepository orderRepository,
            OutboxRepository outboxRepository) {
        this.orderRepository = orderRepository;
        this.outboxRepository = outboxRepository;
    }

    @Transactional
    public void markOrderPaid(
            UUID orderId,
            UUID paymentId,
            BigDecimal amount) {

        Order order = orderRepository.findById(orderId)
            .orElseThrow();

        order.markPaid(paymentId);
        orderRepository.save(order);

        OrderPaid event = new OrderPaid(
            UUID.randomUUID(),
            order.getId(),
            paymentId,
            amount,
            "VND",
            Instant.now()
        );

        outboxRepository.insert(
            event.eventId(),
            "Order",
            order.getId().toString(),
            "OrderPaid",
            event
        );
    }
}
~~~

Đoạn code minh họa ranh giới transaction. Trong triển khai thực tế, cần bảo đảm event ID được tạo đúng một lần cho command/event và được lưu vào outbox. Nếu command có idempotency key, cần tránh tạo hai event nghiệp vụ cho cùng một command được gửi lại.

Nếu transaction commit thất bại, cả order update và outbox insert phải rollback. Nếu commit thành công rồi process dừng, Debezium vẫn có thể đọc outbox row từ transaction log.

## 8. Debezium và Outbox Event Router

Debezium có thể capture thay đổi của outbox table. Outbox Event Router là Single Message Transform (SMT) giúp biến đổi row outbox thành record Kafka có key, value, topic và headers phù hợp.

Cấu hình khái niệm cho connector:

~~~properties
transforms=outbox
transforms.outbox.type=io.debezium.transforms.outbox.EventRouter

transforms.outbox.table.field.event.id=id
transforms.outbox.table.field.event.key=aggregateid
transforms.outbox.table.field.event.type=type
transforms.outbox.table.field.event.payload=payload
transforms.outbox.table.field.event.timestamp=timestamp
transforms.outbox.route.by.field=aggregatetype
~~~

Các property và class name phải khớp với phiên bản Debezium đang triển khai. Cấu hình connector cũng cần khai báo database connection, publication/slot hoặc cơ chế log tương ứng, table include list, converter và security.

Với cấu hình route theo aggregate type, event của aggregate type `Order` có thể được định tuyến tới topic theo quy tắc của Event Router. Hãy xác minh topic naming và key/value serialization trong môi trường thử nghiệm trước khi triển khai.

### 8.1. Vì sao dùng Event Router thay vì phát raw CDC của outbox?

Nếu không dùng SMT, consumer có thể nhận envelope CDC mô tả insert vào bảng `outbox_event`, gồm `before`, `after`, `source` và operation.

Event Router trích các trường có ý nghĩa:

- Event ID.
- Aggregate ID làm message key.
- Event type.
- Payload.
- Timestamp và headers nếu cấu hình.

Consumer nhận integration event trực tiếp, không phải hiểu cấu trúc row outbox hoặc envelope CDC nội bộ.

### 8.2. Không để consumer phụ thuộc schema outbox

Outbox table là chi tiết triển khai của producer. Consumer nên phụ thuộc contract event được publish, không phụ thuộc:

- Tên bảng outbox.
- Tên cột database.
- Database engine.
- Cấu trúc transaction log.
- Cách Debezium lưu source offset.

Nếu schema outbox thay đổi, producer có thể điều chỉnh mapping mà không bắt mọi consumer đổi theo.

## 9. CDC trực tiếp và outbox: khi nào dùng cách nào?

CDC trực tiếp phù hợp khi mục tiêu là đồng bộ dữ liệu hoặc xây dựng luồng thay đổi cho data platform.

Ví dụ:

- Đồng bộ bảng customer sang search index.
- Đưa thay đổi inventory sang data lake.
- Cập nhật cache hoặc read model theo row change.
- Replicate dữ liệu giữa hai database.
- Phân tích lịch sử thay đổi theo source metadata.

Outbox phù hợp khi cần công bố sự kiện nghiệp vụ cho service khác:

- `OrderPaid`.
- `ShipmentDispatched`.
- `CustomerEmailChanged`.
- `InventoryReserved`.
- `PaymentRefunded`.

| Nhu cầu | CDC trực tiếp | Outbox + CDC |
|---|---|---|
| Đồng bộ row/table | Phù hợp | Không cần thiết nếu chỉ replicate |
| Contract domain ổn định | Phải tự xây lớp chuyển đổi | Phù hợp hơn |
| Hiểu ý định nghiệp vụ | Không tự có | Ứng dụng định nghĩa event |
| Phụ thuộc schema database | Cao hơn | Consumer tách khỏi schema DB |
| Cần event cùng transaction với business update | Không tự đảm bảo semantics domain | Outbox row được ghi cùng DB transaction |
| Data lake/warehouse ingestion | Rất phù hợp | Có thể dùng nếu muốn lưu business event |
| Tích hợp service-to-service | Có thể, nhưng cần mapping | Thường là lựa chọn rõ ràng hơn |

Có thể triển khai cả hai luồng song song: CDC trực tiếp phục vụ analytics/replication, outbox phục vụ integration event. Không nên ép một luồng CDC bảng nghiệp vụ thành contract cho mọi consumer.

## 10. Transaction boundary và thứ tự sự kiện

Outbox row được insert trong cùng database transaction với thay đổi nghiệp vụ. Điều đó bảo đảm hai thay đổi cùng commit hoặc cùng rollback trong database.

Tuy nhiên, không nên suy ra mọi record được phát lên Kafka sẽ tạo thành một transaction Kafka duy nhất hoặc consumer ở mọi topic sẽ nhìn thấy chúng đồng thời. Connector, topic routing, partitioning và consumer isolation ảnh hưởng cách record được quan sát.

Để giữ thứ tự theo aggregate:

- Dùng `aggregateid` làm Kafka key.
- Đảm bảo event cùng aggregate đi vào cùng partition.
- Gắn aggregate version hoặc sequence tăng dần.
- Consumer kiểm tra version khi cập nhật read model.
- Tránh tăng partition tùy tiện nếu cần duy trì key-to-partition mapping ổn định.

Ví dụ:

~~~json
{
  "eventId": "evt-902",
  "eventType": "OrderShipped",
  "aggregateId": "order-123",
  "aggregateVersion": 9,
  "occurredAt": "2026-11-20T11:00:00Z",
  "data": {
    "shipmentId": "shipment-789"
  }
}
~~~

Nếu consumer nhận version 9 khi đang giữ version 7, có thể event version 8 đang đến chậm hoặc bị lỗi. Consumer cần retry, giữ event chờ hoặc reconcile từ nguồn dữ liệu tùy yêu cầu nghiệp vụ. Không chỉ dựa vào timestamp để suy ra thứ tự tuyệt đối.

## 11. Delivery semantics, duplicate và idempotency

Outbox tránh mất event do dual-write, nhưng CDC delivery thường cần được thiết kế theo hướng at-least-once. Connector restart, offset recovery hoặc việc xử lý lại log có thể khiến một event được publish lại.

Do đó:

- Giữ `id` ổn định cho cùng một outbox event.
- Consumer lưu event ID đã xử lý nếu có side effect.
- Ghi inbox/dedup key cùng database transaction với side effect.
- Dùng upsert hoặc unique constraint phù hợp.
- Không tạo event ID mới khi re-drive cùng event.
- Giữ key, aggregate ID và version qua retry/DLT.

Một inbox table đơn giản:

~~~sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(120) NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Consumer bắt đầu transaction, insert event ID, chỉ thực hiện side effect khi insert thành công, rồi commit database transaction. Sau đó mới commit Kafka offset. Nếu process crash sau DB commit trước offset commit, event có thể được giao lại nhưng inbox ngăn side effect lặp.

Không gọi đây là exactly-once xuyên suốt database và Kafka. Inbox tạo hiệu ứng lũy đẳng ở ranh giới database; Kafka offset và database transaction vẫn là hai hệ thống riêng.

## 12. Snapshot, delete và cleanup của outbox

CDC connector có thể thực hiện snapshot khi khởi tạo hoặc khi cần khôi phục. Với outbox, cần tránh để snapshot của các row cũ bị hiểu thành event mới và kích hoạt lại side effect.

Các quyết định cần làm rõ:

- Outbox table có được snapshot hay chỉ capture insert mới?
- Khi connector khởi động lần đầu, các row lịch sử được xử lý thế nào?
- Có đánh dấu snapshot record hoặc lọc các row đã publish không?
- Row outbox được giữ bao lâu?
- Khi xóa row outbox, delete/tombstone được xử lý thế nào?
- Có cần archive để audit hoặc replay không?

Một số hệ thống giữ outbox rows một khoảng thời gian rồi cleanup. Cleanup cần phối hợp với CDC progress và chính sách retention. Xóa row quá sớm có thể làm mất khả năng replay nếu connector chưa capture; giữ quá lâu có thể làm bảng và snapshot lớn.

Không tự xóa hoặc truncate outbox table khi chưa hiểu connector offset, snapshot mode và log retention. Hãy thiết kế job cleanup có watermark/checkpoint và kiểm thử phục hồi.

## 13. Schema và version của business event

Business event là contract công khai giữa producer và consumer. Không nên để schema event thay đổi tùy tiện theo schema bảng database.

Một envelope thường có:

| Field | Mục đích |
|---|---|
| `eventId` | ID duy nhất và ổn định |
| `eventType` | Tên sự kiện nghiệp vụ |
| `aggregateType` | Loại aggregate |
| `aggregateId` | Định danh aggregate và Kafka key |
| `aggregateVersion` | Thứ tự/version nghiệp vụ |
| `occurredAt` | Thời điểm nghiệp vụ xảy ra |
| `schemaVersion` | Phiên bản payload contract |
| `correlationId` | Liên kết request/flow |
| `causationId` | Event/command gây ra event hiện tại |
| `data` | Payload nghiệp vụ |

Khi thay đổi contract:

- Thêm field optional/default nếu phù hợp.
- Giữ ý nghĩa field ổn định.
- Không đổi đơn vị đo mà không version hóa rõ ràng.
- Dùng Schema Registry compatibility policy nếu hệ thống quản lý schema.
- Phát event correction/compensation thay vì sửa lịch sử đã công bố.
- Không đưa cột kỹ thuật nội bộ vào payload nếu consumer không cần.

CDC schema của database và event schema có vòng đời khác nhau. Migration thêm cột không nhất thiết phải tạo một business event mới; ngược lại, một business event có thể tổng hợp dữ liệu từ nhiều bảng.

## 14. Bảo mật và dữ liệu nhạy cảm

CDC có thể capture toàn bộ cột trong row, bao gồm thông tin mà consumer downstream không cần. Outbox cho phép chọn payload tường minh, nhưng payload vẫn có thể chứa dữ liệu cá nhân hoặc bí mật.

Các nguyên tắc:

- Chỉ phát các trường consumer cần.
- Không đưa password, token, secret hoặc thông tin xác thực vào event.
- Phân loại PII và áp dụng masking/tokenization khi phù hợp.
- Kiểm soát ACL theo topic và consumer group.
- Bảo vệ database replication credentials và Kafka credentials.
- Đặt retention và quyền truy cập phù hợp với chính sách dữ liệu.
- Cẩn thận với stack trace, source metadata hoặc payload trong log.

Event đã phát vào Kafka có thể tồn tại qua nhiều replica, backup, consumer và data lake. Không xem xóa row database là xóa được mọi bản sao event đã phát.

## 15. Khi nào chọn CDC trực tiếp, khi nào chọn outbox?

Có thể dùng các câu hỏi sau:

**Consumer cần biết thay đổi row hay sự thật nghiệp vụ?**

- Nếu cần đồng bộ row, CDC trực tiếp thường đơn giản và phù hợp.
- Nếu cần biết `OrderPaid` hoặc `ShipmentDispatched`, tạo business event rõ ràng.

**Schema database có được xem là contract tích hợp không?**

- Nếu không, tránh để consumer phụ thuộc trực tiếp schema bảng.
- Dùng outbox để tách contract event khỏi cấu trúc lưu trữ.

**Một transaction nghiệp vụ cập nhật nhiều bảng?**

- Nếu consumer cần một sự kiện đại diện cho toàn bộ quyết định nghiệp vụ, phát một domain/integration event trong outbox.
- Nếu data platform cần quan sát từng row mutation, CDC trực tiếp có thể phù hợp.

**Cần replay dữ liệu lịch sử như thế nào?**

- CDC replay phụ thuộc log retention, snapshot và source offset.
- Business event replay phụ thuộc retention của topic, schema evolution và chính sách lưu outbox/archive.

**Có cần cả hai?**

Nhiều kiến trúc dùng CDC trực tiếp cho data integration và outbox cho service integration. Hai luồng có mục tiêu khác nhau và có thể cùng tồn tại.

## 16. Quy trình triển khai outbox với Debezium

Một quy trình triển khai có kiểm soát:

1. Xác định business event nào cần công bố và consumer nào sẽ dùng.
2. Thiết kế event contract độc lập với schema database.
3. Tạo outbox table có event ID, aggregate type/ID, event type và payload.
4. Ghi business update và outbox row trong cùng database transaction.
5. Cấu hình database log/CDC connector với quyền và retention phù hợp.
6. Chỉ capture outbox table hoặc áp dụng filter rõ ràng.
7. Cấu hình Outbox Event Router để map key, topic, type, payload và headers.
8. Xác minh topic routing, serializer, key và schema.
9. Kiểm thử connector restart, snapshot, duplicate và cleanup.
10. Xây consumer idempotent bằng inbox/dedup.
11. Theo dõi source lag, outbox backlog, connector task status và consumer lag.
12. Chỉ cleanup outbox rows khi CDC đã capture qua watermark an toàn.

Không copy cấu hình Debezium từ connector/database khác mà không kiểm tra plugin, phiên bản, database privilege, log position và SMT property. Tên database setting và snapshot behavior phụ thuộc connector cụ thể.

## 17. Quan sát và xử lý sự cố

Các metric và trạng thái nên theo dõi:

- CDC source lag và vị trí log đã đọc.
- Connector/task state.
- Số outbox row chờ capture.
- Tuổi của outbox row cũ nhất chưa được capture.
- Kafka produce error và retry.
- Record rate theo topic.
- Consumer lag.
- Duplicate event count ở consumer.
- DLT/retry rate.
- Database transaction latency và outbox insert failure.

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Business update thành công nhưng không có event | Outbox insert không nằm cùng transaction hoặc connector không capture bảng | Kiểm tra transaction và table include list |
| Có raw CDC nhưng không có event đã route | SMT không áp dụng hoặc mapping sai | Kiểm tra Event Router config và connector logs |
| Event duplicate | Connector restart/replay hoặc offset được xử lý lại | Dùng event ID và inbox |
| Event đi sai topic | Route field hoặc aggregate type không đúng | Kiểm tra outbox row và route config |
| Consumer nhận payload dạng envelope CDC | Chưa dùng Event Router hoặc SMT không match table | Kiểm tra transforms và table routing |
| Snapshot tạo side effect lặp | Consumer hiểu snapshot row là event mới | Phân biệt snapshot và live change; kiểm soát snapshot policy |
| Outbox table tăng liên tục | Cleanup không chạy hoặc CDC không tiến | Kiểm tra watermark, connector lag và cleanup job |
| Thứ tự theo aggregate bị sai | Key không ổn định, nhiều partition hoặc version gap | Kiểm tra Kafka key và aggregateVersion |
| Mất event khi cleanup | Xóa row trước khi connector capture | Phối hợp cleanup với CDC checkpoint |
| Consumer phụ thuộc schema DB | Phát raw table change như integration contract | Chuyển sang event contract/outbox hoặc lớp mapping |

## 18. Checklist thiết kế ranh giới CDC và business event

- [ ] Đã xác định consumer cần row-level change hay business fact.
- [ ] Không coi mọi insert/update/delete là business event.
- [ ] Snapshot record không bị hiểu nhầm là nghiệp vụ vừa xảy ra.
- [ ] Business event được tạo tại nơi hiểu quyết định nghiệp vụ.
- [ ] Integration event có event ID ổn định, event type và aggregate ID.
- [ ] Event contract độc lập với schema lưu trữ nội bộ.
- [ ] Business update và outbox insert nằm trong cùng DB transaction.
- [ ] Debezium capture đúng outbox table.
- [ ] Event Router map key, type, payload và topic đúng.
- [ ] Consumer idempotent và chịu được event duplicate.
- [ ] Ordering theo aggregate được hỗ trợ bằng key/version.
- [ ] Snapshot, delete, tombstone và cleanup có chính sách rõ ràng.
- [ ] Outbox cleanup không chạy trước CDC checkpoint an toàn.
- [ ] Schema evolution và replay được kiểm thử.
- [ ] PII, secret, ACL và retention được kiểm soát.
- [ ] Có metric cho CDC lag, outbox backlog, task failure và consumer lag.

CDC và business event phục vụ hai mục tiêu khác nhau. CDC cho biết database đã thay đổi row nào; business event cho biết sự thật nghiệp vụ nào đã xảy ra và hệ thống khác cần biết điều gì. Khi cần tích hợp theo ngữ nghĩa domain, transactional outbox cho phép ứng dụng tạo event tường minh cùng transaction với dữ liệu nghiệp vụ, còn Debezium đảm nhận việc vận chuyển qua Kafka. Cách tách này giữ consumer độc lập với schema database, đồng thời vẫn cần event ID, idempotency, ordering và chính sách replay để xử lý duplicate và phục hồi an toàn.
