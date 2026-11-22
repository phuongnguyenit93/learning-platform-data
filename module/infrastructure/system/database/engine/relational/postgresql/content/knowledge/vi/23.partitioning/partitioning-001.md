# Mục tiêu phân vùng và các trường hợp không phù hợp trong PostgreSQL

Khi một bảng PostgreSQL tăng từ vài trăm nghìn lên hàng trăm triệu hoặc hàng tỷ bản ghi, chúng ta thường nghĩ ngay đến **partitioning (phân vùng bảng)**. Nhưng phân vùng không phải là một nút “tăng tốc mọi truy vấn” và cũng không phải yêu cầu bắt buộc mỗi khi bảng lớn. Một bảng được phân vùng hợp lý có thể giúp truy vấn chỉ đọc một phần dữ liệu, xóa dữ liệu cũ nhanh bằng thao tác quản lý partition và giới hạn phạm vi bảo trì. Ngược lại, phân vùng sai khóa hoặc chia quá nhỏ có thể khiến planner phải xử lý hàng nghìn quan hệ con, mỗi câu INSERT phải định tuyến, thao tác UPDATE phải chuyển hàng giữa partitions và truy vấn không có điều kiện trên partition key trở nên phức tạp hơn.

Ví dụ hai báo cáo cùng truy vấn bảng sự kiện có dữ liệu ba năm:

```sql
-- Báo cáo chỉ cho tháng 10/2026:
SELECT COUNT(*)
FROM events
WHERE occurred_at >= TIMESTAMPTZ '2026-10-01 00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-11-01 00:00+00';

-- Báo cáo toàn thời gian:
SELECT COUNT(*)
FROM events;
```

Nếu `events` được chia theo tháng của `occurred_at`, PostgreSQL có thể **prune** phần lớn partitions cho câu đầu, nhưng vẫn phải xét dữ liệu trên tất cả partitions thích hợp cho câu thứ hai. Nếu ứng dụng chủ yếu tìm theo `event_id` mà không biết ngày, partitioning theo tháng có thể không giúp truy vấn ấy, thậm chí làm nó phải tìm qua nhiều index con.

Vì vậy, trước khi viết `CREATE TABLE ... PARTITION BY ...`, câu hỏi đúng là:

> **Ta muốn tối ưu điều gì và workload có thể loại bỏ một phần lớn các partition ở hầu hết thao tác quan trọng hay không?**

Bài học trình bày mục tiêu thực sự của partitioning, cách chọn RANGE/LIST/HASH, các tình huống phù hợp và không phù hợp, những đánh đổi về chỉ mục, khóa chính, tính duy nhất, JOIN, INSERT/UPDATE/DELETE, VACUUM, replication, planning, rồi một quy trình ra quyết định có ví dụ và bài tập.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích sự khác nhau giữa bảng phân vùng logic và dữ liệu vật lý của các partition.
2. Nêu các mục tiêu đúng của partitioning: **partition pruning**, quản lý **vòng đời dữ liệu**, bảo trì có phạm vi và một số dạng song song hóa/tổ chức workload.
3. Phân biệt **RANGE**, **LIST** và **HASH partitioning** trong PostgreSQL.
4. Đọc sơ đồ thiết kế partition theo thời gian, tenant và hash key.
5. Giải thích vì sao partitioning không thay thế B-tree/BRIN/GIN indexes, statistics hoặc tối ưu SQL.
6. Hiểu khi nào truy vấn không có partition key dẫn đến quét nhiều partitions.
7. Chỉ ra chi phí nhiều partitions: planning, metadata, file descriptors, index/constraint maintenance và operational complexity.
8. Nhận diện giới hạn của **PRIMARY KEY/UNIQUE** trên partitioned table và hệ quả với foreign keys, upsert và định danh nghiệp vụ.
9. Phân tích những thao tác UPDATE làm thay đổi partition key và nguy cơ khi chuyển hàng sang partition khác.
10. Thiết kế lịch tạo partition tương lai, attach/detach, lưu trữ/xóa dữ liệu cũ và default partition có kiểm soát.
11. Đánh giá các giải pháp thay thế: index phù hợp, BRIN, query rewriting, archiving, batching, retention jobs, materialized views hoặc sharding khi thực sự cần.
12. Dùng `EXPLAIN` và số liệu thực để quyết định có nên phân vùng hay không.

## 2. Partitioning trong PostgreSQL là gì?

**Declarative partitioning** cho phép khai báo một bảng cha (*partitioned table*) mà dữ liệu được lưu tại các **partition là những bảng vật lý riêng** theo quy tắc khóa phân vùng. Ứng dụng có thể chạy truy vấn trên bảng cha như một bảng logic.

```text
                         orders  (bảng cha logic)
                                  |
                    PARTITION BY RANGE (created_at)
                                  |
                 +----------------+----------------+
                 |                |                |
                 v                v                v
           orders_2026_09   orders_2026_10   orders_2026_11
           [Sep 01-Oct 01)  [Oct 01-Nov 01)  [Nov 01-Dec 01)
                 |                |                |
              dữ liệu          dữ liệu           dữ liệu
               tháng 9         tháng 10          tháng 11
```

Hàng được định tuyến vào partition dựa trên giá trị partition key. Bảng cha partitioned **không phải một heap chứa tất cả các row như một bảng thường**. Nó giữ định nghĩa và cấu trúc phân vùng, trong khi các partition là nơi lưu dữ liệu.

### 2.1. Một bảng logic, nhiều quan hệ vật lý

Khi đọc:

```sql
SELECT *
FROM orders
WHERE created_at >= TIMESTAMPTZ '2026-10-01 00:00+00'
  AND created_at <  TIMESTAMPTZ '2026-11-01 00:00+00';
```

PostgreSQL có thể chỉ đọc partition tháng 10 nếu partition bounds và điều kiện phù hợp. Đây là **partition pruning**.

Nếu đọc:

```sql
SELECT * FROM orders;
```

truy vấn cần xét dữ liệu trong **mọi partition liên quan** để trả kết quả đầy đủ; không có lý do logic nào để bỏ cả những tháng không được lọc.

### 2.2. Phân vùng không phải sharding mặc định

Một partitioned table thông thường trong một PostgreSQL instance:

- Vẫn cùng hệ quản trị, cùng cluster logic và cùng ranh giới tài nguyên server.
- Có nhiều heap/index vật lý theo từng partition.
- Không tự chia dữ liệu sang nhiều PostgreSQL server độc lập.
- Không tự tạo khả năng mở rộng write throughput tuyến tính theo số máy.

**Sharding** là một kiến trúc phân phối dữ liệu/tải sang các nút khác nhau, cần định tuyến, consistency, transaction và operational plan riêng. Chia bảng thành 12 partitions theo tháng **không phải** đã có 12 database servers.

### 2.3. Phân vùng không tự làm dữ liệu nhỏ đi

Nếu bảng có 100 triệu hàng và chia thành 12 partitions, tổng hàng vẫn là 100 triệu. Indexes con, metadata và các tệp vật lý có thể khiến tổng storage **lớn hơn hoặc khác** bảng ban đầu tùy thiết kế. Partitioning chủ yếu làm cho PostgreSQL **không phải xét những phần không liên quan**, và cho phép thao tác quản trị một phần riêng biệt khi phù hợp.

## 3. Ba chiến lược khai báo: RANGE, LIST và HASH

PostgreSQL hỗ trợ ba hình thức declarative partitioning phổ biến:

| Loại | Quy tắc định tuyến | Workload điển hình | Cần thận trọng |
| --- | --- | --- | --- |
| **RANGE** | Khoảng giá trị có cận dưới và cận trên. | Log, event theo ngày/tháng, dữ liệu theo thời gian, dải số. | Cận phải thường **không bao gồm**; phải tạo partition tương lai. |
| **LIST** | Một tập giá trị được liệt kê. | Region, loại nghiệp vụ, nhóm tenant ổn định. | Cardinality quá cao và thay đổi liên tục tạo nhiều partition. |
| **HASH** | Hàm hash phân bổ theo modulus/remainder. | Phân bố đều dữ liệu theo tenant/customer ID trong số partitions cố định. | Query range theo thời gian thường không prune theo hash ID; đổi số bucket khó hơn. |

### 3.1. RANGE theo tháng

```sql
CREATE TABLE range_orders (
    order_id bigint NOT NULL,
    created_at timestamptz NOT NULL,
    amount numeric(12, 2) NOT NULL
) PARTITION BY RANGE (created_at);

CREATE TABLE range_orders_2026_10
PARTITION OF range_orders
FOR VALUES FROM ('2026-10-01 00:00+00')
TO              ('2026-11-01 00:00+00');
```

Giá trị từ **01/10 00:00 UTC đến trước 01/11 00:00 UTC** đi vào partition tháng 10. Chọn ranh giới theo timezone một cách nhất quán.

### 3.2. LIST theo region

```sql
CREATE TABLE region_orders (
    order_id bigint NOT NULL,
    region text NOT NULL,
    amount numeric(12, 2) NOT NULL
) PARTITION BY LIST (region);

CREATE TABLE region_orders_north
PARTITION OF region_orders
FOR VALUES IN ('north');

CREATE TABLE region_orders_south
PARTITION OF region_orders
FOR VALUES IN ('south');
```

Truy vấn `WHERE region='north'` có thể chỉ cần phần north nếu điều kiện tương thích pruning.

### 3.3. HASH theo customer_id

```sql
CREATE TABLE hash_orders (
    order_id bigint NOT NULL,
    customer_id bigint NOT NULL,
    amount numeric(12, 2) NOT NULL
) PARTITION BY HASH (customer_id);

CREATE TABLE hash_orders_p0
PARTITION OF hash_orders
FOR VALUES WITH (MODULUS 4, REMAINDER 0);

CREATE TABLE hash_orders_p1
PARTITION OF hash_orders
FOR VALUES WITH (MODULUS 4, REMAINDER 1);

CREATE TABLE hash_orders_p2
PARTITION OF hash_orders
FOR VALUES WITH (MODULUS 4, REMAINDER 2);

CREATE TABLE hash_orders_p3
PARTITION OF hash_orders
FOR VALUES WITH (MODULUS 4, REMAINDER 3);
```

Một điều kiện equality trên `customer_id` có thể giúp PostgreSQL chỉ đến hash partition tương ứng. Nhưng không thể suy ra một khoảng `created_at >= ...` tương ứng một hash bucket, vì hash được quyết định từ customer_id.

### 3.4. Subpartitioning

Một partition cũng có thể là partitioned table, chẳng hạn:

```text
orders PARTITION BY RANGE (created_at)
  |
  +-- 2026_10 PARTITION BY HASH (tenant_id)
  |      +-- bucket 0
  |      +-- bucket 1
  |      +-- bucket 2
  |      +-- bucket 3
  |
  +-- 2026_11 PARTITION BY HASH (tenant_id)
         +-- bucket 0
         +-- bucket 1
         +-- bucket 2
         +-- bucket 3
```

Điều này có thể giúp một số workloads vừa lọc thời gian vừa lọc tenant. Nhưng số quan hệ vật lý tăng theo **tích số nhánh**, kéo theo quản trị, planning và bảo trì phức tạp hơn. Không dùng subpartitioning chỉ vì “càng phân nhỏ càng nhanh”.

## 4. Mục tiêu đúng thứ nhất: partition pruning

**Partition pruning** là loại bỏ những partition được chứng minh không thể chứa hàng phù hợp với query.

Ví dụ bảng theo khoảng thời gian:

```sql
SELECT COUNT(*)
FROM range_orders
WHERE created_at >= TIMESTAMPTZ '2026-10-01 00:00+00'
  AND created_at <  TIMESTAMPTZ '2026-11-01 00:00+00';
```

Nếu có 36 partitions tháng, planner/executor có thể chỉ cần đọc partition tháng 10 thay vì xét toàn bộ ba năm dữ liệu.

### 4.1. Pruning không phải index scan

Cần phân biệt hai tầng:

```text
WHERE created_at thuộc tháng 10
                |
                v
     Partition pruning
  bỏ mọi partition ngoài tháng 10
                |
                v
   Quét partition tháng 10:
      - Seq Scan?
      - Index Scan?
      - Bitmap Heap Scan?
      - Index Only Scan?
```

Partition pruning **chọn những bảng con cần xét**. Sau đó planner vẫn cần chọn cách truy cập dữ liệu **bên trong** mỗi partition. Nếu tháng 10 có 30 triệu hàng và query chỉ lấy một đơn theo `order_id`, index trên order_id ở partition vẫn có thể rất quan trọng.

### 4.2. Lợi ích mạnh khi query lọc gần khớp partition key

Với bảng chia theo `created_at`:

```sql
WHERE created_at >= :start_time
  AND created_at < :end_time
```

là mẫu thường dễ tận dụng partition bounds hơn query chỉ lọc:

```sql
WHERE customer_id = :customer_id
```

Nếu `customer_id` không phải partition key, mọi partition tháng đều **có thể** chứa đơn của khách ấy. Pruning theo thời gian không thể bỏ partitions chỉ bằng điều kiện customer_id.

### 4.3. Điều kiện không tương thích partition key

Ví dụ:

```sql
WHERE date_trunc('month', created_at)
    = TIMESTAMPTZ '2026-10-01 00:00+00'
```

Nếu bảng được RANGE partition trực tiếp trên `created_at`, việc bọc cột trong biểu thức có thể khiến PostgreSQL không suy ra được phạm vi partition cần đọc, tùy định nghĩa partition key, kiểu dữ liệu và phiên bản.

Khi ngữ nghĩa yêu cầu tháng UTC, biểu diễn bằng khoảng nửa mở thường rõ hơn:

```sql
WHERE created_at >= TIMESTAMPTZ '2026-10-01 00:00+00'
  AND created_at <  TIMESTAMPTZ '2026-11-01 00:00+00'
```

Không thay điều kiện có timezone nghiệp vụ bằng UTC một cách tùy tiện nếu sản phẩm tính tháng theo múi giờ địa phương; trước hết định nghĩa chính xác ranh giới.

### 4.4. Pruning phụ thuộc predicate, không phụ thuộc số partition

Một bảng chia 120 partitions nhưng query luôn lọc đúng một tháng có thể hoạt động hợp lý. Ngược lại một bảng chỉ chia bốn partitions mà mọi query luôn quét cả bốn có thể không có lợi ích pruning đáng kể. **Số partitions một mình không cho biết truy vấn sẽ nhanh hơn.**

## 5. Mục tiêu đúng thứ hai: quản lý vòng đời và xóa dữ liệu cũ

Đây thường là **lợi ích vận hành rõ ràng nhất** của partitioning theo thời gian.

Giả sử lưu log trong 12 tháng. Nếu dùng bảng thường, xóa 50 triệu hàng cũ:

```sql
DELETE FROM logs
WHERE occurred_at < TIMESTAMPTZ '2025-11-01 00:00+00';
```

có thể tạo nhiều thay đổi MVCC, WAL, dead tuples, vacuum work, index maintenance, khóa và áp lực I/O. Với một partition chỉ chứa dữ liệu đã hết hạn, có thể dùng thao tác quản lý partition để loại bỏ **toàn bộ phần dữ liệu** mà không DELETE từng hàng.

### 5.1. DROP partition cũ

```sql
-- Mẫu minh họa: chỉ khi logs_2025_10 thực sự là partition cũ
-- và dữ liệu đã đủ điều kiện xóa theo chính sách:
-- DROP TABLE logs_2025_10;
```

DROP partition là thao tác DDL, không phải xóa từng tuple, và **không miễn phí về lock hoặc WAL metadata**. Nhưng về mặt cơ chế nó thường tránh được lượng xử lý row-by-row khổng lồ của DELETE.

### 5.2. DETACH để lưu trữ trước khi xóa

Một quy trình retention có thể:

```text
Partition hết hạn
   |
   +-- xác minh retention/legal hold/backup
   |
   +-- DETACH partition khỏi bảng cha
   |
   +-- archive/export nếu cần
   |
   +-- DROP bảng đã tách khi đủ điều kiện
```

`DETACH PARTITION` làm partition thành quan hệ độc lập. Việc tách nó **không tự xóa dữ liệu**; đây là điểm thuận lợi để archiving.

### 5.3. Điều kiện tiên quyết để DROP an toàn

Không được xóa partition chỉ dựa vào tên file:

- Khoảng thời gian đã hết hạn theo chính sách chưa?
- Có đơn hàng, chứng từ hoặc bản ghi cần giữ vì quy định không?
- Có dữ liệu đến trễ hoặc bản ghi được sửa hậu kỳ không?
- Có backup/archival đã kiểm chứng không?
- Có downstream CDC, ETL, báo cáo, foreign key hoặc view phụ thuộc không?
- Có thể rollback hoặc restore được không?

Partitioning giúp **thực thi retention**, nhưng không tự quyết định được retention policy.

### 5.4. Xóa dữ liệu không trùng ranh giới partition

Nếu policy yêu cầu “giữ đúng 90 ngày lăn”, nhưng partitions theo **tháng**, ở ngày 15/11 có thể có một partition tháng 8 chứa cả dữ liệu đã hết hạn lẫn chưa hết hạn theo 90 ngày.

Không thể DROP cả tháng 8 mà vẫn giữ chính xác ngưỡng 90 ngày. Cần chọn granularity thích hợp (ngày/tuần/tháng), phối hợp DELETE cho phần rìa hoặc thay đổi định nghĩa retention có phê duyệt.

### 5.5. Vì sao đây khác VACUUM?

`DELETE` đánh dấu hàng không còn visible theo MVCC, rồi VACUUM mới dọn phiên bản hàng khi an toàn. `DROP` một partition nguyên vẹn là DDL làm quan hệ không còn tồn tại, không cần lần lượt xóa từng hàng bằng MVCC. Vì vậy retention theo ranh giới partition thường dễ dự đoán hơn khi lượng dữ liệu rất lớn.

## 6. Mục tiêu đúng thứ ba: bảo trì và quản trị có phạm vi

Khi bảng lớn được chia thành các partitions đúng ranh giới:

- Có thể ANALYZE partition mới sau ingest lớn.
- Có thể VACUUM những partitions bị UPDATE/DELETE nhiều.
- Có thể xử lý index/bloat của một partition phù hợp kế hoạch.
- Có thể chuyển hoặc archive partition cũ theo chính sách.
- Có thể đánh giá statistic của partition “hot” khác “cold”.
- Có thể lên lịch bảo trì trong một phạm vi thời gian/tenant cụ thể.

### 6.1. Phân biệt hot và cold data

Ví dụ hệ thống orders:

```text
2026-11: cập nhật liên tục    -> hot partition
2026-10: cập nhật vừa phải   -> warm partition
2024-01: gần như bất biến    -> cold partition
```

Việc phân biệt này giúp quyết định:

- Autovacuum/vacuum và ANALYZE cần tập trung ở đâu.
- Index nào cần cho truy vấn lịch sử.
- Khi nào một partition có thể archive.
- Nguồn lực lưu trữ và bảo trì.

Nhưng **partitioning không tự làm những partitions cũ read-only**. Muốn bảo đảm bất biến phải dùng quyền, nghiệp vụ và cơ chế quản trị phù hợp.

### 6.2. Index theo từng partition

PostgreSQL có thể tạo index trên bảng cha để quản lý định nghĩa tương ứng trên các partitions. Từng partition có **index vật lý riêng**; không nên suy luận rằng một B-tree duy nhất bao phủ mọi hàng của mọi partition như bảng thường.

Điều này cho phép phạm vi index nhỏ hơn khi pruning tốt, nhưng có chi phí nhân lên theo số partitions.

### 6.3. Thống kê parent và child

Mỗi partition có thể có phân bố dữ liệu khác nhau, khiến statistics của tháng vừa qua khác các tháng cũ. Planner có thể dùng statistics của partition và của parent tùy loại query. Một số tình huống cần ANALYZE parent chủ động, đặc biệt sau thay đổi lớn ở partitions con.

Không giả định autoanalyze luôn cập nhật đủ mọi thống kê inherited/partitioned parent chỉ vì child đang được ghi liên tục.

### 6.4. Bảo trì phạm vi không đồng nghĩa không còn lock

Thao tác CREATE/ATTACH/DETACH/DROP partition, REINDEX hoặc ALTER cấu trúc vẫn có thể lấy lock ở parent/child và tác động truy cập. Một thiết kế tốt giúp **giới hạn phạm vi dữ liệu**, nhưng không loại bỏ mọi yêu cầu điều phối vận hành.

## 7. Phòng thí nghiệm: bảng sự kiện phân vùng theo tháng

Phần này minh họa **mục tiêu của partitioning** mà không phụ thuộc vào database khác. Mọi thao tác chỉ dành cho cơ sở dữ liệu thực hành; không thực thi trên bảng người dùng thật. Ví dụ dùng declarative partitioning PostgreSQL hiện đại.

### 7.1. Tạo schema và bảng cha

```sql
CREATE SCHEMA IF NOT EXISTS partition_goal_lab;

CREATE TABLE partition_goal_lab.events (
    event_id bigint NOT NULL,
    occurred_at timestamptz NOT NULL,
    tenant_id integer NOT NULL,
    event_type text NOT NULL,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (occurred_at, event_id)
) PARTITION BY RANGE (occurred_at);
```

Chú ý đặc biệt `PRIMARY KEY (occurred_at,event_id)` thay vì `PRIMARY KEY (event_id)`: với bảng partition theo thời gian và các quy tắc PostgreSQL tương ứng, constraint unique/primary key trên parent phải có những cột partition key liên quan để có thể đảm bảo uniqueness mà không có global index xuyên các child theo mô hình thông thường. Phần 16 giải thích kỹ.

### 7.2. Tạo ba partition

```sql
CREATE TABLE partition_goal_lab.events_2026_09
PARTITION OF partition_goal_lab.events
FOR VALUES FROM ('2026-09-01 00:00+00')
TO              ('2026-10-01 00:00+00');

CREATE TABLE partition_goal_lab.events_2026_10
PARTITION OF partition_goal_lab.events
FOR VALUES FROM ('2026-10-01 00:00+00')
TO              ('2026-11-01 00:00+00');

CREATE TABLE partition_goal_lab.events_2026_11
PARTITION OF partition_goal_lab.events
FOR VALUES FROM ('2026-11-01 00:00+00')
TO              ('2026-12-01 00:00+00');
```

Các partition có bounds liên tiếp, không chồng lấn. Vì dùng `timestamptz` với cận UTC tường minh, định nghĩa không phụ thuộc cách session hiển thị ngày giờ tại thời điểm truy vấn.

### 7.3. Nạp 18.000 sự kiện qua bảng cha

```sql
INSERT INTO partition_goal_lab.events (
    event_id, occurred_at, tenant_id, event_type, payload
)
SELECT
    g::bigint,
    CASE
        WHEN g <= 6000 THEN
            TIMESTAMPTZ '2026-09-01 00:00+00'
        WHEN g <= 12000 THEN
            TIMESTAMPTZ '2026-10-01 00:00+00'
        ELSE
            TIMESTAMPTZ '2026-11-01 00:00+00'
    END
    + (((g - 1) % 28) * INTERVAL '1 day')
    + (((g - 1) % 1440) * INTERVAL '1 minute'),
    1 + (g % 10),
    CASE (g % 4)
        WHEN 0 THEN 'view'
        WHEN 1 THEN 'purchase'
        WHEN 2 THEN 'click'
        ELSE 'refund'
    END,
    jsonb_build_object('source', 'lab', 'sequence', g)
FROM generate_series(1, 18000) AS series(g);
```

Thí nghiệm này chỉ nên chạy **một lần trên bảng rỗng**. Nếu chạy lại, primary key trùng và query có thể lỗi. Dữ liệu được sinh theo quy luật; không dùng kết quả thời gian thực thi để suy ra tốc độ của sản phẩm thật.

### 7.4. Xác nhận mỗi sự kiện thuộc partition nào

`tableoid` là system column cho biết OID của quan hệ vật lý chứa row. Dùng `::regclass` để hiển thị tên bảng:

```sql
SELECT
    tableoid::regclass AS physical_partition,
    COUNT(*) AS event_count,
    MIN(occurred_at) AS first_event,
    MAX(occurred_at) AS last_event
FROM partition_goal_lab.events
GROUP BY tableoid
ORDER BY tableoid::regclass::text;
```

Với dữ liệu lab nguyên vẹn, có ba partitions và mỗi partition chứa **6.000 hàng**. `tableoid` giúp nhìn routing thực, không tự chứng minh pruning ở một truy vấn bất kỳ.

### 7.5. Query chỉ một tháng

```sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT COUNT(*)
FROM partition_goal_lab.events
WHERE occurred_at >= TIMESTAMPTZ '2026-10-01 00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-11-01 00:00+00';
```

Quan sát:

- Plan có truy cập `events_2026_10` không?
- `events_2026_09` và `events_2026_11` có được loại bỏ không?
- Planner dùng Seq Scan hay index trong partition còn lại?
- Tổng buffers và thời gian có phù hợp quy mô?

Vì query đúng một tháng, PostgreSQL có thể xác định các partition ngoài tháng 10 không phù hợp. Trên bộ dữ liệu nhỏ, **Seq Scan trên riêng partition tháng 10 là bình thường**: pruning và index scan không phải cùng khái niệm.

### 7.6. Query không có partition key

```sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT COUNT(*)
FROM partition_goal_lab.events
WHERE tenant_id = 3;
```

`tenant_id` không phải partition key của bảng RANGE theo `occurred_at`. Mọi tháng đều có thể chứa tenant 3, nên PostgreSQL thường phải xét nhiều partitions. Nếu `tenant_id` là điều kiện lọc quan trọng, index con phù hợp có thể giúp nhưng không làm biến mất nhu cầu thăm dò các partition tháng còn có khả năng chứa kết quả.

### 7.7. Index trên parent, index vật lý ở child

```sql
CREATE INDEX idx_events_tenant_time
ON partition_goal_lab.events (tenant_id, occurred_at DESC);

ANALYZE partition_goal_lab.events;
```

Ở các phiên bản declarative partitioning hiện đại, tạo index trên bảng cha quản lý các index tương ứng cho các partitions hiện có. Khóa `tenant_id,occurred_at` có thể giúp tìm trong mỗi partition, nhưng không làm `WHERE tenant_id=3` prune các partition RANGE thời gian.

Thử lại:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, occurred_at
FROM partition_goal_lab.events
WHERE tenant_id = 3
  AND occurred_at >= TIMESTAMPTZ '2026-10-01 00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-11-01 00:00+00'
ORDER BY occurred_at DESC
LIMIT 20;
```

Query vừa có điều kiện giúp prune partition, vừa có điều kiện/ORDER BY hỗ trợ sử dụng index bên trong partition. Planner vẫn có thể chọn đường đi khác nếu dữ liệu nhỏ hoặc chi phí khác.

### 7.8. Query toàn bộ lịch sử

```sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT COUNT(*)
FROM partition_goal_lab.events;
```

Không có ràng buộc nào cho phép bỏ riêng tháng nào, nên plan có thể quét cả ba partitions và tổng hợp kết quả. Đây là điểm minh họa rõ **partitioning không phải bộ tăng tốc tự động cho quét toàn bảng**.

### 7.9. Dữ liệu ngoài khoảng đã tạo

Thử một câu INSERT cố ý nằm ngoài cả ba tháng:

```sql
-- Chỉ chạy riêng khi client cho phép quan sát lỗi:
INSERT INTO partition_goal_lab.events (
    event_id, occurred_at, tenant_id, event_type
)
VALUES (
    20001,
    TIMESTAMPTZ '2026-12-05 12:00+00',
    1,
    'view'
);
```

Nếu không có default partition và không có child bao trùm tháng 12, PostgreSQL sẽ báo **không tìm được partition phù hợp**. Nếu câu lệnh chạy trong transaction tường minh, SQL error có thể làm transaction chuyển trạng thái aborted cho tới khi rollback phù hợp.

Đây không phải lỗi index: partition routing cần một partition tiếp nhận giá trị mới.

### 7.10. Tạo partition tương lai rồi chèn lại

```sql
CREATE TABLE partition_goal_lab.events_2026_12
PARTITION OF partition_goal_lab.events
FOR VALUES FROM ('2026-12-01 00:00+00')
TO              ('2027-01-01 00:00+00');

INSERT INTO partition_goal_lab.events (
    event_id, occurred_at, tenant_id, event_type
)
VALUES (
    20001,
    TIMESTAMPTZ '2026-12-05 12:00+00',
    1,
    'view'
);
```

Nếu lỗi thử nghiệm trước đã được rollback và session đang ở trạng thái có thể chạy SQL, lần INSERT sau thành công. Lúc này bài lab có **18.001 hàng**: 18.000 hàng ban đầu cộng một hàng mới. Điều đó làm khác kết quả COUNT toàn bảng nếu lặp lại các câu `EXPLAIN ANALYZE`.

### 7.11. Thử với default partition

Thay vì để INSERT mới lỗi, có thể khai báo child mặc định:

```sql
CREATE TABLE partition_goal_lab.events_other
PARTITION OF partition_goal_lab.events
DEFAULT;
```

Default partition nhận hàng không khớp với partitions đã khai báo. Nó hữu ích như hàng rào cho late/out-of-range data, nhưng:

- Có thể che lỗi scheduler tạo partition tương lai.
- Có thể tích tụ dữ liệu “lạc chỗ”, làm pruning/bảo trì khó đoán.
- Khi attach/tạo partition mới, PostgreSQL có thể phải kiểm tra dữ liệu default để bảo đảm không chứa hàng thuộc phạm vi mới, tùy constraints và quy trình.
- Không được coi DEFAULT là điểm đến cuối cùng cho mọi dữ liệu mới.

Trong lab, tháng 12 đã có partition riêng nên câu INSERT ở 7.10 không vào default. Để thử default, chọn một thời gian **ngoài** các bounds có sẵn, nhưng không chạy trên production.

### 7.12. Xem danh sách partitions

Một số cách quan sát:

```sql
SELECT
    parent.relname AS parent_name,
    child.relname AS partition_name,
    pg_get_expr(child.relpartbound, child.oid) AS partition_bound
FROM pg_inherits AS inh
JOIN pg_class AS parent ON parent.oid = inh.inhparent
JOIN pg_class AS child ON child.oid = inh.inhrelid
JOIN pg_namespace AS n ON n.oid = parent.relnamespace
WHERE n.nspname = 'partition_goal_lab'
  AND parent.relname = 'events'
ORDER BY child.relname;
```

Trong `psql`, có thể dùng các metacommands như `\d+ partition_goal_lab.events` để xem cấu trúc và partitions. `\d+` là lệnh của `psql`, không phải SQL gửi trực tiếp tới server.

## 8. Pruning ở lúc lập kế hoạch và khi thực thi

Một truy vấn có literal xác định:

```sql
SELECT COUNT(*)
FROM partition_goal_lab.events
WHERE occurred_at >= TIMESTAMPTZ '2026-10-01 00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-11-01 00:00+00';
```

thường cho planner đủ thông tin để loại partitions ngay khi lập plan. Nhưng ứng dụng thường dùng prepared statements có tham số:

```sql
PREPARE events_by_time(timestamptz, timestamptz) AS
SELECT COUNT(*)
FROM partition_goal_lab.events
WHERE occurred_at >= $1
  AND occurred_at <  $2;
```

PostgreSQL có thể prune ở **planning time** hoặc **execution time**, tùy khả năng và ngữ cảnh plan. Do đó:

- Không nên kết luận “prepared statement không prune được”.
- Cũng không nên giả định mọi predicate có tham số luôn prune ở planning time.
- Hãy đo trên major đang dùng với custom/generic plan thực tế.

### 8.1. Thử generic plan trong lab

```sql
BEGIN;

SET LOCAL plan_cache_mode = force_generic_plan;

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE events_by_time(
    TIMESTAMPTZ '2026-10-01 00:00+00',
    TIMESTAMPTZ '2026-11-01 00:00+00'
);

ROLLBACK;

DEALLOCATE events_by_time;
```

`plan_cache_mode` là cấu hình có trên các PostgreSQL major hỗ trợ (từ PostgreSQL 12). Tùy kiểu plan và phiên bản, `EXPLAIN` có thể hiển thị `Subplans Removed`, những nodes không chạy, hoặc chỉ những nodes còn lại. Đọc theo cơ chế cụ thể, không phụ thuộc một chuỗi output cố định.

### 8.2. Pruning không phải partition-wise JOIN

Khả năng loại partitions dựa trên điều kiện WHERE khác với tối ưu JOIN/aggregate theo từng partition. PostgreSQL có các khả năng *partition-wise join* và *partition-wise aggregate* trong những điều kiện phù hợp, với chi phí tăng khi có nhiều partitions.

Không mặc định chia hai bảng theo cùng tháng sẽ khiến mọi JOIN tự động thực thi một-một giữa partitions. Cần xét partition scheme, join conditions, planner settings, sự tương thích bounds và thực tế EXPLAIN.

## 9. Khi partitioning thực sự đáng cân nhắc

### 9.1. Dữ liệu tăng theo thời gian, retention rõ ràng

Ví dụ:

- Access logs giữ 90 ngày.
- Audit events giữ 12 tháng theo chính sách.
- Telemetry/metrics giữ theo ngày.
- Clickstream với truy vấn chủ yếu theo cửa sổ thời gian.

Đặc điểm tốt:

1. Phần lớn truy vấn giới hạn thời gian tương đối hẹp.
2. Hàng mới đi vào partition hiện tại/tương lai.
3. Dữ liệu cũ trở nên ít thay đổi.
4. Có quy tắc xóa/archive phù hợp ranh giới partition.

**Lợi ích lớn nhất** có thể nằm ở retention/maintenance, không nhất thiết là latency SELECT.

### 9.2. Bảng cực lớn với truy vấn theo danh mục cố định

Ví dụ hệ thống khu vực có 4–8 vùng:

```sql
WHERE region = 'south'
```

Nếu query thường lọc region và dữ liệu/maintenance thực sự độc lập theo vùng, LIST partitioning có thể hữu ích.

Nhưng nếu hệ thống chỉ có 100.000 hàng, một index `(region,...)` có thể đơn giản và đủ nhanh. Không chọn LIST chỉ vì region có ít giá trị.

### 9.3. Workload nhiều tenant có chọn lọc

Phân vùng theo tenant ID hoặc hash của tenant có thể giảm phạm vi truy cập trong một số hệ thống:

```sql
WHERE tenant_id = ?
```

Nhưng phải đánh giá:

- Có bao nhiêu tenant?
- Số hàng từng tenant lệch đến mức nào?
- Có tenant rất lớn chiếm phần lớn dữ liệu không?
- Query có luôn biết tenant không?
- Cần uniqueness và foreign keys xuyên tenants không?
- Có nhu cầu query toàn hệ thống hay báo cáo cross-tenant không?

Một partition **cho mỗi tenant** có thể phù hợp cho số tenant ít, tương đối ổn định và cần vận hành tách biệt; với hàng chục nghìn tenant nhỏ, chiến lược này thường làm bùng nổ số relations/indexes.

### 9.4. Maintenance tách biệt hot/cold

Hệ thống có partition gần đây được UPDATE thường xuyên, còn lịch sử gần như bất biến. Có thể tối ưu lịch vacuum/analyze, index và archiving theo vùng dữ liệu. Nhưng cần kiểm tra real workload trước khi kết luận các partitions đã trở thành cold.

## 10. Trường hợp không phù hợp thứ nhất: bảng chưa đủ lớn hoặc thiếu vấn đề cụ thể

Một bảng 200.000 hàng với index phù hợp và latency đạt yêu cầu không nên được partition chỉ vì “bảng đang ngày càng lớn”. PostgreSQL B-tree có thể hoạt động rất tốt ở quy mô lớn nếu schema/index/query được thiết kế đúng.

### 10.1. Cần phân biệt kích thước với triệu chứng

Những câu hỏi tốt hơn câu “bảng có bao nhiêu GB?”:

- Query cụ thể nào đang chậm, và có bao nhiêu hàng phù hợp?
- Có phải planner đang seq scan khi cần index?
- Có thiếu index khớp điều kiện `WHERE` và `ORDER BY` không?
- Có bị sort lớn, join sai estimate hoặc N+1 queries không?
- Dữ liệu cũ có cần DELETE hàng loạt theo lịch không?
- VACUUM/autovacuum có bị chậm vì transaction dài hay write rate không?
- Disk/RAM/network và concurrency có phải nút thắt thực?

Nếu vấn đề chính là một query tra cứu theo `order_id` trả đúng một hàng, tạo index unique trên `order_id` ở bảng thường có thể giải quyết trực tiếp mà không cần partitioning.

### 10.2. Vì sao partitioning có thể làm chậm bảng nhỏ?

Khi bảng có vài trang dữ liệu, seq scan có thể rất rẻ. Sau khi chia thành hàng chục bảng con, planner phải xét partition metadata, xây các plan nodes, mở các relations liên quan và phối hợp nhiều nhánh. Chi phí overhead có thể lớn hơn lợi ích cắt giảm số trang đọc.

Không có một ngưỡng “10 triệu hàng thì bắt buộc phân vùng” hay “dưới 1 GB không được phân vùng” áp dụng cho mọi workload. Hãy đo trước và sau trên dữ liệu đại diện.

### 10.3. Khi nào vẫn phân vùng bảng chưa quá lớn?

Nếu yêu cầu retention rất rõ và bắt buộc xóa nguyên một tháng mỗi kỳ, partitioning có thể có giá trị **vận hành** trước khi xuất hiện query latency xấu. Quyết định khi đó dựa trên policy và dự báo tăng trưởng, không chỉ độ lớn hiện tại.

## 11. Trường hợp không phù hợp thứ hai: truy vấn không lọc theo partition key

Giả sử bảng được RANGE partition theo `created_at` nhưng hot query nhất là:

```sql
SELECT *
FROM partition_goal_lab.events
WHERE event_id = 12345;
```

`event_id` không tự chỉ ra partition thời gian nào chứa hàng này. Với 36 tháng, có thể cần một phép tìm kiếm qua nhiều child indexes hoặc scan phù hợp trên nhiều partitions.

### 11.1. Có index trên event_id thì sao?

Bạn có thể tạo:

```sql
CREATE INDEX idx_events_id
ON partition_goal_lab.events (event_id);
```

Nhưng trên declarative partitioned table thông thường, index này có các index vật lý con. Nó **không phải một B-tree global duy nhất** định vị một event_id xuyên tất cả partitions mà không cần biết tháng.

PostgreSQL có thể sử dụng child indexes để tìm nhanh trong từng partition, nhưng phải xét những partitions có khả năng chứa event_id. Khi số partitions tăng lớn, overhead của nhiều lần thăm dò có thể đáng kể.

### 11.2. Truy vấn không lọc thời gian nhưng vẫn cần cả lịch sử

Ví dụ:

```sql
SELECT tenant_id, COUNT(*)
FROM partition_goal_lab.events
GROUP BY tenant_id;
```

Truy vấn cần đếm dữ liệu toàn lịch sử; partitioning không thể bỏ các tháng chỉ vì việc nhóm theo tenant. Một số partition-wise aggregation/parallel scans có thể hữu ích nếu đủ điều kiện, nhưng không hứa nhanh hơn một bảng thường với cấu trúc/tài nguyên tương tự.

### 11.3. Truy vấn theo customer_id nhưng partition theo status

Nếu màn hình luôn tìm khách hàng cụ thể và không biết status, LIST partition theo status cũng có thể khiến mỗi query xét nhiều partitions. Chọn khóa phân vùng không khớp access pattern là một nguyên nhân phổ biến của **phân vùng nhiều nhưng pruning kém**.

### 11.4. Giải pháp khác

Trước khi partition:

1. Tạo index `(event_id)` hoặc composite index đúng hot query trên bảng thường.
2. Xem khả năng giữ ngày trong API/query để sử dụng pruning nếu nghiệp vụ tự nhiên đã biết ngày.
3. Nếu cần lookup toàn cục theo ID, cân nhắc mô hình metadata/directory đáng tin cậy ánh xạ ID→partition, nhưng đó là kiến trúc bổ sung với trách nhiệm nhất quán và transaction riêng.
4. Khi không thể xác định thời gian từ ID, đừng kỳ vọng partitioning theo thời gian tự rút ngắn đường tra cứu theo ID.

## 12. Trường hợp không phù hợp thứ ba: quá nhiều partitions quá nhỏ

Một bảng log có 100 triệu hàng được chia thành:

```text
12 partitions theo tháng
365 partitions theo ngày
8.760 partitions theo giờ
525.600 partitions theo phút trong một năm
```

Nhiều partitions nhỏ có thể làm tăng mạnh:

- Số relation/index entries trong system catalogs.
- Chi phí lập kế hoạch truy vấn và quản lý plan nodes.
- Metadata/relcache và bộ nhớ liên quan.
- Số tệp/file descriptors có thể được sử dụng.
- Hoạt động autovacuum/analyze trên nhiều child relations.
- Chi phí DDL khi tạo/attach/detach/index.
- Complexity của migration, backup, monitoring và alerting.

### 12.1. Partition granularity phải theo câu hỏi truy vấn và retention

Nếu 95% query đọc dữ liệu trong một tuần và retention xóa dữ liệu theo tháng, partition hàng ngày hoặc hàng tháng đều có thể đáng cân nhắc tùy kích thước từng ngày và thời gian bảo trì.

Nếu query đọc cả năm, tách theo phút gần như chắc chắn tạo quá nhiều metadata/planning overhead mà không có nhiều pruning hữu ích.

### 12.2. Không có số lượng partition tối đa “chuẩn” cho mọi hệ thống

PostgreSQL liên tục cải thiện cơ chế pruning, planning và quản lý partition qua các major. Nhưng điều đó không tạo ra số mặc định kiểu “1000 partitions luôn an toàn” hoặc “trên 200 chắc chắn chậm”. Các giới hạn thực tế phụ thuộc:

- Kích thước và độ phức tạp của mỗi partition.
- Số partitions query thực sự phải xét.
- Tần suất truy vấn và prepared plans.
- Số indexes/constraints mỗi child.
- DDL concurrency và metadata cache.
- Phần cứng và cấu hình.

Hãy đo trên hệ thống/phiên bản đang sử dụng.

### 12.3. Subpartitioning có thể làm số lượng tăng theo cấp số nhân

Ví dụ: 36 tháng × 128 hash buckets = **4.608 leaf partitions** chưa tính parent nodes và indexes. Nếu mỗi leaf có 3 indexes, số quan hệ index vật lý còn tăng đáng kể.

Phân theo nhiều chiều cần một mục tiêu đủ mạnh để bù chi phí ấy, không nên xem là mặc định “tốt hơn partition một tầng”.

## 13. Trường hợp không phù hợp thứ tư: khóa phân vùng thay đổi thường xuyên

Partition key phù hợp thường là giá trị **ổn định** trong vòng đời bản ghi, như ngày tạo sự kiện hoặc tenant ID bất biến theo thiết kế. Ngược lại, status của đơn hàng thường thay đổi:

```text
pending -> paid -> shipped -> completed
```

### 13.1. LIST theo status gây di chuyển hàng

Nếu:

```sql
CREATE TABLE status_orders (
    order_id bigint NOT NULL,
    status text NOT NULL,
    amount numeric(12, 2) NOT NULL
) PARTITION BY LIST (status);
```

mỗi status có một partition, khi `UPDATE ... SET status='paid'` thay đổi partition key, PostgreSQL có thể phải **di chuyển hàng từ partition cũ sang partition mới** theo ngữ nghĩa hỗ trợ chuyển hàng giữa partitions.

Đây không giống update một cột không khóa phân vùng trong cùng heap. Di chuyển hàng có thể làm tăng công việc index, WAL, trigger/constraint và cạnh tranh với các transaction khác.

### 13.2. Chuyển hàng giữa partitions không phải miễn phí

Về mặt thực thi PostgreSQL có thể biểu diễn row movement tương tự **DELETE khỏi partition nguồn và INSERT vào partition đích**, với các quy tắc concurrency và tính nhất quán tương ứng. Điều đó có ảnh hưởng đến:

- Indexes ở hai partitions.
- Foreign keys, triggers và chính sách bảng.
- Locking và serialization behavior.
- Replication/CDC interpretation theo cấu hình.

Không chọn LIST partition theo status **chỉ vì status là điều kiện lọc thường gặp** nếu status đổi liên tục và các query khác không có lợi.

### 13.3. Nguy cơ thiếu partition đích

Nếu một status mới `'returned'` xuất hiện nhưng chưa có partition hoặc default phù hợp, UPDATE làm thay đổi partition key có thể lỗi vì không định tuyến được row.

### 13.4. Tùy chọn thay thế

Index trên `status`, partial index cho hàng `pending`, hoặc composite `(tenant_id,status,created_at)` có thể phục vụ SELECT mà không buộc phải chuyển bản ghi vật lý mỗi khi status đổi. Nên đo chi phí ghi thực trước.

## 14. Trường hợp không phù hợp thứ năm: kỳ vọng uniqueness toàn cục theo khóa không chứa partition key

Đây là giới hạn thiết kế **rất quan trọng** đối với PostgreSQL declarative partitioning.

Giả sử bảng:

```sql
CREATE TABLE partition_goal_lab.events (
    event_id bigint NOT NULL,
    occurred_at timestamptz NOT NULL,
    ...
) PARTITION BY RANGE (occurred_at);
```

Ứng dụng muốn `event_id` là duy nhất toàn hệ thống, bất kể tháng. Nhưng trong mô hình partitioning PostgreSQL thông thường, **unique/primary key constraint khai báo trên partitioned parent phải bao gồm tất cả cột partition key**. Khi partition key sử dụng biểu thức/hàm, còn có những giới hạn bổ sung đối với khai báo unique/primary key trên parent.

### 14.1. Vì sao?

Các partition có index vật lý riêng. Nếu chỉ unique theo `event_id` trong mỗi child, hai bản ghi có cùng event_id nhưng tháng khác nhau có thể tồn tại, vì mỗi child chỉ kiểm soát hàng của mình.

Ranh giới partition phải tham gia unique key để hai hàng có cùng unique key không thể nằm ở hai partitions khác nhau.

### 14.2. Khóa chính khả thi theo tháng

Trong lab:

```sql
PRIMARY KEY (occurred_at, event_id)
```

Điều này bảo đảm uniqueness của **cặp** `(occurred_at,event_id)`, không đồng nghĩa `event_id` tự duy nhất toàn hệ thống.

Thí nghiệm trong transaction để không làm bẩn dataset:

```sql
BEGIN;

INSERT INTO partition_goal_lab.events (
    event_id, occurred_at, tenant_id, event_type
)
VALUES
    (90001, TIMESTAMPTZ '2026-10-05 00:00+00', 1, 'view'),
    (90001, TIMESTAMPTZ '2026-11-05 00:00+00', 1, 'view');

SELECT event_id, occurred_at, tableoid::regclass
FROM partition_goal_lab.events
WHERE event_id = 90001
ORDER BY occurred_at;

ROLLBACK;
```

Hai hàng có cùng event_id nhưng khác occurred_at **không vi phạm PRIMARY KEY(occurred_at,event_id)**. `ROLLBACK` cuối trả dữ liệu lab về trạng thái ban đầu.

### 14.3. Không khai báo PK(event_id) trên parent partitioned theo thời gian

```sql
-- Ví dụ KHÔNG hợp lệ cho parent partition theo occurred_at:
-- ALTER TABLE partition_goal_lab.events
-- ADD CONSTRAINT events_event_id_unique UNIQUE (event_id);
```

PostgreSQL không thể đảm bảo unique toàn cục bằng các index local của một partitioned table theo cách đó.

### 14.4. Những hướng giải quyết có đánh đổi

- **Dùng khóa ghép (occurred_at,event_id)** trong schema và mọi đường tham chiếu nếu ngữ nghĩa nghiệp vụ chấp nhận.
- **Đổi partition key** sang cột có mặt trong uniqueness cần thiết nếu hợp workload.
- **Bảng định danh/registry riêng** chứa event_id unique trên bảng thường, đồng thời quản lý consistency khi insert vào partitioned table.
- **Tạo ID globally unique ở tầng ứng dụng** (ví dụ định danh với đủ entropy) để xác suất trùng cực thấp, nhưng **đó không giống ràng buộc UNIQUE toàn cục được database kiểm chứng**.
- Nếu yêu cầu bắt buộc là unique(event_id) với enforcement đơn giản và truy vấn thường xuyên theo event_id, cân nhắc **không phân vùng bảng theo thời gian**.

Không cố mô phỏng global uniqueness bằng việc kiểm tra `SELECT` trước `INSERT` trong hai transaction đồng thời; cách đó có race condition nếu không có cơ chế đồng bộ và ràng buộc phù hợp.

## 15. Foreign keys và thiết kế khóa tham chiếu

Giới hạn unique key kéo theo hệ quả về foreign key:

> Nếu bảng cha partitioned chỉ có `PRIMARY KEY (occurred_at,event_id)`, một bảng con không thể tham chiếu chỉ `event_id` như thể nó có unique constraint toàn cục.

### 15.1. Ví dụ tham chiếu khóa ghép

```sql
CREATE TABLE partition_goal_lab.event_notes (
    note_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_occurred_at timestamptz NOT NULL,
    event_id bigint NOT NULL,
    note_text text NOT NULL,
    FOREIGN KEY (event_occurred_at, event_id)
        REFERENCES partition_goal_lab.events
            (occurred_at, event_id)
);
```

Ví dụ chèn note:

```sql
INSERT INTO partition_goal_lab.event_notes (
    event_occurred_at, event_id, note_text
)
SELECT
    occurred_at, event_id, 'Đã xác minh sự kiện'
FROM partition_goal_lab.events
WHERE event_id = 100
LIMIT 1;
```

Trong lab có event_id 100 duy nhất do cách sinh dữ liệu. `LIMIT 1` chỉ để ví dụ đơn giản, **không phải** đảm bảo tính duy nhất của event_id trong schema.

### 15.2. Query API phải biết đủ key

Nếu public API nhận duy nhất:

```text
GET /events/100
```

nhưng database chỉ enforce unique theo (occurred_at,event_id), ứng dụng cần quyết định liệu event_id có thực sự là ID toàn hệ thống không. Việc lưu thêm ngày vào note/foreign key và khả năng tra cứu event_id qua nhiều partitions là **thay đổi thiết kế API và data model**, không chỉ là một thao tác DDL.

### 15.3. Foreign keys được PostgreSQL hỗ trợ nhưng không miễn phí

Những PostgreSQL major hiện đại hỗ trợ foreign keys liên quan đến partitioned tables với các điều kiện/cú pháp phù hợp. Nhưng ràng buộc tham chiếu có thể làm các thao tác `DROP/DETACH` partition cũ, bulk load và migration phức tạp hơn.

Không mặc định bảng sự kiện có 10 tỷ hàng có thể drop partition mà không quan tâm các note/order/customer rows đang tham chiếu. Phải lập kế hoạch dữ liệu phụ thuộc trước khi xóa hoặc tách.

### 15.4. Tình huống không phù hợp

Nếu nhiều bảng con đang foreign key đến `orders(order_id)` và application không có ngày tạo order tại mọi nơi, việc chuyển `orders` sang RANGE partition theo ngày có thể gây chi phí migration rất lớn.

Lợi ích retention cần được so với việc thay đổi toàn bộ mô hình tham chiếu. Đôi khi một bảng không phân vùng và chiến lược archival khác là phương án ít rủi ro hơn.

## 16. UPSERT, UNIQUE và thao tác thay đổi partition key

PostgreSQL hỗ trợ `INSERT ... ON CONFLICT` khi có arbiter unique phù hợp, nhưng trên partitioned table cần hiểu partition scheme và unique key.

### 16.1. ON CONFLICT theo khóa ghép

Với dữ liệu đã chèn ở phần 7, hàng `event_id=100` có `occurred_at` vào ngày 16/09 lúc 01:39 UTC. Dùng đúng cặp này để thấy conflict target áp dụng trên khóa ghép:

```sql
BEGIN;

INSERT INTO partition_goal_lab.events (
    event_id, occurred_at, tenant_id, event_type
)
VALUES (
    100,
    TIMESTAMPTZ '2026-09-16 01:39+00',
    1,
    'purchase'
)
ON CONFLICT (occurred_at, event_id)
DO UPDATE SET
    event_type = EXCLUDED.event_type;

-- Chỉ thử nghiệm, không lưu thay đổi của bản ghi gốc.
ROLLBACK;
```

Lệnh có thể cập nhật bản ghi sẵn có theo khóa ghép, rồi `ROLLBACK` khôi phục dữ liệu lab. Nếu thay occurred_at bằng một thời điểm khác, cặp khóa sẽ khác và INSERT có thể tạo **hàng mới trùng event_id** mà vẫn hợp lệ theo PK ghép. Vì vậy **không dùng khóa ghép này để giả định event_id đơn lẻ có tính idempotency toàn cục**.

### 16.2. Conflict target phải phù hợp unique key

`ON CONFLICT (event_id)` không thể dựa trên `PRIMARY KEY (occurred_at,event_id)` để đảm bảo xung đột event_id toàn cục. Arbiter phải phù hợp unique index/constraint áp dụng.

### 16.3. DO UPDATE không phải cơ chế tự do chuyển partition

PostgreSQL có giới hạn với `ON CONFLICT DO UPDATE` trên partitioned table khi việc cập nhật partition key của row bị conflict khiến row phải chuyển sang partition khác. Không thể giả định mọi UPSERT có thể vừa resolve conflict vừa di chuyển row qua một partition mới.

Nếu nghiệp vụ thường thay đổi ngày tạo, tenant hoặc key phân vùng trong UPSERT, đây là dấu hiệu khóa phân vùng có thể không phù hợp.

## 17. Trường hợp không phù hợp thứ sáu: dữ liệu và truy vấn phân bố rất lệch

Một hệ thống có 100 tenant:

```text
Tenant 1:  85% tổng dữ liệu và 90% write traffic
Tenant 2:   5% tổng dữ liệu
Tenant 3-100: 10% còn lại
```

Nếu LIST partition một child cho mỗi tenant, partition tenant 1 vẫn là một bảng cực lớn, rất “nóng”. Partitioning không tự chia được tải của tenant 1.

### 17.1. Hash partitioning có giải quyết mọi skew không?

HASH theo tenant_id phân phối **các tenant IDs** vào các buckets; mọi row của một tenant nhất định vẫn được định tuyến theo cùng hash key tới cùng bucket trong kiến trúc hash key đó. Nếu một tenant sinh 85% dữ liệu, bucket chứa tenant ấy vẫn rất lớn.

Hash partitioning không đồng nghĩa hash từng row độc lập để phân bố một tenant lớn qua mọi buckets. Đó là sự khác nhau giữa khóa hash **tenant_id** và khóa hash **event_id**.

### 17.2. Đổi key sang event_id có đáng giá?

Nếu HASH trên event_id để phân bố đều row của tenant lớn, truy vấn `WHERE tenant_id=?` có thể không prune hiệu quả theo event_id. Bạn giảm skew vật lý theo row ID nhưng làm mất lợi ích pruning theo tenant.

**Phân vùng phải giải một bài toán workload cụ thể**, không thể mặc định giải đồng thời mọi dạng skew, mọi query và mọi hotspot.

### 17.3. Phân tích theo ba chiều

Với multi-tenant workloads, đánh giá:

1. **Data skew:** số hàng/bytes từng tenant.
2. **Read skew:** những tenant/query nào tạo phần lớn reads.
3. **Write skew:** những tenant/bảng nào tạo phần lớn UPDATE/INSERT.

Một giải pháp phù hợp có thể là subpartitioning cho tenant lớn, table riêng, workload isolation hoặc sharding, nhưng mỗi hướng đều có đánh đổi về transaction/queries và vận hành.

## 18. Trường hợp không phù hợp thứ bảy: JOIN, GROUP BY hoặc ORDER BY xuyên nhiều partitions

Partitioning giúp nhất khi loại được partitions không liên quan. Với truy vấn toàn hệ thống:

```sql
SELECT
    tenant_id,
    COUNT(*) AS event_count
FROM partition_goal_lab.events
GROUP BY tenant_id
ORDER BY event_count DESC
LIMIT 10;
```

PostgreSQL vẫn phải xét dữ liệu trong nhiều partitions để tính tổng số sự kiện của từng tenant trên toàn bộ lịch sử.

### 18.1. ORDER BY thời gian trên toàn bảng

```sql
SELECT event_id, occurred_at
FROM partition_goal_lab.events
ORDER BY occurred_at DESC
LIMIT 20;
```

Planner có thể chọn những phương án như Append/Merge Append và scan indexes phù hợp tùy dữ liệu. Một số trường hợp có lợi từ phạm vi thời gian, nhưng **không được suy ra chỉ vì partition theo tháng là planner chắc chắn đọc duy nhất tháng gần nhất** khi query không có filter.

Ví dụ, partition mới nhất có thể rỗng; timestamps có thể phân bố đặc biệt, default partition có thể chứa dữ liệu bất thường và planner cần chứng minh đủ điều kiện để bỏ phần khác. Kiểm tra `EXPLAIN` và số rows/buffers thực tế.

### 18.2. JOIN giữa hai bảng chia khác khóa

Giả sử orders chia theo thời gian, customers chia theo region:

```text
orders PARTITION BY RANGE(created_at)
customers PARTITION BY LIST(region)
```

Một JOIN `orders.customer_id = customers.customer_id` không tự tương ứng child-to-child. PostgreSQL có thể phải lập kế hoạch JOIN giữa nhiều partition scans và materialization/hash structures.

Đừng chọn partition scheme khác nhau cho những bảng phải JOIN liên tục mà không đánh giá ảnh hưởng query plan.

### 18.3. Partition-wise join/aggregate không phải mặc định

PostgreSQL có khả năng partition-wise join/aggregate trong những điều kiện phù hợp và các cấu hình planner tương ứng. Chẳng hạn:

```sql
SHOW enable_partitionwise_join;
SHOW enable_partitionwise_aggregate;
```

Giá trị mặc định và hiệu ứng cụ thể cần xem trên major/server đang chạy. Việc bật những phương án partition-wise có thể tăng **planning time/memory** theo số partitions. Chúng cũng chỉ được sử dụng khi query, partition bounds, key và costing phù hợp.

### 18.4. Báo cáo toàn lịch sử có giải pháp khác?

Nếu ứng dụng thường phải xem tổng số đơn theo tenant trên năm năm, cân nhắc:

- Index phù hợp hoặc scan song song trên bảng thường.
- Materialized view/tổng hợp định kỳ nếu chấp nhận dữ liệu trễ.
- Bảng summary duy trì theo transaction/outbox.
- Hệ thống analytics riêng cho aggregate lớn.

Phân vùng theo tháng có thể vẫn tốt cho retention, nhưng không tự biến aggregate toàn lịch sử thành query trên một partition.

## 19. Trường hợp không phù hợp thứ tám: muốn tăng hiệu năng ghi mà không đổi giới hạn hệ thống

Một server PostgreSQL có:

- Disk IOPS hữu hạn.
- CPU hữu hạn.
- WAL writer và checkpoint I/O trên cùng hạ tầng.
- Lock/contention và connection pool limits.

Chia bảng thành 64 hash partitions không tự tăng throughput đến 64 lần. Tất cả partitions vẫn hoạt động trong cùng cluster/instance nếu không có kiến trúc phân phối khác.

### 19.1. Partitioning có thể giúp một số bottleneck

Trong các tình huống nhất định, việc tách indexes và heap theo partitions có thể:

- Giới hạn kích thước index được thao tác khi biết partition key.
- Phân tách vacuum/maintenance.
- Thay đổi pattern contention hoặc cache locality.
- Tăng khả năng song song hóa những query/maintenance thích hợp.

Nhưng **đây là lợi ích phụ thuộc workload**, không phải cam kết throughput ghi tăng tuyến tính.

### 19.2. INSERT routing có chi phí riêng

Mỗi INSERT vào bảng cha phải xác định partition đích và tuân thủ constraints/triggers tương ứng. Với quá nhiều partitions, đây cũng là một phần overhead.

Bulk load có thể định tuyến qua parent hoặc load có kiểm soát trực tiếp vào partition thích hợp, nhưng cần đảm bảo partition constraints, bảo mật và quy trình đúng. Không bypass parent chỉ để tăng tốc mà vô tình bỏ qua validation hoặc operational contract.

### 19.3. Khi cần nhiều máy thật

Nếu bài toán là vượt giới hạn CPU/I/O/dung lượng của một instance, cần đánh giá:

- Vertical scaling/phần cứng tốt hơn.
- Connection pooling và query optimization.
- Read replicas cho read-heavy workload.
- Sharding/distributed database khi cần chia data/write load sang nhiều nodes.
- Hệ thống OLAP hoặc streaming cho analytics.

Declarative partitioning có thể là một thành phần của kiến trúc lớn, nhưng **không tự triển khai các thành phần ấy**.

## 20. Trường hợp không phù hợp thứ chín: retention không khớp partition bounds

Một số hệ thống bắt buộc xóa **theo đối tượng nghiệp vụ**, không theo thời gian:

```text
Xóa tất cả dữ liệu của khách A
Giữ lại dữ liệu khách B không giới hạn thời gian
Giữ dữ liệu có legal hold
Xóa từng account khi có yêu cầu
```

Nếu RANGE partition theo tháng, dữ liệu của khách A có thể xuất hiện ở **tất cả các tháng**. Xóa khách A vẫn cần DELETE/logic xóa theo hàng trong nhiều partitions.

### 20.1. Không phải mọi chính sách xóa đều giúp DROP partition

DROP một partition tháng sẽ xóa dữ liệu của **mọi khách** trong tháng đó. Nếu policy chỉ cho xóa khách A, không thể drop toàn partition mà không làm mất dữ liệu của khách khác.

### 20.2. Phân vùng theo tenant có giải quyết không?

Nếu tenant A có một partition riêng và chính sách thực sự yêu cầu xóa **toàn bộ tenant**, LIST partition per tenant có thể giúp. Nhưng điều này lại tăng số partitions và có thể bất lợi nếu số tenants rất lớn.

Phải chọn theo **đơn vị xóa/archival thực tế**, không dựa vào một ví dụ marketing rằng partitioning cho phép DROP dữ liệu cũ.

### 20.3. Soft delete và legal hold

Nếu bản ghi có legal hold, soft-delete flags hoặc retention exceptions, partitioning theo thời gian không tự biết hàng nào được phép xóa. Cần mô hình nghiệp vụ và kiểm soát dữ liệu riêng. Không tự drop partition dù đa số hàng đã hết hạn nếu vẫn chứa một số hàng bắt buộc giữ.

## 21. Trường hợp không phù hợp thứ mười: quản trị tự động chưa sẵn sàng

Với bảng thời gian, partitions cần tồn tại **trước khi hàng mới tới**. Một hệ thống tạo partition thủ công từng tháng dễ gặp lỗi đúng lúc tháng mới bắt đầu.

### 21.1. Những vận hành tối thiểu cần có

- Tạo partitions tương lai trước hạn, có đủ khoảng dự phòng.
- Cảnh báo nếu partition kế tiếp chưa tồn tại.
- Đảm bảo index/constraints/permissions phù hợp trên partition mới.
- ANALYZE sau bulk load khi cần.
- Kiểm tra dữ liệu đến trễ hoặc timestamp sai.
- Đo default partition growth nếu dùng.
- Có lịch attach/detach/archive/drop theo retention.
- Kiểm soát lock, backup, dependency và khả năng rollback của DDL.

Nếu tổ chức chưa có khả năng làm những việc này, partitioning có thể **giảm độ tin cậy** hơn là tăng.

### 21.2. Vấn đề khi DEFAULT bị bỏ quên

Ví dụ:

```text
Tháng 11 có partition
Tháng 12 chưa tạo
DEFAULT nhận mọi dữ liệu tháng 12

Đến giữa tháng 12:
  DEFAULT chứa 50 triệu hàng
  nhiều query chạm DEFAULT
  ATTACH partition tháng 12 cần kiểm tra/di chuyển dữ liệu
```

Mặc định không có cơ chế tự động “chuyển sạch hàng từ DEFAULT sang child tháng mới” chỉ bằng khai báo partition ranh giới. Phải có quy trình migration/validation phù hợp, có thể tốn thời gian và khóa.

### 21.3. Dữ liệu đến trễ

Một event đến ngày 15/11 nhưng `occurred_at` thuộc 30/9 vẫn cần partition tháng 9 nếu dùng ngày sự kiện làm key. Nếu partition tháng 9 đã DROP vì retention, INSERT có thể lỗi hoặc đi vào DEFAULT.

Thiết kế cần quyết định dùng **event time** hay **ingestion time** làm partition key:

- Event time phù hợp báo cáo lịch sử theo thời gian sự kiện.
- Ingestion time phù hợp một số operational workflows theo thời điểm nhận.
- Hai đại lượng có thể lệch rất xa; chọn sai ảnh hưởng pruning, routing và retention.

## 22. Khi nào nên ưu tiên index thay vì partition?

Phần lớn truy vấn ORM/API điển hình là selective lookups:

```sql
SELECT order_id, status, amount
FROM orders
WHERE tenant_id = 15
  AND customer_id = 9001
ORDER BY created_at DESC
LIMIT 20;
```

Nếu bảng chưa phân vùng, một B-tree như:

```sql
CREATE INDEX idx_orders_tenant_customer_time
ON orders (
    tenant_id,
    customer_id,
    created_at DESC
);
```

có thể giải trực tiếp bài toán. Partitioning theo tháng không làm phép tìm khách nhanh hơn nếu query không biết khoảng ngày.

### 22.1. B-tree cho equality và top-N

B-tree composite thường phù hợp:

- `WHERE tenant_id=? AND customer_id=?`.
- `WHERE order_id=?` nếu cần uniqueness/lookup toàn cục.
- `ORDER BY created_at DESC LIMIT ?` với key order thích hợp.
- Keyset pagination trên các khóa có thứ tự.

### 22.2. Partial index cho một trạng thái hiếm

```sql
-- Ví dụ trên bảng orders không phân vùng:
CREATE INDEX idx_orders_pending_by_tenant
ON orders (tenant_id, created_at DESC)
WHERE status = 'pending';
```

Nếu hot query chỉ tìm đơn pending, partial index nhỏ có thể tốt hơn LIST partition theo status thường đổi. Tất nhiên nó vẫn tăng chi phí bảo trì khi status đổi.

### 22.3. BRIN cho dữ liệu append có tương quan vật lý

Một bảng sự kiện rất lớn chèn tăng dần theo thời gian có thể hưởng lợi từ **BRIN**:

```sql
-- Ví dụ trên bảng events thông thường:
CREATE INDEX idx_events_brin_time
ON events USING BRIN (occurred_at);
```

BRIN index thường nhỏ, dùng tóm tắt theo block ranges, phù hợp cột có tương quan vật lý. Tuy nhiên nó có thể trả candidate page ranges cần recheck, không cung cấp order trực tiếp như B-tree.

**BRIN và partitioning có thể phối hợp**, không phải hai lựa chọn loại trừ nhau. Nhưng nếu yêu cầu chỉ lọc thời gian và không có retention/drop nhanh, một BRIN trên bảng thường có thể là điểm thử đơn giản hơn.

### 22.4. Query optimization trước structural migration

Đừng partition một bảng chỉ để che câu SQL thiếu điều kiện:

```sql
SELECT *
FROM orders
ORDER BY created_at DESC
OFFSET 1000000 LIMIT 20;
```

Vấn đề có thể nằm ở pagination (OFFSET cực sâu), không phải thiếu partitions. Keyset pagination kèm index phù hợp đôi khi xử lý chính xác hơn.

## 23. Các phương án thay thế partitioning

| Nhu cầu chính | Phương án nên kiểm tra trước hoặc song song | Khi partitioning đáng cân nhắc |
| --- | --- | --- |
| Lookup một row theo ID | Unique B-tree/index đúng key. | Khi còn mục tiêu retention/bảo trì và ID có thể định tuyến. |
| Query tenant + time | Composite index, pruning logic trong SQL. | Khi dữ liệu theo thời gian rất lớn và query thường giới hạn tháng/ngày. |
| Scan range thời gian trên bảng append | BRIN/B-tree theo thời gian. | Khi cần DROP/archive theo khoảng rõ hoặc giới hạn scans bằng bounds. |
| Xóa từng khách theo yêu cầu | Indexed DELETE, workflow retention, soft-delete policies. | Khi dữ liệu tách được theo đơn vị xóa độc lập và số partitions hợp lý. |
| Aggregate toàn lịch sử | Materialized view, summary table, OLAP. | Có thể hỗ trợ maintenance, không thay thế aggregates. |
| Bảng bloat do transaction dài | Xác định snapshot/XID holder, vacuum, sửa transaction boundary. | Partitioning không giải quyết blocker MVCC gốc. |
| Mức write throughput vượt một máy | Tối ưu contention/I/O, scale-up, sharding/distributed strategy. | Partitioning có thể hỗ trợ tổ chức dữ liệu, không tự phân phối tải sang nhiều máy. |
| Query chỉ lọc trạng thái cập nhật thường xuyên | Partial/composite index. | LIST status dễ gây row movement; chỉ chọn khi lý do đủ mạnh. |
| Dữ liệu cũ cần archive từng tháng | Archival/retention job có kiểm soát. | Một trong những trường hợp partitioning thường rất đáng cân nhắc. |

### 23.1. Vì sao lựa chọn có thể kết hợp?

Ví dụ tốt:

```text
RANGE partition theo tháng
  +-- local B-tree (tenant_id, occurred_at)
  +-- BRIN hoặc index khác theo hot query nếu phù hợp
  +-- ANALYZE theo lịch sau ingest
  +-- DROP/DETACH sau retention kiểm chứng
```

Partitioning **quản lý phạm vi dữ liệu**; indexes **quản lý truy cập trong phạm vi**; statistics **giúp planner chọn plan**; application/retention workflow **quản lý vòng đời nghiệp vụ**.

### 23.2. Đừng tối ưu từng phần mà quên toàn bộ chi phí

Một thiết kế có thể nhanh cho query tháng gần nhất nhưng làm chậm query cross-tenant, tăng chi phí INSERT và khiến migration khó. Quyết định cuối phải dựa trên tổng thể SLA, storage, operational risk và sự cần thiết của retention.

## 24. Partitioning và MVCC/VACUUM: không phải thuốc chữa bloat tổng quát

Một bảng thường bị bloat vì UPDATE/DELETE nhiều, hoặc VACUUM không thể dọn versions do giao dịch dài. Phân vùng theo tháng có thể:

- Giới hạn vùng dữ liệu cập nhật.
- Cho phép vacuum những partitions có write activity cao.
- Cho phép drop phần dữ liệu cũ đã hết hạn mà không DELETE hàng loạt.

Nhưng **không thay đổi quy tắc MVCC**: nếu một snapshot cũ còn cần tuple versions ở partition đang tồn tại, VACUUM không được xóa chúng chỉ vì bảng đã partitioned.

### 24.1. Giao dịch dài vẫn tồn tại

```text
Session A: BEGIN REPEATABLE READ
           SELECT from partition tháng 10
           giữ snapshot lâu

Session B: UPDATE nhiều row tháng 10, COMMIT

Autovacuum tháng 10:
           vẫn phải tôn trọng snapshot A
```

Partitioning không “phá” quyền đọc theo snapshot cũ. Nếu root cause là `idle in transaction` giữ horizon, cần sửa transaction lifecycle/timeout/monitoring.

### 24.2. DROP partition không có nghĩa luôn không chặn

DROP là DDL chịu ràng buộc lock và dependency. Một transaction đang đọc partition có thể khiến ALTER/DROP cần chờ tùy thao tác và phiên bản.

Không đưa partitioning vào production rồi mặc định retention DROP có thể chạy mọi lúc không ảnh hưởng người dùng.

### 24.3. Partitioning và anti-wraparound

Các partitions vẫn có thông tin transaction IDs cần VACUUM/freezing phù hợp. Không được tắt autovacuum toàn bộ vì nghĩ mỗi tháng DROP một partition sẽ giải quyết mọi vấn đề transaction ID.

## 25. Chọn partition key: bảng quyết định

Chọn partition key là quyết định **kiến trúc dữ liệu**, không chỉ cú pháp SQL.

### 25.1. RANGE trên thời gian

Ưu điểm:

- Phù hợp dữ liệu theo sự kiện/ingestion.
- Query có điều kiện thời gian dễ prune.
- Retention theo tháng/ngày có thể đơn giản hóa.
- Partitions cũ có thể được archive theo lifecycle.

Nhược điểm:

- Query theo ID mà không có thời gian phải xét nhiều partitions.
- Unique toàn cục theo ID đơn lẻ khó enforce trên parent partition theo thời gian.
- Late arrivals cần partition cũ hoặc chính sách riêng.
- Granularity cần cân đối retention và số lượng partitions.

### 25.2. LIST theo tenant/region

Ưu điểm:

- Có thể prune khi query luôn có tenant/region.
- Một số tenant/region có thể bảo trì độc lập.
- Dễ lý giải nếu số giá trị thấp và ổn định.

Nhược điểm:

- Mỗi tenant một partition gây bùng nổ child tables khi tenant tăng nhanh.
- Tenant lớn có thể tạo hotspot.
- Cross-tenant queries vẫn xét nhiều partitions.
- Thêm tenant mới phải chuẩn bị bound/partition hoặc default.

### 25.3. HASH theo khóa định danh

Ưu điểm:

- Có thể phân phối các giá trị key tương đối đều nếu hash key phân bố tốt.
- Số partitions có thể được chọn có kiểm soát.
- Equality trên hash key có thể định tuyến vào bucket.

Nhược điểm:

- Không hỗ trợ prune theo một range thời gian nếu range đó không liên quan hash key.
- Rebalance/thay số buckets không chỉ là đổi một tham số đơn giản; cần kế hoạch redistribute dữ liệu/partition bounds.
- Skew mạnh của một giá trị khóa vẫn có thể tồn tại trong bucket.
- Retention theo thời gian phải DELETE trong nhiều buckets nếu không subpartition.

### 25.4. Cần cả thời gian lẫn tenant?

Nếu query phổ biến có:

```sql
WHERE tenant_id = ?
  AND occurred_at >= ?
  AND occurred_at < ?
```

nhưng dữ liệu cực lớn, có thể cân nhắc:

- Partition RANGE theo thời gian, dùng B-tree `(tenant_id,occurred_at)` trong từng child.
- Partition HASH theo tenant, dùng index thời gian trong mỗi child.
- Subpartition RANGE+HASH khi lợi ích đã được chứng minh đủ lớn.

Không nhất thiết subpartition chỉ vì query có hai predicates. Một chỉ mục composite bên trong partition thường giải quyết được phần lớn nhu cầu với ít overhead hơn.

### 25.5. Multi-column partition key không luôn là “hai chiều”

`PARTITION BY RANGE (tenant_id,occurred_at)` sử dụng thứ tự range key nhiều cột theo ngữ nghĩa so sánh của PostgreSQL; nó **không mặc nhiên tạo một lưới tenant × tháng** với hai chiều độc lập dễ suy luận như subpartitioning.

Nếu mục tiêu là mỗi tháng có các hash buckets theo tenant, cần khai báo phân cấp phù hợp thay vì coi một range key hai cột là tương đương.

## 26. Chọn kích thước partition: ngày, tuần, tháng hay năm?

Granularity quyết định số partition, khả năng prune và độ chính xác retention.

### 26.1. Bảng gợi ý theo đặc tính

| Granularity | Điểm mạnh | Rủi ro |
| --- | --- | --- |
| **Năm** | Ít partitions, quản trị đơn giản. | Mỗi child rất lớn; query một tuần vẫn phải xử lý child cả năm; retention theo tháng khó. |
| **Tháng** | Cân bằng cho nhiều datasets thời gian. | Dữ liệu tháng có thể quá lớn; retention 90 ngày lăn không khớp tuyệt đối. |
| **Tuần** | Khoảng nhỏ hơn tháng, phù hợp retention theo tuần. | Nhiều partitions hơn; cần thống nhất tuần ISO/UTC/timezone nghiệp vụ. |
| **Ngày** | Prune rất hẹp, DROP theo ngày. | Nhiều child/indexes, DDL automation thường xuyên. |
| **Giờ** | Phù hợp một số workloads telemetry cực lớn theo cửa sổ giờ. | Metadata và maintenance overhead có thể quá lớn nếu không có lý do mạnh. |

Không phải danh sách này là thứ tự “càng nhỏ càng tốt”. Quyết định phụ thuộc hàng/bytes mỗi partition, tần suất query, thời gian retention và khả năng bảo trì.

### 26.2. Một mô hình tính số child

Giả sử:

- Retention: 3 năm.
- Partition theo tháng: 36 children.
- Partition theo ngày: khoảng 1.095 children.
- Partition theo giờ: khoảng 26.280 children.

Nếu mỗi partition có ba indexes và metadata riêng, số đối tượng vật lý tăng đáng kể. Nhưng mô hình tính này chỉ dự báo **số lượng**, không dự báo chính xác planning time hay IOPS. Cần benchmark theo workload.

### 26.3. Granularity theo kích thước hot partition

Một tháng có 500 triệu hàng có thể quá lớn cho yêu cầu vacuum/index maintenance và retention. Một tuần hoặc ngày có thể hợp lý hơn. Ngược lại, một ngày chỉ 100 hàng mà hệ thống giữ 10 năm thì ngày-per-partition thường không kinh tế.

### 26.4. Đừng thay granularity khi chưa nghĩ tới migration

Đổi từ monthly sang daily không phải sửa duy nhất tham số `PARTITION BY`. Thường cần thay partition tree, chuyển/attach dữ liệu theo bounds, kiểm soát index/constraint/locks và đồng bộ với ứng dụng.

## 27. Quản lý vòng đời partition

Một kế hoạch partitioning tốt phải mô tả trọn vòng đời:

```text
Thiết kế bounds
     |
     v
Tạo partition tương lai
     |
     v
Nhận dữ liệu + routing
     |
     v
ANALYZE/VACUUM và index maintenance
     |
     v
Partition trở nên ít thay đổi
     |
     v
Xác minh retention / legal hold / downstream
     |
     v
DETACH / ARCHIVE / DROP theo runbook
```

### 27.1. Tạo partition trước kỳ

Ví dụ lịch tháng:

```sql
-- Chỉ chạy nếu partition chưa tồn tại:
CREATE TABLE partition_goal_lab.events_2027_01
PARTITION OF partition_goal_lab.events
FOR VALUES FROM ('2027-01-01 00:00+00')
TO              ('2027-02-01 00:00+00');
```

Nếu một DEFAULT partition tồn tại và chứa hàng tháng 1, thao tác tạo/attach partition cần xem xét dữ liệu đang nằm ở DEFAULT và có thể yêu cầu tách/chuyển trước.

Đối với vận hành, nên tạo partitions **trước** thời điểm tháng mới bắt đầu, có monitor kiểm tra bounds chứ không đợi INSERT đầu tiên báo lỗi.

### 27.2. ATTACH partition có dữ liệu lịch sử

Một phương án migration thường:

1. Tạo bảng độc lập có cùng cấu trúc phù hợp.
2. Nạp dữ liệu thuộc khoảng được dự kiến attach.
3. Tạo index và CHECK constraint phù hợp theo chiến lược.
4. Xác nhận không có hàng nằm ngoài bound.
5. `ALTER TABLE parent ATTACH PARTITION ... FOR VALUES ...`.

Nếu PostgreSQL không thể chứng minh toàn bộ hàng thỏa partition constraint, ATTACH có thể phải **scan bảng để validate** và cần locks phù hợp.

### 27.3. DETACH PARTITION

Mẫu SQL minh họa, **không thực thi trên partition lab nếu đang dùng để học**:

```sql
-- ALTER TABLE partition_goal_lab.events
-- DETACH PARTITION partition_goal_lab.events_2026_09;
```

Sau khi tách, bảng `events_2026_09` vẫn tồn tại như một bảng độc lập. Query bảng cha không còn thấy dữ liệu của bảng đã detach.

### 27.4. DETACH PARTITION CONCURRENTLY

Ở các PostgreSQL major hỗ trợ, `DETACH PARTITION ... CONCURRENTLY` có thể giảm một số loại chặn so với detach thông thường, nhưng:

- Không được chạy trong transaction block tường minh.
- Có những hạn chế theo version/configuration, ví dụ liên quan DEFAULT partition.
- Vẫn có nhiều giai đoạn và có thể phải chờ transactions.
- Khi bị gián đoạn có thể cần tiếp tục/khôi phục theo quy trình của PostgreSQL.

Không giả định "CONCURRENTLY" bằng không có locks, không chờ, không ảnh hưởng người dùng.

### 27.5. DROP partition

Mẫu:

```sql
-- Chỉ sau khi đã xác minh retention và dependencies:
-- DROP TABLE partition_goal_lab.events_2026_09;
```

Đây là thao tác mất dữ liệu nếu không có backup/archive khác. Hãy phân biệt **biết cách viết câu SQL** với **được phép thực hiện thao tác phá hủy trong production**.

### 27.6. Không dùng DROP CASCADE một cách phản xạ

Nếu partition có đối tượng phụ thuộc, `DROP ... CASCADE` có thể loại thêm các objects ngoài dự tính. Kiểm tra dependency và chọn cách quản lý có chủ đích. Không thêm CASCADE chỉ để “cho DDL chạy qua” khi chưa biết đối tượng nào bị xóa.

## 28. Quan sát partition tree và kích thước

### 28.1. pg_partition_tree

Ở các PostgreSQL major có hàm `pg_partition_tree`:

```sql
SELECT
    relid::regclass AS relation_name,
    parentrelid::regclass AS parent_name,
    isleaf,
    level
FROM pg_partition_tree(
    'partition_goal_lab.events'::regclass
)
ORDER BY level, relid::regclass::text;
```

Hàm trả cấu trúc cây (parent và children) cho partitioned table được nêu, hữu ích khi kiểm tra subpartitioning.

### 28.2. Kích thước từng leaf partition

```sql
SELECT
    relid::regclass AS partition_name,
    pg_size_pretty(pg_relation_size(relid)) AS heap_size,
    pg_size_pretty(pg_indexes_size(relid)) AS index_size,
    pg_size_pretty(pg_total_relation_size(relid)) AS total_size
FROM pg_partition_tree(
    'partition_goal_lab.events'::regclass
)
WHERE isleaf
ORDER BY pg_total_relation_size(relid) DESC;
```

Kích thước physical relation không tự bằng số rows hoặc live data size. Các index vật lý, TOAST và dead/free space ảnh hưởng total size. Tránh quyết định granularity chỉ từ một con số dung lượng mà không xét query và maintenance.

### 28.3. Row estimates và thời điểm ANALYZE

```sql
SELECT
    s.relid::regclass AS partition_name,
    s.n_live_tup,
    s.n_dead_tup,
    s.last_analyze,
    s.last_autoanalyze,
    s.last_vacuum,
    s.last_autovacuum
FROM pg_stat_all_tables AS s
WHERE s.relid IN (
    SELECT relid
    FROM pg_partition_tree(
        'partition_goal_lab.events'::regclass
    )
)
ORDER BY s.relid::regclass::text;
```

`n_live_tup`/`n_dead_tup` là estimates thống kê, không phải phép đếm chính xác tại thời điểm query. Nếu cần số hàng chính xác cho bài lab, dùng `COUNT(*)` trên dữ liệu.

### 28.4. Kiểm tra pruning bằng EXPLAIN

```sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT COUNT(*)
FROM partition_goal_lab.events
WHERE occurred_at >= TIMESTAMPTZ '2026-10-01 00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-11-01 00:00+00';
```

Xem có những partition scan nodes nào, nodes nào không chạy, bao nhiêu buffers và thời gian. Không chỉ nhìn vào **cost** rồi suy ra hiệu năng.

### 28.5. Cấu hình partition pruning

```sql
SHOW enable_partition_pruning;
```

Giữ nguyên cấu hình phù hợp trong production. Nếu thử sự khác biệt, có thể dùng `SET LOCAL` trong transaction lab cho EXPLAIN để giới hạn phạm vi thay đổi:

```sql
BEGIN;
SET LOCAL enable_partition_pruning = off;

EXPLAIN
SELECT COUNT(*)
FROM partition_goal_lab.events
WHERE occurred_at >= TIMESTAMPTZ '2026-10-01 00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-11-01 00:00+00';

ROLLBACK;
```

Thao tác trên chỉ nhằm so kế hoạch; **không khuyến nghị tắt pruning để tối ưu**. Nếu một kế hoạch không prune, hãy tìm nguyên nhân ở predicates, bindings và partition bounds.

## 29. Vận hành cần đo cả planning time lẫn execution time

Với nhiều partitions, một truy vấn có thể chạy rất nhanh sau khi plan được tạo nhưng **lập plan chậm**. Một query khác có planning time ngắn nhưng execution time dài do phải quét nhiều partitions.

### 29.1. Các chỉ số EXPLAIN

```sql
EXPLAIN (ANALYZE, BUFFERS, SUMMARY)
SELECT event_id, occurred_at
FROM partition_goal_lab.events
WHERE occurred_at >= TIMESTAMPTZ '2026-10-01 00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-11-01 00:00+00'
ORDER BY occurred_at DESC
LIMIT 20;
```

Quan sát:

| Chỉ số | Câu hỏi |
| --- | --- |
| Planning Time | Cây partition làm thời gian lập plan tăng bao nhiêu? |
| Execution Time | Sau pruning/index, truy vấn thực chạy trong bao lâu? |
| Rows, Actual Rows, Loops | Dự báo số hàng có lệch thực tế không? |
| Buffers Shared Hit/Read | Truy cập bao nhiêu trang trong cache/đọc thực? |
| Append / Merge Append | Có kết hợp nhiều child nodes không? |
| Subplans Removed / nodes không chạy | Pruning ở những giai đoạn tương ứng hoạt động thế nào? |
| Sort / Incremental Sort | Index/partition order có tránh sort không? |

### 29.2. Đo nhiều query patterns

Benchmark ít nhất:

1. Query một ngày/tháng với predicate rõ ràng.
2. Query nhiều tháng.
3. Query theo ID không có thời gian.
4. Query theo tenant trên toàn lịch sử.
5. Aggregate hoặc JOIN xuyên nhiều months.
6. Bulk insert và UPDATE có/không đổi key.
7. Retention/maintenance thao tác DDL.

Không dùng kết quả của **một** câu query tháng gần nhất để kết luận partitioning sẽ tốt cho cả hệ thống.

### 29.3. Kiểm tra locks khi DDL

Trong môi trường kiểm thử, có thể xem:

```sql
SELECT
    a.pid,
    a.state,
    a.wait_event_type,
    a.wait_event,
    l.locktype,
    l.mode,
    l.granted,
    a.query
FROM pg_stat_activity AS a
JOIN pg_locks AS l ON l.pid = a.pid
WHERE a.datname = current_database()
ORDER BY a.pid, l.granted, l.mode;
```

Đây là truy vấn tổng quát, có thể trả nhiều rows và văn bản SQL chứa dữ liệu nhạy cảm. Trong production cần quyền phù hợp, giới hạn phạm vi và tránh xuất nguyên query có secrets ra ticket. Mục tiêu là nhận diện các lệnh ALTER/ATTACH/DETACH đang chờ lock, không phải tự động terminate mọi backend.

### 29.4. Dữ liệu test và production khác nhau

Partitioning thường chỉ lộ chi phí rõ khi dataset lớn, query mix đa dạng và nhiều concurrent transactions. Test 18.000 hàng với 3 partitions **chỉ chứng minh cơ chế**, không chứng minh một thiết kế 1.000 partitions production sẽ tốt.

## 30. Ma trận quyết định: nên hay không nên phân vùng?

Đây là bảng để thảo luận kiến trúc, **không phải hệ thống chấm điểm định lượng của PostgreSQL**.

| Tiêu chí | Tín hiệu ủng hộ partitioning | Tín hiệu nên thận trọng hoặc không partition |
| --- | --- | --- |
| **Khối lượng dữ liệu** | Dữ liệu rất lớn, tiếp tục tăng, mỗi khoảng cần quản lý riêng. | Bảng nhỏ, query nhanh với index. |
| **Query patterns** | Phần lớn hot queries có predicate phù hợp partition key. | Hot queries thường thiếu partition key, phải tìm xuyên mọi child. |
| **Retention** | Xóa/archive theo tháng/ngày/tenant nguyên khối. | Xóa từng khách/row hoặc legal hold không trùng bounds. |
| **Partition key** | Ổn định, biết được khi INSERT và trong SELECT. | Đổi thường xuyên, giá trị đến muộn/out-of-range khó quản lý. |
| **Số lượng partitions** | Hợp lý theo kích thước và overhead đo được. | Hàng nghìn/hàng chục nghìn child rất nhỏ không có pruning. |
| **Uniqueness** | PK/UNIQUE có thể chứa partition key đúng ngữ nghĩa. | Bắt buộc UNIQUE toàn cục theo ID không chứa partition key. |
| **Foreign keys** | Hệ tham chiếu chấp nhận khóa ghép và retention dependencies. | Hàng trăm FK hiện có chỉ dùng ID đơn, migration quá phức tạp. |
| **Read/write skew** | Các partitions có thể được truy cập/bảo trì riêng và giảm phạm vi thực. | Một partition vẫn chiếm phần lớn writes/reads. |
| **Operations** | Có tự động tạo trước, monitor, archive, recovery. | Phải tạo partition thủ công, không có người/luồng chịu trách nhiệm. |
| **Measurement** | Benchmark có bằng chứng cải thiện SLA/tổng chi phí. | Chưa đo plan và đang cố xử lý sự cố khác như locks/stale stats. |

### 30.1. Hướng quyết định đơn giản

```text
                   Bảng đang gặp vấn đề gì?
                              |
             +----------------+----------------+
             |                                 |
         Query chậm                    Retention/maintenance khó
             |                                 |
             v                                 v
      Đã có index/query                 Có thể tách theo
      design thích hợp?                 key/range ổn định?
          /       \                         /       \
        Chưa       Rồi                     Không     Có
        |           |                       |       |
        v           v                       v       v
   Tối ưu SQL/   Có filter trên        Cân nhắc   Đánh giá
   index trước   partition key?        archive/   partitioning
                 /        \            DELETE     theo lifecycle
               Không       Có           jobs      & costs
                |          |
                v          v
           Partition   Đo pruning
           có thể ít    và chi phí
           lợi/đắt      planning/DDL
```

### 30.2. Ba câu hỏi phải trả lời trước khi CREATE TABLE

1. **Bỏ được bao nhiêu phần dữ liệu?** Query thật có predicate nào cho phép pruning?
2. **Xử lý lifecycle nào được đơn giản hóa?** Có thể DROP/DETACH nguyên một partition đúng theo policy không?
3. **Đánh đổi nào là chấp nhận được?** Khóa duy nhất, FK, UPDATE, INSERT, operational complexity và khả năng rollback?

Nếu cả ba câu trả lời đều mơ hồ, chưa nên bắt đầu migration partitioned table.

## 31. Case study A: access log cần giữ 90 ngày

**Bối cảnh:**

- 200 triệu events/ngày.
- Các truy vấn vận hành chủ yếu đọc 1–24 giờ gần nhất.
- Quy định lưu 90 ngày, sau đó xóa theo ngày.
- Trường `occurred_at` gần như không sửa.
- ID log không cần làm unique key toàn cục để các bảng nghiệp vụ khác tham chiếu.

### 31.1. Lựa chọn ứng viên

RANGE partition theo **ngày** là ứng viên mạnh:

```text
access_logs
    +-- 2026_11_13
    +-- 2026_11_14
    +-- 2026_11_15
    +-- ... khoảng 90 ngày retention
```

### 31.2. Vì sao hợp?

- Query từ 08:00 đến 09:00 có thể prune phần lớn ngày khác.
- Dữ liệu ngày cũ có thể detach/archive/drop sau retention.
- Partition key ổn định.
- Một ngày có khối lượng rất lớn, không phải chỉ vài hàng.
- Số partition giữ hoạt động tương đối hữu hạn.

### 31.3. Vẫn phải thiết kế bổ sung

- Cách xử lý log đến trễ 2–7 ngày.
- Timezone và ranh giới ngày UTC.
- Index/BRIN bên trong partition.
- Dung lượng 90 ngày và I/O/WAL.
- Hệ thống tạo partitions trước kỳ.
- Quy trình xác minh retention/legal hold.
- Planning cost của query quét toàn bộ 90 ngày.

### 31.4. Kết luận

Đây là trường hợp partitioning có **hai lợi ích cùng lúc**: pruning và retention. Nhưng vẫn cần benchmark theo actual workload và không tự coi việc DROP partition là không có locks.

## 32. Case study B: bảng người dùng tìm theo user_id

**Bối cảnh:**

- 10 triệu users, hồ sơ được cập nhật.
- 99% requests là `WHERE user_id=?`.
- Có nhiều bảng orders, profiles, sessions tham chiếu user_id.
- Không có policy xóa toàn bộ một khoảng thời gian.
- Dữ liệu người dùng cần unique user_id toàn hệ thống.

### 32.1. Lựa chọn tốt đầu tiên

Một bảng thường với:

```sql
PRIMARY KEY (user_id)
```

và các index/query cần thiết thường là điểm xuất phát hợp lý. Phân vùng RANGE theo `created_at` sẽ làm lookup user_id không biết tháng phải xét nhiều partitions, còn unique key toàn cục theo user_id không bao gồm partition key bị ràng buộc bởi giới hạn của declarative partitioning.

### 32.2. Khi nào mới xét HASH?

Nếu đã chứng minh bảng/users writes/read contention hoặc maintenance theo khóa có vấn đề lớn, có thể đánh giá HASH theo user_id. Nhưng cần hiểu hậu quả với uniqueness, foreign keys, số partitions và khả năng thay modulus.

Việc thêm HASH partitions không tự tạo sharding qua nhiều machines.

### 32.3. Kết luận

Đối với lookup định danh toàn cục, **index đúng và schema đơn giản** thường giá trị hơn việc partition theo thời gian chỉ vì bảng lớn.

## 33. Case study C: đơn hàng với status thay đổi liên tục

**Bối cảnh:**

```text
pending -> paid -> shipped -> returned
```

- Màn hình tác nghiệp đọc nhiều đơn pending.
- Đa số đơn thay đổi status nhiều lần.
- API tra cứu theo order_id và tenant_id.
- Retention theo ngày tạo đơn, không theo status.

### 33.1. Phương án hấp dẫn nhưng có hại

LIST partition theo status để query pending chỉ đọc một partition.

**Vấn đề:** mỗi lần status đổi có thể làm row movement; nhiều nghiệp vụ không biết partition key khi tra cứu ID; thiếu partitions cho status mới có thể gây lỗi; retention theo ngày không còn dễ DROP.

### 33.2. Phương án cân bằng

Ưu tiên index:

```sql
-- Ví dụ trên một bảng orders thông thường:
CREATE INDEX idx_orders_pending
ON orders (tenant_id, created_at DESC)
WHERE status = 'pending';
```

Nếu sau này partition theo created_at vì retention thực sự quan trọng, có thể duy trì partial/composite indexes trong từng partition và chấp nhận chi phí tương ứng.

### 33.3. Kết luận

Điều kiện lọc thường gặp **không tự trở thành partition key tốt**, đặc biệt khi cột thay đổi nhiều.

## 34. Case study D: SaaS có 50.000 tenants

**Bối cảnh:**

- 50.000 tenants.
- 90% tenants có ít hàng.
- Một vài tenants tạo phần lớn traffic.
- Query chủ yếu theo tenant_id.
- Không có nhu cầu detach/drop từng tenant mỗi ngày.

### 34.1. Vì sao LIST per tenant dễ gây rủi ro?

Tạo 50.000 child tables và indexes tương ứng có thể làm metadata/catalog/planning/operational complexity rất lớn, trong khi đa số child rất nhỏ. Một tenant lớn vẫn có thể là hotspot.

### 34.2. HASH partition theo tenant?

HASH với số buckets được benchmark có thể kiểm soát số physical partitions và phù hợp tenant equality. Nhưng query cross-tenant vẫn đụng nhiều buckets, còn tenant rất lớn chỉ rơi vào một bucket.

### 34.3. Phương án khác

- Composite index `(tenant_id, key)` trên bảng thường.
- HASH partitions khi có workload đủ lớn và mục tiêu rõ.
- Tách tenant rất lớn theo chiến lược vận hành riêng nếu được phép.
- Sharding khi cần thực sự chia tài nguyên qua nhiều servers.

### 34.4. Kết luận

Không có lựa chọn duy nhất đúng. Cần workload skew, read/write mix và đo chi phí thực thay vì dùng số tenant để kết luận.

## 35. Case study E: yêu cầu xóa dữ liệu từng khách theo pháp lý

**Bối cảnh:**

- Bảng interactions giữ hai năm.
- Người dùng có quyền yêu cầu xóa dữ liệu riêng.
- Có ngoại lệ legal hold.
- Query thường theo khách hàng, đôi khi theo thời gian.

### 35.1. RANGE theo tháng giải quyết được gì?

Có thể giúp archive lịch sử theo tháng và prune query thời gian. Nhưng yêu cầu “xóa customer A trên hai năm” vẫn phải tìm và xóa các row của A trong nhiều partitions.

### 35.2. LIST per customer có hợp?

Nếu có hàng triệu khách, LIST per customer làm số partitions không khả thi về vận hành trong nhiều hệ thống. Nó cũng không tự giải quyết legal hold của một phần bản ghi.

### 35.3. Hướng thay thế

Index theo customer, workflow xóa và xác minh, retention/legal hold model, archival chính xác và observability. Partitioning có thể hỗ trợ vòng đời tháng nhưng không thay thế bài toán xóa theo chủ thể.

### 35.4. Kết luận

**Đơn vị phân vùng và đơn vị xóa không khớp** thì lợi ích DROP partition không áp dụng cho yêu cầu đó.

## 36. Chuyển bảng đang hoạt động sang partitioned table

Giả sử `orders` production hiện là bảng thường và cần chuyển thành partitioned table theo ngày. Đây là một dự án migration, không chỉ chạy `ALTER TABLE orders PARTITION BY RANGE(created_at)` trên bảng hiện hữu theo cách tưởng tượng.

### 36.1. Các bước kiến trúc

Một phương án mức cao:

1. **Khảo sát** queries, indexes, constraints, FKs, triggers, permissions, RLS và replication.
2. **Thiết kế parent mới**, khóa phân vùng, bounds, granularity và unique/PK model.
3. **Tạo partitions và indexes** theo schema phù hợp.
4. **Backfill dữ liệu lịch sử** theo các chunks có kiểm soát.
5. **Đồng bộ writes** giữa dữ liệu nguồn và bảng mới trong giai đoạn chuyển tiếp bằng cơ chế đã được đánh giá.
6. **Kiểm tra tính đầy đủ** bằng counts, checksums/đối soát nghiệp vụ và constraints.
7. **Cutover** ứng dụng với kế hoạch lock/downtime tương ứng.
8. **Theo dõi** latency, routing errors, autovacuum/ANALYZE và replication sau cutover.
9. **Có kế hoạch rollback** về mô hình cũ nếu phát sinh lỗi.
10. **Dọn cấu trúc cũ** chỉ sau khi đã xác nhận và hết thời hạn rollback cần thiết.

Không thể bảo đảm migration “zero downtime” chỉ vì dùng partitioning; cách triển khai phụ thuộc quy mô, constraints, phiên bản PostgreSQL và hệ thống xung quanh.

### 36.2. Ràng buộc cần lập kế hoạch từ đầu

- Một PK cũ `(id)` có thể không tạo được trên parent RANGE `(created_at)`.
- Các FK đang trỏ `id` phải được giải quyết nếu uniqueness đổi.
- Application ORM có thể giả định một ID là primary key duy nhất.
- Queries cũ có thể thiếu partition key nên mất lợi ích pruning.
- Batch jobs cập nhật created_at/tenant_id có thể gây row movement.
- Sequence/identity và defaults cần được chuyển đúng.
- Triggers, RLS và quyền truy cập trực tiếp child tables cần được xem lại.
- Replication/CDC pipeline có thể dựa vào tên table, replica identity và event semantics.

### 36.3. Dữ liệu không đúng bounds

Trước migration:

```sql
SELECT
    MIN(created_at),
    MAX(created_at),
    COUNT(*) FILTER (WHERE created_at IS NULL)
FROM orders;
```

Nếu partition key là `created_at`, phải xử lý hàng NULL hoặc giá trị nằm ngoài lịch. RANGE partitions thường không nhận NULL trừ khi có DEFAULT partition phù hợp. Với declarative partitioning, phần dữ liệu không match bound sẽ làm INSERT/ATTACH fail nếu không có lối xử lý.

### 36.4. Validation và sample mismatch

Chỉ kiểm tra `COUNT(*)` có thể chưa đủ: hai bảng có thể cùng row count nhưng sai rows. Hãy đối soát theo tenant/tháng, keys, checksum dữ liệu và các invariant nghiệp vụ thích hợp. Không dùng checksum một mình thay FK/uniqueness nếu schema mới đã đổi ngữ nghĩa.

### 36.5. Quyền truy cập và RLS

Vì partitions là relations vật lý riêng, cần kiểm tra quyền thao tác qua parent và qua child trực tiếp, các policies phù hợp và các job bảo trì/ETL. Không tự động cho rằng mọi thao tác vào partition con đều có cùng hành vi quyền và RLS như truy cập qua bảng cha.

### 36.6. Transaction và DDL

Các bước tạo/index/attach/cutover có lock levels và ràng buộc transaction khác nhau. Một số tùy chọn CONCURRENTLY không chạy trong transaction tường minh. Lập kế hoạch cụ thể theo major, không gộp tất cả câu SQL vào một script transaction rồi hy vọng mọi tùy chọn đều tương thích.

## 37. Những hiểu nhầm và lỗi thiết kế thường gặp

### Hiểu nhầm 1. “Bảng lớn thì chắc chắn phải phân vùng”

Không. Kích thước bảng là yếu tố đầu vào, nhưng quyết định cần dựa trên query patterns, index, retention, chi phí bảo trì và kết quả đo.

### Hiểu nhầm 2. “Partitioning luôn tăng tốc mọi SELECT”

Không. Query không lọc partition key có thể phải xét nhiều children; một query tập trung một ID có thể đơn giản hơn trên bảng thường với index global theo ID.

### Hiểu nhầm 3. “Partition pruning và Index Scan là một”

Không. Pruning chọn partitions; index scan chọn cách tìm rows trong một relation còn lại. Có thể prune tốt nhưng dùng Seq Scan trên child.

### Hiểu nhầm 4. “Càng chia nhỏ càng nhanh”

Không. Nhiều partitions rất nhỏ có thể tăng planning time, metadata/index count và operational complexity.

### Hiểu nhầm 5. “Phân vùng theo thời gian giúp WHERE event_id=? tự biết tháng”

Không, trừ khi ứng dụng có điều kiện hoặc cơ chế định tuyến khác cung cấp thông tin thời gian. Event ID đơn lẻ không mặc nhiên suy ra bound.

### Hiểu nhầm 6. “Tạo index trên parent là global index duy nhất”

Không theo mô hình declarative partitioning thông thường: index parent quản lý các index vật lý ở partitions, không phải một index xuyên toàn bộ dữ liệu có thể đảm bảo arbitrary global uniqueness theo ID ngoài partition key.

### Hiểu nhầm 7. “Có PRIMARY KEY(event_id) là đủ dù partition theo created_at”

PostgreSQL yêu cầu unique/primary-key constraint trên partitioned parent bao gồm các cột partition key thích hợp. Không tùy tiện sao chép PK cũ mà không thiết kế lại.

### Hiểu nhầm 8. “PRIMARY KEY(created_at,event_id) nghĩa event_id tự unique”

Không. Chỉ cặp được enforce. Cùng event_id với created_at khác có thể hợp lệ theo constraint ấy.

### Hiểu nhầm 9. “Một partition cho mỗi tenant luôn là multi-tenant tốt nhất”

Không. Với hàng chục nghìn tenants nhỏ, metadata/DDL/planning overhead có thể lớn; một tenant khổng lồ vẫn là hotspot.

### Hiểu nhầm 10. “HASH theo tenant tự chia một tenant lớn ra nhiều buckets”

Không. Mọi row cùng tenant_id có cùng giá trị hash key sẽ được định tuyến theo cùng bucket theo thiết kế HASH đó.

### Hiểu nhầm 11. “LIST theo status tốt vì WHERE status=... rất thường gặp”

Không nhất thiết. Status thay đổi thường xuyên có thể gây row movement giữa partitions và làm retention/query theo ID khó hơn.

### Hiểu nhầm 12. “Có DEFAULT thì không cần tạo partition tương lai”

Không. DEFAULT có thể nuốt dữ liệu đáng lẽ thuộc một partition định kỳ và làm attach/maintenance sau này tốn kém.

### Hiểu nhầm 13. “DROP một partition chỉ xóa đúng hàng đã hết hạn”

Không. Nó loại toàn bộ relation, nên bounds phải khớp retention/legal hold và dependency. DROP sai tháng có thể xóa dữ liệu vẫn phải giữ.

### Hiểu nhầm 14. “Retention rolling 90 ngày có thể DROP cả partition tháng tùy lúc”

Không chính xác. Partition tháng có thể chứa dữ liệu ở hai phía mốc 90 ngày. Phải chọn granularity/policy phù hợp hoặc có xử lý vùng rìa.

### Hiểu nhầm 15. “DETACH và DROP có cùng tác động”

Không. DETACH tách quan hệ khỏi parent nhưng vẫn giữ dữ liệu trong bảng độc lập. DROP xóa relation và dữ liệu.

### Hiểu nhầm 16. “CONCURRENTLY nghĩa là không bao giờ chờ lock”

Không. Một số thao tác DDL concurrently giảm mức chặn theo điều kiện nhưng vẫn có pha chờ, giới hạn transaction và rủi ro gián đoạn.

### Hiểu nhầm 17. “Phân vùng giúp hết bloat do transaction lâu”

Không. VACUUM trên từng partition vẫn tuân thủ MVCC visibility horizon. Transaction giữ snapshot cũ có thể cản trở cleanup trong partition liên quan.

### Hiểu nhầm 18. “Không cần index nữa vì đã có partitions”

Không. Một partition một tháng có thể chứa hàng chục triệu hàng; lookup theo tenant/order ID vẫn cần access path phù hợp.

### Hiểu nhầm 19. “Có index thì không cần partition nếu retention khó”

Index giúp tìm rows nhưng không tự thay thế quản lý DROP/archive theo khoảng lớn. Hai kỹ thuật phục vụ những mục tiêu khác nhau.

### Hiểu nhầm 20. “HASH partitions sẽ nhân write throughput lên số buckets”

Không. Trên cùng một PostgreSQL instance, I/O, WAL, CPU và contention tổng vẫn chịu giới hạn server; chỉ một số workload hưởng lợi.

### Hiểu nhầm 21. “Hai bảng chia cùng tháng thì mọi JOIN được partition-wise”

Không tự động. Còn phụ thuộc join keys, scheme, bounds, planner settings, cost và phiên bản.

### Hiểu nhầm 22. “Thay đổi partition key là UPDATE bình thường”

Không hẳn. Nó có thể cần chuyển row giữa partitions, tác động constraints/triggers/index/WAL và có thể lỗi nếu không có child đích.

### Hiểu nhầm 23. “Tạo partition xong, autoanalyze của mọi child/parent tự đúng”

Không chắc. Cần theo dõi statistics riêng của partitions và parent/inherited stats trong ngữ cảnh PostgreSQL cụ thể.

### Hiểu nhầm 24. “Việc xóa khách hàng sẽ nhanh nhờ partition theo tháng”

Không chắc. Nếu khách có dữ liệu ở mọi tháng, vẫn phải xử lý nhiều partitions theo row; DROP tháng làm mất dữ liệu khách khác.

### Hiểu nhầm 25. “Chuyển từ bảng thường sang partition chỉ là một câu ALTER”

Không. Thường phải tạo cấu trúc mới, backfill, đồng bộ writes, thay đổi PK/FK/index và cutover có kế hoạch.

### Hiểu nhầm 26. “Partitioning tự tạo read replica hoặc sharding”

Không. Declarative partitioning thông thường vẫn nằm trong cùng cluster/instance; phân phối nhiều máy là kiến trúc khác.

### Hiểu nhầm 27. “EXPLAIN chỉ cần nhìn Execution Time”

Không. Với nhiều partitions, cần xem Planning Time, pruning, số child nodes, actual rows, loops, buffers và workload concurrency.

### Hiểu nhầm 28. “Không có condition literal thì prepared statement không prune được”

Không phải luôn đúng. PostgreSQL có khả năng execution-time pruning trong các trường hợp phù hợp. Cần xem generic/custom plans và tính năng theo major.

### Hiểu nhầm 29. “Multi-column RANGE tương đương subpartition theo hai chiều”

Không. Range key nhiều cột có ngữ nghĩa thứ tự khác lưới phân vùng hai tầng; phải thiết kế cây nếu thật sự cần nhánh theo cả hai chiều.

### Hiểu nhầm 30. “Bảng cha chứa toàn bộ heap nên vẫn scan nguyên một file”

Không. Declarative partitioned parent là quan hệ logic/metadata, dữ liệu vật lý nằm ở partitions. Planner có thể prune những children không phù hợp.

### Hiểu nhầm 31. “Xóa một partition không ảnh hưởng bất kỳ đối tượng nào khác”

Không. Foreign keys, views, replication, quyền, transactions và dependencies có thể chịu ảnh hưởng. Phải có runbook trước DETACH/DROP.

### Hiểu nhầm 32. “Mọi partition nên có cùng tập index”

Không nhất thiết. Query trên hot/cold partitions có thể khác nhau và index maintenance có chi phí. Tuy nhiên nếu dùng index định nghĩa trên parent, cần hiểu sự nhất quán/quan hệ với child indexes khi thiết kế khác biệt.

### Hiểu nhầm 33. “Cứ bật partition-wise join để mọi JOIN nhanh”

Không. Kích hoạt các lựa chọn partition-wise có thể tăng planning time/memory và không giúp nếu dữ liệu/partition schemes không khớp.

### Hiểu nhầm 34. “Một kết quả nhanh trên 18.000 hàng chứng minh chiến lược production”

Không. Lab nhỏ minh họa cơ chế, phải benchmark theo số partitions, số rows, index sizes, concurrency và query mix thực tế.

## 38. Bài tập thực hành

Các bài sau dùng kiến thức và schema `partition_goal_lab`. Bài có thao tác phá dữ liệu như DETACH/DROP chỉ yêu cầu **phân tích hoặc viết câu SQL dạng comment**, không thực thi nếu không ở database lab riêng và chưa sao lưu. Với `EXPLAIN`, plan cụ thể phụ thuộc phiên bản/chi phí nên câu trả lời nêu dấu hiệu cần quan sát, không khẳng định một node duy nhất.

### Bài 1. Định nghĩa

Phân biệt partitioned table logic với các child partitions vật lý. Một bảng cha RANGE theo tháng có chứa tất cả rows trong heap của chính nó không?

### Bài 2. Ba loại partition

Cho ba bài toán: log theo thời gian, nhóm vùng địa lý ổn định, lookup theo customer_id trong một tập buckets. Ghép với RANGE/LIST/HASH và giải thích lựa chọn.

### Bài 3. Cận RANGE

Với partition từ `2026-10-01 00:00 UTC` đến `2026-11-01 00:00 UTC`, giá trị đúng `2026-11-01 00:00 UTC` có thuộc partition tháng 10 không?

### Bài 4. Pruning theo thời gian

Viết truy vấn đếm events từ đầu tháng 10 tới trước đầu tháng 11 và dự đoán partition nào sẽ được xét.

### Bài 5. Không có partition key

Vì sao `WHERE tenant_id=3` trên bảng partition theo occurred_at vẫn có thể cần truy cập nhiều tháng?

### Bài 6. Partition pruning khác index

Một query chỉ đọc partition tháng 10 nhưng dùng Seq Scan. Có thể kết luận pruning không hoạt động không?

### Bài 7. Không có partition tháng mới

Điều gì xảy ra khi INSERT một event tháng 12 vào parent chỉ có child tháng 9–11 và không có DEFAULT?

### Bài 8. DEFAULT

DEFAULT partition có lợi ích và rủi ro gì? Vì sao nên giám sát số hàng/tuổi dữ liệu của nó?

### Bài 9. Kiểm tra physical relation

Viết truy vấn dùng `tableoid::regclass` để thống kê số row theo từng child partition.

### Bài 10. Thêm index

Với truy vấn `WHERE tenant_id=? AND occurred_at >= ? AND occurred_at < ? ORDER BY occurred_at DESC`, đề xuất một index phù hợp trên parent và giải thích nó hỗ trợ pruning hay scan trong partition.

### Bài 11. Primary key

Tại sao `PRIMARY KEY(event_id)` có thể không được khai báo trên parent RANGE partition theo occurred_at? `PRIMARY KEY(occurred_at,event_id)` đảm bảo điều gì?

### Bài 12. Hai row cùng event_id

Nếu hai row có event_id=999 nhưng occurred_at khác tháng, constraint `PRIMARY KEY(occurred_at,event_id)` có cấm chúng không?

### Bài 13. Foreign key

Một bảng notes cần tham chiếu sự kiện trên parent với primary key hai cột. Nó phải lưu những cột nào để tham chiếu trực tiếp một row theo khóa đó?

### Bài 14. Đơn hàng đổi status

Phân tích vì sao LIST partition theo status có thể không phù hợp với hệ thống đơn thường chuyển pending→paid→shipped.

### Bài 15. Tenant skew

Tenant A chiếm 90% rows. HASH theo tenant_id với 16 buckets có chia đều rows của tenant A vào 16 partitions không?

### Bài 16. Số lượng child

Với retention ba năm, so sánh số partitions xấp xỉ khi chia tháng, ngày và giờ. Phương án nào luôn nhanh hơn?

### Bài 17. Retention 90 ngày

Ngày 14/11, một chính sách “xóa ngay sau đúng 90 ngày” có thể DROP nguyên partition tháng 8 an toàn không? Cần xem điều gì?

### Bài 18. DETACH và DROP

Phân biệt tác động của `DETACH PARTITION` và `DROP TABLE partition` đối với dữ liệu và khả năng query qua parent.

### Bài 19. Vấn đề MVCC

Một transaction REPEATABLE READ cũ giữ snapshot trong lúc UPDATE trên partition tháng 10. Có thể kỳ vọng autovacuum dọn mọi old tuple versions chỉ vì bảng partitioned không?

### Bài 20. Query aggregate toàn lịch sử

Vì sao `SELECT tenant_id,COUNT(*) ... GROUP BY tenant_id` vẫn có thể phải đọc nhiều partitions? Nêu một hướng thay thế nếu dashboard cần số tổng hợp với độ trễ chấp nhận được.

### Bài 21. Partition-wise JOIN

Hai bảng phân vùng khác scheme có chắc được JOIN từng child tương ứng không? Cần kiểm tra những yếu tố gì?

### Bài 22. Xem cây partition

Viết query đọc `pg_partition_tree` để liệt kê relation, parent, leaf và level.

### Bài 23. Size theo partition

Viết query hiển thị `pg_total_relation_size` của từng leaf partition trong schema lab.

### Bài 24. Đọc EXPLAIN

Một query chỉ lọc tháng 10 và có `Planning Time=120 ms`, `Execution Time=4 ms`. Cần điều tra thêm điểm nào nếu số partitions tăng mạnh?

### Bài 25. So index với partition

Bảng users 5 triệu rows, query chủ yếu `WHERE user_id=?` và có primary key user_id. Có nên chuyển sang RANGE partition theo created_at để tối ưu lookup này ngay không?

### Bài 26. CREATE INDEX không phải sharding

Giải thích tại sao 64 hash partitions trên một PostgreSQL instance không đồng nghĩa 64 machines hoặc throughput ghi gấp 64.

### Bài 27. Prepared statement và pruning

Khi `WHERE occurred_at >= $1 AND occurred_at < $2`, PostgreSQL có thể prune ở những giai đoạn nào? Làm sao kiểm tra trên generic plan?

### Bài 28. Granularity phù hợp

Một bảng log có 100 rows/ngày và phải giữ 10 năm. Chia theo phút có hợp lý không? Nêu ít nhất ba chi phí phải xét.

### Bài 29. Late-arriving events

Partition tháng 9 đã drop theo retention, nhưng sự kiện mới đến có occurred_at tháng 9. Những chính sách xử lý nào cần được định nghĩa trước?

### Bài 30. Migration

Một bảng orders đang có PK(order_id), nhiều FK đến order_id và muốn RANGE partition theo created_at. Nêu ba trở ngại đầu tiên và một trình tự migration ở mức cao.

### Bài 31. Quy trình chọn partition key

Một hệ thống vừa query theo tenant_id vừa query theo occurred_at, retention theo tháng. So sánh RANGE thời gian + local composite index với HASH tenant, có nên dùng subpartition ngay không?

### Bài 32. Phân tích case study

Hệ thống gồm: 300 triệu events/ngày, giữ 60 ngày, 95% queries đọc 24 giờ gần nhất, event_time gần như bất biến. Phân vùng có đáng cân nhắc? Theo tiêu chí nào?

## 39. Gợi ý lời giải

### Đáp án 1. Bảng cha và partitions

Partitioned parent đại diện bảng logic và định nghĩa phân vùng, các child partitions là nơi lưu heap rows vật lý. Không nên hình dung parent chứa thêm một bản sao heap của tất cả child rows.

### Đáp án 2. RANGE/LIST/HASH

| Bài toán | Kiểu phù hợp để xem xét | Lý do |
| --- | --- | --- |
| Log theo tháng/ngày | RANGE thời gian | Dễ prune theo thời gian và áp retention nguyên khoảng. |
| Nhóm region ổn định | LIST | Query theo region có thể prune nhóm khác. |
| Lookup theo customer_id trong số buckets hữu hạn | HASH(customer_id) | Equality theo ID có thể định tuyến bucket. |

Không kết luận các lựa chọn ấy bắt buộc trong mọi bảng; có thể một index trên bảng thường đã đủ.

### Đáp án 3. Cận RANGE

Không. Khoảng `FROM ... TO ...` có **cận dưới bao gồm, cận trên không bao gồm** theo cách khai báo RANGE PostgreSQL thông thường. Giá trị chính xác ngày 01/11 00:00 UTC thuộc partition tiếp theo nếu có.

### Đáp án 4. Pruning tháng 10

```sql
SELECT COUNT(*)
FROM partition_goal_lab.events
WHERE occurred_at >= TIMESTAMPTZ '2026-10-01 00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-11-01 00:00+00';
```

PostgreSQL có đủ thông tin để loại các partition ngoài tháng 10 khi bounds phù hợp; query còn có thể dùng Seq Scan hoặc Index Scan trên partition tháng 10 tùy chi phí.

### Đáp án 5. Tenant khác partition key

Partition key là `occurred_at`. Vì tenant 3 có thể có sự kiện ở mọi tháng, chỉ `tenant_id=3` không chứng minh được partition thời gian nào rỗng đối với query. Index theo tenant trong children có thể hữu ích nhưng không đồng nghĩa prune tháng.

### Đáp án 6. Seq Scan trên child

Không. Pruning có thể đã chọn đúng partition và một Seq Scan trên partition ấy là kế hoạch rẻ nhất. Cần xem số child nodes trong `EXPLAIN`, không dùng sự hiện diện của Seq Scan làm kết luận.

### Đáp án 7. Thiếu partition

INSERT không tìm được destination partition phù hợp và báo SQL error nếu không có DEFAULT. Nếu đang trong transaction tường minh, cần rollback hoặc recovery phù hợp trước khi gửi câu SQL mới.

### Đáp án 8. DEFAULT

DEFAULT giúp nhận out-of-range rows nhưng có thể che lỗi tạo partition mới, tích tụ hàng lớn và làm attach partition sau này cần kiểm tra/chuyển dữ liệu. Theo dõi số rows, bounds ngoài dự kiến và lịch tạo partition.

### Đáp án 9. tableoid

```sql
SELECT
    tableoid::regclass AS partition_name,
    COUNT(*) AS row_count
FROM partition_goal_lab.events
GROUP BY tableoid
ORDER BY tableoid::regclass::text;
```

`tableoid` cho biết relation vật lý; trên lab mới có ba partitions và 6.000 rows/partition trước khi thêm tháng 12.

### Đáp án 10. Index

```sql
CREATE INDEX idx_exercise_tenant_occurred
ON partition_goal_lab.events
    (tenant_id, occurred_at DESC);
```

Đây là candidate index cho điều kiện tenant equality, range thời gian và sort thời gian. **Partition pruning** đến từ điều kiện occurred_at và bounds của parent; index giúp tìm trong các partition còn được chọn.

### Đáp án 11. Primary key

Unique/PK trên partitioned parent cần gồm các cột partition key theo những quy tắc PostgreSQL tương ứng, vì index local không tự enforce unique theo event_id xuyên mọi tháng. `PRIMARY KEY(occurred_at,event_id)` bảo vệ cặp, không bảo vệ event_id đơn lẻ.

### Đáp án 12. Trùng event_id khác thời gian

Không cấm, miễn hai cặp `(occurred_at,event_id)` khác nhau. Nếu business yêu cầu event_id unique toàn cục, schema hiện tại không enforce điều đó.

### Đáp án 13. Foreign key

Bảng con phải lưu cả giá trị `event_occurred_at` và `event_id` và khai báo foreign key ghép tham chiếu `(occurred_at,event_id)` của parent.

```sql
FOREIGN KEY (event_occurred_at, event_id)
REFERENCES partition_goal_lab.events (occurred_at, event_id)
```

### Đáp án 14. Status mutable

Mỗi thay đổi status có thể chuyển row giữa LIST partitions, tăng công việc ghi/index và đòi partition đích tồn tại. Partial/composite index trên bảng thường có thể phục vụ SELECT pending mà tránh row movement do partition key.

### Đáp án 15. Hash và skew

Không. Nếu hash key chỉ là `tenant_id`, mọi row của tenant A cùng giá trị key có cùng kết quả hash/bucket theo thiết kế. Tenant A vẫn có thể làm một bucket rất nóng.

### Đáp án 16. Số lượng children

Với ba năm:

- Theo tháng: khoảng 36 partitions.
- Theo ngày: khoảng 1.095 partitions.
- Theo giờ: khoảng 26.280 partitions.

Không có phương án nào luôn nhanh hơn; cần đo tỷ lệ pruning, số rows/partition, planning overhead, indexes và retention.

### Đáp án 17. Rolling retention

Không mặc định. Partition tháng 8 chứa cả dữ liệu đầu và cuối tháng; một phần có thể vẫn trong 90 ngày tùy thời điểm tính. Cần kiểm tra ngưỡng chính xác, timezone, legal hold, granularity và chính sách xử lý phần rìa.

### Đáp án 18. DETACH vs DROP

`DETACH` gỡ partition khỏi parent nhưng bảng độc lập còn dữ liệu; `DROP TABLE` xóa relation/dữ liệu. Cả hai đều là DDL có lock/dependency cần quản lý.

### Đáp án 19. MVCC

Không. VACUUM vẫn không được loại old tuple versions còn cần cho snapshot đang tồn tại, dù bảng đã chia child partitions.

### Đáp án 20. Aggregate toàn lịch sử

Không có điều kiện partition key cho phép bỏ những tháng khác; planner phải xử lý dữ liệu từ các partitions phù hợp để tính tổng. Một materialized view hoặc summary table cập nhật theo lịch/luồng có thể phục vụ dashboard nhanh nếu chấp nhận độ trễ và có cơ chế đồng bộ.

### Đáp án 21. Partition-wise JOIN

Không chắc. Phải xem partition keys, bounds, schemes, JOIN conditions, planner settings, chi phí và PostgreSQL major. Hai bảng chia khác key không tự thành các cặp partitions tương ứng.

### Đáp án 22. Cây partition

```sql
SELECT
    relid::regclass AS relation_name,
    parentrelid::regclass AS parent_name,
    isleaf,
    level
FROM pg_partition_tree(
    'partition_goal_lab.events'::regclass
)
ORDER BY level, relid::regclass::text;
```

### Đáp án 23. Size theo child

```sql
SELECT
    relid::regclass AS leaf_name,
    pg_size_pretty(
        pg_total_relation_size(relid)
    ) AS total_size
FROM pg_partition_tree(
    'partition_goal_lab.events'::regclass
)
WHERE isleaf
ORDER BY pg_total_relation_size(relid) DESC;
```

### Đáp án 24. Planning Time

Planning Time đã lớn hơn Execution Time nhiều lần. Cần xem số partitions, số nodes được lập plan, pruning ở planning/execution, generic/custom plans, frequency queries, memory và hiệu ứng khi tăng child count. Đừng chỉ cải thiện index scan vì execution đã nhanh.

### Đáp án 25. Bảng users

Không nên partition RANGE theo created_at chỉ để tối ưu lookup user_id. Primary key/index trên user_id có thể trả trực tiếp row; partitioning theo ngày tạo còn gây vấn đề định tuyến query và uniqueness/FK.

### Đáp án 26. Hash không phải sharding

Các partitions vẫn thuộc cùng PostgreSQL instance/cluster; chia physical relations không nhân bản CPU/disk/WAL writer thành 64 máy. Workload có thể hưởng lợi từ bố cục dữ liệu nhưng tổng tài nguyên vẫn chịu giới hạn hệ thống.

### Đáp án 27. Prepared pruning

Có thể xảy ra ở planning time khi biết giá trị phù hợp hoặc execution time cho các tham số trong plan hỗ trợ. Để thử generic plan:

```sql
PREPARE exercise_by_time(timestamptz, timestamptz) AS
SELECT COUNT(*)
FROM partition_goal_lab.events
WHERE occurred_at >= $1
  AND occurred_at <  $2;

BEGIN;
SET LOCAL plan_cache_mode = force_generic_plan;

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE exercise_by_time(
    TIMESTAMPTZ '2026-10-01 00:00+00',
    TIMESTAMPTZ '2026-11-01 00:00+00'
);

ROLLBACK;
DEALLOCATE exercise_by_time;
```

Quan sát `Subplans Removed` hoặc nodes không chạy tùy PostgreSQL major và plan thực tế.

### Đáp án 28. Partition theo phút

Không hợp lý trong hầu hết thiết kế với 100 rows/ngày và 10 năm retention. Số partitions cực lớn, metadata và indexes nhiều, planning và DDL/backup/monitoring phức tạp; query không có filter tương ứng phút cũng không được lợi. Có thể xét bảng thường hoặc partition theo tháng/năm nếu retention thực sự cần.

### Đáp án 29. Event đến trễ

Cần xác định:

- Chấp nhận hay từ chối late data?
- Partition cũ được giữ thêm thời gian grace period không?
- Sử dụng event time hay ingestion time?
- Có DEFAULT/quarantine table hay luồng backfill riêng không?
- Phải khôi phục/archive cũ hay đã bị xóa không?
- Retention/legal hold có cho phép lưu sự kiện cũ đến muộn không?

Không để routing error tự biến thành mất dữ liệu âm thầm.

### Đáp án 30. Migration với PK/FK

Ba trở ngại:

1. PK(order_id) có thể không khai báo trên parent partition theo created_at vì thiếu partition key.
2. Nhiều FK chỉ tham chiếu order_id cần mô hình khóa/quan hệ mới hoặc phương án thay thế.
3. Query API theo order_id không biết created_at có thể phải tìm xuyên partitions.

Trình tự: khảo sát → thiết kế PK/partition bounds → tạo bảng/các child và indexes → backfill → đồng bộ writes → validate → cutover có kiểm soát → theo dõi và giữ rollback plan.

### Đáp án 31. Tenant + time

RANGE theo thời gian phù hợp retention tháng, local composite `(tenant_id,occurred_at)` phục vụ truy vấn tenant trong tháng. HASH tenant phù hợp tenant equality nhưng không cho phép DROP tháng nguyên vẹn nếu không có cấu trúc thời gian khác. Subpartition có thể hỗ trợ cả hai nhưng tăng children và overhead; chỉ chọn sau benchmark và xem số rows/query patterns thật.

### Đáp án 32. Events rất lớn với retention ngắn

Đáng cân nhắc mạnh RANGE theo ngày hoặc một granularity phù hợp, vì:

- Dữ liệu cực lớn mỗi ngày.
- Phần lớn query lọc cửa sổ gần đây.
- Partition key gần như bất biến.
- Policy giữ 60 ngày khớp lifecycle theo ngày.
- Có thể quản lý hot/cold và DETACH/DROP theo ngày.

Vẫn phải tính số bytes/day, index, I/O/WAL, timezone, late events, replication, DDL locks và tổ chức vận hành. Không hứa throughput đọc/ghi tăng bao nhiêu nếu chưa đo.

## 40. Checklist trước quyết định phân vùng

1. **Mục tiêu:** cần pruning, retention, maintenance hay đang muốn giải một bottleneck không liên quan?
2. **Query evidence:** có 10–20 hot queries cùng parameter distributions và latency thực tế không?
3. **Partition key:** query có lọc đúng key đó thường xuyên và rõ ràng không?
4. **Routing:** INSERT biết key và luôn có child phù hợp không?
5. **Stability:** key có bị UPDATE làm row movement thường xuyên không?
6. **Bounds:** RANGE boundaries và timezone được định nghĩa rõ chưa?
7. **Retention:** chính sách xóa/archive có khớp trọn partition không?
8. **Late data:** sẽ làm gì với event đến trễ hoặc timestamp sai?
9. **Child count:** bao nhiêu partitions trong một năm, ba năm, toàn retention?
10. **Index design:** có index phù hợp bên trong những partitions còn lại không?
11. **Uniqueness:** PK/UNIQUE có thể gồm partition key mà vẫn đúng nghiệp vụ không?
12. **FKs:** những bảng tham chiếu có chấp nhận composite key và partition lifecycle không?
13. **UPSERT:** conflict target có đúng constraint và có update partition key không?
14. **Skew:** tenant/time buckets có tương đối cân bằng hay một child chiếm đa số?
15. **Cross-partition queries:** aggregate/JOIN/sort toàn lịch sử có chiếm phần lớn workload không?
16. **Planning cost:** đã đo Planning Time khi số child đủ đại diện chưa?
17. **Concurrency:** đã benchmark SELECT/INSERT/UPDATE cùng lúc chưa?
18. **Statistics:** parent/child ANALYZE và partition pruning có được kiểm chứng chưa?
19. **Vacuum:** đã phân biệt MVCC blocker với vấn đề partition count chưa?
20. **Automation:** có job tạo partitions tương lai và cảnh báo default growth không?
21. **Archival:** có backup, legal hold và quy trình recover trước DROP không?
22. **Permissions/RLS:** có kiểm soát truy cập cả parent và child nếu cần không?
23. **Replication/CDC:** downstream có theo dõi đúng dữ liệu khi attach/detach/drop không?
24. **Migration:** có backfill, dual-write/CDC sync, cutover và rollback plan không?
25. **Alternatives:** đã thử composite B-tree, BRIN, partial index, query rewrite hay summary table chưa?
26. **SLA:** có số đo sau thay đổi đủ chứng minh lợi ích lớn hơn operational cost không?

## 41. Tổng kết

**Partitioning là chiến lược tổ chức dữ liệu và vòng đời lưu trữ, không phải phép tăng tốc mặc định.** Nó đặc biệt phù hợp khi workload có hai đặc trưng: **truy vấn thường xuyên lọc theo partition key** và/hoặc **dữ liệu có thể quản lý/xóa nguyên từng khoảng partition**.

Những điều cần nhớ:

- **RANGE** thích hợp dữ liệu theo thời gian và retention; **LIST** thích hợp tập giá trị ổn định; **HASH** thích hợp equality key và phân phối theo buckets khi có mục tiêu rõ.
- **Partition pruning** loại children không thể chứa kết quả. Nó không thay thế B-tree/BRIN, statistics hoặc tối ưu truy vấn bên trong child.
- **Một bảng lớn không tự đòi partitioning.** Bảng thường với index tốt có thể đơn giản, nhanh và dễ bảo trì hơn.
- **Query thiếu partition key** có thể phải xét nhiều partitions; chia quá nhiều child làm tăng planning/metadata overhead.
- **Partition key biến động** có thể khiến UPDATE di chuyển hàng giữa partitions, tăng chi phí và rủi ro.
- **Unique/PK và FK** phải được thiết kế lại cẩn thận nếu muốn giữ định danh toàn cục nhưng partition key khác ID.
- **Retention chỉ đơn giản khi đơn vị xóa trùng với partition bounds.** DROP partition không an toàn nếu còn dữ liệu phải giữ, legal hold hoặc references.
- **Default partition là đường dự phòng**, không thay cho việc tạo child đúng hạn và giám sát late/out-of-range data.
- **Partitioning không tự giải bloat do snapshot cũ, không tự sửa query xấu và không tự biến một instance thành sharded cluster.**
- **Đo pruning, Planning Time, Execution Time, buffers và write/DDL overhead** với query mix đại diện trước khi migration.
- **Vận hành là một phần thiết kế:** tạo partition tương lai, ANALYZE, quản lý indexes, attach/detach, backup/archive, giám sát locks và rollback plan phải có chủ sở hữu rõ ràng.

Nguyên tắc thiết kế cuối cùng:

> **Đừng phân vùng chỉ vì bảng lớn. Hãy phân vùng khi bạn có thể nêu chính xác phần dữ liệu nào sẽ được bỏ qua khi truy vấn, phần dữ liệu nào sẽ được quản lý độc lập và vì sao lợi ích đó đáng giá hơn chi phí thêm của nhiều relations.**

Khi không có bằng chứng rõ cho ít nhất một mục tiêu trên, bắt đầu bằng index/query optimization và đo workload thực tế thường là lựa chọn an toàn hơn.







