# Tổng lũy kế, trung bình trượt và phần trăm theo nhóm trong PostgreSQL

## 1. Bài toán và mục tiêu

Một hệ thống bán hàng có doanh thu phát sinh ở nhiều khu vực và nhiều ngày. Nhóm phân tích cần biết:

- **Doanh thu lũy kế** của mỗi khu vực tính đến từng ngày là bao nhiêu?
- **Trung bình trượt ba ngày** tăng hay giảm như thế nào?
- Mỗi đơn hàng đóng góp **bao nhiêu phần trăm doanh thu khu vực**?
- Một nhóm sản phẩm chiếm **bao nhiêu phần trăm** doanh thu của khu vực?
- Khi có nhiều đơn trong cùng ngày, **thứ tự và khung cửa sổ** ảnh hưởng kết quả ra sao?
- Khi thiếu ngày hoặc tổng bằng 0, làm thế nào để kết quả vẫn có ý nghĩa?

Trong PostgreSQL, **window functions (hàm cửa sổ)** giải quyết những bài toán này mà không bắt buộc phải gộp nhiều hàng thành một hàng kết quả. Khác với `GROUP BY`, cửa sổ cho phép giữ hàng nguồn và tính toán dựa trên **những hàng liên quan** trong cùng một tập kết quả.

Ba mẫu quan trọng nhất:

~~~sql
-- Tổng lũy kế theo thứ tự:
SUM(amount) OVER (
    PARTITION BY region
    ORDER BY sale_date, sale_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)

-- Trung bình trượt ba hàng gần nhất:
AVG(amount) OVER (
    PARTITION BY region
    ORDER BY sale_date, sale_id
    ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
)

-- Phần trăm một hàng trên tổng khu vực:
100 * amount / NULLIF(
    SUM(amount) OVER (PARTITION BY region), 0
)
~~~

Sau bài học, bạn có thể:

1. Phân biệt `GROUP BY` và `OVER(...)` trong các truy vấn báo cáo.
2. Hiểu `PARTITION BY`, `ORDER BY` và window frame `ROWS`, `RANGE`, `GROUPS`.
3. Tính tổng lũy kế theo dòng, ngày, nhóm và khóa phá hòa.
4. Tính trung bình trượt theo **N hàng**, theo **N ngày lịch** và theo dãy ngày đã lấp khoảng trống.
5. Tính tỷ lệ từng hàng, từng danh mục, từng khu vực và tỷ lệ lũy kế.
6. Phòng lỗi chia cho 0, dữ liệu `NULL`, số âm, làm tròn và chênh tỷ lệ.
7. Dùng `LAG`, `FILTER`, CTE, window được đặt tên và `EXPLAIN`.
8. Nhận diện các lỗi thường gặp khi trộn lọc dữ liệu, gom nhóm và window.

> Các lệnh tạo/nạp dữ liệu chỉ dành cho database thực hành được phép. Trên production, cần xem chi phí sort, kích thước partition và quyền truy cập trước khi chạy báo cáo lớn hoặc thêm index.

---

## 2. Dữ liệu thực hành: bán hàng theo khu vực

Để quan sát khác biệt giữa hàng và ngày, bộ dữ liệu có **nhiều đơn cùng ngày**, **ngày không phát sinh giao dịch**, **đơn giá trị 0** và **một dòng hoàn tiền âm**.

~~~sql
CREATE SCHEMA IF NOT EXISTS window_lab;

CREATE TABLE window_lab.sales (
    sale_id BIGINT PRIMARY KEY,
    region TEXT NOT NULL,
    category TEXT NOT NULL,
    sale_date DATE NOT NULL,
    amount NUMERIC(12,2) NOT NULL,
    CONSTRAINT chk_sales_region
        CHECK (region IN ('North', 'South')),
    CONSTRAINT chk_sales_category
        CHECK (category IN ('Books', 'Hardware'))
);
~~~

`amount` là **doanh thu ròng của dòng**, vì vậy dòng hoàn tiền `-20` là hợp lệ trong mô hình báo cáo này. Nếu hệ thống khác yêu cầu doanh thu gộp không âm, phải định nghĩa nghiệp vụ và ràng buộc khác; đừng tự đặt `CHECK(amount >= 0)` khi vẫn cần ghi hoàn tiền.

Nạp dữ liệu:

~~~sql
INSERT INTO window_lab.sales
    (sale_id, region, category, sale_date, amount)
VALUES
    (1001, 'North', 'Books',    DATE '2026-01-01', 100),
    (1002, 'North', 'Hardware', DATE '2026-01-01',  50),
    (1003, 'North', 'Books',    DATE '2026-01-02', 200),
    (1004, 'North', 'Hardware', DATE '2026-01-04',   0),
    (1005, 'North', 'Books',    DATE '2026-01-05', 150),
    (1006, 'North', 'Books',    DATE '2026-01-05', -20),
    (1007, 'North', 'Hardware', DATE '2026-01-07', 120),

    (2001, 'South', 'Books',    DATE '2026-01-01',  80),
    (2002, 'South', 'Books',    DATE '2026-01-03', 120),
    (2003, 'South', 'Hardware', DATE '2026-01-03', 30),
    (2004, 'South', 'Books',    DATE '2026-01-04', 90),
    (2005, 'South', 'Hardware', DATE '2026-01-06', 180),
    (2006, 'South', 'Hardware', DATE '2026-01-07', 0),
    (2007, 'South', 'Books',    DATE '2026-01-07', 50);
~~~

Kiểm tra số dòng và tổng theo khu vực:

~~~sql
SELECT region, COUNT(*) AS sales_count, SUM(amount) AS total_amount
FROM window_lab.sales
GROUP BY region
ORDER BY region;
~~~

| region | sales_count | total_amount |
|---|---:|---:|
| North | 7 | 600.00 |
| South | 7 | 550.00 |

Tổng toàn bộ là **1.150,00**. North có tổng `600` vì `100+50+200+0+150-20+120=600`; South có `80+120+30+90+180+0+50=550`.

**Lưu ý:** `sale_id` là khóa chính và dữ liệu chỉ nên INSERT một lần vào bảng lab trống. Không xóa một bảng đang tồn tại chỉ để chạy lại bài.

### 2.1. Quan sát thứ tự bản ghi

~~~sql
SELECT sale_id, region, category, sale_date, amount
FROM window_lab.sales
ORDER BY region, sale_date, sale_id;
~~~

Hai dòng North vào `2026-01-01`; hai dòng North khác vào `2026-01-05`. South cũng có những ngày nhiều đơn. Các giá trị cùng `sale_date` sẽ là **peers** nếu window chỉ `ORDER BY sale_date`.

---

## 3. GROUP BY khác window function như thế nào?

### 3.1. GROUP BY thu gọn dữ liệu

~~~sql
SELECT region, SUM(amount) AS region_total
FROM window_lab.sales
GROUP BY region
ORDER BY region;
~~~

Kết quả chỉ có **hai hàng** vì mỗi khu vực trở thành một nhóm.

### 3.2. Window giữ từng hàng

~~~sql
SELECT
    sale_id, region, amount,
    SUM(amount) OVER (PARTITION BY region) AS region_total
FROM window_lab.sales
ORDER BY region, sale_id;
~~~

Kết quả vẫn có **14 hàng**. Mỗi dòng North mang thêm `region_total=600`, mỗi dòng South mang `region_total=550`.

Đây là tính chất nền tảng: **window function không làm giảm số hàng giống GROUP BY**. Nếu cần vừa tóm lược từng ngày vừa chạy window trên các ngày đó, ta thường dùng:

~~~text
Bảng giao dịch
       |
       v
GROUP BY region, sale_date  → mỗi ngày một dòng
       |
       v
SUM/AVG ... OVER (...)      → lũy kế/trượt trên các ngày
       |
       v
ORDER BY ...                → thứ tự hiển thị cuối
~~~

### 3.3. OVER không tự bảo đảm thứ tự kết quả cuối

~~~sql
SELECT sale_id,
       SUM(amount) OVER (ORDER BY sale_id) AS running_sum
FROM window_lab.sales;
~~~

`ORDER BY` trong `OVER(...)` xác định **thứ tự tính cửa sổ**, không phải cam kết vĩnh viễn về thứ tự kết quả gửi tới client. Khi giao diện cần thứ tự, viết `ORDER BY` **ngoài**:

~~~sql
SELECT sale_id,
       SUM(amount) OVER (
           ORDER BY sale_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS running_sum
FROM window_lab.sales
ORDER BY sale_id;
~~~

---

## 4. Cấu trúc của một window

Mẫu tổng quát:

~~~sql
aggregate_or_window_function(...) OVER (
    [PARTITION BY partition_expression, ...]
    [ORDER BY sort_expression [ASC|DESC] [NULLS FIRST|LAST], ...]
    [ROWS | RANGE | GROUPS BETWEEN frame_start AND frame_end]
)
~~~

Ba phần có vai trò khác nhau:

| Thành phần | Chức năng | Ví dụ |
|---|---|---|
| `PARTITION BY` | Chia kết quả thành các nhóm **tính toán độc lập** | `PARTITION BY region` |
| `ORDER BY` | Xác định thứ tự logic bên trong từng partition | `ORDER BY sale_date, sale_id` |
| Window frame | Chọn tập hàng trong partition mà aggregate cửa sổ nhìn thấy tại mỗi hàng | `ROWS BETWEEN 2 PRECEDING AND CURRENT ROW` |

### 4.1. PARTITION BY không phải GROUP BY

~~~sql
SUM(amount) OVER (PARTITION BY region)
~~~

Tạo tổng theo từng khu vực nhưng **không làm mất hàng gốc**.

Nếu bỏ `PARTITION BY`:

~~~sql
SUM(amount) OVER ()
~~~

thì tất cả hàng của kết quả đầu vào thuộc **một partition** và hàm SUM cho tổng `1150` trên mỗi hàng, vì window không có ORDER BY và frame mặc định phủ cả partition.

### 4.2. Thêm ORDER BY biến nghĩa thành tổng lũy kế

~~~sql
SUM(amount) OVER (
    PARTITION BY region
    ORDER BY sale_date, sale_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
~~~

Với mỗi dòng, SUM nhìn các hàng từ đầu partition đến **dòng hiện tại** theo thứ tự ngày và ID.

### 4.3. Một partition có thể gồm nhiều khóa

~~~sql
SUM(amount) OVER (
    PARTITION BY region, category
    ORDER BY sale_date, sale_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
~~~

North/Books, North/Hardware, South/Books, South/Hardware có bốn chuỗi lũy kế độc lập.

### 4.4. Nếu ORDER BY chưa đủ phân biệt hàng

`ORDER BY sale_date` có thể xếp nhiều đơn cùng ngày vào **một nhóm peers**. Nếu muốn "sau từng đơn hàng" có thứ tự xác định, thêm khóa duy nhất:

~~~sql
ORDER BY sale_date ASC, sale_id ASC
~~~

Không tự tin rằng PostgreSQL luôn lấy đơn `1001` trước `1002` chỉ vì lần chạy hiện tại như vậy. **Không có tie-breaker, thứ tự tương đối giữa peers không được bảo đảm**.

---

## 5. Window frame: ROWS, RANGE và GROUPS

Đây là phần quyết định tính toán lũy kế/trung bình có đúng hay không.

### 5.1. ROWS: đếm hàng vật lý trong thứ tự logic

~~~sql
ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
~~~

Nghĩa là: **dòng hiện tại và tối đa hai dòng đứng trước** trong partition. Nếu mới là dòng đầu thì frame có một dòng; dòng thứ hai có hai dòng; từ dòng thứ ba có tối đa ba dòng.

`ROWS` không có nghĩa "hai ngày trước". Nếu cùng ngày có năm đơn hàng thì năm đơn vẫn được đếm như năm hàng riêng.

### 5.2. RANGE: theo giá trị của khóa ORDER BY

~~~sql
RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
~~~

Với `ORDER BY sale_date`, frame gồm các hàng có khóa ngày **nhỏ hơn hoặc bằng** ngày hiện tại, bao gồm **tất cả peers cùng ngày**.

Với một khóa thời gian thích hợp, PostgreSQL còn hỗ trợ offset theo khoảng:

~~~sql
RANGE BETWEEN INTERVAL '2 days' PRECEDING AND CURRENT ROW
~~~

Lúc này frame bao gồm những hàng có khóa ORDER BY trong **khoảng hai ngày trước đến hiện tại**, không chỉ hai hàng. Với RANGE có offset, PostgreSQL yêu cầu cấu trúc ORDER BY thích hợp (thông thường **một khóa**).

### 5.3. GROUPS: đếm các nhóm peers

~~~sql
GROUPS BETWEEN 2 PRECEDING AND CURRENT ROW
~~~

Nếu `ORDER BY sale_date`, tất cả đơn trong cùng ngày là **một peer group**. Frame gồm nhóm ngày hiện tại và tối đa hai **nhóm ngày có giao dịch** trước đó. Nó **không** tự lấp ngày trống giữa các ngày.

### 5.4. Bảng phân biệt

| Frame | "2 PRECEDING" đếm theo | Ví dụ ngày 05/01 |
|---|---|---|
| `ROWS` | Hai hàng trước | Có thể là hai đơn trong ngày 05/01 hoặc hàng ngày khác |
| `RANGE` với `INTERVAL '2 days'` | Hai ngày lịch theo giá trị timestamp | Các hàng từ 03/01 đến 05/01 |
| `GROUPS` | Hai nhóm có cùng khóa ORDER BY | Hai ngày **có dữ liệu** trước ngày 05/01 |

### 5.5. Mặc định khi có ORDER BY: cần đặc biệt cẩn thận

Nếu viết:

~~~sql
SUM(amount) OVER (
    PARTITION BY region
    ORDER BY sale_date
)
~~~

PostgreSQL dùng frame mặc định về ý nghĩa tương đương:

~~~sql
RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
~~~

Frame mặc định bao gồm **các peers cùng khóa ORDER BY**. Vì vậy hai đơn North cùng ngày 01/01 đều có kết quả lũy kế **150** chứ không phải lần lượt 100 rồi 150.

### 5.6. Không có ORDER BY thì frame mặc định gồm cả partition

~~~sql
SUM(amount) OVER (PARTITION BY region)
~~~

trả tổng **600** cho mọi dòng North và **550** cho mọi dòng South. Đây không phải tổng lũy kế vì không có thứ tự tiến triển.

### 5.7. Full-partition frame khi có ORDER BY

Nếu cần tổng vùng **dù có ORDER BY**, có thể viết:

~~~sql
SUM(amount) OVER (
    PARTITION BY region
    ORDER BY sale_date, sale_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
)
~~~

Nhưng nếu mục đích chỉ là **tổng vùng**, cách đơn giản và ít gây nhầm hơn thường là `SUM(amount) OVER (PARTITION BY region)` không có ORDER BY.

---

## 6. Tổng lũy kế theo từng giao dịch

### 6.1. Query chuẩn với tie-breaker

~~~sql
SELECT
    region,
    sale_date,
    sale_id,
    amount,
    SUM(amount) OVER (
        PARTITION BY region
        ORDER BY sale_date ASC, sale_id ASC
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_amount
FROM window_lab.sales
ORDER BY region, sale_date, sale_id;
~~~

Đối với North:

| sale_id | sale_date | amount | running_amount |
|---:|---|---:|---:|
| 1001 | 2026-01-01 | 100 | 100 |
| 1002 | 2026-01-01 | 50 | 150 |
| 1003 | 2026-01-02 | 200 | 350 |
| 1004 | 2026-01-04 | 0 | 350 |
| 1005 | 2026-01-05 | 150 | 500 |
| 1006 | 2026-01-05 | -20 | 480 |
| 1007 | 2026-01-07 | 120 | 600 |

Nhờ khóa `sale_id`, câu SQL diễn đạt rõ thứ tự **nội bộ một ngày**. Dòng hoàn tiền `-20` khiến tổng lũy kế có thể **giảm**, điều này đúng với định nghĩa doanh thu ròng, không phải lỗi window.

### 6.2. Tổng lũy kế là phép cộng prefix

Với dãy giá trị đã sắp `x1, x2, ..., xn`:

~~~text
running_sum(i) = x1 + x2 + ... + xi
~~~

Window frame `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` biểu diễn prefix đó cho từng partition.

### 6.3. Không bỏ ORDER BY nếu cần lũy kế

~~~sql
SUM(amount) OVER (PARTITION BY region)
~~~

trả **tổng cuối cùng** cho mọi dòng vùng, không phải prefix. Khi viết tên cột `running_total` mà không có ORDER BY, tên gọi và thực tế đã mâu thuẫn.

### 6.4. Không dùng ORDER BY sai chiều

Nếu sắp:

~~~sql
ORDER BY sale_date DESC, sale_id DESC
~~~

với frame prefix, bạn đang lũy kế từ **đơn mới nhất lùi về cũ**, khác yêu cầu "tính đến thời điểm này" theo thời gian tăng dần. Chọn chiều đúng cho định nghĩa nghiệp vụ.

---

## 7. Tổng lũy kế theo ngày thay vì theo giao dịch

Dashboard thường muốn **một hàng cho mỗi ngày mỗi khu vực**. Trước hết phải tổng hợp đơn hàng cùng ngày, sau đó mới tính window.

### 7.1. Gom nhóm ngày

~~~sql
SELECT
    region,
    sale_date,
    SUM(amount) AS daily_amount
FROM window_lab.sales
GROUP BY region, sale_date
ORDER BY region, sale_date;
~~~

North có:

| sale_date | daily_amount |
|---|---:|
| 2026-01-01 | 150 |
| 2026-01-02 | 200 |
| 2026-01-04 | 0 |
| 2026-01-05 | 130 |
| 2026-01-07 | 120 |

Ngày 03/01 và 06/01 **không có dòng**. Nếu nghiệp vụ cần coi đó là ngày 0 doanh thu, phải dựng lịch riêng.

### 7.2. Tổng hợp rồi dùng window

~~~sql
WITH daily AS (
    SELECT
        region,
        sale_date,
        SUM(amount) AS daily_amount
    FROM window_lab.sales
    GROUP BY region, sale_date
)
SELECT
    region, sale_date, daily_amount,
    SUM(daily_amount) OVER (
        PARTITION BY region
        ORDER BY sale_date
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_daily_total
FROM daily
ORDER BY region, sale_date;
~~~

Kết quả North:

| sale_date | daily_amount | running_daily_total |
|---|---:|---:|
| 2026-01-01 | 150 | 150 |
| 2026-01-02 | 200 | 350 |
| 2026-01-04 | 0 | 350 |
| 2026-01-05 | 130 | 480 |
| 2026-01-07 | 120 | 600 |

Điểm quan trọng: `daily` có **mỗi ngày đúng một dòng trong mỗi vùng**, nên `ORDER BY sale_date` đã xác định duy nhất thứ tự trong partition, không cần thêm `sale_id`.

### 7.3. Tổng ngày và tổng đơn là hai mức chi tiết khác nhau

Nếu bạn vừa `GROUP BY` ngày rồi tính `AVG`, đó là trung bình **doanh thu mỗi ngày có dữ liệu**, không phải trung bình **giá trị mỗi đơn**. Đừng trộn hai mức chi tiết trong cùng lời giải báo cáo mà không nêu rõ.

---

## 8. Peers và lỗi mặc định RANGE làm "nhảy" lũy kế

Xem riêng North trong hai cách tính:

~~~sql
SELECT
    sale_id, sale_date, amount,
    SUM(amount) OVER (
        PARTITION BY region
        ORDER BY sale_date
    ) AS default_running,
    SUM(amount) OVER (
        PARTITION BY region
        ORDER BY sale_date, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS row_running
FROM window_lab.sales
WHERE region = 'North'
ORDER BY sale_date, sale_id;
~~~

Phần đầu kết quả:

| sale_id | sale_date | amount | default_running | row_running |
|---:|---|---:|---:|---:|
| 1001 | 2026-01-01 | 100 | 150 | 100 |
| 1002 | 2026-01-01 | 50 | 150 | 150 |
| 1003 | 2026-01-02 | 200 | 350 | 350 |
| 1004 | 2026-01-04 | 0 | 350 | 350 |
| 1005 | 2026-01-05 | 150 | 480 | 500 |
| 1006 | 2026-01-05 | -20 | 480 | 480 |
| 1007 | 2026-01-07 | 120 | 600 | 600 |

Nguyên nhân:

- `default_running` dùng frame mặc định `RANGE ... CURRENT ROW`, **gom cả peers cùng sale_date**.
- `row_running` có thứ tự `sale_date, sale_id` và frame `ROWS`, nên cộng **từng giao dịch**.

Cả hai đều có thể đúng, tùy yêu cầu:

- "Lũy kế tính đến **hết ngày**": tổng peers cùng ngày có thể là điều mong muốn.
- "Lũy kế **sau mỗi giao dịch**": dùng `ROWS` với tie-breaker xác định.

Không tự chọn một cách mà chưa xác định mức chi tiết.

---

## 9. Tổng lũy kế theo nhiều chiều

### 9.1. Theo từng khu vực và danh mục

~~~sql
SELECT
    region, category, sale_date, sale_id, amount,
    SUM(amount) OVER (
        PARTITION BY region, category
        ORDER BY sale_date, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_category_amount
FROM window_lab.sales
ORDER BY region, category, sale_date, sale_id;
~~~

North/Books sẽ có dãy: `100, 300, 450, 430` theo các sale_id `1001,1003,1005,1006`. North/Hardware sẽ có `50,50,170`, độc lập với Books.

### 9.2. Lũy kế theo tháng qua nhiều tháng

Với bảng thực tế có các giao dịch nhiều tháng, thường tạo:

~~~sql
WITH monthly AS (
    SELECT
        region,
        date_trunc('month', sale_date::timestamp)::date
            AS month_start,
        SUM(amount) AS monthly_amount
    FROM window_lab.sales
    GROUP BY region,
             date_trunc('month', sale_date::timestamp)::date
)
SELECT
    region, month_start, monthly_amount,
    SUM(monthly_amount) OVER (
        PARTITION BY region
        ORDER BY month_start
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS cumulative_amount
FROM monthly
ORDER BY region, month_start;
~~~

Với dữ liệu lab chỉ có tháng 01/2026, mỗi khu vực có một tháng; câu này minh họa mẫu đúng cho tập dữ liệu dài hơn.

### 9.3. Khi muốn lũy kế lại từ đầu mỗi tháng

Nếu bảng có nhiều tháng, partition theo cả vùng và đầu tháng:

~~~sql
SUM(amount) OVER (
    PARTITION BY region, date_trunc('month', sale_date::timestamp)
    ORDER BY sale_date, sale_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
~~~

Cách này **reset** về 0 ở mỗi tháng mới trong cùng vùng. Khác với `PARTITION BY region` tiếp tục cộng xuyên nhiều tháng.

---

## 10. Trung bình trượt ba hàng quan sát

### 10.1. AVG trên hai hàng trước và hàng hiện tại

~~~sql
WITH daily AS (
    SELECT region, sale_date, SUM(amount) AS daily_amount
    FROM window_lab.sales
    GROUP BY region, sale_date
)
SELECT
    region, sale_date, daily_amount,
    AVG(daily_amount) OVER (
        PARTITION BY region
        ORDER BY sale_date
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS moving_avg_3_observed_days
FROM daily
ORDER BY region, sale_date;
~~~

North:

| sale_date | daily_amount | moving_avg_3_observed_days |
|---|---:|---:|
| 2026-01-01 | 150 | 150.0000 |
| 2026-01-02 | 200 | 175.0000 |
| 2026-01-04 | 0 | 116.6667 |
| 2026-01-05 | 130 | 110.0000 |
| 2026-01-07 | 120 | 83.3333 |

Diễn giải:

- Ngày 01/01 có **một** hàng trong frame → AVG=150.
- Ngày 02/01 có **hai** hàng → `(150+200)/2=175`.
- Ngày 04/01 có **ba** hàng → `(150+200+0)/3 ≈ 116,67`.
- Ngày 05/01: `(200+0+130)/3=110`.
- Ngày 07/01: `(0+130+120)/3 ≈ 83,33`.

**Đây là ba ngày có dữ liệu gần nhất**, không phải ba **ngày lịch liên tiếp**. 03/01 và 06/01 không tồn tại trong `daily`.

### 10.2. Trung bình trượt trên giao dịch, không phải ngày

~~~sql
SELECT
    region, sale_date, sale_id, amount,
    AVG(amount) OVER (
        PARTITION BY region
        ORDER BY sale_date, sale_id
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS avg_last_3_transactions
FROM window_lab.sales
ORDER BY region, sale_date, sale_id;
~~~

Ý nghĩa là giá trị trung bình **ba giao dịch gần nhất** (theo thứ tự ngày/ID), không phải doanh thu ba ngày. Nếu trong một ngày có 20 đơn, frame ba hàng có thể chỉ gồm **ba đơn cùng ngày**.

### 10.3. Muốn đúng ba hàng trước đó, chưa đủ dữ liệu thì trả NULL

Nhiều dashboard yêu cầu chỉ hiển thị trung bình trượt khi có đủ **ba** quan sát:

~~~sql
WITH daily AS (
    SELECT region, sale_date, SUM(amount) AS daily_amount
    FROM window_lab.sales
    GROUP BY region, sale_date
),
rolling AS (
    SELECT
        region, sale_date, daily_amount,
        AVG(daily_amount) OVER (
            PARTITION BY region
            ORDER BY sale_date
            ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
        ) AS avg_3,
        COUNT(*) OVER (
            PARTITION BY region
            ORDER BY sale_date
            ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
        ) AS n_rows
    FROM daily
)
SELECT
    region, sale_date, daily_amount,
    CASE WHEN n_rows = 3 THEN avg_3 END AS full_window_avg
FROM rolling
ORDER BY region, sale_date;
~~~

Hai ngày đầu của mỗi vùng có `full_window_avg NULL` vì chưa đủ ba **hàng quan sát**.

### 10.4. AVG bỏ qua NULL, không bỏ qua số 0

Nếu một ngày có `daily_amount=0` thì `AVG` **tính số 0** vào trung bình. Nếu `daily_amount IS NULL`, `AVG` bỏ qua giá trị NULL, dẫn tới số lượng mẫu nhỏ hơn `COUNT(*)`.

Trong dữ liệu lab, amount `NOT NULL` nên sau `SUM` trên ngày có hàng, daily_amount luôn không NULL. Nhưng khi LEFT JOIN lịch trống, các ngày không có hàng có thể cần `COALESCE(daily_amount,0)` theo quy tắc dashboard.

---

## 11. Trung bình trượt theo khoảng ba ngày lịch

### 11.1. RANGE khác ROWS khi ngày không liên tục

Với ngày 05/01, "ba ngày lịch kết thúc hôm nay" là **03, 04, 05/01**, không phải ba ngày có giao dịch 02, 04, 05/01.

Giữ bảng `daily` và dùng `RANGE` theo timestamp:

~~~sql
WITH daily AS (
    SELECT region, sale_date, SUM(amount) AS daily_amount
    FROM window_lab.sales
    GROUP BY region, sale_date
)
SELECT
    region, sale_date, daily_amount,
    AVG(daily_amount) OVER (
        PARTITION BY region
        ORDER BY sale_date::timestamp
        RANGE BETWEEN INTERVAL '2 days' PRECEDING
                  AND CURRENT ROW
    ) AS avg_observed_within_3_calendar_days
FROM daily
ORDER BY region, sale_date;
~~~

Trong North:

- Ngày **05/01**: frame trong khoảng 03–05/01 gồm **04/01=0, 05/01=130** → AVG `65`, vì 03/01 không có hàng.
- Ngày **07/01**: frame trong khoảng 05–07/01 gồm **05/01=130, 07/01=120** → AVG `125`, vì 06/01 không có hàng.

`RANGE` giới hạn theo **khoảng giá trị ngày-giờ**, nhưng không tự sinh những ngày thiếu. Trung bình chỉ tính trên các hàng **thật sự có trong frame**.

### 11.2. Ba ngày lịch với ngày không phát sinh được coi là 0

Nếu nghiệp vụ yêu cầu "trung bình doanh thu một ngày qua ba ngày lịch", cần tạo lịch đủ ngày trước, điền 0 vào ngày không có giao dịch rồi mới áp ROWS.

Không nên ghi chung chung "MA 3 ngày" khi chưa chốt:

1. **Ba quan sát gần nhất**.
2. **Các quan sát nằm trong ba ngày lịch gần nhất**.
3. **Ba ngày lịch liên tiếp, ngày không giao dịch = 0**.

Ba định nghĩa có thể cho **ba kết quả khác nhau**.

### 11.3. Dữ liệu thời gian ở mức timestamp

Nếu cửa sổ cần "24 giờ vừa qua" trên `timestamptz`:

~~~sql
AVG(amount) OVER (
    PARTITION BY region
    ORDER BY occurred_at
    RANGE BETWEEN INTERVAL '24 hours' PRECEDING
              AND CURRENT ROW
)
~~~

Đây là mẫu dành cho bảng có cột `occurred_at TIMESTAMPTZ` (chưa tồn tại trong schema lab). Nó tính trên các sự kiện thuộc **24 giờ thực** trước mỗi instant, khác một "ngày lịch" ở vùng có DST.

---

## 12. Lấp ngày trống bằng generate_series trước khi tính trung bình

Muốn có ngày 01–07/01 cho **cả hai vùng**, kể cả những ngày không có doanh thu, có thể dùng `generate_series`:

~~~sql
WITH regions AS (
    SELECT DISTINCT region FROM window_lab.sales
),
calendar AS (
    SELECT g::date AS sale_date
    FROM generate_series(
        DATE '2026-01-01'::timestamp,
        DATE '2026-01-07'::timestamp,
        INTERVAL '1 day'
    ) AS dates(g)
),
daily AS (
    SELECT region, sale_date, SUM(amount) AS daily_amount
    FROM window_lab.sales
    GROUP BY region, sale_date
),
dense_daily AS (
    SELECT
        r.region,
        c.sale_date,
        COALESCE(d.daily_amount, 0::numeric) AS daily_amount
    FROM regions AS r
    CROSS JOIN calendar AS c
    LEFT JOIN daily AS d
      ON d.region = r.region
     AND d.sale_date = c.sale_date
)
SELECT
    region, sale_date, daily_amount,
    AVG(daily_amount) OVER (
        PARTITION BY region
        ORDER BY sale_date
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS avg_3_calendar_days
FROM dense_daily
ORDER BY region, sale_date;
~~~

North sau khi lấp lịch:

| Ngày | Doanh thu ngày | Trung bình 3 hàng lịch (trong giai đoạn đầu dùng số ngày đã có) |
|---|---:|---:|
| 01/01 | 150 | 150.0000 |
| 02/01 | 200 | 175.0000 |
| 03/01 | 0 | 116.6667 |
| 04/01 | 0 | 66.6667 |
| 05/01 | 130 | 43.3333 |
| 06/01 | 0 | 43.3333 |
| 07/01 | 120 | 83.3333 |

Ví dụ **05/01**: trung bình `(0+0+130)/3 = 43,3333`, khác:

- `110` nếu lấy ba ngày **có dữ liệu gần nhất** (02, 04, 05).
- `65` nếu chỉ lấy những hàng có dữ liệu trong **ba ngày lịch** (04 và 05).

Việc đặt `COALESCE(..., 0)` là **quyết định nghiệp vụ**: không có giao dịch thì doanh thu ngày bằng 0. Với đo lường nhiệt độ/cảm biến, "không có dữ liệu" có thể cần **NULL** chứ không phải 0.

### 12.1. Lấy trung bình chỉ khi đủ ba ngày

Có thể dùng `COUNT(*) OVER (...)` trên `dense_daily` rồi chỉ hiển thị AVG khi số hàng trong frame bằng 3. Nếu cần tính từ khi khởi động hệ thống chứ không phải từ ngày bắt đầu báo cáo, dựng lịch đủ **hai ngày trước ranh giới báo cáo** để có dữ liệu lịch sử cần thiết cho frame.

### 12.2. Dữ liệu lớn

Với nhiều triệu vùng/đối tượng và dải ngày quá rộng, `CROSS JOIN regions × calendar` có thể tạo số hàng rất lớn. Cần chọn đúng phạm vi, lọc nhóm, cân nhắc bảng calendar chuẩn, incremental rollups hoặc preaggregation. Không tạo chuỗi ngày không giới hạn trong production.

---

## 13. Moving SUM, AVG và số lượng quan sát

Ba hàm thường được dùng cùng một frame:

~~~sql
WITH daily AS (
    SELECT region, sale_date, SUM(amount) AS daily_amount
    FROM window_lab.sales
    GROUP BY region, sale_date
)
SELECT
    region, sale_date, daily_amount,
    SUM(daily_amount) OVER w AS rolling_sum,
    AVG(daily_amount) OVER w AS rolling_avg,
    COUNT(*) OVER w AS observed_days
FROM daily
WINDOW w AS (
    PARTITION BY region
    ORDER BY sale_date
    ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
)
ORDER BY region, sale_date;
~~~

`WINDOW w AS (...)` giúp định nghĩa một frame **một lần**, tái sử dụng cho SUM/AVG/COUNT. Kết quả theo cửa sổ:

~~~text
rolling_sum = tổng giá trị có trong frame
rolling_avg = trung bình các giá trị không NULL có trong frame
observed_days = số hàng hiện diện trong frame
~~~

### 13.1. AVG của giao dịch khác AVG của doanh thu ngày

Giả sử ngày 01/01 North có hai đơn 100 và 50; ngày 02/01 có một đơn 200.

- Trung bình **ba đơn** là `(100+50+200)/3 ≈ 116,67`.
- Trung bình **hai ngày có giao dịch** là `(150+200)/2 = 175`.

Cùng một dữ liệu, hai câu trả lời khác vì mẫu số khác. Luôn mô tả **đơn vị phân tích** trong tên cột/API.

### 13.2. Trung bình có trọng số

Khi từng dòng đại diện lượng khác nhau (ví dụ giá đơn vị với số lượng hàng), trung bình số học không phải giá bình quân đúng. Với bảng có `unit_price`, `quantity`:

~~~sql
SUM(unit_price * quantity) OVER w
/
NULLIF(SUM(quantity) OVER w, 0)
~~~

Đây là công thức **trung bình có trọng số** theo số lượng, là mẫu khái niệm cho schema khác. Không dùng `AVG(unit_price)` nếu số lượng từng dòng khác nhau mà muốn giá bình quân theo sản phẩm.

### 13.3. NULL và COUNT

`AVG(x)` bỏ qua NULL, `COUNT(x)` đếm giá trị không NULL, còn `COUNT(*)` đếm hàng. Nếu dữ liệu nguồn cho phép thiếu `amount`, cần quyết định giữa:

- Bỏ qua dòng thiếu khi tính AVG.
- Coi thiếu là 0 bằng `COALESCE`.
- Không công bố trung bình nếu thiếu quá nhiều dữ liệu.

Không có một lựa chọn đúng cho mọi nghiệp vụ.

---

## 14. Phần trăm đóng góp của từng giao dịch theo khu vực

### 14.1. Công thức

Với giao dịch có doanh thu `amount`, tỷ lệ đóng góp vào tổng vùng là:

~~~text
pct_of_region = 100 × amount / total_amount_of_region
~~~

Trong PostgreSQL:

~~~sql
SELECT
    region, sale_date, sale_id, category, amount,
    SUM(amount) OVER (PARTITION BY region) AS region_total,
    ROUND(
        100.0 * amount
        / NULLIF(SUM(amount) OVER (PARTITION BY region), 0),
        2
    ) AS pct_of_region
FROM window_lab.sales
ORDER BY region, sale_date, sale_id;
~~~

Điểm cần nhớ:

- `PARTITION BY region` xác định **mẫu số**.
- **Không có ORDER BY trong OVER** vì mẫu số là tổng **toàn khu vực**, không phải tổng lũy kế đến dòng hiện tại.
- `100.0` diễn đạt phép tính ở kiểu numeric thay vì vô ý chia số nguyên rồi nhân 100.
- `NULLIF(total,0)` tránh lỗi chia cho 0 và trả NULL khi tỷ lệ không xác định.
- `ROUND(...,2)` chỉ làm tròn **kết quả hiển thị**, không nên làm tròn từng thành phần quá sớm.

### 14.2. Kết quả North

Vì tổng North là `600`:

| sale_id | amount | pct_of_region |
|---:|---:|---:|
| 1001 | 100 | 16.67% |
| 1002 | 50 | 8.33% |
| 1003 | 200 | 33.33% |
| 1004 | 0 | 0.00% |
| 1005 | 150 | 25.00% |
| 1006 | -20 | -3.33% |
| 1007 | 120 | 20.00% |

Tổng các giá trị **chưa làm tròn** là 100%. Nếu cộng các tỷ lệ đã làm tròn, kết quả có thể chênh nhẹ 100% vì sai số làm tròn; đây không nhất thiết là lỗi SQL.

### 14.3. Vì sao xuất hiện phần trăm âm?

Giao dịch `1006` là hoàn tiền `-20`, nên đóng góp `-3,33%` vào **doanh thu ròng** của North. Mẫu số `600` đã chứa dòng hoàn tiền. Đây là một định nghĩa tỷ lệ hợp lệ về **net contribution**.

Tuy nhiên, nếu dashboard yêu cầu "tỷ trọng doanh thu bán hàng dương", cần **loại hoặc tách hoàn tiền**, hoặc có metric riêng cho gross sales/refunds. Không được tự thay `-20` bằng `20` chỉ để tránh tỷ lệ âm.

### 14.4. Một truy vấn có thể vừa trả tổng vùng, vừa tỷ lệ

~~~sql
WITH with_total AS (
    SELECT
        sale_id, region, category, sale_date, amount,
        SUM(amount) OVER (PARTITION BY region) AS region_total
    FROM window_lab.sales
)
SELECT
    *,
    ROUND(100.0 * amount / NULLIF(region_total,0), 2)
        AS pct_of_region
FROM with_total
ORDER BY region, sale_date, sale_id;
~~~

Cách tách CTE giúp không lặp công thức mẫu số ở nhiều cột; cũng thuận tiện khi cần kiểm tra tổng vùng trong báo cáo.

---

## 15. Phần trăm tổng toàn hệ thống và phần trăm theo khu vực

### 15.1. Tỷ lệ khu vực trong tổng công ty

Nếu muốn mỗi **khu vực một dòng**:

~~~sql
WITH region_totals AS (
    SELECT region, SUM(amount) AS region_amount
    FROM window_lab.sales
    GROUP BY region
)
SELECT
    region,
    region_amount,
    SUM(region_amount) OVER () AS company_amount,
    ROUND(
        100.0 * region_amount
        / NULLIF(SUM(region_amount) OVER (), 0),
        2
    ) AS pct_of_company
FROM region_totals
ORDER BY region;
~~~

Kết quả:

| region | region_amount | company_amount | pct_of_company |
|---|---:|---:|---:|
| North | 600 | 1150 | 52.17% |
| South | 550 | 1150 | 47.83% |

Khác với phần 14:

- Phần 14: **mỗi giao dịch trên tổng khu vực**.
- Phần 15: **mỗi khu vực trên tổng công ty**.

Không dùng nhầm `PARTITION BY region` cho mẫu số công ty; khi đầu vào đã là `region_totals`, `SUM(region_amount) OVER ()` là tổng **tất cả khu vực**.

### 15.2. Tỷ lệ theo hai cấp độ cùng một truy vấn

Trên từng giao dịch, có thể tính:

~~~sql
SELECT
    sale_id, region, amount,
    ROUND(
        100.0 * amount
        / NULLIF(SUM(amount) OVER (PARTITION BY region), 0),
        2
    ) AS pct_of_region,
    ROUND(
        100.0 * amount
        / NULLIF(SUM(amount) OVER (), 0),
        2
    ) AS pct_of_company
FROM window_lab.sales
ORDER BY region, sale_id;
~~~

Hai cột dùng **hai mẫu số khác nhau**. Mỗi bên có ý nghĩa riêng; không cộng tỷ lệ giao dịch trên tổng vùng với tỷ lệ trên tổng công ty rồi diễn giải như một metric.

---

## 16. Phần trăm mỗi danh mục trong một khu vực

Yêu cầu:

> Trong khu vực North, Books và Hardware lần lượt đóng góp bao nhiêu phần trăm **tổng doanh thu North**?

Cần gom về **mỗi cặp vùng–danh mục một hàng**, rồi chạy window trên kết quả đã gom:

~~~sql
WITH category_totals AS (
    SELECT
        region,
        category,
        SUM(amount) AS category_amount
    FROM window_lab.sales
    GROUP BY region, category
)
SELECT
    region,
    category,
    category_amount,
    SUM(category_amount) OVER (
        PARTITION BY region
    ) AS region_amount,
    ROUND(
        100.0 * category_amount
        / NULLIF(
            SUM(category_amount) OVER (PARTITION BY region),
            0
        ),
        2
    ) AS pct_category_in_region
FROM category_totals
ORDER BY region, category;
~~~

Kết quả:

| region | category | category_amount | region_amount | pct_category_in_region |
|---|---|---:|---:|---:|
| North | Books | 430 | 600 | 71.67% |
| North | Hardware | 170 | 600 | 28.33% |
| South | Books | 340 | 550 | 61.82% |
| South | Hardware | 210 | 550 | 38.18% |

### 16.1. Công thức toán học

Với khu vực r và danh mục c:

~~~text
category_amount(r,c) = tổng amount của các dòng trong nhóm (r,c)
region_amount(r)     = tổng amount của các danh mục thuộc r

share(r,c) = 100 × category_amount(r,c) / region_amount(r)
~~~

### 16.2. Vì sao không chọn category trên từng giao dịch rồi dùng SUM(amount) OVER (PARTITION BY category)?

`PARTITION BY category` sẽ tính tổng **Books trên cả North và South**, không phải Books **trong từng vùng**. Mẫu số "tổng danh mục toàn hệ thống" khác "tổng vùng".

Phải xác định **cấp báo cáo ở tử số** và **phạm vi ở mẫu số** trước khi viết window.

### 16.3. Kiểm tra tỷ lệ cộng về 100%

~~~sql
WITH category_totals AS (
    SELECT region, category, SUM(amount) AS category_amount
    FROM window_lab.sales
    GROUP BY region, category
),
with_share AS (
    SELECT
        region, category, category_amount,
        100.0 * category_amount
        / NULLIF(
            SUM(category_amount) OVER (PARTITION BY region),0
        ) AS pct_raw
    FROM category_totals
)
SELECT
    region,
    SUM(pct_raw) AS sum_pct_before_rounding
FROM with_share
GROUP BY region
ORDER BY region;
~~~

Với dữ liệu mẫu có mẫu số khác 0, mỗi vùng cho tổng gần hoặc đúng **100** theo phép toán numeric. Kiểm tra bằng tỷ lệ **chưa làm tròn**; không ép mỗi tỷ lệ từng danh mục thành integer trước khi cộng.

---

## 17. Tỷ lệ lũy kế đến mỗi thời điểm

Một biểu đồ Pareto hoặc tiến độ có thể cần **đến mỗi ngày, đã đạt bao nhiêu phần trăm tổng doanh thu của kỳ**.

### 17.1. Tử số lũy kế, mẫu số toàn vùng

~~~sql
WITH daily AS (
    SELECT region, sale_date, SUM(amount) AS daily_amount
    FROM window_lab.sales
    GROUP BY region, sale_date
),
metrics AS (
    SELECT
        region, sale_date, daily_amount,
        SUM(daily_amount) OVER (
            PARTITION BY region
            ORDER BY sale_date
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS running_amount,
        SUM(daily_amount) OVER (
            PARTITION BY region
        ) AS region_total
    FROM daily
)
SELECT
    region, sale_date, daily_amount,
    running_amount, region_total,
    ROUND(
        100.0 * running_amount / NULLIF(region_total, 0),
        2
    ) AS cumulative_pct_of_region
FROM metrics
ORDER BY region, sale_date;
~~~

North:

| Ngày | Lũy kế | Tỷ lệ trên tổng North |
|---|---:|---:|
| 01/01 | 150 | 25.00% |
| 02/01 | 350 | 58.33% |
| 04/01 | 350 | 58.33% |
| 05/01 | 480 | 80.00% |
| 07/01 | 600 | 100.00% |

### 17.2. Vì sao không lấy running_amount chia cho chính running_amount?

Nếu mẫu số cũng là `SUM(...) OVER (ORDER BY ...)` với cùng running frame, phần trăm thường thành **100% tại mọi dòng** (khi tổng khác 0), không thể hiện tiến độ của cả kỳ.

Muốn "đã đạt bao nhiêu phần trăm tổng kỳ", mẫu số phải là **tổng cả kỳ**. Vì vậy trong CTE `metrics` ta dùng:

~~~text
running_amount: ORDER BY + ROWS UNBOUNDED PRECEDING
region_total:   chỉ PARTITION BY, không ORDER BY
~~~

### 17.3. Khi doanh thu âm, tỷ lệ lũy kế có thể giảm

Nếu có hoàn tiền lớn, tổng lũy kế có thể giảm. Nếu tổng cuối kỳ rất nhỏ hoặc âm, tỷ lệ "tiến độ" có thể khó hiểu, vượt 100% hoặc mang dấu âm. Không nên ép `GREATEST(..., 0)` hoặc cap 100% trừ khi đó là **quy tắc báo cáo đã xác định**.

---

## 18. FILTER: phần trăm theo điều kiện mà vẫn giữ hàng

PostgreSQL hỗ trợ `FILTER (WHERE ...)` cho một số aggregate, kể cả khi dùng chúng dưới dạng window aggregate.

Ví dụ: tổng doanh thu Books trong mỗi khu vực được lặp lại trên **mọi giao dịch** của vùng:

~~~sql
SELECT
    sale_id, region, category, amount,
    SUM(amount) FILTER (
        WHERE category = 'Books'
    ) OVER (
        PARTITION BY region
    ) AS books_amount_in_region,
    SUM(amount) OVER (
        PARTITION BY region
    ) AS region_amount
FROM window_lab.sales
ORDER BY region, sale_id;
~~~

Đối với mọi dòng North, `books_amount_in_region=430`. Đối với mọi dòng South, giá trị là `340`.

### 18.1. Tỷ trọng Books trên tổng vùng

~~~sql
WITH totals AS (
    SELECT
        region, sale_id,
        SUM(amount) FILTER (
            WHERE category = 'Books'
        ) OVER (PARTITION BY region) AS books_amount,
        SUM(amount) OVER (PARTITION BY region) AS region_amount
    FROM window_lab.sales
)
SELECT
    region, sale_id, books_amount, region_amount,
    ROUND(
        100.0 * books_amount / NULLIF(region_amount, 0),
        2
    ) AS books_share
FROM totals
ORDER BY region, sale_id;
~~~

Nếu chỉ cần **một dòng cho mỗi vùng**, có thể `SELECT DISTINCT region, ...` ở tầng ngoài hoặc dùng GROUP BY như phần 16. Đừng tin window sẽ tự thu gọn số hàng của bảng.

### 18.2. FILTER và WHERE khác nhau

- `WHERE category = 'Books'` **loại những hàng khác** khỏi toàn bộ input trước khi chạy window.
- `SUM(amount) FILTER (WHERE category='Books') OVER (PARTITION BY region)` giữ mọi hàng trong partition nhưng chỉ cộng những amount thỏa điều kiện vào **aggregate này**.

Nếu cùng lúc cần tổng vùng và tổng Books **trên các hàng gốc**, dùng FILTER ở aggregate là cách rõ ràng.

---

## 19. Tỷ lệ tăng trưởng theo ngày bằng LAG

Lũy kế, trung bình trượt và phần trăm theo nhóm thường được trình bày cùng **thay đổi so với kỳ trước**.

### 19.1. LAG lấy giá trị ở hàng trước trong partition

~~~sql
WITH daily AS (
    SELECT region, sale_date, SUM(amount) AS daily_amount
    FROM window_lab.sales
    GROUP BY region, sale_date
)
SELECT
    region, sale_date, daily_amount,
    LAG(daily_amount) OVER (
        PARTITION BY region
        ORDER BY sale_date
    ) AS previous_observed_amount
FROM daily
ORDER BY region, sale_date;
~~~

`LAG` lấy **ngày có dữ liệu trước đó**, không nhất thiết hôm qua. North ngày 04/01 lấy ngày 02/01 là previous observed, vì không có hàng 03/01.

### 19.2. Phần trăm tăng trưởng

~~~sql
WITH daily AS (
    SELECT region, sale_date, SUM(amount) AS daily_amount
    FROM window_lab.sales
    GROUP BY region, sale_date
),
with_previous AS (
    SELECT
        region, sale_date, daily_amount,
        LAG(daily_amount) OVER (
            PARTITION BY region
            ORDER BY sale_date
        ) AS previous_amount
    FROM daily
)
SELECT
    region, sale_date, daily_amount, previous_amount,
    ROUND(
        100.0 * (daily_amount - previous_amount)
        / NULLIF(previous_amount, 0),
        2
    ) AS pct_change_vs_previous_observation
FROM with_previous
ORDER BY region, sale_date;
~~~

Khi hàng đầu `previous_amount IS NULL`, phần trăm thay đổi là NULL. Khi kỳ trước bằng 0, `NULLIF` tránh chia cho 0; tỷ lệ tăng từ 0 sang số dương **không có phần trăm tăng trưởng hữu hạn theo công thức chuẩn**.

### 19.3. "Hôm qua" khác "hàng trước"

Nếu muốn tăng trưởng **hôm nay so với hôm qua**, phải dựng `dense_daily` với đủ lịch như phần 12 trước khi dùng LAG. Không được mô tả chỉ số LAG trên những ngày có doanh thu là "so với ngày hôm qua" khi có ngày trống.

---

## 20. Một truy vấn kết hợp lũy kế, trung bình và phần trăm

Mẫu báo cáo tổng hợp:

~~~sql
WITH daily AS (
    SELECT
        region,
        sale_date,
        SUM(amount) AS daily_amount
    FROM window_lab.sales
    GROUP BY region, sale_date
),
metrics AS (
    SELECT
        region,
        sale_date,
        daily_amount,
        SUM(daily_amount) OVER running_window AS cumulative_amount,
        AVG(daily_amount) OVER moving_window AS moving_avg_3,
        SUM(daily_amount) OVER (
            PARTITION BY region
        ) AS region_total
    FROM daily
    WINDOW
        running_window AS (
            PARTITION BY region
            ORDER BY sale_date
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ),
        moving_window AS (
            PARTITION BY region
            ORDER BY sale_date
            ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
        )
)
SELECT
    region,
    sale_date,
    daily_amount,
    cumulative_amount,
    ROUND(moving_avg_3, 2) AS moving_avg_3_observed,
    ROUND(
        100.0 * daily_amount / NULLIF(region_total, 0), 2
    ) AS daily_pct_of_region,
    ROUND(
        100.0 * cumulative_amount / NULLIF(region_total, 0), 2
    ) AS cumulative_pct_of_region
FROM metrics
ORDER BY region, sale_date;
~~~

Hai mẫu `WINDOW` khác frame nhưng cùng partition/sort. Vì các metric tính từ `daily`, kết quả có **một hàng mỗi khu vực–ngày có dữ liệu**.

Khi xuất API, đặt tên cột phản ánh chính xác:

- `moving_avg_3_observed`: trung bình ba **ngày có dữ liệu** gần nhất.
- `daily_pct_of_region`: đóng góp ngày đó trong **tổng khu vực của toàn tập đầu vào**.
- `cumulative_pct_of_region`: tích lũy đến hết ngày so với tổng vùng.

Nếu đầu vào bị giới hạn theo thời gian (ví dụ chỉ tháng 01), "toàn tập" ở đây là **toàn khoảng đang xét**, không phải doanh thu từ khi công ty thành lập.

---

## 21. Thứ tự xử lý logic và vị trí được phép dùng window

Trong PostgreSQL, window functions được tính sau các bước xác định các hàng kết quả từ `FROM`, `WHERE`, `GROUP BY` và `HAVING`; chúng có thể dùng ở danh sách `SELECT` và `ORDER BY` của cấp truy vấn thích hợp.

### 21.1. Không gọi window trực tiếp trong WHERE cùng cấp

Câu này không hợp lệ:

~~~sql
-- Không hợp lệ: window function không dùng trực tiếp trong WHERE.
SELECT region, sale_id, amount
FROM window_lab.sales
WHERE SUM(amount) OVER (PARTITION BY region) > 500;
~~~

Cách đúng là tính trong CTE/subquery, sau đó lọc:

~~~sql
WITH with_total AS (
    SELECT
        region, sale_id, amount,
        SUM(amount) OVER (PARTITION BY region) AS region_total
    FROM window_lab.sales
)
SELECT region, sale_id, amount, region_total
FROM with_total
WHERE region_total > 500
ORDER BY region, sale_id;
~~~

### 21.2. WHERE trước window có thể thay đổi lũy kế

Ví dụ muốn **hiển thị** các dòng từ ngày 05/01 nhưng lũy kế phải tính từ **đầu dữ liệu**:

~~~sql
WITH calculated AS (
    SELECT
        region, sale_date, sale_id, amount,
        SUM(amount) OVER (
            PARTITION BY region
            ORDER BY sale_date, sale_id
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS cumulative_since_start
    FROM window_lab.sales
)
SELECT *
FROM calculated
WHERE region = 'North'
  AND sale_date >= DATE '2026-01-05'
ORDER BY sale_date, sale_id;
~~~

Ở dòng `1005`, `cumulative_since_start=500`. Nhưng nếu đặt bộ lọc `sale_date >= '2026-01-05'` **ngay trong SELECT chạy window**, các dòng trước đó không còn thuộc input nên lũy kế của `1005` bắt đầu từ `150`.

**Quy tắc:** "lọc dữ liệu trước khi tính" khác "tính trên toàn dữ liệu rồi chỉ hiển thị một phần".

### 21.3. Không lồng trực tiếp window trong window khác

Không dùng dạng:

~~~sql
-- Không hợp lệ: window function nằm trực tiếp bên trong window khác.
SUM(SUM(amount) OVER (PARTITION BY region)) OVER ()
~~~

Nếu muốn tiếp tục tính trên kết quả window, dùng **CTE/subquery** chia giai đoạn.

### 21.4. Có thể dùng aggregate thường rồi window trên kết quả đã GROUP BY

Một mẫu PostgreSQL hợp lệ, nhưng nên sử dụng sau khi hiểu mức chi tiết:

~~~sql
SELECT
    region,
    sale_date,
    SUM(amount) AS daily_amount,
    SUM(SUM(amount)) OVER (
        PARTITION BY region
        ORDER BY sale_date
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS cumulative_daily_amount
FROM window_lab.sales
GROUP BY region, sale_date
ORDER BY region, sale_date;
~~~

`SUM(amount)` bên trong là **aggregate thường theo mỗi ngày**; `SUM(...) OVER` ở ngoài là **window aggregate trên các hàng nhóm**. Nó không phải lồng hai window functions.

CTE `daily` thường dễ đọc, giải thích và mở rộng hơn khi có nhiều metric.

---

## 22. DISTINCT, NULL, kiểu số và mẫu số bằng 0

### 22.1. DISTINCT trong aggregate window

Một nhu cầu như `COUNT(DISTINCT customer_id) OVER (PARTITION BY region)` không thể coi là tương đương `COUNT(customer_id) OVER ...`: cần đếm **khách duy nhất**, không phải số đơn.

PostgreSQL không hỗ trợ `DISTINCT` trực tiếp trong aggregate window theo cú pháp thông thường ở các phiên bản đang được dùng rộng rãi; nếu gặp lỗi, có thể:

1. Deduplicate trong CTE theo `region, customer_id` rồi `COUNT(*) OVER (PARTITION BY region)`.
2. Dùng GROUP BY riêng để tính distinct count rồi JOIN trở lại dữ liệu gốc.
3. Chọn thiết kế thống kê chuyên dụng khi cần rolling distinct trên dữ liệu rất lớn.

Không thay `COUNT(DISTINCT customer_id)` bằng `COUNT(*)` mà vẫn gọi là "số khách duy nhất".

### 22.2. Phép chia số nguyên

Trong PostgreSQL, chia hai số nguyên có thể bị cắt phần thập phân:

~~~sql
SELECT 1 / 2 AS integer_division,
       1.0 / 2 AS numeric_division;
~~~

Kết quả đầu là `0`, còn kết quả sau là `0.5`. Khi tính phần trăm, ưu tiên `100.0 * numerator / denominator` hoặc cast sang `numeric` phù hợp.

### 22.3. Chia cho 0

~~~sql
SELECT 100.0 * amount / NULLIF(region_total, 0)
FROM (... ) AS t;
~~~

Trong truy vấn mẫu, bảng `t` là placeholder cho một subquery/CTE có cột `amount` và `region_total`. `NULLIF(denominator,0)` trả NULL khi denominator bằng 0; phép chia khi ấy ra NULL thay vì lỗi.

Không tự chuyển tỷ lệ undefined thành 0 bằng `COALESCE(...,0)` nếu doanh nghiệp chưa định nghĩa "0%" là đúng. **Tỷ lệ không xác định** và **tỷ lệ bằng 0** là hai trạng thái khác nhau.

### 22.4. Tổng âm và phần trăm trên doanh thu ròng

Nếu tổng vùng âm hoặc gần 0, tỷ lệ từng giao dịch có thể âm hoặc lớn hơn 100%; đó là hệ quả của công thức net revenue. Báo cáo có thể cần tách `gross_sales`, `refunds` và `net_revenue` để có mẫu số đáng hiểu hơn.

### 22.5. AVG bỏ qua NULL

`AVG(x)` bỏ qua x NULL; nếu **tất cả** giá trị trong frame đều NULL, kết quả AVG là NULL. `SUM(x)` trên tập không có giá trị không NULL cũng trả NULL, không tự trả 0. Sử dụng `COALESCE` chỉ khi nghiệp vụ coi thiếu dữ liệu là 0.

### 22.6. Làm tròn sau khi tính

Nếu mỗi tỷ lệ được làm tròn đến 2 chữ số thập phân, tổng các tỷ lệ hiển thị có thể là 99.99% hoặc 100.01% thay vì đúng 100.00%. Khi cần tỷ lệ được chia chính xác đến từng xu/đơn vị báo cáo, phải có **quy tắc phân bổ phần dư làm tròn** thay vì tự sửa số liệu trong SQL.

---

## 23. Percent-of-total không phải percentile hoặc percent_rank

Tên gọi đều có từ "percent" nhưng mô tả những phép đo khác nhau.

| Chỉ số | Câu hỏi | Công thức hoặc SQL |
|---|---|---|
| Phần trăm đóng góp | Một giao dịch chiếm bao nhiêu % tổng vùng? | `100 * amount / SUM(amount) OVER (PARTITION BY region)` |
| Phần trăm lũy kế | Đến ngày này đạt bao nhiêu % tổng vùng? | `100 * running_total / region_total` |
| Percent rank | Hàng này ở vị trí tỷ lệ nào trong thứ hạng? | `PERCENT_RANK() OVER (PARTITION BY region ORDER BY amount)` |
| Cumulative distribution | Bao nhiêu phần trăm **hàng** có sort key ≤ giá trị này? | `CUME_DIST() OVER (...)` |
| Percentile | Ngưỡng giá trị tại một phân vị (ví dụ p90)? | Ordered-set aggregate như `PERCENTILE_CONT`, theo ngữ cảnh |

Ví dụ:

~~~sql
SELECT
    region, sale_id, amount,
    PERCENT_RANK() OVER (
        PARTITION BY region
        ORDER BY amount
    ) AS percent_rank_in_region,
    CUME_DIST() OVER (
        PARTITION BY region
        ORDER BY amount
    ) AS cumulative_distribution
FROM window_lab.sales
ORDER BY region, amount, sale_id;
~~~

`PERCENT_RANK` và `CUME_DIST` được tính dựa vào **thứ hạng và số hàng**, không phải tỷ trọng doanh thu. Không dùng chúng để tính 600/1150 hay 100/600.

### 23.1. RANK với peers

Hai giao dịch có amount bằng nhau có thể là peers trong thứ hạng:

~~~sql
RANK() OVER (PARTITION BY region ORDER BY amount DESC)
~~~

Nhưng khi muốn sắp đầu ra ổn định, có thể thêm `sale_id` vào **ORDER BY ngoài**; nếu thêm `sale_id` vào chính window ranking, bạn có thể làm các peers không còn bằng nhau và thay đổi rank.

---

## 24. Hiệu năng của window functions trong PostgreSQL

### 24.1. Vì sao window có thể tốn tài nguyên?

Với dữ liệu lớn, PostgreSQL có thể phải:

- Đọc nhiều hàng và chuẩn bị các partition.
- Sắp theo `PARTITION BY` và `ORDER BY`.
- Duy trì trạng thái frame, đặc biệt với nhiều cửa sổ hoặc frame khó xử lý.
- Lưu các hàng trung gian cần thiết cho WindowAgg.
- Tính lại/đệm dữ liệu nếu kế hoạch và hàm yêu cầu.

Sử dụng `EXPLAIN` để quan sát các node như `WindowAgg`, `Sort`, `Incremental Sort`, `Seq Scan` hoặc `Index Scan`. Không mặc định mọi window luôn có Sort riêng, vì một đường đọc theo index có thể cung cấp thứ tự cần thiết.

### 24.2. Index phục vụ partition và sort

Nếu nhiều query có mẫu:

~~~sql
PARTITION BY region
ORDER BY sale_date, sale_id
~~~

trên bảng giao dịch lớn, một index ứng viên:

~~~sql
CREATE INDEX ix_sales_region_date_id
ON window_lab.sales (region, sale_date, sale_id);
~~~

Index này có thể giúp đường đọc phù hợp thứ tự vùng–ngày–ID, nhưng **không bảo đảm planner sẽ sử dụng**. Cần đánh giá:

- `WHERE` lọc theo vùng/ngày nào?
- Số dòng trong một vùng và số vùng?
- Index có bao phủ dữ liệu cần đọc không?
- Query có GROUP BY ngày trước khi chạy window không?
- Lợi ích đọc có bù được chi phí ghi và dung lượng index không?

Với 14 dòng lab, `Seq Scan + Sort` hoàn toàn có thể rẻ hơn đi qua index.

### 24.3. EXPLAIN và EXPLAIN ANALYZE

~~~sql
EXPLAIN
SELECT
    region, sale_date, sale_id, amount,
    SUM(amount) OVER (
        PARTITION BY region
        ORDER BY sale_date, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_amount
FROM window_lab.sales;
~~~

Trên lab, có thể đo:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    region, sale_date, sale_id, amount,
    AVG(amount) OVER (
        PARTITION BY region
        ORDER BY sale_date, sale_id
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS moving_avg
FROM window_lab.sales;
~~~

`EXPLAIN ANALYZE` **thực thi SQL** để đo thời gian và số hàng thực. Không chạy tùy ý trên production khi bảng lớn hoặc có tải nhạy cảm.

### 24.4. Giảm dữ liệu đúng mức

Nếu chỉ cần báo cáo theo ngày, thường nên gom dữ liệu:

~~~text
Hàng triệu dòng giao dịch
        |
        v
GROUP BY region, sale_date
        |
        v
Vài nghìn dòng ngày-vùng
        |
        v
Window SUM/AVG trên ngày-vùng
~~~

Cách này có thể giảm đáng kể số hàng WindowAgg cần xử lý, nhưng chỉ đúng nếu định nghĩa báo cáo là **ngày-vùng**, không phải **từng giao dịch**.

### 24.5. Tránh CTE không cần thiết và nhiều lần sort

Sử dụng các window có cùng `PARTITION BY`/`ORDER BY` và khác frame một cách có tổ chức, ví dụ `WINDOW w AS (...)`. Planner có thể tái sử dụng/sắp xếp hợp lý tùy kế hoạch; không tự kết luận một query có ba window sẽ luôn sort ba lần.

Đọc kế hoạch thực tế, tránh vừa `ORDER BY` ngoài theo khóa khác vừa dùng nhiều loại window order không cần thiết nếu dashboard không cần.

### 24.6. work_mem và các partition lớn

Sort/WindowAgg có thể dùng bộ nhớ và file tạm. Không tăng `work_mem` toàn server như một "mẹo" khi chưa đo, vì mỗi truy vấn có thể có nhiều thao tác cần bộ nhớ, và nhiều query chạy đồng thời. Ưu tiên:

1. Chọn đúng frame và đúng mức tiền tổng hợp.
2. Lọc theo phạm vi thời gian cần thiết, đồng thời giữ dữ liệu lịch sử đủ cho frame.
3. Kiểm tra index và thống kê.
4. Đọc `EXPLAIN (ANALYZE, BUFFERS)` trên môi trường đại diện.
5. Cân nhắc materialized view hoặc bảng tổng hợp ngày được cập nhật có kiểm soát khi dashboard chạy thường xuyên.

### 24.7. Window không tự biến dữ liệu thành kết quả bất biến

Các báo cáo chạy ở hai transaction/snapshot khác nhau có thể có dữ liệu nguồn khác nhau vì INSERT, UPDATE hoặc refund mới. Nếu đối soát nhiều báo cáo, chốt mốc dữ liệu, filter và isolation/snapshot phù hợp; đừng diễn giải chênh lệch như lỗi WINDOW nếu thực chất tập nguồn đã đổi.

---

## 25. Những lỗi thực hành thường gặp

| Sai lầm | Biểu hiện | Cách sửa |
|---|---|---|
| Quên `PARTITION BY region` | Tổng chạy xuyên cả North và South | Partition đúng nhóm |
| Không có `ORDER BY` cho lũy kế | Mọi dòng mang cùng tổng vùng | Thêm thứ tự và frame chạy |
| `ORDER BY sale_date` thiếu tie-breaker khi tính từng đơn | Peers và kết quả phụ thuộc frame | Dùng `sale_date, sale_id` với ROWS |
| Dựa vào frame mặc định | Tổng "nhảy" ở hàng đầu cùng ngày | Ghi frame tường minh |
| Nhầm ROWS 2 PRECEDING với hai ngày trước | Chỉ đếm hai hàng, không phải ngày | Dùng RANGE theo thời gian hoặc dựng lịch |
| Nhầm RANGE ba ngày với ba ngày có dữ liệu | Frame có thể thiếu ngày trống | Xác định rõ tiêu chí trung bình |
| Gọi AVG trên giao dịch là AVG theo ngày | Ngày nhiều đơn có trọng số lớn hơn | GROUP BY ngày trước |
| Lấp ngày trống bằng 0 khi thiếu dữ liệu thật | Bình quân bị kéo xuống sai | Chỉ COALESCE khi 0 là nghĩa đúng |
| Chia 100 * amount cho running sum | Ra tỷ lệ theo lũy kế, không phải tổng vùng | Mẫu số toàn partition |
| Dùng mẫu số toàn hệ thống cho tỷ lệ trong vùng | % không đúng mô tả | `SUM(...) OVER (PARTITION BY region)` |
| Chia khi tổng vùng bằng 0 | Lỗi divide-by-zero | `NULLIF(total,0)` |
| Chia số nguyên | Mất phần thập phân | `100.0 * numerator / denominator` |
| Làm tròn từng thành phần rồi cộng | Tổng hiển thị lệch 100% | Làm tròn ở bước hiển thị |
| Nhầm refund âm với lỗi | % âm hoặc lũy kế giảm | Xác định net/gross/refund |
| Đặt WHERE trước window nhưng muốn tổng từ đầu | Thiếu lịch sử ở frame | Tính trong CTE rồi lọc ngoài |
| Dùng window trực tiếp trong WHERE | SQL không hợp lệ | CTE/subquery |
| Lồng hai window trực tiếp | SQL không hợp lệ | Tách giai đoạn |
| LAG "ngày trước" nhưng ngày không liên tục | Trả ngày có dữ liệu trước đó | Dựng dense calendar |
| Dùng PERCENT_RANK để đo % doanh thu | Tỷ lệ thứ hạng thay vì đóng góp | Dùng amount / SUM(amount) |
| Coi ORDER BY trong OVER là thứ tự output | Danh sách hiển thị có thể khác | ORDER BY ngoài |
| Thêm index không đo workload | Tăng dung lượng/chi phí ghi | EXPLAIN và đánh giá bảng lớn |

---

## 26. Quy trình thiết kế báo cáo window

~~~mermaid
flowchart TD
    A["Mô tả chỉ số nghiệp vụ"] --> B["Chốt mức chi tiết: giao dịch hay ngày"]
    B --> C["Chọn partition: vùng, danh mục, khách"]
    C --> D{"Chỉ số có phụ thuộc thứ tự thời gian?"}
    D -- "Không: phần trăm trên tổng nhóm" --> E["Tổng nhóm với OVER PARTITION BY"]
    D -- "Có: lũy kế/trượt" --> F["ORDER BY và tie-breaker"]
    F --> G{"Khoảng trượt nghĩa là gì?"}
    G -- "N hàng" --> H["ROWS"]
    G -- "Khoảng thời gian" --> I["RANGE"]
    G -- "Ngày lịch đủ cả ngày trống" --> J["Calendar + ROWS"]
    E --> K["Xử lý NULL, 0, hoàn tiền"]
    H --> K
    I --> K
    J --> K
    K --> L["Kiểm tra mẫu số và làm tròn"]
    L --> M["EXPLAIN, index và snapshot"]
~~~

Trước khi đưa báo cáo vào production, cần trả lời:

1. `amount` là doanh thu gộp, doanh thu ròng hay số đơn?
2. Mỗi hàng biểu diễn đơn hàng, sản phẩm hay một ngày đã tổng hợp?
3. Mẫu số phần trăm là **khu vực**, **danh mục**, **công ty** hay **kỳ báo cáo**?
4. Khóa thời gian có giá trị trùng không? Có ID phá hòa không?
5. Ba ngày trượt là ba **hàng**, ba **ngày có dữ liệu**, hay ba **ngày lịch**?
6. Ngày không có dữ liệu được hiểu là 0 hay thiếu đo lường?
7. Dòng refund âm có được đưa vào tử số/mẫu số không?
8. Khi mẫu số bằng 0, trả NULL, báo lỗi hay trạng thái "không xác định"?
9. Có cần đủ N quan sát mới tính AVG không?
10. Báo cáo có dùng snapshot/mốc thời gian cố định và đủ hiệu năng không?

---

## 27. Bài tập thực hành

Các bài sử dụng `window_lab.sales` và dữ liệu trong phần 2, trừ khi đề nêu ví dụ giả định khác.

### Bài 1 — Tổng theo vùng nhưng giữ mọi dòng

Viết SQL trả `sale_id,region,amount,region_total`; mỗi giao dịch North phải có tổng 600, mỗi giao dịch South tổng 550.

### Bài 2 — Tổng toàn công ty

Viết SQL lặp tổng 1.150 trên từng giao dịch mà không dùng GROUP BY.

### Bài 3 — Lũy kế từng giao dịch

Viết query tính tổng từ đầu đến mỗi sale theo vùng, thứ tự `sale_date, sale_id`. Với sale_id 1005 và 1006, tổng phải bằng bao nhiêu?

### Bài 4 — Peer theo ngày

Vì sao `SUM(amount) OVER (PARTITION BY region ORDER BY sale_date)` trả cùng tổng 150 cho cả hai đơn North ngày 01/01? Cách để nhận 100 rồi 150?

### Bài 5 — Gom ngày rồi lũy kế

Viết CTE `daily` tính tổng mỗi ngày mỗi vùng, sau đó lũy kế theo ngày. Đối với North, ngày 05/01 lũy kế bao nhiêu?

### Bài 6 — Reset lũy kế theo danh mục

Viết window để mỗi chuỗi lũy kế tách riêng theo `region,category`.

### Bài 7 — Trung bình ba ngày quan sát

Với North, dùng `AVG(daily_amount) OVER (ROWS BETWEEN 2 PRECEDING AND CURRENT ROW)` sau khi GROUP BY ngày. Ngày 05/01 và 07/01 lần lượt có AVG bao nhiêu?

### Bài 8 — Trung bình ba ngày lịch nhưng chỉ đếm ngày có hàng

Dùng `RANGE BETWEEN INTERVAL '2 days' PRECEDING AND CURRENT ROW` trên `daily`. Tính AVG của North ngày 05/01 và giải thích vì sao khác bài 7.

### Bài 9 — Ba ngày lịch tính ngày trống là 0

Dùng `generate_series` lấp đủ ngày 01–07/01; LEFT JOIN `daily` rồi `COALESCE` về 0. AVG North ngày 05/01 bằng bao nhiêu?

### Bài 10 — Chỉ tính khi đủ ba quan sát

Viết truy vấn chỉ hiển thị moving average nếu frame có đúng ba hàng; hai hàng đầu phải trả NULL.

### Bài 11 — Phần trăm từng giao dịch trong khu vực

Tính `pct_of_region` bằng window. Giá trị cho sale_id 1001, 1006 lần lượt bao nhiêu?

### Bài 12 — Chia cho 0

Giải thích cách dùng `NULLIF` nếu một vùng có tổng amount bằng 0. Vì sao không tự đổi kết quả thành 0%?

### Bài 13 — Phần trăm vùng trên công ty

Gom một dòng mỗi vùng rồi tính % trên tổng 1.150. North và South là bao nhiêu?

### Bài 14 — Phần trăm category trong region

Viết query trả mỗi cặp `(region,category)` cùng tổng category và phần trăm trong vùng. North/Books chiếm bao nhiêu?

### Bài 15 — Tỷ lệ lũy kế

Viết query tính `cumulative_pct` theo ngày đã gom, mẫu số là toàn bộ region. Với North ngày 05/01, tỷ lệ là bao nhiêu?

### Bài 16 — FILTER Books

Tính tổng Books của mỗi region bằng `SUM(amount) FILTER (WHERE category='Books') OVER (PARTITION BY region)`. North và South có tổng bao nhiêu?

### Bài 17 — LAG ngày trước

Viết query trả doanh thu ngày và doanh thu **ngày có dữ liệu trước đó**. Với North ngày 04/01, LAG lấy ngày nào?

### Bài 18 — Ngày hôm qua thực sự

Nếu yêu cầu so sánh ngày 04/01 với **03/01** (ngày không có doanh thu), tại sao LAG trên `daily` chưa đủ? Làm thế nào?

### Bài 19 — WHERE trước và sau window

Muốn hiển thị North từ 05/01 nhưng vẫn lũy kế cả các ngày 01–04/01. Đặt bộ lọc ngày ở đâu? Tổng ở dòng 1005?

### Bài 20 — Nhận diện window frame

Giải thích khác nhau giữa `ROWS 2 PRECEDING`, `GROUPS 2 PRECEDING` và `RANGE INTERVAL '2 days' PRECEDING` khi `ORDER BY sale_date` có peers.

### Bài 21 — PERCENT_RANK không phải share

Viết câu dùng `PERCENT_RANK` theo amount mỗi vùng. Vì sao kết quả không phải tỷ lệ 100/600 của đơn 1001?

### Bài 22 — Tổng hợp và window cùng SELECT

Viết truy vấn sử dụng `SUM(SUM(amount)) OVER (...)` cùng `GROUP BY region,sale_date`. Giải thích vai trò của SUM trong và ngoài.

### Bài 23 — EXPLAIN và index

Một bảng có hàng triệu đơn, thường tính lũy kế theo region, sale_date, sale_id. Đề xuất một index ứng viên và nêu ba lý do planner có thể không dùng nó.

### Bài 24 — Business contract

Một dashboard gọi chỉ số "MA 7 ngày" nhưng bỏ ngày không phát sinh, tỷ lệ % âm khi hoàn tiền và mẫu số bằng 0. Hãy viết những câu hỏi cần hỏi product owner trước khi sửa query.

---

## 28. Gợi ý lời giải

### Bài 1

~~~sql
SELECT sale_id, region, amount,
       SUM(amount) OVER (PARTITION BY region) AS region_total
FROM window_lab.sales
ORDER BY region, sale_id;
~~~

North: **600**, South: **550** trên mỗi hàng tương ứng.

### Bài 2

~~~sql
SELECT sale_id, amount,
       SUM(amount) OVER () AS company_total
FROM window_lab.sales
ORDER BY sale_id;
~~~

`company_total` = **1150** trên mỗi giao dịch.

### Bài 3

~~~sql
SELECT region, sale_date, sale_id, amount,
       SUM(amount) OVER (
           PARTITION BY region
           ORDER BY sale_date, sale_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS running_amount
FROM window_lab.sales
ORDER BY region, sale_date, sale_id;
~~~

`1005`: **500**, `1006`: **480**, do dòng 1006 là hoàn tiền `-20`.

### Bài 4

Window có `ORDER BY sale_date` dùng frame mặc định dạng `RANGE` và bao gồm peers cùng ngày, nên cả hai đơn ngày 01/01 thấy tổng **150**. Muốn tổng **100**, rồi **150**, dùng `ORDER BY sale_date,sale_id ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`.

### Bài 5

~~~sql
WITH daily AS (
    SELECT region, sale_date, SUM(amount) AS daily_amount
    FROM window_lab.sales
    GROUP BY region, sale_date
)
SELECT region, sale_date, daily_amount,
       SUM(daily_amount) OVER (
           PARTITION BY region
           ORDER BY sale_date
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS cumulative
FROM daily
ORDER BY region, sale_date;
~~~

North ngày 05/01: **480**.

### Bài 6

~~~sql
SELECT
    region, category, sale_date, sale_id, amount,
    SUM(amount) OVER (
        PARTITION BY region, category
        ORDER BY sale_date, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS cumulative_category
FROM window_lab.sales
ORDER BY region, category, sale_date, sale_id;
~~~

### Bài 7

~~~sql
WITH daily AS (
    SELECT region, sale_date, SUM(amount) AS daily_amount
    FROM window_lab.sales
    GROUP BY region, sale_date
)
SELECT region, sale_date,
       AVG(daily_amount) OVER (
           PARTITION BY region
           ORDER BY sale_date
           ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
       ) AS moving_avg
FROM daily
ORDER BY region, sale_date;
~~~

North 05/01: **110**; 07/01: **83,3333...** (ba ngày có dữ liệu gần nhất).

### Bài 8

~~~sql
WITH daily AS (
    SELECT region, sale_date, SUM(amount) AS daily_amount
    FROM window_lab.sales
    GROUP BY region, sale_date
)
SELECT region, sale_date,
       AVG(daily_amount) OVER (
           PARTITION BY region
           ORDER BY sale_date::timestamp
           RANGE BETWEEN INTERVAL '2 days' PRECEDING
                     AND CURRENT ROW
       ) AS avg_in_3_day_range
FROM daily
ORDER BY region, sale_date;
~~~

Ngày 05/01 nằm trong khoảng 03–05/01, nhưng chỉ có hàng 04/01=0 và 05/01=130, nên AVG **65**.

### Bài 9

~~~sql
WITH regions AS (
    SELECT DISTINCT region FROM window_lab.sales
),
days AS (
    SELECT d::date AS sale_date
    FROM generate_series(
        TIMESTAMP '2026-01-01',
        TIMESTAMP '2026-01-07',
        INTERVAL '1 day'
    ) AS g(d)
),
daily AS (
    SELECT region, sale_date, SUM(amount) AS daily_amount
    FROM window_lab.sales
    GROUP BY region, sale_date
),
dense AS (
    SELECT r.region, d.sale_date,
           COALESCE(s.daily_amount, 0::numeric) AS daily_amount
    FROM regions r CROSS JOIN days d
    LEFT JOIN daily s
      ON s.region = r.region AND s.sale_date = d.sale_date
)
SELECT region, sale_date,
       AVG(daily_amount) OVER (
           PARTITION BY region
           ORDER BY sale_date
           ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
       ) AS avg_3_calendar_days
FROM dense
ORDER BY region, sale_date;
~~~

North ngày 05/01: `(0+0+130)/3 = **43,3333...**`.

### Bài 10

~~~sql
WITH daily AS (
    SELECT region, sale_date, SUM(amount) AS daily_amount
    FROM window_lab.sales
    GROUP BY region, sale_date
),
metrics AS (
    SELECT region, sale_date,
           AVG(daily_amount) OVER w AS avg_3,
           COUNT(*) OVER w AS n
    FROM daily
    WINDOW w AS (
        PARTITION BY region
        ORDER BY sale_date
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    )
)
SELECT region, sale_date,
       CASE WHEN n = 3 THEN avg_3 END AS avg_when_full
FROM metrics
ORDER BY region, sale_date;
~~~

### Bài 11

~~~sql
SELECT sale_id, region, amount,
       ROUND(
           100.0 * amount
           / NULLIF(SUM(amount) OVER (PARTITION BY region),0),
           2
       ) AS pct_of_region
FROM window_lab.sales
ORDER BY region, sale_id;
~~~

`1001`: **16,67%**, `1006`: **-3,33%**.

### Bài 12

`NULLIF(total,0)` biến mẫu số 0 thành NULL, làm kết quả tỷ lệ không xác định thay vì lỗi. `0%` nghĩa là đóng góp bằng 0 trên một mẫu số có nghĩa, còn `NULL` có thể nghĩa là tỷ lệ **không xác định** vì mẫu số bằng 0.

### Bài 13

~~~sql
WITH totals AS (
    SELECT region, SUM(amount) AS region_amount
    FROM window_lab.sales
    GROUP BY region
)
SELECT region, region_amount,
       ROUND(
           100.0 * region_amount
           / NULLIF(SUM(region_amount) OVER (),0),2
       ) AS pct_company
FROM totals
ORDER BY region;
~~~

North **52,17%**, South **47,83%**.

### Bài 14

~~~sql
WITH grouped AS (
    SELECT region, category, SUM(amount) AS category_amount
    FROM window_lab.sales
    GROUP BY region, category
)
SELECT region, category, category_amount,
       ROUND(
           100.0 * category_amount
           / NULLIF(
               SUM(category_amount) OVER (PARTITION BY region),0
           ),2
       ) AS pct_category_in_region
FROM grouped
ORDER BY region, category;
~~~

North/Books **430/600 = 71,67%**.

### Bài 15

~~~sql
WITH daily AS (
    SELECT region, sale_date, SUM(amount) AS daily_amount
    FROM window_lab.sales
    GROUP BY region, sale_date
),
metrics AS (
    SELECT region, sale_date, daily_amount,
           SUM(daily_amount) OVER (
               PARTITION BY region
               ORDER BY sale_date
               ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
           ) AS cumulative,
           SUM(daily_amount) OVER (PARTITION BY region)
               AS region_total
    FROM daily
)
SELECT region, sale_date,
       ROUND(
           100.0 * cumulative / NULLIF(region_total,0), 2
       ) AS cumulative_pct
FROM metrics
ORDER BY region, sale_date;
~~~

North 05/01: `480/600=**80%**`.

### Bài 16

~~~sql
SELECT region, sale_id,
       SUM(amount) FILTER (
           WHERE category = 'Books'
       ) OVER (PARTITION BY region) AS books_amount
FROM window_lab.sales
ORDER BY region, sale_id;
~~~

North **430**, South **340**.

### Bài 17

~~~sql
WITH daily AS (
    SELECT region, sale_date, SUM(amount) AS daily_amount
    FROM window_lab.sales
    GROUP BY region, sale_date
)
SELECT region, sale_date, daily_amount,
       LAG(daily_amount) OVER (
           PARTITION BY region
           ORDER BY sale_date
       ) AS previous_observed_day
FROM daily
ORDER BY region, sale_date;
~~~

North 04/01 lấy **02/01** vì 03/01 không có dòng trong `daily`.

### Bài 18

Để tính "hôm qua" thật sự, dựng đủ các ngày với `generate_series`, nối bằng `LEFT JOIN` và đưa doanh thu ngày không giao dịch về 0 nếu nghiệp vụ quy định. Sau đó mới dùng `LAG` theo ngày liên tục.

### Bài 19

Đặt lọc ngày **ở ngoài CTE đã tính window**, nếu muốn giữ lũy kế từ đầu dữ liệu. Tại dòng `1005` kết quả phải là **500**, không phải 150.

### Bài 20

- `ROWS`: hai **hàng** trước.
- `GROUPS`: hai nhóm **peers** trước, với ORDER BY sale_date là hai ngày có dữ liệu trước.
- `RANGE INTERVAL '2 days'`: những hàng nằm trong khoảng giá trị **hai ngày lịch trước đến hiện tại**, không tự lấp ngày trống.

### Bài 21

~~~sql
SELECT region, sale_id, amount,
       PERCENT_RANK() OVER (
           PARTITION BY region
           ORDER BY amount
       ) AS pct_rank
FROM window_lab.sales
ORDER BY region, amount, sale_id;
~~~

`PERCENT_RANK` là tỷ lệ **vị trí thứ hạng**, không phải tỷ lệ doanh thu `100/600`.

### Bài 22

~~~sql
SELECT region, sale_date,
       SUM(amount) AS daily_amount,
       SUM(SUM(amount)) OVER (
           PARTITION BY region
           ORDER BY sale_date
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS cumulative
FROM window_lab.sales
GROUP BY region, sale_date
ORDER BY region, sale_date;
~~~

`SUM(amount)` tạo tổng của ngày theo `GROUP BY`, còn `SUM(SUM(amount)) OVER` cộng những tổng ngày theo cửa sổ.

### Bài 23

Index ứng viên:

~~~sql
CREATE INDEX ix_sales_region_date_id
ON window_lab.sales(region, sale_date, sale_id);
~~~

Planner vẫn có thể chọn scan khác vì bảng nhỏ, lọc vùng/ngày không phù hợp, chi phí heap access/index lớn, cần GROUP BY trước, thống kê khác hoặc đường đi song song hợp lý hơn. Cần đo `EXPLAIN` trên workload đại diện.

### Bài 24

Hỏi rõ: MA 7 ngày là **7 ngày lịch hay 7 ngày có dữ liệu**? Ngày không giao dịch là `0` hay thiếu dữ liệu? Cần đủ 7 ngày mới công bố không? Hoàn tiền âm có vào doanh thu ròng không? Mẫu số % là gross hay net; nếu tổng bằng 0 thì UI thể hiện trạng thái nào? Kỳ báo cáo bắt đầu/kết thúc khi nào, timezone nào, và snapshot dữ liệu nào được dùng?

---

## 29. Tổng kết

Hàm cửa sổ trong PostgreSQL cung cấp một cách nhất quán để tính **tổng lũy kế**, **trung bình trượt** và **phần trăm theo nhóm** mà vẫn giữ mức chi tiết cần báo cáo:

- `SUM(...) OVER (PARTITION BY ... ORDER BY ... ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)` tạo **tổng lũy kế theo hàng**.
- `AVG(...) OVER (... ROWS BETWEEN 2 PRECEDING AND CURRENT ROW)` tạo trung bình **tối đa ba hàng**, không tự nghĩa là ba ngày lịch.
- `RANGE` theo một offset thời gian dùng **giá trị khóa**; `GROUPS` đếm các nhóm peers; **lịch ngày đầy đủ** cần được dựng riêng khi ngày trống phải tính là 0.
- `100.0 * amount / NULLIF(SUM(amount) OVER (PARTITION BY region),0)` tính tỷ lệ **một dòng trong tổng vùng**.
- Muốn tỷ lệ **danh mục trong vùng**, tổng hợp theo `region,category` trước rồi dùng window tính mẫu số vùng.
- Muốn **tỷ lệ lũy kế**, dùng **running total ở tử số** và **total partition ở mẫu số**, không dùng nhầm hai running totals.
- Frame mặc định khi có `ORDER BY` có thể gom **mọi peers cùng giá trị khóa**; khi cần từng giao dịch phải có tie-breaker và `ROWS` tường minh.
- `WHERE` lọc **trước khi chạy window** ở cùng cấp; tính toàn bộ lịch sử rồi chỉ hiển thị một phần cần **CTE/subquery**.
- Xử lý đúng `NULL`, số 0, hoàn tiền âm, làm tròn và các kỳ không có dữ liệu trước khi coi phần trăm là chỉ số kinh doanh đáng tin.

Quy trình thiết kế hiệu quả: **chốt đơn vị tính → xác định partition → chọn thứ tự và frame → xử lý ngày thiếu/peers → định nghĩa tử số–mẫu số → kiểm tra trường hợp biên → đánh giá EXPLAIN trên dữ liệu đại diện**.
