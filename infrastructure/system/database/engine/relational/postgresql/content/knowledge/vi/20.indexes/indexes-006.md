# BRIN và dữ liệu có tương quan với thứ tự vật lý trong PostgreSQL

Khi một bảng PostgreSQL chứa hàng triệu đến hàng tỷ bản ghi sự kiện, log truy cập, cảm biến hoặc lịch sử giao dịch, việc duy trì chỉ mục B-tree trên nhiều cột có thể tốn đáng kể dung lượng và chi phí ghi. Tuy nhiên, nếu các hàng được nạp **gần theo thứ tự thời gian** thì các bản ghi có giá trị timestamp gần nhau cũng thường nằm gần nhau **trong những trang heap vật lý**. Một truy vấn lọc dữ liệu của ngày hôm qua không cần xem tất cả những trang chứa bản ghi của năm trước.

**BRIN (Block Range INdex)** tận dụng đặc điểm này: thay vì ghi một entry cho từng hàng, nó lưu **thông tin tóm tắt theo nhóm trang heap liên tiếp**. Với một cột thời gian, tóm tắt phổ biến là giá trị nhỏ nhất và lớn nhất của cột trong từng nhóm trang. PostgreSQL có thể bỏ qua toàn bộ những nhóm trang mà khoảng giá trị của chúng chắc chắn không giao với điều kiện `WHERE`.

BRIN rất nhỏ và có thể hiệu quả với **dữ liệu có tương quan giữa giá trị cột và thứ tự vật lý của heap**, nhưng nó là **lossy index**: nó chọn các trang *có khả năng* chứa kết quả, rồi database phải đọc/recheck tuple để xác định kết quả chính xác. Nó không thay thế B-tree cho unique lookup, tìm một hàng cụ thể hoặc `ORDER BY ... LIMIT`.

Bài thuộc chương **Chỉ mục**, module **Database Engine Relational PostgreSQL**, trình bày cấu trúc BRIN, ý nghĩa correlation, các operator class, `pages_per_range`, query plan, bảo trì summarization, cách nạp dữ liệu, tương tác với partitioning/B-tree và các bài tập thực hành.

## 1. Bài toán: dữ liệu thời gian có bố trí vật lý gần tuần tự

Giả sử một bảng `sensor_event` có các cột:

~~~text
event_id | device_id | occurred_at | temperature | payload
~~~

Mỗi phút hệ thống liên tục thêm sự kiện mới. Dữ liệu có thể phân bố trong heap như sau:

~~~text
Heap blocks 0–127    : sự kiện đầu tháng 01
Heap blocks 128–255  : sự kiện giữa tháng 01
Heap blocks 256–383  : sự kiện cuối tháng 01
Heap blocks 384–511  : sự kiện đầu tháng 02
...
~~~

Các giá trị thời gian không nhất thiết tăng hoàn hảo từng hàng, nhưng mỗi **vùng trang vật lý** thường chứa những sự kiện trong một khoảng thời gian tương đối hẹp.

Ví dụ BRIN tóm tắt:

~~~text
Range 0, blocks   0–127:
    min(occurred_at) = 2026-01-01
    max(occurred_at) = 2026-01-12

Range 1, blocks 128–255:
    min(occurred_at) = 2026-01-12
    max(occurred_at) = 2026-01-24

Range 2, blocks 256–383:
    min(occurred_at) = 2026-01-24
    max(occurred_at) = 2026-02-05
~~~

Khi `WHERE` yêu cầu sự kiện ngày 18/01, range 0 và range 2 có thể bị loại ngay vì min/max của chúng không giao với ngày đó; chỉ range 1 còn là ứng viên.

Những ngày ở sơ đồ hoàn toàn minh họa ý tưởng, không phải số liệu thực lấy từ tập dữ liệu của bài.

## 2. Heap page và block range là gì?

PostgreSQL lưu bảng thành các **heap pages** (còn gọi blocks). Bản build thông dụng có trang **8 KiB**, có thể kiểm tra bằng:

~~~sql
SHOW block_size;
~~~

Một trang có thể chứa nhiều tuple và phiên bản tuple do MVCC. Một **block range** là nhóm các trang có block number liên tiếp.

Với `pages_per_range=32`:

~~~text
Range 0: heap block   0–31
Range 1: heap block  32–63
Range 2: heap block  64–95
Range 3: heap block  96–127
...
~~~

Nếu block size bằng 8 KiB, một range 32 trang tương ứng:

\[
32 \times 8\ \text{KiB} = 256\ \text{KiB}
\]

Đây là dung lượng **vùng heap** được summary bao phủ, không phải dung lượng index hoặc dung lượng cột. Số hàng trong một range không cố định vì phụ thuộc chiều rộng tuple, dead tuples, free space và những yếu tố lưu trữ khác.

**`pages_per_range` là số trang heap, không phải số bản ghi.**

## 3. BRIN minmax hoạt động thế nào?

Operator class BRIN dễ hiểu nhất là **minmax**. Nó lưu giá trị nhỏ nhất và lớn nhất của cột trong mỗi range.

Ví dụ:

~~~text
Range A: [10:00, 10:29]
Range B: [10:30, 10:59]
Range C: [11:00, 11:29]
~~~

Truy vấn:

~~~sql
WHERE occurred_at >= TIMESTAMPTZ '2026-01-01 10:40:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-01-01 10:50:00+00'
~~~

Range A và C có thể bị loại. Range B có min/max giao với điều kiện, nên được giữ lại để kiểm tra hàng thực.

### 3.1. Minmax không phải danh sách các giá trị có trong range

Giả sử:

~~~text
Range X:
    min(value) = 10
    max(value) = 100
    giá trị thực chỉ gồm 10 và 100
~~~

Khi tìm `value=50`, range này vẫn có thể được coi là ứng viên vì 50 nằm giữa 10 và 100. PostgreSQL phải recheck những hàng thực để biết không có giá trị 50.

Đây là **false positive ở bước chọn range**. BRIN không được phép bỏ qua một range thực sự có hàng khớp, nhưng có thể chọn thừa nhiều range.

## 4. “Tương quan với thứ tự vật lý” có nghĩa gì?

Một cột có **physical correlation** mạnh nếu giá trị cột thay đổi tương đối có trật tự khi đi dọc theo vị trí các tuple trong heap.

Tương quan dương mạnh:

~~~text
Heap block       occurred_at
0                08:00
1                08:05
2                08:10
3                08:15
4                08:20
~~~

Tương quan âm mạnh:

~~~text
Heap block       occurred_at
0                08:20
1                08:15
2                08:10
3                08:05
4                08:00
~~~

**Cả hai hướng đều có thể tốt với BRIN minmax:** trong từng vùng vật lý, khoảng giá trị vẫn tương đối hẹp. Với BRIN, thứ tự tăng và giảm không phải điều quyết định; điều quan trọng là **mỗi range tập trung vào một phần nhỏ miền giá trị**.

Khi dữ liệu bị trộn:

~~~text
Heap block 0: tháng 01, tháng 08, tháng 12
Heap block 1: tháng 02, tháng 06, tháng 11
Heap block 2: tháng 01, tháng 05, tháng 10
~~~

min/max của từng range có thể trải gần cả năm. Một query một ngày rất nhỏ vẫn phải đọc nhiều range vì tóm tắt không loại được chúng.

### 4.1. Không cần sắp tuyệt đối

Nạp theo thời gian thực tế thường có vài hàng đến muộn và nhiều transaction cùng ghi. BRIN vẫn có thể hữu ích nếu những giá trị trong **cùng page range** ít bị phân tán. Điều cần tránh là quá nhiều giá trị ngoại lai khiến mỗi summary trải gần toàn bộ miền truy vấn.

## 5. Đọc correlation trong PostgreSQL

PostgreSQL lưu thống kê correlation cho các cột có thống kê phù hợp.

~~~sql
SELECT
    schemaname,
    tablename,
    attname,
    correlation
FROM pg_stats
WHERE schemaname = 'brin_lab'
  AND tablename = 'sensor_event'
  AND attname = 'occurred_at';
~~~

Giá trị `correlation` thường nằm từ **-1 đến +1**:

| Giá trị | Ý nghĩa điển hình |
|---|---|
| Gần +1 | Giá trị tăng gần theo vị trí vật lý |
| Gần -1 | Giá trị giảm gần theo vị trí vật lý |
| Gần 0 | Mức tương quan tuyến tính thấp |
| NULL | Có thể thiếu thống kê hoặc chưa có giá trị thích hợp |

`ANALYZE` cập nhật thống kê:

~~~sql
ANALYZE brin_lab.sensor_event;
~~~

Một correlation gần ±1 là tín hiệu đáng cân nhắc BRIN, **không phải bảo đảm hiệu năng**. Cần còn xem mức chọn lọc WHERE, pages_per_range, kích thước bảng, những outliers và kế hoạch thực thi.

### 5.1. Correlation không trực tiếp đo mỗi BRIN summary

`pg_stats.correlation` là một thống kê về tương quan giữa giá trị cột và vị trí vật lý; nó không liệt kê min/max của từng range. Có thể có bảng correlation trung bình nhưng vài vùng tốt hơn hoặc xấu hơn nhiều.

Nếu query chủ yếu đọc những vùng có late-arriving events, correlation toàn bảng cao cũng chưa chắc mang lại hiệu quả như mong đợi.

## 6. So sánh BRIN với B-tree

| Tiêu chí | B-tree | BRIN |
|---|---|---|
| Cấu trúc | Các index entries theo khóa và tham chiếu tuple | Summary theo dải heap pages |
| Kích thước | Thường lớn hơn trên bảng nhiều hàng | Thường rất nhỏ so với heap |
| Tìm khóa chính/điểm rất chọn lọc | Thường rất hiệu quả | Có thể đọc/recheck nhiều hàng |
| Lọc khoảng giá trị trên dữ liệu correlated | Tốt | Thường đáng cân nhắc |
| Phụ thuộc thứ tự vật lý của heap | Ít hơn | Rất quan trọng với minmax |
| `ORDER BY ... LIMIT` | Có thể hỗ trợ ordered index scan | Không cung cấp thứ tự tuple trực tiếp |
| UNIQUE/PRIMARY KEY | Có thể dùng | Không hỗ trợ uniqueness |
| Index Only Scan với index bao phủ | Có thể nếu đủ điều kiện MVCC | Không trả từng tuple chính xác chỉ từ summary |
| Dữ liệu bị xáo trộn | Vẫn có thể tra theo khóa | Tóm tắt minmax thường kém hiệu quả |
| Chi phí index khi append rất nhiều | Có thể đáng kể | Thường nhỏ hơn, tùy workload |

Không nên loại B-tree primary key chỉ vì đã có BRIN. Hai loại index giải quyết **hai dạng truy cập khác nhau** và có thể cùng tồn tại nếu workload cần.

## 7. BRIN là một loại lossy index

BRIN không lưu danh sách chính xác mọi tuple trong một range. Nó thường phối hợp với **bitmap heap scan**:

~~~text
Bitmap Heap Scan on sensor_event
  Recheck Cond: (occurred_at >= ... AND occurred_at < ...)
  Rows Removed by Index Recheck: ...
  Heap Blocks: lossy=...
  -> Bitmap Index Scan on idx_sensor_event_time_brin
       Index Cond: (occurred_at >= ... AND occurred_at < ...)
~~~

Diễn giải:

1. `Bitmap Index Scan` dùng BRIN để tìm những ranges có thể chứa kết quả.
2. Những heap blocks thuộc ranges ứng viên được đưa vào bitmap.
3. `Bitmap Heap Scan` đọc các heap pages được chọn.
4. `Recheck Cond` kiểm tra từng tuple theo điều kiện SQL.
5. Các hàng không khớp bị loại trước khi trả cho client.

### 7.1. Rows Removed by Index Recheck

Nếu kế hoạch có:

~~~text
Rows Removed by Index Recheck: 5000
~~~

thì có nhiều hàng được đọc ở các trang ứng viên nhưng không thỏa điều kiện khi recheck. Với BRIN, điều này không nhất thiết là lỗi; nó phản ánh tính lossy của tóm tắt theo range.

### 7.2. Heap Blocks: lossy

Chỉ số này cho biết số heap blocks được xử lý dưới dạng bitmap lossy trong node tương ứng, **không phải số hàng sai**. Bitmap scan còn có thể bị ảnh hưởng giới hạn bộ nhớ, nên cần đọc toàn bộ kế hoạch và bối cảnh.

**Tính đúng của query vẫn được giữ:** BRIN có thể đề xuất trang thừa, nhưng PostgreSQL phải kiểm tra giá trị thực để không trả false-positive rows.

## 8. Tạo bảng thực hành nạp theo thời gian

Bài dùng một bảng 300.000 sự kiện tổng hợp. **Chỉ chạy trong database lab riêng**, không sử dụng trên production; các câu INSERT/CREATE INDEX tiêu tốn I/O và dung lượng thực.

~~~sql
CREATE SCHEMA brin_lab;

CREATE TABLE brin_lab.sensor_event (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    device_id INTEGER NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    temperature NUMERIC(6, 2) NOT NULL,
    payload TEXT
);

INSERT INTO brin_lab.sensor_event (
    device_id,
    occurred_at,
    temperature,
    payload
)
SELECT
    (g % 64 + 1)::INTEGER,
    TIMESTAMPTZ '2026-01-01 00:00:00+00'
        + g * INTERVAL '1 second',
    (18 + (g % 250) / 10.0)::NUMERIC(6, 2),
    'event-' || g::TEXT
FROM generate_series(1, 300000) AS g
ORDER BY g;
~~~

Bảng này có:

- Timestamp tăng một giây với mỗi giá trị `g`.
- `device_id` tuần hoàn qua 64 thiết bị.
- `temperature` thay đổi theo công thức.
- `payload` là text minh họa.
- `event_id` là identity, có primary-key B-tree riêng.

`ORDER BY g` giúp minh họa quá trình nạp dữ liệu theo thứ tự, nhưng **SQL không cam kết thứ tự vật lý mãi mãi** sau các UPDATE, concurrent inserts, rewrite hoặc thao tác bảo trì.

### 8.1. Quan sát dữ liệu

~~~sql
SELECT
    COUNT(*) AS total_rows,
    MIN(occurred_at) AS first_event,
    MAX(occurred_at) AS last_event
FROM brin_lab.sensor_event;
~~~

Với đúng script, có 300.000 hàng; timestamp đầu là `2026-01-01 00:00:01+00` và timestamp cuối cách mốc 01/01 đúng 300.000 giây.

## 9. CREATE INDEX ... USING brin

Tạo BRIN theo timestamp:

~~~sql
CREATE INDEX idx_sensor_event_time_brin
ON brin_lab.sensor_event
USING brin (occurred_at)
WITH (pages_per_range = 32, autosummarize = on);
~~~

Ở đây:

- `USING brin` chọn index access method.
- `occurred_at` là cột được tóm tắt.
- `pages_per_range=32` nghĩa một entry summary cho mỗi nhóm 32 heap pages.
- `autosummarize=on` bật cơ chế hỗ trợ tự tóm tắt ranges mới khi phù hợp, nhưng **không có nghĩa summary được cập nhật ngay mỗi lần INSERT**.

Nếu không chỉ định, giá trị mặc định thường dùng của `pages_per_range` là **128**.

### 9.1. BRIN không làm UNIQUE

Không thể dùng BRIN để bảo đảm một timestamp hay một ID là duy nhất. Ràng buộc uniqueness phải có index loại phù hợp, thường là B-tree.

### 9.2. Có thể tạo BRIN nhiều cột

~~~sql
CREATE INDEX idx_sensor_event_time_device_brin
ON brin_lab.sensor_event
USING brin (occurred_at, device_id)
WITH (pages_per_range = 32);
~~~

Nhưng không nên tạo nhiều index đồng chức năng trong production chỉ để thử. Trong lab này, index thứ hai giúp phân biệt việc summary của hai cột không tương đương một B-tree hai cột.

## 10. Truy vấn theo khoảng thời gian

~~~sql
SELECT
    event_id,
    device_id,
    occurred_at,
    temperature
FROM brin_lab.sensor_event
WHERE occurred_at >= TIMESTAMPTZ '2026-01-03 12:00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-01-03 12:15:00+00';
~~~

Với bảng gần theo thứ tự timestamp, các page ranges xa khoảng này có thể bị loại.

### 10.1. Dùng khoảng nửa mở

Cách viết:

~~~sql
WHERE occurred_at >= :start_time
  AND occurred_at < :end_time
~~~

thường rõ hơn việc đoán mốc cuối cùng `23:59:59.999999`. Hai khoảng liên tiếp `[12:00,12:15)` và `[12:15,12:30)` không đếm trùng biên 12:15.

`:start_time`/`:end_time` là ký hiệu tham số tầng ứng dụng; với JDBC dùng dấu `?` và bind kiểu phù hợp. Chúng không phải literal SQL chạy nguyên văn ở PostgreSQL server.

### 10.2. Giữ điều kiện trên cột có thể index

Nếu viết:

~~~sql
WHERE occurred_at::DATE = DATE '2026-01-03'
~~~

PostgreSQL không nhất thiết dùng được BRIN minmax trên cột gốc hiệu quả như một điều kiện khoảng, và việc chuyển `TIMESTAMPTZ` sang `DATE` phụ thuộc timezone session.

Nên xác định ranh giới ngày ở timezone nghiệp vụ rồi bind hai mốc `TIMESTAMPTZ`. Tránh thay semantics thời gian chỉ để dùng index.

## 11. Xem kế hoạch bằng EXPLAIN

~~~sql
ANALYZE brin_lab.sensor_event;

EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, occurred_at, temperature
FROM brin_lab.sensor_event
WHERE occurred_at >= TIMESTAMPTZ '2026-01-03 12:00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-01-03 12:15:00+00';
~~~

Quan sát:

- Có `Bitmap Index Scan` dùng BRIN không?
- Có `Bitmap Heap Scan` và `Recheck Cond` không?
- Bao nhiêu `Rows Removed by Index Recheck`?
- Bao nhiêu `Heap Blocks` được đọc?
- `Buffers: shared hit/read`?
- Số `actual rows` và tổng execution time?
- Planner có chọn `Seq Scan` thay vì BRIN không?

**Không bắt buộc PostgreSQL dùng BRIN dù đã tạo index.** Với bảng nhỏ, filter không đủ chọn lọc hoặc dữ liệu đã ở cache, Seq Scan có thể rẻ hơn.

`EXPLAIN ANALYZE` thực thi câu SQL; ví dụ là SELECT. Với DML trên production, không dùng ANALYZE tùy ý vì lệnh có thể thay đổi dữ liệu.

## 12. So sánh kích thước BRIN và B-tree

Tạo thêm B-tree trong lab:

~~~sql
CREATE INDEX idx_sensor_event_time_btree
ON brin_lab.sensor_event (occurred_at);
~~~

Xem dung lượng:

~~~sql
SELECT
    c.relname AS index_name,
    pg_size_pretty(pg_relation_size(c.oid)) AS index_size,
    pg_relation_size(c.oid) AS bytes
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname = 'brin_lab'
  AND c.relname IN (
      'idx_sensor_event_time_brin',
      'idx_sensor_event_time_btree'
  )
ORDER BY bytes;
~~~

BRIN thường nhỏ hơn B-tree rất nhiều trên bảng đủ lớn, nhưng **không ghi sẵn tỷ lệ chính xác** vì còn phụ thuộc số hàng, pages_per_range, operator class, kích thước khóa và phiên bản.

Sau khi B-tree tồn tại, planner có thể chọn nó cho truy vấn theo timestamp. Muốn so tốc độ hai index phải tổ chức thử nghiệm kiểm soát lựa chọn index, tình trạng cache, dữ liệu và cùng câu WHERE.

### 12.1. Kích thước index nhỏ không đồng nghĩa query nhanh hơn

B-tree phải lưu nhiều thông tin hơn, nhưng có thể định vị chính xác hơn cho point query hoặc range rất hẹp. BRIN tiết kiệm storage/index maintenance nhưng có thể phải đọc nhiều heap pages để recheck.

## 13. Thí nghiệm dữ liệu xáo trộn vật lý

Tạo bản sao với hàng được nạp theo thứ tự hash của ID:

~~~sql
CREATE TABLE brin_lab.sensor_event_shuffled AS
SELECT
    event_id, device_id, occurred_at,
    temperature, payload
FROM brin_lab.sensor_event
ORDER BY md5(event_id::TEXT);

CREATE INDEX idx_shuffled_time_brin
ON brin_lab.sensor_event_shuffled
USING brin (occurred_at)
WITH (pages_per_range = 32);

ANALYZE brin_lab.sensor_event_shuffled;
~~~

Bảng shuffled chứa cùng dữ liệu logic nhưng các timestamp ở heap pages gần nhau có thể cách nhau rất xa.

**`CREATE TABLE AS` không tự sao chép tất cả constraint, identity, trigger, RLS hoặc các thuộc tính khác** của bảng gốc. Bảng này chỉ dùng để nghiên cứu index.

### 13.1. So correlation của hai bảng

~~~sql
SELECT
    tablename,
    attname,
    correlation
FROM pg_stats
WHERE schemaname = 'brin_lab'
  AND tablename IN ('sensor_event', 'sensor_event_shuffled')
  AND attname = 'occurred_at'
ORDER BY tablename;
~~~

Kỳ vọng:

- `sensor_event`: correlation gần +1.
- `sensor_event_shuffled`: correlation gần 0.

Giá trị thực có thể lệch do thống kê và bố trí heap.

### 13.2. So cùng câu truy vấn

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, occurred_at, temperature
FROM brin_lab.sensor_event_shuffled
WHERE occurred_at >= TIMESTAMPTZ '2026-01-03 12:00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-01-03 12:15:00+00';
~~~

Khi dữ liệu phân tán, nhiều ranges có min/max rất rộng. PostgreSQL có thể đọc nhiều trang, loại nhiều hàng khi recheck hoặc thậm chí chọn Seq Scan.

Thí nghiệm cho thấy **cùng số hàng và cùng điều kiện WHERE, BRIN có thể khác hiệu quả rõ rệt vì thứ tự vật lý của heap**.

## 14. pages_per_range là một đánh đổi

Nếu block size 8 KiB:

| pages_per_range | Heap space tối đa cho một range |
|---:|---:|
| 16 | 128 KiB |
| 32 | 256 KiB |
| 64 | 512 KiB |
| 128 | 1 MiB |
| 256 | 2 MiB |

Range **nhỏ hơn** thường có min/max hẹp hơn và có thể giúp giảm các trang cần recheck, đổi lại số summary entries và index size lớn hơn.

Range **lớn hơn** thường làm index nhỏ hơn, nhưng min/max trải rộng hơn, nhất là khi có outliers, khiến nhiều trang không khớp vẫn bị đọc.

### 14.1. Vì sao không chọn pages_per_range=1?

Một summary cho mỗi trang gần như tối đa độ chi tiết của BRIN, nhưng làm số entries tăng mạnh và giảm lợi thế về index size/maintenance. Nếu query thực sự cần tra chính xác từng hàng, một B-tree có thể thích hợp hơn.

### 14.2. Chọn như thế nào?

1. Xác định độ rộng khoảng WHERE phổ biến.
2. Đo số heap pages tương ứng một khoảng thời gian.
3. Xem correlation và tỷ lệ dữ liệu đến muộn.
4. Thử vài cấu hình BRIN trên lab.
5. So index size, bitmap heap blocks và recheck rows.
6. So thời gian p50/p95 trên query đại diện.
7. Xem overhead ghi và bảo trì.
8. Chọn điểm cân bằng, không chỉ tối ưu một truy vấn.

## 15. BRIN không hỗ trợ ORDER BY như B-tree

Xét:

~~~sql
SELECT event_id, occurred_at
FROM brin_lab.sensor_event
ORDER BY occurred_at DESC
LIMIT 20;
~~~

B-tree theo thời gian có thể duyệt khóa theo thứ tự rồi dừng sau vài entry. BRIN không lưu danh sách chính xác từng hàng theo khóa để trả ordered scan; nó chỉ biết những page ranges có khoảng min/max nào.

Do đó BRIN **không tự loại chi phí sort cho `ORDER BY ... LIMIT`**. Planner có thể chọn B-tree, Seq Scan + sort hoặc phương án khác.

Ngay cả khi thêm WHERE theo thời gian:

~~~sql
SELECT event_id, occurred_at
FROM brin_lab.sensor_event
WHERE occurred_at >= TIMESTAMPTZ '2026-01-03 00:00:00+00'
ORDER BY occurred_at DESC
LIMIT 20;
~~~

BRIN có thể giúp lọc ranges nhưng các hàng còn lại có thể vẫn cần được sắp xếp.

## 16. Lookup một ID thường nên dùng B-tree

~~~sql
SELECT *
FROM brin_lab.sensor_event
WHERE event_id = 123456;
~~~

Bảng demo có `PRIMARY KEY(event_id)`, nên PostgreSQL đã có B-tree để tra chính xác một ID.

Dù `event_id` có thể tương quan với vị trí heap, một BRIN trên nó vẫn chỉ chọn range và recheck nhiều hàng. Nó không phải thay thế mặc định cho primary key hoặc foreign-key lookup.

## 17. Cột nào phù hợp BRIN?

Những ứng viên tốt khi dữ liệu được nạp có trật tự:

- `created_at`, `occurred_at` ở bảng append-only.
- Sequence/log offset tăng gần theo thứ tự ghi.
- `batch_id` khi các batch được nạp liền nhau.
- Ngày báo cáo được nạp theo ngày.
- Một cột định lượng được nạp theo thứ tự gần monotonic.
- Những kiểu dữ liệu khác có operator class BRIN và bố trí theo khối thuận lợi.

Những ứng viên cần thận trọng:

- `device_id` luân phiên trên toàn bộ bảng.
- `status` thay đổi ngẫu nhiên.
- UUID ngẫu nhiên.
- `email` không tương quan với heap.
- `occurred_at` của các sự kiện đến trễ kéo dài nhiều năm.
- Cột thường xuyên được UPDATE thành giá trị rất khác.

**Kiểu dữ liệu đơn thuần không đủ để chọn BRIN.** Cùng là timestamp nhưng hai hệ thống ingest khác nhau có thể cho correlation khác nhau hoàn toàn.

## 18. Dữ liệu đến muộn và outliers

Giả sử hệ thống đang nạp sự kiện tháng 07, nhưng thỉnh thoảng nhận một sự kiện xảy ra vào tháng 02.

~~~text
Phần lớn giá trị trong range: 2026-07-01 ... 2026-07-03
Một outlier:                2026-02-01
~~~

Summary minmax thành:

~~~text
min = 2026-02-01
max = 2026-07-03
~~~

Một query tìm tháng 04 có thể vẫn giữ range đó, dù không hàng nào thực sự thuộc tháng 04. Đây là nguyên nhân khiến BRIN minmax kém hiệu quả khi **outliers phân tán trên nhiều ranges**.

### 18.1. Các cách ứng phó

- Nạp theo batch sắp thứ tự thời gian nếu pipeline cho phép.
- Partition theo khoảng thời gian.
- Tách late events thành luồng riêng rồi hợp nhất theo quy trình.
- Thử pages_per_range nhỏ hơn để cô lập outlier.
- Thử operator class phù hợp hơn nếu server hỗ trợ.
- Giữ B-tree cho query cần selectivity rất cao.
- Cân nhắc rewrite/CLUSTER nếu lợi ích lớn hơn chi phí.

Không phải vài outliers đã đủ lý do để rewrite cả bảng nhiều terabyte.

## 19. Operator classes: minmax, minmax-multi và loại khác

BRIN không chỉ có một cách tóm tắt min/max. Tùy kiểu dữ liệu và phiên bản PostgreSQL, có những họ operator class như:

- **Minmax:** một dải nhỏ nhất–lớn nhất.
- **Minmax-multi:** nhiều dải đại diện cho các nhóm giá trị trong một page range.
- **Inclusion:** thông tin phục vụ toán tử bao chứa/giao nhau ở những kiểu phù hợp.
- **Bloom-style summaries:** những summary kiểu membership xác suất ở những loại/opclass được hỗ trợ.

### 19.1. Vì sao minmax-multi có thể hữu ích?

Nếu 99% hàng trong range ở tháng 07 nhưng 1% ở tháng 02, một dải minmax trải 5 tháng. Nhiều dải hẹp có thể đại diện các cụm tốt hơn, giúp loại một số truy vấn tìm tháng 04.

Nhưng index có thể lớn hơn và không phải kiểu nào cũng hỗ trợ. Cần đo trên workload thật; không có operator class nào làm BRIN trở thành exact row index.

### 19.2. Tìm operator classes của BRIN trên server

~~~sql
SELECT
    opc.opcname,
    opc.opcintype::regtype AS input_type
FROM pg_opclass AS opc
JOIN pg_am AS am
    ON am.oid = opc.opcmethod
WHERE am.amname = 'brin'
ORDER BY opc.opcname;
~~~

Không tự dùng tên operator class của một kiểu khác hoặc một major version khác mà chưa kiểm tra.

## 20. BRIN nhiều cột không giống B-tree nhiều cột

~~~sql
CREATE INDEX idx_sensor_event_time_device_brin
ON brin_lab.sensor_event
USING brin (occurred_at, device_id)
WITH (pages_per_range = 32);
~~~

Mỗi cột được tóm tắt theo range theo cơ chế/opclass phù hợp. Với bảng lab:

- Thời gian có correlation cao với heap.
- Device ID luân phiên qua 64 thiết bị trên nhiều ranges.

Cột `device_id` có thể không loại trừ được nhiều ranges. Index BRIN nhiều cột **không tự tổ chức khóa lexicographic** như B-tree `(device_id, occurred_at)`.

Khi query thường xuyên lọc một thiết bị:

~~~sql
SELECT event_id, occurred_at, temperature
FROM brin_lab.sensor_event
WHERE device_id = 7
  AND occurred_at >= TIMESTAMPTZ '2026-01-02 00:00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-01-03 00:00:00+00'
ORDER BY occurred_at DESC
LIMIT 100;
~~~

một B-tree sau có thể hữu ích hơn:

~~~sql
CREATE INDEX idx_sensor_event_device_time_btree
ON brin_lab.sensor_event (device_id, occurred_at DESC);
~~~

Nếu workload còn có báo cáo **trên tất cả thiết bị trong một khoảng ngày**, giữ BRIN time cũng có thể hợp lý. Phải cân nhắc chi phí ghi của cả hai index.

## 21. BRIN và partitioning hỗ trợ nhau

Partitioning chia bảng theo phạm vi logic (ví dụ theo tháng). BRIN chia **heap pages bên trong từng relation** thành các ranges.

Sơ đồ:

~~~text
WHERE occurred_at trong ngày 2026-02-12
              |
              v
Partition pruning: chỉ giữ partition tháng 02
              |
              v
BRIN trong partition tháng 02:
bỏ các ranges không giao ngày 12
              |
              v
Bitmap Heap Scan + Recheck các tuple còn lại
~~~

Ví dụ DDL tham khảo cho một bảng khác trong lab:

~~~sql
CREATE TABLE brin_lab.event_partitioned (
    event_id BIGINT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    device_id INTEGER NOT NULL,
    payload TEXT
) PARTITION BY RANGE (occurred_at);

CREATE TABLE brin_lab.event_partitioned_2026_01
PARTITION OF brin_lab.event_partitioned
FOR VALUES FROM ('2026-01-01 00:00:00+00')
             TO ('2026-02-01 00:00:00+00');

CREATE TABLE brin_lab.event_partitioned_2026_02
PARTITION OF brin_lab.event_partitioned
FOR VALUES FROM ('2026-02-01 00:00:00+00')
             TO ('2026-03-01 00:00:00+00');

CREATE INDEX idx_partitioned_time_brin
ON brin_lab.event_partitioned
USING brin (occurred_at);
~~~

Với PostgreSQL hỗ trợ, index trên partitioned parent tạo mô hình partitioned index và các indexes cho partitions tương ứng.

Nếu insert dữ liệu nằm ngoài partitions đã định nghĩa mà không có partition thích hợp, lệnh có thể bị từ chối. Không suy rằng PostgreSQL tự tạo partition mới cho mọi tháng.

### 21.1. Không phải partition nào cũng cần BRIN

Nếu một partition nhỏ hoặc query gần như luôn đọc toàn bộ nó, Seq Scan có thể đủ tốt. Nếu partition rất lớn và query chỉ lấy vài phút/giờ, BRIN có thể thêm lợi ích.

Đo hiệu quả **sau khi partition pruning**, không tự gắn cùng một chỉ mục cho tất cả partitions.

## 22. Summarization là gì?

Các summary entries BRIN đại diện cho từng page range. Khi index được tạo trên bảng đã có dữ liệu, PostgreSQL xây summary cho các ranges hiện có.

Sau đó bảng có thể append thêm những trang mới. Một range mới có thể **chưa được summarise ngay**.

Trong thời gian chưa có summary:

- PostgreSQL vẫn phải bảo đảm kết quả SQL đúng.
- Nó không thể dựa vào một minmax chưa tồn tại để loại range.
- Range chưa summarised có thể phải được đọc như ứng viên.
- Query trên dữ liệu mới nhất có thể đọc nhiều trang hơn mong đợi.

**Unsummarized range không có nghĩa index làm mất kết quả; nó có thể làm giảm khả năng pruning.**

## 23. VACUUM và autosummarize

PostgreSQL có các cơ chế bảo trì BRIN:

### 23.1. VACUUM

~~~sql
VACUUM (ANALYZE) brin_lab.sensor_event;
~~~

VACUUM có thể thực hiện summarization đối với ranges chưa summarised theo cơ chế của BRIN, đồng thời xử lý các công việc MVCC khác. `ANALYZE` cập nhật statistics cho planner.

`VACUUM` thông thường phải chạy **ngoài explicit transaction block**.

### 23.2. autosummarize

Với:

~~~sql
WITH (pages_per_range=32, autosummarize=on)
~~~

BRIN có thể yêu cầu autovacuum summarise những completed ranges phù hợp. Điều này **không bảo đảm summary mới được tạo ngay sau mỗi INSERT**, vì còn scheduling, queue và hoạt động autovacuum.

Một hệ thống ghi tốc độ cao có thể có phần đuôi chưa summarised một thời gian. Cần quan sát trước khi coi đó là vấn đề.

## 24. Hàm bảo trì BRIN thủ công

Với index đã tạo:

~~~sql
SELECT brin_summarize_new_values(
    'brin_lab.idx_sensor_event_time_brin'::regclass
);
~~~

Hàm yêu cầu tóm tắt các ranges chưa được summarized theo semantics hỗ trợ và trả số lượng ranges mới được xử lý.

Có thể tóm tắt một range cụ thể bằng một block number thuộc range:

~~~sql
SELECT brin_summarize_range(
    'brin_lab.idx_sensor_event_time_brin'::regclass,
    256
);
~~~

Vì `pages_per_range=32`, block 256 bắt đầu một range.

PostgreSQL còn có `brin_desummarize_range` để bỏ summary của một range khi cần thao tác bảo trì có kiểm soát. Đây không phải thao tác cần chạy sau mỗi INSERT hoặc mặc định trong production.

**Không sửa tệp chỉ mục thủ công** để “tối ưu BRIN”. Cấu trúc này phải được PostgreSQL duy trì an toàn và nhất quán.

## 25. Chọn dữ liệu theo event time hay ingest time?

Một hệ thống có thể có hai timestamp:

- `occurred_at`: sự kiện xảy ra lúc nào.
- `ingested_at`: hệ thống nhận/ghi sự kiện lúc nào.

Nếu rất nhiều sự kiện đến trễ, `ingested_at` có thể gần thứ tự INSERT và có correlation vật lý cao hơn `occurred_at`.

Tuy nhiên một báo cáo “sự kiện đã diễn ra vào ngày 10/01” **không thể thay `WHERE occurred_at ...` bằng `WHERE ingested_at ...`** chỉ để dùng BRIN tốt hơn. Đó là đổi câu hỏi nghiệp vụ.

Các phương án có thể gồm index khác nhau cho hai loại truy vấn, partitioning, sắp xếp nguồn theo event time hoặc pipeline xử lý late events. Chọn theo semantics chứ không chỉ theo số benchmark.

## 26. Cách nhìn vị trí heap qua ctid trong lab

PostgreSQL có system column `ctid` mô tả vị trí một tuple version theo `(block, offset)`.

~~~sql
SELECT ctid, event_id, occurred_at
FROM brin_lab.sensor_event
ORDER BY ctid
LIMIT 30;
~~~

So với bảng xáo trộn:

~~~sql
SELECT ctid, event_id, occurred_at
FROM brin_lab.sensor_event_shuffled
ORDER BY ctid
LIMIT 30;
~~~

Nếu dữ liệu được nạp gần theo thời gian, những CTID gần nhau thường có timestamp gần nhau. Bảng shuffled có thể có timestamp xa nhau dù CTID lân cận.

### 26.1. ctid không phải khóa nghiệp vụ

`ctid` không bền vững qua UPDATE tạo phiên bản mới, CLUSTER, VACUUM FULL hoặc rewrite. Không dùng `ctid` làm khóa chính, foreign key hoặc cursor phân trang của ứng dụng.

Nó là công cụ chẩn đoán bố trí vật lý, không bảo đảm trật tự SQL khi thiếu `ORDER BY`.

## 27. CLUSTER có thể thay đổi physical correlation

Nếu cần sắp lại heap theo timestamp, có thể dùng `CLUSTER` dựa trên một **index hỗ trợ clustering**, ví dụ B-tree đã tạo.

Trong **database lab**:

~~~sql
CLUSTER brin_lab.sensor_event
USING idx_sensor_event_time_btree;

ANALYZE brin_lab.sensor_event;
~~~

`CLUSTER` rewrite bảng theo index tại thời điểm chạy, có thể cải thiện tương quan vật lý.

### 27.1. Không CLUSTER trực tiếp bằng BRIN

BRIN không hỗ trợ ordered cluster scan như B-tree. Không dùng:

~~~sql
-- Không dùng:
-- CLUSTER brin_lab.sensor_event USING idx_sensor_event_time_brin;
~~~

### 27.2. CLUSTER không phải thao tác miễn phí

Nó có thể:

- Giữ khóa mạnh, chặn hoạt động đồng thời.
- Rewrite dữ liệu và cần dung lượng bổ sung.
- Tạo I/O/WAL, tác động replicas.
- Cần xem lại statistics sau khi hoàn tất.
- Không giữ bảng mãi có trật tự khi INSERT/UPDATE mới đến.

Chỉ cân nhắc khi lợi ích đọc đủ lớn và có kế hoạch vận hành/rollback.

## 28. REINDEX, VACUUM và ANALYZE không phải CLUSTER

Cần phân biệt:

| Thao tác | Mục tiêu chính | Sắp heap theo một cột? |
|---|---|---|
| `ANALYZE` | Thu thập thống kê planner | Không |
| `VACUUM` thường | Cleanup MVCC, free space, VM và bảo trì index | Không |
| `REINDEX` | Xây lại index | Không |
| `VACUUM FULL` | Rewrite/thu hồi không gian | Không phải cách chủ đích sort theo khóa |
| `CLUSTER ... USING btree_index` | Rewrite heap theo thứ tự index hỗ trợ | Có, tại thời điểm chạy |
| `CREATE TABLE AS SELECT ... ORDER BY` | Nạp bản sao theo thứ tự SELECT | Có thể tạo bố trí tương ứng, nhưng không phải bảo đảm vĩnh viễn |

**Rebuild BRIN không tự chữa bố trí vật lý kém.** Nếu nguyên nhân là min/max ranges trải rộng do hàng bị phân tán, cần xét phương pháp bố trí lại dữ liệu hoặc index khác, không chỉ `REINDEX`.

## 29. CTAS theo thứ tự để so lại trong lab

~~~sql
CREATE TABLE brin_lab.sensor_event_reordered AS
SELECT
    event_id, device_id, occurred_at,
    temperature, payload
FROM brin_lab.sensor_event_shuffled
ORDER BY occurred_at, event_id;

CREATE INDEX idx_reordered_time_brin
ON brin_lab.sensor_event_reordered
USING brin (occurred_at)
WITH (pages_per_range = 32);

ANALYZE brin_lab.sensor_event_reordered;
~~~

Giờ có thể so:

- `sensor_event_shuffled`: timestamp phân tán.
- `sensor_event_reordered`: timestamp nạp theo trật tự.

Không sử dụng CTAS như thao tác thay bảng production đơn giản: nó **không tự sao chép** các constraint, identity, FK, trigger, RLS, quyền hoặc đặc tính khác của bảng nguồn.

## 30. BRIN không phục vụ Index Only Scan như covering B-tree

Với B-tree có các cột phù hợp và trang heap all-visible theo MVCC, PostgreSQL đôi khi có thể trả dữ liệu qua **Index Only Scan**.

BRIN là summary theo range, không chứa từng hàng cụ thể hoặc tất cả giá trị cần trả. Ví dụ:

~~~sql
SELECT occurred_at
FROM brin_lab.sensor_event
WHERE occurred_at >= TIMESTAMPTZ '2026-01-03 12:00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-01-03 12:15:00+00';
~~~

Dù `SELECT` chỉ dùng occurred_at, BRIN vẫn phải xác minh giá trị từ các heap pages ứng viên. Nó không phải exact index-only lookup.

Visibility map không biến minmax range summary thành danh sách từng tuple phù hợp.

## 31. BRIN khi có UPDATE và MVCC

UPDATE thường tạo tuple version mới theo MVCC. Nếu timestamp hoặc các giá trị được index bị đổi, PostgreSQL phải duy trì summary an toàn cho những phiên bản ở heap pages tương ứng.

Khi bảng thường xuyên sửa khóa thời gian:

- Correlation với vị trí vật lý có thể suy giảm.
- Range summaries có thể mở rộng.
- Dead tuples chờ cleanup có thể tăng heap work.
- Index/heap maintenance chịu chi phí ghi.

Bảng lịch sử gần như chỉ INSERT thường là ứng viên BRIN tự nhiên hơn bảng thay đổi timestamp tùy ý.

### 31.1. Sửa cột khác vẫn có chi phí

Ngay cả UPDATE `payload` không thay timestamp cũng có thể tạo tuple version mới, ảnh hưởng bố trí vật lý và WAL. Không mặc định tất cả UPDATE đều giữ nguyên vị trí hoặc miễn phí nhờ BRIN.

## 32. NULL và toán tử trên cột BRIN

Nếu cột index nullable, các truy vấn như `IS NULL` có semantics khác so sánh giá trị có thứ tự thông thường. BRIN/operator class có cơ chế xử lý NULL tương ứng; không được đơn giản coi NULL là timestamp nhỏ nhất.

Trong demo `occurred_at NOT NULL` nên câu hỏi dễ hơn. Với một bảng có NULL, cần kiểm tra operator class/EXPLAIN thực tế cho dạng điều kiện thường dùng.

Không tạo BRIN chỉ vì cột nullable; phải xác định tỷ lệ NULL, WHERE chính và phân bố vật lý.

## 33. BRIN có áp dụng được ngoài timestamp không?

Có. Điều quan trọng là:

1. Có operator class BRIN hỗ trợ kiểu dữ liệu/toán tử?
2. Các giá trị có tập trung theo những heap ranges không?
3. WHERE có thể loại nhiều ranges không?
4. Query có cần thứ tự/lookup chính xác mà BRIN không cung cấp?
5. Cost của index nhỏ có bù được cost đọc các trang ứng viên không?

Các cột sequence, ngày, batch ID, số định lượng được nạp theo trật tự và một số kiểu dữ liệu có summary phù hợp đều có thể đáng thử.

Không phải mọi cột số hay mọi cột date đều có correlation vật lý tốt.

## 34. BRIN có giúp COUNT(*) chính xác không?

~~~sql
SELECT COUNT(*)
FROM brin_lab.sensor_event
WHERE occurred_at >= TIMESTAMPTZ '2026-01-03 00:00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-01-04 00:00:00+00';
~~~

BRIN có thể giảm phạm vi heap pages phải đọc. Tuy nhiên minmax summary **không lưu số hàng chính xác thỏa điều kiện tùy ý**. PostgreSQL vẫn phải kiểm tra các tuple phù hợp và MVCC visibility để trả COUNT chính xác.

Nếu báo cáo đếm theo ngày được chạy rất thường xuyên, một bảng tổng hợp theo ngày có thể phù hợp, với chiến lược cập nhật và đối soát riêng.

## 35. Query rộng có thể không cần BRIN

Ví dụ:

~~~sql
SELECT COUNT(*)
FROM brin_lab.sensor_event
WHERE occurred_at >= TIMESTAMPTZ '2020-01-01 00:00:00+00';
~~~

Nếu bảng chỉ chứa dữ liệu từ 2026, **gần như mọi range đều khớp**. BRIN không loại được nhiều trang, Seq Scan có thể rẻ hơn.

BRIN tạo lợi ích khi có thể **loại bỏ đáng kể các ranges không liên quan**, không phải chỉ khi query có một toán tử `>=`.

## 36. Bảng lớn và ingest liên tục: cần quan sát gì?

Những vấn đề vận hành đáng theo dõi:

- Tốc độ INSERT và tuổi/khối lượng các page ranges mới.
- Tỷ lệ late-arriving events.
- Khối lượng UPDATE/DELETE.
- Hoạt động autovacuum/summarization.
- Kích thước BRIN và B-tree khác.
- Sự thay đổi `pg_stats.correlation` sau các batch.
- Query plan và số heap blocks bị đọc.
- Tỷ lệ query theo range so với point lookup.
- Tính hiệu quả của partition pruning.
- Độ trễ ứng dụng và chi phí tổng thể, không chỉ một lần EXPLAIN.

Một BRIN có thể tốt lúc hệ thống mới nạp append-only nhưng dần kém khi mô hình ingest chuyển sang nhập lại dữ liệu lịch sử.

## 37. Đọc pg_stat_user_indexes thận trọng

~~~sql
SELECT
    schemaname,
    relname AS table_name,
    indexrelname,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes
WHERE schemaname = 'brin_lab'
  AND relname = 'sensor_event'
ORDER BY idx_scan DESC, indexrelname;
~~~

Thống kê giúp thấy index có được dùng không, nhưng:

- Số liệu có thể bị reset.
- Không phải mọi bitmap heap fetch được gắn với index như một Index Scan thường.
- BRIN và B-tree không có cùng mô hình index entries.
- `idx_tup_read` không tự là số row hợp lệ trả về.
- Index dùng cho job hàng tuần có thể có `idx_scan` thấp khi xem một ngày.

Hãy đọc thống kê cùng EXPLAIN của query thực, không quyết định xóa index dựa trên một số đếm đơn lẻ.

## 38. Checklist thiết kế chỉ mục BRIN

1. Xác định query chính là **range scan** hay point lookup/ORDER BY.
2. Đánh giá kích thước bảng và dung lượng index hiện tại.
3. Kiểm tra correlation của cột với heap.
4. Kiểm tra ingestion pattern, late arrivals và UPDATE.
5. Xem WHERE có loại được nhiều page ranges không.
6. Chọn operator class phù hợp kiểu dữ liệu và phiên bản.
7. Thử `pages_per_range` ở vài mức.
8. Tạo BRIN trên lab với dữ liệu đại diện.
9. Chạy ANALYZE để planner có thống kê.
10. Đọc `EXPLAIN (ANALYZE, BUFFERS)` và recheck rows.
11. So với B-tree và Seq Scan cho đúng loại query.
12. Xem có cần ordered index scan cho LIMIT không.
13. Cân nhắc partitioning và chọn index theo partition.
14. Thiết kế VACUUM/autosummarize/summarization phù hợp.
15. Đo chi phí ghi và storage của tất cả indexes.
16. Không tự sửa tệp index, không ép planner trên production.
17. Nếu tính reorder heap, đánh giá lock, I/O, WAL và downtime.
18. Theo dõi hiệu quả theo thời gian vì correlation có thể thay đổi.

Không có một cấu hình BRIN nào tối ưu mọi bảng. Chọn theo **cách dữ liệu được ghi, dạng truy vấn và độ hẹp của summaries thực tế**.

## 39. Các sai lầm phổ biến

### Sai lầm 1 — BRIN ghi một entry cho từng row

Không. Nó tóm tắt theo nhóm heap pages.

### Sai lầm 2 — pages_per_range là số hàng

Không, là số trang heap vật lý.

### Sai lầm 3 — Correlation gần -1 là xấu

Không. Tương quan âm mạnh vẫn có thể giúp minmax ranges hẹp.

### Sai lầm 4 — Cột TIMESTAMPTZ tự động phù hợp BRIN

Không. Nếu nạp sự kiện cũ/mới xen kẽ, correlation có thể thấp.

### Sai lầm 5 — BRIN trả tuple chính xác từ index

Không. Nó lossy, cần đọc heap và recheck.

### Sai lầm 6 — BRIN tăng tốc mọi ORDER BY LIMIT

Không. Nó không cung cấp ordered index scan như B-tree.

### Sai lầm 7 — Dùng BRIN để ép UNIQUE

Không. Dùng index type hỗ trợ uniqueness, thường B-tree.

### Sai lầm 8 — pages_per_range nhỏ nhất luôn nhanh nhất

Không. Index size và bảo trì tăng, không phải query nào cũng thêm lợi ích.

### Sai lầm 9 — pages_per_range lớn nhất luôn tốt nhất

Không. Summary rộng gây nhiều false-positive ranges.

### Sai lầm 10 — BRIN(a,b) như B-tree(a,b) nhưng nhỏ hơn

Không. BRIN vẫn tóm tắt từng cột theo block ranges.

### Sai lầm 11 — REINDEX tự sắp lại heap

Không. REINDEX không reorder bảng.

### Sai lầm 12 — VACUUM sẽ sửa correlation vật lý

VACUUM thông thường không sắp bảng theo khóa.

### Sai lầm 13 — CLUSTER trực tiếp với BRIN

BRIN không phải ordered index hỗ trợ CLUSTER.

### Sai lầm 14 — autosummarize=on đồng nghĩa tóm tắt ngay mọi INSERT

Không. Có độ trễ và scheduling autovacuum.

### Sai lầm 15 — Unsummarized range làm thiếu kết quả

Không. Database phải kiểm tra đủ để trả kết quả đúng.

### Sai lầm 16 — Rows Removed by Index Recheck là bug

Không. Đây là phần bình thường của lossy bitmap recheck.

### Sai lầm 17 — Correlation trong pg_stats là số liệu tức thời chính xác

Đó là thống kê có thể cũ; cần ANALYZE và kiểm chứng EXPLAIN.

### Sai lầm 18 — Index nhỏ hơn nghĩa mọi query nhanh hơn

Không. Query còn phải đọc/recheck heap và có thể sort.

### Sai lầm 19 — SQL không ORDER BY tự có thứ tự heap

Không có đảm bảo thứ tự kết quả nếu thiếu ORDER BY.

### Sai lầm 20 — ctid là khóa ổn định

Không. ctid có thể thay đổi khi tuple version hoặc relation được rewrite.

### Sai lầm 21 — Cứ tạo nhiều index BRIN/B-tree không có chi phí

Mỗi index tăng storage, WAL và chi phí ghi/bảo trì.

### Sai lầm 22 — BRIN minmax tính COUNT chính xác từ summary

Không. Minmax không lưu số hàng khớp cho điều kiện bất kỳ.

### Sai lầm 23 — BRIN và partitioning loại trừ lẫn nhau

Có thể kết hợp partition pruning với BRIN range pruning.

### Sai lầm 24 — Chỉ dùng kích thước bảng để chọn index

Không. Correlation, selectivity, WHERE/ORDER BY và dữ liệu đến muộn quan trọng không kém.

## 40. Bài tập thực hành

### Bài 1 — Block range

`pages_per_range=64`, `block_size=8 KiB`. Một range tối đa bao phủ bao nhiêu KiB heap?

**Gợi ý:** 512 KiB.

### Bài 2 — Range pruning

Range A có min=10, max=20. Query `x >= 30 AND x < 40`. BRIN có thể bỏ range A không?

**Gợi ý:** có.

### Bài 3 — False positives

Range có min=10, max=100 nhưng dữ liệu thật chỉ có 10 và 100. Query x=50 có thể phải recheck range không?

**Gợi ý:** có, minmax không chứng minh 50 vắng mặt.

### Bài 4 — Correlation dương

Dữ liệu nạp timestamp tăng theo block. Correlation gần bao nhiêu?

**Gợi ý:** +1.

### Bài 5 — Correlation âm

Dữ liệu nạp timestamp giảm đều theo block. BRIN có tự kém vì correlation âm không?

**Gợi ý:** không; gần -1 vẫn là tương quan mạnh.

### Bài 6 — Dữ liệu xáo trộn

Khi nạp theo `ORDER BY md5(event_id::TEXT)`, minmax ranges của timestamp có xu hướng thế nào?

**Gợi ý:** thường rộng hơn, ít loại trang.

### Bài 7 — CREATE INDEX

Viết SQL tạo BRIN(occurred_at) có pages_per_range=32.

**Gợi ý:** `USING brin (occurred_at) WITH (pages_per_range=32)`.

### Bài 8 — EXPLAIN

Những node/chỉ số nào giúp nhận biết tính lossy của BRIN?

**Gợi ý:** Bitmap Heap Scan, Recheck Cond, Rows Removed by Index Recheck.

### Bài 9 — ORDER BY

Query lấy 20 event mới nhất, không có WHERE. BRIN hay B-tree(time) thường thích hợp hơn?

**Gợi ý:** B-tree phục vụ ordered scan.

### Bài 10 — Unique

Có dùng BRIN cho PRIMARY KEY(event_id) được không?

**Gợi ý:** không.

### Bài 11 — Index size

Viết SQL lấy bytes dung lượng BRIN bằng `pg_relation_size`.

**Gợi ý:** truyền index regclass.

### Bài 12 — Multi-column

Vì sao BRIN(device_id,time) có thể không lọc tốt theo device_id khi device luân phiên trong mọi range?

**Gợi ý:** min/max device phân tán rộng.

### Bài 13 — Timeline một thiết bị

Đề xuất B-tree cho `WHERE device_id=? ORDER BY occurred_at DESC LIMIT 50`.

**Gợi ý:** `(device_id,occurred_at DESC)`.

### Bài 14 — Late arrivals

Một event tháng 02 được thêm vào page chứa tháng 07. Tác động tới minmax?

**Gợi ý:** summary có thể trải từ tháng 02 đến tháng 07.

### Bài 15 — CTID

Vì sao `ctid` không nên là cursor phân trang lâu dài?

**Gợi ý:** thay đổi qua UPDATE/rewrite.

### Bài 16 — CLUSTER

BRIN có thể là index trực tiếp dùng cho `CLUSTER ... USING` không?

**Gợi ý:** không; dùng B-tree hỗ trợ clustering.

### Bài 17 — REINDEX

REINDEX BRIN có tự sắp heap theo thời gian không?

**Gợi ý:** không.

### Bài 18 — VACUUM

VACUUM thông thường có làm correlation timestamp tốt trở lại không?

**Gợi ý:** không reorder dữ liệu.

### Bài 19 — autosummarize

Bật autosummarize có bảo đảm mỗi range mới tóm tắt tức thì sau COMMIT không?

**Gợi ý:** không, có cơ chế nền/độ trễ.

### Bài 20 — Summarize thủ công

Viết lệnh gọi `brin_summarize_new_values` cho BRIN index trong lab.

**Gợi ý:** dùng `'brin_lab.idx_sensor_event_time_brin'::regclass`.

### Bài 21 — Unsummarized ranges

Vì sao range chưa summarized có thể làm query chậm nhưng không được làm mất kết quả?

**Gợi ý:** PostgreSQL phải coi nó như vùng có thể chứa giá trị.

### Bài 22 — Partition

Nếu bảng partition theo tháng và từng partition có BRIN time, WHERE tìm một ngày có những cấp pruning nào?

**Gợi ý:** partition pruning rồi BRIN range pruning.

### Bài 23 — COUNT

Minmax BRIN có thể trả `COUNT(*)` chính xác cho một ngày mà không kiểm tra tuple không?

**Gợi ý:** không.

### Bài 24 — Minmax-multi

Một range có hai cụm timestamp rất xa. Vì sao minmax-multi có thể đáng thử?

**Gợi ý:** nhiều khoảng có thể mô tả cụm tốt hơn một khoảng lớn.

### Bài 25 — Query rộng

WHERE thỏa hơn 90% bảng. Planner có thể chọn Seq Scan thay BRIN không?

**Gợi ý:** có.

### Bài 26 — Chọn index theo workload

Chọn index cho (a) tìm khách bằng email; (b) báo cáo log một ngày trong bảng append-only; (c) 20 sự kiện mới nhất của một thiết bị.

**Gợi ý:** (a) B-tree/unique, (b) BRIN time đáng thử, (c) B-tree(device,time).

### Bài 27 — Đo thực tế

So bảng ordered và shuffled qua EXPLAIN. Cần xem gì ngoài execution time?

**Gợi ý:** index/heap nodes, recheck rows, heap blocks, buffers.

### Bài 28 — pg_stats

Viết query đọc correlation của hai bảng thực hành.

**Gợi ý:** pg_stats với schema/table/attname.

### Bài 29 — Ingest time và event time

Nếu nhiều event đến muộn, cột nào có thể tương quan vật lý tốt hơn? Có tự đổi WHERE sang nó không?

**Gợi ý:** ingested_at có thể tốt hơn, nhưng khác ý nghĩa nghiệp vụ.

### Bài 30 — pages_per_range

Giảm pages_per_range có luôn cải thiện query không?

**Gợi ý:** không; index size và maintenance tăng.

### Bài 31 — Index usage

`idx_scan=0` trong một ngày có đủ lý do xóa index BRIN không?

**Gợi ý:** không nếu workload định kỳ hoặc stats vừa reset.

### Bài 32 — Sắp xếp dữ liệu

CTAS với ORDER BY timestamp có tự sao chép mọi PK/FK/triggers không?

**Gợi ý:** không; cần migration riêng.

## 41. Tổng kết

- **BRIN** là chỉ mục theo **block ranges**, giữ những summary nhỏ của các trang heap thay vì index entry cho từng hàng.
- Với kiểu **minmax**, nó có thể loại toàn bộ ranges chắc chắn không giao với điều kiện WHERE.
- Hiệu quả lớn nhất thường xuất hiện khi giá trị cột **tương quan với vị trí vật lý**: ngày/sự kiện/sequence được nạp gần có thứ tự.
- Tương quan **gần +1 hoặc -1** đều có thể hữu ích. Dữ liệu xáo trộn và late-arriving events làm minmax ranges rộng hơn.
- BRIN là **lossy**, nên `Bitmap Heap Scan` thường phải `Recheck Cond` các tuple trên những trang ứng viên.
- **`pages_per_range`** điều khiển độ chi tiết của summary; range nhỏ thường pruning tốt hơn nhưng index lớn hơn.
- BRIN thường **rất nhỏ** trên bảng lớn, nhưng không thay thế B-tree cho primary/unique, point lookup rất chọn lọc hoặc `ORDER BY ... LIMIT`.
- BRIN nhiều cột vẫn dựa trên **summaries theo page range**, không tương đương B-tree nhiều cột.
- **Partitioning** và BRIN có thể bổ trợ: partition pruning ở cấp bảng con, range pruning ở cấp heap pages.
- **Summarization** cần được duy trì khi bảng thêm pages; `VACUUM`, `autosummarize` và hàm `brin_summarize_*` là những cơ chế liên quan.
- **REINDEX/VACUUM/ANALYZE không tự reorder heap**. Nếu cần tăng correlation bằng sắp xếp vật lý, phải cân nhắc rewrite/CLUSTER bằng index hỗ trợ và chi phí vận hành.
- Đánh giá bằng **`pg_stats.correlation`**, `pg_relation_size` và **`EXPLAIN (ANALYZE, BUFFERS)`** trên workload đại diện thay vì chọn theo lời đồn hoặc kích thước index.

Mô hình tư duy:

~~~text
Giá trị tương quan với thứ tự heap
                |
                v
   Min/max trong từng range hẹp
                |
                v
    BRIN loại được nhiều ranges
                |
                v
 Chỉ đọc và recheck heap pages còn lại
                |
                v
   Giảm I/O với chỉ mục kích thước nhỏ
~~~

Điểm cốt lõi của BRIN không chỉ là cú pháp `CREATE INDEX ... USING brin`. **Chất lượng tổ chức dữ liệu theo thứ tự vật lý quyết định mức độ hữu ích của thông tin tóm tắt theo range**. Khi hiểu mối liên hệ đó, bạn có thể chọn BRIN, B-tree hoặc partitioning dựa trên cách PostgreSQL thực sự đọc dữ liệu, thay vì chỉ dựa vào tên chỉ mục.
