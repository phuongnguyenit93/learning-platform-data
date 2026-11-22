# CUBE và GROUPING SETS cho nhiều tổ hợp nhóm

Khi làm báo cáo SQL, một câu `GROUP BY` thông thường trả kết quả theo **một tổ hợp cột nhóm**. Chẳng hạn, `GROUP BY region, channel` cho biết doanh thu của từng cặp *khu vực–kênh bán*. Nhưng một dashboard thường cần thêm doanh thu **theo từng khu vực**, **theo từng kênh**, và **tổng toàn hệ thống** trong cùng một tập kết quả.

Ta có thể viết bốn câu `GROUP BY` riêng rồi ghép bằng `UNION ALL`. Tuy nhiên, SQL còn cung cấp hai công cụ được thiết kế cho bài toán nhiều mức tổng hợp:

- **`GROUPING SETS`**: liệt kê **chính xác các tổ hợp nhóm** mà báo cáo cần.
- **`CUBE`**: tạo **mọi tổ hợp nhóm có thể có** từ các chiều được chỉ định, kể cả nhóm rỗng `()` đại diện cho tổng toàn bộ.

Bài học thuộc chương **Tổng hợp dữ liệu** của Database SQL. Ví dụ thực hành sử dụng PostgreSQL, tập trung vào cách đọc và dự đoán kết quả của các cấp độ nhóm, cách dùng `GROUPING()` để nhận biết subtotal/grand total, xử lý `NULL` thật trong dữ liệu, kiểm soát trùng lặp tổng và lựa chọn cấu trúc phù hợp cho báo cáo nhiều chiều.

## 1. Mỗi hàng của báo cáo đại diện cho điều gì?

Trước khi viết câu tổng hợp, cần phân biệt **cấp độ dữ liệu đầu vào** (*grain*) và **cấp độ kết quả**.

Ví dụ, bảng giao dịch có một hàng cho một lần bán hàng:

| `sale_id` | `region` | `channel` | `amount` |
| ---: | --- | --- | ---: |
| 1 | North | Online | 100 |
| 2 | North | Store | 80 |
| 3 | South | Online | 120 |

Với `GROUP BY region, channel`, mỗi hàng kết quả đại diện cho một **cặp khu vực và kênh**. Với `GROUP BY region`, mỗi hàng đại diện cho **một khu vực**, bất kể kênh. Khi gộp cả hai cấp vào cùng báo cáo, ta phải biết hàng nào là **chi tiết theo cặp**, hàng nào là **tổng phụ theo một chiều**, và hàng nào là **tổng chung**.

Một cách đọc:

```text
Giao dịch gốc
    │
    ├── Theo (region, channel) ──> từng cặp khu vực/kênh
    ├── Theo (region) ───────────> tổng từng khu vực
    ├── Theo (channel) ──────────> tổng từng kênh
    └── Theo () ────────────────> tổng toàn hệ thống
```

**Các kết quả trên chồng lấp về dữ liệu nguồn.** Cùng một giao dịch được tính trong nhiều cấp tổng hợp, nên không được cộng bừa tất cả hàng của báo cáo như thể chúng là các giao dịch độc lập.

## 2. Tạo bộ dữ liệu thực hành có thể kiểm chứng bằng tay

Chạy đoạn dưới trong một phiên PostgreSQL dùng cho học tập. Bảng tạm `demo_sales_cube` chỉ tồn tại trong phiên hiện tại.

```sql
CREATE TEMP TABLE demo_sales_cube (
    sale_id       INTEGER PRIMARY KEY,
    sale_date     DATE NOT NULL,
    region        TEXT,
    channel       TEXT NOT NULL,
    product_group TEXT NOT NULL,
    amount        NUMERIC(12, 2) NOT NULL CHECK (amount >= 0),
    status        TEXT NOT NULL
        CHECK (status IN ('paid', 'cancelled'))
);

INSERT INTO demo_sales_cube
    (sale_id, sale_date, region, channel,
     product_group, amount, status)
VALUES
    ( 1, DATE '2025-05-01', 'North', 'Online', 'Books', 100.00, 'paid'),
    ( 2, DATE '2025-05-01', 'North', 'Store',  'Books',  80.00, 'paid'),
    ( 3, DATE '2025-05-02', 'South', 'Online', 'Books', 120.00, 'paid'),
    ( 4, DATE '2025-05-02', 'South', 'Store',  'Tech',  200.00, 'paid'),
    ( 5, DATE '2025-05-03', 'North', 'Online', 'Tech',  150.00, 'paid'),
    ( 6, DATE '2025-05-03', 'South', 'Online', 'Tech',   90.00, 'paid'),
    ( 7, DATE '2025-05-04', NULL,    'Online', 'Books', 50.00, 'paid'),
    ( 8, DATE '2025-05-04', 'North', 'Store',  'Tech',   70.00, 'paid'),
    ( 9, DATE '2025-05-05', 'South', 'Store',  'Books',  60.00, 'cancelled'),
    (10, DATE '2025-05-05', 'South', 'Online', 'Books',  30.00, 'paid'),
    (11, DATE '2025-05-06', NULL,    'Store',  'Tech',   40.00, 'paid'),
    (12, DATE '2025-05-06', 'North', 'Online', 'Books',  25.00, 'cancelled');
```

Dữ liệu có **12 giao dịch**, trong đó **10 paid** và **2 cancelled**. `region = NULL` ở giao dịch `7` và `11` có nghĩa là **chưa biết khu vực**, không phải một hàng tổng hợp. Chúng được đưa vào có chủ đích để phát hiện một lỗi rất phổ biến khi đọc kết quả `CUBE`.

Trong bài, “doanh thu” được định nghĩa là **tổng `amount` của các giao dịch `paid`**. Giao dịch `cancelled` không tính vào doanh thu. Đây là quy ước cho ví dụ, không thay thế chính sách ghi nhận doanh thu của một hệ thống thực tế.

### 2.1. Tập đã lọc để tính doanh thu

```sql
SELECT sale_id, region, channel, product_group, amount
FROM demo_sales_cube
WHERE status = 'paid'
ORDER BY sale_id;
```

Các giá trị được dùng:

| `sale_id` | `region` | `channel` | `product_group` | `amount` |
| ---: | --- | --- | --- | ---: |
| 1 | North | Online | Books | 100 |
| 2 | North | Store | Books | 80 |
| 3 | South | Online | Books | 120 |
| 4 | South | Store | Tech | 200 |
| 5 | North | Online | Tech | 150 |
| 6 | South | Online | Tech | 90 |
| 7 | `NULL` | Online | Books | 50 |
| 8 | North | Store | Tech | 70 |
| 10 | South | Online | Books | 30 |
| 11 | `NULL` | Store | Tech | 40 |

Tổng tiền đã thanh toán:

```text
100 + 80 + 120 + 200 + 150 + 90 + 50 + 70 + 30 + 40
= 930
```

Đây là **mốc đối chiếu** xuyên suốt bài.

### 2.2. Tính các tổng riêng trước khi học CUBE

| Cấp nhóm | Giá trị nhóm | Tổng `amount` paid |
| --- | --- | ---: |
| Khu vực | North | 400 |
| Khu vực | South | 440 |
| Khu vực | `NULL` (chưa rõ) | 90 |
| Kênh | Online | 540 |
| Kênh | Store | 390 |
| Loại sản phẩm | Books | 380 |
| Loại sản phẩm | Tech | 550 |
| Toàn hệ thống | Tất cả | 930 |

Kiểm tra:

```text
400 + 440 + 90 = 930  (cộng các khu vực)
540 + 390      = 930  (cộng các kênh)
380 + 550      = 930  (cộng các loại sản phẩm)
```

Đây là những phép cộng **trong cùng một cấp phân chia**, không phải phép cộng toàn bộ mọi loại subtotal.

## 3. Ôn lại GROUP BY thông thường

Đầu tiên, hãy tổng hợp theo cặp khu vực–kênh:

```sql
SELECT
    region,
    channel,
    COUNT(*) AS paid_sales,
    SUM(amount) AS revenue
FROM demo_sales_cube
WHERE status = 'paid'
GROUP BY region, channel
ORDER BY region NULLS LAST, channel;
```

Kết quả là **6 nhóm**:

| `region` | `channel` | `paid_sales` | `revenue` |
| --- | --- | ---: | ---: |
| North | Online | 2 | 250 |
| North | Store | 2 | 150 |
| South | Online | 3 | 240 |
| South | Store | 1 | 200 |
| `NULL` | Online | 1 | 50 |
| `NULL` | Store | 1 | 40 |

`SUM(amount)` tính trong từng nhóm do `GROUP BY` tạo ra. Với North–Online, hai giao dịch có tiền 100 và 150 nên doanh thu nhóm là 250.

Quan sát ba điểm:

1. `GROUP BY region, channel` giữ một hàng trên **mỗi tổ hợp khác nhau** của hai cột.
2. Các hàng có `region IS NULL` vẫn được nhóm lại theo các cột còn lại; `NULL` không tự động loại dữ liệu khỏi `GROUP BY`.
3. Kết quả **chưa có** tổng North = 400, tổng Online = 540 hoặc tổng chung = 930. Muốn các cấp đó, cần phép tổng hợp bổ sung.

### 3.1. Ba câu GROUP BY khác nhau cho ba góc nhìn

Theo khu vực:

```sql
SELECT region, SUM(amount) AS revenue
FROM demo_sales_cube
WHERE status = 'paid'
GROUP BY region
ORDER BY region NULLS LAST;
```

Theo kênh:

```sql
SELECT channel, SUM(amount) AS revenue
FROM demo_sales_cube
WHERE status = 'paid'
GROUP BY channel
ORDER BY channel;
```

Toàn hệ thống:

```sql
SELECT SUM(amount) AS revenue
FROM demo_sales_cube
WHERE status = 'paid';
```

Kết quả tương ứng:

- Theo khu vực: North 400, South 440, không rõ khu vực 90.
- Theo kênh: Online 540, Store 390.
- Toàn hệ thống: 930.

`GROUPING SETS` giúp yêu cầu những cấp đó trong **một câu lệnh tổng hợp**.

## 4. GROUPING SETS: chỉ định chính xác các cấp nhóm cần lấy

Cú pháp khái quát:

```sql
SELECT dimension_columns, aggregate_functions
FROM source
WHERE ...
GROUP BY GROUPING SETS (
    (dimension_a, dimension_b),
    (dimension_a),
    (dimension_b),
    ()
);
```

Mỗi mục trong `GROUPING SETS` là một **tập cột nhóm** riêng. Với ví dụ thực tế:

```sql
SELECT
    region,
    channel,
    COUNT(*) AS paid_sales,
    SUM(amount) AS revenue
FROM demo_sales_cube
WHERE status = 'paid'
GROUP BY GROUPING SETS (
    (region, channel),  -- Từng cặp khu vực/kênh
    (region),           -- Tổng theo khu vực
    (channel),          -- Tổng theo kênh
    ()                  -- Tổng chung
)
ORDER BY region NULLS LAST, channel NULLS LAST;
```

Về mặt logic, câu này tính **bốn loại nhóm**:

| Grouping set | Các cột phân nhóm | Cấp kết quả | Số hàng trên dữ liệu mẫu |
| --- | --- | --- | ---: |
| `(region, channel)` | Khu vực và kênh | Chi tiết cặp | 6 |
| `(region)` | Khu vực | Subtotal khu vực | 3 |
| `(channel)` | Kênh | Subtotal kênh | 2 |
| `()` | Không có cột nhóm | Grand total | 1 |
| **Tổng** | | | **12** |

Ở đây có 12 hàng **báo cáo**, dù bảng nguồn chỉ có 10 giao dịch paid. Điều này hoàn toàn bình thường: cùng một giao dịch góp phần vào nhiều cấp tổng hợp.

### 4.1. Grouping set rỗng `()` nghĩa là gì?

`()` không có chiều nào để chia thành nhiều nhóm. Khi có đầu vào, nó tạo **một nhóm duy nhất bao toàn bộ các hàng được lọc**.

```sql
SELECT SUM(amount) AS revenue
FROM demo_sales_cube
WHERE status = 'paid'
GROUP BY GROUPING SETS (());
```

Kết quả là 930, tương tự một câu tổng hợp không có `GROUP BY` thông thường trên cùng tập dữ liệu.

Chú ý phân biệt:

- `()` bên trong `GROUPING SETS` là **một cấp tổng hợp**.
- `NULL` trong một cột dữ liệu là **giá trị chưa biết/không có của hàng nguồn**.

Chúng có thể cùng được hiển thị dưới dạng `NULL` ở kết quả báo cáo, nhưng có ý nghĩa hoàn toàn khác.

### 4.2. GROUPING SETS tương ứng các truy vấn UNION ALL

Về tư duy, ví dụ bốn mức trên gần như việc ghép:

```sql
-- PostgreSQL: minh họa cách biểu diễn bằng các SELECT riêng.
SELECT region, channel, 'detail'::text AS level_name,
       SUM(amount) AS revenue
FROM demo_sales_cube
WHERE status = 'paid'
GROUP BY region, channel

UNION ALL

SELECT region, NULL::text, 'region_total',
       SUM(amount)
FROM demo_sales_cube
WHERE status = 'paid'
GROUP BY region

UNION ALL

SELECT NULL::text, channel, 'channel_total',
       SUM(amount)
FROM demo_sales_cube
WHERE status = 'paid'
GROUP BY channel

UNION ALL

SELECT NULL::text, NULL::text, 'grand_total',
       SUM(amount)
FROM demo_sales_cube
WHERE status = 'paid';
```

`UNION ALL` giữ các hàng từ từng mức, kể cả những hàng có giá trị hiển thị giống nhau. Trong thực tế, `GROUPING SETS` ngắn gọn hơn và cho bộ tối ưu hóa cơ hội thực hiện nhiều mức tổng hợp trong một kế hoạch; không có cam kết rằng nó luôn nhanh hơn mọi cách viết `UNION ALL` ở mọi hệ quản trị và mọi tập dữ liệu.

Trong ví dụ `UNION ALL`, chuỗi `level_name` được chúng ta tự thêm để nhận diện cấp nhóm. Với `GROUPING SETS`, database cung cấp hàm `GROUPING()` giúp làm điều này **không cần tự gắn chuỗi ở từng nhánh**.

## 5. Vấn đề lớn nhất: NULL thật hay NULL do cột bị lược bỏ?

Trong kết quả `GROUPING SETS`, cột **không thuộc grouping set hiện tại** thường được hiển thị thành `NULL`. Nhưng bảng nguồn cũng có thể chứa `NULL` thật.

Xét ba tình huống:

| Kết quả nhìn thấy | Có thể nghĩa là |
| --- | --- |
| `region = NULL, channel = Online, revenue = 50` | Chi tiết: giao dịch chưa rõ khu vực, bán Online |
| `region = NULL, channel = Online, revenue = 540` | Subtotal: **mọi khu vực**, riêng kênh Online |
| `region = NULL, channel = NULL, revenue = 930` | Tổng toàn hệ thống |

Nếu chỉ xem hai cột `region` và `channel`, rất dễ nhầm dòng chi tiết không rõ khu vực với subtotal Online. Hơn nữa, giá trị `(NULL, NULL)` có thể xuất hiện ở **subtotal khu vực chưa biết** với doanh thu 90 và ở **grand total** với doanh thu 930.

**Không nên dùng duy nhất `region IS NULL` để kết luận đây là tổng mọi khu vực.** Trong ví dụ, `region IS NULL` còn mang ý nghĩa dữ liệu thật.

## 6. GROUPING(): xác định cột bị loại khỏi tập nhóm

PostgreSQL hỗ trợ hàm `GROUPING(...)` trong truy vấn có `GROUPING SETS`, `ROLLUP` hoặc `CUBE`.

- `GROUPING(region) = 0`: biểu thức `region` **có mặt** trong grouping set hiện tại.
- `GROUPING(region) = 1`: biểu thức `region` **bị lược bỏ** khỏi grouping set hiện tại.
- Tương tự cho `channel` và các chiều khác.

Hàm này nhận diện **cấp tổng hợp**, không kiểm tra giá trị của cột dữ liệu. Vì vậy, một hàng có `region IS NULL` thật vẫn có `GROUPING(region) = 0` nếu đang phân nhóm theo region.

### 6.1. Truy vấn có đầy đủ cờ GROUPING

```sql
SELECT
    region,
    channel,
    GROUPING(region) AS g_region,
    GROUPING(channel) AS g_channel,
    GROUPING(region, channel) AS group_code,
    COUNT(*) AS paid_sales,
    SUM(amount) AS revenue
FROM demo_sales_cube
WHERE status = 'paid'
GROUP BY GROUPING SETS (
    (region, channel),
    (region),
    (channel),
    ()
)
ORDER BY
    group_code,
    region NULLS FIRST,
    channel NULLS FIRST;
```

Kết quả dự kiến, nhóm theo `group_code` để dễ quan sát:

| `region` | `channel` | `g_region` | `g_channel` | `group_code` | `revenue` |
| --- | --- | ---: | ---: | ---: | ---: |
| North | Online | 0 | 0 | 0 | 250 |
| North | Store | 0 | 0 | 0 | 150 |
| South | Online | 0 | 0 | 0 | 240 |
| South | Store | 0 | 0 | 0 | 200 |
| `NULL` | Online | 0 | 0 | 0 | 50 |
| `NULL` | Store | 0 | 0 | 0 | 40 |
| North | `NULL` | 0 | 1 | 1 | 400 |
| South | `NULL` | 0 | 1 | 1 | 440 |
| `NULL` | `NULL` | 0 | 1 | 1 | 90 |
| `NULL` | Online | 1 | 0 | 2 | 540 |
| `NULL` | Store | 1 | 0 | 2 | 390 |
| `NULL` | `NULL` | 1 | 1 | 3 | 930 |

Nếu dùng đúng `ORDER BY` trong truy vấn, trong nhóm mã 0 hai dòng region `NULL` có thể xuất hiện trước North và South; bảng trên được **sắp theo nhóm ý nghĩa** để dễ đọc. Nội dung và số hàng vẫn như nhau.

Hai điểm cần nhớ:

1. `group_code = 0` chứa mọi nhóm chi tiết, kể cả nhóm có **region thật bằng `NULL`**.
2. `group_code = 3` là grand total, bất kể dữ liệu nguồn có `NULL` hay không.

### 6.2. Cách tính bitmask của GROUPING(a, b)

Trong PostgreSQL, `GROUPING(region, channel)` ghép các cờ theo thứ tự đối số. Với hai cột:

```text
GROUPING(region, channel)
    = 2 * GROUPING(region) + GROUPING(channel)
```

| `GROUPING(region)` | `GROUPING(channel)` | Nhị phân | `group_code` | Ý nghĩa |
| ---: | ---: | --- | ---: | --- |
| 0 | 0 | `00` | 0 | Theo `region, channel` |
| 0 | 1 | `01` | 1 | Theo `region` |
| 1 | 0 | `10` | 2 | Theo `channel` |
| 1 | 1 | `11` | 3 | Tổng chung `()` |

**Đối số bên phải nhất là bit thấp nhất.** Nếu đổi thành `GROUPING(channel, region)`, các mã số subtotal một chiều cũng đổi theo. Mã nhóm không phải một “ID nhóm toàn cầu”; nó được diễn giải theo **thứ tự các biểu thức truyền vào `GROUPING`**.

Với ba chiều `(region, channel, product_group)`, các trọng số theo thứ tự trái sang phải là **4, 2, 1**:

```text
GROUPING(region, channel, product_group)
 = 4 * GROUPING(region)
 + 2 * GROUPING(channel)
 + 1 * GROUPING(product_group)
```

Mã 7 (nhị phân `111`) là tổng chung; mã 0 là nhóm chi tiết theo cả ba chiều. Mã 1 có nghĩa **product_group bị lược bỏ**, còn region và channel vẫn thuộc khóa nhóm.

### 6.3. Đặt nhãn cấp tổng hợp rõ ràng

```sql
SELECT
    CASE
        WHEN GROUPING(region) = 1 THEN 'ALL REGIONS'
        WHEN region IS NULL THEN '(Unknown region)'
        ELSE region
    END AS region_label,
    CASE
        WHEN GROUPING(channel) = 1 THEN 'ALL CHANNELS'
        ELSE channel
    END AS channel_label,
    CASE GROUPING(region, channel)
        WHEN 0 THEN 'detail'
        WHEN 1 THEN 'region_total'
        WHEN 2 THEN 'channel_total'
        WHEN 3 THEN 'grand_total'
    END AS level_name,
    SUM(amount) AS revenue
FROM demo_sales_cube
WHERE status = 'paid'
GROUP BY CUBE (region, channel)
ORDER BY
    GROUPING(region, channel),
    region NULLS LAST,
    channel NULLS LAST;
```

Với cách này:

- `(Unknown region) / Online` có doanh thu 50 là **nhóm dữ liệu chưa rõ khu vực**, không phải tổng Online.
- `ALL REGIONS / Online` có doanh thu 540 là **subtotal theo channel**.
- `ALL REGIONS / ALL CHANNELS` có doanh thu 930 là **grand total**.

Các nhãn này chỉ dùng để trình bày. Tốt nhất nên giữ **các cột khóa gốc và cột `level_name`/`group_code` riêng**, tránh phá khả năng tiếp tục xử lý dữ liệu bằng cách thay hết giá trị gốc thành chuỗi hiển thị.

### 6.4. GROUPING() không phải GROUP BY hay hàm đếm

Tên dễ gây nhầm:

- `GROUP BY`: tạo các nhóm.
- `GROUPING(...)`: báo biểu thức nhóm có bị **lược khỏi grouping set** hiện tại không; với nhiều đối số cho bitmask.
- `COUNT(*)`: đếm số hàng nguồn trong nhóm.
- `SUM(amount)`: cộng giá trị trong nhóm.

`GROUPING(region) = 1` **không** có nghĩa là nhóm có một khu vực, và `GROUPING(region) = 0` **không** có nghĩa là không có hàng. Đó là cờ cấu trúc cấp tổng hợp.

## 7. CUBE: sinh mọi tổ hợp nhóm từ các chiều

Cú pháp:

```sql
GROUP BY CUBE (region, channel)
```

tương đương về mặt các grouping set được yêu cầu với:

```sql
GROUP BY GROUPING SETS (
    (region, channel),
    (region),
    (channel),
    ()
)
```

Với **n chiều**, một `CUBE` đầy đủ tạo ra **2ⁿ grouping sets**, vì mỗi chiều có hai khả năng: **có mặt** hoặc **bị lược bỏ**.

| Số chiều | Số grouping sets của CUBE |
| ---: | ---: |
| 1 | 2 |
| 2 | 4 |
| 3 | 8 |
| 4 | 16 |
| 5 | 32 |
| 10 | 1.024 |

Đây là số **cấp nhóm**, không phải số hàng kết quả. Mỗi cấp có thể tạo ra hàng nghìn hoặc hàng triệu nhóm nếu chiều có nhiều giá trị.

### 7.1. Hai chiều: khu vực và kênh

```sql
SELECT
    region,
    channel,
    SUM(amount) AS revenue,
    GROUPING(region, channel) AS group_code
FROM demo_sales_cube
WHERE status = 'paid'
GROUP BY CUBE (region, channel)
ORDER BY
    group_code,
    region NULLS LAST,
    channel NULLS LAST;
```

Câu này trả cùng 12 hàng đã liệt kê trong phần `GROUPING SETS`. Với hai chiều, `CUBE` là cách viết ngắn khi thực sự muốn **đủ bốn cấp**.

### 7.2. Ba chiều: khu vực, kênh và nhóm sản phẩm

```sql
SELECT
    region,
    channel,
    product_group,
    SUM(amount) AS revenue,
    GROUPING(region, channel, product_group) AS group_code
FROM demo_sales_cube
WHERE status = 'paid'
GROUP BY CUBE (region, channel, product_group)
ORDER BY
    group_code,
    region NULLS LAST,
    channel NULLS LAST,
    product_group NULLS LAST;
```

Câu này yêu cầu tám grouping sets:

| Mã nhị phân | Mã số | Grouping set | Cấp báo cáo |
| --- | ---: | --- | --- |
| `000` | 0 | `(region, channel, product_group)` | Chi tiết đủ ba chiều |
| `001` | 1 | `(region, channel)` | Tổng theo cặp khu vực–kênh |
| `010` | 2 | `(region, product_group)` | Tổng theo khu vực–loại sản phẩm |
| `011` | 3 | `(region)` | Tổng từng khu vực |
| `100` | 4 | `(channel, product_group)` | Tổng theo kênh–loại sản phẩm |
| `101` | 5 | `(channel)` | Tổng từng kênh |
| `110` | 6 | `(product_group)` | Tổng từng loại sản phẩm |
| `111` | 7 | `()` | Tổng toàn hệ thống |

Ví dụ:

- `group_code = 0`, North–Online–Books: doanh thu 100.
- `group_code = 1`, North–Online–`NULL`: doanh thu 250 (cả Books lẫn Tech).
- `group_code = 2`, North–`NULL`–Books: doanh thu 180 (100 Online + 80 Store).
- `group_code = 3`, North–`NULL`–`NULL`: doanh thu 400.
- `group_code = 6`, `NULL`–`NULL`–Books: doanh thu 380.
- `group_code = 7`, `NULL`–`NULL`–`NULL`: doanh thu 930.

Các `NULL` ở ví dụ này phải được đọc cùng `group_code` để biết cột nào bị lược bỏ. Với region không xác định thật, giá trị `NULL` còn có thể xuất hiện trong các nhóm giữ region.

### 7.3. Tại sao CUBE nhiều chiều có thể rất lớn?

Giả sử có bốn chiều: vùng (10 giá trị), kênh (4), nhóm sản phẩm (100), tháng (24). Chỉ cấp chi tiết theo **tất cả bốn chiều** đã có thể có tối đa `10 × 4 × 100 × 24 = 96.000` nhóm có dữ liệu, tùy phân bố dữ liệu nguồn. `CUBE` còn thêm 15 cấp tổng hợp khác.

Số nhóm **thực tế** phụ thuộc các tổ hợp tồn tại trong dữ liệu và bộ lọc `WHERE`; `CUBE` không tự tạo mọi tổ hợp chưa từng có ở cấp chi tiết. Tuy nhiên, số cấp tăng theo lũy thừa hai, khiến chi phí tính, sắp xếp và truyền kết quả có thể tăng nhanh.

Nếu dashboard chỉ cần 5 trong 16 tổ hợp, thường nên dùng `GROUPING SETS` chọn đúng 5 cấp thay vì dựng cả `CUBE` 4 chiều rồi bỏ phần lớn kết quả.

## 8. So sánh CUBE, ROLLUP và GROUPING SETS

Ba cú pháp thường xuất hiện cạnh nhau nhưng biểu diễn các nhu cầu khác nhau.

| Cú pháp | Cách tạo grouping sets | Phù hợp |
| --- | --- | --- |
| `GROUP BY region, channel` | Chỉ `(region, channel)` | Một cấp chi tiết cố định |
| `ROLLUP(region, channel)` | `(region, channel)`, `(region)`, `()` | Hệ phân cấp: khu vực → kênh → tổng |
| `CUBE(region, channel)` | `(region, channel)`, `(region)`, `(channel)`, `()` | Mọi tổ hợp hai chiều |
| `GROUPING SETS((region,channel),(channel),())` | Chính xác ba cấp được liệt kê | Báo cáo có yêu cầu tổ hợp cụ thể |

### 8.1. ROLLUP tuân theo thứ tự chiều

```sql
SELECT region, channel, SUM(amount) AS revenue
FROM demo_sales_cube
WHERE status = 'paid'
GROUP BY ROLLUP (region, channel);
```

Với hai cột, `ROLLUP(region, channel)` sinh:

```text
(region, channel)
(region)
()
```

Nó **không** sinh riêng `(channel)`. Nếu đổi thứ tự:

```sql
GROUP BY ROLLUP (channel, region)
```

ta được:

```text
(channel, region)
(channel)
()
```

Lúc này subtotal có kênh nhưng không có khu vực. `ROLLUP` phù hợp khi các chiều tạo thành **một thứ bậc có thứ tự**. `CUBE` phù hợp khi các chiều là những góc nhìn độc lập và cần mọi tổ hợp.

### 8.2. Ba chiều: ROLLUP sinh n + 1 cấp, CUBE sinh 2ⁿ cấp

Với `(region, channel, product_group)`:

```text
ROLLUP:
(region, channel, product_group)
(region, channel)
(region)
()
=> 4 cấp

CUBE:
(region, channel, product_group)
(region, channel)
(region, product_group)
(region)
(channel, product_group)
(channel)
(product_group)
()
=> 8 cấp
```

Nếu mong muốn báo cáo theo hệ phân cấp “quốc gia → tỉnh → quận”, `ROLLUP` thường là cách diễn đạt tự nhiên hơn. Nếu muốn số liệu xoay linh hoạt theo khu vực, kênh và loại sản phẩm, `CUBE` có thể thích hợp, nhưng phải cân nhắc kích thước đầu ra.

### 8.3. GROUPING SETS kết hợp linh hoạt

Chỉ lấy các cấp: theo khu vực–kênh, theo khu vực–nhóm sản phẩm, theo nhóm sản phẩm và tổng chung:

```sql
SELECT
    region,
    channel,
    product_group,
    GROUPING(region, channel, product_group) AS group_code,
    SUM(amount) AS revenue
FROM demo_sales_cube
WHERE status = 'paid'
GROUP BY GROUPING SETS (
    (region, channel),
    (region, product_group),
    (product_group),
    ()
)
ORDER BY
    group_code,
    region NULLS LAST,
    channel NULLS LAST,
    product_group NULLS LAST;
```

Câu này **không** yêu cầu các cấp `(channel)`, `(region)` hoặc `(channel, product_group)`. Đây là ưu điểm khi dashboard chỉ cần vài tổ hợp.

Đối chiếu số nhóm dự kiến:

- Theo `(region, channel)`: 6 nhóm.
- Theo `(region, product_group)`: 6 nhóm.
- Theo `(product_group)`: 2 nhóm.
- Tổng chung `()`: 1 nhóm.

Tổng cộng **15 hàng kết quả** nếu mỗi grouping set được liệt kê một lần và dữ liệu như trên.

Trong PostgreSQL, có thể kết hợp các cấu trúc grouping như `GROUPING SETS` với `ROLLUP` hoặc `CUBE` trong câu `GROUP BY` theo cú pháp được hỗ trợ. Tuy nhiên, cách kết hợp nhiều grouping item có thể tạo **tích các tổ hợp** hoặc các grouping set trùng nhau; khi báo cáo phức tạp, cách viết rõ từng grouping set thường dễ kiểm soát hơn.

## 9. GROUPING SETS với một chiều luôn được giữ

Đôi khi ta muốn mọi hàng kết quả đều thuộc **một khu vực cụ thể**, nhưng trong mỗi khu vực có thể hiển thị doanh thu theo kênh và subtotal khu vực.

Cách viết PostgreSQL:

```sql
SELECT
    region,
    channel,
    GROUPING(channel) AS channel_omitted,
    SUM(amount) AS revenue
FROM demo_sales_cube
WHERE status = 'paid'
GROUP BY region,
         GROUPING SETS (
             (channel),
             ()
         )
ORDER BY
    region NULLS LAST,
    GROUPING(channel),
    channel;
```

Ý nghĩa tương đương với:

```sql
GROUP BY GROUPING SETS (
    (region, channel),
    (region)
)
```

`region` luôn được giữ trong các tập nhóm; chỉ `channel` thay đổi giữa “có mặt” và “bị lược bỏ”.

Một ví dụ với North:

| `region` | `channel` | `channel_omitted` | `revenue` |
| --- | --- | ---: | ---: |
| North | Online | 0 | 250 |
| North | Store | 0 | 150 |
| North | `NULL` | 1 | 400 |

Không có dòng grand total 930 và không có dòng channel total 540/390, vì không có grouping set nào lược bỏ `region`.

Đây là lựa chọn tốt khi người dùng xem báo cáo “khu vực là cấp gốc, kênh là cấp phụ”, nhưng **không muốn các tổng theo kênh của toàn bộ khu vực**.

## 10. Dùng GROUPING() để chọn cấp kết quả, thay vì đoán qua NULL

Một báo cáo `CUBE` có thể chứa nhiều cấp, trong khi giao diện chỉ muốn các subtotal khu vực và tổng chung. Có thể lọc theo **mã cấp tổng hợp** bằng `HAVING`:

```sql
SELECT
    region,
    channel,
    GROUPING(region, channel) AS group_code,
    SUM(amount) AS revenue
FROM demo_sales_cube
WHERE status = 'paid'
GROUP BY CUBE (region, channel)
HAVING GROUPING(region, channel) IN (1, 3)
ORDER BY group_code, region NULLS LAST;
```

Kết quả gồm:

- Mã 1: North 400, South 440, region chưa biết 90.
- Mã 3: grand total 930.

Tổng cộng 4 hàng.

### 10.1. WHERE và HAVING không thay thế nhau

`WHERE` lọc **hàng nguồn trước khi tổng hợp**:

```sql
WHERE status = 'paid'
  AND channel = 'Online'
```

Nếu thêm điều kiện `channel = 'Online'` trước `GROUP BY CUBE(region,channel)`, grand total sẽ chỉ còn **doanh thu Online = 540**, không phải doanh thu toàn hệ thống 930.

`HAVING` lọc **nhóm sau khi đã tổng hợp**:

```sql
HAVING GROUPING(region, channel) = 3
```

chỉ lấy grand total của tập nguồn đã chọn trong `WHERE`. Hai mệnh đề phục vụ hai ý nghĩa khác nhau.

### 10.2. Lọc theo giá trị tổng hợp cũng có thể loại từng cấp khác nhau

```sql
SELECT
    region,
    channel,
    GROUPING(region, channel) AS group_code,
    SUM(amount) AS revenue
FROM demo_sales_cube
WHERE status = 'paid'
GROUP BY CUBE (region, channel)
HAVING SUM(amount) >= 200;
```

Điều kiện này áp dụng lên **mọi grouping set**. Ví dụ, North–Online 250 được giữ, North–Store 150 bị loại, nhưng subtotal North 400 vẫn được giữ. Không có mâu thuẫn: đó là những hàng của **các cấp nhóm khác nhau**.

Nếu dashboard chỉ muốn “các cặp region–channel có doanh thu từ 200”, hãy thêm điều kiện cấp:

```sql
HAVING GROUPING(region, channel) = 0
   AND SUM(amount) >= 200
```

Kết quả chỉ là các nhóm chi tiết đủ ngưỡng: North–Online 250, South–Online 240, South–Store 200.

### 10.3. Tránh suy luận theo vị trí của NULL

Điều kiện sau là **sai ý nghĩa** khi muốn lấy grand total:

```sql
-- SAI: có thể chọn các nhóm dữ liệu NULL thật và subtotal khác.
HAVING region IS NULL AND channel IS NULL
```

Với bảng mẫu, các hàng `(NULL,NULL)` có thể biểu thị tổng khu vực chưa biết 90 hoặc grand total 930. Hãy dùng `GROUPING(region, channel) = 3` để xác định đúng cấp tổng chung.

## 11. Nhiều chỉ số trong cùng báo cáo: COUNT, SUM, AVG và FILTER

`GROUPING SETS`/`CUBE` chỉ quyết định **cấp nhóm**. Trong mỗi cấp, vẫn có thể tính nhiều aggregate khác nhau:

```sql
SELECT
    region,
    channel,
    GROUPING(region, channel) AS group_code,
    COUNT(*) AS all_transactions,
    COUNT(*) FILTER (WHERE status = 'paid') AS paid_transactions,
    COUNT(*) FILTER (WHERE status = 'cancelled') AS cancelled_transactions,
    COALESCE(
        SUM(amount) FILTER (WHERE status = 'paid'),
        0::numeric
    ) AS paid_revenue
FROM demo_sales_cube
GROUP BY CUBE (region, channel)
ORDER BY
    group_code,
    region NULLS LAST,
    channel NULLS LAST;
```

Đây là cú pháp PostgreSQL có `FILTER (WHERE ...)` trên aggregate. Tại cấp grand total (`group_code = 3`), kết quả là:

| `all_transactions` | `paid_transactions` | `cancelled_transactions` | `paid_revenue` |
| ---: | ---: | ---: | ---: |
| 12 | 10 | 2 | 930 |

Một số chú ý:

- `COUNT(*)` đếm mọi hàng trong nhóm, kể cả cancelled.
- `COUNT(*) FILTER (WHERE status = 'paid')` chỉ đếm paid.
- `SUM(amount) FILTER (WHERE status = 'paid')` chỉ cộng amount paid.
- `COALESCE(..., 0)` trong ví dụ quy định nhóm **không có paid** được hiển thị doanh thu 0. Với nghiệp vụ khác, thiếu dữ liệu có thể cần giữ `NULL`.

Cách này giúp dashboard vừa hiển thị tổng số giao dịch vừa hiển thị doanh thu paid mà không phải thay đổi tập nguồn theo `WHERE status='paid'` cho tất cả chỉ số.

### 11.1. AVG phải hiểu đúng cấp độ

`AVG(amount)` tính **trung bình giá trị giao dịch** trong nhóm, không phải trung bình doanh thu của các khu vực/kênh. Khi cấp nhóm thay đổi, tập hàng đóng góp cho trung bình cũng thay đổi.

Ví dụ tổng paid là 930 qua 10 giao dịch, nên:

```text
AVG(amount) toàn bộ giao dịch paid = 930 / 10 = 93
```

Đây không phải “trung bình doanh thu mỗi khu vực”:

```text
(400 + 440 + 90) / 3 = 310
```

Cả hai phép tính đều có ý nghĩa riêng, nhưng không tương đương. Muốn trung bình của **những tổng khu vực**, cần tổng hợp theo khu vực trước rồi tính `AVG` trên tập subtotal khu vực phù hợp.

### 11.2. COUNT(DISTINCT ...) và cấp dữ liệu

Nếu dữ liệu nguồn có một hàng trên một **dòng sản phẩm**, nhưng muốn đếm **số đơn**, `COUNT(*)` trong `CUBE` sẽ đếm dòng sản phẩm, không phải đơn. Có thể dùng `COUNT(DISTINCT order_id)` trong từng grouping set hoặc tạo tập đã được chuẩn hóa theo đúng grain của báo cáo.

Ví dụ khái niệm:

```sql
-- Giả sử bảng order_lines có nhiều dòng trên mỗi đơn.
SELECT
    region,
    channel,
    COUNT(DISTINCT order_id) AS distinct_orders,
    SUM(line_amount) AS revenue
FROM order_lines
GROUP BY CUBE (region, channel);
```

`order_lines` là bảng minh họa, **không có trong bộ dữ liệu mẫu**. Nếu một đơn có nhiều kênh/nhóm sản phẩm trong dữ liệu gốc, cùng một order có thể được đếm trong nhiều nhóm chi tiết. Tổng các `COUNT(DISTINCT order_id)` ở các subtotal không nhất thiết bằng grand total do sự chồng lấp đối tượng qua chiều phân nhóm.

Phải biết **mỗi hàng dữ liệu nguồn đại diện cho đối tượng nào** trước khi quyết định dùng `COUNT(*)`, `COUNT(DISTINCT ...)` hoặc tổng tiền.

## 12. Tránh cộng lại subtotal: mỗi cấp đang nhìn cùng dữ liệu

Với hai chiều, `CUBE(region, channel)` tạo bốn grouping sets. Mỗi giao dịch paid trong bài được tính:

1. Một lần trong nhóm `(region, channel)`.
2. Một lần trong nhóm `(region)`.
3. Một lần trong nhóm `(channel)`.
4. Một lần trong `()`.

Vì vậy, nếu cộng **toàn bộ cột revenue của 12 hàng CUBE**, ta thu:

```text
Cấp region + channel: 930
Cấp region:           930
Cấp channel:          930
Cấp tổng chung:       930
--------------------------------
Cộng tất cả các hàng: 3.720
```

`3.720` **không phải doanh thu** của cửa hàng; nó là kết quả cộng nhiều cách nhìn chồng lấp trên cùng 930 đơn vị doanh thu.

Ví dụ truy vấn gây hiểu sai:

```sql
WITH summary AS (
    SELECT
        region,
        channel,
        SUM(amount) AS revenue
    FROM demo_sales_cube
    WHERE status = 'paid'
    GROUP BY CUBE (region, channel)
)
SELECT SUM(revenue) AS wrong_total
FROM summary;
-- 3720.00 trên bộ dữ liệu mẫu
```

Nếu muốn lấy tổng toàn hệ thống từ CUBE, hãy **chọn đúng dòng grand total**:

```sql
WITH summary AS (
    SELECT
        region,
        channel,
        GROUPING(region, channel) AS group_code,
        SUM(amount) AS revenue
    FROM demo_sales_cube
    WHERE status = 'paid'
    GROUP BY CUBE (region, channel)
)
SELECT revenue
FROM summary
WHERE group_code = 3;
-- 930.00
```

Hoặc tính trực tiếp từ bảng nguồn:

```sql
SELECT SUM(amount)
FROM demo_sales_cube
WHERE status = 'paid';
```

### 12.1. Không lấy tổng của subtotal rồi gọi đó là grand total nếu nhóm chồng lấp

Với báo cáo nhiều chiều, subtotal theo region và subtotal theo channel đều bao phủ toàn bộ dữ liệu. Cộng cả hai cho **1.860**, nghĩa là đếm hai lần cùng một dữ liệu.

Ngay cả khi chỉ cộng những hàng có vẻ là “tổng” (`region IS NULL` hoặc `channel IS NULL`), ta vẫn có thể cộng trùng hoặc nhầm với region thật bằng `NULL`. Dùng `group_code` hoặc `level_name` để xác định **một cấp phân chia duy nhất** trước khi cộng.

### 12.2. Khi nào tổng của các nhóm có thể bằng grand total?

Với chỉ số **cộng được** như `SUM(amount)`, nếu các nhóm ở cùng một grouping set tạo thành một **phân hoạch không chồng lấp** của tập nguồn, tổng các nhóm bằng grand total.

Ví dụ theo region:

```text
North 400 + South 440 + Unknown 90 = 930
```

Tương tự theo channel:

```text
Online 540 + Store 390 = 930
```

Nhưng không được cộng **hai phân hoạch khác nhau** với nhau. Với các chỉ số không cộng được hoặc có distinct count qua nhiều chiều, cần xét điều kiện chồng lấp kỹ hơn.

## 13. ORDER BY: trình bày subtotal gần hàng chi tiết

`GROUPING SETS` và `CUBE` không bảo đảm thứ tự kết quả khi thiếu `ORDER BY`. Đặc biệt, các hàng có `NULL` có thể khiến cách sắp xếp mặc định khó đọc.

Nếu muốn bảng hiển thị:

1. Từng khu vực.
2. Các kênh trong khu vực.
3. Subtotal khu vực ngay sau các kênh.
4. Các subtotal theo kênh toàn hệ thống.
5. Grand total cuối cùng.

Có thể viết:

```sql
SELECT
    region,
    channel,
    GROUPING(region) AS region_omitted,
    GROUPING(channel) AS channel_omitted,
    GROUPING(region, channel) AS group_code,
    SUM(amount) AS revenue
FROM demo_sales_cube
WHERE status = 'paid'
GROUP BY CUBE (region, channel)
ORDER BY
    GROUPING(region) ASC,
    region ASC NULLS LAST,
    GROUPING(channel) ASC,
    channel ASC NULLS LAST;
```

Ý nghĩa của các khóa sắp xếp:

- `GROUPING(region) = 0` trước: các cấp còn giữ region ở phía trên.
- `region ... NULLS LAST`: North, South, rồi nhóm region thật chưa biết.
- `GROUPING(channel) = 0` trước: chi tiết theo kênh hiện ra trước subtotal khu vực.
- Khi `GROUPING(region) = 1`, các hàng channel totals xuất hiện trước grand total vì `GROUPING(channel) = 0` đứng trước 1.

Khi đưa kết quả vào API hoặc file báo cáo, nên giữ các cờ cấp nhóm ở dữ liệu trả về, kể cả khi UI chỉ dùng chúng để định dạng.

### 13.1. Tránh dùng nhãn hiển thị làm khóa tổng hợp

Không nên chỉ dựa trên `CASE WHEN region IS NULL THEN 'ALL'`, bởi giá trị `NULL` thật sẽ bị biến thành nhãn tổng chung. Trước tiên tạo grouping sets với khóa gốc và cờ nhóm, **sau đó** mới trình bày nhãn dựa trên `GROUPING`.

Nếu đầu vào có một khu vực thật tên `'ALL REGIONS'`, dùng chuỗi nhãn trực tiếp còn có thể trùng với giá trị nghiệp vụ. Cột `group_code` hoặc cờ Boolean vẫn giúp máy phân biệt đúng.

## 14. Phân nhóm theo tháng và nhiều chiều

Nhiều báo cáo tổng hợp theo **thời gian + vùng + kênh**. Ví dụ tổng tiền paid mỗi tháng theo hai chiều và tổng tháng:

```sql
WITH sales_in_month AS (
    SELECT
        DATE_TRUNC('month', sale_date::timestamp)::date AS month_start,
        region,
        channel,
        amount
    FROM demo_sales_cube
    WHERE status = 'paid'
)
SELECT
    month_start,
    region,
    channel,
    GROUPING(region, channel) AS level_code,
    SUM(amount) AS revenue
FROM sales_in_month
GROUP BY month_start,
         GROUPING SETS (
             (region, channel),
             (region),
             (channel),
             ()
         )
ORDER BY
    month_start,
    level_code,
    region NULLS LAST,
    channel NULLS LAST;
```

Ở đây `month_start` **luôn nằm trong nhóm**, còn region/channel được chọn hoặc lược bỏ theo từng grouping set. Do dữ liệu mẫu chỉ thuộc tháng 5/2025, mọi tổng vẫn gắn với `month_start = 2025-05-01`.

Nếu thay bằng:

```sql
GROUP BY CUBE (month_start, region, channel)
```

thì một số grouping sets **lược bỏ cả tháng**, tạo các tổng xuyên tất cả các tháng. Đó là yêu cầu khác: có thể hữu ích cho báo cáo năm, nhưng không thích hợp nếu mỗi hàng phải có một tháng cụ thể.

### 14.1. Nhóm theo biểu thức cần ghi rõ phạm vi

`GROUPING()` trong PostgreSQL nhận các biểu thức đã xuất hiện trong cấu trúc grouping, với yêu cầu phù hợp về biểu thức. Khi cần nhóm theo biểu thức như `DATE_TRUNC('month', ...)`, cách dùng CTE trước để tạo cột `month_start` rồi nhóm theo tên cột mới thường rõ ràng và ít gây nhầm hơn:

```sql
WITH prepared AS (
    SELECT
        DATE_TRUNC('month', sale_date::timestamp)::date
            AS month_start,
        amount
    FROM demo_sales_cube
)
SELECT
    month_start,
    GROUPING(month_start) AS month_omitted,
    SUM(amount) AS revenue
FROM prepared
GROUP BY GROUPING SETS (
    (month_start),
    ()
);
```

Tập kết quả gồm một dòng tổng tháng và một dòng tổng toàn bộ dữ liệu của tập `prepared`. Do truy vấn này **không lọc `status = 'paid'`**, nó cộng cả hai giao dịch cancelled; nếu muốn doanh thu paid theo quy ước đầu bài, phải thêm bộ lọc trong CTE.

### 14.2. GROUPING SETS không tự tạo tháng trống

Nếu tháng 6 không có giao dịch, `GROUP BY month_start` không tự sinh hàng tháng 6 với doanh thu bằng 0. `CUBE` và `GROUPING SETS` tạo **các cấp tổng hợp của dữ liệu hiện có**, không phải bộ sinh lịch hoặc tất cả tổ hợp chưa có dữ liệu.

Để báo cáo mọi tháng, kể cả tháng không có giao dịch, thường cần:

1. Tập các tháng/kỳ mong muốn (calendar hoặc `generate_series` trong PostgreSQL).
2. Kết quả tổng hợp theo tháng.
3. `LEFT JOIN` từ tập kỳ chuẩn sang kết quả.
4. Quy tắc hiển thị `NULL`/0 rõ ràng.

Tương tự, nếu một kênh chưa xuất hiện tại một khu vực, nhóm chi tiết theo cặp đó không tự được thêm với doanh thu 0. Muốn “hiển thị đủ lưới vùng × kênh”, phải có bảng chiều/tổ hợp chuẩn và phép nối thích hợp.

## 15. GROUPING SETS trong báo cáo nhiều chiều thực tế

Giả sử người quản lý muốn bốn thành phần sau trong **một lần lấy dữ liệu**:

- Doanh thu theo `region, channel` để xem hoạt động từng kênh tại từng khu vực.
- Doanh thu theo `region, product_group` để xem cơ cấu sản phẩm từng khu vực.
- Doanh thu theo `product_group` để biết tổng cơ cấu sản phẩm.
- Grand total để đối soát doanh thu toàn hệ thống.

Yêu cầu này **không cần mọi cấp** của CUBE ba chiều, nên sử dụng grouping sets tường minh:

```sql
WITH paid_sales AS (
    SELECT
        region,
        channel,
        product_group,
        amount
    FROM demo_sales_cube
    WHERE status = 'paid'
),
report AS (
    SELECT
        region,
        channel,
        product_group,
        GROUPING(region, channel, product_group) AS group_code,
        COUNT(*) AS sale_count,
        SUM(amount) AS revenue
    FROM paid_sales
    GROUP BY GROUPING SETS (
        (region, channel),
        (region, product_group),
        (product_group),
        ()
    )
)
SELECT
    CASE group_code
        WHEN 1 THEN 'region_channel'
        WHEN 2 THEN 'region_product'
        WHEN 6 THEN 'product'
        WHEN 7 THEN 'grand_total'
    END AS report_level,
    region,
    channel,
    product_group,
    sale_count,
    revenue
FROM report
ORDER BY
    group_code,
    region NULLS LAST,
    channel NULLS LAST,
    product_group NULLS LAST;
```

Giải thích mã:

| Grouping set | Các chiều bị lược bỏ | Nhị phân | `group_code` |
| --- | --- | --- | ---: |
| `(region, channel)` | product_group | `001` | 1 |
| `(region, product_group)` | channel | `010` | 2 |
| `(product_group)` | region, channel | `110` | 6 |
| `()` | cả ba chiều | `111` | 7 |

Với cấp `region_product`, một số nhóm cụ thể:

| `region` | `product_group` | `revenue` |
| --- | --- | ---: |
| North | Books | 180 |
| North | Tech | 220 |
| South | Books | 150 |
| South | Tech | 290 |
| `NULL` (chưa biết) | Books | 50 |
| `NULL` (chưa biết) | Tech | 40 |

Tổng các nhóm `region_product` là:

```text
180 + 220 + 150 + 290 + 50 + 40 = 930
```

Cấp `product` trả Books 380 và Tech 550; cấp grand total trả 930. Các tổng này **đối soát nhau** nhưng không được cộng chung vào một số doanh thu duy nhất.

### 15.1. Nên trả thêm metadata nào cho dashboard?

Ngoài khóa chiều và aggregate, một API báo cáo nhiều cấp nên cân nhắc trả:

| Trường | Ý nghĩa |
| --- | --- |
| `group_code` | Xác định các chiều bị lược bỏ |
| `report_level` | Tên cấp tổng hợp rõ ràng |
| `region` / `channel` / `product_group` | Khóa chiều gốc, có thể chứa `NULL` thật |
| `revenue` | Số liệu đã tính cho cấp hiện tại |
| `sale_count` | Số giao dịch đóng góp vào cấp hiện tại |
| `as_of` hoặc `period_start/end` | Phạm vi thời gian thống nhất cho báo cáo |
| `currency_code` nếu cần | Đơn vị tiền tệ để tránh cộng tiền khác đơn vị |

Nhãn `ALL REGIONS` hoặc `Unknown region` là vấn đề hiển thị; mã cấp và khóa dữ liệu mới giúp các thành phần của hệ thống phân biệt ý nghĩa ổn định.

## 16. Những góc cạnh ít được chú ý

### 16.1. Hai grouping sets giống nhau có thể tạo hàng lặp

Ví dụ về yêu cầu trùng cấp:

```sql
SELECT region, SUM(amount) AS revenue
FROM demo_sales_cube
WHERE status = 'paid'
GROUP BY GROUPING SETS (
    (region),
    (region)
);
```

Trong PostgreSQL, các grouping set trùng nhau có thể tạo ra những hàng kết quả lặp cho cùng một giá trị region. Điều này khác với một phép `GROUP BY region` đơn giản.

Không mặc định `GROUPING SETS` tự loại bỏ mọi cấp trùng. Khi ghép `ROLLUP`, `CUBE` và các grouping item khác, cần nhận biết nguy cơ sinh cùng một tập cột nhóm nhiều lần. Nếu bài toán không muốn lặp, hãy diễn đạt các cấp duy nhất hoặc áp dụng cơ chế loại bỏ tập nhóm trùng được hệ quản trị hỗ trợ theo ngữ cảnh.

### 16.2. GROUPING() không được dùng tùy ý như một hàm hàng thường

`GROUPING(region)` chỉ có ý nghĩa trong ngữ cảnh grouping phù hợp. Không thể thay `GROUPING()` bằng `IS NULL` và cũng không thể gọi nó trên một biểu thức bất kỳ không thuộc các biểu thức nhóm được khai báo theo quy tắc PostgreSQL.

Ví dụ đúng:

```sql
SELECT
    region,
    GROUPING(region) AS region_omitted,
    SUM(amount) AS revenue
FROM demo_sales_cube
WHERE status = 'paid'
GROUP BY GROUPING SETS ((region), ());
```

Những ví dụ truyền sai biểu thức nhóm có thể bị PostgreSQL từ chối; vì thế nên dùng alias CTE khi cần nhóm theo biểu thức tính toán phức tạp.

### 16.3. Một grouping set rỗng vẫn có hành vi aggregate trên tập đầu vào rỗng

Với `WHERE` không giữ hàng nào:

```sql
SELECT
    COUNT(*) AS row_count,
    SUM(amount) AS amount_sum
FROM demo_sales_cube
WHERE status = 'paid'
  AND sale_date < DATE '2000-01-01'
GROUP BY GROUPING SETS (());
```

Nhóm tổng chung `()` có thể vẫn trả **một hàng** với `COUNT(*) = 0` và `SUM(amount) = NULL`, theo ngữ nghĩa aggregate trên tập rỗng. Các nhóm theo cột thông thường không có khóa nhóm hiện hữu nên không tạo các hàng chi tiết.

Đây là lý do cần phân biệt:

- **0 hàng trong kết quả**: không có nhóm nào được tạo ở cấp đó.
- **1 hàng tổng có `COUNT(*) = 0`**: nhóm tổng rỗng đã được biểu diễn.
- **`SUM(amount) = NULL`**: không có giá trị số để cộng theo quy tắc `SUM`; không mặc định là 0 nếu chưa có quy tắc hiển thị.

### 16.4. DISTINCT không phải cách chữa mọi kết quả trùng

Nếu query tạo ra hai hàng giống nhau từ các grouping sets trùng, `SELECT DISTINCT` có thể làm chúng gộp lại, nhưng không giải thích được **vì sao** trùng. Tệ hơn, một số hàng ở **cấp khác nhau** có thể có cùng giá trị hiển thị và cùng số tiền (nhất là với `NULL` thật hoặc chỉ một kênh), nên loại trùng có thể xóa mất cấp báo cáo cần giữ.

Cách đúng là xác định **bộ grouping sets mong muốn** và giữ cờ `GROUPING`/`group_code`. Chỉ dùng `DISTINCT` nếu nghiệp vụ thật sự muốn loại các hàng trùng theo chính những cột đang chọn.

### 16.5. Ràng buộc trình bày trong BI

Nếu công cụ BI nhận dữ liệu `CUBE` mà không biết hàng nào là grand total, công cụ có thể tự tổng hợp lần nữa và báo sai số liệu. Một giải pháp là cung cấp **level metadata** rõ ràng và chỉ cho phép hệ thống tổng hợp tiếp trong phạm vi phù hợp.

Ví dụ, không nên đưa tất cả 12 hàng `CUBE` vào một biểu đồ cột rồi để công cụ tự `SUM(revenue)` cho nhãn “Tất cả”; kết quả có thể bị nhân nhiều lần. Thay vào đó chọn `group_code = 0` cho biểu đồ theo từng cặp, `group_code = 1` cho biểu đồ khu vực, `group_code = 2` cho biểu đồ kênh, hoặc `group_code = 3` cho KPI tổng.

## 17. Hiệu năng và khả năng mở rộng

`CUBE` và `GROUPING SETS` giúp diễn đạt logic gọn, nhưng không miễn phí. Chi phí tùy vào:

- Số grouping sets được tạo.
- Số tổ hợp giá trị có thật ở mỗi cấp.
- Số lượng hàng nguồn và độ chọn lọc của `WHERE`.
- Số aggregate, đặc biệt những aggregate tốn bộ nhớ như `COUNT(DISTINCT ...)`.
- Kích thước dữ liệu trung gian, sắp xếp/hash aggregate, khả năng tràn đĩa.
- Cách hệ quản trị tối ưu hoặc thực thi các grouping sets.

### 17.1. Tránh CUBE trên quá nhiều chiều không cần thiết

`CUBE` 10 chiều tạo 1.024 grouping sets. Nếu báo cáo chỉ dùng cấp theo 3 tổ hợp được xác định trước, `GROUPING SETS` với 3 mục là cách diễn đạt sát yêu cầu hơn và có thể giảm khối lượng xử lý.

Một thiết kế thường gặp:

```sql
-- Tập cấp chọn lọc:
GROUP BY GROUPING SETS (
    (month_start, region, channel),
    (month_start, region),
    (month_start),
    ()
)
```

Thay vì:

```sql
-- Có thể tạo nhiều cấp không dùng tới:
GROUP BY CUBE (month_start, region, channel, product_group, seller_id)
```

Cách đầu cung cấp bốn cấp rõ ràng. Cách sau tạo 32 grouping sets với 5 chiều, có thể gồm nhiều subtotal không nằm trong yêu cầu.

### 17.2. Lọc sớm nhưng đúng nghiệp vụ

Nếu báo cáo chỉ tính đơn paid trong năm 2025, nên xác định tập nguồn trước:

```sql
WITH filtered AS (
    SELECT region, channel, amount
    FROM demo_sales_cube
    WHERE status = 'paid'
      AND sale_date >= DATE '2025-01-01'
      AND sale_date <  DATE '2026-01-01'
)
SELECT
    region,
    channel,
    SUM(amount) AS revenue
FROM filtered
GROUP BY CUBE (region, channel);
```

Bộ lọc hạn chế dữ liệu được đưa vào mọi cấp tổng hợp. Nhưng nếu báo cáo cần **cùng lúc số cancelled và doanh thu paid**, lọc `status='paid'` quá sớm sẽ làm mất số cancelled; lúc đó dùng aggregate `FILTER` theo từng chỉ số như phần trước.

“Lọc sớm” chỉ đúng khi **đúng định nghĩa phạm vi dữ liệu của tất cả chỉ số**.

### 17.3. Không giả định index luôn giúp GROUPING SETS nhanh

Index trên `(region, channel)` có thể hữu ích với một số bộ lọc hoặc cách đọc, nhưng `CUBE` cần nhiều tổ hợp phân nhóm không cùng thứ tự. Optimizer có thể chọn các phương án sort/hash khác nhau. Việc thêm index không đảm bảo tất cả grouping sets đều được tăng tốc.

Để quan sát kế hoạch của một câu `SELECT` PostgreSQL:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    region,
    channel,
    SUM(amount)
FROM demo_sales_cube
WHERE status = 'paid'
GROUP BY CUBE (region, channel);
```

`EXPLAIN ANALYZE` thực thi truy vấn để đo số hàng và thời gian; ở đây truy vấn chỉ đọc. Với dữ liệu production hoặc truy vấn tốn tài nguyên, nên dùng môi trường/giới hạn phù hợp và quan sát bộ nhớ, I/O, thời gian và số nhóm trả về.

### 17.4. Khi nên tiền tổng hợp

Nếu dữ liệu giao dịch hàng trăm triệu hàng nhưng dashboard chỉ cần báo cáo theo tháng và khu vực, có thể cân nhắc:

1. Tổng hợp giao dịch thành một **bảng trung gian ở đúng grain** (ví dụ một hàng theo ngày–khu vực–kênh–loại sản phẩm).
2. Dùng `GROUPING SETS` trên tập trung gian đó để tạo subtotal nhanh hơn.
3. Quản lý cập nhật tăng dần, sự kiện tới trễ, sửa/xóa giao dịch và đối soát với dữ liệu nguồn.

Tiền tổng hợp chỉ an toàn khi các chỉ số có thể cộng qua các cấp mới. Ví dụ `SUM(amount)` cộng được; nhưng `COUNT(DISTINCT customer_id)` qua các nhóm trung gian có thể **không cộng được** nếu cùng khách xuất hiện ở nhiều nhóm.

## 18. Phân biệt SQL nhiều chiều với GROUP BY trên bảng JOIN

Một báo cáo thường phải `JOIN` bảng giao dịch với bảng khu vực, sản phẩm hoặc người bán trước khi tổng hợp.

Ví dụ bảng giao dịch có mỗi hàng một sản phẩm bán, còn bảng nhãn danh mục có nhiều phiên bản mô tả cho cùng sản phẩm. Nếu `JOIN` không có điều kiện xác định **đúng một phiên bản danh mục** cho mỗi dòng giao dịch, một giao dịch có thể nhân thành hai hàng trước khi vào `CUBE`.

Khi đó doanh thu ở **tất cả cấp tổng hợp** có thể bị nhân đôi. `GROUPING SETS` không sửa được lỗi đó.

Trình tự thiết kế nên là:

```text
Xác định grain dữ liệu nguồn
    ↓
JOIN với các bảng chiều có quan hệ đúng cấp, tránh nhân hàng ngoài ý muốn
    ↓
Lọc giao dịch theo định nghĩa nghiệp vụ
    ↓
Tính chỉ số ở grain nguồn phù hợp
    ↓
GROUPING SETS hoặc CUBE
    ↓
Gắn cờ cấp nhóm và nhãn hiển thị
    ↓
Đối soát từng cấp với tổng nguồn
```

Nếu cùng một hóa đơn có nhiều dòng và muốn tính **số đơn duy nhất**, phải đặc biệt cẩn thận với `COUNT(DISTINCT ...)` và các nhóm chồng lấp. Đừng lấy việc grand total bằng một số mong đợi làm bằng chứng duy nhất; lỗi cộng thừa và cộng thiếu có thể bù trừ nhau.

## 19. Khác biệt giữa các hệ quản trị SQL

Các hệ quản trị không hỗ trợ đồng nhất mọi dạng grouping.

| Hệ quản trị | Khả năng và lưu ý |
| --- | --- |
| **PostgreSQL** | Hỗ trợ `GROUPING SETS`, `ROLLUP`, `CUBE` và `GROUPING(...)`; bitmask được xác định theo thứ tự đối số. Ví dụ chính của bài dùng cú pháp PostgreSQL. |
| **SQL Server** | Hỗ trợ `GROUPING SETS`, `ROLLUP`, `CUBE`, `GROUPING` và `GROUPING_ID`; cú pháp tính mã nhóm và quy tắc đầu ra cần xem tài liệu SQL Server. |
| **Oracle Database** | Có `ROLLUP`, `CUBE`, `GROUPING SETS` và các hàm `GROUPING`/`GROUPING_ID` phục vụ báo cáo nhiều chiều. |
| **MySQL** | Có hỗ trợ `WITH ROLLUP`/`ROLLUP` theo cú pháp, phiên bản; không mặc định hỗ trợ đầy đủ `CUBE`/`GROUPING SETS` như PostgreSQL. Có thể cần nhiều `GROUP BY` và `UNION ALL`. |
| **SQLite** | Không có cú pháp `CUBE`/`GROUPING SETS` tương đương PostgreSQL; có thể diễn đạt nhiều cấp tổng hợp bằng các truy vấn `GROUP BY` riêng ghép `UNION ALL`. |

Các hệ phân tích như BigQuery, DuckDB hoặc các kho dữ liệu cloud cũng có hỗ trợ nhiều chiều ở những phiên bản/cấu hình tương ứng, nhưng cú pháp và giới hạn có thể thay đổi. Khi triển khai đa hệ, cần xác minh tính năng của **phiên bản DBMS đang chạy** thay vì sao chép nguyên một câu lệnh.

### 19.1. Mẫu thay thế bằng UNION ALL khi không có GROUPING SETS

Với công cụ SQL chỉ hỗ trợ `GROUP BY` thông thường:

```sql
SELECT
    region,
    channel,
    'detail' AS level_name,
    SUM(amount) AS revenue
FROM demo_sales_cube
WHERE status = 'paid'
GROUP BY region, channel

UNION ALL

SELECT
    region,
    NULL AS channel,
    'region_total' AS level_name,
    SUM(amount) AS revenue
FROM demo_sales_cube
WHERE status = 'paid'
GROUP BY region

UNION ALL

SELECT
    NULL AS region,
    NULL AS channel,
    'grand_total' AS level_name,
    SUM(amount) AS revenue
FROM demo_sales_cube
WHERE status = 'paid';
```

Đoạn này chỉ chọn **ba cấp**: detail, region total và grand total. Nếu cần channel total, thêm một nhánh `GROUP BY channel` tương ứng.

Khi dùng `UNION ALL`, nên khai báo và ép kiểu `NULL` thống nhất nếu hệ quản trị yêu cầu, đồng thời đặt chuỗi `level_name` hoặc mã cấp để không nhầm `NULL` thật với cột bị lược bỏ. Không dùng `UNION` thay `UNION ALL` một cách tùy tiện: `UNION` loại những hàng có giá trị giống nhau theo danh sách cột kết quả, có thể làm mất các cấp báo cáo mong muốn nếu không có metadata phân biệt.

## 20. Bài tập thực hành có lời giải

Các bài dùng bảng `demo_sales_cube` đã tạo ở phần 2. Nên dự đoán cấp nhóm và tổng tiền bằng bảng dữ liệu paid trước khi chạy câu SQL.

### Bài 1 — Đếm số nhóm chi tiết

```sql
SELECT region, channel, SUM(amount) AS revenue
FROM demo_sales_cube
WHERE status = 'paid'
GROUP BY region, channel;
```

**Câu hỏi:** Có bao nhiêu hàng, và tổng doanh thu nếu cộng những nhóm cùng cấp?

**Đáp án:** Có 6 hàng chi tiết: North–Online 250, North–Store 150, South–Online 240, South–Store 200, Unknown–Online 50, Unknown–Store 40. Tổng ở **một cấp nhóm chi tiết** là 930.

### Bài 2 — GROUPING SETS gồm những cấp nào?

```sql
SELECT region, channel, SUM(amount) AS revenue
FROM demo_sales_cube
WHERE status = 'paid'
GROUP BY GROUPING SETS (
    (region, channel),
    (region),
    ()
);
```

**Đáp án:** Ba cấp: theo cặp khu vực–kênh (6 hàng), theo khu vực (3 hàng), tổng chung (1 hàng). Tổng cộng **10 hàng**. Không có subtotal theo kênh toàn hệ thống vì `(channel)` không được liệt kê.

### Bài 3 — CUBE có thêm cấp nào so với ROLLUP?

```sql
GROUP BY CUBE (region, channel)
```

so với:

```sql
GROUP BY ROLLUP (region, channel)
```

**Đáp án:** CUBE bổ sung grouping set `(channel)` mà ROLLUP không tạo. Trên dữ liệu mẫu, đó là hai dòng Online 540 và Store 390. Vì vậy CUBE trả 12 hàng, ROLLUP trả 10 hàng, khi chỉ lọc paid.

### Bài 4 — NULL thật hay subtotal?

Giả sử một hàng kết quả có:

```text
region = NULL
channel = Online
revenue = 50
```

và hàng khác:

```text
region = NULL
channel = Online
revenue = 540
```

**Đáp án:** Hàng 50 là nhóm chi tiết có region thật chưa biết: `GROUPING(region, channel) = 0`. Hàng 540 là subtotal Online trên **mọi khu vực**: `GROUPING(region, channel) = 2`. Chỉ kiểm tra `region IS NULL` không đủ để phân biệt.

### Bài 5 — Ý nghĩa của mã GROUPING

Với `GROUPING(region, channel)`, giải thích các mã 0, 1, 2, 3.

**Đáp án:**

- 0: cả region và channel đều thuộc nhóm.
- 1: bỏ channel, giữ region.
- 2: bỏ region, giữ channel.
- 3: bỏ cả hai, tổng chung.

Đối số bên phải của `GROUPING` tương ứng bit thấp nhất.

### Bài 6 — Lấy duy nhất tổng theo kênh

Viết truy vấn lấy Online và Store từ CUBE, không lấy detail, subtotal region hay grand total.

```sql
SELECT
    channel,
    SUM(amount) AS revenue
FROM demo_sales_cube
WHERE status = 'paid'
GROUP BY CUBE (region, channel)
HAVING GROUPING(region, channel) = 2
ORDER BY channel;
```

**Đáp án:** Online 540, Store 390. Mã 2 nghĩa là region bị lược bỏ và channel vẫn thuộc nhóm.

### Bài 7 — Tại sao tổng các hàng CUBE là 3.720?

```sql
WITH report AS (
    SELECT region, channel, SUM(amount) AS revenue
    FROM demo_sales_cube
    WHERE status = 'paid'
    GROUP BY CUBE (region, channel)
)
SELECT SUM(revenue) FROM report;
```

**Đáp án:** Mỗi giao dịch paid được tính một lần trong mỗi **bốn grouping sets**. `930 × 4 = 3.720`. Đây là cộng chồng lấp, không phải doanh thu thực. Muốn doanh thu tổng, chọn dòng `GROUPING(region, channel) = 3`.

### Bài 8 — Tổng theo khu vực và nhóm sản phẩm

```sql
SELECT
    region,
    product_group,
    SUM(amount) AS revenue
FROM demo_sales_cube
WHERE status = 'paid'
GROUP BY region, product_group
ORDER BY region NULLS LAST, product_group;
```

**Đáp án:** North–Books 180, North–Tech 220, South–Books 150, South–Tech 290, Unknown–Books 50, Unknown–Tech 40. Có 6 hàng. Tổng cùng cấp là 930.

### Bài 9 — Chọn một số grouping sets thay vì CUBE ba chiều

Yêu cầu bốn cấp: `(region,channel)`, `(region,product_group)`, `(product_group)`, `()`. Viết cấu trúc `GROUP BY`.

**Đáp án:**

```sql
GROUP BY GROUPING SETS (
    (region, channel),
    (region, product_group),
    (product_group),
    ()
)
```

Cấu trúc này tạo 15 hàng trên dữ liệu mẫu (6 + 6 + 2 + 1), không tạo những cấp không được yêu cầu.

### Bài 10 — HAVING khác WHERE

Muốn báo cáo **tất cả giao dịch paid** nhưng chỉ hiển thị những nhóm chi tiết `region/channel` có doanh thu từ 200, viết:

```sql
SELECT
    region,
    channel,
    SUM(amount) AS revenue
FROM demo_sales_cube
WHERE status = 'paid'
GROUP BY CUBE (region, channel)
HAVING GROUPING(region, channel) = 0
   AND SUM(amount) >= 200
ORDER BY region NULLS LAST, channel;
```

**Đáp án:** North–Online 250; South–Online 240; South–Store 200. Nếu chỉ dùng `HAVING SUM(amount) >= 200` mà không lọc mã nhóm, các subtotal và grand total đủ ngưỡng cũng xuất hiện.

### Bài 11 — COUNT(*) khác doanh thu paid

```sql
SELECT
    GROUPING(region, channel) AS group_code,
    COUNT(*) AS all_count,
    COUNT(*) FILTER (WHERE status = 'paid') AS paid_count,
    SUM(amount) FILTER (WHERE status = 'paid') AS paid_amount
FROM demo_sales_cube
GROUP BY CUBE (region, channel)
HAVING GROUPING(region, channel) = 3;
```

**Đáp án:** Một dòng grand total: `all_count = 12`, `paid_count = 10` và `paid_amount = 930`. `COUNT(*)` không tự lọc cancelled; bộ lọc từng chỉ số nằm trong `FILTER`.

### Bài 12 — Mười chiều có bao nhiêu grouping sets?

Một yêu cầu dùng:

```sql
GROUP BY CUBE (
    dim1, dim2, dim3, dim4, dim5,
    dim6, dim7, dim8, dim9, dim10
)
```

**Đáp án:** `2^10 = 1.024` grouping sets. Chưa thể suy ra chính xác số hàng kết quả nếu không biết số giá trị và các tổ hợp dữ liệu thực tế. Nếu báo cáo chỉ cần vài cấp, nên chọn `GROUPING SETS` tường minh.

### Bài 13 — Có GROUPING SETS thì tự sinh nhóm tháng không có doanh số?

Tháng 6 không có bất kỳ giao dịch nào. `GROUP BY month_start, GROUPING SETS((region),())` có tự tạo hàng cho tháng 6 không?

**Đáp án:** Không. Các grouping set chỉ tổng hợp những nhóm có trong dữ liệu đầu vào; muốn tháng 6 hiển thị 0 cần một bảng/tập lịch tháng và `LEFT JOIN` với kết quả tổng hợp, kèm quy tắc thay `NULL` bằng 0 khi phù hợp.

### Bài 14 — Một grouping set xuất hiện hai lần

```sql
GROUP BY GROUPING SETS (
    (region),
    (region)
)
```

**Đáp án:** Trong PostgreSQL, các cấp lặp có thể sinh các hàng kết quả lặp; đây không tự động là hai vùng khác nhau. Cần sửa danh sách grouping sets để chỉ yêu cầu cấp `(region)` một lần khi nghiệp vụ không cần lặp.

## 21. Quy trình thiết kế báo cáo nhiều cấp

Khi được giao một báo cáo có tổng theo nhiều chiều, nên đi theo thứ tự sau:

1. **Xác định grain của dữ liệu gốc.** Một hàng là giao dịch, dòng sản phẩm, đơn hàng hay khách? Các phép `JOIN` có thay đổi grain không?
2. **Định nghĩa chỉ số trước.** Doanh thu lấy trạng thái nào, tính ở cấp nào, có giá trị `NULL`, hoàn tiền hay nhiều loại tiền tệ không?
3. **Liệt kê những cấp báo cáo thực sự cần.** Viết danh sách như `(region,channel)`, `(region)`, `(channel)`, `()` ra giấy.
4. **Chọn cú pháp.** Một cấp: `GROUP BY`; hệ phân cấp: `ROLLUP`; mọi tổ hợp: `CUBE`; tập cấp chọn lọc: `GROUPING SETS`.
5. **Gắn metadata cấp nhóm.** Dùng `GROUPING(...)` để biết cột nào bị lược bỏ; không đoán từ `IS NULL`.
6. **Xử lý giá trị NULL thật.** Phân biệt nhóm dữ liệu chưa biết với subtotal; chỉ tạo nhãn trình bày sau khi biết cấp nhóm.
7. **Đối chiếu mỗi cấp với nguồn.** Từng phân hoạch đầy đủ phải khớp grand total đối với chỉ số cộng được; không cộng subtotal chồng lấp.
8. **Kiểm soát lọc.** `WHERE` lọc đầu vào của mọi nhóm; `HAVING` lọc hàng tổng hợp; `FILTER` xác định tập đóng góp của từng aggregate.
9. **Sắp xếp đầu ra có chủ đích.** Dùng `ORDER BY` với `GROUPING`/mã cấp và các khóa chiều, không dựa vào thứ tự mặc định.
10. **Đánh giá kích thước và hiệu năng.** Số cấp của `CUBE` tăng theo `2^n`; chọn `GROUPING SETS` khi chỉ cần vài tổ hợp, kiểm tra kế hoạch thực thi và cân nhắc tiền tổng hợp đúng grain.

Bản chất của **`GROUPING SETS`** là cho phép nhiều định nghĩa “một nhóm” cùng tồn tại trong một kết quả; bản chất của **`CUBE`** là tự sinh tất cả cách giữ/bỏ những chiều đã cho. Khi hiểu chính xác **cấp tổng hợp**, **cờ `GROUPING`**, **`NULL` thật** và **sự chồng lấp subtotal**, bạn có thể xây dựng báo cáo nhiều chiều có thể giải thích và đối soát mà không vô tình đếm cùng dữ liệu nhiều lần.

