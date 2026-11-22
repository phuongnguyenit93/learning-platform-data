# Đổi tên, đổi kiểu, thêm ràng buộc và xử lý đối tượng phụ thuộc

> **Chủ đề:** Database Engine Relational Oracle  
> **Chương:** Thay đổi và nâng cấp  
> **Mục tiêu:** Thực hiện thay đổi schema Oracle có kiểm soát; đổi tên bảng/cột, chuyển đổi datatype, thêm hoặc thay đổi constraint; xác định các object và ứng dụng phụ thuộc; hiểu tác động của DDL, invalidation, index, view, trigger, PL/SQL và synonym; lập kế hoạch tương thích ngược, kiểm thử, cutover và phục hồi sau thay đổi.

## 1. Schema là hợp đồng giữa database và ứng dụng

Schema không chỉ là danh sách bảng và cột. Nó là hợp đồng được nhiều thành phần sử dụng:

- Ứng dụng Java, Spring Boot, JPA/Hibernate và batch jobs.
- View, materialized view, trigger, package, procedure và function.
- Foreign key, primary key, unique/check constraint và index.
- Synonym, database link và stored SQL.
- ETL, BI/reporting, Data Pump, scheduler jobs và hệ thống tích hợp.
- Công cụ giám sát, audit, replication và migration.

Một thay đổi tưởng nhỏ như đổi tên cột có thể làm hỏng câu SQL trong ứng dụng, view hoặc package. Đổi kiểu dữ liệu có thể làm thay đổi cách so sánh, sắp xếp, tính toán, index access và mapping JDBC. Thêm constraint có thể thất bại vì dữ liệu cũ không thỏa điều kiện.

Vì vậy, schema evolution cần trả lời bốn câu hỏi:

1. Thay đổi chính xác là gì và tại sao cần?
2. Những object, ứng dụng và quy trình nào phụ thuộc vào phần thay đổi?
3. Làm sao triển khai mà vẫn tương thích trong thời gian chuyển đổi?
4. Làm sao xác minh và phục hồi nếu một bước thất bại?

**DDL của Oracle có implicit commit.** Không thể giả định một migration chứa nhiều câu DDL sẽ rollback toàn bộ như một transaction DML.

## 2. Phân loại thay đổi trước khi triển khai

| Nhóm thay đổi | Ví dụ | Rủi ro chính |
|---|---|---|
| Đổi tên object | RENAME TABLE, RENAME COLUMN | SQL, view, package và ứng dụng tham chiếu tên cũ |
| Tăng/giảm độ dài | VARCHAR2(100) lên VARCHAR2(300) | Storage, index key length, client validation |
| Đổi datatype | VARCHAR2 sang NUMBER, DATE sang TIMESTAMP | Chuyển đổi dữ liệu, precision, null, index và constraint |
| Thêm constraint | NOT NULL, CHECK, UNIQUE, FK | Dữ liệu hiện tại không hợp lệ, lock và validation cost |
| Sửa constraint | ENABLE/DISABLE, VALIDATE/NOVALIDATE | Enforcement khác nhau giữa dữ liệu cũ và mới |
| Thay đổi key | Đổi PK/UK hoặc FK | Quan hệ tham chiếu, index và ứng dụng |
| Thay đổi cấu trúc lớn | Tách bảng, gộp bảng, partitioning | Data migration, cutover và tương thích nhiều phiên bản |

Không áp dụng một quy trình giống nhau cho tất cả thay đổi. Rename thường chủ yếu tác động metadata/dependency; datatype conversion và constraint validation có thể cần quét hoặc cập nhật lượng dữ liệu lớn.

## 3. Khảo sát schema trước khi sửa

Trước khi viết ALTER TABLE, thu thập trạng thái hiện tại để có baseline và biết những gì cần kiểm tra sau thay đổi.

### 3.1. Xác nhận database và schema

~~~sql
SELECT name,
       db_unique_name,
       database_role,
       open_mode
FROM v$database;

SELECT sys_context('USERENV', 'SESSION_USER') AS session_user,
       sys_context('USERENV', 'CURRENT_SCHEMA') AS current_schema,
       sys_context('USERENV', 'CON_NAME') AS con_name
FROM dual;
~~~

Đảm bảo đang làm trên đúng database, PDB, schema và môi trường. Nhiều sự cố migration bắt đầu từ việc chạy đúng script trên nhầm service hoặc nhầm container.

### 3.2. Lưu DDL hiện tại

Dùng DBMS_METADATA để trích xuất định nghĩa object trước thay đổi:

~~~sql
SELECT DBMS_METADATA.GET_DDL(
           'TABLE',
           'ORDERS',
           'APP_OWNER'
       )
FROM dual;
~~~

Có thể lấy DDL cho index, constraint hoặc view theo object type tương ứng. Lưu output vào change record hoặc hệ thống version control nội bộ, theo chính sách bảo mật.

DBMS_METADATA là bằng chứng về định nghĩa hiện tại, không phải backup dữ liệu và không thay thế RMAN backup.

### 3.3. Liệt kê column và datatype

~~~sql
SELECT owner,
       table_name,
       column_id,
       column_name,
       data_type,
       data_length,
       char_length,
       char_used,
       data_precision,
       data_scale,
       nullable,
       data_default
FROM dba_tab_columns
WHERE owner = 'APP_OWNER'
  AND table_name = 'ORDERS'
ORDER BY column_id;
~~~

Các cột metadata giúp phân biệt byte length và character length. Với VARCHAR2, CHAR_USED cho biết length semantics theo BYTE hay CHAR.

### 3.4. Liệt kê constraints

~~~sql
SELECT owner,
       table_name,
       constraint_name,
       constraint_type,
       status,
       validated,
       deferrable,
       deferred,
       delete_rule,
       search_condition
FROM dba_constraints
WHERE owner = 'APP_OWNER'
  AND table_name = 'ORDERS'
ORDER BY constraint_type, constraint_name;
~~~

Constraint type thường gặp:

- P: Primary key.
- U: Unique.
- R: Referential integrity/foreign key.
- C: Check constraint, bao gồm NOT NULL được biểu diễn qua metadata tương ứng.

Xem các cột thuộc constraint:

~~~sql
SELECT owner,
       table_name,
       constraint_name,
       column_name,
       position
FROM dba_cons_columns
WHERE owner = 'APP_OWNER'
  AND table_name = 'ORDERS'
ORDER BY constraint_name, position;
~~~

### 3.5. Liệt kê index

~~~sql
SELECT owner,
       index_name,
       index_type,
       table_name,
       uniqueness,
       status,
       visibility,
       tablespace_name
FROM dba_indexes
WHERE table_owner = 'APP_OWNER'
  AND table_name = 'ORDERS'
ORDER BY index_name;
~~~

Xem index column:

~~~sql
SELECT index_owner,
       index_name,
       table_owner,
       table_name,
       column_name,
       column_position,
       descend
FROM dba_ind_columns
WHERE table_owner = 'APP_OWNER'
  AND table_name = 'ORDERS'
ORDER BY index_name, column_position;
~~~

Không kết luận index vẫn tối ưu chỉ vì trạng thái VALID. Sau đổi datatype hoặc phân bố dữ liệu, cần đánh giá execution plan và statistics.

## 4. Tìm object phụ thuộc

Oracle lưu dependency metadata cho nhiều loại object. DBA_DEPENDENCIES là điểm bắt đầu, nhưng không phải công cụ tìm mọi tham chiếu có thể tồn tại.

### 4.1. DBA_DEPENDENCIES

~~~sql
SELECT owner,
       name,
       type,
       referenced_owner,
       referenced_name,
       referenced_type,
       dependency_type
FROM dba_dependencies
WHERE referenced_owner = 'APP_OWNER'
  AND referenced_name = 'ORDERS'
ORDER BY owner, type, name;
~~~

Kết quả có thể chỉ ra view, package, procedure, function, trigger hoặc object khác tham chiếu tới bảng.

Dependency metadata không phát hiện mọi chuỗi SQL được ghép động, SQL nằm trong file ứng dụng, ETL bên ngoài hoặc query được tạo bởi công cụ BI.

### 4.2. Tìm source PL/SQL

~~~sql
SELECT owner,
       name,
       type,
       line,
       text
FROM dba_source
WHERE UPPER(text) LIKE '%ORDERS%'
ORDER BY owner, name, type, line;
~~~

Đây là tìm kiếm văn bản thô. Có thể trả false positive vì tên xuất hiện trong comment/string, và bỏ sót tham chiếu được chia qua nhiều dòng hoặc được tạo động.

### 4.3. Tìm view

~~~sql
SELECT owner,
       view_name,
       text_length
FROM dba_views
WHERE owner IN ('APP_OWNER', 'REPORT_OWNER')
ORDER BY owner, view_name;
~~~

Có thể đọc DBA_VIEWS.TEXT hoặc dùng DBMS_METADATA.GET_DDL để xem định nghĩa cụ thể. Cần kiểm tra view trực tiếp và view lồng nhau.

### 4.4. Tìm synonym

~~~sql
SELECT owner,
       synonym_name,
       table_owner,
       table_name,
       db_link
FROM dba_synonyms
WHERE table_owner = 'APP_OWNER'
  AND table_name = 'ORDERS'
ORDER BY owner, synonym_name;
~~~

Synonym là alias tên object. Nó không tự bảo đảm tương thích khi object đích bị rename hoặc chuyển schema. Kiểm tra private/public synonym, target owner/name và database link nếu có.

### 4.5. Kiểm tra trigger

~~~sql
SELECT owner,
       trigger_name,
       table_owner,
       table_name,
       status,
       triggering_event,
       trigger_type
FROM dba_triggers
WHERE table_owner = 'APP_OWNER'
  AND table_name = 'ORDERS'
ORDER BY owner, trigger_name;
~~~

Trigger có thể tham chiếu column đã đổi tên hoặc datatype. Kiểm tra trigger body, compound trigger, trigger gọi package và trigger tác động sang bảng khác.

### 4.6. Dependency bên ngoài database

Ngoài dictionary, tìm trong:

- Source code repository và ORM entity mapping.
- Native SQL, JPQL và named query.
- Stored SQL trong configuration.
- ETL/Data Integration job.
- BI/reporting dashboard.
- Scheduler và shell scripts.
- CDC/replication configuration.
- API payload, message schema và data contract.
- Stored procedure ở database khác gọi qua database link.

Không có một câu query dictionary nào có thể thay thế việc tìm kiếm ở application repository và xác nhận với owner hệ thống tích hợp.

## 5. Đổi tên bảng

Oracle hỗ trợ RENAME để đổi tên object trong schema:

~~~sql
RENAME orders TO sales_orders;
~~~

Sau khi đổi tên, object được truy cập bằng tên mới. Tên cũ không còn là tên table hiện tại.

### 5.1. Đổi tên bảng tác động tới đâu?

Cần kiểm tra:

- SQL trong application và batch.
- View/materialized view tham chiếu table.
- PL/SQL package/procedure/function.
- Trigger và dynamic SQL.
- Synonym trỏ tới tên cũ.
- Foreign key và constraint.
- ETL, BI và report.
- Database link consumer.
- ORM @Table(name = ...).
- Migration script và deployment config.

Không giả định mọi dependency được tự động sửa source code để dùng tên mới. Oracle có dependency/invalidation mechanism, nhưng ứng dụng bên ngoài database không được Oracle cập nhật.

### 5.2. Tương thích tên cũ

Nếu cần chuyển đổi theo nhiều release, có thể cân nhắc tạo compatibility view hoặc synonym với tên cũ, tùy yêu cầu read/write và quyền.

Ví dụ table mới có tên SALES_ORDERS, tạo view tương thích:

~~~sql
CREATE OR REPLACE VIEW orders AS
SELECT order_id,
       customer_id,
       status,
       created_at
FROM sales_orders;
~~~

View này có thể giúp một số query cũ tiếp tục chạy. Tuy nhiên:

- Không phải mọi view đều tự động updatable.
- DML qua view có thể cần INSTEAD OF trigger.
- Column bị đổi tên phải alias về tên cũ.
- Grants trên view cần được cấp và kiểm tra.
- Query plan và semantics có thể thay đổi.
- Object cũ cùng tên phải được xử lý trước khi tạo view.

Không dùng compatibility view nếu chưa kiểm thử đầy đủ quyền, DML và performance.

### 5.3. Đổi tên bảng không phải copy dữ liệu

RENAME chỉ đổi tên object. Nó không tạo bản sao mới và không chuyển dữ liệu sang storage khác. Nếu mục tiêu là di chuyển dữ liệu, đổi cấu trúc hoặc thay partitioning, cần quy trình khác.

## 6. Đổi tên cột

Dùng ALTER TABLE ... RENAME COLUMN:

~~~sql
ALTER TABLE orders
RENAME COLUMN order_status TO status;
~~~

Đổi tên column thay đổi metadata column. Dữ liệu hiện có vẫn thuộc cùng column, không phải copy sang column mới.

### 6.1. Những nơi cần cập nhật

- SQL SELECT/INSERT/UPDATE/DELETE.
- View và materialized view.
- PL/SQL source.
- Trigger.
- Function-based index expression.
- Check constraint expression.
- Virtual column expression.
- Partition key/subpartition expression.
- ORM entity field và @Column.
- DTO projection và row mapper.
- Report, ETL và external consumer.

Một số metadata dependency được Oracle quản lý và object có thể bị invalidated/recompiled. Nhưng source chứa tên column cũ có thể không compile được cho tới khi sửa.

### 6.2. View dùng SELECT *

View được tạo bằng SELECT * không tự động trở thành contract động luôn phản ánh mọi column mới. Oracle mở rộng wildcard theo định nghĩa view tại thời điểm tạo; khi cấu trúc bảng thay đổi, cần kiểm tra/recreate view để có projection mong muốn.

Không dựa vào SELECT * trong view hoặc API view nếu schema thường xuyên thay đổi.

### 6.3. Rename trực tiếp hay expand-contract?

Nếu toàn bộ consumer có thể được dừng và deploy đồng thời, rename trực tiếp có thể phù hợp.

Nếu ứng dụng deploy rolling hoặc nhiều hệ thống dùng chung database, đổi tên trực tiếp có thể khiến phiên bản cũ lỗi trong thời gian chuyển đổi. Dùng expand-contract:

1. Thêm column mới với tên mới.
2. Cập nhật ứng dụng để đọc cả hai hoặc đọc cột mới khi đã sẵn sàng.
3. Dual-write hoặc backfill theo chiến lược đã định.
4. Xác minh dữ liệu hai cột nhất quán.
5. Chuyển mọi consumer sang cột mới.
6. Ngừng ghi cột cũ.
7. Xóa cột cũ trong release sau.

Cách này tốn thời gian và dung lượng tạm, nhưng tránh cutover tên cột đột ngột.

## 7. Đổi datatype: phân biệt thay đổi tương thích và chuyển đổi dữ liệu

Không phải mọi thay đổi datatype đều có cùng mức độ.

Ví dụ ít rủi ro hơn:

- Tăng VARCHAR2 length từ 100 lên 300.
- Tăng precision NUMBER khi vẫn giữ scale tương thích.
- Tăng độ dài CHAR/VARCHAR2 theo yêu cầu.

Ví dụ cần phân tích kỹ:

- VARCHAR2 sang NUMBER.
- NUMBER sang VARCHAR2.
- DATE sang TIMESTAMP.
- VARCHAR2 sang DATE/TIMESTAMP.
- CLOB sang VARCHAR2.
- BLOB sang RAW.
- Thay đổi scale làm tròn hoặc mất phần thập phân.
- Thay đổi character set/length semantics.

### 7.1. MODIFY column

Ví dụ tăng độ dài:

~~~sql
ALTER TABLE customers
MODIFY (customer_name VARCHAR2(300 CHAR));
~~~

Ví dụ tăng precision:

~~~sql
ALTER TABLE invoice_lines
MODIFY (quantity NUMBER(18, 3));
~~~

Cú pháp và khả năng thực hiện phụ thuộc datatype, dữ liệu hiện có, constraint, index, partitioning và Oracle release.

Tăng length thường khác với chuyển datatype. Giảm length hoặc giảm precision/scale có thể thất bại nếu dữ liệu hiện tại không vừa hoặc làm mất thông tin.

### 7.2. Kiểm tra dữ liệu trước conversion

Nếu chuyển VARCHAR2 sang NUMBER, kiểm tra giá trị không chuyển đổi được trước:

~~~sql
SELECT order_id,
       amount_text
FROM staging_orders
WHERE amount_text IS NOT NULL
  AND VALIDATE_CONVERSION(amount_text AS NUMBER) = 0;
~~~

VALIDATE_CONVERSION có trên các Oracle release hỗ trợ. Với release cũ hơn, dùng cách kiểm tra conversion an toàn phù hợp, không dựa vào regex đơn giản nếu format số có dấu phân cách, locale hoặc exponent.

Kiểm tra cả:

- NULL và empty string semantics.
- Dấu âm/dương.
- Decimal separator.
- Thousands separator.
- Leading/trailing spaces.
- Giá trị vượt precision.
- Giá trị có scale vượt yêu cầu.
- Chuỗi ngày theo NLS format.
- Timezone và daylight saving khi chuyển timestamp.

### 7.3. Chuyển đổi có mất thông tin không?

Ví dụ NUMBER(12,2) sang NUMBER(10,0) có thể mất phần thập phân hoặc vượt precision. DATE sang TIMESTAMP không nhất thiết mất thông tin thời gian nhưng không tự bổ sung timezone. TIMESTAMP WITH TIME ZONE sang DATE có thể mất timezone và fractional seconds.

Định nghĩa rõ phép chuyển đổi nghiệp vụ trước khi viết DDL.

## 8. Chiến lược shadow column cho datatype change

Với bảng có dữ liệu và cần chuyển đổi thực sự, một cách an toàn thường là thêm cột mới thay vì sửa datatype trực tiếp.

Giả sử AMOUNT_TEXT là VARCHAR2 và cần chuyển thành NUMBER.

### Bước 1 — Thêm cột mới

~~~sql
ALTER TABLE orders
ADD (amount_number NUMBER(18, 2));
~~~

DDL này có implicit commit. Chuẩn bị change record và kiểm tra dung lượng/metadata trước khi chạy.

### Bước 2 — Backfill theo batch

~~~sql
UPDATE orders
SET amount_number =
    TO_NUMBER(amount_text DEFAULT NULL ON CONVERSION ERROR)
WHERE amount_number IS NULL
  AND amount_text IS NOT NULL;
~~~

DEFAULT ... ON CONVERSION ERROR phụ thuộc Oracle release hỗ trợ. Không dùng cách này nếu conversion error phải được phát hiện và xử lý; tốt hơn là lưu reject list và đối soát dữ liệu lỗi.

Với bảng lớn, backfill theo primary key range hoặc batch key để giới hạn undo, redo, lock duration và ảnh hưởng workload.

### Bước 3 — Dual-write

Trong giai đoạn chuyển đổi, ứng dụng có thể ghi cả cột cũ và cột mới, hoặc ghi một nguồn chuẩn rồi đồng bộ cột còn lại qua logic được kiểm soát.

Tránh hai nguồn ghi độc lập gây lệch dữ liệu. Xác định một source of truth và cách xử lý khi một lần ghi thất bại.

### Bước 4 — Đối soát

~~~sql
SELECT COUNT(*) AS mismatch_count
FROM orders
WHERE amount_text IS NOT NULL
  AND (
      amount_number IS NULL
      OR amount_number <> TO_NUMBER(
          amount_text DEFAULT NULL ON CONVERSION ERROR
      )
  );
~~~

Đối soát phải xét rounding, scale và format nghiệp vụ. Với số tiền, không tự làm tròn nếu chưa có quy tắc được business owner chấp thuận.

### Bước 5 — Chuyển consumer

Cập nhật view, package, trigger, report, ORM mapping và application query để dùng AMOUNT_NUMBER. Theo dõi lỗi và dữ liệu.

### Bước 6 — Ngừng cột cũ

Sau khi không còn consumer đọc/ghi cột cũ, ngừng dual-write và chỉ giữ lại cột mới. Việc drop cột cũ là bước contract riêng sau khi hết thời gian rollback ứng dụng.

### Bước 7 — Xóa cột cũ trong change riêng

~~~sql
ALTER TABLE orders DROP COLUMN amount_text;
~~~

DROP COLUMN là DDL và không thể rollback bằng transaction thông thường. Giữ snapshot/backup và kiểm tra dependency trước khi thực hiện.

## 9. Thay đổi datatype trực tiếp có giới hạn

Oracle có quy tắc riêng cho ALTER TABLE MODIFY. Một số thay đổi chỉ được phép khi cột rỗng hoặc dữ liệu đáp ứng điều kiện chuyển đổi; một số thay đổi tương thích như tăng độ dài có thể thực hiện trực tiếp.

Trước khi dùng MODIFY, xác minh:

- Column có dữ liệu hay không.
- Datatype nguồn/đích.
- Precision, scale, length và character semantics.
- Column có nằm trong PK/UK/FK/CHECK không.
- Column có nằm trong index, function-based index hoặc partition key không.
- Table có LOB, object type, virtual column hoặc dependent view không.
- Có constraint/index cần disable/rebuild không.
- Oracle release có hỗ trợ online operation nào không.

Không dựa vào việc câu ALTER chạy được trong lab table rỗng để kết luận nó sẽ chạy được trên production table có hàng tỷ row.

### 9.1. Thay đổi length semantics

VARCHAR2(100 BYTE) và VARCHAR2(100 CHAR) không có cùng giới hạn byte. Với multibyte character set, số ký tự thực tế có thể khác nhau.

Kiểm tra CHAR_USED, CHAR_LENGTH và DATA_LENGTH trước/sau thay đổi. Xác minh ứng dụng validate theo byte hay character.

### 9.2. NUMBER precision và scale

NUMBER(p,s) có precision tối đa và scale được quy định bởi Oracle. Khi giảm scale, giá trị có thể bị làm tròn; khi giảm precision, giá trị có thể vượt giới hạn.

Kiểm tra MIN/MAX, số chữ số nguyên, số chữ số thập phân và quy tắc rounding. Dữ liệu tài chính cần test bằng BigDecimal và không dùng floating-point conversion tùy tiện.

### 9.3. DATE và TIMESTAMP

Oracle DATE lưu ngày giờ tới giây nhưng không lưu fractional seconds hoặc timezone. TIMESTAMP hỗ trợ fractional seconds; TIMESTAMP WITH TIME ZONE mang thông tin timezone.

Trước chuyển đổi:

- Xác định session/database timezone.
- Xác định dữ liệu hiện tại đang biểu diễn local time hay UTC.
- Kiểm tra application mapping.
- Xác định có cần giữ offset/timezone không.
- Kiểm tra query filter và index.
- Kiểm tra API format và serialization.

Không thể khôi phục timezone đã không được lưu chỉ bằng cách đổi DATE sang TIMESTAMP WITH TIME ZONE.

## 10. Thêm NOT NULL constraint

Cột NOT NULL yêu cầu mọi hàng có giá trị khác NULL.

~~~sql
ALTER TABLE customers
MODIFY (customer_name NOT NULL);
~~~

Lệnh có thể thất bại nếu bảng đang có hàng NULL.

Kiểm tra trước:

~~~sql
SELECT COUNT(*) AS null_count
FROM customers
WHERE customer_name IS NULL;
~~~

Nếu có dữ liệu NULL:

1. Xác định business rule thay thế.
2. Backfill giá trị hợp lệ hoặc xử lý hàng lỗi.
3. Ngăn ứng dụng mới tiếp tục ghi NULL.
4. Kiểm tra lại.
5. Thêm/validate constraint.

Không thay NULL bằng chuỗi rỗng tùy tiện. Trong Oracle, chuỗi rỗng VARCHAR2 được xử lý như NULL; default giả có thể làm sai nghiệp vụ.

### 10.1. Thêm CHECK NOT NULL theo giai đoạn

Có thể dùng check constraint như một bước chuyển tiếp:

~~~sql
ALTER TABLE customers
ADD CONSTRAINT ck_customers_name_nn
CHECK (customer_name IS NOT NULL)
ENABLE NOVALIDATE;
~~~

Sau khi dữ liệu cũ được làm sạch và kiểm tra, validate:

~~~sql
ALTER TABLE customers
ENABLE VALIDATE CONSTRAINT ck_customers_name_nn;
~~~

Cuối cùng có thể chuẩn hóa thành NOT NULL metadata bằng ALTER TABLE MODIFY nếu phù hợp với release và schema design. Không giữ hai cơ chế trùng lặp mà không có lý do.

## 11. Thêm CHECK constraint

CHECK constraint giới hạn giá trị theo điều kiện:

~~~sql
ALTER TABLE orders
ADD CONSTRAINT ck_orders_amount_nonnegative
CHECK (total_amount >= 0)
ENABLE VALIDATE;
~~~

Trước khi thêm, kiểm tra dữ liệu vi phạm:

~~~sql
SELECT order_id,
       total_amount
FROM orders
WHERE total_amount < 0;
~~~

Lưu ý SQL CHECK semantics: biểu thức trả UNKNOWN do NULL thường không bị xem là vi phạm CHECK. Nếu cột bắt buộc có giá trị, cần thêm NOT NULL riêng.

Ví dụ:

~~~sql
ALTER TABLE orders
ADD CONSTRAINT ck_orders_status
CHECK (status IN ('NEW', 'PAID', 'CANCELLED'));
~~~

Nếu STATUS có NULL, CHECK trên không tự thay thế NOT NULL.

## 12. Thêm UNIQUE và PRIMARY KEY

### 12.1. Kiểm tra duplicate

~~~sql
SELECT customer_code,
       COUNT(*) AS duplicate_count
FROM customers
GROUP BY customer_code
HAVING COUNT(*) > 1;
~~~

Nếu constraint là composite, group theo toàn bộ cột key. Xác định semantics NULL và collation/character comparison theo datatype.

### 12.2. Thêm UNIQUE

~~~sql
ALTER TABLE customers
ADD CONSTRAINT uk_customers_code
UNIQUE (customer_code);
~~~

### 12.3. Thêm PRIMARY KEY

~~~sql
ALTER TABLE customers
ADD CONSTRAINT pk_customers
PRIMARY KEY (customer_id);
~~~

Primary key yêu cầu uniqueness và NOT NULL. Oracle có thể dùng index hiện có phù hợp hoặc tạo index để hỗ trợ constraint, tùy cấu hình và DDL.

Trước khi thêm, kiểm tra index hiện tại, tablespace, key length, data distribution và duplicate/null data. Không tạo index trùng lặp nếu đã có index phù hợp.

## 13. Thêm FOREIGN KEY

Foreign key bảo đảm giá trị ở bảng con tham chiếu key hợp lệ ở bảng cha.

~~~sql
ALTER TABLE orders
ADD CONSTRAINT fk_orders_customer
FOREIGN KEY (customer_id)
REFERENCES customers(customer_id);
~~~

Cột được tham chiếu phải là primary key hoặc unique key phù hợp. Datatype/column compatibility cần đúng theo Oracle rules.

Kiểm tra orphan rows trước:

~~~sql
SELECT o.order_id,
       o.customer_id
FROM orders o
WHERE o.customer_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM customers c
      WHERE c.customer_id = o.customer_id
  );
~~~

### 13.1. Index trên foreign key

Oracle không tự động tạo index cho foreign key trong mọi trường hợp. Index trên FK thường hữu ích cho join và có thể giảm một số vấn đề locking khi parent key được update/delete, nhưng quyết định phụ thuộc workload.

Ví dụ:

~~~sql
CREATE INDEX ix_orders_customer
ON orders(customer_id);
~~~

Nếu FK là composite, xem thứ tự cột và query pattern trước khi tạo index.

### 13.2. ON DELETE behavior

Có thể định nghĩa ON DELETE CASCADE hoặc SET NULL khi phù hợp:

~~~sql
ALTER TABLE order_lines
ADD CONSTRAINT fk_lines_order
FOREIGN KEY (order_id)
REFERENCES orders(order_id)
ON DELETE CASCADE;
~~~

CASCADE có thể xóa nhiều hàng con khi xóa parent. Chỉ dùng khi business semantics thực sự yêu cầu. SET NULL cần cột nullable. Không thêm cascade chỉ để tránh lỗi FK.

## 14. ENABLE, DISABLE, VALIDATE và NOVALIDATE

Constraint có hai khía cạnh cần tách biệt:

- **ENABLE/DISABLE:** có enforcement đối với DML mới hay không.
- **VALIDATE/NOVALIDATE:** dữ liệu hiện có đã được kiểm tra theo constraint hay chưa.

| Trạng thái | Dữ liệu hiện tại | DML mới |
|---|---|---|
| ENABLE VALIDATE | Đã được kiểm tra | Được enforce |
| ENABLE NOVALIDATE | Chưa đảm bảo toàn bộ dữ liệu cũ hợp lệ | DML mới được enforce theo constraint |
| DISABLE VALIDATE | Đã validate nhưng enforcement disabled | Không enforce như ENABLE |
| DISABLE NOVALIDATE | Không đảm bảo dữ liệu cũ hợp lệ | Không enforce |

Chi tiết behavior còn phụ thuộc constraint type và operation. Xem Oracle SQL Reference cho trạng thái cụ thể.

### 14.1. Tạo constraint chưa validate

~~~sql
ALTER TABLE orders
ADD CONSTRAINT ck_orders_amount
CHECK (total_amount >= 0)
ENABLE NOVALIDATE;
~~~

Cách này có thể giúp bắt đầu enforcement cho dữ liệu mới trong khi chưa quét/validate toàn bộ dữ liệu cũ. Nhưng database vẫn có thể chứa hàng cũ vi phạm constraint.

Không báo cáo constraint là fully valid khi VALIDATED = NOT VALIDATED.

### 14.2. Validate sau khi làm sạch

~~~sql
ALTER TABLE orders
ENABLE VALIDATE CONSTRAINT ck_orders_amount;
~~~

Oracle kiểm tra dữ liệu hiện có. Nếu còn hàng vi phạm, thao tác thất bại và constraint không đạt trạng thái mong muốn.

### 14.3. Kiểm tra trạng thái

~~~sql
SELECT owner,
       table_name,
       constraint_name,
       status,
       validated,
       deferrable,
       deferred
FROM dba_constraints
WHERE owner = 'APP_OWNER'
  AND table_name = 'ORDERS'
ORDER BY constraint_name;
~~~

Kiểm tra trạng thái thực tế sau migration, không chỉ dựa vào exit code của script.

## 15. Constraint DEFERRABLE

Một số constraint có thể được khai báo DEFERRABLE để trì hoãn kiểm tra tới thời điểm commit:

~~~sql
ALTER TABLE order_lines
ADD CONSTRAINT fk_lines_order
FOREIGN KEY (order_id)
REFERENCES orders(order_id)
DEFERRABLE INITIALLY DEFERRED;
~~~

Trong transaction có thể điều chỉnh:

~~~sql
SET CONSTRAINTS fk_lines_order DEFERRED;
~~~

hoặc:

~~~sql
SET CONSTRAINTS fk_lines_order IMMEDIATE;
~~~

DEFERRABLE hữu ích cho thao tác nhiều bước, ví dụ tạm thời thay đổi thứ tự dữ liệu cha/con trong cùng transaction. Không phải mọi constraint hoặc mọi use case đều cần deferred checking.

Kiểm tra commit behavior trong test. Flush JPA không nhất thiết tương đương commit; deferred constraint có thể chỉ lỗi khi transaction commit.

## 16. Index và object phụ thuộc sau thay đổi

### 16.1. Index

Sau đổi tên column, index dựa trên column thường vẫn gắn với column metadata, nhưng tên index và các query phụ thuộc cần được kiểm tra. Không giả định mọi index expression hoặc function-based index vẫn đúng theo ý nghĩa mới.

Sau datatype conversion, xem:

- Index status.
- Column order.
- Function-based expression.
- Selectivity và statistics.
- Key length.
- Partitioned index status.
- Execution plan trước/sau.

### 16.2. View và materialized view

View phụ thuộc column/table có thể bị invalid hoặc không còn compile sau rename/drop/type change. Kiểm tra DBA_OBJECTS và compile errors.

Materialized view có thêm refresh dependency, logs và refresh mode. Thay đổi base table có thể ảnh hưởng refresh hoặc query rewrite. Lập kế hoạch full refresh/rebuild nếu cần theo thiết kế.

### 16.3. PL/SQL package và trigger

Stored PL/SQL phụ thuộc object có thể bị invalidated khi metadata thay đổi. Oracle có thể tự động recompile khi object được gọi, nhưng compile có thể thất bại nếu source còn tham chiếu tên/cột cũ.

Kiểm tra:

~~~sql
SELECT owner,
       object_type,
       object_name,
       status,
       last_ddl_time
FROM dba_objects
WHERE owner IN ('APP_OWNER', 'REPORT_OWNER')
  AND status = 'INVALID'
ORDER BY owner, object_type, object_name;
~~~

Xem compile errors:

~~~sql
SELECT owner,
       name,
       type,
       line,
       position,
       text
FROM dba_errors
ORDER BY owner, name, sequence;
~~~

### 16.4. Synonym

Synonym giữ tên logic cho object đích. Khi table/target bị rename hoặc chuyển schema, synonym có thể không còn resolve tới object mong muốn.

Kiểm tra DBA_SYNONYMS và thử resolution bằng principal ứng dụng. Synonym không tự chuyển dữ liệu hoặc tự cập nhật SQL source trong consumer.

### 16.5. Trigger và constraint

Trigger gắn với table và có source body tham chiếu column. Kiểm tra trigger status, body và behavior sau DDL. Constraint có thể vẫn tồn tại nhưng condition/column mapping cần xác minh qua dictionary.

### 16.6. Dynamic SQL và ứng dụng

Oracle dependency metadata không thể biết mọi SQL được ghép từ string. Tìm kiếm source code, config, scheduler scripts, ETL và report.

Ví dụ:

~~~sql
l_sql := 'SELECT old_status FROM orders WHERE order_id = :b1';
OPEN l_cursor FOR l_sql USING p_order_id;
~~~

Tên column trong dynamic SQL không được compiler phân tích dependency như SQL tĩnh. Sau rename, câu này có thể chỉ lỗi khi runtime.

## 17. Xử lý invalid object sau migration

Sau thay đổi schema, tổng hợp invalid objects:

~~~sql
SELECT owner,
       object_type,
       object_name,
       status
FROM dba_objects
WHERE status = 'INVALID'
ORDER BY owner, object_type, object_name;
~~~

Compile một object cụ thể khi source đã được sửa:

~~~sql
ALTER VIEW report_orders COMPILE;
ALTER PACKAGE order_api COMPILE;
ALTER PACKAGE order_api COMPILE BODY;
ALTER PROCEDURE close_order COMPILE;
ALTER FUNCTION calculate_total COMPILE;
~~~

Không chạy compile hàng loạt trước khi biết dependency/source đã được cập nhật. Compile chỉ kiểm tra lại object; nó không tự sửa tham chiếu sai.

Có thể dùng DBMS_UTILITY.COMPILE_SCHEMA hoặc UTL_RECOMP theo quy trình DBA khi cần recompile nhiều object. Lập lịch phù hợp, theo dõi errors và tránh gây tải bất ngờ trên production.

## 18. Expand-contract cho thay đổi không thể deploy đồng thời

Với ứng dụng có rolling deployment hoặc nhiều consumer, thay đổi schema nên có giai đoạn tương thích.

~~~text
Phase 1: EXPAND
    Add new column/object
    Keep old interface working
    Deploy code that understands old + new

Phase 2: MIGRATE
    Backfill existing rows
    Dual-write or synchronize
    Reconcile data
    Move consumers to new interface

Phase 3: CONTRACT
    Stop old reads/writes
    Remove old dependencies
    Drop old column/object in a later release
~~~

### 18.1. Expand

Thêm cột mới nullable hoặc có default phù hợp. Không xóa cột cũ. Tạo index/constraint theo giai đoạn.

### 18.2. Migrate

Backfill theo batch. Theo dõi progress, lỗi conversion và dữ liệu lệch. Ứng dụng có thể dual-write nhưng phải có một source of truth và cơ chế reconcile.

### 18.3. Contract

Chỉ drop cột/object cũ sau khi:

- Không còn phiên bản ứng dụng đọc/ghi tên cũ.
- Không còn batch/ETL/report phụ thuộc.
- Dependency database đã được sửa.
- Dữ liệu mới đã được xác minh.
- Có backup/recovery plan.
- Change được phê duyệt.

Không thực hiện contract ngay sau khi deploy một phiên bản mới nếu rolling deployment hoặc rollback ứng dụng còn có thể đưa code cũ trở lại.

## 19. Online redefinition cho bảng lớn

Với bảng lớn và yêu cầu giảm downtime, Oracle DBMS_REDEFINITION có thể hỗ trợ tái định nghĩa bảng trực tuyến trong các trường hợp được hỗ trợ.

Quy trình khái quát:

1. Kiểm tra table có đủ điều kiện redefinition bằng CAN_REDEF_TABLE.
2. Tạo interim table với cấu trúc đích.
3. Gọi START_REDEF_TABLE.
4. Copy các dependent objects bằng COPY_TABLE_DEPENDENTS theo kế hoạch.
5. Đồng bộ thay đổi phát sinh bằng SYNC_INTERIM_TABLE.
6. Kiểm tra data consistency và dependencies.
7. Gọi FINISH_REDEF_TABLE trong cửa sổ cutover.
8. Kiểm tra object, grants, constraints, indexes và ứng dụng.
9. Dọn interim object theo runbook.

Các API chính:

~~~sql
BEGIN
    DBMS_REDEFINITION.CAN_REDEF_TABLE(
        uname        => 'APP_OWNER',
        tname        => 'ORDERS',
        options_flag => DBMS_REDEFINITION.CONS_USE_PK
    );
END;
/
~~~

Đây chỉ là bước eligibility check minh họa. START_REDEF_TABLE, COPY_TABLE_DEPENDENTS, SYNC_INTERIM_TABLE và FINISH_REDEF_TABLE cần tham số, quyền, storage và điều kiện cụ thể theo Oracle release.

Online redefinition không có nghĩa zero risk hoặc không cần downtime. Cần test trên bản sao dữ liệu tương đương, kiểm tra unsupported datatype/feature, space overhead, materialized view log, dependent object và cutover duration.

## 20. DDL implicit commit và migration recovery

Oracle DDL thực hiện implicit commit trước khi thực thi và commit sau khi DDL thành công. Vì vậy:

- Không chạy DDL giữa transaction nghiệp vụ cần rollback.
- Không dựa vào Spring @Transactional để rollback CREATE/ALTER/DROP/TRUNCATE.
- Nếu script có nhiều DDL, một phần có thể đã hoàn tất trước khi câu sau thất bại.
- Rollback script của migration tool là các thao tác mới, không phải rollback transaction gốc.

### 20.1. Chia migration thành bước nhỏ

Ví dụ một thay đổi datatype:

1. Add shadow column.
2. Add supporting index/constraint nếu cần.
3. Deploy code tương thích.
4. Backfill.
5. Validate.
6. Switch consumer.
7. Drop old column trong migration riêng.

Mỗi bước có precondition, postcondition và recovery/forward-fix plan.

### 20.2. Ghi migration ledger

Ghi nhận:

- Change ID và migration version.
- Database, PDB và schema.
- DDL được thực thi.
- Start/end time.
- Người thực hiện.
- Row count và object count.
- Constraint/index status.
- Invalid objects.
- Application version tương thích.
- Bằng chứng và ticket.

### 20.3. Phục hồi khi DDL thất bại

Không chạy lại toàn bộ script theo phản xạ. Trước tiên:

1. Xác định statement cuối cùng thành công.
2. Query dictionary để xem object/column/constraint đã tồn tại chưa.
3. Kiểm tra dữ liệu backfill và trạng thái constraint.
4. Kiểm tra migration tool history.
5. Xác định có DML đã bị implicit commit hay không.
6. Viết forward-fix hoặc cleanup riêng.
7. Chỉ chạy lại bước idempotent sau khi xác nhận trạng thái.

## 21. Kiểm thử schema change

### 21.1. Kiểm thử trước DDL

- Dữ liệu có phù hợp datatype mới không?
- Có NULL/duplicate/orphan row không?
- Có object phụ thuộc không?
- Có consumer dùng tên cũ không?
- Có index/partition/LOB feature ảnh hưởng không?
- Có đủ tablespace và undo/redo capacity không?
- Có lock hoặc downtime risk không?

### 21.2. Kiểm thử sau DDL

- Column name/type/length/precision đúng.
- Constraint status và validated đúng.
- Index status hợp lệ.
- View/package/trigger compile.
- Synonym resolve.
- Application query/ORM mapping hoạt động.
- Data reconciliation đúng.
- Execution plan và latency không regression.
- Job/ETL/report hoạt động.
- Grants, audit và security policy còn đúng.

### 21.3. Test dữ liệu biên

Với datatype conversion:

- NULL.
- Empty string.
- Giá trị min/max.
- Số âm/dương.
- Decimal rounding.
- Unicode/multibyte.
- Date boundary/leap day.
- Timestamp/timezone.
- Chuỗi sai format.
- Giá trị vượt precision/length.

Với constraint:

- Dữ liệu hợp lệ.
- Dữ liệu vi phạm.
- Duplicate key.
- Orphan FK.
- NULL ở cột bắt buộc.
- Concurrent insert vi phạm uniqueness.
- Deferred constraint tại commit.

### 21.4. Test trên Oracle thật

H2 hoặc database khác không thay Oracle khi kiểm thử:

- DDL implicit commit.
- Data dictionary.
- PL/SQL invalidation.
- Oracle datatype conversion.
- ENABLE NOVALIDATE/VALIDATE.
- DEFERRABLE constraint.
- DBMS_REDEFINITION.
- Partitioned object.
- Oracle optimizer và index behavior.

Dùng Oracle integration environment có release/RU và character set gần production.

## 22. Runbook triển khai schema change

### Bước 1 — Xác nhận mục tiêu

Ghi object, column, datatype/constraint cũ và mới, consumer, business rule, RTO/downtime budget và owner.

### Bước 2 — Inventory dependency

Thu thập DBMS_METADATA, DBA_DEPENDENCIES, DBA_SOURCE, DBA_VIEWS, DBA_SYNONYMS, DBA_TRIGGERS, DBA_CONSTRAINTS, DBA_INDEXES và application references.

### Bước 3 — Kiểm tra dữ liệu

Chạy duplicate, NULL, orphan và conversion validation queries. Lưu số hàng và mẫu dữ liệu lỗi đã được bảo vệ.

### Bước 4 — Kiểm tra dung lượng và tác động

Ước tính table scan, backfill, index build, redo/undo, lock, storage và thời gian validation. Kiểm tra RAC/Data Guard impact nếu áp dụng.

### Bước 5 — Chuẩn bị migration

Viết script theo bước nhỏ, có precondition và postcondition. Chuẩn bị rollback/forward fix và compatibility code.

### Bước 6 — Backup và phê duyệt

Xác nhận backup/recovery point, change window, approver, communication và stop condition. DDL không rollback bằng transaction thông thường.

### Bước 7 — Thực hiện

Chạy đúng thứ tự. Lưu output, thời gian, row count và trạng thái từng bước. Dừng khi postcondition không đạt.

### Bước 8 — Xác minh dependency

Compile/test view, package, trigger; kiểm tra invalid objects, synonym, index, constraint và application consumer.

### Bước 9 — Kiểm thử nghiệp vụ

Chạy smoke test, data reconciliation, batch/report test và performance comparison.

### Bước 10 — Đóng change

Lưu evidence, cập nhật schema documentation, ORM mapping, migration version và runbook. Giao owner cho follow-up.

## 23. Các lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Rename trực tiếp khi ứng dụng cũ vẫn chạy | SQL phiên bản cũ lỗi | Expand-contract hoặc coordinated cutover |
| Chỉ tìm DBA_DEPENDENCIES | Bỏ sót dynamic SQL và ứng dụng ngoài DB | Search source/config/ETL và xác nhận owner |
| Giảm VARCHAR2 length không kiểm tra | DDL lỗi hoặc mất dữ liệu theo conversion path | Kiểm tra max length và multibyte |
| VARCHAR2 sang NUMBER không validate | Dữ liệu lỗi làm migration thất bại | VALIDATE_CONVERSION và reject list |
| Giảm NUMBER scale tùy tiện | Rounding hoặc mất độ chính xác | Business rounding rule và reconciliation |
| Thêm NOT NULL khi còn NULL | ALTER thất bại | Backfill và validate |
| CHECK constraint nhưng quên NULL | NULL vẫn có thể được chấp nhận | Thêm NOT NULL nếu nghiệp vụ yêu cầu |
| Thêm FK khi còn orphan | Constraint không validate được | Tìm và xử lý orphan trước |
| ENABLE NOVALIDATE coi như VALIDATE | Dữ liệu cũ vẫn có thể vi phạm | Kiểm tra DBA_CONSTRAINTS.VALIDATED |
| Giả định index tự phù hợp sau đổi kiểu | Plan regression hoặc index unusable | Kiểm tra index và execution plan |
| Không compile/test dependent object | Runtime mới phát hiện invalid object | Precompile và smoke test |
| Dùng SELECT * trong view/API | Projection không như kỳ vọng sau schema change | Liệt kê column tường minh |
| DDL trong transaction rollback | DML trước DDL đã bị commit | Tách DDL khỏi transaction nghiệp vụ |
| Chạy lại migration mù quáng | Object đã tồn tại hoặc trạng thái lệch | Inspect dictionary và forward-fix |
| Drop old column ngay sau deploy | Rollback ứng dụng không còn tương thích | Giữ compatibility window |
| Test chỉ trên H2 | Bỏ sót Oracle semantics | Oracle integration test |

## 24. Checklist trước và sau schema change

### Trước thay đổi

- [ ] Xác nhận database, PDB, owner và object.
- [ ] Lưu DDL hiện tại bằng DBMS_METADATA.
- [ ] Inventory column, constraint, index và partition.
- [ ] Kiểm tra DBA_DEPENDENCIES và PL/SQL source.
- [ ] Tìm dynamic SQL, synonym, view, trigger và materialized view.
- [ ] Tìm application/ORM/ETL/BI consumer.
- [ ] Validate dữ liệu conversion, NULL, duplicate và orphan.
- [ ] Đánh giá lock, scan, redo/undo và storage.
- [ ] Xác định downtime/online strategy.
- [ ] Chuẩn bị backup, change approval và forward-fix.
- [ ] Đảm bảo ứng dụng cũ/mới tương thích trong giai đoạn deploy.

### Sau thay đổi

- [ ] Xác nhận column name/type/precision/length.
- [ ] Xác nhận constraint ENABLED và VALIDATED đúng yêu cầu.
- [ ] Xác nhận index status và statistics.
- [ ] Xác nhận view/materialized view refresh hoặc compile.
- [ ] Xác nhận package/procedure/function/trigger VALID.
- [ ] Xác nhận synonym và grants.
- [ ] Kiểm tra dynamic SQL và application query.
- [ ] Đối soát dữ liệu trước/sau.
- [ ] Chạy smoke test, batch và report.
- [ ] So sánh execution plan/latency.
- [ ] Kiểm tra invalid objects và error log.
- [ ] Lưu migration evidence và cập nhật documentation.

## 25. Ghi nhớ cốt lõi

- Schema là hợp đồng giữa database, ứng dụng, PL/SQL, ETL, BI và các consumer khác.
- RENAME TABLE và RENAME COLUMN thay đổi tên metadata; chúng không tự cập nhật mọi SQL trong application hoặc dynamic SQL.
- Trước rename/drop/type change phải inventory dependency bằng dictionary views và source search ngoài database.
- DBA_DEPENDENCIES là điểm bắt đầu, không phải danh sách đầy đủ mọi tham chiếu.
- DBMS_METADATA.GET_DDL giúp lưu baseline object definition; nó không thay backup dữ liệu.
- Tăng length thường khác với chuyển datatype; đổi datatype cần kiểm tra dữ liệu, precision, scale, encoding, constraint và index.
- Với chuyển đổi rủi ro, shadow column, backfill theo batch, dual-write, reconcile và cutover thường an toàn hơn đổi trực tiếp.
- NOT NULL, CHECK, UNIQUE, PRIMARY KEY và FOREIGN KEY phải được kiểm tra với dữ liệu hiện tại trước khi enable/validate.
- CHECK không tự thay NOT NULL vì điều kiện UNKNOWN do NULL không bị xem là vi phạm CHECK.
- ENABLE NOVALIDATE enforce dữ liệu mới theo constraint nhưng không chứng minh toàn bộ dữ liệu cũ hợp lệ; VALIDATE mới kiểm tra dữ liệu hiện có.
- DEFERRABLE constraint có thể chỉ được kiểm tra tại commit; test flush đơn thuần chưa đủ.
- Index, view, materialized view, trigger, package, synonym và dynamic SQL cần được kiểm tra sau schema change.
- View dùng SELECT * không tự động phản ánh mọi column được thêm sau khi view được tạo; ưu tiên projection tường minh.
- Oracle có thể invalidate dependent PL/SQL/view và tự recompile khi cần, nhưng source còn tên cũ vẫn có thể compile thất bại.
- Expand-contract giữ tương thích trong rolling deployment; chỉ drop old column/object sau khi hết consumer cũ.
- DBMS_REDEFINITION hỗ trợ một số online table redefinition nhưng có prerequisite, dependency và cutover cần test.
- Oracle DDL implicit commit; Spring @Transactional và ROLLBACK không thể undo DDL hoặc DML đã commit trước DDL.
- Migration nhiều DDL có thể hoàn thành một phần; inspect dictionary và forward-fix thay vì chạy lại script mù quáng.
- Test schema change trên Oracle version/RU gần production, với dữ liệu và concurrency đại diện.
- Xác minh cả metadata, dữ liệu, application behavior, execution plan và dependent object trước khi đóng change.

### Tài liệu Oracle nên đối chiếu

- [Oracle Database SQL Language Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/) — ALTER TABLE, RENAME, constraints, datatype modification, DROP and TRUNCATE.
- [Oracle Database Administrator's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/) — Schema objects, dependencies, indexes, constraints and maintenance.
- [Oracle Database Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/) — DBA_DEPENDENCIES, DBA_TAB_COLUMNS, DBA_CONSTRAINTS, DBA_CONS_COLUMNS, DBA_INDEXES, DBA_OBJECTS and DBA_ERRORS.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_METADATA](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_METADATA.html) — Extracting object definitions.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_REDEFINITION](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_REDEFINITION.html) — Online table redefinition APIs and prerequisites.
- [Oracle Database Concepts](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/) — Dependencies, DDL, transactions and object lifecycle.
- [Oracle Database VLDB and Partitioning Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/vldbg/) — Large table maintenance and partitioning considerations.

DDL capabilities, online operations, datatype conversion restrictions and dependency behavior vary by Oracle release and object type. Confirm the exact release documentation, test against a representative schema and data volume, and use a separate change window with a forward-recovery plan for production schema evolution.

