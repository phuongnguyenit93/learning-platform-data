# Phân vùng nhiều tầng và chi phí số lượng phân vùng trong PostgreSQL

Khi một bảng PostgreSQL tăng đến hàng trăm triệu hoặc hàng tỷ bản ghi, phân vùng (*table partitioning*) có thể giúp giới hạn phạm vi dữ liệu cần đọc, quản lý vòng đời dữ liệu theo kỳ và tách công việc bảo trì. Chẳng hạn, bảng sự kiện có thể được chia theo tháng để truy vấn một tuần chỉ cần đọc một hoặc hai phân vùng thay vì toàn bộ lịch sử.

Nhưng nhu cầu vận hành có thể phức tạp hơn: trong mỗi tháng, hệ thống lại muốn chia theo vùng kinh doanh hoặc tenant. Khi đó ta có **phân vùng nhiều tầng** (*multi-level partitioning* hay *subpartitioning*).

Ví dụ:

```text
events                                  -- RANGE(event_at)
|
+-- events_2026_01                      -- tháng 01/2026, LIST(region)
|   +-- events_2026_01_north            -- region = NORTH
|   +-- events_2026_01_south            -- region = SOUTH
|   +-- events_2026_01_other            -- các region còn lại
|
+-- events_2026_02                      -- tháng 02/2026, LIST(region)
|   +-- events_2026_02_north
|   +-- events_2026_02_south
|   +-- events_2026_02_other
|
+-- ... các tháng tiếp theo
```

Query chỉ xem sự kiện tháng Một ở khu vực NORTH có thể được **partition pruning** đến một partition lá, nếu điều kiện và kế hoạch thực thi cho phép. Tuy nhiên, mỗi tầng chia thêm cũng tạo thêm bảng con, chỉ mục con, metadata, đối tượng thống kê, công việc autovacuum và đôi khi cả chi phí lập kế hoạch hoặc khóa.

Nếu lưu 36 tháng và mỗi tháng chia 32 nhóm, bạn đã có:

```text
36 phân vùng tháng
  x 32 phân vùng con/tháng
  = 1.152 phân vùng lá

+ 36 nút phân vùng trung gian
+ 1 bảng phân vùng gốc
```

Nếu mỗi partition lá mang bốn chỉ mục vật lý, tổng số chỉ mục lá có thể lên tới **4.608**, chưa tính các đối tượng khác. Đó không chỉ là “thêm một lớp tổ chức dữ liệu”; đó là tăng đáng kể số relation mà PostgreSQL phải quản lý.

Bài học này giải thích cách thiết kế phân vùng nhiều tầng, cách PostgreSQL định tuyến hàng và cắt bỏ phân vùng, cách đo chi phí khi số partition tăng, cùng phương pháp chọn một số lượng phân vùng phù hợp dựa trên truy vấn và vận hành thực tế.

---

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt bảng phân vùng gốc, phân vùng trung gian và phân vùng lá.
2. Thiết kế cây phân vùng hai tầng bằng các phương pháp `RANGE`, `LIST` và `HASH`.
3. Viết DDL PostgreSQL tạo subpartitioning với `PARTITION BY` và `PARTITION OF`.
4. Giải thích vì sao **partition pruning** phụ thuộc điều kiện truy vấn tại từng tầng.
5. Phân biệt pruning lúc lập kế hoạch và lúc thực thi; nhận diện các dấu hiệu trong `EXPLAIN`.
6. Tính sự tăng trưởng số partition theo tích các tầng, không chỉ đếm số nhóm ở tầng gốc.
7. Phân tích chi phí số partition đối với **planning, metadata/catalog, relation locks, relcache, memory, file handles, indexes, statistics, autovacuum, DDL và backup/restore**.
8. Hiểu vì sao truy vấn quét toàn lịch sử có thể không hưởng lợi, thậm chí tốn thêm overhead khi chia quá nhỏ.
9. Phân biệt partition pruning với index scan, partition-wise join và partition-wise aggregate.
10. Nhận biết yêu cầu với `PRIMARY KEY`, `UNIQUE`, `FOREIGN KEY` trong bảng phân vùng nhiều tầng.
11. Xử lý dữ liệu không khớp partition, default partition, tạo partition mới và thay đổi partition key.
12. Hiểu ưu/nhược của phân vùng theo thời gian rồi tenant/vùng so với thứ tự ngược lại.
13. Lập kế hoạch vận hành: precreate, attach/detach, retention, analyze, vacuum và index maintenance.
14. Thiết kế bài đo so sánh một tầng với hai tầng, đo cả query latency và số relation phải bảo trì.
15. Tránh thiết kế mỗi khách hàng, mỗi giờ hoặc mỗi sự kiện là một partition khi không có lợi ích đo được.

**Phạm vi:** Bảng khai báo phân vùng (*declarative partitioning*) của PostgreSQL hiện đại. Chi tiết cú pháp, khả năng pruning, behavior của constraints và tính năng bảo trì có thể khác nhau giữa các phiên bản; khi triển khai trên hệ thống thật cần xác minh phiên bản PostgreSQL và thử nghiệm trên workload tương ứng. Các câu `DROP TABLE`/`CREATE TABLE` trong bài chỉ chạy trong database lab có thể reset.

---

## 2. Nhắc lại ba phương pháp phân vùng cơ bản

PostgreSQL hỗ trợ ba phương pháp declarative partitioning thông dụng.

### 2.1. RANGE — chia theo khoảng

```sql
CREATE TABLE measurements (
    measured_at TIMESTAMPTZ NOT NULL,
    sensor_id BIGINT NOT NULL,
    value NUMERIC
) PARTITION BY RANGE (measured_at);
```

Một partition theo tháng:

```sql
CREATE TABLE measurements_2026_01
PARTITION OF measurements
FOR VALUES FROM ('2026-01-01 00:00:00+00')
             TO   ('2026-02-01 00:00:00+00');
```

Ranh giới RANGE dùng mô hình **bao gồm đầu, loại trừ cuối** (*half-open interval*) cho cấu hình phổ biến như trên.

Thích hợp với dữ liệu có tuổi thọ, truy vấn theo ngày/tháng và thao tác retention theo khoảng thời gian.

### 2.2. LIST — chia theo tập giá trị

```sql
CREATE TABLE regional_data (
    region TEXT NOT NULL,
    payload JSONB
) PARTITION BY LIST (region);

CREATE TABLE regional_data_north
PARTITION OF regional_data FOR VALUES IN ('NORTH');

CREATE TABLE regional_data_south
PARTITION OF regional_data FOR VALUES IN ('SOUTH');
```

Thích hợp với một số nhóm rời rạc có ý nghĩa rõ như vùng, loại nghiệp vụ, thị trường.

Không nên mặc định tạo một LIST partition cho mỗi tenant nếu tenant tăng đến hàng nghìn/hàng chục nghìn, bởi số partition có thể trở thành chi phí lớn.

### 2.3. HASH — chia theo giá trị hash

```sql
CREATE TABLE tenant_data (
    tenant_id BIGINT NOT NULL,
    payload JSONB
) PARTITION BY HASH (tenant_id);

CREATE TABLE tenant_data_h0
PARTITION OF tenant_data
FOR VALUES WITH (MODULUS 4, REMAINDER 0);

CREATE TABLE tenant_data_h1
PARTITION OF tenant_data
FOR VALUES WITH (MODULUS 4, REMAINDER 1);

CREATE TABLE tenant_data_h2
PARTITION OF tenant_data
FOR VALUES WITH (MODULUS 4, REMAINDER 2);

CREATE TABLE tenant_data_h3
PARTITION OF tenant_data
FOR VALUES WITH (MODULUS 4, REMAINDER 3);
```

HASH hữu ích khi muốn phân phối nhiều giá trị khóa trên một số partition đã chọn, không cần một partition riêng cho mỗi tenant.

**Không nhầm HASH partition với PostgreSQL sharding qua nhiều máy.** Các partition khai báo ở đây vẫn là các relation thuộc cùng database PostgreSQL, trừ khi hệ thống sử dụng giải pháp phân tán riêng.

---

## 3. Multi-level partitioning là gì?

Phân vùng nhiều tầng là khi một **partition của bảng cha lại chính nó được khai báo là một partitioned table**. Mỗi tầng có thể chọn phương pháp và khóa phân vùng khác nhau theo mô hình dữ liệu.

Ví dụ:

```text
RANGE(event_at)                -- tầng 1
   |
   +-- January 2026
   |      |
   |      +-- LIST(region)    -- tầng 2
   |            |
   |            +-- NORTH     -- partition lá
   |            +-- SOUTH     -- partition lá
   |            +-- DEFAULT   -- partition lá
   |
   +-- February 2026
          |
          +-- LIST(region)
                |
                +-- NORTH
                +-- SOUTH
                +-- DEFAULT
```

Một **partition lá** (*leaf partition*) là bảng nằm ở cuối nhánh, lưu hàng thực tế theo thiết kế heap thông thường. Bảng gốc và những partition trung gian là các **partitioned tables** dùng để định nghĩa cây và định tuyến.

### 3.1. Mỗi hàng đi theo một đường từ gốc xuống lá

Với hàng:

```text
event_at = 2026-01-15 09:00:00+00
region   = NORTH
tenant_id = 42
```

PostgreSQL xác định:

1. `event_at` thuộc khoảng tháng Một ở tầng RANGE.
2. Trong tháng Một, `region='NORTH'` thuộc partition LIST NORTH.
3. Hàng được lưu tại partition lá `events_2026_01_north`.

Client vẫn có thể:

```sql
INSERT INTO partition_levels_lab.events (...);
```

mà không phải tự chọn tên partition lá. PostgreSQL định tuyến theo các partition bounds đã khai báo.

### 3.2. Không cần tất cả các tháng có cấu trúc con giống nhau về mặt cú pháp

Về lý thuyết, mỗi partition trung gian có thể có cấu trúc subpartition phù hợp riêng. Tuy nhiên, hệ thống vận hành thường nên **giữ mô hình nhất quán giữa các kỳ** nếu business rules giống nhau, để tránh lỗi tạo thiếu partition, đặc tính index không đồng đều và bảo trì khó đoán.

### 3.3. Khi nào hai tầng đáng xem xét?

Một số trường hợp hợp lý:

- Dữ liệu log lớn, retention theo tháng, trong mỗi tháng chia thêm một số nhóm hash để giảm kích thước relation.
- Dữ liệu sự kiện nhiều tenant, query vừa giới hạn thời gian vừa giới hạn tenant.
- Thời gian được dùng để xóa/archival cả partition, còn tầng phụ để cô lập một số nhóm vận hành.
- Một số truy vấn và công việc bảo trì có khả năng chỉ xử lý rất ít leaf partitions.
- Một partition tháng đơn tầng vẫn quá lớn để VACUUM, rebuild index hoặc các hoạt động có tính cục bộ thực hiện thuận lợi.

Không nên thêm tầng thứ hai nếu nó chỉ làm mỗi partition nhỏ hơn nhưng **không cải thiện pruning, maintenance hay đường truy cập cụ thể**.

---

## 4. Lab chuẩn: RANGE theo tháng, LIST theo region

Bộ lab dùng hai tháng và ba partition lá trên mỗi tháng. Tất cả DDL dưới đây phải chạy trên database test.

> **Cảnh báo:** `DROP TABLE IF EXISTS ... CASCADE` có thể xóa các đối tượng phụ thuộc trong schema lab. Chỉ chạy trong môi trường được phép reset. Không chạy trên production.

### 4.1. Tạo bảng phân vùng gốc

```sql
CREATE SCHEMA IF NOT EXISTS partition_levels_lab;

DROP TABLE IF EXISTS partition_levels_lab.events CASCADE;

CREATE TABLE partition_levels_lab.events (
    event_at TIMESTAMPTZ NOT NULL,
    region TEXT NOT NULL
        CHECK (region IN ('NORTH', 'SOUTH', 'CENTRAL')),
    event_id BIGINT NOT NULL,
    tenant_id BIGINT NOT NULL,
    event_type TEXT NOT NULL
        CHECK (event_type IN ('VIEW', 'CLICK', 'PURCHASE')),
    amount NUMERIC(14,2) NOT NULL DEFAULT 0
        CHECK (amount >= 0),
    payload JSONB NOT NULL DEFAULT '{}'::JSONB,
    PRIMARY KEY (event_at, region, event_id)
) PARTITION BY RANGE (event_at);
```

Tại sao PRIMARY KEY gồm `event_at` và `region`?

- Tầng một phân vùng theo `event_at`.
- Tầng hai sẽ phân vùng theo `region`.
- Trong hệ thống declarative partitioning thông thường của PostgreSQL, UNIQUE/PRIMARY KEY trên cây phân vùng phải bao gồm các cột partition key cần thiết để bảo đảm uniqueness trên toàn cây theo ranh giới partition.
- Vì không có global unique index tổng quát trên mọi partition lá theo cách nhiều người mới kỳ vọng, `PRIMARY KEY(event_id)` đơn lẻ không thể được giả định là đủ điều kiện cho cây này.

Nếu ứng dụng cần `event_id` duy nhất toàn hệ thống độc lập với ngày và region, phải thiết kế thêm cơ chế phù hợp, chẳng hạn bảng registry chứa khóa duy nhất hoặc một kiến trúc cấp phát ID/kiểm tra uniqueness khác có tính giao dịch; không dựa đơn thuần vào việc mỗi partition lá có local UNIQUE(event_id).

### 4.2. Tạo partition tháng Một, đồng thời khai báo tầng LIST

```sql
CREATE TABLE partition_levels_lab.events_2026_01
PARTITION OF partition_levels_lab.events
FOR VALUES FROM ('2026-01-01 00:00:00+00')
             TO   ('2026-02-01 00:00:00+00')
PARTITION BY LIST (region);
```

Điểm quyết định là dòng cuối:

```sql
PARTITION BY LIST (region)
```

Nó làm `events_2026_01` trở thành một **partition trung gian** chứ chưa phải partition lá lưu các hàng trực tiếp.

### 4.3. Ba lá của tháng Một

```sql
CREATE TABLE partition_levels_lab.events_2026_01_north
PARTITION OF partition_levels_lab.events_2026_01
FOR VALUES IN ('NORTH');

CREATE TABLE partition_levels_lab.events_2026_01_south
PARTITION OF partition_levels_lab.events_2026_01
FOR VALUES IN ('SOUTH');

CREATE TABLE partition_levels_lab.events_2026_01_other
PARTITION OF partition_levels_lab.events_2026_01
DEFAULT;
```

Vì ràng buộc `region IN ('NORTH','SOUTH','CENTRAL')` ở bảng gốc, trong dữ liệu lab, partition DEFAULT của mỗi tháng chủ yếu nhận `CENTRAL`. Không nên tổng quát rằng DEFAULT chỉ nhận CENTRAL nếu bảng thật không có CHECK này.

### 4.4. Tạo tháng Hai và các lá

```sql
CREATE TABLE partition_levels_lab.events_2026_02
PARTITION OF partition_levels_lab.events
FOR VALUES FROM ('2026-02-01 00:00:00+00')
             TO   ('2026-03-01 00:00:00+00')
PARTITION BY LIST (region);

CREATE TABLE partition_levels_lab.events_2026_02_north
PARTITION OF partition_levels_lab.events_2026_02
FOR VALUES IN ('NORTH');

CREATE TABLE partition_levels_lab.events_2026_02_south
PARTITION OF partition_levels_lab.events_2026_02
FOR VALUES IN ('SOUTH');

CREATE TABLE partition_levels_lab.events_2026_02_other
PARTITION OF partition_levels_lab.events_2026_02
DEFAULT;
```

Bây giờ cây có:

- Một bảng gốc.
- Hai partition trung gian theo tháng.
- Sáu partition lá theo region.
- Tổng cộng **chín relation trong cây bảng**, chưa kể chỉ mục.

### 4.5. Nạp dữ liệu mẫu 15.000 sự kiện

```sql
INSERT INTO partition_levels_lab.events (
    event_at, region, event_id, tenant_id,
    event_type, amount, payload
)
SELECT
    TIMESTAMPTZ '2026-01-01 00:00:00+00'
        + (g.n % 59) * INTERVAL '1 day'
        + (g.n % 86400) * INTERVAL '1 second',
    CASE (g.n % 3)
        WHEN 0 THEN 'NORTH'
        WHEN 1 THEN 'SOUTH'
        ELSE 'CENTRAL'
    END,
    g.n::BIGINT,
    (g.n % 200)::BIGINT + 1,
    CASE (g.n % 5)
        WHEN 0 THEN 'PURCHASE'
        WHEN 1 THEN 'CLICK'
        ELSE 'VIEW'
    END,
    CASE WHEN g.n % 5 = 0
        THEN ROUND((g.n % 10000)::NUMERIC / 100, 2)
        ELSE 0::NUMERIC
    END,
    JSONB_BUILD_OBJECT('source', 'lab', 'n', g.n)
FROM GENERATE_SERIES(1, 15000) AS g(n);

ANALYZE partition_levels_lab.events;
```

Khoảng ngày offset 0..58 từ 1/1/2026 nằm trong hai tháng Một và Hai; vì không có bản ghi tháng Ba, toàn bộ hàng có thể đi vào cây đã tạo.

### 4.6. Kiểm tra đường lưu thực tế bằng tableoid

PostgreSQL cung cấp system column `tableoid` để biết relation vật lý chứa hàng:

```sql
SELECT
    tableoid::REGCLASS AS leaf_table,
    COUNT(*) AS event_count
FROM partition_levels_lab.events
GROUP BY tableoid
ORDER BY tableoid;
```

Nếu query ở parent trả số theo sáu lá, việc routing đã diễn ra. Tên leaf_table có thể hiển thị kèm schema hoặc không, tùy search_path và cách PostgreSQL biểu diễn REGCLASS.

### 4.7. Nhìn cây bằng pg_partition_tree

```sql
SELECT
    relid::REGCLASS AS relation_name,
    parentrelid::REGCLASS AS parent_relation,
    isleaf,
    level
FROM pg_partition_tree(
    'partition_levels_lab.events'::REGCLASS
)
ORDER BY level, relid;
```

Với cây lab:

| level | Loại relation | Số lượng |
| ---: | --- | ---: |
| 0 | Bảng gốc | 1 |
| 1 | Partition tháng, tiếp tục partitioned | 2 |
| 2 | Partition lá chứa hàng | 6 |

Đếm leaf partitions:

```sql
SELECT
    COUNT(*) FILTER (WHERE isleaf) AS leaf_partitions,
    COUNT(*) FILTER (WHERE NOT isleaf) AS partitioned_nodes,
    MAX(level) AS max_level
FROM pg_partition_tree(
    'partition_levels_lab.events'::REGCLASS
);
```

Kết quả mong đợi: `leaf_partitions=6`, `partitioned_nodes=3`, `max_level=2`.

### 4.8. Tạo index qua parent

```sql
CREATE INDEX idx_events_tenant_time
ON partition_levels_lab.events (tenant_id, event_at);

CREATE INDEX idx_events_event_type_time
ON partition_levels_lab.events (event_type, event_at);
```

Khi tạo index trên partitioned parent, PostgreSQL quản lý một **partitioned index** về mặt metadata và các index tương ứng trên partitions theo cơ chế được hỗ trợ. Index thực sự lưu entry nằm trên các partition lá; không nên hình dung parent có một B-tree chung chứa tất cả hàng của toàn cây.

Mỗi index thêm vào parent có thể nhân số index vật lý theo số lá. Cùng với PRIMARY KEY, lab có nhiều index leaves tương ứng; ở production, đây là chi phí đáng đo.

---

## 5. Định tuyến INSERT qua hai tầng

Khi client INSERT vào parent, PostgreSQL phải chọn nhánh dựa trên các partition keys.

```sql
INSERT INTO partition_levels_lab.events (
    event_at, region, event_id, tenant_id,
    event_type, amount
)
VALUES (
    TIMESTAMPTZ '2026-01-17 10:30:00+00',
    'NORTH',
    9000001,
    42,
    'CLICK',
    0
)
RETURNING
    tableoid::REGCLASS AS stored_in,
    event_at,
    region,
    event_id;
```

Kết quả dự kiến chứa:

```text
stored_in = partition_levels_lab.events_2026_01_north
```

### 5.1. Nếu không có partition phù hợp?

Thử một hàng tháng Ba khi lab chưa tạo tháng Ba:

```sql
INSERT INTO partition_levels_lab.events (
    event_at, region, event_id, tenant_id,
    event_type, amount
)
VALUES (
    TIMESTAMPTZ '2026-03-01 00:00:00+00',
    'NORTH',
    9000002,
    42,
    'VIEW',
    0
);
```

Vì parent chưa có RANGE partition tháng Ba và cũng không có RANGE DEFAULT, INSERT sẽ không tìm được partition phù hợp và **báo lỗi**.

Đây là một điểm vận hành quan trọng: PostgreSQL không tự tạo partition theo lịch chỉ vì có câu INSERT mới.

### 5.2. Nếu region chưa có lá riêng?

Trong lab, `CENTRAL` đi tới partition `_other` của tháng tương ứng. Nếu không có DEFAULT ở tầng LIST và cũng không có leaf CENTRAL, một INSERT region CENTRAL có thể thất bại dù tầng RANGE đã tìm được tháng phù hợp.

Để định tuyến một hàng thành công, **mọi tầng trên đường đi đều phải có partition phù hợp**.

### 5.3. INSERT trực tiếp vào partition lá có nên không?

Ứng dụng thường nên INSERT vào parent để PostgreSQL quyết định partition theo quy tắc DDL. Ghi thẳng vào leaf làm ứng dụng phụ thuộc tên bảng vật lý theo tháng/vùng và dễ hỏng khi thêm kỳ, đổi chính sách hoặc điều chỉnh cây.

Chỉ dùng thao tác trực tiếp lên leaf cho mục đích vận hành/di chuyển dữ liệu có kiểm soát khi thật sự cần.

---

## 6. Partition pruning qua nhiều tầng

**Partition pruning** là quá trình PostgreSQL loại những partition không thể chứa hàng thỏa điều kiện truy vấn, dựa trên partition keys và bounds.

Mục tiêu của hai tầng không phải ép PostgreSQL mở tất cả sáu lá rồi lọc bằng `WHERE`, mà là nhận ra các nhánh có thể bỏ qua.

### 6.1. Query lọc tháng và vùng

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    COUNT(*) AS events,
    SUM(amount) AS total_amount
FROM partition_levels_lab.events
WHERE event_at >= TIMESTAMPTZ '2026-01-01 00:00:00+00'
  AND event_at <  TIMESTAMPTZ '2026-02-01 00:00:00+00'
  AND region = 'NORTH';
```

Khi pruning hiệu quả, query chỉ cần xét lá tháng Một/NORTH. Planner có thể sử dụng Seq Scan hay Index Scan trên chính leaf tùy số hàng và chi phí.

**Pruning chọn relation nào; index quyết định cách tìm hàng bên trong relation đó.** Hai cơ chế bổ sung cho nhau.

### 6.2. Chỉ lọc theo tháng

```sql
SELECT COUNT(*)
FROM partition_levels_lab.events
WHERE event_at >= TIMESTAMPTZ '2026-02-01 00:00:00+00'
  AND event_at <  TIMESTAMPTZ '2026-03-01 00:00:00+00';
```

PostgreSQL có thể loại tháng Một nhưng vẫn cần xét **ba leaf regions của tháng Hai**, vì WHERE chưa xác định region.

### 6.3. Chỉ lọc theo region

```sql
SELECT COUNT(*)
FROM partition_levels_lab.events
WHERE region = 'SOUTH';
```

Khi không có điều kiện event_at, query không thể biết tháng nào để bỏ ở tầng đầu. Nó có thể phải xét **leaf SOUTH của mọi tháng**. Nếu dữ liệu giữ 60 tháng, đây có thể là 60 leaf scans, không phải một leaf scan.

### 6.4. Chỉ lọc tenant_id

```sql
SELECT COUNT(*)
FROM partition_levels_lab.events
WHERE tenant_id = 42;
```

Lab này phân vùng theo event_at rồi region, **không phân vùng theo tenant_id**. Vì vậy điều kiện tenant_id không tự cho phép bỏ các nhánh theo tháng/vùng. Index `(tenant_id,event_at)` trên từng leaf có thể hữu ích, nhưng nhiều leaf vẫn cần được xem xét.

### 6.5. Bảng tình huống

| WHERE | Nhánh có thể bỏ qua theo logic lab | Phạm vi lá còn xét |
| --- | --- | --- |
| Tháng Một AND NORTH | Tháng Hai; SOUTH/OTHER của tháng Một | Một leaf |
| Tháng Hai, không có region | Tháng Một | Ba leaves |
| NORTH, không có thời gian | SOUTH/OTHER ở các tháng | Một leaf mỗi tháng |
| tenant_id=42 | Không có partition key nào tương ứng | Có thể cần tất cả leaves |
| Không có filter | Không có | Toàn cây |
| event_at toàn bộ hai tháng, region IN (NORTH,SOUTH) | Các leaf OTHER | Bốn leaves |

Đây là mô hình logic dựa trên bounds; plan thật có thể có tối ưu khác, runtime pruning và hành vi tùy phiên bản.

---

## 7. Pruning lúc lập kế hoạch và lúc thực thi

PostgreSQL hiện đại có thể loại partition ở những thời điểm khác nhau.

### 7.1. Plan-time pruning

Khi điều kiện chứa giá trị đã biết lúc lập plan:

```sql
WHERE event_at >= TIMESTAMPTZ '2026-01-01 00:00:00+00'
  AND event_at <  TIMESTAMPTZ '2026-02-01 00:00:00+00'
  AND region = 'NORTH'
```

planner thường có cơ sở loại các partition không phù hợp ngay trong plan.

Một `EXPLAIN` có thể chỉ thể hiện scan trên leaf được giữ lại.

### 7.2. Execution-time pruning

Với prepared statements và parameter binding:

```sql
PREPARE count_events (
    TIMESTAMPTZ, TIMESTAMPTZ, TEXT
) AS
SELECT COUNT(*)
FROM partition_levels_lab.events
WHERE event_at >= $1
  AND event_at <  $2
  AND region = $3;
```

Chạy:

```sql
EXPLAIN (ANALYZE, BUFFERS)
EXECUTE count_events(
    TIMESTAMPTZ '2026-01-01 00:00:00+00',
    TIMESTAMPTZ '2026-02-01 00:00:00+00',
    'NORTH'
);

DEALLOCATE count_events;
```

Tùy cách PostgreSQL chọn custom/generic plan và phiên bản, pruning có thể xảy ra ở thời điểm tạo plan hoặc khi executor có parameter value. Các dấu hiệu thường được xem gồm:

- Những partition không hiện trong plan do đã prune sớm.
- `Subplans Removed` trong một số dạng plan.
- Các subplans có thể xuất hiện nhưng không thực thi (chẳng hạn `never executed` hoặc `loops=0`).
- Số partition thực tế được scan.

### 7.3. Không coi generic plan là không thể pruning

Generic plan có thể chưa biết giá trị parameter cụ thể lúc lập kế hoạch, nhưng execution-time pruning có thể loại partition sau khi nhận parameter.

Đổi lại, planner vẫn có thể đã thực hiện một số công việc với tập partition lớn khi xây generic plan. Vì vậy chi phí **planning** và số partition **thực sự scan** là hai đại lượng khác nhau.

### 7.4. Pruning theo tham số từ JOIN

Trong một số kế hoạch, điều kiện trên partition key phụ thuộc vào giá trị từ phía ngoài của Nested Loop. PostgreSQL có thể prune các nhánh khi tham số thay đổi lúc thực thi, thay vì quét toàn bộ cây mỗi lần.

Nhưng không phải mọi JOIN/filter đều cho phép loại partition ở execution time. Hãy dựa vào plan thực tế thay vì suy đoán.

---

## 8. Điều kiện có biểu thức làm pruning khó hơn

Để partition pruning hiệu quả trên `RANGE(event_at)`, query nên biểu đạt khoảng thời gian trực tiếp trên cột partition key.

### 8.1. Mẫu thuận lợi

```sql
WHERE event_at >= TIMESTAMPTZ '2026-01-01 00:00:00+00'
  AND event_at <  TIMESTAMPTZ '2026-02-01 00:00:00+00'
```

### 8.2. Mẫu dễ làm mất cơ hội pruning/index

```sql
WHERE (event_at AT TIME ZONE 'UTC')::DATE
      = DATE '2026-01-15'
```

hoặc:

```sql
WHERE DATE_TRUNC(
    'month', event_at AT TIME ZONE 'UTC'
) = TIMESTAMP '2026-01-01 00:00:00'
```

Những điều kiện này tính biểu thức trên cột, và planner không nhất thiết suy ra được RANGE bound của partition key raw `event_at`.

Nếu mục tiêu là ngày 15/1 UTC:

```sql
WHERE event_at >= TIMESTAMPTZ '2026-01-15 00:00:00+00'
  AND event_at <  TIMESTAMPTZ '2026-01-16 00:00:00+00'
```

thường rõ ràng hơn, đồng thời thân thiện với index B-tree trên timestamp.

### 8.3. Múi giờ nghiệp vụ

“Nửa đêm Việt Nam” khác mốc UTC. Với ngày 15/1 theo `Asia/Ho_Chi_Minh`, có thể xác định:

```sql
WHERE event_at >= TIMESTAMPTZ '2026-01-15 00:00:00+07'
  AND event_at <  TIMESTAMPTZ '2026-01-16 00:00:00+07'
```

Trong hệ thống có DST, phải tính **hai ranh giới ngày theo timezone nghiệp vụ**, không cộng cứng 24 giờ cho mọi ngày.

Điều kiện mốc được tính trước rồi so sánh raw partition key vẫn giúp PostgreSQL có cơ sở pruning theo thời gian.

---

## 9. Thiết kế ngược: HASH/LIST tenant trước, RANGE thời gian sau

Không bắt buộc luôn RANGE ở tầng gốc. Một hệ thống có thể dùng:

```text
HASH(tenant_id)                      -- tầng 1
   |
   +-- bucket 0
   |      +-- RANGE(event_at)         -- tầng 2
   |           +-- Jan
   |           +-- Feb
   |
   +-- bucket 1
          +-- RANGE(event_at)
               +-- Jan
               +-- Feb
```

Một ví dụ DDL riêng:

```sql
CREATE TABLE tenant_events (
    tenant_id BIGINT NOT NULL,
    event_at TIMESTAMPTZ NOT NULL,
    event_id BIGINT NOT NULL,
    payload JSONB NOT NULL
) PARTITION BY HASH (tenant_id);

CREATE TABLE tenant_events_h0
PARTITION OF tenant_events
FOR VALUES WITH (MODULUS 2, REMAINDER 0)
PARTITION BY RANGE (event_at);

CREATE TABLE tenant_events_h1
PARTITION OF tenant_events
FOR VALUES WITH (MODULUS 2, REMAINDER 1)
PARTITION BY RANGE (event_at);

CREATE TABLE tenant_events_h0_2026_01
PARTITION OF tenant_events_h0
FOR VALUES FROM ('2026-01-01 00:00:00+00')
             TO   ('2026-02-01 00:00:00+00');

CREATE TABLE tenant_events_h1_2026_01
PARTITION OF tenant_events_h1
FOR VALUES FROM ('2026-01-01 00:00:00+00')
             TO   ('2026-02-01 00:00:00+00');
```

Đoạn này minh họa cấu trúc, không phải phần bắt buộc của lab chính. Nếu muốn INSERT nhiều tháng, phải tạo thêm RANGE leaves tương ứng cho mỗi hash bucket.

### 9.1. Thứ tự tầng có ảnh hưởng gì?

Với workload chủ yếu:

```sql
WHERE event_at >= ...
  AND event_at < ...
  AND tenant_id = ...
```

cả hai thứ tự có thể giúp pruning đến một số leaf nhỏ.

Nhưng nếu query thường **chỉ lọc ngày**:

- RANGE thời gian trước: có thể cắt các tháng rất rõ, nhưng vẫn xét các subpartitions dưới tháng được chọn.
- HASH tenant trước: phải xem nhiều hash buckets để tìm khoảng ngày trong từng bucket, rồi cắt các tháng con.

Nếu query thường **chỉ lọc tenant**:

- HASH tenant trước: có thể cắt các bucket không phù hợp, nhưng vẫn cần các tháng con của bucket được chọn.
- RANGE thời gian trước: phải đi qua nhiều tháng, rồi tìm bucket tenant tương ứng dưới từng tháng.

### 9.2. Chọn dựa trên workload

Cần đo:

- Tỷ lệ queries có time range.
- Tỷ lệ queries có tenant_id.
- Truy vấn xuyên tất cả tenants nhưng trong một tuần.
- Truy vấn một tenant trên nhiều năm.
- Retention theo tháng.
- Mức độ cô lập VACUUM/index rebuild mong muốn.
- Chi phí tạo/xóa partition hàng tháng.

Nếu retention theo tháng là mục tiêu quan trọng, **RANGE thời gian ở tầng ngoài** có lợi về mặt vòng đời: tháo/bỏ một nhánh tháng có thể loại toàn bộ các leaves của kỳ đó. Thứ tự ngược lại có thể buộc thao tác trên nhiều hash buckets khi hết hạn một tháng.

---

## 10. Số partition tăng theo tích các tầng

Với hai tầng đều chia đều:

\[
N_{\text{leaf}} = N_{\text{level1}} \times N_{\text{level2}}
\]

Với ba tầng:

\[
N_{\text{leaf}} = N_1 \times N_2 \times N_3
\]

Nếu số con mỗi node không đều, tổng đúng là cộng số leaves của từng nhánh, không luôn dùng một tích đơn giản.

### 10.1. Bảng ví dụ

| Tầng một | Tầng hai | Số lá | Nếu có 3 index/lá |
| --- | --- | ---: | ---: |
| 6 tháng | 3 vùng | 18 | 54 index lá |
| 12 tháng | 8 hash buckets | 96 | 288 |
| 24 tháng | 16 hash buckets | 384 | 1.152 |
| 36 tháng | 32 hash buckets | 1.152 | 3.456 |
| 60 tháng | 32 hash buckets | 1.920 | 5.760 |
| 36 tháng | 2.000 tenant LIST | 72.000 | 216.000 |

Số liệu chỉ mô tả quy mô đối tượng, **không phải benchmark hay ngưỡng giới hạn chính thức**. PostgreSQL có thể làm việc với số partition lớn trong những điều kiện phù hợp, nhưng chi phí phụ thuộc phiên bản, query, RAM, hardware, number of indexes và tần suất DDL.

### 10.2. Một tầng nữa có thể gây bùng nổ

Giả sử:

```text
36 tháng
x 16 hash buckets theo tenant
x 4 loại sự kiện
= 2.304 leaf partitions
```

Nếu thêm loại sự kiện chỉ để cô lập VIEW/CLICK/PURCHASE, liệu query có thực sự lọc `event_type` đủ thường xuyên để lợi ích vượt chi phí 4 lần số lá?

Nếu không, index trên event_type hoặc một partial index có thể là phương án ít đối tượng hơn.

### 10.3. Không có con số thần kỳ “dưới X partition luôn tốt”

Một cây vài nghìn leaves có pruning rất tốt và query chủ yếu vào một tháng có thể vận hành khác hẳn cây vài trăm leaves mà mọi query quét toàn bộ.

Phải đánh giá:

- Số lá **trong cây**.
- Số lá **còn sau pruning** cho mỗi query chính.
- Số index mỗi lá.
- Số transaction/statement đồng thời.
- DDL, vacuum và analyze frequency.
- Memory/catalog/lock overhead.
- Thời gian lập plan so với thời gian executor đọc dữ liệu.

---

## 11. Chi phí thứ nhất: thời gian lập kế hoạch truy vấn

Planner cần xem điều kiện, partition bounds, statistic và những đường truy cập khả dĩ. Với nhiều partition, quá trình xây plan có thể tốn CPU/bộ nhớ đáng kể ngay cả khi phần lớn partition được prune.

### 11.1. Planning Time và Execution Time

```sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT
    COUNT(*),
    SUM(amount)
FROM partition_levels_lab.events
WHERE event_at >= TIMESTAMPTZ '2026-01-01 00:00:00+00'
  AND event_at <  TIMESTAMPTZ '2026-02-01 00:00:00+00'
  AND region = 'NORTH';
```

Đọc hai phần:

```text
Planning Time: ...
Execution Time: ...
```

Với query rất chọn lọc có Execution Time ngắn, Planning Time có thể trở thành tỷ lệ lớn của tổng latency nếu cây partition quá lớn hoặc query phức tạp.

### 11.2. Một query quét một lá vẫn có thể có chi phí metadata

Pruning hiệu quả giúp giảm công việc executor, nhưng không nhất thiết triệt tiêu hoàn toàn việc planner và cache hệ thống phải quản lý cây lớn. Không đánh giá chỉ bằng số heap pages đọc; đo cả planning time.

### 11.3. Khi truy vấn chạy quá ngắn và quá nhiều lần

Một API gọi hàng nghìn query/giây, mỗi query chỉ đọc vài rows, có thể bị chi phí lập plan và metadata lặp lại đáng kể. Prepared statements và plan caching có thể giúp theo contract nhưng không xóa toàn bộ chi phí phụ thuộc số partition; generic/custom plans lại có những đánh đổi riêng về pruning.

### 11.4. Không nên tạo partition mỗi phút mà chưa đo

Nếu giữ 30 ngày với partition mỗi phút:

```text
30 ngày × 24 giờ × 60 phút = 43.200 partitions
```

Chỉ riêng tầng thời gian đã lớn. Nếu subpartition thêm 8 buckets:

```text
43.200 × 8 = 345.600 leaves
```

Hãy so với partition theo ngày hoặc tháng cùng index thời gian, vì nhiều query không cần physical table mới mỗi phút để lọc được vài giây dữ liệu.

---

## 12. Chi phí thứ hai: metadata, system catalogs và relcache

Mỗi partition là một relation có metadata PostgreSQL phải quản lý. Các thông tin liên quan nằm trong các catalog như:

- `pg_class`: relation.
- `pg_inherits`: liên kết cha–con của inheritance/partitioning.
- `pg_partitioned_table`: metadata partitioned relation.
- `pg_index` và các catalog liên quan index.
- `pg_attribute`, `pg_constraint` và các thành phần schema.

### 12.1. Nhiều đối tượng hơn, không chỉ nhiều dữ liệu nhỏ hơn

Một leaf có thể có:

- Relation heap.
- Index relations.
- Các thông tin thống kê.
- TOAST relation/index khi cần theo storage.
- Relcache/catcache entries được backend dùng.
- Locks khi statement/DDL tham chiếu.
- File hoặc forks liên quan trên storage.

Không được suy ra 1.000 partitions = đúng 1.000 filesystem files; mỗi relation và fork/index có cách lưu trữ riêng và có thể sinh nhiều file segments.

### 12.2. Tác động lên cache

Backend PostgreSQL cần tra cứu/bộ nhớ cho descriptors, metadata và plans. Khi số partition tăng, áp lực relcache/catcache có thể tăng và tạo công việc metadata đáng kể trên những phiên sử dụng cây lớn.

Đây không nhất thiết là một chi phí đơn giản tuyến tính cho mọi query; mức tăng phụ thuộc patterns truy cập, pruning, phiên bản và trạng thái cache.

### 12.3. Catalog DDL liên tục

Tạo, attach, detach hoặc drop partition liên tục tạo thay đổi catalog. Nếu hàng nghìn tenant mỗi ngày tạo một bảng con, workload DDL cũng trở thành một phần hiệu năng cần quản lý.

Tách “chi phí SELECT trên dữ liệu” khỏi “chi phí quản trị schema” để đánh giá toàn hệ thống.

---

## 13. Chi phí thứ ba: số index tăng theo số partition lá

Giả sử cây có 1.152 lá và bảng cha có ba index logic. Tùy cấu trúc, PostgreSQL cần các index vật lý tương ứng trên từng leaf.

```text
1.152 leaves
x 3 indexes/leaf
= 3.456 index relations của leaves
```

Những index này:

- Cần disk và metadata.
- Cần được duy trì khi INSERT/UPDATE/DELETE trên leaf liên quan.
- Có thể cần VACUUM/index cleanup.
- Cần statistics và đôi khi REINDEX/bảo trì.
- Tạo thêm đối tượng cho attach/detach và backup/restore.

### 13.1. Index trên parent không phải global index vật lý

```sql
CREATE INDEX idx_events_tenant_time
ON partition_levels_lab.events(tenant_id, event_at);
```

Đây là index declaration qua cây partitioned table; các index leaf thực thi truy cập trên từng partition.

Không suy luận rằng PostgreSQL có một global B-tree chứa tất cả `tenant_id` từ mọi tháng để tìm một tenant trong O(log N) và bỏ mọi bước truy cập partition khi không có event_at/region.

### 13.2. Truy vấn theo cột không phải partition key

Ví dụ:

```sql
WHERE event_id = 12345
```

nếu chỉ có primary key bao gồm `(event_at,region,event_id)`, query không có đủ time/region để prune; còn index key order chưa chắc thuận lợi để tìm bằng event_id đơn lẻ.

Có thể thêm local index trên event_id, nhưng query vẫn phải xét nhiều partitions nếu không có cách tìm partition từ ID.

Ở mô hình này, nếu thường xuyên truy cập sự kiện theo event_id **không biết ngày**, cần cân nhắc bảng tra cứu id→partition keys, thay partition key, hoặc dữ liệu được tổ chức theo access pattern khác.

### 13.3. Global uniqueness không tự xuất hiện

Nếu mỗi leaf có `UNIQUE(event_id)`, cùng event_id vẫn có thể tồn tại ở hai leaves khác nhau vì không có một unique check xuyên lá đơn giản từ các local index đó.

Đây là rủi ro correctness, không chỉ hiệu năng. Cơ chế khóa duy nhất toàn cây của PostgreSQL declarative partitioning có điều kiện về việc bao gồm partition keys, kể cả các tầng subpartition.

### 13.4. Chỉ mục trên leaf có thể khác nhau không?

Trong thực hành nâng cao có thể có sự khác nhau về các index bổ sung trên các leaves, nhưng việc thiếu thống nhất khiến query plans khó đoán và maintenance phức tạp. Nếu truy vấn chính dùng cùng pattern qua mọi tháng, nên có index policy nhất quán trừ khi có lý do đã đo được.

---

## 14. Chi phí thứ tư: khóa và số relation tham gia transaction

Một query hoặc DDL có thể cần relation locks trên những relation liên quan. Với cây lớn, đặc biệt thao tác DDL, maintenance hoặc query chạm nhiều leaves, số lock/object cần xử lý có thể tăng.

### 14.1. max_locks_per_transaction không phải giới hạn số partition cứng

Tham số `max_locks_per_transaction` ảnh hưởng kích thước bảng lock dùng chung; nó **không có nghĩa một transaction chỉ được dùng đúng từng ấy relations** hay đặt ra “số partition tối đa”.

Tuy nhiên, workload cần khóa rất nhiều relations cùng lúc có thể gây áp lực lên shared lock memory. Việc giải quyết cần xem số connections/transactions, kiểu lock, mức DDL, indexes và tham số hệ thống.

### 14.2. Quan sát locks theo relation

Một ví dụ điều tra trên lab:

```sql
SELECT
    l.pid,
    l.mode,
    l.granted,
    l.relation::REGCLASS AS relation_name
FROM pg_locks AS l
WHERE l.locktype = 'relation'
  AND l.relation IN (
      SELECT relid
      FROM pg_partition_tree(
          'partition_levels_lab.events'::REGCLASS
      )
  )
ORDER BY l.pid, l.relation, l.mode;
```

Kết quả phản ánh các sessions đang hoạt động tại thời điểm xem, không phải một con số cố định cho mọi query.

### 14.3. DDL cần quản trị cẩn thận

Một số lệnh tạo partition trực tiếp bằng `CREATE TABLE ... PARTITION OF` có thể yêu cầu lock mạnh trên parent. `ATTACH PARTITION` với bảng đã tạo sẵn có chiến lược lock khác và thường có thể giảm một số ảnh hưởng đến parent, nhưng vẫn cần lock, validation và quản lý index/constraint.

Không thực hiện hàng loạt thay đổi cây partition trong thời gian cao điểm mà không thử lock behavior trên phiên bản PostgreSQL thật.

---

## 15. Chi phí thứ năm: autovacuum, ANALYZE và statistics theo partition

Mỗi partition lá có dữ liệu thực và thống kê/bảo trì tương ứng.

### 15.1. Các leaf được bảo trì riêng

Một leaf có nhiều UPDATE/DELETE có thể tạo dead tuples và cần VACUUM. Một leaf lịch sử chỉ đọc có thể có nhu cầu vacuum thấp hơn nhưng vẫn cần xem transaction age/freeze khi phù hợp.

Phân vùng có thể giúp bảo trì cục bộ, nhưng với hàng nghìn leaves, số đối tượng cần theo dõi tăng lên.

### 15.2. Autovacuum threshold trên các bảng nhỏ

Với quá nhiều partitions nhỏ, một số leaf có thể chưa đạt ngưỡng autovacuum theo chính sách đang dùng; vài leaf rất nóng lại cần vacuum thường xuyên. Cần đánh giá:

- Tốc độ ghi trên từng partition.
- `n_dead_tup` ước lượng.
- `last_autovacuum`, `last_autoanalyze`.
- Ngưỡng scale factor và threshold.
- XID age và chính sách freeze.
- Tài nguyên autovacuum workers và cost limits.

Không áp một cấu hình autovacuum chung mà giả định mọi leaf có mức ghi giống nhau.

### 15.3. ANALYZE parent và child statistics

Tùy phiên bản, kế hoạch và cách PostgreSQL thu thập thống kê, planner có thể cần số liệu ở cả partition leaves và thống kê kế thừa/tổng thể của parent. Đặc biệt, một số phiên bản không tự chạy ANALYZE trên partitioned parent giống bảng lưu rows thông thường, vì parent không lưu tuple.

Trong workload thay đổi lớn, cần lên lịch `ANALYZE` phù hợp:

```sql
ANALYZE partition_levels_lab.events;
```

Lệnh này có ý nghĩa trên cây phân vùng và thống kê mà planner dùng; không nên chỉ nhìn `n_live_tup` của parent rồi cho rằng parent không cần statistics.

### 15.4. Xem thống kê theo leaves

```sql
SELECT
    s.schemaname,
    s.relname,
    s.n_live_tup,
    s.n_dead_tup,
    s.last_vacuum,
    s.last_autovacuum,
    s.last_analyze,
    s.last_autoanalyze
FROM pg_stat_user_tables AS s
WHERE s.schemaname = 'partition_levels_lab'
ORDER BY s.relname;
```

Các bộ đếm có độ trễ/ước lượng và không đồng nghĩa con số hiện thời chính xác đến từng tuple. Parent partitioned table có thể có giá trị thống kê khác leaf vì nó không trực tiếp lưu rows.

### 15.5. Nhiều leaf chưa chắc nhanh hơn VACUUM một bảng lớn

Chia nhỏ có thể giúp công việc VACUUM cục bộ hơn, nhưng tổng overhead khởi động/lập lịch/quản lý nhiều relation và index vẫn có thể tăng. So sánh toàn workload thay vì chỉ duration của một VACUUM trên leaf.

---

## 16. Chi phí thứ sáu: backup, restore, replication và monitoring

Phân vùng nhiều tầng ảnh hưởng vòng đời hệ thống, không chỉ SQL executor.

### 16.1. Backup và restore

Với hàng nghìn leaves và indexes:

- Có nhiều đối tượng schema/catalog cần restore.
- Có thể tăng overhead tạo/rebuild indexes.
- Restore cần giữ đúng quan hệ parent–child và constraints.
- Nhiều đối tượng nhỏ có thể làm vận hành khác với một số ít đối tượng lớn.

Dung lượng dữ liệu không đổi nghĩa backup/restore time không đổi. Đừng tuyên bố một sơ đồ có cùng tổng row count sẽ có cùng tốc độ restore.

### 16.2. Physical replication

Physical standby cần replay WAL cho những thay đổi relation và DDL phù hợp. Việc tạo partition/index liên tục có thể tăng WAL và metadata activity; overhead phụ thuộc workload.

### 16.3. Logical replication

Logical replication có những quy tắc về publication, partitioned tables, row routing và replica identity theo phiên bản/cấu hình. Khi dùng partitioned parent và subpartitions, phải kiểm tra cách publication và subscriber xử lý dữ liệu, tên bảng, default partition, khóa định danh và DDL synchronization.

Không mặc định publication tự tạo partition mới ở subscriber theo mọi cấu hình. DDL trên primary thường cần quy trình quản trị schema tương ứng ở subscriber.

### 16.4. Monitoring cardinality

Nếu hệ thống có 2.000 leaves, dashboard giám sát có thể cần tổng hợp theo cây/tháng, thay vì hiển thị hàng nghìn dòng raw stats mỗi lần. Đồng thời phải giữ khả năng phát hiện một vài leaves bị skew/hot.

---

## 17. Chi phí thứ bảy: độ phức tạp vận hành DDL

Thêm một tháng trong cấu trúc hai tầng không chỉ là một câu CREATE TABLE nếu mỗi tháng có nhiều subpartitions.

### 17.1. Tạo trước partition tháng Ba

```sql
CREATE TABLE partition_levels_lab.events_2026_03
PARTITION OF partition_levels_lab.events
FOR VALUES FROM ('2026-03-01 00:00:00+00')
             TO   ('2026-04-01 00:00:00+00')
PARTITION BY LIST (region);

CREATE TABLE partition_levels_lab.events_2026_03_north
PARTITION OF partition_levels_lab.events_2026_03
FOR VALUES IN ('NORTH');

CREATE TABLE partition_levels_lab.events_2026_03_south
PARTITION OF partition_levels_lab.events_2026_03
FOR VALUES IN ('SOUTH');

CREATE TABLE partition_levels_lab.events_2026_03_other
PARTITION OF partition_levels_lab.events_2026_03
DEFAULT;
```

Các index/constraints kế thừa theo cơ chế partitioning cũng cần được kiểm tra. Với cây thực tế có 32 hash leaves mỗi tháng, job tạo tháng mới cần tạo và xác nhận đủ 32 leaves.

### 17.2. Không tạo mỗi partition cùng lúc với INSERT đầu tiên

Nếu application tự chạy DDL khi thiếu partition trong đường ghi hot path:

- Nhiều requests có thể cùng cố tạo partition.
- DDL lock wait làm request latency tăng.
- Cần xử lý tình huống trùng CREATE/collision.
- Vấn đề quyền DDL xuất hiện trong API runtime.
- Tạo tháng mới có thể có chi phí index/catalog và dễ race.

Nên **precreate trước kỳ vận hành** bằng job có kiểm soát, lưu tiến độ, giám sát, và xác minh cây đã đủ leaves trước khi dữ liệu tới.

### 17.3. Partition creation automation cần idempotent

Một job tạo partition hàng tháng nên:

1. Xác định kỳ và timezone chuẩn.
2. Tính ranh giới FROM/TO chính xác.
3. Kiểm tra partition đã tồn tại và đúng bounds.
4. Tạo node trung gian và các leaves chưa có.
5. Kiểm tra index/constraints/policies theo thiết kế.
6. Ghi nhận thành công và cảnh báo nếu thiếu lá.
7. Không tự tạo vô hạn partitions do input ngày không hợp lệ.

`IF NOT EXISTS` nếu dùng ở bước DDL có thể tránh lỗi tên trùng, nhưng **không chứng minh object hiện có đúng cấu trúc/bounds**. Phải xác nhận metadata khi job vận hành cần tính đúng.

---

## 18. ATTACH PARTITION với bảng được tạo sẵn

Một phương án vận hành là **tạo và chuẩn bị bảng trước**, rồi ATTACH vào cây khi sẵn sàng. Điều này có thể cho phép load/index dữ liệu trên bảng riêng trước khi gắn vào parent.

Ví dụ khái niệm ở mức một partition tháng:

```sql
-- Chỉ minh họa cấu trúc; bảng đã chuẩn bị phải đúng schema,
-- constraints, bound và index yêu cầu.

ALTER TABLE partition_levels_lab.events
ATTACH PARTITION partition_levels_lab.prepared_month
FOR VALUES FROM ('2026-04-01 00:00:00+00')
             TO   ('2026-05-01 00:00:00+00');
```

Trong cây thực tế, `prepared_month` cần được tạo là partitioned table theo LIST(region) với các leaves phù hợp và thỏa ràng buộc của parent. Đoạn mã trên **không thể chạy trực tiếp trong lab** vì prepared_month chưa được tạo; nó minh họa điểm gắn metadata sau chuẩn bị.

### 18.1. ATTACH có thể phải kiểm tra dữ liệu

Nếu bảng chuẩn bị có sẵn rows, PostgreSQL cần bảo đảm tất cả hàng nằm trong partition bound và constraints phù hợp. Nếu không có constraint hợp lệ để chứng minh điều đó, việc ATTACH có thể phải **scan dữ liệu** để xác nhận.

Với nhiều leaves, validation và locks có thể đáng kể. Cần thử trên staging với dữ liệu cùng quy mô.

### 18.2. DEFAULT partition làm attach phức tạp hơn

Nếu parent có DEFAULT partition chứa những hàng sau này thuộc phạm vi tháng mới, việc ATTACH tháng có thể cần xem/validate và di chuyển hoặc xử lý những hàng đó; không thể giả định PostgreSQL sẽ âm thầm chuyển toàn bộ rows từ DEFAULT sang partition mới.

Đây là một lý do nhiều hệ thống time-series thích **tạo trước RANGE partitions** và xử lý dữ liệu ngoài phạm vi bằng cơ chế ứng dụng/quarantine rõ ràng.

### 18.3. Lock behavior tùy lệnh

`CREATE TABLE ... PARTITION OF` và `ATTACH PARTITION` không có cùng đặc tính khóa. Một số thao tác yêu cầu khóa mạnh trên parent hoặc partition, còn việc có DEFAULT partition và bảng đã chứa dữ liệu có thể phát sinh khóa/scan thêm.

Không chép một mẹo “ATTACH không chặn ghi” thành cam kết tuyệt đối; phải xem PostgreSQL phiên bản đang chạy, cấu trúc cây và concurrency.

---

## 19. DETACH và retention: lợi thế của RANGE ở tầng ngoài

Một hệ thống giữ dữ liệu 24 tháng. Khi tháng cũ hết hạn, phương án xóa từng hàng:

```sql
DELETE FROM partition_levels_lab.events
WHERE event_at >= TIMESTAMPTZ '2026-01-01 00:00:00+00'
  AND event_at <  TIMESTAMPTZ '2026-02-01 00:00:00+00';
```

có thể tạo nhiều dead tuples, WAL và vacuum work nếu tháng có hàng tỷ rows.

Nếu thời gian là partition key tầng gốc, có thể **detach cả nhánh tháng**:

```sql
-- Chỉ minh họa thao tác retention, KHÔNG chạy nếu còn cần dữ liệu.
ALTER TABLE partition_levels_lab.events
DETACH PARTITION partition_levels_lab.events_2026_01;
```

Sau detach, nhánh tháng Một không còn nằm dưới parent nhưng dữ liệu trong các bảng của nhánh vẫn tồn tại theo quy tắc DDL. Bước archive/drop tiếp theo phải được thiết kế cẩn thận.

### 19.1. Vì sao detach subtree có ích?

Nếu mỗi tháng có 32 hash leaves, detach partition trung gian tháng đó cho phép xử lý cả **subtree 32 leaves** như một đơn vị vòng đời, thay vì điều khiển từng lá riêng cho retention.

### 19.2. Không dùng DROP CASCADE tùy tiện

Sau khi detach, nếu quyết định xóa hẳn dữ liệu, phải kiểm tra:

- Retention policy và nghĩa vụ lưu trữ.
- Backup/PITR.
- Foreign keys hoặc các object tham chiếu.
- Subscriber/replication.
- Có cần export/archive không.
- Hệ quả với audit và báo cáo lịch sử.

Lệnh DROP ở production có thể làm mất dữ liệu vĩnh viễn theo khả năng khôi phục thực tế. Không xem detach/drop như thao tác cleanup vô hại.

### 19.3. DETACH CONCURRENTLY

PostgreSQL có biến thể `DETACH PARTITION CONCURRENTLY` trên các phiên bản hỗ trợ, với điều kiện/giới hạn riêng (ví dụ transaction block, DEFAULT partition và một số cấu trúc cây). Không coi nó luôn khả dụng hoặc luôn nhanh hơn.

Trong bất kỳ chiến dịch retention nào, cần kiểm tra lock behavior và kế hoạch rollback nếu job bị ngắt.

---

## 20. DEFAULT partition: cứu INSERT hay che thiếu partition?

Có thể tạo DEFAULT partition ở tầng RANGE để nhận những hàng không nằm trong ranges đã khai báo.

Ví dụ khái niệm:

```sql
CREATE TABLE some_events_default
PARTITION OF some_events DEFAULT;
```

Lợi ích:

- Tránh INSERT thất bại ngay khi thời gian nằm ngoài các partitions có sẵn.
- Hữu ích làm vùng quarantine cho dữ liệu muộn/tương lai trong những hệ thống được thiết kế phù hợp.

Nhược điểm:

- Dữ liệu có thể tích tụ do job tạo partition bị lỗi.
- Dữ liệu theo thời gian không còn nằm ở nhánh mong đợi.
- Khi tạo partition chính thức, cần xử lý data/validation từ DEFAULT.
- Query không lọc rõ hoặc planner chưa loại được DEFAULT có thể tốn thêm chi phí.
- Khi DEFAULT của một tầng cũng là partitioned table, việc routing/maintenance phức tạp hơn.

### 20.1. DEFAULT không tự chuyển dữ liệu

Khi thêm partition mới, PostgreSQL không có nghĩa vụ tự phân loại toàn bộ data nằm trong DEFAULT rồi di chuyển nó đến leaf mới theo kỳ như một job ETL hoàn chỉnh. Phải thiết kế migration theo đúng constraint và transaction, tránh trùng/mất rows.

### 20.2. DEFAULT theo từng tầng

Trong lab:

- Không có DEFAULT RANGE ở parent.
- Mỗi tháng có DEFAULT LIST cho region.

Điều này có nghĩa hàng tháng Ba không vào được dù region='NORTH'; còn hàng tháng Một region='CENTRAL' vào leaf `_other`.

Phải xác định lỗi routing xảy ra ở **tầng nào**, không gọi mọi lỗi “thiếu partition chung”.

---

## 21. UPDATE partition key có thể di chuyển hàng

Nếu UPDATE thay `event_at` từ tháng Một sang tháng Hai, bản ghi có thể phải **di chuyển từ leaf cũ sang leaf mới** theo cơ chế partition routing của PostgreSQL.

Ví dụ trong lab:

```sql
BEGIN;

UPDATE partition_levels_lab.events
SET event_at = TIMESTAMPTZ '2026-02-15 12:00:00+00'
WHERE event_id = 9000001
  AND event_at = TIMESTAMPTZ '2026-01-17 10:30:00+00'
  AND region = 'NORTH'
RETURNING tableoid::REGCLASS AS new_leaf, event_at, region;

ROLLBACK;
```

Trong thực tế, UPDATE partition key sang partition khác có hành vi nội bộ tương đương loại hàng khỏi partition cũ và chèn vào partition mới; có thể tác động trigger, foreign keys, indexes, WAL và concurrency.

### 21.1. UPDATE region cũng có thể chuyển leaf

Ở cây RANGE → LIST, đổi `region='NORTH'` thành `'SOUTH'` trong cùng tháng cũng yêu cầu thay đổi leaf chứa hàng.

### 21.2. Không lạm dụng thay partition key

Các cột như `event_at`, `tenant_id` và `region` nên có ý nghĩa ổn định nếu được dùng làm partition key. Một workload liên tục UPDATE partition key có thể chịu chi phí routing/di chuyển lớn hơn so với cập nhật cột không dùng phân vùng.

### 21.3. Concurrency và row movement

Khi có UPDATE/DELETE đồng thời trên hàng đang chuyển partition, một số tình huống có thể trả lỗi serialization/concurrent modification theo quy tắc PostgreSQL. Ứng dụng cần transaction boundary và retry thích hợp, không tự giả định mọi row movement là một UPDATE in-place đơn giản.

---

## 22. Ràng buộc PRIMARY KEY, UNIQUE và nhiều tầng

Một trong các hạn chế quan trọng của declarative partitioning là khả năng enforce uniqueness trên **toàn cây** dựa vào tính không giao nhau của partition bounds cùng các local indexes.

### 22.1. Vì sao khóa phải bao gồm partition keys?

Lab dùng:

```sql
PRIMARY KEY (event_at, region, event_id)
```

Trong cây RANGE(event_at) → LIST(region), hai cột partition key xuất hiện trong PRIMARY KEY, giúp hệ thống biết một tổ hợp key không thể hợp lệ ở hai leaf khác nhau nếu bounds phân vùng nhất quán.

### 22.2. Khóa chỉ chứa event_id là vấn đề

Nếu viết:

```sql
PRIMARY KEY (event_id)
```

trên cây phân vùng theo event_at và region, PostgreSQL không thể dùng local indexes đơn thuần để đảm bảo event_id duy nhất xuyên mọi leaf khi event_at/region không tham gia khóa.

Không phải vì `event_id` thiếu “đủ tính duy nhất” theo nghiệp vụ, mà vì cấu trúc physical partition và thiếu global uniqueness index tổng quát làm việc kiểm tra xuyên lá cần cơ chế bổ sung.

### 22.3. Partition keys bằng biểu thức

Một số kiểu partition key là biểu thức thay vì cột trực tiếp có các giới hạn riêng khi khai báo UNIQUE/PRIMARY KEY trên partitioned table. Nếu hệ thống cần unique constraint toàn cây, hãy thiết kế cột partition key tường minh và kiểm tra điều kiện phiên bản thay vì dùng biểu thức phức tạp rồi trông đợi unique check tự hoạt động.

### 22.4. Foreign key

PostgreSQL hiện đại hỗ trợ nhiều dạng foreign key liên quan partitioned tables, nhưng cần xét:

- Khóa được tham chiếu có thực sự unique/primary key hợp lệ không?
- Bao gồm những partition keys nào?
- Thao tác detach/drop ảnh hưởng reference như thế nào?
- DML/constraint maintenance có chi phí ra sao?
- Phiên bản PostgreSQL đang dùng có hỗ trợ trường hợp cụ thể không?

Một reference theo `event_id` đơn lẻ không thể tự dựa vào PK ba cột nếu không có cơ chế unique khác.

---

## 23. Partition-wise join: lợi ích và rủi ro

Nếu hai bảng lớn được partition tương thích theo cùng khóa và các bounds phù hợp, PostgreSQL có thể có cơ hội thực hiện **partition-wise join** thay vì JOIN trên các tập ghép lớn.

Mô hình ý niệm:

```text
Table A January  JOIN  Table B January
Table A February JOIN  Table B February
...
Append kết quả
```

### 23.1. Cần partition tương thích

Nếu A phân vùng theo `event_at` còn B phân vùng theo `tenant_id`, JOIN không tự phân rã thành các cặp cùng tháng. Tương thích partition keys/bounds và điều kiện JOIN quyết định khả năng tối ưu.

### 23.2. Hai tầng làm bài toán phức tạp hơn

Với RANGE tháng + HASH tenant:

- Hai bảng phải có thiết kế partition tương thích nếu kỳ vọng join từng cặp leaves.
- Có thể có nhiều join nodes tương ứng hàng trăm/thousands leaves.
- Planner phải xem nhiều khả năng và memory cost.

### 23.3. Cấu hình

PostgreSQL có planner setting như `enable_partitionwise_join`. Việc bật/tắt tùy hệ thống và phiên bản; không mặc định bật sẽ nhanh.

Partition-wise join có thể tăng số nodes trong plan và bộ nhớ dùng trong planning/execution. Một cây quá nhiều partitions có thể làm lợi ích I/O bị ăn mòn bởi overhead lập kế hoạch.

---

## 24. Partition-wise aggregate: tổng hợp theo từng nhánh

Báo cáo:

```sql
SELECT
    region,
    COUNT(*) AS events,
    SUM(amount) AS amount
FROM partition_levels_lab.events
GROUP BY region;
```

PostgreSQL có các tối ưu partition-wise aggregation trong những điều kiện hỗ trợ, cho phép aggregate phần dữ liệu theo partitions rồi kết hợp kết quả nếu ngữ nghĩa yêu cầu.

### 24.1. Full và partial aggregation

- **Full partition-wise aggregate** có thể áp dụng khi grouping keys làm các nhóm không thể trải qua nhiều partitions, theo điều kiện tương thích.
- **Partial aggregation** có thể tính trạng thái ở từng partition rồi hoàn tất bên trên khi một group trải qua nhiều partitions.

Điều kiện chính xác còn tùy aggregate functions, partition keys, query shape và planner/version.

### 24.2. Ví dụ region trải qua nhiều tháng

Trong cây RANGE tháng → LIST region, mỗi region có dữ liệu ở nhiều tháng. Nếu muốn tổng theo region toàn lịch sử, cần cộng các kết quả region của nhiều tháng; không thể lấy một leaf NORTH rồi tuyên bố đó là NORTH mọi thời gian.

### 24.3. Cẩn thận với COUNT(DISTINCT)

Không phải mọi aggregate đều có thể phân rã bằng cách cộng kết quả con. Ví dụ khách hàng xuất hiện ở cả tháng Một và Hai:

```text
COUNT(DISTINCT customer_id) tháng Một = 1
COUNT(DISTINCT customer_id) tháng Hai = 1

COUNT(DISTINCT customer_id) của hai tháng = 1,
không phải 2.
```

Dùng partial aggregates phải tuân thủ ngữ nghĩa của từng aggregate. Không tự roll up distinct counts bằng SUM.

### 24.4. Số partition lớn làm aggregate memory tăng?

Partition-wise aggregate có thể tạo nhiều partial aggregate nodes và trạng thái riêng, tăng memory demand theo số partition và grouping keys. Không bật cho mọi workload mà không đo planning time, work_mem/spill và concurrent queries.

---

## 25. Query không pruning: mặt trái của chia nhỏ

Một truy vấn thường gặp:

```sql
SELECT
    event_type,
    COUNT(*) AS events,
    SUM(amount) AS amount
FROM partition_levels_lab.events
GROUP BY event_type;
```

Không có `event_at` hoặc `region` trong WHERE. PostgreSQL phải đọc dữ liệu từ **mọi leaf chứa hàng**, hoặc dựa trên một summary khác nếu hệ thống thiết kế.

### 25.1. Quét toàn cây không tự nhanh hơn một bảng

Với một bảng lớn, executor có thể dùng một Seq Scan/Parallel Seq Scan; với nhiều partitions, có thể phải xây Append/Parallel Append và xử lý nhiều relations/indexes.

Khi partition quá nhỏ, overhead per-partition và kế hoạch nhiều nodes có thể tốn chi phí đáng kể.

### 25.2. Truy vấn theo event_id

```sql
WHERE event_id = 12345
```

không có partition keys. Nếu không có lookup khác, PostgreSQL có thể cần kiểm tra nhiều leaves. Chia thời gian càng nhỏ càng làm kiểu truy vấn lookup không có thời gian trở nên khó tối ưu nếu workload cần nó thường xuyên.

### 25.3. Khi nào index tốt hơn thêm partition?

Nếu bài toán chủ yếu là:

```sql
WHERE tenant_id = 42
  AND event_type = 'PURCHASE'
```

trên toàn lịch sử, một index phù hợp hoặc summary/query design khác có thể đáng xem hơn việc tạo thêm hàng nghìn list partitions theo tenant.

Cần xét selectivity, query frequency, write cost và khả năng prune theo các partition keys đã có.

---

## 26. Đo tổng số relation và kích thước thực

Một số hàm PostgreSQL hữu ích cho việc quan sát cây.

### 26.1. Số partition lá

```sql
SELECT
    COUNT(*) FILTER (WHERE isleaf) AS leaves,
    COUNT(*) FILTER (WHERE NOT isleaf) AS internal_nodes
FROM pg_partition_tree(
    'partition_levels_lab.events'::REGCLASS
);
```

### 26.2. Tổng dung lượng leaves

```sql
SELECT
    PG_SIZE_PRETTY(
        SUM(PG_TOTAL_RELATION_SIZE(relid))::BIGINT
    ) AS all_leaf_size,
    COUNT(*) AS leaf_count
FROM pg_partition_tree(
    'partition_levels_lab.events'::REGCLASS
)
WHERE isleaf;
```

Khi bảng parent là partitioned table, nó không trực tiếp chứa heap rows như leaves. Không lấy `pg_relation_size(parent)` rồi tưởng đó là kích thước toàn bộ cây.

### 26.3. Kích thước theo lá

```sql
SELECT
    relid::REGCLASS AS leaf_name,
    PG_SIZE_PRETTY(PG_TABLE_SIZE(relid)) AS table_size,
    PG_SIZE_PRETTY(PG_INDEXES_SIZE(relid)) AS indexes_size,
    PG_SIZE_PRETTY(PG_TOTAL_RELATION_SIZE(relid))
        AS total_size
FROM pg_partition_tree(
    'partition_levels_lab.events'::REGCLASS
)
WHERE isleaf
ORDER BY PG_TOTAL_RELATION_SIZE(relid) DESC;
```

### 26.4. Tìm phân phối lệch

Một số leaves có thể lớn hơn hẳn:

- Một region có rất nhiều traffic.
- Một tenant “hot” đi vào cùng hash bucket với nhiều tenant khác.
- Tháng sale có cao điểm giao dịch.
- Dữ liệu IMPORT cũ/late events dồn vào DEFAULT.
- Một leaf có bloat/index growth khác thường.

Việc tính partition count không đủ; cần đo **kích thước và tốc độ ghi từng lá**.

---

## 27. Theo dõi catalog và chỉ mục của cây

### 27.1. Xem index của từng leaf

```sql
SELECT
    t.relid::REGCLASS AS leaf_table,
    i.indexrelid::REGCLASS AS index_name
FROM pg_partition_tree(
    'partition_levels_lab.events'::REGCLASS
) AS t
JOIN pg_index AS i
  ON i.indrelid = t.relid
WHERE t.isleaf
ORDER BY t.relid, i.indexrelid;
```

Nếu hệ thống có rất nhiều leaves, câu truy vấn sẽ cho thấy tổng số index relations có thể lớn như thế nào.

### 27.2. Đếm index theo leaf

```sql
SELECT
    t.relid::REGCLASS AS leaf_table,
    COUNT(i.indexrelid) AS index_count
FROM pg_partition_tree(
    'partition_levels_lab.events'::REGCLASS
) AS t
LEFT JOIN pg_index AS i
  ON i.indrelid = t.relid
WHERE t.isleaf
GROUP BY t.relid
ORDER BY index_count DESC, t.relid;
```

Không cần mỗi leaf có số index giống nhau trong mọi hệ thống; nhưng độ lệch có thể báo một kỳ mới thiếu index hoặc một kỳ cũ giữ index không còn cần thiết.

### 27.3. Catalog activity cũng cần quan sát

Nhiều DDL, lock waits hoặc lượng object tăng đột biến có thể cho thấy việc sinh partition vượt kế hoạch. Cần theo dõi tiến độ tạo partition, không chỉ query latency.

---

## 28. So sánh một tầng và hai tầng bằng thí nghiệm

Một benchmark có ý nghĩa phải so hai thiết kế với cùng dữ liệu/semantics.

### 28.1. Giả thuyết

Thiết kế A:

```text
RANGE tháng
  -> 24 leaf partitions
```

Thiết kế B:

```text
RANGE tháng
  -> HASH tenant 16 buckets mỗi tháng
  -> 384 leaves
```

Các giả thuyết:

- Query một tháng và một tenant: B có thể đọc ít dữ liệu ở leaf hơn, nhưng có nhiều relation hơn.
- Query một tháng, mọi tenant: A có thể đơn giản hơn vì chỉ một leaf tháng; B có thể đọc 16 leaves của tháng đó.
- Query một tenant, mọi tháng: B có thể chọn một bucket mỗi tháng; A cần chỉ mục tenant trong từng tháng hoặc scan phù hợp.
- Query toàn lịch sử: B có thể chịu overhead nhiều relation hơn.
- Retention theo tháng: cả hai có thể detach nhánh tháng nếu RANGE là tầng ngoài, nhưng B phải quản lý nhiều leaves bên dưới.
- DDL và index count: B nhiều đối tượng hơn.

### 28.2. Cần giữ các yếu tố công bằng

- Cùng số rows và phân bố dữ liệu.
- Cùng payload và row widths.
- Cùng số lượng/chức năng index tương đương.
- Cùng PostgreSQL version/hardware.
- Cùng cấu hình work_mem, parallelism và stats.
- Cùng tần suất ghi/cạnh tranh.
- Chạy warm-up và nhiều lượt đo.
- Không chỉ đo một truy vấn có lợi cho một phương án.

### 28.3. Đo những gì?

| Chỉ số | Vì sao quan trọng |
| --- | --- |
| Planning Time | Cây lớn có overhead lập plan không? |
| Execution Time | Truy vấn chạy nhanh hơn thật không? |
| Shared buffers hit/read | Có giảm pages truy cập không? |
| Temp blocks/disk | Sort/hash có spill không? |
| Partitions scanned | Pruning hiệu quả đến đâu? |
| Rows removed by filter | Đã giảm input hợp lý chưa? |
| Index footprint | Chi phí storage của index leaves |
| Insert throughput | Routing/index overhead |
| Update/delete throughput | Maintenance và row movement |
| Vacuum/analyze cost | Bảo trì nhiều leaves |
| DDL time/locks | Tạo kỳ mới có ảnh hưởng hoạt động? |
| Memory/CPU | Phần planning và concurrent executions |
| Backup/restore duration | Chi phí vận hành cuối vòng đời |

### 28.4. Một cải thiện cục bộ chưa chắc cải thiện tổng thể

Nếu query tenant/tháng nhanh hơn 10% nhưng 70% workload là tổng báo cáo toàn lịch sử và số relation tăng 16 lần, thiết kế B có thể không đáng.

Không đánh giá một loại truy vấn riêng biệt thay cho workload thực tế.

---

## 29. Prepared statements và plan cache

Ứng dụng JDBC/ORM thường gửi SQL tham số hóa:

```sql
SELECT COUNT(*)
FROM partition_levels_lab.events
WHERE event_at >= $1
  AND event_at < $2
  AND region = $3;
```

PostgreSQL có thể dùng custom plan hoặc generic plan tùy tình huống.

### 29.1. Custom plan

Custom plan biết parameter values tại thời điểm lập plan, có thể tận dụng selectivity/partition bounds cụ thể nhưng phải trả công việc planning cho mỗi lần lập.

### 29.2. Generic plan

Generic plan có thể tiết kiệm chi phí lập plan lặp lại, nhưng không phải lúc nào cũng tối ưu cho các giá trị tham số rất lệch nhau. Execution-time pruning có thể giúp, nhưng không xóa tất cả chi phí planning ban đầu hoặc khác biệt access path.

### 29.3. Không ép plan_cache_mode vô điều kiện

PostgreSQL có setting `plan_cache_mode` trên các phiên bản hỗ trợ để kiểm soát auto/custom/generic trong các thử nghiệm. Tuy nhiên không có cấu hình tốt cho mọi query.

Nếu một tenant có một tỷ hàng còn tenant khác có vài trăm hàng, custom plan và statistics có thể quan trọng. Đo cả P95 trên các tenant có quy mô khác nhau.

---

## 30. Skew dữ liệu và hash buckets

HASH giúp phân phối nhiều tenant vào một số buckets, nhưng không tự đảm bảo mỗi bucket có số rows hoặc mức tải bằng nhau.

### 30.1. Hot tenant

Nếu một tenant tạo 70% toàn bộ events, tenant đó vẫn chủ yếu tập trung trong bucket của mình. Hashing đồng đều các **giá trị khóa** không chia đều **tải của từng giá trị khóa**.

Tăng số bucket có thể cô lập hot tenant với ít tenant khác, nhưng không chia một tenant hot đơn lẻ thành nhiều buckets nếu partition key vẫn là tenant_id.

### 30.2. Điều chỉnh số hash partition không miễn phí

Thay từ 16 lên 32 buckets ở một cấu trúc đang có dữ liệu không phải lúc nào cũng chỉ là đổi cấu hình metadata; có thể cần tạo/attach partitions phù hợp, phân phối lại dữ liệu, xử lý bounds và giữ tính sẵn sàng.

Vì vậy không chọn số hash buckets theo kỳ vọng “tăng sau cũng đơn giản như đổi config” nếu chưa có migration plan.

### 30.3. LIST theo tenant còn phức tạp hơn

Nếu dùng LIST mỗi tenant một partition:

- Onboarding tenant mới có thể cần DDL.
- Tenant rời đi làm vòng đời partition riêng.
- Query xuyên tenants phải xét nhiều relations.
- Catalog/index count tăng theo số tenant.
- Một số tenant cực nhỏ khiến partition thành nhiều bảng trống hoặc vài KB.

Trừ khi yêu cầu vận hành, pháp lý hoặc bảo trì rất đặc thù, thường đáng thử **HASH buckets** hoặc partition thời gian + index tenant trước khi thiết kế một partition riêng cho từng tenant.

---

## 31. Một số lựa chọn thay thế thêm tầng phân vùng

Trước khi tăng cây từ 24 lên 384 leaves, hãy đánh giá những lựa chọn ít đối tượng hơn.

### 31.1. Local B-tree index

Nếu query thường lọc tenant trong một tháng:

```sql
CREATE INDEX idx_events_tenant_time
ON partition_levels_lab.events(tenant_id, event_at);
```

Có thể đủ để truy cập nhanh trong partition tháng mà không cần HASH subpartition.

### 31.2. BRIN cho dữ liệu append theo thời gian

Với relation lớn có tương quan vật lý theo thời gian, BRIN có thể giảm kích thước index và scan ranges phù hợp.

```sql
CREATE INDEX idx_events_time_brin
ON partition_levels_lab.events
USING BRIN (event_at);
```

BRIN không thay được tất cả chức năng của B-tree/HASH subpartition và cần benchmark; nhưng là phương án cần so khi dữ liệu append-heavy.

### 31.3. Partial index

Nếu chỉ một loại sự kiện cần query latency thấp:

```sql
CREATE INDEX idx_events_purchase_time
ON partition_levels_lab.events(event_at)
WHERE event_type = 'PURCHASE';
```

Một partial index theo workload có thể tốt hơn tạo thêm LIST partitions cho mọi event_type nếu lợi ích pruning không đủ.

### 31.4. Summary/materialized view

Nếu query cần tổng số events theo tháng/tenant nhưng chỉ đọc biểu đồ, việc tạo thêm partition không làm `COUNT(*)` trở thành phép đọc tức thì. Một bảng summary hoặc materialized view có thể hợp hơn cho reports lặp lại, với contract refresh/delta/idempotency rõ ràng.

### 31.5. Retention sớm hoặc archive

Nếu 90% queries chỉ xem sáu tháng gần nhất, giữ nhiều năm trong cùng cây có thể không cần thiết. Archive older data ra nơi phù hợp hoặc chính sách retention có thể giảm số partition tích cực, đồng thời cải thiện chi phí catalog/planning/maintenance.

---

## 32. Thiết kế số lượng partition dựa trên kích thước và truy vấn

Không có “kích thước partition chuẩn” dùng được cho mọi hệ thống. Nên trả lời:

1. Một tháng có bao nhiêu rows/GB?
2. Tốc độ INSERT/UPDATE/DELETE mỗi tháng ra sao?
3. Query hay đọc một ngày, một tháng hay nhiều năm?
4. Có bao nhiêu tenants/regions và phân bố lệch?
5. Index mỗi leaf cần bao nhiêu?
6. VACUUM/REINDEX/backup retention cần xử lý một đơn vị dữ liệu lớn đến đâu?
7. Số tháng cần online là bao nhiêu?
8. PostgreSQL version/hardware có mức Planning Time và lock/memory overhead như thế nào?

### 32.1. Ví dụ định lượng

Giả sử 24 tháng, mỗi tháng 100 GB và query chủ yếu theo tháng.

Phương án A: 24 leaf tháng, mỗi leaf ~100 GB.

Phương án B: 24 × 8 hash buckets = 192 leaves, mỗi leaf trung bình ~12,5 GB **nếu phân bố tương đối đều**.

B có thể giúp:

- Một query tenant thu hẹp tới bucket tương ứng.
- Bảo trì index của từng bucket có phạm vi nhỏ hơn.
- Cô lập một phần hot/cold workloads.

Nhưng phải trả:

- Nhiều relation/index hơn 8 lần ở tầng lá.
- Query toàn tháng phải đọc cả tám buckets.
- DDL/thống kê/vacuum quản trị nhiều đối tượng hơn.
- Planning/memory/locks có thể tăng.

Nếu query tháng toàn tenant chiếm 95% và vẫn quét toàn 100 GB, phân chia 8 buckets không tự giảm lượng dữ liệu đọc.

### 32.2. Tránh chọn số partition theo kích thước file đơn lẻ

Một bảng 100 GB không tự động “quá lớn”. Nếu có index tốt, workload ổn định, VACUUM/backup đủ nhanh, một leaf 100 GB có thể vận hành tốt hơn 100 leaves 1 GB.

Quyết định cần dựa trên cả **latency, throughput, kế hoạch bảo trì và chi phí metadata**, không chỉ số GB mỗi bảng.

---

## 33. Checklist vận hành partition nhiều tầng

Một job tự tạo partitions cần coi cây như cấu trúc dữ liệu có invariants.

### 33.1. Trước khi mở tháng mới

- Tính FROM/TO theo timezone chuẩn, half-open.
- Xác nhận không overlap/gap ngoài ý muốn.
- Tạo parent partition cho tháng.
- Tạo đúng số HASH/LIST subpartitions.
- Kiểm tra constraints và indexes trên leaves.
- Xác nhận còn dung lượng filesystem/tablespace.
- Xem quyền truy cập, RLS, trigger và replication setup.
- Dùng job idempotent, lock coordination phù hợp.
- Không để application tự tạo partition trong đường request nóng.

### 33.2. Trong kỳ hoạt động

- Theo dõi INSERT routing errors.
- Theo dõi số rows mỗi leaf.
- Theo dõi skew/hot partitions.
- Theo dõi query plans và pruning hiệu quả.
- Theo dõi planning time.
- Theo dõi VACUUM/ANALYZE và freeze age.
- Theo dõi relation/index sizes.
- Cảnh báo khi DEFAULT tích tụ nhiều rows.
- Kiểm soát số partition/DDL growth.
- Kiểm tra replication lag và backup health.

### 33.3. Khi kỳ hết hạn

- Xác nhận retention và archive.
- Kiểm tra FK, logic downstream và audit.
- Lập kế hoạch detach/drop với locks phù hợp.
- Kiểm tra không còn query cần dữ liệu cũ.
- Ghi nhận metadata thay đổi.
- Chạy thống kê/bảo trì cần thiết sau thay đổi lớn.
- Xác nhận report không lấy mất dữ liệu cần thiết.

---

## 34. Các lỗi thiết kế thường gặp

| Sai lầm | Hệ quả | Hướng xử lý |
| --- | --- | --- |
| Tạo partition cho từng tenant không giới hạn | Bùng nổ relation/catalog/index count | Thử HASH bucket hoặc index tenant |
| Chia thời gian theo phút cho mọi hệ thống | Quá nhiều partitions nhỏ | Chọn granularity dựa trên retention/query |
| Thêm ba tầng vì “càng nhỏ càng nhanh” | Nhiều nodes, plan/maintenance đắt | Chỉ thêm tầng khi đo được lợi ích |
| Quên tổng số leaves là tích các tầng | Đánh giá thấp chi phí | Tính leaf count trước DDL |
| Query không lọc partition key | Không pruning, scan nhiều leaves | Viết predicate hoặc cân nhắc index/schema |
| Bao partition key bằng hàm trong WHERE | Có thể mất pruning/sargability | Half-open raw range |
| Dùng BETWEEN tới 23:59:59 cho cả ngày | Bỏ microseconds | >= start và < next_day |
| Dùng UTC cho ngày kinh doanh địa phương không đúng | Sai phạm vi thời gian | Tính mốc theo timezone nghiệp vụ |
| Nhầm pruning với index-only access | Nghĩ một leaf = O(1) | Đo index/heap scan trong leaf |
| Chỉ tạo index ở một số leaves vô ý | Plan không nhất quán | Index policy và kiểm tra cây |
| Nghĩ parent có global index | Lookup theo ID không prune vẫn khó | Hiểu local indexes/lookup strategy |
| PK chỉ chứa event_id khi partition keys khác | Không enforce uniqueness xuyên leaves | Thiết kế composite key/registry |
| Mặc định FK luôn đơn giản | Chi phí và ràng buộc phụ thuộc keys/DDL | Kiểm tra schema/version |
| Tin rằng PostgreSQL tự tạo partition khi INSERT | INSERT lỗi lúc sang tháng | Precreate và giám sát |
| Dùng DEFAULT rồi quên theo dõi | Dữ liệu lạc kỳ, attach phức tạp | Quarantine/monitor/move policy |
| Chạy DDL tạo lá khi request cao điểm | Lock waits/latency | Job nền có lịch và lock planning |
| Coi ATTACH miễn phí, không scan | Có thể validate rows/constraints | Chuẩn bị CHECK/index, thử staging |
| Drop subtree khi chưa archive | Mất dữ liệu | Retention approval/backup |
| UPDATE partition key liên tục | Row movement/WAL/index overhead | Chọn key ổn định |
| Chỉ đo Execution Time | Bỏ Planning Time tăng | Đo cả planning/execution |
| Bật partitionwise join/aggregate vô điều kiện | Plan/memory nở | Benchmark theo query |
| Nghĩ COUNT DISTINCT cộng được từ leaves | Sai số khách duy nhất | Distinct toàn phạm vi/mergeable state |
| Nghĩ hash phân phối đều workload | Hot tenant vẫn có thể lệch | Đo skew và hot keys |
| Tăng hash buckets không cần migration | Thao tác khó khi dữ liệu đã có | Thiết kế repartition plan |
| Tắt autovacuum vì có nhiều leaves | Bloat/freeze risk | Tuning theo workload |
| Chỉ ANALYZE leaves mà quên parent stats khi cần | Planner estimate sai | Thống kê phù hợp cây |
| Quá nhiều index cho mỗi leaf | Disk/WAL/backup/DDL tăng | Rà soát index usage |
| Dùng một benchmark cache nóng | Kết luận sai tổng workload | Lặp đo, xem concurrency |
| Nhầm một query tenant với workload tổng | Chọn sai layout | Tính tỷ trọng query patterns |
| Không xem restore/replication | Bất ngờ khi vận hành | Thử backup/restore và HA |
| Không kiểm tra số relation tự tạo | Metadata tăng âm thầm | Alert trên leaf/index count |

---

## 35. Bài tập thực hành

### Bài 1 — Giải thích các cấp của cây

Vẽ cây RANGE(event_at) → LIST(region) với 12 tháng, mỗi tháng 4 vùng. Có bao nhiêu nodes trung gian, leaves và relation bảng nếu không tính index?

### Bài 2 — Tính explosion của ba tầng

Một hệ thống giữ 36 tháng, mỗi tháng có 16 hash buckets tenant, mỗi bucket chia thêm 3 loại sự kiện. Tính số lá và số physical indexes nếu có bốn index mỗi lá.

### Bài 3 — Tạo hai cấp bằng DDL

Dùng schema lab tạo tháng Ba với LIST region giống tháng Một/Hai. Vì sao chỉ tạo `events_2026_03 PARTITION BY LIST(region)` mà chưa tạo lá không đủ để INSERT?

### Bài 4 — Quan sát tableoid

INSERT một hàng NORTH tháng Một, một hàng SOUTH tháng Hai, một hàng CENTRAL tháng Hai. Dùng `tableoid::REGCLASS` xác định partition lá của từng hàng.

### Bài 5 — pg_partition_tree

Viết query liệt kê `relid`, `parentrelid`, `isleaf`, `level`. Đếm lá/nút trung gian trước và sau khi thêm tháng Ba.

### Bài 6 — Pruning cả hai tầng

Viết query tháng Một/NORTH và chạy EXPLAIN. Những leaves nào có thể bị loại và vì sao?

### Bài 7 — Chỉ lọc thời gian

Viết query tháng Hai không có region. PostgreSQL có thể prune những gì? Vì sao vẫn cần xét ba region leaves?

### Bài 8 — Chỉ lọc region

Viết query region SOUTH mà không có điều kiện thời gian. Vì sao phải xét SOUTH ở nhiều tháng và tại sao số leaf scans tăng theo retention months?

### Bài 9 — Tenant không phải partition key

Viết query chỉ có tenant_id=42 trong lab. Giải thích vì sao index tenant trên leaf có thể giúp nhưng không tự loại tất cả leaf khác.

### Bài 10 — Half-open range

Viết WHERE cho ngày 1/2/2026 theo UTC và theo múi giờ Asia/Ho_Chi_Minh. Vì sao sử dụng cast `event_at::DATE` có thể kém thuận lợi cho pruning?

### Bài 11 — Prepared statement

Tạo PREPARE nhận start/end/region. Chạy EXPLAIN EXECUTE. Giải thích các dấu hiệu plan-time và execution-time pruning, và vì sao generic plan có thể khác custom plan.

### Bài 12 — HASH trước RANGE

Thiết kế cây hai buckets tenant, mỗi bucket có tháng Một/Hai. Với query chỉ lọc tenant, chỉ lọc thời gian và lọc cả hai, phân tích leaf subsets còn lại.

### Bài 13 — Chọn thứ tự tầng

Một hệ thống 90% queries có time range và 10% chỉ tenant, retention xóa cả tháng. Chọn một thứ tự tầng phù hợp và nêu những giả định cần benchmark.

### Bài 14 — PK/UNIQUE

Vì sao PRIMARY KEY(event_id) trên cây partition theo event_at và region không đơn giản enforce uniqueness toàn cây? Thiết kế một composite key hợp lệ và mô tả cách enforce event_id toàn cục nếu nghiệp vụ cần.

### Bài 15 — Index multiplier

Với 48 tháng × 12 hash leaves, mỗi leaf cần 5 indexes, tính số leaf indexes. Nêu ít nhất bốn chi phí vận hành liên quan.

### Bài 16 — Global lookup

Ứng dụng thường nhận event_id nhưng không biết timestamp hoặc region. Vì sao truy vấn chỉ WHERE event_id=? có thể chậm trên cây RANGE→LIST? Đề xuất giải pháp.

### Bài 17 — Planner overhead

Chạy EXPLAIN (ANALYZE, BUFFERS) và ghi Planning Time/Execution Time cho query một leaf và query toàn cây. Vì sao một leaf scan nhanh không chứng minh cây cực lớn không có metadata overhead?

### Bài 18 — Dung lượng theo leaf

Dùng `pg_partition_tree` và `pg_total_relation_size` để tính kích thước các leaf. Tìm leaf lớn nhất và bàn luận về skew.

### Bài 19 — Metadata/index count

Dùng `pg_index` kết hợp `pg_partition_tree` để đếm index mỗi leaf. Nếu tháng mới có ít index hơn tháng cũ, những nguyên nhân nào cần điều tra?

### Bài 20 — Relation locks

Dùng `pg_locks` để quan sát relation locks của một transaction đọc hoặc DDL trong lab. Vì sao max_locks_per_transaction không phải giới hạn số partitions chính xác?

### Bài 21 — Autovacuum

Một leaf hiện tại có hàng triệu UPDATE, còn nhiều leaf lịch sử không thay đổi. Đề xuất cách quan sát `n_dead_tup`, `last_autovacuum` và freeze age theo leaf.

### Bài 22 — Parent statistics

Sau khi nạp lượng lớn dữ liệu vào cây, chạy ANALYZE trên parent. Vì sao thống kê cả cây và từng leaf đều có thể quan trọng cho query planner?

### Bài 23 — Missing partition

INSERT một hàng tháng Ba khi chưa tạo RANGE tháng Ba. Loại lỗi nào xảy ra? Vì sao PostgreSQL không tự tạo tháng mới?

### Bài 24 — DEFAULT

Giải thích sự khác biệt giữa DEFAULT ở tầng LIST của tháng Một và DEFAULT ở tầng RANGE gốc. Rủi ro nào xuất hiện nếu DEFAULT chứa rất nhiều dữ liệu sai kỳ?

### Bài 25 — ATTACH validation

Một bảng staging chứa nhiều rows muốn ATTACH làm partition tháng mới. Vì sao PostgreSQL có thể phải scan? Chuẩn bị constraint chứng minh bounds có lợi gì?

### Bài 26 — Retention

Phân vùng 24 tháng × 8 hash buckets. Nếu muốn xóa tháng cũ, lợi thế của RANGE tháng ở tầng ngoài là gì? Cần kiểm tra gì trước DETACH/DROP?

### Bài 27 — UPDATE partition key

UPDATE event_at từ tháng Một sang tháng Hai. Vì sao thao tác có thể gây row movement và index/WAL overhead? Hãy quan sát `RETURNING tableoid::REGCLASS` trong transaction lab rồi rollback.

### Bài 28 — Partition-wise join

Hai bảng A và B cùng partition theo (tháng, tenant bucket). Điều kiện JOIN/partition alignment nào cần để có cơ hội partition-wise join? Chi phí nào tăng khi có 1.000 leaves?

### Bài 29 — Partition-wise aggregate

Báo cáo COUNT theo tenant trên tất cả tháng. Vì sao phải tổng hợp các tháng lại? Nếu thay COUNT bằng COUNT(DISTINCT customer_id), tại sao cộng counts của từng tháng sai?

### Bài 30 — Full scan trên hàng nghìn leaves

Một query tổng số rows toàn lịch sử không có WHERE trên partition key. Vì sao chia 48 tháng × 32 buckets có thể không giúp so với 48 leaves tháng? Đề xuất một phương án summary nếu dashboard được gọi nhiều lần.

### Bài 31 — Hot tenant

Một tenant đóng góp 80% writes. HASH(tenant_id) với 32 buckets có chia đều tải không? Đề xuất cách đo và thiết kế thay thế.

### Bài 32 — DDL automation

Viết pseudocode job tạo tháng kế tiếp cho cây RANGE→HASH 16 buckets, xác nhận bounds, indexes, idempotency và alert nếu thiếu partition.

### Bài 33 — So sánh index với subpartition

Một query thường dùng event_at và tenant_id. Hãy so phương án 24 leaf theo tháng + B-tree tenant với phương án 24 × 8 hash leaves. Những benchmark nào cần trước khi quyết định?

### Bài 34 — Kế hoạch thử nghiệm

Thiết kế workload gồm bốn query: (time+tenant), time only, tenant only, full history. Đo Planning Time, Execution Time, Buffers, partitions scanned, locks và index size.

### Bài 35 — Phân vùng hay kiến trúc khác?

Một hệ thống có hàng chục nghìn tenant, mỗi tenant vài trăm sự kiện/ngày, cần retention theo tháng và API query by tenant+time. Vì sao LIST partition per tenant nguy hiểm? Đề xuất một cây hợp lý và phương án theo dõi pruning.

### Bài 36 — Vấn đề backup/restore

Nếu từ 100 partitions tăng lên 5.000 partitions và mỗi leaf có nhiều index, những công việc backup, restore, analyze, replication và monitoring nào có thể thay đổi? Hãy đề xuất tiêu chí kiểm thử trước migration.

### Bài 37 — Migration từ đơn tầng sang nhiều tầng

Một bảng có 24 monthly partitions đã hoạt động. Hãy lập kế hoạch chuyển sang RANGE(month)→HASH(tenant) có downtime tối thiểu theo khả năng hệ thống, bao gồm data movement, locks, constraints, dual-write/verification nếu dùng, rollback và validation. Không cần viết script production; tập trung vào rủi ro.

### Bài 38 — Tổng hợp quyết định

Một doanh nghiệp đề xuất chia 60 tháng × 64 buckets × 5 event types. Tính số leaves và indexes nếu có bốn indexes mỗi leaf. Đặt câu hỏi cần trả lời trước khi chấp thuận phương án, gồm workload, retention, global lookup, planning, disk, vacuum và DDL locks.

---

## 36. Checklist trước khi chọn số lượng và số tầng partition

| Câu hỏi | Bằng chứng cần có |
| --- | --- |
| Vì sao cần phân vùng? | Pruning, retention, maintenance hoặc workload cụ thể |
| Tầng ngoài chia theo gì? | Cột khóa, pattern filter, retention |
| Tầng trong chia theo gì? | Query patterns và skew |
| Vì sao cần tầng thứ hai? | Lợi ích so với index ở lá đơn tầng |
| Có bao nhiêu tháng giữ online? | Retention requirement |
| Có bao nhiêu subpartitions mỗi tháng? | Chọn theo tải, không theo “càng nhiều càng tốt” |
| Tổng leaf count là bao nhiêu? | Tích các tầng hoặc tổng thực |
| Tổng index count? | Indexes/leaf × leaves |
| Query có partition key trong WHERE? | Tỷ lệ truy vấn thực tế |
| Hai tầng có prune cùng lúc? | EXPLAIN với parameters thật |
| Có query không lọc thời gian? | Global scans/lookups |
| Có global uniqueness requirement? | PK, UNIQUE, event ID |
| Có FK phức tạp? | Design và retention compatibility |
| Có UPDATE partition key? | Row movement và concurrency |
| Có DEFAULT partition? | Monitoring và move policy |
| Có precreate partition không? | Automation trước khi đến kỳ |
| DDL có chạy giờ cao điểm? | Lock test và lịch bảo trì |
| Có attach staging data? | Constraint validation và scan cost |
| Có retention bằng detach/drop? | Backup, FK, archiving, audit |
| Có tenant cực nóng? | Skew và hash bucket distribution |
| Planning Time có tăng? | EXPLAIN nhiều query |
| Execution Time có giảm? | EXPLAIN trong workload tương đương |
| Có cần index riêng nữa không? | Local index per leaf và disk |
| Có VACUUM/ANALYZE theo leaf? | Stats và XID age |
| Parent stats có phù hợp? | ANALYZE và estimate |
| Có lock memory pressure? | pg_locks/concurrency/max_locks config |
| Có partition-wise optimization? | enable_partitionwise*, cost tradeoff |
| Workload tổng hợp toàn lịch sử? | Summary/materialized view |
| Có read replica/logical replication? | Schema/DDL và lag |
| Backup/restore có chịu được nhiều objects? | Restore rehearsal |
| Có test trên dữ liệu thật? | Distribution, row width, indexes |
| Có benchmark nhiều lần, tải đồng thời? | P95, CPU, I/O, memory |
| Có monitoring số leaves và indexes? | Alert khi tăng bất thường |
| Có kế hoạch thay đổi số hash buckets? | Repartition/migration |
| Có thể giảm granularity? | Tháng thay ngày/phút nếu phù hợp |
| Có đo tổng chi phí sở hữu? | Query + DDL + storage + operations |

## Kết luận

**Phân vùng nhiều tầng** giúp PostgreSQL kết hợp nhiều mục tiêu tổ chức dữ liệu, ví dụ **RANGE theo thời gian** để giới hạn lịch sử và **LIST/HASH theo vùng hoặc tenant** để tăng khả năng pruning hoặc cô lập bảo trì. Nhưng mỗi tầng mới làm số partition lá tăng, thường theo tích của số nhánh ở từng tầng.

Cần ghi nhớ:

1. **Partition pruning là lợi ích chính của nhiều truy vấn có điều kiện.** Query phải chứa predicate phù hợp khóa phân vùng ở từng tầng thì mới có cơ hội bỏ tối đa những nhánh không liên quan.
2. **Phân vùng không thay index.** Pruning tìm leaf; index hoặc scan xử lý dữ liệu trong leaf. Một query không lọc partition key vẫn có thể chạm nhiều leaves.
3. **Số partition có chi phí thật.** Mỗi leaf kéo theo metadata, index, stats, locks, autovacuum, DDL, planning và backup/restore overhead.
4. **Không có số leaf tối ưu chung.** Cần đo tỷ trọng queries có/không pruning, Planning Time, Execution Time, I/O, memory và thời gian bảo trì.
5. **Thứ tự tầng phản ánh nghiệp vụ.** RANGE thời gian ở tầng ngoài thường thuận lợi cho retention theo tháng; HASH tenant ở tầng ngoài có thể thuận lợi cho truy cập tenant nếu workload tương ứng.
6. **UNIQUE/PRIMARY KEY xuyên cây có giới hạn.** Không giả định các local indexes đảm bảo uniqueness toàn cục cho key không bao gồm partition keys.
7. **Vận hành là phần của thiết kế.** Precreate đủ subpartitions, quản lý DEFAULT, theo dõi skew, chuẩn bị attach/detach, kiểm tra indexes và thống kê.
8. **Không chia nhỏ chỉ vì có thể.** Nếu một leaf lớn vẫn đọc nhanh bằng index và được VACUUM/backup thuận lợi, việc nhân số leaf chưa chắc đem lại lợi ích.
9. **Các báo cáo toàn lịch sử có thể cần summary.** Partition-wise aggregate không biến mọi COUNT/SUM thành chi phí hằng số.
10. **Benchmark là cơ sở ra quyết định.** So thiết kế một tầng và nhiều tầng trên dữ liệu, tham số, concurrency, retention và cấu hình thật trước khi mở rộng cây.

Một thiết kế phân vùng PostgreSQL tốt không phải thiết kế có nhiều partitions nhất, mà là thiết kế có **số tầng và số lá vừa đủ để giảm lượng dữ liệu phải xử lý, vẫn kiểm soát được chi phí metadata và vận hành lâu dài**.
