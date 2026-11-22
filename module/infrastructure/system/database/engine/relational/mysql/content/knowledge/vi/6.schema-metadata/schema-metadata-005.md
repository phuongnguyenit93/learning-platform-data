# INFORMATION_SCHEMA và tra cứu metadata có cấu trúc

## Mục tiêu bài học

Sau bài này, bạn có thể:

- Giải thích INFORMATION_SCHEMA là gì và nó khác với database nghiệp vụ như thế nào.
- Tra cứu danh sách schema, table, view, column, index và constraint bằng SQL.
- Lần theo quan hệ khóa ngoại và kiểm tra các cấu trúc trong schema.
- Khai thác metadata của view, routine, trigger, event và partition khi cần.
- Dùng metadata để lập danh mục, kiểm tra quy ước thiết kế và hỗ trợ migration.
- Nhận biết giới hạn về quyền nhìn thấy, độ mới và độ chính xác của metadata.

Trong MySQL, muốn biết một database có những bảng nào, cột nào, kiểu dữ liệu gì, index ra sao hoặc khóa ngoại trỏ đến đâu, bạn không cần mở từng bảng bằng giao diện quản trị. MySQL cung cấp INFORMATION_SCHEMA để truy vấn metadata bằng SQL. Nhờ đó, các tác vụ kiểm kê schema, tạo tài liệu kỹ thuật, kiểm tra chất lượng thiết kế và so sánh môi trường có thể được tự động hóa.

## 1. INFORMATION_SCHEMA là gì?

**INFORMATION_SCHEMA** là một database hệ thống cung cấp các view chỉ đọc mô tả metadata của MySQL. Metadata là dữ liệu mô tả cấu trúc và thuộc tính của các đối tượng, chẳng hạn:

- Schema/database và các table hoặc view.
- Column, kiểu dữ liệu, giá trị mặc định, charset và collation.
- Index, primary key, unique key, foreign key và check constraint.
- View, stored procedure, function, trigger và event.
- Partition và một số thông tin liên quan đến storage engine.
- Quyền truy cập ở phạm vi user, schema, table và column.

Bạn có thể truy vấn INFORMATION_SCHEMA như một schema bình thường:

```sql
SELECT SCHEMA_NAME
FROM INFORMATION_SCHEMA.SCHEMATA
ORDER BY SCHEMA_NAME;
```

INFORMATION_SCHEMA không phải nơi lưu dữ liệu nghiệp vụ và không phải nơi để INSERT, UPDATE hoặc DELETE metadata. Các view của nó trình bày thông tin mà MySQL quản lý trong data dictionary và các thành phần hệ thống. Với MySQL 8.0, data dictionary được quản lý theo kiến trúc transactional data dictionary; ứng dụng nên dùng INFORMATION_SCHEMA và các câu lệnh SHOW để đọc metadata, thay vì đọc trực tiếp các bảng nội bộ hoặc tệp dữ liệu của server.

### 1.1. Phân biệt ba schema hệ thống thường gặp

| Schema | Mục đích | Dùng khi nào? |
|---|---|---|
| INFORMATION_SCHEMA | Metadata về cấu trúc database và một số trạng thái hệ thống | Cần biết table, column, index, constraint, routine hoặc quyền |
| performance_schema | Instrumentation và số liệu runtime về hoạt động của server | Cần điều tra statement, wait, mutex, I/O và hoạt động đồng thời |
| sys | Các view và routine hỗ trợ đọc dữ liệu chẩn đoán, chủ yếu xây trên Performance Schema và metadata khác | Cần báo cáo dễ đọc về workload, statement, index hoặc tài nguyên |

Ba schema có liên quan nhưng không thay thế nhau. INFORMATION_SCHEMA trả lời “cấu trúc đang được khai báo thế nào?”. Performance Schema giúp trả lời “server đang hoạt động ra sao?”. Sys cung cấp các góc nhìn tổng hợp thuận tiện hơn cho nhiều tình huống vận hành.

## 2. Cách tổ chức metadata và cách truy vấn

INFORMATION_SCHEMA chứa nhiều view. Mỗi view mô tả một nhóm đối tượng. Ví dụ:

| View | Nội dung chính |
|---|---|
| SCHEMATA | Danh sách database/schema và thuộc tính mặc định |
| TABLES | Table, view, storage engine, kích thước và một số thống kê |
| COLUMNS | Cột, kiểu dữ liệu, thứ tự, nullability, default và collation |
| STATISTICS | Các index và từng key part của index |
| TABLE_CONSTRAINTS | Primary key, unique, foreign key, check constraint |
| KEY_COLUMN_USAGE | Cột tham gia constraint và quan hệ tham chiếu |
| REFERENTIAL_CONSTRAINTS | Quy tắc ON UPDATE và ON DELETE của foreign key |
| CHECK_CONSTRAINTS | Biểu thức và trạng thái của check constraint |
| VIEWS | Định nghĩa và thuộc tính view |
| ROUTINES | Stored procedure và function |
| TRIGGERS | Trigger gắn với table |
| EVENTS | Event Scheduler objects |
| PARTITIONS | Thông tin partition và subpartition |
| SCHEMA_PRIVILEGES, TABLE_PRIVILEGES, COLUMN_PRIVILEGES | Quyền được cấp ở các phạm vi tương ứng |

Tên view và tập cột có thể thay đổi theo phiên bản MySQL. Khi viết công cụ dùng cho nhiều phiên bản, hãy xác định phiên bản mục tiêu và kiểm tra cấu trúc view trên phiên bản đó. Không giả định mọi cột xuất hiện ở tất cả bản MySQL.

### 2.1. Cú pháp tra cứu cơ bản

Một truy vấn thường có dạng:

```sql
SELECT column_a, column_b
FROM INFORMATION_SCHEMA.some_view
WHERE condition
ORDER BY column_a;
```

Tên schema và table trong metadata thường được so sánh bằng chuỗi. Nên lọc ngay theo `TABLE_SCHEMA` hoặc `SCHEMA_NAME` để giới hạn phạm vi. Tránh truy vấn toàn bộ metadata của server khi chỉ cần một database.

Ví dụ, liệt kê schema nghiệp vụ và bỏ qua các schema hệ thống:

```sql
SELECT SCHEMA_NAME
FROM INFORMATION_SCHEMA.SCHEMATA
WHERE SCHEMA_NAME NOT IN (
    'information_schema',
    'mysql',
    'performance_schema',
    'sys'
)
ORDER BY SCHEMA_NAME;
```

Không nên phụ thuộc vào một thứ tự ngầm định của kết quả. Nếu cần báo cáo ổn định, luôn chỉ rõ `ORDER BY`.

## 3. Kiểm kê schema và table

### 3.1. Danh sách database

View `SCHEMATA` cung cấp tên schema và một số thuộc tính mặc định như character set, collation và SQL path.

```sql
SELECT
    SCHEMA_NAME,
    DEFAULT_CHARACTER_SET_NAME,
    DEFAULT_COLLATION_NAME
FROM INFORMATION_SCHEMA.SCHEMATA
WHERE SCHEMA_NAME = 'shop';
```

Thông tin charset/collation ở cấp schema là mặc định cho đối tượng được tạo sau đó. Một table hoặc column có thể khai báo charset/collation riêng, nên không thể dùng kết quả này để kết luận tất cả cột trong schema có cùng collation.

### 3.2. Danh sách table và view

View `TABLES` mô tả cả table cơ sở và view:

```sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    TABLE_TYPE,
    ENGINE,
    TABLE_COLLATION,
    CREATE_TIME,
    UPDATE_TIME
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = 'shop'
ORDER BY TABLE_TYPE, TABLE_NAME;
```

`TABLE_TYPE` thường cho biết đối tượng là `BASE TABLE` hay `VIEW`. `ENGINE` cho biết storage engine của table; với view, giá trị này thường là NULL.

Một số cột trong `TABLES` cần được hiểu cẩn thận:

- `TABLE_ROWS` với InnoDB là ước lượng, không phải số hàng chính xác.
- `DATA_LENGTH` và `INDEX_LENGTH` biểu diễn kích thước dữ liệu và index theo cách storage engine báo cáo; không phải lúc nào cũng bằng dung lượng file mà bạn nhìn thấy trên filesystem.
- `DATA_FREE` là thông tin về không gian trống theo cách engine báo cáo, không phải số byte có thể lập tức thu hồi bằng một thao tác đơn giản.
- `UPDATE_TIME` có thể là NULL hoặc không phản ánh chính xác thời điểm cập nhật gần nhất, đặc biệt với InnoDB.
- `CREATE_TIME` và các thống kê khác phụ thuộc engine và phiên bản.

Nếu cần số hàng chính xác cho một table, hãy truy vấn `COUNT(*)` trên chính table đó. Trên bảng lớn, phép đếm có thể tốn I/O và thời gian; hãy cân nhắc tải hệ thống trước khi chạy.

### 3.3. Báo cáo dung lượng theo schema

Có thể tổng hợp kích thước mà metadata báo cáo:

```sql
SELECT
    TABLE_SCHEMA,
    COUNT(*) AS table_count,
    ROUND(SUM(DATA_LENGTH) / 1024 / 1024, 2) AS data_mb,
    ROUND(SUM(INDEX_LENGTH) / 1024 / 1024, 2) AS index_mb,
    ROUND(SUM(DATA_LENGTH + INDEX_LENGTH) / 1024 / 1024, 2) AS total_mb,
    SUM(TABLE_ROWS) AS estimated_rows
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_TYPE = 'BASE TABLE'
  AND TABLE_SCHEMA = 'shop'
GROUP BY TABLE_SCHEMA;
```

Đây là số liệu ước lượng/engine-reported để kiểm kê và so sánh xu hướng. Không cộng `TABLE_ROWS` rồi xem đó là tổng số hàng chính xác của InnoDB. Nếu cần báo cáo dung lượng toàn server, có thể bỏ điều kiện schema nhưng vẫn nên loại các schema hệ thống và hiểu rõ cách engine báo cáo.

## 4. Tra cứu column và kiểu dữ liệu

View `COLUMNS` là một trong những view được dùng thường xuyên nhất. Nó cho biết mỗi cột thuộc table nào, thứ tự xuất hiện, kiểu dữ liệu, khả năng nhận NULL, default và thuộc tính charset/collation.

```sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    ORDINAL_POSITION,
    COLUMN_NAME,
    COLUMN_TYPE,
    IS_NULLABLE,
    COLUMN_DEFAULT,
    EXTRA,
    CHARACTER_SET_NAME,
    COLLATION_NAME
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'shop'
  AND TABLE_NAME = 'orders'
ORDER BY ORDINAL_POSITION;
```

Các cột quan trọng:

- `COLUMN_NAME`: tên cột.
- `ORDINAL_POSITION`: vị trí cột trong định nghĩa table, bắt đầu từ 1.
- `DATA_TYPE`: kiểu dữ liệu cơ sở, chẳng hạn `int`, `varchar`, `decimal`.
- `COLUMN_TYPE`: biểu diễn chi tiết hơn, có thể gồm độ dài, precision, unsigned hoặc thuộc tính enum/set.
- `IS_NULLABLE`: cho biết cột có cho phép NULL hay không.
- `COLUMN_DEFAULT`: giá trị mặc định mà metadata báo cáo.
- `EXTRA`: thuộc tính bổ sung như `auto_increment`, generated column hoặc thuộc tính khác tùy phiên bản.
- `CHARACTER_SET_NAME` và `COLLATION_NAME`: thuộc tính chuỗi ở cấp column.

Lưu ý: `COLUMN_DEFAULT` có thể là NULL khi cột có default NULL hoặc khi định nghĩa không có mệnh đề DEFAULT. Nếu cần phân biệt chính xác các chi tiết cú pháp, hãy đối chiếu `SHOW CREATE TABLE`.

Ví dụ tìm các cột chuỗi có collation khác với collation mặc định của schema:

```sql
SELECT
    c.TABLE_NAME,
    c.COLUMN_NAME,
    c.COLUMN_TYPE,
    c.CHARACTER_SET_NAME,
    c.COLLATION_NAME
FROM INFORMATION_SCHEMA.COLUMNS AS c
JOIN INFORMATION_SCHEMA.SCHEMATA AS s
  ON s.SCHEMA_NAME = c.TABLE_SCHEMA
WHERE c.TABLE_SCHEMA = 'shop'
  AND c.COLLATION_NAME IS NOT NULL
  AND c.COLLATION_NAME <> s.DEFAULT_COLLATION_NAME
ORDER BY c.TABLE_NAME, c.ORDINAL_POSITION;
```

Truy vấn này hỗ trợ tìm điểm khác biệt cần xem xét. Một collation khác không nhất thiết là lỗi; có thể đó là quyết định nghiệp vụ. Hãy kiểm tra lý do trước khi chuẩn hóa.

### 4.1. Tìm cột có kiểu dữ liệu cần rà soát

Ví dụ tìm cột dùng kiểu `TEXT` hoặc `BLOB` trong một schema:

```sql
SELECT
    TABLE_NAME,
    COLUMN_NAME,
    DATA_TYPE,
    COLUMN_TYPE,
    IS_NULLABLE
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'shop'
  AND DATA_TYPE IN ('text', 'mediumtext', 'longtext',
                    'blob', 'mediumblob', 'longblob')
ORDER BY TABLE_NAME, ORDINAL_POSITION;
```

Metadata giúp lập danh sách để review. Quyết định kiểu dữ liệu cần dựa trên kích thước dữ liệu, cách truy vấn, index, charset và yêu cầu nghiệp vụ; không nên tự động đổi kiểu chỉ vì một truy vấn kiểm kê phát hiện nó.

## 5. Tra cứu index

View `STATISTICS` cung cấp metadata về index. Mỗi key part thường là một hàng, vì vậy index nhiều cột xuất hiện trên nhiều hàng theo `SEQ_IN_INDEX`. Truy vấn dưới đây dùng `IS_VISIBLE`, phù hợp với phiên bản MySQL hỗ trợ invisible index; nếu công cụ phải chạy trên phiên bản cũ hơn, hãy bỏ cột này khỏi danh sách SELECT.

```sql
SELECT
    TABLE_NAME,
    INDEX_NAME,
    NON_UNIQUE,
    SEQ_IN_INDEX,
    COLUMN_NAME,
    COLLATION,
    CARDINALITY,
    SUB_PART,
    INDEX_TYPE,
    IS_VISIBLE
FROM INFORMATION_SCHEMA.STATISTICS
WHERE TABLE_SCHEMA = 'shop'
ORDER BY TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX;
```

Ý nghĩa một số cột:

- `INDEX_NAME`: tên index; `PRIMARY` là primary key.
- `NON_UNIQUE = 0`: index có tính duy nhất; `1`: index không yêu cầu duy nhất.
- `SEQ_IN_INDEX`: vị trí của key part trong index ghép.
- `COLUMN_NAME`: cột được index; có thể NULL với một số functional key part.
- `SUB_PART`: độ dài prefix nếu index chỉ một phần của cột.
- `CARDINALITY`: ước lượng số giá trị khác nhau trong index; không phải số liệu chính xác cố định.
- `INDEX_TYPE`: loại index, thường gặp như BTREE.
- `IS_VISIBLE`: trạng thái visible/invisible của index trên các phiên bản hỗ trợ.

Ví dụ, nếu index `idx_customer_created` có `customer_id` ở vị trí 1 và `created_at` ở vị trí 2, đó là index ghép theo thứ tự hai cột ấy. Thứ tự key part ảnh hưởng đến khả năng dùng index cho điều kiện lọc và sắp xếp; chỉ nhìn thấy hai cột có trong index chưa đủ để kết luận index phù hợp.

### 5.1. Tìm table không có primary key

Primary key giúp định danh hàng và là nền tảng quan trọng cho InnoDB clustered index. Có thể lập danh sách table cơ sở chưa khai báo primary key:

```sql
SELECT
    t.TABLE_SCHEMA,
    t.TABLE_NAME,
    t.ENGINE
FROM INFORMATION_SCHEMA.TABLES AS t
LEFT JOIN INFORMATION_SCHEMA.TABLE_CONSTRAINTS AS tc
  ON tc.TABLE_SCHEMA = t.TABLE_SCHEMA
 AND tc.TABLE_NAME = t.TABLE_NAME
 AND tc.CONSTRAINT_TYPE = 'PRIMARY KEY'
WHERE t.TABLE_SCHEMA = 'shop'
  AND t.TABLE_TYPE = 'BASE TABLE'
  AND tc.CONSTRAINT_NAME IS NULL
ORDER BY t.TABLE_NAME;
```

Kết quả là danh sách cần review. Một table không có primary key có thể là thiết kế có chủ đích, nhưng với InnoDB, cần cân nhắc định danh hàng, secondary index, replication và khả năng cập nhật/xóa chính xác. Đừng tự động thêm primary key mà chưa xác định khóa tự nhiên hay khóa thay thế phù hợp.

### 5.2. Tìm index theo table

Để kiểm tra một table cụ thể, có thể dùng cả INFORMATION_SCHEMA và lệnh SHOW:

```sql
SELECT
    INDEX_NAME,
    NON_UNIQUE,
    SEQ_IN_INDEX,
    COLUMN_NAME,
    CARDINALITY,
    INDEX_TYPE,
    IS_VISIBLE
FROM INFORMATION_SCHEMA.STATISTICS
WHERE TABLE_SCHEMA = 'shop'
  AND TABLE_NAME = 'orders'
ORDER BY INDEX_NAME, SEQ_IN_INDEX;

SHOW INDEX FROM shop.orders;
```

Kết quả metadata mô tả cấu trúc index, nhưng không chứng minh optimizer sẽ dùng index cho một truy vấn cụ thể. Để đánh giá kế hoạch thực thi, hãy chạy `EXPLAIN` trên câu truy vấn thực tế và đối chiếu với dữ liệu, thống kê và workload.

## 6. Tra cứu constraint và quan hệ khóa ngoại

Metadata constraint thường cần kết hợp nhiều view:

- `TABLE_CONSTRAINTS` cho biết loại constraint.
- `KEY_COLUMN_USAGE` cho biết cột tham gia constraint và thông tin cột được tham chiếu.
- `REFERENTIAL_CONSTRAINTS` cung cấp hành vi tham chiếu như ON UPDATE và ON DELETE.
- `CHECK_CONSTRAINTS` cung cấp biểu thức check constraint trên các phiên bản hỗ trợ.

Liệt kê constraint trong một schema:

```sql
SELECT
    TABLE_NAME,
    CONSTRAINT_NAME,
    CONSTRAINT_TYPE
FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
WHERE TABLE_SCHEMA = 'shop'
ORDER BY TABLE_NAME, CONSTRAINT_TYPE, CONSTRAINT_NAME;
```

### 6.1. Xem quan hệ foreign key

```sql
SELECT
    kcu.TABLE_NAME,
    kcu.CONSTRAINT_NAME,
    kcu.COLUMN_NAME,
    kcu.ORDINAL_POSITION,
    kcu.REFERENCED_TABLE_SCHEMA,
    kcu.REFERENCED_TABLE_NAME,
    kcu.REFERENCED_COLUMN_NAME,
    rc.UPDATE_RULE,
    rc.DELETE_RULE
FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE AS kcu
LEFT JOIN INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS AS rc
  ON rc.CONSTRAINT_SCHEMA = kcu.CONSTRAINT_SCHEMA
 AND rc.TABLE_NAME = kcu.TABLE_NAME
 AND rc.CONSTRAINT_NAME = kcu.CONSTRAINT_NAME
WHERE kcu.TABLE_SCHEMA = 'shop'
  AND kcu.REFERENCED_TABLE_NAME IS NOT NULL
ORDER BY kcu.TABLE_NAME, kcu.CONSTRAINT_NAME, kcu.ORDINAL_POSITION;
```

Với khóa ngoại ghép, mỗi cột là một hàng. `ORDINAL_POSITION` giúp ghép đúng thứ tự cột nguồn và cột đích. `UPDATE_RULE` và `DELETE_RULE` cho biết hành vi tham chiếu, ví dụ `CASCADE`, `RESTRICT`, `NO ACTION` hoặc `SET NULL`, tùy constraint.

### 6.2. Tra cứu check constraint

Trên MySQL 8.0.16 trở lên, check constraint được thực thi và có thể tra cứu trong INFORMATION_SCHEMA:

```sql
SELECT
    tc.TABLE_NAME,
    tc.CONSTRAINT_NAME,
    tc.CONSTRAINT_TYPE,
    cc.CHECK_CLAUSE,
    cc.ENFORCED
FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS AS tc
JOIN INFORMATION_SCHEMA.CHECK_CONSTRAINTS AS cc
  ON cc.CONSTRAINT_SCHEMA = tc.CONSTRAINT_SCHEMA
 AND cc.CONSTRAINT_NAME = tc.CONSTRAINT_NAME
WHERE tc.TABLE_SCHEMA = 'shop'
  AND tc.CONSTRAINT_TYPE = 'CHECK'
ORDER BY tc.TABLE_NAME, tc.CONSTRAINT_NAME;
```

Nếu phải hỗ trợ phiên bản MySQL cũ hơn, hãy kiểm tra khả năng hỗ trợ CHECK trước khi dùng truy vấn này. Ở những phiên bản cũ, cú pháp CHECK có thể được chấp nhận nhưng không được thực thi như mong đợi.

## 7. Tra cứu view, routine, trigger và event

Schema không chỉ có table. Một hệ thống có thể chứa view, stored procedure, function, trigger và event. Các view metadata tương ứng giúp kiểm kê những đối tượng này.

### 7.1. View

```sql
SELECT
    TABLE_NAME AS VIEW_NAME,
    DEFINER,
    SECURITY_TYPE,
    CHECK_OPTION,
    IS_UPDATABLE,
    VIEW_DEFINITION
FROM INFORMATION_SCHEMA.VIEWS
WHERE TABLE_SCHEMA = 'shop'
ORDER BY TABLE_NAME;
```

`VIEW_DEFINITION` mô tả câu SELECT tạo view. Nội dung định nghĩa có thể không hiển thị đầy đủ nếu tài khoản không có quyền thích hợp. Dùng `SHOW CREATE VIEW shop.view_name` để xem định nghĩa của một view cụ thể khi được cấp quyền.

### 7.2. Stored procedure và function

```sql
SELECT
    ROUTINE_NAME,
    ROUTINE_TYPE,
    DEFINER,
    SECURITY_TYPE,
    SQL_DATA_ACCESS,
    IS_DETERMINISTIC,
    CREATED,
    LAST_ALTERED
FROM INFORMATION_SCHEMA.ROUTINES
WHERE ROUTINE_SCHEMA = 'shop'
ORDER BY ROUTINE_TYPE, ROUTINE_NAME;
```

Có thể truy vấn thêm `ROUTINE_DEFINITION` khi cần đọc phần thân routine và tài khoản có quyền tương ứng. Không nên đưa định nghĩa routine chứa logic nhạy cảm vào báo cáo rộng rãi.

### 7.3. Trigger và event

```sql
SELECT
    TRIGGER_NAME,
    EVENT_MANIPULATION,
    EVENT_OBJECT_TABLE,
    ACTION_TIMING,
    ACTION_ORIENTATION,
    DEFINER
FROM INFORMATION_SCHEMA.TRIGGERS
WHERE TRIGGER_SCHEMA = 'shop'
ORDER BY EVENT_OBJECT_TABLE, TRIGGER_NAME;
```

```sql
SELECT
    EVENT_NAME,
    DEFINER,
    STATUS,
    EVENT_TYPE,
    EXECUTE_AT,
    INTERVAL_VALUE,
    INTERVAL_FIELD,
    LAST_EXECUTED
FROM INFORMATION_SCHEMA.EVENTS
WHERE EVENT_SCHEMA = 'shop'
ORDER BY EVENT_NAME;
```

Metadata của event cho biết lịch và trạng thái khai báo. Để event chạy, Event Scheduler của server cũng phải được bật. Một event có trạng thái ENABLED trong metadata không đồng nghĩa chắc chắn scheduler đang hoạt động.

## 8. Tra cứu partition

Với table được partition, view `PARTITIONS` cung cấp tên partition, phương thức partition, biểu thức partition và một số thống kê:

```sql
SELECT
    TABLE_NAME,
    PARTITION_NAME,
    SUBPARTITION_NAME,
    PARTITION_METHOD,
    PARTITION_EXPRESSION,
    TABLE_ROWS,
    DATA_LENGTH,
    INDEX_LENGTH
FROM INFORMATION_SCHEMA.PARTITIONS
WHERE TABLE_SCHEMA = 'shop'
  AND PARTITION_NAME IS NOT NULL
ORDER BY TABLE_NAME, PARTITION_ORDINAL_POSITION;
```

Các thống kê hàng và kích thước theo partition có thể là ước lượng, nhất là với InnoDB. Metadata giúp kiểm tra table có được partition theo dự kiến hay không; để đánh giá partition pruning, hãy xem kế hoạch thực thi của truy vấn bằng `EXPLAIN`.

## 9. Tra cứu quyền ở các phạm vi

INFORMATION_SCHEMA cung cấp các view về quyền được cấp, ví dụ:

- `USER_PRIVILEGES`: quyền ở phạm vi toàn cục.
- `SCHEMA_PRIVILEGES`: quyền ở phạm vi schema.
- `TABLE_PRIVILEGES`: quyền ở phạm vi table.
- `COLUMN_PRIVILEGES`: quyền ở phạm vi column.

Ví dụ kiểm tra quyền table trong schema:

```sql
SELECT
    GRANTEE,
    TABLE_SCHEMA,
    TABLE_NAME,
    PRIVILEGE_TYPE,
    IS_GRANTABLE
FROM INFORMATION_SCHEMA.TABLE_PRIVILEGES
WHERE TABLE_SCHEMA = 'shop'
ORDER BY GRANTEE, TABLE_NAME, PRIVILEGE_TYPE;
```

Có thể kết hợp thêm `SCHEMA_PRIVILEGES` và `COLUMN_PRIVILEGES` để rà soát các phạm vi khác. Khi xác minh quyền hiệu lực của một tài khoản cụ thể, `SHOW GRANTS FOR CURRENT_USER()` hoặc `SHOW GRANTS FOR 'user'@'host'` thường là điểm bắt đầu dễ hiểu. Hãy lưu ý vai trò (roles), quyền kế thừa và ngữ cảnh xác thực khi diễn giải quyền hiệu lực.

## 10. Dùng INFORMATION_SCHEMA trong công việc thực tế

### 10.1. Tạo danh mục schema

Một công cụ tài liệu hóa có thể chạy các truy vấn theo trình tự:

1. Lấy danh sách schema từ `SCHEMATA`.
2. Lấy danh sách table và view từ `TABLES`.
3. Lấy cột từ `COLUMNS`.
4. Lấy index từ `STATISTICS`.
5. Lấy constraint và quan hệ từ `TABLE_CONSTRAINTS`, `KEY_COLUMN_USAGE` và `REFERENTIAL_CONSTRAINTS`.
6. Lấy định nghĩa view/routine/trigger nếu có quyền và thực sự cần.
7. Xuất thành Markdown, HTML hoặc một data catalog nội bộ.

Khi tạo tài liệu, nên ghi lại phiên bản MySQL, thời điểm thu thập và tài khoản thực hiện. Điều này giúp người đọc hiểu tài liệu phản ánh môi trường nào và có thể thiếu đối tượng mà tài khoản không nhìn thấy.

### 10.2. Kiểm tra schema drift giữa các môi trường

Schema drift là tình trạng cấu trúc giữa dev, test, staging và production không còn đồng nhất theo phiên bản mong muốn. Có thể dùng truy vấn metadata để thu thập:

- Tên table và view.
- Column, type, nullability và default.
- Index, thứ tự key part và trạng thái visible.
- Constraint, quan hệ foreign key và rule.
- Engine, charset và collation.

Sau đó chuẩn hóa kết quả và so sánh giữa các môi trường. Không nên so sánh bằng cách lấy nguyên mọi cột của INFORMATION_SCHEMA.TABLES, vì nhiều trường là thống kê động hoặc phụ thuộc engine. Hãy chọn các thuộc tính định nghĩa schema có ý nghĩa, đồng thời bỏ qua các giá trị runtime như row estimate và thời điểm cập nhật.

Khi phát hiện drift, xác định nguồn chuẩn là migration đã version hóa hoặc schema mong muốn trong repository. Tạo migration để sửa khác biệt sau khi review; tránh chỉnh tay production rồi để các môi trường còn lại lệch theo.

### 10.3. Kiểm tra trước và sau migration

Trước migration, lưu metadata của các đối tượng sẽ bị ảnh hưởng. Sau migration, chạy lại các truy vấn tương ứng và so sánh:

- Cột mới đã xuất hiện đúng kiểu và thứ tự chưa?
- Index đã có đủ key part và đúng thứ tự chưa?
- Foreign key trỏ đến đúng table/column chưa?
- Constraint đã được tạo và được enforce chưa?
- Table vẫn dùng đúng storage engine, charset và collation chưa?

Đối với DDL lớn, metadata chỉ xác nhận cấu trúc. Bạn vẫn cần kiểm tra dữ liệu thực tế, kết quả truy vấn, thời gian thực thi và trạng thái ứng dụng.

## 11. Quyền nhìn thấy và giới hạn của metadata

### 11.1. Metadata visibility phụ thuộc quyền

MySQL không nhất thiết hiển thị mọi đối tượng của server cho mọi tài khoản. Người dùng thường chỉ nhìn thấy metadata của các đối tượng mà họ có quyền truy cập. Vì vậy:

- Một table không xuất hiện trong kết quả chưa chắc là table không tồn tại.
- Hai tài khoản khác nhau có thể nhận kết quả kiểm kê khác nhau.
- Tài khoản dùng để tạo data catalog cần được cấp quyền đọc metadata phù hợp với phạm vi cần lập danh mục.
- Không nên cấp quyền quản trị toàn server chỉ để một công cụ báo cáo đọc metadata.

Khi kết quả có vẻ thiếu, kiểm tra tài khoản đang kết nối và quyền:

```sql
SELECT USER(), CURRENT_USER();
SHOW GRANTS FOR CURRENT_USER();
```

### 11.2. Metadata và thống kê không giống nhau

Một số giá trị trong INFORMATION_SCHEMA mô tả định nghĩa tương đối ổn định; một số khác là thống kê do storage engine cung cấp. Ví dụ, `TABLE_ROWS` và `STATISTICS.CARDINALITY` của InnoDB là ước lượng. Chúng hữu ích để kiểm kê và định hướng điều tra nhưng không nên dùng như số liệu chính xác cho đối soát nghiệp vụ.

Trên MySQL 8.0, biến `information_schema_stats_expiry` điều khiển thời gian cache thống kê table trong INFORMATION_SCHEMA. Có thể xem giá trị hiện tại:

```sql
SHOW VARIABLES LIKE 'information_schema_stats_expiry';
```

Nếu thực sự cần yêu cầu lấy thống kê mới từ storage engine cho session hiện tại, có thể đặt:

```sql
SET SESSION information_schema_stats_expiry = 0;
```

Giá trị 0 làm giảm tác dụng cache và có thể khiến truy vấn metadata tốn thêm công việc. Thống kê mới vẫn có thể là ước lượng; thiết lập này không biến `TABLE_ROWS` thành phép đếm chính xác. Chỉ dùng khi có lý do và cân nhắc tác động lên server.

### 11.3. Tránh truy vấn metadata quá rộng

Một truy vấn INFORMATION_SCHEMA trên server có hàng chục nghìn table có thể tạo tải đáng kể, đặc biệt khi lấy thống kê engine hoặc định nghĩa đối tượng. Thực hành tốt:

- Lọc theo schema và table càng sớm càng tốt.
- Chỉ chọn cột cần dùng, tránh `SELECT *`.
- Không chạy kiểm kê dày đặc theo chu kỳ ngắn nếu schema ít thay đổi.
- Phân trang hoặc chia nhỏ theo schema/table khi công cụ cần xử lý lượng metadata lớn.
- Chạy báo cáo nặng ở thời điểm phù hợp và theo dõi thời gian thực thi.
- Không coi truy vấn metadata là hoàn toàn miễn phí chỉ vì nó không đọc trực tiếp bảng nghiệp vụ.

Nếu DDL đang diễn ra đồng thời, kết quả của nhiều truy vấn thu thập ở các thời điểm khác nhau có thể không còn mô tả cùng một phiên bản schema. Hãy ghi nhận thời điểm và phiên bản migration, hoặc chạy lại phần kiểm tra sau khi thay đổi cấu trúc kết thúc.

## 12. INFORMATION_SCHEMA và các lệnh SHOW

INFORMATION_SCHEMA phù hợp với truy vấn có điều kiện, JOIN, tổng hợp và tự động hóa. Các lệnh SHOW thường nhanh để kiểm tra thủ công một đối tượng.

| Nhu cầu | INFORMATION_SCHEMA | Lệnh SHOW tương ứng |
|---|---|---|
| Liệt kê table | `INFORMATION_SCHEMA.TABLES` | `SHOW TABLES FROM shop` |
| Xem định nghĩa table | `COLUMNS`, `STATISTICS`, constraint views | `SHOW CREATE TABLE shop.orders` |
| Xem index | `STATISTICS` | `SHOW INDEX FROM shop.orders` |
| Xem view | `VIEWS` | `SHOW CREATE VIEW shop.some_view` |
| Xem quyền | Các view PRIVILEGES | `SHOW GRANTS` |
| Xem engine | `TABLES.ENGINE` | `SHOW TABLE STATUS FROM shop` |

Để xem định nghĩa đầy đủ của một table, `SHOW CREATE TABLE` thường là nguồn dễ đọc và trực tiếp. INFORMATION_SCHEMA phát huy ưu thế khi cần tìm kiếm nhiều đối tượng, nối metadata hoặc tạo báo cáo có cấu trúc.

## 13. Bài tập thực hành

Giả sử có schema `shop` gồm các table `customers`, `orders`, `order_items` và `products`.

### Bài 1: Lập danh mục schema

Viết truy vấn lấy tất cả table và view trong `shop`, kèm loại đối tượng và storage engine. Giải thích vì sao view không có engine như table cơ sở.

### Bài 2: Tạo báo cáo column

Liệt kê column của `orders` theo thứ tự, gồm kiểu dữ liệu, nullable, default, extra và collation. Xác định cột nào là generated hoặc auto increment nếu có.

### Bài 3: Kiểm tra index

Liệt kê index của `orders` theo thứ tự key part. Xác định primary key, unique index và index ghép. Giải thích vì sao thứ tự cột trong index ghép quan trọng.

### Bài 4: Vẽ quan hệ khóa ngoại

Dùng `KEY_COLUMN_USAGE` để liệt kê các foreign key của `order_items`. Vẽ quan hệ từ table nguồn đến table đích và xác định ON DELETE/ON UPDATE.

### Bài 5: Tìm table chưa có primary key

Chạy truy vấn ở mục 5.1 trên schema thử nghiệm. Review từng table được tìm thấy và quyết định có cần primary key hay không.

### Bài 6: Kiểm tra schema drift

Chạy các truy vấn metadata tương ứng trên dev và test. So sánh column, index và constraint của cùng một table. Tạo báo cáo chỉ ra khác biệt và đề xuất migration sửa chúng.

### Bài 7: Kiểm tra quyền nhìn thấy

Tạo một tài khoản chỉ có quyền trên một số table. So sánh kết quả truy vấn INFORMATION_SCHEMA.TABLES khi đăng nhập bằng tài khoản đó và bằng tài khoản quản trị. Giải thích vì sao danh sách metadata có thể khác nhau.

## 14. Tự kiểm tra

1. INFORMATION_SCHEMA khác với database nghiệp vụ như thế nào?
2. View nào dùng để tra cứu column, index và foreign key?
3. Vì sao `TABLE_ROWS` của InnoDB không thể dùng làm số hàng chính xác?
4. Một index ghép xuất hiện thành nhiều hàng trong STATISTICS. Cột nào cho biết thứ tự key part?
5. Vì sao một table không xuất hiện trong INFORMATION_SCHEMA chưa chắc đã không tồn tại?
6. Khi nào nên dùng SHOW CREATE TABLE thay vì chỉ đọc COLUMNS và STATISTICS?
7. Vì sao cần ghi phiên bản MySQL và thời điểm thu thập khi xuất data catalog?

**Đáp án gợi ý:** (1) INFORMATION_SCHEMA cung cấp metadata chỉ đọc về các đối tượng và thuộc tính hệ thống. (2) COLUMNS, STATISTICS, KEY_COLUMN_USAGE kết hợp TABLE_CONSTRAINTS/REFERENTIAL_CONSTRAINTS. (3) Đây là ước lượng của storage engine. (4) SEQ_IN_INDEX. (5) Metadata visibility phụ thuộc quyền tài khoản. (6) Khi cần định nghĩa table đầy đủ, dễ kiểm tra và giữ các chi tiết cú pháp. (7) Để biết báo cáo phản ánh phiên bản và thời điểm nào, nhất là khi schema có thể thay đổi.


