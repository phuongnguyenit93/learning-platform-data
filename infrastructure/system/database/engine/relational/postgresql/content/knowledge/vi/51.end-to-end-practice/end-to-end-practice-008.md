# Thiết kế dữ liệu theo thời gian với phân vùng và chính sách lưu giữ

Dữ liệu theo thời gian xuất hiện trong nhiều hệ thống PostgreSQL: sự kiện ứng dụng, log, giao dịch, lịch sử trạng thái, số đo thiết bị, audit trail và dữ liệu phân tích. Những bảng này thường tăng liên tục, được truy vấn theo khoảng thời gian và có thời hạn lưu giữ rõ ràng. Nếu thiết kế như một bảng không giới hạn, việc truy vấn, bảo trì, backup và xóa dữ liệu cũ có thể ngày càng tốn kém.

PostgreSQL declarative partitioning cho phép chia một bảng logic thành nhiều bảng vật lý theo khóa phân vùng. Với dữ liệu chuỗi thời gian, `RANGE` partitioning theo timestamp thường là lựa chọn tự nhiên: mỗi partition chứa một khoảng thời gian, chẳng hạn một ngày hoặc một tháng. Khi kết hợp với chính sách lưu giữ, đội ngũ có thể loại bỏ toàn bộ partition đã hết hạn nhanh hơn nhiều so với xóa từng dòng.

Thiết kế tốt cần giải quyết đồng thời cách chọn khóa và kích thước partition, cách truy vấn để partition pruning hoạt động, cách tạo partition đúng hạn, xử lý dữ liệu đến muộn, cách lưu trữ hoặc xóa dữ liệu hết hạn, và cách kiểm soát backup, quyền truy cập cùng yêu cầu pháp lý. Partitioning là công cụ quản lý dữ liệu; nó không tự động làm mọi truy vấn nhanh hơn hoặc tự thực thi chính sách retention.

## 1. Vì sao dữ liệu theo thời gian cần thiết kế riêng?

### 1.1. Đặc điểm của workload time-series

Một bảng time-series thường có các đặc điểm:

- Dữ liệu mới được ghi liên tục hoặc theo batch.
- Phần lớn truy vấn lọc theo một khoảng thời gian.
- Dữ liệu cũ ít được cập nhật, nhưng vẫn có thể cần truy vấn hoặc lưu trữ.
- Dung lượng tăng đều và có thể dự đoán từ tốc độ ingest.
- Một số dữ liệu có thời hạn lưu giữ theo ngày, tháng hoặc năm.
- Công việc bảo trì trên toàn bộ bảng ngày càng nặng khi bảng lớn.

Ví dụ bảng `telemetry.events` lưu sự kiện thiết bị. Ứng dụng thường hỏi số sự kiện của một thiết bị trong 24 giờ gần nhất, tổng hợp theo ngày hoặc kiểm tra lỗi trong một tuần. Một bảng duy nhất chứa nhiều năm dữ liệu sẽ khiến index và thao tác bảo trì ngày càng lớn.

### 1.2. Phân vùng giải quyết điều gì?

Partitioning tạo một bảng cha (partitioned table) đại diện cho giao diện logic và các bảng con (partitions) chứa dữ liệu thực tế. PostgreSQL định tuyến thao tác ghi tới partition phù hợp dựa trên partition key. Khi truy vấn có điều kiện phù hợp, planner có thể loại bỏ các partition không liên quan trước khi đọc dữ liệu; cơ chế này gọi là partition pruning.

Các lợi ích thường gặp:

- Truy vấn theo khoảng thời gian chỉ đọc các partition liên quan.
- Có thể áp dụng index, storage parameter và maintenance theo từng partition.
- Có thể detach, archive hoặc drop dữ liệu cũ theo lô.
- Có thể nạp dữ liệu theo từng khoảng thời gian và quản lý vòng đời rõ ràng.
- Có thể giới hạn phạm vi vacuum, analyze và index maintenance theo partition.

Các chi phí và giới hạn cần cân nhắc:

- Mỗi partition là một relation riêng, làm tăng metadata và số index.
- Quá nhiều partition có thể làm tăng thời gian planning, catalog overhead và độ phức tạp vận hành.
- Constraint unique trên partitioned table phải bao gồm partition key theo các quy tắc của PostgreSQL.
- DDL thêm, detach hoặc drop partition có thể cần lock và ảnh hưởng truy vấn đồng thời.
- Truy vấn không lọc theo partition key có thể vẫn phải xét nhiều hoặc toàn bộ partition.
- Autovacuum, analyze, quyền và monitoring cần được quan sát trên các partition vật lý.

Partitioning không thay thế index, thiết kế truy vấn hoặc capacity planning. Cần benchmark bằng dữ liệu và truy vấn đại diện trước khi quyết định số lượng và kích thước partition.

## 2. Chọn chiến lược phân vùng

PostgreSQL hỗ trợ ba kiểu declarative partitioning chính:

| Kiểu | Cách chia | Trường hợp thường dùng |
|---|---|---|
| `RANGE` | Theo khoảng giá trị liên tiếp, không chồng lấn | Thời gian, ngày, số thứ tự hoặc dải ID. |
| `LIST` | Theo danh sách giá trị rời rạc | Khu vực, loại sự kiện hoặc nhóm tenant có số lượng nhỏ. |
| `HASH` | Theo kết quả hash của khóa và số modulus/remainder | Phân tán dữ liệu khi không có range/list tự nhiên. |

### 2.1. RANGE theo thời gian

Với dữ liệu chuỗi thời gian, `RANGE` là cách phổ biến nhất. Mỗi partition chứa một khoảng nửa mở: bao gồm giá trị đầu, không bao gồm giá trị cuối.

Ví dụ partition tháng 11 năm 2026:

```sql
CREATE TABLE telemetry.events_2026_11
PARTITION OF telemetry.events
FOR VALUES FROM ('2026-11-01 00:00:00+00')
             TO ('2026-12-01 00:00:00+00');
```

Khoảng `[2026-11-01, 2026-12-01)` giúp một thời điểm đúng 00:00 ngày đầu tháng 12 thuộc partition tháng 12, không bị trùng ở hai partition. Khi tạo partition theo ngày hoặc giờ, cũng dùng nguyên tắc nửa mở này.

### 2.2. LIST theo nhóm

LIST phù hợp khi có một tập giá trị phân loại ổn định, chẳng hạn loại dữ liệu:

```sql
CREATE TABLE telemetry.alerts (
    occurred_at timestamptz NOT NULL,
    alert_id uuid NOT NULL,
    severity text NOT NULL,
    payload jsonb
) PARTITION BY LIST (severity);

CREATE TABLE telemetry.alerts_critical
PARTITION OF telemetry.alerts
FOR VALUES IN ('critical');

CREATE TABLE telemetry.alerts_warning
PARTITION OF telemetry.alerts
FOR VALUES IN ('warning');

CREATE TABLE telemetry.alerts_other
PARTITION OF telemetry.alerts
DEFAULT;
```

Với dữ liệu time-series lớn, LIST theo tenant hoặc severity có thể tạo nhiều partition nếu số giá trị tăng không kiểm soát. Khi vừa cần chia theo thời gian vừa theo nhóm, có thể dùng subpartitioning nhưng phải đánh giá số partition cuối cùng.

### 2.3. HASH theo khóa

HASH chia dữ liệu theo bucket, hữu ích khi muốn phân tán một bảng theo tenant hoặc key mà không có các range tự nhiên:

```sql
CREATE TABLE telemetry.events_by_tenant (
    tenant_id bigint NOT NULL,
    event_id uuid NOT NULL,
    occurred_at timestamptz NOT NULL,
    payload jsonb
) PARTITION BY HASH (tenant_id);

CREATE TABLE telemetry.events_by_tenant_0
PARTITION OF telemetry.events_by_tenant
FOR VALUES WITH (MODULUS 4, REMAINDER 0);

CREATE TABLE telemetry.events_by_tenant_1
PARTITION OF telemetry.events_by_tenant
FOR VALUES WITH (MODULUS 4, REMAINDER 1);

CREATE TABLE telemetry.events_by_tenant_2
PARTITION OF telemetry.events_by_tenant
FOR VALUES WITH (MODULUS 4, REMAINDER 2);

CREATE TABLE telemetry.events_by_tenant_3
PARTITION OF telemetry.events_by_tenant
FOR VALUES WITH (MODULUS 4, REMAINDER 3);
```

HASH không tạo thứ tự theo thời gian. Nếu yêu cầu retention theo tháng, HASH đơn thuần không giúp detach/drop dữ liệu hết hạn theo một mốc thời gian. Có thể dùng RANGE theo thời gian làm lớp ngoài và HASH làm lớp trong nếu có lý do rõ ràng.

## 3. Chọn partition key và kích thước partition

### 3.1. Chọn cột thời gian phù hợp

Các lựa chọn thường gặp:

- `occurred_at`: thời điểm sự kiện thực sự xảy ra.
- `ingested_at`: thời điểm hệ thống nhận hoặc ghi sự kiện.
- `created_at`: thời điểm bản ghi được tạo trong ứng dụng.
- `business_date`: ngày nghiệp vụ theo múi giờ hoặc lịch riêng.

Chọn cột phù hợp với cách truy vấn và chính sách retention. Nếu partition theo `occurred_at`, dữ liệu gửi đến muộn có thể phải ghi vào partition của một khoảng thời gian đã cũ. Nếu partition theo `ingested_at`, dữ liệu đến muộn được ghi vào partition hiện tại dễ hơn, nhưng truy vấn theo thời điểm sự kiện có thể không pruning tốt nếu thiếu điều kiện `ingested_at`.

Không nên chọn timestamp chỉ vì nó có sẵn. Hãy xác định rõ ý nghĩa thời gian, nguồn đồng hồ, múi giờ, khả năng sự kiện đến muộn và mốc bắt đầu retention.

### 3.2. Dùng timestamptz và thống nhất UTC

Với thời điểm thực tế trên toàn hệ thống, `timestamptz` thường phù hợp hơn `timestamp without time zone`. PostgreSQL lưu thời điểm theo dạng chuẩn hóa và hiển thị theo `TimeZone` của session. Dữ liệu không lưu tên múi giờ gốc; nếu cần biết múi giờ nghiệp vụ ban đầu, hãy lưu riêng mã vùng hoặc thông tin đó.

Một quy ước vận hành dễ kiểm soát là tạo partition theo biên tháng UTC. Khi đó, một ngày nghiệp vụ tại múi giờ khác có thể không trùng với biên partition. Nếu retention hoặc báo cáo phải theo lịch địa phương, cần chuyển đổi mốc thời gian rõ ràng khi tạo boundary và khi truy vấn.

Ví dụ xác định đầu tháng UTC:

```sql
SELECT date_trunc('month', now() AT TIME ZONE 'UTC') AS utc_month_start;
```

Tránh tạo boundary từ chuỗi timestamp không có offset khi session có thể dùng múi giờ khác. Ghi offset `+00` trong DDL hoặc tạo giá trị `timestamptz` rõ ràng.

### 3.3. Chọn partition theo ngày, tháng hay quý

Không có một kích thước đúng cho mọi workload. Chọn chu kỳ dựa trên:

- Số dòng và dung lượng phát sinh mỗi ngày.
- Khối lượng truy vấn và khoảng thời gian thường truy cập.
- Mức chi tiết của retention và archive.
- Số partition dự kiến trong vòng đời dữ liệu.
- Thời gian tạo index, vacuum, analyze và backup.
- Giới hạn catalog, planning time và năng lực quản trị.

| Chu kỳ | Ưu điểm | Chi phí/rủi ro |
|---|---|---|
| Theo giờ | Dễ xóa/archive rất chi tiết; mỗi partition nhỏ | Số partition tăng rất nhanh, overhead cao. |
| Theo ngày | Hợp với ingest lớn và retention theo ngày | Có thể có hàng nghìn partition sau nhiều năm. |
| Theo tháng | Dễ quản lý, số partition vừa phải, hợp retention tháng/năm | Partition có thể lớn nếu ingest rất cao; xóa dữ liệu theo ngày không chính xác bằng. |
| Theo quý/năm | Ít partition và đơn giản | Partition lớn, vacuum/index/restore từng phần có thể lâu; retention thô. |

Ví dụ, một bảng nhận vài triệu dòng mỗi ngày có thể cần partition theo ngày hoặc tháng tùy kích thước dòng và truy vấn. Một bảng audit có lưu lượng thấp có thể chỉ cần partition theo tháng hoặc quý. Hãy benchmark thời gian tạo index và vacuum trên partition dự kiến.

### 3.4. Tránh over-partitioning

Quá nhiều partition làm tăng số relation, index, catalog entry, thời gian planning và công việc quản trị. Một truy vấn không có điều kiện thời gian có thể phải xét rất nhiều partition. Mỗi partition cũng cần index và maintenance phù hợp.

Chỉ thêm subpartitioning khi có lợi ích đo được, ví dụ giảm kích thước index theo tenant hoặc giảm contention trên một partition nóng. Không chia theo tenant hàng trăm nghìn giá trị nếu một thiết kế RANGE theo thời gian cùng index tenant có thể đáp ứng.

## 4. Thiết kế bảng partitioned trong PostgreSQL

### 4.1. Tạo bảng cha RANGE theo thời gian

Ví dụ bảng sự kiện telemetry:

```sql
CREATE SCHEMA IF NOT EXISTS telemetry;

CREATE TABLE telemetry.events (
    occurred_at timestamptz NOT NULL,
    event_id uuid NOT NULL,
    tenant_id bigint NOT NULL,
    device_id bigint NOT NULL,
    event_type text NOT NULL,
    value double precision,
    attributes jsonb,
    PRIMARY KEY (occurred_at, event_id)
) PARTITION BY RANGE (occurred_at);
```

Partition key là `occurred_at`. Khóa chính bao gồm cả `occurred_at` và `event_id`. PostgreSQL yêu cầu unique constraint hoặc primary key trên partitioned table phải chứa tất cả cột partition key, để việc kiểm tra uniqueness có thể được thực hiện trên các partition mà không cần global index.

Nếu yêu cầu nghiệp vụ cần `event_id` duy nhất toàn bảng, constraint trên chỉ bảo đảm cặp `(occurred_at, event_id)` là duy nhất. Không có global unique index thông thường trên mọi partition để bảo đảm `event_id` riêng lẻ không lặp giữa các partition. Có thể dùng UUID đủ mạnh để giảm xác suất trùng, sequence chung với kiểm soát ở tầng ứng dụng, hoặc một bảng registry không partition để enforce uniqueness toàn cục. Phải chọn giải pháp theo yêu cầu chính xác, không giả định primary key ghép đã bảo đảm ID riêng lẻ.

### 4.2. Tạo các partition tháng

```sql
CREATE TABLE telemetry.events_2026_11
PARTITION OF telemetry.events
FOR VALUES FROM ('2026-11-01 00:00:00+00')
             TO ('2026-12-01 00:00:00+00');

CREATE TABLE telemetry.events_2026_12
PARTITION OF telemetry.events
FOR VALUES FROM ('2026-12-01 00:00:00+00')
             TO ('2027-01-01 00:00:00+00');

CREATE TABLE telemetry.events_2027_01
PARTITION OF telemetry.events
FOR VALUES FROM ('2027-01-01 00:00:00+00')
             TO ('2027-02-01 00:00:00+00');
```

Tên partition nên thể hiện rõ khoảng thời gian, dùng định dạng nhất quán như `events_YYYY_MM`. Khi xem log, catalog hoặc dashboard, người vận hành có thể nhận biết partition mà không cần giải mã tên tùy ý.

### 4.3. Tạo index trên bảng cha

Khi tạo partitioned index trên bảng cha, PostgreSQL tạo index tương ứng trên các partition hiện có và gắn index cho partition được tạo sau đó:

```sql
CREATE INDEX events_tenant_time_idx
ON telemetry.events (tenant_id, occurred_at DESC);

CREATE INDEX events_type_time_idx
ON telemetry.events (event_type, occurred_at DESC);
```

Index cần phản ánh truy vấn thực tế. Không nên tạo quá nhiều index trên bảng ingest-heavy vì mỗi insert phải duy trì index tương ứng trên partition. Với bảng rất lớn và dữ liệu được ghi gần theo thứ tự thời gian, BRIN có thể tiết kiệm dung lượng hơn B-tree cho một số truy vấn range:

```sql
CREATE INDEX events_occurred_at_brin_idx
ON telemetry.events
USING brin (occurred_at)
WITH (pages_per_range = 128);
```

BRIN có hiệu quả khi giá trị trong một vùng page tương quan với vị trí vật lý của hàng. Nếu dữ liệu đến muộn và thứ tự ghi không còn tương quan với thời gian sự kiện, hiệu quả có thể giảm. Cần đo bằng `EXPLAIN (ANALYZE, BUFFERS)`.

### 4.4. Partition-specific storage parameters

Có thể đặt storage parameter cho từng partition. Ví dụ giảm fillfactor hoặc thay đổi autovacuum scale factor cho một partition có update pattern đặc biệt:

```sql
ALTER TABLE telemetry.events_2026_11 SET (
    autovacuum_vacuum_scale_factor = 0.05,
    autovacuum_analyze_scale_factor = 0.02
);
```

Các giá trị này là ví dụ, cần dựa trên số liệu. Mỗi partition là một relation vật lý nên có thể có reloptions riêng. Hãy áp dụng chính sách cho partition mới khi tạo và theo dõi để tránh partition cũ, mới có hành vi bảo trì quá khác nhau.

### 4.5. Partition DEFAULT

Có thể tạo một partition `DEFAULT` để nhận giá trị không khớp partition nào:

```sql
CREATE TABLE telemetry.events_default
PARTITION OF telemetry.events DEFAULT;
```

DEFAULT giúp tránh lỗi insert khi thiếu partition, nhưng có thể che giấu lỗi automation tạo partition. Nó cũng làm việc thêm partition mới phức tạp hơn: PostgreSQL phải bảo đảm dữ liệu trong DEFAULT không thuộc khoảng mới. Nếu có dữ liệu trùng khoảng, cần di chuyển chúng và thêm constraint chứng minh vùng đó trống trước khi attach partition mới; thao tác xác minh có thể quét bảng và cần lock.

Nếu dùng DEFAULT, hãy giám sát số dòng và cảnh báo ngay khi có dữ liệu đi vào. Với hệ thống cần kiểm soát chặt, có thể không tạo DEFAULT để insert thiếu partition thất bại rõ ràng, sau đó xử lý lỗi ở tầng ingest.

## 5. Partition pruning và cách viết truy vấn

### 5.1. Partition pruning là gì?

Partition pruning cho phép planner hoặc executor bỏ qua partition có bounds không giao với điều kiện truy vấn. Ví dụ:

```sql
SELECT event_type, count(*)
FROM telemetry.events
WHERE occurred_at >= TIMESTAMPTZ '2026-11-01 00:00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-12-01 00:00:00+00'
  AND tenant_id = 42
GROUP BY event_type;
```

Với điều kiện thời gian trên, planner chỉ cần xét partition tháng 11 năm 2026. Điều kiện `tenant_id` tiếp tục giúp sử dụng index phù hợp bên trong partition.

### 5.2. Dùng khoảng nửa mở

Nên dùng `>= start` và `< end`:

```sql
WHERE occurred_at >= TIMESTAMPTZ '2026-11-01 00:00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-12-01 00:00:00+00'
```

Tránh dùng `BETWEEN` cho ranh giới partition liền nhau vì `BETWEEN` bao gồm cả hai đầu. Nếu hai khoảng cùng bao gồm thời điểm ranh giới, một sự kiện đúng tại thời điểm đó có thể bị đếm hai lần khi ghép kết quả nhiều khoảng.

### 5.3. Tránh bọc partition key trong biểu thức không cần thiết

Điều kiện trực tiếp trên partition key thường dễ pruning nhất. Ví dụ:

```sql
-- Tốt: điều kiện trực tiếp trên occurred_at.
SELECT *
FROM telemetry.events
WHERE occurred_at >= TIMESTAMPTZ '2026-11-01 00:00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-12-01 00:00:00+00';
```

Nếu viết:

```sql
SELECT *
FROM telemetry.events
WHERE date(occurred_at) = DATE '2026-11-14';
```

planner có thể không suy ra được khoảng partition từ biểu thức này trong mọi tình huống. Nên chuyển điều kiện thành khoảng timestamp cụ thể, có xét múi giờ:

```sql
SELECT *
FROM telemetry.events
WHERE occurred_at >= TIMESTAMPTZ '2026-11-14 00:00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-11-15 00:00:00+00';
```

### 5.4. Kiểm tra kế hoạch thực thi

Dùng `EXPLAIN` để xác nhận partition pruning:

```sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT count(*)
FROM telemetry.events
WHERE occurred_at >= TIMESTAMPTZ '2026-11-01 00:00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-12-01 00:00:00+00'
  AND tenant_id = 42;
```

Kế hoạch có thể hiển thị `Seq Scan`, `Index Scan`, `Bitmap Heap Scan` trên partition cụ thể hoặc `Append`/`Parallel Append` chứa các partition được chọn. Với prepared statement hoặc parameterized query, một số pruning có thể diễn ra lúc execution thay vì lúc planning. Xem `Subplans Removed` hoặc các subplan bị bỏ qua trong output phù hợp với phiên bản.

### 5.5. Bật/tắt partition pruning và partition-wise operations

Các tham số như `enable_partition_pruning`, `enable_partitionwise_join` và `enable_partitionwise_aggregate` ảnh hưởng planner. Partition-wise join/aggregate có thể chia phép xử lý theo từng cặp partition tương ứng, nhưng cũng làm tăng số subplan và bộ nhớ planning. Không bật chỉ vì bảng đã partition; benchmark truy vấn thật và giữ cấu hình mặc định trừ khi có bằng chứng rõ ràng.

## 6. Quản lý partition theo lịch

### 6.1. Tạo partition trước khi dữ liệu tới

Không đợi đến lúc insert lỗi mới tạo partition. Nên có job định kỳ tạo trước một số partition tương lai, chẳng hạn 2–3 tháng. Khoảng đệm phụ thuộc khả năng triển khai, lịch ingest và quy trình thay đổi schema.

Ví dụ tạo thủ công partition tháng kế tiếp:

```sql
CREATE TABLE telemetry.events_2027_02
PARTITION OF telemetry.events
FOR VALUES FROM ('2027-02-01 00:00:00+00')
             TO ('2027-03-01 00:00:00+00');
```

Nếu dùng automation, cần:

- Tính boundary theo múi giờ chuẩn đã thống nhất.
- Dùng tên partition có quy tắc cố định.
- Kiểm tra partition đã tồn tại và bounds thực tế trước khi bỏ qua.
- Báo lỗi khi tạo partition thất bại.
- Tạo index, storage parameter, quyền và policy cần thiết.
- Cảnh báo khi chỉ còn ít partition tương lai.
- Kiểm tra job chạy lặp lại an toàn và không tạo partition trùng.

`CREATE TABLE IF NOT EXISTS` có thể tránh lỗi khi relation cùng tên đã tồn tại, nhưng không xác minh relation đó có bounds và cấu trúc đúng. Automation vẫn cần kiểm tra metadata.

### 6.2. Ví dụ tạo trước ba partition tháng theo UTC

Đoạn `DO` sau minh họa cách tạo partition cho tháng hiện tại và hai tháng kế tiếp, dùng biên UTC rõ ràng:

```sql
DO $$
DECLARE
    v_month date := date_trunc('month', now() AT TIME ZONE 'UTC')::date;
    v_start timestamptz;
    v_end timestamptz;
    v_name text;
    i integer;
BEGIN
    FOR i IN 0..2 LOOP
        v_start := make_timestamptz(
            extract(year FROM v_month)::integer,
            extract(month FROM v_month)::integer,
            1, 0, 0, 0, 'UTC'
        );
        v_end := v_start + interval '1 month';
        v_name := 'events_' || to_char(v_month, 'YYYY_MM');

        EXECUTE format(
            'CREATE TABLE IF NOT EXISTS telemetry.%I '
            'PARTITION OF telemetry.events '
            'FOR VALUES FROM (%L) TO (%L)',
            v_name, v_start, v_end
        );

        v_month := (v_month + interval '1 month')::date;
    END LOOP;
END
$$;
```

Đoạn mã là ví dụ để minh họa cách sinh DDL an toàn với `format()` và identifier `%I`, literal `%L`. Trong production, cần thêm bước kiểm tra bounds của partition đã tồn tại, xử lý lỗi, ghi log và xác nhận quyền thực thi. Chạy dưới role có quyền phù hợp trên schema và bảng cha.

### 6.3. Xử lý dữ liệu đến muộn

Nếu partition theo `occurred_at`, một sự kiện có thể đến sau nhiều ngày hoặc nhiều tháng. Ví dụ, thiết bị offline gửi lại sự kiện từ tháng trước. Hệ thống phải quyết định:

- Giữ các partition lịch sử mở để nhận late arrival trong một khoảng thời gian cho phép.
- Tạo lại partition lịch sử nếu partition đã detach nhưng chưa xóa.
- Ghi vào staging/late-arrival table rồi xử lý theo batch.
- Từ chối dữ liệu đã vượt quá cửa sổ cho phép và ghi nhận lỗi rõ ràng.
- Đưa dữ liệu quá cũ vào kho archive riêng.

Không nên dùng DEFAULT partition như kho chứa dữ liệu đến muộn vô hạn. Nếu dữ liệu cũ vào DEFAULT, việc attach lại partition đúng thời gian có thể cần di chuyển dữ liệu và kiểm tra constraint.

Nếu partition theo `ingested_at`, late arrival dễ ghi hơn nhưng truy vấn theo thời gian sự kiện cần thêm chiến lược index hoặc dữ liệu tổng hợp. Lựa chọn partition key là một quyết định về ngữ nghĩa dữ liệu và workload, không chỉ là quyết định DDL.

### 6.4. Đưa partition vào trạng thái chỉ đọc

Các partition lịch sử ít thay đổi có thể được bảo vệ bằng quyền chỉ đọc hoặc chuyển sang tablespace/storage phù hợp nếu nền tảng hỗ trợ. Ví dụ:

```sql
REVOKE INSERT, UPDATE, DELETE
ON telemetry.events_2025_01
FROM telemetry_writer;

GRANT SELECT
ON telemetry.events_2025_01
TO telemetry_reader;
```

Nếu ứng dụng chỉ có quyền trên bảng cha và quyền được kế thừa theo cách quản lý hiện tại, cần kiểm tra lại quyền thực tế trên parent và partition. Phân quyền riêng từng partition có thể bị thay đổi ngoài dự kiến khi tạo partition mới; nên quản lý bằng automation và kiểm tra định kỳ.

## 7. Thiết kế chính sách lưu giữ dữ liệu

Retention policy xác định dữ liệu nào được giữ, trong bao lâu, ở đâu, ai được truy cập và cách xử lý khi hết hạn. Partitioning giúp thực thi retention theo nhóm dữ liệu, nhưng chính sách phải bắt đầu từ yêu cầu nghiệp vụ và pháp lý.

### 7.1. Xác định thời hạn theo loại dữ liệu

Không nên áp dụng cùng một thời hạn cho mọi dữ liệu. Ví dụ:

| Loại dữ liệu | Chính sách minh họa | Cách xử lý |
|---|---|---|
| Metrics vận hành chi tiết | 30–90 ngày | Giữ trong PostgreSQL để truy vấn nhanh, sau đó xóa hoặc aggregate. |
| Event phục vụ điều tra | 6–12 tháng | Archive trước khi xóa nếu cần truy vết. |
| Audit log | Theo yêu cầu pháp lý/chính sách tổ chức | Lưu trữ có kiểm soát, chống sửa đổi và có audit access. |
| Dữ liệu phân tích tổng hợp | Nhiều năm nếu cần | Giữ aggregate đã giảm độ chi tiết, theo chính sách riêng. |
| Dữ liệu cá nhân | Theo mục đích và nghĩa vụ xóa | Có quy trình xóa hoặc ẩn danh xuyên hệ thống và bản sao. |

Các khoảng thời gian chỉ là ví dụ, không phải khuyến nghị pháp lý. Chủ sở hữu dữ liệu, bộ phận pháp chế và bảo mật phải xác định thời hạn theo mục đích xử lý, hợp đồng và quy định áp dụng.

### 7.2. Phân biệt hot, warm và cold data

Một mô hình lưu trữ nhiều tầng:

```text
Hot data
  - Dữ liệu mới, truy vấn thường xuyên
  - PostgreSQL primary/replica, index đầy đủ
          |
          v
Warm data
  - Dữ liệu ít truy cập nhưng cần truy vấn
  - Partition lịch sử, storage tối ưu chi phí hoặc database archive
          |
          v
Cold data
  - Dữ liệu hiếm khi truy cập, cần lưu dài hạn
  - Object storage, file columnar hoặc kho lưu trữ chuyên dụng
          |
          v
Expiration
  - Xóa khi hết thời hạn và không còn legal hold
  - Lưu bằng chứng theo chính sách
```

Việc chuyển tầng cần xác định định dạng, schema version, mã hóa, khả năng truy vấn, chi phí restore và thời gian lấy lại dữ liệu. Cold archive không còn nằm trong transaction của PostgreSQL, vì vậy ứng dụng phải có quy trình truy xuất riêng.

### 7.3. Xác định mốc bắt đầu retention

Thời hạn lưu giữ có thể được tính từ:

- Thời điểm sự kiện xảy ra.
- Thời điểm dữ liệu được ingest.
- Thời điểm hợp đồng kết thúc.
- Thời điểm hồ sơ được đóng.
- Thời điểm kết thúc quan hệ khách hàng.

Chọn sai mốc có thể xóa dữ liệu quá sớm hoặc giữ lâu hơn yêu cầu. Với event time-series, retention theo `occurred_at` thường phù hợp với dữ liệu vận hành; với hồ sơ nghiệp vụ, retention có thể gắn với trạng thái hoặc ngày kết thúc thay vì timestamp ingest.

### 7.4. Legal hold và ngoại lệ

Trước khi detach/drop partition, phải xác định partition có chứa dữ liệu đang chịu legal hold, điều tra, khiếu nại hoặc nghĩa vụ lưu trữ đặc biệt không. Nếu một phần dữ liệu cần giữ lâu hơn phần còn lại, partition theo thời gian có thể chưa đủ để đáp ứng; cần tách dữ liệu hoặc dùng archive/registry theo hồ sơ.

Retention automation nên có bước kiểm tra hold và phê duyệt. Không xóa dữ liệu chỉ dựa vào tên partition hoặc tuổi partition nếu chính sách có ngoại lệ theo khách hàng hoặc hồ sơ.

## 8. Thực thi retention bằng detach, archive và drop

### 8.1. Vì sao drop partition hiệu quả hơn DELETE hàng loạt?

Để xóa dữ liệu cũ bằng SQL thông thường, có thể chạy:

```sql
DELETE FROM telemetry.events
WHERE occurred_at < TIMESTAMPTZ '2025-01-01 00:00:00+00';
```

Lệnh này có thể tạo lượng dead tuple lớn, phát sinh WAL, giữ lock trong thời gian dài và làm autovacuum phải xử lý khối lượng lớn. Với bảng partition theo thời gian, nếu toàn bộ partition nằm trước mốc retention, có thể detach hoặc drop relation tương ứng. Thao tác này thường nhanh hơn nhiều vì không cần xóa từng hàng.

Chỉ drop partition khi toàn bộ dữ liệu trong partition đã hết hạn. Nếu mốc retention nằm giữa một partition, phải xử lý phần dữ liệu trong partition đó bằng cách tạo partition mới/di chuyển dữ liệu hoặc xóa theo batch có kiểm soát.

### 8.2. Detach partition trước khi xóa

Ví dụ detach partition cũ:

```sql
ALTER TABLE telemetry.events
DETACH PARTITION telemetry.events_2025_01;
```

Sau khi detach, bảng `telemetry.events_2025_01` vẫn tồn tại như một bảng độc lập nhưng không còn là partition của bảng cha. Có thể kiểm tra, export, chuyển tablespace hoặc xóa theo quy trình retention.

Ở các phiên bản PostgreSQL hỗ trợ, có thể dùng `DETACH PARTITION CONCURRENTLY` để giảm mức lock trên bảng cha:

```sql
ALTER TABLE telemetry.events
DETACH PARTITION telemetry.events_2025_01 CONCURRENTLY;
```

Lệnh `CONCURRENTLY` có các giới hạn theo phiên bản và không được chạy bên trong transaction block. Nếu thao tác bị gián đoạn ở trạng thái pending detach, PostgreSQL cung cấp dạng `DETACH PARTITION ... FINALIZE` để hoàn tất theo điều kiện phù hợp. Cần đọc tài liệu đúng major version và kiểm tra các hạn chế, đặc biệt nếu bảng cha có DEFAULT partition.

### 8.3. Archive partition rồi drop

Sau khi detach, có thể lưu dữ liệu vào kho archive trước khi xóa bảng:

```sql
-- Minh họa xuất dữ liệu qua client psql về nơi lưu trữ được kiểm soát.
\copy telemetry.events_2025_01 TO 'events_2025_01.csv' WITH (FORMAT csv, HEADER true)
```

`\copy` là lệnh của `psql`, đường dẫn file nằm trên máy chạy client. Với dữ liệu lớn, nên cân nhắc định dạng nén hoặc columnar và công cụ truyền đến object storage; CSV có thể lớn và không giữ đầy đủ kiểu/metadata database.

Sau khi xác minh archive đọc lại được và đã ghi nhận metadata, có thể xóa bảng đã detach:

```sql
DROP TABLE telemetry.events_2025_01;
```

Nếu không cần archive và chính sách cho phép xóa trực tiếp, có thể dùng quy trình detach rồi drop. Luôn xác nhận tên partition, bounds, legal hold, backup và phê duyệt trước khi xóa. DDL drop là thao tác không thể hoàn tác bằng rollback sau khi transaction đã commit.

### 8.4. Lưu giữ bằng partition detach thay vì drop ngay

Một số hệ thống cần dữ liệu lịch sử nhưng không muốn để nó trong bảng hot. Có thể detach partition rồi:

- Giữ bảng độc lập trong database archive.
- Chuyển sang tablespace trên storage rẻ hơn nếu hạ tầng hỗ trợ.
- Export sang object storage dưới định dạng Parquet hoặc định dạng phù hợp với hệ thống phân tích.
- Giữ metadata schema, checksum, thời gian export và phiên bản pipeline.
- Cấp quyền đọc riêng cho nhóm điều tra hoặc compliance.

Detach chỉ thay đổi quan hệ partition; nó không tự di chuyển dữ liệu sang storage khác hoặc tự giảm hóa đơn. Cần thực hiện bước archive riêng và tính chi phí lưu trữ, truy xuất.

### 8.5. Xử lý retention theo batch cho dữ liệu không trùng ranh giới

Nếu partition chứa cả dữ liệu còn hạn và hết hạn, có thể xóa theo batch:

```sql
WITH batch AS (
    SELECT ctid
    FROM telemetry.events_2025_02
    WHERE occurred_at < TIMESTAMPTZ '2025-02-15 00:00:00+00'
    LIMIT 10000
)
DELETE FROM telemetry.events_2025_02 AS e
USING batch
WHERE e.ctid = batch.ctid;
```

Lặp lại theo job có giới hạn, commit từng batch và theo dõi vacuum/WAL. `ctid` chỉ phù hợp làm định danh tạm trong cùng một statement; không lưu `ctid` qua transaction hoặc dùng như khóa nghiệp vụ. Có thể dùng khóa chính thay thế nếu cần xử lý rõ ràng hơn.

Nếu retention luôn có mốc chính xác và dữ liệu lớn, hãy cân nhắc chọn partition nhỏ hơn hoặc tạo partition theo ngày để các thao tác drop khớp ranh giới. Cân bằng lợi ích với số lượng partition.

## 9. Quản lý index, vacuum và thống kê theo partition

### 9.1. Index được tạo trên bảng cha

Index trên partitioned table thường là partitioned index không chứa dữ liệu trực tiếp. Mỗi partition có index vật lý tương ứng. Khi tạo partition mới, PostgreSQL gắn index tương ứng nếu partitioned index trên parent đã được tạo.

Kiểm tra index theo partition:

```sql
SELECT
    parent_ns.nspname AS parent_schema,
    parent.relname AS parent_table,
    child_ns.nspname AS partition_schema,
    child.relname AS partition_name,
    child_index.relname AS partition_index
FROM pg_inherits AS inh
JOIN pg_class AS parent
    ON parent.oid = inh.inhparent
JOIN pg_namespace AS parent_ns
    ON parent_ns.oid = parent.relnamespace
JOIN pg_class AS child
    ON child.oid = inh.inhrelid
JOIN pg_namespace AS child_ns
    ON child_ns.oid = child.relnamespace
JOIN pg_index AS idx
    ON idx.indrelid = parent.oid
JOIN pg_class AS parent_index
    ON parent_index.oid = idx.indexrelid
JOIN pg_inherits AS index_inh
    ON index_inh.inhparent = parent_index.oid
   AND index_inh.inhrelid IN (
       SELECT indexrelid
       FROM pg_index
       WHERE indrelid = child.oid
   )
JOIN pg_class AS child_index
    ON child_index.oid = index_inh.inhrelid
WHERE parent.oid = 'telemetry.events'::regclass
ORDER BY child.relname, child_index.relname;
```

Trong vận hành thường ngày, có thể dùng `\d+ telemetry.events` trong `psql` hoặc truy vấn catalog phù hợp với phiên bản để xem partition và index. Nếu tạo index riêng trên một partition rồi muốn gắn vào partitioned index, cần tuân thủ quy trình `CREATE INDEX ... ON ONLY` và `ALTER INDEX ... ATTACH PARTITION` tương ứng.

### 9.2. Tạo index concurrent trên bảng đang hoạt động

`CREATE INDEX CONCURRENTLY` không thể chạy trực tiếp trên partitioned parent theo cách thông thường. Một quy trình phổ biến là tạo index concurrently trên từng partition, sau đó tạo partitioned index trên parent với `ON ONLY` và attach các index con tương ứng. Cú pháp và khả năng phụ thuộc phiên bản; cần kiểm tra tài liệu trước khi áp dụng.

Ví dụ khung thao tác:

```sql
CREATE INDEX CONCURRENTLY events_2026_11_tenant_time_idx
ON telemetry.events_2026_11 (tenant_id, occurred_at DESC);

CREATE INDEX events_tenant_time_idx
ON ONLY telemetry.events (tenant_id, occurred_at DESC);

ALTER INDEX telemetry.events_tenant_time_idx
ATTACH PARTITION telemetry.events_2026_11_tenant_time_idx;
```

Lặp lại cho từng partition. Parent index chưa được đánh dấu hợp lệ cho đến khi các partition cần thiết đã được attach. Nếu có partition mới trong thời gian triển khai, phải đưa nó vào quy trình.

### 9.3. Autovacuum và analyze

Mỗi partition có storage và thống kê riêng. Autovacuum có thể vacuum/analyze các partition vật lý dựa trên hoạt động của chúng. Partition mới chỉ ghi insert có thể cần insert-triggered vacuum để freeze tuple; partition lịch sử ít thay đổi vẫn có thể cần freeze theo tuổi XID.

Một điểm quan trọng: autovacuum không tự động chạy `ANALYZE` trên partitioned parent theo cách thông thường vì parent không lưu tuple. Khi dữ liệu trong các partition thay đổi đáng kể, có thể cần chạy `ANALYZE` thủ công trên bảng cha để cập nhật thống kê kế thừa cho planner:

```sql
ANALYZE telemetry.events;
```

Đồng thời, theo dõi từng partition qua `pg_stat_all_tables`, `pg_class` và `pg_stat_progress_vacuum`. Không giả định rằng parent có `last_autovacuum` là phản ánh đầy đủ tình trạng mọi partition.

### 9.4. Giám sát kích thước và số lượng partition

```sql
SELECT
    relid::regclass AS partition_name,
    pg_size_pretty(pg_relation_size(relid)) AS heap_size,
    pg_size_pretty(pg_indexes_size(relid)) AS indexes_size,
    pg_size_pretty(pg_total_relation_size(relid)) AS total_size
FROM pg_partition_tree('telemetry.events')
WHERE isleaf
ORDER BY relid::regclass::text;
```

`pg_partition_tree()` cung cấp cây partition ở các phiên bản hỗ trợ. Có thể dùng `pg_total_relation_size()` để tính cả heap, index và TOAST. Nên theo dõi số partition, kích thước lớn nhất/nhỏ nhất, partition rỗng, partition thiếu trong tương lai và partition DEFAULT.

## 10. Bảo mật và quyền truy cập theo partition

Ứng dụng thường truy cập bảng cha thay vì truy cập trực tiếp partition. Cần quản lý quyền trên parent và kiểm tra quyền thực tế sau khi tạo partition mới. PostgreSQL hỗ trợ row-level security (RLS) trên partitioned table; policy ở parent được áp dụng cho truy vấn qua parent theo quy tắc RLS. Tuy nhiên, quyền và policy trên partition khi truy cập trực tiếp cần được xem xét riêng.

Nếu ứng dụng không cần truy cập partition trực tiếp, không cấp quyền rộng trên schema chứa các bảng con. Với archive partition đã detach, có thể chuyển sang schema riêng và cấp quyền chỉ đọc cho nhóm được phép.

Retention cũng là một thao tác nhạy cảm. Nên dùng role chuyên trách có quyền cần thiết, kiểm tra bounds và legal hold, ghi log người thực hiện và yêu cầu phê duyệt cho thao tác drop hàng loạt. Không để ứng dụng ingest có quyền tự drop partition.

## 11. Kiểm thử thiết kế partition và retention

Trước khi triển khai production, cần kiểm thử ít nhất các tình huống:

1. Insert ở đầu và cuối mỗi partition boundary.
2. Insert đúng thời điểm `TO` của partition cũ để xác nhận dữ liệu đi vào partition kế tiếp.
3. Insert khi thiếu partition và xác nhận hành vi mong muốn (lỗi rõ ràng hoặc vào DEFAULT).
4. Truy vấn theo một ngày, một tháng và nhiều tháng; xác nhận pruning qua `EXPLAIN`.
5. Truy vấn không có điều kiện thời gian để đo chi phí toàn bộ partition.
6. Late-arriving event thuộc partition đã đóng hoặc đã archive.
7. Tạo partition mới trong lúc ứng dụng đang ghi.
8. Detach/drop partition khi có query đang chạy và đo lock/downtime.
9. Archive partition, đọc lại dữ liệu và so sánh số dòng/checksum.
10. Restore từ backup/PITR để xác định partition đã drop có thể phục hồi tới đâu.
11. Kiểm tra quyền trên parent, child, DEFAULT và archive schema.
12. Kiểm tra autovacuum, analyze và tuổi XID trên các partition có workload khác nhau.

### 11.1. Kiểm tra ranh giới

```sql
INSERT INTO telemetry.events (
    occurred_at, event_id, tenant_id, device_id, event_type, value
)
VALUES
    ('2026-11-30 23:59:59.999+00', gen_random_uuid(), 42, 7, 'reading', 10.5),
    ('2026-12-01 00:00:00+00', gen_random_uuid(), 42, 7, 'reading', 10.6);
```

Sau đó kiểm tra `tableoid` để biết hàng được định tuyến tới partition nào:

```sql
SELECT
    tableoid::regclass AS physical_partition,
    occurred_at,
    event_id
FROM telemetry.events
WHERE occurred_at >= TIMESTAMPTZ '2026-11-30 00:00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-12-02 00:00:00+00'
ORDER BY occurred_at;
```

`tableoid` hữu ích trong kiểm thử và chẩn đoán; không nên dùng tên partition làm hợp đồng nghiệp vụ trong ứng dụng.

### 11.2. Đối soát archive

Trước khi drop partition đã archive, nên xác nhận:

- Số dòng export bằng số dòng trong partition tại snapshot đã thống nhất.
- Khoảng min/max timestamp phù hợp với partition bounds.
- Các checksum hoặc tổng kiểm tra nghiệp vụ khớp.
- File có thể đọc lại bằng công cụ và schema đã lưu.
- Metadata lưu lại gồm tên bảng, bounds, thời điểm export, phiên bản schema, checksum và nơi lưu.
- Bản archive đáp ứng chính sách mã hóa, quyền truy cập, retention và legal hold.

## 12. Các lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| `no partition of relation found for row` | Thiếu partition cho timestamp cần insert | Tạo partition trước, kiểm tra job và cảnh báo khoảng tương lai. |
| Truy vấn vẫn quét nhiều partition | Thiếu điều kiện partition key hoặc biểu thức làm pruning khó nhận biết | Viết điều kiện range trực tiếp và kiểm tra `EXPLAIN`. |
| Không tạo được partition mới vì overlap | Bounds chồng lấn hoặc DEFAULT chứa dữ liệu thuộc range mới | Kiểm tra bounds, di chuyển dữ liệu DEFAULT và thêm constraint phù hợp. |
| Tạo partition có tên đã tồn tại nhưng bounds sai | `IF NOT EXISTS` chỉ kiểm tra tên relation | Kiểm tra catalog/bounds, sửa automation và không bỏ qua silently. |
| Lỗi tạo primary key/unique constraint | Constraint không chứa partition key | Thiết kế khóa ghép chứa đầy đủ partition key hoặc registry uniqueness riêng. |
| Drop partition bị chặn | Lock, dependency, foreign key hoặc transaction đang giữ relation | Xác định blocker, kiểm tra dependency và dùng cửa sổ maintenance/detach phù hợp. |
| Archive xong nhưng không khôi phục được | Thiếu schema, metadata, kiểu dữ liệu hoặc file hỏng | Lưu schema version, checksum và thử import định kỳ. |
| DEFAULT partition tăng liên tục | Job tạo partition tương lai lỗi hoặc late arrival không được phân loại | Cảnh báo số dòng, xác định nguồn và chuyển dữ liệu đúng partition. |
| Partition lịch sử vẫn chiếm nhiều dung lượng | Detach không tự di chuyển hoặc xóa storage | Thực hiện archive/drop hoặc chuyển tablespace theo kế hoạch. |
| Nhiều partition làm planning chậm | Partition quá nhỏ/quá nhiều hoặc truy vấn không pruning | Gộp chu kỳ phù hợp, tối ưu predicate và đo planning time. |
| Thống kê planner sai sau khi nạp dữ liệu | Parent chưa được ANALYZE hoặc partition stats cũ | Chạy `ANALYZE` phù hợp trên parent và partition. |

## 13. Runbook vận hành hằng ngày và hằng tháng

### Hằng ngày

- Kiểm tra partition tương lai đã được tạo đủ cho cửa sổ ingest.
- Theo dõi insert error, số dòng DEFAULT và dữ liệu đến muộn.
- Theo dõi dung lượng partition, index, WAL và tốc độ tăng dữ liệu.
- Kiểm tra job archive/retention, lỗi và thời gian chạy.
- Theo dõi autovacuum/analyze, dead tuple và tuổi XID.

### Hằng tháng

- Đối soát danh sách partition với lịch thời gian và chính sách retention.
- Xác nhận partition hết hạn, legal hold và phê duyệt trước khi detach/drop.
- Kiểm tra archive có thể đọc lại và checksum khớp.
- Kiểm tra backup/PITR bao phủ thời điểm cần thiết.
- Đánh giá kích thước partition, số lượng index và planning time.
- Điều chỉnh chu kỳ partition nếu volume hoặc truy vấn thay đổi đáng kể.
- Kiểm tra role và quyền trên partition mới, partition cũ và archive schema.

## 14. Kết luận

Thiết kế dữ liệu theo thời gian trong PostgreSQL cần bắt đầu từ ý nghĩa của timestamp, cách truy vấn và thời hạn lưu giữ. RANGE partitioning theo thời gian thường giúp truy vấn pruning hiệu quả và cho phép quản lý dữ liệu cũ theo từng lô. Kích thước partition phải cân bằng dung lượng, tần suất truy vấn, số lượng relation và chi phí maintenance. Dùng biên nửa mở, thống nhất UTC khi phù hợp và tạo partition trước khi ingest để tránh lỗi tại ranh giới.

Retention policy cần xác định loại dữ liệu, mốc tính thời hạn, archive, legal hold, quyền xóa và bằng chứng đối soát. Detach/archive/drop partition có thể tiết kiệm hơn DELETE hàng loạt, nhưng phải kiểm tra bounds, dependency, lock, khả năng phục hồi và tính toàn vẹn archive. Kết hợp monitoring partition, autovacuum, index, WAL và job maintenance giúp hệ thống mở rộng ổn định khi dữ liệu tiếp tục tăng.

## Tài liệu tham khảo

- [PostgreSQL — Table Partitioning](https://www.postgresql.org/docs/current/ddl-partitioning.html)
- [PostgreSQL — Declarative Partitioning](https://www.postgresql.org/docs/current/ddl-partitioning.html#DDL-PARTITIONING-DECLARATIVE)
- [PostgreSQL — ALTER TABLE](https://www.postgresql.org/docs/current/sql-altertable.html)
- [PostgreSQL — CREATE TABLE](https://www.postgresql.org/docs/current/sql-createtable.html)
- [PostgreSQL — Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html)
- [PostgreSQL — Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html)
- [PostgreSQL — Date/Time Types](https://www.postgresql.org/docs/current/datatype-datetime.html)
