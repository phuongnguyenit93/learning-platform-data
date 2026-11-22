# Partition-wise join và tổ chức truy vấn theo vùng dữ liệu trong Oracle Database

Trong kho dữ liệu và hệ thống giao dịch lớn, hai bảng được JOIN có thể chứa hàng chục hoặc hàng trăm triệu dòng. Nếu Oracle phải phân phối lại toàn bộ dữ liệu giữa các parallel execution server trước khi JOIN, chi phí truyền dữ liệu, CPU và bộ nhớ có thể rất lớn. **Partition-wise join** giúp giảm phần công việc này bằng cách chia phép JOIN theo các vùng dữ liệu tương ứng của những bảng đã được partition.

Ý tưởng cốt lõi là: nếu hai bảng được phân vùng tương thích theo khóa JOIN, Oracle có thể JOIN từng cặp partition tương ứng độc lập. Một truy vấn lớn khi đó được chia thành nhiều phép JOIN nhỏ hơn, có thể xử lý song song. Nếu chỉ một phía đã partition theo khóa JOIN, Oracle cũng có thể dùng **partial partition-wise join** bằng cách phân phối phía còn lại để khớp với các partition.

Để thiết kế hiệu quả, cần phân biệt:

- **Partitioning:** cách chia dữ liệu của một bảng thành các partition.
- **Partition pruning:** bỏ qua partition không cần đọc nhờ predicate hoặc điều kiện JOIN.
- **Partition-wise join:** thực hiện JOIN theo các partition tương ứng, giảm hoặc tránh việc phân phối lại dữ liệu lớn.
- **Parallel execution:** dùng nhiều process để xử lý các partition hoặc phần dữ liệu đồng thời.

Partition-wise join không tự động xuất hiện chỉ vì hai bảng đều được partition. Khóa partition, phương pháp partition, số lượng và ranh giới partition, điều kiện JOIN, thống kê và cost đều ảnh hưởng quyết định của optimizer.

## 1. Vì sao cần partition-wise join?

Giả sử có hai bảng:

- SALES: hàng trăm triệu giao dịch.
- CUSTOMERS: hàng triệu khách hàng.

Truy vấn:

~~~sql
SELECT c.customer_id,
       c.customer_name,
       SUM(s.amount) AS total_amount
FROM customers c
JOIN sales s
  ON s.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name;
~~~

Nếu các bảng được partition phù hợp theo CUSTOMER_ID, Oracle có thể ghép dữ liệu của từng vùng khách hàng tương ứng. Ví dụ, partition 1 của SALES chỉ cần JOIN với partition 1 của CUSTOMERS, partition 2 với partition 2, và tiếp tục như vậy.

~~~text
CUSTOMERS partition 1  <---->  SALES partition 1
CUSTOMERS partition 2  <---->  SALES partition 2
CUSTOMERS partition 3  <---->  SALES partition 3
...
CUSTOMERS partition N  <---->  SALES partition N

          Mỗi cặp được JOIN độc lập
          Có thể chạy song song
~~~

Lợi ích tiềm năng:

- Giảm lượng dữ liệu phải gửi giữa parallel execution servers.
- Chia một phép JOIN lớn thành nhiều phép JOIN nhỏ hơn.
- Giảm bộ nhớ cần cho từng phép JOIN khi dữ liệu được chia hợp lý.
- Tận dụng partition pruning nếu có predicate trên partition key.
- Tăng khả năng mở rộng cho truy vấn phân tích trên bảng lớn.

Lợi ích thực tế phụ thuộc kích thước dữ liệu, mức skew, phương pháp JOIN và kế hoạch thực thi. Với bảng nhỏ, broadcast join hoặc nested loops có thể rẻ hơn.

## 2. Partition-wise join là gì?

Partition-wise join là kỹ thuật thực thi JOIN trong đó Oracle chia công việc theo partition của bảng. Thay vì gom hoặc phân phối toàn bộ hai tập dữ liệu rồi mới JOIN, Oracle cố gắng xử lý những vùng dữ liệu tương ứng với nhau.

Có hai dạng chính:

1. **Full partition-wise join:** hai bảng được partition tương thích (equipartitioned) theo khóa JOIN, cho phép JOIN các cặp partition tương ứng mà không cần repartition cả hai phía cho phép JOIN đó.
2. **Partial partition-wise join:** chỉ một phía có partitioning phù hợp; Oracle phân phối phía còn lại để khớp với partitioning của phía đã partition.

### 2.1 Full partition-wise join

Ví dụ hai bảng đều hash partition theo CUSTOMER_ID với cùng số partition và cùng cách phân vùng:

~~~text
CUSTOMERS                         SALES
hash(customer_id), 8 partitions  hash(customer_id), 8 partitions

C_P01  ------------------------  S_P01
C_P02  ------------------------  S_P02
C_P03  ------------------------  S_P03
C_P04  ------------------------  S_P04
C_P05  ------------------------  S_P05
C_P06  ------------------------  S_P06
C_P07  ------------------------  S_P07
C_P08  ------------------------  S_P08
~~~

Vì cùng CUSTOMER_ID được ánh xạ vào partition tương ứng ở cả hai bảng, Oracle có thể JOIN từng cặp partition.

### 2.2 Partial partition-wise join

Nếu SALES được hash partition theo CUSTOMER_ID nhưng CUSTOMERS là heap table không partition, Oracle không có sẵn các cặp partition tương ứng. Trong một kế hoạch partial partition-wise join song song, dữ liệu phía không partition có thể được phân phối để khớp với các partition của SALES.

~~~text
CUSTOMERS (nonpartitioned)
          |
          | redistribute theo khóa JOIN
          v
  customer rows được chia theo vùng
          |
          +------> SALES partition 1
          +------> SALES partition 2
          +------> SALES partition 3
          ...

JOIN theo partition của SALES
~~~

Chỉ một phía đã có partitioning phù hợp từ đầu; phía còn lại cần được phân phối. Vì vậy đây là partial, không phải full partition-wise join.

### 2.3 Không phải mọi JOIN giữa hai bảng partitioned đều là full partition-wise join

Hai bảng có thể đều partition nhưng:

- Partition theo các cột khác nhau.
- Dùng phương pháp partition khác nhau.
- Có số partition hoặc ranh giới không tương ứng.
- JOIN không chứa quan hệ cần thiết với partition key.

Trong các trường hợp đó, optimizer có thể phải redistribute dữ liệu theo hash, broadcast một phía, hoặc chọn một kế hoạch JOIN khác. Việc cả hai bảng đều có partition không đủ để kết luận có full partition-wise join.

## 3. Điều kiện để có full partition-wise join

### 3.1 Hai bảng phải được partition tương thích

Để Oracle thực hiện full partition-wise join, các bảng cần được equipartitioned theo điều kiện JOIN. Với partitioning thông thường, cần xem:

- Cùng partitioning key hoặc cách ánh xạ tương đương với join key.
- Cùng phương pháp partitioning phù hợp.
- Cùng số partition tương ứng.
- Các ranh giới/định nghĩa partition tương ứng nhau nếu dùng range hoặc list partitioning.
- Với composite partitioning, cấu trúc subpartition cần tương thích cho phép JOIN tương ứng.

Chi tiết hỗ trợ còn phụ thuộc loại partitioning và phiên bản Oracle. Không nên chỉ so tên partition hoặc số partition bằng mắt; hãy kiểm tra metadata và execution plan.

### 3.2 Điều kiện JOIN phải kết nối partition key

Ví dụ phù hợp:

~~~sql
SELECT ...
FROM sales s
JOIN customers c
  ON s.customer_id = c.customer_id;
~~~

Nếu cả hai bảng được partition tương thích theo CUSTOMER_ID, điều kiện JOIN có thể cho phép ghép các partition tương ứng.

Ví dụ không tận dụng được thiết kế đó:

~~~sql
SELECT ...
FROM sales s
JOIN customers c
  ON s.region_id = c.region_id;
~~~

Nếu bảng được partition theo CUSTOMER_ID nhưng JOIN theo REGION_ID, hai partition cùng số thứ tự không nhất thiết chứa các dòng cần ghép. Oracle không thể coi chúng là các cặp tương ứng chỉ vì tên partition giống nhau.

### 3.3 Partition key có thể gồm nhiều cột

Nếu bảng được partition theo tổ hợp nhiều cột, điều kiện JOIN và cấu trúc partition phải cung cấp đủ quan hệ để Oracle chứng minh các vùng dữ liệu tương ứng. Không giả định JOIN chỉ một phần khóa composite luôn đủ cho full partition-wise join.

Ví dụ bảng partition theo HASH(tenant_id, customer_id) và JOIN chỉ theo CUSTOMER_ID có thể không bảo đảm hai dòng cùng customer nằm trong cùng partition nếu TENANT_ID khác nhau.

### 3.4 Reference partitioning

Oracle hỗ trợ reference partitioning để bảng con kế thừa cách phân vùng theo quan hệ khóa ngoại với bảng cha. Cấu trúc này có thể hữu ích cho các phép JOIN cha-con theo khóa tham chiếu vì dữ liệu liên quan được đồng vị trí theo thiết kế. Vẫn cần kiểm tra loại JOIN, constraint và khả năng thực thi thực tế bằng plan.

## 4. Phân biệt partition-wise join và partition pruning

Hai kỹ thuật thường xuất hiện cùng nhau nhưng giải quyết hai vấn đề khác nhau.

### 4.1 Partition pruning

Partition pruning giảm số partition cần đọc:

~~~sql
SELECT *
FROM sales
WHERE sale_date >= DATE '2026-01-01'
  AND sale_date <  DATE '2026-02-01';
~~~

Nếu SALES range partition theo SALE_DATE, Oracle có thể chỉ đọc partition tháng 1 thay vì quét mọi partition.

### 4.2 Partition-wise join

Partition-wise join giảm chi phí phối hợp dữ liệu giữa hai phía JOIN bằng cách xử lý các cặp partition tương ứng.

Ví dụ:

~~~sql
SELECT c.customer_id,
       SUM(s.amount)
FROM customers c
JOIN sales s
  ON s.customer_id = c.customer_id
GROUP BY c.customer_id;
~~~

Nếu cả hai bảng được partition tương thích theo CUSTOMER_ID, Oracle có thể JOIN theo partition tương ứng ngay cả khi truy vấn không loại bỏ partition nào.

### 4.3 Có thể dùng đồng thời

Nếu các bảng partition tương thích theo CUSTOMER_ID và truy vấn lọc một customer:

~~~sql
SELECT c.customer_id,
       SUM(s.amount)
FROM customers c
JOIN sales s
  ON s.customer_id = c.customer_id
WHERE c.customer_id = :p_customer_id
GROUP BY c.customer_id;
~~~

Oracle có thể prune về partition chứa CUSTOMER_ID đó trên cả hai bảng và JOIN trong vùng dữ liệu đã được chọn. Đây là sự kết hợp giữa pruning và partition-wise join; plan thực tế phải xác nhận partition start/stop và join operation.

### 4.4 Partitioning theo một khóa không có nghĩa mọi truy vấn đều prune

Nếu SALES partition theo CUSTOMER_ID nhưng truy vấn chỉ lọc SALE_DATE, Oracle có thể không prune theo ngày trừ khi có partitioning/subpartitioning phù hợp hoặc điều kiện có thể suy ra partition key.

Partition-wise join cũng không tự động giới hạn số partition được đọc. Nó có thể JOIN từng cặp trên toàn bộ partition.

## 5. Chọn partitioning key cho workload JOIN

Partitioning key là quyết định kiến trúc. Để partition-wise join hữu ích, cần xem các JOIN lớn và tần suất thực tế.

### 5.1 Chọn khóa JOIN thường xuyên

Nếu SALES thường xuyên JOIN với CUSTOMERS theo CUSTOMER_ID, partition cả hai bảng theo CUSTOMER_ID có thể tạo điều kiện cho full partition-wise join.

Tuy nhiên, CUSTOMER_ID có thể không phải khóa tốt nếu:

- Các truy vấn chủ yếu lọc theo SALE_DATE.
- Dữ liệu phân bố rất lệch theo CUSTOMER_ID.
- Bảng dimension nhỏ và broadcast join rẻ hơn.
- Quản trị dữ liệu cần drop/archive theo tháng.

Không chọn partition key chỉ dựa trên một truy vấn. Cần cân bằng query workload, lifecycle dữ liệu, quản trị và khả năng phân phối.

### 5.2 Hash partitioning cho phân phối theo khóa

Hash partitioning thường phù hợp khi muốn phân phối dữ liệu tương đối đều theo một khóa và hỗ trợ JOIN equality theo khóa đó.

Ví dụ:

~~~sql
CREATE TABLE customers (
    customer_id   NUMBER NOT NULL,
    customer_name VARCHAR2(100),
    CONSTRAINT pk_customers PRIMARY KEY (customer_id)
)
PARTITION BY HASH (customer_id)
PARTITIONS 8;
~~~

~~~sql
CREATE TABLE sales (
    sale_id     NUMBER NOT NULL,
    customer_id NUMBER NOT NULL,
    sale_date   DATE NOT NULL,
    amount      NUMBER(12,2)
)
PARTITION BY HASH (customer_id)
PARTITIONS 8;
~~~

Hai bảng dùng cùng hash key và cùng số partition. Đây là mẫu thiết kế cơ bản để Oracle có cơ hội full partition-wise join theo CUSTOMER_ID.

Hash partitioning không đảm bảo phân phối hoàn toàn đều trong mọi tình huống. Một số customer có số giao dịch vượt trội vẫn tạo skew ở partition chứa họ.

### 5.3 Range partitioning khi cần quản trị theo thời gian

Bảng SALES thường được partition theo SALE_DATE để:

- Prune dữ liệu theo khoảng thời gian.
- Archive hoặc drop partition cũ.
- Load dữ liệu theo kỳ.
- Quản lý retention.

Nếu bảng CUSTOMERS partition theo CUSTOMER_ID, hai bảng không equipartitioned theo cùng khóa JOIN. Khi JOIN theo CUSTOMER_ID, full partition-wise join có thể không khả thi. Optimizer có thể dùng partial/repartition/broadcast hoặc phương án JOIN khác.

### 5.4 Composite partitioning

Một bảng có thể partition theo SALE_DATE và subpartition theo HASH(CUSTOMER_ID):

~~~sql
CREATE TABLE sales_by_month_customer (
    sale_id     NUMBER NOT NULL,
    customer_id NUMBER NOT NULL,
    sale_date   DATE NOT NULL,
    amount      NUMBER(12,2)
)
PARTITION BY RANGE (sale_date)
SUBPARTITION BY HASH (customer_id)
SUBPARTITIONS 8
(
    PARTITION p2026_01 VALUES LESS THAN (DATE '2026-02-01'),
    PARTITION p2026_02 VALUES LESS THAN (DATE '2026-03-01'),
    PARTITION pmax     VALUES LESS THAN (MAXVALUE)
);
~~~

Composite partitioning có thể hỗ trợ đồng thời quản trị theo thời gian và phân phối dữ liệu theo customer trong từng partition tháng. Nhưng để full partition-wise join với bảng khác, cấu trúc partition/subpartition của bảng kia phải tương thích theo các điều kiện Oracle hỗ trợ; chỉ có cùng subpartition key chưa đủ để khẳng định toàn bộ cấu trúc đã equipartitioned.

## 6. Partial partition-wise join và phân phối dữ liệu

### 6.1 Một bảng partitioned, một bảng không partitioned

Giả sử SALES hash partition theo CUSTOMER_ID, còn CUSTOMERS là heap table:

~~~sql
SELECT c.customer_id,
       c.customer_name,
       SUM(s.amount) AS total_amount
FROM customers c
JOIN sales s
  ON s.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name;
~~~

Trong partial partition-wise join song song, Oracle có thể phân phối dòng từ CUSTOMERS theo CUSTOMER_ID đến các parallel server xử lý partition tương ứng của SALES. Phép JOIN sau đó được thực hiện theo các vùng partition của SALES.

### 6.2 Broadcast join không đồng nghĩa với partial partition-wise join

Nếu CUSTOMERS nhỏ, Oracle có thể broadcast dữ liệu dimension đến các parallel server để mỗi server JOIN với phần SALES mà nó xử lý. Broadcast là một chiến lược phân phối dữ liệu trong parallel execution; nó có thể xuất hiện trong một kế hoạch JOIN nhưng không nên gọi mọi broadcast join là partial partition-wise join.

So sánh:

| Chiến lược | Phía được phân phối | Khi có thể hữu ích |
|---|---|---|
| Full partition-wise join | Không cần repartition hai bảng cho JOIN tương ứng | Cả hai bảng equipartitioned |
| Partial partition-wise join | Phân phối phía chưa partition tương thích để khớp phía đã partition | Một phía partitioned phù hợp |
| Broadcast join | Sao chép tập nhỏ đến nhiều parallel server | Một phía nhỏ, broadcast rẻ |
| Hash repartition join thông thường | Phân phối cả hai phía theo join key | Không có partition alignment phù hợp |

Optimizer chọn phương án dựa trên cost, cardinality, kích thước dữ liệu và DOP.

### 6.3 Chi phí redistribution

Redistribution có thể sử dụng interconnect giữa parallel execution servers, buffer và TEMP. Với dữ liệu lớn, chi phí truyền và phân phối có thể đáng kể. Full partition-wise join tránh được một phần công việc này vì dữ liệu đã được đặt theo vùng tương ứng.

Partial partition-wise join giảm công việc phải phân phối so với repartition cả hai bảng, nhưng vẫn có chi phí cho phía cần di chuyển.

## 7. Partition-wise join với parallel execution

### 7.1 Parallel execution servers

Oracle có thể chia truy vấn thành các hoạt động chạy trên nhiều parallel execution servers (PX servers). Với partition-wise join, mỗi server hoặc nhóm server xử lý một hay nhiều cặp partition.

~~~text
Query coordinator
       |
       v
Parallel execution servers
   |       |       |
   v       v       v
  P01     P02     P03  ... các cặp partition
   |       |       |
   v       v       v
 JOIN    JOIN    JOIN
   |       |       |
   +-------+-------+
           |
           v
   Tổng hợp / trả kết quả
~~~

### 7.2 Degree of parallelism (DOP)

DOP là số mức song song được yêu cầu hoặc chọn cho hoạt động. DOP không nhất thiết bằng số partition:

- Có nhiều partition hơn DOP: một server có thể xử lý nhiều partition hoặc granule.
- DOP lớn hơn số partition có thể giới hạn mức song song hữu ích cho một số thao tác partition-level.
- Nhiều partition nhỏ không tự đảm bảo truy vấn nhanh hơn.
- DOP cao tiêu tốn thêm CPU, PX server, bộ nhớ và interconnect.

### 7.3 Partition granules

Oracle chia công việc song song thành các granule, thường có thể là block-range hoặc partition granule tùy thao tác và cấu trúc. Với partition-wise join, partition granule có thể giúp phân công vùng dữ liệu cho các PX server. Cách phân công cụ thể phụ thuộc plan, loại partition và phiên bản.

### 7.4 Khi nào chạy song song không có lợi?

Với bảng nhỏ hoặc predicate chỉ trả vài dòng, chi phí khởi tạo PX, truyền dữ liệu và đồng bộ có thể lớn hơn lợi ích. Truy vấn serial dùng index range scan hoặc nested loops có thể nhanh hơn.

Không thêm PARALLEL hint hoặc tăng DOP chỉ vì bảng đã partition. Đo elapsed time, CPU, I/O và tác động đến các truy vấn đồng thời.

## 8. Skew và mất cân bằng giữa các partition

Partition-wise join chia công việc theo vùng dữ liệu, nhưng nếu các partition có kích thước rất khác nhau thì thời gian hoàn thành bị chi phối bởi partition nặng nhất.

Ví dụ:

| Partition | Số dòng SALES |
|---|---:|
| P01 | 10 triệu |
| P02 | 9 triệu |
| P03 | 11 triệu |
| P04 | 70 triệu |
| P05 | 10 triệu |
| P06 | 10 triệu |

P04 lớn hơn nhiều so với các partition còn lại. Các PX server xử lý partition nhỏ có thể kết thúc sớm rồi chờ server đang xử lý P04.

### 8.1 Nguyên nhân skew

- Một vài customer/tenant có số giao dịch vượt trội.
- Giá trị NULL hoặc giá trị mặc định tập trung vào một nhóm.
- Hash key có phân bố không đều hoặc domain nhỏ.
- Một vùng thời gian có lượng dữ liệu lớn bất thường.
- Join key có một giá trị xuất hiện trong phần lớn dòng.

### 8.2 Đo phân bố partition

Có thể xem số dòng ước lượng theo partition:

~~~sql
SELECT partition_name,
       num_rows,
       blocks,
       last_analyzed
FROM user_tab_statistics
WHERE table_name = 'SALES'
  AND partition_name IS NOT NULL
ORDER BY partition_position;
~~~

Các số liệu phụ thuộc thời điểm gather stats. Để đánh giá skew chính xác, kết hợp partition statistics, truy vấn phân bố theo join key và runtime plan.

### 8.3 Cách xử lý skew

- Chọn partition key có phân bố phù hợp hơn.
- Dùng composite partitioning nếu cần phân phối trong từng vùng quản trị.
- Xử lý hot key bằng chiến lược thiết kế dữ liệu riêng khi có căn cứ.
- Cân nhắc broadcast hoặc skew-aware distribution nếu phù hợp với truy vấn.
- Điều chỉnh DOP và kích thước granule theo workload.
- Không tạo quá nhiều partition chỉ để cố chia nhỏ một hot key nếu điều đó làm tăng chi phí quản trị.

## 9. Bài lab: thiết kế full partition-wise join

### 9.1 Tạo hai bảng tương thích

Trong schema lab riêng:

~~~sql
CREATE TABLE lab_customers (
    customer_id   NUMBER NOT NULL,
    customer_name VARCHAR2(100),
    CONSTRAINT pk_lab_customers PRIMARY KEY (customer_id)
)
PARTITION BY HASH (customer_id)
PARTITIONS 8;
~~~

~~~sql
CREATE TABLE lab_sales (
    sale_id     NUMBER NOT NULL,
    customer_id NUMBER NOT NULL,
    sale_date   DATE NOT NULL,
    amount      NUMBER(12,2)
)
PARTITION BY HASH (customer_id)
PARTITIONS 8;
~~~

Hai bảng được partition theo cùng key và cùng số partition. Trong môi trường thật, cần bảo đảm định nghĩa partition tương thích và kiểm tra khả năng full partition-wise join trên plan.

### 9.2 Nạp dữ liệu

~~~sql
INSERT INTO lab_customers
SELECT LEVEL,
       'Customer ' || LEVEL
FROM dual
CONNECT BY LEVEL <= 10000;

INSERT INTO lab_sales
SELECT LEVEL,
       MOD(LEVEL, 10000) + 1,
       DATE '2026-01-01' + MOD(LEVEL, 365),
       MOD(LEVEL, 1000) + 1
FROM dual
CONNECT BY LEVEL <= 1000000;

COMMIT;
~~~

### 9.3 Gather statistics

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname          => USER,
        tabname          => 'LAB_CUSTOMERS',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        cascade          => TRUE
    );

    DBMS_STATS.GATHER_TABLE_STATS(
        ownname          => USER,
        tabname          => 'LAB_SALES',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        cascade          => TRUE
    );
END;
/
~~~

Thống kê chính xác giúp optimizer ước lượng cardinality và cost tốt hơn. Với partitioned table, có thể cần kiểm tra cả global và partition statistics theo chiến lược thống kê của hệ thống.

### 9.4 Chạy JOIN

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       c.customer_id,
       c.customer_name,
       SUM(s.amount) AS total_amount
FROM lab_customers c
JOIN lab_sales s
  ON s.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name;
~~~

Sau khi chạy, xem cursor plan:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PARTITION +PARALLEL +PREDICATE +ALIAS'
    )
);
~~~

Kiểm tra operation và PX distribution. Tên operation cụ thể thay đổi theo phiên bản và kế hoạch; tìm dấu hiệu các partition được xử lý tương ứng và xem có redistribution hay không. Không kết luận full partition-wise join chỉ từ việc thấy TABLE ACCESS FULL trên các bảng partitioned.

### 9.5 Kiểm tra pruning

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       c.customer_id,
       SUM(s.amount) AS total_amount
FROM lab_customers c
JOIN lab_sales s
  ON s.customer_id = c.customer_id
WHERE c.customer_id = 42
GROUP BY c.customer_id;
~~~

Vì hai bảng hash partition theo CUSTOMER_ID, Oracle có thể xác định partition cần truy cập. Trong plan, xem PSTART/PSTOP hoặc partition start/stop tương ứng. Phần này minh họa pruning kết hợp với JOIN; truy vấn JOIN toàn bộ dữ liệu ở phần trước có thể partition-wise mà không prune partition.

## 10. Ví dụ partial partition-wise join

### 10.1 Tạo bảng dimension không partitioned

~~~sql
CREATE TABLE lab_customers_heap (
    customer_id   NUMBER PRIMARY KEY,
    customer_name VARCHAR2(100)
);
~~~

Nạp dữ liệu từ bảng đã có:

~~~sql
INSERT INTO lab_customers_heap
SELECT customer_id,
       customer_name
FROM lab_customers;
COMMIT;
~~~

SALES vẫn partition theo CUSTOMER_ID; CUSTOMERS_HEAP không partition. Điều kiện JOIN vẫn là CUSTOMER_ID.

### 10.2 Truy vấn

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       c.customer_id,
       c.customer_name,
       SUM(s.amount) AS total_amount
FROM lab_customers_heap c
JOIN lab_sales s
  ON s.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name;
~~~

Optimizer có thể chọn partial partition-wise join nếu kế hoạch phân phối phù hợp. Với dimension nhỏ, optimizer cũng có thể chọn broadcast join. Kết quả phụ thuộc cardinality, DOP, memory và thống kê.

### 10.3 Xem plan và phân phối

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PARTITION +PARALLEL +PREDICATE'
    )
);
~~~

Quan sát PX SEND, PX RECEIVE, HASH JOIN hoặc các operation partition-related. Việc có PX operation không tự chứng minh partial partition-wise join; cần đọc toàn bộ cây plan và xem bảng nào được phân phối, partition nào được xử lý.

## 11. Partition-wise join với range và composite partitioning

### 11.1 Hai bảng range-partitioned tương thích

Nếu hai bảng cùng partition theo SALE_DATE với các ranh giới thời gian tương ứng và JOIN theo SALE_DATE hoặc điều kiện tương thích với partitioning, Oracle có thể xử lý cặp partition tương ứng.

Ví dụ partition theo tháng:

~~~text
ORDERS:
  P2026_01: sale_date < 2026-02-01
  P2026_02: sale_date < 2026-03-01

ORDER_LINES:
  P2026_01: sale_date < 2026-02-01
  P2026_02: sale_date < 2026-03-01
~~~

Trong thực tế, ORDER_LINES thường partition theo ORDER_DATE kế thừa từ ORDERS bằng reference partitioning hoặc dùng cấu trúc tương thích. Cần thiết kế quan hệ và partition boundaries chính xác; hai bảng có partition tên giống nhau nhưng boundary khác không tạo ra equipartitioning.

### 11.2 Composite partitioning

Nếu cả hai bảng có cùng range partition theo thời gian và subpartition hash theo CUSTOMER_ID với cấu trúc tương ứng, Oracle có thể khai thác partition/subpartition alignment cho truy vấn phù hợp. Tuy nhiên, điều kiện cụ thể phụ thuộc cách định nghĩa composite partitioning và join predicate.

### 11.3 Reference partitioning

Với bảng cha và con có khóa ngoại, reference partitioning cho phép partition con theo partition của bảng cha. Đây là cách tự nhiên để đồng vị trí dữ liệu quan hệ, đặc biệt khi truy vấn thường JOIN parent-child. Việc tạo FK cần bảo đảm ràng buộc và index theo yêu cầu ứng dụng.

## 12. Join method bên trong mỗi cặp partition

Partition-wise join nói về cách chia vùng dữ liệu cho phép JOIN, không bắt buộc chỉ dùng một join method.

Trong từng cặp partition, Oracle vẫn có thể chọn:

- **Nested loops:** phù hợp khi một phía rất nhỏ hoặc truy cập bằng index cho số dòng ít.
- **Hash join:** thường phù hợp khi hai tập dữ liệu lớn và có thể xây hash table.
- **Sort merge join:** phù hợp trong một số trường hợp dữ liệu đã có thứ tự hoặc cost sort/merge có lợi.

Ví dụ:

~~~text
Partition pair P01:
    HASH JOIN(CUSTOMERS_P01, SALES_P01)

Partition pair P02:
    HASH JOIN(CUSTOMERS_P02, SALES_P02)

Partition pair P03:
    HASH JOIN(CUSTOMERS_P03, SALES_P03)
~~~

Partition-wise không đồng nghĩa hash join; đó là cách chia công việc theo partition. Join method cụ thể được optimizer chọn độc lập theo cost.

## 13. Global index, local index và partition-wise join

### 13.1 Local index

Local index được partition tương ứng với partition của bảng. Nó thuận tiện cho quản trị partition và có thể hỗ trợ truy vấn trong từng partition.

~~~sql
CREATE INDEX ix_lab_sales_customer_local
ON lab_sales (customer_id)
LOCAL;
~~~

Local index có thể hữu ích cho truy cập index trong partition, nhưng bản thân local index không tạo ra full partition-wise join. Điều kiện cốt lõi vẫn là partitioning của các bảng và JOIN.

### 13.2 Global index

Global index có partitioning/structure độc lập với partition của bảng. Nó có thể hữu ích cho truy vấn theo khóa không trùng partition key, nhưng thao tác maintenance partition có thể ảnh hưởng trạng thái global index tùy câu lệnh và option.

### 13.3 Không nhầm index partitioning với table partition alignment

Partition-wise join là kỹ thuật trên các row source/table partitions trong phép JOIN. Hai index đều là local không có nghĩa hai bảng đã equipartitioned theo join key. Cần xem định nghĩa partition của bảng, không chỉ index.

## 14. Đọc execution plan để xác nhận

### 14.1 Thu thập actual statistics

Chạy truy vấn với GATHER_PLAN_STATISTICS:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       ...
FROM ...
JOIN ... ON ...;
~~~

Sau đó:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PARTITION +PARALLEL +PREDICATE +ALIAS'
    )
);
~~~

### 14.2 Những điều cần đọc

- **Operation:** HASH JOIN, NESTED LOOPS, PARTITION HASH ALL, TABLE ACCESS FULL...
- **PSTART/PSTOP:** partition start/stop, giúp xem partition pruning hoặc phạm vi partition.
- **PX SEND/PX RECEIVE:** dữ liệu được truyền giữa các parallel execution server.
- **Distribution method:** HASH, BROADCAST, PARTITION hoặc cách phân phối khác thể hiện trong plan.
- **E-Rows/A-Rows:** số dòng ước lượng và thực tế.
- **Buffers/Reads:** logical và physical I/O.
- **TempSpc:** không gian tạm ước lượng/hiển thị cho một số operation.

Operation names và cách trình bày thay đổi theo phiên bản, plan và loại partition. Hãy đọc cây plan từ trên xuống theo quan hệ parent/child, không chỉ tìm một từ khóa.

### 14.3 Dấu hiệu full partition-wise join

Kỳ vọng chính là hai phía JOIN được xử lý theo các partition tương ứng mà không cần repartition cả hai tập dữ liệu theo join key. Với parallel execution, plan có thể thể hiện partition-wise distribution/operation. Hãy xác nhận:

1. Hai bảng thực sự equipartitioned theo join key.
2. Join predicate chứa quan hệ partition key cần thiết.
3. Plan không có redistribution không cần thiết của cả hai phía trước JOIN.
4. Actual rows/buffers phù hợp với dự đoán.

Không có một operation name duy nhất xuất hiện trong mọi phiên bản để nhận diện mọi full partition-wise join.

### 14.4 Dấu hiệu partial partition-wise join

Xác định phía đã partition, phía không partition hoặc không tương thích, và xem plan phân phối phía còn lại để khớp với partitioned side. Phân biệt cách này với broadcast dimension hoặc hash repartition thông thường.

## 15. Tổ chức truy vấn theo vùng dữ liệu

Partition-wise join phát huy hiệu quả khi thiết kế truy vấn và dữ liệu cùng tôn trọng vùng phân hoạch.

### 15.1 Dùng predicate trên partition key khi có thể

Ví dụ bảng SALES range-partition theo SALE_DATE:

~~~sql
SELECT ...
FROM sales
WHERE sale_date >= :p_from_date
  AND sale_date <  :p_to_date;
~~~

Dùng khoảng nửa mở [from, to) giúp định nghĩa ranh giới rõ và thường hỗ trợ partition pruning. Tránh bọc partition key trong hàm nếu điều đó làm Oracle khó suy ra partition range, trừ khi có thiết kế expression-based phù hợp.

### 15.2 Giữ điều kiện JOIN rõ ràng

~~~sql
ON s.customer_id = c.customer_id
~~~

Điều kiện JOIN trực tiếp theo partition key dễ giúp optimizer nhận ra quan hệ phân vùng. Nếu phải chuyển đổi kiểu dữ liệu hoặc áp dụng hàm lên join key, cần kiểm tra optimizer có thể suy ra quan hệ và dùng partition-wise join hay không.

### 15.3 Tránh ép join order hoặc DOP khi chưa có bằng chứng

Hints như LEADING, USE_HASH, PARALLEL có thể thay đổi plan. Chỉ dùng khi có kiểm chứng trên workload đại diện và có lý do rõ. Một hint có thể giúp một bind value nhưng làm truy vấn khác chậm đi.

### 15.4 Tổ chức vùng dữ liệu theo tenant

Trong ứng dụng multi-tenant, partition theo TENANT_ID có thể giúp cô lập dữ liệu và prune theo tenant. Nếu nhiều bảng lớn đều partition tương thích theo TENANT_ID và JOIN theo tenant cùng khóa nghiệp vụ, partition-wise join có thể giảm redistribution.

Tuy nhiên, tenant lớn bất thường có thể gây skew. Có thể cần subpartition hoặc chiến lược riêng cho tenant lớn, nhưng phải cân nhắc chi phí quản trị và tính tương thích partition.

## 16. Hiệu năng và giới hạn thực tế

Partition-wise join có thể giảm communication cost nhưng không tự làm giảm mọi chi phí:

- Tổng số dòng phải JOIN vẫn như cũ.
- Một partition quá lớn có thể trở thành bottleneck.
- Hash join vẫn cần bộ nhớ; có thể spill ra TEMP.
- Partition count quá lớn làm tăng metadata và overhead quản trị.
- DOP cao có thể tranh CPU, I/O và interconnect.
- Statistics sai có thể khiến optimizer chọn sai join method hoặc phân phối.
- Data skew có thể làm một số PX server chạy lâu hơn nhiều server khác.
- Partition-wise join không thay thế partition pruning, indexing hoặc query rewrite.

### 16.1 Partition count

Không chọn số partition chỉ theo số core CPU. Cần xem:

- Tổng kích thước dữ liệu và tốc độ tăng trưởng.
- DOP mong muốn.
- Kích thước partition trung bình và skew.
- Số bảng liên quan và khả năng equipartition.
- Thời gian maintenance, backup, recovery và statistics.

### 16.2 Statistics ở table và partition level

Partitioned table cần thống kê phù hợp ở cả cấp partition và global. Nếu global stats hoặc partition stats không nhất quán, optimizer có thể ước lượng sai số dòng, pruning và join cost.

Thu thập thống kê:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname          => USER,
        tabname          => 'SALES',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        granularity      => 'AUTO',
        cascade          => TRUE
    );
END;
/
~~~

GRANULARITY => 'AUTO' yêu cầu Oracle chọn cách thu thập phù hợp với partitioning. Chiến lược stats cụ thể còn phụ thuộc incremental statistics, global stats và cách nạp dữ liệu.

### 16.3 Incremental statistics

Với partitioned table lớn, incremental statistics có thể giúp duy trì global statistics bằng cách tổng hợp thông tin từ partition thay đổi thay vì quét lại toàn bộ bảng trong một số trường hợp được hỗ trợ. Đây là tính năng cần cấu hình preference và đánh giá theo phiên bản/license/cấu hình hệ thống; không bật chỉ dựa trên một ví dụ.

## 17. Những ngộ nhận thường gặp

| Ngộ nhận | Thực tế | Cách xử lý |
|---|---|---|
| Hai bảng partitioned luôn có full partition-wise join | Phải partition tương thích theo join key | Kiểm tra partition key/method/boundaries |
| Partition-wise join và partition pruning là một | Một kỹ thuật chia JOIN, một kỹ thuật bỏ partition | Phân tích riêng từng lợi ích |
| Cùng số partition là đủ | Còn cần partitioning scheme tương ứng | Xác nhận equipartitioning |
| Local index tạo ra partition-wise join | Join dựa trên partitioning của bảng và điều kiện JOIN | Xem table partition metadata |
| Full partition-wise join luôn nhanh hơn | Với bảng nhỏ hoặc skew, plan khác có thể rẻ hơn | So actual runtime/cost |
| Partial partition-wise join giống broadcast join | Partial redistributes phía chưa partition tương thích; broadcast là chiến lược riêng | Đọc PX distribution |
| Partition-wise join luôn cần parallel query | Có thể xử lý theo partition; parallelism là một cách tăng throughput | Xem plan và workload |
| Có partition là tự động prune | Cần predicate/điều kiện có thể xác định partition | Xem PSTART/PSTOP |
| Cùng tên partition nghĩa là tương ứng | Tên không chứng minh boundary hoặc hash mapping giống nhau | So sánh định nghĩa partition |
| Hash partition luôn cân bằng hoàn toàn | Hot key có thể tạo skew | Đo số dòng và block từng partition |
| Tăng DOP luôn giảm thời gian | Có thể tăng contention và communication | Benchmark theo SLA |
| Partition-wise join loại bỏ mọi network traffic | Partial join và các bước khác vẫn có thể redistribute | Xem PX SEND/RECEIVE |
| Repartition cả hai bảng luôn cần thiết | Full partition-wise join có thể tránh bước đó | Thiết kế equipartitioning |

## 18. Checklist thiết kế và phân tích

Khi muốn dùng partition-wise join, hãy kiểm tra:

1. Những truy vấn JOIN lớn nào thực sự chiếm tài nguyên?
2. Join key nào được dùng thường xuyên và có phân bố dữ liệu ra sao?
3. Các bảng lớn có thể partition tương thích theo join key không?
4. Partitioning key có phục vụ cả pruning, retention và quản trị dữ liệu không?
5. Hai bảng có cùng partitioning method, số partition và boundaries tương ứng không?
6. Join predicate có kết nối đúng partition key không?
7. Có thể dùng full partition-wise join hay chỉ partial?
8. Nếu một phía nhỏ, broadcast có rẻ hơn redistribution không?
9. Partition sizes và join-key distribution có skew không?
10. DOP và số partition có phù hợp không?
11. Global/partition statistics có được thu thập đầy đủ không?
12. Execution plan có cho thấy partition access và PX distribution như mong đợi không?
13. E-Rows có gần A-Rows không?
14. Buffers, Reads, TEMP và elapsed time thay đổi thế nào?
15. Các DML, index maintenance và partition operations có tăng chi phí đáng kể không?
16. Sau khi thêm partition hoặc thay đổi partition boundaries, các bảng liên quan còn equipartitioned không?

## 19. Bài tập tự luyện

**Câu 1 — Khái niệm.** Partition-wise join giảm chi phí nào khi hai bảng được partition tương thích?

Gợi ý: Giảm nhu cầu phân phối lại dữ liệu giữa các PX server và chia JOIN theo cặp partition.

**Câu 2 — Full join.** Hai bảng cùng hash partition theo CUSTOMER_ID, cùng số partition và mapping tương ứng; JOIN theo CUSTOMER_ID. Có thể dùng dạng nào?

Gợi ý: Có điều kiện cho full partition-wise join; vẫn cần optimizer chọn và plan xác nhận.

**Câu 3 — Không tương thích.** SALES partition theo SALE_DATE, CUSTOMERS partition theo CUSTOMER_ID; JOIN theo CUSTOMER_ID. Có đủ điều kiện full partition-wise join không?

Gợi ý: Không chỉ từ thiết kế này; hai bảng không cùng partition theo join key.

**Câu 4 — Partial join.** SALES partition theo CUSTOMER_ID, CUSTOMERS là heap table. Điều gì có thể xảy ra?

Gợi ý: Oracle có thể phân phối phía CUSTOMERS để khớp với partition của SALES trong partial partition-wise join; hoặc chọn broadcast/plan khác.

**Câu 5 — Pruning.** JOIN theo CUSTOMER_ID nhưng không có filter trên partition key. Có thể vẫn partition-wise join không?

Gợi ý: Có. Partition-wise join không yêu cầu phải prune partition; nó có thể JOIN mọi cặp partition.

**Câu 6 — Skew.** Một partition có số dòng gấp 10 lần các partition khác gây vấn đề gì?

Gợi ý: Một PX server xử lý partition lớn có thể trở thành bottleneck, các server khác chờ.

**Câu 7 — Local index.** Hai bảng có local index cùng tên nhưng partition scheme không tương thích. Có đủ điều kiện full partition-wise join không?

Gợi ý: Không. Cần xem table partitioning, không suy ra từ index.

**Câu 8 — DOP.** Có 4 partition nhưng yêu cầu DOP 16. Có chắc 16 server đều có công việc partition độc lập không?

Gợi ý: Không. Granule và kế hoạch phân công phụ thuộc partition; số partition không phải lúc nào cũng bằng số PX server hoạt động hữu ích.

**Câu 9 — Broadcast.** Dimension nhỏ được gửi đến mọi PX server có phải partial partition-wise join không?

Gợi ý: Không nhất thiết. Broadcast là một chiến lược phân phối riêng; cần đọc plan.

**Câu 10 — Xác nhận.** Cần xem gì ngoài EXPLAIN PLAN để đánh giá hiệu năng?

Gợi ý: Actual rows, buffers, reads, TEMP, PX distribution và runtime qua DBMS_XPLAN.DISPLAY_CURSOR.

## 20. Tổng kết

Partition-wise join tổ chức phép JOIN theo các vùng dữ liệu đã partition để giảm công việc di chuyển và phối hợp dữ liệu:

- **Full partition-wise join** có thể thực hiện khi hai bảng equipartitioned tương thích theo join key; Oracle JOIN các cặp partition tương ứng.
- **Partial partition-wise join** áp dụng khi một phía đã partition phù hợp và phía còn lại được phân phối để khớp.
- **Partition pruning** giảm số partition phải đọc; nó khác với partition-wise join và có thể kết hợp cùng kỹ thuật này.
- **Parallel execution** giúp xử lý các cặp partition đồng thời, nhưng DOP cần phù hợp với số partition, kích thước dữ liệu và tài nguyên.
- **Skew** có thể làm một partition trở thành bottleneck dù JOIN đã được chia theo partition.
- Local index hỗ trợ truy cập trong partition nhưng không tự tạo partition-wise join.
- Execution plan, PX distribution, PSTART/PSTOP, actual rows, buffers và reads là bằng chứng cần xem trước khi kết luận.

Thiết kế partition-wise join tốt bắt đầu từ workload: chọn partition key phục vụ JOIN quan trọng mà vẫn đáp ứng pruning, retention và quản trị dữ liệu. Sau đó xác nhận equipartitioning, đo skew, thu thập statistics và kiểm tra actual execution plan. Partitioning chỉ có giá trị khi cách tổ chức dữ liệu phù hợp với các truy vấn thực tế và tổng chi phí vận hành.
