# SUM/AVG chạy dồn và trung bình trượt trong Oracle

## 1. Từ tổng hợp theo nhóm đến tính toán theo từng dòng

Một báo cáo doanh thu thường cần nhiều cách nhìn trên cùng dữ liệu:

- Tổng doanh thu từ đầu kỳ đến từng ngày.
- Số dư lũy kế của từng tài khoản sau mỗi giao dịch.
- Doanh thu trung bình của ba tháng gần nhất.
- Giá trị trung bình bảy ngày để làm mượt biến động.
- Trung bình lũy kế từ đầu năm đến thời điểm hiện tại.

Nếu chỉ dùng `GROUP BY`, Oracle gom nhiều hàng thành một hàng cho mỗi nhóm. Nhưng với các phép tính chạy dồn hoặc trung bình trượt, ta thường muốn **giữ lại từng hàng gốc** và bổ sung một cột kết quả tính toán theo một cửa sổ hàng hoặc giá trị xung quanh hàng hiện tại. Đây là vai trò của **hàm phân tích (analytic function)**.

Hai hàm trọng tâm:

- `SUM(...) OVER (...)`: tính tổng trên một cửa sổ hàng, thường dùng cho tổng chạy dồn hoặc tổng trượt.
- `AVG(...) OVER (...)`: tính trung bình trên cửa sổ đó, thường dùng cho trung bình chạy dồn hoặc trung bình trượt.

Ví dụ dữ liệu doanh thu theo ngày:

| Ngày | Doanh thu |
|---|---:|
| 01/11 | 100 |
| 02/11 | 150 |
| 03/11 | 50 |
| 04/11 | 200 |

Tổng chạy dồn lần lượt là `100`, `250`, `300`, `500`. Trung bình trượt ba ngày tại 03/11 là `(100 + 150 + 50) / 3 = 100`; tại 04/11 là `(150 + 50 + 200) / 3 = 133,33`.

Bài học thuộc chương **Hàm phân tích**, trình bày cú pháp `OVER`, phân vùng và sắp xếp, khung cửa sổ `ROWS`/`RANGE`, cách tính tổng/trung bình chạy dồn, trung bình trượt theo số quan sát hoặc theo thời gian, ảnh hưởng của NULL và kỳ thiếu, cùng các mẫu truy vấn có thể áp dụng trong báo cáo Oracle.

## 2. Cấu trúc của hàm phân tích

Cú pháp khái quát:

```sql
aggregate_function(expression)
OVER (
    [PARTITION BY partition_expression]
    [ORDER BY sort_expression]
    [windowing_clause]
)
```

Với `SUM` và `AVG`, phần `OVER` xác định tập hàng mà hàm sẽ tính cho mỗi hàng kết quả.

| Thành phần | Vai trò |
|---|---|
| `SUM(amount)` | Tính tổng biểu thức `amount` trong cửa sổ |
| `AVG(amount)` | Tính trung bình biểu thức `amount` trong cửa sổ |
| `PARTITION BY account_id` | Chia dữ liệu thành các nhóm độc lập; mỗi tài khoản có cửa sổ riêng |
| `ORDER BY transaction_date` | Xác định thứ tự hàng để tính chạy dồn hoặc trượt |
| `ROWS` / `RANGE` | Xác định ranh giới cửa sổ quanh hàng hiện tại |

### 2.1. Khác biệt giữa GROUP BY và OVER

`GROUP BY`:

```sql
SELECT account_id,
       SUM(amount) AS account_total
FROM transactions
GROUP BY account_id;
```

Truy vấn trả một hàng cho mỗi tài khoản.

Hàm phân tích:

```sql
SELECT transaction_id,
       account_id,
       transaction_date,
       amount,
       SUM(amount) OVER (
           PARTITION BY account_id
       ) AS account_total
FROM transactions;
```

Truy vấn vẫn trả từng giao dịch, đồng thời lặp tổng tài khoản trên các hàng thuộc cùng tài khoản.

**Hàm phân tích không gom các hàng thành một hàng nhóm.** Nó tính trên cửa sổ rồi gắn kết quả vào từng hàng của tập kết quả.

### 2.2. Không có PARTITION BY

Nếu bỏ `PARTITION BY`, cửa sổ hoạt động trên toàn bộ tập kết quả của query block:

```sql
SELECT transaction_id,
       amount,
       SUM(amount) OVER () AS grand_total
FROM transactions;
```

`GRAND_TOTAL` là tổng của mọi hàng được đưa vào hàm phân tích. Mỗi hàng vẫn xuất hiện riêng.

### 2.3. PARTITION BY tách các chuỗi độc lập

```sql
SELECT account_id,
       transaction_date,
       amount,
       SUM(amount) OVER (
           PARTITION BY account_id
       ) AS account_total
FROM transactions;
```

Tổng của tài khoản 10 không cộng lẫn giao dịch tài khoản 20. Với bài toán số dư, doanh thu chạy dồn hoặc trung bình theo khách hàng, `PARTITION BY` thường là phần không thể thiếu.

## 3. SUM chạy dồn (running total)

**Tổng chạy dồn** là tổng từ điểm bắt đầu của một chuỗi đến hàng hiện tại. Trong Oracle, cách viết tường minh:

```sql
SUM(amount) OVER (
    PARTITION BY account_id
    ORDER BY transaction_date, transaction_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
```

Ý nghĩa:

- `PARTITION BY account_id`: bắt đầu lại tổng khi sang tài khoản khác.
- `ORDER BY transaction_date, transaction_id`: xác định thứ tự giao dịch.
- `UNBOUNDED PRECEDING`: bắt đầu từ hàng đầu tiên trong partition.
- `CURRENT ROW`: kết thúc ở hàng hiện tại.
- `ROWS`: khung được xác định theo số hàng vật lý trong thứ tự đã chọn.

### 3.1. Ví dụ tổng doanh thu chạy dồn

Giả sử bảng `daily_sales` có một hàng cho mỗi ngày:

| sale_day | revenue |
|---|---:|
| 01/11/2026 | 100 |
| 02/11/2026 | 150 |
| 03/11/2026 | 50 |
| 04/11/2026 | 200 |

Truy vấn:

```sql
SELECT sale_day,
       revenue,
       SUM(revenue) OVER (
           ORDER BY sale_day
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS running_revenue
FROM daily_sales
ORDER BY sale_day;
```

Kết quả:

| sale_day | revenue | running_revenue |
|---|---:|---:|
| 01/11 | 100 | 100 |
| 02/11 | 150 | 250 |
| 03/11 | 50 | 300 |
| 04/11 | 200 | 500 |

### 3.2. Tổng chạy dồn theo tài khoản

```sql
SELECT account_id,
       transaction_id,
       transaction_date,
       amount,
       SUM(amount) OVER (
           PARTITION BY account_id
           ORDER BY transaction_date, transaction_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS running_amount
FROM transactions
ORDER BY account_id, transaction_date, transaction_id;
```

Khi chuyển sang tài khoản khác, tổng bắt đầu lại. Nếu `transaction_date` có thể trùng, thêm một khóa phân định như `transaction_id` để kết quả theo từng hàng ổn định.

### 3.3. Tính số dư chạy dồn

Nếu `amount` là số tiền phát sinh, có thể biểu diễn tiền vào là dương và tiền ra là âm:

```sql
SELECT account_id,
       transaction_id,
       transaction_date,
       amount,
       SUM(amount) OVER (
           PARTITION BY account_id
           ORDER BY transaction_date, transaction_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS movement_balance
FROM account_transactions
ORDER BY account_id, transaction_date, transaction_id;
```

Nếu tài khoản có số dư đầu kỳ, cộng thêm số dư đó:

```sql
SELECT t.account_id,
       t.transaction_id,
       t.transaction_date,
       t.amount,
       b.opening_balance
       + SUM(t.amount) OVER (
             PARTITION BY t.account_id
             ORDER BY t.transaction_date, t.transaction_id
             ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
         ) AS closing_balance
FROM account_transactions t
JOIN account_opening_balance b
  ON b.account_id = t.account_id
ORDER BY t.account_id, t.transaction_date, t.transaction_id;
```

Ví dụ giả định mỗi tài khoản có đúng một số dư đầu kỳ. Nếu bảng số dư có nhiều bản ghi cho một tài khoản, phải chuẩn hóa hoặc tổng hợp trước khi JOIN để không nhân bản giao dịch.

### 3.4. Tổng chạy dồn theo tháng

Nếu bảng có nhiều giao dịch trong tháng và muốn một hàng mỗi tháng:

```sql
WITH monthly_revenue AS (
    SELECT TRUNC(sale_date, 'MM') AS month_start,
           SUM(amount) AS revenue
    FROM sales
    GROUP BY TRUNC(sale_date, 'MM')
)
SELECT month_start,
       revenue,
       SUM(revenue) OVER (
           ORDER BY month_start
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS running_revenue
FROM monthly_revenue
ORDER BY month_start;
```

`GROUP BY` tạo hạt dữ liệu theo tháng trước; hàm phân tích tính tổng chạy dồn trên các hàng tháng đó. Nếu một tháng không có giao dịch, tháng ấy không tự xuất hiện trong `monthly_revenue`; phần về calendar bên dưới giải quyết tình huống này.

## 4. AVG chạy dồn (running average)

**Trung bình chạy dồn** là trung bình của toàn bộ các giá trị từ đầu chuỗi đến hàng hiện tại:

```sql
AVG(amount) OVER (
    PARTITION BY account_id
    ORDER BY transaction_date, transaction_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
```

Ví dụ giá trị `100, 150, 50, 200`:

| Hàng | Giá trị | Tổng chạy dồn | Trung bình chạy dồn |
|---:|---:|---:|---:|
| 1 | 100 | 100 | 100 |
| 2 | 150 | 250 | 125 |
| 3 | 50 | 300 | 100 |
| 4 | 200 | 500 | 125 |

Truy vấn:

```sql
SELECT sale_day,
       revenue,
       AVG(revenue) OVER (
           ORDER BY sale_day
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS running_average
FROM daily_sales
ORDER BY sale_day;
```

`AVG` tự bỏ qua giá trị NULL trong biểu thức. Vì vậy mẫu số là số giá trị non-NULL đã gặp, không nhất thiết bằng số hàng.

### 4.1. Trung bình chạy dồn theo tài khoản

```sql
SELECT account_id,
       transaction_id,
       transaction_date,
       amount,
       AVG(amount) OVER (
           PARTITION BY account_id
           ORDER BY transaction_date, transaction_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS running_avg_amount
FROM transactions
ORDER BY account_id, transaction_date, transaction_id;
```

Mỗi tài khoản có một trung bình riêng, được cập nhật sau từng giao dịch theo thứ tự đã định nghĩa.

### 4.2. Running average không phải moving average

| Loại | Phạm vi tính | Đặc điểm |
|---|---|---|
| Running average | Từ đầu partition đến hàng hiện tại | Cửa sổ mở rộng dần |
| Moving average | Một cửa sổ có độ rộng giới hạn quanh hàng hiện tại | Cửa sổ trượt khi đi qua chuỗi |

Ví dụ với bốn giá trị `100, 150, 50, 200`:

- Running average: `100`, `125`, `100`, `125`.
- Moving average ba hàng: `100`, `125`, `100`, `133,33`.

Hai phép tính có thể cho kết quả giống nhau ở vài hàng đầu nhưng mang ý nghĩa khác nhau.

## 5. Trung bình trượt theo số hàng với ROWS

**Moving average** tính trung bình trên một cửa sổ có kích thước hữu hạn. Với ba quan sát gần nhất, dùng:

```sql
AVG(amount) OVER (
    ORDER BY sale_day
    ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
)
```

`2 PRECEDING` là hai hàng trước hàng hiện tại; cộng với `CURRENT ROW` tạo tối đa ba hàng.

### 5.1. Ví dụ trung bình trượt ba ngày quan sát

| Ngày | Revenue | Moving average 3 hàng |
|---|---:|---:|
| 01/11 | 100 | 100 |
| 02/11 | 150 | 125 |
| 03/11 | 50 | 100 |
| 04/11 | 200 | 133,33 |

Truy vấn:

```sql
SELECT sale_day,
       revenue,
       AVG(revenue) OVER (
           ORDER BY sale_day
           ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
       ) AS moving_avg_3_rows
FROM daily_sales
ORDER BY sale_day;
```

Ở hai hàng đầu, cửa sổ chưa đủ ba hàng nên Oracle tính trung bình trên số hàng hiện có. Đây là hành vi mặc định của khung; không tự bổ sung hàng giả để đủ ba.

### 5.2. Tổng trượt ba hàng

```sql
SELECT sale_day,
       revenue,
       SUM(revenue) OVER (
           ORDER BY sale_day
           ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
       ) AS moving_sum_3_rows
FROM daily_sales
ORDER BY sale_day;
```

`SUM` và `AVG` dùng cùng cách xác định cửa sổ; chỉ khác phép tổng hợp bên trong.

### 5.3. Cửa sổ bảy quan sát gần nhất

```sql
AVG(metric_value) OVER (
    PARTITION BY entity_id
    ORDER BY observation_date, observation_id
    ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
) AS moving_avg_7_observations
```

Đây là trung bình trên tối đa bảy **hàng quan sát** gần nhất cho mỗi đối tượng. Nếu một ngày có hai hàng, cả hai đều chiếm vị trí trong cửa sổ; nếu một ngày không có hàng, cửa sổ vẫn trượt qua bảy hàng hiện có.

Do đó, `ROWS BETWEEN 6 PRECEDING AND CURRENT ROW` **không tự có nghĩa là bảy ngày lịch**. Nó có nghĩa là tối đa bảy hàng trong thứ tự.

### 5.4. Cửa sổ đối xứng quanh hàng hiện tại

Có thể tính trung bình trên hai hàng trước, hàng hiện tại và hai hàng sau:

```sql
AVG(metric_value) OVER (
    PARTITION BY entity_id
    ORDER BY observation_date, observation_id
    ROWS BETWEEN 2 PRECEDING AND 2 FOLLOWING
) AS centered_avg_5_rows
```

Đây là trung bình trượt **căn giữa** (centered moving average). Nó sử dụng dữ liệu tương lai so với hàng hiện tại, vì vậy phù hợp cho phân tích lịch sử/làm mượt chuỗi sau khi đã có dữ liệu, nhưng không phù hợp nếu cần một chỉ số chỉ dùng thông tin đã biết tại thời điểm đó.

## 6. ROWS và RANGE: hai cách định nghĩa cửa sổ khác nhau

Đây là phần quan trọng nhất khi thiết kế moving average.

- `ROWS`: xác định cửa sổ bằng **số hàng** trước/sau hàng hiện tại.
- `RANGE`: xác định cửa sổ bằng **khoảng giá trị** của biểu thức sắp xếp; với ngày giờ, có thể dùng khoảng thời gian.

### 6.1. ROWS theo số quan sát

```sql
AVG(amount) OVER (
    ORDER BY sale_date
    ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
)
```

Tối đa bảy hàng gần nhất, bất kể khoảng cách thời gian giữa chúng.

Nếu dữ liệu có ngày 01, 02, 10, 11:

- Hàng ngày 10 vẫn nhìn thấy hai hàng trước là ngày 01 và 02 nếu dùng khung ba hàng.
- Khoảng cách lịch giữa các hàng không được xét trong ROWS.

### 6.2. RANGE theo khoảng ngày

Nếu cần trung bình của bảy ngày lịch gần nhất, có thể dùng:

```sql
AVG(daily_amount) OVER (
    PARTITION BY account_id
    ORDER BY activity_day
    RANGE BETWEEN INTERVAL '6' DAY PRECEDING AND CURRENT ROW
) AS moving_avg_7_calendar_days
```

Với `activity_day` là kiểu DATE hoặc TIMESTAMP phù hợp, khung bắt đầu tại thời điểm/ngày hiện tại trừ sáu ngày và kết thúc tại giá trị hiện tại. Cửa sổ gồm khoảng bảy ngày tính cả ngày hiện tại theo ranh giới đã chọn.

Khung RANGE theo interval dùng biểu thức sắp xếp ngày giờ; Oracle có quy tắc hạn chế riêng cho offset RANGE. Khi dùng offset như `INTERVAL '6' DAY PRECEDING`, hãy giữ một biểu thức sort key ngày giờ tương thích trong `ORDER BY` của analytic clause.

### 6.3. Ví dụ so sánh ROWS và RANGE

Giả sử có dữ liệu:

| Ngày | Giá trị |
|---|---:|
| 01/11 | 10 |
| 02/11 | 20 |
| 10/11 | 30 |
| 11/11 | 40 |

Tại ngày 10/11:

- `ROWS BETWEEN 2 PRECEDING AND CURRENT ROW` có thể lấy cả 01/11, 02/11 và 10/11 (ba hàng hiện có).
- `RANGE BETWEEN INTERVAL '6' DAY PRECEDING AND CURRENT ROW` chỉ lấy các hàng trong khoảng 04/11 đến hết 10/11, tức chỉ có giá trị 30.

Hai kết quả khác nhau vì một khung đếm hàng, một khung xét khoảng ngày.

### 6.4. RANGE và các hàng có cùng giá trị ORDER BY

Với `RANGE`, các hàng có cùng giá trị sort key là **peers**. Khung kết thúc ở `CURRENT ROW` theo RANGE có thể bao gồm tất cả peers có cùng giá trị sắp xếp. Vì vậy, các hàng cùng ngày có thể nhận cùng kết quả running total hoặc moving average theo ngày.

Ví dụ:

```sql
SELECT transaction_id,
       transaction_date,
       amount,
       SUM(amount) OVER (
           ORDER BY transaction_date
           RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS daily_running_total
FROM transactions;
```

Nếu nhiều giao dịch cùng `transaction_date`, tổng của ngày đó có thể xuất hiện giống nhau trên tất cả hàng cùng ngày, vì cửa sổ RANGE bao gồm peers. Nếu muốn tổng tăng sau từng giao dịch, hãy dùng `ROWS` và thêm khóa thứ tự duy nhất:

```sql
SUM(amount) OVER (
    ORDER BY transaction_date, transaction_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
```

### 6.5. RANGE với ngày giờ và ROWS với dữ liệu không đều

Chọn theo câu hỏi:

| Câu hỏi | Khung phù hợp |
|---|---|
| Trung bình 7 lần đo gần nhất | `ROWS BETWEEN 6 PRECEDING AND CURRENT ROW` |
| Trung bình 7 ngày lịch gần nhất | `RANGE BETWEEN INTERVAL '6' DAY PRECEDING AND CURRENT ROW` |
| Tổng từ đầu chuỗi đến giao dịch hiện tại | `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` + thứ tự duy nhất |
| Tổng theo ngày, mọi giao dịch cùng ngày có cùng tổng | `RANGE` theo ngày |
| Trung bình 3 tháng dữ liệu quan sát gần nhất | `ROWS BETWEEN 2 PRECEDING AND CURRENT ROW` sau khi có một hàng mỗi tháng |
| Trung bình trong 90 ngày trước thời điểm hiện tại | `RANGE` theo khoảng thời gian phù hợp |

Không chọn ROWS hay RANGE chỉ vì một câu SQL mẫu dùng nó. Hãy xác định cửa sổ được định nghĩa bởi **số quan sát** hay **khoảng thời gian**.

## 7. Mặc định window frame khi có ORDER BY

Trong Oracle, nếu một hàm analytic có `ORDER BY` nhưng không chỉ rõ windowing clause, mặc định thường là:

```sql
RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
```

Vì vậy:

```sql
SUM(amount) OVER (
    PARTITION BY account_id
    ORDER BY transaction_date
)
```

không nhất thiết tương đương với:

```sql
SUM(amount) OVER (
    PARTITION BY account_id
    ORDER BY transaction_date, transaction_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
```

Trường hợp có ngày trùng, mặc định RANGE bao gồm peers có cùng sort key; ROWS theo từng hàng có thể cho kết quả khác. Để tránh người đọc phải nhớ mặc định, **hãy viết rõ window frame** khi tính chạy dồn hoặc trượt.

## 8. Trung bình trượt theo ngày lịch và dữ liệu thiếu ngày

Một bảng giao dịch thường không có hàng cho ngày không phát sinh giao dịch. Nếu dùng:

```sql
AVG(daily_revenue) OVER (
    ORDER BY activity_day
    ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
)
```

thì đó là trung bình của tối đa bảy **ngày có hàng**, không phải bảy ngày lịch.

Muốn trung bình bảy ngày lịch, phải xác định cách xử lý ngày không có hàng:

1. Ngày không có giao dịch có được coi là doanh thu 0 không?
2. Hay ngày không có hàng là dữ liệu chưa được nạp, cần để NULL?
3. Ngày cuối tuần/ngày lễ có nằm trong mẫu số không?
4. Có cần một hàng cho mỗi tài khoản/ngày trong calendar không?

### 8.1. Sinh lịch ngày và điền 0 khi không có giao dịch

Giả sử nghiệp vụ quy định ngày không có giao dịch là doanh thu 0:

```sql
WITH calendar_days AS (
    SELECT DATE '2026-11-01' + LEVEL - 1 AS calendar_day
    FROM dual
    CONNECT BY LEVEL <= 14
),
daily_revenue AS (
    SELECT TRUNC(sale_date) AS sale_day,
           SUM(amount) AS revenue
    FROM sales
    WHERE sale_date >= DATE '2026-11-01'
      AND sale_date <  DATE '2026-11-15'
    GROUP BY TRUNC(sale_date)
),
complete_series AS (
    SELECT c.calendar_day,
           NVL(d.revenue, 0) AS revenue
    FROM calendar_days c
    LEFT JOIN daily_revenue d
      ON d.sale_day = c.calendar_day
)
SELECT calendar_day,
       revenue,
       AVG(revenue) OVER (
           ORDER BY calendar_day
           ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
       ) AS moving_avg_7_days
FROM complete_series
ORDER BY calendar_day;
```

Do `complete_series` có đúng một hàng mỗi ngày, bảy hàng tương ứng bảy ngày lịch. `NVL(d.revenue,0)` biến ngày không có giao dịch thành 0 theo quy tắc nghiệp vụ đã giả định.

### 8.2. Nếu không có hàng có nghĩa là dữ liệu chưa được nạp

Nếu ngày không có bản ghi là thiếu dữ liệu, không được tự thay bằng 0. Có thể giữ NULL:

```sql
complete_series AS (
    SELECT c.calendar_day,
           d.revenue
    FROM calendar_days c
    LEFT JOIN daily_revenue d
      ON d.sale_day = c.calendar_day
)
```

Khi đó `AVG(revenue)` bỏ qua các ngày NULL, nên mẫu số là số ngày có doanh thu non-NULL trong cửa sổ. Nếu cần chỉ công bố trung bình khi đủ bảy ngày có dữ liệu, phải kiểm tra thêm `COUNT(revenue)` trong cùng cửa sổ.

### 8.3. Bảng calendar dùng chung

Trong hệ thống báo cáo dài hạn, nên cân nhắc calendar dimension có:

- `calendar_date`.
- `is_business_day`.
- `is_holiday`.
- `week_start`, `month_start`, `quarter_start`.
- `fiscal_period_id`.
- `business_day_sequence`.

Calendar giúp tạo chuỗi ngày/tháng hoàn chỉnh, thống nhất cách xử lý ngày nghỉ và hỗ trợ nhiều báo cáo cùng dùng một định nghĩa kỳ.

## 9. Trung bình trượt theo tháng

Nếu mỗi tháng đã có đúng một hàng, trung bình ba tháng gần nhất có thể viết:

```sql
SELECT month_start,
       revenue,
       AVG(revenue) OVER (
           ORDER BY month_start
           ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
       ) AS moving_avg_3_months
FROM monthly_revenue
ORDER BY month_start;
```

Nhưng nếu tháng 02 không có hàng, cửa sổ ba hàng ở tháng 03 có thể chứa tháng 01, tháng 03 và một tháng quan sát khác, thay vì đúng ba tháng lịch gần nhất. Cần calendar tháng nếu nghiệp vụ yêu cầu ba kỳ lịch liên tiếp.

### 9.1. Tạo chuỗi tháng hoàn chỉnh

```sql
WITH calendar_months AS (
    SELECT ADD_MONTHS(DATE '2026-01-01', LEVEL - 1) AS month_start
    FROM dual
    CONNECT BY LEVEL <= 12
),
monthly_revenue AS (
    SELECT TRUNC(sale_date, 'MM') AS month_start,
           SUM(amount) AS revenue
    FROM sales
    WHERE sale_date >= DATE '2026-01-01'
      AND sale_date <  DATE '2027-01-01'
    GROUP BY TRUNC(sale_date, 'MM')
),
complete_months AS (
    SELECT c.month_start,
           NVL(m.revenue, 0) AS revenue
    FROM calendar_months c
    LEFT JOIN monthly_revenue m
      ON m.month_start = c.month_start
)
SELECT month_start,
       revenue,
       AVG(revenue) OVER (
           ORDER BY month_start
           ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
       ) AS moving_avg_3_calendar_months
FROM complete_months
ORDER BY month_start;
```

Ví dụ này coi tháng không có giao dịch là doanh thu 0. Nếu thiếu hàng là thiếu dữ liệu nguồn, bỏ `NVL` và quyết định chính sách công bố trung bình theo số kỳ có dữ liệu.

### 9.2. So sánh với RANGE theo INTERVAL tháng

Với một hàng mỗi tháng và sort key là ngày đầu tháng, có thể cân nhắc một cửa sổ RANGE theo khoảng thời gian:

```sql
AVG(revenue) OVER (
    ORDER BY month_start
    RANGE BETWEEN INTERVAL '2' MONTH PRECEDING AND CURRENT ROW
)
```

Khung này xét các giá trị sort key trong khoảng hai tháng trước đến tháng hiện tại. Tuy nhiên, nó không tự sinh tháng thiếu; nếu thiếu tháng, trung bình chỉ tính những hàng hiện diện và non-NULL. Nếu yêu cầu đúng ba kỳ tháng, calendar scaffold với ROWS thường dễ kiểm soát hơn.

## 10. Xử lý NULL trong SUM và AVG

Các hàm `SUM` và `AVG` bỏ qua giá trị NULL trong biểu thức tổng hợp.

Giả sử cửa sổ có các giá trị:

```text
10, 20, NULL, 30
```

Kết quả:

- `SUM(value)` = 60.
- `AVG(value)` = 20.
- `COUNT(value)` = 3.
- `COUNT(*)` = 4.

### 10.1. Tổng chạy dồn khi amount NULL

```sql
SELECT transaction_id,
       amount,
       SUM(amount) OVER (
           ORDER BY transaction_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS running_sum
FROM transactions;
```

Nếu một hàng có `amount IS NULL`, hàng đó không đóng góp vào tổng. Tổng tích lũy vẫn dựa trên các giá trị non-NULL đã gặp.

Nếu toàn bộ giá trị trong cửa sổ đều NULL, `SUM` trả NULL. Nếu nghiệp vụ muốn hiển thị 0 khi chưa có số liệu:

```sql
NVL(
    SUM(amount) OVER (
        ORDER BY transaction_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ),
    0
) AS running_sum_display
```

Đây là thay đổi ở kết quả hiển thị. Hãy phân biệt “chưa có giá trị” với “tổng thực sự bằng 0”.

### 10.2. AVG bỏ qua NULL, không xem NULL là 0

```sql
AVG(amount) OVER (
    ORDER BY transaction_id
    ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
)
```

Nếu cửa sổ có `10, NULL, 30`, kết quả là 20, không phải 13,33. Mẫu số chỉ gồm hai giá trị non-NULL.

Nếu nghiệp vụ muốn NULL được xem như 0:

```sql
AVG(NVL(amount, 0)) OVER (
    ORDER BY transaction_id
    ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
)
```

Kết quả trong ví dụ là 13,33. Đây là một chỉ số khác; chỉ dùng khi NULL thực sự được định nghĩa là zero.

### 10.3. Đếm số quan sát trong cửa sổ

```sql
SELECT observation_date,
       metric_value,
       COUNT(*) OVER (
           ORDER BY observation_date
           ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
       ) AS row_count_7,
       COUNT(metric_value) OVER (
           ORDER BY observation_date
           ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
       ) AS non_null_count_7,
       AVG(metric_value) OVER (
           ORDER BY observation_date
           ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
       ) AS moving_average
FROM metrics;
```

Hai số đếm giúp giải thích trung bình được tính từ bao nhiêu hàng và bao nhiêu giá trị thực tế.

### 10.4. Chỉ trả trung bình khi có đủ ba giá trị hợp lệ

Oracle không có tham số `min_periods` trực tiếp như một số thư viện phân tích dữ liệu. Có thể kết hợp `COUNT` và `AVG` cùng khung:

```sql
SELECT observation_date,
       metric_value,
       CASE
           WHEN COUNT(metric_value) OVER (
                    ORDER BY observation_date
                    ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
                ) = 3
           THEN AVG(metric_value) OVER (
                    ORDER BY observation_date
                    ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
                )
       END AS full_3_value_average
FROM metrics
ORDER BY observation_date;
```

Nếu chưa có đủ ba giá trị non-NULL, cột `FULL_3_VALUE_AVERAGE` là NULL. Nếu yêu cầu là đủ ba **hàng** dù có measure NULL, thay `COUNT(metric_value)` bằng `COUNT(*)`; hai cách biểu đạt hai chính sách khác nhau.

## 11. Xác định thứ tự: tie-breaker và tính xác định

Hàm chạy dồn phụ thuộc vào thứ tự. Nếu nhiều hàng có cùng ngày, chỉ:

```sql
ORDER BY transaction_date
```

có thể chưa đủ để xác định hàng nào đứng trước hàng nào khi dùng `ROWS`.

Nên thêm khóa phân định:

```sql
ORDER BY transaction_date, transaction_id
```

Ví dụ:

| transaction_id | transaction_date | amount |
|---:|---|---:|
| 101 | 01/11 | 100 |
| 102 | 01/11 | 50 |
| 103 | 02/11 | 20 |

Với `ROWS`, tổng chạy dồn theo `transaction_id` là 100, 150, 170. Nếu không có tie-breaker, hai giao dịch ngày 01/11 có thể được xử lý theo thứ tự không xác định, làm kết quả trung gian trên từng hàng thay đổi.

Với `RANGE` theo ngày, hai giao dịch cùng ngày là peers; tổng tại ngày đó có thể bao gồm cả hai. Điều này phù hợp khi báo cáo theo ngày, nhưng khác với sổ giao dịch cần số dư sau từng giao dịch.

`ORDER BY` trong `OVER` xác định thứ tự tính toán; nó **không tự sắp xếp tập kết quả cuối cùng**. Muốn hiển thị đúng thứ tự, thêm `ORDER BY` ở query block ngoài.

## 12. Các kiểu khung cửa sổ thường dùng

| Window frame | Ý nghĩa |
|---|---|
| `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` | Từ đầu partition đến hàng hiện tại |
| `ROWS BETWEEN 2 PRECEDING AND CURRENT ROW` | Tối đa 3 hàng: 2 hàng trước và hiện tại |
| `ROWS BETWEEN 6 PRECEDING AND CURRENT ROW` | Tối đa 7 hàng gần nhất |
| `ROWS BETWEEN 2 PRECEDING AND 2 FOLLOWING` | Cửa sổ căn giữa tối đa 5 hàng |
| `ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING` | Từ hàng hiện tại đến cuối partition |
| `ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING` | Toàn bộ partition theo khung ROWS |
| `RANGE BETWEEN INTERVAL '6' DAY PRECEDING AND CURRENT ROW` | Khoảng sáu ngày trước đến giá trị hiện tại của sort key ngày giờ |
| `RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` | Từ đầu miền sort key đến giá trị hiện tại, gồm peers |

Một số điểm biên:

- `PRECEDING` nhìn về trước theo thứ tự analytic.
- `FOLLOWING` nhìn về sau theo thứ tự analytic.
- `CURRENT ROW` phụ thuộc loại frame: với ROWS là hàng hiện tại; với RANGE bao gồm các peer theo sort key.
- Nếu frame vượt quá đầu hoặc cuối partition, Oracle chỉ dùng các hàng thực sự có trong partition; không tự tạo hàng ngoài biên.

## 13. Tính tỷ lệ phần trăm lũy kế

Từ tổng chạy dồn, có thể tính tỷ lệ đóng góp lũy kế so với tổng toàn nhóm:

```sql
SELECT product_id,
       sales_date,
       amount,
       SUM(amount) OVER (
           PARTITION BY product_id
           ORDER BY sales_date, sale_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS running_amount,
       SUM(amount) OVER (
           PARTITION BY product_id
       ) AS total_amount,
       SUM(amount) OVER (
           PARTITION BY product_id
           ORDER BY sales_date, sale_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       )
       / NULLIF(
           SUM(amount) OVER (PARTITION BY product_id),
           0
       ) AS cumulative_share
FROM product_sales
ORDER BY product_id, sales_date, sale_id;
```

`NULLIF(total_amount,0)` tránh phép chia cho 0 bằng cách trả NULL nếu tổng nhóm bằng 0. Nếu tổng có thể âm hoặc các giá trị bù trừ, tỷ lệ lũy kế cần được định nghĩa nghiệp vụ cẩn thận; không phải lúc nào nó cũng là tỷ lệ đóng góp trực quan.

Muốn hiển thị phần trăm:

```sql
100 * cumulative_share AS cumulative_percent
```

hoặc định dạng ở lớp trình bày. Nếu cần làm tròn, hãy quyết định làm tròn từng hàng hay chỉ làm tròn kết quả cuối.

## 14. Chạy dồn có điều kiện

Có thể đặt `CASE` bên trong `SUM` để chỉ cộng một số loại giao dịch:

```sql
SELECT account_id,
       transaction_id,
       transaction_date,
       transaction_type,
       amount,
       SUM(
           CASE
               WHEN transaction_type = 'CREDIT' THEN amount
               ELSE 0
           END
       ) OVER (
           PARTITION BY account_id
           ORDER BY transaction_date, transaction_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS running_credit
FROM account_transactions
ORDER BY account_id, transaction_date, transaction_id;
```

Tương tự, tính running debit:

```sql
SUM(
    CASE
        WHEN transaction_type = 'DEBIT' THEN amount
        ELSE 0
    END
) OVER (
    PARTITION BY account_id
    ORDER BY transaction_date, transaction_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
) AS running_debit
```

Nếu `amount` có thể NULL, nhánh CREDIT trả NULL và `SUM` bỏ qua nó; nhánh ELSE 0 đóng góp 0. Nếu cần phân biệt giao dịch thiếu số tiền với giao dịch không thuộc loại đang tính, phải theo dõi thêm cờ dữ liệu hoặc số lượng giá trị NULL.

## 15. Kết hợp tổng chạy dồn với các hàm analytic khác

Một báo cáo có thể cần tổng chạy dồn, trung bình chạy dồn và thứ hạng cùng lúc:

```sql
SELECT account_id,
       transaction_id,
       transaction_date,
       amount,
       SUM(amount) OVER (
           PARTITION BY account_id
           ORDER BY transaction_date, transaction_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS running_sum,
       AVG(amount) OVER (
           PARTITION BY account_id
           ORDER BY transaction_date, transaction_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS running_avg,
       ROW_NUMBER() OVER (
           PARTITION BY account_id
           ORDER BY transaction_date, transaction_id
       ) AS transaction_sequence
FROM transactions
ORDER BY account_id, transaction_date, transaction_id;
```

Các analytic function trong SELECT list dùng cùng partition/order/frame khi có cùng định nghĩa. Oracle có thể tối ưu việc sắp xếp dùng chung, nhưng kế hoạch thực tế tùy truy vấn và phiên bản.

Nếu cần dùng kết quả analytic trong điều kiện lọc, hãy đặt truy vấn vào CTE/inline view:

```sql
WITH calculated AS (
    SELECT account_id,
           transaction_id,
           transaction_date,
           amount,
           SUM(amount) OVER (
               PARTITION BY account_id
               ORDER BY transaction_date, transaction_id
               ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
           ) AS running_sum
    FROM transactions
)
SELECT *
FROM calculated
WHERE running_sum > 10000;
```

Hàm analytic được tính sau các mệnh đề như WHERE/GROUP BY/HAVING trong cùng query block; vì vậy không thể dùng alias analytic trực tiếp trong WHERE của cùng SELECT block. CTE tạo query block tiếp theo để lọc kết quả đã tính.

## 16. Hiệu năng và thiết kế truy vấn

### 16.1. Giới hạn dữ liệu trước khi tính analytic

Nếu chỉ cần báo cáo một năm, hãy lọc phạm vi trong query block trước khi hàm phân tích chạy:

```sql
SELECT account_id,
       transaction_date,
       amount,
       SUM(amount) OVER (
           PARTITION BY account_id
           ORDER BY transaction_date, transaction_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS running_sum
FROM transactions
WHERE transaction_date >= DATE '2026-01-01'
  AND transaction_date <  DATE '2027-01-01';
```

Điều này tính tổng chạy dồn **trong phạm vi năm 2026**. Nếu cần số dư lũy kế từ khi tài khoản mở nhưng chỉ hiển thị giao dịch năm 2026, không thể lọc bỏ lịch sử trước 2026 trước khi tính. Hãy tính trên toàn bộ lịch sử cần thiết trong CTE rồi lọc kết quả ở query block ngoài.

### 16.2. Index và thứ tự analytic

Truy vấn thường phân vùng theo `account_id` và sắp xếp theo `transaction_date`, `transaction_id`. Một index có thể được cân nhắc:

```sql
CREATE INDEX ix_tx_account_date_id
ON transactions (account_id, transaction_date, transaction_id);
```

Index có thể hỗ trợ truy cập và thứ tự, nhưng analytic function vẫn có thể cần sort tùy kế hoạch, phạm vi dữ liệu và thống kê. Không tạo index chỉ dựa trên cú pháp ví dụ.

### 16.3. Tránh tính trên grain sai

Nếu bảng là transaction-level nhưng chỉ số là moving average theo tháng, hãy tổng hợp về một hàng mỗi tháng trước. Nếu bảng là daily snapshot nhưng cần trung bình theo giao dịch, hãy giữ grain giao dịch. Window frame chỉ có ý nghĩa khi hạt dữ liệu đầu vào đúng.

### 16.4. Không dùng TRUNC trên cột trong điều kiện lọc nếu có thể dùng range

Tránh:

```sql
WHERE TRUNC(transaction_date) = DATE '2026-11-14'
```

Ưu tiên:

```sql
WHERE transaction_date >= DATE '2026-11-14'
  AND transaction_date <  DATE '2026-11-15'
```

Điều kiện khoảng nửa mở có thể tận dụng index thường trên cột thời gian tốt hơn. Kế hoạch cuối cùng vẫn phụ thuộc dữ liệu và thống kê.

### 16.5. Kiểm tra execution plan

Trong môi trường có quyền phù hợp:

```sql
EXPLAIN PLAN FOR
SELECT account_id,
       transaction_date,
       SUM(amount) OVER (
           PARTITION BY account_id
           ORDER BY transaction_date, transaction_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS running_sum
FROM transactions
WHERE transaction_date >= DATE '2026-01-01'
  AND transaction_date <  DATE '2027-01-01';

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
```

`EXPLAIN PLAN` cho biết kế hoạch dự kiến. Khi được phép, hãy đối chiếu với execution plan thực tế và thống kê runtime trên dữ liệu gần production.

## 17. Bài thực hành tổng hợp

Các lệnh dưới đây dùng bảng riêng trong schema thực hành. Chỉ chạy khi có quyền tạo bảng và không sử dụng tên bảng trùng với dữ liệu hiện có.

### Bước 1. Tạo bảng doanh thu ngày

```sql
CREATE TABLE demo_daily_sales (
    sale_day DATE NOT NULL,
    revenue NUMBER(12, 2)
);
```

### Bước 2. Chèn dữ liệu

```sql
INSERT INTO demo_daily_sales VALUES (DATE '2026-11-01', 100);
INSERT INTO demo_daily_sales VALUES (DATE '2026-11-02', 150);
INSERT INTO demo_daily_sales VALUES (DATE '2026-11-03', 50);
INSERT INTO demo_daily_sales VALUES (DATE '2026-11-04', 200);
INSERT INTO demo_daily_sales VALUES (DATE '2026-11-05', NULL);

COMMIT;
```

### Bước 3. Tính tổng chạy dồn và trung bình chạy dồn

```sql
SELECT sale_day,
       revenue,
       SUM(revenue) OVER (
           ORDER BY sale_day
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS running_sum,
       AVG(revenue) OVER (
           ORDER BY sale_day
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS running_avg
FROM demo_daily_sales
ORDER BY sale_day;
```

Quan sát hàng có revenue NULL: tổng và trung bình không coi NULL là 0.

### Bước 4. Tính moving average ba hàng

```sql
SELECT sale_day,
       revenue,
       AVG(revenue) OVER (
           ORDER BY sale_day
           ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
       ) AS moving_avg_3_rows,
       COUNT(revenue) OVER (
           ORDER BY sale_day
           ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
       ) AS valid_values_in_window
FROM demo_daily_sales
ORDER BY sale_day;
```

Đối chiếu số hàng trong cửa sổ với số giá trị hợp lệ.

### Bước 5. Chỉ công bố trung bình khi đủ ba giá trị

```sql
SELECT sale_day,
       revenue,
       CASE
           WHEN COUNT(revenue) OVER (
                    ORDER BY sale_day
                    ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
                ) = 3
           THEN AVG(revenue) OVER (
                    ORDER BY sale_day
                    ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
                )
       END AS full_window_avg
FROM demo_daily_sales
ORDER BY sale_day;
```

### Bước 6. So sánh ROWS và RANGE

```sql
SELECT sale_day,
       revenue,
       AVG(revenue) OVER (
           ORDER BY sale_day
           ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
       ) AS avg_3_rows,
       AVG(revenue) OVER (
           ORDER BY sale_day
           RANGE BETWEEN INTERVAL '2' DAY PRECEDING AND CURRENT ROW
       ) AS avg_3_calendar_days
FROM demo_daily_sales
ORDER BY sale_day;
```

Trong dữ liệu mẫu mỗi ngày có một hàng nên kết quả hai cửa sổ có thể giống nhau. Hãy thêm một ngày bị thiếu hoặc nhiều hàng cùng ngày để quan sát khác biệt.

### Bước 7. Thử dữ liệu có nhiều hàng cùng ngày

```sql
INSERT INTO demo_daily_sales VALUES (DATE '2026-11-03', 25);
COMMIT;
```

Chạy lại truy vấn ROWS/RANGE. `ROWS` tính theo từng hàng và thứ tự phải được xác định nếu cần kết quả ổn định; `RANGE` theo ngày coi các hàng cùng ngày là peers.

### Bước 8. Dọn bảng thực hành

Chỉ khi chắc chắn đây là bảng vừa tạo và không cần giữ dữ liệu:

```sql
DROP TABLE demo_daily_sales PURGE;
```

`DROP TABLE ... PURGE` xóa bảng và dữ liệu, bỏ qua recycle bin theo hành vi của lệnh; đây là DDL có commit ngầm. Không chạy trên bảng nghiệp vụ hoặc đối tượng dùng chung.

## 18. Những nhầm lẫn thường gặp

| Nhầm lẫn | Thực tế |
|---|---|
| `SUM(...) OVER (ORDER BY ...)` luôn tăng từng hàng | Mặc định RANGE có thể gộp peers; nếu cần theo từng hàng, dùng ROWS và tie-breaker |
| `ROWS 6 PRECEDING` là bảy ngày | Nó là tối đa bảy hàng, không phải bảy ngày lịch |
| `RANGE 6 DAY` tự tạo các ngày thiếu | RANGE chỉ chọn các hàng hiện có trong khoảng, không sinh hàng |
| `AVG` coi NULL là 0 | AVG bỏ qua NULL |
| Không có hàng trong tháng đồng nghĩa doanh thu bằng 0 | Chỉ đúng nếu nghiệp vụ quy định kỳ không có giao dịch là zero |
| CTE đã GROUP BY tháng thì tự có đủ 12 tháng | Không; tháng không có dữ liệu không xuất hiện nếu không nối calendar |
| ORDER BY trong OVER sắp xếp kết quả cuối | Nó chỉ xác định thứ tự tính analytic; query ngoài vẫn cần ORDER BY |
| Running total trong báo cáo năm luôn phải bắt đầu từ 0 | Nếu cần số dư lịch sử, phải đưa số dư đầu kỳ/lịch sử vào phép tính |
| ROWS frame ở đầu chuỗi tự chờ đủ số hàng | Oracle tính trên các hàng hiện có; cần COUNT nếu muốn yêu cầu đủ quan sát |
| Có thể dùng centered moving average cho dự báo thời gian thực | Cửa sổ FOLLOWING dùng dữ liệu tương lai so với hàng hiện tại |
| Bỏ tháng thiếu không ảnh hưởng trung bình ba tháng | Nó làm cửa sổ ba hàng thành ba tháng quan sát, có thể không còn là ba tháng lịch |
| Mọi ID phải liên tục | Sequence/identity không bảo đảm không có gap |

## 19. Câu hỏi tự kiểm tra

**Câu 1.** Khác biệt chính giữa `GROUP BY` và `SUM(...) OVER (...)` là gì?

**Trả lời:** `GROUP BY` gom hàng thành một hàng mỗi nhóm; hàm analytic giữ từng hàng và bổ sung kết quả tính trên cửa sổ.

**Câu 2.** Cú pháp nào tính tổng chạy dồn từ đầu partition đến hàng hiện tại?

**Trả lời:** `SUM(x) OVER (PARTITION BY ... ORDER BY ... ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)`.

**Câu 3.** Vì sao running total theo giao dịch cần tie-breaker?

**Trả lời:** Nhiều giao dịch có thể cùng timestamp; thêm khóa duy nhất giúp xác định thứ tự từng hàng và kết quả ROWS ổn định.

**Câu 4.** `AVG` xử lý NULL thế nào?

**Trả lời:** Bỏ qua giá trị NULL; mẫu số là số biểu thức non-NULL trong cửa sổ.

**Câu 5.** `ROWS BETWEEN 6 PRECEDING AND CURRENT ROW` lấy bao nhiêu hàng tối đa?

**Trả lời:** Bảy hàng, gồm sáu hàng trước và hàng hiện tại.

**Câu 6.** `RANGE BETWEEN INTERVAL '6' DAY PRECEDING AND CURRENT ROW` khác gì?

**Trả lời:** Nó chọn các hàng có sort key ngày giờ trong khoảng sáu ngày trước đến giá trị hiện tại, không đếm số hàng.

**Câu 7.** Muốn trung bình bảy ngày lịch nhưng nguồn thiếu ngày, cần làm gì?

**Trả lời:** Tạo chuỗi ngày đầy đủ bằng calendar hoặc calendar dimension, nối dữ liệu theo ngày và quyết định rõ ngày thiếu được xem là 0 hay NULL.

**Câu 8.** Vì sao không nên mặc định ngày không có hàng là doanh thu 0?

**Trả lời:** Không có hàng có thể do không phát sinh giao dịch hoặc do dữ liệu chưa được nạp; hai tình huống có ý nghĩa khác nhau.

**Câu 9.** Mặc định window frame khi analytic ORDER BY có thể là gì?

**Trả lời:** `RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`. Vì thế nên ghi rõ frame khi cần semantics ROWS.

**Câu 10.** Vì sao `RANGE` có thể cho cùng running total ở các giao dịch cùng ngày?

**Trả lời:** Các hàng cùng giá trị ORDER BY là peers và có thể cùng nằm trong frame đến CURRENT ROW.

**Câu 11.** Làm sao chỉ trả moving average khi có đủ ba giá trị non-NULL?

**Trả lời:** Dùng `CASE WHEN COUNT(value) OVER (cùng frame) = 3 THEN AVG(value) OVER (cùng frame) END`.

**Câu 12.** Running total chỉ hiển thị giao dịch năm nay nhưng cần số dư từ lịch sử thì lọc năm ở đâu?

**Trả lời:** Tính analytic trên dữ liệu lịch sử cần thiết trong CTE trước, sau đó lọc hàng hiển thị ở query block ngoài.

## 20. Quy tắc ghi nhớ

| Mục tiêu | Biểu thức |
|---|---|
| Tổng toàn bộ partition, lặp trên từng hàng | `SUM(x) OVER (PARTITION BY key)` |
| Tổng chạy dồn | `SUM(x) OVER (PARTITION BY key ORDER BY sort_key ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)` |
| Trung bình chạy dồn | `AVG(x) OVER (PARTITION BY key ORDER BY sort_key ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)` |
| Tổng/trung bình ba hàng gần nhất | `ROWS BETWEEN 2 PRECEDING AND CURRENT ROW` |
| Tổng/trung bình bảy hàng gần nhất | `ROWS BETWEEN 6 PRECEDING AND CURRENT ROW` |
| Cửa sổ căn giữa năm hàng | `ROWS BETWEEN 2 PRECEDING AND 2 FOLLOWING` |
| Trung bình bảy ngày lịch | `RANGE BETWEEN INTERVAL '6' DAY PRECEDING AND CURRENT ROW` |
| Trung bình ba tháng lịch | Calendar tháng đầy đủ + `ROWS BETWEEN 2 PRECEDING AND CURRENT ROW` |
| Đếm số giá trị hợp lệ trong cửa sổ | `COUNT(x) OVER (cùng frame)` |
| Chỉ công bố khi đủ N giá trị | `CASE WHEN COUNT(x) OVER (cùng frame) = N THEN AVG(x) OVER (cùng frame) END` |

## 21. Kết luận

`SUM` và `AVG` kết hợp với `OVER` cho phép tính tổng và trung bình trên một cửa sổ mà vẫn giữ từng hàng trong kết quả. Khi dùng `UNBOUNDED PRECEDING` đến `CURRENT ROW`, ta có tổng hoặc trung bình chạy dồn. Khi dùng `ROWS BETWEEN N PRECEDING AND CURRENT ROW`, ta có cửa sổ trượt theo số hàng quan sát. Với `RANGE`, cửa sổ được xác định theo giá trị sort key, phù hợp khi muốn giới hạn theo một khoảng ngày giờ.

Hãy phân biệt rõ **số hàng** với **số ngày/tháng lịch**. `ROWS` không tự biết kỳ bị thiếu; `RANGE` cũng không tự sinh hàng cho kỳ không có dữ liệu. Muốn tính trung bình theo kỳ lịch, hãy tạo chuỗi kỳ đầy đủ bằng calendar hoặc calendar dimension và quyết định ngày/tháng không có hàng được xem là 0 hay NULL. `AVG` bỏ qua NULL, nên nếu cần đủ số quan sát hợp lệ phải kiểm tra thêm `COUNT`.

Cuối cùng, xác định thứ tự bằng tie-breaker khi cần kết quả theo từng hàng ổn định, ghi rõ window frame thay vì dựa vào mặc định RANGE, và phân biệt dữ liệu lịch sử cần cho số dư với phạm vi hàng chỉ muốn hiển thị. Những quyết định đó giúp running total, running average và moving average phản ánh đúng ý nghĩa nghiệp vụ, kể cả khi dữ liệu có ngày trùng, kỳ thiếu hoặc measure NULL.
