# Giao dịch DDL, bảng tạm và hành vi sau lỗi

## 1. Vì sao DDL có thể làm transaction khác với điều bạn nghĩ?

Trong một ứng dụng, transaction thường được dùng để nhóm nhiều thay đổi dữ liệu:

```sql
BEGIN;

UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = 42;

INSERT INTO order_items(order_id, product_id, quantity)
VALUES (9001, 42, 1);

COMMIT;
```

Nếu một bước thất bại trước COMMIT, ứng dụng thường muốn ROLLBACK để không tạo ra trạng thái nửa vời.

Nhưng trong lúc triển khai schema hoặc chạy migration, ứng dụng còn thực hiện DDL:

```sql
ALTER TABLE orders ADD COLUMN source_code TEXT;
CREATE INDEX orders_source_code_idx ON orders(source_code);
CREATE TABLE migration_audit (...);
```

Không phải DBMS nào cũng xử lý những câu lệnh này giống nhau khi có transaction. Có hệ quản trị cho phép rollback phần lớn DDL; có hệ quản trị tự commit transaction hiện tại trước/sau DDL; có hệ quản trị hỗ trợ DDL nguyên tử khi crash nhưng vẫn không cho rollback theo transaction.

Ba khái niệm cần tách biệt:

1. **Transactional DDL:** thay đổi schema có thể tham gia transaction và được rollback cùng transaction theo phạm vi DBMS hỗ trợ.
2. **Implicit commit:** DBMS tự commit transaction đang mở khi gặp một số câu lệnh DDL.
3. **Atomic DDL/crash-safe DDL:** một thao tác DDL được bảo đảm hoàn tất hoặc không để lại trạng thái nửa chừng khi server gặp sự cố, nhưng điều này không đồng nghĩa có thể ROLLBACK nó sau khi câu lệnh đã thành công.

Một khái niệm khác là **temporary table**. Bảng tạm có thể có vòng đời theo transaction, session, connection hoặc thủ tục; hành vi này cũng khác nhau giữa các DBMS.

Bài học này lấy PostgreSQL, MySQL, SQL Server, Oracle và SQLite làm năm hệ quản trị đối chiếu. Mục tiêu là dự đoán đúng trạng thái database sau COMMIT, ROLLBACK, lỗi DDL, lỗi DML và khi connection được trả về pool.

---

## 2. Phân biệt DDL, DML và transaction control

| Nhóm | Ví dụ | Mục đích |
| --- | --- | --- |
| DDL | CREATE, ALTER, DROP, TRUNCATE | Định nghĩa/thay đổi cấu trúc đối tượng |
| DML | SELECT, INSERT, UPDATE, DELETE, MERGE | Đọc và thay đổi dữ liệu |
| Transaction control | BEGIN, COMMIT, ROLLBACK, SAVEPOINT | Điều khiển ranh giới transaction |
| Session control | SET, USE, PRAGMA tùy DBMS | Thay đổi ngữ cảnh hoặc cấu hình session |
| Administrative | VACUUM, CREATE DATABASE, backup/restore tùy DBMS | Quản trị và bảo trì hệ thống |

Phân loại này là cách nhóm khái niệm; mỗi DBMS có thể đặt một số câu lệnh vào nhóm hoặc quy tắc transaction riêng.

### 2.1. DDL thay đổi schema

Ví dụ:

```sql
CREATE TABLE app.audit_events (
    event_id BIGINT PRIMARY KEY,
    event_type TEXT NOT NULL
);
```

DDL có thể ảnh hưởng metadata, catalog, lock và những câu query đang sử dụng đối tượng.

### 2.2. DML thay đổi hàng

```sql
UPDATE app.orders
SET order_status = 'PAID'
WHERE order_id = 9001;
```

DML thường được đưa vào transaction. Tuy nhiên autocommit, isolation level, trigger, constraint và engine có thể ảnh hưởng cách thực thi.

### 2.3. TRUNCATE là trường hợp cần chú ý

TRUNCATE thường được xếp vào DDL hoặc nhóm thao tác làm rỗng bảng tùy tài liệu DBMS. Nó không tương đương DELETE về trigger, logging, identity/sequence, lock và transaction semantics.

Đừng chỉ nhìn tên lệnh để suy ra khả năng rollback.

---

## 3. Transaction bảo vệ điều gì?

Transaction thường được mô tả qua ACID:

- **Atomicity:** một transaction được commit như một đơn vị; rollback loại bỏ các thay đổi transactional thuộc transaction đó.
- **Consistency:** transaction đưa dữ liệu từ trạng thái thỏa các bất biến sang trạng thái thỏa các bất biến.
- **Isolation:** các transaction đồng thời được điều phối theo isolation level.
- **Durability:** dữ liệu đã commit được bảo vệ theo cam kết durability của hệ thống.

Khi nói “DDL transactional”, câu hỏi cụ thể là:

> Thay đổi schema có nằm trong đơn vị atomicity của transaction hiện tại hay không?

Không phải mọi DDL ở mọi DBMS đều có câu trả lời giống nhau.

### 3.1. Ví dụ DML rollback

```sql
BEGIN;

UPDATE app.accounts
SET balance = balance - 100
WHERE account_id = 1;

UPDATE app.accounts
SET balance = balance + 100
WHERE account_id = 2;

ROLLBACK;
```

Nếu hai UPDATE thuộc cùng transaction transactional, ROLLBACK hủy cả hai thay đổi.

### 3.2. DDL có thể nằm ngoài transaction

Ở DBMS tự implicit commit khi chạy DDL, một câu CREATE TABLE có thể commit các DML trước đó. Khi đó ROLLBACK sau DDL không thể khôi phục trạng thái trước khi implicit commit.

### 3.3. Atomic không đồng nghĩa transactional

Giả sử server chết giữa thao tác tạo index:

- **Atomic DDL** bảo đảm sau recovery không có index nửa hoàn chỉnh theo cam kết của engine.
- **Transactional DDL** cho phép người dùng chủ động rollback một DDL đã chạy thành công nhưng transaction chưa commit.

Hai bảo đảm giải quyết hai thời điểm khác nhau.

---

## 4. Mô hình thử nghiệm chung

Để so sánh, dùng một bảng đơn giản:

```sql
CREATE TABLE demo_accounts (
    account_id INTEGER PRIMARY KEY,
    owner_name VARCHAR(100) NOT NULL,
    balance DECIMAL(12,2) NOT NULL
);

INSERT INTO demo_accounts(account_id, owner_name, balance)
VALUES
    (1, 'An', 1000.00),
    (2, 'Bình', 500.00);
```

Và một DDL thay đổi schema:

```sql
ALTER TABLE demo_accounts
ADD COLUMN account_note VARCHAR(100);
```

Trong từng DBMS, cú pháp khai báo kiểu identity, schema và transaction có thể khác. Mẫu trên minh họa ý tưởng, không phải một migration portable nguyên xi cho mọi engine.

### 4.1. Câu hỏi khi thử nghiệm

Trước khi chạy, ghi lại:

- Số dư hai tài khoản.
- Cột account_note có tồn tại chưa?
- Có temporary table nào trong session?
- Autocommit đang bật hay tắt?
- Transaction hiện tại đã bắt đầu chưa?
- Connection là session mới hay được lấy từ pool?

Sau mỗi thao tác, kiểm tra lại các trạng thái này từ một connection phù hợp.

### 4.2. Không dùng một session duy nhất để kiểm tra mọi kết quả

Temporary table thường chỉ thấy trong session tạo ra. Dùng connection khác để kiểm tra bảng tạm có thể dẫn đến kết luận sai rằng bảng không tồn tại.

Ngược lại, một DDL đã implicit commit có thể làm thay đổi dữ liệu permanent mà session khác nhìn thấy.

---

## 5. PostgreSQL: phần lớn DDL thông thường có thể rollback

PostgreSQL hỗ trợ transactional DDL cho nhiều lệnh schema thông thường.

Ví dụ:

```sql
BEGIN;

CREATE TABLE demo_ddl_rollback (
    id INTEGER PRIMARY KEY,
    note TEXT
);

INSERT INTO demo_ddl_rollback(id, note)
VALUES (1, 'created inside transaction');

ROLLBACK;
```

Sau ROLLBACK, bảng demo_ddl_rollback không còn tồn tại. Cả thao tác tạo bảng lẫn INSERT được rollback trong transaction đó.

### 5.1. ALTER TABLE cũng thường transactional

```sql
BEGIN;

ALTER TABLE demo_accounts
ADD COLUMN migration_marker TEXT;

ROLLBACK;
```

Sau rollback, cột migration_marker không còn được thêm bởi transaction vừa hủy.

### 5.2. CREATE INDEX thông thường

```sql
BEGIN;

CREATE INDEX demo_accounts_owner_idx
ON demo_accounts(owner_name);

ROLLBACK;
```

Index thông thường được tạo trong transaction và có thể bị rollback.

### 5.3. DDL transactional không có nghĩa không cần lock

ALTER TABLE có thể cần lock mạnh trên bảng. Transaction giữ lock cho tới COMMIT/ROLLBACK, có thể chặn query hoặc migration khác.

Một transaction DDL dài có thể gây:

- Query chờ lock.
- Migration sau bị xếp hàng.
- Connection pool cạn.
- Deadlock hoặc timeout.
- Tăng thời gian triển khai.

Transactional DDL giúp rollback, nhưng không loại bỏ chi phí lock và ảnh hưởng workload.

### 5.4. Một số lệnh PostgreSQL không chạy trong transaction block

Không phải mọi câu lệnh PostgreSQL đều transactional. Một số lệnh quản trị bị cấm chạy bên trong transaction block, tùy phiên bản và lệnh cụ thể. Những ví dụ đáng biết:

- CREATE DATABASE / DROP DATABASE.
- CREATE TABLESPACE / DROP TABLESPACE.
- VACUUM (ngoại trừ một số biến thể/hành vi đặc biệt theo phiên bản).
- CREATE INDEX CONCURRENTLY.
- DROP INDEX CONCURRENTLY.
- REINDEX CONCURRENTLY.

Trước khi viết migration, kiểm tra tài liệu đúng phiên bản cho câu lệnh cụ thể.

### 5.5. CREATE INDEX CONCURRENTLY là trường hợp đặc biệt

```sql
CREATE INDEX CONCURRENTLY demo_accounts_owner_idx
ON demo_accounts(owner_name);
```

PostgreSQL không cho chạy CREATE INDEX CONCURRENTLY bên trong transaction block. Công cụ migration phải đánh dấu migration hoặc bước đó chạy ngoài transaction nếu framework hỗ trợ.

Nếu thao tác thất bại, có thể để lại một index INVALID cần kiểm tra và dọn dẹp theo quy trình phù hợp trước khi thử lại. Không mặc định rằng một lỗi sẽ để lại database y nguyên.

### 5.6. SAVEPOINT và DDL

DDL transactional thông thường có thể nằm trong transaction dùng SAVEPOINT:

```sql
BEGIN;

SAVEPOINT before_schema_change;

ALTER TABLE demo_accounts
ADD COLUMN temporary_flag BOOLEAN;

ROLLBACK TO SAVEPOINT before_schema_change;

COMMIT;
```

Sau COMMIT, cột temporary_flag không tồn tại do đã rollback về savepoint, nhưng transaction bên ngoài vẫn commit được.

Không áp dụng mẫu này cho lệnh bị cấm trong transaction block.

---

## 6. MySQL: DDL thường implicit commit

MySQL có một đặc điểm quan trọng: nhiều DDL gây **implicit commit**.

Ví dụ với bảng InnoDB:

```sql
START TRANSACTION;

UPDATE demo_accounts
SET balance = balance - 100
WHERE account_id = 1;

ALTER TABLE demo_accounts
ADD COLUMN account_note VARCHAR(100);

ROLLBACK;
```

Đối với DDL thuộc nhóm implicit commit, transaction đang mở được commit trước khi câu lệnh thực thi; một số câu lệnh còn commit sau khi hoàn thành thành công theo quy tắc của MySQL.

Vì thế UPDATE trước ALTER TABLE có thể đã được commit trước khi ROLLBACK chạy. ROLLBACK không thể khôi phục số dư ban đầu.

### 6.1. Implicit commit không đồng nghĩa DDL luôn thành công

Nếu ALTER TABLE thất bại, vẫn cần biết implicit commit đã xảy ra ở thời điểm nào và DDL đó có atomic/crash-safe trong phiên bản/engine đang dùng hay không.

Không suy luận rằng “lệnh lỗi thì mọi thứ trước nó tự rollback”.

### 6.2. Atomic DDL của MySQL 8.0 không biến DDL thành transactional DDL

MySQL 8.0 hỗ trợ atomic DDL cho nhiều thao tác trên các engine/đối tượng được hỗ trợ. Atomic DDL giúp bảo đảm thay đổi dictionary và storage được xử lý nguyên tử trong tình huống crash theo phạm vi hỗ trợ.

Nhưng câu DDL vẫn có thể gây implicit commit. Bạn không thể chạy ALTER TABLE thành công rồi ROLLBACK để hủy nó như một UPDATE InnoDB thông thường.

### 6.3. Một số DDL có quy tắc implicit commit đặc biệt

MySQL có các ngoại lệ đáng chú ý như CREATE TEMPORARY TABLE và DROP TEMPORARY TABLE: chúng không gây implicit commit theo cách DDL thông thường, nhưng bản thân thao tác tạo/xóa temporary table **không thể được rollback**.

Đây là ví dụ điển hình cho thấy hai câu hỏi phải tách riêng:

- Có implicit commit không?
- Thao tác đó có rollback được không?

### 6.4. TRUNCATE TABLE

Trong MySQL, TRUNCATE TABLE thường gây implicit commit và không thể rollback như DELETE transactional của InnoDB.

Nếu cần xóa hàng trong transaction và có khả năng rollback, cân nhắc DELETE với điều kiện phù hợp, sau khi hiểu trigger, foreign key và hiệu năng.

### 6.5. DDL và engine

Atomicity của DML phụ thuộc storage engine. InnoDB hỗ trợ transaction; một số engine khác có hành vi khác. Không khái quát mọi bảng MySQL đều có cùng bảo đảm transaction.

### 6.6. Kiểm tra version và engine

Trước khi viết migration MySQL, kiểm tra:

```sql
SELECT VERSION();

SHOW TABLE STATUS LIKE 'demo_accounts';
```

Đặc biệt quan tâm MySQL version, storage engine và loại DDL đang chạy.

---

## 7. SQL Server: nhiều DDL có thể tham gia transaction

SQL Server hỗ trợ transaction cho nhiều thao tác DDL.

Ví dụ:

```sql
BEGIN TRANSACTION;

CREATE TABLE dbo.demo_ddl_rollback (
    id INT PRIMARY KEY,
    note NVARCHAR(100)
);

INSERT INTO dbo.demo_ddl_rollback(id, note)
VALUES (1, N'created inside transaction');

ROLLBACK TRANSACTION;
```

Với các câu lệnh hỗ trợ transactional behavior, bảng và hàng được rollback.

### 7.1. ALTER TABLE trong transaction

```sql
BEGIN TRANSACTION;

ALTER TABLE dbo.demo_accounts
ADD account_note NVARCHAR(100);

ROLLBACK TRANSACTION;
```

Thay đổi schema có thể được rollback trong trường hợp thông thường.

### 7.2. Không phải mọi lệnh quản trị đều chạy trong transaction

Một số thao tác như CREATE DATABASE, ALTER DATABASE hoặc DROP DATABASE có các giới hạn transaction riêng. Một số lệnh maintenance/backup/restore cũng có quy tắc riêng.

Luôn kiểm tra danh sách lệnh hỗ trợ transaction trong phiên bản SQL Server đang dùng.

### 7.3. XACT_STATE và lỗi trong transaction

SQL Server có thể đưa transaction vào trạng thái không thể commit sau một lỗi tùy loại lỗi và cấu hình.

```sql
BEGIN TRY
    BEGIN TRANSACTION;

    UPDATE dbo.demo_accounts
    SET balance = balance - 100
    WHERE account_id = 1;

    -- Một thao tác có thể lỗi
    INSERT INTO dbo.demo_accounts(account_id, owner_name, balance)
    VALUES (1, N'Duplicate', 10);

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF XACT_STATE() <> 0
        ROLLBACK TRANSACTION;

    THROW;
END CATCH;
```

XACT_STATE:

- 1: transaction đang hoạt động và có thể commit.
- -1: transaction đang hoạt động nhưng không thể commit; chỉ có thể rollback toàn transaction.
- 0: không có transaction đang hoạt động.

Mẫu TRY/CATCH giúp rollback khi lỗi; chi tiết còn phụ thuộc XACT_ABORT và loại lỗi.

### 7.4. SET XACT_ABORT

```sql
SET XACT_ABORT ON;
```

Với nhiều lỗi runtime, tùy chọn này khiến SQL Server rollback toàn transaction thay vì chỉ rollback statement. Nhưng nó không biến mọi lỗi compile, lỗi kết nối hoặc mọi lệnh quản trị thành một hành vi giống nhau.

### 7.5. DDL transactional vẫn có thể giữ lock

ALTER TABLE, CREATE INDEX và các thay đổi schema có thể giữ schema-modification lock, gây chờ truy vấn. Transaction dài khiến thời gian giữ lock kéo dài.

---

## 8. Oracle: DDL implicit commit trước và sau

Oracle có một quy tắc khác biệt lớn: nhiều DDL tự commit transaction hiện tại **trước khi thực hiện**, và commit sau khi DDL thành công.

Ví dụ:

```sql
UPDATE demo_accounts
SET balance = balance - 100
WHERE account_id = 1;

CREATE TABLE demo_ddl_test (
    id NUMBER PRIMARY KEY
);

ROLLBACK;
```

UPDATE trước CREATE TABLE có thể đã được commit bởi implicit commit trước DDL. ROLLBACK sau đó không khôi phục số dư ban đầu.

### 8.1. DDL không rollback như DML

Nếu CREATE TABLE thành công, DDL đã được commit theo quy tắc Oracle. ROLLBACK sau đó không xóa bảng vừa tạo.

### 8.2. Nếu DDL thất bại thì sao?

Implicit commit **trước** DDL có thể đã commit các DML trước đó, ngay cả khi chính câu DDL thất bại. Vì vậy không nên dùng một transaction DML chưa commit rồi chạy DDL với giả định có thể rollback tất cả nếu DDL không thành công.

### 8.3. DDL commit sau khi thành công

Quy tắc thường gặp của Oracle:

1. Commit transaction hiện tại trước DDL.
2. Thực hiện DDL.
3. Nếu DDL thành công, commit thay đổi DDL.

Chi tiết lỗi/loại DDL vẫn phải kiểm tra theo tài liệu Oracle, nhưng không nên dựa vào ROLLBACK để đảo DDL.

### 8.4. SAVEPOINT không bảo vệ qua implicit commit

```sql
SAVEPOINT before_ddl;

ALTER TABLE demo_accounts
ADD account_note VARCHAR2(100);

ROLLBACK TO before_ddl;
```

Không thể dùng savepoint để rollback qua DDL đã implicit commit; savepoint cũ có thể không còn hiệu lực sau commit.

### 8.5. Transaction DML và DDL nên tách

Trong Oracle, migration thường được thiết kế thành những bước DDL độc lập, có kiểm tra trước/sau và quy trình khôi phục riêng. Không gộp DML chưa commit vào cùng phiên thực hiện DDL nếu muốn giữ khả năng rollback DML.

---

## 9. SQLite: DDL thường có thể nằm trong transaction

SQLite hỗ trợ transaction cho nhiều thao tác schema như CREATE TABLE, ALTER TABLE và DROP TABLE.

Ví dụ:

```sql
BEGIN;

CREATE TABLE demo_ddl_rollback (
    id INTEGER PRIMARY KEY,
    note TEXT
);

INSERT INTO demo_ddl_rollback(id, note)
VALUES (1, 'created inside transaction');

ROLLBACK;
```

Sau rollback, bảng vừa tạo và dữ liệu trong đó không còn.

### 9.1. SAVEPOINT

SQLite hỗ trợ savepoint:

```sql
BEGIN;

SAVEPOINT before_change;

ALTER TABLE demo_accounts
ADD COLUMN account_note TEXT;

ROLLBACK TO before_change;

RELEASE before_change;

COMMIT;
```

Thay đổi schema được rollback về savepoint trong những điều kiện hỗ trợ.

### 9.2. Lock và writer concurrency

SQLite có mô hình locking/transaction riêng. DDL có thể cần lock ghi và gặp SQLITE_BUSY khi connection khác đang giữ lock không tương thích.

Một lỗi SQLITE_BUSY không nhất thiết có nghĩa database đã thay đổi schema. Cần kiểm tra trạng thái transaction và connection.

### 9.3. PRAGMA và lệnh đặc biệt

Không phải mọi câu PRAGMA đều có cùng transaction behavior. Một số thao tác cấu hình hoặc thay đổi journal mode có giới hạn riêng. Đừng suy ra mọi lệnh SQLite đều rollback được chỉ vì CREATE TABLE transactional.

### 9.4. Foreign key

Bật/tắt foreign key enforcement có quy tắc theo connection và transaction. Ví dụ PRAGMA foreign_keys không thể được thay đổi hiệu lực giữa một transaction đang mở trong cách dùng thông thường. Cấu hình cần được đặt đúng thời điểm trên từng connection.

---

## 10. Bảng so sánh transactional DDL

| DBMS | DDL thông thường | DDL và implicit commit | Ghi chú quan trọng |
| --- | --- | --- | --- |
| PostgreSQL | Nhiều lệnh CREATE/ALTER/DROP có thể rollback | Không có quy tắc implicit commit chung như MySQL/Oracle | Một số lệnh bị cấm trong transaction block, ví dụ CREATE INDEX CONCURRENTLY |
| MySQL | Nhiều DDL không rollback như DML | Nhiều DDL gây implicit commit | Atomic DDL không đồng nghĩa transactional DDL; temp table DDL là ngoại lệ đặc biệt |
| SQL Server | Nhiều DDL có thể tham gia transaction | Không áp dụng một quy tắc implicit commit DDL chung | Một số lệnh database/admin không được chạy trong transaction; XACT_STATE quan trọng |
| Oracle | DDL thường tự commit | Commit trước và sau DDL thành công | Không rollback DDL bằng transaction thông thường |
| SQLite | Nhiều DDL có thể rollback | Không có implicit commit DDL chung cho CREATE/ALTER/DROP thông thường | PRAGMA và lệnh đặc biệt có quy tắc riêng |

**Không dùng một nhãn “DDL transactional” để kết luận tất cả câu lệnh của một DBMS.** Hãy kiểm tra từng lệnh, phiên bản và storage engine.

---

## 11. Bảng tạm là gì?

Temporary table là bảng có vòng đời hoặc phạm vi truy cập đặc biệt, thường dùng cho dữ liệu trung gian của một session hoặc transaction.

Ví dụ use case:

- Tập ID cần xử lý trong một request.
- Kết quả trung gian của báo cáo nhiều bước.
- Dữ liệu staging trước khi MERGE/UPDATE.
- Tập khóa được lọc từ một file import.
- Bảng làm việc để chia batch.

Một bảng tạm có schema/cột/index/constraint tương tự bảng thường ở mức sử dụng, nhưng **vòng đời, phạm vi hiển thị và lưu trữ** phụ thuộc DBMS.

### 11.1. Bảng tạm khác CTE

CTE:

```sql
WITH recent_orders AS (
    SELECT *
    FROM orders
    WHERE created_at >= CURRENT_DATE - INTERVAL '7 days'
)
SELECT *
FROM recent_orders;
```

là một cấu trúc trong một câu query. Nó không phải một bảng có vòng đời session.

Temporary table là đối tượng có thể được tham chiếu qua nhiều câu lệnh trong phạm vi cho phép.

### 11.2. Bảng tạm khác bảng staging permanent

Bảng staging permanent có thể được nhiều session/worker sử dụng, nhưng cần phân vùng theo job/request, cleanup, quyền và isolation.

Temporary table thường cô lập tên/dữ liệu theo session tốt hơn, nhưng không tự phù hợp cho mọi job phân tán hoặc mọi connection pool.

---

## 12. PostgreSQL temporary table

PostgreSQL hỗ trợ:

```sql
CREATE TEMPORARY TABLE temp_selected_customers (
    customer_id BIGINT PRIMARY KEY,
    reason TEXT
);
```

TEMP và TEMPORARY tương đương trong ngữ cảnh tạo temporary table.

### 12.1. Phạm vi session

Temporary table PostgreSQL chỉ hiển thị trong session tạo ra. Session khác không truy cập được cùng temporary table.

```sql
INSERT INTO temp_selected_customers(customer_id, reason)
VALUES (1, 'manual review');

SELECT *
FROM temp_selected_customers;
```

### 12.2. ON COMMIT PRESERVE ROWS

Đây là hành vi mặc định:

```sql
CREATE TEMP TABLE temp_keep (
    id INTEGER
)
ON COMMIT PRESERVE ROWS;
```

Khi transaction commit, hàng vẫn còn trong temporary table cho tới khi session kết thúc hoặc bảng bị drop/truncate.

### 12.3. ON COMMIT DELETE ROWS

```sql
CREATE TEMP TABLE temp_clear (
    id INTEGER
)
ON COMMIT DELETE ROWS;
```

Sau COMMIT, các hàng bị xóa, nhưng cấu trúc bảng vẫn tồn tại trong session.

### 12.4. ON COMMIT DROP

```sql
CREATE TEMP TABLE temp_one_tx (
    id INTEGER
)
ON COMMIT DROP;
```

Sau khi transaction commit, temporary table bị drop. Nếu tạo trong transaction rồi rollback, thao tác tạo bảng cũng rollback theo transactional DDL PostgreSQL.

### 12.5. Mẫu sử dụng ON COMMIT DELETE ROWS

```sql
BEGIN;

CREATE TEMP TABLE temp_order_ids (
    order_id BIGINT
) ON COMMIT DELETE ROWS;

INSERT INTO temp_order_ids(order_id)
VALUES (1001), (1002);

SELECT o.*
FROM orders AS o
JOIN temp_order_ids AS t USING (order_id);

COMMIT;
```

Sau COMMIT, temp_order_ids vẫn tồn tại trong session nhưng rỗng.

### 12.6. Temporary schema

PostgreSQL đặt temporary relation trong schema tạm của session. Tên bảng tạm có thể che khuất bảng permanent cùng tên khi name resolution ưu tiên temporary schema.

Để tránh nhầm, schema-qualify bảng permanent khi query quan trọng và không đặt tên bảng tạm gây nhập nhằng.

### 12.7. Index và constraint

Có thể tạo index/constraint trên temporary table. Chúng cũng có vòng đời gắn với bảng tạm.

Nếu dữ liệu tạm rất lớn, việc tạo index có thể giúp query sau nhanh hơn nhưng cũng có chi phí nạp và xây index. Đo với workload thực.

---

## 13. MySQL temporary table

MySQL dùng cú pháp:

```sql
CREATE TEMPORARY TABLE temp_selected_customers (
    customer_id BIGINT PRIMARY KEY,
    reason VARCHAR(100)
);
```

### 13.1. Phạm vi session/connection

Temporary table chỉ hiển thị trong session tạo ra và được tự động drop khi session đóng.

Hai connection có thể cùng tạo temporary table tên temp_selected_customers mà không xung đột vì phạm vi session riêng.

### 13.2. Che khuất bảng permanent cùng tên

Nếu có permanent table cùng tên trong database, temporary table cùng tên trong session sẽ che khuất nó trong name resolution.

Điều này có thể làm một câu SQL trỏ tới bảng tạm thay vì bảng permanent. Dùng tên tạm riêng biệt và kiểm soát connection/session.

### 13.3. Temporary table DDL và rollback là hai vấn đề riêng

MySQL có ngoại lệ implicit commit cho CREATE TEMPORARY TABLE và DROP TEMPORARY TABLE: chúng không gây implicit commit theo quy tắc DDL thông thường.

Tuy nhiên thao tác tạo/xóa temporary table không được rollback như DDL transactional. Ví dụ:

```sql
START TRANSACTION;

CREATE TEMPORARY TABLE temp_demo (
    id INT
);

ROLLBACK;
```

ROLLBACK không nhất thiết xóa temporary table đã tạo. Hãy kiểm tra trạng thái trong chính session.

### 13.4. Dữ liệu của temporary table và storage engine

DML trên temporary table vẫn phụ thuộc engine/transaction semantics. Temporary table InnoDB có thể tham gia transaction cho các thay đổi dữ liệu theo quy tắc engine; điều đó không làm CREATE/DROP temporary table trở thành rollbackable.

### 13.5. Index

MySQL cho phép index/primary key trên temporary table. Chọn index theo query; không tạo quá nhiều index nếu chỉ nạp và đọc một lần.

### 13.6. Connection pool

Khi một request trả connection về pool, session có thể được tái sử dụng. Temporary table có thể vẫn còn nếu connection thực sự chưa đóng.

Cần drop/cleanup rõ hoặc cấu hình pool reset session phù hợp. Không giả định close logical connection đồng nghĩa physical session đã kết thúc.

---

## 14. SQL Server temporary table

SQL Server có hai dạng thường gặp.

### 14.1. Local temporary table: #name

```sql
CREATE TABLE #selected_customers (
    customer_id BIGINT PRIMARY KEY,
    reason NVARCHAR(100)
);
```

Tên bắt đầu bằng một dấu #. Local temporary table thường chỉ hiển thị trong session tạo ra; SQL Server lưu metadata/dữ liệu trong tempdb và tự cleanup theo vòng đời.

### 14.2. Global temporary table: ##name

```sql
CREATE TABLE ##shared_work (
    customer_id BIGINT,
    worker_name NVARCHAR(100)
);
```

Tên bắt đầu bằng hai dấu ##. Global temporary table có thể được session khác nhìn thấy; vòng đời phụ thuộc session tạo và các session còn sử dụng theo quy tắc phiên bản SQL Server.

Không dùng global temp table như một hàng đợi chia sẻ mà không thiết kế concurrency, quyền và cleanup.

### 14.3. Phạm vi trong stored procedure

Local temp table tạo trong stored procedure thường được drop khi procedure kết thúc. Temp table tạo ở scope bên ngoài có thể được procedure lồng bên trong sử dụng theo quy tắc scope.

Điều này hữu ích cho thủ tục nhiều bước, nhưng tên và scope cần được kiểm soát khi lồng procedure.

### 14.4. Transaction với temp table

SQL Server hỗ trợ transaction cho nhiều thao tác trên temporary table, bao gồm DML và nhiều DDL thông thường.

Ví dụ:

```sql
CREATE TABLE #temp_demo(id INT);

BEGIN TRANSACTION;

INSERT INTO #temp_demo(id) VALUES (1);

ROLLBACK TRANSACTION;

SELECT * FROM #temp_demo;
```

Bảng tạm vẫn tồn tại trong session nhưng hàng INSERT trong transaction đã rollback.

### 14.5. Connection pooling

Một local temp table có thể tồn tại trong physical session được pool giữ lại. Driver/pool có thể reset một số trạng thái khi trả connection, nhưng không nên mặc định mọi cấu hình đều cleanup mọi đối tượng session.

Tạo tên tạm ổn định, cleanup trong finally/transaction và kiểm tra behavior của pool.

---

## 15. Oracle global temporary table (GTT)

Oracle có **Global Temporary Table**. Tên bảng và định nghĩa được tạo như một object database tồn tại lâu dài, nhưng dữ liệu được cô lập theo session hoặc transaction tùy khai báo.

Ví dụ:

```sql
CREATE GLOBAL TEMPORARY TABLE temp_selected_customers (
    customer_id NUMBER PRIMARY KEY,
    reason VARCHAR2(100)
)
ON COMMIT DELETE ROWS;
```

### 15.1. ON COMMIT DELETE ROWS

Dữ liệu của session bị xóa khi transaction commit. Định nghĩa bảng vẫn tồn tại.

### 15.2. ON COMMIT PRESERVE ROWS

```sql
CREATE GLOBAL TEMPORARY TABLE temp_keep_rows (
    id NUMBER
)
ON COMMIT PRESERVE ROWS;
```

Dữ liệu được giữ trong session qua các transaction, cho tới khi session kết thúc hoặc dữ liệu bị xóa.

### 15.3. Global trong tên không có nghĩa dữ liệu chia sẻ

Global Temporary Table có **định nghĩa global**, nhưng dữ liệu riêng của từng session. Session A không nhìn thấy hàng temporary của session B.

### 15.4. DDL tạo GTT vẫn chịu implicit commit của Oracle

CREATE GLOBAL TEMPORARY TABLE là DDL. Nó vẫn tuân theo quy tắc implicit commit của Oracle; không thể gộp nó vào transaction DML rồi kỳ vọng rollback tất cả.

### 15.5. Index và constraint

Có thể tạo index trên GTT. Dữ liệu index được quản lý theo dữ liệu temporary tương ứng. Kiểm tra các giới hạn/định nghĩa cụ thể khi tạo index và constraint trong phiên bản Oracle đang dùng.

### 15.6. Private temporary table

Oracle từ 18c có Private Temporary Table với tên và vòng đời riêng, thường dùng prefix được cấu hình (mặc định phổ biến là ORA$PTT_).

Một số định nghĩa có thể có transaction duration hoặc session duration theo cú pháp Oracle. Đây là tính năng khác GTT truyền thống và phụ thuộc version.

---

## 16. SQLite temporary table

SQLite hỗ trợ:

```sql
CREATE TEMP TABLE selected_customers (
    customer_id INTEGER PRIMARY KEY,
    reason TEXT
);
```

TEMP/TEMPORARY tạo bảng trong database tạm của connection.

### 16.1. Phạm vi connection

Temporary table chỉ tồn tại trong connection tạo ra. Connection khác không thấy nó.

Khi connection đóng, bảng tạm được dọn cùng database tạm của connection.

### 16.2. Không phải global temp table

SQLite không có khái niệm global temporary table server-side tương tự SQL Server. Database temp thuộc connection.

### 16.3. Transaction

CREATE TEMP TABLE và các thao tác DDL SQLite thông thường có thể tham gia transaction. Nếu tạo bảng tạm trong transaction rồi rollback, bảng có thể bị rollback cùng transaction.

### 16.4. Connection pool

Nếu connection được tái sử dụng, temporary table có thể tồn tại trong connection đó sau khi request kết thúc nếu chưa drop. Cleanup phải được thực hiện trước khi trả connection về pool hoặc đảm bảo cơ chế reset.

### 16.5. Temp store

SQLite có thể giữ temporary data trong memory hoặc file tùy compile options/PRAGMA/temp_store và kích thước. Không suy ra temporary table luôn chỉ nằm trong RAM.

---

## 17. Bảng so sánh temporary table

| DBMS | Cú pháp điển hình | Phạm vi dữ liệu | Hành vi sau COMMIT | Tự dọn |
| --- | --- | --- | --- | --- |
| PostgreSQL | CREATE TEMP TABLE | Session | PRESERVE mặc định; DELETE ROWS; DROP theo ON COMMIT | Khi session kết thúc hoặc DROP |
| MySQL | CREATE TEMPORARY TABLE | Session/connection | Dữ liệu theo transaction engine; tạo/xóa bảng tạm không rollback | Khi session đóng |
| SQL Server | CREATE TABLE #x / ##x | Local session; global cho nhiều session | Bảng và dữ liệu theo transaction/scope | Local theo scope/session; global theo lifecycle và reference |
| Oracle | CREATE GLOBAL TEMPORARY TABLE | Dữ liệu riêng session | DELETE ROWS hoặc PRESERVE ROWS | Dữ liệu theo transaction/session; định nghĩa vẫn tồn tại |
| SQLite | CREATE TEMP TABLE | Connection | Bảng/dữ liệu còn cho tới drop/close, trừ rollback DDL | Khi connection đóng |

**Đừng chỉ nhìn chữ TEMPORARY.** Hỏi riêng định nghĩa tồn tại bao lâu, dữ liệu tồn tại bao lâu, session nào nhìn thấy, COMMIT/ROLLBACK ảnh hưởng ra sao.

---

## 18. Bốn loại vòng đời cần phân biệt

Một temporary table có ít nhất bốn câu hỏi độc lập:

1. **Definition lifetime:** định nghĩa bảng tồn tại đến khi nào?
2. **Data lifetime:** hàng trong bảng tồn tại đến khi nào?
3. **Visibility scope:** session/connection nào có thể thấy?
4. **Transaction behavior:** COMMIT/ROLLBACK ảnh hưởng DDL và DML ra sao?

Ví dụ:

- PostgreSQL ON COMMIT DELETE ROWS: định nghĩa tồn tại trong session, dữ liệu bị xóa khi commit.
- Oracle GTT ON COMMIT PRESERVE ROWS: định nghĩa database tồn tại lâu dài, dữ liệu riêng session được giữ qua commit.
- MySQL TEMPORARY TABLE: định nghĩa theo session, nhưng CREATE/DROP không rollback được dù không implicit commit như DDL thường.
- SQL Server #temp: định nghĩa local theo session/procedure scope; DML vẫn có thể rollback.
- SQLite TEMP: định nghĩa gắn connection; DDL có thể nằm trong transaction.

Nếu chỉ hỏi “bảng tạm có bị xóa khi commit không?”, câu trả lời thường thiếu một nửa ngữ nghĩa.

---

## 19. Connection pool và bảng tạm: nguồn lỗi khó tìm

Ứng dụng web thường lấy connection từ pool:

```java
try (Connection connection = dataSource.getConnection()) {
    // Thực hiện query
}
```

`Connection.close()` trong pool thường trả logical connection về pool, không đóng physical database session ngay.

### 19.1. Tình huống lỗi

1. Request A lấy physical connection C1.
2. A tạo temporary table temp_work.
3. A trả connection về pool mà không drop.
4. Request B lấy lại đúng C1.
5. B thấy temp_work còn tồn tại, hoặc dữ liệu cũ vẫn còn.
6. B gặp lỗi “table already exists” hoặc xử lý nhầm dữ liệu.

### 19.2. Các biện pháp

- Tạo/drop temp table trong một scope được quản lý rõ.
- Dùng tên tạm có quy tắc và tránh xung đột.
- Xóa dữ liệu tạm trước khi reuse nếu phù hợp.
- Đảm bảo rollback/commit và cleanup chạy trong finally.
- Hiểu cơ chế reset session của pool/driver.
- Integration test với pool thật, không chỉ một connection đơn lẻ.

### 19.3. Không chỉ dựa vào close()

Đừng giả định gọi Connection.close() sẽ drop temp table trên physical session nếu pool chỉ trả connection về danh sách rảnh.

### 19.4. Không cleanup khi transaction còn cần dữ liệu

Nếu bảng tạm có dữ liệu phục vụ các query tiếp theo trong cùng transaction, cleanup quá sớm sẽ làm query thất bại. Vòng đời temp table phải gắn với workflow thực tế.

---

## 20. Hành vi sau lỗi: đừng giả định mọi DBMS rollback giống nhau

Khi câu lệnh thứ ba trong migration lỗi, trạng thái cuối phụ thuộc:

- DDL có transactional không?
- Có implicit commit trước đó không?
- Autocommit đang bật hay tắt?
- Lỗi xảy ra trước hay sau bước commit?
- DDL có atomic/crash-safe không?
- Temporary table thuộc session nào?
- Dữ liệu tạm có transaction-bound không?
- Client đã mất kết nối trước khi nhận kết quả commit chưa?

### 20.1. PostgreSQL transactional DDL

Với DDL được hỗ trợ trong transaction, nếu statement lỗi, transaction có thể bị đánh dấu aborted. Các câu lệnh tiếp theo thường không chạy thành công cho tới khi rollback transaction hoặc rollback về savepoint thích hợp.

### 20.2. MySQL implicit commit

DDL có thể đã commit DML trước đó. Nếu DDL tiếp tục thành công rồi câu sau lỗi, rollback không thể xóa DDL đã commit.

### 20.3. Oracle implicit commit

DML trước DDL có thể đã được commit trước khi DDL chạy. Nếu DDL thành công, thay đổi DDL được commit; nếu DDL lỗi, phần DML đã commit trước đó vẫn không thể rollback.

### 20.4. SQL Server

Lỗi có thể khiến transaction vẫn hoạt động, bị doomed hoặc tự rollback tùy loại lỗi, XACT_ABORT và cấu hình. Kiểm tra XACT_STATE và @@TRANCOUNT, không đoán.

### 20.5. SQLite

Nếu lỗi xảy ra trong transaction, statement có thể bị rollback riêng hoặc transaction bị ảnh hưởng tùy loại lỗi. Kiểm tra sqlite error code và trạng thái transaction; không giả định mọi lỗi đều tự rollback toàn transaction.

---

## 21. Autocommit: ranh giới dễ bị hiểu nhầm

JDBC mặc định thường bật autocommit cho Connection mới theo JDBC API.

Khi autocommit bật, mỗi statement được commit như transaction riêng theo hành vi driver/DBMS, trừ các câu lệnh transaction control và trường hợp đặc biệt.

### 21.1. Tắt autocommit để quản lý transaction

```java
connection.setAutoCommit(false);

try {
    // Nhiều câu SQL
    connection.commit();
} catch (SQLException ex) {
    connection.rollback();
    throw ex;
}
```

### 21.2. DDL implicit commit có thể phá giả định của code

Nếu code:

1. Tắt autocommit.
2. UPDATE một hàng.
3. Chạy DDL MySQL/Oracle gây implicit commit.
4. Lỗi ở bước sau.
5. Gọi connection.rollback().

thì rollback không thể khôi phục DML đã bị implicit commit.

### 21.3. Không tự ý đổi autocommit trong transaction framework

Nếu Spring/JTA hoặc framework đang quản lý transaction, việc gọi setAutoCommit trực tiếp có thể phá transaction boundary hoặc gây lỗi. Để transaction manager quản lý.

### 21.4. Trạng thái autocommit sau pool reset

Pool có thể reset connection properties khi trả về. Không dựa vào trạng thái còn sót từ request trước; xác nhận transaction manager/pool config.

---

## 22. SAVEPOINT và giới hạn theo DBMS

SAVEPOINT tạo mốc rollback trong một transaction.

Ví dụ PostgreSQL/SQLite và các hệ hỗ trợ cú pháp tương tự:

```sql
BEGIN;

UPDATE demo_accounts
SET balance = balance - 100
WHERE account_id = 1;

SAVEPOINT after_debit;

UPDATE demo_accounts
SET balance = balance + 100
WHERE account_id = 2;

ROLLBACK TO SAVEPOINT after_debit;

COMMIT;
```

Sau COMMIT, chỉ thay đổi trước savepoint còn hiệu lực.

### 22.1. Savepoint không vượt qua implicit commit

Trong MySQL/Oracle, nếu DDL gây implicit commit, savepoint trước đó có thể bị xóa cùng transaction. Không thể rollback tới nó.

### 22.2. SQL Server savepoint

SQL Server dùng:

```sql
SAVE TRANSACTION after_debit;
ROLLBACK TRANSACTION after_debit;
```

Tên và cú pháp khác PostgreSQL. Khi transaction ở trạng thái doomed, rollback tới savepoint có thể không đủ; cần rollback toàn transaction.

### 22.3. Savepoint không phải transaction độc lập

Savepoint không commit dữ liệu và không tạo một transaction con độc lập với durability riêng. COMMIT/ROLLBACK transaction ngoài cùng vẫn quyết định kết quả.

---

## 23. Lock và DDL concurrency

DDL thường cần lock metadata/schema. Khi một transaction giữ lock, câu query hoặc DDL khác có thể phải chờ.

### 23.1. PostgreSQL

ALTER TABLE có thể yêu cầu lock mạnh; lock được giữ đến hết transaction. Transaction DDL mở lâu làm query khác chờ.

### 23.2. MySQL

DDL thường cần metadata lock. Một transaction đang đọc/ghi bảng có thể giữ metadata lock và khiến ALTER TABLE chờ. Ngược lại, DDL đang chờ cũng có thể làm query mới xếp hàng tùy tình huống.

### 23.3. SQL Server

Schema modification lock có thể chặn query sử dụng object. Online index operation giảm một số ảnh hưởng nhưng không loại bỏ mọi lock.

### 23.4. Oracle

DDL và DML có lock/metadata behavior riêng; DDL implicit commit không có nghĩa thao tác schema không phải chờ lock.

### 23.5. SQLite

SQLite có locking và chỉ một writer tại một thời điểm theo cơ chế journal/WAL; schema change có thể cần lock và gặp SQLITE_BUSY.

### 23.6. Chiến lược

- Giữ migration ngắn.
- Chạy ngoài giờ cao điểm khi phù hợp.
- Đặt lock timeout phù hợp.
- Kiểm tra transaction/idle-in-transaction.
- Ước lượng thời gian build index/rewrite table.
- Dùng online/concurrent operation khi DBMS hỗ trợ và hiểu giới hạn của nó.
- Không chạy DDL lớn từ request web thông thường.

---

## 24. Migration thất bại giữa chừng: ví dụ theo từng bước

Giả sử migration có ba bước:

```sql
ALTER TABLE app.orders
ADD COLUMN source_code TEXT;

UPDATE app.orders
SET source_code = 'legacy'
WHERE source_code IS NULL;

CREATE INDEX orders_source_code_idx
ON app.orders(source_code);
```

Điều gì xảy ra nếu CREATE INDEX lỗi?

### 24.1. PostgreSQL trong một transaction

```sql
BEGIN;

ALTER TABLE app.orders
ADD COLUMN source_code TEXT;

UPDATE app.orders
SET source_code = 'legacy'
WHERE source_code IS NULL;

CREATE INDEX orders_source_code_idx
ON app.orders(source_code);

COMMIT;
```

Nếu CREATE INDEX thông thường lỗi, transaction có thể bị aborted; rollback sẽ loại bỏ cả cột, dữ liệu cập nhật và index tạo trong transaction.

Nếu dùng CREATE INDEX CONCURRENTLY, không thể đặt nó trong transaction block; cần tách bước và thiết kế recovery.

### 24.2. MySQL

ALTER TABLE thường implicit commit. DML có thể được commit trước DDL; bước UPDATE sau DDL có thể là transaction riêng nếu autocommit/cấu hình như vậy. CREATE INDEX là DDL và có thể tiếp tục implicit commit.

Khi index lỗi, cột có thể vẫn tồn tại, dữ liệu backfill có thể đã commit. Migration cần kiểm tra catalog và tiếp tục từ trạng thái thực tế.

### 24.3. Oracle

ALTER TABLE gây implicit commit. Cột được thêm và DML sau đó thuộc transaction riêng; CREATE INDEX lại gây implicit commit. Lỗi index không làm cột đã tạo biến mất.

### 24.4. SQL Server

Nếu ba bước được thực thi trong transaction hỗ trợ và error handling rollback toàn transaction, có thể đưa schema và DML về trạng thái trước. Nhưng phải xét XACT_ABORT, loại DDL và loại lỗi.

### 24.5. SQLite

Các bước DDL/DML thông thường có thể nằm trong một transaction. Nếu lỗi được xử lý bằng rollback toàn transaction, thay đổi trước đó được rollback theo.

### 24.6. Bài học

**Không thể thiết kế một migration có cùng chiến lược rollback cho mọi DBMS.** Cần biết DDL có commit ngầm, transactional, hoặc có thao tác không thể chạy trong transaction.

---

## 25. Idempotency và migration ledger

Một migration runner thường lưu lịch sử migration trong bảng riêng:

```sql
CREATE TABLE schema_migrations (
    version VARCHAR(100) PRIMARY KEY,
    checksum VARCHAR(128) NOT NULL,
    applied_at TIMESTAMP NOT NULL
);
```

Sau khi migration hoàn thành theo quy tắc runner, nó ghi nhận version.

### 25.1. Không ghi migration là thành công trước khi các bước cần thiết hoàn tất

Nếu ledger ghi version trước khi DDL chạy xong, runner có thể bỏ qua migration còn dở.

### 25.2. DDL nontransactional tạo trạng thái partial

Với MySQL/Oracle, một migration có thể đã thực hiện một số DDL rồi lỗi ở bước sau. Nếu ledger không ghi success, lần chạy tiếp theo không thể mặc định database ở trạng thái ban đầu.

### 25.3. Idempotent không chỉ là thêm IF NOT EXISTS

Ví dụ:

```sql
ALTER TABLE app.orders
ADD COLUMN IF NOT EXISTS source_code TEXT;
```

có thể giúp tránh lỗi nếu cột đã tồn tại ở PostgreSQL. Nhưng nó không chứng minh cột hiện tại có đúng kiểu, nullability, default hay nội dung như migration mong đợi.

### 25.4. Check trạng thái thực tế

Trước khi chạy lại:

- Cột có tồn tại không?
- Kiểu có đúng không?
- Index có tồn tại và valid không?
- Constraint có đúng definition không?
- Backfill đã hoàn thành tới đâu?
- Migration ledger có ghi version không?
- Có writer đang ghi vào schema mới không?

### 25.5. Checksum và migration bất biến

Nhiều migration tool lưu checksum để phát hiện file migration đã bị sửa sau khi chạy. Không chỉnh sửa file cũ đã áp dụng mà không có quy trình sửa version/checksum của tool.

---

## 26. Expand–migrate–contract để triển khai schema an toàn

Một thay đổi schema production có thể được chia thành ba pha.

### Pha 1 — Expand

Thêm cấu trúc mới tương thích với ứng dụng cũ:

```sql
ALTER TABLE app.orders
ADD COLUMN source_code TEXT;
```

Tùy DBMS, DDL có thể cần online/instant/in-place hoặc lock; kiểm tra khả năng của version.

### Pha 2 — Migrate/backfill

Backfill dữ liệu cũ theo batch:

```sql
UPDATE app.orders
SET source_code = 'legacy'
WHERE source_code IS NULL;
```

Trong bảng lớn, chia batch, theo dõi progress và tránh transaction khổng lồ nếu workload không phù hợp.

### Pha 3 — Switch application

Deploy ứng dụng mới đọc/ghi cột source_code. Có thể cần giai đoạn dual-read/dual-write có kiểm soát và kiểm tra consistency.

### Pha 4 — Contract

Sau khi mọi instance cũ đã ngừng dùng cấu trúc cũ, xóa cột/index/constraint không còn cần.

```sql
ALTER TABLE app.orders
DROP COLUMN old_source;
```

Đây là thao tác destructive về schema; cần backup, xác nhận dependency và rollback plan phù hợp.

### 26.1. Vì sao không làm tất cả trong một migration?

Ứng dụng có nhiều instance chạy khác version. Nếu DROP cột cũ trước khi code mới được triển khai đồng bộ, instance cũ có thể lỗi.

### 26.2. Rollback ứng dụng khác rollback database

Có thể rollback application binary nhưng không thể khôi phục dữ liệu đã xóa hoặc schema đã contract chỉ bằng redeploy code cũ.

Cần kế hoạch tương thích ngược và phục hồi dữ liệu riêng.

---

## 27. DDL trong migration tool: transaction policy

Các framework migration thường có tùy chọn transaction ở mức migration hoặc từng statement.

Ví dụ khái niệm:

```text
Migration A:
  transactional = true
  - ALTER TABLE ...
  - UPDATE ...

Migration B:
  transactional = false
  - CREATE INDEX CONCURRENTLY ...
```

Tên cấu hình tùy tool; đây là sơ đồ ý tưởng.

### 27.1. PostgreSQL

Đánh dấu bước chứa CREATE INDEX CONCURRENTLY chạy ngoài transaction nếu migration tool yêu cầu. Những bước khác có thể transactional.

### 27.2. MySQL

Không dựa vào cờ transactional của migration runner để biến ALTER TABLE thành transactional DDL. Runner có thể mở transaction nhưng server vẫn implicit commit.

### 27.3. Oracle

Tách DDL khỏi DML cần rollback. Migration runner không thể ép DDL thông thường tuân theo rollback DML.

### 27.4. SQL Server/SQLite

Có thể tận dụng transactional DDL trong phạm vi hỗ trợ, nhưng vẫn phải xét câu lệnh đặc biệt và lỗi làm transaction không commit được.

### 27.5. Runner và database phải cùng một hợp đồng

Migration tool có thể ghi ledger trong transaction riêng, dùng advisory lock hoặc metadata lock. Cần đọc tài liệu tool và DBMS cùng nhau; không giả định runner tự giải quyết partial state.

---

## 28. DDL và autocommit trong JDBC

Ví dụ Java:

```java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try (Statement st = connection.createStatement()) {
        st.execute("""
            CREATE TABLE app.migration_demo (
                id BIGINT PRIMARY KEY
            )
            """);

        connection.commit();
    } catch (SQLException ex) {
        connection.rollback();
        throw ex;
    }
}
```

### 28.1. PostgreSQL

DDL thông thường hỗ trợ transaction có thể rollback. Nhưng một số lệnh không được phép trong transaction block; JDBC setAutoCommit(false) không thay đổi giới hạn server.

### 28.2. MySQL/Oracle

DDL implicit commit có thể commit transaction đang mở. Gọi rollback trong catch không thể đảo DML đã được commit trước DDL.

### 28.3. SQL Server

DDL thường transactional nhưng lỗi có thể khiến transaction không commit được; kiểm tra transaction state và XACT_ABORT.

### 28.4. SQLite

DDL thông thường có thể rollback trong transaction; lỗi lock/constraint vẫn cần xử lý theo trạng thái transaction và driver.

### 28.5. Đừng để transaction manager bị bất ngờ

Nếu dùng Spring @Transactional, JTA hoặc ORM, không tự trộn DDL implicit commit vào workflow DML mà không hiểu cách framework nhận biết transaction đã bị DBMS commit.

---

## 29. Bảng tạm trong JDBC: dùng cùng connection

Một lỗi phổ biến:

1. Connection A tạo temporary table.
2. Ứng dụng đóng A.
3. Ứng dụng mở connection B.
4. Query bảng tạm trên B.
5. Database báo không tồn tại.

Temporary table thường gắn với session/connection, nên connection B là session khác.

### 29.1. Đúng: giữ cùng connection

```java
try (Connection connection = dataSource.getConnection()) {
    try (Statement st = connection.createStatement()) {
        st.execute("""
            CREATE TEMP TABLE temp_ids (
                id BIGINT PRIMARY KEY
            )
            """);
    }

    try (PreparedStatement ps = connection.prepareStatement(
            "INSERT INTO temp_ids(id) VALUES (?)")) {
        ps.setLong(1, 10L);
        ps.executeUpdate();
    }

    try (Statement st = connection.createStatement();
         ResultSet rs = st.executeQuery(
             "SELECT id FROM temp_ids")) {
        while (rs.next()) {
            System.out.println(rs.getLong(1));
        }
    }
}
```

Cú pháp CREATE TEMP TABLE ở đây phù hợp với PostgreSQL/SQLite/MySQL theo dialect gần nhau, nhưng tên kiểu và DDL cần điều chỉnh cho SQL Server/Oracle.

### 29.2. Nếu repository tự lấy connection riêng

Một method createTempTable dùng connection riêng và method queryTempTable lại lấy connection mới sẽ không thấy cùng temporary table.

Nếu cần nhiều repository method cùng dùng temp table, truyền cùng transaction-bound connection qua framework hoặc dùng API quản lý transaction đúng cách.

### 29.3. ORM có thể đổi connection

Nếu connection release mode hoặc transaction boundary của ORM thay đổi, bảng tạm có thể biến mất khỏi ngữ cảnh query. Test với cấu hình pool/ORM production.

---

## 30. Bảng tạm và dữ liệu lớn: index, statistics, cleanup

Temporary table không miễn phí.

### 30.1. Index

Nếu bảng tạm có hàng triệu ID và JOIN nhiều lần, index có thể hữu ích. Nếu chỉ chứa vài chục hàng dùng một lần, chi phí xây index có thể lớn hơn lợi ích.

### 30.2. Statistics

Optimizer có thể cần thống kê để chọn plan. Cơ chế thu thập/độ mới của statistics trên temporary table khác nhau theo DBMS.

### 30.3. Cleanup

- DROP khi không còn dùng.
- DELETE/TRUNCATE dữ liệu theo đúng semantics DBMS.
- Không giữ session có temp table lớn trong pool lâu không cần thiết.
- Theo dõi tempdb/temp tablespace/temp files và quota.
- Kiểm tra transaction mở giữ dữ liệu/lock lâu.

### 30.4. Không dùng temp table để né thiết kế dữ liệu bền vững

Nếu nhiều worker cần chia sẻ job state, một permanent staging table có job_id, tenant_id, status, created_at và cleanup policy có thể phù hợp hơn.

---

## 31. Bảng tạm có phải dữ liệu riêng tư không?

Temporary table thường cô lập theo session, nhưng không nên tự động coi nó là nơi chứa bí mật an toàn.

Cần xét:

- Quyền đọc tempdb/temp tablespace.
- Log, WAL/redo/transaction log.
- Backup và crash recovery.
- Temp files có thể được ghi xuống disk.
- Session reuse qua pool.
- SQL logging và tracing.
- User/role có thể tạo object cùng tên.
- Quyền truy cập qua routine/view.

Nếu dữ liệu nhạy cảm, áp dụng policy, masking, retention và encryption phù hợp. TEMP không đồng nghĩa “không bao giờ ghi ra disk” hoặc “không thể bị lộ”.

---

## 32. TRUNCATE, DELETE và DROP: khác nhau trong failure handling

Ba lệnh thường bị nhầm:

| Lệnh | Tác động | Có thể rollback? |
| --- | --- | --- |
| DELETE FROM table | Xóa hàng theo điều kiện | Phụ thuộc DBMS/engine/transaction |
| TRUNCATE TABLE | Làm rỗng bảng theo semantics DBMS | Khác nhau đáng kể giữa DBMS |
| DROP TABLE | Xóa đối tượng bảng | Transactional ở một số DBMS, implicit commit ở DBMS khác |

### 32.1. PostgreSQL

DELETE, TRUNCATE và DROP TABLE thông thường có thể tham gia transaction và rollback.

### 32.2. MySQL

DELETE trên InnoDB có thể rollback. TRUNCATE và DROP TABLE thường là DDL gây implicit commit và không rollback như DML.

### 32.3. SQL Server

DELETE, TRUNCATE TABLE và DROP TABLE có thể tham gia transaction trong các trường hợp thông thường; quyền, foreign key, replication và loại bảng có thể giới hạn.

### 32.4. Oracle

DELETE có thể rollback trước COMMIT. TRUNCATE và DROP TABLE là DDL với implicit commit; không rollback bằng ROLLBACK thông thường.

### 32.5. SQLite

DELETE và các thao tác schema/table hỗ trợ transaction có thể rollback. Kiểm tra từng câu lệnh và journal mode/locking.

**Không thay DELETE bằng TRUNCATE để “cho nhanh” nếu quy trình cần rollback.**

---

## 33. DDL lỗi và trạng thái connection

Sau một SQLException, connection có thể:

- Vẫn ở transaction hoạt động.
- Ở trạng thái transaction aborted/doomed.
- Đã bị implicit commit.
- Bị đóng hoặc mất kết nối.
- Không chắc server đã commit hay client chỉ mất phản hồi.

### 33.1. PostgreSQL transaction aborted

Sau một statement lỗi trong transaction PostgreSQL, các statement tiếp theo thường báo lỗi cho đến khi ROLLBACK hoặc rollback về savepoint.

```sql
BEGIN;

SELECT 1 / 0;

SELECT 2; -- Transaction vẫn ở trạng thái aborted

ROLLBACK;
```

### 33.2. SQL Server transaction state

Dùng XACT_STATE() và @@TRANCOUNT để hiểu transaction còn tồn tại và có thể commit không.

### 33.3. MySQL/Oracle implicit commit

Sau DDL, transaction trước đó có thể đã commit. Không thể dùng connection.rollback để đảo ngược phần đã commit.

### 33.4. Mất kết nối khi COMMIT

Nếu client gửi COMMIT rồi connection mất trước khi nhận phản hồi, trạng thái có thể không rõ với ứng dụng: server có thể đã commit nhưng response bị mất.

Đây là lý do migration/data operation quan trọng cần idempotency, ledger và kiểm tra trạng thái server sau reconnect.

---

## 34. Xây recovery plan sau migration thất bại

Một quy trình recovery có thể gồm:

### Bước 1 — Dừng migration runner

Không để một job retry tự động tiếp tục chạy khi chưa biết trạng thái schema.

### Bước 2 — Ghi nhận database và version

- DBMS/version.
- Schema/database hiện tại.
- Migration version và checksum.
- Connection/session settings.
- Thông báo lỗi và SQLState/vendor code.

### Bước 3 — Kiểm tra trạng thái thực tế

Xem catalog/schema:

- Bảng/cột có tồn tại?
- Index valid/usable không?
- Constraint có được tạo không?
- Temporary table có còn trong session không?
- Backfill đã hoàn tất tới đâu?
- Ledger đã ghi nhận migration chưa?

### Bước 4 — Xác định commit boundary

Phân tích lệnh nào đã implicit commit, lệnh nào transactional, lệnh nào autocommit và lệnh nào đã được runner ghi ledger.

### Bước 5 — Chọn resume, repair hoặc rollback

- **Resume:** trạng thái đã đúng một phần và bước tiếp theo an toàn.
- **Repair:** sửa trạng thái lệch bằng migration mới có kiểm soát.
- **Rollback:** chỉ khi DBMS và dữ liệu cho phép rollback thực sự.
- **Restore:** khi dữ liệu/schema không thể phục hồi bằng migration bù.

### Bước 6 — Kiểm tra dữ liệu và ứng dụng

Đảm bảo code đang chạy tương thích schema thực tế. Không deploy binary kỳ vọng cột/index chưa tồn tại.

### Bước 7 — Ghi nhận kết quả

Migration ledger, audit và incident record phải phản ánh trạng thái cuối, không đánh dấu thành công khi chỉ một phần đã chạy.

---

## 35. Compensating migration: sửa bằng thay đổi mới

Với DDL không rollbackable, thường cần **compensating migration** thay vì ROLLBACK.

Ví dụ MySQL/Oracle đã thêm cột:

```sql
ALTER TABLE app.orders
ADD COLUMN source_code VARCHAR(50);
```

Nếu quyết định hủy thay đổi, một migration mới có thể:

```sql
ALTER TABLE app.orders
DROP COLUMN source_code;
```

Nhưng chỉ được làm khi:

- Cột chưa chứa dữ liệu cần giữ.
- Ứng dụng không còn đọc/ghi cột.
- Không có view/index/trigger/constraint phụ thuộc.
- Backup và rollback plan phù hợp.

### 35.1. Không phải mọi thay đổi đều có phép nghịch đảo

Nếu migration đã chuẩn hóa dữ liệu, xóa cột cũ hoặc merge nhiều hàng, thao tác ngược có thể không khôi phục dữ liệu ban đầu.

### 35.2. Lưu dữ liệu trước destructive DDL

Trước khi DROP/ALTER destructive, cân nhắc snapshot/export, backup có thể restore và kiểm tra khả năng phục hồi.

### 35.3. Roll forward thường an toàn hơn

Trong production, một migration sửa lỗi mới có thể rõ ràng hơn việc cố sửa migration cũ đã chạy một phần. Tuy nhiên chọn cách nào phải dựa trên trạng thái thực tế và khả năng tương thích.

---

## 36. DDL online và giảm thời gian gián đoạn

Một số DBMS có lựa chọn online/concurrent/in-place để giảm block.

Ví dụ PostgreSQL:

```sql
CREATE INDEX CONCURRENTLY orders_created_at_idx
ON app.orders(created_at);
```

MySQL có algorithm/lock options cho một số ALTER TABLE:

```sql
ALTER TABLE app.orders
ADD INDEX orders_created_at_idx(created_at),
ALGORITHM=INPLACE,
LOCK=NONE;
```

Khả năng và điều kiện tùy phiên bản, storage engine, loại thay đổi và cấu trúc bảng. SQL Server có online index operations theo edition/version/loại index; Oracle có nhiều lựa chọn online DDL; SQLite có giới hạn khác.

### 36.1. Online không có nghĩa không lock

Ngay cả operation online cũng có thể cần lock ngắn ở đầu/cuối, metadata lock, tài nguyên tạm hoặc gây tăng I/O/CPU.

### 36.2. Concurrent không có nghĩa transactional

CREATE INDEX CONCURRENTLY PostgreSQL không chạy trong transaction block. Đừng nhầm chữ CONCURRENTLY với “có thể rollback”.

### 36.3. Kiểm tra trước khi chạy

- Phiên bản/edition.
- Loại bảng/index.
- Disk headroom.
- Thời gian build.
- Lock timeout.
- Replica lag.
- WAL/binlog/redo volume.
- Kế hoạch dọn index invalid/failed.
- Cửa sổ triển khai và rollback.

---

## 37. Temp table hay CTE hay permanent staging table?

| Tiêu chí | CTE | Temporary table | Permanent staging |
| --- | --- | --- | --- |
| Phạm vi | Một statement | Session/connection/transaction theo DBMS | Nhiều session/job |
| Lưu dữ liệu trung gian | Trong query execution, optimizer quyết định | Có object riêng | Có object bền vững |
| Tái sử dụng qua nhiều statement | Không trực tiếp | Có | Có |
| Index riêng | Thường không theo cách bảng | Có thể | Có |
| Chia sẻ worker | Không | Thường không (trừ global temp đặc biệt) | Có, với khóa/job scope |
| Cleanup | Hết statement | Hết scope/session hoặc explicit | Cần job/retention |
| Quản lý quyền | Quyền query/object nguồn | Quyền temp/DBMS | Quyền bảng và tenant/job |
| Phù hợp | Query nhiều bước ngắn | Dữ liệu trung gian theo session | Import/export, workflow dài, nhiều worker |

### 37.1. Chọn CTE khi

- Logic chỉ dùng trong một câu query.
- Muốn chia query thành các bước dễ đọc.
- Không cần tái sử dụng kết quả qua nhiều statement.

### 37.2. Chọn temporary table khi

- Cần giữ tập trung gian qua nhiều câu lệnh.
- Dữ liệu thuộc session/connection.
- Cần index hoặc cập nhật tập trung gian.
- Có thể giữ đúng connection và cleanup.

### 37.3. Chọn permanent staging khi

- Nhiều worker cần thấy cùng dữ liệu.
- Job chạy dài hoặc cần resume sau process restart.
- Cần audit/progress/retry.
- Connection có thể đổi giữa các bước.
- Cần phân quyền, retention và cleanup theo job.

---

## 38. Checklist thiết kế migration DDL đa hệ quản trị

Trước khi triển khai, hãy trả lời:

1. DBMS và phiên bản chính xác là gì?
2. Storage engine nào đang dùng?
3. Câu lệnh có transactional không?
4. Có implicit commit trước/sau không?
5. Atomic DDL có được hỗ trợ không?
6. Câu lệnh có bị cấm trong transaction block không?
7. Autocommit của JDBC/framework đang ở trạng thái nào?
8. Transaction manager có biết DBMS implicit commit không?
9. DDL cần loại lock nào?
10. Có online/concurrent option không?
11. Có nguy cơ rewrite bảng hoặc build index lâu không?
12. Migration có thể chạy lại không?
13. Nếu thất bại ở bước N, trạng thái schema là gì?
14. Migration ledger ghi version vào lúc nào?
15. Có checksum và lock migration không?
16. Có kế hoạch resume/repair/compensate không?
17. Có backup và kiểm tra restore không?
18. Ứng dụng cũ có tương thích schema expand không?
19. Temporary table gắn session hay transaction?
20. Connection pool có giữ lại temporary table không?
21. COMMIT/ROLLBACK ảnh hưởng definition và data riêng thế nào?
22. Có negative test sau khi cố tình tạo lỗi không?

---

## 39. Bài tập thực hành có lời giải

Các bài tập dùng PostgreSQL làm chính, sau đó suy luận khác biệt theo DBMS. Thực hành trên database riêng; không thử migration gây implicit commit trên dữ liệu thật.

### Bài 1. Transactional DDL PostgreSQL

```sql
BEGIN;
CREATE TABLE ddl_practice(id INTEGER);
ROLLBACK;
```

**Đáp án:** Với CREATE TABLE thông thường trong PostgreSQL, bảng được rollback và không còn tồn tại.

### Bài 2. ALTER TABLE PostgreSQL trong transaction

```sql
BEGIN;
ALTER TABLE demo_accounts ADD COLUMN marker TEXT;
ROLLBACK;
```

**Đáp án:** Cột marker không còn được thêm bởi transaction này.

### Bài 3. CREATE INDEX CONCURRENTLY có chạy trong transaction block không?

**Đáp án:** Không. PostgreSQL cấm lệnh này trong transaction block. Tách bước migration và kiểm tra trạng thái index nếu lỗi.

### Bài 4. MySQL UPDATE rồi ALTER TABLE rồi ROLLBACK

**Đáp án:** ALTER TABLE thuộc nhóm implicit commit; UPDATE trước đó có thể đã được commit trước DDL. ROLLBACK sau không khôi phục UPDATE.

### Bài 5. Atomic DDL có đồng nghĩa rollback được không?

**Đáp án:** Không. Atomic DDL bảo vệ tính nguyên tử của thao tác DDL khi lỗi/crash theo phạm vi hỗ trợ; transactional DDL mới nói về rollback trong transaction của người dùng.

### Bài 6. Oracle UPDATE rồi CREATE TABLE rồi ROLLBACK

**Đáp án:** DDL commit transaction hiện tại trước khi thực thi; UPDATE có thể đã được commit. CREATE TABLE thành công cũng được commit theo quy tắc Oracle; ROLLBACK sau không đảo chúng.

### Bài 7. SQL Server CREATE TABLE trong transaction

**Đáp án:** CREATE TABLE thông thường có thể tham gia transaction và rollback, nhưng phải xét các lệnh đặc biệt/giới hạn và trạng thái transaction sau lỗi.

### Bài 8. SQLite CREATE TABLE rồi ROLLBACK

**Đáp án:** CREATE TABLE thông thường có thể rollback trong transaction SQLite.

### Bài 9. PostgreSQL ON COMMIT DELETE ROWS

```sql
CREATE TEMP TABLE t(id INT) ON COMMIT DELETE ROWS;
INSERT INTO t VALUES (1);
COMMIT;
```

**Đáp án:** Bảng tạm vẫn tồn tại trong session nhưng hàng bị xóa khi commit.

### Bài 10. PostgreSQL ON COMMIT DROP

**Đáp án:** Bảng tạm bị drop sau COMMIT của transaction chứa thao tác tạo/đang dùng theo cấu hình. Không còn bảng để query trong session sau commit.

### Bài 11. PostgreSQL mặc định ON COMMIT

**Đáp án:** PRESERVE ROWS; hàng được giữ qua COMMIT cho tới khi session kết thúc hoặc bảng bị drop/truncate.

### Bài 12. MySQL temporary table sau ROLLBACK CREATE

**Đáp án:** CREATE TEMPORARY TABLE không gây implicit commit như DDL thường, nhưng bản thân CREATE TEMPORARY TABLE không rollback được; kiểm tra bảng trong cùng session.

### Bài 13. MySQL temporary table có tồn tại ở connection khác không?

**Đáp án:** Không. Nó thuộc session tạo ra.

### Bài 14. SQL Server #temp và ##temp khác nhau thế nào?

**Đáp án:** #temp là local temporary table, thường chỉ session/scope tương ứng thấy; ##temp là global temporary table có thể được nhiều session nhìn thấy theo lifecycle rules.

### Bài 15. Oracle GTT ON COMMIT PRESERVE ROWS

**Đáp án:** Định nghĩa bảng tồn tại trong database; dữ liệu riêng session được giữ qua COMMIT cho tới khi session kết thúc hoặc xóa.

### Bài 16. “Global” trong Global Temporary Table có nghĩa gì?

**Đáp án:** Định nghĩa bảng được tạo ở mức database, còn dữ liệu vẫn được cô lập theo session/transaction; không có nghĩa mọi session đọc cùng hàng.

### Bài 17. SQLite TEMP table có chia sẻ giữa connection không?

**Đáp án:** Không. Nó gắn với connection tạo bảng.

### Bài 18. Connection.close với pool có drop temp table không?

**Đáp án:** Không được giả định. Logical close thường trả connection về pool; physical session có thể còn và temp table tồn tại. Cleanup/reset phải rõ.

### Bài 19. CTE hay temp table?

**Đáp án:** CTE phù hợp logic trong một statement; temp table phù hợp dữ liệu trung gian cần tái sử dụng qua nhiều statement trong cùng scope.

### Bài 20. Khi nào dùng permanent staging?

**Đáp án:** Khi nhiều worker/session cần chia sẻ, job cần resume/audit hoặc connection có thể thay đổi giữa các bước.

### Bài 21. Migration MySQL lỗi ở bước cuối

**Đáp án:** Không chạy lại mù quáng. Kiểm tra cột, dữ liệu backfill, index, ledger và xác định implicit commits đã xảy ra tới đâu; chọn resume hoặc compensating migration.

### Bài 22. PostgreSQL transaction lỗi ở giữa DDL

**Đáp án:** Transaction có thể ở trạng thái aborted; cần ROLLBACK hoặc rollback tới savepoint trước khi tiếp tục.

### Bài 23. SQL Server XACT_STATE = -1

**Đáp án:** Transaction đang hoạt động nhưng không thể commit; cần rollback toàn transaction.

### Bài 24. SAVEPOINT có thể rollback qua Oracle DDL không?

**Đáp án:** Không. DDL implicit commit làm savepoint trước đó mất hiệu lực.

### Bài 25. DELETE và TRUNCATE khác gì về recovery?

**Đáp án:** Semantics và khả năng rollback khác theo DBMS. PostgreSQL/SQL Server/SQLite có thể rollback trong các trường hợp thông thường; MySQL TRUNCATE và Oracle TRUNCATE là DDL có implicit commit.

### Bài 26. CREATE INDEX CONCURRENTLY lỗi ở PostgreSQL

**Đáp án:** Kiểm tra catalog và trạng thái index. Có thể còn index INVALID; không chỉ retry y nguyên mà không kiểm tra.

### Bài 27. Atomic DDL MySQL 8.0 bảo vệ điều gì?

**Đáp án:** Tính nguyên tử/crash safety của những DDL được hỗ trợ qua dictionary/storage, không biến chúng thành câu lệnh rollbackable trong transaction người dùng.

### Bài 28. Temporary table chứa dữ liệu nhạy cảm có luôn ở RAM không?

**Đáp án:** Không. Tùy DBMS, temp store, kích thước, engine và cấu hình; dữ liệu có thể chạm disk, log hoặc temporary tablespace.

### Bài 29. Vì sao không tạo temp table trong một repository method rồi query ở method lấy connection mới?

**Đáp án:** Temporary table thường thuộc session/connection; method thứ hai có thể lấy session khác và không nhìn thấy bảng.

### Bài 30. Khi client mất kết nối ngay sau COMMIT

**Đáp án:** Trạng thái commit có thể không rõ đối với client. Reconnect và kiểm tra dữ liệu/ledger bằng operation ID hoặc migration version; thiết kế idempotency thay vì mù quáng lặp thao tác.

---

## 40. Tổng kết

DDL, transaction và temporary table là ba chủ đề liên quan nhưng không thể suy luận thay cho nhau.

- PostgreSQL cho phép nhiều DDL thông thường rollback trong transaction, nhưng có lệnh bị cấm trong transaction block như CREATE INDEX CONCURRENTLY.
- MySQL có nhiều DDL implicit commit. Atomic DDL không đồng nghĩa transactional DDL; CREATE/DROP TEMPORARY TABLE có quy tắc đặc biệt.
- SQL Server hỗ trợ transaction cho nhiều DDL thông thường, nhưng lỗi có thể làm transaction không commit được; XACT_STATE giúp xác định trạng thái.
- Oracle DDL thường commit trước và sau thao tác thành công, nên ROLLBACK không đảo DDL hoặc DML đã bị commit trước đó.
- SQLite hỗ trợ transaction cho nhiều thao tác DDL thông thường, nhưng PRAGMA và lệnh đặc biệt có thể có quy tắc riêng.
- Temporary table có vòng đời và phạm vi khác nhau: session, connection, transaction hoặc scope thủ tục; phải phân biệt definition với data lifetime.
- Connection pool có thể tái sử dụng physical session, nên temp table và session state có thể còn sau logical close.
- Khi migration lỗi, phải kiểm tra trạng thái thực tế, implicit commit boundary, ledger, object catalog và dữ liệu trước khi resume/repair.
- Atomic DDL, transactional DDL, autocommit và crash recovery là những cam kết khác nhau.
- Expand–migrate–contract, migration idempotent và compensating migration giúp triển khai schema an toàn hơn.

**Kết luận:** Trước khi viết migration hoặc dùng bảng tạm, hãy xác định rõ **DBMS/version, transaction boundary, implicit commit, rollback behavior, definition/data lifetime và connection scope**. Khi DDL thất bại, đừng giả định database quay về trạng thái trước đó; hãy kiểm tra trạng thái thực tế và phục hồi theo đúng semantics của engine. Đây là điều giúp migration có thể dự đoán, vận hành an toàn và tránh dữ liệu hoặc schema bị thay đổi một phần ngoài ý muốn.
