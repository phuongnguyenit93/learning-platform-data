# SUM, AVG, COUNT trên cửa sổ

Trong báo cáo SQL, đôi khi ta muốn biết **tổng doanh thu của cả khu vực** ngay bên cạnh **từng giao dịch**; hoặc muốn xem **tổng lũy kế**, **trung bình ba giao dịch gần nhất**, **số hàng trong từng nhóm** mà **không gộp các giao dịch lại thành một hàng**.

`GROUP BY` có thể tổng hợp, nhưng thường **rút nhiều hàng về một hàng trên mỗi nhóm**. Hàm tổng hợp cửa sổ (*window aggregate*) giải quyết nhu cầu khác: tính `SUM`, `AVG`, `COUNT` trên một **cửa sổ các hàng liên quan**, đồng thời **giữ mỗi hàng của kết quả đầu vào**.

Ba dạng tiêu biểu:

```sql
SUM(amount)  OVER (PARTITION BY region)
AVG(amount)  OVER (PARTITION BY region)
COUNT(*)     OVER (PARTITION BY region)
```

Bài học thuộc chương **Hàm cửa sổ** của Database SQL. Ví dụ chính sử dụng **PostgreSQL** và nhấn mạnh ba quyết định ảnh hưởng trực tiếp đến kết quả:

1. **`PARTITION BY`**: mỗi hàng so sánh với những hàng nào?
2. **`ORDER BY` bên trong `OVER`**: hàng được xét theo trình tự nào?
3. **Khung cửa sổ (*window frame*)**: từ tập đã phân vùng và sắp xếp, những hàng cụ thể nào được đưa vào phép tổng hợp cho hàng hiện tại?

Đặc biệt, phải phân biệt tổng **toàn phân vùng** với tổng **lũy kế**, trung bình **mọi giao dịch** với trung bình **cửa sổ trượt**, và `COUNT(*)` với `COUNT(cột)` khi dữ liệu có `NULL`.

## 1. Bắt đầu từ bài toán: nhìn từng hàng cùng với số liệu tổng

Giả sử bảng bán hàng có các giao dịch thuộc khu vực North và South. Một màn hình muốn hiển thị:

| Giao dịch | Khu vực | Tiền giao dịch | Tổng tiền khu vực |
| ---: | --- | ---: | ---: |
| 1 | North | 100 | 600 |
| 2 | North | 200 | 600 |
| 3 | North | 50 | 600 |
| … | … | … | … |
| 8 | South | 80 | 500 |
| 9 | South | 120 | 500 |

Số tiền giao dịch khác nhau, nhưng **tổng khu vực** được lặp lại bên cạnh từng giao dịch thuộc khu vực đó. Nếu dùng:

```sql
SELECT region, SUM(amount)
FROM sales
GROUP BY region;
```

ta chỉ có một hàng cho North và một hàng cho South, mất danh sách từng giao dịch. Một cách là tính tổng rồi `JOIN` lại bảng gốc; cách trực tiếp hơn là:

```sql
SELECT
    sale_id,
    region,
    amount,
    SUM(amount) OVER (PARTITION BY region) AS region_total
FROM sales;
```

`OVER` chuyển phép `SUM` thông thường thành **phép tổng hợp cửa sổ**. Mỗi hàng gốc vẫn hiện diện, nhưng nó mang thêm một giá trị tính từ các hàng thuộc cùng phân vùng.

### 1.1. Cửa sổ không phải là một bảng khác

Trong ngữ cảnh này, “cửa sổ” là **tập hàng dùng để tính giá trị cho hàng hiện tại**. Nó có thể là:

- Toàn bộ những hàng cùng `region`.
- Những hàng đã xuất hiện **từ đầu phân vùng đến hàng hiện tại**.
- Ba hàng gần nhất theo một thứ tự rõ ràng.
- Các hàng trong khoảng thời gian cách ngày hiện tại không quá hai ngày.
- Những hàng cùng một giá trị khóa sắp xếp (*peers*).

Cửa sổ **không phải** một bảng cần tạo bằng DDL và cũng không mặc nhiên là một khoảng thời gian. `SUM`, `AVG` và `COUNT` có thể nhìn các tập hàng khác nhau tùy cấu trúc `OVER`.

## 2. Bộ dữ liệu thực hành

Chạy các câu SQL sau trong một phiên PostgreSQL. Bảng tạm chỉ phục vụ ví dụ học tập và không đụng đến bảng ứng dụng.

```sql
CREATE TEMP TABLE demo_sales_window (
    sale_id       INTEGER PRIMARY KEY,
    sold_on       DATE NOT NULL,
    region        TEXT NOT NULL,
    salesperson   TEXT NOT NULL,
    amount        NUMERIC(12, 2),
    status        TEXT NOT NULL
        CHECK (status IN ('paid', 'pending', 'cancelled')),
    CHECK (amount IS NULL OR amount >= 0)
);

INSERT INTO demo_sales_window
    (sale_id, sold_on, region, salesperson, amount, status)
VALUES
    ( 1, DATE '2025-05-01', 'North', 'An',   100.00, 'paid'),
    ( 2, DATE '2025-05-01', 'North', 'Binh', 200.00, 'paid'),
    ( 3, DATE '2025-05-02', 'North', 'An',    50.00, 'paid'),
    ( 4, DATE '2025-05-03', 'North', 'Binh',   NULL, 'paid'),
    ( 5, DATE '2025-05-03', 'North', 'An',   150.00, 'paid'),
    ( 6, DATE '2025-05-04', 'North', 'An',    90.00, 'pending'),
    ( 7, DATE '2025-05-05', 'North', 'Binh', 100.00, 'paid'),
    ( 8, DATE '2025-05-01', 'South', 'Chi',   80.00, 'paid'),
    ( 9, DATE '2025-05-02', 'South', 'Dung', 120.00, 'paid'),
    (10, DATE '2025-05-02', 'South', 'Chi',   40.00, 'paid'),
    (11, DATE '2025-05-03', 'South', 'Dung',  60.00, 'paid'),
    (12, DATE '2025-05-04', 'South', 'Chi',  110.00, 'cancelled'),
    (13, DATE '2025-05-05', 'South', 'Dung', 100.00, 'paid'),
    (14, DATE '2025-05-06', 'South', 'Chi',  100.00, 'paid'),
    (15, DATE '2025-05-07', 'South', 'Dung',   NULL, 'paid');
```

Trong bài này, “doanh thu” được quy ước là **tổng `amount` của các hàng `paid` có giá trị tiền được ghi nhận**. Hai giao dịch `paid` mang `amount = NULL` được xem là **chưa biết số tiền**, không tự động đổi thành 0. Giao dịch `pending` và `cancelled` không đóng góp vào doanh thu đã thanh toán.

### 2.1. Tập dữ liệu paid

```sql
SELECT sale_id, sold_on, region, salesperson, amount
FROM demo_sales_window
WHERE status = 'paid'
ORDER BY region, sold_on, sale_id;
```

| `sale_id` | `sold_on` | `region` | `salesperson` | `amount` |
| ---: | --- | --- | --- | ---: |
| 1 | 2025-05-01 | North | An | 100 |
| 2 | 2025-05-01 | North | Binh | 200 |
| 3 | 2025-05-02 | North | An | 50 |
| 4 | 2025-05-03 | North | Binh | `NULL` |
| 5 | 2025-05-03 | North | An | 150 |
| 7 | 2025-05-05 | North | Binh | 100 |
| 8 | 2025-05-01 | South | Chi | 80 |
| 9 | 2025-05-02 | South | Dung | 120 |
| 10 | 2025-05-02 | South | Chi | 40 |
| 11 | 2025-05-03 | South | Dung | 60 |
| 13 | 2025-05-05 | South | Dung | 100 |
| 14 | 2025-05-06 | South | Chi | 100 |
| 15 | 2025-05-07 | South | Dung | `NULL` |

Tổng số **hàng paid** là 13. Trong đó có 11 hàng có `amount` khác `NULL`.

### 2.2. Những con số đối chiếu quan trọng

North có 6 hàng paid, 5 hàng có số tiền:

```text
100 + 200 + 50 + 150 + 100 = 600
AVG(amount) = 600 / 5 = 120
```

South có 7 hàng paid, 6 hàng có số tiền:

```text
80 + 120 + 40 + 60 + 100 + 100 = 500
AVG(amount) = 500 / 6 ≈ 83.3333
```

Toàn bộ:

```text
Tổng doanh thu paid             = 600 + 500 = 1.100
Số hàng paid                    = 6 + 7 = 13
Số hàng paid có amount khác NULL = 5 + 6 = 11
Trung bình số tiền đã biết      = 1.100 / 11 = 100
```

Các con số này giúp ta hiểu vì sao `COUNT(*)` và `COUNT(amount)` khác nhau và vì sao `AVG(amount)` không chia cho tất cả 13 hàng.

## 3. Nhắc lại SUM, AVG, COUNT với GROUP BY

Trước tiên, tổng hợp dữ liệu paid bằng `GROUP BY` thông thường:

```sql
SELECT
    region,
    SUM(amount) AS revenue,
    AVG(amount) AS average_known_amount,
    COUNT(*) AS paid_rows,
    COUNT(amount) AS known_amount_rows
FROM demo_sales_window
WHERE status = 'paid'
GROUP BY region
ORDER BY region;
```

Kết quả:

| `region` | `revenue` | `average_known_amount` | `paid_rows` | `known_amount_rows` |
| --- | ---: | ---: | ---: | ---: |
| North | 600.00 | 120.00 | 6 | 5 |
| South | 500.00 | khoảng 83.33 | 7 | 6 |

Truy vấn này trả **2 hàng**, vì tập paid được chia thành hai nhóm. Nó rất thích hợp cho bảng KPI theo khu vực, nhưng không hiển thị lại từng `sale_id`.

**Câu hỏi khác**: “Với mỗi giao dịch, cho tôi thấy tổng tiền và số giao dịch paid của khu vực đó.” Đây mới là mục tiêu của window aggregate.

## 4. SUM(...) OVER(PARTITION BY ...): tổng của phân vùng

```sql
SELECT
    sale_id,
    region,
    amount,
    SUM(amount) OVER (
        PARTITION BY region
    ) AS region_revenue
FROM demo_sales_window
WHERE status = 'paid'
ORDER BY region, sold_on, sale_id;
```

Với North, `region_revenue` bằng **600** trên cả sáu hàng. Với South, nó bằng **500** trên cả bảy hàng.

Một đoạn kết quả:

| `sale_id` | `region` | `amount` | `region_revenue` |
| ---: | --- | ---: | ---: |
| 1 | North | 100 | 600 |
| 2 | North | 200 | 600 |
| 3 | North | 50 | 600 |
| 4 | North | `NULL` | 600 |
| 5 | North | 150 | 600 |
| 7 | North | 100 | 600 |
| 8 | South | 80 | 500 |
| … | South | … | 500 |

### 4.1. PARTITION BY khác GROUP BY như thế nào?

Hai cụm đều chia dữ liệu theo cột, nhưng mục đích khác nhau:

| Điểm so sánh | `GROUP BY region` | `SUM(amount) OVER (PARTITION BY region)` |
| --- | --- | --- |
| Số hàng đầu ra | Một hàng trên mỗi region | Giữ từng hàng của tập đầu vào |
| Giá trị tổng region | Một giá trị trên hàng tổng | Lặp lại trên mọi hàng trong region |
| Có giữ `sale_id` từng giao dịch không? | Không thể chọn tự do nếu không được nhóm/tổng hợp | Có |
| Có dùng tiếp để tính lũy kế theo thứ tự không? | Cần cấu trúc bổ sung | Có thể thêm `ORDER BY` và frame trong `OVER` |
| Dùng khi nào? | Chỉ cần một báo cáo cấp nhóm | Cần chỉ số cấp nhóm đặt cạnh từng hàng |

`PARTITION BY` **không bắt buộc**. Nếu bỏ nó, toàn bộ tập hàng đầu vào của cửa sổ thuộc **một phân vùng**.

### 4.2. Tổng toàn bộ dữ liệu bằng OVER()

```sql
SELECT
    sale_id,
    region,
    amount,
    SUM(amount) OVER () AS overall_paid_revenue
FROM demo_sales_window
WHERE status = 'paid'
ORDER BY region, sold_on, sale_id;
```

`SUM(amount) OVER ()` trả **1100** ở cả 13 hàng. Nó tính trên toàn bộ hàng sau bộ lọc `WHERE status = 'paid'`, không chỉ theo một khu vực.

Từ khóa `OVER` là điểm mấu chốt:

- `SUM(amount)` không có `OVER` là **aggregate thông thường**.
- `SUM(amount) OVER (...)` là **window aggregate**.

## 5. AVG(...) OVER(...): trung bình của những giá trị không NULL

```sql
SELECT
    sale_id,
    region,
    amount,
    ROUND(
        AVG(amount) OVER (PARTITION BY region),
        2
    ) AS region_average
FROM demo_sales_window
WHERE status = 'paid'
ORDER BY region, sold_on, sale_id;
```

Kết quả `region_average`:

- North: **120.00** ở mọi hàng North.
- South: **83.33** ở mọi hàng South.

### 5.1. Mẫu số của AVG không nhất thiết là số hàng

Về mặt ý nghĩa của aggregate:

\[
\operatorname{AVG}(x)
=
\frac{\operatorname{SUM}(x)}
{\operatorname{COUNT}(x)}
\]

với những hàng có `x IS NOT NULL`. Công thức chỉ được dùng khi có ít nhất một giá trị không `NULL`.

Trong North có sáu hàng paid, nhưng giao dịch 4 không có số tiền. Vì vậy:

```text
AVG(amount) = 600 / 5 = 120
không phải 600 / 6 = 100
```

`AVG` **bỏ qua giá trị `NULL`**, không coi `NULL` là số 0.

### 5.2. Nếu muốn tính trung bình với 0 theo quy tắc nghiệp vụ?

Có thể viết:

```sql
SELECT
    sale_id,
    region,
    ROUND(
        AVG(COALESCE(amount, 0)) OVER (
            PARTITION BY region
        ),
        2
    ) AS average_with_missing_as_zero
FROM demo_sales_window
WHERE status = 'paid'
ORDER BY region, sale_id;
```

Với North, giá trị này là `600 / 6 = 100`; với South là `500 / 7 ≈ 71.43`.

**Nhưng đây là một chỉ số khác.** `NULL` có nghĩa là “chưa biết” trong bộ dữ liệu mẫu. Biến nó thành 0 chỉ phù hợp nếu nghiệp vụ thật sự coi giao dịch chưa biết số tiền như 0 để tính trung bình. Không dùng `COALESCE` chỉ để làm báo cáo “đẹp hơn” mà không công bố quy tắc.

## 6. COUNT(*) và COUNT(cột) trên cửa sổ

`COUNT` là hàm cửa sổ rất thường dùng, nhưng có hai dạng dễ nhầm:

- `COUNT(*) OVER (...)`: đếm **mọi hàng** trong cửa sổ.
- `COUNT(amount) OVER (...)`: đếm những hàng trong cửa sổ có **`amount IS NOT NULL`**.

Ví dụ:

```sql
SELECT
    sale_id,
    region,
    amount,
    COUNT(*) OVER (
        PARTITION BY region
    ) AS paid_rows_in_region,
    COUNT(amount) OVER (
        PARTITION BY region
    ) AS known_amounts_in_region,
    SUM(amount) OVER (
        PARTITION BY region
    ) AS region_revenue
FROM demo_sales_window
WHERE status = 'paid'
ORDER BY region, sold_on, sale_id;
```

Kết quả được lặp lại trên từng hàng:

| Khu vực | `COUNT(*)` | `COUNT(amount)` | `SUM(amount)` |
| --- | ---: | ---: | ---: |
| North | 6 | 5 | 600 |
| South | 7 | 6 | 500 |

Nếu tính trên toàn bộ tập paid:

```sql
SELECT
    sale_id,
    COUNT(*) OVER () AS total_paid_rows,
    COUNT(amount) OVER () AS total_known_amount_rows,
    SUM(amount) OVER () AS total_revenue,
    AVG(amount) OVER () AS overall_average
FROM demo_sales_window
WHERE status = 'paid'
ORDER BY sale_id;
```

Mỗi hàng trả:

```text
total_paid_rows        = 13
total_known_amount_rows = 11
total_revenue          = 1100
overall_average        = 100
```

### 6.1. COUNT(1) có khác COUNT(*) không?

Với literal `1` chắc chắn không `NULL`:

```sql
COUNT(1) OVER (PARTITION BY region)
```

thường có cùng số đếm với `COUNT(*) OVER (PARTITION BY region)`. Tuy vậy, `COUNT(*)` diễn đạt rõ nhất rằng ta muốn đếm **hàng**, còn `COUNT(amount)` diễn đạt rõ nhất rằng ta muốn đếm **giá trị amount đã biết**.

### 6.2. COUNT DISTINCT trên cửa sổ có được không?

Một số DBMS cho phép cách viết tương tự `COUNT(DISTINCT salesperson) OVER (PARTITION BY region)`, nhưng **PostgreSQL không hỗ trợ `DISTINCT` bên trong lời gọi window aggregate theo cách này**.

Câu sau **cố ý không hợp lệ trong PostgreSQL**:

```sql
-- PostgreSQL: không hỗ trợ DISTINCT trong window aggregate.
SELECT
    region,
    COUNT(DISTINCT salesperson) OVER (
        PARTITION BY region
    ) AS distinct_sellers
FROM demo_sales_window;
```

Nếu cần số người bán khác nhau trong khu vực, tính riêng theo `GROUP BY` rồi nối kết quả về từng hàng:

```sql
WITH paid AS (
    SELECT *
    FROM demo_sales_window
    WHERE status = 'paid'
),
seller_counts AS (
    SELECT
        region,
        COUNT(DISTINCT salesperson) AS seller_count
    FROM paid
    GROUP BY region
)
SELECT
    p.sale_id,
    p.region,
    p.salesperson,
    s.seller_count
FROM paid AS p
JOIN seller_counts AS s
  ON s.region = p.region
ORDER BY p.region, p.sale_id;
```

Trong dữ liệu mẫu, cả North và South đều có **2 nhân viên bán hàng**. Với dữ liệu có khóa nhóm `NULL`, cần xem lại điều kiện nối `=` vì hai `NULL` không khớp nhau; ở đây `region NOT NULL` nên phép nối an toàn.

## 7. Cửa sổ không có ORDER BY khác gì có ORDER BY?

Đây là thay đổi nhỏ về cú pháp nhưng lớn về ý nghĩa.

**Không có `ORDER BY` trong `OVER`:**

```sql
SUM(amount) OVER (PARTITION BY region)
```

Mỗi hàng North nhìn **toàn bộ sáu giao dịch paid của North** → tổng 600.

**Có `ORDER BY` trong `OVER`:**

```sql
SUM(amount) OVER (
    PARTITION BY region
    ORDER BY sold_on, sale_id
)
```

Trong PostgreSQL, khi một window aggregate có `ORDER BY` mà không chỉ định frame, khung mặc định thông thường là:

```sql
RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
```

Điều đó thường cho kết quả **lũy kế từ đầu phân vùng đến hàng hiện tại**, đồng thời gồm cả các hàng **đồng hạng trên khóa `ORDER BY`** (*peers*). Khi `ORDER BY sold_on, sale_id` có khóa duy nhất `sale_id`, mỗi hàng có một vị trí sắp xếp duy nhất, nên kết quả lũy kế tăng theo từng hàng.

Nếu muốn **toàn bộ phân vùng dù có ORDER BY**, viết frame tường minh:

```sql
SUM(amount) OVER (
    PARTITION BY region
    ORDER BY sold_on, sale_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
)
```

Tổng lại là 600 cho mọi hàng North và 500 cho mọi hàng South. `ORDER BY` xác định trình tự nhưng frame bao phủ toàn bộ phân vùng.

**Quy tắc ghi nhớ:** `PARTITION BY` trả lời “chia thành những nhóm nào”, còn `ORDER BY` và **frame** quyết định “cho mỗi hàng, lấy phần nào của nhóm để tính”.

## 8. Tổng lũy kế với SUM và ROWS

Yêu cầu: “Cho mỗi giao dịch paid, hiển thị tổng tiền của những giao dịch paid thuộc **cùng khu vực**, từ đầu kỳ đến chính giao dịch đó.”

```sql
SELECT
    sale_id,
    sold_on,
    region,
    amount,
    SUM(amount) OVER (
        PARTITION BY region
        ORDER BY sold_on, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_revenue
FROM demo_sales_window
WHERE status = 'paid'
ORDER BY region, sold_on, sale_id;
```

Ở đây:

- `PARTITION BY region`: khi chuyển khu vực, bắt đầu lại tổng lũy kế.
- `ORDER BY sold_on, sale_id`: sắp theo ngày; nếu cùng ngày, theo ID để có thứ tự xác định.
- `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`: tính từ **hàng đầu tiên trong phân vùng** đến **hàng hiện tại**, bao gồm hai đầu.

### 8.1. Kết quả khu vực North

| `sale_id` | Ngày | `amount` | `running_revenue` |
| ---: | --- | ---: | ---: |
| 1 | 05-01 | 100 | 100 |
| 2 | 05-01 | 200 | 300 |
| 3 | 05-02 | 50 | 350 |
| 4 | 05-03 | `NULL` | 350 |
| 5 | 05-03 | 150 | 500 |
| 7 | 05-05 | 100 | 600 |

Diễn giải:

```text
Giao dịch 1: 100
Giao dịch 2: 100 + 200 = 300
Giao dịch 3: 300 + 50 = 350
Giao dịch 4: 350 + NULL → SUM vẫn là 350
Giao dịch 5: 350 + 150 = 500
Giao dịch 7: 500 + 100 = 600
```

### 8.2. Kết quả khu vực South

| `sale_id` | Ngày | `amount` | `running_revenue` |
| ---: | --- | ---: | ---: |
| 8 | 05-01 | 80 | 80 |
| 9 | 05-02 | 120 | 200 |
| 10 | 05-02 | 40 | 240 |
| 11 | 05-03 | 60 | 300 |
| 13 | 05-05 | 100 | 400 |
| 14 | 05-06 | 100 | 500 |
| 15 | 05-07 | `NULL` | 500 |

Tổng lũy kế của South được đặt lại ở 80 khi sang hàng đầu tiên của South, **không cộng tiếp** từ 600 của North.

### 8.3. Tại sao phải có khóa phá hòa khi dùng ROWS?

Hai giao dịch North số 1 và 2 có cùng ngày 01/05. Nếu chỉ:

```sql
ORDER BY sold_on
ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
```

SQL chưa quy định thứ tự **giữa hai hàng cùng `sold_on`**, nên không có bảo đảm giao dịch 1 được cộng trước giao dịch 2. Kết quả cuối ngày vẫn có thể là 300, nhưng giá trị lũy kế **theo từng dòng giao dịch** có thể khác.

Khi nghiệp vụ cần lũy kế **theo từng giao dịch**, dùng khóa sắp xếp đầy đủ, ví dụ:

```sql
ORDER BY sold_on, sale_id
```

`sale_id` là khóa chính nên không có hai giao dịch đồng hạng trên toàn bộ cặp này.

## 9. Đếm lũy kế và trung bình lũy kế

Cùng một frame có thể áp dụng cho `SUM`, `COUNT(*)`, `COUNT(amount)` và `AVG(amount)`.

```sql
SELECT
    sale_id,
    region,
    sold_on,
    amount,
    COUNT(*) OVER (
        PARTITION BY region
        ORDER BY sold_on, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_paid_rows,
    COUNT(amount) OVER (
        PARTITION BY region
        ORDER BY sold_on, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_known_amounts,
    SUM(amount) OVER (
        PARTITION BY region
        ORDER BY sold_on, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_revenue,
    ROUND(
        AVG(amount) OVER (
            PARTITION BY region
            ORDER BY sold_on, sale_id
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ),
        2
    ) AS running_average
FROM demo_sales_window
WHERE status = 'paid'
ORDER BY region, sold_on, sale_id;
```

Một phần kết quả North:

| `sale_id` | Số hàng paid đến hiện tại | Số amount đã biết | Tổng lũy kế | AVG lũy kế |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 1 | 1 | 100 | 100.00 |
| 2 | 2 | 2 | 300 | 150.00 |
| 3 | 3 | 3 | 350 | 116.67 |
| 4 | 4 | 3 | 350 | 116.67 |
| 5 | 5 | 4 | 500 | 125.00 |
| 7 | 6 | 5 | 600 | 120.00 |

Ở giao dịch 4, `COUNT(*)` tăng từ 3 lên 4, nhưng `COUNT(amount)` vẫn là 3 và `AVG(amount)` không thay đổi vì amount là `NULL`.

Đây là một cách phát hiện chất lượng dữ liệu: so sánh **số bản ghi đã xử lý** và **số bản ghi có giá trị cần đo** trong từng đoạn thời gian.

## 10. Bẫy của khung mặc định: RANGE và các hàng cùng ngày

Giả sử viết:

```sql
SELECT
    sale_id,
    sold_on,
    region,
    amount,
    SUM(amount) OVER (
        PARTITION BY region
        ORDER BY sold_on
    ) AS running_by_date
FROM demo_sales_window
WHERE status = 'paid'
ORDER BY region, sold_on, sale_id;
```

Chú ý `OVER` **không có frame tường minh** và `ORDER BY` chỉ dùng `sold_on`.

Trong PostgreSQL, frame mặc định với `ORDER BY` là dạng `RANGE UNBOUNDED PRECEDING ... CURRENT ROW`, bao gồm **tất cả peers của hàng hiện tại**. Hai hàng cùng ngày có cùng giá trị `sold_on` nên nằm trong cùng nhóm peers.

Với North:

| `sale_id` | Ngày | `amount` | `ROWS` lũy kế theo ngày + ID | Khung mặc định `RANGE` theo ngày |
| ---: | --- | ---: | ---: | ---: |
| 1 | 05-01 | 100 | 100 | 300 |
| 2 | 05-01 | 200 | 300 | 300 |
| 3 | 05-02 | 50 | 350 | 350 |
| 4 | 05-03 | `NULL` | 350 | 500 |
| 5 | 05-03 | 150 | 500 | 500 |
| 7 | 05-05 | 100 | 600 | 600 |

Sự khác nhau xuất hiện ở những ngày có nhiều giao dịch:

- Ngày 01/05 có 100 và 200. `RANGE` xem cả hai hàng có cùng khóa ngày và trả **300 cho cả hai**.
- Ngày 03/05 có `NULL` và 150. `RANGE` trả **500 cho cả hai**, kể cả giao dịch 4 có amount chưa biết.

### 10.1. Peer nghĩa là gì?

Hai hàng là **peers** khi chúng có cùng giá trị trên **toàn bộ các biểu thức `ORDER BY` của cửa sổ**.

Nếu `ORDER BY sold_on`, các giao dịch cùng ngày là peers.

Nếu `ORDER BY sold_on, sale_id`, vì `sale_id` duy nhất nên không có hai hàng khác nhau là peers. Khi đó frame `RANGE` mặc định có kết quả giống lũy kế từng hàng trong dữ liệu mẫu.

Nhưng nên viết `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` rõ ràng khi nghiệp vụ là **lũy kế từng bản ghi**. Nó giúp người đọc không phải dựa vào mặc định của DBMS hoặc suy luận peers từ các khóa.

### 10.2. RANGE không phải lúc nào cũng là “ngày gần nhất”

`RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` với `ORDER BY sold_on` là **từ đầu phân vùng đến ngày hiện tại**, chứ không giới hạn một, hai hay bảy ngày gần nhất.

`RANGE` có thể diễn tả một khoảng giá trị tính từ hàng hiện tại, nhưng điều đó cần một **frame offset** tường minh, ví dụ `INTERVAL '2 days' PRECEDING`.

## 11. Khung ROWS trượt: trung bình ba giao dịch gần nhất

Một yêu cầu phổ biến:

> Với mỗi giao dịch paid, tính số tiền trung bình của **tối đa ba giao dịch paid gần nhất trong cùng khu vực**, bao gồm giao dịch hiện tại.

Cú pháp:

```sql
ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
```

Nó lấy **hai hàng trước + hàng hiện tại** theo thứ tự `OVER (ORDER BY ...)`.

```sql
SELECT
    sale_id,
    sold_on,
    region,
    amount,
    SUM(amount) OVER (
        PARTITION BY region
        ORDER BY sold_on, sale_id
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS last_3_rows_sum,
    COUNT(*) OVER (
        PARTITION BY region
        ORDER BY sold_on, sale_id
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS last_3_rows_count,
    COUNT(amount) OVER (
        PARTITION BY region
        ORDER BY sold_on, sale_id
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS last_3_known_amounts,
    ROUND(
        AVG(amount) OVER (
            PARTITION BY region
            ORDER BY sold_on, sale_id
            ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
        ),
        2
    ) AS last_3_rows_average
FROM demo_sales_window
WHERE status = 'paid'
ORDER BY region, sold_on, sale_id;
```

### 11.1. Kết quả North

| `sale_id` | Các amount trong frame | SUM | COUNT(*) | COUNT(amount) | AVG |
| ---: | --- | ---: | ---: | ---: | ---: |
| 1 | [100] | 100 | 1 | 1 | 100.00 |
| 2 | [100, 200] | 300 | 2 | 2 | 150.00 |
| 3 | [100, 200, 50] | 350 | 3 | 3 | 116.67 |
| 4 | [200, 50, `NULL`] | 250 | 3 | 2 | 125.00 |
| 5 | [50, `NULL`, 150] | 200 | 3 | 2 | 100.00 |
| 7 | [`NULL`, 150, 100] | 250 | 3 | 2 | 125.00 |

Ở `sale_id = 4`, cửa sổ gồm **ba hàng**, nhưng chỉ có **hai amount đã biết**, nên:

```text
SUM = 200 + 50 = 250
AVG = 250 / 2 = 125
```

Không phải `250 / 3`.

### 11.2. “Ba giao dịch gần nhất” khác “ba ngày gần nhất”

Dữ liệu có thể có nhiều giao dịch trong một ngày. `ROWS BETWEEN 2 PRECEDING AND CURRENT ROW` chọn tối đa **ba hàng giao dịch** bất kể chúng trải trên bao nhiêu ngày.

Ví dụ, tại giao dịch 5 ngày 03/05 ở North, ba hàng gần nhất theo thứ tự là giao dịch 3, 4, 5; không nhất thiết là toàn bộ giao dịch trong ba ngày 01/05–03/05.

Nếu bài toán là “doanh thu ba ngày gần nhất”, cần dùng frame dựa trên **khoảng giá trị ngày** hoặc tổng hợp trước theo ngày. Hai cách sẽ được phân biệt ở phần tiếp theo.

### 11.3. ROWS không tự bỏ hàng có NULL

Frame `ROWS` chọn hàng dựa trên vị trí. Một hàng `amount IS NULL` **vẫn chiếm một vị trí** trong ba hàng gần nhất. Sau đó:

- `SUM(amount)` bỏ qua amount `NULL`.
- `AVG(amount)` bỏ qua amount `NULL` và không đưa nó vào mẫu số.
- `COUNT(*)` vẫn đếm hàng đó.
- `COUNT(amount)` không đếm hàng đó.

Đây là lý do không nên gọi `ROWS BETWEEN 2 PRECEDING AND CURRENT ROW` là “ba giá trị amount gần nhất không NULL”. Nó là **ba hàng gần nhất**, rồi aggregate xử lý `NULL` theo quy tắc riêng.

## 12. ROWS, RANGE và GROUPS: ba cách xác định frame

Ba loại frame thường gặp trong PostgreSQL:

| Loại frame | Xác định dựa trên | Ý nghĩa với ngày trùng nhau |
| --- | --- | --- |
| `ROWS` | Số **hàng** trước/sau theo thứ tự cửa sổ | Có thể chia hai giao dịch cùng ngày vào hai frame khác nhau |
| `RANGE` | **Giá trị khóa ORDER BY** và khoảng giá trị cho phép | Có thể lấy tất cả giao dịch trong cùng ngày/khoảng ngày |
| `GROUPS` | Số **nhóm peers** trước/sau | Mỗi nhóm các hàng đồng khóa sắp xếp được xem như một đơn vị |

### 12.1. ROWS: chính xác ba hàng

```sql
SUM(amount) OVER (
    PARTITION BY region
    ORDER BY sold_on, sale_id
    ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
)
```

Tại giao dịch North `5`: lấy giao dịch `3, 4, 5` → tổng **200**.

### 12.2. RANGE: ba ngày lịch tính theo giá trị ngày

Dùng khóa thời gian duy nhất trong `ORDER BY` của frame kiểu offset:

```sql
SELECT
    sale_id,
    region,
    sold_on,
    amount,
    SUM(amount) OVER (
        PARTITION BY region
        ORDER BY sold_on::timestamp
        RANGE BETWEEN INTERVAL '2 days' PRECEDING
                  AND CURRENT ROW
    ) AS last_3_calendar_days_revenue
FROM demo_sales_window
WHERE status = 'paid'
ORDER BY region, sold_on, sale_id;
```

Với `sold_on = 2025-05-03`, frame lấy các giao dịch trong khoảng **01/05 đến hết 03/05**, vì ranh giới theo thời gian là từ 03/05 lùi hai ngày đến 01/05 và tới hàng hiện tại theo nhóm peers.

Ở North, tại giao dịch `4` hoặc `5`:

```text
Ngày 01/05: 100 + 200
Ngày 02/05: 50
Ngày 03/05: NULL + 150
Tổng = 500
```

Tại giao dịch `7` ngày 05/05, khoảng là 03/05–05/05:

```text
Ngày 03/05: NULL + 150
Ngày 04/05: không có giao dịch paid ở North
Ngày 05/05: 100
Tổng = 250
```

Frame `RANGE` dùng **giá trị thời gian**, không chọn đúng ba hàng. Nó có thể chứa 0, 1, 2 hoặc nhiều giao dịch ở mỗi ngày.

**Lưu ý DBMS:** cú pháp frame `RANGE` với `INTERVAL` khác nhau giữa các hệ; ví dụ này dùng PostgreSQL. Việc ép `sold_on::timestamp` giúp rõ cột sắp xếp là giá trị thời gian để dùng offset kiểu `INTERVAL`.

### 12.3. GROUPS: hai nhóm ngày liền nhau có dữ liệu

`GROUPS` được PostgreSQL hỗ trợ. Ví dụ:

```sql
SELECT
    sale_id,
    sold_on,
    region,
    SUM(amount) OVER (
        PARTITION BY region
        ORDER BY sold_on
        GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW
    ) AS current_and_previous_date_group
FROM demo_sales_window
WHERE status = 'paid'
ORDER BY region, sold_on, sale_id;
```

Các hàng cùng `sold_on` tạo một **nhóm peers**.

Ở North tại ngày 03/05:

- Nhóm peers hiện tại (03/05): `NULL` và 150.
- Nhóm peers trước đó (02/05): 50.
- Tổng hai nhóm: **200**.

Ở North tại ngày 05/05:

- Nhóm hiện tại: 100.
- Nhóm ngày có dữ liệu paid trước đó: 03/05 có 150 và `NULL`.
- Tổng: **250**.

`GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW` nói về **hai nhóm giá trị ngày xuất hiện trong dữ liệu**, không nhất thiết hai ngày lịch liên tục. Nếu có ngày trống, nhóm ngày trước có thể cách nhiều ngày.

### 12.4. Đặt ba kết quả cạnh nhau

Tại giao dịch North `5` ngày 03/05, trên dữ liệu paid:

| Frame | Những hàng/sự kiện được tính | `SUM(amount)` |
| --- | --- | ---: |
| `ROWS 2 PRECEDING` theo ngày + ID | ID 3, 4, 5 | 200 |
| `RANGE INTERVAL '2 days' PRECEDING` | Mọi giao dịch 01/05–03/05 | 500 |
| `GROUPS 1 PRECEDING` theo ngày | Mọi giao dịch 02/05 và 03/05 | 200 |

Hai phép có thể trùng kết quả ở một ngày cụ thể nhưng không có cùng ngữ nghĩa. Lựa chọn phải dựa vào yêu cầu **đếm hàng**, **khoảng thời gian**, hay **số nhóm đồng khóa**.

## 13. Khung mở rộng, khung tương lai và frame rỗng

Cấu trúc chung của frame trong PostgreSQL:

```sql
ROWS BETWEEN <ranh_gioi_dau> AND <ranh_gioi_cuoi>
```

Những ranh giới thường gặp:

| Ranh giới | Ý nghĩa |
| --- | --- |
| `UNBOUNDED PRECEDING` | Bắt đầu phân vùng |
| `N PRECEDING` | N hàng/nhóm/khoảng đơn vị trước, tùy loại frame |
| `CURRENT ROW` | Hàng hiện tại; với `RANGE`/`GROUPS` có liên quan nhóm peers |
| `N FOLLOWING` | N hàng/nhóm/khoảng đơn vị sau |
| `UNBOUNDED FOLLOWING` | Kết thúc phân vùng |

### 13.1. Cửa sổ đối xứng gồm trước và sau

Ví dụ tính trung bình của **hàng trước, hàng hiện tại và hàng sau**:

```sql
AVG(amount) OVER (
    PARTITION BY region
    ORDER BY sold_on, sale_id
    ROWS BETWEEN 1 PRECEDING AND 1 FOLLOWING
)
```

Ở đầu hoặc cuối phân vùng, frame bị giới hạn bởi biên thực tế của phân vùng. Không có hàng “ngoài biên” được tự tạo.

Dạng này có thể hữu ích khi làm mượt chuỗi số liệu, nhưng **bao gồm dữ liệu của hàng sau**. Nếu người dùng cần báo cáo “tính đến thời điểm hiện tại” tuyệt đối không dùng dữ liệu tương lai, hãy chọn frame chỉ gồm `PRECEDING` và `CURRENT ROW`.

### 13.2. Tổng từ hàng hiện tại đến cuối phân vùng

```sql
SUM(amount) OVER (
    PARTITION BY region
    ORDER BY sold_on, sale_id
    ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING
)
```

Với North:

- Giao dịch 1: tổng còn lại bao gồm nó là **600**.
- Giao dịch 2: **500**.
- Giao dịch 3: **300**.
- Giao dịch 4: **250** (bỏ qua amount `NULL` của chính nó).
- Giao dịch 5: **250**.
- Giao dịch 7: **100**.

Đây là tổng **đuôi phân vùng**, không phải tổng lũy kế từ đầu.

### 13.3. Frame không có hàng và frame chỉ toàn NULL

`COUNT(*)`, `SUM` và `AVG` phản ứng khác nhau khi frame rỗng:

- `COUNT(*)` trên frame rỗng trả **0**.
- `COUNT(amount)` trên frame rỗng trả **0**.
- `SUM(amount)` trên frame rỗng trả **NULL**.
- `AVG(amount)` trên frame rỗng trả **NULL**.

Một frame **có hàng nhưng tất cả `amount IS NULL`** cũng cho `COUNT(amount)=0`, `SUM(amount)=NULL` và `AVG(amount)=NULL`, dù `COUNT(*)` lớn hơn 0.

Ví dụ thực hành độc lập:

```sql
WITH values_example(n, amount) AS (
    VALUES
        (1, NULL::numeric),
        (2, NULL::numeric)
)
SELECT
    n,
    COUNT(*) OVER (
        ORDER BY n
        ROWS BETWEEN 1 PRECEDING AND 1 PRECEDING
    ) AS rows_before,
    SUM(amount) OVER (
        ORDER BY n
        ROWS BETWEEN 1 PRECEDING AND 1 PRECEDING
    ) AS sum_before
FROM values_example
ORDER BY n;
```

Kết quả:

| `n` | `rows_before` | `sum_before` |
| ---: | ---: | --- |
| 1 | 0 | `NULL` |
| 2 | 1 | `NULL` |

Ở hàng 1, frame không có hàng trước. Ở hàng 2, frame có hàng 1 nhưng amount của hàng đó là `NULL`. Cả hai tình huống có `sum_before = NULL`, nhưng `rows_before` giúp phân biệt.

**Không nên tự thay mọi `SUM` rỗng/không biết thành 0** nếu chưa xác định ý nghĩa nghiệp vụ của dữ liệu thiếu.

## 14. Nhiều cột PARTITION BY: phân vùng nhỏ hơn

Ta có thể chia theo **khu vực và người bán**:

```sql
SELECT
    sale_id,
    region,
    salesperson,
    amount,
    SUM(amount) OVER (
        PARTITION BY region, salesperson
    ) AS salesperson_revenue,
    COUNT(*) OVER (
        PARTITION BY region, salesperson
    ) AS salesperson_paid_rows,
    COUNT(amount) OVER (
        PARTITION BY region, salesperson
    ) AS salesperson_known_amount_rows
FROM demo_sales_window
WHERE status = 'paid'
ORDER BY region, salesperson, sale_id;
```

Kết quả cấp phân vùng:

| Khu vực | Người bán | Tổng tiền paid | Số hàng paid | Số amount đã biết |
| --- | --- | ---: | ---: | ---: |
| North | An | 300 | 3 | 3 |
| North | Binh | 300 | 3 | 2 |
| South | Chi | 220 | 3 | 3 |
| South | Dung | 280 | 4 | 3 |

Tổng 300 của An ở North đến từ các ID `1,3,5`. Tổng 300 của Binh ở North đến từ ID `2,4,7` nhưng ID 4 có `NULL`, nên chỉ có hai giá trị được cộng.

### 14.1. PARTITION BY không tự tạo hàng tổng

Ví dụ trên vẫn trả **13 hàng paid**, chứ không phải bốn hàng nhóm như `GROUP BY region, salesperson`. Các số ở bảng trên được **lặp lại trên các hàng thuộc cùng phân vùng**.

Nếu muốn bảng tổng hợp một hàng trên mỗi người bán/khu vực, dùng `GROUP BY`. Nếu muốn chi tiết từng giao dịch kèm KPI của người bán, dùng window aggregate.

### 14.2. NULL trong khóa phân vùng

Nếu một cột `region` hoặc `salesperson` được phép `NULL`, các hàng có khóa phân vùng giống nhau theo quy tắc phân vùng (bao gồm các giá trị `NULL` tương ứng) có thể cùng nằm trong một phân vùng.

Đừng nhầm `PARTITION BY region` với `WHERE region = NULL` — phép so sánh `= NULL` trong SQL không có nghĩa là tìm các hàng region thiếu dữ liệu. Khi muốn lọc dữ liệu thiếu, phải dùng `IS NULL`. Trong bộ dữ liệu mẫu, `region` và `salesperson` đều được khai báo `NOT NULL` để các ví dụ chính tập trung vào `NULL` của `amount`.

## 15. Tính tỷ trọng giao dịch trong toàn bộ doanh thu

Vì window aggregate giữ từng hàng, ta có thể tính doanh thu toàn hệ thống ngay trong phép chia tỷ trọng.

```sql
SELECT
    sale_id,
    region,
    amount,
    SUM(amount) OVER () AS overall_revenue,
    ROUND(
        100 * amount
        / NULLIF(SUM(amount) OVER (), 0),
        2
    ) AS pct_of_overall_revenue
FROM demo_sales_window
WHERE status = 'paid'
ORDER BY region, sale_id;
```

Ví dụ:

- Giao dịch 1: `100 / 1100 × 100 ≈ 9.09%`.
- Giao dịch 2: `200 / 1100 × 100 ≈ 18.18%`.
- Giao dịch 8: `80 / 1100 × 100 ≈ 7.27%`.
- Giao dịch 4 và 15 có `amount = NULL` nên tỷ trọng là `NULL`, không phải 0 theo giả định.

`NULLIF(total, 0)` giúp tránh phép chia cho 0 nếu tổng doanh thu bằng 0. Nếu mẫu số `NULL` vì không có giá trị tiền đã biết, kết quả tỷ trọng cũng là `NULL`.

### 15.1. Tỷ trọng so với khu vực

```sql
SELECT
    sale_id,
    region,
    amount,
    ROUND(
        100 * amount
        / NULLIF(
            SUM(amount) OVER (PARTITION BY region),
            0
        ),
        2
    ) AS pct_within_region
FROM demo_sales_window
WHERE status = 'paid'
ORDER BY region, sale_id;
```

Với giao dịch 1, `100/600 × 100 ≈ 16.67%` của North. Giao dịch 8 là `80/500 × 100 = 16%` của South.

### 15.2. Không cộng lại tỷ trọng cấp nhóm đã lặp trên từng hàng

Nếu tính:

```sql
SUM(amount) OVER (PARTITION BY region) AS region_revenue
```

rồi lấy `region_revenue / overall_revenue`, tỷ trọng **54.55% của North** sẽ lặp trên tất cả sáu giao dịch North. Không được cộng sáu tỷ trọng đó để suy ra “tỷ trọng toàn bộ”.

Một chỉ số cấp nhóm bị lặp lại trên nhiều hàng chỉ là **thông tin ngữ cảnh của từng hàng**. Muốn một dòng trên mỗi khu vực, nên tổng hợp bằng `GROUP BY` rồi tính tỷ trọng ở cấp nhóm.

## 16. GROUP BY kết hợp window aggregate: hai tầng tổng hợp

Window aggregate cũng có thể chạy **trên kết quả đã GROUP BY**.

Yêu cầu: “Mỗi khu vực một hàng, hiển thị doanh thu khu vực và phần trăm của tổng doanh thu toàn hệ thống.”

```sql
SELECT
    region,
    COUNT(*) AS paid_rows,
    COUNT(amount) AS known_amount_rows,
    SUM(amount) AS region_revenue,
    SUM(SUM(amount)) OVER () AS overall_revenue,
    ROUND(
        100 * SUM(amount)
        / NULLIF(SUM(SUM(amount)) OVER (), 0),
        2
    ) AS pct_of_overall_revenue
FROM demo_sales_window
WHERE status = 'paid'
GROUP BY region
ORDER BY region;
```

Kết quả:

| `region` | `paid_rows` | `known_amount_rows` | `region_revenue` | `overall_revenue` | `pct_of_overall_revenue` |
| --- | ---: | ---: | ---: | ---: | ---: |
| North | 6 | 5 | 600 | 1100 | 54.55 |
| South | 7 | 6 | 500 | 1100 | 45.45 |

### 16.1. Tại sao có SUM(SUM(amount)) OVER()?

Đây là hai tầng:

1. `SUM(amount)` **bên trong** tổng hợp từng khu vực do `GROUP BY region`.
2. `SUM( ... ) OVER ()` **bên ngoài** cộng các kết quả doanh thu **của những hàng khu vực sau GROUP BY**.

```text
13 giao dịch paid
      │
      └── GROUP BY region, SUM(amount)
               │
               ├── North: 600
               └── South: 500
                       │
            SUM(SUM(amount)) OVER ()
                       │
                 600 + 500 = 1100
```

Không nên nhầm với `SUM(amount) OVER ()` ở cùng cấp truy vấn đã `GROUP BY region`. Sau `GROUP BY`, cột amount gốc không còn có thể được chọn tự do nếu nó không nằm trong khóa nhóm hoặc không được tổng hợp hợp lệ.

### 16.2. COUNT(*) OVER() sau GROUP BY đếm nhóm, không đếm giao dịch

```sql
SELECT
    region,
    COUNT(*) AS transactions_in_region,
    COUNT(*) OVER () AS group_rows_in_result,
    SUM(COUNT(*)) OVER () AS all_paid_transactions
FROM demo_sales_window
WHERE status = 'paid'
GROUP BY region
ORDER BY region;
```

Kết quả:

| `region` | `transactions_in_region` | `group_rows_in_result` | `all_paid_transactions` |
| --- | ---: | ---: | ---: |
| North | 6 | 2 | 13 |
| South | 7 | 2 | 13 |

Vì window function xử lý tập hàng **đã GROUP BY**, `COUNT(*) OVER()` ở đây đếm **hai hàng nhóm**, không phải 13 giao dịch gốc.

Muốn tổng số giao dịch paid, dùng `SUM(COUNT(*)) OVER()`, cộng các số đếm của các nhóm.

### 16.3. AVG của tổng nhóm không phải AVG của giao dịch

Với hai hàng nhóm có doanh thu 600 và 500:

```sql
AVG(SUM(amount)) OVER ()
```

là **trung bình doanh thu mỗi khu vực = (600+500)/2 = 550**.

Nó **không** phải trung bình `amount` của giao dịch, vốn là **1100/11 = 100** khi bỏ qua hai `NULL`.

Muốn trung bình amount đã biết trên toàn bộ các nhóm trong một truy vấn `GROUP BY`, có thể viết:

```sql
SELECT
    region,
    SUM(amount) AS region_revenue,
    COUNT(amount) AS region_known_amounts,
    SUM(SUM(amount)) OVER ()
      / NULLIF(SUM(COUNT(amount)) OVER (), 0)
      AS overall_known_amount_average
FROM demo_sales_window
WHERE status = 'paid'
GROUP BY region
ORDER BY region;
```

Mỗi hàng trả `overall_known_amount_average = 100`.

Đây là nguyên lý **trung bình có trọng số**: không lấy trung bình đơn giản của hai `AVG` theo khu vực khi số quan sát ở mỗi khu vực khác nhau.

## 17. Tổng lũy kế sau khi tổng hợp theo ngày

Một bản ghi bán hàng không nhất thiết tương ứng một ngày. Nếu muốn **doanh thu lũy kế theo ngày** và **trung bình doanh thu ba ngày có giao dịch gần nhất**, trước hết cần đưa dữ liệu về cấp **một hàng trên mỗi khu vực–ngày**.

```sql
WITH daily_paid AS (
    SELECT
        region,
        sold_on,
        COUNT(*) AS paid_rows,
        COUNT(amount) AS known_amount_rows,
        SUM(amount) AS day_revenue
    FROM demo_sales_window
    WHERE status = 'paid'
    GROUP BY region, sold_on
)
SELECT
    region,
    sold_on,
    paid_rows,
    known_amount_rows,
    day_revenue,
    SUM(day_revenue) OVER (
        PARTITION BY region
        ORDER BY sold_on
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_daily_revenue,
    ROUND(
        AVG(day_revenue) OVER (
            PARTITION BY region
            ORDER BY sold_on
            ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
        ),
        2
    ) AS avg_last_3_active_days
FROM daily_paid
ORDER BY region, sold_on;
```

### 17.1. Kết quả North

| `sold_on` | Hàng paid | Doanh thu ngày | Lũy kế theo ngày | AVG tối đa 3 ngày có paid gần nhất |
| --- | ---: | ---: | ---: | ---: |
| 2025-05-01 | 2 | 300 | 300 | 300.00 |
| 2025-05-02 | 1 | 50 | 350 | 175.00 |
| 2025-05-03 | 2 | 150 | 500 | 166.67 |
| 2025-05-05 | 1 | 100 | 600 | 100.00 |

Ở 03/05, trung bình ba giá trị **doanh thu theo ngày** là:

```text
(300 + 50 + 150) / 3 = 166.666...
```

Ở 05/05, ba ngày **có giao dịch paid gần nhất** là 02/05, 03/05, 05/05:

```text
(50 + 150 + 100) / 3 = 100
```

Ngày 04/05 không có paid ở North nên **không xuất hiện** trong `daily_paid` và không chiếm một hàng trong frame.

### 17.2. “Ba ngày có hoạt động” khác “ba ngày lịch”

Nếu yêu cầu thật sự là trung bình của **ba ngày lịch gần nhất**, kể cả ngày không có giao dịch, cần tạo tập ngày lịch rồi nối với dữ liệu đã tổng hợp.

Khung `ROWS BETWEEN 2 PRECEDING AND CURRENT ROW` trên `daily_paid` chọn **ba hàng ngày có dữ liệu**, không tự thêm ngày còn thiếu.

Trong PostgreSQL, có thể dùng `generate_series` để tạo lịch:

```sql
WITH calendar AS (
    SELECT gs::date AS sold_on
    FROM generate_series(
        TIMESTAMP '2025-05-01',
        TIMESTAMP '2025-05-05',
        INTERVAL '1 day'
    ) AS gs
),
north_daily AS (
    SELECT
        sold_on,
        SUM(amount) AS day_revenue
    FROM demo_sales_window
    WHERE status = 'paid'
      AND region = 'North'
    GROUP BY sold_on
),
completed_days AS (
    SELECT
        c.sold_on,
        COALESCE(n.day_revenue, 0::numeric) AS day_revenue
    FROM calendar AS c
    LEFT JOIN north_daily AS n
      ON n.sold_on = c.sold_on
)
SELECT
    sold_on,
    day_revenue,
    ROUND(
        AVG(day_revenue) OVER (
            ORDER BY sold_on
            ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
        ),
        2
    ) AS avg_last_3_calendar_days
FROM completed_days
ORDER BY sold_on;
```

Ở 05/05, ba ngày lịch là 03/05, 04/05, 05/05, nên:

```text
(150 + 0 + 100) / 3 = 83.33
```

Điều kiện `COALESCE(day_revenue,0)` ở đây **chủ động quy định không có giao dịch paid trong ngày là doanh thu 0**. Với ngày có paid nhưng toàn bộ amount chưa biết (như South 07/05), `SUM(amount)` cũng có thể `NULL`; có nên đổi nó thành 0 hay không là một quy tắc dữ liệu khác cần làm rõ trước khi áp dụng rộng rãi.

## 18. WHERE lọc trước cửa sổ; FILTER chỉ lọc đầu vào của aggregate

Sự khác biệt này rất quan trọng khi một báo cáo cần **hiển thị mọi trạng thái** nhưng **chỉ cộng các giao dịch paid**.

### 18.1. WHERE loại hàng khỏi tập nhìn thấy của mọi window function

```sql
SELECT
    sale_id,
    region,
    status,
    SUM(amount) OVER (
        PARTITION BY region
    ) AS region_revenue
FROM demo_sales_window
WHERE status = 'paid'
ORDER BY region, sale_id;
```

Kết quả chỉ chứa 13 hàng paid; giao dịch pending `6` và cancelled `12` **không hiện diện**. Mỗi cửa sổ chỉ nhìn những hàng đã qua `WHERE`.

### 18.2. FILTER giữ hàng nhưng chỉ cộng các giá trị phù hợp

PostgreSQL hỗ trợ `FILTER (WHERE ...)` trên aggregate window function:

```sql
SELECT
    sale_id,
    region,
    status,
    amount,
    SUM(amount) FILTER (
        WHERE status = 'paid'
    ) OVER (
        PARTITION BY region
    ) AS paid_revenue_in_region,
    COUNT(*) FILTER (
        WHERE status = 'paid'
    ) OVER (
        PARTITION BY region
    ) AS paid_rows_in_region
FROM demo_sales_window
ORDER BY region, sale_id;
```

Truy vấn này trả **cả 15 hàng**, bao gồm pending và cancelled, nhưng chỉ đưa hàng paid vào phép `SUM` và `COUNT` được lọc.

- Mọi hàng North, kể cả pending `6`, thấy `paid_revenue_in_region = 600` và `paid_rows_in_region = 6`.
- Mọi hàng South, kể cả cancelled `12`, thấy `paid_revenue_in_region = 500` và `paid_rows_in_region = 7`.

### 18.3. FILTER với tổng lũy kế

```sql
SELECT
    sale_id,
    sold_on,
    region,
    status,
    amount,
    SUM(amount) FILTER (
        WHERE status = 'paid'
    ) OVER (
        PARTITION BY region
        ORDER BY sold_on, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_paid_revenue
FROM demo_sales_window
ORDER BY region, sold_on, sale_id;
```

Ở North:

- Sau giao dịch paid `5`, tổng lũy kế là 500.
- Tại giao dịch `6` trạng thái pending, tổng **vẫn 500** vì amount 90 không được cộng.
- Sau giao dịch paid `7`, tổng tăng thành 600.

Nhưng giao dịch pending `6` vẫn **chiếm một vị trí** trong frame `ROWS`. Với cửa sổ trượt kiểu “ba hàng gần nhất”, sự hiện diện của các hàng không paid có thể làm kết quả khác với việc lọc `WHERE status='paid'` trước rồi mới chọn ba hàng. Phải phân biệt **ba hàng nguồn gần nhất, chỉ cộng paid** với **ba giao dịch paid gần nhất**.

### 18.4. Nếu DBMS không hỗ trợ FILTER

Có thể viết phép tổng có điều kiện bằng `CASE`:

```sql
SUM(
    CASE WHEN status = 'paid'
         THEN amount
         ELSE NULL
    END
) OVER (PARTITION BY region)
```

Đối với đếm số hàng paid:

```sql
SUM(
    CASE WHEN status = 'paid'
         THEN 1
         ELSE 0
    END
) OVER (PARTITION BY region)
```

Với một phân vùng có ít nhất một hàng, tổng `CASE` 1/0 bằng số hàng paid trong phân vùng. `COUNT(CASE WHEN status = 'paid' THEN 1 END) OVER (...)` cũng là một mẫu phổ biến. Nếu dùng `SUM(CASE ... THEN amount ELSE 0 END)`, cần hiểu rằng giá trị mặc định 0 có thể thay đổi ngữ nghĩa của nhóm không có amount đã biết so với `SUM` vốn trả `NULL`.

## 19. Window function được tính ở giai đoạn nào trong truy vấn?

Về cách suy luận logic, các hàm cửa sổ được đánh giá trên tập hàng còn lại **sau `FROM`, `WHERE`, `GROUP BY` và `HAVING`** của cùng cấp truy vấn. Chúng có thể được dùng trong `SELECT` và `ORDER BY` của cấp đó; không thể tùy ý gọi chúng trực tiếp trong `WHERE`/`GROUP BY`/`HAVING` cùng cấp.

### 19.1. Sai: dùng SUM OVER trực tiếp trong WHERE

```sql
-- CỐ Ý SAI trong PostgreSQL:
SELECT
    sale_id,
    amount
FROM demo_sales_window
WHERE SUM(amount) OVER (
    PARTITION BY region
) > 550;
```

`WHERE` lọc hàng trước giai đoạn tính window function, nên không dùng biểu thức cửa sổ theo cách này.

### 19.2. Đúng: dùng CTE hoặc truy vấn con

```sql
WITH paid_with_region_total AS (
    SELECT
        sale_id,
        region,
        amount,
        SUM(amount) OVER (
            PARTITION BY region
        ) AS region_revenue
    FROM demo_sales_window
    WHERE status = 'paid'
)
SELECT sale_id, region, amount, region_revenue
FROM paid_with_region_total
WHERE region_revenue > 550
ORDER BY sale_id;
```

Kết quả là **sáu giao dịch North**; South bị loại vì tổng khu vực 500 không vượt 550.

Cách viết này cũng giúp việc suy luận rõ ràng:

1. Tính tổng khu vực trên **đầy đủ tập paid**.
2. Ở cấp truy vấn ngoài, lọc những hàng có tổng khu vực lớn hơn 550.

### 19.3. HAVING làm thay đổi tập nhóm mà cửa sổ nhìn thấy

```sql
SELECT
    region,
    SUM(amount) AS region_revenue,
    SUM(SUM(amount)) OVER () AS total_of_visible_groups
FROM demo_sales_window
WHERE status = 'paid'
GROUP BY region
HAVING SUM(amount) > 500
ORDER BY region;
```

Sau `HAVING` chỉ còn North (600), vì South bằng 500 nên bị loại. `SUM(SUM(amount)) OVER ()` lúc này trả **600**, không phải 1100, vì window aggregate chỉ nhìn thấy hàng nhóm còn lại.

Nếu nghiệp vụ cần **tỷ trọng trên tất cả khu vực** rồi mới ẩn các khu vực nhỏ, hãy tính trên tất cả nhóm ở CTE trước, sau đó lọc ở truy vấn ngoài. Vị trí `HAVING` hay `WHERE` có thể thay đổi **mẫu số của một KPI**.

### 19.4. LIMIT không làm COUNT(*) OVER() thành số hàng của trang

```sql
SELECT
    sale_id,
    region,
    amount,
    COUNT(*) OVER () AS total_paid_rows
FROM demo_sales_window
WHERE status = 'paid'
ORDER BY sale_id
LIMIT 5;
```

Đầu ra chỉ có **5 hàng**, nhưng `total_paid_rows` trên mỗi hàng bằng **13**. Cửa sổ được tính trên tập 13 hàng paid trước khi `LIMIT` cuối cùng giới hạn số hàng trình bày.

Đây là cách tiện để trả danh sách phân trang kèm tổng số hàng sau bộ lọc. Tuy nhiên, nếu trang dùng `OFFSET` vượt quá cuối tập và trả **0 hàng**, sẽ không có hàng nào mang số `total_paid_rows`; ứng dụng có thể cần một truy vấn tổng riêng trong trường hợp đó.

## 20. Dùng WINDOW để đặt tên cấu hình lặp lại

Khi `SUM`, `AVG` và `COUNT` dùng cùng phân vùng, thứ tự và frame, viết lại cấu hình cửa sổ nhiều lần làm truy vấn dài và dễ lệch.

PostgreSQL hỗ trợ mệnh đề `WINDOW`:

```sql
SELECT
    sale_id,
    region,
    sold_on,
    amount,
    SUM(amount) OVER running_rows AS running_sum,
    ROUND(
        AVG(amount) OVER running_rows,
        2
    ) AS running_avg,
    COUNT(*) OVER running_rows AS running_row_count,
    COUNT(amount) OVER running_rows AS running_known_count
FROM demo_sales_window
WHERE status = 'paid'
WINDOW running_rows AS (
    PARTITION BY region
    ORDER BY sold_on, sale_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
ORDER BY region, sold_on, sale_id;
```

`running_rows` là tên cửa sổ, **không phải tên bảng**. Bốn window aggregate cùng áp dụng một cấu hình.

### 20.1. Vì sao WINDOW hữu ích?

- Đọc một lần là biết tất cả chỉ số được tính trên khung nào.
- Tránh vô ý dùng `ORDER BY sold_on` ở một chỉ số nhưng `ORDER BY sold_on, sale_id` ở chỉ số khác.
- Giúp so sánh `SUM`, `AVG` và `COUNT` trên cùng tập hàng.
- Giảm chi phí bảo trì câu SQL dài.

Dù có thể giúp optimizer nhận ra các cửa sổ tương thích, `WINDOW` **không phải một lời hứa rằng mọi hệ quản trị sẽ tính chỉ một lần và luôn nhanh hơn**. Cần kiểm tra kế hoạch thực tế.

## 21. ORDER BY trong OVER không đảm bảo thứ tự hiển thị

Hai chỗ `ORDER BY` có nhiệm vụ khác nhau:

```sql
SELECT
    sale_id,
    region,
    amount,
    SUM(amount) OVER (
        PARTITION BY region
        ORDER BY sold_on, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_revenue
FROM demo_sales_window
WHERE status = 'paid'
ORDER BY region DESC, sold_on DESC, sale_id DESC;
```

- `ORDER BY sold_on, sale_id` **bên trong `OVER`** quyết định thứ tự cộng dồn: từ giao dịch sớm đến muộn.
- `ORDER BY region DESC, sold_on DESC, sale_id DESC` **bên ngoài** quyết định cách các hàng được **trình bày cuối cùng**: khu vực và ngày theo chiều giảm.

Nhờ vậy, màn hình có thể hiển thị giao dịch mới nhất trước, trong khi mỗi dòng vẫn mang số lũy kế tính theo thứ tự thời gian tăng dần.

Nếu bỏ `ORDER BY` ngoài, SQL không cam kết thứ tự trả về, ngay cả khi cửa sổ có `ORDER BY`.

## 22. Những lỗi thường gặp với SUM, AVG, COUNT trên cửa sổ

| Cách viết hoặc suy luận dễ sai | Vì sao sai/dễ nhầm | Cách làm rõ |
| --- | --- | --- |
| Cho rằng `OVER (PARTITION BY region)` làm mất hàng | Nhầm window aggregate với `GROUP BY` | Window giữ từng hàng; GROUP BY gom hàng |
| Thêm `ORDER BY` vào `OVER` mà không xét frame | Mặc định có thể chuyển tổng toàn phân vùng thành lũy kế | Chỉ rõ `ROWS ...` hoặc `UNBOUNDED FOLLOWING` |
| `ORDER BY sold_on` khi có nhiều giao dịch cùng ngày | Peers làm `RANGE` và `ROWS` có ý nghĩa khác nhau | Chọn chính sách theo ngày hay theo từng dòng |
| `ROWS 2 PRECEDING` được hiểu là hai ngày trước | ROWS đếm hàng, không đếm ngày | Dùng RANGE theo giá trị ngày hoặc bảng ngày tổng hợp |
| `AVG(amount) = SUM(amount) / COUNT(*)` | Sai khi amount có `NULL` | Dùng `COUNT(amount)` hoặc `AVG(amount)` trực tiếp |
| `COUNT(amount)` để đếm mọi giao dịch | Bỏ giao dịch có amount `NULL` | Dùng `COUNT(*)` |
| Dùng `COALESCE(amount,0)` không có quy tắc | Biến thiếu dữ liệu thành số 0 | Chỉ dùng khi nghiệp vụ xác nhận |
| `COUNT(*) OVER()` sau GROUP BY để đếm giao dịch gốc | Nó đếm **hàng nhóm** | Dùng `SUM(COUNT(*)) OVER()` hoặc tính ở cấp gốc |
| `AVG(SUM(amount)) OVER()` cho AVG giao dịch | Đây là trung bình các tổng nhóm | Tính tổng tiền / tổng số amount đã biết |
| Lọc `WHERE status='paid'` khi muốn vẫn hiển thị pending | WHERE loại hàng trước cửa sổ | Dùng `FILTER`/`CASE` cho aggregate |
| Lọc window aggregate trực tiếp trong WHERE | Không hợp lệ ở cùng cấp truy vấn PostgreSQL | Tính trong CTE, lọc ở truy vấn ngoài |
| `HAVING` loại nhóm trước khi tính tỷ trọng tổng | Mẫu số chỉ còn các nhóm vượt HAVING | Tính trên toàn bộ nhóm trước, lọc sau |
| Giả định `ORDER BY` của `OVER` sắp đầu ra | Nó định nghĩa thứ tự tính toán cửa sổ | Thêm `ORDER BY` ngoài |
| Giả định ba hàng gần nhất luôn có ba amount đã biết | Frame có thể chứa `NULL` | Đối chiếu `COUNT(*)` và `COUNT(amount)` |
| `COUNT(DISTINCT col) OVER (...)` trong PostgreSQL | Không được hỗ trợ trực tiếp | Tổng hợp distinct trước rồi JOIN |
| Cộng các tổng khu vực được lặp trên từng hàng | Một tổng khu vực bị đếm nhiều lần | Chọn đúng cấp tổng hợp trước khi cộng |
| Dùng `LIMIT`/`OFFSET` để giới hạn hàng trước khi tính cửa sổ | LIMIT ở cấp cuối thường áp dụng sau window | Bọc dữ liệu đã giới hạn trong CTE nếu thật sự muốn cửa sổ trên trang |
| Chỉ số lũy kế không có khóa sắp xếp phân định | Khi đồng thời điểm, thứ tự hàng có thể không xác định | Kết thúc ORDER BY bằng khóa duy nhất nếu cần |

## 23. Hiệu năng và lựa chọn index

Window aggregate thường phải **phân vùng**, có thể phải **sắp xếp** và quản lý frame của các hàng liên quan. Chi phí phụ thuộc lượng dữ liệu, số phân vùng, kích thước từng phân vùng, số hàm cửa sổ và kiểu frame.

### 23.1. Index phù hợp với PARTITION BY và ORDER BY

Truy vấn lũy kế:

```sql
SELECT
    sale_id,
    region,
    sold_on,
    SUM(amount) OVER (
        PARTITION BY region
        ORDER BY sold_on, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_revenue
FROM demo_sales_window
WHERE status = 'paid';
```

có thể hưởng lợi từ index hỗ trợ thứ tự và bộ lọc, ví dụ PostgreSQL:

```sql
CREATE INDEX idx_demo_sales_window_paid_order
ON demo_sales_window (region, sold_on, sale_id)
INCLUDE (amount)
WHERE status = 'paid';
```

Index này lưu các hàng paid với thứ tự khóa `region, sold_on, sale_id`; `amount` được thêm như cột phục vụ truy vấn bằng `INCLUDE`, không phải cột quyết định thứ tự.

**Nhưng không có bảo đảm database sẽ dùng index.** Trên bảng vài chục hàng, quét tuần tự và sắp xếp có thể rẻ hơn. Với phân vùng lớn hoặc truy vấn nhiều frame, vẫn có thể có bước xử lý đáng kể sau khi đọc index.

### 23.2. EXPLAIN và WindowAgg

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    sale_id,
    SUM(amount) OVER (
        PARTITION BY region
        ORDER BY sold_on, sale_id
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS moving_sum
FROM demo_sales_window
WHERE status = 'paid';
```

Trong PostgreSQL, kế hoạch có thể xuất hiện nút `WindowAgg` và các bước đọc/sắp xếp. `EXPLAIN ANALYZE` **thực sự thực thi** truy vấn để đo thống kê. Ví dụ ở đây chỉ đọc dữ liệu tạm.

Cần quan sát lượng hàng đi qua window, số phân vùng, sort/I/O, thời gian và bộ nhớ. Không tự kết luận một frame `ROWS` luôn nhanh hơn một frame `RANGE` trên mọi dữ liệu hoặc phiên bản DBMS.

### 23.3. Nhiều cửa sổ có thứ tự khác nhau

Nếu một câu truy vấn vừa có:

```sql
SUM(amount) OVER (
    PARTITION BY region
    ORDER BY sold_on, sale_id
)
```

vừa có:

```sql
SUM(amount) OVER (
    PARTITION BY salesperson
    ORDER BY amount DESC
)
```

thì hai cấu hình yêu cầu các cách phân vùng và thứ tự khác nhau. Database có thể cần nhiều bước sắp xếp/xử lý.

Tránh thêm nhiều window function chỉ vì “không làm mất hàng”; mỗi phép đo cần có ý nghĩa nghiệp vụ và chi phí phù hợp.

### 23.4. Giới hạn dữ liệu đầu vào khi phù hợp

Nếu dashboard chỉ hiển thị doanh thu paid trong tháng 5/2025, bộ lọc `WHERE` có thể hạn chế số hàng đi vào cửa sổ:

```sql
WHERE status = 'paid'
  AND sold_on >= DATE '2025-05-01'
  AND sold_on <  DATE '2025-06-01'
```

Nhưng nếu chỉ muốn **hiển thị tháng 5 trong khi tổng lũy kế tính từ đầu năm**, không được lọc bỏ tháng trước **trước khi tính running sum**. Lúc đó phải tính trên phạm vi từ đầu năm trong CTE, sau đó lọc tháng hiển thị ở cấp ngoài.

Việc đặt bộ lọc ảnh hưởng **cả ngữ nghĩa lẫn hiệu năng**.

## 24. Khác biệt giữa các hệ quản trị SQL

`SUM(...) OVER (...)`, `AVG(...) OVER (...)` và `COUNT(...) OVER (...)` là các cấu trúc quen thuộc của SQL phân tích, nhưng giới hạn hỗ trợ và cú pháp frame khác nhau theo DBMS.

| Hệ quản trị | Hỗ trợ tổng quát | Điểm cần lưu ý |
| --- | --- | --- |
| **PostgreSQL** | Window aggregate, `PARTITION BY`, `ORDER BY`, `ROWS`, `RANGE`, `GROUPS`, `FILTER` | Ví dụ chính của bài; không hỗ trợ `COUNT(DISTINCT ...) OVER (...)` trực tiếp |
| **SQL Server** | `SUM`/`AVG`/`COUNT` với `OVER`; `PARTITION BY`, `ORDER BY` và các frame được hỗ trợ | Kiểm tra giới hạn `RANGE`, không dùng nguyên `FILTER (WHERE ...)` của PostgreSQL; có thể dùng `CASE` |
| **MySQL 8.0+** | Hỗ trợ window aggregate và nhiều loại frame | Kiểm tra cú pháp/giới hạn offset `RANGE` và hàm có hỗ trợ trong phiên bản đang dùng; `FILTER` không phải cú pháp MySQL thông dụng |
| **Oracle Database** | Analytic `SUM`/`AVG`/`COUNT` và các frame theo cú pháp Oracle | Có các quy tắc riêng cho `RANGE`/`ROWS`, peer và các giới hạn biểu thức |
| **SQLite 3.25.0+** | Hỗ trợ window functions, với các tính năng bổ sung qua các phiên bản sau | Kiểm tra phiên bản cụ thể cho `GROUPS`/`FILTER` và các tính năng mở rộng |
| **BigQuery** | Analytic aggregate với `OVER`, hỗ trợ `QUALIFY` ở nhiều bài toán | Cú pháp frame/thời gian khác PostgreSQL; `QUALIFY` cho phép lọc kết quả window tại cùng query block |

### 24.1. Không suy đoán mặc định frame khi đổi DBMS

Ngay cả khi hai hệ cùng chấp nhận:

```sql
SUM(amount) OVER (
    PARTITION BY region
    ORDER BY sold_on
)
```

hãy kiểm tra quy tắc mặc định trên engine cụ thể, nhất là khi **có ngày trùng nhau**. Để bài học và ứng dụng dễ đọc hơn, nên viết frame tường minh khi cần **từng hàng** hoặc **toàn bộ phân vùng**.

### 24.2. Chuyển kỹ thuật FILTER sang CASE

Ví dụ `FILTER`:

```sql
SUM(amount) FILTER (
    WHERE status = 'paid'
) OVER (PARTITION BY region)
```

có thể diễn đạt bằng `CASE` ở nhiều hệ:

```sql
SUM(
    CASE WHEN status = 'paid' THEN amount END
) OVER (PARTITION BY region)
```

Với hàng không paid, biểu thức `CASE` không có `ELSE` trả `NULL`, nên `SUM` bỏ qua. Cần xem xét kiểu dữ liệu và quy tắc xử lý `NULL` của từng DBMS trong những trường hợp biên.

### 24.3. PostgreSQL không có QUALIFY thông dụng

Với PostgreSQL, lọc theo `running_sum` hay `region_total` thường cần CTE/subquery. Một số công cụ phân tích có `QUALIFY` nên viết gọn hơn, nhưng không nên sao chép `QUALIFY` sang PostgreSQL mà không kiểm tra.

## 25. Bài tập thực hành và đáp án

Các bài dưới đây dùng bảng `demo_sales_window` ở phần 2. Nên dự đoán kết quả bằng bảng paid trước, sau đó mới thực thi SQL.

### Bài 1 — Tổng doanh thu của từng khu vực trên mỗi giao dịch

```sql
SELECT
    sale_id,
    region,
    SUM(amount) OVER (
        PARTITION BY region
    ) AS region_revenue
FROM demo_sales_window
WHERE status = 'paid'
ORDER BY region, sale_id;
```

**Đáp án:** North = 600 trên sáu hàng North; South = 500 trên bảy hàng South. Tổng cộng vẫn có 13 hàng, không rút còn hai hàng như `GROUP BY`.

### Bài 2 — Tổng và trung bình toàn bộ paid

```sql
SELECT
    sale_id,
    SUM(amount) OVER () AS all_revenue,
    AVG(amount) OVER () AS all_average
FROM demo_sales_window
WHERE status = 'paid'
ORDER BY sale_id;
```

**Đáp án:** Mỗi hàng mang `all_revenue = 1100` và `all_average = 100`. Hai amount `NULL` bị bỏ qua ở `SUM` và `AVG`.

### Bài 3 — Đếm hàng so với đếm amount

```sql
SELECT
    region,
    COUNT(*) OVER (PARTITION BY region) AS n_rows,
    COUNT(amount) OVER (PARTITION BY region) AS n_known
FROM demo_sales_window
WHERE status = 'paid'
ORDER BY region, sale_id;
```

**Đáp án:** North có `n_rows=6`, `n_known=5`; South có `n_rows=7`, `n_known=6`.

### Bài 4 — Tổng lũy kế của North tại sale_id = 5

Truy vấn:

```sql
SELECT
    sale_id,
    SUM(amount) OVER (
        PARTITION BY region
        ORDER BY sold_on, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_revenue
FROM demo_sales_window
WHERE status = 'paid'
ORDER BY region, sold_on, sale_id;
```

**Đáp án:** Ở North `sale_id=5`, lũy kế = `100+200+50+150 = 500`. Giao dịch 4 có `NULL` nên không tăng tổng.

### Bài 5 — COUNT lũy kế tại giao dịch North số 4

Với cùng frame lũy kế:

```sql
COUNT(*) OVER (
    PARTITION BY region
    ORDER BY sold_on, sale_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
```

và `COUNT(amount)` tương ứng, giá trị là bao nhiêu?

**Đáp án:** `COUNT(*)=4`, `COUNT(amount)=3`, vì giao dịch 4 có `NULL`.

### Bài 6 — RANGE mặc định làm gì khi có giao dịch cùng ngày?

```sql
SELECT
    sale_id,
    sold_on,
    SUM(amount) OVER (
        PARTITION BY region
        ORDER BY sold_on
    ) AS running_by_date
FROM demo_sales_window
WHERE status = 'paid'
  AND region = 'North'
ORDER BY sold_on, sale_id;
```

**Đáp án:** ID 1 và 2 cùng ngày 01/05 có tổng `300` trên cả hai hàng; ID 4 và 5 cùng ngày 03/05 có tổng `500` trên cả hai hàng. Đây là hành vi của nhóm peers trong frame mặc định `RANGE` của PostgreSQL.

### Bài 7 — Trung bình ba hàng gần nhất tại sale_id = 4

```sql
AVG(amount) OVER (
    PARTITION BY region
    ORDER BY sold_on, sale_id
    ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
)
```

**Đáp án:** Frame chứa amount `[200,50,NULL]`, nên `AVG = (200+50)/2 = 125`. `COUNT(*)` của frame là 3, `COUNT(amount)` là 2.

### Bài 8 — Trung bình ba hàng gần nhất tại sale_id = 7

**Đáp án:** Frame North chứa `[NULL,150,100]`, nên `AVG = 125` và `SUM = 250`; có ba hàng nhưng hai amount không `NULL`.

### Bài 9 — Ba ngày lịch tại North ngày 03/05

Với:

```sql
SUM(amount) OVER (
    PARTITION BY region
    ORDER BY sold_on::timestamp
    RANGE BETWEEN INTERVAL '2 days' PRECEDING
              AND CURRENT ROW
)
```

giá trị ở `sale_id=5` là bao nhiêu?

**Đáp án:** 500. Khoảng ngày 01/05–03/05 bao gồm amount 100, 200, 50, `NULL`, 150. Đây không phải tổng của ba hàng gần nhất, vốn là 200.

### Bài 10 — COUNT(*) OVER() trong truy vấn GROUP BY

```sql
SELECT
    region,
    COUNT(*) AS paid_count,
    COUNT(*) OVER () AS groups_count,
    SUM(COUNT(*)) OVER () AS total_paid_count
FROM demo_sales_window
WHERE status = 'paid'
GROUP BY region
ORDER BY region;
```

**Đáp án:** `groups_count=2` trên cả hai hàng khu vực; `total_paid_count=13`; `paid_count` là 6 North và 7 South.

### Bài 11 — Hai tỷ trọng khu vực

```sql
SELECT
    region,
    SUM(amount) AS revenue,
    ROUND(
        100 * SUM(amount)
        / NULLIF(SUM(SUM(amount)) OVER (), 0),
        2
    ) AS pct
FROM demo_sales_window
WHERE status = 'paid'
GROUP BY region
ORDER BY region;
```

**Đáp án:** North `54.55%`; South `45.45%`, vì tổng doanh thu paid = 1100.

### Bài 12 — Lọc sau khi tính SUM OVER

Yêu cầu giữ các giao dịch thuộc khu vực có doanh thu paid **lớn hơn 550**. Viết đúng:

```sql
WITH totals AS (
    SELECT
        sale_id,
        region,
        SUM(amount) OVER (
            PARTITION BY region
        ) AS region_total
    FROM demo_sales_window
    WHERE status = 'paid'
)
SELECT sale_id, region, region_total
FROM totals
WHERE region_total > 550
ORDER BY sale_id;
```

**Đáp án:** Chỉ sáu giao dịch North. Không dùng `SUM(...) OVER (...)` trực tiếp trong `WHERE` của truy vấn bên trong.

### Bài 13 — Tính paid nhưng giữ cả pending/cancelled

```sql
SELECT
    sale_id,
    status,
    region,
    SUM(amount) FILTER (
        WHERE status = 'paid'
    ) OVER (
        PARTITION BY region
    ) AS region_paid_revenue
FROM demo_sales_window
ORDER BY region, sale_id;
```

**Đáp án:** Trả **15 hàng**, bao gồm pending ID 6 và cancelled ID 12. Tổng paid khu vực vẫn 600 ở North và 500 ở South.

### Bài 14 — Moving AVG theo ngày có hoạt động khác theo ngày lịch

Tập `daily_paid` của North có doanh thu ngày:

```text
01/05 = 300
02/05 = 50
03/05 = 150
05/05 = 100
```

Hỏi trung bình ba **ngày có paid gần nhất** tại 05/05 và ba **ngày lịch gần nhất** khi điền ngày 04/05 bằng 0.

**Đáp án:** Ba ngày có paid gần nhất: `(50+150+100)/3 = 100`. Ba ngày lịch 03/05–05/05: `(150+0+100)/3 = 83.33`.

### Bài 15 — Tại sao GROUP BY rồi AVG(SUM(amount)) lại cho 550?

Giải thích:

```sql
SELECT
    region,
    AVG(SUM(amount)) OVER () AS avg_region_revenue
FROM demo_sales_window
WHERE status = 'paid'
GROUP BY region;
```

**Đáp án:** Sau `GROUP BY` có hai hàng doanh thu khu vực, North 600 và South 500. `AVG` bên ngoài tính trung bình **hai tổng khu vực**: 550. Nó không tính trung bình amount của 11 giao dịch có tiền (100).

### Bài 16 — Khác nhau giữa lọc hàng và lọc aggregate

Hai câu có luôn giống nhau khi tính “ba giao dịch paid gần nhất” không?

**Câu A:** `WHERE status='paid'`, sau đó `ROWS BETWEEN 2 PRECEDING AND CURRENT ROW`.

**Câu B:** Giữ mọi status, rồi `SUM(amount) FILTER(WHERE status='paid') OVER(...ROWS BETWEEN 2 PRECEDING AND CURRENT ROW)`.

**Đáp án:** Không. Câu A chọn **ba hàng paid** gần nhất; câu B chọn **ba hàng bất kể status**, sau đó chỉ cộng những hàng paid trong ba hàng đó. Pending/cancelled có thể chiếm vị trí trong frame của câu B.

### Bài 17 — Một frame chỉ có NULL

```sql
WITH t(n, amount) AS (
    VALUES (1, NULL::numeric), (2, NULL::numeric)
)
SELECT
    n,
    COUNT(*) OVER (
        ORDER BY n ROWS BETWEEN UNBOUNDED PRECEDING
                            AND CURRENT ROW
    ) AS rows_seen,
    COUNT(amount) OVER (
        ORDER BY n ROWS BETWEEN UNBOUNDED PRECEDING
                            AND CURRENT ROW
    ) AS known_values,
    SUM(amount) OVER (
        ORDER BY n ROWS BETWEEN UNBOUNDED PRECEDING
                            AND CURRENT ROW
    ) AS total
FROM t
ORDER BY n;
```

**Đáp án:** Hàng 1: `rows_seen=1`, `known_values=0`, `total=NULL`. Hàng 2: `rows_seen=2`, `known_values=0`, `total=NULL`. `SUM` không tự đổi `NULL` thành 0.

### Bài 18 — Tự chọn frame cho ba yêu cầu

Chọn cấu trúc thích hợp:

1. Tổng tiền paid **mọi giao dịch trong cùng khu vực**, không phụ thuộc ngày.
2. Tổng tiền paid **từ giao dịch đầu đến giao dịch hiện tại** trong khu vực.
3. Trung bình amount của **tối đa ba giao dịch paid gần nhất** trong khu vực.

**Đáp án gợi ý:**

```sql
-- (1) Toàn phân vùng:
SUM(amount) OVER (
    PARTITION BY region
)

-- (2) Lũy kế theo từng hàng:
SUM(amount) OVER (
    PARTITION BY region
    ORDER BY sold_on, sale_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)

-- (3) Trung bình ba hàng gần nhất:
AVG(amount) OVER (
    PARTITION BY region
    ORDER BY sold_on, sale_id
    ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
)
```

Điều kiện `WHERE status='paid'` của truy vấn bao ngoài phải được đặt phù hợp nếu chỉ muốn tính trên tập paid.

## 26. Quy trình chọn SUM, AVG, COUNT trên cửa sổ

Khi được yêu cầu một chỉ số tổng hợp nhưng vẫn giữ dữ liệu chi tiết, hãy lần lượt trả lời:

1. **Một hàng kết quả đại diện cho gì?** Giao dịch, ngày, khách hay khu vực? Chọn đúng cấp dữ liệu trước khi tính.
2. **Có cần giữ từng hàng không?** Nếu có, cân nhắc window aggregate; nếu chỉ cần mỗi nhóm một hàng, `GROUP BY` có thể là lựa chọn rõ hơn.
3. **Chỉ số nào cần tính?** Tổng giá trị → `SUM`; trung bình các giá trị đã biết → `AVG`; số hàng → `COUNT(*)`; số giá trị không `NULL` → `COUNT(cột)`.
4. **Phân vùng theo chiều nào?** Toàn bảng với `OVER()`, theo `region`, hay theo `region,salesperson`?
5. **Có yếu tố thứ tự không?** Nếu cần lũy kế hoặc trượt, phải định nghĩa `ORDER BY` bên trong `OVER`; thêm khóa phá hòa khi muốn kết quả theo từng hàng có thể tái lập.
6. **Frame thực sự là gì?** Toàn phân vùng, từ đầu đến hiện tại, ba hàng, ba ngày lịch hay hai nhóm ngày có dữ liệu?
7. **Có nhiều hàng đồng khóa ORDER BY không?** Kiểm tra peers và sự khác nhau giữa `ROWS`, `RANGE`, `GROUPS`.
8. **Xử lý `NULL` theo quy tắc nào?** `SUM`/`AVG` bỏ qua giá trị thiếu, `COUNT(*)` vẫn đếm hàng; không tự đổi thiếu thành 0.
9. **WHERE, HAVING hoặc FILTER đang loại gì?** Bộ lọc trước cửa sổ thay đổi hàng đầu vào; `FILTER` chỉ thay đổi những hàng đóng góp vào một aggregate.
10. **Có GROUP BY trước window không?** Khi đó window nhìn các hàng đã nhóm; `COUNT(*) OVER()` đếm nhóm, `SUM(SUM(...)) OVER()` cộng tổng các nhóm.
11. **Có cần lọc theo kết quả cửa sổ không?** Trong PostgreSQL, tính trong CTE/subquery, rồi lọc ở truy vấn ngoài.
12. **Kết quả có cần thứ tự hiển thị hay phân trang?** Thêm `ORDER BY` ngoài; không nhầm với `ORDER BY` trong `OVER`.
13. **DBMS có hỗ trợ đúng cú pháp không?** Xác minh `RANGE` offset, `GROUPS`, `FILTER` và `DISTINCT` trong window aggregate theo phiên bản.
14. **Đã kiểm chứng bằng trường hợp biên chưa?** Hãy thử hai giao dịch cùng ngày, một amount `NULL`, ngày không có giao dịch, phân vùng chỉ một hàng và frame rỗng.

Kết luận: **`SUM`, `AVG` và `COUNT` trên cửa sổ không chỉ là phép tổng hợp thêm chữ `OVER`.** Kết quả của chúng phụ thuộc trực tiếp vào **tập hàng sau bộ lọc**, **phân vùng**, **thứ tự**, **khung cửa sổ**, và **ngữ nghĩa `NULL`**. Khi xác định rõ năm yếu tố này, bạn có thể tạo đúng tổng khu vực, tổng lũy kế, trung bình trượt, số đếm và tỷ trọng mà vẫn giữ được chi tiết từng hàng để phân tích và đối chiếu.

