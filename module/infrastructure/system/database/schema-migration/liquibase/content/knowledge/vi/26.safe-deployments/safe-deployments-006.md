# Cân nhắc DDL trực tuyến và khả năng của từng hệ quản trị

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, chúng ta quản lý thay đổi schema và dữ liệu bằng **changelog**, **changeset**, **precondition**, **checksum** và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Bài thuộc chương **Triển khai an toàn** này tập trung vào cách đánh giá **DDL trực tuyến (online DDL)** và khả năng thực tế của từng hệ quản trị cơ sở dữ liệu trước khi thiết kế migration.

DDL trực tuyến là nhóm cơ chế cho phép thay đổi cấu trúc database trong khi ứng dụng vẫn tiếp tục đọc/ghi ở mức độ nhất định. Ví dụ là tạo index đồng thời, thêm constraint theo giai đoạn, thêm cột bằng thuật toán không sao chép toàn bảng hoặc rebuild index trong chế độ online. Tuy nhiên, **online không có nghĩa không khóa, không chờ, không tốn tài nguyên hoặc không thể gây gián đoạn**. Hầu hết DBMS vẫn cần khóa metadata hoặc khóa ngắn ở một số thời điểm; một số thao tác còn tạo bản sao dữ liệu, tăng I/O, transaction log và replication lag.

Mục tiêu là biết đánh giá một thay đổi theo loại DBMS, phiên bản, engine, loại object và quy mô dữ liệu; chọn change type Liquibase hay SQL chuyên biệt; chia migration thành các bước tương thích; và xác minh trạng thái trước, trong và sau khi triển khai.

## 1. DDL trực tuyến giải quyết vấn đề gì?

**DDL (Data Definition Language)** là các lệnh thay đổi cấu trúc như CREATE, ALTER, DROP, CREATE INDEX và các thao tác quản lý constraint. Với bảng nhỏ hoặc môi trường ít tải, nhiều DDL có thể chạy nhanh. Trên bảng hàng triệu/billions bản ghi, cùng thao tác có thể:

- Giữ khóa làm các truy vấn ghi hoặc đọc phải chờ.
- Quét hoặc viết lại toàn bộ bảng.
- Tạo index với lượng I/O lớn.
- Tăng transaction log, redo/undo hoặc WAL.
- Tăng replication lag và áp lực lên replica.
- Cần thêm dung lượng tạm hoặc dung lượng đĩa.
- Làm connection pool cạn vì request chờ lock.
- Kéo dài thời gian triển khai và vượt timeout của CI/CD.

Online DDL cố gắng giảm mức chặn hoặc chia công việc thành các giai đoạn để ứng dụng vẫn hoạt động. Cơ chế cụ thể khác nhau theo DBMS và từng thao tác. Một hệ quản trị có thể hỗ trợ online index build nhưng không hỗ trợ online đổi kiểu dữ liệu; cùng một lệnh ALTER TABLE có thể online ở phiên bản mới nhưng phải copy table ở phiên bản cũ.

### Online không đồng nghĩa zero-downtime

Một thao tác được gọi là online vẫn có thể cần:

1. Khóa ngắn lúc bắt đầu để xác nhận cấu trúc và chuẩn bị metadata.
2. Quét dữ liệu trong khi vẫn cho phép một số thao tác DML.
3. Đồng bộ các thay đổi phát sinh trong lúc quét.
4. Khóa ngắn lúc hoàn tất để chuyển đổi metadata.
5. Chờ transaction cũ kết thúc hoặc chờ lock được cấp.

Nếu một transaction dài đang giữ lock hoặc tham chiếu bảng, DDL có thể chờ trước khi bắt đầu. Khi DDL đã nằm trong hàng đợi, một số DBMS có thể khiến các request khác chờ phía sau. Vì vậy, cần theo dõi lock wait và đặt chính sách timeout phù hợp.

## 2. Các chiều cần đánh giá trước khi chọn online DDL

Không nên quyết định chỉ dựa vào tên lệnh có chữ ONLINE hoặc CONCURRENTLY. Hãy đánh giá ít nhất các yếu tố sau:

| Yếu tố | Câu hỏi cần trả lời |
|---|---|
| DBMS và phiên bản | Server cụ thể có hỗ trợ thao tác này không? |
| Edition/license | Tính năng online có phụ thuộc edition, license hoặc cấu hình không? |
| Loại object | Bảng thường, partitioned table, index, view hay constraint? |
| Storage engine | Engine có hỗ trợ online DDL tương ứng không? |
| Thuật toán | Metadata-only, in-place, concurrent hay phải copy/rebuild? |
| Mức khóa | Cho phép đọc/ghi đồng thời đến mức nào? Có khóa ngắn đầu/cuối không? |
| Dữ liệu | Kích thước bảng, số hàng, độ rộng hàng, index và phân bố dữ liệu? |
| Tài nguyên | Đĩa trống, temporary space, CPU, I/O và transaction log? |
| Replication | Có replica, CDC, logical replication hoặc downstream consumer không? |
| Rollback | Có thể đảo ngược không? Thao tác đã commit có phục hồi được không? |
| Ứng dụng | Phiên bản code cũ/mới có tương thích với schema ở từng giai đoạn không? |
| Quan sát | Có thể theo dõi tiến độ, lock, lỗi và hậu điều kiện không? |

Cần phân biệt **algorithm**, **lock mode** và **transaction semantics**. Ví dụ, một thao tác dùng thuật toán INPLACE không nhất thiết không rebuild dữ liệu; một thao tác dùng LOCK=NONE vẫn có thể cần metadata lock; một DDL chạy online vẫn có thể implicit commit và không rollback được như DML.

## 3. Khả năng online DDL theo từng hệ quản trị

Bảng sau là định hướng, không phải cam kết cho mọi phiên bản. Trước production, kiểm tra tài liệu đúng DBMS/version/edition và thử trên bản sao có kích thước, workload gần thực tế.

| DBMS | Cơ chế thường gặp | Điểm cần chú ý |
|---|---|---|
| **PostgreSQL** | CREATE INDEX CONCURRENTLY; NOT VALID/VALIDATE CONSTRAINT; lock modes | Concurrent index không chạy trong transaction block; một số ALTER TABLE vẫn cần lock mạnh; index lỗi có thể invalid |
| **MySQL (InnoDB)** | Online DDL với ALGORITHM và LOCK; INSTANT/INPLACE/COPY | Hỗ trợ tùy thao tác/version; metadata lock vẫn tồn tại; DDL có implicit commit |
| **MariaDB** | Online/instant ALTER tùy version và engine | Không giả định hành vi giống MySQL; kiểm tra cú pháp, algorithm và giới hạn riêng |
| **SQL Server** | Online index create/rebuild; resumable operations ở trường hợp hỗ trợ | Phụ thuộc version, edition, index/object type; vẫn cần lock ngắn và dung lượng |
| **Oracle Database** | Online index operations, online redefinition và DBMS_REDEFINITION | Tính năng/giới hạn phụ thuộc version, object và license; DDL có implicit commit |
| **SQLite** | Một số ALTER TABLE đơn giản; thường rebuild table cho thay đổi phức tạp | Khả năng online hạn chế, chỉ một writer tại một thời điểm; cần kế hoạch khóa và downtime |

Không có một thuộc tính Liquibase chung có thể biến DDL thành online trên mọi DBMS. Liquibase điều phối migration; tính chất online đến từ câu lệnh và engine của database.

## 4. PostgreSQL: CREATE INDEX CONCURRENTLY

PostgreSQL hỗ trợ **CREATE INDEX CONCURRENTLY** để tạo index mà không chặn các thao tác INSERT, UPDATE và DELETE theo cách CREATE INDEX thông thường có thể làm. Cơ chế này vẫn tốn tài nguyên và có thể chờ transaction đang hoạt động.

Ví dụ:

~~~sql
CREATE INDEX CONCURRENTLY idx_invoice_status_created
ON public.invoice (status, created_at);
~~~

Đặc điểm cần nhớ:

- Thực hiện nhiều giai đoạn và quét bảng nhiều lần.
- Có thể chờ transaction hoặc snapshot cũ kết thúc.
- Tốn CPU, I/O và dung lượng index.
- Không được chạy bên trong transaction block.
- Nếu thất bại, có thể để lại index không hợp lệ.
- Không phải mọi loại index/partitioned table đều hỗ trợ cùng cách; cần kiểm tra phiên bản và loại bảng.

### Đưa vào Liquibase

Vì PostgreSQL cấm CREATE INDEX CONCURRENTLY trong transaction block, changeset cần đặt **runInTransaction: false**. Ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 040-create-invoice-status-created-index
      author: billing-team
      dbms: postgresql
      runInTransaction: false
      preConditions:
        - onFail: HALT
        - onError: HALT
        - tableExists:
            schemaName: public
            tableName: invoice
        - columnExists:
            schemaName: public
            tableName: invoice
            columnName: status
        - not:
            - indexExists:
                schemaName: public
                tableName: invoice
                indexName: idx_invoice_status_created
      changes:
        - sql:
            splitStatements: false
            sql: |
              CREATE INDEX CONCURRENTLY idx_invoice_status_created
              ON public.invoice (status, created_at);
      rollback:
        - sql:
            splitStatements: false
            sql: |
              DROP INDEX CONCURRENTLY IF EXISTS
              public.idx_invoice_status_created;
~~~

Các lưu ý:

- **Một changeset nên chứa một thao tác non-transactional độc lập.** Nếu có nhiều lệnh và lệnh sau lỗi, lệnh trước có thể đã có hiệu lực.
- **runInTransaction: false không phải tùy chọn bật online.** Nó chỉ tránh transaction bao trùm changeset; chính từ khóa CONCURRENTLY mới chọn cơ chế PostgreSQL.
- **indexExists không đủ để xác minh index hợp lệ.** Sau khi chạy, cần kiểm tra metadata.
- **Rollback cũng phải phù hợp transaction semantics.** DROP INDEX CONCURRENTLY có các giới hạn riêng và cần được thử.
- Không thêm `MARK_RAN` để bỏ qua lỗi trùng tên nếu chưa xác minh định nghĩa và trạng thái index.

Kiểm tra trạng thái:

~~~sql
SELECT
    ns.nspname AS schema_name,
    idx.relname AS index_name,
    i.indisready,
    i.indisvalid
FROM pg_class AS idx
JOIN pg_namespace AS ns ON ns.oid = idx.relnamespace
JOIN pg_index AS i ON i.indexrelid = idx.oid
WHERE ns.nspname = 'public'
  AND idx.relname = 'idx_invoice_status_created';
~~~

Nếu `indisvalid = false`, index không đạt hậu điều kiện. Cần xác định tiến trình tạo đã dừng, kiểm tra log và dependency, rồi mới quyết định drop/recreate hoặc cách khắc phục phù hợp.

## 5. PostgreSQL: thêm constraint theo nhiều giai đoạn

Với bảng lớn, thêm foreign key hoặc check constraint và xác thực toàn bộ dữ liệu trong một thao tác có thể tạo tải hoặc lock không mong muốn. PostgreSQL cho phép một số constraint được thêm với **NOT VALID**, sau đó xác minh dữ liệu hiện hữu bằng **VALIDATE CONSTRAINT**.

Ví dụ thêm foreign key:

~~~sql
ALTER TABLE public.invoice
ADD CONSTRAINT fk_invoice_customer
FOREIGN KEY (customer_id)
REFERENCES public.customer(id)
NOT VALID;
~~~

Sau đó, trong một bước riêng:

~~~sql
ALTER TABLE public.invoice
VALIDATE CONSTRAINT fk_invoice_customer;
~~~

Ý nghĩa:

- Constraint được tạo để áp dụng cho các thay đổi mới theo quy tắc của PostgreSQL.
- Dữ liệu cũ chưa được quét/xác thực ngay trong bước đầu.
- VALIDATE CONSTRAINT kiểm tra các hàng hiện có.
- Tách hai giai đoạn giúp kiểm soát thời gian và thời điểm validation.

Tuy nhiên, ADD CONSTRAINT vẫn cần lock để thay đổi metadata; NOT VALID không đồng nghĩa không lock. VALIDATE cũng sử dụng tài nguyên và có thể chờ hoặc cạnh tranh workload. Với check constraint, PostgreSQL cũng hỗ trợ chiến lược NOT VALID/VALIDATE trong các trường hợp được tài liệu hóa. Không áp dụng cơ chế này cho mọi loại constraint: ví dụ unique constraint có cách tạo index riêng và không có cú pháp NOT VALID tương tự.

Một changeset Liquibase có thể quản lý mỗi bước riêng bằng SQL PostgreSQL và `dbms: postgresql`. Giữ changeset nhỏ để có thể xác định rõ bước nào đã chạy khi validation thất bại.

## 6. PostgreSQL: kiểm soát lock và timeout

DDL cần lock ngay cả khi có cơ chế online. Trên PostgreSQL, một số công cụ cấu hình timeout trong session:

- **lock_timeout**: giới hạn thời gian chờ để lấy lock.
- **statement_timeout**: giới hạn thời gian thực thi statement.
- **idle_in_transaction_session_timeout**: kiểm soát session để transaction mở nhưng không hoạt động trong thời gian dài.

Ví dụ minh họa truy vấn cấu hình:

~~~sql
SHOW lock_timeout;
SHOW statement_timeout;
~~~

Chọn timeout dựa trên SLA và thời gian bảo trì. Timeout quá ngắn có thể khiến migration thất bại lặp lại; timeout quá dài có thể làm request chờ lâu. Cần xác định nếu lock không lấy được thì dừng và retry vào cửa sổ khác, thay vì chờ vô hạn.

Theo dõi các session đang chờ:

~~~sql
SELECT
    pid,
    usename,
    state,
    wait_event_type,
    wait_event,
    query
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY query_start;
~~~

Quyền xem thông tin session có thể khác theo role. Khi điều tra production, dùng công cụ giám sát và quyền được phê duyệt.

## 7. MySQL InnoDB: ALGORITHM và LOCK

MySQL InnoDB hỗ trợ online DDL cho nhiều thao tác thông qua các thuật toán và mức khóa:

- **INSTANT**: thay đổi metadata cho những thao tác được hỗ trợ, thường tránh rebuild bảng.
- **INPLACE**: thực hiện thay đổi tại chỗ theo khả năng của thao tác; có thể vẫn rebuild hoặc scan dữ liệu.
- **COPY**: tạo/copy bảng mới và chuyển dữ liệu; thường tốn tài nguyên và ảnh hưởng concurrency nhiều hơn.
- **LOCK=NONE/SHARED/EXCLUSIVE**: chỉ định mức khóa DML được phép trong quá trình thực hiện, trong phạm vi thao tác/version hỗ trợ.

Tên thuật toán không nên được diễn giải quá đơn giản. **INPLACE không có nghĩa không copy dữ liệu**, và **INSTANT chỉ áp dụng cho những thay đổi được hỗ trợ ở phiên bản/định dạng bảng tương ứng**.

Ví dụ thêm index trong MySQL InnoDB:

~~~sql
ALTER TABLE invoice
ADD INDEX idx_invoice_status (status),
ALGORITHM=INPLACE,
LOCK=NONE;
~~~

Câu lệnh minh họa cho một trường hợp MySQL hỗ trợ online index creation. Nếu phiên bản, engine hoặc cấu trúc bảng không hỗ trợ algorithm/lock được yêu cầu, lệnh có thể thất bại. Việc chỉ định rõ tùy chọn là cách tránh âm thầm chấp nhận mức khóa hoặc thuật toán khác ngoài mong muốn; cần xác minh cú pháp và khả năng trên đúng version.

### INSTANT không áp dụng cho mọi ALTER

Thêm cột, đổi kiểu, xóa cột, thay default hoặc thay index có giới hạn khác nhau theo phiên bản MySQL. Một thao tác được hỗ trợ INSTANT ở phiên bản mới có thể phải INPLACE/COPY ở phiên bản cũ. Engine, row format, generated column, index và thuộc tính bảng cũng ảnh hưởng.

Trước khi chọn algorithm:

1. Kiểm tra version server và engine InnoDB.
2. Đọc tài liệu online DDL cho đúng loại ALTER.
3. Thử với schema tương đương và dữ liệu gần quy mô production.
4. Ghi nhận algorithm/lock được chấp nhận.
5. Đặt timeout và theo dõi metadata lock.
6. Nếu không đáp ứng mức online yêu cầu, dừng và lập kế hoạch khác.

### Metadata lock

Ngay cả khi DDL hỗ trợ LOCK=NONE trong phần lớn thời gian, MySQL vẫn cần **metadata lock (MDL)** ở một số giai đoạn. Transaction dài đang truy cập bảng có thể giữ metadata lock và khiến ALTER chờ. Khi DDL chờ, request khác có thể xếp hàng phía sau tùy tình huống.

Kiểm tra processlist, performance_schema metadata_locks hoặc công cụ giám sát được hỗ trợ. Trước khi triển khai, rà soát transaction lâu và connection idle trong transaction.

## 8. MariaDB: không đồng nhất với MySQL

MariaDB có nhiều cơ chế online và instant DDL, nhưng lịch sử phát triển và phạm vi hỗ trợ khác MySQL. Không được giả định:

- Cùng tên ALGORITHM có cùng phạm vi hỗ trợ.
- Cùng câu lệnh ALTER TABLE sẽ dùng cùng đường thực thi.
- Một tính năng INSTANT trong MySQL tồn tại tương tự ở MariaDB.
- Cùng engine/version sẽ có cùng mức lock.
- Driver hoặc Liquibase change type sẽ sinh SQL giống nhau.

Với MariaDB, xác định rõ **server version**, **storage engine**, loại thay đổi, algorithm và lock hỗ trợ. Thử câu lệnh trên đúng version và cấu trúc bảng, đọc output/warning để biết DBMS đã dùng thuật toán nào. Nếu cần đảm bảo fail khi không đạt yêu cầu, dùng cú pháp ép algorithm/lock mà phiên bản hỗ trợ thay vì chấp nhận fallback không được review.

Trong Liquibase, có thể giới hạn changeset bằng `dbms: mariadb` và tách khỏi changeset MySQL. Đừng dùng `dbms: mysql` cho mọi hệ tương thích MySQL mà chưa kiểm tra Liquibase nhận diện MariaDB như thế nào ở phiên bản cụ thể.

## 9. SQL Server: online index operations

SQL Server hỗ trợ online index create/rebuild cho một số loại index và thao tác, nhưng phạm vi phụ thuộc **phiên bản, edition, loại index và thuộc tính bảng**. Một số thao tác online có thể cần edition/license hoặc điều kiện nhất định.

Ví dụ dạng câu lệnh:

~~~sql
CREATE INDEX IX_Invoice_Status
ON dbo.Invoice(Status)
WITH (ONLINE = ON);
~~~

Đây là ví dụ cú pháp; trước khi dùng cần kiểm tra khả năng ONLINE cho version/edition và index type đích. Online operation vẫn có thể cần khóa ngắn ở đầu/cuối, sử dụng thêm dung lượng và tạo tải CPU/I/O. Nếu không hỗ trợ, SQL Server có thể từ chối câu lệnh.

Một số phiên bản và thao tác hỗ trợ **RESUMABLE** cho index operations. Tính năng này có thể cho phép tạm dừng/tiếp tục những thao tác đủ điều kiện, nhưng không phải mọi CREATE/ALTER INDEX đều hỗ trợ và phải xem các giới hạn cụ thể.

Với những thao tác hỗ trợ low-priority wait, có thể thiết kế cách chờ lock để giảm ảnh hưởng workload. Hãy kiểm tra cú pháp và điều kiện áp dụng; không sao chép tùy chọn WAIT_AT_LOW_PRIORITY sang lệnh hoặc version không hỗ trợ.

Trong Liquibase, SQL Server-specific online DDL có thể được khai báo bằng changeset giới hạn `dbms: mssql` và SQL riêng. Tạo rollback tương ứng, thử trên edition/version đích và kiểm tra kết quả qua catalog như sys.indexes, sys.index_columns và metadata liên quan.

## 10. Oracle Database: online DDL và redefinition

Oracle hỗ trợ nhiều thao tác DDL online, chẳng hạn một số thao tác tạo/rebuild index và thay đổi bảng. Đối với thay đổi cấu trúc phức tạp hoặc cần chuyển đổi dữ liệu trong khi vẫn duy trì khả năng truy cập, **DBMS_REDEFINITION** có thể là một công cụ phù hợp trong những điều kiện được hỗ trợ.

Tuy nhiên:

- Tính năng online phụ thuộc phiên bản, loại object, thao tác và một số điều kiện/license.
- Online không loại bỏ mọi lock; có thể cần khóa ở giai đoạn bắt đầu/kết thúc.
- DDL của Oracle có hành vi implicit commit; không coi rollback transaction Liquibase là cách đảo DDL đã commit.
- Reorganization/redefinition có thể cần dung lượng phụ, đồng bộ thay đổi và bước hoàn tất riêng.
- Cần kiểm tra quyền, dependency, trigger, constraint, grants và invalid object sau thao tác.

Ví dụ dạng lệnh tạo index online:

~~~sql
CREATE INDEX idx_invoice_status
ON invoice(status)
ONLINE;
~~~

Đây là minh họa cho cú pháp Oracle ở môi trường hỗ trợ. Không dùng nó như SQL đa DBMS. Trong Liquibase, giới hạn changeset bằng DBMS phù hợp và review SQL rollback; nếu thao tác không thể đảo an toàn, ghi rõ forward-fix/restore plan.

Với thay đổi lớn, hãy xem xét DBMS_REDEFINITION hoặc quy trình online reorganization được DBA phê duyệt thay vì giả định một ALTER TABLE đơn lẻ luôn đáp ứng SLA.

## 11. SQLite: giới hạn online DDL

SQLite có mô hình khóa và concurrency khác các DBMS server lớn. Nó hỗ trợ một số thay đổi schema bằng ALTER TABLE, nhưng nhiều thay đổi phức tạp thường cần **tạo bảng mới, sao chép dữ liệu, xóa bảng cũ và đổi tên bảng mới**.

Một quy trình rebuild table có thể bao gồm:

1. Tạo bảng mới với định nghĩa mong muốn.
2. Copy dữ liệu từ bảng cũ và chuyển đổi giá trị.
3. Kiểm tra số hàng, constraint và index.
4. Thay thế bảng cũ bằng bảng mới theo quy trình được kiểm chứng.
5. Tạo lại index, trigger và view phụ thuộc.
6. Kiểm tra foreign key và trạng thái ứng dụng.

SQLite chỉ cho phép một writer tại một thời điểm; chế độ journal/WAL ảnh hưởng hành vi reader/writer nhưng không biến mọi DDL thành online. Khi rebuild bảng, cần tính thời gian copy, dung lượng, lock và thời gian ứng dụng có thể phải chờ.

Với SQLite, cần xem đúng phiên bản, foreign_keys pragma và cách migration framework thực hiện table rebuild. Liquibase change type có thể sinh SQL khác với quy trình rebuild thủ công; hãy xem update-sql và test trên bản sao.

## 12. DDL trực tuyến và transaction semantics

Online DDL và transactional DDL là hai thuộc tính khác nhau:

- **Online** nói về mức độ cho phép workload đồng thời trong lúc thay đổi.
- **Transactional** nói về khả năng commit/rollback thay đổi theo transaction.
- **Atomic DDL** nói về tính nguyên tử của một thao tác DDL trong một số điều kiện/cơ chế phục hồi của DBMS; nó không nhất thiết cho phép người dùng rollback DDL bằng ROLLBACK.

Ví dụ:

| DBMS/thao tác | Online? | Transaction/rollback |
|---|---|---|
| PostgreSQL CREATE INDEX CONCURRENTLY | Cho phép DML đồng thời ở mức được thiết kế | Không chạy trong transaction block; không rollback như một changeset transaction |
| PostgreSQL ALTER TABLE thông thường | Tùy loại lệnh và lock | Nhiều DDL có thể transactional, nhưng cần xét lệnh cụ thể |
| MySQL InnoDB online ALTER | Tùy algorithm/lock/version | DDL thường implicit commit; không coi như DML transaction |
| SQL Server ONLINE index | Tùy operation/edition/version | Ngữ nghĩa transaction và resumable operation riêng |
| Oracle online DDL | Tùy operation/version/object | DDL implicit commit; cần rollback/forward-fix riêng |
| SQLite schema changes | Khả năng online hạn chế | DDL có thể transactional nhưng concurrency một writer |

Không chuyển một changeset sang `runInTransaction: false` chỉ vì muốn DDL chạy online. Trên PostgreSQL, lựa chọn này cần cho CREATE INDEX CONCURRENTLY do lệnh cấm transaction block. Trên MySQL hoặc Oracle, DDL có implicit commit dù Liquibase yêu cầu transaction; false không làm thao tác trở nên online hoặc reversible.

## 13. Tích hợp online DDL với Liquibase

Liquibase có change type chung như `createIndex`, `addColumn`, `addForeignKeyConstraint` và `addNotNullConstraint`. Những change type này giúp changelog dễ đọc và có thể hỗ trợ nhiều DBMS. Tuy nhiên, chúng không tự động bảo đảm DBMS chọn online algorithm.

Khi cần một cú pháp đặc thù:

- Dùng change type chung nếu SQL được sinh ra đáp ứng yêu cầu.
- Dùng `sql` hoặc `sqlFile` nếu cần chỉ định rõ ONLINE, CONCURRENTLY, ALGORITHM, LOCK hoặc cú pháp riêng.
- Dùng thuộc tính **dbms** để giới hạn changeset theo DBMS.
- Chia changeset theo giai đoạn và theo thao tác.
- Dùng precondition để kiểm tra bảng/cột/index/constraint cần có.
- Viết rollback hoặc mô tả rõ giới hạn không thể đảo.
- Xem `update-sql` để kiểm tra SQL thực tế được sinh ra.

Ví dụ changeset PostgreSQL:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 050-pg-invoice-index-concurrently
      author: platform-team
      dbms: postgresql
      runInTransaction: false
      changes:
        - sql:
            splitStatements: false
            sql: |
              CREATE INDEX CONCURRENTLY idx_invoice_created_at
              ON public.invoice(created_at);
~~~

Ví dụ changeset MySQL:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 051-mysql-invoice-index-online
      author: platform-team
      dbms: mysql
      changes:
        - sql:
            sql: |
              ALTER TABLE invoice
              ADD INDEX idx_invoice_created_at(created_at),
              ALGORITHM=INPLACE,
              LOCK=NONE;
~~~

Câu lệnh MySQL cần được thử trên đúng version/engine. Nếu DBMS không thể đáp ứng algorithm/lock, changeset nên thất bại để nhóm đánh giá lại, không âm thầm chấp nhận một đường thực thi khác.

Đối với MariaDB, SQL Server và Oracle, tạo changeset riêng theo DBMS/version/capability. Không nhét nhiều nhánh SQL vào một changeset khó review nếu chúng có semantics và rollback khác nhau.

### runInTransaction: false có phạm vi hẹp

Chỉ đặt false khi lệnh hoặc executor yêu cầu chạy ngoài transaction block, hoặc có lý do đã được xác minh. Không dùng false như cờ online chung. Với changeset non-transactional:

- Chỉ chứa một thao tác độc lập nếu có thể.
- Xem trước SQL và xác định partial failure.
- Có truy vấn hậu kiểm cụ thể.
- Kiểm tra trạng thái object trước retry.
- Không giả định DATABASECHANGELOG và schema luôn cùng cập nhật nguyên tử.

## 14. Mẫu expand–migrate–contract để giảm downtime

Một thay đổi nguy hiểm thường có thể chia thành nhiều release nhỏ thay vì một ALTER lớn. Mẫu **expand–migrate–contract**:

~~~text
EXPAND
  Thêm cột/bảng/index mới theo cách tương thích
       |
       v
DEPLOY COMPATIBLE APP
  Code đọc/ghi được trạng thái cũ và mới
       |
       v
MIGRATE DATA
  Backfill theo batch, có checkpoint
       |
       v
VERIFY
  Kiểm tra dữ liệu, constraint, index và ứng dụng
       |
       v
CONTRACT
  Bỏ cột/đường truy cập cũ khi không còn consumer
~~~

Ví dụ đổi `customer.full_name` thành `display_name`:

1. Thêm `display_name` nullable.
2. Deploy code ghi cả hai cột trong giai đoạn tương thích.
3. Backfill display_name theo batch từ full_name.
4. Kiểm tra số lượng NULL và giá trị không khớp.
5. Chuyển code đọc sang display_name.
6. Sau khi mọi consumer cũ đã được loại bỏ, mới cân nhắc xóa full_name ở release sau.

Cách này giảm áp lực phải thực hiện một migration phá hủy ngay trong một cửa sổ ngắn. Tuy nhiên, nó cần quản lý thời gian tồn tại hai cấu trúc và tránh hai nguồn dữ liệu mâu thuẫn.

## 15. Backfill dữ liệu lớn không phải online DDL

Một UPDATE hàng chục triệu hàng có thể gây lock, transaction log/WAL lớn và replication lag, dù nó không phải DDL. Không nên coi việc thêm `runInTransaction: false` là cách chia batch.

Một backfill an toàn thường có:

- Phạm vi rõ ràng, ví dụ tenant hoặc khoảng ID.
- Batch size và tốc độ có thể điều chỉnh.
- Điều kiện idempotent, chạy lại không làm sai dữ liệu.
- Checkpoint để biết batch nào đã hoàn thành.
- Giới hạn số lần retry và xử lý deadlock.
- Theo dõi replication lag, transaction age và dung lượng log.
- Hậu kiểm số hàng và quy tắc dữ liệu.
- Kế hoạch dừng/tiếp tục mà không khóa toàn bảng lâu.

Ví dụ ý tưởng batch:

~~~sql
UPDATE invoice
SET status = 'OPEN'
WHERE id > :last_id
  AND id <= :next_id
  AND status IS NULL;
~~~

Đây là SQL minh họa cho một worker điều phối batch; cú pháp bind parameter tùy ứng dụng. Liquibase có thể quản lý changeset tạo schema hỗ trợ, còn backfill kéo dài có thể phù hợp hơn với job dữ liệu riêng có checkpoint. Nếu đặt trong changeset, phải đánh giá thời gian, transaction và khả năng retry.

## 16. Preflight trước online DDL

Một migration online vẫn cần gate trước khi chạy. Checklist preflight:

**Database identity**
- Xác nhận đúng host/database/schema/role.
- Xác nhận DBMS, version, edition và storage engine.
- Xác nhận Liquibase/JDBC version và changelog commit.

**Schema/data**
- Bảng/cột/constraint hiện tại đúng giả định.
- Index cùng tên chưa tồn tại hoặc đã được phân loại.
- Dữ liệu đáp ứng điều kiện thêm constraint.
- Dependency của view, trigger, FK và ứng dụng đã được kiểm tra.

**Workload**
- Ước lượng kích thước bảng và thời gian.
- Kiểm tra transaction dài, lock wait và job nền.
- Xem connection pool, traffic peak và maintenance window.
- Kiểm tra replica lag/CDC/downstream consumer.

**Tài nguyên**
- Dung lượng đĩa và temporary space.
- CPU, I/O và transaction log/WAL/redo capacity.
- Dung lượng dự phòng cho index hoặc table copy.
- Tốc độ backup và khả năng restore.

**Vận hành**
- Có owner migration duy nhất.
- Có lock/timeout policy.
- Có kế hoạch dừng hoặc retry.
- Có rollback/forward-fix và backup/PITR phù hợp.
- Có postflight query và ngưỡng PASS/FAIL.

Nếu không thể xác nhận một điều kiện quan trọng, dừng trước khi chạy DDL. Không dùng online option để bù cho việc chưa hiểu quy mô dữ liệu hoặc dependency.

## 17. Theo dõi trong khi DDL chạy

Trong lúc migration, theo dõi:

- Thời gian đã chạy và trạng thái tiến trình.
- Lock đang chờ, lock đang giữ và transaction cũ.
- CPU, I/O, disk growth và temporary space.
- WAL/redo/binlog/transaction log growth.
- Replication lag và độ trễ CDC.
- Request latency, timeout, deadlock và error rate.
- Tình trạng index/constraint đang được xây dựng hoặc validate.

Đặt ngưỡng dừng cụ thể, ví dụ replication lag vượt giới hạn SLA, disk free dưới ngưỡng an toàn hoặc request error tăng mạnh. Ngưỡng phải phù hợp hệ thống, không dùng một con số chung cho mọi database.

Không kill session hoặc giải phóng Liquibase lock chỉ vì migration chạy lâu. Xác minh session đang thực thi DDL, trạng thái transaction và hậu quả hủy lệnh trên DBMS đó. Một số thao tác có thể mất nhiều thời gian để rollback/cleanup hoặc để lại object trung gian.

## 18. Postflight: chứng minh thay đổi đã đạt

Sau khi DDL kết thúc, kiểm tra **cấu trúc, tính hợp lệ, dữ liệu và hành vi ứng dụng**.

Ví dụ kiểm tra index PostgreSQL:

~~~sql
SELECT
    indexrelid::regclass AS index_name,
    indisready,
    indisvalid
FROM pg_index
WHERE indexrelid = 'public.idx_invoice_status_created'::regclass;
~~~

Kỳ vọng index tồn tại, ready và valid. Nếu query không tìm thấy object hoặc object invalid, migration chưa đạt.

Với MySQL, kiểm tra information_schema.statistics và metadata phù hợp để xác nhận index/cột. Với SQL Server, xem sys.indexes và sys.index_columns; với Oracle, xem ALL_INDEXES/ALL_IND_COLUMNS và trạng thái tương ứng. Metadata query cần được viết riêng theo DBMS.

Với constraint:

- Xác nhận tên, cột và trạng thái validation.
- Kiểm tra dữ liệu không vi phạm.
- Thử DML hợp lệ và không hợp lệ trên database test.
- Xác nhận ứng dụng dùng role runtime có thể thao tác.

Sau đó đọc DATABASECHANGELOG để xác nhận changeset được ghi nhận đúng id/author/path và checksum. Lịch sử Liquibase không thay thế hậu kiểm object thực tế; cả hai phải được đối chiếu.

## 19. Rollback và phục hồi với online DDL

Khả năng online không nói lên khả năng rollback. Một thao tác có thể chạy đồng thời tốt nhưng không đảo được tự động hoặc cần thao tác phục hồi riêng.

| Loại thay đổi | Hướng phục hồi cần xem xét |
|---|---|
| Tạo index | Drop index nếu an toàn; kiểm tra index invalid/active và dependency |
| Thêm cột nullable | Có thể giữ lại trong forward-fix; drop chỉ khi không có code/data phụ thuộc |
| Backfill dữ liệu | Cần lưu giá trị cũ hoặc có logic đảo; nếu không, forward-fix/restore |
| Thêm FK NOT VALID rồi VALIDATE | Có thể drop constraint nếu rollback được phê duyệt và không ảnh hưởng integrity |
| Đổi kiểu dữ liệu | Chuyển ngược có thể mất precision/truncate; cần kiểm tra dữ liệu |
| Rebuild/copy table | Cần backup/restore và xác minh trigger/index/permission/dependency |

Với DBMS có implicit commit, Liquibase rollback transaction không thể đảo DDL đã commit. Với changeset `runInTransaction: false`, một phần thay đổi có thể tồn tại khi lệnh thất bại. Không retry mù; đối chiếu object metadata và DATABASECHANGELOG trước.

Nếu rollback gây rủi ro dữ liệu hoặc tương thích, cân nhắc **forward-fix** để đưa schema đến trạng thái đúng. Với thay đổi phá hủy, cần backup/PITR đã được thử và RPO/RTO rõ ràng.

## 20. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách tránh |
|---|---|---|
| Nghĩ ONLINE/CONCURRENTLY là không lock | Request vẫn có thể chờ metadata/DDL lock | Kiểm tra lock mode và timeout |
| Dùng INPLACE như đồng nghĩa không rebuild | Bảng có thể vẫn bị rebuild/scan | Đọc algorithm cụ thể của operation/version |
| Dùng runInTransaction=false để bật online | DDL vẫn chạy theo semantics DBMS; mất atomicity của changeset | Chỉ dùng false khi lệnh yêu cầu |
| Chạy DDL online trên version chưa hỗ trợ | Lỗi hoặc fallback không mong muốn | Pin version và test đúng môi trường |
| Thêm constraint trước khi làm sạch dữ liệu | DDL fail hoặc kéo dài validation | Preflight data và chia giai đoạn |
| Backfill toàn bảng trong một transaction dài | Lock/log/replication lag tăng | Batch, checkpoint và rate limit |
| Retry CREATE INDEX CONCURRENTLY sau lỗi | Đụng index invalid còn sót | Kiểm tra metadata trước retry |
| Chỉ xem DATABASECHANGELOG | Lịch sử có thể đúng nhưng object đã drift | Postflight metadata và data |
| Không thử trên dữ liệu gần production | Thời gian/lock khác xa dự đoán | Dùng bản sao hoặc dữ liệu tương đương |
| Không có kế hoạch phục hồi | DDL đã commit nhưng không thể rollback | Forward-fix/backup/PITR và runbook |

## 21. Ma trận lựa chọn cho một số thay đổi phổ biến

| Thay đổi | PostgreSQL | MySQL/MariaDB | SQL Server | Oracle | SQLite |
|---|---|---|---|---|---|
| Tạo index trên bảng lớn | Xem xét CONCURRENTLY | Xem xét online DDL/algorithm | Xem xét ONLINE nếu hỗ trợ | Xem xét ONLINE nếu hỗ trợ | Thường cần cửa sổ khóa/ghi |
| Thêm cột nullable | ALTER với lock phù hợp; kiểm tra default | Có thể INSTANT tùy operation/version | Thường nhanh nhưng vẫn kiểm tra lock | Có thể online tùy thao tác | ALTER hỗ trợ hạn chế theo version |
| Thêm FK trên bảng lớn | NOT VALID rồi VALIDATE | Khả năng online phụ thuộc version/engine | Kiểm tra lock/validation và options | Kiểm tra validation/online options | Có thể cần rebuild/kiểm tra riêng |
| Đổi kiểu cột lớn | Có thể rewrite hoặc lock tùy kiểu | Có thể INPLACE/COPY/INSTANT tùy kiểu | Có thể cần schema modification lock | Tùy datatype và online operation | Thường rebuild table |
| Xóa cột | ALTER cần lock; kiểm tra dependency | INSTANT/INPLACE tùy version | Kiểm tra dependency/lock | Kiểm tra dependency/DDL | Có thể hỗ trợ hoặc rebuild tùy version |

Bảng là định hướng lựa chọn, không phải ma trận hỗ trợ chính thức. Trước mỗi release, tra tài liệu DBMS đúng phiên bản và thử câu lệnh thực tế. Đặc biệt với thay đổi kiểu dữ liệu, collation, partition, generated column hoặc constraint, kết quả có thể khác đáng kể.

## 22. Quy trình thiết kế changeset online DDL

Một quy trình nhất quán:

1. **Mô tả mục tiêu:** thay đổi schema nào, vì sao cần online, SLA và mức gián đoạn chấp nhận được.
2. **Xác định nền tảng:** DBMS, version, edition, engine, Liquibase/JDBC.
3. **Đánh giá operation:** algorithm, lock mode, copy/rebuild, metadata lock và transaction semantics.
4. **Chia giai đoạn:** expand, migrate, verify, contract nếu cần.
5. **Viết changeset:** dbms-specific khi cần, precondition, runInTransaction đúng, một thao tác rõ ràng.
6. **Viết rollback/forward-fix:** đánh giá khả năng phục hồi dữ liệu và object.
7. **Preview:** validate và update-sql, review câu SQL thực tế.
8. **Test:** chạy trên database tương đương kích thước/workload và kiểm tra failure path.
9. **Preflight production:** identity, backup, lock, resource, replication, maintenance window.
10. **Deploy:** một owner migration, giám sát tiến trình và ngưỡng dừng.
11. **Postflight:** schema/data/history/app smoke tests.
12. **Record:** lưu release, changelog commit, DBMS/version, kết quả và snapshot/evidence nếu có.

Ví dụ gate dạng giả mã:

~~~text
assert target_identity == approved_target
assert dbms_version in tested_matrix
assert changelog_validate == PASS
assert online_ddl_capability == VERIFIED
assert data_preconditions == PASS
assert backup_or_forward_fix == READY
assert sql_preview == REVIEWED

run_liquibase_update()

assert object_metadata == EXPECTED
assert data_postconditions == PASS
assert databasechangelog == EXPECTED
assert application_smoke_test == PASS
~~~

Nếu bất kỳ gate bắt buộc nào FAIL, dừng rollout và phân loại sự cố. Không tự động bỏ qua precondition hoặc đánh dấu MARK_RAN để pipeline tiếp tục.

## 23. Checklist trước khi phát hành

**Thiết kế và tương thích**

- [ ] Đã xác định DBMS/version/edition/engine.
- [ ] Đã kiểm tra thao tác online cụ thể, không chỉ tên tính năng.
- [ ] Đã hiểu algorithm, lock mode, metadata lock và khả năng copy/rebuild.
- [ ] Đã đánh giá kích thước bảng, dữ liệu, index và dependency.
- [ ] Đã xác định transaction/implicit commit và runInTransaction.
- [ ] Đã tách DDL khỏi backfill dài nếu cần.
- [ ] Đã bảo đảm ứng dụng cũ/mới tương thích trong từng giai đoạn.

**Vận hành**

- [ ] Preflight xác nhận đúng target, quyền, backup và resource.
- [ ] Có lock timeout/statement timeout và ngưỡng dừng.
- [ ] Có kế hoạch theo dõi CPU, I/O, disk, log và replication lag.
- [ ] Có một tiến trình migration owner và DATABASECHANGELOGLOCK được kiểm soát.
- [ ] Đã thử migration trên DBMS/version và quy mô gần production.
- [ ] Đã xem update-sql và review changeset/rollback.

**Xác minh và phục hồi**

- [ ] Có postflight query cho index/constraint/table/object.
- [ ] Kiểm tra dữ liệu và quyền runtime.
- [ ] Đối chiếu DATABASECHANGELOG/checksum với object thực tế.
- [ ] Có quy trình xử lý partial failure và retry.
- [ ] Rollback hoặc forward-fix đã được đánh giá.
- [ ] Backup/PITR được xác minh cho thay đổi có nguy cơ mất dữ liệu.
- [ ] Lưu release evidence và kết quả vận hành.

Với **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, triển khai DDL an toàn bắt đầu bằng việc hiểu chính xác khả năng của DBMS và phiên bản đích. PostgreSQL CONCURRENTLY, MySQL/MariaDB ALGORITHM/LOCK, SQL Server ONLINE/RESUMABLE, Oracle online DDL và SQLite table rebuild có ngữ nghĩa khác nhau về lock, tài nguyên và phục hồi. Liquibase giúp quản lý thay đổi qua changeset, precondition, checksum và lịch sử; nó không thể biến một DDL không hỗ trợ thành online. Khi kết hợp SQL đúng nền tảng, rollout expand–migrate–contract, kiểm tra trước/sau, giám sát và kế hoạch forward-fix/restore, nhóm có thể giảm thời gian gián đoạn mà vẫn kiểm soát được trạng thái database trong từng lần phát hành.
