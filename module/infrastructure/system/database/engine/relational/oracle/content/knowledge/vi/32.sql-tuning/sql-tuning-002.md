# Giảm số dòng và số cột được xử lý trước các thao tác tốn chi phí

Trong Oracle Database, một câu SQL có thể phải đọc, nối, sắp xếp, nhóm hoặc loại trùng một lượng dữ liệu rất lớn trước khi trả về kết quả. Những thao tác này thường tiêu thụ CPU, bộ nhớ và I/O; khi vùng làm việc không đủ bộ nhớ, Oracle còn có thể phải ghi dữ liệu tạm ra TEMP. Vì vậy, một nguyên tắc quan trọng khi tối ưu SQL là **giảm số dòng và số cột mà mỗi bước xử lý phải nhận càng sớm càng tốt**, miễn là vẫn giữ nguyên ý nghĩa của truy vấn.

Nguyên tắc này có hai phần bổ trợ cho nhau:

- **Giảm số dòng (row reduction):** loại bỏ những bản ghi không liên quan trước khi thực hiện các phép nối, sắp xếp, nhóm, tính toán cửa sổ hoặc loại trùng.
- **Giảm số cột (column reduction):** chỉ đọc và mang theo những cột thật sự cần cho kết quả, điều kiện lọc, điều kiện nối, sắp xếp hoặc tính toán.

Ví dụ, nếu một báo cáo chỉ cần 50 đơn hàng gần nhất của một khách hàng, việc đọc toàn bộ cột của hàng triệu đơn hàng rồi mới lọc và sắp xếp sẽ lãng phí tài nguyên. Truy vấn nên cho Oracle biết sớm phạm vi ngày, khách hàng và các cột cần dùng; sau đó bộ tối ưu chi phí (cost-based optimizer) sẽ chọn kế hoạch thực thi phù hợp.

## 1. Vì sao cần giảm dữ liệu trước các thao tác tốn chi phí?

Giả sử bảng `ORDERS` có 20 triệu dòng, mỗi dòng chứa mã đơn hàng, mã khách hàng, ngày đặt hàng, trạng thái, số tiền và một cột ghi chú kiểu `CLOB`. Một truy vấn báo cáo chỉ cần mã đơn, ngày và số tiền của các đơn đã thanh toán trong một tháng.

Nếu truy vấn đọc tất cả cột và tất cả dòng rồi mới lọc, Oracle có thể phải xử lý nhiều dữ liệu hơn mức cần thiết. Khi số dòng hoặc độ rộng của mỗi dòng tăng, chi phí truyền dữ liệu giữa các bước trong execution plan cũng tăng theo.

Những thao tác thường trở nên đắt đỏ khi đầu vào lớn gồm:

| Thao tác | Vì sao lượng dữ liệu đầu vào quan trọng |
|---|---|
| `SORT ORDER BY` | Phải sắp xếp các dòng cần xét; có thể dùng nhiều bộ nhớ hoặc TEMP. |
| `HASH JOIN` | Phải xây dựng và tra cứu cấu trúc băm; đầu vào lớn làm tăng bộ nhớ và công việc xử lý. |
| `HASH GROUP BY` / `SORT GROUP BY` | Phải tổng hợp nhiều dòng và duy trì trạng thái cho các nhóm. |
| `DISTINCT` | Phải xác định các dòng trùng nhau, thường cần sort hoặc hash. |
| Hàm phân tích (analytic/window functions) | Phải phân vùng và có thể sắp xếp các dòng trong từng cửa sổ. |
| Truy xuất bảng và LOB | Đọc thêm cột rộng hoặc LOB có thể tăng I/O và lượng dữ liệu trả về. |

Không phải mọi full table scan hay hash join đều xấu. Nếu truy vấn cần phần lớn dữ liệu của bảng, full table scan có thể hiệu quả hơn việc đọc chỉ mục rồi truy xuất từng dòng. Mục tiêu là giảm lượng dữ liệu không cần thiết và để Oracle chọn cách truy cập phù hợp, chứ không phải ép mọi truy vấn dùng index.

## 2. Hiểu đúng cách Oracle thực thi SQL

SQL mô tả **kết quả cần nhận**, còn Oracle quyết định **cách lấy kết quả**. Thứ tự viết các mệnh đề trong câu SQL không phải là thứ tự thực thi vật lý. Bộ tối ưu có thể đổi thứ tự nối bảng, đẩy điều kiện lọc vào view hoặc subquery, loại bỏ cột không được sử dụng và biến đổi truy vấn nếu phép biến đổi vẫn bảo toàn kết quả.

Vì thế, viết điều kiện lọc sớm và chỉ chọn cột cần thiết giúp bộ tối ưu có đủ thông tin để tạo kế hoạch tốt. Tuy nhiên, chỉ nhìn thấy `WHERE` nằm trước `ORDER BY` trong câu SQL không chứng minh rằng dữ liệu đã được lọc trước khi sắp xếp. Cần kiểm tra execution plan và số liệu thực thi để biết điều gì thực sự xảy ra.

Hai khái niệm thường gặp là:

- **Predicate pushdown:** đẩy điều kiện lọc xuống gần nơi dữ liệu được đọc nhất, để các bước phía sau nhận ít dòng hơn.
- **Projection pushdown:** chỉ giữ lại những cột cần thiết ở các bước phía dưới, để dữ liệu trung gian hẹp hơn.

Oracle có thể tự thực hiện các biến đổi này. Cách viết SQL tốt giúp điều kiện và nhu cầu về cột rõ ràng, đồng thời tránh những cấu trúc làm bộ tối ưu khó nhận diện cơ hội tối ưu.

## 3. Giảm số dòng bằng điều kiện lọc hiệu quả

### 3.1. Lọc theo phạm vi cụ thể trong `WHERE`

Đưa các điều kiện có thể áp dụng trực tiếp vào bảng nguồn vào `WHERE`. Ví dụ, nếu báo cáo chỉ cần đơn hàng trong tháng 11 năm 2026 và đã thanh toán:

```sql
SELECT
    order_id,
    customer_id,
    order_date,
    total_amount
FROM orders
WHERE status = 'PAID'
  AND order_date >= DATE '2026-11-01'
  AND order_date <  DATE '2026-12-01';
```

Điều kiện ngày dùng khoảng nửa mở: bao gồm thời điểm bắt đầu và loại trừ thời điểm bắt đầu tháng tiếp theo. Cách này xử lý đúng mọi thời điểm trong ngày cuối tháng, kể cả khi `ORDER_DATE` có phần giờ, phút và giây.

Nếu cột ngày được lưu dưới kiểu `DATE` hoặc `TIMESTAMP`, hãy truyền bind variable có kiểu tương ứng khi ứng dụng thực thi truy vấn. Tránh chuyển cột thành chuỗi để so sánh.

### 3.2. Tránh bọc hàm quanh cột lọc khi không cần thiết

Một cách viết thường gặp là:

```sql
SELECT order_id, order_date
FROM orders
WHERE TRUNC(order_date) = DATE '2026-11-14';
```

`TRUNC(order_date)` áp dụng hàm lên từng giá trị của cột. Một index thông thường trên `ORDER_DATE` có thể không được dùng hiệu quả cho điều kiện này, vì biểu thức cần tìm không còn là giá trị cột nguyên bản.

Có thể viết lại thành khoảng thời gian:

```sql
SELECT order_id, order_date
FROM orders
WHERE order_date >= DATE '2026-11-14'
  AND order_date <  DATE '2026-11-15';
```

Điều kiện dạng khoảng thường giúp Oracle sử dụng index trên `ORDER_DATE` và hỗ trợ partition pruning nếu bảng được phân vùng theo cột này. Đây là một cách viết tương đương về ý nghĩa đối với mục tiêu lấy toàn bộ ngày 14, đồng thời không áp dụng hàm lên cột.

Nếu nghiệp vụ thực sự cần tìm theo một biểu thức như `UPPER(email)`, có thể cân nhắc function-based index trên chính biểu thức đó. Quyết định này cần dựa trên workload, độ chọn lọc, thống kê và chi phí duy trì index khi ghi dữ liệu.

### 3.3. Viết điều kiện có thể tận dụng index và partition pruning

Index B-tree thường hữu ích khi điều kiện chọn ra một phần tương đối nhỏ của bảng. Các dạng điều kiện thường thuận lợi gồm so sánh bằng, so sánh theo khoảng và điều kiện nối trên cột phù hợp:

```sql
WHERE customer_id = :customer_id
  AND order_date >= :from_date
  AND order_date <  :to_date
```

Nếu bảng `ORDERS` được partition theo `ORDER_DATE`, điều kiện khoảng trên cột phân vùng có thể giúp Oracle chỉ truy cập những partition liên quan. Đây là partition pruning. Nếu viết `TRUNC(order_date)` hoặc chuyển đổi kiểu dữ liệu không phù hợp quanh cột phân vùng, khả năng pruning có thể bị hạn chế.

Khi cân nhắc index ghép, cần xem xét toàn bộ mẫu truy vấn. Một index ứng viên có thể gồm cột lọc bằng, cột lọc theo khoảng và cột nối; thứ tự cột phải phù hợp với điều kiện thực tế và mức độ chọn lọc. Không có một thứ tự cột đúng cho mọi workload. Index cũng chiếm dung lượng và làm tăng chi phí `INSERT`, `UPDATE`, `DELETE`, vì vậy không nên tạo index chỉ dựa trên một câu SQL riêng lẻ.

### 3.4. Đưa điều kiện lọc vào đúng vị trí với `GROUP BY` và `HAVING`

`WHERE` lọc dòng đầu vào trước khi nhóm. `HAVING` lọc kết quả nhóm sau khi phép tổng hợp đã được tính. Nếu điều kiện không phụ thuộc vào kết quả tổng hợp, đặt nó trong `WHERE` thường giúp giảm số dòng phải nhóm.

Ví dụ:

```sql
SELECT
    customer_id,
    SUM(total_amount) AS total_paid
FROM orders
WHERE status = 'PAID'
  AND order_date >= :from_date
  AND order_date <  :to_date
GROUP BY customer_id
HAVING SUM(total_amount) > :minimum_total;
```

Ở đây, trạng thái và ngày được lọc trước khi nhóm. Điều kiện tổng tiền của từng khách hàng phải nằm ở `HAVING`, vì nó phụ thuộc vào kết quả `SUM`. Không thể chuyển điều kiện này thành điều kiện lọc từng dòng mà vẫn giữ nguyên ý nghĩa.

### 3.5. Dùng `EXISTS` khi chỉ cần biết có bản ghi liên quan

Nếu mục tiêu chỉ là tìm khách hàng có ít nhất một đơn hàng đã thanh toán, phép nối thông thường có thể tạo nhiều dòng cho một khách hàng khi khách hàng có nhiều đơn. Sau đó truy vấn có thể phải dùng `DISTINCT` để loại trùng.

Có thể diễn đạt trực tiếp ý định bằng `EXISTS`:

```sql
SELECT
    c.customer_id,
    c.customer_name
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
      AND o.order_date >= :from_date
      AND o.order_date <  :to_date
);
```

`EXISTS` chỉ kiểm tra sự tồn tại của ít nhất một dòng phù hợp. Oracle có thể biến đổi truy vấn thành semi join để tránh tạo toàn bộ các dòng ghép chỉ nhằm kiểm tra sự tồn tại. `SELECT 1` trong subquery thể hiện rằng giá trị cột không được dùng; Oracle không cần lấy các cột đầu ra của dòng đơn hàng cho mục đích này.

Nếu cần hiển thị từng đơn hàng hoặc tính tổng giá trị đơn hàng, hãy dùng phép nối phù hợp. Không nên thay `JOIN` bằng `EXISTS` nếu việc đó làm mất các dòng hoặc giá trị mà kết quả cần có.

### 3.6. Giữ đúng ý nghĩa khi lọc trước phép nối

Lọc bảng trước khi nối thường có lợi, nhưng vị trí điều kiện có thể làm thay đổi kết quả, nhất là với outer join.

Ví dụ, truy vấn sau giữ lại mọi khách hàng và chỉ ghép những đơn hàng đã thanh toán:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id
FROM customers c
LEFT JOIN orders o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID';
```

Nếu chuyển `o.status = 'PAID'` xuống `WHERE`, các dòng khách hàng không có đơn hàng phù hợp sẽ bị loại vì các cột `o` có giá trị `NULL`. Khi đó, kết quả có thể tương đương inner join đối với điều kiện này. Chỉ di chuyển điều kiện khi đã xác nhận phép biến đổi giữ nguyên quy tắc nghiệp vụ.

## 4. Giảm số cột bằng projection rõ ràng

### 4.1. Tránh `SELECT *` trong truy vấn có mục tiêu cụ thể

Giả sử bảng có các cột `ORDER_ID`, `CUSTOMER_ID`, `ORDER_DATE`, `STATUS`, `TOTAL_AMOUNT`, `SHIPPING_ADDRESS` và `NOTES` kiểu `CLOB`. Nếu màn hình chỉ hiển thị mã đơn, ngày và số tiền, hãy viết:

```sql
SELECT
    order_id,
    order_date,
    total_amount
FROM orders
WHERE customer_id = :customer_id;
```

thay vì:

```sql
SELECT *
FROM orders
WHERE customer_id = :customer_id;
```

Chọn rõ cột giúp giảm dữ liệu phải đọc, giữ trong các bước trung gian, truyền qua mạng và chuyển đổi ở tầng ứng dụng. Điều này đặc biệt có ý nghĩa với cột rộng như `CLOB`, `BLOB`, JSON lớn hoặc các cột văn bản dài. Nó cũng làm hợp đồng dữ liệu của truy vấn rõ ràng hơn khi bảng được bổ sung cột mới.

### 4.2. Chỉ mang theo cột cần cho các bước tiếp theo

Trong truy vấn nhiều bảng, mỗi nhánh chỉ cần giữ các cột phục vụ một trong các mục đích sau:

- Trả về kết quả cuối cùng.
- Tham gia điều kiện nối.
- Tham gia điều kiện lọc.
- Phục vụ `GROUP BY`, `ORDER BY`, biểu thức tính toán hoặc hàm phân tích.

Ví dụ, một truy vấn tổng hợp theo khách hàng không cần mang theo địa chỉ giao hàng hay ghi chú của từng đơn hàng:

```sql
WITH paid_orders AS (
    SELECT
        customer_id,
        total_amount
    FROM orders
    WHERE status = 'PAID'
      AND order_date >= :from_date
      AND order_date <  :to_date
)
SELECT
    c.customer_id,
    c.customer_name,
    SUM(p.total_amount) AS total_paid
FROM paid_orders p
JOIN customers c
    ON c.customer_id = p.customer_id
GROUP BY c.customer_id, c.customer_name;
```

CTE `paid_orders` làm rõ rằng truy vấn chỉ cần mã khách hàng và số tiền của các đơn phù hợp. Oracle có thể inline hoặc merge CTE vào truy vấn chính và tiếp tục tối ưu toàn bộ câu lệnh; không nên mặc định rằng `WITH` luôn tạo bảng tạm hoặc luôn buộc dữ liệu được vật hóa. Lợi ích của cách viết này trước hết là thể hiện đúng các cột và điều kiện cần thiết.

### 4.3. Chú ý đến index-only access

Nếu một truy vấn chỉ cần những cột có sẵn trong index, Oracle đôi khi có thể lấy kết quả từ index mà không cần truy xuất thêm block của bảng. Đây là một cơ hội giảm I/O. Ví dụ, một index ghép có thể chứa cột khách hàng và ngày đặt hàng cho một truy vấn chỉ cần hai cột đó.

Tuy nhiên, không nên thêm mọi cột đầu ra vào index chỉ để cố tạo index-only access. Index rộng hơn cần nhiều dung lượng, tốn bộ nhớ đệm và tăng chi phí duy trì khi dữ liệu thay đổi. Hãy cân nhắc tần suất truy vấn, số dòng được chọn, số lần ghi và các truy vấn khác cùng dùng index.

## 5. Giảm dữ liệu trước `JOIN`, `SORT`, `DISTINCT` và các phép tổng hợp

### 5.1. Lọc trước khi nối các tập dữ liệu lớn

Giả sử báo cáo cần tổng số tiền đã thanh toán theo khách hàng trong một khoảng thời gian. Một cách viết rõ ràng là:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    SUM(o.total_amount) AS total_paid
FROM customers c
JOIN orders o
    ON o.customer_id = c.customer_id
WHERE o.status = 'PAID'
  AND o.order_date >= :from_date
  AND o.order_date <  :to_date
GROUP BY c.customer_id, c.customer_name;
```

Các điều kiện trên bảng `ORDERS` cho biết chỉ những đơn đã thanh toán trong khoảng thời gian cần báo cáo mới liên quan. Oracle có thể đẩy các điều kiện này xuống bước truy cập `ORDERS`, rồi mới nối với `CUSTOMERS`. Kế hoạch thực thi thực tế còn phụ thuộc vào thống kê, index, phân vùng, số dòng ước tính và chi phí của từng phương án.

Không cần tạo inline view chỉ để viết lại cùng một điều kiện nếu bộ tối ưu đã có thể đẩy predicate xuống. Ngược lại, cũng không nên dựa vào hình thức viết subquery để khẳng định chắc chắn thứ tự thực thi. Hãy xác nhận bằng execution plan.

### 5.2. Tránh `DISTINCT` để che giấu lỗi nhân dòng

`DISTINCT` có thể cần sort hoặc hash trên các cột được chọn. Nếu truy vấn tạo ra nhiều dòng do nối một bảng cha với bảng con có nhiều bản ghi, rồi dùng `DISTINCT` để đưa kết quả về một dòng cha, hãy kiểm tra xem mục tiêu thực sự có phải chỉ là kiểm tra sự tồn tại hay không. Trong trường hợp đó, `EXISTS` có thể diễn đạt ý định chính xác và tránh tạo các dòng trùng ngay từ đầu.

Không loại bỏ `DISTINCT` một cách máy móc. Nếu kết quả nghiệp vụ thực sự yêu cầu các tổ hợp giá trị duy nhất, `DISTINCT` là một phần của ngữ nghĩa và cần được giữ lại. Có thể giảm chi phí bằng cách chỉ chọn những cột cần thiết trước khi loại trùng, thay vì đưa thêm cột rộng không cần thiết vào phép so sánh.

### 5.3. Chỉ sắp xếp khi kết quả cần thứ tự

Một câu `ORDER BY` có thể yêu cầu Oracle sắp xếp lượng lớn dòng. Nếu thứ tự không cần cho kết quả hoặc giao diện, hãy bỏ `ORDER BY`. Thứ tự dòng không được bảo đảm nếu truy vấn không có `ORDER BY`, vì vậy chỉ dựa vào thứ tự tình cờ quan sát được là không an toàn.

Nếu chỉ cần một số dòng đầu tiên, kết hợp thứ tự với giới hạn dòng:

```sql
SELECT
    order_id,
    order_date,
    total_amount
FROM orders
WHERE customer_id = :customer_id
ORDER BY order_date DESC, order_id DESC
FETCH FIRST 20 ROWS ONLY;
```

`FETCH FIRST` được hỗ trợ từ Oracle Database 12c. Oracle có thể dùng kế hoạch top-N, chẳng hạn `SORT ORDER BY STOPKEY`, hoặc tận dụng index phù hợp để tìm các dòng đầu. Tuy nhiên, giới hạn kết quả không bảo đảm rằng Oracle chỉ đọc đúng 20 dòng: nếu không có access path phù hợp, hệ thống vẫn có thể phải xét và sắp xếp nhiều dòng để xác định 20 dòng đứng đầu.

Thứ tự phụ `ORDER_ID DESC` giúp kết quả ổn định hơn khi nhiều đơn có cùng `ORDER_DATE`. Khi dùng top-N hoặc phân trang, nên có tiêu chí sắp xếp đủ để phân biệt các dòng.

### 5.4. Phân trang sâu bằng khóa tiếp nối

Phân trang bằng `OFFSET` có thể tốn thêm công việc khi trang nằm sâu, vì Oracle phải xác định và bỏ qua các dòng đứng trước. Với luồng dữ liệu lớn, có thể cân nhắc keyset pagination: gửi lại khóa của dòng cuối trang trước và yêu cầu dòng tiếp theo.

Ví dụ với thứ tự giảm dần theo ngày và mã đơn:

```sql
SELECT
    order_id,
    order_date,
    total_amount
FROM orders
WHERE customer_id = :customer_id
  AND (
        order_date < :last_order_date
        OR (order_date = :last_order_date AND order_id < :last_order_id)
      )
ORDER BY order_date DESC, order_id DESC
FETCH FIRST 20 ROWS ONLY;
```

Ứng dụng truyền `:last_order_date` và `:last_order_id` từ dòng cuối của trang trước. Cần bảo đảm cặp khóa tạo thứ tự ổn định và có index phù hợp với điều kiện khách hàng cùng thứ tự sắp xếp. Nếu dữ liệu thay đổi giữa các lần lấy trang, ứng dụng cũng cần xác định rõ yêu cầu nhất quán của việc phân trang.

### 5.5. Cẩn thận với `ROWNUM` trên phiên bản cũ

Trên phiên bản Oracle chưa hỗ trợ `FETCH FIRST`, có thể giới hạn top-N bằng cách sắp xếp trong subquery rồi áp dụng `ROWNUM` ở lớp ngoài:

```sql
SELECT order_id, order_date, total_amount
FROM (
    SELECT order_id, order_date, total_amount
    FROM orders
    WHERE customer_id = :customer_id
    ORDER BY order_date DESC, order_id DESC
)
WHERE ROWNUM <= 20;
```

Không đặt `ROWNUM <= 20` và `ORDER BY` ở cùng một query block nếu mục tiêu là lấy 20 dòng mới nhất. `ROWNUM` được gán trước bước sắp xếp của query block đó, nên kết quả có thể là 20 dòng được chọn trước rồi mới sắp xếp, thay vì 20 dòng mới nhất.

## 6. Các trường hợp không thể tùy tiện đẩy điều kiện xuống

Giảm dữ liệu càng sớm càng tốt là nguyên tắc tối ưu, nhưng điều kiện lọc phải giữ đúng ngữ nghĩa của phép tính.

- **Outer join:** điều kiện trên bảng phía nullable đặt trong `ON` có thể giữ lại dòng không khớp; đặt trong `WHERE` có thể loại dòng đó.
- **Aggregation:** điều kiện trên từng dòng thường nằm trong `WHERE`; điều kiện trên kết quả `SUM`, `COUNT`, `AVG` hoặc nhóm nằm trong `HAVING`.
- **Analytic functions:** lọc dòng trước khi tính `ROW_NUMBER`, `RANK`, `SUM(...) OVER (...)` có thể làm thay đổi tập dòng của cửa sổ và thứ hạng. Chỉ đẩy điều kiện xuống nếu đó là kết quả mong muốn.
- **Top-N:** lọc trước khi xếp hạng có thể khác với việc xếp hạng toàn bộ rồi lọc. Cần xác định rõ top-N trong phạm vi nào.
- **Set operators:** `UNION` loại dòng trùng, còn `UNION ALL` giữ tất cả dòng. Chỉ thay `UNION` bằng `UNION ALL` khi đã chứng minh rằng dòng trùng không thể xuất hiện hoặc được phép giữ lại.

Ví dụ, nếu cần xếp hạng đơn hàng theo từng khách hàng, truy vấn phải xác định đúng tập đơn hàng tham gia xếp hạng:

```sql
SELECT customer_id, order_id, order_date, rn
FROM (
    SELECT
        customer_id,
        order_id,
        order_date,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY order_date DESC, order_id DESC
        ) AS rn
    FROM orders
    WHERE status = 'PAID'
)
WHERE rn <= 3;
```

Ở đây, điều kiện `status = 'PAID'` xác định những đơn được đưa vào phép xếp hạng. Điều kiện `rn <= 3` phải được áp dụng sau khi `ROW_NUMBER` được tính. Chuyển điều kiện thứ hai vào cùng query block trước analytic function sẽ không giữ được ý nghĩa top 3.

## 7. Đo lường bằng execution plan thay vì phỏng đoán

Sau khi sửa SQL, cần kiểm tra Oracle có thực sự đọc ít dòng và ít dữ liệu hơn hay không. Một câu SQL ngắn hơn hoặc có thêm CTE không tự động chạy nhanh hơn.

### 7.1. Xem kế hoạch thực thi ước tính

Có thể dùng `EXPLAIN PLAN` để xem kế hoạch Oracle dự kiến:

```sql
EXPLAIN PLAN FOR
SELECT order_id, order_date, total_amount
FROM orders
WHERE customer_id = :customer_id
  AND order_date >= :from_date
  AND order_date <  :to_date;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
```

`EXPLAIN PLAN` không thực thi câu SQL. Các con số trong đó là ước tính dựa trên thông tin thống kê mà optimizer sử dụng; chúng có thể khác với dữ liệu thực tế của một lần chạy cụ thể.

### 7.2. Xem số liệu của lần thực thi thực tế

Khi cần biết số dòng thực sự đi qua từng bước, có thể thu thập runtime statistics bằng hint `GATHER_PLAN_STATISTICS` rồi xem cursor vừa chạy:

```sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       order_id,
       order_date,
       total_amount
FROM orders
WHERE customer_id = :customer_id
  AND order_date >= :from_date
  AND order_date <  :to_date
ORDER BY order_date DESC, order_id DESC
FETCH FIRST 20 ROWS ONLY;

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE +ALIAS +MEMSTATS'
    )
);
```

`ALLSTATS LAST` hiển thị thống kê của lần thực thi gần nhất khi runtime statistics đã được thu thập. Hint ở ví dụ trên yêu cầu thu thập thống kê cho câu SQL đó; việc thu thập có thêm một ít overhead. Một cách khác là cấu hình `STATISTICS_LEVEL = ALL` trong phạm vi phù hợp, theo quyền và quy trình quản trị của môi trường.

Khi đọc kết quả, chú ý:

| Thông tin | Cách sử dụng |
|---|---|
| `E-Rows` | Số dòng optimizer ước tính cho một bước. |
| `A-Rows` | Số dòng thực tế được bước đó trả ra trong lần chạy được ghi nhận. |
| `Starts` | Số lần một bước được khởi chạy; cần xem cùng `A-Rows` để hiểu số dòng qua bước lặp. |
| `Buffers` | Số logical reads; hữu ích để so sánh lượng block phải xử lý. |
| `Reads` | Số physical reads được ghi nhận. |
| `A-Time` | Thời gian thực thi được ghi nhận cho bước, cần đọc trong ngữ cảnh toàn kế hoạch. |
| `TempSpc`, `OMem`, `1Mem`, `Used-Mem` | Cho biết ước tính không gian tạm và thông tin bộ nhớ của các phép toán có dùng vùng nhớ; xem các giá trị này cùng runtime statistics để nhận biết thao tác cần nhiều bộ nhớ hoặc có thể spill ra TEMP. |
| `Predicate Information` | Cho biết điều kiện truy cập và điều kiện lọc được áp dụng ở đâu. |

Nếu `A-Rows` ở một bước nối tăng đột biến so với đầu vào, hãy kiểm tra quan hệ một-nhiều và điều kiện join. Nếu `E-Rows` khác xa `A-Rows`, thống kê hoặc phân bố dữ liệu có thể khiến optimizer ước tính sai. Nếu bước sort hoặc hash nhận quá nhiều dòng, hãy tìm điều kiện lọc có thể áp dụng sớm hơn mà vẫn đúng ngữ nghĩa. Nếu số dòng đã nhỏ nhưng `Buffers` cao, hãy xem access path, index, partition pruning và số lần truy cập bảng.

Quyền xem cursor và runtime statistics phụ thuộc cấu hình, quyền truy cập và phiên bản Oracle. Trong môi trường dùng chung hoặc production, cần tuân theo quy trình vận hành hiện có khi thu thập và phân tích số liệu.

### 7.3. Kiểm tra cả kết quả lẫn hiệu năng

Khi so sánh truy vấn trước và sau tối ưu:

1. Dùng cùng bộ bind variable và cùng điều kiện dữ liệu đại diện.
2. Xác nhận số dòng và giá trị kết quả vẫn đúng yêu cầu nghiệp vụ.
3. So sánh execution plan, `A-Rows`, `Buffers`, `Reads`, thời gian và TEMP nếu có.
4. Thử với các giá trị bind có độ chọn lọc khác nhau; một truy vấn có thể nhanh với khách hàng ít đơn nhưng chậm với khách hàng có rất nhiều đơn.
5. Đánh giá tác động đến các truy vấn khác và chi phí ghi nếu thay đổi index.

Không kết luận chỉ từ một lần chạy hoặc chỉ từ thời gian đo ở máy phát triển. Cache, tải hệ thống, bind variable, thống kê và phân bố dữ liệu đều có thể làm kết quả khác nhau.

## 8. Quy trình thực hành tối ưu

Khi gặp một câu SQL xử lý quá nhiều dữ liệu, có thể đi theo quy trình sau:

1. **Xác định kết quả thật sự cần:** liệt kê cột đầu ra, phạm vi dòng, thứ tự, quy tắc nhóm và điều kiện nghiệp vụ.
2. **Tìm bước xử lý đắt đỏ:** xem execution plan và runtime statistics; xác định sort, hash join, group by, distinct, table access hoặc LOB access đang tiêu tốn tài nguyên.
3. **Giảm dòng ở nguồn:** đưa điều kiện độc lập với phép tổng hợp vào `WHERE`, lọc theo khoảng phù hợp, tận dụng partition pruning và xem xét index theo workload.
4. **Giảm độ rộng dữ liệu:** bỏ `SELECT *`, không mang theo cột LOB hoặc cột không được dùng, chỉ giữ khóa nối và cột phục vụ tính toán.
5. **Tránh tạo dòng thừa:** kiểm tra quan hệ một-nhiều, dùng `EXISTS` khi chỉ cần kiểm tra sự tồn tại, và chỉ dùng `DISTINCT` khi kết quả thực sự yêu cầu loại trùng.
6. **Giới hạn kết quả có chủ đích:** nếu chỉ cần top-N, dùng `ORDER BY` ổn định kết hợp `FETCH FIRST`; cân nhắc keyset pagination cho trang sâu.
7. **Đo lại và xác nhận:** so sánh số dòng thực tế qua từng bước, logical reads, physical reads, TEMP và thời gian; đồng thời kiểm tra kết quả nghiệp vụ.

## 9. Những lỗi thường gặp cần tránh

| Cách làm | Vấn đề | Hướng xử lý |
|---|---|---|
| `SELECT *` dù chỉ cần vài cột | Tăng lượng dữ liệu đọc, truyền và giữ trong các bước trung gian. | Liệt kê các cột thực sự cần. |
| `TRUNC(date_col) = ...` | Có thể cản trở index thường và partition pruning. | Dùng khoảng `>=` và `<` trên cột gốc, hoặc cân nhắc function-based index nếu phù hợp. |
| Dùng `DISTINCT` để sửa kết quả bị nhân dòng | Phải xử lý thêm dữ liệu và có thể che giấu join sai. | Kiểm tra cardinality; dùng `EXISTS` nếu chỉ cần biết có dòng liên quan. |
| Sắp xếp toàn bộ dữ liệu rồi mới giới hạn | Có thể tạo sort lớn. | Dùng top-N đúng cách và kiểm tra access path. |
| Đưa điều kiện của outer join từ `ON` xuống `WHERE` | Có thể làm mất các dòng không có bản ghi khớp. | Kiểm tra ngữ nghĩa `NULL` và vị trí điều kiện. |
| Tạo index cho mọi cột lọc | Tăng dung lượng và chi phí DML; index có thể không được chọn. | Đánh giá độ chọn lọc, thứ tự cột, workload và execution plan. |
| Ép index bằng hint khi chưa đo | Có thể khóa truy vấn vào kế hoạch kém khi dữ liệu thay đổi. | Để optimizer chọn trước; chỉ dùng hint khi có bằng chứng và quy trình kiểm soát. |
| Nghĩ rằng CTE luôn được vật hóa | Oracle có thể inline hoặc merge CTE. | Dùng CTE để làm rõ logic; xác nhận kế hoạch thực thi thực tế. |

## 10. Ví dụ tổng hợp

Giả sử màn hình cần hiển thị 20 đơn hàng đã thanh toán gần nhất của một khách hàng. Bảng có nhiều cột, bao gồm `NOTES` kiểu `CLOB`, và dữ liệu trải dài nhiều năm.

Một truy vấn chưa được thu gọn có thể đọc mọi cột, áp dụng hàm lên ngày rồi sắp xếp toàn bộ các đơn của khách hàng:

```sql
SELECT *
FROM orders
WHERE customer_id = :customer_id
  AND status = 'PAID'
  AND TRUNC(order_date) <= TRUNC(:as_of_date)
ORDER BY order_date DESC;
```

Truy vấn có thể viết rõ phạm vi dữ liệu và cột cần trả về như sau:

```sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       order_id,
       order_date,
       total_amount
FROM orders
WHERE customer_id = :customer_id
  AND status = 'PAID'
  AND order_date < :next_day
ORDER BY order_date DESC, order_id DESC
FETCH FIRST 20 ROWS ONLY;
```

Ứng dụng đặt `:next_day` là thời điểm bắt đầu ngày kế tiếp theo múi giờ và quy tắc nghiệp vụ đã thống nhất. Truy vấn mới:

- Chỉ lấy ba cột cần hiển thị, không truy xuất `NOTES` và các cột không dùng.
- Lọc theo khách hàng, trạng thái và mốc thời gian ngay tại bảng nguồn.
- Không áp dụng `TRUNC` lên `ORDER_DATE`, tạo điều kiện thuận lợi cho index hoặc partition pruning phù hợp.
- Chỉ yêu cầu 20 dòng đầu theo một thứ tự có tiêu chí phụ để ổn định khi trùng ngày.

Một index ứng viên có thể được đánh giá là `(CUSTOMER_ID, STATUS, ORDER_DATE, ORDER_ID)`, nhưng thứ tự và hướng sắp xếp cần được kiểm tra theo phân bố dữ liệu, các truy vấn liên quan và execution plan. Nếu trạng thái có độ chọn lọc thấp hoặc bảng được partition theo ngày, phương án tối ưu có thể khác. Không thể kết luận index nào tốt nhất chỉ từ câu SQL.

Sau khi chạy truy vấn với bộ bind đại diện, xem `DBMS_XPLAN.DISPLAY_CURSOR` để xác nhận Oracle có giảm số dòng ở bước truy cập `ORDERS`, có tránh đọc các cột không cần, có dùng access path phù hợp và có giới hạn sort hiệu quả hay không. Cuối cùng, so sánh kết quả với truy vấn ban đầu để bảo đảm điều kiện ngày và thứ tự mới vẫn đúng yêu cầu.

## Kết luận

Khi tối ưu SQL trên Oracle, hãy làm rõ phạm vi dòng và tập cột cần thiết trước khi dữ liệu đi vào các phép nối, sắp xếp, nhóm, loại trùng và tính toán cửa sổ. Điều kiện lọc phù hợp, projection gọn, cách nối đúng với mục tiêu và giới hạn kết quả có chủ đích thường giúp giảm CPU, bộ nhớ, I/O và TEMP. Hiệu quả cuối cùng phải được xác nhận bằng execution plan, thống kê thực tế và kiểm tra tính đúng đắn của kết quả.
# Giảm số dòng và số cột được xử lý trước các thao tác tốn chi phí

Một truy vấn SQL có thể phải đọc hàng triệu dòng nhưng chỉ trả về vài chục dòng. Hiệu năng phụ thuộc rất lớn vào việc Oracle có loại bỏ dữ liệu không cần thiết sớm hay phải mang một tập dữ liệu lớn qua nhiều operation như join, sort, group by, window function hoặc trao đổi dữ liệu giữa các process.

Hai đại lượng cần quan tâm là:

- **Số dòng (cardinality):** có bao nhiêu dòng đi qua mỗi row source.
- **Độ rộng dòng (row width):** mỗi dòng mang bao nhiêu cột và bao nhiêu byte.

Một tập dữ liệu có ít dòng nhưng mỗi dòng chứa nhiều cột lớn vẫn có thể tốn bộ nhớ và I/O. Ngược lại, một tập dữ liệu hẹp nhưng có hàng triệu dòng vẫn có thể làm hash join, sort hoặc aggregation trở nên đắt đỏ. Tối ưu truy vấn vì vậy cần giảm cả số dòng lẫn số cột ở những vị trí phù hợp trong cây thực thi.

Nguyên tắc thực hành là đưa điều kiện lọc đến gần nguồn dữ liệu, chỉ lấy những cột thực sự cần, và bảo đảm các phép join/aggregate/sort nhận đầu vào nhỏ nhất có thể mà vẫn giữ nguyên ngữ nghĩa SQL.

## 1. Vì sao số dòng và số cột quan trọng?

Giả sử một truy vấn đọc bảng `ORDERS` có 8 triệu dòng, nhưng chỉ cần đơn hàng của một khách hàng trong một tháng. Nếu Oracle phải đọc và xử lý nhiều dòng trước khi áp dụng điều kiện lọc, các operation phía trên có thể phải làm việc nhiều hơn mức cần thiết.

Hãy hình dung một pipeline:

```text
TABLE ACCESS
    ↓
JOIN
    ↓
SORT
    ↓
GROUP BY
    ↓
RESULT
```

Nếu lọc được dữ liệu ngay tại table access, join và sort phía trên sẽ nhận ít dòng hơn. Nếu chỉ chọn các cột cần thiết, mỗi dòng truyền qua pipeline cũng nhẹ hơn.

### 1.1. Cardinality ảnh hưởng đến chi phí operation

Số dòng đầu vào ảnh hưởng trực tiếp đến lượng công việc của nhiều operation:

- Nested loops có thể thực hiện lookup ở nhánh trong theo số dòng của nhánh ngoài.
- Hash join phải xây dựng và dò hash table dựa trên kích thước các đầu vào.
- Sort phải sắp xếp tập dòng nhận được.
- Group by phải duy trì trạng thái tổng hợp cho các nhóm.
- Window function phải xử lý các partition và thứ tự dòng tương ứng.
- Parallel execution có thể phải phân phối một lượng dữ liệu lớn giữa các process.

Nếu một predicate giảm số dòng từ 2.000.000 xuống 5.000, những operation phía trên có thể tiết kiệm rất nhiều công việc. Tuy nhiên, không phải predicate nào cũng có thể được đẩy xuống thấp nhất: SQL có quy tắc về outer join, aggregation, analytic function và subquery mà optimizer phải bảo toàn.

### 1.2. Độ rộng dòng ảnh hưởng đến bộ nhớ và I/O

Hai truy vấn có thể đọc cùng 100.000 dòng nhưng có chi phí khác nhau nếu một truy vấn chỉ lấy khóa và số tiền, còn truy vấn kia lấy thêm nhiều cột văn bản lớn hoặc LOB.

Ví dụ:

```sql
-- Chỉ lấy dữ liệu cần cho báo cáo.
SELECT order_id,
       customer_id,
       total_amount
FROM orders
WHERE order_status = 'PAID';
```

```sql
-- Lấy toàn bộ cột dù báo cáo chỉ cần ba cột.
SELECT *
FROM orders
WHERE order_status = 'PAID';
```

`SELECT *` có thể làm tăng số byte cần đọc, truyền, lưu trong workarea và trả về client. Nó cũng khiến câu SQL phụ thuộc vào cấu trúc bảng nhiều hơn. Oracle có thể thực hiện projection pruning trong các trường hợp mà cột không được sử dụng, nhưng khi câu SQL yêu cầu mọi cột thì optimizer phải đáp ứng yêu cầu đó.

### 1.3. Mục tiêu không phải luôn giảm mọi operation

Một full table scan không mặc nhiên xấu. Nếu truy vấn cần phần lớn dữ liệu hoặc bảng nhỏ, full scan có thể là cách hiệu quả nhất. Một sort có thể là bắt buộc nếu kết quả phải được sắp xếp theo một thứ tự không có sẵn.

Mục tiêu là giảm công việc không cần thiết. Hãy xem số dòng và số byte thực sự cần qua từng operation, thay vì cố loại bỏ một operation chỉ vì tên của nó.

## 2. Lọc dữ liệu sớm bằng WHERE và predicate pushdown

`WHERE` xác định điều kiện lọc dòng trước khi kết quả được chuyển tiếp qua các bước tiếp theo theo ngữ nghĩa truy vấn. Oracle Optimizer có thể thực hiện *predicate pushdown*: đẩy predicate xuống gần nguồn dữ liệu hơn để giảm số dòng trung gian.

Ví dụ, truy vấn cần các đơn hàng đã thanh toán trong tháng 10:

```sql
SELECT o.order_id,
       o.customer_id,
       o.total_amount
FROM orders o
WHERE o.order_status = 'PAID'
  AND o.order_date >= DATE '2026-10-01'
  AND o.order_date <  DATE '2026-11-01';
```

Nếu plan áp dụng hai predicate ngay tại access path của `ORDERS`, chỉ các dòng phù hợp mới được chuyển lên join hoặc aggregation phía trên (nếu có). Cách viết điều kiện theo khoảng nửa mở cũng tránh phải biến đổi cột ngày thành chuỗi hoặc cắt bỏ phần thời gian.

### 2.1. Predicate có thể dùng index và partition pruning

Một predicate thường dễ sử dụng index hơn khi nó so sánh trực tiếp cột với một giá trị hoặc bind value có kiểu tương thích:

```sql
WHERE order_id = :p_order_id
```

```sql
WHERE order_date >= :p_from_date
  AND order_date <  :p_to_date
```

Ngược lại, các biểu thức biến đổi cột có thể khiến index thông thường khó được sử dụng như mong muốn:

```sql
-- Có thể cản trở range access trên index thông thường của ORDER_DATE.
WHERE TRUNC(order_date) = DATE '2026-10-15'
```

Có thể viết lại thành khoảng ngày:

```sql
WHERE order_date >= DATE '2026-10-15'
  AND order_date <  DATE '2026-10-16'
```

Nếu nghiệp vụ thực sự cần truy vấn theo biểu thức `TRUNC(order_date)`, có thể cân nhắc function-based index hoặc virtual column phù hợp. Việc viết lại predicate cần giữ đúng kiểu dữ liệu, múi giờ và quy tắc nghiệp vụ.

Tránh chuyển cột bằng `TO_CHAR`, `TO_NUMBER` hoặc hàm khác khi không cần thiết. Cũng cần chú ý implicit conversion: nếu hai phía so sánh khác kiểu, Oracle có thể phải chuyển đổi một phía và làm access path kém hiệu quả. Hãy dùng bind variable có kiểu dữ liệu đúng với cột.

### 2.2. Dùng khoảng thời gian thay vì áp dụng hàm lên cột

Với cột `DATE` có cả giờ, điều kiện:

```sql
WHERE order_date = DATE '2026-10-15'
```

chỉ khớp giá trị đúng tại nửa đêm của ngày đó. Nếu mục tiêu là toàn bộ ngày, dùng khoảng nửa mở:

```sql
WHERE order_date >= DATE '2026-10-15'
  AND order_date <  DATE '2026-10-16'
```

Không nên dùng:

```sql
WHERE TO_CHAR(order_date, 'YYYY-MM-DD') = '2026-10-15'
```

vì biểu thức chuyển đổi có thể làm index thông thường trên `ORDER_DATE` không còn là access path thuận lợi, đồng thời phụ thuộc format rõ ràng. Với `TIMESTAMP` hoặc `TIMESTAMP WITH TIME ZONE`, cần chọn kiểu bind và ranh giới thời gian đúng với semantics của ứng dụng.

### 2.3. Điều kiện có OR

Một số predicate dùng `OR` có thể khiến optimizer khó chọn một access path đơn giản:

```sql
SELECT order_id, order_date
FROM orders
WHERE customer_id = :p_customer_id
   OR order_status = :p_status;
```

Oracle có thể dùng OR expansion để biến đổi thành các nhánh riêng, nếu điều đó có lợi và bảo toàn ngữ nghĩa. Trong một số trường hợp, có thể viết lại thành `UNION ALL` với điều kiện loại trừ trùng lặp:

```sql
SELECT order_id, order_date
FROM orders
WHERE customer_id = :p_customer_id

UNION ALL

SELECT order_id, order_date
FROM orders
WHERE order_status = :p_status
  AND (customer_id <> :p_customer_id OR customer_id IS NULL);
```

Ví dụ này minh họa việc tách hai nhánh và tránh trả lại dòng thỏa cả hai điều kiện. Phần xử lý `NULL` rất quan trọng vì so sánh SQL với `NULL` trả về UNKNOWN. Không nên áp dụng mẫu rewrite này nếu chưa chứng minh tương đương cho kiểu dữ liệu, NULL semantics và yêu cầu loại trùng của truy vấn gốc. `UNION` loại trùng nhưng thường phải có bước distinct; `UNION ALL` giữ trùng và thường nhẹ hơn khi các nhánh đã được làm rời nhau.

### 2.4. Predicate pushdown qua view và subquery

Ví dụ một view tổng hợp:

```sql
SELECT *
FROM (
    SELECT customer_id,
           order_status,
           SUM(total_amount) AS amount
    FROM orders
    GROUP BY customer_id, order_status
) x
WHERE x.order_status = 'PAID';
```

Oracle có thể đẩy điều kiện trên `ORDER_STATUS` xuống trước bước group by nếu điều đó bảo toàn ngữ nghĩa:

```sql
SELECT customer_id,
       order_status,
       SUM(total_amount) AS amount
FROM orders
WHERE order_status = 'PAID'
GROUP BY customer_id, order_status;
```

Điều kiện lọc trước aggregation giúp giảm số dòng phải gom nhóm. Nhưng không phải mọi predicate bên ngoài đều có thể đẩy qua mọi view. Predicate liên quan đến kết quả tổng hợp, analytic function, outer join hoặc phép biến đổi khác có thể cần giữ ở tầng trên.

Việc viết inline view không đảm bảo Oracle materialize kết quả thành bảng tạm. Optimizer có thể merge view, push predicate hoặc biến đổi query block. Hãy xác nhận bằng execution plan thay vì suy luận chỉ từ hình thức SQL.

## 3. Giảm dữ liệu trước khi JOIN

Join có thể làm tăng lượng công việc rất nhanh, đặc biệt khi một bảng lớn được kết hợp với một bảng khác trước khi áp dụng điều kiện lọc có độ chọn lọc cao.

Giả sử cần danh sách đơn hàng đã thanh toán của một vùng:

```sql
SELECT o.order_id,
       o.order_date,
       c.customer_name
FROM orders o
JOIN customers c
  ON c.customer_id = o.customer_id
WHERE o.order_status = 'PAID'
  AND c.region_id = :p_region_id;
```

Optimizer có thể đẩy predicate trên `ORDERS` và `CUSTOMERS` xuống các row source tương ứng trước khi join. Nếu dữ liệu vùng chỉ chiếm một phần nhỏ và trạng thái `PAID` cũng chọn lọc tốt, các nhánh đầu vào có thể nhỏ hơn đáng kể.

Không cần viết lại mọi truy vấn thành inline view để ép lọc trước join. Trước tiên hãy viết predicate rõ ràng, bảo đảm thống kê phù hợp và kiểm tra plan. Nếu optimizer không push được điều kiện vì cấu trúc query block hoặc ràng buộc ngữ nghĩa, lúc đó mới cân nhắc rewrite có kiểm chứng.

### 3.1. Dùng EXISTS khi chỉ cần biết có bản ghi liên quan

Nếu chỉ cần lấy khách hàng có ít nhất một đơn hàng đã thanh toán, không cần join để trả các cột của đơn hàng:

```sql
SELECT c.customer_id,
       c.customer_name
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
      AND o.order_status = 'PAID'
);
```

`EXISTS` thể hiện đúng ý định kiểm tra sự tồn tại. Oracle có thể biến đổi thành semi join, cho phép dừng tìm kiếm khi tìm được một dòng phù hợp thay vì tạo mọi cặp dòng rồi loại trùng.

So sánh với cách join rồi distinct:

```sql
SELECT DISTINCT c.customer_id,
                c.customer_name
FROM customers c
JOIN orders o
  ON o.customer_id = c.customer_id
WHERE o.order_status = 'PAID';
```

Nếu một khách hàng có nhiều đơn hàng, join tạo nhiều dòng cho cùng khách hàng rồi `DISTINCT` phải loại trùng. `EXISTS` mô tả trực tiếp yêu cầu và thường tránh được lượng dòng trung gian đó. Optimizer vẫn có thể biến đổi cả hai câu SQL; cần xem plan và bảo đảm semantics giống nhau.

### 3.2. Dùng NOT EXISTS cho kiểm tra không tồn tại

Để tìm khách hàng chưa từng có đơn hàng:

```sql
SELECT c.customer_id,
       c.customer_name
FROM customers c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
);
```

Oracle có thể dùng anti join. Cách viết này tránh phải tạo toàn bộ kết quả join rồi tìm các dòng không khớp.

Cẩn thận khi thay `NOT IN` bằng `NOT EXISTS`. Nếu subquery của `NOT IN` có thể trả về `NULL`, kết quả của `NOT IN` tuân theo three-valued logic và có thể khác `NOT EXISTS`. Phải xử lý NULL theo đúng yêu cầu nghiệp vụ.

### 3.3. Chỉ join những cột cần thiết

Khi join, không nên mang toàn bộ cột của các bảng qua nhiều operation nếu kết quả chỉ dùng một vài cột:

```sql
SELECT o.order_id,
       c.customer_name
FROM orders o
JOIN customers c
  ON c.customer_id = o.customer_id
WHERE o.order_status = 'PAID';
```

Ở đây, truy vấn chỉ cần `ORDER_ID`, `CUSTOMER_NAME`, `CUSTOMER_ID` để join và `ORDER_STATUS` để lọc. Không cần truyền thêm địa chỉ, ghi chú dài, LOB hoặc các thuộc tính khác nếu không được sử dụng.

Projection pruning có thể loại bỏ cột không cần thiết ở các tầng trong plan. Tuy nhiên, `SELECT *`, view chứa nhiều cột hoặc các biểu thức yêu cầu dữ liệu rộng có thể làm giảm cơ hội pruning và tăng chi phí truyền dữ liệu.

## 4. Giảm số cột bằng projection pruning

Projection là việc xác định cột nào cần được giữ lại tại mỗi bước xử lý. Optimizer có thể đẩy projection xuống gần nguồn dữ liệu để chỉ đọc hoặc truyền những cột cần thiết cho các operation phía trên.

Ví dụ truy vấn báo cáo:

```sql
SELECT customer_id,
       SUM(total_amount) AS total_amount
FROM orders
WHERE order_status = 'PAID'
GROUP BY customer_id;
```

Các cột cần thiết là:

- `CUSTOMER_ID` để group by.
- `TOTAL_AMOUNT` để tính tổng.
- `ORDER_STATUS` để lọc.

Các cột như `ORDER_NOTE`, `SHIPPING_ADDRESS`, `ATTACHMENT` hoặc `CREATED_BY` không tham gia truy vấn nên không cần mang qua aggregation.

### 4.1. Tránh SELECT *

`SELECT *` thường tạo ra các vấn đề sau:

- Đọc hoặc truyền các cột không cần thiết.
- Tăng kích thước row source và workarea.
- Làm truy vấn nhạy cảm hơn với việc thêm cột vào bảng.
- Có thể ngăn một số covering index đáp ứng hoàn toàn truy vấn.
- Tăng dữ liệu trả qua network tới ứng dụng.

Thay vì:

```sql
SELECT *
FROM orders
WHERE order_status = 'PAID';
```

hãy chọn rõ cột:

```sql
SELECT order_id,
       customer_id,
       order_date,
       total_amount
FROM orders
WHERE order_status = 'PAID';
```

Việc chọn rõ cột cũng làm hợp đồng dữ liệu của API ổn định hơn. Khi bảng có thêm cột mới, kết quả truy vấn không tự nhiên thay đổi về hình dạng.

### 4.2. Cột trong SELECT, WHERE, JOIN và ORDER BY

Một cột có thể không xuất hiện trong danh sách SELECT nhưng vẫn cần được đọc để lọc, join, group hoặc sắp xếp. Projection pruning không có nghĩa chỉ lấy những cột được trả về cuối cùng; nó giữ mọi cột cần thiết cho toàn bộ phép tính.

Ví dụ:

```sql
SELECT order_id,
       total_amount
FROM orders
WHERE customer_id = :p_customer_id
ORDER BY order_date DESC;
```

`CUSTOMER_ID` và `ORDER_DATE` không được trả về nhưng vẫn cần cho predicate và order by. Nếu một index phù hợp chứa các cột liên quan, Oracle có thể đáp ứng truy vấn từ index mà không cần table access, tùy cấu trúc index và các cột được yêu cầu.

### 4.3. Covering index và độ rộng dữ liệu

Một index có thể bao phủ truy vấn nếu chứa tất cả cột cần thiết để lọc, join, sắp xếp và trả kết quả. Khi đó Oracle có thể tránh table access bằng rowid.

Ví dụ, truy vấn:

```sql
SELECT order_id,
       order_date
FROM orders
WHERE customer_id = :p_customer_id;
```

có thể được đáp ứng bởi một index bắt đầu bằng `CUSTOMER_ID` và chứa `ORDER_ID`, `ORDER_DATE` theo cấu trúc phù hợp. Tuy nhiên, không nên thêm mọi cột vào index chỉ để bao phủ một truy vấn. Index rộng hơn làm tăng dung lượng, chi phí DML, redo/undo và bảo trì.

Hãy cân bằng số cột truy vấn cần với chi phí duy trì index. Việc tạo index là quyết định thiết kế riêng; projection pruning không đồng nghĩa phải tạo một index cho mỗi SELECT.

## 5. Giảm dữ liệu trước GROUP BY và aggregation

Aggregation thường phải xử lý tất cả các dòng thuộc phạm vi nhóm. Nếu có thể lọc dòng trước khi group, số dòng cần tổng hợp sẽ giảm.

Ví dụ:

```sql
SELECT customer_id,
       SUM(total_amount) AS total_amount
FROM orders
WHERE order_status = 'PAID'
  AND order_date >= DATE '2026-01-01'
GROUP BY customer_id;
```

Điều kiện `WHERE` loại bỏ các dòng không liên quan trước khi aggregation xử lý chúng. Nếu điều kiện được áp dụng ở table access, hash group by hoặc sort group by nhận ít dòng hơn.

### 5.1. WHERE và HAVING có vai trò khác nhau

`WHERE` lọc dòng đầu vào trước khi group. `HAVING` lọc nhóm sau khi đã tính toán aggregate.

Ví dụ:

```sql
SELECT customer_id,
       SUM(total_amount) AS total_amount
FROM orders
WHERE order_status = 'PAID'
GROUP BY customer_id
HAVING SUM(total_amount) > 100000;
```

`ORDER_STATUS = 'PAID'` là điều kiện trên từng dòng nên đặt ở `WHERE`. `SUM(TOTAL_AMOUNT) > 100000` phụ thuộc kết quả tổng hợp nên đặt ở `HAVING`.

Không thể chuyển mọi điều kiện `HAVING` thành `WHERE`. Ví dụ `HAVING SUM(total_amount) > 100000` không tương đương với việc lọc từng đơn hàng có `TOTAL_AMOUNT > 100000`.

### 5.2. Pre-aggregation trước khi join

Nếu cần join một bảng chi tiết rất lớn với bảng khác nhưng chỉ cần tổng hợp theo khóa, có thể tổng hợp trước rồi join kết quả nhỏ hơn.

Ví dụ cần tổng số tiền theo khách hàng và tên khách hàng:

```sql
WITH order_totals AS (
    SELECT customer_id,
           SUM(total_amount) AS total_amount
    FROM orders
    WHERE order_status = 'PAID'
    GROUP BY customer_id
)
SELECT c.customer_id,
       c.customer_name,
       ot.total_amount
FROM order_totals ot
JOIN customers c
  ON c.customer_id = ot.customer_id;
```

Nếu `ORDERS` có hàng triệu dòng nhưng số khách hàng ít hơn nhiều, pre-aggregation có thể làm giảm số dòng đi vào join. Tuy nhiên, Oracle có thể tự thực hiện group-by placement hoặc các query transformation tương tự. CTE không tự đảm bảo materialization.

### 5.3. Bảo toàn ngữ nghĩa khi pre-aggregate

Pre-aggregation chỉ đúng nếu giữ nguyên quan hệ giữa dữ liệu và phép tính. Hãy cẩn thận khi:

- Join có quan hệ one-to-many hoặc many-to-many làm nhân bản dòng.
- Aggregate phụ thuộc cột từ bảng được join.
- Có outer join và cần giữ lại nhóm không có dòng khớp.
- Có `COUNT(DISTINCT ...)`, analytic function hoặc điều kiện `HAVING`.
- Dữ liệu có NULL và aggregate có quy tắc bỏ qua NULL.

Ví dụ nếu một khách hàng có nhiều dòng trong bảng địa chỉ, join `CUSTOMERS` với `ADDRESSES` trước khi tính tổng đơn hàng có thể nhân bản số tiền. Tổng hợp đơn hàng theo khách hàng trước rồi join địa chỉ có thể đúng hơn nếu báo cáo cần tổng theo khách hàng, nhưng sẽ không đúng nếu mục tiêu là tổng theo từng địa chỉ và mỗi đơn hàng phải được phân bổ theo một quy tắc cụ thể.

Không nên rewrite chỉ để giảm cardinality mà không kiểm tra multiplicity và NULL semantics. Tối ưu hóa phải bảo toàn kết quả.

## 6. Giảm dữ liệu trước SORT và TOP-N

Sort có thể tốn CPU, bộ nhớ và TEMP. Nếu truy vấn chỉ cần một số dòng đầu theo thứ tự xác định, hãy diễn đạt rõ giới hạn dòng để Oracle có cơ hội sử dụng top-N optimization hoặc stopkey.

Ví dụ lấy 20 đơn hàng mới nhất:

```sql
SELECT order_id,
       order_date,
       total_amount
FROM orders
WHERE customer_id = :p_customer_id
ORDER BY order_date DESC, order_id DESC
FETCH FIRST 20 ROWS ONLY;
```

Oracle 12c trở lên hỗ trợ row limiting clause `FETCH FIRST`. Việc có thể dừng sớm hay không phụ thuộc access path và thứ tự cần thiết. Nếu có index phù hợp bắt đầu bằng `CUSTOMER_ID` và tiếp theo hỗ trợ thứ tự ngày/ID, Oracle có thể đọc một phần index rồi dừng khi đủ 20 dòng. Nếu không có access path cung cấp thứ tự, có thể vẫn phải đọc nhiều dòng và dùng sort top-N.

### 6.1. ORDER BY phải xác định thứ tự ổn định

Nếu nhiều dòng có cùng `ORDER_DATE`, truy vấn chỉ `ORDER BY ORDER_DATE DESC` không xác định duy nhất dòng nào nằm trước trong nhóm ngày bằng nhau. Thêm khóa phân biệt như `ORDER_ID` giúp kết quả phân trang/top-N ổn định hơn:

```sql
ORDER BY order_date DESC, order_id DESC
FETCH FIRST 20 ROWS ONLY;
```

Không nên bỏ `ORDER BY` chỉ để query chạy nhanh hơn nếu nghiệp vụ cần thứ tự. Không có `ORDER BY`, Oracle không đảm bảo thứ tự kết quả.

### 6.2. OFFSET pagination và keyset pagination

Phân trang bằng OFFSET:

```sql
SELECT order_id,
       order_date,
       total_amount
FROM orders
WHERE customer_id = :p_customer_id
ORDER BY order_date DESC, order_id DESC
OFFSET 10000 ROWS FETCH NEXT 20 ROWS ONLY;
```

Oracle có thể phải đi qua hoặc loại bỏ nhiều dòng trước khi trả trang thứ 501. OFFSET càng lớn, lượng dòng cần xử lý có thể càng lớn.

Nếu giao diện có thể gửi khóa của dòng cuối trang trước, keyset pagination thường hiệu quả hơn:

```sql
SELECT order_id,
       order_date,
       total_amount
FROM orders
WHERE customer_id = :p_customer_id
  AND (
        order_date < :p_last_order_date
        OR (
            order_date = :p_last_order_date
            AND order_id < :p_last_order_id
        )
      )
ORDER BY order_date DESC, order_id DESC
FETCH FIRST 20 ROWS ONLY;
```

Với index phù hợp, truy vấn có thể bắt đầu từ vị trí sau khóa cuối trang trước thay vì bỏ qua một số lượng lớn dòng. Điều kiện phải khớp hoàn toàn với thứ tự sắp xếp và xử lý NULL theo quy tắc rõ ràng. Nếu dữ liệu thay đổi giữa các lần lấy trang, keyset pagination cũng thường tránh một số vấn đề dịch chuyển trang của OFFSET.

### 6.3. Không giới hạn dòng trước khi sắp xếp

Mẫu sau không có nghĩa là lấy 20 dòng mới nhất:

```sql
SELECT *
FROM (
    SELECT order_id, order_date
    FROM orders
    WHERE customer_id = :p_customer_id
    FETCH FIRST 20 ROWS ONLY
)
ORDER BY order_date DESC;
```

Nó giới hạn 20 dòng trước rồi mới sắp xếp 20 dòng đó. Nếu không có thứ tự bên trong subquery, 20 dòng được chọn không xác định và có thể không phải 20 dòng mới nhất. Hãy đặt `ORDER BY` cùng row limiting clause ở đúng query block:

```sql
SELECT order_id,
       order_date
FROM orders
WHERE customer_id = :p_customer_id
ORDER BY order_date DESC, order_id DESC
FETCH FIRST 20 ROWS ONLY;
```

## 7. Giảm dữ liệu trước analytic/window function

Analytic function như `ROW_NUMBER`, `RANK`, `SUM(...) OVER (...)` thường cần xem nhiều dòng trong partition và có thể yêu cầu sort theo partition/order key. Vì vậy, lọc đúng phạm vi dữ liệu trước analytic function có thể giảm chi phí đáng kể.

Ví dụ lấy đơn hàng mới nhất của mỗi khách hàng trong nhóm đơn đã thanh toán:

```sql
SELECT customer_id,
       order_id,
       order_date,
       total_amount
FROM (
    SELECT o.customer_id,
           o.order_id,
           o.order_date,
           o.total_amount,
           ROW_NUMBER() OVER (
               PARTITION BY o.customer_id
               ORDER BY o.order_date DESC, o.order_id DESC
           ) AS rn
    FROM orders o
    WHERE o.order_status = 'PAID'
      AND o.order_date >= DATE '2026-01-01'
)
WHERE rn = 1;
```

Điều kiện trạng thái và ngày lọc dòng trước khi tính `ROW_NUMBER`. Predicate `rn = 1` phải được áp dụng sau khi analytic function xác định thứ hạng; chuyển nó vào cùng tầng trước analytic sẽ làm thay đổi ý nghĩa.

### 7.1. Điều kiện nào có thể đẩy qua analytic?

Predicate trên cột không tham gia partition/order hoặc không làm thay đổi tập dòng cần xếp hạng có thể được đẩy xuống trong một số trường hợp. Nhưng predicate giới hạn chính các dòng trong partition có thể thay đổi thứ hạng, nên không thể tùy tiện chuyển vị trí.

Ví dụ, nếu mục tiêu là đơn hàng mới nhất trong số đơn đã thanh toán, lọc `ORDER_STATUS = 'PAID'` trước `ROW_NUMBER` là đúng. Nếu mục tiêu là xác định đơn hàng mới nhất nói chung rồi chỉ trả về đơn đó khi nó đã thanh toán, lọc trạng thái sau analytic mới đúng. Hai câu SQL có ý nghĩa khác nhau.

## 8. Partition pruning: tránh đọc partition không cần thiết

Nếu bảng được partition theo ngày hoặc tháng, predicate trên partition key có thể giúp Oracle chỉ đọc partition liên quan. Đây là một cách giảm số dòng và số block ngay tại nguồn dữ liệu.

Ví dụ bảng `SALES` partition theo `SALE_DATE`:

```sql
SELECT sale_id,
       customer_id,
       amount
FROM sales
WHERE sale_date >= DATE '2026-10-01'
  AND sale_date <  DATE '2026-11-01';
```

Nếu partition key và predicate tương thích, Oracle có thể chỉ truy cập partition của tháng 10. Plan có thể thể hiện `PARTITION RANGE SINGLE`, `PARTITION RANGE ITERATOR` hoặc operation partition khác.

Tránh bọc partition key trong hàm nếu không cần:

```sql
-- Có thể làm partition pruning khó hơn trong một số trường hợp.
WHERE TO_CHAR(sale_date, 'YYYYMM') = '202610'
```

Viết thành khoảng ngày thường rõ ràng hơn và dễ tận dụng pruning:

```sql
WHERE sale_date >= DATE '2026-10-01'
  AND sale_date <  DATE '2026-11-01'
```

Với partition pruning động, plan có thể hiển thị `KEY` ở `PSTART`/`PSTOP`; phạm vi được xác định khi chạy dựa trên bind hoặc giá trị runtime. Cần kiểm tra plan và runtime thay vì chỉ tìm một con số partition cố định.

## 9. Giảm dữ liệu trước khi trao đổi trong parallel hoặc distributed query

Parallel execution và distributed query có thể phải chuyển dữ liệu giữa process hoặc database. Số dòng và độ rộng dòng càng lớn thì chi phí trao đổi càng cao.

Với parallel plan, các operation `PX SEND` và `PX RECEIVE` thể hiện việc phân phối dữ liệu. Nếu có thể lọc và project trước `PX SEND`, lượng dữ liệu truyền giữa các process có thể giảm.

Với truy vấn qua database link, predicate pushdown có thể cho phép database từ xa lọc dữ liệu trước khi gửi về database cục bộ. Ví dụ:

```sql
SELECT order_id,
       total_amount
FROM remote_orders@reporting_link
WHERE order_status = 'PAID'
  AND order_date >= :p_from_date;
```

Nếu predicate được thực thi tại remote site, chỉ các dòng cần thiết mới phải đi qua network. Nếu database cục bộ kéo toàn bộ dữ liệu về rồi mới lọc, chi phí network có thể rất lớn.

Có thể xem thông tin remote operation và query plan theo khả năng của môi trường. Khi cần, kiểm tra plan ở cả database local và remote. Không nên giả định mọi predicate hoặc function đều được push qua database link; khả năng pushdown phụ thuộc SQL, kiểu dữ liệu, function, phiên bản và cấu hình.

## 10. CTE, inline view và materialization

CTE (`WITH`) và inline view giúp chia câu SQL thành các query block dễ đọc. Chúng không tự đảm bảo dữ liệu trung gian được tính một lần hoặc lưu thành bảng tạm.

Ví dụ:

```sql
WITH paid_orders AS (
    SELECT order_id,
           customer_id,
           total_amount
    FROM orders
    WHERE order_status = 'PAID'
)
SELECT customer_id,
       SUM(total_amount) AS total_amount
FROM paid_orders
GROUP BY customer_id;
```

Optimizer có thể merge query block `PAID_ORDERS` vào truy vấn bên ngoài, push predicate hoặc thực hiện phép biến đổi khác. Tùy trường hợp, Oracle cũng có thể materialize kết quả trung gian. Hãy kiểm tra plan để biết operation thực tế.

Không nên dùng hint `MATERIALIZE` hoặc `INLINE` một cách máy móc. Hint có thể ảnh hưởng cách thực hiện query block nhưng không thay thế việc xác định nguyên nhân chi phí. Cần cân nhắc số lần CTE được tham chiếu, kích thước dữ liệu trung gian, TEMP và khả năng predicate pushdown.

## 11. Ví dụ tổng hợp: lọc và project trước join, aggregate sau đó

Giả sử báo cáo cần tổng doanh thu theo vùng cho đơn đã thanh toán trong quý 4. Bảng `ORDERS` rất lớn, `ORDER_ITEMS` còn lớn hơn, còn `CUSTOMERS` chứa nhiều cột hồ sơ không cần cho báo cáo.

Một câu truy vấn rõ phạm vi dữ liệu:

```sql
WITH order_totals AS (
    SELECT o.order_id,
           o.customer_id,
           SUM(oi.quantity * oi.unit_price) AS order_amount
    FROM orders o
    JOIN order_items oi
      ON oi.order_id = o.order_id
    WHERE o.order_status = 'PAID'
      AND o.order_date >= DATE '2026-10-01'
      AND o.order_date <  DATE '2027-01-01'
    GROUP BY o.order_id,
             o.customer_id
)
SELECT c.region_id,
       SUM(ot.order_amount) AS total_revenue
FROM order_totals ot
JOIN customers c
  ON c.customer_id = ot.customer_id
GROUP BY c.region_id;
```

Điểm đáng chú ý:

1. Predicate trạng thái và ngày được đặt trực tiếp trên `ORDERS`, cho phép optimizer lọc gần nguồn dữ liệu.
2. Join chỉ cần `ORDER_ID` để kết hợp `ORDERS` với `ORDER_ITEMS` và `CUSTOMER_ID` để kết hợp với `CUSTOMERS`.
3. Chỉ các cột cần cho join và phép tính được giữ lại; không lấy `SELECT *`.
4. Dữ liệu chi tiết được tổng hợp theo đơn hàng trước khi join với bảng khách hàng.
5. Sau khi join, kết quả được tổng hợp theo vùng.

Đây là một cách tổ chức truy vấn để làm rõ mục tiêu. Optimizer có thể biến đổi query block hoặc chọn thứ tự thực thi khác. Cần xác nhận rằng việc tổng hợp theo đơn hàng trước khi join không làm thay đổi kết quả nếu dữ liệu có quan hệ một-nhiều hoặc các quy tắc phân bổ đặc biệt.

## 12. Kiểm chứng bằng execution plan và runtime statistics

Không thể kết luận một rewrite tốt hơn chỉ bằng cách đếm số dòng trong SQL hoặc nhìn câu lệnh ngắn hơn. Hãy đo plan trước và sau bằng dữ liệu và bind values đại diện.

Có thể yêu cầu Oracle thu thập row-source statistics:

```sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       o.order_id,
       o.customer_id,
       o.total_amount
FROM orders o
WHERE o.order_status = 'PAID'
  AND o.order_date >= DATE '2026-10-01'
  AND o.order_date <  DATE '2026-11-01';
```

Sau khi chạy trong cùng session:

```sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE +ALIAS +PARTITION'
    )
);
```

Các thông tin cần so sánh:

| Thông tin | Câu hỏi |
|---|---|
| `E-Rows` | Optimizer dự đoán bao nhiêu dòng ở mỗi operation? |
| `A-Rows` | Operation thực tế trả bao nhiêu dòng? |
| `Starts` | Operation được khởi chạy bao nhiêu lần? |
| `Buffers` | Bao nhiêu logical reads được sử dụng? |
| `Reads` | Có bao nhiêu physical reads được ghi nhận? |
| `A-Time` | Thời gian thực tế tập trung ở operation nào? |
| `Bytes` | Độ rộng dữ liệu ước lượng có lớn bất thường không? |
| `PSTART` / `PSTOP` | Đã prune đúng partition cần đọc chưa? |
| TEMP/workarea | Sort hoặc hash có spill ra TEMP không? |

### 12.1. Tìm nơi dữ liệu tăng hoặc giảm

Đọc actual rows từ các operation lá lên trên:

- Nếu table access trả quá nhiều dòng, xem predicate có được áp dụng sớm không và access path có phù hợp không.
- Nếu join tạo ra nhiều dòng hơn dự kiến, kiểm tra multiplicity, điều kiện join và cardinality estimates.
- Nếu aggregation nhận rất nhiều dòng, xem có thể lọc trước hoặc tổng hợp theo khóa sớm hơn mà vẫn đúng semantics không.
- Nếu sort nhận nhiều dòng hoặc dòng quá rộng, xem có thể giảm dữ liệu trước sort hoặc dùng access path cung cấp thứ tự không.
- Nếu nhánh trong nested loops có `Starts` rất lớn, xem số dòng outer và chi phí lookup mỗi lần.

### 12.2. Không chỉ nhìn A-Rows cuối cùng

Một truy vấn có thể trả 20 dòng nhưng vẫn đọc hàng triệu dòng và sort một tập rất lớn trước khi giới hạn kết quả. Vì vậy, `A-Rows` ở nút gốc không đủ để kết luận truy vấn hiệu quả.

Hãy xem các operation trung gian, `Starts`, `Buffers`, `A-Time` và predicate. Một operation có actual rows lớn nhưng thời gian nhỏ có thể không phải nút thắt; một operation có số dòng ít nhưng được chạy hàng trăm nghìn lần có thể tạo chi phí lớn.

## 13. Những rewrite cần thận trọng

Giảm số dòng và số cột là mục tiêu tốt, nhưng một rewrite không tương đương có thể trả kết quả sai. Các trường hợp cần chú ý:

- **Outer join:** đẩy điều kiện từ `WHERE` vào `ON` hoặc ngược lại có thể thay đổi việc giữ dòng không khớp.
- **Aggregation:** chuyển điều kiện giữa `WHERE` và `HAVING` có thể làm thay đổi tập dòng được tổng hợp.
- **Analytic function:** lọc trước hay sau `ROW_NUMBER`/`RANK` có thể tạo thứ hạng khác.
- **DISTINCT:** bỏ hoặc thêm `DISTINCT` có thể thay đổi kết quả và thêm chi phí sort/hash.
- **UNION và UNION ALL:** `UNION` loại trùng, còn `UNION ALL` giữ trùng.
- **NULL:** `NOT IN`, `NOT EXISTS`, phép so sánh và điều kiện OR có thể khác nhau khi có NULL.
- **Join multiplicity:** pre-aggregate trước join chỉ đúng khi phép tính và quan hệ giữa bảng được bảo toàn.
- **Top-N:** giới hạn dòng trước khi sắp xếp không tương đương với lấy N dòng đầu sau khi sắp xếp.
- **Data type/time zone:** rewrite khoảng ngày phải giữ đúng kiểu và quy tắc thời gian.

Hãy kiểm tra kết quả bằng dữ liệu có các trường hợp biên: không có dòng khớp, nhiều dòng khớp, NULL, giá trị trùng, thời điểm ở ranh giới và các quan hệ một-nhiều.

## 14. Những cách làm thường gây lãng phí

| Cách làm | Chi phí có thể phát sinh | Cách xem xét |
|---|---|---|
| `SELECT *` | Row width lớn, network và workarea tăng | Chỉ chọn cột cần dùng |
| Lọc bằng hàm trên cột | Index/partition pruning khó tận dụng | Viết predicate theo khoảng hoặc cân nhắc function-based index |
| Join bảng chi tiết rồi `DISTINCT` | Tạo nhiều dòng trung gian rồi loại trùng | Dùng `EXISTS` nếu chỉ cần kiểm tra tồn tại |
| Aggregate sau khi join nhiều-nhiều | Dữ liệu bị nhân bản, aggregate lớn | Xác định multiplicity và pre-aggregate khi tương đương |
| OFFSET rất lớn | Phải đi qua nhiều dòng bị bỏ qua | Cân nhắc keyset pagination |
| Sort toàn bộ rồi mới giới hạn | Sort lớn và có thể dùng TEMP | Dùng top-N đúng ngữ nghĩa và access path hỗ trợ order |
| Lấy LOB trong danh sách cột không cần | Tăng I/O, memory và network | Tách truy vấn metadata và nội dung lớn |
| Chuyển toàn bộ dữ liệu qua DB link | Network traffic lớn | Kiểm tra predicate/projection pushdown |
| Dùng CTE với giả định nó luôn materialize | Có thể hiểu sai chi phí trung gian | Đọc query transformation và plan thực tế |
| Ép hint trước khi hiểu cardinality | Có thể che nguyên nhân và làm plan kém ổn định | Đo estimates/actuals và kiểm tra statistics trước |

## 15. Quy trình tối ưu theo thứ tự

Khi một truy vấn xử lý quá nhiều dữ liệu, có thể điều tra theo trình tự:

1. **Xác định kết quả cần thiết:** liệt kê chính xác các cột, dòng và thứ tự mà ứng dụng cần.
2. **Đánh dấu predicate:** xác định điều kiện nào lọc dòng và điều kiện nào là điều kiện join.
3. **Lọc gần nguồn:** bảo đảm điều kiện có thể được áp dụng tại table/index/partition access khi ngữ nghĩa cho phép.
4. **Giảm row width:** loại cột không cần khỏi SELECT, subquery và các nhánh trung gian.
5. **Kiểm tra join multiplicity:** xác định quan hệ một-một, một-nhiều hay nhiều-nhiều; dùng EXISTS nếu chỉ cần sự tồn tại.
6. **Đánh giá aggregation:** lọc trước group by và cân nhắc pre-aggregation nếu bảo toàn kết quả.
7. **Đánh giá sort/top-N:** dùng row limiting đúng thứ tự và xem xét keyset pagination cho trang sâu.
8. **Kiểm tra partition/network:** xác nhận pruning và pushdown trước các bước trao đổi dữ liệu.
9. **Đo execution plan:** so sánh E-Rows, A-Rows, Starts, Buffers, A-Time và TEMP.
10. **Kiểm chứng kết quả:** so sánh output của truy vấn cũ và mới trên dữ liệu đại diện, bao gồm NULL và trường hợp biên.

## 16. Checklist khi xem một truy vấn tốn chi phí

| Nội dung | Câu hỏi cần trả lời |
|---|---|
| Kết quả | Có đang lấy nhiều dòng hơn ứng dụng thực sự cần không? |
| Projection | Có cột nào không được sử dụng nhưng vẫn được SELECT hoặc truyền qua nhánh không? |
| Predicate | Điều kiện lọc có được áp dụng gần nguồn dữ liệu không? |
| Sargability | Có hàm hoặc implicit conversion trên cột làm giảm khả năng dùng index không? |
| Partition | Predicate có cho phép partition pruning không? |
| Join | Có tạo nhiều dòng trung gian do join multiplicity không? |
| Existence | Có thể dùng EXISTS/NOT EXISTS thay cho join rồi loại trùng không? |
| Aggregation | Có thể lọc trước hoặc pre-aggregate an toàn không? |
| Sort | Có đang sort tập dữ liệu rộng hoặc lớn hơn cần thiết không? |
| Top-N | Có giới hạn dòng sau đúng thứ tự và có thể dừng sớm không? |
| Analytic | Predicate có được đặt đúng trước/sau analytic function theo semantics không? |
| Network | Có đang gửi quá nhiều dòng hoặc cột qua PX/database link không? |
| Runtime | Actual rows, starts, buffers và thời gian xác nhận nút thắt ở đâu? |
| Correctness | Rewrite có giữ nguyên NULL, duplicate, outer join và thứ tự kết quả không? |

Giảm số dòng và số cột trước các thao tác tốn chi phí giúp giảm lượng dữ liệu mà Oracle phải đọc, kết hợp, sắp xếp, tổng hợp và truyền đi. Cách làm hiệu quả nhất bắt đầu từ việc hiểu kết quả cần trả, đặt predicate đúng vị trí, giữ projection gọn và kiểm tra plan thực tế. Mỗi rewrite phải được xác nhận cả về kết quả lẫn runtime statistics để bảo đảm truy vấn nhanh hơn mà vẫn trả đúng dữ liệu.
