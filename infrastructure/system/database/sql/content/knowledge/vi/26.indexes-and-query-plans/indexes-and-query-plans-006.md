# Phân biệt kế hoạch ước lượng với kế hoạch có thực thi trong SQL

Khi một truy vấn chạy chậm, chúng ta thường muốn biết hệ quản trị cơ sở dữ liệu **định thực hiện truy vấn như thế nào**: đọc toàn bảng hay dùng chỉ mục, lọc trước hay nối bảng trước, sắp xếp ở đâu, ước lượng bao nhiêu dòng và mất bao nhiêu công xử lý.

Trong PostgreSQL, hai cách quan sát quan trọng nhất là:

- **`EXPLAIN`**: yêu cầu bộ tối ưu hóa (*query planner/optimizer*) tạo và hiển thị **kế hoạch ước lượng**, nhưng **không thực thi truy vấn chính**.
- **`EXPLAIN ANALYZE`**: **thực thi truy vấn**, thu thập số liệu khi chạy và hiển thị **kế hoạch cùng thống kê thực tế**.

Sự khác nhau không chỉ là số lượng thông tin. Nó ảnh hưởng trực tiếp tới cách bạn đọc `cost`, `rows`, `actual time`, `loops`, khả năng đánh giá hiệu quả chỉ mục và **mức độ an toàn của phép đo**.

> **`EXPLAIN` trả lời “bộ tối ưu hóa dự kiến làm gì?”; `EXPLAIN ANALYZE` giúp trả lời “truy vấn đã chạy ra sao trong lần đo này?”**

Bài thuộc module **Database SQL**, chương **Chỉ mục và kế hoạch**, sử dụng PostgreSQL làm hệ quản trị chính. Các ví dụ tập trung vào cách đối chiếu **ước lượng với thực thi**, không coi mọi kế hoạch khác nhau là lỗi hay mặc định **Index Scan luôn tốt hơn Sequential Scan**.

## 1. Kế hoạch thực thi là gì?

Một câu SQL khai báo **kết quả cần lấy**, nhưng thường không chỉ định chi tiết mọi thao tác nội bộ. Chẳng hạn:

```sql
SELECT
    order_id,
    order_date,
    total_amount
FROM orders
WHERE customer_id = 42
ORDER BY order_date DESC
LIMIT 5;
```

Để trả kết quả, PostgreSQL phải quyết định nhiều điều:

- Đọc bảng `orders` bằng **Sequential Scan** hay **Index Scan**?
- Có thể dùng một chỉ mục phù hợp để tìm `customer_id = 42` không?
- Kết quả cần `Sort` hay chỉ mục đã cung cấp đúng thứ tự?
- Chỉ trả 5 dòng cuối cùng, vậy có thể dừng sớm nhờ `LIMIT` không?
- Bao nhiêu dòng sẽ khớp điều kiện?
- Chi phí đọc các trang dữ liệu và xử lý CPU dự kiến là bao nhiêu?

**Kế hoạch truy vấn** là cấu trúc các thao tác mà bộ tối ưu hóa chọn. Trong PostgreSQL nó thường được hiển thị dưới dạng **cây các nút** (*plan nodes*).

Ví dụ minh họa:

```text
Limit
  └─ Index Scan using idx_orders_customer_date on orders
       Index Cond: (customer_id = 42)
```

Đọc từ dưới lên:

1. `Index Scan` tìm các dòng theo điều kiện khóa chỉ mục.
2. `Limit` chỉ yêu cầu một lượng dòng cần thiết.
3. Kết quả được trả theo thứ tự phù hợp nếu chỉ mục và điều kiện truy vấn cho phép.

Một kế hoạch khác có thể là:

```text
Limit
  └─ Sort
       Sort Key: order_date DESC
       └─ Seq Scan on orders
            Filter: (customer_id = 42)
```

Hai kế hoạch có thể cho **cùng kết quả SQL**, nhưng chi phí và thời gian thực thi khác nhau tùy kích thước bảng, phân bố dữ liệu, chỉ mục, bộ nhớ và trạng thái cache.

**Chú ý:** tên nút và hình dạng kế hoạch trong ví dụ chỉ minh họa. PostgreSQL có thể chọn kế hoạch khác tùy phiên bản, cấu hình và thống kê.

## 2. Hai cấp độ quan sát: dự kiến và đã thực hiện

| Đặc điểm | `EXPLAIN` | `EXPLAIN ANALYZE` |
|---|---|---|
| Thực thi truy vấn chính? | **Không** | **Có** |
| Hiển thị cấu trúc kế hoạch? | Có | Có |
| Hiển thị `cost` ước lượng? | Có | Có |
| Hiển thị `rows` ước lượng? | Có | Có |
| Hiển thị `width` ước lượng? | Có | Có |
| Hiển thị `actual time`? | Không | Có, nếu bật đo thời gian nút |
| Hiển thị `actual rows` và `loops`? | Không | Có |
| Có thể hiển thị bộ đệm `BUFFERS`? | Dùng trong phép đo `ANALYZE` theo cách thông thường | Có |
| Có thể làm thay đổi dữ liệu khi dùng với DML? | Không thực thi DML chính | **Có, thực thi DML thật** |
| Phù hợp để xem trước `UPDATE`/`DELETE`? | Có, để hiểu kế hoạch dự kiến | Chỉ khi chấp nhận tác động hoặc kiểm soát rollback |
| Có thể dùng làm phép đo hiệu năng đã quan sát? | Không | Có, nhưng phải hiểu sai số phép đo |

**Kết luận nền tảng:** kế hoạch ước lượng không phải bản ghi về những gì đã diễn ra. Ngược lại, kế hoạch có thực thi cũng chỉ là quan sát **một hoặc một số lần chạy** trong điều kiện cụ thể, không phải lời hứa về mọi lần chạy tương lai.

### 2.1. Cú pháp cơ bản

Xem kế hoạch dự kiến:

```sql
EXPLAIN
SELECT *
FROM orders
WHERE customer_id = 42;
```

Vừa thực thi vừa đo:

```sql
EXPLAIN ANALYZE
SELECT *
FROM orders
WHERE customer_id = 42;
```

Dạng tùy chọn rõ ràng:

```sql
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF)
SELECT *
FROM orders
WHERE customer_id = 42;
```

Với `TIMING OFF`, PostgreSQL không thu thập thời gian ở từng nút theo cách thông thường, giúp giảm phần overhead đo thời gian nút; **thời gian thực thi tổng thể vẫn có thể được hiển thị**.

## 3. Đọc các trường estimate: cost, rows và width

Một dòng kế hoạch dự kiến PostgreSQL có thể có dạng:

```text
Index Scan using idx_orders_customer on orders
    (cost=0.29..15.71 rows=20 width=24)
```

Giải thích:

| Trường | Ý nghĩa | Không nên hiểu là |
|---|---|---|
| `cost=0.29..15.71` | Chi phí **ước lượng** từ lúc bắt đầu đến khi hoàn thành nút | 0,29 đến 15,71 mili giây |
| `rows=20` | Số dòng **ước lượng** nút sẽ phát ra trong một lần thực hiện | Chắc chắn có đúng 20 dòng |
| `width=24` | Kích thước trung bình **ước lượng** của một dòng đầu ra, tính bằng byte | Kích thước file/bảng hoặc số cột |
| `Index Scan` | Phương thức đọc dùng chỉ mục | Bảo đảm nhanh hơn mọi `Seq Scan` |
| `Index Cond` | Điều kiện có thể dùng ở thao tác truy cập chỉ mục | Toàn bộ điều kiện lọc của truy vấn |

### 3.1. Cost là đơn vị tương đối của planner

`cost` được thể hiện bằng đơn vị chi phí nội bộ của PostgreSQL, dựa trên mô hình chi phí như đọc trang dữ liệu, CPU xử lý tuple/operator và các tham số cấu hình.

Ví dụ:

```text
cost=0.29..15.71
```

thường được đọc là:

- **Startup cost ~0,29:** chi phí ước lượng trước khi có thể bắt đầu đưa ra kết quả.
- **Total cost ~15,71:** chi phí ước lượng nếu thực thi nút đến khi hoàn thành theo kế hoạch đó.

Đừng viết:

> “Query dự kiến chạy trong 15,71 ms.”

Vì **cost không phải thời gian mili giây**. Hai kế hoạch được đánh giá tương đối theo mô hình planner và các tham số chi phí. Chúng không phải đồng hồ đo thời gian thật.

### 3.2. Rows là cardinality ước lượng

`rows=20` có thể xuất phát từ:

- Số dòng ước lượng của bảng.
- Phân bố giá trị trong thống kê.
- Tỉ lệ lọc (*selectivity*) của điều kiện `WHERE`.
- Quan hệ giữa các điều kiện.
- Thông tin unique/index.
- Ước lượng sau `JOIN`, `GROUP BY`, `LIMIT`.

Nếu PostgreSQL ước lượng **20 dòng** nhưng thực tế chỉ có **1 dòng**, không nhất thiết câu SQL sai. Điều đó cho thấy bộ tối ưu hóa có một giả định về phân bố/số dòng không phù hợp với lần chạy đó.

### 3.3. Width là kích thước dòng ước lượng

`width=24` nghĩa là PostgreSQL ước lượng mỗi dòng đầu ra của nút có kích thước trung bình khoảng 24 byte theo mô hình thống kê/kiểu dữ liệu. Không suy ra rằng bảng chỉ chiếm `24 × rows` byte trên đĩa, vì còn overhead trang, tuple, index, TOAST và những yếu tố khác.

`width` ảnh hưởng đến ước lượng chi phí sắp xếp, hash, di chuyển dữ liệu và bộ nhớ.

## 4. Đọc các trường actual: time, rows và loops

Với `EXPLAIN ANALYZE`, một dòng có thể trông như:

```text
Index Scan using idx_orders_customer on orders
  (cost=0.29..15.71 rows=20 width=24)
  (actual time=0.026..0.101 rows=20 loops=1)
```

**Đây là định dạng minh họa, không phải kết quả chạy đo được trong môi trường của bạn.**

Bây giờ có hai nhóm thông tin:

1. **Ước lượng:** `cost`, `rows`, `width` được planner đưa ra.
2. **Thực tế:** `actual time`, `rows`, `loops` được thu thập khi truy vấn chạy.

### 4.1. Actual time có đơn vị mili giây

`actual time=0.026..0.101` thường chỉ:

- Thời gian đo tới lúc có dòng đầu tiên từ nút.
- Thời gian đo tới lúc nút hoàn tất.
- Đơn vị là **mili giây**.
- Giá trị được báo cáo **trên một lần thực hiện nút**, với cách tính trung bình khi có nhiều loops.

Khác với `cost`, đây là số liệu thời gian được đo thật ở lần chạy `ANALYZE`. Nhưng nó chịu overhead của công cụ đo và trạng thái cache/máy chủ.

### 4.2. Actual rows và loops

`actual rows=20 loops=1` nghĩa là nút phát khoảng 20 dòng trong một lần thực hiện.

Nếu:

```text
actual rows=3 loops=100
```

thì `rows=3` là **giá trị trung bình mỗi lần nút được thực hiện**, còn `loops=100` cho biết nút được thực hiện 100 lần. Tổng dòng phát ra qua các lần thực hiện có thể xấp xỉ:

\[
3 \times 100 = 300.
\]

Đừng so `estimated rows=3` với `actual rows=300` nếu 300 thực chất là **tổng số dòng qua 100 vòng lặp** và nhãn actual đã báo trung bình mỗi vòng.

### 4.3. Actual rows không phải số dòng bảng ban đầu

Nếu một nút `Aggregate` tính `COUNT(*)`:

```sql
SELECT COUNT(*)
FROM orders;
```

nút Aggregate có thể phát ra **một dòng** (giá trị đếm), dù nút scan phía dưới đã đọc hàng trăm nghìn dòng.

Vì vậy cần xem **nút cụ thể** đang nói đến dữ liệu nào. `actual rows=1` tại `Aggregate` không có nghĩa query chỉ đọc một dòng trong bảng.

### 4.4. Execution Time tổng thể

Dưới cùng của `EXPLAIN ANALYZE` thường có:

```text
Planning Time: 0.185 ms
Execution Time: 0.463 ms
```

- `Planning Time`: thời gian lập kế hoạch được báo cáo.
- `Execution Time`: thời gian thực thi query được báo cáo.
- Đây **không phải** tổng thời gian người dùng thấy trên mạng từ lúc nhấn nút đến lúc giao diện hiển thị hết dữ liệu.

Khi EXPLAIN ANALYZE chạy SELECT, hệ quản trị thu thập kết quả để đo nhưng không trả toàn bộ kết quả truy vấn theo cách SELECT thông thường. Thời gian truyền dữ liệu về client, kết xuất giao diện và logic ứng dụng không được đo đầy đủ giống một request thực tế.

## 5. Bộ dữ liệu thực hành tự chứa trên PostgreSQL

Ta tạo một bảng đơn hàng **100.000 dòng** để thấy nhiều kiểu kế hoạch. Không chạy trong hệ thống thật; câu `generate_series` tạo dữ liệu luyện tập.

### 5.1. Tạo bảng

```sql
CREATE TABLE lesson327_orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    order_date DATE NOT NULL,
    status VARCHAR(12) NOT NULL
        CHECK (status IN ('PAID', 'PENDING', 'CANCELLED')),
    region_code VARCHAR(12) NOT NULL,
    total_amount NUMERIC(12, 2) NOT NULL
        CHECK (total_amount >= 0)
);
```

### 5.2. Tạo 100.000 đơn

```sql
INSERT INTO lesson327_orders (
    customer_id,
    order_date,
    status,
    region_code,
    total_amount
)
SELECT
    ((g.n - 1) % 5000) + 1,
    DATE '2024-01-01' + ((g.n - 1) % 730),
    CASE
        WHEN g.n % 10 = 0 THEN 'CANCELLED'
        WHEN g.n % 5 = 0 THEN 'PENDING'
        ELSE 'PAID'
    END,
    CASE
        WHEN g.n % 20 = 0 THEN 'SOUTH'
        ELSE 'NORTH'
    END,
    (100 + (g.n % 5000))::NUMERIC(12, 2)
FROM generate_series(1, 100000) AS g(n);
```

Dữ liệu có tính chất:

- Có **100.000 đơn**.
- Có **5.000 mã khách** (1 đến 5000), mỗi khách xuất hiện **20 lần**.
- Trạng thái `PAID`: **80.000 dòng**.
- `PENDING`: **10.000 dòng**.
- `CANCELLED`: **10.000 dòng**.
- Vùng `SOUTH`: **5.000 dòng**.
- Vùng `NORTH`: **95.000 dòng**.
- Đặc biệt: do `n % 20 = 0` suy ra `n % 10 = 0`, **mọi đơn SOUTH đều có trạng thái CANCELLED**.

Phân bố có chủ ý để minh họa vì sao **ước lượng selectivity của hai cột tương quan** có thể sai.

### 5.3. Thu thập thống kê planner

```sql
ANALYZE lesson327_orders;
```

Lệnh `ANALYZE` ở đây thu thập/cập nhật **thống kê** để planner ước lượng số dòng và độ chọn lọc.

**Đừng nhầm:**

- `ANALYZE lesson327_orders;`: cập nhật thống kê của bảng.
- `EXPLAIN ANALYZE SELECT ...;`: **thực thi truy vấn được giải thích** rồi đo số liệu thực tế.

Hai lệnh đều có chữ **ANALYZE**, nhưng mục đích hoàn toàn khác nhau.

### 5.4. Xác minh đặc tính của bộ dữ liệu

```sql
SELECT
    COUNT(*) AS total_orders,
    COUNT(DISTINCT customer_id) AS customers,
    COUNT(*) FILTER (WHERE status = 'PAID') AS paid_orders,
    COUNT(*) FILTER (WHERE status = 'PENDING') AS pending_orders,
    COUNT(*) FILTER (WHERE status = 'CANCELLED') AS cancelled_orders,
    COUNT(*) FILTER (WHERE region_code = 'SOUTH') AS south_orders
FROM lesson327_orders;
```

Dữ liệu nguồn được tạo theo quy tắc xác định nên các số lượng ở trên có thể tính được trước, còn **kế hoạch và thời gian thực thi** vẫn phụ thuộc PostgreSQL và môi trường.

## 6. Lần đầu dùng EXPLAIN: chỉ xem dự kiến

Chạy:

```sql
EXPLAIN
SELECT
    order_id,
    order_date,
    total_amount
FROM lesson327_orders
WHERE customer_id = 42;
```

Nếu chưa tạo chỉ mục trên `customer_id`, PostgreSQL có thể chọn `Seq Scan`.

Một đoạn kế hoạch **minh họa**:

```text
Seq Scan on lesson327_orders
  (cost=0.00..2167.00 rows=20 width=22)
  Filter: (customer_id = 42)
```

Số `cost` và `width` ở đây là **ví dụ về cách đọc**, không phải số đo được đảm bảo cho mọi máy.

Ý nghĩa:

- `Seq Scan`: PostgreSQL dự kiến quét tuần tự bảng.
- `Filter`: kiểm tra `customer_id = 42` trên các dòng đọc được.
- `rows=20`: planner dự kiến có khoảng 20 dòng khớp.
- `cost=...`: mô hình chi phí, **không phải ms**.

Điều quan trọng: bạn **chưa biết thực tế có bao nhiêu dòng được xuất ra, bao nhiêu trang được đọc hay mất bao lâu**. `EXPLAIN` mới cho kế hoạch dự kiến.

### 6.1. Không có actual time khi chỉ EXPLAIN

Nếu output không có `actual time`, `actual rows` hay `loops`, đó là điều bình thường. Bạn chưa yêu cầu thực thi và đo.

Không nên viết nhận xét:

> “Thực tế query đã chạy Seq Scan trong 2 ms” chỉ dựa vào `cost=...`.

### 6.2. EXPLAIN có thể chạy trên câu UPDATE mà chưa thay đổi dữ liệu

```sql
EXPLAIN
UPDATE lesson327_orders
SET status = 'PAID'
WHERE customer_id = 42;
```

PostgreSQL lập kế hoạch cho UPDATE, nhưng **không thực hiện câu UPDATE chính**.

Tuy nhiên, không phải vì vậy mà có thể xem mọi hoạt động ở pha lập kế hoạch hoàn toàn không có side effect trong mọi hoàn cảnh (ví dụ hàm do người dùng định nghĩa với hành vi bất thường). Với quy trình thực hành thông thường, quy tắc cần nhớ là **không có `ANALYZE` thì PostgreSQL không thực thi lệnh DML được giải thích**.

## 7. Dùng EXPLAIN ANALYZE: quan sát truy vấn thật

Thử:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    order_id,
    order_date,
    total_amount
FROM lesson327_orders
WHERE customer_id = 42;
```

Với dữ liệu mẫu, có đúng **20 dòng** của khách 42.

Một đoạn output **chỉ để minh họa cách đọc**:

```text
Seq Scan on lesson327_orders
  (cost=0.00..2167.00 rows=20 width=22)
  (actual time=0.015..5.834 rows=20 loops=1)
  Filter: (customer_id = 42)
  Rows Removed by Filter: 99980
  Buffers: shared hit=900
Planning Time: 0.167 ms
Execution Time: 5.862 ms
```

Đừng sao chép các con số thời gian, cost hay buffer ở đây làm kết quả benchmark thật: chúng phụ thuộc **phiên bản, phần cứng, dữ liệu, cache và cấu hình**.

Các thông tin quan trọng:

- Planner dự kiến `rows=20`.
- Thực tế nút xuất `rows=20`.
- `loops=1`: thực hiện nút một lần.
- `Rows Removed by Filter: 99980`: các dòng không qua điều kiện lọc trong ví dụ một vòng.
- `Buffers: shared hit=900`: truy cập buffer trong cache chung được ghi nhận, **không phải số mili giây**.
- `Execution Time` là thời gian đo của lần chạy này.

### 7.1. Vì sao `Rows Removed by Filter` không phải số dòng bảng bị xóa?

Đây chỉ là **số dòng bị loại khỏi kết quả của nút do điều kiện lọc**, không phải `DELETE` dữ liệu.

### 7.2. Có thể so estimated và actual ở đâu?

So:

```text
rows=20             -- ước lượng planner
actual rows=20      -- kết quả quan sát mỗi vòng
loops=1             -- số vòng thực hiện
```

Nếu `estimated rows=500` nhưng `actual rows=20`, planner đã **ước lượng cao hơn thực tế 25 lần** tại nút đó. Sai số có thể ảnh hưởng lựa chọn `JOIN`, `Sort` hoặc sử dụng chỉ mục.

## 8. Tạo chỉ mục rồi so sánh kế hoạch

Tạo một chỉ mục hỗ trợ tìm theo khách và thứ tự ngày giảm dần:

```sql
CREATE INDEX lesson327_orders_customer_date_idx
    ON lesson327_orders (
        customer_id,
        order_date DESC
    );
```

Xem lại:

```sql
EXPLAIN
SELECT
    order_id,
    order_date,
    total_amount
FROM lesson327_orders
WHERE customer_id = 42
ORDER BY order_date DESC
LIMIT 5;
```

Một dạng kế hoạch có thể thấy:

```text
Limit
  └─ Index Scan using lesson327_orders_customer_date_idx
       on lesson327_orders
       Index Cond: (customer_id = 42)
```

Vì chỉ mục sắp xếp theo `customer_id` rồi `order_date DESC`, với điều kiện bằng trên `customer_id`, PostgreSQL có thể lấy các dòng theo thứ tự ngày mà **không cần nút Sort riêng**.

### 8.1. EXPLAIN không chứng minh chỉ mục đã giúp nhanh hơn

`EXPLAIN` cho biết **planner chọn** chỉ mục, chứ chưa cho biết tốc độ thực tế sau khi chạy.

Để quan sát:

```sql
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF)
SELECT
    order_id,
    order_date,
    total_amount
FROM lesson327_orders
WHERE customer_id = 42
ORDER BY order_date DESC
LIMIT 5;
```

Quan sát các dòng:

- Có `Index Scan` hay `Bitmap Heap Scan` không?
- Có `Sort` không?
- `actual rows` ở `Limit` là bao nhiêu?
- `Buffers` đã dùng những loại trang nào?
- `Execution Time` là bao nhiêu trong lần đo?

### 8.2. Đối chiếu đúng truy vấn, không đổi bài toán giữa hai lần

Nếu so trước/sau chỉ mục, hãy giữ cùng:

- Câu SQL.
- Điều kiện lọc.
- Tập dữ liệu.
- Tham số.
- Isolation và môi trường càng tương đương càng tốt.

Không nên so `SELECT *` trước index với `SELECT order_id` sau index rồi kết luận index giúp nhanh hơn: **khối lượng dữ liệu cần trả đã thay đổi**.

### 8.3. Không bảo đảm planner luôn chọn Index Scan

Ngay cả khi chỉ mục tồn tại, PostgreSQL có thể chọn `Seq Scan` nếu ước lượng quét bảng rẻ hơn, ví dụ khi truy vấn cần phần lớn dòng hoặc bảng rất nhỏ. Điều đó **không tự chứng minh chỉ mục tạo sai**.

## 9. Vì sao Seq Scan đôi khi là kế hoạch tốt?

Xét:

```sql
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF)
SELECT
    COUNT(*)
FROM lesson327_orders
WHERE status = 'PAID';
```

Có **80.000 trong 100.000 dòng** thỏa điều kiện, tức khoảng 80%.

Khi phải xét phần lớn bảng, đọc tuần tự có thể hiệu quả hơn việc dùng chỉ mục rồi truy cập nhiều trang heap rời rạc. Planner có thể chọn `Seq Scan` (hoặc kế hoạch song song tùy cấu hình/bảng).

Ngược lại:

```sql
SELECT *
FROM lesson327_orders
WHERE customer_id = 42;
```

chỉ cần khoảng **20/100.000 dòng** (0,02%), và một chỉ mục phù hợp thường rất hữu ích.

### 9.1. Cách chọn kế hoạch là bài toán chi phí

Không nên áp dụng:

- “Dùng Index Scan luôn tốt.”
- “Seq Scan nghĩa là thiếu index.”
- “Index Scan chỉ cần ít dòng nên chắc chắn nhanh hơn.”

Planner cân nhắc số dòng, phân bố, thứ tự, chi phí đọc ngẫu nhiên, cache, độ rộng dữ liệu và các yếu tố khác. **Chỉ mục không phải đáp án cho mọi truy vấn**.

## 10. Giải thích Index Scan, Index Only Scan và Bitmap Scan

### 10.1. Index Scan

`Index Scan` dùng chỉ mục tìm dòng đáp ứng điều kiện, sau đó có thể truy cập bảng heap để lấy các cột không nằm trong chỉ mục.

Ví dụ:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    order_id,
    total_amount
FROM lesson327_orders
WHERE customer_id = 42;
```

Chỉ mục `(customer_id, order_date DESC)` giúp tìm khách 42, nhưng `total_amount` và `order_id` không thuộc phần khóa chỉ mục đó, nên vẫn cần truy cập dữ liệu bảng trong nhiều trường hợp.

### 10.2. Index Only Scan

Một chỉ mục có thể chứa đủ những cột truy vấn cần:

```sql
CREATE INDEX lesson327_orders_customer_cover_idx
    ON lesson327_orders (customer_id)
    INCLUDE (order_date, total_amount);
```

Sau đó:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    order_date,
    total_amount
FROM lesson327_orders
WHERE customer_id = 42;
```

PostgreSQL **có thể** dùng `Index Only Scan`, nhưng điều đó **không bảo đảm không đọc heap** trong mọi tình huống: kiểm tra khả năng nhìn thấy tuple dưới MVCC có thể cần đọc heap nếu visibility map chưa hỗ trợ tránh truy cập.

Trong output có thể có:

```text
Heap Fetches: 0
```

hoặc một số lớn hơn 0.

**Không gọi một kế hoạch là “index-only thực sự không đụng heap” chỉ nhìn tên nút**; xem `Heap Fetches` trong số liệu thực tế.

### 10.3. Bitmap Index Scan + Bitmap Heap Scan

Với một số điều kiện trả nhiều dòng nằm rải rác trong bảng, PostgreSQL có thể dùng:

```text
Bitmap Heap Scan on lesson327_orders
  Recheck Cond: (...)
  └─ Bitmap Index Scan on ...
       Index Cond: (...)
```

Điểm cần đọc:

- `Bitmap Index Scan` thu thập vị trí các dòng/trang phù hợp từ chỉ mục.
- `Bitmap Heap Scan` đọc các trang dữ liệu tương ứng.
- `Recheck Cond` và `Rows Removed by Index Recheck` (nếu có) nói về điều kiện cần xác nhận lại trong một số tình huống bitmap, đặc biệt bitmap mất chi tiết.

Không so trực tiếp `Bitmap Index Scan.actual rows` với số dòng cuối cùng mà không hiểu **nút cha và nút con làm gì**.

## 11. Trường actual rows và loops khi JOIN

Một truy vấn `JOIN` có thể dùng `Nested Loop`:

```text
Nested Loop
  (actual rows=300 loops=1)
  -> Seq Scan on customers
       (actual rows=100 loops=1)
  -> Index Scan on orders
       (actual rows=3 loops=100)
```

Đây là **kế hoạch minh họa**.

Hiểu như sau:

- Bảng ngoài cung cấp 100 dòng.
- Với mỗi dòng ngoài, nút index phía trong được chạy một lần.
- Nút phía trong trung bình trả 3 dòng mỗi vòng và chạy 100 vòng.
- Tổng số dòng phía trong có thể khoảng `3 × 100 = 300`.

### 11.1. Không nhân hoặc cộng nhầm actual rows

Nhiều người đọc `actual rows=3 loops=100` rồi kết luận query chỉ đọc 3 dòng, hoặc cho rằng planner ước lượng sai 100 lần khi thấy `rows=3`. Đó là sai cách đọc nếu chưa xét **per-loop**.

`rows` của estimate là số dòng dự kiến cho một lần thực hiện nút. `actual rows` khi có nhiều `loops` cũng được báo theo giá trị bình quân trên vòng trong PostgreSQL. Để suy tổng số dòng đi qua nút, cần xét cả số vòng.

### 11.2. Một thay đổi nhỏ trong cardinality có thể đổi chiến lược JOIN

Nếu planner nghĩ phía ngoài chỉ có 100 dòng nhưng thực tế có 100.000 dòng, nút Index Scan phía trong có thể bị gọi nhiều lần hơn dự kiến. Tổng chi phí tích lũy tăng mạnh.

Đây là lý do **sai số ước lượng ở nút thấp** có thể dẫn đến một kế hoạch JOIN kém cho toàn truy vấn, dù một lần Index Scan riêng lẻ rất nhanh.

### 11.3. Hash Join và Merge Join

PostgreSQL còn có thể chọn:

- `Hash Join`: xây cấu trúc hash từ một phía rồi dò phía kia.
- `Merge Join`: nối hai luồng được sắp xếp theo khóa tương thích.
- `Nested Loop`: với mỗi dòng một phía, tìm dòng phù hợp ở phía còn lại.

Không có chiến lược nào tốt nhất mọi lúc. Điều quan trọng là planner **ước lượng đúng quy mô và phân bố dữ liệu** để chọn cách nối phù hợp.

## 12. Trường Rows Removed by Filter và sự khác nhau với output rows

Ví dụ:

```text
Seq Scan on lesson327_orders
  (actual rows=20 loops=1)
  Filter: (customer_id = 42)
  Rows Removed by Filter: 99980
```

Nếu bộ dữ liệu đúng 100.000 dòng và scan một lần, cách đọc đơn giản là:

- 20 dòng vượt qua bộ lọc của nút.
- 99.980 dòng bị bộ lọc loại.
- Tổng dòng được xét ở nút là xấp xỉ 100.000.

Nhưng đừng áp dụng phép cộng này máy móc cho mọi nút khi có:

- `loops > 1`.
- `LIMIT` khiến kế hoạch dừng sớm.
- Bitmap recheck.
- Join filter hoặc filter ở các cấp khác nhau.
- Parallel scan và giá trị báo cáo trung bình nhiều worker.
- Dòng bị loại ở nhiều cấp khác nhau.

**Mỗi dòng kế hoạch nói về một nút cụ thể**, không tự đại diện cho toàn bộ truy vấn.

## 13. Sự chênh lệch lớn giữa estimated rows và actual rows

Giả sử một nút có:

```text
(cost=... rows=5000 width=...)
(actual time=... rows=50 loops=1)
```

Planner dự kiến 5.000 dòng nhưng thực tế chỉ có 50, tức ước lượng cao gấp **100 lần**.

Hoặc:

```text
(cost=... rows=10 width=...)
(actual time=... rows=10000 loops=1)
```

Planner dự kiến 10 nhưng thực tế 10.000, tức **ước lượng thiếu 1.000 lần**.

Đây là các dấu hiệu cần tìm nguyên nhân, không phải bằng chứng tự thân rằng toàn bộ query chắc chắn chậm.

### 13.1. Những nguyên nhân thường gặp

- Thống kê chưa cập nhật sau khi dữ liệu thay đổi mạnh.
- Một giá trị phân bố rất lệch (*data skew*).
- Hai điều kiện lọc có quan hệ tương quan nhưng planner không biết đầy đủ.
- Biểu thức hoặc hàm làm khó việc ước lượng selectivity.
- Dữ liệu phân bố khác trong các tenant.
- Tham số truy vấn có độ chọn lọc khác nhau.
- Mô hình thống kê không nắm hết quan hệ giữa các cột/bảng.
- Phép JOIN làm sai số nhân lên qua nhiều cấp.

### 13.2. So sánh một lần chưa đủ để kết luận nguyên nhân

Sự chênh lệch giữa estimated và actual **có thể** làm planner chọn kế hoạch không tốt, nhưng cần xem nó tác động thế nào đến các nút khác, lượng buffer, thực tế thời gian và thông tin nghiệp vụ.

Mục tiêu không phải làm mọi con số estimate trùng tuyệt đối với actual, mà là giúp planner chọn phương án có hiệu năng phù hợp và ổn định.

## 14. Bài thực hành về dữ liệu tương quan

Bộ dữ liệu của `lesson327_orders` có một quan hệ có chủ ý:

- `region_code = 'SOUTH'` chỉ xuất hiện khi `n % 20 = 0`.
- Những dòng ấy đồng thời có `status = 'CANCELLED'`.

Do đó:

```sql
SELECT COUNT(*)
FROM lesson327_orders
WHERE region_code = 'SOUTH'
  AND status = 'PAID';
```

trả **0 dòng thỏa điều kiện**.

Nhưng nếu optimizer chỉ dựa trên xác suất riêng từng cột và giả định gần độc lập:

\[
P(\text{SOUTH}) \approx 0.05,\quad
P(\text{PAID}) \approx 0.80.
\]

Một ước lượng độc lập đơn giản sẽ cho:

\[
100000 \times 0.05 \times 0.80 = 4000.
\]

**4.000 là con số giả định của mô hình độc lập đơn giản, không phải khẳng định PostgreSQL chắc chắn xuất `rows=4000`.** PostgreSQL có thể sử dụng thống kê bổ sung, các giới hạn nội bộ và phiên bản khác nhau.

### 14.1. Đối chiếu hai loại kế hoạch

```sql
EXPLAIN
SELECT
    order_id
FROM lesson327_orders
WHERE region_code = 'SOUTH'
  AND status = 'PAID';
```

Sau đó:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    order_id
FROM lesson327_orders
WHERE region_code = 'SOUTH'
  AND status = 'PAID';
```

Với dữ liệu mẫu, kết quả thực tế **0 dòng**, nhưng estimated rows có thể khác 0.

Đó là minh họa trực tiếp:

> Một ước lượng dựa trên thống kê không nhất thiết nắm được quan hệ phụ thuộc chặt chẽ giữa các cột.

### 14.2. Extended statistics trong PostgreSQL

PostgreSQL hỗ trợ **extended statistics** cho một số loại quan hệ đa cột:

```sql
CREATE STATISTICS lesson327_region_status_stats (
    dependencies,
    mcv
)
ON region_code, status
FROM lesson327_orders;

ANALYZE lesson327_orders;
```

Sau đó chạy lại `EXPLAIN` và `EXPLAIN ANALYZE` cho cùng câu truy vấn.

- `dependencies` mô tả một số phụ thuộc chức năng giữa các cột.
- `mcv` mô tả các kết hợp giá trị xuất hiện nhiều.

Các loại thống kê này **có thể cải thiện** một số ước lượng selectivity nhiều cột. Không đảm bảo mọi kế hoạch đều đổi hoặc mọi ước lượng trở thành chính xác tuyệt đối. Tính hỗ trợ và ứng dụng thống kê phụ thuộc điều kiện truy vấn và phiên bản PostgreSQL.

### 14.3. Thống kê không sửa được tất cả tương quan

Một số tương quan phức tạp qua nhiều bảng, phép JOIN, biểu thức, dữ liệu đang thay đổi liên tục hoặc điều kiện bất thường vẫn khó ước lượng. Có khi giải pháp đúng là:

- Thiết kế lại câu SQL.
- Bổ sung chỉ mục phù hợp.
- Định nghĩa ràng buộc hợp lý.
- Thay đổi cấu trúc dữ liệu/tập bảng nếu nghiệp vụ yêu cầu.
- Cải thiện thống kê.
- Thay đổi cách chuẩn bị/truyền tham số.

Không chỉ tăng statistics target bằng mọi giá.

## 15. Cập nhật thống kê: ANALYZE khác EXPLAIN ANALYZE

### 15.1. ANALYZE thu thập thống kê

```sql
ANALYZE lesson327_orders;
```

PostgreSQL cập nhật thông tin thống kê phục vụ planner. Quá trình có thể lấy mẫu; không phải mỗi số thống kê đều là số đếm chính xác 100%.

### 15.2. EXPLAIN ANALYZE thực thi một truy vấn

```sql
EXPLAIN ANALYZE
SELECT COUNT(*)
FROM lesson327_orders;
```

Đây là **chạy SELECT COUNT(*)**, rồi đo kế hoạch. Không phải cập nhật thống kê optimizer của bảng theo mục đích thông thường của câu `ANALYZE lesson327_orders`.

### 15.3. AUTOVACUUM, AUTOANALYZE và thống kê cũ

PostgreSQL có cơ chế tự động bảo trì và thu thập thống kê. Dù vậy, sau các thay đổi dữ liệu lớn hoặc bất thường, thống kê vẫn có thể chưa phản ánh phân bố mới tại thời điểm bạn đo.

Nếu `EXPLAIN ANALYZE` cho thấy sai số cardinality rất lớn, kiểm tra số liệu và độ mới của thống kê trước khi kết luận planner “không biết dùng index”.

### 15.4. VACUUM không giống ANALYZE

`VACUUM` xử lý các khía cạnh bảo trì liên quan MVCC và dung lượng, trong khi `ANALYZE` thu thập thống kê planner. PostgreSQL có lệnh `VACUUM ANALYZE` để kết hợp các công việc phù hợp.

Đừng nhầm việc `VACUUM` giúp visibility map với `ANALYZE` thay đổi ước lượng selectivity; chúng có những tác động khác nhau.

## 16. BUFFERS cho biết điều gì?

Chạy:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    order_id,
    order_date,
    total_amount
FROM lesson327_orders
WHERE customer_id = 42;
```

Một nút có thể hiển thị:

```text
Buffers: shared hit=12 read=3
```

Cách đọc:

- `shared hit=12`: ghi nhận các lần tìm trang trong bộ đệm chung đã có trong cache.
- `shared read=3`: ghi nhận các lần đọc trang vào shared buffer theo instrumentation.
- Các số là **thống kê truy cập block**, không phải thời gian mili giây.
- Các nút cha có thể **bao gồm tác động của nút con** khi báo cáo buffer, nên không được cộng máy móc mọi dòng buffer trong cây thành tổng duy nhất.

### 16.1. Shared hit không đồng nghĩa “CPU miễn phí”

Một buffer hit tránh cần đọc trang vào shared buffers tại thời điểm đó, nhưng vẫn có chi phí CPU, truy cập bộ nhớ, kiểm tra MVCC, xử lý tuple. Đọc từ shared buffers không có nghĩa query không tốn thời gian.

### 16.2. Shared read không luôn đồng nghĩa đĩa vật lý chậm

Một trang không có sẵn trong PostgreSQL shared buffers vẫn có thể được đáp ứng từ **cache của hệ điều hành** thay vì đọc từ thiết bị lưu trữ vật lý. Vì vậy không suy ra số lượt I/O đĩa thật chỉ bằng `shared read`.

### 16.3. Temp và local buffers

Một số thao tác có thể báo:

- `temp read`/`temp written`: block tạm liên quan đến xử lý như sort/hash vượt bộ nhớ.
- `local hit/read`: buffer cục bộ cho bảng tạm của session.
- `shared dirtied/written`: thông tin về trang bị thay đổi/ghi trong quá trình thực thi.

Ý nghĩa và mức độ xuất hiện tùy phép toán, dữ liệu, cấu hình và phiên bản.

### 16.4. I/O timing cần instrumentation phù hợp

Khi PostgreSQL được cấu hình thu thập thời gian I/O, kế hoạch có thể hiện thêm các số liệu như `I/O Timings`. Tính sẵn có phụ thuộc cấu hình, chẳng hạn `track_io_timing`, và phiên bản.

Không suy đoán một kế hoạch không có `I/O Timings` nghĩa là không xảy ra I/O.

## 17. Timing ON và TIMING OFF

Hai lệnh:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*)
FROM lesson327_orders;
```

và:

```sql
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF)
SELECT COUNT(*)
FROM lesson327_orders;
```

đều thực thi SELECT và thu thập thông tin số dòng. Nhưng khi `TIMING OFF`:

- PostgreSQL tránh đo thời gian chi tiết của từng nút theo cách thông thường.
- `actual time=...` ở các nút không còn được hiển thị như khi đo thời gian.
- `actual rows`, `loops` và thông tin bộ đệm vẫn có thể được hiển thị.
- `Execution Time` tổng thể vẫn được báo cáo trong cấu hình thích hợp.

### 17.1. Vì sao tắt timing đôi khi hữu ích?

Đo thời gian ở từng nút có overhead. Nếu truy vấn có rất nhiều vòng lặp, overhead của việc gọi đồng hồ và thu thập thống kê có thể ảnh hưởng phép đo.

Khi cần tập trung vào **cardinality, số vòng và buffer**, `TIMING OFF` giúp giảm một loại overhead.

### 17.2. Nhưng TIMING OFF không biến phép đo thành “thời gian ứng dụng”

Ngay cả khi tắt timing từng nút, `EXPLAIN ANALYZE` vẫn không phản ánh toàn bộ network round-trip, thời gian serialize tất cả rows cho client, thời gian xử lý ở Java hay render giao diện.

Muốn đánh giá hiệu năng đầu cuối, cần kết hợp **phép đo database** và **đồng hồ ứng dụng**.

## 18. Parallel plan làm cách đọc loops phức tạp hơn

PostgreSQL có thể thực thi một số truy vấn song song. Kế hoạch có thể có:

```text
Gather
  Workers Planned: 2
  Workers Launched: 2
  └─ Parallel Seq Scan on lesson327_orders
       (actual rows=... loops=3)
```

Các con số chỉ minh họa hình dạng cây.

### 18.1. Workers Planned và Workers Launched

- `Workers Planned`: số worker được planner dự kiến huy động.
- `Workers Launched`: số worker thực sự được khởi chạy ở lần thực thi.

Có thể khác nhau tùy tài nguyên và cấu hình.

### 18.2. Actual rows và loops trong parallel

Thông tin `actual rows`/`loops` có thể được tổng hợp qua các lần thực thi, gồm leader và worker. Cần xem output `VERBOSE` hoặc biểu diễn chi tiết khi muốn hiểu phân phối công việc.

Không kết luận query chỉ đọc một phần rất nhỏ vì nhìn thấy `actual rows` tại một worker mà không xét toàn bộ kế hoạch.

### 18.3. Parallel không tự bảo đảm nhanh hơn

Khởi tạo worker, chia và gom kết quả tốn overhead. Với truy vấn nhỏ, kế hoạch đơn luồng có thể hiệu quả hơn. Planner dựa vào cost để chọn, còn `EXPLAIN ANALYZE` cho phép quan sát kết quả chạy thực tế.

## 19. LIMIT, Sort và thời điểm dừng sớm

Xét:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    order_id,
    customer_id,
    order_date
FROM lesson327_orders
WHERE customer_id = 42
ORDER BY order_date DESC
LIMIT 5;
```

Chỉ mục `(customer_id, order_date DESC)` có thể cho phép PostgreSQL **đọc đúng thứ tự cần thiết và dừng sớm** sau số dòng phù hợp.

Nếu không có chỉ mục thích hợp, kế hoạch có thể cần:

1. Đọc nhiều dòng.
2. Lọc khách 42.
3. Sắp xếp.
4. Lấy 5 dòng đầu.

### 19.1. `LIMIT 5` không có nghĩa chỉ đọc 5 dòng trong bảng

Nếu không có thứ tự truy cập phù hợp, database có thể phải đọc/so sánh rất nhiều dòng trước khi biết 5 dòng nào đứng đầu.

Vì vậy, hãy xem **các nút phía dưới Limit** trong `EXPLAIN ANALYZE`.

### 19.2. Top-N Sort

Một số kế hoạch có thể dùng thuật toán `top-N heapsort` thay vì sắp xếp đầy đủ. Output thực tế có thể có:

```text
Sort Method: top-N heapsort  Memory: ...
```

Thông tin này cho biết **thuật toán thực sự được sử dụng trong nút Sort**, khác với chỉ đọc mỗi tên `Sort` ở kế hoạch ước lượng.

### 19.3. LIMIT không làm kết quả ổn định nếu ORDER BY không đủ khóa

Nếu hai đơn cùng `order_date`, `LIMIT 5` với `ORDER BY order_date DESC` có thể chọn những dòng đồng hạng khác nhau giữa các lần chạy/kế hoạch. Nếu nghiệp vụ cần kết quả ổn định, bổ sung khóa phá hòa:

```sql
ORDER BY order_date DESC, order_id DESC
LIMIT 5
```

Muốn hỗ trợ hoàn toàn thứ tự này bằng chỉ mục, cần xét thiết kế chỉ mục tương ứng. Đừng đo nhanh/chậm mà quên **độ đúng của thứ tự nghiệp vụ**.

## 20. Sắp xếp hoặc hash vượt bộ nhớ

Khi PostgreSQL thực thi `Sort`, một kế hoạch thực tế có thể báo:

```text
Sort Method: quicksort  Memory: 2048kB
```

hoặc:

```text
Sort Method: external merge  Disk: 16384kB
```

Những dòng trên là **ví dụ định dạng**, không phải kết quả đo của bộ dữ liệu này.

Sự khác nhau:

- `quicksort` trong bộ nhớ: dữ liệu phù hợp phạm vi tài nguyên được cấp cho phép sort.
- `external merge` có thể cho thấy thao tác sắp xếp dùng đĩa tạm.
- Các toán tử `Hash`/`Hash Join` có thể báo lượng bộ nhớ và batch liên quan.

`EXPLAIN` ước lượng cost sort/hash, nhưng **chỉ kế hoạch được thực thi** mới cho bạn biết dạng thực tế và các thông tin runtime tương ứng.

**Không chỉ tăng `work_mem` sau khi thấy disk sort**. Tùy truy vấn và số connection đồng thời, tăng bộ nhớ cho mỗi thao tác có thể gây áp lực RAM lớn. Phải đánh giá tổng workload.

## 21. Cảnh báo quan trọng: EXPLAIN ANALYZE thực thi UPDATE, DELETE, INSERT

Đây là khác biệt có rủi ro cao nhất giữa hai loại kế hoạch.

### 21.1. EXPLAIN UPDATE chỉ lập kế hoạch

```sql
EXPLAIN
UPDATE lesson327_orders
SET status = 'PAID'
WHERE customer_id = 42;
```

Câu UPDATE **không được thực thi** trong ví dụ kế hoạch thông thường.

### 21.2. EXPLAIN ANALYZE UPDATE thực sự cập nhật

```sql
EXPLAIN ANALYZE
UPDATE lesson327_orders
SET status = 'PAID'
WHERE customer_id = 42;
```

**Câu này thực sự chạy UPDATE.** Nếu không bao trong transaction rollback phù hợp, dữ liệu có thể bị thay đổi và commit.

Tương tự:

- `EXPLAIN ANALYZE DELETE FROM ...` thực sự xóa.
- `EXPLAIN ANALYZE INSERT INTO ...` thực sự chèn.
- `EXPLAIN ANALYZE MERGE ...` thực sự thực hiện thao tác DML tương ứng khi DBMS hỗ trợ.

Không sử dụng trực tiếp các câu này như một công cụ “chỉ xem trước” trên production.

### 21.3. Mẫu thử DML trong transaction có rollback

Trong database thực hành, một cách kiểm soát là:

```sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS, WAL)
UPDATE lesson327_orders
SET total_amount = total_amount + 1
WHERE customer_id = 42;

ROLLBACK;
```

PostgreSQL vẫn **thực sự chạy UPDATE** để thu số liệu. `ROLLBACK` giúp hoàn tác các thay đổi transactional trong database.

**Nhưng có những giới hạn phải hiểu**:

- Giá trị từ sequence/identity đã tiêu thụ có thể **không được rollback**.
- Trigger có thể phát sinh tác dụng phụ ngoài database không tự hoàn tác.
- Hàm do người dùng định nghĩa có thể gọi hệ thống ngoài.
- Transaction vẫn tạo tải, khóa và WAL trong quá trình thử.
- Câu DML bị đo có thể chặn người dùng khác.
- Nếu đang đo trên dữ liệu quan trọng, rollback không tự biến thao tác thành “không rủi ro”.

Với môi trường production, nên dùng bản sao/staging hoặc quy trình kiểm thử được phê duyệt thay vì giả định BEGIN/ROLLBACK luôn vô hại.

### 21.4. WAL là tùy chọn đo bổ sung

Tùy chọn `WAL` có thể hiển thị thống kê Write-Ahead Log tương ứng trong các phiên bản PostgreSQL hỗ trợ. Đây là thông tin hữu ích để đánh giá khối lượng ghi của DML, nhưng chỉ nên dùng khi bạn thực sự kiểm soát được việc **thực thi câu lệnh**.

## 22. EXPLAIN ANALYZE và truy vấn SELECT vẫn cần thận trọng

Phần lớn SELECT thuần đọc là lựa chọn thích hợp để đo bằng `EXPLAIN ANALYZE`. Tuy nhiên:

- SELECT có thể thực hiện hàm **VOLATILE** có tác dụng phụ.
- Một số hàm có thể viết dữ liệu hoặc tương tác hệ thống ngoài.
- SELECT có thể giữ khóa đọc/khóa dòng nếu dùng `FOR UPDATE`.
- Câu truy vấn rất nặng có thể chiếm CPU, RAM, I/O và làm ảnh hưởng người dùng khác.

Do đó **EXPLAIN ANALYZE SELECT** không nên được coi tự động an toàn trên mọi môi trường và mọi biểu thức. Hãy hiểu truy vấn, quyền truy cập, khối lượng dữ liệu và ảnh hưởng tài nguyên.

## 23. FORMAT TEXT và FORMAT JSON

Mặc định PostgreSQL thường trả kế hoạch dạng văn bản dễ đọc:

```sql
EXPLAIN (FORMAT TEXT)
SELECT *
FROM lesson327_orders
WHERE customer_id = 42;
```

Có thể lấy cấu trúc JSON:

```sql
EXPLAIN (FORMAT JSON)
SELECT *
FROM lesson327_orders
WHERE customer_id = 42;
```

Hoặc kế hoạch thực tế dạng JSON:

```sql
EXPLAIN (
    ANALYZE,
    BUFFERS,
    TIMING OFF,
    FORMAT JSON
)
SELECT *
FROM lesson327_orders
WHERE customer_id = 42;
```

### 23.1. Khi nào dùng JSON?

Dạng JSON có lợi cho công cụ phân tích tự động, lưu lịch sử số liệu hoặc so sánh các trường theo cấu trúc.

Ví dụ các thuộc tính có thể gồm:

- `Node Type`.
- `Plan Rows`.
- `Plan Width`.
- `Actual Rows`.
- `Actual Loops`.
- `Startup Cost` / `Total Cost`.
- Thông tin buffer và thời gian nếu được thu thập.

Không nên so sánh trực tiếp toàn bộ chuỗi JSON như văn bản bất biến giữa các phiên bản PostgreSQL: trường và cách trình bày có thể thay đổi. Khi xây công cụ, đọc theo thuộc tính cấu trúc và xử lý trường tùy chọn.

### 23.2. VERBOSE, SETTINGS và SUMMARY

Các tùy chọn khác:

```sql
EXPLAIN (
    ANALYZE,
    VERBOSE,
    BUFFERS,
    SETTINGS,
    SUMMARY,
    TIMING OFF
)
SELECT *
FROM lesson327_orders
WHERE customer_id = 42;
```

- `VERBOSE`: bổ sung thông tin chi tiết về output/biểu thức và các yếu tố khác.
- `SETTINGS`: hiển thị một số thiết lập ảnh hưởng kế hoạch khác mặc định liên quan.
- `SUMMARY`: điều khiển phần tổng kết thời gian và thông tin tương ứng.
- `BUFFERS`: thống kê truy cập bộ đệm trong phép đo.
- `TIMING OFF`: tắt thu thời gian từng nút, giữ các thống kê quan trọng khác.

Không cần bật mọi tùy chọn cho mọi lần xem. Bắt đầu bằng **câu hỏi cần trả lời** rồi chọn thông tin phù hợp.

## 24. Vì sao hai lần EXPLAIN ANALYZE có thể ra thời gian khác nhau?

Cùng câu SQL, cùng bảng và cùng index không đồng nghĩa hai lần thực thi mất đúng số mili giây như nhau.

Nguyên nhân:

- Trang dữ liệu nằm trong cache PostgreSQL hoặc phải đọc mới.
- Cache của hệ điều hành khác nhau.
- CPU/đĩa đang có workload cạnh tranh.
- Autovacuum hoặc tác vụ khác ảnh hưởng.
- Số phiên truy cập đồng thời và chờ khóa.
- Kế hoạch song song được huy động số worker khác nhau.
- Cấu hình bộ nhớ, session hoặc tham số khác nhau.
- JIT compilation trong trường hợp được áp dụng.
- Cách đo time và overhead instrumentation.

### 24.1. Warm cache và cold cache

Lần đầu chạy truy vấn có thể cần đọc nhiều block vào bộ nhớ; lần sau có thể tận dụng cache.

Nếu lần đầu mất 100 ms, lần hai mất 10 ms, **không kết luận chỉ mục vừa giúp nhanh hơn 10 lần** nếu bạn đã thay đổi trạng thái cache hoặc workload.

### 24.2. Đo nhiều lần nhưng không “chọn số đẹp”

Muốn so sánh có cơ sở, nên:

1. Giữ điều kiện dữ liệu/config gần tương đương.
2. Ghi lại truy vấn và tham số.
3. Chạy nhiều phép đo phù hợp.
4. So sánh median/phân bố, không chỉ một số thấp nhất.
5. Xem cùng lúc cấu trúc plan, rows, buffers và thời gian.
6. Kết hợp theo dõi p95/p99 ở ứng dụng nếu mục tiêu là độ trễ người dùng.

**Không cần làm benchmark sản xuất trong bài học này**; đây là nguyên tắc đọc kết quả thực thi cho đúng.

## 25. Kế hoạch dự kiến không bảo đảm kế hoạch thực tế về sau luôn giống vậy

`EXPLAIN` hiển thị kế hoạch được planner chọn **cho câu truy vấn, thống kê, tham số và môi trường hiện tại**.

Kế hoạch có thể đổi do:

- Bảng lớn lên hoặc phân bố thay đổi.
- `ANALYZE` cập nhật thống kê.
- Thêm/xóa index.
- Thay đổi cấu hình planner và cost.
- Thay đổi PostgreSQL version.
- `WHERE` có tham số khác độ chọn lọc.
- Thay đổi cách chuẩn bị câu lệnh/plan cache.
- Dữ liệu trong bảng phân vùng hoặc bảng liên quan biến đổi.

### 25.1. Cùng câu SQL, tham số khác nhau

```sql
SELECT *
FROM lesson327_orders
WHERE status = 'PAID';
```

có 80% dòng.

```sql
SELECT *
FROM lesson327_orders
WHERE region_code = 'SOUTH';
```

chỉ có 5% dòng.

Hai điều kiện lọc có độ chọn lọc rất khác, nên planner có thể chọn cách truy cập khác nếu có index tương ứng.

### 25.2. Prepared statements: generic plan và custom plan

Trong PostgreSQL, truy vấn chuẩn bị sẵn có thể sử dụng **custom plan** tính theo giá trị tham số hoặc **generic plan** tái sử dụng một kế hoạch cho nhiều giá trị, tùy chiến lược và trạng thái lập kế hoạch.

Điều này có nghĩa một phép đo với giá trị tham số hiếm gặp không nhất thiết đại diện cho tham số phổ biến.

Khi phân tích ứng dụng JDBC hoặc framework, cần xác định:

- Câu truy vấn có được prepare không?
- Giá trị tham số là gì?
- Plan được tạo theo tham số hiện tại hay có thể tái sử dụng?
- Session settings khác nhau không?

Không kết luận mọi sự khác biệt giữa EXPLAIN chạy tay và thực thi ứng dụng chỉ do index.

### 25.3. EXPLAIN trên literal khác với kế hoạch thực thi qua ứng dụng

Nếu ứng dụng dùng tham số:

```sql
WHERE customer_id = ?
```

còn bạn kiểm tra bằng literal:

```sql
WHERE customer_id = 42
```

kết quả đôi khi khác do cơ chế chuẩn bị/plan cache hoặc thay đổi tham số.

Muốn so đúng, cần tái tạo **cách truy vấn được thực thi trong ứng dụng**, không chỉ sao chép hình thức tương tự.

## 26. Làm sao đọc một cây kế hoạch theo trình tự hợp lý?

Đọc từ nút thấp tới cao và đối chiếu **đúng loại chỉ số**.

### Bước 1. Xác định truy vấn và số dòng mong đợi

Trước tiên hiểu:

- Truy vấn trả một dòng, vài dòng hay hàng triệu dòng?
- `WHERE` có chọn lọc không?
- `JOIN` có thể nhân dòng không?
- `GROUP BY` đang tạo một dòng trên khóa nào?
- `LIMIT` có làm dừng sớm không?

### Bước 2. Tìm các nút scan

Xem:

- `Seq Scan`.
- `Index Scan`.
- `Index Only Scan`.
- `Bitmap Heap Scan`.
- `Parallel Seq Scan`.

Đọc điều kiện `Index Cond` và `Filter` tương ứng, không mặc định mọi điều kiện ở `WHERE` đều được dùng làm điều kiện index.

### Bước 3. So estimated rows với actual rows

So **trên cùng một nút** và lưu ý `loops`.

Nếu một nút ước lượng 10 nhưng thực tế 10.000, cần xem sai số đó ảnh hưởng nút cha và join như thế nào.

### Bước 4. Xem những nút làm nhiều việc

Đặc biệt:

- `Nested Loop` với nút trong chạy hàng nghìn lần.
- `Sort` dùng disk.
- `Hash` có nhiều batch.
- `Aggregate` xử lý lượng dòng lớn.
- Các nút đọc nhiều dữ liệu rồi bị Filter loại gần hết.

### Bước 5. Xem BUFFERS và thời gian

Nếu query chậm, xem đó có phải do:

- Nhiều block read/hit.
- Sort/hash tốn tài nguyên.
- Truy cập bảng nhiều lần.
- Cardinality sai dẫn tới join không phù hợp.
- Truy vấn đang chờ khóa hoặc tài nguyên ngoài kế hoạch.

### Bước 6. Đề xuất thay đổi có căn cứ

Tùy nguyên nhân:

- `ANALYZE` nếu thống kê cũ.
- Index phù hợp filter/order/join.
- Thiết kế query giảm lượng dữ liệu sớm.
- Extended statistics cho cột tương quan.
- Thay đổi độ rộng dòng/kết quả.
- Điều chỉnh cấu hình có kiểm soát.
- Giảm truy cập đồng thời hoặc contention.

### Bước 7. Đo lại với cùng điều kiện

Đừng coi việc “kế hoạch đã có Index Scan” là mục tiêu cuối. Mục tiêu là **thời gian và tài nguyên phù hợp**, cùng kết quả SQL chính xác.

## 27. So sánh hai kế hoạch: số liệu nào đáng tin nhất?

Không có một con số duy nhất. Một cách trình bày đối chiếu:

| Khía cạnh | Trước thay đổi | Sau thay đổi | Câu hỏi cần xem |
|---|---|---|---|
| Hình dạng plan | Seq Scan + Sort | Index Scan + Limit | Đã giảm khối lượng xử lý chưa? |
| Estimated rows | 20 | 20 | Planner dự kiến đúng số dòng chứ? |
| Actual rows | 20 | 5 ở Limit | So cùng loại nút và semantics |
| Rows Removed by Filter | Lớn | Ít hơn | Nút nào loại dòng, có dừng sớm? |
| Buffer accesses | Cao | Thấp | Điều kiện cache có tương đương? |
| Execution Time | Thực đo | Thực đo | Chạy nhiều lần, không lấy một mẫu |
| Planning Time | Thực đo | Thực đo | Có đáng kể so với execution không? |
| DML side effects | Không có với SELECT thuần | Không có với SELECT thuần | Với UPDATE/DELETE, cần an toàn giao dịch |

**Đừng so hai `actual rows` ở các nút khác nhau rồi suy ra tỉ lệ cải thiện.** Ví dụ `actual rows=5` tại `Limit` sau index và `actual rows=20` tại `Seq Scan` trước index mô tả hai vị trí khác nhau trong cây.

## 28. Những ngộ nhận thường gặp

### Ngộ nhận 1. Cost bằng thời gian thực

Sai. `cost=0.29..15.71` là đơn vị cost nội bộ; `actual time=...` mới là thời gian đo, đơn vị ms.

### Ngộ nhận 2. EXPLAIN đã thực thi truy vấn

Không. `EXPLAIN` thông thường chỉ lập kế hoạch. Muốn thu thực tế, dùng `EXPLAIN ANALYZE`.

### Ngộ nhận 3. EXPLAIN ANALYZE chỉ “xem trước” UPDATE

Sai nguy hiểm. `EXPLAIN ANALYZE UPDATE` **chạy UPDATE thật**; có thể thay đổi dữ liệu, khóa và tạo WAL.

### Ngộ nhận 4. ROLLBACK làm phép đo DML luôn không có tác dụng phụ

Không hoàn toàn. Sequence/identity và tác dụng bên ngoài DB có thể không rollback; chi phí tài nguyên và ảnh hưởng khóa vẫn tồn tại trong lúc chạy.

### Ngộ nhận 5. Index Scan luôn tốt hơn Seq Scan

Không. Nếu lọc trả phần lớn bảng, seq scan có thể rẻ hơn rất nhiều truy cập ngẫu nhiên qua index.

### Ngộ nhận 6. Có Index Only Scan chắc chắn không đọc heap

Không. Xem `Heap Fetches` trong kế hoạch thực tế; MVCC/visibility map ảnh hưởng khả năng bỏ heap.

### Ngộ nhận 7. Rows=10 nghĩa query chắc chắn trả 10 dòng

Không. `rows` trong estimate là dự báo. Với actual còn phải xét nút, filter, LIMIT và loops.

### Ngộ nhận 8. Actual rows=3 loops=100 nghĩa tổng chỉ có 3 dòng

Sai. PostgreSQL thường báo actual rows theo trung bình mỗi vòng; tổng có thể khoảng 300 ở ví dụ này.

### Ngộ nhận 9. Aggregate rows=1 nghĩa chỉ đọc một dòng

Sai. `COUNT(*)` thường trả một dòng kết quả sau khi xử lý nhiều dòng đầu vào.

### Ngộ nhận 10. Rows Removed by Filter là dòng bị DELETE

Không. Đó là dòng bị loại khỏi **kết quả của nút** bởi điều kiện lọc.

### Ngộ nhận 11. Buffers shared hit là số lần truy cập đĩa

Không. Hit liên quan trang đã ở shared buffers; read cũng chưa đủ để suy ra mọi lượt đĩa vật lý do cache OS.

### Ngộ nhận 12. Cộng buffers của mọi nút để được tổng

Nhiều số liệu của nút cha có thể bao gồm công việc nút con; cộng máy móc có thể đếm trùng.

### Ngộ nhận 13. Một lần EXPLAIN ANALYZE là benchmark chắc chắn

Không. Thời gian phụ thuộc cache, workload, worker, instrument overhead và điều kiện hệ thống.

### Ngộ nhận 14. ANALYZE bảng và EXPLAIN ANALYZE là một

Sai. `ANALYZE table` thu thập thống kê; `EXPLAIN ANALYZE query` thực thi và đo query.

### Ngộ nhận 15. Planner ước lượng sai tức PostgreSQL bị lỗi

Có thể do thống kê, skew, tương quan, tham số hoặc giới hạn mô hình. Cần chẩn đoán thay vì kết luận ngay optimizer hỏng.

### Ngộ nhận 16. `SELECT *` và SELECT một vài cột sẽ có kế hoạch giống nhau

Không nhất thiết. Độ rộng dữ liệu và khả năng index-only có thể đổi plan.

### Ngộ nhận 17. LIMIT 5 nghĩa scan chỉ đọc 5 dòng

Không. Nếu cần sort/filter không có chỉ mục phù hợp, hệ thống có thể đọc nhiều dòng để tìm top 5.

### Ngộ nhận 18. Có index mới thì nhất định planner sẽ dùng

Không. Planner chọn kế hoạch theo cost dự kiến. Một index không hữu ích cho điều kiện này có thể không được sử dụng.

### Ngộ nhận 19. EXPLAIN chạy tay luôn giống prepared query của ứng dụng

Không nhất thiết, vì generic/custom plans, tham số và session settings khác nhau.

### Ngộ nhận 20. EXPLAIN ANALYZE đo toàn bộ trải nghiệm người dùng

Không. Nó đo thời gian ở DB theo công cụ, không tính đầy đủ network, ứng dụng, ORM và render giao diện.

## 29. Bài tập thực hành có lời giải

Các bài dùng bảng `lesson327_orders` đã tạo ở phần 5. Những con số `cost`, `actual time` và `Buffers` không có đáp án cố định vì phụ thuộc môi trường. Chỉ những số lượng nguồn được thiết kế theo `generate_series` mới có giá trị xác định.

### Bài 1. Phân biệt hai câu

```sql
EXPLAIN SELECT COUNT(*) FROM lesson327_orders;

EXPLAIN ANALYZE SELECT COUNT(*) FROM lesson327_orders;
```

**Câu hỏi:** câu nào chạy SELECT thật?

**Đáp án:** câu thứ hai, `EXPLAIN ANALYZE`. Câu thứ nhất chỉ đưa ra kế hoạch dự kiến.

### Bài 2. Đọc cost

Một kế hoạch có `cost=0.00..1500.00`. Có thể kết luận query mất 1.500 ms không?

**Đáp án:** không. Cost không phải mili giây; đây là chi phí planner ước lượng.

### Bài 3. Đọc rows và width

```text
Seq Scan on lesson327_orders
  (cost=0.00..2200.00 rows=20 width=24)
```

**Đáp án:** planner ước lượng scan cho 20 dòng đầu ra, kích thước trung bình khoảng 24 byte một dòng. Không có thông tin actual rows hay thời gian thực thi.

### Bài 4. Đọc actual time

```text
(actual time=0.020..2.400 rows=20 loops=1)
```

**Đáp án:** trong lần đo, nút phát 20 dòng qua một vòng thực hiện; hai mốc thời gian tính bằng ms cho quá trình nút bắt đầu phát và hoàn tất theo cách đo thực tế.

### Bài 5. Actual rows và loops

```text
(actual rows=4 loops=250)
```

**Câu hỏi:** tổng số dòng phát ra qua những vòng đó xấp xỉ bao nhiêu?

**Đáp án:** `4 × 250 = 1000`. Phải hiểu actual rows được báo theo bình quân mỗi vòng, không kết luận chỉ có 4 dòng tổng.

### Bài 6. Sai số cardinality

Estimate `rows=1000`, actual `rows=10 loops=1`.

**Đáp án:** planner ước lượng cao hơn thực tế khoảng **100 lần** tại nút ấy. Cần xem thống kê, điều kiện lọc và ảnh hưởng lên nút cha.

### Bài 7. Đếm đơn của khách 42

```sql
SELECT COUNT(*)
FROM lesson327_orders
WHERE customer_id = 42;
```

**Đáp án:** **20**, vì `((n-1)%5000)+1` lặp lại đúng 20 lần trên 100.000 dòng. Kế hoạch ước lượng có thể gần 20 sau `ANALYZE` nhưng không được xem là bảo đảm.

### Bài 8. Dùng EXPLAIN so với ANALYZE cho khách 42

```sql
EXPLAIN
SELECT *
FROM lesson327_orders
WHERE customer_id = 42;

EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM lesson327_orders
WHERE customer_id = 42;
```

**Đáp án:** câu đầu hiển thị plan và rows/cost dự kiến; câu sau chạy SELECT và cung cấp actual rows/loops/buffer và thời gian (theo tùy chọn).

### Bài 9. Vì sao sau khi tạo index plan có thể đổi?

```sql
CREATE INDEX lesson327_orders_customer_date_idx
    ON lesson327_orders(customer_id, order_date DESC);
```

**Đáp án:** PostgreSQL có thêm phương án truy cập theo khách và thứ tự ngày. Với điều kiện chọn ít dòng, index có thể giúp tránh seq scan hoặc sort, nhưng không đảm bảo planner luôn dùng.

**Lưu ý:** nếu chỉ mục đã được tạo ở phần 8, không chạy lại `CREATE INDEX` cùng tên. Bài này nhằm giải thích tác động của việc có chỉ mục.

### Bài 10. Có cần Sort không?

Truy vấn:

```sql
SELECT *
FROM lesson327_orders
WHERE customer_id = 42
ORDER BY order_date DESC
LIMIT 5;
```

**Đáp án:** chỉ mục `(customer_id, order_date DESC)` có thể cho phép lấy theo thứ tự mà không cần một nút `Sort` riêng. Kiểm tra bằng `EXPLAIN` và `EXPLAIN ANALYZE`; không áp đặt kết quả một plan cố định cho mọi cấu hình.

### Bài 11. `LIMIT 5` có nghĩa chỉ đọc năm dòng của bảng?

**Đáp án:** không. Có thể đọc nhiều dòng để lọc và sắp xếp nếu không có đường truy cập thích hợp. Xem các nút phía dưới `Limit`.

### Bài 12. Vì sao tìm PAID có thể dùng Seq Scan?

**Đáp án:** có 80.000/100.000 dòng PAID. Nếu phần lớn bảng phải được xét, scan tuần tự có thể rẻ hơn truy cập ngẫu nhiên qua index.

### Bài 13. Kết quả vùng SOUTH và PAID là bao nhiêu?

```sql
SELECT COUNT(*)
FROM lesson327_orders
WHERE region_code = 'SOUTH'
  AND status = 'PAID';
```

**Đáp án:** **0**, vì mọi SOUTH được sinh từ `n % 20 = 0`, cũng thuộc `n % 10 = 0`, tức CANCELLED.

### Bài 14. Vì sao planner có thể ước lượng không bằng 0?

**Đáp án:** nếu thống kê không thể hiện đầy đủ tương quan giữa `region_code` và `status`, mô hình selectivity có thể dự báo một số dòng dù thực tế không có. Extended statistics có thể giúp một số tình huống.

### Bài 15. Hai chữ ANALYZE khác nhau thế nào?

```sql
ANALYZE lesson327_orders;

EXPLAIN ANALYZE
SELECT COUNT(*) FROM lesson327_orders;
```

**Đáp án:** câu đầu thu thập thống kê planner của bảng. Câu sau thực thi và đo SELECT, không đơn thuần cập nhật thống kê optimizer.

### Bài 16. Ý nghĩa `Buffers: shared hit=20 read=4`

**Đáp án:** đây là số liệu truy cập trang trong bộ đệm chung; hit liên quan trang có sẵn trong shared buffers, read liên quan việc đưa trang vào shared buffers. Không suy trực tiếp ra 24 lần đọc đĩa vật lý hoặc 24 ms.

### Bài 17. Tại sao không cộng buffer của mọi nút?

**Đáp án:** một số thống kê của nút cha đã bao gồm hoạt động của nút con. Cộng mọi dòng có thể đếm trùng.

### Bài 18. Index Only Scan vẫn có Heap Fetches

**Đáp án:** để kiểm tra MVCC visibility trong trường hợp visibility map không đủ cho việc tránh heap. Phải xem `Heap Fetches` thực tế, không chỉ tên nút.

### Bài 19. Đo chi phí DML thế nào cho an toàn hơn?

```sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS)
UPDATE lesson327_orders
SET total_amount = total_amount + 1
WHERE customer_id = 42;

ROLLBACK;
```

**Đáp án:** `EXPLAIN ANALYZE` thực sự cập nhật các dòng trong transaction, và rollback hoàn tác thay đổi transactional. Nhưng phép đo vẫn có tác động tài nguyên/khóa, sequence hoặc trigger ngoài DB có thể không rollback; chỉ chạy ở môi trường phù hợp.

### Bài 20. EXPLAIN UPDATE có thay dữ liệu không?

```sql
EXPLAIN
UPDATE lesson327_orders
SET status = 'PAID'
WHERE customer_id = 42;
```

**Đáp án:** PostgreSQL lập kế hoạch nhưng không chạy UPDATE chính. Đây là lựa chọn để xem kế hoạch dự kiến khi chưa muốn thực thi DML.

### Bài 21. Actual time có phải thời gian HTTP request?

**Đáp án:** không. Thời gian EXPLAIN ANALYZE không gồm đầy đủ network, ORM, xử lý ứng dụng và render UI.

### Bài 22. Khi nào dùng TIMING OFF?

```sql
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF)
SELECT COUNT(*)
FROM lesson327_orders;
```

**Đáp án:** khi muốn quan sát actual rows/loops và buffers nhưng giảm overhead đo thời gian ở từng nút. Execution Time tổng vẫn có thể được báo cáo.

### Bài 23. Parallel Scan có Workers Launched khác Workers Planned

**Đáp án:** nguồn lực chạy thực tế có thể khác kế hoạch dự kiến. Muốn hiểu phân phối công việc phải xem worker và loops, không chỉ một số dòng ở nút parallel.

### Bài 24. Đánh giá Sort dùng disk

Một plan có `Sort Method: external merge Disk: ...`.

**Đáp án:** nút Sort đã dùng tệp/không gian tạm trên đĩa; kiểm tra lượng dữ liệu cần sort, chỉ mục/thứ tự truy vấn và cấu hình bộ nhớ. Không tự tăng `work_mem` toàn hệ thống khi chưa xét số query song song.

### Bài 25. Kế hoạch tay khác ứng dụng dù câu SQL giống nhau

**Đáp án:** có thể do tham số, generic/custom prepared plan, session settings, thống kê hoặc kiểu dữ liệu tham số. Phải tái hiện cách ứng dụng thực thi, không chỉ EXPLAIN một literal khác.

### Bài 26. Chọn công cụ cho ba mục đích

| Mục đích | Công cụ nên chọn |
|---|---|
| Xem trước bộ tối ưu hóa dự kiến làm gì | `EXPLAIN` |
| Biết actual rows/loops và thời gian đã chạy | `EXPLAIN ANALYZE` |
| Cập nhật thống kê planner sau nhập dữ liệu lớn | `ANALYZE table_name` |

**Đáp án:** đúng theo cột công cụ. Không nhầm chức năng của ba lệnh.

## 30. Quy trình thực hành khi truy vấn chậm

Khi gặp một truy vấn chậm, quy trình hợp lý là:

1. **Đọc câu SQL và xác định kết quả đúng**: khóa nào, bao nhiêu dòng, thứ tự nào.
2. **Chạy `EXPLAIN` trước** để xem kế hoạch ước lượng mà chưa thực thi dữ liệu, đặc biệt nếu có DML.
3. **Chọn phép đo an toàn**: với SELECT thuần trong môi trường phù hợp, dùng `EXPLAIN (ANALYZE, BUFFERS)`; với DML, cân nhắc staging và giao dịch rollback cùng giới hạn đã biết.
4. **Đọc cây từ nút thấp lên**; xem `Seq Scan`, `Index Scan`, `Join`, `Sort` và `Limit`.
5. **So estimated rows với actual rows** ở **cùng nút**, xét `loops` và parallel worker.
6. **Xem buffers, Sort Method, Heap Fetches và thời gian tổng thể** thay vì chỉ so `cost`.
7. **Tìm nguyên nhân chênh lệch**: thống kê cũ, skew, cột tương quan, thiếu index, phép JOIN nhân dòng, tham số khác.
8. **Thay đổi có kiểm soát**: cập nhật thống kê, tạo index phù hợp hoặc sửa query khi thật sự cần.
9. **Đo lại nhiều lần** dưới điều kiện tương đương, không tuyên bố cải thiện chỉ từ một lần chạy có cache khác.
10. **Xác nhận hiệu quả đầu cuối** trong ứng dụng nếu mục tiêu là giảm độ trễ người dùng.

## 31. Bảng ghi nhớ nhanh

| Nội dung | Điều quan trọng |
|---|---|
| `EXPLAIN` | Kế hoạch **ước lượng**, chưa thực thi câu SQL chính |
| `EXPLAIN ANALYZE` | Thực thi câu SQL và đo **thực tế** |
| `cost=startup..total` | Chi phí tương đối của planner, **không phải ms** |
| `rows` trong estimate | Số dòng dự kiến của nút |
| `width` | Kích thước trung bình dự kiến của dòng đầu ra |
| `actual time` | Thời gian đo của nút, tính bằng ms |
| `actual rows` | Số dòng thực tế được báo cho nút, thường trung bình mỗi loop |
| `loops` | Số lần nút được thực thi |
| `Rows Removed by Filter` | Số dòng bị loại bởi filter, **không phải DELETE** |
| `BUFFERS` | Thống kê truy cập block, không thay thời gian |
| `shared hit` | Trang được tìm thấy trong shared buffers |
| `shared read` | Trang được đọc vào shared buffers; không đồng nghĩa chắc chắn I/O vật lý |
| `Seq Scan` | Có thể là phương án tốt khi cần phần lớn bảng |
| `Index Scan` | Có thể phù hợp khi lọc ít dòng |
| `Index Only Scan` | Xem thêm `Heap Fetches`, không chỉ tên nút |
| `Sort Method` | Thể hiện thuật toán/bộ nhớ/đĩa khi chạy thực tế |
| `Parallel` | Xem số worker và loops, không coi mọi nút một lần duy nhất |
| `ANALYZE table` | Thu thập thống kê optimizer |
| `Extended statistics` | Có thể giúp ước lượng điều kiện nhiều cột tương quan |
| `TIMING OFF` | Giảm overhead đo thời gian từng nút |
| DML + `EXPLAIN ANALYZE` | **Thực thi DML thật**, có thể thay đổi dữ liệu |
| `ROLLBACK` phép đo DML | Hoàn tác dữ liệu transactional nhưng không xóa mọi tác dụng phụ |
| Prepared statements | Plan có thể phụ thuộc custom/generic và tham số |
| Benchmark | Nhiều phép đo, cùng điều kiện, hiểu cache và tải |
| Mục tiêu cuối | Query đúng, tài nguyên và độ trễ phù hợp |

## 32. Kết luận

**Kế hoạch ước lượng** là quyết định mà bộ tối ưu hóa đưa ra dựa trên thông tin sẵn có: cấu trúc bảng, chỉ mục, thống kê và mô hình chi phí. **Kế hoạch có thực thi** bổ sung sự thật của một lần chạy: những nút đã được thực hiện, số dòng thực sự đi qua, số vòng lặp, trang buffer và thời gian đo được.

Đối chiếu hai loại thông tin giúp bạn trả lời những câu hỏi quan trọng:

- PostgreSQL nghĩ điều kiện sẽ trả bao nhiêu dòng, và thực tế có bao nhiêu?
- Planner chọn Seq Scan vì bảng nhỏ, vì query trả gần hết dữ liệu, hay vì thiếu chỉ mục có ích?
- Một Nested Loop có chạy nút trong quá nhiều vòng so với dự kiến không?
- Sort có đụng đĩa tạm không?
- Một Index Only Scan có phải truy cập heap nhiều không?
- Query bị chậm do đường truy cập, ước lượng cardinality, bộ nhớ, cache hay yếu tố khác?

Và hãy luôn giữ ranh giới an toàn: **`EXPLAIN ANALYZE` thực thi truy vấn**. Với `UPDATE`, `DELETE`, `INSERT` hoặc `MERGE`, phép đo có thể thay đổi dữ liệu thật. Bắt đầu bằng `EXPLAIN` khi chỉ muốn xem dự kiến; chỉ đo thực tế khi bạn hiểu rõ ảnh hưởng và có môi trường kiểm thử phù hợp.

## Tài liệu tham khảo

- [PostgreSQL — EXPLAIN](https://www.postgresql.org/docs/current/sql-explain.html): tùy chọn `ANALYZE`, `BUFFERS`, `TIMING`, `FORMAT` và những cảnh báo khi thực thi DML.
- [PostgreSQL — Using EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html): cách đọc cost, rows, width, plan nodes và thống kê thực tế.
- [PostgreSQL — Planner Statistics](https://www.postgresql.org/docs/current/planner-stats.html): thống kê ước lượng selectivity và extended statistics.
- [PostgreSQL — ANALYZE](https://www.postgresql.org/docs/current/sql-analyze.html): thu thập thống kê cho query planner.
- [PostgreSQL — Indexes](https://www.postgresql.org/docs/current/indexes.html): chỉ mục, truy cập index và chiến lược sử dụng.
- [PostgreSQL — Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html): bộ đệm, I/O và thống kê quan sát.
- [MySQL — EXPLAIN](https://dev.mysql.com/doc/refman/8.4/en/explain.html): cú pháp và thông tin kế hoạch của MySQL, với các khả năng runtime tùy phiên bản.
- [SQLite — EXPLAIN QUERY PLAN](https://www.sqlite.org/eqp.html): hiển thị chiến lược truy cập của SQLite, không tương đương trực tiếp đầy đủ với PostgreSQL `EXPLAIN ANALYZE`.

