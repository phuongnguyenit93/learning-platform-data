# Phân biệt xuất dữ liệu, dump logic và bản sao lưu phục hồi được

Trong PostgreSQL, **xuất dữ liệu**, **dump logic** và **bản sao lưu phục hồi được** liên quan nhau nhưng không đồng nghĩa. Một file CSV chứa hàng dữ liệu để trao đổi; một file `pg_dump` có thể chứa cấu trúc và dữ liệu của một database ở snapshot; còn một kế hoạch khôi phục từ sự cố phải chứng minh rằng các file, quyền, phần mềm, WAL và quy trình thao tác còn đủ để đưa hệ thống trở lại **phạm vi và thời điểm mà doanh nghiệp cần**.

Ví dụ, file `orders.csv` không có users, indexes, constraints hoặc sequence state. Archive `pg_dump -Fc` có thể tái dựng một database nhưng không có lịch sử WAL để phục hồi tới 15:59 khi snapshot dump được lấy lúc 01:00. Một bản sao vật lý từ `pg_basebackup` có thể giúp phục hồi cluster, nhưng **PITR** tới thời điểm tùy chọn cần chuỗi WAL hoàn chỉnh và cơ chế truy xuất chúng. Ngay cả khi một file backup mở đọc được, việc chưa từng diễn tập restore vẫn là một rủi ro.

Bài học thuộc chương **Nhập xuất dữ liệu** của module **Database Engine Relational PostgreSQL**. Mục tiêu là chọn đúng công cụ theo nhu cầu trao đổi, di chuyển và bảo vệ dữ liệu, đồng thời phân biệt **có artifact** với **khả năng phục hồi đã được xác minh**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích sự khác nhau giữa export, logical dump, physical backup và một backup có thể phục hồi.
2. Dùng `COPY`, `\copy`, `pg_dump`, `pg_restore`, `pg_dumpall`, `pg_basebackup` đúng mục đích.
3. Phân biệt plain SQL, custom, directory và tar dump.
4. Hiểu ảnh hưởng của snapshots, DDL, nhiều databases và thao tác ngoài database tới tính nhất quán.
5. Chọn backup dựa trên **RPO** và **RTO**.
6. Hiểu quan hệ giữa base backup, WAL archive, recovery target và PITR.
7. Liệt kê roles, tablespaces, extensions, secrets, file cấu hình và dependencies bị bỏ sót trong nhiều cách export.
8. Khôi phục thử vào môi trường cô lập và xác minh dữ liệu lẫn khả năng sử dụng.
9. Tránh các thao tác nguy hiểm như restore nhầm production hoặc dùng `--clean` không kiểm soát.
10. Thiết kế checklist lưu trữ, encryption, kiểm tra integrity và diễn tập khôi phục định kỳ.

## 2. Bức tranh tổng quan

~~~text
                 PostgreSQL đang chạy
                          |
            +-------------+---------------+
            |             |               |
            v             v               v
         EXPORT        LOGICAL DUMP    PHYSICAL BACKUP
         COPY          pg_dump         pg_basebackup
         \copy         pg_dumpall      filesystem snapshot
            |             |               |
            v             v               v
      CSV/TSV/JSON     SQL/archive     Data pages + WAL
            |             |               |
            v             v               v
      COPY FROM/ETL    psql/pg_restore  Physical recovery
            |             |               |
            +-------------+---------------+
                          |
                          v
           Phục hồi thử + đo RPO/RTO +
             xác nhận toàn vẹn nghiệp vụ
~~~

### 2.1. Ba câu hỏi khác nhau

- **Export:** “Tôi muốn lấy những hàng/cột nào để dùng ở nơi khác?”
- **Logical dump:** “Tôi muốn dựng lại những objects và dữ liệu nào bằng ngữ nghĩa SQL?”
- **Recoverable backup:** “Nếu nguồn biến mất hoặc dữ liệu hỏng lúc này, tôi có thể dựng lại đúng phần hệ thống và đúng thời điểm mong đợi không?”

### 2.2. Backup là một hợp đồng kết quả

Cần xác định scope, mốc thời gian, độ đầy đủ, vị trí bản sao, quyền truy cập, encryption key, phiên bản PostgreSQL và điều kiện để restore. Đuôi file `.sql`, `.dump`, `.tar` hoặc `.csv` **không tự xác nhận** một backup đạt yêu cầu.

## 3. Bảng phân biệt chính

| Thuộc tính | Export dữ liệu | Logical dump | Physical backup với WAL |
|---|---|---|---|
| Công cụ | `COPY`, `\copy`, SQL/ETL | `pg_dump`, `pg_dumpall` | `pg_basebackup`, snapshot đúng chuẩn |
| Đơn vị | Query/bảng/phân vùng dữ liệu | Database hoặc cluster bằng nhiều dump | Toàn database cluster |
| Rows | Có | Có | Có qua file vật lý |
| Schema, indexes | Thường không | Có trong dump đầy đủ | Có trong file dữ liệu |
| Roles toàn cluster | Không | Cần globals qua pg_dumpall | Có trong cluster catalog |
| WAL để PITR | Không | Không | Phải bảo đảm đầy đủ WAL |
| Phục hồi một bảng | Import vào schema | Có thể chọn qua pg_restore | Thường cần dựng cluster phụ |
| Chuyển major version | Qua import | Thường thuận tiện khi compatible | Không dùng trực tiếp làm upgrade khác major |
| RPO | Theo dữ liệu đã xuất | Theo snapshot dump | Phụ thuộc base backup + WAL đã giữ |
| Khả năng phục hồi | Cần schema/ETL đích | Cần restore thành công | Cần physical restore + replay |
| Bảo vệ bí mật | Có thể chứa PII | Chứa dữ liệu, quyền và metadata | Chứa cluster data, có thể chứa secret |

Một **logical dump đầy đủ là backup hợp lệ** nếu restore từ snapshot đó thỏa RPO/RTO. Nói “pg_dump không phải backup” là quá cực đoan; nói “có pg_dump thì luôn có PITR” cũng sai.

## 4. Export dữ liệu nghĩa là gì?

Xuất dữ liệu tạo một file/cấu trúc kết quả để trao đổi, ETL, báo cáo hoặc đồng bộ có kiểm soát.

Ví dụ:

~~~sql
SELECT
    order_id, customer_id, total_amount, created_at
FROM sales.orders
WHERE created_at >= TIMESTAMPTZ '2026-11-01 00:00:00+07'
ORDER BY order_id;
~~~

### 4.1. Hợp đồng export

Cần mô tả danh sách và thứ tự cột, encoding UTF-8, định dạng CSV/JSON, dấu phân cách, cách quote, NULL, timezone, decimal precision, phân trang, query filter và format version.

### 4.2. Export không tự chứa database schema

Một CSV không biết table constraints, foreign keys, indexes, triggers, views, stored functions, sequences, identity columns, RLS policy hay role grants.

### 4.3. Không có bảo đảm dữ liệu đầy đủ

Một câu `SELECT` có WHERE chỉ xuất những rows phù hợp. Một file có đủ rows của bảng `orders` vẫn không chứa toàn bộ bảng customers, refunds, audit events.

### 4.4. Trường hợp nên dùng

Hợp tác dữ liệu với đối tác, phân tích, dashboard, nạp data warehouse, chia sẻ dữ liệu đã masking hoặc chuyển một tập records sang hệ thống mới theo schema contract.

## 5. COPY và \copy có địa điểm đọc/ghi file khác nhau

### 5.1. COPY TO server-side file

~~~sql
COPY sales.orders (order_id, customer_id, total_amount)
TO '/srv/postgresql/exports/orders.csv'
WITH (FORMAT csv, HEADER true);
~~~

Đường dẫn là filesystem **máy chủ PostgreSQL**. Ghi server-side file bị giới hạn quyền; ứng dụng không nên được cấp quyền server-file rộng chỉ vì cần tải CSV.

### 5.2. \copy trong psql

~~~text
\copy (SELECT order_id, customer_id, total_amount FROM sales.orders ORDER BY order_id) TO 'orders.csv' WITH (FORMAT csv, HEADER true)
~~~

Lệnh thuộc **psql**, file nằm trên máy chạy psql. Nó sử dụng COPY stream qua client; role vẫn cần quyền SELECT tương ứng.

### 5.3. COPY TO STDOUT

~~~sql
COPY (
    SELECT order_id, total_amount
    FROM sales.orders
    ORDER BY order_id
) TO STDOUT WITH (FORMAT csv, HEADER true);
~~~

Đưa dữ liệu ra giao thức client; không đồng nghĩa server lưu một file local của người dùng.

### 5.4. COPY FROM STDIN

Nhận dữ liệu do client gửi lên. PgJDBC có COPY API riêng cho streaming dữ liệu lớn khi cần, ngoài cách nhập qua psql.

### 5.5. Phân biệt lệnh trong tài liệu

`COPY` là SQL, còn `\copy` là psql meta-command. Đừng gửi chuỗi `\copy` qua JDBC PreparedStatement và kỳ vọng PostgreSQL server parse như SQL.

## 6. Ví dụ export CSV và ý nghĩa snapshot

Giả sử bảng:

~~~sql
CREATE SCHEMA sales;
CREATE TABLE sales.orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    total_amount NUMERIC(18,2) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

Trong psql:

~~~text
\copy (SELECT order_id, customer_id, total_amount, created_at FROM sales.orders ORDER BY order_id) TO 'orders-export.csv' WITH (FORMAT csv, HEADER true)
~~~

### 6.1. ORDER BY cần khi muốn thứ tự ổn định

Không có ORDER BY, PostgreSQL không bảo đảm xuất theo khóa chính. Thứ tự ổn định giúp so files và xử lý downstream.

### 6.2. NUMERIC khi xuất là text

Một con số trong CSV là textual representation; schema lúc import mới quyết định NUMERIC precision/scale, giới hạn và rounding.

### 6.3. TIMESTAMPTZ chịu session timezone khi hiển thị

Hai exports có thể biểu diễn offset khác nhau của cùng một instant. Ghi rõ quy ước timezone, không suy rằng một text timestamp duy nhất giữ ZoneId ban đầu.

### 6.4. Một export query có snapshot theo MVCC

Nhưng **hai export queries khác nhau có thể có hai snapshots khác nhau**. Nếu cần nhất quán giữa nhiều bảng/file, phải thiết kế transaction/snapshot strategy hoặc ETL synchronization rõ.

## 7. Export nhiều bảng có thể không nhất quán

~~~text
10:00   Export customers.csv  (snapshot S1)
10:01   Transaction cập nhật customer và tạo order
10:02   COMMIT
10:03   Export orders.csv     (snapshot S2)
~~~

Khi nhập lại, có thể thấy order mới nhưng customer metadata của thời điểm cũ. Tình trạng này không nhất thiết làm một trong hai file “hỏng”, mà cho thấy hai files phản ánh thời điểm khác nhau.

### 7.1. MVCC không tự đồng bộ files

Để giữ một logical snapshot thống nhất, cần cùng transaction isolation phù hợp, hoặc exported snapshot/coordination qua clients khi triển khai được.

### 7.2. Long-running export có ảnh hưởng vận hành

Một snapshot kéo dài có thể giữ old row versions, ảnh hưởng VACUUM và bloat. Khi export lớn, cân nhắc incremental ETL/CDC với semantics rõ.

### 7.3. Ngoại lệ đến từ hệ thống bên ngoài

Nếu orders có references tới object storage và payment provider, PostgreSQL snapshot không chụp đồng thời trạng thái của các dịch vụ đó.

## 8. Vì sao CSV chưa đủ làm disaster backup?

Giả sử bạn chỉ có:

~~~text
orders.csv
customers.csv
payments.csv
~~~

Các file không tự mang:

- CREATE TABLE và toàn bộ kiểu cột.
- PRIMARY KEY, UNIQUE, CHECK, FOREIGN KEY.
- Sequences/identity state và index definitions.
- Triggers, functions, procedures, materialized views.
- Role definitions, privileges và row-level security.
- Extension versions, collations, tablespaces.
- Thứ tự import phù hợp references.
- WAL/timeline để phục hồi gần thời điểm lỗi.

### 8.1. Import có thể kích hoạt logic mới

`COPY FROM` đi qua semantics kiểm tra constraints/triggers phù hợp. Nếu triggers đích phát message hoặc ghi audit, nạp CSV có thể có tác dụng phụ khác với phục hồi vật lý.

### 8.2. Import dữ liệu có ID rõ phải xét sequences

Nếu nạp lại order IDs 1–10000, sequence trong database đích có thể không tự tăng theo giá trị lớn nhất. Sau import, cần kiểm tra trạng thái sinh ID để tránh lỗi trùng khóa.

### 8.3. CSV không thể xác minh recovery toàn ứng dụng

Một báo cáo `COUNT(*)` trùng không chứng minh references, quyền và nghiệp vụ vẫn hoạt động.

## 9. Logical dump là gì?

**Logical dump** là bản biểu diễn của các objects và dữ liệu theo logic SQL, không phải copy nguyên data pages của PostgreSQL.

Các công cụ liên quan:

- `pg_dump` — dump một database.
- `pg_dumpall` — tạo SQL script cho các databases và globals của cluster theo options.
- `pg_restore` — khôi phục archive từ những non-plain formats của pg_dump.
- `psql` — thực thi SQL script plain text.

### 9.1. Dump đầy đủ chứa nhiều hơn rows

Trong phạm vi được chọn, có thể chứa CREATE TABLE, INDEX, VIEW, constraints, functions, data, ownership và GRANT statements.

### 9.2. Dump logic không chứa WAL history

Logical dump mô tả snapshot, không bao gồm chuỗi WAL để replay các transactions sau snapshot.

### 9.3. Dump dùng cho migration và rebuild

Vì data được chuyển thành logical representation, dump/restore thường phù hợp để chuyển sang PostgreSQL major version mới khi objects/extensions và SQL features tương thích.

### 9.4. Không nhầm với pg_dump schema-only

Một dump `--schema-only` không chứa rows; một dump `--data-only` không tự tạo toàn bộ schema trong database trống.

## 10. Ví dụ pg_dump custom archive

Ví dụ terminal, với database nguồn `trainingdb`:

~~~sh
pg_dump -h db.example.test -U backup_reader -d trainingdb -F c -f trainingdb.dump
~~~

### 10.1. -d chọn đúng một database

`pg_dump` không tự dump mọi database của cluster.

### 10.2. -F c chọn custom archive

Định dạng custom có mục lục TOC, hỗ trợ lựa chọn objects và các hình thức restore linh hoạt.

### 10.3. -f chọn artifact đích

Nên lưu tại filesystem/object storage có phân quyền, mã hóa và retention phù hợp; không đưa vào thư mục web public.

### 10.4. Password không đặt trong command

Không đưa production secret vào URI/command line hoặc ghi ra log. Dùng prompt, password file hoặc secret injection an toàn.

### 10.5. Kiểm tra command failure

File tồn tại chưa đủ: phải kiểm tra exit status, stderr, log job và khả năng đọc bằng pg_restore/restore thật.

## 11. Các định dạng pg_dump

| Format | Tùy chọn | Restore | Ý nghĩa |
|---|---|---|---|
| Plain SQL | `-F p` | `psql` | Script SQL dạng text |
| Custom | `-F c` | `pg_restore` | Archive có TOC, linh hoạt |
| Directory | `-F d` | `pg_restore` | Folder archive, phù hợp parallel workflows |
| Tar | `-F t` | `pg_restore` | Tar archive, có các giới hạn riêng |

### 11.1. Plain SQL

~~~sh
pg_dump -d trainingdb -F p -f trainingdb.sql
psql -X -v ON_ERROR_STOP=1 -d training_restore -f trainingdb.sql
~~~

`-X` giúp tránh nạp user startup file của psql; `ON_ERROR_STOP=1` khiến script dừng khi gặp lỗi SQL. Nên chạy trên database phục hồi được chuẩn bị sẵn.

### 11.2. Custom

~~~sh
pg_dump -d trainingdb -F c -f trainingdb.dump
pg_restore --list trainingdb.dump
~~~

Dùng `pg_restore` để đọc file archive, không dùng psql -f như plain SQL.

### 11.3. Directory

~~~sh
pg_dump -d trainingdb -F d -f trainingdb-directory
~~~

Một directory archive gồm nhiều files; phải giữ đầy đủ cả thư mục cùng metadata, không copy một file lẻ.

### 11.4. Tar

~~~sh
pg_dump -d trainingdb -F t -f trainingdb.tar
~~~

Tar có khác biệt/hạn chế so với custom/directory, đặc biệt trong một số kiểu restore song song. Đừng suy từ đuôi tar rằng có thể giải nén rồi start PostgreSQL như bản sao vật lý.

### 11.5. Compression

Một số định dạng/options hỗ trợ nén; khả năng compression, algorithm và compatibility tùy PostgreSQL/pg_dump version. Nén giúp giảm storage nhưng làm thay đổi CPU và thời gian restore.

## 12. pg_restore: chọn đúng đích và đúng nội dung

~~~sh
pg_restore --list trainingdb.dump
createdb training_restore
pg_restore -d training_restore trainingdb.dump
~~~

### 12.1. Database đích thường cần tồn tại

Nếu không dùng create database mode thích hợp, `-d` phải trỏ đến một database đã được tạo.

### 12.2. --schema-only và --data-only

Phù hợp khi tách DDL/data. Không xem mỗi một phần là full database backup.

### 12.3. -n và -t

Có thể chọn schema/table từ archive, nhưng dependencies bên ngoài selection không nhất thiết tự được phục hồi đầy đủ.

### 12.4. -j parallel jobs

Một số archive formats hỗ trợ song song khi restore. Có thể cải thiện thời gian với database lớn, nhưng dùng nhiều connections và tăng CPU/disk I/O, không đảm bảo tuyến tính.

### 12.5. --clean và --if-exists cực kỳ nhạy cảm

`--clean` có thể DROP những objects trước khi tạo lại; `--if-exists` không làm thao tác vô hại. Chỉ dùng khi đã xác minh host, database, phạm vi và phương án rollback.

### 12.6. --no-owner và --no-acl

Có thể hữu ích khi chuyển môi trường khác roles, nhưng bỏ ownership/grants đồng nghĩa security state thay đổi. Phải tái tạo quyền bằng kế hoạch riêng.

## 13. Snapshot nhất quán của pg_dump

`pg_dump` dùng snapshot của database để tạo một view nhất quán ngay khi writers khác tiếp tục cập nhật theo MVCC.

~~~text
01:00  pg_dump lấy snapshot S
01:05  Writer INSERT orders #101 COMMIT
01:20  pg_dump tiếp tục dump các bảng theo snapshot S
01:40  pg_dump hoàn thành artifact
~~~

### 13.1. Một dump không phải chụp “tới 01:40”

Dù artifact tạo xong lúc 01:40, snapshot đại diện trạng thái sớm hơn, không chứa giao dịch commit sau snapshot.

### 13.2. Không khóa mọi DML

pg_dump có thể chạy trên database đang hoạt động, nhưng có những locks để bảo vệ cấu trúc và có thể xung đột với DDL.

### 13.3. Không phải snapshot distributed toàn hệ thống

Các dịch vụ ngoài database, nhiều databases trong cùng cluster và external objects không tự được chụp tại cùng một distributed timestamp.

### 13.4. Long-running snapshot có chi phí

Một dump kéo dài có thể giữ old versions, trì hoãn cleanup VACUUM/bloat và làm tăng contention với schema changes.

### 13.5. Sequence có semantics riêng

Sequence operations không rollback như row updates MVCC. Khi dump/restore trong hệ thống có writes liên tục, cần kiểm tra consistency của generated IDs trước khi mở ghi trở lại.

## 14. Phạm vi không tự có trong pg_dump

`pg_dump -d trainingdb` không có nghĩa đã tạo bản sao toàn bộ cluster và môi trường vận hành.

### 14.1. Global roles và mật khẩu

Role definitions là cluster-wide; dump database có thể chứa tham chiếu tới owner/grantee nhưng không phải danh sách đầy đủ CREATE ROLE của cluster.

### 14.2. Tablespace definitions

Tablespace paths và đặc quyền thuộc môi trường cluster. Máy đích có thể cần recreate hoặc remap đúng cách.

### 14.3. Cấu hình và network

Các file `postgresql.conf`, `pg_hba.conf`, TLS keys/certs, OS services, DNS/firewall và secrets có thể nằm ngoài phạm vi backup logic.

### 14.4. Extensions và external binaries

Dump có thể có CREATE EXTENSION và definitions liên quan; để restore còn cần extension package, compatible binary và thiết lập trên server đích.

### 14.5. Large objects và tùy chọn lọc

Full dumps thường bao gồm large objects theo semantics của pg_dump, nhưng partial dump với `-n`/`-t` và các flags liên quan có thể không chứa chúng như mong đợi. Phải xác định backup scope, không tự giả định.

### 14.6. Foreign tables, message brokers và object storage

Khôi phục SQL definitions không tự mang data của remote databases/foreign servers, external objects hoặc hàng đợi bên ngoài.

## 15. pg_dumpall cho cluster globals

Để dump role/tablespace definitions theo khả năng của công cụ:

~~~sh
pg_dumpall --globals-only -f globals.sql
~~~

### 15.1. Restore globals trước database khi thích hợp

Nếu database dump chứa GRANT cho role `app_reader`, role đó cần tồn tại trên cluster đích hoặc phải thay đổi quyền sau restore.

### 15.2. Globals có thể chứa dữ liệu nhạy cảm

Role password verifiers hoặc metadata xác thực là bí mật nhạy cảm. Bảo vệ file dump globals bằng encryption, IAM và retention chặt.

### 15.3. pg_dumpall là plain SQL

Full dumpall và globals-only output là SQL scripts để restore qua psql theo quyền phù hợp; không phải custom archive dùng pg_restore.

### 15.4. Không bảo đảm một snapshot xuyên databases

pg_dumpall có thể xử lý databases nối tiếp, nên không có một snapshot MVCC nguyên tử cho mọi database trong cluster. Dữ liệu liên quan nhiều databases cần coordination riêng.

### 15.5. Dựng lại cluster logic không là dựng lại hạ tầng

Phải kiểm tra HA topology, connection endpoints, certificates, tablespace directories, replication slots, WAL retention và những cấu hình vận hành khác.

## 16. Logical dump có thể được coi là backup không?

**Có**, với mục tiêu phục hồi rõ ràng và khi đã thực sự kiểm chứng restore.

Ví dụ doanh nghiệp chấp nhận mất tối đa một ngày dữ liệu, database nhỏ và có thể phục hồi trong vài chục phút. Dump hằng ngày, gửi offsite, kiểm tra integrity và restore drills có thể đáp ứng.

### 16.1. Ràng buộc về thời điểm

Nếu dump snapshot lúc 01:00, lỗi lúc 16:00, dump chỉ phản ánh trạng thái lúc snapshot. Không thể dùng pg_restore tự replay giao dịch tới 15:59 chỉ từ file dump.

### 16.2. Ràng buộc về tốc độ

Logical restore phải tái tạo indexes, constraints và nạp rows. Với dữ liệu rất lớn, có thể vượt RTO dù dump hoàn toàn chính xác.

### 16.3. Ràng buộc về phạm vi

Nếu ứng dụng cần roles, extensions, filesystem files, secrets và dịch vụ ngoài database, phải bổ sung những thành phần đó vào kế hoạch.

### 16.4. Lợi ích chọn lọc

Custom dump cho phép dựng bản phụ và phục hồi một số bảng/objects dễ hơn physical restore, nhưng không phải mọi dependency đều tự được kéo theo.

## 17. Bản sao lưu vật lý là gì?

**Physical backup** chụp dữ liệu ở mức tệp/trang vật lý theo quy trình mà PostgreSQL có thể phục hồi nhất quán, thay vì tạo script SQL.

Các cách phổ biến:

- `pg_basebackup` dùng replication protocol.
- Filesystem/storage snapshots được phối hợp theo yêu cầu PostgreSQL.
- Công cụ backup chuyên dụng quản lý full/differential/incremental và WAL archive.

### 17.1. Không copy data directory bừa khi server đang chạy

Copy files tuần tự dưới writes liên tục có thể bắt những data pages ở thời điểm khác nhau. Không có WAL/backup protocol thích hợp, bản copy có thể không recover được dù đủ tên file.

### 17.2. Base backup thường ở phạm vi cluster

Nó chứa dữ liệu của cluster gồm nhiều databases và catalog chung, không chọn một bảng như COPY/export.

### 17.3. Ràng buộc về PostgreSQL major version

Bản vật lý gắn với format data directory của PostgreSQL version cụ thể. Không dùng nó như đường nâng cấp trực tiếp giữa major versions, trừ quy trình đặc biệt được hỗ trợ.

### 17.4. Tài nguyên và filesystem

Cần xem tablespaces, symbolic links, permissions, owner, đường dẫn trên host mới và tài nguyên disk khi restore.

## 18. pg_basebackup: ví dụ

~~~sh
pg_basebackup -h primary.example.test -U backup_agent -D /backup/base-20261114 -F p -X stream -P
~~~

### 18.1. -D: thư mục đích

Phải là vị trí phù hợp/đủ dung lượng. Không trỏ vào data directory của primary đang chạy.

### 18.2. -F p: plain physical backup

Lưu dữ liệu theo dạng thư mục physical files. Các dạng tar có quy tắc xử lý khác.

### 18.3. -X stream: nhận WAL cần thiết khi lấy backup

Cho phép thu WAL liên quan trong quá trình base backup khi điều kiện connection/replication phù hợp. Một base backup nhất quán về mốc kết thúc **không đồng nghĩa** archive đủ mọi WAL tương lai cho PITR.

### 18.4. -P: tiến độ

Tùy chọn hiển thị tiến độ, không tự tăng mức bảo vệ.

### 18.5. Quyền kết nối

Role backup cần quyền replication phù hợp, HBA và cấu hình `max_wal_senders` đủ; nên cấp ít quyền nhất cần thiết.

### 18.6. PostgreSQL vẫn cần kiểm chứng sau backup

Command báo success là điều kiện cần, nhưng restore và kiểm tra hoạt động mới chứng minh mục tiêu backup.

## 19. Write-Ahead Log (WAL) liên quan thế nào đến backup?

WAL là nhật ký ghi trước (*write-ahead log*) phục vụ cơ chế crash recovery và replication của PostgreSQL. Nó ghi lại các thay đổi vật lý/logical ở mức cần thiết để PostgreSQL đưa data pages về trạng thái nhất quán theo quy tắc engine.

~~~text
Một transaction thay bảng
          |
          v
Ghi records vào WAL
          |
          v
Commit / data pages được flush theo cơ chế
          |
          +------> WAL archive độc lập
                         |
                         v
                 Replay khi phục hồi
~~~

### 19.1. WAL không phải bản copy toàn database

Một tập WAL files không tự tạo ra toàn bộ tables/indexes như base backup. Để PITR, bạn cần một **base backup có thể phục hồi** và chuỗi WAL đủ từ base backup tới recovery target.

### 19.2. pg_wal trên primary chưa phải offsite archive

Nếu disk/host primary mất, WAL chỉ tồn tại trên disk đó cũng có thể mất. Cần một cơ chế lưu WAL tới storage độc lập với kiểm soát retention và integrity.

### 19.3. WAL archive không được thiếu đoạn

Nếu một WAL segment cần cho replay bị mất, bạn có thể không thể đạt target mong muốn. Một bản backup base có checksum đúng nhưng WAL chain hỏng vẫn không đạt mục tiêu PITR.

### 19.4. Retention liên quan base backups

Lưu 30 ngày base backups nhưng xóa WAL cần thiết cho các backup đó sẽ làm giảm hoặc mất khả năng phục hồi tới một số thời điểm. Phải thiết kế chính sách xóa cũ cho cả **backup chain**.

### 19.5. Replication slots không thay archive

Replication slots có thể giữ WAL cho consumers, nhưng không làm WAL tự có bản sao an toàn offsite. Slot bị bỏ quên còn có thể giữ WAL vô hạn và làm disk đầy nếu không đặt giới hạn/monitoring phù hợp.

## 20. Continuous archiving và Point-In-Time Recovery

**PITR** (*point-in-time recovery*) đưa PostgreSQL cluster về trạng thái tương ứng một mốc phục hồi được chọn, bằng base backup và WAL replay.

~~~text
00:00   Base backup B0
00:30   WAL archive W1
01:00   WAL archive W2
01:30   WAL archive W3
01:47   Một lệnh DELETE nhầm COMMIT
02:00   Server báo sự cố
            |
            v
     Phục hồi B0 trong cluster phụ
            |
            v
     Replay WAL tới trước lệnh DELETE
            |
            v
     Kiểm tra dữ liệu và lựa chọn cutover
~~~

### 20.1. Target phải được xác định đúng

Một mốc thời gian địa phương không ghi offset có thể gây mơ hồ. Nên xác định timestamp kèm timezone và đối chiếu transaction commit time/logs trước khi chọn target.

### 20.2. PITR là thao tác ở mức cluster

Không trực tiếp dùng WAL để “undo một row” trong production đang hoạt động. Với lỗi xóa một bảng, thường dựng **cluster phụ** ở thời điểm trước lỗi, trích dữ liệu cần cứu và merge cẩn thận với dữ liệu hợp lệ mới.

### 20.3. Không phải giao dịch nào cũng có thể chọn lọc replay

WAL của PostgreSQL là cơ chế recovery, không phải API lọc mọi writes của một transaction bất kỳ và giữ lại các transactions sau đó như không có phụ thuộc.

### 20.4. Timeline của cluster

Sau promote/failover, PostgreSQL có thể tạo timeline mới; backup/recovery cần biết đúng WAL history path, không ghép nhầm segments giữa các nhánh timeline.

### 20.5. “PITR chạy được” cần được diễn tập

Phải có procedure để lấy artifact, dựng cluster trong môi trường cô lập, replay WAL, kiểm tra data, promote khi thích hợp và mở lại ứng dụng an toàn.

## 21. Minh họa recovery configuration

Trong các phiên bản PostgreSQL hiện đại, một quy trình recovery có thể sử dụng `recovery.signal` và các tham số phù hợp. Ví dụ dưới đây là **mô tả ý tưởng**, không phải hướng dẫn chạy trực tiếp trên production:

~~~conf
restore_command = 'command-to-fetch-archived-wal %f %p'
recovery_target_time = '2026-11-14 10:00:00+07'
recovery_target_action = 'pause'
~~~

### 21.1. restore_command là placeholder

`command-to-fetch-archived-wal` không phải lệnh thực thi. Trong hệ thống thực, nó cần được thay bằng chương trình nhận tên file WAL và tải đúng nội dung từ archive với logging/exit code đầy đủ.

### 21.2. recovery.signal

Dùng theo hướng dẫn phiên bản đang chạy; không đem nguyên hướng dẫn `recovery.conf` của các bản PostgreSQL rất cũ áp dụng cho PostgreSQL hiện đại.

### 21.3. Phân biệt pause và promote

Dừng ở recovery target để kiểm tra không giống tự động cho cluster mới nhận write traffic. Cutover phải được kiểm soát, tránh hai primary cùng được ứng dụng ghi.

### 21.4. Không thử trực tiếp trên data directory primary

Một thao tác nhầm recovery files hoặc start nhầm database có thể gây hỏng/gián đoạn. Luôn dựng thư mục phục hồi tách biệt, với cả network/ports và credentials cách ly.

### 21.5. Cần chính sách fail-safe khi không có đủ WAL

Quy trình phải thất bại rõ ràng nếu archive thiếu segment hoặc không thể xác định target, không âm thầm gọi thành công chỉ vì PostgreSQL start được ở một điểm cũ hơn.

## 22. Physical base backup có thể phục hồi mà không PITR được không?

Có những trường hợp base backup có đủ WAL cần thiết để khởi động nhất quán tại điểm kết thúc backup, nhưng **không có đủ WAL history tiếp theo** cho target tùy ý.

### 22.1. Hai mục tiêu khác nhau

- **Restore base backup:** phục hồi về một trạng thái nhất quán được xác định bởi backup và WAL cần thiết.
- **PITR:** phục hồi tới thời điểm cụ thể trong khoảng lịch sử đã lưu.

### 22.2. Không có WAL bổ sung sau backup

Nếu chỉ có base backup 01:00 và không có WAL archive từ đó, không thể yêu cầu một mốc 13:59 sau backup.

### 22.3. Full backup hằng ngày chưa bảo đảm RPO thấp

Nếu business chỉ chấp nhận mất 5 phút mà bạn backup full hằng đêm, chỉ những bản full backup không thể đáp ứng RPO đó. Cần thiết kế WAL archival/streaming hoặc cách khác phù hợp.

### 22.4. WAL archive không tự là đồng bộ tức thời

WAL có thể được archive theo segment/timeout và chịu network/storage delays. RPO thực tế phụ thuộc việc WAL nào đã đến nơi bền vững trước sự cố.

## 23. Snapshot ở storage layer có được gọi backup không?

Có thể, **nếu** đó là một snapshot theo quy trình đảm bảo nhất quán/khả năng crash recovery của PostgreSQL và bao gồm toàn bộ những storage components cần thiết.

### 23.1. Atomic snapshot

Các volumes chứa data directory và tablespaces phải được chụp đồng bộ phù hợp hoặc có cơ chế bổ sung để PostgreSQL phục hồi nhất quán.

### 23.2. Ảnh chụp một volume thiếu tablespace

Nếu database dùng tablespace trên volume khác, chỉ snapshot PGDATA có thể thiếu các datafiles quan trọng.

### 23.3. Snapshot khi PostgreSQL đang chạy

Cần hiểu crash consistency, WAL, checkpoint và yêu cầu của nền tảng. Một lệnh copy từng file hoặc một snapshot thiếu WAL không được tự coi là backup hợp lệ.

### 23.4. Snapshot vẫn có single point of failure

Snapshot trên cùng storage account/host bị xóa cùng primary không giúp disaster recovery. Có chính sách sao chép offsite, IAM và khả năng khôi phục khi cloud region mất.

### 23.5. Snapshot và logical export là hai lớp khác nhau

Một snapshot vật lý không thay thế CSV cho đối tác, và CSV không thay snapshot cho toàn cluster.

## 24. Bản sao lưu incremental và differential

Một số hệ thống PostgreSQL sử dụng incremental hoặc differential backups để giảm dữ liệu chép mỗi lần. Khả năng native incremental backup, restore chain và công cụ đi kèm như `pg_combinebackup` phụ thuộc phiên bản; các công cụ chuyên dụng cũng có cơ chế riêng.

### 24.1. Full backup

Chứa một baseline theo phương thức backup đã chọn. Thường dễ khôi phục hơn nhưng tốn storage và thời gian sao chép.

### 24.2. Incremental

Chỉ lưu những phần thay đổi so với baseline/backup tham chiếu theo cách công cụ định nghĩa. Restore có thể cần toàn bộ chain; thiếu một thành phần có thể khiến chain vô dụng.

### 24.3. Differential

Theo nhiều công cụ, lưu thay đổi so với một full backup. Không coi tất cả backup products định nghĩa incremental/differential giống nhau.

### 24.4. Đừng nhầm size nhỏ với tính đầy đủ

Một file incremental 500 MB không thể tự phục hồi một cluster 2 TB nếu thiếu full base và các dependencies cần thiết.

### 24.5. Định nghĩa retention theo chain

Không xóa base backup cũ mà các incrementals còn phụ thuộc. Quản lý catalog, manifest, checksums và khả năng truy xuất trên các storage tiers.

## 25. RPO và RTO là hai chỉ tiêu độc lập

**RPO — Recovery Point Objective:** mức mất dữ liệu tối đa có thể chấp nhận, thường đo bằng khoảng thời gian từ trạng thái phục hồi tới thời điểm sự cố.

**RTO — Recovery Time Objective:** khoảng thời gian tối đa có thể chấp nhận để phục hồi dịch vụ đáp ứng yêu cầu sau sự cố.

### 25.1. Ví dụ

~~~text
Backup snapshot:       01:00
Sự cố:                13:00
Phục hồi xong:        15:30

Mất dữ liệu gần nhất: 12 giờ (theo backup 01:00)
Thời gian phục hồi:   2 giờ 30 phút
~~~

Nếu RPO yêu cầu 15 phút và RTO yêu cầu 1 giờ, phương án này không đạt cả hai.

### 25.2. RPO thực khác target

Có WAL archiving không chứng minh mọi transaction đã có bản sao tại nơi an toàn ngay lập tức. Phải đo độ trễ archiving thực tế, xác nhận WAL cuối đã bền vững và có thể replay.

### 25.3. RTO gồm nhiều công đoạn

Download backups, decrypt, provision instance, restore, replay WAL, build indexes (logical), chạy migrations, kiểm tra dữ liệu, điều chỉnh endpoints và kiểm tra ứng dụng đều tính vào thời gian phục hồi.

### 25.4. RPO=0 thường là yêu cầu rất khó

Không thể suy từ WAL archiving bất đồng bộ rằng không mất transaction nào. Nếu yêu cầu zero data loss, cần kiến trúc đồng bộ/HA phù hợp cùng threat model rõ, và vẫn cần backup độc lập.

### 25.5. RPO và RTO không thay nhau

Backup mỗi 5 phút không đảm bảo khôi phục trong 5 phút. Replica promote rất nhanh không nhất thiết giúp phục hồi dữ liệu bị xóa nhầm, và cũng không thay lịch sử backup.

## 26. Chọn giải pháp theo RPO/RTO

| Nhu cầu | Giải pháp tham khảo | Điều cần đo |
|---|---|---|
| Chia sẻ dữ liệu cho đối tác | CSV/JSON export | Contract và chất lượng file |
| Chuyển một số bảng | COPY/import hoặc pg_dump chọn lọc | Dependencies, schema, validation |
| Di chuyển database sang version mới | Logical dump/restore | Compatibility, downtime |
| Khôi phục database nhỏ về tối qua | pg_dump full + globals | Restore time, mất dữ liệu |
| Khôi phục cluster lớn sau mất disk | Physical base backup | Provision, WAL, network I/O |
| Khôi phục trước lệnh xóa nhầm | Physical backup + WAL/PITR | Recovery target, WAL chain |
| Mất primary, cần nhận traffic nhanh | HA/standby promote | RTO thực, failover correctness |
| Bảo vệ trước xóa nhầm lan sang standby | Backup lịch sử độc lập | Retention, PITR khả dụng |
| Chống ransomware/storage compromise | Offsite/immutable backup | Quyền xóa, key recovery |

### 26.1. Có thể kết hợp nhiều chiến lược

Một hệ thống lớn có thể đồng thời có base backup + WAL cho PITR, logical dump cho migrations và CSV export cho analytics.

### 26.2. Không chọn chỉ theo tên công cụ

Cần thử restore theo business scenarios, không chỉ xem job báo “backup completed”.

## 27. High availability không tự là backup

Streaming replication có thể giúp một standby luôn theo kịp primary. Nhưng nếu primary thực hiện `DROP TABLE` và WAL được replica replay, standby cũng có thể mất bảng.

### 27.1. Replication sao chép thay đổi đúng lẫn sai

Xóa nhầm, UPDATE sai, DDL lỗi và nhiều corruption/application mistakes có thể lan tới replica theo kiểu replication.

### 27.2. Standby promote phục vụ availability

Nó giúp giảm RTO khi primary hỏng; không tự đảm bảo có lịch sử giữ lại để PITR.

### 27.3. Logical replication cũng không thay backup

Logical replication có thể phục vụ migration/integration nhưng không mặc định sao chép mọi roles, DDL, extension binaries, sequences hoặc toàn cluster với semantics một backup.

### 27.4. Snapshot replica có thể tạo nguồn backup

Một số backup workflows chạy trên standby hoặc chụp storage snapshot, nhưng cần bảo đảm tính nhất quán và khả năng lấy WAL. Không mặc định “lấy file từ standby” đã đủ.

## 28. Khả năng tương thích phiên bản và kiến trúc

### 28.1. pg_dump và server source

`pg_dump` thường hỗ trợ dump nhiều phiên bản server cũ hơn trong phạm vi tương thích, nhưng không được tùy tiện dùng pg_dump quá cũ để dump server mới hơn nó. Quy tắc phiên bản cụ thể cần đối chiếu với bộ công cụ đang dùng.

### 28.2. Logical dump đến server mới

Logical SQL representation có lợi khi nâng major version, nhưng extension, collations, syntax, privileges và object dependencies có thể không tương thích. Phải thử restore/migration rehearsal.

### 28.3. Physical backups

Phải tương thích binary/database format, PostgreSQL major version, data checksum settings, architecture và tablespace layout theo yêu cầu. Không khởi động PGDATA cũ bằng binary major mới để “restore”.

### 28.4. Encoding, locale và collations

Một dump chứa dữ liệu Unicode vẫn có thể gặp khác biệt sắp xếp/uniqueness nếu collations/ICU/libc thay đổi giữa nguồn và đích. Cần xem lại indexes/constraints và khả năng reindex.

### 28.5. Extensions

Một dump nói CREATE EXTENSION chưa chắc cài được nếu máy đích thiếu extension library/version. Ghi lại extension inventory trước migration.

## 29. File backup đầy đủ khác file backup nguyên vẹn

Một file có thể tồn tại nhưng:

- Được tạo bởi job thất bại giữa chừng.
- Bị truncate do hết dung lượng.
- Bị lỗi mạng khi upload.
- Bị mã hóa bằng key đã mất.
- Bị xóa bớt một file trong directory archive.
- Không có các WAL segments cần cho PITR.
- Không tương thích version đích.
- Có dữ liệu nhưng thiếu roles/permissions/extension dependencies.
- Nằm trên cùng disk bị hỏng với primary.

### 29.1. Integrity và recoverability không đồng nghĩa

Hash/checksum giúp chứng minh file không bị thay đổi so với một bản hash được tin cậy; **không chứng minh database restore sẽ hoạt động**.

### 29.2. pg_restore --list

Có thể kiểm tra custom archive có TOC đọc được:

~~~sh
pg_restore --list trainingdb.dump
~~~

Đây là bước kiểm tra ban đầu hữu ích, nhưng không thay restore đầy đủ.

### 29.3. pg_verifybackup

Với physical backups có manifest được hỗ trợ, `pg_verifybackup` có thể kiểm tra manifest/checksums và một số tính nhất quán của backup theo phạm vi công cụ. Nó không thay kiểm tra phục hồi đầy đủ, đặc biệt về WAL tương lai và ứng dụng.

### 29.4. Restore drill là bằng chứng mạnh hơn

Dựng PostgreSQL mới từ artifact, mở query và test invariants nghiệp vụ cho kết quả có giá trị hơn chỉ thống kê bytes hoặc checksum.

## 30. Backup metadata và manifest vận hành

Với mỗi backup, nên lưu metadata ngoài file dữ liệu:

| Trường | Ví dụ | Ý nghĩa |
|---|---|---|
| Backup ID | `pg-base-20261114-001` | Truy vết |
| Scope | `cluster/orders-db` | Thành phần được bảo vệ |
| Type | logical/physical/incremental | Đường restore |
| Start/end | Timestamp có timezone | Vòng đời job |
| Snapshot/consistent point | LSN/time metadata | Mốc khôi phục |
| PostgreSQL version | Major/minor | Compatibility |
| Tool version | pg_dump, backup tool | Tái lập |
| WAL/timeline coverage | LSN/timeline range | Xác định PITR |
| Storage URI | Private object storage path | Truy xuất |
| Encryption key reference | Key ID, không ghi key | Giải mã |
| Checksum/manifest | Hash danh mục | Integrity |
| Last restore test | Kết quả và thời gian | Recoverability evidence |

### 30.1. Không đặt mật khẩu trong manifest

Metadata không được chứa plaintext database password, storage token, IAM secret hoặc encryption key material.

### 30.2. Thời gian file creation không phải snapshot time

Một dump chạy 40 phút có file modified time sau snapshot rất lâu. Phải ghi mốc tạo snapshot đúng semantics.

### 30.3. Restore guide nên versioned

Nếu quy trình khôi phục chỉ nằm trong trí nhớ một DBA, lúc người đó vắng mặt có thể không đáp ứng RTO.

## 31. Retention và chính sách nhiều bản sao

### 31.1. Một bản sao trên cùng máy chủ là rủi ro

Nếu disk hỏng hoặc instance bị xóa, file trong thư mục `/backup` cùng host cũng mất. Cần offsite/cross-zone hoặc storage độc lập theo threat model.

### 31.2. Nguyên tắc 3-2-1 là định hướng

Có thể dùng nhiều bản sao trên những loại/storage domains khác nhau và ít nhất một bản ở địa điểm độc lập. Tuy nhiên số lượng cụ thể phải dựa trên regulatory, data volume, budget và threat model.

### 31.3. Immutable/append-only backups

Giảm nguy cơ tài khoản production có quyền xóa mọi backups sau khi bị compromise. Cần phân quyền backup writers, restore readers và delete admins.

### 31.4. Retention phải gắn WAL

Khi hết hạn một base backup, không được xóa WAL đang cần cho backup khác hoặc một target recovery nằm trong retention. Dùng dependency-aware retention.

### 31.5. Quyền xóa và encryption key

Nếu kẻ tấn công có quyền xóa cả backup lẫn key hoặc nếu key bị mất, có thể không recover được. Tách IAM, lưu key và kiểm tra recovery từ key vault.

## 32. Rủi ro bảo mật của exports và dumps

### 32.1. CSV chứa PII

Một export có tên, email, địa chỉ hoặc số giao dịch là tài sản nhạy cảm. Không tự đưa lên dịch vụ chia sẻ công khai chỉ vì nó là “file báo cáo”.

### 32.2. Plain SQL dump có thể chứa secrets trong dữ liệu

API keys, hashes, session tokens hoặc nội dung cấu hình nằm trong các bảng cũng sẽ bị dump nếu không loại trừ. Không lưu dump vào Git, artifact CI public hoặc ticket.

### 32.3. Globals chứa auth metadata

`pg_dumpall --globals-only` có thể ghi password verifiers; phải phân quyền và mã hóa như secret material.

### 32.4. Restore là đường chạy SQL

Plain SQL dump có thể chứa functions/DDL và statements có tác động. Chỉ restore artifacts từ nguồn tin cậy, đọc/kiểm soát scope và không dùng superuser nếu không cần thiết.

### 32.5. Test restore cần masking và isolation

Một clone production chứa PII vẫn là dữ liệu production nhạy cảm. Test environment cần network isolation, RBAC, data retention và xử lý masking theo policy.

## 33. Kịch bản sự cố và lựa chọn khôi phục

### 33.1. Mất file CSV xuất cho đối tác

Có thể chạy lại export theo query/snapshot yêu cầu, nếu dữ liệu nguồn còn. Không cần phục hồi cả cluster.

### 33.2. Xóa nhầm 10 rows và có logical dump tối qua

Khôi phục dump vào database phụ, lấy 10 rows theo primary keys, sau đó reconciliation với dữ liệu hiện tại; không tự overwrite production database nếu có transactions hợp lệ mới.

### 33.3. Xóa nhầm bảng và có PITR

Dựng cluster phụ tới target trước lệnh DROP, copy dữ liệu cần thiết về production theo kế hoạch an toàn.

### 33.4. Mất cả storage cluster

Dùng physical backup + WAL, hoặc logical dump + globals nếu thời gian và phạm vi cho phép. Cần provision PostgreSQL service, roles, endpoints và ứng dụng.

### 33.5. Ransomware xóa bản backup cùng host

Nếu chỉ có local copies, có thể không phục hồi được. Offsite/immutable backup và quyền tách biệt là biện pháp quan trọng.

### 33.6. Lỗi schema migration

Có thể khôi phục từ pre-migration backup trong môi trường tách biệt, nhưng nếu có writes trong lúc migration, rollback toàn database có thể làm mất dữ liệu hợp lệ. Cần migration rollback/reconciliation protocol riêng.

## 34. Lộ trình phục hồi một database từ logical dump

~~~text
Chọn artifact và xác định snapshot
              |
              v
Tạo môi trường PostgreSQL cô lập
              |
              v
Chuẩn bị versions, extensions, roles
              |
              v
Tạo database đích sạch
              |
              v
psql hoặc pg_restore
              |
              v
Kiểm tra errors, indexes, constraints
              |
              v
Kiểm tra row counts, invariants, queries
              |
              v
Đo RPO/RTO, quyết định cutover
~~~

### 34.1. Không restore thử trên production trước

Nếu backup bị lỗi và dùng `--clean` trên production, bạn có thể mất thêm dữ liệu trước khi biết rằng restore không hoàn tất.

### 34.2. Restore globals có thể cần quyền cao

Chỉ thực hiện trên môi trường có chủ đích; không import role/superuser statements vào cluster chia sẻ một cách máy móc.

### 34.3. Schema-only/data-only không phải full restore

Một bản phục hồi đầy đủ cần cả objects và data, cộng dependencies ngoài dump.

### 34.4. Xác minh quyền và dữ liệu

Kiểm tra service role có SELECT/INSERT phù hợp, indexes tồn tại, sequences không gây duplicate và các extension functions hoạt động.

## 35. Lộ trình phục hồi một cluster vật lý

~~~text
Chọn base backup và recovery target
              |
              v
Xác nhận toàn bộ WAL/timeline chain
              |
              v
Provision host/storage/version tương thích
              |
              v
Giải mã/tải/khôi phục physical data
              |
              v
Cấu hình WAL restore và recovery target
              |
              v
Start PostgreSQL ở network cô lập
              |
              v
Replay WAL và kiểm tra recovery state
              |
              v
Kiểm tra dữ liệu, extensions, roles, services
              |
              v
Promote/cutover có kiểm soát
~~~

### 35.1. Backup restore không tự là application recovery

App endpoints, certificates, proxies, DNS, external services và secret distributions vẫn cần được khôi phục hoặc cập nhật.

### 35.2. Phiên bản phải tương thích

Physical backup không phải đường thay major PostgreSQL version. Với target khác major, dùng quy trình upgrade được hỗ trợ hoặc logical migration.

### 35.3. Quy trình phải có rollback plan

Nếu kiểm tra sau restore thất bại, phải giữ khả năng quay về trạng thái trước cutover mà không tạo split-brain hoặc ghi nhầm dữ liệu.

## 36. Ví dụ về backup từ standby và replicas

Backup một standby có thể giảm tải primary tùy cấu hình và công cụ, nhưng:

- Cần xác định backup này có thể restore tới mốc nào.
- WAL/archive phải phù hợp với timeline và replay point.
- Các thành phần filesystem/tablespace vẫn phải đầy đủ.
- Độ trễ standby có thể ảnh hưởng latest recovery point.
- Failover/promote có thể thay timeline và phương án lưu WAL.

### 36.1. Replica không lưu lịch sử vô tận

Một standby thường replay những thay đổi đã commit trên primary; dữ liệu bị xóa hợp lệ về mặt SQL có thể biến mất trên cả hai.

### 36.2. Không copy nóng tùy tiện từ standby

Phải dùng backup protocol/snapshot strategy phù hợp. Một database standby đang replay WAL vẫn là tiến trình có thay đổi files.

### 36.3. Chọn backup source theo mục tiêu

Việc backup trên primary hay standby phải cân nhắc consistency, network, resource contention và RPO, không chỉ số lần connection.

## 37. Khi nào dùng physical recovery, khi nào dùng logical restoration?

| Tiêu chí quyết định | Logical | Physical |
|---|---|---|
| Chọn một bảng để dựng lại | Thuận tiện hơn | Thường phải dựng cluster phụ |
| Di chuyển major PostgreSQL | Thường phù hợp | Không dùng nguyên PGDATA khác major |
| Dữ liệu cực lớn, cần khôi phục nhanh | Có thể tốn thời gian rebuild | Có thể hiệu quả hơn tùy storage |
| PITR gần thời điểm lỗi | Không từ dump đơn lẻ | Base backup + WAL |
| Phạm vi một database | Rất phù hợp | Backup toàn cluster |
| Các roles và cấu hình global | Cần đi kèm | Catalog có, config bên ngoài có thể thiếu |
| Thử một export query | Không cần full dump | Không cần |
| Phục hồi cluster đúng môi trường vật lý | Không phải bản sao byte-for-byte | Thiết kế cho mục tiêu này |

### 37.1. Không có lựa chọn thắng mọi tình huống

Một hệ thống production có thể duy trì cả hai: physical backups cho DR/PITR và logical dumps cho migrations, hoặc exports chuyên biệt cho analytics.

### 37.2. Đánh giá trên dữ liệu thật

RTO đo được từ một database 10 MB không thể ngoại suy đơn giản sang cluster 2 TB có indexes lớn, extensions và traffic cao.

## 38. Lab tổng hợp: chuẩn bị môi trường thử nghiệm

**Không chạy lab trên production.** Các ví dụ dùng một database riêng, giả định bạn có quyền tạo database/schema tại môi trường học tập. Nếu trùng tên database/schema đang tồn tại, hãy chọn tên khác thay vì xóa.

Trong terminal được cấu hình quyền thích hợp:

~~~sh
createdb backup_lab
psql -d backup_lab
~~~

Trong psql, tạo schema và bảng:

~~~sql
CREATE SCHEMA training;

CREATE TABLE training.customers (
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_name TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE training.orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL
        REFERENCES training.customers(customer_id),
    amount NUMERIC(18,2) NOT NULL CHECK (amount >= 0),
    status TEXT NOT NULL
        CHECK (status IN ('new', 'paid', 'cancelled')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX orders_customer_created_idx
ON training.orders (customer_id, created_at);
~~~

### 38.1. Nạp dữ liệu mẫu

~~~sql
INSERT INTO training.customers(customer_name)
VALUES ('Nguyễn An'), ('Trần Bình');

INSERT INTO training.orders(customer_id, amount, status)
SELECT customer_id, 125.50, 'new'
FROM training.customers
WHERE customer_name = 'Nguyễn An';

INSERT INTO training.orders(customer_id, amount, status)
SELECT customer_id, 400.00, 'paid'
FROM training.customers
WHERE customer_name = 'Trần Bình';
~~~

### 38.2. Vì sao có foreign key và index?

Lab cố ý chứa cấu trúc không thể tái tạo hoàn chỉnh chỉ từ một CSV rows: UNIQUE, FK, CHECK, identity và index. Đây là cơ sở so sánh export và dump.

### 38.3. Kiểm tra dữ liệu trước

~~~sql
SELECT
    count(*) AS order_count,
    sum(amount) AS sum_amount
FROM training.orders;

SELECT c.customer_name, o.order_id, o.amount, o.status
FROM training.orders AS o
JOIN training.customers AS c
  ON c.customer_id = o.customer_id
ORDER BY o.order_id;
~~~

Ghi lại kết quả để đối chiếu sau restore, nhưng không coi count và sum là bằng chứng đầy đủ duy nhất.

## 39. Lab: xuất orders.csv

Trong psql đang kết nối `backup_lab`:

~~~text
\copy (SELECT order_id, customer_id, amount, status, created_at FROM training.orders ORDER BY order_id) TO 'orders.csv' WITH (FORMAT csv, HEADER true)
~~~

### 39.1. File nằm ở đâu?

Tại nơi chạy psql; không phải máy database server nếu psql ở host khác.

### 39.2. Nội dung có những gì?

Header và các hàng theo cột SELECT. File không chứa CREATE TABLE, FK hay SQL index definition.

### 39.3. Kiểm tra schema không nằm trong CSV

Dùng text editor để xem file: nó không có DDL tự dựng table theo đúng kiểu PostgreSQL.

### 39.4. Export chỉ một bảng

`training.customers` không nằm trong orders.csv. Nếu import vào bảng có foreign key trên một database mới, cần nạp customers trước hoặc thiết kế workflow phù hợp.

### 39.5. Đừng copy production PII vào lab không kiểm soát

Lab dùng tên giả; với dữ liệu thật, cần masking hoặc synthetic data và giới hạn quyền file.

## 40. Lab: import CSV vào bảng staging

Trong database thử nghiệm, tạo bảng nhận CSV:

~~~sql
CREATE TABLE training.orders_imported (
    order_id BIGINT,
    customer_id BIGINT,
    amount NUMERIC(18,2),
    status TEXT,
    created_at TIMESTAMPTZ
);
~~~

Trong psql:

~~~text
\copy training.orders_imported (order_id, customer_id, amount, status, created_at) FROM 'orders.csv' WITH (FORMAT csv, HEADER true)
~~~

### 40.1. COUNT và SUM

~~~sql
SELECT
    count(*) AS rows_imported,
    sum(amount) AS amount_imported
FROM training.orders_imported;
~~~

### 40.2. Vì sao không tự tạo FK?

Chỉ CREATE TABLE phía trên mới quyết định constraints. `\copy` không suy ra PRIMARY KEY/FK/NOT NULL từ file.

### 40.3. Hai bản sao dữ liệu có thể cùng tồn tại

Bảng staging không tự được liên kết với ứng dụng. Dữ liệu phục hồi một phần phải có kế hoạch merge/validation và giải quyết conflicts.

### 40.4. NULL và empty string

Trong CSV mode, biểu diễn NULL và chuỗi rỗng phụ thuộc quoting và COPY options. Phải dùng format contract tương ứng để không làm thay đổi ý nghĩa.

### 40.5. CSV formula injection

Nếu file được mở trong spreadsheet, những giá trị text đầu bằng ký tự mà phần mềm nhận là formula có thể gây rủi ro. Khi xuất cho spreadsheet consumers, cần sanitize theo đúng context; không áp dụng một cách biến đổi làm hỏng dữ liệu khi import lại vào PostgreSQL.

## 41. Lab: tạo custom logical dump

Thoát psql, chạy trong terminal:

~~~sh
pg_dump -d backup_lab -F c -f backup_lab.dump
~~~

### 41.1. Database scope

Lệnh chỉ dump `backup_lab`, không tạo bản sao của mọi databases/roles toàn cluster.

### 41.2. Archive gồm objects và data

Trong full dump có DDL của schema/bảng/index/constraints và dữ liệu trong phạm vi dump.

### 41.3. Liệt kê TOC

~~~sh
pg_restore --list backup_lab.dump
~~~

Bạn sẽ thấy danh mục có các objects liên quan. Điều này kiểm tra khả năng đọc TOC, **chưa phải restore test**.

### 41.4. Bản dump chụp cả bảng staging

Vì lab đã tạo `orders_imported` trước khi dump, bảng này cũng thuộc database và có thể nằm trong dump. Muốn tránh, dùng database sạch hoặc dump trước bước import; cần hiểu scope chính xác.

### 41.5. Ghi metadata

Lưu tên database, server major version, pg_dump version, thời điểm snapshot/job và file checksum trong backup manifest độc lập.

## 42. Lab: khôi phục custom dump vào database mới

Trong terminal:

~~~sh
createdb backup_lab_restored
pg_restore --exit-on-error --no-owner --no-acl -d backup_lab_restored backup_lab.dump
~~~

### 42.1. Vì sao dùng --no-owner và --no-acl trong lab?

Để bớt phụ thuộc role/privilege definitions của nguồn khi phục hồi trong môi trường thử nghiệm. Đây là **lựa chọn đổi security state**; không dùng làm bằng chứng đã phục hồi quyền production nguyên vẹn.

### 42.2. Vì sao dùng --exit-on-error?

Giúp phát hiện rõ khi một lệnh SQL trong restore thất bại, thay vì tiếp tục và vô tình cho rằng database đã đầy đủ.

### 42.3. Xác minh schema

~~~sh
psql -d backup_lab_restored
~~~

~~~sql
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_schema = 'training'
ORDER BY table_name;

SELECT count(*), sum(amount)
FROM training.orders;
~~~

### 42.4. Xác minh constraints

Trong psql:

~~~text
\d+ training.orders
~~~

Kiểm tra PRIMARY KEY, FK, CHECK, index và default/identity; không chỉ đếm rows.

### 42.5. Xác minh join

~~~sql
SELECT c.customer_name, count(o.order_id), sum(o.amount)
FROM training.customers AS c
LEFT JOIN training.orders AS o
  ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
~~~

### 42.6. Xác minh row generation

Một INSERT mới trong database phục hồi có thể xác nhận identity/sequence đã được xử lý hợp lý, nhưng chỉ làm trong lab và đảm bảo không gây trùng khóa.

## 43. Lab: plain SQL dump khác archive

~~~sh
pg_dump -d backup_lab -F p -f backup_lab.sql
createdb backup_lab_plain
psql -X -v ON_ERROR_STOP=1 -d backup_lab_plain -f backup_lab.sql
~~~

### 43.1. Plain SQL đọc được bằng text editor

Nó bao gồm SQL DDL và statements nạp dữ liệu. Không nhất thiết thuận tiện bằng custom archive khi cần TOC, chọn items và parallel restoration.

### 43.2. pg_restore không dùng cho plain dump

`pg_restore` dành cho các archive formats của pg_dump. Dùng psql cho plain SQL script.

### 43.3. Chú ý command shell

Các câu lệnh trên là ví dụ shell được chạy từng lệnh. Nếu môi trường dùng PowerShell, có thể gọi executable theo cú pháp tương ứng; tránh nhầm các câu SQL bên trong file với shell commands.

### 43.4. Không mặc định plain SQL dump an toàn khi restore tùy ý

SQL script có thể chứa CREATE FUNCTION hoặc statements thay đổi objects. Chỉ restore nguồn tin cậy vào database xác định trước.

## 44. Lab: dump một schema và những gì bị bỏ sót

~~~sh
pg_dump -d backup_lab -F c -n training -f training_schema.dump
~~~

### 44.1. Chọn lọc giúp giảm phạm vi

Nhưng không có nghĩa tất cả dependencies của objects được chọn đều được dump. Nếu bảng thuộc schema training dùng một enum/function/extension ở schema khác, restore chỉ training có thể thiếu dependencies.

### 44.2. Kết quả không thay backup toàn database

Một schema dump không chứa mọi database objects, cũng không tự có cluster globals.

### 44.3. Khi cần lấy một bảng

Có thể dùng `-t` hoặc chọn objects từ custom archive; phải kiểm tra dữ liệu liên quan và constraints trước khi phục hồi.

### 44.4. Đừng áp dụng partial restore vào production thiếu đối chiếu

Một table có FK từ các bảng khác, triggers phát sự kiện hoặc sequence riêng. Restore bảng trong isolation có thể gây trạng thái nghiệp vụ không khớp.

## 45. Lab: kiểm kê globals nhưng không xuất secrets lên màn hình

Trong môi trường thử nghiệm với quyền phù hợp:

~~~sh
pg_dumpall --globals-only -f globals-backup.sql
~~~

### 45.1. Phạm vi

Có thể có CREATE ROLE, ALTER ROLE, tablespaces và những global definitions theo options/version. Đây không phải dump dữ liệu của toàn bộ các tables.

### 45.2. Phân quyền file

File có thể chứa password verifiers/metadata nhạy cảm. Không in toàn bộ file vào logs, chat, CI artifacts hoặc gửi cho người không có quyền.

### 45.3. Restore globals cần đánh giá trước

Không phát lại toàn bộ vào cluster đang có users/roles trùng tên. Với production restore, cần kế hoạch security/ownership rõ và environment isolation.

### 45.4. Database dump và globals dump là hai artifacts

Nếu muốn tái dựng hệ thống logic ở cluster sạch, phải biết chính xác bản nào đi với bản nào, tránh ghép globals của một ngày với database dump không tương thích quyền.

## 46. Lab: bản sao vật lý và kiểm tra manifest

Trên host backup được cấp phép và có storage độc lập, lệnh minh họa:

~~~sh
pg_basebackup -h primary.example.test -U backup_agent -D /backup/base-test -F p -X stream -P
~~~

### 46.1. Không chạy vào data directory sống

`/backup/base-test` là thư mục đích mới trong lab. Không trỏ `-D` vào PGDATA của một cluster đang hoạt động.

### 46.2. Điều kiện kết nối

Role cần quyền replication/HBA phù hợp. Máy backup cần dung lượng đủ, host network truy cập được primary và PostgreSQL protocol tương thích.

### 46.3. Manifest

Trong PostgreSQL versions hỗ trợ backup manifests, `pg_basebackup` có thể tạo manifest để kiểm tra bằng công cụ tương ứng, ví dụ:

~~~sh
pg_verifybackup /backup/base-test
~~~

### 46.4. Verifybackup chưa bằng restore

Manifest verification kiểm tra tập files/checksums theo khả năng công cụ, không kiểm chứng môi trường boot, application queries, external dependencies hay WAL archive retention sau backup.

### 46.5. Diễn tập physical recovery cần môi trường riêng

Vì đây là bản dữ liệu toàn cluster, việc restore phải tiến hành ở host/data directory được cô lập và đúng PostgreSQL major version. Không dùng bản copy này để ghi đè production như một phép thử.

## 47. Điều gì chứng minh một bản backup “phục hồi được”?

Một backup đáp ứng mục tiêu khi các điều kiện sau đều có bằng chứng:

1. **Artifact hoàn chỉnh:** các file/tệp archive hoặc backup chain có thể đọc đầy đủ.
2. **Truy xuất được:** storage, network, permissions và keys còn tồn tại khi primary không còn.
3. **Phù hợp phần mềm:** PostgreSQL và extension/runtime versions có thể sử dụng backup.
4. **Đúng phạm vi:** đủ database objects, roles, tablespaces, WAL và external dependencies cần thiết.
5. **Đúng điểm dữ liệu:** recovered state đạt RPO đã định.
6. **Đúng thời gian:** thực tế hoàn tất phục hồi trong RTO đã định.
7. **Đúng nghiệp vụ:** ứng dụng chạy và dữ liệu vượt qua constraints/các reconciliation checks.
8. **Có quy trình lặp lại:** người vận hành có thể thực hiện lại mà không phụ thuộc vào kiến thức truyền miệng của một cá nhân.

### 47.1. Bản backup hợp lệ của hôm qua chưa bảo đảm hôm nay

Cấu hình thêm tablespace, extension hoặc database mới có thể khiến backup job cũ không còn đầy đủ. Cần rà soát scope khi kiến trúc thay đổi.

### 47.2. Khôi phục thành công nhưng chậm hơn RTO vẫn là không đạt mục tiêu

Nếu doanh nghiệp yêu cầu 30 phút nhưng quy trình restore mất 6 giờ, file không hỏng nhưng chiến lược DR không đáp ứng nhu cầu.

### 47.3. Restore test không được giả lập đơn giản

Test chỉ copy file từ một backup disk trên chính host nguồn không phản ánh sự cố mất host/region. Cần thử điều kiện tương đương thảm họa mà kế hoạch tuyên bố bảo vệ.

### 47.4. Cần ghi kết quả diễn tập

Ghi backup ID, target, thời điểm restore, thời gian tải/giải mã/khởi động, errors, checks, vai trò thao tác và các bước cần sửa trong runbook.

## 48. Bài toán RPO/RTO khi có nhiều lớp bảo vệ

Giả sử một hệ thống thương mại có:

- CSV export mỗi 24 giờ cho báo cáo.
- pg_dump full mỗi đêm.
- Physical base backup mỗi ngày.
- WAL archive liên tục, với độ trễ có giám sát.
- Hot standby trong một availability zone khác.
- Offsite immutable backup copy.

### 48.1. CSV phục vụ analytics

Không dùng CSV export như tuyến khôi phục toàn cluster.

### 48.2. pg_dump phục vụ logical restore

Có thể giúp lấy bảng bị xóa nhầm hoặc migration major version, nhưng RPO của dump nằm ở snapshot.

### 48.3. Base backup + WAL phục vụ PITR

Có thể dùng cho tình huống data corruption hoặc xóa nhầm cần quay về mốc cụ thể, nếu WAL chain còn đủ.

### 48.4. Standby phục vụ failover

Giúp giảm downtime khi primary hỏng; nó có thể replay cả thao tác lỗi nên không thay backup history.

### 48.5. Offsite immutable copy chống xóa phá hoại

Giúp tránh backup bị xóa cùng môi trường nguồn; tuy vậy phải kiểm tra khả năng lấy key, download và thời gian phục hồi.

### 48.6. Không cộng các RPO một cách tùy ý

RPO thực tế phụ thuộc kịch bản. Sự cố mất một host có thể dùng replica; sự cố logical corruption lan cả primary/standby có thể phải PITR. Cần xác định RPO/RTO cho từng loại thảm họa.

## 49. Khi cần khôi phục một bảng bị xóa nhầm

### 49.1. Không vội restore toàn production cluster về hôm qua

Điều đó có thể làm mất các transactions hợp lệ mới.

### 49.2. Dựng database phụ từ logical dump

Nếu dump gần đủ để lấy bảng bị xóa, phục hồi archive vào `restore_tmp`, xuất dữ liệu cần thiết từ đó và nhập có kiểm soát vào production.

### 49.3. Dựng physical cluster phụ với PITR

Nếu cần thời điểm ngay trước lỗi, dựng cluster phụ từ base backup + WAL, kiểm tra bảng và chỉ lấy tập dữ liệu cần cứu.

### 49.4. Reconciliation quan trọng

Nếu bảng phụ thuộc customer, payments, child tables hoặc events đã được xử lý bên ngoài, copy thô có thể tạo trùng giao dịch hoặc xung đột references. Phải có quy tắc merge rõ.

### 49.5. Các sequences sau import

Khi nạp lại explicit primary keys, kiểm tra identity/sequence state trước khi ứng dụng tiếp tục INSERT.

### 49.6. Không loại bỏ audit trails

Việc sửa lại dữ liệu do sự cố cần có record về thao tác phục hồi, người thực hiện và phạm vi chỉnh sửa theo chính sách nghiệp vụ.

## 50. Runbook mẫu cho một lần phục hồi

### Giai đoạn A — Xác minh sự cố

- Xác định loại sự cố: mất host, xóa nhầm, corruption, ransomware hay lỗi app.
- Đóng băng những thao tác có thể gây hỏng thêm khi cần.
- Chọn recovery target/timeline và scope.
- Ước lượng RPO/RTO kỳ vọng.

### Giai đoạn B — Chọn artifact

- Kiểm tra backup ID, trạng thái job và checksum/manifest.
- Xác nhận chain WAL/timeline (nếu PITR).
- Xác nhận globals/roles, tablespaces, extension packages và config.
- Xác nhận storage/key vẫn truy cập khi primary không còn.

### Giai đoạn C — Dựng môi trường

- Provision PostgreSQL version tương thích.
- Tách network/ports và credentials để không ghi nhầm production.
- Chuẩn bị file ownership, disk paths và tablespaces.
- Tải và giải mã artifacts theo quyền được cấp.

### Giai đoạn D — Restore

- Với logical: tạo database đích sạch, chạy psql/pg_restore và lưu logs/errors.
- Với physical: restore base backup, WAL recovery config/target, start PostgreSQL riêng.
- Giám sát tiến độ, disk/CPU/network và lỗi.
- Chỉ promote/cutover theo phê duyệt của incident plan.

### Giai đoạn E — Xác minh

- Kiểm tra row counts và business aggregates.
- Kiểm tra FK/unique/check constraints và indexes.
- Xác nhận sequences/identities không trùng khóa.
- Kiểm tra roles, ownership, RLS, extensions, permissions.
- Xác nhận application health/read-write flows và external integrations.
- Đo thời gian và dữ liệu cuối cùng đã phục hồi.

### Giai đoạn F — Mở traffic và theo dõi

- Chỉ mở ghi sau khi nhất trí primary duy nhất.
- Cập nhật endpoints/connection pools/secrets khi cần.
- Theo dõi errors, replica state và backlog reconciliation.
- Ghi postmortem, cập nhật runbook và lịch diễn tập tiếp theo.

## 51. Những hiểu lầm phổ biến

### 51.1. “CSV có tất cả rows thì là full database backup”

**Sai.** Nó không có schema, permissions, WAL và nhiều dependencies.

### 51.2. “COPY TO '/path' ghi file lên laptop người dùng”

**Sai.** Đường dẫn server-side nằm trên host PostgreSQL; `\copy` mới làm thao tác file ở client psql.

### 51.3. “psql \copy là câu SQL chạy được từ JDBC”

**Sai.** Đó là psql meta-command.

### 51.4. “Hai file CSV export liền nhau chắc chắn cùng snapshot”

**Sai.** Hai statements có thể lấy snapshots khác.

### 51.5. “pg_dump -d db1 tự sao lưu db2”

**Sai.** Nó dump database được chọn.

### 51.6. “pg_dump -Fc tạo SQL plain text”

**Sai.** Nó tạo custom archive, phục hồi bằng pg_restore.

### 51.7. “pg_restore đọc mọi file .sql”

**Sai.** Plain SQL thường chạy qua psql; đuôi file không quyết định format.

### 51.8. “pg_dumpall cho snapshot nguyên tử của mọi database”

**Sai.** Nó có thể xử lý các databases theo thời điểm khác nhau.

### 51.9. “pg_dump backup đầy đủ users và server config”

**Sai.** Globals và file cấu hình cần xử lý riêng.

### 51.10. “pg_dump --schema-only vẫn lưu toàn bộ rows”

**Sai.** Nó chủ yếu lưu schema definitions trong phạm vi dump.

### 51.11. “pg_dump --data-only có thể restore database trống không cần schema”

**Sai.** Cần schema và dependencies.

### 51.12. “File dump đọc TOC được nghĩa restore thành công”

**Sai.** Phải thử phục hồi.

### 51.13. “Restore --no-owner --no-acl bảo toàn permissions gốc”

**Sai.** Các tùy chọn đó bỏ ownership/grants theo phạm vi phù hợp.

### 51.14. “--clean và --if-exists luôn an toàn”

**Sai.** Vẫn có thể DROP objects của database đích.

### 51.15. “Một file WAL đủ tạo cả database”

**Sai.** Cần base data state và WAL chain phù hợp.

### 51.16. “WAL nằm trong pg_wal luôn sống sót khi mất primary disk”

**Sai.** WAL trên cùng disk có thể mất cùng cluster.

### 51.17. “pg_basebackup -X stream cho PITR mọi thời điểm tương lai”

**Sai.** Nó thu WAL liên quan backup; tương lai cần archive/retention tiếp tục.

### 51.18. “Có physical backup là phục hồi được trên mọi PostgreSQL major version”

**Sai.** Physical data format phụ thuộc version/compatibility.

### 51.19. “Hot standby tương đương backup có lịch sử”

**Sai.** Replica có thể replay lệnh xóa nhầm.

### 51.20. “PITR có thể chỉ undo một row và giữ mọi transaction khác bằng một option”

**Sai.** PITR phục hồi trạng thái cluster theo target.

### 51.21. “Checksum trùng nghĩa application chạy được”

**Sai.** Checksum không kiểm tra business/role/external dependencies.

### 51.22. “Backup mỗi ngày đáp ứng RPO 5 phút”

**Sai** nếu không có một đường giữ lại dữ liệu mới hơn đủ tin cậy.

### 51.23. “Khôi phục được data sau 10 giờ nghĩa đạt RTO 30 phút”

**Sai.** RTO cần đo từ lúc sự cố đến lúc dịch vụ đáp ứng.

### 51.24. “Backup nằm chung instance cũng chống mất cả instance”

**Sai.** Cần storage/địa điểm độc lập.

### 51.25. “File backup đã encryption thì có thể bỏ bảo vệ key”

**Sai.** Key mất thì backup có thể không giải mã được; key lộ thì dữ liệu lộ.

### 51.26. “Logical dump không bao giờ là backup”

**Sai.** Nếu mục tiêu chỉ restore snapshot, logical dump đã kiểm chứng có thể đáp ứng.

### 51.27. “Một snapshot vật lý bất kỳ luôn nhất quán”

**Sai.** Phải đáp ứng PostgreSQL crash/backup consistency và đủ volumes/tablespaces.

### 51.28. “Phục hồi bảng từ dump sẽ tự đồng bộ tất cả external services”

**Sai.** Cần reconciliation với queues, payment gateway, object storage.

### 51.29. “Data warehouse export là một DR plan”

**Sai.** Analytics exports chỉ bảo vệ tập dữ liệu theo contract riêng, không phải cluster recovery.

### 51.30. “Một lần restore test năm ngoái chứng minh backup hiện nay vẫn đủ”

**Sai.** Schema, storage, permissions, versions và workloads thay đổi theo thời gian.

## 52. Bài tập thực hành

### Bài 1 — Phân loại CSV

Bạn có file `customers.csv` chứa customer_id và tên. Đây là export, logical dump hay physical backup?

**Đáp án:** Export dữ liệu.

### Bài 2 — Schema bị thiếu

Vì sao không thể tạo lại indexes và foreign keys chỉ từ CSV khi không có schema contract?

**Gợi ý:** CSV chứa giá trị, không chứa đầy đủ DDL metadata.

### Bài 3 — COPY path

`COPY table TO '/tmp/x.csv'` ghi file ở máy nào?

**Đáp án:** Máy chủ PostgreSQL.

### Bài 4 — \copy path

`\copy table TO 'x.csv'` ghi file ở máy nào?

**Đáp án:** Máy chạy psql.

### Bài 5 — JDBC

Có thể gửi trực tiếp `\copy` qua JDBC SQL statement không?

**Đáp án:** Không; dùng COPY SQL/driver COPY API.

### Bài 6 — Hai export snapshots

Vì sao export orders và customers bằng hai statements riêng có thể không đồng nhất?

**Gợi ý:** Hai snapshots khác thời điểm.

### Bài 7 — Filter

File CSV tạo bởi SELECT WHERE có tự chứa tất cả rows không?

**Đáp án:** Không; chỉ rows phù hợp predicate.

### Bài 8 — CSV import

Sau khi nhập CSV với ID cũ, cần kiểm tra cơ chế sinh ID nào?

**Gợi ý:** Identity/sequence.

### Bài 9 — Logical dump

`pg_dump -d trainingdb` có dump toàn cluster không?

**Đáp án:** Không.

### Bài 10 — Format

`pg_dump -F c` tạo định dạng nào?

**Đáp án:** Custom archive.

### Bài 11 — Restore custom

Công cụ nào dùng để xem TOC của custom archive?

**Đáp án:** `pg_restore --list`.

### Bài 12 — Restore plain

Dùng công cụ nào để thực thi plain SQL dump?

**Đáp án:** psql.

### Bài 13 — Directory dump

Có thể copy một file data bất kỳ trong directory archive để coi là dump đầy đủ không?

**Đáp án:** Không; cần toàn bộ archive.

### Bài 14 — Schema-only

Schema-only có tự chứa rows không?

**Đáp án:** Không.

### Bài 15 — Data-only

Data-only có tự tạo mọi bảng trong database sạch không?

**Đáp án:** Không.

### Bài 16 — pg_restore -j

Tùy chọn nào giúp song song restore trong phạm vi archive hỗ trợ?

**Đáp án:** `-j`.

### Bài 17 — --clean

Vì sao --clean nguy hiểm?

**Gợi ý:** Có thể DROP objects trên đích.

### Bài 18 — --no-acl

Tại sao --no-acl không chứng minh restore bảo toàn quyền?

**Gợi ý:** Nó bỏ GRANT/REVOKE tương ứng.

### Bài 19 — Globals

Để dump role/tablespace definitions cần công cụ/options nào?

**Gợi ý:** `pg_dumpall --globals-only`.

### Bài 20 — Password verifiers

File globals có thể chứa dữ liệu nhạy cảm gì?

**Gợi ý:** Auth metadata/password verifiers.

### Bài 21 — Snapshot

Dump chạy 01:00–01:45 có chắc chứa mọi transaction tới 01:45 không?

**Đáp án:** Không.

### Bài 22 — Multi-database

pg_dumpall có bảo đảm snapshot chung cho tất cả databases không?

**Đáp án:** Không.

### Bài 23 — WAL

WAL có tự chứa toàn bộ data pages cần thiết cho database không?

**Đáp án:** Không; cần base backup.

### Bài 24 — Basebackup

`pg_basebackup` sao lưu một bảng hay cả database cluster?

**Đáp án:** Cả cluster.

### Bài 25 — PITR

Những thành phần chính cho PITR là gì?

**Gợi ý:** Base backup, WAL chain, recovery settings/target và môi trường tương thích.

### Bài 26 — Missing WAL

Thiếu một segment WAL bắt buộc ảnh hưởng gì?

**Gợi ý:** Có thể không replay được tới target mong muốn.

### Bài 27 — pg_wal

WAL nằm trên cùng disk primary có phải offsite backup không?

**Đáp án:** Không.

### Bài 28 — Replication slot

Vì sao replication slot không thay backup và còn có thể gây đầy disk?

**Gợi ý:** Giữ WAL cho consumer, không tự copy offsite; lag có thể kéo dài.

### Bài 29 — RPO

RPO 15 phút nghĩa là gì?

**Gợi ý:** Mức mất dữ liệu theo thời gian tối đa được phép.

### Bài 30 — RTO

RTO 1 giờ nghĩa là gì?

**Gợi ý:** Dịch vụ phải trở lại trạng thái chấp nhận được trong tối đa 1 giờ.

### Bài 31 — RPO với dump

Dump 01:00, lỗi 12:00, chỉ có dump. RPO thực trong kịch bản này tối đa khoảng bao lâu?

**Gợi ý:** Khoảng 11 giờ nếu snapshot thực là 01:00.

### Bài 32 — RTO với restore

Sự cố 12:00, dịch vụ hoạt động lại 15:30. Thời gian phục hồi?

**Đáp án:** 3 giờ 30 phút.

### Bài 33 — Replica

Replica có tự bảo vệ trước lệnh DROP TABLE được replay không?

**Đáp án:** Không.

### Bài 34 — Logical migration

Tại sao dump/restore thường phù hợp khi nâng PostgreSQL major version?

**Gợi ý:** Logical representation tái tạo objects theo engine version mới.

### Bài 35 — Physical migration

Tại sao không khởi động data directory PG major cũ bằng binary major mới?

**Gợi ý:** Data format/compatibility khác.

### Bài 36 — Extensions

Dump có CREATE EXTENSION nhưng restore thiếu library ở target. Kết quả có thể thế nào?

**Gợi ý:** Restore thất bại hoặc objects phụ thuộc không hoạt động.

### Bài 37 — Checksum

Một file có checksum đúng đã chứng minh app có thể chạy chưa?

**Đáp án:** Chưa.

### Bài 38 — pg_verifybackup

pg_verifybackup thay toàn bộ restore drill được không?

**Đáp án:** Không.

### Bài 39 — Dựng cluster phụ

Tại sao nên phục hồi table bị xóa vào database/cluster phụ?

**Gợi ý:** Không làm mất các transactions hợp lệ trên production.

### Bài 40 — Retention

Vì sao không xóa base backup mà incremental chain vẫn phụ thuộc?

**Gợi ý:** Chain trở nên không phục hồi được.

### Bài 41 — Offsite storage

Backup trên cùng disk primary có bảo vệ trước mất cả disk không?

**Đáp án:** Không.

### Bài 42 — Encryption keys

Nếu có backup được mã hóa nhưng mất key, hệ quả?

**Gợi ý:** Có thể không giải mã/phục hồi được.

### Bài 43 — Versioning

Một backup cũ vẫn dùng PostgreSQL 14, máy đích PostgreSQL 17. Chọn logical hay physical strategy thuận lợi hơn?

**Gợi ý:** Logical dump/restore nếu SQL/extensions tương thích; không đưa raw PGDATA v14 vào v17.

### Bài 44 — External storage

Nếu database chứa đường dẫn tới 5 TB object storage, pg_dump có tự sao lưu toàn bộ objects đó không?

**Đáp án:** Không.

### Bài 45 — Thiết kế tổng hợp

Một hệ thống PostgreSQL 2 TB yêu cầu RPO tối đa 5 phút, RTO 1 giờ, có HA standby, cần phục hồi khi xóa nhầm dữ liệu và bảo vệ trước mất một region. Bạn sẽ triển khai các lớp nào?

**Gợi ý:** Physical backups định kỳ, continuous WAL archive giám sát độ trễ, offsite/immutable storage, HA cho failover, retention chain, automated restore drills, cross-region credentials/key management, test PITR và đo RPO/RTO; logical dump có thể bổ sung cho object-level recovery.

## 53. Checklist trước khi coi một backup có thể phục hồi

### 53.1. Mục tiêu

- [ ] Đã định nghĩa cụ thể kịch bản sự cố?
- [ ] Scope: rows, table, database hay cluster?
- [ ] RPO và RTO có con số rõ?
- [ ] Có cần PITR hay chỉ snapshot?
- [ ] Có cần bảo tồn transactions sau một lỗi logic?
- [ ] Có external services cần reconciliation?

### 53.2. Artifacts

- [ ] Backup job hoàn tất và exit code thành công?
- [ ] Có đủ files/backup manifest?
- [ ] Có globals/roles/tablespaces/extension dependencies?
- [ ] Có đủ WAL segments và timeline cần thiết?
- [ ] Có phiên bản tool/PostgreSQL được ghi lại?
- [ ] Có metadata snapshot/consistent point?
- [ ] Có checksum/integrity verification phù hợp?
- [ ] Có backup chain dependency mapping?

### 53.3. Storage và bảo mật

- [ ] Storage độc lập với primary?
- [ ] Có offsite/cross-zone/region copy nếu yêu cầu?
- [ ] IAM phân tách backup writers/restore readers/delete admins?
- [ ] Encryption at rest/in transit?
- [ ] Encryption keys vẫn có thể truy xuất khi thảm họa?
- [ ] Artifact không bị public/CI log/Git leak?
- [ ] Có immutable retention khi cần chống xóa phá hoại?
- [ ] Có giám sát dung lượng và WAL archive failures?

### 53.4. Restore test

- [ ] Đã thực sự dựng database/cluster mới?
- [ ] Đã kiểm tra restore errors và logs?
- [ ] Đã chạy queries xác minh dữ liệu?
- [ ] Đã kiểm tra indexes, constraints và sequences?
- [ ] Đã thử roles, permissions, RLS và extensions?
- [ ] Đã thử ứng dụng kết nối, read/write business flows?
- [ ] Đã đo thực tế RPO và RTO?
- [ ] Đã ghi kết quả drill và người chịu trách nhiệm?
- [ ] Đã thử theo kịch bản mất hạ tầng thật thay vì copy local file?

## 54. Cây quyết định chọn công cụ

~~~text
Bạn cần làm gì?
    |
    +-- Chia sẻ/tải dữ liệu theo query?
    |       |
    |       +--> COPY / \copy / ETL / JSON export
    |
    +-- Di chuyển/tái tạo một số database objects?
    |       |
    |       +--> pg_dump + pg_restore / psql
    |               |
    |               +--> Cần roles/tablespaces?
    |                        |
    |                        +--> pg_dumpall --globals-only
    |
    +-- Khôi phục dữ liệu sau sự cố?
            |
            +-- Chỉ cần snapshot cuối đêm;
            |   database đủ nhỏ, RTO phù hợp?
            |        |
            |        +--> Logical dump đã kiểm chứng
            |
            +-- Cần phục hồi cả cluster/PITR?
                     |
                     +--> Physical base backup
                          + WAL archive/retention
                          + recovery runbook
                          + restore drills
    |
    v
Luôn kiểm tra RPO, RTO, dependencies và bảo mật
~~~

### 54.1. Một công cụ không phục vụ mọi mục tiêu

CSV export rất tốt cho trao đổi dữ liệu. pg_dump rất tốt cho logical snapshot. Physical base backup và WAL rất quan trọng cho khả năng phục hồi ở cấp cluster và các mốc thời gian cụ thể.

### 54.2. Chọn theo sự cố tồi nhất cần bảo vệ

Một hệ thống có thể đáp ứng restore table nhưng không đáp ứng mất region. RPO/RTO và cost cần gắn với threat model thực tế.

## 55. Bảng tra cứu nhanh

| Thành phần | Ghi nhớ |
|---|---|
| `SELECT` | Truy vấn dữ liệu |
| `COPY ... TO` | Export dữ liệu qua SQL, server path khi dùng file |
| `\copy` | psql client-side file export/import |
| CSV/TSV/JSON | Format dữ liệu, không có đầy đủ DB metadata |
| `pg_dump` | Logical dump của một database |
| `pg_dumpall` | Plain SQL cho cluster databases/globals |
| `--globals-only` | Dump cluster-wide roles/tablespaces metadata |
| `-F p` | Plain SQL |
| `-F c` | Custom archive |
| `-F d` | Directory archive |
| `-F t` | Tar archive |
| `psql -f` | Restore plain SQL |
| `pg_restore` | Restore custom/directory/tar archives |
| `pg_restore --list` | Xem TOC, không phải restore test |
| `--clean` | DROP trước khi tạo, phải thận trọng |
| `--no-owner` | Bỏ phục hồi ownership |
| `--no-acl` | Bỏ GRANT/REVOKE từ dump |
| `pg_basebackup` | Physical base backup của cluster |
| `WAL` | Nhật ký phục vụ recovery/replication |
| WAL archive | Lưu WAL tại nơi độc lập để khôi phục lịch sử |
| PITR | Phục hồi cluster tới recovery target |
| `recovery.signal` | Tín hiệu recovery trong các bản PG hiện đại |
| `restore_command` | Lấy WAL từ archive khi recovery |
| `pg_verifybackup` | Kiểm tra manifest của backup phù hợp |
| RPO | Mức mất dữ liệu có thể chấp nhận |
| RTO | Thời gian phục hồi có thể chấp nhận |
| Hot standby | Phục vụ HA, không thay backup history |
| Incremental chain | Phải giữ đủ các dependencies |
| Restore drill | Bằng chứng recoverability thực tế |
| Offsite/immutable backup | Giảm rủi ro mất/xóa cùng primary |
| Extension/role dependencies | Phải kiểm tra ngoài dữ liệu rows |
| External systems | Cần backup/reconciliation riêng |

---

## 56. Kết luận

**Xuất dữ liệu, dump logic và bản sao lưu phục hồi được là ba khái niệm liên quan nhưng không thay thế nhau.** Xuất dữ liệu bằng COPY, \copy hoặc truy vấn CSV/JSON lấy đúng tập hàng phục vụ trao đổi/ETL; nó không tự tái tạo schema, constraints, quyền và WAL. Logical dump bằng pg_dump có thể tái tạo objects và dữ liệu của một database ở snapshot, rất hữu ích cho migration và phục hồi theo mốc dump, nhưng một dump riêng không có WAL để PITR tới thời điểm sau đó.

**Khả năng phục hồi cấp cluster và theo thời điểm thường dựa trên physical base backup cùng chuỗi WAL được lưu và kiểm tra đầy đủ.** Một bản sao vật lý không đúng quy trình hoặc thiếu WAL cần thiết có thể không restore được dù file hiện diện. Replication/standby giảm downtime trong một số sự cố, nhưng vẫn có thể sao chép lệnh xóa nhầm và không thay lịch sử backup.

Điều quyết định backup có đạt yêu cầu không là **RPO/RTO và lần phục hồi thử thành công**, không phải kích thước file hay thông báo “job completed”. Một phương án tin cậy phải bảo vệ artifacts và encryption keys, lưu đủ globals/extensions/external dependencies, có retention theo backup chain, quy trình dựng môi trường cô lập, kiểm chứng constraints/transactions/ứng dụng và diễn tập theo kịch bản thảm họa.

**Nguyên tắc thực hành:** dùng export khi cần *dữ liệu*, dùng pg_dump khi cần *logical snapshot*, dùng physical backups và WAL khi cần *disaster recovery/PITR*, và chỉ gọi đó là **backup phục hồi được** khi đã chứng minh có thể khôi phục đúng phạm vi, đúng mốc dữ liệu và trong thời gian doanh nghiệp chấp nhận.







