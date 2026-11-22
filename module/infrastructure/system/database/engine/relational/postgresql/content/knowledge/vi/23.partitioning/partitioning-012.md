# Đánh giá kế hoạch, khóa và bảo trì trên hệ thống phân vùng trong PostgreSQL

## 1. Vì sao một bảng đã phân vùng vẫn có thể chậm hoặc bị khóa?

Hãy hình dung bảng giao dịch chứa hàng trăm triệu dòng, được phân vùng (*partitioning*) theo tháng. Một báo cáo chỉ cần dữ liệu tháng 2, nhưng kế hoạch truy vấn vẫn xuất hiện nhiều bảng con. Một đợt thêm phân vùng tháng mới làm câu lệnh ghi đang chạy phải chờ. Một phân vùng cũ không còn được ghi vẫn tăng dung lượng hoặc thiếu thống kê. Một thao tác `DROP TABLE` nhằm dọn dữ liệu lịch sử lại chờ một giao dịch đọc lâu.

Tất cả đều có thể xảy ra vì **phân vùng không tự thay thế tối ưu truy vấn, quản lý khóa và bảo trì**.

Ba câu hỏi cần trả lời khi vận hành hệ thống PostgreSQL phân vùng là:

1. **Kế hoạch:** planner có loại đúng các phân vùng không cần đọc không? Trong từng phân vùng còn chọn scan, join, aggregate và index như thế nào?
2. **Khóa:** một câu SELECT, INSERT, DDL hoặc thao tác `ATTACH`/`DETACH` có thể ảnh hưởng bảng cha và những phân vùng nào? Ai đang chặn ai?
3. **Bảo trì:** thống kê, VACUUM, index, dung lượng và vòng đời lưu giữ dữ liệu được quản lý ở bảng cha và từng phân vùng ra sao?

Mô hình cần ghi nhớ:

```text
                    sales (partitioned parent)
                            |
          +-----------------+-----------------+
          |                 |                 |
          v                 v                 v
     sales_2026_01     sales_2026_02     sales_2026_03 ...
       Jan rows          Feb rows          Mar rows
          |                 |                 |
       local index       local index       local index
          |                 |                 |
       VACUUM /          VACUUM /          VACUUM /
       ANALYZE            ANALYZE            ANALYZE
          \                 |                 /
           +----------------+----------------+
                            |
                 Parent query / DDL / locks
```

Một câu `SELECT * FROM sales` truy cập **bảng phân vùng logic**. Các hàng thực tế được lưu ở **những phân vùng lá (*leaf partitions*)**, không nằm trong heap của bảng cha dạng partitioned table.

> **Điểm chính:** partition pruning giúp tránh đọc những partition không liên quan, nhưng không bảo đảm mỗi partition còn lại có plan tốt; DDL quản lý partition có thể cần khóa mạnh; và công việc VACUUM/ANALYZE/index cần được quan sát ở đúng cấp.

## 2. Mục tiêu bài học

Sau bài này, bạn có thể:

1. Đọc cấu trúc bảng cha, partition bounds, bảng con và local indexes.
2. Giải thích sự khác nhau giữa **partition pruning** và **index scan**.
3. Đọc `Append`, `Merge Append`, `Parallel Append` cùng các scan nodes của từng partition.
4. Phân biệt pruning ở **planning time**, **initialization time** và **execution time**.
5. Hiểu tác dụng của literal constants, bind parameters và generic prepared plans.
6. Nhận biết điều kiện WHERE khiến pruning không đạt kỳ vọng.
7. Hiểu giới hạn và đánh đổi của partitionwise join/aggregate.
8. Đánh giá index trên partitioned parent và từng leaf partition.
9. Giải thích tác động khóa của SELECT/INSERT/UPDATE và các thao tác DDL liên quan partition.
10. Quan sát phiên chờ khóa bằng `pg_locks`, `pg_stat_activity`, `pg_blocking_pids`.
11. Lập kế hoạch `ATTACH PARTITION`, `DETACH PARTITION` và `DROP` an toàn hơn.
12. Hiểu giới hạn của `CREATE INDEX CONCURRENTLY` trên bảng phân vùng.
13. Phân biệt thống kê bảng cha/partition, thiết lập `ANALYZE` và autovacuum.
14. Theo dõi bloat, dead tuples, index usage và dung lượng theo partition.
15. Lập quy trình retention/archive theo partition có rollback và kiểm soát dữ liệu đến muộn.
16. Dùng EXPLAIN và số liệu thực tế để kiểm chứng cải thiện thay vì giả định partitioning luôn nhanh.

## 3. Declarative partitioning hoạt động như thế nào?

PostgreSQL hỗ trợ declarative partitioning bằng:

- `PARTITION BY RANGE`: chia theo các khoảng giá trị, ví dụ tháng.
- `PARTITION BY LIST`: chia theo danh sách giá trị, ví dụ khu vực hoặc loại dữ liệu.
- `PARTITION BY HASH`: chia theo hash của partition key.

Ví dụ:

```sql
CREATE TABLE sales (
    sold_on date NOT NULL,
    sale_id bigint NOT NULL,
    amount numeric(12,2) NOT NULL
) PARTITION BY RANGE (sold_on);
```

Tạo bảng con:

```sql
CREATE TABLE sales_2026_01 PARTITION OF sales
FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');

CREATE TABLE sales_2026_02 PARTITION OF sales
FOR VALUES FROM ('2026-02-01') TO ('2026-03-01');
```

Với RANGE, biên `FROM` **bao gồm**, còn biên `TO` **không bao gồm**:

```text
sales_2026_01: [2026-01-01, 2026-02-01)
sales_2026_02: [2026-02-01, 2026-03-01)
```

### 3.1. Bảng cha khác bảng thường

Bảng cha khai báo `PARTITION BY` là quan hệ logic quản lý phân vùng. Khi chèn qua bảng cha, PostgreSQL định tuyến hàng tới bảng con phù hợp với partition key.

Vì bảng cha không phải heap chứa các hàng đã phân vùng, một số số liệu như:

```sql
SELECT pg_relation_size('schema.sales'::regclass);
```

**không phải tổng dữ liệu** của mọi partition. Muốn biết tổng dung lượng, phải cộng qua các leaf relations và index/toast của chúng.

### 3.2. Partition là bảng thật

Một leaf partition có:

- Heap pages của riêng nó.
- Indexes gắn với nó.
- Statistics và trạng thái VACUUM của riêng nó.
- Catalog metadata và quan hệ khóa riêng.
- Dung lượng dữ liệu/TOAST riêng khi có.

Vì thế, bảo trì không thể chỉ nhìn “một bảng sales” trong dashboard.

### 3.3. Partitioning không phải sharding

Các partition trong bài cùng thuộc một PostgreSQL database và do cùng hệ thống quản lý. Chúng không tự động phân phối dữ liệu sang các cluster khác như sharding.

Việc đặt partition trên tablespace khác cũng không biến partitioning thành một bộ điều phối cluster phân tán.

## 4. Dựng phòng thí nghiệm theo tháng

Thực hành trong **database thử nghiệm**. Các lệnh nạp dữ liệu, tạo index và DDL có chi phí tài nguyên; không áp dụng trực tiếp lên production.

### 4.1. Tạo schema

```sql
CREATE SCHEMA IF NOT EXISTS part_eval_lab;
```

### 4.2. Tạo bảng cha với khóa chính hợp lệ

```sql
CREATE TABLE part_eval_lab.sales (
    sale_id bigint GENERATED ALWAYS AS IDENTITY,
    sold_on date NOT NULL,
    tenant_id integer NOT NULL,
    status text NOT NULL
        CHECK (status IN ('PENDING', 'PAID', 'CANCELLED')),
    amount numeric(12,2) NOT NULL
        CHECK (amount >= 0),
    note text NOT NULL,
    PRIMARY KEY (sold_on, sale_id)
) PARTITION BY RANGE (sold_on);
```

**Vì sao PRIMARY KEY là `(sold_on, sale_id)`?**

PostgreSQL không có một global unique index thông thường trải qua mọi phân vùng như một heap index duy nhất. Một PRIMARY KEY/UNIQUE constraint khai báo trên partitioned table phải bao gồm các cột partition key theo những điều kiện PostgreSQL hỗ trợ, để sự duy nhất có thể được thực thi bởi indexes của các partition.

Trong ví dụ, `sold_on` là partition key. `PRIMARY KEY (sold_on, sale_id)` phù hợp.

`sale_id` được cấp từ identity sequence, nhưng **không coi sequence một mình là ràng buộc global uniqueness** cho mọi đường ghi dữ liệu hoặc migration. Nếu nghiệp vụ cần một ID duy nhất toàn cục độc lập ngày, phải thiết kế cơ chế đảm bảo phù hợp thay vì tưởng có thể tạo ngay `UNIQUE (sale_id)` trên parent RANGE-partitioned theo `sold_on`.

### 4.3. Tạo bốn partition

```sql
CREATE TABLE part_eval_lab.sales_2026_01
PARTITION OF part_eval_lab.sales
FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');

CREATE TABLE part_eval_lab.sales_2026_02
PARTITION OF part_eval_lab.sales
FOR VALUES FROM ('2026-02-01') TO ('2026-03-01');

CREATE TABLE part_eval_lab.sales_2026_03
PARTITION OF part_eval_lab.sales
FOR VALUES FROM ('2026-03-01') TO ('2026-04-01');

CREATE TABLE part_eval_lab.sales_2026_04
PARTITION OF part_eval_lab.sales
FOR VALUES FROM ('2026-04-01') TO ('2026-05-01');
```

Thêm DEFAULT partition để nghiên cứu dữ liệu không khớp khoảng:

```sql
CREATE TABLE part_eval_lab.sales_default
PARTITION OF part_eval_lab.sales DEFAULT;
```

Không đặt các khoảng biên chồng lấn nhau. `DEFAULT` nhận những hàng chưa thuộc các partition khai báo.

### 4.4. Sinh 120.000 hàng qua bảng cha

```sql
INSERT INTO part_eval_lab.sales (
    sold_on, tenant_id, status, amount, note
)
SELECT
    DATE '2026-01-01' + ((g - 1) % 120),
    CASE
        WHEN g % 5 IN (0, 1, 2, 3) THEN 1
        ELSE 2 + ((g / 5) % 400)
    END,
    CASE
        WHEN g % 17 = 0 THEN 'CANCELLED'
        WHEN g % 7  = 0 THEN 'PENDING'
        ELSE 'PAID'
    END,
    ((g * 31) % 100000)::numeric / 100,
    repeat('sale-note-', 8) || g::text
FROM generate_series(1, 120000) AS s(g);
```

Phân bố thời gian:

- `2026-01-01` đến `2026-04-30` là đúng **120 ngày** của bốn tháng đầu năm 2026.
- Mỗi ngày có 1.000 hàng theo cách sinh dữ liệu.
- Tenant 1 chiếm khoảng 80% hàng.
- Những tenant còn lại chia phần nhỏ hơn.

Bộ dữ liệu vừa phục vụ đánh giá **partition pruning theo ngày/tháng**, vừa dùng để quan sát tác động của **selectivity theo tenant** trong từng partition.

### 4.5. Thu thập thống kê

```sql
ANALYZE part_eval_lab.sales;
```

Dữ liệu được chèn qua parent, nhưng thực tế nằm ở các leaves. Sau `ANALYZE`, có thể thử `EXPLAIN` với thống kê tương ứng.

### 4.6. Kiểm tra hàng trong từng partition

```sql
SELECT
    tableoid::regclass AS physical_partition,
    COUNT(*) AS rows_in_partition,
    MIN(sold_on) AS first_date,
    MAX(sold_on) AS last_date
FROM part_eval_lab.sales
GROUP BY tableoid
ORDER BY physical_partition;
```

Kỳ vọng có dữ liệu ở bốn partition tháng. `sales_default` không có hàng từ đợt sinh này.

`tableoid` cho biết OID của **bảng vật lý** chứa tuple, nên `tableoid::regclass` giúp quan sát row routing. Không dùng `tableoid` làm khóa chính nghiệp vụ.

## 5. Kiểm tra cây phân vùng và partition bounds

Trước khi đọc EXPLAIN, phải biết schema thật sự có những partition nào.

### 5.1. `pg_partition_tree`

```sql
SELECT
    relid::regclass AS relation_name,
    parentrelid::regclass AS parent_name,
    isleaf,
    level
FROM pg_partition_tree(
    'part_eval_lab.sales'::regclass
)
ORDER BY level, relation_name;
```

Trên phiên bản hỗ trợ `pg_partition_tree`, kết quả gồm parent (level 0) và những descendants.

- `relid`: relation OID.
- `parentrelid`: parent của node, NULL ở root.
- `isleaf`: true nếu node không tiếp tục phân vùng.
- `level`: độ sâu trong cây.

### 5.2. Xem bounds từ catalog

```sql
SELECT
    i.inhrelid::regclass AS child_partition,
    pg_get_expr(
        child.relpartbound,
        child.oid
    ) AS partition_bound
FROM pg_inherits AS i
JOIN pg_class AS child
  ON child.oid = i.inhrelid
WHERE i.inhparent = 'part_eval_lab.sales'::regclass
ORDER BY child.relname;
```

`pg_inherits` lưu quan hệ inheritance/partition hierarchy. Với declarative partitions, thông tin `relpartbound` thể hiện ranh giới phân vùng.

### 5.3. Mở trong psql

Trong `psql`, lệnh:

```text
\d+ part_eval_lab.sales
```

có thể hiển thị định nghĩa partition key, partition list và indexes tùy phiên bản. Đây là lệnh client của psql, **không phải SQL** để gửi qua JDBC.

### 5.4. Lỗi thường gặp: partition mới chưa thực sự được attach

Một bảng tên `sales_2026_05` **không tự trở thành partition** chỉ vì trùng quy tắc tên. Nó phải được tạo bằng `PARTITION OF` hoặc attach bằng `ALTER TABLE ... ATTACH PARTITION`.

Nếu `pg_partition_tree` không có node đó, query qua parent sẽ không tự truy cập bảng rời chỉ có tên gần giống.

## 6. Kế hoạch truy vấn: đọc `Append` trước tiên

Một truy vấn nhiều partition thường được thể hiện bằng node `Append` hoặc cấu trúc tương ứng.

Ví dụ:

```sql
EXPLAIN
SELECT sale_id, sold_on, tenant_id, amount
FROM part_eval_lab.sales;
```

Một hình dạng kế hoạch minh họa:

```text
Append
  -> Seq Scan on sales_2026_01
  -> Seq Scan on sales_2026_02
  -> Seq Scan on sales_2026_03
  -> Seq Scan on sales_2026_04
  -> Seq Scan on sales_default
```

Đây là **cấu trúc minh họa**, không phải đầu ra bắt buộc. PostgreSQL có thể chọn `Parallel Append`, thứ tự nodes khác, hoặc cấu trúc kế hoạch khác tùy query/stats/version.

### 6.1. `Append` nghĩa là gì?

`Append` kết hợp kết quả từ nhiều child plans. Mỗi child plan có thể là:

- `Seq Scan`.
- `Index Scan`.
- `Bitmap Heap Scan`.
- Một subplan/join phức tạp hơn.

Nó không có nghĩa “toàn bộ partition data đã được hợp nhất thành một heap”.

### 6.2. `Append` không đảm bảo thứ tự

Nếu query không có `ORDER BY`, PostgreSQL không hứa trả kết quả theo tháng, theo thứ tự tạo partition hay theo primary key.

Nếu query cần thứ tự:

```sql
SELECT sale_id, sold_on, amount
FROM part_eval_lab.sales
ORDER BY sold_on, sale_id;
```

planner phải đáp ứng thứ tự đó bằng sort hoặc một path có thứ tự.

### 6.3. `Merge Append`

Khi các child paths đã có thứ tự tương thích, PostgreSQL có thể dùng `Merge Append` để hợp nhất streams theo order:

```text
Merge Append
  Sort Key: sold_on, sale_id
  -> Index Scan on sales_2026_01 ...
  -> Index Scan on sales_2026_02 ...
  -> Index Scan on sales_2026_03 ...
  -> Index Scan on sales_2026_04 ...
```

`Merge Append` có thể tránh một global Sort riêng nhưng vẫn có overhead hợp nhất nhiều streams. Không phải mọi query `ORDER BY` đều chọn nó.

### 6.4. `Parallel Append`

Trong một parallel plan, executor có thể tổ chức workers cùng xử lý các child subplans qua `Parallel Append`.

```text
Gather
  -> Parallel Append
       -> Parallel Seq Scan on sales_2026_01
       -> Parallel Seq Scan on sales_2026_02
       -> ...
```

Lợi ích phụ thuộc partition sizes, number of workers, I/O và overhead. Nhiều partition rất nhỏ có thể làm parallel overhead lớn hơn lợi ích.

### 6.5. Không đánh giá plan chỉ theo số node

Một plan có `Append` với 12 children nhưng tất cả đều nhỏ có thể chạy nhanh. Một query chỉ còn một partition nhưng phải Seq Scan hàng tỷ dòng vẫn có thể rất chậm.

Cần so **actual rows, buffers, execution time, partition count sau pruning và scan path trong từng leaf**.

## 7. Partition pruning: loại phân vùng không cần đọc

**Partition pruning** là việc PostgreSQL xác định các partition **không thể chứa hàng** thỏa predicate dựa trên partition bounds.

### 7.1. Truy vấn chỉ tháng 2

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT sale_id, sold_on, tenant_id, amount
FROM part_eval_lab.sales
WHERE sold_on >= DATE '2026-02-01'
  AND sold_on <  DATE '2026-03-01';
```

Với RANGE partitioning trên `sold_on`, predicate tương ứng chính xác bounds của `sales_2026_02`.

Planner có thể loại tháng 1, 3, 4 và default ngay lúc lập kế hoạch. Một plan minh họa chỉ còn:

```text
Seq Scan on sales_2026_02
  Filter: (
      sold_on >= '2026-02-01'::date
      AND sold_on < '2026-03-01'::date
  )
```

Tùy tối ưu hóa, plan có thể còn lớp `Append` hoặc được rút gọn thành scan trực tiếp trên child. **Cả hai đều có thể là đã pruning thành công**.

### 7.2. Predicate hai tháng

```sql
EXPLAIN
SELECT sale_id, sold_on
FROM part_eval_lab.sales
WHERE sold_on >= DATE '2026-02-01'
  AND sold_on <  DATE '2026-04-01';
```

Có thể chỉ cần February và March partitions.

### 7.3. Query không có partition key

```sql
EXPLAIN
SELECT sale_id, sold_on, tenant_id
FROM part_eval_lab.sales
WHERE tenant_id = 1;
```

Dù `tenant_id = 1` rất phổ biến, nó **không tự đủ để pruning partition theo ngày**. PostgreSQL có thể phải xem mọi partition, rồi chọn scan/index riêng cho từng child.

**Partition pruning dựa trên partition key/bounds, không chỉ dựa trên việc có WHERE.**

### 7.4. Pruning không tương đương dùng index

Nếu predicate tháng 2 đã loại ba partition, PostgreSQL vẫn cần truy vấn trong `sales_2026_02`.

Nó có thể dùng:

- Seq Scan trong một partition.
- Index Scan trên local index.
- Bitmap Heap Scan nếu cần.

Ngay cả khi partition không có index trên `sold_on`, pruning **vẫn có thể xảy ra** vì nó dùng metadata của partition bounds.

### 7.5. Không có ngưỡng “một partition luôn nhanh”

Nếu tháng 2 chứa 500 triệu dòng, chỉ đọc một partition vẫn có thể đắt. Nếu dữ liệu cần là một tenant nhỏ trong tháng 2, local index `(tenant_id, sold_on)` có thể quan trọng hơn việc giảm 12 partition xuống một.

## 8. Cách viết predicate giúp pruning

Để PostgreSQL dễ suy luận ranges, nên viết predicate trực tiếp trên partition key khi có thể.

### 8.1. Nên dùng nửa khoảng `[start, end)`

```sql
WHERE sold_on >= DATE '2026-02-01'
  AND sold_on <  DATE '2026-03-01'
```

Ưu điểm:

- Khớp đúng RANGE partition bounds.
- Không phải suy nghĩ ngày cuối tháng có bao nhiêu ngày.
- Dễ mở rộng sang timestamp với độ chính xác khác nhau.
- Có thể truyền start/end bằng bind parameters.

### 8.2. Predicate bằng hàm trên cột có thể cản pruning

Ví dụ:

```sql
WHERE date_trunc(
    'month',
    sold_on::timestamp
) = timestamp '2026-02-01 00:00:00'
```

Về logic, với ngày bình thường nó tương ứng tháng 2. Nhưng planner có thể không biến đổi được biểu thức trên cột thành ràng buộc `sold_on` phù hợp partition bounds.

Một cách thường rõ hơn:

```sql
WHERE sold_on >= DATE '2026-02-01'
  AND sold_on <  DATE '2026-03-01'
```

### 8.3. Bọc cột trong cast/expression cần thận trọng

```sql
WHERE sold_on::text LIKE '2026-02%'
```

không tương đương về khả năng tối ưu với range predicate trực tiếp. Nó còn làm type/operator semantics phức tạp và có thể cản index use.

### 8.4. Với TIMESTAMP/TIMESTAMPTZ

Nếu partition key là `timestamptz`, hãy xác định timezone nghiệp vụ và biên tháng chuẩn.

Ví dụ một cửa sổ UTC:

```sql
WHERE created_at >= timestamptz '2026-02-01 00:00:00+00'
  AND created_at <  timestamptz '2026-03-01 00:00:00+00'
```

Không dùng `BETWEEN` với `23:59:59` để biểu diễn “đến cuối ngày” trên timestamp vì có thể bỏ sót các giá trị fractional seconds.

### 8.5. `OR` phức tạp và optional filters

Predicate:

```sql
WHERE (
    $1 IS NULL
    OR sold_on >= $1
)
```

có thể khiến generic plan khó pruning theo các bounds cụ thể, vì câu SQL phải đúng cả khi tham số NULL.

Nếu nghiệp vụ có hai dạng rõ ràng “không lọc ngày” và “lọc theo khoảng”, cân nhắc hai query shapes với bind parameters phù hợp.

## 9. Plan-time pruning: biết giá trị ngay khi lập kế hoạch

Khi query có hằng số:

```sql
SELECT *
FROM part_eval_lab.sales
WHERE sold_on >= DATE '2026-03-01'
  AND sold_on <  DATE '2026-04-01';
```

planner có đủ thông tin để loại những partitions ngoài March trong quá trình lập kế hoạch.

### 9.1. Trong EXPLAIN có thể không thấy partition bị loại

Vì nodes bị loại trước khi plan hình thành, EXPLAIN thường **không hiển thị tên các partition đã prune**.

Để xác nhận, so:

- Số partitions thật từ `pg_partition_tree`.
- Tên partition xuất hiện trong EXPLAIN.
- Actual buffers/read của query.

### 9.2. Việc pruning sớm giảm chi phí gì?

Có thể giảm:

- Số relations có trong access paths.
- Số child plans phải chạy.
- Số heap/index pages có thể được truy cập.
- Trong một số trường hợp, lượng công việc liên quan locks và executor initialization.

Không phải mọi catalog/planning overhead đều biến mất, đặc biệt với rất nhiều partitions và query phức tạp.

### 9.3. Pruning không đảm bảo loại được default trong mọi predicate

Nếu query không giới hạn rõ partition key, DEFAULT partition có thể là một candidate hợp lệ.

Khi có DEFAULT, cần kiểm tra nó có chứa dữ liệu ngoài các khoảng mong đợi không; một query quên date predicate có thể đọc default cùng tất cả các tháng.

## 10. Execution-time pruning với prepared statements

Trong ứng dụng, ngày tháng thường được bind:

```sql
SELECT sale_id, sold_on, tenant_id
FROM part_eval_lab.sales
WHERE sold_on >= $1
  AND sold_on < $2;
```

Generic prepared plan có thể không biết giá trị `$1` và `$2` khi lập kế hoạch. PostgreSQL hỗ trợ **partition pruning trong quá trình thực thi** trong những trường hợp phù hợp.

### 10.1. Tạo prepared statement trong lab

```sql
PREPARE sales_in_range(date, date) AS
SELECT sale_id, sold_on, tenant_id, amount
FROM part_eval_lab.sales
WHERE sold_on >= $1
  AND sold_on < $2;
```

### 10.2. Ép generic plan để quan sát

```sql
BEGIN;

SET LOCAL plan_cache_mode = force_generic_plan;

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
EXECUTE sales_in_range(
    DATE '2026-02-01',
    DATE '2026-03-01'
);

ROLLBACK;
```

Generic plan có thể chứa `Append` với các child candidates, nhưng executor dùng giá trị tham số để bỏ qua những child không cần thiết.

Dấu hiệu trong EXPLAIN có thể là:

```text
Append
  Subplans Removed: 4
  -> Seq Scan on sales_2026_02 ...
```

Số `4` ở đây chỉ minh họa nếu đúng bốn partitions bị loại ở initialization. Plan thực tế tùy phiên bản và cấu trúc cây.

### 10.3. `Subplans Removed` nghĩa là gì?

Khi pruning xảy ra **ở thời điểm khởi tạo executor**, EXPLAIN có thể ghi `Subplans Removed`. Những subplans bị loại sẽ không chạy.

Không xem sự tồn tại của `Append` là bằng chứng pruning thất bại nếu các subplans không cần thiết đã bị loại.

### 10.4. Pruning lặp trong lúc thực thi

Trong một Nested Loop hoặc truy vấn tham số hóa mà giá trị partition key thay đổi theo từng vòng, PostgreSQL có thể pruning lại trong quá trình execution.

EXPLAIN ANALYZE có thể cho thấy các partitions:

- Có `loops` khác nhau.
- Có node `(never executed)`.
- Có một số partitions được dùng ở vòng này nhưng không dùng ở vòng khác.

Đừng chỉ dựa vào `Subplans Removed` để kết luận toàn bộ pruning. Các cơ chế pruning khác thời điểm có cách quan sát khác.

### 10.5. Thử custom plan

```sql
BEGIN;

SET LOCAL plan_cache_mode = force_custom_plan;

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
EXECUTE sales_in_range(
    DATE '2026-02-01',
    DATE '2026-03-01'
);

ROLLBACK;
```

Custom plan có thể xét giá trị tham số cụ thể ngay ở planning time và loại nhiều partition sớm hơn.

### 10.6. Dọn prepared statement

```sql
DEALLOCATE sales_in_range;
```

### 10.7. Không kết luận generic luôn quét mọi partition

Đây là một nhầm lẫn quan trọng:

> “Prepared SQL dùng $1 nên chắc chắn đọc hết mọi partition”.

Không đúng trong các phiên bản PostgreSQL có execution-time partition pruning và với predicate phù hợp. Generic plan vẫn có thể tránh thực thi những subplans không liên quan.

Nhưng execution-time pruning có giới hạn và overhead của plan/locks vẫn có thể khác plan-time pruning. **Phải đo theo phiên bản và query thật**.

## 11. `enable_partition_pruning` và constraint exclusion

PostgreSQL có cấu hình:

```sql
SHOW enable_partition_pruning;
SHOW constraint_exclusion;
```

### 11.1. Partition pruning là cơ chế riêng

`enable_partition_pruning` kiểm soát việc planner/executor sử dụng partition pruning theo khả năng được hỗ trợ.

Để thử sự khác biệt trong lab:

```sql
BEGIN;

SET LOCAL enable_partition_pruning = off;

EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*)
FROM part_eval_lab.sales
WHERE sold_on >= DATE '2026-02-01'
  AND sold_on <  DATE '2026-03-01';

ROLLBACK;
```

So với cấu hình bình thường:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*)
FROM part_eval_lab.sales
WHERE sold_on >= DATE '2026-02-01'
  AND sold_on <  DATE '2026-03-01';
```

Khi pruning bị hạn chế, các child plans có thể xuất hiện nhiều hơn. Tuy nhiên, các tối ưu khác, chẳng hạn index constraints, vẫn có thể ảnh hưởng cách đọc.

### 11.2. Constraint exclusion khác partition pruning

Constraint exclusion dùng các CHECK constraints để loại những quan hệ không thể chứa hàng phù hợp trong những tình huống nhất định. Nó là cơ chế liên quan nhưng **không đồng nghĩa** với declarative partition pruning.

Với declarative partitioning hiện đại, partition pruning dựa trên partition bounds là trọng tâm. Đừng tăng `constraint_exclusion` bừa bãi và xem đó là cách chữa mọi truy vấn partitioned chậm.

### 11.3. Tắt planner method chỉ dùng trong lab

`SET LOCAL enable_partition_pruning = off` giúp quan sát hiệu ứng khác biệt, không phải cấu hình nên để trong production.

Nếu một query đã prune tốt nhưng vẫn chậm, phải điều tra scan/index trong partition còn lại, join/aggregation và data skew.

## 12. Index trên bảng cha và index vật lý trên phân vùng

Một partitioned table có thể có **partitioned index definition** trên parent. Các child indexes thực tế phục vụ dữ liệu ở mỗi partition.

### 12.1. Tạo index trên parent

```sql
CREATE INDEX sales_tenant_date_idx
ON part_eval_lab.sales (tenant_id, sold_on);
```

PostgreSQL quản lý cấu trúc index theo hierarchy và tạo/ghép các indexes phù hợp trên các partitions hiện có theo thao tác được hỗ trợ.

Về khái niệm:

```text
sales_tenant_date_idx (partitioned parent index)
            |
     +------+------+------+
     |      |      |      |
    Jan    Feb    Mar    Apr  (local B-tree indexes)
```

Không có một heap index duy nhất chứa tuples của mọi tháng.

### 12.2. Index dùng sau pruning

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT sale_id, sold_on, amount
FROM part_eval_lab.sales
WHERE sold_on >= DATE '2026-02-01'
  AND sold_on <  DATE '2026-03-01'
  AND tenant_id = 321;
```

Query có hai cơ hội tối ưu:

1. Pruning để chỉ giữ partition February.
2. Trong February, dùng local B-tree trên `(tenant_id, sold_on)` nếu cost hợp lý.

Một plan minh họa:

```text
Index Scan using sales_2026_02_tenant_id_sold_on_idx
  on sales_2026_02
  Index Cond: (
      tenant_id = 321
      AND sold_on >= '2026-02-01'::date
      AND sold_on < '2026-03-01'::date
  )
```

Tên local index trong output thực tế có thể khác. Quan trọng là **đường truy cập của partition còn lại**.

### 12.3. Có thể Seq Scan trong một partition dù có index

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT sale_id, sold_on, tenant_id, amount, note
FROM part_eval_lab.sales
WHERE sold_on >= DATE '2026-02-01'
  AND sold_on <  DATE '2026-03-01'
  AND tenant_id = 1;
```

Tenant 1 chiếm khoảng 80% dữ liệu. Seq Scan trên February có thể hợp lý hơn đi index và đọc nhiều heap tuples. Đây **không phải pruning thất bại**.

### 12.4. Index-only scan và visibility map

Nếu local index chứa đủ columns cho query, PostgreSQL có thể cân nhắc `Index Only Scan`. Nhưng việc tránh heap fetch còn phụ thuộc MVCC visibility map của **từng partition**.

Partition lịch sử ít ghi có thể thuận lợi hơn partition hiện tại nhiều INSERT/UPDATE.

### 12.5. Không nên tạo index cho mọi cột trên mọi partition

Index làm tăng:

- Storage của mỗi child.
- Chi phí ghi và WAL.
- Thời gian tạo/duy trì index khi thêm partitions.
- Công việc REINDEX/VACUUM liên quan.
- Số đối tượng catalog và planning overhead.

Chọn index dựa trên query patterns thực tế.

## 13. Tạo chỉ mục trên hệ thống phân vùng đang chạy

Dùng:

```sql
CREATE INDEX index_name
ON part_eval_lab.sales (tenant_id, status);
```

có thể phải tạo index cho nhiều partitions, chiếm tài nguyên và lấy khóa theo hành vi của phiên bản/operation. Đây không phải thao tác không gây chặn.

### 13.1. Giới hạn `CREATE INDEX CONCURRENTLY` trên parent

Trên các phiên bản PostgreSQL phổ biến hỗ trợ declarative partitioning, không thể chỉ chạy trực tiếp:

```sql
-- Không dùng như một lệnh được bảo đảm hỗ trợ:
CREATE INDEX CONCURRENTLY ix
ON part_eval_lab.sales (tenant_id);
```

với kỳ vọng xây dựng đồng thời hoàn chỉnh tất cả child indexes trên partitioned parent. **`CREATE INDEX CONCURRENTLY` trực tiếp trên partitioned parent không được hỗ trợ** trong những phiên bản tương ứng.

Cần kiểm tra tài liệu đúng phiên bản khi xây runbook.

### 13.2. Chiến lược xây trên các partition riêng lẻ

Một chiến lược được PostgreSQL hỗ trợ trong những phiên bản phù hợp:

1. Tạo **partitioned index metadata** trên parent với `ON ONLY`; index cha chưa hợp lệ đầy đủ cho đến khi các partition indexes tương ứng được attach.
2. Tạo child indexes bằng `CREATE INDEX CONCURRENTLY` từng partition, ngoài transaction block tường minh.
3. Gắn child indexes bằng `ALTER INDEX ... ATTACH PARTITION` theo đúng parent index definition.
4. Xác nhận mọi child index đã attach và parent index trở thành valid khi cấu trúc đầy đủ.

Ví dụ minh họa cho **một index mới**, không phải lệnh nên chạy khi đã tồn tại index trùng định nghĩa:

```sql
-- 1. Metadata index trên parent:
CREATE INDEX sales_tenant_status_parent_idx
ON ONLY part_eval_lab.sales (tenant_id, status);

-- 2. Xây riêng một child index:
-- CREATE INDEX CONCURRENTLY phải chạy ngoài BEGIN/COMMIT.
CREATE INDEX CONCURRENTLY sales_2026_01_tenant_status_idx
ON part_eval_lab.sales_2026_01 (tenant_id, status);

-- 3. Gắn index con vào index cha:
ALTER INDEX part_eval_lab.sales_tenant_status_parent_idx
ATTACH PARTITION
part_eval_lab.sales_2026_01_tenant_status_idx;

-- 4. Lặp với những partition còn lại, kể cả DEFAULT.
```

**Chú ý:** ví dụ trên chỉ gắn **một partition**; parent index có thể vẫn ở trạng thái chưa valid cho đến khi toàn bộ child indexes cần thiết được attach. Với index con đã tồn tại/định nghĩa khác, cần xem khả năng reuse và compatibility.

### 13.3. Không chạy cả quy trình trong một transaction

`CREATE INDEX CONCURRENTLY` có yêu cầu thực thi ngoài transaction block tường minh. Một công cụ migration luôn bọc mọi step bằng BEGIN/COMMIT có thể gặp lỗi.

Thiết kế migration cần phân loại bước transactional và nontransactional, checkpoint, retry, cleanup index invalid và giám sát tiến độ.

### 13.4. Cần kế hoạch cho partition tương lai

Khi parent index đã hợp lệ và partition mới được thêm, hệ thống có thể tạo hoặc attach index child phù hợp theo cơ chế DDL. Kiểm tra runbook đảm bảo partition tương lai có **đúng indexes cần thiết** thay vì chỉ tối ưu partition cũ.

## 14. Khóa trên parent và child: điều gì thực sự bị khóa?

PostgreSQL quản lý khóa ở cấp relation/transaction/tuple và các đối tượng khác. Với phân vùng, thao tác có thể liên quan cả **parent** và **những child relations**.

### 14.1. Đọc một partition

```sql
SELECT COUNT(*)
FROM part_eval_lab.sales
WHERE sold_on >= DATE '2026-02-01'
  AND sold_on <  DATE '2026-03-01';
```

Một SELECT thông thường có thể lấy `ACCESS SHARE` relation locks trên các quan hệ thực sự cần truy cập. Tập relation locks phụ thuộc kế hoạch và thời điểm pruning.

**Không được mặc định SELECT qua parent luôn lấy khóa trên mọi partition hoặc luôn chỉ lấy khóa trên đúng một partition.** Điều này còn phụ thuộc loại pruning (plan-time/init-time/per-loop), kế hoạch và phiên bản.

### 14.2. Ghi một partition

```sql
INSERT INTO part_eval_lab.sales (
    sold_on, tenant_id, status, amount, note
) VALUES (
    DATE '2026-02-15', 50, 'PAID', 100.00, 'lab'
);
```

Bộ máy định tuyến row tới partition February. Câu INSERT cần các locks phù hợp với thao tác ghi trên quan hệ liên quan (parent và destination leaf theo cơ chế PostgreSQL).

Không suy rằng vì chỉ một child nhận row nên DDL thay đổi parent hoàn toàn không bị ảnh hưởng.

### 14.3. UPDATE partition key có thể di chuyển row

```sql
BEGIN;

UPDATE part_eval_lab.sales
SET sold_on = DATE '2026-03-01'
WHERE sold_on = DATE '2026-02-15'
  AND tenant_id = 50;

ROLLBACK;
```

Khi một UPDATE đổi partition key và destination partition khác, PostgreSQL có thể thực hiện **row movement** giữa partitions theo ngữ nghĩa tương ứng, về bản chất tác động cả source/destination.

Hệ quả:

- Có thể cần khóa ở nhiều partitions.
- Foreign keys/triggers/constraints cần được xét.
- Có thể xuất hiện các xung đột đồng thời và lỗi serialization trong tình huống phù hợp.
- Không nên dùng việc đổi partition key hàng loạt như một cách bảo trì thời gian mà chưa đo.

Ví dụ dùng transaction/rollback để tránh thay đổi dữ liệu lab; WHERE có thể match nhiều hàng, nên không chạy trên production.

### 14.4. Partition-level lock không xóa mọi xung đột

Dù January và February là hai heap khác nhau, thao tác DDL trên parent có thể cần lock cấp parent. Một thao tác maintenance chỉ trên February cũng có thể xung đột với truy vấn đang sử dụng February.

Phân vùng giúp cô lập một số thao tác, **không bảo đảm mọi workload hoàn toàn độc lập**.

## 15. Thí nghiệm hai phiên: khóa một partition

Mục tiêu là quan sát lock wait **chỉ trong lab**. Mở hai/ba kết nối độc lập, xác minh PID:

```sql
SELECT pg_backend_pid();
```

### 15.1. Session A khóa February

```sql
BEGIN;

LOCK TABLE part_eval_lab.sales_2026_02
IN ACCESS EXCLUSIVE MODE;

-- Giữ transaction chưa kết thúc để quan sát.
```

`ACCESS EXCLUSIVE` là mode rất mạnh, xung đột cả với `ACCESS SHARE` của SELECT thông thường trên cùng relation.

### 15.2. Session B thử đọc February

```sql
BEGIN;

SET LOCAL lock_timeout = '3s';

SELECT COUNT(*)
FROM part_eval_lab.sales
WHERE sold_on >= DATE '2026-02-01'
  AND sold_on <  DATE '2026-03-01';
```

Nếu B phải lấy lock không tương thích trên `sales_2026_02`, nó sẽ chờ rồi có thể nhận `lock_timeout`.

### 15.3. Session C quan sát waiters

```sql
SELECT
    a.pid,
    a.application_name,
    a.state,
    a.wait_event_type,
    a.wait_event,
    a.xact_start,
    pg_blocking_pids(a.pid) AS blocking_pids
FROM pg_stat_activity AS a
WHERE a.datname = current_database()
ORDER BY a.xact_start NULLS LAST, a.pid;
```

Nếu cần xác nhận relation lock:

```sql
SELECT
    l.pid,
    l.relation::regclass AS relation_name,
    l.mode,
    l.granted,
    l.waitstart
FROM pg_locks AS l
WHERE l.locktype = 'relation'
  AND l.relation IN (
      SELECT relid
      FROM pg_partition_tree(
          'part_eval_lab.sales'::regclass
      )
  )
ORDER BY l.pid NULLS LAST, l.granted, relation_name;
```

### 15.4. Session A giải phóng khóa

```sql
ROLLBACK;
```

Session B nếu đã timeout hoặc transaction aborted cần:

```sql
ROLLBACK;
```

### 15.5. Thử January riêng

Trong khi A giữ lock trên February, có thể thử một query January ở session khác với predicate literal đủ rõ để **plan-time prune February**:

```sql
SELECT COUNT(*)
FROM part_eval_lab.sales
WHERE sold_on >= DATE '2026-01-01'
  AND sold_on <  DATE '2026-02-01';
```

Nó **có thể không cần khóa leaf February** và do đó không bị chặn bởi lock chỉ trên February, tùy plan/phiên bản. Nhưng một lock cấp parent hay một query với pruning muộn có thể thay đổi kết quả.

**Không dựa vào giả định tuyệt đối “partition khác thì mọi câu lệnh chắc chắn không chặn nhau”. Hãy quan sát `pg_locks` thực tế.**

## 16. `ATTACH PARTITION`: thêm phân vùng vào cây có thể quét và khóa

Ngoài `CREATE TABLE ... PARTITION OF`, PostgreSQL có:

```sql
ALTER TABLE part_eval_lab.sales
ATTACH PARTITION part_eval_lab.sales_2026_05
FOR VALUES FROM ('2026-05-01') TO ('2026-06-01');
```

Nhưng bảng được attach phải **đã tồn tại**, có schema/constraints tương thích và đáp ứng bounds. Dòng trên chỉ minh họa cú pháp, chưa tạo bảng `sales_2026_05` trong lab.

### 16.1. Vì sao ATTACH không chỉ sửa metadata?

Khi attach một bảng có sẵn, PostgreSQL phải bảo đảm các hàng hiện có thuộc partition bounds mới. Nếu không có bằng chứng hợp lệ, nó có thể **quét bảng được attach** để kiểm tra.

Nếu có DEFAULT partition, PostgreSQL còn có thể cần xác minh rằng DEFAULT **không chứa hàng** thuộc khoảng mới; việc này có thể yêu cầu scan và lock trên DEFAULT.

### 16.2. Lock modes cần đánh giá

Với các phiên bản PostgreSQL hỗ trợ declarative partitioning:

- `ALTER TABLE ... ATTACH PARTITION` thường chỉ cần **`SHARE UPDATE EXCLUSIVE` trên parent** (ít chặn hơn `ACCESS EXCLUSIVE` của một số thao tác khác).
- Bảng được attach có thể cần **`ACCESS EXCLUSIVE`**.
- DEFAULT partition có thể chịu lock/scan để xác minh các rows không thuộc partition mới.

Lock modes và các điều kiện phụ thuộc phiên bản/loại thao tác; khi lập runbook production, đối chiếu đúng phiên bản PostgreSQL, schema và tình trạng DEFAULT.

### 16.3. CHECK constraint có thể giúp tránh full scan validation

Nếu bảng chuẩn bị attach đã có **CHECK constraint được validate** chứng minh mọi row nằm trong bounds phù hợp, PostgreSQL có thể không cần quét toàn bảng để xác nhận bounds.

Ví dụ ý tưởng cho bảng dữ liệu tháng 5:

```sql
ALTER TABLE part_eval_lab.sales_2026_05
ADD CONSTRAINT sales_2026_05_bounds_check
CHECK (
    sold_on >= DATE '2026-05-01'
    AND sold_on < DATE '2026-06-01'
);
```

Lệnh này chỉ chạy **sau khi** bạn tạo bảng `sales_2026_05` có cấu trúc phù hợp. Nếu bảng đã có nhiều rows, việc thêm/validate CHECK cũng có thể tốn thời gian và khóa; nên hoàn tất chuẩn bị/validation **trước cửa sổ attach**.

### 16.4. DEFAULT partition làm attach phức tạp hơn

Nếu `sales_default` đã nhận dữ liệu tháng 5, attach riêng partition tháng 5 sẽ xung đột: DEFAULT hiện chứa những rows mà partition mới sẽ nhận.

Cần:

1. Kiểm tra dữ liệu trong DEFAULT theo khoảng tháng mới.
2. Di chuyển dữ liệu hợp lệ sang bảng sẽ attach/partition tương ứng theo quy trình nhất quán.
3. Kiểm tra các constraints và giao dịch đang ghi.
4. Thiết kế cách ngăn new rows vào nhầm DEFAULT trong lúc chuyển tiếp.
5. Chỉ attach khi điều kiện bounds/default thỏa và khóa được đánh giá.

Đừng xóa hàng trong DEFAULT chỉ để tránh lỗi attach nếu chưa có kế hoạch lưu giữ dữ liệu.

### 16.5. Thêm partition trước khi dữ liệu tới

Trong hệ thống theo tháng, nên tạo partitions tương lai **trước** ngày chuyển tháng để tránh:

- INSERT không có partition nhận dữ liệu.
- Hàng mới rơi vào DEFAULT rồi phải di chuyển.
- DDL phải chạy giữa thời điểm cao tải.

Nên có lịch tạo partition trước và cảnh báo nếu partition kỳ tiếp theo chưa tồn tại.

## 17. Tạo mới partition và ATTACH: hai workflow khác nhau

### 17.1. Tạo trực tiếp một partition trống

Nếu mục tiêu chỉ là thêm tháng mới và không cần nạp dữ liệu ngoại vi:

```sql
CREATE TABLE part_eval_lab.sales_2026_05
PARTITION OF part_eval_lab.sales
FOR VALUES FROM ('2026-05-01') TO ('2026-06-01');
```

Đây là lệnh **thao tác trên parent partition hierarchy**; nó có thể cần lock mạnh ở cấp parent theo cơ chế `CREATE TABLE ... PARTITION OF`, nên cần thời điểm triển khai phù hợp.

**Lưu ý:** nếu DEFAULT đã chứa rows tháng 5, việc tạo partition mới cũng cần giải quyết sự chồng lấn dữ liệu/constraints trước.

### 17.2. Chuẩn bị standalone table rồi ATTACH

Workflow khác:

```text
Tạo bảng standalone có schema tương thích
    |
Nạp dữ liệu vào bảng đó (nếu cần)
    |
Tạo index/check constraints phù hợp
    |
VALIDATE dữ liệu và bounds
    |
ALTER TABLE parent ATTACH PARTITION standalone
    |
Xác minh cây, dữ liệu và indexes
```

Lợi thế có thể là chuẩn bị bulk-load/index ngoài cây rồi thực hiện bước attach ngắn hơn nếu validation đã được chuẩn bị kỹ.

### 17.3. Không chạy cả hai workflow cùng tên

Nếu đã:

```sql
CREATE TABLE part_eval_lab.sales_2026_05
PARTITION OF part_eval_lab.sales ...;
```

thì bảng đó **đã là partition**, không cần và không thể attach lại như một standalone table mới.

Ngược lại, `ATTACH PARTITION` yêu cầu bảng phù hợp đã tồn tại nhưng chưa được attach vào parent đó.

### 17.4. DDL trên production cần hiểu locks thật

Mục tiêu tối ưu ATTACH không chỉ là “giảm thời gian scan” mà còn:

- Giảm thời gian chờ khóa.
- Giảm thời gian giữ khóa.
- Giảm ảnh hưởng đến các INSERT/SELECT liên quan.
- Xác minh index/constraint/foreign key.
- Tránh mặc định thêm partition thành công trong mọi điều kiện concurrent.

## 18. `DETACH PARTITION` và `DETACH ... CONCURRENTLY`

Detach tách một partition khỏi cây parent, nhưng bảng con **vẫn tồn tại** dưới dạng bảng độc lập nếu detach thành công.

Ví dụ minh họa:

```sql
ALTER TABLE part_eval_lab.sales
DETACH PARTITION part_eval_lab.sales_2026_01;
```

Sau detach:

- Query qua parent không còn thấy dữ liệu của partition đã detach.
- Bảng `sales_2026_01` vẫn có thể được truy vấn trực tiếp.
- Indexes/data của nó không tự bị xóa chỉ vì detach.

### 18.1. DETACH thông thường có thể khóa mạnh

`ALTER TABLE ... DETACH PARTITION` không-CONCURRENTLY có thể cần lock mạnh trên parent và gây blocking. Trên hệ thống bận, phải đo trước khi chạy.

### 18.2. DETACH CONCURRENTLY

Một số phiên bản PostgreSQL hỗ trợ:

```sql
ALTER TABLE part_eval_lab.sales
DETACH PARTITION part_eval_lab.sales_2026_01
CONCURRENTLY;
```

Mục tiêu là giảm mức chặn bằng quy trình detach nhiều giai đoạn, thường dùng lock yếu hơn trên parent so với detach thông thường.

**Hạn chế quan trọng:**

- Không dùng `DETACH ... CONCURRENTLY` bên trong một transaction block tường minh.
- Một số cấu trúc partition hierarchy, đặc biệt tình huống **có DEFAULT partition**, có giới hạn áp dụng.
- Có thể phải chờ các giao dịch cũ kết thúc.
- Nếu bị gián đoạn, có thể cần xử lý **pending detach** bằng thủ tục phù hợp với phiên bản, như `FINALIZE` trong những trường hợp hỗ trợ.

Không cho rằng chỉ thêm từ khóa `CONCURRENTLY` thì thao tác luôn tức thì hoặc không cần lock.

### 18.3. Bảng lab hiện có DEFAULT

Lab đã tạo `sales_default`, vì vậy **đừng mặc định chạy ngay ví dụ DETACH CONCURRENTLY ở trên**. Hãy kiểm tra giới hạn của đúng phiên bản và cân nhắc một hierarchy lab riêng không có DEFAULT khi muốn thực hành phương thức concurrent.

### 18.4. DETACH không phải DROP

- **DETACH**: bỏ quan hệ partition/parent, giữ bảng và dữ liệu vật lý.
- **DROP TABLE child**: xóa bảng cùng dữ liệu của nó sau khi thao tác hoàn tất.
- **TRUNCATE child**: xóa dữ liệu trong bảng đó nhưng giữ bảng.
- **DROP TABLE parent**: có thể tác động đến toàn bộ cấu trúc phụ thuộc, không phải thao tác dọn một tháng.

Phân biệt này quyết định thiết kế retention/archive.

## 19. Partition retention: xóa tháng cũ mà không DELETE từng hàng

Đối với log theo tháng, thay vì:

```sql
DELETE FROM part_eval_lab.sales
WHERE sold_on < DATE '2026-02-01';
```

trên lượng dữ liệu cực lớn, có thể cân nhắc **detach/drop phân vùng cũ** theo chính sách lưu giữ.

### 19.1. Vì sao DELETE có thể đắt?

Một `DELETE` hàng triệu rows có thể:

- Tạo nhiều WAL.
- Tạo dead tuples.
- Tăng công việc VACUUM.
- Làm index cần bảo trì.
- Giữ transaction/locks lâu.
- Gây áp lực replication và I/O.

### 19.2. Partition-level retention

Một workflow có thể là:

```text
Xác định tháng đủ điều kiện xóa
    |
Kiểm tra cutoff, timezone và quy định lưu giữ
    |
Kiểm tra late-arriving writes và external dependencies
    |
Lưu bản sao/backup/archive nếu cần
    |
DETACH PARTITION (nếu cần bước lưu giữ độc lập)
    |
Kiểm tra dữ liệu không còn nằm trong parent query
    |
DROP standalone table khi đã được phê duyệt
    |
Xác minh stats, monitoring, storage, replication
```

### 19.3. DETACH không giải phóng dung lượng ngay

Sau DETACH, bảng và index vẫn tồn tại. Dung lượng chỉ thực sự được thu hồi theo thao tác xóa/lưu trữ thích hợp.

Nếu mục tiêu là giảm storage, cần thêm bước được kiểm soát như `DROP TABLE` **sau** khi đã đáp ứng quy định backup và retention.

### 19.4. DROP một partition là thao tác phá hủy

```sql
-- CHỈ là minh họa, không chạy trên production:
DROP TABLE part_eval_lab.sales_2026_01;
```

Câu này có thể xóa toàn bộ dữ liệu partition, index và phụ thuộc liên quan theo ngữ nghĩa DROP. Đừng dùng trên production nếu chưa có approval/checkpoint/backup và hiểu các dependencies.

### 19.5. Dữ liệu tới muộn

Nếu đã xóa January nhưng sau đó API vẫn INSERT một sale có `sold_on = '2026-01-15'`:

- Nếu còn DEFAULT và không có rule chặn, row có thể rơi vào DEFAULT.
- Nếu không có partition thích hợp và không có DEFAULT, INSERT có thể lỗi.
- Một vài tiến trình ETL có thể tự retry không giới hạn.

Do đó, retention phải đi kèm **chính sách late data**: từ chối, đưa vào quarantine, lưu ở archive, hoặc tái mở partition theo quy trình có kiểm soát.

### 19.6. Replication/backup và retention

DROP/DETACH là DDL có hậu quả đối với downstream/replicas/backup và job analytics. Kiểm tra:

- Streaming/logical replication theo cấu hình.
- Backup/PITR.
- Foreign key và view dependencies.
- Data lake/export pipeline.
- Hệ thống báo cáo lịch sử.
- Audit/compliance và thời gian lưu trữ.

Không xem việc schema có partition theo tháng là đủ để tự động xóa dữ liệu tháng cũ.

## 20. Khóa khi thêm/xóa partition: cần kế hoạch timeout

DDL có thể bị chặn bởi các transaction đang chạy hoặc cũng có thể chặn những câu SELECT/INSERT mới.

### 20.1. Thiết lập timeout trong transaction cho DDL hỗ trợ

```sql
BEGIN;

SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '30s';

-- Ví dụ thao tác DDL transactional trong lab:
-- ALTER TABLE ... ATTACH PARTITION ...;

ROLLBACK;
```

`lock_timeout` hạn chế thời gian chờ lấy khóa; `statement_timeout` giới hạn statement duration.

Nếu DDL không lấy được lock trong ngưỡng, nên **bỏ lượt và retry có kiểm soát**, không mặc định treo request vô hạn.

### 20.2. Với CONCURRENTLY chạy ngoài transaction

Một số lệnh như `CREATE INDEX CONCURRENTLY` hoặc `DETACH PARTITION CONCURRENTLY` không được chạy trong explicit transaction block.

Nếu cần giới hạn chờ, phải dùng cách đặt timeout phù hợp phạm vi **session/driver/role** và cleanup cài đặt sau khi chạy.

Đừng sao chép `SET LOCAL` ngoài transaction rồi kỳ vọng nó tự ảnh hưởng đến câu lệnh CONCURRENTLY kế tiếp trong autocommit.

### 20.3. Tình huống `idle in transaction`

Một client đọc hoặc ghi rồi quên commit/rollback có thể giữ relation locks và snapshot trong thời gian dài. DDL thay đổi partition hierarchy có thể phải chờ.

Dùng:

```sql
SELECT
    pid,
    state,
    xact_start,
    clock_timestamp() - xact_start AS xact_age,
    wait_event_type,
    wait_event,
    pg_blocking_pids(pid) AS blockers
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY xact_start NULLS LAST;
```

Không terminate một backend chỉ vì xact_age lớn; cần biết user/application/đối tượng khóa và ảnh hưởng nghiệp vụ.

## 21. Tìm ai đang chặn DDL của partition

### 21.1. Query waiters và blockers

```sql
SELECT
    w.pid AS waiting_pid,
    w.application_name AS waiting_app,
    w.state AS waiting_state,
    w.wait_event_type,
    w.wait_event,
    w.query AS waiting_query,
    b.pid AS blocking_pid,
    b.application_name AS blocking_app,
    b.state AS blocking_state,
    b.xact_start AS blocking_xact_start,
    b.query AS blocking_last_query
FROM pg_stat_activity AS w
CROSS JOIN LATERAL
    unnest(pg_blocking_pids(w.pid)) AS p(blocking_pid)
LEFT JOIN pg_stat_activity AS b
  ON b.pid = p.blocking_pid
WHERE w.datname = current_database()
ORDER BY w.pid, b.pid;
```

`pg_blocking_pids` lấy những backend cản một request theo lock manager, kể cả các quan hệ chờ trong lock queue. Không nên tự xác định root blocker chỉ từ một cặp row `pg_locks`.

### 21.2. Query relation locks của parent và leaves

```sql
SELECT
    l.pid,
    l.relation::regclass AS relation_name,
    l.mode,
    l.granted,
    l.waitstart,
    a.application_name,
    a.state,
    a.query
FROM pg_locks AS l
LEFT JOIN pg_stat_activity AS a
  ON a.pid = l.pid
WHERE l.locktype = 'relation'
  AND l.database = (
      SELECT oid
      FROM pg_database
      WHERE datname = current_database()
  )
  AND l.relation IN (
      SELECT relid
      FROM pg_partition_tree(
          'part_eval_lab.sales'::regclass
      )
  )
ORDER BY l.granted, l.waitstart NULLS LAST, relation_name;
```

Quan sát:

- `relation_name`: parent hay child nào.
- `mode`: khóa yêu cầu/đang giữ.
- `granted`: true đã cấp, false đang chờ.
- `waitstart`: thời điểm bắt đầu chờ khi có.
- `application_name`, `state`: owner ứng dụng.

### 21.3. Không chỉ xem relation locks

Một query UPDATE có thể chờ `transactionid` lock do giao dịch khác giữ row. `pg_locks` không liệt kê mọi row-level lock như những row `tuple` rõ ràng.

Vì vậy, khi một ứng dụng ghi chậm, cần cả:

- `pg_blocking_pids`.
- `pg_stat_activity`.
- Relation/transactionid lock views.
- DDL lịch sử và transaction age.

### 21.4. Không cancel/terminate hàng loạt

Nếu DDL đang chờ, hành động đúng không mặc định là:

```sql
-- KHÔNG chạy trên production:
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE state = 'active';
```

Câu này có thể ngắt nhiều transaction hợp lệ và gây retry storm. Hãy ưu tiên giảm impact, đợi lock, nhờ owner kết thúc transaction hoặc chỉ can thiệp backend đã xác minh với quyền phù hợp.

## 22. Index build và VACUUM có thể xung đột với DDL như thế nào?

Các thao tác bảo trì thường có lock requirements khác nhau.

| Hoạt động | Ý nghĩa vận hành |
| --- | --- |
| SELECT thường | Cần relation lock đọc, có thể xung đột DDL khóa mạnh |
| INSERT/UPDATE/DELETE | Cần locks để ghi trên parent/leaves, có thể cạnh tranh |
| `CREATE INDEX` thường | Có thể ảnh hưởng ghi và giữ locks trong thời gian build |
| `CREATE INDEX CONCURRENTLY` trên leaf | Giảm một số blocking nhưng có chi phí/pha chờ và giới hạn |
| `VACUUM` thông thường | Dọn dead tuples, có lock mode phù hợp cho hoạt động thường |
| `VACUUM FULL` | Rewrite relation và cần khóa mạnh, có thể ảnh hưởng đáng kể |
| `ATTACH PARTITION` | Có thể scan/validate và khóa parent/new/default |
| `DETACH PARTITION` | Có thể cần khóa mạnh; CONCURRENTLY có giới hạn |
| `DROP TABLE` partition | Xóa relation và dữ liệu, thao tác phá hủy |

Một plan bảo trì tốt không chỉ tối ưu thời gian chạy mà còn phải kiểm soát **thời gian đợi khóa và tác động đến workload đồng thời**.

### 22.1. Vì sao CREATE INDEX CONCURRENTLY vẫn có thể chờ?

`CONCURRENTLY` không có nghĩa “không lock”, “không tốn I/O” hoặc “không cần chờ”. Nó có nhiều pha, phải đồng bộ với transaction/snapshot liên quan và có thể kéo dài.

### 22.2. Vì sao VACUUM FULL nguy hiểm hơn VACUUM thường?

`VACUUM FULL` ghi lại bảng để thu hồi dung lượng chặt hơn và có lock mạnh. Không xem nó là lệnh cron mặc định trên mọi partition.

### 22.3. Maintenance window vẫn cần khi có partition

Một leaf rất lớn có thể cần bảo trì kéo dài. Dù phần còn lại vẫn phục vụ được một số queries, DDL cấp parent hay những queries chạm leaf đó vẫn có thể bị ảnh hưởng.

Hãy xác định **partition nóng** và **partition lịch sử ít ghi** để chọn lịch bảo trì khác nhau.

## 23. VACUUM trên từng partition

MVCC tạo các phiên bản tuple. UPDATE/DELETE có thể để lại dead tuples cần dọn bằng VACUUM khi không còn snapshot cần giữ.

### 23.1. Kiểm tra một partition

```sql
SELECT
    relid::regclass AS partition_name,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    vacuum_count,
    autovacuum_count
FROM pg_stat_user_tables
WHERE schemaname = 'part_eval_lab'
  AND relname LIKE 'sales_2026_%'
ORDER BY relname;
```

`n_live_tup`/`n_dead_tup` là estimates/statistical counters, không phải `COUNT(*)` chính xác theo snapshot của query.

### 23.2. Vacuum leaf có nhiều dead tuples

```sql
VACUUM (ANALYZE) part_eval_lab.sales_2026_02;
```

Câu này xử lý leaf February; không giả định nó bảo trì mọi leaf khác.

**Không chạy `VACUUM` thông thường trong explicit transaction block**.

### 23.3. Tác dụng chính

VACUUM thông thường có thể:

- Thu hồi khả năng tái sử dụng không gian của dead tuples theo MVCC.
- Cập nhật visibility map và free space map.
- Giúp Index Only Scan tránh heap fetch khi pages đủ điều kiện.
- Thực hiện công việc chống transaction ID wraparound theo chính sách.
- Tùy cấu hình và tình trạng, hỗ trợ dọn dẹp indexes.

Nó không đảm bảo trả ngay toàn bộ disk space về hệ điều hành. Khi quan sát bloat, phải phân biệt **không gian trống bên trong relation có thể tái sử dụng** và **kích thước file trên đĩa**.

### 23.4. Partition cũ cũng cần chính sách freeze

Một partition lịch sử ít được ghi có thể ít phát sinh dead tuples, nhưng vẫn cần quản lý transaction age/freeze phù hợp để tránh vấn đề wraparound ở database.

Không nên vô hiệu hóa autovacuum trên mọi historical partition chỉ vì “dữ liệu không đổi” mà không có chính sách vacuum/freeze đã được chứng minh.

### 23.5. Long transactions ảnh hưởng VACUUM

Một transaction/snapshot sống lâu có thể khiến VACUUM chưa thể giải phóng những tuple versions còn cần cho MVCC, ngay cả khi chương trình đang định VACUUM một partition khác.

Nếu thấy dead tuples tăng, hãy kiểm tra transaction age/replication slots/snapshots và những blockers phù hợp, không chỉ điều chỉnh autovacuum thresholds.

## 24. ANALYZE: thống kê parent và child đều quan trọng

Một bảng phân vùng có hai lớp ước lượng:

1. **Statistics của từng partition** để chọn scan/join trên data của partition đó.
2. **Statistics/inheritance statistics của partitioned parent** để planner ước lượng query đi qua nhiều partitions.

### 24.1. ANALYZE parent

```sql
ANALYZE part_eval_lab.sales;
```

Lệnh này thu thập thống kê thích hợp cho partition hierarchy trong những phiên bản PostgreSQL hỗ trợ, bao gồm thông tin toàn cây và/hoặc leaf statistics theo cơ chế ANALYZE.

### 24.2. Autovacuum và partitioned parent

Một điểm vận hành quan trọng: partitioned parent thường **không chứa tuples trực tiếp**, nên autovacuum không hoạt động trên parent theo cùng cách với bảng heap. Sự thay đổi dữ liệu chỉ trong children **không nhất thiết khiến parent được auto-ANALYZE** như một bảng lưu heap.

Vì vậy, với dữ liệu thay đổi lớn ở các partition, nên có kế hoạch **ANALYZE parent thủ công/định kỳ** theo workload thay vì mặc định thống kê parent luôn tự mới.

Các child partitions vẫn có autovacuum/autoanalyze policies phù hợp với heap của chúng.

### 24.3. Xem last_analyze và last_autoanalyze

```sql
SELECT
    relid::regclass AS relation_name,
    n_live_tup,
    n_dead_tup,
    last_analyze,
    last_autoanalyze,
    analyze_count,
    autoanalyze_count
FROM pg_stat_user_tables
WHERE schemaname = 'part_eval_lab'
  AND relname LIKE 'sales%'
ORDER BY relname;
```

Chú ý các cột stats là counters/thời điểm thu thập, không chứng minh dữ liệu phân bố đã được mô tả tốt về mọi predicate.

### 24.4. Khi nào cần phân tích lại?

- Bulk load partition mới.
- Di chuyển dữ liệu từ DEFAULT vào partition mới.
- Tenant/status distribution đổi mạnh.
- Thêm/bớt partition trong hierarchy.
- Query có estimated rows lệch actual rows nhiều lần.
- Lượng dữ liệu trong một leaf tăng đột biến.

### 24.5. Không tự tạo một ANALYZE toàn cây sau mọi INSERT

ANALYZE có chi phí sample/catalog/CPU. Hãy tổ chức theo batch ingestion, thời gian tải thấp hoặc ngưỡng dữ liệu, và đo hiệu quả. Mục tiêu là đủ mới để planner chọn đúng đường truy cập.

## 25. Cách đo plan sau khi thêm partition

### 25.1. Lấy plan trước thay đổi

```sql
EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT COUNT(*)
FROM part_eval_lab.sales
WHERE sold_on >= DATE '2026-02-01'
  AND sold_on <  DATE '2026-03-01';
```

Ghi:

- Child nodes và partition names.
- Estimated rows / actual rows.
- Buffers hit/read.
- Planning Time / Execution Time.
- Các query parameters.
- PostgreSQL version và indexes.

### 25.2. Thực hiện thay đổi trong lab

Ví dụ thêm tháng 5 khi DEFAULT không chứa dữ liệu trùng:

```sql
CREATE TABLE part_eval_lab.sales_2026_05
PARTITION OF part_eval_lab.sales
FOR VALUES FROM ('2026-05-01') TO ('2026-06-01');
```

### 25.3. Cập nhật stats khi cần

```sql
ANALYZE part_eval_lab.sales;
```

### 25.4. Chạy lại query February

```sql
EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT COUNT(*)
FROM part_eval_lab.sales
WHERE sold_on >= DATE '2026-02-01'
  AND sold_on <  DATE '2026-03-01';
```

Một hệ thống pruning tốt vẫn không cần đọc May chỉ vì parent vừa được thêm partition.

### 25.5. Nhưng planning overhead có thể tăng

Với hàng nghìn partitions, catalog/planner overhead và số lượng relations/indexes có thể tăng ngay cả khi execution-time pruning loại nhiều children.

Vì vậy, đo **Planning Time riêng** với **Execution Time**. Không chỉ xem tổng query latency sau warm cache.

## 26. Khi nào quá nhiều partition gây phản tác dụng?

Phân vùng theo **ngày** thay vì theo **tháng** có thể tăng số partitions lên khoảng 30 lần cho cùng khoảng thời gian.

Hệ quả có thể gồm:

- Nhiều catalog objects.
- Nhiều local indexes.
- Planning overhead.
- Maintenance scheduling phức tạp.
- Thêm những metadata/locks khi DDL.
- Xử lý partitions quá nhỏ kém hiệu quả.
- Tăng công việc quản lý backup, monitoring, permission.

### 26.1. Không có một ngưỡng tối ưu cố định

Không có quy tắc “đúng 100 partition thì tốt, 101 partition thì xấu”.

Số lượng partition phù hợp phụ thuộc:

- Dữ liệu mỗi partition.
- Tỷ lệ query theo partition key.
- Retention window.
- Index count.
- Khả năng pruning.
- PostgreSQL version.
- Memory và workload concurrent.
- Mức thường xuyên attach/detach/reindex.

### 26.2. Chọn granularity theo query và retention

Nếu đa số query chỉ quét 3 ngày, partition theo tháng có thể vẫn ổn với index ngày phù hợp trong một month partition.

Nếu dữ liệu mỗi ngày cực lớn và retention chạy theo ngày, partition ngày có thể hợp lý.

Nếu dữ liệu thấp, chia theo ngày có thể tạo hàng nghìn bảng nhỏ không cần thiết.

### 26.3. Nhiều partition không thay thế index

Một query lọc tenant trong January vẫn có thể cần local index sau khi pruning xuống January. Độ hạt partition và index design là hai quyết định liên quan nhưng khác nhau.

## 27. `enable_partitionwise_join`: join theo từng cặp partition

Khi hai bảng được partition tương thích và join predicates bao gồm partition keys theo điều kiện được hỗ trợ, PostgreSQL có thể thực hiện **partitionwise join**.

### 27.1. Ý tưởng

```text
sales (Jan, Feb, Mar)       sale_tags (Jan, Feb, Mar)
       |                            |
       +-- Jan sales  JOIN Jan tags-+
       +-- Feb sales  JOIN Feb tags-+
       +-- Mar sales  JOIN Mar tags-+
                 |
               Append
```

Thay vì join hai tập lớn toàn bộ, có thể join từng cặp partitions tương ứng.

### 27.2. Bảng phụ có cùng partition scheme

Trong lab:

```sql
CREATE TABLE part_eval_lab.sale_tags (
    sale_id bigint NOT NULL,
    sold_on date NOT NULL,
    tag text NOT NULL
) PARTITION BY RANGE (sold_on);

CREATE TABLE part_eval_lab.sale_tags_2026_01
PARTITION OF part_eval_lab.sale_tags
FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');

CREATE TABLE part_eval_lab.sale_tags_2026_02
PARTITION OF part_eval_lab.sale_tags
FOR VALUES FROM ('2026-02-01') TO ('2026-03-01');

CREATE TABLE part_eval_lab.sale_tags_2026_03
PARTITION OF part_eval_lab.sale_tags
FOR VALUES FROM ('2026-03-01') TO ('2026-04-01');

CREATE TABLE part_eval_lab.sale_tags_2026_04
PARTITION OF part_eval_lab.sale_tags
FOR VALUES FROM ('2026-04-01') TO ('2026-05-01');
```

Chọn vài sale rows làm tag:

```sql
INSERT INTO part_eval_lab.sale_tags (
    sale_id, sold_on, tag
)
SELECT
    sale_id, sold_on, 'reviewed'
FROM part_eval_lab.sales
WHERE sold_on >= DATE '2026-01-01'
  AND sold_on <  DATE '2026-05-01'
  AND sale_id % 100 = 0;

ANALYZE part_eval_lab.sale_tags;
```

### 27.3. So plan

```sql
BEGIN;

SET LOCAL enable_partitionwise_join = on;

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT
    s.sold_on,
    COUNT(*) AS tagged_sales
FROM part_eval_lab.sales AS s
JOIN part_eval_lab.sale_tags AS t
  ON t.sold_on = s.sold_on
 AND t.sale_id = s.sale_id
WHERE s.sold_on >= DATE '2026-02-01'
  AND s.sold_on <  DATE '2026-04-01'
GROUP BY s.sold_on;

ROLLBACK;
```

Câu query chứa equality trên `sold_on`, partition key của cả hai bảng.

### 27.4. Vì sao chưa chắc xuất hiện partitionwise join?

Planner chọn theo cost và các điều kiện tương thích partitioning. Nếu bảng tags nhỏ, một phương án hash join khác có thể rẻ hơn.

`enable_partitionwise_join = on` **cho phép cân nhắc**, không buộc planner chọn.

### 27.5. Cảnh báo bộ nhớ

Partitionwise join có thể tạo nhiều join nodes, mỗi node có memory requirements tương ứng. Với nhiều partitions và joins/sorts/hashes, tổng memory có thể cao.

Đừng bật tùy chọn chỉ vì cái tên “partitionwise” nghe có vẻ nhanh hơn.

## 28. `enable_partitionwise_aggregate`: tổng hợp từng partition

Một số query có thể aggregate dữ liệu riêng trên từng partition trước khi gộp kết quả.

### 28.1. Query thống kê từng ngày

```sql
BEGIN;

SET LOCAL enable_partitionwise_aggregate = on;

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT
    sold_on,
    COUNT(*) AS sales_count,
    SUM(amount) AS total_amount
FROM part_eval_lab.sales
WHERE sold_on >= DATE '2026-01-01'
  AND sold_on <  DATE '2026-05-01'
GROUP BY sold_on;

ROLLBACK;
```

Vì `sold_on` là partition key và cũng là GROUP BY key, các nhóm không trải qua những RANGE partitions tháng khác nhau trong điều kiện lab.

### 28.2. Partial/final aggregation

Planner có thể chọn:

- Aggregate trên từng child rồi Append.
- Partial aggregate và Finalize aggregate.
- Một aggregate sau Append.
- Một parallel aggregation strategy khác.

Kết quả tùy workload và phiên bản.

### 28.3. Không phải mọi group đều partitionwise hoàn toàn

`GROUP BY tenant_id` có thể có cùng tenant xuất hiện ở nhiều tháng. Nếu aggregate chỉ ở từng partition rồi gộp, cần bước tổng hợp cuối để hợp nhất cùng tenant qua tháng.

Không được suy rằng “GROUP BY trên bảng partitioned thì mọi nhóm luôn nằm trong một partition”.

### 28.4. Tăng số aggregate nodes cũng tăng chi phí

Nhiều partition có thể tạo nhiều hash/sort aggregate nodes, gây memory overhead. Vì vậy tùy chọn này cần benchmark, nhất là ở hệ thống nhiều partitions.

## 29. Kiểm tra dung lượng đúng cách

### 29.1. Sai lầm: chỉ đo parent

```sql
SELECT pg_size_pretty(
    pg_total_relation_size(
        'part_eval_lab.sales'::regclass
    )
);
```

Số này **không phải tổng kích thước mọi child**, vì partitioned parent không lưu tuples của tất cả leaves trong một heap.

### 29.2. Đo từng leaf

```sql
SELECT
    p.relid::regclass AS partition_name,
    pg_size_pretty(
        pg_relation_size(p.relid)
    ) AS heap_size,
    pg_size_pretty(
        pg_indexes_size(p.relid)
    ) AS indexes_size,
    pg_size_pretty(
        pg_total_relation_size(p.relid)
    ) AS total_size
FROM pg_partition_tree(
    'part_eval_lab.sales'::regclass
) AS p
WHERE p.isleaf
ORDER BY p.relid::regclass::text;
```

`pg_total_relation_size` của một leaf tính cả những phần lưu trữ liên quan, bao gồm indexes và TOAST khi có.

### 29.3. Tổng toàn cây

```sql
SELECT
    pg_size_pretty(
        SUM(pg_total_relation_size(p.relid))
    ) AS total_leaf_storage
FROM pg_partition_tree(
    'part_eval_lab.sales'::regclass
) AS p
WHERE p.isleaf;
```

Đây là cách cộng kích thước của **các leaves đang attach** tại thời điểm quan sát.

### 29.4. DETACH làm mất khỏi tổng parent, không nhất thiết giảm disk

Nếu đã detach January, query `pg_partition_tree('...sales')` không còn thấy nó. Tổng leaf storage của cây giảm, nhưng standalone table January vẫn chiếm disk cho đến khi được dọn/di chuyển theo cách phù hợp.

Đừng dùng “tổng cây giảm” làm bằng chứng disk thực tế đã được thu hồi.

### 29.5. Cần đối chiếu tablespaces/replica/storage layers

Kích thước relation trong database không đồng nghĩa tổng dung lượng của mọi backup, WAL, replicas và storage snapshots. Khi đánh giá retention, phải xét từng lớp lưu trữ thực tế.

## 30. Theo dõi scan, index usage và dead tuples từng partition

### 30.1. Seq Scan và Index Scan

```sql
SELECT
    relid::regclass AS relation_name,
    seq_scan,
    seq_tup_read,
    idx_scan,
    idx_tup_fetch,
    n_live_tup,
    n_dead_tup
FROM pg_stat_user_tables
WHERE schemaname = 'part_eval_lab'
  AND relname LIKE 'sales%'
ORDER BY relname;
```

Ý nghĩa:

- `seq_scan`: số lần sequential scans theo thống kê.
- `seq_tup_read`: tuples đã đọc bởi sequential scans theo bộ đếm.
- `idx_scan`: số index scans theo định nghĩa statistics.
- `idx_tup_fetch`: heap tuples fetched qua index scans theo cơ chế thống kê.
- `n_live_tup` / `n_dead_tup`: ước lượng live/dead tuples.

### 30.2. Tỷ lệ index scan không phải KPI duy nhất

Nếu January reports đọc 80% dữ liệu partition, Seq Scan có thể phù hợp. Chỉ số `seq_scan` cao không tự chứng minh thiếu index.

Cần xem queries chậm thực tế và EXPLAIN. Một `Index Scan` được gọi quá nhiều lần trong nested loop cũng có thể làm chậm hệ thống.

### 30.3. Index usage

```sql
SELECT
    relid::regclass AS table_name,
    indexrelid::regclass AS index_name,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes
WHERE schemaname = 'part_eval_lab'
ORDER BY relid::regclass::text, indexrelid::regclass::text;
```

Bộ đếm index scan thấp **không tự là bằng chứng chắc chắn index thừa**. Index có thể dùng cho constraints, workload hiếm nhưng quan trọng hoặc kế hoạch chỉ xảy ra ở thời điểm nhất định.

### 30.4. I/O statistics

```sql
SELECT
    relid::regclass AS relation_name,
    heap_blks_read,
    heap_blks_hit,
    idx_blks_read,
    idx_blks_hit
FROM pg_statio_user_tables
WHERE schemaname = 'part_eval_lab'
  AND relname LIKE 'sales%'
ORDER BY relname;
```

Các counters tích lũy trong khoảng stats tracking; khi so sánh phải ghi lại thời điểm/reset, không coi đây là metrics của một query duy nhất.

### 30.5. Số liệu có độ trễ và quyền truy cập

Statistics views không phải phép đo transactional tức thì cho từng statement. Dữ liệu có thể trễ, bị reset hoặc bị giới hạn theo quyền. Dùng chúng để tìm xu hướng và đối chiếu với EXPLAIN/monitoring.

## 31. Quan sát VACUUM đang chạy

`pg_stat_progress_vacuum` hỗ trợ xem tiến độ VACUUM đang thực thi trong phạm vi tính năng/phiên bản.

```sql
SELECT
    pid,
    relid::regclass AS relation_name,
    phase,
    heap_blks_total,
    heap_blks_scanned,
    heap_blks_vacuumed
FROM pg_stat_progress_vacuum
WHERE datname = current_database()
ORDER BY pid;
```

Một VACUUM chạy trên leaf February thường có `relid` tương ứng với relation của partition đó, không phải một “heap chung” của parent.

### 31.1. Không nhầm tiến độ VACUUM với dung lượng được thu hồi

Progress cho biết công việc đang tiến đến đâu, không trực tiếp chứng minh file size sẽ giảm.

### 31.2. Index maintenance riêng

Khi xây index, có thể quan sát những thông tin tiến độ liên quan trong `pg_stat_progress_create_index` khi phiên bản hỗ trợ. Cần hiểu index build thông thường so với concurrently có nhiều phases và lock/snapshot synchronization.

### 31.3. Autovacuum trên nhiều partitions

Khi một số partition nóng cập nhật liên tục, chúng có thể cần autovacuum/autoanalyze thường xuyên hơn partitions lịch sử. Thiết kế per-table reloptions có thể phù hợp với workload, nhưng cần tránh quá nhiều tham số khác nhau khó vận hành.

## 32. Tùy chỉnh autovacuum cho partition nóng

PostgreSQL cho phép thiết lập một số tham số autovacuum per relation.

Ví dụ minh họa cho February:

```sql
ALTER TABLE part_eval_lab.sales_2026_02
SET (
    autovacuum_vacuum_scale_factor = 0.05,
    autovacuum_analyze_scale_factor = 0.02
);
```

Những ngưỡng này chỉ là **ví dụ**, không phải cài đặt tối ưu phổ quát.

### 32.1. Vì sao cần phân biệt partition nóng/lạnh?

Một partition đang nhận INSERT/UPDATE có thể phát sinh dead tuples nhanh và cần stats cập nhật thường xuyên.

Partition lịch sử đã đóng cho ghi có thể ít thay đổi, nhưng vẫn cần freeze/maintenance theo tuổi transaction và policies.

### 32.2. Kiểm tra settings của từng child

```sql
SELECT
    oid::regclass AS relation_name,
    reloptions
FROM pg_class
WHERE oid IN (
    SELECT relid
    FROM pg_partition_tree(
        'part_eval_lab.sales'::regclass
    )
)
ORDER BY oid::regclass::text;
```

### 32.3. Không tắt autovacuum tùy tiện

Vô hiệu hóa autovacuum trên partitions vì muốn “giảm load” có thể khiến dead tuples tích lũy, statistics cũ và rủi ro wraparound.

Nếu cần giảm áp lực, hãy điều chỉnh schedule/threshold/worker capacity có kiểm soát và giám sát tình trạng từng partition.

### 32.4. ANALYZE parent vẫn cần chú ý riêng

Cài autovacuum cho child không đảm bảo global parent statistics luôn mới. Một kế hoạch ANALYZE parent phù hợp vẫn có thể cần thiết sau thay đổi lớn toàn hierarchy.

## 33. Bloat, REINDEX và việc “phân vùng nhỏ hơn” không tự hết vấn đề

### 33.1. Bloat có thể xảy ra ở từng leaf

Một partition nhận nhiều UPDATE/DELETE có thể phát sinh dead tuples và index bloat. Phân vùng chỉ giới hạn phạm vi của từng quan hệ, không làm MVCC biến mất.

### 33.2. Index maintenance

Khi có bằng chứng index bloat hoặc lỗi/nhu cầu bảo trì, có thể cân nhắc `REINDEX` cho một **child index** với lựa chọn lock/concurrent phù hợp phiên bản.

Ví dụ mô tả:

```sql
-- Chỉ minh họa, kiểm tra đúng index và version:
REINDEX INDEX CONCURRENTLY
part_eval_lab.some_child_index;
```

Không chạy khi index mẫu `some_child_index` chưa tồn tại. `REINDEX ... CONCURRENTLY` có giới hạn và thường không được đặt trong explicit transaction block.

### 33.3. Không reindex tất cả partitions theo định kỳ mù quáng

Nếu index vừa được tạo, ít bloat và hoạt động tốt, reindex có thể chỉ tăng I/O/WAL và gây contention.

Chỉ thực hiện khi có:

- Bằng chứng về vấn đề.
- Đánh giá kích thước/index scan và thời gian.
- Kế hoạch lock/concurrency/rollback.
- Theo dõi replication lag và disk headroom.

### 33.4. VACUUM FULL không phải bước dọn mỗi tháng

`VACUUM FULL` rewrite relation, có thể cần không gian tạm thời và lock mạnh. Nó khác hoàn toàn việc detach/drop một partition lịch sử đủ điều kiện retention.

Đừng dùng VACUUM FULL như giải pháp mặc định cho việc xóa dữ liệu cũ nếu partition-level retention có thể đáp ứng đúng nghiệp vụ.

## 34. Truy vấn trên nhiều partition và lỗi ước lượng số hàng

Partitioning làm planner phải ước lượng:

- Có bao nhiêu partition liên quan.
- Mỗi partition có bao nhiêu hàng.
- Predicate selectivity trên từng child.
- Distribution tổng thể của dữ liệu.
- Chọn join/aggregate/sort ở đâu.

### 34.1. Query tenant nóng nhưng quên ngày

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*)
FROM part_eval_lab.sales
WHERE tenant_id = 1;
```

Vì không có `sold_on` predicate, planner có thể cần mọi partition.

### 34.2. Query tenant nhỏ trong February

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT sale_id, sold_on, tenant_id, amount
FROM part_eval_lab.sales
WHERE sold_on >= DATE '2026-02-01'
  AND sold_on <  DATE '2026-03-01'
  AND tenant_id = 321;
```

Có thể prune chỉ February rồi dùng local index.

### 34.3. Skew giữa các partition

Một tháng có thể chứa tenant 1 chiếm 90%, tháng khác tenant 1 chỉ chiếm 10%. Thống kê chung của parent không đủ mô tả mọi tình huống chi tiết.

Vì vậy, phải quan sát actual rows/estimates ở child nodes thay vì chỉ nhìn `Append` tổng.

### 34.4. Prepared statements và generic plans

Một query:

```sql
WHERE sold_on >= $1
  AND sold_on < $2
  AND tenant_id = $3
```

có thể được execution-time prune theo tháng, nhưng vẫn cần chọn scan trong partition với thông tin tham số và stats phù hợp.

Nếu tenant selectivity lệch rất mạnh, custom/generic plan có thể ảnh hưởng scan path; runtime pruning **không giải quyết hết vấn đề parameter skew**.

### 34.5. Cập nhật stats không đồng nghĩa ép dùng index

`ANALYZE` giúp planner ước lượng tốt hơn; nó không bảo đảm mọi query tháng chọn Index Scan. Seq Scan vẫn có thể rẻ nhất khi đọc phần lớn partition.

## 35. EXPLAIN trên partitioned table: đọc đúng trường nào?

Dùng:

```sql
EXPLAIN (ANALYZE, BUFFERS, SETTINGS, VERBOSE)
SELECT
    sold_on,
    tenant_id,
    COUNT(*) AS sale_count,
    SUM(amount) AS total_amount
FROM part_eval_lab.sales
WHERE sold_on >= DATE '2026-02-01'
  AND sold_on <  DATE '2026-04-01'
GROUP BY sold_on, tenant_id;
```

### 35.1. Các thành phần nên ghi lại

| Thành phần | Ý nghĩa |
| --- | --- |
| `Append` / `Merge Append` | Kết hợp streams của children |
| `Parallel Append` | Phân công child plans trong parallel execution |
| Tên partition | Child nào thực sự xuất hiện trong plan |
| `Subplans Removed` | Initialization-time pruning khi được báo |
| `(never executed)` | Node không thực thi ở lần đo |
| `loops` | Số lượt node chạy; quan trọng với pruning trong joins |
| `Seq Scan` / `Index Scan` / `Bitmap Heap Scan` | Access path bên trong leaf |
| `Index Cond` / `Filter` | Predicate dùng index hay lọc sau |
| `rows` / `actual rows` | Ước lượng so với thực tế |
| `Buffers: shared hit/read` | Lượng blocks truy cập theo instrumentation |
| `Planning Time` | Chi phí lập plan, cần chú ý khi nhiều partitions |
| `Execution Time` | Chi phí thực thi server-side trong EXPLAIN |
| `Settings` | Tham số khác default được hiển thị khi áp dụng |

### 35.2. EXPLAIN ANALYZE thực sự chạy query

Với SELECT, nó đo bằng cách thực thi nhưng thường không gửi từng row ra client như câu SELECT thông thường.

Với `INSERT`/`UPDATE`/`DELETE`, `EXPLAIN ANALYZE` **thực sự thay đổi dữ liệu** theo transaction.

Nếu muốn thử DML trong lab:

```sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS)
UPDATE part_eval_lab.sales
SET status = 'PAID'
WHERE sold_on = DATE '2026-02-01'
  AND tenant_id = 321;

ROLLBACK;
```

Rollback khôi phục dữ liệu transactional, nhưng vẫn có I/O/WAL và có thể có side effects khác. Không xem `BEGIN...ROLLBACK` là giấy phép thử DML nguy hiểm trên production.

### 35.3. Buffers và timing

`shared hit` là buffer hit trong shared buffers. `shared read` là block cần đọc vào shared buffers; nó có thể đến từ OS cache, nên không đồng nhất với physical disk reads.

Lượt đầu và lượt sau có thể khác vì cache nóng lên. Benchmark cần lặp lại và ghi điều kiện chạy.

### 35.4. Planning Time có thể là bottleneck

Khi số partitions tăng lớn, query chạy rất nhanh sau pruning nhưng Planning Time tăng rõ.

Vì vậy, đánh giá partitioning cần cả **planning** lẫn **execution**, nhất là với các query được gọi rất nhiều lần.

## 36. Quy trình vận hành thêm partition tháng mới

Một runbook mẫu, cần điều chỉnh theo phiên bản và hệ thống:

### Trước ngày chuyển tháng

1. **Xác minh ranh giới** ngày/tháng và timezone nghiệp vụ.
2. Kiểm tra cây bằng `pg_partition_tree`.
3. Kiểm tra DEFAULT có dữ liệu thuộc khoảng sắp thêm không.
4. Chuẩn bị child table/indexes/constraints theo workflow chọn.
5. Xác định DDL lock modes thực tế trên phiên bản sử dụng.
6. Chọn cửa sổ tải thấp; đặt lock timeout phù hợp.
7. Có kế hoạch xử lý khi ATTACH/CREATE thất bại.
8. Nếu có migration không transactional, chuẩn bị checkpoint/cleanup.

### Khi thực hiện

```text
Kiểm tra partition chưa tồn tại
      |
      v
Kiểm tra DEFAULT và dữ liệu đến muộn
      |
      v
CREATE PARTITION hoặc ATTACH (chỉ chọn một)
      |
      v
Xác minh bounds/indexes/constraints
      |
      v
ANALYZE khi cần
      |
      v
Thử INSERT/SELECT và EXPLAIN trên khoảng mới
```

### Sau khi thực hiện

- Xác nhận row routing vào đúng child.
- Không có lock wait kéo dài.
- Local indexes đã sẵn sàng.
- Monitoring và backup nhận diện partition mới.
- Job retention không vô tình xóa nhầm partition mới.
- Cảnh báo “thiếu tháng kế tiếp” được cập nhật.

## 37. Quy trình vận hành loại bỏ partition cũ

### Trước khi dọn

1. Xác nhận retention cutoff theo nghiệp vụ/pháp lý.
2. Kiểm tra partition bounds; đừng chỉ dựa vào tên.
3. Xác nhận không còn writer cần ghi dữ liệu quá cũ.
4. Kiểm tra late-arriving data policy.
5. Kiểm tra FK, views, procedures, downstream references.
6. Kiểm tra backup/archive và replication.
7. Xác định nên DETACH, DROP hay giữ partition read-only.
8. Kiểm tra long transactions và nguy cơ DDL wait.
9. Chọn lock timeout và rollback/escalation plan.

### Khi dọn

Nếu cần giữ dữ liệu tạm thời:

```text
DETACH -> xác minh parent không còn thấy rows
       -> xuất/đối soát/archive nếu cần
       -> DROP standalone table khi đã được duyệt
```

Nếu chọn xóa trực tiếp leaf và được phép, hiểu rõ lock và tính phá hủy.

### Sau khi dọn

- Query parent không còn nhìn thấy partition đã bỏ.
- Tổng dung lượng của attached leaves giảm.
- Disk/storage thực tế được đo lại.
- Không còn prepared detach/index invalid bỏ dở.
- Không có INSERT muộn rơi vào DEFAULT ngoài ý muốn.
- Các báo cáo có khoảng lịch sử lớn vẫn chạy đúng theo chính sách.

## 38. Mẫu bảng quyết định: chọn giải pháp phù hợp

| Vấn đề | Không nên vội | Hướng điều tra |
| --- | --- | --- |
| Query tháng 2 vẫn đọc 12 partitions | Tạo index ngẫu nhiên | Kiểm tra partition key predicate và pruning time |
| Query chỉ đọc Feb nhưng chậm | Tăng số partitions | Kiểm tra scan/index/join trong Feb |
| Generic prepared plan có nhiều child nodes | Kết luận chắc quét hết | Xem Subplans Removed, loops và actual buffers |
| `WHERE date_trunc(...)` không prune | Tắt Seq Scan | Viết lại range predicate trên partition key |
| Parent có index nhưng child scan chậm | Tạo lại index khác ngay | Xem child indexes/statistics/selectivity |
| ATTACH chạy lâu | Terminate mọi session | Xem validation scan/default và lock graph |
| DETACH chờ transaction cũ | Kill tất cả backends | Xem mode, long xacts, concurrent limitations |
| Default chứa dữ liệu tháng mới | Xóa default | Move/reconcile dữ liệu và check constraints |
| Parent stats cũ | Reindex toàn bộ | ANALYZE parent/leaves phù hợp |
| Partition nóng nhiều dead tuples | VACUUM FULL ngay | Xem autovacuum, snapshots, bình thường VACUUM |
| Partition lịch sử tăng disk | DELETE tất cả row | Xem bloat/retention, detach/drop đúng chính sách |
| Nhiều partitions tăng planning time | Tăng shared_buffers vô cớ | Xem granularity và số partition/joins/indexes |
| JOIN nhiều partition chậm | Bật mọi planner flag toàn cục | Đánh giá partitionwise join/agg và memory |
| CREATE INDEX parent chặn ghi | Bỏ index | Lập workflow concurrent per-child đúng phiên bản |
| Retention xong dữ liệu cũ vẫn xuất hiện | DROP thêm mọi bảng | Xem DEFAULT và late-data ingestion |
| `pg_total_relation_size(parent)` nhỏ | Kết luận bảng ít dữ liệu | Cộng sizes của leaves |
| DDL timeout thường xuyên | Tăng timeout vô hạn | Điều tra blockers và thiết kế cửa sổ bảo trì |

## 39. Bài tập thực hành có đáp án

Dùng `part_eval_lab` đã tạo. Các bài có DDL phá hủy, detach, drop hoặc lock mạnh chỉ thực hiện trên **bản sao lab**, không chạy trên production.

### Bài 1. Bảng cha có chứa heap của mọi partition không?

**Đáp án:** không. Declarative partitioned parent là relation logic, còn tuples được lưu ở các leaf partitions. Tổng dung lượng phải tính từ leaves.

### Bài 2. Lấy danh sách tất cả partitions

```sql
SELECT relid::regclass, isleaf, level
FROM pg_partition_tree(
    'part_eval_lab.sales'::regclass
);
```

**Đáp án:** có parent level 0 và các leaves Jan-Apr cùng DEFAULT, nếu chưa thay đổi hierarchy.

### Bài 3. Kiểm tra bounds của February

```sql
SELECT pg_get_expr(c.relpartbound, c.oid)
FROM pg_class AS c
WHERE c.oid = 'part_eval_lab.sales_2026_02'::regclass;
```

**Đáp án:** range từ ngày 2026-02-01 (bao gồm) đến 2026-03-01 (không bao gồm).

### Bài 4. Tại sao SELECT tháng 2 không cần scan January?

**Đáp án:** predicate trên `sold_on` phù hợp partition bounds nên planner/executor có thể prune January. Không cần index trên sold_on chỉ để biết January không chứa ngày tháng 2.

### Bài 5. Viết query dễ prune tháng 3

```sql
SELECT COUNT(*)
FROM part_eval_lab.sales
WHERE sold_on >= DATE '2026-03-01'
  AND sold_on <  DATE '2026-04-01';
```

**Đáp án:** half-open date range khớp bounds March.

### Bài 6. Vì sao `date_trunc('month',sold_on::timestamp)` có thể làm pruning kém?

**Đáp án:** biểu thức biến đổi cột partition key có thể không được optimizer suy ra thành range constraints trên `sold_on` như câu WHERE trực tiếp.

### Bài 7. `Append` có đồng nghĩa quét tất cả partitions không?

**Đáp án:** không. Append có thể chỉ chứa các children còn lại sau plan-time pruning, hoặc executor bỏ bớt subplans ở runtime.

### Bài 8. `Subplans Removed` biểu thị điều gì?

**Đáp án:** số subplans bị loại trong initialization-time partition pruning khi EXPLAIN báo thông tin đó.

### Bài 9. Vì sao generic plan vẫn có thể prune?

**Đáp án:** PostgreSQL có execution-time partition pruning trong những điều kiện được hỗ trợ; executor có thể dùng bind parameter values để bỏ subplans không liên quan.

### Bài 10. Tại sao `(never executed)` trong EXPLAIN đáng chú ý?

**Đáp án:** cho thấy node không chạy ở lần thực thi được đo; có thể là hậu quả runtime pruning hoặc điều kiện điều khiển plan khác. Cần xem cả cây và loops.

### Bài 11. Pruning và Index Scan khác nhau thế nào?

**Đáp án:** pruning loại **cả relation/partition** theo bounds; Index Scan tìm những tuple cần đọc **bên trong relation** theo index.

### Bài 12. Cùng query February tenant 1 và tenant 321 có thể dùng scan khác nhau?

**Đáp án:** có. Tenant 1 là giá trị phổ biến, Seq Scan có thể tốt; tenant 321 ít hàng nên local Index Scan có thể tốt.

### Bài 13. `Merge Append` giúp điều gì?

**Đáp án:** hợp nhất những streams đã được sắp xếp từ child plans để tạo kết quả có thứ tự, có thể tránh global Sort tùy plan.

### Bài 14. `Parallel Append` luôn nhanh hơn Append không?

**Đáp án:** không. Overhead worker/Gather, sizes và storage có thể làm parallel kém hiệu quả trên những partitions nhỏ.

### Bài 15. Tại sao PRIMARY KEY của parent phải chứa partition key?

**Đáp án:** PostgreSQL cần thực thi uniqueness qua local indexes mà không có global unique index thông thường; bao gồm partition key giúp phân định những rows có thể trùng key về cùng partition theo điều kiện hỗ trợ.

### Bài 16. Một index trên parent có lưu entries của mọi child trong một B-tree duy nhất không?

**Đáp án:** không. Partitioned index định nghĩa hierarchy, local indexes vật lý nằm trên children.

### Bài 17. Có thể chạy CREATE INDEX CONCURRENTLY trực tiếp trên partitioned parent như bảng thường không?

**Đáp án:** không được hỗ trợ trên các phiên bản PostgreSQL liên quan. Có thể dùng workflow tạo parent metadata index, xây child indexes concurrently rồi attach theo đúng quy trình/version.

### Bài 18. `CREATE INDEX CONCURRENTLY` có chạy được bên trong BEGIN không?

**Đáp án:** không. Nó có yêu cầu thực thi ngoài transaction block tường minh.

### Bài 19. Vì sao ATTACH có thể phải quét bảng con?

**Đáp án:** PostgreSQL cần xác minh các rows của bảng chuẩn bị attach nằm trong partition bounds nếu không có bằng chứng/constraint đủ thích hợp.

### Bài 20. CHECK constraint validated trước ATTACH giúp gì?

**Đáp án:** có thể chứng minh dữ liệu của bảng thuộc bounds, giảm hoặc tránh validation scan của bảng được attach trong điều kiện phù hợp.

### Bài 21. DEFAULT ảnh hưởng attach tháng mới thế nào?

**Đáp án:** nếu DEFAULT có hàng thuộc tháng mới, cần di chuyển/xử lý chúng; PostgreSQL có thể phải validate và lock DEFAULT trước khi attach.

### Bài 22. CREATE TABLE PARTITION OF và ATTACH có giống nhau không?

**Đáp án:** không. Cái đầu tạo bảng con mới trực tiếp trong hierarchy; cái sau gắn một bảng tương thích đã tồn tại. Chúng có khác biệt về preparation/validation/locks.

### Bài 23. DETACH xong dữ liệu còn tồn tại không?

**Đáp án:** có. Detached table vẫn là bảng độc lập và chứa dữ liệu/index của nó cho tới khi bạn có thao tác xóa/lưu trữ tiếp theo.

### Bài 24. DETACH CONCURRENTLY có luôn dùng được khi có DEFAULT?

**Đáp án:** không. Một số phiên bản/hierarchy có giới hạn khi có default partition; cần xem documentation và kiểm tra môi trường trước khi dùng.

### Bài 25. Vì sao partition retention có thể tốt hơn DELETE hàng triệu rows?

**Đáp án:** detach/drop một partition đủ điều kiện có thể tránh DELETE từng hàng, giảm WAL/dead tuples/VACUUM workload, nhưng có rủi ro DDL/lock và yêu cầu backup/retention.

### Bài 26. Nếu xóa January rồi INSERT một row January thì sao?

**Đáp án:** có thể đi vào DEFAULT nếu còn và không có rule chặn, hoặc nhận lỗi không có partition phù hợp. Cần chính sách late-arriving data.

### Bài 27. Tại sao UPDATE partition key có thể đắt?

**Đáp án:** có thể cần di chuyển tuple sang partition khác, đụng đến indexes/constraints và transaction concurrency trên source/destination.

### Bài 28. Một lock ACCESS EXCLUSIVE trên February có chặn SELECT February không?

**Đáp án:** có, nếu SELECT cần ACCESS SHARE lock không tương thích trên relation đó và transaction giữ khóa chưa kết thúc.

### Bài 29. Lock February có chắc chắn chặn mọi SELECT January không?

**Đáp án:** không. Query January đủ rõ và plan-time prune February có thể tránh child February, nhưng vẫn phải xét parent locks và plan/phiên bản thực tế.

### Bài 30. Tìm PID đang chặn

```sql
SELECT
    pid,
    pg_blocking_pids(pid) AS blockers
FROM pg_stat_activity
WHERE datname = current_database();
```

**Đáp án:** mảng blockers giúp xác định wait graph. Kiểm tra state/application/query trước khi can thiệp.

### Bài 31. Vì sao `pg_locks.granted = false` quan trọng?

**Đáp án:** cho biết một yêu cầu lock chưa được cấp; dùng cùng locktype/mode/relation/waitstart để điều tra contention.

### Bài 32. VACUUM một leaf sẽ tự VACUUM toàn bộ hierarchy không?

**Đáp án:** không. `VACUUM (ANALYZE) part_eval_lab.sales_2026_02` nhắm relation February, không mặc định làm mọi month partition.

### Bài 33. `n_dead_tup` là số hàng chết chính xác tuyệt đối?

**Đáp án:** không. Đây là một estimate/counter của statistics, không phải phép đếm MVCC chính xác theo mọi snapshot.

### Bài 34. Vì sao parent cần ANALYZE thủ công theo thời gian?

**Đáp án:** parent không lưu heap tuples trực tiếp; changes ở children không nhất thiết khiến autovacuum tự cập nhật parent inheritance statistics. Cần lịch ANALYZE parent khi dữ liệu đổi đáng kể.

### Bài 35. Vì sao historical partition vẫn cần quản lý freeze?

**Đáp án:** dù ít ghi, tuổi transaction/freeze vẫn cần được quản lý để tránh rủi ro wraparound và đáp ứng MVCC maintenance.

### Bài 36. `pg_total_relation_size(parent)` có phải tổng bytes của partitions không?

**Đáp án:** không. Cộng `pg_total_relation_size(relid)` của các leaf relations lấy từ `pg_partition_tree`.

### Bài 37. DETACH xong size đo theo cây giảm nhưng disk không giảm, vì sao?

**Đáp án:** detached table không còn trong hierarchy để cộng, nhưng heap/index files của standalone table vẫn tồn tại.

### Bài 38. `enable_partitionwise_join=on` có bắt planner dùng partitionwise join không?

**Đáp án:** không. Đây là khả năng được cân nhắc theo cấu trúc/cost, không phải một hint bắt buộc mọi query.

### Bài 39. `GROUP BY tenant_id` có thể aggregate hoàn toàn theo từng month rồi không gộp không?

**Đáp án:** không trong trường hợp tenant xuất hiện ở nhiều tháng. Có thể cần bước final aggregation để gộp cùng tenant từ nhiều partitions.

### Bài 40. Vì sao `work_mem` cần xét khi bật partitionwise join/aggregate?

**Đáp án:** nhiều partitions có thể tạo nhiều hash/sort nodes, tổng memory tăng. Cần benchmark với concurrency, không bật các cờ toàn server theo cảm tính.

### Bài 41. Khi EXPLAIN chỉ còn February nhưng query vẫn chậm, kiểm tra gì?

**Đáp án:** scan node trong February, estimated/actual rows, local index, selectivity, buffers, join loops, sort/aggregate và data skew. Không tạo thêm partitions để “prune tốt hơn” khi đã prune đúng.

### Bài 42. Khi Planning Time tăng sau khi chia từ 12 lên 365 partitions, nguyên nhân nào có thể?

**Đáp án:** catalog objects và plan paths tăng, nhiều index/hierarchy metadata hơn, có thể tăng planner overhead dù execution-time pruning vẫn tốt.

### Bài 43. Mô tả runbook ATTACH tháng mới

**Đáp án:** xác minh bounds, default, schema/indexes; chuẩn bị/validate CHECK; kiểm tra lock modes, cửa sổ DDL và timeout; attach; ANALYZE; xác minh cây, row routing, plan và monitoring.

### Bài 44. Mô tả runbook retention

**Đáp án:** xác minh cutoff/quyền/backup; kiểm tra data đến muộn, dependencies và replica; chọn detach/archive/drop; quản lý lock timeout; xác minh dữ liệu/space/monitoring sau thực thi.

### Bài 45. Viết bản báo cáo hiệu năng partitioning

**Đáp án gợi ý:** ghi query, parameter, partition key/bounds, số partitions trước/sau pruning, scan path từng child, estimated/actual rows, buffers, planning/execution time, lock wait, stats freshness và overhead maintenance. Chỉ kết luận cải thiện khi đo được với workload đại diện.

## 40. Checklist kiểm tra hệ thống phân vùng

| Câu hỏi | Hành động |
| --- | --- |
| Partition key có phù hợp query/filter chính? | So WHERE patterns và bounds |
| Có thiếu partition tương lai? | Xem `pg_partition_tree`/lịch tạo partition |
| DEFAULT có chứa dữ liệu ngoài ý muốn? | Kiểm tra rows và dates |
| WHERE trên partition key có dễ prune? | Ưu tiên half-open range |
| Predicate có cast/function làm mất pruning? | Viết lại khi phù hợp |
| Query param dùng generic plan? | So runtime pruning và EXPLAIN EXECUTE |
| Bao nhiêu partition được scan thật? | Xem plan nodes, loops, buffers |
| Có `Subplans Removed`? | Phân biệt init-time pruning |
| Có nodes never executed? | Xem per-loop pruning |
| Có quá nhiều partitions? | Đo Planning Time và catalog overhead |
| Partition sau pruning vẫn lớn? | Tối ưu local indexes/scan path |
| Có index hierarchy phù hợp? | Xem parent/child index definitions |
| Có child index bị thiếu/invalid? | Kiểm tra catalog/index maintenance |
| Cần concurrent index build? | Làm trên leaves theo workflow/version |
| ATTACH có scan bảng đang nạp? | CHECK validation chuẩn bị trước |
| DEFAULT có cản ATTACH? | Kiểm tra overlap và lock/scan |
| CREATE PARTITION có lock mạnh? | Chọn cửa sổ triển khai |
| DETACH có dùng CONCURRENTLY được? | Kiểm tra phiên bản/default/tx restrictions |
| DDL có chờ transaction dài? | `pg_blocking_pids`/`pg_stat_activity` |
| Có dùng lock timeout phù hợp? | Không treo DDL vô hạn |
| Retention có cutoff đúng? | Phê duyệt theo nghiệp vụ/compliance |
| Có late-arriving writes? | Reject/quarantine/reconcile |
| Có backup/replica/downstream dependencies? | Xác minh trước DROP |
| Parent statistics có mới? | ANALYZE định kỳ khi cần |
| Child stats có phù hợp? | last_analyze/actual rows |
| Autovacuum child có theo kịp UPDATE? | n_dead_tup, last_autovacuum |
| Historical partitions có freeze policy? | Theo dõi transaction age |
| Có partition bloat lớn? | Đo storage và VACUUM |
| Có cần REINDEX child? | Dựa trên evidence và lock impact |
| Dung lượng đo đã cộng tất cả leaves? | `pg_partition_tree` + size funcs |
| DETACH rồi disk chưa giảm? | Standalone table vẫn tồn tại |
| Có partitionwise join/aggregate? | Đo plan và memory |
| Query có many-to-many join? | Xem loops/row estimates |
| Có monitoring theo từng leaf? | pg_stat_*/pg_statio_* |
| Có theo dõi VACUUM progress? | `pg_stat_progress_vacuum` |
| Có benchmark sau thay đổi DDL? | EXPLAIN ANALYZE BUFFERS |
| Có rollback plan khi migration lỗi? | Checkpoint, cleanup, alert |
| Có đo concurrency và p95/p99? | Không chỉ một EXPLAIN đơn lẻ |
| Có owner cho runbook partition? | Alerting, audit, approvals |

## 41. Tổng kết

Phân vùng giúp tổ chức dữ liệu lớn và cho phép nhiều thao tác vận hành hiệu quả hơn, nhưng cần xem xét đồng thời **kế hoạch truy vấn, khóa và bảo trì**.

Những điều quan trọng nhất:

1. **Partitioned parent là quan hệ logic**, còn leaf partitions chứa heap/index/tuples thật.
2. **Partition pruning** dùng partition bounds để tránh truy cập những partitions không liên quan; nó **khác Index Scan** trong partition.
3. `Append` / `Merge Append` / `Parallel Append` là những hình dạng kế hoạch phổ biến, nhưng không có nghĩa mọi child đều được scan.
4. **Plan-time pruning** thường loại child ngay trước khi hình thành kế hoạch; **execution-time pruning** có thể dùng bind parameters ở executor.
5. Một **generic prepared plan** vẫn có thể runtime prune; phải quan sát `Subplans Removed`, `loops` và `(never executed)`, không suy luận từ chữ Append.
6. Viết predicate **half-open range trực tiếp trên partition key** giúp planner dễ suy luận bounds và tránh bỏ sót timestamp.
7. Local indexes vẫn cần thiết cho queries selective trong leaf. Parent index là **index hierarchy**, không phải một global B-tree trên tất cả dữ liệu.
8. `CREATE INDEX CONCURRENTLY` không được hỗ trợ trực tiếp trên parent partitioned table trong những phiên bản liên quan; có workflow tạo index trên leaves rồi attach.
9. **DDL không miễn phí khóa**: `CREATE PARTITION`, `ATTACH`, `DETACH`, `DROP` có thể cần lock mạnh hoặc phải chờ transaction lâu.
10. **ATTACH** có thể quét bảng mới và DEFAULT để validate bounds; CHECK constraints đã validate có thể giảm scan trong điều kiện phù hợp.
11. **DETACH không phải DROP**: dữ liệu vẫn còn trong standalone table. `DETACH CONCURRENTLY` có giới hạn và không được coi là thao tác tức thì.
12. **Partition retention** có thể tránh DELETE hàng triệu rows nhưng phải gắn với backup, late data, foreign keys, replication và approvals.
13. **VACUUM/ANALYZE/index maintenance** phải được quan sát ở từng leaf. Bảng cha cũng cần kế hoạch ANALYZE để thống kê toàn hierarchy không cũ.
14. **Partition cũ ít ghi vẫn cần freeze policy** theo MVCC, trong khi partition nóng có thể cần autovacuum/autoanalyze tích cực hơn.
15. `pg_total_relation_size(parent)` không phải tổng storage; hãy cộng `pg_total_relation_size` của **các leaves**.
16. `pg_locks`, `pg_stat_activity` và `pg_blocking_pids` giúp xác định DDL/queries nào đang chặn; không terminate session hàng loạt.
17. **Partitionwise join/aggregate** đôi khi giúp giảm work nhưng có thể tăng số plan nodes và memory khi hierarchy lớn.
18. **Đo Planning Time và Execution Time**, cùng buffers/rows/lock waits, mới có thể kết luận partitioning mang lại lợi ích.

Bộ truy vấn cần nhớ:

```sql
-- 1. Cây phân vùng thực tế:
SELECT relid::regclass, isleaf, level
FROM pg_partition_tree(
    'part_eval_lab.sales'::regclass
);

-- 2. Pruning tháng 2:
EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*)
FROM part_eval_lab.sales
WHERE sold_on >= DATE '2026-02-01'
  AND sold_on <  DATE '2026-03-01';

-- 3. Quan sát DDL/lock waits:
SELECT
    pid,
    state,
    wait_event_type,
    wait_event,
    pg_blocking_pids(pid) AS blockers
FROM pg_stat_activity
WHERE datname = current_database();

-- 4. Bảo trì thống kê parent:
ANALYZE part_eval_lab.sales;

-- 5. Đo tổng lưu trữ hiện thuộc hierarchy:
SELECT pg_size_pretty(
    SUM(pg_total_relation_size(relid))
)
FROM pg_partition_tree(
    'part_eval_lab.sales'::regclass
)
WHERE isleaf;
```

**Quy tắc cốt lõi:** khi một hệ thống phân vùng chậm hoặc bị chặn, hãy hỏi **“những phân vùng nào thật sự được đọc, khóa đang được giữ ở parent hay leaf nào, và thống kê/bảo trì của chính các partition đó đang ở trạng thái nào?”**. Trả lời bằng EXPLAIN, lock graph và thống kê từng leaf sẽ chính xác hơn giả định rằng chỉ cần chia bảng theo tháng là đã tối ưu xong.
