# Giảm cột và số hàng trả về từ sớm mà vẫn giữ đúng kết quả

## 1. Vì sao cần giảm dữ liệu càng sớm càng tốt?

Một truy vấn có thể trả về vài chục dòng nhưng phải đọc, nối, sắp xếp hoặc truyền qua nhiều toán tử hàng triệu dòng trung gian. Mỗi dòng mang càng nhiều cột thì bộ nhớ, CPU, I/O và băng thông mạng càng phải xử lý nhiều dữ liệu. Nếu có thể loại bỏ những cột không cần thiết và lọc những dòng không thuộc kết quả ngay gần nguồn dữ liệu, các bước phía sau thường nhẹ hơn.

Hai kỹ thuật nền tảng là **column pruning/projection pushdown** (chỉ giữ các cột cần thiết) và **predicate pushdown/selection pushdown** (đẩy điều kiện lọc xuống gần nơi đọc dữ liệu). Chúng giúp giảm độ rộng hàng, số dòng và kích thước dữ liệu trung gian trước khi join, sort, aggregate hoặc gửi kết quả về ứng dụng.

Trong tối ưu hiệu năng cơ sở dữ liệu, mục tiêu là giảm công việc vật lý trong khi giữ nguyên ngữ nghĩa của câu SQL: cùng tập kết quả, cùng số lần xuất hiện của mỗi dòng, cùng giá trị NULL, cùng thứ tự khi truy vấn yêu cầu thứ tự và cùng quy tắc phân trang. Một phép viết lại có vẻ nhanh hơn nhưng làm mất dòng, nhân bản dòng hoặc thay đổi kết quả không phải là tối ưu đúng.

Bài học này trình bày cách giảm cột và số dòng từ sớm, cách đẩy lọc qua các bước join và aggregate, cách dùng `EXISTS`, cách xử lý outer join, `DISTINCT`, window function và phân trang, cùng quy trình kiểm chứng bằng execution plan và số liệu thực tế. Bộ tối ưu có thể tự thực hiện một số phép biến đổi; việc viết SQL rõ ràng giúp thể hiện đúng ý định và làm cho kế hoạch dễ phân tích hơn.

## 2. Hai hướng giảm dữ liệu: chiều rộng và số lượng

### 2.1. Giảm chiều rộng hàng bằng projection

Projection là phép chọn các cột cần giữ lại. Nếu truy vấn chỉ cần `order_id`, `created_at` và `total_amount`, việc đọc thêm mô tả sản phẩm, nội dung JSON hoặc dữ liệu nhị phân lớn có thể làm tăng lượng dữ liệu phải giải mã và truyền qua các toán tử.

Ví dụ:

```sql
-- Lấy tất cả cột dù ứng dụng chỉ dùng ba cột
SELECT *
FROM orders
WHERE customer_id = :customer_id;

-- Chỉ lấy những cột thực sự cần
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = :customer_id;
```

Truy vấn thứ hai thể hiện rõ dữ liệu đầu ra cần thiết. Engine có thể tận dụng chỉ mục bao phủ nếu chỉ mục chứa các cột cần thiết và điều kiện phù hợp. Ngay cả khi vẫn phải đọc trang bảng, giảm cột có thể giảm giải mã, cấp phát bộ nhớ, kích thước hàng trung gian và lượng dữ liệu truyền qua mạng.

### 2.2. Giảm số lượng hàng bằng predicate

Selection là phép lọc các hàng thỏa điều kiện. Ví dụ, nếu báo cáo chỉ lấy đơn hàng của một khách hàng trong một tháng, hãy lọc theo khách hàng và khoảng thời gian càng gần nguồn dữ liệu càng tốt.

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = :customer_id
  AND created_at >= :from_time
  AND created_at <  :to_time;
```

Điều kiện lọc trực tiếp trên cột có thể giúp bộ tối ưu dùng index seek/range scan hoặc partition pruning nếu kiểu dữ liệu, chỉ mục, phân vùng và thống kê phù hợp. Dù vậy, điều kiện có thể dùng chỉ mục không đồng nghĩa engine luôn phải chọn index; nếu phần lớn bảng thỏa điều kiện, quét tuần tự vẫn có thể rẻ hơn.

### 2.3. Tác động kết hợp

Dung lượng dữ liệu trung gian có thể ước lượng sơ bộ bằng:

\[
\text{Dữ liệu trung gian} \approx \text{số hàng} \times \text{độ rộng hàng trung bình}
\]

Giảm số hàng và giảm độ rộng hàng thường có tác động nhân lên nhau. Ví dụ, một bước join nhận 500.000 hàng, mỗi hàng rộng 400 byte, tương đương khoảng 200 MB dữ liệu thô. Nếu lọc sớm còn 20.000 hàng và chỉ giữ cột làm hàng rộng 80 byte, dữ liệu thô chỉ còn khoảng 1,6 MB. Đây là ước lượng đơn giản; cấu trúc hash, sort, tuple header, alignment và overhead bộ nhớ làm kích thước thực khác đi.

Giảm dữ liệu trước join hoặc sort đặc biệt có ích vì những toán tử này có thể cần giữ dữ liệu trong bộ nhớ, tạo hash table, sắp xếp hoặc ghi spill ra vùng tạm khi vượt ngân sách.

## 3. Column pruning và projection pushdown

### 3.1. Chỉ chọn cột đầu ra cần thiết

Tránh `SELECT *` trong truy vấn ứng dụng, API và báo cáo nếu chỉ dùng một phần cột. Chọn cột rõ ràng giúp:

- Giảm số byte đọc và truyền về ứng dụng.
- Tránh tải cột LOB, JSON hoặc dữ liệu lớn không cần thiết.
- Giảm độ rộng hàng trong sort, hash join, aggregate và materialize.
- Tăng khả năng sử dụng covering index hoặc index-only access.
- Giảm phụ thuộc vào schema khi bảng được bổ sung cột mới.

Tuy nhiên, không phải cột nào không xuất hiện trong `SELECT` cũng có thể bỏ khỏi các bước trước đó. Một cột vẫn cần thiết nếu được dùng trong `WHERE`, `JOIN`, `GROUP BY`, `HAVING`, `ORDER BY`, biểu thức window hoặc điều kiện phân nhánh. Bộ tối ưu phải giữ cột cho đến toán tử cuối cùng cần dùng nó.

### 3.2. Đẩy projection xuống gần nguồn dữ liệu

Giả sử `order_items` có cột `line_total`, truy vấn nối `orders` và `order_items` nhưng báo cáo chỉ cần mã đơn hàng, thời điểm và tiền của từng dòng. Ta có thể giới hạn các cột đầu vào trước khi join:

```sql
SELECT o.order_id, o.created_at, i.line_total
FROM (
    SELECT order_id, created_at
    FROM orders
    WHERE created_at >= :from_time
      AND created_at <  :to_time
) AS o
JOIN (
    SELECT order_id, line_total
    FROM order_items
    WHERE is_cancelled = FALSE
) AS i
  ON i.order_id = o.order_id;
```

Các subquery ở đây minh họa ranh giới logic của dữ liệu cần thiết. Bộ tối ưu có thể inline chúng và thực hiện projection/predicate pushdown tự động. Điều quan trọng là không mang các cột lớn hoặc không dùng qua join nếu không cần.

### 3.3. Projection và chỉ mục bao phủ

Một covering index chứa các cột cần để lọc, join và trả kết quả. Nếu truy vấn chỉ yêu cầu các cột có trong chỉ mục, engine có thể đọc từ leaf page mà không cần quay lại trang dữ liệu cho từng hàng, tùy cơ chế visibility và loại chỉ mục.

Ví dụ, truy vấn:

```sql
SELECT order_id, created_at
FROM orders
WHERE customer_id = :customer_id
  AND created_at >= :from_time
  AND created_at <  :to_time;
```

có thể được hỗ trợ bởi chỉ mục ghép bắt đầu bằng `(customer_id, created_at)` và chứa `order_id` theo cách phù hợp với hệ quản trị. Cần cân nhắc chi phí thêm cột vào chỉ mục: index rộng hơn chiếm dung lượng, giảm mật độ trang, tăng chi phí ghi và bảo trì cache. Chỉ thêm cột khi workload và phép đo cho thấy lợi ích.

## 4. Predicate pushdown: lọc gần nguồn dữ liệu

### 4.1. Ý tưởng đại số quan hệ

Trong đại số quan hệ, phép lọc thường được ký hiệu là \(\sigma\), còn phép chiếu cột là \(\pi\). Khi một điều kiện chỉ tham chiếu đến một bảng đầu vào, phép lọc có thể được thực hiện trước khi join với bảng khác mà vẫn giữ kết quả của inner join:

\[
\sigma_{P(A)}(A \bowtie B) = \sigma_{P(A)}(A) \bowtie B
\]

Ở đây, \(P(A)\) là điều kiện chỉ dùng cột của quan hệ A. Tương tự, nếu các cột bị loại không được dùng trong điều kiện nối, lọc, nhóm hoặc đầu ra, phép chiếu có thể được đẩy xuống trước join để giảm độ rộng dữ liệu.

Các đẳng thức này giúp hiểu nguyên lý, nhưng không thể áp dụng máy móc cho mọi cấu trúc SQL. Outer join, phép tổng hợp, window function, DISTINCT, LIMIT, phép toán tập hợp và biểu thức không xác định có thể làm thay đổi điều kiện tương đương.

### 4.2. Lọc trước khi join

Ví dụ, cần lấy các đơn hàng đã hoàn tất trong một khoảng thời gian và thông tin khách hàng tương ứng:

```sql
SELECT o.order_id, o.created_at, c.customer_name
FROM orders AS o
JOIN customers AS c
  ON c.customer_id = o.customer_id
WHERE o.status = 'COMPLETED'
  AND o.created_at >= :from_time
  AND o.created_at <  :to_time;
```

Bộ tối ưu có thể đẩy hai điều kiện trên `orders` xuống trước phép join. Nếu bảng `orders` rất lớn nhưng chỉ một tỷ lệ nhỏ dòng thỏa điều kiện, join sẽ xử lý ít dòng hơn. Việc viết điều kiện trực tiếp trên bảng nguồn giúp ý định lọc rõ ràng; vẫn cần xem execution plan để xác nhận engine đã thực hiện pushdown.

### 4.3. Điều kiện sargable hỗ trợ pushdown

Điều kiện trực tiếp trên cột thường dễ chuyển thành range hoặc seek hơn điều kiện bọc cột bằng hàm:

```sql
-- Có thể làm khó việc dùng index thường trên created_at
WHERE DATE(created_at) = :target_date

-- Khoảng nửa mở, có thể tìm theo index thời gian
WHERE created_at >= :day_start
  AND created_at <  :next_day_start
```

Hai cách chỉ tương đương nếu ranh giới được tính đúng theo kiểu timestamp và timezone nghiệp vụ. Tương tự, kiểu tham số phải tương thích với kiểu cột để tránh chuyển đổi ngầm định không mong muốn.

## 5. Giảm dữ liệu trước và trong phép nối

### 5.1. Lọc từng nhánh theo điều kiện riêng

Nếu một truy vấn join nhiều bảng, hãy xác định điều kiện nào chỉ dùng cột của một bảng. Những điều kiện đó thường có thể lọc ngay trên nhánh tương ứng. Ví dụ, lọc đơn hàng theo ngày trên `orders`, lọc sản phẩm đang kinh doanh trên `products`, sau đó mới nối với `order_items`.

Không nhất thiết phải viết mọi nhánh thành subquery. Optimizer thường tự đẩy predicate qua inner join. Điều cần làm là bảo đảm điều kiện đúng, không bọc cột vô ích và kiểm tra plan để xem số hàng đầu vào từng nhánh.

### 5.2. Dùng EXISTS khi chỉ cần biết có bản ghi liên quan

Nếu mục tiêu là tìm khách hàng có ít nhất một đơn hàng hoàn tất, truy vấn join thông thường có thể tạo một dòng cho mỗi đơn hàng. Nếu một khách hàng có nhiều đơn hàng, kết quả sẽ lặp khách hàng. Khi chỉ cần kiểm tra sự tồn tại, `EXISTS` thể hiện đúng ý định semi-join:

```sql
SELECT c.customer_id, c.customer_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'COMPLETED'
);
```

So với:

```sql
SELECT DISTINCT c.customer_id, c.customer_name
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id
WHERE o.status = 'COMPLETED';
```

`EXISTS` diễn đạt rằng chỉ cần một dòng phù hợp là đủ. Engine có thể dừng tìm sau khi xác nhận tồn tại hoặc chọn một chiến lược semi-join. Câu join cộng `DISTINCT` phải xử lý các bản ghi trùng phát sinh trước khi loại trùng. Hai câu có thể cho cùng tập kết quả trong điều kiện này, nhưng cần so sánh semantics về cột, NULL và duplicate nếu thay đổi truy vấn thực tế.

### 5.3. Dùng NOT EXISTS cho anti-join

Nếu cần khách hàng chưa có đơn hàng, có thể dùng `NOT EXISTS`:

```sql
SELECT c.customer_id
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
```

Hãy cẩn trọng khi thay bằng `NOT IN`. Nếu tập giá trị của subquery chứa NULL, `NOT IN` có thể trả kết quả khác do logic ba giá trị của SQL. `NOT EXISTS` kiểm tra sự tồn tại của dòng thỏa điều kiện và thường dễ diễn đạt anti-join an toàn hơn. Vẫn cần xác nhận điều kiện so sánh và xử lý NULL theo yêu cầu nghiệp vụ.

### 5.4. Tổng hợp trước khi join khi phù hợp

Nếu cần tổng doanh thu theo khách hàng, có thể tổng hợp các dòng đơn hàng trước khi nối với bảng khách hàng:

```sql
SELECT c.customer_id, c.customer_name, x.total_amount
FROM customers AS c
JOIN (
    SELECT customer_id, SUM(total_amount) AS total_amount
    FROM orders
    WHERE status = 'COMPLETED'
    GROUP BY customer_id
) AS x
  ON x.customer_id = c.customer_id;
```

Nhánh `orders` có thể được rút gọn thành một dòng mỗi khách hàng trước khi join. Cách này hữu ích khi số đơn hàng lớn nhưng số khách hàng nhỏ hơn nhiều.

Chỉ tổng hợp trước khi join khi phép biến đổi giữ đúng kết quả. Nếu join làm nhân bản dòng, tổng hợp trước có thể khác tổng hợp sau. Cần xem khóa nối có duy nhất không, có quan hệ một-nhiều hoặc nhiều-nhiều không, có bộ lọc phụ thuộc bảng còn lại không và aggregate có cần phân biệt từng dòng hay không. Với `COUNT(DISTINCT ...)`, tỷ lệ phân nhóm hoặc các phép tổng hợp nhạy với duplicate, phải chứng minh tương đương trước khi viết lại.

## 6. Giữ đúng ngữ nghĩa của outer join

### 6.1. Khác biệt giữa điều kiện ON và WHERE

Outer join giữ lại dòng ở phía được bảo toàn ngay cả khi không có dòng khớp ở phía còn lại; các cột phía không khớp được điền NULL. Vì vậy, chuyển điều kiện từ `ON` sang `WHERE` có thể làm mất các dòng được giữ lại và biến hành vi thành inner join.

Ví dụ cần giữ mọi khách hàng, đồng thời chỉ nối đơn hàng hoàn tất:

```sql
SELECT c.customer_id, o.order_id
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.customer_id
 AND o.status = 'COMPLETED';
```

Nếu chuyển điều kiện trạng thái xuống `WHERE`:

```sql
SELECT c.customer_id, o.order_id
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.customer_id
WHERE o.status = 'COMPLETED';
```

những khách hàng không có đơn hàng sẽ có `o.status` là NULL và bị loại bởi điều kiện `WHERE`. Kết quả không còn giữ tất cả khách hàng.

### 6.2. Khi nào có thể lọc trước nhánh bên phải?

Có thể viết nhánh phải thành tập con đã lọc để thể hiện ý định:

```sql
SELECT c.customer_id, o.order_id
FROM customers AS c
LEFT JOIN (
    SELECT customer_id, order_id
    FROM orders
    WHERE status = 'COMPLETED'
) AS o
  ON o.customer_id = c.customer_id;
```

Trong ví dụ này, điều kiện trạng thái được áp dụng cho các hàng `orders` trước khi outer join; khách hàng không có đơn hàng hoàn tất vẫn xuất hiện với cột đơn hàng là NULL. Đây là ý nghĩa tương ứng với điều kiện đặt trong `ON` ở ví dụ trước.

Không áp dụng phép đẩy điều kiện một cách máy móc qua outer join, anti-join hoặc lateral join. Hãy xét phía nào được bảo toàn, điều kiện có chấp nhận NULL không và kết quả mong muốn có giữ các hàng không khớp hay không.

## 7. GROUP BY, HAVING, DISTINCT và window function

### 7.1. WHERE và HAVING có vai trò khác nhau

`WHERE` lọc hàng trước khi nhóm; `HAVING` lọc nhóm sau khi aggregate. Nếu điều kiện không phụ thuộc kết quả aggregate, đặt trong `WHERE` thường giúp giảm số hàng đầu vào cho bước nhóm:

```sql
-- Lọc trạng thái trước khi nhóm
SELECT customer_id, SUM(total_amount) AS revenue
FROM orders
WHERE status = 'COMPLETED'
GROUP BY customer_id
HAVING SUM(total_amount) > :minimum_revenue;
```

Không thể chuyển điều kiện `SUM(total_amount) > :minimum_revenue` sang `WHERE`, vì tổng chỉ có sau khi nhóm. Tương tự, nếu điều kiện liên quan aggregate hoặc alias được tính sau nhóm, cần giữ ở `HAVING` hoặc lớp truy vấn ngoài thích hợp.

### 7.2. DISTINCT có thể cần xử lý duplicate

`DISTINCT` loại các dòng trùng trên toàn bộ danh sách cột được chọn. Nó có thể yêu cầu sort hoặc hash để phát hiện trùng. Nếu chỉ cần kiểm tra sự tồn tại ở bảng liên quan, `EXISTS` có thể tránh tạo duplicate rồi mới loại trùng.

Không xóa `DISTINCT` chỉ vì nó tốn chi phí. Trước tiên xác định duplicate đến từ đâu và liệu truy vấn có chủ đích loại trùng không. Thay đổi join hoặc danh sách cột trong `SELECT DISTINCT` có thể làm thay đổi định nghĩa một dòng trùng.

### 7.3. Window function cần giữ đủ hàng và cột

Window function như `ROW_NUMBER`, `RANK`, `LAG`, `LEAD` tính giá trị dựa trên tập hàng trong partition và thứ tự cửa sổ. Đẩy bộ lọc xuống trước window có thể thay đổi thứ hạng hoặc giá trị lân cận.

Ví dụ, nếu cần lấy 3 đơn hàng mới nhất của mỗi khách hàng, không thể lọc tùy ý còn 3 dòng trước khi tính `ROW_NUMBER`; phải tính thứ hạng trên đúng tập đơn hàng đủ điều kiện rồi lọc kết quả:

```sql
SELECT customer_id, order_id, created_at
FROM (
    SELECT customer_id,
           order_id,
           created_at,
           ROW_NUMBER() OVER (
               PARTITION BY customer_id
               ORDER BY created_at DESC, order_id DESC
           ) AS rn
    FROM orders
    WHERE status = 'COMPLETED'
) AS ranked
WHERE rn <= 3;
```

Điều kiện `status = 'COMPLETED'` có thể lọc trước khi xếp hạng vì yêu cầu là xếp hạng các đơn hoàn tất. Nhưng điều kiện `rn <= 3` phải được áp dụng sau khi tính window. Thứ tự phụ `order_id` giúp kết quả xác định khi nhiều đơn có cùng `created_at`.

## 8. LIMIT, TOP và phân trang

### 8.1. Giới hạn số dòng đầu ra

`LIMIT`, `FETCH FIRST` hoặc `TOP` có thể giảm số dòng trả về ứng dụng. Khi có `ORDER BY` phù hợp và chỉ mục hỗ trợ, bộ tối ưu có thể dùng chiến lược top-N để tránh sắp xếp toàn bộ tập dữ liệu.

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = :customer_id
ORDER BY created_at DESC, order_id DESC
FETCH FIRST 20 ROWS ONLY;
```

Chỉ thêm giới hạn dòng khi nghiệp vụ thực sự chỉ cần số dòng đó. Nếu không có `ORDER BY`, thứ tự kết quả không được bảo đảm; giới hạn có thể trả về các dòng khác nhau giữa các lần chạy.

### 8.2. Không đẩy LIMIT qua join một cách tùy tiện

Lấy 20 đơn hàng trước rồi mới join sản phẩm có thể khác với join toàn bộ rồi lấy 20 dòng, đặc biệt khi mỗi đơn hàng có nhiều sản phẩm. Nếu mục tiêu là 20 đơn hàng mới nhất kèm toàn bộ dòng hàng của chúng, hãy chọn 20 khóa đơn hàng trước với thứ tự xác định, sau đó join để lấy chi tiết:

```sql
WITH recent_orders AS (
    SELECT order_id, created_at
    FROM orders
    WHERE customer_id = :customer_id
    ORDER BY created_at DESC, order_id DESC
    FETCH FIRST 20 ROWS ONLY
)
SELECT r.order_id, r.created_at, i.product_id, i.quantity
FROM recent_orders AS r
JOIN order_items AS i
  ON i.order_id = r.order_id
ORDER BY r.created_at DESC, r.order_id DESC, i.product_id;
```

Truy vấn này giới hạn **đơn hàng** trước, sau đó trả tất cả dòng hàng của 20 đơn đó. Nó không giới hạn kết quả cuối cùng còn 20 dòng. Nếu yêu cầu là 20 dòng chi tiết, vị trí giới hạn phải khác. Cần xác định đơn vị nghiệp vụ được phân trang: đơn hàng, khách hàng hay dòng chi tiết.

### 8.3. OFFSET pagination và keyset pagination

Phân trang bằng `OFFSET` lớn có thể buộc engine đọc và bỏ qua nhiều dòng trước khi trả trang tiếp theo. Với thứ tự ổn định, keyset pagination dùng khóa cuối cùng của trang trước để tìm phần tiếp theo:

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = :customer_id
  AND (created_at, order_id) < (:last_created_at, :last_order_id)
ORDER BY created_at DESC, order_id DESC
FETCH FIRST 20 ROWS ONLY;
```

Cú pháp so sánh tuple không được hỗ trợ giống nhau ở mọi hệ quản trị; có thể viết thành điều kiện tương đương bằng `OR`:

```sql
AND (
    created_at < :last_created_at
    OR (created_at = :last_created_at AND order_id < :last_order_id)
)
```

Keyset pagination thường giảm công việc bỏ qua các trang trước và ổn định hơn khi dữ liệu mới được thêm vào đầu danh sách. Cần có chỉ mục phù hợp với bộ lọc và thứ tự; khóa sắp xếp phải xác định duy nhất hoặc có tie-breaker. Nếu dữ liệu sắp xếp thay đổi trong lúc phân trang, vẫn cần xác định semantics snapshot mà ứng dụng mong muốn.

## 9. CTE, subquery và khả năng optimizer tự đẩy điều kiện

CTE và subquery giúp chia truy vấn thành các bước logic dễ đọc. Chúng không mặc nhiên là bảng tạm vật lý. Nhiều hệ quản trị có thể inline, gộp hoặc biến đổi CTE/subquery để đẩy điều kiện và projection xuống nguồn dữ liệu.

```sql
WITH filtered_orders AS (
    SELECT order_id, customer_id, created_at, total_amount
    FROM orders
    WHERE status = 'COMPLETED'
      AND created_at >= :from_time
      AND created_at <  :to_time
)
SELECT customer_id, SUM(total_amount) AS revenue
FROM filtered_orders
GROUP BY customer_id;
```

CTE trên thể hiện tập đơn hàng cần thiết trước khi nhóm. Tuy nhiên, một số engine hoặc cú pháp có thể materialize CTE, trong khi engine khác inline; một số hỗ trợ hint hoặc từ khóa điều khiển materialization. Materialize có thể hữu ích khi tái sử dụng kết quả nhiều lần, nhưng cũng có thể tạo ghi/đọc dữ liệu tạm và cản trở pushdown. Hãy kiểm tra plan của hệ quản trị cụ thể.

Các toán tử như window, aggregate, DISTINCT, LIMIT, set operation, hàm volatile hoặc ranh giới bảo mật có thể giới hạn phép biến đổi. Đừng giả định chỉ cần bọc truy vấn trong CTE là điều kiện sẽ được đẩy xuống hoặc kết quả sẽ được lưu vật lý.

## 10. Những trường hợp phải chứng minh tính tương đương

Trước khi đẩy điều kiện, bỏ cột hoặc thay đổi thứ tự toán tử, hãy kiểm tra các trường hợp sau:

| Tình huống | Rủi ro khi biến đổi | Câu hỏi cần kiểm tra |
|---|---|---|
| LEFT/RIGHT/FULL OUTER JOIN | Mất hàng không khớp hoặc thay đổi NULL được tạo ra | Điều kiện nằm trong `ON` hay `WHERE`? Phía nào phải được bảo toàn? |
| Duplicate và DISTINCT | Nhân bản hoặc loại bỏ dòng khác ý định | Join có một-nhiều/nhiều-nhiều không? Định nghĩa dòng trùng gồm những cột nào? |
| GROUP BY/HAVING | Thay đổi tập hàng đầu vào hoặc điều kiện trên aggregate | Điều kiện có thể áp dụng trước nhóm mà không đổi tổng/đếm không? |
| Window function | Thay đổi partition, thứ hạng hoặc giá trị lân cận | Bộ lọc có được áp dụng trước hay sau cửa sổ theo đúng nghiệp vụ? |
| LIMIT/TOP/OFFSET | Chọn một tập con khác hoặc đổi đơn vị phân trang | Thứ tự có xác định không? Giới hạn áp dụng cho entity hay dòng join? |
| NULL và NOT IN | Logic ba giá trị làm thay đổi kết quả | Subquery có thể chứa NULL không? `NOT EXISTS` có phù hợp hơn không? |
| UNION/UNION ALL | Thay đổi duplicate và số dòng | Có cần loại trùng hay phải giữ tất cả lần xuất hiện? |
| Hàm không xác định/volatile | Số lần gọi hoặc thứ tự đánh giá có thể đổi | Hàm có phụ thuộc thời gian, random, sequence hoặc trạng thái không? |
| Row-level security/view | Lọc bảo mật hoặc logic view có thể bị ảnh hưởng | Điều kiện được áp dụng trong đúng ngữ cảnh quyền và chính sách không? |

Một phép biến đổi an toàn cần giữ đúng logic của SQL, bao gồm duplicate, NULL và thứ tự khi được yêu cầu. Nếu không chứng minh được tương đương, hãy giữ cấu trúc truy vấn ban đầu và tìm cách tối ưu khác.

## 11. Ví dụ tổng hợp: lọc và chiếu trước khi nối

Giả sử báo cáo cần doanh thu theo khách hàng trong tháng trước, chỉ tính đơn hàng đã thanh toán. Truy vấn ban đầu nối dữ liệu đơn hàng với từng dòng hàng rồi mới tổng hợp:

```sql
SELECT c.customer_id,
       c.customer_name,
       SUM(i.quantity * i.unit_price) AS revenue
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id
JOIN order_items AS i
  ON i.order_id = o.order_id
WHERE o.paid_at >= :month_start
  AND o.paid_at <  :next_month_start
  AND o.status = 'PAID'
GROUP BY c.customer_id, c.customer_name;
```

Nếu báo cáo chỉ cần mã khách hàng và tổng doanh thu, có thể giảm cột, lọc đơn hàng trước, tổng hợp chi tiết theo đơn hàng rồi mới nối với khách hàng:

```sql
WITH paid_orders AS (
    SELECT order_id, customer_id
    FROM orders
    WHERE status = 'PAID'
      AND paid_at >= :month_start
      AND paid_at <  :next_month_start
),
revenue_by_customer AS (
    SELECT p.customer_id,
           SUM(i.quantity * i.unit_price) AS revenue
    FROM order_items AS i
    JOIN paid_orders AS p
      ON p.order_id = i.order_id
    GROUP BY p.customer_id
)
SELECT c.customer_id, c.customer_name, r.revenue
FROM revenue_by_customer AS r
JOIN customers AS c
  ON c.customer_id = r.customer_id;
```

Truy vấn viết lại chỉ giữ các cột cần thiết ở từng bước. Đơn hàng được lọc theo trạng thái và khoảng thời gian trước khi nối với dòng hàng. Dữ liệu chi tiết được tổng hợp theo khách hàng; tên khách hàng chỉ được lấy sau khi đã giảm tập kết quả.

Trước khi dùng, cần xác nhận:

1. `customer_id` là duy nhất trong `customers` và `order_id` là duy nhất trong `orders`.
2. Mỗi dòng `order_items` chỉ thuộc một đơn hàng theo khóa nối.
3. Báo cáo muốn tính doanh thu từ `quantity * unit_price`, không phải một cột tổng khác có quy tắc chiết khấu/thuế.
4. Bộ lọc `PAID` và khoảng `paid_at` xác định đúng tập đơn hàng nghiệp vụ.
5. Không có join khác trong truy vấn ban đầu làm thay đổi multiplicity có chủ đích.
6. Cách xử lý đơn hàng không có dòng hàng và khách hàng không có đơn hàng đúng yêu cầu báo cáo.

Nếu truy vấn ban đầu cần trả từng dòng hàng, không thể thay bằng kết quả tổng hợp trên. Nếu cần giữ khách hàng không có doanh thu, phải dùng outer join thích hợp và xử lý NULL ở bước tổng hợp. Tối ưu phải bắt đầu từ định nghĩa kết quả cần có.

## 12. Đo và xác nhận việc giảm dữ liệu

### 12.1. Đọc execution plan

Sau khi viết lại, hãy so sánh plan trước và sau. Các điểm cần xem:

- Điều kiện lọc có xuất hiện gần scan/seek của bảng nguồn không?
- Số hàng ước lượng và thực tế ở đầu vào join có giảm không?
- Các toán tử có mang những cột không cần thiết qua join/sort/hash không?
- Có giảm key lookup/heap fetch hoặc số lần đọc trang không?
- Có thay đổi join algorithm, thứ tự join, sort hoặc aggregate không?
- Có phát sinh materialize hoặc spill vào vùng tạm không?

Không đánh giá chỉ bằng việc plan có ít node hơn. Một kế hoạch có thêm bước lọc sớm nhưng giảm hàng triệu dòng ở bước sau có thể tốt hơn kế hoạch ngắn hơn.

### 12.2. So sánh số liệu cùng điều kiện

| Chỉ số | Ý nghĩa khi kiểm chứng |
|---|---|
| Actual rows theo từng toán tử | Xác nhận số dòng được loại bỏ sớm và quy mô đầu vào join |
| Row width/estimated row size | Xác nhận projection làm giảm độ rộng hàng |
| Logical reads | Đo số trang được truy cập trong buffer pool |
| Physical reads/read-ahead | Đo hoạt động đọc storage |
| CPU time | Đánh giá công việc xử lý, so sánh và aggregate |
| Elapsed time | Đo thời gian hoàn tất trong điều kiện tải cụ thể |
| Memory grant/temp spill | Xem nhu cầu bộ nhớ và dữ liệu tạm |
| Network bytes/result rows | Đánh giá lượng dữ liệu trả về ứng dụng |

Chạy cùng dữ liệu, tham số, mức tải và phương thức đo; kiểm tra nhiều giá trị tham số đại diện. Đọc lại kết quả để xác nhận số dòng, duplicate, NULL và giá trị aggregate không đổi. Nếu cần, so sánh hai tập kết quả bằng phép đối chiếu hai chiều hoặc checksum phù hợp, đồng thời lưu ý thứ tự chỉ được so sánh khi truy vấn có `ORDER BY` xác định.

### 12.3. Kiểm chứng không chỉ ở một truy vấn

Giảm cột có thể giúp truy vấn đọc nhanh hơn nhưng cũng có thể khiến một chỉ mục bao phủ mới rộng hơn. Lọc sớm có thể giảm join nhưng thay đổi thứ tự truy cập hoặc ảnh hưởng truy vấn dùng chung bảng. Sau khi điều chỉnh, kiểm tra workload liên quan, chi phí ghi, kích thước index, cache và kế hoạch của các truy vấn quan trọng khác.

## 13. Những lỗi thường gặp

- **Dùng `SELECT *`:** đọc và truyền cột không cần thiết, có thể kéo theo LOB hoặc làm hàng trung gian rộng.
- **Chỉ lọc ở cuối truy vấn:** để quá nhiều dòng đi qua join, sort hoặc aggregate trước khi bị loại.
- **Đẩy mọi điều kiện xuống mọi nơi:** outer join, window, aggregate và LIMIT có thể làm thay đổi ngữ nghĩa nếu chuyển sai vị trí.
- **Thay JOIN bằng EXISTS mà không xét duplicate:** hai dạng chỉ tương đương khi mục tiêu là kiểm tra sự tồn tại và cột đầu ra phù hợp.
- **Tổng hợp trước join một cách máy móc:** có thể làm sai tổng hoặc số đếm khi quan hệ nối tạo multiplicity.
- **Đưa điều kiện outer join từ ON sang WHERE:** có thể loại các dòng không khớp vốn cần được giữ lại.
- **Xóa DISTINCT chỉ để giảm chi phí:** có thể làm kết quả xuất hiện duplicate ngoài ý muốn.
- **Đẩy LIMIT trước join:** có thể giới hạn sai đơn vị dữ liệu và làm mất các dòng chi tiết cần thiết.
- **Tin rằng CTE luôn materialize hoặc luôn inline:** hành vi tùy hệ quản trị, phiên bản và cấu trúc truy vấn.
- **Chỉ nhìn số dòng cuối cùng:** cần đo số dòng và độ rộng ở từng toán tử trung gian.
- **Chỉ so sánh thời gian một lần:** cache, tải đồng thời và tham số có thể làm số đo dao động.
- **Tối ưu mà không kiểm tra kết quả:** nhanh hơn nhưng sai duplicate, NULL, tổng hoặc thứ tự vẫn là lỗi.

## 14. Quy trình thực hành

1. **Xác định kết quả nghiệp vụ.** Ghi rõ cột đầu ra, đơn vị một dòng, điều kiện lọc, duplicate có được giữ không, cách xử lý NULL và thứ tự/phân trang.
2. **Đọc truy vấn và execution plan hiện tại.** Tìm scan lớn, join có đầu vào lớn, sort/hash, materialize và các cột rộng.
3. **Lập danh sách cột cần ở từng bước.** Giữ cột phục vụ output, filter, join, group, order và window; loại bỏ cột thừa sớm nhất có thể.
4. **Phân loại điều kiện lọc.** Xác định điều kiện chỉ thuộc một bảng, điều kiện trên aggregate, điều kiện của outer join và điều kiện sau window/limit.
5. **Đẩy predicate an toàn.** Lọc gần scan/seek, dùng khoảng sargable, tận dụng partition pruning và giảm dữ liệu mỗi nhánh trước join.
6. **Chọn đúng dạng join.** Dùng `EXISTS` khi chỉ cần kiểm tra tồn tại; cân nhắc anti-join với `NOT EXISTS`; tổng hợp trước join chỉ khi chứng minh giữ nguyên multiplicity.
7. **Giữ ranh giới ngữ nghĩa.** Kiểm tra outer join, DISTINCT, GROUP BY, HAVING, window, LIMIT, NULL, volatile function và phân trang.
8. **Đo lại.** So sánh actual rows, row width, reads, CPU, elapsed time, memory, temp I/O và dữ liệu trả về.
9. **Kiểm tra tính đúng và tác động rộng.** Đối chiếu kết quả, kiểm thử biên và tham số đại diện; kiểm tra workload đọc/ghi liên quan.

## 15. Bài tập tự kiểm tra

**Bài 1.** Một truy vấn dùng `SELECT *` nhưng ứng dụng chỉ đọc `order_id` và `created_at`. Hãy nêu lợi ích của việc chọn đúng hai cột này và một trường hợp cột vẫn cần giữ dù không xuất hiện trong output.

*Gợi ý:* Giảm độ rộng hàng, I/O, dữ liệu truyền và có thể tận dụng covering index. Một cột vẫn cần nếu được dùng trong WHERE, JOIN, GROUP BY, ORDER BY hoặc window calculation.

**Bài 2.** Bạn cần danh sách khách hàng có ít nhất một đơn hàng đã thanh toán. Vì sao `EXISTS` có thể phù hợp hơn `JOIN` cộng `DISTINCT`?

*Gợi ý:* Mục tiêu là kiểm tra tồn tại; `EXISTS` diễn đạt semi-join và tránh tạo nhiều dòng khách hàng rồi mới loại trùng. Kiểm tra cột đầu ra và semantics duplicate.

**Bài 3.** Một truy vấn LEFT JOIN giữ mọi khách hàng. Điều gì xảy ra nếu chuyển điều kiện `orders.status = 'PAID'` từ `ON` sang `WHERE`?

*Gợi ý:* Khách hàng không có đơn hàng nhận NULL ở phía orders và bị WHERE loại bỏ; kết quả có thể biến thành hành vi inner join.

**Bài 4.** Một truy vấn lấy 20 đơn hàng mới nhất và cần toàn bộ dòng hàng của các đơn đó. Nên áp dụng giới hạn 20 ở bước nào?

*Gợi ý:* Chọn 20 khóa đơn hàng theo thứ tự xác định trước, sau đó join lấy toàn bộ dòng hàng. Nếu giới hạn sau join thì 20 có thể là 20 dòng chi tiết, không phải 20 đơn hàng.

**Bài 5.** Một phép tổng hợp trước join làm số dòng giảm mạnh nhưng tổng doanh thu thay đổi. Những nguyên nhân nào cần kiểm tra?

*Gợi ý:* Join có nhân bản dòng không; khóa nối có duy nhất không; tổng hợp có bỏ qua phân biệt dòng, bộ lọc từ bảng còn lại, NULL hoặc điều kiện outer join không; công thức doanh thu có giữ đúng quy tắc nghiệp vụ không.

## 16. Ghi nhớ khi tối ưu

Giảm cột và số hàng từ sớm làm giảm độ rộng và kích thước dữ liệu đi qua các bước của truy vấn. Projection pushdown giúp giữ lại những cột cần thiết; predicate pushdown giúp loại bỏ hàng không phù hợp gần nguồn dữ liệu; semi-join, lọc trước join và tổng hợp có kiểm soát có thể giảm lượng công việc trung gian đáng kể.

Mọi phép biến đổi phải giữ đúng semantics SQL, đặc biệt với outer join, duplicate, NULL, aggregate, window function và phân trang. Hãy xác định rõ kết quả nghiệp vụ trước khi viết lại, sau đó đọc execution plan và đo actual rows, row width, reads, CPU, memory, temp I/O và thời gian. Một tối ưu chỉ được xác nhận khi dữ liệu trả về vẫn đúng và workload thực tế giảm công việc trong điều kiện đo tương đương.
