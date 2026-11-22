# GROUP BY và lựa chọn mức tổng hợp trong PostgreSQL

Trong ứng dụng thực tế, dữ liệu thường được lưu ở mức rất chi tiết: **một hàng cho một đơn hàng**, **một hàng cho một dòng sản phẩm**, **một hàng cho một lần thanh toán** hoặc **một hàng cho một sự kiện**. Nhưng người sử dụng cần những câu hỏi khác: “Doanh thu từng tháng bao nhiêu?”, “Mỗi cửa hàng có bao nhiêu đơn?”, “Mỗi khách hàng mua bao nhiêu lần?” hay “Tổng toàn hệ thống khác tổng theo khu vực ra sao?”.

Trong PostgreSQL, **`GROUP BY`** gom những hàng có cùng giá trị khóa nhóm lại thành từng nhóm. Các hàm tổng hợp như `COUNT`, `SUM`, `AVG`, `MIN`, `MAX` được tính **trên mỗi nhóm**. Tuy nhiên, viết được cú pháp `GROUP BY` mới chỉ là một phần của bài toán. Điều quyết định báo cáo **đúng hay sai** là chọn **mức tổng hợp** (*grain*, tức mỗi hàng kết quả đại diện cho điều gì) phù hợp với câu hỏi nghiệp vụ.

Ví dụ, từ bảng đơn hàng:

- `GROUP BY tenant_id` → **mỗi tenant một hàng**.
- `GROUP BY tenant_id, region` → **mỗi cặp tenant–vùng một hàng**.
- `GROUP BY date_trunc('month', created_at)` → **mỗi tháng một hàng** theo cách xác định múi giờ.
- Không có `GROUP BY`, chỉ dùng `SUM(...)` → **một tổng chung**.
- `GROUP BY ROLLUP(...)` hoặc `GROUPING SETS(...)` → **nhiều mức tổng hợp trong một kết quả**, ví dụ chi tiết theo vùng, tổng tenant và tổng toàn hệ thống.

Nếu chọn sai mức, kết quả vẫn có thể chạy được và trông hợp lý nhưng **đếm sai**, **nhân đôi doanh thu sau JOIN**, **tính trung bình sai** hoặc **trộn dữ liệu của nhiều tenant**.

Bài học thuộc chương **Tổng hợp dữ liệu** của module *Database Engine Relational PostgreSQL*. Sau khi học, bạn sẽ có thể giải thích ngữ nghĩa `GROUP BY`, chọn khóa nhóm theo câu hỏi, sử dụng `HAVING`/`FILTER`, xử lý `NULL`, tổng hợp theo ngày tháng, phân biệt `GROUPING SETS`/`ROLLUP`/`CUBE`, tránh lỗi JOIN làm nhân bản hàng và đánh giá cách PostgreSQL thực thi các truy vấn tổng hợp.

> **Phạm vi:** Các ví dụ dùng PostgreSQL hiện đại, schema `agg_lab` riêng và dữ liệu giả định. Những câu lệnh tạo bảng/chèn dữ liệu dùng để thực hành trên database thử nghiệm. Không dùng tên bảng hoặc số liệu trong bài như dữ liệu production.

## 1. Mức tổng hợp (*grain*) là gì?

Trước khi viết SQL, hãy hoàn thành câu:

> “**Mỗi hàng trong kết quả đại diện cho ...**”

Ví dụ:

| Câu hỏi | Một hàng kết quả đại diện cho | Khóa nhóm gợi ý |
|---|---|---|
| Toàn hệ thống có bao nhiêu đơn đã thanh toán? | Toàn bộ tập đơn phù hợp | Không cần `GROUP BY` |
| Mỗi tenant có bao nhiêu đơn đã thanh toán? | Một tenant | `tenant_id` |
| Doanh thu theo vùng trong từng tenant? | Một cặp tenant–vùng | `tenant_id, region` |
| Doanh thu từng tháng của từng tenant? | Một cặp tenant–tháng | `tenant_id, month_bucket` |
| Số khách mua hàng theo kênh trong từng tháng? | Một cặp tháng–kênh | `month_bucket, channel` |
| Một báo cáo gồm chi tiết, subtotal và grand total? | Nhiều mức được đánh dấu rõ | `GROUPING SETS` hoặc `ROLLUP` |

**Grain của dữ liệu nguồn** khác **grain của kết quả**. Nếu dữ liệu nguồn đã có một hàng cho mỗi **dòng sản phẩm**, `COUNT(*)` sau khi `JOIN` không còn là số đơn hàng nữa. Đây là nguyên nhân rất phổ biến của báo cáo sai.

### 1.1. Sơ đồ tư duy: từ hàng chi tiết đến nhóm

```text
Dữ liệu gốc: mỗi hàng = một đơn hàng
    |
    | WHERE status = 'paid'
    v
Chỉ giữ những đơn đã thanh toán
    |
    | GROUP BY tenant_id, region
    v
Mỗi nhóm = một cặp tenant / region
    |
    | COUNT(*), SUM(total_amount)
    v
Mỗi hàng kết quả = số đơn + doanh thu của nhóm đó
    |
    | HAVING ..., ORDER BY ...
    v
Báo cáo gửi đến người dùng
```

`GROUP BY` không tự biết đơn hàng nào “đã hoàn tất” hoặc tổng tiền nào “là doanh thu”. Những quy tắc đó phải thể hiện ở `WHERE`, hàm tổng hợp, điều kiện `FILTER` hoặc mô hình dữ liệu.

### 1.2. Đừng bắt đầu bằng danh sách cột SELECT

Một cách làm dễ sai là liệt kê mọi cột có vẻ hữu ích vào `SELECT` rồi tìm cách “thêm đủ chúng vào `GROUP BY` để SQL hết lỗi”. Nếu câu hỏi chỉ cần **mỗi tenant một hàng**, thêm `order_id` vào `GROUP BY` sẽ biến mỗi đơn thành một nhóm, khiến không còn tổng hợp theo tenant như mong đợi.

Thay vào đó:

1. Xác định **đối tượng đếm/tính tiền** (đơn, dòng hàng, khách, giao dịch thanh toán).
2. Xác định **bộ lọc** (chỉ paid, thời gian, tenant, quyền truy cập).
3. Xác định **khóa nhóm** (tenant, vùng, tháng, kênh).
4. Chọn **hàm tổng hợp** phù hợp với mỗi chỉ tiêu.
5. Kiểm tra liệu việc `JOIN` có thay đổi grain của dữ liệu đầu vào hay không.

## 2. Chuẩn bị bộ dữ liệu thực hành

Ta tạo bảng `orders` mà **mỗi hàng là một đơn hàng**. Mỗi đơn có tenant, khách, thời điểm, vùng (có thể chưa biết), kênh bán, trạng thái và tổng tiền. Sau đó thêm `order_items` để minh họa rủi ro khi JOIN.

### 2.1. Tạo bảng đơn hàng

```sql
CREATE SCHEMA IF NOT EXISTS agg_lab;

CREATE TABLE agg_lab.orders (
    order_id BIGINT PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    customer_id BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    region TEXT,
    channel TEXT NOT NULL
        CHECK (channel IN ('web', 'store')),
    status TEXT NOT NULL
        CHECK (status IN ('paid', 'pending', 'cancelled')),
    total_amount NUMERIC(12, 2) NOT NULL
        CHECK (total_amount >= 0)
);
```

`NUMERIC` được chọn cho số tiền minh họa nhằm tránh sai số dấu phẩy động trong các phép cộng thông thường. Trong hệ thống thật, còn cần thống nhất đơn vị tiền tệ, thuế, giảm giá, phí vận chuyển và định nghĩa thế nào được gọi là “doanh thu”.

### 2.2. Chèn dữ liệu

```sql
INSERT INTO agg_lab.orders
    (order_id, tenant_id, customer_id, created_at,
     region, channel, status, total_amount)
VALUES
    ( 1, 10, 101, '2026-01-05 10:00:00+07', 'north', 'web',   'paid',      300),
    ( 2, 10, 102, '2026-01-07 11:00:00+07', 'north', 'store', 'paid',      180),
    ( 3, 10, 101, '2026-01-12 12:00:00+07', 'south', 'web',   'pending',   240),
    ( 4, 10, 103, '2026-02-02 08:30:00+07', 'south', 'web',   'paid',      120),
    ( 5, 10, 104, '2026-02-07 14:00:00+07', 'north', 'web',   'cancelled', 500),
    ( 6, 10, 102, '2026-02-15 15:00:00+07', NULL,    'store', 'paid',       90),
    ( 7, 10, 101, '2026-03-05 09:00:00+07', 'south', 'store', 'paid',      250),
    ( 8, 20, 201, '2026-01-08 10:00:00+07', 'north', 'web',   'paid',      400),
    ( 9, 20, 202, '2026-01-11 16:00:00+07', 'south', 'store', 'paid',      160),
    (10, 20, 201, '2026-02-01 09:00:00+07', 'south', 'web',   'pending',   350),
    (11, 20, 203, '2026-02-20 17:00:00+07', NULL,    'web',   'paid',       80),
    (12, 20, 201, '2026-03-06 13:00:00+07', 'north', 'store', 'paid',      230);
```

Tổng cộng có **12 đơn**, trong đó **9 đơn `paid`**, **2 đơn `pending`** và **1 đơn `cancelled`**. Khi bài này nói “doanh thu đơn hàng đã thanh toán”, ta dùng `status = 'paid'` và cộng `total_amount` của các hàng đó. Đây là quy ước lab, không phải định nghĩa kế toán cho mọi doanh nghiệp.

Các đơn đã thanh toán:

| tenant_id | order_id | region | total_amount |
|---:|---:|---|---:|
| 10 | 1 | north | 300 |
| 10 | 2 | north | 180 |
| 10 | 4 | south | 120 |
| 10 | 6 | `NULL` | 90 |
| 10 | 7 | south | 250 |
| 20 | 8 | north | 400 |
| 20 | 9 | south | 160 |
| 20 | 11 | `NULL` | 80 |
| 20 | 12 | north | 230 |

Lưu ý các thời điểm có offset `+07`. Giá trị `TIMESTAMPTZ` biểu diễn một thời điểm thực; khi nhóm theo ngày/tháng địa phương, cần chọn múi giờ nghiệp vụ một cách nhất quán.

### 2.3. Bảng chi tiết một-nhiều để dùng về sau

```sql
CREATE TABLE agg_lab.order_items (
    item_id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL
        REFERENCES agg_lab.orders(order_id),
    category TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    line_total NUMERIC(12, 2) NOT NULL
        CHECK (line_total >= 0)
);

INSERT INTO agg_lab.order_items
    (item_id, order_id, category, quantity, line_total)
VALUES
    ( 1,  1, 'device',  1, 200),
    ( 2,  1, 'addon',   1, 100),
    ( 3,  2, 'device',  1, 180),
    ( 4,  4, 'addon',   2, 120),
    ( 5,  6, 'service', 1,  90),
    ( 6,  7, 'device',  1, 200),
    ( 7,  7, 'addon',   1,  50),
    ( 8,  8, 'device',  2, 360),
    ( 9,  8, 'service', 1,  40),
    (10,  9, 'addon',   2, 160),
    (11, 11, 'service', 1,  80),
    (12, 12, 'device',  1, 150),
    (13, 12, 'addon',   2,  80);
```

Với dữ liệu này:

- `orders` có **một hàng cho một đơn hàng**.
- `order_items` có **một hàng cho một dòng sản phẩm**.
- Một đơn có thể có **nhiều dòng sản phẩm**: `order_id=1` có hai dòng, `order_id=8` có hai dòng.
- Các dòng `line_total` của mỗi đơn `paid` trong lab cộng đúng bằng `orders.total_amount`.
- Các đơn `pending`/`cancelled` trong ví dụ chưa có dòng item; điều đó phục vụ minh họa, không phải quy tắc bắt buộc của database bán hàng thật.

Để kiểm tra dữ liệu không cần dựa trên ghi nhớ:

```sql
SELECT status, COUNT(*) AS so_don
FROM agg_lab.orders
GROUP BY status
ORDER BY status;
```

## 3. GROUP BY đơn giản: một nhóm cho mỗi giá trị

Hãy trả lời: **Mỗi tenant có bao nhiêu đơn đã thanh toán và tổng số tiền bao nhiêu?**

```sql
SELECT
    tenant_id,
    COUNT(*) AS paid_orders,
    SUM(total_amount) AS paid_amount
FROM agg_lab.orders
WHERE status = 'paid'
GROUP BY tenant_id
ORDER BY tenant_id;
```

Kết quả dự kiến:

| tenant_id | paid_orders | paid_amount |
|---:|---:|---:|
| 10 | 5 | 940 |
| 20 | 4 | 870 |

Giải thích từng phần:

- `FROM agg_lab.orders`: chọn dữ liệu gốc ở grain một hàng/đơn.
- `WHERE status = 'paid'`: chỉ giữ đơn đã thanh toán.
- `GROUP BY tenant_id`: tạo hai nhóm, tenant 10 và tenant 20.
- `COUNT(*)`: đếm số **hàng** trong từng nhóm, ở đây tương đương số đơn.
- `SUM(total_amount)`: cộng tiền của các đơn trong nhóm.
- `ORDER BY tenant_id`: sắp thứ tự kết quả. `GROUP BY` **không tự bảo đảm thứ tự xuất ra**.

Đây là một ví dụ đúng vì câu hỏi nghiệp vụ, grain nguồn, bộ lọc và khóa nhóm đều ăn khớp.

### 3.1. GROUP BY nhiều cột: chi tiết hơn

Nếu muốn **mỗi tenant, mỗi vùng một hàng**:

```sql
SELECT
    tenant_id,
    region,
    COUNT(*) AS paid_orders,
    SUM(total_amount) AS paid_amount
FROM agg_lab.orders
WHERE status = 'paid'
GROUP BY tenant_id, region
ORDER BY tenant_id, region NULLS LAST;
```

Kết quả:

| tenant_id | region | paid_orders | paid_amount |
|---:|---|---:|---:|
| 10 | north | 2 | 480 |
| 10 | south | 2 | 370 |
| 10 | `NULL` | 1 | 90 |
| 20 | north | 2 | 630 |
| 20 | south | 1 | 160 |
| 20 | `NULL` | 1 | 80 |

Thêm `region` vào khóa nhóm làm kết quả **chi tiết hơn**, chứ không làm nhóm “chính xác hơn” trong mọi bài toán. Khi báo cáo cần một hàng/tenant, `region` không nên nằm trong `GROUP BY` của kết quả cuối.

### 3.2. Lựa chọn mức tổng hợp thay đổi số hàng kết quả

Với chín đơn `paid` trong lab:

| Cách viết | Grain kết quả | Số hàng dự kiến |
|---|---|---:|
| `SUM(total_amount)` | Toàn bộ đơn paid | 1 |
| `GROUP BY tenant_id` | Một tenant | 2 |
| `GROUP BY region` | Một vùng, bao gồm nhóm NULL | 3 |
| `GROUP BY tenant_id, region` | Một cặp tenant–vùng | 6 |
| `GROUP BY order_id` | Một đơn | 9 |

Nếu bạn yêu cầu “tổng theo tenant” nhưng câu truy vấn sinh ra chín hàng, rất có thể đã đưa khóa chi tiết như `order_id` vào `GROUP BY`.

## 4. Quy tắc SELECT, GROUP BY và lỗi cột chưa tổng hợp

Một câu truy vấn tổng hợp thông thường có thể chọn:

1. Những **biểu thức nhóm** được xác định bởi `GROUP BY`.
2. Kết quả của **hàm tổng hợp** như `COUNT(*)`, `SUM(total_amount)`.
3. Một số biểu thức khác mà PostgreSQL có thể chứng minh phụ thuộc hàm vào khóa nhóm, với các giới hạn được hỗ trợ.

Ví dụ đúng:

```sql
SELECT tenant_id, SUM(total_amount)
FROM agg_lab.orders
WHERE status = 'paid'
GROUP BY tenant_id;
```

Ví dụ sai về grain:

```sql
-- Sai: region có thể có nhiều giá trị trong cùng tenant.
-- SELECT tenant_id, region, SUM(total_amount)
-- FROM agg_lab.orders
-- GROUP BY tenant_id;
```

PostgreSQL thường báo lỗi dạng:

```text
column "orders.region" must appear in the GROUP BY clause
or be used in an aggregate function
```

SQLSTATE tương ứng thường là `42803` (`grouping_error`).

**Không chữa lỗi bằng cách thêm ngẫu nhiên `region` vào `GROUP BY`** nếu yêu cầu ban đầu vẫn là một hàng/tenant. Hãy quyết định:

- Nếu cần **chi tiết mỗi tenant–vùng**, nhóm theo cả hai.
- Nếu cần **một tenant**, bỏ `region` khỏi SELECT, hoặc dùng một phép tổng hợp có ý nghĩa rõ với dữ liệu vùng, ví dụ `COUNT(DISTINCT region)`.
- Nếu chỉ muốn một bản ghi đại diện, xác định quy tắc chọn đại diện thay vì dùng `MIN(region)` một cách tùy tiện.

### 4.1. GROUP BY biểu thức

Không bắt buộc nhóm theo cột thô. Có thể nhóm theo biểu thức:

```sql
SELECT
    lower(channel) AS channel_key,
    COUNT(*) AS order_count
FROM agg_lab.orders
GROUP BY lower(channel)
ORDER BY channel_key;
```

Trong lab `channel` đã có dữ liệu chuẩn `web`/`store`, nhưng tình huống thực tế có thể dùng `lower`, `date_trunc`, `COALESCE` hoặc một biểu thức định nghĩa bucket.

**Lưu ý:** Hai giá trị khác nhau trước khi chuẩn hóa có thể trở thành **cùng một khóa nhóm** sau khi áp biểu thức. Hãy quyết định chính sách chuẩn hóa trước thay vì để một biểu thức vô tình hợp nhất những nhóm khác nghĩa.

### 4.2. GROUP BY theo vị trí cột SELECT

PostgreSQL chấp nhận cú pháp theo vị trí:

```sql
SELECT tenant_id, region, SUM(total_amount)
FROM agg_lab.orders
GROUP BY 1, 2
ORDER BY 1, 2;
```

`1` và `2` trong ngữ cảnh này tham chiếu biểu thức thứ nhất/thứ hai của danh sách SELECT. Dù ngắn, cách viết có thể khó bảo trì: nếu thêm hoặc đổi thứ tự cột SELECT, ngữ nghĩa GROUP BY có thể đổi ngoài ý muốn.

Trong tài liệu và truy vấn quan trọng, ghi tường minh `GROUP BY tenant_id, region` thường rõ nghĩa hơn.

### 4.3. Trường hợp phụ thuộc hàm vào PRIMARY KEY

PostgreSQL có thể cho phép chọn các cột khác khi các cột nhóm bao gồm **khóa chính của bảng** và phụ thuộc hàm được nhận diện:

```sql
SELECT
    order_id,
    customer_id,
    total_amount
FROM agg_lab.orders
GROUP BY order_id;
```

Vì `order_id` là `PRIMARY KEY` của bảng `orders`, mỗi nhóm có tối đa một đơn, nên `customer_id` và `total_amount` được xác định bởi khóa đó. Tuy nhiên, truy vấn này thực tế **không cộng gộp nhiều đơn**, vì mỗi đơn tạo một nhóm.

Không mở rộng quy tắc tùy tiện cho mọi unique index, phép JOIN hoặc mọi biểu thức mà con người “biết chắc là duy nhất”. PostgreSQL có những điều kiện nhận diện functional dependency cụ thể; khi báo cáo tổng hợp, nên dùng `GROUP BY` rõ grain và các hàm aggregate thích hợp.

## 5. Thứ tự logic: WHERE, GROUP BY, HAVING, SELECT, ORDER BY

Để tránh nhầm bộ lọc hàng với bộ lọc nhóm, có thể hình dung luồng xử lý:

```text
FROM / JOIN
    |
    v
WHERE                -- lọc các hàng đầu vào
    |
    v
GROUP BY             -- tạo nhóm theo khóa
    |
    v
Hàm tổng hợp          -- COUNT, SUM, AVG... cho từng nhóm
    |
    v
HAVING               -- lọc cả nhóm sau khi đã tổng hợp
    |
    v
SELECT               -- định dạng biểu thức đầu ra
    |
    v
ORDER BY             -- sắp kết quả trả về
    |
    v
LIMIT / OFFSET       -- giới hạn và phân trang kết quả
```

Đây là **mô hình logic để hiểu SQL**, không phải khẳng định executor vật lý của PostgreSQL luôn chạy từng bước đúng thứ tự đó. Optimizer có thể đẩy điều kiện, chọn `HashAggregate`/`GroupAggregate` và thay đổi cách triển khai nhưng phải giữ ngữ nghĩa truy vấn.

### 5.1. WHERE lọc hàng trước khi gom nhóm

```sql
SELECT tenant_id, SUM(total_amount) AS paid_amount
FROM agg_lab.orders
WHERE status = 'paid'
GROUP BY tenant_id;
```

Đơn `pending` và `cancelled` **không có mặt trong đầu vào** của phép tổng hợp.

### 5.2. HAVING lọc nhóm dựa vào kết quả aggregate

Muốn tìm những tenant có **doanh thu đã thanh toán ít nhất 900**:

```sql
SELECT
    tenant_id,
    COUNT(*) AS paid_orders,
    SUM(total_amount) AS paid_amount
FROM agg_lab.orders
WHERE status = 'paid'
GROUP BY tenant_id
HAVING SUM(total_amount) >= 900
ORDER BY tenant_id;
```

Kết quả chỉ có **tenant 10** với 940, vì tenant 20 có 870.

Không dùng:

```sql
-- Sai vị trí: WHERE không thể lọc dựa trên SUM của cả nhóm.
-- SELECT tenant_id, SUM(total_amount)
-- FROM agg_lab.orders
-- WHERE SUM(total_amount) >= 900
-- GROUP BY tenant_id;
```

### 5.3. Đặt điều kiện ở WHERE hay HAVING?

Hai truy vấn sau **không tương đương**:

```sql
-- A: Loại đơn nhỏ trước khi tính tổng.
SELECT tenant_id, SUM(total_amount) AS amount_large_orders
FROM agg_lab.orders
WHERE status = 'paid'
  AND total_amount >= 200
GROUP BY tenant_id;

-- B: Tính tổng tất cả đơn paid, rồi giữ tenant có tổng >= 200.
SELECT tenant_id, SUM(total_amount) AS total_paid_amount
FROM agg_lab.orders
WHERE status = 'paid'
GROUP BY tenant_id
HAVING SUM(total_amount) >= 200;
```

Trong A, điều kiện `total_amount >= 200` là **điều kiện trên từng đơn**. Trong B, điều kiện `SUM(total_amount) >= 200` là **điều kiện trên tổng của cả tenant**.

Một số điều kiện chỉ dựa vào khóa nhóm có thể viết ở cả `WHERE` và `HAVING` về mặt kết quả; thông thường nên đặt điều kiện lọc hàng ở `WHERE` để diễn đạt ý định rõ ràng và giảm dữ liệu phải tổng hợp.

### 5.4. ORDER BY là bước riêng

`GROUP BY tenant_id` không cam kết trả tenant tăng dần. Nếu muốn doanh thu giảm dần và tránh tie chưa xác định:

```sql
SELECT tenant_id, SUM(total_amount) AS paid_amount
FROM agg_lab.orders
WHERE status = 'paid'
GROUP BY tenant_id
ORDER BY paid_amount DESC, tenant_id ASC;
```

Trong PostgreSQL có thể tham chiếu alias `paid_amount` ở `ORDER BY`. Với nhóm có cùng tổng tiền, `tenant_id` là khóa phân định để thứ tự ổn định cho cùng tập dữ liệu.

## 6. COUNT, SUM, AVG, MIN, MAX: đúng hàm, đúng mẫu số

### 6.1. COUNT(*) và COUNT(column) không giống nhau

`COUNT(*)` đếm **số hàng**. `COUNT(expr)` đếm **các hàng mà biểu thức expr không phải NULL**.

Trong lab, `region` có hai đơn paid không rõ vùng:

```sql
SELECT
    COUNT(*) AS so_don_paid,
    COUNT(region) AS so_don_co_vung,
    COUNT(*) - COUNT(region) AS so_don_chua_co_vung
FROM agg_lab.orders
WHERE status = 'paid';
```

Kết quả:

| so_don_paid | so_don_co_vung | so_don_chua_co_vung |
|---:|---:|---:|
| 9 | 7 | 2 |

Nếu mục tiêu là đếm số đơn, đừng dùng `COUNT(region)` khi `region` được phép NULL. Nó sẽ bỏ hai đơn không có vùng và cho kết quả sai.

### 6.2. COUNT(DISTINCT): đếm số giá trị khác nhau

Trong tenant 10, các đơn paid thuộc khách 101, 102, 103, 102 và 101. Vì thế số đơn là 5 nhưng số khách đã mua là 3.

```sql
SELECT
    tenant_id,
    COUNT(*) AS paid_orders,
    COUNT(DISTINCT customer_id) AS paying_customers
FROM agg_lab.orders
WHERE status = 'paid'
GROUP BY tenant_id
ORDER BY tenant_id;
```

Kết quả:

| tenant_id | paid_orders | paying_customers |
|---:|---:|---:|
| 10 | 5 | 3 |
| 20 | 4 | 3 |

`COUNT(DISTINCT customer_id)` không tính lặp cùng khách trong **một nhóm**, nhưng nếu cùng khách có mặt ở nhiều nhóm, việc cộng các số distinct của các nhóm có thể **đếm lặp khách**.

### 6.3. SUM và AVG bỏ qua NULL, nhưng mẫu số khác nhau

`SUM(expr)` cộng các giá trị không NULL, `AVG(expr)` lấy trung bình những giá trị **không NULL**. Trong bảng lab, `total_amount NOT NULL` nên `AVG(total_amount)` chính là tổng tiền / số đơn của nhóm.

```sql
SELECT
    tenant_id,
    SUM(total_amount) AS paid_amount,
    COUNT(*) AS paid_orders,
    ROUND(AVG(total_amount), 2) AS avg_order_value
FROM agg_lab.orders
WHERE status = 'paid'
GROUP BY tenant_id
ORDER BY tenant_id;
```

Kết quả:

| tenant_id | paid_amount | paid_orders | avg_order_value |
|---:|---:|---:|---:|
| 10 | 940 | 5 | 188.00 |
| 20 | 870 | 4 | 217.50 |

Với cột nullable, trung bình `AVG(column)` **không chia cho `COUNT(*)`** mà chia cho `COUNT(column)`. Nếu nghiệp vụ coi missing là 0 thì cần thể hiện chính sách đó tường minh bằng `COALESCE`, nhưng phải hiểu việc thay missing bằng 0 có thể làm thay đổi ý nghĩa thống kê.

### 6.4. MIN và MAX

```sql
SELECT
    tenant_id,
    MIN(total_amount) AS min_paid_order,
    MAX(total_amount) AS max_paid_order,
    MIN(created_at) AS first_paid_at,
    MAX(created_at) AS last_paid_at
FROM agg_lab.orders
WHERE status = 'paid'
GROUP BY tenant_id
ORDER BY tenant_id;
```

Các hàm `MIN`/`MAX` tìm cực trị theo kiểu và quy tắc so sánh của biểu thức, không “lấy toàn bộ hàng” tương ứng cực trị. Ví dụ `MAX(total_amount)` trả số tiền lớn nhất, chứ không tự trả `order_id` của đơn lớn nhất. Nếu cần cả hàng có giá trị lớn nhất, dùng chiến lược phù hợp như `ORDER BY ... LIMIT 1`, `DISTINCT ON` hoặc window function.

### 6.5. Tổng hợp không GROUP BY: một hàng chung

```sql
SELECT
    COUNT(*) AS paid_orders,
    SUM(total_amount) AS paid_amount,
    ROUND(AVG(total_amount), 2) AS avg_paid_order
FROM agg_lab.orders
WHERE status = 'paid';
```

Kết quả:

| paid_orders | paid_amount | avg_paid_order |
|---:|---:|---:|
| 9 | 1810 | 201.11 |

Đây là **một nhóm toàn cục**, không phải “mọi hàng có tenant giống nhau”. Khi mục tiêu là tổng toàn hệ thống, không cần thêm `GROUP BY tenant_id` rồi cộng thủ công kết quả nếu truy vấn tổng trực tiếp đã diễn đạt rõ mục tiêu.

### 6.6. Khi không có hàng phù hợp

```sql
SELECT
    COUNT(*) AS row_count,
    SUM(total_amount) AS total,
    AVG(total_amount) AS average
FROM agg_lab.orders
WHERE status = 'paid'
  AND tenant_id = -1;
```

Kết quả là **một hàng** với `row_count=0`, còn `SUM` và `AVG` là `NULL` (vì không có giá trị nào để cộng hoặc lấy trung bình).

Nếu thêm `GROUP BY tenant_id` vào cùng điều kiện, kết quả thường **không có hàng nào**, vì không tồn tại nhóm nào. Phân biệt:

- **Không GROUP BY:** một nhóm toàn cục, ngay cả khi đầu vào rỗng; `COUNT(*) = 0`.
- **Có GROUP BY trên khóa cột:** không có nhóm nếu không có hàng phù hợp.

Nếu API thật sự muốn số tiền 0 thay vì `NULL`:

```sql
SELECT COALESCE(SUM(total_amount), 0) AS total
FROM agg_lab.orders
WHERE tenant_id = -1;
```

`COALESCE` này là quyết định trình bày/nghiệp vụ; **đừng thay `NULL` bằng 0 một cách mù quáng** trong các chỉ tiêu mà “không có dữ liệu” khác nghĩa với số 0.

## 7. GROUP BY và NULL: nhóm “chưa biết”

Trong PostgreSQL, khi nhóm theo một cột nullable, những hàng có `NULL` ở khóa nhóm được **gom vào cùng một nhóm**.

```sql
SELECT
    region,
    COUNT(*) AS paid_orders,
    SUM(total_amount) AS paid_amount
FROM agg_lab.orders
WHERE status = 'paid'
GROUP BY region
ORDER BY region NULLS LAST;
```

Kết quả:

| region | paid_orders | paid_amount |
|---|---:|---:|
| north | 4 | 1110 |
| south | 3 | 530 |
| `NULL` | 2 | 170 |

Đây là điểm cần phân biệt với toán tử `NULL = NULL` trong biểu thức thường: `NULL = NULL` cho unknown, nhưng **`GROUP BY` gom những giá trị NULL của cùng khóa vào một nhóm** theo quy tắc nhóm của SQL.

### 7.1. Đổi nhãn NULL để hiển thị

```sql
SELECT
    COALESCE(region, '(chưa xác định)') AS region_label,
    COUNT(*) AS paid_orders
FROM agg_lab.orders
WHERE status = 'paid'
GROUP BY COALESCE(region, '(chưa xác định)')
ORDER BY region_label;
```

Đây là cách hợp lý nếu muốn người xem thấy nhãn rõ hơn. Tuy nhiên, nếu dữ liệu có **giá trị region thật** bằng đúng chuỗi `'(chưa xác định)'`, biểu thức `COALESCE` sẽ hợp nhất nó với nhóm `NULL`.

Trong trường hợp nhãn có thể va chạm, hãy giữ `region` gốc làm khóa nhóm và chỉ đổi nhãn ở bước trình bày:

```sql
SELECT
    COALESCE(region, '(chưa xác định)') AS region_label,
    COUNT(*) AS paid_orders
FROM agg_lab.orders
WHERE status = 'paid'
GROUP BY region
ORDER BY region NULLS LAST;
```

Hai nhóm `region` khác nhau vẫn là hai nhóm trong phép `GROUP BY region`, dù nhãn hiển thị có thể trùng. Ứng dụng có thể cần trả kèm khóa gốc hoặc một mã phân biệt trong API.

### 7.2. Không dùng COUNT(region) để đếm mọi đơn trong nhóm NULL

```sql
SELECT
    region,
    COUNT(*) AS rows_in_group,
    COUNT(region) AS nonnull_region_values
FROM agg_lab.orders
WHERE status = 'paid'
GROUP BY region
ORDER BY region NULLS LAST;
```

Ở nhóm `region=NULL`, `COUNT(*)=2` nhưng `COUNT(region)=0`. Nếu muốn số đơn theo từng vùng, `COUNT(*)` đúng với grain một hàng/đơn.

### 7.3. NULL trong GROUPING SETS còn có một ý nghĩa khác

Khi làm báo cáo subtotal/grand total bằng `ROLLUP` hoặc `GROUPING SETS`, PostgreSQL còn đưa `NULL` vào các cột **không tham gia cấp tổng hợp đó**. Lúc ấy một ô `NULL` có thể nghĩa là:

1. Vùng thật sự **chưa xác định** trong dữ liệu.
2. Vùng được **gộp lại** để tạo tổng theo tenant.

Hai trường hợp cần phân biệt bằng hàm **`GROUPING()`**, sẽ học ở phần sau. Chỉ dùng `COALESCE(region,'Tất cả')` không đủ để phân biệt.

## 8. FILTER: nhiều chỉ tiêu có điều kiện trong cùng nhóm

Giả sử báo cáo cần **một hàng cho mỗi tenant** với số đơn theo trạng thái và tiền của đơn đã thanh toán.

Cách dễ đọc trong PostgreSQL là dùng `FILTER (WHERE ...)` cho từng aggregate:

```sql
SELECT
    tenant_id,
    COUNT(*) AS all_orders,
    COUNT(*) FILTER (WHERE status = 'paid') AS paid_orders,
    COUNT(*) FILTER (WHERE status = 'pending') AS pending_orders,
    COUNT(*) FILTER (WHERE status = 'cancelled') AS cancelled_orders,
    COALESCE(
        SUM(total_amount) FILTER (WHERE status = 'paid'),
        0
    ) AS paid_amount
FROM agg_lab.orders
GROUP BY tenant_id
ORDER BY tenant_id;
```

Kết quả dự kiến:

| tenant_id | all_orders | paid_orders | pending_orders | cancelled_orders | paid_amount |
|---:|---:|---:|---:|---:|---:|
| 10 | 7 | 5 | 1 | 1 | 940 |
| 20 | 5 | 4 | 1 | 0 | 870 |

`FILTER` có ưu điểm: mỗi hàm tổng hợp ghi rõ **tập hàng mà nó tính trên đó**.

### 8.1. FILTER khác WHERE

Nếu viết:

```sql
SELECT
    tenant_id,
    COUNT(*) AS paid_orders,
    SUM(total_amount) AS paid_amount
FROM agg_lab.orders
WHERE status = 'paid'
GROUP BY tenant_id;
```

thì các hàng `pending` và `cancelled` bị loại khỏi **toàn bộ** phép tổng hợp.

Nhưng với `COUNT(*) FILTER (WHERE status = 'paid')`, các hàng vẫn nằm trong tập đầu vào của nhóm; chỉ **hàm cụ thể** bỏ qua những hàng không đạt điều kiện. Nhờ vậy có thể tính cùng lúc `paid_orders`, `pending_orders` và `all_orders`.

### 8.2. FILTER kết hợp DISTINCT

```sql
SELECT
    tenant_id,
    COUNT(DISTINCT customer_id)
        FILTER (WHERE status = 'paid') AS paying_customers,
    COUNT(DISTINCT customer_id)
        FILTER (WHERE status = 'pending') AS pending_customers
FROM agg_lab.orders
GROUP BY tenant_id
ORDER BY tenant_id;
```

Tập khách của hai trạng thái **có thể chồng nhau**. Do đó, không nên cộng hai số distinct để suy ra tổng số khách duy nhất của tenant.

### 8.3. CASE WHEN là một cách tương đương cho nhiều phép đếm

Trên các hệ thống SQL khác, có thể gặp:

```sql
SELECT
    tenant_id,
    SUM(CASE WHEN status = 'paid' THEN 1 ELSE 0 END)
        AS paid_orders,
    SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END)
        AS pending_orders
FROM agg_lab.orders
GROUP BY tenant_id;
```

Với dữ liệu có hàng và điều kiện đơn giản, cách trên cho cùng số đếm như `COUNT(*) FILTER`. Tuy nhiên:

- `COUNT(*) FILTER` diễn đạt trực tiếp “đếm số hàng thỏa điều kiện”.
- `SUM(CASE ... ELSE 0 END)` là phép cộng số; cần xét hành vi khi không có hàng đầu vào.
- Với việc tổng hợp tiền, `SUM(CASE WHEN ... THEN total_amount ELSE 0 END)` có thể tạo 0 trong trường hợp không có đơn thuộc trạng thái đó **nếu nhóm có hàng từ trạng thái khác**. `SUM(...) FILTER` có thể trả NULL khi không có hàng đạt điều kiện, nên cân nhắc `COALESCE`.

Đừng chọn cách viết vì cảm giác nhanh hơn; ưu tiên rõ nghĩa rồi đo kế hoạch nếu workload có vấn đề.

## 9. Tổng hợp theo ngày, tháng và múi giờ

Thường phải chọn **mức thời gian** trước khi viết `GROUP BY`: giờ, ngày, tuần, tháng, quý hay năm?

### 9.1. Nhóm theo ngày địa phương

Vì `created_at` là `TIMESTAMPTZ`, nếu muốn báo cáo theo ngày tại Việt Nam:

```sql
SELECT
    (created_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
        AS local_order_date,
    COUNT(*) AS paid_orders,
    SUM(total_amount) AS paid_amount
FROM agg_lab.orders
WHERE status = 'paid'
GROUP BY
    (created_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
ORDER BY local_order_date;
```

`AT TIME ZONE 'Asia/Ho_Chi_Minh'` chuyển thời điểm `TIMESTAMPTZ` thành timestamp theo đồng hồ địa phương; ép sang `date` lấy ngày tương ứng.

Không viết `created_at::date` trong mọi hệ thống rồi mặc định đó là ngày Việt Nam: kết quả ép kiểu `TIMESTAMPTZ` phụ thuộc timezone của phiên. Nếu tenant ở nhiều múi giờ, cần chính sách rõ cho báo cáo tổng hợp.

### 9.2. Nhóm theo tháng

```sql
SELECT
    date_trunc(
        'month',
        created_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
    ) AS month_local,
    COUNT(*) AS paid_orders,
    SUM(total_amount) AS paid_amount
FROM agg_lab.orders
WHERE status = 'paid'
GROUP BY
    date_trunc(
        'month',
        created_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
    )
ORDER BY month_local;
```

Kết quả theo dữ liệu lab:

| month_local | paid_orders | paid_amount |
|---|---:|---:|
| 2026-01-01 00:00:00 | 4 | 1040 |
| 2026-02-01 00:00:00 | 3 | 290 |
| 2026-03-01 00:00:00 | 2 | 480 |

`date_trunc('month', ...)` đưa các thời điểm cùng tháng về đầu tháng theo thời điểm/đồng hồ được chọn. Trong ví dụ, kết quả là `timestamp without time zone` sau `AT TIME ZONE`; nó là **nhãn tháng địa phương**, không phải một `TIMESTAMPTZ` mang timezone riêng.

### 9.3. Mỗi tenant–tháng một hàng

```sql
SELECT
    tenant_id,
    date_trunc(
        'month',
        created_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
    ) AS month_local,
    COUNT(*) AS paid_orders,
    SUM(total_amount) AS paid_amount
FROM agg_lab.orders
WHERE status = 'paid'
GROUP BY tenant_id, month_local
ORDER BY tenant_id, month_local;
```

PostgreSQL hỗ trợ dùng alias được định nghĩa trong SELECT ở `GROUP BY` trong những trường hợp phù hợp. Tuy nhiên, nếu tên alias trùng tên cột đầu vào, quy tắc giải quyết tên có thể gây bất ngờ; khi muốn rõ ràng, lặp lại biểu thức hoặc dùng CTE để đặt tên bucket.

### 9.4. Dùng CTE để đặt tên mức thời gian

```sql
WITH paid_orders AS (
    SELECT
        tenant_id,
        total_amount,
        date_trunc(
            'month',
            created_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
        ) AS month_local
    FROM agg_lab.orders
    WHERE status = 'paid'
)
SELECT
    tenant_id,
    month_local,
    COUNT(*) AS paid_orders,
    SUM(total_amount) AS paid_amount
FROM paid_orders
GROUP BY tenant_id, month_local
ORDER BY tenant_id, month_local;
```

Lợi ích của CTE ở đây chủ yếu là **đọc dễ và tránh lặp biểu thức**. PostgreSQL hiện đại có thể tối ưu một số CTE như phần của truy vấn; không mặc định mọi CTE đều bắt buộc materialize hoặc chắc chắn chậm hơn.

### 9.5. Đếm theo tháng và lọc khoảng thời gian

Với báo cáo “ba tháng đầu năm 2026”, bộ lọc nên dùng **khoảng nửa mở**:

```sql
SELECT
    date_trunc(
        'month',
        created_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
    ) AS month_local,
    COUNT(*) AS paid_orders,
    SUM(total_amount) AS paid_amount
FROM agg_lab.orders
WHERE status = 'paid'
  AND created_at >= TIMESTAMPTZ '2026-01-01 00:00:00+07'
  AND created_at <  TIMESTAMPTZ '2026-04-01 00:00:00+07'
GROUP BY month_local
ORDER BY month_local;
```

Dùng `>=` mốc đầu và `<` mốc sau giúp tránh vấn đề “23:59:59.999...” khi timestamp có độ chính xác cao. Điều kiện so sánh trực tiếp trên `created_at` cũng thường dễ được hỗ trợ bởi index hơn việc bọc cột trong một phép biến đổi ở `WHERE`, tùy kế hoạch.

### 9.6. Ngày tháng không đồng nghĩa “mỗi tháng có dữ liệu”

`GROUP BY` chỉ tạo nhóm cho các tháng **thực sự có hàng đầu vào**, không tự tạo tháng trống.

Nếu báo cáo cần hiển thị tháng 01–12 và 0 khi không có đơn, có thể tạo một calendar bằng `generate_series` rồi `LEFT JOIN` với kết quả đã tổng hợp:

```sql
WITH months AS (
    SELECT generate_series(
        DATE '2026-01-01',
        DATE '2026-12-01',
        INTERVAL '1 month'
    )::date AS month_start
),
monthly AS (
    SELECT
        date_trunc(
            'month',
            created_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
        )::date AS month_start,
        SUM(total_amount) AS paid_amount
    FROM agg_lab.orders
    WHERE status = 'paid'
    GROUP BY 1
)
SELECT
    m.month_start,
    COALESCE(a.paid_amount, 0) AS paid_amount
FROM months AS m
LEFT JOIN monthly AS a
    ON a.month_start = m.month_start
ORDER BY m.month_start;
```

Ở đây **calendar có 12 hàng** làm bảng bên trái, nên các tháng không có đơn vẫn xuất hiện. `COALESCE` biến thiếu tổng thành 0 theo quy tắc hiển thị của báo cáo. Không dùng `INNER JOIN` nếu muốn giữ tháng trống.

## 10. GROUP BY sau JOIN: nguyên nhân thường gặp của tổng bị nhân đôi

Đây là phần quan trọng nhất khi lựa chọn mức tổng hợp.

`orders` ở grain một đơn; `order_items` ở grain một dòng sản phẩm. Một đơn có nhiều item, nên:

```sql
SELECT
    o.order_id,
    o.total_amount,
    i.item_id,
    i.line_total
FROM agg_lab.orders AS o
JOIN agg_lab.order_items AS i
    ON i.order_id = o.order_id
WHERE o.order_id = 1
ORDER BY i.item_id;
```

Kết quả:

| order_id | total_amount | item_id | line_total |
|---:|---:|---:|---:|
| 1 | 300 | 1 | 200 |
| 1 | 300 | 2 | 100 |

Trong kết quả JOIN, `orders.total_amount=300` xuất hiện **hai lần** vì đơn 1 có hai item. Đây là **nhân bản hàng theo quan hệ một-nhiều**, không phải hai đơn riêng biệt.

### 10.1. Câu tổng hợp sai sau JOIN

```sql
SELECT
    o.tenant_id,
    COUNT(*) AS joined_rows,
    SUM(o.total_amount) AS wrong_order_amount
FROM agg_lab.orders AS o
JOIN agg_lab.order_items AS i
    ON i.order_id = o.order_id
WHERE o.status = 'paid'
GROUP BY o.tenant_id
ORDER BY o.tenant_id;
```

Vì mỗi đơn có thể xuất hiện nhiều lần:

- `COUNT(*)` đếm **số dòng sau JOIN**, không còn là số đơn.
- `SUM(o.total_amount)` cộng **số tiền của mỗi đơn nhiều lần**, có thể tăng gấp đôi/gấp ba.

Với dữ liệu lab:

| tenant_id | joined_rows | wrong_order_amount |
|---:|---:|---:|
| 10 | 7 | 1490 |
| 20 | 6 | 1500 |

Trong khi doanh thu đúng của `orders` theo tenant là **940** và **870**. Những số sai vẫn “có vẻ hợp lý” nếu người xem không biết mức chi tiết của kết quả JOIN.

### 10.2. COUNT(DISTINCT order_id) chỉ sửa được phép đếm

```sql
SELECT
    o.tenant_id,
    COUNT(DISTINCT o.order_id) AS paid_orders,
    SUM(o.total_amount) AS wrong_amount_still
FROM agg_lab.orders AS o
JOIN agg_lab.order_items AS i
    ON i.order_id = o.order_id
WHERE o.status = 'paid'
GROUP BY o.tenant_id
ORDER BY o.tenant_id;
```

`COUNT(DISTINCT o.order_id)` có thể đưa **số đơn** trở về đúng, nhưng `SUM(o.total_amount)` **vẫn bị nhân**. Đừng sửa một truy vấn sai grain chỉ bằng cách thêm `DISTINCT` vào một phép đếm.

Đặc biệt, `SUM(DISTINCT o.total_amount)` cũng **không** phải giải pháp chung: nếu hai đơn độc lập có cùng số tiền, nó sẽ chỉ cộng giá trị tiền đó một lần, làm thiếu doanh thu.

### 10.3. Cách 1: tổng hợp từ bảng ở đúng grain

Nếu chỉ cần doanh thu theo đơn:

```sql
SELECT
    tenant_id,
    COUNT(*) AS paid_orders,
    SUM(total_amount) AS paid_amount
FROM agg_lab.orders
WHERE status = 'paid'
GROUP BY tenant_id
ORDER BY tenant_id;
```

Không JOIN `order_items` khi không cần dữ liệu dòng sản phẩm. Đây là cách đơn giản và tránh fanout nhất.

### 10.4. Cách 2: tổng hợp item lên grain một đơn trước JOIN

Nếu cần **cả tiền theo đơn và số lượng sản phẩm**, hãy tổng hợp bảng item về **một hàng/order_id** trước:

```sql
WITH item_per_order AS (
    SELECT
        order_id,
        COUNT(*) AS item_lines,
        SUM(quantity) AS units,
        SUM(line_total) AS item_amount
    FROM agg_lab.order_items
    GROUP BY order_id
)
SELECT
    o.tenant_id,
    COUNT(*) AS paid_orders,
    SUM(o.total_amount) AS paid_order_amount,
    SUM(COALESCE(i.units, 0)) AS units,
    SUM(COALESCE(i.item_amount, 0)) AS item_amount
FROM agg_lab.orders AS o
LEFT JOIN item_per_order AS i
    ON i.order_id = o.order_id
WHERE o.status = 'paid'
GROUP BY o.tenant_id
ORDER BY o.tenant_id;
```

Vì `item_per_order` có tối đa **một hàng cho mỗi order_id**, JOIN không nhân bản mỗi đơn. Trong dữ liệu lab, tổng tiền item và tiền order trùng nhau theo tenant. Ở production có thể khác nếu tổng đơn bao gồm phí, thuế, coupon, hoàn tiền hoặc làm tròn; đừng xem hai đại lượng đó luôn phải bằng nhau.

### 10.5. Cách 3: tổng hợp riêng rồi JOIN ở grain kết quả

Nếu muốn tổng số đơn và số item theo tenant, có thể tách thành hai báo cáo:

```sql
WITH order_totals AS (
    SELECT
        tenant_id,
        COUNT(*) AS paid_orders,
        SUM(total_amount) AS paid_amount
    FROM agg_lab.orders
    WHERE status = 'paid'
    GROUP BY tenant_id
),
item_totals AS (
    SELECT
        o.tenant_id,
        SUM(i.quantity) AS units
    FROM agg_lab.orders AS o
    JOIN agg_lab.order_items AS i
        ON i.order_id = o.order_id
    WHERE o.status = 'paid'
    GROUP BY o.tenant_id
)
SELECT
    a.tenant_id,
    a.paid_orders,
    a.paid_amount,
    COALESCE(b.units, 0) AS units
FROM order_totals AS a
LEFT JOIN item_totals AS b
    ON b.tenant_id = a.tenant_id
ORDER BY a.tenant_id;
```

Cả hai CTE cuối đều có **một hàng/tenant**, nên kết hợp ở cùng grain sẽ không nhân số đo. Phương án này cũng phù hợp khi mỗi chỉ tiêu đến từ một bảng fact hoặc một pipeline khác nhau.

### 10.6. Hai bảng con một-nhiều tạo “fanout nhân fanout”

Giả sử mỗi đơn có nhiều `order_items` **và** nhiều bản ghi `payments`. Nếu JOIN cả hai bảng con với `orders` rồi `SUM` trực tiếp, mỗi item có thể bị ghép với mọi payment của cùng đơn, tạo số hàng xấp xỉ:

```text
số dòng item của đơn × số dòng payment của đơn
```

Đây là trường hợp nghiêm trọng hơn JOIN một bảng con. Cách an toàn là tổng hợp **item về một hàng/order_id**, payment về **một hàng/order_id**, rồi JOIN các kết quả đã giảm grain với bảng orders.

Không mặc định `DISTINCT` ở ngoài SELECT sẽ sửa các phép `SUM` đã bị nhân: nếu số đo bị cộng trước đó, dữ liệu sai đã hình thành.

### 10.7. LEFT JOIN và vị trí lọc bảng bên phải

Muốn biết số dòng item loại `device` của từng đơn, kể cả đơn **không có device**, cần giữ mọi đơn:

```sql
SELECT
    o.order_id,
    COUNT(i.item_id) AS device_lines
FROM agg_lab.orders AS o
LEFT JOIN agg_lab.order_items AS i
    ON i.order_id = o.order_id
   AND i.category = 'device'
WHERE o.status = 'paid'
GROUP BY o.order_id
ORDER BY o.order_id;
```

Đặt điều kiện `i.category='device'` trong `ON` giúp các đơn không có device vẫn được giữ, `COUNT(i.item_id)=0`.

Nếu chuyển điều kiện đó xuống:

```sql
-- KHÁC NGHĨA nếu muốn giữ các đơn không có device:
SELECT o.order_id, COUNT(i.item_id)
FROM agg_lab.orders AS o
LEFT JOIN agg_lab.order_items AS i
    ON i.order_id = o.order_id
WHERE o.status = 'paid'
  AND i.category = 'device'
GROUP BY o.order_id;
```

thì các đơn không có item device bị `WHERE` loại bỏ, khiến phép LEFT JOIN thực tế mất tác dụng giữ hàng bên trái cho mục tiêu này.

## 11. Từ nhóm đơn giản đến báo cáo nhiều cấp

Một báo cáo quản trị thường cần đồng thời:

1. Doanh thu **từng tenant–vùng**.
2. Tổng doanh thu **mỗi tenant**.
3. **Tổng toàn bộ** các tenant.

Nếu chạy ba truy vấn riêng rồi `UNION ALL`, vẫn có thể đúng. Nhưng PostgreSQL có những cấu trúc tổng hợp đa cấp được thiết kế cho trường hợp này: **`GROUPING SETS`**, **`ROLLUP`** và **`CUBE`**.

Để hiểu dễ, hình dung dữ liệu paid có hai chiều:

```text
tenant_id                  region
   10                  north / south / NULL
   20                  north / south / NULL
```

Mỗi **mức tổng hợp** tương ứng với việc giữ lại hoặc bỏ bớt một chiều trong khóa nhóm.

| Mức | Khóa nhóm | Ví dụ câu hỏi |
|---|---|---|
| Chi tiết | `(tenant_id, region)` | Tenant 10 ở south có bao nhiêu tiền? |
| Tổng theo tenant | `(tenant_id)` | Tenant 10 tổng bao nhiêu tiền? |
| Tổng theo region | `(region)` | Toàn hệ thống ở north bao nhiêu tiền? |
| Tổng toàn hệ thống | `()` | Tất cả paid tổng bao nhiêu? |

`()` là **grouping set rỗng**, biểu diễn mức tổng hợp không phân chia theo cột nào.

## 12. GROUPING SETS: chọn chính xác các mức muốn có

Cú pháp:

```sql
SELECT
    tenant_id,
    region,
    COUNT(*) AS paid_orders,
    SUM(total_amount) AS paid_amount
FROM agg_lab.orders
WHERE status = 'paid'
GROUP BY GROUPING SETS (
    (tenant_id, region),
    (tenant_id),
    ()
);
```

Truy vấn yêu cầu PostgreSQL tạo:

- Các nhóm `(tenant_id, region)`.
- Các nhóm chỉ theo `tenant_id`.
- Một nhóm toàn cục `()`.

Ở mức tổng theo tenant, cột `region` trong kết quả được hiển thị là `NULL` vì nó **không còn là chiều phân nhóm**. Ở mức toàn hệ thống, cả `tenant_id` lẫn `region` đều là `NULL`.

### 12.1. Vì sao không chỉ nhìn NULL để nhận subtotal?

Dữ liệu gốc có các đơn `region IS NULL`. Do đó, một hàng:

```text
tenant_id = 10, region = NULL
```

có thể là:

- **Nhóm dữ liệu thật** của tenant 10 có region chưa biết, doanh thu 90.
- **Subtotal của tenant 10**, gộp tất cả region, doanh thu 940.

Hai hàng có cách hiển thị cặp khóa **giống nhau** nhưng ý nghĩa **khác nhau**. Dựa riêng vào `region IS NULL` để quyết định nhãn “Tất cả vùng” sẽ sai.

### 12.2. GROUPING() phân biệt NULL thật và NULL do tổng hợp

PostgreSQL cung cấp hàm `GROUPING(expression, ...)` để đánh dấu những chiều bị loại khỏi grouping set hiện tại:

```sql
SELECT
    tenant_id,
    region,
    GROUPING(tenant_id) AS tenant_is_rolled_up,
    GROUPING(region) AS region_is_rolled_up,
    GROUPING(tenant_id, region) AS grouping_mask,
    COUNT(*) AS paid_orders,
    SUM(total_amount) AS paid_amount
FROM agg_lab.orders
WHERE status = 'paid'
GROUP BY GROUPING SETS (
    (tenant_id, region),
    (tenant_id),
    ()
)
ORDER BY grouping_mask, tenant_id NULLS LAST, region NULLS LAST;
```

Ý nghĩa:

- `GROUPING(region)=0`: `region` **tham gia** khóa nhóm; nếu kết quả region là NULL thì đó là **NULL thật của dữ liệu**.
- `GROUPING(region)=1`: `region` **bị gộp bỏ** ở mức subtotal hoặc grand total.
- `GROUPING(tenant_id, region)` là **bitmask**: với thứ tự hai đối số này, bit của `region` có trọng số 1, bit của `tenant_id` có trọng số 2.

| Grouping set | tenant_is_rolled_up | region_is_rolled_up | grouping_mask |
|---|---:|---:|---:|
| `(tenant_id, region)` | 0 | 0 | 0 |
| `(tenant_id)` | 0 | 1 | 1 |
| `()` | 1 | 1 | 3 |

Không có nhóm `(region)` trong truy vấn trên, nên mask 2 không xuất hiện.

### 12.3. Đặt nhãn mức tổng hợp chính xác

```sql
SELECT
    CASE
        WHEN GROUPING(tenant_id) = 1
            THEN 'Tất cả tenant'
        ELSE tenant_id::text
    END AS tenant_label,
    CASE
        WHEN GROUPING(region) = 1
            THEN 'Tất cả vùng'
        WHEN region IS NULL
            THEN 'Chưa rõ vùng'
        ELSE region
    END AS region_label,
    COUNT(*) AS paid_orders,
    SUM(total_amount) AS paid_amount
FROM agg_lab.orders
WHERE status = 'paid'
GROUP BY GROUPING SETS (
    (tenant_id, region),
    (tenant_id),
    ()
)
ORDER BY
    GROUPING(tenant_id, region),
    tenant_id NULLS LAST,
    region NULLS LAST;
```

Ở đây `GROUPING()` được dùng để quyết định nhãn, nên **subtotal không bị nhầm với region NULL thật**. Nếu xuất báo cáo cho frontend, còn nên trả một trường `level` hoặc `grouping_mask` có cấu trúc để frontend không phải suy ý nghĩa từ chuỗi nhãn.

### 12.4. Mức tổng hợp không mong muốn thì đừng tạo

Nếu báo cáo chỉ muốn tổng theo tenant và tổng toàn cục, không cần chi tiết vùng:

```sql
SELECT
    tenant_id,
    GROUPING(tenant_id) AS is_grand_total,
    COUNT(*) AS paid_orders,
    SUM(total_amount) AS paid_amount
FROM agg_lab.orders
WHERE status = 'paid'
GROUP BY GROUPING SETS ((tenant_id), ())
ORDER BY is_grand_total, tenant_id NULLS LAST;
```

`GROUPING SETS` rất phù hợp khi người thiết kế biết rõ **những mức cần có**. Không cần tạo mọi tổ hợp chiều phân tích nếu báo cáo chỉ sử dụng hai hoặc ba mức.

## 13. ROLLUP: tổng hợp phân cấp

`ROLLUP(tenant_id, region)` là cách viết gọn cho các grouping set theo thứ tự phân cấp:

```sql
GROUP BY ROLLUP (tenant_id, region)
```

tương đương về nhóm với:

```sql
GROUP BY GROUPING SETS (
    (tenant_id, region),
    (tenant_id),
    ()
)
```

Tức là:

```text
tenant + region   -> các hàng chi tiết
tenant            -> subtotal cho tenant
()                -> grand total
```

Ví dụ chạy được:

```sql
SELECT
    tenant_id,
    region,
    GROUPING(tenant_id, region) AS group_level,
    COUNT(*) AS paid_orders,
    SUM(total_amount) AS paid_amount
FROM agg_lab.orders
WHERE status = 'paid'
GROUP BY ROLLUP (tenant_id, region)
ORDER BY group_level, tenant_id NULLS LAST, region NULLS LAST;
```

### 13.1. Thứ tự cột trong ROLLUP quan trọng

So sánh:

```sql
GROUP BY ROLLUP (tenant_id, region)
```

và:

```sql
GROUP BY ROLLUP (region, tenant_id)
```

Trường hợp thứ nhất tạo subtotal **theo tenant**. Trường hợp thứ hai tạo subtotal **theo region**, bởi nhóm trung gian chỉ giữ biểu thức **đầu tiên** trong danh sách ROLLUP.

Nó không đơn giản là “sắp xếp tên cột khác nhau”; **mức subtotal thay đổi**.

### 13.2. ROLLUP ba chiều

Với `ROLLUP (tenant_id, region, channel)`:

```text
(tenant_id, region, channel)
(tenant_id, region)
(tenant_id)
()
```

Đây là phân cấp từ trái sang phải. Nếu muốn subtotal theo `channel` nhưng không theo `tenant_id`, `ROLLUP` đơn giản này không tạo ra; phải dùng `GROUPING SETS` hoặc `CUBE` phù hợp.

### 13.3. Khi nào ROLLUP phù hợp?

- Báo cáo có thứ bậc rõ: `năm → quý → tháng`.
- Báo cáo `tenant → region → channel` cùng các subtotal theo cấp cha.
- Dashboard cần các dòng “Tổng tenant” và “Tổng chung”.

Đừng dùng ROLLUP nếu muốn một tập mức không phân cấp; `GROUPING SETS` thường diễn đạt đúng yêu cầu hơn.

## 14. CUBE: tất cả tổ hợp chiều tổng hợp

`CUBE (tenant_id, region)` tạo **mọi tổ hợp** của hai chiều:

```text
(tenant_id, region)   -- chi tiết
(tenant_id)           -- subtotal tenant
(region)              -- subtotal region
()                    -- tổng chung
```

Truy vấn:

```sql
SELECT
    tenant_id,
    region,
    GROUPING(tenant_id, region) AS grouping_mask,
    COUNT(*) AS paid_orders,
    SUM(total_amount) AS paid_amount
FROM agg_lab.orders
WHERE status = 'paid'
GROUP BY CUBE (tenant_id, region)
ORDER BY grouping_mask, tenant_id NULLS LAST, region NULLS LAST;
```

CUBE đặc biệt hữu ích trong báo cáo phân tích đa chiều, khi người dùng muốn cả **theo tenant**, **theo region** và **theo tenant–region**.

### 14.1. CUBE tăng số grouping sets theo số chiều

Với `n` biểu thức phân tích độc lập, `CUBE` tạo tới **`2^n` grouping sets**:

| Số chiều | Số grouping sets |
|---:|---:|
| 1 | 2 |
| 2 | 4 |
| 3 | 8 |
| 4 | 16 |
| 6 | 64 |

Với nhiều chiều có cardinality lớn, một CUBE tổng quát có thể sinh nhiều nhóm, tiêu tốn bộ nhớ và làm kết quả khó hiểu. Không viết `CUBE` vì “tổng hợp nhiều hơn luôn tốt hơn”; chỉ tạo các cấp thật sự cần.

### 14.2. GROUPING SETS, ROLLUP, CUBE nên chọn thế nào?

| Nhu cầu | Cú pháp phù hợp |
|---|---|
| Chỉ tổng theo tenant | `GROUP BY tenant_id` |
| Chi tiết tenant–region | `GROUP BY tenant_id, region` |
| Chi tiết + tổng tenant + tổng chung | `ROLLUP(tenant_id, region)` |
| Chi tiết + tổng tenant + tổng region + tổng chung | `CUBE(tenant_id, region)` |
| Chỉ một số cấp tùy chọn, không nhất thiết phân cấp | `GROUPING SETS (...)` |

**Chọn cú pháp theo cấu trúc báo cáo**, không theo việc cú pháp nào trông “nâng cao” hơn.

## 15. GROUP BY và DISTINCT không giải quyết cùng một câu hỏi

`DISTINCT` dùng để loại các hàng kết quả trùng nhau; `GROUP BY` dùng để định nghĩa nhóm để tính aggregate, dù `GROUP BY` **không có aggregate** đôi khi cho tập giá trị tương tự `SELECT DISTINCT`.

### 15.1. Liệt kê vùng khác nhau

```sql
SELECT DISTINCT region
FROM agg_lab.orders
ORDER BY region NULLS LAST;
```

Tương tự về tập kết quả:

```sql
SELECT region
FROM agg_lab.orders
GROUP BY region
ORDER BY region NULLS LAST;
```

Trong trường hợp chỉ muốn **danh sách giá trị khác nhau**, `DISTINCT` thường rõ nghĩa hơn. Nếu muốn **đếm đơn theo vùng**, dùng `GROUP BY region` cùng `COUNT(*)`.

### 15.2. Đừng dùng SELECT DISTINCT để chữa JOIN nhân hàng

Nếu JOIN nhân một đơn thành hai dòng, `SELECT DISTINCT o.order_id` chỉ làm danh sách ID còn một dòng mỗi đơn. Nó **không tự sửa** phép `SUM(o.total_amount)` đã cộng nhiều lần trong cùng query aggregate.

Để tính doanh thu đúng, phải giữ grain phù hợp **trước khi cộng** hoặc tổng hợp riêng từng fact.

### 15.3. DISTINCT trong COUNT không cộng được giữa các nhóm

Ví dụ một khách mua đơn ở tháng 1 và tháng 3. Khách đó được đếm **một lần trong mỗi tháng** ở báo cáo:

```sql
SELECT
    date_trunc(
        'month',
        created_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
    ) AS month_local,
    COUNT(DISTINCT customer_id) AS unique_customers
FROM agg_lab.orders
WHERE status = 'paid'
GROUP BY month_local
ORDER BY month_local;
```

**Cộng các unique_customers của từng tháng** không nhất thiết bằng số khách duy nhất của cả quý, vì cùng khách có thể quay lại nhiều tháng.

Đây là ví dụ về chỉ tiêu **không cộng dồn trực tiếp được** (*non-additive* hoặc *distinct measure*). Khi chọn mức tổng hợp mới, phải tính lại `COUNT(DISTINCT ...)` trên tập dữ liệu tương ứng, hoặc sử dụng thiết kế distinct-count có phương pháp phù hợp.

## 16. GROUP BY so với window functions

`GROUP BY` **rút nhiều hàng thành một hàng trên mỗi nhóm**. Window function với `OVER (PARTITION BY ...)` thường **giữ lại các hàng chi tiết** rồi gắn số liệu tổng hợp tương ứng lên từng hàng.

### 16.1. Một hàng mỗi tenant bằng GROUP BY

```sql
SELECT
    tenant_id,
    SUM(total_amount) AS tenant_paid_amount
FROM agg_lab.orders
WHERE status = 'paid'
GROUP BY tenant_id
ORDER BY tenant_id;
```

Kết quả có **hai hàng**, tenant 10 và 20.

### 16.2. Mỗi đơn vẫn giữ nguyên, kèm tổng tenant

```sql
SELECT
    order_id,
    tenant_id,
    total_amount,
    SUM(total_amount) OVER (
        PARTITION BY tenant_id
    ) AS tenant_paid_amount
FROM agg_lab.orders
WHERE status = 'paid'
ORDER BY tenant_id, order_id;
```

Kết quả có **chín hàng**, mỗi đơn paid vẫn hiện diện; mỗi đơn tenant 10 đều kèm tổng 940, tenant 20 kèm tổng 870.

Chọn:

- `GROUP BY` nếu cần báo cáo **mỗi tenant một hàng**.
- Window function nếu cần **mỗi đơn một hàng** nhưng kèm chỉ tiêu của tenant.

### 16.3. Đánh số thứ hạng trong từng nhóm

```sql
SELECT
    order_id,
    tenant_id,
    total_amount,
    ROW_NUMBER() OVER (
        PARTITION BY tenant_id
        ORDER BY total_amount DESC, order_id DESC
    ) AS rank_in_tenant
FROM agg_lab.orders
WHERE status = 'paid'
ORDER BY tenant_id, rank_in_tenant;
```

Đây là bài toán chọn **top N đơn trong từng tenant**, không phải một phép tổng tiền đơn thuần. Nếu muốn chỉ top 2:

```sql
WITH ranked AS (
    SELECT
        order_id,
        tenant_id,
        total_amount,
        ROW_NUMBER() OVER (
            PARTITION BY tenant_id
            ORDER BY total_amount DESC, order_id DESC
        ) AS rn
    FROM agg_lab.orders
    WHERE status = 'paid'
)
SELECT order_id, tenant_id, total_amount, rn
FROM ranked
WHERE rn <= 2
ORDER BY tenant_id, rn;
```

Không dùng `GROUP BY tenant_id` rồi cố chọn `order_id` lớn nhất nếu mục tiêu là **top đơn theo tiền**. Một aggregate như `MAX(total_amount)` không tự trả lại toàn bộ hàng có giá trị cực đại.

## 17. Tổng hợp nhiều cấp và tính đúng của chỉ tiêu

### 17.1. SUM là cộng dồn được khi các nhóm không chồng nhau

Nếu mỗi đơn thuộc **đúng một tenant**, tổng doanh thu tenant 10 và 20 có thể cộng thành tổng doanh thu hệ thống:

```text
940 + 870 = 1810
```

Điều kiện quan trọng: mỗi đơn **được tính đúng một lần**, không bị nhân bản sau JOIN và tập các nhóm không chồng nhau.

Tuy nhiên, trong hệ thống dùng nhiều loại tiền tệ, không thể cộng hai tổng tiền khác đơn vị rồi gọi là một “doanh thu chung” nếu chưa có quy tắc quy đổi và thời điểm tỷ giá.

### 17.2. Trung bình của các trung bình thường sai

Trong lab:

- Tenant 10: **5 đơn**, trung bình **188.00**.
- Tenant 20: **4 đơn**, trung bình **217.50**.

Lấy trung bình đơn giản của hai giá trị:

```text
(188.00 + 217.50) / 2 = 202.75
```

**Không** bằng giá trị trung bình trên tất cả chín đơn:

```text
1810 / 9 = 201.111...
```

Để tổng hợp lại AOV từ nhóm, cần **tổng tiền và số đơn**:

```sql
WITH by_tenant AS (
    SELECT
        tenant_id,
        SUM(total_amount) AS amount,
        COUNT(*) AS order_count
    FROM agg_lab.orders
    WHERE status = 'paid'
    GROUP BY tenant_id
)
SELECT
    SUM(amount) AS all_amount,
    SUM(order_count) AS all_orders,
    ROUND(
        SUM(amount) / NULLIF(SUM(order_count), 0),
        2
    ) AS all_avg_order_value
FROM by_tenant;
```

`NULLIF(...,0)` bảo vệ phép chia cho 0. Số **201.11** là trung bình có trọng số theo số đơn, không phải trung bình hai tenant với trọng số bằng nhau.

### 17.3. Tỷ lệ cũng phải chọn mẫu số đúng

Tỷ lệ paid trên tổng số đơn theo tenant:

```sql
SELECT
    tenant_id,
    COUNT(*) AS total_orders,
    COUNT(*) FILTER (WHERE status = 'paid') AS paid_orders,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE status = 'paid')
        / NULLIF(COUNT(*), 0),
        2
    ) AS paid_rate_percent
FROM agg_lab.orders
GROUP BY tenant_id
ORDER BY tenant_id;
```

Vì `COUNT(*)` của mỗi nhóm đang tồn tại là dương, phép chia ở ví dụ có mẫu khác 0; `NULLIF` vẫn giúp câu lệnh dễ thích ứng khi thay đổi mô hình tổng hợp.

Trong báo cáo toàn hệ thống, **không lấy trung bình tỷ lệ các tenant** nếu bạn muốn tỷ lệ tính trên mọi đơn; phải dùng tổng số paid / tổng số đơn.

### 17.4. Cần phân biệt thời điểm tạo và thời điểm thanh toán

Truy vấn:

```sql
WHERE status = 'paid'
GROUP BY date_trunc('month', created_at ...)
```

trả doanh thu những đơn **hiện đang paid**, nhóm theo **tháng tạo đơn**. Nếu câu hỏi là “doanh thu được ghi nhận trong tháng thanh toán”, bảng cần có `paid_at` hoặc dữ liệu sự kiện thanh toán làm nguồn, rồi nhóm theo đúng thời điểm đó.

Đây là ví dụ điển hình: **SQL đúng cú pháp nhưng chọn sai cột thời gian dẫn đến sai định nghĩa kinh doanh**.

## 18. Tổng hợp trong môi trường nhiều tenant

Với dữ liệu multi-tenant, `GROUP BY tenant_id` thường là **mức báo cáo**, nhưng `WHERE tenant_id = :tenant` cũng là một phần của **phạm vi truy cập**.

Ví dụ dashboard chỉ cho tenant 10:

```sql
SELECT
    region,
    COUNT(*) AS paid_orders,
    SUM(total_amount) AS paid_amount
FROM agg_lab.orders
WHERE tenant_id = 10
  AND status = 'paid'
GROUP BY region
ORDER BY region NULLS LAST;
```

Không hiểu rằng “chỉ GROUP BY tenant_id” tự ngăn lộ dữ liệu tenant khác. Một query không có bộ lọc tenant đúng vẫn có thể tính và trả số liệu của tenant khác.

Trong hệ thống thực tế, kiểm soát phạm vi truy cập cần thiết kế ở tầng dịch vụ, SQL policy, role, **Row-Level Security (RLS)** nếu dùng, và các ranh giới hạ tầng phù hợp. `GROUP BY` không phải cơ chế authorization.

### 18.1. Thời gian/tiền tệ/vùng có thể là những chiều phân tích

Khi có nhiều tenant với múi giờ, tiền tệ hoặc danh mục sản phẩm khác nhau, một “tổng theo tháng” có thể không có ý nghĩa nếu:

- Tháng được tính theo timezone khác nhau.
- Tổng tiền gộp USD với VND.
- Một danh mục được đổi tên theo thời gian.
- `region` trong hai tenant có cùng tên nhưng thực chất chỉ vùng địa lý khác nhau.

Hãy xác định **các chiều cần nhóm** và cách chuẩn hóa chúng trước khi tổng hợp. Nếu muốn nhóm theo `currency_code`, thêm cột đó vào grain kết quả và xử lý chuyển đổi tiền tệ như một bước nghiệp vụ độc lập.

## 19. GROUP BY và giới hạn hiệu năng

`GROUP BY` trên bảng lớn có thể tiêu tốn CPU, RAM, I/O và thời gian. Cần hiểu các nhóm và cách PostgreSQL thực thi.

### 19.1. HashAggregate và GroupAggregate

Một truy vấn:

```sql
EXPLAIN
SELECT tenant_id, region, SUM(total_amount)
FROM agg_lab.orders
WHERE status = 'paid'
GROUP BY tenant_id, region;
```

có thể có các node kế hoạch như:

| Kế hoạch | Ý nghĩa khái quát |
|---|---|
| `HashAggregate` | Dùng cấu trúc hash để gom các khóa nhóm, tính aggregate |
| `GroupAggregate` | Tính aggregate theo những hàng đã được sắp thứ tự phù hợp |
| `Sort` | Sắp dữ liệu cho một chiến lược tổng hợp hoặc ORDER BY |
| `Partial Aggregate` / `Finalize Aggregate` | Một số aggregate có thể thực hiện song song theo phần rồi kết hợp |

Không nên khẳng định PostgreSQL **luôn** dùng HashAggregate hay GroupAggregate cho một query: planner chọn dựa vào thống kê, số nhóm dự kiến, index, `work_mem`, kích thước đầu vào, hỗ trợ song song và phiên bản.

### 19.2. Cardinality của khóa nhóm

Nhóm theo `status` chỉ có vài nhóm nếu dữ liệu chỉ có ba trạng thái. Nhóm theo `customer_id` có thể có hàng triệu nhóm. Nhóm theo `order_id` là một nhóm cho mỗi đơn nên gần như không giảm số hàng.

Khi số nhóm lớn:

- Hash table có thể tiêu tốn đáng kể bộ nhớ.
- Sort/aggregate có thể cần ghi đĩa nếu không đủ bộ nhớ.
- Tập kết quả vẫn lớn, gây chi phí truyền dữ liệu đến client.
- Báo cáo có thể cần bước lọc/giới hạn hoặc tiền tổng hợp theo nhu cầu thật.

**Đừng thêm nhiều chiều vào GROUP BY nếu dashboard chỉ cần tổng cao cấp hơn.** Số chiều và số giá trị khác nhau có thể khiến kết quả tăng rất nhanh.

### 19.3. WHERE nên giảm dữ liệu trước khi GROUP BY

```sql
SELECT tenant_id, SUM(total_amount)
FROM agg_lab.orders
WHERE status = 'paid'
  AND created_at >= TIMESTAMPTZ '2026-01-01 00:00:00+07'
  AND created_at <  TIMESTAMPTZ '2026-04-01 00:00:00+07'
GROUP BY tenant_id;
```

Khoảng thời gian và trạng thái được xác định trước khi nhóm có thể giảm dữ liệu phải xử lý, nếu các điều kiện phản ánh đúng nghiệp vụ. PostgreSQL có thể tận dụng index/partition pruning tùy thiết kế bảng.

### 19.4. Index không luôn làm GROUP BY nhanh hơn

Ví dụ:

```sql
CREATE INDEX orders_tenant_status_date_idx
ON agg_lab.orders (tenant_id, status, created_at);
```

Index có thể phù hợp với một số truy vấn lọc tenant, trạng thái, thời gian. Nhưng với thống kê trên phần lớn bảng, PostgreSQL có thể chọn sequential scan rồi HashAggregate thay vì đọc nhiều index entry; đó có thể là lựa chọn tốt.

Nếu báo cáo thường chỉ tính đơn paid, đôi khi một **partial index** theo điều kiện phù hợp có ích:

```sql
CREATE INDEX orders_paid_tenant_date_idx
ON agg_lab.orders (tenant_id, created_at)
WHERE status = 'paid';
```

Index không miễn phí: cần thêm dung lượng và chi phí duy trì khi `INSERT`/`UPDATE`. Không tạo mọi index gợi ý trong bài trên production trước khi đo workload thật.

### 19.5. EXPLAIN ANALYZE và BUFFERS

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    tenant_id,
    region,
    COUNT(*) AS paid_orders,
    SUM(total_amount) AS paid_amount
FROM agg_lab.orders
WHERE status = 'paid'
GROUP BY tenant_id, region;
```

`EXPLAIN (ANALYZE, BUFFERS)` **thực thi truy vấn** để đo runtime và buffer activity. Với SELECT đọc trong lab, đây là phép thử phù hợp; với câu lệnh ghi ở hệ thống thật, việc dùng `ANALYZE` cần kiểm soát vì nó có thể thực thi thay đổi.

Các khía cạnh nên quan sát:

- Số hàng thực tế và ước lượng tại các node.
- Số nhóm đầu ra của aggregate.
- Sort method và khả năng dùng đĩa nếu có.
- Memory usage/batches của hash aggregate nếu planner hiển thị.
- Buffer hits/reads và chi phí scan bảng.
- Sự khác nhau giữa truy vấn có/không có bộ lọc phù hợp.

### 19.6. work_mem và số truy vấn đồng thời

Các thao tác sort/hash có thể dùng bộ nhớ làm việc liên quan đến `work_mem` và một số tham số khác tùy loại node và phiên bản. Không suy luận “tăng `work_mem` gấp 10 thì query chắc chắn nhanh gấp 10” hoặc “mỗi connection chỉ dùng một lần `work_mem`”.

Một truy vấn có thể có nhiều node cần bộ nhớ; nhiều query chạy đồng thời có thể làm tổng sử dụng RAM tăng mạnh. Thay đổi tham số cấp server cần đánh giá workload và concurrency, không phải bước mặc định khi `GROUP BY` chậm.

## 20. Tổng hợp trước, lưu kết quả và materialized view

Nếu dashboard chạy đi chạy lại cùng một báo cáo đắt đỏ trên dữ liệu lớn, có thể cân nhắc **pre-aggregation**.

### 20.1. Tạo materialized view theo tenant–tháng

Ví dụ minh họa:

```sql
CREATE MATERIALIZED VIEW agg_lab.monthly_paid_summary AS
SELECT
    tenant_id,
    date_trunc(
        'month',
        created_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
    )::date AS month_start,
    COUNT(*) AS paid_orders,
    SUM(total_amount) AS paid_amount
FROM agg_lab.orders
WHERE status = 'paid'
GROUP BY tenant_id, month_start;
```

Materialized view lưu **kết quả đã tính** tại thời điểm tạo/refresh, khác view thông thường thường chỉ lưu định nghĩa truy vấn.

Đọc:

```sql
SELECT *
FROM agg_lab.monthly_paid_summary
ORDER BY tenant_id, month_start;
```

### 20.2. Tính tươi mới là một phần của hợp đồng

Nếu có thêm đơn mới sau khi tạo materialized view, dữ liệu bên trong **không tự cập nhật ngay**. Cần quy trình refresh:

```sql
-- Chạy trong môi trường thực hành khi muốn cập nhật số liệu.
REFRESH MATERIALIZED VIEW agg_lab.monthly_paid_summary;
```

Refresh có thể gây tải và ảnh hưởng việc đọc tùy cách thực hiện. `REFRESH MATERIALIZED VIEW CONCURRENTLY` có những điều kiện như materialized view đã được populate và có unique index phù hợp; không mặc định thêm `CONCURRENTLY` là chạy được.

**Quan trọng:** Nếu dữ liệu trạng thái đơn có thể đổi từ `pending` sang `paid` hoặc bị hoàn tiền, thiết kế incremental summary phải xử lý cả **thay đổi/xóa/điều chỉnh**, không chỉ cộng những hàng insert mới.

### 20.3. Cẩn thận khi đổi grain của bảng tổng hợp sẵn

Nếu bảng pre-aggregate lưu `(tenant_id, month_start, paid_amount, paid_orders)`, bạn có thể lấy tổng paid amount và tổng paid orders theo quý bằng cách cộng các tháng **nếu các tháng không chồng và định nghĩa chỉ tiêu nhất quán**.

Nhưng không thể suy ra chính xác số **khách duy nhất trong quý** chỉ từ `COUNT(DISTINCT customer_id)` của từng tháng, vì khách có thể xuất hiện nhiều tháng. Với chỉ tiêu distinct, cần thêm dữ liệu grain thích hợp hoặc chiến lược đo lường khác.

## 21. Bảo đảm kết quả tổng hợp đúng trong giao dịch và báo cáo

### 21.1. PostgreSQL snapshot và thay đổi đồng thời

Một câu `SELECT ... GROUP BY` đơn lẻ ở isolation `READ COMMITTED` thông thường quan sát các phiên bản hàng phù hợp với snapshot của statement. Nhưng nếu bạn chạy:

```sql
SELECT COUNT(*) FROM agg_lab.orders WHERE status = 'paid';

SELECT SUM(total_amount)
FROM agg_lab.orders
WHERE status = 'paid';
```

thành hai câu riêng, một transaction khác có thể commit giữa chúng. Khi ấy số đơn và tổng tiền có thể thuộc **hai thời điểm khác nhau**.

Nếu yêu cầu số liệu nhất quán của cùng một snapshot, có thể tính chúng trong **một câu SELECT**:

```sql
SELECT
    COUNT(*) AS paid_orders,
    SUM(total_amount) AS paid_amount
FROM agg_lab.orders
WHERE status = 'paid';
```

Hoặc dùng một transaction read-only với isolation thích hợp cho quy trình nhiều statement:

```sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;

SELECT COUNT(*) FROM agg_lab.orders WHERE status = 'paid';
SELECT SUM(total_amount) FROM agg_lab.orders WHERE status = 'paid';

COMMIT;
```

Không giữ transaction báo cáo lâu một cách không kiểm soát: snapshot dài có thể làm tăng yêu cầu lưu phiên bản hàng cũ và ảnh hưởng vacuum/tài nguyên.

### 21.2. Báo cáo không thay thế sổ cái kế toán

`SUM(total_amount) WHERE status='paid'` trong lab trả “tiền các đơn hiện đang paid”. Nhưng hệ thống thật có thể cần:

- Giao dịch trả tiền một phần.
- Hoàn tiền và chargeback.
- Thuế/giảm giá/phí.
- Tiền tệ và tỷ giá.
- Sự kiện ghi nhận doanh thu theo thời điểm khác thời điểm đơn.
- Giá trị bù trừ âm hoặc sổ cái không được sửa trực tiếp.

Trước khi đổi báo cáo thành KPI tài chính, hãy xác định fact table và định nghĩa metric đúng, không dùng `GROUP BY` để che giấu sự khác biệt nghiệp vụ.

## 22. Những lỗi tổng hợp thường gặp

**1. “GROUP BY tự sắp xếp kết quả.”** Không. Muốn thứ tự cụ thể, dùng `ORDER BY`.

**2. “Cứ thêm mọi cột SELECT vào GROUP BY để hết lỗi là đúng.”** Không. Việc này có thể đổi grain từ một tenant thành một đơn.

**3. “COUNT(*) và COUNT(region) luôn giống nhau.”** Không. `COUNT(region)` bỏ qua hàng có `region NULL`.

**4. “COUNT(DISTINCT customer_id) theo từng tháng cộng lại bằng số khách cả quý.”** Không nếu khách xuất hiện nhiều tháng.

**5. “AVG của các AVG theo tenant bằng AVG toàn hệ thống.”** Không trừ khi các nhóm có trọng số phù hợp; phải tổng tiền / tổng số đơn.

**6. “WHERE SUM(total_amount) > 1000 là hợp lệ.”** Không trong truy vấn thông thường; điều kiện trên aggregate dùng `HAVING` hoặc tầng truy vấn bao ngoài.

**7. “HAVING và WHERE luôn thay thế được.”** Không. `WHERE` lọc hàng, `HAVING` lọc nhóm.

**8. “Sau JOIN orders–items, COUNT(*) vẫn là số đơn.”** Không. Nó đếm các dòng sau JOIN.

**9. “Sau JOIN fanout, COUNT(DISTINCT order_id) sẽ sửa cả SUM(total_amount).”** Không. Cần xử lý lại grain của chỉ tiêu tiền.

**10. “SUM(DISTINCT total_amount) giải quyết mọi vấn đề đếm trùng.”** Không. Hai đơn hợp lệ có cùng tiền sẽ bị cộng thiếu.

**11. “LEFT JOIN kết hợp WHERE i.category = ... vẫn giữ các đơn không có item.”** Thường không; điều kiện trên bảng phải có thể loại hàng NULL-extended.

**12. “NULL = NULL là true nên GROUP BY gom NULL.”** Lý giải sai. `NULL = NULL` cho unknown; GROUP BY có ngữ nghĩa grouping riêng.

**13. “Trong ROLLUP, region=NULL luôn là dữ liệu thiếu vùng.”** Không. Nó có thể là NULL đại diện cho subtotal; dùng `GROUPING()`.

**14. “ROLLUP(a,b) và ROLLUP(b,a) có cùng subtotal.”** Không. Thứ tự cột xác định phân cấp.

**15. “CUBE ít tốn tài nguyên hơn GROUP BY thường.”** Không mặc định; nó tạo nhiều grouping sets.

**16. “SUM trên tập rỗng trả 0.”** Trong PostgreSQL, `SUM` trên tập rỗng trả `NULL`; `COUNT(*)` trả 0.

**17. “GROUP BY tháng tự sinh mọi tháng không có dữ liệu.”** Không. Cần bảng lịch/calendar hoặc `generate_series`.

**18. “date_trunc('day', created_at) luôn đúng ngày của tenant.”** Không nếu timestamp là `TIMESTAMPTZ` và timezone báo cáo không được xác định.

**19. “SELECT một query GROUP BY paid là tổng doanh thu tài chính chuẩn.”** Chỉ đúng theo định nghĩa đã nêu, không tự xử lý hoàn tiền/thuế/tiền tệ.

**20. “Window SUM OVER thay GROUP BY mà không ảnh hưởng số hàng.”** Không. Window giữ hàng chi tiết, GROUP BY rút thành một hàng/nhóm.

**21. “Group theo order_id là tổng theo khách hàng.”** Không. Grain một đơn khác grain một khách.

**22. “Thêm index trên mọi khóa nhóm sẽ bảo đảm nhanh.”** Không. Cần quan sát scan, cardinality, query plan và chi phí ghi.

**23. “Materialized view luôn cập nhật khi bảng nguồn thay đổi.”** Không. Cần refresh hoặc pipeline update riêng.

**24. “GROUP BY tenant_id tự bảo vệ dữ liệu tenant khác.”** Không. Đó là việc của bộ lọc và chính sách quyền.

## 23. Bài tập thực hành có lời giải

### Bài 1 — Tổng theo tenant

**Yêu cầu:** chỉ đếm đơn `paid`, trả tenant, số đơn và tổng tiền. Mỗi tenant một hàng.

**Đáp án:**

```sql
SELECT
    tenant_id,
    COUNT(*) AS paid_orders,
    SUM(total_amount) AS paid_amount
FROM agg_lab.orders
WHERE status = 'paid'
GROUP BY tenant_id
ORDER BY tenant_id;
```

Kết quả: tenant 10 có 5 đơn/940; tenant 20 có 4 đơn/870.

### Bài 2 — Thêm vùng làm đổi grain

**Yêu cầu:** số đơn và tiền từng **tenant–region**.

**Đáp án:**

```sql
SELECT
    tenant_id,
    region,
    COUNT(*) AS orders,
    SUM(total_amount) AS amount
FROM agg_lab.orders
WHERE status = 'paid'
GROUP BY tenant_id, region
ORDER BY tenant_id, region NULLS LAST;
```

Có **sáu nhóm**, bao gồm một nhóm `region=NULL` cho mỗi tenant.

### Bài 3 — Đếm số đơn không rõ vùng

**Yêu cầu:** tính số đơn paid, số đơn có region, số đơn thiếu region.

**Đáp án:**

```sql
SELECT
    COUNT(*) AS total,
    COUNT(region) AS known_region,
    COUNT(*) - COUNT(region) AS missing_region
FROM agg_lab.orders
WHERE status = 'paid';
```

Kết quả `9, 7, 2`.

### Bài 4 — HAVING

**Yêu cầu:** tìm tenant có tổng paid amount từ 900 trở lên.

**Đáp án:**

```sql
SELECT tenant_id, SUM(total_amount) AS paid_amount
FROM agg_lab.orders
WHERE status = 'paid'
GROUP BY tenant_id
HAVING SUM(total_amount) >= 900
ORDER BY tenant_id;
```

Chỉ tenant 10 với 940.

### Bài 5 — FILTER nhiều trạng thái

**Yêu cầu:** trên mỗi tenant, lấy số đơn tổng, paid, pending và cancelled.

**Đáp án:**

```sql
SELECT
    tenant_id,
    COUNT(*) AS all_orders,
    COUNT(*) FILTER (WHERE status = 'paid') AS paid_orders,
    COUNT(*) FILTER (WHERE status = 'pending') AS pending_orders,
    COUNT(*) FILTER (WHERE status = 'cancelled') AS cancelled_orders
FROM agg_lab.orders
GROUP BY tenant_id
ORDER BY tenant_id;
```

Tenant 10: `7,5,1,1`; tenant 20: `5,4,1,0`.

### Bài 6 — Doanh thu theo tháng tại Việt Nam

**Yêu cầu:** nhóm đơn paid theo tháng địa phương và sắp tăng dần.

**Đáp án:**

```sql
SELECT
    date_trunc(
        'month',
        created_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
    ) AS month_local,
    SUM(total_amount) AS amount
FROM agg_lab.orders
WHERE status = 'paid'
GROUP BY month_local
ORDER BY month_local;
```

Kết quả tiền: tháng 1 = 1040, tháng 2 = 290, tháng 3 = 480.

### Bài 7 — GROUP BY bị nhân sau JOIN

**Câu hỏi:** tại sao truy vấn sau sai nếu muốn tổng tiền đơn?

```sql
SELECT o.tenant_id, SUM(o.total_amount)
FROM agg_lab.orders AS o
JOIN agg_lab.order_items AS i
    ON i.order_id = o.order_id
WHERE o.status = 'paid'
GROUP BY o.tenant_id;
```

**Đáp án:** Một đơn có nhiều item khiến `o.total_amount` lặp trên nhiều dòng kết quả JOIN, bị cộng nhiều lần. Tính trực tiếp từ `orders`, hoặc tổng hợp item về một hàng/order_id trước khi JOIN.

### Bài 8 — Không dùng SUM(DISTINCT)

**Yêu cầu:** giải thích vì sao `SUM(DISTINCT o.total_amount)` không sửa fanout đúng trong mọi trường hợp.

**Đáp án:** Nếu hai đơn khác nhau cùng có `total_amount=100`, `SUM(DISTINCT total_amount)` chỉ cộng 100 một lần dù cần cộng 200. `DISTINCT` trên **giá trị tiền** không phải distinct trên **định danh đơn**.

### Bài 9 — Đếm khách duy nhất

**Yêu cầu:** mỗi tenant có bao nhiêu khách đã từng có đơn paid?

**Đáp án:**

```sql
SELECT
    tenant_id,
    COUNT(DISTINCT customer_id) AS paying_customers
FROM agg_lab.orders
WHERE status = 'paid'
GROUP BY tenant_id
ORDER BY tenant_id;
```

Mỗi tenant có **3 khách** trong lab.

### Bài 10 — Tổng tenant và tổng chung bằng ROLLUP

**Yêu cầu:** tổng hợp theo tenant, đồng thời thêm một hàng tổng toàn hệ thống.

**Đáp án:**

```sql
SELECT
    tenant_id,
    GROUPING(tenant_id) AS is_grand_total,
    COUNT(*) AS paid_orders,
    SUM(total_amount) AS paid_amount
FROM agg_lab.orders
WHERE status = 'paid'
GROUP BY ROLLUP (tenant_id)
ORDER BY is_grand_total, tenant_id NULLS LAST;
```

Kết quả gồm tenant 10, tenant 20 và một dòng tổng chung `9 đơn/1810`. Trường `is_grand_total` nhận `1` ở hàng tổng, giúp phân biệt khi tenant_id có thể NULL ở mô hình khác.

### Bài 11 — GROUPING() và NULL thật

**Câu hỏi:** trong `ROLLUP(tenant_id, region)`, hai hàng có `tenant_id=10` và `region=NULL` có thể mang ý nghĩa gì?

**Đáp án:** Một hàng là nhóm vùng **chưa biết** trong dữ liệu (90), một hàng là **subtotal của tenant 10** (940). Dùng `GROUPING(region)=0` để nhận diện nhóm dữ liệu thật; `GROUPING(region)=1` cho subtotal.

### Bài 12 — CUBE khác ROLLUP

**Yêu cầu:** ngoài chi tiết tenant–region và tổng tenant, cần **tổng theo region xuyên tenant**.

**Đáp án:**

```sql
SELECT
    tenant_id,
    region,
    GROUPING(tenant_id, region) AS mask,
    SUM(total_amount) AS amount
FROM agg_lab.orders
WHERE status = 'paid'
GROUP BY CUBE (tenant_id, region)
ORDER BY mask, tenant_id NULLS LAST, region NULLS LAST;
```

`CUBE` tạo cả `(region)`, trong khi `ROLLUP(tenant_id,region)` không tạo cấp đó.

### Bài 13 — Trung bình hai tenant

**Câu hỏi:** Vì sao lấy `(188 + 217.5)/2 = 202.75` không phải AOV của toàn hệ thống?

**Đáp án:** Hai tenant có **số đơn khác nhau**, 5 và 4. AOV toàn hệ thống phải là `(940+870)/(5+4) = 1810/9 ≈ 201.11`, tức tổng có trọng số theo số đơn.

### Bài 14 — Window function giữ hàng chi tiết

**Yêu cầu:** mỗi đơn paid vẫn có một hàng, nhưng kèm tổng paid amount của tenant.

**Đáp án:**

```sql
SELECT
    order_id,
    tenant_id,
    total_amount,
    SUM(total_amount) OVER (
        PARTITION BY tenant_id
    ) AS tenant_paid_amount
FROM agg_lab.orders
WHERE status = 'paid'
ORDER BY tenant_id, order_id;
```

Kết quả có **9 hàng**, không phải hai hàng như `GROUP BY tenant_id`.

### Bài 15 — Nhóm tháng trống

**Câu hỏi:** chỉ có đơn paid ở tháng 1–3, làm sao báo cáo vẫn có tháng 4–12 với tiền 0?

**Đáp án:** Sinh dãy tháng bằng `generate_series`, tổng hợp `orders` theo tháng trong CTE riêng, rồi `LEFT JOIN` calendar với kết quả tổng hợp và `COALESCE` tiền khi không có nhóm. `GROUP BY` tự nó không sinh các nhóm không có dữ liệu.

### Bài 16 — Nhóm theo khách thay vì theo đơn

**Yêu cầu:** tenant 10 có mỗi khách mua paid bao nhiêu lần?

**Đáp án:**

```sql
SELECT
    customer_id,
    COUNT(*) AS paid_orders,
    SUM(total_amount) AS total_paid
FROM agg_lab.orders
WHERE tenant_id = 10
  AND status = 'paid'
GROUP BY customer_id
ORDER BY customer_id;
```

Kết quả: khách 101 có **2 đơn/550**, khách 102 có **2 đơn/270**, khách 103 có **1 đơn/120**. Mức tổng hợp là **một khách trong tenant 10**.

### Bài 17 — Dọn môi trường lab

Khi chắc chắn `agg_lab` chỉ có các đối tượng được tạo trong bài:

```sql
-- Chỉ chạy ở database thực hành và sau khi kiểm tra phạm vi:
-- DROP MATERIALIZED VIEW IF EXISTS agg_lab.monthly_paid_summary;
-- DROP TABLE IF EXISTS agg_lab.order_items;
-- DROP TABLE IF EXISTS agg_lab.orders;
-- DROP SCHEMA IF EXISTS agg_lab;
```

Không dùng `DROP SCHEMA ... CASCADE` trong database dùng chung khi chưa xác minh các phụ thuộc; thao tác đó có thể xóa dữ liệu không thuộc bài học.

## 24. Checklist thiết kế một báo cáo GROUP BY

Trước khi đưa truy vấn vào dashboard/API, hãy đi qua các câu hỏi:

1. **Một hàng nguồn đại diện cho gì?** Đơn, item, payment hay event?
2. **Một hàng kết quả đại diện cho gì?** Tenant, tenant–region, tháng, khách hay một subtotal?
3. **Đã lọc đúng tập dữ liệu ở WHERE chưa?** Trạng thái paid, khoảng thời gian, quyền tenant, sản phẩm?
4. **Hàm tổng hợp đúng nghĩa chưa?** `COUNT(*)` so với `COUNT(col)`, `COUNT(DISTINCT)`, `SUM`/`AVG`?
5. **Có cột nullable không?** `COUNT(column)` bỏ NULL; `GROUP BY` tạo một nhóm NULL.
6. **Có JOIN một-nhiều hoặc nhiều-nhiều không?** Nếu có, metric từ bảng cha có thể bị nhân; cần giảm grain trước.
7. **Có nhiều mức subtotal không?** Chọn `GROUPING SETS`, `ROLLUP` hoặc `CUBE`, phân biệt NULL bằng `GROUPING()`.
8. **Mốc thời gian nào đúng?** Ngày đặt, ngày thanh toán, ngày hoàn tiền; timezone nào?
9. **Có nhóm không tồn tại cần hiển thị 0 không?** Sinh dimension/calendar và LEFT JOIN.
10. **Chỉ tiêu có cộng dồn được không?** SUM thường có thể nếu nhóm không chồng, distinct count và average cần tính lại với trọng số.
11. **Có cần tất cả hàng chi tiết không?** Nếu có, cân nhắc window function thay GROUP BY.
12. **Kết quả cần sắp xếp không?** `GROUP BY` không bảo đảm; dùng `ORDER BY` rõ ràng.
13. **Có nhiều tenant/đơn vị tiền tệ không?** Không gộp dữ liệu khác phạm vi hoặc đơn vị tùy tiện.
14. **Hiệu năng đã đo chưa?** `EXPLAIN`, cardinality, hash/sort memory, chỉ mục, phần dữ liệu quét, chi phí đồng thời.
15. **Báo cáo có yêu cầu nhất quán snapshot không?** Một hay nhiều statement, isolation, dữ liệu thay đổi và vật liệu hóa.

## 25. Tổng kết

Trong PostgreSQL, **`GROUP BY` biến các hàng chi tiết thành các nhóm được xác định bởi khóa nhóm**, còn các hàm như `COUNT`, `SUM`, `AVG` tính chỉ tiêu trên từng nhóm. Khóa nhóm quyết định **mức tổng hợp**: một hàng/tenant khác một hàng/tenant–region, và khác một hàng/toàn hệ thống.

Các nguyên tắc quan trọng nhất:

- **Chọn grain trước khi viết SQL**, không thêm mọi cột vào `GROUP BY` chỉ để hết lỗi.
- **`WHERE` lọc hàng; `HAVING` lọc nhóm; `FILTER` áp điều kiện riêng cho từng aggregate.**
- **`COUNT(*)` đếm hàng; `COUNT(column)` bỏ NULL; `COUNT(DISTINCT)` không cộng dồn đơn giản qua các nhóm chồng nhau.**
- **JOIN có thể thay đổi grain** và làm `SUM`/`COUNT` sai; hãy tổng hợp mỗi bảng về grain phù hợp trước khi kết hợp chỉ tiêu.
- **`GROUPING SETS` chọn những cấp cần có; `ROLLUP` tạo subtotal phân cấp; `CUBE` tạo mọi tổ hợp cấp.** Dùng `GROUPING()` để nhận diện NULL do gộp nhóm khác NULL thật của dữ liệu.
- **Tổng hợp theo thời gian cần chọn đúng timestamp và timezone**; `GROUP BY` không sinh những tháng không có dữ liệu.
- **AVG và tỷ lệ cần mẫu số đúng**, không lấy trung bình các trung bình hoặc cộng số distinct tùy tiện.
- **`GROUP BY` không bảo đảm thứ tự kết quả**, và không tự giải quyết quyền truy cập, snapshot nhất quán hoặc tối ưu I/O.

**Kết luận:** Truy vấn tổng hợp đúng không chỉ là câu SQL chạy được. Nó phải trả lời rõ “đang đếm/cộng **điều gì**, trên **những hàng nào**, và mỗi dòng báo cáo đại diện cho **mức nào**?”. Khi ba câu hỏi này được xác định, `GROUP BY` mới là một công cụ đáng tin cậy để xây KPI, báo cáo và phân tích dữ liệu trong PostgreSQL.

### Tài liệu PostgreSQL chính thức

- [SELECT và GROUP BY](https://www.postgresql.org/docs/current/sql-select.html).
- [Aggregate Functions](https://www.postgresql.org/docs/current/functions-aggregate.html).
- [GROUPING() và Grouping Operations](https://www.postgresql.org/docs/current/functions-aggregate.html#FUNCTIONS-GROUPING-TABLE).
- [Date/Time Functions, date_trunc và AT TIME ZONE](https://www.postgresql.org/docs/current/functions-datetime.html).
- [Window Functions](https://www.postgresql.org/docs/current/tutorial-window.html).
- [EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html).
