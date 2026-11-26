# Phối hợp Neo4j với kho dữ liệu khác và quản lý nhất quán liên hệ thống

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Xác định **nguồn dữ liệu có thẩm quyền** (*source of truth*) của mỗi thực thể khi ứng dụng dùng Neo4j đồng thời với RDBMS, search engine, cache hoặc event broker.
- Phân biệt **nhất quán trong một transaction Neo4j** với **nhất quán giữa nhiều hệ thống**; lựa chọn nhất quán mạnh, nhất quán cuối cùng hoặc quy trình bù trừ đúng nghiệp vụ.
- Giải thích vì sao **dual-write** sang hai database không an toàn nếu chỉ thực hiện hai lệnh ghi nối tiếp.
- Thiết kế luồng **transactional outbox → broker/CDC → consumer Neo4j** với khóa nghiệp vụ, idempotency, version, kiểm soát thứ tự và xử lý sự kiện xóa.
- Thiết kế **snapshot/backfill, checkpoint, retry, dead-letter queue, reconciliation** và cơ chế phục hồi khi một thành phần ngừng hoạt động.
- Kết hợp Java Driver hoặc Spring Data Neo4j với transaction tại kho nguồn mà không nhầm đó là một giao dịch phân tán.
- Đo độ trễ đồng bộ, tỷ lệ sai lệch dữ liệu và tác động tới những truy vấn quan hệ/đường đi quan trọng.

Chương **Thiết kế ứng dụng** thuộc module **DATABASE_ENGINE_GRAPH_NEO4J**. Neo4j biểu diễn dữ liệu liên kết bằng **property graph**: node, relationship, thuộc tính và truy vấn Cypher. Trong hệ thống thực tế, một ứng dụng cũng có thể dùng PostgreSQL/MySQL để xử lý đơn hàng, Kafka để truyền sự kiện, Elasticsearch/OpenSearch để tìm kiếm và Redis để cache. Giá trị của từng kho dữ liệu là khác nhau; thách thức lớn là **giữ các bản biểu diễn nhất quán theo hợp đồng nghiệp vụ** khi mỗi kho có transaction, mô hình dữ liệu và tốc độ cập nhật riêng.

> Ví dụ minh họa dùng PostgreSQL và Neo4j với Java. Tên bảng, thuộc tính, Java API, connector và quy trình vận hành phải điều chỉnh theo phiên bản sản phẩm đang chạy. **Không có một transaction ACID tự động bao trùm PostgreSQL, Neo4j, Kafka và HTTP** chỉ vì ứng dụng sử dụng Spring `@Transactional`.

## 1. Vì sao kết hợp nhiều kho dữ liệu?

Một hệ thống bán hàng có các yêu cầu:

1. Kiểm soát giao dịch thanh toán, tồn kho và hóa đơn với các ràng buộc chặt.
2. Truy vấn “khách hàng này đã mua những sản phẩm nào, có liên hệ với những khách hàng khác ra sao?”.
3. Tìm kiếm toàn văn trên tên hoặc mô tả sản phẩm.
4. Cung cấp response API nhanh và cache các màn hình truy cập thường xuyên.

Không nhất thiết ép tất cả yêu cầu vào một cơ sở dữ liệu:

| Thành phần | Vai trò phù hợp | Điều phải xác định |
| --- | --- | --- |
| **RDBMS** | Giao dịch nguồn: đơn hàng, thanh toán, tồn kho, ràng buộc quan hệ | Bảng nào là nguồn sự thật? |
| **Neo4j** | Truy vấn đa bước, quan hệ khách hàng–đơn hàng–sản phẩm, đường đi, phát hiện kết nối | Đồ thị là bản sao đọc hay là nguồn ghi chính? |
| **Search engine** | Tìm kiếm văn bản, ranking, phân tích token | Chỉ mục có thể cập nhật trễ bao lâu? |
| **Cache** | Giảm latency cho kết quả đọc phổ biến | Invalidate/TTL như thế nào? |
| **Event broker** | Truyền thay đổi có thể phát lại/khôi phục và tách producer–consumer | Ordering, retention, delivery guarantee ra sao? |

Kiến trúc này thường gọi là **polyglot persistence**. Nó không có nghĩa mọi kho đều được phép sửa cùng một thực thể mà không có nguyên tắc.

### 1.1. Ví dụ luồng đơn hàng

~~~mermaid
flowchart LR
    API["Order API / Java Service"] -->|Ghi transaction nguồn| R[("PostgreSQL<br/>Orders + Outbox")]
    R -->|Outbox publisher / CDC| B["Kafka hoặc message broker"]
    B --> N["Graph projector / consumer"]
    N -->|Neo4j transaction| G[("Neo4j<br/>Customer-PLACED-Order")]
    B --> S["Search indexer"]
    S --> X[("Search engine")]
    QR["Relationship API"] -->|Cypher READ| G
~~~

**Giả định kiến trúc của ví dụ:** PostgreSQL là nơi quyết định đơn hàng có thật hay đã được thanh toán. Neo4j là **read model** phục vụ truy vấn liên kết; khi Neo4j chậm nhận event, đơn hàng **không biến mất khỏi nguồn sự thật**. Truy vấn graph có thể tạm thời chưa phản ánh thay đổi mới nhất.

Nếu Neo4j là nguồn sự thật cho một quan hệ nghiệp vụ khác (ví dụ cấu trúc cây tổ chức), phải thiết kế **chiều đồng bộ ngược lại** và ranh giới quyền ghi riêng. Không suy diễn rằng PostgreSQL luôn là nguồn chính cho mọi dữ liệu.

## 2. Định nghĩa ownership và bất biến trước khi viết code

Một hợp đồng dữ liệu giữa các hệ thống cần trả lời:

- Ai có quyền **tạo, sửa, xóa** từng loại đối tượng?
- ID nào bền vững xuyên các kho: `customerId`, `orderId`, `sku`?
- Khi thuộc tính thay đổi, **phiên bản (version)** được tăng ở đâu?
- Bản sao Neo4j cần cập nhật trong bao lâu: vài giây hay ngay trong request?
- Khi một bên lỗi, có được trả “thành công” hay phải chặn giao dịch nguồn?

Ví dụ hợp đồng cho một mô hình read-side:

| Dữ liệu | Nguồn có thẩm quyền | Bản sao Neo4j | Quy tắc |
| --- | --- | --- | --- |
| `Customer.customerId` | Customer Service / RDBMS | Node `:Customer` | Không phát sinh ID mới khi sao chép |
| `Order.orderId`, `status`, `totalCents` | Order Service / RDBMS | Node `:Order` | Đọc/áp dụng theo source version |
| `Customer -[:PLACED]-> Order` | Theo ID khách hàng sở hữu đơn trong Order Service | Relationship trong Neo4j | Phản ánh đúng ownership, kể cả khi đổi/xóa |
| `Product.sku` | Product Catalog | Node `:Product` | Dùng ID ổn định; event đến trễ có thể xảy ra |
| `Order -[:CONTAINS]-> Product` | Order Service / dữ liệu dòng hàng | Relationship trong Neo4j | Không giả định thiếu node là lỗi vĩnh viễn |

**Bất biến nghiệp vụ** là điều luôn phải đúng ở nguồn: ví dụ một đơn chỉ được thu tiền một lần, không có số lượng tồn kho âm, hai đơn không dùng cùng `orderId`. **Bất biến bản sao** là điều graph phải hội tụ tới: đúng node, đúng relationship, đúng `sourceVersion`, không có cạnh cũ sau khi đổi ownership.

Phân biệt **bất biến luôn đúng ngay lập tức** và **bất biến được phép trễ**:

- Không thu tiền hai lần: **không được trễ/sai**; xử lý trong hệ thống có thẩm quyền và phương án thanh toán lũy đẳng.
- Danh sách “đơn hàng tương tự” trên Neo4j cập nhật sau 2 giây: có thể chấp nhận nếu sản phẩm cho phép.
- Phê duyệt cấp quyền truy cập dựa trên graph được đồng bộ chậm: **rủi ro cao**; không nên dựa vào read model trễ nếu quyết định an ninh yêu cầu trạng thái tức thời.

## 3. ACID cục bộ không biến thành ACID liên hệ thống

Neo4j hỗ trợ transaction ACID cho những thay đổi **trong chính database Neo4j**. PostgreSQL cũng có transaction riêng. Hai transaction **không tự commit/rollback cùng nhau**:

~~~text
BEGIN PostgreSQL
    UPDATE orders SET status = 'PAID' ...
COMMIT PostgreSQL

BEGIN Neo4j
    MATCH (o:Order {orderId: ...}) SET o.status = 'PAID'
COMMIT Neo4j
~~~

Đoạn trên là mã giả. Nếu lệnh đầu đã commit và chương trình crash trước lệnh thứ hai, PostgreSQL đã đổi trạng thái còn Neo4j chưa đổi. Spring `@Transactional` tại một service **không mặc nhiên bao trùm hai transaction manager** hoặc biến một cuộc gọi HTTP/message broker thành thành viên của cùng giao dịch.

### 3.1. Anti-pattern: dual-write trực tiếp

~~~mermaid
sequenceDiagram
    participant App as Order Service
    participant RDB as PostgreSQL
    participant Graph as Neo4j
    App->>RDB: COMMIT Order = PAID
    RDB-->>App: OK
    Note over App: Crash / timeout
    App--xGraph: Chưa cập nhật :Order
    Note over RDB,Graph: Hai bản biểu diễn tạm thời lệch nhau
~~~

Đảo thứ tự ghi cũng không giải quyết căn bản: nếu Neo4j commit trước rồi PostgreSQL thất bại, graph lại chứa trạng thái chưa được nguồn chấp nhận.

| Cách xử lý | Bảo đảm | Rủi ro |
| --- | --- | --- |
| Hai lệnh ghi nối tiếp | Không có atomicity xuyên kho | Crash ở giữa gây sai lệch |
| Retry lệnh ghi thứ hai | Tăng khả năng hội tụ | Không giải quyết mất request khi tiến trình chết nếu không có bản ghi bền vững cần retry |
| Transactional outbox ở kho nguồn | Thay đổi nghiệp vụ và **ý định phát event** commit nguyên tử trong kho nguồn | Consumer vẫn bất đồng bộ, cần retry và dedup |
| Saga/bù trừ | Điều phối nhiều transaction cục bộ với các hành động bù | Không cung cấp rollback tức thời kiểu một transaction duy nhất |
| Giao dịch phân tán/2PC | Có thể điều phối atomic commit nếu **tất cả hệ thống và cấu hình hỗ trợ thực sự** | Phức tạp, ảnh hưởng độ sẵn sàng; không được giả định Neo4j + RDBMS + broker tự hỗ trợ |

Với graph read model, **outbox + đồng bộ cuối cùng** thường hợp lý hơn cố gắng áp dụng một transaction phân tán cho mọi bước.

## 4. Transactional outbox: thay đổi dữ liệu và sự kiện cùng commit

Transactional outbox lưu một event **ngay trong database có thẩm quyền**, **cùng transaction** với thay đổi nghiệp vụ. Một tiến trình publisher/CDC khác mới chuyển event đó tới broker hoặc consumer.

~~~mermaid
flowchart TD
    A["Order Service nhận command"] --> T["Transaction PostgreSQL"]
    T --> O["UPDATE orders và tăng version"]
    O --> E["INSERT outbox_events"]
    E --> C{"COMMIT?"}
    C -->|Không| R["Rollback cả Order và Outbox"]
    C -->|Có| P["Publisher/CDC lấy event"]
    P --> B["Broker / Consumer Neo4j"]
~~~

### 4.1. Lược đồ PostgreSQL minh họa

~~~sql
CREATE TABLE orders (
    order_id       text PRIMARY KEY,
    customer_id    text NOT NULL,
    status         text NOT NULL,
    total_cents    bigint NOT NULL,
    version        bigint NOT NULL DEFAULT 0
);

CREATE TABLE outbox_events (
    event_id           uuid PRIMARY KEY,
    aggregate_type     text NOT NULL,
    aggregate_id       text NOT NULL,
    aggregate_version  bigint NOT NULL,
    event_type         text NOT NULL,
    payload            jsonb NOT NULL,
    created_at         timestamptz NOT NULL DEFAULT now(),
    published_at       timestamptz
);

CREATE UNIQUE INDEX outbox_order_version_uk
ON outbox_events (aggregate_type, aggregate_id, aggregate_version);
~~~

Lược đồ này là **minh họa**, không phải schema bắt buộc. Ràng buộc duy nhất theo aggregate/version chỉ phù hợp khi **mỗi version phát một event tương ứng**; nếu nghiệp vụ phát nhiều event cùng version, cần thiết kế key khác. Cần chính sách retention, quyền đọc và xử lý dữ liệu nhạy cảm trong `payload`.

Giả sử một command cập nhật trạng thái, trong **cùng transaction PostgreSQL**:

~~~sql
BEGIN;

UPDATE orders
SET status = 'PAID',
    version = version + 1
WHERE order_id = :orderId
  AND status = 'PENDING'
RETURNING order_id, customer_id, status, total_cents, version;

-- Ứng dụng lấy đúng hàng UPDATE trả về để xây event snapshot,
-- rồi chèn event có cùng order_id và version trong transaction này.
INSERT INTO outbox_events (
    event_id, aggregate_type, aggregate_id,
    aggregate_version, event_type, payload
)
VALUES (
    :eventId, 'Order', :orderId,
    :newVersion, 'OrderChanged', :payloadJson
);

COMMIT;
~~~

Hai câu SQL phụ thuộc vào logic ứng dụng lấy giá trị `RETURNING`; **nếu UPDATE trả 0 hàng**, không chèn event và phải quyết định trả lỗi, xử lý idempotent hoặc bỏ qua theo quy tắc nghiệp vụ. Tất cả phải nằm trên **cùng connection/transaction PostgreSQL**. Tránh tự chèn event với `version` lấy từ truy vấn ngoài transaction đang cập nhật.

Trong Spring, có thể để `@Transactional` của **RDBMS transaction manager** bao quanh repository cập nhật đơn và insert outbox; sau khi commit, publisher bất đồng bộ mới phát sự kiện. Không gọi Neo4j rồi tin rằng transaction annotation này bao trùm luôn Neo4j.

### 4.2. Payload tối thiểu, có version và ID ổn định

~~~json
{
  "eventId": "f3d0b1f1-0181-4b3f-bebb-44a0b9c17355",
  "eventType": "OrderChanged",
  "schemaVersion": 1,
  "aggregateType": "Order",
  "aggregateId": "O-901",
  "aggregateVersion": 12,
  "occurredAt": "2026-11-25T08:12:00Z",
  "data": {
    "orderId": "O-901",
    "customerId": "C-101",
    "status": "PAID",
    "totalCents": 150000
  }
}
~~~

Các giá trị là **giả định**. Sự kiện nên chứa thông tin đủ để projector dựng trạng thái mà không phải gọi lại nhiều service cho từng event. `aggregateVersion` giúp phân biệt event cũ/mới; `schemaVersion` giúp consumer giải mã khi hợp đồng event tiến hóa; `eventId` giúp deduplication. Không phát thừa thông tin nhạy cảm nếu graph chỉ cần mã và trạng thái.

### 4.3. Publisher không có “exactly once” miễn phí

Giả sử publisher:

1. Lấy outbox event.
2. Gửi lên Kafka, broker đã nhận.
3. Crash trước khi đánh dấu `published_at`.

Lúc chạy lại, publisher có thể gửi **cùng event hai lần**. Do đó, outbox thông thường đem lại cơ sở để **không mất ý định phát sự kiện**, nhưng **delivery có thể trùng**. Ngay cả khi một broker/connector quảng bá cơ chế exactly-once trong phạm vi của nó, cần kiểm tra chính xác **phạm vi bảo đảm**; không suy ra mọi tác dụng trên Neo4j và hệ thống ngoài cũng exactly-once.

Thay đổi trạng thái outbox sang published **trước** khi broker xác nhận cũng nguy hiểm: crash sau bước đó có thể làm **mất event**.

## 5. CDC lấy dữ liệu từ đâu? Phân biệt nguồn và đích

**Change Data Capture (CDC)** đọc các thay đổi được commit rồi phát sang downstream. Có hai chiều kiến trúc khác nhau:

| Luồng | Nguồn thay đổi | Khi dùng |
| --- | --- | --- |
| **PostgreSQL → Neo4j** | Outbox hoặc CDC của PostgreSQL | RDBMS là nguồn sự thật, Neo4j làm graph projection |
| **Neo4j → hệ thống khác** | **Neo4j CDC** hoặc outbox ứng dụng dựa trên nguồn Neo4j | Graph là nơi phát sinh thay đổi có thẩm quyền |

Không nhầm việc cài một **Neo4j sink connector** (ghi vào Neo4j) với việc **bật Neo4j CDC** (đọc thay đổi ra khỏi Neo4j). Với luồng PostgreSQL → Neo4j, projector có thể hoạt động bằng Kafka consumer + Neo4j Java Driver mà **không cần Neo4j CDC**.

### Điều kiện khi Neo4j là nguồn CDC

Neo4j CDC chính thức là tính năng có điều kiện theo **version, edition/gói triển khai và cấu hình**. Trong dòng Neo4j 5.x, CDC được giới thiệu từ 5.13 cho Enterprise, namespace procedure thay đổi ở 5.17 từ `cdc.*` sang `db.cdc.*`; các bản mới cần đối chiếu tài liệu cùng phiên bản. Neo4j Community không mặc nhiên có CDC chính thức. Ngoài việc được hỗ trợ, phải **bật change capture mode** thích hợp và kiểm tra quyền đọc CDC.

Nếu cần đồng bộ Neo4j → Kafka/search, phải thiết kế **cursor, retention của transaction log, checkpoint và snapshot ban đầu** như với bất kỳ nguồn CDC đáng tin cậy nào. Không tự coi Neo4j CDC là một message queue vô hạn; cursor cũ có thể không còn hợp lệ khi log bị prune hoặc database trải qua một số sự kiện vòng đời.

## 6. Biến event thành node và relationship trong Neo4j

Consumer phía Neo4j thường **không cần tái thực thi toàn bộ transaction PostgreSQL**. Nó cần **chiếu (project)** hợp đồng dữ liệu thành đúng node, relationship và thuộc tính.

### 6.1. Chuẩn bị uniqueness constraint

~~~cypher
CREATE CONSTRAINT customer_id_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.customerId IS UNIQUE;

CREATE CONSTRAINT order_id_unique IF NOT EXISTS
FOR (o:Order)
REQUIRE o.orderId IS UNIQUE;

CREATE CONSTRAINT applied_graph_event_id_unique IF NOT EXISTS
FOR (e:AppliedGraphEvent)
REQUIRE e.eventId IS UNIQUE;
~~~

Các constraint này:

- Bảo vệ ID logic trong graph; không dựa vào internal node ID hoặc `elementId` làm khóa liên hệ thống.
- Cho phép Cypher dùng index hậu thuẫn uniqueness để tìm node theo `customerId`/`orderId`.
- Ngăn hai transaction **commit cùng eventId** vào bảng theo dõi sự kiện đã xử lý.

Neo4j `MERGE` không tự thay thế uniqueness constraint khi nhiều consumer cùng ghi cạnh tranh. Đối với nhiều relationship song song hoặc các khóa tổng hợp, cần thiết kế mô hình/constraint và cơ chế khóa thích hợp với phiên bản Neo4j đang dùng.

### 6.2. Một câu Cypher cập nhật graph projection

Với event `OrderChanged` có **trạng thái đầy đủ**, trong trường hợp `customerId` của đơn **không đổi**:

~~~cypher
MERGE (c:Customer {customerId: $customerId})
MERGE (o:Order {orderId: $orderId})
SET o.status = $status,
    o.totalCents = $totalCents,
    o.sourceVersion = $version
MERGE (c)-[:PLACED]->(o)
RETURN o.orderId AS orderId;
~~~

`MERGE` tìm hoặc tạo node/cạnh theo mẫu. Vì sự kiện chứa ID khách hàng, consumer có thể tạo một **Customer placeholder** chỉ có `customerId` nếu thông tin khách hàng chưa đến. Khi event khách hàng xuất hiện sau đó, cập nhật thuộc tính có thẩm quyền. Phải có chính sách cho placeholder và các node/relationship mồ côi, không tự chấp nhận mọi tình trạng thiếu dữ liệu mãi mãi.

**Không chạy câu này mù quáng khi event cũ đến sau event mới.** Lệnh `SET` không kiểm tra `sourceVersion` sẽ **ghi lùi trạng thái**. Tầng consumer phải kiểm tra thứ tự hoặc áp dụng chiến lược version phù hợp (phần 7).

### 6.3. Khi quan hệ đổi hoặc đối tượng bị xóa

Nếu một đơn có thể đổi khách hàng sở hữu, lệnh `MERGE (c)-[:PLACED]->(o)` có thể để lại cạnh cũ. Với một event **ownership snapshot** có thẩm quyền, cần xóa cạnh `PLACED` cũ **của chính đơn đó**, rồi tạo cạnh mới trong **cùng transaction Neo4j**:

~~~cypher
MATCH (o:Order {orderId: $orderId})
OPTIONAL MATCH (:Customer)-[old:PLACED]->(o)
DELETE old
WITH DISTINCT o
MERGE (newOwner:Customer {customerId: $customerId})
MERGE (newOwner)-[:PLACED]->(o)
RETURN o.orderId;
~~~

Truy vấn này chỉ là bước **thay ownership** theo event đã được kiểm tra version. Nó xóa **toàn bộ cạnh PLACED đến đơn**; chỉ đúng khi hợp đồng nghiệp vụ quy định đúng một chủ sở hữu và `PLACED` không mang ý nghĩa khác. Không dùng nguyên xi nếu một đơn có nhiều chủ sở hữu hợp lệ.

Với event xóa, xác định rõ **tombstone**:

- Xóa mềm: đặt `o.deleted = true`, giữ graph để truy xuất lịch sử theo yêu cầu.
- Xóa vật lý: thực hiện `DETACH DELETE o` khi thật sự muốn xóa node và **mọi relationship** gắn với nó.
- Xóa relationship riêng: `MATCH ... DELETE r` nếu chỉ liên kết mất hiệu lực.

Đừng xóa node đã được sử dụng bởi domain khác, hoặc để một event cũ tái tạo node vừa xóa. Với xóa vật lý, cần giữ **tombstone/version** ở vị trí phù hợp để chặn event upsert trễ; nếu không, bản ghi có thể “sống lại”.

## 7. Idempotency và thứ tự sự kiện: điều kiện để hội tụ

Broker hoặc webhook thường có khả năng **gửi lặp, chậm, đảo thứ tự hoặc mất khả năng kết nối tạm thời**. Vì vậy **consumer không được coi một event mới nhận luôn là event mới nhất**.

### 7.1. Event ID và aggregate version giải quyết hai việc khác nhau

| Trường | Mục đích | Giới hạn |
| --- | --- | --- |
| `eventId` | Nhận diện cùng **một sự kiện** được giao lại | Hai event khác ID vẫn có thể cùng tác dụng nghiệp vụ |
| `orderId` | Nhận diện cùng **một đơn hàng** xuyên database | Không thể hiện thứ tự |
| `aggregateVersion` | So sánh trạng thái mới/cũ **trong một aggregate** | Không tự sắp thứ tự giữa các aggregate khác nhau |
| `schemaVersion` | Biết cấu trúc payload để giải mã | Không phải source version của dữ liệu |
| `occurredAt` | Phục vụ quan sát và SLA đồng bộ | Timestamp không thay thế số phiên bản đơn điệu khi clock lệch |

Ví dụ:

~~~text
Event E10: Order O-901, version 10, status=PENDING
Event E12: Order O-901, version 12, status=PAID
Event E11: Order O-901, version 11, status=CONFIRMED  (đến sau E12)
~~~

Nếu projector áp dụng **mọi event theo thời điểm nhận**, trạng thái cuối cùng sẽ sai `CONFIRMED`. Với **full-state event** có version đơn điệu, có thể bỏ qua event đã cũ (version ≤ version đã áp dụng). Với **delta event** như “tăng số lượng thêm 1”, **không được bỏ qua gap tùy tiện**: cần phát hiện thiếu version 11 trước khi áp dụng version 12 hoặc có nguồn snapshot để tái dựng chính xác.

### 7.2. Mẫu consumer Neo4j Java Driver

Giả định kiến trúc:

1. Mỗi event là **full-state của một Order** với `orderId`, `customerId`, `status`, `totalCents`, `aggregateVersion`.
2. Broker partition theo `orderId`; **chỉ một worker chủ động xử lý một order tại một thời điểm**. Nếu có nhiều worker ghi cùng order ngoài cơ chế đó, bắt buộc bổ sung locking/CAS thích hợp; phép kiểm tra version đơn thuần trước `SET` không tự chứng minh an toàn dưới mọi cuộc đua.
3. Neo4j đã có các uniqueness constraint phần 6 và consumer không làm side effect ngoài database trong callback.

~~~java
import java.util.Map;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public record OrderChanged(
        String eventId,
        String orderId,
        String customerId,
        String status,
        long totalCents,
        long version
) {}

public final class OrderGraphProjector {
    private final Driver driver;

    public OrderGraphProjector(Driver driver) {
        this.driver = driver;
    }

    public void apply(OrderChanged event) {
        Map<String, Object> p = Map.of(
                "eventId", event.eventId(),
                "orderId", event.orderId(),
                "customerId", event.customerId(),
                "status", event.status(),
                "totalCents", event.totalCents(),
                "version", event.version());

        try (Session session =
                driver.session(SessionConfig.forDatabase("neo4j"))) {
            session.executeWrite(tx -> {
                boolean alreadyApplied = !tx.run("""
                    MATCH (e:AppliedGraphEvent {eventId: $eventId})
                    RETURN e.eventId AS id
                    """, p).list().isEmpty();
                if (alreadyApplied) {
                    return null;
                }

                long currentVersion = tx.run("""
                    OPTIONAL MATCH (o:Order {orderId: $orderId})
                    RETURN coalesce(o.sourceVersion, -1) AS v
                    """, p).single().get("v").asLong();

                if (event.version() > currentVersion) {
                    tx.run("""
                        MERGE (c:Customer {customerId: $customerId})
                        MERGE (o:Order {orderId: $orderId})
                        SET o.status = $status,
                            o.totalCents = $totalCents,
                            o.sourceVersion = $version
                        MERGE (c)-[:PLACED]->(o)
                        """, p).consume();
                }

                // Ghi marker và các thay đổi graph trong CÙNG
                // transaction Neo4j để tránh ghi nửa chừng.
                tx.run("""
                    CREATE (e:AppliedGraphEvent {
                        eventId: $eventId,
                        orderId: $orderId,
                        sourceVersion: $version,
                        appliedAt: datetime()
                    })
                    """, p).consume();
                return null;
            });
        }
    }
}
~~~

**Đặc điểm của mẫu:**

- `executeWrite` bao toàn bộ phần đọc marker, kiểm tra version, cập nhật graph và ghi marker; commit hoặc rollback là **một transaction Neo4j**.
- Nếu callback được driver retry do lỗi transient, thao tác phải chịu được việc chạy lại. **Không phát Kafka message, gửi email, gọi API thanh toán** trong callback.
- Khi một event cũ đến, graph không bị ghi lùi; marker vẫn ghi nhận event đã được xử lý theo chính sách full-state.
- Khi **cùng event** đến lại sau commit, tìm marker cho phép bỏ qua.
- **Race cần xử lý rõ:** nếu cùng eventId được hai transaction đồng thời xử lý, constraint trên `AppliedGraphEvent.eventId` khiến ít nhất một giao dịch không thể commit marker trùng. Giao dịch bị lỗi phải được rollback và caller kiểm tra lại marker để phân biệt duplicate với lỗi thực. Không mặc định exception nào cũng là thành công.

Mẫu không giải quyết đầy đủ **event xóa, đổi customer, nhiều event giữa các aggregate, thay đổi schema** hoặc **ghi song song lên một `orderId`**. Những tình huống đó cần event handler riêng và thiết kế khóa/ordering phù hợp. Để tránh graph catalog chứa vô hạn marker, có thể quản lý retention `AppliedGraphEvent` **chỉ khi** có chính sách đảm bảo event cũ không còn được phát lại hoặc có watermark/version thay thế an toàn.

### 7.3. Checkpoint ở broker và trong Neo4j

Quy trình nên là:

1. Nhận event từ broker.
2. Ghi projection **và marker** bằng transaction Neo4j.
3. Chỉ khi transaction Neo4j đã commit thành công, mới **acknowledge/commit offset** theo semantics của consumer.

Nếu commit graph thành công nhưng tiến trình crash **trước khi commit offset**, broker có thể gửi lại → marker/idempotency bảo vệ khỏi ghi lặp. Nếu acknowledge **trước** khi graph commit rồi consumer crash, event có thể mất khỏi luồng xử lý. Đây là lý do phải chọn thứ tự **ghi bền vững trước, ack sau**.

Nếu consumer phụ thuộc một luồng CDC kiểu cursor thay vì broker offset, nguyên tắc tương tự: checkpoint sau khi sink đã ghi bền vững. **Kafka offset** và **Neo4j CDC change identifier** là hai cơ chế khác nhau, không thể thay thế trực tiếp.

## 8. Event ordering trên nhiều thực thể và tính hội tụ

Partition theo `orderId` giúp giữ trật tự cho một đơn **khi producer cùng chọn partition key và connector/broker bảo đảm ordering trong phạm vi partition**. Nó **không** bảo đảm:

- Customer event đến trước Order event.
- Product event đến trước relationship `CONTAINS`.
- Mọi aggregate thuộc một nghiệp vụ đều được cập nhật nguyên tử trong Neo4j.
- Thứ tự event giữa hai partition phản ánh chính xác thứ tự commit ở tất cả database.

Các cách ứng phó:

| Chiến lược | Khi hữu ích | Cần cảnh giác |
| --- | --- | --- |
| **Placeholder node** với ID logic | Relationship đến trước dữ liệu đầy đủ của endpoint | Cần lấp dữ liệu và phát hiện placeholder tồn lâu |
| **Retry với backoff** khi thiếu endpoint | Event phụ thuộc có thể đến sau | Retry vô hạn có thể giữ backlog; cần DLQ |
| **Partition theo aggregate key** | Duy trì thứ tự event của cùng aggregate | Key phải nhất quán ở publisher/consumer |
| **Version/checkpoint** | Bỏ qua update cũ và phát hiện gap | Chỉ “bỏ gap” an toàn với full-state event phù hợp |
| **Reconciliation định kỳ** | Sửa trôi dạt sau lỗi/bug/retention | Phải có nguồn chuẩn và cách đối soát hiệu quả |

**Tính hội tụ (convergence)** nghĩa là khi nguồn ngừng phát thay đổi và hệ thống xử lý hết backlog, bản sao Neo4j phải phản ánh trạng thái nguồn theo hợp đồng. Muốn chứng minh điều này cần mô hình event, xử lý delete, version và reconciliation rõ ràng; chỉ có cơ chế retry chưa đủ.

## 9. Đồng bộ dữ liệu ban đầu: snapshot và streaming changes

Một hệ thống Neo4j mới cần cả **dữ liệu lịch sử** và các thay đổi sau khi bắt đầu đồng bộ.

~~~mermaid
flowchart TD
    A["Tạo mốc đồng bộ nguồn"] --> B["Đọc snapshot / backfill"]
    B --> C["Upsert node/relationship vào Neo4j"]
    C --> D["Áp dụng event sau mốc theo version"]
    D --> E["Theo dõi lag và đối soát"]
~~~

### 9.1. Vì sao không thể chỉ “dump rồi mới subscribe”?

~~~text
T1: Bắt đầu export bảng orders
T2: Order O-901 được cập nhật ở nguồn và COMMIT
T3: Export hoàn tất
T4: Consumer mới subscribe các event từ hiện tại
~~~

Nếu snapshot tại T1 chưa chứa cập nhật T2 và consumer chỉ lấy sự kiện sau T4, **thay đổi giữa T1 và T4 bị bỏ sót**.

Một phương án robust:

1. Thiết lập **CDC/outbox offset mốc** có thể phát lại, theo hướng dẫn của connector/source.
2. Lấy snapshot tại điểm nhất quán hoặc theo cơ chế snapshot có kiểm soát.
3. Nạp dữ liệu bằng business ID, kèm source version.
4. Replay event sau mốc, áp dụng **idempotent + version** để tránh ghi lùi khi snapshot và stream giao thoa.
5. Đối soát node, edge, version và số liệu nghiệp vụ trước khi bật API sử dụng graph rộng rãi.

Không có **một thủ thuật chung** đảm bảo snapshot nhất quán cho mọi RDBMS/broker. Với PostgreSQL có thể cần snapshot transaction, WAL/LSN và thuật toán CDC của connector; với nguồn khác dùng cơ chế tương ứng. Chọn một chiến lược cụ thể, tài liệu hóa thời điểm cắt và phép thử không mất event.

### 9.2. Backfill bằng UNWIND và chia batch

Java có thể đọc các record từ nguồn rồi gửi các batch vào Neo4j:

~~~cypher
UNWIND $orders AS item
MERGE (c:Customer {customerId: item.customerId})
MERGE (o:Order {orderId: item.orderId})
SET o.status = item.status,
    o.totalCents = item.totalCents,
    o.sourceVersion = item.version
MERGE (c)-[:PLACED]->(o);
~~~

Đây là mẫu **minh họa nạp snapshot** khi graph đích trống hoặc không có luồng cập nhật cạnh tranh. Nếu đồng thời đang chạy CDC, lệnh `SET` trên có thể **ghi đè phiên bản mới** bằng snapshot cũ; phải có logic version guard/điều phối phù hợp trước khi cho hai luồng ghi song song. Không lấy sự đơn giản của `UNWIND` làm lý do bỏ kiểm soát ordering.

Mỗi batch thường được commit riêng để hạn chế thời gian transaction, RAM và lock. Khi batch sau lỗi, batch trước đã commit không tự rollback. Vì thế batch phải **có thể chạy lại**, có checkpoint và thống kê số record lỗi.

## 10. Đọc dữ liệu khi hai kho chưa đồng bộ

**Eventual consistency** nghĩa là bản sao có thể **trễ trong một khoảng thời gian**, nhưng cần có mục tiêu và cách xử lý rõ ràng, không phải “chấp nhận sai mãi mãi”.

### 10.1. Ví dụ read-your-writes

Người dùng tạo đơn trong PostgreSQL, rồi lập tức truy cập trang xem quan hệ đơn trên Neo4j:

~~~text
T1: POST /orders -> PostgreSQL COMMIT O-901
T2: API trả 201 Created
T3: GET /graph/customers/C-101/orders -> Neo4j chưa có O-901
T4: Consumer xử lý OrderChanged
T5: GET /graph/... -> thấy O-901
~~~

Không thể dùng **Neo4j bookmark** để “bắt buộc” read-side đợi một PostgreSQL commit mà Neo4j chưa hề nhận; bookmark chỉ phục vụ nhất quán nhân quả **trong phạm vi Neo4j** theo driver/session.

Các lựa chọn thiết kế API:

| Yêu cầu sản phẩm | Cách xử lý | Đánh đổi |
| --- | --- | --- |
| Trang thanh toán phải thấy đúng đơn ngay | Đọc từ **source of truth RDBMS** | Có thể không dùng được traversal Neo4j cho màn hình đó |
| Gợi ý liên kết có thể trễ vài giây | Đọc Neo4j và hiển thị `lastUpdatedAt` hoặc nhãn “đang đồng bộ” | UI chấp nhận trễ |
| Phải thấy sau khi projection hoàn tất | Trả operation ID/version, cho client poll trạng thái xử lý/đợi có giới hạn | Tăng latency và độ phức tạp |
| Đọc toàn graph nhưng cần snapshot nghiệp vụ | Tạo materialized view theo mốc version hoặc một luồng batch nhất quán | Độ mới có giới hạn |

**Không sử dụng graph read model trễ để quyết định các giao dịch không được sai** như khấu trừ tồn kho hoặc cấp quyền khẩn cấp nếu nguồn có thẩm quyền nằm ở hệ thống khác.

### 10.2. Hợp đồng độ tươi (*freshness contract*)

Ví dụ một API có thể công bố:

~~~json
{
  "customerId": "C-101",
  "relatedOrders": ["O-901", "O-902"],
  "projectionVersion": 12,
  "dataAsOf": "2026-11-25T08:12:02Z",
  "isSynchronizing": false
}
~~~

Các trường trên chỉ là **thiết kế DTO minh họa**, không phải trường Neo4j tự cung cấp. Nếu trình bày `projectionVersion`, phải định nghĩa nó ứng với aggregate nào, mốc nào và cách lấy; không dùng một số `12` của đơn O-901 để chứng minh mọi đơn/customer/product đã đồng bộ đến cùng mốc.

Một mục tiêu ví dụ: “99% sự kiện có thể quan sát trên graph trong vòng 5 giây sau nguồn commit”. Đây là **SLO do nhóm tự đặt**; cần đo `commitTime → applyTime` và xử lý skew giữa đồng hồ. Không coi đó là bảo đảm mặc định của Neo4j hoặc broker.

## 11. Nhiều nguồn cùng cần ghi: Saga và hành động bù

Không phải mọi quy trình đều là đồng bộ read model. Ví dụ khách hàng đặt hàng đồng thời phải:

1. Giữ tồn kho trong Inventory Service.
2. Thu tiền qua Payment Service.
3. Xác nhận đơn trong Order Service.
4. Tạo graph quan hệ liên quan nếu ứng dụng cần đọc từ Neo4j.

Đây là một **quy trình liên hệ thống có quyết định nghiệp vụ**, thường thiết kế dưới dạng **Saga**:

~~~mermaid
flowchart TD
    A["Create Order: PENDING"] --> B["Reserve inventory"]
    B --> C{"Reserve OK?"}
    C -->|Không| X["Cancel Order"]
    C -->|Có| D["Charge payment"]
    D --> E{"Payment OK?"}
    E -->|Không| F["Release inventory + cancel order"]
    E -->|Có| G["Confirm order"]
    G --> H["Outbox event -> cập nhật Neo4j"]
~~~

Mỗi bước thay đổi nguồn của chính service trong **transaction cục bộ**. Khi bước sau thất bại, Saga phát **compensating action**: ví dụ giải phóng phần tồn kho đã giữ. Hành động bù là một nghiệp vụ mới, **không phải rollback vật lý của transaction đã commit**.

### Lưu ý Saga

- Quy định **idempotency key** cho mọi command, đặc biệt thanh toán và refund.
- Mỗi bước có trạng thái `PENDING/SUCCEEDED/FAILED/COMPENSATING`, timeout và chính sách retry.
- Có thể chọn **orchestration** (điều phối viên quản lý trạng thái) hoặc **choreography** (các service phản ứng với event).
- Một bước đã xảy ra bên ngoài (ví dụ thanh toán ngân hàng) không nhất thiết đảo được ngay; yêu cầu quy trình bù và đối soát.
- Graph projection trong ví dụ này thường **không nên là điều kiện commit** của thanh toán: nếu graph sync chậm, đơn đã được xác nhận ở nguồn vẫn hợp lệ.

Nếu Neo4j là **nguồn có thẩm quyền** cho một hành động như duyệt cây quyền truy cập, phải xác định **transaction Neo4j** nào giữ bất biến và kết quả nào cần công bố bằng event; không ép nó vào pattern “chỉ là projection”.

## 12. Vấn đề giao dịch đồng thời, thứ tự và thiết kế ID

### 12.1. Không sử dụng elementId làm ID liên hệ thống

`elementId(n)` phục vụ nhận diện phần tử trong phạm vi Neo4j theo semantics phiên bản, **không phải khóa nghiệp vụ bền vững xuyên backup, restore, export hay hệ thống khác**. Thiết kế node theo `customerId`, `orderId`, `sku` hoặc ID ổn định do domain quản lý, đi kèm uniqueness constraint.

### 12.2. Một producer phải gán version ở nơi kiểm soát đồng thời

Không tạo `aggregateVersion` từ timestamp máy ứng dụng. Version cần đơn điệu trong **mỗi aggregate**: có thể tăng trong transaction cập nhật hàng RDBMS, hoặc sử dụng cơ chế sequence/compare-and-set phù hợp nguồn. Khi nhiều instance cùng sửa order, database phải giải quyết write conflict để hai event không vô tình nhận cùng version.

### 12.3. Ghi đa nguồn cùng một thuộc tính gây xung đột sở hữu

Nếu cả Customer Service và Neo4j graph service đều có thể `SET o.status`, một event đồng bộ trễ có thể ghi đè thay đổi trên Neo4j. Có ba lựa chọn rõ ràng:

1. **Single writer:** chỉ một service được quyền quyết định `Order.status`.
2. **Tách thuộc tính:** RDBMS sở hữu `status`, Neo4j sở hữu `graphScore`/thuộc tính phân tích riêng.
3. **Giải quyết xung đột có hợp đồng:** version/vector clock hoặc chiến lược CRDT/merge phù hợp nghiệp vụ; không dùng last-write-wins theo thời gian đồng hồ một cách vô thức.

**Lựa chọn mặc định nên ưu tiên:** single writer theo từng thuộc tính/aggregate, đặc biệt với trạng thái nghiệp vụ quan trọng. Quản lý nhiều nguồn ghi tự do khiến consistency khó kiểm soát hơn đáng kể.

## 13. Các tình huống lỗi và quy trình phục hồi

| Sự cố | Điều có thể xảy ra | Cách phục hồi |
| --- | --- | --- |
| Order Service crash **trước commit nguồn** | Cả thay đổi đơn và outbox rollback | Retry command theo idempotency key |
| Source commit thành công, publisher chưa gửi | Event vẫn nằm trong outbox | Publisher/CDC resume và gửi tiếp |
| Publisher gửi xong nhưng crash trước checkpoint | Broker nhận event lặp | Consumer dedup bằng `eventId` |
| Neo4j commit xong, consumer crash trước ack | Broker gửi lại event | Marker/phiên bản giúp xử lý lặp |
| Event 12 đến trước event 11 | Có nguy cơ ghi lùi khi 11 đến sau | Full-state version guard; hoặc gap detection cho delta |
| Product event chưa đến, Order–Product relationship đến trước | Thiếu endpoint dữ liệu đầy đủ | Placeholder, retry phụ thuộc hoặc DLQ có kiểm soát |
| Consumer ngừng lâu hơn retention broker/CDC | Không phát lại được toàn bộ khoảng bị mất | Báo lỗi, snapshot/backfill lại và đối soát |
| Event xóa đến muộn | Node/relationship sai hoặc bị tái tạo | Tombstone/version + chính sách delete rõ |
| Schema event thay đổi | Consumer parse lỗi hoặc đọc sai dữ liệu | Schema version, backward compatibility, migration |
| Neo4j không đủ dung lượng/cluster tạm lỗi | Backlog tăng, API graph thấy dữ liệu cũ | Backpressure, retry có giới hạn, cảnh báo lag, tăng tài nguyên có cơ sở |
| Restore Neo4j từ backup cũ | Graph mất những projection sau mốc backup | Chạy lại từ checkpoint phù hợp hoặc tái bootstrap; không dùng offset cũ mù quáng |

### 13.1. Dead-letter queue không phải thùng rác

Event có thể không thể xử lý do payload sai schema, thiếu ID, ràng buộc không phù hợp hoặc dữ liệu bị xung đột. Sau số lần retry hợp lý:

- Chuyển event cùng **ID, nguyên nhân lỗi, thời điểm, phiên bản schema** vào **dead-letter queue (DLQ)** hoặc kho lỗi có quản lý.
- Giữ đủ thông tin để điều tra nhưng **không ghi lộ thông tin nhạy cảm**.
- Có công cụ replay có kiểm soát và đảm bảo consumer áp dụng idempotency/version khi phát lại.
- Đặt cảnh báo khi DLQ tăng hoặc backlog vượt SLO; **không âm thầm bỏ qua event** rồi tuyên bố hệ thống nhất quán.

### 13.2. Reconciliation định kỳ

Ngay cả pipeline có retry vẫn có thể xảy ra lỗi logic: mapping sai, mất event trước khi tạo checkpoint, delete thiếu cạnh hoặc schema cũ được dùng quá lâu. **Reconciliation** là đối soát nguồn và bản sao:

1. Chọn mốc **watermark/version** hoặc khoảng thời gian có thể so sánh.
2. Lấy danh sách/order ID từ nguồn theo batch.
3. Truy vấn node `Order` trong Neo4j theo `orderId` và `sourceVersion`; kiểm tra trạng thái và ownership.
4. Phân loại **missing / stale / divergent / orphaned**.
5. Tự động sửa những lỗi có quy tắc an toàn; lỗi nhạy cảm cần điều tra hoặc xử lý thủ công.

Ví dụ Cypher tra cứu trạng thái bản sao cho một tập ID:

~~~cypher
UNWIND $orderIds AS orderId
OPTIONAL MATCH (o:Order {orderId: orderId})
OPTIONAL MATCH (c:Customer)-[:PLACED]->(o)
RETURN orderId,
       o.sourceVersion AS graphVersion,
       o.status AS graphStatus,
       collect(DISTINCT c.customerId) AS ownerIds;
~~~

Nếu không có node `Order`, các trường thuộc tính trả `null`; `ownerIds` có thể rỗng. Để tìm node **thừa** trong graph nhưng không có ở nguồn, phải đối chiếu theo một tập/watermark bao quát cả hai phía, không chỉ query những ID đang tồn tại ở nguồn.

Truy vấn đối soát trên graph lớn cần **batch, index, giới hạn concurrency và scheduling**; đừng chạy quét toàn bộ production vào giờ cao điểm.

## 14. Quan sát, hiệu năng và bảo mật

Một pipeline nhất quán liên hệ thống cần giám sát **cả sức khỏe vận chuyển lẫn chất lượng dữ liệu**.

### 14.1. Những chỉ số cần đo

| Nhóm | Metric gợi ý | Cần cảnh báo khi |
| --- | --- | --- |
| **Độ trễ đồng bộ** | p50/p95/p99 của `source commit → Neo4j apply` | Vượt SLO |
| **Backlog** | Số event chưa xử lý, tuổi event cũ nhất, consumer lag | Tăng liên tục hoặc gần vượt retention |
| **Khả năng xử lý** | Events/s gửi và áp dụng, throughput theo entity type | Apply chậm hơn tốc độ thay đổi nguồn |
| **Độ tin cậy** | Retry, timeout, transient error, số event DLQ | Lỗi đột biến hoặc DLQ tồn lâu |
| **Tính đúng đắn** | Missing node, stale version, sai ownership, duplicate marker | Bất kỳ sai lệch vượt ngưỡng cho phép |
| **Neo4j** | CPU, heap/GC, page cache, DB Hits, lock wait, transaction latency | Projector ảnh hưởng truy vấn graph chính |
| **Nguồn và broker** | Outbox chưa publish, WAL/log retention, disk, queue depth | Event có nguy cơ không thể phát lại |

**Không so sánh p99 chỉ trên event thành công rồi bỏ qua các event lỗi**. Cần công bố đồng thời tỷ lệ hoàn tất, số lỗi, backlog và thời gian chờ; nếu hàng trăm event đã quá hạn nhưng chưa thành công thì “p99 đã apply rất thấp” không phản ánh hệ thống đang khỏe.

### 14.2. Tối ưu projector Neo4j

- Dùng **Neo4j Java Driver** theo mô hình Driver dùng chung, Session riêng; gom các lệnh liên quan vào **`executeWrite`**.
- Tạo index/uniqueness constraint cho business key dùng trong `MERGE`/`MATCH`.
- Batch event theo khóa nghiệp vụ nếu cần, nhưng **không phá ordering** của cùng aggregate; tránh một transaction quá lớn.
- Dùng `UNWIND` để upsert nhiều bản ghi khi semantics event/version cho phép và đã xử lý tranh chấp.
- Không tạo relationship không có ý nghĩa truy vấn; tránh graph “mọi thứ kết nối với mọi thứ” gây fan-out lớn.
- Trên đường đọc, dùng `EXPLAIN`/`PROFILE` để kiểm tra seek/expand, số hàng trung gian, DB Hits và chi phí join/sort.

Khi dùng Spring Data Neo4j, một entity graph có thể chứa nhiều relationship; không cần tải lại toàn aggregate cho mỗi event nếu một câu Cypher `MERGE/SET` có thể cập nhật chính xác phần cần thay đổi. Nếu project graph qua entity repository, kiểm tra rõ lifecycle mapping và nguy cơ cập nhật quan hệ ngoài ý muốn.

### 14.3. Bảo mật và phân quyền liên hệ thống

**Dữ liệu lưu ở nhiều kho = nhiều bề mặt rủi ro.** Cần:

- Service account riêng cho publisher, consumer và API; áp dụng **least privilege** ở RDBMS, broker và Neo4j.
- TLS phù hợp cho kết nối Neo4j `neo4j+s://`/`bolt+s://` và kết nối khác; quản lý secret trong secret manager.
- Không đưa số thẻ thanh toán, token hay PII không cần thiết vào outbox/event/bản sao graph.
- Chính sách retention, xóa dữ liệu theo yêu cầu pháp lý và xử lý **delete/tombstone** xuyên hệ thống.
- Cân nhắc cách bảo vệ multi-tenant: đặt `tenantId` trong hợp đồng định danh, constraint và truy vấn; không để sự kiện tenant này nối relationship với tenant khác.
- Kiểm soát quyền truy vấn **graph traversal**: mối liên hệ giữa hai entity có thể là thông tin nhạy cảm ngay cả khi thuộc tính từng node không nhạy cảm.

## 15. Bài thực hành: PostgreSQL và Neo4j cùng quản lý đơn hàng

**Bài toán:** Order Service ghi vào PostgreSQL; Neo4j phục vụ API `GET /customers/{id}/related-orders`. Đơn mới phải xuất hiện trong graph sau một khoảng trễ được cấu hình, không để ID trùng hoặc ghi lùi trạng thái.

### Bước 1 — Viết hợp đồng

Thống nhất:

- PostgreSQL quyết định `orderId`, `customerId`, `status` và `version`.
- Event `OrderChanged` có `eventId`, `aggregateVersion` và snapshot đủ dữ liệu.
- Neo4j chỉ ghi các thuộc tính đồng bộ này thông qua projector; thuộc tính phân tích graph riêng do job khác sở hữu.
- API giao dịch bắt buộc đọc nguồn, API quan hệ có thể đọc bản sao.
- Chỉ một worker áp dụng event cho cùng `orderId` tại một thời điểm.

### Bước 2 — Tạo constraint trong Neo4j

Thực hiện ba câu `CREATE CONSTRAINT` ở phần 6. Kiểm tra index đã sẵn sàng:

~~~cypher
SHOW INDEXES
YIELD name, labelsOrTypes, properties, state
RETURN name, labelsOrTypes, properties, state
ORDER BY name;
~~~

### Bước 3 — Tạo dữ liệu và outbox tại nguồn

Trong **cùng PostgreSQL transaction**, tạo/cập nhật đơn và thêm event vào outbox. Kiểm tra nếu transaction bị rollback thì **không còn cả thay đổi đơn lẫn outbox mới**. Đây là bước kiểm chứng ranh giới atomicity của nguồn.

### Bước 4 — Mô phỏng sự cố vận chuyển

Dùng một event `E-100` để kiểm tra bốn kịch bản:

1. Giao `E-100` một lần: có node `Order`, relationship `PLACED`, marker.
2. Giao lại `E-100`: graph không thêm Order hoặc marker trùng.
3. Giao version 12 trước version 11 của cùng Order: trạng thái không bị ghi lùi khi event 11 đến sau.
4. Consumer crash sau Neo4j commit nhưng trước ack broker: event phát lại phải được xử lý an toàn.

### Bước 5 — Thử delete và ownership change

Nếu domain cho phép đổi chủ sở hữu:

- Gửi event snapshot với `customerId` mới và version cao hơn.
- Xác minh **không còn relationship PLACED cũ** nếu hợp đồng nói một chủ sở hữu.
- Đảm bảo số lượng cạnh `PLACED` hướng vào mỗi `Order` là đúng, không tự dùng `MERGE` để bỏ qua cạnh cũ.

Nếu đơn bị hủy hoặc xóa, thảo luận lựa chọn **soft delete** và **hard delete**, cùng cách tránh event cũ tái tạo đơn sau khi xóa.

### Bước 6 — Đo eventual consistency

Ghi lại thời gian source commit, thời gian broker nhận, thời gian Neo4j commit và thời gian query có thể nhìn thấy node. Tính độ trễ theo phân vị và đếm event lỗi/backlog. Thử tạm dừng consumer rồi chạy lại để xem hệ thống **bắt kịp** và không vượt retention.

### Bước 7 — Đối soát

Lấy một tập `orderId` từ PostgreSQL, so sánh `status`, `version`, `customerId` và cạnh `PLACED` với Neo4j. Chủ động tạo một trạng thái sai trong database thực hành rồi xác minh quy trình reconciliation phát hiện và sửa **đúng nguồn có thẩm quyền**.

### Câu hỏi tự kiểm tra

**1. Vì sao không đặt `@Transactional` quanh lệnh ghi PostgreSQL rồi gọi Neo4j để có atomicity xuyên hai kho?**

Vì transaction manager chỉ điều phối những tài nguyên mà nó thực sự quản lý. Hai transaction cục bộ không tự thành một distributed transaction ACID; nếu một bên commit trước, bên còn lại vẫn có thể lỗi.

**2. Transactional outbox đã bảo đảm event đến consumer đúng một lần chưa?**

Chưa. Sự kiện có thể được giao lại khi publisher crash sau gửi nhưng trước checkpoint. Consumer cần xử lý idempotent.

**3. Dùng `MERGE (o:Order {orderId:$id})` đã đủ chặn update trễ ghi lùi chưa?**

Chưa. `MERGE` nhận diện node, không kiểm tra version. Cần source version, ordering và mô hình xử lý ghi đồng thời.

**4. Neo4j bookmark có bảo đảm node đã xuất hiện ngay sau PostgreSQL commit không?**

Không. Bookmark phục vụ nhất quán nhân quả trong Neo4j, không làm cho một event chưa được đồng bộ từ hệ thống khác xuất hiện sớm.

**5. Nếu event version 12 đến trước version 11, luôn được bỏ qua version 11 hay không?**

Không. Chỉ có thể bỏ qua một cách an toàn theo hợp đồng **full-state snapshot event** hoặc cơ chế tương đương. Với delta event, thường cần phát hiện gap và phục hồi sự kiện thiếu.

**6. Neo4j graph read model mất sạch sau restore cũ, chỉ khởi động consumer từ offset mới nhất có đủ không?**

Không. Graph có thể mất dữ liệu đã có ở nguồn nhưng không còn được replay. Cần backfill/khôi phục checkpoint thích hợp và đối soát.

## 16. Checklist kiến trúc liên hệ thống

- [ ] Chỉ định **system of record** cho từng entity/relationship/thuộc tính; không để multi-writer tùy tiện.
- [ ] Phân biệt rõ **source invariants** và **projection invariants**; đặt SLO độ trễ cập nhật phù hợp.
- [ ] Không dual-write không bảo vệ giữa PostgreSQL, Neo4j, broker và search.
- [ ] Dùng outbox/CDC theo ranh giới transaction **thực sự có thể bảo đảm**; thiết kế delivery có thể trùng.
- [ ] Chuẩn hóa `eventId`, `aggregateId`, `aggregateVersion`, `schemaVersion` và payload.
- [ ] Dùng **business ID và uniqueness constraint** trong Neo4j; không dùng internal ID/`elementId` làm khóa liên hệ thống.
- [ ] Consumer lưu marker/checkpoint bền vững; ghi graph xong mới ack offset.
- [ ] Xử lý **out-of-order**, concurrency cùng aggregate, retry, DLQ, delete/tombstone và thay ownership.
- [ ] Snapshot/backfill ban đầu có mốc cắt phù hợp; không bỏ sót event ở khoảng giao thoa.
- [ ] API quyết định nơi đọc theo nhu cầu: giao dịch tức thời từ nguồn, graph traversal có thể dùng read model trễ.
- [ ] Thiết kế Saga/compensation riêng khi nhiều service **thật sự cần phối hợp thao tác ghi**.
- [ ] Giám sát lag, lỗi, tỷ lệ dữ liệu sai, throughput, log retention và tài nguyên Neo4j.
- [ ] Có reconciliation định kỳ, cách repair an toàn và quy trình diễn tập recovery.
- [ ] Bảo vệ dữ liệu nhạy cảm, tài khoản dịch vụ, mã hóa, multi-tenancy và chính sách xóa liên hệ thống.
- [ ] Kiểm thử lỗi crash **trước/sau commit**, phát event trùng, đảo thứ tự, thiếu endpoint và restore backup.

## Tài liệu tham khảo

- [Neo4j Java Driver Manual — Transactions](https://neo4j.com/docs/java-manual/current/transactions/)
- [Neo4j Cypher Manual — Constraints](https://neo4j.com/docs/cypher-manual/current/constraints/)
- [Neo4j Cypher Manual — MERGE](https://neo4j.com/docs/cypher-manual/current/clauses/merge/)
- [Neo4j Change Data Capture — Introduction](https://neo4j.com/docs/cdc/current/)
- [Neo4j Connector for Apache Kafka](https://neo4j.com/docs/kafka/current/)
- [Spring Data Neo4j Reference](https://docs.spring.io/spring-data/neo4j/reference/)
- [Microservices.io — Transactional Outbox](https://microservices.io/patterns/data/transactional-outbox.html)
- [Microservices.io — Saga](https://microservices.io/patterns/data/saga.html)

**Kết luận:** Khi phối hợp Neo4j với RDBMS, broker, search và cache, bài toán cốt lõi không chỉ là chuyển record giữa các hệ thống mà là **thiết kế một hợp đồng nhất quán có thể kiểm chứng**. Xác định nguồn có thẩm quyền, ghi outbox cùng transaction nguồn, áp dụng projection trong transaction Neo4j, quản lý idempotency và version, rồi đo lag và đối soát định kỳ. Với thao tác liên hệ thống có hậu quả nghiệp vụ, dùng Saga/compensation hoặc cơ chế điều phối được hỗ trợ thay vì giả định các transaction cục bộ sẽ tự commit nguyên tử cùng nhau.
