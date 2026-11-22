# DDL, sequence, large object và các giới hạn cần xử lý riêng trong PostgreSQL

Logical backup của PostgreSQL lưu cấu trúc và dữ liệu ở mức database objects thay vì sao chép trực tiếp các data files. Công cụ chính là pg_dump, pg_restore và pg_dumpall. Cách tiếp cận này linh hoạt khi cần di chuyển database, khôi phục một schema/table hoặc nâng cấp giữa các major version.

Tuy nhiên, một logical dump không phải lúc nào cũng là bản sao đầy đủ của mọi thứ mà ứng dụng cần. DDL có dependency và thứ tự thực thi; sequence có trạng thái riêng không tuân theo MVCC; large object được lưu tách khỏi các hàng thông thường; roles và tablespaces là global objects; extension, foreign data và cấu hình hệ điều hành có thể cần chuẩn bị riêng.

~~~text
PostgreSQL database
       |
       +-------------------------------+
       |                               |
       v                               v
  Schema / DDL                    Data objects
  - schemas                       - table rows
  - types/domains                 - sequence values
  - functions                     - large objects
  - tables/views                  - data-only sections
  - indexes/constraints
  - triggers/policies
       |                               |
       +---------------+---------------+
                       |
                       v
                   pg_dump
                       |
             +---------+---------+
             |         |         |
             v         v         v
           Plain     Custom    Directory
           SQL       archive   archive
             |         |         |
           psql     pg_restore pg_restore
                       |
                       v
                Target database
                       |
          +------------+-------------+
          |            |             |
          v            v             v
       Roles       Extensions    External systems
       /tablespace  /libraries   /files /secrets
       globals      /versions    /remote data
~~~

Bài này thuộc chương **Sao chép logic** của module *Database Engine Relational PostgreSQL*, tập trung vào những phần cần chú ý khi dump/restore DDL, sequence, large object và các giới hạn của logical backup.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích phạm vi của logical backup và sự khác nhau giữa pg_dump, pg_restore và pg_dumpall.
2. Phân biệt schema-only, data-only và full logical dump.
3. Chọn plain, custom, directory hoặc tar format.
4. Hiểu thứ tự pre-data, data và post-data khi restore.
5. Phân tích dependency giữa schema, type, function, table, sequence, index và constraint.
6. Nhận biết những global objects không nằm trong một pg_dump thông thường.
7. Sao lưu và khôi phục roles, tablespaces bằng pg_dumpall --globals-only.
8. Hiểu vì sao extension cần package/binary tương thích ở target.
9. Giải thích sequence state, nextval, setval và đặc tính không transactional.
10. Đồng bộ sequence sau khi nạp dữ liệu hoặc nhập một phần bảng.
11. Phân biệt large object với bytea và OID thông thường.
12. Đảm bảo large objects được đưa vào dump khi dùng các tùy chọn chọn lọc.
13. Nhận diện orphan large objects và vấn đề quyền truy cập.
14. Hiểu giới hạn của pg_dump theo database, table/schema và dependency.
15. Xử lý foreign tables, FDW, credentials và dữ liệu nằm ngoài PostgreSQL.
16. Chọn phiên bản client/server phù hợp khi dump và restore.
17. Dùng pg_restore để xem nội dung archive và điều khiển thứ tự/đối tượng restore.
18. Xác minh logical backup bằng thử restore và kiểm tra dữ liệu.
19. Thiết kế quy trình migration có downtime, consistency và rollback rõ ràng.
20. Nhận diện các giới hạn cần xử lý riêng trước khi coi logical dump là bản backup hoàn chỉnh.

## 2. Logical backup là gì?

Logical backup biểu diễn database bằng các câu lệnh SQL và/hoặc một archive có cấu trúc chứa định nghĩa object cùng dữ liệu. Khi restore, PostgreSQL tạo lại object rồi nạp dữ liệu vào database đích.

### 2.1. Logical objects

Một database có nhiều loại object:

- Schema và namespace.
- Tables, partitioned tables, views và materialized views.
- Sequences và identity columns.
- Types, domains, enums và composite types.
- Functions, procedures, operators và aggregates.
- Indexes, constraints, triggers và rules.
- Policies và grants.
- Large objects.
- Extension declarations và một số database-level settings.

### 2.2. Logical dump

pg_dump kết nối tới một database và tạo dump của database đó. Có thể chọn toàn database, schema, table, section hoặc object theo tùy chọn.

### 2.3. Logical restore

Plain SQL dump được thực thi bằng psql. Custom, directory và tar archives được xử lý bằng pg_restore.

### 2.4. Logical backup không sao chép nguyên PGDATA

Dump không phải bản copy vật lý của data directory. Nó tái tạo objects qua DDL và nạp dữ liệu qua các cơ chế logical.

### 2.5. Khả năng portability

Logical dump thường linh hoạt hơn physical backup khi di chuyển dữ liệu giữa các môi trường hoặc major versions, nhưng SQL, extension, collations và tính năng mới vẫn có thể không tương thích với target cũ.

## 3. pg_dump, pg_restore và pg_dumpall

| Công cụ | Nhiệm vụ | Input/Output |
| --- | --- | --- |
| pg_dump | Dump một database | Server → dump file |
| pg_restore | Restore hoặc liệt kê archive không phải plain | Archive → target server hoặc SQL |
| pg_dumpall | Dump toàn cluster ở mức logical | Server → SQL script |
| psql | Chạy plain SQL dump | SQL script → database |
| pg_verifybackup | Verify physical backup manifest | Physical backup directory |

### 3.1. pg_dump

Dùng khi cần sao lưu một database cụ thể:

~~~bash
pg_dump -h db.example.internal -U backup_user \
  -d appdb -Fc -f appdb.dump
~~~

### 3.2. pg_restore

Dùng với custom, directory và tar archives:

~~~bash
pg_restore -h target.example.internal -U restore_user \
  -d appdb --verbose appdb.dump
~~~

### 3.3. pg_dumpall

Dump nhiều database và global objects:

~~~bash
pg_dumpall -h db.example.internal -U backup_user \
  -f cluster.sql
~~~

### 3.4. Global objects

Một pg_dump thông thường không sao lưu toàn bộ cluster-level roles và tablespaces. Dùng:

~~~bash
pg_dumpall --globals-only -h db.example.internal \
  -U backup_user -f globals.sql
~~~

### 3.5. Chỉ dump roles

~~~bash
pg_dumpall --roles-only -h db.example.internal \
  -U backup_user -f roles.sql
~~~

Tùy chọn cụ thể có thể thay đổi theo phiên bản. Dùng pg_dumpall --help của client đang cài.

### 3.6. Backup database và globals thành hai artifact

Trong môi trường vận hành, có thể lưu từng database dump cùng một globals dump. Cách này giúp kiểm soát restore order và phân quyền tốt hơn, nhưng cần giữ chúng cùng một backup set.

## 4. Plain SQL và archive formats

pg_dump hỗ trợ nhiều output format.

### 4.1. Plain format

~~~bash
pg_dump -d appdb -Fp -f appdb.sql
~~~

Plain format là SQL script có thể đọc được. Restore bằng psql:

~~~bash
psql -X -v ON_ERROR_STOP=1 -d appdb -f appdb.sql
~~~

### 4.2. Custom format

~~~bash
pg_dump -d appdb -Fc -f appdb.dump
~~~

Custom format lưu archive riêng của PostgreSQL. Có thể xem danh sách nội dung, chọn object và restore song song bằng pg_restore.

### 4.3. Directory format

~~~bash
pg_dump -d appdb -Fd -j 4 -f appdb_dir
~~~

Directory format tạo nhiều file trong một thư mục và hỗ trợ parallel dump. Nó hữu ích cho database lớn hoặc khi muốn tăng throughput.

### 4.4. Tar format

~~~bash
pg_dump -d appdb -Ft -f appdb.tar
~~~

Tar format đóng gói các thành phần dump vào một archive tar. Restore bằng pg_restore.

### 4.5. So sánh

| Format | Dễ đọc | Chọn object khi restore | Parallel dump | Parallel restore |
| --- | --- | --- | --- | --- |
| Plain | Có | Qua chỉnh sửa/script | Không | Không qua pg_restore |
| Custom | Không | Có | Không | Có |
| Directory | Không | Có | Có | Có |
| Tar | Không | Có | Không | Không hỗ trợ parallel restore như custom/directory |

### 4.6. Chọn format

- Plain phù hợp khi cần SQL script dễ đọc, chỉnh sửa và lưu trong workflow migration.
- Custom phù hợp với backup thông dụng cần chọn object/parallel restore.
- Directory phù hợp database lớn cần parallel dump và restore.
- Tar phù hợp khi cần archive dạng tar hoặc pipeline lưu trữ tương thích.

### 4.7. Không dùng psql cho custom archive

Custom/directory/tar không phải plain SQL script. Dùng pg_restore để đọc và phục hồi đúng format.

## 5. Snapshot consistency của pg_dump

Một điểm mạnh của pg_dump là tạo dump nhất quán trong khi database vẫn có thể phục vụ truy vấn và ghi.

### 5.1. MVCC snapshot

pg_dump dùng một snapshot để đọc dữ liệu ở một trạng thái nhất quán. Những thay đổi commit sau snapshot không xuất hiện trong table data của dump đó.

### 5.2. Ghi vẫn tiếp tục

Ứng dụng có thể tiếp tục INSERT/UPDATE/DELETE trong khi dump chạy. pg_dump không yêu cầu dừng toàn bộ writes cho một dump database thông thường.

### 5.3. DDL concurrent

pg_dump lấy lock phù hợp để bảo vệ các object đang dump. DDL đồng thời có thể chờ lock hoặc khiến dump gặp lỗi nếu object bị thay đổi/xóa trong quá trình thực hiện. Nên tránh deploy DDL lớn cùng lúc backup.

### 5.4. Parallel dump

Directory format với -j sử dụng synchronized snapshots để các worker đọc cùng một trạng thái dữ liệu. Server cần hỗ trợ cơ chế snapshot đồng bộ tương ứng.

### 5.5. Sequence là ngoại lệ quan trọng

Sequence state không tuân theo MVCC snapshot giống table rows. Giá trị sequence có thể thay đổi trong khi dump. Vì vậy, dump table data nhất quán không đồng nghĩa mọi sequence value phản ánh chính xác cùng một instant.

### 5.6. pg_dumpall không phải một snapshot cluster-wide duy nhất

pg_dumpall gọi các thao tác dump cho từng database. Các database có thể được dump ở những thời điểm khác nhau. Nếu ứng dụng có invariant xuyên database, cần quiesce writes hoặc chọn một chiến lược backup phù hợp khác.

## 6. Dump toàn database, schema hoặc table

### 6.1. Dump toàn database

~~~bash
pg_dump -Fc -d appdb -f appdb.dump
~~~

Đây là cách đơn giản nhất để giữ các objects và dữ liệu trong một database.

### 6.2. Schema-only

~~~bash
pg_dump -s -d appdb -f appdb_schema.sql
~~~

Chỉ dump definitions, không dump table data và sequence current values như một data backup.

### 6.3. Data-only

~~~bash
pg_dump -a -d appdb -Fc -f appdb_data.dump
~~~

Chỉ dump dữ liệu. Target phải có schema tương thích hoặc schema được restore trước.

### 6.4. Dump một schema

~~~bash
pg_dump -n app -Fc -d appdb -f app_schema.dump
~~~

### 6.5. Dump một table

~~~bash
pg_dump -t 'app.orders' -Fc -d appdb -f orders.dump
~~~

### 6.6. Nhiều table

Có thể lặp lại -t cho các table cần chọn. Dùng pattern chính xác và kiểm tra danh sách object trước khi thực hiện.

### 6.7. Table selection không tự kéo theo mọi dependency

Dump một table không bảo đảm tự động bao gồm mọi type, function, sequence, schema hoặc object mà table phụ thuộc. Phải xác định dependency và dump/restore chúng riêng.

### 6.8. Schema selection có giới hạn

Chọn một schema không tự động bao gồm mọi object bên ngoài schema mà object được chọn tham chiếu. Ví dụ function dùng type ở schema khác hoặc foreign server ở cluster khác.

## 7. DDL và thứ tự tạo object

DDL mô tả cấu trúc database. Các object thường phụ thuộc lẫn nhau, nên restore cần thứ tự phù hợp.

### 7.1. Dependency graph

Ví dụ một bảng orders phụ thuộc schema, enum type, sequence, function và extension:

~~~text
Extension / Type / Schema
          |
          v
      Sequence
          |
          v
       Table
          |
     +----+-----+
     |          |
     v          v
   Index     Constraint
     |          |
     +-----+----+
           |
           v
        Trigger
           |
           v
        Application
~~~

### 7.2. Schema

Schema là namespace chứa objects. Tạo schema trước khi tạo các object bên trong.

### 7.3. Types và domains

Table column có thể dùng enum, domain, composite type hoặc range type. Các type cần tồn tại trước khi tạo table phụ thuộc.

### 7.4. Functions và procedures

Default expressions, generated expressions, triggers và views có thể gọi functions. Restore cần có function trước object tham chiếu khi dependency yêu cầu.

### 7.5. Tables và partitions

Tạo table/partitioned table trước khi nạp dữ liệu. Partition attachment và constraints có thể thuộc giai đoạn post-data.

### 7.6. Indexes và constraints

Indexes và một số constraints thường được tạo sau khi nạp dữ liệu để giảm chi phí restore. PostgreSQL archive chia các thành phần theo sections để hỗ trợ thứ tự.

### 7.7. Triggers và rules

Triggers có thể thực thi khi data được nạp. Restore tooling quản lý thứ tự phù hợp; khi viết migration thủ công, cần cân nhắc trigger behavior và side effects.

## 8. Các sections của archive

pg_dump/pg_restore chia archive thành ba section logic:

| Section | Nội dung điển hình |
| --- | --- |
| pre-data | Schema, types, functions, tables và object definitions cần trước data |
| data | Table data, large objects và sequence values |
| post-data | Indexes, triggers, rules và constraints được tạo sau data |

### 8.1. Pre-data

~~~bash
pg_dump -Fc -d appdb --section=pre-data -f pre.dump
~~~

Section này chứa các định nghĩa cần có trước khi nạp dữ liệu.

### 8.2. Data

~~~bash
pg_dump -Fc -d appdb --section=data -f data.dump
~~~

Section data chứa table data và các thành phần dữ liệu như sequence values/large objects theo phạm vi dump.

### 8.3. Post-data

~~~bash
pg_dump -Fc -d appdb --section=post-data -f post.dump
~~~

Section này thường chứa indexes, triggers và constraints cần được thêm sau khi nạp dữ liệu.

### 8.4. Xem TOC

~~~bash
pg_restore --list appdb.dump
~~~

TOC (table of contents) liệt kê các archive entries. Có thể lưu ra file, chỉnh sửa danh sách restore hoặc dùng -L để chỉ restore các entries được chọn.

### 8.5. Không tùy tiện thay đổi thứ tự

Nếu restore thủ công từng section, phải giữ dependency. Nạp data trước khi tạo type/table hoặc restore constraint khi dữ liệu chưa thỏa có thể gây lỗi.

## 9. Restore bằng pg_restore

### 9.1. Restore vào database đã tạo

~~~bash
createdb -h target.example.internal -U admin appdb_restore

pg_restore -h target.example.internal -U restore_user \
  -d appdb_restore --verbose appdb.dump
~~~

### 9.2. Tạo database từ archive

~~~bash
pg_restore -h target.example.internal -U admin \
  -C -d postgres appdb.dump
~~~

-C yêu cầu tạo database theo metadata archive. Kết nối -d postgres là database đích ban đầu để chạy CREATE DATABASE.

### 9.3. Clean trước khi restore

~~~bash
pg_restore --clean --if-exists \
  -d appdb_restore appdb.dump
~~~

--clean xóa các objects sẽ được restore trước khi tạo lại. Đây là thao tác có thể xóa dữ liệu hiện tại; chỉ dùng trên database đích đã xác nhận.

### 9.4. Parallel restore

~~~bash
pg_restore -j 4 -d appdb_restore appdb.dump
~~~

Parallel restore hỗ trợ custom và directory archives. Nó có thể tăng tốc nhưng cần tài nguyên CPU, I/O và connections.

### 9.5. Exit on error

~~~bash
pg_restore --exit-on-error -d appdb_restore appdb.dump
~~~

Giúp dừng khi gặp lỗi thay vì tiếp tục tạo một trạng thái restore không đầy đủ mà không được chú ý.

### 9.6. Plain SQL restore

~~~bash
psql -X -v ON_ERROR_STOP=1 \
  -h target.example.internal -U restore_user \
  -d appdb_restore -f appdb.sql
~~~

-X tránh nạp psqlrc cá nhân làm thay đổi hành vi script; ON_ERROR_STOP giúp trả lỗi khi một lệnh SQL thất bại.

### 9.7. Single transaction

Với restore nhỏ, có thể dùng chế độ single transaction phù hợp của pg_restore hoặc psql. Không phải mọi option đều tương thích với parallel restore; kiểm tra help theo phiên bản.

## 10. Ownership, privileges và global objects

Một logical dump có thể chứa owner và ACL, nhưng role tương ứng phải tồn tại ở target.

### 10.1. Owner

Khi restore, các lệnh ALTER OWNER có thể thất bại nếu role không tồn tại.

### 10.2. ACL

GRANT/REVOKE tham chiếu role và objects. Nếu role thiếu, restore có thể lỗi ở phần privileges.

### 10.3. Globals

Dùng pg_dumpall --globals-only để dump roles và tablespaces:

~~~bash
pg_dumpall --globals-only -h db.example.internal \
  -U backup_user -f globals.sql
~~~

### 10.4. Restore globals trước

Thông thường cần tạo roles và tablespaces trước khi restore database có owner, grants hoặc object nằm trong tablespace đó.

~~~bash
psql -X -v ON_ERROR_STOP=1 -d postgres -f globals.sql
~~~

Thực hiện bằng account có quyền phù hợp và review nội dung globals trước khi áp dụng.

### 10.5. Bỏ owner

Nếu target dùng role mapping khác, có thể restore với:

~~~bash
pg_restore --no-owner -d appdb_restore appdb.dump
~~~

Khi bỏ owner, objects thường được tạo dưới role thực hiện restore. Phải xác định owner đích sau đó.

### 10.6. Bỏ privileges

~~~bash
pg_restore --no-acl -d appdb_restore appdb.dump
~~~

Chỉ dùng khi quyền sẽ được cấp lại bằng một quy trình khác. Không bỏ ACL rồi quên khôi phục security model.

### 10.7. Password hashes

Globals dump có thể chứa role definitions và password hashes tùy quyền/cấu hình. Bảo vệ file như secret; không gửi vào chat/log hoặc repository công khai.

## 11. Sequence là gì?

Sequence là object tạo ra chuỗi số theo yêu cầu, thường dùng làm khóa chính hoặc số định danh.

~~~sql
CREATE SEQUENCE app.orders_id_seq
    AS bigint
    START WITH 1
    INCREMENT BY 1
    CACHE 20;
~~~

Lấy giá trị:

~~~sql
SELECT nextval('app.orders_id_seq');
~~~

### 11.1. Serial

Cột serial là shorthand tạo integer column, sequence và default gọi nextval, đồng thời gắn sequence ownership với column.

### 11.2. Identity

Identity column dùng sequence nội bộ theo SQL standard syntax:

~~~sql
CREATE TABLE app.orders (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    description text
);
~~~

### 11.3. Sequence độc lập

Sequence có thể được dùng cho nhiều bảng hoặc mục đích khác, không nhất thiết là sequence sở hữu bởi một column.

### 11.4. nextval

nextval() cấp một giá trị mới và thao tác này có tính atomic giữa các session.

### 11.5. currval

currval() trả giá trị sequence gần nhất mà session hiện tại đã lấy bằng nextval.

### 11.6. setval

setval() đặt trạng thái sequence. Nó thường được dùng khi import dữ liệu hoặc cần đồng bộ sequence với các ID đã nạp.

## 12. Vì sao sequence cần xử lý riêng khi backup?

Sequence không hoạt động giống một bảng thông thường.

### 12.1. Sequence không theo MVCC snapshot

Các thay đổi sequence không được rollback theo transaction như table updates và không tuân theo snapshot isolation theo cùng cách. Một pg_dump có snapshot nhất quán cho table data nhưng sequence có thể đã tiến thêm trong lúc dump.

### 12.2. Sequence có thể có gaps

Giá trị bị cấp phát có thể không được dùng vì transaction rollback, crash hoặc cache. Sequence không bảo đảm số liên tiếp không có khoảng trống.

### 12.3. Cache

Sequence có thể cache nhiều giá trị cho session. last_value không nhất thiết bằng ID lớn nhất đã commit trong bảng.

### 12.4. Data dump và sequence state

pg_dump lưu sequence definitions trong schema và sequence values trong phần data khi dump bao gồm data. Schema-only dump không phải bản lưu current sequence state.

### 12.5. Data-only dump

Data-only dump có thể ghi các giá trị sequence để đồng bộ sau khi nạp table rows, tùy phạm vi objects được chọn.

### 12.6. Dump một table

Nếu chỉ dump table mà không bao gồm sequence liên quan, dữ liệu có thể được restore nhưng sequence không tự động ở đúng vị trí. Xác định sequence được column sử dụng và đưa nó vào backup/migration.

## 13. Kiểm tra sequence và quan hệ với column

### 13.1. Tìm sequence gắn với serial/identity

~~~sql
SELECT pg_get_serial_sequence('app.orders', 'id');
~~~

Hàm trả tên sequence được sở hữu bởi column, bao gồm serial/identity khi quan hệ ownership tồn tại.

### 13.2. Liệt kê sequence

~~~sql
SELECT
    schemaname,
    sequencename,
    data_type,
    start_value,
    min_value,
    max_value,
    increment_by,
    cycle,
    cache_size,
    last_value
FROM pg_sequences
WHERE schemaname = 'app'
ORDER BY sequencename;
~~~

Một số thông tin có thể null nếu role không có quyền hoặc sequence chưa được gọi. Cột và view details có thể khác theo version.

### 13.3. Kiểm tra identity

~~~sql
SELECT
    table_schema,
    table_name,
    column_name,
    is_identity,
    identity_generation,
    column_default
FROM information_schema.columns
WHERE table_schema = 'app'
  AND table_name = 'orders';
~~~

### 13.4. Xác định sequence trong schema dump

Dùng pg_restore --list hoặc xem plain SQL dump để xác nhận sequence definition và setval entry có được đưa vào hay không.

### 13.5. Không suy ra sequence state từ MAX(id) khi workload còn chạy

MAX(id) chỉ là dữ liệu hiện có trong bảng; sequence có thể đã cấp giá trị lớn hơn nhưng transaction chưa commit hoặc ID đã bị bỏ. Đối chiếu cả trạng thái sequence và workload.

## 14. Đồng bộ sequence sau khi import dữ liệu

Khi import một phần bảng hoặc hợp nhất dữ liệu, sequence có thể nhỏ hơn ID lớn nhất trong bảng.

### 14.1. Ví dụ lỗi duplicate key

Giả sử bảng có ID tới 5000 nhưng sequence vẫn ở 4200. Lệnh insert mới dùng nextval có thể tạo ID đã tồn tại và gây unique violation.

### 14.2. Lấy sequence name

~~~sql
SELECT pg_get_serial_sequence('app.orders', 'id');
~~~

### 14.3. Đồng bộ theo MAX(id)

Với một sequence sở hữu bởi cột id:

~~~sql
SELECT setval(
    pg_get_serial_sequence('app.orders', 'id')::regclass,
    COALESCE(MAX(id), 1),
    COUNT(*) > 0
)
FROM app.orders;
~~~

Ý nghĩa:
- Nếu bảng có rows, đặt sequence bằng MAX(id) và is_called = true; nextval tiếp theo sẽ cấp giá trị sau đó theo increment.
- Nếu bảng rỗng, đặt về 1 với is_called = false; nextval tiếp theo sẽ trả giá trị start tương ứng trong ví dụ đơn giản này.

### 14.4. Sequence start/increment khác mặc định

Nếu sequence có start value hoặc increment khác 1, phải dùng metadata thực tế để tính giá trị phù hợp. Không mặc định mọi sequence đều tăng từ 1.

### 14.5. Chặn writes trong lúc đồng bộ

Thực hiện sequence resync khi đã dừng hoặc khóa các writers liên quan. Nếu ứng dụng tiếp tục gọi nextval đồng thời, giá trị có thể thay đổi ngay sau khi đồng bộ.

### 14.6. Identity column

pg_get_serial_sequence cũng có thể xác định sequence gắn với identity column. Kiểm tra đúng table/column và quyền trước khi gọi setval.

### 14.7. Không dùng MAX(id) làm chính sách gapless

Sequence dùng để tạo định danh, không phải bộ đếm nghiệp vụ không có khoảng trống. Không cố lấp gaps bằng cách reset sequence trong khi ứng dụng hoạt động.

## 15. Sequence và transaction semantics

### 15.1. nextval không rollback

~~~sql
BEGIN;
SELECT nextval('app.orders_id_seq');
ROLLBACK;
~~~

Giá trị đã cấp không được trả lại chỉ vì transaction rollback.

### 15.2. setval không rollback theo cách thông thường

Thay đổi sequence state qua setval có hiệu lực ngay và không được hoàn tác như table row khi transaction abort.

### 15.3. Concurrent sessions

Nhiều session gọi nextval có thể nhận các giá trị khác nhau một cách atomic. Không dùng sequence như cơ chế cấp số tuần tự gapless.

### 15.4. Dump trong khi writes tiếp tục

Table rows trong dump phản ánh snapshot; sequence value được đọc ở một thời điểm khác trong quy trình. Khi restore, giá trị sequence có thể cao hơn một số row trong snapshot, tạo gaps nhưng vẫn hợp lệ.

### 15.5. Import vào database đang hoạt động

Khi nạp rows vào một database đã có writes, phải quyết định cách merge IDs và sequence state. Không restore sequence state từ dump một cách mù quáng vì có thể làm sequence lùi so với giá trị đã được cấp ở target.

## 16. Sequence trong serial và identity

### 16.1. Serial

Ví dụ:

~~~sql
CREATE TABLE app.invoice (
    id bigserial PRIMARY KEY,
    invoice_no text NOT NULL
);
~~~

PostgreSQL tạo sequence và default nextval. pg_dump thường ghi lại cả quan hệ sequence và current value trong data dump đầy đủ.

### 16.2. Identity

~~~sql
CREATE TABLE app.invoice (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    invoice_no text NOT NULL
);
~~~

Identity là thuộc tính của column và sequence được quản lý gắn với column. Dump/restore cần giữ generation mode và state.

### 16.3. GENERATED ALWAYS

Khi nạp explicit ID vào identity ALWAYS, có thể cần cú pháp/option phù hợp như OVERRIDING SYSTEM VALUE trong SQL hoặc tùy chọn restore tương ứng. pg_dump/pg_restore xử lý các trường hợp dump chuẩn, nhưng import dữ liệu thủ công cần chú ý.

### 16.4. GENERATED BY DEFAULT

Cho phép explicit value khi INSERT, hữu ích trong một số workflow migration. Sau khi import vẫn cần xác nhận sequence state.

### 16.5. Ownership dependency

Sequence ownership giúp DROP TABLE/COLUMN xử lý sequence liên quan đúng cách. Một sequence độc lập không có ownership có lifecycle riêng và cần backup riêng.

## 17. Large object là gì?

Large object (LO) là cơ chế PostgreSQL lưu nội dung nhị phân lớn bên ngoài row thông thường và tham chiếu bằng OID.

### 17.1. OID reference

Một bảng có thể lưu OID để tham chiếu large object:

~~~sql
CREATE TABLE app.documents (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    file_oid oid,
    file_name text
);
~~~

### 17.2. Large object storage

Nội dung large object được chia thành các page/chunk và lưu trong các system catalogs chuyên dụng như pg_largeobject; metadata/owner/ACL nằm trong catalog liên quan.

### 17.3. Large object API

Ứng dụng có thể dùng large object API để mở, đọc, ghi, seek, truncate hoặc unlink object. Một số ngôn ngữ driver cung cấp wrapper riêng.

### 17.4. OID không phải nội dung

Dump table chứa giá trị OID trong column không đồng nghĩa nội dung large object đã được dump. Nếu LO bị bỏ khỏi archive, OID trong row có thể trỏ tới object không tồn tại ở target.

### 17.5. Large object khác bytea

bytea là kiểu dữ liệu nhị phân nằm trong row value, có thể được TOAST khi lớn. Large object là object riêng được truy cập qua OID và API. Hai cách lưu có lifecycle, quyền và backup behavior khác nhau.

## 18. Large object và bytea: chọn loại nào?

| Tiêu chí | bytea | Large object |
| --- | --- | --- |
| Cách tham chiếu | Giá trị column | OID |
| Lưu trữ | Trong row/TOAST | Catalog large object riêng |
| Truy vấn SQL | Có thể đọc/ghi như value | Thường dùng LO API |
| Streaming | Driver có thể stream value tùy API | LO API hỗ trợ đọc/ghi theo chunk |
| Quyền | Table/column privileges | LO ownership/ACL và quyền API |
| Logical dump | Table data | Cần bảo đảm LO objects được include |
| Lifecycle | Theo row | Có thể tồn tại độc lập với row tham chiếu |
| Orphan risk | Không có LO orphan riêng | Có thể có orphan LO nếu row bị xóa mà LO không unlink |

### 18.1. Khi chọn bytea

Dùng khi dữ liệu nhị phân là một phần tự nhiên của row và kích thước/workload phù hợp với driver, query và storage design.

### 18.2. Khi chọn large object

Dùng khi cần thao tác nội dung lớn theo stream/chunk hoặc ứng dụng đã dựa vào large object API.

### 18.3. Không chuyển đổi tùy tiện

Chuyển OID large object sang bytea cần đọc nội dung từng LO và ghi vào column. Chỉ copy OID number không chuyển nội dung.

## 19. pg_dump và large objects

Với dump toàn database, pg_dump thường bao gồm large objects theo mặc định. Tuy nhiên, một số lựa chọn giới hạn schema/table hoặc schema-only làm thay đổi default này. Khi ứng dụng dùng LO, hãy kiểm tra và chỉ định rõ -b/--blobs nếu cần.

### 19.1. Dump toàn database có LO

~~~bash
pg_dump -Fc -b -d appdb -f appdb_with_blobs.dump
~~~

### 19.2. --no-blobs

~~~bash
pg_dump -Fc --no-blobs -d appdb -f appdb_without_blobs.dump
~~~

Không dùng --no-blobs nếu ứng dụng cần nội dung large objects để hoạt động.

### 19.3. Dump schema-only

Schema-only không lưu nội dung large objects như một data backup. Nó có thể giữ table definitions/OID columns nhưng không có bytes của LO.

### 19.4. Dump chọn table

~~~bash
pg_dump -Fc -t 'app.documents' -b \
  -d appdb -f documents.dump
~~~

Khi dùng table selection, cần chủ động bảo đảm large objects được include. -b có thể đưa các large objects trong database vào archive; điều đó không nhất thiết chỉ giới hạn ở những OID được các row đã chọn tham chiếu.

### 19.5. Không giả định dependency được chọn tự động

pg_dump không phải công cụ dependency closure tổng quát cho mọi table subset. Nếu dump một table có OID reference, kiểm tra LO data có trong archive và có thể restore.

### 19.6. Kiểm tra TOC

~~~bash
pg_restore --list documents.dump
~~~

Tìm các entries liên quan large objects/blobs và đối chiếu với phạm vi dump.

## 20. Restore large objects

### 20.1. Restore archive đầy đủ

~~~bash
pg_restore -d appdb_restore --verbose appdb_with_blobs.dump
~~~

Nếu archive chứa large objects, pg_restore nạp chúng cùng các entries khác theo TOC/dependency.

### 20.2. Restore một số entries

Có thể dùng pg_restore --list để tạo TOC list rồi chọn entries cần restore bằng -L. Khi chọn riêng table hoặc LO, phải giữ cả những dependencies mà ứng dụng cần.

### 20.3. Large object permissions

Large object có owner và ACL riêng. Kiểm tra role đích và quyền đọc/ghi LO sau restore, không chỉ quyền SELECT trên table chứa OID.

### 20.4. LO API

Ứng dụng dùng large object API cần quyền phù hợp và transaction context theo API. Kiểm tra bằng driver thực tế sau restore.

### 20.5. Orphan large objects

Nếu ứng dụng xóa row tham chiếu nhưng không unlink LO, object có thể còn lại mà không có row nào trỏ tới. Dump toàn database có thể vẫn mang theo các LO orphan đó.

### 20.6. Cleanup có kiểm soát

Xác định LO không còn tham chiếu trước khi xóa. Không chạy unlink hàng loạt nếu chưa biết schema/application reference model; một LO có thể được nhiều row dùng chung.

## 21. Kiểm tra large object inventory

Có thể xem metadata large objects:

~~~sql
SELECT
    loid,
    pageno,
    length(data) AS chunk_bytes
FROM pg_largeobject
ORDER BY loid, pageno
LIMIT 50;
~~~

Catalog pg_largeobject chứa các chunks; truy cập trực tiếp cần quyền phù hợp và không nên coi đây là API ứng dụng thông thường.

### 21.1. Metadata

~~~sql
SELECT *
FROM pg_largeobject_metadata
ORDER BY oid
LIMIT 50;
~~~

### 21.2. Đếm LO

~~~sql
SELECT count(*) AS large_object_count
FROM pg_largeobject_metadata;
~~~

### 21.3. Dung lượng

Có thể ước lượng số bytes bằng tổng độ dài chunks:

~~~sql
SELECT
    count(DISTINCT loid) AS object_count,
    sum(length(data)) AS stored_chunk_bytes
FROM pg_largeobject;
~~~

Đây là dung lượng nội dung chunk ước lượng, không phải tổng disk usage chính xác vì chưa tính catalog/index/page overhead và bloat.

### 21.4. Quyền truy cập

Large object metadata chứa owner/ACL. Kiểm tra quyền ứng dụng sau restore; table grants không tự thay thế LO privileges.

### 21.5. OID reference audit

Để tìm orphan objects, cần biết các column OID nào thực sự mang ý nghĩa LO reference. Không phải mọi column kiểu oid đều là large object reference. Viết kiểm tra theo schema/application model.

## 22. Dependency của DDL cần xử lý riêng

Một logical dump toàn database có thể sắp xếp nhiều dependency cho restore chuẩn. Nhưng khi chọn lọc object, di chuyển giữa môi trường hoặc tách schema, cần kiểm tra các dependency ngoài phạm vi.

### 22.1. Schema và search_path

Object có thể được tham chiếu bằng schema-qualified name hoặc phụ thuộc search_path. Restore vào database có schema khác hoặc search_path khác có thể làm function/view hoạt động sai.

### 22.2. Types và domains

Enum/domain/composite types phải tồn tại trước khi tạo columns/functions dùng chúng. Type trong schema khác cần được đưa vào migration set.

### 22.3. Functions và procedures

View, trigger, generated expression và default có thể gọi function. Cần giữ language, function body, owner, volatility, security definer và grants.

### 22.4. Collations

Collation phụ thuộc locale/ICU/OS version. Restore trên target thiếu collation hoặc khác collation version có thể ảnh hưởng sort/index semantics.

### 22.5. Extensions

Dump thường ghi lệnh CREATE EXTENSION và metadata liên quan, nhưng không đóng gói shared library hay source code extension. Target phải cài extension package tương thích.

### 22.6. Operators và operator classes

Index definitions có thể tham chiếu operator class hoặc extension-specific access method. Cần có package/objects tương ứng trước khi restore indexes.

### 22.7. Triggers và rules

Trigger có thể gọi function hoặc ghi sang bảng khác. Khi nạp dữ liệu, restore tooling thường điều khiển thứ tự; import thủ công phải biết trigger side effects.

### 22.8. Constraints

Foreign keys, unique/check constraints và exclusion constraints có thể được tạo ở post-data. Dữ liệu target phải thỏa constraints khi chúng được thêm.

### 22.9. Views và materialized views

View phụ thuộc vào tables/functions/types. Materialized view có thể cần refresh sau restore tùy cách dump và data availability; kiểm tra dữ liệu và trạng thái thực tế.

### 22.10. Row-level security

Policies và role membership ảnh hưởng dữ liệu mà ứng dụng nhìn thấy. Restore schema mà thiếu roles/grants/policies có thể tạo hành vi khác production.

## 23. Extension, FDW và dữ liệu ngoài database

Logical dump không đóng gói mọi dependency bên ngoài PostgreSQL.

### 23.1. Extension package

Ví dụ PostGIS, pgcrypto hoặc extension nội bộ cần được cài trên target với version tương thích. CREATE EXTENSION trong dump chỉ tham chiếu package có sẵn.

### 23.2. Shared libraries

Các function viết bằng C hoặc extension dùng shared libraries cần binary tương thích với OS, PostgreSQL major version và architecture.

### 23.3. Foreign Data Wrapper

Dump có thể chứa definitions của foreign servers/foreign tables trong phạm vi được hỗ trợ, nhưng dữ liệu thực nằm ở remote source không tự được sao chép như table data thông thường.

### 23.4. User mappings và secrets

Thông tin kết nối/credentials tới external services cần kiểm tra riêng. Không giả định mọi secret đã được dump hoặc có thể khôi phục an toàn từ file SQL.

### 23.5. External files

File nằm trên filesystem, object storage, application server hoặc dịch vụ ngoài không nằm trong logical database dump. Backup chúng theo lifecycle riêng.

### 23.6. Sequences/IDs ở hệ thống ngoài

Nếu ứng dụng dùng sequence để cấp ID cho nhiều hệ thống hoặc đồng bộ sang message broker, restore database có thể không tự khôi phục trạng thái bên ngoài. Cần reconciliation.

## 24. Global objects và database-level settings

### 24.1. Roles

Roles là cluster-wide objects. Một database dump có thể chứa owner/ACL references nhưng không tự tạo đầy đủ role definitions.

### 24.2. Tablespaces

Tablespace definitions là global objects. Restore sang server khác cần chuẩn bị tablespace name, location và filesystem path.

### 24.3. Database settings

Một số database-level settings được dump cùng database, nhưng server-wide settings như postgresql.conf, pg_hba.conf và SSL files cần backup riêng.

### 24.4. Replication slots

Physical/logical replication slots và runtime state của chúng không được xem là nội dung logical dump thông thường. Tái tạo replication setup bằng runbook riêng.

### 24.5. Server configuration

Các tham số như shared_buffers, max_connections, archive_command, wal_level, logging, listen_addresses và authentication rules nằm ngoài phạm vi dữ liệu logical của database.

### 24.6. Database encoding và locale

Khi tạo target database, cần chọn encoding, locale provider, collation và template phù hợp. Không phải mọi khác biệt đều có thể sửa sau khi database đã tạo.

## 25. pg_dumpall và consistency xuyên database

pg_dumpall giúp tạo SQL dump của nhiều database cùng globals, nhưng nó không biến toàn cluster thành một snapshot MVCC duy nhất.

### 25.1. Từng database được dump riêng

Mỗi database có thời điểm snapshot riêng. Một transaction workflow liên quan hai database có thể được nhìn ở trạng thái khác nhau giữa hai dump.

### 25.2. Cross-database invariants

PostgreSQL không hỗ trợ transaction thông thường xuyên nhiều database. Tuy nhiên, ứng dụng có thể có workflow nghiệp vụ liên quan nhiều database. Nếu cần một mốc nhất quán chung, quiesce writers hoặc dùng một chiến lược physical backup.

### 25.3. Dump globals cùng thời điểm

Roles/tablespaces thay đổi trong khi các database đang dump có thể tạo mismatch nếu globals dump và database dump không được điều phối.

### 25.4. Restore order

Thông thường restore globals trước, sau đó tạo/restore database. Kiểm tra tablespaces tồn tại trước khi restore object đặt trong tablespace đó.

### 25.5. Kết quả partial

pg_dumpall có thể tiếp tục/ghi lỗi theo cách của script và phiên bản. Kiểm tra exit status, stderr và xác nhận mọi database đều có dump hoàn chỉnh.

## 26. Phiên bản client và server

### 26.1. Dùng pg_dump tương thích

pg_dump không thể dump từ server major version mới hơn major version của chính client. Dùng client cùng major version hoặc mới hơn server theo quy tắc hỗ trợ.

### 26.2. Restore sang version mới hơn

Logical dump thường được dùng để chuyển dữ liệu lên major version mới hơn. Dù vậy, kiểm tra syntax, extension, collation và feature compatibility.

### 26.3. Restore sang version cũ hơn

Dump từ server mới có thể chứa syntax/object mà server cũ không hiểu. Không giả định logical dump luôn hỗ trợ downgrade.

### 26.4. pg_restore version

Dùng pg_restore tương thích với archive format/version tạo dump; thực tế thường dùng bộ client cùng version với pg_dump tạo file hoặc mới hơn theo hỗ trợ.

### 26.5. Extension compatibility

Kiểm tra extension version trên nguồn và target, upgrade scripts và binary dependencies.

### 26.6. Collation drift

Khác libc/ICU/OS version có thể khiến collation behavior thay đổi. Sau restore, kiểm tra collation version và reindex theo hướng dẫn khi cần.

## 27. Logical backup không bảo vệ mọi thứ

| Thành phần | pg_dump database thông thường |
| --- | --- |
| Table data | Có |
| DDL trong database | Có |
| Sequence definitions/state | Có trong full dump; schema-only không lưu current state |
| Large objects | Thường có mặc định trong full dump; kiểm tra khi chọn lọc hoặc dùng --no-blobs |
| Roles | Không dump đầy đủ như globals |
| Tablespaces definitions | Không dump đầy đủ như globals |
| postgresql.conf | Không |
| pg_hba.conf | Không |
| SSL keys/certificates | Không |
| Extension binaries | Không |
| Remote foreign data | Không |
| External files/object storage | Không |
| Replication slot runtime state | Không |
| OS packages/config | Không |
| Database data trên mọi database trong cluster | Chỉ khi dump từng DB/pg_dumpall |

### 27.1. Phân biệt data và environment

Logical dump tái tạo database objects/data. Nó không tự tái tạo toàn bộ server environment cần để ứng dụng chạy.

### 27.2. Backup runbook

Lưu riêng các thông tin: PostgreSQL version, extension list, config files, TLS, secrets, FDW endpoints, roles, tablespaces và application deployment dependencies.

### 27.3. Không gọi dump là full disaster recovery nếu thiếu dependencies

Nếu ứng dụng cần file ngoài database, extension binary hoặc remote service mà không có backup, logical dump chỉ là một phần của recovery plan.

## 28. Bảo mật dump files

Plain SQL dump có thể chứa toàn bộ dữ liệu nhạy cảm và role definitions.

### 28.1. File permissions

Chỉ cấp quyền đọc cho backup/restore operators và service identities cần thiết.

### 28.2. Encryption

Mã hóa khi truyền và khi lưu. Quản lý key độc lập với nơi lưu dump.

### 28.3. Password handling

Dùng .pgpass với permissions phù hợp hoặc secret manager. Tránh đặt password trực tiếp trong shell history, command logs hoặc repository.

### 28.4. SQL injection trong restore context

Dump là nội dung thực thi SQL. Chỉ restore từ artifact có nguồn gốc tin cậy và review khi nhận từ bên ngoài.

### 28.5. Role passwords

Globals dump có thể chứa password hashes. Bảo vệ như dữ liệu xác thực nhạy cảm và giới hạn người truy cập.

### 28.6. Retention và deletion

Áp dụng retention, encryption, audit và secure deletion theo policy dữ liệu của tổ chức.

## 29. Migration bằng logical dump

Logical dump thường được dùng khi chuyển database sang host/version mới.

### 29.1. Preflight

- Xác nhận target PostgreSQL version.
- Kiểm tra extension, locale/collation và encoding.
- Kiểm tra roles, tablespaces và owner.
- Xác định large objects và sequence dependencies.
- Ước lượng dung lượng và restore time.

### 29.2. Schema freeze

Tránh deploy DDL trong lúc dump/restore migration trừ khi migration plan đã tính đến thay đổi đó.

### 29.3. Initial dump

Tạo full dump hoặc dump theo schema/table. Với database lớn, cân nhắc directory/custom format và parallelism.

### 29.4. Delta changes

pg_dump là snapshot dump, không tự capture các writes xảy ra sau snapshot. Để giảm downtime, cần một chiến lược đồng bộ delta riêng như logical replication hoặc write freeze/cutover.

### 29.5. Cutover

Tạm dừng writes, đồng bộ phần thay đổi cuối, xác minh sequence state và chuyển ứng dụng sang target.

### 29.6. Rollback

Giữ nguồn cũ ở trạng thái có thể phục hồi theo thời gian đã định. Sau khi target nhận writes mới, rollback có thể cần reverse replication hoặc reconciliation; chỉ đổi connection string không tự đồng bộ dữ liệu ngược.

## 30. Kiểm tra dump và restore

### 30.1. Kiểm tra exit status

Automation chỉ đánh dấu backup thành công khi pg_dump kết thúc với exit code 0.

### 30.2. Kiểm tra file

Xác nhận artifact tồn tại, kích thước hợp lý, checksum được ghi nhận và file có thể đọc.

### 30.3. Kiểm tra archive TOC

~~~bash
pg_restore --list appdb.dump
~~~

Nếu không đọc được TOC, file có thể hỏng hoặc không phải archive format mong đợi.

### 30.4. Restore vào database riêng

Không kiểm tra backup bằng cách ghi đè production. Dùng một target database/instance độc lập.

### 30.5. Kiểm tra DDL

Xác nhận schema, type, function, trigger, index, constraint, policy và owner được tạo đúng.

### 30.6. Kiểm tra data

So sánh row counts, key ranges, aggregate totals và business invariants. Với large objects, kiểm tra OID references và đọc thử nội dung.

### 30.7. Kiểm tra sequence

Sau import, kiểm tra nextval không tạo ID trùng và sequence state phù hợp với dữ liệu đã nạp.

### 30.8. Kiểm tra ứng dụng

Chạy smoke tests, transaction đại diện và các truy vấn phụ thuộc extension/FDW.

## 31. Các giới hạn khi dump một phần database

### 31.1. Table selection không tự chứa dependency

Một table có thể dùng enum ở schema khác, function trong default expression, sequence, trigger function hoặc extension. Dump table riêng không bảo đảm các dependency được đưa vào.

### 31.2. Cross-schema references

View/function có thể tham chiếu object ngoài schema đã chọn. Restore có thể thất bại hoặc object tạo được nhưng chạy không đúng.

### 31.3. Large objects

Table chứa OID reference không đảm bảo LO content được include trong selective dump. Xác nhận --blobs và archive TOC.

### 31.4. Sequences

Table dump có thể không bao gồm sequence liên quan hoặc current value theo cách cần cho migration. Xác định sequence và đồng bộ sau import.

### 31.5. Foreign keys

Dump một table có thể bỏ qua bảng được tham chiếu. Khi restore constraint, target cần có bảng/keys tương ứng hoặc phải lên kế hoạch tách constraint.

### 31.6. Triggers

Trigger function và bảng phụ trợ có thể nằm ngoài selection. Khi import thủ công, trigger có thể lỗi hoặc tạo side effects.

### 31.7. Views/materialized views

Các view phụ thuộc nhiều table/function/type. Chọn một view mà không chọn dependency có thể làm restore thất bại.

### 31.8. Chọn object theo dependency closure

Trước khi dump subset, lập danh sách object nguồn và target, dependency, role, extension, sequence, LO và external resources. Kiểm tra restore thử trước cutover.

## 32. Large object lifecycle và orphan objects

Large object có thể tồn tại độc lập với row đang tham chiếu OID.

### 32.1. Tạo LO

Ứng dụng tạo LO qua large object API hoặc các hàm hỗ trợ phù hợp.

### 32.2. Gắn OID vào row

Bảng lưu OID như một tham chiếu. PostgreSQL không tự hiểu mọi OID column là quan hệ foreign key tới large object.

### 32.3. Xóa row

DELETE row chứa OID không nhất thiết tự xóa nội dung large object.

### 32.4. Orphan growth

Nếu ứng dụng không gọi unlink khi object không còn cần, pg_largeobject có thể tăng dù số row ứng dụng giảm.

### 32.5. Dump vẫn có thể mang orphan

Dump toàn database có thể lưu các LO còn tồn tại, kể cả LO không còn được row nào tham chiếu. Đây là một phần dữ liệu thực tế trong database.

### 32.6. Cleanup policy

Xây logic tham chiếu theo schema/app, xác định LO không còn được sử dụng, review trước và xóa trong transaction/tooling phù hợp. Không giả định mọi LO chỉ có một owner row.

## 33. Sequence và large object trong restore từng phần

Khi chỉ restore một nhóm bảng, hai loại object này cần được kiểm tra riêng.

### 33.1. Sequence checklist

- Sequence definition có trong dump không?
- Owner/OWNED BY có đúng không?
- Default/identity column có tham chiếu sequence đúng không?
- Current value có được dump không?
- Có writes mới trên target trong lúc import không?
- Sau import, nextval có thể tạo duplicate không?

### 33.2. Large object checklist

- Bảng có OID reference tới LO không?
- Dump có include blob data không?
- TOC có large object entries không?
- OID references có giữ nguyên khi restore không?
- LO owner/ACL có đúng không?
- Có orphan objects hoặc LO dùng chung không?
- Ứng dụng có thể đọc LO qua driver/API không?

### 33.3. Không chỉ kiểm tra row count

Số row có thể khớp trong khi sequence sai hoặc LO content bị thiếu. Cần kiểm tra từng loại object theo cách riêng.

## 34. Lỗi thường gặp và cách xử lý

### Lỗi 1. Restore báo role does not exist

Globals dump chưa được restore hoặc target role mapping chưa được chuẩn bị. Restore roles trước hoặc dùng --no-owner theo kế hoạch.

### Lỗi 2. Tablespace location không tồn tại

Tablespace globals hoặc filesystem path chưa được tạo. Chuẩn bị mount/directory và tablespace trước database restore.

### Lỗi 3. Extension is not available

Cài extension package/binary đúng version trước khi restore CREATE EXTENSION.

### Lỗi 4. Function/type does not exist

Dump subset bỏ dependency hoặc restore order sai. Xem TOC và bổ sung object phụ thuộc.

### Lỗi 5. Duplicate key sau restore

Sequence state nhỏ hơn dữ liệu đã nạp hoặc target có dữ liệu cũ. Dừng writes, xác định sequence và đồng bộ có kiểm soát.

### Lỗi 6. Large object missing

Selective dump/schema-only/no-blobs đã bỏ LO content. Tạo dump có blobs từ nguồn còn đầy đủ và restore LO entries.

### Lỗi 7. OID tồn tại nhưng nội dung không đọc được

Table row được restore nhưng large object không có hoặc ACL không đúng. Kiểm tra pg_largeobject_metadata và LO privileges.

### Lỗi 8. Restore plain bằng pg_restore

Plain SQL cần psql. Dùng pg_restore cho custom/directory/tar archives.

### Lỗi 9. Archive version mismatch

Dùng pg_restore tương thích hoặc mới hơn với archive format. Kiểm tra version binary và tạo lại dump nếu cần.

### Lỗi 10. SQL syntax không hỗ trợ trên target

Dump từ server mới có thể chứa syntax/object target cũ không hiểu. Chọn target version phù hợp hoặc thực hiện migration có chuyển đổi.

### Lỗi 11. Parallel restore hết connections

Giảm -j, tăng connection capacity phù hợp hoặc restore theo sections.

### Lỗi 12. Parallel dump không hỗ trợ format

Parallel dump yêu cầu directory format. Chọn -Fd -j hoặc dump tuần tự với format khác.

### Lỗi 13. pg_dumpall có database thiếu

Kiểm tra exit code/log từng database, quyền kết nối và dung lượng output. Không đánh dấu cluster backup thành công khi một database thất bại.

### Lỗi 14. Sequence lùi trong migration

Không restore sequence state cũ đè lên target đang có writes. Dừng writes và reconcile state với IDs đã cấp.

### Lỗi 15. Foreign table không có dữ liệu

Foreign table definitions không đồng nghĩa remote data được dump. Backup remote source theo công cụ của hệ thống đó.

### Lỗi 16. Collation mismatch

Kiểm tra locale provider/version và reindex theo hướng dẫn PostgreSQL sau khi chuyển môi trường.

### Lỗi 17. Role password lộ trong dump

Giới hạn quyền file, mã hóa, audit truy cập và xoay vòng credentials nếu artifact đã bị lộ.

### Lỗi 18. Dump không nhất quán xuyên database

pg_dumpall dump từng database riêng. Quiesce ứng dụng hoặc dùng phương án backup có consistency phù hợp nếu có invariant xuyên DB.

### Lỗi 19. Trigger side effects khi import thủ công

Restore dữ liệu theo workflow chuẩn hoặc lập kế hoạch trigger/constraint rõ ràng. Không disable triggers tùy tiện nếu chưa hiểu integrity requirements.

### Lỗi 20. Restore thành công nhưng ứng dụng lỗi

Kiểm tra role memberships, grants, extension, FDW, secrets, sequence, LO, collation và external dependencies.

## 35. Quy trình backup logical đề xuất

~~~text
Scheduler
   |
   v
Preflight
   |-- source/version
   |-- roles/tablespaces
   |-- extension inventory
   |-- sequence/LO inventory
   |-- disk and credentials
   |
   v
pg_dump / pg_dumpall
   |-- chosen format
   |-- explicit blob policy
   |-- logs and exit code
   |
   v
Artifact verification
   |-- file size/checksum
   |-- archive TOC
   |-- metadata
   |
   v
Offsite encrypted storage
   |
   v
Restore drill
   |-- globals first
   |-- extensions/tablespaces
   |-- database restore
   |-- sequence/LO checks
   |-- application validation
~~~

### 35.1. Inventory trước backup

Ghi PostgreSQL version, database list, roles, tablespaces, extensions, sequences, large objects, FDW và external dependencies.

### 35.2. Chọn format

Chọn custom/directory cho archive workflow cần selective/parallel restore hoặc plain cho SQL script.

### 35.3. Explicit blobs

Nếu ứng dụng dùng large objects, chỉ định -b trong workflow dump cần chúng và kiểm tra TOC.

### 35.4. Lưu globals

Dump roles/tablespaces cùng backup set.

### 35.5. Artifact integrity

Ghi checksum, file size, thời gian, source cluster và command options.

### 35.6. Restore drill

Restore vào target cô lập, kiểm tra sequence/LO và ứng dụng. Chỉ publish backup usable sau khi bước cần thiết hoàn tất.

## 36. Quy trình migration logical đề xuất

1. Kiểm tra source/target major versions và extension compatibility.
2. Tạo inventory DDL, roles, tablespaces, sequences, LOs và external systems.
3. Chuẩn bị target server, roles, tablespaces, extensions và database settings.
4. Tạo initial logical dump.
5. Restore và kiểm tra schema/data ở target.
6. Lập phương án đồng bộ writes phát sinh sau snapshot.
7. Tới cutover, tạm dừng writers hoặc chốt delta replication.
8. Đồng bộ sequence state và large objects.
9. Kiểm tra constraints, indexes, triggers, ownership và ACL.
10. Chạy application smoke tests và business reconciliation.
11. Chuyển traffic tới target.
12. Theo dõi lỗi và giữ rollback plan.
13. Không xóa source hoặc backup cho tới khi hết cửa sổ rollback đã thống nhất.

## 37. Bài tập thực hành

Các bài tập dùng database lab riêng và dump artifact không chứa dữ liệu production nhạy cảm.

### Bài 1. Logical backup

Logical backup lưu database ở mức nào?

### Bài 2. Công cụ

Phân biệt nhiệm vụ của pg_dump, pg_restore và pg_dumpall.

### Bài 3. Plain format

Restore plain SQL dump bằng công cụ nào?

### Bài 4. Custom format

Vì sao custom archive dùng pg_restore?

### Bài 5. Directory format

Format nào hỗ trợ parallel dump?

### Bài 6. Schema-only

Tùy chọn nào tạo schema-only dump và sequence current state có được lưu không?

### Bài 7. Data-only

Khi nào cần dùng data-only dump?

### Bài 8. Snapshot

Vì sao pg_dump có thể tạo snapshot nhất quán trong khi writes vẫn tiếp tục?

### Bài 9. DDL

Nêu ba loại dependency có thể khiến restore table riêng bị lỗi.

### Bài 10. Sections

Ba sections pre-data, data và post-data chứa những gì?

### Bài 11. TOC

Viết lệnh xem nội dung archive.

### Bài 12. Globals

Dùng lệnh nào để dump roles và tablespaces?

### Bài 13. Owner

Tùy chọn nào bỏ owner commands khi restore?

### Bài 14. ACL

Tùy chọn nào bỏ privilege commands khi restore?

### Bài 15. Sequence

Vì sao sequence không tuân theo MVCC snapshot như table rows?

### Bài 16. nextval

Vì sao nextval có thể tạo gaps?

### Bài 17. setval

Viết một ví dụ đồng bộ sequence với MAX(id) sau khi import.

### Bài 18. Concurrent writes

Vì sao không nên resync sequence khi writers vẫn hoạt động?

### Bài 19. Identity

Identity column khác serial ở điểm nào về định nghĩa SQL?

### Bài 20. Large object

Large object được tham chiếu trong table thường bằng kiểu gì?

### Bài 21. bytea

Nêu một khác biệt giữa bytea và large object.

### Bài 22. Blob option

Tùy chọn nào include large objects trong pg_dump?

### Bài 23. no-blobs

Khi nào không nên dùng --no-blobs?

### Bài 24. Selective dump

Vì sao dump table chứa OID không bảo đảm large object content có mặt?

### Bài 25. Orphan LO

Orphan large object là gì?

### Bài 26. LO permissions

Vì sao table SELECT privilege chưa chắc đủ để đọc large object?

### Bài 27. Extension

Vì sao CREATE EXTENSION trong dump chưa đủ để cài extension trên target?

### Bài 28. FDW

Vì sao dump foreign table không backup dữ liệu remote?

### Bài 29. Version

Có thể dùng pg_dump client cũ hơn server major version để dump server mới hơn không?

### Bài 30. pg_dumpall consistency

Vì sao pg_dumpall không tạo một snapshot duy nhất xuyên mọi database?

### Bài 31. Collation

Khác biệt collation version có thể gây vấn đề gì sau restore?

### Bài 32. Global configuration

Kể bốn thành phần không nằm trong logical dump thông thường.

### Bài 33. Parallel restore

Format nào hỗ trợ parallel restore qua pg_restore?

### Bài 34. Exit on error

Tùy chọn nào giúp dừng pg_restore khi có lỗi?

### Bài 35. Security

Vì sao globals dump cần được bảo vệ như secret?

### Bài 36. Migration

Vì sao initial pg_dump không tự đồng bộ writes phát sinh sau snapshot?

### Bài 37. Sequence restore

Vì sao cần kiểm tra sequence sau khi restore một phần table?

### Bài 38. LO restore

Nêu bốn kiểm tra cần làm sau khi restore large objects.

### Bài 39. Validation

Nêu năm lớp kiểm tra cho một logical backup.

### Bài 40. Thiết kế

Đề xuất quy trình backup/migration có DDL, sequences, large objects và external dependencies.

## 38. Lời giải tham khảo

### Bài 1–5. Công cụ và format

Logical backup lưu schema/data ở mức object. pg_dump tạo dump một database; pg_restore đọc custom/directory/tar archive; pg_dumpall dump nhiều database và global objects. Plain SQL dùng psql. Directory format hỗ trợ parallel dump.

### Bài 6–10. Snapshot và DDL

-s tạo schema-only và không lưu current sequence state như data dump. Data-only dùng khi schema đã tồn tại và cần nạp dữ liệu. pg_dump dùng MVCC snapshot để đọc table data nhất quán. Dependency ví dụ: enum/type, sequence/default, function/trigger, extension, schema và foreign key. Pre-data chứa definitions trước data; data chứa rows/LO/sequence values; post-data chứa indexes/triggers/constraints theo archive organization.

### Bài 11–14. Archive và globals

~~~bash
pg_restore --list appdb.dump
~~~

~~~bash
pg_dumpall --globals-only -f globals.sql
~~~

--no-owner bỏ owner commands; --no-acl bỏ privilege commands. Cần có quy trình cấp role/owner/privilege thay thế.

### Bài 15–19. Sequence

Sequence state không theo MVCC snapshot và nextval/setval không rollback như table row. Gaps xuất hiện do rollback, cache hoặc giá trị cấp phát không dùng. Ví dụ đồng bộ:

~~~sql
SELECT setval(
    pg_get_serial_sequence('app.orders', 'id')::regclass,
    COALESCE(MAX(id), 1),
    COUNT(*) > 0
)
FROM app.orders;
~~~

Cần dừng writers trong lúc resync để tránh race. Identity dùng cú pháp GENERATED ... AS IDENTITY, còn serial là shorthand tạo sequence/default/ownership.

### Bài 20–26. Large objects

Large object thường được tham chiếu bằng OID. bytea là value của column; LO là object riêng dùng LO API. -b/--blobs include LOs. Không dùng --no-blobs nếu ứng dụng cần LO content. Selective dump có thể giữ OID column nhưng bỏ LO data nếu không include blobs. Orphan LO là object không còn row/application reference. LO có ACL riêng nên table SELECT không tự đảm bảo quyền đọc LO.

### Bài 27–32. Dependencies và giới hạn

CREATE EXTENSION chỉ tạo extension nếu package/binary có sẵn trên target. Foreign table definition không sao chép dữ liệu ở remote server. pg_dump client cũ không dump từ server major mới hơn nó. pg_dumpall dump từng database riêng nên không có một snapshot cluster-wide duy nhất. Collation drift có thể ảnh hưởng sort/index semantics và cần reindex theo hướng dẫn. Các thành phần ngoài dump gồm roles/tablespaces globals, server config, TLS files, extension binaries, external data/files, replication slots và OS packages.

### Bài 33–36. Restore và migration

Custom và directory archives hỗ trợ parallel restore. --exit-on-error dừng pg_restore khi gặp lỗi. Globals dump có thể chứa password hashes nên cần bảo vệ. Initial pg_dump chỉ phản ánh snapshot tại thời điểm dump; writes sau snapshot phải được đồng bộ bằng delta mechanism hoặc write freeze/cutover.

### Bài 37–40. Validation và quy trình

Sau partial table restore, kiểm tra sequence definition/state/nextval và duplicate IDs. Với LO, kiểm tra OID references, object count/content readability, owner/ACL và orphan lifecycle. Logical backup validation gồm exit status, artifact/checksum, TOC/manifest metadata, restore drill và application/business checks. Pipeline đầy đủ cần inventory DDL/dependencies, roles/tablespaces, sequence và LO, extension/FDW/external systems, dump có blobs khi cần, restore theo dependency order, resync sequence, validate và cutover có delta/rollback plan.

## 39. Bảng tra cứu nhanh

| Nhu cầu | Công cụ/tùy chọn |
| --- | --- |
| Dump một database | pg_dump |
| Dump toàn cluster logical | pg_dumpall |
| Dump roles/tablespaces | pg_dumpall --globals-only |
| Restore plain SQL | psql |
| Restore archive | pg_restore |
| Plain output | -Fp |
| Custom archive | -Fc |
| Directory archive | -Fd |
| Tar archive | -Ft |
| Schema-only | -s / --schema-only |
| Data-only | -a / --data-only |
| Include large objects | -b / --blobs |
| Exclude large objects | --no-blobs |
| Select schema | -n |
| Select table | -t |
| Parallel dump | -Fd -j |
| Parallel restore | pg_restore -j |
| View archive TOC | pg_restore --list |
| Select TOC entries | pg_restore -L |
| Create database on restore | pg_restore -C |
| Clean existing objects | pg_restore --clean |
| Stop restore on error | pg_restore --exit-on-error |
| Skip owner commands | --no-owner |
| Skip ACL commands | --no-acl |
| Find owned sequence | pg_get_serial_sequence() |
| Read sequence metadata | pg_sequences |
| Set sequence state | setval() |
| Get next sequence value | nextval() |
| Inspect LO metadata | pg_largeobject_metadata |
| Inspect LO chunks | pg_largeobject |

## 40. Checklist DDL, sequence và large object

1. Chọn đúng database/schema/table scope cho dump.
2. Ghi client/server PostgreSQL major versions.
3. Chọn plain/custom/directory/tar format phù hợp.
4. Kiểm tra dump exit status và artifact integrity.
5. Lưu TOC/metadata cùng backup.
6. Lập inventory schema, types, domains và collations.
7. Lập inventory functions, procedures, triggers và rules.
8. Lập inventory tables, partitions, indexes và constraints.
9. Xác định dependency ngoài schema/table được chọn.
10. Dump roles và tablespaces bằng globals workflow.
11. Bảo vệ globals dump vì có thể chứa password hashes.
12. Chuẩn bị extension packages và shared libraries trên target.
13. Kiểm tra FDW servers, user mappings và external credentials.
14. Backup server configuration, TLS files và secrets riêng.
15. Kiểm tra sequence definitions và ownership.
16. Xác định serial/identity columns và sequence names.
17. Đảm bảo data dump có sequence values khi cần.
18. Resync sequence sau partial import hoặc ID merge.
19. Dừng writers trong khi sequence resync.
20. Kiểm tra nextval không tạo duplicate IDs.
21. Inventory large objects và OID references.
22. Dùng --blobs khi workflow cần include large objects.
23. Không dùng --no-blobs nếu ứng dụng cần LO content.
24. Kiểm tra selective dump có giữ LO entries.
25. Kiểm tra LO owner và ACL sau restore.
26. Kiểm tra orphan LO theo application reference model.
27. Restore theo thứ tự dependency phù hợp.
28. Restore globals/roles/tablespaces trước database khi cần.
29. Dùng psql cho plain và pg_restore cho archive.
30. Kiểm tra DDL, data, sequence, LO và application behavior sau restore.
31. Quản lý cross-database consistency nếu dùng pg_dumpall.
32. Lập delta/cutover strategy cho migration có writes.
33. Giữ source/rollback plan trong cửa sổ migration.
34. Chỉ đánh dấu backup usable sau restore drill đạt yêu cầu.

## 41. Tổng kết

Logical backup dùng pg_dump/pg_dumpall để lưu database objects và dữ liệu ở mức SQL/archive. Cách làm này linh hoạt cho migration, selective restore và nâng cấp major version, nhưng có những thành phần không tự nằm trong một database dump: roles, tablespaces, server configuration, extension binaries, remote data, external files và replication runtime state.

DDL cần được restore theo dependency. Một dump toàn database giúp PostgreSQL archive quản lý phần lớn thứ tự object, nhưng dump chọn riêng schema/table có thể bỏ sót type, function, sequence, trigger, extension hoặc foreign-key dependencies. Hãy kiểm tra TOC và thử restore trước khi dùng artifact cho migration.

Sequence cần chú ý vì nextval/setval không có transactional behavior như table rows và sequence state không theo MVCC snapshot. Sau partial import hoặc merge IDs, dừng writers, xác định sequence đúng và đồng bộ state có kiểm soát. Large object cũng cần kiểm tra riêng: table có OID reference không có nghĩa nội dung LO đã được dump. Dùng --blobs khi cần, kiểm tra TOC, ownership, ACL và khả năng đọc nội dung sau restore.

Một logical backup chỉ có giá trị khi target có đủ DDL dependencies, roles, extensions, sequences, large objects và external configuration cần thiết. Hãy inventory trước backup, bảo vệ artifact, restore thử trong môi trường riêng, kiểm tra business invariants và đo thời gian phục hồi. Với migration đang có writes, lập delta synchronization và cutover plan; pg_dump một mình không capture các thay đổi commit sau snapshot của nó.
