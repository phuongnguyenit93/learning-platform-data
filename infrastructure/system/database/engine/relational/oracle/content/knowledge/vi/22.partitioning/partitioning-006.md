# Local/global index và tác động của bảo trì partition trong Oracle

Khi một bảng Oracle được chia partition, index trên bảng cũng cần được thiết kế theo cách dữ liệu được phân vùng và theo các thao tác bảo trì như ADD, DROP, TRUNCATE, MOVE, SPLIT, MERGE hoặc EXCHANGE PARTITION. Một index có thể được tổ chức theo từng partition của bảng (local index), hoặc có phạm vi độc lập với partition của bảng (global index).

Local index thường dễ bảo trì cùng partition dữ liệu: khi một partition được thêm, xóa hoặc trao đổi, phần index tương ứng có thể được xử lý cục bộ. Global index có thể truy cập khóa trên nhiều partition của bảng, phù hợp với các truy vấn tìm theo khóa không chứa partition key, nhưng một số thao tác partition maintenance có thể phải cập nhật hoặc làm mất tính sử dụng của index nếu không dùng đúng tùy chọn.

Chọn local hay global không chỉ là quyết định hiệu năng SELECT. Nó ảnh hưởng đến tính duy nhất của khóa, chi phí ETL, thời gian khóa, khả năng availability, quy trình rebuild và tính phức tạp khi triển khai DDL.

Sau bài học, bạn có thể:

- Phân biệt local index, global nonpartitioned index và global partitioned index.
- Hiểu local index partition được căn chỉnh với table partition như thế nào.
- Phân biệt local prefixed và local nonprefixed index.
- Chọn local/global theo truy vấn, partition key, unique constraint và workload.
- Hiểu partition pruning và index partition pruning.
- Dự đoán tác động của ADD, DROP, TRUNCATE, MOVE, SPLIT, MERGE và EXCHANGE PARTITION.
- Dùng UPDATE INDEXES/UPDATE GLOBAL INDEXES và hiểu khác biệt theo phiên bản Oracle.
- Kiểm tra index hoặc index partition ở trạng thái UNUSABLE.
- Rebuild index partition đúng phạm vi và quản lý chi phí bảo trì.
- Lập kế hoạch ETL, exchange partition và kiểm tra sau migration.

> Các cú pháp partition maintenance và khả năng duy trì index thay đổi theo phiên bản Oracle, loại partition, loại index và tùy chọn DDL. Các ví dụ trong bài là mẫu phổ biến; hãy xác nhận syntax trên phiên bản đang chạy và kiểm tra trạng thái index sau mỗi thao tác. Không thử DROP/TRUNCATE/MOVE trên bảng production để học cú pháp.

## 1. Nền tảng: partition table và index

### 1.1. Partition table là gì?

Partitioning chia một bảng lớn thành nhiều phần vật lý/logical nhỏ hơn dựa trên partition key. Ứng dụng vẫn truy vấn một tên bảng duy nhất; Oracle xác định partition cần đọc hoặc thay đổi dựa trên predicate và metadata.

Ví dụ bảng SALES được partition theo tháng của SALE_DATE:

| Partition | Khoảng dữ liệu |
| --- | --- |
| P2026_01 | Tháng 01/2026 |
| P2026_02 | Tháng 02/2026 |
| P2026_03 | Tháng 03/2026 |
| P2026_04 | Tháng 04/2026 |

Một truy vấn:

```sql
SELECT SUM(amount)
FROM sales
WHERE sale_date >= DATE '2026-03-01'
  AND sale_date <  DATE '2026-04-01';
```

có thể chỉ cần đọc partition P2026_03. Việc loại partition không liên quan được gọi là partition pruning. Partitioning có thể giúp quản lý dữ liệu theo thời gian, archive, purge, load và truy vấn; nó không tự động tạo index.

### 1.2. Table partition và index partition là hai cấu trúc riêng

Một bảng partitioned có thể có:

- Không có index.
- Một hoặc nhiều local index.
- Một hoặc nhiều global index.
- Cả local và global index trên các cột khác nhau.

Mỗi index có cách phân vùng và vòng đời riêng. Khi table partition thay đổi, cần xác định index nào được Oracle duy trì tự động, index nào cần tùy chọn cập nhật, và index partition nào có thể chuyển sang UNUSABLE.

### 1.3. Local và global nói về quan hệ với partition của bảng

- **Local index:** index được partition theo cách tương ứng với table; mỗi index partition gắn với một table partition.
- **Global index:** index có phạm vi trên nhiều table partition; cách phân vùng của index không bắt buộc trùng với cách phân vùng của table.

Global index có thể là một index không partition (một cấu trúc index toàn cục) hoặc một global partitioned index có partitioning scheme riêng.

## 2. Local index

### 2.1. Khái niệm

Local index được partition theo cùng partitioning key và ranh giới tương ứng với bảng. Mỗi partition của local index chỉ tham chiếu dữ liệu thuộc table partition tương ứng.

Ví dụ:

```sql
CREATE INDEX ix_sales_customer_local
ON sales (customer_id)
LOCAL;
```

Nếu SALES có 12 table partitions theo tháng, local index thường có 12 index partitions tương ứng. Tên partition index có thể do Oracle sinh theo metadata hoặc được đặt trong câu lệnh tạo index tùy cú pháp.

### 2.2. Mô hình local index

```text
TABLE SALES
  P2026_01 ───── LOCAL INDEX PARTITION P2026_01
  P2026_02 ───── LOCAL INDEX PARTITION P2026_02
  P2026_03 ───── LOCAL INDEX PARTITION P2026_03
  P2026_04 ───── LOCAL INDEX PARTITION P2026_04

Mỗi index partition chỉ lập chỉ mục các hàng
trong table partition tương ứng.
```

Local index có tính equipartitioned: cấu trúc index theo sát cấu trúc partition của table. Điều này làm các thao tác bảo trì partition thường dễ giới hạn trong một partition index tương ứng thay vì phải điều chỉnh index toàn bảng.

### 2.3. Ưu điểm

- **Bảo trì cục bộ:** drop/truncate một table partition thường chỉ cần xử lý index partition tương ứng đối với local index.
- **Quản lý vòng đời dữ liệu:** archive hoặc purge theo partition có thể giữ các index partition còn lại hoạt động.
- **Khả năng phục hồi:** nếu một local index partition cần rebuild, có thể rebuild riêng partition đó.
- **Phù hợp ETL:** các partition mới có thể được load và index theo quy trình từng partition.
- **Partition-wise access:** optimizer có thể khai thác quan hệ giữa table partition và local index partition.
- **Không phụ thuộc global keyspace:** index partition có thể được bảo trì cùng table partition tương ứng.

### 2.4. Hạn chế

- Truy vấn không có predicate trên partition key có thể phải probe nhiều local index partitions.
- Một local index không nhất thiết là đường truy cập tốt nhất cho lookup toàn bảng theo một khóa không chứa partition key.
- Local unique index có giới hạn về khóa: để bảo đảm uniqueness trên toàn bảng, khóa unique thường phải chứa đầy đủ partitioning key của table.
- Số lượng index partitions tăng theo số table partitions, làm metadata và công việc bảo trì nhiều hơn.

### 2.5. Thêm partition và local index

Khi thêm table partition, Oracle có thể tạo partition tương ứng cho local index theo metadata. Với range partition, ví dụ:

```sql
ALTER TABLE sales
ADD PARTITION p2026_05
VALUES LESS THAN (DATE '2026-06-01');
```

Các local index được duy trì theo cấu trúc partition của table. Sau DDL, vẫn nên kiểm tra USER_IND_PARTITIONS/ALL_IND_PARTITIONS để xác nhận partition index mới ở trạng thái usable.

## 3. Global index

### 3.1. Global nonpartitioned index

Global nonpartitioned index là một index duy nhất có thể chứa entry trỏ tới hàng thuộc bất kỳ partition nào của table. Index không chia thành các partition tương ứng với table.

Ví dụ trên bảng SALES partition theo SALE_DATE, ứng dụng cần tìm giao dịch theo SALE_ID mà không biết ngày:

```sql
CREATE INDEX ix_sales_sale_id_global
ON sales (sale_id);
```

Vì index này không khai báo LOCAL và không có partitioning clause riêng, nó là một global nonpartitioned index trên bảng partitioned.

### 3.2. Global partitioned index

Global partitioned index có partitioning scheme riêng, độc lập với partitioning của table. Ví dụ minh họa global index partitioned theo hash trên CUSTOMER_ID:

```sql
CREATE INDEX ix_sales_customer_g
ON sales (customer_id)
GLOBAL PARTITION BY HASH (customer_id)
PARTITIONS 8;
```

Các index partitions này phân bố key của toàn bảng theo hash CUSTOMER_ID; chúng không tương ứng một-một với table partitions theo tháng.

Một global partitioned index cũng có thể được partition theo range/list/hash theo cú pháp và giới hạn phiên bản Oracle. Chọn scheme theo cách truy vấn index và cách quản lý index, không mặc định sao chép scheme của table.

### 3.3. Mô hình global index

```text
TABLE SALES (partition theo SALE_DATE)
  P2026_01 ─┐
  P2026_02 ─┼────> GLOBAL INDEX
  P2026_03 ─┤       Gồm key trỏ tới ROWID
  P2026_04 ─┘       trên nhiều table partitions

Global partitioned index:
  G1, G2, G3 ... là các index partitions
  theo scheme riêng, không khớp table partition.
```

### 3.4. Ưu điểm

- Lookup theo khóa không chứa partition key có thể truy cập một index toàn cục thay vì probe mọi local index partition.
- Có thể hỗ trợ unique constraint trên khóa không bao gồm partition key, tùy loại constraint/index và quy tắc partitioned table.
- Global partitioned index có thể phân phối dung lượng và I/O giữa nhiều index partitions.
- Phù hợp với ứng dụng cần truy cập toàn bảng theo ID hoặc khóa nghiệp vụ.

### 3.5. Hạn chế

- Một thao tác DROP/TRUNCATE/SPLIT/MERGE/EXCHANGE trên table partition có thể phải bảo trì global index vì index tham chiếu dữ liệu từ nhiều table partitions.
- Nếu global index không được cập nhật theo cách phù hợp, index hoặc index partition có thể trở thành UNUSABLE.
- Bảo trì một table partition có thể tạo công việc trên index toàn cục, làm tăng I/O, redo, thời gian DDL hoặc tác động tới availability.
- Global partitioned index có scheme riêng nên việc bảo trì partition index cũng cần kế hoạch độc lập.

## 4. So sánh local và global index

| Tiêu chí | Local index | Global index |
| --- | --- | --- |
| Quan hệ với table partition | Căn chỉnh theo table partitions | Phạm vi nhiều table partitions |
| Phân vùng index | Tương ứng với table | Độc lập hoặc không partition |
| Drop/truncate một table partition | Thường chỉ tác động index partition tương ứng | Có thể phải cập nhật index toàn cục |
| Lookup không có partition key | Có thể phải probe nhiều index partitions | Thường thuận tiện hơn qua index toàn cục |
| Unique key không chứa partition key | Không thể bảo đảm uniqueness toàn bảng bằng local unique index | Có thể dùng global unique index/constraint khi được hỗ trợ |
| Quản trị partition | Thường đơn giản, cục bộ | Phức tạp hơn khi table partition thay đổi |
| Phù hợp | DW, vòng đời partition, truy vấn có partition key | Lookup toàn bảng, unique key độc lập partition key |

Không có quy tắc rằng mọi index của một bảng partitioned phải là local hoặc phải là global. Một thiết kế thường kết hợp:

- Local index cho truy vấn lọc theo partition key hoặc cho workload bảo trì partition thường xuyên.
- Global index cho lookup theo ID/key toàn bảng mà không chứa partition key.
- Không tạo index dư thừa nếu truy vấn có thể dùng partition pruning và local index hiệu quả.

## 5. Local prefixed và local nonprefixed index

### 5.1. Prefixed local index

Local index được gọi là prefixed nếu các cột partition key của table xuất hiện ở đầu (leftmost prefix) của key index theo thứ tự phù hợp.

Ví dụ table SALES partition theo SALE_DATE:

```sql
CREATE INDEX ix_sales_date_customer_l
ON sales (sale_date, customer_id)
LOCAL;
```

SALE_DATE là cột partition key và đứng đầu index key, nên đây là local prefixed index.

### 5.2. Nonprefixed local index

Nếu local index không bắt đầu bằng đầy đủ partition key, đó là local nonprefixed index:

```sql
CREATE INDEX ix_sales_customer_date_l
ON sales (customer_id, sale_date)
LOCAL;
```

CUSTOMER_ID đứng đầu, SALE_DATE đứng sau. Index vẫn local, nhưng key không có partition key ở vị trí prefix.

### 5.3. Ảnh hưởng tới truy vấn

Giả sử query:

```sql
SELECT *
FROM sales
WHERE sale_date = DATE '2026-03-15'
  AND customer_id = 1001;
```

Oracle có thể partition-prune theo SALE_DATE rồi dùng local index partition phù hợp. Prefixed index có thể hỗ trợ truy cập theo partition key và customer.

Nếu query chỉ có:

```sql
SELECT *
FROM sales
WHERE customer_id = 1001;
```

Oracle không biết partition tháng nào chứa hàng của CUSTOMER_ID. Với local nonprefixed index, có thể cần probe các local index partitions liên quan; global index thường thuận tiện hơn nếu lookup theo customer diễn ra thường xuyên trên toàn bộ dữ liệu. Nhưng nếu số partition nhỏ hoặc query có cách giới hạn khác, local index vẫn có thể hợp lý.

### 5.4. Prefixed không đồng nghĩa luôn nhanh hơn

Prefixed/nonprefixed mô tả vị trí partition key trong index key, không phải nhãn hiệu năng tuyệt đối. Cần xét:

- Query có predicate partition key không?
- Có bao nhiêu partition phải probe?
- Selectivity của cột đứng đầu index?
- Index clustering và số ROWID cần truy cập?
- Chi phí bảo trì và uniqueness?

Chọn thứ tự cột dựa vào predicate và mục tiêu nghiệp vụ, không chỉ dựa vào việc muốn index prefixed.

## 6. Unique index và partition key

Một câu hỏi thiết kế quan trọng là: làm sao bảo đảm một ID không xuất hiện ở hai partition khác nhau?

### 6.1. Local unique index phải chứa partition key

Giả sử SALES được partition theo SALE_DATE. Nếu tạo local unique index chỉ trên SALE_ID:

```sql
CREATE UNIQUE INDEX ux_sales_id_l
ON sales (sale_id)
LOCAL;
```

Oracle không thể bảo đảm SALE_ID duy nhất trên toàn bảng chỉ bằng các local index partitions, vì mỗi partition index chỉ kiểm tra uniqueness trong phạm vi partition của nó. Hai hàng có cùng SALE_ID có thể nằm ở hai table partitions khác nhau.

Vì vậy, local unique index trên partitioned table cần chứa đầy đủ partitioning key của table trong key index để uniqueness có thể được bảo đảm theo từng partition. Ví dụ:

```sql
CREATE UNIQUE INDEX ux_sales_date_id_l
ON sales (sale_date, sale_id)
LOCAL;
```

Index này bảo đảm tổ hợp SALE_DATE và SALE_ID duy nhất. Nó không bảo đảm SALE_ID riêng lẻ duy nhất nếu cùng SALE_ID xuất hiện ở hai ngày khác nhau.

### 6.2. Khi cần unique key không chứa partition key

Nếu nghiệp vụ yêu cầu SALE_ID duy nhất trên toàn bảng, kể cả khi cùng ID có thể rơi vào các partition ngày khác nhau, cần một global unique index/constraint phù hợp:

```sql
CREATE UNIQUE INDEX ux_sales_id_g
ON sales (sale_id);
```

Sau đó có thể tạo constraint dùng index:

```sql
ALTER TABLE sales
ADD CONSTRAINT uq_sales_id
UNIQUE (sale_id)
USING INDEX ux_sales_id_g;
```

Global unique index có thể khiến các thao tác bảo trì partition tốn công hơn vì index phải tiếp tục đại diện cho uniqueness trên toàn bảng. Đây là trade-off cần đưa vào thiết kế.

### 6.3. Global unique index và NULL

Quy tắc NULL của UNIQUE constraint vẫn áp dụng. Nếu ID bắt buộc phải có, khai báo NOT NULL riêng. Không dựa vào uniqueness để thay thế tính bắt buộc của dữ liệu.

### 6.4. Chọn partition key có ảnh hưởng tới constraint

Khi thiết kế partitioning, cân nhắc:

- Partition key có phải một phần của khóa nghiệp vụ không?
- Có cần uniqueness toàn bảng trên một cột không chứa partition key?
- Có thể dùng khóa ghép gồm partition key và ID theo đúng nghiệp vụ không?
- Global unique index có chấp nhận được về bảo trì và availability không?

Đừng thêm partition key vào UNIQUE chỉ để làm local unique index hợp lệ nếu điều đó làm thay đổi ý nghĩa nghiệp vụ. Nếu SALE_ID phải unique toàn cục, UNIQUE(SALE_DATE, SALE_ID) không thay thế được UNIQUE(SALE_ID).

## 7. Partition pruning và index access

### 7.1. Partition pruning

Partition pruning là việc Oracle loại các table partitions không cần thiết dựa trên predicate và partition metadata. Ví dụ:

```sql
SELECT SUM(amount)
FROM sales
WHERE sale_date >= DATE '2026-03-01'
  AND sale_date <  DATE '2026-04-01';
```

Nếu SALES range-partitioned theo SALE_DATE, Oracle có thể chỉ đọc partition tháng 3. Partition pruning hoạt động độc lập với việc bảng có local hay global index.

### 7.2. Index partition pruning

Với local index, partition của index được căn chỉnh với table partition. Khi Oracle prune table partition, nó cũng có thể chỉ cần truy cập local index partition tương ứng.

Với global index, index partitioning scheme độc lập với table partitioning. Global index access có thể tìm ROWID thuộc nhiều table partitions; sau đó Oracle truy cập các table partitions chứa hàng. Table partition pruning và global index partition pruning là hai cơ chế khác nhau.

### 7.3. Query không có partition key

```sql
SELECT sale_date, amount
FROM sales
WHERE sale_id = :sale_id;
```

Nếu chỉ có local index trên SALE_ID, Oracle có thể cần truy cập nhiều local index partitions vì không biết partition ngày. Global index trên SALE_ID có thể tìm ROWID toàn bảng trực tiếp hơn.

Nếu query có cả SALE_DATE và SALE_ID, local index có thể chỉ cần một index partition:

```sql
SELECT sale_date, amount
FROM sales
WHERE sale_date = :sale_date
  AND sale_id = :sale_id;
```

### 7.4. Không nhầm partition pruning với index skip scan

Partition pruning loại table/index partitions dựa trên partition key. Index skip scan là kỹ thuật truy cập B-tree composite index khi predicate không có cột leading trong một số trường hợp. Hai kỹ thuật khác nhau; không giả định skip scan thay thế được thiết kế local/global.

### 7.5. Đọc plan

Trong execution plan, có thể gặp:

| Operation | Ý nghĩa |
| --- | --- |
| PARTITION RANGE SINGLE | Chỉ một range partition được chọn |
| PARTITION RANGE ITERATOR | Duyệt một tập partition được chọn |
| PARTITION RANGE ALL | Không prune, truy cập toàn bộ range partitions |
| PARTITION LIST SINGLE | Chọn một list partition |
| PARTITION HASH SINGLE | Chọn một hash partition nếu điều kiện đủ |
| INDEX RANGE SCAN | Quét phạm vi key của index |
| INDEX UNIQUE SCAN | Tìm một key unique |
| TABLE ACCESS BY LOCAL INDEX ROWID | Truy cập table qua local index ROWID |

Operation cụ thể phụ thuộc kiểu partition, phiên bản và optimizer transformation. Dùng DBMS_XPLAN để xem PSTART/PSTOP và các partition được truy cập; với dynamic pruning, giá trị có thể được hiển thị là KEY hoặc dạng runtime khác.

## 8. Tạo local và global index

### 8.1. Tạo local nonunique index

```sql
CREATE INDEX ix_sales_customer_l
ON sales (customer_id)
LOCAL;
```

Oracle tạo index partitions tương ứng với table partitions.

### 8.2. Tạo local index với tên partition index

Có thể đặt tên và tablespace cho từng index partition theo cú pháp CREATE INDEX PARTITION:

```sql
CREATE INDEX ix_sales_date_customer_l
ON sales (sale_date, customer_id)
LOCAL (
    PARTITION pidx_2026_01 TABLESPACE idx_2026_01,
    PARTITION pidx_2026_02 TABLESPACE idx_2026_02,
    PARTITION pidx_2026_03 TABLESPACE idx_2026_03
);
```

Danh sách partition index phải tương ứng với cấu trúc table partition tại thời điểm tạo. Cú pháp và cách quản lý partition được thêm sau đó cần được kiểm tra theo DDL và phiên bản đang dùng. Nếu không cần đặt tên/tablespace riêng, để Oracle quản lý partition index thường đơn giản hơn.

### 8.3. Tạo global nonpartitioned index

```sql
CREATE INDEX ix_sales_sale_id_g
ON sales (sale_id);
```

Trên một partitioned table, index không khai báo LOCAL và không có global partitioning clause là global nonpartitioned index.

### 8.4. Tạo global partitioned index

Ví dụ hash partitioned:

```sql
CREATE INDEX ix_sales_customer_g
ON sales (customer_id)
GLOBAL PARTITION BY HASH (customer_id)
PARTITIONS 8;
```

Ví dụ range partitioned:

```sql
CREATE INDEX ix_sales_id_range_g
ON sales (sale_id)
GLOBAL PARTITION BY RANGE (sale_id) (
    PARTITION gip_1 VALUES LESS THAN (1000000),
    PARTITION gip_2 VALUES LESS THAN (2000000),
    PARTITION gip_max VALUES LESS THAN (MAXVALUE)
);
```

Index partitioning key và boundary ở đây là của index, không phải table partitioning key SALE_DATE. Hãy chọn scheme phù hợp với phân bố index key và truy vấn.

### 8.5. Kiểm tra locality

```sql
SELECT
    index_name,
    locality,
    alignment,
    partitioning_type,
    partition_count
FROM user_part_indexes
WHERE table_name = 'SALES'
ORDER BY index_name;
```

USER_PART_INDEXES/ALL_PART_INDEXES/DBA_PART_INDEXES mô tả index partitioned và locality. Global nonpartitioned index không có index partition metadata như local/global partitioned index; kiểm tra thêm USER_INDEXES.

## 9. Tác động của các thao tác partition maintenance

Điều cần xác định sau mỗi DDL là:

1. Table partition nào bị thêm, xóa, làm rỗng, di chuyển hoặc thay đổi ranh giới?
2. Local index partitions tương ứng được duy trì ra sao?
3. Global index có phải sửa entry/ROWID không?
4. Index hoặc index partition nào có thể thành UNUSABLE?
5. Có cần UPDATE INDEXES/UPDATE GLOBAL INDEXES, rebuild hoặc thu thập statistics không?

### 9.1. Bảng tổng quan

| Thao tác | Local index | Global index |
| --- | --- | --- |
| ADD PARTITION | Tạo/duy trì partition index tương ứng | Thường không cần thay đổi key hiện có; kiểm tra theo DDL cụ thể |
| DROP PARTITION | Xóa phần index partition tương ứng | Cần duy trì global entries hoặc xử lý trạng thái index |
| TRUNCATE PARTITION | Làm rỗng phần index partition tương ứng | Cần duy trì global entries hoặc xử lý trạng thái index |
| MOVE PARTITION | Có thể làm local index partition UNUSABLE nếu không duy trì index | Có thể cần cập nhật/rebuild global index |
| SPLIT PARTITION | Local index partitions được split/duy trì theo table | Global index cần bảo trì theo tùy chọn DDL |
| MERGE PARTITIONS | Local index partitions được merge tương ứng | Global index cần bảo trì theo tùy chọn DDL |
| EXCHANGE PARTITION | Cần xử lý index của bảng trao đổi và local index | Global index có thể cần cập nhật; xem INCLUDING/UPDATE INDEXES |

Bảng này là định hướng, không thay thế tài liệu syntax theo phiên bản. Một số thao tác có cơ chế asynchronous global index maintenance hoặc khác biệt giữa DDL online/offline. Sau khi chạy, kiểm tra index status thay vì suy luận chỉ từ câu DDL thành công.

## 10. DROP PARTITION và global index

### 10.1. DROP PARTITION

Ví dụ xóa partition cũ:

```sql
ALTER TABLE sales
DROP PARTITION p2025_01;
```

Table partition bị loại bỏ. Local index partition tương ứng cũng được loại bỏ/duy trì theo cấu trúc local. Global index có thể cần cập nhật để loại các ROWID thuộc partition vừa drop.

### 10.2. Duy trì global index

Trong các phiên bản và trường hợp hỗ trợ, có thể chỉ định:

```sql
ALTER TABLE sales
DROP PARTITION p2025_01
UPDATE INDEXES;
```

Một số tài liệu/phiên bản hoặc cú pháp cụ thể dùng UPDATE GLOBAL INDEXES. Hãy xác nhận từ Oracle SQL Language Reference đúng release. Tùy chọn cập nhật index có thể yêu cầu công việc bảo trì global index ngay trong DDL hoặc sử dụng cơ chế asynchronous maintenance của release.

Nếu không dùng tùy chọn duy trì global index trong một trường hợp mà Oracle không tự bảo trì, global index hoặc index partitions có thể chuyển sang UNUSABLE. Truy vấn dùng index đó sẽ không thể sử dụng access path như trước; tùy trạng thái và cấu hình, DML tiếp theo có thể bị từ chối hoặc cần rebuild trước.

### 10.3. Asynchronous global index maintenance

Oracle Database 12c trở lên có hỗ trợ asynchronous global index maintenance cho một số thao tác DROP/TRUNCATE partition. Thay vì xóa ngay mọi index entry, Oracle có thể đánh dấu metadata và trì hoãn dọn entry cũ tới thời điểm thích hợp. Điều này giảm thời gian DDL, nhưng không có nghĩa index entry cũ biến mất ngay lập tức hoặc không cần cleanup.

Hành vi cụ thể phụ thuộc release, loại index, thao tác và clause được dùng. Đừng suy ra mọi DROP PARTITION trên mọi phiên bản đều tự duy trì global index. Kiểm tra documentation của release, trạng thái index sau DDL và công cụ cleanup phù hợp.

### 10.4. Khi nào dùng DROP PARTITION?

DROP PARTITION phù hợp khi loại bỏ hẳn một khoảng dữ liệu, ví dụ purge tháng đã hết retention. So với DELETE hàng triệu dòng, DDL partition có thể nhanh hơn và ít tạo undo/redo hơn cho dữ liệu bị loại, nhưng vẫn cần đánh giá:

- Foreign key constraints và dependency.
- Global indexes.
- Materialized views và statistics.
- Backup/archiving/retention.
- DDL locking và cửa sổ vận hành.

DROP PARTITION là DDL có implicit commit; không thể rollback như một DELETE chưa commit.

## 11. TRUNCATE PARTITION

### 11.1. TRUNCATE khác DROP

- DROP PARTITION loại bỏ partition và metadata của partition khỏi bảng.
- TRUNCATE PARTITION giữ partition trong bảng nhưng xóa toàn bộ hàng bên trong.

Ví dụ:

```sql
ALTER TABLE sales
TRUNCATE PARTITION p2026_01;
```

Local index partition tương ứng được làm rỗng theo table partition. Global index cần được duy trì để các entry trỏ tới hàng đã truncate không còn gây kết quả sai.

### 11.2. Duy trì index

Ví dụ cú pháp thường dùng:

```sql
ALTER TABLE sales
TRUNCATE PARTITION p2026_01
UPDATE INDEXES;
```

Ở release/cú pháp khác, tài liệu có thể chỉ rõ UPDATE GLOBAL INDEXES. Oracle 12c trở lên hỗ trợ asynchronous global index maintenance cho một số thao tác truncate/drop; tùy chọn và hành vi phải xác nhận theo release. Nếu global index không được duy trì và trở thành UNUSABLE, cần xử lý index trước khi dựa vào nó.

### 11.3. Khi nào dùng?

TRUNCATE PARTITION hữu ích khi cần giữ khung partition cho tháng/quý nhưng làm rỗng dữ liệu, ví dụ nạp lại partition sau khi chạy ETL lỗi. Vì đây là DDL, thao tác có implicit commit và không thể rollback như DELETE. Hãy xác nhận dữ liệu đã được archive hoặc có thể nạp lại trước khi chạy.

## 12. MOVE PARTITION

### 12.1. Mục đích

MOVE PARTITION chuyển segment của một table partition, thường để đổi tablespace, nén dữ liệu, thay đổi thuộc tính lưu trữ hoặc tổ chức lại segment.

Ví dụ:

```sql
ALTER TABLE sales
MOVE PARTITION p2026_03
TABLESPACE sales_data_2026;
```

Việc di chuyển partition có thể làm thay đổi ROWID của các hàng. Index chứa ROWID cần được duy trì hoặc rebuild; local index partition tương ứng và global index đều cần được xem xét.

### 12.2. Duy trì index trong MOVE

Một dạng cú pháp phổ biến:

```sql
ALTER TABLE sales
MOVE PARTITION p2026_03
TABLESPACE sales_data_2026
UPDATE INDEXES;
```

Nếu không dùng tùy chọn duy trì index được hỗ trợ trong release, local index partition tương ứng hoặc global index có thể trở thành UNUSABLE. Tác động cụ thể phụ thuộc loại index, phiên bản và hình thức MOVE (online/offline, compression, tablespace, partition/subpartition).

### 12.3. Rebuild local index partition sau MOVE

Nếu index partition trở thành UNUSABLE, xác định tên index partition rồi rebuild:

```sql
ALTER INDEX ix_sales_customer_l
REBUILD PARTITION pidx_2026_03;
```

Tên partition index có thể khác tên table partition. Hãy tra USER_IND_PARTITIONS thay vì giả định tên giống nhau.

### 12.4. MOVE và availability

MOVE PARTITION là DDL có thể cần khóa metadata hoặc có ảnh hưởng tới truy cập tùy hình thức và release. Nếu yêu cầu availability cao, xem xét cú pháp ONLINE được hỗ trợ, kiểm tra giới hạn với loại partition/index và thử trên môi trường tương đương. ONLINE không có nghĩa không phát sinh khóa hoặc không cần thêm tài nguyên.

## 13. SPLIT PARTITION

### 13.1. Mục đích

SPLIT PARTITION chia một partition thành hai partition mới. Thường dùng khi partition MAXVALUE hoặc partition lớn cần tách theo ranh giới mới.

Ví dụ partition P_FUTURE đang chứa các ngày từ tháng 5 trở đi. Tách tháng 5 khỏi phần tương lai:

```sql
ALTER TABLE sales
SPLIT PARTITION p_future
AT (DATE '2026-06-01')
INTO (
    PARTITION p2026_05,
    PARTITION p_future
);
```

Oracle phân chia hàng theo partition bound. Local index partitions cũng phải được chia/duy trì theo hai partition mới.

### 13.2. Global index

SPLIT thay đổi ROWID/partition placement của các hàng liên quan và có thể cần bảo trì global index. Ví dụ dùng clause:

```sql
ALTER TABLE sales
SPLIT PARTITION p_future
AT (DATE '2026-06-01')
INTO (
    PARTITION p2026_05,
    PARTITION p_future
)
UPDATE INDEXES;
```

Khả năng và cách viết clause phụ thuộc release và loại index. Kiểm tra global index status sau split. Với bảng lớn, công việc duy trì index có thể đáng kể và cần tính vào cửa sổ bảo trì.

### 13.3. Split partition có thể tốn tài nguyên

Split có thể cần đọc/di chuyển dữ liệu trong partition, cập nhật local index partitions và duy trì global index. Không xem split là thao tác chỉ đổi metadata trong mọi trường hợp. Kiểm tra kích thước partition, compression, tablespace, undo/redo, parallelism và thời gian khóa.

## 14. MERGE PARTITIONS

### 14.1. Mục đích

MERGE PARTITIONS gộp các partition liền kề thành một partition mới. Thường dùng khi nhiều partition nhỏ cần gộp hoặc thay đổi chiến lược quản lý dữ liệu.

Ví dụ:

```sql
ALTER TABLE sales
MERGE PARTITIONS p2026_01, p2026_02
INTO PARTITION p2026_q1;
```

Hai partition nguồn bị thay thế bằng partition đích. Local index partitions tương ứng được merge theo table.

### 14.2. Duy trì global index

Ví dụ:

```sql
ALTER TABLE sales
MERGE PARTITIONS p2026_01, p2026_02
INTO PARTITION p2026_q1
UPDATE INDEXES;
```

Global index cần được duy trì theo quy tắc của thao tác và release. Nếu không, index hoặc partition của global index có thể trở thành UNUSABLE. Sau MERGE, kiểm tra trạng thái index và xác nhận query plan.

### 14.3. Lưu ý

- Các partition cần merge phải phù hợp với quy tắc của partitioning method; với range partition thường phải liền kề.
- Xác nhận partition name đích chưa tồn tại.
- Kiểm tra tablespace, compression và storage attributes của partition mới.
- Đánh giá tác động tới local/global index và statistics.
- Xác nhận dữ liệu sau merge vẫn nằm trong bound đúng.

## 15. EXCHANGE PARTITION

### 15.1. Khái niệm

EXCHANGE PARTITION hoán đổi segment của một table partition với một nonpartitioned table có cấu trúc tương thích. Đây là kỹ thuật phổ biến để nạp dữ liệu lớn vào kho dữ liệu: nạp và kiểm tra dữ liệu ở staging trước, sau đó exchange vào partition đích.

Ví dụ:

```sql
ALTER TABLE sales
EXCHANGE PARTITION p2026_04
WITH TABLE sales_stage;
```

Sau exchange, dữ liệu trước đó của partition nằm trong bảng staging, còn dữ liệu của staging nằm trong partition. Đây là thao tác metadata/segment exchange nhanh hơn việc INSERT từng hàng trong nhiều tình huống, nhưng các điều kiện tương thích và index vẫn cần được xử lý.

### 15.2. Điều kiện tương thích

Bảng staging cần có cấu trúc cột, kiểu dữ liệu và các thuộc tính phù hợp với partition được exchange. Các constraint, partition key values và index cũng cần được xem xét. Nếu dùng validation, Oracle kiểm tra hàng staging có phù hợp partition bound hay không; nếu dùng WITHOUT VALIDATION, trách nhiệm bảo đảm dữ liệu đúng partition thuộc quy trình ETL.

Không dùng WITHOUT VALIDATION chỉ để tăng tốc nếu chưa có bước kiểm tra dữ liệu tương đương. Một hàng có SALE_DATE nằm ngoài bound của partition có thể khiến dữ liệu sai logic khi exchange không validate.

### 15.3. INCLUDING INDEXES

Nếu muốn trao đổi cả local index partition với index tương ứng trên staging table, có thể dùng INCLUDING INDEXES khi cấu trúc index phù hợp:

```sql
ALTER TABLE sales
EXCHANGE PARTITION p2026_04
WITH TABLE sales_stage
INCLUDING INDEXES;
```

Nếu không exchange index tương ứng, local index partition có thể cần được rebuild hoặc có thể trở thành UNUSABLE tùy điều kiện và clause. Staging table cần có index tương ứng về cấu trúc cho thao tác INCLUDING INDEXES.

### 15.4. UPDATE GLOBAL INDEXES

Global index tham chiếu dữ liệu của nhiều table partitions. Khi exchange partition, cần cập nhật global index để nó trỏ tới ROWID phù hợp. Ví dụ:

```sql
ALTER TABLE sales
EXCHANGE PARTITION p2026_04
WITH TABLE sales_stage
INCLUDING INDEXES
WITHOUT VALIDATION
UPDATE GLOBAL INDEXES;
```

Đây là mẫu thường gặp; cú pháp, khả năng asynchronous maintenance và hỗ trợ online phụ thuộc release. Xác nhận đúng Oracle SQL Language Reference trước khi dùng.

### 15.5. Quy trình ETL exchange partition

Một quy trình an toàn thường là:

1. Tạo/chuẩn bị staging table tương thích với partition đích.
2. Nạp dữ liệu vào staging.
3. Kiểm tra row count, duplicate, NULL, domain và partition-key bounds.
4. Thu thập statistics cho staging nếu quy trình cần.
5. Chuẩn bị index tương ứng nếu dùng INCLUDING INDEXES.
6. Exchange partition với tùy chọn validation/index phù hợp.
7. Kiểm tra local/global index status.
8. Kiểm tra số hàng và truy vấn đại diện trên partition mới.
9. Lưu dữ liệu cũ đang nằm trong staging theo chính sách retention hoặc truncate staging sau khi xác nhận.

EXCHANGE PARTITION là DDL và có implicit commit. Cần kế hoạch rollback/đổi ngược segment exchange nếu bước xác minh thất bại; không thể dùng ROLLBACK thông thường để hoàn tác DDL.

## 16. Kiểm tra và khôi phục index UNUSABLE

### 16.1. Vì sao index có thể thành UNUSABLE?

Một số thao tác partition maintenance có thể đánh dấu index hoặc index partition là UNUSABLE nếu Oracle không duy trì index theo cách được yêu cầu/hỗ trợ. Tình huống này thường gặp khi:

- MOVE PARTITION không dùng tùy chọn duy trì index thích hợp.
- SPLIT/MERGE hoặc EXCHANGE làm thay đổi ROWID/partition contents mà global index không được cập nhật.
- Load hoặc thao tác partition được thực hiện với tùy chọn làm index partition unusable.
- Một index partition được đánh dấu unusable thủ công hoặc DDL thất bại giữa quy trình bảo trì.

Index UNUSABLE không còn là access path hợp lệ cho optimizer. Một số thao tác DML có thể báo lỗi nếu cần duy trì index unusable, tùy loại index và cấu hình. Không bỏ qua trạng thái này chỉ vì câu SELECT vẫn có thể chạy bằng full table scan.

### 16.2. Kiểm tra USER_INDEXES

```sql
SELECT
    index_name,
    table_name,
    status,
    visibility,
    partitioned,
    uniqueness
FROM user_indexes
WHERE table_name = 'SALES'
ORDER BY index_name;
```

USER_INDEXES cung cấp trạng thái tổng thể cho index. Với partitioned index, cần kiểm tra từng index partition; trạng thái tổng thể có thể không cho biết chính xác partition nào cần rebuild.

### 16.3. Kiểm tra USER_IND_PARTITIONS

```sql
SELECT
    index_name,
    partition_name,
    status,
    tablespace_name
FROM user_ind_partitions
WHERE index_name IN (
    SELECT index_name
    FROM user_indexes
    WHERE table_name = 'SALES'
)
ORDER BY index_name, partition_position;
```

Với index subpartitioned, xem USER_IND_SUBPARTITIONS/ALL_IND_SUBPARTITIONS để kiểm tra từng subpartition. Có thể dùng ALL_ hoặc DBA_ views khi cần phạm vi rộng hơn và có quyền.

### 16.4. Rebuild một local index partition

```sql
ALTER INDEX ix_sales_customer_l
REBUILD PARTITION pidx_2026_03;
```

Rebuild chỉ partition được chỉ định. Tên pidx_2026_03 là ví dụ; lấy đúng tên từ USER_IND_PARTITIONS.

### 16.5. Rebuild một global index partition

Với global partitioned index:

```sql
ALTER INDEX ix_sales_customer_g
REBUILD PARTITION sys_p123;
```

Tên partition cần lấy từ dictionary. Global partitioned index partition không nhất thiết có tên tương ứng với table partition.

### 16.6. Rebuild global nonpartitioned index

```sql
ALTER INDEX ix_sales_sale_id_g
REBUILD;
```

Đây là rebuild toàn bộ global nonpartitioned index. Với index lớn, thao tác có thể cần đáng kể I/O và temporary space; lên lịch phù hợp.

### 16.7. Rebuild không thay thế việc điều tra nguyên nhân

Trước khi rebuild, xác định:

- Index nào unusable: local, global partitioned hay global nonpartitioned?
- Partition/subpartition nào bị ảnh hưởng?
- DDL nào làm index unusable?
- Có thể duy trì index bằng clause trong lần chạy tiếp theo không?
- Rebuild cần tablespace, TEMP, redo và thời gian bao nhiêu?
- Có cần thu thập statistics sau rebuild?

Nếu thao tác partition tiếp theo lại làm index unusable, rebuild đơn thuần chỉ chữa triệu chứng. Cần sửa quy trình DDL/ETL.

## 17. Statistics và execution plan sau bảo trì partition

### 17.1. Vì sao cần statistics?

Partition maintenance có thể thay đổi số hàng, phân bố dữ liệu và mức độ skew trong partition. Optimizer cần statistics phù hợp để ước lượng cardinality và chọn access path.

Sau load, exchange, split, merge, truncate hoặc drop, hãy xác định statistics nào cần cập nhật:

- Table-level statistics.
- Partition-level statistics.
- Index statistics.
- Global statistics hoặc synopses khi dùng incremental statistics.

Không phải mọi DDL đều yêu cầu gather toàn bảng ngay lập tức. Với bảng rất lớn, dùng chiến lược incremental statistics và partition-level gathering theo thiết kế của DBA.

### 17.2. Thu thập statistics cho một partition

Ví dụ:

```sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname          => USER,
        tabname          => 'SALES',
        partname         => 'P2026_03',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        cascade          => TRUE
    );
END;
/
```

CASCADE có thể thu thập statistics cho index liên quan theo cách DBMS_STATS hỗ trợ. Trong production, tuân theo chính sách stats hiện tại; không tự gather lại toàn bảng khi chỉ một partition thay đổi nếu chiến lược incremental đã được cấu hình.

### 17.3. Xem execution plan

```sql
EXPLAIN PLAN FOR
SELECT SUM(amount)
FROM sales
WHERE sale_date >= DATE '2026-03-01'
  AND sale_date <  DATE '2026-04-01'
  AND customer_id = 1001;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
```

Kiểm tra:

- PSTART/PSTOP cho biết partition được chọn hay toàn bộ.
- Access path dùng local hay global index.
- E-Rows có phù hợp với phân bố thực tế không.
- Có full scan hoặc table access by ROWID không.
- Plan có thay đổi sau maintenance/statistics không.

### 17.4. Xem actual rows

Trong môi trường thử nghiệm:

```sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       SUM(amount)
FROM sales
WHERE sale_date >= DATE '2026-03-01'
  AND sale_date <  DATE '2026-04-01'
  AND customer_id = 1001;

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PARTITION'
    )
);
```

Actual row-source statistics giúp so sánh E-Rows với A-Rows. Nếu estimate lệch nhiều, xem histogram, correlation, partition stats và bind variable peeking/adaptive behavior theo phiên bản. Không dùng một lần chạy đơn lẻ làm kết luận cho toàn workload.

## 18. Bài thực hành: local/global và partition maintenance

Các ví dụ sau dành cho schema lab. Cần quyền tạo bảng partitioned, index và sequence nếu muốn chạy toàn bộ.

### 18.1. Tạo bảng SALES partition theo tháng

```sql
CREATE TABLE lab_sales_part (
    sale_id      NUMBER(12) NOT NULL,
    sale_date    DATE NOT NULL,
    customer_id  NUMBER(12) NOT NULL,
    channel      VARCHAR2(20),
    amount       NUMBER(12, 2)
)
PARTITION BY RANGE (sale_date) (
    PARTITION p2026_01 VALUES LESS THAN (DATE '2026-02-01'),
    PARTITION p2026_02 VALUES LESS THAN (DATE '2026-03-01'),
    PARTITION p2026_03 VALUES LESS THAN (DATE '2026-04-01'),
    PARTITION p_future VALUES LESS THAN (MAXVALUE)
);
```

Để giữ ví dụ đơn giản, bảng chưa khai báo primary key. Nếu muốn SALE_ID unique toàn bảng, thêm global unique index/constraint sau khi nạp dữ liệu; nếu chỉ cần unique theo ngày, dùng khóa ghép theo đúng quy tắc nghiệp vụ.

### 18.2. Nạp dữ liệu

```sql
INSERT INTO lab_sales_part (
    sale_id, sale_date, customer_id, channel, amount
)
SELECT
    LEVEL,
    DATE '2026-01-01' + MOD(LEVEL, 90),
    MOD(LEVEL, 1000) + 1,
    CASE MOD(LEVEL, 3)
        WHEN 0 THEN 'WEB'
        WHEN 1 THEN 'STORE'
        ELSE 'PARTNER'
    END,
    MOD(LEVEL * 19, 50000) / 100
FROM dual
CONNECT BY LEVEL <= 100000;

COMMIT;
```

Dữ liệu được phân bố vào các partition tháng 1–3. Partition P_FUTURE có thể rỗng.

### 18.3. Tạo local index

```sql
CREATE INDEX ix_lsp_customer_local
ON lab_sales_part (sale_date, customer_id)
LOCAL;
```

Index là local prefixed vì SALE_DATE là partition key và đứng đầu index key.

### 18.4. Tạo global nonpartitioned index

```sql
CREATE INDEX ix_lsp_sale_global
ON lab_sales_part (sale_id);
```

Index này hỗ trợ lookup SALE_ID trên toàn bảng mà không cần biết SALE_DATE.

### 18.5. Kiểm tra locality và partition status

```sql
SELECT index_name, locality, alignment, partitioning_type
FROM user_part_indexes
WHERE table_name = 'LAB_SALES_PART'
ORDER BY index_name;

SELECT index_name, status, partitioned
FROM user_indexes
WHERE table_name = 'LAB_SALES_PART'
ORDER BY index_name;

SELECT index_name, partition_name, status
FROM user_ind_partitions
WHERE index_name = 'IX_LSP_CUSTOMER_LOCAL'
ORDER BY partition_position;
```

Đối chiếu: local index có metadata partition; global nonpartitioned index không có các index partitions tương ứng.

### 18.6. Quan sát partition pruning

```sql
EXPLAIN PLAN FOR
SELECT SUM(amount)
FROM lab_sales_part
WHERE sale_date >= DATE '2026-02-01'
  AND sale_date <  DATE '2026-03-01'
  AND customer_id = 100;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
```

Xem PSTART/PSTOP và xác nhận Oracle có thể chọn partition P2026_02. So sánh query chỉ lọc CUSTOMER_ID để quan sát global index có thể phục vụ lookup mà không cần biết tháng.

### 18.7. Thêm partition

```sql
ALTER TABLE lab_sales_part
ADD PARTITION p2026_04
VALUES LESS THAN (DATE '2026-05-01');
```

Kiểm tra local index partition mới:

```sql
SELECT index_name, partition_name, status
FROM user_ind_partitions
WHERE index_name = 'IX_LSP_CUSTOMER_LOCAL'
ORDER BY partition_position;
```

### 18.8. Truncate một partition trong lab

Chỉ chạy sau khi xác nhận partition test có thể làm rỗng:

```sql
ALTER TABLE lab_sales_part
TRUNCATE PARTITION p2026_01
UPDATE INDEXES;
```

Kiểm tra số hàng trong partition và trạng thái global/local index sau thao tác. Trên release có cú pháp hoặc behavior khác, xác nhận clause UPDATE INDEXES theo tài liệu tương ứng.

### 18.9. Rebuild một local index partition

Lấy tên index partition từ USER_IND_PARTITIONS, rồi:

```sql
ALTER INDEX ix_lsp_customer_local
REBUILD PARTITION <index_partition_name>;
```

Thay placeholder bằng tên thật trong dictionary. Không giả định index partition có cùng tên với table partition.

### 18.10. Dọn schema lab

Sau khi hoàn thành và không cần dữ liệu nữa:

```sql
DROP TABLE lab_sales_part PURGE;
```

DROP TABLE xóa các index thuộc bảng. Chỉ chạy trong schema lab và sau khi xác nhận không còn bài thực hành khác dùng bảng này.

## 19. Các lỗi và bẫy thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Local unique index bị từ chối | Khóa unique thiếu partition key | Đưa đầy đủ partition key vào local unique key hoặc dùng global unique index |
| Lookup theo ID phải quét nhiều index partitions | Query không có partition key và index là local | Cân nhắc global index hoặc bổ sung predicate partition key |
| Index partition UNUSABLE sau MOVE | MOVE không duy trì index hoặc tùy chọn không phù hợp | Rebuild partition hoặc chạy lại DDL với clause đúng release |
| Global index UNUSABLE sau DROP/TRUNCATE | Global index không được duy trì theo cơ chế của release | Dùng UPDATE INDEXES/UPDATE GLOBAL INDEXES hoặc rebuild |
| EXCHANGE làm local index partition unusable | Index staging không tương ứng hoặc thiếu INCLUDING INDEXES | Chuẩn bị index staging và kiểm tra exchange clause |
| Query đọc quá nhiều partition | Predicate không cho phép pruning hoặc dùng hàm trên partition key | Viết predicate sargable, kiểm tra implicit conversion và plan |
| Plan không dùng local index | Full scan rẻ hơn hoặc stats/selectivity khác dự kiến | So sánh cost, E-Rows/A-Rows, clustering và workload |
| Global index maintenance kéo dài DDL | Index lớn, nhiều entry cần cập nhật | Lên lịch, dùng cơ chế async nếu release hỗ trợ, benchmark và theo dõi cleanup |
| Local index partition name không khớp table partition | Tên index partition do Oracle/DDL quản lý độc lập | Tra USER_IND_PARTITIONS |
| Index status tổng thể gây nhầm | Index partitioned có trạng thái theo từng partition | Kiểm tra USER_IND_PARTITIONS/USER_IND_SUBPARTITIONS |
| Sau ETL query plan thay đổi | Statistics cũ hoặc phân bố mới | Thu thập partition/global stats theo chính sách |
| Global unique constraint làm purge phức tạp | Uniqueness toàn bảng cần index toàn cục | Đưa chi phí bảo trì vào thiết kế partition key và constraint |

## 20. Nguyên tắc thực hành tốt

1. **Thiết kế partition và index cùng nhau.** Partition key ảnh hưởng pruning, local uniqueness và chi phí bảo trì.
2. **Dùng local index cho vòng đời dữ liệu theo partition.** Nó thường làm DROP/TRUNCATE/EXCHANGE cục bộ hơn.
3. **Dùng global index khi lookup toàn bảng thực sự cần.** Đặc biệt khi truy vấn không có partition key.
4. **Không dùng local unique index để giả lập global uniqueness.** Khóa local phải chứa partition key; nếu business key unique toàn bảng, dùng giải pháp phù hợp.
5. **Phân biệt local prefixed và nonprefixed.** Thứ tự cột ảnh hưởng khả năng truy cập và số partition index cần probe.
6. **Kiểm tra tác động từng DDL.** DROP, TRUNCATE, MOVE, SPLIT, MERGE và EXCHANGE không có cùng tác động index.
7. **Dùng UPDATE INDEXES/UPDATE GLOBAL INDEXES đúng release.** Đừng dựa vào cú pháp từ phiên bản khác.
8. **Kiểm tra trạng thái index sau maintenance.** Xem cả index-level và partition/subpartition-level status.
9. **Rebuild đúng phạm vi.** Chỉ rebuild partition bị ảnh hưởng nếu đủ; tránh rebuild toàn index không cần thiết.
10. **Quản lý global index maintenance như một phần ETL.** Tính I/O, redo, thời gian DDL và availability.
11. **Validate staging trước EXCHANGE.** Không bỏ validation nếu chưa có bước kiểm tra partition bound tương đương.
12. **Cập nhật statistics theo partition.** Dùng incremental stats nếu kiến trúc và phiên bản hỗ trợ.
13. **Đọc PSTART/PSTOP và actual rows.** Xác nhận partition pruning thực sự diễn ra.
14. **Thử DDL trên môi trường tương đương.** DDL có implicit commit và có thể tác động dữ liệu/availability.

## 21. Câu hỏi tự kiểm tra

1. Local index khác global index ở quan hệ với table partitions như thế nào?
2. Global nonpartitioned index khác global partitioned index ở điểm nào?
3. Vì sao local index thường dễ bảo trì khi DROP một table partition?
4. Khi query không có partition key, local index có thể phải làm gì?
5. Local prefixed index được xác định dựa trên thứ tự cột nào?
6. Local nonprefixed index có thể hữu ích trong trường hợp nào?
7. Vì sao local unique index phải chứa đầy đủ partition key?
8. Khi cần SALE_ID unique toàn bảng nhưng table partition theo SALE_DATE, lựa chọn index nào phù hợp?
9. Partition pruning khác index partition pruning ra sao?
10. PSTART/PSTOP trong execution plan giúp kiểm tra điều gì?
11. DROP PARTITION khác TRUNCATE PARTITION như thế nào?
12. Vì sao MOVE PARTITION có thể làm index partition UNUSABLE?
13. SPLIT và MERGE PARTITIONS tác động local/global index ra sao?
14. EXCHANGE PARTITION dùng staging table để giải quyết bài toán nào?
15. INCLUDING INDEXES và UPDATE GLOBAL INDEXES có vai trò gì trong EXCHANGE?
16. Khi nào cần rebuild local index partition thay vì rebuild toàn index?
17. USER_PART_INDEXES và USER_IND_PARTITIONS cung cấp thông tin khác nhau như thế nào?
18. Vì sao phải kiểm tra statistics sau khi nạp hoặc exchange partition?
19. Asynchronous global index maintenance giúp gì và vì sao vẫn cần cleanup/kiểm tra?
20. Những bước nào cần thực hiện trước khi chạy DROP/TRUNCATE/MOVE trên production?

## 22. Mô hình ghi nhớ

```text
PARTITIONED TABLE
       |
       +-----------------------------+
       |                             |
       v                             v
   LOCAL INDEX                   GLOBAL INDEX
   Căn chỉnh table partition     Phạm vi nhiều table partitions
       |                             |
       v                             v
   Mỗi table partition           Nonpartitioned hoặc
   có index partition tương ứng  partitioned theo scheme riêng
       |                             |
       v                             v
   Dễ bảo trì cục bộ             Lookup toàn bảng thuận tiện
   Hợp với partition lifecycle   Nhưng DDL partition phải bảo trì
                                 global entries

PARTITION MAINTENANCE
  ADD / DROP / TRUNCATE / MOVE
  SPLIT / MERGE / EXCHANGE
       |
       v
  Kiểm tra local index partitions
  Kiểm tra global index status
  UPDATE INDEXES nếu phù hợp
  REBUILD nếu UNUSABLE
  GATHER STATS và kiểm tra plan
```

**Điểm cần nhớ:** local index đi cùng vòng đời từng table partition; global index phục vụ truy cập trên nhiều partition nhưng khiến một số thao tác partition maintenance cần thêm công việc cập nhật hoặc rebuild. Hãy chọn loại index theo predicate, partition key và yêu cầu uniqueness; sau mọi DDL, kiểm tra index status, partition pruning và execution plan trước khi kết luận hệ thống đã sẵn sàng.
