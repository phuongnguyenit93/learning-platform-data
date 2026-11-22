# pg_dump với định dạng plain, custom, directory và tar

`pg_dump` là công cụ sao lưu logic của PostgreSQL. Công cụ kết nối tới một database, đọc schema và dữ liệu theo một snapshot nhất quán, rồi ghi chúng ra file hoặc directory theo định dạng được chọn. Khi cần khôi phục, định dạng đầu ra quyết định công cụ và cách thức restore.

Bốn định dạng chính:

- **plain**: script SQL văn bản, thường được nạp bằng `psql`.
- **custom**: archive riêng của PostgreSQL, một file, hỗ trợ chọn object, đổi thứ tự restore và parallel restore.
- **directory**: archive dạng thư mục gồm TOC và các file dữ liệu riêng; đây là định dạng hỗ trợ parallel dump.
- **tar**: archive dạng TAR, có thể được `pg_restore` đọc và chọn object, nhưng không hỗ trợ parallel restore.

Không có định dạng nào tốt nhất cho mọi trường hợp. Plain phù hợp khi cần script dễ đọc, dễ chỉnh sửa và tương thích với công cụ SQL. Custom thường là lựa chọn linh hoạt cho backup một file và restore có chọn lọc. Directory phù hợp với database lớn cần dump song song. Tar hữu ích khi workflow yêu cầu archive TAR hoặc cần tích hợp công cụ xử lý TAR.

~~~mermaid
flowchart TD
    A["pg_dump database"] --> P["plain SQL"]
    A --> C["custom archive"]
    A --> D["directory archive"]
    A --> T["tar archive"]
    P --> PS["Restore bằng psql"]
    C --> PR["Restore bằng pg_restore"]
    D --> PR
    T --> PR
    D --> PD["Hỗ trợ parallel dump"]
    C --> RR["Hỗ trợ parallel restore"]
    D --> RR
~~~

Bài học thuộc chương **Sao lưu**, module **Database Engine Relational PostgreSQL**. Chúng ta sẽ so sánh cấu trúc file, compression, parallelism, cách dump/restore, chọn object, xử lý owner/privileges, kiểm tra backup và lập quy trình vận hành an toàn.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích pg_dump là logical backup và phạm vi của một lần dump.
2. Phân biệt plain, custom, directory và tar.
3. Chọn định dạng dựa trên nhu cầu lưu trữ, restore và vận hành.
4. Tạo dump bằng các option `-F`, `-f` và `-Z`.
5. Restore plain script bằng psql.
6. Restore archive bằng pg_restore.
7. Sử dụng `pg_restore -l` và `-L` để xem/chọn thứ tự object.
8. Dump và restore song song đúng định dạng.
9. Phân biệt parallel dump với parallel restore.
10. Dùng schema-only, data-only và section để chia phạm vi.
11. Chọn table/schema và hiểu giới hạn của selective dump.
12. Quản lý owner, ACL, role, extension và tablespace khi restore.
13. Kiểm soát lỗi bằng ON_ERROR_STOP, exit-on-error và single transaction.
14. Hiểu snapshot consistency và ảnh hưởng của DDL/transaction lâu.
15. Kiểm tra file archive và xác minh bằng thử restore.
16. Phân biệt logical backup với physical backup/PITR.
17. Lập lịch, bảo vệ file backup và ghi nhận phiên bản client/server.

## 2. pg_dump là logical backup

`pg_dump` xuất định nghĩa đối tượng và dữ liệu của **một database** thành dạng logic. Nó không sao chép nguyên trạng các data files của cluster.

Ví dụ, một database có:

- Schemas và tables.
- Views/materialized views.
- Sequences.
- Indexes và constraints.
- Functions, procedures, types.
- Triggers và rules.
- Privileges/ownership theo option.
- Large objects theo phạm vi dump.
- Extension declarations.

pg_dump xuất các thành phần thuộc database theo phạm vi và option đã chọn. Các đối tượng toàn cluster như roles và tablespaces không phải nội dung đầy đủ của một database dump.

### pg_dump không phải backup toàn cluster

Một lệnh:

~~~bash
pg_dump -d appdb -Fc -f appdb.dump
~~~

chỉ dump database `appdb`. Nó không tự sao lưu:

- Các database khác trong cluster.
- Role definitions và role memberships toàn cluster.
- Tablespace definitions.
- PostgreSQL server configuration.
- WAL archive/replication slots.
- Physical files cần cho PITR.

Nếu cần role/global objects, có thể dùng:

~~~bash
pg_dumpall --globals-only > globals.sql
~~~

`pg_dumpall` có thể xuất nhiều database và global objects thành script SQL, nhưng đây là công cụ/phạm vi khác. Cần lưu role/global backup cùng database dump để restore đầy đủ quyền và ownership.

### Logical backup và physical backup bổ sung cho nhau

Logical dump hữu ích khi cần chuyển database, chọn object hoặc nâng cấp phiên bản. Physical base backup kết hợp WAL archive phù hợp cho phục hồi ở mức cluster và point-in-time recovery (PITR). Một hệ thống quan trọng thường thiết kế cả hai theo RPO/RTO.

## 3. Cách chọn định dạng

| Định dạng | Output | Restore | Parallel dump | Parallel restore | Chọn lọc object |
| --- | --- | --- | --- | --- | --- |
| Plain | Một SQL script | `psql` | Không | Không | Không qua pg_restore; có thể chỉnh script |
| Custom | Một archive file | `pg_restore` | Không | Có | Có |
| Directory | Một thư mục archive | `pg_restore` | Có | Có | Có |
| Tar | Một TAR archive | `pg_restore` | Không | Không | Có |

### Gợi ý lựa chọn

- Chọn **plain** nếu cần đọc, review, chỉnh sửa SQL hoặc đưa script vào quy trình triển khai.
- Chọn **custom** cho backup một file, nén tích hợp, restore có chọn lọc và parallel restore.
- Chọn **directory** khi database lớn và thời gian dump là yếu tố quan trọng; có thể dùng nhiều worker khi dump.
- Chọn **tar** khi workflow yêu cầu archive TAR hoặc muốn giữ các thành phần trong một archive tar.

Custom là lựa chọn mặc định hợp lý cho nhiều workflow backup/restore logic vì tính linh hoạt. Nhưng nếu yêu cầu chính là parallel dump, directory là lựa chọn cần thiết.

## 4. Các option cơ bản của pg_dump

Cú pháp tổng quát:

~~~bash
pg_dump [connection-options] [options] [dbname]
~~~

Các option thường gặp:

| Option | Ý nghĩa |
| --- | --- |
| `-F` / `--format` | Chọn định dạng output |
| `-f` / `--file` | File output hoặc directory output |
| `-d` / `--dbname` | Database connection string/name |
| `-h` / `--host` | Host PostgreSQL |
| `-p` / `--port` | Port |
| `-U` / `--username` | Database role dùng để kết nối |
| `-W` / `--password` | Yêu cầu prompt mật khẩu |
| `-j` / `--jobs` | Số worker song song ở định dạng hỗ trợ |
| `-Z` / `--compress` | Compression cho format hỗ trợ |
| `-v` / `--verbose` | In tiến trình chi tiết |
| `--no-owner` | Bỏ lệnh đặt ownership khi dump |
| `--no-acl` | Bỏ lệnh GRANT/REVOKE |
| `-C` / `--create` | Đưa lệnh tạo database vào dump |

Ví dụ kết nối:

~~~bash
pg_dump -h db.example.internal -p 5432 -U backup_user -d appdb -Fc -f appdb.dump
~~~

Không nên ghi password trực tiếp trong command line hoặc script được commit. Dùng cơ chế xác thực phù hợp như `.pgpass`, secret manager, service file hoặc prompt theo chính sách của môi trường.

### Kiểm tra phiên bản client

~~~bash
pg_dump --version
pg_restore --version
psql --version
~~~

Dùng client tool tương thích với server. Quy tắc chung của PostgreSQL là pg_dump không thể dump từ server có major version mới hơn major version của chính pg_dump. Client mới thường có thể dump server cũ trong phạm vi hỗ trợ. Output thường hướng tới restore trên cùng hoặc major version mới hơn; restore ngược về major version cũ không được bảo đảm.

Luôn kiểm tra release notes khi dump/restore qua các major versions.

## 5. Định dạng plain

Plain là định dạng mặc định nếu không chỉ định `-F`. Output là script SQL văn bản gồm các lệnh tạo object và nạp dữ liệu.

Dump:

~~~bash
pg_dump -F p -d appdb -f appdb.sql
~~~

Hoặc:

~~~bash
pg_dump -d appdb > appdb.sql
~~~

### Ưu điểm

- Có thể mở bằng text editor.
- Dễ review SQL và lưu trong hệ thống quản lý thay đổi khi phù hợp.
- Có thể chỉnh sửa script trước khi restore.
- Dễ tích hợp với `psql` và pipeline Unix.
- Không phụ thuộc archive TOC của pg_restore.

### Hạn chế

- Không hỗ trợ selective restore và reorder bằng pg_restore.
- Không có parallel restore.
- Script có thể rất lớn.
- Nếu cần chỉ restore một table, phải tạo dump scope phù hợp từ đầu hoặc xử lý script cẩn thận.
- Chỉnh sửa thủ công có thể làm mất tính nhất quán giữa các object.

### Restore plain bằng psql

Tạo database đích trước:

~~~bash
createdb -T template0 appdb_restore
~~~

Sau đó chạy:

~~~bash
psql -X -v ON_ERROR_STOP=1 -d appdb_restore -f appdb.sql
~~~

Ý nghĩa:

- `-X` không đọc file psqlrc của người dùng, giúp script có hành vi nhất quán hơn.
- `ON_ERROR_STOP=1` yêu cầu psql dừng khi gặp lỗi SQL.
- `-d` chỉ database đích.
- `-f` chỉ script dump.

Nếu không bật ON_ERROR_STOP, psql có thể tiếp tục chạy các lệnh sau một lỗi, khiến restore kết thúc nhưng database ở trạng thái không đầy đủ. Hãy kiểm tra exit code của psql trong automation.

### Dump plain có CREATE DATABASE

Có thể tạo script kèm lệnh tạo database:

~~~bash
pg_dump -F p -C -d appdb -f appdb_create.sql
~~~

Restore vào một database bảo trì có quyền tạo database:

~~~bash
psql -X -v ON_ERROR_STOP=1 -d postgres -f appdb_create.sql
~~~

Script có thể chứa lệnh tạo và kết nối database theo tên trong dump. Nếu muốn restore sang tên database khác, cách đơn giản hơn là dump không có `-C`, tạo database đích theo tên mới rồi nạp script vào đó.

### Plain script và transaction

Không mặc định chạy mọi plain dump trong một transaction duy nhất. Một số lệnh như CREATE DATABASE không thể chạy trong transaction block. Nếu dùng psql `-1`/`--single-transaction`, chỉ làm khi script tương thích và đã thử nghiệm; với script có CREATE DATABASE, hãy chọn workflow khác.

## 6. Định dạng custom

Custom format được chọn bằng `-F c` hoặc `--format=custom`:

~~~bash
pg_dump -F c -d appdb -f appdb.dump
~~~

Output là một archive file riêng của PostgreSQL. Archive có table of contents (TOC) và các thành phần schema/data được lưu trong cấu trúc archive. Data items thường được nén theo cấu hình mặc định của format này.

Restore bằng `pg_restore`, không nạp trực tiếp bằng psql:

~~~bash
pg_restore -d appdb_restore appdb.dump
~~~

### Ưu điểm

- Một file dễ chuyển và lưu trữ.
- Có TOC để xem danh sách object.
- Có thể chọn schema/table/object.
- Có thể thay đổi thứ tự restore qua TOC list.
- Hỗ trợ parallel restore.
- Compression tích hợp.

### Hạn chế

- Không đọc trực tiếp như SQL script.
- Cần pg_restore để giải archive.
- Custom format không hỗ trợ parallel dump; muốn dump song song hãy dùng directory.
- Không phải archive vật lý để phục hồi cả cluster/WAL.

### Xem TOC

~~~bash
pg_restore --list appdb.dump
~~~

Có thể lưu danh sách:

~~~bash
pg_restore --list appdb.dump > appdb.list
~~~

TOC giúp xem các object archive chứa và chuẩn bị chọn phần cần restore. File list có thể được chỉnh sửa để bỏ qua hoặc sắp xếp các entry theo quy tắc pg_restore.

## 7. Định dạng directory

Directory format được chọn bằng `-F d`:

~~~bash
pg_dump -F d -d appdb -f appdb_dir
~~~

Output là một thư mục archive, thường gồm TOC metadata và các file dữ liệu riêng cho các table/large objects. Không coi directory này là một thư mục chứa một file SQL duy nhất.

### Parallel dump

Directory là định dạng duy nhất của pg_dump hỗ trợ parallel dump:

~~~bash
pg_dump -F d -j 4 -d appdb -f appdb_dir
~~~

`-j 4` cho phép tối đa bốn worker dump đồng thời theo cơ chế của pg_dump. Các worker dùng synchronized snapshot để bảo đảm dữ liệu dump nhất quán dù nhiều kết nối cùng đọc database.

### Yêu cầu vận hành

- Đường dẫn output phải dành riêng cho archive; bảo đảm không ghi đè dữ liệu khác.
- Disk phải đủ cho toàn bộ directory và overhead.
- Mỗi worker dùng một kết nối database; tính connection budget.
- Số worker quá cao có thể làm tăng I/O, CPU và tải trên primary.
- Parallel dump cần server hỗ trợ synchronized snapshots; các PostgreSQL hiện đại đáp ứng điều này, nhưng kiểm tra version khi làm việc với hệ thống cũ.
- Directory phải được chuyển/lưu nguyên vẹn; thiếu file thành phần có thể khiến archive không restore được.

### Ưu điểm

- Dump song song, có thể rút ngắn thời gian với database lớn.
- Mỗi table/data object có file riêng.
- Hỗ trợ parallel restore.
- Hỗ trợ selective restore và reorder.
- Có compression cho các data files theo option hỗ trợ.

### Hạn chế

- Quản lý nhiều file/thư mục thay vì một file.
- Copy, upload, checksum và retention phải áp dụng cho toàn bộ directory.
- Không nên xóa hoặc đổi tên một file bên trong archive.
- Parallelism cao có thể làm primary bị quá tải.

## 8. Định dạng tar

Tar format được chọn bằng `-F t`:

~~~bash
pg_dump -F t -d appdb -f appdb.tar
~~~

Đây là archive theo định dạng TAR, có thể được pg_restore đọc:

~~~bash
pg_restore -d appdb_restore appdb.tar
~~~

### Đặc điểm

- Một file archive.
- Có TOC để chọn object và thay đổi thứ tự restore.
- Không hỗ trợ parallel dump.
- pg_restore parallel restore chỉ hỗ trợ custom và directory, vì vậy không chọn tar nếu yêu cầu restore song song.
- Tar format không có compression tích hợp như custom/directory. Nếu nén archive tar bằng công cụ ngoài, cần giải nén trước khi đưa cho pg_restore, trừ khi workflow có bước giải nén riêng.

### Khi nào chọn tar?

- Công cụ lưu trữ hoặc pipeline nội bộ yêu cầu TAR.
- Cần đóng gói thành phần theo archive format quen thuộc.
- Không cần parallel dump/restore.
- Có thể chấp nhận xử lý compression ở lớp ngoài nếu cần.

Không nhầm file tar từ pg_dump với physical backup của data directory PostgreSQL.

## 9. Compression trong các định dạng

Compression có thể giảm dung lượng lưu trữ và network transfer, nhưng đổi lại CPU time.

| Format | Compression |
| --- | --- |
| Plain | Không nén tích hợp; có thể nén file ngoài |
| Custom | Có compression tích hợp |
| Directory | Có compression cho data files |
| Tar | Không có compression tích hợp; có thể nén archive bên ngoài |

Option `-Z`/`--compress` điều khiển compression cho những format hỗ trợ. Cú pháp và các compression methods phụ thuộc PostgreSQL major version và cách build client. Hãy xem `pg_dump --help` và docs của đúng phiên bản thay vì giả định một method luôn có sẵn.

Ví dụ minh họa:

~~~bash
pg_dump -F c -Z 6 -d appdb -f appdb.dump
~~~

Mức `6` là ví dụ cú pháp theo dạng compression level được hỗ trợ ở các phiên bản tương ứng; các bản mới có thể cung cấp cách chỉ định method/detail khác.

### Chọn compression theo bottleneck

- CPU còn dư, network/disk chậm: compression có thể hữu ích.
- CPU đã bận: compression mạnh có thể làm dump chậm hơn.
- Backup local trên storage nhanh: có thể ưu tiên tốc độ.
- Backup truyền qua mạng: compression có thể giảm băng thông.
- Cần restore nhanh: đo cả dump time và restore time, không chỉ file size.

Compression ratio phụ thuộc dữ liệu. JSON/text lặp lại thường nén tốt hơn dữ liệu đã nén hoặc dữ liệu entropy cao.

## 10. Parallel dump và parallel restore

Hai tính năng này độc lập:

| Hoạt động | Format hỗ trợ | Option |
| --- | --- | --- |
| Parallel dump | Directory | `pg_dump -Fd -j N` |
| Parallel restore | Custom, directory | `pg_restore -j N` |
| Parallel dump custom | Không | Không hỗ trợ |
| Parallel restore tar | Không | Không hỗ trợ |
| Parallel restore plain | Không | Dùng psql script tuần tự |

### Parallel restore custom

~~~bash
pg_restore -j 4 -d appdb_restore appdb.dump
~~~

### Parallel restore directory

~~~bash
pg_restore -j 4 -d appdb_restore appdb_dir
~~~

pg_restore điều phối các restore jobs có thể chạy song song theo dependency và archive TOC. Không phải mọi object đều có thể chạy đồng thời; một số bước cần thứ tự hoặc serialization.

### Chọn số worker

Bắt đầu từ số nhỏ rồi benchmark. Cân nhắc:

- CPU của source/target.
- Disk throughput và IOPS.
- Network bandwidth.
- Số kết nối cho phép.
- Index build và constraint validation.
- WAL generation/replay.
- Lock contention.
- Workload ứng dụng đang chạy.

Tăng `-j` không bảo đảm thời gian giảm tuyến tính. Khi target storage đã bão hòa, thêm worker có thể làm restore chậm hơn.

## 11. Restore custom bằng pg_restore

Tạo database đích:

~~~bash
createdb -T template0 appdb_restore
~~~

Restore:

~~~bash
pg_restore -d appdb_restore --exit-on-error appdb.dump
~~~

Có thể dùng parallel:

~~~bash
pg_restore -j 4 -d appdb_restore --exit-on-error appdb.dump
~~~

Nếu database đích chưa có và muốn tạo database theo metadata trong archive:

~~~bash
pg_restore -C -d postgres --exit-on-error appdb.dump
~~~

Trong ví dụ cuối, kết nối ban đầu tới database `postgres` để pg_restore tạo database đích có tên được ghi trong archive. Option `-C` không có nghĩa đổi tên database theo tên bất kỳ trong `-d`; hãy hiểu `-d` là database kết nối ban đầu khi dùng create.

## 12. Restore directory và tar

Directory:

~~~bash
pg_restore -d appdb_restore --exit-on-error appdb_dir
~~~

Tar:

~~~bash
pg_restore -d appdb_restore --exit-on-error appdb.tar
~~~

Có thể thêm lựa chọn object hoặc clean tương tự custom archive. Nhưng chỉ custom/directory hỗ trợ parallel restore.

### pg_restore nhận biết archive format

pg_restore có thể đọc custom, directory và tar archives. Plain SQL không phải input của pg_restore; dùng psql.

Nếu đưa nhầm file plain vào pg_restore, công cụ sẽ báo format không hợp lệ. Không đổi đuôi file để biến SQL script thành archive.

## 13. Xem và chỉnh TOC list

Với custom/directory/tar:

~~~bash
pg_restore -l appdb.dump > appdb.list
~~~

Có thể chỉnh file list để bỏ một số entry hoặc điều chỉnh thứ tự restore, sau đó:

~~~bash
pg_restore -L appdb.list -d appdb_restore appdb.dump
~~~

`-L`/`--use-list` yêu cầu pg_restore chỉ restore các entry được liệt kê theo thứ tự trong file list. Dòng bị comment/bỏ khỏi danh sách sẽ không được restore theo list đó.

### Khi nào dùng TOC list?

- Bỏ một table dữ liệu lớn không cần trong môi trường test.
- Restore schema trước, data sau theo quy trình tùy chỉnh.
- Bỏ một object không tương thích ở target.
- Khôi phục chọn lọc object sau sự cố.

### Rủi ro

Object có dependency. Nếu bỏ table nhưng giữ view/function/constraint phụ thuộc vào table đó, restore có thể lỗi. Chọn lọc không tự giải quyết toàn bộ dependency graph; phải hiểu schema và kiểm tra restore trong môi trường thử.

## 14. Dump và restore theo schema/table

Có thể giới hạn phạm vi dump:

~~~bash
pg_dump -F c -n sales -d appdb -f sales.dump
~~~

Dump một table:

~~~bash
pg_dump -F c -t sales.orders -d appdb -f orders.dump
~~~

Dump schema only:

~~~bash
pg_dump -F c --schema-only -d appdb -f schema.dump
~~~

Dump data only:

~~~bash
pg_dump -F c --data-only -d appdb -f data.dump
~~~

Với archive, restore có thể chọn schema/table:

~~~bash
pg_restore -n sales -d appdb_restore sales.dump
~~~

~~~bash
pg_restore -t orders -n sales -d appdb_restore orders.dump
~~~

### Selective dump không tự bao gồm mọi dependency

Dump một table không nhất thiết mang theo mọi type, function, schema, extension hay object phụ thuộc mà table cần. Khi restore vào database trống, có thể cần dump schema rộng hơn hoặc tạo dependency trước.

Nếu dùng `--schema`/`--table`, kiểm tra object được chọn và test restore. Pattern matching của pg_dump/pg_restore có quy tắc riêng; dùng schema qualification và quote khi tên có ký tự đặc biệt.

## 15. Section: pre-data, data và post-data

Archive có thể chia thành các section:

- **pre-data**: phần lớn định nghĩa schema cần có trước khi nạp dữ liệu, như tables/types.
- **data**: table data, large objects và các thành phần dữ liệu.
- **post-data**: nhiều index, trigger, constraint và các object cần tạo sau data.

Ví dụ restore từng section:

~~~bash
pg_restore --section=pre-data -d appdb_restore appdb.dump
pg_restore --section=data -d appdb_restore appdb.dump
pg_restore --section=post-data -d appdb_restore appdb.dump
~~~

Các section hữu ích khi thiết kế workflow nhiều bước, ví dụ tạo table trước, nạp dữ liệu, sau đó build indexes/constraints. Hãy giữ dependency và transaction context phù hợp.

Không chạy ba lệnh trên song song tùy tiện; post-data cần dữ liệu/schema từ các phase trước.

## 16. Owner, ACL và role

Dump có thể chứa lệnh đặt owner và privileges. Khi restore sang môi trường khác, role nguồn có thể không tồn tại.

Có thể bỏ ownership và ACL:

~~~bash
pg_dump -Fc --no-owner --no-acl -d appdb -f appdb.dump
~~~

Hoặc áp dụng ở restore:

~~~bash
pg_restore --no-owner --no-acl -d appdb_restore appdb.dump
~~~

Khác biệt:

- `--no-owner`: không phát các lệnh đặt owner như trong dump.
- `--no-acl`: bỏ GRANT/REVOKE được lưu trong archive.
- `--role=target_role`: yêu cầu pg_restore thực hiện SET ROLE sau khi kết nối (nếu phù hợp quyền).

Các option này không tạo role. Nếu cần giữ ownership và grants nguyên vẹn, hãy dump/restore global roles trước, hoặc tạo roles tương ứng trên target.

### Không nên bỏ ACL theo thói quen

Trong production, quyền truy cập là một phần của database security. Nếu bỏ ACL để restore dễ hơn, cần có bước tái tạo quyền rõ ràng trước khi mở ứng dụng.

## 17. Extension và tablespace

pg_dump lưu các lệnh cần thiết để tạo extension trong database theo metadata, nhưng không đóng gói binary extension của server. Target phải cài package/extension tương thích trước khi restore.

Ví dụ:

~~~sql
CREATE EXTENSION IF NOT EXISTS pgcrypto;
~~~

Đây chỉ là ví dụ về extension declaration; package tương ứng phải tồn tại trên server target.

Tablespace definitions là global objects. Nếu dump có object được gắn vào tablespace cụ thể, target phải có tablespace phù hợp hoặc sử dụng option xử lý tablespace như `--no-tablespaces` khi dump/restore theo mục tiêu.

### Checklist dependency

- Roles và memberships.
- Tablespaces.
- Extension packages/versions.
- Locale/collation.
- Encoding.
- Database-level settings.
- Foreign data wrappers/servers và credentials theo môi trường.
- External functions/libraries.
- Application-specific secrets/configuration.

Một database dump không thể thay thế inventory dependency của cả hệ thống.

## 18. Large objects

PostgreSQL hỗ trợ large objects (LO) ngoài cơ chế TOAST của các cột thông thường. pg_dump có option `--blobs`/`-b` và `--no-large-objects` để điều khiển large object dump theo phiên bản và phạm vi được chọn.

Nếu ứng dụng dùng LO API, cần xác nhận dump có chứa các large objects mà ứng dụng tham chiếu. Đừng nhầm LO với dữ liệu bytea/TOAST trong một column; chúng là hai cơ chế khác nhau.

Khi dump chọn lọc theo table/schema, kiểm tra docs vì phạm vi large objects có thể khác so với dump toàn database.

## 19. Xử lý lỗi khi restore

### Plain script

Dùng:

~~~bash
psql -X -v ON_ERROR_STOP=1 -d appdb_restore -f appdb.sql
~~~

Kiểm tra exit code của psql. Khi chạy trong shell script, bật chế độ xử lý lỗi phù hợp và lưu stdout/stderr vào log có bảo vệ.

### Archive

Dùng:

~~~bash
pg_restore --exit-on-error -d appdb_restore appdb.dump
~~~

Mặc định pg_restore có thể tiếp tục một số bước sau lỗi và báo lỗi tổng kết. `--exit-on-error` yêu cầu dừng khi có lỗi đầu tiên.

### Single transaction

Với archive có thể yêu cầu:

~~~bash
pg_restore --single-transaction --exit-on-error -d appdb_restore appdb.dump
~~~

Điều này gom restore thành một transaction, giúp all-or-nothing khi mọi command tương thích. Tuy nhiên:

- Không kết hợp được với parallel jobs.
- Transaction rất lớn có thể giữ locks/resources lâu.
- Một số command không chạy được trong transaction block.
- Restore thất bại sẽ rollback toàn bộ, có thể tốn thời gian và WAL.

Không bật single transaction một cách máy móc cho mọi database lớn.

## 20. Clean trước khi restore

Option:

~~~bash
pg_restore --clean --if-exists -d appdb_restore appdb.dump
~~~

- `--clean`: phát lệnh DROP cho object trước khi tạo lại.
- `--if-exists`: thêm IF EXISTS vào các lệnh drop khi có thể.

Cẩn thận: `--clean` có thể xóa object đang tồn tại trong database đích. Chỉ dùng trên database đã xác định đúng và có backup/approval phù hợp.

Nếu restore vào database mới tạo từ template0, thường không cần clean.

## 21. Dump snapshot nhất quán và concurrent writes

pg_dump dùng snapshot để dữ liệu được đọc nhất quán trong suốt dump. Các INSERT/UPDATE/DELETE khác vẫn có thể tiếp tục trong phần lớn quá trình; dump không phải thao tác khóa toàn bộ database để ngừng ghi.

Tuy vậy:

- pg_dump lấy lock đọc phù hợp trên các relation.
- DDL cần lock mạnh có thể phải chờ hoặc xung đột với dump.
- Transaction lâu có thể giữ snapshot và ảnh hưởng vacuum.
- Dump kéo dài có thể tăng áp lực storage/cache.
- Parallel dump dùng synchronized snapshots để các worker nhìn cùng một trạng thái dữ liệu.

Không xem dump là hoàn toàn không ảnh hưởng production. Hãy chọn giờ phù hợp, quan sát tải và tránh DDL lớn trùng thời điểm.

### Dump từ replica

Một số môi trường dùng standby để giảm tải primary. Cần xác nhận quyền, trạng thái standby, recovery conflicts và version support. Dump từ standby có thể bị cancel do recovery conflict hoặc bị ảnh hưởng bởi replay workload. Kiểm tra logs và chính sách hot standby trước khi triển khai.

## 22. Dump bằng connection string

Có thể truyền connection string:

~~~bash
pg_dump -Fc "host=db.internal port=5432 dbname=appdb user=backup_user sslmode=verify-full" -f appdb.dump
~~~

Trong automation, tránh đặt mật khẩu trực tiếp trong command line, nơi có thể xuất hiện trong process list/logs. Dùng `.pgpass`, service file hoặc secret manager được bảo vệ.

Các biến môi trường thường dùng:

- `PGHOST`
- `PGPORT`
- `PGDATABASE`
- `PGUSER`
- `PGSERVICE`
- `PGPASSFILE`

Không đặt `PGPASSWORD` lâu dài trong môi trường dùng chung nếu có cơ chế an toàn hơn.

## 23. Ví dụ: dump custom và restore sang database khác

Dump:

~~~bash
pg_dump -Fc -v -d appdb -f appdb_2026.dump
~~~

Tạo database đích:

~~~bash
createdb -T template0 appdb_test_restore
~~~

Restore:

~~~bash
pg_restore -v --exit-on-error -d appdb_test_restore appdb_2026.dump
~~~

Xác minh:

~~~bash
psql -d appdb_test_restore -c "SELECT count(*) FROM public.orders;"
~~~

Count chỉ là kiểm tra mẫu. Với dữ liệu quan trọng, đối chiếu row counts, constraints, sequences, large objects và các invariant nghiệp vụ.

## 24. Ví dụ: directory dump song song

~~~bash
pg_dump -Fd -j 4 -v -d appdb -f appdb_directory
~~~

Kiểm tra TOC:

~~~bash
pg_restore -l appdb_directory > appdb_directory.list
~~~

Restore song song:

~~~bash
createdb -T template0 appdb_restore
pg_restore -j 4 --exit-on-error -d appdb_restore appdb_directory
~~~

Giữ nguyên toàn bộ thư mục trong quá trình copy/retention. Nếu dùng object storage, hãy upload toàn bộ files và kiểm tra manifest/checksum do pipeline tạo.

## 25. Ví dụ: tar dump và restore

~~~bash
pg_dump -Ft -v -d appdb -f appdb.tar
~~~

Xem danh sách:

~~~bash
pg_restore -l appdb.tar
~~~

Restore:

~~~bash
pg_restore --exit-on-error -d appdb_restore appdb.tar
~~~

Không thêm `-j` nếu mong muốn parallel restore tar; định dạng tar không hỗ trợ chế độ đó.

## 26. Ví dụ: plain dump nén bên ngoài

Có thể nén SQL script bằng công cụ ngoài:

~~~bash
pg_dump -Fp -d appdb | gzip > appdb.sql.gz
~~~

Restore:

~~~bash
gzip -dc appdb.sql.gz | psql -X -v ON_ERROR_STOP=1 -d appdb_restore
~~~

Pipeline cần kiểm tra exit status của cả hai process. Trong Bash có thể dùng `set -o pipefail`; trong PowerShell cần xử lý exit code từng tiến trình theo cơ chế riêng.

Compression ngoài có thể giảm dung lượng plain dump, nhưng script vẫn phải được giải nén/stream qua psql; không thể đưa file gzip trực tiếp vào pg_restore.

## 27. Kiểm tra archive trước restore

Với custom/directory/tar:

~~~bash
pg_restore --list appdb.dump
~~~

Nếu lệnh đọc được TOC, đây là tín hiệu archive có header/metadata đọc được. Nhưng nó **không chứng minh toàn bộ data payload đều đầy đủ hoặc restore thành công**.

Có thể kiểm tra checksum file sau khi copy:

~~~bash
sha256sum appdb.dump
~~~

Trên Windows dùng công cụ checksum tương đương như Get-FileHash. Với directory archive, cần checksum từng file hoặc manifest bao trùm tất cả file thành phần.

### File size khác 0 không phải bằng chứng backup tốt

Một file dump có thể bị truncate, thiếu data segment hoặc không thể restore. Exit code của pg_dump, logs, checksum và test restore là các lớp kiểm chứng bổ sung.

## 28. Test restore là bước xác minh quan trọng

Một backup chỉ có giá trị khi có thể restore trong thời gian yêu cầu.

Quy trình định kỳ:

1. Chọn một bản backup đại diện.
2. Tạo database/cluster thử nghiệm tương thích.
3. Chuẩn bị roles, tablespaces và extensions cần thiết.
4. Restore bằng workflow thực tế.
5. Ghi thời gian restore.
6. Kiểm tra object count, row count và constraints.
7. Chạy smoke tests/query nghiệp vụ.
8. Xác nhận owner, ACL, sequence và large objects.
9. Đo RTO và so với mục tiêu.
10. Ghi lại lỗi và cải thiện runbook.

Đừng chỉ chạy `pg_restore -l` rồi coi backup đã được kiểm chứng.

## 29. Bảo mật và lưu trữ file dump

Logical dump thường chứa dữ liệu ứng dụng ở dạng có thể khôi phục hoặc đọc được. Bảo vệ nó như dữ liệu production.

- Mã hóa khi truyền và khi lưu.
- Giới hạn quyền đọc file/directory.
- Không upload vào public bucket.
- Không đưa dump vào Git repository.
- Không đính kèm dump vào ticket/chat không được phép.
- Dùng encryption/key management theo policy.
- Đặt retention và lifecycle rõ ràng.
- Xóa bản tạm an toàn theo policy sau khi restore.
- Theo dõi ai tạo, ai tải và ai restore backup.
- Không ghi credentials trong shell history hoặc logs.

Custom archive có thể nén nhưng compression không phải encryption.

## 30. Tác động của pg_dump tới production

Dump lớn có thể tiêu thụ:

- CPU cho serialize và compression.
- I/O đọc heap/index/TOAST.
- Network nếu client ở host khác.
- Connections cho các workers.
- Cache bandwidth.
- Snapshot retention trong thời gian dump.

Để giảm impact:

- Chạy ngoài giờ peak nếu có thể.
- Dump từ replica khi kiến trúc cho phép.
- Điều chỉnh `-j` theo tải thực tế.
- Không compression quá mạnh khi CPU là bottleneck.
- Dùng `--verbose` để quan sát tiến trình.
- Theo dõi database latency, disk throughput và replica lag.
- Tránh chạy nhiều dump lớn đồng thời trên cùng storage.

## 31. Dump và restore sequence values

pg_dump lưu dữ liệu sequence trong dump để sequence có thể tiếp tục từ trạng thái được backup theo cách restore tương ứng. Khi dump chỉ chọn một table hoặc chỉ data/schema, cần kiểm tra sequence dependency và ownership.

Sau restore, xác minh:

- Sequence tồn tại.
- `OWNED BY` đúng column nếu schema dùng identity/serial.
- Giá trị sequence phù hợp dữ liệu đã restore.
- Insert mới không đụng primary key hiện có.

Không tự đặt sequence về MAX(id) trong mọi trường hợp mà chưa hiểu increment, cycle, cache và workload concurrent.

## 32. Dump có bao gồm user/role không?

pg_dump không dump định nghĩa roles toàn cluster. Nó có thể dump object ownership và ACL trong database.

Do đó có hai tình huống:

- **Restore giữ owner/ACL**: tạo roles và memberships cần thiết trên target trước.
- **Restore không giữ owner/ACL**: dùng `--no-owner` `--no-acl`, sau đó áp dụng security policy của môi trường target.

Global backup:

~~~bash
pg_dumpall --globals-only > globals.sql
~~~

Script global có thể chứa role attributes, memberships và tablespace definitions; bảo vệ file vì nó chứa thông tin nhạy cảm về cấu hình/quyền.

## 33. Lựa chọn --no-tablespaces

Nếu không muốn restore object vào tablespace nguồn, có thể bỏ tablespace assignment theo option phù hợp:

~~~bash
pg_dump -Fc --no-tablespaces -d appdb -f appdb.dump
~~~

Việc này hữu ích khi chuyển từ môi trường có storage layout riêng sang target dùng tablespace mặc định. Nhưng hãy xem xét dung lượng đích và policy storage; bỏ tablespace metadata không làm dữ liệu tự nhỏ hơn.

## 34. Dump schema-only để kiểm tra/migration

~~~bash
pg_dump --schema-only -d appdb -f appdb_schema.sql
~~~

Dùng để:

- Review DDL.
- So sánh schema giữa môi trường.
- Tạo môi trường test.
- Kiểm tra index/constraint/function definitions.
- Chuẩn bị migration plan.

Schema-only không chứa table data. Nó cũng không thay thế schema diff tool hoàn chỉnh nếu cần phát hiện thay đổi theo semantics và dependencies.

## 35. Data-only dump

~~~bash
pg_dump --data-only -Fc -d appdb -f appdb_data.dump
~~~

Data-only có thể hữu ích khi schema đã được triển khai riêng. Nhưng restore data cần đúng table definitions, types, sequences, constraints và dependencies.

Khi nạp dữ liệu lớn, có thể cần điều phối triggers/constraints/indexes theo quy trình phù hợp. Không tắt trigger/constraint tùy tiện; điều đó có thể để lại dữ liệu sai.

## 36. Dump một số table cho môi trường test

~~~bash
pg_dump -Fc \
  -t public.customers \
  -t public.products \
  -d appdb \
  -f sample_data.dump
~~~

Đây là ví dụ chọn table, nhưng có thể không bao gồm các object phụ thuộc. Nếu muốn restore vào database mới, hãy bảo đảm schema, types, sequences và functions cần thiết đã có.

Có thể dùng `--exclude-table-data` để dump schema của bảng nhưng loại data theo pattern phù hợp. Kiểm tra kết quả TOC trước khi restore.

## 37. Restore vào database có sẵn

Nếu database đích đã có object trùng tên, restore có thể lỗi do object exists hoặc constraint conflict.

Lựa chọn:

- Tạo database trống từ template0.
- Dùng `--clean` `--if-exists` nếu chủ đích thay thế object và đã xác nhận scope.
- Restore schema/data theo phase.
- Dùng TOC list để chọn object.
- Restore vào database tạm, xác minh rồi chuyển ứng dụng.

Không dùng `--clean` trên database production đang phục vụ chỉ để bỏ lỗi duplicate object.

## 38. Tối ưu restore lớn

Một số chiến lược:

- Dùng custom/directory để parallel restore.
- Chọn số jobs vừa với CPU/IO.
- Tạo schema/data/post-data theo phase khi cần.
- Chuẩn bị extension và roles trước.
- Kiểm tra tablespace/disk.
- Đảm bảo target có đủ WAL/disk headroom.
- Tránh query workload cạnh tranh trong lúc restore.
- Theo dõi `pg_stat_activity`, progress và server logs.
- Chạy ANALYZE sau bulk restore nếu cần planner statistics mới.

Không disable constraints/triggers bằng tay nếu không có quy trình tái tạo và xác minh. pg_restore có thể sắp xếp object theo TOC/dependency; giữ nguyên cơ chế mặc định trừ khi có lý do rõ ràng.

## 39. Các lỗi thường gặp

1. **Dùng plain dump rồi gọi pg_restore**, trong khi plain SQL phải được chạy bằng psql.
2. **Dùng custom archive với psql**, dù archive không phải script SQL.
3. **Chọn custom nhưng kỳ vọng parallel dump**, trong khi parallel dump chỉ hỗ trợ directory.
4. **Chọn tar nhưng kỳ vọng parallel restore**, trong khi parallel restore chỉ hỗ trợ custom/directory.
5. **Nhầm `-j` dump với `-j` restore**, hai option chạy ở hai công cụ và có format restrictions riêng.
6. **Tăng jobs quá cao**, làm CPU/I/O/connection pressure tăng.
7. **Nghĩ pg_dump backup cả cluster**, trong khi nó dump một database.
8. **Quên roles/tablespaces**, khiến restore owner/ACL hoặc storage thất bại.
9. **Bỏ ACL mà không có bước tái tạo quyền**, làm target sai security posture.
10. **Không cài extension trên target**, khiến CREATE EXTENSION thất bại.
11. **Restore vào database đang có dữ liệu mà không kiểm tra object conflicts**.
12. **Dùng `--clean` không hiểu phạm vi DROP**, có thể xóa object đang dùng.
13. **Không bật ON_ERROR_STOP/exit-on-error**, khiến script tiếp tục sau lỗi.
14. **Dùng single transaction cùng parallel jobs**, không được hỗ trợ.
15. **Đặt `-C` nhưng kết nối vào database không phù hợp quyền**, hoặc hiểu nhầm database name được tạo.
16. **Dump một table rồi giả định mọi dependency đều có**, dẫn tới restore thiếu type/function/schema.
17. **Không kiểm tra version client/server**, gây incompatibility.
18. **Không xác minh large objects**, đặc biệt khi ứng dụng dùng LO API.
19. **Đổi tên hoặc xóa file bên trong directory archive**, làm archive không đầy đủ.
20. **Nén tar rồi đưa trực tiếp file nén vào pg_restore**, dù cần giải nén trước.
21. **Coi `pg_restore -l` là test restore đầy đủ**, dù lệnh này chủ yếu đọc TOC.
22. **Chỉ kiểm tra file size**, không kiểm tra exit code/checksum/restore.
23. **Không tính disk/WAL/replication lag**, gây đầy storage hoặc lag.
24. **Không test RTO**, đến lúc sự cố mới phát hiện restore quá lâu.
25. **Lưu dump không mã hóa hoặc quyền quá rộng**, làm lộ dữ liệu.
26. **Dùng logical dump như thay thế PITR**, không có base backup/WAL archive.
27. **Không chạy ANALYZE sau import lớn**, khiến planner dùng statistics cũ.
28. **Tự chỉnh plain SQL script mà không review dependency**, tạo restore không đầy đủ.

## 40. Bài tập thực hành có đáp án

### Bài 1. pg_dump là loại backup nào?

**Đáp án:** Logical backup của một database, xuất object definitions và dữ liệu theo snapshot.

### Bài 2. pg_dump có backup toàn bộ roles không?

**Đáp án:** Không. Dùng pg_dumpall --globals-only hoặc workflow global-object riêng.

### Bài 3. Plain format restore bằng công cụ nào?

**Đáp án:** psql.

### Bài 4. Custom format restore bằng công cụ nào?

**Đáp án:** pg_restore.

### Bài 5. Chọn custom format

~~~bash
pg_dump -Fc -d appdb -f appdb.dump
~~~

**Đáp án:** Tạo một custom archive file.

### Bài 6. Chọn directory format

~~~bash
pg_dump -Fd -d appdb -f appdb_dir
~~~

**Đáp án:** Tạo directory archive.

### Bài 7. Định dạng nào hỗ trợ parallel dump?

**Đáp án:** Directory format.

### Bài 8. Định dạng nào hỗ trợ parallel restore?

**Đáp án:** Custom và directory.

### Bài 9. Tar có parallel restore không?

**Đáp án:** Không.

### Bài 10. Restore plain script

~~~bash
psql -X -v ON_ERROR_STOP=1 -d appdb_restore -f appdb.sql
~~~

**Đáp án:** Chạy SQL script và dừng khi có lỗi.

### Bài 11. Restore custom archive

~~~bash
pg_restore -d appdb_restore appdb.dump
~~~

**Đáp án:** Restore archive vào database đích.

### Bài 12. Xem archive TOC

~~~bash
pg_restore -l appdb.dump
~~~

**Đáp án:** Liệt kê các archive entries.

### Bài 13. Dùng TOC list để chọn object

~~~bash
pg_restore -l appdb.dump > list.txt
pg_restore -L list.txt -d appdb_restore appdb.dump
~~~

**Đáp án:** Restore các entries trong list theo thứ tự của list.

### Bài 14. Dump song song bốn worker

~~~bash
pg_dump -Fd -j 4 -d appdb -f appdb_dir
~~~

**Đáp án:** Directory format với tối đa bốn worker.

### Bài 15. Restore song song bốn worker

~~~bash
pg_restore -j 4 -d appdb_restore appdb.dump
~~~

**Đáp án:** Parallel restore nếu archive là custom hoặc directory.

### Bài 16. Dump chỉ schema

~~~bash
pg_dump --schema-only -d appdb -f schema.sql
~~~

**Đáp án:** Xuất definitions, không xuất table data.

### Bài 17. Dump chỉ data

~~~bash
pg_dump --data-only -Fc -d appdb -f data.dump
~~~

**Đáp án:** Xuất dữ liệu, cần schema phù hợp ở target.

### Bài 18. Dump một schema

~~~bash
pg_dump -Fc -n sales -d appdb -f sales.dump
~~~

**Đáp án:** Chọn object trong schema sales theo pattern matching của pg_dump.

### Bài 19. Dump một table

~~~bash
pg_dump -Fc -t sales.orders -d appdb -f orders.dump
~~~

**Đáp án:** Chọn table orders; dependency khác có thể cần dump riêng.

### Bài 20. Bỏ owner và ACL

**Đáp án:** Dùng `--no-owner` `--no-acl` khi dump hoặc restore, rồi áp dụng security policy của target.

### Bài 21. Tạo database từ archive

~~~bash
pg_restore -C -d postgres appdb.dump
~~~

**Đáp án:** Kết nối tới database postgres và tạo database theo metadata trong archive.

### Bài 22. Vì sao directory dump cần giữ toàn thư mục?

**Đáp án:** Archive gồm TOC và nhiều file dữ liệu; thiếu file thành phần có thể làm restore thất bại.

### Bài 23. Vì sao custom không parallel dump?

**Đáp án:** pg_dump chỉ triển khai parallel dump cho directory format.

### Bài 24. Vì sao tar không phải physical backup?

**Đáp án:** Tar chứa archive logic do pg_dump tạo, không phải data files/WAL của cluster.

### Bài 25. `--single-transaction` có kết hợp `-j` được không?

**Đáp án:** Không. Parallel restore không tương thích với single transaction mode.

### Bài 26. `pg_restore -l` chứng minh gì?

**Đáp án:** Archive TOC có thể đọc được; không chứng minh toàn bộ payload restore thành công.

### Bài 27. Làm sao xác minh backup tốt?

**Đáp án:** Kiểm tra exit code/log/checksum và thực hiện test restore định kỳ, sau đó chạy smoke tests.

### Bài 28. Vì sao cần chuẩn bị extension trước restore?

**Đáp án:** pg_dump lưu declaration, không đóng gói binary extension server.

### Bài 29. Dump có nhất quán khi ứng dụng vẫn ghi không?

**Đáp án:** pg_dump dùng snapshot nhất quán; DML có thể tiếp tục trong phần lớn quá trình, nhưng DDL/lock và snapshot retention vẫn cần xem xét.

### Bài 30. Logical dump có thay PITR không?

**Đáp án:** Không. PITR cần physical base backup và WAL archive phù hợp.

## 41. Checklist chọn format và vận hành

- [ ] Xác định chỉ dump một database hay cần global objects/cluster backup.
- [ ] Chọn plain, custom, directory hoặc tar theo restore workflow.
- [ ] Dùng plain khi cần SQL script và psql restore.
- [ ] Dùng custom khi cần một archive linh hoạt.
- [ ] Dùng directory nếu cần parallel dump.
- [ ] Dùng custom/directory nếu cần parallel restore.
- [ ] Không kỳ vọng tar hỗ trợ parallel restore.
- [ ] Kiểm tra pg_dump/pg_restore client version.
- [ ] Dùng authentication an toàn, không ghi password vào command line.
- [ ] Tính CPU, I/O, network và connection budget.
- [ ] Chọn compression theo bottleneck.
- [ ] Lưu toàn bộ directory archive, không thiếu file.
- [ ] Dump roles/global objects khi cần.
- [ ] Chuẩn bị roles, tablespaces và extensions trên target.
- [ ] Quyết định giữ hay bỏ owner/ACL có chủ đích.
- [ ] Kiểm tra large objects và sequence state.
- [ ] Dùng ON_ERROR_STOP/exit-on-error và kiểm tra exit code.
- [ ] Chỉ dùng clean khi đã xác nhận phạm vi DROP.
- [ ] Không kết hợp single transaction với parallel restore.
- [ ] Kiểm tra TOC trước selective restore.
- [ ] Test restore trong môi trường tương thích.
- [ ] Đo RTO và xác minh dữ liệu/object/permissions.
- [ ] Bảo vệ dump bằng encryption, access control và retention.
- [ ] Theo dõi WAL/replication lag khi backup/restore lớn.
- [ ] Duy trì physical backup/WAL archive nếu cần PITR.

## 42. Tài liệu PostgreSQL chính thức

Đọc theo major version đang triển khai:

- [pg_dump](https://www.postgresql.org/docs/current/app-pgdump.html) — option, formats, parallel dump, snapshot và compression.
- [pg_restore](https://www.postgresql.org/docs/current/app-pgrestore.html) — archive restore, TOC list, parallel jobs và selective restore.
- [psql](https://www.postgresql.org/docs/current/app-psql.html) — chạy plain SQL scripts, ON_ERROR_STOP và single transaction.
- [pg_dumpall](https://www.postgresql.org/docs/current/app-pg-dumpall.html) — dump nhiều database và global objects.
- [Backup and Restore](https://www.postgresql.org/docs/current/backup.html) — tổng quan logical/physical backup.
- [SQL Dump](https://www.postgresql.org/docs/current/backup-dump.html) — logical dump và restore.
- [Continuous Archiving and Point-in-Time Recovery](https://www.postgresql.org/docs/current/continuous-archiving.html) — base backup, WAL và PITR.
- [Client Connection Defaults](https://www.postgresql.org/docs/current/libpq-envars.html) — biến môi trường libpq.
- [The Password File](https://www.postgresql.org/docs/current/libpq-pgpass.html) — cấu hình password file.
- [CREATE EXTENSION](https://www.postgresql.org/docs/current/sql-createextension.html) — extension installation trên target.
- [Database Roles](https://www.postgresql.org/docs/current/user-manag.html) — role và privilege management.
- [Tablespaces](https://www.postgresql.org/docs/current/manage-ag-tablespaces.html) — tablespace definitions và storage.

Các URL `/current/` trỏ tới tài liệu PostgreSQL hiện hành. Compression methods, archive options, progress reporting và một số restriction có thể thay đổi theo major version/build; kiểm tra tài liệu cùng phiên bản client/server trước khi vận hành.

## 43. Tổng kết

**pg_dump tạo logical backup cho một database; plain là SQL script, còn custom, directory và tar là archive dành cho pg_restore.** Định dạng cần được chọn theo cách dump, lưu trữ và restore thực tế.

1. **Plain** dễ đọc và restore bằng psql, nhưng không có selective/parallel restore qua pg_restore.
2. **Custom** tạo một archive file, có compression tích hợp, TOC và parallel restore.
3. **Directory** lưu TOC cùng các file dữ liệu riêng và là định dạng duy nhất hỗ trợ parallel dump; cũng hỗ trợ parallel restore.
4. **Tar** là archive TAR có thể chọn object khi restore, nhưng không hỗ trợ parallel dump/restore.
5. **Parallel dump và parallel restore là hai tính năng riêng.** Directory hỗ trợ dump song song; custom/directory hỗ trợ restore song song.
6. **pg_dump chỉ backup một database.** Roles và các global objects cần workflow riêng như pg_dumpall --globals-only.
7. **Owner, ACL, extension và tablespace cần được chuẩn bị khi restore** sang môi trường khác.
8. **Selective dump có thể thiếu dependencies.** Xem TOC và test restore trước khi dựa vào archive.
9. **Kiểm tra exit code, checksum và restore thực tế.** Đọc TOC thành công chưa chứng minh toàn bộ backup hợp lệ.
10. **Tính compression, worker count, disk, WAL và replica lag** theo năng lực source/target.
11. **Bảo vệ file dump như dữ liệu production** bằng encryption, access control và retention.
12. **Logical dump không thay physical backup/PITR.** Chọn chiến lược backup theo RPO/RTO của hệ thống.

Một quy trình backup tốt không kết thúc ở lúc pg_dump trả về thành công. Nó còn phải bảo vệ được file, kiểm tra được tính toàn vẹn và chứng minh rằng đội vận hành có thể restore dữ liệu trong thời gian yêu cầu.
