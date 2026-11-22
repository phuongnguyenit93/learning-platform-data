# Composite index, cột dẫn đầu và thứ tự các cột

Trong Oracle Database, **composite index** (còn gọi là concatenated index hoặc multicolumn index) là chỉ mục được tạo trên từ hai cột hoặc biểu thức trở lên của cùng một bảng. Composite index lưu khóa theo thứ tự các cột được khai báo. Thứ tự đó quyết định cách các khóa được sắp xếp, vùng dữ liệu Oracle có thể định vị trực tiếp, khả năng lọc hàng và khả năng hỗ trợ ORDER BY.

Ba khái niệm quan trọng:

- **Cột dẫn đầu (leading column)** là cột đầu tiên trong định nghĩa index.
- **Leading prefix** là một hoặc nhiều cột liên tiếp bắt đầu từ cột đầu tiên. Với index (A, B, C), các prefix là (A), (A, B) và (A, B, C).
- **Thứ tự cột phải theo workload**: chọn dựa trên các mẫu WHERE, JOIN, ORDER BY, GROUP BY, phạm vi giá trị, phân bố dữ liệu và chi phí DML. Không có quy tắc máy móc rằng cột có cardinality cao nhất luôn phải đứng đầu.

Ví dụ:

~~~sql
CREATE INDEX ix_orders_customer_status_date
ON orders (customer_id, status, created_at);
~~~

Index được sắp xếp trước theo CUSTOMER_ID, trong mỗi CUSTOMER_ID theo STATUS, và trong mỗi cặp CUSTOMER_ID/STATUS theo CREATED_AT. Nó thường phù hợp với truy vấn tìm đơn hàng của một khách hàng, lọc thêm trạng thái và khoảng thời gian. Nó không tương đương với index (STATUS, CUSTOMER_ID, CREATED_AT) hoặc (CREATED_AT, CUSTOMER_ID, STATUS).

Bài học giải thích cấu trúc B-tree composite index, leading prefix, equality/range predicates, index skip scan, thứ tự ASC/DESC, thiết kế cột theo truy vấn, NULL, unique index, function-based index, thống kê và cách đọc execution plan.

## 1. Composite index là gì?

Index một cột:

~~~sql
CREATE INDEX ix_orders_customer
ON orders (customer_id);
~~~

Composite index:

~~~sql
CREATE INDEX ix_orders_customer_status
ON orders (customer_id, status);
~~~

Index hai cột chứa khóa kết hợp từ CUSTOMER_ID và STATUS. Với B-tree index, khóa được sắp xếp theo thứ tự từ điển: Oracle so sánh cột thứ nhất trước; nếu bằng nhau mới so sánh cột thứ hai; nếu tiếp tục bằng nhau mới xét cột thứ ba.

Giả sử dữ liệu:

| CUSTOMER_ID | STATUS | CREATED_AT |
| ---: | --- | --- |
| 10 | CLOSED | 2025-01-02 |
| 10 | CLOSED | 2025-01-09 |
| 10 | NEW | 2025-01-03 |
| 10 | NEW | 2025-02-01 |
| 20 | CLOSED | 2025-01-04 |
| 20 | NEW | 2025-01-07 |

Với index (CUSTOMER_ID, STATUS, CREATED_AT), thứ tự logic có thể hình dung:

~~~text
CUSTOMER_ID
  10
    CLOSED
      2025-01-02
      2025-01-09
    NEW
      2025-01-03
      2025-02-01
  20
    CLOSED
      2025-01-04
    NEW
      2025-01-07
~~~

Đây là lý do thứ tự cột quan trọng. Index được tổ chức theo CUSTOMER_ID trước, không phải theo CREATED_AT trên toàn bảng.

### 1.1. Composite key không phải chuỗi nối thủ công

Index (A, B) không tương đương với việc tạo cột chuỗi A || B. Oracle quản lý từng thành phần khóa theo datatype, collation và quy tắc so sánh tương ứng. Tự nối cột có thể tạo va chạm, thay đổi semantics NULL và làm mất khả năng dùng index thông thường trên từng cột.

### 1.2. Index chứa khóa và thông tin định vị hàng

B-tree index thường lưu:
- Giá trị khóa theo thứ tự các cột/biểu thức.
- Thông tin ROWID để truy cập hàng trong heap table.
- Cấu trúc branch block và leaf block để tìm kiếm, duyệt khóa.

Composite index có thể giúp truy vấn chỉ đọc index nếu tất cả cột cần thiết đã có trong index và optimizer chọn access path phù hợp. Khi cần cột không có trong index, Oracle có thể truy cập bảng bằng ROWID.

## 2. Leading column và leading prefix

Với index:

~~~sql
CREATE INDEX ix_sales_region_product_date
ON sales (region_id, product_id, sale_date);
~~~

Các leading prefix hợp lệ là:

1. REGION_ID
2. REGION_ID, PRODUCT_ID
3. REGION_ID, PRODUCT_ID, SALE_DATE

Các prefix bắt đầu từ cột đầu tiên và không bỏ qua cột ở giữa.

Oracle thường có thể dùng index range scan để tìm vùng khóa theo một prefix. Điều kiện trên cột không dẫn đầu vẫn có thể hữu ích, nhưng khả năng truy cập và chi phí khác nhau.

### 2.1. Điều kiện chỉ dùng cột dẫn đầu

~~~sql
SELECT sale_id, region_id, product_id, sale_date
FROM sales
WHERE region_id = 10;
~~~

Index (REGION_ID, PRODUCT_ID, SALE_DATE) có thể tìm vùng entry bắt đầu với REGION_ID=10. Các entry của vùng này nằm liên tiếp theo thứ tự các cột tiếp theo.

### 2.2. Điều kiện dùng hai cột đầu

~~~sql
SELECT sale_id, region_id, product_id, sale_date
FROM sales
WHERE region_id = 10
  AND product_id = 200;
~~~

Oracle có thể dùng prefix (REGION_ID, PRODUCT_ID) để thu hẹp vùng tìm kiếm hơn so với chỉ REGION_ID.

### 2.3. Điều kiện dùng đủ ba cột

~~~sql
SELECT sale_id
FROM sales
WHERE region_id = 10
  AND product_id = 200
  AND sale_date >= DATE '2025-01-01'
  AND sale_date <  DATE '2025-02-01';
~~~

Index có thể định vị theo REGION_ID và PRODUCT_ID, sau đó giới hạn khoảng SALE_DATE bên trong vùng khóa đó.

### 2.4. Chỉ lọc cột thứ hai

~~~sql
SELECT sale_id, region_id, product_id
FROM sales
WHERE product_id = 200;
~~~

Index (REGION_ID, PRODUCT_ID, SALE_DATE) không có prefix bắt đầu bằng PRODUCT_ID. Oracle không thể đơn giản tìm một vùng liên tục duy nhất cho PRODUCT_ID=200 trên toàn index, vì giá trị PRODUCT_ID được sắp xếp lại bên trong từng REGION_ID.

Tùy dữ liệu và chi phí, Oracle có thể:
- Dùng index khác bắt đầu bằng PRODUCT_ID.
- Dùng full table scan.
- Dùng index full scan hoặc fast full index scan nếu phù hợp.
- Cân nhắc index skip scan nếu số distinct value của cột dẫn đầu đủ thấp và điều kiện phù hợp.

Không nên kết luận index hoàn toàn không thể được đọc khi thiếu cột dẫn đầu. Điều cần hiểu là nó không có đường range scan theo prefix thông thường trên PRODUCT_ID một cách trực tiếp.

### 2.5. Bỏ qua cột giữa

Với index (A, B, C), truy vấn lọc A và C nhưng không lọc B:

~~~sql
SELECT *
FROM t
WHERE a = :a
  AND c = :c;
~~~

Oracle có thể dùng A để định vị vùng khóa; C có thể được áp dụng như filter trên các entry thuộc vùng A. Điều kiện C không tạo thành prefix (A, C), vì B nằm giữa. Nếu B có nhiều giá trị, vùng phải duyệt có thể lớn hơn mong muốn.

Nếu truy vấn này thường xuyên và có tính chọn lọc cao, hãy đánh giá index (A, C) hoặc một thứ tự khác theo toàn bộ workload.

## 3. Index range scan và predicate trên prefix

Một composite B-tree index giúp Oracle tìm một khoảng khóa liên tiếp. Predicate càng xác định được phần đầu của khóa, vùng tìm kiếm càng có thể hẹp.

Ví dụ index:

~~~sql
CREATE INDEX ix_order_customer_status_date
ON orders (customer_id, status, created_at);
~~~

### 3.1. Equality trên cột đầu

~~~sql
WHERE customer_id = :customer_id
~~~

Oracle định vị vùng entry của một khách hàng.

### 3.2. Equality trên hai cột đầu

~~~sql
WHERE customer_id = :customer_id
  AND status = 'NEW'
~~~

Oracle định vị vùng của một khách hàng và trạng thái NEW.

### 3.3. Equality rồi đến range

~~~sql
WHERE customer_id = :customer_id
  AND status = 'NEW'
  AND created_at >= :from_date
  AND created_at <  :to_date
~~~

Đây là mẫu thường phù hợp với thứ tự (CUSTOMER_ID, STATUS, CREATED_AT): equality xác định prefix, range giới hạn phần tiếp theo.

### 3.4. Range ở cột đầu, predicate ở cột sau

~~~sql
WHERE customer_id BETWEEN :low_id AND :high_id
  AND status = 'NEW'
~~~

Oracle có thể dùng CUSTOMER_ID để định vị nhiều vùng/range. Điều kiện STATUS vẫn có thể được kiểm tra trong index entry hoặc ở bước filter, nhưng không còn tạo một vùng đơn giản tương ứng với một giá trị CUSTOMER_ID cụ thể.

Một nguyên tắc thiết kế thường hữu ích là đặt các cột equality phổ biến trước cột range, nếu đó là cấu trúc truy vấn chủ đạo. Tuy nhiên, phải xem toàn bộ truy vấn và khả năng tái sử dụng index; đây là heuristic, không phải quy luật tuyệt đối.

### 3.5. Nhiều điều kiện equality

~~~sql
WHERE customer_id = :customer_id
  AND status = :status
  AND channel_id = :channel_id
~~~

Khi tất cả điều kiện là equality, Oracle có thể sử dụng các cột trong prefix để xác định một vùng hẹp. Thứ tự giữa các cột equality có thể ảnh hưởng:
- Truy vấn khác chỉ lọc một trong các cột đó.
- Truy vấn lọc một prefix ngắn hơn.
- Khả năng hỗ trợ ORDER BY.
- Kích thước index và phân bố giá trị.
- Skip scan và các access path khác.

Không chỉ xét một câu truy vấn đơn lẻ khi chọn thứ tự.

## 4. Equality trước range: nguyên tắc hữu ích nhưng không máy móc

Với index:

~~~sql
CREATE INDEX ix_orders_customer_date_status
ON orders (customer_id, created_at, status);
~~~

và truy vấn:

~~~sql
WHERE customer_id = :customer_id
  AND created_at >= :from_date
  AND created_at < :to_date
  AND status = 'NEW'
~~~

Oracle có thể dùng CUSTOMER_ID equality và CREATED_AT range để xác định vùng index. STATUS ở sau cột range có thể được kiểm tra như filter; nó không nhất thiết thu hẹp cùng vùng liên tục hiệu quả như khi STATUS đứng trước CREATED_AT.

Nếu phần lớn truy vấn lọc equality CUSTOMER_ID + STATUS rồi range CREATED_AT, index (CUSTOMER_ID, STATUS, CREATED_AT) thường là ứng viên tự nhiên hơn.

Tuy nhiên, nếu truy vấn quan trọng nhất là lấy mọi đơn theo CUSTOMER_ID và CREATED_AT, bất kể STATUS, thứ tự (CUSTOMER_ID, CREATED_AT, STATUS) có thể phù hợp hơn.

### 4.1. Range không chỉ là BETWEEN

Các điều kiện range gồm:
- >, >=, <, <=
- BETWEEN
- So sánh khoảng ngày/giờ
- Một số điều kiện prefix/range theo datatype và collation

Ví dụ:

~~~sql
WHERE created_at >= TIMESTAMP '2025-01-01 00:00:00'
  AND created_at <  TIMESTAMP '2025-02-01 00:00:00'
~~~

Khoảng nửa kín thường thích hợp cho timestamp vì không phải đoán giá trị cuối ngày với phần giây lẻ.

### 4.2. Predicate sau range vẫn có thể hữu ích

Không nên hiểu “cột sau range vô dụng”. Oracle vẫn có thể:
- Kiểm tra predicate trên cột sau trong index entry.
- Dùng cột đó để giảm table access.
- Dùng index-only access nếu query được bao phủ.
- Kết hợp nhiều access path hoặc filter theo cost.

Điều cần tránh là giả định predicate sau range luôn tạo thêm một giới hạn liên tục tương đương equality prefix. Hãy xem predicate access/filter trong plan.

## 5. Index skip scan

**Index skip scan** là một access path Oracle có thể dùng khi truy vấn không có điều kiện trên cột dẫn đầu nhưng có điều kiện trên một cột phía sau. Oracle chia index thành các logical subindex theo từng giá trị khác nhau của leading column rồi tìm trong các subindex phù hợp.

Ví dụ:

~~~sql
CREATE INDEX ix_emp_gender_dept
ON employees (gender, department_id);
~~~

Truy vấn:

~~~sql
SELECT employee_id, department_id
FROM employees
WHERE department_id = 10;
~~~

Nếu GENDER chỉ có rất ít giá trị khác nhau, chẳng hạn M/F, Oracle có thể cân nhắc skip scan:
- Tìm trong logical subindex GENDER='F'.
- Tìm trong logical subindex GENDER='M'.
- Kết hợp các entry thỏa DEPARTMENT_ID=10.

### 5.1. Khi nào skip scan có thể phù hợp?

Skip scan có thể được cân nhắc khi:
- Leading column có cardinality thấp.
- Cột phía sau có predicate chọn lọc.
- Số distinct value của leading column nhỏ.
- Chi phí skip scan thấp hơn full table scan hoặc access path khác.

Nếu leading column có hàng triệu giá trị khác nhau, số logical subindex phải xét có thể lớn và skip scan thường kém hấp dẫn.

### 5.2. Skip scan không thay thế thiết kế leading column

Nếu workload thường xuyên truy vấn theo DEPARTMENT_ID mà không lọc GENDER, index (GENDER, DEPARTMENT_ID) không nhất thiết là lựa chọn tốt nhất. Index (DEPARTMENT_ID, GENDER) có thể hỗ trợ trực tiếp prefix DEPARTMENT_ID và thường dễ dự đoán hơn cho workload đó.

Skip scan là một lựa chọn optimizer, không phải lời hứa rằng mọi truy vấn không có leading predicate sẽ dùng index tốt.

### 5.3. Xem plan để nhận biết

Trong execution plan có thể thấy operation INDEX SKIP SCAN. Tên operation cụ thể phụ thuộc phiên bản và plan. Đừng tạo index leading column cardinality thấp chỉ để trông chờ skip scan nếu một index bắt đầu bằng cột truy vấn thực tế sẽ đơn giản và hiệu quả hơn.

## 6. Chọn thứ tự cột theo workload

Giả sử bảng ORDERS có các cột:
- ORDER_ID: khóa chính.
- CUSTOMER_ID: khách hàng.
- STATUS: trạng thái.
- CREATED_AT: thời điểm tạo.
- SALES_REP_ID: nhân viên bán hàng.
- CHANNEL_ID: kênh.

Các truy vấn thường gặp:

~~~sql
-- Q1: đơn mới của một khách hàng trong khoảng ngày.
SELECT order_id, created_at
FROM orders
WHERE customer_id = :customer_id
  AND status = 'NEW'
  AND created_at >= :from_date
  AND created_at < :to_date;

-- Q2: đơn của một khách hàng.
SELECT order_id, status, created_at
FROM orders
WHERE customer_id = :customer_id;

-- Q3: đơn NEW trong khoảng ngày trên toàn hệ thống.
SELECT order_id, customer_id
FROM orders
WHERE status = 'NEW'
  AND created_at >= :from_date
  AND created_at < :to_date;

-- Q4: đơn của một sales rep, sắp xếp mới nhất.
SELECT order_id, created_at
FROM orders
WHERE sales_rep_id = :sales_rep_id
ORDER BY created_at DESC;
~~~

Không nhất thiết một composite index duy nhất phục vụ tối ưu cả bốn mẫu. Các ứng viên có thể là:

| Index | Mẫu truy vấn được hỗ trợ tự nhiên |
| --- | --- |
| (CUSTOMER_ID, STATUS, CREATED_AT) | Q1 và prefix CUSTOMER_ID cho Q2 |
| (STATUS, CREATED_AT) | Q3 |
| (SALES_REP_ID, CREATED_AT DESC) | Q4 |

Việc có nên tạo cả ba hay không phụ thuộc tần suất truy vấn, số hàng, chi phí DML, dung lượng và các index hiện có.

### 6.1. Không có một index tối ưu cho mọi truy vấn

Nếu tạo:

~~~sql
CREATE INDEX ix_orders_customer_status_date
ON orders (customer_id, status, created_at);
~~~

Q1 có prefix đầy đủ. Q2 dùng prefix CUSTOMER_ID. Nhưng Q3 chỉ lọc STATUS và CREATED_AT, không có CUSTOMER_ID; index này không phải đường range scan prefix trực tiếp cho Q3.

Nếu đảo thứ tự:

~~~sql
CREATE INDEX ix_orders_status_date_customer
ON orders (status, created_at, customer_id);
~~~

Q3 có thể được hỗ trợ tự nhiên, nhưng Q2 chỉ lọc CUSTOMER_ID thì không có leading prefix.

Thứ tự cột là sự đánh đổi giữa workload, không phải một thuộc tính “tốt nhất” độc lập.

### 6.2. Cột được dùng nhiều ở leading position có thể đáng ưu tiên

Nếu nhiều truy vấn lọc CUSTOMER_ID mà không lọc STATUS, đặt CUSTOMER_ID đầu giúp index dùng được cho:
- CUSTOMER_ID.
- CUSTOMER_ID + STATUS.
- CUSTOMER_ID + STATUS + CREATED_AT.

Một index (CUSTOMER_ID, STATUS, CREATED_AT) có thể phục vụ các prefix liên tiếp. Ngược lại, truy vấn chỉ lọc STATUS không được hỗ trợ trực tiếp theo prefix.

### 6.3. Cardinality và selectivity

**Cardinality** của cột thường nói tới số giá trị khác nhau; **selectivity** của predicate nói tới tỷ lệ hàng được chọn.

Ví dụ:
- STATUS có 3 giá trị NEW/PROCESSING/CLOSED, cardinality thấp.
- CUSTOMER_ID có hàng trăm nghìn giá trị, cardinality cao.
- Predicate STATUS='CLOSED' có thể chọn 70% bảng, selectivity thấp.
- Predicate CUSTOMER_ID=12345 có thể chọn 0,001% bảng, selectivity cao.

Cột có cardinality cao thường có thể tạo predicate chọn lọc hơn, nhưng không tự động phải đứng đầu mọi composite index. Nếu truy vấn luôn có equality trên cả CUSTOMER_ID và STATUS, thứ tự còn phụ thuộc các prefix cần hỗ trợ, range, ORDER BY và phân bố dữ liệu.

### 6.4. Equality columns có thể sắp xếp theo khả năng tái sử dụng

Giả sử workload có:
- CUSTOMER_ID.
- CUSTOMER_ID + STATUS.
- STATUS + CHANNEL_ID.

Nếu CUSTOMER_ID là điều kiện thường xuyên đứng một mình, có lý do đặt nó đầu. Nếu STATUS + CHANNEL_ID là workload chính, index khác có thể cần.

Khi tất cả predicate đều equality, chọn thứ tự để hỗ trợ nhiều prefix truy vấn nhất thường hữu ích hơn chỉ xếp cardinality giảm dần.

### 6.5. Đặt cột range sau các cột equality khi phù hợp

Mẫu thường gặp:

~~~sql
WHERE customer_id = :id
  AND status = :status
  AND created_at >= :from_ts
  AND created_at < :to_ts
~~~

Index (CUSTOMER_ID, STATUS, CREATED_AT) đặt hai equality trước range. Đây là heuristic thực tế hữu ích cho truy vấn này.

Nếu CREATED_AT là cột được dùng riêng trong nhiều truy vấn, có thể cần một index khác bắt đầu bằng CREATED_AT hoặc một thiết kế phù hợp với partitioning/workload. Không cố nhồi tất cả vào một index.

## 7. Composite index hỗ trợ ORDER BY

Index có thể giúp tránh hoặc giảm chi phí sort nếu thứ tự truy vấn tương thích với thứ tự khóa index và các điều kiện prefix.

Index:

~~~sql
CREATE INDEX ix_orders_customer_created
ON orders (customer_id, created_at);
~~~

Truy vấn:

~~~sql
SELECT order_id, created_at
FROM orders
WHERE customer_id = :customer_id
ORDER BY created_at;
~~~

Sau khi cố định CUSTOMER_ID, các entry trong vùng đó được sắp theo CREATED_AT. Oracle có thể dùng index để trả theo thứ tự mà không cần một sort riêng, tùy plan và các cột cần đọc.

### 7.1. ORDER BY cùng thứ tự cột

Index (A, B) có thể hỗ trợ:

~~~sql
WHERE a = :a
ORDER BY b;
~~~

vì A đã cố định, thứ tự còn lại trong vùng là B.

Index (A, B, C) có thể hỗ trợ truy vấn:

~~~sql
WHERE a = :a
ORDER BY b, c;
~~~

nếu các chiều sắp xếp tương thích với định nghĩa index và không có điều kiện làm thay đổi yêu cầu thứ tự.

### 7.2. ORDER BY prefix

Index (A, B, C) có thể cung cấp thứ tự theo A, hoặc theo A/B, hoặc theo A/B/C. Nhưng nếu chỉ ORDER BY B trên toàn bảng mà không cố định A, thứ tự index vẫn là A trước B nên không phải thứ tự B toàn cục.

Ví dụ:

~~~sql
SELECT *
FROM t
ORDER BY b;
~~~

Index (A,B) không tự tạo thứ tự B toàn bảng; các giá trị B được nhóm theo từng A.

### 7.3. ASC và DESC

Oracle B-tree index có thể được duyệt theo chiều thuận hoặc ngược. Index:

~~~sql
CREATE INDEX ix_orders_customer_date
ON orders (customer_id ASC, created_at ASC);
~~~

có thể được duyệt ngược để lấy thứ tự CUSTOMER_ID DESC và CREATED_AT DESC trong những trường hợp phù hợp. Nhưng một thứ tự hỗn hợp như:

~~~sql
ORDER BY customer_id ASC, created_at DESC
~~~

không tương đương với việc đảo ngược toàn bộ index (CUSTOMER_ID ASC, CREATED_AT ASC). Có thể cần descending index:

~~~sql
CREATE INDEX ix_orders_customer_date_mix
ON orders (customer_id ASC, created_at DESC);
~~~

Hãy xem plan thực tế; optimizer có thể chọn sort thay vì index scan nếu đường index đắt hơn.

### 7.4. NULLS FIRST và NULLS LAST

Thứ tự NULL mặc định trong Oracle:
- ASC mặc định là NULLS LAST.
- DESC mặc định là NULLS FIRST.

Nếu truy vấn cần:

~~~sql
ORDER BY created_at DESC NULLS LAST
~~~

hãy xem index direction và khả năng dùng index để đáp ứng NULL ordering. Một descending key có cách sắp xếp NULL khác với ascending key. Đừng giả định index scan luôn thỏa mọi ORDER BY chỉ vì cột giống nhau; direction và NULL positioning cũng quan trọng.

### 7.5. ORDER BY không được bảo đảm nếu thiếu ORDER BY cuối

Dù execution plan tình cờ dùng index theo thứ tự, ứng dụng vẫn phải viết ORDER BY trong SQL để có hợp đồng thứ tự kết quả. Không dựa vào thứ tự vật lý của index hoặc plan hiện tại.

## 8. Composite index cho JOIN

Composite index thường hữu ích khi điều kiện JOIN và filter cùng dùng nhiều cột.

~~~sql
SELECT o.order_id,
       o.created_at,
       c.customer_name
FROM orders o
JOIN customers c
  ON c.customer_id = o.customer_id
WHERE o.status = 'NEW'
  AND o.created_at >= :from_date;
~~~

Ứng viên index trên ORDERS có thể là (STATUS, CREATED_AT, CUSTOMER_ID) hoặc (CUSTOMER_ID, STATUS, CREATED_AT) tùy thứ tự truy cập, cardinality và workload khác.

Index trên bảng CUSTOMERS có thể đã được cung cấp bởi primary key CUSTOMER_ID. Không tạo index trùng lặp nếu primary key đã có index phù hợp.

### 8.1. Index phía foreign key

Nếu truy vấn thường tìm order theo CUSTOMER_ID, index bắt đầu bằng CUSTOMER_ID hữu ích:

~~~sql
CREATE INDEX ix_orders_customer_status
ON orders (customer_id, status);
~~~

Index foreign key cũng có thể giúp một số thao tác parent UPDATE/DELETE và join, tùy workload. Oracle không tự động tạo index cho mọi foreign key; DBA/Developer phải đánh giá nhu cầu.

### 8.2. Index JOIN không chỉ dựa vào thứ tự cột trong ON

Một câu JOIN có thể có nhiều predicate:
- Equality JOIN key.
- Filter WHERE.
- Range date.
- ORDER BY.

Hãy xem cả access path của bảng ngoài và bảng trong, số hàng dự kiến, join method và cardinality. Chọn index chỉ từ một dòng ON có thể bỏ qua điều kiện quan trọng khác.

## 9. Composite index và covering query

Một index **covering** cho truy vấn khi tất cả cột cần để lọc, join, sắp xếp và trả kết quả có thể lấy từ index, nên Oracle có thể tránh table access trong một số plan.

Ví dụ:

~~~sql
CREATE INDEX ix_orders_customer_status_date_id
ON orders (customer_id, status, created_at, order_id);
~~~

Truy vấn:

~~~sql
SELECT order_id, created_at
FROM orders
WHERE customer_id = :customer_id
  AND status = 'NEW'
ORDER BY created_at;
~~~

Các cột cần thiết đều nằm trong index. Oracle có thể chọn INDEX RANGE SCAN mà không truy cập bảng, nếu plan và điều kiện cho phép.

### 9.1. Covering index không phải lúc nào cũng nên tạo

Thêm nhiều cột vào index:
- Tăng dung lượng segment.
- Tăng chi phí INSERT/UPDATE/DELETE.
- Tăng redo/undo và bảo trì index.
- Có thể giảm số entry trên mỗi leaf block.
- Có thể làm tăng chiều cao hoặc số block cần đọc.

Chỉ thêm cột để cover query khi lợi ích đọc được đo và đáng với chi phí ghi/storage. Không đưa mọi cột SELECT vào index một cách máy móc.

### 9.2. Cột INCLUDE khác nhau giữa các hệ quản trị

Một số database có cú pháp INCLUDE để lưu cột phụ ở leaf level mà không tham gia khóa sắp xếp. Không áp dụng cú pháp đó tùy tiện cho Oracle B-tree index thông thường. Trong Oracle, cột được khai báo trong composite index là thành phần của key; cần cân nhắc thứ tự và độ rộng khóa.

## 10. NULL trong composite index

Oracle B-tree index không lưu entry cho hàng mà **tất cả các cột khóa của index đều NULL**. Với composite index, nếu ít nhất một cột khóa có giá trị non-NULL, hàng có thể có entry index.

Ví dụ:

~~~sql
CREATE INDEX ix_t_a_b
ON t (a, b);
~~~

| A | B | Entry B-tree |
| --- | --- | --- |
| 10 | 20 | Có |
| 10 | NULL | Có |
| NULL | 20 | Có |
| NULL | NULL | Không có entry |

Điều này quan trọng khi thiết kế truy vấn tìm NULL và khi cân nhắc index chỉ gồm một cột nullable.

### 10.1. Index một cột nullable

~~~sql
CREATE INDEX ix_employee_middle_name
ON employees (middle_name);
~~~

Các hàng MIDDLE_NAME NULL không có entry trong B-tree index đó. Truy vấn:

~~~sql
SELECT employee_id
FROM employees
WHERE middle_name IS NULL;
~~~

thường không thể dùng index B-tree một cột này để tìm toàn bộ hàng NULL, vì các hàng đó không có entry. Optimizer thường chọn table scan hoặc một access path khác.

### 10.2. Composite index có thể chứa hàng với một cột NULL

~~~sql
CREATE INDEX ix_employee_dept_name
ON employees (department_id, middle_name);
~~~

Nếu DEPARTMENT_ID có giá trị còn MIDDLE_NAME NULL, hàng vẫn có entry vì toàn bộ khóa không NULL. Index có thể hỗ trợ truy vấn theo DEPARTMENT_ID và kiểm tra MIDDLE_NAME trong vùng tương ứng.

### 10.3. NULL và unique composite index

Unique composite index/constraint có quy tắc NULL riêng của Oracle. Không nên suy luận rằng mọi hàng có một cột NULL đều bị bỏ qua như hàng có toàn bộ key NULL. Nếu dùng unique index để bảo vệ quy tắc nghiệp vụ có nullable columns, hãy xác minh semantics cụ thể của tổ hợp giá trị NULL bằng tài liệu và thử nghiệm trong schema sandbox; không dựa vào mô hình “NULL luôn giống nhau” hoặc “NULL luôn khác nhau” một cách đơn giản.

Nếu nghiệp vụ yêu cầu uniqueness có điều kiện, có thể cần function-based unique index hoặc thiết kế constraint phù hợp. Việc xử lý NULL phải được định nghĩa rõ.

## 11. Unique composite index

Có thể tạo unique index trên nhiều cột:

~~~sql
CREATE UNIQUE INDEX ux_customer_external_key
ON customer_external_id (source_system, external_id);
~~~

Index bảo đảm tổ hợp khóa theo quy tắc unique của Oracle không bị trùng. Ví dụ:
- SOURCE_SYSTEM='CRM', EXTERNAL_ID='A100'.
- SOURCE_SYSTEM='ERP', EXTERNAL_ID='A100'.

Hai hàng này không trùng composite key vì SOURCE_SYSTEM khác nhau.

### 11.1. Unique constraint và unique index

Có thể khai báo ràng buộc:

~~~sql
ALTER TABLE customer_external_id
ADD CONSTRAINT uq_customer_external
UNIQUE (source_system, external_id);
~~~

Oracle thường tạo unique index để thực thi constraint nếu chưa có index phù hợp. Unique constraint biểu đạt quy tắc toàn vẹn dữ liệu ở mức schema; unique index là đối tượng index với thuộc tính unique. Khi nghiệp vụ là uniqueness, ưu tiên khai báo constraint rõ ràng để metadata và mục đích dễ hiểu.

### 11.2. Không tạo unique index chỉ vì truy vấn cần nhanh

Nếu tổ hợp cột không thực sự phải duy nhất, unique index sẽ từ chối dữ liệu hợp lệ theo nghiệp vụ. Chọn nonunique composite index nếu mục tiêu chỉ là access path.

## 12. Function-based composite index và biểu thức

Index thông thường trên cột có thể không phù hợp nếu truy vấn áp dụng hàm lên cột:

~~~sql
SELECT *
FROM customers
WHERE UPPER(email) = UPPER(:email);
~~~

Index trên EMAIL không nhất thiết được dùng như một range access trực tiếp cho biểu thức UPPER(EMAIL). Có thể tạo function-based index:

~~~sql
CREATE INDEX ix_customers_upper_email
ON customers (UPPER(email));
~~~

Có thể kết hợp nhiều biểu thức:

~~~sql
CREATE INDEX ix_orders_customer_month
ON orders (customer_id, TRUNC(created_at, 'MM'));
~~~

Truy vấn:

~~~sql
SELECT *
FROM orders
WHERE customer_id = :customer_id
  AND TRUNC(created_at, 'MM') = DATE '2025-01-01';
~~~

có thể phù hợp với index biểu thức nếu các điều kiện và datatype khớp.

### 12.1. Biểu thức phải phù hợp

Oracle cần nhận diện biểu thức trong predicate tương ứng với biểu thức index. Khác biệt về hàm, datatype, implicit conversion hoặc cách viết có thể ảnh hưởng khả năng dùng index.

Nếu truy vấn lọc:

~~~sql
WHERE TRUNC(created_at) = DATE '2025-01-01'
~~~

nhưng index được tạo trên TRUNC(created_at, 'MM'), hai biểu thức không giống nhau về ngữ nghĩa. Không kỳ vọng index tự đáp ứng predicate khác.

### 12.2. Tránh bọc cột không cần thiết

Nếu có thể viết range trực tiếp:

~~~sql
WHERE created_at >= TIMESTAMP '2025-01-01 00:00:00'
  AND created_at <  TIMESTAMP '2025-02-01 00:00:00'
~~~

thường dễ dùng index trên CREATED_AT hơn việc bọc cột bằng TRUNC trong WHERE, đồng thời giữ chính xác thành phần thời gian. Chỉ dùng function-based index khi biểu thức là mẫu truy vấn thực sự cần hỗ trợ.

## 13. Implicit conversion và datatype

Composite index có thể không được khai thác như dự kiến nếu predicate buộc Oracle chuyển đổi datatype ở phía cột được index.

Ví dụ cột CUSTOMER_ID là NUMBER nhưng ứng dụng bind một chuỗi:

~~~sql
WHERE customer_id = '100'
~~~

Oracle có thể thực hiện implicit conversion tùy quy tắc datatype. Nếu chuyển đổi được áp dụng lên cột index, khả năng access path có thể bị ảnh hưởng; nếu chuỗi không chuyển được thành số, truy vấn có thể lỗi.

Trong JDBC, bind đúng datatype:

~~~java
statement.setLong(1, customerId);
~~~

thay vì gửi chuỗi cho cột NUMBER.

Với DATE/TIMESTAMP, dùng bind variable đúng kiểu hoặc literal ANSI rõ ràng. Tránh dựa vào NLS_DATE_FORMAT hoặc NLS_NUMERIC_CHARACTERS để chuyển đổi ngầm.

## 14. Composite index và GROUP BY

Index có thể hỗ trợ truy vấn nhóm nếu thứ tự cột và điều kiện phù hợp:

~~~sql
SELECT customer_id,
       status,
       COUNT(*) AS order_count
FROM orders
WHERE customer_id = :customer_id
GROUP BY customer_id, status;
~~~

Index (CUSTOMER_ID, STATUS) có thể cung cấp các entry theo thứ tự phù hợp để xử lý nhóm trong một số plan.

Tuy nhiên, không đảm bảo Oracle luôn dùng index hoặc tránh sort. Optimizer có thể chọn HASH GROUP BY, SORT GROUP BY, table scan hoặc access path khác dựa trên chi phí.

### 14.1. GROUP BY không cần cùng thứ tự hiển thị

GROUP BY định nghĩa nhóm, không đảm bảo thứ tự output. Nếu ứng dụng cần kết quả sắp xếp, phải thêm ORDER BY:

~~~sql
SELECT customer_id,
       status,
       COUNT(*) AS order_count
FROM orders
GROUP BY customer_id, status
ORDER BY customer_id, status;
~~~

Index có thể giúp cung cấp thứ tự nhưng ORDER BY vẫn là hợp đồng SQL.

## 15. Composite index và index prefix redundancy

Nếu có index (A, B, C), index đó có thể hỗ trợ nhiều truy vấn prefix A và A/B. Vì vậy, một index riêng (A) có thể dư thừa trong một số workload.

Tuy nhiên, không tự động xóa index prefix chỉ dựa vào định nghĩa cột:
- Index (A) nhỏ và nhẹ hơn (A,B,C).
- Index riêng có thể phục vụ truy vấn chỉ đọc A với ít block hơn.
- Unique constraint hoặc foreign key có thể phụ thuộc index.
- Index có khác biệt về compression, partitioning, visibility hoặc direction.
- Workload DML và optimizer plan có thể thay đổi.
- Index rộng hơn có chi phí bảo trì cao hơn.

Trước khi bỏ index prefix, xem:
- Constraint đang dùng index.
- SQL workload và execution plans.
- Index usage monitoring nếu được cấu hình và diễn giải đúng.
- AWR/ASH hoặc công cụ giám sát được cấp phép.
- Kích thước và chi phí DML.
- Các truy vấn cần index hẹp.

## 16. Compression và kích thước composite index

Composite index có thể có nhiều entry lặp lại giá trị cột đầu, chẳng hạn nhiều hàng cùng CUSTOMER_ID. Oracle hỗ trợ index key compression cho một số dạng B-tree index:

~~~sql
CREATE INDEX ix_orders_customer_status_date
ON orders (customer_id, status, created_at)
COMPRESS 2;
~~~

COMPRESS 2 chỉ định số cột leading được nén theo cơ chế prefix compression. Compression có thể giảm dung lượng khi các prefix lặp lại nhiều, nhưng có trade-off về CPU và workload. Cần đo trên dữ liệu thật.

Không nhầm:
- Index key compression là nén phần khóa index.
- Advanced Index Compression có các tính năng/cấp độ khác phụ thuộc edition, license và version.
- Compression không thay thế thiết kế đúng thứ tự cột.

## 17. Thống kê optimizer và selectivity

Optimizer cần thống kê để ước lượng số hàng và chi phí các access path. Với composite index, thống kê có thể bao gồm:
- Số distinct keys.
- Leaf blocks.
- Clustering factor.
- B-level.
- Average leaf blocks per key.
- Histogram trên cột khi phù hợp.
- Extended statistics cho column group khi có tương quan giữa các cột.

Nếu CUSTOMER_ID và STATUS có tương quan, ước lượng độc lập từng predicate có thể sai. Ví dụ một số khách hàng chỉ có trạng thái CLOSED, khách khác có tỷ lệ NEW cao. Thống kê column group có thể giúp optimizer ước lượng cardinality tốt hơn trong một số trường hợp.

### 17.1. Thu thập thống kê bảng và index

Trong môi trường được phép:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'ORDERS',
        cascade => TRUE
    );
END;
/
~~~

CASCADE có thể thu thập thống kê index liên quan. Trong production, DBA cần chọn METHOD_OPT, DEGREE, ESTIMATE_PERCENT, GRANULARITY và lịch thu thập phù hợp; không chạy thu thập thống kê hàng loạt tùy tiện trong giờ cao điểm.

### 17.2. Extended statistics cho nhóm cột

Khi nhiều cột có tương quan, có thể tạo column group statistics:

~~~sql
SELECT DBMS_STATS.CREATE_EXTENDED_STATS(
           USER,
           'ORDERS',
           '(CUSTOMER_ID, STATUS)'
       )
FROM dual;
~~~

Sau đó thu thập lại thống kê bảng theo quy trình phù hợp. Extended statistics là thông tin cho optimizer ước lượng cardinality; nó không tạo index và không thay thế composite index.

## 18. Đọc execution plan để hiểu composite index

Không kết luận index được dùng chỉ vì tên cột xuất hiện trong WHERE. Xem execution plan:

~~~sql
EXPLAIN PLAN FOR
SELECT order_id, created_at
FROM orders
WHERE customer_id = 100
  AND status = 'NEW'
  AND created_at >= DATE '2025-01-01'
  AND created_at <  DATE '2025-02-01';

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

Các operation thường gặp:
- INDEX RANGE SCAN: duyệt một vùng khóa phù hợp.
- INDEX UNIQUE SCAN: tìm khóa duy nhất.
- INDEX SKIP SCAN: bỏ qua các giá trị leading key theo các logical subindex.
- INDEX FULL SCAN: duyệt toàn bộ index theo thứ tự index.
- INDEX FAST FULL SCAN: đọc các block index như một segment, không bảo đảm thứ tự index.
- TABLE ACCESS BY INDEX ROWID: truy cập hàng bảng bằng ROWID từ index.
- TABLE ACCESS FULL: quét bảng.

Tên và lựa chọn operation phụ thuộc phiên bản, cấu trúc index, dữ liệu và optimizer.

### 18.1. Access predicate và filter predicate

Trong DBMS_XPLAN, predicate information có thể phân biệt:
- **Access predicate**: điều kiện dùng để định vị hoặc giới hạn vùng truy cập.
- **Filter predicate**: điều kiện kiểm tra thêm trên các hàng/entry đã truy cập.

Với index (A,B,C) và query WHERE A=:a AND C=:c, A có thể là access predicate còn C là filter tùy plan. Điều này minh họa vì sao cột sau bị bỏ qua trong prefix không nhất thiết thu hẹp vùng tìm kiếm như mong đợi.

### 18.2. Xem cursor plan thực tế

Nếu có quyền và SQL đã chạy:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE'
    )
);
~~~

ALLSTATS LAST hữu ích khi đã thu thập runtime plan statistics phù hợp. So sánh E-Rows và A-Rows để xem ước lượng cardinality có lệch nhiều không. Không phải mọi session đều có quyền đọc cursor plan hoặc thống kê runtime.

### 18.3. EXPLAIN PLAN không phải runtime measurement

EXPLAIN PLAN tạo plan ước lượng trong PLAN_TABLE. Nó không chứng minh thời gian chạy, số buffer gets hoặc số hàng thực tế. Khi đánh giá hiệu năng, dùng runtime statistics và dữ liệu đại diện, đồng thời kiểm soát bind values và bind peeking/adaptive behavior.

## 19. Thử nghiệm composite index trong schema sandbox

Tạo bảng demo để quan sát prefix và thứ tự cột. Các lệnh chỉ dành cho schema thực hành.

### 19.1. Tạo bảng

~~~sql
CREATE TABLE order_index_demo (
    order_id    NUMBER(10)
        CONSTRAINT pk_order_index_demo PRIMARY KEY,
    customer_id NUMBER(8) NOT NULL,
    status      VARCHAR2(12 CHAR) NOT NULL,
    created_at  DATE NOT NULL,
    amount      NUMBER(12,2) NOT NULL,
    channel_id  NUMBER(4)
);
~~~

### 19.2. Nạp dữ liệu mẫu

~~~sql
INSERT INTO order_index_demo
VALUES (1, 10, 'NEW', DATE '2025-01-02', 100, 1);

INSERT INTO order_index_demo
VALUES (2, 10, 'CLOSED', DATE '2025-01-05', 150, 2);

INSERT INTO order_index_demo
VALUES (3, 10, 'NEW', DATE '2025-01-15', 200, 1);

INSERT INTO order_index_demo
VALUES (4, 20, 'NEW', DATE '2025-01-03', 300, 1);

INSERT INTO order_index_demo
VALUES (5, 20, 'CLOSED', DATE '2025-02-01', 400, 2);

INSERT INTO order_index_demo
VALUES (6, 30, 'NEW', DATE '2025-01-20', 250, 3);

INSERT INTO order_index_demo
VALUES (7, 30, 'CLOSED', DATE '2025-02-10', 350, 1);

COMMIT;
~~~

### 19.3. Tạo index theo customer, status, date

~~~sql
CREATE INDEX ix_oid_customer_status_date
ON order_index_demo (customer_id, status, created_at);
~~~

### 19.4. Truy vấn theo leading column

~~~sql
SELECT order_id, customer_id, status
FROM order_index_demo
WHERE customer_id = 10;
~~~

Index có prefix CUSTOMER_ID nên có thể được cân nhắc cho access path này.

### 19.5. Truy vấn theo hai leading columns

~~~sql
SELECT order_id, created_at
FROM order_index_demo
WHERE customer_id = 10
  AND status = 'NEW'
ORDER BY created_at;
~~~

Prefix CUSTOMER_ID/STATUS được cố định; CREATED_AT có thứ tự bên trong vùng đó.

### 19.6. Truy vấn theo equality + range

~~~sql
SELECT order_id, created_at, amount
FROM order_index_demo
WHERE customer_id = 10
  AND status = 'NEW'
  AND created_at >= DATE '2025-01-01'
  AND created_at <  DATE '2025-02-01'
ORDER BY created_at;
~~~

Đây là mẫu truy vấn phù hợp với thứ tự index đã tạo. Vì AMOUNT không nằm trong index, Oracle có thể truy cập bảng theo ROWID để lấy cột này.

### 19.7. Truy vấn chỉ theo cột thứ hai

~~~sql
SELECT order_id, customer_id
FROM order_index_demo
WHERE status = 'NEW';
~~~

Index hiện tại không có leading prefix STATUS. Oracle có thể chọn table scan hoặc access path khác; không ép optimizer dùng index chỉ để chứng minh index tồn tại.

### 19.8. Tạo index thay thế để thử workload theo status

~~~sql
CREATE INDEX ix_oid_status_date
ON order_index_demo (status, created_at);
~~~

Truy vấn:

~~~sql
SELECT order_id, created_at
FROM order_index_demo
WHERE status = 'NEW'
  AND created_at >= DATE '2025-01-01'
  AND created_at <  DATE '2025-02-01';
~~~

Index mới bắt đầu bằng STATUS và CREATED_AT nên phù hợp hơn với prefix của truy vấn này. Hai index có mục tiêu khác nhau; trong hệ thống thật cần đánh giá chi phí duy trì cả hai.

### 19.9. Thu thập thống kê và xem plan

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'ORDER_INDEX_DEMO',
        cascade => TRUE
    );
END;
/

EXPLAIN PLAN FOR
SELECT order_id, created_at
FROM order_index_demo
WHERE customer_id = 10
  AND status = 'NEW';

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

Bảng demo nhỏ có thể khiến optimizer chọn TABLE ACCESS FULL vì chi phí thấp. Đây không phải bằng chứng index sai; dữ liệu quá nhỏ để thể hiện lợi ích của index. Thử nghiệm hiệu năng cần dữ liệu đủ lớn và phân bố đại diện.

### 19.10. Dọn đối tượng sandbox

~~~sql
DROP TABLE order_index_demo PURGE;
~~~

Chỉ xóa bảng sandbox do bài học tạo khi chắc chắn không cần dữ liệu. DROP TABLE là DDL có implicit commit; cleanup nên thực hiện riêng.

## 20. Các lỗi thiết kế composite index thường gặp

| Vấn đề | Vì sao xảy ra | Cách xử lý |
| --- | --- | --- |
| Query chỉ lọc cột thứ hai nhưng index bắt đầu bằng cột khác | Không có leading prefix trực tiếp | Đánh giá index bắt đầu bằng cột truy vấn hoặc skip scan nếu NDV leading thấp |
| Index quá rộng | Thêm nhiều cột chỉ để cover vài query | Đo lợi ích đọc so với dung lượng và chi phí DML |
| Cột range đứng trước equality | Predicate phía sau khó thu hẹp vùng liên tục | Cân nhắc equality trước range theo workload |
| Chọn cột đầu chỉ vì cardinality cao | Bỏ qua các query cần prefix khác | Phân tích workload và prefix thường dùng |
| Dùng một index cho mọi query | Các truy vấn có mẫu lọc khác nhau | Thiết kế một tập index tối thiểu theo workload |
| Bọc cột bằng hàm | Predicate không khớp index cột gốc | Viết range trực tiếp hoặc tạo function-based index |
| Bind sai datatype | Implicit conversion có thể làm giảm khả năng dùng index | Bind đúng NUMBER/DATE/TIMESTAMP |
| Giả định index scan luôn trả đúng thứ tự | Thiếu ORDER BY hoặc direction/NULL không khớp | Viết ORDER BY và kiểm tra plan |
| Bỏ index prefix không kiểm tra | Index hẹp có thể rẻ hơn hoặc hỗ trợ constraint | Xem workload, constraint, usage và plan |
| Dùng skip scan làm thiết kế chính | Leading column có thể có nhiều distinct values | Tạo index phù hợp leading predicate thường xuyên |
| Tạo unique index cho mục đích tốc độ | Có thể vô tình áp đặt uniqueness nghiệp vụ | Dùng nonunique index nếu không cần ràng buộc |
| Tin EXPLAIN PLAN là runtime | Plan ước lượng có thể khác thực tế | Xem cursor plan và runtime statistics |

## 21. Quy trình thiết kế thứ tự cột

Khi quyết định tạo composite index, thực hiện theo trình tự:

1. Thu thập các câu SQL thực tế có tần suất hoặc chi phí cao.
2. Ghi lại các cột xuất hiện trong equality predicates, range predicates, JOIN, ORDER BY và GROUP BY.
3. Xác định các prefix truy vấn cần hỗ trợ, đặc biệt các truy vấn chỉ lọc một phần cột.
4. Đặt cột equality phổ biến ở đầu khi điều đó hỗ trợ nhiều prefix hữu ích.
5. Cân nhắc cột range sau các equality prefix nếu mẫu truy vấn phù hợp.
6. Xem selectivity, cardinality, phân bố dữ liệu và tương quan giữa các cột.
7. Xem thứ tự ORDER BY, ASC/DESC và NULLS FIRST/LAST.
8. Đánh giá query có thể được cover bởi index hay cần table access.
9. Tính chi phí dung lượng, INSERT/UPDATE/DELETE và redo/undo.
10. Kiểm tra index hiện có, unique/primary key/foreign key và prefix redundancy.
11. Thu thập thống kê phù hợp.
12. Xem execution plan và runtime statistics trên dữ liệu đại diện.
13. Thử các bind values có selectivity khác nhau.
14. Chỉ giữ index mang lại lợi ích đo được cho workload tổng thể.

### 21.1. Bảng quyết định nhanh

| Mẫu truy vấn | Thứ tự index thường đáng đánh giá |
| --- | --- |
| WHERE A = :a | (A, ...) |
| WHERE A = :a AND B = :b | (A, B, ...) hoặc (B, A, ...) tùy prefix workload |
| WHERE A = :a AND B BETWEEN ... | (A, B, ...) |
| WHERE A = :a AND B = :b AND C BETWEEN ... | (A, B, C) |
| WHERE B = :b | Index bắt đầu bằng B hoặc access path khác |
| WHERE A = :a ORDER BY B | (A, B) |
| WHERE A = :a ORDER BY B DESC | Đánh giá direction (A, B DESC) hoặc scan phù hợp |
| WHERE A = :a AND C = :c, index (A,B,C) | A có thể định vị; C có thể là filter do B bị bỏ qua |
| WHERE B = :b, index (A,B) với A có ít distinct values | Có thể cân nhắc skip scan, cần đo |

Bảng chỉ là điểm bắt đầu. Optimizer quyết định plan dựa trên chi phí; index phù hợp về mặt prefix không bảo đảm sẽ được chọn trong mọi lần chạy.

## 22. Những nhầm lẫn thường gặp

**Index (A,B,C) giống index (B,A,C).** Không đúng. Thứ tự khóa khác nhau, leading prefix khác nhau và các query được hỗ trợ trực tiếp cũng khác.

**Có index chứa cột B thì truy vấn WHERE B = ... luôn dùng được index range scan hiệu quả.** Không đúng nếu B không phải leading column. Oracle có thể dùng skip scan hoặc scan index theo cách khác, nhưng không tương đương prefix trực tiếp.

**Cột có cardinality cao nhất luôn phải đứng đầu.** Không đúng. Phải xét các prefix truy vấn, equality/range, ORDER BY, selectivity và workload tổng thể.

**Predicate trên cột sau range hoàn toàn vô dụng.** Không đúng. Nó vẫn có thể làm filter trên index/table hoặc hỗ trợ covering; chỉ không nhất thiết thu hẹp vùng range theo cách prefix.

**Equality luôn phải đứng trước mọi cột khác trong mọi index.** Đây là heuristic hữu ích cho nhiều query pattern, không phải luật cứng. Cần xét query nào quan trọng và thứ tự prefix cần hỗ trợ.

**Index skip scan bảo đảm cột leading không quan trọng.** Không đúng. Skip scan có chi phí phụ thuộc số distinct leading values và optimizer chỉ chọn khi phù hợp.

**Index (A,B,C) luôn thay thế được index (A).** Không phải lúc nào. Index riêng A hẹp hơn, có thể rẻ hơn và có thể phục vụ constraint/workload riêng.

**Index scan tự bảo đảm thứ tự kết quả.** Không đúng theo hợp đồng SQL. Cần ORDER BY cuối cùng.

**DESC index chỉ cần đảo toàn bộ index.** Không đúng với mọi thứ tự mixed ASC/DESC; direction của từng cột có thể cần được thiết kế phù hợp.

**B-tree index lưu hàng có mọi cột khóa NULL.** Không đúng. Oracle B-tree không tạo entry cho hàng mà tất cả các cột khóa đều NULL.

**Thêm mọi cột SELECT vào index luôn làm truy vấn nhanh hơn.** Không đúng. Index rộng làm tăng storage và chi phí DML; phải đo lợi ích covering.

**Một index composite chỉ phục vụ đúng một truy vấn.** Không đúng. Nó có thể phục vụ nhiều leading prefixes và nhiều query pattern liên quan.

**EXPLAIN PLAN chọn index là chứng minh truy vấn nhanh.** Không đúng. Cần xem runtime, logical reads, cardinality thực tế và workload.

## 23. Bài tập tự luyện

1. Tạo index (CUSTOMER_ID, STATUS, CREATED_AT). Liệt kê tất cả leading prefixes.
2. Vì sao truy vấn chỉ có WHERE STATUS='NEW' không có prefix trực tiếp trên index trên?
3. Giải thích lexicographic order bằng ba cột A, B, C và dữ liệu ví dụ.
4. Viết truy vấn equality trên CUSTOMER_ID và STATUS, range trên CREATED_AT.
5. Nếu truy vấn chỉ lọc CUSTOMER_ID, STATUS và CREATED_AT đều không có điều kiện, index nào có thể hỗ trợ?
6. Nếu truy vấn chỉ lọc PRODUCT_ID nhưng index bắt đầu bằng REGION_ID, những access path nào Oracle có thể cân nhắc?
7. Index skip scan hoạt động như thế nào? Vì sao leading column có cardinality thấp có thể giúp?
8. Vì sao không nên dựa vào skip scan nếu truy vấn theo cột thứ hai xảy ra thường xuyên?
9. Giải thích vì sao equality columns thường được đặt trước range column.
10. Với A BETWEEN ... AND ... AND B=:b, predicate B có thể được xử lý thế nào nếu index (A,B)?
11. Index (CUSTOMER_ID, CREATED_AT) có thể hỗ trợ WHERE CUSTOMER_ID=:id ORDER BY CREATED_AT vì sao?
12. Vì sao index (A,B) không tự cung cấp thứ tự toàn cục cho ORDER BY B?
13. So sánh (A ASC, B ASC) và (A ASC, B DESC) với truy vấn ORDER BY hỗn hợp.
14. Oracle mặc định đặt NULL ở đâu với ASC và DESC?
15. Vì sao B-tree index một cột không lưu entry cho hàng có cột đó NULL?
16. Với index (A,B), hàng A=10/B=NULL có entry không? Giải thích.
17. So sánh unique composite index và unique constraint.
18. Khi nào function-based composite index phù hợp?
19. Vì sao bind NUMBER bằng String có thể ảnh hưởng index access?
20. Một query có SELECT chỉ các cột đã nằm trong index. Khi nào Oracle có thể tránh TABLE ACCESS BY ROWID?
21. Vì sao không nên thêm mọi cột vào index chỉ để tạo covering index?
22. Một index (A,B,C) đã tồn tại. Khi nào index riêng (A) có thể vẫn hữu ích?
23. Giải thích clustering factor ảnh hưởng lựa chọn index range scan như thế nào.
24. Vì sao thống kê column group có thể giúp khi A và B tương quan?
25. Xem DBMS_XPLAN và phân biệt access predicate với filter predicate.
26. Tại sao EXPLAIN PLAN không đủ để kết luận hiệu năng?
27. Thiết kế index cho query lọc CUSTOMER_ID, STATUS và khoảng CREATED_AT.
28. Thiết kế index cho query lọc STATUS và khoảng CREATED_AT toàn hệ thống.
29. Nếu cả hai truy vấn trên đều quan trọng, có nên tạo hai index không? Nêu trade-off.
30. Xây dựng kế hoạch thử nghiệm index mới bằng workload đại diện và runtime statistics.

**Composite index được sắp xếp theo thứ tự các cột khai báo. Leading column và các leading prefixes quyết định những vùng khóa Oracle có thể định vị trực tiếp; equality, range, ORDER BY, NULL và skip scan đều chịu ảnh hưởng từ thứ tự đó.** Hãy chọn thứ tự theo workload thật, cân bằng khả năng truy cập với chi phí ghi và dung lượng, rồi xác nhận bằng thống kê cùng execution plan/runtime. Không có một thứ tự cột tối ưu cho mọi truy vấn; index tốt là index hỗ trợ đúng những mẫu truy cập quan trọng với tổng chi phí phù hợp.
