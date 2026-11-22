# EXCHANGE PARTITION để nạp hoặc luân chuyển dữ liệu trong Oracle

Một bảng giao dịch được phân vùng theo tháng có thể nhận hàng triệu dòng mỗi kỳ. Nếu nạp dữ liệu bằng INSERT trực tiếp vào bảng lớn, hệ thống phải thực hiện DML trên các partition đích, duy trì index, tạo undo/redo và phối hợp với workload đang chạy. Trong một số quy trình ETL, cách hiệu quả hơn là nạp dữ liệu vào một bảng staging độc lập, kiểm tra dữ liệu, sau đó dùng **EXCHANGE PARTITION** để hoán đổi segment của bảng staging với một partition của bảng đích.

EXCHANGE PARTITION là thao tác metadata ở cấp partition: Oracle hoán đổi dữ liệu/segment giữa một partition của bảng partitioned và một bảng không partition tương thích. Nó không phải lệnh copy từng dòng và cũng không phải INSERT SELECT. Vì vậy, thao tác có thể rất nhanh so với việc chuyển hàng loạt dòng bằng DML, nhưng đòi hỏi cấu trúc hai bảng tương thích, dữ liệu staging phải thuộc đúng partition, index và constraint phải được xử lý đúng, và ứng dụng phải hiểu rằng đây là DDL có implicit commit.

Bài học thuộc nhóm **Phân vùng** của Database Engine Relational Oracle. Nội dung tập trung vào hai hướng sử dụng chính: exchange-in để đưa dữ liệu đã chuẩn bị vào partition, và exchange-out để lấy một partition ra thành bảng độc lập phục vụ archive, export hoặc xử lý ngoài. Bài cũng giải thích validation, local/global indexes, trạng thái UNUSABLE, thống kê, khóa DDL, giới hạn cấu trúc và một quy trình ETL có thể vận hành.

Sau bài này, bạn có thể:

- Giải thích EXCHANGE PARTITION là hoán đổi segment/metadata thay vì copy từng hàng.
- Thiết kế staging table tương thích với partitioned table.
- Phân biệt exchange-in và exchange-out, hiểu dữ liệu đi đâu sau khi hoán đổi.
- Dùng WITH VALIDATION và WITHOUT VALIDATION có trách nhiệm.
- Xử lý local index bằng INCLUDING INDEXES/EXCLUDING INDEXES.
- Bảo trì global index bằng tùy chọn phù hợp và kiểm tra trạng thái sau thao tác.
- Tổ chức quy trình nạp staging, kiểm tra dữ liệu, exchange, gather statistics và publish.
- Dùng exchange-out để tách dữ liệu lịch sử ra bảng archive.
- Nhận diện tác động của DDL implicit commit, khóa và concurrency.
- Kiểm tra partition/index metadata và execution plan sau khi exchange.
- Xây checklist triển khai an toàn cho ETL và partition lifecycle.

> **Phạm vi ví dụ:** Các câu lệnh minh họa theo Oracle Database 19c. Partitioning có điều kiện edition/giấy phép riêng; chỉ chạy ví dụ trên database mà quyền sử dụng partitioning đã được xác minh. Cú pháp và tùy chọn index maintenance có thể thay đổi theo release, loại bảng/index và loại partition. Hãy kiểm tra SQL Language Reference/VLDB and Partitioning Guide đúng phiên bản trước khi dùng trên production.

## 1. EXCHANGE PARTITION giải quyết vấn đề gì?

Giả sử bảng SALES được phân vùng theo tháng. Hàng tháng, hệ thống nhận một file lớn từ hệ thống nguồn. Quy trình có thể:

1. Nạp file vào bảng staging.
2. Kiểm tra datatype, giá trị bắt buộc, duplicate key và khoảng ngày.
3. Tạo index/constraint cần thiết trên staging.
4. Hoán đổi staging với partition tháng tương ứng.
5. Kiểm tra partition và index sau exchange.
6. Thu thập statistics và cho workload sử dụng dữ liệu mới.

~~~text
FILE / SOURCE SYSTEM
        |
        v
   STAGING TABLE
   - load rows
   - validate values
   - prepare indexes
        |
        | EXCHANGE PARTITION
        v
PARTITIONED TABLE
   SALES
   +-- P_2026_01
   +-- P_2026_02  <--- segment tu staging
   +-- P_2026_03
        |
        v
   APPLICATION / REPORTS
~~~

Nếu staging có dữ liệu tương thích và thao tác exchange thành công, Oracle đổi segment/metadata tương ứng. Dữ liệu trong staging trở thành dữ liệu của partition đích; dữ liệu cũ của partition được chuyển sang bảng staging.

### 1.1. Exchange không copy từng hàng

Điểm khác biệt cốt lõi:

| Phương pháp | Cách làm | Chi phí thường gặp |
| --- | --- | --- |
| INSERT INTO partitioned_table SELECT ... | Đọc và chèn từng hàng vào bảng đích | DML, undo/redo, index maintenance và logging theo cách load |
| DELETE/TRUNCATE rồi INSERT | Xóa dữ liệu cũ rồi nạp dữ liệu mới | DML/DDL và index maintenance |
| EXCHANGE PARTITION | Hoán đổi segment của partition với bảng tương thích | Chủ yếu là metadata/segment operation, kèm validation và index maintenance được chọn |

Exchange không làm cho toàn bộ quy trình ETL miễn phí. Việc nạp staging, build index, validation, cập nhật global index, gather statistics và khóa DDL vẫn tiêu tốn thời gian/tài nguyên. Lợi ích chính là bước đưa segment đã chuẩn bị vào partition tránh phải insert từng dòng qua partitioned table.

### 1.2. Exchange là hoán đổi hai phía

Tên “exchange” rất quan trọng: đây là swap, không phải “copy staging vào partition rồi giữ nguyên staging”.

Trước exchange:

~~~text
Partition P_2026_01: [old rows]
Staging table:      [new rows]
~~~

Sau exchange:

~~~text
Partition P_2026_01: [new rows]
Staging table:      [old rows]
~~~

Nếu partition ban đầu rỗng, staging sau exchange sẽ nhận segment rỗng của partition. Nếu partition có dữ liệu cũ, staging nhận dữ liệu cũ đó. Phải lập kế hoạch cho nội dung staging sau thao tác; không được giả định staging vẫn giữ bản dữ liệu vừa nạp.

## 2. Hai hướng sử dụng chính

### 2.1. Exchange-in: nạp dữ liệu vào partition

Exchange-in dùng khi staging đã chứa dữ liệu cho đúng một partition:

- Bảng partitioned có partition P2026_01.
- Bảng staging không partition có cùng cấu trúc tương thích.
- Staging chứa các dòng thuộc khoảng tháng 1/2026.
- Sau validation và exchange, các dòng staging trở thành nội dung P2026_01.

Đây là mẫu thường gặp trong data warehouse, fact table và ETL theo kỳ.

### 2.2. Exchange-out: lấy partition ra bảng độc lập

Exchange-out dùng khi muốn tách dữ liệu một partition:

- Archive partition cũ.
- Export dữ liệu theo kỳ.
- Xử lý lại dữ liệu ngoài bảng chính.
- Di chuyển dữ liệu sang một tablespace hoặc hệ thống khác qua quy trình riêng.

Nếu bảng nhận exchange ban đầu rỗng, sau thao tác nó chứa các hàng của partition. Partition trong bảng gốc nhận segment rỗng của bảng nhận. Nếu muốn loại bỏ hoàn toàn partition khỏi bảng, có thể dùng DROP PARTITION sau khi đã exchange-out, tùy retention và quy trình.

### 2.3. Exchange không tự tạo bản sao lưu

Vì dữ liệu được hoán đổi, staging sau exchange có thể giữ dữ liệu cũ, nhưng đây không phải chiến lược backup đầy đủ:

- Staging có thể bị truncate/drop trong bước cleanup.
- DDL exchange có implicit commit.
- Dữ liệu/metadata/index cần được bảo vệ bởi backup/recovery policy.
- Nếu exchange nhầm partition hoặc staging sai, hậu quả có thể ảnh hưởng báo cáo ngay.

Hãy coi exchange là một bước publish/relocation có kiểm soát, không phải backup.

## 3. Điều kiện tương thích giữa partition và staging table

EXCHANGE PARTITION yêu cầu bảng không partition dùng làm exchange table có cấu trúc tương thích với bảng partitioned. Đây là nơi cần chuẩn bị kỹ nhất.

### 3.1. Số lượng cột, thứ tự và datatype

Về nguyên tắc, các cột tương ứng phải tương thích về:

- Số lượng cột.
- Thứ tự cột.
- Datatype và thuộc tính datatype liên quan.
- Độ dài/precision/scale phù hợp.
- Cột hidden, virtual hoặc đặc tính đặc biệt nếu có.

Không nên chỉ so tên cột. Một bảng có cùng tên cột nhưng khác thứ tự hoặc datatype có thể không exchange được hoặc không đáp ứng yêu cầu dữ liệu.

### 3.2. Dùng DDL tường minh cho staging

Ví dụ bảng partitioned:

~~~sql
CREATE TABLE sales_part_lab (
    sale_id      NUMBER NOT NULL,
    sale_date    DATE NOT NULL,
    customer_id  NUMBER NOT NULL,
    amount       NUMBER(12,2) NOT NULL
)
PARTITION BY RANGE (sale_date) (
    PARTITION p_before_2026
        VALUES LESS THAN (DATE '2026-01-01'),
    PARTITION p2026_01
        VALUES LESS THAN (DATE '2026-02-01'),
    PARTITION p2026_02
        VALUES LESS THAN (DATE '2026-03-01'),
    PARTITION p_future
        VALUES LESS THAN (MAXVALUE)
);
~~~

Bảng staging có cùng danh sách cột theo đúng thứ tự:

~~~sql
CREATE TABLE sales_stage_lab (
    sale_id      NUMBER NOT NULL,
    sale_date    DATE NOT NULL,
    customer_id  NUMBER NOT NULL,
    amount       NUMBER(12,2) NOT NULL
);
~~~

Staging là bảng heap không partition. Khi thiết kế thật, cần đối chiếu thêm charset, collation, virtual/invisible columns, LOB, object types, identity columns, hidden columns, compression và các thuộc tính đặc biệt.

### 3.3. CTAS không tự sao chép mọi thuộc tính

Có thể dùng CREATE TABLE AS SELECT để tạo nhanh một bảng rỗng:

~~~sql
CREATE TABLE sales_stage_lab AS
SELECT sale_id, sale_date, customer_id, amount
FROM sales_part_lab
WHERE 1 = 0;
~~~

CTAS hữu ích để lấy datatype/column expressions trong một số trường hợp, nhưng không nên mặc định nó sao chép đầy đủ:

- Primary key, unique, foreign key và check constraints.
- Indexes.
- Defaults và một số thuộc tính cột.
- Triggers.
- Partition-specific metadata hoặc hidden-column semantics.
- Các thuộc tính vật lý cần cho exchange.

Sau CTAS, phải kiểm tra và bổ sung những gì cần thiết. Với quy trình chuẩn hóa, DDL tường minh hoặc cơ chế tạo exchange table được hỗ trợ bởi release có thể an toàn và dễ review hơn.

### 3.4. FOR EXCHANGE WITH TABLE

Một số release Oracle hỗ trợ cú pháp tạo exchange table dựa trên cấu trúc bảng partitioned:

~~~sql
CREATE TABLE sales_stage_lab
FOR EXCHANGE WITH TABLE sales_part_lab;
~~~

Cú pháp FOR EXCHANGE WITH TABLE được thiết kế để tạo bảng không partition có cấu trúc phù hợp cho exchange, bao gồm một số chi tiết mà CTAS thông thường không sao chép. Hãy kiểm tra hỗ trợ và cú pháp trong SQL Language Reference của release đang chạy. Không giả định mọi phiên bản cũ đều có cú pháp này.

### 3.5. Constraint phải được xem xét riêng

Exchange có thể liên quan đến:

- NOT NULL.
- CHECK constraint.
- Primary key/unique constraint.
- Foreign key.
- Constraint trạng thái ENABLE/DISABLE và VALIDATE/NOVALIDATE.
- Các constraint phụ thuộc vào cột hoặc dữ liệu ở bảng khác.

Không chỉ kiểm tra DDL bảng mà bỏ qua trạng thái constraint. Unique/primary key có thể ảnh hưởng đến khả năng bỏ validation hoặc yêu cầu index tương ứng. Foreign key và các tính năng như reference partitioning có thêm điều kiện riêng.

Trước khi exchange, so sánh USER_CONSTRAINTS/ALL_CONSTRAINTS và kiểm tra tài liệu đúng release cho cấu trúc cụ thể. Nếu staging có constraint khác bảng partitioned, đừng giả định Oracle tự chuyển tất cả semantics sang bên kia.

### 3.6. Index và cấu trúc đặc biệt

Nếu muốn exchange index cùng partition, các index tương ứng phải tương thích. Cần kiểm tra:

- Column list và thứ tự cột.
- Datatype/biểu thức function-based.
- Uniqueness.
- Local/global organization.
- Partitioning và trạng thái index.
- Compression, visibility và thuộc tính index liên quan.

LOB, domain index, IOT, nested table, virtual/hidden columns, reference partitioning và một số cấu trúc đặc biệt có thể có giới hạn riêng. Hãy xác nhận từng trường hợp thay vì áp dụng mẫu heap-table đơn giản.

## 4. Cú pháp EXCHANGE PARTITION

Mẫu khái quát:

~~~sql
ALTER TABLE partitioned_table
EXCHANGE PARTITION partition_name
WITH TABLE staging_table
[INCLUDING INDEXES | EXCLUDING INDEXES]
[WITH VALIDATION | WITHOUT VALIDATION]
[UPDATE GLOBAL INDEXES];
~~~

Tên tùy chọn và hỗ trợ có thể khác theo release/loại bảng; kiểm tra SQL Language Reference của phiên bản đích.

### 4.1. EXCHANGE PARTITION

Chỉ định partition trong bảng partitioned:

~~~sql
ALTER TABLE sales_part_lab
EXCHANGE PARTITION p2026_01
WITH TABLE sales_stage_lab;
~~~

Oracle hoán đổi segment/dữ liệu của P2026_01 với bảng SALES_STAGE_LAB nếu các điều kiện cấu trúc và constraint phù hợp.

### 4.2. INCLUDING INDEXES

INCLUDING INDEXES yêu cầu trao đổi các index tương ứng cùng với dữ liệu partition. Với local index, staging table cần có index tương ứng và cấu trúc phù hợp để exchange index segment với local index partition.

~~~sql
ALTER TABLE sales_part_lab
EXCHANGE PARTITION p2026_01
WITH TABLE sales_stage_lab
INCLUDING INDEXES
WITH VALIDATION;
~~~

Đừng hiểu INCLUDING INDEXES là “Oracle tự tạo mọi index còn thiếu”. Nó không thay thế việc thiết kế index tương ứng trên staging. Nếu index không tương thích hoặc thiếu, thao tác có thể thất bại.

### 4.3. EXCLUDING INDEXES

EXCLUDING INDEXES không trao đổi các index tương ứng. Tùy loại index và thao tác, local index partition liên quan có thể bị đánh dấu UNUSABLE và cần rebuild/recover. Nếu dùng EXCLUDING INDEXES, phải có bước kiểm tra trạng thái và kế hoạch xử lý index sau exchange.

Không chọn EXCLUDING INDEXES chỉ để làm DDL đơn giản hơn rồi quên bước index maintenance. Truy vấn/DML có thể bị ảnh hưởng khi index partition không usable.

### 4.4. WITH VALIDATION

WITH VALIDATION yêu cầu Oracle kiểm tra dữ liệu của exchange table phù hợp với ranh giới partition đích. Với partition tháng 1/2026 trong ví dụ, dữ liệu cần thuộc khoảng:

~~~text
2026-01-01 <= sale_date < 2026-02-01
~~~

Validation có thể phải đọc dữ liệu staging và làm thao tác lâu hơn. Đổi lại, nó giúp Oracle xác nhận dữ liệu thuộc partition được chỉ định.

### 4.5. WITHOUT VALIDATION

WITHOUT VALIDATION bỏ qua bước kiểm tra dữ liệu staging có thỏa partition bound hay không. Chỉ dùng khi một quy trình khác đã bảo đảm dữ liệu đúng range/list/hash semantics và có bằng chứng kiểm soát.

Nếu staging chứa một hàng tháng 3 nhưng được exchange vào partition tháng 1 mà không validation, dữ liệu có thể nằm trong partition sai so với partition key. Khi truy vấn dùng partition pruning, Oracle có thể bỏ qua partition chứa hàng đó và kết quả truy vấn bị thiếu hoặc sai.

Ví dụ:

~~~sql
-- Chi dung sau khi da validate staging bang quy trinh tin cay.
ALTER TABLE sales_part_lab
EXCHANGE PARTITION p2026_01
WITH TABLE sales_stage_lab
WITHOUT VALIDATION;
~~~

Không dùng WITHOUT VALIDATION chỉ để “làm nhanh hơn” khi chưa có kiểm tra dữ liệu độc lập. Với primary key/unique constraint hoặc cấu trúc đặc biệt, Oracle có thể vẫn cần kiểm tra hoặc áp dụng các điều kiện bổ sung; không giả định tùy chọn này bỏ qua mọi validation.

### 4.6. UPDATE GLOBAL INDEXES

Global index có phạm vi qua nhiều partition của bảng. Khi exchange một partition, các entry trong global index có thể cần được cập nhật để phản ánh ROWID/segment sau exchange. Tùy chọn UPDATE GLOBAL INDEXES yêu cầu duy trì global index trong thao tác theo khả năng của release.

~~~sql
ALTER TABLE sales_part_lab
EXCHANGE PARTITION p2026_01
WITH TABLE sales_stage_lab
INCLUDING INDEXES
WITH VALIDATION
UPDATE GLOBAL INDEXES;
~~~

Nếu bỏ qua global index maintenance trong tình huống cần cập nhật, global index có thể trở thành UNUSABLE hoặc cần được xử lý riêng theo quy tắc release/operation. Kiểm tra USER_INDEXES sau thao tác. Không suy luận trạng thái chỉ từ việc DDL trả về thành công.

## 5. Quy trình exchange-in: nạp staging vào partition

Quy trình khuyến nghị có các bước tách biệt:

1. Chuẩn bị partition đích và staging table.
2. Nạp dữ liệu vào staging.
3. Kiểm tra dữ liệu và duplicate keys.
4. Tạo/chuẩn bị index và constraint cần thiết.
5. Chốt staging để không còn DML đồng thời.
6. Exchange partition với validation phù hợp.
7. Kiểm tra index, constraint và số lượng hàng.
8. Thu thập statistics.
9. Đánh dấu batch hoàn tất và cho consumer sử dụng.

### 5.1. Tạo bảng partitioned

~~~sql
CREATE TABLE sales_part_lab (
    sale_id      NUMBER NOT NULL,
    sale_date    DATE NOT NULL,
    customer_id  NUMBER NOT NULL,
    amount       NUMBER(12,2) NOT NULL
)
PARTITION BY RANGE (sale_date) (
    PARTITION p_before_2026
        VALUES LESS THAN (DATE '2026-01-01'),
    PARTITION p2026_01
        VALUES LESS THAN (DATE '2026-02-01'),
    PARTITION p2026_02
        VALUES LESS THAN (DATE '2026-03-01'),
    PARTITION p_future
        VALUES LESS THAN (MAXVALUE)
);
~~~

P2026_01 nhận giá trị từ 2026-01-01 đến trước 2026-02-01 vì partition trước đó đã nhận giá trị nhỏ hơn 2026-01-01.

### 5.2. Tạo staging table tương thích

~~~sql
CREATE TABLE sales_stage_lab (
    sale_id      NUMBER NOT NULL,
    sale_date    DATE NOT NULL,
    customer_id  NUMBER NOT NULL,
    amount       NUMBER(12,2) NOT NULL
);
~~~

Trong lab này staging có đúng thứ tự cột và datatype tương ứng. Production cần kiểm tra đầy đủ thuộc tính bổ sung đã nêu ở Mục 3.

### 5.3. Nạp dữ liệu vào staging

~~~sql
INSERT INTO sales_stage_lab
    (sale_id, sale_date, customer_id, amount)
VALUES
    (1001, DATE '2026-01-03', 501, 120);

INSERT INTO sales_stage_lab
    (sale_id, sale_date, customer_id, amount)
VALUES
    (1002, DATE '2026-01-15', 502, 250);

INSERT INTO sales_stage_lab
    (sale_id, sale_date, customer_id, amount)
VALUES
    (1003, DATE '2026-01-28', 501, 80);

COMMIT;
~~~

COMMIT staging trước exchange giúp chốt batch và tránh DDL exchange làm implicit commit một transaction load còn mở. Trong ETL thật, batch ID và trạng thái load nên được ghi ở bảng điều phối riêng.

### 5.4. Kiểm tra range trước exchange

~~~sql
SELECT COUNT(*) AS rows_outside_partition
FROM sales_stage_lab
WHERE sale_date < DATE '2026-01-01'
   OR sale_date >= DATE '2026-02-01';
~~~

Kết quả phải là 0 cho partition P2026_01. Cũng cần kiểm tra:

~~~sql
SELECT COUNT(*) AS total_rows,
       COUNT(sale_id) AS nonnull_sale_id,
       COUNT(sale_date) AS nonnull_sale_date,
       MIN(sale_date) AS min_sale_date,
       MAX(sale_date) AS max_sale_date,
       SUM(amount) AS total_amount
FROM sales_stage_lab;
~~~

Kiểm tra duplicate sale_id trong staging:

~~~sql
SELECT sale_id, COUNT(*) AS duplicate_count
FROM sales_stage_lab
GROUP BY sale_id
HAVING COUNT(*) > 1;
~~~

Nếu sale_id phải duy nhất toàn bảng, còn cần kiểm tra trùng với các partition khác hoặc bảo đảm unique global index/constraint sẽ bảo vệ điều đó. Kiểm tra riêng staging không đủ để bảo đảm uniqueness toàn bảng.

### 5.5. Exchange vào partition

~~~sql
ALTER TABLE sales_part_lab
EXCHANGE PARTITION p2026_01
WITH TABLE sales_stage_lab
WITH VALIDATION;
~~~

Ví dụ đơn giản chưa tạo local/global indexes, nên không cần thêm các tùy chọn index. Trong production có index, hãy chọn INCLUDING/EXCLUDING INDEXES và UPDATE GLOBAL INDEXES theo thiết kế đã kiểm thử.

Sau exchange:

- P2026_01 chứa các hàng 1001, 1002, 1003.
- SALES_STAGE_LAB nhận segment cũ của P2026_01.
- Nếu partition trước đó rỗng, staging nhận partition rỗng.

### 5.6. Kiểm tra dữ liệu sau exchange

~~~sql
SELECT sale_id, sale_date, customer_id, amount
FROM sales_part_lab PARTITION (p2026_01)
ORDER BY sale_id;
~~~

Truy vấn không chỉ rõ partition:

~~~sql
SELECT sale_id, sale_date, customer_id, amount
FROM sales_part_lab
WHERE sale_date >= DATE '2026-01-01'
  AND sale_date < DATE '2026-02-01'
ORDER BY sale_id;
~~~

Đối chiếu số dòng và tổng amount với batch staging đã ghi nhận trước exchange. Nên lưu row count, checksum/aggregate và batch identifier trong hệ thống ETL để có thể đối soát.

## 6. Local index và INCLUDING INDEXES

### 6.1. Local index được chia theo table partition

Tạo local index:

~~~sql
CREATE INDEX ix_sales_part_date_local_lab
ON sales_part_lab(sale_date)
LOCAL;
~~~

Oracle tạo các index partitions tương ứng với table partitions. Khi exchange partition, local index partition đích cũng cần được xử lý.

### 6.2. Chuẩn bị index tương ứng trên staging

Để trao đổi local index segment cùng dữ liệu, staging cần index tương ứng có cấu trúc phù hợp:

~~~sql
CREATE INDEX ix_sales_stage_date_lab
ON sales_stage_lab(sale_date);
~~~

Sau đó:

~~~sql
ALTER TABLE sales_part_lab
EXCHANGE PARTITION p2026_01
WITH TABLE sales_stage_lab
INCLUDING INDEXES
WITH VALIDATION;
~~~

INCLUDING INDEXES không tự xây index trên staging. Index tương ứng phải được chuẩn bị theo cấu trúc Oracle yêu cầu. Kiểm tra số lượng, thứ tự cột, uniqueness và các thuộc tính liên quan.

### 6.3. EXCLUDING INDEXES và rebuild

Nếu exchange không kèm index, local index partition liên quan có thể bị đánh dấu UNUSABLE. Sau thao tác, kiểm tra:

~~~sql
SELECT index_name, partition_name, status
FROM user_ind_partitions
WHERE index_name = 'IX_SALES_PART_DATE_LOCAL_LAB'
ORDER BY partition_position;
~~~

Nếu partition index UNUSABLE và thiết kế yêu cầu usable, rebuild:

~~~sql
ALTER INDEX ix_sales_part_date_local_lab
REBUILD PARTITION p2026_01;
~~~

Tên index và partition phải thay theo object thực tế. Rebuild tốn I/O, TEMP/redo tùy tùy chọn và có thể ảnh hưởng workload. Hãy lập kế hoạch thay vì coi rebuild là bước miễn phí.

### 6.4. Chọn INCLUDING hay EXCLUDING

| Tình huống | Cách cân nhắc |
| --- | --- |
| Cần local index usable ngay sau exchange | Chuẩn bị index staging tương ứng và dùng INCLUDING INDEXES |
| Có thể chấp nhận index partition unusable trong cửa sổ bảo trì | EXCLUDING INDEXES, sau đó rebuild theo kế hoạch |
| Staging không có index phù hợp | Không giả định INCLUDING INDEXES tự tạo; chuẩn bị index hoặc chọn chiến lược khác |
| Có nhiều local indexes lớn | So sánh chi phí build staging index với rebuild partition index |

Lựa chọn tốt nhất phụ thuộc dung lượng batch, số index, thời gian chấp nhận downtime/maintenance và workload sau exchange.

## 7. Global index và UPDATE GLOBAL INDEXES

### 7.1. Global index bao phủ nhiều partition

Global index có thể giúp lookup theo khóa không chứa partition key, ví dụ SALE_ID duy nhất toàn bảng. Khi một partition được exchange, ROWID/segment mapping liên quan có thể thay đổi; global index phải được duy trì để trỏ đúng hàng.

Ví dụ:

~~~sql
CREATE INDEX ix_sales_part_id_global_lab
ON sales_part_lab(sale_id)
GLOBAL;
~~~

### 7.2. Duy trì global index khi exchange

Nếu release và thao tác hỗ trợ:

~~~sql
ALTER TABLE sales_part_lab
EXCHANGE PARTITION p2026_01
WITH TABLE sales_stage_lab
INCLUDING INDEXES
WITH VALIDATION
UPDATE GLOBAL INDEXES;
~~~

UPDATE GLOBAL INDEXES yêu cầu Oracle duy trì global index trong quá trình exchange. Công việc này có thể làm tăng thời gian và tài nguyên của DDL, nhất là khi index lớn.

Nếu không duy trì global index trong thao tác, trạng thái index có thể chuyển thành UNUSABLE hoặc cần bước bảo trì tiếp theo theo semantics của release. Hãy xác minh bằng USER_INDEXES/ALL_INDEXES sau DDL.

### 7.3. Global index maintenance là một trade-off

| Lựa chọn | Lợi ích | Chi phí/rủi ro |
| --- | --- | --- |
| Duy trì global index trong exchange | Consumer có thể tiếp tục dùng index theo trạng thái được hỗ trợ | Exchange tốn thêm công việc cập nhật index |
| Không duy trì trong exchange | Có thể giảm công việc trong critical DDL window | Index có thể unusable; cần rebuild/maintenance trước khi workload phụ thuộc index |

Không để ứng dụng tiếp tục chạy truy vấn phụ thuộc global index khi index đang UNUSABLE. Đưa bước kiểm tra index status thành điều kiện publish dữ liệu.

### 7.4. Kiểm tra index sau exchange

~~~sql
SELECT index_name, index_type, status
FROM user_indexes
WHERE table_name = 'SALES_PART_LAB'
ORDER BY index_name;

SELECT index_name, partition_name, status
FROM user_ind_partitions
WHERE index_name IN (
    SELECT index_name
    FROM user_indexes
    WHERE table_name = 'SALES_PART_LAB'
)
ORDER BY index_name, partition_position;
~~~

Global partitioned index có thể cần xem USER_IND_PARTITIONS; global nonpartitioned index xem USER_INDEXES. Hãy kiểm tra đúng loại index.

## 8. WITH VALIDATION và WITHOUT VALIDATION

### 8.1. WITH VALIDATION bảo vệ partition bound

Với RANGE partition P2026_01:

~~~text
lower bound: 2026-01-01 (exclusive of previous partition)
upper bound: 2026-02-01 (exclusive)
valid rows: 2026-01-01 <= SALE_DATE < 2026-02-01
~~~

WITH VALIDATION yêu cầu dữ liệu exchange table thỏa điều kiện partition. Nếu có một hàng ngoài range, Oracle từ chối exchange.

### 8.2. WITHOUT VALIDATION đặt trách nhiệm lên pipeline

Nếu dùng WITHOUT VALIDATION, pipeline phải có kiểm tra độc lập trước đó. Ít nhất:

- Tất cả hàng có partition key hợp lệ, không NULL nếu key yêu cầu NOT NULL.
- Min/max nằm trong partition bounds.
- Không có giá trị rời rạc sai LIST partition.
- Không có duplicate key trái với unique constraint.
- Các check constraints và business rules được thỏa.
- Batch đã được đóng, không còn DML thay đổi dữ liệu sau validation.

Nếu staging có thể bị ghi thêm sau bước kiểm tra, kết quả validation cũ không còn đáng tin. Hãy khóa hoặc chuyển staging sang trạng thái immutable trước exchange.

### 8.3. Validation không thay thế kiểm tra nghiệp vụ

WITH VALIDATION kiểm tra điều kiện partition phù hợp. Nó không tự xác minh:

- Tổng amount có khớp file nguồn.
- Không có duplicate nghiệp vụ nếu không có constraint phù hợp.
- Mã khách hàng có hợp lệ trong hệ thống nguồn.
- Batch có đủ số dòng dự kiến.
- Dữ liệu đã được chuyển đổi timezone/tiền tệ đúng.

Hãy tách partition-bound validation khỏi data-quality validation.

### 8.4. Unique/primary key và validation

Constraint duy nhất có thể ảnh hưởng cách Oracle thực hiện exchange và việc có thể bỏ validation hay không. Một số trường hợp Oracle vẫn phải kiểm tra tính duy nhất hoặc áp dụng quy tắc bổ sung dù câu lệnh chỉ định WITHOUT VALIDATION. Đừng dùng WITHOUT VALIDATION như lời hứa rằng Oracle sẽ bỏ qua mọi kiểm tra. Xem SQL Language Reference của đúng release, trạng thái constraint và cấu trúc index trước khi chọn.

## 9. Exchange-out: tách partition ra bảng độc lập

Exchange-out hữu ích khi partition cũ cần archive hoặc export mà không muốn DELETE từng hàng khỏi bảng chính.

### 9.1. Chuẩn bị bảng archive

Bảng archive cần cấu trúc tương thích:

~~~sql
CREATE TABLE sales_archive_stage_lab (
    sale_id      NUMBER NOT NULL,
    sale_date    DATE NOT NULL,
    customer_id  NUMBER NOT NULL,
    amount       NUMBER(12,2) NOT NULL
);
~~~

Nếu cần exchange index, chuẩn bị index tương ứng theo cấu trúc yêu cầu. Nếu không, chọn EXCLUDING INDEXES và lập kế hoạch index status/rebuild.

### 9.2. Exchange partition ra bảng

~~~sql
ALTER TABLE sales_part_lab
EXCHANGE PARTITION p2026_01
WITH TABLE sales_archive_stage_lab
WITH VALIDATION;
~~~

Sau thao tác:

- SALES_ARCHIVE_STAGE_LAB chứa các hàng trước đó thuộc P2026_01.
- P2026_01 nhận segment của SALES_ARCHIVE_STAGE_LAB, thường là rỗng nếu bảng archive ban đầu rỗng.

### 9.3. Sau exchange-out

Có thể thực hiện các bước riêng:

- Đối chiếu row count và aggregate.
- Gather statistics cho bảng archive.
- Export bằng Data Pump hoặc chuyển dữ liệu qua quy trình lưu trữ.
- Nén/di chuyển bảng archive theo chính sách.
- Drop partition đã rỗng nếu mục tiêu là loại bỏ partition cũ, hoặc giữ partition để tái sử dụng.

Không DROP partition trước khi exchange-out nếu cần giữ dữ liệu. Cũng không DROP bảng archive stage trước khi export/backup hoàn tất.

### 9.4. Luân chuyển dữ liệu giữa các bảng

Exchange-out rồi exchange-in có thể được dùng để chuyển segment giữa các đối tượng tương thích, nhưng cần quản lý kỹ:

- Bảng nhận và bảng nguồn có cùng cấu trúc không?
- Có cùng partition bounds hoặc quy tắc dữ liệu không?
- Index và constraint có được bảo toàn?
- Global index của từng bảng được xử lý ra sao?
- Dữ liệu đã được kiểm tra sau mỗi lần swap chưa?

Không xem exchange là một thao tác copy có thể thực hiện lặp lại mà không xét nội dung hiện tại của hai phía.

## 10. DDL transaction boundary, locking và concurrency

### 10.1. EXCHANGE PARTITION là DDL

ALTER TABLE EXCHANGE PARTITION là DDL. Oracle thực hiện implicit commit theo quy tắc DDL: transaction hiện tại có thể được commit trước khi DDL chạy, và DDL thành công được commit sau đó.

Vì vậy:

- Không đặt exchange giữa các DML của một transaction nghiệp vụ cần rollback cùng nhau.
- Commit staging load và hoàn tất data-quality checks trước DDL.
- Không mong ROLLBACK có thể đảo ngược exchange.
- Nếu exchange sai, cần một DDL exchange ngược hoặc quy trình phục hồi được thiết kế trước; không phải ROLLBACK.

### 10.2. Exchange cần khóa

Exchange phải lấy các khóa/metadata locks cần thiết trên bảng partitioned, partition và exchange table. Nó không có nghĩa “metadata-only thì hoàn toàn không block”. Tác động chờ phụ thuộc release, tùy chọn, session đang chạy và loại object.

Trước khi exchange:

- Kiểm tra batch đã đóng.
- Tránh DML đồng thời trên staging.
- Xác định workload có thể truy cập partition đích trong cửa sổ DDL.
- Đặt timeout/chính sách vận hành phù hợp nếu có.
- Theo dõi session wait và thời gian DDL.

### 10.3. DDL thất bại và dữ liệu

Nếu exchange thất bại do cấu trúc không tương thích hoặc validation không đạt, Oracle báo lỗi và không hoàn tất việc hoán đổi theo cách ứng dụng mong muốn. Tuy nhiên, implicit commit trước DDL vẫn có thể đã kết thúc transaction DML trước đó. Vì vậy staging load phải được commit/chốt có chủ đích trước khi gọi exchange.

### 10.4. Consumer đang đọc dữ liệu

Đừng giả định mọi truy vấn đang chạy sẽ không bị ảnh hưởng. DDL cần khóa phù hợp và có thể phải chờ hoặc làm session khác chờ. Hãy thử nghiệm concurrency với đúng workload, thời gian truy vấn và release. Với bảng quan trọng, có thể cần maintenance window hoặc chiến lược publish dữ liệu qua view/synonym/application state.

## 11. Statistics và metadata sau exchange

### 11.1. Kiểm tra partition

~~~sql
SELECT
    partition_name,
    partition_position,
    num_rows,
    blocks,
    tablespace_name
FROM user_tab_partitions
WHERE table_name = 'SALES_PART_LAB'
ORDER BY partition_position;
~~~

NUM_ROWS/BLOCKS phụ thuộc statistics và có thể cũ. Không dùng số liệu thống kê thay cho COUNT(*) đối soát khi cần xác nhận batch.

### 11.2. Kiểm tra index status

~~~sql
SELECT index_name, status, uniqueness
FROM user_indexes
WHERE table_name = 'SALES_PART_LAB'
ORDER BY index_name;

SELECT index_name, partition_name, status
FROM user_ind_partitions
WHERE index_name IN (
    SELECT index_name
    FROM user_indexes
    WHERE table_name = 'SALES_PART_LAB'
)
ORDER BY index_name, partition_position;
~~~

Điều kiện publish nên yêu cầu mọi index mà workload cần đều usable. Nếu có index UNUSABLE, thực hiện rebuild hoặc maintenance phù hợp rồi kiểm tra lại.

### 11.3. Gather statistics

Sau exchange, thống kê của partition và global table statistics cần được xem xét. Không giả định mọi thống kê staging tự động trở thành thống kê đúng cho bảng partitioned:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname     => USER,
        tabname     => 'SALES_PART_LAB',
        partname    => 'P2026_01',
        granularity => 'PARTITION',
        cascade     => TRUE
    );
END;
/
~~~

Tùy chiến lược thống kê, có thể cần cập nhật global statistics hoặc incremental statistics. Trên production, theo DBA policy và maintenance window; gather stats có thể làm thay đổi execution plan.

### 11.4. Kiểm tra DDL và partition bounds

~~~sql
SELECT DBMS_METADATA.GET_DDL(
           'TABLE',
           'SALES_PART_LAB',
           USER
       )
FROM dual;
~~~

USER_TAB_PARTITIONS cung cấp metadata partition, nhưng HIGH_VALUE có kiểu LONG trong một số dictionary views nên việc xử lý trực tiếp bị giới hạn. Dùng DBMS_METADATA hoặc công cụ phù hợp khi cần trích xuất định nghĩa chính xác.

## 12. Exchange và các chiến lược index/constraint

### 12.1. Thiết kế index trước khi chọn exchange mode

Hãy lập danh sách:

| Index | Loại | Vai trò | Xử lý khi exchange |
| --- | --- | --- | --- |
| IX_SALES_DATE_LOCAL | Local | Truy vấn theo ngày trong partition | INCLUDING INDEXES hoặc rebuild local index partition |
| IX_SALES_ID_GLOBAL | Global | Lookup theo sale_id toàn bảng | UPDATE GLOBAL INDEXES hoặc maintenance sau exchange |
| PK_SALES | Unique/constraint-backed | Bảo vệ uniqueness | Kiểm tra unique key có chứa partition key và quy tắc exchange |

Bảng này cần được điền theo schema thật. Không có một cú pháp INCLUDING INDEXES duy nhất giải quyết tất cả loại index.

### 12.2. Unique key và partition key

Nếu bảng partition theo SALE_DATE nhưng SALE_ID phải duy nhất toàn bảng:

- Local unique index trên SALE_ID đơn lẻ có thể không đáp ứng quy tắc uniqueness của partitioned table vì key không chứa partition key.
- Global unique index có thể bảo vệ SALE_ID toàn bảng.
- Exchange cần cập nhật global unique index để các entry trỏ đúng ROWID.

Thiết kế partition key và uniqueness phải được quyết định cùng nhau. Nếu không, quy trình exchange có thể gặp lỗi hoặc buộc phải rebuild index lớn sau mỗi batch.

### 12.3. Constraint validation và staging

Staging cần tuân thủ các quy tắc dữ liệu tương ứng. Một số kiểm tra có thể làm trước exchange:

~~~sql
-- Gia tri bat buoc
SELECT COUNT(*)
FROM sales_stage_lab
WHERE sale_id IS NULL
   OR sale_date IS NULL
   OR customer_id IS NULL
   OR amount IS NULL;

-- Gia tri amount khong hop le
SELECT COUNT(*)
FROM sales_stage_lab
WHERE amount < 0;

-- Kiem tra duplicate trong staging
SELECT sale_id, COUNT(*)
FROM sales_stage_lab
GROUP BY sale_id
HAVING COUNT(*) > 1;
~~~

Đây là kiểm tra nghiệp vụ bổ sung. Constraint database vẫn nên được khai báo phù hợp để bảo vệ dữ liệu khi các luồng khác ghi vào.

## 13. Quy trình ETL production có kiểm soát

Một pipeline có thể chia thành các trạng thái:

~~~text
CREATED
   |
   v
LOADING
   |
   v
LOADED
   |
   v
VALIDATING
   |
   v
READY_TO_EXCHANGE
   |
   v
EXCHANGING
   |
   v
EXCHANGED
   |
   v
INDEX_CHECK
   |
   v
STATS_REFRESH
   |
   v
PUBLISHED
~~~

Nếu một bước thất bại, batch phải chuyển sang trạng thái lỗi có thể điều tra. Không đánh dấu PUBLISHED chỉ vì DDL trả thành công; cần kiểm tra index, dữ liệu và statistics theo yêu cầu.

### 13.1. Ghi batch metadata

Một bảng điều phối có thể lưu:

~~~sql
CREATE TABLE etl_exchange_batch_lab (
    batch_id       NUMBER PRIMARY KEY,
    target_table   VARCHAR2(30 CHAR) NOT NULL,
    target_partition VARCHAR2(30 CHAR) NOT NULL,
    source_name    VARCHAR2(100 CHAR),
    row_count      NUMBER,
    amount_total   NUMBER(18,2),
    status         VARCHAR2(30 CHAR) NOT NULL,
    loaded_at      TIMESTAMP,
    validated_at   TIMESTAMP,
    exchanged_at   TIMESTAMP,
    published_at   TIMESTAMP,
    error_message  VARCHAR2(2000 CHAR)
);
~~~

Thông tin batch giúp đối soát và phục hồi quy trình nếu scheduler/job bị dừng giữa các bước. Trạng thái batch phải được quản lý nhất quán; không ghi một trạng thái “EXCHANGED” trước khi DDL thực sự thành công và được xác nhận.

### 13.2. Kiểm tra staging đã đóng

Sau khi batch load xong:

- Dừng writer vào staging hoặc chuyển sang bảng staging version mới.
- Ghi nhận row count/aggregate.
- Chạy validation.
- Chốt batch ID.
- Không cho job khác sửa staging trong thời gian exchange.

Nếu có DML sau validation nhưng trước exchange, dữ liệu được exchange có thể khác dữ liệu đã kiểm tra. Đây là race condition của pipeline.

### 13.3. Idempotency và retry

Nếu scheduler không nhận được phản hồi DDL do mất kết nối, không nên mù quáng chạy lại exchange. Vì exchange là swap, lần thứ hai có thể hoán đổi dữ liệu ngược lại hoặc tạo trạng thái khác mong muốn.

Khi client mất phản hồi:

1. Kết nối lại.
2. Kiểm tra nội dung partition đích và staging.
3. Đối chiếu batch ID/row count/aggregate.
4. Kiểm tra index status.
5. Xác định exchange đã xảy ra hay chưa.
6. Chỉ chạy lại khi trạng thái thực tế đã được hiểu rõ.

Đây là idempotency ở cấp workflow: hành động cần dựa trên trạng thái đã xác nhận, không phải chỉ gửi lại cùng DDL.

### 13.4. Logging và audit

Ghi lại:

- Batch ID và partition name.
- Thời gian bắt đầu/kết thúc.
- Số hàng và aggregate trước/sau.
- Validation mode.
- Index mode và trạng thái global/local index.
- Statistics refresh.
- User/session/SQL ID nếu cần.
- Kết quả publish và lỗi.

DDL exchange là thao tác quản trị dữ liệu quan trọng; audit giúp giải thích dữ liệu đến từ đâu và khi nào được đưa vào bảng chính.

## 14. Những giới hạn và trường hợp cần kiểm tra kỹ

Không nên áp dụng mẫu exchange đơn giản cho mọi loại bảng. Trước khi dùng với object phức tạp, kiểm tra tài liệu release cho:

- Partitioned IOT và overflow/mapping table.
- LOB columns và SecureFiles/BasicFiles.
- Domain indexes.
- Bitmap indexes và các index đặc biệt.
- Virtual, invisible hoặc hidden columns.
- Identity columns và default expressions.
- Object types, nested tables hoặc XMLType.
- Reference partitioning và cascading exchange.
- Compression, tablespace, encryption và logging attributes.
- Enabled/validated primary key, unique, check và foreign key constraints.
- Global/local index maintenance.
- Online exchange hoặc các tùy chọn concurrency mới của release.

Các điều kiện này có thể thay đổi theo release và cấu trúc. Hãy tạo proof of concept với DDL giống production, không chỉ thử trên một bảng bốn cột đơn giản rồi suy ra mọi object đều exchange được.

## 15. Các lỗi thường gặp

| Lỗi/hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Exchange báo cấu trúc không tương thích | Số cột, thứ tự, datatype hoặc thuộc tính không khớp | So sánh DDL hai bảng và hidden/virtual columns |
| WITH VALIDATION thất bại | Có hàng ngoài partition bound | Tìm hàng sai, sửa staging và chạy validation lại |
| Dùng WITHOUT VALIDATION nhưng truy vấn thiếu hàng | Dữ liệu bị exchange vào partition sai | Đối soát partition key; exchange ngược/di chuyển đúng theo kế hoạch |
| Local index partition UNUSABLE | Excluding indexes hoặc index exchange không phù hợp | Rebuild/repair theo index strategy |
| Global index UNUSABLE | Không duy trì global index trong thao tác | UPDATE GLOBAL INDEXES hoặc rebuild theo kế hoạch |
| INCLUDING INDEXES thất bại | Staging thiếu index tương ứng hoặc index definition không khớp | Chuẩn bị index staging tương thích |
| DDL chờ khóa | Session đang dùng bảng/partition hoặc staging | Tìm blocker, điều phối workload và maintenance window |
| Staging sau exchange chứa dữ liệu cũ | Đây là semantics swap | Kiểm tra và xử lý staging sau khi đối soát |
| Retry exchange làm dữ liệu quay ngược | Client gửi lại DDL sau khi mất phản hồi | Kiểm tra trạng thái thực tế trước retry |
| Statistics không phản ánh batch mới | Stats cũ hoặc chưa được cập nhật đúng cấp | Gather partition/global stats theo policy |
| DDL commit DML trước đó ngoài ý muốn | Implicit commit trước DDL | Kết thúc staging transaction có chủ đích trước exchange |
| Exchange không phù hợp với object đặc biệt | Release/object type có giới hạn | Kiểm tra SQL Language Reference và thử trên môi trường tương đương |

## 16. Bài thực hành tổng hợp: exchange-in rồi exchange-out

Lab này giả định Oracle environment được cấp quyền sử dụng Partitioning. Chạy trong schema riêng.

### Bước 1 — Tạo bảng partitioned

~~~sql
CREATE TABLE sales_exchange_lab (
    sale_id NUMBER NOT NULL,
    sale_date DATE NOT NULL,
    customer_id NUMBER NOT NULL,
    amount NUMBER(12,2) NOT NULL
)
PARTITION BY RANGE (sale_date) (
    PARTITION p_before_2026 VALUES LESS THAN (DATE '2026-01-01'),
    PARTITION p2026_01 VALUES LESS THAN (DATE '2026-02-01'),
    PARTITION p2026_02 VALUES LESS THAN (DATE '2026-03-01'),
    PARTITION p_future VALUES LESS THAN (MAXVALUE)
);
~~~

### Bước 2 — Tạo staging table

~~~sql
CREATE TABLE sales_exchange_stage_lab (
    sale_id NUMBER NOT NULL,
    sale_date DATE NOT NULL,
    customer_id NUMBER NOT NULL,
    amount NUMBER(12,2) NOT NULL
);
~~~

### Bước 3 — Nạp staging

~~~sql
INSERT INTO sales_exchange_stage_lab VALUES
    (1, DATE '2026-01-03', 101, 120);

INSERT INTO sales_exchange_stage_lab VALUES
    (2, DATE '2026-01-15', 102, 250);

INSERT INTO sales_exchange_stage_lab VALUES
    (3, DATE '2026-01-28', 101, 80);

COMMIT;
~~~

### Bước 4 — Kiểm tra partition range

~~~sql
SELECT COUNT(*) AS invalid_rows
FROM sales_exchange_stage_lab
WHERE sale_date < DATE '2026-01-01'
   OR sale_date >= DATE '2026-02-01';
~~~

Kết quả phải bằng 0.

### Bước 5 — Exchange-in

~~~sql
ALTER TABLE sales_exchange_lab
EXCHANGE PARTITION p2026_01
WITH TABLE sales_exchange_stage_lab
WITH VALIDATION;
~~~

### Bước 6 — Xác nhận partition nhận dữ liệu

~~~sql
SELECT *
FROM sales_exchange_lab PARTITION (p2026_01)
ORDER BY sale_id;
~~~

### Bước 7 — Tạo bảng archive và exchange-out

~~~sql
CREATE TABLE sales_exchange_archive_lab (
    sale_id NUMBER NOT NULL,
    sale_date DATE NOT NULL,
    customer_id NUMBER NOT NULL,
    amount NUMBER(12,2) NOT NULL
);

ALTER TABLE sales_exchange_lab
EXCHANGE PARTITION p2026_01
WITH TABLE sales_exchange_archive_lab
WITH VALIDATION;
~~~

Sau bước này, SALES_EXCHANGE_ARCHIVE_LAB chứa các hàng vừa được exchange-out. P2026_01 nhận segment rỗng của bảng archive ban đầu.

### Bước 8 — Đối soát archive

~~~sql
SELECT COUNT(*) AS row_count,
       MIN(sale_date) AS min_date,
       MAX(sale_date) AS max_date,
       SUM(amount) AS total_amount
FROM sales_exchange_archive_lab;
~~~

Đối chiếu với batch metadata đã ghi trước đó.

### Bước 9 — Dọn lab (tùy chọn)

~~~sql
DROP TABLE sales_exchange_archive_lab PURGE;
DROP TABLE sales_exchange_stage_lab PURGE;
DROP TABLE sales_exchange_lab PURGE;
~~~

DROP TABLE là DDL và có implicit commit. Chỉ chạy khi chắc chắn các bảng thuộc lab và không cần dữ liệu nữa.

## 17. Checklist trước khi chạy EXCHANGE PARTITION

**Cấu trúc**

- Bảng đích đúng partition và đúng bound.
- Staging là bảng exchange tương thích.
- Số cột, thứ tự, datatype và thuộc tính cột đã được đối chiếu.
- Hidden/virtual/identity/LOB/object-specific columns đã được kiểm tra.
- Constraint và index tương ứng đã được chuẩn bị.

**Dữ liệu**

- Batch đã nạp xong và commit.
- Staging không còn writer.
- Range/list partition validation đã đạt.
- Duplicate/business checks đã đạt.
- Row count và aggregate đã được ghi nhận.
- Batch ID và nguồn dữ liệu đã được audit.

**Exchange options**

- Chọn WITH VALIDATION hay WITHOUT VALIDATION có lý do rõ.
- Chọn INCLUDING/EXCLUDING INDEXES theo local index strategy.
- Global indexes được duy trì hoặc có kế hoạch rebuild.
- Release hỗ trợ đúng cú pháp/tùy chọn đang dùng.

**Vận hành**

- Đã hiểu DDL implicit commit.
- Đã xác định khóa và ảnh hưởng workload.
- Có maintenance window/timeout phù hợp.
- Có bước xác nhận partition và index status.
- Có bước gather statistics.
- Có kế hoạch đối soát, phục hồi và xử lý staging sau swap.
- Có quy tắc kiểm tra trạng thái trước khi retry.

## 18. Câu hỏi tự kiểm tra

1. EXCHANGE PARTITION là copy dữ liệu hay hoán đổi segment?
2. Vì sao staging sau exchange có thể chứa dữ liệu cũ của partition?
3. Exchange-in và exchange-out khác nhau ở mục tiêu nào?
4. Vì sao CTAS không nên được xem là bản sao hoàn chỉnh của DDL bảng?
5. Những thuộc tính nào cần tương thích giữa staging và bảng partitioned?
6. WITH VALIDATION kiểm tra điều gì?
7. WITHOUT VALIDATION có thể gây sai kết quả partition pruning như thế nào?
8. Validation partition bound có thay thế data-quality validation không?
9. INCLUDING INDEXES cần điều kiện gì ở staging?
10. EXCLUDING INDEXES có thể ảnh hưởng local index partition ra sao?
11. UPDATE GLOBAL INDEXES có mục đích gì?
12. Vì sao phải kiểm tra USER_INDEXES và USER_IND_PARTITIONS sau exchange?
13. Tại sao unique key không chứa partition key có thể cần global unique index?
14. Vì sao EXCHANGE PARTITION là DDL boundary quan trọng?
15. Có thể ROLLBACK một exchange đã thành công không?
16. Vì sao phải commit/chốt staging trước exchange?
17. Exchange có thể chờ khóa dù chủ yếu là metadata operation không?
18. Sau exchange cần kiểm tra những thông tin nào trước khi publish?
19. Vì sao không được retry exchange mù quáng sau khi client mất phản hồi?
20. Khi nào exchange-out hữu ích cho archive?

**Gợi ý trả lời:**

1. Hoán đổi segment/metadata giữa partition và bảng không partition tương thích.
2. Vì thao tác swap; dữ liệu cũ của partition chuyển sang bảng staging.
3. Exchange-in đưa staging vào partition; exchange-out đưa partition ra bảng độc lập.
4. CTAS thường không sao chép mọi constraint, index, trigger và thuộc tính cột.
5. Số cột, thứ tự, datatype và các thuộc tính đặc biệt liên quan.
6. Dữ liệu exchange table có thuộc partition bound đích không.
7. Hàng nằm trong partition sai có thể bị pruning bỏ qua khi truy vấn theo partition key.
8. Không; cần kiểm tra business rules, duplicate, aggregate và nguồn dữ liệu riêng.
9. Index staging tương ứng phải có cấu trúc tương thích để exchange index.
10. Local index partition có thể thành UNUSABLE và cần rebuild.
11. Duy trì global index để entry tiếp tục trỏ đúng hàng sau exchange.
12. Để xác nhận index vẫn usable và consumer có thể dùng.
13. Local unique index cần đáp ứng quy tắc liên quan partition key; global unique index có thể bảo vệ uniqueness toàn bảng.
14. DDL có implicit commit và không rollback như DML.
15. Không; cần DDL exchange ngược hoặc quy trình phục hồi.
16. Vì DDL có thể implicit commit transaction trước khi chạy.
17. Có; DDL vẫn cần metadata/table/partition locks phù hợp.
18. Row count, aggregate, partition bounds, constraint, index status, statistics và batch state.
19. Vì exchange là swap; chạy lần nữa có thể hoán đổi dữ liệu ngược.
20. Khi muốn tách một partition cũ thành bảng để export/archive/xử lý riêng.

## Tài liệu Oracle tham khảo

- [Oracle Database 19c VLDB and Partitioning Guide — Exchanging Partitions](https://docs.oracle.com/en/database/oracle/oracle-database/19/vldbg/maintenance-partition-tables-indexes.html): exchange partition và quản lý partitioned tables/indexes.
- [Oracle Database 19c SQL Language Reference — ALTER TABLE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ALTER-TABLE.html): cú pháp EXCHANGE PARTITION, index options và validation.
- [Oracle Database 19c SQL Language Reference — CREATE TABLE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-TABLE.html): tạo bảng partitioned và các thuộc tính cấu trúc.
- [Oracle Database 19c VLDB and Partitioning Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/vldbg/): chiến lược partitioning, maintenance và data warehousing.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_STATS](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_STATS.html): thu thập và quản lý statistics.
- [Oracle Database Reference — USER_TAB_PARTITIONS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/USER_TAB_PARTITIONS.html): metadata partition của schema hiện tại.
- [Oracle Database Reference — USER_IND_PARTITIONS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/USER_IND_PARTITIONS.html): trạng thái và metadata local/global index partitions.

**Nguyên tắc cần nhớ:** EXCHANGE PARTITION là một thao tác swap segment giữa partition và bảng staging tương thích. Hãy chuẩn bị staging, kiểm tra dữ liệu thuộc đúng partition, quyết định cách xử lý local/global indexes, rồi xác nhận dữ liệu và trạng thái index sau DDL. Vì exchange là DDL có implicit commit và không thể ROLLBACK như DML, pipeline phải chốt batch, ghi nhận trạng thái, đối soát kết quả và kiểm tra trạng thái thực tế trước khi retry.
