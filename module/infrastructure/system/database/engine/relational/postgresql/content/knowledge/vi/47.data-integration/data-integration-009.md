# CDC, sự kiện dữ liệu và bảo đảm xử lý ở hệ thống nhận trong PostgreSQL

Khi một giao dịch thay đổi dữ liệu trong PostgreSQL, các hệ thống khác có thể cần biết thay đổi đó để cập nhật search index, cache, data warehouse, hệ thống thanh toán, báo cáo hoặc dịch vụ nghiệp vụ. **Change Data Capture (CDC)** giúp truyền những thay đổi đã commit tới các hệ thống nhận. **Event-driven integration** truyền các sự kiện có ý nghĩa nghiệp vụ để những hệ thống khác phản ứng với chúng.

Việc đọc được thay đổi từ PostgreSQL mới chỉ là một nửa bài toán. Hệ thống nhận còn phải xử lý đúng khi message bị gửi lại, consumer crash, network timeout, event đến sai thứ tự, schema thay đổi hoặc một transaction nguồn tạo ra nhiều event. Một thiết kế tốt phải xác định rõ event identity, ordering, delivery semantics, checkpoint, retry, deduplication và cách reconcile dữ liệu.

Bài học này tập trung vào hai lớp tích hợp:

- **CDC mức dữ liệu:** phát hiện thay đổi row-level từ PostgreSQL WAL/logical decoding và chuyển thành change records.
- **Sự kiện nghiệp vụ:** phát ra event mô tả điều đã xảy ra trong nghiệp vụ, thường qua transactional outbox để bảo đảm event và thay đổi dữ liệu được commit cùng nhau.

Phía nhận cần thiết kế để có thể nhận lại một event mà không nhân đôi tác động. Trong mô hình phổ biến, consumer ghi nhận event ID và áp dụng hiệu ứng nghiệp vụ trong cùng một transaction; chỉ checkpoint/acknowledge sau khi transaction đó commit. Đây là nền tảng thực tế để xử lý at-least-once delivery một cách an toàn.

~~~mermaid
flowchart LR
    A["PostgreSQL transaction"] --> B["WAL"]
    B --> C["Logical decoding / slot"]
    C --> D["CDC connector"]
    D --> E["Event broker"]
    E --> F["Consumer"]
    F --> G["Inbox / dedup"]
    G --> H["Business effect"]
    H --> I["Commit"]
    I --> J["Checkpoint / ACK"]
~~~

Bài học thuộc chương **Tích hợp dữ liệu**, module **Database Engine Relational PostgreSQL**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt CDC row-level với domain/business events.
2. Giải thích vai trò của WAL, logical decoding, output plugin, replication slot và publication.
3. Chuẩn bị PostgreSQL cho logical decoding theo đúng version.
4. Tạo publication và hiểu giới hạn của logical replication.
5. Theo dõi slot, WAL retention, LSN và replication lag.
6. Thiết kế event envelope có ID, source, transaction metadata và schema version.
7. Chọn at-most-once, at-least-once hoặc cơ chế gần exactly-once phù hợp.
8. Thiết kế inbox/idempotency key để chống xử lý trùng.
9. Dùng transactional outbox để gắn business event với transaction nguồn.
10. Xử lý ordering, partitioning, duplicate, retry và dead-letter queue.
11. Commit business effect và consumer checkpoint đúng thứ tự.
12. Bootstrap snapshot và tiếp tục streaming mà không tạo khoảng trống dữ liệu.
13. Reconcile source và sink sau sự cố.
14. Quản lý schema evolution, delete, tombstone và event version.
15. Theo dõi lag, throughput, retry, poison event và WAL growth.
16. Bảo vệ credentials, PII và quyền replication.
17. Xây dựng runbook cho CDC outage, replay và consumer recovery.

## 2. CDC và business events khác nhau thế nào?

CDC và business events có thể cùng bắt đầu từ một transaction PostgreSQL, nhưng mô tả hai góc nhìn khác nhau.

**CDC row-level** mô tả dữ liệu đã thay đổi trong bảng. Ví dụ, một row trong public.orders được INSERT, UPDATE hoặc DELETE. Event thường chứa tên bảng, operation, before/after values, primary key, source position và transaction metadata tùy connector.

**Business event** mô tả điều đã xảy ra trong nghiệp vụ. Ví dụ:

- OrderPlaced.
- PaymentAuthorized.
- ShipmentDispatched.
- CustomerEmailChanged.
- InventoryReserved.

Business event có thể được tạo từ nhiều bảng hoặc nhiều thao tác nội bộ và chỉ phát ra khi một điều kiện nghiệp vụ đã được thỏa mãn.

| Tiêu chí | CDC row-level | Business event |
| --- | --- | --- |
| Ý nghĩa | Row/table đã thay đổi | Một việc nghiệp vụ đã xảy ra |
| Nguồn | WAL/logical decoding hoặc audit/change log | Application transaction/domain logic |
| Payload | Table, operation, before/after | Event type và business facts |
| Coupling | Gắn với schema database | Gắn với contract nghiệp vụ |
| Consumer | Thường cần hiểu schema nguồn | Có thể độc lập với schema nội bộ |
| Dùng cho | Replication, cache, warehouse, search index | Workflow, integration, notification |
| Schema change | Có thể ảnh hưởng trực tiếp consumer | Được quản lý qua event contract |

CDC phù hợp khi hệ thống nhận cần phản chiếu dữ liệu hoặc xây dựng read model. Business event phù hợp khi cần thông báo ý nghĩa nghiệp vụ ổn định qua thời gian.

Không nên phát toàn bộ row changes ra ngoài rồi yêu cầu consumer tự suy luận nghiệp vụ nếu application có thể phát domain event rõ nghĩa hơn.

## 3. Luồng CDC tổng quát

Một pipeline CDC phổ biến có các thành phần:

1. PostgreSQL ghi transaction vào WAL.
2. Logical decoding đọc WAL và chuyển thay đổi thành logical records.
3. Replication slot giữ vị trí cần thiết để consumer có thể tiếp tục.
4. Output plugin định dạng logical changes.
5. Connector lấy changes và chuyển thành message.
6. Broker lưu message theo partition/offset.
7. Consumer đọc message, xác thực và áp dụng hiệu ứng.
8. Consumer ghi checkpoint/offset sau khi xử lý thành công.
9. Monitoring theo dõi lag, retries, slot retention và sink health.

~~~mermaid
flowchart TD
    A["Application COMMIT"] --> B["PostgreSQL WAL"]
    B --> C["Logical decoding"]
    C --> D["Replication slot"]
    D --> E["Connector / output plugin"]
    E --> F["Broker topic"]
    F --> G["Consumer group"]
    G --> H{"Event hợp lệ?"}
    H -->|"Có"| I["Deduplicate + apply"]
    H -->|"Không tạm thời"| J["Retry"]
    H -->|"Poison event"| K["DLQ / quarantine"]
    I --> L["Commit sink transaction"]
    L --> M["Commit offset"]
    J --> G
~~~

Logical decoding phát ra các thay đổi của transaction đã commit theo semantics của output plugin. Consumer vẫn phải xử lý duplicate, retry và sink failures vì connector/broker có thể gửi lại message khi checkpoint chưa được ghi nhận.

## 4. WAL là nền tảng của logical decoding

WAL (Write-Ahead Log) là nhật ký ghi trước của PostgreSQL. Thay đổi dữ liệu được ghi vào WAL trước khi page tương ứng được ghi xuống data files, giúp PostgreSQL phục hồi sau crash và hỗ trợ replication.

Logical decoding đọc WAL và diễn giải thay đổi thành dạng logic như INSERT/UPDATE/DELETE thay vì chỉ truyền physical page changes.

Các khái niệm liên quan:

- **WAL record:** bản ghi mô tả thay đổi vật lý/logical operation cần phục hồi.
- **LSN:** Log Sequence Number, vị trí trong WAL.
- **Commit record:** đánh dấu transaction commit.
- **Logical decoding:** giải mã WAL thành logical changes.
- **Output plugin:** chuyển changes thành protocol/format.
- **Replication slot:** lưu tiến độ và giữ WAL cần thiết cho consumer.
- **Publication:** xác định table/operation được native logical replication publish.

LSN là vị trí kỹ thuật, không phải event ID nghiệp vụ. Một transaction có thể tạo nhiều WAL records và nhiều row changes; connector có thể gắn cùng transaction metadata cho nhiều events.

## 5. Chuẩn bị PostgreSQL cho logical decoding

Để dùng logical decoding, server cần cấu hình phù hợp. Tham số cốt lõi là wal_level.

~~~sql
SHOW wal_level;
SHOW max_replication_slots;
SHOW max_wal_senders;
SHOW max_slot_wal_keep_size;
~~~

Thông thường cần:

- wal_level = logical.
- max_replication_slots đủ cho các slots dự kiến.
- max_wal_senders đủ cho logical/physical replication connections.
- Disk capacity và WAL retention policy phù hợp.
- Network/firewall cho connector.
- Replication role và quyền đọc dữ liệu snapshot nếu connector cần snapshot.

wal_level, max_replication_slots và max_wal_senders là các tham số có yêu cầu restart theo PostgreSQL version. Kiểm tra pg_settings.context và tài liệu của version đang chạy trước khi thay đổi.

Ví dụ xem setting và context:

~~~sql
SELECT
    name,
    setting,
    unit,
    context,
    source,
    pending_restart
FROM pg_settings
WHERE name IN (
    'wal_level',
    'max_replication_slots',
    'max_wal_senders',
    'max_slot_wal_keep_size'
)
ORDER BY name;
~~~

Không tăng max_replication_slots hoặc max_wal_senders vô hạn. Mỗi slot/connection có resource cost và slot bị bỏ quên có thể giữ WAL lâu dài.

## 6. Tạo replication role

Tạo một role riêng cho connector, chỉ cấp quyền cần thiết.

~~~sql
CREATE ROLE cdc_reader
    WITH LOGIN REPLICATION
    NOSUPERUSER
    NOCREATEDB
    NOCREATEROLE;
~~~

Replication role cần được phép kết nối tới database và được cấu hình trong pg_hba.conf. Nếu connector thực hiện initial snapshot, role còn cần SELECT trên các bảng được snapshot và quyền cần thiết để đọc metadata.

Ví dụ:

~~~sql
GRANT CONNECT ON DATABASE sales TO cdc_reader;
GRANT USAGE ON SCHEMA public TO cdc_reader;
GRANT SELECT ON TABLE public.orders TO cdc_reader;
~~~

Với nhiều bảng, cấp quyền theo scope rõ ràng. Có thể dùng default privileges cho objects tương lai nếu policy cho phép, nhưng phải xác định đúng object owner role.

Không cấp SUPERUSER chỉ để connector hoạt động. Một số connector/version có yêu cầu quyền đặc biệt; đối chiếu tài liệu chính thức của connector và PostgreSQL version để cấp đúng role attributes và grants.

Credential phải được lưu trong secret manager, rotate theo policy và không đưa vào migration file, log hoặc event payload.

## 7. Publication trong PostgreSQL

Publication là tập hợp các bảng và thao tác mà native logical replication publish. CDC connector dùng pgoutput có thể sử dụng publication để xác định scope, tùy cách cấu hình connector.

Ví dụ publication cho một bảng:

~~~sql
CREATE PUBLICATION orders_cdc_pub
FOR TABLE public.orders
WITH (publish = 'insert, update, delete');
~~~

Hoặc publication cho nhiều bảng:

~~~sql
CREATE PUBLICATION app_cdc_pub
FOR TABLE public.orders, public.order_items, public.customers;
~~~

Publication có thể cấu hình các thao tác INSERT, UPDATE, DELETE và TRUNCATE theo hỗ trợ của version. Kiểm tra publication:

~~~sql
SELECT
    pubname,
    puballtables,
    pubinsert,
    pubupdate,
    pubdelete,
    pubtruncate
FROM pg_publication
ORDER BY pubname;
~~~

Xem bảng thuộc publication:

~~~sql
SELECT
    p.pubname,
    n.nspname AS schema_name,
    c.relname AS table_name
FROM pg_publication_tables AS p
JOIN pg_namespace AS n
    ON n.nspname = p.schemaname
JOIN pg_class AS c
    ON c.relname = p.tablename
   AND c.relnamespace = n.oid
ORDER BY p.pubname, p.schemaname, p.tablename;
~~~

Publication không phải một event schema hoàn chỉnh. Nó chọn dữ liệu được publish; output plugin/connector quyết định envelope và message format.

### Row filters và column lists

Các phiên bản PostgreSQL mới hỗ trợ publication row filters và column lists cho một số use cases. Cú pháp/giới hạn phụ thuộc major version.

Row filter có thể giảm lượng dữ liệu truyền, nhưng phải hiểu rằng UPDATE/DELETE filtering có semantics riêng và replica identity vẫn cần thiết. Column list giảm trường được publish nhưng có thể khiến consumer thiếu dữ liệu để tái tạo trạng thái hoặc áp dụng logic.

Không coi publication filter là ranh giới bảo mật duy nhất. Kết hợp role privileges, network, connector policy và data classification.

## 8. Replica identity: cách PostgreSQL nhận diện row update/delete

Để logical replication mô tả UPDATE/DELETE, PostgreSQL cần nhận diện row cũ. Replica identity quyết định thông tin định danh được ghi vào WAL cho mục đích logical decoding.

Kiểm tra:

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    c.relreplident AS replica_identity
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'p')
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY n.nspname, c.relname;
~~~

Các giá trị phổ biến:

- d: DEFAULT, thường sử dụng primary key nếu có.
- n: NOTHING, không có replica identity.
- f: FULL, ghi nhận toàn bộ old row image cho update/delete.
- i: USING INDEX, dùng một suitable unique index.

Nếu bảng không có primary key/replica identity phù hợp, UPDATE/DELETE có thể không được publish theo cách mong muốn hoặc replication có thể báo lỗi.

### Dùng FULL

~~~sql
ALTER TABLE public.audit_events REPLICA IDENTITY FULL;
~~~

FULL có thể làm tăng WAL volume và lộ nhiều old values hơn trong CDC payload. Chỉ dùng khi cần và đánh giá tác động storage/network/privacy.

### Dùng index cụ thể

~~~sql
ALTER TABLE public.orders
REPLICA IDENTITY USING INDEX orders_replica_identity_key;
~~~

Index phải đáp ứng yêu cầu của PostgreSQL về unique, non-partial và non-null columns. Kiểm tra tài liệu đúng version trước khi dùng.

## 9. Replication slot và WAL retention

Replication slot giữ trạng thái tiến độ của consumer và ngăn PostgreSQL loại bỏ WAL cần thiết cho consumer chưa đọc. Đây là thành phần quan trọng để không mất change records, nhưng slot bị bỏ quên có thể làm WAL tăng không giới hạn.

Kiểm tra slots:

~~~sql
SELECT
    slot_name,
    plugin,
    slot_type,
    database,
    active,
    active_pid,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_replication_slots
ORDER BY slot_name;
~~~

Một số PostgreSQL version có thêm columns như wal_status, safe_wal_size, invalidation_reason hoặc failover-related metadata. Kiểm tra schema view thực tế trước khi dùng query tự động hóa.

Ý nghĩa chính:

- slot_name: tên slot.
- plugin: output plugin với logical slot.
- slot_type: physical hoặc logical.
- database: database gắn với logical slot.
- active: có consumer đang dùng slot hay không.
- restart_lsn: WAL sớm nhất còn cần giữ.
- confirmed_flush_lsn: vị trí consumer đã xác nhận xử lý/nhận theo protocol.

restart_lsn và confirmed_flush_lsn khác nhau. Khoảng cách giữa chúng phản ánh phần WAL vẫn còn cần giữ do slot/decoding state; không đơn giản bằng số message đang chờ ở broker.

### Ước lượng WAL retention

Trên primary, có thể xem khoảng cách từ current WAL LSN tới restart_lsn:

~~~sql
SELECT
    slot_name,
    active,
    restart_lsn,
    confirmed_flush_lsn,
    CASE
        WHEN restart_lsn IS NULL THEN NULL
        ELSE pg_size_pretty(
            pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)::bigint
        )
    END AS retained_wal_distance
FROM pg_replication_slots
WHERE slot_type = 'logical'
ORDER BY slot_name;
~~~

Đây là khoảng cách LSN, không phải phép đo chính xác số bytes vật lý còn nằm trên filesystem do segment boundaries, shared retention và archive behavior. Đối chiếu filesystem/monitoring metrics.

### Giới hạn WAL giữ bởi slot

max_slot_wal_keep_size có thể giới hạn lượng WAL được giữ cho slot trong các version hỗ trợ. Nếu giới hạn bị vượt, slot có thể mất khả năng tiếp tục vì WAL cần thiết đã bị recycle; consumer phải được xử lý theo recovery plan, có thể cần tạo lại slot và bootstrap/reconcile.

Đừng đặt giới hạn thấp đến mức consumer bình thường thường xuyên mất slot. Đừng để unlimited mà không có alert và capacity planning.

## 10. Logical decoding và output plugins

Logical decoding chuyển WAL thành changes thông qua output plugin.

Plugin built-in phổ biến:

- pgoutput: output plugin được dùng bởi native logical replication và nhiều CDC connectors.
- Các plugin bên ngoài có thể cung cấp JSON, text hoặc binary formats tùy package/version.

Không phải output plugin nào cũng được cài sẵn. Connector có thể quản lý slot và plugin riêng. Không tạo slot thủ công nếu connector được cấu hình tự tạo slot; hai bên có thể tranh quyền sử dụng hoặc tạo slot trùng.

### Tạo logical slot minh họa

~~~sql
SELECT *
FROM pg_create_logical_replication_slot(
    'orders_cdc_slot',
    'pgoutput'
);
~~~

Lệnh trên tạo slot trong database hiện tại. Nó không tự tạo broker, connector hay consumer. Với pgoutput, consumer cần dùng logical replication protocol phù hợp và cung cấp publication/scope theo protocol.

Trong production, thường để connector quản lý slot lifecycle để nó có thể phối hợp snapshot, offsets và restart. Nếu tạo slot thủ công, phải có runbook quản lý ownership, drop/recreate và recovery.

### Liệt kê slot

~~~sql
SELECT
    slot_name,
    plugin,
    database,
    active,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_replication_slots
WHERE slot_type = 'logical';
~~~

Không drop slot đang được connector dùng. Drop slot sẽ làm mất trạng thái decoding progress và có thể khiến WAL được recycle; consumer cần bootstrap/recovery.

## 11. Native logical replication và CDC connector

Hai cách thường gặp:

**Native logical replication:** PostgreSQL publisher phát changes qua publication; PostgreSQL subscriber áp dụng vào bảng tương ứng. Đây là cơ chế database-to-database replication.

**CDC connector:** Connector dùng logical replication protocol/slot để chuyển changes thành event message cho broker hoặc sink khác. Ví dụ kiến trúc phổ biến là Debezium kết hợp Kafka Connect và Kafka, nhưng các connector khác cũng có thể dùng cùng nền tảng PostgreSQL.

| Tiêu chí | Native logical replication | CDC connector |
| --- | --- | --- |
| Sink | PostgreSQL subscriber | Broker, warehouse, search, cache, service |
| Payload | Logical row changes | Connector-defined event envelope |
| Apply | PostgreSQL apply worker | Consumer/application |
| Offset | Subscription/slot state | Connector offsets và slot progress |
| Schema evolution | Schema cần quản lý riêng | Connector schema/history + consumer contract |
| Transform | Hạn chế hơn | Có thể transform/filter/route |
| Delivery handling | PostgreSQL-managed apply | Phải thiết kế sink idempotency/retry |
| Business semantics | Row changes | Có thể map thành domain events |

Native logical replication cũng cần kiểm tra sequence, DDL, large objects và các object không thuộc row replication. CDC connector có thể thêm metadata/formatting nhưng không tự giải quyết business correctness.

## 12. Logical replication không tự replicate mọi thứ

Một số điều không được tự động chuyển qua logical row replication theo cách người dùng thường mong đợi:

- DDL/schema changes.
- Sequence state.
- Roles và grants.
- Large objects trong các mô hình phổ biến.
- Configuration và extension packages.
- External side effects.
- Các bảng không nằm trong publication.

Schema cần được triển khai đồng bộ ở subscriber/consumer trước khi event có schema mới tới. Sequence state phải đồng bộ riêng khi cần cutover. Với business event, application phải chủ động tạo event contract.

Đọc tài liệu version cụ thể và connector docs vì khả năng hỗ trợ có thể mở rộng theo thời gian.

## 13. Thiết kế event envelope

Một event nên có envelope ổn định, tách metadata khỏi payload nghiệp vụ.

Ví dụ JSON:

~~~json
{
  "id": "0192f2d0-7e51-7b6a-9d31-1c5d6b7e8f90",
  "type": "com.example.orders.order-status-changed",
  "version": 2,
  "source": "postgres://sales/public.orders",
  "subject": "orders/ORD-1042",
  "time": "2026-11-14T08:30:00Z",
  "transaction": {
    "id": "tx-88421",
    "commit_lsn": "0/16B6C50",
    "sequence": 3
  },
  "correlation_id": "req-5f42",
  "causation_id": "cmd-9a18",
  "data": {
    "order_id": "ORD-1042",
    "old_status": "paid",
    "new_status": "shipped"
  }
}
~~~

Các trường quan trọng:

- id: định danh duy nhất, ổn định qua retry.
- type: event type có namespace.
- version: phiên bản contract.
- source: hệ thống/bảng/aggregate phát event.
- subject: entity/aggregate liên quan.
- time: thời điểm nghiệp vụ hoặc commit, cần xác định semantics.
- transaction: transaction/LSN/sequence metadata nếu có.
- correlation_id: liên kết workflow/request.
- causation_id: event/command gây ra event hiện tại.
- data: payload.

Đừng dùng LSN làm event ID duy nhất nếu một transaction có nhiều row changes cùng LSN hoặc connector tạo nhiều records cho một commit. Dùng ID riêng ổn định hoặc composite identity có semantics được định nghĩa rõ.

## 14. CDC event envelope và before/after

Một CDC event thường mô tả operation:

- c: create/insert.
- u: update.
- d: delete.
- r: snapshot/read event.

Tên code và shape phụ thuộc connector. Với Debezium, envelope có thể chứa before, after, source metadata, op, timestamp và transaction metadata.

Ví dụ khái niệm:

~~~json
{
  "before": {
    "id": 42,
    "status": "pending"
  },
  "after": {
    "id": 42,
    "status": "paid"
  },
  "source": {
    "schema": "public",
    "table": "orders",
    "lsn": "0/16B6C50"
  },
  "op": "u"
}
~~~

Không coi đây là JSON schema cố định cho mọi connector. Đọc schema thật của connector/version và cấu hình converter/serializer.

### Delete và tombstone

Delete event có thể chứa old key/before image hoặc chỉ key tùy replica identity và connector. Một số broker/connector phát tombstone record (key có value null) để hỗ trợ log compaction. Consumer phải phân biệt delete event nghiệp vụ với tombstone phục vụ broker semantics.

Nếu downstream cần biết các field cũ, phải cấu hình replica identity và kiểm tra connector payload. REPLICA IDENTITY FULL tăng WAL volume và có thể lộ dữ liệu; cân nhắc kỹ.

## 15. Business event và transactional outbox

Một lỗi kinh điển là application commit database rồi mới gửi message:

1. UPDATE orders SET status = 'paid'.
2. COMMIT.
3. Gửi OrderPaid tới broker.

Nếu process crash giữa bước 2 và 3, database đã đổi nhưng event không được gửi. Nếu gửi trước commit, transaction có thể rollback nhưng event đã phát ra.

Transactional outbox giải quyết khoảng trống này bằng cách ghi business data và event record trong cùng một database transaction.

~~~mermaid
flowchart TD
    A["Application command"] --> B["BEGIN"]
    B --> C["Update business tables"]
    C --> D["Insert outbox event"]
    D --> E["COMMIT"]
    E --> F["CDC / outbox relay"]
    F --> G["Broker"]
    G --> H["Consumer"]
~~~

Ví dụ bảng outbox:

~~~sql
CREATE TABLE integration_outbox (
    event_id uuid PRIMARY KEY,
    aggregate_type text NOT NULL,
    aggregate_id text NOT NULL,
    aggregate_version bigint,
    event_type text NOT NULL,
    schema_version integer NOT NULL,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    payload jsonb NOT NULL
);
~~~

Trong cùng transaction:

~~~sql
BEGIN;

UPDATE public.orders
SET status = 'paid',
    updated_at = now()
WHERE order_id = 'ORD-1042';

INSERT INTO integration_outbox (
    event_id,
    aggregate_type,
    aggregate_id,
    aggregate_version,
    event_type,
    schema_version,
    payload
)
VALUES (
    gen_random_uuid(),
    'Order',
    'ORD-1042',
    7,
    'OrderPaid',
    1,
    '{"order_id":"ORD-1042","status":"paid"}'::jsonb
);

COMMIT;
~~~

Nếu transaction rollback, cả business change và outbox row đều rollback. Nếu commit, event tồn tại bền vững để relay/CDC chuyển đi.

Cần bảo đảm UPDATE thực sự tác động đúng một order trước khi insert event; ví dụ trên minh họa pattern, ứng dụng cần kiểm tra affected rows và tạo event dựa trên trạng thái đã xác nhận.

## 16. Outbox relay: polling hay CDC?

Hai cách phổ biến:

### Polling relay

Worker định kỳ đọc các rows chưa gửi, publish rồi đánh dấu trạng thái.

Ưu điểm:
- Dễ hiểu, ít yêu cầu logical decoding.
- Có thể kiểm soát batch và retry trong application.
- Dễ quan sát trạng thái từng event.

Thách thức:
- Cần locking/claiming an toàn khi nhiều workers.
- Publish thành công nhưng đánh dấu chưa gửi có thể gây duplicate.
- Polling tạo query load và cần cleanup.
- Không thể đảm bảo atomic commit giữa PostgreSQL và broker nếu không có distributed transaction.

### CDC relay

Connector đọc outbox table qua logical decoding và phát event.

Ưu điểm:
- Tận dụng WAL/slot.
- Có thể giảm polling query.
- Theo dõi commit order/transaction metadata.
- Phù hợp với pipeline CDC sẵn có.

Thách thức:
- Phải vận hành slot/WAL retention.
- Schema outbox cần ổn định.
- Event cleanup phải theo retention/consumer recovery policy.
- Connector restart có thể phát lại records.
- Cần xử lý snapshot của outbox và event dedup ở consumer.

Dù dùng polling hay CDC, phía nhận vẫn cần idempotency. Không có cơ chế relay phổ biến nào loại bỏ mọi khả năng duplicate ở ranh giới PostgreSQL và broker.

## 17. At-most-once, at-least-once và exactly-once

### At-most-once

Consumer checkpoint/ack trước khi áp dụng hiệu ứng. Nếu process crash sau checkpoint nhưng trước khi effect commit, event có thể bị mất.

Phù hợp khi mất một số cập nhật có thể chấp nhận hoặc dữ liệu có thể được tái tạo dễ dàng.

### At-least-once

Consumer chỉ checkpoint sau khi effect đã commit. Nếu crash sau commit nhưng trước checkpoint, event được gửi lại và có thể xử lý trùng.

Đây là lựa chọn phổ biến vì không bỏ sót event đã nhận, với điều kiện source/connector giữ được dữ liệu và retry đúng.

### Exactly-once

Exactly-once có nghĩa một logical event tạo đúng một hiệu ứng quan sát được ở sink. Điều này cần atomic coordination giữa event offset/checkpoint và business effect, hoặc idempotent sink với deduplication bền vững.

Chỉ bật producer idempotence hoặc broker transaction không tự bảo đảm exactly-once end-to-end nếu consumer còn ghi sang database/service khác.

Trong nhiều hệ thống, mục tiêu thực tế là **at-least-once delivery + idempotent processing**. Kết quả nghiệp vụ quan sát được khi đó tương đương một lần trong phạm vi idempotency key và transaction được thiết kế.

## 18. Consumer inbox và deduplication

Inbox là bảng lưu event ID đã xử lý. Event ID cần ổn định qua retry và duy nhất trong phạm vi được định nghĩa.

Ví dụ:

~~~sql
CREATE TABLE consumer_inbox (
    event_id uuid PRIMARY KEY,
    event_type text NOT NULL,
    payload_hash text,
    received_at timestamptz NOT NULL DEFAULT now()
);
~~~

Consumer xử lý trong một transaction:

~~~sql
BEGIN;

INSERT INTO consumer_inbox (
    event_id,
    event_type,
    payload_hash
)
VALUES (
    '0192f2d0-7e51-7b6a-9d31-1c5d6b7e8f90',
    'OrderPaid',
    'sha256:example'
)
ON CONFLICT (event_id) DO NOTHING
RETURNING event_id;
~~~

Ứng dụng kiểm tra kết quả RETURNING:

- Có row trả về: event mới; áp dụng business effect trong cùng transaction.
- Không có row: event đã được xử lý; bỏ qua effect và commit/no-op.
- Cùng event ID nhưng payload hash khác: đây là integrity/producer bug; quarantine và alert thay vì âm thầm bỏ qua.

Sau khi áp dụng effect:

~~~sql
UPDATE customer_order_summary
SET paid_orders = paid_orders + 1
WHERE customer_id = 42;

COMMIT;
~~~

Đây là ví dụ minh họa. Consumer phải thực hiện insert inbox và business update trên cùng database transaction. Nếu effect được gửi tới external API, inbox transaction không thể tự atomically bao trùm API call; cần outbox/command workflow hoặc idempotency key phía API.

### Vì sao inbox phải commit cùng effect?

Nếu inbox commit trước effect, crash có thể khiến event bị đánh dấu đã xử lý nhưng effect chưa xảy ra. Nếu effect commit trước inbox, crash có thể làm effect chạy lại. Cùng transaction loại bỏ khoảng trống đó khi cả hai ghi trong cùng transactional database.

## 19. Idempotency key cho effect nghiệp vụ

Event ID là một cách deduplicate, nhưng không phải lúc nào cũng đủ. Một business command có thể được phát ra thành nhiều event ID do bug/retry ở producer. Khi đó cần thêm unique business key.

Ví dụ thanh toán:

~~~sql
CREATE TABLE payment_effects (
    payment_id text PRIMARY KEY,
    order_id text NOT NULL,
    applied_at timestamptz NOT NULL DEFAULT now()
);
~~~

Consumer insert payment_id với ON CONFLICT DO NOTHING trước khi áp dụng hiệu ứng. Điều này bảo đảm một payment ID chỉ được áp dụng một lần theo transaction.

Chọn key theo business invariant:

- payment_id cho payment authorization/capture.
- order_id + transition_version cho trạng thái order.
- aggregate_id + aggregate_version cho event stream của aggregate.
- event_id cho dedup từng event.

Không dùng timestamp hoặc random key mới ở mỗi retry làm idempotency key.

## 20. Offset/checkpoint phải commit sau sink effect

Giả sử consumer đọc message từ broker rồi ghi vào PostgreSQL sink:

1. Đọc event và offset.
2. Mở transaction sink.
3. Insert inbox/dedup record.
4. Áp dụng business effect.
5. Commit sink transaction.
6. Commit broker offset/ack.

Nếu process crash ở giữa bước 5 và 6, broker gửi lại event; inbox nhận diện duplicate và consumer không lặp effect.

Nếu commit offset ở bước 2 trước khi sink transaction commit, crash có thể làm mất event effect vĩnh viễn.

### Lưu ý khi xử lý batch

Nếu batch gồm nhiều messages:

- Xác định offset cao nhất đã xử lý liên tục, không chỉ offset lớn nhất đã hoàn tất bất kỳ.
- Không commit offset vượt qua message đang xử lý dở.
- Nếu xử lý song song, cần tracking completion per partition/sequence.
- Có thể commit inbox/effects theo batch transaction, nhưng phải biết giới hạn transaction size và lock.
- Retry một event không được làm bỏ qua event đứng trước nếu ordering yêu cầu.

## 21. Event ordering và transaction boundaries

WAL có thứ tự vật lý, logical decoding có thể giữ transaction/commit ordering theo protocol. Nhưng ordering ở consumer còn phụ thuộc connector, broker partitioning, parallelism và retry.

### Ordering theo aggregate key

Nếu mọi event của cùng order/customer/account được publish vào cùng broker partition theo aggregate ID, consumer có thể xử lý tuần tự trong partition đó.

Ví dụ key:

~~~text
key = aggregate_type + ":" + aggregate_id
~~~

Điều này giữ ordering trong partition, không tạo global ordering giữa tất cả aggregates.

### Aggregate version

Đính kèm version tăng đơn điệu:

~~~json
{
  "aggregate_id": "ORD-1042",
  "aggregate_version": 8,
  "event_type": "OrderShipped"
}
~~~

Consumer có thể phát hiện gap hoặc event cũ:

- version = last + 1: xử lý tiếp.
- version <= last: duplicate/stale, bỏ qua theo policy.
- version > last + 1: thiếu event; buffer/retry/reconcile.

Không giả định mọi CDC row change có aggregate version. Nếu cần version nghiệp vụ, tạo ở application/outbox.

### Transaction gồm nhiều rows

Một transaction PostgreSQL có thể cập nhật nhiều bảng/rows. Connector có thể phát nhiều messages riêng. Nếu consumer cần tính nguyên tử của source transaction, phải dùng transaction metadata và buffering/staging tới khi biết transaction kết thúc, hoặc thiết kế business event ở mức aggregate để không phụ thuộc việc ghép row changes.

Không phân tán các records của cùng transaction sang nhiều partition rồi giả định consumer thấy chúng cùng lúc.

## 22. Retry strategy

Retry phù hợp với lỗi tạm thời:

- Network timeout.
- Broker unavailable.
- Sink database failover.
- Rate limit.
- Temporary dependency outage.
- Serialization service tạm lỗi.

Dùng exponential backoff và jitter:

~~~text
delay = min(max_delay, base_delay * 2^attempt) + random_jitter
~~~

Cần:

- Giới hạn số lần retry hoặc thời gian retry.
- Phân loại retryable/non-retryable errors.
- Giới hạn concurrency.
- Không retry nhanh vô hạn làm tăng tải.
- Giữ event ID và original payload.
- Ghi attempt count và last error.
- Không checkpoint event chưa xử lý nếu semantics yêu cầu không mất.

Lỗi schema/validation cố định thường không tự hết khi retry. Đưa vào quarantine/DLQ để sửa consumer/contract rồi replay.

## 23. Dead-letter queue và poison events

Poison event là event luôn thất bại do payload/schema/logic hoặc dữ liệu đặc biệt.

DLQ/quarantine record nên giữ:

- Original event ID.
- Source topic/partition/offset hoặc source LSN.
- Event type/schema version.
- Payload (được bảo vệ).
- First/last failure timestamp.
- Attempt count.
- Error category/message.
- Consumer version.
- Correlation/causation IDs.
- Replay status.

Không đưa event vào DLQ rồi âm thầm commit offset nếu điều đó làm mất business obligation. Policy phải nói rõ DLQ là trạng thái chờ xử lý có alert và owner.

### Replay

Replay cần:

1. Sửa nguyên nhân.
2. Xác định event còn hợp lệ với current state không.
3. Giữ event ID gốc.
4. Chạy qua cùng idempotency/dedup mechanism.
5. Giữ ordering nếu event phụ thuộc sequence.
6. Ghi replay operator/change ID.
7. Đối chiếu sink sau replay.

Không replay toàn DLQ vào production mà chưa đánh giá duplicate, ordering và event expiry.

## 24. Snapshot bootstrap và tránh gap dữ liệu

CDC thường cần một initial snapshot để consumer có trạng thái ban đầu rồi tiếp tục nhận changes.

Rủi ro lớn nhất là khoảng trống giữa snapshot và streaming:

- Snapshot bắt đầu.
- Một row thay đổi trong lúc copy.
- Connector bắt đầu streaming ở vị trí không nhất quán.
- Consumer bỏ lỡ hoặc áp dụng trùng thay đổi.

Connector đúng chuẩn thường phối hợp consistent snapshot với logical slot/WAL position. Đừng tự chạy SELECT toàn bảng rồi tạo slot sau đó mà không có cơ chế snapshot/LSN coordination.

### Bootstrap strategy

- Chọn snapshot mode của connector.
- Ghi snapshot watermark/LSN.
- Xác định consumer bắt đầu từ snapshot hay streaming.
- Dùng upsert/idempotent sink khi snapshot records có thể gặp lại.
- Reconcile counts/checksums sau bootstrap.
- Chỉ mở downstream reads khi snapshot và stream đã bắt kịp.

### Incremental snapshot

Với bảng lớn, incremental snapshot chia dữ liệu theo chunks trong khi WAL streaming vẫn tiếp tục. Connector cần cơ chế watermark/dedup để xử lý row có thể thay đổi trong lúc snapshot. Kiểm tra đúng connector/version và không tự giả định semantics.

## 25. Reconciliation giữa source và sink

CDC có thể bị gián đoạn, filter sai hoặc consumer logic sai. Reconciliation giúp xác nhận sink phản ánh source.

Các phép đối chiếu:

- Row count theo partition/key range.
- Min/max primary key.
- Max updated_at hoặc source watermark.
- Aggregate totals.
- Hash/checksum theo chunk.
- Missing keys.
- Extra keys.
- Duplicate business keys.
- Version/watermark của aggregate.
- Delete/tombstone coverage.

Nếu source vẫn đang ghi, so sánh cần cùng logical watermark hoặc snapshot nhất quán. So sánh hai thời điểm khác nhau sẽ tạo false mismatch.

### Ví dụ kiểm tra aggregate

~~~sql
SELECT
    count(*) AS order_count,
    sum(total_amount) AS total_amount,
    max(updated_at) AS latest_update
FROM public.orders;
~~~

Chạy logic tương ứng trên sink và lưu thời điểm/watermark. Aggregate match không chứng minh mọi row match; kết hợp chunk checks hoặc key reconciliation cho dữ liệu quan trọng.

## 26. Consumer transaction khi sink là PostgreSQL

Khi consumer ghi vào PostgreSQL sink, pattern phổ biến:

~~~sql
BEGIN;

INSERT INTO consumer_inbox (event_id, event_type)
VALUES ('0192f2d0-7e51-7b6a-9d31-1c5d6b7e8f90', 'OrderPaid')
ON CONFLICT (event_id) DO NOTHING
RETURNING event_id;

-- Chỉ khi INSERT trả về row mới:
-- áp dụng các thay đổi business trong cùng transaction.

COMMIT;
~~~

Ứng dụng phải quyết định effect dựa trên kết quả RETURNING. Nếu event duplicate, transaction có thể kết thúc mà không áp dụng lại effect.

Đảm bảo:

- Inbox có unique constraint.
- Business update và inbox nằm cùng database.
- Error trước COMMIT làm cả hai rollback.
- Consumer chỉ ack sau COMMIT.
- External calls được tách thành outbox/worker riêng.
- Event payload validation xảy ra trước khi ghi effect.

Nếu sink database và broker hỗ trợ transactional integration cụ thể, đọc semantics của connector/framework. Không giả định hai hệ thống tự tạo một distributed transaction.

## 27. Consumer transaction khi sink là external API

Nếu consumer gọi REST API, email provider hoặc payment gateway, không thể dùng transaction PostgreSQL để rollback external side effect.

Cách xử lý:

- Truyền idempotency key tới API nếu API hỗ trợ.
- Lưu command state trong database.
- Dùng outbox để phát command retryable.
- Ghi nhận response/remote reference.
- Reconcile khi timeout vì request có thể đã thành công dù response mất.
- Không gửi lại với key mới.
- Có compensation workflow nếu side effect không thể đảo ngược.

Timeout không có nghĩa API chưa xử lý request. Cần truy vấn trạng thái theo idempotency key hoặc remote reference trước khi retry.

## 28. Schema evolution cho CDC và event consumers

Consumer có thể chạy phiên bản cũ trong khi source thêm column hoặc thay event contract.

Nguyên tắc:

- Thêm field optional trước.
- Consumer bỏ qua field chưa biết nếu contract cho phép.
- Không đổi type/meaning của field hiện có một cách phá vỡ.
- Version event schema rõ ràng.
- Dùng compatibility checks trong CI.
- Có migration cho sink schema.
- Phối hợp rollout producer và consumer.
- Giữ backward/forward compatibility trong thời gian rolling deployment.

### Thêm field

Consumer cũ cần chịu được field mới. Serializer/schema registry phải cấu hình compatibility phù hợp.

### Rename field

Không rename trực tiếp nếu consumer đang đọc field cũ. Dùng giai đoạn dual-field:

1. Producer thêm field mới.
2. Consumer chuyển sang đọc field mới.
3. Theo dõi consumer cũ.
4. Producer ngừng field cũ sau compatibility window.

### Xóa field

Chỉ xóa sau khi không còn consumer dùng field và schema history/retention cho phép.

### Thay đổi type

Type widening có thể vẫn cần kiểm tra serializer và sink mapping. Thay đổi meaning nguy hiểm hơn type change; tạo event type/version mới nếu semantic contract thay đổi.

## 29. Delete events, replica identity và tombstones

DELETE là trường hợp cần thiết kế rõ:

- Key của row bị xóa.
- Có cần before image không?
- Consumer có cần old values để tính compensation không?
- Sink cần xóa record hay đánh dấu deleted?
- Broker có log compaction không?
- Tombstone có ý nghĩa broker-level hay domain-level?

Nếu cần old row values, xác minh replica identity. DEFAULT thường dùng primary key; FULL có thể ghi toàn bộ old row image và làm WAL lớn hơn.

Trong sink, xử lý delete phải idempotent: xóa một row đã bị xóa vẫn nên là no-op hợp lệ. Với downstream aggregate, delete event có thể cần giảm counters/đảo hiệu ứng trong cùng transaction và chống duplicate.

## 30. Truncate và bulk changes

TRUNCATE có semantics khác nhiều DELETE rows. Publication phải bật publish truncate nếu muốn nhận operation đó, và connector cần biểu diễn tương ứng.

Consumer phải biết:

- Truncate toàn table hay partition.
- Có thể áp dụng sink truncate an toàn không.
- Có cần rebuild cache/index không.
- Event có transaction metadata không.
- Consumer nào được phép xử lý operation phá hủy.

Không biến truncate event thành hàng triệu delete events nếu connector không thiết kế như vậy. Ngược lại, không bỏ qua truncate khi sink cần giữ parity.

## 31. Ordering, concurrency và partitioning

Broker thường partition message để mở rộng throughput. Ordering thường chỉ được bảo đảm trong một partition, không phải toàn topic.

Chọn partition key:

- Aggregate ID cho event nghiệp vụ.
- Primary key cho row-level CDC.
- Tenant ID nếu cần giữ thứ tự theo tenant.
- Một key tổng hợp nếu transaction/aggregate có quy tắc ordering cụ thể.

Nếu cùng aggregate bị phân phối nhiều partitions, event có thể đến consumer theo thứ tự khác. Nếu dùng nhiều consumer threads trong cùng partition, cần serialize effect hoặc dùng aggregate version checks.

Không tăng partition count tùy tiện nếu hệ thống phụ thuộc partition mapping/order. Một số broker thay đổi mapping key khi partition count tăng; đánh giá migration strategy trước.

## 32. Backpressure và consumer lag

Khi consumer xử lý chậm hơn producer, lag tăng. Với CDC từ PostgreSQL, lag có thể xuất hiện ở nhiều tầng:

- Slot confirmed_flush_lsn tụt lại.
- Connector queue tăng.
- Broker topic lag tăng.
- Consumer processing backlog tăng.
- Sink write latency tăng.
- DLQ/retry backlog tăng.

Phải đo từng tầng; một metric “lag” duy nhất không chỉ ra nguyên nhân.

### Giảm backpressure

- Tăng consumer concurrency trong giới hạn sink capacity.
- Batch writes hợp lý.
- Dùng bulk upsert khi an toàn.
- Tối ưu indexes ở sink.
- Giảm payload/columns không cần thiết.
- Tách workload theo topic/partition.
- Giới hạn retry storms.
- Scale sink trước khi tăng consumer vô hạn.
- Điều chỉnh connector queue/batch size có kiểm soát.

Nếu connector đọc nhanh nhưng sink chậm, slot có thể đã tiến lên trong khi broker backlog tăng. Khi đó WAL retention và consumer lag là hai vấn đề khác nhau.

## 33. Theo dõi replication slot và lag

Slot inventory:

~~~sql
SELECT
    slot_name,
    slot_type,
    database,
    active,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_replication_slots
ORDER BY slot_name;
~~~

Replication sender state:

~~~sql
SELECT
    application_name,
    client_addr,
    state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    write_lag,
    flush_lag,
    replay_lag
FROM pg_stat_replication
ORDER BY application_name;
~~~

Không phải mọi logical connector đều xuất hiện như một row trong pg_stat_replication tại mọi thời điểm/connection mode. Kiểm tra slot active và connector metrics.

### Cảnh báo nên có

- Slot inactive lâu hơn threshold.
- Restart LSN không tiến triển.
- Retained WAL vượt capacity budget.
- Slot sắp mất WAL theo max_slot_wal_keep_size.
- Connector disconnected/restarting.
- Broker lag tăng liên tục.
- Consumer retry/DLQ tăng.
- Event-to-effect latency vượt SLA.
- Duplicate rate tăng đột biến.
- Reconciliation mismatch.

## 34. Monitoring native logical subscriptions

Với native logical replication subscriber, kiểm tra:

~~~sql
SELECT *
FROM pg_stat_subscription;
~~~

Theo dõi subscription state:

~~~sql
SELECT
    subname,
    subenabled,
    subslotname,
    subpublications
FROM pg_subscription
ORDER BY subname;
~~~

Ngoài ra xem worker processes, logs và replication slot phía publisher. View columns thay đổi theo version; dùng SELECT * để khám phá rồi xây query theo schema thực tế.

Native subscriber có thể cần initial table copy, apply worker và table synchronization workers. Đừng coi subscription enabled là đồng nghĩa toàn bộ tables đã sync xong.

## 35. Event schema registry và contract ownership

Trong hệ thống nhiều producer/consumer, event schema cần được quản lý như API công khai.

Một contract nên xác định:

- Event type và version.
- Required/optional fields.
- Field type/format.
- Nullability.
- Semantics và units.
- Ordering/partition key.
- Delivery guarantees.
- Retention/replay policy.
- PII classification.
- Owner/contact.
- Compatibility rules.

Có thể dùng JSON Schema, Avro, Protobuf hoặc schema registry. Chọn format theo hệ sinh thái và compatibility requirements.

Không chỉ lưu JSON sample trong wiki. Contract phải được version hóa và kiểm tra tự động trong CI.

## 36. CDC filtering và data minimization

Chỉ capture các bảng/columns cần thiết. Truyền toàn bộ database có thể:

- Tăng WAL/connector/broker traffic.
- Làm consumer phức tạp.
- Tăng nguy cơ lộ PII.
- Tạo coupling với internal schema.
- Gây chi phí lưu trữ/replay lớn.

Dùng publication table scope, row filters/column lists khi version hỗ trợ, connector transforms và broker ACLs. Tuy nhiên, transform sau khi connector đã đọc WAL không làm giảm toàn bộ WAL generation ở source.

Nếu event cần dữ liệu nhạy cảm, cân nhắc tokenization/masking ở source hoặc trước broker. Không dựa vào consumer để tự loại bỏ PII sau khi dữ liệu đã lan tới nhiều topic.

## 37. Security cho CDC pipeline

Bảo vệ từng hop:

**PostgreSQL:**
- Role replication riêng.
- HBA giới hạn source addresses.
- TLS và certificate validation.
- Quyền SELECT chỉ trên bảng snapshot cần thiết.
- Publication scope tối thiểu.
- Slot inventory và cleanup policy.

**Connector:**
- Secret manager.
- TLS tới source/broker.
- Không log passwords hoặc payload nhạy cảm.
- Giới hạn plugin/transform.
- Quản lý offsets/config có access control.

**Broker:**
- ACL theo topic/group.
- Encryption in transit/at rest.
- Retention và deletion policy.
- Audit access.
- PII classification.

**Consumer:**
- Least privilege trên sink.
- Validate payload/schema.
- Không tin source metadata nếu chưa xác thực.
- Idempotency và replay controls.
- Audit event processing.

CDC role có thể đọc nhiều dữ liệu hơn role ứng dụng thông thường. Cần review riêng.

## 38. WAL retention và sự cố slot bị mất

Một slot không active vẫn có thể giữ WAL. Nếu connector dừng nhiều giờ/ngày, pg_wal có thể tăng tới mức làm đầy disk.

Khi phát hiện slot giữ WAL:

1. Xác định slot owner/connector.
2. Xác định active/inactive và last progress.
3. Đo retained WAL và disk free.
4. Kiểm tra connector offsets và broker backlog.
5. Khởi động lại connector nếu còn khả năng tiếp tục.
6. Không drop slot chỉ để giải phóng disk trước khi biết consumer recovery path.
7. Nếu slot đã invalid/mất WAL, tạo slot mới theo connector procedure và bootstrap/reconcile.
8. Ghi nhận event gap và chứng minh sink parity trước khi đóng incident.

Nếu phải drop slot, có thể mất khả năng đọc lại phần WAL đã bị recycle. Không có cách tái tạo CDC records từ WAL không còn tồn tại; cần snapshot/reconciliation hoặc restore/archive strategy tùy tình huống.

## 39. Replay và rebuild consumer

Consumer có thể cần replay khi:

- Bug trong consumer đã tạo sai sink state.
- Schema mapping được sửa.
- Sink bị restore về thời điểm cũ.
- DLQ cần được xử lý.
- Consumer offset bị mất hoặc không đáng tin.

Trước replay:

- Chọn start offset/LSN.
- Xác định sink state và idempotency retention.
- Xác định event ordering.
- Kiểm tra external side effects.
- Có snapshot/backup sink.
- Ước lượng replay rate và sink capacity.
- Ghi replay ID và owner.

Nếu replay từ đầu mà inbox table vẫn còn, event duplicates sẽ bị bỏ qua; nhưng nếu sink đã được restore về trạng thái trước khi các inbox records được tạo, dedup state cũng cần khôi phục nhất quán. Inbox và business state nên được backup/restore cùng transaction boundary.

## 40. Event retention và inbox cleanup

Inbox table tăng theo số event đã xử lý. Có thể partition theo received_at hoặc xóa records cũ theo retention policy.

Trước cleanup, xác định:

- Event replay window.
- Broker retention.
- Source slot/rebootstrap strategy.
- Business idempotency horizon.
- External API idempotency retention.
- Legal/audit retention.
- Event ID uniqueness lifetime.

Nếu inbox record bị xóa trước khi event cũ được replay, duplicate effect có thể xảy ra. Giữ dedup state ít nhất bằng replay horizon hoặc dùng business uniqueness constraints lâu dài.

Outbox rows cũng cần cleanup. Chỉ xóa sau khi connector/relay đã xác nhận vượt qua vị trí tương ứng và retention policy cho phép. Với CDC, việc delete outbox rows cũng tạo CDC events; lọc hoặc routing phù hợp để tránh vòng lặp.

## 41. Xử lý transaction có nhiều event

Một transaction nguồn có thể tạo nhiều row-level events. Consumer cần quyết định:

- Có cần thấy mọi event riêng lẻ?
- Có cần áp dụng tất cả hoặc không event nào?
- Có cần transaction boundary?
- Có thể xử lý từng aggregate độc lập không?

Nếu consumer yêu cầu atomicity ở cấp source transaction, cần transaction metadata (transaction ID, event count, order, END marker) từ connector/output format phù hợp. Consumer có thể stage events theo transaction rồi apply sau khi nhận commit boundary.

Cách này tăng latency và memory/storage requirements. Nếu không cần atomicity liên bảng, xử lý theo aggregate/key thường đơn giản và scale tốt hơn.

## 42. Snapshot consistency và initial load

Initial snapshot lớn có thể mất nhiều giờ. Trong thời gian đó source vẫn ghi dữ liệu. Connector cần phối hợp snapshot snapshot point và WAL position để bảo đảm mọi thay đổi đều được phản ánh.

Các câu hỏi cần trả lời:

- Snapshot có consistent point không?
- WAL slot được tạo trước hay trong snapshot workflow?
- Connector giữ exported snapshot bao lâu?
- Có giới hạn transaction age không?
- Consumer có thể nhận snapshot rows trùng với stream updates không?
- Sink dùng upsert/aggregate version để xử lý overlap không?
- Có cách resume snapshot sau crash không?

Không tự xây snapshot bằng SELECT * trên từng table ở các thời điểm khác nhau rồi coi đó là baseline nhất quán. Dùng connector-supported snapshot mode hoặc quy trình export snapshot/slot đã được kiểm chứng.

## 43. Native logical replication: subscriber-side checks

Nếu dùng native PostgreSQL subscription:

~~~sql
CREATE SUBSCRIPTION orders_sub
CONNECTION 'host=<publisher-host> port=5432 dbname=sales user=replication_user'
PUBLICATION orders_cdc_pub
WITH (copy_data = true, create_slot = true, enabled = true);
~~~

Connection string ở đây là placeholder; credential thực tế phải lấy từ secret manager/connection policy. Việc tạo subscription có thể kết nối publisher và tạo slot. Không dùng cùng slot do connector khác quản lý.

Trước khi tạo subscription:

- Tạo schema/table ở subscriber.
- Xác minh owner và types.
- Kiểm tra publication scope.
- Kiểm tra network/TLS/HBA.
- Đảm bảo đủ replication slots/senders.
- Xác định copy_data và initial sync behavior.
- Xác định conflict policy.

Sau khi tạo:

~~~sql
SELECT
    subname,
    pid,
    relid::regclass AS relation_name,
    received_lsn,
    latest_end_lsn,
    latest_end_time
FROM pg_stat_subscription;
~~~

View columns thay đổi theo version. Kiểm tra subscription state và per-table sync state ở catalog phù hợp.

### Subscriber không tự đồng bộ schema

Tạo publication/subscription không tạo đầy đủ schema ở subscriber. Tables phải tồn tại và tương thích. DDL thay đổi ở publisher cần được triển khai riêng ở subscriber trước khi data changes yêu cầu schema mới tới.

## 44. CDC cho partitioned tables

Partitioned table cần xem xét publication behavior và connector metadata:

- Publish qua partition root hay từng leaf.
- Table filter áp dụng ở parent/partition.
- Consumer key/schema naming.
- Partition attach/detach events.
- DDL/partition maintenance không tự được chuyển như row changes.
- Partition routing khi sink cũng partitioned.

PostgreSQL có option publish_via_partition_root ở các version hỗ trợ. Cấu hình này ảnh hưởng relation identity/schema trong logical changes. Kiểm tra behavior đúng version và connector.

Không giả định partition attach/detach sẽ xuất hiện như INSERT/DELETE rows cho CDC consumer.

## 45. Event processing khi sink là search index/cache

Một consumer có thể cập nhật Elasticsearch/OpenSearch, Redis hoặc cache service. Những sink này thường không tham gia transaction PostgreSQL.

Thiết kế:

- Dùng document key ổn định theo aggregate/row primary key.
- Dùng upsert/replace document để idempotent.
- Dùng version/LSN để bỏ stale updates nếu có ordering gaps.
- Delete phải idempotent.
- Retry network failures.
- Rebuild index/cache từ snapshot khi cần.
- Có reconciliation giữa source và sink.
- Không checkpoint trước khi sink xác nhận thành công.

Với cache, có thể chọn invalidate thay vì gửi toàn bộ row state. Invalidation thường giảm coupling nhưng cần xử lý cache repopulation và duplicate invalidations.

## 46. Event processing khi sink là data warehouse

Data warehouse thường nhận append-only CDC logs rồi transform thành current-state tables hoặc history tables.

Cần xác định:

- Raw event retention.
- Dedup key.
- Source commit LSN/transaction ID.
- Late/out-of-order event handling.
- Delete representation.
- Schema evolution.
- Snapshot vs streaming merge.
- Exactly-once merge semantics.
- Reconciliation and backfill.

Với current-state table, dùng MERGE/upsert theo primary key và source version/LSN để tránh event cũ ghi đè state mới. Với history/SCD, giữ event ordering và transaction metadata.

## 47. Observability cho producer, connector, broker và consumer

Theo dõi mỗi tầng:

| Tầng | Metrics/logs quan trọng |
| --- | --- |
| PostgreSQL | WAL generation, slot restart_lsn, confirmed_flush_lsn, retained WAL, active slots |
| Connector | last processed LSN, source lag, queue size, task state, snapshot progress |
| Broker | records in/out, partition lag, under-replicated partitions, produce errors |
| Consumer | processing rate, commit latency, retries, DLQ, duplicate count, sink errors |
| Sink | write latency, connection pool, locks, storage, error rate |
| Business | event-to-effect latency, missing transitions, reconciliation mismatch |

Các timestamp phải đồng bộ theo NTP/clock policy. Độ trễ end-to-end có thể tính từ event/source timestamp tới sink applied_at, nhưng cần phân biệt clock skew và timestamp semantics.

### Alert quan trọng

- Slot inactive kéo dài.
- Retained WAL vượt threshold.
- Connector không tiến LSN.
- Broker lag tăng liên tục.
- Consumer error/retry rate tăng.
- DLQ có event mới.
- Event-to-effect latency vượt SLA.
- Duplicate rate tăng đột biến.
- Reconciliation mismatch.

## 48. Runbook xử lý CDC bị dừng

### Bước 1: Xác định phạm vi

- Database/cluster và publication.
- Slot name và connector.
- Topic/partition.
- Consumer group.
- Sink tables/services.
- Thời điểm event cuối cùng thành công.

### Bước 2: Kiểm tra PostgreSQL

~~~sql
SELECT
    slot_name,
    plugin,
    slot_type,
    database,
    active,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_replication_slots
WHERE slot_type = 'logical';
~~~

Kiểm tra disk, WAL retention, server logs và replication connections.

### Bước 3: Kiểm tra connector/broker

- Task state và error logs.
- Last source LSN.
- Connector queue.
- Broker offsets/lag.
- Serialization/schema errors.
- Credentials/network.

### Bước 4: Kiểm tra consumer/sink

- Last committed offset.
- Last successful event.
- Inbox/dedup records.
- Sink transaction errors.
- DLQ/retry backlog.
- Application version.

### Bước 5: Phục hồi

- Khôi phục connector nếu slot còn hợp lệ.
- Sửa schema/credential/network.
- Replay event theo offset nếu còn trong retention.
- Nếu slot mất WAL, bootstrap/reconcile từ snapshot.
- Chạy sink reconciliation.
- Lưu incident evidence và xác nhận end-to-end latency trở lại ngưỡng.

Không drop/recreate slot chỉ vì connector disconnected. Xác định slot state và WAL availability trước.

## 49. Runbook xử lý duplicate hoặc out-of-order events

1. Lưu event ID, source LSN, transaction metadata, partition/offset và aggregate key.
2. Kiểm tra producer có phát event ID ổn định không.
3. Kiểm tra connector restart/offset commit.
4. Kiểm tra consumer commit ordering.
5. Kiểm tra inbox unique constraint và retention.
6. Kiểm tra partition key/parallel processing.
7. Kiểm tra aggregate version gap/stale event.
8. Xác định business effect đã xảy ra hay chưa.
9. Replay/reconcile theo policy.
10. Sửa producer/consumer và thêm test regression.

Nếu event duplicate nhưng effect idempotent, có thể no-op. Nếu event out-of-order làm state regression, cần version check hoặc per-key sequencing.

## 50. Những sai lầm thường gặp

1. **Coi CDC và business events là một khái niệm**, khiến consumer phụ thuộc trực tiếp vào schema nội bộ.
2. **Gửi message sau database commit mà không outbox**, tạo khoảng trống khi process crash.
3. **Dùng at-most-once nhưng mong không mất event**, checkpoint trước effect có thể làm mất tác động.
4. **Checkpoint trước khi sink commit**, làm event bị mất khi consumer crash.
5. **Commit sink effect nhưng không deduplicate**, tạo duplicate side effects khi event được gửi lại.
6. **Đặt inbox và business effect ở hai transaction khác nhau**, tạo cửa sổ mất hoặc lặp effect.
7. **Dùng event ID mới cho mỗi retry**, làm dedup không hiệu quả.
8. **Coi Kafka transaction là exactly-once cho external database/API**, bỏ qua transaction boundary giữa hệ thống.
9. **Không có replica identity phù hợp**, khiến UPDATE/DELETE không thể được capture đúng.
10. **Dùng REPLICA IDENTITY FULL trên mọi bảng**, tăng WAL và data exposure không cần thiết.
11. **Tạo slot thủ công rồi để connector tạo slot khác**, gây slot dư và WAL retention.
12. **Bỏ quên inactive logical slot**, làm pg_wal tăng và đầy disk.
13. **Drop slot để giải phóng disk mà không đánh giá recovery**, mất khả năng tiếp tục từ vị trí cũ.
14. **Không đồng bộ schema subscriber trước khi publisher thay đổi**, khiến apply worker lỗi.
15. **Giả định logical replication tự replicate DDL, sequence và large objects**, dẫn tới sink thiếu state.
16. **Snapshot và stream không có watermark chung**, tạo gap hoặc duplicate không kiểm soát.
17. **Chỉ kiểm tra broker lag**, bỏ qua slot lag và connector queue.
18. **Retry poison event vô hạn**, tạo retry storm và chặn partition.
19. **Đưa DLQ rồi bỏ quên**, event không được xử lý nhưng hệ thống báo đã nhận.
20. **Replay không giữ event ID gốc**, phá deduplication.
21. **Không giữ ordering theo aggregate**, event cũ ghi đè state mới.
22. **Tăng partition count mà không đánh giá key ordering**, thay đổi phân bố event.
23. **Xóa inbox quá sớm**, event replay cũ có thể tạo duplicate effect.
24. **Xóa outbox rows trước khi relay/connector đã đi qua**, làm mất event.
25. **Không reconcile source và sink**, không phát hiện event gap hoặc consumer bug.
26. **Đưa PII vào event topic không kiểm soát**, làm dữ liệu lan ra nhiều hệ thống.
27. **Không version hóa event schema**, consumer cũ bị lỗi khi producer thay đổi.
28. **Coi slot confirmed_flush_lsn là offset của broker**, nhầm checkpoint giữa hai tầng.
29. **Không có runbook khi slot mất WAL**, dẫn tới downtime kéo dài.
30. **Chỉ test happy path**, bỏ qua crash giữa sink commit và offset commit.

## 51. Bài tập thực hành có đáp án

### Bài 1. CDC là gì?

**Đáp án:** Cơ chế capture các thay đổi dữ liệu đã commit và chuyển chúng tới hệ thống khác để đồng bộ hoặc xử lý.

### Bài 2. CDC row-level khác business event thế nào?

**Đáp án:** CDC mô tả thay đổi row/table; business event mô tả sự kiện có ý nghĩa nghiệp vụ.

### Bài 3. Logical decoding đọc gì?

**Đáp án:** WAL và chuyển thay đổi thành logical records qua output plugin.

### Bài 4. LSN là gì?

**Đáp án:** Log Sequence Number, vị trí trong WAL; không mặc định là event ID nghiệp vụ.

### Bài 5. Replication slot dùng để làm gì?

**Đáp án:** Giữ decoding/replication progress và WAL cần thiết cho consumer.

### Bài 6. Publication có nhiệm vụ gì?

**Đáp án:** Xác định table và operation được native logical replication publish.

### Bài 7. wal_level cần giá trị gì cho logical decoding?

**Đáp án:** logical.

### Bài 8. Vì sao cần role replication riêng?

**Đáp án:** Giới hạn quyền, audit và blast radius cho connector.

### Bài 9. REPLICA IDENTITY DEFAULT thường dùng gì?

**Đáp án:** Primary key nếu có để nhận diện row cũ cho UPDATE/DELETE.

### Bài 10. REPLICA IDENTITY FULL có trade-off gì?

**Đáp án:** Có old row image đầy đủ hơn nhưng tăng WAL volume và exposure dữ liệu.

### Bài 11. Logical replication có tự replicate DDL không?

**Đáp án:** Không mặc định; schema changes cần triển khai riêng.

### Bài 12. Transactional outbox giải quyết vấn đề gì?

**Đáp án:** Ghi business state và event record trong cùng transaction, tránh commit database nhưng mất event.

### Bài 13. At-least-once có thể tạo duplicate không?

**Đáp án:** Có; crash sau sink commit nhưng trước offset commit có thể khiến event được gửi lại.

### Bài 14. Exactly-once end-to-end cần gì?

**Đáp án:** Atomic coordination giữa effect và checkpoint hoặc idempotent sink với deduplication bền vững.

### Bài 15. Inbox pattern làm gì?

**Đáp án:** Lưu event ID đã xử lý và áp dụng business effect trong cùng transaction.

### Bài 16. Khi nào checkpoint offset?

**Đáp án:** Sau khi sink transaction đã commit thành công.

### Bài 17. Event ID có nên thay đổi khi retry không?

**Đáp án:** Không; phải giữ ổn định để deduplicate.

### Bài 18. Vì sao dùng aggregate ID làm partition key?

**Đáp án:** Để giữ thứ tự event trong cùng aggregate trên một partition.

### Bài 19. Ordering trong broker thường được bảo đảm ở phạm vi nào?

**Đáp án:** Thường trong từng partition, không phải global order toàn topic.

### Bài 20. Poison event là gì?

**Đáp án:** Event luôn thất bại do payload/schema/logic và không tự hết lỗi khi retry.

### Bài 21. DLQ cần lưu gì?

**Đáp án:** Event ID, source offset/LSN, payload được bảo vệ, attempts, error và replay status.

### Bài 22. Vì sao không tự tạo snapshot rồi mới tạo slot?

**Đáp án:** Có thể tạo khoảng trống giữa snapshot và WAL stream; cần consistent snapshot/LSN coordination.

### Bài 23. Slot inactive có thể gây gì?

**Đáp án:** Giữ WAL lâu dài và làm filesystem đầy.

### Bài 24. confirmed_flush_lsn có phải broker offset không?

**Đáp án:** Không; đó là tiến độ slot/logical replication phía PostgreSQL.

### Bài 25. Khi slot mất WAL thì sao?

**Đáp án:** Consumer không thể tiếp tục từ vị trí cũ; cần bootstrap/reconcile hoặc recovery theo connector policy.

### Bài 26. Vì sao inbox retention phải phù hợp replay window?

**Đáp án:** Xóa dedup state quá sớm khiến event cũ replay có thể tạo duplicate effects.

### Bài 27. Event schema evolution nên làm thế nào?

**Đáp án:** Version hóa contract, thêm field tương thích trước, triển khai consumer rồi mới loại field cũ.

### Bài 28. Vì sao cần source/sink reconciliation?

**Đáp án:** Phát hiện missing, duplicate, stale hoặc sai dữ liệu sau connector outage/replay.

### Bài 29. CDC event delete có luôn chứa old row không?

**Đáp án:** Không; phụ thuộc replica identity, publication và connector format.

### Bài 30. Một consumer an toàn cần bảo đảm gì?

**Đáp án:** Validate event, deduplicate, apply effect transactionally, checkpoint sau commit, retry/DLQ có kiểm soát và reconciliation.

## 52. Checklist thiết kế và vận hành CDC

### Source PostgreSQL

- [ ] wal_level = logical.
- [ ] max_replication_slots/max_wal_senders đủ.
- [ ] Restart đã được thực hiện nếu setting yêu cầu.
- [ ] Replication role least privilege.
- [ ] HBA/TLS/network được giới hạn.
- [ ] Publication scope đúng.
- [ ] Replica identity phù hợp UPDATE/DELETE.
- [ ] Slot owner và lifecycle rõ.
- [ ] max_slot_wal_keep_size/capacity policy được đánh giá.
- [ ] Alert inactive slots và retained WAL.

### Connector và broker

- [ ] Output plugin/version tương thích.
- [ ] Connector quản lý slot nhất quán.
- [ ] Snapshot mode và watermark rõ.
- [ ] Event envelope/schema version rõ.
- [ ] Topic/partition/key strategy rõ.
- [ ] Broker ACL/retention/encryption đúng.
- [ ] Connector offsets được bảo vệ.
- [ ] Connector lag/task state được monitor.

### Consumer và sink

- [ ] Event ID ổn định.
- [ ] Inbox/unique idempotency key.
- [ ] Inbox và business effect cùng transaction khi có thể.
- [ ] Offset/ACK sau sink commit.
- [ ] Retryable/non-retryable errors được phân loại.
- [ ] Backoff/jitter và retry budget.
- [ ] DLQ/quarantine có owner và replay plan.
- [ ] Ordering theo aggregate được xác định.
- [ ] Schema compatibility được kiểm tra.
- [ ] External side effects có idempotency/compensation.
- [ ] Inbox retention đủ replay horizon.

### Recovery và operations

- [ ] Initial snapshot và streaming không có gap.
- [ ] Source/sink reconciliation có thể chạy.
- [ ] Slot loss/rebootstrap runbook tồn tại.
- [ ] Connector restart/replay runbook tồn tại.
- [ ] WAL disk capacity và alerting hoạt động.
- [ ] Backup/restore của sink và offsets được phối hợp.
- [ ] PII/secret redaction.
- [ ] Event-to-effect latency và DLQ được giám sát.
- [ ] Incident evidence và owner được xác định.
- [ ] Recovery drill đã được thực hiện.

## 53. Tài liệu PostgreSQL chính thức

Đọc tài liệu theo major version đang triển khai:

- [Logical Decoding](https://www.postgresql.org/docs/current/logicaldecoding.html) — kiến trúc và concepts của logical decoding.
- [Logical Decoding Concepts](https://www.postgresql.org/docs/current/logicaldecoding-explanation.html) — slots, snapshots, output plugins và consistency.
- [Logical Decoding Output Plugins](https://www.postgresql.org/docs/current/logicaldecoding-output-plugin.html) — plugin interface.
- [Logical Replication](https://www.postgresql.org/docs/current/logical-replication.html) — publisher, subscriber và replication model.
- [Publications](https://www.postgresql.org/docs/current/logical-replication-publication.html) — publication scope và operations.
- [Subscriptions](https://www.postgresql.org/docs/current/logical-replication-subscription.html) — subscription configuration.
- [Replication Slots](https://www.postgresql.org/docs/current/logicaldecoding-explanation.html#LOGICALDECODING-REPLICATION-SLOTS) — slot behavior và WAL retention.
- [REPLICA IDENTITY](https://www.postgresql.org/docs/current/sql-altertable.html) — cấu hình row identity.
- [WAL Configuration](https://www.postgresql.org/docs/current/runtime-config-wal.html) — wal_level và WAL settings.
- [Replication Configuration](https://www.postgresql.org/docs/current/runtime-config-replication.html) — sender, slots và replication settings.
- [Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html) — pg_stat_replication, pg_replication_slots và monitoring views.
- [CREATE PUBLICATION](https://www.postgresql.org/docs/current/sql-createpublication.html) — tạo publication.
- [CREATE SUBSCRIPTION](https://www.postgresql.org/docs/current/sql-createsubscription.html) — tạo subscription.
- [CREATE ROLE](https://www.postgresql.org/docs/current/sql-createrole.html) — role attributes và replication privilege.
- [CREATE EXTENSION](https://www.postgresql.org/docs/current/sql-createextension.html) — cài extension.
- [WAL Internals](https://www.postgresql.org/docs/current/wal-intro.html) — write-ahead logging.

Connector-specific snapshot, offset, schema history, event envelope và exactly-once semantics phải được kiểm tra trong tài liệu của đúng connector/broker version đang triển khai. PostgreSQL logical decoding bảo đảm source-side decoding semantics; nó không tự bảo đảm consumer side effects được áp dụng đúng một lần.

## 54. Tổng kết

**CDC đưa thay đổi đã commit ra khỏi PostgreSQL; consumer phải biến delivery có thể lặp thành hiệu ứng nghiệp vụ an toàn.** Logical decoding, publication và replication slot xử lý phần source capture. Event contract, inbox/outbox, idempotency, ordering, retry và checkpoint xử lý phần tích hợp.

1. **Phân biệt row-level CDC và business events.** Chọn loại event theo nhu cầu consumer và mức coupling mong muốn.
2. **Logical decoding dựa trên WAL.** wal_level, output plugin, publication và replication slot phải được cấu hình đúng.
3. **Replica identity quyết định khả năng capture UPDATE/DELETE.** FULL tăng WAL và data exposure.
4. **Replication slot giữ WAL cho consumer.** Slot inactive hoặc lag lâu có thể làm đầy disk; phải có capacity và alert.
5. **Logical replication không tự replicate mọi object.** DDL, sequence, roles, grants và large objects cần quy trình riêng.
6. **Transactional outbox gắn business event với database commit.** Không gửi event sau commit mà không có durable outbox.
7. **At-least-once là mô hình phổ biến.** Duplicate phải được xử lý bằng event ID/inbox/idempotency key.
8. **Commit sink effect trước khi checkpoint.** Inbox và business effect nên cùng transaction.
9. **Ordering cần được thiết kế.** Partition theo aggregate key và dùng aggregate version để phát hiện stale/gap.
10. **Retry có backoff; poison event có DLQ và owner.** Replay phải giữ event ID và ordering semantics.
11. **Snapshot cần consistent watermark với WAL stream.** Tránh gap bằng connector-supported snapshot workflow.
12. **Reconcile source và sink.** Kiểm tra counts, keys, aggregates và watermarks sau outage/replay.
13. **Schema event phải được version hóa.** Rollout producer/consumer theo compatibility window.
14. **Monitoring phải theo dõi cả slot, connector, broker, consumer và sink.** Một metric lag không đủ để tìm nguyên nhân.
15. **Bảo vệ event payload và credentials.** CDC có thể mở rộng phạm vi dữ liệu nhạy cảm ra nhiều hệ thống.

Một pipeline CDC đáng tin cậy không chỉ chuyển được record. Nó phải giữ được tiến độ, xử lý duplicate an toàn, phát hiện gap, phục hồi sau outage và chứng minh hệ thống nhận đã áp dụng đúng những thay đổi mà PostgreSQL đã commit.
