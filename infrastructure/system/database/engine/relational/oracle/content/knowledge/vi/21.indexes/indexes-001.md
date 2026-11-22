# Cấu trúc B-tree và cơ chế tìm kiếm theo khóa trong Oracle

Khi ứng dụng tìm một khách hàng theo mã, lấy các đơn hàng trong một khoảng ngày hoặc nối hai bảng theo khóa, Oracle cần tìm những hàng phù hợp trong dữ liệu. Nếu phải đọc toàn bộ bảng mỗi lần, chi phí có thể lớn khi bảng chứa hàng triệu dòng. **B-tree index** là cấu trúc chỉ mục phổ biến của Oracle Database: nó sắp xếp khóa, tổ chức các khối chỉ mục thành cây cân bằng và lưu ROWID để dẫn đến hàng trong bảng.

Điểm quan trọng là index không phải một bản sao đầy đủ của bảng. Nó là một cấu trúc phụ được duy trì cùng dữ liệu, chứa giá trị khóa và thông tin định vị hàng. Khi truy vấn phù hợp với thứ tự khóa và có tính chọn lọc tốt, Oracle có thể đi từ root block qua branch blocks đến leaf block, sau đó dùng ROWID để đọc các block dữ liệu. Với một khoảng khóa, Oracle có thể đi đến leaf đầu tiên phù hợp rồi tiếp tục duyệt các leaf kế tiếp theo thứ tự.

Bài học thuộc nhóm **Chỉ mục** của Database Engine Relational Oracle. Nội dung tập trung vào cấu trúc B-tree, cách tìm kiếm khóa, cách đọc leaf entries và ROWID, thứ tự của composite index, các access path trong execution plan, clustering factor, NULL, tác động của DML và thống kê optimizer.

Sau bài này, bạn có thể:

- Mô tả vai trò của root, branch và leaf blocks trong B-tree index.
- Giải thích vì sao cây cân bằng giúp tìm khóa với ít lần đọc block hơn so với quét toàn bộ bảng.
- Phân biệt index unique scan, range scan, full scan, fast full scan và skip scan.
- Hiểu cách Oracle dùng ROWID để truy cập hàng trong table blocks.
- Chọn thứ tự cột cho composite index dựa trên predicate và thứ tự khóa.
- Giải thích selectivity, clustering factor và chi phí table access by ROWID.
- Nhận biết giới hạn của B-tree index với NULL và biểu thức trên cột.
- Hiểu index leaf split, việc duy trì index khi INSERT/UPDATE/DELETE và chi phí của nhiều index.
- Đọc execution plan để biết index có thực sự được dùng và có đem lại lợi ích hay không.
- Kiểm tra index metadata và thống kê bằng các data dictionary views.

> **Phạm vi ví dụ:** Cú pháp và hành vi minh họa theo Oracle Database 19c. Các bảng có hậu tố _LAB dành cho schema thực hành riêng. Kế hoạch thực thi phụ thuộc dữ liệu, thống kê, bind values, phiên bản và cấu hình; không có một access path luôn tốt nhất cho mọi bảng.

## 1. Vì sao cần index?

Giả sử bảng ORDERS có vài triệu dòng và ứng dụng thường chạy:

~~~sql
SELECT order_id, customer_id, order_date, status
FROM orders
WHERE order_id = :order_id;
~~~

Nếu không có access path phù hợp, Oracle có thể phải đọc nhiều block của bảng để tìm order_id cần thiết. Một B-tree index trên ORDER_ID giúp Oracle tìm khóa trong cấu trúc đã sắp xếp và lấy ROWID của hàng tương ứng.

### 1.1. Table scan và index lookup

~~~text
TABLE ACCESS FULL
  Doc cac block cua bang
  Kiem tra predicate tren cac hang
  Tra cac hang phu hop

INDEX ACCESS
  Tim khoa trong B-tree
  Lay ROWID tu leaf entry
  Doc table block chua hang
  Tra cac hang phu hop
~~~

Index có lợi khi số hàng cần tìm nhỏ so với lượng dữ liệu phải đọc. Nếu truy vấn cần phần lớn bảng, đọc tuần tự toàn bảng có thể rẻ hơn việc đi qua index rồi nhảy đến rất nhiều table blocks.

### 1.2. Index là cấu trúc phụ cần được duy trì

Một bảng có thể có nhiều index. Khi INSERT, DELETE hoặc UPDATE cột khóa, Oracle phải cập nhật các index liên quan. Index giúp một số truy vấn đọc nhanh hơn nhưng tăng:

- Dung lượng lưu trữ.
- Công việc ghi khi DML.
- Redo và undo liên quan đến thay đổi.
- Chi phí bảo trì, backup và quản trị.

Vì vậy, không nên tạo index trên mọi cột chỉ vì cột xuất hiện trong WHERE. Hãy tạo index cho workload thực tế và đo hiệu quả bằng execution plan/runtime statistics.

## 2. B-tree index là cây tìm kiếm nhiều nhánh cân bằng

B-tree trong Oracle là cấu trúc cây tìm kiếm nhiều nhánh, được tổ chức theo block của database. Nó không phải cây nhị phân đơn giản có tối đa hai con cho mỗi node. Một block branch có thể chứa nhiều khóa phân cách và nhiều con trỏ đến block cấp dưới.

### 2.1. Ba loại block khái niệm

~~~text
                   ROOT BLOCK
                 /      |      \
                v       v       v
          BRANCH 1  BRANCH 2  BRANCH 3
            /  \       /  \      /  \
           v    v     v    v    v    v
         LEAF  LEAF  LEAF LEAF LEAF LEAF
           |     |     |    |    |    |
           +-----+-----+----+----+----+
             leaf blocks linked in key order
~~~

- **Root block:** điểm bắt đầu của cây. Nó chứa thông tin khóa phân cách và con trỏ đến branch hoặc leaf blocks bên dưới.
- **Branch block:** khối trung gian dẫn hướng tìm kiếm. Nó chứa các khóa phân cách và địa chỉ block con.
- **Leaf block:** tầng lá chứa các index entries với khóa và ROWID (hoặc thông tin tương ứng cho index entry).

Với index rất nhỏ, root có thể đồng thời là leaf level; không phải index nào cũng có đủ nhiều tầng root, branch và leaf riêng biệt.

### 2.2. Cây cân bằng

Các leaf blocks nằm cùng một mức sâu của cây. Khi dữ liệu tăng hoặc thay đổi, Oracle duy trì cấu trúc để tìm kiếm vẫn đi qua số mức cây tương đối nhỏ. Chiều cao cây thường tăng chậm so với số entry vì mỗi branch block có thể dẫn đến nhiều block con.

Không nên nhầm B-tree với một danh sách đã sắp xếp duy nhất. Cấu trúc được chia thành nhiều block; root/branch hướng đến leaf phù hợp, còn các leaf chứa dải khóa và liên kết theo thứ tự.

### 2.3. Khóa phân cách và con trỏ block

Một branch block chứa các giá trị khóa giúp Oracle chọn nhánh cần đi xuống. Khi tìm một giá trị, Oracle so sánh khóa tìm kiếm với các giá trị phân cách, chọn child pointer phù hợp rồi tiếp tục ở block con. Quá trình lặp cho đến leaf level.

Ví dụ minh họa, giả sử khóa số được chia thành các dải:

~~~text
Root:
  <  1000  -> Branch A
  >= 1000  -> Branch B

Branch B:
  <  1500  -> Leaf B1
  >= 1500  -> Leaf B2

Leaf B2:
  1500 -> ROWID X
  1501 -> ROWID Y
  1503 -> ROWID Z
~~~

Các giá trị trên chỉ minh họa điều hướng, không mô tả chính xác cách Oracle mã hóa branch key hoặc phân chia block trong mọi index.

## 3. Leaf entries: khóa và ROWID

### 3.1. Leaf entry chứa gì?

Với một B-tree index thông thường, leaf entry đại diện cho giá trị khóa và ROWID của hàng trong bảng:

~~~text
INDEX LEAF ENTRY
+--------------------+--------------------------+
| Indexed key value  | ROWID                    |
+--------------------+--------------------------+
| 1001               | file/block/row location  |
| 1002               | file/block/row location  |
| 1002               | file/block/row location  |
| 1005               | file/block/row location  |
+--------------------+--------------------------+
~~~

Nếu nhiều hàng có cùng giá trị khóa trong nonunique index, leaf level có thể chứa nhiều entry tương ứng với cùng khóa và các ROWID khác nhau. Với unique index, các giá trị khóa không NULL phải duy nhất theo quy tắc của index/constraint.

### 3.2. ROWID là địa chỉ hàng

ROWID là pseudocolumn Oracle cung cấp để định vị hàng. Với heap-organized table thông thường, extended ROWID mã hóa thông tin như data object number, relative file number, block number và row slot. Nó cho phép Oracle xác định table block và vị trí hàng trong block.

Ví dụ:

~~~sql
SELECT
    employee_id,
    ROWID
FROM employee_data_lab
WHERE employee_id = 101;
~~~

ROWID không phải khóa nghiệp vụ. Không dùng ROWID làm mã định danh bền vững trong ứng dụng vì thao tác di chuyển hàng, shrink/move table, partition maintenance hoặc tái tổ chức dữ liệu có thể làm ROWID thay đổi.

### 3.3. Index lookup thường cần thêm table access

~~~text
1. INDEX RANGE/UNIQUE SCAN
       |
       v
   Lay ROWID tu leaf
       |
       v
2. TABLE ACCESS BY INDEX ROWID
       |
       v
   Doc cot khong nam trong index
~~~

Ví dụ index chỉ chứa EMPLOYEE_ID nhưng truy vấn còn lấy FULL_NAME:

~~~sql
SELECT employee_id, full_name
FROM employee_data_lab
WHERE employee_id = 101;
~~~

Oracle tìm EMPLOYEE_ID trong index, lấy ROWID, sau đó đọc table block để lấy FULL_NAME. Execution plan có thể hiển thị INDEX UNIQUE SCAN rồi TABLE ACCESS BY INDEX ROWID.

### 3.4. Index-only access

Nếu tất cả cột cần trả về đã có trong index, Oracle có thể lấy dữ liệu từ index mà không cần truy cập table block cho từng hàng:

~~~sql
SELECT employee_id
FROM employee_data_lab
WHERE employee_id = 101;
~~~

Với primary-key index phù hợp, truy vấn có thể chỉ cần index access. Tuy nhiên, việc optimizer chọn plan cụ thể vẫn phụ thuộc thống kê và chi phí. Một số query cần xác nhận tính nhất quán của dữ liệu hoặc truy cập thêm thông tin có thể cần thao tác khác.

Không nên thêm thật nhiều cột vào index chỉ để biến một truy vấn thành index-only nếu chi phí tăng về storage và DML lớn hơn lợi ích đọc.

## 4. Cách Oracle tìm kiếm một khóa

### 4.1. Tìm kiếm bằng equality

Với index trên EMPLOYEE_ID:

~~~sql
SELECT employee_id, full_name
FROM employee_data_lab
WHERE employee_id = 101;
~~~

Quá trình khái quát:

1. Đọc root block.
2. So sánh 101 với khóa phân cách và chọn child block.
3. Đi qua các branch blocks cần thiết.
4. Tìm leaf entry có khóa 101.
5. Lấy ROWID.
6. Đọc table block nếu còn cột cần lấy ngoài index.

Nếu index unique và điều kiện equality bao phủ toàn bộ unique key, optimizer có thể chọn INDEX UNIQUE SCAN. Nếu index không unique, hoặc equality chỉ bao phủ một phần composite key, có thể dùng INDEX RANGE SCAN.

### 4.2. Tìm kiếm theo khoảng

~~~sql
SELECT order_id, order_date, status
FROM orders
WHERE order_date >= DATE '2026-01-01'
  AND order_date <  DATE '2026-02-01';
~~~

Với index trên ORDER_DATE, Oracle có thể:

1. Tìm leaf entry đầu tiên có ORDER_DATE lớn hơn hoặc bằng ngày bắt đầu.
2. Đọc các leaf entries tiếp theo theo thứ tự khóa.
3. Dừng khi vượt biên ngày kết thúc.
4. Dùng ROWID để lấy các hàng phù hợp nếu cần.

Các leaf blocks được liên kết theo thứ tự khóa, giúp quét một khoảng liên tiếp mà không phải quay lại root cho từng entry.

### 4.3. Tìm kiếm prefix

Với composite index (A, B, C), predicate có điều kiện trên A hoặc A và B thường có thể định vị một vùng khóa theo leading prefix:

~~~sql
WHERE a = :a

WHERE a = :a
  AND b = :b

WHERE a = :a
  AND b >= :b_start
~~~

Khi điều kiện không có leading column A, Oracle thường không thể dùng index như một range lookup trực tiếp theo B. Có thể có các access path khác như index skip scan, nhưng cần dữ liệu và thống kê phù hợp.

### 4.4. Vì sao tìm kiếm thường ít lần đọc block?

Index có nhiều entry trong mỗi block. Một lần đọc branch block có thể chọn một trong nhiều child blocks. Vì vậy, dù bảng có rất nhiều hàng, số tầng cây thường không tăng tuyến tính theo số entry.

Không nên đưa ra một số tầng cố định cho mọi index. Block size, số entry, độ dài khóa, compression, mức đầy block và lịch sử DML ảnh hưởng fan-out và chiều cao thực tế.

## 5. Các loại B-tree index scan trong execution plan

Tên operation trong execution plan cho biết Oracle dùng index theo cách nào. Không phải operation nào có chữ INDEX cũng đồng nghĩa chỉ đọc một hàng.

### 5.1. INDEX UNIQUE SCAN

Tìm đúng một giá trị khóa duy nhất:

~~~sql
SELECT employee_id
FROM employee_data_lab
WHERE employee_id = :employee_id;
~~~

Nếu EMPLOYEE_ID là primary key và predicate equality xác định đầy đủ key, Oracle có thể dùng INDEX UNIQUE SCAN. Operation này tìm một entry duy nhất theo key.

### 5.2. INDEX RANGE SCAN

Dùng cho một dải khóa hoặc nhiều entry cùng giá trị:

~~~sql
SELECT order_id
FROM orders
WHERE customer_id = :customer_id;
~~~

Nếu nhiều đơn hàng cùng customer_id, Oracle cần đọc một vùng leaf entries tương ứng. Range scan cũng phù hợp với điều kiện lớn hơn/nhỏ hơn, BETWEEN hoặc prefix của composite index.

### 5.3. INDEX RANGE SCAN DESCENDING

Oracle có thể quét leaf entries theo chiều giảm dần khi truy vấn yêu cầu thứ tự giảm và index/order phù hợp:

~~~sql
SELECT order_id, order_date
FROM orders
WHERE customer_id = :customer_id
ORDER BY order_date DESC;
~~~

Khả năng tránh sort phụ thuộc thứ tự cột, chiều ASC/DESC trong index, predicate và các cột bổ sung trong ORDER BY. Không giả định mọi index range scan đều tự đáp ứng mọi ORDER BY.

### 5.4. INDEX FULL SCAN

INDEX FULL SCAN đọc toàn bộ leaf entries theo thứ tự index. Nó có thể hữu ích khi:

- Truy vấn cần phần lớn hoặc toàn bộ key trong index.
- Index chứa tất cả cột cần trả.
- Thứ tự index đáp ứng ORDER BY.
- Optimizer ước lượng đọc index rẻ hơn đọc bảng.

Full scan ở đây là toàn bộ index, không phải toàn bộ table.

### 5.5. INDEX FAST FULL SCAN

INDEX FAST FULL SCAN đọc các block của index theo cách tương tự full scan nhiều block, không bảo đảm trả hàng theo thứ tự khóa. Nó có thể dùng khi index chứa đủ các cột cần thiết và đọc index rẻ hơn đọc bảng.

Phân biệt:

| Operation | Đọc phạm vi | Có đảm bảo thứ tự key? |
| --- | --- | --- |
| INDEX RANGE SCAN | Một vùng khóa | Theo thứ tự index trong phạm vi scan |
| INDEX UNIQUE SCAN | Một khóa duy nhất | Không phải scan tập lớn |
| INDEX FULL SCAN | Toàn bộ leaf theo thứ tự | Có thứ tự index |
| INDEX FAST FULL SCAN | Toàn bộ index theo block/multiblock | Không bảo đảm thứ tự key |

### 5.6. INDEX SKIP SCAN

Skip scan có thể hữu ích khi composite index có nhiều cột nhưng truy vấn không lọc cột leading. Oracle xem các giá trị distinct của leading column như các nhóm con và dò phần tiếp theo của index.

Ví dụ index (GENDER, DEPARTMENT_ID), trong đó GENDER có rất ít giá trị distinct:

~~~sql
SELECT employee_id
FROM employee_data_lab
WHERE department_id = :department_id;
~~~

Oracle có thể cân nhắc INDEX SKIP SCAN nếu số giá trị distinct của GENDER thấp và chi phí ước lượng phù hợp. Đây không phải thay thế phổ quát cho index bắt đầu bằng DEPARTMENT_ID. Nếu truy vấn theo department_id là workload quan trọng và selectivity tốt, index (DEPARTMENT_ID, ...) thường là thiết kế trực tiếp hơn.

### 5.7. INDEX JOIN SCAN

Trong một số trường hợp, Oracle có thể kết hợp nhiều index để lấy đủ cột truy vấn mà không cần truy cập bảng, thông qua index join. Đây là access path chuyên biệt; không nên xây nhiều index chồng lặp chỉ để mong optimizer chọn nó.

### 5.8. Không có access path nào luôn tốt nhất

Một truy vấn lấy một khách hàng trong bảng lớn có thể rất phù hợp với index range scan. Một báo cáo lấy 80% số hàng có thể phù hợp với full table scan. Cần xét số hàng thực tế, số block phải đọc, clustering factor, cột trả về, sort, parallelism và chi phí tổng thể.

## 6. Composite B-tree index và thứ tự cột

Composite index chứa nhiều cột theo một thứ tự xác định. Thứ tự đó là một phần quan trọng của cấu trúc tìm kiếm.

### 6.1. Ví dụ index (CUSTOMER_ID, ORDER_DATE)

~~~sql
CREATE INDEX ix_orders_customer_date_lab
ON orders_lab(customer_id, order_date);
~~~

Các khóa được sắp theo CUSTOMER_ID trước, rồi ORDER_DATE trong mỗi nhóm CUSTOMER_ID:

~~~text
(CUSTOMER_ID, ORDER_DATE)

(10, 2026-01-03)
(10, 2026-01-12)
(10, 2026-02-01)
(20, 2026-01-05)
(20, 2026-03-09)
(30, 2026-02-15)
~~~

Truy vấn phù hợp:

~~~sql
SELECT order_id, order_date
FROM orders_lab
WHERE customer_id = :customer_id
  AND order_date >= :start_date
  AND order_date < :end_date;
~~~

Oracle có thể định vị nhóm customer_id rồi quét dải order_date bên trong nhóm đó.

### 6.2. Leading column

Với index (CUSTOMER_ID, ORDER_DATE):

| Predicate | Cơ hội dùng index |
| --- | --- |
| CUSTOMER_ID = :c | Dùng leading prefix |
| CUSTOMER_ID = :c AND ORDER_DATE >= :d | Dùng prefix và range |
| CUSTOMER_ID = :c AND ORDER_DATE BETWEEN ... | Dùng prefix và range |
| ORDER_DATE >= :d, không có CUSTOMER_ID | Không phải range lookup trực tiếp theo leading prefix; có thể cân nhắc skip scan hoặc access path khác |

Không nên nói cột thứ hai “không bao giờ dùng được”. Skip scan, full index scan, fast full scan hoặc các biến đổi khác có thể làm index được sử dụng. Nhưng nếu workload chủ yếu lọc ORDER_DATE độc lập, index bắt đầu bằng ORDER_DATE thường phù hợp hơn.

### 6.3. Thứ tự cột không chỉ dựa vào selectivity riêng lẻ

Khi chọn thứ tự cột, hãy xem:

- Các predicate thường xuất hiện cùng nhau.
- Equality predicates và range predicates.
- Truy vấn cần ORDER BY nào.
- Số giá trị distinct và phân bố dữ liệu.
- Có cần index hỗ trợ foreign key hoặc join không.
- Index có được dùng bởi nhiều câu SQL khác nhau không.
- Chi phí DML và dung lượng.

Không áp dụng máy móc quy tắc “cột chọn lọc nhất luôn đứng đầu”. Leading column cần phục vụ access patterns quan trọng; thứ tự phù hợp phụ thuộc tổ hợp predicate và cách optimizer truy cập.

### 6.4. Equality trước range thường là một điểm khởi đầu hữu ích

Với truy vấn:

~~~sql
WHERE customer_id = :customer_id
  AND order_date >= :start_date
  AND order_date < :end_date
~~~

Index (CUSTOMER_ID, ORDER_DATE) thường là ứng viên tự nhiên: equality trên leading column, range trên cột tiếp theo. Nhưng nếu các truy vấn khác lọc date độc lập, index khác có thể cần thiết. Hãy thiết kế theo workload tổng thể, không chỉ một câu SQL.

### 6.5. Index có chiều DESC

Oracle cho phép định nghĩa thứ tự ASC/DESC cho các cột index:

~~~sql
CREATE INDEX ix_orders_customer_date_desc_lab
ON orders_lab(customer_id, order_date DESC);
~~~

Index descending có thể hỗ trợ truy vấn lấy ngày mới nhất theo customer khi các điều kiện khác phù hợp. Tuy nhiên, Oracle cũng có thể quét một index theo chiều ngược trong nhiều trường hợp. Hãy kiểm tra plan trước khi tạo index DESC chỉ vì câu SQL có ORDER BY DESC.

## 7. Selectivity và cardinality

### 7.1. Selectivity là mức độ lọc của predicate

Selectivity mô tả tỷ lệ dữ liệu được giữ lại sau predicate. Một điều kiện chỉ khớp 10 hàng trong bảng 1 triệu hàng có selectivity rất cao theo nghĩa lọc mạnh (tỷ lệ kết quả nhỏ). Một điều kiện khớp 800.000 hàng trong 1 triệu hàng lọc yếu.

Ví dụ:

~~~sql
WHERE employee_id = 101
~~~

Nếu employee_id là primary key, kết quả tối đa một hàng.

~~~sql
WHERE employment_status = 'ACTIVE'
~~~

Nếu 95% nhân viên đang ACTIVE, predicate không lọc nhiều. Full table scan có thể rẻ hơn index lookup cộng hàng trăm nghìn table block visits.

### 7.2. Cardinality là số hàng ước lượng hoặc thực tế

Optimizer ước lượng số hàng sau mỗi operation để so sánh kế hoạch. Trong execution plan:

- E-Rows: số hàng ước lượng.
- A-Rows: số hàng thực tế khi có runtime statistics.

Nếu ước lượng sai xa thực tế, optimizer có thể chọn join method, join order hoặc access path không phù hợp.

### 7.3. Histogram và phân bố lệch

Một cột có thể có phân bố lệch (skew). Ví dụ 95% hàng có STATUS='ACTIVE' nhưng chỉ 5% là 'CLOSED'. Một thống kê trung bình đơn giản có thể không mô tả tốt mọi giá trị. Histogram có thể giúp optimizer ước lượng selectivity theo giá trị cụ thể khi phù hợp.

Không tự tạo histogram trên mọi cột. Statistics strategy phải dựa trên workload, bind usage và DBA policy.

## 8. Clustering factor: index tìm được hàng nhưng table block nằm rải rác

Một index có thể tìm được ROWID rất nhanh, nhưng bước đọc table block có thể tốn kém nếu các hàng theo thứ tự khóa nằm rải rác khắp bảng.

### 8.1. Clustering factor đo điều gì?

Clustering factor mô tả mức độ tương quan giữa thứ tự khóa trong index và thứ tự vật lý các hàng trong table blocks. Khái niệm đơn giản:

- Clustering factor thấp, gần số table blocks: các hàng có khóa gần nhau thường nằm gần nhau trong bảng.
- Clustering factor cao, gần số hàng: các hàng có khóa gần nhau thường nằm ở nhiều table blocks khác nhau.

Đây là thống kê dùng để ước lượng chi phí table access by ROWID, không phải một thước đo trực tiếp về chất lượng nghiệp vụ hoặc độ phân mảnh tổng thể.

### 8.2. Ví dụ trực quan

Trường hợp dữ liệu được tổ chức tương quan với khóa:

~~~text
INDEX KEY ORDER:  1  2  3  4  5  6
ROWID BLOCK:      A  A  A  B  B  B
~~~

Trường hợp hàng nằm rải rác:

~~~text
INDEX KEY ORDER:  1  2  3  4  5  6
ROWID BLOCK:      A  Z  C  X  B  Y
~~~

Ở trường hợp đầu, nhiều ROWID liên tiếp có thể đọc từ một vài table blocks. Ở trường hợp sau, Oracle có thể phải truy cập nhiều block khác nhau.

### 8.3. Tác động đến quyết định dùng index

Nếu predicate trả về rất ít hàng, index vẫn có thể tốt ngay cả khi clustering factor cao. Nếu predicate trả về nhiều hàng và mỗi ROWID dẫn đến block khác nhau, full table scan có thể rẻ hơn.

Vì vậy, “có index” không đủ để kết luận truy vấn nhanh. Hãy xem cả selectivity, clustering factor, số table blocks và số hàng cần lấy.

### 8.4. Xem clustering factor

~~~sql
SELECT
    index_name,
    blevel,
    leaf_blocks,
    distinct_keys,
    num_rows,
    clustering_factor
FROM user_indexes
WHERE table_name = 'ORDERS_LAB'
ORDER BY index_name;
~~~

Tên bảng trong data dictionary thường được lưu chữ hoa nếu không tạo bằng quoted identifier. Thay ORDERS_LAB bằng tên bảng thực tế.

## 9. NULL và B-tree index

### 9.1. B-tree index một cột không lưu entry khi giá trị là NULL

Với B-tree index thông thường trên một cột, hàng có giá trị cột đó là NULL không tạo index entry. Vì vậy truy vấn:

~~~sql
SELECT *
FROM employee_data_lab
WHERE work_email IS NULL;
~~~

thường không thể dùng một B-tree index chỉ trên WORK_EMAIL để tìm tất cả hàng NULL, vì các hàng NULL không có entry trong index đó.

### 9.2. Composite index có thể chứa entry khi một cột NULL

Với index nhiều cột, nếu ít nhất một cột trong key có giá trị non-NULL, index entry có thể tồn tại dù một cột khác là NULL. Ví dụ index (DEPARTMENT_ID, WORK_EMAIL) có thể có entry cho (10, NULL), vì toàn bộ composite key không phải NULL.

Do đó, một predicate IS NULL trên cột thứ hai có thể được hỗ trợ trong một số composite index khi leading column được ràng buộc phù hợp. Hãy kiểm tra plan và dữ liệu thực tế.

### 9.3. Function-based index để xử lý NULL

Nếu workload thường xuyên tìm các giá trị NULL ở một cột đơn, có thể cân nhắc function-based index với biểu thức biến NULL thành một giá trị sentinel phù hợp:

~~~sql
CREATE INDEX ix_employee_email_nvl_lab
ON employee_data_lab(NVL(work_email, 'NO_EMAIL'));
~~~

Truy vấn phải dùng biểu thức tương thích:

~~~sql
SELECT employee_id
FROM employee_data_lab
WHERE NVL(work_email, 'NO_EMAIL') = 'NO_EMAIL';
~~~

Sentinel phải được chọn sao cho không thể nhầm với dữ liệu hợp lệ, và datatype/collation phải phù hợp. Function-based index tăng chi phí DML và cần thống kê thích hợp. Không tạo index kiểu này nếu truy vấn NULL rất hiếm.

### 9.4. Unique index và NULL

NULL không được so sánh như một giá trị thông thường trong SQL. Quy tắc uniqueness có các trường hợp đặc biệt khi key chứa NULL; không nên dựa vào suy đoán rằng NULL luôn là một giá trị duy nhất hoặc luôn bị loại khỏi mọi index. Hãy xem định nghĩa unique constraint/index, số cột key và semantics Oracle cho trường hợp cụ thể. Với khóa nghiệp vụ bắt buộc có giá trị, khai báo NOT NULL cùng UNIQUE/PRIMARY KEY rõ ràng.

## 10. Predicate có thể làm index khó sử dụng

### 10.1. Hàm trên cột

Index thông thường trên ORDER_DATE được tổ chức theo giá trị ORDER_DATE. Điều kiện:

~~~sql
WHERE TRUNC(order_date) = DATE '2026-01-15'
~~~

đặt hàm lên cột nên không tương đương trực tiếp với một range lookup trên index thông thường.

Có thể viết lại thành khoảng nửa mở:

~~~sql
WHERE order_date >= DATE '2026-01-15'
  AND order_date <  DATE '2026-01-16'
~~~

Hoặc tạo function-based index nếu workload và thiết kế yêu cầu biểu thức TRUNC:

~~~sql
CREATE INDEX ix_orders_order_day_lab
ON orders_lab(TRUNC(order_date));
~~~

### 10.2. Chuyển cột thành chuỗi

Không nên lọc tháng bằng:

~~~sql
WHERE TO_CHAR(order_date, 'YYYY-MM') = '2026-01'
~~~

khi có thể dùng range predicate:

~~~sql
WHERE order_date >= DATE '2026-01-01'
  AND order_date <  DATE '2026-02-01'
~~~

Range predicate diễn đạt rõ biên thời gian, tránh phụ thuộc format/NLS và thường dễ dùng index range access trên cột gốc.

### 10.3. Implicit conversion

So sánh cột NUMBER với chuỗi hoặc cột DATE với chuỗi không định dạng rõ có thể khiến Oracle phải chuyển kiểu. Nếu conversion được áp lên cột index, access path có thể bị ảnh hưởng; conversion còn có thể phụ thuộc NLS và gây lỗi dữ liệu.

Hãy bind đúng datatype:

~~~sql
-- JDBC: bind NUMBER bang setLong/setBigDecimal,
-- DATE/TIMESTAMP bang setDate/setTimestamp phu hop.
~~~

Không nối chuỗi để tạo điều kiện SQL từ input người dùng.

### 10.4. LIKE và leading wildcard

Với index B-tree trên LAST_NAME:

~~~sql
WHERE last_name LIKE 'Ng%'
~~~

có thể hỗ trợ range scan vì pattern có prefix cố định. Nhưng:

~~~sql
WHERE last_name LIKE '%Ng'
~~~

không có leading prefix xác định, nên B-tree thông thường khó dùng để định vị một khoảng khóa liên tục. Có thể cần full scan, Oracle Text hoặc một thiết kế tìm kiếm khác tùy yêu cầu.

## 11. DML và bảo trì B-tree index

Index không phải cấu trúc chỉ đọc. Oracle duy trì index đồng bộ với thay đổi bảng trong transaction.

### 11.1. INSERT

Khi thêm một hàng:

1. Oracle ghi hàng vào table block.
2. Tạo entry trong từng index liên quan, nếu key đủ điều kiện được lưu.
3. Cập nhật cấu trúc leaf/branch nếu cần.
4. Ghi undo/redo phù hợp cho recovery và rollback.

Nếu index leaf block còn chỗ, entry được chèn vào vị trí theo thứ tự khóa. Nếu không đủ chỗ, Oracle có thể thực hiện block split.

### 11.2. DELETE

DELETE một hàng phải loại bỏ hoặc đánh dấu entry tương ứng trong các index liên quan theo cơ chế quản lý index. Việc xóa nhiều hàng có thể tạo công việc bảo trì đáng kể và không nhất thiết làm segment co nhỏ ngay.

### 11.3. UPDATE cột không thuộc index

Nếu UPDATE chỉ thay đổi một cột không nằm trong index key hoặc biểu thức index, index đó thường không cần thay đổi entry. Tuy nhiên, table block vẫn thay đổi và transaction vẫn cần undo/redo.

### 11.4. UPDATE cột thuộc index

Nếu giá trị khóa thay đổi, Oracle phải cập nhật vị trí entry trong index: về bản chất loại bỏ key cũ và tạo key mới. Điều này làm tăng chi phí DML so với cập nhật cột không được index.

### 11.5. Leaf block split

Khi leaf block không còn chỗ để chèn một entry mới theo thứ tự khóa, Oracle có thể split block, phân phối các entry sang block mới và cập nhật cấu trúc cây khi cần.

~~~text
TRUOC SPLIT
Leaf A: [10, 20, 30, 40, 50]  (gan day)

CHEN key 35

SAU SPLIT (MINH HOA)
Leaf A: [10, 20, 30]
Leaf B: [35, 40, 50]
       |
       +-- branch/root duoc cap nhat neu can
~~~

Hình trên chỉ minh họa ý tưởng phân chia; số entry, vị trí phân chia và cập nhật branch phụ thuộc block layout và trạng thái thực tế.

### 11.6. Vì sao nhiều index làm DML chậm hơn?

Một INSERT vào bảng có 8 index có thể cần cập nhật tối đa 8 cấu trúc index, ngoài table block. UPDATE một cột tham gia nhiều index cũng có thể tạo thêm công việc. Vì vậy, mỗi index cần có lý do workload cụ thể.

### 11.7. Monotonically increasing keys

Index trên khóa tăng dần như sequence ID có thể khiến các INSERT mới tập trung ở vùng leaf phía cuối theo thứ tự khóa. Đây là đặc điểm có thể tạo contention ở leaf block cuối trong workload insert đồng thời rất cao. Reverse key index hoặc thiết kế partitioning có thể giúp một số workload, nhưng có trade-off: reverse key làm mất khả năng range scan theo thứ tự khóa thông thường. Không áp dụng chỉ vì thấy ID tăng dần; phải đo contention và query patterns.

## 12. Index compression và các biến thể

### 12.1. Prefix compression

Composite index có thể có nhiều entry lặp lại giá trị leading prefix. Index key compression có thể giảm lưu trữ bằng cách lưu prefix lặp hiệu quả hơn trong block:

~~~sql
CREATE INDEX ix_orders_region_customer_lab
ON orders_lab(region, customer_id)
COMPRESS 1;
~~~

Ví dụ này minh họa nén một cột prefix. Hiệu quả phụ thuộc số lượng giá trị lặp, độ dài key, pattern truy cập và chi phí CPU. Compression có thể giảm block count/I/O nhưng cũng có chi phí xử lý; hãy đo trên dữ liệu thực.

### 12.2. Reverse key index

Reverse key index đảo thứ tự byte của key để phân tán các giá trị tăng tuần tự trong leaf blocks. Nó có thể giảm contention ở điểm chèn cuối trong một số workload insert-heavy.

Đổi lại, thứ tự khóa không còn hữu ích cho range scan thông thường theo giá trị gốc. Equality lookup vẫn có thể phù hợp; range predicate có thể mất lợi ích. Chỉ chọn khi workload chủ yếu lookup equality và vấn đề contention đã được đo.

### 12.3. Bitmap index không phải B-tree

Bitmap index là loại index khác, thường phù hợp với workload phân tích/đọc nhiều và cột có cardinality thấp trong môi trường ít DML đồng thời. Nó biểu diễn tập hàng bằng bitmap và có đặc tính locking khác. Không dùng bitmap index tùy tiện cho bảng OLTP có nhiều giao dịch ghi đồng thời. Bài này tập trung vào B-tree index.

## 13. Thống kê index và data dictionary

### 13.1. Xem index trong schema hiện tại

~~~sql
SELECT
    index_name,
    table_name,
    index_type,
    uniqueness,
    status,
    blevel,
    leaf_blocks,
    distinct_keys,
    clustering_factor
FROM user_indexes
ORDER BY table_name, index_name;
~~~

Các cột đáng chú ý:

- INDEX_TYPE: loại index.
- UNIQUENESS: UNIQUE hoặc NONUNIQUE.
- STATUS: trạng thái index.
- BLEVEL: số branch levels theo thống kê index.
- LEAF_BLOCKS: số leaf blocks theo thống kê.
- DISTINCT_KEYS: số giá trị khóa distinct.
- CLUSTERING_FACTOR: mức tương quan thứ tự index với table blocks.

Các thống kê có thể cũ hoặc chưa được thu thập; không diễn giải một con số tách khỏi thời điểm và phương pháp gather stats.

### 13.2. Xem cột và thứ tự của composite index

~~~sql
SELECT
    index_name,
    column_position,
    column_name,
    descend
FROM user_ind_columns
WHERE table_name = 'ORDERS_LAB'
ORDER BY index_name, column_position;
~~~

COLUMN_POSITION cho biết thứ tự cột trong index. DESCEND cho biết chiều sắp xếp của cột trong index. Đây là thông tin cần xem trước khi kết luận một predicate có dùng được leading prefix hay ORDER BY có thể được đáp ứng bằng index.

### 13.3. Xem index thuộc constraint nào

~~~sql
SELECT
    constraint_name,
    constraint_type,
    table_name,
    index_name,
    status
FROM user_constraints
WHERE constraint_type IN ('P', 'U')
ORDER BY table_name, constraint_name;
~~~

Primary key và unique constraint có thể được Oracle hỗ trợ bằng unique index. Không nên drop index đang được constraint sử dụng mà chưa hiểu tác động đến constraint.

### 13.4. Thu thập statistics

Trong schema lab, có thể thu thập statistics:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'ORDERS_LAB',
        cascade => TRUE
    );
END;
/
~~~

CASCADE cho phép thu thập statistics cho các index liên quan. Trên production, việc gather stats cần theo chính sách DBA, maintenance window và workload. Statistics có thể làm thay đổi execution plan của nhiều câu SQL.

## 14. Đọc execution plan để biết index có ích không

### 14.1. EXPLAIN PLAN

~~~sql
EXPLAIN PLAN FOR
SELECT order_id, customer_id, order_date
FROM orders_lab
WHERE customer_id = 100
  AND order_date >= DATE '2026-01-01'
  AND order_date < DATE '2026-02-01';

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

Plan ước lượng có thể cho thấy INDEX RANGE SCAN và TABLE ACCESS BY INDEX ROWID, hoặc FULL TABLE SCAN nếu optimizer ước lượng cách đó rẻ hơn.

### 14.2. Actual plan với runtime statistics

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       order_id, customer_id, order_date
FROM orders_lab
WHERE customer_id = 100
  AND order_date >= DATE '2026-01-01'
  AND order_date < DATE '2026-02-01';

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL, NULL, 'ALLSTATS LAST +PREDICATE +ALIAS'
    )
);
~~~

Xem:

| Thông tin | Ý nghĩa |
| --- | --- |
| Operation | Access path và cách kết hợp dữ liệu |
| E-Rows | Số hàng optimizer ước lượng |
| A-Rows | Số hàng thực tế khi đã thu thập runtime statistics |
| Starts | Số lần operation được thực thi |
| Buffers | Logical I/O |
| A-Time | Thời gian operation được ghi nhận |
| Predicate Information | Điều kiện access/filter |

### 14.3. Access predicate và filter predicate

Access predicate giúp định vị phạm vi đọc từ index hoặc table. Filter predicate được áp dụng để loại các hàng sau khi đã truy cập. Một điều kiện có thể là access predicate ở một operation và filter predicate ở operation khác.

Khi xem plan, hãy kiểm tra:

- Cột nào được dùng để định vị index range?
- Predicate nào chỉ được kiểm tra sau khi đọc leaf/table row?
- Có bao nhiêu ROWID được lấy?
- Có nhiều TABLE ACCESS BY INDEX ROWID không?
- Buffers của index và table access có hợp lý không?
- Estimated rows có gần actual rows không?

### 14.4. Index scan có thể tốn hơn full table scan

Ví dụ truy vấn:

~~~sql
SELECT *
FROM orders_lab
WHERE status = 'ACTIVE';
~~~

Nếu 95% đơn hàng có trạng thái ACTIVE và SELECT * cần nhiều cột, index trên STATUS có thể khiến Oracle phải lấy ROWID cho phần lớn bảng rồi đọc nhiều table blocks. Full table scan có thể rẻ hơn.

Không ép index bằng hint chỉ vì index tồn tại. Nếu cần thử một phương án, hãy dùng hint trong môi trường kiểm thử và so sánh actual metrics; sau đó xác định nguyên nhân optimizer chọn plan.

### 14.5. COST không phải thời gian

COST là ước lượng nội bộ của optimizer để so sánh phương án. Nó không phải mili giây, giây hoặc số block thực tế chắc chắn sẽ đọc. Hãy xem actual rows, buffers, elapsed time, I/O và workload khi benchmark.

## 15. Bài thực hành: tạo và quan sát B-tree index

### 15.1. Tạo bảng lab

~~~sql
CREATE TABLE orders_lab (
    order_id NUMBER PRIMARY KEY,
    customer_id NUMBER NOT NULL,
    order_date DATE NOT NULL,
    status VARCHAR2(12 CHAR) NOT NULL,
    total_amount NUMBER(12,2) NOT NULL
);
~~~

Primary key tạo hoặc sử dụng unique index phù hợp để bảo vệ ORDER_ID.

### 15.2. Nạp dữ liệu minh họa

~~~sql
INSERT INTO orders_lab
SELECT
    LEVEL AS order_id,
    MOD(LEVEL, 100) + 1 AS customer_id,
    DATE '2026-01-01' + MOD(LEVEL, 180) AS order_date,
    CASE
        WHEN MOD(LEVEL, 10) = 0 THEN 'CLOSED'
        ELSE 'ACTIVE'
    END AS status,
    100 + MOD(LEVEL, 500) AS total_amount
FROM dual
CONNECT BY LEVEL <= 10000;

COMMIT;
~~~

### 15.3. Tạo composite index

~~~sql
CREATE INDEX ix_orders_customer_date_lab
ON orders_lab(customer_id, order_date);
~~~

### 15.4. Thu thập statistics

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'ORDERS_LAB',
        cascade => TRUE
    );
END;
/
~~~

### 15.5. Truy vấn theo leading prefix và range

~~~sql
SELECT order_id, customer_id, order_date
FROM orders_lab
WHERE customer_id = 25
  AND order_date >= DATE '2026-03-01'
  AND order_date < DATE '2026-04-01'
ORDER BY order_date;
~~~

Kiểm tra plan và xem Oracle có chọn INDEX RANGE SCAN trên composite index hay không. Dữ liệu lab nhỏ nên optimizer vẫn có thể chọn table scan; điều đó không chứng minh index sai.

### 15.6. Truy vấn chỉ theo cột thứ hai

~~~sql
SELECT order_id, order_date
FROM orders_lab
WHERE order_date >= DATE '2026-03-01'
  AND order_date < DATE '2026-04-01';
~~~

So sánh plan với truy vấn trước. Vì index bắt đầu bằng CUSTOMER_ID, predicate chỉ trên ORDER_DATE không có leading prefix; optimizer có thể chọn table scan hoặc một access path khác. Hãy thử thêm index riêng trên ORDER_DATE trong môi trường lab, thu thập statistics và so sánh buffers/actual rows:

~~~sql
CREATE INDEX ix_orders_date_lab
ON orders_lab(order_date);
~~~

### 15.7. So sánh predicate có hàm và range

~~~sql
-- Predicate dat ham tren cot.
SELECT COUNT(*)
FROM orders_lab
WHERE TRUNC(order_date) = DATE '2026-03-15';

-- Predicate theo range.
SELECT COUNT(*)
FROM orders_lab
WHERE order_date >= DATE '2026-03-15'
  AND order_date < DATE '2026-03-16';
~~~

Hai câu có cùng ý nghĩa cho cột DATE trong ví dụ. So sánh plan và cân nhắc function-based index nếu truy vấn TRUNC là pattern quan trọng.

### 15.8. Quan sát metadata

~~~sql
SELECT index_name, index_type, uniqueness, blevel,
       leaf_blocks, distinct_keys, clustering_factor
FROM user_indexes
WHERE table_name = 'ORDERS_LAB'
ORDER BY index_name;

SELECT index_name, column_position, column_name, descend
FROM user_ind_columns
WHERE table_name = 'ORDERS_LAB'
ORDER BY index_name, column_position;
~~~

### 15.9. Dọn bảng lab (tùy chọn)

Chỉ chạy khi chắc chắn đây là bảng lab do bạn tạo và không cần dữ liệu nữa:

~~~sql
DROP TABLE orders_lab PURGE;
~~~

DROP TABLE là DDL và có implicit commit theo quy tắc Oracle. Không chạy trên bảng nghiệp vụ thật.

## 16. Những hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế |
| --- | --- |
| B-tree là cây nhị phân | Đây là cây tìm kiếm nhiều nhánh được tổ chức theo database blocks |
| Index lưu toàn bộ hàng của bảng | Leaf entries chủ yếu lưu key và ROWID |
| Có index thì truy vấn luôn nhanh | Selectivity, clustering factor, số cột cần đọc và chi phí table access quyết định |
| INDEX RANGE SCAN luôn chỉ đọc một hàng | Nó có thể đọc một vùng gồm nhiều entry |
| INDEX FULL SCAN và FAST FULL SCAN giống nhau | Full scan theo thứ tự key; fast full scan không bảo đảm thứ tự |
| Cột thứ hai của composite index không bao giờ dùng được | Skip scan hoặc full index access có thể dùng, nhưng leading prefix thường quan trọng |
| Mọi NULL đều được lưu trong B-tree index đơn cột | Entry có toàn bộ key NULL không được lưu trong B-tree thông thường |
| ROWID là khóa nghiệp vụ ổn định | ROWID là định vị vật lý/logical row locator, có thể thay đổi khi di chuyển hàng |
| Thêm index không ảnh hưởng INSERT | Mỗi index liên quan cần được duy trì |
| Rebuild index luôn làm truy vấn nhanh hơn | Chỉ nên rebuild khi có lý do và bằng chứng cụ thể |
| COST thấp hơn chắc chắn nhanh hơn | COST là ước lượng optimizer, không phải elapsed time |
| Index scan luôn tốt hơn full table scan | Đọc phần lớn bảng có thể rẻ hơn table lookups qua index |

## 17. Nguyên tắc thiết kế B-tree index

Khi cân nhắc một index mới:

1. Xác định câu SQL và workload cần hỗ trợ.
2. Xác định predicate equality, range, join và ORDER BY.
3. Chọn leading columns theo access pattern quan trọng.
4. Kiểm tra cột trả về có thể được lấy từ index hay cần table access.
5. Ước lượng selectivity và số ROWID dự kiến.
6. Xem clustering factor và kích thước bảng/index.
7. Cân nhắc chi phí INSERT/UPDATE/DELETE.
8. Thu thập statistics phù hợp.
9. Xem actual execution plan và buffers.
10. Giữ index khi lợi ích workload tổng thể lớn hơn chi phí duy trì.

### 17.1. Đừng tạo index trùng lặp

Index (CUSTOMER_ID, ORDER_DATE) đã có leading prefix CUSTOMER_ID. Một index đơn cột CUSTOMER_ID có thể dư thừa nếu không có lý do khác như khác compression, uniqueness, partitioning hoặc workload. Trước khi thêm index, xem các index hiện tại và các câu SQL đang sử dụng chúng.

### 17.2. Đừng rebuild theo lịch nếu không có lý do

B-tree index được Oracle duy trì tự động. Leaf block split không tự động có nghĩa index hỏng hoặc cần rebuild. Rebuild có thể tốn I/O, TEMP, redo, thời gian và tài nguyên; nó cũng có thể làm tăng tải hệ thống.

Chỉ cân nhắc rebuild/coalesce khi có bằng chứng về tình trạng segment, hiệu quả truy vấn, yêu cầu quản trị hoặc khuyến nghị DBA phù hợp. Hãy hiểu khác biệt giữa REBUILD và COALESCE, online/offline và tác động khóa/không gian.

### 17.3. Index không thay thế constraint

Index có thể hỗ trợ primary key hoặc unique constraint, nhưng một index nonunique không tự bảo vệ tính duy nhất. Nếu nghiệp vụ yêu cầu duy nhất, hãy khai báo PRIMARY KEY/UNIQUE constraint thay vì chỉ tạo index và mong ứng dụng luôn kiểm tra trước INSERT.

## 18. Câu hỏi tự kiểm tra

1. B-tree index trong Oracle có những tầng block khái niệm nào?
2. Root và branch blocks dùng để làm gì?
3. Leaf entry thường chứa thông tin nào?
4. Vì sao ROWID không nên được dùng làm business key?
5. Khi nào index unique scan phù hợp?
6. INDEX RANGE SCAN khác INDEX FULL SCAN thế nào?
7. INDEX FAST FULL SCAN có bảo đảm thứ tự khóa không?
8. Skip scan có thể hữu ích trong trường hợp composite index nào?
9. Leading column ảnh hưởng ra sao đến khả năng range lookup?
10. Vì sao index scan có thể cần TABLE ACCESS BY INDEX ROWID?
11. Index-only access có nghĩa gì?
12. Selectivity và cardinality khác nhau thế nào?
13. Clustering factor mô tả điều gì?
14. Khi nào full table scan có thể rẻ hơn index range scan?
15. B-tree index một cột xử lý hàng có giá trị NULL thế nào?
16. Vì sao function trên cột có thể làm index thông thường khó được sử dụng?
17. Function-based index hỗ trợ pattern truy vấn nào?
18. Leaf block split xảy ra khi nào?
19. UPDATE cột không nằm trong index có cần cập nhật index đó không?
20. Vì sao nhiều index làm INSERT/UPDATE/DELETE tốn kém hơn?
21. Reverse key index có trade-off gì?
22. BLEVEL và LEAF_BLOCKS có thể xem ở đâu?
23. Vì sao phải so A-Rows và E-Rows?
24. COST có phải thời gian thực thi không?
25. Vì sao không nên rebuild index chỉ theo lịch?

**Gợi ý trả lời:**

1. Root, branch và leaf; index nhỏ có thể gộp root với leaf level.
2. Chọn nhánh và dẫn hướng đến leaf block chứa khóa.
3. Giá trị khóa và ROWID của hàng.
4. ROWID là locator có thể đổi khi hàng được di chuyển/tái tổ chức.
5. Khi equality xác định đầy đủ một unique key.
6. Range scan đọc một vùng khóa; full scan đọc toàn bộ leaf theo thứ tự index.
7. Không.
8. Khi thiếu leading column nhưng leading column có ít giá trị distinct và chi phí phù hợp.
9. Leading prefix giúp định vị vùng khóa; thiếu nó có thể phải dùng access path khác.
10. Vì index thường chỉ chứa key/ROWID, còn cột khác nằm trong table block.
11. Truy vấn lấy đủ cột từ index và có thể tránh table access.
12. Selectivity là tỷ lệ lọc; cardinality là số hàng ước lượng/thực tế.
13. Mức tương quan giữa thứ tự key trong index và vị trí hàng trong table blocks.
14. Khi predicate trả về phần lớn bảng hoặc table lookups qua ROWID quá tốn.
15. Entry có toàn bộ key NULL không được lưu trong B-tree thông thường.
16. Vì index được sắp theo giá trị cột gốc, không phải kết quả hàm.
17. Khi truy vấn thường xuyên dùng cùng biểu thức đã index.
18. Khi leaf block không đủ chỗ cho entry mới theo thứ tự khóa.
19. Thường không, nếu không thay đổi key hoặc biểu thức index.
20. Mỗi index liên quan phải được duy trì và ghi redo/undo tương ứng.
21. Giảm tập trung insert ở leaf cuối nhưng làm mất lợi thế range scan theo key gốc.
22. USER_INDEXES hoặc ALL_INDEXES/DBA_INDEXES.
23. Để thấy sai lệch ước lượng cardinality và hiểu plan runtime.
24. Không, cost là ước lượng nội bộ optimizer.
25. Vì rebuild tốn tài nguyên và không phải mọi split/phân mảnh đều làm index chậm.

## Tài liệu Oracle tham khảo

- [Oracle Database Concepts — Schema Objects: Indexes](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/indexes-and-index-organized-tables.html): khái niệm index và cách tổ chức dữ liệu.
- [Oracle Database Administrator's Guide — Managing Indexes](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/managing-indexes.html): tạo, quản lý và bảo trì index.
- [Oracle Database SQL Language Reference — CREATE INDEX](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-INDEX.html): cú pháp index, composite, descending, compression và function-based index.
- [Oracle Database Reference — USER_INDEXES](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/USER_INDEXES.html): metadata và thống kê index.
- [Oracle Database Reference — USER_IND_COLUMNS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/USER_IND_COLUMNS.html): thứ tự và thuộc tính cột index.
- [Oracle Database SQL Tuning Guide — Access Paths](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/optimizer-access-paths.html): index scans và các access path.
- [Oracle Database SQL Tuning Guide — Optimizer Statistics](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/optimizer-statistics-concepts.html): thống kê optimizer, cardinality và selectivity.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_STATS](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_STATS.html): thu thập và quản lý optimizer statistics.

**Nguyên tắc cần nhớ:** B-tree index là cây tìm kiếm nhiều nhánh cân bằng, trong đó root/branch dẫn đến leaf entries chứa khóa và ROWID. Index giúp Oracle định vị vùng khóa nhanh, nhưng lợi ích cuối cùng phụ thuộc số hàng cần đọc, table block locality, các cột cần trả về và chi phí duy trì index khi ghi. Hãy thiết kế theo leading predicates và workload, rồi xác nhận bằng actual execution plan và runtime statistics.
