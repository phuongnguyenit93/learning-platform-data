# Conditional aggregation bằng CASE

Khi lập báo cáo, ta thường cần nhiều con số trên cùng một nhóm dữ liệu: tổng doanh thu đã thanh toán, tổng doanh thu chờ xử lý, số đơn bị hủy, số khách hàng đã mua và giá trị đơn hàng lớn nhất. Nếu chạy một câu SQL riêng cho từng chỉ số, ứng dụng phải gửi nhiều truy vấn và ghép kết quả lại. Oracle có thể tính nhiều chỉ số như vậy trong **một lần nhóm dữ liệu** bằng kỹ thuật **conditional aggregation** — đặt biểu thức `CASE` bên trong hàm tổng hợp như `SUM`, `COUNT`, `AVG`, `MIN` hoặc `MAX`.

Ý tưởng cốt lõi:

~~~sql
SUM(
    CASE
        WHEN dieu_kien THEN gia_tri
        ELSE 0
    END
)
~~~

`CASE` quyết định giá trị đóng góp của từng hàng; hàm tổng hợp sau đó cộng hoặc đếm những giá trị đó trong mỗi nhóm. Kỹ thuật này đặc biệt hữu ích trong báo cáo theo tháng, khu vực, trạng thái, kênh bán hàng và các dashboard cần nhiều cột chỉ số.

Bài học đi từ biểu thức cơ bản đến nhiều điều kiện, xử lý `NULL`, tỷ lệ an toàn, `HAVING`, analytic function và những sai lệch thường gặp khi JOIN. Các ví dụ dùng Oracle SQL và bảng giả định `SALES_ORDERS`.

## 1. Conditional aggregation là gì?

Giả sử bảng `SALES_ORDERS` có các cột:

| Cột | Ý nghĩa |
|---|---|
| `ORDER_ID` | Mã đơn hàng |
| `CUSTOMER_ID` | Mã khách hàng |
| `ORDER_DATE` | Ngày tạo đơn |
| `REGION_ID` | Mã khu vực |
| `CHANNEL` | Kênh bán hàng, ví dụ `WEB` hoặc `STORE` |
| `STATUS` | Trạng thái, ví dụ `PAID`, `PENDING`, `CANCELLED` |
| `AMOUNT` | Giá trị đơn hàng |

Yêu cầu báo cáo: theo từng khu vực, tính tổng doanh thu của đơn đã thanh toán. Ta có thể viết:

~~~sql
SELECT region_id,
       SUM(
           CASE
               WHEN status = 'PAID' THEN amount
               ELSE 0
           END
       ) AS paid_revenue
FROM sales_orders
GROUP BY region_id
ORDER BY region_id;
~~~

Với mỗi hàng:

- Nếu `STATUS = 'PAID'`, `CASE` trả về `AMOUNT`.
- Nếu không, `CASE` trả về 0.
- `SUM` cộng các giá trị mà từng hàng đóng góp trong cùng `REGION_ID`.

~~~mermaid
flowchart TD
    A["Các hàng SALES_ORDERS"] --> B["Chia nhóm theo REGION_ID"]
    B --> C["Xét từng hàng trong nhóm"]
    C --> D{"STATUS = PAID?"}
    D -->|Có| E["Đóng góp AMOUNT"]
    D -->|Không| F["Đóng góp 0"]
    E --> G["SUM các giá trị đóng góp"]
    F --> G
    G --> H["Một kết quả PAID_REVENUE cho mỗi khu vực"]
~~~

Đây là **tổng có điều kiện**. Bản thân `GROUP BY` tạo các nhóm; `CASE` quyết định hàng nào đóng góp giá trị gì cho chỉ số.

## 2. Mẫu CASE bên trong các hàm tổng hợp

### 2.1 SUM(CASE ...): tính tổng có điều kiện

Mẫu thông dụng:

~~~sql
SUM(
    CASE
        WHEN dieu_kien THEN bieu_thuc_so
        ELSE 0
    END
)
~~~

Ví dụ tính tổng đơn đã thanh toán:

~~~sql
SELECT SUM(
           CASE
               WHEN status = 'PAID' THEN amount
               ELSE 0
           END
       ) AS paid_total
FROM sales_orders;
~~~

Nếu chỉ muốn tính giá trị của các hàng thỏa điều kiện và để những hàng còn lại là `NULL`:

~~~sql
SELECT SUM(
           CASE
               WHEN status = 'PAID' THEN amount
           END
       ) AS paid_total
FROM sales_orders;
~~~

Hai cách có thể cho cùng kết quả khi nhóm có ít nhất một hàng thỏa điều kiện và dữ liệu số phù hợp. Nhưng khi **không có hàng nào thỏa điều kiện**, kết quả có thể khác:

- `SUM(CASE WHEN ... THEN amount ELSE 0 END)` trả 0 nếu nhóm có hàng nhưng không hàng nào thỏa.
- `SUM(CASE WHEN ... THEN amount END)` trả `NULL` nếu không có hàng nào đóng góp giá trị khác `NULL`.

Chọn kết quả theo ý nghĩa báo cáo. Nếu “không có doanh thu” cần hiện 0, dạng có `ELSE 0` thường dễ hiểu. Nếu cần phân biệt “không có dữ liệu tính được” với “tổng thực sự bằng 0”, giữ `NULL` hoặc trả thêm chỉ số đếm.

### 2.2 COUNT(CASE ...): đếm hàng thỏa điều kiện

Mẫu đếm an toàn:

~~~sql
COUNT(
    CASE
        WHEN status = 'PAID' THEN 1
    END
)
~~~

`COUNT(expression)` chỉ đếm những giá trị **không `NULL`**. Khi điều kiện đúng, `CASE` trả 1; khi sai, không có `ELSE` nên trả `NULL` và không được đếm.

Ví dụ:

~~~sql
SELECT region_id,
       COUNT(*) AS all_orders,
       COUNT(
           CASE
               WHEN status = 'PAID' THEN 1
           END
       ) AS paid_orders
FROM sales_orders
GROUP BY region_id;
~~~

**Lỗi thường gặp:**

~~~sql
COUNT(
    CASE
        WHEN status = 'PAID' THEN 1
        ELSE 0
    END
)
~~~

Biểu thức trên đếm **mọi hàng**, vì cả 1 lẫn 0 đều là giá trị không `NULL`. Nếu cần đếm có điều kiện, hãy bỏ `ELSE` hoặc dùng `SUM(CASE WHEN ... THEN 1 ELSE 0 END)`.

Hai mẫu sau đều đếm số hàng có trạng thái PAID:

~~~sql
COUNT(CASE WHEN status = 'PAID' THEN 1 END)
~~~

~~~sql
SUM(CASE WHEN status = 'PAID' THEN 1 ELSE 0 END)
~~~

Mẫu `COUNT` biểu đạt ý “đếm biểu thức không NULL”; mẫu `SUM` biểu đạt ý “cộng 1 cho mỗi hàng thỏa điều kiện”. Với nhóm có hàng, chúng thường cho cùng số đếm. Nếu truy vấn không có hàng nào và không có `GROUP BY`, `COUNT` trả 0 còn `SUM` có thể trả `NULL`; cần để ý khi tạo báo cáo tổng.

### 2.3 AVG(CASE ...): trung bình trên tập con

~~~sql
SELECT AVG(
           CASE
               WHEN status = 'PAID' THEN amount
           END
       ) AS average_paid_amount
FROM sales_orders;
~~~

Các hàng không phải `PAID` trả `NULL`; `AVG` bỏ qua `NULL` nên chỉ tính trung bình trên những hàng đã thanh toán có `AMOUNT` khác `NULL`.

Không viết `ELSE 0` một cách tùy tiện:

~~~sql
AVG(
    CASE
        WHEN status = 'PAID' THEN amount
        ELSE 0
    END
)
~~~

Ở đây các hàng không phải `PAID` đóng góp số 0 và **vẫn nằm trong mẫu số của AVG**. Kết quả không còn là trung bình của đơn PAID; nó là trung bình của toàn bộ hàng trong nhóm với các hàng không PAID được coi như giá trị 0.

| Biểu thức | Những giá trị được AVG tính? | Ý nghĩa |
|---|---|---|
| `AVG(CASE WHEN status='PAID' THEN amount END)` | Chỉ amount của hàng PAID, không NULL | Giá trị trung bình của đơn PAID |
| `AVG(CASE WHEN status='PAID' THEN amount ELSE 0 END)` | Amount của PAID và 0 của hàng khác | Trung bình trên tất cả hàng trong nhóm theo quy ước hàng khác PAID bằng 0 |

### 2.4 MIN và MAX có điều kiện

~~~sql
SELECT region_id,
       MIN(CASE WHEN status = 'PAID' THEN order_date END)
           AS first_paid_order,
       MAX(CASE WHEN status = 'PAID' THEN order_date END)
           AS latest_paid_order,
       MAX(CASE WHEN status = 'PAID' THEN amount END)
           AS largest_paid_order
FROM sales_orders
GROUP BY region_id;
~~~

`MIN` và `MAX` bỏ qua `NULL`, vì vậy chỉ các hàng PAID đóng góp ngày/giá trị. Nếu một khu vực không có hàng PAID, các cột tương ứng có thể trả `NULL`. Đây là cách lấy ngày sớm nhất/muộn nhất hoặc giá trị lớn nhất **trong tập con** mà không cần truy vấn riêng.

### 2.5 COUNT(DISTINCT CASE ...): đếm đối tượng duy nhất có điều kiện

Ví dụ đếm số khách hàng có ít nhất một đơn đã thanh toán:

~~~sql
SELECT region_id,
       COUNT(
           DISTINCT CASE
               WHEN status = 'PAID' THEN customer_id
           END
       ) AS paid_customers
FROM sales_orders
GROUP BY region_id;
~~~

Các hàng không PAID trả `NULL`; `COUNT(DISTINCT ...)` bỏ qua `NULL` và chỉ đếm mỗi `CUSTOMER_ID` khác `NULL` một lần trong nhóm. Nếu một khách hàng có năm đơn PAID ở cùng khu vực, khách hàng đó vẫn được đếm một lần.

Nếu `CUSTOMER_ID` có thể `NULL`, các hàng không có mã khách hàng không được tính là khách hàng duy nhất. Đó thường là điều mong muốn; nếu nghiệp vụ yêu cầu xử lý khách hàng chưa định danh, cần thêm chỉ số riêng.

## 3. Chuẩn bị dữ liệu thực hành

Nếu có schema thực hành, có thể tạo bảng nhỏ sau. Chỉ chạy một lần trong schema được phép:

~~~sql
CREATE TABLE lab_sales_orders (
    order_id    NUMBER(10) PRIMARY KEY,
    customer_id NUMBER(10),
    order_date  DATE NOT NULL,
    region_id   VARCHAR2(10 CHAR),
    channel     VARCHAR2(10 CHAR),
    status      VARCHAR2(12 CHAR),
    amount      NUMBER(12,2)
);
~~~

Nạp dữ liệu mẫu:

~~~sql
INSERT ALL
    INTO lab_sales_orders VALUES
        (1, 101, DATE '2026-01-05', 'NORTH', 'WEB',   'PAID',      1000)
    INTO lab_sales_orders VALUES
        (2, 102, DATE '2026-01-08', 'NORTH', 'STORE', 'PENDING',    500)
    INTO lab_sales_orders VALUES
        (3, 101, DATE '2026-01-12', 'NORTH', 'WEB',   'PAID',       700)
    INTO lab_sales_orders VALUES
        (4, 103, DATE '2026-01-15', 'SOUTH', 'STORE', 'CANCELLED',  300)
    INTO lab_sales_orders VALUES
        (5, 104, DATE '2026-02-02', 'SOUTH', 'WEB',   'PAID',      1200)
    INTO lab_sales_orders VALUES
        (6, 102, DATE '2026-02-10', 'NORTH', 'WEB',   'CANCELLED',  200)
    INTO lab_sales_orders VALUES
        (7, 105, DATE '2026-02-14', 'SOUTH', 'STORE', 'PENDING',    800)
    INTO lab_sales_orders VALUES
        (8, 106, DATE '2026-02-18', 'SOUTH', 'WEB',   'PAID',       600)
    INTO lab_sales_orders VALUES
        (9, 107, DATE '2026-02-20', 'NORTH', 'STORE', NULL,         400)
SELECT 1 FROM dual;

COMMIT;
~~~

Dữ liệu có hai khu vực, hai kênh, ba trạng thái và một hàng có `STATUS IS NULL` để kiểm tra cách điều kiện hoạt động.

Xem dữ liệu:

~~~sql
SELECT order_id, customer_id, order_date,
       region_id, channel, status, amount
FROM lab_sales_orders
ORDER BY order_id;
~~~

## 4. Nhiều chỉ số có điều kiện trong cùng một GROUP BY

Một lợi thế lớn của conditional aggregation là tạo nhiều chỉ số trong một lần nhóm. Ví dụ:

~~~sql
SELECT region_id,
       COUNT(*) AS total_orders,
       SUM(CASE WHEN status = 'PAID' THEN amount ELSE 0 END)
           AS paid_revenue,
       SUM(CASE WHEN status = 'PENDING' THEN amount ELSE 0 END)
           AS pending_amount,
       SUM(CASE WHEN status = 'CANCELLED' THEN amount ELSE 0 END)
           AS cancelled_amount,
       COUNT(CASE WHEN status = 'PAID' THEN 1 END)
           AS paid_order_count,
       COUNT(CASE WHEN status = 'PENDING' THEN 1 END)
           AS pending_order_count,
       COUNT(CASE WHEN status = 'CANCELLED' THEN 1 END)
           AS cancelled_order_count
FROM lab_sales_orders
GROUP BY region_id
ORDER BY region_id;
~~~

Kết quả dự kiến:

| REGION_ID | TOTAL_ORDERS | PAID_REVENUE | PENDING_AMOUNT | CANCELLED_AMOUNT | PAID_ORDER_COUNT | PENDING_ORDER_COUNT | CANCELLED_ORDER_COUNT |
|---|---:|---:|---:|---:|---:|---:|---:|
| NORTH | 5 | 1700 | 500 | 200 | 2 | 1 | 1 |
| SOUTH | 4 | 1800 | 800 | 300 | 2 | 1 | 1 |

Mỗi biểu thức tổng hợp là một chỉ số độc lập. Oracle nhóm hàng theo `REGION_ID`, rồi tính tất cả biểu thức trong danh sách `SELECT` cho từng nhóm. Hàng có `STATUS IS NULL` vẫn nằm trong `TOTAL_ORDERS` nhưng không được tính vào ba trạng thái cụ thể.

### 4.1 Tính số lượng và tổng tiền cho từng trạng thái

~~~sql
SELECT region_id,
       SUM(CASE WHEN status = 'PAID' THEN 1 ELSE 0 END)
           AS paid_count,
       SUM(CASE WHEN status = 'PAID' THEN amount ELSE 0 END)
           AS paid_amount,
       SUM(CASE WHEN status = 'PENDING' THEN 1 ELSE 0 END)
           AS pending_count,
       SUM(CASE WHEN status = 'PENDING' THEN amount ELSE 0 END)
           AS pending_amount
FROM lab_sales_orders
GROUP BY region_id;
~~~

Một cặp chỉ số thường gồm:

- **Số lượng:** cộng 1 cho mỗi hàng thỏa điều kiện.
- **Giá trị:** cộng số tiền của các hàng thỏa điều kiện.

Không cần truy vấn riêng rồi JOIN các kết quả theo khu vực nếu các chỉ số đều xuất phát từ cùng tập hàng và cùng cách nhóm.

### 4.2 Tách chỉ số theo kênh

~~~sql
SELECT region_id,
       SUM(CASE WHEN channel = 'WEB' THEN amount ELSE 0 END)
           AS web_revenue,
       SUM(CASE WHEN channel = 'STORE' THEN amount ELSE 0 END)
           AS store_revenue,
       COUNT(CASE WHEN channel = 'WEB' THEN 1 END)
           AS web_orders,
       COUNT(CASE WHEN channel = 'STORE' THEN 1 END)
           AS store_orders
FROM lab_sales_orders
GROUP BY region_id
ORDER BY region_id;
~~~

Đây là một dạng báo cáo “pivot thủ công”: mỗi điều kiện trở thành một cột kết quả. Cách này rất linh hoạt khi số nhóm cần hiển thị đã biết trước.

## 5. Conditional aggregation với nhiều điều kiện

Điều kiện trong `CASE` có thể kết hợp nhiều cột bằng `AND`, `OR`, `IN`, so sánh khoảng và kiểm tra `NULL`.

### 5.1 Kết hợp trạng thái và kênh

Doanh thu của đơn PAID qua WEB:

~~~sql
SELECT region_id,
       SUM(
           CASE
               WHEN status = 'PAID'
                AND channel = 'WEB'
               THEN amount
               ELSE 0
           END
       ) AS paid_web_revenue
FROM lab_sales_orders
GROUP BY region_id;
~~~

Số đơn PAID hoặc PENDING:

~~~sql
SELECT region_id,
       COUNT(
           CASE
               WHEN status IN ('PAID', 'PENDING') THEN 1
           END
       ) AS active_orders
FROM lab_sales_orders
GROUP BY region_id;
~~~

Điều kiện có thể dài; khi dài, xuống dòng và đặt ngoặc rõ ràng:

~~~sql
SUM(
    CASE
        WHEN status = 'PAID'
         AND channel IN ('WEB', 'STORE')
         AND order_date >= DATE '2026-01-01'
         AND order_date <  DATE '2026-02-01'
        THEN amount
        ELSE 0
    END
) AS paid_january_amount
~~~

### 5.2 Nhóm điều kiện theo khoảng ngày

Ví dụ báo cáo doanh thu tháng 1 và tháng 2 trên cùng một hàng cho mỗi khu vực:

~~~sql
SELECT region_id,
       SUM(
           CASE
               WHEN order_date >= DATE '2026-01-01'
                AND order_date <  DATE '2026-02-01'
                AND status = 'PAID'
               THEN amount
               ELSE 0
           END
       ) AS jan_paid_revenue,
       SUM(
           CASE
               WHEN order_date >= DATE '2026-02-01'
                AND order_date <  DATE '2026-03-01'
                AND status = 'PAID'
               THEN amount
               ELSE 0
           END
       ) AS feb_paid_revenue
FROM lab_sales_orders
GROUP BY region_id
ORDER BY region_id;
~~~

Dùng khoảng nửa mở `[đầu tháng, đầu tháng tiếp theo)` để bao gồm mọi thời điểm trong tháng nếu cột `ORDER_DATE` có phần giờ. Ví dụ `ORDER_DATE < DATE '2026-02-01'` loại đúng từ đầu tháng 2 trở đi; không cần đoán thời điểm cuối ngày bằng `23:59:59`.

### 5.3 Một hàng có thể thỏa nhiều điều kiện

Conditional aggregation cho phép các điều kiện **chồng lấn**. Ví dụ:

~~~sql
SELECT region_id,
       SUM(CASE WHEN amount >= 1000 THEN amount ELSE 0 END)
           AS large_order_amount,
       SUM(CASE WHEN channel = 'WEB' THEN amount ELSE 0 END)
           AS web_order_amount
FROM lab_sales_orders
GROUP BY region_id;
~~~

Một đơn WEB trị giá 1.200 có thể đóng góp vào cả `LARGE_ORDER_AMOUNT` và `WEB_ORDER_AMOUNT`. Điều đó đúng nếu hai chỉ số mô tả hai khía cạnh khác nhau; nhưng không được cộng hai cột rồi gọi là tổng doanh thu vì có thể **đếm trùng**.

Nếu muốn phân loại thành các nhóm loại trừ nhau, phải thiết kế điều kiện sao cho mỗi hàng chỉ thuộc đúng một nhóm và kiểm tra rằng các nhóm bao phủ đầy đủ tập dữ liệu cần báo cáo.

## 6. CASE và NULL: chi tiết quyết định kết quả

### 6.1 Không có ELSE thì CASE trả NULL

~~~sql
CASE
    WHEN status = 'PAID' THEN amount
END
~~~

Nếu điều kiện không đúng, Oracle trả `NULL` vì không có `ELSE`. Đây là hành vi hữu ích với hàm tổng hợp:

- `SUM` bỏ qua các giá trị `NULL`.
- `AVG` bỏ qua các giá trị `NULL` trong cả tổng lẫn số lượng mẫu.
- `COUNT(expression)` bỏ qua `NULL`.
- `MIN` và `MAX` bỏ qua `NULL`.

Ví dụ:

~~~sql
SELECT SUM(CASE WHEN status = 'PAID' THEN amount END)
           AS paid_sum,
       COUNT(CASE WHEN status = 'PAID' THEN 1 END)
           AS paid_count,
       AVG(CASE WHEN status = 'PAID' THEN amount END)
           AS paid_average
FROM lab_sales_orders;
~~~

### 6.2 Phân biệt trạng thái NULL với trạng thái khác

Điều kiện:

~~~sql
CASE
    WHEN status <> 'PAID' THEN amount
    ELSE 0
END
~~~

không coi `STATUS IS NULL` là một giá trị “khác PAID” theo logic hai giá trị. Trong SQL, so sánh `NULL <> 'PAID'` cho kết quả UNKNOWN; nhánh `WHEN` không được chọn nên `ELSE 0` được dùng.

Nếu muốn nhóm “khác PAID, bao gồm cả NULL”:

~~~sql
CASE
    WHEN status = 'PAID' THEN 0
    ELSE amount
END
~~~

hoặc viết rõ:

~~~sql
CASE
    WHEN status <> 'PAID' OR status IS NULL THEN amount
    ELSE 0
END
~~~

Nếu muốn chỉ đếm những trạng thái khác PAID nhưng **loại trừ NULL**:

~~~sql
CASE
    WHEN status IS NOT NULL
     AND status <> 'PAID'
    THEN amount
    ELSE 0
END
~~~

Điều kiện nên thể hiện rõ cách xử lý trạng thái thiếu dữ liệu, đặc biệt khi báo cáo có ý nghĩa kiểm soát chất lượng dữ liệu.

### 6.3 SUM không có hàng phù hợp có thể trả NULL

Giả sử không có hàng PAID trong toàn bộ bảng:

~~~sql
SELECT SUM(CASE WHEN status = 'REFUNDED' THEN amount END)
           AS sum_without_match,
       SUM(CASE WHEN status = 'REFUNDED' THEN amount ELSE 0 END)
           AS sum_with_zero
FROM lab_sales_orders;
~~~

Với bảng có hàng nhưng không có trạng thái `REFUNDED`:

- `SUM_WITHOUT_MATCH` là `NULL` vì tất cả biểu thức đầu vào là `NULL`.
- `SUM_WITH_ZERO` là 0 vì mỗi hàng đóng góp 0.

Nếu muốn hiển thị 0 nhưng vẫn giữ logic biểu thức gốc:

~~~sql
NVL(SUM(CASE WHEN status = 'REFUNDED' THEN amount END), 0)
~~~

`NVL` ở ngoài hàm tổng hợp chuyển kết quả tổng `NULL` thành 0. Cách này hữu ích khi cần phân biệt rõ **quy tắc chọn hàng** bên trong `CASE` với **quy tắc hiển thị tổng** bên ngoài.

Nếu truy vấn có `GROUP BY`, nhóm không có bất kỳ hàng nào trong nguồn thường không xuất hiện thành một hàng kết quả. `ELSE 0` không tự sinh một nhóm chưa tồn tại trong dữ liệu.

### 6.4 COUNT(*) và COUNT(CASE...) khác nhau

~~~sql
SELECT COUNT(*) AS all_rows,
       COUNT(status) AS rows_with_status,
       COUNT(CASE WHEN status = 'PAID' THEN 1 END) AS paid_rows,
       COUNT(CASE WHEN status = 'PAID' THEN amount END)
           AS paid_rows_with_amount
FROM lab_sales_orders;
~~~

Các số đếm khác nhau khi có `STATUS IS NULL` hoặc `AMOUNT IS NULL`:

- `COUNT(*)` đếm mọi hàng.
- `COUNT(status)` đếm hàng có trạng thái khác `NULL`.
- `COUNT(CASE WHEN ... THEN 1 END)` đếm hàng thỏa điều kiện.
- `COUNT(CASE WHEN ... THEN amount END)` chỉ đếm hàng thỏa điều kiện **và** amount không `NULL`.

Đây là lý do dùng `THEN 1` cho phép đếm hàng thường rõ nghĩa hơn dùng một cột có thể `NULL`.

## 7. Đếm duy nhất có điều kiện

Khi cần đếm số khách hàng duy nhất đã thanh toán theo khu vực:

~~~sql
SELECT region_id,
       COUNT(DISTINCT
           CASE
               WHEN status = 'PAID' THEN customer_id
           END
       ) AS distinct_paid_customers
FROM lab_sales_orders
GROUP BY region_id
ORDER BY region_id;
~~~

Trong dữ liệu mẫu:

- Khu vực NORTH có khách hàng 101 với hai đơn PAID, nên số khách hàng duy nhất là 1.
- Khu vực SOUTH có khách hàng 104 và 106 có đơn PAID, nên số khách hàng duy nhất là 2.

Nếu cần đếm khách hàng đã có đơn WEB bất kể trạng thái:

~~~sql
COUNT(DISTINCT CASE WHEN channel = 'WEB' THEN customer_id END)
~~~

Không dùng `COUNT(DISTINCT customer_id)` nếu mục tiêu là chỉ đếm khách hàng PAID; biểu thức đó sẽ đếm khách hàng từ mọi trạng thái.

### 7.1 Đếm có điều kiện theo nhiều chiều

~~~sql
SELECT region_id,
       COUNT(DISTINCT CASE
           WHEN status = 'PAID' AND channel = 'WEB'
           THEN customer_id
       END) AS paid_web_customers,
       COUNT(DISTINCT CASE
           WHEN status = 'PAID' AND channel = 'STORE'
           THEN customer_id
       END) AS paid_store_customers
FROM lab_sales_orders
GROUP BY region_id;
~~~

Một khách hàng có thể xuất hiện ở cả hai cột nếu đã thanh toán qua cả WEB và STORE. Hai số đếm này không nhất thiết cộng lại bằng tổng khách hàng duy nhất của khu vực.

## 8. Conditional aggregation kết hợp GROUP BY và HAVING

`WHERE` lọc **hàng nguồn trước khi nhóm**; `HAVING` lọc **nhóm sau khi tính aggregate**. Điều kiện bên trong `CASE` chỉ quyết định hàng đóng góp vào một chỉ số, không loại hàng khỏi tất cả các chỉ số.

### 8.1 Chỉ giữ khu vực có doanh thu PAID vượt ngưỡng

~~~sql
SELECT region_id,
       SUM(CASE WHEN status = 'PAID' THEN amount ELSE 0 END)
           AS paid_revenue,
       COUNT(CASE WHEN status = 'PAID' THEN 1 END)
           AS paid_orders
FROM lab_sales_orders
GROUP BY region_id
HAVING SUM(CASE WHEN status = 'PAID' THEN amount ELSE 0 END) > 1500;
~~~

`HAVING` dùng aggregate để quyết định nhóm nào được trả về. Cả hai khu vực trong dữ liệu mẫu có tổng PAID lớn hơn 1.500? NORTH có 1.700, SOUTH có 1.800, vì vậy cả hai đều thỏa.

### 8.2 Sai lầm khi đưa điều kiện vào WHERE

Nếu viết:

~~~sql
SELECT region_id,
       COUNT(*) AS total_orders,
       SUM(CASE WHEN status = 'PAID' THEN amount ELSE 0 END)
           AS paid_revenue
FROM lab_sales_orders
WHERE status = 'PAID'
GROUP BY region_id;
~~~

thì `COUNT(*)` chỉ đếm đơn PAID vì `WHERE` đã loại các hàng PENDING, CANCELLED và NULL trước khi nhóm. Nếu báo cáo muốn tổng số đơn **mọi trạng thái** cùng doanh thu PAID, hãy bỏ điều kiện trạng thái khỏi `WHERE` và giữ nó bên trong `CASE`.

Ví dụ `WHERE` phù hợp:

~~~sql
SELECT region_id,
       COUNT(*) AS total_orders_in_period,
       SUM(CASE WHEN status = 'PAID' THEN amount ELSE 0 END)
           AS paid_revenue
FROM lab_sales_orders
WHERE order_date >= DATE '2026-01-01'
  AND order_date <  DATE '2026-03-01'
GROUP BY region_id;
~~~

Ở đây `WHERE` lọc khoảng thời gian mà báo cáo quan tâm cho **tất cả chỉ số**; `CASE` tiếp tục tách riêng trạng thái PAID.

### 8.3 Lọc nhóm theo nhiều điều kiện aggregate

~~~sql
SELECT region_id,
       COUNT(*) AS total_orders,
       COUNT(CASE WHEN status = 'PAID' THEN 1 END) AS paid_orders,
       SUM(CASE WHEN status = 'PAID' THEN amount ELSE 0 END)
           AS paid_revenue
FROM lab_sales_orders
GROUP BY region_id
HAVING COUNT(*) >= 3
   AND COUNT(CASE WHEN status = 'PAID' THEN 1 END) >= 2;
~~~

Khu vực phải có ít nhất 3 đơn tổng cộng và ít nhất 2 đơn PAID. Không thể dùng alias của aggregate trong `WHERE` vì `WHERE` được xử lý trước bước nhóm; đặt điều kiện nhóm trong `HAVING`.

## 9. Conditional aggregation theo tháng, quý và các khoảng thời gian

Một báo cáo thường cần nhiều cột tháng:

~~~sql
SELECT region_id,
       SUM(CASE
           WHEN order_date >= DATE '2026-01-01'
            AND order_date <  DATE '2026-02-01'
            AND status = 'PAID'
           THEN amount ELSE 0 END) AS jan,
       SUM(CASE
           WHEN order_date >= DATE '2026-02-01'
            AND order_date <  DATE '2026-03-01'
            AND status = 'PAID'
           THEN amount ELSE 0 END) AS feb,
       SUM(CASE
           WHEN order_date >= DATE '2026-03-01'
            AND order_date <  DATE '2026-04-01'
            AND status = 'PAID'
           THEN amount ELSE 0 END) AS mar
FROM sales_orders
WHERE order_date >= DATE '2026-01-01'
  AND order_date <  DATE '2026-04-01'
GROUP BY region_id;
~~~

Đây là pivot thủ công cho ba tháng đã biết. Nếu muốn một hàng cho từng tháng, có thể dùng `GROUP BY TRUNC(order_date, 'MM')` thay vì tạo một cột cho từng tháng:

~~~sql
SELECT region_id,
       TRUNC(order_date, 'MM') AS month_start,
       SUM(CASE WHEN status = 'PAID' THEN amount ELSE 0 END)
           AS paid_revenue,
       COUNT(CASE WHEN status = 'PAID' THEN 1 END)
           AS paid_orders
FROM sales_orders
WHERE order_date >= DATE '2026-01-01'
  AND order_date <  DATE '2026-04-01'
GROUP BY region_id, TRUNC(order_date, 'MM')
ORDER BY region_id, month_start;
~~~

Chọn dạng kết quả:

- **Nhiều cột tháng:** phù hợp dashboard với số kỳ cố định.
- **Một hàng cho mỗi tháng:** phù hợp biểu đồ, xuất dữ liệu hoặc báo cáo có số kỳ thay đổi.

Không dùng chuỗi ngày phụ thuộc `NLS_DATE_FORMAT` trong điều kiện; date literal hoặc bind kiểu ngày giúp kết quả ổn định.

## 10. Conditional aggregation với analytic function

Aggregate thông thường kết hợp `GROUP BY` làm giảm số hàng thành một hàng cho mỗi nhóm. Analytic function dùng `OVER` có thể tính chỉ số theo nhóm nhưng vẫn giữ từng hàng chi tiết.

Ví dụ: hiển thị từng đơn cùng tổng doanh thu PAID của khu vực:

~~~sql
SELECT order_id,
       region_id,
       status,
       amount,
       SUM(
           CASE WHEN status = 'PAID' THEN amount ELSE 0 END
       ) OVER (PARTITION BY region_id) AS region_paid_revenue
FROM sales_orders
ORDER BY region_id, order_id;
~~~

Mỗi hàng vẫn đại diện một đơn; cột `REGION_PAID_REVENUE` lặp lại tổng PAID của khu vực tương ứng. Đây không phải cùng dạng kết quả với `GROUP BY region_id`.

Có thể tính tỷ trọng của từng đơn PAID trên tổng PAID khu vực:

~~~sql
SELECT order_id,
       region_id,
       status,
       amount,
       CASE
           WHEN status = 'PAID' THEN
               amount / NULLIF(
                   SUM(CASE WHEN status = 'PAID' THEN amount ELSE 0 END)
                       OVER (PARTITION BY region_id),
                   0
               )
       END AS paid_order_share
FROM sales_orders;
~~~

Hàng không PAID trả `NULL` ở cột tỷ trọng; mẫu số 0 được bảo vệ bằng `NULLIF`. Nếu cần phần trăm, nhân biểu thức với 100 và làm tròn theo yêu cầu.

## 11. Conditional aggregation và JOIN: tránh nhân bản dữ liệu

Một lỗi nghiêm trọng không nằm trong `CASE` mà nằm ở số hàng sau JOIN. Giả sử một đơn hàng có nhiều dòng hàng trong `ORDER_ITEMS`. Khi JOIN `SALES_ORDERS` với `ORDER_ITEMS`, một đơn có ba dòng hàng sẽ xuất hiện ba lần.

~~~sql
SELECT o.region_id,
       SUM(o.amount) AS order_revenue,
       SUM(CASE WHEN o.status = 'PAID' THEN o.amount ELSE 0 END)
           AS paid_revenue
FROM sales_orders o
JOIN order_items i
  ON i.order_id = o.order_id
GROUP BY o.region_id;
~~~

Nếu `O.AMOUNT` là tổng tiền **cấp đơn**, mỗi dòng hàng lặp lại nó; `SUM(o.amount)` và `PAID_REVENUE` sẽ bị nhân lên theo số dòng item. Conditional aggregation không tự khử trùng lặp do JOIN.

### 11.1 Cách 1: tổng hợp bảng con trước khi JOIN

Nếu cần số dòng hàng của mỗi đơn:

~~~sql
WITH item_counts AS (
    SELECT order_id,
           COUNT(*) AS item_count
    FROM order_items
    GROUP BY order_id
)
SELECT o.region_id,
       SUM(o.amount) AS order_revenue,
       SUM(CASE WHEN o.status = 'PAID' THEN o.amount ELSE 0 END)
           AS paid_revenue,
       SUM(NVL(i.item_count, 0)) AS total_items
FROM sales_orders o
LEFT JOIN item_counts i
  ON i.order_id = o.order_id
GROUP BY o.region_id;
~~~

CTE `ITEM_COUNTS` tạo một hàng cho mỗi order trước khi JOIN, nên giá trị cấp đơn không bị lặp bởi từng item.

### 11.2 Cách 2: tổng hợp dữ liệu cấp item theo đúng grain

Nếu mục tiêu là doanh thu item, hãy cộng `ITEM_AMOUNT` ở bảng chi tiết và áp dụng trạng thái đơn từ bảng header:

~~~sql
SELECT o.region_id,
       SUM(CASE
               WHEN o.status = 'PAID' THEN i.item_amount
               ELSE 0
           END) AS paid_item_revenue
FROM sales_orders o
JOIN order_items i
  ON i.order_id = o.order_id
GROUP BY o.region_id;
~~~

Đây là phép tính ở **grain item**, không phải tổng tiền cấp đơn. Phải xác nhận `ITEM_AMOUNT` đã bao gồm/loại trừ thuế, chiết khấu và các khoản điều chỉnh đúng yêu cầu.

### 11.3 LEFT JOIN và COUNT(*)

Với bảng cha có thể không có dòng con:

~~~sql
SELECT o.region_id,
       COUNT(*) AS joined_rows,
       COUNT(i.item_id) AS actual_item_rows
FROM sales_orders o
LEFT JOIN order_items i
  ON i.order_id = o.order_id
GROUP BY o.region_id;
~~~

Một đơn không có item vẫn tạo một hàng mở rộng NULL trong kết quả LEFT JOIN. Vì vậy `COUNT(*)` đếm ít nhất một hàng cho đơn đó; `COUNT(i.item_id)` chỉ đếm item có mã khác NULL. Khi conditional aggregation cần đếm đơn, hãy xác định rõ đang đếm **đơn**, **item** hay **khách hàng**, và tránh đếm sai grain.

## 12. Nhiều điều kiện loại trừ nhau và kiểm tra tính đầy đủ

Một báo cáo trạng thái có thể định nghĩa ba nhóm:

~~~sql
SELECT region_id,
       SUM(CASE WHEN status = 'PAID' THEN 1 ELSE 0 END) AS paid,
       SUM(CASE WHEN status = 'PENDING' THEN 1 ELSE 0 END) AS pending,
       SUM(CASE WHEN status = 'CANCELLED' THEN 1 ELSE 0 END) AS cancelled,
       COUNT(*) AS total
FROM lab_sales_orders
GROUP BY region_id;
~~~

Nếu chỉ có ba trạng thái hợp lệ và không có NULL, ta kỳ vọng:

`PAID + PENDING + CANCELLED = TOTAL`.

Nhưng dữ liệu mẫu có một hàng `STATUS IS NULL`, nên ở khu vực NORTH:

`2 + 1 + 1 = 4`, trong khi `TOTAL = 5`.

Khoảng chênh 1 là hàng thiếu trạng thái. Để báo cáo minh bạch, thêm cột:

~~~sql
SUM(CASE WHEN status IS NULL THEN 1 ELSE 0 END) AS missing_status
~~~

hoặc tính trạng thái khác:

~~~sql
SUM(
    CASE
        WHEN status IS NULL THEN 1
        WHEN status NOT IN ('PAID', 'PENDING', 'CANCELLED') THEN 1
        ELSE 0
    END
) AS other_or_missing
~~~

Khi dùng `NOT IN` với một cột có thể NULL, nhớ rằng điều kiện có thể là UNKNOWN; muốn đưa NULL vào nhóm phải viết `IS NULL` riêng.

### 12.1 Điều kiện có thể chồng lấn

Nếu một đơn có thể vừa thuộc “đơn WEB” vừa thuộc “đơn lớn”, tổng các chỉ số không nhất thiết bằng tổng hàng. Đừng kiểm tra tính đầy đủ bằng cách cộng các nhóm độc lập nếu điều kiện không loại trừ nhau.

Nếu muốn tạo đúng một bucket cho mỗi hàng, dùng một `CASE` với các nhánh theo thứ tự ưu tiên:

~~~sql
CASE
    WHEN status = 'PAID' THEN 'PAID'
    WHEN status = 'PENDING' THEN 'PENDING'
    WHEN status = 'CANCELLED' THEN 'CANCELLED'
    ELSE 'OTHER_OR_MISSING'
END
~~~

Sau đó có thể nhóm theo bucket hoặc viết conditional aggregation trên cùng các điều kiện. Thứ tự nhánh `WHEN` quan trọng khi các điều kiện chồng lấn; Oracle chọn nhánh đầu tiên đúng.

## 13. Conditional aggregation so với WHERE, subquery và PIVOT

### 13.1 Khi nào dùng CASE trong aggregate?

Phù hợp khi:

- Nhiều chỉ số được tính từ **cùng tập dữ liệu nguồn**.
- Các chỉ số có cùng grain và cùng cách nhóm.
- Số điều kiện cần xuất thành cột đã biết trước.
- Cần giữ cả hàng không thỏa một điều kiện để tính chỉ số khác.

Ví dụ:

~~~sql
SELECT region_id,
       COUNT(*) AS total_orders,
       COUNT(CASE WHEN status = 'PAID' THEN 1 END) AS paid_orders,
       COUNT(CASE WHEN status = 'PENDING' THEN 1 END) AS pending_orders
FROM sales_orders
GROUP BY region_id;
~~~

### 13.2 Khi nào WHERE phù hợp hơn?

Nếu toàn bộ báo cáo chỉ quan tâm đơn PAID, có thể lọc trước:

~~~sql
SELECT region_id,
       COUNT(*) AS paid_orders,
       SUM(amount) AS paid_revenue
FROM sales_orders
WHERE status = 'PAID'
GROUP BY region_id;
~~~

Đây là cách tự nhiên hơn nếu không cần các chỉ số của trạng thái khác. `WHERE` loại hàng trước bước nhóm và có thể giúp giảm lượng hàng cần xử lý. Nhưng nếu cần `TOTAL_ORDERS` cùng `PAID_ORDERS` trong một kết quả, đưa trạng thái vào `WHERE` sẽ làm mất các hàng không PAID.

### 13.3 Khi nào dùng PIVOT?

Oracle có toán tử `PIVOT` cho một số dạng chuyển giá trị thành cột. Conditional aggregation thường linh hoạt hơn khi:

- Cần nhiều hàm khác nhau cho mỗi nhóm.
- Mỗi cột có điều kiện phức tạp.
- Cần kết hợp chỉ số số lượng, tổng, trung bình và distinct.
- Muốn kiểm soát rõ cách xử lý NULL/ELSE.

Ví dụ PIVOT đơn giản cho tổng tiền theo trạng thái:

~~~sql
SELECT *
FROM (
    SELECT region_id, status, amount
    FROM sales_orders
)
PIVOT (
    SUM(amount)
    FOR status IN (
        'PAID' AS paid,
        'PENDING' AS pending,
        'CANCELLED' AS cancelled
    )
);
~~~

`PIVOT` phù hợp khi phép biến đổi tự nhiên theo một cột phân loại. Conditional aggregation vẫn là lựa chọn trực tiếp khi cần định nghĩa riêng từng chỉ số. Không có một kỹ thuật luôn nhanh hơn: kiểm tra execution plan và dữ liệu thực tế.

## 14. Kiểu dữ liệu và biểu thức CASE trong aggregate

Các nhánh `THEN` và `ELSE` của `CASE` cần có kiểu dữ liệu tương thích để Oracle xác định kiểu kết quả. Ví dụ:

~~~sql
SUM(
    CASE
        WHEN status = 'PAID' THEN amount
        ELSE 0
    END
)
~~~

`AMOUNT` là NUMBER và `0` là numeric literal nên phù hợp.

Tránh trộn số với chuỗi:

~~~sql
-- Không phù hợp cho phép tính số:
CASE WHEN status = 'PAID' THEN amount ELSE '0' END
~~~

Oracle có thể phải chuyển đổi ngầm định hoặc báo lỗi kiểu dữ liệu. Với aggregate số, giữ tất cả nhánh là kiểu số; với báo cáo hiển thị, chuyển sang chuỗi ở bước cuối bằng `TO_CHAR`.

### 14.1 Điều kiện so sánh và NULL

~~~sql
CASE
    WHEN amount >= 1000 THEN 'LARGE'
    WHEN amount >= 500 THEN 'MEDIUM'
    ELSE 'SMALL'
END
~~~

Nếu `AMOUNT IS NULL`, các điều kiện so sánh đều không TRUE nên nhánh `ELSE` trả `SMALL`. Nếu NULL cần được nhận diện riêng:

~~~sql
CASE
    WHEN amount IS NULL THEN 'MISSING'
    WHEN amount >= 1000 THEN 'LARGE'
    WHEN amount >= 500 THEN 'MEDIUM'
    ELSE 'SMALL'
END
~~~

Thứ tự nhánh ảnh hưởng kết quả; đặt trường hợp đặc biệt trước những nhánh tổng quát.

## 15. Hiệu năng và khả năng bảo trì

Conditional aggregation có thể giúp tính nhiều chỉ số trong một lượt nhóm dữ liệu thay vì gửi nhiều câu SQL riêng. Nhưng **không thể khẳng định một truy vấn conditional aggregation luôn nhanh hơn mọi cách khác**. Optimizer còn xét:

- Số hàng và phân bố dữ liệu.
- Index, partition pruning và điều kiện `WHERE`.
- Số nhóm trong `GROUP BY`.
- Số biểu thức `CASE` và hàm aggregate.
- JOIN trước khi nhóm và nguy cơ nhân bản hàng.
- Statistics và execution plan.

### 15.1 Lọc tập nguồn bằng WHERE khi mọi chỉ số dùng chung điều kiện

Ví dụ báo cáo chỉ lấy dữ liệu trong một quý:

~~~sql
SELECT region_id,
       SUM(CASE WHEN status = 'PAID' THEN amount ELSE 0 END)
           AS paid_revenue,
       COUNT(CASE WHEN status = 'PENDING' THEN 1 END)
           AS pending_orders
FROM sales_orders
WHERE order_date >= :period_start
  AND order_date <  :period_end
GROUP BY region_id;
~~~

Bind `:period_start` và `:period_end` bằng kiểu ngày/giờ phù hợp. Lọc thời gian trong `WHERE` giúp loại các hàng ngoài kỳ cho tất cả chỉ số; trạng thái vẫn nằm trong `CASE` để tách các chỉ số.

### 15.2 Không lặp logic điều kiện tùy tiện

Nếu nhiều cột dùng cùng một điều kiện phức tạp, có thể chuẩn hóa bằng CTE:

~~~sql
WITH classified_orders AS (
    SELECT region_id,
           amount,
           status,
           CASE
               WHEN status = 'PAID' AND channel = 'WEB'
               THEN 1
               ELSE 0
           END AS is_paid_web
    FROM sales_orders
)
SELECT region_id,
       SUM(CASE WHEN is_paid_web = 1 THEN amount ELSE 0 END)
           AS paid_web_revenue,
       SUM(is_paid_web) AS paid_web_orders
FROM classified_orders
GROUP BY region_id;
~~~

CTE giúp tập trung logic phân loại để dễ đọc và tái sử dụng trong câu truy vấn. Không mặc định CTE là bảng vật lý tạm hoặc Oracle luôn materialize nó; optimizer có thể biến đổi cách thực thi.

### 15.3 Kiểm tra plan thay vì đoán

Sau khi có truy vấn thực tế, xem execution plan bằng công cụ được phép, chẳng hạn:

~~~sql
EXPLAIN PLAN FOR
SELECT region_id,
       SUM(CASE WHEN status = 'PAID' THEN amount ELSE 0 END)
           AS paid_revenue
FROM sales_orders
WHERE order_date >= DATE '2026-01-01'
  AND order_date <  DATE '2026-02-01'
GROUP BY region_id;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

`EXPLAIN PLAN` cho biết kế hoạch dự kiến theo môi trường và thống kê hiện có; nó không luôn phản ánh chính xác runtime của một lần chạy thực tế với bind values. Với workload quan trọng, dùng công cụ giám sát và execution plan thực tế theo quyền/chính sách DBA.

## 16. Những lỗi thường gặp khi dùng conditional aggregation

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `COUNT(CASE WHEN cond THEN 1 ELSE 0 END)` đếm tất cả hàng | Giá trị 0 không phải NULL nên vẫn được COUNT | Bỏ ELSE hoặc dùng SUM với 1/0 |
| AVG thấp bất ngờ | Dùng `ELSE 0` khiến hàng không thỏa vẫn nằm trong mẫu số | Bỏ ELSE nếu muốn trung bình trên tập con |
| Tổng có điều kiện trả NULL | Không có hàng đóng góp giá trị khác NULL | Chọn `ELSE 0` hoặc `NVL(SUM(...),0)` theo ý nghĩa |
| Nhóm không có trong kết quả | Không có hàng nguồn để tạo group | Dùng dimension/calendar table nếu cần hiện nhóm rỗng |
| Hàng NULL trạng thái không vào nhóm “khác” | So sánh `<>` với NULL cho UNKNOWN | Thêm `OR status IS NULL` hoặc nhánh riêng |
| Tổng doanh thu bị nhân lên sau JOIN | Một hàng header lặp theo nhiều dòng detail | Tổng hợp detail trước, hoặc tính đúng grain |
| Tổng các bucket không bằng tổng hàng | Điều kiện chồng lấn hoặc không bao phủ NULL/trạng thái khác | Kiểm tra định nghĩa bucket và thêm nhóm missing/other |
| Tỷ lệ báo lỗi chia cho 0 | Mẫu số aggregate bằng 0 | Bảo vệ bằng `NULLIF` |
| Tỷ lệ trung bình khác tỷ lệ tổng | Khác định nghĩa và trọng số | Chọn AVG từng tỷ lệ hoặc SUM/SUM theo mục tiêu |
| Báo cáo tháng bỏ sót cuối ngày | Dùng điều kiện <= ngày cuối ở mốc nửa đêm | Dùng khoảng nửa mở đầu tháng đến đầu tháng sau |
| CASE báo lỗi kiểu dữ liệu | Các nhánh trả kiểu không tương thích | Giữ nhánh số là NUMBER, nhánh text là text |
| Conditional aggregation chậm | Quá nhiều hàng, JOIN fan-out, nhóm lớn hoặc thiếu lọc phù hợp | Xem plan, grain, index/partition và statistics |

## 17. Bài thực hành tự kiểm tra

Các bài tập dưới đây dùng bảng `LAB_SALES_ORDERS` ở phần 3. Nếu chưa tạo bảng, có thể thay tên bằng bảng báo cáo thực tế có các cột tương đương.

### Bài 1 — Tổng theo trạng thái

Viết một câu SQL theo `REGION_ID` trả:

- Tổng số đơn.
- Tổng giá trị PAID.
- Tổng giá trị PENDING.
- Tổng giá trị CANCELLED.

Không lọc trạng thái trong `WHERE`. Kiểm tra vì sao tổng số đơn NORTH bao gồm cả hàng `STATUS IS NULL`.

### Bài 2 — Đếm có điều kiện

Viết ba biểu thức:

~~~sql
COUNT(CASE WHEN status = 'PAID' THEN 1 END)
~~~

~~~sql
SUM(CASE WHEN status = 'PAID' THEN 1 ELSE 0 END)
~~~

~~~sql
COUNT(CASE WHEN status = 'PAID' THEN amount END)
~~~

Giải thích khi `AMOUNT` có NULL thì biểu thức thứ ba có thể khác hai biểu thức đầu như thế nào.

### Bài 3 — AVG và ELSE 0

So sánh:

~~~sql
AVG(CASE WHEN status = 'PAID' THEN amount END)
~~~

với:

~~~sql
AVG(CASE WHEN status = 'PAID' THEN amount ELSE 0 END)
~~~

Tính bằng tay cho khu vực NORTH và giải thích mẫu số của từng phép AVG.

### Bài 4 — Đếm khách hàng duy nhất

Theo từng khu vực, đếm khách hàng có đơn PAID:

~~~sql
COUNT(DISTINCT CASE WHEN status = 'PAID' THEN customer_id END)
~~~

Sau đó viết một cột khác đếm khách hàng có đơn WEB bất kể trạng thái. Một khách hàng có thể được đếm trong cả hai cột không? Vì sao?

### Bài 5 — Báo cáo theo tháng

Viết một hàng cho mỗi khu vực với hai cột `JAN_PAID` và `FEB_PAID`. Dùng khoảng nửa mở với date literal. Giải thích tại sao `ORDER_DATE` có phần giờ vẫn được lọc đúng.

### Bài 6 — Nhóm trạng thái thiếu

Thêm cột đếm `STATUS IS NULL` và chứng minh:

`PAID + PENDING + CANCELLED + MISSING_STATUS = TOTAL`

với dữ liệu mẫu. Nếu có trạng thái mới `REFUNDED`, cần bổ sung cách nào để kiểm tra tính đầy đủ?

### Bài 7 — HAVING

Chỉ hiển thị khu vực có ít nhất hai đơn PAID và doanh thu PAID trên 1.500. Viết điều kiện trong `HAVING`. Vì sao không đặt aggregate vào `WHERE`?

### Bài 8 — Tỷ lệ an toàn

Tính tỷ lệ giá trị PAID trên tổng giá trị của từng khu vực. Dùng:

~~~sql
SUM(CASE WHEN status = 'PAID' THEN amount ELSE 0 END)
/
NULLIF(SUM(amount), 0)
~~~

Giải thích khi nào kết quả là NULL và tại sao không nên tự đổi mẫu số 0 thành 1.

### Bài 9 — Phát hiện JOIN fan-out

Giả sử mỗi đơn có nhiều item. Viết một truy vấn JOIN header/detail và giải thích tại sao `SUM(header.amount)` có thể bị nhân lên. Viết lại bằng CTE tổng hợp item trước khi JOIN.

### Bài 10 — Giữ chi tiết bằng analytic

Viết truy vấn vẫn hiển thị từng `ORDER_ID` nhưng có thêm tổng doanh thu PAID theo `REGION_ID` bằng:

~~~sql
SUM(CASE WHEN status = 'PAID' THEN amount ELSE 0 END)
OVER (PARTITION BY region_id)
~~~

Giải thích sự khác nhau giữa kết quả analytic và kết quả `GROUP BY`.

## 18. Ghi nhớ khi viết conditional aggregation

| Nhu cầu | Mẫu SQL nên nhớ |
|---|---|
| Tổng giá trị theo điều kiện | `SUM(CASE WHEN cond THEN amount ELSE 0 END)` |
| Tổng tập con và giữ ý nghĩa NULL | `SUM(CASE WHEN cond THEN amount END)` |
| Đếm hàng theo điều kiện | `COUNT(CASE WHEN cond THEN 1 END)` |
| Đếm bằng tổng 1/0 | `SUM(CASE WHEN cond THEN 1 ELSE 0 END)` |
| Trung bình tập con | `AVG(CASE WHEN cond THEN amount END)` |
| Giá trị lớn nhất/nhỏ nhất tập con | `MAX/MIN(CASE WHEN cond THEN value END)` |
| Đếm khách hàng duy nhất theo điều kiện | `COUNT(DISTINCT CASE WHEN cond THEN customer_id END)` |
| Tỷ lệ an toàn | `numerator / NULLIF(denominator, 0)` |
| Lọc nhóm sau aggregate | `HAVING SUM(CASE WHEN ... END) ...` |
| Giữ từng hàng cùng tổng nhóm | Aggregate có `OVER (PARTITION BY ...)` |

Khi viết conditional aggregation, hãy xác định **grain của dữ liệu**, định nghĩa từng điều kiện, cách xử lý NULL, và ý nghĩa của giá trị 0 trước khi chọn `ELSE`. Dùng `COUNT(CASE ... THEN 1 END)` để đếm hàng, `AVG(CASE ... END)` để tính trung bình tập con, và `NULLIF` để bảo vệ mẫu số. Cuối cùng, kiểm tra số hàng sau JOIN để tránh nhân bản tổng. Làm rõ những điểm này giúp một câu SQL duy nhất tạo ra nhiều chỉ số nhất quán và có thể giải thích được.
