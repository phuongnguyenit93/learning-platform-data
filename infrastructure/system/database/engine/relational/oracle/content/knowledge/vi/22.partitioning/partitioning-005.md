# Partition pruning tĩnh và động trong Oracle

Khi một bảng Oracle được chia thành nhiều partition, truy vấn không nhất thiết phải đọc tất cả partition. **Partition pruning** là khả năng Oracle xác định những partition có thể chứa hàng thỏa điều kiện và loại các partition còn lại khỏi thao tác truy cập. Nếu truy vấn chỉ cần dữ liệu của một tháng, Oracle có thể chỉ đọc partition tháng đó thay vì quét toàn bộ lịch sử.

Oracle có thể xác định partition cần đọc ngay từ thông tin có sẵn trong câu SQL và cấu trúc partition (**static pruning**), hoặc chỉ xác định được khi câu lệnh đang thực thi, sau khi có bind value, kết quả subquery hay giá trị từ hàng của bảng khác (**dynamic pruning**). Cả hai đều giảm công việc đọc; khác biệt nằm ở thời điểm Oracle biết tập partition cần truy cập và cách thông tin đó thể hiện trong execution plan.

Bài học thuộc chủ đề **Phân vùng** của *Database Engine Relational Oracle*. Nội dung tập trung vào:

- Cách partition pruning hoạt động và lợi ích của nó.
- Static pruning và dynamic pruning khác nhau ở thời điểm xác định partition.
- Các dạng predicate hỗ trợ pruning trên RANGE, LIST, HASH và INTERVAL partition.
- Vai trò của bind variable, subquery, join và partition key.
- Đọc PARTITION START/STOP trong execution plan.
- Các lỗi thường gặp do hàm, implicit conversion và biểu thức trên partition key.
- Cách kiểm chứng pruning bằng EXPLAIN PLAN, DBMS_XPLAN và SQL lab.

## 1. Partition pruning giải quyết vấn đề gì?

Partitioning chia một bảng hoặc index lớn thành các phần nhỏ hơn được quản lý riêng. Các partition vẫn thuộc một đối tượng logic duy nhất trong câu SQL; ứng dụng thường truy vấn bảng bằng tên chung mà không phải tự chọn tên partition.

Ví dụ bảng đơn hàng được partition theo tháng:

~~~text
ORDERS
  P_2026_01  -> đơn hàng tháng 01/2026
  P_2026_02  -> đơn hàng tháng 02/2026
  P_2026_03  -> đơn hàng tháng 03/2026
  P_2026_04  -> đơn hàng tháng 04/2026
  ...
~~~

Truy vấn:

~~~sql
SELECT order_id, order_date, customer_id, amount
FROM orders
WHERE order_date >= DATE '2026-03-01'
  AND order_date <  DATE '2026-04-01';
~~~

Nếu ORDER_DATE là partition key của RANGE/INTERVAL partitioning, Oracle có thể loại các partition nằm ngoài tháng 03/2026. Việc loại partition này gọi là partition pruning.

### Lợi ích

- Giảm số partition và số block cần đọc.
- Giảm I/O và CPU cho truy vấn chỉ cần một phần dữ liệu.
- Giảm công việc cho table scan hoặc index range scan trên partition.
- Có thể giúp partition-wise operation và bảo trì dữ liệu hiệu quả hơn.

Pruning không tự bảo đảm truy vấn nhanh. Một partition được giữ lại vẫn có thể chứa hàng tỷ dòng; truy vấn có thể cần full scan partition đó. Hiệu quả phụ thuộc số partition bị loại, kích thước partition còn lại, predicate, thống kê và access path.

### Pruning khác index access

Partition pruning quyết định **partition nào cần tham gia**. Index access quyết định **cách tìm hàng bên trong partition hoặc trên đối tượng index**.

Ví dụ:

~~~sql
SELECT *
FROM orders
WHERE order_date >= DATE '2026-03-01'
  AND order_date <  DATE '2026-04-01'
  AND customer_id = 100;
~~~

Oracle có thể prune còn partition tháng 03, sau đó dùng local index trên CUSTOMER_ID trong partition đó, hoặc full scan partition nếu cost phù hợp. Pruning và index là hai quyết định có thể phối hợp, không thay thế nhau.

## 2. Cơ chế xác định partition

Oracle biết ranh giới partition từ metadata của bảng: partition key, partition bound và loại partitioning. Khi tối ưu truy vấn, Oracle xem predicate có giới hạn giá trị partition key hay không.

Với RANGE partitioning, mỗi partition giữ một khoảng giá trị. Ví dụ:

~~~sql
CREATE TABLE orders (
    order_id    NUMBER,
    order_date  DATE NOT NULL,
    customer_id NUMBER,
    amount      NUMBER(12,2)
)
PARTITION BY RANGE (order_date) (
    PARTITION p_before_2026 VALUES LESS THAN (DATE '2026-01-01'),
    PARTITION p_2026_q1    VALUES LESS THAN (DATE '2026-04-01'),
    PARTITION p_2026_q2    VALUES LESS THAN (DATE '2026-07-01'),
    PARTITION p_2026_q3    VALUES LESS THAN (DATE '2026-10-01'),
    PARTITION p_2026_q4    VALUES LESS THAN (DATE '2027-01-01')
);
~~~

Oracle dùng predicate trên ORDER_DATE để xác định partition bound nào có thể chứa hàng phù hợp.

### Predicate phải liên hệ được với partition key

Các dạng thường có thể prune:

~~~sql
-- Equality
WHERE order_date = DATE '2026-05-10'

-- IN list
WHERE order_date IN (
    DATE '2026-05-10',
    DATE '2026-06-15'
)

-- Range
WHERE order_date >= DATE '2026-04-01'
  AND order_date <  DATE '2026-07-01'

-- So sánh một phía
WHERE order_date < DATE '2026-04-01'
~~~

Với RANGE partitioning, equality thường chỉ cần một partition; range có thể cần nhiều partition; predicate không giới hạn partition key có thể khiến Oracle đọc tất cả partition.

### LIST và HASH partitioning

Với LIST partitioning, equality hoặc IN trên partition key có thể giúp Oracle xác định partition tương ứng với các giá trị liệt kê:

~~~sql
CREATE TABLE sales_by_region (
    sale_id NUMBER,
    region_code VARCHAR2(10),
    amount NUMBER
)
PARTITION BY LIST (region_code) (
    PARTITION p_north VALUES ('NORTH'),
    PARTITION p_south VALUES ('SOUTH'),
    PARTITION p_east  VALUES ('EAST'),
    PARTITION p_west  VALUES ('WEST')
);

SELECT *
FROM sales_by_region
WHERE region_code IN ('NORTH', 'EAST');
~~~

Với HASH partitioning, Oracle ánh xạ giá trị partition key tới partition bằng hash function. Predicate equality trên đủ partition key thường cho phép xác định partition cụ thể; range predicate không có cùng ý nghĩa với RANGE partitioning và có thể cần đọc nhiều hoặc tất cả hash partition.

### INTERVAL partitioning

INTERVAL partitioning tự tạo partition theo khoảng khi dữ liệu vượt ranh giới đã khai báo. Pruning vẫn dựa trên partition key và bound của partition; việc tự sinh partition không làm mất khả năng prune.

## 3. Static pruning

**Static pruning** xảy ra khi Oracle có thể xác định partition cần truy cập từ thông tin đã biết trong câu SQL và metadata lúc tối ưu. Predicate thường chứa literal hoặc biểu thức hằng mà optimizer có thể tính được trước khi thực thi.

Ví dụ:

~~~sql
SELECT COUNT(*)
FROM orders
WHERE order_date >= DATE '2026-04-01'
  AND order_date <  DATE '2026-07-01';
~~~

Hai mốc ngày là literal. Oracle có thể xác định phạm vi partition Q2/2026 ngay khi tối ưu câu lệnh. Execution plan thường thể hiện partition start/stop cụ thể bằng số thứ tự partition thay vì KEY runtime.

### Equality trên partition key

~~~sql
SELECT *
FROM sales_by_region
WHERE region_code = 'NORTH';
~~~

Với LIST partitioning, Oracle có thể xác định partition P_NORTH tại thời điểm tối ưu.

### IN list

~~~sql
SELECT *
FROM sales_by_region
WHERE region_code IN ('NORTH', 'WEST');
~~~

Oracle có thể xác định hai partition tương ứng. Tùy dạng partitioning và plan, operation có thể thể hiện iterator qua nhiều partition.

### Biểu thức hằng

Một biểu thức có thể tính được từ literal cũng có thể hỗ trợ static pruning:

~~~sql
SELECT *
FROM orders
WHERE order_date >= DATE '2026-01-01' + 90
  AND order_date <  DATE '2026-01-01' + 181;
~~~

Optimizer có thể tính các mốc hằng khi tối ưu. Trong thực tế, nên dùng date literal rõ ràng hoặc bind variable có kiểu dữ liệu phù hợp để câu SQL dễ đọc và tránh phụ thuộc NLS.

## 4. Dynamic pruning

**Dynamic pruning** xảy ra khi Oracle chỉ xác định được partition cần đọc trong lúc thực thi. Giá trị quyết định có thể đến từ bind variable, kết quả subquery, hàng của bảng được join hoặc thông tin chỉ có khi runtime.

Ví dụ dùng bind variable:

~~~sql
SELECT order_id, order_date, amount
FROM orders
WHERE order_date >= :from_date
  AND order_date <  :to_date;
~~~

Khi tối ưu SQL, Oracle biết tên bind nhưng giá trị thực tế được truyền lúc execute. Runtime engine dùng giá trị bind để xác định partition phù hợp. Execution plan thường hiển thị KEY ở PSTART/PSTOP để biểu thị ranh giới partition được xác định động.

### Bind variable không đồng nghĩa không prune

Một hiểu lầm phổ biến là bind variable khiến Oracle phải quét mọi partition. Điều đó không đúng. Oracle vẫn có thể dynamic prune dựa trên giá trị bind lúc thực thi. Việc bind peeking/adaptive cursor sharing có thể ảnh hưởng lựa chọn plan, nhưng partition pruning runtime vẫn có thể diễn ra.

Bind variable giúp chia sẻ cursor và giảm hard parse; dynamic pruning cho phép cùng một cursor được thực thi với các khoảng giá trị khác nhau mà chỉ truy cập partition phù hợp.

### Dynamic pruning qua subquery

Ví dụ bảng CUSTOMERS được lọc trước, rồi khoảng ngày cần đọc được xác định từ kết quả truy vấn khác:

~~~sql
SELECT o.order_id,
       o.order_date,
       o.customer_id,
       o.amount
FROM orders o
WHERE o.order_date >= (
          SELECT MIN(c.valid_from)
          FROM customer_campaign c
          WHERE c.campaign_id = :campaign_id
      )
  AND o.order_date < (
          SELECT MAX(c.valid_to)
          FROM customer_campaign c
          WHERE c.campaign_id = :campaign_id
      );
~~~

Các mốc ngày chỉ có được sau khi thực hiện subquery. Optimizer có thể dùng kết quả runtime để prune partition của ORDERS. Khả năng và hình dạng plan phụ thuộc cách optimizer biến đổi subquery và cách biểu thức được sử dụng.

### Dynamic pruning qua join

Một bảng dimension nhỏ có thể cung cấp partition key cho bảng fact:

~~~sql
SELECT f.order_id,
       f.order_date,
       f.amount
FROM selected_periods p
JOIN orders f
  ON f.order_date >= p.start_date
 AND f.order_date <  p.end_date
WHERE p.period_code = :period_code;
~~~

Khi giá trị START_DATE/END_DATE đến từ hàng của bảng khác, Oracle có thể prune partition của ORDERS tại runtime. Một số kế hoạch nested loops hoặc biến đổi truy vấn có thể thực hiện partition pruning theo từng giá trị từ phía ngoài của join.

Không phải mọi join tới partitioned table đều tự động prune. Điều kiện join cần liên hệ đúng partition key, optimizer phải chọn transformation/access path hỗ trợ và cardinality/statistics phải đủ tốt.

### Dynamic pruning trong star transformation

Trong data warehouse, dimension filter có thể xác định các key cần thiết ở runtime. Khi optimizer dùng star transformation hoặc bitmap access phù hợp, tập partition của fact table có thể được xác định động từ các key đã lọc. Đây là một dạng runtime pruning; cần xem plan thực tế thay vì suy luận chỉ từ việc query có join dimension.

## 5. Static và dynamic pruning: so sánh

| Tiêu chí | Static pruning | Dynamic pruning |
| --- | --- | --- |
| Thời điểm xác định partition | Trong quá trình parse/optimization khi predicate đã đủ rõ | Trong lúc execute khi runtime value có sẵn |
| Nguồn giá trị thường gặp | Literal, biểu thức hằng, điều kiện xác định trước | Bind variable, subquery, join value, runtime expression |
| PSTART/PSTOP thường thấy | Số partition cụ thể | KEY hoặc ký hiệu runtime tương ứng |
| Có thể giảm số partition đọc? | Có | Có |
| Có phụ thuộc bind value? | Không cần giá trị bind runtime | Thường có |
| Có thể dùng cùng một cursor cho nhiều khoảng khác nhau? | Plan có thể được tạo theo literal/cursor cụ thể | Có thể runtime prune theo bind mỗi lần execute |

Hai loại không phải hai mức chất lượng. Dynamic pruning không kém hơn chỉ vì nó xảy ra lúc runtime; trong workload dùng bind variable, đó thường là hành vi mong muốn. Điều cần quan tâm là Oracle có prune được đúng partition và lượng partition còn lại có phù hợp truy vấn hay không.

### Một câu SQL có thể có nhiều loại pruning

Một query phức tạp có thể truy cập nhiều partitioned object. Có object được static prune theo literal, object khác dynamic prune theo bind hoặc join. Hãy đọc từng operation partition trong execution plan, không gán một nhãn duy nhất cho toàn câu SQL.

## 6. Đọc PARTITION START và PARTITION STOP trong execution plan

Execution plan thường thể hiện operation partition và hai cột PSTART/PSTOP:

- PSTART: partition bắt đầu trong phạm vi truy cập.
- PSTOP: partition kết thúc trong phạm vi truy cập.
- Số cụ thể thường cho biết partition number được xác định trong plan.
- KEY thường biểu thị Oracle sẽ xác định partition ở runtime.

Ví dụ một plan minh họa:

~~~text
| Id | Operation                 | Name   | Pstart | Pstop |
|----|---------------------------|--------|--------|-------|
|  0 | SELECT STATEMENT          |        |        |       |
|  1 | PARTITION RANGE SINGLE    |        |      3 |     3 |
|  2 | TABLE ACCESS FULL         | ORDERS |      3 |     3 |
~~~

Plan này thể hiện truy cập một partition cụ thể. Tên operation có thể là PARTITION RANGE SINGLE, PARTITION RANGE ITERATOR, PARTITION LIST SINGLE, PARTITION LIST ITERATOR hoặc dạng tương ứng tùy loại partition và số partition được chọn.

Ví dụ dynamic:

~~~text
| Id | Operation                 | Name   | Pstart | Pstop |
|----|---------------------------|--------|--------|-------|
|  0 | SELECT STATEMENT          |        |        |       |
|  1 | PARTITION RANGE ITERATOR  |        | KEY    | KEY   |
|  2 | TABLE ACCESS FULL         | ORDERS | KEY    | KEY   |
~~~

KEY biểu thị ranh giới partition phụ thuộc giá trị chỉ có ở runtime. Nó không có nghĩa quét tất cả partition. Cần xem actual rows, starts và predicate để biết thực tế bao nhiêu partition được truy cập.

### PARTITION RANGE SINGLE và ITERATOR

- SINGLE thường xuất hiện khi một partition được chọn.
- ITERATOR thường xuất hiện khi Oracle duyệt một hoặc nhiều partition trong phạm vi.
- ALL thường cho biết operation đi qua toàn bộ partition của đối tượng trong access path đó.
- Các operation LIST/HASH có tên tương ứng tùy kiểu partitioning.

Tên operation không tự cho biết tổng số block được đọc. Một partition đơn lẻ vẫn có thể rất lớn; cần xem table access, index access, buffers và actual rows.

### KEY không phải một partition tên KEY

KEY trong PSTART/PSTOP là ký hiệu trong plan, không phải tên partition. Nó cho biết ranh giới được tính động. Đừng tìm một partition có tên KEY trong USER_TAB_PARTITIONS.

## 7. Kiểm chứng pruning bằng EXPLAIN PLAN và DBMS_XPLAN

Tạo plan:

~~~sql
EXPLAIN PLAN FOR
SELECT COUNT(*)
FROM orders
WHERE order_date >= DATE '2026-04-01'
  AND order_date <  DATE '2026-07-01';

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY(NULL, NULL, 'BASIC +PARTITION'));
~~~

Định dạng +PARTITION hiển thị thông tin partition start/stop nếu có trong plan. Có thể dùng format rộng hơn:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY(
        NULL,
        NULL,
        'ALL +PARTITION +PREDICATE +ALIAS'
    )
);
~~~

EXPLAIN PLAN là plan ước lượng, không thực thi câu truy vấn và không cho biết chính xác runtime partition đã được truy cập. Với bind variable hoặc runtime pruning, plan có thể hiện KEY; muốn xác nhận thực tế cần xem cursor thực thi và thống kê runtime phù hợp.

### Xem cursor thực tế

~~~sql
SELECT /*+ gather_plan_statistics */
       COUNT(*)
FROM orders
WHERE order_date >= :from_date
  AND order_date <  :to_date;

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PARTITION +PREDICATE +ALIAS'
    )
);
~~~

ALLSTATS LAST cần runtime plan statistics được thu thập, ví dụ hint GATHER_PLAN_STATISTICS hoặc cấu hình phù hợp. Kiểm tra:

- PSTART/PSTOP có thể hiện số cụ thể hay KEY.
- Starts cho operation partition/table access.
- E-Rows so với A-Rows.
- Buffers, reads và thời gian thực thi.
- Predicate information cho biết điều kiện nào được dùng để access/filter.

Nếu câu SQL chạy qua ứng dụng với bind variables, hãy kiểm tra đúng child cursor và bind values của lần thực thi cần phân tích. DISPLAY_CURSOR(NULL,NULL,...) thường hiển thị cursor gần nhất của session; môi trường có nhiều câu SQL có thể cần SQL_ID/child number cụ thể.

### Partition name và partition number

Các số PSTART/PSTOP là vị trí partition trong metadata của đối tượng tại thời điểm plan được tạo; không phải giá trị partition key và không nên hard-code vào ứng dụng. Để xem tên và bound:

~~~sql
SELECT partition_position,
       partition_name,
       high_value
FROM user_tab_partitions
WHERE table_name = 'ORDERS'
ORDER BY partition_position;
~~~

HIGH_VALUE được hiển thị dưới dạng biểu thức metadata và kiểu dữ liệu trả về phụ thuộc phiên bản/view. Không dùng chuỗi HIGH_VALUE để tự dựng logic truy vấn; dùng partition key và predicate SQL bình thường.

## 8. Predicate giúp pruning

Để Oracle prune hiệu quả, predicate nên thể hiện trực tiếp giới hạn của partition key và dùng đúng kiểu dữ liệu.

### Dùng range nửa mở cho DATE/TIMESTAMP

Với partition theo ngày/tháng, dạng range nửa mở thường rõ ràng:

~~~sql
WHERE order_date >= DATE '2026-03-01'
  AND order_date <  DATE '2026-04-01'
~~~

Điều kiện này bao gồm mọi thời điểm trong tháng 3, kể cả phần thời gian của ngày cuối tháng, và không phụ thuộc độ chính xác giây/ fractional seconds. So với BETWEEN hai ngày, range nửa mở tránh phải đoán giá trị thời gian cuối ngày.

### So sánh đúng kiểu dữ liệu

Nếu partition key là DATE, truyền DATE literal hoặc bind DATE. Nếu partition key là TIMESTAMP, truyền TIMESTAMP phù hợp. Tránh so sánh cột DATE với chuỗi ký tự:

~~~sql
-- Không nên phụ thuộc implicit conversion/NLS.
WHERE order_date >= '01-MAR-2026'
~~~

Nên viết:

~~~sql
WHERE order_date >= DATE '2026-03-01'
~~~

Implicit conversion có thể làm kết quả phụ thuộc NLS_DATE_FORMAT hoặc khiến Oracle phải chuyển đổi biểu thức theo cách ảnh hưởng access path. Dùng bind variable có datatype đúng trong ứng dụng.

### Predicate equality, IN và range

RANGE partition:

~~~sql
WHERE order_date = DATE '2026-05-10'
~~~

LIST partition:

~~~sql
WHERE region_code IN ('NORTH', 'SOUTH')
~~~

HASH partition:

~~~sql
WHERE customer_id = 12345
~~~

Đối với HASH, equality trên partition key thường giúp xác định partition; điều kiện range không ánh xạ thành một dải hash partition tương tự RANGE partitioning.

### Predicate kết hợp nhiều điều kiện

~~~sql
SELECT *
FROM orders
WHERE order_date >= DATE '2026-01-01'
  AND order_date <  DATE '2026-02-01'
  AND status = 'PAID'
  AND customer_id = 100;
~~~

Điều kiện ORDER_DATE có thể prune partition; STATUS và CUSTOMER_ID tiếp tục lọc hàng bên trong partition hoặc giúp chọn index. Không cần mọi predicate đều là partition key.

### OR và biểu thức phức tạp

~~~sql
SELECT *
FROM orders
WHERE order_date < DATE '2026-01-01'
   OR order_date >= DATE '2026-12-01';
~~~

Optimizer có thể prune theo cả hai khoảng nếu có thể suy luận từng nhánh. Nhưng khi OR trộn partition key với cột khác, hoặc các biểu thức phức tạp, khả năng pruning phụ thuộc query transformation và phiên bản. Kiểm tra plan thực tế.

## 9. Các biểu thức có thể cản trở pruning

Một lỗi phổ biến là bọc partition key trong hàm khiến optimizer khó ánh xạ predicate về partition bound.

### Hàm trên partition key

Giả sử ORDERS được partition theo ORDER_DATE:

~~~sql
-- Có thể làm giảm khả năng pruning trực tiếp.
WHERE TRUNC(order_date) = DATE '2026-03-15'
~~~

Thay bằng range:

~~~sql
WHERE order_date >= DATE '2026-03-15'
  AND order_date <  DATE '2026-03-16'
~~~

Điều kiện thứ hai giữ cột partition key ở dạng trực tiếp và thường dễ prune hơn. Optimizer có thể biến đổi một số hàm phổ biến, nhưng không nên dựa vào điều đó nếu có thể viết predicate range rõ ràng.

### Hàm trên partition key theo tháng

~~~sql
-- Dễ khiến predicate không sargable đối với partition key.
WHERE TO_CHAR(order_date, 'YYYY-MM') = '2026-03'
~~~

Viết:

~~~sql
WHERE order_date >= DATE '2026-03-01'
  AND order_date <  DATE '2026-04-01'
~~~

Nếu bảng được partition theo biểu thức, chẳng hạn TRUNC(ORDER_DATE, 'MM') hoặc virtual column, predicate nên khớp với biểu thức partition key và kiểu dữ liệu tương ứng. Không áp dụng máy móc quy tắc “mọi hàm đều không prune”; optimizer có thể hỗ trợ một số biểu thức, nhưng plan mới là bằng chứng.

### Implicit conversion

Nếu partition key là NUMBER nhưng ứng dụng truyền chuỗi, hoặc partition key là DATE nhưng ứng dụng truyền VARCHAR2, Oracle có thể phải chuyển đổi kiểu. Tùy chiều conversion, điều này có thể cản trở pruning hoặc khiến predicate phụ thuộc NLS.

Ví dụ partition key NUMBER:

~~~sql
-- Bind nên là NUMBER.
WHERE customer_id = :customer_id
~~~

Trong JDBC, dùng setLong/setBigDecimal phù hợp thay vì setString cho cột số. Với ngày, dùng setDate/setTimestamp theo datatype thực tế.

### Predicate không giới hạn partition key

~~~sql
SELECT *
FROM orders
WHERE status = 'PAID';
~~~

Nếu STATUS không phải partition key và không có điều kiện liên quan tới partition key, Oracle thường phải xem xét tất cả partition. Một local index trên STATUS có thể giúp access từng partition nhưng không tự loại partition khỏi phạm vi.

## 10. Partition key ghép và pruning

Một bảng có thể partition theo nhiều cột hoặc partition-subpartition. Với composite partitioning, Oracle có thể prune ở cả cấp partition và subpartition nếu predicate cung cấp đủ thông tin.

Ví dụ RANGE-HASH:

~~~sql
CREATE TABLE sales_fact (
    sale_id NUMBER,
    sale_date DATE NOT NULL,
    customer_id NUMBER NOT NULL,
    amount NUMBER
)
PARTITION BY RANGE (sale_date)
SUBPARTITION BY HASH (customer_id)
SUBPARTITIONS 8
(
    PARTITION p_2026_q1 VALUES LESS THAN (DATE '2026-04-01'),
    PARTITION p_2026_q2 VALUES LESS THAN (DATE '2026-07-01'),
    PARTITION p_2026_q3 VALUES LESS THAN (DATE '2026-10-01'),
    PARTITION p_2026_q4 VALUES LESS THAN (DATE '2027-01-01')
);
~~~

Predicate:

~~~sql
SELECT *
FROM sales_fact
WHERE sale_date >= DATE '2026-04-01'
  AND sale_date <  DATE '2026-07-01'
  AND customer_id = 12345;
~~~

Điều kiện SALE_DATE có thể prune xuống partition Q2; CUSTOMER_ID có thể prune tiếp subpartition hash phù hợp. Nếu chỉ có SALE_DATE, Oracle vẫn có thể phải đọc các subpartition trong partition Q2.

### Partition key ghép

Với RANGE COLUMNS hoặc các chiến lược multi-column tùy phiên bản, khả năng prune phụ thuộc thứ tự và tổ hợp cột partition key. Nếu predicate chỉ giới hạn một phần khóa, Oracle có thể prune một phạm vi nhưng không nhất thiết chọn được partition đơn lẻ. Xem PSTART/PSTOP và partition operations để hiểu mức pruning thực tế.

## 11. Partition pruning và local/global index

Pruning áp dụng cho partitioned table hoặc partitioned index. Index locality quyết định index được tổ chức theo từng partition hay trên phạm vi toàn bảng; nó ảnh hưởng access path và bảo trì index, nhưng không thay đổi nguyên tắc xác định partition theo partition key.

### Local index

Local index được chia partition tương ứng với các partition của bảng. Mỗi index partition chỉ chứa entry cho table partition tương ứng. Khi Oracle prune table partition, nó có thể chỉ truy cập các local index partition tương ứng.

~~~sql
CREATE INDEX ix_orders_customer_local
ON orders(customer_id)
LOCAL;
~~~

Ví dụ query theo tháng và khách hàng có thể prune table xuống một số partition rồi dùng local index để tìm CUSTOMER_ID trong các partition đó:

~~~sql
SELECT order_id, order_date, amount
FROM orders
WHERE order_date >= DATE '2026-04-01'
  AND order_date <  DATE '2026-07-01'
  AND customer_id = 100;
~~~

### Global index

Global index được tổ chức trên phạm vi nhiều partition của bảng, có thể là nonpartitioned global index hoặc partitioned global index. Một truy vấn prune table partition vẫn có thể sử dụng global index nếu access path và cost phù hợp. Việc duy trì global index khi partition maintenance (DROP, TRUNCATE, EXCHANGE, MOVE) cần được quản lý cẩn thận theo tùy chọn và phiên bản.

### Pruning không có nghĩa chỉ đọc local index

Oracle có thể:

- Prune table partition rồi full scan các partition còn lại.
- Prune partition và dùng local index partition.
- Dùng global index để tìm rowid rồi truy cập table partition tương ứng.
- Chọn full scan toàn bộ bảng nếu truy vấn cần phần lớn dữ liệu hoặc cost thấp hơn.

Đọc toàn bộ execution plan để hiểu thứ tự partition iterator, index access và table access. Chỉ nhìn operation index chưa đủ để kết luận partition pruning có xảy ra hay không.

## 12. Bind peeking, cursor sharing và runtime pruning

Bind variable có thể được truyền với giá trị khác nhau ở mỗi lần execute. Oracle có thể peek một số bind value tại hard parse để ước lượng selectivity và chọn plan; tính năng adaptive cursor sharing có thể tạo child cursor khác khi các giá trị bind có đặc tính selectivity khác nhau.

Điều này liên quan tới lựa chọn plan, nhưng cần phân biệt với việc xác định partition ở runtime:

- **Bind peeking:** optimizer quan sát bind value trong quá trình hard parse để ước lượng cardinality/selectivity.
- **Dynamic pruning:** execution engine dùng giá trị runtime để xác định partition thực sự cần truy cập.
- **Adaptive cursor sharing:** Oracle có thể quản lý nhiều child cursor cho các nhóm bind value có hành vi selectivity khác nhau.

Không nên kết luận rằng bind peeking đã xảy ra thì pruning chắc chắn là static. Plan có thể vẫn thể hiện KEY cho partition start/stop và thực hiện pruning động ở mỗi lần execute.

### Bind datatype phải khớp partition key

Ví dụ:

~~~sql
SELECT *
FROM orders
WHERE order_date >= :from_date
  AND order_date < :to_date;
~~~

Nếu ORDER_DATE là DATE, ứng dụng nên bind DATE. Nếu truyền VARCHAR2, Oracle có thể thực hiện implicit conversion; ngoài rủi ro NLS, biểu thức chuyển đổi có thể làm giảm khả năng dùng predicate trực tiếp trên partition key.

### Một cursor, nhiều khoảng ngày

Ứng dụng có thể dùng cùng câu SQL với các khoảng ngày khác nhau:

~~~sql
SELECT COUNT(*)
FROM orders
WHERE order_date >= :from_date
  AND order_date < :to_date;
~~~

Lần execute đầu có thể đọc một partition; lần khác có thể đọc ba partition. Dynamic pruning cho phép runtime partition set thay đổi theo bind values mà không cần tạo một câu SQL literal khác cho mỗi khoảng.

## 13. Partition pruning và partition-wise join

Partition pruning và partition-wise join có liên quan trong truy vấn bảng lớn nhưng không phải cùng một kỹ thuật:

- Partition pruning loại partition không cần thiết khỏi một table access.
- Partition-wise join chia phép JOIN theo các partition tương ứng, có thể giảm dữ liệu trao đổi và tận dụng parallel execution.

Nếu hai bảng được partition tương thích trên join key, Oracle có thể thực hiện full hoặc partial partition-wise join tùy cấu trúc và predicate. Nếu một bảng dimension nhỏ không partition tương thích, optimizer có thể dùng partial partition-wise join hoặc broadcast/replicate tùy plan.

Ví dụ fact và dimension cùng partition theo CUSTOMER_ID:

~~~sql
SELECT f.customer_id,
       SUM(f.amount)
FROM sales_fact f
JOIN customer_fact_partitioned d
  ON d.customer_id = f.customer_id
WHERE f.sale_date >= DATE '2026-01-01'
  AND f.sale_date <  DATE '2026-02-01'
GROUP BY f.customer_id;
~~~

Predicate SALE_DATE có thể prune partition theo ngày. Join theo CUSTOMER_ID có thể được tối ưu riêng theo cách partitioning của hai bảng. Cần đọc plan để phân biệt operation partition pruning với PARTITION HASH/ RANGE JOIN hoặc các operation partition-wise.

## 14. Những nguyên nhân khiến pruning không như mong đợi

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Query đọc mọi partition | Không có predicate trên partition key | Thêm điều kiện partition key nếu nghiệp vụ cho phép. |
| Predicate dùng TRUNC/TO_CHAR trên key | Biểu thức làm optimizer khó suy ra partition range | Viết range nửa mở trên cột gốc hoặc partition expression phù hợp. |
| Plan hiển thị KEY | Pruning được quyết định ở runtime | Không coi KEY là full scan; xem runtime stats và bind value. |
| PSTART/PSTOP là số nhưng query vẫn chậm | Partition được chọn vẫn rất lớn hoặc access path tốn kém | Kiểm tra số block, index, selectivity và actual rows. |
| Bind query chọn plan kém cho một số giá trị | Selectivity của bind values khác nhau | Kiểm tra child cursor, bind peeking/adaptive cursor sharing và thống kê. |
| So sánh DATE với chuỗi | Implicit conversion/NLS | Dùng DATE/TIMESTAMP literal hoặc bind đúng datatype. |
| Join không prune được fact table | Join key/predicate không hỗ trợ runtime pruning hoặc transformation không được chọn | Kiểm tra partition key, join order, transformation và plan. |
| Chỉ prune một cấp trong composite partition | Predicate chưa giới hạn subpartition key | Bổ sung predicate subpartition key nếu phù hợp. |
| Dùng index nhưng vẫn đọc nhiều partition | Index access không đồng nghĩa partition pruning | Xem operation partition và PSTART/PSTOP riêng. |
| Pruning khác giữa môi trường | Partition metadata, statistics, bind datatype hoặc optimizer settings khác nhau | So sánh DDL, stats, binds, plan hash và phiên bản. |

## 15. Bài thực hành tổng hợp

Thực hiện trong schema học tập có quyền CREATE TABLE và quota phù hợp. Các lệnh DDL có implicit commit trong Oracle; không chạy trên bảng nghiệp vụ thật.

### Bước 1: tạo bảng RANGE partition theo tháng/quý

~~~sql
CREATE TABLE lab_orders (
    order_id    NUMBER,
    order_date  DATE NOT NULL,
    customer_id NUMBER,
    amount      NUMBER(12,2),
    status      VARCHAR2(20)
)
PARTITION BY RANGE (order_date) (
    PARTITION p_before_2026 VALUES LESS THAN (DATE '2026-01-01'),
    PARTITION p_2026_q1    VALUES LESS THAN (DATE '2026-04-01'),
    PARTITION p_2026_q2    VALUES LESS THAN (DATE '2026-07-01'),
    PARTITION p_2026_q3    VALUES LESS THAN (DATE '2026-10-01'),
    PARTITION p_2026_q4    VALUES LESS THAN (DATE '2027-01-01'),
    PARTITION p_future     VALUES LESS THAN (MAXVALUE)
);
~~~

### Bước 2: chèn dữ liệu ở nhiều partition

~~~sql
INSERT INTO lab_orders VALUES
    (1, DATE '2026-01-10', 10, 100, 'PAID');
INSERT INTO lab_orders VALUES
    (2, DATE '2026-02-15', 20, 200, 'PAID');
INSERT INTO lab_orders VALUES
    (3, DATE '2026-04-05', 10, 150, 'PENDING');
INSERT INTO lab_orders VALUES
    (4, DATE '2026-05-20', 30, 300, 'PAID');
INSERT INTO lab_orders VALUES
    (5, DATE '2026-08-01', 20, 250, 'PAID');
INSERT INTO lab_orders VALUES
    (6, DATE '2026-11-12', 10, 400, 'PAID');
COMMIT;
~~~

### Bước 3: quan sát static pruning

~~~sql
EXPLAIN PLAN FOR
SELECT order_id, amount
FROM lab_orders
WHERE order_date >= DATE '2026-04-01'
  AND order_date <  DATE '2026-07-01';

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY(NULL, NULL, 'BASIC +PARTITION +PREDICATE'));
~~~

Quan sát partition operation và PSTART/PSTOP. Với literal range Q2, Oracle có thể xác định partition cụ thể khi tối ưu.

### Bước 4: quan sát dynamic pruning bằng bind

Trong SQL client hỗ trợ bind variable:

~~~sql
VARIABLE from_date DATE
VARIABLE to_date DATE

EXEC :from_date := DATE '2026-04-01';
EXEC :to_date   := DATE '2026-07-01';

SELECT /*+ gather_plan_statistics */
       order_id, amount
FROM lab_orders
WHERE order_date >= :from_date
  AND order_date <  :to_date;

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL, NULL,
        'ALLSTATS LAST +PARTITION +PREDICATE'
    )
);
~~~

Client khác nhau có cú pháp khai báo bind khác nhau. Trong JDBC/ứng dụng, bind DATE bằng API datatype tương ứng. Quan sát KEY trong PSTART/PSTOP nếu plan thể hiện runtime pruning.

### Bước 5: thử biểu thức trên partition key

~~~sql
EXPLAIN PLAN FOR
SELECT *
FROM lab_orders
WHERE TRUNC(order_date) = DATE '2026-04-05';

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY(NULL, NULL, 'BASIC +PARTITION +PREDICATE'));
~~~

So sánh với range predicate:

~~~sql
EXPLAIN PLAN FOR
SELECT *
FROM lab_orders
WHERE order_date >= DATE '2026-04-05'
  AND order_date <  DATE '2026-04-06';

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY(NULL, NULL, 'BASIC +PARTITION +PREDICATE'));
~~~

Quan sát cách optimizer xử lý từng biểu thức ở phiên bản đang dùng. Mục tiêu là hiểu vì sao predicate trực tiếp trên partition key thường dễ prune hơn, không giả định mọi biểu thức hàm đều luôn ngăn pruning.

### Bước 6: kiểm tra partition metadata

~~~sql
SELECT partition_position,
       partition_name,
       num_rows,
       blocks
FROM user_tab_partitions
WHERE table_name = 'LAB_ORDERS'
ORDER BY partition_position;
~~~

NUM_ROWS/BLOCKS phản ánh statistics; nếu chưa thu thập hoặc đã cũ, số liệu có thể NULL hoặc không đại diện dữ liệu hiện tại. Có thể thu thập stats trong schema lab:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'LAB_ORDERS',
        granularity => 'ALL'
    );
END;
/
~~~

### Bước 7: dọn dữ liệu

~~~sql
DROP TABLE lab_orders PURGE;
~~~

Chỉ chạy khi đã hoàn thành lab và không cần giữ dữ liệu. DROP TABLE là DDL có implicit commit; PURGE bỏ qua Recycle Bin.

## 16. Câu hỏi tự kiểm tra

1. **Partition pruning là gì?** Là việc Oracle loại các partition không thể chứa hàng thỏa predicate khỏi thao tác truy cập.
2. **Pruning khác index access thế nào?** Pruning chọn partition; index access tìm hàng bên trong phạm vi partition/object được chọn.
3. **Static pruning thường dựa trên thông tin nào?** Literal hoặc biểu thức hằng mà optimizer có thể xác định partition khi tối ưu.
4. **Dynamic pruning thường dựa trên thông tin nào?** Bind value, subquery result, join value hoặc runtime expression chỉ có khi execute.
5. **Bind variable có ngăn pruning không?** Không; Oracle có thể dùng bind value lúc runtime để dynamic prune.
6. **PSTART/PSTOP là gì?** Hai cột trong execution plan biểu thị partition bắt đầu/kết thúc của operation truy cập partition.
7. **KEY trong PSTART/PSTOP có nghĩa gì?** Partition boundary được xác định động lúc runtime; không phải tên partition và không có nghĩa quét tất cả.
8. **PARTITION RANGE SINGLE thường biểu thị điều gì?** Access path chọn một range partition.
9. **PARTITION RANGE ALL thường biểu thị điều gì?** Operation truy cập toàn bộ partition trong phạm vi object đó.
10. **Vì sao nên dùng range nửa mở cho DATE?** Nó bao gồm trọn khoảng thời gian và tránh phải đoán giá trị cuối ngày.
11. **TRUNC(partition_key) có thể gây vấn đề gì?** Hàm trên key có thể làm optimizer khó suy ra partition range; predicate trực tiếp thường dễ prune hơn.
12. **Implicit conversion ảnh hưởng ra sao?** Có thể làm predicate phụ thuộc NLS hoặc khiến biểu thức không còn trực tiếp trên partition key.
13. **Dynamic pruning qua join xảy ra khi nào?** Khi giá trị partition key đến từ hàng phía ngoài/join và Oracle có thể xác định partition lúc thực thi.
14. **Local index có tự tạo partition pruning không?** Không; local index được tổ chức theo table partition, còn pruning vẫn dựa trên predicate/partition key.
15. **EXPLAIN PLAN có chứng minh runtime pruning thực tế không?** Không; nó cho plan ước lượng. Cần xem cursor thực thi và runtime statistics.
16. **Tại sao một partition đã được prune vẫn có thể chậm?** Partition còn lại có thể rất lớn hoặc access path, selectivity, I/O và CPU vẫn tốn kém.
17. **Partition pruning và partition-wise join có giống nhau không?** Không; pruning loại partition khỏi truy cập, partition-wise join chia phép join theo partition tương ứng.
18. **Làm thế nào xác nhận pruning cải thiện hiệu năng?** So sánh actual plan, partition starts, buffers, reads, actual rows, latency và throughput trên workload tương đương.

Partition pruning tĩnh và động đều nhằm giảm số partition Oracle phải truy cập. Static pruning xác định partition từ literal/biểu thức đã biết khi tối ưu; dynamic pruning đợi bind, subquery hoặc giá trị join xuất hiện lúc thực thi. Hãy viết predicate trực tiếp trên partition key với datatype phù hợp, đọc PSTART/PSTOP cùng operation và runtime statistics, rồi xác nhận bằng workload thực tế. Một plan có KEY vẫn có thể prune rất hiệu quả; một plan chỉ truy cập một partition vẫn có thể chậm nếu partition đó quá lớn hoặc access path không phù hợp.
