# GROUP BY, khóa nhóm ghép và biểu thức nhóm trong Oracle Database

Một bảng bán hàng có thể chứa hàng triệu dòng chi tiết đơn hàng. Khi cần biết **doanh thu theo khu vực**, **số đơn theo kênh bán**, hoặc **doanh thu theo từng tháng và sản phẩm**, ta không muốn nhận lại từng dòng giao dịch. Ta muốn Oracle gom các dòng có cùng tiêu chí thành nhóm và tính toán trên mỗi nhóm. Câu lệnh **`GROUP BY`** thực hiện việc đó.

Điểm quan trọng nhất là một nhóm có thể được xác định bởi **một cột**, **nhiều cột kết hợp thành khóa nhóm**, hoặc **biểu thức tính từ dữ liệu**. Ví dụ `GROUP BY region, channel` tạo một nhóm cho mỗi cặp khu vực và kênh bán; `GROUP BY TRUNC(sold_at, 'MM')` tạo nhóm theo tháng; `GROUP BY UPPER(product_name)` gom các cách viết khác nhau về cùng dạng chữ hoa theo quy tắc của hàm.

Bài học thuộc nhóm **Gom nhóm và tập hợp** của Oracle Database, tập trung vào cách xác định nhóm, cách dùng hàm tổng hợp, thứ tự lọc dữ liệu, cách xử lý NULL và các biểu thức nhóm thường gặp.

Sau khi học, bạn có thể:

- Giải thích một nhóm được hình thành như thế nào khi có một hoặc nhiều khóa nhóm.
- Viết `GROUP BY` với khóa nhóm ghép như `region, channel, product`.
- Dùng `COUNT`, `SUM`, `AVG`, `MIN`, `MAX` và các hàm tổng hợp khác theo nhóm.
- Phân biệt `WHERE` và `HAVING` trong truy vấn gom nhóm.
- Gom nhóm theo tháng, năm, khoảng giá trị, dạng chuẩn hóa hoặc biểu thức `CASE`.
- Hiểu cách Oracle xử lý NULL, giá trị trùng, alias và thứ tự kết quả.
- Nhận biết các lỗi thường gặp như `ORA-00979` và `ORA-00937`.

> **Phạm vi ví dụ:** Các câu SQL dùng cú pháp Oracle phổ biến, tương thích với Oracle Database 19c. Bảng thực hành `GROUP_BY_LAB` được tạo trong schema/PDB lab do bạn quản lý. Không chạy DDL hoặc dữ liệu mẫu trên schema ứng dụng đang hoạt động.

## 1. GROUP BY làm gì?

Giả sử bảng `SALES` lưu mỗi giao dịch bán hàng thành một dòng:

| Sale ID | Region | Channel | Product | Quantity | Unit price |
| ---: | --- | --- | --- | ---: | ---: |
| 1 | North | Online | Laptop | 1 | 1.000 |
| 2 | North | Store | Laptop | 2 | 1.000 |
| 3 | North | Online | Mouse | 3 | 25 |
| 4 | South | Online | Laptop | 1 | 1.000 |
| 5 | South | Store | Mouse | 4 | 25 |

Nếu muốn tính doanh thu từng khu vực, ta gom các dòng có cùng `REGION`:

~~~sql
SELECT
    region,
    SUM(quantity * unit_price) AS revenue
FROM sales
GROUP BY region;
~~~

Oracle tạo một nhóm cho `North` và một nhóm cho `South`, rồi tính `SUM` trên từng nhóm.

~~~text
SALES (cac dong giao dich)
       |
       | GROUP BY region
       v
  +-----------+             +-----------+
  | North     |             | South     |
  | sale 1    |             | sale 4    |
  | sale 2    |             | sale 5    |
  | sale 3    |             |           |
  +-----+-----+             +-----+-----+
        |                         |
        v                         v
  SUM(quantity * price)     SUM(quantity * price)
        |                         |
        +------------+------------+
                     v
             Ket qua: 1 dong/nhom
~~~

**Kết quả có một dòng cho mỗi tổ hợp khóa nhóm**, không phải một dòng cho mỗi bản ghi nguồn. Hàm tổng hợp tính trên những dòng thành viên của nhóm đó.

### 1.1. GROUP BY với một cột

~~~sql
SELECT status, COUNT(*) AS order_count
FROM orders
GROUP BY status;
~~~

Kết quả có một dòng cho mỗi trạng thái khác nhau. Nếu có 500 đơn `PAID`, 30 đơn `PENDING` và 5 đơn `CANCELLED`, kết quả có ba nhóm với số lượng tương ứng.

### 1.2. GROUP BY không có hàm tổng hợp

~~~sql
SELECT region
FROM sales
GROUP BY region;
~~~

Truy vấn vẫn hợp lệ và trả các giá trị `REGION` khác nhau, tương tự `SELECT DISTINCT region` trong trường hợp đơn giản. Tuy nhiên, khi mục tiêu chỉ là loại bỏ dòng trùng, `DISTINCT` thường diễn đạt ý định rõ hơn:

~~~sql
SELECT DISTINCT region
FROM sales;
~~~

`GROUP BY` hữu ích khi bạn muốn tính tổng hợp hoặc xác định nhóm cho các phép tính khác.

### 1.3. GROUP BY không tự sắp xếp kết quả

Oracle không bảo đảm thứ tự dòng chỉ vì bạn viết `GROUP BY`:

~~~sql
SELECT region, COUNT(*) AS row_count
FROM sales
GROUP BY region;
~~~

Nếu cần khu vực theo thứ tự chữ cái:

~~~sql
SELECT region, COUNT(*) AS row_count
FROM sales
GROUP BY region
ORDER BY region;
~~~

**`GROUP BY` xác định thành viên của nhóm; `ORDER BY` xác định thứ tự hiển thị các nhóm.** Không dựa vào thứ tự ngẫu nhiên mà công cụ SQL đang hiển thị.

## 2. Hàm tổng hợp hoạt động trên từng nhóm

Các hàm thường dùng:

| Hàm | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `COUNT(*)` | Đếm tất cả dòng trong nhóm | Không bỏ dòng chỉ vì một cột có NULL |
| `COUNT(expression)` | Đếm dòng mà expression khác NULL | Không đếm giá trị NULL |
| `COUNT(DISTINCT expression)` | Đếm giá trị khác nhau và khác NULL | Có thể tốn tài nguyên khi nhóm lớn |
| `SUM(expression)` | Tổng các giá trị khác NULL | Nếu mọi giá trị đều NULL, kết quả là NULL |
| `AVG(expression)` | Trung bình các giá trị khác NULL | Tương đương tổng chia số giá trị được tính |
| `MIN(expression)` | Giá trị nhỏ nhất | Có thể áp dụng cho số, ngày, chuỗi theo quy tắc so sánh |
| `MAX(expression)` | Giá trị lớn nhất | Có thể áp dụng cho số, ngày, chuỗi theo quy tắc so sánh |
| `STDDEV(expression)` | Độ lệch chuẩn mẫu | Dùng khi phân tích phân tán |
| `VARIANCE(expression)` | Phương sai mẫu | Dùng khi phân tích phân tán |

Ví dụ:

~~~sql
SELECT
    region,
    COUNT(*) AS sale_rows,
    SUM(quantity) AS units_sold,
    AVG(unit_price) AS average_unit_price,
    MIN(unit_price) AS min_unit_price,
    MAX(unit_price) AS max_unit_price,
    SUM(quantity * unit_price) AS revenue
FROM sales
GROUP BY region
ORDER BY region;
~~~

Oracle tính từng hàm trên các dòng thuộc cùng một khu vực. Các biểu thức tổng hợp có thể khác nhau; ví dụ `AVG(unit_price)` là trung bình đơn giá theo dòng, trong khi `SUM(quantity * unit_price)` là doanh thu theo số lượng nhân đơn giá.

### 2.1. COUNT(*) và COUNT(column) khác nhau

Giả sử một nhóm có 5 dòng, trong đó cột `EMAIL` chỉ có 3 dòng khác NULL:

~~~sql
SELECT
    region,
    COUNT(*) AS all_rows,
    COUNT(email) AS rows_with_email,
    COUNT(DISTINCT email) AS distinct_emails
FROM customers
GROUP BY region;
~~~

- `COUNT(*)` trả 5 cho nhóm đó.
- `COUNT(email)` trả 3 nếu đúng 3 giá trị email khác NULL.
- `COUNT(DISTINCT email)` trả số email khác nhau, bỏ qua NULL.

Đừng thay `COUNT(*)` bằng `COUNT(column)` nếu nghiệp vụ muốn đếm mọi dòng, vì kết quả có thể thấp hơn.

### 2.2. SUM và AVG bỏ qua NULL

Giả sử các giá trị trong nhóm là `10, 20, NULL`:

- `SUM(value)` là 30.
- `AVG(value)` là 15, không phải 10.
- `COUNT(value)` là 2.
- `COUNT(*)` là 3.

Nếu mọi giá trị trong nhóm đều NULL, `SUM` và `AVG` trả NULL. Nếu muốn hiển thị 0 cho trường hợp đó:

~~~sql
SELECT
    region,
    NVL(SUM(discount_amount), 0) AS total_discount
FROM sales
GROUP BY region;
~~~

`NVL` ở đây chỉ thay kết quả tổng hợp NULL bằng 0 để trình bày. Hãy chắc rằng 0 đúng ý nghĩa nghiệp vụ; “không có dữ liệu” và “tổng bằng 0” có thể là hai trạng thái khác nhau.

### 2.3. Biểu thức tính trong hàm tổng hợp

Bạn không cần tạo cột doanh thu vật lý mới chỉ để tính tổng:

~~~sql
SELECT
    region,
    SUM(quantity * unit_price) AS gross_revenue,
    SUM(quantity * unit_price * (1 - discount_pct / 100))
        AS net_revenue
FROM sales
GROUP BY region;
~~~

Biểu thức bên trong `SUM` được tính cho các dòng thuộc nhóm. Hãy kiểm tra kiểu dữ liệu, scale, NULL và quy tắc làm tròn nếu phép tính liên quan tiền tệ. Một phép tính có thể cho kết quả NULL nếu toán hạng NULL; có thể dùng `NVL`/`COALESCE` khi nghiệp vụ quy định giá trị thay thế.

## 3. Khóa nhóm ghép: GROUP BY nhiều cột

### 3.1. Một khóa nhóm có thể là tổ hợp nhiều giá trị

Giả sử muốn xem số dòng và doanh thu theo **khu vực và kênh bán**. Câu lệnh:

~~~sql
SELECT
    region,
    channel,
    COUNT(*) AS sale_rows,
    SUM(quantity * unit_price) AS revenue
FROM sales
GROUP BY region, channel
ORDER BY region, channel;
~~~

Oracle tạo nhóm theo **cặp (`REGION`, `CHANNEL`)**:

~~~text
  (North, Online)       (North, Store)
       |                     |
       v                     v
  cac dong North/Online  cac dong North/Store
       |                     |
       v                     v
    COUNT, SUM             COUNT, SUM

  (South, Online)       (South, Store)
       |                     |
       v                     v
  cac dong South/Online  cac dong South/Store
       |                     |
       v                     v
    COUNT, SUM             COUNT, SUM
~~~

**Mỗi tổ hợp khác nhau là một nhóm riêng.** Không phải Oracle nhóm theo `REGION` trước rồi lại nhóm độc lập theo `CHANNEL`; hai giá trị cùng nhau xác định khóa nhóm.

### 3.2. Ví dụ số liệu

Giả sử dữ liệu:

| Region | Channel | Sale rows | Revenue |
| --- | --- | ---: | ---: |
| North | Online | 2 | 1.075 |
| North | Store | 1 | 2.000 |
| South | Online | 1 | 1.000 |
| South | Store | 1 | 100 |

Truy vấn:

~~~sql
SELECT
    region,
    channel,
    COUNT(*) AS sale_rows,
    SUM(quantity * unit_price) AS revenue
FROM sales
GROUP BY region, channel;
~~~

chỉ có bốn nhóm nếu bảng chứa đúng bốn tổ hợp trên. Nếu có thêm `North / Partner`, Oracle tạo một nhóm thứ năm.

### 3.3. Thêm khóa nhóm làm số nhóm tăng hoặc giữ nguyên

So sánh:

~~~sql
-- Nhom theo region:
SELECT region, COUNT(*) AS rows_per_region
FROM sales
GROUP BY region;

-- Nhom theo region va channel:
SELECT region, channel, COUNT(*) AS rows_per_pair
FROM sales
GROUP BY region, channel;

-- Nhom theo region, channel va product:
SELECT region, channel, product, COUNT(*) AS rows_per_combination
FROM sales
GROUP BY region, channel, product;
~~~

Khi thêm khóa `CHANNEL` hoặc `PRODUCT`, nhóm cũ có thể được chia nhỏ hơn. Số nhóm **không thể tăng ít đi** khi bổ sung một khóa nhóm vào cùng tập dữ liệu và cùng các điều kiện lọc; nó có thể giữ nguyên nếu giá trị mới không phân biệt thêm nhóm nào.

Nếu thêm khóa không cần thiết, báo cáo có thể bị chi tiết hóa quá mức. Ví dụ người quản lý muốn doanh thu theo khu vực nhưng vô tình thêm `ORDER_ID` vào `GROUP BY`, mỗi đơn hàng có thể thành một nhóm riêng, làm báo cáo gần giống dữ liệu chi tiết.

### 3.4. Khóa nhóm ghép không phải phép nối chuỗi

Không nên thay:

~~~sql
GROUP BY region, channel
~~~

bằng:

~~~sql
GROUP BY region || channel
~~~

Hai cách không tương đương. Ví dụ:

| Region | Channel | Nối trực tiếp |
| --- | --- | --- |
| `AB` | `C` | `ABC` |
| `A` | `BC` | `ABC` |

Hai tổ hợp khác nhau có thể tạo ra cùng chuỗi nối. Thêm dấu phân cách cũng không hoàn toàn an toàn nếu chính dữ liệu có thể chứa dấu phân cách. Ngoài ra, phép nối chuỗi có quy tắc NULL riêng và làm thay đổi kiểu/ý nghĩa của khóa nhóm.

Hãy viết mỗi thành phần thành một expression riêng:

~~~sql
SELECT region, channel, COUNT(*)
FROM sales
GROUP BY region, channel;
~~~

Oracle hiểu đây là một khóa nhóm gồm hai thành phần và so sánh từng giá trị theo kiểu dữ liệu tương ứng.

### 3.5. Khóa nhóm ghép có thể chứa NULL

Giả sử một dòng có `REGION = 'North'` nhưng `CHANNEL IS NULL`. Oracle vẫn đưa dòng đó vào một nhóm có khóa (`North`, `NULL`). Những dòng có cùng tổ hợp giá trị nhóm, kể cả NULL ở cùng vị trí, sẽ thuộc cùng nhóm:

~~~sql
SELECT
    region,
    channel,
    COUNT(*) AS row_count
FROM sales
GROUP BY region, channel
ORDER BY region, channel;
~~~

Để hiển thị rõ nhóm NULL, có thể định dạng biểu thức:

~~~sql
SELECT
    NVL(region, '(unknown region)') AS region_label,
    NVL(channel, '(unknown channel)') AS channel_label,
    COUNT(*) AS row_count
FROM sales
GROUP BY
    NVL(region, '(unknown region)'),
    NVL(channel, '(unknown channel)')
ORDER BY region_label, channel_label;
~~~

Hãy chọn giá trị thay thế không thể nhầm với dữ liệu thật nếu cần giữ phân biệt. Nếu dữ liệu thực sự có nhãn `'(unknown region)'`, phép NVL trên có thể gộp nhãn thật với NULL; có thể thay bằng cờ riêng hoặc giữ NULL và xử lý ở tầng hiển thị.

## 4. Quy tắc SELECT khi dùng GROUP BY

### 4.1. Cột thường trong SELECT phải được nhóm hoặc tổng hợp

Truy vấn hợp lệ:

~~~sql
SELECT region, SUM(quantity * unit_price) AS revenue
FROM sales
GROUP BY region;
~~~

`REGION` có mặt trong `GROUP BY`; `SUM(...)` là hàm tổng hợp.

Truy vấn không hợp lệ:

~~~sql
SELECT region, product, SUM(quantity * unit_price) AS revenue
FROM sales
GROUP BY region;
~~~

`PRODUCT` không nằm trong `GROUP BY` và cũng không nằm trong hàm tổng hợp. Một nhóm `North` có thể chứa nhiều sản phẩm; Oracle không biết phải hiển thị sản phẩm nào cho một dòng tổng doanh thu của cả nhóm. Trong Oracle, lỗi thường gặp là `ORA-00979: not a GROUP BY expression`.

Sửa theo đúng mục tiêu:

~~~sql
-- Neu muon doanh thu theo tung san pham trong khu vuc:
SELECT region, product, SUM(quantity * unit_price) AS revenue
FROM sales
GROUP BY region, product;

-- Neu chi muon doanh thu theo khu vuc:
SELECT region, SUM(quantity * unit_price) AS revenue
FROM sales
GROUP BY region;
~~~

Không thêm cột vào `GROUP BY` chỉ để làm biến mất lỗi; việc đó có thể thay đổi cấp độ tổng hợp và làm sai ý nghĩa báo cáo.

### 4.2. Biểu thức SELECT phải phù hợp với khóa nhóm

Ví dụ:

~~~sql
SELECT
    UPPER(region) AS region_upper,
    COUNT(*) AS row_count
FROM sales
GROUP BY UPPER(region);
~~~

Biểu thức không tổng hợp trong `SELECT` chính là biểu thức nhóm. Nếu bạn muốn hiển thị `UPPER(region)` nhưng chỉ nhóm theo `region`, hãy viết đúng expression và hiểu việc chuẩn hóa có thể làm nhiều giá trị khác nhau về chữ hoa/thường được gom chung.

### 4.3. Alias trong GROUP BY

Để tương thích với Oracle 19c, không dựa vào alias của select list trong `GROUP BY` cùng query block:

~~~sql
-- Khong dung mau nay trong Oracle 19c:
SELECT TRUNC(sold_at, 'MM') AS sale_month,
       SUM(quantity * unit_price) AS revenue
FROM sales
GROUP BY sale_month;
~~~

Hãy lặp lại biểu thức:

~~~sql
SELECT
    TRUNC(sold_at, 'MM') AS sale_month,
    SUM(quantity * unit_price) AS revenue
FROM sales
GROUP BY TRUNC(sold_at, 'MM')
ORDER BY sale_month;
~~~

Hoặc đặt biểu thức vào inline view/CTE để alias trở thành một cột đầu vào của query block ngoài:

~~~sql
WITH sales_by_month_input AS (
    SELECT
        TRUNC(sold_at, 'MM') AS sale_month,
        quantity * unit_price AS line_revenue
    FROM sales
)
SELECT sale_month, SUM(line_revenue) AS revenue
FROM sales_by_month_input
GROUP BY sale_month
ORDER BY sale_month;
~~~

Trong query ngoài, `SALE_MONTH` là cột của inline view nên có thể dùng trực tiếp trong `GROUP BY`. Alias trong `ORDER BY` cùng query block được hỗ trợ theo quy tắc SQL Oracle thông thường.

## 5. WHERE và HAVING: lọc dòng trước hay lọc nhóm sau?

Đây là khác biệt cốt lõi khi kết hợp gom nhóm:

| Mệnh đề | Lọc đối tượng nào? | Có dùng hàm tổng hợp của nhóm trong điều kiện không? |
| --- | --- | --- |
| `WHERE` | Các dòng nguồn trước khi gom nhóm | Không dùng trực tiếp hàm tổng hợp như `SUM`/`COUNT` của nhóm |
| `HAVING` | Các nhóm sau khi hình thành | Có, ví dụ `HAVING SUM(amount) > 1000` |

### 5.1. WHERE lọc dòng trước GROUP BY

~~~sql
SELECT
    region,
    SUM(quantity * unit_price) AS revenue
FROM sales
WHERE status = 'PAID'
GROUP BY region;
~~~

Oracle chỉ đưa các dòng `PAID` vào nhóm; đơn `PENDING` hoặc `CANCELLED` không tham gia tính tổng.

### 5.2. HAVING lọc nhóm sau khi tổng hợp

~~~sql
SELECT
    region,
    SUM(quantity * unit_price) AS revenue
FROM sales
GROUP BY region
HAVING SUM(quantity * unit_price) >= 1000;
~~~

Oracle tính doanh thu cho mỗi khu vực, sau đó chỉ giữ nhóm có doanh thu ít nhất 1.000.

### 5.3. Kết hợp WHERE và HAVING

~~~sql
SELECT
    region,
    channel,
    COUNT(*) AS paid_rows,
    SUM(quantity * unit_price) AS revenue
FROM sales
WHERE status = 'PAID'
GROUP BY region, channel
HAVING SUM(quantity * unit_price) >= 500
ORDER BY revenue DESC;
~~~

Trình tự tư duy:

1. `WHERE` chỉ lấy dòng đã thanh toán.
2. `GROUP BY` gom theo khu vực và kênh.
3. `COUNT`/`SUM` tính trên các dòng còn lại trong từng nhóm.
4. `HAVING` loại nhóm có doanh thu dưới 500.
5. `ORDER BY` sắp xếp các nhóm còn lại.

### 5.4. Đừng dùng HAVING thay cho WHERE khi có thể lọc sớm

Ví dụ:

~~~sql
-- Co the viet, nhung khong dien dat muc dich loc dong ro rang:
SELECT region, COUNT(*)
FROM sales
GROUP BY region
HAVING region = 'North';
~~~

Nên viết:

~~~sql
SELECT region, COUNT(*)
FROM sales
WHERE region = 'North'
GROUP BY region;
~~~

Nếu điều kiện chỉ phụ thuộc từng dòng nguồn, `WHERE` thể hiện đúng ý định và có thể giúp Oracle giảm lượng dữ liệu phải gom nhóm. `HAVING` dành cho điều kiện phụ thuộc kết quả nhóm, chẳng hạn tổng tiền hoặc số dòng.

## 6. GROUP BY theo biểu thức

Không nhất thiết phải nhóm theo giá trị nguyên gốc của một cột. Bạn có thể nhóm theo **biểu thức xác định khóa nhóm**. Các biểu thức phổ biến gồm hàm chuỗi, phép tính số, hàm ngày giờ và `CASE`.

### 6.1. Chuẩn hóa chuỗi bằng UPPER/LOWER

Giả sử dữ liệu có `Laptop`, `LAPTOP` và `laptop`. Nếu nghiệp vụ muốn gom chúng thành cùng nhóm:

~~~sql
SELECT
    UPPER(product) AS normalized_product,
    COUNT(*) AS sale_rows,
    SUM(quantity) AS units_sold
FROM sales
GROUP BY UPPER(product)
ORDER BY normalized_product;
~~~

Oracle nhóm theo kết quả của `UPPER(product)`. Điều này có thể gộp các cách viết khác nhau thành một nhóm. Nhưng `UPPER` không phải cơ chế chuẩn hóa đầy đủ mọi ngôn ngữ hoặc mọi khác biệt dấu; hành vi còn liên quan character set, NLS/collation và yêu cầu ngôn ngữ. Nếu cần so sánh không phân biệt dấu hoặc theo ngôn ngữ, hãy thiết kế collation/normalization đúng mục đích.

### 6.2. Nhóm theo tiền tố hoặc phần chuỗi

~~~sql
SELECT
    SUBSTR(product_code, 1, 3) AS product_family,
    COUNT(*) AS item_count
FROM products
GROUP BY SUBSTR(product_code, 1, 3)
ORDER BY product_family;
~~~

Các mã có cùng ba ký tự đầu sẽ thuộc cùng nhóm. Hãy xác nhận ba ký tự đầu thực sự là quy tắc phân loại trong hệ thống; không tùy tiện cắt chuỗi nếu mã có độ dài hoặc cấu trúc khác nhau.

### 6.3. Nhóm theo khoảng giá trị số

Có thể tạo nhóm theo khoảng giá:

~~~sql
SELECT
    FLOOR(unit_price / 100) * 100 AS price_bucket,
    COUNT(*) AS sale_rows,
    SUM(quantity) AS units_sold
FROM sales
GROUP BY FLOOR(unit_price / 100) * 100
ORDER BY price_bucket;
~~~

Với đơn giá 25, 50, 90, 125, 210, biểu thức tạo các mốc 0, 100, 200. Đây là khoảng bắt đầu từ mốc 100: `0–99.99...`, `100–199.99...`, `200–299.99...`. Nếu nghiệp vụ cần nhãn hiển thị, dùng `CASE` để định nghĩa khoảng rõ ràng.

### 6.4. Nhóm theo CASE

Ví dụ phân loại giá trị đơn hàng:

~~~sql
SELECT
    CASE
        WHEN quantity * unit_price < 100 THEN 'LOW'
        WHEN quantity * unit_price < 1000 THEN 'MEDIUM'
        ELSE 'HIGH'
    END AS order_band,
    COUNT(*) AS order_count,
    SUM(quantity * unit_price) AS total_revenue
FROM sales
GROUP BY
    CASE
        WHEN quantity * unit_price < 100 THEN 'LOW'
        WHEN quantity * unit_price < 1000 THEN 'MEDIUM'
        ELSE 'HIGH'
    END
ORDER BY order_band;
~~~

Các dòng được phân vào nhóm `LOW`, `MEDIUM` hoặc `HIGH` theo biểu thức. Trong Oracle 19c, để nhóm theo alias của select list, hãy lặp lại biểu thức hoặc dùng inline view/CTE như sau:

~~~sql
WITH classified_sales AS (
    SELECT
        CASE
            WHEN quantity * unit_price < 100 THEN 'LOW'
            WHEN quantity * unit_price < 1000 THEN 'MEDIUM'
            ELSE 'HIGH'
        END AS order_band,
        quantity * unit_price AS line_amount
    FROM sales
)
SELECT
    order_band,
    COUNT(*) AS order_count,
    SUM(line_amount) AS total_revenue
FROM classified_sales
GROUP BY order_band
ORDER BY order_band;
~~~

CTE giúp định nghĩa logic phân loại một lần và tái sử dụng trong query ngoài, giảm nguy cơ viết biểu thức dài hai lần nhưng khác nhau.

### 6.5. Nhóm theo tháng/quý/năm

Nếu `SOLD_AT` là `DATE`, nhóm theo tháng:

~~~sql
SELECT
    TRUNC(sold_at, 'MM') AS month_start,
    COUNT(*) AS sale_rows,
    SUM(quantity * unit_price) AS revenue
FROM sales
GROUP BY TRUNC(sold_at, 'MM')
ORDER BY month_start;
~~~

`TRUNC(sold_at, 'MM')` đưa mọi ngày trong cùng tháng về ngày đầu tháng lúc 00:00:00. Dùng giá trị DATE đó làm khóa nhóm thường rõ nghĩa hơn việc nhóm theo chuỗi format.

Hiển thị nhãn `YYYY-MM`:

~~~sql
SELECT
    TO_CHAR(TRUNC(sold_at, 'MM'), 'YYYY-MM') AS sale_month,
    SUM(quantity * unit_price) AS revenue
FROM sales
GROUP BY TRUNC(sold_at, 'MM')
ORDER BY TRUNC(sold_at, 'MM');
~~~

Nếu nhóm theo quý:

~~~sql
SELECT
    EXTRACT(YEAR FROM sold_at) AS sale_year,
    TO_CHAR(sold_at, 'Q') AS sale_quarter,
    SUM(quantity * unit_price) AS revenue
FROM sales
GROUP BY
    EXTRACT(YEAR FROM sold_at),
    TO_CHAR(sold_at, 'Q')
ORDER BY sale_year, sale_quarter;
~~~

Hoặc dùng một biểu thức mốc quý phù hợp với kiểu dữ liệu/nghiệp vụ. Lưu ý `TO_CHAR` tạo chuỗi; nếu dùng format có tên tháng/ngày, kết quả có thể phụ thuộc `NLS_DATE_LANGUAGE`. Đối với grouping và sắp xếp thời gian, ưu tiên khóa DATE/TIMESTAMP như `TRUNC(sold_at, 'MM')`.

### 6.6. Nhóm theo biểu thức số học

~~~sql
SELECT
    EXTRACT(YEAR FROM sold_at) AS sale_year,
    EXTRACT(MONTH FROM sold_at) AS sale_month,
    COUNT(*) AS sale_rows
FROM sales
GROUP BY
    EXTRACT(YEAR FROM sold_at),
    EXTRACT(MONTH FROM sold_at)
ORDER BY sale_year, sale_month;
~~~

Ở đây khóa nhóm ghép gồm năm và tháng. Dùng cả hai để phân biệt tháng 1 của năm 2025 với tháng 1 của năm 2026; chỉ nhóm theo `EXTRACT(MONTH...)` sẽ gộp mọi tháng 1 của tất cả các năm.

## 7. Khóa nhóm ghép kết hợp với biểu thức

Bạn có thể kết hợp cột thông thường và biểu thức để xác định nhóm:

~~~sql
SELECT
    region,
    channel,
    TRUNC(sold_at, 'MM') AS sale_month,
    UPPER(product) AS product_key,
    COUNT(*) AS sale_rows,
    SUM(quantity * unit_price) AS revenue
FROM sales
GROUP BY
    region,
    channel,
    TRUNC(sold_at, 'MM'),
    UPPER(product)
ORDER BY
    region,
    channel,
    sale_month,
    product_key;
~~~

Một nhóm được xác định bởi **bốn thành phần cùng lúc**:

1. Khu vực.
2. Kênh bán.
3. Tháng giao dịch.
4. Tên sản phẩm sau khi chuyển thành chữ hoa.

Hai dòng chỉ thuộc cùng nhóm nếu tất cả bốn biểu thức nhóm cho giá trị tương ứng giống nhau theo quy tắc so sánh. Chỉ cần một thành phần khác, chúng nằm ở hai nhóm khác nhau.

### 7.1. Nhóm theo năm và tháng thay vì chuỗi YYYYMM

Hai cách:

~~~sql
-- Cach 1: hai khoa so rieng biet.
SELECT
    EXTRACT(YEAR FROM sold_at) AS sale_year,
    EXTRACT(MONTH FROM sold_at) AS sale_month,
    COUNT(*) AS row_count
FROM sales
GROUP BY
    EXTRACT(YEAR FROM sold_at),
    EXTRACT(MONTH FROM sold_at);

-- Cach 2: mot khoa DATE la dau thang.
SELECT
    TRUNC(sold_at, 'MM') AS month_start,
    COUNT(*) AS row_count
FROM sales
GROUP BY TRUNC(sold_at, 'MM');
~~~

Hai cách đều có thể biểu diễn nhóm theo tháng. Cách dùng DATE đầu tháng thuận tiện khi cần range filtering hoặc nối với calendar dimension; cách hai khóa riêng phù hợp khi báo cáo cần hai cột năm/tháng.

### 7.2. Không thêm khóa chi tiết không cần thiết

Giả sử mục tiêu là doanh thu theo khu vực và tháng:

~~~sql
SELECT region, TRUNC(sold_at, 'MM') AS sale_month,
       SUM(quantity * unit_price) AS revenue
FROM sales
GROUP BY region, TRUNC(sold_at, 'MM');
~~~

Nếu thêm `SALE_ID` vào `GROUP BY`, mỗi giao dịch có thể thành nhóm riêng:

~~~sql
-- Khong phai bao cao doanh thu theo khu vuc/thang nua:
SELECT region, TRUNC(sold_at, 'MM'), sale_id,
       SUM(quantity * unit_price)
FROM sales
GROUP BY region, TRUNC(sold_at, 'MM'), sale_id;
~~~

Hãy đặt câu hỏi: **một dòng kết quả đại diện cho đối tượng nào?** Mỗi dòng đại diện một khu vực, một cặp khu vực/kênh, một tháng hay một giao dịch? Câu trả lời xác định các khóa nhóm nên có.

## 8. Điều kiện và quy tắc với NULL

### 8.1. NULL được gom vào một nhóm

Trong `GROUP BY`, các giá trị NULL của khóa nhóm được xem là cùng một nhóm:

~~~sql
SELECT channel, COUNT(*) AS row_count
FROM sales
GROUP BY channel;
~~~

Nếu có 10 dòng `CHANNEL IS NULL`, kết quả có một nhóm NULL với `ROW_COUNT=10`. Điều này khác cách so sánh điều kiện `channel = NULL` trong `WHERE`; phép so sánh đó không trả TRUE.

Muốn lọc nhóm NULL:

~~~sql
SELECT channel, COUNT(*) AS row_count
FROM sales
WHERE channel IS NULL
GROUP BY channel;
~~~

Hoặc giữ mọi nhóm rồi hiển thị nhãn:

~~~sql
SELECT
    NVL(channel, '(not assigned)') AS channel_label,
    COUNT(*) AS row_count
FROM sales
GROUP BY NVL(channel, '(not assigned)');
~~~

### 8.2. NULL trong hàm tổng hợp

`COUNT(*)` đếm dòng kể cả khi mọi cột đều NULL. `COUNT(column)` bỏ qua NULL của cột đó. `SUM(column)` và `AVG(column)` cũng bỏ qua giá trị NULL; nếu không có giá trị số nào, kết quả là NULL.

Ví dụ:

~~~sql
SELECT
    region,
    COUNT(*) AS all_sales,
    COUNT(discount_pct) AS rows_with_discount,
    AVG(discount_pct) AS average_discount
FROM sales
GROUP BY region;
~~~

Nếu một khu vực không có giá trị `DISCOUNT_PCT` nào, `ROWS_WITH_DISCOUNT` là 0 và `AVERAGE_DISCOUNT` là NULL. Điều này có thể có nghĩa “chưa có dữ liệu giảm giá”, không nhất thiết là “giảm giá trung bình bằng 0%”.

### 8.3. NVL/COALESCE có thể thay đổi khóa nhóm

~~~sql
SELECT
    NVL(region, 'UNKNOWN') AS region_label,
    COUNT(*) AS row_count
FROM sales
GROUP BY NVL(region, 'UNKNOWN');
~~~

Mọi NULL được ánh xạ thành chuỗi `UNKNOWN`. Nếu trong dữ liệu cũng có region thật mang tên `UNKNOWN`, hai loại dòng sẽ bị gom chung. Muốn phân biệt, hãy giữ cột gốc trong nhóm và chuyển nhãn ở tầng ngoài, hoặc dùng thêm cờ biểu thị giá trị bị thiếu.

## 9. HAVING với nhiều khóa và nhiều hàm tổng hợp

Bạn có thể lọc nhóm dựa trên nhiều tiêu chí:

~~~sql
SELECT
    region,
    channel,
    COUNT(*) AS sale_rows,
    COUNT(DISTINCT product) AS product_count,
    SUM(quantity * unit_price) AS revenue
FROM sales
WHERE status = 'PAID'
GROUP BY region, channel
HAVING COUNT(*) >= 2
   AND SUM(quantity * unit_price) >= 500
ORDER BY revenue DESC;
~~~

Nhóm chỉ xuất hiện nếu có ít nhất hai dòng đã thanh toán và doanh thu đạt ngưỡng 500. Các điều kiện trong `HAVING` được đánh giá theo **mỗi nhóm**, không phải từng row riêng.

### 9.1. HAVING có thể tham chiếu biểu thức nhóm

~~~sql
SELECT
    TRUNC(sold_at, 'MM') AS sale_month,
    SUM(quantity * unit_price) AS revenue
FROM sales
GROUP BY TRUNC(sold_at, 'MM')
HAVING TRUNC(sold_at, 'MM') >= DATE '2026-01-01';
~~~

Điều kiện giữ các nhóm có mốc tháng từ tháng 1/2026 trở đi. Nếu chỉ cần lọc các dòng nguồn từ ngày đó, có thể dùng `WHERE sold_at >= DATE '2026-01-01'` trước khi nhóm để giảm lượng dòng phải tổng hợp. Hai cách tương đương về mục tiêu này khi mốc được xác định đúng, nhưng `HAVING` có thể dùng điều kiện trên kết quả tổng hợp mà `WHERE` không thể.

### 9.2. HAVING và alias

Để tương thích Oracle 19c, không dựa vào alias của hàm tổng hợp trong `HAVING` cùng query block:

~~~sql
-- Khong dung mau alias trong HAVING tren Oracle 19c:
SELECT region, SUM(quantity * unit_price) AS revenue
FROM sales
GROUP BY region
HAVING revenue > 1000;
~~~

Viết:

~~~sql
SELECT region, SUM(quantity * unit_price) AS revenue
FROM sales
GROUP BY region
HAVING SUM(quantity * unit_price) > 1000;
~~~

Hoặc bọc query:

~~~sql
WITH revenue_by_region AS (
    SELECT region, SUM(quantity * unit_price) AS revenue
    FROM sales
    GROUP BY region
)
SELECT region, revenue
FROM revenue_by_region
WHERE revenue > 1000;
~~~

Trong query ngoài, `REVENUE` là cột đầu vào thông thường của CTE, vì vậy dùng `WHERE` là phù hợp. Tên alias không phải biến toàn cục dùng được ở mọi mệnh đề của query block.

## 10. Tổng hợp có điều kiện bằng CASE

Không cần chạy nhiều truy vấn riêng cho từng trạng thái. Có thể tính nhiều chỉ số trong cùng nhóm:

~~~sql
SELECT
    region,
    COUNT(*) AS total_rows,
    SUM(CASE WHEN status = 'PAID' THEN 1 ELSE 0 END) AS paid_rows,
    SUM(CASE WHEN status = 'PENDING' THEN 1 ELSE 0 END) AS pending_rows,
    SUM(CASE
            WHEN status = 'PAID'
            THEN quantity * unit_price
            ELSE 0
        END) AS paid_revenue
FROM sales
GROUP BY region
ORDER BY region;
~~~

Mỗi dòng đầu vào chỉ đóng góp vào cột tổng hợp tương ứng theo điều kiện `CASE`. Đây là kỹ thuật **conditional aggregation**, hữu ích cho báo cáo có nhiều chỉ số theo cùng một chiều nhóm.

Nếu dùng `SUM(CASE WHEN ... THEN amount END)` mà không có `ELSE 0`, những dòng không thỏa điều kiện trả NULL; `SUM` bỏ qua chúng. Nếu cả nhóm không có dòng nào thỏa, kết quả tổng có thể là NULL. Thêm `ELSE 0` nếu muốn biểu diễn “không có doanh thu” thành 0.

### 10.1. Đếm theo điều kiện

~~~sql
SELECT
    region,
    COUNT(CASE WHEN status = 'PAID' THEN 1 END) AS paid_count,
    COUNT(CASE WHEN status = 'CANCELLED' THEN 1 END) AS cancelled_count
FROM sales
GROUP BY region;
~~~

`COUNT(expression)` chỉ đếm khi expression khác NULL. Đây là cách khác để đếm các dòng thỏa điều kiện.

### 10.2. Tổng hợp theo nhiều nhóm và nhiều điều kiện

~~~sql
SELECT
    region,
    channel,
    SUM(CASE WHEN status = 'PAID'
             THEN quantity * unit_price ELSE 0 END) AS paid_revenue,
    SUM(CASE WHEN status = 'PENDING'
             THEN quantity * unit_price ELSE 0 END) AS pending_value
FROM sales
GROUP BY region, channel
ORDER BY region, channel;
~~~

Khóa nhóm vẫn là cặp khu vực/kênh; các biểu thức CASE tạo ra những chỉ số khác nhau trong từng nhóm.

## 11. DISTINCT trong hàm tổng hợp và các tổ hợp khóa

### 11.1. COUNT(DISTINCT ...)

~~~sql
SELECT
    region,
    COUNT(DISTINCT product) AS unique_products,
    COUNT(*) AS sale_rows
FROM sales
GROUP BY region;
~~~

`COUNT(DISTINCT product)` đếm số giá trị sản phẩm khác nhau trong từng khu vực, bỏ qua NULL. Nó không thay đổi khóa nhóm; `REGION` vẫn là chiều nhóm.

### 11.2. Đếm tổ hợp nhiều cột khác nhau

Khi muốn đếm số cặp khác nhau (`REGION`, `CHANNEL`) trong một tập dữ liệu, không nên ghép hai cột thành chuỗi rồi dùng `COUNT(DISTINCT region || channel)` vì có thể va chạm, xử lý NULL và chuyển kiểu không như mong muốn.

Dùng inline view:

~~~sql
SELECT COUNT(*) AS distinct_region_channel_pairs
FROM (
    SELECT DISTINCT region, channel
    FROM sales
);
~~~

Hoặc nếu cần số tổ hợp theo từng khu vực, `GROUP BY region` kết hợp với một query con distinct tương ứng. Cách dùng `SELECT DISTINCT col1, col2` giữ riêng từng thành phần của khóa ghép.

## 12. Biểu thức nhóm với ngày giờ và múi giờ

### 12.1. DATE và TIMESTAMP

`TRUNC(date_value, 'MM')` là mẫu quen thuộc khi nhóm theo tháng. Nếu cột là `TIMESTAMP`, Oracle có thể cần chuyển đổi kiểu hoặc dùng biểu thức timestamp phù hợp. Hãy kiểm tra kiểu cột và không dựa vào implicit conversion trong hệ thống nhạy cảm về độ chính xác.

Với cột `TIMESTAMP WITH TIME ZONE`, trước khi nhóm theo ngày/tháng, cần xác định **ngày theo múi giờ nào**:

~~~sql
SELECT
    TRUNC(CAST(event_time AT TIME ZONE '+07:00' AS DATE)) AS local_day,
    COUNT(*) AS event_count
FROM app_events
GROUP BY TRUNC(CAST(event_time AT TIME ZONE '+07:00' AS DATE))
ORDER BY local_day;
~~~

Ý nghĩa: đưa instant về biểu diễn offset +07:00 rồi lấy phần ngày để nhóm. Nếu nghiệp vụ dùng timezone region có DST, hãy thay offset cố định bằng region thích hợp và kiểm thử theo ngày cụ thể. Không nhóm theo ngày server nếu báo cáo yêu cầu ngày của người dùng ở vùng khác.

### 12.2. Không nhóm theo chuỗi ngày phụ thuộc NLS

~~~sql
-- Co the phu thuoc NLS_DATE_LANGUAGE/format:
SELECT TO_CHAR(sold_at, 'MON') AS month_name,
       SUM(quantity * unit_price)
FROM sales
GROUP BY TO_CHAR(sold_at, 'MON');
~~~

Truy vấn trên còn gộp tháng cùng tên của **mọi năm** và có thể trả tên tháng theo ngôn ngữ phiên. Nếu muốn doanh thu từng tháng theo thời gian:

~~~sql
SELECT
    TRUNC(sold_at, 'MM') AS month_start,
    SUM(quantity * unit_price) AS revenue
FROM sales
GROUP BY TRUNC(sold_at, 'MM')
ORDER BY month_start;
~~~

Định dạng nhãn sau khi đã có khóa DATE:

~~~sql
SELECT
    TO_CHAR(month_start, 'YYYY-MM') AS month_label,
    revenue
FROM (
    SELECT
        TRUNC(sold_at, 'MM') AS month_start,
        SUM(quantity * unit_price) AS revenue
    FROM sales
    GROUP BY TRUNC(sold_at, 'MM')
)
ORDER BY month_start;
~~~

## 13. GROUP BY và truy vấn con/CTE

CTE có thể giúp tách các bước tính toán, đặt tên biểu thức nhóm và tránh lặp logic:

~~~sql
WITH normalized_sales AS (
    SELECT
        UPPER(TRIM(region)) AS region_key,
        UPPER(TRIM(channel)) AS channel_key,
        TRUNC(sold_at, 'MM') AS month_key,
        quantity * unit_price AS amount
    FROM sales
    WHERE status = 'PAID'
),
monthly_summary AS (
    SELECT
        region_key,
        channel_key,
        month_key,
        COUNT(*) AS sale_rows,
        SUM(amount) AS revenue
    FROM normalized_sales
    GROUP BY region_key, channel_key, month_key
)
SELECT
    region_key,
    channel_key,
    month_key,
    sale_rows,
    revenue
FROM monthly_summary
WHERE revenue >= 500
ORDER BY month_key, region_key, channel_key;
~~~

Các bước:

1. `NORMALIZED_SALES` lọc trạng thái và tạo khóa chuẩn hóa.
2. `MONTHLY_SUMMARY` gom nhóm theo ba khóa và tính chỉ số.
3. Query ngoài lọc kết quả tổng hợp bằng `WHERE` vì `REVENUE` đã là cột của CTE.

CTE là cách tổ chức SQL dễ đọc; không mặc định mỗi CTE luôn được materialize thành bảng tạm. Oracle optimizer có thể inline hoặc biến đổi query tùy plan.

## 14. Giới hạn và lưu ý khi chọn biểu thức nhóm

### 14.1. Kiểu dữ liệu và biểu thức không hỗ trợ

Không phải mọi datatype đều có thể dùng làm khóa `GROUP BY`. Các kiểu LOB như `CLOB`/`BLOB` không thể được nhóm trực tiếp theo cách thông thường; một số kiểu phức hợp hoặc biểu thức có quy tắc riêng. Nếu cần phân loại nội dung LOB, phải thiết kế khóa thay thế phù hợp (ví dụ metadata, mã định danh, hash có xử lý nguy cơ va chạm), không dùng một đoạn đầu CLOB rồi giả định nó đại diện duy nhất toàn bộ nội dung.

Biểu thức nhóm cũng cần xác định được giá trị theo dữ liệu đầu vào. Không đưa một phép biến đổi không cần thiết vào `GROUP BY` nếu nó làm mất thông tin phân biệt hoặc tạo ra nhóm sai.

### 14.2. Độ chính xác số và làm tròn

Nhóm theo một biểu thức số có thể khác với nhóm theo giá trị gốc:

~~~sql
SELECT ROUND(unit_price, 0) AS rounded_price,
       COUNT(*) AS row_count
FROM sales
GROUP BY ROUND(unit_price, 0);
~~~

Giá trị 10.2 và 10.4 có thể cùng được làm tròn thành 10; chúng được gom chung. Nếu nghiệp vụ muốn nhóm theo khoảng, hãy dùng biểu thức khoảng rõ ràng như `FLOOR(unit_price / 10)` thay vì tùy tiện làm tròn.

Với tiền tệ, không làm tròn ở cấp dòng trước khi tổng nếu quy tắc nghiệp vụ yêu cầu tính tổng chính xác rồi mới làm tròn (hoặc ngược lại). Thứ tự phép tính có thể ảnh hưởng kết quả.

### 14.3. Biểu thức chuỗi và collation

Nhóm theo `UPPER(name)` có thể gom nhiều kiểu chữ nhưng không tự giải quyết mọi khác biệt dấu, Unicode normalization hoặc collation. Nếu ứng dụng có dữ liệu đa ngôn ngữ, cần thống nhất cách chuẩn hóa trước khi lưu hoặc dùng collation phù hợp. Đừng giả định hai chuỗi trông giống nhau trên màn hình luôn được Oracle xem là bằng nhau.

### 14.4. Không dùng GROUP BY để che dữ liệu sai

Nếu join làm nhân bản dòng, thêm `GROUP BY`/`SUM(DISTINCT amount)` để làm số tổng “đẹp” có thể che lỗi join. Hãy kiểm tra cardinality và quan hệ khóa trước:

- Một khách hàng có nhiều đơn hàng là quan hệ 1-n.
- Một đơn hàng có nhiều dòng chi tiết là quan hệ 1-n khác.
- Join hai bảng detail độc lập có thể tạo tích số dòng nếu thiếu điều kiện nối.

Hàm `SUM(DISTINCT amount)` chỉ bỏ giá trị amount trùng, **không sửa lỗi nhân bản row do join**; hai đơn hàng khác nhau có cùng số tiền vẫn có thể bị gộp sai khi dùng DISTINCT. Phải xác định đúng grain (mức chi tiết) của dữ liệu trước khi tổng hợp.

## 15. Những lỗi thường gặp

| Lỗi/biểu hiện | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `ORA-00979: not a GROUP BY expression` | Cột/biểu thức không tổng hợp trong SELECT không phù hợp với khóa nhóm | Xác định cấp độ kết quả; thêm đúng biểu thức nhóm hoặc tổng hợp cột |
| `ORA-00937: not a single-group group function` | Trộn aggregate với cột thường mà thiếu GROUP BY phù hợp | Viết GROUP BY cho các chiều cần hiển thị |
| `ORA-00904` khi dùng alias trong GROUP BY | Alias không được phân giải theo cú pháp query block/phiên bản | Lặp expression hoặc bọc trong CTE/inline view |
| Có quá nhiều dòng nhóm | Thêm khóa quá chi tiết, ví dụ ID giao dịch | Xác định một dòng kết quả đại diện cho đối tượng nào |
| Thiếu nhóm NULL | Dùng WHERE lọc NULL hoặc nối chuỗi làm mất NULL | Kiểm tra điều kiện và biểu thức nhóm; dùng IS NULL khi lọc |
| Tổng doanh thu lớn bất thường | JOIN làm nhân bản dòng nguồn | Kiểm tra grain, khóa nối và cardinality trước GROUP BY |
| Kết quả thay đổi thứ tự | Không có ORDER BY | Thêm ORDER BY tường minh |
| Nhóm tên không gộp như mong muốn | Khác biệt khoảng trắng, chữ hoa/thường, dấu hoặc normalization | Chuẩn hóa bằng biểu thức có chủ đích và kiểm thử dữ liệu thật |
| Tổng/AVG trả NULL | Mọi giá trị trong nhóm đều NULL hoặc không có giá trị hợp lệ | Phân biệt NULL với 0; dùng NVL/COALESCE chỉ khi phù hợp |
| Tháng cùng tên bị gộp qua nhiều năm | Chỉ nhóm theo tên/tháng, không có năm | Dùng TRUNC(date,'MM') hoặc nhóm theo cả YEAR và MONTH |

### 15.1. Quy trình đọc lỗi ORA-00979

Ví dụ lỗi:

~~~sql
SELECT region, channel, product, SUM(quantity)
FROM sales
GROUP BY region, channel;
~~~

Phân tích:

1. `REGION` có trong GROUP BY.
2. `CHANNEL` có trong GROUP BY.
3. `SUM(quantity)` là aggregate.
4. `PRODUCT` là cột thường không được nhóm.

Nếu muốn báo cáo theo sản phẩm, thêm `PRODUCT` vào khóa:

~~~sql
GROUP BY region, channel, product;
~~~

Nếu không cần product, bỏ nó khỏi SELECT. Không dùng `MAX(product)` chỉ để vượt lỗi trừ khi nghiệp vụ thực sự muốn lấy giá trị lớn nhất theo thứ tự so sánh của chuỗi.

### 15.2. Kiểm tra grain trước khi sửa

Hãy viết câu mô tả:

> Mỗi dòng kết quả đại diện cho một ________.

Ví dụ:

- Một khu vực.
- Một khu vực và một kênh.
- Một khu vực, kênh và tháng.
- Một khách hàng trong một tháng.

Sau đó đối chiếu từng cột không tổng hợp trong SELECT với mô tả này. Đây là cách hiệu quả để tránh thêm nhầm khóa nhóm.

## 16. Bài thực hành tổng hợp

Phần này tạo bảng lab có nhiều khu vực, kênh, sản phẩm, tháng và giá trị NULL. Thực hiện trong schema riêng; nếu bảng đã tồn tại, đổi tên lab thay vì xóa bảng không rõ chủ sở hữu.

### Bước 1 — Tạo bảng

~~~sql
CREATE TABLE group_by_lab (
    sale_id     NUMBER PRIMARY KEY,
    region      VARCHAR2(20 CHAR),
    channel     VARCHAR2(20 CHAR),
    product     VARCHAR2(30 CHAR),
    sold_at     DATE NOT NULL,
    quantity    NUMBER(8,2) NOT NULL,
    unit_price  NUMBER(10,2) NOT NULL,
    status      VARCHAR2(12 CHAR) NOT NULL
);
~~~

### Bước 2 — Thêm dữ liệu mẫu

~~~sql
INSERT INTO group_by_lab VALUES
    (1, 'North', 'Online', 'Laptop', DATE '2026-01-02', 1, 1000, 'PAID');

INSERT INTO group_by_lab VALUES
    (2, 'North', 'Store', 'Laptop', DATE '2026-01-03', 2, 1000, 'PAID');

INSERT INTO group_by_lab VALUES
    (3, 'North', 'Online', 'Mouse', DATE '2026-01-05', 3, 25, 'PAID');

INSERT INTO group_by_lab VALUES
    (4, 'South', 'Online', 'Laptop', DATE '2026-01-07', 1, 1000, 'PAID');

INSERT INTO group_by_lab VALUES
    (5, 'South', 'Store', 'Mouse', DATE '2026-01-09', 4, 25, 'PENDING');

INSERT INTO group_by_lab VALUES
    (6, 'South', 'Online', 'Mouse', DATE '2026-01-15', 2, 25, 'PAID');

INSERT INTO group_by_lab VALUES
    (7, NULL, 'Online', 'Mouse', DATE '2026-02-02', 1, 25, 'PAID');

INSERT INTO group_by_lab VALUES
    (8, 'North', NULL, 'Laptop', DATE '2026-02-05', 1, 1000, 'PAID');

INSERT INTO group_by_lab VALUES
    (9, 'North', 'Online', 'Keyboard', DATE '2026-02-07', 2, 50, 'PAID');

INSERT INTO group_by_lab VALUES
    (10, 'north', 'ONLINE', 'laptop', DATE '2026-02-10', 1, 1000, 'PAID');

COMMIT;
~~~

Hai dòng cuối có giá trị NULL và kiểu viết hoa/thường khác nhau để quan sát cách nhóm.

### Bước 3 — Gom nhóm theo một khóa

~~~sql
SELECT region, COUNT(*) AS row_count
FROM group_by_lab
GROUP BY region
ORDER BY region;
~~~

Đếm số dòng theo khu vực. Các dòng `REGION IS NULL` nằm trong một nhóm NULL riêng.

### Bước 4 — Gom nhóm theo khóa ghép

~~~sql
SELECT
    region,
    channel,
    COUNT(*) AS sale_rows,
    SUM(quantity * unit_price) AS revenue
FROM group_by_lab
GROUP BY region, channel
ORDER BY region, channel;
~~~

Quan sát các cặp `(North, Online)`, `(North, Store)`, `(North, NULL)` và `(NULL, Online)`. Mỗi cặp khác nhau tạo một nhóm riêng.

### Bước 5 — Lọc dòng trước khi gom nhóm

~~~sql
SELECT
    region,
    channel,
    COUNT(*) AS paid_rows,
    SUM(quantity * unit_price) AS paid_revenue
FROM group_by_lab
WHERE status = 'PAID'
GROUP BY region, channel
ORDER BY region, channel;
~~~

Đơn `PENDING` không được đưa vào các tổng hợp.

### Bước 6 — Lọc nhóm bằng HAVING

~~~sql
SELECT
    region,
    SUM(quantity * unit_price) AS revenue
FROM group_by_lab
GROUP BY region
HAVING SUM(quantity * unit_price) >= 500
ORDER BY revenue DESC;
~~~

Chỉ các nhóm khu vực có doanh thu tổng ít nhất 500 được trả về.

### Bước 7 — Gom theo tháng

~~~sql
SELECT
    TO_CHAR(TRUNC(sold_at, 'MM'), 'YYYY-MM') AS sale_month,
    COUNT(*) AS sale_rows,
    SUM(quantity * unit_price) AS revenue
FROM group_by_lab
GROUP BY TRUNC(sold_at, 'MM')
ORDER BY TRUNC(sold_at, 'MM');
~~~

Tháng 1 và tháng 2 là hai nhóm riêng.

### Bước 8 — Gom theo biểu thức CASE

~~~sql
SELECT
    CASE
        WHEN quantity * unit_price < 100 THEN 'LOW'
        WHEN quantity * unit_price < 1000 THEN 'MEDIUM'
        ELSE 'HIGH'
    END AS amount_band,
    COUNT(*) AS sale_rows
FROM group_by_lab
GROUP BY
    CASE
        WHEN quantity * unit_price < 100 THEN 'LOW'
        WHEN quantity * unit_price < 1000 THEN 'MEDIUM'
        ELSE 'HIGH'
    END
ORDER BY amount_band;
~~~

Các giao dịch được gom theo khoảng giá trị của dòng.

### Bước 9 — Chuẩn hóa chuỗi trước khi nhóm

~~~sql
SELECT
    UPPER(product) AS product_key,
    COUNT(*) AS sale_rows,
    SUM(quantity) AS units_sold
FROM group_by_lab
GROUP BY UPPER(product)
ORDER BY product_key;
~~~

`Laptop` và `laptop` được gom vào cùng nhóm `LAPTOP`; điều này chỉ đúng với quy tắc chuẩn hóa mà bạn chủ động chọn.

### Bước 10 — Conditional aggregation

~~~sql
SELECT
    region,
    SUM(CASE WHEN status = 'PAID'
             THEN quantity * unit_price ELSE 0 END) AS paid_revenue,
    SUM(CASE WHEN status = 'PENDING'
             THEN quantity * unit_price ELSE 0 END) AS pending_revenue
FROM group_by_lab
GROUP BY region
ORDER BY region;
~~~

Mỗi nhóm khu vực có hai chỉ số riêng, không cần chạy hai truy vấn độc lập.

### Bước 11 — Dọn bảng lab (tùy chọn)

~~~sql
-- Chi chay neu chac chan bang nay la lab cua ban va khong can du lieu nua.
DROP TABLE group_by_lab PURGE;
~~~

`PURGE` bỏ qua recycle bin. Không dùng bước này nếu muốn giữ bảng để tiếp tục luyện tập hoặc nếu bảng không thuộc phạm vi lab của bạn.

## 17. Câu hỏi tự kiểm tra

1. `GROUP BY region, channel` tạo nhóm theo khu vực và kênh độc lập hay theo từng cặp giá trị?
2. Nếu thêm `PRODUCT` vào khóa nhóm, số nhóm có thể thay đổi như thế nào?
3. Vì sao `GROUP BY region || channel` có thể làm gộp nhầm hai tổ hợp khác nhau?
4. Trong cùng một nhóm có 5 dòng nhưng chỉ 3 email khác NULL, `COUNT(*)` và `COUNT(email)` trả về bao nhiêu?
5. `SUM(amount)` trả gì nếu mọi amount trong nhóm đều NULL?
6. Tại sao Oracle không cho chọn `PRODUCT` không tổng hợp khi chỉ `GROUP BY REGION`?
7. `WHERE` và `HAVING` khác nhau ở thời điểm lọc nào?
8. Muốn lọc nhóm có doanh thu trên 1.000, nên dùng `WHERE` hay `HAVING`?
9. `GROUP BY TRUNC(sold_at, 'MM')` khác nhóm theo `TO_CHAR(sold_at, 'MON')` ở điểm nào?
10. Khi `CHANNEL` là NULL, các dòng đó được phân nhóm như thế nào?
11. Vì sao không nên dùng `NVL(region, 'UNKNOWN')` nếu dữ liệu thật có thể chứa region tên UNKNOWN?
12. Trong Oracle 19c, làm thế nào dùng alias cho biểu thức nhóm mà không lặp biểu thức trong GROUP BY?
13. `UPPER(product)` có bảo đảm gom mọi chuỗi tiếng Việt khác dấu thành cùng nhóm không?
14. Vì sao `SUM(DISTINCT amount)` không phải cách đúng để sửa tổng tiền bị nhân đôi do JOIN?
15. Nếu báo cáo cần doanh thu theo năm và tháng, tại sao chỉ `GROUP BY EXTRACT(MONTH FROM sold_at)` là chưa đủ?

**Gợi ý trả lời:**

1. Theo từng cặp giá trị region/channel.
2. Có thể tăng hoặc giữ nguyên, không giảm.
3. Vì hai cặp khác nhau có thể tạo cùng chuỗi nối; dữ liệu có thể chứa dấu phân cách.
4. 5 và 3.
5. NULL.
6. Một nhóm có thể chứa nhiều sản phẩm; Oracle không biết chọn giá trị nào.
7. WHERE lọc dòng trước nhóm; HAVING lọc nhóm sau tổng hợp.
8. HAVING.
9. TRUNC tạo khóa DATE đầu tháng có cả năm; MON chỉ tạo tên tháng và có thể gộp nhiều năm/phụ thuộc NLS.
10. Các dòng cùng tổ hợp khóa có NULL ở vị trí channel vào một nhóm.
11. Vì có thể gộp NULL với giá trị UNKNOWN thật.
12. Dùng inline view/CTE để alias trở thành cột đầu vào của query ngoài.
13. Không; UPPER xử lý chữ hoa/thường, không phải phép chuẩn hóa bỏ dấu toàn diện.
14. Vì các giao dịch khác nhau có cùng amount có thể bị gộp sai; phải sửa cardinality/join.
15. Tháng 1 của nhiều năm sẽ bị gộp chung nếu thiếu khóa năm.

## Tài liệu Oracle tham khảo

- [Oracle Database SQL Language Reference — SELECT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SELECT.html): cú pháp `GROUP BY`, `HAVING` và quy tắc select list.
- [Oracle Database SQL Language Reference — Aggregate Functions](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Aggregate-Functions.html): hành vi các hàm tổng hợp và cách xử lý NULL.
- [Oracle Database SQL Language Reference — COUNT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/COUNT.html): `COUNT(*)`, `COUNT(expr)` và `COUNT(DISTINCT ...)`.
- [Oracle Database SQL Language Reference — GROUPING](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/GROUPING.html): hàm liên quan đến các phép mở rộng nhóm nâng cao.
- [Oracle Database SQL Language Reference — TRUNC (date)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/TRUNC-date.html): nhóm và chuẩn hóa ngày theo tháng/năm.
