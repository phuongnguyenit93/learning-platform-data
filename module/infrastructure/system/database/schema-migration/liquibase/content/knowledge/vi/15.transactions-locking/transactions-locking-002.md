# DDL có giao dịch và DDL tự commit theo từng hệ quản trị

Một migration có thể tạo bảng thành công rồi thất bại khi thêm ràng buộc. Trong môi trường này, bảng mới biến mất sau khi rollback; trong môi trường khác, bảng vẫn tồn tại và lần chạy Liquibase tiếp theo báo lỗi **table already exists**. Sự khác biệt thường không nằm ở cấu trúc changeset, mà ở **khả năng giao dịch của DDL trên từng hệ quản trị cơ sở dữ liệu (DBMS)**.

Bài học thuộc chương **Giao dịch và khóa** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Phạm vi module là nắm cách quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD.

Trọng tâm của bài là **DDL có thể được rollback trong transaction**, **DDL tự commit/implicit commit** và cách hai loại hành vi đó tác động tới Liquibase khi chạy nhiều changeset, gặp lỗi, rollback hoặc triển khai đồng thời.

Sau bài học, bạn sẽ có thể:

1. Phân biệt transaction, autocommit, implicit commit, atomic DDL và rollback có chủ đích.
2. So sánh hành vi thường gặp của PostgreSQL, MySQL/MariaDB, Oracle, SQL Server và SQLite.
3. Giải thích phạm vi của **runInTransaction** và tại sao nó không thể “ép” một DBMS hỗ trợ transactional DDL.
4. Phân tích hậu quả khi một changeset có nhiều lệnh DDL/DML chạy dở dang.
5. Xây dựng migration ít rủi ro, tách bước hợp lý và kiểm tra trạng thái thực tế sau sự cố.
6. Hiểu quan hệ giữa transaction của changeset, khóa DDL của DBMS và **DATABASECHANGELOGLOCK** của Liquibase.
7. Thiết kế cách xác minh trước/sau update và phương án rollback hoặc forward fix trên từng DBMS.

## 1. DDL là gì và vì sao tính giao dịch quan trọng?

**DDL (Data Definition Language)** là nhóm lệnh định nghĩa hoặc thay đổi đối tượng database, ví dụ:

~~~sql
CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    email VARCHAR(255)
);

ALTER TABLE customer
ADD COLUMN status VARCHAR(24);

CREATE INDEX idx_customer_email
ON customer (email);

DROP TABLE customer;
~~~

Ngược lại, **DML (Data Manipulation Language)** như INSERT, UPDATE và DELETE thao tác với hàng dữ liệu.

Một **transaction** là đơn vị công việc mà hệ quản trị có thể commit hoặc rollback theo khả năng hỗ trợ. Khi câu lệnh nằm trong transaction được DBMS hỗ trợ, ROLLBACK có thể đảo lại các thay đổi **chưa commit** trong phạm vi đó.

Đối với migration, tính giao dịch đặc biệt quan trọng ở câu hỏi:

> Nếu câu lệnh thứ hai trong changeset lỗi, câu lệnh đầu tiên có được hoàn nguyên tự động hay đã trở thành một phần của schema?

Không thể trả lời bằng cách chỉ nhìn **runInTransaction:true**. Cần biết DBMS, loại DDL, driver và cách Liquibase thực thi.

## 2. Phân biệt năm khái niệm dễ nhầm

| Khái niệm | Ý nghĩa | Không được hiểu nhầm |
|---|---|---|
| **Transaction** | Phạm vi các thay đổi mà DBMS quản lý qua COMMIT/ROLLBACK | Không đồng nghĩa mọi DDL đều nằm trong transaction |
| **Autocommit của kết nối** | Chế độ kết nối tự commit theo từng lệnh/cơ chế driver | Không giải thích hết implicit commit do chính DDL gây ra |
| **Implicit commit của DDL** | DBMS tự kết thúc/commit transaction khi chạy loại DDL nhất định | Không thể vô hiệu hóa chỉ bằng cấu hình Liquibase |
| **Atomic DDL** | Tính nguyên tử của một thao tác DDL theo nghĩa DBMS hỗ trợ, có thể bao gồm bảo vệ khi crash | Không nhất thiết cho phép người dùng ROLLBACK DDL đã thành công |
| **Rollback của Liquibase** | Một thao tác migration chủ đích dùng thay đổi đảo ngược | Khác với ROLLBACK của transaction đang mở |

**Ví dụ quan trọng:** MySQL 8 có cơ chế **atomic DDL** cho những thao tác và storage engine được hỗ trợ, nhằm quản lý tính nhất quán của thao tác DDL kể cả khi gặp sự cố. Điều này **không có nghĩa** người dùng có thể bao CREATE TABLE trong BEGIN rồi dùng ROLLBACK để xóa bảng vừa tạo. Nhiều DDL MySQL vẫn gây implicit commit.

### 2.1. Hai nghĩa khác nhau của “rollback”

**Transaction rollback:**

~~~sql
BEGIN;
INSERT INTO audit_note (id, note_text) VALUES (1, 'temporary');
ROLLBACK;
~~~

Nếu DBMS hỗ trợ giao dịch cho thao tác này, INSERT chưa commit sẽ được hoàn nguyên.

**Liquibase rollback changeset:**

~~~yaml
rollback:
  - dropTable:
      tableName: audit_note
~~~

Đây là **thao tác ngược do người viết khai báo hoặc do Liquibase hỗ trợ tạo**, cần được thực thi riêng. Nó không phải bằng chứng database có khả năng undo CREATE TABLE bằng transaction.

Nếu bảng đã nhận dữ liệu sau migration, một rollback bằng DROP TABLE có thể gây mất dữ liệu, dù trước đó CREATE TABLE được áp dụng thành công.

## 3. Mô hình giao dịch của một changeset Liquibase

Theo cách sử dụng thông thường, Liquibase cố thực thi **mỗi changeset trong transaction** nếu DBMS hỗ trợ. Thuộc tính **runInTransaction** của changeset cho phép điều chỉnh hành vi đó; mặc định phổ biến là **true**.

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-001"
      author: "db-team"
      runInTransaction: true
      changes:
        - createTable:
            tableName: audit_event
            columns:
              - column:
                  name: id
                  type: bigint
                  constraints:
                    primaryKey: true
~~~

Điểm cần hiểu:

- **runInTransaction:true** là yêu cầu cách Liquibase quản lý transaction cho changeset khi được hỗ trợ.
- DBMS **quyết định** DDL có thể được rollback trong transaction hay không.
- Một changelog có nhiều changeset không mặc nhiên là **một transaction duy nhất** bao trùm toàn bộ update.
- Changeset đã commit thành công trước khi changeset sau gặp lỗi thường **không tự rollback hàng loạt**.
- Một changeset có **nhiều statement** trên DBMS tự commit có thể làm database thay đổi một phần nếu lệnh sau thất bại.

Đây là sự khác biệt giữa tính nguyên tử ở mức **statement**, **changeset** và **toàn bộ đợt triển khai**.

### 3.1. Luồng điển hình

~~~mermaid
flowchart TD
    A[Liquibase update] --> B[Đọc changeset và kiểm tra lịch sử]
    B --> C{Changeset cần thực thi?}
    C -->|Không| J[Bỏ qua hoặc xử lý theo cơ chế khác]
    C -->|Có| D[Thiết lập transaction nếu được hỗ trợ]
    D --> E[Thực thi DDL hoặc DML]
    E --> F{Thành công?}
    F -->|Có| G[Commit/ghi nhận thay đổi theo cơ chế DBMS]
    G --> H[Ghi lịch sử DATABASECHANGELOG theo cơ chế Liquibase]
    F -->|Không| I[Rollback được phần chưa commit nếu DBMS hỗ trợ]
    I --> K[Kiểm tra schema và lịch sử thực tế]
~~~

Sơ đồ đơn giản hóa quy trình: chi tiết ghi lịch sử, commit, transaction boundary và xử lý lỗi phụ thuộc DBMS và phiên bản Liquibase. Không nên suy ra các bước trên luôn là một transaction duy nhất trong mọi môi trường.

## 4. Bảng so sánh hành vi DDL theo hệ quản trị

| DBMS | Hành vi thường gặp | Giới hạn cần nhớ |
|---|---|---|
| **PostgreSQL** | Nhiều DDL thông dụng có thể rollback khi chạy trong transaction | Một số thao tác phải nằm ngoài transaction block, ví dụ CREATE INDEX CONCURRENTLY, CREATE DATABASE |
| **MySQL (InnoDB)** | Nhiều DDL như CREATE/ALTER/DROP TABLE gây implicit commit | Atomic DDL ở các phiên bản hỗ trợ không tương đương transaction rollback do người dùng yêu cầu |
| **MariaDB** | Nhiều DDL gây implicit commit, có khác biệt theo phiên bản/cơ chế | Tính nhất quán khi crash của từng thao tác không đồng nghĩa DDL có thể ROLLBACK |
| **Oracle Database** | DDL thường gây implicit commit trước/sau thao tác | ROLLBACK sau CREATE/ALTER thông thường không hoàn nguyên đối tượng vừa thay đổi |
| **Microsoft SQL Server** | Nhiều DDL có thể tham gia explicit transaction | Có ngoại lệ và giới hạn theo loại DDL, chế độ database hoặc thao tác hệ thống |
| **SQLite** | DDL thông thường có thể rollback trong explicit transaction | ALTER TABLE và cơ chế đổi schema có giới hạn; driver/công cụ có thể ảnh hưởng |
| **H2, DB2, DBMS khác** | Cần xác nhận theo loại lệnh và phiên bản cụ thể | Không suy luận từ PostgreSQL hoặc từ việc Liquibase validate thành công |

**Đây là bảng định hướng, không phải cam kết cho mọi lệnh DDL.** Đơn vị kiểm tra đúng là tổ hợp **DBMS + phiên bản + loại DDL + executor/driver + cấu hình Liquibase**.

### 4.1. Vì sao không xếp một DBMS vào nhóm “có” hoặc “không” tuyệt đối?

Ngay với DBMS hỗ trợ transactional DDL rộng rãi, có thao tác yêu cầu **không chạy trong transaction** hoặc có behavior đặc biệt. Ngược lại, một số lệnh DDL trên DBMS tự commit có tính nguyên tử ở mức statement, nhưng không thể hoàn nguyên sau khi statement kết thúc.

Đội migration phải xem **chính lệnh dự định chạy**, không chỉ gắn nhãn DBMS là “transactional” hoặc “nontransactional”.

## 5. PostgreSQL: nhiều DDL có thể rollback trong transaction

PostgreSQL hỗ trợ transaction cho nhiều thao tác schema phổ biến, ví dụ CREATE TABLE, ALTER TABLE và DROP TABLE.

Trên **database thử nghiệm**, có thể chạy:

~~~sql
BEGIN;

CREATE TABLE public.tx_ddl_probe (
    id BIGINT PRIMARY KEY
);

ROLLBACK;
~~~

Sau khi ROLLBACK, bảng **tx_ddl_probe** thường không còn tồn tại vì CREATE TABLE chưa commit.

Kiểm tra bằng truy vấn chỉ đọc:

~~~sql
SELECT to_regclass('public.tx_ddl_probe') AS existing_table;
~~~

Kết quả **NULL** cho biết không tìm thấy đối tượng theo tên được truy vấn.

### 5.1. Một changeset có nhiều DDL trên PostgreSQL

Ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-002"
      author: "orders-team"
      dbms: postgresql
      runInTransaction: true
      changes:
        - createTable:
            tableName: shipping_event
            schemaName: public
            columns:
              - column:
                  name: id
                  type: bigint
                  constraints:
                    primaryKey: true
        - createIndex:
            tableName: shipping_event
            schemaName: public
            indexName: idx_shipping_event_id
            columns:
              - column:
                  name: id
~~~

Giả sử CREATE INDEX thất bại và cả changeset nằm trong một transaction PostgreSQL hợp lệ, thay đổi CREATE TABLE chưa commit cũng có thể được rollback. Tuy nhiên, có thể tránh tạo index dư thừa trên cột khóa chính; ví dụ này nhằm minh họa transaction, không phải đề xuất thiết kế index.

Trong thực tế, Liquibase thường **commit từng changeset**, không bao trùm toàn changelog. Nếu changeset tạo bảng thành công và commit, nhưng một changeset độc lập ở sau thất bại, bảng từ changeset trước vẫn tồn tại.

### 5.2. Transactional DDL vẫn có thể khóa mạnh

**Có thể rollback** không có nghĩa **không gây ảnh hưởng khi chạy**. Chẳng hạn ALTER TABLE có thể cần lock mạnh và giữ lock cho đến khi transaction kết thúc. Một changeset kéo dài có thể làm chặn query hoặc DML của ứng dụng.

Vì vậy, với bảng lớn, cần đánh giá:

- Loại lock mà câu DDL yêu cầu.
- Thời gian nắm giữ lock.
- Số lượng phiên làm việc đang truy cập bảng.
- Thời gian chạy backfill và index.
- Khả năng chờ lock lâu hoặc gây timeout.

## 6. PostgreSQL: ngoại lệ CREATE INDEX CONCURRENTLY

**CREATE INDEX CONCURRENTLY** được thiết kế nhằm giảm mức độ chặn ghi của thao tác xây index, nhưng PostgreSQL **không cho chạy trong transaction block**.

Ví dụ SQL:

~~~sql
CREATE INDEX CONCURRENTLY idx_orders_created_at
ON public.orders (created_at);
~~~

Nếu đưa vào một changeset được Liquibase bao bằng transaction, có thể gặp lỗi tương tự “CREATE INDEX CONCURRENTLY cannot run inside a transaction block”.

Một cách tổ chức:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-003-concurrent-index"
      author: "orders-team"
      dbms: postgresql
      runInTransaction: false
      changes:
        - sql:
            splitStatements: false
            sql: |
              CREATE INDEX CONCURRENTLY idx_orders_created_at
              ON public.orders (created_at);
      rollback:
        - sql:
            sql: |
              DROP INDEX CONCURRENTLY IF EXISTS public.idx_orders_created_at;
~~~

Lưu ý kỹ:

1. **runInTransaction:false** là chủ đích, do lệnh DDL này cần nằm ngoài transaction block.
2. Chỉ đặt **một thao tác chính** trong changeset này để giảm rủi ro thành công một phần.
3. **splitStatements:false** ở đây nhằm gửi một statement nguyên vẹn; nó không thay thế yêu cầu không chạy transaction.
4. Lệnh **DROP INDEX CONCURRENTLY** cũng có giới hạn transaction; cần kiểm thử phương án rollback bằng đúng Liquibase/executor. Không mặc định rằng thuộc tính rollback luôn được bao transaction giống SQL update.
5. Nếu CREATE INDEX CONCURRENTLY bị gián đoạn, PostgreSQL có thể còn **index không hợp lệ (invalid)**. Cần kiểm tra trạng thái catalog trước khi retry.

Ví dụ truy vấn đọc trạng thái index:

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS index_name,
    i.indisvalid AS index_valid
FROM pg_catalog.pg_class c
JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
JOIN pg_catalog.pg_index i ON i.indexrelid = c.oid
WHERE n.nspname = 'public'
  AND c.relname = 'idx_orders_created_at';
~~~

Nếu index tồn tại nhưng **indisvalid = false**, phải áp dụng quy trình khắc phục phù hợp, không chỉ chạy lại nguyên changeset.

### 6.1. Những ngoại lệ khác

Một số thao tác PostgreSQL như CREATE DATABASE không được chạy trong transaction block. Hãy kiểm tra từng lệnh có yêu cầu đặc biệt về transaction hay không thay vì dùng runInTransaction:false cho toàn bộ changelog.

## 7. MySQL: implicit commit của nhiều thao tác DDL

Trong MySQL, nhiều thao tác như **CREATE TABLE**, **ALTER TABLE**, **DROP TABLE** có thể gây **implicit commit**. Hệ quả là BEGIN/START TRANSACTION không tạo ra rollback DDL như trên PostgreSQL.

Trên **database thử nghiệm**, ví dụ:

~~~sql
START TRANSACTION;

CREATE TABLE tx_ddl_probe (
    id BIGINT PRIMARY KEY
);

ROLLBACK;
~~~

Với CREATE TABLE thông thường của MySQL, bảng **tx_ddl_probe** vẫn có thể tồn tại sau ROLLBACK vì thao tác DDL đã gây implicit commit.

Kiểm tra:

~~~sql
SELECT
    TABLE_NAME
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'tx_ddl_probe';
~~~

### 7.1. Implicit commit có thể ảnh hưởng DML trước DDL

Xét tình huống:

~~~sql
START TRANSACTION;

UPDATE migration_state
SET note = 'begin migration'
WHERE id = 1;

CREATE TABLE payment_audit (
    id BIGINT PRIMARY KEY
);

ROLLBACK;
~~~

Nếu CREATE TABLE gây implicit commit, **UPDATE trước đó có thể đã được commit**. ROLLBACK ở cuối không thể đảm bảo khôi phục dữ liệu như người viết mong đợi.

Đây là lý do đặc biệt phải tránh gộp **DDL + DML phụ thuộc nhau** vào một changeset trên DBMS có implicit commit nếu mục tiêu là “tất cả hoặc không có gì”.

### 7.2. Atomic DDL trong MySQL 8 không phải transactional DDL

Một số phiên bản MySQL 8 hỗ trợ **atomic DDL** cho những thao tác, đối tượng và storage engine được hỗ trợ. Mục tiêu là đảm bảo kết quả của **một câu DDL** có trạng thái nhất quán, nhất là khi server gặp sự cố.

Tuy nhiên:

- Nó không biến nhiều DDL thành một transaction có thể ROLLBACK theo ý người dùng.
- Nó không làm lệnh ROLLBACK đảo ngược CREATE TABLE đã implicit commit.
- Nó không chứng minh DML trước DDL vẫn chưa commit.
- Phạm vi hỗ trợ atomic DDL cần kiểm tra theo phiên bản và loại lệnh.

**Thông điệp cốt lõi:** “atomic” trong tài liệu DDL của DBMS và “transactional” theo nghĩa COMMIT/ROLLBACK của ứng dụng **không phải một khái niệm**.

### 7.3. Ngoại lệ và DDL tạm

Có một số thao tác/đối tượng đặc biệt như bảng tạm với quy tắc commit khác, nhưng không được từ đó suy ra khả năng rollback đầy đủ. Chẳng hạn có những thao tác không implicit commit nhưng bản thân việc tạo hoặc xóa đối tượng tạm vẫn không đảo ngược theo cách người dùng kỳ vọng.

Với MySQL, hãy đọc đúng tài liệu của câu lệnh cụ thể và kiểm thử kết quả sau ROLLBACK, không thiết lập một quy tắc tổng quát chỉ dựa trên từ khóa CREATE.

## 8. MariaDB: cùng cảnh báo về implicit commit

MariaDB có nhiều thao tác DDL gây implicit commit tương tự MySQL, dù các phiên bản và tính năng có khác biệt. Một số cơ chế **atomic DDL** ở những bản MariaDB nhất định chủ yếu xử lý tính nhất quán khi thao tác bị gián đoạn hoặc crash.

Không đồng nhất những cơ chế đó với việc DDL có thể ROLLBACK trong transaction do người dùng mở.

Với MariaDB nên xác nhận:

- Phiên bản server và storage engine.
- Lệnh DDL chính xác, ví dụ ALTER TABLE, RENAME TABLE hoặc CREATE INDEX.
- Các thay đổi DML trước lệnh DDL có bị commit ngầm không.
- DDL có thể gây rebuild bảng hoặc giữ metadata lock lâu hay không.
- Kết quả schema sau khi rollback hoặc lỗi giữa chừng.

Khi dùng Liquibase, **runInTransaction:true** không thể biến một thao tác MariaDB implicit-commit thành một thao tác có thể rollback như PostgreSQL.

## 9. Oracle: DDL thường gây implicit commit

Với Oracle Database, nhiều lệnh DDL thông thường gây implicit commit trước khi thực thi; sau khi thành công, thao tác DDL cũng được commit. Vì vậy, chạy **ROLLBACK sau CREATE TABLE** thông thường không xóa bảng mới.

Tình huống minh họa:

~~~sql
-- Giả định bảng MIGRATION_STATE đã tồn tại
UPDATE MIGRATION_STATE
SET NOTE = 'STARTED'
WHERE ID = 1;

CREATE TABLE ORACLE_DDL_PROBE (
    ID NUMBER PRIMARY KEY
);

ROLLBACK;
~~~

Không nên kỳ vọng ROLLBACK cuối cùng đảo ngược UPDATE ở trước DDL hoặc xóa bảng vừa tạo. DDL có thể commit giao dịch đang mở **trước khi bản thân DDL được thực hiện**.

### 9.1. Điều gì xảy ra nếu DDL lỗi?

Một bẫy đặc biệt là nghĩ “DDL không thành công thì DML trước đó chắc chắn chưa commit”. Với implicit commit trước DDL, phần DML trước đó có thể đã commit **ngay cả khi lệnh DDL sau không thành công**.

Trong migration thực tế:

- Không gộp cập nhật dữ liệu quan trọng và DDL vào một changeset với kỳ vọng Oracle sẽ rollback toàn bộ khi lỗi.
- Ưu tiên changeset riêng cho bước DDL và bước DML.
- Kiểm tra trạng thái thật của database sau sự cố, không chỉ nhìn exception từ Liquibase.
- Có kế hoạch rollback chủ động hoặc forward fix cho schema đã thay đổi.

### 9.2. Lưu ý về khối PL/SQL

Khối PL/SQL có thể chứa DML trong transaction, nhưng không vì vậy mà các DDL thông thường được thực thi như một phần rollback-able của cùng transaction. Một số cơ chế SQL động và hệ thống có hành vi commit đặc thù. Đừng dùng việc “đưa DDL vào procedure” như giải pháp đảm bảo tính nguyên tử của schema migration.

### 9.3. Kiểm tra kết quả

Trên schema Oracle hiện tại, có thể truy vấn catalog tương ứng, chẳng hạn:

~~~sql
SELECT OBJECT_NAME, OBJECT_TYPE
FROM USER_OBJECTS
WHERE OBJECT_NAME = 'ORACLE_DDL_PROBE';
~~~

Dùng công cụ, quyền và schema phù hợp. Không chạy bài thử tạo/xóa bảng trên production.

## 10. SQL Server: nhiều DDL có thể giao dịch, nhưng có ngoại lệ

Microsoft SQL Server cho phép nhiều thao tác DDL phổ biến nằm trong explicit transaction. Ví dụ minh họa trên database thử nghiệm:

~~~sql
BEGIN TRANSACTION;

CREATE TABLE dbo.tx_ddl_probe (
    id BIGINT PRIMARY KEY
);

ROLLBACK TRANSACTION;
~~~

Đối với CREATE TABLE thông thường trong transaction hợp lệ, bảng sẽ không còn sau ROLLBACK.

Kiểm tra:

~~~sql
SELECT OBJECT_ID('dbo.tx_ddl_probe', 'U') AS table_object_id;
~~~

### 10.1. Những điều cần tránh giả định

Không phải mọi lệnh DDL hoặc thao tác quản trị của SQL Server đều được phép trong explicit transaction. Một số tác vụ ở cấp database, thao tác cấu hình hệ thống hoặc chế độ đặc biệt có giới hạn riêng.

Cần kiểm tra theo lệnh cụ thể:

- Có được thực thi trong transaction không?
- Có bắt buộc là lệnh đầu tiên của batch không?
- Có dùng kỹ thuật online/resumable hoặc chế độ khác làm thay đổi cách chạy không?
- Mức độ khóa là gì, ảnh hưởng tới truy vấn/DML ra sao?
- JDBC driver và executor của Liquibase có gửi đúng batch T-SQL không?

### 10.2. GO không tự tạo transaction

Trong nhiều công cụ SQL Server, **GO** là batch separator của client như sqlcmd/SSMS, không phải câu lệnh T-SQL được SQL Server xử lý trực tiếp qua JDBC.

~~~sql
CREATE TABLE dbo.sample_a (id INT PRIMARY KEY);
GO
CREATE TABLE dbo.sample_b (id INT PRIMARY KEY);
GO
~~~

Đoạn script dùng GO không nói lên hai lệnh có nằm trong một transaction hay không. Batch boundary và transaction boundary là hai khái niệm khác nhau.

Khi chuyển script này vào Liquibase, phải xử lý GO đúng phiên bản/executor, và không được cho rằng việc tách batch tương đương với COMMIT.

## 11. SQLite: transactional DDL trong explicit transaction

SQLite có thể rollback những thay đổi schema thông thường khi chúng nằm trong explicit transaction hợp lệ.

Ví dụ trên database thử nghiệm:

~~~sql
BEGIN;

CREATE TABLE tx_ddl_probe (
    id INTEGER PRIMARY KEY
);

ROLLBACK;
~~~

Truy vấn kiểm tra:

~~~sql
SELECT name
FROM sqlite_master
WHERE type = 'table'
  AND name = 'tx_ddl_probe';
~~~

Nếu đã rollback đúng, bảng không còn được liệt kê.

Tuy nhiên, SQLite có những giới hạn riêng về ALTER TABLE, đổi cấu trúc bảng và locking. Liquibase có thể phải áp dụng một chuỗi thao tác thay thế để thực hiện một số thay đổi schema. Đừng suy luận một change type Liquibase cụ thể luôn chỉ tạo ra đúng một lệnh DDL SQLite.

## 12. DBMS nào cũng có ngoại lệ: kiểm tra theo thao tác

Một bảng tổng hợp nên được dùng như **điểm khởi đầu**, không phải quy tắc tuyệt đối.

~~~text
DBMS hỗ trợ transactional DDL rộng rãi
    |
    +-- DDL thông thường: có thể rollback trong transaction
    |
    +-- Một số DDL đặc biệt: phải chạy ngoài transaction

DBMS có nhiều implicit-commit DDL
    |
    +-- DDL có thể commit giao dịch trước/sau câu lệnh
    |
    +-- Một số thao tác có tính nguyên tử ở mức statement
    |
    +-- Không tự suy ra khả năng rollback toàn bộ migration
~~~

Trước khi viết changelog, hãy ghi nhận **loại câu lệnh**, **DBMS/version** và **transaction expectation**. Không chỉ dựa vào nhãn “PostgreSQL an toàn” hoặc “Oracle không an toàn”: bản chất rủi ro phụ thuộc thay đổi cụ thể.

## 13. runInTransaction trong Liquibase hoạt động ra sao?

**runInTransaction** là thuộc tính của **changeset**. Ví dụ YAML:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-004"
      author: "db-team"
      runInTransaction: true
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: status
                  type: varchar(24)
~~~

Và thay đổi chủ đích chạy ngoài transaction:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-005"
      author: "db-team"
      dbms: postgresql
      runInTransaction: false
      changes:
        - sql:
            splitStatements: false
            sql: |
              CREATE INDEX CONCURRENTLY idx_customer_status
              ON public.customer (status);
~~~

Không có nghĩa:

- **true**: “Liquibase sẽ rollback mọi DDL trên mọi DBMS khi lỗi”.
- **false**: “Lệnh sẽ tự thành công nếu SQL trước đó lỗi”.
- **false**: “Không cần rollback hoặc kiểm tra”.
- **true**: “Tất cả changeset trong changelog là một transaction”.

### 13.1. Khi nào dùng false?

Chỉ nên dùng khi có lý do rõ ràng, chẳng hạn câu lệnh DBMS **không được phép trong transaction block** hoặc cần quản lý giao dịch theo cách khác.

Những kiểm soát bổ sung:

1. Giới hạn một changeset ngoài transaction vào một thao tác chính khi khả thi.
2. Viết precondition để xác nhận đối tượng và trạng thái trước khi chạy.
3. Thiết kế câu lệnh khôi phục hoặc xử lý phần đã áp dụng.
4. Kiểm tra metadata database sau lỗi.
5. Xem DATABASECHANGELOG để hiểu changeset đã được ghi nhận hay chưa.
6. Tránh retry mù vì một thao tác có thể đã thành công dù công cụ báo lỗi sau đó.

### 13.2. Khi nào không nên đổi true thành false?

Không nên đổi chỉ vì gặp lỗi kiểu **permission denied**, **duplicate column** hoặc **syntax error**. Những lỗi đó cần được phân tích theo nguyên nhân riêng. Chuyển false có thể làm mất khả năng rollback transaction trên DBMS vốn hỗ trợ.

## 14. Ví dụ thất bại giữa changeset: PostgreSQL so với MySQL

Giả sử một changeset có hai thao tác:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-006-two-ddl"
      author: "training-team"
      runInTransaction: true
      changes:
        - createTable:
            tableName: tx_demo_customer
            columns:
              - column:
                  name: id
                  type: bigint
                  constraints:
                    primaryKey: true
        - createTable:
            tableName: tx_demo_customer
            columns:
              - column:
                  name: id
                  type: bigint
                  constraints:
                    primaryKey: true
~~~

Lệnh thứ hai cố tạo **cùng bảng** lần nữa và dự kiến thất bại. Đây chỉ là ví dụ để nghiên cứu giao dịch trên database cách ly, **không phải migration thực tế nên sử dụng**.

### Trên PostgreSQL

Nếu changeset được thực thi trong một transaction hợp lệ, CREATE TABLE đầu tiên có thể được rollback cùng lỗi của lệnh thứ hai. Sau thất bại, bảng không còn tồn tại.

### Trên MySQL

CREATE TABLE thường gây implicit commit. Bảng có thể vẫn tồn tại sau khi lệnh thứ hai thất bại. Liquibase có thể chưa ghi nhận changeset là EXECUTED, làm phát sinh sai lệch giữa **schema thực tế** và **lịch sử migration**.

### Bài học

Không nên xem **runInTransaction:true** là lớp bảo đảm duy nhất. Changelog phải được thử đúng DBMS, với kế hoạch xử lý nếu thay đổi dở dang.

## 15. Vì sao changeset khác với toàn bộ update?

Một changelog có thể gồm:

~~~text
changeset A: tạo bảng customer
changeset B: thêm cột customer.status
changeset C: tạo index trên customer.status
changeset D: chuyển đổi dữ liệu
~~~

Giả sử A, B, C đã hoàn thành và được commit, nhưng D thất bại.

Ngay cả trên PostgreSQL, **failure của changeset D không tự rollback A/B/C**. Các changeset đã thành công trước đó có lịch sử riêng. Liquibase không mặc định gói toàn bộ changelog vào một transaction toàn cục.

Vì thế:

- **Transaction rollback** chủ yếu liên quan tới phần chưa commit trong phạm vi hiện tại.
- **Liquibase rollback** là thao tác chủ động áp dụng những bước đảo ngược theo đích rollback đã chọn.
- **Database restore** có thể cần thiết nếu dữ liệu bị mất hoặc thay đổi không thể đảo ngược an toàn.

Không dùng một từ “rollback” để thay thế cả ba cơ chế.

## 16. Thiết kế rollback cho DDL theo DBMS

Một ví dụ changeset tạo bảng:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-007-create-notification"
      author: "notification-team"
      changes:
        - createTable:
            tableName: notification_event
            columns:
              - column:
                  name: id
                  type: bigint
                  constraints:
                    primaryKey: true
      rollback:
        - dropTable:
            tableName: notification_event
~~~

Rollback **dropTable** là lệnh đảo ngược được thiết kế rõ ràng. Nó có thể cần chạy như DDL mới ngay cả trên DBMS đã implicit commit DDL đầu tiên.

### 16.1. Một lệnh rollback không bảo đảm không mất dữ liệu

Khi bảng **notification_event** đã có dữ liệu, DROP TABLE sẽ làm mất dữ liệu nếu được thực thi. Một rollback kỹ thuật có thể đúng về cấu trúc nhưng sai về nghiệp vụ.

Đối với production, cần cân nhắc:

- Bảng đã có dữ liệu cần lưu không?
- Có foreign key, view, trigger hoặc job phụ thuộc không?
- Có thể dùng **forward fix** thay cho DROP không?
- Cần backup/restore có kiểm thử không?
- DDL rollback có thể chạy trong transaction theo DBMS đích không?

### 16.2. Rollback tự động và rollback tùy chỉnh

Liquibase có thể tạo rollback cho một số change type có cấu trúc; nhưng không phải thay đổi nào cũng được hỗ trợ auto rollback. Đặc biệt với **sql** và **sqlFile** tùy ý, cần chủ động viết rollback khi có thể hoặc xác định kế hoạch khôi phục riêng.

Cần chạy lệnh sinh **rollback SQL** phù hợp với phiên bản Liquibase và mốc rollback được chọn để review, thay vì cho rằng update-sql cũng chính là rollback-sql.

## 17. Liên hệ giữa DDL transaction và khóa database

Transaction và lock là hai khái niệm liên quan nhưng không đồng nhất.

**Khóa của DBMS** có thể bảo vệ bảng, index, catalog hoặc đối tượng khác trong quá trình DDL. Một số lock được giữ đến khi transaction commit/rollback; những thao tác khác nắm metadata lock theo vòng đời riêng.

**Khóa của Liquibase** dùng để phối hợp tránh nhiều tiến trình Liquibase cùng cập nhật một schema database song song.

Ví dụ hậu quả:

- PostgreSQL hỗ trợ rollback ALTER TABLE nhưng một transaction DDL kéo dài có thể giữ lock và chặn ứng dụng.
- MySQL có DDL implicit commit nhưng ALTER TABLE vẫn có thể cần metadata lock và gây chờ.
- Một changeset ngoài transaction có thể vẫn giữ lock ở DBMS trong thời gian thực thi statement.
- Liquibase lock không thay thế lock của DBMS và không ngăn người quản trị hoặc ứng dụng chạy SQL ngoài Liquibase.

### 17.1. DATABASECHANGELOGLOCK là gì?

Liquibase dùng bảng **DATABASECHANGELOGLOCK** để điều phối quyền chạy migration trên database đích. Khi có một tiến trình đang nắm lock, tiến trình Liquibase khác thường phải chờ hoặc thất bại theo cấu hình.

Đừng suy luận rằng có Liquibase lock thì toàn bộ DDL đang nằm trong một database transaction. **Khóa điều phối migration** và **transaction rollback của DDL** là hai cơ chế độc lập.

### 17.2. Cẩn thận khi lock còn tồn tại sau lỗi

Nếu quá trình bị gián đoạn, cần xác minh có tiến trình Liquibase nào đang thực sự chạy trước khi can thiệp khóa. Việc giải phóng lock thủ công hoặc qua lệnh quản trị tương ứng **không tự rollback DDL** hay khôi phục schema đã thay đổi một phần.

Tuyệt đối tránh giải phóng lock khi một migration khác vẫn đang hoạt động, vì có thể mở đường cho các thay đổi chồng chéo.

## 18. Lock duration và chiến lược giảm downtime

Một migration DDL có thể đúng về cú pháp và transactional behavior nhưng vẫn gây sự cố vận hành do **thời gian khóa**.

Ví dụ cần thay đổi một bảng có hàng triệu bản ghi:

~~~sql
ALTER TABLE orders
ADD COLUMN delivery_note VARCHAR(500);
~~~

Chi phí thực tế tùy DBMS, phiên bản, loại ALTER, kích thước bảng, index và mức độ tải.

Để giảm rủi ro:

1. Kiểm tra cơ chế lock/online DDL của lệnh cụ thể.
2. Thử trên dữ liệu có kích thước đại diện.
3. Chọn khung triển khai và timeout phù hợp.
4. Tách DDL nhanh và backfill dài thành các bước riêng.
5. Cân nhắc cách tạo index online/concurrently theo DBMS.
6. Theo dõi session chờ lock và độ trễ ứng dụng.
7. Có kế hoạch dừng, khôi phục hoặc tiếp tục phù hợp.

**Transactional DDL không đồng nghĩa zero-downtime DDL**. Thậm chí rollback một DDL bị chặn lâu có thể cũng phải giải phóng lock và thực hiện công việc phục hồi đáng kể.

## 19. Kết hợp với precondition và bộ lọc thực thi

Một changeset cần được xét qua nhiều lớp:

- **dbms**: chạy trên hệ quản trị nào?
- **context / labels**: nhóm triển khai nào được chọn?
- **precondition**: trạng thái schema/dữ liệu hiện tại có thỏa không?
- **runInTransaction**: Liquibase quản lý transaction cho changeset thế nào?
- **SQL thực tế**: DBMS có hỗ trợ và thực thi đúng hay không?

Ví dụ cho PostgreSQL:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-008-postgres-index"
      author: "orders-team"
      dbms: postgresql
      labels: performance
      runInTransaction: false
      preConditions:
        - onFail: HALT
        - onError: HALT
        - tableExists:
            schemaName: public
            tableName: orders
        - columnExists:
            schemaName: public
            tableName: orders
            columnName: created_at
        - not:
            - indexExists:
                schemaName: public
                tableName: orders
                indexName: idx_orders_created_at
      changes:
        - sql:
            splitStatements: false
            sql: |
              CREATE INDEX CONCURRENTLY idx_orders_created_at
              ON public.orders (created_at);
~~~

**Precondition không phải transaction.** Nó kiểm tra trạng thái tại thời điểm đánh giá, không đảm bảo không có thao tác ngoài Liquibase thay đổi schema ngay sau đó. SQL đặc thù DBMS vẫn cần được kiểm tra trên server thật.

**Labels không chọn database đích.** Dù dbms:postgresql và labels:performance đều khớp, nếu URL trỏ vào sai PostgreSQL database, changeset vẫn có thể chạy ngoài môi trường dự kiến.

## 20. Không dùng MARK_RAN để che trạng thái DDL dở dang

Một rủi ro sau thất bại là bảng đã được tạo nhưng changeset chưa được ghi nhận trong DATABASECHANGELOG.

Nhìn thấy precondition **tableExists** fail, người phát triển có thể muốn đặt **onFail:MARK_RAN** để pipeline tiếp tục. Điều này rất nguy hiểm khi chưa kiểm chứng:

- Bảng có đủ cột và constraint không?
- Index có hợp lệ không?
- Dữ liệu đã chuyển đổi đầy đủ chưa?
- Những câu SQL sau có được thực thi không?
- Các thay đổi có tương thích với mong đợi của ứng dụng không?

**MARK_RAN** đánh dấu changeset được xử lý theo cơ chế của Liquibase mà không thực thi phần thay đổi. Nó không làm schema tự động trở nên đúng.

Với partial DDL do implicit commit, cách xử lý cần có **điều tra trạng thái thật** và một kế hoạch hòa giải (reconciliation), không phải thay đổi metadata lịch sử để che lỗi.

## 21. Khi changeset lỗi: quy trình kiểm tra ba lớp

Sau lỗi, cần phân biệt **kết quả công cụ**, **trạng thái database** và **lịch sử Liquibase**.

### Lớp 1: Xem lỗi và transaction boundary

Ghi nhận:

- Changeset id, author và FILENAME.
- Statement nào gặp lỗi.
- DBMS/version, JDBC driver, Liquibase version.
- Giá trị runInTransaction.
- Lệnh DDL có implicit commit hoặc yêu cầu chạy ngoài transaction không.
- Có SQL nào đã thực thi thành công trước lỗi không.

### Lớp 2: Kiểm tra schema/dữ liệu thật

Truy vấn catalog để xác nhận bảng, cột, index, constraint. Kiểm tra dữ liệu đã sửa và các thay đổi từng bước. Đừng suy luận trạng thái chỉ từ exception.

### Lớp 3: Kiểm tra DATABASECHANGELOG

Ví dụ SQL:

~~~sql
SELECT
    ID,
    AUTHOR,
    FILENAME,
    DATEEXECUTED,
    ORDEREXECUTED,
    EXECTYPE,
    MD5SUM,
    DEPLOYMENT_ID
FROM DATABASECHANGELOG
ORDER BY DATEEXECUTED, ORDEREXECUTED;
~~~

Những dòng lịch sử giúp biết Liquibase đã ghi nhận gì, nhưng không chứng minh schema không từng bị thay đổi thủ công hoặc một phần DDL chưa commit thất bại đã được tự động phục hồi.

Nếu thấy schema khác DATABASECHANGELOG, **không chỉnh bảng lịch sử thủ công** như phương án đầu tiên. Đầu tiên phải xác định thay đổi nào thực sự tồn tại.

## 22. Bảng quyết định phục hồi sau migration thất bại

| Trạng thái | Diễn giải có thể | Hướng xử lý có kiểm soát |
|---|---|---|
| Changeset lỗi, không có thay đổi schema | Transaction rollback có thể đã hoàn tất | Sửa nguyên nhân và thử lại trên DB test; xác minh lịch sử |
| Changeset lỗi, bảng mới vẫn tồn tại | DDL implicit commit hoặc chạy ngoài transaction | Kiểm tra cấu trúc thật, chọn rollback chủ động/forward fix |
| Changeset lỗi, index tồn tại nhưng invalid | Có thể do index concurrent bị gián đoạn | Kiểm tra catalog, làm sạch/sửa index theo quy trình DBMS |
| Changeset được ghi EXECUTED, schema đã bị sửa thủ công | Drift ngoài Liquibase | Điều tra audit và áp dụng changeset sửa chữa |
| Changeset được ghi MARK_RAN nhưng đối tượng thiếu | Precondition đánh dấu mà không thực thi SQL | Xác minh tiền đề và kế hoạch baseline/correction |
| Các changeset trước thành công, một changeset sau thất bại | Mỗi changeset có commit riêng | Giữ lịch sử bước đã thành công, khắc phục bước lỗi |
| Liquibase lock chưa được giải phóng | Tiến trình bị ngắt hoặc đang chạy | Kiểm tra tiến trình thật trước khi xử lý lock |

Không xóa hàng DATABASECHANGELOG hoặc thay checksum để ép Liquibase chạy lại một script mà chưa biết database có đang giữ phần kết quả hay không.

## 23. Chiến lược expand–migrate–contract khi DDL không rollback được

Đối với thay đổi lớn, thay vì mong rollback toàn bộ, có thể triển khai theo nhiều bước tương thích ngược:

**Expand:** thêm cột hoặc cấu trúc mới, ứng dụng cũ vẫn hoạt động.

**Migrate:** chuyển dữ liệu trong các batch có kiểm soát; theo dõi tiến độ và tính lặp lại an toàn.

**Switch:** đưa ứng dụng sang dùng cấu trúc mới sau khi dữ liệu sẵn sàng.

**Contract:** xóa cấu trúc cũ sau khi xác nhận không còn phụ thuộc.

Ví dụ:

~~~text
Release A:
  001-add-customer-status-column
  002-deploy-application-writing-both-fields

Release B:
  003-backfill-customer-status
  004-verify-data-consistency

Release C:
  005-switch-reads-to-new-status
  006-enforce-status-constraint

Release D:
  007-drop-legacy-status
~~~

Đây là sơ đồ vận hành, không phải các chỉ thị Liquibase thực thi trực tiếp. Các bước deploy ứng dụng và kiểm tra dữ liệu phải được điều phối ngoài changelog hoặc bằng quy trình phù hợp.

Ưu điểm là có nhiều điểm dừng an toàn, đặc biệt trên DBMS có implicit-commit DDL. Tuy nhiên, **DROP** vẫn có thể không đảo ngược được khi đã mất dữ liệu; cần backup và chính sách retention.

## 24. Transactional DDL không thay thế precondition dữ liệu

Trước khi thêm NOT NULL, có thể cần kiểm tra:

~~~sql
SELECT COUNT(*)
FROM customer
WHERE status IS NULL;
~~~

Nếu còn NULL, thay đổi có thể thất bại. Trên PostgreSQL transactional DDL có thể rollback bước ALTER, nhưng điều đó không giải quyết dữ liệu chưa hợp lệ. Trên MySQL hoặc Oracle, kiểu thất bại có thể còn làm tăng rủi ro partial state.

Một precondition local có thể đặt ngưỡng:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-009-enforce-status"
      author: "customer-team"
      preConditions:
        - onFail: HALT
        - onError: HALT
        - sqlCheck:
            expectedResult: "0"
            sql: "SELECT COUNT(*) FROM customer WHERE status IS NULL"
      changes:
        - addNotNullConstraint:
            tableName: customer
            columnName: status
            columnDataType: varchar(24)
~~~

Câu SQL kiểm tra phải tương thích DBMS. Precondition không bảo đảm dữ liệu không bị ghi mới giữa thời điểm check và thời điểm constraint được áp dụng; cần đánh giá ghi đồng thời/lock và chính sách ứng dụng.

## 25. CI/CD: kiểm tra SQL trước khi chạy không đồng nghĩa kiểm tra transaction

Pipeline có thể chạy:

~~~bash
liquibase --changelog-file=db/changelog/db.changelog-master.yaml validate
liquibase --changelog-file=db/changelog/db.changelog-master.yaml status --verbose
liquibase --changelog-file=db/changelog/db.changelog-master.yaml update-sql
~~~

Các lệnh có giá trị nhưng giới hạn rõ:

- **validate**: kiểm tra cấu trúc changelog theo khả năng Liquibase, không chứng minh transaction hoạt động như mong muốn.
- **status --verbose**: xem changeset pending theo database và filter hiện tại, không chứng minh DDL có thể rollback.
- **update-sql**: xem SQL dự kiến, không thực thi transaction thử nghiệm.
- **update**: thực thi thật và có thể làm thay đổi database; chỉ chạy sau khi kiểm tra và được phê duyệt.

Cần có **database kiểm thử đại diện** để thực nghiệm transaction/rollback với đúng DBMS/driver/executor. Đặc biệt với Oracle/MySQL/MariaDB, không dựa vào SQL preview để kết luận rằng failed changeset sẽ được undo toàn bộ.

### 25.1. Nên lưu bằng chứng nào?

- Liquibase version và JDBC driver.
- DBMS và version, schema/database đích.
- Artifact hoặc commit hash chứa changelog.
- Danh sách changeset pending.
- SQL preview đã review.
- RunInTransaction của changeset nhạy cảm.
- Kiểm tra metadata trước và sau update.
- Deployment ID và log kết quả.
- Phương án phục hồi đã được kiểm thử.

Không ghi password hoặc secret vào log migration.

## 26. Tích hợp Spring Boot và cách tránh lỗi khi startup

Nếu ứng dụng Spring Boot bật Liquibase, migration có thể chạy trong quá trình khởi động.

Ví dụ:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://db-staging.internal:5432/orders
    username: orders_migrator
    password: "<inject-at-runtime>"
    driver-class-name: org.postgresql.Driver

  liquibase:
    enabled: true
    change-log: classpath:/db/changelog/db.changelog-master.yaml
~~~

Đây là cấu hình ví dụ, không chứa secret thật.

Những nguyên tắc quan trọng:

1. **Spring transaction của ứng dụng không tự bao trùm Liquibase startup migration.** Không cho rằng một transaction annotation của business service làm DDL rollback được.
2. Nếu DDL tự commit, thất bại khởi động ứng dụng không tự hoàn nguyên schema đã thay đổi.
3. Nhiều instance khởi động song song cần cơ chế phối hợp; Liquibase có DATABASECHANGELOGLOCK nhưng vẫn phải kiểm soát quyền và thời điểm triển khai.
4. Với migration DDL dài hoặc nhạy cảm, cân nhắc chạy bước Liquibase tách khỏi khởi động ứng dụng.
5. Dùng tài khoản migration có quyền phù hợp và tách quyền khỏi tài khoản runtime khi kiến trúc yêu cầu.

Nếu ứng dụng khởi động lại sau thất bại, Liquibase sẽ xem lịch sử và tập changeset pending, nhưng phải kiểm tra schema thật nếu có khả năng DDL đã implicit commit. Tự động retry có thể gây duplicate object hoặc side effect dữ liệu.

## 27. Bài thực hành 1: quan sát ROLLBACK trên PostgreSQL và MySQL

**Mục đích:** chứng minh khác biệt giữa transactional DDL và implicit-commit DDL bằng một phép thử nhỏ.

**Điều kiện:** tạo hai database thử nghiệm riêng, không dùng production. Có quyền CREATE/DROP trong schema dành riêng cho bài học. Đảm bảo tên **tx_ddl_probe** chưa tồn tại.

### 27.1. PostgreSQL

~~~sql
BEGIN;
CREATE TABLE public.tx_ddl_probe (id BIGINT PRIMARY KEY);
ROLLBACK;

SELECT to_regclass('public.tx_ddl_probe') AS table_after_rollback;
~~~

**Kỳ vọng:** table_after_rollback là NULL trong tình huống kiểm thử thông thường.

### 27.2. MySQL

~~~sql
START TRANSACTION;
CREATE TABLE tx_ddl_probe (id BIGINT PRIMARY KEY);
ROLLBACK;

SELECT COUNT(*) AS tables_after_rollback
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'tx_ddl_probe';
~~~

**Kỳ vọng:** đếm được bảng vì CREATE TABLE thông thường gây implicit commit.

### 27.3. Điều cần giải thích

- Tại sao kết quả khác nhau dù cả hai đều có lệnh BEGIN/START TRANSACTION?
- Nếu Liquibase chứa hai CREATE TABLE và cái thứ hai lỗi, rủi ro trên MySQL khác PostgreSQL thế nào?
- **runInTransaction:true** có làm kết quả MySQL giống PostgreSQL không?
- Tại sao phải kiểm tra database thật thay vì chỉ kiểm tra lệnh Liquibase trả lỗi?
- “Atomic DDL” của MySQL có nghĩa là ROLLBACK xóa bảng mới tạo không?

### 27.4. Dọn thử nghiệm

Chỉ sau khi xác minh database hiện tại là **database thử nghiệm được cấp phép**, có thể dọn đối tượng còn tồn tại bằng DDL phù hợp:

~~~sql
DROP TABLE IF EXISTS tx_ddl_probe;
~~~

Không chạy lệnh DROP trên môi trường ngoài bài thực hành. PostgreSQL có thể không cần dọn vì bảng đã rollback; MySQL có thể cần dọn.

## 28. Bài thực hành 2: đánh giá changeset nhiều DDL

**Bối cảnh:** một migration cần tạo bảng **training_invoice** và thêm index, nhưng người viết muốn tránh trạng thái thành công một phần.

### Phương án A: một changeset

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "practice-001"
      author: "training-team"
      runInTransaction: true
      changes:
        - createTable:
            tableName: training_invoice
            columns:
              - column:
                  name: id
                  type: bigint
                  constraints:
                    primaryKey: true
              - column:
                  name: invoice_code
                  type: varchar(80)
        - createIndex:
            tableName: training_invoice
            indexName: idx_training_invoice_code
            columns:
              - column:
                  name: invoice_code
~~~

### Phương án B: hai changeset riêng

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "practice-002-create"
      author: "training-team"
      changes:
        - createTable:
            tableName: training_invoice
            columns:
              - column:
                  name: id
                  type: bigint
                  constraints:
                    primaryKey: true
              - column:
                  name: invoice_code
                  type: varchar(80)

  - changeSet:
      id: "practice-003-index"
      author: "training-team"
      preConditions:
        - onFail: HALT
        - onError: HALT
        - tableExists:
            tableName: training_invoice
      changes:
        - createIndex:
            tableName: training_invoice
            indexName: idx_training_invoice_code
            columns:
              - column:
                  name: invoice_code
~~~

**Yêu cầu:** phân tích ưu/nhược điểm trên PostgreSQL và MySQL.

Gợi ý:

- Với PostgreSQL, phương án A có thể rollback cả phần DDL trong một transaction nếu có lỗi bên trong changeset.
- Với MySQL, implicit commit có thể khiến phương án A vẫn để lại bảng; phương án B cho lịch sử và bước phục hồi tường minh hơn nhưng cũng không ngăn implicit commit.
- Phương án B tăng số changeset, đổi lại khả năng review/điều tra từng bước tốt hơn.
- Cả hai phương án đều cần xác minh schema sau lỗi, không phụ thuộc duy nhất vào DATABASECHANGELOG.

**Không chạy cả hai phương án liên tiếp trên một database chưa được reset**, vì chúng cùng tạo bảng training_invoice.

## 29. Case study: migration production dừng sau ALTER TABLE

Hệ thống hóa đơn sử dụng MySQL. Một changeset thực hiện:

1. ALTER TABLE invoice ADD COLUMN status.
2. UPDATE invoice SET status theo dữ liệu cũ.
3. ALTER TABLE invoice MODIFY COLUMN status NOT NULL.

Ở bước 3, migration lỗi do dữ liệu chưa đạt điều kiện. Người vận hành thấy Liquibase báo changeset thất bại.

### 29.1. Điều không nên làm

- Không mặc định ALTER TABLE đầu tiên đã bị rollback.
- Không chạy lại nguyên changeset mà chưa xem cột đã tồn tại.
- Không xóa dòng DATABASECHANGELOG hoặc đổi ID để “chạy lại”.
- Không đặt MARK_RAN chỉ vì cột status đã xuất hiện.
- Không tiếp tục rollout ứng dụng khi chưa rõ dữ liệu và constraint đang ở trạng thái nào.

### 29.2. Quy trình giải quyết

1. Dừng các bước phát hành phụ thuộc.
2. Kiểm tra cột **status** đã tồn tại chưa, nullable/default/type hiện tại là gì.
3. Kiểm tra những dòng đã được UPDATE và mức độ hoàn tất.
4. Xem DATABASECHANGELOG và log Liquibase để xác định phần được ghi nhận.
5. Xác minh server/driver, implicit commit và thời điểm lỗi.
6. Chọn cách sửa chữa: backfill còn thiếu, bổ sung constraint bằng changeset mới, hoặc phục hồi dữ liệu và schema theo kế hoạch đã duyệt.
7. Thử trên bản sao database đại diện trước khi tiếp tục production.
8. Lưu biên bản sự cố để điều chỉnh cách chia changeset trong lần tiếp theo.

### 29.3. Thiết kế phòng ngừa

Tách thành ba changeset: **expand**, **backfill**, **contract**. Chỉ thực hiện contract sau khi dữ liệu đã được kiểm tra và ứng dụng không còn ghi NULL. Kiểm soát khối lượng UPDATE để tránh transaction hoặc metadata lock quá lâu.

## 30. Những hiểu nhầm cần sửa

| Hiểu nhầm | Thực tế cần nhớ |
|---|---|
| runInTransaction:true đảm bảo mọi DDL rollback được | Chỉ đúng trong phạm vi khả năng DBMS/loại lệnh |
| MySQL 8 atomic DDL giống PostgreSQL transactional DDL | Atomic DDL không tự cho phép ROLLBACK thao tác đã implicit commit |
| Một changelog tương đương một transaction lớn | Thông thường Liquibase xử lý transaction theo changeset |
| Có Liquibase lock thì DDL không gây khóa bảng | Lock điều phối và DBMS locks là hai lớp khác nhau |
| Nếu Liquibase báo lỗi thì database chưa đổi | DDL có thể đã commit hoặc chạy dở dang |
| Chỉnh checksum có thể khôi phục schema | Checksum là metadata lịch sử, không phải thao tác phục hồi |
| Rollback changeset bằng DROP luôn an toàn | Có thể làm mất dữ liệu hoặc đối tượng phụ thuộc |
| update-sql thành công chứng minh rollback DDL tốt | SQL preview không thực thi thử transaction |
| DDL chạy nhanh trên dev sẽ không khóa lâu trên prod | Dữ liệu, tải hệ thống và lock khác nhau |
| Precondition pass thì không có race condition | Trạng thái có thể đổi sau thời điểm kiểm tra |
| runInTransaction:false xử lý mọi lỗi DDL | Nó thay đổi cách bọc transaction, không sửa SQL sai hoặc quyền |
| SQL Server luôn rollback được mọi DDL | Có ngoại lệ theo loại lệnh/phiên bản/chế độ |

## 31. Checklist trước khi triển khai DDL bằng Liquibase

- [ ] Xác định đúng DBMS, phiên bản, JDBC driver và loại executor.
- [ ] Xác định câu DDL nào có thể nằm trong transaction và câu nào bắt buộc ngoài transaction.
- [ ] Biết DDL có gây implicit commit hay không; không nhầm atomic DDL với transactional DDL.
- [ ] Không dựa duy nhất vào runInTransaction:true để kỳ vọng rollback tự động.
- [ ] Chỉ dùng runInTransaction:false khi có lý do cụ thể, đã kiểm chứng.
- [ ] Không gộp nhiều thao tác rủi ro vào một changeset khó phục hồi.
- [ ] Với DDL và DML liên quan, đã đánh giá partial commit và quan hệ phụ thuộc.
- [ ] Đã đánh giá lock, metadata lock, thời gian chạy và tác động tới ứng dụng.
- [ ] Có precondition phù hợp với trạng thái schema/dữ liệu.
- [ ] Không dùng MARK_RAN để che trạng thái schema không tương đương.
- [ ] Changelog, IDs, author và đường dẫn changeset đã phát hành được giữ ổn định.
- [ ] Đã chạy validate, status và update-sql trên cấu hình dự kiến.
- [ ] Có database thử nghiệm cùng DBMS/version và dữ liệu đại diện.
- [ ] Đã thử kịch bản fail giữa changeset trên môi trường thử nghiệm.
- [ ] Đã kiểm tra schema/dữ liệu thực tế và DATABASECHANGELOG sau lỗi.
- [ ] Rollback tùy chỉnh hoặc forward fix đã được review và thử nghiệm.
- [ ] Các thay đổi cần chạy ngoài transaction có kế hoạch xử lý khi bị gián đoạn.
- [ ] Không xóa/sửa DATABASECHANGELOG hoặc giải phóng lock tùy tiện.
- [ ] Endpoint, schema, user và quyền của môi trường đích đã được xác nhận.
- [ ] Spring Boot/CI/CD dùng đúng artifact và bộ lọc môi trường.
- [ ] Có backup/restore hoặc phương án khôi phục đã kiểm thử cho thay đổi phá hủy.
- [ ] Đã ghi nhận log, deployment ID và các quyết định rollback/phục hồi.

**Kết luận:** Hành vi transaction của DDL là thuộc tính của **DBMS và từng câu lệnh**, không phải lời hứa phổ quát từ Liquibase. PostgreSQL và một số thao tác SQL Server/SQLite thường hỗ trợ rollback DDL khi nằm trong transaction hợp lệ; MySQL, MariaDB và Oracle có nhiều DDL gây implicit commit. Thuộc tính **runInTransaction** giúp điều phối cách Liquibase thực thi changeset nhưng không thay đổi khả năng giao dịch của database. Muốn triển khai an toàn, hãy thiết kế changeset theo ranh giới phục hồi, kiểm tra SQL và lock, thử kịch bản lỗi trên DBMS thật, rồi đối chiếu cả **DATABASECHANGELOG** lẫn **schema/dữ liệu thực tế** trước khi tiếp tục hoặc rollback.

