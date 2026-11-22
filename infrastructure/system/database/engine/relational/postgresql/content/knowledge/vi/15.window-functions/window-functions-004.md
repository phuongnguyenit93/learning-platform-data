# LAG, LEAD và so sánh các hàng liền kề trong PostgreSQL

Khi phân tích dữ liệu theo thời gian hoặc theo một thứ tự nghiệp vụ, câu hỏi thường không chỉ là “hàng này có giá trị bao nhiêu?” mà còn là **“hàng trước đó có giá trị gì?”**, **“so với lần đo trước đã thay đổi thế nào?”**, hoặc **“sau sự kiện này là sự kiện nào?”**.

Ví dụ:

- Doanh thu hôm nay tăng hay giảm so với ngày ghi nhận trước?
- Giá sản phẩm ở lần cập nhật này khác giá trước đó bao nhiêu?
- Một thiết bị chuyển từ trạng thái `online` sang `offline` lúc nào?
- Khoảng cách thời gian giữa hai lần đăng nhập liên tiếp có vượt ngưỡng tạo phiên mới?
- Đơn hàng tiếp theo của cùng một khách diễn ra sau bao lâu?
- Tại sao khi bảng có hai sự kiện cùng timestamp, kết quả “sự kiện trước” lại thay đổi giữa các lần chạy?

Trong PostgreSQL, các hàm cửa sổ **`LAG()` và `LEAD()`** giúp lấy giá trị ở những hàng đứng trước hoặc sau **theo thứ tự trong từng nhóm** mà không phải tự nối bảng với chính nó để truy tìm từng cặp hàng.

Bài học thuộc chương **Hàm cửa sổ** của module **Database Engine Relational PostgreSQL**. Chúng ta sẽ đi từ cấu trúc `OVER (...)` đến những tình huống phân tích thực tế, ranh giới của kết quả, `NULL`, so sánh hàng liền kề, tính biến động, phát hiện khoảng trống thời gian, phiên hoạt động, index và cách đặt hàm cửa sổ đúng vị trí trong câu SQL.

## 1. Ý tưởng cốt lõi: hàng hiện tại, hàng trước và hàng sau

Giả sử có một dãy doanh thu được sắp theo ngày:

| Ngày | Doanh thu |
|---|---:|
| 2026-03-01 | 100 |
| 2026-03-02 | 130 |
| 2026-03-03 | 125 |
| 2026-03-04 | 160 |

Với hàng ngày 2026-03-03:

- **Hàng hiện tại:** doanh thu 125.
- **Hàng trước:** doanh thu 130 của ngày 2026-03-02.
- **Hàng sau:** doanh thu 160 của ngày 2026-03-04.

`LAG(revenue)` đọc doanh thu **một hàng trước**; `LEAD(revenue)` đọc doanh thu **một hàng sau**, theo thứ tự đã khai báo trong `OVER`.

Sơ đồ:

~~~text
ORDER BY sold_on ASC

  2026-03-01      2026-03-02      2026-03-03      2026-03-04
      100   --->      130   --->      125   --->      160
                       ^               ^               ^
                       |               |               |
                 LAG tại 03-03    hàng hiện tại    LEAD tại 03-03
~~~

Không có nghĩa “trước” luôn là ngày hôm qua hoặc “sau” luôn là ngày mai. **LAG/LEAD đi theo vị trí hàng trong thứ tự kết quả**, có thể cách nhau nhiều ngày nếu dữ liệu thiếu một ngày.

## 2. Cú pháp LAG và LEAD

Cú pháp thông dụng:

~~~sql
LAG(value_expression [, offset [, default_expression]])
OVER (
    [PARTITION BY partition_expression, ...]
    ORDER BY sort_expression [ASC | DESC], ...
)

LEAD(value_expression [, offset [, default_expression]])
OVER (
    [PARTITION BY partition_expression, ...]
    ORDER BY sort_expression [ASC | DESC], ...
)
~~~

Ý nghĩa:

| Thành phần | Vai trò |
|---|---|
| `value_expression` | Giá trị muốn đọc ở hàng trước/sau, ví dụ `revenue` |
| `offset` | Số hàng lùi/tiến; mặc định là 1 |
| `default_expression` | Giá trị dùng khi hàng tại vị trí offset không tồn tại; mặc định là `NULL` |
| `OVER (...)` | Định nghĩa ngữ cảnh cửa sổ cho hàm |
| `PARTITION BY` | Chia dữ liệu thành các nhóm tính toán độc lập |
| `ORDER BY` trong `OVER` | Xác định thứ tự và do đó xác định hàng trước/sau |

Những câu như:

~~~sql
LAG(revenue) OVER (ORDER BY sold_on)
LEAD(revenue) OVER (ORDER BY sold_on)
~~~

có nghĩa là lùi hoặc tiến một hàng theo ngày tăng dần.

### 2.1. LAG và LEAD đều trả giá trị cho từng hàng

Khác với phép tổng hợp không có cửa sổ:

~~~sql
SELECT SUM(revenue)
FROM sales_daily;
~~~

`LAG`/`LEAD` thông thường **không gom nhiều hàng thành một hàng**. Chúng trả thêm một giá trị phân tích cho **mỗi hàng đầu vào** còn lại sau các bước lọc/nhóm thích hợp.

Vì vậy rất tiện để so sánh những hàng đứng cạnh nhau, nhưng chúng không thay đổi số lượng hàng chỉ vì đọc giá trị lân cận.

## 3. Chuẩn bị bảng dữ liệu mẫu

Bài dùng hai cửa hàng có doanh thu theo ngày. Có ngày thiếu dữ liệu và có ngày doanh thu bằng nhau để phân biệt những tình huống khác nhau.

**Chỉ chạy trong PostgreSQL database thực hành.** Các lệnh tạo schema/bảng dưới đây không xóa bảng cũ; nếu tên đã tồn tại, dùng database lab mới hoặc tên phù hợp. Các giá trị tiền chỉ để minh họa SQL, không phải dữ liệu kinh doanh thật.

~~~sql
CREATE SCHEMA window_lab;

CREATE TABLE window_lab.daily_sales (
    store_id TEXT NOT NULL,
    sold_on DATE NOT NULL,
    revenue NUMERIC(12, 2) NOT NULL
        CHECK (revenue >= 0),
    order_count INTEGER NOT NULL
        CHECK (order_count >= 0),
    PRIMARY KEY (store_id, sold_on)
);

INSERT INTO window_lab.daily_sales
    (store_id, sold_on, revenue, order_count)
VALUES
    ('HCM', DATE '2026-03-01', 100.00, 10),
    ('HCM', DATE '2026-03-02', 130.00, 11),
    ('HCM', DATE '2026-03-03', 130.00, 15),
    ('HCM', DATE '2026-03-05',  80.00,  8),
    ('HCM', DATE '2026-03-06', 180.00, 20),
    ('HN',  DATE '2026-03-01',  60.00,  6),
    ('HN',  DATE '2026-03-03',  90.00,  8),
    ('HN',  DATE '2026-03-04',  90.00,  9),
    ('HN',  DATE '2026-03-06', 120.00, 11);
~~~

Một truy vấn hiển thị rõ dữ liệu:

~~~sql
SELECT store_id, sold_on, revenue, order_count
FROM window_lab.daily_sales
ORDER BY store_id, sold_on;
~~~

Với cửa hàng HCM:

~~~text
2026-03-01  100.00
2026-03-02  130.00
2026-03-03  130.00
2026-03-05   80.00
2026-03-06  180.00
~~~

**Ngày 2026-03-04 chưa có hàng.** LAG của 2026-03-05 sẽ đọc hàng ngày 2026-03-03, không tự sinh hàng 2026-03-04.

## 4. Ví dụ LAG đầu tiên

~~~sql
SELECT
    store_id,
    sold_on,
    revenue,
    LAG(revenue) OVER (
        PARTITION BY store_id
        ORDER BY sold_on
    ) AS previous_revenue
FROM window_lab.daily_sales
ORDER BY store_id, sold_on;
~~~

Một phần kết quả cho HCM:

| sold_on | revenue | previous_revenue |
|---|---:|---:|
| 2026-03-01 | 100.00 | NULL |
| 2026-03-02 | 130.00 | 100.00 |
| 2026-03-03 | 130.00 | 130.00 |
| 2026-03-05 | 80.00 | 130.00 |
| 2026-03-06 | 180.00 | 80.00 |

Phân tích:

1. `PARTITION BY store_id` tạo chuỗi riêng cho từng cửa hàng.
2. `ORDER BY sold_on` sắp các hàng theo ngày tăng dần **bên trong** cửa hàng.
3. `LAG(revenue)` lấy giá trị revenue của hàng trước.
4. Hàng đầu của mỗi nhóm không có hàng trước, nên mặc định trả `NULL`.
5. Hàng ngày 2026-03-05 có previous_revenue là doanh thu ngày 2026-03-03 vì đó là **hàng liền trước tồn tại**.

### 4.1. Không có PARTITION BY thì sao?

~~~sql
SELECT
    store_id,
    sold_on,
    revenue,
    LAG(revenue) OVER (
        ORDER BY store_id, sold_on
    ) AS previous_revenue
FROM window_lab.daily_sales
ORDER BY store_id, sold_on;
~~~

Câu này coi toàn bộ tập là một chuỗi. Hàng đầu của HCM có thể nhận previous_revenue từ hàng cuối của HN, vì hai cửa hàng bị nối thành **một partition duy nhất**.

Nếu mục tiêu là “doanh thu ngày trước của chính cửa hàng”, như vậy sẽ sai nghiệp vụ.

**PARTITION BY trả lời “so sánh bên trong nhóm nào?”; ORDER BY trả lời “trước/sau theo thứ tự nào?”**.

## 5. LEAD: nhìn hàng tiếp theo

~~~sql
SELECT
    store_id,
    sold_on,
    revenue,
    LEAD(revenue) OVER (
        PARTITION BY store_id
        ORDER BY sold_on
    ) AS next_revenue
FROM window_lab.daily_sales
ORDER BY store_id, sold_on;
~~~

Đối với HCM:

| sold_on | revenue | next_revenue |
|---|---:|---:|
| 2026-03-01 | 100.00 | 130.00 |
| 2026-03-02 | 130.00 | 130.00 |
| 2026-03-03 | 130.00 | 80.00 |
| 2026-03-05 | 80.00 | 180.00 |
| 2026-03-06 | 180.00 | NULL |

`LEAD(revenue)` của ngày 2026-03-03 là giá trị tại **hàng tiếp theo đang có**, tức ngày 2026-03-05.

Hàng cuối nhóm không có hàng tiếp theo, nên mặc định trả `NULL`.

### 5.1. Đọc cùng lúc hàng trước và hàng sau

~~~sql
SELECT
    store_id,
    sold_on,
    revenue,
    LAG(revenue) OVER (
        PARTITION BY store_id
        ORDER BY sold_on
    ) AS previous_revenue,
    LEAD(revenue) OVER (
        PARTITION BY store_id
        ORDER BY sold_on
    ) AS next_revenue
FROM window_lab.daily_sales
ORDER BY store_id, sold_on;
~~~

Đây là cấu trúc cơ bản của một **truy vấn so sánh lân cận**: một hàng hiện tại có thể nhìn cả quá khứ gần nhất và tương lai gần nhất theo thứ tự dữ liệu.

## 6. “Hàng trước” khác “thời gian trước một ngày”

Trong bảng HCM, chuỗi ngày là:

~~~text
03-01 -> 03-02 -> 03-03 -> 03-05 -> 03-06
~~~

Tại ngày 03-05:

- `LAG(sold_on)` trả **2026-03-03**.
- `sold_on - INTERVAL '1 day'` tương ứng ngày **2026-03-04**.

Hai khái niệm khác nhau:

- **Hàng trước được ghi nhận:** hàng xuất hiện ngay trước trong thứ tự.
- **Ngày lịch liền trước:** một ngày đúng trước đó trong lịch, kể cả nếu bảng không có hàng.

Ví dụ:

~~~sql
SELECT
    store_id,
    sold_on,
    LAG(sold_on) OVER (
        PARTITION BY store_id
        ORDER BY sold_on
    ) AS previous_recorded_date,
    sold_on - LAG(sold_on) OVER (
        PARTITION BY store_id
        ORDER BY sold_on
    ) AS days_since_previous_record
FROM window_lab.daily_sales
ORDER BY store_id, sold_on;
~~~

Ở PostgreSQL, phép `DATE - DATE` trả số ngày nguyên. Với HCM ngày 2026-03-05, khoảng cách là **2 ngày**, không phải 1.

**Đừng dùng LAG để định nghĩa “hôm qua” khi dữ liệu có ngày thiếu mà nghiệp vụ yêu cầu so sánh đúng ngày lịch.** Khi đó cần tạo lịch ngày hoặc JOIN trực tiếp với ngày tương ứng; phần sau sẽ minh họa.

## 7. Tính chênh lệch giữa hai hàng liền kề

Một nhu cầu thường gặp là đo mức tăng/giảm:

\[
\Delta_i = x_i - x_{i-1}
\]

Trong PostgreSQL:

~~~sql
SELECT
    store_id,
    sold_on,
    revenue,
    LAG(revenue) OVER (
        PARTITION BY store_id
        ORDER BY sold_on
    ) AS previous_revenue,
    revenue - LAG(revenue) OVER (
        PARTITION BY store_id
        ORDER BY sold_on
    ) AS revenue_delta
FROM window_lab.daily_sales
ORDER BY store_id, sold_on;
~~~

Với HCM:

| Ngày | Doanh thu | Trước đó | Chênh lệch |
|---|---:|---:|---:|
| 03-01 | 100.00 | NULL | NULL |
| 03-02 | 130.00 | 100.00 | +30.00 |
| 03-03 | 130.00 | 130.00 | 0.00 |
| 03-05 | 80.00 | 130.00 | -50.00 |
| 03-06 | 180.00 | 80.00 | +100.00 |

Đối với hàng đầu, `NULL` là thông tin hợp lý: không có quan sát trước để tính chênh lệch.

### 7.1. CTE để tránh lặp lời gọi LAG

Khi cần nhiều phép tính với cùng previous_revenue, dùng CTE giúp query dễ đọc:

~~~sql
WITH compared AS (
    SELECT
        store_id,
        sold_on,
        revenue,
        LAG(revenue) OVER (
            PARTITION BY store_id
            ORDER BY sold_on
        ) AS previous_revenue
    FROM window_lab.daily_sales
)
SELECT
    store_id,
    sold_on,
    revenue,
    previous_revenue,
    revenue - previous_revenue AS revenue_delta
FROM compared
ORDER BY store_id, sold_on;
~~~

CTE đặt tên cho kết quả trung gian. Điều đó không có nghĩa PostgreSQL luôn vật lý hóa CTE thành một bảng riêng; optimizer có thể xử lý nó theo cách phù hợp với phiên bản và ngữ cảnh.

## 8. Tính phần trăm thay đổi và tránh chia cho 0

Phần trăm biến động:

\[
\text{changePercent}
=
\frac{\text{current}-\text{previous}}{\text{previous}}
\times 100
\]

Ví dụ:

~~~sql
WITH compared AS (
    SELECT
        store_id,
        sold_on,
        revenue,
        LAG(revenue) OVER (
            PARTITION BY store_id
            ORDER BY sold_on
        ) AS previous_revenue
    FROM window_lab.daily_sales
)
SELECT
    store_id,
    sold_on,
    revenue,
    previous_revenue,
    ROUND(
        100.0 * (revenue - previous_revenue)
        / NULLIF(previous_revenue, 0),
        2
    ) AS change_percent
FROM compared
ORDER BY store_id, sold_on;
~~~

Với HCM ngày 03-02:

\[
(130-100)/100\times100=30\%
\]

Ngày 03-05 so với ngày ghi nhận trước 03-03:

\[
(80-130)/130\times100\approx-38.46\%
\]

### 8.1. Tại sao dùng NULLIF?

`NULLIF(previous_revenue, 0)` trả `NULL` nếu doanh thu trước là 0, tránh lỗi chia cho 0.

Nếu không có doanh thu trước (hàng đầu), biểu thức cũng trả `NULL`. Hai trường hợp “không có hàng trước” và “hàng trước bằng 0” đều khiến phần trăm không có định nghĩa trong công thức này, nhưng ý nghĩa nghiệp vụ khác nhau.

**Không tự thay phần trăm tăng từ 0 lên số dương thành 100%.** Khi mẫu số bằng 0, mức tăng tương đối theo công thức trên không xác định. Ứng dụng có thể hiển thị “không áp dụng” hoặc định nghĩa metric khác theo yêu cầu sản phẩm.

## 9. LAG/LEAD với offset lớn hơn 1

Tham số thứ hai cho biết số hàng cần lùi hoặc tiến:

~~~sql
SELECT
    store_id,
    sold_on,
    revenue,
    LAG(revenue, 1) OVER (
        PARTITION BY store_id
        ORDER BY sold_on
    ) AS previous_1,
    LAG(revenue, 2) OVER (
        PARTITION BY store_id
        ORDER BY sold_on
    ) AS previous_2,
    LEAD(revenue, 2) OVER (
        PARTITION BY store_id
        ORDER BY sold_on
    ) AS next_2
FROM window_lab.daily_sales
ORDER BY store_id, sold_on;
~~~

Với HCM tại ngày 03-05:

- `LAG(revenue, 1)` đọc doanh thu 03-03: 130.
- `LAG(revenue, 2)` đọc doanh thu 03-02: 130.
- `LEAD(revenue, 2)` không có hai hàng phía sau (chỉ còn 03-06), nên trả `NULL`.

**Offset 2 nghĩa là hai hàng, không phải hai ngày hoặc hai phút.** Để so sánh với một khoảng thời gian cố định, hãy xử lý trục thời gian một cách rõ ràng.

### 9.1. Offset 0 có ý nghĩa gì?

`LAG(value, 0)` hoặc `LEAD(value, 0)` tham chiếu **hàng hiện tại**. Vì vậy khi offset bằng 0, kết quả là chính biểu thức ở hàng đó.

~~~sql
SELECT
    sold_on,
    revenue,
    LAG(revenue, 0) OVER (
        PARTITION BY store_id
        ORDER BY sold_on
    ) AS same_row_value
FROM window_lab.daily_sales
WHERE store_id = 'HCM'
ORDER BY sold_on;
~~~

Offset âm không phải cách chuẩn để “đảo chiều” logic; hãy dùng đúng hàm `LAG`/`LEAD` hoặc thay đổi ORDER BY. Với offset động, cần kiểm soát giá trị hợp lệ của tham số.

### 9.2. Offset có thể là một biểu thức

PostgreSQL cho phép offset là một biểu thức phù hợp và được đánh giá trong ngữ cảnh hàng hiện tại. Trong ứng dụng thật, nên dùng offset cố định nhỏ hoặc tham số đã kiểm tra để giữ semantics rõ và tránh truy cập vượt xa số hàng trong partition.

Một offset bằng `NULL` có semantics khác với một vị trí không tồn tại, nên không nên biến offset động thành giá trị tùy ý chưa validate.

## 10. Tham số default: khi không có hàng trước/sau

Dạng ba tham số:

~~~sql
LAG(value_expression, offset, default_expression)
LEAD(value_expression, offset, default_expression)
~~~

Tham số thứ ba được dùng khi hàng ở vị trí yêu cầu **không tồn tại** trong partition.

Ví dụ:

~~~sql
SELECT
    store_id,
    sold_on,
    revenue,
    LAG(revenue, 1, 0::NUMERIC) OVER (
        PARTITION BY store_id
        ORDER BY sold_on
    ) AS previous_or_zero
FROM window_lab.daily_sales
ORDER BY store_id, sold_on;
~~~

Hàng đầu mỗi cửa hàng sẽ có previous_or_zero là 0 thay vì NULL.

### 10.1. Không đánh đồng default với việc thay NULL của hàng lân cận

Giả sử doanh thu có thể NULL trong một bảng dữ liệu khác. Nếu **hàng trước tồn tại nhưng giá trị của nó là NULL**, tham số default của `LAG` không tự thay NULL đó bằng 0.

Phân biệt:

| Tình huống | `LAG(x,1,0)` |
|---|---|
| Hàng hiện tại là hàng đầu partition | 0 |
| Có hàng trước và x của hàng trước là 125 | 125 |
| Có hàng trước nhưng x của hàng trước là NULL | NULL |

Đây là điểm dễ nhầm giữa:

~~~sql
LAG(x, 1, 0) OVER (...)
~~~

và:

~~~sql
COALESCE(LAG(x) OVER (...), 0)
~~~

Biểu thức `COALESCE` thay cả trường hợp “không có hàng trước” **và** “hàng trước có giá trị NULL”. Hai cách không hoàn toàn tương đương.

### 10.2. Khi nào nên để mặc định NULL?

Với báo cáo biến động, `NULL` thường diễn đạt đúng rằng **không đủ dữ liệu**. Nếu ép hàng đầu thành 0, chênh lệch đầu tiên có thể bị hiểu sai là tăng từ 0 lên giá trị thật.

Chỉ thay bằng 0 khi nghiệp vụ xác nhận ý nghĩa “không có quan sát trước” tương đương 0. Đừng dùng default để che lấp dữ liệu thiếu.

## 11. PARTITION BY: so sánh độc lập theo từng nhóm

Nếu bỏ `PARTITION BY`, LAG/LEAD sẽ đi qua toàn bộ tập dữ liệu, bất kể hàng thuộc cửa hàng nào.

Để phân tích từng khách hàng, thiết bị hoặc sản phẩm, cần chia partition theo khóa nghiệp vụ:

~~~sql
LAG(revenue) OVER (
    PARTITION BY store_id
    ORDER BY sold_on
)
~~~

Các partition giống như những chuỗi độc lập:

~~~text
HCM: [100] -> [130] -> [130] -> [80] -> [180]

HN : [60]  -> [90]  -> [90]  -> [120]
~~~

Mỗi chuỗi có:

- Hàng đầu: `LAG` trả NULL nếu không có default.
- Hàng cuối: `LEAD` trả NULL nếu không có default.
- Các hàng giữa: LAG/LEAD chỉ nhìn trong chính partition.

### 11.1. PARTITION BY khác GROUP BY

`GROUP BY store_id` gom nhiều hàng thành một hàng cho từng cửa hàng khi tính aggregate tương ứng.

`PARTITION BY store_id` trong cửa sổ **không làm mất hàng chi tiết**. Nó định nghĩa những nhóm bên trong đó hàm cửa sổ hoạt động.

~~~sql
SELECT
    store_id,
    sold_on,
    revenue,
    LAG(revenue) OVER (
        PARTITION BY store_id
        ORDER BY sold_on
    ) AS previous_revenue
FROM window_lab.daily_sales;
~~~

Vẫn trả từng ngày của từng cửa hàng.

### 11.2. Có thể partition theo nhiều cột

Ví dụ một bảng thực tế có `tenant_id`, `device_id` và `measured_at`:

~~~sql
LAG(measurement) OVER (
    PARTITION BY tenant_id, device_id
    ORDER BY measured_at, measurement_id
)
~~~

Điều này tạo chuỗi riêng cho từng **cặp tenant–device**. Nếu chỉ partition theo device_id trong hệ thống multi-tenant mà ID có thể trùng giữa tenant, kết quả có thể trộn dữ liệu khác tenant.

## 12. ORDER BY trong OVER khác ORDER BY của kết quả

Có hai vị trí `ORDER BY`:

~~~sql
SELECT
    store_id,
    sold_on,
    revenue,
    LAG(revenue) OVER (
        PARTITION BY store_id
        ORDER BY sold_on ASC
    ) AS previous_revenue
FROM window_lab.daily_sales
ORDER BY store_id, sold_on DESC;
~~~

- `ORDER BY sold_on ASC` trong `OVER` quyết định **hàng nào được xem là trước** khi tính LAG.
- `ORDER BY store_id, sold_on DESC` ở cuối câu SQL quyết định **thứ tự trình bày kết quả**.

Kết quả được in theo ngày giảm dần trong mỗi cửa hàng, nhưng `previous_revenue` vẫn là doanh thu của **hàng theo ngày tăng dần đứng ngay trước**.

**Không dựa vào thứ tự kết quả tự nhiên** sau khi có window function. Nếu UI cần thứ tự cụ thể, thêm `ORDER BY` ngoài cùng một cách tường minh.

## 13. Nếu đổi ORDER BY DESC, nghĩa của LAG cũng đổi

Với HCM:

~~~sql
SELECT
    sold_on,
    revenue,
    LAG(revenue) OVER (
        ORDER BY sold_on DESC
    ) AS previous_in_desc_order,
    LEAD(revenue) OVER (
        ORDER BY sold_on DESC
    ) AS next_in_desc_order
FROM window_lab.daily_sales
WHERE store_id = 'HCM'
ORDER BY sold_on DESC;
~~~

Theo DESC, hàng “trước” trong thứ tự là hàng **ngày mới hơn**, không phải ngày cũ hơn.

Ví dụ tại ngày 03-05:

- `LAG(revenue) OVER (ORDER BY sold_on DESC)` đọc ngày 03-06.
- `LEAD(revenue) OVER (ORDER BY sold_on DESC)` đọc ngày 03-03.

Không có quy tắc “LAG luôn chỉ quá khứ”. **LAG chỉ lùi theo thứ tự cửa sổ**, nên ý nghĩa thời gian phụ thuộc ASC/DESC.

## 14. Thứ tự không duy nhất có thể làm kết quả không ổn định

Bảng `daily_sales` có primary key `(store_id,sold_on)` nên trong một cửa hàng, `sold_on` là duy nhất. Nhưng nhiều bảng sự kiện có thể ghi **hai hàng cùng timestamp**.

Ví dụ:

~~~sql
CREATE TABLE window_lab.device_event (
    event_id BIGINT PRIMARY KEY,
    device_id TEXT NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL,
    state TEXT NOT NULL
        CHECK (state IN ('online', 'offline', 'maintenance')),
    temperature NUMERIC(7, 2)
);

INSERT INTO window_lab.device_event
    (event_id, device_id, recorded_at, state, temperature)
VALUES
    (1, 'sensor-A', TIMESTAMPTZ '2026-03-01 08:00:00+00', 'online',      24.0),
    (2, 'sensor-A', TIMESTAMPTZ '2026-03-01 08:05:00+00', 'online',      24.5),
    (3, 'sensor-A', TIMESTAMPTZ '2026-03-01 08:05:00+00', 'maintenance', 24.5),
    (4, 'sensor-A', TIMESTAMPTZ '2026-03-01 08:20:00+00', 'offline',     NULL),
    (5, 'sensor-A', TIMESTAMPTZ '2026-03-01 09:30:00+00', 'online',      25.0),
    (6, 'sensor-B', TIMESTAMPTZ '2026-03-01 08:00:00+00', 'online',      22.0),
    (7, 'sensor-B', TIMESTAMPTZ '2026-03-01 08:40:00+00', 'offline',     NULL);
~~~

Nếu viết:

~~~sql
LAG(state) OVER (
    PARTITION BY device_id
    ORDER BY recorded_at
)
~~~

thì hai sự kiện của `sensor-A` lúc 08:05 **đồng hạng về sort key**. PostgreSQL không bảo đảm giữa chúng sự kiện nào đứng trước nếu không có khóa bổ sung.

Nên viết:

~~~sql
LAG(state) OVER (
    PARTITION BY device_id
    ORDER BY recorded_at, event_id
)
~~~

Khi `event_id` là primary key, cặp `(recorded_at,event_id)` phân định được thứ tự.

### 14.1. Tie-breaker không tự định nghĩa thứ tự nghiệp vụ

`ORDER BY recorded_at,event_id` là lựa chọn kỹ thuật ổn định, nhưng nếu hai sự kiện cùng timestamp có thứ tự nghiệp vụ thực sự khác với thứ tự ID, phải xác định nguồn sự thật phù hợp: sequence của thiết bị, số phiên bản, offset trong stream hoặc mốc sự kiện có độ chính xác hơn.

Một thứ tự **xác định** chưa chắc là thứ tự **nghiệp vụ đúng**. DDL và dữ liệu nguồn cần thể hiện quy tắc sự kiện.

## 15. So sánh nhiều cột của hàng trước

Ta có thể đọc đồng thời thời điểm, trạng thái và nhiệt độ của hàng trước, miễn là mọi lời gọi dùng **cùng window definition**.

~~~sql
SELECT
    device_id,
    event_id,
    recorded_at,
    state,
    temperature,
    LAG(recorded_at) OVER (
        PARTITION BY device_id
        ORDER BY recorded_at, event_id
    ) AS previous_at,
    LAG(state) OVER (
        PARTITION BY device_id
        ORDER BY recorded_at, event_id
    ) AS previous_state,
    LAG(temperature) OVER (
        PARTITION BY device_id
        ORDER BY recorded_at, event_id
    ) AS previous_temperature
FROM window_lab.device_event
ORDER BY device_id, recorded_at, event_id;
~~~

Tất cả `previous_*` tham chiếu cùng hàng đứng trước trong mỗi partition, bởi thứ tự cửa sổ giống nhau.

Nếu vô tình dùng một lời gọi ORDER BY `recorded_at` và một lời gọi ORDER BY `recorded_at,event_id`, khi timestamp trùng thì kết quả có thể **ghép thuộc tính từ những hàng trước khác nhau**. Vì vậy đừng thay đổi window specification tùy tiện giữa các biểu thức của cùng một phép so sánh.

## 16. Dùng named WINDOW để tái sử dụng thứ tự

PostgreSQL cho phép đặt tên window definition:

~~~sql
SELECT
    device_id,
    event_id,
    recorded_at,
    state,
    LAG(recorded_at) OVER event_order AS previous_at,
    LAG(state) OVER event_order AS previous_state,
    LEAD(state) OVER event_order AS next_state
FROM window_lab.device_event
WINDOW event_order AS (
    PARTITION BY device_id
    ORDER BY recorded_at, event_id
)
ORDER BY device_id, recorded_at, event_id;
~~~

Cú pháp `WINDOW event_order AS (...)` giúp:

- Tránh lặp `PARTITION BY`/`ORDER BY` dài.
- Giảm rủi ro các lời gọi vô tình sử dụng thứ tự khác nhau.
- Làm query đọc như “cùng một chuỗi sự kiện”.
- Dễ mở rộng khi cần thêm `LAG`/`LEAD` cho các trường.

`WINDOW` là **tên trong phạm vi câu SQL**, không tạo đối tượng bền vững và không tạo index. Nó không khiến toàn bộ phép tính miễn phí; PostgreSQL vẫn phải xử lý window theo kế hoạch thực thi.

## 17. So sánh trạng thái bằng IS DISTINCT FROM

Bài toán: chỉ tìm những sự kiện mà trạng thái **thay đổi so với sự kiện trước**.

Một cách viết:

~~~sql
WITH transitions AS (
    SELECT
        device_id,
        event_id,
        recorded_at,
        state,
        LAG(state) OVER (
            PARTITION BY device_id
            ORDER BY recorded_at, event_id
        ) AS previous_state
    FROM window_lab.device_event
)
SELECT
    device_id,
    event_id,
    recorded_at,
    previous_state,
    state
FROM transitions
WHERE
    previous_state IS NOT NULL
    AND state IS DISTINCT FROM previous_state
ORDER BY device_id, recorded_at, event_id;
~~~

Với `sensor-A`:

- Event 2: online sau online → không thay đổi.
- Event 3: maintenance sau online → thay đổi.
- Event 4: offline sau maintenance → thay đổi.
- Event 5: online sau offline → thay đổi.

Với `sensor-B`, event 7 là offline sau online → thay đổi.

### 17.1. Vì sao không chỉ viết state <> previous_state?

Nếu hai bên có thể là `NULL`:

~~~sql
NULL <> 'online'
~~~

trả `NULL`/UNKNOWN, không phải TRUE. Biểu thức:

~~~sql
state IS DISTINCT FROM previous_state
~~~

xử lý `NULL` theo semantics hai giá trị:

- Hai NULL → không khác.
- Một NULL và một giá trị không NULL → khác.
- Hai giá trị khác nhau → khác.

Nhưng cần phân biệt **“không có hàng trước”** với **“hàng trước có giá trị NULL”**. Trong ví dụ state được khai báo `NOT NULL`, nên `previous_state IS NULL` xác định đúng hàng đầu partition. Nếu state có thể NULL, điều kiện đó không còn đủ.

## 18. Phân biệt hàng đầu với giá trị trước NULL

Giả sử một chuỗi số đo có `measurement` nullable. `LAG(measurement)` trả NULL trong ít nhất hai trường hợp:

1. Đây là hàng đầu, **không có hàng trước**.
2. Có hàng trước, nhưng **measurement của hàng trước là NULL**.

Để phân biệt, đọc một cột định danh `NOT NULL` của hàng trước:

~~~sql
WITH compared AS (
    SELECT
        device_id,
        event_id,
        recorded_at,
        temperature,
        LAG(event_id) OVER (
            PARTITION BY device_id
            ORDER BY recorded_at, event_id
        ) AS previous_event_id,
        LAG(temperature) OVER (
            PARTITION BY device_id
            ORDER BY recorded_at, event_id
        ) AS previous_temperature
    FROM window_lab.device_event
)
SELECT
    device_id,
    event_id,
    previous_event_id,
    previous_temperature,
    CASE
        WHEN previous_event_id IS NULL
            THEN 'first_event'
        WHEN previous_temperature IS NULL
            THEN 'previous_value_missing'
        ELSE 'previous_value_available'
    END AS comparison_state
FROM compared
ORDER BY device_id, event_id;
~~~

Vì `event_id` là primary key không NULL, `previous_event_id IS NULL` chỉ ra chắc chắn không có hàng trước trong partition.

### 18.1. LAG không tự bỏ qua NULL

Trong PostgreSQL phổ biến, `LAG`/`LEAD` thực hiện theo hành vi **RESPECT NULLS**: hàng có giá trị NULL vẫn được tính là một hàng khi đếm offset.

Ví dụ chuỗi:

~~~text
10, NULL, 30
~~~

Tại 30, `LAG(value)` trả NULL (giá trị của hàng ngay trước), **không tự nhảy ngược qua hàng NULL để lấy 10**.

Không sao chép cú pháp `IGNORE NULLS` từ hệ quản trị khác rồi giả định PostgreSQL hỗ trợ. Nếu bài toán cần **giá trị không NULL gần nhất** thì phải thiết kế giải pháp riêng phù hợp dữ liệu, chẳng hạn một phép tìm kiếm có điều kiện, cấu trúc aggregate/truy vấn phụ hoặc tiền xử lý. Mục sau có ví dụ.

## 19. Tìm giá trị không NULL gần nhất: khác LAG thông thường

Giả sử cần “nhiệt độ gần nhất đã đo được” cho từng event, bỏ qua các event không có giá trị. Với bảng `device_event`, `event_id=4` có nhiệt độ NULL.

Một cách với `LEFT JOIN LATERAL`:

~~~sql
SELECT
    e.device_id,
    e.event_id,
    e.recorded_at,
    e.temperature,
    previous_known.event_id AS known_previous_event_id,
    previous_known.temperature AS known_previous_temperature
FROM window_lab.device_event AS e
LEFT JOIN LATERAL (
    SELECT
        x.event_id,
        x.temperature
    FROM window_lab.device_event AS x
    WHERE
        x.device_id = e.device_id
        AND x.temperature IS NOT NULL
        AND
            (x.recorded_at, x.event_id)
            < (e.recorded_at, e.event_id)
    ORDER BY x.recorded_at DESC, x.event_id DESC
    LIMIT 1
) AS previous_known ON TRUE
ORDER BY e.device_id, e.recorded_at, e.event_id;
~~~

Lệnh này tìm **hàng trước gần nhất có nhiệt độ không NULL**, không nhất thiết là hàng liền trước.

Nếu dùng nhiều trên dữ liệu lớn, cần index phù hợp. Ví dụ:

~~~sql
CREATE INDEX idx_device_event_known_temperature
ON window_lab.device_event (
    device_id,
    recorded_at DESC,
    event_id DESC
)
WHERE temperature IS NOT NULL;
~~~

Đây là bài toán khác với `LAG`: yêu cầu bỏ qua một số hàng theo giá trị cột, nên giải pháp có thể có chi phí riêng.

## 20. Phát hiện khoảng thời gian bất thường giữa hai bản ghi

Ta muốn tìm các lần ghi nhận liên tiếp cách nhau hơn 10 phút.

~~~sql
WITH timed AS (
    SELECT
        device_id,
        event_id,
        recorded_at,
        LAG(recorded_at) OVER (
            PARTITION BY device_id
            ORDER BY recorded_at, event_id
        ) AS previous_at
    FROM window_lab.device_event
)
SELECT
    device_id,
    event_id,
    previous_at,
    recorded_at,
    recorded_at - previous_at AS time_gap
FROM timed
WHERE
    previous_at IS NOT NULL
    AND recorded_at - previous_at > INTERVAL '10 minutes'
ORDER BY device_id, recorded_at, event_id;
~~~

Ví dụ với sensor-A:

- 08:00 → 08:05: 5 phút.
- 08:05 → 08:05: 0 phút.
- 08:05 → 08:20: 15 phút → vượt 10 phút.
- 08:20 → 09:30: 70 phút → vượt 10 phút.

Với sensor-B: 08:00 → 08:40 là 40 phút → vượt 10 phút.

### 20.1. Kiểm tra gap lớn hơn không chứng minh dữ liệu bị mất

Khoảng thời gian dài giữa hai sự kiện có thể có nhiều ý nghĩa:

- Thiết bị không gửi bản tin.
- Hệ thống nhận bản tin chậm.
- Thiết bị được cấu hình ghi ít thường xuyên hơn.
- Dữ liệu bị lọc trước khi query.
- Có sự kiện nhưng chưa được commit hoặc đồng bộ.
- Timestamp ghi nhận khác thời điểm thật của sự kiện.

`LAG` đo **khoảng cách giữa các hàng nhìn thấy trong query**, không tự xác nhận nguyên nhân. Cần kết hợp với SLA, lịch phát bản tin và cơ chế ingest để kết luận.

## 21. Phát hiện ngày thiếu trong chuỗi theo ngày

Trong `daily_sales`, HCM không có hàng 2026-03-04. Ta có thể tìm chỗ gián đoạn:

~~~sql
WITH numbered AS (
    SELECT
        store_id,
        sold_on,
        LAG(sold_on) OVER (
            PARTITION BY store_id
            ORDER BY sold_on
        ) AS previous_day
    FROM window_lab.daily_sales
)
SELECT
    store_id,
    previous_day,
    sold_on,
    sold_on - previous_day AS calendar_days_between,
    sold_on - previous_day - 1 AS missing_days
FROM numbered
WHERE
    previous_day IS NOT NULL
    AND sold_on - previous_day > 1
ORDER BY store_id, sold_on;
~~~

Ví dụ:

- HCM: giữa 03-03 và 03-05 thiếu 1 ngày là 03-04.
- HN: giữa 03-01 và 03-03 thiếu 1 ngày là 03-02.
- HN: giữa 03-04 và 03-06 thiếu 1 ngày là 03-05.

Kết quả chỉ phát hiện khoảng trống **giữa hai ngày đã được ghi nhận**. Nó không tự chỉ ra các ngày thiếu **trước ngày đầu** hoặc **sau ngày cuối** nếu không có phạm vi thời gian kỳ vọng.

### 21.1. Ngày thiếu không nhất thiết là doanh thu bằng 0

Không có hàng có thể có nghĩa:

- Cửa hàng không mở.
- Hệ thống ETL chưa nạp dữ liệu.
- Doanh thu đúng là 0 nhưng hệ thống không ghi dòng.
- Báo cáo chỉ chứa ngày có đơn.

Trước khi điền 0 cho ngày trống, hãy xác định semantics. Nếu không, chênh lệch và trung bình sau khi điền có thể sai nghiệp vụ.

## 22. So sánh đúng ngày lịch trước bằng generate_series

Nếu yêu cầu là “so sánh **ngày hôm nay với ngày hôm qua**, kể cả không có dòng ngày hôm qua”, cần tạo trục lịch ngày đầy đủ.

Ví dụ cho riêng HCM trong khoảng 03-01 đến 03-06:

~~~sql
WITH calendar AS (
    SELECT gs::DATE AS sold_on
    FROM generate_series(
        DATE '2026-03-01'::TIMESTAMP,
        DATE '2026-03-06'::TIMESTAMP,
        INTERVAL '1 day'
    ) AS gs
),
daily AS (
    SELECT
        c.sold_on,
        s.revenue,
        s.order_count
    FROM calendar AS c
    LEFT JOIN window_lab.daily_sales AS s
        ON s.store_id = 'HCM'
       AND s.sold_on = c.sold_on
)
SELECT
    sold_on,
    revenue,
    LAG(revenue) OVER (
        ORDER BY sold_on
    ) AS previous_calendar_day_revenue
FROM daily
ORDER BY sold_on;
~~~

Lúc này có một hàng cho ngày 2026-03-04, nhưng `revenue` là NULL vì không có dữ liệu. Ngày 03-05 có `LAG(revenue) = NULL`, đúng với cách diễn đạt “giá trị của ngày lịch liền trước chưa biết”.

Nếu nghiệp vụ xác nhận ngày không có bản ghi đồng nghĩa doanh thu 0, có thể dùng:

~~~sql
COALESCE(s.revenue, 0::NUMERIC) AS revenue
~~~

ở CTE `daily`. Khi đó LAG của 03-05 sẽ là 0. **Đây là một quyết định nghiệp vụ**, không phải tính năng tự động của LAG.

### 22.1. Tạo lịch cho nhiều cửa hàng

Khi muốn tạo đầy đủ lịch cho nhiều store:

1. Xác định phạm vi store.
2. CROSS JOIN từng store với ngày trong khoảng.
3. LEFT JOIN dữ liệu gốc theo `(store_id,sold_on)`.
4. Dùng `PARTITION BY store_id ORDER BY sold_on`.

Ví dụ:

~~~sql
WITH
stores AS (
    SELECT DISTINCT store_id
    FROM window_lab.daily_sales
),
calendar AS (
    SELECT gs::DATE AS sold_on
    FROM generate_series(
        DATE '2026-03-01'::TIMESTAMP,
        DATE '2026-03-06'::TIMESTAMP,
        INTERVAL '1 day'
    ) AS gs
),
grid AS (
    SELECT
        st.store_id,
        cal.sold_on,
        s.revenue
    FROM stores AS st
    CROSS JOIN calendar AS cal
    LEFT JOIN window_lab.daily_sales AS s
        ON s.store_id = st.store_id
       AND s.sold_on = cal.sold_on
)
SELECT
    store_id,
    sold_on,
    revenue,
    LAG(revenue) OVER (
        PARTITION BY store_id
        ORDER BY sold_on
    ) AS previous_calendar_day_revenue
FROM grid
ORDER BY store_id, sold_on;
~~~

Nếu có hàng triệu store và nhiều năm dữ liệu, `CROSS JOIN` tạo một số lượng hàng rất lớn. Cần giới hạn phạm vi và đánh giá chi phí trước khi áp dụng trên production.

## 23. LEAD để tính thời gian tới sự kiện tiếp theo

Với nhật ký thao tác, người học thường muốn biết **mất bao lâu cho đến khi có event tiếp theo của cùng thiết bị**.

~~~sql
WITH ordered_events AS (
    SELECT
        device_id,
        event_id,
        recorded_at,
        state,
        LEAD(event_id) OVER (
            PARTITION BY device_id
            ORDER BY recorded_at, event_id
        ) AS next_event_id,
        LEAD(recorded_at) OVER (
            PARTITION BY device_id
            ORDER BY recorded_at, event_id
        ) AS next_at
    FROM window_lab.device_event
)
SELECT
    device_id,
    event_id,
    state,
    recorded_at,
    next_event_id,
    next_at,
    next_at - recorded_at AS until_next_event
FROM ordered_events
ORDER BY device_id, recorded_at, event_id;
~~~

Đối với `sensor-A` event 3 lúc 08:05, event tiếp theo là event 4 lúc 08:20; thời gian là 15 phút.

Với event 5 là event cuối, `next_at` NULL; không thể tính độ dài “đến sự kiện sau” vì chưa có sự kiện sau.

### 23.1. LEAD và thời lượng trạng thái

Nếu mỗi event ghi trạng thái mới của thiết bị và trạng thái giữ nguyên cho đến event tiếp theo, có thể diễn giải khoảng:

~~~text
[state tại recorded_at, next_at)
~~~

thành thời gian trạng thái đó có hiệu lực theo **mô hình sự kiện**.

Nhưng:

- Event cuối chưa có mốc kết thúc.
- Có thể có sự kiện đến trễ hoặc ghi sai timestamp.
- Một số trạng thái có thể không kéo dài đến sự kiện sau theo nghiệp vụ.
- Các event cùng timestamp cho thời lượng 0.
- Không nên ép `next_at NULL` thành `now()` nếu báo cáo yêu cầu chỉ tính khoảng đã đóng.

Cần xác định semantics trước khi cộng thời lượng của từng trạng thái.

## 24. Ghi nhận các lần thay đổi, bỏ sự kiện lặp trạng thái

Trong nhật ký có những event liên tiếp cùng `state`. Nếu chỉ quan tâm **lần chuyển trạng thái**, dùng LAG rồi lọc kết quả ở query ngoài:

~~~sql
WITH compared AS (
    SELECT
        device_id,
        event_id,
        recorded_at,
        state,
        LAG(event_id) OVER (
            PARTITION BY device_id
            ORDER BY recorded_at, event_id
        ) AS previous_event_id,
        LAG(state) OVER (
            PARTITION BY device_id
            ORDER BY recorded_at, event_id
        ) AS previous_state
    FROM window_lab.device_event
)
SELECT
    device_id,
    event_id,
    recorded_at,
    previous_state,
    state,
    CASE
        WHEN previous_event_id IS NULL THEN 'initial_state'
        ELSE 'state_changed'
    END AS change_kind
FROM compared
WHERE
    previous_event_id IS NULL
    OR state IS DISTINCT FROM previous_state
ORDER BY device_id, recorded_at, event_id;
~~~

Câu này giữ:

- Event đầu của mỗi thiết bị để biết trạng thái khởi đầu.
- Những event có trạng thái khác event ngay trước.
- Bỏ các event lặp cùng trạng thái.

Đây là phép **lọc thay đổi lân cận**, không tự tạo một event history có đầy đủ bảo đảm audit. Nếu dữ liệu gốc được nhập sai thứ tự hoặc bị sửa sau đó, kết quả chuyển trạng thái có thể thay đổi.

## 25. Phân loại tăng, giảm hay không đổi

Với doanh thu theo ngày:

~~~sql
WITH compared AS (
    SELECT
        store_id,
        sold_on,
        revenue,
        LAG(revenue) OVER (
            PARTITION BY store_id
            ORDER BY sold_on
        ) AS previous_revenue
    FROM window_lab.daily_sales
)
SELECT
    store_id,
    sold_on,
    revenue,
    previous_revenue,
    CASE
        WHEN previous_revenue IS NULL THEN 'first_observation'
        WHEN revenue > previous_revenue THEN 'increase'
        WHEN revenue < previous_revenue THEN 'decrease'
        ELSE 'unchanged'
    END AS movement
FROM compared
ORDER BY store_id, sold_on;
~~~

Với HCM:

~~~text
03-01 -> first_observation
03-02 -> increase
03-03 -> unchanged
03-05 -> decrease
03-06 -> increase
~~~

### 25.1. Khi dữ liệu có thể NULL

Nếu `revenue` nullable, nhánh `ELSE 'unchanged'` có thể sai khi một trong hai giá trị NULL: các phép `>` và `<` trả UNKNOWN.

Khi đó nên có nhánh riêng:

~~~sql
CASE
    WHEN previous_row_id IS NULL THEN 'first_observation'
    WHEN revenue IS NULL OR previous_revenue IS NULL
        THEN 'missing_value'
    WHEN revenue > previous_revenue THEN 'increase'
    WHEN revenue < previous_revenue THEN 'decrease'
    ELSE 'unchanged'
END
~~~

`previous_row_id` là kết quả `LAG` trên khóa NOT NULL, giúp xác định hàng đầu một cách chính xác.

## 26. Phát hiện thay đổi lớn bất thường

Giả sử muốn đánh dấu ngày mà doanh thu tăng/giảm hơn 50% so với lần ghi nhận trước:

~~~sql
WITH compared AS (
    SELECT
        store_id,
        sold_on,
        revenue,
        LAG(revenue) OVER (
            PARTITION BY store_id
            ORDER BY sold_on
        ) AS previous_revenue
    FROM window_lab.daily_sales
),
changes AS (
    SELECT
        store_id,
        sold_on,
        revenue,
        previous_revenue,
        (revenue - previous_revenue)
            / NULLIF(previous_revenue, 0) AS change_ratio
    FROM compared
)
SELECT
    store_id,
    sold_on,
    revenue,
    previous_revenue,
    ROUND(change_ratio * 100, 2) AS change_percent
FROM changes
WHERE ABS(change_ratio) > 0.50
ORDER BY store_id, sold_on;
~~~

Bài toán có thể áp dụng cho lưu lượng truy cập, số đơn, khối lượng dữ liệu hoặc những phép đo định lượng khác.

**Cảnh báo:** một giá trị bất thường trong phân tích dữ liệu không tự là sự cố. Nếu có khoảng trống ngày hoặc thay đổi giờ mở cửa, so sánh hai bản ghi kế tiếp có thể chưa đủ để đánh giá. Cần thêm ngữ cảnh mùa vụ, lịch kinh doanh và chất lượng dữ liệu.

## 27. LAG/LEAD để tạo phiên hoạt động (sessionization)

Một kỹ thuật phân tích thường dùng: hai sự kiện của cùng một người/thiết bị được xem thuộc **cùng phiên** nếu cách nhau không quá một ngưỡng.

Ví dụ, đặt ngưỡng **30 phút**. Khi khoảng cách đến event trước **lớn hơn 30 phút**, bắt đầu phiên mới. Đây là quy tắc minh họa; mỗi sản phẩm có thể chọn ngưỡng khác.

### 27.1. Bước 1: đọc thời điểm trước

~~~sql
WITH events_with_previous AS (
    SELECT
        device_id,
        event_id,
        recorded_at,
        LAG(recorded_at) OVER (
            PARTITION BY device_id
            ORDER BY recorded_at, event_id
        ) AS previous_at
    FROM window_lab.device_event
)
SELECT
    device_id,
    event_id,
    recorded_at,
    previous_at,
    CASE
        WHEN previous_at IS NULL THEN 1
        WHEN recorded_at - previous_at > INTERVAL '30 minutes'
            THEN 1
        ELSE 0
    END AS starts_new_session
FROM events_with_previous
ORDER BY device_id, recorded_at, event_id;
~~~

Với sensor-A:

- Event 1 bắt đầu phiên 1.
- Event 2/3/4 cách event trước không quá 30 phút nên còn phiên 1.
- Event 5 sau event 4 đến 70 phút nên bắt đầu phiên 2.

### 27.2. Bước 2: dùng SUM cửa sổ để đánh số phiên

Không được đặt trực tiếp một lời gọi window function bên trong lời gọi window function khác ở cùng mức biểu thức. Hãy tạo bước trung gian:

~~~sql
WITH
events_with_previous AS (
    SELECT
        device_id,
        event_id,
        recorded_at,
        LAG(recorded_at) OVER (
            PARTITION BY device_id
            ORDER BY recorded_at, event_id
        ) AS previous_at
    FROM window_lab.device_event
),
markers AS (
    SELECT
        device_id,
        event_id,
        recorded_at,
        CASE
            WHEN previous_at IS NULL THEN 1
            WHEN recorded_at - previous_at > INTERVAL '30 minutes'
                THEN 1
            ELSE 0
        END AS starts_new_session
    FROM events_with_previous
)
SELECT
    device_id,
    event_id,
    recorded_at,
    starts_new_session,
    SUM(starts_new_session) OVER (
        PARTITION BY device_id
        ORDER BY recorded_at, event_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS session_number
FROM markers
ORDER BY device_id, recorded_at, event_id;
~~~

Cách hoạt động:

1. `LAG` tìm mốc event trước.
2. `CASE` tạo cờ 1 nếu cần bắt đầu phiên mới.
3. `SUM` tích lũy số lần bắt đầu phiên trong mỗi device.
4. Mỗi thiết bị có `session_number` tăng theo chuỗi sự kiện.

### 27.3. Vì sao cần ROWS ...?

Đối với phép tổng cửa sổ chạy theo thứ tự, frame xác định tập hàng được tính vào mỗi kết quả. Cấu trúc:

~~~sql
ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
~~~

diễn đạt rõ “cộng các marker từ đầu partition đến hàng hiện tại”.

Khi có timestamp trùng, nếu chỉ dùng window frame mặc định theo `RANGE` ở một số tình huống, các **peer rows** có thể ảnh hưởng cách tổng được tính. Trong ví dụ đã có tie-breaker `event_id`, nhưng viết `ROWS` rõ vẫn làm ý đồ “tích lũy theo từng hàng” minh bạch.

## 28. Gaps and islands: tìm các đoạn liên tiếp

**Gaps and islands** là bài toán chia một chuỗi thành những đoạn liên tục theo điều kiện.

Ví dụ chuỗi ngày ghi nhận có “đảo” những ngày liền nhau, bị ngắt khi thiếu ít nhất một ngày.

### 28.1. Phát hiện mốc mở đầu đoạn

~~~sql
WITH previous_dates AS (
    SELECT
        store_id,
        sold_on,
        LAG(sold_on) OVER (
            PARTITION BY store_id
            ORDER BY sold_on
        ) AS previous_day
    FROM window_lab.daily_sales
),
markers AS (
    SELECT
        store_id,
        sold_on,
        CASE
            WHEN previous_day IS NULL THEN 1
            WHEN sold_on - previous_day > 1 THEN 1
            ELSE 0
        END AS starts_new_island
    FROM previous_dates
)
SELECT
    store_id,
    sold_on,
    SUM(starts_new_island) OVER (
        PARTITION BY store_id
        ORDER BY sold_on
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS island_number
FROM markers
ORDER BY store_id, sold_on;
~~~

Đối với HCM:

~~~text
03-01  island 1
03-02  island 1
03-03  island 1
03-05  island 2
03-06  island 2
~~~

Đối với HN:

~~~text
03-01  island 1
03-03  island 2
03-04  island 2
03-06  island 3
~~~

### 28.2. Gom mỗi đảo thành khoảng

~~~sql
WITH
previous_dates AS (
    SELECT
        store_id,
        sold_on,
        LAG(sold_on) OVER (
            PARTITION BY store_id
            ORDER BY sold_on
        ) AS previous_day
    FROM window_lab.daily_sales
),
markers AS (
    SELECT
        store_id,
        sold_on,
        CASE
            WHEN previous_day IS NULL
              OR sold_on - previous_day > 1
                THEN 1
            ELSE 0
        END AS new_group
    FROM previous_dates
),
numbered AS (
    SELECT
        store_id,
        sold_on,
        SUM(new_group) OVER (
            PARTITION BY store_id
            ORDER BY sold_on
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS group_no
    FROM markers
)
SELECT
    store_id,
    group_no,
    MIN(sold_on) AS first_day,
    MAX(sold_on) AS last_day,
    COUNT(*) AS recorded_days
FROM numbered
GROUP BY store_id, group_no
ORDER BY store_id, first_day;
~~~

Mẫu này áp dụng cho những chuỗi như ngày có hoạt động, sự kiện thiết bị, lịch sử trạng thái hoặc các khoảng thời gian liên tục, với điều kiện tách đoạn do nghiệp vụ định nghĩa.

## 29. So sánh các lần thay đổi giá

Một bài toán quản lý sản phẩm: theo dõi lịch sử giá, tính giá trước đó và phần thay đổi.

~~~sql
CREATE TABLE window_lab.price_history (
    price_change_id BIGINT PRIMARY KEY,
    product_id TEXT NOT NULL,
    effective_at TIMESTAMPTZ NOT NULL,
    price NUMERIC(12, 2) NOT NULL
        CHECK (price >= 0)
);

INSERT INTO window_lab.price_history
    (price_change_id, product_id, effective_at, price)
VALUES
    (1, 'BOOK', TIMESTAMPTZ '2026-01-01 00:00:00+00', 120000.00),
    (2, 'BOOK', TIMESTAMPTZ '2026-02-01 00:00:00+00', 135000.00),
    (3, 'BOOK', TIMESTAMPTZ '2026-04-01 00:00:00+00', 125000.00),
    (4, 'MOUSE', TIMESTAMPTZ '2026-01-15 00:00:00+00', 180000.00),
    (5, 'MOUSE', TIMESTAMPTZ '2026-03-01 00:00:00+00', 180000.00);

SELECT
    product_id,
    effective_at,
    price,
    LAG(price) OVER (
        PARTITION BY product_id
        ORDER BY effective_at, price_change_id
    ) AS previous_price,
    price - LAG(price) OVER (
        PARTITION BY product_id
        ORDER BY effective_at, price_change_id
    ) AS price_difference
FROM window_lab.price_history
ORDER BY product_id, effective_at, price_change_id;
~~~

Lưu ý:

- `effective_at` là thời điểm **giá có hiệu lực theo nghiệp vụ**, có thể khác thời điểm ghi vào database.
- `price_change_id` xác định thứ tự khi hai thay đổi có cùng mốc hiệu lực.
- Hàng đầu mỗi sản phẩm không có previous_price.
- Có thể có lần cập nhật ghi lại **cùng giá**; chênh lệch 0 không tự là lỗi.
- Nếu muốn tìm giá có hiệu lực tại một thời điểm cụ thể, cần quy tắc interval/as-of lookup phù hợp, không chỉ LAG.

## 30. LEAD để tạo khoảng hiệu lực [start, end)

Trong mô hình lịch sử thay đổi, mỗi mức giá có thể được xem là có hiệu lực từ lần thay đổi này **đến trước lần thay đổi kế tiếp**.

~~~sql
SELECT
    product_id,
    price,
    effective_at AS valid_from,
    LEAD(effective_at) OVER (
        PARTITION BY product_id
        ORDER BY effective_at, price_change_id
    ) AS valid_until_exclusive
FROM window_lab.price_history
ORDER BY product_id, effective_at, price_change_id;
~~~

Có thể diễn giải mỗi hàng theo khoảng nửa mở:

~~~text
[valid_from, valid_until_exclusive)
~~~

Lợi ích của khoảng nửa mở:

- Tại đúng thời điểm lần thay đổi tiếp theo có hiệu lực, giá mới được dùng.
- Hai khoảng liền nhau không cùng bao gồm mốc chuyển đổi.
- Dễ viết logic as-of cho các mốc có thứ tự.

Ví dụ tra giá có hiệu lực tại một mốc thời gian:

~~~sql
WITH periods AS (
    SELECT
        product_id,
        price,
        effective_at AS valid_from,
        LEAD(effective_at) OVER (
            PARTITION BY product_id
            ORDER BY effective_at, price_change_id
        ) AS valid_until
    FROM window_lab.price_history
)
SELECT product_id, price
FROM periods
WHERE
    product_id = 'BOOK'
    AND TIMESTAMPTZ '2026-03-01 12:00:00+00' >= valid_from
    AND (
        TIMESTAMPTZ '2026-03-01 12:00:00+00' < valid_until
        OR valid_until IS NULL
    );
~~~

Theo dữ liệu, giá BOOK lúc 2026-03-01 là **135000.00**.

### 30.1. Chú ý khi hai thay đổi cùng effective_at

Nếu hai hàng cùng `effective_at` nhưng khác `price_change_id`, một khoảng có thể có độ dài 0. Phải xác định liệu:

- Thay đổi sau ghi đè thay đổi trước trong cùng thời điểm.
- Hệ thống cho phép nhiều phiên bản cùng mốc.
- Cần constraint ngăn trùng effective time.
- Có thêm thông tin sequence/validity để giải thích thứ tự.

LAG/LEAD chỉ đọc chuỗi theo ORDER BY; chúng không tự xác nhận lịch sử giá hợp lệ về nghiệp vụ.

## 31. ROW_NUMBER và LAG: bổ trợ nhưng không giống nhau

`ROW_NUMBER()` đánh số hàng theo thứ tự cửa sổ, còn `LAG()` đọc một giá trị ở hàng đứng trước.

~~~sql
SELECT
    store_id,
    sold_on,
    revenue,
    ROW_NUMBER() OVER (
        PARTITION BY store_id
        ORDER BY sold_on
    ) AS row_position,
    LAG(revenue) OVER (
        PARTITION BY store_id
        ORDER BY sold_on
    ) AS previous_revenue
FROM window_lab.daily_sales
ORDER BY store_id, sold_on;
~~~

`ROW_NUMBER() = 1` giúp nhận biết hàng đầu khi thứ tự xác định. Nhưng một bộ dữ liệu có `NULL` hợp lệ ở cột so sánh vẫn cần phân biệt “không có hàng trước” với “hàng trước có giá trị NULL”.

Không nên tự dùng `ROW_NUMBER()` rồi JOIN hàng `rn-1` cho mọi bài toán nếu `LAG` đã diễn đạt trực tiếp hơn. Tuy vậy, vị trí hàng vẫn hữu ích khi muốn đánh số phiên, kiểm tra dữ liệu hoặc dùng các phép biến đổi sâu hơn.

## 32. LAG/LEAD có dùng window frame không?

Đây là một phân biệt kỹ thuật quan trọng.

Trong `OVER` của PostgreSQL, có thể có:

- `PARTITION BY`.
- `ORDER BY`.
- Window **frame** như `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`.

Với `LAG`/`LEAD`, vị trí tương đối dựa trên **partition và thứ tự hàng**, không được hiểu là chỉ giới hạn trong frame hiện tại. Đặc biệt:

- `LAG` có thể đọc giá trị của hàng trước dù frame hiện tại chỉ bao gồm hàng hiện tại.
- `LEAD` có thể đọc hàng sau dù frame chạy tích lũy đến current row.

Ví dụ để đối chiếu ý nghĩa:

~~~sql
SELECT
    store_id,
    sold_on,
    revenue,
    LAG(revenue) OVER (
        PARTITION BY store_id
        ORDER BY sold_on
        ROWS BETWEEN CURRENT ROW AND CURRENT ROW
    ) AS previous_revenue
FROM window_lab.daily_sales
ORDER BY store_id, sold_on;
~~~

Trong PostgreSQL, `LAG` vẫn tìm hàng trước theo vị trí trong partition; frame đơn hàng hiện tại **không làm LAG luôn NULL**.

### 32.1. Đừng nhầm với FIRST_VALUE/LAST_VALUE

Các hàm `FIRST_VALUE`, `LAST_VALUE` và `NTH_VALUE` chịu ảnh hưởng của window frame theo semantics tương ứng. Ví dụ `LAST_VALUE` với frame mặc định có thể trả giá trị ở cuối frame hiện tại, không nhất thiết là hàng cuối toàn partition.

LAG/LEAD không bị giới hạn theo cách đó. Khi so sánh hai nhóm hàm, cần tách rõ **relative row offset** và **frame-based calculation**.

## 33. Vì sao không thể đặt LAG trực tiếp trong WHERE?

Một câu SQL thường gặp nhưng không hợp lệ:

~~~sql
-- Không hợp lệ:
-- SELECT *
-- FROM window_lab.daily_sales
-- WHERE revenue > LAG(revenue) OVER (
--     PARTITION BY store_id ORDER BY sold_on
-- );
~~~

Trong PostgreSQL, window functions chỉ được phép dùng trực tiếp ở những vị trí như **SELECT list** và **ORDER BY** của query level phù hợp, không được đặt trực tiếp trong `WHERE`, `GROUP BY` hoặc `HAVING` cùng cấp.

Lý do logic: `WHERE` xác định các hàng đầu vào trước khi cửa sổ được tính. Nếu vừa lọc hàng vừa yêu cầu đọc “hàng trước” từ tập đang lọc, sẽ không có semantics rõ theo thứ tự xử lý SQL.

Cách làm đúng: **tính window ở subquery hoặc CTE**, sau đó lọc bên ngoài:

~~~sql
WITH compared AS (
    SELECT
        store_id,
        sold_on,
        revenue,
        LAG(revenue) OVER (
            PARTITION BY store_id
            ORDER BY sold_on
        ) AS previous_revenue
    FROM window_lab.daily_sales
)
SELECT
    store_id,
    sold_on,
    revenue,
    previous_revenue
FROM compared
WHERE revenue > previous_revenue
ORDER BY store_id, sold_on;
~~~

Câu trên tìm các ngày có doanh thu lớn hơn **hàng trước** theo từng cửa hàng. Hàng đầu có previous_revenue NULL sẽ không thỏa phép `>`.

### 33.1. Không dùng HAVING thay cho CTE

`HAVING` không phải cách né quy tắc này. Nếu cần lọc theo kết quả LAG/LEAD, hãy tạo một query level bên ngoài, hoặc một cấu trúc tương đương, để cột window trở thành dữ liệu đầu vào thông thường của bước lọc tiếp theo.

## 34. Không lồng trực tiếp các window function

Ví dụ không hợp lệ:

~~~sql
-- Không viết:
-- SUM(
--     CASE WHEN sold_on - LAG(sold_on) OVER (...) > 1
--          THEN 1 ELSE 0 END
-- ) OVER (...)
~~~

PostgreSQL không cho lồng một lời gọi window function **trực tiếp** bên trong đối số của một window function khác ở cùng query level.

Trong bài toán sessionization và gaps/islands, chúng ta đã dùng các CTE:

~~~text
Bước 1: LAG(timestamp) -> previous_timestamp

Bước 2: CASE -> new_session_flag

Bước 3: SUM(new_session_flag) OVER (...) -> session_number
~~~

Tách bước làm semantics rõ và tránh lỗi cú pháp.

Không cần tạo bảng vật lý cho từng bước; CTE/subquery là đủ trong nhiều trường hợp.

## 35. GROUP BY trước rồi mới so sánh giữa các nhóm thời gian

Nhiều bảng transaction có **nhiều đơn trong cùng một ngày**. Không thể dùng `LAG(amount)` trực tiếp trên từng dòng transaction rồi gọi đó là “doanh thu ngày trước” — như vậy chỉ so sánh **hai giao dịch liền nhau**.

Cần tổng hợp theo ngày trước:

~~~sql
WITH transactions(store_id, sold_on, amount) AS (
    VALUES
        ('HCM'::TEXT, DATE '2026-03-01', 30.00::NUMERIC),
        ('HCM', DATE '2026-03-01', 70.00::NUMERIC),
        ('HCM', DATE '2026-03-02', 50.00::NUMERIC),
        ('HCM', DATE '2026-03-02', 80.00::NUMERIC),
        ('HN',  DATE '2026-03-01', 60.00::NUMERIC)
),
daily_totals AS (
    SELECT
        store_id,
        sold_on,
        SUM(amount) AS revenue
    FROM transactions
    GROUP BY store_id, sold_on
)
SELECT
    store_id,
    sold_on,
    revenue,
    LAG(revenue) OVER (
        PARTITION BY store_id
        ORDER BY sold_on
    ) AS previous_day_revenue
FROM daily_totals
ORDER BY store_id, sold_on;
~~~

Quy trình logic:

1. Giao dịch → tổng hợp thành một hàng/ngày/cửa hàng.
2. Các ngày đã tổng hợp → so sánh với ngày có hàng trước.
3. Nếu cần **đúng ngày lịch**, thêm calendar grid trước bước LAG như mục 22.

### 35.1. Định nghĩa “kỳ trước” phải rõ

“Tháng trước” có thể mang nhiều nghĩa:

- Tháng lịch trước đó.
- Kỳ báo cáo có dữ liệu ngay trước.
- 30 ngày trước.
- 1 hàng trong bảng tổng hợp theo tháng trước đó.
- Tháng trước đã chốt sổ.

LAG chỉ làm việc theo **hàng của tập đã đưa vào window**, không tự định nghĩa kỳ cho ứng dụng. Nên tổng hợp đúng grain rồi áp dụng LAG.

## 36. Điều kiện WHERE có thể thay đổi hàng “liền trước”

Một lỗi tinh vi: lọc dữ liệu **trước** khi tính window làm chuỗi hàng bị đứt.

Ví dụ chỉ giữ ngày có revenue lớn hơn 100 trước khi gọi LAG:

~~~sql
SELECT
    store_id,
    sold_on,
    revenue,
    LAG(revenue) OVER (
        PARTITION BY store_id
        ORDER BY sold_on
    ) AS previous_in_filtered_set
FROM window_lab.daily_sales
WHERE revenue > 100
ORDER BY store_id, sold_on;
~~~

Với HCM, ngày 03-05 doanh thu 80 bị loại, nên tại ngày 03-06, LAG đọc ngày 03-03 doanh thu 130, **không phải hàng ghi nhận ngay trước trong toàn bộ dữ liệu là 03-05 doanh thu 80**.

Nếu yêu cầu “tìm ngày doanh thu >100 rồi hiển thị doanh thu **ngày ghi nhận trước thực sự**”, phải tính trước rồi lọc:

~~~sql
WITH compared AS (
    SELECT
        store_id,
        sold_on,
        revenue,
        LAG(revenue) OVER (
            PARTITION BY store_id
            ORDER BY sold_on
        ) AS previous_revenue
    FROM window_lab.daily_sales
)
SELECT *
FROM compared
WHERE revenue > 100
ORDER BY store_id, sold_on;
~~~

Đây là khác biệt lớn:

- **Filter trước LAG:** so sánh những hàng còn lại sau khi lọc.
- **LAG trước filter:** so sánh trong tập gốc rồi chọn những hàng cần hiển thị.

Cả hai có thể hợp lệ, nhưng trả lời **hai câu hỏi khác nhau**.

## 37. Lọc theo khoảng thời gian và dữ liệu biên

Giả sử giao diện chỉ hiển thị từ 2026-03-05, nhưng vẫn muốn doanh thu trước đó để tính biến động cho ngày đầu trong phạm vi.

Nếu viết:

~~~sql
SELECT
    sold_on,
    revenue,
    LAG(revenue) OVER (
        ORDER BY sold_on
    ) AS previous_revenue
FROM window_lab.daily_sales
WHERE
    store_id = 'HCM'
    AND sold_on >= DATE '2026-03-05'
ORDER BY sold_on;
~~~

thì LAG của 03-05 trả NULL vì **các hàng trước ngày 03-05 đã bị WHERE loại khỏi đầu vào window**.

Cách giữ ngữ nghĩa “trước trong toàn bộ lịch sử” là tính window trên chuỗi đầy đủ, sau đó lọc bên ngoài:

~~~sql
WITH compared AS (
    SELECT
        store_id,
        sold_on,
        revenue,
        LAG(revenue) OVER (
            PARTITION BY store_id
            ORDER BY sold_on
        ) AS previous_revenue
    FROM window_lab.daily_sales
    WHERE store_id = 'HCM'
)
SELECT *
FROM compared
WHERE sold_on >= DATE '2026-03-05'
ORDER BY sold_on;
~~~

Với dữ liệu lớn, tính window trên toàn bộ lịch sử mỗi lần không phải lúc nào cũng tối ưu. Có thể:

- Tìm **một hàng trước mốc bắt đầu** rồi UNION với tập phạm vi để tính window.
- Dùng `LATERAL` để tìm previous row phù hợp qua index.
- Dùng bảng tổng hợp theo kỳ đã chuẩn hóa.
- Lựa chọn chiến lược dựa trên số lượng hàng và index.

Nhưng mọi tối ưu phải giữ đúng semantics của việc “hàng trước” được xác định trên **tập dữ liệu nào**.

## 38. LEAD trong khoảng được lọc cũng có vấn đề biên

Tương tự LAG, khi giới hạn `sold_on <= DATE '2026-03-03'` **trước** phép LEAD, ngày 03-03 có thể trông như hàng cuối và next_revenue trả NULL, dù toàn bộ bảng còn ngày 03-05.

Nếu muốn “hàng tiếp theo trong lịch sử” thì tính LEAD trên tập phù hợp trước rồi mới lọc thời gian hiển thị.

Ví dụ:

~~~sql
WITH with_next AS (
    SELECT
        store_id,
        sold_on,
        revenue,
        LEAD(sold_on) OVER (
            PARTITION BY store_id
            ORDER BY sold_on
        ) AS next_recorded_date
    FROM window_lab.daily_sales
)
SELECT *
FROM with_next
WHERE
    store_id = 'HCM'
    AND sold_on <= DATE '2026-03-03'
ORDER BY sold_on;
~~~

Ngày 03-03 hiển thị `next_recorded_date = 2026-03-05` vì LEAD được tính trước bước lọc ngày của query ngoài.

## 39. LAG, LEAD hay self JOIN?

Cùng một câu hỏi đôi khi có nhiều hướng SQL.

### 39.1. LAG/LEAD

~~~sql
SELECT
    store_id,
    sold_on,
    revenue,
    LAG(revenue) OVER (
        PARTITION BY store_id
        ORDER BY sold_on
    ) AS previous_revenue
FROM window_lab.daily_sales;
~~~

Phù hợp với **hàng trước theo một thứ tự**.

### 39.2. JOIN đúng ngày lịch trước

~~~sql
SELECT
    cur.store_id,
    cur.sold_on,
    cur.revenue,
    prev.revenue AS yesterday_revenue
FROM window_lab.daily_sales AS cur
LEFT JOIN window_lab.daily_sales AS prev
    ON prev.store_id = cur.store_id
   AND prev.sold_on = cur.sold_on - 1
ORDER BY cur.store_id, cur.sold_on;
~~~

Phù hợp với **ngày trước chính xác**, không phải bản ghi tồn tại ngay trước.

### 39.3. LATERAL tìm hàng trước gần nhất

~~~sql
SELECT
    cur.store_id,
    cur.sold_on,
    cur.revenue,
    prev.sold_on AS previous_recorded_day,
    prev.revenue AS previous_revenue
FROM window_lab.daily_sales AS cur
LEFT JOIN LATERAL (
    SELECT
        p.sold_on,
        p.revenue
    FROM window_lab.daily_sales AS p
    WHERE p.store_id = cur.store_id
      AND p.sold_on < cur.sold_on
    ORDER BY p.sold_on DESC
    LIMIT 1
) AS prev ON TRUE
ORDER BY cur.store_id, cur.sold_on;
~~~

Có thể thuận tiện khi chỉ cần **một số hàng hiện tại đã được lọc rất hẹp**, muốn lookup hàng trước bằng index mà không tính window trên một partition lớn.

### 39.4. Cách chọn

| Câu hỏi | Cách ưu tiên cân nhắc |
|---|---|
| Giá trị của hàng đứng trước theo thứ tự | `LAG` |
| Giá trị của hàng tiếp theo theo thứ tự | `LEAD` |
| Giá trị đúng ngày hôm qua | JOIN theo `sold_on - 1` hoặc calendar |
| Một hàng hiện tại ít nhưng lịch sử rất lớn | `LATERAL` lookup với index, cân nhắc kế hoạch |
| So sánh liên tục nhiều hàng của một nhóm | `LAG`/`LEAD` thường rõ ràng |
| Cần bỏ qua NULL để lấy giá trị gần nhất | Cần thiết kế thêm, không mặc định LAG |
| Nhiều tính toán theo hàng liền kề | CTE + named WINDOW |
| Phân loại đoạn liên tiếp hoặc phiên | LAG + marker + running SUM |

Không có công cụ tốt nhất trong mọi trường hợp. Chọn theo **nghĩa của “liền kề”** trước, rồi đánh giá chi phí.

## 40. Window function và index PostgreSQL

Window query thường yêu cầu tổ chức đầu vào theo:

~~~sql
PARTITION BY store_id
ORDER BY sold_on
~~~

Một index B-tree có cùng thứ tự khóa có thể hỗ trợ:

~~~sql
CREATE INDEX idx_daily_sales_store_date
ON window_lab.daily_sales (store_id, sold_on);
~~~

Trong bảng demo, primary key `(store_id, sold_on)` **đã có B-tree index tương ứng**, vì vậy không cần tạo thêm index trùng lặp chỉ để thực hành.

Với bảng `device_event`, một index phù hợp cho chuỗi sự kiện:

~~~sql
CREATE INDEX idx_device_event_order
ON window_lab.device_event (
    device_id,
    recorded_at,
    event_id
);
~~~

### 40.1. Index không bảo đảm luôn tránh Sort

PostgreSQL có thể sử dụng `Index Scan` theo thứ tự có ích, nhưng cũng có thể chọn:

- Sequential scan + Sort.
- Index scan + phần xử lý khác.
- Incremental Sort trong trường hợp phù hợp.
- Một kế hoạch gồm nhiều node WindowAgg/Sort nếu có nhiều window specifications.

Tùy số hàng, filter, thống kê, kích thước cột và phiên bản PostgreSQL.

Không kết luận “có index nên query luôn O(1)” hoặc “LAG tự nhanh hơn JOIN”. Để đọc một partition dài, engine vẫn phải xử lý các hàng liên quan.

### 40.2. Kiểm tra bằng EXPLAIN

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    device_id,
    event_id,
    recorded_at,
    LAG(state) OVER (
        PARTITION BY device_id
        ORDER BY recorded_at, event_id
    ) AS previous_state
FROM window_lab.device_event
ORDER BY device_id, recorded_at, event_id;
~~~

Quan sát:

- Node `WindowAgg`.
- Có node `Sort` không.
- `Index Scan`, `Index Only Scan` hoặc `Seq Scan`.
- Số hàng được xử lý.
- Thời gian thực, buffers hit/read và hoạt động spill nếu có.
- Có nhiều sort khi dùng các window ORDER BY khác nhau hay không.

`EXPLAIN ANALYZE` **thực thi SQL**. Ở ví dụ này là SELECT. Không thử với DML production mà không hiểu tác động.

## 41. Hiệu năng trên partition lớn

Khi mỗi `device_id` có hàng triệu event, cần nghĩ đến:

- Số hàng của mỗi partition.
- Index theo các cột partition/sort.
- WHERE có thể thu hẹp **đúng** tập cần phân tích hay không.
- Bộ nhớ cho việc sắp xếp và xử lý window.
- Số window specifications khác nhau.
- Kích thước cột được SELECT.
- Có thể tính trước bảng tổng hợp theo ngày/giờ không.
- Có cần chỉ đọc một số event hiện tại và lookup phần trước qua index không.

Không tăng cấu hình `work_mem` bừa bãi cho toàn server chỉ vì một query window spill ra đĩa. Mỗi query có thể có nhiều phép sort/hash và nhiều session đồng thời; tăng vô hạn sẽ làm tăng áp lực bộ nhớ.

Nếu query thường xuyên hỏi cùng một metric, có thể cân nhắc bảng tổng hợp hoặc pipeline tính trước có chiến lược cập nhật và xử lý dữ liệu đến trễ. Tuy nhiên, việc cache/tính trước làm phát sinh bài toán đồng bộ khi sự kiện cũ được sửa hoặc bổ sung.

## 42. MVCC và dữ liệu thay đổi đồng thời

Ở mức isolation mặc định `READ COMMITTED`, PostgreSQL thực thi một SELECT trên snapshot nhất quán theo quy tắc statement. Trong phạm vi **một statement** như:

~~~sql
SELECT
    device_id,
    event_id,
    LAG(state) OVER (...) AS previous_state
FROM window_lab.device_event;
~~~

kết quả LAG/LEAD được tính từ **tập hàng nhìn thấy và thỏa điều kiện của statement đó**.

Nhưng khi chạy lại cùng query ở một thời điểm khác:

- Một event mới có thể được chèn vào giữa hai event cũ.
- Một event cũ có thể bị xóa hoặc đổi timestamp.
- Một phép sửa trạng thái có thể thay đổi transition history.
- Hai transaction khác nhau có thể commit ở thứ tự khác timestamp nghiệp vụ.

Vì vậy “hàng liền trước” phụ thuộc vào **ảnh dữ liệu và thứ tự** của từng lần query.

### 42.1. Late-arriving events thay đổi kết quả lịch sử

Giả sử ban đầu có:

~~~text
08:00 online
08:20 offline
~~~

LAG của 08:20 là online lúc 08:00. Nếu sau đó ETL thêm một event lúc 08:10:

~~~text
08:00 online
08:10 maintenance
08:20 offline
~~~

LAG của 08:20 bây giờ là maintenance lúc 08:10.

Đây là hành vi đúng của phép phân tích trên dữ liệu mới; không phải PostgreSQL tính sai. Nếu báo cáo đã xuất theo sự kiện đến trước cần bất biến, hệ thống phải định nghĩa version/snapshot, cửa sổ chốt dữ liệu hoặc quy tắc xử lý late data.

## 43. LAG/LEAD có làm thay đổi số hàng không?

Trong một truy vấn thông thường, `LAG`/`LEAD` là hàm cửa sổ trả một giá trị ứng với mỗi hàng đầu vào và **không tự nhân hoặc gộp số hàng**.

Nếu kết quả bị tăng số hàng, cần kiểm tra:

- JOIN với bảng có nhiều hàng khớp.
- CROSS JOIN.
- generate_series.
- UNION ALL.
- Cấu trúc dữ liệu nguồn bị trùng khóa mà ứng dụng không dự tính.

Nếu kết quả ít hàng hơn, kiểm tra:

- WHERE trước/sau window.
- INNER JOIN.
- GROUP BY.
- DISTINCT.
- LIMIT.

LAG/LEAD không tự lọc bỏ hàng đầu có previous value NULL. Muốn loại hàng đầu, phải đưa điều kiện vào query ngoài, ví dụ `previous_event_id IS NOT NULL`.

## 44. Những lỗi thường gặp

### Lỗi 1 — Quên ORDER BY trong OVER

Không có thứ tự rõ thì “hàng trước” không mang ý nghĩa ổn định theo thời gian.

**Cách xử lý:** khai báo ORDER BY đúng nghiệp vụ, có tie-breaker nếu cần.

### Lỗi 2 — Không có PARTITION BY

LAG của cửa hàng này có thể đọc hàng của cửa hàng khác.

**Cách xử lý:** partition theo khóa nhóm cần so sánh.

### Lỗi 3 — Dùng ngày nhưng hiểu offset là số ngày

`LAG(x,2)` lùi hai hàng, không phải hai ngày.

**Cách xử lý:** dùng calendar hoặc JOIN theo mốc thời gian chính xác.

### Lỗi 4 — Quên dữ liệu có ngày thiếu

LAG ở 03-05 đọc 03-03 vì không có 03-04.

**Cách xử lý:** phân biệt recorded previous và calendar previous.

### Lỗi 5 — Chỉ ORDER BY timestamp khi nhiều hàng cùng thời điểm

Thứ tự peer rows không xác định.

**Cách xử lý:** thêm khóa ổn định và duy nhất.

### Lỗi 6 — Đổi ASC thành DESC mà không đổi ý nghĩa kết quả

LAG có thể đọc sự kiện mới hơn thay vì cũ hơn.

**Cách xử lý:** hiểu “trước” là trước **theo ORDER BY trong OVER**.

### Lỗi 7 — Dùng default=0 như bằng chứng “không có doanh thu”

Hàng đầu không có quan sát trước không đồng nghĩa doanh thu trước là 0.

**Cách xử lý:** giữ NULL hoặc mô tả rõ chính sách thay thế.

### Lỗi 8 — Không phân biệt NULL của giá trị trước với thiếu hàng trước

Cả hai có thể làm LAG(value) trả NULL.

**Cách xử lý:** LAG trên khóa NOT NULL để xác định sự tồn tại của hàng trước.

### Lỗi 9 — Cho rằng LAG tự bỏ qua NULL

Hàng trước có giá trị NULL vẫn là hàng trước.

**Cách xử lý:** thiết kế giải pháp tìm non-NULL gần nhất khi thật sự cần.

### Lỗi 10 — Chia cho doanh thu trước bằng 0

Có thể tạo lỗi chia 0 trong phép tính phần trăm.

**Cách xử lý:** dùng `NULLIF(previous_revenue,0)` và chính sách hiển thị rõ ràng.

### Lỗi 11 — Dùng LAG trong WHERE

Window function không dùng trực tiếp ở WHERE cùng query level.

**Cách xử lý:** tính trong CTE/subquery, lọc query ngoài.

### Lỗi 12 — Lồng một window function vào window function khác

Ví dụ SUM(LAG(...) OVER(...)) OVER(...) không hợp lệ cùng cấp.

**Cách xử lý:** tách thành nhiều bước query.

### Lỗi 13 — Lọc trước khi tính window ngoài ý muốn

LAG chỉ nhìn những hàng còn sau WHERE, có thể bỏ qua hàng thực sự liền trước.

**Cách xử lý:** xác định tập gốc; tính trước rồi lọc ngoài nếu muốn so sánh với lịch sử đầy đủ.

### Lỗi 14 — Lọc thời gian làm mất dữ liệu ở biên

Hàng đầu phạm vi báo cáo có LAG NULL dù có hàng trước ngoài phạm vi.

**Cách xử lý:** tính trên lịch sử phù hợp hoặc nạp một hàng biên trước đó.

### Lỗi 15 — Dùng LEAD để tính thời gian trạng thái nhưng tự kết thúc hàng cuối

Không có next_at thì không có mốc kết thúc thật.

**Cách xử lý:** định nghĩa rõ trạng thái “ongoing”, mốc chốt báo cáo hoặc giới hạn suy luận.

### Lỗi 16 — Đánh đồng ORDER BY ngoài cùng với ORDER BY trong OVER

Thứ tự trình bày có thể ngược với thứ tự dùng tính LAG.

**Cách xử lý:** đọc hai vị trí ORDER BY riêng biệt.

### Lỗi 17 — Tạo index giống hệt primary key

Tăng storage và chi phí ghi không cần thiết.

**Cách xử lý:** xem index có sẵn từ PK/UNIQUE trước khi tạo thêm.

### Lỗi 18 — Coi kết quả LAG là bất biến khi ETL đến trễ

Một event được bổ sung vào giữa chuỗi làm thay đổi previous/next của hàng khác.

**Cách xử lý:** quy định dữ liệu chốt, snapshot và xử lý late-arriving events.

### Lỗi 19 — Tính LAG trên giao dịch rồi gọi là tăng trưởng theo ngày

Một ngày có nhiều giao dịch, nên hàng trước là giao dịch trước, không phải ngày trước.

**Cách xử lý:** tổng hợp đúng grain rồi mới dùng LAG.

### Lỗi 20 — Tối ưu index mà quên semantics

Một query nhanh nhưng lọc sai tập trước khi tính window vẫn trả kết quả sai.

**Cách xử lý:** định nghĩa đúng nhóm, thời gian và thứ tự trước khi đo hiệu năng.

## 45. Quy trình xây dựng truy vấn so sánh hàng liền kề

**Bước 1 — Định nghĩa đối tượng cần so sánh.** Hai đơn, hai ngày, hai mốc giá hay hai trạng thái? Không dùng từ “trước” khi chưa có tiêu chí.

**Bước 2 — Xác định grain của dữ liệu.** Mỗi hàng là transaction, ngày, tháng, event hay snapshot?

**Bước 3 — Chọn PARTITION BY.** Theo cửa hàng, thiết bị, sản phẩm, khách hàng, tenant hoặc kết hợp các khóa.

**Bước 4 — Chọn ORDER BY.** Dùng đúng timestamp/sequence nghiệp vụ; thêm tie-breaker duy nhất.

**Bước 5 — Xác định offset.** Một hàng trước, hai hàng trước, hay đúng một khoảng thời gian trước? Nếu là khoảng thời gian, kiểm tra có cần calendar/JOIN.

**Bước 6 — Xử lý NULL và boundary.** Hàng đầu/cuối, giá trị NULL hợp lệ, default và chia cho 0.

**Bước 7 — Tính trong CTE nếu cần lọc/aggregate tiếp.** Tránh dùng window trực tiếp trong WHERE hoặc lồng window.

**Bước 8 — Xác nhận phạm vi WHERE.** Lọc trước hay sau LAG sẽ cho những câu hỏi khác nhau.

**Bước 9 — Đo truy vấn khi dữ liệu lớn.** Xem index theo partition/order và `EXPLAIN (ANALYZE, BUFFERS)`.

**Bước 10 — Nêu rõ hành vi khi dữ liệu thay đổi.** Một event bổ sung, một timestamp sửa hoặc trạng thái cập nhật có thể thay đổi kết quả lân cận.

Đây là cách tiếp cận nhất quán cho nhiều bài toán SQL nâng cao, không chỉ riêng dữ liệu doanh thu.

## 46. Bài tập thực hành

### Bài 1 — LAG đơn giản

Viết query trả `store_id, sold_on, revenue` và doanh thu của hàng ghi nhận trước trong cùng cửa hàng.

**Gợi ý:** `LAG(revenue) OVER (PARTITION BY store_id ORDER BY sold_on)`.

### Bài 2 — LEAD đơn giản

Viết query trả doanh thu và ngày ghi nhận của hàng tiếp theo trong cùng cửa hàng.

**Gợi ý:** `LEAD(revenue)` và `LEAD(sold_on)` với cùng window definition.

### Bài 3 — Hàng đầu partition

Giá trị `LAG(revenue)` của HCM ngày 03-01 là gì? Vì sao?

**Gợi ý:** NULL vì không có hàng trước trong partition.

### Bài 4 — Hàng cuối partition

Giá trị `LEAD(revenue)` của HN ngày 03-06 là gì?

**Gợi ý:** NULL vì không có hàng sau.

### Bài 5 — Ngày bị thiếu

Với HCM ngày 03-05, `LAG(sold_on)` trả ngày nào? Có phải ngày 03-04 không?

**Gợi ý:** trả 03-03, vì 03-04 không có hàng.

### Bài 6 — Chênh lệch doanh thu

Tính `revenue - previous_revenue` của HCM ngày 03-06.

**Gợi ý:** 180 - 80 = 100.

### Bài 7 — Phần trăm biến động

Tính tỷ lệ tăng doanh thu HCM 03-02 so với hàng trước.

**Gợi ý:** (130 - 100) / 100 × 100 = 30%.

### Bài 8 — Offset 2

HCM ngày 03-05, `LAG(revenue,2)` là bao nhiêu? Đây có phải doanh thu hai ngày trước không?

**Gợi ý:** 130 từ hàng 03-02; offset đo hàng, không đo ngày.

### Bài 9 — Default

Tại sao `LAG(revenue,1,0)` và `COALESCE(LAG(revenue),0)` không luôn tương đương khi cột revenue có thể NULL?

**Gợi ý:** default chỉ dùng khi không có hàng offset; COALESCE còn thay NULL của hàng tồn tại.

### Bài 10 — PARTITION BY

Điều gì xảy ra khi xóa `PARTITION BY store_id` khỏi query so sánh doanh thu theo ngày?

**Gợi ý:** chuỗi của các cửa hàng bị trộn; previous row có thể thuộc cửa hàng khác.

### Bài 11 — ORDER BY DESC

Với HCM 03-05, `LAG(revenue) OVER (ORDER BY sold_on DESC)` trả bao nhiêu?

**Gợi ý:** giá trị của ngày mới hơn là 03-06, tức 180.

### Bài 12 — Timestamp trùng

Hai event sensor-A cùng mốc 08:05. Vì sao cần `ORDER BY recorded_at,event_id`?

**Gợi ý:** timestamp riêng không phân định thứ tự của hai hàng.

### Bài 13 — Trạng thái thay đổi

Tìm những event có `state` khác state của event trước, không tính event đầu.

**Gợi ý:** CTE LAG(state), sau đó `state IS DISTINCT FROM previous_state` và kiểm tra previous_event_id.

### Bài 14 — NULL là giá trị của hàng trước

Event sensor-A số 5 có previous_temperature là gì? Nó có nghĩa là không có event trước không?

**Gợi ý:** event số 4 tồn tại nhưng temperature NULL; cần LAG(event_id) để phân biệt.

### Bài 15 — Phát hiện gap

Viết SQL tìm các cặp event liên tiếp cách nhau hơn 10 phút.

**Gợi ý:** LAG(recorded_at), rồi lọc `recorded_at - previous_at > INTERVAL '10 minutes'` ở query ngoài.

### Bài 16 — Tìm ngày thiếu

Viết query đếm số ngày trống giữa hai hàng liên tiếp của HN.

**Gợi ý:** `sold_on - previous_day - 1` khi hiệu ngày lớn hơn 1.

### Bài 17 — Calendar grid

Nếu muốn doanh thu “đúng ngày hôm qua”, phải làm gì khi một ngày không có hàng?

**Gợi ý:** tạo lịch bằng `generate_series`, LEFT JOIN và LAG, hoặc JOIN trực tiếp theo ngày - 1.

### Bài 18 — Thời gian trạng thái

Dùng LEAD để tính thời lượng từ event hiện tại đến event tiếp theo của mỗi device.

**Gợi ý:** `LEAD(recorded_at) - recorded_at`, giữ NULL ở event cuối nếu chưa có mốc kết thúc.

### Bài 19 — Sessionization

Với ngưỡng 30 phút, sensor-A có mấy phiên theo dữ liệu mẫu?

**Gợi ý:** 2 phiên; event 5 cách event 4 là 70 phút.

### Bài 20 — Gaps and islands

Đối với HCM, các ngày nào thuộc hai đảo ngày liên tiếp?

**Gợi ý:** đảo 1 = 03-01 đến 03-03; đảo 2 = 03-05 đến 03-06.

### Bài 21 — Giá tại thời điểm

Dùng LEAD(effective_at) tạo khoảng hiệu lực giá BOOK. Giá tại 2026-03-01 là bao nhiêu?

**Gợi ý:** 135000.00.

### Bài 22 — WHERE và window

Vì sao không thể đặt `LAG(revenue) OVER (...)` trực tiếp vào WHERE? Hãy viết lại bằng CTE.

**Gợi ý:** tính previous_revenue ở CTE, lọc ở SELECT bên ngoài.

### Bài 23 — Lọc trước/sau

Với HCM ngày 03-06, nếu lọc `WHERE revenue > 100` trước khi LAG, previous_revenue khác thế nào so với tính LAG toàn bộ rồi lọc?

**Gợi ý:** khi lọc trước, ngày 03-05 revenue 80 bị loại; hàng trước thành 03-03 revenue 130. Khi tính trên toàn bộ, hàng trước là 03-05 revenue 80.

### Bài 24 — Window frame

Nếu LAG dùng `ROWS BETWEEN CURRENT ROW AND CURRENT ROW`, nó có tự thành NULL với mọi hàng không?

**Gợi ý:** không; LAG định vị theo partition và thứ tự, không bị hạn chế theo frame như LAST_VALUE.

### Bài 25 — Index và EXPLAIN

Với bảng device_event, đề xuất index phục vụ `PARTITION BY device_id ORDER BY recorded_at,event_id` và kiểm tra kế hoạch.

**Gợi ý:** B-tree `(device_id,recorded_at,event_id)`; dùng `EXPLAIN (ANALYZE,BUFFERS)` trên SELECT.

### Bài 26 — Báo cáo theo tháng

Bảng giao dịch có nhiều hàng một ngày. Vì sao không dùng LAG(amount) trực tiếp để tính doanh thu ngày trước?

**Gợi ý:** phải GROUP BY đến grain ngày/tháng trước rồi mới LAG.

### Bài 27 — Hai window có thứ tự khác nhau

Nếu previous_state dùng ORDER BY recorded_at còn previous_temperature dùng ORDER BY recorded_at,event_id, có thể phát sinh lỗi gì?

**Gợi ý:** hai giá trị có thể thuộc hai hàng trước khác nhau khi timestamp trùng.

### Bài 28 — Named WINDOW

Viết query dùng `WINDOW event_order AS (...)` để tính `LAG(state)` và `LEAD(state)` cho mỗi thiết bị.

**Gợi ý:** cả hai dùng `OVER event_order`.

### Bài 29 — Xử lý dữ liệu đến muộn

Một event 08:10 được thêm sau khi đã phân tích chuỗi 08:00 → 08:20. Tại sao LAG của 08:20 thay đổi?

**Gợi ý:** hàng liền trước đã thay đổi trong snapshot dữ liệu mới.

### Bài 30 — LAG hay JOIN?

Đề bài yêu cầu doanh thu chính xác ngày hôm qua, kể cả khi bảng chỉ lưu ngày có đơn. Nên dùng LAG trực tiếp hay JOIN ngày lịch?

**Gợi ý:** JOIN theo ngày - 1 hoặc calendar; LAG trực tiếp chỉ biết hàng ghi nhận trước.

## 47. Tổng kết

- **`LAG(value) OVER (...)`** đọc giá trị ở hàng trước; **`LEAD(value) OVER (...)`** đọc giá trị ở hàng sau.
- “Trước/sau” phụ thuộc **`ORDER BY` trong cửa sổ**, không mặc định là quá khứ hoặc tương lai theo thời gian.
- **`PARTITION BY`** chia chuỗi phân tích độc lập theo khách hàng, thiết bị, cửa hàng hoặc các khóa nghiệp vụ khác.
- **Thứ tự phải xác định**: khi nhiều hàng trùng timestamp, thêm tie-breaker duy nhất nếu cần.
- Offset mặc định là 1 **hàng**, không phải một ngày hay một đơn vị thời gian. Offset 2 đọc hàng cách hai vị trí.
- Default được dùng khi **không có hàng tại offset**, không tự thay giá trị NULL của một hàng tồn tại.
- **`NULL` tại hàng đầu/cuối** thường mang ý nghĩa thiếu quan sát; không mặc định thay bằng 0 hoặc một timestamp giả.
- Có thể dùng LAG để tính **delta, phần trăm thay đổi, trạng thái tăng/giảm, transition, time gap và gaps/islands**.
- Có thể dùng LEAD để tạo **thời lượng đến sự kiện tiếp theo** hoặc các khoảng hiệu lực `[valid_from, valid_until)`.
- Với bài toán **đúng ngày lịch hôm qua** và dữ liệu thiếu ngày, cần dùng **calendar hoặc JOIN theo ngày**, không chỉ LAG của hàng tồn tại trước.
- **Window functions không đặt trực tiếp trong WHERE/HAVING cùng query level**, và không lồng trực tiếp những window functions vào nhau; hãy tách thành CTE/subquery.
- **Lọc trước LAG** và **lọc sau LAG** có thể trả về hai ý nghĩa khác nhau, đặc biệt ở giới hạn ngày hoặc khi loại những hàng dữ liệu thấp.
- **LAG/LEAD dựa trên partition và thứ tự, không phải window frame hiện tại** theo cách các hàm FIRST_VALUE/LAST_VALUE sử dụng frame.
- Index theo `PARTITION BY` và `ORDER BY` có thể hỗ trợ kế hoạch, nhưng cần đo bằng **`EXPLAIN (ANALYZE, BUFFERS)`** trên dữ liệu phù hợp.
- Khi event đến trễ hoặc dữ liệu bị sửa, “hàng liền kề” cũng có thể thay đổi: PostgreSQL tính theo **tập hàng nhìn thấy ở thời điểm câu SQL**, không tự bảo đảm lịch sử bất biến.

Điểm quan trọng nhất của `LAG` và `LEAD` không phải chỉ là cú pháp ngắn hơn self JOIN. Chúng buộc người thiết kế truy vấn diễn đạt rõ **đang so sánh những hàng nào, trong nhóm nào, theo thứ tự nào và trên tập dữ liệu đã lọc như thế nào**. Khi các quyết định này đúng, PostgreSQL có thể tính toán biến động, phát hiện chuyển trạng thái và phân tích chuỗi thời gian trực tiếp bằng SQL một cách dễ hiểu và có thể mở rộng.
