# Trạng thái UNUSABLE, REBUILD, COALESCE và chi phí bảo trì chỉ mục trong Oracle

## 1. Vì sao cần theo dõi trạng thái index?

Index giúp Oracle tìm row nhanh hơn mà không phải quét toàn bộ bảng trong nhiều trường hợp. Nhưng index cũng là một cấu trúc dữ liệu vật lý cần được duy trì khi bảng thay đổi. Trong quá trình vận hành, index có thể bị đánh dấu **UNUSABLE**, có thể chứa nhiều leaf block chưa được sử dụng hiệu quả, hoặc có thể cần chuyển tablespace hay xây dựng lại cấu trúc.

Oracle cung cấp các thao tác khác nhau cho những mục tiêu khác nhau:

- **UNUSABLE:** đánh dấu index hoặc một index partition không thể được sử dụng.
- **REBUILD:** tạo lại cấu trúc index, thường dùng để khôi phục index unusable hoặc thay đổi cách lưu trữ.
- **COALESCE:** hợp nhất các leaf block B-tree lân cận để tăng khả năng tái sử dụng không gian trống bên trong index.

Không nên coi REBUILD và COALESCE là hai lệnh thay thế nhau. Một index unusable cần được rebuild để trở lại trạng thái sử dụng được; coalesce phục vụ việc sắp xếp lại leaf block của B-tree còn hợp lệ.

Ngoài ra, index tạo ra chi phí bảo trì cho mọi thao tác DML liên quan đến cột được lập chỉ mục. Một thiết kế có quá nhiều index có thể giúp SELECT nhưng làm INSERT, UPDATE, DELETE, bulk load, backup và quản lý không gian tốn kém hơn.

> Bài học dùng Oracle Database 19c. Các lệnh ALTER INDEX và DDL có thể tác động trực tiếp tới ứng dụng; chỉ thử trong schema lab. DDL của Oracle có implicit commit, vì vậy không thể dựa vào ROLLBACK để hoàn tác thao tác rebuild hoặc unusable.

## 2. Trạng thái VALID và UNUSABLE

### 2.1. VALID

Index ở trạng thái VALID có thể được optimizer xem xét khi lập execution plan và được duy trì theo các quy tắc DML của Oracle. Trạng thái VALID không bảo đảm optimizer sẽ chọn index; lựa chọn còn phụ thuộc predicate, statistics, selectivity, chi phí truy cập và các yếu tố khác.

### 2.2. UNUSABLE

Index ở trạng thái UNUSABLE không thể được sử dụng như một index hợp lệ để truy cập dữ liệu. Optimizer bỏ qua index đó. Nếu index hoặc partition bị unusable, truy vấn vẫn có thể chạy bằng full table scan hoặc một access path khác, miễn là query có cách đọc dữ liệu hợp lệ.

Ví dụ:

~~~sql
ALTER INDEX ix_orders_customer UNUSABLE;
~~~

Lệnh này đánh dấu toàn bộ index không sử dụng được. Nó không xóa bảng nguồn và cũng không xóa dữ liệu nghiệp vụ trong bảng. Segment index vẫn có thể còn được cấp phát cho tới khi được rebuild hoặc xử lý bằng thao tác DDL phù hợp.

### 2.3. Unusable index khác index không được optimizer chọn

Hai tình huống này khác nhau:

- **Index VALID nhưng không được chọn:** optimizer quyết định full scan hoặc access path khác rẻ hơn. Index vẫn tồn tại và có thể được dùng trong câu SQL khác.
- **Index UNUSABLE:** optimizer không thể dùng index đó. Cần khôi phục trạng thái bằng thao tác phù hợp nếu ứng dụng cần index.

Không kết luận index unusable chỉ vì execution plan không có INDEX RANGE SCAN hoặc INDEX UNIQUE SCAN.

## 3. Nguyên nhân index hoặc index partition trở thành UNUSABLE

Một số tình huống thường gặp:

### 3.1. Đánh dấu chủ động

DBA hoặc quy trình nạp dữ liệu có thể cố ý đánh dấu index unusable:

~~~sql
ALTER INDEX ix_sales_customer UNUSABLE;
~~~

Mục đích thường là tránh chi phí duy trì một index trong lúc bulk load hoặc một thao tác bảo trì lớn, sau đó rebuild khi dữ liệu đã được nạp xong.

Không áp dụng tùy tiện cho index đang được ứng dụng sử dụng. Phải kiểm tra ràng buộc, loại index, quyền truy cập và kế hoạch khôi phục.

### 3.2. Bulk load và direct-path load

Một số quy trình direct-path load hoặc lựa chọn bỏ qua bảo trì index có thể làm index bị unusable. Ví dụ, SQL*Loader direct path có các tùy chọn liên quan đến việc bỏ qua index maintenance; kết quả phụ thuộc chế độ load và lỗi phát sinh.

Nếu bỏ qua index maintenance để tăng tốc nạp dữ liệu, quy trình cần có bước kiểm tra và rebuild index trước khi mở lại workload phụ thuộc index.

### 3.3. Thao tác trên bảng hoặc partition

Một số thao tác DDL trên bảng, như MOVE, hoặc thao tác partition maintenance có thể làm một hay nhiều index/index partition bị unusable nếu không yêu cầu Oracle duy trì index trong cùng thao tác.

Ví dụ, khi drop hoặc truncate một table partition, global index có thể bị ảnh hưởng nếu không dùng tùy chọn duy trì global index phù hợp. Cú pháp và hành vi cụ thể tùy loại thao tác, phiên bản và loại index. Sau partition maintenance, cần kiểm tra trạng thái của local index partitions và global indexes thay vì giả định mọi index vẫn VALID.

### 3.4. Chỉ một partition bị unusable

Với partitioned index, có thể chỉ một index partition hoặc subpartition bị unusable trong khi các partition khác vẫn usable. Đây là lý do phải kiểm tra metadata ở cấp partition, không chỉ nhìn trạng thái index tổng thể.

Ví dụ:

~~~sql
ALTER INDEX ix_sales_local
MODIFY PARTITION p2026_01 UNUSABLE;
~~~

Tên partition chỉ là ví dụ. Với local partitioned index, mỗi index partition tương ứng với table partition theo cấu trúc local index.

### 3.5. Ràng buộc UNIQUE và PRIMARY KEY

Index dùng để thực thi PRIMARY KEY hoặc UNIQUE constraint có vai trò bảo đảm tính duy nhất. Oracle không cho phép tùy tiện đánh dấu unusable một index đang thực thi constraint theo cách làm mất khả năng kiểm tra uniqueness. Hãy kiểm tra constraint phụ thuộc trước khi lập kế hoạch bảo trì.

Nếu muốn thay đổi cách thực thi constraint, phải thiết kế quy trình constraint riêng và hiểu tác động đến tính toàn vẹn dữ liệu. Không coi việc đánh dấu unusable là cách tạm tắt một unique constraint an toàn.

## 4. DML khi index ở trạng thái UNUSABLE

### 4.1. Ảnh hưởng tới SELECT

Optimizer không sử dụng unusable index. Query có thể vẫn thành công bằng full table scan hoặc một index khác:

~~~sql
SELECT order_id, order_total
FROM orders
WHERE customer_id = 100;
~~~

Nếu index trên CUSTOMER_ID bị unusable và không có access path khác, Oracle có thể phải đọc nhiều block của bảng hơn. Kết quả dữ liệu vẫn đúng; vấn đề là hiệu năng có thể giảm.

### 4.2. Ảnh hưởng tới INSERT, UPDATE và DELETE

DML thông thường phải duy trì các index liên quan. Nếu index không sử dụng được, hành vi phụ thuộc cấu hình và loại index:

- Khi không cho phép bỏ qua unusable indexes, DML có thể thất bại với ORA-01502.
- SKIP_UNUSABLE_INDEXES cho phép một số DML tiếp tục mà bỏ qua unusable nonunique indexes.
- Index unusable dùng để thực thi UNIQUE/PRIMARY KEY constraint không thể bị bỏ qua theo cách làm mất kiểm tra uniqueness; DML vẫn phải bảo đảm constraint.

Ví dụ lỗi:

~~~text
ORA-01502: index 'OWNER.IX_ORDERS_CUSTOMER' or partition of such index is in unusable state
~~~

### 4.3. SKIP_UNUSABLE_INDEXES

Tham số SKIP_UNUSABLE_INDEXES điều khiển việc DML có được bỏ qua một số unusable indexes/index partitions hay không. Có thể kiểm tra:

~~~sql
SHOW PARAMETER skip_unusable_indexes;
~~~

Hoặc:

~~~sql
SELECT name, value
FROM v$parameter
WHERE name = 'skip_unusable_indexes';
~~~

Trong session lab, có thể thử:

~~~sql
ALTER SESSION SET skip_unusable_indexes = TRUE;
~~~

Khi được bật, Oracle có thể cho phép DML trên bảng có nonunique index unusable mà không duy trì index đó. Điều này hữu ích trong một số quy trình bulk load, nhưng query không thể dùng index cho tới khi index được rebuild.

**Không diễn giải SKIP_UNUSABLE_INDEXES thành “mọi index lỗi đều được bỏ qua”.** Index hỗ trợ unique constraint không thể bị bỏ qua nếu điều đó làm mất kiểm tra uniqueness. Các giới hạn còn phụ thuộc loại index và thao tác DML.

### 4.4. Vì sao phải rebuild ngay sau khi bỏ qua index?

Giả sử một bảng có index unusable trên CUSTOMER_ID. Trong thời gian DML được phép bỏ qua index:

- Bảng vẫn nhận dữ liệu.
- Index không được duy trì theo các thay đổi đó.
- Optimizer không dùng index unusable.
- Sau khi rebuild, Oracle tạo lại index từ dữ liệu hiện có trong bảng.

Vì vậy, chỉ bật SKIP_UNUSABLE_INDEXES mà không có bước rebuild và xác nhận trạng thái sẽ để lại một access path không dùng được.

## 5. Kiểm tra index và trạng thái partition

### 5.1. USER_INDEXES

Để xem index thuộc schema hiện tại:

~~~sql
SELECT index_name,
       table_name,
       index_type,
       uniqueness,
       status,
       tablespace_name
FROM user_indexes
ORDER BY table_name, index_name;
~~~

Các cột hữu ích:

- INDEX_NAME: tên index.
- TABLE_NAME: bảng cơ sở.
- INDEX_TYPE: loại index.
- UNIQUENESS: UNIQUE hoặc NONUNIQUE.
- STATUS: trạng thái index không partitioned; với partitioned index, cần kiểm tra partition metadata.
- TABLESPACE_NAME: tablespace lưu index nếu áp dụng.

### 5.2. ALL_INDEXES và DBA_INDEXES

User có thể xem các index có quyền nhìn thấy qua ALL_INDEXES:

~~~sql
SELECT owner, index_name, table_owner, table_name,
       index_type, uniqueness, status
FROM all_indexes
ORDER BY owner, table_name, index_name;
~~~

DBA có thể xem toàn bộ:

~~~sql
SELECT owner, index_name, table_owner, table_name,
       index_type, uniqueness, status
FROM dba_indexes
ORDER BY owner, table_name, index_name;
~~~

Với partitioned indexes, trạng thái ở cấp index có thể không phản ánh trạng thái từng partition. Cần xem các view partition tương ứng.

### 5.3. Kiểm tra index partitions

~~~sql
SELECT index_name,
       partition_name,
       status,
       tablespace_name
FROM user_ind_partitions
ORDER BY index_name, partition_position;
~~~

Nếu dùng DBA view:

~~~sql
SELECT index_owner,
       index_name,
       partition_name,
       status,
       tablespace_name
FROM dba_ind_partitions
WHERE status = 'UNUSABLE'
ORDER BY index_owner, index_name, partition_position;
~~~

### 5.4. Kiểm tra subpartitions

~~~sql
SELECT index_name,
       partition_name,
       subpartition_name,
       status,
       tablespace_name
FROM user_ind_subpartitions
ORDER BY index_name, partition_name, subpartition_position;
~~~

Để tìm subpartition unusable:

~~~sql
SELECT index_name, partition_name, subpartition_name, status
FROM user_ind_subpartitions
WHERE status = 'UNUSABLE';
~~~

### 5.5. Kiểm tra constraint sử dụng index

~~~sql
SELECT constraint_name,
       constraint_type,
       status,
       validated,
       index_name
FROM user_constraints
WHERE index_name = UPPER(:index_name);
~~~

Nếu index gắn với constraint PRIMARY KEY hoặc UNIQUE, cần hiểu rõ constraint trước khi thay đổi trạng thái index.

## 6. REBUILD: tạo lại cấu trúc index

### 6.1. Khi nào cần REBUILD?

REBUILD thường được dùng khi:

- Index hoặc partition đã unusable.
- Cần chuyển index sang tablespace khác.
- Cần thay đổi một số thuộc tính lưu trữ hoặc compression.
- Cần tạo lại cấu trúc vật lý sau một thao tác bảo trì.
- Có bằng chứng đo lường cho thấy rebuild phù hợp với mục tiêu dung lượng hoặc workload.

Không rebuild chỉ vì index đã tồn tại lâu, vì BLEVEL tăng một mức, hoặc vì ai đó nói rằng “index luôn cần defragment định kỳ”. B-tree có cơ chế split và tái sử dụng block; cần đo lường trước khi can thiệp.

### 6.2. Rebuild toàn bộ nonpartitioned index

~~~sql
ALTER INDEX ix_orders_customer REBUILD;
~~~

Oracle tạo lại cấu trúc index từ dữ liệu của bảng. Sau khi thành công, index trở lại trạng thái usable.

### 6.3. Rebuild một index partition

~~~sql
ALTER INDEX ix_sales_local
REBUILD PARTITION p2026_01;
~~~

Chỉ partition được chỉ định được rebuild. Đây thường là lựa chọn phù hợp khi chỉ một local index partition hoặc global index partition bị unusable.

### 6.4. Rebuild một index subpartition

~~~sql
ALTER INDEX ix_sales_local
REBUILD SUBPARTITION sp2026_01_a;
~~~

Dùng tên subpartition thực tế trong dictionary. Không nhầm partition của bảng với partition/subpartition của index; hãy kiểm tra USER_IND_PARTITIONS và USER_IND_SUBPARTITIONS trước khi chạy.

### 6.5. Rebuild và chuyển tablespace

~~~sql
ALTER INDEX ix_orders_customer
REBUILD TABLESPACE index_ts;
~~~

Lệnh này tạo lại index trong tablespace đích. Cần bảo đảm tablespace có đủ dung lượng trong thời gian rebuild, vì cấu trúc mới có thể cần tồn tại song song với segment cũ cho đến khi thao tác hoàn tất.

### 6.6. Rebuild ONLINE

~~~sql
ALTER INDEX ix_orders_customer REBUILD ONLINE;
~~~

ONLINE cho phép các DML thông thường tiếp tục trên bảng trong phần lớn thời gian rebuild, theo các điều kiện hỗ trợ của Oracle và loại index. Nó giảm thời gian chặn ứng dụng so với rebuild offline, nhưng không có nghĩa là không cần khóa hoặc không có giai đoạn đồng bộ ngắn ở đầu/cuối thao tác.

ONLINE rebuild có thể tốn thêm tài nguyên và có các giới hạn theo loại index, partition, edition hoặc thao tác cụ thể. Kiểm tra SQL Language Reference 19c trước khi dùng trong production.

### 6.7. Parallel rebuild

~~~sql
ALTER INDEX ix_orders_customer
REBUILD PARALLEL 4;
~~~

Parallel có thể rút ngắn thời gian bằng cách dùng nhiều process, nhưng tăng nhu cầu CPU, I/O, temporary space và cạnh tranh tài nguyên. Chọn DOP theo năng lực hệ thống, không đặt giá trị cao chỉ để lệnh hoàn tất nhanh.

Nếu không muốn giữ thuộc tính parallel sau rebuild:

~~~sql
ALTER INDEX ix_orders_customer NOPARALLEL;
~~~

### 6.8. NOLOGGING và recovery

Có thể chỉ định NOLOGGING trong một số thao tác rebuild:

~~~sql
ALTER INDEX ix_orders_customer
REBUILD NOLOGGING;
~~~

NOLOGGING có thể giảm lượng redo cho phần thao tác được phép, nhưng không có nghĩa mọi thay đổi đều không tạo redo. FORCE LOGGING có thể ghi đè lựa chọn này. NOLOGGING còn ảnh hưởng khả năng phục hồi media và đồng bộ standby/Data Guard; phải phối hợp với DBA và chính sách backup trước khi sử dụng.

Không dùng NOLOGGING như một mẹo hiệu năng vô điều kiện.

## 7. COALESCE: hợp nhất leaf block của B-tree

### 7.1. Khái niệm

Trong B-tree index, các leaf block chứa index entry trỏ tới row trong bảng. Sau nhiều thao tác DELETE hoặc thay đổi dữ liệu, một số leaf block có thể chứa ít entry hơn và không gian trong index có thể chưa được sử dụng hiệu quả.

COALESCE hợp nhất các leaf block lân cận có thể ghép trong cùng nhánh của cây, làm cho block được giải phóng có thể tái sử dụng bên trong index.

Cú pháp:

~~~sql
ALTER INDEX ix_orders_customer COALESCE;
~~~

Đối với partition:

~~~sql
ALTER INDEX ix_sales_local
COALESCE PARTITION p2026_01;
~~~

COALESCE là thao tác online đối với B-tree index theo khả năng hỗ trợ của Oracle và không cần tạo một segment index mới có kích thước tương đương để thay thế segment cũ.

### 7.2. COALESCE không phải REBUILD

COALESCE:

- Hợp nhất leaf block lân cận có thể ghép.
- Cho phép index tái sử dụng block được giải phóng.
- Không xây dựng lại toàn bộ cây index theo cách REBUILD làm.
- Không chuyển index sang tablespace khác.
- Không có mục tiêu hạ high-water mark và trả toàn bộ không gian segment về tablespace.

REBUILD:

- Tạo lại cấu trúc index.
- Có thể tổ chức lại nhiều phần của cây.
- Có thể chuyển tablespace hoặc thay đổi thuộc tính được hỗ trợ.
- Có thể tạo một segment mới gọn hơn, tùy dữ liệu và storage.
- Thường cần thêm không gian trong lúc thao tác.

### 7.3. COALESCE không sửa index UNUSABLE

COALESCE là bảo trì cấu trúc leaf block của một B-tree index có thể sử dụng. Nếu index đã bị đánh dấu UNUSABLE, cần REBUILD để tạo lại index trước khi sử dụng. Không dùng COALESCE như một bước thay thế REBUILD cho index unusable.

### 7.4. COALESCE có trả không gian về tablespace không?

Không nên kỳ vọng COALESCE làm segment index nhỏ đi hoặc trả các extent cuối cùng về tablespace. Các block được giải phóng có thể được tái sử dụng bên trong segment index, nhưng high-water mark và dung lượng segment đã cấp phát có thể không giảm.

Nếu mục tiêu là chuyển tablespace hoặc thu hồi segment space, hãy đánh giá REBUILD hoặc một thao tác segment phù hợp thay vì chỉ chạy COALESCE.

### 7.5. Loại index

COALESCE là thao tác dành cho B-tree indexes. Không áp dụng cùng giả định cho bitmap, domain index hoặc các loại index chuyên biệt. Với loại index đặc biệt, dùng thao tác bảo trì mà indextype và Oracle hỗ trợ.

## 8. So sánh REBUILD, COALESCE và không làm gì

| Tình trạng/mục tiêu | Hướng xử lý thường phù hợp | Lý do |
| --- | --- | --- |
| Index UNUSABLE | REBUILD | Tạo lại index để khôi phục khả năng sử dụng |
| Một index partition UNUSABLE | REBUILD PARTITION | Chỉ phục hồi partition bị ảnh hưởng |
| Một index subpartition UNUSABLE | REBUILD SUBPARTITION | Phạm vi nhỏ hơn rebuild toàn bộ |
| B-tree VALID, leaf block có thể hợp nhất | COALESCE | Tái sử dụng leaf blocks mà không tạo segment mới |
| Cần chuyển tablespace | REBUILD TABLESPACE | Tạo lại index ở vị trí lưu trữ khác |
| Cần rebuild trong khi DML vẫn diễn ra | REBUILD ONLINE nếu được hỗ trợ | Giảm thời gian chặn DML |
| Index VALID, query vẫn nhanh, không có vấn đề dung lượng | Không làm gì | Tránh chi phí bảo trì không cần thiết |
| Index VALID nhưng optimizer không chọn | Kiểm tra query/stats/selectivity trước | Không chọn index không đồng nghĩa index hỏng |

## 9. Chi phí của REBUILD và COALESCE

### 9.1. Không gian lưu trữ

REBUILD thường cần không gian cho cấu trúc mới trong khi cấu trúc cũ vẫn tồn tại. Với index lớn, cần dự trù dung lượng tablespace, temporary space và khoảng trống để thao tác hoàn tất.

COALESCE không cần tạo một index segment mới thay thế segment cũ; do đó nhu cầu không gian bổ sung thường thấp hơn đáng kể.

### 9.2. CPU và I/O

REBUILD phải đọc dữ liệu nguồn để tạo lại index, sắp xếp và ghi cấu trúc mới. Điều này có thể tạo tải CPU và I/O đáng kể, nhất là index lớn hoặc rebuild song song.

COALESCE thao tác trên các leaf block cần hợp nhất nên thường nhẹ hơn rebuild toàn bộ. Tuy nhiên, chạy coalesce thường xuyên trên nhiều index cũng tiêu tốn I/O và thời gian bảo trì.

### 9.3. REDO, UNDO và phục hồi

Khối lượng redo phụ thuộc LOGGING/NOLOGGING, FORCE LOGGING, loại thao tác và cấu hình database. Dù dùng NOLOGGING, vẫn phải hiểu ảnh hưởng đến backup, media recovery và standby.

UNDO chủ yếu phục vụ transaction và consistent read; không nên đánh đồng chi phí undo với redo. Các thao tác DDL và index maintenance có cơ chế ghi nhận riêng của Oracle.

### 9.4. Khóa và khả năng đồng thời

Rebuild offline có thể chặn DML trên bảng trong thời gian liên quan đến thao tác. Rebuild ONLINE cho phép DML đồng thời theo giới hạn hỗ trợ, nhưng cần thêm xử lý thay đổi phát sinh và vẫn có các điểm đồng bộ.

Coalesce B-tree là thao tác online, thường phù hợp hơn khi muốn giảm khoảng trống leaf block mà không cần thay thế toàn bộ index.

### 9.5. Statistics và execution plan

Sau khi index thay đổi, cần xem lại statistics và execution plan nếu workload có dấu hiệu thay đổi. Không giả định rebuild luôn làm query nhanh hơn.

Các chỉ số thường được xem trong USER_INDEXES/DBA_INDEXES:

- BLEVEL: số tầng branch trong cây theo cách Oracle thống kê.
- LEAF_BLOCKS: số leaf blocks theo statistics.
- DISTINCT_KEYS: số giá trị khóa phân biệt.
- CLUSTERING_FACTOR: mức tương quan giữa thứ tự index và vị trí row trong bảng.
- LAST_ANALYZED: thời điểm thu thập statistics.

Rebuild index không tự sắp xếp lại thứ tự vật lý các row trong bảng. Vì vậy, nó không tự động sửa clustering factor kém do thứ tự lưu trữ của table. Không dùng riêng BLEVEL hoặc LEAF_BLOCKS để quyết định rebuild; kết hợp workload, execution plan, thời gian đáp ứng và số liệu segment.

## 10. Chi phí bảo trì index trong DML hằng ngày

Index không miễn phí. Mỗi index có thể cần được cập nhật khi dữ liệu của bảng thay đổi.

### 10.1. INSERT

Khi INSERT row vào bảng, Oracle cần tạo entry tương ứng trong mỗi index liên quan. Một bảng có 12 index có thể phải duy trì nhiều cấu trúc hơn đáng kể so với bảng chỉ có 2 index.

### 10.2. DELETE

Khi DELETE row, Oracle phải xử lý entry trong các index liên quan. Các leaf block có thể còn khoảng trống; Oracle có thể tái sử dụng không gian đó cho các entry sau.

### 10.3. UPDATE

Nếu UPDATE thay đổi cột nằm trong index key hoặc cột được index tham chiếu, Oracle phải cập nhật index entry tương ứng. Nếu chỉ thay đổi cột không liên quan tới index, index đó thường không cần thay đổi entry.

Với composite index, cần xem cột thay đổi có thuộc key hay không. Function-based index còn phụ thuộc biểu thức được lập chỉ mục.

### 10.4. Chi phí tổng hợp

Mỗi index bổ sung có thể làm tăng:

- Thời gian và I/O của INSERT, DELETE và một số UPDATE.
- Redo/undo liên quan tới thay đổi dữ liệu và index.
- Dung lượng segment, backup và thời gian phục hồi.
- Chi phí statistics và maintenance window.
- Cạnh tranh tài nguyên trong workload ghi đồng thời.

Index vẫn cần thiết cho primary key, unique constraint, foreign key access patterns và truy vấn quan trọng. Mục tiêu không phải xóa index cho ít đi bằng mọi giá, mà là giữ những index có giá trị truy cập hoặc integrity rõ ràng.

## 11. Bảo trì index partitioned

### 11.1. Local partitioned index

Local index được partition theo cùng chiến lược partition của bảng. Mỗi table partition có index partition tương ứng.

Nếu một local index partition bị unusable:

~~~sql
ALTER INDEX ix_sales_local
REBUILD PARTITION p2026_01;
~~~

Chỉ rebuild partition đó thay vì toàn bộ index, nếu đây là phạm vi bị ảnh hưởng.

### 11.2. Global partitioned index

Global partitioned index có cách partition độc lập với partition của bảng. Một thao tác trên table partition có thể ảnh hưởng nhiều phần của global index, tùy loại thao tác và tùy chọn duy trì index.

Sau khi DROP/TRUNCATE/MOVE table partition, hãy kiểm tra global index và các index partitions liên quan. Sử dụng tùy chọn UPDATE INDEXES hoặc UPDATE GLOBAL INDEXES khi cú pháp thao tác hỗ trợ và khi yêu cầu vận hành cần duy trì index.

Không giả định mọi lệnh partition maintenance đều có cùng hành vi đối với local và global indexes.

### 11.3. Kiểm tra trước và sau partition maintenance

~~~sql
SELECT index_name, partition_name, status
FROM user_ind_partitions
WHERE index_name = 'IX_SALES_LOCAL'
ORDER BY partition_position;
~~~

Sau thao tác DDL, chạy lại truy vấn để phát hiện partition UNUSABLE. Nếu có, xác định partition nào bị ảnh hưởng và rebuild đúng phạm vi.

### 11.4. Rebuild partition và coalesce partition

Rebuild partition:

~~~sql
ALTER INDEX ix_sales_local
REBUILD PARTITION p2026_01;
~~~

Coalesce partition:

~~~sql
ALTER INDEX ix_sales_local
COALESCE PARTITION p2026_01;
~~~

Rebuild dùng để khôi phục partition unusable hoặc tạo lại cấu trúc; coalesce dùng để hợp nhất leaf blocks của B-tree partition còn hợp lệ.

## 12. Lập kế hoạch bulk load với index

Với bảng staging hoặc bảng fact lớn, việc duy trì nhiều index trong lúc nạp hàng triệu row có thể làm load chậm. Một chiến lược có thể là:

1. Xác định các index có thể tạm bỏ qua trong batch.
2. Kiểm tra index nào hỗ trợ constraint và không được phép bỏ qua.
3. Lập kế hoạch đánh dấu unusable hoặc dùng phương án load được hỗ trợ.
4. Chạy bulk load với cơ chế SKIP_UNUSABLE_INDEXES phù hợp.
5. Rebuild các index bị unusable sau load.
6. Thu thập hoặc xác nhận statistics.
7. Đối soát row count, constraint và execution plan trước khi mở workload.

Đây là quy trình bảo trì có cửa sổ kiểm soát, không phải cách chạy DML hằng ngày trên bảng đang phục vụ ứng dụng.

### 12.1. Ví dụ minh họa quy trình

Giả sử bảng SALES_STAGE có nonunique index IX_SALES_STAGE_REGION:

~~~sql
ALTER INDEX ix_sales_stage_region UNUSABLE;

ALTER SESSION SET skip_unusable_indexes = TRUE;

-- Bulk load dữ liệu vào SALES_STAGE bằng quy trình phù hợp.

ALTER INDEX ix_sales_stage_region REBUILD;
~~~

Sau rebuild:

~~~sql
SELECT index_name, status
FROM user_indexes
WHERE index_name = 'IX_SALES_STAGE_REGION';
~~~

Phải xác nhận index trở lại VALID trước khi kết thúc cửa sổ bảo trì. Nếu có nhiều index, quản lý danh sách và kết quả từng index; không chỉ dựa vào một lệnh rebuild thành công.

### 12.2. Không đánh dấu unusable index hỗ trợ constraint

Trước khi áp dụng chiến lược trên, kiểm tra:

~~~sql
SELECT constraint_name, constraint_type, status, index_name
FROM user_constraints
WHERE table_name = 'SALES_STAGE';
~~~

Unique/primary key enforcement không thể bị bỏ qua như nonunique secondary index. Nếu batch cần bảo đảm uniqueness trong lúc load, thiết kế quy trình constraint và load riêng.

## 13. Đánh giá xem có nên rebuild hay không

Trước khi rebuild một index VALID, cần trả lời:

### 13.1. Có vấn đề thực tế nào không?

- Query nào chậm?
- Execution plan có dùng index không?
- Index có phải access path phù hợp cho predicate không?
- Statistics có mới và phản ánh dữ liệu không?
- Có thay đổi lớn về số lượng row hoặc phân bố giá trị không?

Nếu query chậm do predicate không selective, function trên cột không khớp index, datatype conversion, network hoặc I/O của bảng, rebuild có thể không giải quyết nguyên nhân.

### 13.2. Có bằng chứng về không gian không?

Xem segment size và index statistics:

~~~sql
SELECT segment_name,
       segment_type,
       bytes,
       blocks
FROM user_segments
WHERE segment_type LIKE 'INDEX%'
ORDER BY bytes DESC;
~~~

Và:

~~~sql
SELECT index_name,
       blevel,
       leaf_blocks,
       distinct_keys,
       clustering_factor,
       last_analyzed
FROM user_indexes
ORDER BY leaf_blocks DESC;
~~~

Statistics có thể cũ. Hãy xem thời điểm thu thập và workload sau đó.

### 13.3. So sánh tác động với lợi ích

Rebuild có thể giảm segment size trong một số trường hợp, tạo lại cấu trúc index hoặc chuyển tablespace/thay đổi storage attributes.

Nhưng cũng có thể tốn I/O, CPU, temporary space, redo tùy logging và cạnh tranh với workload đang chạy. Rebuild không cải thiện query nếu nguyên nhân nằm ở nơi khác.

Nếu index vẫn hoạt động tốt và không có mục tiêu storage cụ thể, giữ nguyên thường là quyết định hợp lý.

## 14. Các thao tác DDL và transaction

ALTER INDEX, ALTER TABLE, CREATE INDEX và DROP INDEX là DDL. Oracle thực hiện implicit commit trước và sau DDL theo quy tắc transaction của Oracle.

Ví dụ:

~~~sql
UPDATE maintenance_log
SET status = 'STARTED'
WHERE task_id = 10;

ALTER INDEX ix_orders_customer REBUILD;

ROLLBACK;
~~~

Không thể mong ROLLBACK hoàn tác cả UPDATE trước DDL và rebuild như một transaction DML thông thường. DDL tạo ranh giới commit; UPDATE trước DDL có thể đã được commit ngầm.

Vì vậy:

- Không chạy DDL bảo trì index giữa một transaction nghiệp vụ chưa kết thúc.
- Lập lịch maintenance window và ghi log trạng thái riêng.
- Nếu cần audit, ghi trạng thái trước/sau bằng transaction riêng và hiểu implicit commit.
- Chuẩn bị phương án khôi phục nếu rebuild thất bại.

## 15. Những lỗi thường gặp

| Lỗi/hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| ORA-01502 | DML hoặc thao tác truy cập gặp index/index partition unusable | Kiểm tra trạng thái và rebuild đúng phạm vi |
| ORA-00001 sau rebuild hoặc load | Dữ liệu nguồn có khóa trùng; unique constraint phát hiện vi phạm | Kiểm tra duplicate và quy tắc uniqueness |
| Rebuild không đủ chỗ | Tablespace không đủ dung lượng cho cấu trúc mới | Dự trù thêm space, chọn tablespace phù hợp |
| Rebuild online bị từ chối | Loại index hoặc cú pháp không hỗ trợ online | Kiểm tra giới hạn loại index và Oracle 19c |
| DML vẫn lỗi dù SKIP_UNUSABLE_INDEXES bật | Index hỗ trợ unique constraint hoặc loại index không thể bỏ qua | Kiểm tra constraint/index type |
| Query chậm sau khi index unusable | Optimizer không thể dùng index và chọn access path khác | Rebuild nếu index cần thiết; xem execution plan |
| COALESCE không làm segment nhỏ đi | COALESCE tái sử dụng block trong index, không nhằm trả extent về tablespace | Dùng REBUILD hoặc phương án segment phù hợp nếu cần thu hồi space |
| Rebuild không cải thiện query | Nguyên nhân không nằm ở cấu trúc index | Kiểm tra SQL, statistics, selectivity, clustering factor và I/O |
| Local/global partition index bị unusable sau DDL | Partition maintenance không duy trì index theo tùy chọn mong muốn | Kiểm tra partition status và rebuild phần bị ảnh hưởng |
| Không rollback được rebuild | DDL đã tạo implicit commit | Lập kế hoạch DDL riêng, dùng phương án phục hồi |

## 16. Bộ thực hành tự chứa

Các bài lab sau dùng bảng riêng. Chỉ chạy trong schema lab; không chạy lệnh UNUSABLE hoặc REBUILD trên index của ứng dụng thật.

### 16.1. Tạo bảng và index

~~~sql
CREATE TABLE orders_index_lab (
    order_id NUMBER PRIMARY KEY,
    customer_id NUMBER NOT NULL,
    order_total NUMBER(12,2),
    order_status VARCHAR2(20 CHAR)
);

INSERT INTO orders_index_lab
SELECT level,
       MOD(level, 1000) + 1,
       MOD(level * 17, 100000) / 100,
       CASE WHEN MOD(level, 3) = 0 THEN 'CLOSED' ELSE 'OPEN' END
FROM dual
CONNECT BY level <= 10000;

CREATE INDEX ix_orders_lab_customer
ON orders_index_lab(customer_id);

CREATE INDEX ix_orders_lab_status
ON orders_index_lab(order_status);

COMMIT;
~~~

### 16.2. Kiểm tra trạng thái

~~~sql
SELECT index_name, index_type, uniqueness, status
FROM user_indexes
WHERE table_name = 'ORDERS_INDEX_LAB'
ORDER BY index_name;
~~~

### 16.3. Đánh dấu một nonunique index unusable

~~~sql
ALTER INDEX ix_orders_lab_customer UNUSABLE;
~~~

Kiểm tra:

~~~sql
SELECT index_name, status
FROM user_indexes
WHERE index_name = 'IX_ORDERS_LAB_CUSTOMER';
~~~

### 16.4. Quan sát SELECT

~~~sql
SELECT COUNT(*)
FROM orders_index_lab
WHERE customer_id = 10;
~~~

Query vẫn có thể chạy, nhưng optimizer không dùng index unusable đó. Dùng EXPLAIN PLAN hoặc DBMS_XPLAN để quan sát access path:

~~~sql
EXPLAIN PLAN FOR
SELECT *
FROM orders_index_lab
WHERE customer_id = 10;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

### 16.5. Thử DML khi index unusable

Kiểm tra cấu hình session:

~~~sql
SHOW PARAMETER skip_unusable_indexes;
~~~

Nếu cần thử bỏ qua unusable nonunique index:

~~~sql
ALTER SESSION SET skip_unusable_indexes = TRUE;

INSERT INTO orders_index_lab
       (order_id, customer_id, order_total, order_status)
VALUES (20001, 10, 500, 'OPEN');

COMMIT;
~~~

Hành vi phụ thuộc loại index, constraint và cấu hình. Không dùng bài lab này để kết luận unique index cũng được bỏ qua.

### 16.6. Rebuild để khôi phục

~~~sql
ALTER INDEX ix_orders_lab_customer REBUILD;
~~~

Xác nhận:

~~~sql
SELECT index_name, status
FROM user_indexes
WHERE index_name = 'IX_ORDERS_LAB_CUSTOMER';
~~~

Index cần trở lại VALID.

### 16.7. Thử COALESCE

~~~sql
ALTER INDEX ix_orders_lab_customer COALESCE;
~~~

Lệnh này minh họa coalesce trên B-tree index đang usable. Kiểm tra trạng thái:

~~~sql
SELECT index_name, status
FROM user_indexes
WHERE index_name = 'IX_ORDERS_LAB_CUSTOMER';
~~~

COALESCE không thay thế bước rebuild nếu index đang unusable.

### 16.8. Xem index statistics và segment

~~~sql
SELECT index_name, blevel, leaf_blocks,
       distinct_keys, clustering_factor, last_analyzed
FROM user_indexes
WHERE table_name = 'ORDERS_INDEX_LAB';

SELECT segment_name, bytes, blocks
FROM user_segments
WHERE segment_name LIKE 'IX_ORDERS_LAB%';
~~~

Số liệu chỉ là ảnh chụp tại thời điểm truy vấn. Không kết luận hiệu năng chỉ từ một chỉ số.

### 16.9. Dọn lab (tùy chọn)

~~~sql
DROP TABLE orders_index_lab PURGE;
~~~

DROP TABLE xóa cả các index phụ thuộc của bảng. DDL có implicit commit; chỉ chạy khi đã hoàn thành bài lab và không cần giữ dữ liệu.

## 17. Checklist bảo trì index

1. **Index có thật sự UNUSABLE không?** Kiểm tra USER_INDEXES hoặc DBA_INDEXES.
2. **Đây có phải partitioned index không?** Kiểm tra USER_IND_PARTITIONS và USER_IND_SUBPARTITIONS.
3. **Index có hỗ trợ PRIMARY KEY/UNIQUE constraint không?** Kiểm tra USER_CONSTRAINTS trước khi thay đổi.
4. **DML đang gặp ORA-01502 hay chỉ query không dùng index?** Hai tình huống cần cách xử lý khác nhau.
5. **Có thể dùng SKIP_UNUSABLE_INDEXES không?** Chỉ khi loại index và constraint cho phép; cần lịch rebuild rõ ràng.
6. **Phạm vi rebuild là gì?** Toàn index, partition hay subpartition.
7. **Có cần ONLINE không?** Kiểm tra hỗ trợ theo index type và tác động tài nguyên.
8. **Tablespace có đủ chỗ không?** Dự trù segment mới, temporary space và tải I/O.
9. **Có dùng PARALLEL hoặc NOLOGGING không?** Đánh giá CPU, redo, backup, standby và FORCE LOGGING.
10. **Mục tiêu là hợp nhất leaf blocks hay tạo lại cấu trúc?** Chọn COALESCE hoặc REBUILD tương ứng.
11. **Có cần thu hồi space về tablespace không?** COALESCE không có mục tiêu giảm segment high-water mark.
12. **Đã xem execution plan và statistics chưa?** Không rebuild chỉ dựa trên BLEVEL hoặc tuổi index.
13. **Có partition maintenance liên quan không?** Kiểm tra local và global index status sau DDL.
14. **DDL có thể commit transaction hiện tại không?** Kết thúc transaction nghiệp vụ trước khi chạy.
15. **Đã xác nhận trạng thái sau bảo trì chưa?** Kiểm tra index và partition trở lại usable.

## 18. Câu hỏi tự kiểm tra

**Câu 1.** Index UNUSABLE khác index VALID nhưng optimizer không chọn như thế nào?

**Câu 2.** Optimizer xử lý index unusable ra sao?

**Câu 3.** DML có thể gặp lỗi nào khi index unusable?

**Câu 4.** SKIP_UNUSABLE_INDEXES có nghĩa mọi unusable index đều có thể bỏ qua không?

**Câu 5.** Vì sao index hỗ trợ unique constraint không thể bị bỏ qua như nonunique index?

**Câu 6.** Khi nào nên dùng REBUILD?

**Câu 7.** Khi nào COALESCE phù hợp hơn REBUILD?

**Câu 8.** COALESCE có trả toàn bộ không gian segment về tablespace không?

**Câu 9.** Có thể COALESCE một index unusable để khôi phục nó không?

**Câu 10.** Vì sao REBUILD ONLINE vẫn có thể cần tài nguyên và đồng bộ khóa?

**Câu 11.** Vì sao cần kiểm tra DBA_IND_PARTITIONS thay vì chỉ DBA_INDEXES?

**Câu 12.** Rebuild index có tự động sửa clustering factor kém do thứ tự row trong bảng không?

**Câu 13.** Vì sao index bổ sung làm tăng chi phí INSERT và DELETE?

**Câu 14.** Vì sao không nên chạy REBUILD định kỳ cho mọi index?

**Câu 15.** DDL REBUILD có thể được ROLLBACK như UPDATE không?

<details>
<summary>Gợi ý đáp án</summary>

1. VALID nhưng không được chọn là quyết định của optimizer; UNUSABLE không thể được optimizer dùng.
2. Bỏ qua index unusable và tìm access path khác.
3. ORA-01502 trong các tình huống DML không thể bỏ qua index unusable.
4. Không. Có giới hạn theo loại index và constraint; unique enforcement không được bỏ qua.
5. Vì constraint phải tiếp tục bảo đảm không có khóa trùng.
6. Khi index/index partition unusable, cần tái tạo cấu trúc, chuyển tablespace hoặc thay đổi thuộc tính được hỗ trợ.
7. Khi B-tree còn usable và mục tiêu là hợp nhất leaf block lân cận để tái sử dụng không gian.
8. Không. Block được giải phóng có thể tái sử dụng trong index; segment space không nhất thiết giảm.
9. Không. Index unusable cần REBUILD.
10. ONLINE cho DML đồng thời theo điều kiện hỗ trợ nhưng vẫn cần tài nguyên và giai đoạn đồng bộ.
11. Vì partitioned index có thể chỉ một partition/subpartition unusable trong khi các phần khác usable.
12. Không. Rebuild index không sắp xếp lại row vật lý trong table.
13. Mỗi thay đổi cần duy trì thêm index entry, I/O, redo/undo và không gian.
14. Rebuild tiêu tốn tài nguyên và có thể không cải thiện query nếu không có vấn đề thực tế.
15. Không. ALTER INDEX là DDL và có implicit commit theo quy tắc Oracle.

</details>

## 19. Tài liệu Oracle chính thức

1. [Oracle Database 19c SQL Language Reference — ALTER INDEX](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ALTER-INDEX.html): UNUSABLE, REBUILD, REBUILD PARTITION, COALESCE và các thuộc tính index.
2. [Oracle Database 19c SQL Language Reference — CREATE INDEX](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-INDEX.html): index types, partitioned indexes, logging và parallel options.
3. [Oracle Database 19c Administrator's Guide — Managing Indexes](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/managing-indexes.html): quản lý, giám sát và bảo trì index.
4. [Oracle Database 19c Database VLDB and Partitioning Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/vldbg/): local/global indexes và tác động của partition maintenance.
5. [Oracle Database 19c Reference — USER_INDEXES](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/USER_INDEXES.html): trạng thái và statistics của index trong schema hiện tại.
6. [Oracle Database 19c Reference — USER_IND_PARTITIONS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/USER_IND_PARTITIONS.html): metadata của index partitions.
7. [Oracle Database 19c Reference — USER_IND_SUBPARTITIONS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/USER_IND_SUBPARTITIONS.html): metadata của index subpartitions.
8. [Oracle Database 19c Reference — SKIP_UNUSABLE_INDEXES](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/SKIP_UNUSABLE_INDEXES.html): hành vi DML với unusable indexes.
9. [Oracle Database 19c SQL Language Reference — ALTER TABLE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ALTER-TABLE.html): MOVE, partition maintenance và các tùy chọn duy trì index.

**Nguyên tắc cần nhớ:** UNUSABLE là trạng thái index không thể được optimizer sử dụng; DML có thể bị ảnh hưởng và SKIP_UNUSABLE_INDEXES chỉ giúp trong phạm vi được hỗ trợ, đặc biệt không bỏ qua yêu cầu unique constraint. REBUILD tạo lại cấu trúc và là cách phục hồi index unusable. COALESCE chỉ hợp nhất leaf block lân cận của B-tree còn usable, giúp tái sử dụng không gian trong segment chứ không thay thế rebuild hay bảo đảm trả extent về tablespace. Mỗi index đều làm tăng chi phí DML và lưu trữ; chỉ bảo trì khi có mục tiêu, số liệu và kế hoạch khôi phục rõ ràng.
