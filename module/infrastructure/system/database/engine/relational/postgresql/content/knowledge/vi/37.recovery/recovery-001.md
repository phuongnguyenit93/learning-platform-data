# Khôi phục SQL dump và điều khiển lỗi khi chạy script trong PostgreSQL

Một bản SQL dump chỉ có giá trị khi có thể khôi phục đúng vào database đích. Trong PostgreSQL, cách restore phụ thuộc vào **định dạng dump**:

- Dump dạng plain SQL là một file lệnh SQL, được thực thi bằng `psql`.
- Dump dạng custom, directory hoặc tar là archive do `pg_dump` tạo, được đọc bằng `pg_restore`.

Một phần quan trọng khác là **điều khiển lỗi**. Mặc định, `psql` có thể tiếp tục chạy các lệnh sau khi một SQL statement bị lỗi. `pg_restore` cũng có thể tiếp tục qua một số lỗi và báo tổng kết cuối cùng. Nếu script restore cần dừng ngay khi có lỗi, rollback toàn bộ hoặc ghi log với exit code đáng tin cậy, phải chọn đúng tùy chọn.

Bài **“Khôi phục SQL dump và điều khiển lỗi khi chạy script”**, thuộc chương **Khôi phục** của module **Database Engine Relational PostgreSQL**, trình bày định dạng dump, lựa chọn `psql`/`pg_restore`, chuẩn bị database/roles/extensions, restore toàn bộ và từng phần, xử lý ownership/ACL, transaction scope, error handling, shell exit codes, log và xác minh sau restore.

> **Nguyên tắc:** xác định dump format trước khi restore; restore vào target đã chuẩn bị; bật chế độ dừng khi lỗi nếu cần kết quả all-or-nothing; luôn kiểm tra exit code và dữ liệu sau khi restore.

---

## 1. SQL dump là gì?

SQL dump là bản biểu diễn logic của schema và/hoặc dữ liệu PostgreSQL. Nó có thể chứa:

- `CREATE TABLE`, `CREATE SEQUENCE`, `CREATE VIEW`.
- `CREATE INDEX`, constraints và triggers.
- `INSERT` hoặc lệnh nạp dữ liệu dạng khác.
- Function, procedure, type và extension declarations.
- Ownership và privilege statements nếu được giữ trong dump.
- Sequence values và các object metadata cần thiết.

Dump logic không phải bản copy vật lý của data directory. Nó được tạo bằng cách đọc database objects và xuất ra dạng có thể tái tạo trên server khác.

### 1.1. SQL dump khác physical backup

| Logical SQL dump | Physical backup |
|---|---|
| Biểu diễn schema/data dưới dạng SQL hoặc archive logic | Sao lưu files vật lý của cluster/database |
| Thường restore bằng psql/pg_restore | Restore bằng quy trình physical backup/recovery |
| Có thể chọn schema/table/section | Thường phục hồi một physical cluster/instance |
| Phù hợp migration và chuyển dữ liệu logic | Phù hợp PITR/physical disaster recovery |
| Không giữ nguyên physical page layout | Giữ trạng thái vật lý theo backup method |

Không dùng `pg_restore` để restore một physical base backup. Không dùng SQL dump như thay thế trực tiếp cho WAL archive/PITR.

## 2. Các định dạng dump

`pg_dump` hỗ trợ các định dạng chính:

| Format | Tùy chọn | Đặc điểm | Công cụ restore |
|---|---|---|---|
| Plain | Mặc định | File SQL đọc được | `psql` |
| Custom | `-Fc` | Archive linh hoạt, chọn object/parallel restore | `pg_restore` |
| Directory | `-Fd` | Một thư mục gồm nhiều file archive; hỗ trợ parallel dump/restore | `pg_restore` |
| Tar | `-Ft` | Archive dạng tar | `pg_restore` |

**Plain SQL** có thể mở bằng text editor và kiểm tra nội dung. Custom/directory/tar là archive format; dùng `pg_restore --list` để xem mục lục.

### 2.1. Không dùng sai công cụ

- Plain SQL: `psql -f dump.sql`.
- Custom/directory/tar: `pg_restore`.
- Không truyền custom archive cho psql như thể đó là SQL text.
- Không truyền plain SQL file cho pg_restore.

## 3. Tạo plain SQL dump

~~~bash
pg_dump -h db.example -p 5432 -U backup_user -d appdb -f appdb.sql
~~~

Lệnh tạo file SQL có thể nạp bằng psql.

Có thể yêu cầu dump gồm lệnh tạo database:

~~~bash
pg_dump -h db.example -U backup_user -d appdb --create -f appdb-create.sql
~~~

Khi dump có lệnh CREATE DATABASE và psql connect meta-command, phải kết nối psql tới một database maintenance phù hợp, chẳng hạn `postgres`, để script tự tạo và chuyển sang database đích.

### 3.1. Kiểm tra plain dump

Có thể tìm các lệnh `CREATE TABLE`, `COPY`, `ALTER TABLE`, `CREATE INDEX` và `setval`. Không chỉnh sửa tùy tiện những phần liên quan thứ tự dependencies hoặc quoting.

## 4. Tạo custom archive

~~~bash
pg_dump -h db.example -U backup_user -d appdb -Fc -f appdb.dump
~~~

Custom archive phù hợp khi muốn:

- Chọn object cần restore.
- Restore schema-only hoặc data-only.
- Restore theo section.
- Dùng `pg_restore --list` và file TOC.
- Chạy parallel restore với `-j`.

Custom archive không phải file SQL thuần, dù có thể dùng pg_restore để xuất nó thành SQL text.

## 5. Tạo directory archive

~~~bash
pg_dump -h db.example -U backup_user -d appdb -Fd -j 4 -f appdb-dir
~~~

Directory format ghi archive thành nhiều file trong thư mục. Nó hỗ trợ parallel dump và parallel restore.

Đảm bảo thư mục đích có đủ dung lượng và được bảo vệ quyền truy cập.

### 5.1. Tạo tar archive

~~~bash
pg_dump -h db.example -U backup_user -d appdb -Ft -f appdb.tar
~~~

Tar archive có thể restore bằng pg_restore, nhưng không hỗ trợ mọi khả năng parallel giống custom/directory format.

## 6. Dump toàn cluster

`pg_dump` chỉ dump **một database** mỗi lần. Nó không xuất toàn bộ cluster-wide roles và tablespaces.

`pg_dumpall` có thể dump tất cả databases và global objects:

~~~bash
pg_dumpall -h db.example -U postgres -f cluster.sql
~~~

Có thể chỉ xuất global objects:

~~~bash
pg_dumpall -h db.example -U postgres --globals-only -f globals.sql
~~~

Global objects gồm roles và tablespaces. Script globals có thể chứa thông tin nhạy cảm như role password hashes hoặc đường dẫn tablespace; bảo vệ file dump như credential material.

### 6.1. Restore pg_dumpall

Dump của pg_dumpall là plain SQL script, thường được chạy qua psql:

~~~bash
psql -X -h target.example -U postgres -d postgres -v ON_ERROR_STOP=1 -f cluster.sql
~~~

Script có thể tự tạo databases và chuyển kết nối giữa chúng. Không bọc một dump toàn cluster có CREATE DATABASE trong một transaction duy nhất.

## 7. Chuẩn bị target trước khi restore

Trước khi chạy restore, xác định:

1. Target server/port/database.
2. PostgreSQL source và target versions.
3. Encoding và locale/collation cần thiết.
4. Roles/owners cần tồn tại.
5. Extensions và package phía server cần cài.
6. Tablespaces và filesystem paths.
7. Quyền kết nối và quyền tạo object.
8. Dung lượng disk, WAL và thời gian bảo trì.
9. Database target có đang được ứng dụng sử dụng không?
10. Có backup/rollback plan cho target hiện tại không?

Restore vào database rỗng thường dễ dự đoán hơn restore chồng lên database đã có object.

## 8. Tạo database đích

Ví dụ tạo database mới:

~~~bash
createdb -h target.example -U db_admin -T template0 -E UTF8 appdb_restore
~~~

`template0` thường hữu ích khi cần tạo database sạch với encoding/locale chỉ định, tránh object tùy chỉnh có trong template1.

Tùy hệ điều hành và PostgreSQL version, có thể cần thêm locale/collation options. Hãy chọn chúng tương thích với source và ứng dụng.

### 8.1. Vì sao không restore vào postgres database?

`postgres` thường là maintenance database để kết nối quản trị. Nên tạo một database riêng cho ứng dụng và restore vào đó, trừ khi dump script tự tạo database bằng tùy chọn `--create`.

## 9. Restore plain SQL bằng psql

Lệnh cơ bản:

~~~bash
psql -X -h target.example -p 5432 -U restore_user -d appdb_restore -f appdb.sql
~~~

Ý nghĩa:

- `-X`: không đọc psqlrc của user/system, giúp script ít phụ thuộc môi trường.
- `-h`, `-p`: chọn host/port.
- `-U`: role kết nối.
- `-d`: database đích.
- `-f`: file SQL cần chạy.

Đối với script restore tự động, nên bật `ON_ERROR_STOP`:

~~~bash
psql -X -v ON_ERROR_STOP=1 -h target.example -U restore_user -d appdb_restore -f appdb.sql
~~~

Khi có lỗi SQL, psql dừng script và trả exit code khác 0 theo chế độ này.

## 10. Restore plain dump có CREATE DATABASE

Nếu dump được tạo bằng `pg_dump --create`, script có thể chứa lệnh tạo database và psql connect meta-command sang database đó.

Ví dụ:

~~~bash
psql -X -v ON_ERROR_STOP=1 -h target.example -U db_admin -d postgres -f appdb-create.sql
~~~

Kết nối vào maintenance database. Dump tự tạo database theo metadata và chuyển kết nối.

Không chạy script loại này với `psql --single-transaction` nếu nó có CREATE DATABASE, vì PostgreSQL không cho phép CREATE DATABASE bên trong transaction block.

## 11. Restore custom archive bằng pg_restore

Nếu đã tạo database đích:

~~~bash
createdb -h target.example -U db_admin -T template0 appdb_restore

pg_restore -h target.example -U restore_user -d appdb_restore appdb.dump
~~~

`pg_restore` đọc archive, tạo schema và nạp data theo thứ tự dependency được ghi trong archive.

Mặc định pg_restore có thể tiếp tục sau một số lỗi, ghi lỗi và báo tổng số lỗi khi kết thúc. Nếu muốn dừng ở lỗi đầu tiên, dùng `--exit-on-error`.

~~~bash
pg_restore --exit-on-error -h target.example -U restore_user -d appdb_restore appdb.dump
~~~

### 11.1. Xem archive trước khi restore

~~~bash
pg_restore --list appdb.dump
~~~

Lệnh hiển thị Table of Contents (TOC): schema, tables, data, indexes, constraints, functions và các object khác có trong archive.

## 12. pg_restore --create

Có thể yêu cầu pg_restore tạo database được ghi trong archive:

~~~bash
pg_restore --create -h target.example -U db_admin -d postgres appdb.dump
~~~

Khi dùng `--create`, database được tạo theo tên được lưu trong archive. `-d postgres` là database maintenance để pg_restore kết nối trước khi tạo và chuyển sang database đích.

Nếu muốn restore vào database có tên khác, tạo database đó trước và dùng `-d appdb_restore` **không** thêm `--create`.

### 12.1. Không nhầm -d với tên database nguồn

- Không có `--create`: `-d` là database nhận object/data.
- Có `--create`: `-d` là database maintenance dùng để thực hiện CREATE DATABASE, còn tên database được lấy từ archive.

## 13. Xử lý owner và privileges

Dump có thể chứa ownership và ACL từ source. Target có thể không có các roles đó.

Với custom archive:

~~~bash
pg_restore --no-owner --no-privileges -d appdb_restore appdb.dump
~~~

- `--no-owner`: không phát lệnh khôi phục owner cũ; objects thường thuộc role thực hiện restore.
- `--no-privileges` (còn gọi `--no-acl`): bỏ các GRANT/REVOKE đã dump.

Với plain dump, các lựa chọn tương ứng có thể được đặt khi tạo dump:

~~~bash
pg_dump --no-owner --no-acl -f appdb.sql appdb
~~~

Không bỏ ownership/ACL nếu hệ thống cần giữ chính xác mô hình quyền. Quyết định dựa trên mapping roles ở target.

## 14. Roles và global objects

`pg_dump` không dump roles và tablespaces cluster-wide. Nếu restore object có owner hoặc grant cho role chưa tồn tại, restore có thể báo lỗi.

Có thể xuất globals riêng:

~~~bash
pg_dumpall --globals-only -h source.example -U postgres -f globals.sql
~~~

Restore globals bằng role quản trị phù hợp:

~~~bash
psql -X -v ON_ERROR_STOP=1 -h target.example -U postgres -d postgres -f globals.sql
~~~

Sau đó restore database dump.

### 14.1. Không khôi phục password hashes vô thức

Global dump có thể chứa role definitions và password hashes. Chỉ restore trong môi trường tin cậy, giới hạn quyền đọc file và review chính sách credential trước khi áp dụng.

## 15. Extensions và dependencies

Nếu dump có:

~~~sql
CREATE EXTENSION some_extension;
~~~

server đích phải có extension package tương ứng được cài đặt ở cấp hệ điều hành/PostgreSQL installation. Chỉ có SQL dump không tự cài binary extension.

Trước restore:

- Liệt kê extension source.
- Cài package tương thích trên target.
- Xác minh version.
- Kiểm tra extension dependencies.
- Đảm bảo restore role có quyền cần thiết.

Xem extensions hiện tại ở source:

~~~sql
SELECT extname, extversion
FROM pg_extension
ORDER BY extname;
~~~

## 16. PostgreSQL version compatibility

Quy tắc thực dụng:

- Dùng `pg_dump` cùng major version hoặc mới hơn server nguồn; pg_dump không hỗ trợ dump server mới hơn major version của chính nó.
- Dump logic thường được thiết kế để chuyển dữ liệu sang PostgreSQL mới hơn.
- Restore ngược về major version cũ hơn không được bảo đảm.
- Extension, collation, data types, functions và SQL syntax có thể tạo incompatibility.
- Physical backup có quy tắc version compatibility khác với logical dump.

Kiểm tra version:

~~~sql
SELECT version();
~~~

và:

~~~bash
pg_dump --version
pg_restore --version
psql --version
~~~

Không chỉ so sánh số version client; xác minh source/target major versions và extension compatibility.

## 17. Encoding, locale và collation

Một database được tạo với encoding/collation khác có thể gây lỗi hoặc thay đổi thứ tự so sánh/sort.

Kiểm tra source:

~~~sql
SELECT
    datname,
    pg_encoding_to_char(encoding) AS encoding,
    datcollate,
    datctype
FROM pg_database
WHERE datname = current_database();
~~~

Kiểm tra target trước restore. Với database cần tái tạo tương thích, dùng `template0` và chọn encoding/locale phù hợp.

Một số collation dựa trên ICU/libc có thể phụ thuộc OS và version. Thay đổi collation version có thể ảnh hưởng indexes; xử lý theo hướng dẫn PostgreSQL tương ứng.

## 18. Restore vào database không rỗng

Nếu target đã có tables/indexes, restore có thể gặp:

- `relation already exists`.
- Duplicate keys.
- Existing functions/types.
- Conflicting owners/ACL.
- Constraint/index name collision.
- Data duplicated hoặc không nạp được.

Cách an toàn thường là restore vào database mới, kiểm tra, sau đó chuyển ứng dụng/routing.

Nếu bắt buộc restore chồng, phải xác định rõ object scope và dùng `--clean`/`--if-exists` cẩn trọng.

## 19. --clean và --if-exists

Với pg_restore:

~~~bash
pg_restore --clean --if-exists -d appdb_restore appdb.dump
~~~

- `--clean`: phát lệnh DROP cho objects trước khi tạo lại.
- `--if-exists`: dùng điều kiện IF EXISTS khi drop nếu phù hợp, giảm lỗi khi object chưa tồn tại.

Đây có thể là thao tác phá hủy dữ liệu/object hiện có. Chỉ dùng khi target được xác định rõ và đã có backup/approval phù hợp.

### 19.1. --clean không reset toàn cluster

Nó xử lý objects nằm trong archive và phạm vi restore. Nó không tự xóa mọi object hoặc mọi database ngoài archive.

## 20. Restore schema-only và data-only

Custom archive cho phép chọn nội dung:

**Chỉ schema:**

~~~bash
pg_restore --schema-only -d appdb_restore appdb.dump
~~~

**Chỉ data:**

~~~bash
pg_restore --data-only -d appdb_restore appdb.dump
~~~

Schema-only tạo object definitions, data-only nạp dữ liệu vào schema đã có.

### 20.1. Data-only cần schema tương thích

Nếu tables/columns/types/constraints không tương thích, data restore có thể lỗi. Kiểm tra schema version và dependencies trước.

## 21. Restore theo section

Archive có các sections chính:

- `pre-data`: definitions cần trước data, ví dụ tables/types/functions tùy object.
- `data`: table data, large objects, sequence values.
- `post-data`: indexes, constraints, triggers và object cần sau data.

Ví dụ:

~~~bash
pg_restore --section=pre-data -d appdb_restore appdb.dump
pg_restore --section=data -d appdb_restore appdb.dump
pg_restore --section=post-data -d appdb_restore appdb.dump
~~~

Chạy riêng sections hữu ích cho migration/debug, nhưng phải giữ thứ tự và dependencies phù hợp. Nếu một phase lỗi, phải dừng và xử lý trước phase kế tiếp.

## 22. Restore chọn schema/table

Có thể lọc archive:

~~~bash
pg_restore --schema=public -d appdb_restore appdb.dump
~~~

Chọn table:

~~~bash
pg_restore --table=orders -d appdb_restore appdb.dump
~~~

Tên object/schema cần khớp với TOC và quy tắc quoting. Restore một table có thể cần types, sequences, functions, referenced tables hoặc extensions liên quan.

### 22.1. Partial restore không tự giải quyết dependencies

Nếu chọn riêng table nhưng bỏ qua type/function/sequence mà table cần, restore có thể lỗi. Dùng `pg_restore --list` và kiểm tra dependency trước.

## 23. TOC list và file chọn object

Có thể xuất TOC:

~~~bash
pg_restore --list appdb.dump > restore.list
~~~

Sau đó chỉnh file list để chọn những entries muốn restore và chạy:

~~~bash
pg_restore --use-list=restore.list -d appdb_restore appdb.dump
~~~

Tên option rút gọn thường là `-L`.

Giữ file TOC gốc để có thể so sánh. Một dòng bị bỏ có thể khiến object phụ thuộc không được restore.

## 24. Parallel restore

Custom và directory archive hỗ trợ parallel restore bằng `-j`:

~~~bash
pg_restore -j 4 -d appdb_restore appdb.dump
~~~

PostgreSQL có thể restore nhiều objects/data tasks độc lập đồng thời, giảm thời gian khi CPU, disk và target có đủ năng lực.

Parallelism tăng số connections, disk I/O, CPU usage, WAL generation concurrency và pressure lên shared resources. Benchmark số jobs phù hợp với target hardware và workload.

### 24.1. Parallel restore không dùng cùng --single-transaction

`pg_restore --single-transaction` không thể kết hợp với `-j`. Chọn một trong hai: restore song song hoặc một transaction all-or-nothing.

## 25. --single-transaction của pg_restore

~~~bash
pg_restore --single-transaction -d appdb_restore appdb.dump
~~~

Tùy chọn này bọc restore trong một transaction duy nhất. Nếu một lệnh restore thất bại, transaction rollback để tránh để lại một phần restore đã commit.

Tùy chọn này ngụ ý `--exit-on-error` và không tương thích với parallel jobs.

### 25.1. Khi nào phù hợp?

- Dump vừa phải.
- Các commands trong archive có thể chạy trong transaction.
- Cần all-or-nothing.
- Target mới và chưa được sử dụng.

### 25.2. Khi nào không phù hợp?

- Archive rất lớn, transaction kéo dài.
- Cần parallel restore.
- Có commands không thể chạy trong transaction block.
- Cần chia restore thành các phase độc lập.
- Có yêu cầu vận hành/lock không phù hợp với transaction dài.

`CREATE DATABASE`, `CREATE TABLESPACE`, `VACUUM` và một số commands khác không chạy được bên trong transaction block. Nếu restore có những commands này, không bọc toàn bộ trong một transaction.

## 26. psql ON_ERROR_STOP

Mặc định psql có thể tiếp tục thực thi các lệnh tiếp theo sau một SQL error trong script.

Để dừng khi gặp lỗi:

~~~bash
psql -X -v ON_ERROR_STOP=1 -d appdb_restore -f restore.sql
~~~

Hoặc ở đầu file script dùng psql variable ON_ERROR_STOP với giá trị on.

Khi bật ON_ERROR_STOP, lỗi SQL trong script khiến psql dừng và trả exit status khác 0.

### 26.1. Exit code của psql

Trong chế độ không tương tác, các exit statuses quan trọng:

| Exit code | Ý nghĩa |
|---|---|
| `0` | Hoàn tất bình thường |
| `1` | Lỗi nghiêm trọng phía psql, ví dụ lỗi file hoặc resource |
| `2` | Kết nối tới server bị lỗi trong chế độ không tương tác |
| `3` | Lỗi trong script khi ON_ERROR_STOP được bật |

Script gọi psql phải kiểm tra exit code, không chỉ xem log có dòng ERROR hay không.

## 27. ON_ERROR_STOP không giống ON_ERROR_ROLLBACK

`ON_ERROR_STOP` điều khiển **có dừng script hay không** khi xảy ra lỗi.

`ON_ERROR_ROLLBACK` điều khiển psql xử lý lỗi trong transaction bằng savepoint.

Khi ON_ERROR_ROLLBACK bật, psql tự tạo savepoint trước mỗi command trong transaction; nếu command lỗi, psql rollback tới savepoint để transaction có thể tiếp tục.

Cơ chế này hữu ích trong một số phiên làm việc tương tác, nhưng không thay thế chiến lược fail-fast cho restore.

### 27.1. Vì sao không bật ON_ERROR_ROLLBACK để “restore cho xong”?

Nếu lỗi bị rollback riêng statement và script tiếp tục, database có thể ở trạng thái thiếu một phần object/data. Đây thường không phải kết quả mong muốn cho một lần restore cần đầy đủ.

## 28. Dùng psql single transaction

Với một script SQL phù hợp, có thể dùng:

~~~bash
psql -X -v ON_ERROR_STOP=1 --single-transaction -d appdb_restore -f schema-and-data.sql
~~~

psql mở transaction trước các input commands và commit sau khi hoàn tất. Khi có lỗi với ON_ERROR_STOP, transaction có thể được rollback thay vì giữ phần thay đổi đã chạy trước đó.

Không dùng với script có CREATE DATABASE, CREATE TABLESPACE, VACUUM, psql connect meta-command hoặc các commands cần nằm ngoài transaction. Cũng cần tránh nếu script tự quản lý BEGIN/COMMIT theo cách xung đột.

## 29. Transaction scope và restore lớn

Một transaction restore duy nhất có lợi cho atomicity nhưng có chi phí:

- Transaction tồn tại lâu.
- Locks có thể được giữ lâu.
- Rollback khi lỗi có thể tốn thời gian.
- Snapshot/transaction state tồn tại lâu hơn.
- Có thể ảnh hưởng vacuum và workload khác.
- Toàn bộ restore chỉ được commit ở cuối.

Với database lớn, restore vào database riêng biệt chưa được ứng dụng sử dụng thường dễ vận hành hơn việc cố bọc mọi thứ trong một transaction duy nhất.

## 30. pg_restore --exit-on-error

Mặc định pg_restore có thể tiếp tục sau lỗi để cố gắng restore các objects khác và tổng hợp số lỗi cuối cùng.

Nếu muốn dừng ngay:

~~~bash
pg_restore --exit-on-error -d appdb_restore appdb.dump
~~~

Tùy chọn này phù hợp khi bất kỳ lỗi nào cũng khiến restore không được chấp nhận.

Nếu muốn thử khôi phục tối đa dữ liệu để phân tích, có thể dùng mặc định rồi kiểm tra toàn bộ error summary; nhưng không coi một lần restore có lỗi là thành công.

## 31. Kết hợp pg_restore với transaction

All-or-nothing, không parallel:

~~~bash
pg_restore --single-transaction -d appdb_restore appdb.dump
~~~

Fail-fast, có thể parallel:

~~~bash
pg_restore --exit-on-error -j 4 -d appdb_restore appdb.dump
~~~

Không thể dùng single transaction cùng parallel jobs. Nếu restore song song, cần một target riêng và quy trình xác minh/cleanup rõ ràng khi có job lỗi.

## 32. Phân biệt lỗi SQL và lỗi vận hành

Một restore có thể thất bại vì:

**Lỗi SQL/object:**

- Role không tồn tại.
- Table/type đã tồn tại.
- Duplicate key.
- Extension thiếu.
- Function/operator không tương thích.
- Permission denied.

**Lỗi môi trường/vận hành:**

- Không kết nối được.
- Disk full.
- WAL/disk pressure.
- File dump không đọc được.
- Archive hỏng.
- Network timeout.
- Server restart.
- Client/server version không tương thích.

Đọc error đầu tiên và context trước khi quyết định sửa. Một lỗi ở đầu restore có thể kéo theo hàng trăm lỗi phụ thuộc phía sau.

## 33. Log restore và verbose

Với pg_restore:

~~~bash
pg_restore --verbose --exit-on-error -d appdb_restore appdb.dump > restore.log 2>&1
~~~

Với psql:

~~~bash
psql -X -v ON_ERROR_STOP=1 -d appdb_restore -f appdb.sql > restore.log 2>&1
~~~

Log cần bảo vệ vì có thể chứa object names, SQL text hoặc dữ liệu nhạy cảm tùy loại error/verbosity.

Ghi lại thời điểm bắt đầu/kết thúc, command và tool versions, target database/server, exit code, số lỗi, restore duration và file dump/checksum.

Không ghi password vào command line/log.

## 34. Shell script cần giữ đúng exit code

Ví dụ Bash:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

pg_restore \
  --verbose \
  --exit-on-error \
  --dbname=appdb_restore \
  appdb.dump \
  >restore.log 2>&1

echo "Restore completed successfully"
~~~

`set -euo pipefail` giúp script dừng khi command thất bại, biến chưa được đặt nếu có dùng hoặc pipeline có command lỗi.

Nếu dùng `tee` để vừa hiển thị vừa lưu log:

~~~bash
set -o pipefail
pg_restore --exit-on-error -d appdb_restore appdb.dump 2>&1 | tee restore.log
~~~

Không bỏ `pipefail`: nếu không, shell có thể lấy exit code của tee thay vì pg_restore.

## 35. PowerShell và exit code của client

Trong PowerShell, native programs như psql/pg_restore trả exit code qua `LASTEXITCODE`.

~~~powershell
$ErrorActionPreference = 'Stop'

& pg_restore --verbose --exit-on-error --dbname=appdb_restore appdb.dump 2>&1 |
    Tee-Object -FilePath restore.log

if ($LASTEXITCODE -ne 0) {
    throw "pg_restore failed with exit code $LASTEXITCODE"
}

Write-Output "Restore completed successfully"
~~~

`ErrorActionPreference` điều khiển PowerShell errors, còn `LASTEXITCODE` là exit code của native executable. Không nhầm hai cơ chế.

Với pipeline phức tạp, nên kiểm tra kỹ cách shell/version xử lý native command exit status; cách đơn giản nhất là chạy command trực tiếp, lưu log và kiểm tra LASTEXITCODE ngay sau command.

## 36. Truyền password an toàn

Không viết password trực tiếp trong command line. Tùy chọn `-W` chỉ yêu cầu prompt password; không nhận password như một argument phía sau.

Ưu tiên:

- `.pgpass` trên Unix-like systems.
- `PGPASSFILE` với file có permissions phù hợp.
- Service definitions và secret manager theo môi trường.
- Interactive prompt khi vận hành thủ công.

Không đưa password vào source control, shell history, process list hoặc log.

## 37. Kiểm tra archive trước khi restore

Với custom/directory/tar:

~~~bash
pg_restore --list appdb.dump
~~~

Kiểm tra:

- Có schema/table mong muốn?
- Có data entries?
- Có sequences?
- Có large objects nếu ứng dụng dùng?
- Có functions/extensions?
- Có owners/ACL?
- Có tablespaces?
- Có object nào không muốn restore?

Có thể xuất TOC ra file để review:

~~~bash
pg_restore --list appdb.dump > appdb.toc
~~~

Đây là bước đọc metadata archive, chưa thay đổi database đích.

## 38. Kiểm tra dump file và checksum

Với file dump được truyền qua network/storage, nên có checksum:

~~~bash
sha256sum appdb.dump
~~~

Ở Windows:

~~~powershell
Get-FileHash -Algorithm SHA256 -LiteralPath .\appdb.dump
~~~

So sánh checksum với manifest/nguồn đáng tin. Checksum chỉ xác nhận bytes giống nhau, không chứng minh dump có thể restore thành công.

## 39. Restore theo pre-data/data/post-data

Một quy trình có kiểm soát có thể tách sections:

~~~bash
pg_restore --section=pre-data --exit-on-error -d appdb_restore appdb.dump
pg_restore --section=data --exit-on-error -d appdb_restore appdb.dump
pg_restore --section=post-data --exit-on-error -d appdb_restore appdb.dump
~~~

Cách này giúp phân tích lỗi theo giai đoạn và có thể cho phép nạp dữ liệu trước khi tạo indexes/constraints.

Nếu một phase lỗi, phải dừng và xử lý trước phase kế tiếp. Không giả định chạy lại toàn bộ lệnh sẽ tự động sửa mọi trạng thái một phần.

## 40. Restore data-only và triggers

Một số trường hợp data-only restore có thể cần kiểm soát triggers/foreign keys.

pg_restore có tùy chọn `--disable-triggers` cho một số data-only restores; việc này đòi hỏi quyền cao (thường superuser) và có rủi ro nếu triggers không được bật lại đúng cách.

Không dùng để né constraint errors mà chưa hiểu dữ liệu. Nếu có foreign key violations, hãy xác định dependency/order và tính toàn vẹn của dump.

## 41. Sequence values sau restore

Sequence là object riêng. Dump logic thường chứa lệnh khôi phục sequence state phù hợp.

~~~sql
SELECT
    schemaname,
    sequencename,
    last_value
FROM pg_sequences
WHERE schemaname = 'public'
ORDER BY sequencename;
~~~

`last_value`/`is_called` semantics cần được hiểu khi kiểm tra sequence cụ thể. Test INSERT mới để xác nhận sequence không phát ID trùng với dữ liệu hiện có.

## 42. Large Objects trong dump

Large Objects là subsystem riêng của PostgreSQL, nhưng pg_dump mặc định có thể dump large objects cùng database; tùy chọn `--blobs`/`--no-blobs` điều khiển phạm vi này.

Nếu ứng dụng dùng OID references:

- Xác nhận dump có LO contents.
- Xác nhận restore có đủ LO objects.
- Kiểm tra OID references.
- Kiểm tra large object privileges.
- Kiểm tra quy trình backup/restore.

Một row metadata có OID nhưng object contents không được restore sẽ tạo reference không sử dụng được.

## 43. Restore xong cần ANALYZE

Sau khi nạp lượng lớn dữ liệu, planner statistics có thể chưa phản ánh dữ liệu mới đầy đủ.

~~~sql
ANALYZE;
~~~

Hoặc dùng công cụ:

~~~bash
vacuumdb --analyze-in-stages -d appdb_restore
~~~

Chọn lệnh phù hợp với size và trạng thái database. Không chạy VACUUM FULL chỉ vì vừa restore; mục tiêu ở đây là cập nhật planner statistics và maintenance phù hợp.

## 44. Xác minh sau restore

Không chỉ kiểm tra command exit code. Xác minh:

1. Database tồn tại và kết nối được.
2. Schema/tables/views/functions đúng.
3. Row counts hợp lý.
4. Primary/foreign keys và constraints hiện diện.
5. Indexes đã được tạo.
6. Sequence values không gây trùng ID.
7. Extensions và versions phù hợp.
8. Owners/GRANT/RLS đúng.
9. Large Objects hoặc object references hoạt động.
10. Application smoke tests chạy được.
11. Log không có errors chưa được chấp nhận.
12. Restore duration phù hợp RTO.

Ví dụ đếm nhanh:

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup
FROM pg_stat_user_tables
ORDER BY schemaname, relname;
~~~

`n_live_tup` là estimate; với bảng quan trọng, chạy COUNT có kiểm soát hoặc đối chiếu manifest/business invariants.

## 45. Restore vào database mới rồi chuyển ứng dụng

~~~text
Production database cũ
        |
        +--> tạo dump
        |
        v
Restore vào database mới
        |
        v
Xác minh schema/data/permissions
        |
        v
Chạy smoke tests
        |
        v
Chuyển connection string/routing
        |
        v
Theo dõi ứng dụng
~~~

Giữ database cũ theo retention/change window cho đến khi việc chuyển đổi được xác nhận. Quy trình rename/swap database cần xử lý connections, locks, ownership và downtime rõ ràng.

## 46. Troubleshooting: role does not exist

Triệu chứng:

~~~text
ERROR: role "app_owner" does not exist
~~~

Nguyên nhân: dump giữ owner/grants từ source nhưng target chưa có role.

Cách xử lý:

- Restore global roles trước nếu được phép.
- Hoặc dùng `--no-owner --no-privileges` nếu target có mô hình quyền mới.
- Hoặc tạo role mapping theo chính sách.
- Không tạo superuser chỉ để bỏ qua một lỗi owner.

## 47. Troubleshooting: relation already exists

Triệu chứng:

~~~text
ERROR: relation "orders" already exists
~~~

Nguyên nhân: target không rỗng hoặc restore đã chạy một phần.

Cách xử lý:

- Xác định object có dữ liệu quan trọng không.
- Với target disposable, tạo database mới là cách sạch.
- Với target đã có dữ liệu, review `--clean --if-exists` và scope.
- Không DROP schema/database nếu chưa xác định target.

## 48. Troubleshooting: extension missing

Triệu chứng:

~~~text
ERROR: extension "some_extension" is not available
~~~

Cài extension package đúng version trên target, xác minh server có control file/shared library cần thiết rồi chạy lại restore theo trạng thái database hiện tại.

Một câu lệnh CREATE EXTENSION trong dump không tải binary extension từ source.

## 49. Troubleshooting: permission denied

Kiểm tra:

- Role đang kết nối.
- Database CONNECT/CREATE privileges.
- Schema USAGE/CREATE.
- Owner và role membership.
- Tablespace access.
- Extension installation permissions.
- Superuser-only commands trong dump.

Dùng role có quyền tối thiểu cần thiết nhưng đủ để restore. Không cấp SUPERUSER rộng cho application role.

## 50. Troubleshooting: restore dừng giữa chừng

Với psql ON_ERROR_STOP, script dừng tại lỗi đầu tiên. Với pg_restore --exit-on-error, restore cũng dừng tại lỗi đầu tiên.

Database có thể còn một phần objects/data đã commit nếu không chạy trong single transaction.

Cách phục hồi:

1. Lưu log và exit code.
2. Xác định object/statement đầu tiên thất bại.
3. Xác định restore có single transaction hay không.
4. Kiểm tra database hiện tại có phải target disposable không.
5. Sửa nguyên nhân.
6. Ưu tiên restore lại vào database mới nếu cần trạng thái sạch.
7. Chỉ resume theo TOC/section khi hiểu dependencies và những phần đã hoàn tất.

Không chạy lại toàn bộ dump mù quáng trên target nửa chừng.

## 51. Troubleshooting: disk full hoặc WAL tăng mạnh

Restore lớn có thể tạo nhiều WAL, indexes và temporary files.

Theo dõi:

- Free disk space trên data directory và tablespace.
- `pg_wal` size.
- WAL archive success/failure.
- Replication slots và standby lag.
- Temporary files.
- Index build progress.
- Storage IOPS/latency.

Nếu disk sắp đầy, dừng quy trình theo cách có kiểm soát và xác định target state. Không xóa WAL files thủ công để lấy chỗ.

## 52. Troubleshooting: encoding hoặc invalid byte sequence

Kiểm tra dump encoding, database encoding và client encoding:

~~~sql
SHOW server_encoding;
SHOW client_encoding;
~~~

Dump được pg_dump tạo thường có thông tin encoding cần thiết. Nếu chuyển dữ liệu qua text tools, tránh thay đổi encoding hoặc line endings không đúng cách.

Không bỏ qua invalid byte sequence bằng cách thay thế ký tự ngẫu nhiên; cần xác định dữ liệu nguồn và encoding chính xác.

## 53. Troubleshooting: client và server version

Nếu client quá cũ so với server nguồn, pg_dump có thể từ chối kết nối/dump. Nếu archive được tạo bởi tool mới hơn, pg_restore cũ có thể không hiểu archive version.

Dùng pg_dump/pg_restore phù hợp với source/target major versions và kiểm tra `--version` trước khi chạy.

## 54. Script restore có thể chạy lại an toàn không?

Không mặc định.

Một script có thể tạo object, insert data, gọi function hoặc thực hiện side effects. Chạy lại có thể:

- Lỗi duplicate objects/keys.
- Nhân đôi rows nếu dump dùng INSERT.
- Đổi sequence state.
- Gọi trigger nhiều lần.
- Drop/recreate objects nếu có `--clean`.
- Tạo dữ liệu phụ ngoài database nếu script có external commands.

Muốn idempotent, phải thiết kế script có chủ đích: target mới, kiểm tra preconditions, migration versioning và rollback strategy.

## 55. psql meta-commands trong script

Plain dump có thể chứa psql meta-commands như connect, set, echo, include file và các lệnh kiểm soát script. Đây không phải SQL statements gửi trực tiếp tới server; psql diễn giải chúng ở client.

Vì vậy, không chạy một plain pg_dump script bằng driver JDBC SQL statement executor thông thường. Dùng psql để xử lý cả SQL và psql meta-commands.

## 56. Bảo mật khi restore dump không tin cậy

Một dump SQL có thể chứa commands được chọn bởi người tạo dump, gồm function definitions, triggers, extension declarations và SQL khác.

Không restore dump từ nguồn không tin cậy vào production bằng superuser.

Thực hành:

- Xác minh nguồn/checksum.
- Review TOC hoặc SQL text.
- Restore vào isolated database/instance.
- Dùng role ít quyền nhất có thể.
- Dùng `-X` để không nạp psqlrc ngoài ý muốn.
- Xem xét `--no-owner` và `--no-privileges`.
- Kiểm tra extensions trước khi cài.
- Không để script đọc secrets ngoài phạm vi.

`--no-owner`/`--no-acl` không biến một dump độc hại thành an toàn; vẫn phải review nội dung và nguồn.

## 57. Lựa chọn error policy

| Mục tiêu | psql | pg_restore |
|---|---|---|
| Dừng ngay khi có lỗi | `ON_ERROR_STOP=1` | `--exit-on-error` |
| All-or-nothing nếu commands phù hợp | `--single-transaction` + `ON_ERROR_STOP` | `--single-transaction` |
| Tiếp tục để thu thập nhiều lỗi | Mặc định không bật ON_ERROR_STOP | Mặc định có thể tiếp tục và báo lỗi |
| Phục hồi parallel | Không áp dụng theo cách tương đương | `-j N`, không kết hợp single transaction |
| Log chi tiết | Redirect output/psql logging | `--verbose` và redirect output |

Chọn policy trước khi chạy, không quyết định sau khi restore đã tạo một phần trạng thái.

## 58. Quy trình restore mẫu: custom archive

~~~bash
# 1. Kiểm tra client.
pg_restore --version

# 2. Xem TOC.
pg_restore --list appdb.dump > appdb.toc

# 3. Tạo database mới.
createdb -h target.example -U db_admin -T template0 appdb_restore

# 4. Restore, dừng khi lỗi.
pg_restore \
  --verbose \
  --exit-on-error \
  --no-owner \
  --no-privileges \
  -h target.example \
  -U restore_user \
  -d appdb_restore \
  appdb.dump

# 5. Chạy analyze sau khi restore thành công.
vacuumdb --analyze-in-stages -h target.example -U db_admin -d appdb_restore
~~~

Các lựa chọn `--no-owner` và `--no-privileges` chỉ dùng khi chính sách target yêu cầu. Nếu cần giữ ownership/ACL, chuẩn bị roles và permissions trước rồi bỏ hai options này.

## 59. Quy trình restore mẫu: plain SQL

~~~bash
psql \
  -X \
  -v ON_ERROR_STOP=1 \
  -h target.example \
  -U restore_user \
  -d appdb_restore \
  -f appdb.sql
~~~

Nếu dump có `--create`, kết nối tới maintenance database theo hướng dẫn ở phần trước.

Đối với script có thể chạy trong một transaction:

~~~bash
psql \
  -X \
  -v ON_ERROR_STOP=1 \
  --single-transaction \
  -h target.example \
  -U restore_user \
  -d appdb_restore \
  -f schema-and-data.sql
~~~

Chỉ dùng single transaction khi script không chứa commands cần chạy ngoài transaction và không tự quản lý transaction xung đột.

## 60. Checklist trước khi chạy restore

**Dump và target**

1. Đã xác định đúng plain/custom/directory/tar?
2. File dump có checksum/nguồn đáng tin?
3. Client tools tương thích source/target versions?
4. Target host/port/database đã xác nhận?
5. Target có đang được ứng dụng sử dụng?
6. Dung lượng disk/WAL đủ?
7. Có backup/rollback plan?

**Dependencies**

8. Roles và tablespaces đã chuẩn bị?
9. Extensions đã cài đúng version?
10. Encoding/locale/collation phù hợp?
11. Owner/ACL sẽ được giữ hay mapping?
12. Có large objects cần restore?

**Error policy**

13. psql có ON_ERROR_STOP?
14. pg_restore có --exit-on-error?
15. Có nên dùng single transaction?
16. Có cần parallel jobs?
17. Có command không thể chạy trong transaction?
18. Log và exit code được lưu?

**Sau restore**

19. Schema/data/sequence/indexes đúng?
20. Constraints/permissions/RLS đúng?
21. ANALYZE đã chạy?
22. Smoke tests thành công?
23. Restore duration/RPO/RTO được ghi nhận?
24. Có kế hoạch chuyển ứng dụng và giữ target cũ?

## 61. Bài tập thực hành

### Bài 1 — Dump format

Nêu bốn định dạng pg_dump phổ biến.

**Gợi ý:** plain, custom, directory, tar.

### Bài 2 — Công cụ restore

Plain SQL dump dùng công cụ nào?

**Gợi ý:** psql.

### Bài 3 — Custom archive

Custom archive dùng công cụ nào?

**Gợi ý:** pg_restore.

### Bài 4 — Tạo custom dump

Viết lệnh tạo custom archive cho database appdb.

**Gợi ý:** pg_dump -Fc.

### Bài 5 — Directory format

Format nào hỗ trợ parallel dump và restore?

**Gợi ý:** directory.

### Bài 6 — pg_dumpall

Vì sao cần pg_dumpall khi muốn xuất roles và nhiều databases?

**Gợi ý:** pg_dump chỉ dump một database; pg_dumpall có globals/all DBs.

### Bài 7 — Globals

Viết lệnh xuất global objects.

**Gợi ý:** pg_dumpall --globals-only.

### Bài 8 — Plain restore

Viết lệnh psql restore có ON_ERROR_STOP.

**Gợi ý:** psql -X -v ON_ERROR_STOP=1 -f.

### Bài 9 — Archive list

Lệnh nào xem TOC của custom dump?

**Gợi ý:** pg_restore --list.

### Bài 10 — Create database

pg_restore --create lấy database name từ đâu?

**Gợi ý:** metadata archive.

### Bài 11 — Maintenance database

Khi dùng --create, -d thường trỏ tới đâu?

**Gợi ý:** database maintenance như postgres.

### Bài 12 — Owner

--no-owner có tác dụng gì?

**Gợi ý:** không khôi phục owner source.

### Bài 13 — ACL

--no-privileges tương đương lựa chọn nào?

**Gợi ý:** --no-acl.

### Bài 14 — Extensions

Tại sao CREATE EXTENSION trong dump có thể thất bại trên target?

**Gợi ý:** package/binary extension chưa được cài.

### Bài 15 — Versions

Có thể dùng pg_dump cũ hơn major version server mới hơn không?

**Gợi ý:** không được hỗ trợ; pg_dump từ chối server mới hơn major của client.

### Bài 16 — Clean

--clean làm gì?

**Gợi ý:** drop objects trước khi tạo lại.

### Bài 17 — if-exists

--if-exists dùng cùng option nào?

**Gợi ý:** thường đi với --clean.

### Bài 18 — Schema-only

Viết lệnh restore chỉ schema.

**Gợi ý:** pg_restore --schema-only.

### Bài 19 — Data-only

Viết lệnh restore chỉ data.

**Gợi ý:** pg_restore --data-only.

### Bài 20 — Sections

Nêu ba sections chính.

**Gợi ý:** pre-data, data, post-data.

### Bài 21 — TOC list

File TOC đã chỉnh sửa được dùng với option nào?

**Gợi ý:** --use-list/-L.

### Bài 22 — Parallel

Viết lệnh restore 4 jobs.

**Gợi ý:** pg_restore -j 4.

### Bài 23 — Single transaction

pg_restore --single-transaction có tương thích -j không?

**Gợi ý:** không.

### Bài 24 — Exit on error

Option nào khiến pg_restore dừng ở lỗi đầu tiên?

**Gợi ý:** --exit-on-error.

### Bài 25 — psql error stop

Variable nào làm psql dừng khi script gặp lỗi?

**Gợi ý:** ON_ERROR_STOP.

### Bài 26 — psql exit code

Exit code 3 có ý nghĩa gì?

**Gợi ý:** script error khi ON_ERROR_STOP được bật.

### Bài 27 — ON_ERROR_ROLLBACK

Khác ON_ERROR_STOP ở đâu?

**Gợi ý:** savepoint rollback statement vs dừng script.

### Bài 28 — psql single transaction

Khi nào nên dùng --single-transaction?

**Gợi ý:** script phù hợp transaction và cần all-or-nothing.

### Bài 29 — CREATE DATABASE

Vì sao không thể bọc CREATE DATABASE trong transaction?

**Gợi ý:** PostgreSQL không cho phép command này trong transaction block.

### Bài 30 — Shell pipefail

Vì sao cần pipefail khi dùng tee?

**Gợi ý:** giữ exit code lỗi của command trong pipeline.

### Bài 31 — PowerShell

Biến nào chứa exit code của native executable?

**Gợi ý:** LASTEXITCODE.

### Bài 32 — Password

Vì sao không đặt password trong command line?

**Gợi ý:** process list/history/log exposure.

### Bài 33 — Large objects

Vì sao cần kiểm tra LO khi restore?

**Gợi ý:** OID reference có thể thiếu object contents/privileges.

### Bài 34 — Sequence

Sau restore cần test điều gì với sequences?

**Gợi ý:** INSERT mới không sinh ID trùng.

### Bài 35 — ANALYZE

Vì sao chạy ANALYZE sau restore lớn?

**Gợi ý:** cập nhật planner statistics.

### Bài 36 — Partial restore

Vì sao restore riêng một table có thể thất bại?

**Gợi ý:** thiếu type/function/sequence/dependencies.

### Bài 37 — Nonempty target

Lỗi relation already exists thường chỉ ra điều gì?

**Gợi ý:** target có object hoặc restore đã chạy một phần.

### Bài 38 — Disk full

Vì sao không xóa WAL files thủ công để tiếp tục restore?

**Gợi ý:** có thể phá recovery/replication/archive continuity.

### Bài 39 — Restore security

Vì sao không restore dump không tin cậy bằng superuser?

**Gợi ý:** dump có thể chứa SQL/commands tùy ý.

### Bài 40 — Chọn error policy

Một restore cần all-or-nothing, archive vừa phải và không cần parallel. Chọn option nào?

**Gợi ý:** pg_restore --single-transaction.

## 62. Câu hỏi thường gặp

### Có thể dùng psql để restore custom dump không?

Không. Custom/directory/tar archive dùng pg_restore; plain SQL dùng psql.

### pg_restore mặc định có dừng ở lỗi đầu tiên không?

Không. Mặc định có thể tiếp tục và tổng hợp lỗi. Dùng --exit-on-error để dừng sớm.

### psql mặc định có dừng script khi SQL lỗi không?

Không. Bật ON_ERROR_STOP để dừng khi gặp lỗi trong script.

### ON_ERROR_STOP có tự rollback toàn bộ script không?

Không phải tự nó. Muốn all-or-nothing, dùng transaction phù hợp như psql --single-transaction hoặc transaction block được thiết kế đúng.

### pg_restore --single-transaction có dùng được với -j không?

Không. Single transaction và parallel restore không tương thích.

### Có nên dùng --clean trên production?

Chỉ khi đã xác nhận target, phạm vi object, backup và kế hoạch rollback. --clean có thể drop objects hiện có.

### pg_dump có dump roles không?

Không. Dùng pg_dumpall --globals-only để xuất roles/tablespaces.

### Dump có chứa extension binary không?

Không. Target phải cài extension package tương ứng trước khi CREATE EXTENSION thành công.

### Restore thành công có nghĩa ứng dụng hoạt động đúng?

Không. Cần kiểm tra constraints, sequences, permissions, extensions và application smoke tests.

### Nếu psql trả lỗi giữa restore thì database có còn một phần dữ liệu không?

Có thể, nếu không chạy trong một transaction bao trùm. Kiểm tra target state và ưu tiên restore lại vào database mới khi cần trạng thái sạch.

### Có nên chạy lại dump trên database restore dở?

Không mù quáng. Dump có thể không idempotent và sẽ gặp duplicate objects/data. Xác định trạng thái hoặc tạo target mới.

### --no-owner và --no-privileges có luôn nên bật?

Không. Chỉ bật khi muốn mapping sang ownership/ACL mới. Nếu cần giữ quyền source, chuẩn bị roles và giữ các statements.

### Có thể restore vào version PostgreSQL cũ hơn source không?

Không được bảo đảm. Logical dump thường hướng tới cùng hoặc mới hơn; cần kiểm tra syntax, types, extensions và collation compatibility.

### Vì sao cần -X khi chạy psql script?

Để không đọc psqlrc ngoài ý muốn, giảm sự khác biệt do cấu hình cá nhân/máy chủ.

### Checksum có chứng minh dump restore được không?

Không. Nó chỉ xác nhận bytes khớp. Phải thực hiện restore test.

## 63. Tổng kết

Các lệnh cốt lõi:

~~~bash
# Plain SQL dump.
pg_dump -d appdb -f appdb.sql

# Custom archive.
pg_dump -d appdb -Fc -f appdb.dump

# Directory archive.
pg_dump -d appdb -Fd -j 4 -f appdb-dir

# Dump globals.
pg_dumpall --globals-only -f globals.sql

# Restore plain SQL, fail-fast.
psql -X -v ON_ERROR_STOP=1 -d appdb_restore -f appdb.sql

# Restore custom archive, fail-fast.
pg_restore --exit-on-error -d appdb_restore appdb.dump

# Restore archive all-or-nothing, serial.
pg_restore --single-transaction -d appdb_restore appdb.dump

# Inspect archive.
pg_restore --list appdb.dump

# Restore parallel.
pg_restore --exit-on-error -j 4 -d appdb_restore appdb.dump

# Analyze after restore.
vacuumdb --analyze-in-stages -d appdb_restore
~~~

Những nguyên tắc cần nhớ:

1. **Plain SQL dùng psql; custom/directory/tar dùng pg_restore.**
2. pg_dump xuất một database; pg_dumpall có thể xuất globals và nhiều databases.
3. Base backup/physical recovery khác logical SQL dump.
4. Chuẩn bị roles, extensions, encoding, locale, tablespaces và permissions trước restore.
5. Dùng --list để kiểm tra archive TOC trước khi chạy.
6. --no-owner và --no-privileges thay đổi ownership/ACL semantics; chỉ dùng khi cần.
7. --clean có thể drop objects; xác nhận target và backup trước.
8. Partial restore phải xét dependencies.
9. -j tăng throughput nhưng không tương thích --single-transaction.
10. pg_restore mặc định có thể tiếp tục qua lỗi; dùng --exit-on-error để fail-fast.
11. psql mặc định có thể tiếp tục sau SQL error; dùng ON_ERROR_STOP=1.
12. ON_ERROR_ROLLBACK dùng savepoints trong transaction, khác với dừng script.
13. Single transaction cung cấp all-or-nothing khi mọi command tương thích transaction; không dùng với CREATE DATABASE và commands ngoài transaction.
14. Luôn lưu logs và kiểm tra native exit code.
15. Shell pipeline cần pipefail; PowerShell cần kiểm tra LASTEXITCODE.
16. Không đưa passwords vào command line hoặc source control.
17. Kiểm tra sequence values, Large Objects, constraints, indexes, ACL/RLS và extensions sau restore.
18. Chạy ANALYZE phù hợp và application smoke tests.
19. Không chạy lại một restore dở trên cùng target mà chưa hiểu trạng thái.
20. Restore test là bằng chứng quan trọng nhất cho khả năng sử dụng dump.

Sơ đồ chọn công cụ và error policy:

~~~text
Có file dump?
     |
     v
Xác định format
     |
     +--> Plain SQL
     |       |
     |       v
     |     psql -X -v ON_ERROR_STOP=1
     |       |
     |       +--> --single-transaction nếu script phù hợp
     |
     +--> Custom / Directory / Tar
             |
             v
          pg_restore --list
             |
             v
          Chọn target/objects
             |
             +--> All-or-nothing, serial:
             |       --single-transaction
             |
             +--> Parallel:
                     -j N + --exit-on-error
             |
             v
       Kiểm tra exit code/log
             |
             v
       Xác minh schema/data/ACL
             |
             v
       ANALYZE + smoke test
             |
             v
       Chuyển ứng dụng khi đạt yêu cầu
~~~

**Kết luận:** Khôi phục SQL dump là một quy trình gồm chọn đúng công cụ, chuẩn bị môi trường, xác định transaction/error policy và xác minh kết quả. Dùng **psql với ON_ERROR_STOP** cho plain SQL và **pg_restore với --exit-on-error hoặc --single-transaction** cho archive phù hợp; lưu log, kiểm tra exit code và restore test để biết database thực sự đã phục hồi đầy đủ.
