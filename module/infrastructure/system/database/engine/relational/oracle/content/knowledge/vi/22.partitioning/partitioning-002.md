# Range, list, hash và interval partitioning

Partitioning (phân vùng) chia dữ liệu của một bảng hoặc index lớn thành các phần nhỏ hơn gọi là partition. Ứng dụng vẫn truy vấn bảng như một đối tượng logic duy nhất; Oracle quản lý các partition ở mức vật lý và có thể loại bỏ những partition không liên quan đến truy vấn.

Trong Oracle Database, bốn phương pháp cơ bản thường gặp là:

- **Range partitioning:** phân vùng theo khoảng giá trị có thứ tự, thường dùng cho ngày tháng hoặc số.
- **List partitioning:** phân vùng theo tập giá trị được liệt kê, thường dùng cho khu vực, trạng thái hoặc loại nghiệp vụ.
- **Hash partitioning:** Oracle áp dụng hàm băm trên partition key để phân phối hàng tương đối đều giữa các partition.
- **Interval partitioning:** mở rộng range partitioning; Oracle tự tạo partition mới khi dữ liệu đi vào khoảng interval chưa tồn tại.

Chọn đúng phương pháp dựa trên cách truy vấn, cách dữ liệu tăng trưởng, quy tắc lưu trữ và nhu cầu bảo trì. Partitioning không tự làm mọi câu SQL nhanh hơn. Lợi ích hiệu năng thường đến từ **partition pruning** (loại bỏ partition không cần đọc), còn lợi ích vận hành đến từ khả năng quản lý, nạp, lưu trữ và loại bỏ dữ liệu theo từng partition.

Các ví dụ dưới đây dùng cú pháp Oracle 19c. Partitioning là tính năng có điều kiện cấp phép tùy edition/offer và phiên bản Oracle; hãy xác nhận quyền sử dụng của môi trường trước khi triển khai production.

## 1. Partitioning hoạt động ở mức nào?

Một bảng partitioned vẫn có một tên logic duy nhất:

~~~text
APPLICATION SQL
      |
      v
  SALES TABLE
      |
      +-------------------+-------------------+
      |                   |                   |
      v                   v                   v
  PARTITION P1        PARTITION P2        PARTITION P3
  older rows          current rows        future rows
~~~

Ứng dụng có thể chạy:

~~~sql
SELECT SUM(amount)
FROM sales
WHERE sale_date >= DATE '2024-01-01'
  AND sale_date <  DATE '2024-02-01';
~~~

Nếu bảng được partition theo SALE_DATE, optimizer có thể chỉ đọc các partition chứa khoảng ngày cần tìm. Câu SQL vẫn tham chiếu bảng SALES; thông thường ứng dụng không cần biết tên partition.

### 1.1. Partition key

Partition key là một hoặc nhiều cột Oracle dùng để quyết định hàng thuộc partition nào. Khi thiết kế, hãy chọn key dựa trên:

- Predicate thường xuất hiện trong WHERE và join.
- Cách dữ liệu được tạo theo thời gian hoặc theo nhóm nghiệp vụ.
- Quy tắc xóa/archive dữ liệu.
- Phân phối giá trị và mức độ mất cân bằng giữa partition.
- Khả năng giữ unique key, foreign key và index theo yêu cầu.

Ví dụ:

| Bảng | Partition key có thể phù hợp | Lý do |
| --- | --- | --- |
| SALES, ORDERS, AUDIT_LOG | SALE_DATE, ORDER_DATE, EVENT_TIME | Truy vấn theo thời gian, archive/drop dữ liệu cũ |
| CUSTOMER_BY_REGION | REGION_CODE | Truy vấn và quản trị theo khu vực |
| TRANSACTIONS_BY_ACCOUNT | ACCOUNT_ID với HASH | Phân phối dữ liệu theo account khi không có ranh giới nghiệp vụ tự nhiên |
| SALES theo tháng tự sinh | SALE_DATE với INTERVAL | Không muốn tạo thủ công từng partition thời gian |

Không chọn partition key chỉ vì cột có nhiều giá trị. Một key có cardinality cao nhưng hầu như không xuất hiện trong predicate truy vấn có thể không đem lại pruning hữu ích.

### 1.2. Partition pruning

Partition pruning là khả năng optimizer bỏ qua partition không thể chứa hàng thỏa điều kiện truy vấn. Đây thường là nguồn lợi ích hiệu năng lớn nhất của partitioning.

Ví dụ, với bảng range partition theo SALE_DATE:

~~~sql
SELECT COUNT(*)
FROM sales
WHERE sale_date >= DATE '2024-01-01'
  AND sale_date <  DATE '2024-02-01';
~~~

Oracle có thể chỉ đọc partition tháng 1. Predicate dạng khoảng nửa mở (>= đầu khoảng, < đầu khoảng kế tiếp) cũng tránh lỗi biên thời gian khi cột chứa giờ/phút/giây.

Partition pruning có thể là:

- **Static pruning:** optimizer xác định partition từ literal hoặc biểu thức có thể tính lúc parse.
- **Dynamic pruning:** partition được xác định trong runtime, ví dụ từ bind variable hoặc giá trị join tùy kế hoạch thực thi.

Không phải truy vấn nào trên bảng partitioned cũng prune được. Nếu predicate không ràng buộc partition key, Oracle có thể phải đọc nhiều hoặc tất cả partition.

## 2. Range partitioning

Range partitioning chia miền giá trị thành các khoảng liên tiếp theo thứ tự. Mỗi partition khai báo **giới hạn trên không bao gồm** bằng VALUES LESS THAN.

### 2.1. Cú pháp

~~~sql
CREATE TABLE sales_range (
    sale_id     NUMBER NOT NULL,
    sale_date   DATE NOT NULL,
    customer_id NUMBER NOT NULL,
    amount      NUMBER(12, 2)
)
PARTITION BY RANGE (sale_date) (
    PARTITION p_before_2024
        VALUES LESS THAN (DATE '2024-01-01'),
    PARTITION p_2024_h1
        VALUES LESS THAN (DATE '2024-07-01'),
    PARTITION p_future
        VALUES LESS THAN (MAXVALUE)
);
~~~

Các partition được hiểu như sau:

| Partition | Miền giá trị của SALE_DATE |
| --- | --- |
| P_BEFORE_2024 | Nhỏ hơn 2024-01-01 |
| P_2024_H1 | Từ 2024-01-01 đến trước 2024-07-01 |
| P_FUTURE | Từ 2024-07-01 trở đi |

VALUES LESS THAN là biên trên loại trừ. Ngày 2024-07-01 không nằm trong P_2024_H1; nó thuộc partition kế tiếp.

Partition đầu tiên không khai báo biên dưới; nó nhận mọi giá trị nhỏ hơn biên trên đầu tiên. Partition cuối MAXVALUE nhận các giá trị lớn hơn hoặc bằng biên trước đó.

### 2.2. Chèn dữ liệu và xác định partition

~~~sql
INSERT INTO sales_range VALUES
    (1, DATE '2023-12-15', 101, 100);

INSERT INTO sales_range VALUES
    (2, DATE '2024-02-10', 102, 200);

INSERT INTO sales_range VALUES
    (3, DATE '2024-08-20', 103, 300);

COMMIT;
~~~

Kết quả:

- Hàng 1 vào P_BEFORE_2024.
- Hàng 2 vào P_2024_H1.
- Hàng 3 vào P_FUTURE.

Nếu không có partition nào nhận được giá trị key, INSERT có thể báo ORA-14400: inserted partition key does not map to any partition. Vì vậy, với range table không có MAXVALUE, phải tạo partition trước khi nạp dữ liệu thuộc miền mới.

### 2.3. NULL trong range partition

Với range partitioning, giá trị NULL được xem là nhỏ hơn các giá trị không NULL và được đưa vào partition đầu tiên. Nếu cột partition key khai báo NOT NULL, tình huống này bị chặn bởi constraint trước khi trở thành dữ liệu của bảng.

Không nên dựa vào hành vi NULL để thay thế quy tắc nghiệp vụ. Nếu ngày giao dịch bắt buộc phải có, khai báo NOT NULL và xử lý dữ liệu thiếu ở staging.

### 2.4. Chọn ranh giới partition

Ranh giới nên phù hợp với workload và chu kỳ lưu trữ:

- Theo ngày nếu truy vấn/retention yêu cầu độ chi tiết ngày.
- Theo tháng nếu lượng dữ liệu lớn và nghiệp vụ quản trị theo tháng.
- Theo quý/năm nếu dữ liệu tăng chậm hoặc truy vấn ít cần phạm vi hẹp.

Không tạo hàng nghìn partition nhỏ chỉ vì có thể làm vậy. Mỗi partition thêm metadata và chi phí quản trị; số lượng phù hợp phụ thuộc kích thước bảng, release Oracle và workload.

### 2.5. Range pruning

~~~sql
SELECT sale_id, sale_date, amount
FROM sales_range
WHERE sale_date >= DATE '2024-01-01'
  AND sale_date <  DATE '2024-07-01';
~~~

Predicate trên khớp miền của P_2024_H1, nên optimizer có thể loại bỏ hai partition còn lại. Để xác nhận, xem execution plan và các cột PSTART, PSTOP.

## 3. List partitioning

List partitioning phân chia hàng theo **các giá trị được liệt kê rõ ràng**. Phương pháp này phù hợp khi miền giá trị có nhóm nghiệp vụ rời rạc, ví dụ mã khu vực, loại sản phẩm hoặc trạng thái.

### 3.1. Cú pháp

~~~sql
CREATE TABLE customers_by_region (
    customer_id NUMBER NOT NULL,
    region_code VARCHAR2(10) NOT NULL,
    full_name   VARCHAR2(100)
)
PARTITION BY LIST (region_code) (
    PARTITION p_north
        VALUES ('N', 'NE'),
    PARTITION p_south
        VALUES ('S', 'SE'),
    PARTITION p_central
        VALUES ('C'),
    PARTITION p_other
        VALUES (DEFAULT)
);
~~~

Mỗi partition nhận một tập giá trị cụ thể. DEFAULT nhận các giá trị chưa được liệt kê trong partition khác, thuận tiện khi mã mới xuất hiện mà chưa có partition chuyên biệt.

### 3.2. NULL và DEFAULT

Với list partitioning, NULL là một giá trị có thể xuất hiện ở partition key. Nếu không liệt kê NULL ở một partition cụ thể, partition DEFAULT có thể nhận nó. Nếu không có DEFAULT và không partition nào nhận giá trị nguồn, INSERT có thể báo ORA-14400.

Nếu REGION_CODE là bắt buộc, khai báo NOT NULL như ví dụ. Nếu NULL có ý nghĩa nghiệp vụ, hãy quyết định rõ nó thuộc partition riêng hay DEFAULT.

### 3.3. Thêm giá trị mới

Khi một mã khu vực mới xuất hiện, có thể:

- Để hàng vào partition DEFAULT.
- Tạo partition chuyên biệt và chuyển giá trị từ DEFAULT sang partition mới bằng thao tác bảo trì phù hợp.

Ví dụ thêm partition cho mã NW:

~~~sql
ALTER TABLE customers_by_region
SPLIT PARTITION p_other
VALUES ('NW')
INTO (
    PARTITION p_northwest,
    PARTITION p_other
);
~~~

SPLIT PARTITION tách partition DEFAULT thành partition mới cho giá trị được chỉ định và partition DEFAULT còn lại. Hãy kiểm tra cú pháp/giới hạn theo release và bảo đảm tên partition chưa tồn tại.

### 3.4. List pruning

~~~sql
SELECT customer_id, full_name
FROM customers_by_region
WHERE region_code IN ('N', 'NE');
~~~

Oracle có thể chỉ đọc P_NORTH. Nếu predicate không lọc theo REGION_CODE, list partitioning không tự tạo lợi ích pruning.

### 3.5. Khi nào nên dùng list?

List phù hợp khi nhóm giá trị có ý nghĩa quản trị và tương đối ổn định. Nếu mã mới xuất hiện thường xuyên, DEFAULT giúp tiếp nhận dữ liệu nhưng cũng có thể tích tụ quá nhiều nhóm khác nhau trong một partition. Cần theo dõi giá trị trong DEFAULT và có quy trình phân loại lại.

Không dùng list partitioning cho cột có hàng triệu giá trị riêng biệt như customer ID; số lượng nhóm quá lớn làm thiết kế khó quản lý. Với mục tiêu phân phối đều theo khóa, xem xét hash partitioning.

## 4. Hash partitioning

Hash partitioning dùng hàm băm của Oracle trên partition key để phân phối hàng vào các partition. Người thiết kế chỉ định số lượng partition; Oracle quyết định hàng nào vào partition nào.

### 4.1. Cú pháp

~~~sql
CREATE TABLE customer_events_hash (
    event_id    NUMBER NOT NULL,
    customer_id NUMBER NOT NULL,
    event_time  TIMESTAMP NOT NULL,
    payload     VARCHAR2(200)
)
PARTITION BY HASH (customer_id)
PARTITIONS 8;
~~~

Oracle tạo tám partition hash. Hàng có cùng giá trị CUSTOMER_ID được ánh xạ vào cùng partition; các customer ID khác được phân phối theo hash function.

Có thể đặt tên partition tường minh:

~~~sql
CREATE TABLE account_activity_hash (
    activity_id NUMBER NOT NULL,
    account_id  NUMBER NOT NULL,
    activity_at DATE NOT NULL
)
PARTITION BY HASH (account_id) (
    PARTITION p_h1,
    PARTITION p_h2,
    PARTITION p_h3,
    PARTITION p_h4
);
~~~

### 4.2. Khi nào hash hữu ích?

Hash thường hữu ích khi:

- Không có range hoặc list boundary tự nhiên.
- Muốn phân phối hàng trên nhiều partition để giảm tập trung dữ liệu.
- Truy vấn thường tìm theo equality trên partition key.
- Cần tận dụng partition-wise processing khi các bảng được partition tương thích.

Hash không sắp xếp dữ liệu theo thời gian hoặc theo giá trị key. Nó không thay thế range partitioning khi cần archive dữ liệu cũ theo tháng.

### 4.3. Hash pruning

~~~sql
SELECT *
FROM customer_events_hash
WHERE customer_id = 10042;
~~~

Vì predicate xác định giá trị hash key, Oracle có thể xác định partition liên quan. Nếu query không có điều kiện trên CUSTOMER_ID, Oracle có thể phải đọc tất cả partition.

Với predicate chỉ lọc EVENT_TIME, hash partitioning theo CUSTOMER_ID thường không giúp loại partition theo thời gian. Đây là lý do phải chọn partition key theo truy vấn thực tế.

### 4.4. Phân phối không đảm bảo tuyệt đối cân bằng

Hash giúp phân phối tốt hơn trong nhiều trường hợp, nhưng không bảo đảm mỗi partition có đúng cùng số hàng hoặc cùng dung lượng. Nếu key có skew, ví dụ một customer chiếm phần lớn giao dịch, các hàng của customer đó vẫn đi cùng partition và tạo hotspot.

Chọn key có phân phối phù hợp và đo dữ liệu thật. Số partition ảnh hưởng mức song song, kích thước segment và chi phí quản trị; không chọn số lớn chỉ để tăng tốc.

### 4.5. Hash subpartitioning

Oracle cũng cho phép kết hợp các phương pháp trong composite partitioning, ví dụ range theo ngày rồi hash theo customer. Cách này có thể vừa quản trị vòng đời theo thời gian vừa phân phối dữ liệu trong mỗi khoảng thời gian. Composite partitioning là một thiết kế bổ sung; hãy đánh giá số lượng subpartition, index và maintenance trước khi áp dụng.

## 5. Interval partitioning

Interval partitioning mở rộng range partitioning cho dữ liệu tăng theo một bước đều, ví dụ mỗi tháng hoặc mỗi ngày. Người thiết kế khai báo một **transition point** bằng các range partition ban đầu và một interval. Khi dữ liệu mới vượt transition point, Oracle tự tạo partition interval tương ứng.

### 5.1. Cú pháp theo tháng

~~~sql
CREATE TABLE sales_interval (
    sale_id     NUMBER NOT NULL,
    sale_date   DATE NOT NULL,
    customer_id NUMBER NOT NULL,
    amount      NUMBER(12, 2)
)
PARTITION BY RANGE (sale_date)
INTERVAL (NUMTOYMINTERVAL(1, 'MONTH')) (
    PARTITION p_before_2024
        VALUES LESS THAN (DATE '2024-01-01')
);
~~~

Trong ví dụ:

- P_BEFORE_2024 là range partition ban đầu.
- Biên 2024-01-01 là transition point.
- Interval là một tháng.
- Khi chèn hàng thuộc tháng 1/2024 hoặc tháng sau, Oracle tạo interval partition tương ứng khi cần.

Interval partitioning yêu cầu một range partition ban đầu để xác định transition point. Partition interval được tạo tự động khi cần, không phải tạo sẵn tất cả partition tương lai.

### 5.2. Chèn dữ liệu và partition tự sinh

~~~sql
INSERT INTO sales_interval VALUES
    (1, DATE '2023-12-20', 101, 100);

INSERT INTO sales_interval VALUES
    (2, DATE '2024-01-15', 102, 200);

INSERT INTO sales_interval VALUES
    (3, DATE '2024-03-05', 103, 300);

INSERT INTO sales_interval VALUES
    (4, DATE '2024-03-25', 104, 400);

COMMIT;
~~~

Hàng tháng 1 và tháng 3 thuộc các interval partition tương ứng. Hai hàng tháng 3 cùng vào một partition tháng 3. Oracle thường đặt tên hệ thống cho interval partition mới nếu không có thao tác đổi tên; không nên hard-code tên SYS_P... trong ứng dụng.

### 5.3. Interval partition không tạo partition cho ngày cũ bất kỳ

Interval tự sinh áp dụng cho giá trị nằm **trên transition point**. Hàng cũ hơn transition point vẫn phải khớp một range partition đã khai báo. Nếu chỉ có partition ban đầu từ trước 2024, hàng năm 2022 có thể vào partition đó; nếu miền giá trị cũ không được bao phủ, INSERT có thể thất bại.

### 5.4. Kiểu dữ liệu và interval expression

Trong Oracle 19c, interval partitioning sử dụng một partition key đơn kiểu NUMBER hoặc DATE, với interval expression tương thích. Ví dụ:

~~~sql
-- Theo tháng cho DATE.
INTERVAL (NUMTOYMINTERVAL(1, 'MONTH'))

-- Theo ngày cho DATE.
INTERVAL (NUMTODSINTERVAL(1, 'DAY'))

-- Theo dải số.
INTERVAL (1000)
~~~

Kiểm tra kiểu cột và interval expression theo release Oracle đang chạy. Không dùng biểu thức interval thay đổi theo từng hàng; interval phải xác định bước phân vùng.

### 5.5. MAXVALUE và interval

Không khai báo một range partition MAXVALUE làm partition cuối cho interval-partitioned table. Interval partitioning cần khoảng phía trên transition point để Oracle tạo các partition mới. Hãy thiết kế range section và transition point theo đúng cú pháp interval.

### 5.6. Partition pruning trên interval table

~~~sql
SELECT SUM(amount)
FROM sales_interval
WHERE sale_date >= DATE '2024-03-01'
  AND sale_date <  DATE '2024-04-01';
~~~

Oracle có thể prune đến interval partition tháng 3. Cách truy vấn và kiểm tra pruning giống range partitioning.

## 6. So sánh bốn phương pháp

| Tiêu chí | RANGE | LIST | HASH | INTERVAL |
| --- | --- | --- | --- | --- |
| Cách phân loại | Khoảng giá trị có thứ tự | Tập giá trị liệt kê | Hàm băm trên key | Khoảng range tự tạo theo bước |
| Phù hợp | Ngày, số, thời gian | Khu vực, trạng thái, loại | Phân phối theo khóa | Dữ liệu thời gian/số tăng đều |
| Biên partition | VALUES LESS THAN | VALUES (...), có thể DEFAULT | Số lượng/partition names | Range transition point + interval |
| Tự tạo partition mới | Không | Không | Không theo giá trị mới | Có, khi dữ liệu vượt transition point |
| Pruning điển hình | Predicate range trên key | Equality/IN trên key | Equality/IN trên hash key | Predicate range trên key |
| Quản trị dữ liệu cũ | Rất phù hợp | Theo nhóm giá trị | Không thuận tiện theo thời gian | Rất phù hợp theo interval |
| Rủi ro thiết kế | Boundary gap/partition thiếu | DEFAULT tích tụ giá trị mới | Skew/hot partition | Interval/key/type và transition point |

### 6.1. Cây quyết định chọn phương pháp

~~~text
Có quy tắc khoảng giá trị tự nhiên?
       |
      YES --------------------> RANGE
       |
       NO
       v
Giá trị thuộc các nhóm nghiệp vụ liệt kê rõ?
       |
      YES --------------------> LIST
       |
       NO
       v
Cần phân phối hàng theo hash key?
       |
      YES --------------------> HASH
       |
       NO
       v
Dữ liệu tăng theo bước đều và muốn tự tạo partition?
       |
      YES --------------------> INTERVAL
       |
       NO
       v
Đánh giá lại partition key hoặc không partition
~~~

Nếu cần quản lý theo thời gian và phân phối hàng trong mỗi tháng, cân nhắc composite RANGE-HASH hoặc INTERVAL-HASH. Không thêm subpartition nếu workload không cần.

## 7. Truy vấn dữ liệu và chỉ định partition

### 7.1. Truy vấn bảng bình thường

~~~sql
SELECT *
FROM sales_range
WHERE sale_date >= DATE '2024-01-01'
  AND sale_date <  DATE '2024-07-01';
~~~

Đây là cách nên dùng trong phần lớn ứng dụng. Optimizer tự chọn partition dựa trên predicate.

### 7.2. Partition extension syntax

Trong kiểm tra hoặc bảo trì, có thể chỉ định partition:

~~~sql
SELECT *
FROM sales_range PARTITION (p_2024_h1);
~~~

Hoặc xác định partition theo giá trị key:

~~~sql
SELECT *
FROM sales_interval PARTITION FOR (DATE '2024-03-15');
~~~

Partition name và PARTITION FOR hữu ích cho thao tác chuyên biệt, nhưng ứng dụng nghiệp vụ thường nên truy vấn bảng với predicate key để tránh phụ thuộc vào tên partition.

### 7.3. Đọc execution plan để xác nhận pruning

~~~sql
EXPLAIN PLAN FOR
SELECT SUM(amount)
FROM sales_range
WHERE sale_date >= DATE '2024-01-01'
  AND sale_date <  DATE '2024-07-01';

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

Trong plan, tìm operation liên quan PARTITION RANGE hoặc thông tin partition start/stop:

- PSTART và PSTOP cho biết phạm vi partition được truy cập.
- Giá trị số có thể đại diện vị trí partition; KEY thường cho biết pruning được xác định khi chạy.
- Plan thực tế còn phụ thuộc statistics, bind variable và optimizer environment.

EXPLAIN PLAN cho biết kế hoạch dự kiến. Khi cần biết runtime plan và số hàng thực tế, DBA có thể dùng các phương pháp hiển thị cursor plan phù hợp, có cân nhắc quyền và license của tính năng liên quan.

## 8. Quản lý index trên bảng partitioned

Partitioned table có thể dùng local index hoặc global index. Lựa chọn index ảnh hưởng hiệu năng truy vấn, uniqueness và thao tác bảo trì partition.

### 8.1. Local index

Local index được chia partition tương ứng với partition của bảng. Mỗi index partition chỉ phục vụ phần dữ liệu tương ứng của table partition.

~~~sql
CREATE INDEX ix_sales_range_customer_local
ON sales_range (customer_id)
LOCAL;
~~~

Đặc điểm:

- Index partition được quản lý cùng table partition.
- Partition maintenance thường dễ đồng bộ với local index.
- Partition pruning trên bảng và index có thể phối hợp.
- Mỗi index partition có phạm vi dữ liệu tương ứng với table partition.

### 8.2. Global index

Global index có phạm vi vượt qua ranh giới một table partition. Nó có thể là nonpartitioned global index hoặc partitioned global index với scheme độc lập.

~~~sql
CREATE INDEX ix_sales_range_sale_id_global
ON sales_range (sale_id)
GLOBAL;
~~~

Global index hữu ích khi cần truy cập theo khóa không bao gồm partition key hoặc cần enforce uniqueness trên toàn bảng. Đổi lại, thao tác DROP/TRUNCATE/SPLIT/MERGE partition có thể cần bảo trì global index để tránh index unusable hoặc phát sinh chi phí cập nhật.

### 8.3. Unique constraint và partition key

Một unique local index chỉ có thể bảo đảm uniqueness trong từng index partition. Để uniqueness được bảo đảm trên toàn bảng bằng local unique index, khóa unique phải bao gồm partition key.

Ví dụ bảng range-partition theo SALE_DATE:

- Unique key (SALE_ID, SALE_DATE) có thể phù hợp với local unique index.
- Unique key chỉ (SALE_ID) không chứa partition key; để bảo đảm SALE_ID duy nhất trên toàn bảng, thường cần global unique index/constraint phù hợp.

Không loại bỏ unique constraint chỉ để dùng local index. Hãy xác định uniqueness là toàn bảng hay chỉ trong phạm vi partition trước khi thiết kế.

### 8.4. Kiểm tra index partition

~~~sql
SELECT
    index_name,
    partitioned,
    status
FROM user_indexes
WHERE table_name = 'SALES_RANGE'
ORDER BY index_name;

SELECT
    index_name,
    partition_name,
    status
FROM user_ind_partitions
WHERE index_name = UPPER(:index_name)
ORDER BY partition_position;
~~~

Với global partitioned index, kiểm tra trạng thái từng index partition. Với nonpartitioned global index, xem USER_INDEXES.STATUS.

## 9. Bảo trì partition

Partitioning đem lại lợi ích quản trị vì có thể thực hiện một số thao tác trên một phần dữ liệu thay vì toàn bảng. Cú pháp và khả năng hỗ trợ khác nhau theo phương pháp partition và release.

### 9.1. Truncate một partition

~~~sql
ALTER TABLE sales_range
TRUNCATE PARTITION p_before_2024;
~~~

Lệnh này xóa dữ liệu trong partition nhưng giữ cấu trúc partition. Đây là thao tác phá hủy dữ liệu; chỉ chạy khi partition đã hết hạn lưu trữ và có phê duyệt.

### 9.2. Drop một partition

~~~sql
ALTER TABLE sales_range
DROP PARTITION p_before_2024;
~~~

Lệnh loại bỏ partition và dữ liệu bên trong. Nếu partition chứa dữ liệu cần lưu trữ, archive hoặc exchange trước khi drop.

Global index có thể cần được duy trì trong partition maintenance. Tùy thao tác và release, có thể dùng mệnh đề UPDATE INDEXES:

~~~sql
ALTER TABLE sales_range
DROP PARTITION p_before_2024
UPDATE INDEXES;
~~~

Hãy kiểm tra syntax và trạng thái index theo Oracle release. UPDATE INDEXES có thể tăng chi phí thao tác; đổi lại, index liên quan được duy trì theo yêu cầu của lệnh.

### 9.3. Split partition

Dùng split khi một partition hiện tại cần chia thành các miền nhỏ hơn, ví dụ partition tương lai đang quá rộng:

~~~sql
ALTER TABLE sales_range
SPLIT PARTITION p_future
AT (DATE '2025-01-01')
INTO (
    PARTITION p_2024_h2,
    PARTITION p_future
);
~~~

Trong ví dụ, P_FUTURE trước đó chứa mọi giá trị từ 2024-07-01 trở đi. Sau split:

- P_2024_H2 nhận giá trị từ 2024-07-01 đến trước 2025-01-01.
- P_FUTURE nhận giá trị từ 2025-01-01 trở đi.

### 9.4. Add partition cho range/list

Với range table không có partition MAXVALUE, có thể thêm partition ở cuối:

~~~sql
ALTER TABLE sales_range_no_max
ADD PARTITION p_2025_q1
VALUES LESS THAN (DATE '2025-04-01');
~~~

Nếu bảng đã có partition MAXVALUE, không thể thêm partition mới sau MAXVALUE bằng cách ADD thông thường; cần split partition chứa miền đó.

List table có thể thêm partition cho một tập giá trị mới khi các giá trị đó chưa thuộc partition khác và cấu trúc table cho phép. Nếu có DEFAULT partition đang nhận các giá trị đó, cần split/reorganize DEFAULT theo cú pháp phù hợp.

### 9.5. Interval partition tự sinh

Với interval table, partition mới được Oracle tạo khi dữ liệu cần một khoảng interval chưa có. Không cần tạo trước partition cho từng tháng. Tuy nhiên vẫn phải quản lý:

- Số lượng partition đã phát sinh.
- Statistics của partition mới.
- Index partition tương ứng.
- Retention và archive.
- Dữ liệu cũ hơn transition point.

Không giả định tên partition tự sinh ổn định qua các môi trường. Hãy dùng metadata hoặc PARTITION FOR để xác định partition theo key.

### 9.6. Exchange partition

EXCHANGE PARTITION hoán đổi segment dữ liệu của một partition với một bảng staging tương thích về cấu trúc. Đây là kỹ thuật hữu ích cho bulk load hoặc archive với thời gian thao tác metadata ngắn so với INSERT hàng loạt.

Trước khi exchange, cần bảo đảm:

- Cấu trúc cột, kiểu dữ liệu và thuộc tính tương thích.
- Dữ liệu staging nằm đúng miền partition.
- Constraint validation được quyết định rõ (WITH VALIDATION/WITHOUT VALIDATION theo use case).
- Index và dependent object được xử lý theo kế hoạch.

Exchange partition là thao tác nâng cao; không dùng WITHOUT VALIDATION nếu chưa có cơ chế xác minh mọi hàng staging thuộc đúng partition.

## 10. Row movement khi cập nhật partition key

Nếu UPDATE thay đổi partition key khiến hàng phải chuyển sang partition khác, Oracle cần row movement được bật:

~~~sql
ALTER TABLE sales_range ENABLE ROW MOVEMENT;
~~~

Sau đó mới thực hiện UPDATE làm hàng chuyển partition:

~~~sql
UPDATE sales_range
SET sale_date = DATE '2024-08-01'
WHERE sale_id = 2;
~~~

Nếu row movement chưa được bật, UPDATE thay đổi partition key có thể báo ORA-14402: updating partition key column would cause a partition change. Bật row movement cho phép Oracle di chuyển hàng; nó không phải thao tác miễn phí và có thể ảnh hưởng ROWID. Ứng dụng không nên coi ROWID là định danh bền vững qua thao tác này.

## 11. Metadata để theo dõi partition

### 11.1. Partition của bảng hiện tại

~~~sql
SELECT
    table_name,
    partition_name,
    partition_position,
    tablespace_name,
    num_rows,
    last_analyzed
FROM user_tab_partitions
WHERE table_name = 'SALES_RANGE'
ORDER BY partition_position;
~~~

NUM_ROWS và LAST_ANALYZED đến từ statistics, có thể NULL hoặc cũ nếu chưa gather statistics. Không dùng NUM_ROWS như số đếm chính xác tại mọi thời điểm.

### 11.2. Thông tin partitioning của bảng

~~~sql
SELECT
    table_name,
    partitioning_type,
    subpartitioning_type,
    partition_count,
    interval
FROM user_part_tables
WHERE table_name IN (
    'SALES_RANGE',
    'CUSTOMERS_BY_REGION',
    'CUSTOMER_EVENTS_HASH',
    'SALES_INTERVAL'
)
ORDER BY table_name;
~~~

### 11.3. Partition key

~~~sql
SELECT
    name,
    object_type,
    column_name,
    column_position
FROM user_part_key_columns
WHERE name = UPPER(:table_name)
ORDER BY column_position;
~~~

View USER_PART_KEY_COLUMNS cho biết cột nào tham gia partition key. Với composite partitioning, dùng thêm USER_SUBPART_KEY_COLUMNS và USER_TAB_SUBPARTITIONS.

### 11.4. Toàn schema hoặc toàn database

Các view tương ứng:

| Phạm vi | Table partition | Partition key | Index partition |
| --- | --- | --- | --- |
| Schema hiện tại | USER_TAB_PARTITIONS | USER_PART_KEY_COLUMNS | USER_IND_PARTITIONS |
| Object có thể truy cập | ALL_TAB_PARTITIONS | ALL_PART_KEY_COLUMNS | ALL_IND_PARTITIONS |
| Toàn database | DBA_TAB_PARTITIONS | DBA_PART_KEY_COLUMNS | DBA_IND_PARTITIONS |

Chọn view theo quyền cần thiết. Không cấp quyền DBA catalog rộng chỉ để ứng dụng đọc metadata của bảng thuộc schema mình.

## 12. Statistics và hiệu năng

Optimizer cần statistics để ước lượng cardinality và chọn partition access path phù hợp. Sau bulk load hoặc partition maintenance, cần đánh giá statistics của table, partition và index.

Ví dụ gather statistics cho bảng:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'SALES_RANGE',
        granularity => 'AUTO'
    );
END;
/
~~~

GRANULARITY => 'AUTO' để Oracle chọn mức statistics phù hợp theo cấu trúc partition. Chính sách thực tế còn phụ thuộc incremental statistics, partition exchange, global statistics và phiên bản. Không gather statistics toàn bảng liên tục sau mỗi batch nhỏ nếu chưa đo tác động.

Các yếu tố hiệu năng cần quan sát:

- Partition pruning có thực sự xảy ra không.
- Số partition được truy cập.
- Local/global index access.
- Statistics có đủ mới không.
- Skew giữa các partition.
- Parallel execution và partition-wise join.
- Chi phí quản lý nhiều partition và index partition.

## 13. Partition-wise join

Nếu hai bảng partition tương thích theo join key, Oracle có thể thực hiện partition-wise join: mỗi partition của bảng này được join với partition tương ứng của bảng kia. Điều này có thể giảm trao đổi dữ liệu giữa các process và tăng khả năng song song.

Ví dụ hai bảng fact/dimension hoặc hai bảng giao dịch đều partition theo cùng một key. Tuy nhiên, partition-wise join phụ thuộc cách partition, join predicate, optimizer plan và cấu hình parallel. Chỉ có cùng số partition không đủ bảo đảm Oracle dùng partition-wise join.

Hãy kiểm tra execution plan thay vì giả định kỹ thuật này tự động được áp dụng.

## 14. Chọn partition key và thiết kế vận hành

Trước khi tạo partition, trả lời các câu hỏi:

1. Truy vấn thường lọc theo cột nào?
2. Dữ liệu có miền thời gian hoặc nhóm giá trị rõ ràng không?
3. Có cần xóa/archive dữ liệu cũ theo một đơn vị quản trị không?
4. Giá trị key có skew lớn không?
5. Có unique constraint nào phải duy trì trên toàn bảng không?
6. Index nào nên local, index nào cần global?
7. Batch load có biết trước partition đích không?
8. Partition mới sẽ được tạo thủ công hay tự động?
9. Có cần row movement khi cập nhật partition key không?
10. Ai theo dõi số lượng partition, statistics và trạng thái index?

### 14.1. Những lựa chọn thường gặp

| Yêu cầu | Lựa chọn khởi đầu |
| --- | --- |
| Lọc và archive theo ngày/tháng | RANGE hoặc INTERVAL |
| Mỗi mã khu vực/loại dữ liệu có nhóm riêng | LIST |
| Chia tải theo customer/account ID | HASH |
| Theo tháng nhưng muốn tự sinh partition | INTERVAL |
| Theo tháng và phân phối theo customer trong từng tháng | INTERVAL-RANGE/HASH composite tùy release và nhu cầu |

### 14.2. Khi không nên partition

Không phải mọi bảng đều cần partition. Bảng nhỏ, ít truy vấn theo partition key, không có nhu cầu quản trị dữ liệu theo miền hoặc có chi phí index/maintenance lớn hơn lợi ích có thể không cần partition.

Partitioning cũng không thay thế index. Nếu truy vấn tìm một hàng bằng một khóa không liên quan partition key, Oracle vẫn có thể cần index phù hợp hoặc phải kiểm tra nhiều partition.

## 15. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| ORA-14400 khi INSERT | Giá trị partition key không khớp partition nào | Thêm/split partition hoặc điều chỉnh transition point |
| Hàng ngày đầu tháng vào partition không mong muốn | Nhầm VALUES LESS THAN là biên bao gồm | Nhớ rằng upper bound là exclusive |
| Range table thiếu miền dữ liệu tương lai | Không có partition tương ứng hoặc MAXVALUE | Tạo partition trước load hoặc split partition cuối |
| List INSERT lỗi với mã mới | Giá trị không được liệt kê và không có DEFAULT | Thêm partition hoặc dùng DEFAULT có kiểm soát |
| DEFAULT partition tăng quá lớn | Nhiều mã mới tích tụ | Theo dõi giá trị mới và split/reorganize khi cần |
| Hash không giúp truy vấn theo ngày | Hash key là customer/account, không phải date | Chọn key theo predicate; cân nhắc composite range-hash |
| Hash partition lệch dữ liệu | Key bị skew hoặc một giá trị chiếm phần lớn | Đo phân phối, xem lại key và workload |
| Interval không tự tạo partition cho dữ liệu cũ | Giá trị nằm dưới transition point | Khai báo range partition bao phủ dữ liệu cũ |
| Interval DDL không hợp lệ | Key/interval expression không được hỗ trợ hoặc dùng MAXVALUE | Kiểm tra kiểu key, interval và cú pháp đúng release |
| Query vẫn đọc nhiều partition | Predicate không lọc partition key hoặc biểu thức cản pruning | Viết predicate trực tiếp trên key và kiểm tra plan |
| Global index unusable sau maintenance | Index không được duy trì theo thao tác partition | Kiểm tra trạng thái và dùng UPDATE INDEXES khi phù hợp |
| Unique local index không tạo được | Unique key không chứa partition key | Dùng global unique index hoặc thiết kế lại khóa |
| UPDATE partition key báo ORA-14402 | Row movement chưa bật | Bật ENABLE ROW MOVEMENT nếu nghiệp vụ cho phép |
| Số hàng trong partition view không chính xác | Statistics cũ hoặc chưa gather | Gather/kiểm tra statistics; dùng COUNT để đối chiếu chính xác |

## 16. Bài tập thực hành

Thực hiện trong schema lab riêng. Có thể tạo bốn bảng từ các ví dụ ở mục 2–5.

### Bài 1 — Range boundary

Chèn các ngày ngay trước, đúng bằng và ngay sau từng boundary. Dự đoán partition nhận hàng. Giải thích vì sao ngày đúng bằng 2024-07-01 không vào partition kết thúc ở ngày đó.

### Bài 2 — Range pruning

Chạy truy vấn chỉ lấy nửa đầu năm. Dùng EXPLAIN PLAN và DBMS_XPLAN.DISPLAY để xem PSTART/PSTOP. Sau đó bỏ điều kiện ngày và so sánh số partition được truy cập.

### Bài 3 — List DEFAULT

Chèn mã khu vực đã khai báo, mã mới và NULL. Quan sát partition nhận dữ liệu. Sau đó split DEFAULT để tạo partition chuyên biệt cho mã mới.

### Bài 4 — Hash distribution

Chèn nhiều customer ID khác nhau vào bảng hash tám partition. Xem USER_TAB_PARTITIONS và statistics để quan sát phân phối. Thử query theo một customer ID và query chỉ theo thời gian; so sánh pruning.

### Bài 5 — Interval auto-create

Chèn dữ liệu thuộc nhiều tháng sau transition point. Xem danh sách partition trước và sau INSERT. Dùng PARTITION FOR để truy cập partition theo ngày mà không phụ thuộc tên hệ thống.

### Bài 6 — Local và global index

Tạo local index trên customer ID và global index trên sale ID. Xem USER_INDEXES và USER_IND_PARTITIONS. Thảo luận index nào phù hợp với truy vấn theo partition key và truy vấn theo khóa toàn bảng.

### Bài 7 — Row movement

Thử UPDATE thay đổi SALE_DATE khiến hàng chuyển partition khi row movement đang tắt. Sau đó bật row movement và chạy lại. Ghi nhận tác động tới ROWID và index.

### Bài 8 — Lập kế hoạch retention

Thiết kế bảng giao dịch lưu 36 tháng. Chọn RANGE hay INTERVAL, xác định interval, transition point, local/global index và cách archive/drop partition cũ. Nêu cách kiểm soát dữ liệu chưa hết hạn.

## 17. Dọn dữ liệu lab

Chỉ chạy trong schema lab do bạn tạo, sau khi hoàn thành bài tập:

~~~sql
DROP TABLE sales_range PURGE;
DROP TABLE customers_by_region PURGE;
DROP TABLE customer_events_hash PURGE;
DROP TABLE sales_interval PURGE;
DROP TABLE account_activity_hash PURGE;
~~~

Nếu bạn tạo thêm bảng sales_range_no_max hoặc các bảng lab khác, chỉ drop đúng các bảng thuộc schema thực hành của mình. PURGE bỏ qua recycle bin; không dùng trên bảng nghiệp vụ hoặc dữ liệu cần khôi phục.

## Tổng kết

RANGE chia miền key thành các khoảng liên tiếp với biên trên loại trừ; LIST chia theo tập giá trị được khai báo và có thể có DEFAULT; HASH dùng hàm băm để phân phối hàng; INTERVAL mở rộng RANGE và tự tạo partition theo bước khi dữ liệu vượt transition point. Chọn phương pháp theo predicate truy vấn, phân phối dữ liệu và quy trình quản trị vòng đời.

Partitioning phát huy tác dụng khi optimizer prune được partition cần đọc và khi đội vận hành tận dụng được maintenance theo partition. Hãy kiểm tra execution plan, statistics, local/global index, uniqueness và row movement. Với interval, xác định đúng transition point, kiểu partition key và interval expression. Đừng tạo partition chỉ để tăng số lượng; một thiết kế tốt phải giúp truy vấn và vận hành đơn giản hơn trong workload thực tế.

## Tài liệu Oracle tham khảo

- [Oracle Database VLDB and Partitioning Guide — Partitioning Concepts (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/vldbg/partition-intro.html) — khái niệm và lợi ích partitioning.
- [Oracle Database VLDB and Partitioning Guide — Range and Interval Partitioning (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/vldbg/partition-create-tables-indexes.html) — tạo range/interval partition.
- [Oracle Database VLDB and Partitioning Guide — List Partitioning (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/vldbg/partition-create-tables-indexes.html) — list partitioning và DEFAULT.
- [Oracle Database VLDB and Partitioning Guide — Hash Partitioning (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/vldbg/partition-create-tables-indexes.html) — hash partitioning.
- [Oracle Database VLDB and Partitioning Guide — Partition Maintenance Operations (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/vldbg/maintenance-partition-tables-indexes.html) — split, merge, drop, truncate và exchange.
- [Oracle Database Reference — USER_TAB_PARTITIONS (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/USER_TAB_PARTITIONS.html) — metadata partition của schema hiện tại.
- [Oracle Database SQL Language Reference — CREATE TABLE (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-TABLE.html) — cú pháp partitioning khi tạo bảng.

Khi triển khai trên Oracle release khác 19c, hãy đối chiếu VLDB and Partitioning Guide và SQL Language Reference đúng phiên bản, đặc biệt giới hạn partition key, interval expression, index maintenance và quyền sử dụng tính năng Partitioning.
