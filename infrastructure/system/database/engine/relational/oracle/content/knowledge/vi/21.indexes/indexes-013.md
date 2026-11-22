# Chỉ mục phủ truy vấn, đánh đổi tốc độ đọc/ghi và tránh tạo dư thừa trong Oracle

## 1. Vì sao cần chỉ mục phủ truy vấn?

Một chỉ mục (index) giúp Oracle tìm hàng phù hợp mà không phải quét toàn bộ bảng trong nhiều trường hợp. Tuy nhiên, một truy vấn có thể tìm được ROWID qua index rồi vẫn phải đọc thêm block của bảng để lấy các cột cần hiển thị. Nếu workload lặp lại truy vấn đó với lượng dữ liệu lớn, các lần truy cập bảng theo ROWID có thể tạo thêm I/O và logical reads.

**Chỉ mục phủ truy vấn (covering index)** là cách gọi một index chứa đủ các cột mà một truy vấn cần để lọc, nối, sắp xếp và trả kết quả. Khi điều kiện và cost cho phép, Oracle có thể dùng index để trả lời truy vấn mà không cần truy cập table block cho từng ROWID. Trong execution plan, đây thường được gọi là *index-only access*.

Ví dụ, ứng dụng thường chạy:

```sql
SELECT order_id,
       order_date,
       total_amount
FROM orders
WHERE customer_id = :customer_id
  AND status = 'PAID'
  AND order_date >= :from_date
  AND order_date <  :to_date
ORDER BY order_date, order_id;
```

Một index chỉ gồm `(customer_id, status, order_date)` có thể giúp tìm nhanh các đơn hàng, nhưng `ORDER_ID` và `TOTAL_AMOUNT` chưa nằm trong index. Oracle có thể phải truy cập bảng để lấy hai cột đó. Một index rộng hơn:

```sql
CREATE INDEX ix_orders_customer_paid_cover
ON orders (
    customer_id,
    status,
    order_date,
    order_id,
    total_amount
);
```

chứa đủ cột của truy vấn trên. Nếu optimizer chọn index phù hợp và các điều kiện khác cho phép, truy vấn có thể được thực hiện bằng index range scan mà không cần `TABLE ACCESS BY INDEX ROWID`.

Chỉ mục phủ giúp giảm chi phí đọc trong một số workload, nhưng làm index lớn hơn và tăng chi phí INSERT, UPDATE, DELETE. Vì vậy, mục tiêu là chọn index có ích cho các truy vấn quan trọng mà không tạo một bản sao rộng của bảng trong mỗi index.

Bài học thuộc chương **Chỉ mục**, trình bày index-only access trong Oracle, cách thiết kế composite B-tree index theo predicate và projection, ảnh hưởng của thứ tự cột, xử lý NULL, đánh đổi giữa tốc độ đọc và ghi, nhận diện index trùng hoặc dư thừa, đọc execution plan và quy trình đánh giá trước khi thêm hay xóa index.

## 2. Index thông thường và index phủ khác nhau thế nào?

### 2.1. Index thông thường giúp tìm ROWID

Một B-tree index thông thường lưu giá trị khóa và thông tin ROWID để Oracle xác định hàng trong bảng. Ví dụ:

```sql
CREATE INDEX ix_orders_customer
ON orders (customer_id);
```

Truy vấn:

```sql
SELECT order_id, order_date, total_amount
FROM orders
WHERE customer_id = :customer_id;
```

Index `IX_ORDERS_CUSTOMER` có thể giúp Oracle tìm các ROWID có `CUSTOMER_ID` tương ứng. Nhưng index không chứa `ORDER_ID`, `ORDER_DATE` và `TOTAL_AMOUNT`, nên Oracle cần truy cập bảng để lấy các giá trị đó.

Execution plan có thể có dạng:

```text
SELECT STATEMENT
  TABLE ACCESS BY INDEX ROWID  ORDERS
    INDEX RANGE SCAN           IX_ORDERS_CUSTOMER
```

`INDEX RANGE SCAN` tìm các entry phù hợp; `TABLE ACCESS BY INDEX ROWID` đọc các hàng trong bảng dựa trên ROWID tìm được.

### 2.2. Index phủ chứa các cột truy vấn cần

Nếu index có tất cả cột mà truy vấn cần, Oracle có thể trả các giá trị trực tiếp từ index:

```sql
CREATE INDEX ix_orders_customer_cover
ON orders (
    customer_id,
    order_id,
    order_date,
    total_amount
);
```

Truy vấn:

```sql
SELECT order_id,
       order_date,
       total_amount
FROM orders
WHERE customer_id = :customer_id;
```

Các cột lọc và hiển thị đều nằm trong index. Optimizer có thể chọn đường truy cập chỉ qua index, tùy thống kê, độ chọn lọc và chi phí ước lượng.

Execution plan có thể chỉ còn:

```text
SELECT STATEMENT
  INDEX RANGE SCAN  IX_ORDERS_CUSTOMER_COVER
```

Đây là dạng index-only access thường được nhắc đến khi nói về covering index trong Oracle.

### 2.3. ROWID không thay thế giá trị của cột

Index entry có ROWID để định vị hàng, nhưng điều đó không có nghĩa Oracle có thể trả mọi cột của hàng chỉ từ ROWID. Nếu SELECT cần `TOTAL_AMOUNT` mà index không lưu `TOTAL_AMOUNT`, Oracle vẫn phải đọc table block.

Tương tự, nếu truy vấn chọn khóa chính `ORDER_ID`, đừng giả định index trên `CUSTOMER_ID` tự động chứa giá trị khóa chính. Index B-tree lưu các key columns đã khai báo và ROWID; muốn trả một cột nghiệp vụ từ index, hãy bảo đảm cột đó nằm trong key của index.

## 3. Xác định một truy vấn có thể được index phủ hay không

Để đánh giá, cần xét toàn bộ các cột mà query block sử dụng:

1. **SELECT list:** cột trả về cho ứng dụng.
2. **WHERE:** cột dùng lọc hàng.
3. **JOIN:** cột dùng ghép bảng.
4. **ORDER BY:** cột dùng sắp xếp.
5. **GROUP BY:** cột dùng nhóm.
6. **HAVING và biểu thức:** cột tham gia phép tính sau nhóm hoặc điều kiện.

Ví dụ:

```sql
SELECT order_id,
       order_date,
       total_amount
FROM orders
WHERE customer_id = :customer_id
  AND status = 'PAID'
  AND order_date >= :from_date
  AND order_date < :to_date
ORDER BY order_date, order_id;
```

Các cột cần xét là:

| Vai trò | Cột |
|---|---|
| SELECT | `ORDER_ID`, `ORDER_DATE`, `TOTAL_AMOUNT` |
| WHERE | `CUSTOMER_ID`, `STATUS`, `ORDER_DATE` |
| ORDER BY | `ORDER_DATE`, `ORDER_ID` |

Một index chứa tất cả các cột này có khả năng phủ truy vấn:

```sql
CREATE INDEX ix_orders_customer_status_date
ON orders (
    customer_id,
    status,
    order_date,
    order_id,
    total_amount
);
```

Đây chỉ là một ứng viên. Index có thể không được chọn nếu truy vấn trả về phần lớn bảng, nếu full table scan rẻ hơn, nếu thống kê không phù hợp hoặc nếu các đặc điểm dữ liệu khiến index không hiệu quả.

### 3.1. SELECT * thường làm mất lợi ích covering

```sql
SELECT *
FROM orders
WHERE customer_id = :customer_id;
```

Nếu bảng có nhiều cột, một index chỉ chứa một số cột không thể cung cấp toàn bộ kết quả. Cố thêm mọi cột của bảng vào index chỉ để phủ `SELECT *` thường tạo một index rất rộng, tốn dung lượng và làm mọi thao tác ghi đắt hơn.

Với truy vấn nghiệp vụ, nên chọn rõ các cột cần dùng thay vì `SELECT *`, đặc biệt trong API và báo cáo chạy thường xuyên.

### 3.2. Cột dùng trong biểu thức cũng phải được xem xét

Ví dụ:

```sql
SELECT UPPER(email)
FROM customers
WHERE UPPER(email) = UPPER(:email);
```

Index thông thường trên `EMAIL` không nhất thiết hỗ trợ hiệu quả biểu thức `UPPER(EMAIL)`. Có thể dùng function-based index:

```sql
CREATE INDEX ix_customers_email_upper
ON customers (UPPER(email));
```

Biểu thức truy vấn cần tương thích với biểu thức index. Nếu SELECT chỉ cần `UPPER(EMAIL)` và predicate dùng cùng biểu thức, index này có thể phục vụ index access phù hợp.

### 3.3. Cột JOIN cũng là một phần của nhu cầu truy cập

```sql
SELECT o.order_id,
       o.order_date,
       c.customer_name
FROM orders o
JOIN customers c
  ON c.customer_id = o.customer_id
WHERE o.status = 'PAID';
```

Index phủ trên `ORDERS` không thể cung cấp `CUSTOMER_NAME` vì cột đó thuộc bảng `CUSTOMERS`. Oracle vẫn phải truy cập bảng khách hàng hoặc một index khác có thể phục vụ phần truy vấn tương ứng. Đánh giá covering theo từng bảng và từng query block, không coi một index của bảng này phủ được dữ liệu của bảng khác.

## 4. Thiết kế composite index cho truy vấn phủ

Một composite index (index ghép) chứa nhiều cột theo một thứ tự xác định:

```sql
CREATE INDEX ix_orders_a_b_c
ON orders (a, b, c);
```

Thứ tự các cột là một phần quan trọng của thiết kế. Index `(A, B, C)` không giống index `(B, A, C)`, dù chúng chứa cùng tập cột.

### 4.1. Leading column và khả năng dùng index

Với index:

```sql
CREATE INDEX ix_orders_customer_status_date
ON orders (customer_id, status, order_date);
```

Oracle có thể sử dụng tiền tố index để tìm theo:

- `CUSTOMER_ID`.
- `CUSTOMER_ID` và `STATUS`.
- `CUSTOMER_ID`, `STATUS` và điều kiện trên `ORDER_DATE`.

Truy vấn chỉ lọc `STATUS` mà không có điều kiện trên `CUSTOMER_ID` thường không tận dụng được range scan theo tiền tố một cách trực tiếp như truy vấn có leading column. Oracle có thể cân nhắc index skip scan trong một số phân bố dữ liệu, nhưng không nên thiết kế dựa trên giả định skip scan luôn xảy ra.

### 4.2. Equality predicates và range predicate

Một quy tắc khởi đầu thường hữu ích là đặt các cột được so sánh bằng trước, rồi đến cột range:

```sql
WHERE customer_id = :customer_id
  AND status = 'PAID'
  AND order_date >= :from_date
  AND order_date < :to_date
```

Index ứng viên:

```sql
CREATE INDEX ix_orders_cust_status_date
ON orders (customer_id, status, order_date);
```

`CUSTOMER_ID` và `STATUS` là equality predicates; `ORDER_DATE` là range predicate. Index có thể thu hẹp vùng cần quét theo hai giá trị bằng rồi đi qua khoảng ngày.

Đây là quy tắc thực hành, không phải công thức tuyệt đối. Nếu workload có truy vấn khác, độ chọn lọc khác hoặc yêu cầu sort khác, thứ tự có thể thay đổi. Khi nhiều cột đều là equality predicates, hãy chọn thứ tự dựa trên các access paths thường dùng và nhu cầu tiền tố của những query khác.

### 4.3. Thêm cột projection phía sau để phủ truy vấn

Sau khi chọn phần key phục vụ tìm kiếm, có thể thêm các cột chỉ cần để trả kết quả:

```sql
CREATE INDEX ix_orders_cust_status_date_cov
ON orders (
    customer_id,
    status,
    order_date,
    order_id,
    total_amount
);
```

Trong Oracle B-tree index thông thường, các cột được thêm vào đều là key columns của index. Oracle không có cú pháp `INCLUDE` cho cột payload theo kiểu một số DBMS khác. Vì vậy, thêm cột chỉ để covering vẫn làm entry rộng hơn, ảnh hưởng dung lượng, fan-out và chi phí bảo trì.

### 4.4. Cột sắp xếp và khả năng tránh SORT

Nếu query có:

```sql
ORDER BY order_date, order_id
```

thì index có thứ tự:

```sql
(customer_id, status, order_date, order_id, total_amount)
```

có thể cung cấp thứ tự phù hợp khi `CUSTOMER_ID` và `STATUS` đã được cố định bằng equality predicates. Oracle có thể tránh một bước sort riêng nếu đường truy cập và chiều sắp xếp tương thích.

Nếu thêm `TOTAL_AMOUNT` trước `ORDER_ID`, thứ tự index sẽ là `(ORDER_DATE, TOTAL_AMOUNT, ORDER_ID)` trong phần sau prefix. Điều đó không còn trực tiếp cung cấp thứ tự `ORDER_DATE, ORDER_ID` cho các hàng có cùng ngày. Vì vậy, khi cần vừa covering vừa tránh sort, hãy đặt các cột sort theo đúng thứ tự trước những cột chỉ phục vụ projection.

### 4.5. ASC, DESC và NULL ordering

Oracle hỗ trợ khai báo hướng sắp xếp cho cột index:

```sql
CREATE INDEX ix_orders_recent
ON orders (customer_id, order_date DESC, order_id);
```

Index có hướng DESC có thể hữu ích với truy vấn cần ngày mới nhất. Tuy nhiên, B-tree có thể được quét theo hướng ngược trong nhiều trường hợp; không tạo index DESC riêng chỉ vì thấy `ORDER BY ... DESC`. Hãy kiểm tra plan và thứ tự thực tế, bao gồm cách xử lý NULL.

## 5. Ví dụ thiết kế index phủ từ đầu đến cuối

Giả sử bảng:

```sql
CREATE TABLE orders (
    order_id NUMBER PRIMARY KEY,
    customer_id NUMBER NOT NULL,
    status VARCHAR2(20) NOT NULL,
    order_date TIMESTAMP NOT NULL,
    total_amount NUMBER(14, 2) NOT NULL,
    sales_channel VARCHAR2(20),
    note VARCHAR2(1000)
);
```

Ứng dụng thường lấy các đơn hàng đã thanh toán của một khách hàng trong một khoảng thời gian:

```sql
SELECT order_id,
       order_date,
       total_amount
FROM orders
WHERE customer_id = :customer_id
  AND status = 'PAID'
  AND order_date >= :from_date
  AND order_date < :to_date
ORDER BY order_date, order_id;
```

### 5.1. Bắt đầu bằng index tìm kiếm

```sql
CREATE INDEX ix_orders_customer_status_date
ON orders (customer_id, status, order_date);
```

Index này hỗ trợ tìm vùng dữ liệu theo customer, status và khoảng ngày. Nhưng truy vấn còn cần `ORDER_ID` và `TOTAL_AMOUNT`, vì vậy plan có thể cần table lookup.

### 5.2. Xem plan của truy vấn

Trong session thử nghiệm, bật runtime statistics:

```sql
ALTER SESSION SET statistics_level = ALL;
```

Chạy truy vấn:

```sql
SELECT order_id,
       order_date,
       total_amount
FROM orders
WHERE customer_id = :customer_id
  AND status = 'PAID'
  AND order_date >= :from_date
  AND order_date < :to_date
ORDER BY order_date, order_id;
```

Sau khi chạy truy vấn trong cùng session:

```sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE'
    )
);
```

Nếu plan có `TABLE ACCESS BY INDEX ROWID` trên `ORDERS`, Oracle đang đọc bảng sau bước index access. Hãy xem số hàng thực tế, buffer gets, số lần thực hiện và predicate information trước khi kết luận table lookup là nút thắt.

### 5.3. Tạo ứng viên covering index

```sql
CREATE INDEX ix_orders_customer_status_date_cov
ON orders (
    customer_id,
    status,
    order_date,
    order_id,
    total_amount
);
```

Index mới chứa tất cả cột cần cho query. Optimizer có thể chọn:

```text
SELECT STATEMENT
  INDEX RANGE SCAN  IX_ORDERS_CUSTOMER_STATUS_DATE_COV
```

Plan cụ thể phụ thuộc thống kê, bind values, phiên bản và dữ liệu. Nếu optimizer tiếp tục chọn index cũ hoặc full table scan, không có nghĩa index mới sai; hãy kiểm tra cost và lý do access path được chọn.

### 5.4. Không giữ cả hai index nếu không có workload chứng minh

Sau khi tạo index phủ, index cũ `(CUSTOMER_ID, STATUS, ORDER_DATE)` có thể trở thành tiền tố của index mới. Nhưng không được xóa ngay. Index cũ có thể:

- Nhỏ và rẻ hơn cho truy vấn chỉ cần ba cột key.
- Được constraint hoặc workload khác sử dụng.
- Có thuộc tính uniqueness, partitioning hoặc compression khác.
- Hỗ trợ access path mà index rộng không phục vụ tương đương về chi phí.

Hãy đo workload và kiểm tra dependency trước khi quyết định giữ hay bỏ.

## 6. Index-only access không phải lúc nào cũng được chọn

Một index có đủ cột là điều kiện để có thể cover, không phải mệnh lệnh bắt Oracle phải dùng index.

Optimizer ước lượng chi phí dựa trên:

- Số hàng dự kiến trả về.
- Selectivity và cardinality của predicate.
- Số block index phải đọc.
- Số table blocks phải đọc nếu có table lookup.
- Clustering factor.
- Thống kê bảng/index và histogram.
- Bind values, optimizer settings và phiên bản.

Nếu truy vấn trả về phần lớn bảng, full table scan có thể rẻ hơn việc quét index. Index phủ rộng cũng có thể lớn hơn nhiều so với index hẹp, khiến số leaf blocks phải đọc tăng.

### 6.1. Truy vấn chọn quá nhiều hàng

```sql
SELECT order_id, order_date, total_amount
FROM orders
WHERE status = 'PAID';
```

Nếu phần lớn hàng trong bảng có trạng thái PAID, optimizer có thể chọn full table scan. Việc index chứa đủ cột không làm index scan luôn rẻ hơn.

### 6.2. Clustering factor

Clustering factor phản ánh mức độ tương quan giữa thứ tự key trong index và vị trí hàng trong table blocks. Với index không phủ, clustering factor cao có thể khiến các ROWID dẫn đến nhiều table block rải rác, làm table lookup đắt hơn. Index phủ có thể tránh phần table lookup đó, nhưng chính index rộng lại cần thêm block để đọc.

### 6.3. Index scan không đồng nghĩa ít I/O trong mọi tình huống

Một `INDEX FAST FULL SCAN` có thể đọc nhiều block của index bằng multiblock I/O và không giữ thứ tự key. Một `INDEX FULL SCAN` có thể đọc theo thứ tự index. `INDEX RANGE SCAN` chỉ đọc một vùng phù hợp. Cần phân biệt các operation này thay vì chỉ nhìn thấy chữ INDEX trong plan rồi kết luận truy vấn nhanh.

## 7. NULL và giới hạn của B-tree index

Oracle B-tree index thông thường không lưu entry cho hàng mà **tất cả các cột key của index đều NULL**. Đây là điểm quan trọng khi đánh giá index-only access.

### 7.1. Index một cột nullable

```sql
CREATE INDEX ix_customers_middle_name
ON customers (middle_name);
```

Nếu `MIDDLE_NAME` là NULL, hàng đó không có entry trong B-tree index một cột này. Vì vậy, index thông thường không thể cung cấp toàn bộ hàng có `MIDDLE_NAME IS NULL` chỉ bằng cách quét các entry của nó.

### 7.2. Composite index và NULL

Với:

```sql
CREATE INDEX ix_customers_status_email
ON customers (status, email);
```

Nếu `STATUS` khác NULL nhưng `EMAIL` NULL, entry vẫn có thể tồn tại vì không phải tất cả key columns đều NULL. Nếu cả `STATUS` và `EMAIL` đều NULL, hàng không có entry trong B-tree index thông thường.

### 7.3. Khi query cần cả hàng có NULL

Nếu một truy vấn cần trả cả hàng mà mọi cột trong index đều NULL, index đó không thể đại diện cho những hàng không có entry. Có thể cần thiết kế key bao gồm một cột NOT NULL phù hợp hoặc dùng access path khác.

Không thêm một cột chỉ để xử lý NULL mà chưa đánh giá ý nghĩa và chi phí. Cách phù hợp phụ thuộc predicate và tính đầy đủ của dữ liệu.

## 8. Chọn cột phủ: lợi ích và chi phí

### 8.1. Lợi ích phía đọc

Một covering index tốt có thể:

- Tránh `TABLE ACCESS BY INDEX ROWID` cho truy vấn phù hợp.
- Giảm số lần đọc table blocks.
- Giảm logical reads và có thể giảm physical I/O.
- Trả kết quả từ một cấu trúc nhỏ hơn bảng.
- Hỗ trợ predicate và ORDER BY trong cùng access path.
- Cải thiện độ trễ của truy vấn lặp lại, có chọn lọc cao.

Lợi ích lớn nhất thường xuất hiện với query chạy thường xuyên, chỉ đọc một số cột, lọc được tập hàng tương đối nhỏ và table lookup đang là phần chi phí đáng kể.

### 8.2. Chi phí phía ghi

Mỗi index là một cấu trúc cần được duy trì:

| DML | Chi phí liên quan index |
|---|---|
| INSERT | Thêm entry vào mỗi index liên quan |
| DELETE | Xóa entry tương ứng khỏi mỗi index |
| UPDATE cột key | Thay đổi entry index cũ và tạo entry mới |
| UPDATE cột không nằm trong index | Thường không cần thay entry của index đó |
| UPDATE cột được thêm chỉ để covering | Vẫn phải duy trì index khi giá trị cột thay đổi |

Thêm `TOTAL_AMOUNT` vào index có thể giúp query đọc nhanh hơn, nhưng mỗi lần sửa `TOTAL_AMOUNT` sẽ phát sinh công việc bảo trì index.

### 8.3. Chi phí dung lượng và cache

Cột càng rộng thì index entry càng lớn. Index rộng có thể:

- Dùng nhiều tablespace hơn.
- Có ít entry hơn trên mỗi leaf block.
- Tăng số leaf blocks phải đọc.
- Tăng khả năng index tree có thêm mức khi dữ liệu lớn.
- Chiếm buffer cache, cạnh tranh với dữ liệu và index khác.
- Tăng chi phí backup, recovery và bảo trì.

Đặc biệt tránh đưa CLOB, BLOB hoặc cột VARCHAR2 rất dài vào B-tree index chỉ để phủ truy vấn. Hãy cân nhắc một mô hình truy vấn khác hoặc chỉ lập index trên khóa/biểu thức cần thiết.

### 8.4. Read-heavy và write-heavy

| Workload | Hướng cân nhắc |
|---|---|
| Báo cáo đọc lặp lại, ít thay đổi dữ liệu | Covering index có thể đem lại lợi ích đáng kể |
| OLTP ghi nhiều, cập nhật liên tục | Giữ index hẹp, chỉ thêm cột phủ khi có số đo chứng minh |
| Bảng append-only, query theo khoảng thời gian | Composite index theo partition/filter có thể phù hợp |
| Bảng có nhiều cột mutable | Cân nhắc chi phí cập nhật các cột được thêm vào index |
| Query trả phần lớn bảng | Full table scan có thể tốt hơn covering index |

## 9. Không nhầm covering index với index-only scan được bảo đảm

“Covering” mô tả khả năng index chứa đủ thông tin cho query. “Index-only access” mô tả đường truy cập optimizer thực sự chọn trong plan. Hai khái niệm liên quan nhưng không đồng nhất:

- Index có đủ cột nhưng optimizer chọn full table scan.
- Index có đủ cột nhưng predicate/biểu thức không tương thích với key.
- Dữ liệu NULL hoặc các đặc điểm visibility có thể ảnh hưởng cách Oracle thực thi.
- Truy vấn cần thêm cột từ bảng khác.
- Thống kê hoặc bind selectivity khiến optimizer chọn access path khác.

Vì vậy, hãy xác nhận plan thực tế và runtime statistics. Không đánh giá chỉ bằng việc đếm tên cột trong `CREATE INDEX`.

## 10. Tránh tạo index dư thừa

Index dư thừa làm tăng chi phí ghi, dung lượng và độ phức tạp của optimizer. Trước khi thêm index mới, hãy so sánh với những index đang có.

### 10.1. Index trùng hoàn toàn

Ví dụ:

```sql
CREATE INDEX ix_orders_customer_a
ON orders (customer_id, status);

CREATE INDEX ix_orders_customer_b
ON orders (customer_id, status);
```

Hai index có cùng table, cùng danh sách cột và cùng thuộc tính chính thường là dư thừa. Mỗi INSERT/DELETE hoặc UPDATE key phải bảo trì cả hai.

Trước khi xóa, cần xác nhận index thứ hai không mang thuộc tính khác như UNIQUE, partitioning, compression, visibility hoặc mục đích constraint.

### 10.2. Index tiền tố

Giả sử:

```sql
CREATE INDEX ix_orders_customer
ON orders (customer_id);

CREATE INDEX ix_orders_customer_status_date
ON orders (customer_id, status, order_date);
```

Index thứ hai có leading prefix là `CUSTOMER_ID`, nên có thể phục vụ nhiều truy vấn chỉ lọc theo customer. Index đơn cột đầu tiên có thể dư thừa nếu không có nhu cầu đặc biệt.

Nhưng không thể kết luận tự động. Index hẹp có thể:

- Nhỏ hơn và rẻ hơn cho workload chỉ cần customer ID.
- Được dùng bởi constraint hoặc truy vấn đặc biệt.
- Có thuộc tính UNIQUE hoặc local/global khác.
- Có hướng sort, compression hoặc partitioning khác.

Hãy so sánh số lần sử dụng, buffer gets, chi phí ghi và plan của các truy vấn quan trọng.

### 10.3. Index không có cùng leading column không thay thế nhau

```sql
CREATE INDEX ix_orders_customer_status
ON orders (customer_id, status);
```

Index này không tương đương index `(STATUS, CUSTOMER_ID)`. Truy vấn lọc chỉ theo STATUS có thể không sử dụng index đầu hiệu quả như một index có STATUS ở leading position. Oracle có thể dùng skip scan trong một số trường hợp, nhưng không phải thay thế tổng quát.

### 10.4. Index đơn cột và composite index

Nếu có:

```sql
CREATE INDEX ix_orders_customer ON orders(customer_id);
CREATE INDEX ix_orders_status ON orders(status);
CREATE INDEX ix_orders_date ON orders(order_date);
```

và workload chủ yếu lọc đồng thời customer, status, date, một composite index có thể hiệu quả hơn việc kết hợp nhiều index đơn cột:

```sql
CREATE INDEX ix_orders_customer_status_date
ON orders(customer_id, status, order_date);
```

Tuy nhiên, composite index không thay thế tự động mọi index đơn cột. Nếu workload có truy vấn chỉ lọc STATUS hoặc DATE, cần đo xem index ghép có phục vụ đủ tốt hay cần một index riêng.

### 10.5. Index phục vụ constraint

Index có thể được dùng để hỗ trợ PRIMARY KEY, UNIQUE và các truy vấn khóa ngoại. Oracle có thể tạo unique index khi cần thực thi constraint nếu chưa có index phù hợp, hoặc dùng index đã tồn tại theo cấu hình. Không xóa một index chỉ vì thấy nó trùng cột với index khác mà chưa kiểm tra constraint phụ thuộc.

Với foreign key, index trên cột con thường hữu ích cho JOIN và giúp giảm nguy cơ khóa/chặn mở rộng khi cập nhật hoặc xóa hàng cha trong một số tình huống. Nếu composite index hiện có bắt đầu bằng các cột foreign key theo thứ tự phù hợp, có thể đã đáp ứng nhu cầu này.

## 11. Thứ tự cột và khả năng tái sử dụng index

### 11.1. Đặt cột truy vấn phổ biến ở leading position

Index:

```sql
(customer_id, status, order_date)
```

phục vụ tốt các truy vấn có `CUSTOMER_ID` làm tiền tố. Nếu hệ thống có truy vấn chủ yếu theo `STATUS` và khoảng ngày trên toàn bộ khách hàng, index này có thể không phải lựa chọn tối ưu.

Không có thứ tự cột đúng cho mọi truy vấn. Hãy gom các query pattern quan trọng trước khi thiết kế.

### 11.2. Selectivity không phải tiêu chí duy nhất

Cột có nhiều giá trị phân biệt thường có selectivity cao, nhưng không có nghĩa luôn phải đứng đầu index. Equality predicates có thể được kết hợp; leading position còn phụ thuộc:

- Truy vấn có dùng tiền tố nào.
- Có range predicate ở cột nào.
- Có cần tránh sort không.
- Phân bố dữ liệu và histogram.
- Khả năng tái sử dụng cho các query khác.

Ví dụ, `CUSTOMER_ID` có nhiều giá trị nhưng truy vấn thường dùng cả `CUSTOMER_ID` và `STATUS`; thứ tự hai cột equality có thể được quyết định bởi các truy vấn khác cần tiền tố nào.

### 11.3. Range predicate thường giới hạn việc dùng các cột phía sau

Với index `(A, B, C, D)` và query:

```sql
WHERE A = :a
  AND B >= :b
  AND C = :c
```

Oracle có thể dùng A và B để xác định range scan. Điều kiện C vẫn có thể được kiểm tra bằng index filter nếu C nằm trong index, nhưng nó không nhất thiết thu hẹp range như một equality predicate đứng trước range key.

Vì vậy, nếu query thường có nhiều equality predicates và một range predicate, thường đặt equality keys trước range key rồi mới đến cột phục vụ sort/projection. Hãy kiểm tra predicate information trong plan để hiểu cột nào là access predicate và cột nào là filter predicate.

## 12. Function-based index và covering

Nếu truy vấn dùng hàm trên cột, có thể tạo function-based index:

```sql
CREATE INDEX ix_customers_upper_email
ON customers (UPPER(email));
```

Truy vấn:

```sql
SELECT UPPER(email)
FROM customers
WHERE UPPER(email) = UPPER(:email);
```

Index có thể phục vụ truy cập theo biểu thức. Nếu SELECT cần thêm cột không có trong index, Oracle vẫn có thể phải truy cập bảng.

### 12.1. Tránh bọc cột ngày bằng TRUNC nếu có thể

Truy vấn:

```sql
SELECT order_id, order_date
FROM orders
WHERE TRUNC(order_date) = DATE '2026-11-14';
```

có thể khiến index thông thường trên `ORDER_DATE` không được sử dụng như một range scan trực tiếp. Thường nên viết:

```sql
SELECT order_id, order_date
FROM orders
WHERE order_date >= TIMESTAMP '2026-11-14 00:00:00'
  AND order_date <  TIMESTAMP '2026-11-15 00:00:00';
```

Nếu nghiệp vụ thực sự cần biểu thức `TRUNC(order_date)` và query pattern ổn định, có thể cân nhắc function-based index:

```sql
CREATE INDEX ix_orders_order_day
ON orders (TRUNC(order_date));
```

Function-based index cũng cần được duy trì khi giá trị nguồn thay đổi và có thể cần thống kê phù hợp.

## 13. Đọc execution plan để xác nhận covering

Không thể xác nhận một index phủ chỉ bằng câu lệnh DDL. Cần xem plan của truy vấn thực tế.

### 13.1. Các operation thường gặp

| Operation | Ý nghĩa khái quát |
|---|---|
| `INDEX RANGE SCAN` | Đọc một khoảng key phù hợp |
| `INDEX UNIQUE SCAN` | Tìm key duy nhất |
| `INDEX FULL SCAN` | Quét toàn index theo thứ tự index |
| `INDEX FAST FULL SCAN` | Quét toàn index theo kiểu multiblock; không bảo đảm thứ tự key |
| `TABLE ACCESS BY INDEX ROWID` | Dùng ROWID từ index để đọc hàng bảng |
| `TABLE ACCESS FULL` | Quét toàn bảng |
| `SORT ORDER BY` | Sắp xếp kết quả |
| `SORT GROUP BY` | Sắp xếp/nhóm dữ liệu cho GROUP BY |

Một truy vấn được index phủ có thể không cần `TABLE ACCESS BY INDEX ROWID` cho bảng đó. Nhưng vẫn có thể có table access trên bảng khác trong JOIN.

### 13.2. Thu thập runtime statistics

Trong session thử nghiệm:

```sql
ALTER SESSION SET statistics_level = ALL;
```

Chạy truy vấn thực tế rồi xem cursor plan:

```sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE'
    )
);
```

Xem:

- Operation nào được thực hiện.
- `E-Rows` so với `A-Rows`.
- `Buffers` và số lần thực hiện.
- Access predicates và filter predicates.
- Có `TABLE ACCESS BY INDEX ROWID` hay không.
- Có bước SORT mà index có thể tránh không.

### 13.3. So sánh trước và sau

Ghi lại ít nhất:

| Chỉ số | Trước | Sau |
|---|---:|---:|
| Elapsed time | Đo | Đo |
| Buffer gets | Đo | Đo |
| Physical reads | Đo | Đo |
| Rows returned | Đo | Đo |
| Table access by ROWID | Có/không | Có/không |
| Index size | Đo | Đo |
| DML throughput | Đo | Đo |

Đừng chỉ đo một lần khi cache còn lạnh hoặc chỉ đo query trong một bộ bind values. Cần thử nhiều selectivity và workload gần thực tế.

### 13.4. Không ép index bằng hint quá sớm

Hint `INDEX` có thể dùng trong thử nghiệm có kiểm soát, nhưng không nên dùng để che một thiết kế index hoặc thống kê chưa phù hợp. Khi dữ liệu thay đổi, access path bị ép có thể trở nên tệ hơn full table scan.

Hãy để optimizer lựa chọn sau khi đã có thống kê phù hợp; chỉ dùng hint khi có bằng chứng rõ ràng và có quy trình theo dõi.

## 14. Thống kê index và bảng

Optimizer dựa trên statistics để ước lượng cardinality và cost. Sau khi dữ liệu thay đổi đáng kể hoặc tạo index mới, cần xem xét thống kê:

```sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'ORDERS',
        cascade => TRUE
    );
END;
/
```

`CASCADE => TRUE` yêu cầu thu thập thống kê liên quan index theo cách Oracle hỗ trợ. Trong production, hãy theo quy trình quản lý statistics của hệ thống; không chạy gather thủ công hàng loạt vào giờ cao điểm nếu chưa đánh giá tác động.

Xem metadata index:

```sql
SELECT index_name,
       index_type,
       uniqueness,
       status,
       visibility,
       num_rows,
       leaf_blocks,
       distinct_keys,
       clustering_factor
FROM user_indexes
WHERE table_name = 'ORDERS'
ORDER BY index_name;
```

Xem cột và thứ tự trong index:

```sql
SELECT index_name,
       column_position,
       column_name,
       descend
FROM user_ind_columns
WHERE table_name = 'ORDERS'
ORDER BY index_name, column_position;
```

Các view `USER_*` hiển thị metadata trong schema hiện tại. Dùng `ALL_*` hoặc `DBA_*` khi cần xem schema khác và có quyền phù hợp.

## 15. Thử index mới mà giảm rủi ro ảnh hưởng optimizer

Oracle hỗ trợ invisible index để tạo index và thử nghiệm mà không cho optimizer sử dụng mặc định trong các session thông thường.

### 15.1. Tạo invisible index

```sql
CREATE INDEX ix_orders_test_cover
ON orders (
    customer_id,
    status,
    order_date,
    order_id,
    total_amount
)
INVISIBLE;
```

Index invisible vẫn được duy trì khi DML xảy ra; nó vẫn tiêu tốn dung lượng và chi phí ghi. Invisible chỉ ảnh hưởng khả năng optimizer xem xét index theo cấu hình session.

### 15.2. Bật sử dụng invisible index trong session thử nghiệm

```sql
ALTER SESSION SET optimizer_use_invisible_indexes = TRUE;
```

Sau đó chạy query và xem execution plan. Session khác không tự động sử dụng index chỉ vì một session đã bật tham số này.

### 15.3. Đưa index vào sử dụng hoặc xóa

Nếu thử nghiệm cho kết quả tốt và đã được phê duyệt:

```sql
ALTER INDEX ix_orders_test_cover VISIBLE;
```

Nếu không cần:

```sql
DROP INDEX ix_orders_test_cover;
```

Invisible index là công cụ thử access path, không phải cách miễn phí để tạo index. DML vẫn duy trì index, vì vậy cần tính cả chi phí ghi trong thời gian thử nghiệm.

## 16. Nhận diện index dư thừa trong schema

### 16.1. Liệt kê index và cột

```sql
SELECT i.index_name,
       i.index_type,
       i.uniqueness,
       i.status,
       c.column_position,
       c.column_name,
       c.descend
FROM user_indexes i
JOIN user_ind_columns c
  ON c.index_name = i.index_name
 AND c.table_name = i.table_name
WHERE i.table_name = 'ORDERS'
ORDER BY i.index_name, c.column_position;
```

Dùng kết quả để nhóm index có cùng danh sách cột và so sánh thứ tự, uniqueness, trạng thái, visibility và các thuộc tính khác.

### 16.2. Tìm các index có cùng danh sách cột theo thứ tự

Truy vấn dưới đây giúp phát hiện ứng viên trùng key columns:

```sql
SELECT table_name,
       column_list,
       COUNT(*) AS index_count,
       LISTAGG(index_name, ', ')
           WITHIN GROUP (ORDER BY index_name) AS index_names
FROM (
    SELECT table_name,
           index_name,
           LISTAGG(column_name, ', ')
               WITHIN GROUP (ORDER BY column_position) AS column_list
    FROM user_ind_columns
    GROUP BY table_name, index_name
)
GROUP BY table_name, column_list
HAVING COUNT(*) > 1
ORDER BY table_name, column_list;
```

Đây chỉ là bước phát hiện ứng viên. Truy vấn không so sánh hết expression, partitioning, compression, uniqueness, constraint dependency hoặc thuộc tính vật lý. Không tự động DROP mọi index xuất hiện trong kết quả.

### 16.3. Kiểm tra constraint phụ thuộc

```sql
SELECT constraint_name,
       constraint_type,
       index_name,
       status
FROM user_constraints
WHERE table_name = 'ORDERS'
  AND constraint_type IN ('P', 'U');
```

Nếu index hỗ trợ PRIMARY KEY hoặc UNIQUE constraint, cần xử lý constraint/index theo đúng quan hệ phụ thuộc. Không xóa index đang được constraint sử dụng chỉ vì thấy một index khác có cột tương tự.

### 16.4. Kiểm tra usage trước khi xóa

Oracle có các cơ chế theo dõi usage index trong một số phiên bản và công cụ quản trị. Việc theo dõi có phạm vi và giới hạn; một khoảng quan sát ngắn không chứng minh index không được dùng. Hãy đối chiếu SQL workload, AWR/ASH nếu có quyền và quy trình quản trị của tổ chức trước khi kết luận.

### 16.5. Vì sao không nên giữ index “phòng khi cần”?

Index không được dùng vẫn có chi phí:

- Mỗi lần INSERT/DELETE phải duy trì entry.
- UPDATE cột key phải sửa entry.
- Chiếm tablespace và buffer cache.
- Tăng công việc thống kê, backup và bảo trì.
- Làm schema khó hiểu, khó lựa chọn index đúng cho từng workload.

Giữ index khi có truy vấn, constraint hoặc yêu cầu vận hành cụ thể chứng minh giá trị của nó.

## 17. Index phủ và các loại index khác

### 17.1. B-tree index

B-tree là lựa chọn phổ biến cho OLTP và truy vấn equality/range. Covering index trong bài chủ yếu nói về composite B-tree index.

### 17.2. Bitmap index

Bitmap index có thể hữu ích trong một số workload data warehouse với các cột có cardinality thấp và ít DML đồng thời. Nhưng bitmap index thường không phù hợp với bảng OLTP có nhiều transaction cập nhật đồng thời vì đặc tính khóa và chi phí cập nhật bitmap.

Không chọn bitmap chỉ vì một cột có ít giá trị; phải xét loại workload và concurrency.

### 17.3. Function-based index

Index trên biểu thức như `UPPER(email)` hoặc `TRUNC(order_date)` phục vụ predicate dùng biểu thức tương ứng. Nếu query còn cần các cột khác, có thể phải thêm chúng vào index để đạt covering, nhưng hãy đánh giá độ rộng và chi phí.

### 17.4. Index-organized table không đồng nghĩa covering index

Index-organized table (IOT) lưu dữ liệu hàng trong cấu trúc B-tree theo primary key. Đây là lựa chọn tổ chức lưu trữ bảng, khác với việc thêm một secondary covering index trên heap table. Không chuyển một bảng sang IOT chỉ để tránh table lookup mà chưa phân tích toàn bộ access pattern, kích thước hàng và DML.

## 18. Quy trình thiết kế covering index

Một quy trình thực tế:

1. **Chọn query quan trọng:** dựa trên tần suất, độ trễ, buffer gets và tác động nghiệp vụ.
2. **Đọc SQL đầy đủ:** ghi nhận SELECT, WHERE, JOIN, ORDER BY, GROUP BY và biểu thức.
3. **Xác định access keys:** equality predicates, range predicates và cột JOIN.
4. **Chọn thứ tự key:** cân nhắc leading columns, range và thứ tự sort.
5. **Xác định cột phủ:** chỉ thêm cột projection cần thiết, tránh `SELECT *`.
6. **Đánh giá độ rộng:** kiểu dữ liệu, độ dài, số hàng và kích thước index.
7. **Kiểm tra index hiện có:** tìm index trùng, prefix và index hỗ trợ constraint.
8. **Tạo thử có kiểm soát:** có thể dùng invisible index trong session thử nghiệm.
9. **So sánh plan và runtime:** buffers, elapsed time, table lookup, sort, DML throughput.
10. **Quyết định giữ/bỏ:** chỉ giữ index khi lợi ích workload lớn hơn chi phí ghi và dung lượng.

### 18.1. Câu hỏi trước khi thêm cột vào index

- Query có chạy thường xuyên và quan trọng không?
- Table lookup hiện tại có thực sự tốn kém không?
- Cột được thêm có thay đổi thường xuyên không?
- Cột có kích thước lớn không?
- Query có trả quá nhiều hàng không?
- Một index hiện tại đã gần phủ query chưa?
- Có thể sửa query để dùng range predicate hoặc tránh SELECT * không?
- Index mới có trùng prefix với index khác không?

Nếu không trả lời được các câu hỏi này, chưa nên thêm cột vào index chỉ để “cho chắc”.

## 19. Bài thực hành tổng hợp

Các lệnh dưới đây tạo bảng riêng trong schema thực hành. Chỉ chạy khi có quyền tạo bảng và không dùng tên trùng với dữ liệu hiện có.

### Bước 1. Tạo bảng đơn hàng demo

```sql
CREATE TABLE demo_orders (
    order_id NUMBER PRIMARY KEY,
    customer_id NUMBER NOT NULL,
    status VARCHAR2(20) NOT NULL,
    order_date DATE NOT NULL,
    total_amount NUMBER(12, 2) NOT NULL,
    note VARCHAR2(500)
);
```

### Bước 2. Chèn dữ liệu minh họa

```sql
INSERT INTO demo_orders
SELECT LEVEL,
       MOD(LEVEL, 100) + 1,
       CASE WHEN MOD(LEVEL, 3) = 0 THEN 'PAID' ELSE 'NEW' END,
       DATE '2026-01-01' + MOD(LEVEL, 365),
       LEVEL * 100,
       'Demo order ' || LEVEL
FROM dual
CONNECT BY LEVEL <= 10000;

COMMIT;
```

### Bước 3. Chạy query trước khi tạo covering index

```sql
SELECT order_id,
       order_date,
       total_amount
FROM demo_orders
WHERE customer_id = 42
  AND status = 'PAID'
  AND order_date >= DATE '2026-06-01'
  AND order_date < DATE '2026-07-01'
ORDER BY order_date, order_id;
```

Xem plan bằng `DBMS_XPLAN.DISPLAY_CURSOR` sau khi chạy query.

### Bước 4. Tạo index tìm kiếm

```sql
CREATE INDEX ix_demo_orders_search
ON demo_orders (customer_id, status, order_date);
```

Chạy lại query và so sánh access path.

### Bước 5. Tạo index phủ để thử nghiệm

```sql
CREATE INDEX ix_demo_orders_cover
ON demo_orders (
    customer_id,
    status,
    order_date,
    order_id,
    total_amount
)
INVISIBLE;
```

### Bước 6. Bật invisible index trong session thử nghiệm

```sql
ALTER SESSION SET optimizer_use_invisible_indexes = TRUE;
```

Chạy lại query, xem plan và so sánh buffers. Sau thử nghiệm, có thể tắt tham số:

```sql
ALTER SESSION SET optimizer_use_invisible_indexes = FALSE;
```

### Bước 7. So sánh dung lượng và metadata

```sql
SELECT index_name,
       status,
       visibility,
       leaf_blocks,
       distinct_keys,
       clustering_factor
FROM user_indexes
WHERE table_name = 'DEMO_ORDERS'
ORDER BY index_name;

SELECT index_name,
       column_position,
       column_name
FROM user_ind_columns
WHERE table_name = 'DEMO_ORDERS'
ORDER BY index_name, column_position;
```

### Bước 8. Quan sát chi phí ghi

Thử INSERT một số hàng trong transaction demo trước và sau khi tạo index, đo elapsed time và redo/undo nếu môi trường lab cho phép. Không kết luận chỉ từ một lần chạy; cache, parse và workload có thể ảnh hưởng kết quả.

### Bước 9. Dọn index và bảng demo

Chỉ khi xác nhận đây là các đối tượng do bạn tạo và không cần giữ dữ liệu:

```sql
DROP INDEX ix_demo_orders_cover;
DROP INDEX ix_demo_orders_search;
DROP TABLE demo_orders PURGE;
```

`DROP TABLE ... PURGE` xóa bảng và dữ liệu, bỏ qua recycle bin theo hành vi lệnh; DDL có commit ngầm. Không chạy lệnh dọn trên bảng nghiệp vụ hoặc đối tượng dùng chung.

## 20. Những nhầm lẫn thường gặp

| Nhầm lẫn | Thực tế |
|---|---|
| Có index là truy vấn không cần đọc bảng | Chỉ khi index cung cấp đủ dữ liệu và optimizer chọn access path phù hợp |
| ROWID trong index có thể trả mọi cột | ROWID chỉ định vị hàng; cột chưa nằm trong index vẫn cần table access |
| Thêm mọi cột SELECT vào index luôn tốt | Index rộng làm tăng dung lượng và chi phí DML |
| Oracle có INCLUDE columns giống mọi DBMS | B-tree index thông thường lưu các key columns; không có cú pháp INCLUDE payload tương đương phổ biến |
| Index phủ luôn được chọn | Optimizer có thể chọn full table scan hoặc access path khác theo cost |
| Index (A,B,C) giống (B,A,C) | Leading column và thứ tự key khác nhau |
| Index ghép luôn thay thế index đơn | Chỉ khi workload, constraint và thuộc tính index cho phép |
| Có thể xóa index prefix ngay | Phải kiểm tra uniqueness, constraint, partitioning, usage và hiệu năng |
| B-tree index một cột lưu cả hàng có key NULL | Hàng có tất cả key columns NULL không có entry trong B-tree index thông thường |
| Index invisible không tốn chi phí ghi | Invisible index vẫn được duy trì bởi DML |
| ORDER BY luôn được index đáp ứng | Cần thứ tự key tương thích và equality prefix; optimizer vẫn có thể SORT |
| Chỉ cần xem EXPLAIN PLAN | Cần xem runtime statistics và workload thực tế |

## 21. Quy tắc ghi nhớ

| Mục tiêu | Nguyên tắc |
|---|---|
| Tìm kiếm theo điều kiện | Đặt các predicate keys phù hợp ở leading columns |
| Cover một query | Bao gồm cột lọc, join, sort và projection cần thiết |
| Tránh table lookup | Xác nhận plan không có `TABLE ACCESS BY INDEX ROWID` cho bảng đó |
| Tránh sort | Đặt sort keys theo thứ tự phù hợp sau equality prefix |
| Giảm index rộng | Chỉ thêm cột projection thực sự cần |
| Xử lý ngày | Ưu tiên range predicate nửa mở thay vì bọc cột bằng TRUNC |
| Truy vấn biểu thức | Cân nhắc function-based index |
| Tránh index dư thừa | So sánh exact duplicate, left-prefix và constraint dependency |
| Đánh giá read/write | Đo query runtime, buffers, DML throughput và index size |
| Thử index mới | Dùng invisible index khi phù hợp và kiểm tra plan trong session thử nghiệm |
| Không dựa vào giả định | Kiểm tra execution plan và thống kê runtime |

## 22. Câu hỏi tự kiểm tra

**Câu 1.** Covering index là gì?

**Trả lời:** Index chứa đủ các cột mà một truy vấn cần cho predicate, join, sort và kết quả, giúp Oracle có khả năng thực hiện index-only access.

**Câu 2.** Vì sao index `(customer_id)` vẫn cần table lookup khi SELECT `total_amount`?

**Trả lời:** `TOTAL_AMOUNT` không nằm trong index; ROWID chỉ định vị hàng chứ không chứa giá trị cột.

**Câu 3.** Trong composite index, vì sao thứ tự cột quan trọng?

**Trả lời:** B-tree được sắp theo thứ tự key; leading columns quyết định các tiền tố và range scan có thể sử dụng trực tiếp.

**Câu 4.** Vì sao thường đặt equality predicates trước range predicate?

**Trả lời:** Các giá trị bằng giúp thu hẹp prefix trước khi quét khoảng của cột range; đây là quy tắc khởi đầu cần xác nhận bằng workload và plan.

**Câu 5.** Oracle có INCLUDE columns như một số DBMS không?

**Trả lời:** B-tree index thông thường dùng danh sách key columns; cột thêm để cover vẫn là key và làm index rộng hơn.

**Câu 6.** Index phủ có luôn được optimizer chọn không?

**Trả lời:** Không. Cost, cardinality, selectivity, statistics và kích thước index có thể khiến full table scan hoặc access path khác rẻ hơn.

**Câu 7.** Vì sao thêm `TOTAL_AMOUNT` vào index làm UPDATE đắt hơn?

**Trả lời:** Khi giá trị key column đó thay đổi, Oracle phải duy trì entry index tương ứng.

**Câu 8.** Vì sao không nên tạo index covering cho SELECT *?

**Trả lời:** Có thể phải đưa hầu hết cột vào index, tạo cấu trúc rất rộng và tăng chi phí mọi thao tác ghi.

**Câu 9.** B-tree index một cột có entry cho hàng mà cột đó NULL không?

**Trả lời:** Không; hàng có tất cả key columns NULL không được lưu trong B-tree index thông thường.

**Câu 10.** Index `(A,B)` có thể phục vụ query chỉ lọc A không?

**Trả lời:** Thường có thể dùng leading prefix A. Query chỉ lọc B không có cùng lợi thế; skip scan có thể xuất hiện trong trường hợp phù hợp nhưng không nên dựa vào nó như quy tắc chung.

**Câu 11.** Làm sao nhận biết truy vấn đã tránh table lookup?

**Trả lời:** Xem execution plan thực tế; với bảng đó, không có operation `TABLE ACCESS BY INDEX ROWID`, và kiểm tra runtime statistics.

**Câu 12.** Invisible index có miễn phí cho DML không?

**Trả lời:** Không. DML vẫn phải duy trì invisible index.

**Câu 13.** Có thể xóa index đơn cột vì nó là prefix của index ghép không?

**Trả lời:** Chỉ sau khi kiểm tra workload, constraint, uniqueness, partitioning, compression và tác động runtime.

**Câu 14.** Chỉ mục phủ có thay thế được bảng con hoặc thiết kế dữ liệu tốt không?

**Trả lời:** Không. Index tối ưu access path; nó không thay thế mô hình dữ liệu, constraint hoặc quy tắc nghiệp vụ.

## 23. Kết luận

Chỉ mục phủ truy vấn là một composite index chứa đủ các cột mà một query cần, giúp Oracle có cơ hội trả kết quả bằng index-only access và tránh đọc table block theo ROWID. Khi thiết kế, hãy bắt đầu từ truy vấn thực tế: xác định cột lọc, nối, sắp xếp và hiển thị; chọn leading columns theo predicate và access pattern; đặt range và sort keys phù hợp; chỉ thêm cột projection thật sự cần để cover.

Lợi ích đọc phải được cân đối với chi phí ghi. Mỗi cột thêm vào index làm entry rộng hơn, chiếm thêm dung lượng và khiến INSERT, DELETE hoặc UPDATE key columns phải duy trì thêm dữ liệu. Index phủ cũng không được optimizer chọn trong mọi trường hợp; hãy xác nhận bằng execution plan và runtime statistics như buffers, elapsed time, table lookup và sort.

Tránh tạo index trùng hoặc prefix dư thừa bằng cách kiểm kê index hiện có, đối chiếu workload và kiểm tra constraint dependency trước khi xóa. Một index tốt không phải index chứa nhiều cột nhất, mà là index phục vụ được các truy vấn quan trọng với tổng chi phí đọc, ghi và lưu trữ phù hợp.
