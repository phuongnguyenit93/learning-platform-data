# Khung ROWS/RANGE, khung mặc định và các dòng đồng hạng

Window function tính toán trên một tập hàng liên quan đến hàng hiện tại mà vẫn giữ từng hàng trong kết quả. Với aggregate window function như `SUM() OVER (...)`, khung cửa sổ (*window frame*) quyết định những hàng nào trong partition được đưa vào phép tính tại mỗi hàng. Chọn sai frame có thể làm tổng lũy kế nhảy theo nhóm, rolling average tính theo số ngày thay vì số bản ghi, hoặc `LAST_VALUE()` trả về giá trị hiện tại thay vì giá trị cuối partition.

MySQL hỗ trợ hai đơn vị frame chính là `ROWS` và `RANGE`. `ROWS` xác định frame theo vị trí hàng trong thứ tự cửa sổ; `RANGE` xác định frame theo giá trị của biểu thức sắp xếp và bao gồm các hàng đồng hạng (*peers*). Khi bỏ qua frame clause, MySQL dùng frame mặc định. Nếu không hiểu mặc định này, các hàng có cùng giá trị `ORDER BY` có thể nhận cùng kết quả aggregate dù bạn nghĩ mình đang tính từng hàng một.

Bài học này thuộc module `DATABASE_MYSQL`, bao gồm thiết kế bảng, kiểu dữ liệu, khóa, truy vấn SQL, index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi và tối ưu truy vấn. Nội dung tập trung vào cách xác định frame đúng với yêu cầu nghiệp vụ: theo số hàng, theo khoảng giá trị, theo ngày lịch hay theo toàn bộ partition.

Sau bài học, bạn có thể:

- Giải thích partition, window ordering, frame và peer rows.
- Phân biệt `ROWS` với `RANGE`.
- Dự đoán frame mặc định khi có hoặc không có `ORDER BY`.
- Viết frame tường minh bằng `UNBOUNDED`, `PRECEDING`, `CURRENT ROW` và `FOLLOWING`.
- Tính tổng lũy kế và rolling aggregate theo số hàng hoặc khoảng thời gian.
- Xử lý các hàng đồng hạng và chọn khóa phân xử khi cần thứ tự xác định.
- Tránh lỗi phổ biến với `LAST_VALUE()` và các hàm nhạy với frame.
- Kiểm tra cú pháp, kết quả và hiệu năng window frame trên MySQL.

## 1. Partition, ORDER BY và frame

Một window specification có thể gồm ba phần:

```sql
function_name(expression) OVER (
    PARTITION BY partition_expression
    ORDER BY order_expression
    frame_clause
)
```

- `PARTITION BY` chia dữ liệu thành các nhóm độc lập. Hàm cửa sổ được tính riêng trong từng partition. Nếu không có `PARTITION BY`, toàn bộ tập hàng thuộc một partition.
- `ORDER BY` xác định thứ tự logic của hàng trong partition. Thứ tự này được dùng bởi ranking, navigation và frame.
- `frame_clause` xác định phần nào của partition quanh hàng hiện tại được dùng cho những window function có hỗ trợ frame.

Ví dụ:

```sql
SUM(amount) OVER (
    PARTITION BY account_id
    ORDER BY sold_on, sale_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
) AS running_total
```

Biểu thức này tính tổng lũy kế riêng cho mỗi tài khoản, bắt đầu từ hàng đầu tiên trong partition đến hàng hiện tại. `sale_id` là khóa phân xử để các giao dịch cùng ngày có thứ tự xác định.

Không nhầm `ORDER BY` bên trong `OVER()` với `ORDER BY` của truy vấn ngoài cùng. `OVER(ORDER BY ...)` điều khiển cách tính window function; `ORDER BY` ngoài cùng điều khiển thứ tự hàng được trả về cho client. Muốn kết quả hiển thị có thứ tự, vẫn cần `ORDER BY` ở truy vấn ngoài.

## 2. Fixture dùng để so sánh ROWS và RANGE

Tạo bảng tạm với các giao dịch có ngày trùng nhau và số tiền bằng nhau. Fixture được thiết kế để nhìn thấy rõ tác động của peer rows.

```sql
DROP TEMPORARY TABLE IF EXISTS window_sales;

CREATE TEMPORARY TABLE window_sales (
    sale_id BIGINT UNSIGNED NOT NULL,
    account_id INT UNSIGNED NOT NULL,
    sold_on DATE NOT NULL,
    amount DECIMAL(10, 2) NOT NULL,
    PRIMARY KEY (sale_id),
    KEY idx_window_sales_account_date (account_id, sold_on, sale_id)
) ENGINE = InnoDB;

INSERT INTO window_sales (sale_id, account_id, sold_on, amount) VALUES
(101, 1, '2026-11-01', 100.00),
(102, 1, '2026-11-02',  50.00),
(103, 1, '2026-11-02',  50.00),
(104, 1, '2026-11-04',  20.00),
(105, 1, '2026-11-07',  30.00),
(201, 2, '2026-11-02', 200.00);
```

Dữ liệu của account 1:

| sale_id | sold_on | amount |
| ---: | --- | ---: |
| 101 | 2026-11-01 | 100.00 |
| 102 | 2026-11-02 | 50.00 |
| 103 | 2026-11-02 | 50.00 |
| 104 | 2026-11-04 | 20.00 |
| 105 | 2026-11-07 | 30.00 |

Hai giao dịch 102 và 103 có cùng `sold_on`, vì vậy chúng là peer rows nếu window chỉ `ORDER BY sold_on`. Chúng không phải cùng một giao dịch: `sale_id` khác nhau. Khi thêm `sale_id` vào window ordering, hai hàng không còn đồng hạng vì toàn bộ biểu thức `ORDER BY` đã khác nhau.

## 3. ROWS: frame theo vị trí hàng

`ROWS` xác định frame bằng số hàng trước/sau hàng hiện tại trong thứ tự window. Nó không quan tâm khoảng cách giữa các giá trị sort key.

### 3.1. Tổng lũy kế theo từng hàng

```sql
SELECT
    sale_id,
    account_id,
    sold_on,
    amount,
    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY sold_on, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_total
FROM window_sales
ORDER BY account_id, sold_on, sale_id;
```

Kết quả mong đợi:

| sale_id | account_id | sold_on | amount | running_total |
| ---: | ---: | --- | ---: | ---: |
| 101 | 1 | 2026-11-01 | 100.00 | 100.00 |
| 102 | 1 | 2026-11-02 | 50.00 | 150.00 |
| 103 | 1 | 2026-11-02 | 50.00 | 200.00 |
| 104 | 1 | 2026-11-04 | 20.00 | 220.00 |
| 105 | 1 | 2026-11-07 | 30.00 | 250.00 |
| 201 | 2 | 2026-11-02 | 200.00 | 200.00 |

Với account 1, mỗi hàng thêm đúng amount của chính nó vào tổng trước đó. Hai hàng cùng ngày được xử lý lần lượt theo `sale_id`, nên tổng lần lượt là 150 và 200.

### 3.2. Rolling window ba hàng

```sql
SELECT
    sale_id,
    sold_on,
    amount,
    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY sold_on, sale_id
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS rolling_3_rows_total
FROM window_sales
WHERE account_id = 1
ORDER BY sold_on, sale_id;
```

Kết quả:

| sale_id | amount | rolling_3_rows_total |
| ---: | ---: | ---: |
| 101 | 100.00 | 100.00 |
| 102 | 50.00 | 150.00 |
| 103 | 50.00 | 200.00 |
| 104 | 20.00 | 120.00 |
| 105 | 30.00 | 100.00 |

Frame `2 PRECEDING` đến `CURRENT ROW` chứa tối đa ba hàng: hai hàng trước và hàng hiện tại. Ở sale 104, frame gồm sale 102, 103 và 104 nên tổng là 120. Ở sale 105, frame gồm sale 103, 104 và 105 nên tổng là 100.

Đây là rolling window theo số bản ghi. Nếu một ngày không có giao dịch, ngày đó không tạo thêm một hàng trong frame. Nếu nghiệp vụ cần rolling ba ngày lịch, hãy dùng `RANGE` theo ngày hoặc tạo calendar table rồi join.

### 3.3. ROWS cần thứ tự ổn định khi có tie

Nếu chỉ viết:

```sql
SUM(amount) OVER (
    PARTITION BY account_id
    ORDER BY sold_on
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
```

sale 102 và 103 có cùng sort key. SQL không xác định hàng nào đứng trước hàng nào trong nhóm tie. Tổng lũy kế tại hai hàng đó có thể được gán theo thứ tự khác nhau giữa các kế hoạch thực thi.

Khi frame dùng `ROWS` và kết quả phụ thuộc vị trí từng hàng, hãy thêm khóa duy nhất vào `ORDER BY`, ví dụ `ORDER BY sold_on, sale_id`. Nếu nghiệp vụ không có thứ tự tự nhiên giữa các hàng đồng hạng, hãy xác định rõ quy tắc phân xử trước khi viết truy vấn.

## 4. RANGE: frame theo giá trị ORDER BY

`RANGE` xác định frame dựa trên giá trị của biểu thức sắp xếp. Các hàng có cùng giá trị ở tất cả biểu thức window `ORDER BY` là peers. Khi frame kết thúc tại `CURRENT ROW`, các peer của hàng hiện tại cũng thuộc frame.

### 4.1. RANGE mặc định với ORDER BY

Với aggregate window function có `ORDER BY` nhưng không khai báo frame, MySQL dùng frame mặc định tương đương:

```sql
RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
```

Chạy truy vấn:

```sql
SELECT
    sale_id,
    sold_on,
    amount,
    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY sold_on
    ) AS default_running_total
FROM window_sales
WHERE account_id = 1
ORDER BY sold_on, sale_id;
```

Kết quả mong đợi:

| sale_id | sold_on | amount | default_running_total |
| ---: | --- | ---: | ---: |
| 101 | 2026-11-01 | 100.00 | 100.00 |
| 102 | 2026-11-02 | 50.00 | 200.00 |
| 103 | 2026-11-02 | 50.00 | 200.00 |
| 104 | 2026-11-04 | 20.00 | 220.00 |
| 105 | 2026-11-07 | 30.00 | 250.00 |

Hai hàng ngày 02/11 cùng nhận tổng 200.00 vì frame `RANGE ... CURRENT ROW` bao gồm cả hai peer rows. Đây là khác biệt quan trọng so với `ROWS` có khóa phân xử.

### 4.2. RANGE với khoảng giá trị số

Với biểu thức `ORDER BY` dạng số, offset RANGE biểu diễn khoảng cách giá trị, không phải số hàng:

```sql
RANGE BETWEEN 10 PRECEDING AND CURRENT ROW
```

Nếu sort key hiện tại là 100, frame bao gồm các hàng có sort key trong khoảng từ 90 đến 100 theo thứ tự tăng dần, cùng các peers ở biên. Nó có thể chứa 1, 3 hoặc hàng trăm bản ghi tùy dữ liệu.

Ví dụ trên cột số:

```sql
SELECT
    score,
    SUM(points) OVER (
        ORDER BY score
        RANGE BETWEEN 10 PRECEDING AND CURRENT ROW
    ) AS points_in_score_band
FROM player_scores;
```

Đây là tổng của các hàng có `score` nằm trong dải giá trị 10 điểm đến score hiện tại, không phải tổng của 10 hàng trước đó.

### 4.3. RANGE theo khoảng ngày

Với sort key temporal, có thể dùng `INTERVAL` để xác định khoảng thời gian:

```sql
SELECT
    sale_id,
    sold_on,
    amount,
    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY sold_on
        RANGE BETWEEN INTERVAL 2 DAY PRECEDING AND CURRENT ROW
    ) AS rolling_3_calendar_days_total
FROM window_sales
WHERE account_id = 1
ORDER BY sold_on, sale_id;
```

Kết quả:

| sale_id | sold_on | amount | rolling_3_calendar_days_total |
| ---: | --- | ---: | ---: |
| 101 | 2026-11-01 | 100.00 | 100.00 |
| 102 | 2026-11-02 | 50.00 | 200.00 |
| 103 | 2026-11-02 | 50.00 | 200.00 |
| 104 | 2026-11-04 | 20.00 | 120.00 |
| 105 | 2026-11-07 | 30.00 | 30.00 |

Với ngày 04/11, frame lấy các hàng từ 02/11 đến 04/11, gồm sale 102, 103 và 104. Với ngày 07/11, frame lấy từ 05/11 đến 07/11; chỉ sale 105 nằm trong khoảng nên tổng là 30.00.

`RANGE BETWEEN INTERVAL 2 DAY PRECEDING AND CURRENT ROW` là rolling window theo ba ngày lịch tính cả ngày hiện tại. Nó không sinh thêm hàng cho những ngày không có giao dịch. Nếu cần hiển thị cả ngày trống, kết hợp calendar table/CTE với dữ liệu giao dịch trước khi áp dụng window function.

### 4.4. Giới hạn của RANGE offset trong MySQL

Với frame `RANGE` có offset `expr PRECEDING` hoặc `expr FOLLOWING`, MySQL yêu cầu window `ORDER BY` chỉ có một biểu thức. Biểu thức đó phải có kiểu số hoặc temporal phù hợp với offset; với temporal, dùng dạng `INTERVAL`. Không thể thêm `sale_id` làm khóa phân xử vào cùng `ORDER BY` của ví dụ `RANGE INTERVAL` nếu vẫn muốn dùng offset frame.

Nếu cần thứ tự từng hàng xác định và rolling range theo ngày cùng lúc, hãy phân biệt hai mục tiêu:

- `RANGE` theo ngày tự gom các hàng cùng ngày thành peers.
- `ROWS` theo ngày và ID xác định từng vị trí hàng, nhưng cửa sổ được tính theo số hàng.

Không thể thay thế hai ngữ nghĩa này cho nhau chỉ bằng cách thêm hoặc bỏ một cột trong `ORDER BY`.

## 5. Peer rows và các dòng đồng hạng

Peer rows là các hàng có cùng giá trị trên toàn bộ biểu thức trong window `ORDER BY`. Ví dụ, với `ORDER BY sold_on`, mọi giao dịch cùng ngày là peers. Với `ORDER BY sold_on, sale_id`, chỉ những hàng trùng cả ngày lẫn ID mới là peers; nếu `sale_id` duy nhất thì mỗi hàng là một peer riêng.

Peers ảnh hưởng đến:

- `RANGE ... CURRENT ROW`: frame kết thúc bao gồm toàn bộ peer group.
- Ranking functions như `RANK()` và `DENSE_RANK()`: hàng cùng giá trị sort key nhận cùng hạng theo quy tắc tương ứng.
- Các kết quả aggregate window có frame mặc định `RANGE`: các hàng đồng hạng có thể nhận cùng kết quả tích lũy.

Ví dụ:

```sql
SELECT
    sale_id,
    sold_on,
    amount,
    RANK() OVER (PARTITION BY account_id ORDER BY sold_on) AS date_rank,
    DENSE_RANK() OVER (PARTITION BY account_id ORDER BY sold_on) AS dense_date_rank
FROM window_sales
WHERE account_id = 1
ORDER BY sold_on, sale_id;
```

Hai giao dịch ngày 02/11 có cùng `date_rank` và `dense_date_rank`. `RANK()` để lại khoảng trống sau nhóm tie; `DENSE_RANK()` không để khoảng trống. Thêm `sale_id` vào window ordering sẽ phá nhóm tie và khiến mỗi hàng có thứ hạng riêng, vì vậy chỉ thêm khóa đó nếu nghiệp vụ muốn thứ tự từng hàng thay vì xếp hạng theo ngày.

### 5.1. ORDER BY ngoài cùng không thay đổi peer group

Có thể giữ window `ORDER BY sold_on` để peers được xác định theo ngày, rồi dùng `ORDER BY sold_on, sale_id` ở truy vấn ngoài để hiển thị ổn định:

```sql
SELECT
    sale_id,
    sold_on,
    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY sold_on
    ) AS daily_peer_running_total
FROM window_sales
WHERE account_id = 1
ORDER BY sold_on, sale_id;
```

`ORDER BY` ngoài cùng chỉ sắp xếp các hàng đã tính xong. Nó không thêm `sale_id` vào window ordering và không làm thay đổi frame hoặc peer group.

## 6. Frame mặc định trong MySQL

Đối với các window function có sử dụng frame:

| Window specification | Frame mặc định tương đương |
| --- | --- |
| Có `ORDER BY`, không ghi frame | `RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` |
| Không có `ORDER BY`, không ghi frame | Toàn bộ partition, tương đương `RANGE BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING` |

Ví dụ có `ORDER BY`:

```sql
SUM(amount) OVER (
    PARTITION BY account_id
    ORDER BY sold_on
)
```

Frame kết thúc ở current row và bao gồm peers. Nếu cần tổng lũy kế theo từng hàng, khai báo `ROWS` cùng thứ tự có khóa phân xử.

Ví dụ không có `ORDER BY`:

```sql
SUM(amount) OVER (PARTITION BY account_id)
```

Mỗi hàng của một account nhận tổng amount của toàn bộ partition account đó. Không có thứ tự hàng nên không có khái niệm “trước hàng hiện tại” trong frame mặc định.

Đừng dựa vào frame mặc định trong truy vấn quan trọng. Viết frame tường minh làm rõ ý định và giúp người đọc nhận ra liệu phép tính là tổng toàn partition, tổng lũy kế theo peer group hay tổng lũy kế theo từng hàng.

## 7. Các loại frame boundary

Frame được viết theo dạng:

```sql
ROWS | RANGE BETWEEN frame_start AND frame_end
```

Các boundary thường dùng:

| Boundary | Ý nghĩa |
| --- | --- |
| `UNBOUNDED PRECEDING` | Bắt đầu từ đầu partition |
| `n PRECEDING` | Bắt đầu/kết thúc tại n hàng trước (ROWS) hoặc giá trị cách n đơn vị (RANGE số) |
| `INTERVAL n unit PRECEDING` | Offset temporal cho RANGE, ví dụ 7 ngày trước |
| `CURRENT ROW` | Hàng hiện tại với ROWS; hàng hiện tại và peers với RANGE |
| `n FOLLOWING` | n hàng sau với ROWS hoặc giá trị cách n đơn vị với RANGE số |
| `INTERVAL n unit FOLLOWING` | Offset temporal về phía sau cho RANGE |
| `UNBOUNDED FOLLOWING` | Kết thúc ở cuối partition |

Ví dụ một số frame:

```sql
-- Từ đầu partition tới hàng hiện tại
ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW

-- Hai hàng trước, hàng hiện tại và một hàng sau
ROWS BETWEEN 2 PRECEDING AND 1 FOLLOWING

-- Hàng hiện tại và hai hàng tiếp theo
ROWS BETWEEN CURRENT ROW AND 2 FOLLOWING

-- Toàn bộ partition
ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING

-- Giá trị sort key từ 10 đơn vị trước tới hiện tại
RANGE BETWEEN 10 PRECEDING AND CURRENT ROW
```

Frame start không thể là `UNBOUNDED FOLLOWING`; frame end không thể là `UNBOUNDED PRECEDING`. Các boundary phải tạo thành một khoảng hợp lệ theo thứ tự. Với `ROWS`, offset là số hàng nguyên không âm. Với `RANGE`, offset phải tương thích với kiểu và biểu thức `ORDER BY`.

## 8. LAST_VALUE() và frame mặc định

`LAST_VALUE()` là hàm dễ bị hiểu nhầm khi frame mặc định kết thúc tại current row. Hàm trả giá trị từ hàng cuối của frame hiện tại, không mặc định trả hàng cuối của toàn partition.

Ví dụ:

```sql
SELECT
    sale_id,
    sold_on,
    amount,
    LAST_VALUE(amount) OVER (
        PARTITION BY account_id
        ORDER BY sold_on, sale_id
    ) AS last_value_default,
    LAST_VALUE(amount) OVER (
        PARTITION BY account_id
        ORDER BY sold_on, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) AS last_value_partition
FROM window_sales
WHERE account_id = 1
ORDER BY sold_on, sale_id;
```

Vì window ordering có `sale_id` duy nhất, frame mặc định kết thúc tại hàng hiện tại. Do đó `last_value_default` lần lượt là 100, 50, 50, 20 và 30. Cột `last_value_partition` là 30 trên mọi hàng vì frame tường minh mở rộng đến cuối partition.

Nếu mục tiêu là lấy giá trị cuối cùng của partition, hãy dùng:

```sql
ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
```

Đồng thời, window `ORDER BY` phải mô tả đúng hàng nào được xem là cuối. Nếu có tie mà không có khóa phân xử, “cuối cùng” có thể không xác định.

`FIRST_VALUE()` thường lấy giá trị đầu frame; `NTH_VALUE()` lấy giá trị ở vị trí n trong frame và có thể trả `NULL` khi frame chưa có đủ hàng. Hãy kiểm tra frame tường minh khi dùng các hàm này.

## 9. Hàm nào sử dụng frame?

Frame quan trọng với aggregate window functions như `SUM()`, `AVG()`, `COUNT()`, `MIN()`, `MAX()` và các value functions nhạy với frame như `FIRST_VALUE()`, `LAST_VALUE()`, `NTH_VALUE()`.

Các ranking functions như `ROW_NUMBER()`, `RANK()`, `DENSE_RANK()`, `PERCENT_RANK()`, `CUME_DIST()`, `NTILE()` dựa trên partition và window ordering; frame clause không quyết định kết quả xếp hạng của chúng. `LAG()` và `LEAD()` lấy giá trị ở hàng trước/sau theo thứ tự window, không dùng frame để giới hạn offset.

Vì vậy, không nên thêm frame vào mọi window function theo thói quen. Hãy xác định hàm có sử dụng frame hay không, sau đó khai báo frame khi nó làm rõ hoặc thay đổi tập hàng được tính.

## 10. NULL và frame

Aggregate như `SUM()` và `AVG()` bỏ qua giá trị `NULL` trong frame; `COUNT(expr)` chỉ đếm biểu thức khác `NULL`; `COUNT(*)` đếm hàng trong frame. Nếu frame không chứa giá trị hợp lệ để cộng/trung bình, `SUM()`/`AVG()` có thể trả `NULL`.

Ví dụ:

```sql
SELECT
    sale_id,
    amount,
    COUNT(*) OVER (
        ORDER BY sale_id
        ROWS BETWEEN 1 PRECEDING AND CURRENT ROW
    ) AS frame_rows,
    COUNT(amount) OVER (
        ORDER BY sale_id
        ROWS BETWEEN 1 PRECEDING AND CURRENT ROW
    ) AS non_null_amounts,
    SUM(amount) OVER (
        ORDER BY sale_id
        ROWS BETWEEN 1 PRECEDING AND CURRENT ROW
    ) AS frame_sum
FROM window_sales
ORDER BY sale_id;
```

Frame có thể chứa hai hàng nhưng `COUNT(amount)` chỉ là 1 nếu một hàng có amount NULL. `SUM()` không biến NULL thành 0; nếu muốn hiển thị 0 khi frame không có giá trị số, dùng `COALESCE(SUM(amount) OVER (...), 0)` và bảo đảm đó là quy tắc nghiệp vụ mong muốn.

## 11. Chọn ROWS hay RANGE theo yêu cầu

| Yêu cầu | Frame phù hợp | Lưu ý |
| --- | --- | --- |
| Tổng lũy kế từng giao dịch | `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` | Thêm khóa duy nhất vào window ORDER BY |
| Trung bình 7 giao dịch gần nhất | `ROWS BETWEEN 6 PRECEDING AND CURRENT ROW` | Có thể chứa dữ liệu qua nhiều ngày |
| Tổng trong 7 ngày lịch gần nhất | `RANGE BETWEEN INTERVAL 6 DAY PRECEDING AND CURRENT ROW` | Cần một temporal ORDER BY expression |
| Tổng lũy kế theo ngày, các giao dịch cùng ngày nhận cùng kết quả | `RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` với ORDER BY ngày | Peer rows cùng ngày được tính chung |
| Tổng toàn bộ partition lặp trên từng hàng | Không ORDER BY, hoặc frame unbounded đến unbounded | Không tạo running total |
| Giá trị cuối partition | Frame kết thúc `UNBOUNDED FOLLOWING` với `LAST_VALUE()` | Xác định thứ tự cuối một cách duy nhất |

Trước khi chọn frame, hãy diễn đạt cửa sổ theo ngôn ngữ nghiệp vụ:

- “Ba giao dịch gần nhất” là số hàng: dùng `ROWS`.
- “Bảy ngày lịch gần nhất” là khoảng giá trị ngày: dùng `RANGE`.
- “Tất cả giao dịch cùng ngày nhận cùng tổng lũy kế theo ngày”: dùng peer semantics của `RANGE`.
- “Mỗi giao dịch có tổng lũy kế riêng theo thứ tự ID”: dùng `ROWS` và tie-breaker.

## 12. Những giới hạn và lưu ý riêng của MySQL

- MySQL hỗ trợ frame unit `ROWS` và `RANGE`; không hỗ trợ frame unit `GROUPS`.
- `RANGE` với offset `PRECEDING`/`FOLLOWING` yêu cầu một biểu thức `ORDER BY`; kiểu biểu thức phải tương thích với offset số hoặc temporal.
- Với temporal `RANGE`, dùng `INTERVAL` thích hợp, ví dụ `INTERVAL 7 DAY PRECEDING`.
- Recursive CTE, aggregate và window functions có các quy tắc riêng; không đưa window function vào recursive member của recursive CTE.
- Frame boundary phải hợp lệ; không dùng `UNBOUNDED FOLLOWING` làm điểm bắt đầu hoặc `UNBOUNDED PRECEDING` làm điểm kết thúc.
- Window `ORDER BY` không tự sắp xếp kết quả cuối cùng; truy vấn ngoài vẫn cần `ORDER BY`.
- Frame không làm giảm số hàng trả về; nó chỉ thay đổi tập hàng được dùng cho hàm cửa sổ.

Kiểm tra tài liệu đúng phiên bản MySQL khi dùng offset RANGE temporal hoặc các cú pháp nâng cao. Một số hệ quản trị khác hỗ trợ `GROUPS` và `EXCLUDE`, nhưng không thể sao chép nguyên cú pháp đó sang MySQL.

## 13. Kiểm tra kết quả và hiệu năng

### 13.1. Kiểm tra logic bằng fixture nhỏ

Với mỗi truy vấn frame, xác định trước:

1. Partition nào được tính riêng.
2. Window ordering và khóa phân xử.
3. Peer group nào có cùng sort key.
4. Các hàng thuộc frame tại từng hàng mẫu.
5. Kết quả aggregate mong đợi.

Fixture ở phần 2 đủ để phân biệt:

- `ROWS` cumulative: 150 và 200 ở hai giao dịch cùng ngày.
- Default `RANGE`: cả hai giao dịch cùng ngày đều nhận 200.
- `ROWS 2 PRECEDING`: ba bản ghi gần nhất.
- `RANGE INTERVAL 2 DAY PRECEDING`: ba ngày lịch gần nhất, không phải ba bản ghi.

Khi test, đừng chỉ so sánh tổng cuối partition. Hãy kiểm tra cả các hàng ở giữa, đặc biệt hàng đầu tiên, hàng có tie, hàng sau khoảng trống ngày và hàng cuối.

### 13.2. EXPLAIN và index

Window function có thể cần sắp xếp dữ liệu theo partition/order keys. Index phù hợp đôi khi giúp truy cập theo thứ tự mong muốn hoặc giảm công việc, nhưng optimizer có thể vẫn cần sort/materialize tùy truy vấn và kế hoạch.

Ví dụ:

```sql
EXPLAIN
SELECT
    sale_id,
    account_id,
    sold_on,
    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY sold_on, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_total
FROM window_sales;
```

Index `(account_id, sold_on, sale_id)` phù hợp với partition/order keys của ví dụ, nhưng không đảm bảo MySQL luôn tránh được bước sort. Hãy đọc plan, kiểm tra số hàng thực tế và benchmark trên dữ liệu đại diện. `EXPLAIN ANALYZE` thực thi truy vấn thật, nên cân nhắc tải trước khi dùng.

Các yếu tố cần quan sát:

- Số partition và số hàng trong mỗi partition.
- Chi phí sắp xếp theo các biểu thức `PARTITION BY`/`ORDER BY`.
- Kích thước frame và số hàng cần giữ để tính các frame có `FOLLOWING`.
- Có nhiều window specification khác nhau buộc phải thực hiện nhiều thứ tự hay không.
- Bộ nhớ và temporary table khi dữ liệu lớn.

## 14. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Bỏ frame và nghĩ mặc định là ROWS | Peer rows nhận cùng aggregate | Khai báo `ROWS` tường minh nếu cần từng hàng |
| Dùng ROWS cho khoảng ngày | Frame đếm bản ghi, không đếm ngày | Dùng RANGE temporal hoặc calendar table |
| Dùng RANGE offset với nhiều ORDER BY expressions | MySQL từ chối cú pháp | Chỉ dùng một sort expression cho RANGE offset |
| Không thêm tie-breaker cho ROWS | Thứ tự giữa peer rows không xác định | Thêm khóa duy nhất vào window ORDER BY |
| Thêm khóa duy nhất vào RANGE khi muốn giữ peer group | Peer group bị tách nhỏ | Giữ ORDER BY theo khóa nghiệp vụ và sắp xếp ngoài cùng riêng |
| Nghĩ CURRENT ROW luôn chỉ một hàng | RANGE CURRENT ROW bao gồm peers | Phân biệt semantics ROWS và RANGE |
| Dùng LAST_VALUE với frame mặc định để lấy cuối partition | Thường nhận giá trị hiện tại/peer cuối frame | Mở frame tới UNBOUNDED FOLLOWING |
| Cho rằng window ORDER BY sắp xếp kết quả cuối | Client nhận thứ tự không cam kết | Thêm ORDER BY ở truy vấn ngoài |
| Dùng SUM/AVG mà không xét NULL | Tổng/trung bình có thể không như mong đợi | Kiểm tra COUNT(*) và COUNT(expr), xác định ý nghĩa NULL |

## 15. Bài tập thực hành

1. Chạy fixture ở phần 2. Tính tổng lũy kế bằng frame mặc định và bằng `ROWS`; so sánh sale 102 và 103.
2. Bỏ `sale_id` khỏi `ORDER BY` của `ROWS`. Giải thích vì sao thứ tự lũy kế trong nhóm cùng ngày không được bảo đảm.
3. Viết rolling sum ba hàng bằng `ROWS BETWEEN 2 PRECEDING AND CURRENT ROW`.
4. Viết rolling sum ba ngày lịch bằng `RANGE BETWEEN INTERVAL 2 DAY PRECEDING AND CURRENT ROW`. So sánh sale ngày 07/11 với ROWS.
5. Tạo dữ liệu có nhiều hàng cùng giá trị score. So sánh `RANK()`, `DENSE_RANK()` và aggregate với frame mặc định RANGE.
6. Dùng `LAST_VALUE()` với frame mặc định, sau đó mở frame tới `UNBOUNDED FOLLOWING`. Ghi lại khác biệt.
7. Thử frame `ROWS BETWEEN CURRENT ROW AND 2 FOLLOWING` để tính tổng ba giao dịch từ hiện tại trở đi.
8. Thêm amount NULL vào fixture và so sánh `COUNT(*)`, `COUNT(amount)` và `SUM(amount)` trong frame.
9. Thử `RANGE BETWEEN 10 PRECEDING AND CURRENT ROW` trên một cột số. Xác định những hàng được bao gồm theo giá trị sort key.
10. Chạy `EXPLAIN` cho truy vấn window trước và sau khi có index theo partition/order keys. Giải thích giới hạn của kết luận trên bảng nhỏ.

## 16. Checklist trước khi đưa window frame vào production

- [ ] Đã xác định partition và thứ tự logic của hàng.
- [ ] Đã xác định cửa sổ theo số hàng hay khoảng giá trị/thời gian.
- [ ] Đã ghi frame tường minh nếu không muốn dùng mặc định.
- [ ] Đã xác định peer rows theo toàn bộ biểu thức window ORDER BY.
- [ ] Với ROWS, đã thêm tie-breaker duy nhất khi kết quả phụ thuộc thứ tự từng hàng.
- [ ] Với RANGE offset, chỉ dùng một ORDER BY expression có kiểu tương thích.
- [ ] Với rolling date range, đã chọn đúng INTERVAL và xử lý ngày không có bản ghi.
- [ ] `LAST_VALUE()`/`NTH_VALUE()` có frame phù hợp với yêu cầu.
- [ ] Đã kiểm tra NULL và tập frame không có giá trị.
- [ ] Có ORDER BY ngoài cùng nếu cần thứ tự kết quả ổn định.
- [ ] Đã kiểm tra cú pháp theo phiên bản MySQL triển khai.
- [ ] Đã kiểm tra EXPLAIN và hiệu năng bằng dữ liệu đại diện.

## 17. Tiêu chí hoàn thành

Bạn hoàn thành bài khi có thể giải thích vì sao frame mặc định với `ORDER BY` là `RANGE ... CURRENT ROW`, phân biệt kết quả giữa `ROWS` và `RANGE` khi có peer rows, viết được rolling window theo số hàng và theo ngày lịch, chọn boundary đúng, xử lý `LAST_VALUE()` để lấy giá trị cuối partition, đồng thời bảo đảm thứ tự xác định và đánh giá được chi phí thực thi.

## Tài liệu tham khảo

- [MySQL 8.4 Reference Manual — Window Function Frame Specification](https://dev.mysql.com/doc/refman/8.4/en/window-functions-frames.html)
- [MySQL 8.4 Reference Manual — Window Function Concepts and Syntax](https://dev.mysql.com/doc/refman/8.4/en/window-functions-usage.html)
- [MySQL 8.4 Reference Manual — Window Function Descriptions](https://dev.mysql.com/doc/refman/8.4/en/window-function-descriptions.html)
