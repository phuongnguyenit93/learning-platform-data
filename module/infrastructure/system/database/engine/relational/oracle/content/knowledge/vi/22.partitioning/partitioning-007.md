# ADD, DROP, TRUNCATE, SPLIT, MERGE và MOVE PARTITION

> **Chủ đề:** Database Engine Relational Oracle  
> **Chương:** Phân vùng  
> **Mục tiêu:** Hiểu và sử dụng các thao tác bảo trì partition trong Oracle Database: ADD, DROP, TRUNCATE, SPLIT, MERGE và MOVE PARTITION. Biết điều kiện áp dụng theo kiểu partitioning, ảnh hưởng đến dữ liệu và local/global index, cách giảm thời gian bảo trì, kiểm tra trạng thái sau DDL và lập kế hoạch triển khai an toàn.

## 1. Partition maintenance là gì?

Partitioning chia một bảng lớn thành nhiều phần logic gọi là partition. Ứng dụng vẫn truy vấn bảng bằng tên chung, còn Oracle có thể chỉ đọc những partition liên quan nhờ partition pruning. Mỗi partition thường có segment và thuộc tính lưu trữ riêng.

Ví dụ bảng giao dịch được partition theo tháng:

~~~sql
CREATE TABLE sales (
    sale_id NUMBER NOT NULL,
    sale_date DATE NOT NULL,
    customer_id NUMBER NOT NULL,
    amount NUMBER(12,2) NOT NULL
)
PARTITION BY RANGE (sale_date) (
    PARTITION p_2026_01 VALUES LESS THAN (DATE '2026-02-01'),
    PARTITION p_2026_02 VALUES LESS THAN (DATE '2026-03-01'),
    PARTITION p_2026_03 VALUES LESS THAN (DATE '2026-04-01')
);
~~~

Thay vì một segment duy nhất cho toàn bộ dữ liệu, bảng có các partition theo khoảng ngày. Khi cần xử lý dữ liệu cũ, chuẩn bị tháng mới hoặc chuyển dữ liệu sang tablespace khác, DBA có thể thao tác trên một partition.

Các thao tác trong bài:

| Thao tác | Tác dụng chính | Dữ liệu trong partition |
|---|---|---|
| ADD PARTITION | Thêm partition mới | Partition mới ban đầu rỗng |
| DROP PARTITION | Loại bỏ partition khỏi bảng | Dữ liệu partition bị loại bỏ |
| TRUNCATE PARTITION | Xóa toàn bộ hàng trong một partition | Partition vẫn tồn tại nhưng rỗng |
| SPLIT PARTITION | Chia một partition thành hai hoặc nhiều phần theo cú pháp hỗ trợ | Hàng được phân phối vào partition mới |
| MERGE PARTITIONS | Gộp các partition tương thích thành một partition | Hàng được giữ trong partition kết quả |
| MOVE PARTITION | Di chuyển segment partition hoặc thay đổi thuộc tính lưu trữ | Hàng được giữ, segment được xây lại/chuyển vị trí |

Đây là DDL bảo trì cấu trúc. Không nhầm MERGE PARTITIONS với câu lệnh DML MERGE dùng để kết hợp INSERT và UPDATE.

## 2. Xác định kiểu partitioning trước khi thao tác

Cú pháp và thao tác được hỗ trợ phụ thuộc cách bảng được partition.

### 2.1. Range partitioning

Range partitioning chia dữ liệu theo các khoảng giá trị có thứ tự. Mỗi partition khai báo giới hạn trên bằng VALUES LESS THAN.

~~~sql
CREATE TABLE sales_range (
    sale_id NUMBER,
    sale_date DATE,
    amount NUMBER(12,2)
)
PARTITION BY RANGE (sale_date) (
    PARTITION p_before_2026 VALUES LESS THAN (DATE '2026-01-01'),
    PARTITION p_2026_h1 VALUES LESS THAN (DATE '2026-07-01'),
    PARTITION p_future VALUES LESS THAN (MAXVALUE)
);
~~~

Một partition range chứa các giá trị từ cận dưới (exclusive của partition trước) đến cận trên (exclusive). Giá trị đúng bằng giới hạn trên sẽ thuộc partition tiếp theo.

Nếu đã có partition MAXVALUE, không thể thêm một range partition có bound lớn hơn nó. Thường cần SPLIT partition MAXVALUE để tạo khoảng mới và giữ lại phần tương lai.

### 2.2. List partitioning

List partitioning chia dữ liệu theo các giá trị rời rạc:

~~~sql
CREATE TABLE customers_by_region (
    customer_id NUMBER,
    region_code VARCHAR2(20 CHAR),
    customer_name VARCHAR2(100)
)
PARTITION BY LIST (region_code) (
    PARTITION p_north VALUES ('NORTH'),
    PARTITION p_south VALUES ('SOUTH'),
    PARTITION p_other VALUES (DEFAULT)
);
~~~

Khi thêm vùng mới, cần kiểm tra giá trị đó đã thuộc partition nào, đặc biệt nếu có DEFAULT partition. Việc chuyển các giá trị đã nằm trong DEFAULT sang partition riêng thường cần thao tác tách/di chuyển phù hợp với cú pháp và release Oracle.

### 2.3. Hash partitioning

Hash partitioning phân phối hàng theo hash của partition key:

~~~sql
CREATE TABLE customer_events (
    event_id NUMBER,
    customer_id NUMBER NOT NULL,
    event_time DATE,
    payload VARCHAR2(200)
)
PARTITION BY HASH (customer_id)
PARTITIONS 4;
~~~

Hash partitioning thường dùng để phân phối đều dữ liệu và I/O, không tạo ranh giới thời gian/nghiệp vụ như range/list. Có thể thêm hoặc drop hash partition theo cú pháp Oracle hỗ trợ; Oracle có thể phải phân phối lại hàng giữa các partition. Hãy xem xét thời gian và chi phí thao tác thay vì giả định chỉ tạo metadata.

### 2.4. Composite partitioning

Bảng có thể partition hai cấp, ví dụ RANGE-HASH:

~~~sql
CREATE TABLE sales_composite (
    sale_id NUMBER,
    sale_date DATE,
    customer_id NUMBER,
    amount NUMBER(12,2)
)
PARTITION BY RANGE (sale_date)
SUBPARTITION BY HASH (customer_id)
SUBPARTITIONS 4 (
    PARTITION p_2026_01 VALUES LESS THAN (DATE '2026-02-01'),
    PARTITION p_2026_02 VALUES LESS THAN (DATE '2026-03-01')
);
~~~

Thao tác ở cấp partition có thể ảnh hưởng nhiều subpartition. Cần kiểm tra cả local index partition và subpartition, cũng như giới hạn DDL cho đúng loại composite partitioning.

### 2.5. Kiểm tra metadata partitioning

Trong schema sở hữu bảng:

~~~sql
SELECT table_name,
       partitioning_type,
       subpartitioning_type,
       partition_count,
       def_tablespace_name
FROM user_part_tables
WHERE table_name = 'SALES';
~~~

Liệt kê partition:

~~~sql
SELECT table_name,
       partition_name,
       partition_position,
       tablespace_name,
       num_rows,
       last_analyzed
FROM user_tab_partitions
WHERE table_name = 'SALES'
ORDER BY partition_position;
~~~

Với schema khác, dùng DBA_PART_TABLES và DBA_TAB_PARTITIONS nếu có quyền. NUM_ROWS và LAST_ANALYZED là statistics, không phải số hàng chính xác theo thời gian thực.

## 3. Chuẩn bị trước khi chạy partition DDL

Partition maintenance có thể xóa dữ liệu hoặc thay đổi segment/index. Trước khi thực hiện:

1. Xác định đúng owner, table và partition name.
2. Xác nhận partition key, loại partitioning và boundary.
3. Kiểm tra số hàng, thời gian dữ liệu và quy tắc lưu trữ.
4. Kiểm tra local/global index và trạng thái từng index partition.
5. Xác định constraint, foreign key, trigger, materialized view và ứng dụng phụ thuộc.
6. Xem xét transaction đang chạy và cửa sổ bảo trì.
7. Xác nhận backup, recovery và retention phù hợp nếu thao tác loại bỏ dữ liệu.
8. Chạy thử DDL trên môi trường tương đương với phiên bản Oracle production.
9. Ghi lại metadata và số hàng trước thao tác để đối soát.
10. Chuẩn bị cách xử lý index UNUSABLE hoặc thao tác thất bại.

Các DDL partition thông thường có implicit commit trước và sau câu lệnh. Không thể dùng ROLLBACK để hoàn tác DROP, TRUNCATE, SPLIT, MERGE hoặc MOVE PARTITION như với DML chưa commit. Cần coi đây là thao tác quản trị có ảnh hưởng thực tế.

## 4. ADD PARTITION — thêm partition

ADD PARTITION tạo partition mới. Partition mới thường rỗng; việc thêm partition không tự chuyển dữ liệu hiện có vào đó, trừ các trường hợp cơ chế partitioning tự phân phối lại như một số thao tác hash.

### 4.1. Thêm range partition

Giả sử bảng SALES_RANGE có partition cuối P_2026_H1 với bound nhỏ hơn DATE '2026-07-01' và không có partition có bound cao hơn.

~~~sql
ALTER TABLE sales_range
ADD PARTITION p_2026_h2
VALUES LESS THAN (DATE '2027-01-01')
TABLESPACE sales_data;
~~~

Partition mới nhận các giá trị từ giới hạn trên của partition trước đến trước 2027-01-01.

Nếu partition cuối cùng đã có bound MAXVALUE, câu ADD PARTITION với bound hữu hạn lớn hơn sẽ không hợp lệ vì không thể đặt partition mới sau MAXVALUE. Dùng SPLIT PARTITION trên partition MAXVALUE để tạo ranh giới mong muốn.

### 4.2. Thêm list partition

~~~sql
ALTER TABLE customers_by_region
ADD PARTITION p_east
VALUES ('EAST')
TABLESPACE customer_data;
~~~

Giá trị EAST phải chưa được gán cho partition khác. Nếu có DEFAULT partition, kiểm tra cú pháp và quy trình chuyển giá trị khỏi DEFAULT theo Oracle release; không giả định chỉ ADD là tự chuyển những hàng cũ.

### 4.3. Thêm hash partition

Với bảng hash-partitioned, có thể thêm partition theo cú pháp phù hợp:

~~~sql
ALTER TABLE customer_events
ADD PARTITION p_hash_5
TABLESPACE event_data;
~~~

Oracle phân phối hàng theo hash partitioning. Thao tác thêm partition có thể yêu cầu tái phân phối dữ liệu hiện có và gây I/O đáng kể. Kiểm tra tài liệu release, execution time dự kiến và khả năng online/availability.

### 4.4. Interval partitioning

Với interval-partitioned table, Oracle có thể tự tạo partition khi INSERT giá trị nằm ngoài transition range. Vì vậy không phải lúc nào cũng cần ADD PARTITION thủ công cho mỗi tháng mới.

Ví dụ:

~~~sql
CREATE TABLE monthly_sales (
    sale_id NUMBER,
    sale_date DATE NOT NULL,
    amount NUMBER(12,2)
)
PARTITION BY RANGE (sale_date)
INTERVAL (NUMTOYMINTERVAL(1, 'MONTH')) (
    PARTITION p_before_2026 VALUES LESS THAN (DATE '2026-01-01')
);
~~~

Khi dữ liệu mới vượt transition point, Oracle tạo interval partition theo quy tắc interval. Vẫn cần theo dõi tên partition, tablespace mặc định, index và chính sách lưu trữ.

### 4.5. Khi nào dùng ADD?

- Chuẩn bị khoảng dữ liệu tương lai.
- Thêm nhóm giá trị mới trong list partition.
- Tăng số hash partition khi cần phân phối lại.
- Chuẩn bị partition cho batch nạp tiếp theo.

Sau ADD, kiểm tra partition metadata, tablespace và local index partition tương ứng. Nếu bảng có global index, xác nhận trạng thái và khả năng sử dụng.

## 5. DROP PARTITION — loại bỏ partition và dữ liệu

DROP PARTITION loại bỏ partition khỏi bảng. Dữ liệu trong partition bị loại bỏ cùng segment partition.

Ví dụ:

~~~sql
ALTER TABLE sales_range
DROP PARTITION p_2026_h1;
~~~

Thao tác phù hợp với dữ liệu đã hết thời hạn lưu trữ hoặc partition được tạo nhầm và đã có kế hoạch xử lý.

### 5.1. DROP khác DELETE

~~~sql
DELETE FROM sales_range
WHERE sale_date < DATE '2026-07-01';
~~~

DELETE là DML: Oracle tìm từng hàng phù hợp, tạo undo/redo, duy trì index, trigger và constraint; có thể rollback trước commit.

~~~sql
ALTER TABLE sales_range
DROP PARTITION p_old_data;
~~~

DROP PARTITION là DDL partition maintenance: loại bỏ partition segment và metadata liên quan; không tạo một undo record cho từng hàng theo cách DELETE thông thường. DDL có implicit commit, vì vậy không thể rollback bằng ROLLBACK.

Với lượng dữ liệu lớn, DROP PARTITION thường hiệu quả hơn DELETE toàn bộ hàng của một partition nếu ranh giới partition khớp chính xác yêu cầu nghiệp vụ. Tuy nhiên phải xử lý index, constraint và dependencies.

### 5.2. Không được xóa partition cuối cùng theo cách thông thường

Oracle không cho DROP partition nếu thao tác khiến partitioned table không còn partition hợp lệ. Nếu muốn xóa toàn bộ dữ liệu, cân nhắc TRUNCATE TABLE hoặc drop table theo đúng mục đích và quyền hạn.

### 5.3. DROP với global index

Local index được partition tương ứng với table partition. Khi drop table partition, local index partition tương ứng cũng được loại bỏ.

Global index có thể bị ảnh hưởng vì entry của nó tham chiếu dữ liệu ở nhiều table partition. Nếu không thực hiện bảo trì global index phù hợp, global index hoặc các partition của nó có thể bị đánh dấu UNUSABLE tùy operation và phiên bản.

Ví dụ cú pháp bảo trì index thường gặp:

~~~sql
ALTER TABLE sales_range
DROP PARTITION p_old_data
UPDATE INDEXES;
~~~

Các release cũ hoặc cú pháp cụ thể có thể dùng cách diễn đạt UPDATE GLOBAL INDEXES. Hãy kiểm tra SQL Language Reference đúng phiên bản và trạng thái index sau DDL. Không mặc định cú pháp hay hành vi giống nhau ở mọi release.

### 5.4. DROP partition có dữ liệu cần giữ lại

Nếu partition chứa dữ liệu vẫn cần lưu trữ, có thể cần export, backup, archive hoặc EXCHANGE PARTITION với bảng staging trước khi drop. Đừng DROP trước rồi mới tìm cách khôi phục.

Một chiến lược thường gặp là chuyển partition cũ sang tablespace lưu trữ hoặc exchange ra bảng riêng, kiểm tra kết quả, rồi mới drop theo retention policy. EXCHANGE PARTITION là thao tác riêng, cần kiểm tra constraint và index alignment.

## 6. TRUNCATE PARTITION — xóa hàng nhưng giữ partition

TRUNCATE PARTITION loại bỏ toàn bộ hàng trong một partition, nhưng giữ partition definition để có thể nạp dữ liệu mới vào cùng khoảng.

~~~sql
ALTER TABLE sales_range
TRUNCATE PARTITION p_2026_h1;
~~~

Dùng khi cần làm rỗng một partition để nạp lại dữ liệu, reset một batch/period hoặc xóa toàn bộ dữ liệu trong phạm vi partition.

### 6.1. DROP và TRUNCATE khác nhau

| Tiêu chí | DROP PARTITION | TRUNCATE PARTITION |
|---|---|---|
| Partition definition | Bị loại bỏ | Được giữ |
| Dữ liệu | Bị loại bỏ | Bị xóa |
| Segment | Partition segment bị loại bỏ | Segment được làm rỗng/tái khởi tạo theo cách Oracle quản lý |
| Dùng lại cùng partition | Cần ADD/SPLIT hoặc tái cấu trúc | Có thể nạp lại vào partition hiện có |
| Phù hợp | Loại bỏ hẳn khoảng dữ liệu | Làm sạch một khoảng nhưng giữ cấu trúc |

Cả hai là DDL, có implicit commit và không thể rollback như DELETE chưa commit.

### 6.2. TRUNCATE và index

Local index partition tương ứng được xử lý cùng partition table theo thao tác truncate. Global index cần được duy trì theo cú pháp/khả năng của release; nếu không, index có thể bị ảnh hưởng hoặc cần rebuild.

Ví dụ:

~~~sql
ALTER TABLE sales_range
TRUNCATE PARTITION p_2026_h1
UPDATE INDEXES;
~~~

Sau thao tác, kiểm tra USER_INDEXES và USER_IND_PARTITIONS để xác nhận index vẫn usable. Một số phiên bản Oracle hỗ trợ bảo trì global index không đồng bộ hoặc tối ưu hơn cho DROP/TRUNCATE; điều đó không loại bỏ yêu cầu kiểm tra trạng thái và khả năng truy vấn.

### 6.3. TRUNCATE không tương đương DELETE

TRUNCATE PARTITION không kích hoạt row-level DELETE trigger theo cách DELETE từng hàng; các semantics trigger và constraint cần được kiểm tra theo tài liệu Oracle. DDL cũng không cung cấp rollback row-by-row.

Nếu cần audit từng hàng bị xóa, cần ghi nhận dữ liệu trước thao tác hoặc dùng quy trình archive/audit riêng. Không dùng TRUNCATE thay DELETE khi nghiệp vụ phụ thuộc trigger xóa từng hàng.

### 6.4. Foreign key và các ràng buộc

Partition maintenance có thể bị hạn chế khi bảng được tham chiếu bởi foreign key hoặc có các constraint/dependency liên quan. Cần kiểm tra constraint, trạng thái ENABLED/VALIDATED và các quy tắc DDL tương ứng. Không vô hiệu hóa FK chỉ để DDL chạy nếu chưa có kế hoạch xác thực lại dữ liệu.

## 7. SPLIT PARTITION — chia một partition

SPLIT PARTITION chia một partition hiện có thành các partition nhỏ hơn theo ranh giới mới. Đây là thao tác hữu ích khi một partition tương lai quá rộng, cần tách một khoảng dữ liệu hoặc phân loại một vùng giá trị riêng.

Ví dụ bảng có partition P_FUTURE chứa mọi ngày trước MAXVALUE:

~~~sql
PARTITION p_future VALUES LESS THAN (MAXVALUE)
~~~

Muốn tách năm 2027 ra khỏi vùng tương lai:

~~~sql
ALTER TABLE sales_range
SPLIT PARTITION p_future
AT (DATE '2028-01-01')
INTO (
    PARTITION p_2027,
    PARTITION p_future
);
~~~

Partition kết quả đầu tiên nhận các hàng nằm dưới ranh giới split trong phạm vi cũ; partition thứ hai nhận phần còn lại. Tên và high bound phải được kiểm tra để bảo đảm không tạo khoảng sai.

### 7.1. Chia partition theo ranh giới range

Giả sử P_2026_H2 chứa các ngày từ 2026-07-01 đến trước 2027-01-01. Có thể chia thành hai partition:

~~~sql
ALTER TABLE sales_range
SPLIT PARTITION p_2026_h2
AT (DATE '2026-10-01')
INTO (
    PARTITION p_2026_q3,
    PARTITION p_2026_q4
);
~~~

Các hàng trước 2026-10-01 nằm trong P_2026_Q3; các hàng từ 2026-10-01 đến trước bound cũ nằm trong P_2026_Q4.

### 7.2. SPLIT không chỉ đổi tên metadata

Oracle phải phân phối hàng vào các partition kết quả và duy trì index. Nếu partition chứa nhiều dữ liệu, thao tác có thể tiêu thụ I/O, CPU, temporary space và redo. Thời gian phụ thuộc số hàng, storage, index, parallelism và tùy chọn online.

Không coi SPLIT trên partition lớn là thao tác tức thời.

### 7.3. SPLIT và index

Local index partition tương ứng cũng phải được chia để tiếp tục đồng bộ với table partition. Global index có thể cần maintenance hoặc rebuild theo tùy chọn DDL.

Ví dụ có thể chỉ định index maintenance trong cùng DDL:

~~~sql
ALTER TABLE sales_range
SPLIT PARTITION p_2026_h2
AT (DATE '2026-10-01')
INTO (
    PARTITION p_2026_q3,
    PARTITION p_2026_q4
)
UPDATE INDEXES;
~~~

Kiểm tra cú pháp UPDATE INDEXES và khả năng online theo Oracle release. Sau SPLIT, kiểm tra trạng thái table partition và index partition; không giả định tất cả index luôn usable.

### 7.4. SPLIT list partition và hash partition

Các dạng partitioning khác có cú pháp/khả năng SPLIT riêng. List partition có thể cần chỉ định tập giá trị phân phối vào partition kết quả. Hash partition thường được quản lý bằng ADD/DROP và cơ chế hash distribution hơn là dùng SPLIT range boundary.

Không áp dụng ví dụ RANGE AT(...) cho LIST/HASH. Đối chiếu partitioning type và cú pháp release trước khi chạy.

## 8. MERGE PARTITIONS — gộp partition

MERGE PARTITIONS gộp các partition tương thích, thường là các range partition liền kề, thành một partition. Dùng khi số partition quá nhiều, dữ liệu cần được gom lại hoặc không còn cần độ hạt mịn của các khoảng cũ.

Ví dụ:

~~~sql
ALTER TABLE sales_range
MERGE PARTITIONS p_2026_q3, p_2026_q4
INTO PARTITION p_2026_h2;
~~~

Partition kết quả có high bound tương ứng với bound cao nhất của các partition nguồn. Các hàng từ hai partition được giữ trong partition kết quả.

### 8.1. Điều kiện và ý nghĩa

- Các partition nguồn phải đáp ứng yêu cầu tương thích và thứ tự của partitioning method.
- Với range partitioning, thường gộp các partition liền kề.
- Tên partition kết quả phải không xung đột với tên hiện có.
- Bound của partition kết quả phải bao phủ chính xác phạm vi của các partition nguồn.
- Cần xem giới hạn cho list, composite và các loại partition khác theo release.

Không gộp các partition chỉ vì tên nằm cạnh nhau; xác nhận boundary và dữ liệu thực tế.

### 8.2. MERGE partition không phải SQL MERGE

~~~sql
MERGE INTO target_table t
USING source_table s
ON (t.id = s.id)
WHEN MATCHED THEN UPDATE SET t.value = s.value
WHEN NOT MATCHED THEN INSERT (id, value) VALUES (s.id, s.value);
~~~

Đây là DML MERGE để đồng bộ hàng.

~~~sql
ALTER TABLE sales_range
MERGE PARTITIONS p_2026_q3, p_2026_q4
INTO PARTITION p_2026_h2;
~~~

Đây là DDL MERGE PARTITIONS để thay đổi cấu trúc phân vùng. Hai lệnh có mục đích và transaction semantics khác nhau.

### 8.3. Index sau MERGE

Local index partitions được gộp tương ứng với table partitions. Global index cần được bảo trì hoặc có thể trở nên unusable nếu thao tác không thực hiện maintenance phù hợp.

Ví dụ:

~~~sql
ALTER TABLE sales_range
MERGE PARTITIONS p_2026_q3, p_2026_q4
INTO PARTITION p_2026_h2
UPDATE INDEXES;
~~~

Sau DDL, kiểm tra local/global index status, số partition và query plan.

## 9. MOVE PARTITION — chuyển segment partition

MOVE PARTITION di chuyển dữ liệu của một partition sang segment mới, thường để thay đổi tablespace, storage attribute hoặc tổ chức lại segment.

Ví dụ chuyển partition sang tablespace khác:

~~~sql
ALTER TABLE sales_range
MOVE PARTITION p_2026_h1
TABLESPACE sales_archive;
~~~

Partition vẫn thuộc bảng SALES_RANGE và giữ dữ liệu, nhưng segment được chuyển đến tablespace đích.

### 9.1. Khi nào dùng MOVE?

- Chuyển dữ liệu cũ sang tablespace chi phí thấp hơn.
- Di chuyển partition khỏi tablespace thiếu dung lượng.
- Thay đổi storage attribute hoặc compression.
- Tổ chức lại segment sau thời gian DML.
- Chuẩn bị cho chiến lược backup, tiered storage hoặc bảo trì.

MOVE khác DROP/TRUNCATE: dữ liệu được giữ lại. Tuy nhiên đây vẫn là DDL có thể cần đọc/ghi lượng dữ liệu lớn và tiêu thụ tài nguyên đáng kể.

### 9.2. MOVE có thể ảnh hưởng ROWID và index

MOVE xây dựng segment mới; ROWID vật lý của hàng có thể thay đổi. Local index partition và global index tham chiếu ROWID cần được xử lý theo quy tắc index maintenance của Oracle.

Nếu không yêu cầu index maintenance phù hợp, index có thể bị đánh dấu UNUSABLE. Ví dụ:

~~~sql
ALTER TABLE sales_range
MOVE PARTITION p_2026_h1
TABLESPACE sales_archive
UPDATE INDEXES;
~~~

Cú pháp và mức độ hỗ trợ UPDATE INDEXES, ONLINE hoặc các tùy chọn khác phụ thuộc Oracle release và loại index. Kiểm tra trạng thái index sau thao tác.

### 9.3. Online move

Một số release/edition và loại partition hỗ trợ MOVE PARTITION ONLINE:

~~~sql
ALTER TABLE sales_range
MOVE PARTITION p_2026_h1
TABLESPACE sales_archive
ONLINE
UPDATE INDEXES;
~~~

ONLINE có thể cho phép một số DML tiếp tục trong lúc move, nhưng không có nghĩa hoàn toàn không khóa hoặc không có giới hạn. Có thể vẫn có giai đoạn khóa ngắn, yêu cầu tài nguyên bổ sung, hạn chế datatype/index/partitioning và khác biệt theo phiên bản.

Trước khi dùng, kiểm tra SQL Language Reference, license/edition nếu liên quan, và thử trên schema tương đương. Không tự thêm ONLINE vào DDL nếu release không hỗ trợ.

### 9.4. Compression và storage attribute

MOVE có thể kết hợp thuộc tính lưu trữ hoặc compression được Oracle hỗ trợ:

~~~sql
ALTER TABLE sales_range
MOVE PARTITION p_2026_h1
TABLESPACE sales_archive
COMPRESS FOR QUERY HIGH
UPDATE INDEXES;
~~~

Tên compression option và khả năng áp dụng phụ thuộc edition, release và loại bảng. Compression có thể giảm storage và I/O đọc nhưng tăng CPU khi nạp/truy vấn hoặc làm thay đổi đặc tính DML. Đo workload trước khi áp dụng hàng loạt.

## 10. Local index và global index trong partition maintenance

Đây là phần phải kiểm tra sau hầu hết thao tác ADD, DROP, TRUNCATE, SPLIT, MERGE và MOVE.

### 10.1. Local index

Local index được partition tương ứng với table partition. Mỗi local index partition chỉ chứa entry của table partition tương ứng.

Ưu điểm:

- Quản lý vòng đời dễ hơn khi DROP/TRUNCATE partition.
- Bảo trì partition có thể thực hiện cục bộ.
- Phù hợp với dữ liệu có vòng đời theo partition.
- Partition pruning và index partition pruning có thể giảm phạm vi đọc.

Ví dụ:

~~~sql
CREATE INDEX ix_sales_date_local
ON sales_range(sale_date)
LOCAL;
~~~

Khi thêm table partition, Oracle tạo index partition tương ứng theo định nghĩa local index. Khi drop/truncate/split/merge/move, các local index partition được bảo trì theo thao tác tương ứng.

### 10.2. Global index

Global index có thể tham chiếu hàng trên nhiều table partition và không nhất thiết có ranh giới giống table partition.

Ví dụ global nonpartitioned index:

~~~sql
CREATE INDEX ix_sales_customer_global
ON sales_range(customer_id);
~~~

Global partitioned index:

~~~sql
CREATE INDEX ix_sales_customer_g
ON sales_range(customer_id)
GLOBAL PARTITION BY HASH(customer_id)
PARTITIONS 4;
~~~

Global index hữu ích khi truy vấn tìm theo key không chứa partition key hoặc cần index bao phủ toàn bảng. Nhưng partition maintenance trên table có thể làm global index phải cập nhật entry ở phạm vi rộng hơn.

### 10.3. Vì sao global index có thể UNUSABLE?

Khi một table partition bị loại bỏ, làm rỗng, split, merge hoặc move, ROWID/entry tương ứng trong global index có thể không còn hợp lệ nếu Oracle không thực hiện maintenance. Oracle có thể đánh dấu index hoặc index partition UNUSABLE để ngăn query sử dụng cấu trúc sai.

Có thể yêu cầu maintenance ngay trong DDL bằng UPDATE INDEXES nếu operation/release hỗ trợ. Nếu không, phải rebuild index hoặc index partition sau đó.

### 10.4. Kiểm tra index status

Index tổng quát:

~~~sql
SELECT index_name,
       index_type,
       uniqueness,
       status,
       partitioned
FROM user_indexes
WHERE table_name = 'SALES_RANGE'
ORDER BY index_name;
~~~

Index partition:

~~~sql
SELECT index_name,
       partition_name,
       status,
       tablespace_name
FROM user_ind_partitions
WHERE index_name IN (
    SELECT index_name
    FROM user_indexes
    WHERE table_name = 'SALES_RANGE'
)
ORDER BY index_name, partition_position;
~~~

Với index subpartitioned, kiểm tra USER_IND_SUBPARTITIONS. Với schema khác, dùng DBA views nếu được cấp quyền.

Trạng thái cần chú ý là USABLE/UNUSABLE. Không coi DDL hoàn tất là đủ; truy vấn production có thể lỗi hoặc không dùng được index nếu index partition bị unusable.

### 10.5. Rebuild index hoặc index partition

Nếu một index partition bị unusable, có thể rebuild theo cú pháp phù hợp:

~~~sql
ALTER INDEX ix_sales_date_local
REBUILD PARTITION p_2026_h1;
~~~

Với global nonpartitioned index:

~~~sql
ALTER INDEX ix_sales_customer_global
REBUILD;
~~~

Rebuild cần I/O, CPU, temporary space và có thể tạo redo tùy logging. Xác định thời gian, online support và ảnh hưởng DML trước khi chạy.

## 11. Statistics sau partition maintenance

Partition DDL có thể thay đổi số hàng, phân bố dữ liệu và cấu trúc index. Statistics cũ có thể không còn đại diện cho partition mới.

Có thể xem statistics partition:

~~~sql
SELECT table_name,
       partition_name,
       num_rows,
       blocks,
       last_analyzed,
       stale_stats
FROM user_tab_statistics
WHERE table_name = 'SALES_RANGE'
ORDER BY partition_name;
~~~

Thu thập statistics cho bảng và partition theo chính sách:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname          => USER,
        tabname          => 'SALES_RANGE',
        granularity      => 'AUTO',
        cascade          => TRUE,
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE
    );
END;
/
~~~

DBMS_STATS có nhiều tùy chọn incremental statistics và granularity cho bảng partitioned. Lựa chọn phụ thuộc số partition, query workload và quy trình DBA.

Không chạy gather statistics quá rộng sau mọi DDL nếu đã có chính sách incremental/automatic phù hợp. Cần xác nhận optimizer có statistics cần thiết cho partition mới hoặc partition bị thay đổi.

## 12. DDL partition và tính sẵn sàng

Partition maintenance có thể đọc/ghi nhiều block, lấy metadata/table lock và ảnh hưởng transaction đang chạy. Mức độ blocking phụ thuộc operation, release, ONLINE option, index và workload.

Trước khi triển khai production:

- Chọn maintenance window nếu thao tác offline hoặc có thể gây blocking.
- Kiểm tra session đang truy cập partition.
- Ước lượng dung lượng tablespace, TEMP và redo.
- Đảm bảo archive destination đủ dung lượng nếu redo lớn.
- Kiểm tra standby/Data Guard nếu database có replication.
- Đo thời gian trên dữ liệu có kích thước gần production.
- Theo dõi lock, I/O, redo generation và job cạnh tranh.
- Có kế hoạch rollback ở cấp vận hành: restore/reload/recreate, vì DDL đã commit không thể ROLLBACK thông thường.

Một số thao tác có tùy chọn ONLINE nhưng vẫn có giới hạn. ONLINE là đặc tính cần xác nhận theo đúng operation và release, không phải cam kết zero downtime.

## 13. Bảng so sánh các thao tác

| Thao tác | Giữ partition definition? | Giữ dữ liệu hiện có? | Tác động chính |
|---|---|---|---|
| ADD | Thêm definition | Có, dữ liệu cũ vẫn ở partition cũ (ngoại lệ phân phối hash theo operation) | Mở rộng phạm vi/partition count |
| DROP | Không | Không, partition bị loại | Loại bỏ hẳn segment và dữ liệu |
| TRUNCATE | Có | Không, hàng trong partition bị xóa | Làm rỗng partition để dùng lại |
| SPLIT | Thay một partition bằng nhiều partition | Có, hàng được phân phối lại | Tạo ranh giới chi tiết hơn |
| MERGE PARTITIONS | Thay nhiều partition bằng một partition | Có, hàng được gom lại | Giảm số partition |
| MOVE | Có | Có | Chuyển/rebuild segment, có thể đổi ROWID |

## 14. Ví dụ vòng đời partition theo tháng

Một chiến lược range partition theo tháng có thể vận hành như sau:

~~~text
Trước kỳ mới:
  P_2026_01 | P_2026_02 | P_2026_03 | P_FUTURE
       |
       +-- SPLIT P_FUTURE để chuẩn bị tháng mới
       |
Khi hết retention:
  DROP partition tháng cũ sau archive/backup
       |
Khi cần nạp lại một tháng:
  TRUNCATE partition tháng đó
       |
Khi cần thay đổi dung lượng:
  MOVE partition sang tablespace phù hợp
       |
Khi có quá nhiều partition nhỏ:
  MERGE các range partition liền kề nếu phù hợp
~~~

Một cách thiết kế khác là tạo sẵn các partition tương lai bằng ADD thay vì giữ một MAXVALUE partition. Cách chọn phụ thuộc quy trình nạp dữ liệu, interval partitioning, retention và khả năng triển khai.

### 14.1. Ví dụ chuẩn bị partition tương lai bằng SPLIT

Giả sử P_FUTURE có bound MAXVALUE:

~~~sql
ALTER TABLE sales_range
SPLIT PARTITION p_future
AT (DATE '2027-01-01')
INTO (
    PARTITION p_2026
        TABLESPACE sales_data,
    PARTITION p_future
        TABLESPACE sales_future
)
UPDATE INDEXES;
~~~

Sau đó kiểm tra boundary, tablespace và index status. Nếu partition cũ có dữ liệu thuộc năm 2026, Oracle phân phối chúng vào partition kết quả tương ứng.

### 14.2. Ví dụ hết retention

Sau khi dữ liệu đã được archive và phê duyệt xóa:

~~~sql
ALTER TABLE sales_range
DROP PARTITION p_2024_01
UPDATE INDEXES;
~~~

Đối soát số partition còn lại, index status và số hàng theo thống kê. Đừng dựa riêng vào NUM_ROWS nếu statistics stale.

## 15. Các lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| ADD range partition sau MAXVALUE | DDL không hợp lệ | SPLIT partition MAXVALUE |
| DROP partition mà chưa archive dữ liệu cần giữ | Mất dữ liệu trong phạm vi partition | Backup/exchange/archive và xác nhận retention trước |
| Nhầm DROP với TRUNCATE | Mất luôn partition definition khi chỉ muốn làm rỗng | Chọn đúng DDL |
| Dùng DELETE hàng loạt thay DROP partition | Tạo nhiều undo/redo và xử lý từng hàng | Dùng partition maintenance nếu predicate khớp trọn partition |
| Quên global index | Index có thể UNUSABLE hoặc cần rebuild | Dùng index maintenance phù hợp và kiểm tra status |
| Nghĩ local index giống global index | Dự đoán sai phạm vi maintenance | Xác định loại index trước |
| SPLIT/MERGE mà không kiểm tra boundary | Dữ liệu vào partition không như dự kiến | Đọc HIGH_VALUE và test trên lab |
| MOVE partition nhưng không xử lý index | Index partition có thể unusable | UPDATE INDEXES hoặc rebuild |
| Dùng ví dụ RANGE cho bảng LIST/HASH | DDL sai cú pháp hoặc không được hỗ trợ | Kiểm tra partitioning type |
| Nghĩ DDL có thể ROLLBACK | Không thể khôi phục bằng rollback transaction | Backup, staging và recovery plan |
| Không cập nhật statistics | Optimizer estimate sai sau thay đổi lớn | DBMS_STATS theo chính sách |
| Cho rằng ONLINE không có lock | Vẫn có thể có lock ngắn/giới hạn operation | Kiểm tra release và thử workload |
| Quên subpartition | Không đánh giá hết index/storage thay đổi | Kiểm tra composite partitioning metadata |

## 16. Checklist trước và sau partition maintenance

### Trước thao tác

- [ ] Xác nhận đúng schema, bảng và partition.
- [ ] Xác nhận RANGE/LIST/HASH/INTERVAL/COMPOSITE.
- [ ] Kiểm tra high bound, list values hoặc hash partition count.
- [ ] Xác nhận dữ liệu trong partition và chính sách retention.
- [ ] Xác nhận cần DROP hay TRUNCATE.
- [ ] Xác nhận SPLIT/MERGE boundary và partition name kết quả.
- [ ] Kiểm tra tablespace đích nếu MOVE.
- [ ] Kiểm kê local/global index và index partition status.
- [ ] Kiểm tra constraint, FK, trigger, MV và dependencies.
- [ ] Đánh giá transaction, lock, redo, TEMP và dung lượng.
- [ ] Xác nhận cú pháp/ONLINE/UPDATE INDEXES trên Oracle release thực tế.
- [ ] Có backup/archive và kế hoạch phục hồi phù hợp.

### Sau thao tác

- [ ] Kiểm tra USER_TAB_PARTITIONS và boundary/order.
- [ ] Kiểm tra số partition/subpartition.
- [ ] Kiểm tra tablespace và segment.
- [ ] Kiểm tra USER_INDEXES, USER_IND_PARTITIONS và trạng thái USABLE.
- [ ] Rebuild index partition nếu cần.
- [ ] Thu thập/điều chỉnh statistics theo chính sách.
- [ ] Chạy query đại diện và xem execution plan.
- [ ] Đối soát số hàng/dữ liệu với batch hoặc archive.
- [ ] Kiểm tra job, standby và ứng dụng phụ thuộc.
- [ ] Ghi audit DDL: ai chạy, thời gian, câu lệnh, kết quả.

## 17. Ghi nhớ cốt lõi

- ADD tạo partition mới; với range, không thể thêm partition vượt qua một partition MAXVALUE hiện có mà không tái cấu trúc boundary.
- DROP PARTITION loại bỏ cả partition definition và dữ liệu của nó; TRUNCATE PARTITION chỉ làm rỗng partition để dùng lại.
- SPLIT chia một partition thành các phần theo boundary; MERGE PARTITIONS gộp các partition tương thích, thường là range liền kề.
- MOVE PARTITION giữ dữ liệu nhưng chuyển/rebuild segment, thường dùng để đổi tablespace hoặc storage attribute.
- DDL partition có implicit commit; không thể dùng ROLLBACK thông thường để khôi phục dữ liệu đã DROP/TRUNCATE.
- Local index đi theo partition của bảng; global index có phạm vi rộng hơn và cần maintenance/rebuild thích hợp.
- UPDATE INDEXES và ONLINE có hỗ trợ, cú pháp và giới hạn phụ thuộc operation/Oracle release.
- Sau DDL phải kiểm tra partition metadata, index status, statistics và execution plan.
- Partition maintenance giúp quản lý dữ liệu lớn theo vòng đời, nhưng vẫn cần đánh giá lock, I/O, redo, TEMP, backup và dependencies.
- Không dùng một cú pháp RANGE cho LIST/HASH hoặc composite partitioning; xác định đúng loại partitioning trước khi triển khai.

### Tài liệu Oracle nên đối chiếu

- [Oracle Database VLDB and Partitioning Guide](https://docs.oracle.com/en/database/) — Partition maintenance operations, ADD/DROP/TRUNCATE/SPLIT/MERGE/MOVE.
- [Oracle Database SQL Language Reference](https://docs.oracle.com/en/database/) — ALTER TABLE partition clauses và ALTER INDEX.
- [Oracle Database Administrator's Guide](https://docs.oracle.com/en/database/) — Managing tablespaces, segments, indexes và partitioned tables.
- [Oracle Database Reference](https://docs.oracle.com/en/database/) — USER_PART_TABLES, USER_TAB_PARTITIONS, USER_INDEXES và USER_IND_PARTITIONS.
- [Oracle Database PL/SQL Packages and Types Reference](https://docs.oracle.com/en/database/) — DBMS_STATS và thống kê optimizer.

Cú pháp, online capability, global index maintenance và các giới hạn theo partitioning method thay đổi theo Oracle release. Trước khi chạy production, đối chiếu tài liệu đúng phiên bản, thử DDL trên schema tương đương và xác nhận index/partition status sau thao tác.

