# Kiểm thử truy vấn với dữ liệu lệch và dung lượng đại diện

Một truy vấn chạy nhanh trên vài nghìn hàng chưa chắc chạy tốt khi bảng có hàng chục triệu hàng và dữ liệu phân bố không đồng đều. Trong PostgreSQL, bộ tối ưu truy vấn (planner) dựa vào thống kê để ước lượng số hàng, chọn cách truy cập bảng, thứ tự join, thuật toán join, cách sắp xếp và mức độ song song. Nếu dữ liệu thử nghiệm quá nhỏ, phân bố quá đều hoặc thiếu các mối tương quan có trong thực tế, kế hoạch truy vấn có thể khác xa production.

Kiểm thử hiệu năng có ý nghĩa phải tái hiện cả **quy mô dữ liệu**, **hình dạng phân bố**, **mẫu truy vấn**, **tham số đầu vào** và **mức đồng thời**. Mục tiêu không phải tìm một con số thời gian chạy đẹp trong một lần đo, mà là xác định truy vấn có đáp ứng yêu cầu khi dữ liệu và tải tăng lên hay không, đồng thời hiểu nguyên nhân khi hiệu năng suy giảm.

## 1. Vì sao dữ liệu thử nghiệm phải đại diện?

Giả sử một ứng dụng quản lý đơn hàng theo tenant. Một số tenant lớn tạo ra phần lớn đơn hàng, trong khi hàng trăm tenant còn lại chỉ có vài nghìn bản ghi. Trạng thái `paid` phổ biến hơn nhiều so với `refunded`, và phần lớn đơn hàng nằm trong vài tuần gần nhất.

Truy vấn sau có thể phục vụ dashboard của một tenant:

```sql
SELECT
    id,
    created_at,
    total_amount
FROM sales.orders
WHERE tenant_id = $1
  AND status = 'paid'
  AND created_at >= now() - interval '30 days'
ORDER BY created_at DESC
LIMIT 100;
```

Nếu bộ dữ liệu thử nghiệm chia đều số đơn hàng cho mọi tenant, mọi trạng thái và mọi ngày, truy vấn sẽ được kiểm tra trong điều kiện dễ đoán hơn production. Trong thực tế, tenant lớn có thể trả về hàng triệu hàng nếu bỏ giới hạn thời gian; tenant nhỏ chỉ có vài chục hàng. Điều kiện `status = 'paid'` cũng có thể rất phổ biến ở tenant này nhưng hiếm ở tenant khác.

Những khác biệt đó tác động đến:

- Số hàng mà planner ước lượng cho từng điều kiện lọc.
- Khả năng dùng index thay cho sequential scan.
- Thứ tự join và lựa chọn nested loop, hash join hoặc merge join.
- Kích thước hash table, sort và nguy cơ ghi dữ liệu tạm ra đĩa.
- Số block cần đọc, tỷ lệ cache hit và lượng I/O thực tế.
- Độ trễ của các tham số phổ biến so với tham số hiếm.
- Tải CPU, bộ nhớ, WAL và khóa khi nhiều session chạy cùng lúc.

Vì vậy, một bộ dữ liệu kiểm thử tốt phải giữ được các đặc điểm ảnh hưởng đến truy vấn, thay vì chỉ đạt một tổng số hàng gần bằng production.

## 2. Hiểu các dạng phân bố dữ liệu lệch

### Lệch theo tần suất giá trị

Một cột có thể chứa một vài giá trị xuất hiện rất thường xuyên và rất nhiều giá trị hiếm. Ví dụ, 70% đơn hàng thuộc tenant `1`, 30% còn lại phân tán trên 999 tenant. Tương tự, trạng thái `paid` có thể chiếm 80%, còn `pending`, `cancelled` và `refunded` chiếm phần nhỏ.

Đây là phân bố lệch (skew). Nếu kiểm thử chỉ lấy tenant ngẫu nhiên với xác suất đều nhau, rất có thể không tái hiện được tenant nóng và tail của các tenant nhỏ.

### Lệch theo thời gian

Hệ thống giao dịch thường có tính tập trung thời gian. Dữ liệu mới được truy cập thường xuyên hơn dữ liệu cũ; các đợt khuyến mãi tạo ra đỉnh ghi; dữ liệu theo tháng có thể tăng đột biến vào cuối kỳ. Một bảng có 500 triệu hàng lịch sử nhưng phần lớn truy vấn chỉ đọc 7 ngày gần nhất có đặc tính khác bảng mà các hàng phân bố đều trong nhiều năm.

### Tương quan giữa các cột

Các cột không phải lúc nào cũng độc lập. Ví dụ:

- Tenant lớn có tỷ lệ đơn `paid` cao hơn tenant nhỏ.
- Đơn hàng mới có xác suất `pending` cao hơn đơn hàng cũ.
- Một khu vực chỉ có một nhóm sản phẩm nhất định.
- `country_code` và `currency_code` có mối quan hệ gần như phụ thuộc.

Nếu planner giả định các điều kiện độc lập trong khi chúng có tương quan mạnh, ước lượng số hàng sau khi kết hợp điều kiện có thể sai. Điều này ảnh hưởng đến lựa chọn join và phương án truy cập.

### Lệch theo độ rộng hàng và kích thước dữ liệu

Hai bảng có cùng số hàng nhưng có thể có kích thước vật lý rất khác nhau. Một bảng chứa vài cột số nguyên nhỏ khác bảng có nhiều `text`, `jsonb`, `bytea`, array hoặc giá trị TOAST lớn. Kích thước heap, index, số block cần đọc và mức tiêu thụ bộ nhớ đều có thể khác.

### Lệch theo khóa và phân bố trùng lặp

Khóa duy nhất thường có độ chọn lọc cao, trong khi mã trạng thái hoặc loại sự kiện có ít giá trị phân biệt. Nếu dữ liệu thử nghiệm không có tỷ lệ trùng lặp giống thực tế, planner và index có thể được đánh giá trong điều kiện sai.

## 3. Xác định dữ liệu nào là đại diện

Trước khi tạo dữ liệu, hãy xác định các đặc điểm mà truy vấn thực sự sử dụng. Không cần sao chép mọi cột nếu chúng không ảnh hưởng đến đường truy cập, phép join, kích thước hàng hoặc điều kiện lọc. Tuy nhiên, không được bỏ qua những đặc điểm có ảnh hưởng đến kế hoạch thực thi.

Một hồ sơ dữ liệu nên ghi nhận:

| Đặc điểm | Câu hỏi cần trả lời | Cách đo hoặc nguồn thông tin |
|---|---|---|
| Quy mô | Mỗi bảng có bao nhiêu hàng? | `count(*)`, catalog và số liệu vận hành |
| Kích thước | Heap và index chiếm bao nhiêu dung lượng? | `pg_total_relation_size`, `pg_relation_size` |
| Cardinality | Mỗi cột có bao nhiêu giá trị phân biệt? | `count(DISTINCT ...)`, `pg_stats.n_distinct` |
| Tần suất | Giá trị phổ biến nhất chiếm bao nhiêu phần trăm? | `GROUP BY`, `pg_stats.most_common_freqs` |
| Null | Tỷ lệ `NULL` là bao nhiêu? | `count(*) FILTER (WHERE col IS NULL)` |
| Tương quan | Các cột có phụ thuộc hoặc thường xuất hiện cùng nhau không? | Truy vấn nhóm kết hợp, thống kê đa cột |
| Thời gian | Dữ liệu tập trung ở giai đoạn nào? | Histogram theo ngày/tháng và truy vấn thực tế |
| Quan hệ | Tỷ lệ khóa ngoại hợp lệ và số hàng con mỗi cha? | Join, phân bố số lượng theo khóa |
| Độ rộng | Giá trị text/JSON có độ dài điển hình ra sao? | `avg(octet_length(...))`, percentile |
| Truy cập | Tham số nào thường gặp và tần suất bao nhiêu? | Query log, `pg_stat_statements`, trace ứng dụng |

Nên thu thập dữ liệu ở nhiều thời điểm, chẳng hạn ngày bình thường, ngày cao điểm và cuối kỳ. Một snapshot duy nhất có thể bỏ qua đợt tăng tải theo mùa hoặc dữ liệu lịch sử đã bị xóa theo retention policy.

## 4. Quy mô dữ liệu và kích thước vật lý

### Chọn các mức kiểm thử

Thay vì chỉ tạo một dataset, nên kiểm thử theo nhiều mức:

1. **Nhỏ:** dùng để phát triển truy vấn, kiểm tra kết quả và phát hiện lỗi logic.
2. **Trung bình:** dùng để quan sát xu hướng khi số hàng và index tăng.
3. **Mục tiêu hiện tại:** gần với quy mô production đang vận hành.
4. **Mục tiêu tăng trưởng:** mô phỏng dung lượng dự kiến trong một khoảng thời gian, chẳng hạn 6 hoặc 12 tháng.
5. **Đỉnh tải:** kết hợp dữ liệu mục tiêu với mức đồng thời và tỷ lệ truy vấn cao điểm.

Không nên suy ra thời gian chạy ở quy mô lớn bằng cách nhân thời gian của dataset nhỏ theo tỷ lệ số hàng. Index, cache, join, sort, phân vùng, checkpoint và I/O có thể thay đổi hành vi không tuyến tính.

### Đo kích thước bảng và index

```sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    pg_size_pretty(pg_relation_size(relid)) AS heap_size,
    pg_size_pretty(pg_indexes_size(relid)) AS indexes_size,
    pg_size_pretty(pg_total_relation_size(relid)) AS total_size
FROM pg_stat_user_tables
ORDER BY pg_total_relation_size(relid) DESC;
```

`n_live_tup` và `n_dead_tup` là ước lượng từ thống kê, không phải phép đếm chính xác tại thời điểm truy vấn. Các hàm kích thước cho biết dung lượng vật lý của relation và index. Có thể dùng chúng để xác định dataset thử nghiệm đã gần với kích thước cần mô phỏng hay chưa.

### Kích thước vật lý cũng quan trọng

Planner ước lượng chi phí dựa trên số trang, thống kê và các cost parameter. Một dataset có cùng số hàng nhưng nhỏ hơn nhiều trong cache có thể tạo ra kết quả kiểm thử lạc quan. Hãy so sánh kích thước heap và index với bộ nhớ khả dụng, đồng thời kiểm tra tỷ lệ buffer hit/read trong workload.

## 5. Tạo dữ liệu thử nghiệm có phân bố lệch

Ví dụ sau tạo bảng đơn hàng với một tenant rất lớn, trạng thái `paid` phổ biến và dữ liệu tập trung trong khoảng thời gian gần đây. Chạy trên database kiểm thử riêng.

```sql
CREATE SCHEMA IF NOT EXISTS bench;

CREATE TABLE bench.orders (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id integer NOT NULL,
    status text NOT NULL,
    created_at timestamptz NOT NULL,
    total_amount numeric(12, 2) NOT NULL
);

SELECT setseed(0.42);

INSERT INTO bench.orders (
    tenant_id,
    status,
    created_at,
    total_amount
)
SELECT
    CASE
        WHEN random() < 0.70 THEN 1
        ELSE 2 + floor(random() * 999)::integer
    END,
    CASE
        WHEN random() < 0.80 THEN 'paid'
        ELSE (ARRAY['pending', 'cancelled', 'refunded'])[
            1 + floor(random() * 3)::integer
        ]
    END,
    CASE
        WHEN random() < 0.85
            THEN now() - random() * interval '14 days'
        ELSE now() - random() * interval '3 years'
    END,
    (10 + random() * 990)::numeric(12, 2)
FROM generate_series(1, 5000000);
```

Với cách tạo này, khoảng 70% hàng thuộc tenant `1`, khoảng 80% hàng có trạng thái `paid`, và phần lớn timestamp nằm trong 14 ngày gần nhất. Các phần còn lại được phân tán để tạo tail và dữ liệu lịch sử. `setseed` đặt seed cho bộ sinh số ngẫu nhiên trong session, giúp lần chạy thử có thể tái lập tốt hơn; nếu cần fixture hoàn toàn bất biến giữa các lần kiểm thử, hãy lưu snapshot dữ liệu đã tạo và quản lý phiên bản của snapshot.

Đây là dữ liệu minh họa. Trong hệ thống thật, nên điều chỉnh tỷ lệ theo số liệu đo được, thêm các mối tương quan thực tế và bảo đảm quan hệ khóa ngoại. Dữ liệu được sinh độc lập cho từng cột như ví dụ chưa mô phỏng tương quan giữa tenant, trạng thái và thời gian.

### Tạo quan hệ cha-con

Khi kiểm thử join, cần có phân bố số hàng con trên mỗi hàng cha. Ví dụ một khách hàng lớn có thể có nhiều đơn hàng, trong khi phần lớn khách hàng chỉ có một vài đơn. Nếu tạo đúng một đơn cho mỗi khách hàng, nested loop join có thể trông tốt hơn so với dữ liệu thực tế.

```sql
CREATE TABLE bench.customers (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id integer NOT NULL,
    region_code text NOT NULL
);

INSERT INTO bench.customers (tenant_id, region_code)
SELECT
    CASE
        WHEN random() < 0.70 THEN 1
        ELSE 2 + floor(random() * 999)::integer
    END,
    (ARRAY['north', 'south', 'central', 'west'])[
        1 + floor(random() * 4)::integer
    ]
FROM generate_series(1, 500000);
```

Để tạo dữ liệu `orders` có quan hệ thật với `customers`, nên sinh `customer_id` từ tập khóa đã tồn tại hoặc tạo bảng ánh xạ có kiểm soát. Không dùng một phép random độc lập trên miền ID nếu nó có thể tạo khóa ngoại không hợp lệ.

### Tạo phân bố có tương quan

Nếu tenant `1` có tỷ lệ thanh toán cao hơn tenant khác, hãy đưa điều kiện đó vào bộ sinh dữ liệu. Ví dụ minh họa:

```sql
SELECT
    CASE WHEN random() < 0.70 THEN 1 ELSE 2 END AS tenant_id,
    CASE
        WHEN random() < 0.70 THEN 'paid'
        ELSE 'pending'
    END AS status;
```

Đoạn truy vấn ngắn trên chỉ minh họa ý tưởng và không bảo đảm tương quan vì hai lần gọi `random()` độc lập. Để tạo tương quan thực sự, hãy dùng một giá trị tenant được sinh trước rồi chọn xác suất status dựa trên giá trị đó trong cùng biểu thức hoặc trong bước sinh dữ liệu có kiểm soát. Ví dụ:

```sql
WITH generated AS (
    SELECT
        CASE WHEN random() < 0.70 THEN 1 ELSE 2 END AS tenant_id,
        random() AS status_roll
    FROM generate_series(1, 100000)
)
SELECT
    tenant_id,
    CASE
        WHEN tenant_id = 1 AND status_roll < 0.95 THEN 'paid'
        WHEN tenant_id <> 1 AND status_roll < 0.35 THEN 'paid'
        ELSE 'pending'
    END AS status
FROM generated;
```

Trong ví dụ này, tenant `1` có tỷ lệ `paid` cao hơn tenant `2`. Khi đưa vào `INSERT`, có thể mở rộng CTE để sinh timestamp, customer và các cột còn lại. Cần giữ lại seed, quy tắc sinh và snapshot để lần kiểm thử sau có thể so sánh trên dữ liệu tương đương.

## 6. Xây dựng ma trận dữ liệu kiểm thử

Không chỉ kiểm thử tenant lớn nhất hoặc giá trị hiếm nhất. Hãy chọn các nhóm tham số đại diện cho cách người dùng và ứng dụng thực sự truy vấn.

| Nhóm dữ liệu | Ví dụ tham số | Mục đích |
|---|---|---|
| Hot value | Tenant chiếm 70% hàng | Kiểm tra truy vấn trả về tập dữ liệu lớn |
| Cold value | Tenant chỉ có vài trăm hàng | Kiểm tra truy vấn có tính chọn lọc cao |
| Giá trị trung bình | Tenant gần median | Kiểm tra trường hợp thông thường |
| Giá trị phổ biến của enum | `paid` | Kiểm tra điều kiện ít chọn lọc |
| Giá trị hiếm | `refunded` | Kiểm tra điều kiện chọn lọc cao |
| Khoảng thời gian gần | 1 ngày, 7 ngày | Kiểm tra dữ liệu nóng và tính cục bộ |
| Khoảng thời gian dài | 1 năm, toàn bộ lịch sử | Kiểm tra scan, partition và tổng hợp lớn |
| Kết hợp tương quan | Tenant lớn + `paid` | Kiểm tra ước lượng đa cột |
| Kết hợp hiếm | Tenant nhỏ + `refunded` | Kiểm tra cardinality rất thấp |

Với mỗi nhóm, ghi lại số hàng thực tế, số hàng ước lượng, thời gian, buffer và kết quả. Tham số phải được lấy từ phân bố thật hoặc bộ dữ liệu đã xác định, không chọn tùy ý một giá trị thuận lợi.

## 7. Cập nhật thống kê cho planner

PostgreSQL dùng `ANALYZE` để thu thập thống kê về phân bố dữ liệu. Sau khi nạp hoặc thay đổi nhiều hàng, hãy chạy `ANALYZE` trước khi đo kế hoạch truy vấn:

```sql
ANALYZE bench.orders;
```

`VACUUM (ANALYZE)` có thể phù hợp sau khi tải hoặc cập nhật/xóa dữ liệu lớn trong môi trường thử nghiệm:

```sql
VACUUM (ANALYZE) bench.orders;
```

`VACUUM` giúp xử lý dead tuples và cập nhật visibility map; `ANALYZE` cập nhật thống kê cho planner. Chúng giải quyết các vấn đề khác nhau. Không dùng `VACUUM FULL` như bước chuẩn bị mặc định cho mọi benchmark vì thao tác này viết lại bảng, cần khóa mạnh và làm thay đổi bố cục vật lý.

### Xem thống kê một cột

```sql
SELECT
    attname,
    null_frac,
    n_distinct,
    most_common_vals,
    most_common_freqs,
    histogram_bounds,
    correlation
FROM pg_stats
WHERE schemaname = 'bench'
  AND tablename = 'orders'
  AND attname IN ('tenant_id', 'status', 'created_at');
```

Các trường có ý nghĩa:

- `null_frac`: tỷ lệ giá trị `NULL` ước lượng.
- `n_distinct`: số giá trị phân biệt ước lượng; giá trị âm biểu thị tỷ lệ so với số hàng.
- `most_common_vals` và `most_common_freqs`: các giá trị phổ biến và tần suất tương ứng.
- `histogram_bounds`: ranh giới histogram cho các giá trị không nằm trong danh sách phổ biến.
- `correlation`: tương quan giữa thứ tự giá trị của cột và thứ tự vật lý của hàng trong bảng, hữu ích cho ước lượng chi phí truy cập index. Đây không phải là thống kê tương quan giữa hai cột.

### Tăng statistics target khi cần

Mặc định, planner lấy mẫu một phần dữ liệu. Với cột lệch mạnh hoặc có nhiều giá trị phổ biến, mẫu mặc định có thể chưa mô tả đủ chi tiết. Có thể tăng statistics target cho cột quan trọng:

```sql
ALTER TABLE bench.orders
    ALTER COLUMN tenant_id SET STATISTICS 1000;

ALTER TABLE bench.orders
    ALTER COLUMN status SET STATISTICS 1000;

ANALYZE bench.orders;
```

Target lớn hơn có thể tạo thống kê chi tiết hơn nhưng tăng thời gian và tài nguyên của `ANALYZE`, đồng thời làm metadata thống kê lớn hơn. Chỉ tăng cho các cột cần thiết và so sánh trước/sau.

### Thống kê đa cột

Khi planner cần ước lượng điều kiện trên nhiều cột có tương quan, có thể tạo extended statistics:

```sql
CREATE STATISTICS bench.orders_tenant_status_stats
    (mcv, dependencies, ndistinct)
ON tenant_id, status
FROM bench.orders;

ANALYZE bench.orders;
```

- `mcv` lưu các tổ hợp giá trị phổ biến của nhiều cột.
- `dependencies` lưu thông tin phụ thuộc thống kê giữa các cột.
- `ndistinct` giúp ước lượng số tổ hợp phân biệt.

Extended statistics áp dụng cho các cột trong cùng một bảng và chỉ cải thiện các dạng ước lượng mà planner hỗ trợ. Chúng không thay thế việc tạo dữ liệu có phân bố đúng hoặc kiểm thử kế hoạch thực tế.

## 8. Đọc kế hoạch bằng `EXPLAIN`

### Phân biệt `EXPLAIN` và `EXPLAIN ANALYZE`

`EXPLAIN` hiển thị kế hoạch dự kiến mà không thực thi câu truy vấn. `EXPLAIN ANALYZE` thực thi truy vấn rồi bổ sung số liệu thực tế. Dùng `ANALYZE` để so sánh ước lượng với số hàng thật, nhưng cần nhớ truy vấn sẽ chạy thật và có thể tiêu tốn tài nguyên hoặc thay đổi dữ liệu.

Ví dụ:

```sql
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF, SUMMARY ON)
SELECT
    id,
    created_at,
    total_amount
FROM bench.orders
WHERE tenant_id = 1
  AND status = 'paid'
  AND created_at >= now() - interval '30 days'
ORDER BY created_at DESC
LIMIT 100;
```

Các thông tin cần đọc:

- **Estimated rows:** số hàng planner dự đoán tại mỗi node.
- **Actual rows:** số hàng thực tế được trả về bởi node; khi có `loops` lớn hơn 1, số hàng hiển thị thường là trung bình mỗi lần lặp, nên cần đọc cùng `loops`.
- **Startup cost / total cost:** chi phí planner ước lượng, không phải thời gian mili giây.
- **Actual time:** thời gian thực thi đo được nếu bật timing; `TIMING OFF` giảm overhead đo thời gian ở từng node.
- **Buffers:** số block shared/local/temp được hit, read, dirtied hoặc written.
- **Planning Time / Execution Time:** thời gian lập kế hoạch và thực thi tổng thể.
- **Rows Removed by Filter:** số hàng bị loại bởi điều kiện lọc tại node.
- **Sort Method / Hash Batches:** cách sort hoặc hash được thực hiện và dấu hiệu vượt bộ nhớ.

Các bộ đếm buffer ở node cha thường bao gồm công việc của node con. Không cộng tất cả buffer ở mọi node như các lượng độc lập.

### Nhận diện sai lệch cardinality

Nếu planner ước lượng 100 hàng nhưng node thực tế trả về 500.000 hàng, sai lệch rất lớn. Sai lệch ở node sớm có thể làm planner chọn sai thứ tự join, nested loop không phù hợp hoặc cấp bộ nhớ không đủ cho hash/sort.

Một cách đọc thực tế:

1. Tìm node đầu tiên có `estimated rows` lệch đáng kể so với `actual rows`.
2. Kiểm tra thống kê của các cột tham gia điều kiện lọc hoặc join.
3. Kiểm tra dữ liệu lệch, tỷ lệ `NULL`, giá trị phổ biến và tương quan cột.
4. Chạy `ANALYZE`, tăng statistics target hoặc tạo extended statistics khi có lý do.
5. Đo lại trên cùng dataset và cùng tham số.

Đừng chỉ nhìn node gốc. Sai lệch có thể bắt đầu ở một scan nhỏ phía dưới và lan lên các node join hoặc aggregate.

### Sequential scan không phải lúc nào cũng xấu

Nếu một điều kiện trả về phần lớn hàng, đọc tuần tự có thể rẻ hơn đi qua index rồi truy cập heap nhiều lần. Ngược lại, với tham số hiếm, index scan hoặc bitmap scan có thể tốt hơn. Mục tiêu kiểm thử là xác định planner chọn phương án phù hợp cho các nhóm tham số khác nhau, không phải ép mọi truy vấn dùng index.

Có thể tạm tắt một phương án planner trong session thử nghiệm để hiểu lựa chọn thay thế, nhưng các `enable_*` setting chỉ nên dùng như công cụ chẩn đoán. Không dùng chúng như giải pháp mặc định trong production nếu chưa có bằng chứng và đánh giá tác động rộng.

## 9. Đo buffer, I/O và spill ra đĩa

Thời gian chạy đơn lẻ không cho biết truy vấn đang bị giới hạn bởi CPU, cache hay lưu trữ. `BUFFERS` giúp phân biệt block đã có trong shared buffers với block cần đọc từ storage.

```sql
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF)
SELECT
    tenant_id,
    status,
    count(*) AS order_count,
    sum(total_amount) AS amount
FROM bench.orders
WHERE created_at >= now() - interval '90 days'
GROUP BY tenant_id, status;
```

Quan sát:

- `shared hit`: block đã có trong PostgreSQL shared buffers.
- `shared read`: block được đọc vào shared buffers từ tầng lưu trữ bên dưới; block vẫn có thể được phục vụ từ OS page cache.
- `temp read`/`temp written`: dữ liệu tạm được đọc/ghi, thường liên quan đến sort hoặc hash vượt giới hạn bộ nhớ.
- `local`: block thuộc temporary relation trong session.

`shared read` không đồng nghĩa chắc chắn với một lần đọc vật lý từ ổ đĩa; hệ điều hành có thể trả dữ liệu từ page cache. Nếu cần đo I/O thời gian, có thể xem xét `track_io_timing` trong môi trường kiểm thử và các số liệu hệ điều hành.

### Nhận diện sort và hash spill

Một sort lớn có thể hiển thị `Sort Method: external merge` và lượng disk sử dụng. Hash join hoặc hash aggregate có thể chia thành nhiều batch khi hash table không vừa bộ nhớ. Đây là tín hiệu cần xem xét kích thước dữ liệu, điều kiện lọc, index và `work_mem`.

Không tăng `work_mem` toàn cục chỉ để làm một truy vấn thử nghiệm hết spill. Mỗi truy vấn có thể có nhiều thao tác sort/hash, và nhiều session chạy đồng thời sẽ nhân mức tiêu thụ bộ nhớ. Hãy đo concurrency và cân nhắc điều chỉnh theo role hoặc session trong workload phù hợp.

## 10. Kiểm thử tham số phổ biến và hiếm

Một truy vấn tham số hóa có thể có kế hoạch tốt với tenant nhỏ nhưng kém với tenant lớn, hoặc ngược lại. Vì vậy, cần chạy cùng một câu SQL với nhiều nhóm tham số:

```sql
PREPARE tenant_orders(integer, timestamptz) AS
SELECT id, created_at, total_amount
FROM bench.orders
WHERE tenant_id = $1
  AND created_at >= $2
ORDER BY created_at DESC
LIMIT 100;

EXPLAIN (ANALYZE, BUFFERS, TIMING OFF)
EXECUTE tenant_orders(1, now() - interval '30 days');

EXPLAIN (ANALYZE, BUFFERS, TIMING OFF)
EXECUTE tenant_orders(777, now() - interval '30 days');

DEALLOCATE tenant_orders;
```

Tenant `1` đại diện cho hot value trong dataset minh họa; `777` đại diện một tenant trong tail. Kết quả cụ thể phụ thuộc dữ liệu đã sinh và có thể cần kiểm tra tenant có thực sự tồn tại.

### Generic plan và custom plan

Với prepared statement, PostgreSQL có thể dùng custom plan dựa trên giá trị tham số cụ thể hoặc generic plan không phụ thuộc vào từng giá trị. Cơ chế tự chọn phụ thuộc lịch sử thực thi và chi phí ước lượng. Nếu phân bố tham số lệch mạnh, một generic plan có thể không tối ưu cho mọi nhóm tham số.

Trong session kiểm thử, có thể so sánh:

```sql
SET plan_cache_mode = force_custom_plan;
-- Chạy EXPLAIN EXECUTE với tham số hot và cold.

SET plan_cache_mode = force_generic_plan;
-- Chạy lại cùng câu lệnh với các tham số tương tự.

RESET plan_cache_mode;
```

Đây là phép thử chẩn đoán. Không nên ép custom hoặc generic plan toàn hệ thống chỉ dựa trên một truy vấn. Hãy kiểm tra driver có dùng prepared statements hay không, cách pooler quản lý session và thời gian sống của prepared statement trong môi trường thật.

## 11. Kiểm thử index với dữ liệu lệch

Index có hiệu quả khác nhau tùy độ chọn lọc, thứ tự cột, kích thước hàng và phân bố truy cập. Ví dụ:

```sql
CREATE INDEX orders_tenant_created_idx
    ON bench.orders (tenant_id, created_at DESC);

CREATE INDEX orders_tenant_status_created_idx
    ON bench.orders (tenant_id, status, created_at DESC);

ANALYZE bench.orders;
```

Hãy so sánh truy vấn theo tenant lớn và tenant nhỏ, theo trạng thái phổ biến và hiếm, cũng như khoảng thời gian ngắn và dài. Một index có nhiều cột không tự động tốt hơn index ít cột. Thứ tự cột ảnh hưởng đến các điều kiện có thể sử dụng và thứ tự dữ liệu trong B-tree.

### Kiểm tra index-only scan

Index-only scan chỉ tránh heap fetch hiệu quả khi visibility map cho biết các page liên quan all-visible. Sau một đợt nạp dữ liệu, cập nhật hoặc xóa lớn, điều kiện này có thể khác production. Chạy vacuum phù hợp trong môi trường kiểm thử và quan sát `Heap Fetches` trong plan. Không suy luận rằng index-only scan luôn không truy cập heap chỉ từ tên node.

### Đo chi phí ghi

Index cải thiện một số truy vấn đọc nhưng làm tăng công việc khi insert/update/delete, chiếm dung lượng và tăng bảo trì. Cần chạy workload ghi hỗn hợp khi so sánh index. Đừng chỉ benchmark SELECT rồi thêm mọi index có thể nghĩ ra.

## 12. Kiểm thử join với cardinality thực tế

Một phép join phụ thuộc vào số hàng ở hai phía, phân bố khóa, tỷ lệ trùng lặp và số hàng khớp. Ví dụ:

```sql
SELECT
    o.tenant_id,
    c.region_code,
    count(*) AS order_count,
    sum(o.total_amount) AS total_amount
FROM bench.orders AS o
JOIN bench.customers AS c
  ON c.tenant_id = o.tenant_id
WHERE o.created_at >= now() - interval '30 days'
GROUP BY o.tenant_id, c.region_code;
```

Ví dụ trên minh họa join theo tenant và có thể tạo nhiều hàng khớp ở cả hai phía, dẫn đến nhân bản kết quả. Trong mô hình thực tế, thường cần join theo khóa customer cụ thể. Khi tạo fixture, hãy bảo đảm khóa join phản ánh đúng quan hệ nghiệp vụ và cardinality.

Khi đọc plan, kiểm tra:

- Số hàng ở mỗi đầu vào của join.
- Số hàng sau join và số hàng thực tế được nhân lên.
- `Nested Loop`, `Hash Join` hay `Merge Join` được chọn.
- Hash table có spill thành nhiều batch hay không.
- Index join key có phù hợp và có được sử dụng không.
- Điều kiện lọc có thể được đẩy xuống scan trước khi join không.

Một nested loop có thể rất tốt khi phía ngoài chỉ có vài hàng và phía trong có index phù hợp. Cùng kế hoạch đó có thể rất tệ khi phía ngoài thực tế có hàng triệu hàng do ước lượng sai.

## 13. Kiểm thử phân vùng

Nếu bảng production được partition theo thời gian hoặc tenant, dataset thử nghiệm phải có số lượng partition, kích thước từng partition và ranh giới giống dự kiến. Một bảng nhỏ với hai partition không đại diện cho bảng có hàng trăm partition.

Ví dụ tạo bảng partition theo tháng:

```sql
CREATE TABLE bench.events (
    id bigint NOT NULL,
    occurred_at timestamptz NOT NULL,
    tenant_id integer NOT NULL,
    payload jsonb
) PARTITION BY RANGE (occurred_at);

CREATE TABLE bench.events_2026_01
    PARTITION OF bench.events
    FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');

CREATE TABLE bench.events_2026_02
    PARTITION OF bench.events
    FOR VALUES FROM ('2026-02-01') TO ('2026-03-01');
```

Truy vấn có điều kiện trên partition key có thể loại bỏ các partition không liên quan (partition pruning):

```sql
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF)
SELECT count(*)
FROM bench.events
WHERE occurred_at >= timestamptz '2026-02-01 00:00:00+00'
  AND occurred_at <  timestamptz '2026-03-01 00:00:00+00';
```

Kiểm thử cả literal và bind parameter, vì pruning có thể diễn ra ở các giai đoạn khác nhau tùy plan và tham số. Đánh giá số partition được truy cập, chi phí planning, index từng partition, dữ liệu ở partition mặc định và truy vấn không có điều kiện trên partition key.

## 14. Tạo workload có mức đồng thời đại diện

Một truy vấn chạy một mình có thể nhanh, nhưng nhiều session chạy cùng lúc có thể cạnh tranh CPU, I/O, buffer, lock và connection. Workload kiểm thử nên bao gồm tỷ lệ truy vấn đọc/ghi, truy vấn ngắn/dài, thời gian chờ giữa các thao tác và phân bố tham số.

### Dùng `pgbench`

`pgbench` là công cụ đi kèm PostgreSQL để tạo tải đồng thời. Có thể dùng script SQL tùy chỉnh:

```text
\set p random(1, 100)
\if :p <= 70
  \set tenant_id 1
\else
  \set tenant_id random(2, 1000)
\endif

SELECT count(*)
FROM bench.orders
WHERE tenant_id = :tenant_id
  AND status = 'paid';
```

Script này tạo khoảng 70% lượt truy vấn cho tenant nóng `1`, còn lại chọn tenant trong tail. Cú pháp meta-command có thể phụ thuộc phiên bản `pgbench`; hãy xác nhận trên phiên bản công cụ đang cài. Nếu phiên bản không hỗ trợ biểu thức mong muốn, tạo file tham số hoặc driver workload riêng với phân bố xác định.

Chạy thử 32 client, 8 worker trong 5 phút:

```bash
pgbench -M prepared \
  -f tenant_lookup.sql \
  -c 32 \
  -j 8 \
  -T 300 \
  -P 10 \
  -r \
  -l \
  benchmark_db
```

Các tùy chọn chính:

- `-f`: file script SQL.
- `-M prepared`: dùng prepared statements cho script.
- `-c`: số client đồng thời.
- `-j`: số worker thread của pgbench.
- `-T`: thời gian chạy tính bằng giây.
- `-P`: in tiến độ định kỳ.
- `-r`: báo cáo độ trễ theo lệnh trong script.
- `-l`: ghi log giao dịch để phân tích chi tiết hơn.

Chạy trên database kiểm thử riêng. Không dùng `pgbench -i` trên database có dữ liệu cần giữ vì bước khởi tạo có thể tạo/xóa các bảng benchmark chuẩn.

### Tái hiện tỷ lệ truy vấn

Không phải mọi truy vấn đều có tần suất như nhau. Có thể dùng `pg_stat_statements`, application trace hoặc log đã ẩn thông tin nhạy cảm để xác định:

- Top truy vấn theo tổng thời gian và số lần gọi.
- Tỷ lệ truy vấn theo mẫu SQL.
- Tỷ lệ tham số hot/cold.
- Tỷ lệ đọc/ghi và transaction ngắn/dài.
- Khoảng thời gian cao điểm và số client đồng thời.

Một workload chỉ chạy truy vấn SELECT đơn giản không thể đại diện cho hệ thống có dashboard, ETL batch, ghi giao dịch và CDC cùng hoạt động. Cần tạo workload hỗn hợp theo tỷ lệ thực tế.

## 15. Đo latency, throughput và độ ổn định

Các chỉ số nên được đo cùng nhau:

- **Throughput:** số giao dịch hoặc truy vấn hoàn thành trong một đơn vị thời gian.
- **Latency:** thời gian hoàn thành của một giao dịch hoặc truy vấn.
- **p50:** độ trễ trung vị.
- **p95/p99:** độ trễ mà 95%/99% thao tác không vượt quá; phản ánh tail latency.
- **Error rate:** tỷ lệ timeout, lỗi SQL, lỗi kết nối và retry.
- **Resource use:** CPU, RAM, I/O, WAL, connection và lock wait.

Throughput tăng không đồng nghĩa trải nghiệm tốt hơn nếu p99 tăng mạnh hoặc tỷ lệ lỗi cao. Khi concurrency vượt khả năng hệ thống, hàng đợi và lock contention có thể khiến tail latency tăng đột biến.

### Đặt tiêu chí chấp nhận trước khi chạy

Ví dụ một tiêu chí cho dashboard:

| Chỉ số | Ngưỡng minh họa |
|---|---:|
| p95 truy vấn chính | Dưới 500 ms |
| p99 truy vấn chính | Dưới 1.5 s |
| Lỗi truy vấn | Dưới 0.1% |
| Replication lag | Dưới 10 giây |
| CPU trung bình trong bài tải | Dưới 70% |

Các con số chỉ minh họa cách viết tiêu chí. Ngưỡng thật phải dựa vào SLA, loại truy vấn, hạ tầng và mức độ quan trọng của ứng dụng. Ghi nhận cả điều kiện chạy để kết quả có thể so sánh.

## 16. Cache nóng và cache lạnh

Lần chạy đầu có thể phải đọc nhiều block từ tầng lưu trữ; các lần chạy sau có thể nhanh hơn vì dữ liệu nằm trong shared buffers hoặc OS page cache. Nếu chỉ đo lần thứ hai, kết quả có thể lạc quan hơn một workload mà truy vấn liên tục thay đổi vùng dữ liệu.

Nên phân biệt:

- **Warm-cache test:** chạy nhiều vòng trên cùng tập dữ liệu để đo workload khi cache đã nóng.
- **Cold-ish test:** dùng dataset lớn hơn cache hoặc truy cập các vùng dữ liệu khác nhau để giảm tỷ lệ tái sử dụng cache.
- **Mixed test:** kết hợp dữ liệu nóng và dữ liệu lịch sử theo tỷ lệ thực tế.

Không có cách đơn giản, an toàn và portable để làm sạch đồng thời shared buffers và OS page cache trên mọi môi trường. Không chạy lệnh xóa page cache hoặc restart database production chỉ để tạo cache lạnh. Hãy dùng instance thử nghiệm riêng, snapshot mới hoặc dataset đủ lớn để mô phỏng điều kiện cần đo.

## 17. Bảo đảm môi trường kiểm thử có thể so sánh

Kết quả benchmark chỉ có ý nghĩa khi điều kiện giữa các lần chạy được ghi lại. Các yếu tố cần kiểm soát gồm:

- Phiên bản PostgreSQL và extension.
- CPU, RAM, loại storage, IOPS và filesystem.
- `shared_buffers`, `work_mem`, `effective_cache_size`, `maintenance_work_mem`.
- `max_connections`, parallel worker và cấu hình autovacuum.
- Index, partition, constraint và trạng thái vacuum/analyze.
- Số client, số worker, tỷ lệ truy vấn và tham số đầu vào.
- Cache state, thời lượng warm-up và thời gian đo.
- Các job nền, backup, checkpoint và replication đang chạy.

Không thay đổi nhiều biến cùng lúc rồi kết luận biến nào cải thiện hiệu năng. Khi so sánh hai phương án, chỉ thay đổi yếu tố đang nghiên cứu hoặc ghi rõ mọi thay đổi khác.

### Ghi nhận cấu hình server

```sql
SELECT name, setting, unit, source
FROM pg_settings
WHERE name IN (
    'shared_buffers',
    'work_mem',
    'effective_cache_size',
    'maintenance_work_mem',
    'max_connections',
    'max_parallel_workers',
    'max_parallel_workers_per_gather',
    'random_page_cost',
    'effective_io_concurrency'
)
ORDER BY name;
```

Lưu kết quả cùng báo cáo benchmark để có thể so sánh giữa môi trường và giữa các lần triển khai.

## 18. Quan sát workload bằng `pg_stat_statements`

Extension `pg_stat_statements` thu thập thống kê về các câu lệnh SQL đã thực thi. Extension cần được cài đặt và cấu hình theo hướng dẫn của phiên bản PostgreSQL, thường liên quan đến `shared_preload_libraries` và việc tạo extension trong database.

Ví dụ truy vấn các statement tốn tổng thời gian nhiều:

```sql
SELECT
    queryid,
    calls,
    total_exec_time,
    mean_exec_time,
    rows,
    shared_blks_hit,
    shared_blks_read,
    temp_blks_written,
    left(query, 250) AS query_sample
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
```

Tên cột có thể khác giữa các phiên bản PostgreSQL và phiên bản extension; ví dụ trên dùng các trường của phiên bản hiện đại. Hãy xem schema thực tế trước khi tự động hóa truy vấn giám sát.

`pg_stat_statements` giúp tìm query pattern đắt đỏ, nhưng thường chuẩn hóa literal nên không tự cho biết đầy đủ phân bố tham số hot/cold. Muốn kiểm thử tham số, cần lấy mẫu giá trị từ trace ứng dụng đã được xử lý dữ liệu nhạy cảm hoặc tạo bộ tham số có phân bố rõ ràng.

## 19. Kiểm thử truy vấn ghi và tác động phụ

`EXPLAIN ANALYZE` với `INSERT`, `UPDATE` hoặc `DELETE` thực thi câu lệnh thật. Một transaction rollback có thể giúp hoàn tác thay đổi dữ liệu transactional trong môi trường thử nghiệm:

```sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS, WAL, TIMING OFF)
UPDATE bench.orders
SET status = 'refunded'
WHERE tenant_id = 1
  AND status = 'paid'
  AND created_at < now() - interval '2 years';

ROLLBACK;
```

Ví dụ này có thể cập nhật nhiều hàng, nên chỉ chạy trên database kiểm thử. Rollback không làm cho mọi tác động biến mất: sequence không rollback giá trị đã cấp, trigger có thể gọi hệ thống bên ngoài, extension hoặc hàm có thể có tác dụng phụ ngoài transaction. Hãy kiểm tra trigger và hàm liên quan trước khi chạy.

`WAL` trong `EXPLAIN` giúp quan sát lượng WAL phát sinh cho thao tác được đo trên các phiên bản hỗ trợ tùy chọn này. Nếu mục tiêu là kiểm thử độ bền của transaction và checkpoint, cần workload kéo dài hơn và đo ở cấp hệ thống, không chỉ dựa vào một câu lệnh.

## 20. Kiểm thử sau khi thay đổi index hoặc schema

Khi thêm index, đổi partition, thay đổi kiểu cột hoặc cập nhật phiên bản PostgreSQL, hãy chạy lại cùng một bộ benchmark:

1. Giữ nguyên dataset và workload.
2. Ghi lại kế hoạch trước thay đổi.
3. Thực hiện migration trên môi trường thử nghiệm.
4. Chạy `ANALYZE` hoặc quy trình vacuum phù hợp.
5. Chạy lại từng nhóm tham số và mức concurrency.
6. So sánh latency, throughput, buffer, I/O, CPU, WAL và lỗi.
7. Kiểm tra cả workload ghi để phát hiện chi phí phụ của index hoặc schema mới.

Nếu kết quả khác đáng kể, xác định thay đổi đến từ planner statistics, plan shape, cache, dữ liệu, cấu hình hay workload. Không kết luận migration tốt hơn chỉ vì một truy vấn mẫu chạy nhanh hơn.

## 21. Quy trình kiểm thử hiệu năng truy vấn

Một quy trình có thể áp dụng trong dự án:

1. **Chọn truy vấn trọng yếu:** lấy từ dashboard, API, ETL hoặc `pg_stat_statements`.
2. **Xác định tiêu chí:** p95/p99, throughput, error rate, thời gian batch và mức tài nguyên chấp nhận.
3. **Lập hồ sơ dữ liệu:** quy mô, skew, cardinality, tương quan, null, độ rộng hàng và phân bố thời gian.
4. **Tạo hoặc khử định danh dữ liệu:** dùng snapshot được phép hoặc bộ sinh dữ liệu tái lập; giữ quan hệ và đặc tính phân bố.
5. **Nạp đến quy mô mục tiêu:** tạo index/partition/constraint như production và chạy `ANALYZE`.
6. **Chạy kiểm tra đơn truy vấn:** dùng `EXPLAIN (ANALYZE, BUFFERS)` với tham số hot, cold và trung bình.
7. **Chạy tải đồng thời:** tái hiện tỷ lệ query, số client và mẫu đọc/ghi.
8. **Đo nhiều vòng:** có warm-up, thời gian đo đủ dài, p50/p95/p99 và error rate.
9. **Phân tích kế hoạch:** tìm node sai lệch cardinality, scan, join, sort/hash spill và buffer/I/O.
10. **Thay đổi có kiểm soát:** cập nhật statistics, index hoặc cấu hình từng bước rồi benchmark lại.
11. **Lưu kết quả:** phiên bản, dataset, seed/snapshot, cấu hình, script, tham số, plan và metric.
12. **Đặt ngưỡng hồi quy:** tự động cảnh báo khi latency hoặc tài nguyên vượt ngưỡng đã thống nhất.

## 22. Mẫu báo cáo benchmark

Một báo cáo nên có đủ thông tin để người khác tái hiện:

| Trường | Nội dung cần ghi |
|---|---|
| Mã kiểm thử | Tên truy vấn hoặc workload |
| Commit/migration | Phiên bản mã và schema |
| PostgreSQL | Phiên bản server, extension liên quan |
| Dataset | Snapshot/seed, số hàng và kích thước heap/index |
| Phân bố | Tỷ lệ hot/cold, enum, thời gian, null và tương quan |
| Thống kê | Thời điểm `ANALYZE`, statistics target, extended statistics |
| Cấu hình | CPU, RAM, storage và các setting quan trọng |
| Tham số | Nhóm giá trị được chạy và tỷ trọng từng nhóm |
| Tải | Số client, worker, thời lượng, tỷ lệ đọc/ghi |
| Kết quả | p50/p95/p99, throughput, lỗi, CPU, I/O, buffer, WAL |
| Kế hoạch | EXPLAIN trước/sau và sai lệch ước lượng |
| Kết luận | Ngưỡng đạt/trượt, nguyên nhân và việc cần làm tiếp |

Không chỉ lưu ảnh chụp màn hình hoặc một con số tổng hợp. Hãy lưu script, SQL, cấu hình, plan dạng văn bản/JSON và dữ liệu đầu vào cần thiết để có thể tái hiện kết quả.

## 23. Các lỗi thường gặp khi kiểm thử

- Chỉ dùng vài nghìn hàng và suy rộng kết quả cho bảng hàng triệu hàng.
- Sinh mọi giá trị bằng phân bố đều trong khi production có hot value.
- Không tái hiện tương quan giữa các cột.
- Không chạy `ANALYZE` sau khi nạp hoặc biến đổi dữ liệu lớn.
- So sánh hai plan với cache state, tham số hoặc concurrency khác nhau.
- Chỉ đo một lần và báo cáo thời gian thấp nhất.
- Chỉ đo SELECT mà bỏ qua tác động index lên ghi.
- Cộng dồn buffer ở mọi node EXPLAIN dù node cha bao gồm node con.
- Đọc `shared read` như thể chắc chắn là đọc vật lý từ ổ đĩa.
- Ép planner dùng index thay vì tìm hiểu vì sao sequential scan rẻ hơn.
- Dùng một prepared statement nhưng chỉ kiểm tra một giá trị tham số.
- Chỉ đo throughput mà bỏ qua p95/p99 và error rate.
- Chạy `EXPLAIN ANALYZE` câu lệnh ghi trên database production mà không đánh giá tác động.
- Không lưu lại dataset, cấu hình, script và kế hoạch nên không thể tái lập.
- Dùng dữ liệu có thông tin cá nhân thật trong môi trường kiểm thử không được bảo vệ.

## 24. Bài tập thực hành

### Bài 1: Tạo dữ liệu lệch theo tenant

Tạo bảng đơn hàng có ít nhất một triệu hàng, trong đó một tenant chiếm khoảng 70% dữ liệu và phần còn lại phân tán trên nhiều tenant. Đo số hàng theo tenant và xác nhận tỷ lệ trước khi benchmark.

### Bài 2: So sánh hot value và cold value

Chạy cùng một truy vấn với tenant nóng và tenant nhỏ. Lưu `EXPLAIN (ANALYZE, BUFFERS)` và so sánh estimated rows, actual rows, node scan và buffer.

### Bài 3: Kiểm tra thống kê một cột

Xem `pg_stats` trước và sau `ANALYZE`. Tăng statistics target cho cột lệch, chạy `ANALYZE` lại và ghi nhận thay đổi trong ước lượng.

### Bài 4: Kiểm tra tương quan nhiều cột

Tạo dữ liệu trong đó tenant lớn có tỷ lệ `paid` cao hơn tenant nhỏ. So sánh ước lượng trước và sau khi tạo extended statistics `mcv`/`dependencies`.

### Bài 5: Đo nhiều mức dữ liệu

Tạo các dataset 100 nghìn, 1 triệu và 5 triệu hàng với cùng phân bố. Đo thời gian, buffer, kích thước index và kế hoạch. Giải thích tại sao tốc độ không tăng tuyến tính.

### Bài 6: Kiểm thử prepared statement

Tạo prepared statement và chạy với hot/cold parameter. So sánh `force_custom_plan` với `force_generic_plan` trong session thử nghiệm.

### Bài 7: Kiểm tra spill

Chạy truy vấn group/sort trên dữ liệu lớn. Quan sát sort method, hash batches và temp blocks. Thử điều chỉnh `work_mem` theo session rồi đo lại ở cả mức concurrency.

### Bài 8: Kiểm thử tải đồng thời

Viết script `pgbench` có tỷ lệ hot/cold. Chạy với 1, 8, 32 và 64 client; ghi throughput, p95/p99 và error rate.

### Bài 9: So sánh cache nóng và hỗn hợp

Chạy lặp lại cùng một workload để đo warm cache. Sau đó thay đổi vùng dữ liệu truy cập hoặc dùng dataset lớn hơn cache để mô phỏng workload hỗn hợp.

### Bài 10: Kiểm tra hồi quy sau khi thêm index

Benchmark trước/sau index với cả truy vấn đọc và ghi. Đánh giá lợi ích đọc, chi phí insert/update, dung lượng và thời gian bảo trì.

## 25. Câu hỏi ôn tập

**1. Vì sao số hàng bằng nhau chưa đủ để dataset kiểm thử đại diện?**

Vì phân bố giá trị, cardinality, tương quan, tỷ lệ null, độ rộng hàng, kích thước index và tính cục bộ thời gian đều ảnh hưởng đến ước lượng planner và chi phí truy cập.

**2. Dữ liệu lệch có thể làm thay đổi kế hoạch truy vấn như thế nào?**

Một điều kiện lọc có thể trả về phần lớn hàng với hot value nhưng chỉ vài hàng với cold value. Planner có thể cần chọn sequential scan cho trường hợp đầu và index scan cho trường hợp sau.

**3. `ANALYZE` có tác dụng gì?**

Thu thập thống kê về phân bố dữ liệu để planner ước lượng cardinality và chi phí. Sau khi nạp hoặc thay đổi nhiều dữ liệu, thống kê cũ có thể không còn đại diện.

**4. `pg_stats.correlation` mô tả điều gì?**

Nó mô tả tương quan giữa thứ tự giá trị của một cột và thứ tự vật lý của hàng trong bảng. Nó không phải là hệ số tương quan giữa hai cột.

**5. Khi nào nên dùng extended statistics?**

Khi các điều kiện trên nhiều cột cùng một bảng có tương quan và planner ước lượng sai tổ hợp giá trị. Các loại `mcv`, `dependencies` và `ndistinct` hỗ trợ các dạng ước lượng khác nhau.

**6. Vì sao cần thử tham số hot và cold với prepared statement?**

Vì generic plan có thể không tối ưu cho mọi giá trị khi phân bố tham số lệch mạnh. Cần xem hành vi custom/generic plan và cách driver thực sự gửi truy vấn.

**7. `EXPLAIN ANALYZE` có an toàn với mọi câu lệnh không?**

Không. Nó thực thi câu lệnh. Với DML, dữ liệu có thể bị thay đổi; rollback cũng không hoàn tác mọi tác dụng phụ ngoài transaction. Hãy dùng môi trường thử nghiệm.

**8. Vì sao cần đo p95 và p99?**

Trung bình có thể che giấu một nhóm request rất chậm. Percentile tail phản ánh trải nghiệm của các request chậm và giúp xác định mức ổn định dưới tải.

**9. `shared read` có đồng nghĩa đọc từ đĩa vật lý không?**

Không nhất thiết. PostgreSQL phải đọc block vào shared buffers, nhưng OS page cache có thể phục vụ yêu cầu đó mà không cần đọc thiết bị lưu trữ.

**10. Vì sao benchmark phải có workload đồng thời?**

Vì nhiều session cạnh tranh CPU, I/O, bộ nhớ, lock và connection. Kế hoạch chạy nhanh một mình chưa chắc đáp ứng p95/p99 khi có tải thật.

**11. Khi nào sequential scan là lựa chọn hợp lý?**

Khi điều kiện trả về tỷ lệ lớn của bảng hoặc đọc tuần tự rẻ hơn nhiều lần truy cập heap thông qua index. Không phải mọi truy vấn đều nên dùng index.

**12. Tại sao cần lưu snapshot hoặc seed dữ liệu?**

Để lần benchmark sau dùng dữ liệu tương đương, giúp phân biệt thay đổi hiệu năng do code/configuration với thay đổi do dataset.

## 26. Kết luận

Kiểm thử truy vấn PostgreSQL với dữ liệu lệch và dung lượng đại diện đòi hỏi tái hiện được các đặc điểm chi phối planner và workload: quy mô bảng, kích thước vật lý, hot/cold values, tương quan cột, thời gian, cardinality, tham số truy vấn và mức đồng thời. Hãy dùng `ANALYZE`, `pg_stats`, extended statistics và `EXPLAIN (ANALYZE, BUFFERS)` để hiểu chênh lệch giữa ước lượng với thực tế; sau đó benchmark cả latency, throughput, tail latency và tài nguyên trong điều kiện có thể lặp lại. Kết quả chỉ đáng tin khi dataset, cấu hình, tham số và cách chạy được ghi lại rõ ràng.
