# Phân vùng theo RANGE, LIST và HASH trong PostgreSQL

## 1. Vì sao phải phân vùng bảng?

Giả sử một hệ thống thu thập **500 triệu sự kiện** trong nhiều năm. Đội vận hành thường truy vấn sự kiện của 7 ngày gần nhất và cần xóa dữ liệu quá 12 tháng. Nếu tất cả sự kiện nằm trong một bảng heap khổng lồ, các tác vụ sau có thể tốn kém:

- Truy vấn theo ngày phải xem xét một lượng dữ liệu và chỉ mục lớn.
- Xóa dữ liệu cũ theo từng hàng tạo nhiều WAL, dead tuples và công việc VACUUM.
- Một số index trở nên rất lớn, khó xây lại hoặc bảo trì.
- Việc thay đổi chính sách lưu trữ/backup dữ liệu cũ cần thao tác trên cả bảng.
- Thống kê trên toàn bộ dữ liệu có thể che giấu sự khác biệt giữa các giai đoạn/nhóm.

**Partitioning (phân vùng)** cho phép quản lý một **bảng logic** gồm nhiều **bảng vật lý con** (*partitions*), dựa trên giá trị **partition key**. Ứng dụng có thể tiếp tục truy vấn bảng cha như một bảng duy nhất; PostgreSQL định tuyến hàng vào partition và có thể **bỏ qua partition không liên quan** khi điều kiện truy vấn đủ rõ.

PostgreSQL hỗ trợ ba chiến lược **declarative partitioning** cốt lõi:

1. **RANGE:** chia theo các khoảng giá trị, chẳng hạn từng tháng của `event_at`.
2. **LIST:** chia theo tập giá trị cụ thể, chẳng hạn `region IN ('north', 'central')`.
3. **HASH:** chia theo giá trị băm của khóa, chẳng hạn `customer_id` thành nhiều bucket.

### 1.1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Chọn RANGE, LIST hoặc HASH theo workload và cách quản lý dữ liệu.
- Tạo bảng cha `PARTITION BY` và các partitions `PARTITION OF` bằng SQL.
- Giải thích đúng **ranh giới [lower, upper)** của RANGE, tập giá trị và NULL trong LIST, `MODULUS`/`REMAINDER` trong HASH.
- Quan sát hàng được định tuyến đến partition nào bằng `tableoid::regclass`.
- Đọc kế hoạch `EXPLAIN` để xác định **partition pruning** và các trường hợp không prune được.
- Xử lý khóa chính, UNIQUE, FOREIGN KEY, index, constraint và cập nhật partition key.
- Thực hiện `ATTACH PARTITION`, `DETACH PARTITION` và quản lý vòng đời partition.
- Hiểu giới hạn của DEFAULT partition, đổi số HASH partitions và phân vùng nhiều tầng.
- Giám sát thống kê, autovacuum, số lượng partitions, tài nguyên và ảnh hưởng trên production.
- Thực hành các bài tập, phân tích tình huống và chọn phương án phù hợp.

> **Lưu ý môi trường:** các ví dụ tập trung vào PostgreSQL hiện đại có declarative partitioning. Chi tiết index concurrent, foreign keys, pruning, partitioned index và một số DDL khác có thể phụ thuộc phiên bản. Hãy kiểm tra phiên bản đang dùng khi triển khai production. Chỉ chạy phần thực hành trên database/schema có quyền; đặc biệt không DROP/TRUNCATE/DETACH dữ liệu thật để thử nghiệm.

---

## 2. Một bảng partitioned gồm những gì?

Mô hình RANGE đơn giản:

~~~text
                 Bảng logic: events
               PARTITION BY RANGE(event_at)
                          |
          +---------------+-----------------+
          |               |                 |
          v               v                 v
  events_2026_10    events_2026_11    events_2026_12
  [Oct 1, Nov 1)    [Nov 1, Dec 1)    [Dec 1, Jan 1)
     dữ liệu           dữ liệu           dữ liệu
     + index           + index           + index
~~~

**Bảng cha partitioned** mô tả schema logic và quy tắc phân vùng. Trong declarative partitioning, bản thân bảng cha có `relkind = 'p'` và **không lưu những hàng dữ liệu thông thường** vào một heap cha; dữ liệu nằm ở các **leaf partitions**.

Các khái niệm:

| Khái niệm | Diễn giải |
|---|---|
| **Partitioned table / parent** | Bảng logic có định nghĩa `PARTITION BY`; truy vấn cha thường nhìn dữ liệu các partitions |
| **Partition key** | Cột hoặc biểu thức quyết định đường định tuyến |
| **Partition bound** | Điều kiện RANGE/LIST/HASH xác định mỗi child nhận giá trị nào |
| **Partition / child** | Relation chứa dữ liệu, hoặc một partitioned table cấp trung gian |
| **Leaf partition** | Child cuối cùng lưu row vật lý |
| **Default partition** | Partition bắt giá trị không rơi vào partition được định nghĩa, với RANGE/LIST |
| **Partition pruning** | Bỏ các partitions không thể có row thỏa query |
| **Partition-wise join/aggregate** | Các tối ưu có điều kiện khi join/tổng hợp từng partition |

### 2.1. Partitioning không phải sharding

Các partitions thông thường vẫn thuộc **cùng một PostgreSQL database/cluster**, dùng chung transaction, WAL, planner và cơ chế quản trị. Partitioning **không tự động phân phối bảng lên nhiều máy** hoặc tăng tổng năng lực CPU/RAM như sharding nhiều node.

Một partition có thể dùng tablespace riêng theo cấu hình, nhưng điều đó không đồng nghĩa hệ thống trở thành distributed database.

### 2.2. Partitioning không tự làm mọi truy vấn nhanh hơn

Nếu query:

~~~sql
SELECT COUNT(*)
FROM partition_lab.events;
~~~

không có bộ lọc, PostgreSQL vẫn phải tính trên các partitions liên quan. Việc có 48 partitions thay vì một bảng không làm biến mất nhu cầu xử lý mọi hàng.

Lợi ích đáng kể thường đến khi:

- Có **predicate phù hợp partition key** để pruning.
- Có thể **DETACH/DROP partition cũ** theo chính sách retention.
- Có tác vụ bảo trì/index/storage thực hiện theo từng partition.
- Có partition-wise operations đúng điều kiện.
- Kích thước mỗi partition và số partitions được chọn hợp lý.

### 2.3. Chọn khóa phân vùng có ảnh hưởng lâu dài

Partition key không chỉ quyết định routing. Nó ảnh hưởng:

- Độ hiệu quả pruning của query.
- Điều kiện khóa chính/UNIQUE ở bảng cha.
- Cách UPDATE chuyển row giữa partitions.
- Chi phí tạo index, thống kê, quản lý lifecycle.
- Khả năng thêm/bớt partition mà không gây downtime.
- Số partitions một query phải xét.

Vì vậy partitioning là quyết định **thiết kế dữ liệu và vận hành**, không phải một câu CREATE TABLE tùy ý.

---

## 3. So sánh ba chiến lược trước khi viết SQL

| Tiêu chí | RANGE | LIST | HASH |
|---|---|---|---|
| Quy tắc chia | Khoảng có thứ tự | Tập giá trị rời rạc | Kết quả hàm băm theo modulus/remainder |
| Ví dụ key | `event_at`, `order_date`, `account_id` theo dải | `region`, `country_code`, `status` | `customer_id`, `tenant_id` |
| Điểm mạnh | Pruning theo khoảng; quản lý retention theo thời gian | Chính sách riêng cho từng nhóm có danh tính rõ | Phân phối nhiều giá trị khóa vào buckets tương đối cân bằng khi phù hợp |
| Truy vấn thường hợp | `event_at >= ... AND event_at < ...` | `region='north'`, `region IN (...)` | `customer_id=42` |
| Query theo khoảng thời gian | Thường rất hợp nếu key là thời gian | Không tự được lợi nếu key là region | Không tự được lợi nếu key là customer |
| Quản lý dữ liệu cũ | Rất thuận tiện nếu phân vùng theo thời gian | Thuận tiện theo nhóm cụ thể | Thường không phù hợp retention theo thời gian |
| Tăng số partitions | Thêm khoảng mới có thể tương đối dễ nếu chuẩn bị trước | Thêm/chuyển nhóm cần xem DEFAULT/data | Rebalance thường không đơn giản khi bucket coverage đã đầy |
| DEFAULT partition | Có | Có | Không có |
| NULL key | DEFAULT có thể nhận NULL; RANGE bounds không liệt kê NULL | Có thể định nghĩa `FOR VALUES IN (NULL)` hoặc dùng DEFAULT | Giá trị NULL có cơ chế hash routing phù hợp, không dựa vào DEFAULT |
| Rủi ro thiết kế | Thời gian lệch múi giờ, thiếu partition tháng mới | Nhóm quá nhỏ/lệch, case sensitivity | Skew theo hash key, mở rộng buckets, truy vấn thiếu key |
| Độ phân phối thực tế | Theo lượng dữ liệu trong khoảng | Theo số rows của mỗi giá trị/nhóm | Theo phân bố distinct keys và hash, không phải bảo đảm 4 partitions luôn bằng nhau |

**Ví dụ chọn nhanh:** logs theo tháng → RANGE; dữ liệu cần chính sách từng quốc gia → LIST; truy cập chủ yếu một tenant theo `tenant_id` và mong chia lưu trữ theo nhiều buckets → HASH.

---

## 4. Cú pháp tổng quan declarative partitioning

### 4.1. Tạo bảng cha

~~~sql
CREATE TABLE schema_name.parent_table (
    id BIGINT NOT NULL,
    partition_key SOME_TYPE NOT NULL,
    payload TEXT
)
PARTITION BY RANGE (partition_key);
~~~

Tương tự:

~~~sql
PARTITION BY LIST (partition_key)
~~~

hoặc:

~~~sql
PARTITION BY HASH (partition_key)
~~~

### 4.2. Tạo partitions

RANGE:

~~~sql
CREATE TABLE schema_name.parent_2026_11
PARTITION OF schema_name.parent_table
FOR VALUES FROM ('2026-11-01') TO ('2026-12-01');
~~~

LIST:

~~~sql
CREATE TABLE schema_name.parent_north
PARTITION OF schema_name.parent_table
FOR VALUES IN ('north', 'northern');
~~~

HASH:

~~~sql
CREATE TABLE schema_name.parent_h0
PARTITION OF schema_name.parent_table
FOR VALUES WITH (MODULUS 4, REMAINDER 0);
~~~

Ba ví dụ trên chỉ để thấy **dạng cú pháp**; không chạy liên tiếp trên cùng một parent vì `PARTITION BY` là lựa chọn cố định của bảng cha.

### 4.3. Routing khi INSERT

~~~sql
INSERT INTO schema_name.parent_table (...)
VALUES (...);
~~~

PostgreSQL định tuyến hàng đến child có bound phù hợp. Nếu không có partition nhận giá trị và không có DEFAULT hỗ trợ, INSERT **báo lỗi**, không tự tạo partition mới.

### 4.4. Truy vấn parent và truy vấn một partition

~~~sql
SELECT * FROM schema_name.parent_table;
~~~

thường đọc dữ liệu của các partitions theo plan phù hợp.

~~~sql
SELECT * FROM schema_name.parent_2026_11;
~~~

chỉ đọc một partition cụ thể. Trong phần lớn nghiệp vụ, ứng dụng nên truy vấn **parent** để tránh hardcode tên partitions theo thời gian, rồi để planner prune.

---

## 5. Tạo schema lab an toàn

Các ví dụ sau dùng schema riêng:

~~~sql
CREATE SCHEMA IF NOT EXISTS partition_lab;
~~~

Hãy chạy trên database thử nghiệm. Một số câu CREATE tạo objects có tên cố định; **không chạy lặp lại trên cùng schema nếu đã tạo chúng**, hoặc dùng database/schema lab mới khi cần chạy từ đầu.

Các ngày dùng trong ví dụ là mốc minh họa cố định; không cần dữ liệu tương ứng với đồng hồ hệ thống hiện tại.

---

## 6. RANGE: phân vùng bảng sự kiện theo tháng

### 6.1. Tạo parent có khóa theo thời gian

~~~sql
CREATE TABLE partition_lab.events (
    event_id BIGINT NOT NULL,
    event_at TIMESTAMPTZ NOT NULL,
    tenant_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (event_at, event_id)
)
PARTITION BY RANGE (event_at);
~~~

Giải thích:

- `event_at` là partition key.
- `TIMESTAMPTZ` lưu một thời điểm tuyệt đối, hỗ trợ biểu diễn múi giờ khi nhập/xuất.
- `event_id` do application hoặc dịch vụ ID cấp trong ví dụ.
- Khóa chính gồm **`event_at` và `event_id`**; điều này liên quan giới hạn UNIQUE trên partitioned tables, giải thích sau.
- Parent là bảng logic, chưa có leaf partitions để nhận dữ liệu.

### 6.2. Tạo ba partition tháng

~~~sql
CREATE TABLE partition_lab.events_2026_10
PARTITION OF partition_lab.events
FOR VALUES FROM ('2026-10-01 00:00:00+00')
           TO   ('2026-11-01 00:00:00+00');

CREATE TABLE partition_lab.events_2026_11
PARTITION OF partition_lab.events
FOR VALUES FROM ('2026-11-01 00:00:00+00')
           TO   ('2026-12-01 00:00:00+00');

CREATE TABLE partition_lab.events_2026_12
PARTITION OF partition_lab.events
FOR VALUES FROM ('2026-12-01 00:00:00+00')
           TO   ('2027-01-01 00:00:00+00');
~~~

Tháng 10 nhận thời điểm từ đầu 01/10/2026 đến **trước** đầu 01/11/2026; tháng 11 tương tự.

### 6.3. Tạo DEFAULT partition

~~~sql
CREATE TABLE partition_lab.events_other
PARTITION OF partition_lab.events
DEFAULT;
~~~

DEFAULT nhận dữ liệu không khớp các bounds RANGE đang định nghĩa, ví dụ 2027-01 hoặc 2026-09. Nó là **vùng dự phòng**, không nên để trở thành “kho dữ liệu vô danh” chứa hàng trăm triệu rows vì quên tạo partition tháng mới.

### 6.4. Nạp dữ liệu qua bảng cha

~~~sql
INSERT INTO partition_lab.events
    (event_id, event_at, tenant_id, event_type, payload)
VALUES
    (1001, '2026-10-31 23:59:59+00', 11, 'view', '{"page":"home"}'),
    (1002, '2026-11-01 00:00:00+00', 11, 'login', '{"device":"mobile"}'),
    (1003, '2026-11-15 08:30:00+00', 12, 'purchase', '{"amount":150}'),
    (1004, '2026-12-01 00:00:00+00', 13, 'logout', '{}'),
    (1005, '2027-01-05 10:00:00+00', 11, 'login', '{}');
~~~

Các JSON strings được cast ngầm theo cột `JSONB` khi INSERT. Nếu môi trường/công cụ cần cú pháp chặt chẽ, có thể viết `'{"page":"home"}'::jsonb`.

### 6.5. Kiểm tra routing bằng tableoid

~~~sql
SELECT
    event_id,
    event_at,
    tenant_id,
    event_type,
    tableoid::regclass AS physical_partition
FROM partition_lab.events
ORDER BY event_at, event_id;
~~~

Kỳ vọng:

| event_id | Partition |
|---:|---|
| 1001 | `partition_lab.events_2026_10` |
| 1002 | `partition_lab.events_2026_11` |
| 1003 | `partition_lab.events_2026_11` |
| 1004 | `partition_lab.events_2026_12` |
| 1005 | `partition_lab.events_other` |

`tableoid` chỉ ra OID của relation thực sự lưu row. Giá trị in dạng regclass có thể được rút gọn theo `search_path`; vì thế đừng dùng một chuỗi kết quả cụ thể làm khóa ứng dụng.

### 6.6. Parent không lưu heap rows

~~~sql
SELECT COUNT(*) AS all_rows
FROM partition_lab.events;
~~~

Kỳ vọng: 5 nếu chỉ nạp dữ liệu một lần.

~~~sql
SELECT COUNT(*) AS only_parent_rows
FROM ONLY partition_lab.events;
~~~

Kỳ vọng: 0 vì declarative partitioned parent không chứa các tuple thường. `ONLY` ngăn mở rộng đến child partitions, không phải thủ thuật xóa dữ liệu.

---

## 7. RANGE: hiểu đúng ranh giới và giá trị đặc biệt

### 7.1. Lower bound bao gồm, upper bound loại trừ

RANGE sử dụng logic:

\[
\text{lower} \le x < \text{upper}
\]

Ví dụ:

~~~text
Partition October: [2026-10-01 00:00+00, 2026-11-01 00:00+00)
Partition November:[2026-11-01 00:00+00, 2026-12-01 00:00+00)
~~~

Thời điểm **01/11/2026 00:00 UTC** thuộc November, không thuộc October. Hai partitions có thể nằm sát nhau mà **không chồng lấn**.

### 7.2. Không cần “23:59:59.999999” làm upper bound

Sai hướng thiết kế:

~~~text
October: FROM 2026-10-01 TO 2026-10-31 23:59:59
November: FROM 2026-11-01 TO ...
~~~

Cách này dễ tạo **khoảng trống** giữa thời điểm có phần giây và ranh giới. Hãy dùng upper bound **đầu tháng sau**. PostgreSQL sẽ loại upper endpoint theo đúng semantics.

### 7.3. MINVALUE và MAXVALUE

RANGE có thể dùng các giá trị đặc biệt ở bound:

~~~sql
CREATE TABLE partition_lab.range_demo (
    id BIGINT NOT NULL,
    score INTEGER
) PARTITION BY RANGE (score);

CREATE TABLE partition_lab.range_demo_low
PARTITION OF partition_lab.range_demo
FOR VALUES FROM (MINVALUE) TO (0);

CREATE TABLE partition_lab.range_demo_mid
PARTITION OF partition_lab.range_demo
FOR VALUES FROM (0) TO (100);

CREATE TABLE partition_lab.range_demo_high
PARTITION OF partition_lab.range_demo
FOR VALUES FROM (100) TO (MAXVALUE);
~~~

`MINVALUE/MAXVALUE` là ký hiệu **bound** cho partitioning, không phải các giá trị INTEGER mà ứng dụng INSERT. Với dữ liệu `score=NULL` và không có DEFAULT, **RANGE không tự có partition nhận NULL**.

### 7.4. DEFAULT không chứng minh mọi dữ liệu đều đúng miền kỳ vọng

Nếu bạn dùng DEFAULT để nhận mọi giá trị ngoài ba tháng, các hàng từ năm 2001 hoặc 2100 vẫn có thể được chèn nếu các constraint khác cho phép. DEFAULT giúp tránh lỗi thiếu partition nhưng có thể che giấu lỗi input hoặc job tạo partition bị ngừng.

Cần giám sát số rows trong DEFAULT:

~~~sql
SELECT COUNT(*) AS default_rows
FROM partition_lab.events_other;
~~~

### 7.5. Nhiều cột RANGE là thứ tự từ điển

PostgreSQL có thể phân vùng:

~~~sql
CREATE TABLE partition_lab.range_composite_demo (
    tenant_id INTEGER NOT NULL,
    seq_no INTEGER NOT NULL,
    note TEXT
)
PARTITION BY RANGE (tenant_id, seq_no);
~~~

Với khóa hai cột, so sánh bounds theo **thứ tự từ điển (lexicographic)**, không phải “tenant_id nằm trong khoảng A đồng thời seq_no nằm trong khoảng B” như hai điều kiện độc lập.

Ví dụ một partition:

~~~sql
CREATE TABLE partition_lab.range_composite_1
PARTITION OF partition_lab.range_composite_demo
FOR VALUES FROM (1, 0) TO (2, 0);
~~~

Partition này nhận các khóa như `(1,0)`, `(1,999)`, nhưng không nhận `(2,0)`. Nó không phải “hình chữ nhật” gồm tenant_id từ 1 đến 2 và seq_no 0 đến 0.

Đừng dùng RANGE nhiều cột để thay thế cơ chế **subpartition theo nhiều chiều** nếu yêu cầu thực sự cần chia theo thời gian rồi tenant một cách độc lập.

---

## 8. Pruning với RANGE: vì sao query phải có điều kiện phù hợp?

### 8.1. Query lọc nửa khoảng

~~~sql
EXPLAIN
SELECT event_id, event_at, tenant_id
FROM partition_lab.events
WHERE event_at >= TIMESTAMPTZ '2026-11-10 00:00:00+00'
  AND event_at <  TIMESTAMPTZ '2026-11-20 00:00:00+00';
~~~

Nếu metadata partitions đúng, planner có thể loại October, December và DEFAULT khỏi truy cập dữ liệu vì **chỉ November chứa hàng thỏa điều kiện**.

Một dạng plan minh họa:

~~~text
Seq Scan on events_2026_11
  Filter: (event_at >= ... AND event_at < ...)
~~~

Với bảng chỉ năm dòng, PostgreSQL có thể dùng Seq Scan trên đúng partition, điều đó **không có nghĩa partitioning thất bại**. Pruning và việc chọn **index scan hay seq scan bên trong partition** là hai quyết định khác nhau.

### 8.2. Query không lọc key

~~~sql
EXPLAIN
SELECT *
FROM partition_lab.events
WHERE tenant_id = 11;
~~~

Vì parent được chia theo `event_at`, PostgreSQL không thể chỉ từ `tenant_id=11` mà biết sự kiện nằm ở tháng nào. Plan có thể dùng `Append` trên các partitions, mỗi child có local index nếu đã tạo.

### 8.3. Khác biệt partition pruning và index filtering

- **Partition pruning:** bỏ toàn bộ relation con không thể có row khớp.
- **Index filtering:** trong relation còn lại, dùng index để tìm row/page phù hợp.
- **Row filter:** executor kiểm tra điều kiện trên những candidates đã được lấy.

Một query tối ưu có thể **vừa prune partition vừa dùng local index**. Không coi hai cơ chế là một.

### 8.4. Kiểm tra số partitions thực sự tham gia

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*)
FROM partition_lab.events
WHERE event_at >= TIMESTAMPTZ '2026-11-01 00:00:00+00'
  AND event_at <  TIMESTAMPTZ '2026-12-01 00:00:00+00';
~~~

Đọc các node child thực sự chạy, `Subplans Removed` nếu có, và `never executed` cho những nhánh bị loại ở runtime. Output tùy PostgreSQL version, độ phức tạp predicate, prepared parameters và plan type.

---

## 9. RANGE và thời gian: múi giờ là một phần của thiết kế

### 9.1. TIMESTAMPTZ lưu thời điểm, không lưu “chuỗi giờ + timezone gốc”

Trong PostgreSQL, `TIMESTAMPTZ` biểu diễn một **instant**. Hiển thị có thể khác theo session timezone:

~~~sql
SHOW TimeZone;

SELECT
    TIMESTAMPTZ '2026-11-01 00:00:00+00'
        AS utc_instant;
~~~

Nếu session hiển thị theo Asia/Ho_Chi_Minh (+07 lúc ví dụ), cùng instant được trình bày là **07:00 ngày 01/11**. Routing dựa trên **giá trị thời điểm** và bounds, không dựa vào chuỗi UI sau khi định dạng.

### 9.2. Partition theo ngày UTC khác ngày địa phương

Một sự kiện lúc `2026-10-31 20:00:00+00` có thể là sáng 01/11 theo giờ Việt Nam, nhưng nó nằm trong **partition October UTC** nếu bounds chia theo UTC.

Nếu yêu cầu nghiệp vụ “mỗi partition đúng ngày địa phương”, cần **thiết kế partition key/bounds theo quy tắc ngày địa phương** và chú ý daylight saving ở các múi giờ có DST. Đừng giả định `date(event_at)` trong timezone session sẽ luôn tương ứng tháng UTC của partition.

### 9.3. Điều kiện theo timezone cần suy ra khoảng trên partition key

Ví dụ query thực sự muốn ngày 01/11 theo Asia/Ho_Chi_Minh:

~~~sql
SELECT event_id, event_at
FROM partition_lab.events
WHERE event_at >= TIMESTAMP '2026-11-01 00:00:00'
                      AT TIME ZONE 'Asia/Ho_Chi_Minh'
  AND event_at <  TIMESTAMP '2026-11-02 00:00:00'
                      AT TIME ZONE 'Asia/Ho_Chi_Minh';
~~~

Hình thức này đưa **hai cận thời điểm** về cùng kiểu với `event_at` để PostgreSQL có cơ hội prune theo RANGE. Với những vùng có DST, dùng cận ngày địa phương **riêng biệt** như trên thay vì luôn cộng cứng 24 giờ cho một ngày địa phương.

### 9.4. Function bọc trên partition key có thể hạn chế pruning

~~~sql
-- Cần đo plan; không tự coi tương đương khả năng pruning:
WHERE date_trunc('month', event_at) =
      TIMESTAMPTZ '2026-11-01 00:00:00+00'
~~~

Tùy cách định nghĩa timezone, semantics của biểu thức còn có thể khác. Nếu parent partition theo `event_at` trực tiếp, điều kiện half-open range trên chính key thường rõ hơn cho pruning.

---

## 10. LIST: phân vùng theo nhóm giá trị

### 10.1. Tạo bảng hỗ trợ theo vùng

~~~sql
CREATE TABLE partition_lab.support_tickets (
    ticket_id BIGINT NOT NULL,
    region TEXT,
    subject TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
PARTITION BY LIST (region);
~~~

Chú ý: trong ví dụ này `region` cho phép NULL để minh họa cách LIST định tuyến NULL. Vì không có khóa chính, cùng ticket_id có thể xuất hiện ở nhiều partitions nếu ứng dụng không kiểm soát; phần constraint sau giải thích cách xử lý.

### 10.2. Các nhóm giá trị cụ thể

~~~sql
CREATE TABLE partition_lab.support_tickets_north
PARTITION OF partition_lab.support_tickets
FOR VALUES IN ('north', 'northern');

CREATE TABLE partition_lab.support_tickets_south
PARTITION OF partition_lab.support_tickets
FOR VALUES IN ('south');

CREATE TABLE partition_lab.support_tickets_null
PARTITION OF partition_lab.support_tickets
FOR VALUES IN (NULL);

CREATE TABLE partition_lab.support_tickets_other
PARTITION OF partition_lab.support_tickets
DEFAULT;
~~~

- `north` và `northern` đều vào partition north.
- `south` vào partition south.
- `NULL` vào partition null đã chỉ định.
- Những giá trị còn lại như `'west'` vào DEFAULT.

Các tập giá trị LIST không được chồng lấn trên cùng parent. Không thể tạo thêm một partition khác cũng nhận `'north'`.

### 10.3. Nạp dữ liệu

~~~sql
INSERT INTO partition_lab.support_tickets
    (ticket_id, region, subject)
VALUES
    (1, 'north', 'Ứng dụng không đăng nhập'),
    (2, 'northern', 'Lỗi nhập liệu'),
    (3, 'south', 'Yêu cầu báo cáo'),
    (4, 'west', 'Hỗ trợ tài khoản'),
    (5, NULL, 'Chưa xác định khu vực');

SELECT
    ticket_id, region, subject,
    tableoid::regclass AS physical_partition
FROM partition_lab.support_tickets
ORDER BY ticket_id;
~~~

Kỳ vọng các ticket lần lượt rơi vào north, north, south, other và null.

### 10.4. LIST không tự chuẩn hóa chữ hoa/thường

`'north'` và `'North'` là các giá trị khác nhau đối với kiểu `text`/collation phù hợp; không giả định PostgreSQL tự gọi `lower(region)` trước routing.

Nếu hệ thống muốn không phân biệt hoa/thường, có thể:

- Chuẩn hóa dữ liệu trong application.
- Dùng một cột chuẩn hóa riêng làm partition key.
- Cân nhắc expression partition key `PARTITION BY LIST ((lower(region)))` khi phù hợp, đồng thời hiểu giới hạn UNIQUE/PK với partition key biểu thức.

Không thay đổi semantics của dữ liệu production một cách ngầm định.

### 10.5. LIST có một partition key

Trong declarative LIST partitioning, khóa phân vùng được giới hạn ở **một cột hoặc một biểu thức** tại mỗi cấp. Muốn phân vùng theo country rồi channel, có thể dùng **subpartitioning**; không viết `PARTITION BY LIST(country, channel)` và mong tạo các nhóm cặp tùy ý như RANGE nhiều cột.

---

## 11. Pruning và truy vấn LIST

### 11.1. Tìm ticket theo region

~~~sql
EXPLAIN
SELECT ticket_id, subject
FROM partition_lab.support_tickets
WHERE region = 'north';
~~~

Planner có thể prune các partitions không chứa `'north'`, chỉ đọc partition north.

### 11.2. Truy vấn nhiều region

~~~sql
EXPLAIN
SELECT ticket_id, region, subject
FROM partition_lab.support_tickets
WHERE region IN ('north', 'south');
~~~

Có thể đọc north và south, không cần các partitions khác nếu planner suy ra được.

### 11.3. Query NULL

~~~sql
EXPLAIN
SELECT ticket_id, subject
FROM partition_lab.support_tickets
WHERE region IS NULL;
~~~

Vì partition null được khai báo riêng, PostgreSQL có cơ hội đọc đúng partition đó. **`region = NULL` không phải điều kiện SQL đúng**; phép so sánh bằng NULL trả UNKNOWN, hãy dùng `IS NULL`.

### 11.4. Query không có region

~~~sql
EXPLAIN
SELECT COUNT(*)
FROM partition_lab.support_tickets
WHERE created_at >= TIMESTAMPTZ '2026-01-01 00:00:00+00';
~~~

Parent chia theo region, không phải created_at, nên điều kiện thời gian một mình thường không prune theo region. Có thể cần index thời gian trên mỗi partition, hoặc xem lại chiến lược phân vùng nếu truy vấn theo thời gian là chính.

### 11.5. Khi nào LIST hợp lý?

- Danh tính nhóm ít thay đổi và cần quản lý riêng.
- Có chính sách dữ liệu theo region/country/category.
- Nhiều query lọc một hoặc vài nhóm.
- Muốn áp dụng tablespace/maintenance/storage theo nhóm.
- Có khả năng giám sát DEFAULT và xử lý giá trị nhóm mới.

Không chọn LIST theo `status` nếu trạng thái thay đổi liên tục và mỗi update khiến row chuyển partition, trừ khi có lý do vận hành mạnh.

---

## 12. LIST: NULL, DEFAULT, nhóm mới và skew

### 12.1. NULL là một giá trị phân vùng đặc biệt trong LIST

Một LIST partition có thể khai báo `FOR VALUES IN (NULL)`. Nếu không khai báo NULL riêng mà có DEFAULT, NULL có thể được định tuyến vào DEFAULT. Nếu không có cả hai, INSERT NULL **không tìm thấy partition**.

Điều này khác với `RANGE`, nơi các bounds thứ tự không nhận NULL trực tiếp.

### 12.2. DEFAULT cũng nhận nhiều giá trị không liệt kê

Trong lab, `west` vào `support_tickets_other`. Nếu ngày mai xuất hiện `east` và `central`, chúng cũng vào DEFAULT nếu chưa tạo partitions riêng.

Truy vấn:

~~~sql
SELECT region, COUNT(*) AS ticket_count
FROM partition_lab.support_tickets_other
GROUP BY region
ORDER BY ticket_count DESC;
~~~

giúp xem DEFAULT đang giữ nhóm nào. Không coi việc hệ thống vẫn INSERT thành công là bằng chứng partition lifecycle đã vận hành đúng.

### 12.3. Thêm partition mới khi DEFAULT đã có dữ liệu tương ứng

Nếu DEFAULT đã chứa `region='west'`, một lệnh:

~~~sql
-- Minh họa rủi ro; cần chuyển dữ liệu DEFAULT trước:
CREATE TABLE partition_lab.support_tickets_west
PARTITION OF partition_lab.support_tickets
FOR VALUES IN ('west');
~~~

không được coi là phương án có thể chạy thẳng. PostgreSQL phải bảo đảm DEFAULT không còn chứa row thuộc miền sẽ được chuyển sang partition mới; nếu có row tương ứng, thao tác tạo/attach sẽ **bị từ chối** cho đến khi dữ liệu được chuyển và các kiểm tra an toàn hoàn tất.

Không tự DELETE dữ liệu DEFAULT để làm cho DDL chạy: phải có kế hoạch **di chuyển** hàng, xử lý ghi đồng thời và rollback.

### 12.4. Skew trong LIST

Nếu 95% tickets thuộc north, một partition north có thể rất lớn trong khi south nhỏ. LIST không cân bằng số rows; nó đảm bảo **đúng giá trị nhóm**.

Có thể subpartition north theo ngày/hash nếu thực sự cần và có workload phù hợp; không tạo hàng trăm partitions theo mỗi giá trị hiếm khi số lượng không thể quản lý.

---

## 13. HASH: phân vùng theo kết quả hash của khóa

### 13.1. Tạo parent HASH theo customer_id

~~~sql
CREATE TABLE partition_lab.orders_hash (
    order_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    amount NUMERIC(12,2) NOT NULL CHECK (amount >= 0),
    placed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (customer_id, order_id)
)
PARTITION BY HASH (customer_id);
~~~

Khóa chính gồm `customer_id` vì đây là partition key. Để đảm bảo mỗi order_id duy nhất **toàn hệ thống**, ứng dụng cần thêm chiến lược tạo/kiểm soát ID phù hợp; `PRIMARY KEY(customer_id,order_id)` chỉ đảm bảo cặp.

### 13.2. Tạo bốn buckets

~~~sql
CREATE TABLE partition_lab.orders_hash_h0
PARTITION OF partition_lab.orders_hash
FOR VALUES WITH (MODULUS 4, REMAINDER 0);

CREATE TABLE partition_lab.orders_hash_h1
PARTITION OF partition_lab.orders_hash
FOR VALUES WITH (MODULUS 4, REMAINDER 1);

CREATE TABLE partition_lab.orders_hash_h2
PARTITION OF partition_lab.orders_hash
FOR VALUES WITH (MODULUS 4, REMAINDER 2);

CREATE TABLE partition_lab.orders_hash_h3
PARTITION OF partition_lab.orders_hash
FOR VALUES WITH (MODULUS 4, REMAINDER 3);
~~~

Với `MODULUS 4`, `REMAINDER` hợp lệ là 0, 1, 2, 3. Mỗi giá trị partition key được PostgreSQL hash theo cơ chế operator class và rơi vào đúng một remainder tương ứng.

### 13.3. Nạp dữ liệu qua parent

~~~sql
INSERT INTO partition_lab.orders_hash
    (order_id, customer_id, amount)
VALUES
    (1, 101, 150.00),
    (2, 101, 200.00),
    (3, 102, 90.00),
    (4, 103, 45.00),
    (5, 104, 990.00),
    (6, 105, 110.00),
    (7, 106, 35.00),
    (8, 107, 80.00);

SELECT
    order_id,
    customer_id,
    amount,
    tableoid::regclass AS physical_partition
FROM partition_lab.orders_hash
ORDER BY order_id;
~~~

### 13.4. HASH không đồng nghĩa SQL modulo trên ID

Sai:

~~~text
Nếu customer_id % 4 = 1
→ chắc chắn hàng nằm orders_hash_h1
~~~

PostgreSQL không bắt buộc partition remainder bằng phép `customer_id % 4` thông thường. Nó băm **giá trị qua hash support function và quy tắc nội bộ**, sau đó áp modulus/remainder.

Dùng `tableoid::regclass` để **quan sát routing thực**, không dự đoán tên child bằng phép modulo nguyên đơn giản.

### 13.5. Những order cùng customer vào cùng partition

Đối với cùng partition key `customer_id=101`, các rows được định tuyến vào **cùng HASH partition** theo quy tắc bound tương ứng. Điều này hữu ích khi truy vấn theo customer_id, nhưng nếu một customer chiếm 80% dữ liệu, partition chứa customer đó vẫn có thể cực lớn.

HASH không “tách một customer quá lớn ra nhiều buckets” nếu chỉ hash theo customer_id.

---

## 14. HASH: MODULUS, REMAINDER và phạm vi bao phủ

### 14.1. Một bucket là tập giá trị hash, không phải khoảng ID

Định nghĩa:

~~~sql
FOR VALUES WITH (MODULUS 4, REMAINDER 2)
~~~

nghĩa là các khóa có kết quả hash **thỏa remainder 2 theo modulus 4** nằm trong partition này.

Nó không có nghĩa nhận `customer_id BETWEEN 2 AND 999999`, cũng không có nghĩa nhóm customers thứ ba theo thứ tự tăng.

### 14.2. HASH không có DEFAULT partition

Khác RANGE/LIST, PostgreSQL **không hỗ trợ DEFAULT cho HASH partitioning**. Nếu không có partition phù hợp remainder, INSERT có thể báo “no partition of relation found for row”.

### 14.3. Các bounds không được chồng lấn

Không tạo hai child cùng `MODULUS 4, REMAINDER 1` dưới một parent. PostgreSQL phải bảo đảm mỗi giá trị chỉ định tuyến tới một partition phù hợp.

### 14.4. Có thể có modulus khác nhau không?

PostgreSQL có quy tắc tương thích cho các hash partition bounds với modulus khác nhau; modulus lớn phải là bội phù hợp của modulus nhỏ theo yêu cầu khai báo. Nhưng việc **trộn modulus** không đồng nghĩa cơ sở dữ liệu tự di chuyển rows khi bạn thêm một child mới.

Trong bài nhập môn/vận hành, nên dùng cùng modulus và đủ remainders theo kế hoạch, rồi thiết kế migration rõ ràng khi cần thay đổi.

### 14.5. Bốn buckets không đảm bảo mỗi bucket 25% rows

Điều đó chỉ gần đúng khi có đủ số giá trị key độc lập và phân bố tương đối đều. Nếu dữ liệu có vài khóa rất phổ biến hoặc có rất ít distinct keys, phân bố rows có thể lệch.

Kiểm tra:

~~~sql
SELECT
    tableoid::regclass AS partition_name,
    COUNT(*) AS row_count
FROM partition_lab.orders_hash
GROUP BY tableoid
ORDER BY row_count DESC, partition_name;
~~~

### 14.6. Pruning khi query bằng khóa hash

~~~sql
EXPLAIN
SELECT order_id, customer_id, amount
FROM partition_lab.orders_hash
WHERE customer_id = 101;
~~~

Vì `customer_id` là partition key, PostgreSQL có thể xác định bucket phù hợp và bỏ các buckets khác.

Ngược lại:

~~~sql
EXPLAIN
SELECT *
FROM partition_lab.orders_hash
WHERE order_id = 1;
~~~

`order_id` không phải partition key, vì vậy một predicate chỉ có order_id thường **không prune theo customer_id**. Có thể phải kiểm tra nhiều partitions, dù mỗi partition có local index.

---

## 15. RANGE, LIST và HASH: ví dụ một giá trị thuộc đâu?

| Chiến lược | Khóa/bound | Giá trị thử | Định tuyến |
|---|---|---|---|
| RANGE tháng UTC | October `[Oct 1, Nov 1)` | `2026-10-31 23:59:59+00` | October |
| RANGE tháng UTC | November `[Nov 1, Dec 1)` | `2026-11-01 00:00:00+00` | November |
| RANGE | Không có partition cho Jan, có DEFAULT | `2027-01-05` | DEFAULT |
| RANGE | Không có DEFAULT, giá trị NULL | `NULL` | Không có partition |
| LIST | `IN ('north','northern')` | `'northern'` | North |
| LIST | `IN (NULL)` | `NULL` | Partition NULL |
| LIST | DEFAULT | `'west'` | DEFAULT |
| HASH | `MODULUS 4`/4 buckets | `customer_id=101` | Một bucket xác định theo hash, **không được đoán từ `101%4`** |
| HASH | Thiếu bucket nhận remainder | Key rơi vào remainder thiếu | INSERT lỗi không tìm được partition |

Các con số/key trong bảng là minh họa. Trạng thái partition thực phụ thuộc cấu trúc đã được tạo, dữ liệu và loại key.

---

## 16. Sơ đồ quyết định chọn chiến lược

~~~mermaid
flowchart TD
    A["Phân tích workload và vòng đời dữ liệu"] --> B{"Phần lớn query lọc gì?"}
    B -- "Khoảng thời gian hoặc giá trị có thứ tự" --> C["RANGE"]
    B -- "Một tập nhóm có ý nghĩa nghiệp vụ" --> D["LIST"]
    B -- "Equality trên key có nhiều distinct values" --> E["HASH"]
    B -- "Nhiều chiều độc lập" --> F["Cân nhắc subpartitioning"]
    C --> G{"Retention theo khoảng?"}
    G -- "Có" --> H["Chia theo ngày/tháng/tuần phù hợp"]
    G -- "Không" --> I["So với bảng thường + B-tree/BRIN"]
    D --> J{"Nhóm có skew và thay đổi thường?"}
    J -- "Có" --> K["Xem lại key, DEFAULT, hoặc subpartitioning"]
    J -- "Không" --> L["Phân vùng theo nhóm"]
    E --> M{"Có nhiều hot keys không?"}
    M -- "Có" --> N["HASH một key có thể lệch; đánh giá thiết kế khác"]
    M -- "Không" --> O["Bắt đầu số buckets hợp lý"]
    F --> P["Đo overhead số partitions và pruning"]
    H --> Q["Thiết kế PK/UNIQUE, index, automation"]
    I --> Q
    K --> Q
    L --> Q
    N --> Q
    O --> Q
    P --> Q
    Q --> R["EXPLAIN, benchmark, triển khai an toàn"]
~~~

**Không có lựa chọn mặc định tốt nhất cho mọi workload.** B-tree/BRIN trên một bảng không partition có thể đơn giản và hiệu quả hơn khi dữ liệu chưa lớn hoặc retention không đòi quản lý từng phân đoạn.

---

## 17. Quan sát cây partition và partition bounds từ catalog

Tạo xong partitions chưa có nghĩa mọi đối tượng đã attach đúng. Trước khi làm index/migration, kiểm tra cấu trúc thực tế.

### 17.1. pg_partition_tree

Trong các PostgreSQL versions hỗ trợ:

~~~sql
SELECT
    relid::regclass AS relation_name,
    parentrelid::regclass AS parent_name,
    isleaf,
    level
FROM pg_partition_tree('partition_lab.events'::regclass)
ORDER BY level, relation_name::text;
~~~

Thông tin gồm:

- `relid`: parent hoặc child trong cây.
- `parentrelid`: relation cha trực tiếp (NULL với root).
- `isleaf`: đã là leaf partition hay còn phân vùng tiếp.
- `level`: cấp độ tính từ root.

Khi không chắc một partition là leaf, `isleaf` giúp tránh áp giả định “mọi child trực tiếp đều chứa dữ liệu”.

### 17.2. pg_inherits và pg_get_expr

PostgreSQL sử dụng catalog về quan hệ parent-child để lưu cấu trúc partition.

~~~sql
SELECT
    child.oid::regclass AS partition_name,
    parent.oid::regclass AS parent_name,
    pg_get_expr(child.relpartbound, child.oid) AS partition_bound
FROM pg_inherits AS inh
JOIN pg_class AS child ON child.oid = inh.inhrelid
JOIN pg_class AS parent ON parent.oid = inh.inhparent
WHERE inh.inhparent = 'partition_lab.events'::regclass
ORDER BY partition_name::text;
~~~

`pg_get_expr(... relpartbound ...)` có thể hiển thị đại loại:

~~~text
FOR VALUES FROM ('2026-11-01 ...') TO ('2026-12-01 ...')
FOR VALUES DEFAULT
~~~

Không tự sửa `pg_class.relpartbound` hoặc `pg_inherits`: đây là catalog nội bộ phải được PostgreSQL quản lý qua DDL được hỗ trợ.

### 17.3. Kiểm tra parent key

~~~sql
SELECT
    partrelid::regclass AS parent_table,
    partstrat,
    partnatts,
    pg_get_partkeydef(partrelid) AS partition_key_definition
FROM pg_partitioned_table
WHERE partrelid IN (
    'partition_lab.events'::regclass,
    'partition_lab.support_tickets'::regclass,
    'partition_lab.orders_hash'::regclass
);
~~~

Giá trị chiến lược thường được biểu diễn:

| `partstrat` | Chiến lược |
|---|---|
| `r` | RANGE |
| `l` | LIST |
| `h` | HASH |

Sử dụng `pg_get_partkeydef` để xem định nghĩa key dễ đọc hơn thay vì suy ra từ tên bảng.

### 17.4. Đừng dựa vào hậu tố tên bảng để xác định routing

Một bảng tên `events_2026_11` có thể được tạo/attach với bound sai nếu DDL không đúng. **Metadata partition bound thực tế** mới quyết định định tuyến, không phải hậu tố tên child.

---

## 18. Chỉ mục trên bảng partitioned: parent và child khác nhau

### 18.1. Index parent là đối tượng logic

Trên declarative partitioned table:

~~~sql
CREATE INDEX idx_events_tenant_time
ON partition_lab.events (tenant_id, event_at DESC);
~~~

PostgreSQL tạo một **partitioned index** tương ứng ở parent và các index vật lý trên child partitions hiện có, theo khả năng của phiên bản và lệnh.

Mỗi leaf partition có **local index riêng**. Không có một B-tree vật lý duy nhất chứa mọi row thuộc tất cả partitions theo cách một global index hoạt động.

### 18.2. Index local hoạt động cùng pruning

Một query:

~~~sql
EXPLAIN
SELECT event_id, event_at, event_type
FROM partition_lab.events
WHERE tenant_id = 11
  AND event_at >= TIMESTAMPTZ '2026-11-01 00:00:00+00'
  AND event_at <  TIMESTAMPTZ '2026-12-01 00:00:00+00'
ORDER BY event_at DESC
LIMIT 20;
~~~

có thể:

1. **Prune** chỉ November.
2. Dùng local index trên `tenant_id, event_at DESC` trong November.
3. Trả top 20 theo thứ tự phù hợp (tùy plan/size/selectivity).

Hai cấp này khác nhau: pruning làm giảm số partitions cần xét; index làm giảm công việc **bên trong** partitions còn lại.

### 18.3. Index trên parent có áp cho partitions tạo về sau không?

Khi tạo/attach partition mới, PostgreSQL có cơ chế tạo hoặc gắn index con tương ứng với partitioned indexes trên parent theo quy tắc hiện hành. Vì vậy lập kế hoạch index ở parent thường thuận tiện hơn việc tự viết từng lệnh cho mọi child.

Tuy nhiên nếu bạn **attach bảng đã có dữ liệu** và index cần xây trên bảng lớn, quá trình tạo index phù hợp có thể kéo dài. Chuẩn bị index tương đương trước khi attach giúp kiểm soát thời điểm và khóa.

### 18.4. Tạo index riêng cho một partition

~~~sql
CREATE INDEX idx_events_nov_event_type
ON partition_lab.events_2026_11 (event_type);
~~~

Index này chỉ phục vụ `events_2026_11`, không tự tạo trên October/December. Phù hợp khi một partition có workload đặc biệt, nhưng cần ghi chú vận hành rõ để không quên partition mới.

### 18.5. Không tự tạo index mỗi child nếu đã có tương đương từ parent

Nếu parent đã tự tạo local index cho `tenant_id,event_at`, thêm một index child với cùng định nghĩa chỉ tăng disk/write amplification. Kiểm tra `pg_indexes` hoặc catalog trước khi triển khai.

---

## 19. CREATE INDEX CONCURRENTLY trên partitioned table

### 19.1. Vì sao cần cách triển khai riêng?

`CREATE INDEX CONCURRENTLY` giảm chặn ghi khi xây index trên một **bảng thường**, nhưng PostgreSQL không hỗ trợ trực tiếp nó trên **partitioned parent table** theo cách:

~~~sql
-- Không dùng: CREATE INDEX CONCURRENTLY trực tiếp trên parent.
CREATE INDEX CONCURRENTLY idx_parent_online
ON partition_lab.events (tenant_id, event_at);
~~~

Trong các phiên bản PostgreSQL hiện hành nơi giới hạn này áp dụng, lệnh bị từ chối; phải xây từng **leaf index** rồi attach index theo quy trình.

### 19.2. Mẫu tạo partitioned index ON ONLY

Một quy trình thường dùng trên bảng lớn:

~~~sql
-- Tạo định nghĩa index parent chưa gắn đủ các leaf indexes:
CREATE INDEX idx_events_tenant_at_online
ON ONLY partition_lab.events (tenant_id, event_at);
~~~

Sau đó xây index riêng ở những leaf partitions cần thiết:

~~~sql
-- Chạy độc lập từng lệnh, NGOÀI transaction block tường minh:
CREATE INDEX CONCURRENTLY idx_events_oct_tenant_at_online
ON partition_lab.events_2026_10 (tenant_id, event_at);

CREATE INDEX CONCURRENTLY idx_events_nov_tenant_at_online
ON partition_lab.events_2026_11 (tenant_id, event_at);

CREATE INDEX CONCURRENTLY idx_events_dec_tenant_at_online
ON partition_lab.events_2026_12 (tenant_id, event_at);

CREATE INDEX CONCURRENTLY idx_events_other_tenant_at_online
ON partition_lab.events_other (tenant_id, event_at);
~~~

Gắn các index đã xây đúng định nghĩa vào parent:

~~~sql
ALTER INDEX partition_lab.idx_events_tenant_at_online
    ATTACH PARTITION partition_lab.idx_events_oct_tenant_at_online;

ALTER INDEX partition_lab.idx_events_tenant_at_online
    ATTACH PARTITION partition_lab.idx_events_nov_tenant_at_online;

ALTER INDEX partition_lab.idx_events_tenant_at_online
    ATTACH PARTITION partition_lab.idx_events_dec_tenant_at_online;

ALTER INDEX partition_lab.idx_events_tenant_at_online
    ATTACH PARTITION partition_lab.idx_events_other_tenant_at_online;
~~~

Khi **tất cả** partitions hiện có có index tương thích và được attach đúng, parent partitioned index mới có thể chuyển sang trạng thái valid.

Đây là mẫu triển khai mang tính **quy trình**: trước khi chạy thực, kiểm tra index parent chưa tồn tại, tất cả child/DEFAULT hiện có, định nghĩa index khớp hoàn toàn, giới hạn công cụ migration và lock availability.

### 19.3. Vì sao không dùng BEGIN cho concurrent index build?

`CREATE INDEX CONCURRENTLY` cần nhiều giai đoạn và **không được chạy trong transaction block tường minh**. Một số công cụ migration mặc định bọc cả file migration trong một transaction; phải tách các bước nontransactional cho đúng.

### 19.4. Nếu một child index build thất bại

Index trên child có thể ở trạng thái `INVALID`. Không thể coi parent index sẵn sàng khi thiếu child hợp lệ.

Kiểm tra:

~~~sql
SELECT
    idx.relname AS index_name,
    tbl.relname AS table_name,
    ix.indisvalid,
    ix.indisready,
    pg_get_indexdef(ix.indexrelid) AS definition
FROM pg_index AS ix
JOIN pg_class AS idx ON idx.oid = ix.indexrelid
JOIN pg_class AS tbl ON tbl.oid = ix.indrelid
JOIN pg_namespace AS ns ON ns.oid = tbl.relnamespace
WHERE ns.nspname = 'partition_lab'
  AND tbl.relname LIKE 'events%'
ORDER BY table_name, index_name;
~~~

Lỗi cần xử lý theo nguyên nhân gốc trước khi retry. `IF NOT EXISTS` không chứng minh một index cùng tên đã valid hoặc đúng định nghĩa.

### 19.5. Đây không phải cách tạo global index

Việc attach tất cả child indexes vào một parent partitioned index là **tập hợp logical indexes**. Nó không tạo global B-tree xuyên suốt mọi partitions và không xóa giới hạn UNIQUE/PRIMARY KEY của parent.

---

## 20. Khóa chính và UNIQUE trên bảng partitioned

### 20.1. Vì sao PRIMARY KEY(event_id) không hợp lệ với RANGE(event_at)?

Hãy xem:

~~~sql
CREATE TABLE partition_lab.invalid_event_pk (
    event_id BIGINT PRIMARY KEY,
    event_at TIMESTAMPTZ NOT NULL
)
PARTITION BY RANGE (event_at);
~~~

Trong PostgreSQL hiện đại, định nghĩa này **không hợp lệ** vì khóa chính trên partitioned parent phải bao gồm **mọi cột partition key**. Nếu không, hai partitions riêng có thể cùng chứa `event_id=123` nhưng local unique indexes không phối hợp để cấm duplicate toàn cục.

**Đây là ví dụ lỗi dự kiến**: không chạy như bước tạo dữ liệu tiếp theo.

### 20.2. Khóa hợp lệ khi key là cột trực tiếp

Ví dụ `events` đã tạo:

~~~sql
PRIMARY KEY (event_at, event_id)
~~~

Khóa có chứa `event_at` nên có thể được thực thi bằng unique indexes ở các partitions tương ứng.

Nhưng cần hiểu chính xác: nó bảo đảm **cặp (event_at,event_id)** unique. Nó **không bảo đảm một event_id không xuất hiện hai lần với event_at khác nhau**.

### 20.3. UNIQUE và PRIMARY KEY trên parent có điều kiện

Với declarative partitioning, các ràng buộc UNIQUE/PRIMARY KEY trên parent phải bao gồm **toàn bộ partition key columns**, và partition key tương ứng **không dùng biểu thức/function calls** nếu muốn tạo loại constraint đó trên parent.

Ví dụ có thể hợp lệ trên LIST(region):

~~~sql
CREATE TABLE partition_lab.region_memberships (
    member_id BIGINT NOT NULL,
    region TEXT NOT NULL,
    PRIMARY KEY (region, member_id)
)
PARTITION BY LIST (region);
~~~

Không thể chỉ khai báo `PRIMARY KEY(member_id)` trên parent rồi mong PostgreSQL tạo một global unique index xuyên partitions.

### 20.4. Biểu thức partition key và unique constraints

Ví dụ:

~~~sql
-- Ví dụ hợp lệ về tạo bảng (chưa có PK trên parent):
CREATE TABLE partition_lab.regions_normalized (
    id BIGINT NOT NULL,
    region TEXT NOT NULL
)
PARTITION BY LIST ((lower(region)));
~~~

Một UNIQUE/PRIMARY KEY trên partitioned parent có partition key biểu thức bị ràng buộc bởi giới hạn liên quan operator/cột của PostgreSQL; không giả định có thể tạo một parent PK đơn giản trên `id`.

Nếu ứng dụng cần global uniqueness độc lập partition key, cân nhắc:

- Thiết kế lại partition key hoặc khóa nghiệp vụ.
- Dùng nguồn sinh ID toàn cục và đảm bảo ứng dụng không cấp trùng, hiểu rằng sequence **chỉ cấp số** chứ không tự tạo global UNIQUE constraint ở parent.
- Bảng registry nhỏ không phân vùng giữ khóa unique, phối hợp transaction khi ghi.
- Cơ chế dữ liệu khác nếu cần invariant toàn cục rất chặt.

### 20.5. Vì sao UNIQUE cục bộ chưa đủ?

Hai partitions có hai index riêng. Mỗi index chỉ nhìn những rows của partition đó. Không có global index duy nhất để đối chiếu `event_id` trên mọi partitions.

Thiết kế API tránh coi “PRIMARY KEY (event_at,event_id)” là tương đương “event_id duy nhất toàn bảng”, và tránh query/chỉ định khóa một phần khi nghiệp vụ đòi định danh một event duy nhất.

### 20.6. NULL và UNIQUE

SQL UNIQUE truyền thống có semantics NULL khác equality thông thường; PostgreSQL phiên bản mới có tùy chọn `NULLS NOT DISTINCT` cho UNIQUE theo hỗ trợ của phiên bản. Nhưng điều đó **không vượt qua** yêu cầu constraint parent phải bao gồm partition key. Không dùng NULL semantics để né giới hạn unique xuyên partitions.

---

## 21. FOREIGN KEY và ràng buộc toàn vẹn

### 21.1. Foreign key với partitioned table

PostgreSQL hiện đại hỗ trợ FOREIGN KEY trong nhiều kịch bản liên quan partitioned tables, cả quan hệ tham chiếu và được tham chiếu theo điều kiện của schema/phiên bản. Nhưng khi bảng đích có parent PK gồm partition key, FK phải tham chiếu **một key được bảo đảm unique phù hợp**.

Ví dụ nếu bảng dimension có khóa thường:

~~~sql
CREATE TABLE partition_lab.tenants (
    tenant_id INTEGER PRIMARY KEY,
    tenant_name TEXT NOT NULL
);

INSERT INTO partition_lab.tenants(tenant_id, tenant_name)
VALUES (11, 'Alpha'), (12, 'Beta'), (13, 'Gamma');
~~~

Có thể thêm FK từ `events.tenant_id`:

~~~sql
ALTER TABLE partition_lab.events
ADD CONSTRAINT fk_events_tenant
FOREIGN KEY (tenant_id)
REFERENCES partition_lab.tenants(tenant_id);
~~~

Trên dataset lab, 11,12,13 đã có nên FK hợp lệ. Trên production, việc thêm FK có thể cần validate/scan và lock trên bảng con/cha; nên dùng quy trình migration phù hợp.

### 21.2. Không mặc định FK tham chiếu event_id đơn lẻ

Với `events` có PK `(event_at,event_id)`, một bảng khác muốn FK chỉ theo `event_id` **không có unique target** trên parent. Nó cần lưu đủ khóa composite, hoặc mô hình registry/ID khác.

### 21.3. CHECK và NOT NULL

Partitions thừa hưởng những ràng buộc tương thích từ parent theo semantics của declarative partitioning. Có thể dùng CHECK để tăng invariant dữ liệu, nhưng **partition bounds đã là quy tắc routing**; không tự định nghĩa CHECK xung đột với bound hoặc đặt một constraint trên child mà ứng dụng không biết.

### 21.4. Exclusion constraints và global uniqueness

Exclusion constraints trên dữ liệu partitioned có giới hạn theo phạm vi index/partition và phiên bản. Không giả định một exclusion constraint ở từng child tự chống chồng lấn **giữa hai child** khi predicate nghiệp vụ có thể giao nhau xuyên bounds. Nếu cần điều kiện toàn cục, thiết kế partition key và phạm vi constraint sao cho những bản ghi có khả năng xung đột luôn nằm cùng partition, hoặc dùng cơ chế điều phối/thiết kế dữ liệu khác.

---

## 22. INSERT: routing hoạt động ở đâu?

### 22.1. Ghi qua parent

~~~sql
INSERT INTO partition_lab.events
    (event_id, event_at, tenant_id, event_type)
VALUES
    (2001, '2026-11-20 03:00:00+00', 11, 'click');
~~~

PostgreSQL tra partition key và định tuyến hàng vào `events_2026_11`.

### 22.2. Ghi thẳng vào một child

~~~sql
INSERT INTO partition_lab.events_2026_11
    (event_id, event_at, tenant_id, event_type)
VALUES
    (2002, '2026-11-21 04:00:00+00', 12, 'view');
~~~

Lệnh ghi trực tiếp child được phép khi có quyền phù hợp, nhưng row vẫn phải thỏa **partition constraint**. Cố chèn timestamp January vào child November sẽ báo lỗi, không tự được định tuyến sang DEFAULT.

Trong ứng dụng, ưu tiên ghi qua parent để tránh coupling với tên child.

### 22.3. Không có partition nhận dữ liệu

Nếu parent RANGE không có DEFAULT và không có partition chứa event_at, INSERT báo lỗi về partition không tìm thấy. PostgreSQL **không tự tạo partition theo tên tháng**.

### 22.4. INSERT ... SELECT, COPY và batch ingestion

Ghi số lượng lớn qua parent vẫn cần routing từng row theo partition key. Chi phí có thể tăng khi có quá nhiều partitions hoặc mỗi row phải xử lý constraint/index ở child.

Nếu ứng dụng ingest nhiều sự kiện cùng tháng, có thể tạo batch theo thời gian để giảm overhead client/transaction, nhưng cần test lock, WAL, trigger và recovery. Không chuyển thẳng sang child để “tăng tốc” nếu có nguy cơ làm sai routing/mất đồng bộ schema.

### 22.5. ON CONFLICT trên bảng partitioned

PostgreSQL hỗ trợ `INSERT ... ON CONFLICT` theo ràng buộc UNIQUE/PK phù hợp. Nhưng conflict detection chỉ dựa vào những **unique constraints/indexes thực sự được khai báo và hỗ trợ**.

Ví dụ composite key:

~~~sql
INSERT INTO partition_lab.events
    (event_id, event_at, tenant_id, event_type)
VALUES
    (1002, '2026-11-01 00:00:00+00', 11, 'login')
ON CONFLICT (event_at, event_id)
DO NOTHING;
~~~

Mẫu này tránh duplicate **cặp** key, không cấm event_id trùng tại event_at khác.

### 22.6. ON CONFLICT DO UPDATE không phải cơ chế chuyển partition tự do

Trong nhiều PostgreSQL versions, `ON CONFLICT DO UPDATE` **không được hỗ trợ cho trường hợp phải thay đổi partition key khiến row xung đột chuyển sang partition khác**. Không dùng UPSERT để đổi `event_at` từ November sang December một cách tùy ý; đánh giá cú pháp hỗ trợ và transaction/update semantics cụ thể.

---

## 23. UPDATE partition key: row có thể được chuyển partition

### 23.1. Khi partition key thay đổi

Ví dụ một sự kiện bị sửa lại thời gian từ tháng 11 sang tháng 12:

~~~sql
BEGIN;

UPDATE partition_lab.events
SET event_at = TIMESTAMPTZ '2026-12-02 10:00:00+00'
WHERE event_id = 1003
  AND event_at = TIMESTAMPTZ '2026-11-15 08:30:00+00';

SELECT
    event_id, event_at, tableoid::regclass AS partition_name
FROM partition_lab.events
WHERE event_id = 1003;

ROLLBACK;
~~~

PostgreSQL có thể thực hiện **row movement** từ November sang December theo mô hình delete+insert nội bộ khi UPDATE partition key.

Vì ví dụ có ROLLBACK, dữ liệu lab ban đầu được giữ nguyên.

### 23.2. Row movement có chi phí và cạnh tranh

- Thay đổi index/constraint ở partition nguồn và đích.
- Có thể phát sinh WAL và dead tuples.
- Trigger, FKs và row locking có các quy tắc cần hiểu.
- Trong tương tác đồng thời, có thể xuất hiện serialization failure (`SQLSTATE 40001`) hoặc conflict khác, tùy mức cô lập và loại thao tác.
- Nếu partition đích không tồn tại, UPDATE có thể báo lỗi, không tự tạo partition.

### 23.3. Không chọn partition key biến động liên tục nếu không cần

Ví dụ LIST theo `status` (new → processing → paid) có thể khiến mỗi thay đổi trạng thái gây row movement, thay vì update trong cùng heap. Nếu workload có hàng triệu status changes mỗi giờ, cần cân nhắc partition key ổn định hơn.

### 23.4. DELETE trên parent

~~~sql
DELETE FROM partition_lab.events
WHERE event_at >= TIMESTAMPTZ '2026-10-01 00:00:00+00'
  AND event_at <  TIMESTAMPTZ '2026-11-01 00:00:00+00';
~~~

Có thể prune và tác động October, nhưng vẫn là **DELETE từng hàng** với WAL/dead tuples/VACUUM. Nếu mục tiêu là xóa **toàn bộ** partition cũ theo retention, DETACH/DROP partition có thể phù hợp hơn, với quy trình riêng về khóa, backup, FKs và an toàn dữ liệu.

**Đừng chạy DELETE này trên lab nếu muốn giữ các row October cho bài tập sau**; đây là ví dụ nghiệp vụ.

---

## 24. Partition pruning: compile-time và execution-time

### 24.1. Compile-time pruning

Khi query có điều kiện hằng:

~~~sql
EXPLAIN
SELECT COUNT(*)
FROM partition_lab.events
WHERE event_at >= TIMESTAMPTZ '2026-11-01 00:00:00+00'
  AND event_at <  TIMESTAMPTZ '2026-12-01 00:00:00+00';
~~~

Planner có thể xác định những partitions không thể có row ngay **lúc lập kế hoạch**.

### 24.2. Execution-time pruning

Truy vấn tham số hóa:

~~~sql
PREPARE count_events_in_range(timestamptz, timestamptz) AS
SELECT COUNT(*)
FROM partition_lab.events
WHERE event_at >= $1
  AND event_at <  $2;

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE count_events_in_range(
    '2026-11-01 00:00:00+00',
    '2026-12-01 00:00:00+00'
);

DEALLOCATE count_events_in_range;
~~~

Khi planner chưa biết giá trị cụ thể ở lập kế hoạch (ví dụ generic plan), PostgreSQL có thể prune partitions trong **giai đoạn khởi tạo/thực thi** theo tham số, với các biểu hiện `Subplans Removed`, `never executed` hoặc số loops ở child.

### 24.3. enable_partition_pruning

~~~sql
SHOW enable_partition_pruning;
~~~

Thông thường nên để hệ thống pruning khi hợp lý. Trong session lab, có thể thử:

~~~sql
BEGIN;
SET LOCAL enable_partition_pruning = off;

EXPLAIN
SELECT COUNT(*)
FROM partition_lab.events
WHERE event_at >= TIMESTAMPTZ '2026-11-01 00:00:00+00'
  AND event_at <  TIMESTAMPTZ '2026-12-01 00:00:00+00';

ROLLBACK;
~~~

Tắt pruning **chỉ để quan sát sự khác biệt** trong lab; không phải cách tối ưu production.

### 24.4. Pruning có cần index không?

Không. Pruning dùng **partition bounds**, không yêu cầu index trên partition key. Kể cả partition không có index, PostgreSQL vẫn có thể loại các child không liên quan.

Index được xét **sau đó** trên các child còn lại để truy vấn hiệu quả hơn.

### 24.5. Pruning phụ thuộc toán tử và biểu thức

Điều kiện dùng partition key với toán tử phù hợp, cast đúng, dữ liệu hằng/parameter có thể giúp pruning. Những phép biến đổi tùy ý trên key không được planner tự nghịch đảo trong mọi trường hợp.

Ví dụ với parent RANGE(event_at):

~~~sql
-- Hình thức thường thuận lợi:
WHERE event_at >= TIMESTAMPTZ '2026-11-01 00:00+00'
  AND event_at < TIMESTAMPTZ '2026-12-01 00:00+00'
~~~

khác với:

~~~sql
-- Có thể hạn chế pruning, phải EXPLAIN:
WHERE EXTRACT(MONTH FROM event_at) = 11
~~~

Dòng thứ hai còn chứa **mọi năm**, không đồng nghĩa chỉ November 2026.

### 24.6. Parameterized joins và pruning

Khi join một bảng khác cho biết một giá trị partition key, PostgreSQL có thể dùng execution-time pruning bên trong parameterized plans ở trường hợp hỗ trợ. Nhưng không phải mọi join/filter đều tạo được runtime pruning; kiểm tra `EXPLAIN (ANALYZE, BUFFERS)` với workload cụ thể.

---

## 25. Khi nào pruning không đủ để query nhanh?

### 25.1. Một partition còn quá lớn

Nếu bạn chia logs theo **năm**, query một giờ mới nhất vẫn chỉ prune còn **một partition năm** chứa hàng trăm triệu rows. Cần local index phù hợp hoặc phân vùng theo tháng/ngày dựa workload.

### 25.2. Query thiếu partition key

~~~sql
SELECT *
FROM partition_lab.events
WHERE tenant_id = 11;
~~~

Parent partition theo thời gian, query chỉ lọc tenant, nên có thể phải xét mọi partition. Giải pháp có thể là thêm local index tenant/time, bổ sung điều kiện thời gian hợp lệ hoặc cân nhắc hai tầng phân vùng. Không thêm mốc thời gian giả tạo nếu yêu cầu thực sự cần **mọi lịch sử**.

### 25.3. COUNT(*) không có filter

~~~sql
SELECT COUNT(*) FROM partition_lab.events;
~~~

Phải tổng hợp trên các partitions liên quan. Partitioning không tạo một bộ đếm row chính xác tự động có thể trả không cần scan.

### 25.4. ORDER BY / LIMIT trên nhiều partitions

~~~sql
SELECT event_id, event_at
FROM partition_lab.events
ORDER BY event_at DESC
LIMIT 20;
~~~

Có thể dùng local indexes và MergeAppend/Limit hoặc phải xử lý nhiều partitions tùy plan. Không mặc định PostgreSQL biết “chỉ partition tháng mới nhất có dữ liệu cần đọc” nếu query không có điều kiện ràng buộc và một số partitions khác có thể chứa hàng cạnh tranh.

### 25.5. Quá nhiều partitions

Vài nghìn hoặc hàng chục nghìn partitions có thể tăng:

- Thời gian planning hoặc metadata/catalog work.
- Bộ nhớ cho kế hoạch.
- Số relations/indexes được mở và khóa.
- Chi phí maintenance, backup, monitor và schema migrations.
- Khả năng lock exhaustion khi một transaction đụng nhiều objects.

Không suy ra “thêm partitions = tuyến tính nhanh hơn”. Chọn granularity bằng **dung lượng mỗi partition, retention và filter patterns**.

---

## 26. Phân vùng nhiều tầng (subpartitioning)

Có thể chia theo thời gian trước, rồi theo tenant/hash.

### 26.1. Tạo parent RANGE theo ngày

~~~sql
CREATE TABLE partition_lab.multilevel_events (
    event_id BIGINT NOT NULL,
    event_at DATE NOT NULL,
    tenant_id INTEGER NOT NULL,
    payload TEXT
)
PARTITION BY RANGE (event_at);
~~~

### 26.2. Child tháng lại là partitioned table HASH

~~~sql
CREATE TABLE partition_lab.multilevel_events_2026_11
PARTITION OF partition_lab.multilevel_events
FOR VALUES FROM ('2026-11-01') TO ('2026-12-01')
PARTITION BY HASH (tenant_id);
~~~

Đây là child của parent theo RANGE **và cũng là parent cấp hai** của các HASH partitions.

### 26.3. Tạo hai leaf HASH partitions

~~~sql
CREATE TABLE partition_lab.multilevel_events_2026_11_h0
PARTITION OF partition_lab.multilevel_events_2026_11
FOR VALUES WITH (MODULUS 2, REMAINDER 0);

CREATE TABLE partition_lab.multilevel_events_2026_11_h1
PARTITION OF partition_lab.multilevel_events_2026_11
FOR VALUES WITH (MODULUS 2, REMAINDER 1);
~~~

### 26.4. Nạp và quan sát

~~~sql
INSERT INTO partition_lab.multilevel_events
    (event_id, event_at, tenant_id, payload)
VALUES
    (1, DATE '2026-11-05', 101, 'A'),
    (2, DATE '2026-11-20', 102, 'B'),
    (3, DATE '2026-11-21', 103, 'C');

SELECT
    event_id, event_at, tenant_id,
    tableoid::regclass AS leaf_partition
FROM partition_lab.multilevel_events
ORDER BY event_id;
~~~

Mỗi row đi qua quy tắc RANGE rồi HASH, cuối cùng nằm trong một leaf.

### 26.5. Query có cả hai keys

~~~sql
EXPLAIN
SELECT *
FROM partition_lab.multilevel_events
WHERE event_at >= DATE '2026-11-01'
  AND event_at <  DATE '2026-12-01'
  AND tenant_id = 101;
~~~

Planner có thể prune ở cả hai tầng nếu đủ điều kiện.

### 26.6. Cẩn trọng với lượng leaf partitions

12 tháng × 32 HASH buckets = **384 leaf partitions/năm**. Nếu giữ 5 năm là 1.920 leaf partitions, chưa kể partitioned parents và indexes. Thiết kế nhiều tầng phải cân nhắc tổng object count/lock overhead và lịch tạo child, không chỉ lợi ích pruning lý thuyết.

### 26.7. Không giả định mọi tổ hợp hai chiều đều có partitions

Ở lab chỉ có tháng 11/2026. Chèn row tháng 12 không có partition cấp 1 phù hợp sẽ lỗi, dù tháng 11 đã có đủ HASH buckets. Từng cấp phải có **bounds đầy đủ** cho miền dữ liệu cần nhận.

---

## 27. Partition-wise join và partition-wise aggregate

### 27.1. Tư tưởng partition-wise join

Nếu hai bảng được phân vùng tương thích trên **join key** và join condition có đủ điều kiện tương ứng, planner có thể thực hiện các joins **giữa partitions tương ứng** rồi kết hợp kết quả, thay vì materialize toàn bộ hai bảng trước khi join.

~~~text
orders_h0  JOIN items_h0 ─┐
orders_h1  JOIN items_h1 ─┼─> Append/merge kết quả
orders_h2  JOIN items_h2 ─┤
orders_h3  JOIN items_h3 ─┘
~~~

Đây là mô hình ý tưởng. Để có kế hoạch hợp lệ, hai bên phải đáp ứng các yêu cầu về strategy/keys, data types, join condition và cấu trúc partition; không phải cứ hai bảng đều có 4 partitions là tự ghép h0-h0.

### 27.2. enable_partitionwise_join

~~~sql
SHOW enable_partitionwise_join;
~~~

Trong PostgreSQL hiện đại, tham số này thường **mặc định off**. Khi phù hợp, có thể thử trong session lab:

~~~sql
BEGIN;
SET LOCAL enable_partitionwise_join = on;

EXPLAIN
SELECT *
FROM partition_lab.orders_hash AS o
JOIN partition_lab.orders_hash AS p
  ON p.customer_id = o.customer_id
WHERE o.customer_id = 101;

ROLLBACK;
~~~

Query self-join này **chỉ nhằm xem plan**; nếu executed không kiểm soát có thể tạo nhiều rows do cùng customer có nhiều orders. Không coi ví dụ là workload production.

### 27.3. enable_partitionwise_aggregate

~~~sql
SHOW enable_partitionwise_aggregate;
~~~

Tùy query và partition keys, PostgreSQL có thể thực hiện một phần aggregation ở từng partition trước khi tổng hợp toàn cục. Nhưng một query:

~~~sql
SELECT tenant_id, COUNT(*)
FROM partition_lab.events
GROUP BY tenant_id;
~~~

trên RANGE(event_at) không bảo đảm rằng mỗi tenant chỉ nằm ở một partition; có thể cần bước tổng hợp kết quả của nhiều partitions. Đọc plan để biết aggregation được partition-wise ở mức nào.

### 27.4. Không bật mọi tối ưu partition-wise toàn server theo quán tính

Partition-wise join/aggregate có thể tăng số nodes và chi phí planning/memory, nhất là khi nhiều partitions. Thử trên workload thật và so `Planning Time`, `Execution Time`, buffers và memory trước khi thay đổi cấu hình.

---

## 28. Giới hạn UNIQUE khi subpartitioning

Nếu parent phân vùng RANGE(event_at), child tháng phân vùng HASH(tenant_id), một khóa duy nhất muốn bảo đảm **toàn cây** có thể cần bao gồm **các partition keys ở những tầng liên quan** theo các quy tắc và đối tượng constraint. Không giả định `PRIMARY KEY(event_at,event_id)` đã đầy đủ nếu leaf tiếp tục chia HASH(tenant_id) mà constraint ở cấp sâu không thể được thực thi hợp lệ.

Đối với ví dụ `multilevel_events`, chưa khai báo PK để tránh hiểu sai rằng mỗi level đều tự có global unique index.

Khi thiết kế thực:

1. Liệt kê **tất cả partition key columns** ở root và các tầng.
2. Xác định khóa nghiệp vụ phải unique trên phạm vi nào.
3. Kiểm tra giới hạn UNIQUE/PK của parent và từng partitioned child theo phiên bản.
4. Dùng constraint hợp lệ hoặc thay đổi cách phân vùng/mô hình dữ liệu nếu không thể bảo đảm invariant.

Đây là lý do subpartitioning cần được cân nhắc cùng **schema và các ràng buộc**, không chỉ cùng truy vấn SELECT.

---

## 29. Quản lý vòng đời RANGE: tạo partition trước khi dữ liệu tới

### 29.1. Vì sao cần tạo trước?

Với hệ thống sự kiện liên tục, đến ngày đầu tháng mới mà partition chưa tồn tại có thể dẫn đến:

- INSERT **thất bại** nếu không có DEFAULT.
- INSERT vẫn chạy nhưng dồn vào DEFAULT quá lớn nếu có.
- Truy vấn/backup/retention mất tính quy luật.
- Khi bổ sung partition mới, việc kiểm tra DEFAULT chứa dữ liệu trong bound mới gây lỗi hoặc đòi di chuyển dữ liệu khó.

Vì vậy cần lịch **pre-create partitions** trước thời điểm chúng có thể nhận dữ liệu.

### 29.2. Tạo tháng mới

Ví dụ tạo February 2027, không trùng ba tháng đã có:

~~~sql
CREATE TABLE partition_lab.events_2027_02
PARTITION OF partition_lab.events
FOR VALUES FROM ('2027-02-01 00:00:00+00')
           TO   ('2027-03-01 00:00:00+00');
~~~

Lệnh trên có thể phải kiểm tra DEFAULT partition để bảo đảm không có row thuộc February trước khi gán bound mới. Trong dữ liệu lab chỉ có January 2027 ở DEFAULT nên không có February; tuy nhiên trên production, **đừng giả định DEFAULT trống**.

### 29.3. Tự động tạo partition định kỳ

Một quy trình vận hành có thể:

1. Xác định ngày/giờ và timezone của partition boundaries.
2. Tính các partitions sẽ cần cho vài kỳ tương lai.
3. Kiểm tra metadata hiện tại để tránh lệnh trùng.
4. Tạo/attach những partitions thiếu.
5. Xác minh bound, index, constraint và tablespace.
6. Giám sát DEFAULT hoặc lỗi routing.
7. Ghi nhận những partition có hạn retention sắp đến.

Tự động hóa phải **idempotent**, quản lý cạnh tranh (không có hai job cùng tạo một partition), biết xử lý lỗi và không tự DROP dữ liệu theo biến ngày tính sai.

### 29.4. Backfill dữ liệu cũ cần partition nào?

Nếu ứng dụng có thể nạp dữ liệu lịch sử năm 2025, chỉ tạo partitions tháng tương lai là chưa đủ. Bạn cần phạm vi backfill hoặc DEFAULT phù hợp, nhưng DEFAULT không thay thế kế hoạch partition lịch sử.

### 29.5. Tần suất chia theo ngày, tuần, tháng hay năm?

| Granularity | Thường hợp lý khi | Rủi ro |
|---|---|---|
| Theo giờ | Lưu lượng cực lớn, dữ liệu hot rất ngắn | Object count/maintenance khổng lồ |
| Theo ngày | Khối lượng mỗi ngày lớn, cần retention theo ngày | Nhiều partitions sau vài năm |
| Theo tháng | Volume vừa/lớn và retention theo tháng | Partition tháng hiện tại có thể vẫn quá lớn |
| Theo năm | Dataset nhỏ hơn hoặc lịch sử ít query | Partition lớn, pruning yếu cho query vài ngày |

Không dùng một mốc row count cố định cho mọi workload. Cần đo số pages/index size/queries và khả năng quản trị thực tế.

---

## 30. ATTACH PARTITION: biến bảng có sẵn thành child

### 30.1. Vì sao ATTACH hữu ích?

Đôi khi dữ liệu đã được nạp vào **một bảng thường** bằng batch, hoặc bạn muốn xây index/kiểm tra dữ liệu trước khi đưa nó vào parent. `ATTACH PARTITION` gắn relation hiện có làm child với bound xác định.

### 30.2. Tạo bảng standalone cùng cấu trúc

~~~sql
CREATE TABLE partition_lab.events_2027_03
(LIKE partition_lab.events INCLUDING DEFAULTS INCLUDING CONSTRAINTS);
~~~

`LIKE` sao chép những thuộc tính theo option đã yêu cầu. Nó không đảm bảo sao chép **tất cả** index/triggers/identity/permissions/thuộc tính đặc biệt của parent theo mọi phiên bản. Khi attach, PostgreSQL kiểm tra điều kiện schema/constraints và thực hiện cơ chế index/constraint tương ứng. Phải xem catalog thực tế.

### 30.3. Kiểm tra dữ liệu phù hợp bound

Một constraint hợp lệ trên standalone table có thể chứng minh nó chỉ chứa rows trong tháng March 2027:

~~~sql
ALTER TABLE partition_lab.events_2027_03
ADD CONSTRAINT chk_events_2027_03_bound
CHECK (
    event_at >= TIMESTAMPTZ '2027-03-01 00:00:00+00'
    AND
    event_at < TIMESTAMPTZ '2027-04-01 00:00:00+00'
);
~~~

Khi CHECK **đã được validate** và đúng hình thức PostgreSQL có thể sử dụng làm bằng chứng, quá trình attach có thể tránh quét lại toàn bảng standalone chỉ để xác minh bound. Nếu CHECK không tồn tại hoặc không đủ chứng minh, PostgreSQL phải xác minh rows và scan có thể đắt.

### 30.4. Gắn bảng vào parent

~~~sql
ALTER TABLE partition_lab.events
ATTACH PARTITION partition_lab.events_2027_03
FOR VALUES FROM ('2027-03-01 00:00:00+00')
           TO   ('2027-04-01 00:00:00+00');
~~~

Một bảng đã attach không còn là một bảng độc lập tùy ý; nó là child tuân theo bounds và metadata của parent.

### 30.5. Khóa khi ATTACH

Theo quy tắc PostgreSQL hiện đại, `ATTACH PARTITION` thường lấy **SHARE UPDATE EXCLUSIVE** trên parent và **ACCESS EXCLUSIVE** trên bảng cần attach. Nếu parent có DEFAULT, hệ thống có thể cần kiểm tra DEFAULT bằng lock mạnh, trừ khi có bằng chứng constraint thích hợp chứng minh không chứa rows thuộc bound mới.

Vì vậy “ATTACH chỉ đổi metadata” **không có nghĩa** nó không có lock hoặc scan. Với bảng lớn, pre-validate CHECK và lập lịch lúc traffic phù hợp.

### 30.6. DEFAULT có thể cản trở ATTACH

Giả sử `events_other` chứa dữ liệu March 2027. Khi bạn muốn attach `events_2027_03`, DEFAULT **không thể tiếp tục chứa rows thuộc miền của partition mới**. PostgreSQL có thể từ chối attach khi tìm thấy dữ liệu chồng lấn.

Bạn phải thiết kế một đợt di chuyển:

- Ngăn ghi mới vào miền cần chuyển trong khi duy trì đúng transaction semantics, hoặc dùng chiến lược dual-write/cutover được thiết kế riêng.
- Tạo standalone table và index/constraints phù hợp.
- Di chuyển đủ rows từ DEFAULT sang standalone, xác minh số lượng và dữ liệu.
- Loại rows tương ứng khỏi DEFAULT khi đã lưu an toàn.
- ATTACH bảng mới khi DEFAULT không còn rows thuộc miền đó.
- Mở ghi lại và xác minh query parent.

Không chỉ chạy `DELETE FROM events_other WHERE event_at ...` rồi “hy vọng” dữ liệu đã tồn tại ở nơi khác. Trên bảng lớn cần batch và kế hoạch tránh giai đoạn một phần dữ liệu không visible từ parent.

### 30.7. CHECK loại trừ trên DEFAULT để tránh scan

Có thể dùng một CHECK **đã validate** trên DEFAULT để chứng minh nó không chứa giá trị của bound mới, ví dụ một constraint tương đương phủ định khoảng March:

~~~sql
ALTER TABLE partition_lab.events_other
ADD CONSTRAINT chk_events_other_not_march_2027
CHECK (
    event_at < TIMESTAMPTZ '2027-03-01 00:00:00+00'
    OR
    event_at >= TIMESTAMPTZ '2027-04-01 00:00:00+00'
);
~~~

Đây là ví dụ khi DEFAULT **không có** dữ liệu March; nếu có, câu ADD CHECK sẽ thất bại khi validate. PostgreSQL có thể dùng bằng chứng này để tránh một số scan khi attach. Nhưng thêm/validate CHECK bản thân có chi phí lock/scan riêng, nên vẫn cần kế hoạch thực hiện.

**Chú ý:** trong lab ở phần 30.4, nếu bạn đã attach March rồi, không nên chạy lại ADD CHECK này như một bước bắt buộc; đó là kỹ thuật **chuẩn bị trước ATTACH**, không phải thao tác thêm ngẫu nhiên sau khi attach.

---

## 31. DEFAULT partition: nên có hay không?

### 31.1. Có DEFAULT

Ưu điểm:

- Giảm lỗi INSERT khi phát sinh tháng/nhóm ngoài dự kiến.
- Dùng như vùng tiếp nhận tạm thời cho dữ liệu lệch lịch.
- Cho phép truy vấn parent vẫn nhìn thấy dữ liệu không thuộc các bounds đã đặt tên.

Nhược điểm:

- Có thể che giấu job pre-create partition bị lỗi.
- Dữ liệu tích tụ khiến DEFAULT rất lớn.
- ATTACH partition mới phải đảm bảo DEFAULT không chứa row chồng miền, đôi khi gây scan/lock.
- Query pruning phải xét DEFAULT khi không có đủ thông tin để loại nó.

### 31.2. Không có DEFAULT

Ưu điểm:

- Dữ liệu không hợp phạm vi phát hiện **ngay khi INSERT**.
- Buộc pipeline tạo partition sẵn và xử lý lịch ingest.

Nhược điểm:

- Một job pre-create bị lỗi có thể làm ingestion ngừng.
- Backfill dữ liệu bất thường cần kế hoạch partition riêng.

### 31.3. Quyết định theo yêu cầu vận hành

Nếu hệ thống thanh toán không chấp nhận event đi sai tháng mà không được phát hiện, **fail-fast** có thể tốt hơn DEFAULT. Nếu hệ thống logs cần tiếp tục ingest với giới hạn rủi ro, DEFAULT kèm cảnh báo/retention riêng có thể phù hợp.

Dù chọn cách nào, cần có monitoring:

~~~sql
SELECT COUNT(*) AS unexpected_rows
FROM partition_lab.events_other;
~~~

Cảnh báo khi DEFAULT có rows ngoài các quy tắc chấp nhận, không chỉ khi database đã báo lỗi.

### 31.4. DEFAULT không phải “catch-all” cho HASH

HASH không hỗ trợ DEFAULT; phải chuẩn bị đủ hash bounds cho mọi remainder có khả năng phát sinh hoặc chấp nhận lỗi định tuyến nếu thiếu bucket.

---

## 32. DETACH PARTITION và chính sách lưu trữ dữ liệu cũ

### 32.1. Tách khỏi parent trước khi lưu trữ/xóa

Một quy trình retention thường:

1. Xác nhận khoảng dữ liệu đã hết hạn.
2. Xác nhận backup/archive và yêu cầu pháp lý.
3. Dừng hoặc điều phối writer có thể ghi vào partition đó.
4. `DETACH PARTITION` theo hình thức thích hợp.
5. Kiểm tra bảng đã không còn thuộc parent, dữ liệu vẫn còn trong standalone relation.
6. Archive/export, sau đó **DROP** nếu được phê duyệt.

Ví dụ chỉ nên chạy trên lab được phép:

~~~sql
ALTER TABLE partition_lab.events
DETACH PARTITION partition_lab.events_2026_10;
~~~

Sau khi DETACH, `events_2026_10` là relation độc lập, không còn xuất hiện khi SELECT parent. **Dữ liệu của nó chưa tự bị xóa**.

### 32.2. DROP partition hoặc child table là thao tác phá hủy

~~~sql
-- Chỉ ví dụ sau khi có backup/quyền/phê duyệt:
DROP TABLE partition_lab.events_2026_10;
~~~

`DROP TABLE` xóa relation, indexes và có thể ảnh hưởng dependencies; không tự động khôi phục được khi đã COMMIT. Với retention, thao tác này có thể nhanh hơn DELETE hàng trăm triệu rows, nhưng độ nhanh DDL **không làm giảm rủi ro xóa sai kỳ dữ liệu**.

### 32.3. DETACH PARTITION CONCURRENTLY

Ở các phiên bản PostgreSQL hỗ trợ, dạng:

~~~sql
ALTER TABLE partition_lab.events
DETACH PARTITION partition_lab.events_2026_10 CONCURRENTLY;
~~~

giảm tác động khóa trên parent theo cơ chế nhiều giai đoạn, nhưng có những giới hạn quan trọng:

- Không được chạy trong transaction block tường minh.
- Có hạn chế khi parent có **DEFAULT partition**.
- Có thể phải chờ transactions/snapshots.
- Có thể để lại trạng thái detach chưa hoàn tất nếu gián đoạn, cần thao tác hoàn tất theo quy trình, ví dụ `FINALIZE` trong các phiên bản hỗ trợ.
- Không thể dùng cùng mọi trường hợp subpartition/dependency tùy phiên bản.

**Vì lab `events` đang có DEFAULT, câu trên chỉ để minh họa cú pháp, không phải lệnh hợp lệ áp dụng trực tiếp trong toàn bộ kịch bản lab.** Khi có DEFAULT, xem xét non-concurrent DETACH hoặc thiết kế lại kế hoạch theo tài liệu phiên bản.

### 32.4. Dữ liệu đến muộn

Nếu bạn detach/drop partition October nhưng có một event October được ingest tháng November/December:

- Nếu có DEFAULT, nó có thể rơi vào DEFAULT.
- Nếu không, INSERT có thể lỗi.
- Nếu còn một partition khác trùng bound thì cấu trúc không hợp lệ.

Trước retention, xác định **late-arriving data window** và chính sách xử lý. Không chỉ lấy ngày chạy job hiện tại để cho rằng mọi dữ liệu của tháng cũ đã ổn định.

### 32.5. Backup, replication và dependencies

DETACH/DROP partition có thể tác động đến:

- Query/report dùng parent hoặc child trực tiếp.
- FKs và những relation tham chiếu.
- Logical replication/subscriptions hoặc pipelines đọc child.
- Backup/restore và PITR.
- Cache/trình theo dõi index/statistics.
- Replica replay/WAL và thời gian bảo trì.

Một lệnh DDL nhanh không thay thế kiểm soát những tác động phụ này.

---

## 33. Tăng số HASH partitions: không phải “thêm h4” là xong

### 33.1. Bốn buckets đang phủ đủ remainder

Parent `orders_hash` có bốn partitions với `MODULUS 4, REMAINDER 0..3`. Tất cả giá trị khóa đều được định tuyến vào một bucket.

Không thể thêm một partition HASH thứ năm với `MODULUS 4, REMAINDER 4`, vì remainder hợp lệ chỉ nằm trong 0..3.

Cũng không thể tạo thêm partition cùng `MODULUS 4, REMAINDER 1` vì chồng lấn.

### 33.2. Chuyển sang tám buckets cần redistribution

Một cách mở rộng về mặt thuật toán là chia mỗi nhóm hash cũ thành hai nhóm tương ứng với `MODULUS 8`, nhưng PostgreSQL **không tự chia dữ liệu** chỉ vì bạn khai báo một partition mới.

Một migration phải xem:

- Bảng/child nào sẽ được tạo.
- Bounds cũ và mới có chồng lấn trong từng giai đoạn không.
- Di chuyển dữ liệu giữa các tables/partitions thế nào.
- Đọc/ghi đang chạy có được đồng bộ không.
- Có local/global uniqueness requirements không.
- Lock và WAL/replication của việc chuyển rows.
- Làm sao rollback không mất dữ liệu.

### 33.3. Một phương án kiểm soát

Với dữ liệu lớn, thường phải lập kế hoạch như:

~~~text
Tạo bảng/cây HASH 8 buckets mới ở schema riêng
                  |
                  v
Sao chép/backfill dữ liệu theo batch
                  |
                  v
Đồng bộ phần ghi phát sinh khi backfill
                  |
                  v
Xác minh dữ liệu, khóa và indexes
                  |
                  v
Cutover có kiểm soát (app/table rename/routing)
                  |
                  v
Theo dõi, giữ đường rollback rồi mới dọn bảng cũ
~~~

Đây là **mô hình migration**, không phải script SQL hoàn chỉnh. Cách triển khai thực phụ thuộc traffic, FKs, sequences, các ràng buộc và thời gian downtime cho phép.

### 33.4. Nhiều buckets không giải quyết hot key

Nếu customer 101 chiếm 70% rows, dù đổi 4 thành 32 hash partitions, **các rows của cùng customer_id vẫn ở cùng một partition**. Muốn xử lý hot key phải xét workload, tenant isolation, subpartition theo thời gian hoặc mô hình khác.

### 33.5. Chọn số buckets trước khi tạo

Cân nhắc số distinct keys, data growth, kích thước target mỗi child, retention, query patterns, CPU/I/O và overhead catalog. Không chọn số bucket chỉ dựa vào số CPU cores nếu mục tiêu thực sự là quản lý truy vấn/retention.

---

## 34. Quản lý LIST khi thêm hoặc đổi nhóm

### 34.1. Group mới khi không có DEFAULT

Nếu parent LIST chỉ có north/south và không có DEFAULT, `region='west'` sẽ lỗi INSERT. Để hỗ trợ west, tạo partition:

~~~sql
CREATE TABLE partition_lab.support_tickets_west
PARTITION OF partition_lab.support_tickets
FOR VALUES IN ('west');
~~~

**Nhưng** trong lab có DEFAULT đang chứa west, nên lệnh trên có thể bị từ chối cho đến khi dữ liệu west được chuyển khỏi DEFAULT. Câu SQL này là **hình thức mục tiêu**, không phải thao tác chạy ngay trên dữ liệu mẫu.

### 34.2. Một region đổi tên

Nếu nghiệp vụ đổi `'north'` thành `'north_v2'`, có nhiều phương án:

- Chuẩn hóa giá trị trong application rồi UPDATE các row đúng lúc.
- Tạo partition nhận giá trị mới (hoặc cho thêm vào tập LIST của chiến lược được triển khai) theo DDL phù hợp.
- Di chuyển dữ liệu cũ sang nhóm mới, kiểm tra compatibility.
- Ngăn tình trạng hai giá trị cùng mô tả một region nhưng hệ thống tính/đếm khác nhau.

LIST partition key biến động khiến **row movement** có thể tốn kém. Tốt hơn dùng code ổn định như `region_id` và bảng dimension lưu tên hiển thị nếu region labels thường thay đổi.

### 34.3. Đừng chia một giá trị LIST thành hai partitions cùng cấp

Không thể tạo hai partitions đều `FOR VALUES IN ('north')` để chia dữ liệu north tại cùng một cấp LIST. Nếu north quá lớn, **subpartition north** theo RANGE/HASH hoặc đổi key/thiết kế.

---

## 35. VACUUM, ANALYZE và statistics trên partitioned tables

### 35.1. Leaf partitions có dữ liệu thật

Autovacuum/VACUUM quản lý dead tuples, visibility/freeze và thống kê ở từng relation có lưu dữ liệu. Leaf partitions có dữ liệu vật lý nên cần bảo trì như những bảng thường.

Xem thống kê:

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
WHERE schemaname = 'partition_lab'
ORDER BY relname;
~~~

`n_live_tup`/`n_dead_tup` là **ước lượng**, không phải phép đếm chính xác. Các giá trị thống kê có thể cập nhật trễ.

### 35.2. VACUUM một partition

~~~sql
VACUUM (ANALYZE) partition_lab.events_2026_11;
~~~

Chạy ngoài transaction block tường minh. Nó xử lý một partition, không yêu cầu bạn VACUUM toàn bộ các partitions còn lại chỉ để giữ một child khỏe mạnh.

### 35.3. ANALYZE parent

~~~sql
ANALYZE partition_lab.events;
~~~

Với partitioned table, planner cần các thống kê phù hợp cho query qua parent. PostgreSQL không nhất thiết auto-ANALYZE parent chỉ vì partitions con có nhiều INSERT/UPDATE; autovacuum không xử lý parent không lưu row theo cùng cách leaf table.

Vì vậy một số hệ thống cần **chủ động ANALYZE parent** sau khi dữ liệu/partition thay đổi lớn, bên cạnh việc leaf partitions được autoanalyze.

### 35.4. Không nhầm dead tuples với lý do phải repartition

Partition có nhiều dead tuples có thể do UPDATE/DELETE hoặc long-running snapshots khiến VACUUM chưa dọn được; không phải cứ bảng bloat là phải đổi RANGE thành HASH.

### 35.5. Statistics theo partition có thể tốt hơn hoặc tệ hơn

Một lợi ích tiềm năng: tháng có phân bố status riêng có thể có stats phản ánh đúng tháng đó. Nhưng nếu số partitions quá nhiều, mỗi child rất nhỏ, stats dễ nhiễu và planning overhead tăng.

Không kết luận partitioning tự bảo đảm ước tính cardinality chính xác.

---

## 36. Kích thước, indexes và kiểm tra phân bố

### 36.1. Kích thước mỗi child

~~~sql
SELECT
    c.oid::regclass AS relation_name,
    pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size,
    pg_total_relation_size(c.oid) AS bytes
FROM pg_class AS c
JOIN pg_namespace AS n ON n.oid = c.relnamespace
WHERE n.nspname = 'partition_lab'
  AND c.relname LIKE 'events_%'
ORDER BY bytes DESC, relation_name::text;
~~~

Lưu ý `LIKE 'events_%'` trong SQL có wildcard `_` là một ký tự; ở schema lab tên còn tương đối kiểm soát được. Trong hệ thống nghiêm ngặt nên lọc dựa vào `pg_partition_tree`/catalog quan hệ parent-child thay vì chỉ dựa vào tên.

### 36.2. Đếm rows mỗi partition

~~~sql
SELECT
    tableoid::regclass AS partition_name,
    COUNT(*) AS row_count
FROM partition_lab.events
GROUP BY tableoid
ORDER BY row_count DESC, partition_name;
~~~

Query này quét dữ liệu thật trong các partitions, vì vậy **không chạy COUNT(*) toàn cây quá thường xuyên** trên production hàng tỷ rows. Với giám sát định kỳ, dùng statistics estimates và kiểm chứng bằng COUNT(*) khi thích hợp.

### 36.3. Xem index trên child

~~~sql
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'partition_lab'
  AND tablename IN (
      'events_2026_10',
      'events_2026_11',
      'events_2026_12',
      'events_other'
  )
ORDER BY tablename, indexname;
~~~

Quan sát:

- PK local trên partition.
- Index tạo từ parent.
- Index chỉ định riêng cho một child.
- Có index trùng mục đích hoặc invalid không.

### 36.4. Monitoring DEFAULT partition

Trên hệ thống RANGE có DEFAULT:

~~~sql
SELECT
    date_trunc('month', event_at) AS event_month,
    COUNT(*) AS events_in_default
FROM partition_lab.events_other
GROUP BY date_trunc('month', event_at)
ORDER BY event_month;
~~~

Đây là query quan sát **phân bố dữ liệu chưa được đặt partition riêng**. Với DEFAULT rất lớn, dùng thống kê/batch/alerts để tránh report này thành full scan tốn kém liên tục.

---

## 37. Lock, WAL và vận hành partition DDL

### 37.1. CREATE PARTITION không hoàn toàn “không khóa”

`CREATE TABLE ... PARTITION OF parent`, `ATTACH PARTITION`, `DETACH PARTITION` và các thay đổi index/constraint trên parent đều có thể yêu cầu relation locks ở các mức khác nhau.

Khi migration cố attach bảng đã có dữ liệu, việc validate bounds/indexes có thể quét table/DEFAULT, kéo dài thời gian giữ lock. Các câu DDL nhỏ trên lab không đại diện cho bảng thật.

### 37.2. Kiểm tra ai chặn DDL

~~~sql
SELECT
    a.pid,
    a.application_name,
    a.state,
    a.wait_event_type,
    a.wait_event,
    pg_blocking_pids(a.pid) AS blocking_pids,
    LEFT(a.query, 180) AS sql_sample
FROM pg_stat_activity AS a
WHERE a.datname = current_database()
  AND (
       a.wait_event_type = 'Lock'
       OR cardinality(pg_blocking_pids(a.pid)) > 0
  )
ORDER BY a.pid;
~~~

Một transaction dài hoặc `idle in transaction` giữ lock có thể chặn schema changes. Không tự terminate blocker khi chưa xác minh owner và rủi ro.

### 37.3. Timeout trong migration

Ví dụ trên lab:

~~~sql
BEGIN;
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '30s';

-- Một DDL ngắn khi đã chuẩn bị đầy đủ:
-- ALTER TABLE ... ATTACH PARTITION ...

ROLLBACK;
~~~

`SET LOCAL` có phạm vi transaction. Nếu lock_timeout/statement_timeout làm statement lỗi, transaction có thể ở trạng thái aborted; phải ROLLBACK hoặc xử lý savepoint hợp lệ. Với `DETACH PARTITION CONCURRENTLY` và `CREATE INDEX CONCURRENTLY` không chạy trong BEGIN, dùng cách cấu hình timeout ngoài transaction theo chính sách session/job và reset sau đó.

### 37.4. Metadata changes cũng có thể ảnh hưởng replication

CREATE/ATTACH/DETACH/DROP partitions, index builds và backfill đều có thể tạo WAL hoặc thay đổi schema mà downstream logical decoding/replica cần xử lý theo cơ chế riêng. Không cho rằng “DROP partition không DELETE từng row” nghĩa là mọi replica/backup không chịu ảnh hưởng.

### 37.5. Tách biệt HA và partitioning

Partitioned table vẫn là dữ liệu của một PostgreSQL database. Nó không thay thế replication, backup, failover và disaster recovery. Khi thay đổi partition lifecycle, cần đánh giá primary, standby, logical replication và các consumers.

---

## 38. Di chuyển từ một bảng lớn không partition sang partitioned table

### 38.1. Không thể cứ ALTER một bảng thường thành RANGE parent bằng một câu đơn giản

Trong thực tế, chuyển một bảng heap lớn sang partitioning thường đòi **xây dựng bảng partitioned mới và di chuyển dữ liệu/cutover**, chứ không phải câu `ALTER TABLE old PARTITION BY RANGE (...)` phổ quát được PostgreSQL hỗ trợ cho mọi bảng thường.

### 38.2. Quy trình ở mức kiến trúc

~~~text
Bảng cũ: orders_old
          |
          v
Phân tích workload, partition key, PK/UNIQUE/FK
          |
          v
Tạo orders_new PARTITION BY ...
          |
          v
Tạo đủ child partitions, indexes, constraints
          |
          v
Backfill theo batches; xác minh row counts/keys
          |
          v
Đồng bộ writes trong quá trình di chuyển
          |
          v
Cutover có kiểm soát (app routing / renaming)
          |
          v
Theo dõi, rollback plan, chỉ dọn old sau khi an toàn
~~~

### 38.3. Vấn đề không thể bỏ qua

- PK cũ chỉ có `order_id` nhưng parent mới partition theo `created_at` không hỗ trợ PK `order_id` đơn lẻ.
- Các FKs từ bảng khác đang tham chiếu tên/oid bảng cũ.
- Trigger, RLS policies, grants, sequences/identity, generated columns, replication publication.
- Realtime writes trong lúc backfill.
- Đảm bảo không thiếu/duplicate rows khi cutover.
- Index/constraint validation và lock time.
- Rollback nếu một service còn dùng schema cũ.

### 38.4. Không đổi schema bằng rename đơn giản khi chưa xử lý dependencies

`ALTER TABLE old RENAME TO ...` có thể thay tên relation nhưng **không tự chuyển các FKs/views/triggers/permissions** sang bảng mới theo đúng ý định ứng dụng. Cần thiết kế migration có kiểm tra dependencies và kiến trúc phù hợp, không chỉ thay chuỗi tên.

### 38.5. Ưu tiên dữ liệu đúng hơn một cutover nhanh

Nếu một bước backfill thất bại, phải biết cách resume, phát hiện row thiếu, kiểm tra checksum/sample và không làm mất writes đang phát sinh. Partitioning có ích khi vận hành dài hạn, nhưng cutover sai có thể gây mất dữ liệu nghiệp vụ ngay lập tức.

---

## 39. Những trường hợp không nên phân vùng

Partitioning thường không phải lựa chọn tối ưu nếu:

1. Bảng chỉ vài nghìn đến vài triệu rows, query đã nhanh với B-tree/BRIN.
2. Workload không lọc theo partition key và luôn phải quét mọi child.
3. Cần UNIQUE/PK toàn cục trên cột không chứa partition key, không muốn đổi schema.
4. Số distinct nhóm quá ít hoặc skew cực lớn khiến HASH/LIST không giúp phân phối.
5. Partition key biến động liên tục, gây row movement nhiều.
6. Chia quá nhỏ khiến overhead catalog/locks/planning vượt lợi ích.
7. Không có lịch tạo partition trước, retention, backup và monitor.
8. Hệ thống chỉ cần tăng read throughput nhưng bottleneck thực nằm ở join sai, quá nhiều SELECT *, network hoặc connection pool.
9. Ý định thực sự là **sharding qua nhiều node**; local partitioning không tự thực hiện.
10. Dataset liên tục phải aggregate toàn lịch sử, nên phân vùng có thể cải thiện quản trị nhưng không xóa chi phí tính toán.

Trước khi chuyển sang partitioned tables, benchmark bảng thường với chỉ mục/SQL phù hợp. Tối ưu hóa tốt là đáp ứng mục tiêu, không phải dùng cấu trúc phức tạp hơn.

---

## 40. Các lỗi và ngộ nhận phổ biến

| Ngộ nhận hoặc lỗi | Hậu quả | Cách hiểu/khắc phục |
|---|---|---|
| “Partitioning tự làm mọi SELECT nhanh” | Query không lọc key vẫn đọc nhiều partitions | Xem pruning và scan strategy |
| “Partition parent lưu rows như bảng thường” | Hiểu sai `ONLY parent` và kích thước heap | Dữ liệu ở leaf partitions |
| “RANGE upper bound được bao gồm” | Dữ liệu mốc đầu tháng vào nhầm partition | Nhớ `[lower, upper)` |
| “Tháng 10 kết thúc 23:59:59” | Bỏ sót mili/microsecond | Dùng đầu tháng sau làm exclusive upper |
| “RANGE nhiều cột là hình chữ nhật hai chiều” | Bound nhận miền bất ngờ | RANGE multi-key so lexicographically |
| “RANGE tự nhận NULL vào partition gần nhất” | INSERT NULL không tìm thấy partition | NOT NULL/DEFAULT hoặc chuẩn hóa |
| “LIST('north') nhận cả 'North'” | Routing vào DEFAULT hoặc lỗi | Chuẩn hóa case hoặc key |
| “LIST không thể nhận NULL” | Hiểu thiếu cú pháp | `FOR VALUES IN (NULL)` hoặc DEFAULT |
| “LIST có thể tạo hai child cùng giá trị north” | Overlap bound bị từ chối | Subpartition nếu một nhóm quá lớn |
| “HASH là customer_id % N” | Đoán sai child | Routing dựa hash operator class |
| “HASH có DEFAULT” | DDL không hợp lệ | Tạo bounds HASH phù hợp |
| “HASH 4 buckets luôn chia đều 25% rows” | Một hot key làm lệch partition | Đo skew và distinct keys |
| “Muốn từ 4 lên 8 buckets chỉ cần thêm h4” | Bound sai/overlap, không di chuyển dữ liệu | Migration rehash/repartition rõ |
| “RANGE và HASH là sharding nhiều máy” | Đặt kỳ vọng sai về tài nguyên | Partitioning local trong một database |
| “Tạo index trên cha nghĩa là global index” | Hiểu sai UNIQUE toàn bảng | Parent index logic, child indexes vật lý |
| “PK(event_id) hợp lệ dù partition theo event_at” | Constraint bị từ chối | PK/UNIQUE parent phải chứa partition key |
| “PK(event_at,event_id) làm event_id unique” | Có thể trùng event_id khác event_at | Hiểu đúng composite key |
| “CREATE INDEX CONCURRENTLY trên partitioned parent luôn chạy” | DDL bị từ chối trong giới hạn hiện hành | Build leaf indexes concurrent và attach |
| “Index trùng tên nghĩa là usable” | Index có thể INVALID | Xem `pg_index.indisvalid` |
| “Không cần tạo partition tháng sau vì có DEFAULT” | DEFAULT tích tụ và gây khó ATTACH | Tạo trước và giám sát DEFAULT |
| “ATTACH có metadata-only nên không scan/lock” | DDL có thể chờ và scan child/DEFAULT | Prevalidate CHECK, xem lock |
| “Có rows March trong DEFAULT vẫn attach March ngay” | Bị từ chối/không an toàn | Di chuyển dữ liệu có cutover |
| “DETACH đồng nghĩa DELETE” | Dữ liệu vẫn ở standalone | Phân biệt DETACH và DROP |
| “DROP partition vô hại vì nhanh” | Mất cả kỳ dữ liệu | Kiểm tra retention/backup/phê duyệt |
| “DETACH CONCURRENTLY dùng được với mọi parent” | Gặp giới hạn DEFAULT/transaction | Tra phiên bản và điều kiện |
| “UPDATE partition key chỉ cập nhật một field” | Có thể move row giữa leaf, tăng WAL/lock | Thiết kế key ổn định |
| “ON CONFLICT chuyển partition tùy ý” | Có thể bị từ chối với DO UPDATE | Hiểu giới hạn row movement |
| “Pruning yêu cầu index” | Tạo index không cần thiết | Pruning dùng bounds, index dùng trong child |
| “EXPLAIN có Seq Scan tức pruning không chạy” | Seq Scan trên một leaf nhỏ là hợp lý | Xem child được scan |
| “EXTRACT(MONTH) = 11 tương đương November 2026” | Lấy mọi November, không thể prune như range | Dùng khoảng có cả năm |
| “Timezone UI không ảnh hưởng thiết kế RANGE” | Dữ liệu ngày địa phương rơi tháng UTC khác | Chốt timezone/bounds |
| “Bật partitionwise join luôn cải thiện” | Tăng planning/memory | Benchmark theo workload |
| “Một partition một row là tốt nhất” | Metadata/locks/planning overhead nặng | Chọn granularity theo vận hành |
| “Autovacuum của leaf đồng nghĩa stats parent luôn mới” | Planner parent có thể có stats cũ | Theo dõi và ANALYZE parent |
| “Migration bảng thường bằng RENAME là đủ” | FK/views/triggers/dependencies còn ràng buộc | Lập kế hoạch cutover toàn vẹn |
| “DELETE 100 triệu rows như DROP partition” | WAL/dead tuples/maintenance khác nhiều | Dùng retention theo partition khi đúng nghiệp vụ |

---

## 41. Tình huống thực tế 1: nhật ký truy cập giữ 90 ngày

### 41.1. Yêu cầu

Hệ thống có:

- 20 triệu events/ngày.
- Query thường tìm 1–3 ngày gần nhất.
- Cần giữ dữ liệu 90 ngày và xóa kỳ cũ nhanh.
- Truy vấn thường lọc tenant_id trong một khoảng event_at.
- Có event đến trễ tới 48 giờ.

### 41.2. Phân tích lựa chọn

**RANGE(event_at) theo ngày** là ứng viên vì retention và predicate chính đều theo thời gian.

Nếu chia theo tháng, một partition chứa khoảng 600 triệu events, có thể rất lớn. Nếu chia theo giờ, 90 ngày × 24 = 2.160 partitions, overhead lớn hơn. Chia theo ngày có khoảng 90 leaf partitions nóng, có thể là điểm khởi đầu hợp lý để benchmark.

### 41.3. Thiết kế tham khảo

~~~sql
CREATE TABLE partition_lab.access_logs (
    log_id BIGINT NOT NULL,
    tenant_id INTEGER NOT NULL,
    event_at TIMESTAMPTZ NOT NULL,
    path TEXT NOT NULL,
    status_code INTEGER NOT NULL,
    PRIMARY KEY (event_at, log_id)
)
PARTITION BY RANGE (event_at);
~~~

Ví dụ một ngày:

~~~sql
CREATE TABLE partition_lab.access_logs_2026_11_14
PARTITION OF partition_lab.access_logs
FOR VALUES FROM ('2026-11-14 00:00:00+00')
           TO   ('2026-11-15 00:00:00+00');
~~~

Index:

~~~sql
CREATE INDEX idx_access_logs_tenant_time
ON partition_lab.access_logs (tenant_id, event_at DESC);
~~~

Query:

~~~sql
SELECT log_id, event_at, path, status_code
FROM partition_lab.access_logs
WHERE tenant_id = 11
  AND event_at >= TIMESTAMPTZ '2026-11-13 00:00:00+00'
  AND event_at <  TIMESTAMPTZ '2026-11-15 00:00:00+00'
ORDER BY event_at DESC
LIMIT 100;
~~~

### 41.4. Vòng đời

- Pre-create partitions trước vài ngày.
- Giám sát partition DEFAULT nếu có và lỗi routing.
- Retention chỉ xét partitions mà toàn bộ bound đã hết hạn **và** vượt late-arrival window.
- Archive/backup, DETACH theo phương án phù hợp, xác minh rồi mới DROP.
- Theo dõi daily partition sizes, autovacuum/index bloat, replica lag.
- Đảm bảo thống kê parent/leaf phù hợp.

### 41.5. Rủi ro khó thấy

PK `(event_at,log_id)` không bảo đảm `log_id` duy nhất nếu event_at khác. Nếu API dùng log_id làm ID đơn, cần cơ chế sinh/kiểm soát ID riêng hoặc luôn truyền composite key; không đưa vào production trước khi giải quyết invariant này.

---

## 42. Tình huống thực tế 2: dữ liệu khách hàng theo vùng

### 42.1. Yêu cầu

Doanh nghiệp có nhóm region north/south/west, mỗi nhóm có chính sách maintenance khác nhau. Query báo cáo thường theo đúng region, dữ liệu có thể chuyển vùng hiếm khi.

### 42.2. LIST có thể phù hợp

~~~sql
CREATE TABLE partition_lab.region_orders (
    order_id BIGINT NOT NULL,
    region TEXT NOT NULL,
    customer_id BIGINT NOT NULL,
    placed_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (region, order_id)
)
PARTITION BY LIST (region);

CREATE TABLE partition_lab.region_orders_north
PARTITION OF partition_lab.region_orders
FOR VALUES IN ('north');

CREATE TABLE partition_lab.region_orders_south
PARTITION OF partition_lab.region_orders
FOR VALUES IN ('south');

CREATE TABLE partition_lab.region_orders_west
PARTITION OF partition_lab.region_orders
FOR VALUES IN ('west');
~~~

### 42.3. Query

~~~sql
EXPLAIN
SELECT order_id, customer_id, placed_at
FROM partition_lab.region_orders
WHERE region = 'north'
  AND placed_at >= TIMESTAMPTZ '2026-11-01 00:00+00';
~~~

Có cơ hội prune south/west. Nếu north chiếm 95% dữ liệu, riêng prune không chắc làm north query nhanh; cần local index và cân nhắc subpartition.

### 42.4. Tránh dùng status thay region khi status thay đổi nhiều

Nếu `status='new'` chuyển liên tục sang `'paid'`, LIST(status) làm nhiều UPDATE phải chuyển partition. Region có thể ổn định hơn; nhưng nếu nghiệp vụ thường chuyển khách hàng giữa vùng, cần tính row movement và uniqueness cùng FK.

---

## 43. Tình huống thực tế 3: bảng nhiều tenant, query luôn theo tenant_id

### 43.1. Yêu cầu

Ứng dụng SaaS có 50.000 tenants; truy vấn chủ yếu `WHERE tenant_id = ?`, ít cần retention theo thời gian. Mỗi tenant có số hàng tương đối vừa phải.

### 43.2. HASH là ứng viên

~~~sql
CREATE TABLE partition_lab.tenant_messages (
    tenant_id BIGINT NOT NULL,
    message_id BIGINT NOT NULL,
    sent_at TIMESTAMPTZ NOT NULL,
    body TEXT NOT NULL,
    PRIMARY KEY (tenant_id, message_id)
)
PARTITION BY HASH (tenant_id);

CREATE TABLE partition_lab.tenant_messages_h0
PARTITION OF partition_lab.tenant_messages
FOR VALUES WITH (MODULUS 4, REMAINDER 0);

CREATE TABLE partition_lab.tenant_messages_h1
PARTITION OF partition_lab.tenant_messages
FOR VALUES WITH (MODULUS 4, REMAINDER 1);

CREATE TABLE partition_lab.tenant_messages_h2
PARTITION OF partition_lab.tenant_messages
FOR VALUES WITH (MODULUS 4, REMAINDER 2);

CREATE TABLE partition_lab.tenant_messages_h3
PARTITION OF partition_lab.tenant_messages
FOR VALUES WITH (MODULUS 4, REMAINDER 3);
~~~

### 43.3. Query

~~~sql
EXPLAIN
SELECT message_id, sent_at, body
FROM partition_lab.tenant_messages
WHERE tenant_id = 12345
ORDER BY sent_at DESC
LIMIT 50;
~~~

HASH có thể prune còn một bucket. Tuy nhiên nếu bucket chứa hàng triệu messages từ nhiều tenants, query vẫn cần local index `(tenant_id,sent_at DESC)` phù hợp.

### 43.4. Không coi HASH là giải pháp hot tenant

Nếu một tenant chiếm 60% tổng messages, nó vẫn nằm trọn trong một bucket; mất cân bằng còn lại không tự được giải quyết. Có thể cần chọn partition strategy khác, thêm time dimension hoặc cô lập tenant lớn vào mô hình riêng.

### 43.5. Dữ liệu yêu cầu xóa theo thời gian?

Nếu retention theo 30 ngày là yếu tố quyết định, HASH đơn thuần không giúp DROP dữ liệu cũ bằng partition theo thời gian. Có thể xét **RANGE(time) rồi HASH(tenant)** hoặc chỉ RANGE(time) cộng local index tenant, nhưng phải tính rất kỹ số lượng partitions và constraints.

---

## 44. Bài tập thực hành

Các bài giả định đã tạo schema `partition_lab` và những bảng theo từng phần. Một số bài yêu cầu viết SQL **không nhất thiết chạy trực tiếp** nếu ví dụ trước đã thay đổi dữ liệu/partition. Cần làm trên database riêng, và tránh thực thi DELETE/DROP nếu chưa có phương án khôi phục.

### Bài 1 — Khái niệm

Giải thích declarative partitioning, bảng parent, leaf partition, partition key và partition pruning. Partitioning có tự chia dữ liệu sang nhiều PostgreSQL server không?

### Bài 2 — Chọn chiến lược

Với nhật ký ứng dụng 300 triệu rows, query theo tháng và cần xóa dữ liệu trước hai năm, nên cân nhắc RANGE, LIST hay HASH? Vì sao?

### Bài 3 — RANGE syntax

Viết câu tạo bảng `monthly_sales` với `sale_id BIGINT`, `sold_at DATE`, `amount NUMERIC`, phân vùng theo `sold_at`.

### Bài 4 — RANGE November

Viết câu tạo partition nhận `sold_at` trong November 2026 và giải thích cận đầu/cuối.

### Bài 5 — Biên giới

Sự kiện tại `2026-11-01 00:00:00+00` thuộc October `[Oct 1,Nov 1)` hay November `[Nov 1,Dec 1)`?

### Bài 6 — MINVALUE/MAXVALUE

Viết hai partition cho bảng `range_demo(score)`, một nhận mọi score dưới 0, một nhận mọi score từ 0 trở lên. Giá trị NULL có tự nằm trong một partition RANGE không?

### Bài 7 — RANGE nhiều cột

Với key `(tenant_id,seq_no)`, bound `FROM(1,0) TO(2,0)` có nhận row `(1,9999)` và `(2,0)` không? Vì sao?

### Bài 8 — DEFAULT RANGE

Một event January 2027 được INSERT nhưng chỉ có partitions October–December 2026 và DEFAULT. Nó vào đâu? Nếu không có DEFAULT thì sao?

### Bài 9 — tableoid

Viết SQL lấy `event_id`, `event_at` và tên partition vật lý chứa row. Vì sao nên truy vấn parent nhưng quan sát child bằng tableoid khi cần chẩn đoán?

### Bài 10 — Chỉ parent

`SELECT COUNT(*) FROM ONLY partition_lab.events` dự kiến trả gì trong lab? Tại sao?

### Bài 11 — LIST syntax

Tạo bảng `tickets_by_region` partition theo `region TEXT` và một child nhận `'north'`, `'northern'`.

### Bài 12 — LIST NULL

Viết LIST child nhận NULL và câu query chỉ chọn những ticket có `region IS NULL`. Vì sao `region = NULL` không phù hợp?

### Bài 13 — LIST DEFAULT

Với LIST north/south và DEFAULT, giá trị west vào đâu? Nêu rủi ro khi DEFAULT đã có west mà bạn muốn ATTACH partition riêng cho west.

### Bài 14 — LIST case

Vì sao `region='North'` không nên được mặc định xem như `'north'`? Bạn sẽ chuẩn hóa kiểu gì?

### Bài 15 — HASH syntax

Tạo parent `hash_events(tenant_id BIGINT,event_id BIGINT)` phân vùng theo `tenant_id` và bốn children modulus 4, remainder 0..3.

### Bài 16 — HASH routing

Có thể biết child chỉ bằng `tenant_id % 4` không? Cách quan sát kết quả thực tế là gì?

### Bài 17 — HASH DEFAULT

HASH có thể tạo `FOR VALUES DEFAULT` không? Điều gì xảy ra khi thiếu remainder cần thiết?

### Bài 18 — Hot key

Một tenant tạo 80% events. HASH(tenant_id) chia 16 buckets có chia đều workload của tenant đó sang 16 partitions không?

### Bài 19 — Pruning RANGE

Viết truy vấn `EXPLAIN` lọc events từ 10/11 đến trước 20/11/2026 UTC. PostgreSQL có thể prune những child nào?

### Bài 20 — Pruning HASH

Viết query tìm orders_hash của customer 101. Nếu query chỉ có order_id, có tự prune xuống một bucket không?

### Bài 21 — Pruning vs index

Một plan chỉ Seq Scan trên `events_2026_11` khi query lọc November. Điều đó có nghĩa partition pruning thất bại không?

### Bài 22 — Pruning với expression

Vì sao `EXTRACT(MONTH FROM event_at)=11` không tương đương điều kiện đúng November 2026, và có thể khó pruning hơn?

### Bài 23 — Timezone

Sự kiện `2026-10-31 20:00+00` có thể là ngày nào ở Việt Nam? Nếu RANGE theo UTC, nó vào October hay November partition?

### Bài 24 — Parent PRIMARY KEY

Tại sao `PRIMARY KEY(event_id)` không hợp lệ trên bảng RANGE(event_at) theo quy tắc parent partitioned PK hiện hành? Khóa nào trong lab hợp lệ và có giới hạn uniqueness nào?

### Bài 25 — UNIQUE global

Nếu yêu cầu `event_id` unique toàn database bất kể event_at, `PRIMARY KEY(event_at,event_id)` đã đủ chưa? Đề xuất một chiến lược mô hình dữ liệu an toàn.

### Bài 26 — Local indexes

Viết index trên parent phục vụ `WHERE tenant_id=? AND event_at BETWEEN... ORDER BY event_at DESC`. Index vật lý được tạo ở đâu?

### Bài 27 — CREATE INDEX CONCURRENTLY

Vì sao không mặc định chạy `CREATE INDEX CONCURRENTLY ON partitioned_parent(...)`? Nêu quy trình sử dụng parent `ON ONLY`, tạo leaf indexes concurrently rồi ATTACH.

### Bài 28 — UPDATE row movement

Một event ở November đổi `event_at` sang December. Có thể phải di chuyển row không? Những rủi ro vận hành nào phát sinh?

### Bài 29 — ON CONFLICT

Vì sao `ON CONFLICT(event_at,event_id) DO NOTHING` không ngăn cùng event_id ở hai thời điểm khác nhau?

### Bài 30 — Subpartitioning

Viết schema chia theo `RANGE(event_at DATE)` ở level 1 và `HASH(tenant_id)` modulus 2 ở level 2 cho tháng November 2026. Nêu tổng leaf count khi có 12 tháng × 2 buckets.

### Bài 31 — Catalog

Viết query `pg_partition_tree` cho events và query xem partition bounds qua `pg_inherits/pg_class`.

### Bài 32 — ATTACH existing

Một bảng standalone có dữ liệu March 2027 cần attach vào events. Vì sao một CHECK bound đã VALID trên standalone có thể hữu ích?

### Bài 33 — DEFAULT chứa dữ liệu chồng bound

DEFAULT chứa rows March 2027. Có thể attach partition March mà không di chuyển dữ liệu không? Trình bày quy trình an toàn về mặt ý tưởng.

### Bài 34 — DETACH vs DROP

Phân biệt `DETACH PARTITION` và `DROP TABLE` về khả năng nhìn thấy dữ liệu từ parent và việc xóa dữ liệu vật lý.

### Bài 35 — DETACH CONCURRENTLY

Nêu ít nhất ba điều kiện/giới hạn cần kiểm tra trước khi dùng DETACH PARTITION CONCURRENTLY. Có thể dùng trực tiếp trên parent events lab đang có DEFAULT không?

### Bài 36 — HASH rebalancing

Parent có đủ 4 partitions modulus 4. Tại sao không thể chỉ thêm “remainder 4”? Nếu muốn 8 buckets, bạn cần lên kế hoạch gì?

### Bài 37 — Autoanalyze

Vì sao leaf partitions đã có thống kê mới nhưng parent có thể cần ANALYZE thủ công? Viết câu lệnh tương ứng.

### Bài 38 — Retention

Một bảng logs theo ngày muốn xóa dữ liệu quá 90 ngày nhưng events có thể đến trễ 48 giờ. Cần kiểm tra gì trước khi detach/drop một partition?

### Bài 39 — Vòng đời partition mới

Nêu checklist chuẩn bị một partition RANGE tháng tiếp theo để tránh ghi dữ liệu vào DEFAULT hoặc gặp lỗi no partition found.

### Bài 40 — Tổng hợp kiến trúc

Hệ thống có 10.000 tenants, hàng tỷ orders, 95% query lọc tenant_id và khoảng một tháng; retention 2 năm. Đề xuất ít nhất hai chiến lược phân vùng khả thi, so sánh ưu/nhược, chú ý số leaf partitions, parent PK/UNIQUE và tốc độ ingest.

---

## 45. Gợi ý lời giải

### Bài 1 — Khái niệm

Declarative partitioning cho phép định nghĩa **bảng logic parent** với `PARTITION BY` và các bảng con theo bound. Row vật lý được lưu ở **leaf partition**, PostgreSQL định tuyến INSERT và có thể prune những partitions không thể thỏa WHERE. Partitioning trong một PostgreSQL database **không tự sharding lên nhiều servers**.

### Bài 2 — Chọn RANGE cho retention theo thời gian

**RANGE(event_at)** là ứng viên vì truy vấn thường theo tháng và chính sách xóa dữ liệu cũ cũng theo thời gian. Khi một partition đã hết retention và dữ liệu đến muộn được xử lý, có thể DETACH/DROP đúng partition thay vì DELETE hàng triệu rows. Chọn kích cỡ tháng/ngày sau khi đo volume/index sizes và số partitions.

### Bài 3 — Tạo parent RANGE

~~~sql
CREATE TABLE partition_lab.monthly_sales (
    sale_id BIGINT NOT NULL,
    sold_at DATE NOT NULL,
    amount NUMERIC(12,2) NOT NULL
)
PARTITION BY RANGE (sold_at);
~~~

Nếu cần PK trên parent, key phải bao gồm `sold_at` theo giới hạn partitioned UNIQUE/PK. Không tùy tiện thêm `PRIMARY KEY(sale_id)` vào parent RANGE(sold_at).

### Bài 4 — Partition tháng 11

~~~sql
CREATE TABLE partition_lab.monthly_sales_2026_11
PARTITION OF partition_lab.monthly_sales
FOR VALUES FROM ('2026-11-01') TO ('2026-12-01');
~~~

Cận dưới 01/11 được bao gồm; cận trên 01/12 bị loại trừ. Vì thế mọi ngày November được nhận, December bắt đầu ở partition tiếp theo.

### Bài 5 — Biên giới

`2026-11-01 00:00:00+00` thuộc **November**, không thuộc October. RANGE sử dụng lower inclusive, upper exclusive.

### Bài 6 — MINVALUE/MAXVALUE

Trên bảng `range_demo(score)` đã có thể tạo:

~~~sql
CREATE TABLE partition_lab.range_demo_negative
PARTITION OF partition_lab.range_demo
FOR VALUES FROM (MINVALUE) TO (0);

CREATE TABLE partition_lab.range_demo_nonnegative
PARTITION OF partition_lab.range_demo
FOR VALUES FROM (0) TO (MAXVALUE);
~~~

Hai lệnh này là **một phương án thay thế** cho các `range_demo_low/mid/high` được tạo ở phần 7; không chạy cả hai thiết kế trên cùng parent vì bounds chồng lấn.

NULL không tự nằm trong bound RANGE; cần xử lý NULL qua DEFAULT phù hợp hoặc đặt NOT NULL trên key.

### Bài 7 — RANGE nhiều cột

Với lexicographic bounds `[(1,0),(2,0))`:

- `(1,9999)`: **được nhận**, vì first key 1 nhỏ hơn upper first key 2.
- `(2,0)`: **không được nhận**, vì bằng exclusive upper.

Đừng diễn giải multi-column RANGE thành hai khoảng số độc lập.

### Bài 8 — DEFAULT RANGE

Với parent `events` có DEFAULT, January 2027 hiện chưa có partition riêng nên row vào `events_other`. Nếu không có DEFAULT và không có partition January, INSERT báo lỗi không tìm được partition.

### Bài 9 — tableoid

~~~sql
SELECT
    event_id,
    event_at,
    tableoid::regclass AS physical_partition
FROM partition_lab.events
ORDER BY event_at, event_id;
~~~

Ứng dụng thường nên INSERT/SELECT parent để không phụ thuộc tên child. `tableoid` hữu ích khi chẩn đoán routing và kiểm tra dữ liệu sai partition.

### Bài 10 — ONLY parent

~~~sql
SELECT COUNT(*)
FROM ONLY partition_lab.events;
~~~

Kỳ vọng **0** do parent declarative partitioned table không chứa heap rows thường. Không dùng `ONLY` cho truy vấn nghiệp vụ cần xem dữ liệu ở leaf partitions.

### Bài 11 — LIST syntax

~~~sql
CREATE TABLE partition_lab.tickets_by_region (
    ticket_id BIGINT NOT NULL,
    region TEXT,
    subject TEXT NOT NULL
)
PARTITION BY LIST (region);

CREATE TABLE partition_lab.tickets_by_region_north
PARTITION OF partition_lab.tickets_by_region
FOR VALUES IN ('north', 'northern');
~~~

Các nhóm khác cần child/DEFAULT trước khi INSERT các giá trị không thuộc north.

### Bài 12 — LIST NULL

~~~sql
CREATE TABLE partition_lab.tickets_by_region_null
PARTITION OF partition_lab.tickets_by_region
FOR VALUES IN (NULL);

SELECT ticket_id, subject
FROM partition_lab.tickets_by_region
WHERE region IS NULL;
~~~

`= NULL` trả UNKNOWN theo SQL three-valued logic; `IS NULL` mới kiểm tra giá trị NULL đúng.

### Bài 13 — DEFAULT và nhóm mới

`'west'` rơi vào DEFAULT nếu không có child west. Khi muốn attach west riêng, hệ thống phải bảo đảm DEFAULT **không còn rows west**. Nếu có, phải di chuyển có kiểm soát trước khi attach; không xóa dữ liệu chỉ để làm DDL chạy.

### Bài 14 — Case

`'north'` và `'North'` thường là hai giá trị text khác nhau theo semantics collation/operator class. Có thể chuẩn hóa lowercase ở ingestion hoặc dùng một `region_code` ổn định. Nếu dùng expression `lower(region)` làm partition key, kiểm tra ràng buộc PK/UNIQUE trên parent và tính chất function/locale.

### Bài 15 — Tạo HASH

~~~sql
CREATE TABLE partition_lab.hash_events (
    tenant_id BIGINT NOT NULL,
    event_id BIGINT NOT NULL
)
PARTITION BY HASH (tenant_id);

CREATE TABLE partition_lab.hash_events_h0
PARTITION OF partition_lab.hash_events
FOR VALUES WITH (MODULUS 4, REMAINDER 0);

CREATE TABLE partition_lab.hash_events_h1
PARTITION OF partition_lab.hash_events
FOR VALUES WITH (MODULUS 4, REMAINDER 1);

CREATE TABLE partition_lab.hash_events_h2
PARTITION OF partition_lab.hash_events
FOR VALUES WITH (MODULUS 4, REMAINDER 2);

CREATE TABLE partition_lab.hash_events_h3
PARTITION OF partition_lab.hash_events
FOR VALUES WITH (MODULUS 4, REMAINDER 3);
~~~

Đủ bốn remainders cho modulus 4, có route cho các khóa theo bộ bounds này.

### Bài 16 — HASH routing

Không. PostgreSQL sử dụng hash support function và partitioning semantics, không phải phép modulo SQL trực tiếp trên tenant_id. Quan sát:

~~~sql
SELECT tenant_id, event_id,
       tableoid::regclass AS target_partition
FROM partition_lab.hash_events
ORDER BY tenant_id, event_id;
~~~

Cần INSERT dữ liệu lab trước khi SELECT mới có hàng để quan sát.

### Bài 17 — HASH DEFAULT

Không có DEFAULT partition cho HASH. Với một modulus/remainder không được phủ bởi child thích hợp, row có hash tương ứng có thể bị từ chối vì không tìm thấy partition.

### Bài 18 — Hot key

Không. Tất cả rows cùng `tenant_id` được định tuyến vào **cùng bucket**. HASH giúp phân phối nhiều distinct tenants, không tự chia một tenant rất lớn sang 16 buckets. Cân nhắc subpartition theo thời gian hoặc thiết kế khác.

### Bài 19 — Pruning RANGE

~~~sql
EXPLAIN
SELECT event_id, event_at
FROM partition_lab.events
WHERE event_at >= TIMESTAMPTZ '2026-11-10 00:00+00'
  AND event_at <  TIMESTAMPTZ '2026-11-20 00:00+00';
~~~

Bounds chỉ giao November, nên PostgreSQL có thể bỏ October, December và DEFAULT. Nếu có execution-time parameter/pruning, biểu diễn plan có thể khác; kiểm tra nodes thực.

### Bài 20 — Pruning HASH

~~~sql
EXPLAIN
SELECT order_id, customer_id, amount
FROM partition_lab.orders_hash
WHERE customer_id = 101;
~~~

Có thể prune còn một HASH bucket. Nếu chỉ `WHERE order_id = 1`, không đủ thông tin xác định customer_id, thường phải xét các buckets phù hợp (có thể tất cả).

### Bài 21 — Seq Scan vẫn có thể prune tốt

Không. Nếu chỉ `events_2026_11` được scan, pruning đã loại các child khác. Việc chọn Seq Scan trên leaf nhỏ là quyết định cost-driven độc lập. Có thể cần local index khi leaf đủ lớn và predicate chọn lọc.

### Bài 22 — EXTRACT MONTH

`EXTRACT(MONTH FROM event_at)=11` lấy **November của mọi năm**, không phải riêng 2026. PostgreSQL cũng khó suy ra bounds trực tiếp của `event_at` từ mọi function expression. Dùng half-open range với cả ngày và timezone để biểu diễn đúng thời điểm cần truy vấn.

### Bài 23 — Timezone

`2026-10-31 20:00+00` tương ứng **01/11/2026 03:00** ở Việt Nam (+07). Nhưng parent chia tháng **UTC**, nên row vào **October** vì instant còn trước `2026-11-01 00:00+00`.

### Bài 24 — Parent PRIMARY KEY

Parent RANGE(event_at) có local child indexes. PK(event_id) trên parent không chứa partition key, không thể bảo đảm toàn cục theo quy tắc declarative partitioning. Lab dùng:

~~~sql
PRIMARY KEY (event_at, event_id)
~~~

Đây là composite PK hợp lệ, nhưng chỉ bảo đảm **cặp** unique; cùng event_id ở hai event_at khác nhau vẫn có thể tồn tại.

### Bài 25 — Unique event_id toàn hệ thống

Chưa đủ. Có thể dùng:

- Registry table không partitioned với `event_id PRIMARY KEY`, transaction bảo đảm registry và event cùng được ghi.
- ID generator toàn cục (sequence/UUID/Snowflake-like) kết hợp quy trình kiểm soát uniqueness nghiệp vụ, nhưng **không hiểu nhầm generator tự tạo global unique constraint** trên partitioned parent.
- Thiết kế lại partition key/PK hoặc dùng mô hình dữ liệu khác nếu invariant cần kiểm soát bằng database ở mọi trường hợp.

Chọn theo yêu cầu transaction, FKs và khả năng scale; không chỉ dựa trên xác suất UUID trùng thấp mà bỏ qua contract dữ liệu.

### Bài 26 — Index cho tenant + thời gian

~~~sql
CREATE INDEX idx_events_tenant_time_answer
ON partition_lab.events(tenant_id, event_at DESC);
~~~

Parent index là đối tượng logic; các leaf partitions có index vật lý tương ứng. Query theo tháng có thể prune trước và dùng index local sau. Nếu index tương đương đã tồn tại từ bài trước, không tạo index trùng chỉ để làm bài.

### Bài 27 — Concurrent index build

Không dùng trực tiếp `CREATE INDEX CONCURRENTLY` trên parent khi phiên bản PostgreSQL không hỗ trợ. Quy trình:

1. `CREATE INDEX ... ON ONLY parent` để có parent index metadata chưa valid/attach đủ.
2. `CREATE INDEX CONCURRENTLY` trên từng leaf phù hợp, **ngoài transaction block**.
3. `ALTER INDEX parent_index ATTACH PARTITION child_index` cho từng child đã valid và đúng definition.
4. Xác minh tất cả leaf indexes được attach và parent `indisvalid` đã đúng.
5. Nếu build lỗi, điều tra invalid index và xử lý trước retry.

### Bài 28 — Row movement

UPDATE partition key từ November sang December có thể di chuyển phiên bản hàng giữa leaf partitions; PostgreSQL phối hợp như delete+insert nội bộ. Tăng WAL, index maintenance, row locks và có thể gặp conflict; nếu December partition thiếu thì UPDATE lỗi. Chọn key ít thay đổi khi có thể.

### Bài 29 — ON CONFLICT

`ON CONFLICT(event_at,event_id)` chỉ nhận biết duplicate của **hai cột cùng giá trị**. Event_id giống nhưng timestamp khác không vi phạm composite PK. Muốn sự duy nhất event_id toàn cục cần mô hình/invariant riêng.

### Bài 30 — Subpartitioning

~~~sql
CREATE TABLE partition_lab.multi_demo (
    event_at DATE NOT NULL,
    tenant_id BIGINT NOT NULL,
    event_id BIGINT NOT NULL
)
PARTITION BY RANGE(event_at);

CREATE TABLE partition_lab.multi_demo_2026_11
PARTITION OF partition_lab.multi_demo
FOR VALUES FROM ('2026-11-01') TO ('2026-12-01')
PARTITION BY HASH(tenant_id);

CREATE TABLE partition_lab.multi_demo_2026_11_h0
PARTITION OF partition_lab.multi_demo_2026_11
FOR VALUES WITH(MODULUS 2, REMAINDER 0);

CREATE TABLE partition_lab.multi_demo_2026_11_h1
PARTITION OF partition_lab.multi_demo_2026_11
FOR VALUES WITH(MODULUS 2, REMAINDER 1);
~~~

12 tháng × 2 buckets = **24 leaf partitions**, cộng các partitioned parent levels và indexes. Truy vấn cần months ngoài November thì phải tạo thêm cấp 1/2 tương ứng.

### Bài 31 — Catalog

~~~sql
SELECT
    relid::regclass AS relation_name,
    parentrelid::regclass AS parent_name,
    isleaf,
    level
FROM pg_partition_tree('partition_lab.events'::regclass)
ORDER BY level, relid::text;
~~~

~~~sql
SELECT
    child.oid::regclass AS child_name,
    pg_get_expr(child.relpartbound, child.oid) AS bound
FROM pg_inherits AS i
JOIN pg_class AS child ON child.oid = i.inhrelid
WHERE i.inhparent = 'partition_lab.events'::regclass
ORDER BY child.oid;
~~~

Hai query xem cấu trúc/metadata; không cập nhật catalog trực tiếp.

### Bài 32 — CHECK trước ATTACH

Một bảng standalone có CHECK đã validate chứng minh mọi row thuộc `[2027-03-01,2027-04-01)` giúp PostgreSQL có thể **bỏ qua scan xác minh bound** khi ATTACH. Nó giảm thời gian khóa/scan của bước attach, nhưng việc tạo/validate constraint và index trước đó vẫn tốn chi phí.

### Bài 33 — DEFAULT có rows chồng bound

Không attach trực tiếp khi DEFAULT còn chứa rows thuộc partition mới. Cần:

1. Chuẩn bị partition standalone đúng schema/bound.
2. Điều phối writes để không phát sinh thêm rows chồng trong cutover.
3. Sao chép/di chuyển dữ liệu March sang standalone.
4. Kiểm tra completeness, uniqueness/constraints.
5. Xóa rows March khỏi DEFAULT sau khi bản sao an toàn và không bỏ lỡ writes.
6. ATTACH trong window kiểm soát; xác minh SELECT parent, tableoid và số rows.
7. Có cách khôi phục nếu bất kỳ bước nào thất bại.

Trên production có volume lớn, cần thiết kế cơ chế đồng bộ hai chiều/transaction/CDC phù hợp, không chỉ chạy một script DELETE + ATTACH ngắn.

### Bài 34 — DETACH khác DROP

`DETACH PARTITION` biến child thành standalone relation, dữ liệu vẫn tồn tại nhưng **SELECT parent không còn đọc nó**. `DROP TABLE` xóa relation và dữ liệu, có hậu quả phá hủy và cần backup/recovery plan. Retention thường DETACH/verify/archive trước rồi mới DROP.

### Bài 35 — DETACH CONCURRENTLY

Cần kiểm tra:

1. PostgreSQL version có hỗ trợ không.
2. Không chạy trong transaction block.
3. Parent có DEFAULT partition không (là giới hạn quan trọng).
4. Trạng thái detach đang pending sau lỗi, khả năng FINALIZE.
5. FK/dependencies, long transactions, lock waits và traffic.

**Lab events có DEFAULT**, nên câu DETACH CONCURRENTLY trên parent này không phải phương án chạy trực tiếp như một ví dụ an toàn.

### Bài 36 — HASH rebalancing

`MODULUS 4` chỉ có remainder 0..3; remainder 4 không hợp lệ. Muốn 8 buckets phải thiết kế chuyển từ bounds cũ sang mới, di chuyển/đồng bộ data, xử lý writes concurrent, index/constraints, WAL/locks và cutover. Một bảng HASH mới với 8 partitions rồi migrate/cutover có thể đơn giản để suy luận hơn thao tác chồng bounds trực tiếp.

### Bài 37 — ANALYZE parent

Autovacuum/autoanalyze leaf không nhất thiết làm thống kê parent luôn đại diện dữ liệu con mới. Khi thêm partition/bulk load thay đổi đáng kể, cân nhắc:

~~~sql
ANALYZE partition_lab.events;
~~~

Kết hợp thống kê từng leaf và đo EXPLAIN. Không chạy ANALYZE liên tục mà không biết chi phí/chu kỳ.

### Bài 38 — Retention 90 ngày và late arrivals

Trước khi DETACH/DROP:

- Xác định bound của partition đã **hoàn toàn** trước retention cutoff.
- Tính cửa sổ dữ liệu đến trễ 48 giờ/thoả thuận ingest khác.
- Kiểm tra writers/backfill đang có thể ghi vào ngày đó.
- Xác minh backup/archive và thời hạn giữ theo pháp lý.
- Kiểm tra FKs, query consumers, logical replication/replica.
- Có recovery plan nếu job chọn nhầm partition.
- Giám sát dữ liệu đến muộn sau khi đã đổi cấu trúc.

Không DROP một partition chỉ vì phần lớn dữ liệu trong đó đã quá hạn, khi còn hàng cần lưu.

### Bài 39 — Checklist partition mới

Một quy trình:

1. Tính đúng lower/upper bounds và timezone.
2. Kiểm tra partition hiện có để không tạo trùng/chồng.
3. Kiểm tra DEFAULT có rows trùng miền không.
4. Pre-create child/attach vào parent trước kỳ mới.
5. Xác minh child indexes, PK/constraints, tablespace/storage.
6. Thử INSERT một row lab có bounds sát biên trong transaction rồi rollback nếu phù hợp.
7. Kiểm tra `tableoid` và `EXPLAIN` pruning.
8. Giám sát DEFAULT, errors và lịch jobs; báo động khi partition thiếu.

### Bài 40 — Hai phương án cho nhiều tenants, query theo tenant + tháng

**Phương án A: RANGE theo tháng, local index theo tenant.**

- Khoảng 24 partitions cho retention 2 năm (chưa tính lịch tương lai/DEFAULT).
- Pruning theo tháng, index `(tenant_id,event_at)` trong những months liên quan.
- Dễ retention bằng detach/drop tháng hết hạn.
- Nếu một tháng có quá nhiều hàng, partition còn lớn nhưng vẫn có index.
- PK parent phải chứa partition key thời gian; global uniqueness theo order_id một mình không tự có.

**Phương án B: RANGE theo tháng rồi HASH theo tenant.**

- Nếu 24 tháng × 8 buckets = **192 leaf partitions** (chưa tính parent layers).
- Query lọc cả tháng và tenant có thể prune ở hai tầng.
- Data/queries có thể chia thành child nhỏ hơn, nhưng metadata/index count, lock và planning overhead tăng.
- Hot tenant vẫn tập trung vào một bucket mỗi tháng.
- Unique/PK phải được thiết kế với các partition key liên quan ở nhiều tầng; rất cần kiểm tra FKs và schema.
- Cần job tạo đủ 8 HASH leaf partitions cho **mỗi tháng**.

Một phương án HASH-only theo tenant có thể hữu ích cho equality lookups nhưng **không hỗ trợ retention theo tháng bằng DETACH/DROP hiệu quả**, nên thường kém phù hợp hơn khi yêu cầu xóa dữ liệu cũ là chính.

**Cách chọn:** benchmark truy vấn và tốc độ ingest trên dữ liệu tương đương, đo buffers/planning time, disk/index overhead, tốc độ retention và tác động production. Không chỉ chọn phương án nhiều partitions nhất.

---

## 46. Tài liệu và từ khóa nên tra cứu

Khi triển khai với một PostgreSQL major version cụ thể, nên đối chiếu:

- [PostgreSQL — Table Partitioning](https://www.postgresql.org/docs/current/ddl-partitioning.html): cú pháp, pruning, constraints, attach/detach và giới hạn declarative partitioning.
- [PostgreSQL — CREATE TABLE](https://www.postgresql.org/docs/current/sql-createtable.html): `PARTITION BY`, `PARTITION OF`, partition bounds.
- [PostgreSQL — ALTER TABLE](https://www.postgresql.org/docs/current/sql-altertable.html): `ATTACH PARTITION`, `DETACH PARTITION`, lock behavior và các hạn chế.
- [PostgreSQL — Partition Pruning](https://www.postgresql.org/docs/current/ddl-partitioning.html#DDL-PARTITION-PRUNING): cách planner/executor loại partitions.
- [PostgreSQL — CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html): partitioned indexes và concurrent builds.
- [PostgreSQL — EXPLAIN](https://www.postgresql.org/docs/current/sql-explain.html): đọc node scan/pruning và hiệu năng.
- [PostgreSQL — Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html): maintenance và statistics.

Đường dẫn `/current/` có thể trỏ tới PostgreSQL major version mới hơn version đang chạy. Khi cần xác minh cú pháp/giới hạn chi tiết, mở tài liệu cho **major version thực tế** của server và cả extension liên quan.

---

## 47. Tổng kết

**RANGE, LIST và HASH đều giúp quản lý một bảng logic thành nhiều partitions vật lý, nhưng chúng tối ưu những vấn đề khác nhau.**

- **RANGE:** phù hợp dữ liệu có thứ tự và vòng đời theo thời gian; dùng bounds **[lower, upper)**, cận cuối loại trừ. Mạnh về pruning theo khoảng và retention qua partition lifecycle.
- **LIST:** phù hợp một tập nhóm nghiệp vụ như region/country; các child khai báo tập giá trị rời rạc, có thể có NULL partition và DEFAULT. Cần giám sát case/giá trị mới, skew và di chuyển nhóm từ DEFAULT.
- **HASH:** phù hợp truy vấn equality theo key có nhiều distinct values và mong phân phối vào các buckets; dùng **MODULUS/REMAINDER của PostgreSQL hash**, không phải `key % N`. Không có DEFAULT và việc tăng số buckets cần kế hoạch rebalancing dữ liệu.
- **Parent/child:** parent là relation logic, leaf lưu row; `tableoid::regclass` giúp kiểm tra routing, `pg_partition_tree` giúp xem cấu trúc.
- **Pruning:** dựa vào partition key/bounds và predicate phù hợp, **không yêu cầu index**; trong leaf, local indexes mới quyết định cách tìm rows. Query không lọc key vẫn có thể quét nhiều partitions.
- **Khóa và uniqueness:** parent PK/UNIQUE phải bao gồm partition key columns theo quy tắc và không có global index vật lý mặc định xuyên partitions. Composite key có nghĩa khác uniqueness một cột.
- **Row movement:** UPDATE partition key có thể chuyển row sang child khác, với WAL, index maintenance và cạnh tranh phù hợp.
- **Index:** CREATE INDEX trên parent tạo partitioned index logic với local indexes; khi cần build online trên parent lớn, phải đánh giá quy trình concurrent index trên leaf rồi ATTACH.
- **Lifecycle:** pre-create partitions, quan sát DEFAULT, dùng ATTACH/DETACH có kế hoạch, hiểu lock/validation; không DROP dữ liệu retention khi chưa có backup và kiểm tra late arrivals.
- **Bảo trì:** mỗi leaf cần VACUUM/ANALYZE/index care; thống kê parent có thể cần ANALYZE thủ công. Quá nhiều partitions gây chi phí planning/catalog/locks.
- **Thiết kế nhiều tầng:** RANGE→HASH hoặc LIST→RANGE có thể giải bài toán nhiều chiều, nhưng số leaf partitions và các giới hạn PK/UNIQUE/maintenance tăng nhanh.
- **Hiệu năng:** đo `EXPLAIN (ANALYZE, BUFFERS)`, kiểm tra pruning, node scans, planning time, index usage, write cost và chi phí vận hành; không mặc định partitioning luôn thắng bảng thường với index phù hợp.

Quy trình thực tế: **mô tả truy vấn và retention → chọn RANGE/LIST/HASH theo partition key ổn định → thiết kế ranh giới và PK/UNIQUE → tạo partitions/indexes đúng → thử routing và pruning → giám sát dữ liệu, statistics và DEFAULT → tự động hóa pre-create/retention → triển khai ATTACH/DETACH có backup, timeout và kế hoạch phục hồi**.
