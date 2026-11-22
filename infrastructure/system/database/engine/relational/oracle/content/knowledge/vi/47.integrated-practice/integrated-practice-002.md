# Viết báo cáo doanh thu có tổng phụ, xếp hạng và so sánh theo thời gian

Báo cáo doanh thu thường cần trả lời nhiều câu hỏi trong cùng một kết quả: doanh thu từng vùng hoặc nhân viên là bao nhiêu, tổng của mỗi tháng là bao nhiêu, đơn vị nào đứng đầu, và kết quả thay đổi thế nào so với tháng trước hoặc cùng kỳ năm trước. Oracle SQL có thể thực hiện các phép tổng hợp này bằng `GROUP BY`, `ROLLUP`, `GROUPING SETS` và các hàm phân tích như `RANK`, `DENSE_RANK`, `ROW_NUMBER`, `LAG`.

Điểm quan trọng khi ghép các kỹ thuật là xác định đúng cấp dữ liệu. Hãy tổng hợp doanh thu ở cấp cần báo cáo trước, sau đó mới xếp hạng hoặc so sánh theo thời gian. Tổng phụ phải được nhận diện rõ để không bị đưa vào phép xếp hạng như một đơn vị kinh doanh. Khi so sánh theo tháng, cần tạo đủ các kỳ kể cả tháng không có giao dịch để tháng liền trước thực sự là tháng lịch liền trước.

## 1. Xác định quy tắc tính doanh thu

Trước khi viết SQL, thống nhất định nghĩa doanh thu. Cùng một bảng giao dịch có thể cho ra nhiều con số khác nhau tùy quy tắc ghi nhận.

Ví dụ bài thực hành sử dụng mô hình đơn giản:

| Bảng | Cột chính | Vai trò |
|---|---|---|
| `SALES_ORDER` | `ORDER_ID`, `ORDER_DATE`, `STATUS`, `REGION_ID`, `CURRENCY_CODE` | Thông tin đơn hàng và thời điểm ghi nhận |
| `SALES_ORDER_LINE` | `ORDER_ID`, `LINE_NO`, `PRODUCT_ID`, `QUANTITY`, `UNIT_PRICE`, `DISCOUNT_AMOUNT` | Giá trị từng dòng hàng |
| `SALES_REGION` | `REGION_ID`, `REGION_NAME` | Danh mục vùng kinh doanh |

Giả định cho các ví dụ:

- Chỉ tính đơn hàng có `STATUS = 'COMPLETED'`.
- `ORDER_DATE` là ngày ghi nhận doanh thu trong báo cáo.
- `DISCOUNT_AMOUNT` là số tiền giảm trừ của cả dòng hàng, không phải tỷ lệ phần trăm.
- Doanh thu dòng = số lượng × đơn giá − số tiền giảm trừ.
- Ví dụ chưa tính thuế, phí giao hàng, hoàn tiền hoặc điều chỉnh sau bán.
- Mỗi báo cáo chỉ cộng một loại tiền tệ; nếu có nhiều loại tiền, phải nhóm theo tiền tệ hoặc quy đổi theo tỷ giá được phê duyệt.

Công thức:

[
\text{Revenue} = \sum (\text{QUANTITY} \times \text{UNIT\_PRICE} - \text{DISCOUNT\_AMOUNT})
\]

Không nên chỉ lấy `SUM(UNIT_PRICE)` vì mỗi dòng có thể có số lượng lớn hơn một và có chiết khấu. Cũng không nên tính doanh thu trên bảng header rồi join trực tiếp với bảng line nếu header amount đã là tổng đơn hàng: phép join có thể nhân bản giá trị header theo số dòng chi tiết.

### 1.1. Kiểm tra cấp dữ liệu và quan hệ join

Quan hệ phổ biến:

```text
SALES_ORDER 1 ----- n SALES_ORDER_LINE
      |
      +----- 1 SALES_REGION
```

Một đơn hàng có nhiều dòng hàng, nhưng chỉ thuộc một vùng trong mô hình này. Nếu join thêm bảng khuyến mãi, thanh toán hoặc lịch sử trạng thái có nhiều dòng cho mỗi đơn hàng, cần tổng hợp bảng đó trước hoặc xác định đúng bản ghi cần lấy. Nếu không, doanh thu có thể bị nhân lên.

### 1.2. Chọn ngày ghi nhận

`ORDER_DATE` trong ví dụ là ngày ghi nhận doanh thu. Hệ thống thực tế có thể phải dùng ngày xuất hóa đơn, ngày giao hàng, ngày hoàn tất dịch vụ hoặc ngày ghi sổ kế toán. Hãy chọn đúng cột ngày theo chính sách tài chính.

Nếu cột là `TIMESTAMP WITH TIME ZONE`, cần thống nhất múi giờ báo cáo trước khi gom nhóm theo ngày/tháng. Một giao dịch gần nửa đêm có thể thuộc tháng khác nếu chuyển từ UTC sang múi giờ địa phương. Không cắt bỏ thông tin timezone trước khi xác định quy tắc nghiệp vụ.

## 2. Tính doanh thu cơ bản bằng GROUP BY

Trước tiên, tính doanh thu theo vùng:

```sql
SELECT r.region_id,
       r.region_name,
       SUM(
         l.quantity * l.unit_price
         - NVL(l.discount_amount, 0)
       ) AS revenue
FROM sales_order o
JOIN sales_order_line l
  ON l.order_id = o.order_id
JOIN sales_region r
  ON r.region_id = o.region_id
WHERE o.status = 'COMPLETED'
GROUP BY r.region_id, r.region_name
ORDER BY revenue DESC, r.region_id;
```

`NVL(l.discount_amount, 0)` coi chiết khấu chưa có giá trị là 0. Nếu `DISCOUNT_AMOUNT` có thể âm hoặc dữ liệu không hợp lệ, cần kiểm tra ràng buộc nghiệp vụ thay vì để công thức tự che giấu dữ liệu sai.

Để tính theo tháng và vùng, thêm biểu thức tháng vào cả danh sách chọn và `GROUP BY`:

```sql
SELECT TRUNC(o.order_date, 'MM') AS month_start,
       r.region_id,
       r.region_name,
       SUM(
         l.quantity * l.unit_price
         - NVL(l.discount_amount, 0)
       ) AS revenue
FROM sales_order o
JOIN sales_order_line l
  ON l.order_id = o.order_id
JOIN sales_region r
  ON r.region_id = o.region_id
WHERE o.status = 'COMPLETED'
  AND o.order_date >= DATE '2026-01-01'
  AND o.order_date <  DATE '2027-01-01'
GROUP BY TRUNC(o.order_date, 'MM'),
         r.region_id,
         r.region_name
ORDER BY month_start, revenue DESC, r.region_id;
```

`TRUNC(date_value, 'MM')` đưa ngày về ngày đầu tháng. Dùng khoảng ngày nửa mở `>= start` và `< end` để bao gồm mọi thời điểm trong ngày cuối cùng, kể cả khi cột lưu phần giờ. Cách lọc trực tiếp trên cột ngày cũng thường thuận lợi hơn cho index hoặc partition pruning so với điều kiện `TRUNC(order_date) = ...`.

## 3. Tạo tổng phụ bằng ROLLUP và GROUPING SETS

### 3.1. ROLLUP theo tháng và vùng

`ROLLUP` tạo các cấp tổng hợp từ chi tiết lên tổng phụ và tổng cộng. Với thứ tự `ROLLUP(month_start, (region_id, region_name))`, Oracle tạo các nhóm tương đương:

1. Mỗi cặp tháng và vùng.
2. Tổng của tất cả vùng trong từng tháng.
3. Tổng cộng của toàn bộ các tháng.

Ví dụ:

```sql
WITH sales_by_region AS (
  SELECT TRUNC(o.order_date, 'MM') AS month_start,
         r.region_id,
         r.region_name,
         SUM(
           l.quantity * l.unit_price
           - NVL(l.discount_amount, 0)
         ) AS revenue
  FROM sales_order o
  JOIN sales_order_line l
    ON l.order_id = o.order_id
  JOIN sales_region r
    ON r.region_id = o.region_id
  WHERE o.status = 'COMPLETED'
    AND o.order_date >= DATE '2026-01-01'
    AND o.order_date <  DATE '2027-01-01'
  GROUP BY TRUNC(o.order_date, 'MM'),
           r.region_id,
           r.region_name
)
SELECT CASE
         WHEN GROUPING(month_start) = 1 THEN 'TONG CONG'
         WHEN GROUPING(region_name) = 1 THEN 'TONG THANG'
         ELSE 'CHI TIET VUNG'
       END AS row_type,
       month_start,
       region_name,
       SUM(revenue) AS revenue,
       GROUPING_ID(month_start, region_id, region_name) AS grouping_level
FROM sales_by_region
GROUP BY ROLLUP(month_start, (region_id, region_name))
ORDER BY month_start NULLS LAST,
         GROUPING(region_name),
         region_id;
```

Hàm `GROUPING(column)` trả về 1 khi cột bị loại khỏi cấp nhóm hiện tại để tạo tổng phụ, và 0 khi cột là một phần của nhóm chi tiết. Đây là cách phân biệt dòng tổng phụ với một dòng dữ liệu thật có giá trị `NULL`.

`GROUPING_ID(month_start, region_id, region_name)` mã hóa trạng thái grouping của các cột được truyền vào. Nó hữu ích khi báo cáo có nhiều cấp tổng hợp hoặc cần nhận diện từng loại dòng trong ứng dụng.

Thứ tự cột trong `ROLLUP` có ý nghĩa. Cú pháp `ROLLUP(month_start, (region_id, region_name))` coi mã vùng và tên vùng là một nhóm cột ghép, tạo chi tiết tháng-vùng, tổng theo tháng và tổng cộng mà không tạo thêm một cấp tổng dư theo riêng mã vùng. Nếu đảo thứ tự các cấp, các grouping set được tạo ra cũng thay đổi.

### 3.2. Dùng GROUPING SETS khi cần đúng các cấp tổng

`GROUPING SETS` cho phép chỉ định chính xác những nhóm cần tính, không nhất thiết phải lấy toàn bộ chuỗi của ROLLUP:

```sql
SELECT TRUNC(o.order_date, 'MM') AS month_start,
       r.region_name,
       SUM(
         l.quantity * l.unit_price
         - NVL(l.discount_amount, 0)
       ) AS revenue,
       GROUPING_ID(
         TRUNC(o.order_date, 'MM'),
         r.region_name
       ) AS grouping_level
FROM sales_order o
JOIN sales_order_line l
  ON l.order_id = o.order_id
JOIN sales_region r
  ON r.region_id = o.region_id
WHERE o.status = 'COMPLETED'
GROUP BY GROUPING SETS (
  (TRUNC(o.order_date, 'MM'), r.region_name),
  (TRUNC(o.order_date, 'MM')),
  ()
);
```

Các nhóm ở ví dụ là chi tiết tháng-vùng, tổng tháng và tổng cộng. Nếu cần thêm tổng riêng theo vùng nhưng không cần tổng cộng, có thể khai báo các grouping set tương ứng. `CUBE` tạo mọi tổ hợp nhóm và có thể sinh nhiều dòng hơn mức báo cáo cần; chỉ dùng khi thực sự cần phân tích mọi chiều kết hợp.

### 3.3. Đặt nhãn và sắp xếp tổng phụ

Các dòng tổng thường có giá trị `NULL` ở cột chiều đã được roll up. Không dùng riêng `NVL(region_name, 'TONG')` để nhận diện tổng vì dữ liệu thực có thể có vùng chưa gán tên. Dùng `GROUPING` để phân biệt.

Khi xuất báo cáo, có thể dùng `CASE` để đặt nhãn:

```sql
CASE
  WHEN GROUPING(region_name) = 1 THEN 'TONG THANG'
  ELSE region_name
END
```

Nếu báo cáo có tổng cộng, kiểm tra `GROUPING(month_start)` trước `GROUPING(region_name)` để dòng tổng cộng được nhận diện đúng.

## 4. Xếp hạng bằng hàm phân tích

Hàm phân tích thực hiện phép tính trên các dòng trong một nhóm mà vẫn giữ lại từng dòng. Với báo cáo doanh thu, tổng hợp trước theo tháng-vùng rồi mới xếp hạng vùng trong từng tháng.

### 4.1. Phân biệt RANK, DENSE_RANK và ROW_NUMBER

Giả sử doanh thu theo vùng trong một tháng:

| Vùng | Doanh thu | RANK | DENSE_RANK | ROW_NUMBER |
|---|---:|---:|---:|---:|
| Bắc | 500 | 1 | 1 | 1 |
| Nam | 420 | 2 | 2 | 2 |
| Trung | 420 | 2 | 2 | 3 |
| Tây | 300 | 4 | 3 | 4 |

- `RANK()` cho cùng thứ hạng khi hòa điểm và bỏ qua số hạng kế tiếp.
- `DENSE_RANK()` cho cùng thứ hạng khi hòa điểm nhưng không bỏ số.
- `ROW_NUMBER()` đánh số duy nhất từng dòng, kể cả khi doanh thu bằng nhau.

Ví dụ:

```sql
WITH region_month AS (
  SELECT TRUNC(o.order_date, 'MM') AS month_start,
         r.region_id,
         r.region_name,
         SUM(
           l.quantity * l.unit_price
           - NVL(l.discount_amount, 0)
         ) AS revenue
  FROM sales_order o
  JOIN sales_order_line l
    ON l.order_id = o.order_id
  JOIN sales_region r
    ON r.region_id = o.region_id
  WHERE o.status = 'COMPLETED'
  GROUP BY TRUNC(o.order_date, 'MM'),
           r.region_id,
           r.region_name
)
SELECT month_start,
       region_name,
       revenue,
       RANK() OVER (
         PARTITION BY month_start
         ORDER BY revenue DESC
       ) AS revenue_rank,
       DENSE_RANK() OVER (
         PARTITION BY month_start
         ORDER BY revenue DESC
       ) AS dense_revenue_rank,
       ROW_NUMBER() OVER (
         PARTITION BY month_start
         ORDER BY revenue DESC, region_id
       ) AS display_order
FROM region_month
ORDER BY month_start, display_order;
```

`PARTITION BY month_start` bắt đầu xếp hạng lại từ đầu ở mỗi tháng. `ORDER BY revenue DESC` xác định doanh thu cao nhất đứng đầu. Với `ROW_NUMBER`, thêm khóa ổn định như `region_id` để kết quả không đổi thứ tự tùy ý khi doanh thu bằng nhau.

Đối với `RANK` và `DENSE_RANK`, chỉ đưa tiêu chí hòa điểm vào `ORDER BY` nếu muốn phá hòa. Nếu thêm `region_id` vào cùng `ORDER BY`, hai vùng có cùng doanh thu sẽ không còn được xem là đồng hạng.

### 4.2. Lấy Top N trong từng tháng

Oracle không cần lọc trực tiếp trên alias của hàm phân tích trong cùng query block. Hãy bọc kết quả bằng CTE hoặc subquery:

```sql
WITH ranked_region AS (
  SELECT month_start,
         region_id,
         region_name,
         revenue,
         ROW_NUMBER() OVER (
           PARTITION BY month_start
           ORDER BY revenue DESC, region_id
         ) AS rn
  FROM (
    SELECT TRUNC(o.order_date, 'MM') AS month_start,
           r.region_id,
           r.region_name,
           SUM(
             l.quantity * l.unit_price
             - NVL(l.discount_amount, 0)
           ) AS revenue
    FROM sales_order o
    JOIN sales_order_line l
      ON l.order_id = o.order_id
    JOIN sales_region r
      ON r.region_id = o.region_id
    WHERE o.status = 'COMPLETED'
    GROUP BY TRUNC(o.order_date, 'MM'),
             r.region_id,
             r.region_name
  )
)
SELECT month_start, region_name, revenue
FROM ranked_region
WHERE rn <= 3
ORDER BY month_start, rn;
```

`ROW_NUMBER() <= 3` luôn trả tối đa ba vùng mỗi tháng. Nếu yêu cầu là lấy tất cả vùng đồng hạng ở vị trí thứ ba, dùng `RANK() <= 3` hoặc `DENSE_RANK() <= 3` tùy quy tắc xếp hạng.

### 4.3. Xếp hạng nhân viên trong từng vùng

Để xếp hạng nhân viên theo vùng và tháng, tổng hợp ở cấp tháng-vùng-nhân viên rồi phân vùng theo tháng và vùng:

```sql
RANK() OVER (
  PARTITION BY month_start, region_id
  ORDER BY revenue DESC
)
```

Không xếp hạng trên từng dòng hàng nếu mục tiêu là xếp hạng theo tổng doanh thu. Nếu làm vậy, Oracle sẽ xếp hạng từng line item, không phải tổng của nhân viên hoặc vùng.

## 5. So sánh doanh thu theo thời gian bằng LAG

`LAG(expression, offset, default)` lấy giá trị ở dòng đứng trước trong cửa sổ phân tích mà không cần self join. Với dữ liệu tháng liên tục, `LAG(revenue, 1)` lấy doanh thu tháng trước; `LAG(revenue, 12)` lấy doanh thu cùng tháng năm trước.

### 5.1. Tính doanh thu tháng và tháng trước

```sql
WITH monthly_sales AS (
  SELECT TRUNC(o.order_date, 'MM') AS month_start,
         SUM(
           l.quantity * l.unit_price
           - NVL(l.discount_amount, 0)
         ) AS revenue
  FROM sales_order o
  JOIN sales_order_line l
    ON l.order_id = o.order_id
  WHERE o.status = 'COMPLETED'
  GROUP BY TRUNC(o.order_date, 'MM')
),
comparison AS (
  SELECT month_start,
         revenue,
         LAG(revenue) OVER (
           ORDER BY month_start
         ) AS previous_month_revenue
  FROM monthly_sales
)
SELECT month_start,
       revenue,
       previous_month_revenue,
       revenue - previous_month_revenue AS change_amount,
       CASE
         WHEN previous_month_revenue IS NULL
           OR previous_month_revenue = 0
         THEN NULL
         ELSE ROUND(
           (revenue - previous_month_revenue)
           / previous_month_revenue * 100,
           2
         )
       END AS change_percent
FROM comparison
ORDER BY month_start;
```

Tỷ lệ thay đổi:

[
\text{Change \%} =
\frac{\text{Current} - \text{Previous}}{\text{Previous}} \times 100
\]

Nếu kỳ trước không có doanh thu hoặc bằng 0, phần trăm tăng trưởng không xác định theo công thức này. Trả `NULL` hoặc hiển thị nhãn riêng như “N/A”; không tự thay mẫu số 0 bằng 1 vì sẽ tạo ra tỷ lệ sai.

### 5.2. Vì sao phải tạo đủ các tháng

Truy vấn ở trên chỉ có các tháng phát sinh giao dịch. Nếu tháng 2 không có doanh thu, dữ liệu có thể chỉ gồm tháng 1 và tháng 3. Khi đó `LAG(revenue)` ở tháng 3 sẽ trả tháng 1, dù báo cáo ghi là so với tháng trước. Đây là so sánh với kỳ có dữ liệu gần nhất, không phải tháng lịch liền trước.

Để so sánh đúng tháng liền trước, tạo một calendar spine gồm tất cả tháng trong khoảng báo cáo, sau đó left join doanh thu và thay kỳ không phát sinh bằng 0.

```sql
WITH params AS (
  SELECT DATE '2026-01-01' AS from_month,
         DATE '2026-12-01' AS to_month
  FROM dual
),
months AS (
  SELECT ADD_MONTHS(p.from_month, LEVEL - 1) AS month_start
  FROM params p
  CONNECT BY LEVEL <= MONTHS_BETWEEN(
    p.to_month, p.from_month
  ) + 1
),
monthly_sales AS (
  SELECT TRUNC(o.order_date, 'MM') AS month_start,
         SUM(
           l.quantity * l.unit_price
           - NVL(l.discount_amount, 0)
         ) AS revenue
  FROM sales_order o
  JOIN sales_order_line l
    ON l.order_id = o.order_id
  CROSS JOIN params p
  WHERE o.status = 'COMPLETED'
    AND o.order_date >= p.from_month
    AND o.order_date < ADD_MONTHS(p.to_month, 1)
  GROUP BY TRUNC(o.order_date, 'MM')
),
filled_months AS (
  SELECT m.month_start,
         NVL(s.revenue, 0) AS revenue
  FROM months m
  LEFT JOIN monthly_sales s
    ON s.month_start = m.month_start
),
comparison AS (
  SELECT month_start,
         revenue,
         LAG(revenue) OVER (
           ORDER BY month_start
         ) AS previous_month_revenue
  FROM filled_months
)
SELECT month_start,
       revenue,
       previous_month_revenue,
       revenue - previous_month_revenue AS change_amount,
       CASE
         WHEN previous_month_revenue IS NULL
           OR previous_month_revenue = 0
         THEN NULL
         ELSE ROUND(
           (revenue - previous_month_revenue)
           / previous_month_revenue * 100,
           2
         )
       END AS change_percent
FROM comparison
ORDER BY month_start;
```

Trong ví dụ, `from_month` và `to_month` phải là ngày đầu tháng. `CONNECT BY LEVEL` sinh một dòng cho mỗi tháng. Điều kiện lọc trên `ORDER_DATE` vẫn dùng khoảng ngày nửa mở để bao gồm trọn tháng cuối.

### 5.3. So sánh cùng kỳ năm trước

Khi calendar spine đã có đủ tháng, có thể dùng offset 12:

```sql
LAG(revenue, 12) OVER (ORDER BY month_start) AS same_month_last_year
```

Sau đó tính chênh lệch và phần trăm tương tự tháng trước. Offset 12 chỉ mang ý nghĩa cùng tháng năm trước khi chuỗi đầu vào có đúng một dòng cho mỗi tháng, không bị thiếu tháng và được sắp xếp liên tục. Nếu không có calendar spine, offset 12 chỉ lấy dòng thứ mười hai trước đó.

Một cách khác là self join theo ngày đầu tháng:

```sql
SELECT current_month.month_start,
       current_month.revenue,
       prior_year.revenue AS same_month_last_year
FROM monthly_sales current_month
LEFT JOIN monthly_sales prior_year
  ON prior_year.month_start =
     ADD_MONTHS(current_month.month_start, -12);
```

Self join dễ diễn đạt quan hệ cùng kỳ khi dữ liệu không liên tục, nhưng vẫn cần calendar nếu báo cáo muốn hiển thị những tháng không có giao dịch.

### 5.4. So sánh theo quý hoặc năm

Có thể thay biểu thức kỳ:

- Tháng: `TRUNC(order_date, 'MM')`
- Quý: `TRUNC(order_date, 'Q')`
- Năm: `TRUNC(order_date, 'YYYY')`

Khi so sánh theo quý, cần có calendar đủ quý và dùng `LAG(revenue, 1)` cho quý trước hoặc `LAG(revenue, 4)` cho cùng quý năm trước. Tương tự, với năm thì offset 1 là năm trước.

## 6. Báo cáo tổng hợp: chi tiết, tổng tháng, xếp hạng và tăng trưởng

Phần này kết hợp các kỹ thuật thành một truy vấn. Báo cáo trả về:

- Dòng chi tiết theo tháng và vùng, có doanh thu, thứ hạng, doanh thu tháng trước và tỷ lệ thay đổi.
- Dòng tổng tháng, có doanh thu toàn bộ vùng, so sánh với tháng trước.
- Dòng tổng cộng của toàn bộ khoảng thời gian.
- Các tháng không có giao dịch vẫn xuất hiện với doanh thu bằng 0.

Ví dụ dùng bảng danh mục `SALES_REGION` để tạo đủ mọi tổ hợp tháng-vùng. Các vùng chưa có doanh thu trong tháng được gán 0 để có thể xếp hạng và so sánh nhất quán.

```sql
WITH
params AS (
  SELECT DATE '2026-01-01' AS from_month,
         DATE '2026-12-01' AS to_month
  FROM dual
),
months AS (
  SELECT ADD_MONTHS(p.from_month, LEVEL - 1) AS month_start
  FROM params p
  CONNECT BY LEVEL <= MONTHS_BETWEEN(
    p.to_month, p.from_month
  ) + 1
),
sales_by_region AS (
  SELECT TRUNC(o.order_date, 'MM') AS month_start,
         o.region_id,
         SUM(
           l.quantity * l.unit_price
           - NVL(l.discount_amount, 0)
         ) AS revenue
  FROM sales_order o
  JOIN sales_order_line l
    ON l.order_id = o.order_id
  CROSS JOIN params p
  WHERE o.status = 'COMPLETED'
    AND o.order_date >= p.from_month
    AND o.order_date < ADD_MONTHS(p.to_month, 1)
  GROUP BY TRUNC(o.order_date, 'MM'),
           o.region_id
),
region_month_grid AS (
  SELECT m.month_start,
         r.region_id,
         r.region_name,
         NVL(s.revenue, 0) AS revenue
  FROM months m
  CROSS JOIN sales_region r
  LEFT JOIN sales_by_region s
    ON s.month_start = m.month_start
   AND s.region_id = r.region_id
),
region_trend AS (
  SELECT g.*,
         LAG(g.revenue) OVER (
           PARTITION BY g.region_id
           ORDER BY g.month_start
         ) AS previous_region_revenue
  FROM region_month_grid g
),
ranked_region AS (
  SELECT t.*,
         RANK() OVER (
           PARTITION BY t.month_start
           ORDER BY t.revenue DESC
         ) AS revenue_rank,
         ROW_NUMBER() OVER (
           PARTITION BY t.month_start
           ORDER BY t.revenue DESC, t.region_id
         ) AS display_order,
         CASE
           WHEN t.previous_region_revenue IS NULL
             OR t.previous_region_revenue = 0
           THEN NULL
           ELSE ROUND(
             (t.revenue - t.previous_region_revenue)
             / t.previous_region_revenue * 100,
             2
           )
         END AS change_percent
  FROM region_trend t
),
monthly_totals AS (
  SELECT month_start,
         SUM(revenue) AS total_revenue
  FROM region_month_grid
  GROUP BY month_start
),
monthly_trend AS (
  SELECT month_start,
         total_revenue,
         LAG(total_revenue) OVER (
           ORDER BY month_start
         ) AS previous_month_revenue
  FROM monthly_totals
),
report_rows AS (
  SELECT month_start,
         1 AS sort_group,
         CAST('CHI TIET VUNG' AS VARCHAR2(20)) AS row_type,
         region_id,
         region_name,
         revenue,
         revenue_rank,
         previous_region_revenue AS previous_revenue,
         change_percent,
         display_order
  FROM ranked_region
  WHERE revenue <> 0

  UNION ALL

  SELECT month_start,
         2 AS sort_group,
         CAST('TONG THANG' AS VARCHAR2(20)) AS row_type,
         CAST(NULL AS NUMBER) AS region_id,
         CAST(NULL AS VARCHAR2(100)) AS region_name,
         total_revenue AS revenue,
         CAST(NULL AS NUMBER) AS revenue_rank,
         previous_month_revenue AS previous_revenue,
         CASE
           WHEN previous_month_revenue IS NULL
             OR previous_month_revenue = 0
           THEN NULL
           ELSE ROUND(
             (total_revenue - previous_month_revenue)
             / previous_month_revenue * 100,
             2
           )
         END AS change_percent,
         0 AS display_order
  FROM monthly_trend

  UNION ALL

  SELECT CAST(NULL AS DATE) AS month_start,
         3 AS sort_group,
         CAST('TONG CONG' AS VARCHAR2(20)) AS row_type,
         CAST(NULL AS NUMBER) AS region_id,
         CAST(NULL AS VARCHAR2(100)) AS region_name,
         SUM(total_revenue) AS revenue,
         CAST(NULL AS NUMBER) AS revenue_rank,
         CAST(NULL AS NUMBER) AS previous_revenue,
         CAST(NULL AS NUMBER) AS change_percent,
         0 AS display_order
  FROM monthly_trend
)
SELECT TO_CHAR(month_start, 'YYYY-MM') AS report_month,
       row_type,
       region_id,
       region_name,
       ROUND(revenue, 2) AS revenue,
       revenue_rank,
       ROUND(previous_revenue, 2) AS previous_revenue,
       change_percent
FROM report_rows
ORDER BY month_start NULLS LAST,
         sort_group,
         display_order;
```

### 6.1. Cách đọc kết quả

| Loại dòng | Cấp dữ liệu | Cột so sánh |
|---|---|---|
| `CHI TIET VUNG` | Một vùng trong một tháng | So sánh doanh thu vùng với chính vùng đó ở tháng trước |
| `TONG THANG` | Tổng tất cả vùng trong một tháng | So sánh tổng tháng với tổng tháng trước |
| `TONG CONG` | Tổng toàn bộ khoảng báo cáo | Không có kỳ trước trong truy vấn này |

`region_month_grid` tạo một dòng cho mỗi cặp tháng-vùng. Vì thế `LAG` phân vùng theo vùng luôn nhìn thấy tháng liền trước, kể cả khi vùng đó không có doanh thu. `ranked_region` tính thứ hạng trên dữ liệu đã tổng hợp, còn `monthly_trend` tính xu hướng của tổng tháng.

Điều kiện `WHERE revenue <> 0` chỉ ẩn dòng chi tiết không có doanh thu trong phần trình bày; những dòng 0 vẫn tham gia ranking và LAG trước đó. Nếu cần hiển thị mọi vùng, kể cả vùng có doanh thu bằng 0, bỏ điều kiện này. Nếu nghiệp vụ cho phép doanh thu âm do hoàn tiền, điều kiện này vẫn giữ lại dòng âm.

Truy vấn mẫu giả định `REGION_ID` là NUMBER và `REGION_NAME` không dài quá 100 ký tự; điều chỉnh kiểu trong các `CAST(NULL AS ...)` theo schema thật. Nếu danh mục vùng không có dòng nào, cross join sẽ không tạo region detail; tổng tháng khi đó không phản ánh doanh thu không gắn vùng. Cần quyết định cách xử lý giao dịch thiếu vùng trước khi phát hành báo cáo.

## 7. Thực hành với ROLLUP và analytic functions trong cùng báo cáo

`ROLLUP` và hàm phân tích có thể xuất hiện trong cùng truy vấn, nhưng cần xác định phép phân tích đang chạy trên những dòng nào. Nếu áp dụng `RANK` trực tiếp sau `GROUP BY ROLLUP`, dòng tổng tháng và tổng cộng cũng có mặt trong tập đầu vào của hàm phân tích. Những dòng đó có thể nhận thứ hạng và làm sai báo cáo.

Cách dễ kiểm soát là:

1. Tạo CTE chi tiết đã tổng hợp.
2. Tính rank trên các dòng chi tiết.
3. Tạo tổng tháng và tổng cộng ở CTE riêng hoặc dùng ROLLUP riêng.
4. Ghép các loại dòng bằng `UNION ALL`.

Nếu dùng `ROLLUP` để tạo tổng phụ và cần thêm xếp hạng, có thể dùng CTE bọc quanh kết quả rollup, lọc `GROUPING(region_name) = 0` trước khi tính rank, hoặc tính rank ở CTE chi tiết trước khi thêm dòng tổng. Không xếp hạng tổng phụ như thể chúng là một vùng.

## 8. Xử lý NULL, tháng thiếu và dữ liệu không hợp lệ

### 8.1. NULL trong phép tính doanh thu

Nếu `DISCOUNT_AMOUNT` là NULL, phép trừ trực tiếp sẽ cho kết quả NULL và `SUM` bỏ qua giá trị đó. Dùng `NVL(discount_amount, 0)` khi NULL có nghĩa là không có chiết khấu. Nếu NULL có nghĩa là dữ liệu chưa được xác định, phải xử lý dữ liệu đầu vào thay vì mặc định thành 0.

Nếu `QUANTITY` hoặc `UNIT_PRICE` có thể NULL, hãy xác định quy tắc dữ liệu. Một dòng thiếu đơn giá không nên tự biến mất khỏi tổng doanh thu mà không có cảnh báo. Có thể kiểm tra riêng:

```sql
SELECT COUNT(*) AS invalid_line_count
FROM sales_order_line
WHERE quantity IS NULL
   OR unit_price IS NULL
   OR quantity < 0;
```

Điều kiện số lượng âm có thể hợp lệ với một hệ thống biểu diễn điều chỉnh/hoàn trả; hãy áp dụng quy tắc phù hợp với mô hình kế toán.

### 8.2. Đơn hàng không có vùng

Join inner với `SALES_REGION` sẽ loại giao dịch có `REGION_ID` không khớp danh mục. Nếu báo cáo phải giữ các giao dịch đó, dùng left join và gán nhãn “Chưa phân vùng” trong kết quả. Đồng thời báo cáo số lượng và doanh thu chưa được phân bổ để tránh tổng báo cáo thấp hơn dữ liệu gốc.

### 8.3. Tiền tệ và làm tròn

Không cộng trực tiếp VND, USD, EUR hoặc loại tiền khác vào một tổng số học duy nhất. Có hai cách:

- Nhóm báo cáo theo `CURRENCY_CODE`, tạo tổng riêng cho từng tiền tệ.
- Quy đổi về một tiền tệ báo cáo bằng bảng tỷ giá có ngày hiệu lực, loại tỷ giá và quy tắc chọn tỷ giá được xác định.

Giữ độ chính xác trong phép tính và làm tròn ở lớp báo cáo theo chính sách kế toán. Làm tròn từng dòng trước khi cộng có thể cho kết quả khác với cộng toàn bộ rồi mới làm tròn.

## 9. Hiệu năng và khả năng mở rộng

### 9.1. Lọc ngày trên cột gốc

Ưu tiên:

```sql
WHERE order_date >= :from_date
  AND order_date <  :to_date_exclusive
```

Hạn chế dùng:

```sql
WHERE TRUNC(order_date, 'MM') = DATE '2026-01-01'
```

trừ khi đã có function-based index hoặc thiết kế phù hợp. Lọc theo khoảng nửa mở thường tận dụng index và partition theo ngày/tháng tốt hơn.

### 9.2. Tổng hợp trước khi join dimension lớn

Nếu dimension có quan hệ một-nhiều, hãy kiểm tra cardinality và tránh nhân bản fact. Có thể tổng hợp doanh thu theo khóa trước rồi mới join tên vùng, tên sản phẩm hoặc nhân viên. Bảng dimension nên có khóa duy nhất ở cột được dùng để join.

### 9.3. Index và partition

Index phù hợp phụ thuộc điều kiện lọc và workload. Một index bắt đầu bằng `STATUS` rồi `ORDER_DATE` có thể phù hợp hoặc không tùy độ chọn lọc; không có một thứ tự index đúng cho mọi báo cáo. Với bảng fact lớn, partition theo ngày ghi nhận có thể giúp pruning theo kỳ, nhưng cần kiểm tra kế hoạch thực thi và chiến lược lưu trữ.

### 9.4. Xem execution plan

Kiểm tra plan của truy vấn báo cáo bằng `DBMS_XPLAN.DISPLAY_CURSOR` khi có quyền và dữ liệu cursor:

```sql
SELECT *
FROM TABLE(
  DBMS_XPLAN.DISPLAY_CURSOR(
    sql_id => :sql_id,
    format => 'TYPICAL'
  )
);
```

Đánh giá cardinality, join method, access path, sort, hash aggregate và lượng dữ liệu trung gian. Các báo cáo dùng `ROLLUP`, `RANK` và `LAG` có thể cần sort hoặc window operation; kiểm tra memory/temp usage nếu dữ liệu lớn.

Không tự động thu thập AWR/ASH hoặc dùng tính năng Diagnostics/Tuning Pack nếu chưa xác nhận quyền cấp phép tương ứng. Có thể kiểm tra execution plan từ cursor và các số liệu runtime được phép thu thập theo chính sách tổ chức.

### 9.5. Vật hóa kết quả khi báo cáo được chạy thường xuyên

Nếu báo cáo được chạy nhiều lần trên dữ liệu lớn, cân nhắc bảng tổng hợp theo ngày/tháng hoặc materialized view. Cần xác định:

- Tần suất refresh và độ trễ dữ liệu cho phép.
- Cơ chế xử lý giao dịch đến muộn, hủy đơn và hoàn tiền.
- Cách đồng bộ lại khi dữ liệu nguồn thay đổi.
- Cách so sánh tổng hợp với bảng giao dịch gốc.
- Quyền truy cập và thời gian lưu dữ liệu tổng hợp.

Materialized view hoặc bảng summary không thay thế việc xác định định nghĩa doanh thu. Chúng chỉ lưu kết quả theo quy tắc đã chọn.

## 10. Kiểm tra kết quả và đối soát

Một báo cáo có thể chạy không lỗi nhưng vẫn sai do join nhân bản, lọc trạng thái thiếu, bỏ sót tháng hoặc cộng nhiều tiền tệ. Nên đối soát ở nhiều cấp:

1. Tổng doanh thu từ bảng dòng hàng với tổng theo vùng.
2. Tổng doanh thu theo vùng cộng lại với tổng tháng.
3. Tổng các tháng cộng lại với tổng toàn kỳ.
4. Số đơn hàng được tính so với số đơn hoàn tất trong cùng điều kiện.
5. Kiểm tra tháng không phát sinh giao dịch có xuất hiện với doanh thu 0.
6. Kiểm tra vùng đồng hạng có thứ hạng theo đúng quy tắc.
7. Kiểm tra tháng đầu kỳ không có previous month nếu ngoài phạm vi báo cáo không được truy vấn.
8. Kiểm tra phần trăm khi doanh thu kỳ trước bằng 0.
9. Kiểm tra giao dịch sát ranh giới ngày/tháng và timezone.

Truy vấn đối soát tổng:

```sql
SELECT SUM(
         l.quantity * l.unit_price
         - NVL(l.discount_amount, 0)
       ) AS source_revenue
FROM sales_order o
JOIN sales_order_line l
  ON l.order_id = o.order_id
WHERE o.status = 'COMPLETED'
  AND o.order_date >= DATE '2026-01-01'
  AND o.order_date <  DATE '2027-01-01';
```

So sánh con số này với tổng toàn kỳ trong báo cáo, dùng cùng định nghĩa trạng thái, ngày, tiền tệ và xử lý vùng chưa phân bổ. Nếu báo cáo có quy đổi tiền tệ, đối soát thêm tỷ giá và ngày hiệu lực đã chọn.

## 11. Trình bày báo cáo cho người sử dụng

Khi đưa kết quả SQL lên ứng dụng hoặc công cụ BI, nên hiển thị rõ loại dòng:

- Dòng chi tiết: tháng, vùng, doanh thu, hạng, doanh thu tháng trước, tỷ lệ thay đổi.
- Dòng tổng tháng: nhấn mạnh tổng nhưng vẫn giữ cột so sánh theo kỳ.
- Dòng tổng cộng: ghi rõ toàn bộ khoảng thời gian, không hiển thị phần trăm so sánh không có ý nghĩa.

Định dạng số theo tiền tệ và locale người xem, nhưng giữ giá trị số gốc để sắp xếp và tính toán. Không sắp xếp doanh thu theo chuỗi đã định dạng như `1.200.000`; hãy sắp xếp theo NUMBER rồi mới format.

Nếu báo cáo có bộ lọc vùng, sản phẩm hoặc nhân viên, cần xác định tổng phụ được tính trong phạm vi đã lọc hay trên toàn bộ dữ liệu. Cùng một truy vấn có thể tạo ra tổng khác nhau nếu điều kiện lọc được áp dụng trước hoặc sau phép tổng hợp.

## 12. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Join bảng header với nhiều bảng con trước khi tổng hợp | Doanh thu bị nhân bản | Tổng hợp từng quan hệ một-nhiều trước khi join |
| Xếp hạng từng dòng hàng | Thứ hạng không phản ánh doanh thu vùng/nhân viên | Tổng hợp đúng cấp trước rồi mới dùng analytic function |
| Xếp hạng cả dòng tổng phụ | Tổng tháng hoặc tổng cộng chen vào bảng xếp hạng | Xếp hạng chi tiết riêng rồi ghép dòng tổng |
| Dùng `RANK` khi cần số thứ tự duy nhất | Nhiều dòng cùng thứ hạng | Dùng `ROW_NUMBER` với tie-breaker ổn định |
| Dùng `ROW_NUMBER` khi cần giữ đồng hạng | Một đơn vị hòa điểm bị đẩy xuống hạng sau | Dùng `RANK` hoặc `DENSE_RANK` |
| Dùng `LAG` trên tháng có giao dịch | Tháng thiếu làm so sánh nhảy qua kỳ | Tạo calendar spine và điền tháng 0 |
| Chia cho doanh thu kỳ trước bằng 0 | Lỗi hoặc tỷ lệ vô nghĩa | Dùng `CASE` để trả NULL/N/A |
| Lọc bằng `BETWEEN` với cột có giờ | Có thể bỏ sót thời điểm cuối ngày | Dùng `>= start` và `< end_exclusive` |
| Cộng nhiều tiền tệ trực tiếp | Tổng doanh thu không có ý nghĩa | Nhóm theo currency hoặc quy đổi theo tỷ giá |
| Làm tròn từng dòng không theo chính sách | Tổng có sai lệch làm tròn | Thống nhất điểm làm tròn |

## 13. Quy trình xây dựng báo cáo

1. Chốt định nghĩa doanh thu, trạng thái giao dịch, ngày ghi nhận, tiền tệ và cách xử lý hoàn tiền.
2. Xác định grain của dữ liệu nguồn và kiểm tra quan hệ một-nhiều để tránh nhân bản.
3. Viết truy vấn tổng hợp cơ bản theo chiều cần báo cáo.
4. Thêm `ROLLUP` hoặc `GROUPING SETS` để tạo tổng phụ và tổng cộng.
5. Tạo CTE chi tiết rồi áp dụng `RANK`, `DENSE_RANK` hoặc `ROW_NUMBER` theo quy tắc xếp hạng.
6. Tạo calendar spine nếu cần so sánh đúng kỳ lịch liền trước hoặc cùng kỳ năm trước.
7. Dùng `LAG` hoặc self join để lấy kỳ so sánh và xử lý trường hợp kỳ trước bằng 0.
8. Ghép dòng chi tiết, tổng tháng và tổng cộng bằng `UNION ALL` khi cần kiểm soát rõ cấp dòng.
9. Đối soát tổng nguồn, tổng theo vùng và tổng theo kỳ.
10. Kiểm tra execution plan, quyền truy cập, bảo mật dữ liệu và định dạng đầu ra.

## 14. Nguyên tắc thực hành

Một báo cáo doanh thu đáng tin cậy bắt đầu từ định nghĩa doanh thu và grain dữ liệu đúng. `GROUP BY` tạo số liệu ở cấp cần phân tích; `ROLLUP` và `GROUPING SETS` tạo tổng phụ; `RANK`, `DENSE_RANK` và `ROW_NUMBER` xếp hạng trên dữ liệu đã tổng hợp; `LAG` so sánh các kỳ liên tiếp. Calendar spine bảo đảm tháng không có giao dịch vẫn được xem là một kỳ, còn `GROUPING` phân biệt tổng phụ với giá trị NULL thật.

Khi ghép các phép tính, hãy tính chi tiết và xu hướng trong những CTE riêng, sau đó mới kết hợp các loại dòng báo cáo. Đối soát tổng từ dữ liệu nguồn, xử lý tiền tệ và timezone rõ ràng, và kiểm tra hiệu năng trên quy mô dữ liệu thực tế. Như vậy, người đọc có thể hiểu mỗi con số được tính từ đâu, thứ hạng dựa trên tiêu chí nào và phép so sánh đang dùng đúng kỳ thời gian nào.
