# SUM/AVG chạy dồn và trung bình trượt

Hàm cửa sổ cho phép tính tổng, trung bình hoặc các chỉ số khác trên một nhóm hàng liên quan mà vẫn giữ từng hàng trong kết quả. Với `SUM() OVER (...)` và `AVG() OVER (...)`, bạn có thể tính tổng lũy kế theo thời gian, trung bình lũy kế hoặc trung bình trượt trên các giao dịch gần nhất. Khác với `GROUP BY`, phép tính cửa sổ không gom nhiều hàng thành một hàng đại diện.

Kết quả phụ thuộc vào ba phần quan trọng: `PARTITION BY` chia dữ liệu thành từng nhóm độc lập, `ORDER BY` xác định thứ tự xử lý và frame xác định những hàng được đưa vào phép tính cho hàng hiện tại. Hiểu đúng `ROWS` và `RANGE` giúp tránh lỗi khi nhiều bản ghi có cùng thời điểm hoặc khi cần trung bình theo số ngày.

Trong module `DATABASE_MYSQL`, các kỹ thuật này thường dùng cho số dư tài khoản, doanh thu lũy kế, tiến độ mục tiêu, số liệu theo kỳ và dashboard vận hành. Bài học sử dụng MySQL 8.0 trở lên.

## Mục tiêu

Sau bài này, bạn có thể:

- Phân biệt aggregate thông thường với aggregate window function.
- Dùng `PARTITION BY` và `ORDER BY` để tính riêng theo từng tài khoản hoặc nhóm.
- Viết tổng chạy dồn bằng `SUM() OVER (...)`.
- Viết trung bình chạy dồn và trung bình trượt bằng `AVG() OVER (...)`.
- Chọn frame `ROWS` hoặc `RANGE` đúng với yêu cầu nghiệp vụ.
- Xử lý các hàng có cùng giá trị sắp xếp, `NULL` và khoảng thời gian không liên tục.
- Hiểu ảnh hưởng của bộ lọc trước/sau phép tính cửa sổ.
- Kiểm tra kế hoạch thực thi và chọn index phù hợp cho truy vấn cửa sổ.

## 1. Aggregate thông thường và aggregate window function

`SUM(amount)` trong truy vấn tổng hợp thông thường trả một giá trị cho toàn bộ tập hoặc cho từng nhóm `GROUP BY`:

```sql
SELECT account_id, SUM(amount) AS total_amount
FROM account_txn
GROUP BY account_id;
```

Kết quả chỉ có một hàng cho mỗi tài khoản. Nếu muốn giữ từng giao dịch và hiển thị tổng lũy kế sau mỗi giao dịch, dùng hàm cửa sổ:

```sql
SELECT
    account_id,
    txn_id,
    amount,
    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY txn_at, txn_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_total
FROM account_txn;
```

Mỗi giao dịch vẫn là một hàng trong kết quả; `running_total` là giá trị được tính trên một frame thay đổi theo vị trí hàng hiện tại.

### 1.1. Cấu trúc cơ bản

```sql
aggregate_function(expression) OVER (
    PARTITION BY partition_expression
    ORDER BY sort_expression
    frame_clause
)
```

- `PARTITION BY`: chia hàng thành các phân vùng độc lập. Khi giá trị partition thay đổi, phép tính bắt đầu lại.
- `ORDER BY`: xác định thứ tự hàng trong mỗi partition.
- `frame_clause`: xác định tập con của partition dùng để tính cho hàng hiện tại.

`PARTITION BY` và `ORDER BY` có thể dùng một hoặc nhiều biểu thức. Nếu bỏ `PARTITION BY`, toàn bộ kết quả thuộc cùng một partition. Nếu bỏ `ORDER BY`, aggregate window không có frame tường minh thường tính trên toàn bộ partition.

### 1.2. ORDER BY bên trong OVER khác ORDER BY cuối truy vấn

`ORDER BY` trong `OVER(...)` điều khiển thứ tự tính toán, không bảo đảm thứ tự hàng trả về cho client. Muốn kết quả hiển thị theo thời gian, hãy viết thêm `ORDER BY` ở cuối câu lệnh:

```sql
SELECT
    account_id,
    txn_at,
    amount,
    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY txn_at, txn_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_total
FROM account_txn
ORDER BY account_id, txn_at, txn_id;
```

## 2. Dữ liệu mẫu để thực hành

Bảng giao dịch lưu tài khoản, thời điểm và số tiền. `amount` cho phép `NULL` để biểu diễn giao dịch chưa có giá trị tiền được ghi nhận.

```sql
CREATE TABLE account_txn (
    txn_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    account_id BIGINT UNSIGNED NOT NULL,
    txn_at DATETIME(6) NOT NULL,
    amount DECIMAL(12, 2) NULL,
    txn_note VARCHAR(100) NULL,
    PRIMARY KEY (txn_id),
    KEY idx_account_txn_time (account_id, txn_at, txn_id)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4;

INSERT INTO account_txn (account_id, txn_at, amount, txn_note)
VALUES
    (10, '2026-01-01 09:00:00', 100.00, 'Opening'),
    (10, '2026-01-02 09:00:00',  50.00, 'Deposit A'),
    (10, '2026-01-02 09:00:00',  25.00, 'Deposit B'),
    (10, '2026-01-03 09:00:00',   NULL, 'Pending amount'),
    (10, '2026-01-04 09:00:00', -20.00, 'Adjustment'),
    (20, '2026-01-01 10:00:00', 200.00, 'Opening'),
    (20, '2026-01-03 10:00:00', 100.00, 'Deposit'),
    (20, '2026-01-04 10:00:00',  50.00, 'Deposit'),
    (20, '2026-01-05 10:00:00',   0.00, 'Zero-value event');
```

Tài khoản 10 có hai giao dịch cùng thời điểm ngày 2/1. Đây là tình huống quan trọng để phân biệt frame theo hàng với frame theo giá trị sắp xếp. Tài khoản 20 có ngày không phát sinh giao dịch; điều này giúp phân biệt trung bình trên các hàng hiện có với trung bình theo ngày lịch.

## 3. Tổng chạy dồn (running total)

Tổng chạy dồn tại một hàng là tổng các giá trị từ đầu partition tới hàng hiện tại theo thứ tự đã chọn.

```sql
SELECT
    account_id,
    txn_id,
    txn_at,
    amount,
    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY txn_at, txn_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_total
FROM account_txn
ORDER BY account_id, txn_at, txn_id;
```

Kết quả dự kiến:

| account_id | txn_id | amount | running_total |
|---:|---:|---:|---:|
| 10 | 1 | 100.00 | 100.00 |
| 10 | 2 | 50.00 | 150.00 |
| 10 | 3 | 25.00 | 175.00 |
| 10 | 4 | `NULL` | 175.00 |
| 10 | 5 | -20.00 | 155.00 |
| 20 | 6 | 200.00 | 200.00 |
| 20 | 7 | 100.00 | 300.00 |
| 20 | 8 | 50.00 | 350.00 |
| 20 | 9 | 0.00 | 350.00 |

### 3.1. Ý nghĩa frame UNBOUNDED PRECEDING

```sql
ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
```

Frame bắt đầu ở hàng đầu tiên của partition và kết thúc ở hàng hiện tại. Khi chuyển sang hàng tiếp theo, frame mở rộng thêm hàng đó. Khi `account_id` thay đổi, partition mới bắt đầu nên tổng chạy dồn được đặt lại.

Nếu cần tổng chạy dồn toàn hệ thống, bỏ `PARTITION BY account_id`:

```sql
SUM(amount) OVER (
    ORDER BY txn_at, txn_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
```

Khi bỏ partition, giao dịch của mọi tài khoản được cộng vào cùng một chuỗi theo thời gian. Chỉ làm vậy nếu đó là ý nghĩa báo cáo mong muốn.

### 3.2. Thứ tự phải xác định được

Nếu nhiều giao dịch có cùng `txn_at`, chỉ sắp xếp theo `txn_at` không xác định thứ tự giữa các giao dịch cùng thời điểm. Với `ROWS`, thứ tự đó ảnh hưởng giá trị tổng sau từng hàng. Thêm khóa duy nhất như `txn_id` làm tie-breaker:

```sql
ORDER BY txn_at, txn_id
```

Thứ tự này không nói giao dịch nào xảy ra trước trong thế giới thực nếu timestamp giống nhau; nó chỉ tạo thứ tự ổn định cho phép tính. Nếu nghiệp vụ có sequence number hoặc event ordering riêng, hãy dùng cột đó.

## 4. Trung bình chạy dồn (running average)

`AVG()` với cùng frame lũy kế tính trung bình của các giá trị từ đầu partition đến hàng hiện tại:

```sql
SELECT
    account_id,
    txn_id,
    txn_at,
    amount,
    AVG(amount) OVER (
        PARTITION BY account_id
        ORDER BY txn_at, txn_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_average
FROM account_txn
ORDER BY account_id, txn_at, txn_id;
```

Với tài khoản 10, các giá trị trung bình lần lượt là 100.00, 75.00, khoảng 58.3333, 58.3333 và 38.75. Hàng có `amount IS NULL` không đóng góp vào tổng hoặc mẫu số của `AVG()`, vì vậy giá trị trung bình ở hàng thứ tư giữ nguyên.

### 4.1. AVG bỏ qua NULL nhưng frame vẫn chứa hàng đó

`ROWS` xác định số hàng trong frame, không đồng nghĩa mọi hàng đều đóng góp vào mẫu số. `AVG(amount)` bỏ qua `NULL`; có thể hiển thị số lượng giá trị thực sự được dùng bằng `COUNT(amount)`:

```sql
SELECT
    account_id,
    txn_id,
    amount,
    COUNT(*) OVER (
        PARTITION BY account_id
        ORDER BY txn_at, txn_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS rows_seen,
    COUNT(amount) OVER (
        PARTITION BY account_id
        ORDER BY txn_at, txn_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS known_amounts,
    AVG(amount) OVER (
        PARTITION BY account_id
        ORDER BY txn_at, txn_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_average
FROM account_txn
ORDER BY account_id, txn_at, txn_id;
```

`rows_seen` đếm mọi hàng trong frame; `known_amounts` chỉ đếm số tiền khác `NULL`. Nếu mọi giá trị trong frame đều `NULL`, `AVG()` trả `NULL`.

## 5. Trung bình trượt theo số hàng

Trung bình trượt (moving average) tính trung bình trên một cửa sổ có kích thước giới hạn. Ví dụ trung bình của giao dịch hiện tại và hai giao dịch ngay trước nó:

```sql
SELECT
    account_id,
    txn_id,
    txn_at,
    amount,
    AVG(amount) OVER (
        PARTITION BY account_id
        ORDER BY txn_at, txn_id
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS moving_avg_3_txns
FROM account_txn
ORDER BY account_id, txn_at, txn_id;
```

Frame có tối đa ba hàng: hai hàng trước và hàng hiện tại. Ở đầu partition, frame nhỏ hơn ba hàng vì không có đủ lịch sử.

Kết quả dự kiến:

| account_id | txn_id | amount | moving_avg_3_txns |
|---:|---:|---:|---:|
| 10 | 1 | 100.00 | 100.00 |
| 10 | 2 | 50.00 | 75.00 |
| 10 | 3 | 25.00 | 58.33 |
| 10 | 4 | `NULL` | 37.50 |
| 10 | 5 | -20.00 | 2.50 |
| 20 | 6 | 200.00 | 200.00 |
| 20 | 7 | 100.00 | 150.00 |
| 20 | 8 | 50.00 | 116.67 |
| 20 | 9 | 0.00 | 50.00 |

### 5.1. Frame theo số giao dịch, không phải số ngày

`ROWS BETWEEN 2 PRECEDING AND CURRENT ROW` có nghĩa là ba hàng theo thứ tự, không có nghĩa ba ngày. Nếu tài khoản có 20 giao dịch trong cùng một ngày, cửa sổ có thể gồm ba giao dịch trong cùng ngày. Nếu tài khoản không có giao dịch trong một tuần, cửa sổ vẫn lấy ba hàng gần nhất, dù chúng cách nhau nhiều ngày.

Đặt tên chỉ số rõ ràng như `moving_avg_3_txns` để tránh người đọc hiểu nhầm đó là trung bình ba ngày.

### 5.2. Trung bình trượt với frame đối xứng

Có thể tính trung bình có một hàng trước và một hàng sau:

```sql
AVG(amount) OVER (
    PARTITION BY account_id
    ORDER BY txn_at, txn_id
    ROWS BETWEEN 1 PRECEDING AND 1 FOLLOWING
) AS centered_avg_3_rows
```

Đây là trung bình căn giữa (centered moving average). Nó dùng dữ liệu tương lai so với hàng hiện tại, nên phù hợp cho phân tích lịch sử hoặc làm mượt chuỗi đã hoàn tất. Với dashboard thời gian thực hoặc dự báo tại thời điểm hiện tại, dùng `FOLLOWING` có thể tạo rò rỉ dữ liệu tương lai; frame kết thúc ở `CURRENT ROW` thường phù hợp hơn.

## 6. ROWS và RANGE: hai cách xác định frame

`ROWS` xác định frame theo số vị trí hàng. `RANGE` xác định frame theo giá trị của biểu thức sắp xếp và bao gồm các hàng ngang hàng (peers) có cùng giá trị sort key.

| Tiêu chí | `ROWS` | `RANGE` |
|---|---|---|
| Cách xác định | Số hàng trước/sau hàng hiện tại | Khoảng giá trị của biểu thức `ORDER BY` |
| Ví dụ | `2 PRECEDING` là hai hàng trước | `INTERVAL 6 DAY PRECEDING` là phạm vi sáu ngày trước |
| Hàng có cùng sort key | Vẫn là các vị trí hàng riêng; cần tie-breaker để thứ tự ổn định | Là peers và được xử lý cùng theo biên `CURRENT ROW` |
| Dùng điển hình | Ba giao dịch gần nhất, 7 bản ghi gần nhất | Tổng/trung bình trong khoảng thời gian hoặc giá trị |

### 6.1. Mặc định RANGE có thể làm tổng chạy dồn khác mong đợi

Trong MySQL, khi một aggregate window có `ORDER BY` nhưng không khai báo frame, frame mặc định là:

```sql
RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
```

Với `RANGE`, các hàng có cùng giá trị `ORDER BY` là peers. Trong dữ liệu mẫu, giao dịch ID 2 và 3 của tài khoản 10 cùng `txn_at`. Truy vấn:

```sql
SELECT
    txn_id,
    txn_at,
    amount,
    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY txn_at
    ) AS default_range_total
FROM account_txn
WHERE account_id = 10
ORDER BY txn_at, txn_id;
```

cho cả ID 2 và ID 3 cùng tổng `175.00`, vì frame của mỗi hàng bao gồm toàn bộ peers ở thời điểm 2/1. Đây không phải lỗi; đó là semantics của `RANGE`.

Nếu muốn tổng tăng theo từng giao dịch, chỉ rõ `ROWS` và tie-breaker:

```sql
SUM(amount) OVER (
    PARTITION BY account_id
    ORDER BY txn_at, txn_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
```

Kết quả cho ID 2 là 150.00 và ID 3 là 175.00. Đừng dựa vào frame mặc định khi yêu cầu nghiệp vụ cần thứ tự từng hàng.

### 6.2. RANGE với khoảng thời gian

Với dữ liệu ngày giờ, `RANGE` có thể dùng khoảng `INTERVAL` nếu `ORDER BY` là một biểu thức thời gian:

```sql
RANGE BETWEEN INTERVAL 6 DAY PRECEDING AND CURRENT ROW
```

Frame này lấy các hàng có giá trị ngày nằm trong khoảng từ sáu ngày trước tới ngày hiện tại, tính theo sort key. Với frame `RANGE` có offset, dùng một biểu thức `ORDER BY` phù hợp; không thêm khóa phụ như `txn_id` vào cùng cửa sổ thời gian này. Nếu cần xác định thứ tự giao dịch từng hàng, đó là yêu cầu khác và nên dùng `ROWS`.

## 7. Trung bình trượt theo 7 ngày lịch

Để tính trung bình theo ngày, trước tiên tổng hợp giao dịch về một hàng mỗi tài khoản mỗi ngày, sau đó áp dụng `RANGE` theo ngày:

```sql
WITH daily_amount AS (
    SELECT
        account_id,
        DATE(txn_at) AS txn_day,
        SUM(amount) AS day_total
    FROM account_txn
    GROUP BY account_id, DATE(txn_at)
)
SELECT
    account_id,
    txn_day,
    day_total,
    AVG(day_total) OVER (
        PARTITION BY account_id
        ORDER BY txn_day
        RANGE BETWEEN INTERVAL 6 DAY PRECEDING AND CURRENT ROW
    ) AS avg_daily_total_7d
FROM daily_amount
ORDER BY account_id, txn_day;
```

Vì `daily_amount` có tối đa một hàng mỗi tài khoản mỗi ngày, frame thời gian có ý nghĩa rõ ràng. `AVG(day_total)` tính trung bình các ngày có hàng trong CTE và bỏ qua `day_total IS NULL`.

### 7.1. Không có hàng không đồng nghĩa ngày đó có giá trị 0

Truy vấn trên chỉ trả những ngày có giao dịch. Nếu tài khoản không có giao dịch ngày 2/1, ngày đó không xuất hiện trong `daily_amount` và không tự được tính là một ngày có tổng bằng 0. Vì vậy, `AVG(day_total)` ở đây là trung bình trên các ngày xuất hiện trong dữ liệu, trong phạm vi bảy ngày lịch.

Nếu yêu cầu là trung bình đúng bảy ngày lịch, kể cả ngày không có giao dịch, cần tạo calendar (bảng ngày) rồi `LEFT JOIN` tổng ngày vào lịch và thay ngày không có giao dịch thành 0 theo quy tắc nghiệp vụ:

```sql
WITH RECURSIVE calendar AS (
    SELECT DATE('2026-01-01') AS calendar_day
    UNION ALL
    SELECT calendar_day + INTERVAL 1 DAY
    FROM calendar
    WHERE calendar_day < '2026-01-31'
),
daily_amount AS (
    SELECT
        account_id,
        DATE(txn_at) AS txn_day,
        SUM(amount) AS day_total
    FROM account_txn
    GROUP BY account_id, DATE(txn_at)
),
account_days AS (
    SELECT
        a.account_id,
        c.calendar_day,
        COALESCE(d.day_total, 0) AS day_total
    FROM (SELECT DISTINCT account_id FROM account_txn) AS a
    CROSS JOIN calendar AS c
    LEFT JOIN daily_amount AS d
        ON d.account_id = a.account_id
       AND d.txn_day = c.calendar_day
)
SELECT
    account_id,
    calendar_day,
    day_total,
    AVG(day_total) OVER (
        PARTITION BY account_id
        ORDER BY calendar_day
        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
    ) AS avg_calendar_7d
FROM account_days
ORDER BY account_id, calendar_day;
```

Ở đây calendar tạo một hàng cho mỗi ngày, nên `ROWS BETWEEN 6 PRECEDING AND CURRENT ROW` tương ứng tối đa bảy ngày liên tiếp. Truy vấn giả định ngày không có bản ghi được xem là tổng 0; nếu `NULL` có nghĩa là dữ liệu chưa được nạp hoặc chưa xác định, không nên tự chuyển thành 0. Với khoảng báo cáo lớn, dùng bảng calendar vật lý thay cho recursive CTE sinh ngày mỗi lần chạy.

## 8. Frame và các biên thường dùng

| Frame | Ý nghĩa |
|---|---|
| `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` | Từ đầu partition tới hàng hiện tại; tổng/trung bình chạy dồn |
| `ROWS BETWEEN 2 PRECEDING AND CURRENT ROW` | Hai hàng trước và hàng hiện tại; tối đa ba hàng |
| `ROWS BETWEEN 6 PRECEDING AND CURRENT ROW` | Sáu hàng trước và hàng hiện tại; tối đa bảy hàng |
| `ROWS BETWEEN 1 PRECEDING AND 1 FOLLOWING` | Một hàng trước, hàng hiện tại và một hàng sau |
| `ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING` | Từ hàng hiện tại tới cuối partition |
| `ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING` | Toàn bộ partition cho mọi hàng |

`PRECEDING` và `FOLLOWING` chỉ số lượng hàng với `ROWS`, hoặc khoảng offset với `RANGE`. Frame bắt đầu/kết thúc phải hợp lệ; không đặt biên bắt đầu nằm sau biên kết thúc.

## 9. NULL và phép tính chạy dồn/trượt

`SUM()` và `AVG()` bỏ qua giá trị `NULL` trong frame:

- Nếu frame có cả số và `NULL`, chỉ các số đóng góp vào tổng/trung bình.
- Nếu frame không có giá trị khác `NULL`, `SUM()` và `AVG()` trả `NULL`.
- `COUNT(*) OVER (...)` đếm mọi hàng trong frame.
- `COUNT(amount) OVER (...)` đếm các giá trị amount khác `NULL` trong frame.

Ví dụ kiểm tra moving average và số quan sát:

```sql
SELECT
    account_id,
    txn_id,
    amount,
    COUNT(*) OVER w AS rows_in_frame,
    COUNT(amount) OVER w AS known_amounts,
    SUM(amount) OVER w AS frame_sum,
    AVG(amount) OVER w AS frame_average
FROM account_txn
WINDOW w AS (
    PARTITION BY account_id
    ORDER BY txn_at, txn_id
    ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
)
ORDER BY account_id, txn_at, txn_id;
```

Named window `w` giúp tránh lặp lại cùng một định nghĩa frame. Có thể đặt `COALESCE(AVG(amount) OVER w, 0)` nếu báo cáo muốn hiển thị 0 khi frame không có giá trị, nhưng hãy cân nhắc trả thêm `known_amounts` để người đọc biết đó là frame không có dữ liệu hợp lệ.

## 10. Lọc dữ liệu trước hay sau window function

Window function được tính trên tập hàng sau `FROM`, `WHERE`, `GROUP BY` và `HAVING` của query block. Vì vậy, vị trí đặt bộ lọc ảnh hưởng trực tiếp tới kết quả. Không thể lọc trực tiếp kết quả window trong `WHERE` hoặc `HAVING` cùng query block; hãy bọc phép tính trong CTE/derived table rồi lọc ở query ngoài.

### 10.1. Lọc trước khi tính cửa sổ

```sql
SELECT
    account_id,
    txn_at,
    amount,
    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY txn_at, txn_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_total_in_filtered_set
FROM account_txn
WHERE txn_at >= '2026-01-03';
```

Các giao dịch trước ngày 3/1 bị loại trước khi tính window. Tổng lũy kế bắt đầu từ những hàng còn lại, không bao gồm lịch sử trước mốc đó.

### 10.2. Tính trên lịch sử trước, rồi lọc kết quả

Nếu muốn hiển thị từ ngày 3/1 nhưng tổng lũy kế vẫn tính cả lịch sử trước đó, đặt window trong CTE rồi lọc ở query ngoài:

```sql
WITH running AS (
    SELECT
        account_id,
        txn_id,
        txn_at,
        amount,
        SUM(amount) OVER (
            PARTITION BY account_id
            ORDER BY txn_at, txn_id
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS running_total
    FROM account_txn
)
SELECT account_id, txn_id, txn_at, amount, running_total
FROM running
WHERE txn_at >= '2026-01-03'
ORDER BY account_id, txn_at, txn_id;
```

Đây là cách thường dùng cho báo cáo có khoảng hiển thị hẹp nhưng cần số dư lũy kế từ đầu lịch sử.

### 10.3. Moving average cũng bị ảnh hưởng bởi WHERE

Nếu lọc chỉ lấy giao dịch từ ngày 3/1 trước khi tính trung bình ba giao dịch, frame đầu tiên của ngày 3/1 không nhìn thấy hai giao dịch trước đó. Nếu muốn trung bình trượt dùng lịch sử trước ngày hiển thị, tính window ở CTE rồi lọc ở ngoài. Với báo cáo lớn, cần cân nhắc chỉ nạp thêm số hàng lịch sử tối thiểu cần cho frame để tránh quét toàn bộ dữ liệu.

## 11. Kiểu dữ liệu và độ chính xác

Với tiền tệ, nên dùng `DECIMAL` thay vì `FLOAT`/`DOUBLE` để hạn chế sai số biểu diễn nhị phân. `SUM()` và `AVG()` trên kiểu số chính xác như `DECIMAL` giữ kết quả kiểu số chính xác theo quy tắc MySQL; kiểu gần đúng có thể tạo sai số làm tròn.

Không ép kết quả thành chuỗi bên trong window nếu còn cần cộng/trung bình hoặc so sánh số. Chỉ định dạng ở query ngoài hoặc tầng ứng dụng:

```sql
WITH metrics AS (
    SELECT
        account_id,
        txn_id,
        AVG(amount) OVER (
            PARTITION BY account_id
            ORDER BY txn_at, txn_id
            ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
        ) AS moving_average
    FROM account_txn
)
SELECT
    account_id,
    txn_id,
    ROUND(moving_average, 2) AS moving_average_display
FROM metrics;
```

`ROUND()` ở đây chỉ làm tròn giá trị trả ra. Nếu dùng kết quả đã làm tròn làm đầu vào cho các phép tính tiếp theo, sai số tích lũy có thể khác so với giữ độ chính xác gốc.

## 12. Index và hiệu năng window query

Truy vấn thường phân vùng theo `account_id` và sắp xếp theo `txn_at`, `txn_id`. Index:

```sql
KEY idx_account_txn_time (account_id, txn_at, txn_id)
```

có thứ tự cột phù hợp với access pattern này: cột partition đứng đầu, tiếp theo là các cột sắp xếp. Index có thể giúp đọc hàng theo thứ tự mong muốn hoặc giảm chi phí sort, nhưng optimizer vẫn quyết định kế hoạch dựa trên thống kê, bộ lọc và kích thước dữ liệu.

Kiểm tra kế hoạch:

```sql
EXPLAIN FORMAT=TREE
SELECT
    account_id,
    txn_id,
    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY txn_at, txn_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_total
FROM account_txn
WHERE account_id = 10;
```

Kiểm tra các bước đọc bảng, sort và xử lý window. `EXPLAIN ANALYZE` trên MySQL 8.0.18 trở lên chạy truy vấn và cung cấp số hàng/thời gian thực tế; dùng trên truy vấn đọc có phạm vi được kiểm soát.

Một số lưu ý:

- Index không loại bỏ chi phí tính window; nó chỉ có thể hỗ trợ truy cập và thứ tự đầu vào.
- Nhiều partition hoặc nhiều cách `ORDER BY` khác nhau có thể cần nhiều bước sort.
- Frame rộng và lượng hàng lớn làm tăng tài nguyên xử lý.
- Chỉ chọn cột cần thiết; tránh đưa BLOB/TEXT lớn vào tập trung gian nếu không cần.
- Index làm tăng dung lượng và chi phí `INSERT`/`UPDATE`/`DELETE`; cân nhắc workload ghi.

## 13. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Tổng lũy kế tăng theo cả tài khoản khác | Thiếu `PARTITION BY account_id` | Chia partition theo khóa nghiệp vụ |
| Tổng ở hai hàng cùng thời điểm giống nhau | Frame mặc định là `RANGE` và hai hàng là peers | Dùng `ROWS` với tie-breaker nếu cần từng hàng |
| Kết quả thay đổi giữa các lần chạy khi có timestamp trùng | `ORDER BY` không xác định thứ tự duy nhất cho `ROWS` | Thêm khóa duy nhất hoặc sequence nghiệp vụ |
| Moving average bao gồm quá nhiều ngày | Dùng `ROWS` nhưng nghĩ nó là số ngày | Dùng `RANGE` theo thời gian hoặc calendar table |
| Trung bình thấp hơn kỳ vọng | `AVG(COALESCE(amount, 0))` hoặc mẫu số bao gồm giá trị thay thế 0 | Xác định ý nghĩa NULL và dùng `AVG(amount)` nếu NULL là thiếu |
| Không thấy ngày không giao dịch trong kết quả | Window chỉ tính trên hàng hiện có | Dùng calendar table và LEFT JOIN nếu cần mọi ngày |
| Tổng lũy kế bị đặt lại ở đầu khoảng báo cáo | Đặt `WHERE` lọc thời gian trước window | Tính window ở CTE rồi lọc kết quả bên ngoài |
| Moving average đầu khoảng thiếu lịch sử | Lọc hàng trước khi window chạy | Nạp đủ số hàng lịch sử cần cho frame hoặc lọc sau window |
| Truy vấn chậm dù đã có index | Window vẫn cần sort/materialize hoặc xử lý nhiều hàng | Kiểm tra `EXPLAIN`, partition/order, frame và lượng dữ liệu |

## 14. Quy trình thiết kế running total và moving average

Trước khi viết SQL, hãy trả lời các câu hỏi:

1. Chỉ số tính riêng theo tài khoản, khách hàng, sản phẩm hay toàn hệ thống? Đây là `PARTITION BY`.
2. Thứ tự nghiệp vụ là thời điểm, ngày, sequence hay ID? Chọn `ORDER BY` và tie-breaker.
3. Cửa sổ là từ đầu lịch sử, ba giao dịch gần nhất, bảy ngày lịch hay một khoảng khác? Chọn frame.
4. `NULL` là thiếu dữ liệu, không phát sinh hay bằng 0? Quyết định cách tính và hiển thị.
5. Có cần bao gồm ngày không phát sinh giao dịch? Nếu có, tạo calendar/dense series trước window.
6. Báo cáo chỉ hiển thị một khoảng hay phép tính cũng chỉ dùng khoảng đó? Đặt filter trước hoặc sau window cho đúng.
7. Kết quả cần giữ độ chính xác tiền tệ bao nhiêu? Dùng `DECIMAL` và làm tròn ở vị trí phù hợp.
8. Dữ liệu lớn đến mức nào? Kiểm tra index, `EXPLAIN` và kế hoạch sort/materialization.

## 15. Bài thực hành

Thực hiện với bảng `account_txn` ở phần 2:

1. Viết tổng chạy dồn theo từng tài khoản với `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`.
2. Viết trung bình chạy dồn và so sánh với tổng lũy kế.
3. Tính `COUNT(*)` và `COUNT(amount)` trên cùng frame; giải thích hàng `amount IS NULL`.
4. Viết trung bình trượt ba giao dịch gần nhất bằng `ROWS BETWEEN 2 PRECEDING AND CURRENT ROW`.
5. Bỏ `txn_id` khỏi `ORDER BY` và bỏ frame để quan sát ảnh hưởng của `RANGE` mặc định với hai giao dịch cùng thời điểm.
6. Thêm `txn_id` và frame `ROWS` để tạo thứ tự từng giao dịch ổn định.
7. Viết frame căn giữa `1 PRECEDING AND 1 FOLLOWING`; xác định vì sao chỉ số này không phù hợp cho dashboard thời gian thực.
8. Tổng hợp số tiền theo ngày rồi tính trung bình trượt bảy ngày bằng `RANGE INTERVAL 6 DAY`.
9. Tạo calendar và tính trung bình bảy ngày lịch, kể cả ngày không có giao dịch; so sánh với trung bình trên các ngày xuất hiện.
10. Tính tổng lũy kế trên toàn bộ lịch sử rồi chỉ hiển thị các giao dịch từ một ngày chọn trước bằng CTE.
11. Thử đặt `WHERE` ở trong query window và ngoài CTE; ghi nhận sự khác nhau của kết quả đầu khoảng.
12. Dùng named window để tái sử dụng định nghĩa partition/order/frame cho `SUM`, `AVG` và `COUNT`.
13. Chạy `EXPLAIN FORMAT=TREE`; so sánh truy vấn có và không có index `(account_id, txn_at, txn_id)` trên dữ liệu lab đủ lớn.

Bạn hoàn thành bài khi giải thích được vì sao hai giao dịch cùng timestamp có thể nhận cùng tổng trong frame `RANGE`, viết được trung bình trượt theo số hàng và theo ngày, đồng thời giữ đúng lịch sử khi lọc khoảng hiển thị.

## 16. Nguyên tắc cần ghi nhớ

- `SUM() OVER` và `AVG() OVER` giữ từng hàng; `GROUP BY` gom hàng thành nhóm.
- `PARTITION BY` làm phép tính bắt đầu lại cho mỗi nhóm.
- `ORDER BY` trong `OVER` quyết định thứ tự tính; `ORDER BY` cuối truy vấn quyết định thứ tự trả kết quả.
- Running total thường dùng `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`.
- Moving average ba hàng thường dùng `ROWS BETWEEN 2 PRECEDING AND CURRENT ROW`.
- `ROWS` đếm vị trí hàng; `RANGE` xét giá trị sort key và peers.
- MySQL mặc định `RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` khi aggregate window có `ORDER BY` nhưng không chỉ rõ frame.
- Thêm tie-breaker duy nhất khi cần thứ tự từng hàng ổn định.
- `AVG()` và `SUM()` bỏ qua `NULL`; dùng `COUNT(amount)` để biết số quan sát hợp lệ trong frame.
- Trung bình theo bảy giao dịch khác trung bình theo bảy ngày lịch.
- Ngày không có hàng không tự được tính là 0; dùng calendar table nếu cần chuỗi ngày đầy đủ.
- Lọc trước window làm thay đổi tập dữ liệu dùng để tính; lọc ở query ngoài nếu cần giữ lịch sử trước khoảng hiển thị.
- Dùng `DECIMAL` cho tiền tệ và chỉ làm tròn ở bước trình bày hoặc theo quy tắc nghiệp vụ.
- Index theo `(partition_key, order_key, tie_breaker)` có thể hỗ trợ truy cập; luôn kiểm tra kế hoạch thực thi thực tế.
