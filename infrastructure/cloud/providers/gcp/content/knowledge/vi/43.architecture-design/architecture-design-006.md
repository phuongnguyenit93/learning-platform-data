# CQRS và event sourcing với các dịch vụ dữ liệu GCP

Một hệ thống xử lý đơn hàng có thể cần ghi đơn chính xác, cập nhật tồn kho, hiển thị trạng thái mới nhất cho khách hàng và tạo báo cáo doanh thu. Nếu tất cả thao tác đọc/ghi đều tập trung vào một mô hình dữ liệu và một transaction, ứng dụng dễ gặp khó khăn khi số lượng truy vấn, workflow bất đồng bộ và yêu cầu mở rộng tăng lên. **CQRS (Command Query Responsibility Segregation)** tách cách xử lý thao tác thay đổi trạng thái khỏi cách phục vụ truy vấn. **Event sourcing** là lựa chọn lưu trữ trạng thái bằng chuỗi các sự kiện nghiệp vụ bất biến thay vì chỉ giữ trạng thái mới nhất.

Trong chương **Thiết kế kiến trúc GCP** của module **CLOUD_PROVIDERS_GCP**, bài học kết hợp lựa chọn dịch vụ dữ liệu như Cloud SQL, Spanner, Firestore, BigQuery và Cloud Storage với Pub/Sub, Dataflow, Cloud Run hoặc GKE để xây dựng luồng ghi, phát sự kiện và cập nhật các mô hình đọc. Mục tiêu là thiết kế kiến trúc có thể truy vết lịch sử và mở rộng khả năng đọc mà không đánh đồng message broker với kho sự kiện bền vững, cũng không bỏ qua consistency, giao hàng trùng hoặc yêu cầu bảo mật.

Sau bài học, người học có thể:

- Phân biệt command, query, domain event, integration event, event store và projection.
- Giải thích CQRS và event sourcing là hai lựa chọn độc lập, không buộc phải áp dụng cùng nhau.
- Chọn dịch vụ GCP cho write model, event store, event bus và read model dựa trên yêu cầu tải, consistency và chi phí.
- Thiết kế transactional outbox để tránh lỗi dual write khi vừa ghi database vừa phát Pub/Sub.
- Thiết kế event schema, aggregate version, optimistic concurrency và idempotent projector.
- Xử lý ordering, at-least-once delivery, replay, rebuild và projection lag.
- Áp dụng CQRS bằng Java/Spring với Cloud SQL hoặc Spanner, Pub/Sub và Firestore/BigQuery.
- Nhận diện các tình huống không nên dùng event sourcing và cách triển khai tăng dần từ monolith.
- Bảo vệ thông tin nhạy cảm, theo dõi SLO và lập kế hoạch vận hành, khôi phục sự cố.

## 1. Phân biệt CQRS và event sourcing

### 1.1. CQRS là gì?

Trong ứng dụng CRUD truyền thống, cùng một entity/model được dùng để cập nhật dữ liệu và phục vụ nhiều kiểu truy vấn. CQRS phân tách trách nhiệm:

- **Command side (write side):** nhận ý định thay đổi trạng thái như `PlaceOrder`, `CancelOrder` hoặc `ReserveInventory`; kiểm tra quy tắc nghiệp vụ và ghi kết quả vào nguồn dữ liệu có thẩm quyền.
- **Query side (read side):** trả lời câu hỏi như “đơn hàng đang ở trạng thái nào?” hoặc “10 sản phẩm bán chạy nhất?” bằng mô hình đọc được tối ưu cho truy vấn.

CQRS không nhất thiết yêu cầu hai database, hai microservice hoặc xử lý bất đồng bộ. Một monolith có thể tách command handler và query handler nhưng vẫn dùng cùng database. Khi các nhu cầu đọc/ghi khác nhau đáng kể, có thể mở rộng thành các storage model và service riêng.

Ví dụ:

| Hoạt động | Trách nhiệm | Model phù hợp |
|---|---|---|
| Tạo đơn hàng | Command | Aggregate đơn hàng, kiểm tra giá và tồn kho |
| Hủy đơn hàng | Command | Kiểm tra trạng thái và quyền hủy |
| Xem chi tiết đơn | Query | Document/row tối ưu theo orderId |
| Liệt kê đơn của khách | Query | Index theo customerId và thời gian |
| Báo cáo doanh thu theo tháng | Query | Bảng phân tích/aggregate tại BigQuery |

Mục tiêu CQRS là chọn đúng cách lưu và truy vấn, không phải phân tách mọi thao tác theo khuôn mẫu dù ứng dụng nhỏ.

### 1.2. Event sourcing là gì?

Trong mô hình cập nhật trạng thái thông thường, bảng `orders` lưu trạng thái hiện tại, ví dụ `status=PAID`. Event sourcing lưu chuỗi sự kiện nghiệp vụ đã xảy ra:

1. `OrderPlaced`
2. `PaymentAuthorized`
3. `OrderPaid`
4. `OrderShipped`

Trạng thái hiện tại được khôi phục bằng cách áp dụng các sự kiện theo đúng thứ tự của aggregate. Sự kiện phải mô tả **điều đã xảy ra**, không phải một mệnh lệnh tương lai.

Ví dụ:

| Command | Event thành công | Trạng thái sau khi apply |
|---|---|---|
| PlaceOrder | OrderPlaced | CREATED |
| AuthorizePayment | PaymentAuthorized | PAYMENT_AUTHORIZED |
| CapturePayment | OrderPaid | PAID |
| ShipOrder | OrderShipped | SHIPPED |

Event store là **nguồn sự thật** của trạng thái trong thiết kế event-sourced. Bảng trạng thái hiện tại, cache hoặc document dùng để đọc có thể được tạo lại từ chuỗi event nếu event store đầy đủ và quy tắc projection tương thích.

### 1.3. Hai pattern độc lập

| Mô hình | CQRS | Event sourcing | Khi nào dùng |
|---|---|---|---|
| CRUD đơn giản | Không | Không | Ứng dụng nhỏ, ít truy vấn hoặc ít biến đổi |
| CQRS với state-based writes | Có | Không | Cần nhiều read model nhưng không cần lưu mọi domain event |
| Event-sourced aggregate | Có thể có | Có | Cần audit/replay nghiệp vụ, nhiều consumer, lịch sử thay đổi |
| CQRS + event sourcing | Có | Có | Write model từ event; nhiều projection phục vụ đọc |

**Không có quy tắc bắt buộc “dùng CQRS thì phải dùng event sourcing”.** Một transactional outbox từ bảng CRUD có thể phát integration events để xây dựng read model mà không chuyển write model thành event sourcing.

## 2. Các khái niệm nền tảng

| Khái niệm | Ý nghĩa | Trách nhiệm |
|---|---|---|
| Command | Yêu cầu thay đổi, có thể bị từ chối | Validate, authorize, enforce invariants |
| Aggregate | Ranh giới giữ nhất quán của một nhóm dữ liệu nghiệp vụ | Quyết định event hợp lệ dựa trên trạng thái |
| Domain event | Sự kiện nghiệp vụ đã xảy ra | Ghi nhận fact bất biến, ví dụ OrderPaid |
| Event store | Nguồn lưu event bền vững theo aggregate và version | Atomic append, concurrency, replay |
| Integration event | Hợp đồng công khai giữa các service/bounded context | Tương thích schema và phân phối |
| Event bus | Kênh vận chuyển thông điệp | Fan-out, retry, subscription, delivery |
| Projection | Hàm chuyển event thành dữ liệu phục vụ đọc | Idempotency, version, rebuild |
| Read model | Bảng/document/index phục vụ query | Tối ưu latency, shape và search |
| Snapshot | Trạng thái tổng hợp tại một version | Giảm thời gian khôi phục aggregate |
| Checkpoint | Mốc tiến độ consumer/projection | Khởi động lại và xử lý tiếp |

Một domain event nội bộ không nhất thiết đồng nghĩa một integration event được phát ra bên ngoài. Có thể cần chuyển đổi, loại bỏ thông tin nhạy cảm hoặc gộp event để ổn định hợp đồng tích hợp.

### 2.1. Aggregate và invariant

Aggregate không nên trùng một cách máy móc với mọi bảng dữ liệu. Nó là ranh giới của quy tắc cần nhất quán tức thì. Ví dụ, một đơn hàng không được chuyển từ `CANCELLED` sang `SHIPPED`; handler phải kiểm tra chuỗi event của order trước khi append `OrderShipped`.

Một giao dịch cần kiểm tra tồn kho của nhiều kho hàng có thể vượt ranh giới một aggregate. Không giả định event sourcing tạo ra distributed transaction giữa mọi service. Hãy dùng workflow/Saga, reservation, compensation hoặc thay đổi ranh giới aggregate nếu nghiệp vụ yêu cầu.

### 2.2. Metadata của một event

Một event nên có ít nhất:

~~~json
{
  "eventId": "evt-2d7a...",
  "eventType": "OrderPaid",
  "schemaVersion": 2,
  "aggregateType": "Order",
  "aggregateId": "ord-1042",
  "aggregateVersion": 3,
  "occurredAt": "2026-11-19T08:15:00Z",
  "commandId": "cmd-8ab1...",
  "correlationId": "req-719...",
  "causationId": "evt-bb33...",
  "payload": {
    "paymentReference": "pay-ref-123",
    "currency": "VND",
    "amountMinor": 259000
  }
}
~~~

Các ID chỉ mang tính minh họa. Không dùng thời gian xảy ra event làm tiêu chí duy nhất xác định thứ tự, vì clock của các producer có thể lệch. `aggregateVersion` do event store kiểm soát giúp phát hiện xung đột và giữ thứ tự trong một aggregate.

## 3. Kiến trúc CQRS + event sourcing tổng quát trên GCP

~~~mermaid
flowchart LR
    Client[Client / API caller] --> Command[Command API - Cloud Run]
    Command --> Store[(Event store - Cloud SQL / Spanner)]
    Store --> Relay[Outbox relay / CDC]
    Relay --> Bus[Pub/Sub topic]
    Bus --> P1[Projection worker]
    Bus --> P2[Analytics stream]
    P1 --> Read[(Firestore / Cloud SQL read model)]
    P2 --> Flow[Dataflow]
    Flow --> BQ[(BigQuery)]
    Read --> Query[Query API - Cloud Run]
    Query --> Client
    Store --> Archive[(Cloud Storage backup / archive)]
~~~

Các tầng có ranh giới trách nhiệm:

1. **Command API:** xác thực, kiểm tra input, policy và logic aggregate.
2. **Event store:** append event bằng transaction có kiểm soát version; lưu lịch sử có thẩm quyền.
3. **Outbox/relay:** chuyển event ra khỏi database sau commit mà không làm mất fact.
4. **Pub/Sub:** phân phối integration events cho nhiều consumer độc lập.
5. **Projection:** cập nhật read model, có thể xử lý lại và chống duplicate.
6. **Query API:** trả dữ liệu từ projection; không tự xem projection là nguồn sự thật cho command.
7. **Analytics:** dùng Dataflow/BigQuery để tổng hợp; không đặt BigQuery trên đường kiểm tra invariant cần phản hồi cực nhanh.

Event store không nên chỉ là một Pub/Sub topic. Pub/Sub là dịch vụ vận chuyển và giữ message theo retention/seek policy; nó không mặc nhiên cung cấp kho lịch sử nghiệp vụ không mất dữ liệu cho toàn bộ tuổi đời domain, optimistic concurrency theo aggregate hoặc khả năng replay mọi phiên bản từ khởi đầu. Event store phải được thiết kế riêng.

## 4. Ánh xạ từng thành phần sang các dịch vụ GCP

| Vai trò | Dịch vụ thường cân nhắc | Điểm cần đánh giá |
|---|---|---|
| Command API | Cloud Run service, GKE | Auth, timeout, concurrency, transaction, SLA |
| Transactional write/event store | Cloud SQL PostgreSQL/MySQL, Spanner | ACID, optimistic concurrency, throughput, vùng và cost |
| Event data dạng document | Firestore | Document transaction, hot document, query pattern |
| Outbox relay | Cloud Run Jobs/service, GKE worker, CDC/Datastream phù hợp | Polling, claim, checkpoint, retry |
| CDC | Spanner change streams, Datastream cho source được hỗ trợ | Row changes, latency, retention, schema mapping |
| Event distribution | Pub/Sub | At-least-once, ordering key, retries, DLQ |
| Projection worker | Cloud Run, Cloud Run functions, GKE, Dataflow | Idempotency, checkpoint, throughput |
| Read model nghiệp vụ | Firestore, Cloud SQL, Spanner | Query patterns, index, latency, consistency |
| Analytics/read model | BigQuery | Scan cost, ingest latency, BI/aggregate |
| Archive / snapshot export | Cloud Storage | Durability, lifecycle, access control, backup |
| Observability | Cloud Logging, Monitoring, Trace | Lag, errors, correlation, SLO |

### 4.1. Cloud SQL cho write model và event store

Cloud SQL phù hợp với hệ thống Java/Spring có domain model quan hệ, cần transaction rõ ràng và quy mô write chưa đòi hỏi kiến trúc Spanner. Một event store tối thiểu có bảng events với unique key (`aggregate_id`, `version`) và transaction append.

Ưu điểm là SQL, JDBC/Spring Transaction, migration tool và kỹ năng vận hành phổ biến. Cần lưu ý connection pooling, instance HA/backup, throughput của một instance, storage, read replicas và chiến lược partition/archive khi event tăng.

### 4.2. Spanner cho giao dịch lớn và phân phối nhiều vùng

Spanner cung cấp transactional database phân tán với strong consistency và scale theo cấu hình. Phù hợp khi khối lượng dữ liệu, throughput hoặc yêu cầu tính sẵn sàng nhiều vùng khiến Cloud SQL trở thành hạn chế quan trọng.

Có thể lưu event theo aggregate và sequence trong Spanner, thiết kế primary key tránh hotspot, rồi dùng outbox hoặc change streams để đưa thay đổi ra hệ thống khác. **Spanner change streams là CDC ghi nhận thay đổi hàng/cột**, không tự quyết định sự kiện nào là fact nghiệp vụ, cũng không thay thế lưu event dài hạn. Change stream có retention hữu hạn; không dùng nó làm toàn bộ lịch sử event sourcing.

### 4.3. Firestore cho read model dạng document

Firestore phù hợp các projection được truy vấn theo document key, collection hoặc index, chẳng hạn `order-summary/{orderId}`, `customer-orders/{customerId}/...`. Có thể phục vụ client/mobile và các API cần lấy tài liệu được denormalize.

Cần quản lý chi phí read/write/index, quy tắc bảo mật, transaction limits, document size, hot document và schema/version khi projection thay đổi. Listener realtime của Firestore phục vụ cập nhật giao diện, **không phải event store**. Trigger từ Firestore document changes có thể đến lặp và không bảo đảm thứ tự; handler phải idempotent nếu được dùng để cập nhật projection.

### 4.4. BigQuery cho read model phân tích

BigQuery phù hợp báo cáo doanh thu, phân tích funnel, cohort hoặc dữ liệu lớn theo thời gian. Dùng Pub/Sub/Dataflow, Datastream hoặc pipeline batch để đưa event/read model vào BigQuery.

BigQuery không mặc nhiên phù hợp endpoint cần đọc/ghi trạng thái một đơn hàng với latency cực thấp, kiểm tra invariant tức thì hoặc transactional updates như OLTP. Tách query API giao dịch khỏi analytics query để không đưa độ trễ và chi phí scan vào đường request chính.

### 4.5. Cloud Storage cho archive và backup

Có thể lưu export event, snapshots, manifest, schema và backup ra Cloud Storage theo policy. GCS là nơi lưu trữ bền vững, không tự đảm bảo atomic append có version trên aggregate. Nếu dùng GCS như archive, cần định dạng file bất biến, checksum, partition, catalog và quy trình khôi phục từ file vào event store/read models.

## 5. Thiết kế event store

Một event store tối thiểu cần giải quyết bốn vấn đề: append nguyên tử, thứ tự trong aggregate, chống concurrent writes không hợp lệ và replay có thể kiểm tra được.

### 5.1. Ví dụ schema PostgreSQL

~~~sql
CREATE TABLE domain_events (
    event_id         UUID PRIMARY KEY,
    aggregate_type   VARCHAR(100) NOT NULL,
    aggregate_id     VARCHAR(128) NOT NULL,
    aggregate_version BIGINT NOT NULL CHECK (aggregate_version > 0),
    event_type       VARCHAR(120) NOT NULL,
    schema_version   INTEGER NOT NULL CHECK (schema_version > 0),
    occurred_at      TIMESTAMPTZ NOT NULL,
    command_id       VARCHAR(128) NOT NULL,
    correlation_id   VARCHAR(128),
    payload          JSONB NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_aggregate_version
        UNIQUE (aggregate_type, aggregate_id, aggregate_version),
    CONSTRAINT uq_aggregate_command
        UNIQUE (aggregate_type, aggregate_id, command_id)
);

CREATE INDEX idx_events_replay
    ON domain_events (aggregate_type, aggregate_id, aggregate_version);
~~~

Unique constraint theo command chỉ phù hợp nếu mỗi command tạo tối đa một event. Nếu một command sinh nhiều event thì cần thiết kế idempotency table riêng hoặc dùng `command_id + event_index`. Không áp ràng buộc ví dụ trên một cách máy móc khi domain có multi-event commands.

Điểm then chốt là `UNIQUE (aggregate_type, aggregate_id, aggregate_version)`: hai handler cùng đọc version 5 và cùng muốn append version 6 không thể đều commit thành công. Handler thất bại cần reload aggregate và trả lỗi conflict hoặc retry command theo policy, không tùy tiện ghi đè.

### 5.2. Append và optimistic concurrency

Một trình tự xử lý command:

1. Nhận command có `commandId` để chống retry tạo tác động lặp.
2. Load event/snapshot của aggregate.
3. Apply event để dựng trạng thái và lấy version hiện tại.
4. Validate authorization, transition và invariant.
5. Tạo một hoặc nhiều event mới với version kế tiếp.
6. Trong một database transaction, append event và lưu outbox rows tương ứng.
7. Commit; sau đó relay sẽ phát integration event.
8. Trả `aggregateId`, `newVersion` hoặc token đọc dự kiến.

Nếu cần chống duplicate command, lưu commandId trong durable idempotency store có unique constraint cùng transaction với event append. Chỉ kiểm tra “đã thấy command chưa?” ở cache không đủ vì hai request đồng thời có thể cùng vượt kiểm tra.

### 5.3. Source of truth và trạng thái hiện tại

Trong event sourcing thuần, event store là nguồn sự thật. Một bảng `aggregate_current_state` có thể là projection/materialized state để tăng tốc load, nhưng không được bất ngờ thay đổi nó thành nguồn sự thật khác mà không có quy tắc đồng bộ.

Nếu chọn CRUD + CQRS, write table mới là nguồn sự thật, còn outbox phát integration event. Cần ghi rõ lựa chọn nào đang được triển khai; không gọi mọi bảng audit hoặc CDC là event sourcing.

## 6. Tránh dual write bằng transactional outbox

Đây là sai lầm thiết kế thường gặp:

~~~text
1. UPDATE orders SET status = 'PAID' ...; COMMIT;
2. Publish OrderPaid to Pub/Sub;
~~~

Nếu process chết sau commit và trước publish, database nói đơn đã thanh toán nhưng read model/consumer không bao giờ nhận sự kiện. Nếu đảo thứ tự publish trước commit, subscriber có thể xử lý event cho một transaction sau đó rollback.

### 6.1. Outbox lưu cùng transaction

Thay vì publish trực tiếp, command handler ghi trạng thái/event và một outbox record trong **cùng database transaction**:

~~~sql
CREATE TABLE outbox_events (
    event_id        UUID PRIMARY KEY,
    aggregate_id    VARCHAR(128) NOT NULL,
    aggregate_version BIGINT NOT NULL,
    event_type      VARCHAR(120) NOT NULL,
    payload         JSONB NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at    TIMESTAMPTZ,
    attempts        INTEGER NOT NULL DEFAULT 0
);
~~~

~~~mermaid
sequenceDiagram
    participant C as Client
    participant H as Command handler
    participant DB as Cloud SQL / Spanner
    participant R as Outbox relay
    participant P as Pub/Sub
    participant W as Projection
    C->>H: PayOrder(commandId)
    H->>DB: BEGIN; event/state + outbox; COMMIT
    DB-->>H: Commit OK
    H-->>C: Accepted + aggregateVersion
    R->>DB: Read unprocessed outbox
    R->>P: Publish OrderPaid
    P-->>R: Publish acknowledged
    R->>DB: Mark published/checkpoint
    P-->>W: Deliver event (may repeat)
    W->>W: Deduplicate + apply
~~~

Quy tắc:

- Outbox record phải có ID bền vững, eventType, aggregateId, version và schemaVersion.
- Chỉ trả kết quả command thành công sau khi transaction event + outbox commit.
- Relay retry khi publish lỗi; có backoff, metrics, alert và giới hạn retry.
- Dữ liệu outbox được xóa/archive theo retention sau khi xác định checkpoint an toàn.
- Publish có thể thành công nhưng relay chết trước khi đánh dấu `published_at`: lần sau có thể publish lại. Consumer **phải idempotent**.

Transactional outbox tránh mất event giữa database commit và message publication nhưng **không cung cấp end-to-end exactly-once business processing**.

### 6.2. Relay polling hoặc CDC

| Cơ chế | Cách hoạt động | Ưu/nhược |
|---|---|---|
| Polling relay | Worker truy vấn outbox chưa publish, claim batch và publish | Dễ hiểu; cần locking, batch size, lag monitoring |
| Database CDC | Đọc thay đổi row/table từ log hoặc change stream | Giảm polling; thêm connector, schema mapping, vận hành |
| Spanner change streams | Dòng thay đổi được ghi cùng database transaction | Tích hợp tốt với Spanner; retention/connector cần thiết kế |
| Datastream | CDC/replication từ database được hỗ trợ tới destination như BigQuery/GCS | Mạnh về replication; muốn publish domain events cần pipeline chuyển đổi rõ ràng |

Không kết luận mọi thay đổi trong bảng orders là event nghiệp vụ. Một UPDATE có thể do migration, sửa kỹ thuật hoặc batch job. Nếu muốn hợp đồng ổn định giữa service, hãy tạo **outbox domain integration events** một cách tường minh thay vì expose raw row-level CDC cho consumer.

### 6.3. Claim outbox an toàn khi có nhiều relay

Với Cloud SQL PostgreSQL có thể dùng `SELECT ... FOR UPDATE SKIP LOCKED` trong transaction ngắn để claim batch, tránh hai worker claim cùng row. Không nên giữ database transaction mở trong lúc publish qua network hàng giây vì tăng lock contention; dùng claim token/lease và xử lý kết quả sau publish, hoặc cơ chế checkpoint tương đương.

Vẫn phải chấp nhận duplicate nếu worker mất lease hoặc publish success không được ghi nhận. Tăng số relay replica không thay thế idempotency.

## 7. Phân phối sự kiện bằng Pub/Sub

Pub/Sub phù hợp fan-out event tới nhiều projection/consumer: bảng đơn hàng cho API, cập nhật thống kê, thông báo và pipeline phân tích. Mỗi nhóm consumer nên có subscription riêng để việc ack của nhóm này không làm mất message của nhóm khác.

### 7.1. Delivery semantics

Pub/Sub mặc định có **at-least-once delivery**, nên subscriber có thể nhận cùng message nhiều lần do ack deadline, retry hoặc lỗi mạng. Không được cộng doanh thu hai lần chỉ vì nhận hai thông điệp `OrderPaid`.

Pub/Sub có tùy chọn **exactly-once delivery** cho pull subscription trong phạm vi một region, nhưng đó là bảo đảm giao/ack theo message ID do Pub/Sub định nghĩa. Nó không ngăn publisher phát cùng business event thành hai message khác ID và không biến cập nhật database downstream thành transaction chung với Pub/Sub. Vẫn phải deduplicate theo `eventId` và đặt idempotency tại nơi ghi kết quả.

### 7.2. Thứ tự trong aggregate

Nếu muốn subscriber nhận event `OrderPlaced`, `OrderPaid`, `OrderShipped` đúng thứ tự của một order, có thể:

- Dùng `orderingKey = aggregateId` khi publish.
- Bật message ordering ở subscription.
- Publish các message cùng ordering key từ một region và phối hợp publisher nếu có nhiều instance.
- Lưu `aggregateVersion` và từ chối/để chờ version vượt gap trong projector.

Pub/Sub không cung cấp thứ tự tổng giữa mọi aggregate. Ordering key chỉ áp dụng trong phạm vi một key và điều kiện dịch vụ hỗ trợ. Khi message cũ được redeliver, một số message theo sau cùng key cũng có thể được redeliver. Projector phải xử lý được replay/dedup.

Nếu dùng Dataflow để đọc Pub/Sub, không mặc định giả định ordering key được bảo toàn qua toàn bộ Apache Beam pipeline. Thiết kế stateful processing theo key/version hoặc bổ sung checkpoint và điều kiện dữ liệu phù hợp.

### 7.3. Retry, DLQ và xử lý poison message

Nên cấu hình:

- Ack deadline/lease extension phù hợp thời gian projector xử lý.
- Retry với exponential backoff và jitter.
- Dead-letter topic cho event vượt số lần xử lý cho phép.
- Alert trên oldest unacked message, backlog và DLQ count.
- Quy trình sửa lỗi, re-drive/republish event sau khi khắc phục, có kiểm soát idempotency.

Poison event do schema không tương thích hoặc dữ liệu invalid cần được cách ly để điều tra, không retry vô hạn làm tắc một ordering key và gây ảnh hưởng các event phía sau.

## 8. Xây read model và projector idempotent

Projection là hàm chuyển event thành dữ liệu thuận tiện cho query:

~~~text
OrderPlaced(orderId, customerId, total) -> order_summary:
  status = CREATED, total = total

OrderPaid(orderId, paidAt) -> order_summary:
  status = PAID, paid_at = paidAt

OrderShipped(orderId, tracking) -> order_summary:
  status = SHIPPED, tracking = tracking
~~~

Một event có thể cập nhật nhiều projection với tốc độ và mục tiêu khác nhau. Ví dụ `order_summary` cho API cần latency thấp, `sales_analytics` cho BigQuery cần báo cáo chính xác nhưng có thể chấp nhận lag lớn hơn.

### 8.1. Idempotency tại database đích

Nếu projector ghi Cloud SQL, có thể lưu ledger processed events và dữ liệu projection trong cùng transaction:

~~~sql
CREATE TABLE processed_events (
    projector_name VARCHAR(100) NOT NULL,
    event_id       UUID NOT NULL,
    processed_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (projector_name, event_id)
);

CREATE TABLE order_summary (
    order_id       VARCHAR(128) PRIMARY KEY,
    status         VARCHAR(32) NOT NULL,
    aggregate_version BIGINT NOT NULL,
    total_minor    BIGINT,
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

Trong một transaction:

1. INSERT vào `processed_events` với `(projector_name, event_id)`.
2. Nếu conflict, đó có thể là duplicate đã xử lý; bỏ qua update.
3. Kiểm tra version của order hiện tại.
4. Apply event để cập nhật `order_summary`.
5. Commit rồi mới ack message.

Nếu không có atomic transaction giữa dedup ledger và projection state, có thể xảy ra tình huống đánh dấu event đã xử lý nhưng cập nhật read model chưa thành công. Với Firestore, sử dụng transaction trên các document liên quan (trong giới hạn của dịch vụ) hoặc thiết kế last-applied-version giúp update idempotent. Không coi lưu event ID riêng rồi ghi dữ liệu sau bằng hai API call độc lập là atomic.

### 8.2. Version gap và reorder

Giả sử projector đã áp dụng version 5 của order nhưng nhận version 7 trước version 6. Không cập nhật thẳng lên version 7 nếu phép tính phụ thuộc lịch sử. Có thể:

- Park version 7, chờ version 6.
- Load event store để bù missing event.
- Áp dụng idempotent reducer nếu domain cho phép xử lý không theo thứ tự.
- Đưa vào DLQ/repair workflow sau timeout có kiểm soát.

Checkpoint cần được hiểu theo từng aggregate và nguồn event; không thay thế việc kiểm tra idempotency từng event.

### 8.3. Mô hình đọc khác nhau

| Truy vấn | Projection phù hợp | Dịch vụ |
|---|---|---|
| Lấy trạng thái một order theo ID | Document nhỏ, key-value | Firestore hoặc Cloud SQL |
| Danh sách order của customer theo thời gian | Index theo customerId/createdAt | Firestore/Cloud SQL |
| Tính tồn kho hiện tại theo SKU | Row aggregate/version | Cloud SQL/Spanner |
| Doanh thu theo ngày, channel, khu vực | Fact table/aggregate | BigQuery |
| Tra cứu lịch sử nghiệp vụ | Event view/audit projection | Event store + API riêng |

Tách read model theo pattern thực tế. Không tạo một bảng denormalized khổng lồ phục vụ mọi query nếu điều đó tạo bottleneck hay dữ liệu dư thừa khó kiểm soát.

## 9. Eventual consistency và trải nghiệm người dùng

Trong CQRS bất đồng bộ, command side có thể commit trong 50 ms nhưng projector cần thêm vài trăm ms hoặc lâu hơn để cập nhật read model. Người dùng có thể thanh toán thành công nhưng màn hình danh sách vẫn hiển thị trạng thái cũ một thời gian ngắn.

Một API nên có hợp đồng rõ ràng:

~~~http
POST /orders/ord-1042/pay
Idempotency-Key: cmd-8ab1

HTTP/1.1 202 Accepted
Location: /orders/ord-1042
Retry-After: 1
X-Aggregate-Version: 3
~~~

Mã 202 chỉ phù hợp khi việc xử lý theo hợp đồng thật sự bất đồng bộ. Nếu command đã commit nghiệp vụ và hoàn thành ngay, có thể trả 200/201/204 theo hợp đồng API, đồng thời nêu rõ projection có độ trễ.

Các chiến lược:

- **Read-your-writes:** sau command, trả trực tiếp trạng thái mới/aggregate version từ write path trong response, thay vì lập tức hỏi read model cũ.
- **Version token:** query có thể nhận `minVersion` và chờ projection đạt version đó trong giới hạn timeout.
- **Optimistic UI:** hiển thị trạng thái tạm với chỉ dấu đang đồng bộ.
- **Polling/SSE/WebSocket:** client nhận thông báo khi projection sẵn sàng.
- **Fallback:** với truy vấn quan trọng, đọc write model có kiểm soát nếu read model chậm, nhưng cân nhắc chi phí và ranh giới CQRS.

Đặt SLO rõ cho projection freshness, ví dụ “99% event xuất hiện ở order_summary trong 3 giây” theo đo lường thực tế. Không dùng từ “real time” mà không xác định latency, percentile và hành vi khi quá hạn.

## 10. Replay, rebuild và snapshot

Event sourcing tạo khả năng dựng lại trạng thái từ lịch sử, nhưng replay phải được thiết kế và thử nghiệm.

### 10.1. Khi cần replay?

- Tạo projection mới từ event lịch sử.
- Khắc phục bug reducer khiến read model sai.
- Chuyển dữ liệu sang schema hoặc dịch vụ read model mới.
- Khôi phục projection sau mất dữ liệu.
- Tạo analytics backfill theo khoảng thời gian.

### 10.2. Quy trình rebuild an toàn

1. Xác định event store có đủ lịch sử và schema version cần thiết.
2. Tạo read model mới với tên/bảng/collection riêng, không ghi đè trực tiếp dữ liệu đang phục vụ production.
3. Đọc event theo aggregate và version, apply reducer với code đã được kiểm thử.
4. Đồng thời theo dõi event mới (catch-up) hoặc xác định checkpoint consistent phù hợp.
5. So sánh record count, hash/summary, business invariants giữa projection mới và projection cũ.
6. Chuyển query API sang projection mới bằng version/alias/feature flag.
7. Giữ rollback window rồi mới thu hồi projection cũ.

Nếu replay có side effect như gửi email hoặc tạo payment, **không được gọi side-effect handler trong replay**. Reducer phải là hàm xác định dữ liệu; external effects được xử lý theo consumer riêng với cơ chế chặn khi replay.

### 10.3. Snapshot

Một aggregate có hàng trăm nghìn event sẽ tốn thời gian khi load lại từ event đầu tiên. Có thể lưu snapshot tại version N rồi chỉ apply các event N+1 trở đi.

Snapshot cần chứa aggregate ID, version, schema version, checksum và trạng thái đã materialize. Snapshot là dữ liệu tối ưu hóa có thể tái tạo, không thay thế event store trừ khi domain có chính sách retention/compaction được thiết kế đặc biệt.

### 10.4. Replay không đồng nghĩa Pub/Sub replay vô hạn

Pub/Sub cho phép retention/seek/snapshot trong giới hạn cấu hình và dịch vụ; không mặc định lưu sự kiện vĩnh viễn. Nếu domain cần lịch sử nhiều năm, giữ event store hoặc archive có khả năng khôi phục độc lập. Spanner change streams cũng có retention ngắn (thường tối đa 30 ngày theo tài liệu); không dùng làm nguồn replay dài hạn.

## 11. Schema evolution và hợp đồng sự kiện

Event bất biến nghĩa là không tùy ý sửa payload lịch sử mỗi khi model mới phát hành. Cần quản lý version và tương thích.

### 11.1. Quy tắc cơ bản

- Đặt eventType với ý nghĩa nghiệp vụ ổn định.
- Thêm field mới theo hướng backward-compatible khi có thể.
- Reader chịu được field mới không biết và có default phù hợp với field tùy chọn.
- Không đổi ý nghĩa một field cũ nhưng giữ nguyên schemaVersion.
- Với breaking change, dùng event version mới và migration/upcaster có kiểm soát.
- Test replay với event payload của nhiều phiên bản, không chỉ event mới.
- Có contract test giữa producer và consumer nếu nhiều team sử dụng cùng integration event.

Ví dụ, `OrderPlaced.v1` có totalMinor; `OrderPlaced.v2` bổ sung currency. Nếu event lịch sử v1 chưa có currency, upcaster chỉ được chọn default khi domain thật sự có quy tắc hợp lệ (ví dụ tất cả đơn v1 đều VND). Không bịa một currency mặc định khi dữ liệu cũ có thể đa tiền tệ.

### 11.2. Domain event và integration event

Domain event có thể chứa nhiều chi tiết phục vụ aggregate. Integration event công khai chỉ nên chia sẻ dữ liệu cần cho consumer, có version hợp đồng và chính sách PII riêng. Outbox relay có thể chuyển đổi domain event sang integration event trước khi publish.

Khi producer cần thay đổi schema, cần xác định consumer nào phụ thuộc và quy trình dual publish/migration nếu cần. Tránh để một consumer đọc bảng nội bộ của service khác vì nó phá vỡ ranh giới ownership.

## 12. Java/Spring: skeleton command handler và projector

Đoạn code bên dưới mô tả ý tưởng ở mức thiết kế; repository adapter, DTO, DDL idempotency và error mapping phải được triển khai đầy đủ trong dự án thật.

### 12.1. Aggregate reducer

~~~java
sealed interface OrderEvent permits OrderPlaced, OrderPaid, OrderShipped {}

record OrderPlaced(String orderId, long totalMinor) implements OrderEvent {}
record OrderPaid(String orderId, String paymentReference) implements OrderEvent {}
record OrderShipped(String orderId, String trackingCode) implements OrderEvent {}

record OrderState(String orderId, String status, long totalMinor, long version) {
    static OrderState empty(String orderId) {
        return new OrderState(orderId, "NONE", 0, 0);
    }
}

final class OrderReducer {
    static OrderState apply(OrderState state, OrderEvent event) {
        return switch (event) {
            case OrderPlaced e -> new OrderState(
                    e.orderId(), "CREATED", e.totalMinor(), state.version() + 1);
            case OrderPaid e -> new OrderState(
                    e.orderId(), "PAID", state.totalMinor(), state.version() + 1);
            case OrderShipped e -> new OrderState(
                    e.orderId(), "SHIPPED", state.totalMinor(), state.version() + 1);
        };
    }
}
~~~

Ví dụ dùng pattern matching trong switch của các bản Java hỗ trợ tính năng tương ứng, thích hợp với JDK hiện đại đã được dự án kiểm chứng. Reducer thực tế cần validate version, identity và transition; không được để bất kỳ event ngẫu nhiên nào đổi `NONE -> SHIPPED`.

### 12.2. Command handler với Spring transaction

~~~java
@Service
public class PayOrderHandler {
    private final EventStore eventStore;
    private final OutboxRepository outbox;
    private final CommandDedupRepository dedup;

    public PayOrderHandler(
            EventStore eventStore,
            OutboxRepository outbox,
            CommandDedupRepository dedup) {
        this.eventStore = eventStore;
        this.outbox = outbox;
        this.dedup = dedup;
    }

    @Transactional
    public long handle(PayOrder command) {
        // Unique constraint trên commandId ngăn hai request cùng ghi.
        dedup.registerOrThrow(command.commandId());

        OrderAggregate order = eventStore.load(command.orderId());
        order.requireCanPay();

        OrderPaid paid = new OrderPaid(
                command.orderId(), command.paymentReference());
        long version = eventStore.append(
                command.orderId(), order.version(), paid);

        outbox.insert(
                command.eventId(), command.orderId(), version,
                "OrderPaid", command.toIntegrationPayload());
        return version;
    }
}
~~~

`EventStore.append` cần implement optimistic concurrency bằng DB constraint/conditional write trong cùng transaction. DDL dedup và outbox cũng phải nằm trong chính transaction của event store. Nếu eventStore và outbox là hai database/service khác nhau, annotation `@Transactional` trên một DataSource không tạo ra atomic distributed commit. Khi đó cần thiết kế lại ranh giới transaction hoặc cơ chế bảo đảm tương đương.

Lỗi conflict có thể ánh xạ thành HTTP 409 hoặc retry sau khi reload theo chính sách; cùng commandId cần trả kết quả idempotent đã lưu thay vì tự động trừ tiền hai lần.

### 12.3. Projector idempotent

~~~java
@Service
public class OrderSummaryProjector {
    private final ProcessedEventRepository processed;
    private final OrderSummaryRepository summaries;

    public OrderSummaryProjector(
            ProcessedEventRepository processed,
            OrderSummaryRepository summaries) {
        this.processed = processed;
        this.summaries = summaries;
    }

    @Transactional
    public void onEvent(IntegrationEvent event) {
        // insertIfAbsent trả false khi event đã được commit trước đó.
        if (!processed.insertIfAbsent("order-summary-v2", event.eventId())) {
            return;
        }

        OrderSummary summary = summaries.loadForUpdate(event.aggregateId());
        long expected = summary == null ? 1 : summary.version() + 1;
        if (event.aggregateVersion() != expected) {
            // Rollback cả processed event để có thể retry/repair.
            throw new ProjectionVersionGapException(
                    event.aggregateId(), expected, event.aggregateVersion());
        }
        summaries.apply(event);
    }
}
~~~

Đây là skeleton minh họa. Trong thực tế phải quyết định liệu `insertIfAbsent` và `apply` cùng transaction/connection hay không, cách khóa row khi đồng thời, cách xử lý duplicate có version cũ và cách init projection. Acknowledge Pub/Sub **sau** khi transaction projection commit. Nếu projection fail, message được retry hoặc đưa vào DLQ theo policy.

## 13. Dataflow và BigQuery cho read model phân tích

Khi có hàng triệu event/ngày, một projector đơn giản có thể không đủ cho aggregate theo cửa sổ, chuyển đổi schema và throughput analytics. Dataflow (Apache Beam) có thể đọc Pub/Sub/CDC, thực hiện parsing, enrichment, deduplication và ghi BigQuery hoặc storage khác.

### 13.1. Pipeline logic

~~~mermaid
flowchart LR
    Events[Pub/Sub integration events] --> DF[Dataflow pipeline]
    DF --> Validate[Schema validation + eventId]
    Validate --> Transform[Enrich / window / aggregate]
    Transform --> BQ[BigQuery dataset]
    Validate --> Bad[Invalid events quarantine]
    BQ --> BI[BI / analytics queries]
~~~

Dataflow hỗ trợ exactly-once processing trong pipeline ở chế độ tương ứng, nhưng side effect ngoài hệ thống hoặc sink không hỗ trợ cơ chế tương đương có thể vẫn nhận duplicate. Đừng dựa vào cụm từ exactly-once để bỏ idempotency/dedup tại ranh giới database.

### 13.2. Thiết kế BigQuery

Event analytics table có thể chứa `eventId`, `eventType`, `aggregateId`, `aggregateVersion`, `occurredAt`, `ingestedAt` và những field nghiệp vụ đã được cho phép. Partition theo thời gian sự kiện hoặc ingest phù hợp, cluster theo query hot keys, đặt retention và giám sát chi phí scan.

Khi báo cáo tiền, cần xác định cách xử lý event trùng và event sửa sai. Chỉ `COUNT(*)` trên bảng raw events sẽ không chính xác nếu publisher phát duplicate hoặc stream được replay. Có thể dùng bảng dedup theo `eventId` hoặc materialized aggregate dựa trên projection có version.

## 14. Bảo mật, kiểm toán và dữ liệu nhạy cảm

Event sourcing lưu lịch sử lâu dài làm tăng rủi ro lưu thông tin nhạy cảm không cần thiết.

### 14.1. Data minimization

- Chỉ lưu field cần cho ý nghĩa nghiệp vụ và khả năng replay.
- Không lưu password, access token, card PAN, khóa bí mật hoặc dữ liệu tài chính nhạy cảm dạng plaintext.
- Dùng token/reference hoặc mã hóa thích hợp cho trường nhạy cảm.
- Tách PII khỏi event bất biến nếu quy định yêu cầu xóa hoặc sửa PII.
- Thiết kế retention, access control, legal hold và quy trình data subject request trước khi ghi event vào kho lâu dài.

“Event bất biến” không có nghĩa được bỏ qua quyền xóa dữ liệu theo pháp luật. Có thể dùng crypto-shredding, payload tách riêng, redaction/tombstone hoặc chính sách retention thích hợp tùy loại dữ liệu và yêu cầu tuân thủ; cần đánh giá với nhóm bảo mật/pháp chế và khả năng tái tạo projection.

### 14.2. IAM và network

| Thành phần | Quyền tối thiểu |
|---|---|
| Command service | Ghi event store và outbox thuộc domain của mình |
| Outbox relay | Đọc/claim outbox, publish đúng Pub/Sub topic |
| Projection worker | Subscriber trên subscription riêng, ghi đúng read model |
| Query service | Read-only read model; không cần append event |
| Dataflow worker | Đọc subscription và ghi đúng BigQuery dataset |
| Auditor | Chỉ đọc event history theo policy; không tự chỉnh payload |

Cloud Run/GKE nên dùng workload identity/service account riêng; tránh key JSON tĩnh. Database dùng private connectivity, TLS, IAM database authentication khi phù hợp; secret trong Secret Manager. Log/traces không chứa event payload nhạy cảm.

### 14.3. Audit và bằng chứng

Event sourcing có thể hỗ trợ truy vết nghiệp vụ, nhưng **không thay thế Cloud Audit Logs** cho hành động quản trị/IAM/API của hạ tầng. Cần lưu ai khởi tạo command, correlationId, version, thời điểm commit và nguồn sự kiện; không mặc định mọi field này đều đáng tin nếu nhận từ client. Server phải xác thực identity và tạo audit metadata đáng tin cậy.

## 15. Observability và SLO cho CQRS

Một hệ thống CQRS có thể trả command thành công nhưng read model bị chậm; vì vậy giám sát chỉ command API là không đủ.

### 15.1. Metrics quan trọng

| Metric | Ý nghĩa | Tín hiệu bất thường |
|---|---|---|
| Command latency p95/p99 | Thời gian xác nhận transaction | Database contention/lock/quota |
| Command conflict rate | Version/idempotency conflicts | Hot aggregate, retry storm |
| Outbox oldest unpublished age | Độ trễ event chưa rời DB | Relay lỗi hoặc backlog |
| Publish error/retry count | Sự cố relay/PubSub | IAM, quota, network |
| Pub/Sub oldest unacked age | Backlog subscription | Consumer giảm throughput |
| Projection lag p95/p99 | Từ event commit đến read model cập nhật | SLO freshness vi phạm |
| Version gap / DLQ | Event thiếu hoặc schema lỗi | Ordering, logic, poison event |
| Replay throughput/checkpoint | Tiến độ rebuild | Rebuild quá chậm hoặc kẹt |
| Read query latency | Trải nghiệm truy vấn | Index/capacity/read model |
| Duplicate suppression count | Event được bỏ qua do idempotency | Retry/publisher duplication |

Cloud Logging/Monitoring/Trace giúp liên kết request `correlationId` đến command, database transaction, outbox relay, Pub/Sub message và projector. Cần tránh high-cardinality labels ở hệ thống metrics; đặt ID chi tiết trong trace/log có quyền truy cập hạn chế.

### 15.2. Error budget và alert

Ví dụ SLO:

- 99,9% command hợp lệ commit trong thời gian được chọn.
- 99% order-summary projection bắt kịp event mới trong 3 giây.
- Không mất event đã commit (thiết kế, backup và test khôi phục phải chứng minh).
- 99,9% query API thành công trong ngân sách latency.

Ngưỡng là ví dụ, phải chọn theo nhu cầu nghiệp vụ và đo thực tế. Cảnh báo khi oldest unpublished outbox age tăng, projection lag vượt ngưỡng, DLQ có event mới hoặc số event version gap tăng liên tục.

## 16. Kiểm thử chiến lược CQRS + event sourcing

### 16.1. Unit và domain tests

- Given event history → When command → Then event mới hoặc domain error.
- Reducer apply cùng event history hai lần cho kết quả xác định.
- Các transition không hợp lệ phải bị từ chối.
- Mọi business invariant được kiểm tra tại aggregate command boundary.
- Event schema version cũ vẫn được reducer/upcaster hiểu đúng.

### 16.2. Integration tests trên project GCP riêng

- Dùng Cloud SQL/Spanner thật để xác minh atomic append và unique version.
- Mô phỏng hai command đồng thời cùng expected version: chỉ một thành công.
- Gây lỗi relay giữa publish và mark-published: event được phát lại nhưng projection không nhân đôi.
- Nhận version N+2 trước N+1: projector không ghi trạng thái sai.
- Publish duplicate business event với messageId Pub/Sub khác nhau: eventId dedup vẫn hiệu quả.
- Tắt worker để backlog tăng, bật lại và đo catch-up.
- Đưa poison event sai schema vào DLQ và thử repair/re-drive.
- Rebuild projection ở storage mới, so sánh invariants trước cutover.

Không chạy stress/replay toàn bộ production event stream trong project thử nghiệm không có budget và quota rõ ràng. Dùng dữ liệu tổng hợp, hoặc dữ liệu production đã được xử lý theo chính sách bảo mật.

### 16.3. Fault injection

Kiểm tra đường thất bại quan trọng:

| Điểm lỗi | Điều phải giữ |
|---|---|
| DB transaction rollback | Không có event/outbox tương ứng được coi là commit |
| Relay chết trước publish | Outbox còn và được retry |
| Relay chết sau publish | Duplicate có thể có; projector idempotent |
| Projector commit rồi chết trước ack | Message redeliver không tạo double effect |
| Projector nhận event sai thứ tự | Không bỏ qua version gap âm thầm |
| Read store mất dữ liệu | Có khả năng rebuild từ event store |
| Event schema mới không tương thích | Dừng/park/DLQ có audit, không làm sai dữ liệu |

## 17. Ví dụ kiến trúc: xử lý đơn hàng

Ứng dụng thương mại điện tử có các yêu cầu:

- Không được ghi hai lần một khoản thanh toán.
- Client thấy trạng thái đơn theo ID trong thời gian ngắn.
- Báo cáo doanh thu và customer history không làm chậm write path.
- Có thể giải thích tại sao đơn từ CREATED chuyển thành PAID hoặc CANCELLED.

### Bước 1: chọn boundary và event

Aggregate Order chứa orderId, trạng thái, tổng tiền và version. Command: PlaceOrder, PayOrder, ShipOrder, CancelOrder. Event: OrderPlaced, OrderPaid, OrderShipped, OrderCancelled.

### Bước 2: chọn storage

- Cloud SQL PostgreSQL làm event store và outbox trong một transaction.
- Pub/Sub topic `orders.events` phân phối integration events.
- Firestore lưu `order-summary` cho query trạng thái đơn.
- BigQuery lưu fact table cho analytics qua Dataflow.
- Cloud Run chạy command API, query API và projector; Cloud Run Jobs dùng cho replay có kiểm soát.

Đây là một lựa chọn tham khảo; nếu cần transactional scale lớn/multi-region, có thể đánh giá Spanner. Nếu ứng dụng nhỏ và không cần event history dài hạn, CQRS với bảng CRUD + outbox có thể đơn giản hơn.

### Bước 3: command PayOrder

1. Client gửi PayOrder với commandId/idempotency key.
2. Server xác thực người dùng và kiểm tra quyền trên Order.
3. Load event history/snapshot và expected aggregateVersion.
4. Kiểm tra trạng thái có thể thanh toán và payment reference hợp lệ.
5. Commit `OrderPaid` và outbox record cùng transaction.
6. Trả version mới; relay publish integration event sau commit.

### Bước 4: projection

- OrderSummary projector nhận OrderPaid, kiểm tra eventId/version, update document Firestore.
- Analytics projector đưa event vào Dataflow/BigQuery với dedup eventId.
- Notification consumer có thể gửi email theo workflow riêng, có idempotency key để không gửi hai lần khi Pub/Sub redeliver.

### Bước 5: query và trải nghiệm người dùng

Query API đọc Firestore, trả status và lastAppliedVersion. Nếu client vừa gửi command cần thấy trạng thái ngay, có thể hiển thị thông tin đã commit trong command response hoặc poll tới khi lastAppliedVersion đạt version mới.

### Bước 6: vận hành và phục hồi

Giám sát command conflicts, outbox lag, Pub/Sub backlog, projection lag và query latency. Khi phát hiện bug projection, deploy reducer đã sửa, rebuild read model vào collection mới, kiểm tra đối soát rồi chuyển alias/query API. Không chỉnh sửa lịch sử event để “làm đẹp” số liệu nếu không có quy trình correction rõ ràng.

## 18. Khi nào không nên dùng CQRS hoặc event sourcing?

Những pattern này có chi phí kiến trúc đáng kể:

- Nhiều storage model và data pipelines cần vận hành, backup, kiểm thử và giám sát.
- Eventual consistency làm UI/API và logic đọc phức tạp hơn.
- Event schema/version và replay cần năng lực quản trị lâu dài.
- Dữ liệu nhạy cảm khó xóa hoặc sửa trong kho event bất biến.
- Duplicate, ordering và version gap tạo thêm nhánh lỗi.
- Debugging cần correlation ID và tracing xuyên dịch vụ.
- Replay lớn có thể tốn nhiều compute, storage I/O và chi phí.

Không nên dùng event sourcing chỉ để có một bảng audit hoặc để mọi cập nhật đều phát Pub/Sub. Nếu chỉ cần read replicas, indexing hoặc báo cáo đơn giản, hãy đánh giá tối ưu SQL/index, materialized view, cache hoặc CDC trước.

Một lộ trình tăng dần an toàn:

1. Bắt đầu từ CRUD và domain boundaries rõ ràng.
2. Tách command/query interface trong code nếu read/write khác nhau.
3. Thêm outbox để phát integration events đáng tin cậy.
4. Xây projection phụ, đo lợi ích thực tế.
5. Chỉ chuyển aggregate có yêu cầu audit/replay quan trọng sang event sourcing.
6. Cải tiến versioning, snapshot, replay và observability trước khi mở rộng nhiều bounded contexts.

## 19. Checklist thiết kế và triển khai

### Domain và dữ liệu

- [ ] Đã xác định rõ bounded context và aggregate invariants.
- [ ] CQRS và event sourcing được chọn độc lập, có lý do nghiệp vụ.
- [ ] Event store có atomic append, ordering và optimistic concurrency.
- [ ] Event có eventId, aggregateId, aggregateVersion, schemaVersion, commandId.
- [ ] Có chiến lược schema evolution/upcaster và contract testing.
- [ ] Có chính sách retention, PII và dữ liệu phải xóa theo quy định.

### Messaging và projection

- [ ] Tránh dual write nhờ transaction + outbox hoặc giải pháp đảm bảo tương đương.
- [ ] Relay và projector đều có retry/backoff, checkpoint, DLQ.
- [ ] Consumer idempotent theo eventId/business key.
- [ ] Ordering/version gap được thiết kế theo aggregate.
- [ ] Mỗi projection có ranh giới dữ liệu và ownership rõ ràng.
- [ ] Đã xác định SLO freshness và hành vi read-your-writes.

### GCP và vận hành

- [ ] Chọn Cloud SQL/Spanner/Firestore/BigQuery theo write/read pattern thật.
- [ ] Không coi Pub/Sub hoặc change streams là event store vĩnh viễn.
- [ ] IAM và service account tách theo command, relay, projector, query.
- [ ] Có log/trace/correlation ID, metrics và cảnh báo projection lag.
- [ ] Có backup, replay, rebuild, reconciliation và rollback plan.
- [ ] Test duplicate, concurrent write, out-of-order, replay và fault injection.
- [ ] Đã tính chi phí lưu event dài hạn, storage/index, Pub/Sub, Dataflow và BigQuery.

## 20. Tài liệu tham khảo chính thức

- [Spanner change streams overview](https://cloud.google.com/spanner/docs/change-streams)
- [Spanner transactions](https://cloud.google.com/spanner/docs/transactions)
- [Cloud SQL documentation](https://cloud.google.com/sql/docs)
- [Datastream overview](https://cloud.google.com/datastream/docs/overview)
- [Pub/Sub subscription overview](https://cloud.google.com/pubsub/docs/subscription-overview)
- [Pub/Sub message ordering](https://cloud.google.com/pubsub/docs/ordering)
- [Pub/Sub exactly-once delivery](https://cloud.google.com/pubsub/docs/exactly-once-delivery)
- [Pub/Sub dead-letter topics](https://cloud.google.com/pubsub/docs/dead-letter-topics)
- [Cloud Run documentation](https://cloud.google.com/run/docs)
- [Firestore real-time listeners](https://cloud.google.com/firestore/native/docs/query-data/listen)
- [Firestore triggers with Cloud Run functions](https://cloud.google.com/firestore/native/docs/extend-with-cloud-run-functions)
- [Dataflow streaming modes](https://cloud.google.com/dataflow/docs/guides/streaming-modes)
- [Dataflow and Pub/Sub streaming](https://cloud.google.com/dataflow/docs/concepts/streaming-with-cloud-pubsub)
- [BigQuery documentation](https://cloud.google.com/bigquery/docs)
- [Cloud Storage lifecycle management](https://cloud.google.com/storage/docs/lifecycle)
- [Google Cloud IAM best practices](https://cloud.google.com/iam/docs/using-iam-securely)

**Kết luận:** CQRS giúp độc lập tối ưu đường ghi và đường đọc; event sourcing cung cấp lịch sử sự kiện nghiệp vụ có thể replay. Trên GCP, sự kết hợp Cloud SQL hoặc Spanner cho transaction, Pub/Sub cho phân phối, Firestore/Cloud SQL cho projection phục vụ ứng dụng và Dataflow/BigQuery cho analytics là một kiến trúc khả thi khi nhu cầu thực sự biện minh cho độ phức tạp. Điều quyết định độ tin cậy là ranh giới source of truth, atomic append/outbox, idempotency, versioning, bảo mật dữ liệu và khả năng phục hồi có kiểm thử.
