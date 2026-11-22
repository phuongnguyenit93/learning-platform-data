# Query rewrite và điều kiện tương thích, thống kê, tính năng trong Oracle Database

Oracle Database có thể biến đổi một câu SQL để tìm cách thực thi hiệu quả hơn mà vẫn giữ nguyên kết quả theo ngữ nghĩa SQL. Quá trình này thường được gọi là **query transformation** hoặc **query rewrite**. Một trường hợp đặc biệt quan trọng là **materialized view query rewrite**: optimizer có thể thay một truy vấn trên các bảng nguồn bằng cách đọc dữ liệu đã được tính trước trong materialized view (MV).

Khả năng rewrite không chỉ phụ thuộc vào việc hai câu SQL trông giống nhau. Oracle phải chứng minh phép biến đổi tương đương trong điều kiện dữ liệu và quyền hiện có. Các yếu tố như khóa chính/khóa ngoại, NOT NULL, trạng thái materialized view, mức độ tin cậy của constraint, kiểu aggregate, hàm được sử dụng, thống kê optimizer và phiên bản tính năng đều có thể ảnh hưởng.

Một kế hoạch tốt cũng cần thống kê đủ chính xác. Optimizer dùng số hàng, độ chọn lọc, histogram, thống kê index và system statistics để ước lượng chi phí. Nếu thống kê cũ hoặc thiếu tương quan giữa các cột, optimizer có thể chọn sai join order, join method hoặc không chọn được materialized view phù hợp.

Bài học phân biệt các khái niệm thường bị gộp chung:

- **Query transformation:** optimizer biến đổi cấu trúc truy vấn, ví dụ view merging hoặc subquery unnesting.
- **Materialized view query rewrite:** optimizer thay truy vấn bằng dữ liệu đã tính trước trong MV khi đủ điều kiện.
- **Optimizer statistics:** dữ liệu mô tả bảng, cột, index và hệ thống để ước lượng cardinality/cost.
- **Compatibility và optimizer features:** thiết lập phiên bản database và bộ hành vi optimizer; chúng không đồng nghĩa với nhau.

## 1. Query rewrite là gì?

### 1.1. Mục tiêu của optimizer

Một câu SQL mô tả **kết quả cần lấy**, không bắt buộc mô tả chính xác thứ tự thao tác vật lý. Oracle optimizer phân tích câu lệnh, đánh giá các phương án và chọn execution plan dựa trên chi phí ước lượng.

Ví dụ:

```sql
SELECT c.customer_id,
       c.customer_name
FROM customers c
WHERE c.customer_id IN (
    SELECT o.customer_id
    FROM orders o
    WHERE o.status = 'COMPLETED'
);
```

Optimizer có thể biến đổi subquery thành semi-join nếu phép biến đổi bảo toàn semantics. Câu SQL vẫn là câu người dùng gửi, nhưng plan có thể không còn cấu trúc subquery như ban đầu.

### 1.2. Query transformation và materialized view rewrite

| Khái niệm | Nội dung | Ví dụ |
|---|---|---|
| Query transformation | Thay đổi cách biểu diễn nội bộ của truy vấn | View merging, predicate pushing, subquery unnesting |
| Materialized view rewrite | Dùng kết quả đã lưu trong MV để đáp ứng truy vấn | Dùng bảng tổng hợp theo tháng thay vì đọc toàn bộ fact table |

Query transformation là hoạt động nội bộ của optimizer trong quá trình tối ưu SQL. Materialized view rewrite còn phụ thuộc vào một đối tượng schema cụ thể đã được tạo và duy trì.

### 1.3. Vì sao rewrite có thể nhanh hơn?

Giả sử bảng SALES_FACT có hàng trăm triệu giao dịch. Một báo cáo lặp đi lặp lại yêu cầu tổng doanh thu theo khu vực và sản phẩm. Nếu mỗi lần chạy đều quét fact table, join dimension và group hàng triệu bản ghi, chi phí có thể cao.

Một materialized view lưu sẵn tổng hợp:

```sql
SELECT region_id,
       product_id,
       SUM(amount) AS total_amount
FROM sales_fact
GROUP BY region_id, product_id;
```

Nếu truy vấn cần kết quả tương thích với mức tổng hợp đó, Oracle có thể đọc ít hàng hơn từ MV. Lợi ích phụ thuộc vào kích thước MV, độ mới dữ liệu, index, partitioning, thống kê và chi phí refresh.

## 2. Các dạng query transformation thường gặp

### 2.1. View merging

View merging là biến đổi optimizer có thể đưa nội dung của inline view vào truy vấn ngoài để mở rộng không gian tìm kiếm join order và predicate.

```sql
SELECT v.customer_id,
       v.total_amount
FROM (
    SELECT customer_id,
           SUM(total_amount) AS total_amount
    FROM orders
    WHERE status = 'COMPLETED'
    GROUP BY customer_id
) v
WHERE v.total_amount > 10000000;
```

Optimizer xem xét liệu có thể merge view hay không. Aggregate, DISTINCT, analytic function, row limiting và các cấu trúc khác có thể giới hạn khả năng merge vì chúng tạo ranh giới ngữ nghĩa cần được bảo toàn. Không phải inline view nào cũng được merge.

### 2.2. Predicate pushing

Predicate pushing cố gắng đưa điều kiện lọc gần nguồn dữ liệu hơn để giảm số hàng trung gian:

```sql
SELECT *
FROM (
    SELECT order_id, customer_id, status
    FROM orders
) v
WHERE v.status = 'COMPLETED';
```

Điều kiện status có thể được áp dụng trực tiếp trên bảng orders. Với view phức tạp, predicate pushdown có thể bị giới hạn bởi outer join, aggregate hoặc biểu thức làm thay đổi semantics.

### 2.3. Subquery unnesting

Optimizer có thể chuyển một số subquery thành join:

```sql
SELECT c.customer_id,
       c.customer_name
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'COMPLETED'
);
```

Một semi-join có thể thực hiện kiểm tra tồn tại hiệu quả hơn việc đánh giá subquery theo cách ngây thơ. Subquery chứa aggregate, ROWNUM, set operator hoặc cấu trúc đặc biệt có thể không được unnest tự động.

### 2.4. Join elimination

Trong một số trường hợp, optimizer có thể bỏ một join nếu join đó không ảnh hưởng đến kết quả. Ví dụ, bảng con chỉ được join để xác nhận quan hệ và không có cột của bảng đó được dùng; constraint phù hợp có thể chứng minh quan hệ cần thiết.

Điều kiện PK/FK, tính duy nhất, NOT NULL và trạng thái ENABLED/VALIDATED/RELY của constraint có thể ảnh hưởng khả năng chứng minh. Không khai báo constraint sai sự thật để ép optimizer bỏ join: kết quả truy vấn có thể sai nếu dữ liệu không đáp ứng giả định.

### 2.5. OR expansion

Điều kiện OR đôi khi được biến đổi thành các nhánh truy vấn riêng, thường có dạng tương tự UNION ALL:

```sql
SELECT order_id
FROM orders
WHERE customer_id = :customer_id
   OR status = 'URGENT';
```

Optimizer có thể tách nhánh để sử dụng index/access path phù hợp cho từng predicate. Phép biến đổi phải xử lý đúng trường hợp một hàng thỏa cả hai nhánh để tránh nhân đôi kết quả.

### 2.6. Star transformation

Trong mô hình data warehouse dạng star schema, fact table liên kết với nhiều dimension. Star transformation có thể giúp lọc fact rows qua bitmap indexes và dimension predicates trong một số cấu hình phù hợp.

Khả năng này phụ thuộc cấu trúc schema, loại index, tính chọn lọc, thống kê và thiết lập optimizer. Không phải mọi star schema đều tự động dùng star transformation.

### 2.7. Materialized view query rewrite

Đây là trọng tâm của bài: câu truy vấn trên bảng nguồn có thể được đáp ứng bằng MV đã tính trước nếu Oracle chứng minh MV chứa đủ thông tin và kết quả tương đương.

Ví dụ, truy vấn:

```sql
SELECT region_id,
       SUM(amount) AS revenue
FROM sales_fact
WHERE product_id = 10
GROUP BY region_id;
```

có thể được viết lại để đọc MV đã tổng hợp theo region và product rồi tổng hợp tiếp theo region. MV cần lưu đúng aggregate cần thiết và các cột nhóm/lọc cần thiết.

## 3. Materialized view query rewrite

### 3.1. Materialized view khác view thường

View thường lưu định nghĩa SELECT; khi truy vấn, Oracle thường truy cập các đối tượng nền theo định nghĩa đó. Materialized view lưu kết quả truy vấn tại thời điểm refresh.

| Đặc điểm | View | Materialized view |
|---|---|---|
| Lưu kết quả dữ liệu riêng | Không lưu bản sao kết quả | Có lưu kết quả |
| Cần refresh | Không | Có |
| Có thể có index trên kết quả | Không trực tiếp như bảng | Có thể tạo index |
| Dữ liệu có thể cũ | Phụ thuộc dữ liệu nguồn tại thời điểm query | Có thể stale giữa các lần refresh |
| Dùng cho query rewrite | Không phải đối tượng MV rewrite | Có thể được optimizer sử dụng nếu đủ điều kiện |

MV tiêu tốn storage và chi phí refresh. Cần cân bằng thời gian trả lời báo cáo với độ mới dữ liệu và chi phí duy trì.

### 3.2. Tạo bảng fact mẫu

Thực hiện trong schema lab:

```sql
CREATE TABLE sales_fact_demo (
    sale_id     NUMBER(12) CONSTRAINT pk_sales_fact_demo PRIMARY KEY,
    sale_date   DATE NOT NULL,
    region_id   NUMBER(6) NOT NULL,
    product_id  NUMBER(8) NOT NULL,
    amount      NUMBER(14, 2) NOT NULL,
    CONSTRAINT ck_sales_fact_demo_amount CHECK (amount >= 0)
);

INSERT INTO sales_fact_demo VALUES
    (1, DATE '2026-01-05', 10, 100, 1200);
INSERT INTO sales_fact_demo VALUES
    (2, DATE '2026-01-08', 10, 100, 800);
INSERT INTO sales_fact_demo VALUES
    (3, DATE '2026-01-10', 20, 100, 1500);
INSERT INTO sales_fact_demo VALUES
    (4, DATE '2026-02-03', 10, 200, 2000);
INSERT INTO sales_fact_demo VALUES
    (5, DATE '2026-02-12', 20, 100, 700);
COMMIT;
```

### 3.3. Tạo materialized view tổng hợp

```sql
CREATE MATERIALIZED VIEW sales_region_product_mv
BUILD IMMEDIATE
REFRESH COMPLETE ON DEMAND
ENABLE QUERY REWRITE
AS
SELECT region_id,
       product_id,
       SUM(amount) AS total_amount,
       COUNT(*) AS sale_count
FROM sales_fact_demo
GROUP BY region_id, product_id;
```

MV được tạo ngay (BUILD IMMEDIATE), refresh bằng phương thức COMPLETE khi được yêu cầu, và được đánh dấu cho phép query rewrite. Các tùy chọn refresh khác có thể phù hợp trong hệ thống thật; lựa chọn phải dựa trên tính chất thay đổi của nguồn và chi phí vận hành.

### 3.4. Truy vấn nguồn có thể rewrite

```sql
SELECT region_id,
       SUM(amount) AS revenue
FROM sales_fact_demo
WHERE product_id = 100
GROUP BY region_id;
```

MV có dữ liệu tổng hợp theo region và product. Vì truy vấn lọc product 100 rồi cộng amount theo region, Oracle có thể đọc các hàng tương ứng trong MV và tổng hợp lại. Điều kiện chính xác để rewrite được quyết định bởi optimizer và cấu trúc MV.

### 3.5. Bật query rewrite trong session

```sql
ALTER SESSION SET query_rewrite_enabled = TRUE;
ALTER SESSION SET query_rewrite_integrity = ENFORCED;
```

QUERY_REWRITE_ENABLED cho phép optimizer xem xét query rewrite. Giá trị TRUE cho phép rewrite khi optimizer đánh giá có lợi và đủ điều kiện. FALSE tắt khả năng này; FORCE yêu cầu optimizer ưu tiên rewrite trong phạm vi có thể, nhưng không thể làm một phép rewrite không tương đương trở nên hợp lệ.

### 3.6. Kiểm tra execution plan

```sql
EXPLAIN PLAN FOR
SELECT region_id,
       SUM(amount) AS revenue
FROM sales_fact_demo
WHERE product_id = 100
GROUP BY region_id;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
```

Nếu rewrite được chọn, plan có thể thể hiện truy cập materialized view thay vì fact table. Tên operation và hình dạng plan thay đổi theo release, thống kê, hint và optimizer environment; không nên chỉ tìm một dòng operation cố định rồi kết luận.

Để quan sát plan thực tế của cursor:

```sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       region_id,
       SUM(amount) AS revenue
FROM sales_fact_demo
WHERE product_id = 100
GROUP BY region_id;

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE'
    )
);
```

Quyền đọc cursor và thống kê thực thi có thể cần được DBA cấp. EXPLAIN PLAN cho plan ước lượng; DISPLAY_CURSOR có thể cho thấy plan đã thực thi cùng số liệu thực tế nếu được thu thập.

## 4. Điều kiện để materialized view được dùng rewrite

### 4.1. Query rewrite phải được bật

Kiểm tra thiết lập:

```sql
SELECT name, value
FROM v$parameter
WHERE name IN (
    'query_rewrite_enabled',
    'query_rewrite_integrity',
    'optimizer_features_enable',
    'compatible'
)
ORDER BY name;
```

Truy cập V$ view cần quyền phù hợp. Nếu không có quyền, nhờ DBA cung cấp giá trị cấu hình.

### 4.2. MV phải cho phép query rewrite

MV được tạo hoặc thay đổi với thuộc tính ENABLE QUERY REWRITE. Có thể xem metadata:

```sql
SELECT mview_name,
       rewrite_enabled,
       refresh_mode,
       refresh_method,
       staleness,
       compile_state
FROM user_mviews
WHERE mview_name = 'SALES_REGION_PRODUCT_MV';
```

Tên cột metadata có thể khác giữa các view/version; tham khảo dictionary view của release đang dùng. REWRITE_ENABLED cho biết MV có được bật cho rewrite hay không, còn STALENESS giúp đánh giá trạng thái mới/cũ.

### 4.3. MV phải chứa đủ thông tin

Oracle phải suy ra được kết quả truy vấn từ dữ liệu MV. Ví dụ:

- Nếu truy vấn lọc theo product_id, MV cần lưu product_id hoặc một cấu trúc cho phép suy ra điều kiện đó.
- Nếu truy vấn cần tổng amount, MV cần lưu SUM(amount) hoặc các aggregate đủ để tái tính.
- Nếu truy vấn cần group theo region, MV phải giữ region_id ở grain phù hợp.
- Nếu truy vấn cần join dimension, MV phải có dữ liệu hoặc quan hệ đủ để tái dựng kết quả.

MV tổng hợp theo (region_id, product_id) có thể hỗ trợ truy vấn tổng hợp theo region sau khi lọc product. MV chỉ tổng hợp theo region không thể trả kết quả riêng cho từng product nếu thông tin product đã bị mất.

### 4.4. Query và MV phải tương đương về ngữ nghĩa

Optimizer phải bảo đảm kết quả giữ đúng:

- Giá trị và kiểu dữ liệu.
- Số hàng và tính duy nhất.
- NULL semantics.
- Điều kiện lọc và join.
- Aggregate, grouping và duplicate semantics.
- Các biểu thức có thể thay đổi theo session hoặc thời gian.

Hai câu SQL nhìn gần giống nhau chưa chắc tương đương. Ví dụ, đổi vị trí predicate quanh outer join có thể làm thay đổi hàng được giữ; thay UNION ALL bằng UNION có thể loại hàng trùng; aggregate ở grain khác có thể không tái dựng được kết quả gốc.

### 4.5. Trạng thái freshness và refresh

Với QUERY_REWRITE_INTEGRITY = ENFORCED, Oracle chỉ dùng MV khi có thể đảm bảo dữ liệu và quan hệ được sử dụng là hợp lệ theo mức integrity này. MV stale có thể không được dùng.

Refresh MV:

```sql
BEGIN
    DBMS_MVIEW.REFRESH(
        list   => 'SALES_REGION_PRODUCT_MV',
        method => 'C'
    );
END;
/
```

C yêu cầu complete refresh trong ví dụ. Có thể chọn fast refresh nếu MV và nguồn đáp ứng điều kiện; không phải MV nào cũng hỗ trợ fast refresh.

### 4.6. Materialized view log và query rewrite không phải một điều kiện

Materialized view log thường cần cho fast refresh theo thay đổi ở bảng nguồn. Nó không phải điều kiện phổ quát bắt buộc cho mọi trường hợp query rewrite. Một MV có thể được refresh COMPLETE ON DEMAND và vẫn là ứng viên rewrite khi đủ điều kiện freshness/integrity.

Phân biệt:

- **Query rewrite:** dùng dữ liệu đã lưu trong MV để đáp ứng SELECT.
- **Fast refresh:** cập nhật MV bằng cách áp dụng thay đổi tăng dần từ nguồn.
- **Complete refresh:** tính lại toàn bộ kết quả MV.

Thiết kế refresh strategy và query rewrite strategy có liên quan nhưng là hai quyết định khác nhau.

## 5. QUERY_REWRITE_INTEGRITY và độ tin cậy

### 5.1. ENFORCED

ENFORCED yêu cầu Oracle dựa trên các quan hệ được thực thi và dữ liệu MV đáp ứng điều kiện freshness phù hợp. Đây là lựa chọn thận trọng cho hệ thống nghiệp vụ cần kết quả nhất quán.

### 5.2. TRUSTED

TRUSTED cho phép optimizer tin cậy một số quan hệ/khai báo mà database không nhất thiết xác minh đầy đủ như ENFORCED, ví dụ metadata dimension hoặc constraint được đánh dấu RELY trong các trường hợp phù hợp. Điều này có thể mở rộng khả năng rewrite, nhưng chỉ an toàn khi dữ liệu thực sự tuân thủ giả định.

Không khai báo RELY chỉ để ép rewrite nếu dữ liệu không đáp ứng constraint. Optimizer có thể dựa vào giả định đó và tạo kết quả không đúng.

### 5.3. STALE_TOLERATED

STALE_TOLERATED cho phép sử dụng một số MV stale theo chính sách của Oracle. Kết quả có thể phản ánh dữ liệu tại lần refresh trước thay vì dữ liệu nguồn mới nhất.

Chỉ cân nhắc khi nghiệp vụ chấp nhận độ trễ dữ liệu, ví dụ báo cáo tổng hợp không yêu cầu realtime. Không dùng cho số dư, tồn kho hoặc quyết định cần dữ liệu hiện thời nếu chưa có chấp thuận nghiệp vụ rõ ràng.

### 5.4. Bảng so sánh

| Integrity | Mức tin cậy | Rủi ro cần hiểu |
|---|---|---|
| ENFORCED | Dựa vào ràng buộc được thực thi và MV phù hợp freshness | Có thể bỏ lỡ rewrite nếu MV stale hoặc quan hệ chưa được xác minh |
| TRUSTED | Tin cậy thêm metadata/quan hệ được khai báo | Dữ liệu vi phạm giả định có thể làm kết quả rewrite sai |
| STALE_TOLERATED | Cho phép một số kết quả MV stale | Có thể trả dữ liệu cũ hơn bảng nguồn |

Giá trị mặc định và khả năng cụ thể có thể khác theo phiên bản/cấu hình. Hãy xem parameter thật của môi trường thay vì dựa vào một giá trị giả định.

## 6. Constraint và metadata ảnh hưởng rewrite

### 6.1. Primary key và unique constraint

PK/UNIQUE cung cấp thông tin về tính duy nhất. Optimizer có thể dùng metadata này để suy luận cardinality, loại bỏ join dư thừa hoặc chứng minh một phép biến đổi.

Ví dụ:

```sql
CREATE TABLE region_dim_demo (
    region_id   NUMBER(6)
        CONSTRAINT pk_region_dim_demo PRIMARY KEY,
    region_name VARCHAR2(80 CHAR) NOT NULL
);

CREATE TABLE sales_fact_fk_demo (
    sale_id   NUMBER(12)
        CONSTRAINT pk_sales_fact_fk_demo PRIMARY KEY,
    region_id NUMBER(6) NOT NULL,
    amount    NUMBER(14, 2) NOT NULL,
    CONSTRAINT fk_sales_region_demo
        FOREIGN KEY (region_id)
        REFERENCES region_dim_demo(region_id)
);
```

### 6.2. ENABLED, VALIDATED và RELY

Constraint có các trạng thái/thuộc tính ảnh hưởng cách Oracle thực thi và tin cậy:

- ENABLE: database thực thi constraint đối với thay đổi theo trạng thái constraint.
- VALIDATE: dữ liệu hiện có đã được kiểm tra theo constraint.
- NOVALIDATE: không xác nhận toàn bộ dữ liệu cũ, dù các DML mới có thể vẫn được kiểm soát tùy trạng thái.
- RELY: cho optimizer tin cậy constraint trong các ngữ cảnh phù hợp, đặc biệt khi query rewrite integrity là TRUSTED.

ENABLE NOVALIDATE không đồng nghĩa mọi hàng hiện có đều hợp lệ. Khi dùng constraint để hỗ trợ rewrite, cần hiểu rõ dữ liệu cũ và đường nạp dữ liệu.

### 6.3. NOT NULL và NULL semantics

NOT NULL giúp optimizer chứng minh một số phép biến đổi an toàn. Nếu một cột nullable, phép join, filter và aggregate có thể có hành vi khác so với giả định cột luôn có giá trị.

Ví dụ, COUNT(*) và COUNT(column) không tương đương khi column có thể NULL:

```sql
SELECT region_id,
       COUNT(*) AS all_rows,
       COUNT(product_id) AS rows_with_product
FROM sales_fact_demo
GROUP BY region_id;
```

Một MV lưu COUNT(*) không tự động thay được mọi truy vấn COUNT(product_id). MV cần lưu aggregate đủ để tái dựng đúng kết quả, bao gồm cách xử lý NULL.

### 6.4. Dimension và hierarchy

Trong data warehouse, dimension metadata có thể mô tả hierarchy và quan hệ phụ thuộc như city → state → country. Query rewrite có thể tận dụng metadata để trả lời truy vấn ở mức tổng hợp khác, nhưng các quan hệ phải đúng và được khai báo ở trạng thái phù hợp.

Dimension không phải chỉ là bảng có tên *_DIM. Cần định nghĩa hierarchy, level và attribute relationship bằng metadata Oracle tương ứng, đồng thời bảo đảm dữ liệu thật sự tuân thủ.

## 7. Các yếu tố làm query rewrite không thể thực hiện

Một truy vấn có thể không rewrite dù MV đã tồn tại:

1. QUERY_REWRITE_ENABLED = FALSE.
2. MV không có ENABLE QUERY REWRITE.
3. MV stale trong khi integrity yêu cầu dữ liệu fresh.
4. MV thiếu cột lọc, cột group hoặc aggregate cần thiết.
5. Grain của MV không đủ để tái dựng kết quả.
6. Join path hoặc constraint không đủ để chứng minh tương đương.
7. NULL, outer join, duplicate hoặc aggregate semantics khác nhau.
8. Biểu thức dùng hàm không deterministic hoặc phụ thuộc session/time.
9. MV không hợp lệ, chưa compile hoặc refresh thất bại.
10. Optimizer đánh giá truy cập bảng nguồn rẻ hơn MV.
11. Hint hoặc parameter đang hạn chế transformation.
12. Phiên bản database không hỗ trợ tính năng/cú pháp cần thiết.

Không phải mọi trường hợp không rewrite đều là lỗi. Optimizer có thể chủ động chọn plan khác vì chi phí ước lượng thấp hơn.

### 7.1. Hàm deterministic và biểu thức phụ thuộc môi trường

MV hoặc query có thể dùng biểu thức hàm. Nếu hàm phụ thuộc thời gian, session, NLS, trạng thái package hoặc dữ liệu ngoài database, kết quả có thể thay đổi dù hàng nguồn không đổi.

Khai báo PL/SQL function là DETERMINISTIC là cam kết của lập trình viên; Oracle không tự chứng minh hàm luôn trả cùng kết quả cho cùng input. Không đánh dấu deterministic một hàm đọc bảng khác hoặc phụ thuộc session chỉ để mở rộng rewrite.

### 7.2. ROWNUM, row limiting và analytic function

Các cấu trúc như ROWNUM, FETCH FIRST/OFFSET, analytic function, hierarchical query hoặc set operator có semantics thứ tự/nhóm riêng. Chúng có thể giới hạn transformation hoặc yêu cầu optimizer giữ ranh giới query block.

Khi rewrite không xảy ra, hãy xem cấu trúc SQL cụ thể và thông báo từ công cụ giải thích; không xóa predicate hay đổi thứ tự join chỉ để ép plan mà chưa chứng minh kết quả tương đương.

## 8. Giải thích vì sao rewrite không xảy ra

### 8.1. DBMS_MVIEW.EXPLAIN_REWRITE

Oracle cung cấp DBMS_MVIEW.EXPLAIN_REWRITE để phân tích khả năng một truy vấn được rewrite với MV cụ thể. Trong các môi trường cần dùng, DBA thường tạo bảng kết quả bằng script quản trị utlxrw.sql trong thư mục script của Oracle Home; tên bảng mặc định thường là REWRITE_TABLE.

Ví dụ:

```sql
BEGIN
    DBMS_MVIEW.EXPLAIN_REWRITE(
        query => q'[
            SELECT region_id, SUM(amount)
            FROM sales_fact_demo
            WHERE product_id = 100
            GROUP BY region_id
        ]',
        mv => 'SALES_REGION_PRODUCT_MV',
        statement_id => 'SALES_REWRITE_TEST'
    );
END;
/

SELECT statement_id,
       message
FROM rewrite_table
WHERE statement_id = 'SALES_REWRITE_TEST'
ORDER BY sequence;
```

EXPLAIN_REWRITE cho thông tin về khả năng và lý do rewrite theo API/version. Kiểm tra đúng tên MV, schema, quyền và cấu trúc bảng output trên release đang sử dụng.

### 8.2. DBMS_MVIEW.EXPLAIN_MVIEW

EXPLAIN_MVIEW đánh giá khả năng refresh và rewrite của một materialized view. Bảng capability thường được tạo bằng script utlxmv.sql theo hướng dẫn Oracle:

```sql
BEGIN
    DBMS_MVIEW.EXPLAIN_MVIEW(
        mv => 'SALES_REGION_PRODUCT_MV'
    );
END;
/

SELECT capability_name,
       possible,
       related_text,
       msgtxt
FROM mv_capabilities_table
ORDER BY seq;
```

Kết quả có thể chỉ ra MV hỗ trợ hoặc không hỗ trợ các capability như rewrite, fast refresh hoặc các dạng query cụ thể. Tên cột bảng capability cần đối chiếu script của phiên bản.

### 8.3. DBMS_XPLAN và execution plan

Dùng EXPLAIN PLAN để xem plan ước lượng:

```sql
EXPLAIN PLAN FOR
SELECT region_id,
       SUM(amount)
FROM sales_fact_demo
WHERE product_id = 100
GROUP BY region_id;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
```

Nếu cần plan thực tế, chạy câu lệnh với thống kê phù hợp và xem cursor:

```sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       region_id,
       SUM(amount)
FROM sales_fact_demo
WHERE product_id = 100
GROUP BY region_id;

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +OUTLINE +PREDICATE'
    )
);
```

So sánh estimated rows và actual rows. Chênh lệch lớn thường gợi ý thống kê thiếu, skew, correlated columns hoặc predicate estimate không phù hợp.

## 9. Optimizer statistics là gì?

### 9.1. Cardinality và selectivity

Optimizer ước lượng số hàng mà mỗi bước truy vấn trả về:

- **Cardinality:** số hàng dự kiến của một row source.
- **Selectivity:** tỷ lệ hàng thỏa điều kiện lọc.
- **Cost:** mô hình chi phí tương đối để so sánh các plan, không phải số giây thực tế.

Ví dụ bảng có 1.000.000 hàng, điều kiện status = 'CLOSED' được ước lượng chọn 10%, cardinality ước tính là 100.000 hàng. Nếu thực tế chỉ có 100 hàng hoặc 900.000 hàng, optimizer có thể chọn access path/join method không phù hợp.

### 9.2. Các loại statistics

| Loại | Thông tin | Tác động |
|---|---|---|
| Table statistics | NUM_ROWS, BLOCKS, AVG_ROW_LEN | Ước lượng quy mô bảng và I/O |
| Column statistics | NDV, NULL count, min/max | Ước lượng selectivity |
| Histogram | Phân bố giá trị không đồng đều | Cải thiện ước lượng cho skew |
| Index statistics | Leaf blocks, clustering factor, distinct keys | Ước lượng chi phí index access |
| System statistics | CPU, I/O characteristics | Mô hình chi phí CPU/I/O |
| Extended statistics | Tương quan giữa nhiều cột hoặc expression | Cải thiện cardinality khi cột có phụ thuộc |

Thống kê không phải dữ liệu nghiệp vụ; chúng là mô tả phục vụ tối ưu hóa. Có thể stale, thiếu hoặc không phản ánh đúng workload hiện tại.

## 10. Thu thập và kiểm tra statistics với DBMS_STATS

### 10.1. Thu thập table và index statistics

Ví dụ:

```sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname          => USER,
        tabname          => 'SALES_FACT_DEMO',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
        cascade          => TRUE
    );
END;
/
```

AUTO_SAMPLE_SIZE để Oracle chọn sample phù hợp. CASCADE => TRUE yêu cầu thu thập thống kê index liên quan theo chính sách của package. SIZE AUTO cho phép Oracle quyết định histogram theo thông tin workload/column usage và cấu hình.

Sau khi tạo MV, cũng cần thống kê cho MV:

```sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'SALES_REGION_PRODUCT_MV',
        cascade => TRUE
    );
END;
/
```

### 10.2. Xem trạng thái statistics

```sql
SELECT table_name,
       num_rows,
       blocks,
       last_analyzed,
       stale_stats
FROM user_tab_statistics
WHERE table_name IN (
    'SALES_FACT_DEMO',
    'SALES_REGION_PRODUCT_MV'
)
ORDER BY table_name;
```

Các cột hiển thị phụ thuộc dictionary view và phiên bản. NUM_ROWS là ước lượng tại lần gather gần nhất, không phải lúc nào cũng là số đếm realtime.

### 10.3. Xem column statistics

```sql
SELECT table_name,
       column_name,
       num_distinct,
       num_nulls,
       density,
       histogram,
       num_buckets,
       last_analyzed
FROM user_tab_col_statistics
WHERE table_name = 'SALES_FACT_DEMO'
ORDER BY column_name;
```

NUM_DISTINCT ước lượng số giá trị phân biệt; NUM_NULLS mô tả NULL; histogram cung cấp thông tin phân bố khi có. Đừng diễn giải DENSITY như xác suất chính xác cho mọi predicate nếu histogram tồn tại.

### 10.4. Histogram và dữ liệu lệch phân bố

Giả sử 90% đơn hàng có status COMPLETED, 9% PENDING, và 1% CANCELLED. Nếu optimizer chỉ giả định các giá trị phân bố đều, ước lượng có thể sai cho status hiếm hoặc phổ biến.

Histogram có thể giúp mô tả skew. Nhưng histogram cũng có thể khiến cùng một SQL với bind variable trở thành bind-sensitive hoặc tạo child cursor khác nhau tùy giá trị. Cần kiểm tra plan theo workload thực tế, không bật histogram cho mọi cột một cách máy móc.

### 10.5. Extended statistics cho tương quan cột

Giả sử COUNTRY_CODE và POSTAL_REGION có tương quan mạnh. Ước lượng từng cột độc lập có thể sai khi lọc đồng thời:

```sql
WHERE country_code = 'VN'
  AND postal_region = 'HCM'
```

Có thể tạo column group statistics:

```sql
SELECT DBMS_STATS.CREATE_EXTENDED_STATS(
           ownname   => USER,
           tabname   => 'CUSTOMER_DEMO',
           extension => '(COUNTRY_CODE, POSTAL_REGION)'
       )
FROM dual;
```

Sau đó gather statistics cho bảng. Extended stats không tạo index và không thay constraint; chúng bổ sung thông tin để optimizer ước lượng tương quan.

### 10.6. Expression statistics

Nếu truy vấn thường lọc theo expression, thống kê expression có thể hỗ trợ cardinality:

```sql
SELECT DBMS_STATS.CREATE_EXTENDED_STATS(
           ownname   => USER,
           tabname   => 'ORDERS',
           extension => '(TRUNC(ORDER_DATE))'
       )
FROM dual;
```

Đây là statistics cho expression, không tự động tạo function-based index. Nếu cần access path theo expression, đánh giá index riêng và kiểm tra điều kiện sử dụng.

### 10.7. Incremental statistics cho partitioned table

Với bảng partition lớn, gather toàn bộ thống kê sau mỗi lần nạp có thể tốn kém. Incremental statistics cho phép quản lý thống kê partition/global theo cách tăng dần khi cấu hình phù hợp:

```sql
BEGIN
    DBMS_STATS.SET_TABLE_PREFS(
        ownname => USER,
        tabname => 'SALES_FACT',
        pname   => 'INCREMENTAL',
        pvalue  => 'TRUE'
    );
END;
/
```

Đây là thiết lập ví dụ; cần xem chính sách partition, synopses, release và lịch gather. Không bật trên mọi bảng mà không đo chi phí và lợi ích.

## 11. Statistics, dynamic sampling và feedback

### 11.1. Dynamic statistics

Khi thống kê thiếu hoặc optimizer không đủ thông tin để ước lượng, dynamic statistics (trước đây thường gọi dynamic sampling) có thể lấy sample dữ liệu lúc parse để cải thiện ước lượng. Nó bổ sung cho statistics đã lưu, không thay thế chiến lược gather statistics.

Mức lấy mẫu và hành vi phụ thuộc phiên bản, parameter, query complexity và optimizer decision. Dynamic statistics có thể tăng chi phí parse; không nên nâng mức toàn hệ thống chỉ để chữa một truy vấn mà chưa xem plan.

### 11.2. Statistics feedback và adaptive behavior

Oracle có thể so sánh ước lượng với số liệu thực tế và sử dụng feedback/adaptive mechanisms để cải thiện các lần thực thi sau trong các trường hợp phù hợp. Hành vi cụ thể thay đổi theo release, patch level và optimizer parameters.

Feedback không đảm bảo mọi truy vấn đều được sửa plan ngay hoặc giữ plan tốt mãi mãi. Sau khi dữ liệu thay đổi, bind thay đổi hoặc statistics được gather, plan có thể đổi.

### 11.3. Pending statistics

Một số môi trường có thể thu thập statistics ở trạng thái pending để thử plan trước khi publish cho mọi session:

```sql
BEGIN
    DBMS_STATS.SET_TABLE_PREFS(
        ownname => USER,
        tabname => 'SALES_FACT_DEMO',
        pname   => 'PUBLISH',
        pvalue  => 'FALSE'
    );

    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'SALES_FACT_DEMO'
    );
END;
/
```

Việc dùng pending stats cần session/test setup và quy trình publish phù hợp. Nếu bật PUBLISH=FALSE, statistics mới chưa tự động trở thành statistics chính thức cho toàn hệ thống. Hãy lưu lại preference ban đầu và khôi phục theo chính sách sau thử nghiệm.

## 12. Compatibility và optimizer feature controls

### 12.1. COMPATIBLE

COMPATIBLE là tham số khởi tạo kiểm soát mức tương thích của database với các tính năng/định dạng tương ứng. Nó ảnh hưởng khả năng sử dụng một số tính năng và định dạng nội bộ, đồng thời có ý nghĩa lớn trong nâng cấp/hạ cấp database.

Không xem COMPATIBLE như công tắc để chọn execution plan. Thay đổi tham số này cần quy trình DBA, kiểm tra release, backup và kế hoạch khôi phục. Trong nhiều trường hợp, sau khi nâng giá trị COMPATIBLE, không thể đơn giản hạ lại như một tham số session.

### 12.2. OPTIMIZER_FEATURES_ENABLE

OPTIMIZER_FEATURES_ENABLE cho phép chọn tập hành vi optimizer tương ứng với một release baseline:

```sql
SELECT name, value
FROM v$parameter
WHERE name = 'optimizer_features_enable';
```

Có thể đặt ở session để thử nghiệm với giá trị hợp lệ của phiên bản:

```sql
ALTER SESSION SET optimizer_features_enable = '19.1.0';
```

Chuỗi phiên bản minh họa phải được thay bằng giá trị được release đang cài đặt hỗ trợ. Tham số này không làm database trở thành phiên bản cũ hơn và không vô hiệu hóa mọi tính năng mới của SQL; nó chủ yếu điều khiển hành vi optimizer theo baseline tương ứng.

### 12.3. COMPATIBLE và OPTIMIZER_FEATURES_ENABLE khác nhau

| Tham số | Phạm vi | Mục đích |
|---|---|---|
| COMPATIBLE | Database-level, quản trị bằng init parameter | Mức tương thích tính năng/định dạng database |
| OPTIMIZER_FEATURES_ENABLE | Có thể đặt theo session/system tùy phạm vi | Chọn baseline hành vi optimizer |
| QUERY_REWRITE_ENABLED | Optimizer/query rewrite | Cho phép hoặc tắt rewrite |
| QUERY_REWRITE_INTEGRITY | Query rewrite integrity | Quy định mức tin cậy/freshness cho rewrite |
| STATISTICS_LEVEL | Thu thập thống kê/diagnostics | Điều khiển mức thống kê và advisor features |

Không thay đổi COMPATIBLE để xử lý một plan chậm. Nếu nghi ngờ optimizer regression sau nâng cấp, hãy kiểm tra plan history, SQL Plan Management và thử baseline optimizer trong session kiểm soát trước.

### 12.4. Các parameter liên quan khác

Một số thiết lập thường cần hiểu:

- OPTIMIZER_MODE: mục tiêu tối ưu như ALL_ROWS hoặc FIRST_ROWS_n.
- CURSOR_SHARING: chính sách thay literal thành bind trong một số trường hợp; không thay thế việc ứng dụng viết bind đúng cách.
- OPTIMIZER_DYNAMIC_SAMPLING: mức dynamic statistics theo release.
- STATISTICS_LEVEL: mức thu thập statistics và thông tin phục vụ diagnostics.
- QUERY_REWRITE_ENABLED: bật/tắt/force rewrite.
- QUERY_REWRITE_INTEGRITY: mức integrity cho query rewrite.

Không thay đổi nhiều parameter cùng lúc. Ghi lại giá trị ban đầu, phạm vi ảnh hưởng, lý do, kế hoạch rollback và đo trước/sau.

## 13. Phiên bản database và tính năng SQL

### 13.1. SQL syntax và optimizer behavior là hai lớp khác nhau

Một câu SQL có thể:

1. Không parse được vì cú pháp/tính năng chưa có ở release.
2. Parse được nhưng optimizer không áp dụng transformation.
3. Được transformation nhưng plan cuối không nhanh hơn.

OPTIMIZER_FEATURES_ENABLE không thêm cú pháp SQL của một release mới vào database cũ. COMPATIBLE cũng không thay thế việc kiểm tra version hỗ trợ cú pháp/API.

### 13.2. Kiểm tra phiên bản

```sql
SELECT banner
FROM v$version
WHERE banner LIKE 'Oracle Database%';
```

Hoặc:

```sql
SELECT version
FROM product_component_version
WHERE product LIKE 'Oracle Database%';
```

Quyền truy cập dictionary view phụ thuộc môi trường. Khi viết script triển khai, ghi rõ release tối thiểu cần thiết và kiểm tra trước khi chạy DDL/API mới.

### 13.3. Patch level và Release Update

Hai database cùng major release vẫn có thể khác patch level và behavior do bug fix/optimizer fix. Khi điều tra plan regression:

- Ghi nhận version đầy đủ và RU.
- Ghi nhận COMPATIBLE và optimizer parameters.
- So sánh SQL text, bind metadata, schema và statistics.
- Kiểm tra SQL plan history/baseline.
- Thử trong môi trường tương đương trước khi áp dụng production.

Không kết luận “Oracle 19c luôn chọn plan X” chỉ từ một hệ thống có patch, statistics và dữ liệu riêng.

## 14. SQL Plan Management và ổn định plan

Query rewrite là một khả năng optimizer lựa chọn; SQL Plan Management (SPM) là cơ chế quản lý/kiểm soát plan đã được chấp nhận. Hai cơ chế có thể cùng tồn tại nhưng không đồng nghĩa.

### 14.1. SQL plan baseline

SQL plan baseline có thể giúp kiểm soát các plan được optimizer chấp nhận cho SQL statement. Khi nâng cấp hoặc statistics thay đổi, baseline có thể giảm rủi ro plan regression nếu được quản lý đúng.

Không nên tạo baseline cho mọi truy vấn mà không có đánh giá. Baseline cũ có thể ngăn optimizer tận dụng plan tốt hơn nếu không evolve/maintain.

### 14.2. So sánh plan trước và sau

Thu thập:

- SQL ID và child cursor.
- Plan hash value.
- Estimated rows và actual rows.
- Buffer gets, physical reads, CPU, elapsed time.
- Bind values/peeking context ở mức được phép.
- Statistics timestamp và optimizer environment.

Nếu plan thay đổi sau khi gather stats, kiểm tra xem ước lượng có cải thiện không và liệu query rewrite có được chọn khác đi. Đừng chỉ so sánh plan hash mà bỏ qua số hàng và workload.

### 14.3. Hints

Hints như REWRITE, NO_REWRITE, MERGE, NO_MERGE, PUSH_PRED, NO_PUSH_PRED, UNNEST hoặc NO_UNNEST có thể ảnh hưởng một số quyết định optimizer trong ngữ cảnh hỗ trợ.

Hints là công cụ điều khiển/diagnostic có phạm vi cụ thể, không phải bảo đảm mọi release sẽ dùng đúng plan mong muốn. Một hint không hợp lệ hoặc không áp dụng có thể bị bỏ qua. Ưu tiên sửa thống kê, schema, SQL shape và kiểm tra nguyên nhân trước khi cố định plan bằng hint.

## 15. Tối ưu thống kê cho materialized view

### 15.1. Gather stats cho cả nguồn và MV

MV là đối tượng lưu kết quả; optimizer cần biết số hàng, block, phân bố cột và index của nó:

```sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'SALES_FACT_DEMO',
        cascade => TRUE
    );

    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'SALES_REGION_PRODUCT_MV',
        cascade => TRUE
    );
END;
/
```

Nếu MV được refresh làm số hàng thay đổi đáng kể, statistics có thể cần được cập nhật theo lịch phù hợp. Không gather ngay sau mỗi refresh nhỏ nếu chi phí lớn hơn lợi ích.

### 15.2. Index trên MV

Nếu truy vấn thường lọc product rồi group region, có thể đánh giá index:

```sql
CREATE INDEX ix_sales_mv_product_region
ON sales_region_product_mv(product_id, region_id);
```

Thứ tự cột index cần dựa trên predicate, selectivity và truy vấn thực tế. Index làm tăng chi phí refresh/maintenance và storage. Optimizer vẫn có thể chọn full scan MV nếu phần lớn hàng cần đọc.

### 15.3. Partitioning và partition change tracking

Với fact table/MV rất lớn, partitioning theo thời gian hoặc dimension có thể giúp pruning và quản lý refresh. Partition Change Tracking (PCT) có thể hỗ trợ refresh/rewrite trong các cấu hình phù hợp.

PCT không tự động hoạt động chỉ vì bảng có partition. Cần đáp ứng yêu cầu về partition key, MV definition, constraints và refresh capability. Dùng DBMS_MVIEW.EXPLAIN_MVIEW để kiểm tra thay vì giả định.

## 16. Tình huống thực tế và hướng chẩn đoán

### 16.1. MV tồn tại nhưng truy vấn vẫn đọc bảng nguồn

Kiểm tra theo thứ tự:

1. MV có ENABLE QUERY REWRITE không?
2. QUERY_REWRITE_ENABLED có bật không?
3. MV có fresh/valid không?
4. QUERY_REWRITE_INTEGRITY có cho phép sử dụng không?
5. MV có đủ cột, grouping key và aggregate không?
6. Constraints/dimensions có đủ để chứng minh quan hệ không?
7. EXPLAIN_REWRITE báo lý do gì?
8. Optimizer có thấy đọc bảng nguồn rẻ hơn không?

### 16.2. Rewrite xảy ra nhưng truy vấn chậm hơn

MV không tự động nhanh hơn trong mọi trường hợp. Có thể:

- MV quá lớn và thiếu index phù hợp.
- Statistics của MV cũ.
- Query chỉ cần một phần nhỏ của fact table và index nguồn hiệu quả hơn.
- Refresh làm tăng overhead hoặc contention.
- Join/group tiếp trên MV vẫn tốn chi phí.

So sánh plan thực tế, actual rows, buffer gets và thời gian trên workload đại diện. Nếu optimizer chọn rewrite nhưng plan xấu, cải thiện MV/index/stats hoặc cân nhắc SQL plan control sau khi có bằng chứng.

### 16.3. Sau nâng cấp, plan thay đổi

Kiểm tra:

- OPTIMIZER_FEATURES_ENABLE và optimizer environment.
- Statistics được gather lại hay thay đổi.
- Bind peeking và child cursor.
- Query transformation mới/khác.
- SQL Plan Baseline có được áp dụng/evolve không.
- Patch level và RU.

Không hạ COMPATIBLE chỉ để quay lại plan cũ. Dùng session thử optimizer baseline hoặc SPM theo quy trình quản trị.

### 16.4. Kết quả báo cáo có vẻ cũ

Nếu MV được dùng với integrity cho phép dữ liệu stale, báo cáo có thể không bao gồm giao dịch mới. Kiểm tra:

```sql
SELECT mview_name,
       staleness,
       last_refresh_type,
       last_refresh_date
FROM user_mviews
WHERE mview_name = 'SALES_REGION_PRODUCT_MV';
```

Tên cột metadata cần xác nhận trên release. Xem lịch refresh và trạng thái MV trước khi thay integrity setting. Không đổi sang STALE_TOLERATED chỉ để query rewrite hoạt động nếu người dùng mong dữ liệu realtime.

## 17. Quy trình triển khai query rewrite có kiểm soát

Một quy trình phù hợp cho hệ thống báo cáo:

1. **Đo baseline:** ghi nhận SQL, plan, elapsed time, buffer gets, actual rows và tần suất chạy.
2. **Xác định grain:** mô tả mức chi tiết của fact table và kết quả báo cáo.
3. **Thiết kế MV:** chỉ lưu các khóa, aggregate và biểu thức thực sự cần.
4. **Kiểm tra capability:** dùng EXPLAIN_MVIEW/EXPLAIN_REWRITE.
5. **Thiết lập refresh:** chọn COMPLETE/FAST và ON DEMAND/ON COMMIT theo độ mới dữ liệu và chi phí.
6. **Bật rewrite trong môi trường thử:** dùng integrity phù hợp, không nới lỏng constraint giả tạo.
7. **Gather statistics:** cho nguồn, MV và index.
8. **Xác nhận plan:** kiểm tra optimizer có rewrite và actual plan có lợi.
9. **So sánh kết quả:** chạy query gốc và query rewrite trong dữ liệu kiểm thử, so sánh đầy đủ kết quả/NULL/duplicates.
10. **Theo dõi production:** refresh lag, MV staleness, plan, storage và workload.

## 18. Bài thực hành tổng hợp

Thực hiện trong schema lab riêng. Dùng bảng SALES_FACT_DEMO và MV SALES_REGION_PRODUCT_MV ở mục 3.

### Bước 1 — Xem kết quả truy vấn gốc

```sql
SELECT region_id,
       SUM(amount) AS revenue
FROM sales_fact_demo
WHERE product_id = 100
GROUP BY region_id
ORDER BY region_id;
```

Ghi kết quả làm baseline.

### Bước 2 — Bật query rewrite và integrity

```sql
ALTER SESSION SET query_rewrite_enabled = TRUE;
ALTER SESSION SET query_rewrite_integrity = ENFORCED;
```

### Bước 3 — Xem plan

```sql
EXPLAIN PLAN FOR
SELECT region_id,
       SUM(amount) AS revenue
FROM sales_fact_demo
WHERE product_id = 100
GROUP BY region_id;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
```

Ghi nhận nguồn dữ liệu mà plan truy cập. Đừng yêu cầu plan phải có một operation name cố định giữa các release.

### Bước 4 — Gather statistics

```sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'SALES_FACT_DEMO',
        cascade => TRUE
    );
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'SALES_REGION_PRODUCT_MV',
        cascade => TRUE
    );
END;
/
```

Chạy lại EXPLAIN PLAN và so sánh.

### Bước 5 — Làm MV stale

Chèn một hàng mới vào fact table:

```sql
INSERT INTO sales_fact_demo (
    sale_id, sale_date, region_id, product_id, amount
)
VALUES (
    6, DATE '2026-02-20', 10, 100, 300
);
COMMIT;
```

MV ON DEMAND chưa refresh nên có thể stale. Chạy lại truy vấn và xem optimizer xử lý theo integrity hiện tại.

### Bước 6 — Refresh MV

```sql
BEGIN
    DBMS_MVIEW.REFRESH(
        list => 'SALES_REGION_PRODUCT_MV',
        method => 'C'
    );
END;
/
```

Chạy lại truy vấn và so sánh kết quả với nguồn.

### Bước 7 — Kiểm tra rewrite capability

Chuẩn bị bảng REWRITE_TABLE và MV_CAPABILITIES_TABLE theo script Oracle Home được DBA cung cấp. Chạy DBMS_MVIEW.EXPLAIN_REWRITE và DBMS_MVIEW.EXPLAIN_MVIEW; đọc các message/capability.

### Bước 8 — Thử query không thể rewrite

Thử truy vấn cần một cột không có trong MV hoặc một aggregate chưa được lưu. Giải thích vì sao MV không đủ thông tin để tái dựng kết quả.

### Bước 9 — Quan sát thống kê và cardinality

Chạy query với GATHER_PLAN_STATISTICS, xem ALLSTATS LAST, so sánh estimated rows và actual rows. Thử gather stats và xem plan thay đổi hay không.

### Bước 10 — So sánh optimizer baseline

Trong session lab, thử một giá trị OPTIMIZER_FEATURES_ENABLE được phiên bản hỗ trợ. So sánh plan, không thay COMPATIBLE và không thay cấu hình toàn hệ thống. Khôi phục session parameter sau thử nghiệm.

## 19. Các lỗi hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế |
|---|---|
| Có MV thì Oracle luôn dùng MV | Optimizer chỉ rewrite khi đủ điều kiện và plan có lợi |
| ENABLE QUERY REWRITE là đủ | Còn cần query rewrite enabled, freshness/integrity, dữ liệu và semantics phù hợp |
| MV log là điều kiện bắt buộc cho rewrite | MV log chủ yếu phục vụ fast refresh; không phải điều kiện phổ quát cho rewrite |
| FORCE bảo đảm mọi truy vấn dùng MV | Không thể ép một rewrite không hợp lệ hoặc không đủ thông tin |
| TRUSTED luôn an toàn | Nó dựa vào giả định/metadata; dữ liệu vi phạm giả định có thể làm kết quả sai |
| STALE_TOLERATED chỉ là tối ưu hiệu năng | Nó có thể cho phép kết quả cũ hơn nguồn |
| Gather stats một lần là đủ mãi mãi | Dữ liệu thay đổi, statistics có thể stale |
| Histogram luôn làm plan tốt hơn | Histogram có thể cải thiện skew nhưng cũng làm plan nhạy với bind |
| COMPATIBLE là phiên bản optimizer | COMPATIBLE điều khiển mức tương thích database; OPTIMIZER_FEATURES_ENABLE điều khiển baseline optimizer |
| Hạ OPTIMIZER_FEATURES_ENABLE làm database thành bản cũ | Nó không hạ version database hay thêm/bớt toàn bộ SQL syntax |
| Query transformation luôn làm SQL nhanh hơn | Transformation mở rộng phương án; cost và dữ liệu quyết định plan cuối |
| EXPLAIN PLAN là số liệu thực thi | Nó là plan ước lượng; cần actual cursor statistics để đo |

## 20. Câu hỏi tự kiểm tra

1. Query transformation khác materialized view query rewrite như thế nào?
2. View merging, predicate pushing và subquery unnesting giải quyết vấn đề gì?
3. Semi-join và join elimination liên quan query transformation ra sao?
4. Materialized view khác view thường ở cách lưu dữ liệu nào?
5. Query rewrite có thể thay fact table bằng MV trong điều kiện nào?
6. Vì sao MV cần đủ cột group/filter và aggregate?
7. ENABLE QUERY REWRITE khác QUERY_REWRITE_ENABLED như thế nào?
8. QUERY_REWRITE_INTEGRITY có các mức ENFORCED, TRUSTED và STALE_TOLERATED với ý nghĩa gì?
9. MV log phục vụ fast refresh khác vai trò query rewrite ra sao?
10. Constraint ENABLED, VALIDATED và RELY ảnh hưởng optimizer thế nào?
11. Vì sao NOT NULL và NULL semantics có thể quyết định một rewrite có an toàn không?
12. DBMS_MVIEW.EXPLAIN_REWRITE và EXPLAIN_MVIEW giúp chẩn đoán gì?
13. Cardinality, selectivity và cost khác nhau thế nào?
14. Table/column/index/system statistics mô tả những gì?
15. Histogram có ích khi nào và có thể gây trade-off gì với bind variable?
16. Extended statistics giúp gì khi hai cột có tương quan?
17. Dynamic statistics và statistics feedback khác gather statistics thế nào?
18. COMPATIBLE khác OPTIMIZER_FEATURES_ENABLE ở phạm vi và mục đích ra sao?
19. Vì sao optimizer feature baseline không thay thế kiểm tra SQL syntax theo release?
20. SQL Plan Management khác query rewrite thế nào?
21. Vì sao plan có rewrite vẫn có thể chậm hơn plan đọc bảng nguồn?
22. Cần so sánh những chỉ số nào trước và sau khi triển khai MV rewrite?

**Nguyên tắc cần nhớ:** query rewrite chỉ an toàn khi Oracle chứng minh kết quả tương đương theo dữ liệu, constraint và mức integrity được cấu hình. Materialized view có thể giảm chi phí truy vấn lặp lại, nhưng phải thiết kế đúng grain, refresh đúng chính sách và có statistics phù hợp. Khi điều tra plan, phân biệt rõ tính năng SQL theo phiên bản, optimizer baseline, query rewrite parameters và statistics; thay đổi từng yếu tố có kiểm soát rồi đo plan thực tế.
