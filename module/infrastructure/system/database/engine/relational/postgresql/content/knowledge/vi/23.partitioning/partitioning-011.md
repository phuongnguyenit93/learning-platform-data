# Phân biệt phân vùng, kế thừa bảng và chia dữ liệu nhiều máy

Trong PostgreSQL, **phân vùng bảng** (*partitioning*), **kế thừa bảng** (*table inheritance*) và **chia dữ liệu nhiều máy** (*sharding*) đều có thể làm dữ liệu nằm ở nhiều bảng hoặc nhiều phần. Tuy nhiên, ba cơ chế khác nhau về **ranh giới quản lý, cách định tuyến dữ liệu, tính nhất quán, khả năng tối ưu SQL và chi phí vận hành**.

- **Declarative partitioning** chia một bảng logic thành nhiều partitions thuộc **một PostgreSQL database/cluster**, theo `RANGE</BT>, `LIST</BT> hoặc `HASH</BT>.
- **Table inheritance** cho bảng con kế thừa cột và một số constraints từ bảng cha. Nó không tự động là hệ thống routing dữ liệu theo ngày hoặc tenant.
- **Sharding** phân bố dữ liệu trên **nhiều PostgreSQL servers/clusters** với một tầng router, coordinator hoặc giải pháp phân tán điều phối.

Một hệ thống tạo 1.000 partitions trong một PostgreSQL primary **không có nghĩa có 1.000 máy cùng xử lý ghi**. Ngược lại, nhiều máy chứa những phần dữ liệu khác nhau không tự trở thành declarative partitioned table với một giao dịch và một global unique index.

Bài học thuộc chương **Phân vùng** của module *Database Engine Relational PostgreSQL*. Mục tiêu là hiểu cơ chế từng mô hình, thực hành SQL và chọn kiến trúc dựa trên truy vấn, tải ghi, retention và ràng buộc nghiệp vụ.

## 1. Sơ đồ ba mô hình

~~~text
A. DECLARATIVE PARTITIONING — MỘT CLUSTER

Application
    |
    v
PostgreSQL primary
    |
    orders [PARTITION BY RANGE(order_date)]
       +-- orders_2026_01
       +-- orders_2026_02
       +-- orders_2026_03
       +-- orders_default


B. TABLE INHERITANCE — CHA/CON TRONG MỘT CLUSTER

PostgreSQL
    |
    events_parent [ordinary table, có thể chứa rows]
       +-- events_child_a INHERITS(parent)
       +-- events_child_b INHERITS(parent)

INSERT parent không tự chọn child theo CHECK.


C. SHARDING — NHIỀU CLUSTERS

Application / Router
    |
    +---- PostgreSQL A: tenants nhóm 1
    +---- PostgreSQL B: tenants nhóm 2
    +---- PostgreSQL C: tenants nhóm 3

Router chọn server; có thể cần query nhiều servers.
~~~

### 1.1. Câu hỏi nhận diện

Một thiết kế là partitioning nếu PostgreSQL tự chọn table partition dựa trên **partition bounds**. Nó là table inheritance nếu tồn tại quan hệ `INHERITS` với semantics bảng cha/con, không mặc định có routing. Nó là sharding nếu **phần dữ liệu được đặt trên những servers/clusters độc lập** và có cơ chế quyết định server cần truy cập.

## 2. Bảng so sánh

| Tiêu chí | Declarative partitioning | Table inheritance | Sharding |
|---|---|---|---|
| Tầng chính | Các bảng trong một cluster | Quan hệ cha/con | Nhiều clusters |
| Khai báo | `PARTITION BY</BT>, `PARTITION OF</BT> | `INHERITS</BT> | Router/extension/distributed system |
| Quy tắc phân bố | Partition key và bounds | Không có router built-in | Shard key và shard map |
| INSERT qua cha | Auto-routing | Ghi parent trừ khi tự route | Route tới shard phù hợp |
| SELECT qua cha | Có thể xem mọi partitions | Thường bao gồm descendants | Query một/nhiều shards |
| Loại phần không phù hợp | Partition pruning | Constraint exclusion khi phù hợp | Shard routing |
| Transaction nhiều phần | Một transaction PostgreSQL | Một transaction PostgreSQL | Cần xem distributed guarantees |
| Unique toàn dữ liệu | Giới hạn bởi partition key | Không tự lan toàn children | Không tự global |
| Tăng write primaries | Không | Không | Có thể |
| HA tự động | Không | Không | Không; vẫn cần HA mỗi shard |
| Chi phí chính | Partition count, indexes, DDL | Trigger, constraint và index thủ công | Rebalance, cross-shard JOIN, consistency |

## 3. Phân biệt cluster, database và shard

Một **PostgreSQL database cluster** theo thuật ngữ server truyền thống là tập databases do một server instance/datadir quản lý. Nó không có nghĩa PostgreSQL tự chia write load giữa các machines.

Trong cluster có databases, schemas, tables, indexes và partitions. Một bảng partitioned thường nằm trong **một database**; các leaf partitions có thể được tổ chức trên tablespaces khác nhau, nhưng vẫn do cluster đó quản lý transaction và WAL.

~~~text
Primary server
  Database shop
    Schema sales
      orders (partitioned parent)
      orders_2026_01 (leaf)
      orders_2026_02 (leaf)
~~~

**Tablespace khác không đồng nghĩa shard khác.** Đặt dữ liệu trên hai volumes hoặc hai storage paths vẫn không tự có independent writable primaries.

## 4. Declarative partitioning hoạt động thế nào?

PostgreSQL dùng partition key và bounds để quản lý những tables chứa rows.

~~~sql
CREATE TABLE audit_events (
    event_id BIGINT NOT NULL,
    occurred_on DATE NOT NULL,
    action TEXT NOT NULL
) PARTITION BY RANGE(occurred_on);

CREATE TABLE audit_events_2026_01
PARTITION OF audit_events
FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');

CREATE TABLE audit_events_2026_02
PARTITION OF audit_events
FOR VALUES FROM ('2026-02-01') TO ('2026-03-01');
~~~

Insert qua parent:

~~~sql
INSERT INTO audit_events(event_id, occurred_on, action)
VALUES (1, DATE '2026-02-10', 'login');
~~~

PostgreSQL định tuyến row vào child tháng 02. Parent partitioned table chủ yếu chứa metadata/định nghĩa logic; rows nằm ở leaf partitions.

**Nếu không có partition nào phù hợp và không có DEFAULT partition, INSERT bị lỗi.** PostgreSQL không tự tạo partition mới cho tháng sau.

## 5. RANGE, LIST và HASH

### 5.1. RANGE: chia theo khoảng

~~~sql
CREATE TABLE metrics (
    id BIGINT,
    measured_on DATE NOT NULL
) PARTITION BY RANGE(measured_on);

CREATE TABLE metrics_jan
PARTITION OF metrics
FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');
~~~

Cận dưới bao gồm, cận trên loại trừ:

~~~text
2026-01-01 <= measured_on < 2026-02-01
~~~

RANGE thích hợp dữ liệu theo ngày, tháng, quý hoặc khoảng số.

### 5.2. LIST: tập giá trị rõ ràng

~~~sql
CREATE TABLE regional_jobs (
    id BIGINT,
    region TEXT NOT NULL
) PARTITION BY LIST(region);

CREATE TABLE regional_jobs_north
PARTITION OF regional_jobs
FOR VALUES IN ('north', 'northeast');

CREATE TABLE regional_jobs_south
PARTITION OF regional_jobs
FOR VALUES IN ('south', 'southeast');
~~~

LIST hợp với một số nhóm ổn định, nhưng rất nhiều giá trị phát sinh có thể tăng gánh quản trị partitions.

### 5.3. HASH: phân nhóm bằng hash

~~~sql
CREATE TABLE tenant_messages (
    message_id BIGINT,
    tenant_id INTEGER NOT NULL,
    body TEXT
) PARTITION BY HASH(tenant_id);

CREATE TABLE tenant_messages_p0
PARTITION OF tenant_messages
FOR VALUES WITH (MODULUS 4, REMAINDER 0);

CREATE TABLE tenant_messages_p1
PARTITION OF tenant_messages
FOR VALUES WITH (MODULUS 4, REMAINDER 1);

CREATE TABLE tenant_messages_p2
PARTITION OF tenant_messages
FOR VALUES WITH (MODULUS 4, REMAINDER 2);

CREATE TABLE tenant_messages_p3
PARTITION OF tenant_messages
FOR VALUES WITH (MODULUS 4, REMAINDER 3);
~~~

**Đừng dùng `tenant_id % 4` ở ứng dụng để suy ra chắc chắn partition HASH của PostgreSQL**. Hệ thống dùng phép hash theo implementation tương ứng, không đơn giản modulo raw integer cho mọi dữ liệu.

### 5.4. Chọn theo mục tiêu

| Workload | Hướng nên đánh giá |
|---|---|
| Giữ dữ liệu 18 tháng, xoá tháng cũ | RANGE monthly |
| Vài vùng địa lý cố định | LIST |
| Equality queries theo tenant, phân phối đều | HASH |
| Một tenant chiếm phần lớn dữ liệu | Phải xử lý skew riêng |
| Query theo tenant và ngày | Index phù hợp, có thể subpartition |

## 6. Partition pruning: tại sao có thể nhanh hơn?

**Partition pruning** cho PostgreSQL bỏ qua partitions không thể chứa rows phù hợp predicate.

~~~sql
SELECT *
FROM audit_events
WHERE occurred_on >= DATE '2026-02-01'
  AND occurred_on < DATE '2026-03-01';
~~~

Nếu bảng có 36 partitions tháng, hệ thống có thể chỉ cần quét tháng 02.

~~~text
WHERE ngày trong tháng 02
       |
Partition pruning
       |
Chọn audit_events_2026_02
       |
Seq Scan / Index Scan trên partition đã chọn
~~~

### 6.1. Pruning khác index

- **Pruning**: loại toàn bộ child relations không phù hợp bounds.
- **Index scan**: tìm rows trong một relation còn lại.

Nếu query lọc tenant và ngày, pruning theo ngày và local index theo tenant có thể hỗ trợ nhau.

### 6.2. Không có partition key, pruning bị giới hạn

Nếu partition theo `occurred_on` nhưng query chỉ lọc `tenant_id = 42`, PostgreSQL không thể biết chỉ từ bounds thời gian tháng nào có tenant đó.

### 6.3. Viết predicate thuận lợi

~~~sql
WHERE occurred_on >= DATE '2026-02-01'
  AND occurred_on < DATE '2026-03-01'
~~~

thường dễ hỗ trợ pruning hơn biểu thức bọc cột ngày như `to_char(occurred_on,'YYYY-MM') = '2026-02'`. Kết quả vẫn phụ thuộc planner/phiên bản; xác nhận bằng EXPLAIN.

### 6.4. Pruning ở planning/execution

Một số pruning được thực hiện khi lập kế hoạch; một số ở executor với parameters đã biết. Khi xem EXPLAIN, chú ý `Subplans Removed` hoặc nodes không được thực thi, không chỉ đếm số tên partitions trong phần văn bản.

## 7. Tại sao partitioning không tự scale writes nhiều máy?

~~~text
Một PostgreSQL primary
  +-- 120 monthly/daily partitions
  +-- một bộ WAL/transaction management
  +-- một primary phục vụ writes
~~~

Tách thành nhiều relations có thể giảm chi phí scan, tăng hiệu quả cache/index và giúp maintenance. Nhưng primary server vẫn chịu writes của mọi partitions.

**Partition count không phải server count.** Muốn phân writes qua nhiều independent primaries, cần sharding/distributed architecture hoặc giải pháp tương ứng.

## 8. Table inheritance là tính năng khác

Inheritance dùng `INHERITS`:

~~~sql
CREATE TABLE raw_events (
    event_id BIGINT,
    event_date DATE NOT NULL,
    content TEXT
);

CREATE TABLE raw_events_2026 (
    CHECK (
        event_date >= DATE '2026-01-01'
        AND event_date < DATE '2027-01-01'
    )
) INHERITS(raw_events);
~~~

Child thừa hưởng cột, một số `NOT NULL</BT> và CHECK constraints theo quy tắc PostgreSQL. Nhưng parent **là bảng thường, có thể chứa rows trực tiếp**.

### 8.1. SELECT parent đọc descendants

~~~sql
SELECT * FROM raw_events;
~~~

Thông thường SELECT từ parent bao gồm rows của child tables.

### 8.2. ONLY chỉ đọc parent

~~~sql
SELECT * FROM ONLY raw_events;
~~~

Bỏ descendants.

### 8.3. INSERT parent không tự chọn child

~~~sql
INSERT INTO raw_events(event_id, event_date, content)
VALUES (1, DATE '2026-02-01', 'parent row');
~~~

Hàng này vẫn ghi vào **parent**, dù hợp CHECK của child năm 2026.

### 8.4. Parent có PK/UNIQUE không đồng nghĩa toàn cây

PRIMARY KEY, UNIQUE indexes, foreign keys và indexes ở parent legacy inheritance **không tự** mở rộng thành constraints/indexes toàn bộ descendants theo cách người dùng thường nghĩ.

### 8.5. Check constraint không phải router

CHECK chỉ chặn dữ liệu không hợp lệ trong child mà đang INSERT vào; nó không chọn child giúp một INSERT nhắm parent.

## 9. Inheritance-based partitioning truyền thống

Trước khi declarative partitioning phổ biến, một thiết kế thường gồm:

1. Ordinary parent.
2. Nhiều child `INHERITS</BT>.
3. CHECK constraints theo ngày.
4. Trigger/rule định tuyến INSERT.
5. Constraint exclusion giúp planner loại child không phù hợp.
6. Script tạo child/indexes cho tháng mới.

~~~sql
CREATE TABLE raw_events_jan (
    CHECK (
        event_date >= DATE '2026-01-01'
        AND event_date < DATE '2026-02-01'
    )
) INHERITS(raw_events);
~~~

### 9.1. Constraint exclusion

Planner có thể dùng CHECK của child và WHERE của query để kết luận một child chắc chắn không chứa rows phù hợp, từ đó bỏ qua child đó ở plan.

### 9.2. Khác partition pruning

Declarative partition pruning dựa trên partition bounds có metadata chuyên dụng; constraint exclusion dựa trên CHECK constraints và các quy tắc chứng minh ở planning time. Chúng không phải cùng một cơ chế, dù cùng mục tiêu tránh scan dữ liệu không liên quan.

### 9.3. Nguy cơ của cách thủ công

- CHECK ranges có thể chồng nhau hoặc bị thiếu.
- Router trigger có thể sai.
- INSERT parent có thể giữ hàng sai nơi.
- Index và constraint có thể không đồng bộ trên mọi child.
- Unique/PK/FK xuyên children khó bảo đảm.
- Schema migration phải xử lý toàn hierarchy.

Nếu use case là RANGE/LIST/HASH tiêu chuẩn trên PostgreSQL hiện đại, declarative partitioning thường là điểm bắt đầu tốt hơn.

## 10. Partition và inheritance xuất hiện chung trong catalog

Declarative partition hierarchy vẫn liên quan metadata parent-child như `pg_inherits`. Nhưng điều đó **không làm hai cơ chế tương đương**.

| Catalog/thuộc tính | Gợi ý sử dụng |
|---|---|
| `pg_class.relkind='p'` | Partitioned parent |
| `pg_class.relispartition` | Relation là declarative partition |
| `pg_partitioned_table` | Partitioning strategy và key |
| `pg_inherits` | Quan hệ parent-child của inheritance/partitioning |
| `pg_get_partkeydef` | Đọc partition key |
| `pg_partition_tree` | Duyệt partition hierarchy trên phiên bản hỗ trợ |

Một truy vấn `pg_inherits` đơn độc không đủ để nói tất cả descendants đều có automatic routing kiểu declarative.

## 11. Lab 1: tạo RANGE partitions thực tế

Dùng **database thử nghiệm**. Nếu schema `partition_lab` đã tồn tại, tạo database/schema mới hoặc đổi tên thay vì DROP dữ liệu không thuộc lab.

~~~sql
CREATE SCHEMA partition_lab;

CREATE TABLE partition_lab.order_events (
    event_id BIGINT NOT NULL,
    occurred_on DATE NOT NULL,
    tenant_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    amount NUMERIC(12,2) NOT NULL CHECK (amount >= 0),
    PRIMARY KEY(event_id, occurred_on)
) PARTITION BY RANGE(occurred_on);

CREATE TABLE partition_lab.order_events_2026_01
PARTITION OF partition_lab.order_events
FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');

CREATE TABLE partition_lab.order_events_2026_02
PARTITION OF partition_lab.order_events
FOR VALUES FROM ('2026-02-01') TO ('2026-03-01');

CREATE TABLE partition_lab.order_events_2026_03
PARTITION OF partition_lab.order_events
FOR VALUES FROM ('2026-03-01') TO ('2026-04-01');

CREATE TABLE partition_lab.order_events_default
PARTITION OF partition_lab.order_events DEFAULT;
~~~

### 11.1. Nạp qua parent

~~~sql
INSERT INTO partition_lab.order_events(
    event_id, occurred_on, tenant_id, event_type, amount
)
VALUES
    (101, DATE '2026-01-15', 10, 'created', 120),
    (102, DATE '2026-01-20', 10, 'paid',    120),
    (103, DATE '2026-02-02', 20, 'created', 300),
    (104, DATE '2026-02-18', 10, 'paid',    300),
    (105, DATE '2026-03-05', 30, 'created',  75),
    (106, DATE '2026-04-01', 10, 'created',  44);
~~~

### 11.2. Xem nơi lưu dữ liệu

~~~sql
SELECT
    tableoid::regclass AS physical_partition,
    event_id,
    occurred_on,
    tenant_id,
    amount
FROM partition_lab.order_events
ORDER BY event_id;
~~~

Các rows tháng 01 vào `order_events_2026_01`; tháng 02 vào `order_events_2026_02`; tháng 03 vào tháng 03; row ngày 01/04 vào default partition.

### 11.3. Truy vấn parent

~~~sql
SELECT event_id, tenant_id, amount
FROM partition_lab.order_events
WHERE occurred_on >= DATE '2026-02-01'
  AND occurred_on < DATE '2026-03-01';
~~~

Ứng dụng vẫn dùng một tên bảng logic. PostgreSQL dựa trên bounds để chọn leaf relations.

## 12. Lab 2: EXPLAIN partition pruning

~~~sql
ANALYZE partition_lab.order_events;

EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM partition_lab.order_events
WHERE occurred_on >= DATE '2026-02-01'
  AND occurred_on < DATE '2026-03-01';
~~~

Kiểm tra plan có loại được partitions tháng 01, 03 và default không.

### 12.1. So sánh query không có partition key

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM partition_lab.order_events
WHERE tenant_id = 10;
~~~

Query có thể phải truy cập nhiều partitions vì mọi tháng đều có khả năng chứa tenant 10.

### 12.2. Index và pruning bổ trợ

~~~sql
CREATE INDEX order_events_tenant_date_idx
ON partition_lab.order_events(tenant_id, occurred_on);

EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM partition_lab.order_events
WHERE tenant_id = 10
  AND occurred_on >= DATE '2026-01-01'
  AND occurred_on < DATE '2026-03-01';
~~~

Parent index definition quản lý child indexes. Bảng lab rất nhỏ nên Seq Scan vẫn có thể rẻ hơn; không nhất thiết thấy Index Scan.

### 12.3. EXPLAIN ANALYZE thực thi query

Đối với SELECT trong lab điều đó an toàn. Nhưng `EXPLAIN ANALYZE INSERT/UPDATE/DELETE` thực sự chạy DML, nên cần môi trường thử nghiệm hoặc transaction có rollback.

## 13. Lab 3: HASH partitioning theo tenant

~~~sql
CREATE TABLE partition_lab.tenant_messages (
    message_id BIGINT NOT NULL,
    tenant_id INTEGER NOT NULL,
    body TEXT,
    PRIMARY KEY(message_id, tenant_id)
) PARTITION BY HASH(tenant_id);

CREATE TABLE partition_lab.tenant_messages_p0
PARTITION OF partition_lab.tenant_messages
FOR VALUES WITH (MODULUS 4, REMAINDER 0);

CREATE TABLE partition_lab.tenant_messages_p1
PARTITION OF partition_lab.tenant_messages
FOR VALUES WITH (MODULUS 4, REMAINDER 1);

CREATE TABLE partition_lab.tenant_messages_p2
PARTITION OF partition_lab.tenant_messages
FOR VALUES WITH (MODULUS 4, REMAINDER 2);

CREATE TABLE partition_lab.tenant_messages_p3
PARTITION OF partition_lab.tenant_messages
FOR VALUES WITH (MODULUS 4, REMAINDER 3);
~~~

Nạp và xem phân phối:

~~~sql
INSERT INTO partition_lab.tenant_messages(
    message_id, tenant_id, body
)
SELECT n, (n % 20) + 1, 'message-' || n::text
FROM generate_series(1,100) AS gs(n);

SELECT tableoid::regclass AS physical_partition,
       COUNT(*) AS number_of_rows
FROM partition_lab.tenant_messages
GROUP BY tableoid
ORDER BY physical_partition;
~~~

Đây vẫn là một PostgreSQL database. HASH partitions không tự biến thành nhiều máy.

## 14. Lab 4: chứng minh inheritance khác partitioning

~~~sql
CREATE SCHEMA inheritance_lab;

CREATE TABLE inheritance_lab.events(
    event_id BIGINT,
    occurred_on DATE NOT NULL,
    action TEXT NOT NULL
);

CREATE TABLE inheritance_lab.events_jan (
    CHECK (
        occurred_on >= DATE '2026-01-01'
        AND occurred_on < DATE '2026-02-01'
    )
) INHERITS(inheritance_lab.events);

CREATE TABLE inheritance_lab.events_feb (
    CHECK (
        occurred_on >= DATE '2026-02-01'
        AND occurred_on < DATE '2026-03-01'
    )
) INHERITS(inheritance_lab.events);
~~~

### 14.1. INSERT parent

~~~sql
INSERT INTO inheritance_lab.events(event_id, occurred_on, action)
VALUES (1, DATE '2026-01-10', 'parent');
~~~

Hàng ghi vào parent.

### 14.2. INSERT child

~~~sql
INSERT INTO inheritance_lab.events_jan(event_id, occurred_on, action)
VALUES (2, DATE '2026-01-11', 'child');

INSERT INTO inheritance_lab.events_feb(event_id, occurred_on, action)
VALUES (3, DATE '2026-02-03', 'child');
~~~

### 14.3. SELECT không ONLY

~~~sql
SELECT tableoid::regclass, event_id, occurred_on
FROM inheritance_lab.events
ORDER BY event_id;
~~~

Trả rows của parent và children.

### 14.4. SELECT ONLY

~~~sql
SELECT *
FROM ONLY inheritance_lab.events;
~~~

Chỉ trả row nằm trực tiếp ở parent. Đây là khác biệt quan trọng khi bảo trì inheritance hierarchy.

## 15. PRIMARY KEY và UNIQUE trong declarative partitioning

Một giới hạn thiết kế quan trọng: PostgreSQL thông thường **không có global unique B-tree index vật lý duy nhất** bao trùm mọi leaf partitions trong một partitioned table.

Nếu các partitions được chia theo ngày, hai child indexes trên event_id có thể mỗi cái cho phép event_id=777 mà không biết child còn lại cũng có 777.

### 15.1. Vì sao PK phải bao gồm partition key?

Với partition key `occurred_on`, một PK hợp lệ phổ biến là:

~~~sql
PRIMARY KEY(event_id, occurred_on)
~~~

Vì những rows có cùng cặp giá trị bắt buộc thuộc cùng partition hợp lệ, local unique index có thể kiểm tra trùng.

### 15.2. Ví dụ thường không hợp lệ

~~~sql
CREATE TABLE invalid_events (
    event_id BIGINT PRIMARY KEY,
    occurred_on DATE NOT NULL
) PARTITION BY RANGE(occurred_on);
~~~

Đây là ví dụ **cố ý minh họa hạn chế**: parent partitioned theo occurred_on không thể mặc định bảo vệ uniqueness chỉ trên event_id bằng global index vô hình.

### 15.3. Nếu event_id phải unique toàn cluster?

Có thể cân nhắc:

- Khóa tổ hợp và sửa tham chiếu của ứng dụng.
- Chọn partition key phù hợp hơn với PK.
- Registry table không partitioned giữ global IDs với transaction protocol.
- Giữ dữ liệu không partitioned nếu invariant quan trọng hơn lợi ích.
- Cơ chế ID generation kết hợp kiểm soát uniqueness; không coi UUID/sequence tự thay constraint.

### 15.4. Inheritance còn hạn chế khác

PRIMARY KEY ở ordinary parent inheritance không tự enforce uniqueness toàn children; phải thiết kế integrity độc lập.

## 16. FOREIGN KEY, CHECK và row movement

### 16.1. Foreign keys

PostgreSQL hiện đại hỗ trợ foreign keys liên quan partitioned tables trong các giới hạn phiên bản/cấu trúc phù hợp.

Ví dụ bảng tham chiếu composite PK của lab:

~~~sql
CREATE TABLE partition_lab.event_notes (
    note_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_id BIGINT NOT NULL,
    occurred_on DATE NOT NULL,
    note TEXT NOT NULL,
    FOREIGN KEY (event_id, occurred_on)
        REFERENCES partition_lab.order_events(event_id, occurred_on)
);
~~~

Không nên dùng thông tin cũ “partitioned table không hỗ trợ FK” như chân lý bất biến. Tuy nhiên, FK của ordinary inheritance parent không tự có semantics bao phủ mọi descendants như nhiều ứng dụng kỳ vọng.

### 16.2. UPDATE partition key

~~~sql
UPDATE partition_lab.order_events
SET occurred_on = DATE '2026-02-11'
WHERE event_id = 101
  AND occurred_on = DATE '2026-01-15';
~~~

Các phiên bản PostgreSQL hiện đại có thể di chuyển row sang partition khác theo key mới. Điều đó liên quan logic delete/insert giữa leafs, constraints, triggers và concurrency.

### 16.3. ON CONFLICT có giới hạn

Những trường hợp `INSERT ... ON CONFLICT DO UPDATE` muốn thay partition key để move row có giới hạn theo PostgreSQL version. Không mặc định UPSERT hỗ trợ mọi row movement như UPDATE thông thường; test trên server thật.

### 16.4. Một WHERE không có partition key

~~~sql
UPDATE partition_lab.order_events
SET amount = amount + 1
WHERE tenant_id = 10;
~~~

Có thể phải xem nhiều partitions. Partitioning không tự làm mọi câu DML nhẹ hơn.

## 17. Retention: DROP/DETACH khác DELETE

Dữ liệu theo tháng thường có chính sách giữ 18–24 tháng.

Một bảng không partitioned muốn xóa hàng trăm triệu rows cũ có thể phải DELETE nhiều batches, ghi WAL, tạo dead tuples và cần VACUUM/index cleanup.

Với RANGE partitions, có thể quản lý **nguyên một table** đại diện một tháng.

### 17.1. DETACH PARTITION

~~~sql
ALTER TABLE partition_lab.order_events
DETACH PARTITION partition_lab.order_events_2026_01;
~~~

Sau detach, child còn là một table độc lập, không được SELECT qua parent. Chỉ chạy ví dụ này **sau các bài lab cần tháng 01**.

### 17.2. ATTACH PARTITION

~~~sql
ALTER TABLE partition_lab.order_events
ATTACH PARTITION partition_lab.order_events_2026_01
FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');
~~~

Chỉ chạy nếu child đã detach, schema/constraints/bounds phù hợp và parent chưa có partition trùng khoảng.

### 17.3. ATTACH có thể quét dữ liệu

PostgreSQL có thể cần validate rows thuộc bounds. CHECK constraint phù hợp có thể tránh một số validation scans. Nếu có DEFAULT partition, thêm bound mới có thể yêu cầu kiểm tra default để đảm bảo không có rows thuộc khoảng vừa bổ sung.

### 17.4. DETACH CONCURRENTLY

Một số phiên bản hỗ trợ `DETACH PARTITION ... CONCURRENTLY` với hạn chế về transaction block, default partition và lock semantics. Không thêm CONCURRENTLY tùy ý cho migration tool.

### 17.5. DROP không tự archive

Nếu phải lưu dữ liệu để tuân thủ, hãy export/backup/verify trước khi drop; DDL không thay quy trình retention và backup.

## 18. Index, VACUUM và ANALYZE theo partitions

Leaf partition là relation vật lý có local indexes, statistics và storage riêng.

### 18.1. Parent index vs local indexes

~~~sql
CREATE INDEX order_events_amount_idx
ON partition_lab.order_events(amount);
~~~

Definition ở parent được quản lý qua indexes ở leaf partitions theo cơ chế PostgreSQL. Đây không phải global index duy nhất.

### 18.2. Maintenance lợi ích

Có thể VACUUM/REINDEX/ANALYZE một leaf nóng hoặc archive một leaf lạnh, phù hợp hạn chế locks/chi phí theo workload.

### 18.3. Thống kê của parent

~~~sql
ANALYZE partition_lab.order_events;
~~~

Autovacuum/autoanalyze có xử lý leaf relations nhưng thống kê inherited ở parent có thể không tự được cập nhật đúng thời điểm chỉ vì children thay đổi. Với workload phụ thuộc stats hierarchy, cần kế hoạch ANALYZE parent phù hợp.

### 18.4. Quá nhiều partitions có thể chậm hơn

Mỗi partition tạo thêm relations/indexes/catalog entries. Query planning, relcache, locks, autovacuum scheduling và DDL management đều có overhead. Không đặt tiêu chuẩn “mỗi 100 rows một partition”.

## 19. Subpartitioning nhiều tầng

Ví dụ:

~~~text
orders PARTITION BY RANGE(order_date)
  orders_2026_01 PARTITION BY HASH(tenant_id)
     orders_2026_01_p0
     orders_2026_01_p1
     orders_2026_01_p2
     orders_2026_01_p3
  orders_2026_02 PARTITION BY HASH(tenant_id)
     orders_2026_02_p0
     orders_2026_02_p1
     orders_2026_02_p2
     orders_2026_02_p3
~~~

Hai tầng có thể phù hợp với queries luôn lọc cả tenant/date và yêu cầu retention monthly.

Tuy nhiên:

\[
36\ \text{tháng}\times 32\ \text{buckets}=1{,}152\ \text{leaf partitions}
\]

Chưa tính indexes. Subpartitioning vẫn do **một cluster** quản lý nếu không có tầng distributed sharding.

## 20. Sharding là gì và router hoạt động ra sao?

Sharding đặt các tập rows khác nhau trên nhiều PostgreSQL servers. Một request cần biết **shard key** hoặc hỏi một metadata directory.

~~~text
tenant_id=1450
     |
     v
Router / shard map
     |
     v
PostgreSQL B
     |
     v
orders WHERE tenant_id=1450
~~~

### 20.1. Query có shard key

Có thể định tuyến thẳng tới một shard, tránh fanout.

### 20.2. Query không có shard key

Có thể phải gửi tới A, B, C rồi tổng hợp. Đây là **scatter-gather**; network và partial failures trở thành một phần của query execution.

### 20.3. Shard key quyết định locality

Shard theo `tenant_id` có thể giữ orders, customers và items cùng tenant gần nhau, giúp JOIN và transaction local. Shard theo `order_id` có thể hợp với lookup theo order nhưng làm analytics của một tenant phức tạp hơn.

### 20.4. Shard key không phải partition key

Partition key chọn **table trong cluster**; shard key chọn **server/cluster**. Có thể sử dụng hai khóa khác nhau trong một hệ thống.

## 21. Các kiểu sharding

### 21.1. Range sharding

~~~text
tenants 1-1000      -> A
tenants 1001-2000   -> B
tenants 2001-3000   -> C
~~~

Dễ hiểu, nhưng tenants lớn và vùng ID tăng nhanh có thể khiến phân tải không đều.

### 21.2. Hash sharding

~~~text
stable_hash(tenant_id) -> bucket
bucket -> shard
~~~

Có thể cân tải tương đối đều nếu keys cân bằng, nhưng thay số physical shards cần kế hoạch mapping/rebalance.

### 21.3. Virtual buckets

Thay vì hash trực tiếp theo N machines, tạo nhiều logical buckets rồi ánh xạ buckets sang machines. Khi thêm máy, chuyển subsets buckets.

### 21.4. Directory-based

~~~text
tenant_id | shard_id
42        | A
1450      | B
3001      | C
~~~

Cho phép di chuyển tenants riêng lẻ, nhưng directory phải được đồng bộ và ứng dụng phải xử lý cache stale/cutover.

### 21.5. Geographic

Shard theo region phục vụ latency/data residency. Chi phí cross-region network, failover và compliance cần được thiết kế riêng.

## 22. Sharding khác replication

**Replication** sao chép dữ liệu, còn sharding chia dữ liệu khác nhau.

~~~text
REPLICATION
Primary A (toàn bộ dữ liệu)
   +-- Standby A1 (bản sao)
   +-- Standby A2 (bản sao)

SHARDING
Primary A (tenants 1..1000)
Primary B (tenants 1001..2000)
Primary C (tenants 2001..3000)
~~~

Read replicas có thể tăng khả năng đọc và HA, không tự tăng số writable primary servers cho cùng dữ liệu.

Có thể kết hợp:

~~~text
Shard A primary -> A standby
Shard B primary -> B standby
Shard C primary -> C standby
~~~

Mỗi shard có replication riêng. High availability vẫn cần failover, recovery và monitoring.

## 23. postgres_fdw và distributed extensions

PostgreSQL có `postgres_fdw` để truy vấn foreign tables trên remote PostgreSQL.

~~~text
PostgreSQL A
   -> postgres_fdw
   -> PostgreSQL B (remote table)
~~~

### 23.1. FDW có thể giúp

Đọc/ghi foreign table theo cấu hình, pushdown những filters/joins/aggregates trong điều kiện hỗ trợ và cho phép query kết hợp local/remote data.

### 23.2. FDW không tự là giải pháp sharding hoàn chỉnh

Nó không tự giải quyết shard routing, rebalance, global uniqueness, global FKs, cross-server ACID, HA và coordinated backups.

### 23.3. Transaction nhiều servers

Không suy luận các statements trên nhiều foreign servers luôn thuộc một global atomic distributed two-phase commit chỉ vì client có một câu BEGIN. Phải xem semantics cụ thể và xử lý partial failure.

### 23.4. Distributed PostgreSQL solutions

Một số extensions/products bổ sung coordinator, distributed tables, worker placements và query routing. Nhưng độ tương thích SQL, foreign keys, JOINs, transaction guarantees, index behavior và failover khác nhau theo sản phẩm/phiên bản. Không gom tất cả vào một bảo đảm chung.

## 24. JOIN giữa shards và co-location

Giả sử SQL:

~~~sql
SELECT o.order_id, SUM(i.quantity)
FROM orders AS o
JOIN order_items AS i
  ON i.order_id = o.order_id
WHERE o.tenant_id = 42
GROUP BY o.order_id;
~~~

Nếu orders/items của tenant 42 cùng shard A, JOIN có thể chạy local.

Nếu orders trên A nhưng items trên C, distributed engine có thể phải chuyển rows qua mạng hoặc phân tán JOIN.

### 24.1. Chọn shard key theo transaction boundary

Các bảng thường được JOIN/cập nhật cùng nhau nên ưu tiên co-location khi có thể.

### 24.2. Global analytics

SUM theo toàn hệ có thể chia thành local SUM trên mỗi shard rồi gộp. DISTINCT, window functions, global ORDER BY và một số percentile queries có thể phức tạp hơn đáng kể.

### 24.3. Reference tables

Một số distributed solutions hỗ trợ nhân bản bảng reference nhỏ trên workers; cần kiểm soát cập nhật/consistency của bản sao.

## 25. Transaction trong một cluster và xuyên shards

### 25.1. Partitioning cùng cluster

~~~sql
BEGIN;

UPDATE partition_lab.order_events
SET amount = amount + 1
WHERE event_id = 102
  AND occurred_on = DATE '2026-01-20';

UPDATE partition_lab.order_events
SET amount = amount + 1
WHERE event_id = 103
  AND occurred_on = DATE '2026-02-02';

COMMIT;
~~~

Hai updates ở các partitions khác nhau vẫn thuộc **một PostgreSQL transaction**.

### 25.2. Inheritance cùng cluster

Tương tự, ordinary parent/children cùng database có thể tham gia một transaction, dù routing/constraints khác declarative.

### 25.3. Sharding nhiều primaries

~~~text
Shard A: trừ tài khoản X 100, COMMIT.
Network lỗi.
Shard B: chưa cộng tài khoản Y 100.
~~~

Hai COMMIT độc lập không atomic toàn cục.

### 25.4. Phương án bảo vệ

- Co-locate dữ liệu cần atomic.
- Distributed transaction protocol của solution phù hợp.
- Saga/compensating transactions.
- Transactional outbox và idempotency.
- Ledger và reconciliation.
- Xác định rõ strong/eventual consistency cho từng workflow.

Không dùng kết quả “mỗi query chạy thành công” để kết luận toàn workflow liên máy luôn đúng.

## 26. Global uniqueness và foreign keys khi sharding

### 26.1. Local UNIQUE không phải global UNIQUE

~~~text
Shard A có username='alice'
Shard B có username='alice'

Mỗi server có UNIQUE(username).
Toàn hệ vẫn có hai username trùng.
~~~

### 26.2. Unique theo tenant dễ hơn khi co-locate

Nếu chỉ cần `UNIQUE(tenant_id,username)` và mọi rows một tenant nằm một shard, local unique constraint có thể bảo vệ đúng phạm vi.

### 26.3. Unique toàn hệ

Cần registry/global lookup hoặc distributed uniqueness protocol; dùng UUID không thay unique của username/email/business key.

### 26.4. Cross-shard FK

Một local PostgreSQL foreign key trên A không tự bảo vệ một row được lưu trên B như bảng local trong một transaction. Có thể co-locate data, dùng distributed FK capability phù hợp hoặc application protocol/reconciliation.

### 26.5. Pre-check có race

Kiểm tra customer ở B rồi INSERT order trên A không atomic; customer có thể bị thay đổi/xóa ngay sau pre-check nếu thiếu coordination.

## 27. Hot shards và data skew

Nếu tenant 42 chiếm 80% write traffic và hệ thống hash theo tenant_id:

~~~text
tenant 42 -> chỉ một shard
80% writes -> shard đó
~~~

Hash không tự chia một tenant lớn ra nhiều machines.

### 27.1. Cách xử lý

- Dedicated shard cho tenant lớn.
- Sub-sharding theo order_id/time khi nghiệp vụ cho phép.
- Read replicas/cache cho tải đọc.
- Tách OLTP và analytics.
- Redistribute virtual buckets.
- Giảm hotspot tại một row/index/business key.

### 27.2. Đổi lại chi phí locality

Nếu chia dữ liệu tenant lớn sang nhiều shards, cross-shard JOIN và transaction của tenant đó phức tạp hơn.

### 27.3. Cần đo skew

Theo dõi QPS, WAL bytes/sec, CPU, IOPS, row sizes, replication lag và các hot tenants, không chỉ đếm số shards.

## 28. Rebalancing giữa machines

Thêm shard D vào A/B/C thường cần di chuyển một số tenants/buckets.

### 28.1. Các bước cơ bản

1. Xác định dữ liệu cần chuyển.
2. Copy dữ liệu lịch sử.
3. Theo dõi writes đang phát sinh.
4. Đồng bộ delta changes.
5. Xác minh count/checksum/invariants.
6. Cutover router/shard map.
7. Xử lý in-flight requests.
8. Theo dõi sau cutover.
9. Giữ rollback plan.
10. Xóa source cũ khi an toàn.

### 28.2. Metadata stale

Nếu một ứng dụng vẫn route tenant 42 về A trong khi router khác đã chuyển sang D, có thể xảy ra missing/duplicate writes. Shard map phải có version và quy tắc cutover.

### 28.3. Rebalance không giống ATTACH

ATTACH/DETACH partition là DDL trong cluster. Resharding là **data migration qua mạng**, có partial failures và consistency concerns.

## 29. Backup, HA và replication lag

### 29.1. Backup partitioned cluster

Backup PostgreSQL có thể bao gồm toàn bộ hierarchy; restore phụ thuộc công cụ và phạm vi snapshot.

### 29.2. Backup sharded platform

Nếu shard A backup lúc 10:00, B lúc 10:05, một distributed business workflow tại 10:03 có thể không được khôi phục nhất quán chỉ bằng hai backups đó.

### 29.3. RPO/RTO

Cần recovery objectives cho toàn platform, gồm shard map, các primaries, replicas, backups và reconciliation, không chỉ từng database.

### 29.4. Replica lag

Client ghi vào primary, rồi đọc standby trước khi standby nhận WAL mới có thể thấy dữ liệu cũ. Đây là read consistency/replication issue, không phải partition pruning.

### 29.5. HA theo từng shard

Mất primary của shard B chỉ tác động một phần tenants, nhưng vẫn cần failover/recovery. Nhiều partitions trong một primary không tự tạo HA.

## 30. Quan sát partition hierarchy bằng catalog

### 30.1. pg_partition_tree

~~~sql
SELECT *
FROM pg_partition_tree(
    'partition_lab.order_events'::regclass
);
~~~

### 30.2. Partition key

~~~sql
SELECT pg_get_partkeydef(
    'partition_lab.order_events'::regclass
);
~~~

### 30.3. pg_partitioned_table

~~~sql
SELECT
    partrelid::regclass AS parent,
    partstrat
FROM pg_partitioned_table
WHERE partrelid =
    'partition_lab.order_events'::regclass;
~~~

### 30.4. pg_inherits

~~~sql
SELECT
    inhparent::regclass AS parent,
    inhrelid::regclass AS child
FROM pg_inherits
WHERE inhparent =
    'partition_lab.order_events'::regclass;
~~~

### 30.5. relkind/relispartition

~~~sql
SELECT oid::regclass, relkind, relispartition
FROM pg_class
WHERE oid IN (
    'partition_lab.order_events'::regclass,
    'partition_lab.order_events_2026_01'::regclass,
    'inheritance_lab.events'::regclass,
    'inheritance_lab.events_jan'::regclass
);
~~~

Parent declarative thường `relkind='p'`; legacy ordinary parent không được nhận diện chỉ bằng pg_inherits.

### 30.6. Bounds

~~~sql
SELECT
    c.oid::regclass AS child,
    pg_get_expr(c.relpartbound, c.oid) AS bound
FROM pg_class AS c
JOIN pg_inherits AS i ON i.inhrelid=c.oid
WHERE i.inhparent =
    'partition_lab.order_events'::regclass;
~~~

## 31. Kiểm tra dung lượng từng partition

Một partitioned parent có thể không chứa heap rows nên chỉ nhìn `pg_relation_size(parent)` sẽ thiếu tổng dữ liệu.

~~~sql
SELECT
    inhrelid::regclass AS partition_name,
    pg_size_pretty(
        pg_total_relation_size(inhrelid)
    ) AS total_size
FROM pg_inherits
WHERE inhparent =
    'partition_lab.order_events'::regclass;
~~~

Với hierarchy nhiều tầng, cần lấy **leaf partitions**, không chỉ direct children.

- `pg_relation_size` đo relation/fork theo đối số.
- `pg_indexes_size` đo indexes liên quan.
- `pg_total_relation_size` đo table/index/toast tương ứng.

Theo dõi default partition, partitions quá lớn và indexes bloat để phát hiện sai routing hoặc skew.

## 32. Schema migrations: một máy vs nhiều máy

### 32.1. Declarative partitioning

Một ALTER TABLE parent có thể tác động hierarchy theo semantics PostgreSQL, nhưng vẫn cần hiểu locks/index constraints/validation.

### 32.2. Inheritance cũ

Phải kiểm tra children, routing triggers, CHECK ranges, indexes và data types. Không giả định mọi schema change ở parent tự tạo những index và constraints mong muốn ở children.

### 32.3. Sharding

Migration có thể thành công trên A/B nhưng thất bại trên C:

~~~text
A schema version 12
B schema version 12
C schema version 11
~~~

Ứng dụng phải chịu giai đoạn mixed schema hoặc có orchestration/rollback.

### 32.4. Expand-contract

Một quy trình an toàn là thêm cấu trúc backward-compatible, deploy code hỗ trợ hai versions, backfill, chuyển read/write paths, rồi xóa cấu trúc cũ khi an toàn.

### 32.5. Cẩn thận với downtime và lock

CREATE INDEX/ATTACH/DETACH/ALTER có giới hạn transaction và locks theo phiên bản. Dùng lock_timeout/statement_timeout hợp lý trong migrations nhưng không xem timeout thay kế hoạch online schema change.

## 33. Security và tenant isolation

Partition theo tenant hoặc shard theo tenant **không tự thay authorization**.

### 33.1. Partitioning

Một user vẫn có thể query tenant khác nếu quyền SQL/RLS/application cho phép. Đừng xem partition key là security boundary.

### 33.2. Sharding

Nhiều tenants có thể nằm cùng một shard. Router đúng server không ngăn API lộ rows thuộc tenant khác.

### 33.3. RLS, GRANT và truy cập child trực tiếp

Cần hiểu quyền parent vs partitions, RLS policy evaluation và tác động khi client có quyền truy cập trực tiếp leaf partitions. Không suy luận policy trên parent tự động bảo vệ mọi đường truy cập độc lập vào child trong mọi tình huống.

### 33.4. Compliance

Tách tenant ra máy hoặc region riêng có thể hỗ trợ data residency nhưng tăng công backup, HA và maintenance. Phải phân tích yêu cầu cụ thể.

## 34. Khi nào nên dùng partitioning?

Thường phù hợp nếu:

- Một primary vẫn đáp ứng total throughput.
- Bảng lớn và query hay lọc theo partition key.
- Có retention/archival theo thời gian.
- Muốn VACUUM/REINDEX/maintenance theo phần.
- Muốn local ACID transaction và SQL trên một cluster.
- Không cần independent writable primaries ngay.

Ví dụ audit logs với 18 tháng retention và đa số query chỉ xem 7 ngày gần nhất: RANGE theo tháng/tuần là phương án nên benchmark.

**Không nên** phân vùng một bảng vài nghìn rows chỉ vì có thể, hoặc chia thành 10.000 partitions mà không đo planning/catalog overhead.

## 35. Khi nào inheritance phù hợp?

Một số hệ thống cũ dùng inheritance cho parent-child data model hoặc legacy partitioning. Nó có thể cần duy trì vì tương thích, nhưng phải kiểm tra:

- Parent có rows riêng không.
- Có routing trigger/rule không.
- CHECK ranges có chồng nhau không.
- UNIQUE/FK/index có đúng scope không.
- SELECT/UPDATE có dùng ONLY phù hợp không.
- Schema migrations có đồng bộ children không.

Với partitioning RANGE/LIST/HASH mới trên PostgreSQL hiện đại, declarative partitioning thường là điểm khởi đầu ít thủ công hơn.

## 36. Khi nào thực sự cần sharding?

Đáng cân nhắc khi:

- Primary write throughput vượt khả năng scale-up hợp lý.
- Dung lượng/WAL hoặc retention vượt một cluster.
- Tenant isolation cần independent primaries.
- Data residency hoặc failure isolation theo khu vực.
- Phần lớn queries/transactions có shard key rõ ràng.
- Tổ chức sẵn sàng quản lý distributed consistency và ops.

Trước đó nên đo lợi ích từ query/index tuning, declarative partitioning, read replicas, connection pooling, archival và tách analytics.

**Sharding không miễn phí**: cross-shard JOINs, global uniqueness, transactions, backup/restore, rebalancing và failover có thể phức tạp hơn rất nhiều so với một cluster.

## 37. Kết hợp: shard theo tenant, partition theo thời gian

~~~text
Request: tenant_id=1450, occurred_on='2026-02-10'
    |
Shard router -> PostgreSQL B
    |
Partition router -> events_2026_02 trên B
~~~

Hai tầng:

1. **Shard key** tenant_id chọn PostgreSQL server B.
2. **Partition key** occurred_on chọn leaf table tháng 02.

Lợi ích: writes phân tải nhiều primaries, retention monthly và query có cả tenant/date hưởng locality/pruning.

Chi phí: phải tạo partitions trên mọi shards; schema migrations đồng bộ, backup HA từng shard, báo cáo cross-tenant fanout và global uniqueness vẫn là vấn đề.

## 38. Migration từ bảng thường sang partitioning

Nếu bảng hiện có `PRIMARY KEY(order_id)` và muốn phân vùng theo `order_date`, phải xem lại uniqueness invariant trước.

Một kế hoạch có thể gồm:

1. Tạo parent partitioned mới.
2. Tạo partitions và indexes.
3. Thiết kế PK/FK hợp lệ chứa partition key khi cần.
4. Backfill data theo batch.
5. Đồng bộ writes trong thời gian backfill.
6. Kiểm tra counts/checksums/constraints.
7. Cutover application.
8. Giữ rollback path.
9. Dọn legacy table khi an toàn.

Không chỉ đổi tên bảng; ORM, triggers, sequences, default values, RLS và UPSERT behavior có thể chịu ảnh hưởng.

## 39. Migration inheritance sang declarative

Các bước kiểm tra quan trọng:

- `SELECT COUNT(*) FROM ONLY parent`: có rows trực tiếp không?
- CHECK bounds của children có hợp lệ/không chồng không?
- Data types/columns/defaults có tương thích không?
- Child indexes và constraints cần chuyển đổi thế nào?
- PK/UNIQUE/FK có phù hợp partition key mới không?
- Routing triggers/rules cũ có cần gỡ không?
- ATTACH validation có thể scan bao nhiêu dữ liệu?
- Cutover trong lúc concurrent writes thế nào?
- Backup/rollback và application compatibility ra sao?

Inheritance partitioning không tự nâng cấp chỉ bằng thay `INHERITS` thành `PARTITION OF`.

## 40. Những hiểu lầm phổ biến

1. **“Partitioning là sharding.”** Sai: một bên chủ yếu là tables trong cluster, bên kia là dữ liệu trên servers độc lập.
2. **“Nhiều partitions là nhiều primaries.”** Sai.
3. **“INHERITS giống PARTITION OF.”** Sai về routing và constraints.
4. **“CHECK ở child tự route INSERT parent.”** Sai.
5. **“SELECT parent inheritance chỉ đọc parent.”** Sai; dùng ONLY khi cần.
6. **“PK parent inheritance enforce toàn children.”** Sai.
7. **“Parent partitioned luôn có global unique index.”** Sai.
8. **“PK(event_id) luôn hợp lệ khi partition theo date.”** Sai theo giới hạn declarative thông thường.
9. **“Có partition pruning thì không cần index.”** Sai.
10. **“WHERE tenant_id tự prune time partitions.”** Sai nếu không có thông tin bounds liên quan.
11. **“HASH partitions ở bốn tables là bốn machines.”** Sai.
12. **“HASH theo tenant cân bằng tenant siêu lớn.”** Sai.
13. **“Càng nhiều partitions càng nhanh.”** Sai; planning/catalog overhead.
14. **“DETACH tương đương DELETE từng row.”** Sai.
15. **“Default partition không cần giám sát.”** Sai.
16. **“Replication là sharding.”** Sai.
17. **“Read replicas tăng writable primaries.”** Sai.
18. **“FDW tự có global ACID.”** Sai.
19. **“Hai COMMIT ở hai shards là atomic.”** Sai.
20. **“Unique mỗi shard là unique toàn platform.”** Sai.
21. **“Foreign key local tự tham chiếu shard khác.”** Sai.
22. **“UUID thay mọi unique constraints.”** Sai.
23. **“Một router đúng shard thay authorization.”** Sai.
24. **“Có backup từng shard thì restore toàn hệ chắc chắn nhất quán.”** Sai.
25. **“Chỉ cần thêm server, không cần rebalance.”** Sai trong nhiều kiến trúc.

## 41. Bài tập thực hành

### Bài 1 — Định nghĩa

Phân biệt declarative partitioning, inheritance và sharding bằng ba câu.

**Gợi ý:** Bảng con một cluster có bounds/routing; cha-con INHERITS; dữ liệu nhiều servers.

### Bài 2 — RANGE

Partition tháng 01 `FROM('2026-01-01') TO('2026-02-01')` có chứa ngày 01/02 không?

**Đáp án:** Không; cận trên loại trừ.

### Bài 3 — Parent

Hàng của declarative partitioned table chủ yếu nằm ở parent heap hay leaf partitions?

**Đáp án:** Leaf partitions.

### Bài 4 — Pruning

Bảng partition theo occurred_on; WHERE chỉ tenant_id=42. PostgreSQL có tự loại mọi tháng khác không?

**Đáp án:** Không theo bounds thời gian chỉ từ tenant.

### Bài 5 — Index

Vì sao index tenant_id vẫn hữu ích trong time partitions?

**Gợi ý:** Nó giảm rows scan trong leaf còn lại.

### Bài 6 — tableoid

Viết SQL biết relation thực sự chứa event_id=101.

~~~sql
SELECT tableoid::regclass, event_id
FROM partition_lab.order_events
WHERE event_id=101;
~~~

### Bài 7 — HASH

Có nên tự dùng `tenant_id % 4` để suy luận chính xác PostgreSQL HASH partition không?

**Đáp án:** Không.

### Bài 8 — Inheritance insert

INSERT vào ordinary parent có tự đi child phù hợp CHECK không?

**Đáp án:** Không.

### Bài 9 — ONLY

SELECT với ONLY khác SELECT inheritance parent không ONLY thế nào?

**Gợi ý:** Chỉ đọc parent rows.

### Bài 10 — Constraint exclusion

Cơ chế nào có thể dùng CHECK constraints để loại children không phù hợp?

**Đáp án:** Constraint exclusion.

### Bài 11 — PK

Với partition key occurred_on, PK trên event_id đơn có mặc định hợp lệ như global unique không?

**Đáp án:** Không.

### Bài 12 — PK hợp lệ

Hãy đề xuất PK cho event_id và occurred_on.

**Gợi ý:** PRIMARY KEY(event_id, occurred_on).

### Bài 13 — Global ID

Vì sao UUID không thay hoàn toàn constraint kiểm tra business uniqueness?

**Gợi ý:** Business keys khác UUID và rows có thể được nhập thủ công/lặp.

### Bài 14 — UPDATE key

UPDATE occurred_on từ January sang February có thể làm gì?

**Đáp án:** Row movement giữa partitions.

### Bài 15 — Retention

Vì sao drop/detach một tháng khác DELETE hàng triệu rows?

**Gợi ý:** DDL trên relation thay vì row-level DML.

### Bài 16 — Default partition

Một default partition tích tụ cả năm dữ liệu do job tạo tháng mới thất bại. Rủi ro gì?

**Gợi ý:** Storage, pruning, ATTACH validation, retention.

### Bài 17 — Catalog

Hàm nào hiển thị partition hierarchy?

**Đáp án:** pg_partition_tree trên phiên bản hỗ trợ.

### Bài 18 — pg_inherits

pg_inherits có chỉ dành cho declarative partitioning không?

**Đáp án:** Không.

### Bài 19 — Storage

Vì sao chỉ pg_relation_size(parent) có thể thiếu tổng size?

**Gợi ý:** Heap rows nằm trong leafs.

### Bài 20 — Subpartitions

36 months × 32 buckets có bao nhiêu leaf tables?

**Đáp án:** 1.152.

### Bài 21 — Shard key

SaaS đa tenant có 90% queries theo tenant_id. Chọn shard key nào đáng thử?

**Gợi ý:** tenant_id, nhưng kiểm tra hot tenants.

### Bài 22 — Scatter-gather

Query toàn hệ không có shard key có thể cần gì?

**Gợi ý:** Fanout/aggregate.

### Bài 23 — Co-location

Vì sao orders và order_items cùng shard theo tenant giúp JOIN?

**Gợi ý:** Giảm network.

### Bài 24 — Hot tenant

Một tenant chiếm 80% writes. Hash theo tenant_id có tự chia tenant ra nhiều servers không?

**Đáp án:** Không.

### Bài 25 — Replication

Physical standby chứa bản sao hay dữ liệu shard khác?

**Đáp án:** Bản sao theo replication.

### Bài 26 — FDW

postgres_fdw có tự cung cấp global unique index và distributed commit coordination đầy đủ không?

**Đáp án:** Không mặc định.

### Bài 27 — Global uniqueness

UNIQUE(email) mỗi shard có bảo đảm email unique toàn hệ không?

**Đáp án:** Không.

### Bài 28 — FK

Foreign key local ở A có tự tham chiếu row chỉ tồn tại ở B như local row không?

**Đáp án:** Không mặc định.

### Bài 29 — Distributed transfer

A trừ tiền và COMMIT, B chưa cộng tiền thì network lỗi. Giải pháp gì?

**Gợi ý:** Co-location, distributed transaction protocol hoặc saga/outbox/idempotency/reconciliation.

### Bài 30 — Rebalance

Virtual buckets giúp gì khi thêm server?

**Gợi ý:** Di chuyển một nhóm buckets và cập nhật mapping.

### Bài 31 — Backup

Backup shard A lúc 10:00 và B lúc 10:05 có chắc là one consistent snapshot toàn hệ không?

**Đáp án:** Không chắc.

### Bài 32 — HA

Một cluster có 100 partitions nhưng một primary và không standby có tự HA không?

**Đáp án:** Không.

### Bài 33 — RLS

Partition theo tenant_id có tự ngăn tenant A xem dữ liệu B không?

**Đáp án:** Không; cần authorization/RLS/GRANT.

### Bài 34 — Kết hợp

Với shard theo tenant, partition theo ngày, đâu là hai lớp routing?

**Đáp án:** Router chọn server theo tenant; PostgreSQL chọn leaf partition theo ngày.

### Bài 35 — Migration

Liệt kê năm điều phải kiểm tra trước khi chuyển legacy inheritance sang declarative partitioning.

**Gợi ý:** Parent rows, CHECK ranges, index/constraints, routing triggers, schema compatibility.

### Bài 36 — Chọn kiến trúc

| Nhu cầu | Hướng đánh giá |
|---|---|
| Xóa dữ liệu theo tháng trên một primary đủ mạnh | Declarative RANGE |
| Parent-child legacy model | Inheritance nếu hiểu giới hạn |
| Write throughput vượt một primary | Sharding |
| Tăng read QPS khi một primary vẫn ghi đủ | Read replicas |
| Write scale-out và retention theo tháng | Sharding + partitions trong shards |

## 42. Checklist quyết định

1. Xác định pain point: scans, retention, bloat, write capacity hay HA.
2. Đo workload: row count, CPU, WAL, IOPS, p95/p99.
3. Phân nhóm queries theo ngày, tenant, global ID.
4. Liệt kê PK/UNIQUE/FK và transaction invariants.
5. Thử query/index tuning, archival, read replicas trước.
6. Nếu partition: chọn key, RANGE/LIST/HASH, granularity.
7. Đo pruning bằng EXPLAIN và thống kê.
8. Thiết kế tạo partitions tương lai, default và retention.
9. Theo dõi leaf indexes, ANALYZE, VACUUM và planning overhead.
10. Nếu inheritance: kiểm tra CHECK, ONLY, INSERT routing.
11. Nếu shard: chọn key theo locality và skew.
12. Thiết kế router, shard map, metadata version.
13. Phân loại single-shard và cross-shard queries.
14. Bảo vệ global uniqueness, FK, distributed transactions.
15. Thiết kế HA, replication và backup/recovery từng shard.
16. Lập plan rebalance, online migration và rollback.
17. Kiểm tra RLS/permissions/tenant isolation.
18. Test concurrent writes và network failure.
19. Đo hiệu năng trước/sau trên dữ liệu đại diện.
20. Rà soát architecture khi distribution thay đổi.

## 43. Bảng ghi nhớ cuối

| Khái niệm | Ghi nhớ |
|---|---|
| Declarative partitioning | PARTITION BY RANGE/LIST/HASH |
| Leaf partition | Table thực chứa rows |
| Partition key | Chọn table con |
| RANGE bounds | Lower inclusive, upper exclusive |
| Partition pruning | Bỏ partitions không chứa hàng phù hợp |
| Local index | Index trên leaf relation |
| Parent partitioned index | Definition quản lý local indexes |
| DEFAULT partition | Hứng rows ngoài các bounds cụ thể |
| ATTACH/DETACH | Gắn/tách partition và hierarchy |
| INHERITS | Table inheritance |
| ONLY | Chỉ ordinary parent trong truy vấn phù hợp |
| Constraint exclusion | Dùng CHECK loại child legacy |
| tableoid | Relation vật lý chứa row |
| Global uniqueness | Không tự có trên local indexes |
| Sharding | Phân tán dữ liệu qua servers |
| Shard key | Chọn server |
| Shard map | Key/bucket -> server |
| Scatter-gather | Query nhiều shards rồi gộp |
| Co-location | Giữ dữ liệu cần JOIN cùng shard |
| Hot shard | Một server quá tải |
| Rebalance | Di chuyển tenants/buckets |
| Replication | Sao chép dữ liệu cho HA/reads |
| postgres_fdw | Truy cập foreign tables |
| Distributed transaction | Phối hợp tính nhất quán nhiều servers |
| Global FK | Cần giải pháp phân tán hoặc co-location |
| RPO/RTO | Mục tiêu khôi phục |
| pg_partition_tree | Xem declarative hierarchy |
| pg_inherits | Parent/child metadata |
| pg_partitioned_table | Partition strategy/key metadata |
| EXPLAIN | Xem plan/pruning |
| ANALYZE | Cập nhật planner statistics |

---

## Kết luận

**Partitioning, inheritance và sharding là ba cơ chế khác nhau, có thể kết hợp nhưng không thể đánh đồng.**

**Declarative partitioning** chia một bảng logic thành các partitions trong một PostgreSQL cluster. Nó tự động định tuyến INSERT, hỗ trợ partition pruning và retention theo phần. Nó phù hợp bảng lớn có điều kiện lọc hoặc vòng đời dữ liệu rõ, nhưng **không tự tăng số writable primaries** và có giới hạn về PK/UNIQUE liên quan partition key.

**Table inheritance** tạo quan hệ parent-child qua `INHERITS`. Parent có thể chứa rows riêng, SELECT thường bao gồm descendants, INSERT không tự route và unique/foreign key/indexes không tự bao phủ toàn cây. Nó là tính năng riêng, từng dùng cho phân vùng thủ công, không phải phiên bản cú pháp tương đương của declarative partitioning.

**Sharding** chia dữ liệu qua các PostgreSQL servers/clusters độc lập. Nó có thể tăng write throughput và phân tán dung lượng nhưng mang theo routing, cross-shard JOIN, global constraints, distributed transaction, HA, backup và rebalancing. Một giải pháp distributed PostgreSQL cụ thể có thể hỗ trợ nhiều phần trong số đó, nhưng các bảo đảm phải được kiểm tra theo sản phẩm/phiên bản.

Quyết định nên bắt đầu từ **workload thật, yêu cầu nhất quán, cách truy vấn và khả năng vận hành**, không từ số partitions hoặc số servers. Khi biết rõ mỗi kỹ thuật giải quyết vấn đề nào, bạn có thể chọn phân vùng để tối ưu trong cluster, inheritance khi thực sự cần semantics cha/con, và sharding khi bài toán đòi mở rộng ngang qua nhiều máy.
