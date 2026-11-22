# TABLE ACCESS FULL, BY INDEX ROWID và các đường truy cập chỉ mục

## 1. Access path trong execution plan là gì?

Oracle Database sử dụng Cost-Based Optimizer (CBO) để chọn cách đọc dữ liệu cho từng bảng hoặc partition trong câu SQL. Cách Oracle tìm và lấy các dòng từ một đối tượng được gọi là **access path** (đường truy cập).

Trong execution plan, access path thường được thể hiện bằng các operation như:

- `TABLE ACCESS FULL`: đọc các block của bảng theo kiểu full scan.
- `INDEX UNIQUE SCAN`, `INDEX RANGE SCAN`, `INDEX SKIP SCAN`: tìm các entry phù hợp trong B-tree index.
- `TABLE ACCESS BY INDEX ROWID`: dùng ROWID lấy các dòng tương ứng từ bảng sau khi tìm thấy entry trong index.
- `INDEX FULL SCAN`, `INDEX FAST FULL SCAN`: đọc toàn bộ index theo những cách khác nhau.
- `BITMAP INDEX ...`: thao tác trên bitmap index, thường gặp trong workload phân tích dữ liệu.

Access path là một phần của execution plan, không phải một câu lệnh SQL riêng hay một loại index. Optimizer chọn đường truy cập dựa trên thống kê, điều kiện truy vấn, cấu trúc bảng/index và chi phí dự kiến. Cùng một câu SQL có thể nhận plan khác nhau khi dữ liệu, statistics, bind value hoặc môi trường thực thi thay đổi.

## 2. TABLE ACCESS FULL

### 2.1. Oracle thực hiện full table scan như thế nào?

`TABLE ACCESS FULL` cho biết Oracle đọc dữ liệu trực tiếp từ các block của bảng thay vì tìm ROWID qua một B-tree index. Với heap table, full scan đọc các block đã được định dạng của segment nằm dưới high water mark (HWM), sau đó áp dụng các điều kiện lọc để xác định dòng cần trả về.

Ví dụ:

```sql
SELECT order_id, customer_id, order_date, amount
FROM orders
WHERE order_date >= DATE '2026-01-01';
```

Nếu điều kiện trả về phần lớn dòng trong `ORDERS`, optimizer có thể chọn full scan. Khi đó, execution plan có thể chứa operation:

```text
TABLE ACCESS FULL  ORDERS
```

Oracle có thể đọc nhiều block liên tiếp bằng multiblock I/O. Đối với truy vấn cần một tỷ lệ lớn dữ liệu, việc đọc tuần tự các block thường hiệu quả hơn việc tìm từng entry trong index rồi quay lại bảng để đọc từng block rải rác.

Với bảng partition, partition pruning có thể loại bỏ các partition không liên quan trước khi truy cập. Vì vậy, `TABLE ACCESS FULL` trên partition được chọn không nhất thiết có nghĩa Oracle đọc toàn bộ dữ liệu của tất cả partition trong bảng.

### 2.2. Khi nào full scan là lựa chọn tốt?

Full scan thường hợp lý trong các trường hợp sau:

- Bảng nhỏ; chi phí đọc toàn bộ bảng thấp hơn chi phí đi qua index.
- Truy vấn cần phần lớn dòng của bảng.
- Điều kiện lọc có selectivity thấp, tức số dòng thỏa điều kiện chiếm tỷ lệ lớn.
- Truy vấn cần nhiều cột, trong khi index chỉ chứa một phần nhỏ các cột đó; dùng index sẽ phải quay lại bảng nhiều lần.
- ROWID trong index phân tán trên nhiều block bảng, khiến việc lấy dòng qua index phát sinh nhiều lần đọc block.
- Truy vấn phân tích hoặc xử lý theo lô có thể tận dụng multiblock I/O và parallel execution.

Không nên kết luận `TABLE ACCESS FULL` là xấu chỉ vì tên operation có chữ `FULL`. Full scan có thể là đường truy cập ít tốn chi phí nhất. Ép Oracle dùng index trong trường hợp truy vấn cần nhiều dòng đôi khi làm truy vấn chậm hơn.

### 2.3. Điều kiện lọc trong full scan

Full scan có thể đọc block rồi loại bỏ các dòng không thỏa predicate. Trong phần Predicate Information của execution plan, điều kiện có thể được hiển thị là `filter`:

```text
filter("ORDER_DATE">=DATE '2026-01-01')
```

Điều kiện filter không đồng nghĩa Oracle đã tìm được một access path bằng index. Nó cho biết điều kiện được đánh giá trên các dòng mà operation đang xử lý.

## 3. B-tree index và ROWID

### 3.1. Index lưu gì?

B-tree index là cấu trúc cây cân bằng gồm root block, branch blocks và leaf blocks. Các leaf entry được sắp theo khóa index; với B-tree index thông thường trên heap table, entry chứa giá trị khóa và ROWID của dòng tương ứng.

Ví dụ:

```sql
CREATE INDEX ix_orders_customer_date
    ON orders(customer_id, order_date);
```

Index trên được sắp xếp theo `CUSTOMER_ID`, sau đó theo `ORDER_DATE` trong từng giá trị khách hàng. Khi truy vấn có điều kiện phù hợp với phần đầu của khóa, Oracle có thể đi từ root/branch đến vùng leaf chứa các entry cần tìm.

### 3.2. ROWID là gì?

ROWID là địa chỉ dùng để định vị một dòng trong bảng. Với heap table, extended ROWID biểu diễn thông tin định vị vật lý như data object, file, block và vị trí dòng trong block. Khi index trả về ROWID, Oracle có thể dùng địa chỉ đó để đọc block bảng chứa dòng tương ứng.

ROWID không phải khóa nghiệp vụ như `ORDER_ID`. Nó là thông tin định vị do Oracle quản lý. Không nên lưu ROWID như một định danh lâu dài trong ứng dụng, vì thao tác di chuyển hoặc tổ chức lại dữ liệu có thể làm thay đổi địa chỉ vật lý.

### 3.3. Vì sao index thường đi cùng TABLE ACCESS BY INDEX ROWID?

Index chỉ chứa các cột làm khóa index và thông tin định vị. Nếu câu SQL cần thêm cột không nằm trong index, Oracle phải đọc dòng thật trong bảng.

Ví dụ:

```sql
SELECT order_id, customer_id, order_date, amount, status
FROM orders
WHERE customer_id = :customer_id
  AND order_date >= DATE '2026-01-01';
```

Với index `(CUSTOMER_ID, ORDER_DATE)`, Oracle có thể tìm các entry phù hợp bằng `INDEX RANGE SCAN`. Nhưng `ORDER_ID`, `AMOUNT` và `STATUS` không có trong index, nên Oracle cần lấy dữ liệu từ bảng qua ROWID.

Một execution plan minh họa:

```text
SELECT STATEMENT
  TABLE ACCESS BY INDEX ROWID  ORDERS
    INDEX RANGE SCAN           IX_ORDERS_CUSTOMER_DATE
```

Đọc cây plan từ dưới lên để hiểu luồng dữ liệu: `INDEX RANGE SCAN` tìm các entry phù hợp và trả ROWID; `TABLE ACCESS BY INDEX ROWID` dùng các ROWID đó đọc các dòng trong `ORDERS`.

### 3.4. TABLE ACCESS BY INDEX ROWID BATCHED

Một biến thể có thể xuất hiện là:

```text
TABLE ACCESS BY INDEX ROWID BATCHED  ORDERS
```

Oracle gom một nhóm ROWID rồi sắp xếp hoặc tổ chức việc đọc theo block để giảm số lần truy cập block bảng rải rác. Cách xử lý theo batch có thể cải thiện locality của I/O khi nhiều ROWID nằm ở các block khác nhau.

`BATCHED` không có nghĩa kết quả SQL được đảm bảo sắp xếp theo ROWID hoặc theo thứ tự index. Nếu ứng dụng cần thứ tự kết quả, câu SQL vẫn phải có `ORDER BY` phù hợp.

Với bảng partition và global index, plan còn có thể hiển thị operation như `TABLE ACCESS BY GLOBAL INDEX ROWID`. Khi đọc plan, hãy xem tên operation đầy đủ để nhận biết loại truy cập và quan hệ với partition.

## 4. Các đường truy cập B-tree index

### 4.1. INDEX UNIQUE SCAN

`INDEX UNIQUE SCAN` tìm một entry trong unique index bằng điều kiện bằng trên toàn bộ khóa duy nhất. Nếu khóa là một cột:

```sql
SELECT order_id
FROM orders
WHERE order_id = :order_id;
```

và `ORDER_ID` có unique index hoặc là primary key, Oracle có thể dùng `INDEX UNIQUE SCAN`.

Với unique composite index gồm `(A, B)`, để xác định duy nhất một entry theo cách này, predicate cần cung cấp giá trị bằng cho toàn bộ các cột khóa. Nếu chỉ có điều kiện trên `A`, Oracle thường phải xem xét một range thay vì một unique lookup.

Unique scan chỉ cho tối đa một entry index. Nếu truy vấn cần các cột không có trong index, plan vẫn có thể có `TABLE ACCESS BY INDEX ROWID` ở phía trên để đọc dòng bảng.

### 4.2. INDEX RANGE SCAN

`INDEX RANGE SCAN` tìm một khoảng entry trong index. Nó thường xuất hiện với:

- Điều kiện bằng trên khóa index không unique.
- Điều kiện bằng trên phần đầu của composite index.
- Điều kiện khoảng như `>`, `>=`, `<`, `<=` hoặc `BETWEEN` trên cột tiếp theo sau phần khóa bằng.

Ví dụ:

```sql
SELECT order_id, order_date
FROM orders
WHERE customer_id = :customer_id
  AND order_date >= DATE '2026-01-01'
  AND order_date <  DATE '2027-01-01';
```

Với index `(CUSTOMER_ID, ORDER_DATE)`, Oracle có thể tìm vùng leaf tương ứng với một `CUSTOMER_ID`, rồi đọc khoảng `ORDER_DATE` trong vùng đó.

Range scan có thể trả về một hoặc nhiều ROWID. Số entry phải đọc phụ thuộc vào độ chọn lọc của predicate và phân bố dữ liệu. Range scan không tự bảo đảm toàn bộ câu SQL có thứ tự mong muốn; thứ tự của index chỉ có thể giúp tránh sort khi các cột, hướng sắp xếp và điều kiện truy vấn phù hợp.

### 4.3. INDEX RANGE SCAN DESCENDING

`INDEX RANGE SCAN DESCENDING` đọc vùng index theo chiều ngược lại. Oracle có thể dùng đường truy cập này khi truy vấn cần thứ tự giảm dần phù hợp với khóa index, ví dụ:

```sql
SELECT order_id, order_date
FROM orders
WHERE customer_id = :customer_id
ORDER BY order_date DESC;
```

Việc có thể bỏ operation `SORT ORDER BY` hay không còn phụ thuộc toàn bộ cấu trúc index, predicate và hướng sắp xếp. Hãy kiểm tra execution plan thay vì suy luận chỉ từ một dòng SQL.

### 4.4. INDEX SKIP SCAN

Composite index được tổ chức theo thứ tự các cột. Index `(A, B)` thường hữu ích nhất khi truy vấn có predicate trên cột dẫn đầu `A`. Tuy vậy, Oracle đôi khi vẫn có thể dùng index khi truy vấn chỉ lọc theo `B`, thông qua `INDEX SKIP SCAN`.

Ví dụ index:

```sql
CREATE INDEX ix_orders_status_customer
    ON orders(status, customer_id);
```

Truy vấn:

```sql
SELECT order_id
FROM orders
WHERE customer_id = :customer_id;
```

Oracle có thể xem index như nhiều vùng logic, mỗi vùng tương ứng một giá trị `STATUS`, rồi tìm `CUSTOMER_ID` trong từng vùng. Cách này có thể có ích khi số giá trị phân biệt của cột dẫn đầu thấp.

Skip scan không phải cách thay thế mặc định cho index có thứ tự cột phù hợp. Nếu cột dẫn đầu có rất nhiều giá trị phân biệt, việc lặp qua nhiều vùng logic có thể tốn kém. Khi workload thường xuyên lọc theo `CUSTOMER_ID`, index bắt đầu bằng `CUSTOMER_ID` có thể phù hợp hơn.

### 4.5. INDEX FULL SCAN

`INDEX FULL SCAN` đọc toàn bộ leaf entry của index theo thứ tự khóa. Oracle có thể chọn đường truy cập này khi:

- Truy vấn cần các cột có sẵn trong index.
- Đọc index nhỏ hơn hoặc rẻ hơn đọc toàn bộ bảng.
- Thứ tự index có thể đáp ứng yêu cầu sắp xếp, nhờ đó tránh một bước sort riêng.

Ví dụ:

```sql
SELECT customer_id, order_date
FROM orders
ORDER BY customer_id, order_date;
```

Nếu index `(CUSTOMER_ID, ORDER_DATE)` phù hợp và chứa đủ các cột cần trả về, Oracle có thể đọc index theo thứ tự để lấy kết quả. Khi mọi dữ liệu cần thiết đã nằm trong index, không cần thêm `TABLE ACCESS BY INDEX ROWID`.

### 4.6. INDEX FAST FULL SCAN

`INDEX FAST FULL SCAN` đọc toàn bộ block của index như đọc một segment dạng bảng, thường tận dụng multiblock I/O. Nó không duy trì thứ tự khóa index trong kết quả.

Đường truy cập này hữu ích khi truy vấn cần toàn bộ dữ liệu từ một index đủ hẹp và không yêu cầu thứ tự do index cung cấp. Ví dụ, nếu truy vấn chỉ cần các cột đã có trong index, Oracle có thể quét index thay vì quét bảng:

```sql
SELECT COUNT(*)
FROM orders;
```

Optimizer có thể chọn một index phù hợp để lấy thông tin cần thiết, nhưng lựa chọn thực tế phụ thuộc statistics và chi phí. `INDEX FAST FULL SCAN` không đồng nghĩa với `INDEX FULL SCAN`: fast full scan ưu tiên đọc block hiệu quả và không bảo đảm thứ tự khóa; full scan đi theo thứ tự index.

### 4.7. Tổng hợp các B-tree index scan

| Operation | Mục đích | Đặc điểm chính |
|---|---|---|
| `INDEX UNIQUE SCAN` | Tìm một entry theo toàn bộ khóa unique | Tối đa một entry |
| `INDEX RANGE SCAN` | Tìm một khoảng entry | Có thể trả nhiều entry/ROWID |
| `INDEX RANGE SCAN DESCENDING` | Đọc một khoảng theo chiều ngược | Có thể hỗ trợ thứ tự giảm dần phù hợp |
| `INDEX SKIP SCAN` | Tìm theo cột không dẫn đầu của composite index | Xem xét các vùng logic theo giá trị cột dẫn đầu |
| `INDEX FULL SCAN` | Đọc toàn bộ index theo thứ tự khóa | Có thể hỗ trợ `ORDER BY` và index-only access |
| `INDEX FAST FULL SCAN` | Đọc toàn bộ block index | Multiblock I/O; không bảo đảm thứ tự khóa |

## 5. Index-only access và các loại index khác

### 5.1. Khi nào không cần TABLE ACCESS BY INDEX ROWID?

Nếu index chứa toàn bộ cột cần cho predicate và kết quả, Oracle có thể xử lý truy vấn chỉ bằng index. Ví dụ:

```sql
SELECT customer_id, order_date
FROM orders
WHERE customer_id = :customer_id;
```

Với index `(CUSTOMER_ID, ORDER_DATE)`, các giá trị cần trả về đã nằm trong index. Plan có thể chỉ cần `INDEX RANGE SCAN` mà không cần quay lại bảng.

Đây thường được gọi là index-only access hoặc covering access. Lợi ích là giảm việc đọc block bảng qua ROWID. Tuy nhiên, thêm quá nhiều cột vào index để bao phủ mọi truy vấn sẽ làm index lớn hơn, tăng chi phí ghi, cập nhật và lưu trữ. Cần cân đối workload đọc và ghi.

### 5.2. Bitmap index

Bitmap index lưu thông tin biểu diễn các dòng phù hợp với giá trị khóa dưới dạng bitmap. Oracle có thể kết hợp nhiều bitmap bằng các operation như `BITMAP AND` hoặc `BITMAP OR`, rồi chuyển bitmap thành ROWID để đọc bảng.

Ví dụ minh họa một plan có thể chứa:

```text
TABLE ACCESS BY INDEX ROWID  ORDERS
  BITMAP CONVERSION TO ROWIDS
    BITMAP AND
      BITMAP INDEX SINGLE VALUE  IX_ORDERS_STATUS_BM
      BITMAP INDEX SINGLE VALUE  IX_ORDERS_REGION_BM
```

Bitmap index thường phù hợp với workload kho dữ liệu hoặc phân tích, nơi predicate kết hợp trên các cột có ít giá trị phân biệt. Với workload OLTP có nhiều giao dịch cập nhật đồng thời, bitmap index có thể gây phạm vi khóa rộng hơn và ảnh hưởng concurrency; cần cân nhắc kỹ trước khi áp dụng.

### 5.3. Function-based index

Khi truy vấn lọc trên biểu thức, có thể cần index được tạo trên chính biểu thức đó:

```sql
CREATE INDEX ix_customers_upper_email
    ON customers(UPPER(email));

SELECT customer_id
FROM customers
WHERE UPPER(email) = :email;
```

Function-based index tạo một access path dựa trên kết quả biểu thức. Predicate cần tương thích với biểu thức đã index để optimizer có thể sử dụng. Statistics cho biểu thức và index có vai trò khác nhau: statistics hỗ trợ ước lượng, còn index cung cấp access path.

## 6. Vì sao Oracle chọn full scan hay index access?

Optimizer ước lượng chi phí của các plan ứng viên. Không có một ngưỡng selectivity cố định áp dụng cho mọi bảng để quyết định lúc nào dùng index. Một số yếu tố chính gồm:

### 6.1. Selectivity và cardinality

**Selectivity** thể hiện tỷ lệ dòng thỏa một predicate; **cardinality** là số dòng được ước lượng tại một operation. Predicate càng chọn lọc, index càng có cơ hội giảm lượng dữ liệu phải đọc. Nhưng một index scan có selectivity tốt vẫn có thể tốn kém nếu các ROWID dẫn đến nhiều block khác nhau.

Nếu optimizer ước lượng sai cardinality, nó có thể chọn access path không phù hợp. Hãy kiểm tra statistics và extended statistics khi các cột tương quan hoặc predicate dùng biểu thức.

### 6.2. Clustering factor

Clustering factor mô tả mức độ tương quan giữa thứ tự ROWID trong index và thứ tự các dòng trong block bảng. Có thể hiểu gần đúng:

- Clustering factor thấp, gần số block của bảng: các ROWID liên tiếp trong index thường trỏ đến ít block lặp lại hơn.
- Clustering factor cao, gần số dòng của bảng: các ROWID liên tiếp có xu hướng nằm rải rác ở nhiều block.

Khi clustering factor cao, index range scan có thể phải đọc nhiều block bảng riêng lẻ. Nếu predicate trả về nhiều dòng, full scan có thể rẻ hơn.

### 6.3. Kích thước bảng và index

Một index nhỏ hơn bảng đáng kể có thể là đường đọc hiệu quả, nhất là khi truy vấn chỉ cần cột có trong index. Ngược lại, nếu truy vấn cần nhiều cột và nhiều dòng, việc đọc index rồi truy cập bảng có thể tạo ra lượng I/O lớn hơn full scan.

### 6.4. Các yếu tố khác

Optimizer còn xem xét:

- Số block và số dòng của bảng, số leaf block và chiều cao index.
- Histogram và độ lệch phân bố dữ liệu.
- Số cột được truy vấn cần đọc và khả năng index-only access.
- Partition pruning và loại index local/global.
- System statistics, mô hình I/O, parallel degree và các thuộc tính của môi trường.
- Predicate có thể được chuyển thành điều kiện truy cập index hay chỉ được lọc sau khi lấy dòng.

Vì vậy, không nên đánh giá plan bằng một quy tắc đơn giản như “có index thì phải dùng index” hoặc “full scan luôn chậm”. Cần xem số dòng thực tế, số block đọc và mục tiêu của truy vấn.

## 7. ACCESS predicate và FILTER predicate

Trong phần Predicate Information của execution plan, Oracle phân biệt điều kiện dùng để truy cập dữ liệu và điều kiện dùng để lọc các dòng đã được lấy:

- `access(...)`: điều kiện giúp xác định vùng index hoặc phạm vi truy cập của operation.
- `filter(...)`: điều kiện được đánh giá trên các dòng mà operation nhận hoặc đọc được.

Ví dụ với index `(CUSTOMER_ID, ORDER_DATE)`:

```sql
SELECT order_id, amount
FROM orders
WHERE customer_id = :customer_id
  AND order_date >= DATE '2026-01-01'
  AND status = 'SHIPPED';
```

Optimizer có thể dùng `CUSTOMER_ID` và `ORDER_DATE` để tìm range trong index. Nếu `STATUS` không có trong index, điều kiện `STATUS = 'SHIPPED'` có thể được đánh giá sau khi Oracle lấy dòng từ bảng. Khi đó plan có thể cho thấy `access` trên hai cột index và `filter` trên `STATUS`.

Phân biệt hai loại predicate giúp xác định index đang thu hẹp phạm vi tìm kiếm đến đâu và Oracle phải đọc bao nhiêu dòng trước khi lọc tiếp. Tuy nhiên, không phải mọi operation đều có cả hai loại predicate; hãy đọc chúng trong ngữ cảnh của operation cụ thể.

## 8. Đọc và kiểm chứng access path bằng DBMS_XPLAN

### 8.1. Lấy execution plan kèm số liệu runtime

Có thể dùng hint `GATHER_PLAN_STATISTICS` để thu thập số liệu thực thi cho cursor:

```sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       order_id, customer_id, order_date, amount
FROM orders
WHERE customer_id = :customer_id
  AND order_date >= DATE '2026-01-01';
```

Ngay sau khi chạy câu SQL, xem cursor vừa thực thi:

```sql
SELECT *
FROM TABLE(
  DBMS_XPLAN.DISPLAY_CURSOR(
    NULL,
    NULL,
    'ALLSTATS LAST +PREDICATE +ALIAS'
  )
);
```

`ALLSTATS LAST` hiển thị thống kê runtime của lần thực thi gần nhất khi row-source statistics đã được thu thập. Nếu không dùng hint hoặc cấu hình thu thập runtime statistics tương ứng, các cột thực tế có thể không xuất hiện đầy đủ.

### 8.2. Những cột cần quan sát

| Cột | Ý nghĩa |
|---|---|
| `Operation` / `Name` | Loại operation và đối tượng được truy cập |
| `E-Rows` | Số dòng optimizer ước lượng |
| `A-Rows` | Số dòng thực tế operation trả ra |
| `Starts` | Số lần operation được khởi chạy |
| `Buffers` | Số logical reads (buffer gets) được ghi nhận |
| `Reads` | Số physical reads được ghi nhận |
| `A-Time` | Thời gian thực tế được ghi nhận cho operation |

Khi đánh giá access path, trước hết so sánh `E-Rows` và `A-Rows`. Sai lệch lớn có thể khiến các operation phía trên trong cây plan nhận đầu vào khác xa dự đoán. Sau đó xem `Buffers`, `Reads`, `Starts` và thời gian để hiểu chi phí thực tế.

Không cộng máy móc thời gian của mọi dòng operation vì thời gian ở các node cha có thể bao gồm thời gian của node con. Hãy xem plan như cây xử lý dữ liệu và đọc số liệu theo quan hệ cha-con.

### 8.3. EXPLAIN PLAN và DISPLAY_CURSOR

`EXPLAIN PLAN` cho biết plan optimizer dự kiến cho câu SQL trong ngữ cảnh explain. Nó không thực thi câu SQL để thu thập số liệu thực tế. Bind values, session settings và môi trường có thể khiến plan explain khác cursor thực sự chạy.

`DBMS_XPLAN.DISPLAY_CURSOR` đọc plan của cursor trong shared SQL area và có thể hiển thị runtime statistics nếu đã thu thập. Khi điều tra vấn đề hiệu năng, hãy ưu tiên plan của cursor thực tế cùng bind values và điều kiện chạy tương ứng.

## 9. Ví dụ so sánh hai access path

Giả sử bảng `ORDERS` có hàng triệu dòng và có index:

```sql
CREATE INDEX ix_orders_customer_date
    ON orders(customer_id, order_date);
```

### Truy vấn chọn lọc cao

```sql
SELECT order_id, amount
FROM orders
WHERE customer_id = 90001
  AND order_date >= DATE '2026-11-01'
  AND order_date <  DATE '2026-11-08';
```

Nếu chỉ có một số ít dòng phù hợp, optimizer có thể chọn:

```text
SELECT STATEMENT
  TABLE ACCESS BY INDEX ROWID  ORDERS
    INDEX RANGE SCAN           IX_ORDERS_CUSTOMER_DATE
```

Index thu hẹp vùng tìm kiếm; ROWID giúp lấy `ORDER_ID` và `AMOUNT` từ bảng. Nếu index bao phủ toàn bộ cột cần thiết, operation đọc bảng có thể không còn cần thiết.

### Truy vấn cần phần lớn bảng

```sql
SELECT order_id, customer_id, order_date, amount, status
FROM orders
WHERE order_date >= DATE '2020-01-01';
```

Nếu điều kiện trả về phần lớn dòng, index có thể dẫn đến nhiều lần truy cập block bảng và phải đọc nhiều cột không có trong index. Optimizer có thể chọn:

```text
SELECT STATEMENT
  TABLE ACCESS FULL  ORDERS
```

Hai plan trên chỉ minh họa cách operation có thể xuất hiện; không phải plan cố định cho mọi database. Lựa chọn thật phụ thuộc dữ liệu, statistics, cấu hình và chi phí được optimizer tính toán.

## 10. Quy trình phân tích và cải thiện access path

Khi gặp truy vấn chậm, có thể đi theo quy trình sau:

1. Lấy SQL thực tế, bind values và execution plan của cursor đã chạy.
2. Dùng runtime statistics để xác định operation có sai lệch lớn giữa `E-Rows` và `A-Rows`.
3. Xác định truy vấn cần ít dòng hay nhiều dòng; kiểm tra predicate nào là `access`, predicate nào là `filter`.
4. Kiểm tra index hiện có, thứ tự cột của composite index, các cột truy vấn cần đọc và khả năng index-only access.
5. Xem clustering factor, số leaf block, histogram, độ mới của table/index statistics và khả năng partition pruning.
6. So sánh logical reads, physical reads và thời gian giữa các phương án trên workload đại diện.
7. Chỉ thay đổi index, statistics hoặc SQL khi có bằng chứng về nguyên nhân; sau thay đổi, chạy lại và kiểm chứng plan thực tế.

Tránh thêm index chỉ vì thấy `TABLE ACCESS FULL`, cũng tránh ép `INDEX` hoặc `FULL` bằng hint trước khi hiểu chi phí. Mỗi index mới làm tăng dung lượng và công việc bảo trì khi insert, update, delete. Một access path tốt là đường có chi phí phù hợp với workload và yêu cầu của truy vấn.

## Tài liệu Oracle tham khảo

- [Oracle Database 19c SQL Tuning Guide — Optimizer Access Paths](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/optimizer-access-paths.html)
- [Oracle Database 19c SQL Tuning Guide — Generating and Displaying Execution Plans](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/generating-and-displaying-execution-plans.html)
- [Oracle Database 19c PL/SQL Packages and Types Reference — DBMS_XPLAN](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_XPLAN.html)
- [Oracle Database 19c Concepts — Indexes and Index-Organized Tables](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/indexes-and-index-organized-tables.html)
