# Index skip scan và điều kiện bộ tối ưu cân nhắc trong Oracle

Composite B-tree index (chỉ mục ghép) lưu khóa theo thứ tự các cột đã khai báo. Khi truy vấn lọc theo cột đứng đầu, Oracle thường có thể đi thẳng đến vùng khóa phù hợp bằng index range scan. Nhưng nếu điều kiện chỉ lọc theo cột đứng sau, liệu chỉ mục ghép có hoàn toàn vô dụng?

Oracle có một access path tên **index skip scan**. Với một số cấu hình dữ liệu, bộ tối ưu có thể xem chỉ mục ghép như nhiều vùng tìm kiếm logic được chia theo các giá trị của cột dẫn đầu, rồi tìm giá trị ở cột phía sau trong từng vùng. Cách này có thể hữu ích khi cột dẫn đầu có ít giá trị phân biệt và điều kiện trên cột phía sau chọn được ít dòng.

Skip scan là một lựa chọn dựa trên chi phí, không phải bảo đảm rằng Oracle sẽ dùng index. Bài học này giải thích cấu trúc chỉ mục ghép, cơ chế skip scan, các yếu tố optimizer cân nhắc, cách đọc execution plan và cách quyết định thứ tự cột index theo workload.

## 1. Nhắc lại cấu trúc composite B-tree index

Một index ghép chứa nhiều cột. Ví dụ:

~~~sql
CREATE INDEX ix_orders_status_customer
ON orders (order_status, customer_id);
~~~

Oracle sắp xếp khóa theo thứ tự:

1. ORDER_STATUS trước.
2. Trong cùng một ORDER_STATUS, sắp xếp tiếp theo CUSTOMER_ID.

Có thể hình dung index như sau:

~~~text
(CANCELLED, 101)
(CANCELLED, 105)
(CANCELLED, 210)
...
(PAID,      101)
(PAID,      105)
(PAID,      210)
...
(PENDING,   101)
(PENDING,   105)
(PENDING,   210)
...
~~~

Đây là cách mô tả logic để hiểu thứ tự khóa, không phải cách Oracle lưu một danh sách văn bản. B-tree thực tế tổ chức các entry trong root, branch và leaf blocks.

### 1.1. Leading column và trailing column

Với index (ORDER_STATUS, CUSTOMER_ID):

- ORDER_STATUS là **leading column** (cột dẫn đầu).
- CUSTOMER_ID là **trailing column** (cột phía sau).

Các điều kiện truy vấn thường có lợi:

~~~sql
-- Có điều kiện trên leading column.
SELECT *
FROM orders
WHERE order_status = 'PAID';

-- Có điều kiện trên cả leading và trailing column.
SELECT *
FROM orders
WHERE order_status = 'PAID'
  AND customer_id = 101;
~~~

Oracle có thể xác định một vùng khóa liên tục trong index dựa trên cột dẫn đầu, rồi tiếp tục áp dụng điều kiện cột sau.

### 1.2. Khi chỉ lọc trailing column

~~~sql
SELECT *
FROM orders
WHERE customer_id = 101;
~~~

Vì các khóa được sắp theo ORDER_STATUS trước, các entry có CUSTOMER_ID = 101 không nhất thiết nằm liền nhau trong toàn bộ index. Chúng được phân tán trong các nhóm ORDER_STATUS khác nhau.

Một cách truy cập truyền thống là full table scan. Tuy nhiên, nếu ORDER_STATUS chỉ có vài giá trị phân biệt, Oracle có thể cân nhắc index skip scan.

## 2. Index skip scan là gì?

**Index skip scan** là một access path cho phép Oracle sử dụng composite B-tree index ngay cả khi câu truy vấn không có điều kiện trên leading column, bằng cách xét các giá trị khác nhau của cột dẫn đầu và tìm kiếm trong từng vùng logic tương ứng.

Với index:

~~~sql
CREATE INDEX ix_orders_status_customer
ON orders (order_status, customer_id);
~~~

và truy vấn:

~~~sql
SELECT *
FROM orders
WHERE customer_id = 101;
~~~

Oracle có thể xử lý về mặt khái niệm như sau:

1. Xét giá trị ORDER_STATUS thứ nhất, tìm CUSTOMER_ID = 101 trong vùng khóa đó.
2. Chuyển sang giá trị ORDER_STATUS tiếp theo, tiếp tục tìm CUSTOMER_ID = 101.
3. Lặp lại với các giá trị leading column khác.
4. Ghép các rowid tìm được để truy cập dòng trong bảng nếu cần.

~~~text
Index (ORDER_STATUS, CUSTOMER_ID)

Nhóm CANCELLED: tìm CUSTOMER_ID = 101
          |
          v
Nhóm PAID:      tìm CUSTOMER_ID = 101
          |
          v
Nhóm PENDING:   tìm CUSTOMER_ID = 101
          |
          v
Kết hợp các entry phù hợp
          |
          v
Truy cập dòng bảng theo ROWID nếu cần
~~~

Các nhóm trên là **logical subindexes** (chỉ mục con logic) theo từng giá trị leading key. Oracle không tạo ra một index vật lý mới cho mỗi giá trị. Nó dùng cấu trúc B-tree hiện có để thực hiện các lần tìm kiếm tương ứng.

### 2.1. Vì sao tên gọi là skip scan?

Oracle bỏ qua việc cần cố định một giá trị leading column duy nhất. Thay vào đó, nó lần lượt xét các giá trị dẫn đầu có thể có và tìm trong các vùng khóa phía sau. Cách truy cập này khác với một index range scan thông thường chỉ đi vào một vùng khóa liên tục được xác định bởi leading key.

Skip scan không có nghĩa Oracle tùy tiện bỏ qua các block hoặc chỉ đọc một vài dòng. Chi phí vẫn phụ thuộc số giá trị leading key, kích thước index, số entry phù hợp và số lần phải truy cập bảng.

### 2.2. Điều kiện quan trọng: leading column có ít giá trị phân biệt

Giả sử ORDER_STATUS chỉ có ba giá trị:

- CANCELLED
- PAID
- PENDING

Khi truy vấn chỉ lọc CUSTOMER_ID, Oracle có thể cần xét ba vùng logic theo ORDER_STATUS. Nếu leading column có hàng nghìn giá trị phân biệt, số vùng cần xét lớn hơn nhiều và skip scan thường kém hấp dẫn.

Quy tắc định hướng:

> Skip scan đáng cân nhắc khi leading column có cardinality thấp, còn điều kiện trên trailing column có tính chọn lọc tốt.

Đây là quy tắc thực hành, không phải công thức buộc optimizer phải chọn skip scan. Oracle vẫn so sánh chi phí với full table scan và các access path khác.

## 3. Chuẩn bị dữ liệu thực hành

Ta tạo bảng đơn hàng với:

- ORDER_STATUS: chỉ có ba giá trị trạng thái.
- CUSTOMER_ID: có nhiều giá trị khác nhau.
- ORDER_ID: mã đơn hàng.
- ORDER_DATE và AMOUNT: dữ liệu bổ sung để truy vấn.

Index ghép sẽ đặt ORDER_STATUS trước CUSTOMER_ID. Sau đó ta chạy truy vấn chỉ lọc CUSTOMER_ID để quan sát khả năng skip scan.

### 3.1. Tạo bảng

Chạy trong schema lab thuộc PDB thực hành. Nếu bảng cùng tên đã tồn tại, hãy dùng schema hoặc tên khác; không ghi đè dữ liệu đang sử dụng.

~~~sql
CREATE TABLE lab_ss_orders (
    order_id     NUMBER(10) PRIMARY KEY,
    order_status VARCHAR2(12 CHAR) NOT NULL,
    customer_id  NUMBER(10) NOT NULL,
    order_date   DATE NOT NULL,
    amount       NUMBER(12,2) NOT NULL,
    CONSTRAINT ck_lab_ss_order_status
      CHECK (order_status IN ('PAID', 'PENDING', 'CANCELLED')),
    CONSTRAINT ck_lab_ss_amount
      CHECK (amount >= 0)
);
~~~

### 3.2. Sinh dữ liệu mẫu

Để optimizer có đủ dữ liệu để so sánh access path, tạo 200.000 dòng:

~~~sql
INSERT INTO lab_ss_orders (
    order_id,
    order_status,
    customer_id,
    order_date,
    amount
)
SELECT
    LEVEL,
    CASE MOD(LEVEL, 3)
        WHEN 0 THEN 'PAID'
        WHEN 1 THEN 'PENDING'
        ELSE 'CANCELLED'
    END,
    MOD(LEVEL * 37, 10000) + 1,
    DATE '2024-01-01' + MOD(LEVEL, 730),
    MOD(LEVEL * 19, 50000) / 100
FROM dual
CONNECT BY LEVEL <= 200000;

COMMIT;
~~~

Với công thức trên:

- ORDER_ID chạy từ 1 đến 200000.
- ORDER_STATUS có ba giá trị.
- CUSTOMER_ID nằm trong khoảng 1 đến 10000.
- Nhiều đơn thuộc cùng một khách hàng.

Đây là dữ liệu giả lập để học access path, không phải mô hình phân bố dữ liệu chuẩn cho mọi ứng dụng.

### 3.3. Tạo composite index

~~~sql
CREATE INDEX ix_lab_ss_status_customer
ON lab_ss_orders (order_status, customer_id);
~~~

### 3.4. Thu thập statistics

Optimizer cần statistics để ước lượng cardinality và chi phí:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'LAB_SS_ORDERS',
        cascade => TRUE
    );
END;
/
~~~

CASCADE => TRUE yêu cầu thu thập statistics cho các index liên quan cùng với bảng. Quyền sử dụng DBMS_STATS và chính sách statistics có thể khác giữa các môi trường; trong schema lab, dùng quyền được cấp cho schema.

### 3.5. Kiểm tra phân bố giá trị

~~~sql
SELECT
    order_status,
    COUNT(*) AS order_count
FROM lab_ss_orders
GROUP BY order_status
ORDER BY order_status;
~~~

Và:

~~~sql
SELECT
    COUNT(DISTINCT order_status) AS status_ndv,
    COUNT(DISTINCT customer_id) AS customer_ndv,
    COUNT(*) AS total_rows
FROM lab_ss_orders;
~~~

NDV là viết tắt của number of distinct values (số giá trị phân biệt). Dataset này có ba giá trị ORDER_STATUS và 10000 giá trị CUSTOMER_ID.

## 4. Truy vấn có thể dùng index skip scan

Truy vấn chỉ lọc theo CUSTOMER_ID:

~~~sql
SELECT
    order_id,
    order_status,
    customer_id,
    amount
FROM lab_ss_orders
WHERE customer_id = 1234;
~~~

Index có thứ tự (ORDER_STATUS, CUSTOMER_ID), nhưng điều kiện chỉ có CUSTOMER_ID. Vì ORDER_STATUS có ba giá trị, optimizer có thể cân nhắc skip scan để tìm các entry CUSTOMER_ID = 1234 trong từng nhóm trạng thái.

Nếu access path được chọn, execution plan thường có operation:

~~~text
INDEX SKIP SCAN
~~~

Vì truy vấn còn lấy ORDER_ID và AMOUNT không nằm trong index, kế hoạch có thể cần thêm TABLE ACCESS BY INDEX ROWID để lấy các cột còn lại từ bảng.

**Không có bảo đảm** rằng optimizer sẽ chọn skip scan trên mọi máy hoặc mọi lần chạy. Nếu bảng nhỏ, statistics khác, bind value khác hoặc full table scan rẻ hơn, kế hoạch có thể khác.

## 5. Đọc execution plan để xác nhận skip scan

### 5.1. Dùng EXPLAIN PLAN

~~~sql
EXPLAIN PLAN FOR
SELECT
    order_id,
    order_status,
    customer_id,
    amount
FROM lab_ss_orders
WHERE customer_id = 1234;

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY(
        NULL,
        NULL,
        'BASIC +PREDICATE +COST +NOTE'
    )
);
~~~

Trong kết quả, tìm operation INDEX SKIP SCAN và tên index IX_LAB_SS_STATUS_CUSTOMER.

Một phần kế hoạch có thể có dạng khái niệm:

~~~text
--------------------------------------------------------------------------------
| Id | Operation                    | Name                         |
--------------------------------------------------------------------------------
|  0 | SELECT STATEMENT              |                              |
|  1 |  TABLE ACCESS BY INDEX ROWID  | LAB_SS_ORDERS                |
|  2 |   INDEX SKIP SCAN             | IX_LAB_SS_STATUS_CUSTOMER    |
--------------------------------------------------------------------------------
~~~

Đây chỉ là hình minh họa hình dạng operation; số Id, cost, cardinality và việc có TABLE ACCESS hay không phụ thuộc kế hoạch thực tế.

### 5.2. Dùng hint để quan sát access path

Nếu optimizer chọn full table scan vì chi phí ước lượng, có thể thử hint INDEX_SS trong môi trường lab để yêu cầu xem xét index skip scan:

~~~sql
EXPLAIN PLAN FOR
SELECT /*+ INDEX_SS(o ix_lab_ss_status_customer) */
    o.order_id,
    o.order_status,
    o.customer_id,
    o.amount
FROM lab_ss_orders o
WHERE o.customer_id = 1234;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

Hint INDEX_SS là công cụ thử nghiệm và điều khiển optimizer. Hint có thể bị bỏ qua nếu sai alias, sai index, không áp dụng được hoặc xung đột với ngữ cảnh truy vấn. Luôn kiểm tra execution plan để biết hint có tác dụng hay không.

Không giữ hint chỉ vì nó tạo ra operation INDEX SKIP SCAN. Kế hoạch tốt phải phù hợp với dữ liệu và workload thực tế.

### 5.3. Xem số liệu runtime

EXPLAIN PLAN thể hiện kế hoạch ước lượng; để xem thống kê của lần chạy, có thể dùng GATHER_PLAN_STATISTICS:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS INDEX_SS(o ix_lab_ss_status_customer) */
    o.order_id,
    o.order_status,
    o.customer_id,
    o.amount
FROM lab_ss_orders o
WHERE o.customer_id = 1234;
~~~

Sau khi chạy truy vấn:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE +COST +NOTE'
    )
);
~~~

ALLSTATS LAST hiển thị thống kê thực tế của lần chạy gần nhất nếu các thống kê đã được thu thập. Việc đọc cursor và các view nền có thể yêu cầu quyền bổ sung. Nếu không có quyền, dùng EXPLAIN PLAN hoặc nhờ DBA cung cấp thông tin phù hợp.

## 6. Vì sao optimizer chọn hoặc không chọn skip scan?

Oracle dùng cost-based optimizer (CBO). Nó ước lượng số dòng sẽ trả về, số block cần đọc, chi phí CPU/I/O và so sánh các kế hoạch khả thi.

Với skip scan, các yếu tố đáng chú ý gồm:

1. Số giá trị phân biệt của leading column.
2. Tính chọn lọc của điều kiện trên trailing column.
3. Tổng số dòng và kích thước bảng.
4. Kích thước index và số leaf block.
5. Clustering factor của index.
6. Statistics có đầy đủ và cập nhật hay không.
7. Các access path khác, như index riêng trên trailing column hoặc full table scan.
8. Số cột truy vấn cần lấy và chi phí truy cập bảng theo ROWID.

### 6.1. Cardinality của leading column

Đây thường là yếu tố đầu tiên cần quan sát.

| Leading column | Số giá trị phân biệt | Khả năng skip scan |
|---|---:|---|
| ORDER_STATUS | 3 | Có thể hấp dẫn nếu trailing key chọn lọc |
| GENDER | 2 | Có thể hấp dẫn nếu các điều kiện khác phù hợp |
| COUNTRY_CODE | 200 | Có thể tốn hơn vì phải xét nhiều nhóm |
| CUSTOMER_ID | 1000000 | Thường kém hấp dẫn nếu bỏ qua leading column |

Số NDV thấp làm số vùng logic cần xét ít hơn. Tuy nhiên, NDV thấp không tự bảo đảm skip scan tốt: nếu trailing predicate trả về quá nhiều dòng, full scan vẫn có thể rẻ hơn.

### 6.2. Selectivity của trailing column

Selectivity mô tả tỷ lệ dòng thỏa điều kiện. Nếu CUSTOMER_ID = 1234 chỉ trả một lượng nhỏ trong 200000 dòng, điều kiện có tính chọn lọc cao.

Nếu điều kiện trả về phần lớn bảng, việc đọc index rồi truy cập nhiều rowid có thể tốn kém hơn đọc bảng tuần tự.

Ví dụ:

~~~sql
-- Có thể chọn lọc cao nếu một khách chỉ có ít đơn.
WHERE customer_id = 1234

-- Có thể chọn lọc thấp nếu điều kiện bao phủ phần lớn khách.
WHERE customer_id BETWEEN 1 AND 9000
~~~

Không chỉ nhìn toán tử. Hãy dựa vào phân bố dữ liệu và số dòng thực tế.

### 6.3. Kích thước index và bảng

Index nhỏ hơn bảng nhiều có thể làm việc tìm kiếm bằng index hấp dẫn. Nhưng skip scan cần xét nhiều vùng logic; nếu index lớn hoặc leading NDV cao, tổng block đọc có thể tăng.

Optimizer cân nhắc chi phí truy cập index và chi phí lấy dòng từ table. Một index bao phủ mọi cột SELECT có thể tránh table access, trong khi index không bao phủ có thể cần truy cập ROWID.

### 6.4. Clustering factor

Clustering factor phản ánh mức độ tương quan giữa thứ tự key trong index và vị trí các dòng trong table. Khi các dòng có key gần nhau cũng nằm gần nhau trong data block, việc truy cập table qua ROWID có thể hiệu quả hơn.

Nếu clustering factor cao, các rowid tìm được có thể rải rác qua nhiều block. Khi truy vấn cần nhiều cột không nằm trong index, chi phí table access có thể tăng đáng kể.

Do đó, ngay cả khi skip scan tìm được ít entry, phần TABLE ACCESS BY INDEX ROWID vẫn có thể làm kế hoạch đắt.

### 6.5. Statistics và ước lượng cardinality

Optimizer dựa vào table/index statistics và có thể dùng histogram khi phân bố dữ liệu lệch. Statistics cũ hoặc thiếu có thể khiến optimizer ước lượng sai số dòng, từ đó chọn access path không phù hợp.

Kiểm tra metadata index:

~~~sql
SELECT
    index_name,
    blevel,
    leaf_blocks,
    distinct_keys,
    clustering_factor,
    num_rows,
    last_analyzed
FROM user_indexes
WHERE index_name = 'IX_LAB_SS_STATUS_CUSTOMER';
~~~

Kiểm tra thứ tự cột:

~~~sql
SELECT
    index_name,
    column_name,
    column_position
FROM user_ind_columns
WHERE index_name = 'IX_LAB_SS_STATUS_CUSTOMER'
ORDER BY column_position;
~~~

Các view trên mô tả statistics và cấu trúc index đã được thu thập. Không diễn giải một chỉ số riêng lẻ như BLEVEL hoặc CLUSTERING_FACTOR thành kết luận hiệu năng mà không xem workload và execution plan.

## 7. So sánh skip scan với các access path khác

### 7.1. Index range scan

Với index (ORDER_STATUS, CUSTOMER_ID), truy vấn:

~~~sql
SELECT order_id, customer_id
FROM lab_ss_orders
WHERE order_status = 'PAID'
  AND customer_id = 1234;
~~~

có điều kiện trên leading column và trailing column. Oracle có thể tìm một vùng khóa phù hợp bằng INDEX RANGE SCAN, không cần skip qua nhiều giá trị leading key.

### 7.2. Index skip scan

~~~sql
SELECT order_id, customer_id
FROM lab_ss_orders
WHERE customer_id = 1234;
~~~

Không có predicate trên ORDER_STATUS. Nếu optimizer thấy có lợi, nó có thể dùng INDEX SKIP SCAN để xét các vùng theo status.

### 7.3. Full table scan

~~~sql
SELECT order_id, customer_id, order_status, amount
FROM lab_ss_orders
WHERE customer_id BETWEEN 1 AND 9000;
~~~

Nếu phần lớn bảng thỏa điều kiện, đọc bảng tuần tự có thể rẻ hơn nhiều lần truy cập index và table theo ROWID. Full table scan không mặc nhiên là kế hoạch xấu; nó có thể là lựa chọn hợp lý nhất.

### 7.4. Index full scan và fast full index scan

INDEX FULL SCAN đọc toàn bộ index theo thứ tự khóa; INDEX FAST FULL SCAN đọc các block index theo cách tối ưu I/O, không bảo đảm thứ tự khóa như full scan thông thường. Hai operation này khác skip scan.

| Access path | Cách đọc khái quát | Khi thường gặp |
|---|---|---|
| INDEX RANGE SCAN | Đọc vùng khóa liên tục được xác định bởi điều kiện | Có predicate phù hợp với leading key |
| INDEX SKIP SCAN | Xét các vùng logic theo leading key rồi tìm trailing key | Bỏ qua leading key có NDV thấp |
| INDEX FULL SCAN | Đọc toàn index theo thứ tự khóa | Cần dữ liệu index hoặc thứ tự khóa |
| INDEX FAST FULL SCAN | Đọc toàn index theo kiểu scan nhanh, không theo thứ tự khóa | Index nhỏ/bao phủ và cần nhiều entry |
| TABLE ACCESS FULL | Đọc các block của bảng | Bảng nhỏ hoặc truy vấn trả nhiều dòng |

Không chọn kế hoạch chỉ dựa trên tên operation. Hãy xem actual rows, buffers, reads, thời gian và mức tải hệ thống.

## 8. Thay đổi thứ tự cột index có thể loại bỏ nhu cầu skip scan

Nếu workload thường xuyên truy vấn theo CUSTOMER_ID mà không lọc ORDER_STATUS, có thể thiết kế index theo thứ tự ngược lại:

~~~sql
CREATE INDEX ix_lab_ss_customer_status
ON lab_ss_orders (customer_id, order_status);
~~~

Với index mới, CUSTOMER_ID là leading column. Truy vấn:

~~~sql
SELECT order_id, customer_id, order_status, amount
FROM lab_ss_orders
WHERE customer_id = 1234;
~~~

có thể dùng INDEX RANGE SCAN trực tiếp theo CUSTOMER_ID.

So sánh ý nghĩa:

| Index | Truy vấn theo ORDER_STATUS | Truy vấn chỉ theo CUSTOMER_ID |
|---|---|---|
| (ORDER_STATUS, CUSTOMER_ID) | Leading-key access thuận lợi | Có thể dùng skip scan nếu cost phù hợp |
| (CUSTOMER_ID, ORDER_STATUS) | Có thể kém thuận lợi nếu không có CUSTOMER_ID | Leading-key access thuận lợi |

Không có thứ tự cột tối ưu cho mọi truy vấn. Hãy xem các predicate thường gặp, điều kiện JOIN, ORDER BY, GROUP BY, số dòng trả về và chi phí duy trì index khi INSERT/UPDATE/DELETE.

### 8.1. Không tạo cả hai index một cách máy móc

Hai index (ORDER_STATUS, CUSTOMER_ID) và (CUSTOMER_ID, ORDER_STATUS) có thể giúp các nhóm truy vấn khác nhau, nhưng mỗi index tiêu thụ storage và làm tăng chi phí DML. Chỉ giữ cả hai khi workload thực sự cần và lợi ích đo được lớn hơn chi phí.

### 8.2. Index skip scan không thay thế index đúng thứ tự

Nếu một cột được lọc thường xuyên và có tính chọn lọc cao, việc đặt nó ở leading position có thể tạo access path trực tiếp và dễ dự đoán hơn. Skip scan là một khả năng bổ sung để tận dụng composite index trong một số truy vấn, không phải lý do để đảo ngược mọi thứ tự cột.

## 9. Khi nào skip scan thường không hấp dẫn?

Một số tình huống:

- Leading column có quá nhiều giá trị phân biệt.
- Trailing predicate không chọn lọc, trả về phần lớn bảng.
- Bảng nhỏ, full table scan rất rẻ.
- Index lớn hoặc clustering factor khiến table lookup đắt.
- Truy vấn cần nhiều cột không có trong index và phải truy cập nhiều block bảng.
- Có index khác phù hợp hơn với leading key của truy vấn.
- Statistics không phản ánh đúng phân bố dữ liệu.
- Predicate dùng biểu thức hoặc chuyển đổi kiểu dữ liệu khiến index hiện có không được khai thác như mong đợi.

Ví dụ nếu ORDER_STATUS được thay bằng TRANSACTION_ID gần như duy nhất trong index (TRANSACTION_ID, CUSTOMER_ID), việc tìm CUSTOMER_ID mà không có TRANSACTION_ID có thể buộc Oracle xét quá nhiều giá trị leading key. Skip scan khi đó thường không hấp dẫn.

## 10. Predicate, biểu thức và điều kiện JOIN

Skip scan được cân nhắc dựa trên predicate mà optimizer có thể áp dụng vào các cột index. Kiểu dữ liệu và cách viết điều kiện có ảnh hưởng.

Ví dụ:

~~~sql
-- Predicate trực tiếp trên cột index.
WHERE customer_id = 1234
~~~

Khác với:

~~~sql
-- Hàm được áp dụng lên cột.
WHERE TO_CHAR(customer_id) = '1234'
~~~

Biểu thức thứ hai có thể không sử dụng index thông thường theo cùng cách, trừ khi có function-based index phù hợp hoặc optimizer biến đổi biểu thức. Tránh ép kiểu không cần thiết và dùng bind variable đúng kiểu dữ liệu.

Trong JOIN, optimizer cũng có thể chọn access path cho một bảng dựa trên giá trị được lấy từ bảng còn lại. Skip scan có thể xuất hiện trong kế hoạch phức tạp nếu chi phí phù hợp, nhưng cần đọc toàn bộ join order và predicate information thay vì chỉ xem một operation riêng.

## 11. Dùng hint INDEX_SS và NO_INDEX_SS

Oracle cung cấp hint để tác động đến việc sử dụng index skip scan:

~~~sql
SELECT /*+ INDEX_SS(o ix_lab_ss_status_customer) */
    o.order_id,
    o.customer_id,
    o.order_status
FROM lab_ss_orders o
WHERE o.customer_id = 1234;
~~~

Hint đối nghịch:

~~~sql
SELECT /*+ NO_INDEX_SS(o ix_lab_ss_status_customer) */
    o.order_id,
    o.customer_id,
    o.order_status
FROM lab_ss_orders o
WHERE o.customer_id = 1234;
~~~

INDEX_SS yêu cầu optimizer xem xét skip scan trên index được chỉ định; NO_INDEX_SS loại trừ skip scan trên index đó trong phạm vi hint. Hint không sửa cấu trúc index và không thay thế statistics.

### 11.1. Vì sao không nên ép hint ngay từ đầu?

Hint có thể làm kế hoạch không thích nghi với thay đổi dữ liệu. Ví dụ hôm nay ORDER_STATUS có ba giá trị, nhưng sau này ứng dụng thêm nhiều trạng thái hoặc phân bố CUSTOMER_ID thay đổi. Skip scan từng tốt có thể trở nên đắt hơn.

Quy trình nên là:

1. Chạy SQL không hint.
2. Xem execution plan và runtime statistics.
3. Xác định optimizer ước lượng sai ở đâu.
4. Kiểm tra statistics, index order và predicate.
5. Thử hint trong môi trường kiểm soát để so sánh.
6. Chỉ giữ hint khi có bằng chứng rõ ràng trên workload đại diện và có kế hoạch theo dõi.

## 12. Đọc predicate information

Trong output DBMS_XPLAN, phần Predicate Information giúp phân biệt điều kiện dùng để truy cập index và điều kiện chỉ lọc sau khi lấy dòng.

Ví dụ dạng minh họa:

~~~text
Predicate Information:
----------------------
  2 - access("O"."CUSTOMER_ID"=1234)
~~~

Tên operation và cách Oracle trình bày predicate có thể thay đổi theo phiên bản, kế hoạch và dạng SQL. Hãy xem phần access và filter:

- Access predicate giúp xác định vùng index/table được truy cập.
- Filter predicate loại bỏ dòng sau khi một row source đã được đọc.

Một điều kiện xuất hiện ở FILTER không nhất thiết có nghĩa index vô dụng; nhưng nó cho biết điều kiện đó không được dùng theo cùng cách để định vị vùng truy cập.

## 13. Vai trò của statistics và histogram

Optimizer cần biết dữ liệu phân bố như thế nào để ước lượng số dòng.

### 13.1. Table statistics

Table statistics có thể gồm:

- NUM_ROWS.
- BLOCKS.
- AVG_ROW_LEN.
- LAST_ANALYZED.

### 13.2. Column statistics

Column statistics có thể gồm:

- NUM_DISTINCT.
- NUM_NULLS.
- DENSITY.
- HISTOGRAM.

Với skip scan, số giá trị phân biệt của leading column là thông tin quan trọng. Độ chọn lọc của trailing predicate cũng ảnh hưởng ước lượng cardinality.

Có thể xem column statistics:

~~~sql
SELECT
    table_name,
    column_name,
    num_distinct,
    num_nulls,
    density,
    histogram,
    last_analyzed
FROM user_tab_col_statistics
WHERE table_name = 'LAB_SS_ORDERS'
  AND column_name IN ('ORDER_STATUS', 'CUSTOMER_ID')
ORDER BY column_name;
~~~

Histogram có thể giúp optimizer xử lý phân bố lệch, nhưng không phải cứ tạo histogram là kế hoạch tốt hơn. Histograms có thể ảnh hưởng ước lượng theo bind value và khiến các giá trị khác nhau có kế hoạch khác nhau; hãy dùng statistics gathering theo chính sách của hệ thống.

### 13.3. Statistics cũ

Nếu dữ liệu thay đổi lớn nhưng statistics không được cập nhật, optimizer có thể nghĩ leading column có số giá trị khác với thực tế hoặc ước lượng sai số dòng của CUSTOMER_ID. Khi điều tra kế hoạch bất thường:

1. Kiểm tra LAST_ANALYZED.
2. Kiểm tra NUM_ROWS và NUM_DISTINCT.
3. Kiểm tra histogram nếu có.
4. So sánh estimated rows với actual rows.
5. Thu thập lại statistics nếu thực sự cần.

Không chạy GATHER_TABLE_STATS trên production tùy tiện khi chưa hiểu chính sách statistics, locking, incremental stats và tác động đến kế hoạch SQL.

## 14. Skip scan và khả năng bao phủ của index

Index (ORDER_STATUS, CUSTOMER_ID) chứa hai cột đó cùng ROWID. Nếu truy vấn chỉ cần các cột được lưu trong index, Oracle có thể tránh table access:

~~~sql
SELECT order_status, customer_id
FROM lab_ss_orders
WHERE customer_id = 1234;
~~~

Nếu index skip scan được chọn, index có thể cung cấp đủ cột để trả kết quả. Đây là một covering access path.

Ngược lại:

~~~sql
SELECT order_id, order_status, customer_id, amount, order_date
FROM lab_ss_orders
WHERE customer_id = 1234;
~~~

cần thêm các cột không nằm trong index, nên thường phải truy cập bảng theo ROWID.

Không nên thêm quá nhiều cột vào index chỉ để biến mọi truy vấn thành index-only. Index lớn hơn sẽ tiêu thụ storage, tăng chi phí ghi và có thể làm giảm hiệu quả cache.

## 15. Index skip scan không phải index fast full scan

Hai khái niệm dễ nhầm:

- Skip scan dùng cấu trúc composite index để tìm theo cột không dẫn đầu bằng cách xét các giá trị leading key.
- Fast full index scan đọc toàn bộ index theo cách tối ưu I/O, không yêu cầu trả kết quả theo thứ tự khóa.

Skip scan là cách tìm một phần các entry phù hợp; fast full index scan đọc toàn index. Operation name trong execution plan là bằng chứng trực tiếp hơn so với việc chỉ nhìn thấy tên index trong plan.

## 16. Cách thiết kế index ghép theo workload

Trước khi tạo index (A, B), hãy xem:

1. Truy vấn thường lọc theo A hay B?
2. Có nhiều truy vấn lọc theo cả A và B không?
3. A có ít giá trị phân biệt hay rất nhiều?
4. B có chọn lọc cao không?
5. Có truy vấn cần ORDER BY A, B không?
6. Có truy vấn JOIN theo A hoặc B không?
7. Index có bao phủ các cột SELECT quan trọng không?
8. Chi phí thêm index lên INSERT/UPDATE/DELETE là bao nhiêu?

Ví dụ:

| Truy vấn thường gặp | Index có thể phù hợp để thử |
|---|---|
| WHERE order_status = :s | (order_status, customer_id) |
| WHERE order_status = :s AND customer_id = :c | (order_status, customer_id) |
| WHERE customer_id = :c | (customer_id, order_status) hoặc cân nhắc skip scan trên index ngược nếu leading NDV thấp |
| WHERE customer_id = :c ORDER BY order_date | Có thể cần (customer_id, order_date) tùy workload |
| Truy vấn đọc phần lớn bảng | Full table scan có thể phù hợp hơn index |

Các index trong bảng là gợi ý để đánh giá, không phải công thức tự động. Cần đo với dữ liệu, bind values và tải đồng thời đại diện.

## 17. Những hiểu lầm thường gặp

| Hiểu lầm | Thực tế |
|---|---|
| Index ghép chỉ dùng được khi có leading column | Skip scan có thể dùng index khi predicate chỉ nằm trên cột sau, nếu cost phù hợp |
| Leading column ít distinct thì chắc chắn skip scan | Còn phụ thuộc selectivity, kích thước index/bảng, clustering factor và statistics |
| Skip scan luôn nhanh hơn full table scan | Không; truy vấn trả nhiều dòng hoặc index lớn có thể khiến full scan rẻ hơn |
| Skip scan tạo index con vật lý | Không; các subindex là cách diễn giải logic theo leading key |
| Skip scan bảo đảm Oracle dùng index | Không; optimizer chọn theo cost |
| Dùng ORDER hoặc hint là chữa được index design | Không; cần thiết kế index theo workload và đo lường |
| Thấy tên index trong plan nghĩa là skip scan | Cần xem operation cụ thể, ví dụ INDEX SKIP SCAN |
| Thêm mọi cột SELECT vào index luôn tốt | Index phình to và làm tăng chi phí DML |

## 18. Bài tập thực hành

### Bài 1 — Nhận diện leading column

Cho index:

~~~sql
CREATE INDEX ix_a_b_c
ON some_table (a, b, c);
~~~

Xác định leading column và trailing columns. Giải thích truy vấn chỉ có WHERE b = :value có thể được cân nhắc skip scan trong điều kiện nào.

### Bài 2 — So sánh predicate

Với index (ORDER_STATUS, CUSTOMER_ID), so sánh ba truy vấn:

~~~sql
WHERE order_status = 'PAID'
~~~

~~~sql
WHERE order_status = 'PAID'
  AND customer_id = 1234
~~~

~~~sql
WHERE customer_id = 1234
~~~

**Gợi ý:** truy vấn thứ nhất và thứ hai có leading predicate; truy vấn thứ ba là tình huống có thể cân nhắc skip scan.

### Bài 3 — Quan sát NDV

Chạy COUNT(DISTINCT ORDER_STATUS) và COUNT(DISTINCT CUSTOMER_ID). Giải thích vì sao ORDER_STATUS phù hợp hơn để làm leading column trong ví dụ skip scan.

### Bài 4 — Đọc execution plan

Chạy EXPLAIN PLAN cho truy vấn CUSTOMER_ID = 1234. Tìm operation INDEX SKIP SCAN, TABLE ACCESS BY INDEX ROWID và predicate information.

### Bài 5 — So sánh với full table scan

Thử truy vấn có khoảng CUSTOMER_ID rộng. So sánh plan không hint và plan có NO_INDEX_SS hoặc FULL trong môi trường lab.

**Câu hỏi:** Vì sao full table scan có thể rẻ hơn khi điều kiện trả về nhiều dòng?

### Bài 6 — Thử index đảo thứ tự

Tạo index (CUSTOMER_ID, ORDER_STATUS). Dùng hint INDEX để xem access path khi lọc CUSTOMER_ID. So sánh với index (ORDER_STATUS, CUSTOMER_ID).

### Bài 7 — Statistics

Đọc USER_INDEXES và USER_TAB_COL_STATISTICS. Giải thích vai trò của DISTINCT_KEYS, CLUSTERING_FACTOR và NUM_DISTINCT.

### Bài 8 — Hint

So sánh INDEX_SS và NO_INDEX_SS. Kiểm tra execution plan để xác nhận hint có tác dụng.

**Câu hỏi:** Vì sao không nên giữ INDEX_SS chỉ vì nó làm plan xuất hiện operation INDEX SKIP SCAN?

### Bài 9 — Thiết kế theo workload

Một ứng dụng có:

- 60% truy vấn lọc theo CUSTOMER_ID.
- 25% truy vấn lọc theo ORDER_STATUS.
- 15% truy vấn lọc theo cả hai.

Đề xuất thứ tự cột index và giải thích liệu cần một hay hai index. Nêu chi phí DML và storage cần cân nhắc.

## 19. Quy trình đánh giá index skip scan

Khi thấy truy vấn không lọc leading column của một index ghép, hãy đi theo trình tự:

1. Xác định thứ tự cột thực tế trong index.
2. Xác định predicate đang lọc cột nào.
3. Kiểm tra NDV của leading column.
4. Kiểm tra selectivity/cardinality của predicate trailing column.
5. Kiểm tra table/index statistics và clustering factor.
6. Xem optimizer chọn access path nào.
7. So sánh estimated rows với actual rows.
8. Thử index order khác hoặc hint trong lab để hiểu các phương án.
9. Đo logical reads, physical reads, buffers và thời gian trên workload đại diện.
10. Chọn thiết kế index dựa trên tổng workload, không chỉ một câu SQL.

Sơ đồ:

~~~text
Truy vấn không có predicate leading column
                 |
                 v
Kiểm tra composite B-tree index
                 |
                 v
Leading column có NDV thấp?
          /              \
        Không             Có
         |                 |
         v                 v
Skip scan thường      Trailing predicate
kém hấp dẫn           có chọn lọc?
                           |
                     +-----+-----+
                     |           |
                    Không        Có
                     |           |
                     v           v
               Cân nhắc FTS   Kiểm tra index size,
               hoặc access    clustering factor,
               path khác      statistics và cost
                                  |
                                  v
                         Xem execution plan
                                  |
                                  v
                        Đo runtime thực tế
                                  |
                                  v
                       Chọn index theo workload
~~~

Index skip scan mở rộng khả năng sử dụng composite B-tree index khi truy vấn bỏ qua cột dẫn đầu. Nó thường đáng cân nhắc khi leading column có ít giá trị phân biệt và predicate trên trailing column chọn lọc tốt. Tuy nhiên, optimizer vẫn phải so sánh chi phí với index range scan, các index khác và full table scan. Hãy đọc operation trong execution plan, kiểm tra statistics và đo runtime trước khi thay đổi thứ tự cột hoặc ép hint. Thiết kế index nên phục vụ workload tổng thể, còn skip scan là một access path bổ sung khi cấu trúc dữ liệu phù hợp.
